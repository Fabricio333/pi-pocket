"""Headless mini PC runtime for receipt monitoring, audio and BLE lighting."""
import json
import os
from pathlib import Path
import queue
import signal
import threading
import time

TRACKS={'demo':'reactive-demo.wav','thunder':'thunder-natural.wav','zap':'zap-announcement.wav','click':'reactive-click.wav'}

def state_directory():
    return Path(os.environ.get('POCKET_STATE_DIR',str(Path.home()/'.local/share/nostr-wot-pocket-server')))

def write_json(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value));temporary.chmod(0o600);temporary.replace(path)

def export_qr(invoice,directory):
    import qrcode
    path=directory/'current-invoice.png'
    temporary=path.with_suffix('.tmp')
    qrcode.make(invoice.upper(),box_size=6,border=4).save(temporary,format='PNG')
    temporary.chmod(0o600);temporary.replace(path)
    return str(path)

class Server:
    def __init__(self,directory,events,worker,backend,celebrate):
        self.directory=directory;self.events=events;self.worker=worker
        self.backend=backend;self.celebrate=celebrate;self.busy=False
        self.cancel=threading.Event();self.playbacks=[];self.invoice=None
        self.state={'running':True,'pid':os.getpid(),'invoice_busy':False}
        from .settings import DEFAULTS,validate
        defaults=worker.calibration() if worker and hasattr(worker,'calibration') else dict(DEFAULTS)
        path=directory/'calibration.json'
        try:self.settings=validate(json.loads(path.read_text()))
        except (OSError,ValueError,TypeError):self.settings=validate(defaults)
        self.saved_settings=dict(self.settings)
        if worker and hasattr(worker,'configure'):worker.configure(self.settings)
        if not path.exists():write_json(path,self.settings)
        if not (directory/'calibration-baseline.json').exists():write_json(directory/'calibration-baseline.json',self.settings)
    def status(self):
        self.state.update(at=time.time(),invoice_busy=self.busy,calibration=self.settings,saved_calibration=self.saved_settings)
        write_json(self.directory/'server-status.json',self.state)
    def play(self,track):
        if self.cancel.is_set():return
        cancel=threading.Event();self.playbacks.append(cancel)
        def playback():
            try:
                if track=='reactive-click.wav':self.celebrate(cancel=cancel,track=track,reactive=False)
                else:self.celebrate(cancel=cancel,track=track)
            finally:self.playbacks.remove(cancel)
        threading.Thread(target=playback,daemon=True).start()
    def handle(self,command):
        action=command.get('action');value=command.get('value')
        if action in ('live','off','red'):
            if self.worker:self.worker.command({'live':'audio-live','off':'off','red':'steady'}[action])
        elif action in ('settings','preview','restore'):
            from .settings import validate
            settings=validate(json.loads((self.directory/'calibration-baseline.json').read_text()) if action=='restore' else value)
            if self.worker:self.worker.configure(settings)
            self.settings=settings
            if action=='settings':
                write_json(self.directory/'calibration.json',settings);self.saved_settings=dict(settings)
        elif action=='test' and value in TRACKS:
            if value=='click' and self.worker:self.worker.command('audio-live')
            self.play(TRACKS[value])
        elif action=='invoice' and not self.busy:
            self.busy=True;self.state.pop('error',None)
            def create():
                try:self.events.put(('invoice',self.backend.create_invoice(self.events)))
                except Exception as exc:
                    print('Invoice creation failed: '+str(exc),flush=True)
                    self.events.put(('invoice-error',str(exc)))
            threading.Thread(target=create,daemon=True).start()
        else:raise ValueError('Unknown, invalid, or currently busy command')
    def event(self,kind,value):
        if kind=='invoice':
            self.busy=False;self.invoice=value
            self.state.update(invoice_address=self.backend.invoice_address(value),qr=export_qr(value,self.directory))
            self.state.pop('error',None)
            print('Invoice QR ready for '+self.state['invoice_address'],flush=True)
        elif kind=='invoice-error':self.busy=False;self.state['error']=value
        elif kind=='paid':
            # Events reach here only after the backend validates the exact signed receipt.
            self.state['last_receipt']=value['receipt'];self.state['last_payment_at']=time.time()
            if value['invoice']==self.invoice:
                self.invoice=None;self.state.pop('qr',None);self.state.pop('invoice_address',None)
                (self.directory/'current-invoice.png').unlink(missing_ok=True)
            print('Verified payment received; '+('starting celebration.' if self.settings.get('payment_sound',True) else 'payment sound muted.'),flush=True)
            if self.settings.get('payment_sound',True):self.play('zap-announcement.wav')
    def close(self):
        self.cancel.set()
        for cancel in list(self.playbacks):cancel.set()
        if self.worker:self.worker.command('off')
        self.state['running']=False;self.status()

def main():
    directory=state_directory();directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o700)
    os.environ['POCKET_STATE_DIR']=str(directory)
    from . import zap_backend as backend
    from .celebration import prepare,celebrate
    events=queue.Queue();worker=prepare();server=Server(directory,events,worker,backend,celebrate)
    stop=threading.Event()
    for signum in (signal.SIGINT,signal.SIGTERM):signal.signal(signum,lambda *_:stop.set())
    backend.start(events)
    with backend.lock:
        active=[record for record in backend.pending.values() if not record.get('paid') and record.get('expires_at',0)>time.time()]
    if active:server.event('invoice',max(active,key=lambda record:record['created_at'])['invoice'])
    if worker:worker.command('audio-live')
    print('Headless WoT Pocket server ready.',flush=True)
    heartbeat=0
    try:
        while not stop.is_set():
            inboxes=[directory/'server-command.json']+sorted((directory/'commands').glob('*.json'))[:8]
            for inbox in inboxes:
                if not inbox.exists():continue
                try:
                    server.handle(json.loads(inbox.read_text()));server.state.pop('error',None);server.status()
                except (ValueError,OSError) as exc:server.state['error']=str(exc);print('Command:',exc,flush=True)
                finally:inbox.unlink(missing_ok=True)
            try:
                kind,value=events.get(timeout=.2);server.event(kind,value);server.status()
            except queue.Empty:pass
            if time.monotonic()-heartbeat>5:server.status();heartbeat=time.monotonic()
    finally:
        server.close();time.sleep(.4)

if __name__=='__main__':main()
