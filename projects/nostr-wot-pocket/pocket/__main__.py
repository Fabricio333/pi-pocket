"""Device shell: display ownership, app lifecycle, and marketplace navigation."""
import json, os, queue, threading, time
from pathlib import Path
from types import SimpleNamespace
from .ui import UI, ROOT, ACCENT, MUTED, BG
from .registry import Registry
from .controls import ThreeButtonControls

def run():
    # Import hardware only when running the device, never during catalog tests.
    from .drivers.ST7789 import ST7789
    lcd=ST7789();lcd.Init();lcd.bl_DutyCycle(80)
    state=Path(os.environ.get('POCKET_STATE_DIR',str(Path.home()/'.local/share/nostr-wot-pocket')))
    state.mkdir(parents=True,exist_ok=True)
    os.environ['POCKET_STATE_DIR']=str(state)
    ui=UI();registry=Registry(state)
    ctx=SimpleNamespace(ui=ui,events=queue.Queue(),invoice=None,
                        sink=os.environ.get('POCKET_AUDIO_SINK','@DEFAULT_SINK@'))
    if os.environ.get('POCKET_LED_ADDRESS') or os.environ.get('POCKET_SPEAKER_ADDRESS'):
        from .celebration import prepare
        prepare()
    pins={name:getattr(lcd,attr) for name,attr in {
        'one':'GPIO_KEY1_PIN','two':'GPIO_KEY2_PIN','three':'GPIO_KEY3_PIN'}.items()}
    controls=ThreeButtonControls()
    app=None;app_id=None;page='home';selected=0;store_selected=0;detail_selected=0;dirty=True;last_frame=None
    def close_app():
        nonlocal app,app_id
        if app:
            app.close();old_id=app_id;app=None;app_id=None;registry.unload(old_id)
    def open_app(target):
        nonlocal app,app_id,page,dirty
        close_app();app=registry.open(target,ctx);app_id=target;page='app';dirty=True
        print('Opened miniapp: '+target,flush=True)
    def shell_frame():
        nonlocal selected
        if page=='home':
            entries=[a for a in registry.catalog if a['id'] in registry.installed]+[{'id':'store','name':'App Market'}]
            selected%=len(entries)
            im,d=ui.base('Your miniapps',str(len(entries)-1)+' installed · load on open')
            first=max(0,selected-2)
            for i,item in enumerate(entries[first:first+3]):ui.card(d,102+i*34,item['name'],first+i==selected)
            ui.footer(d,'PRESS OPEN  ·  2 APP MARKET')
        elif page=='store':
            im,d=ui.base('App Market','Bundled collection · v0.1')
            first=max(0,store_selected-2)
            for i,item in enumerate(registry.catalog[first:first+3]):
                label=item['name']+('  ✓' if item['id'] in registry.installed else '  +')
                ui.card(d,105+i*33,label,first+i==store_selected)
            ui.footer(d,'PRESS DETAILS  ·  3 HOME')
        else:
            item=registry.catalog[store_selected];installed=item['id'] in registry.installed
            im,d=ui.base(item['name'],item['category']+' · '+item['version'])
            for i,line in enumerate(item['description']):ui.text(d,105+i*23,line,15)
            action=['Open app','Remove app'][detail_selected%2] if installed else 'Install app'
            ui.card(d,181,action,True,item['color'])
            ui.footer(d,'1 OPEN  ·  2 REMOVE  ·  3 HOME' if installed else '1 INSTALL  ·  LEFT BACK')
        return im
    # Resume receipt monitoring only if an unfinished payment makes it necessary.
    state_file=state/'zap-invoices.json'
    if state_file.exists():
        try:
            records=json.loads(state_file.read_text())
            active=[r for r in records.values() if not r.get('paid') and r.get('expires_at',0)>time.time()]
            if active:
                from .zap_backend import start
                ctx.invoice=max(active,key=lambda r:r['created_at'])['invoice'];start(ctx.events)
        except (OSError,ValueError,KeyError) as exc:print('Payment restore:',exc,flush=True)
    request=state/'open-app'
    if (state/'satsbell.sqlite3').exists():
        from .satsbell import get_bell
        get_bell(ctx)
    if request.exists():
        try:
            target=request.read_text().strip()
            if target in registry.installed:open_app(target)
        finally:request.unlink(missing_ok=True)
    last_draw=0
    replay=state/'replay-receipt'
    if replay.exists():
        receipt=replay.read_text().strip();replay.unlink()
        records=json.loads(state_file.read_text())
        for record in records.values():
            if record.get('paid') and record.get('receipt')==receipt:
                print('Replaying previously verified receipt: '+receipt,flush=True)
                ctx.events.put(('paid',record));break
    print('Pocket launcher ready. Miniapps load only on open.',flush=True)
    try:
        while True:
            play_sound=False;transition=False
            while True:
                try:kind,value=ctx.events.get_nowait()
                except queue.Empty:break
                if kind=='invoice':ctx.invoice=value
                if kind in ('satsbell-paid','satsbell-test'):
                    if kind=='satsbell-paid':
                        if 'satsbell' not in registry.installed:registry.install('satsbell')
                        if app_id!='satsbell':open_app('satsbell')
                        app.event(kind,value);dirty=True
                    def bell_sound():
                        from .satsbell import play_sound
                        try:play_sound(ctx.sink)
                        except Exception as exc:
                            print('JBL playback failed:',exc,flush=True)
                            if hasattr(ctx,'satsbell'):ctx.satsbell.error='JBL playback failed; test speaker'
                    threading.Thread(target=bell_sound,daemon=True).start()
                    continue
                if kind=='paid':
                    print('Payment UI received: '+value.get('receipt','unknown'),flush=True)
                    ctx.invoice=None
                    if 'pay21' not in registry.installed:registry.install('pay21')
                    if app_id!='pay21':open_app('pay21')
                    app.event(kind,value);dirty=True;play_sound=True
                elif app_id=='pay21':app.event(kind,value)
                elif kind=='invoice-error':print('Invoice request:',value,flush=True)
            raw={k for k,p in pins.items() if lcd.digital_read(p)}
            ctx.held=raw
            pressed=controls.update(raw,time.monotonic())
            if 'back' in pressed:
                if app and getattr(app,'back',lambda:False)():app.dirty=True
                elif app:close_app();page='home';dirty=True;transition=True
                elif page=='detail':page='store';dirty=True
                else:page='home';dirty=True
            elif app:
                app.handle(pressed)
            elif page=='home':
                entries=[a for a in registry.catalog if a['id'] in registry.installed]+[{'id':'store'}]
                if 'up' in pressed:selected=(selected-1)%len(entries);dirty=True
                if 'down' in pressed:selected=(selected+1)%len(entries);dirty=True
                if 'ok' in pressed:
                    target=entries[selected%len(entries)]['id']
                    if target=='store':page='store';dirty=True
                    else:open_app(target)
                    transition=True
            elif page=='store':
                if 'up' in pressed:store_selected=(store_selected-1)%len(registry.catalog);dirty=True
                if 'down' in pressed:store_selected=(store_selected+1)%len(registry.catalog);dirty=True
                if 'ok' in pressed:page='detail';detail_selected=0;dirty=True;transition=True
            else:
                target=registry.catalog[store_selected]['id']
                if pressed & {'up','down'}:detail_selected=1-detail_selected;dirty=True
                if 'ok' in pressed:
                    if target in registry.installed and detail_selected%2==0:open_app(target)
                    elif target in registry.installed:registry.uninstall(target);detail_selected=0;dirty=True
                    else:registry.install(target);dirty=True
                    transition=True
            now=time.monotonic()
            if app:app.tick(now)
            if dirty or (app and app.dirty and now-last_draw>=.1):
                frame=app.render() if app else shell_frame()
                if transition and last_frame is not None and not play_sound:
                    from PIL import Image
                    for alpha in (.4,.8):lcd.ShowImage(Image.blend(last_frame,frame,alpha).transpose(Image.Transpose.ROTATE_270))
                from PIL import Image
                lcd.ShowImage(frame.transpose(Image.Transpose.ROTATE_270));last_frame=frame
                dirty=False;last_draw=now
                if app:app.dirty=False
            if play_sound:
                from .celebration import celebrate
                print('Paid screen drawn; starting zap celebration.',flush=True)
                threading.Thread(target=celebrate,daemon=True).start()
            time.sleep(.035)
    finally:
        close_app();lcd.module_exit()

if __name__=='__main__':run()
