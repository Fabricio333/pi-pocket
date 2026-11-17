"""Preconnected BLE lighting plus cached audio, triggered after the paid screen draws."""
import asyncio, json, os, queue, subprocess, threading, time
from pathlib import Path
from . import led_protocol as led

ROOT=Path(__file__).resolve().parent.parent
_lock=threading.Lock();_worker=None;_audio_started=False
class PreviewCancelled(Exception):pass

async def steady_red(client,level=100):
    for data in [led.color(),led.brightness(level),led.power(True)]:
        await client.write_gatt_char(led.TX,data,response=False)
        await asyncio.sleep(.025)

async def light_pattern(client,level=100,sleep=asyncio.sleep,cancel=None):
    """Known spatial effects and whole-strip colors; no invented half-strip command."""
    async def write(data):
        if cancel and cancel.is_set():raise PreviewCancelled()
        await client.write_gatt_char(led.TX,data,response=False)
    try:
        await write(led.brightness(level));await write(led.power(True))
        await write(led.color(0,0));await write(led.brightness(1000));await sleep(.6)
        await write(led.brightness(level))
        for name,forward,duration in [('yellow-running',True,.6),('red-running',False,.6)]:
            await write(led.effect(name));await write(led.direction(forward))
            await write(led.brightness(level));await sleep(duration)
        # Orange / yellow / white are real color packets, not claimed custom segments.
        for _ in range(3):
            for hue,saturation in [(30,1000),(60,1000),(0,0),(30,1000),(300,1000),(180,1000),(60,1000),(0,0)]:
                await write(led.color(hue,saturation));await sleep(.1)
    finally:
        for data in [led.brightness(level),led.power(False)]:
            await client.write_gatt_char(led.TX,data,response=False);await sleep(.025)

async def half_strip_probe(client,level=100,sleep=asyncio.sleep,cancel=None):
    """Experimental prefix overwrite. It is not advertised as supported segmentation."""
    async def write(data):
        if cancel and cancel.is_set():raise PreviewCancelled()
        await client.write_gatt_char(led.TX,data,response=False);await sleep(.05)
    try:
        for data in [led.brightness(level),led.power(True),led.count_probe(300),led.color(30,1000)]:await write(data)
        await sleep(1)
        for data in [led.count_probe(150),led.color(60,1000)]:await write(data)
        print('Half-strip probe: look for yellow first half and orange second half.',flush=True)
        for _ in range(80):
            if cancel and cancel.is_set():raise PreviewCancelled()
            await sleep(.1)
    finally:
        for data in [led.count_probe(8),led.brightness(level),led.power(False)]:
            await client.write_gatt_char(led.TX,data,response=False);await sleep(.025)

class LedWorker:
    def __init__(self,address,level=100):
        self.address=address;self.level=level;self.jobs=queue.SimpleQueue();self.ready=threading.Event()
        self.active_cancel=None;self.mode='steady';self.generation=0;self.live_enabled=False;self.music_effect='auto';self.beats_per_color=4
        self.reactive_delay=max(-.5,min(1.,float(os.environ.get('POCKET_AUDIO_LED_DELAY_MS','150'))/1000))
        state=Path(os.environ.get('POCKET_STATE_DIR',str(Path.home()/'.local/share/nostr-wot-pocket')))
        state.mkdir(parents=True,exist_ok=True);self.status_path=state/'led-status.json'
    def status(self,connected,**extra):
        value={'connected':connected,'at':time.time(),'mode':self.mode,'brightness':self.level,'delay_ms':round(self.reactive_delay*1000),
               'effect':self.music_effect,'beats_per_color':self.beats_per_color,**extra}
        temp=self.status_path.with_suffix('.tmp');temp.write_text(json.dumps(value));temp.replace(self.status_path)
    def calibration(self):
        return {'brightness':self.level,'delay_ms':round(self.reactive_delay*1000),
                'effect':self.music_effect,'beats_per_color':self.beats_per_color}
    def configure(self,settings):
        from .settings import validate
        value=validate(settings)
        self.level=value['brightness'];self.reactive_delay=value['delay_ms']/1000
        self.music_effect=value['effect'];self.beats_per_color=value['beats_per_color']
    def request(self,cancel=None):
        print('LED celebration queued; connected='+str(self.ready.is_set()),flush=True)
        self.jobs.put({'action':'celebrate','cancel':cancel,'at':time.monotonic()})
    def command(self,action,value=None):
        if action in ('off','steady','effect'):self.live_enabled=False
        if self.active_cancel:self.active_cancel.set()
        self.generation+=1
        self.jobs.put({'action':action,'value':value,'at':time.monotonic(),'generation':self.generation})
    def reactive(self,frames,start,duration,cancel):
        if self.active_cancel:self.active_cancel.set()
        self.generation+=1
        self.jobs.put({'action':'reactive','frames':frames,'start':start,'duration':duration,
                       'cancel':cancel,'at':time.monotonic(),'generation':self.generation})
    def start(self):threading.Thread(target=lambda:asyncio.run(self.run()),daemon=True).start()
    async def run(self):
        from bleak import BleakScanner,BleakClient
        while True:
            self.ready.clear();self.status(False)
            try:
                # BlueZ can retain this known LED link after a client process dies,
                # hiding its advertisements from a new Bleak scanner. Recycle only
                # this device, never the shared radio or the classic audio link.
                await asyncio.to_thread(subprocess.run,['bluetoothctl','--timeout','4','disconnect',self.address],
                                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=6)
                device=await BleakScanner.find_device_by_address(self.address,timeout=15)
                if not device:await asyncio.sleep(5);continue
                async with BleakClient(device,timeout=20,disconnected_callback=lambda client:self.ready.clear()) as client:
                    self.mode='off'
                    await client.write_gatt_char(led.TX,led.power(False),response=False)
                    self.ready.set();self.status(True)
                    print('LED controller connected; celebration ready.',flush=True)
                    while client.is_connected:
                        try:job=await asyncio.to_thread(self.jobs.get,True,1)
                        except queue.Empty:
                            inbox=self.status_path.parent/'led-command.json'
                            if inbox.exists():
                                try:job=json.loads(inbox.read_text());job['at']=time.monotonic()
                                finally:inbox.unlink(missing_ok=True)
                            elif self.live_enabled:job={'action':'audio-live','at':time.monotonic()}
                            else:continue
                        if time.monotonic()-job['at']>15:continue
                        if job.get('generation',self.generation)!=self.generation:continue
                        action=job['action'];value=job.get('value')
                        if action=='audio-live':
                            from .audio_reactive import monitor
                            self.live_enabled=True;self.mode='audio-live';self.active_cancel=threading.Event()
                            self.status(True,celebrating=False)
                            print('Live audio reactive monitoring started.',flush=True)
                            try:
                                await monitor(client,os.environ.get('POCKET_AUDIO_SINK','@DEFAULT_SINK@'),
                                              self.level,self.reactive_delay,self.active_cancel,self.status_path.parent/'led-command.json',
                                              controls=self.calibration,on_metrics=lambda metrics:self.status(True,celebrating=False,**metrics))
                            finally:self.active_cancel=None;self.mode='off'
                        elif action=='audio-test' and value in ('reactive-demo.wav','thunder-natural.wav','zap-announcement.wav'):
                            threading.Thread(target=celebrate,kwargs={'track':value},daemon=True).start()
                        elif action=='reactive':
                            from .audio_reactive import render
                            cancel=job['cancel']
                            if cancel.is_set() or time.monotonic()>job['start']+job['duration']+self.reactive_delay:continue
                            self.active_cancel=cancel;self.mode='audio-reactive';self.status(True,celebrating=True)
                            print('Audio reactive lights started.',flush=True)
                            try:
                                stats=await render(client,job['frames'],job['start'],self.reactive_delay,self.level,cancel)
                                print('Audio reactive lights finished: '+json.dumps(stats),flush=True)
                            finally:self.active_cancel=None;self.mode='off'
                        elif action=='delay':
                            if isinstance(value,(int,float)) and -.5<=value<=1.:self.reactive_delay=value
                        elif action=='celebrate':
                            print('LED celebration started.',flush=True)
                            self.active_cancel=job.get('cancel') or threading.Event()
                            self.status(True,celebrating=True)
                            try:await light_pattern(client,self.level,cancel=self.active_cancel)
                            except PreviewCancelled:pass
                            finally:
                                self.active_cancel=None;self.mode='off'
                                print('LED celebration finished; lights off.',flush=True)
                        elif action=='probe-halves':
                            self.active_cancel=threading.Event();self.mode='halves-probe';self.status(True,celebrating=False)
                            try:await half_strip_probe(client,self.level,cancel=self.active_cancel)
                            except PreviewCancelled:pass
                            finally:self.active_cancel=None;self.mode='off'
                        elif action=='brightness':
                            if not isinstance(value,int) or not 3<=value<=1000:continue
                            self.level=value
                            await client.write_gatt_char(led.TX,led.brightness(value),response=False)
                        elif action=='effect' and value in led.EFFECTS:
                            self.live_enabled=False;self.mode=value
                            for data in [led.power(True),led.effect(value),led.direction(True),led.brightness(self.level)]:
                                await client.write_gatt_char(led.TX,data,response=False);await asyncio.sleep(.025)
                        elif action=='steady':self.live_enabled=False;self.mode='steady';await steady_red(client,self.level)
                        elif action=='off':
                            self.live_enabled=False;self.mode='off';await client.write_gatt_char(led.TX,led.power(False),response=False)
                        self.status(True,celebrating=False)
            except Exception as exc:
                self.status(False,error=str(exc)[:150]);print('LED reconnect:',str(exc)[:150],flush=True)
            finally:self.ready.clear()
            await asyncio.sleep(3)

def _maintain_audio():
    env=os.environ.copy();env.setdefault('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}')
    address=os.environ.get('POCKET_SPEAKER_ADDRESS');sink=os.environ.get('POCKET_AUDIO_SINK','@DEFAULT_SINK@')
    while True:
        try:
            check=subprocess.run(['pactl','get-sink-volume',sink],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
            if check.returncode and address:
                subprocess.run(['bluetoothctl','--timeout','6','connect',address],env=env,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8)
        except Exception as exc:print('Speaker reconnect:',str(exc)[:100],flush=True)
        time.sleep(15)

def prepare():
    global _worker,_audio_started
    with _lock:
        address=os.environ.get('POCKET_LED_ADDRESS')
        if address and _worker is None:
            level=int(os.environ.get('POCKET_LED_BRIGHTNESS','100'))
            if not 3<=level<=100:raise ValueError('Celebration brightness must be 3..100 per mille')
            _worker=LedWorker(address,level);_worker.start()
        if os.environ.get('POCKET_SPEAKER_ADDRESS') and not _audio_started:
            _audio_started=True;threading.Thread(target=_maintain_audio,daemon=True).start()
    return _worker

def celebrate(cancel=None,track='zap-announcement.wav',reactive=True):
    """Play cached audio and its analyzed lighting timeline from one monotonic origin."""
    from .audio_reactive import analyze
    if track not in ('zap-announcement.wav','thunder-natural.wav','reactive-demo.wav','reactive-click.wav'):
        raise ValueError('Unknown reactive track')
    cancel=cancel or threading.Event()
    path=ROOT/'assets/audio'/track
    frames,duration=analyze(path)
    worker=prepare()
    if worker:worker.ready.wait(timeout=5)
    if cancel.is_set():return
    env=os.environ.copy();env.setdefault('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}')
    sink=os.environ.get('POCKET_AUDIO_SINK','@DEFAULT_SINK@');player=None
    try:
        start=time.monotonic()
        player=subprocess.Popen(['paplay','--device='+sink,str(path)],env=env)
        if reactive and worker and worker.ready.is_set():worker.reactive(frames,start,duration,cancel)
        end=start+duration+5
        while player.poll() is None and not cancel.is_set() and time.monotonic()<end:time.sleep(.025)
        if player.poll() is None:player.terminate()
        player.wait(timeout=2)
        if player.returncode and not cancel.is_set():
            print('Announcement playback exited: '+str(player.returncode),flush=True)
    except Exception as exc:print('Announcement playback:',str(exc)[:150],flush=True)
    finally:
        cancel.set()
        if player and player.poll() is None:
            player.kill();player.wait(timeout=2)
