"""Three-button LED control panel and free celebration preview."""
import threading
from ..ui import ACCENT,MUTED

OPTIONS=[('audio-live','React to audio'),('reactive-thunder','Reactive thunder TEST'),('reactive-demo','Bass/treble TEST'),('delay','Audio/light delay'),('steady','Steady red'),('white-wipe','White wipe'),('red-running','Red chase'),
         ('yellow-running','Yellow chase'),('red-tailing','Red tail'),('preview','Zap + sound TEST'),
         ('brightness','Brightness'),('off','Lights off')]
class App:
    def __init__(self,context):
        from ..celebration import prepare
        self.ctx=context;self.worker=prepare();self.selected=0;self.page='menu';self.dirty=True
        self.level=self.worker.level if self.worker else 100;self.previewing=False
        self.cancel=threading.Event();self.last_status=None
    def handle(self,keys):
        if self.page=='delay':
            if 'up' in keys:self.delay=max(-500,self.delay-25);self.dirty=True
            if 'down' in keys:self.delay=min(1000,self.delay+25);self.dirty=True
            if 'ok' in keys:
                if self.worker:self.worker.command('delay',self.delay/1000)
                self.page='menu';self.dirty=True
            return
        if self.page=='brightness':
            if 'up' in keys:self.level=max(10,self.level-10);self.dirty=True
            if 'down' in keys:self.level=min(1000,self.level+10);self.dirty=True
            if 'ok' in keys:
                if self.worker:self.worker.command('brightness',self.level)
                self.page='menu';self.dirty=True
            return
        if 'up' in keys:self.selected=(self.selected-1)%len(OPTIONS);self.dirty=True
        if 'down' in keys:self.selected=(self.selected+1)%len(OPTIONS);self.dirty=True
        if 'ok' not in keys:return
        action=OPTIONS[self.selected][0];self.cancel.set()
        if action=='delay':self.delay=round(self.worker.reactive_delay*1000) if self.worker else 150;self.page='delay'
        elif action=='brightness':self.page='brightness'
        elif action in ('preview','reactive-thunder','reactive-demo'):
            if self.previewing:return
            self.cancel=threading.Event();cancel=self.cancel;self.previewing=True
            def preview():
                try:
                    from ..celebration import celebrate
                    if self.worker:self.worker.ready.wait(timeout=10)
                    if not cancel.is_set():celebrate(cancel,track={'reactive-thunder':'thunder-natural.wav','reactive-demo':'reactive-demo.wav'}.get(action,'zap-announcement.wav'))
                finally:self.previewing=False;self.dirty=True
            threading.Thread(target=preview,daemon=True).start()
        elif self.worker:
            if action in ['steady','off','audio-live']:self.worker.command(action)
            else:self.worker.command('effect',action)
        self.dirty=True
    def back(self):
        if self.page in ('brightness','delay'):self.page='menu';self.dirty=True;return True
        return False
    def tick(self,now):
        status=(bool(self.worker and self.worker.ready.is_set()),self.worker.mode if self.worker else '',self.previewing)
        if status!=self.last_status:self.last_status=status;self.dirty=True
    def render(self):
        u=self.ctx.ui
        if self.page=='delay':
            im,d=u.base('Audio/light delay','Top −  ·  middle +  ·  bottom apply')
            u.text(d,111,f'{self.delay:+d} ms',36,ACCENT,True)
            u.text(d,178,'Positive: lights arrive later',12,MUTED)
        elif self.page=='brightness':
            im,d=u.base('Brightness','Top −  ·  middle +  ·  bottom apply')
            u.text(d,111,f'{self.level/10:g}%',49,ACCENT,True)
            u.text(d,178,'Setting, not measured power',12,MUTED)
        else:
            connected=bool(self.worker and self.worker.ready.is_set())
            subtitle='TEST preview · no payment' if self.previewing else ('BLE connected' if connected else 'Connecting to LEDs…')
            if not self.worker:subtitle='LED address not configured'
            im,d=u.base('LED Controls',subtitle)
            first=max(0,self.selected-2)
            for row,(_,label) in enumerate(OPTIONS[first:first+3]):u.card(d,101+row*32,label,first+row==self.selected)
            u.text(d,204,'Current: '+(self.worker.mode if self.worker else 'unavailable'),11,MUTED)
        u.footer(d);return im
    def close(self):
        self.cancel.set()
        if self.worker:self.worker.command('off')
