"""Shared, asynchronous PulseAudio volume and BlueZ speaker selection."""
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from .ringtones import state_directory,stop_preview

MAC=re.compile(r'^[0-9A-F]{2}(?::[0-9A-F]{2}){5}$')
A2DP_SINK='0000110b-0000-1000-8000-00805f9b34fb'

class Speaker:
    def __init__(self,context=None,directory=None):
        self.ctx=context;self.path=(Path(directory) if directory else state_directory())/'speaker.json'
        try:saved=json.loads(self.path.read_text())
        except (OSError,ValueError):saved={}
        self.has_saved=bool(saved)
        self.sink=saved.get('sink') or os.environ.get('POCKET_AUDIO_SINK','@DEFAULT_SINK@')
        self.address=saved.get('address','')
        if not self.address and self.sink.startswith('bluez_sink.'):
            self.address=self.sink.split('.')[1].replace('_',':')
        self.name=saved.get('name','Bluetooth speaker')
        self.volume=max(0,min(100,int(saved.get('volume',100))))
        self.muted=bool(saved.get('muted',False));self.connected=False
        self.devices=[];self.busy=False;self.message='Checking speaker';self.error=''
        self.jobs=queue.Queue();self.lock=threading.RLock();self.thread=None;self.apply_pending=False
        self.pending=set()

    def command(self,args,timeout=8,check=True):
        env=os.environ.copy();env.setdefault('XDG_RUNTIME_DIR','/run/user/1000')
        return subprocess.run(args,env=env,capture_output=True,text=True,timeout=timeout,check=check).stdout.strip()

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps({k:getattr(self,k) for k in ('sink','address','name','volume','muted')}))
            temp.chmod(0o600);temp.replace(self.path)
            self.has_saved=True

    def route(self):
        if self.ctx is not None:self.ctx.sink=self.sink
        os.environ['POCKET_AUDIO_SINK']=self.sink
        if self.address:os.environ['POCKET_SPEAKER_ADDRESS']=self.address

    def start(self):
        self.route()
        self.thread=threading.Thread(target=self.worker,daemon=True);self.thread.start()
        self.jobs.put(('reconnect',None))

    def enqueue(self,action,value=None):
        if action=='apply':
            with self.lock:
                if self.apply_pending:return False
                self.apply_pending=True
        else:
            with self.lock:
                if action=='refresh' and self.busy:return False
                if action in self.pending:return False
                self.pending.add(action)
        self.jobs.put((action,value))
        return True

    def set_volume(self,value):
        with self.lock:self.volume=max(0,min(100,int(value)))
        self.save();self.enqueue('apply')

    def set_mute(self,value):
        self.muted=bool(value);self.save();self.enqueue('apply')

    def apply(self):
        self.command(['pactl','set-sink-volume',self.sink,str(self.volume)+'%'])
        self.command(['pactl','set-sink-mute',self.sink,'1' if self.muted else '0'])

    def refresh(self):
        volume=self.command(['pactl','get-sink-volume',self.sink])
        mute=self.command(['pactl','get-sink-mute',self.sink])
        match=re.search(r'(\d+)%',volume)
        with self.lock:
            if self.apply_pending:return
            previous=(self.volume,self.muted)
            if match:self.volume=max(0,min(100,int(match.group(1))))
            self.muted=mute.endswith('yes')
            if not self.has_saved or previous!=(self.volume,self.muted):self.save()
        self.connected=True
        self.message='Connected';self.error=''

    def find_sink(self,address):
        marker=address.replace(':','_').lower()
        for line in self.command(['pactl','list','short','sinks']).splitlines():
            fields=line.split()
            if len(fields)>1 and marker in fields[1].lower():return fields[1]
        return None

    def reconnect(self):
        # An existing audio output already carries the hardware button level.
        # Reconnecting/reselecting its profile can reset AVRCP volume on speakers.
        try:self.refresh()
        except Exception:
            if self.address:self.connect(self.address,None if self.name=='Bluetooth speaker' else self.name)
            else:self.apply();self.refresh()
            return
        if self.name=='Bluetooth speaker' and self.address:
            try:
                info=self.command(['bluetoothctl','info',self.address])
                name=re.search(r'\bName: (.+)',info)
                if name:self.name=name.group(1)
            except Exception:pass
        if self.sink!='@DEFAULT_SINK@':self.command(['pactl','set-default-sink',self.sink])
        self.route();self.save()

    def scan(self):
        self.message='Searching for speakers...'
        self.command(['bluetoothctl','power','on'])
        self.command(['bluetoothctl','--timeout','8','scan','on'],timeout=12,check=False)
        devices=[]
        for line in self.command(['bluetoothctl','devices']).splitlines()[:30]:
            match=re.match(r'Device ([0-9A-F:]{17}) (.+)',line)
            if not match:continue
            address,name=match.groups()
            info=self.command(['bluetoothctl','info',address])
            if 'Audio Sink' in info or any(icon in info for icon in ('audio-card','audio-headset','audio-headphones')):
                devices.append({'address':address,'name':name,'connected':'Connected: yes' in info})
        self.devices=devices
        self.message=str(len(devices))+' speakers found'

    def connect(self,address,name=None):
        address=address.upper()
        if not MAC.fullmatch(address):raise ValueError('Invalid Bluetooth address')
        started=time.monotonic()
        stop_preview();self.message='Checking speaker...'
        print('Speaker connection requested: '+(name or address),flush=True)
        info=self.command(['bluetoothctl','info',address])
        sink=self.find_sink(address) if 'Connected: yes' in info else None
        if 'Paired: yes' not in info:
            self.message='Pairing speaker...'
            self.command(['bluetoothctl','--agent','NoInputNoOutput','--timeout','25','pair',address],timeout=30)
        self.command(['bluetoothctl','trust',address])
        if not sink:
            self.message='Connecting audio...'
            self.command(['bluetoothctl','--timeout','15','connect',address,A2DP_SINK],timeout=20)
            sink=self.find_sink(address)
            if not sink:
                self.message='Preparing audio output...'
                self.command(['pactl','set-card-profile','bluez_card.'+address.replace(':','_'),'a2dp_sink'],check=False)
                for _ in range(30):
                    sink=self.find_sink(address)
                    if sink:break
                    time.sleep(.2)
        if not sink:raise RuntimeError('Audio output not ready; retry connect')
        self.message='Switching audio output...'
        self.command(['pactl','set-default-sink',sink])
        old=self.address
        self.sink=sink;self.address=address
        names=re.search(r'\bName: (.+)',info)
        self.name=name or (names.group(1) if names else 'Bluetooth speaker')
        self.apply();self.route();self.save()
        for line in self.command(['pactl','list','short','sink-inputs']).splitlines():
            ident=line.split()[0]
            if ident.isdigit():self.command(['pactl','move-sink-input',ident,sink],check=False)
        if old and old!=address:self.command(['bluetoothctl','disconnect',old],check=False)
        self.connected=True;self.message='Connected';self.error=''
        print('Speaker connected: '+self.name+' in '+str(round(time.monotonic()-started,1))+' s',flush=True)

    def worker(self):
        while True:
            queued=True
            try:action,value=self.jobs.get(timeout=2)
            except queue.Empty:action,value='refresh',None;queued=False
            self.busy=True
            if action=='apply':
                with self.lock:self.apply_pending=False
            try:
                if action=='scan':self.scan()
                elif action=='connect':self.connect(value['address'],value['name'])
                elif action=='reconnect':
                    self.reconnect()
                elif action=='apply':self.apply();self.message='Connected';self.error=''
                elif action=='refresh':self.refresh()
            except Exception as exc:
                self.error='Pairing failed: use pairing mode' if action=='connect' else 'Speaker unavailable; reconnect'
                self.message='Not connected';self.connected=False
                print('Speaker settings:',action,str(exc)[:100],flush=True)
            finally:
                self.busy=False
                with self.lock:self.pending.discard(action)
                if queued:self.jobs.task_done()

def get_speaker(context):
    if not hasattr(context,'speaker'):
        context.speaker=Speaker(context);context.speaker.start()
    return context.speaker
