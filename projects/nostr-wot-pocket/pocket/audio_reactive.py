"""Cached PCM analysis and bounded whole-strip BLE rendering."""
import asyncio
import math
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path
import time
import wave
from . import led_protocol as led

HZ=5

@lru_cache(maxsize=8)
def _analyze(path,mtime,size,hz):
    import numpy as np
    with wave.open(path) as audio:
        if audio.getsampwidth()!=2 or audio.getcomptype()!='NONE':
            raise ValueError('Audio reactive playback requires uncompressed 16-bit PCM WAV')
        rate=audio.getframerate();channels=audio.getnchannels()
        samples=np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').astype(np.float32)
    samples=samples.reshape(-1,channels).mean(axis=1)/32768
    hop=max(1,round(rate/hz));window=max(hop,round(rate*.08))
    frequencies=np.fft.rfftfreq(window,1/rate)
    masks=[(frequencies>=low)&(frequencies<high) for low,high in [(40,250),(250,2000),(2000,rate/2+1)]]
    rows=[]
    for start in range(0,len(samples),hop):
        chunk=samples[start:start+window]
        rms=float(np.sqrt(np.mean(chunk*chunk)))
        padded=np.zeros(window);padded[:len(chunk)]=chunk
        spectrum=abs(np.fft.rfft(padded*np.hanning(window)))**2
        bands=[float(spectrum[mask].sum()) for mask in masks]
        rows.append((start/rate,rms,bands))
    reference=max(.02,float(np.percentile([r[1] for r in rows],95))) if rows else .02
    envelope=0.;previous=0.;last_onset=-1.;frames=[]
    for at,rms,bands in rows:
        target=0. if rms<.003 else min(1.,rms/reference)
        envelope+=(target-envelope)*(.85 if target>envelope else .35)
        if target==0 and envelope<.03:envelope=0.
        total=sum(bands)
        bass,mid,treble=[value/total if total else 0. for value in bands]
        onset=target>.25 and target-previous>.22 and at-last_onset>.25
        if onset:last_onset=at
        # Warm bass, purple mids, cool treble; silence remains dark.
        hue=30 if bass>=max(mid,treble) else (280 if mid>=treble else 190)
        saturation=250 if onset and treble>.3 else 1000
        frames.append((at,float(envelope),hue,saturation,bool(onset)))
        previous=target
    return tuple(frames),len(samples)/rate

def analyze(path,hz=HZ):
    path=Path(path).resolve();stat=path.stat()
    if not 1<=hz<=20:raise ValueError('Feature rate must be 1..20 Hz')
    return _analyze(str(path),stat.st_mtime_ns,stat.st_size,hz)

async def render(client,frames,start,delay,level,cancel,clock=time.monotonic,sleep=asyncio.sleep):
    """Latest frame wins: late BLE writes never replay an animation backlog."""
    if not 3<=level<=1000 or not -.5<=delay<=1.:raise ValueError('Invalid reactive settings')
    times=[f[0] for f in frames];index=0;late=0
    renderer=LiveRenderer(client,level,sleep=sleep,cancel=cancel)
    try:
        while index<len(frames) and not cancel.is_set():
            remaining=start+delay+frames[index][0]-clock()
            if remaining>0:
                await sleep(min(.025,remaining));continue
            newest=max(index,bisect_right(times,clock()-start-delay)-1)
            late+=newest-index;index=newest
            await renderer.apply(frames[index]);index+=1
        return {'writes':renderer.writes,'dropped_frames':late}
    finally:
        await client.write_gatt_char(led.TX,led.power(False),response=True)

class LiveFeatures:
    """Bounded gain, attack/release and frequency palette for 50 ms PCM frames."""
    def __init__(self,rate=16000):
        self.rate=rate;self.reference=.1;self.envelope=0.;self.previous=0.;self.last_onset=-1.;self.bass_reference=.01;self.previous_bass=0.
    def update(self,pcm,at):
        import numpy as np
        samples=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
        rms=float(np.sqrt(np.mean(samples*samples)))
        self.reference=max(.02,self.reference*.995,rms)
        target=0. if rms<.003 else min(1.,rms/self.reference)
        self.envelope+=(target-self.envelope)*(.85 if target>self.envelope else .35)
        if target==0 and self.envelope<.03:self.envelope=0.
        spectrum=abs(np.fft.rfft(samples*np.hanning(len(samples))))**2
        f=np.fft.rfftfreq(len(samples),1/self.rate)
        bands=[float(spectrum[(f>=lo)&(f<hi)].sum()) for lo,hi in [(40,250),(250,2000),(2000,8001)]]
        dominant=max(range(3),key=lambda i:bands[i])
        bass=math.sqrt(bands[0])/len(samples)
        self.bass_reference=max(.005,self.bass_reference*.995,bass)
        bass_target=bass/self.bass_reference
        onset=target>.08 and (bass_target-self.previous_bass>.18 or target-self.previous>.22) and at-self.last_onset>.18
        if onset:self.last_onset=at
        self.previous=target;self.previous_bass=bass_target
        return (at,float(self.envelope),(30,280,190)[dominant],1000,bool(onset))

class LiveRenderer:
    def __init__(self,client,level,sleep=asyncio.sleep,cancel=None):
        self.client=client;self.level=level;self.previous=None;self.writes=0
        self.sleep=sleep;self.cancel=cancel
    async def apply(self,frame):
        _,energy,hue,saturation,_=frame
        on=energy>=.03
        # The strip was visible at a fixed 10%; sub-percent reactive values were not.
        brightness=max(3,min(self.level,round(self.level*(.4+.6*max(0.,min(1.,energy))**.5))))
        state=(on,hue,saturation,brightness);previous=self.previous;packets=[]
        if on:
            waking=previous is None or not previous[0]
            if waking or state[1:3]!=previous[1:3]:packets.append(led.color(hue,saturation))
            if waking or brightness!=previous[3]:packets.append(led.brightness(brightness))
            if waking:packets.append(led.power(True))
        elif previous is None or previous[0]:packets.append(led.power(False))
        for packet in packets:
            if self.cancel and self.cancel.is_set():return
            await self.client.write_gatt_char(led.TX,packet,response=True);self.writes+=1
            await self.sleep(.035)
        self.previous=state

class MusicRenderer:
    """Multicolor controller motion with beat-pulsed intensity, without per-pixel claims."""
    def __init__(self,client,level,sleep=asyncio.sleep,cancel=None,effect='auto',beats_per_color=4):
        self.client=client;self.level=level;self.sleep=sleep;self.cancel=cancel
        self.previous=None;self.writes=0;self.kick=0.;self.last_at=None
        self.last_signal=-10.;self.beats=0;self.last_effect_at=-10.;self.effect_index=0
        self.effect=None;self.beats_per_color=beats_per_color;self.effect_start_beats=0
        self.configure_effect(effect,beats_per_color)
    def configure_effect(self,effect,beats_per_color):
        if effect==self.effect and beats_per_color==self.beats_per_color:return
        if effect=='auto':effects=('rainbow-tail','rainbow-flow','rainbow-running')
        elif effect=='beat-tail':effects=('red-tailing','yellow-tailing','green-tailing','cyan-tailing','blue-tailing','purple-tailing')
        elif effect=='beat-running':effects=('red-running','yellow-running','green-running','cyan-running','blue-running','purple-running')
        elif effect=='beat-build':effects=('build-red','build-orange','build-yellow','build-green','build-cyan','build-blue','build-purple')
        elif effect in ('rainbow-tail','rainbow-flow','rainbow-running','rainbow-gradient','rainbow-brush',
                        'colorful-energy','rainbow-breathe','blue-purple-flow','warm-cool-flow'):effects=(effect,)
        else:raise ValueError('Unknown music effect')
        self.effects=effects;self.effect=effect;self.beats_per_color=beats_per_color
        self.effect_index=0;self.effect_start_beats=self.beats;self.previous=None
    async def apply(self,frame):
        at,energy,_,_,onset=frame
        dt=max(0,at-self.last_at) if self.last_at is not None else .05
        self.last_at=at;self.kick*=math.exp(-dt/.16)
        if energy>=.03:self.last_signal=at
        if onset:self.kick=1.;self.beats+=1
        # Brief silence dims immediately, preserving the running preset between beats.
        on=energy>=.03 or (self.previous is not None and self.previous[0] and at-self.last_signal<1.)
        intensity=min(1.,.12+.43*min(1.,max(0.,energy))**1.3+.5*self.kick)
        brightness=max(3,min(self.level,round(self.level*intensity))) if energy>=.03 else 3
        previous=self.previous;packets=[]
        if on:
            waking=previous is None or not previous[0]
            if self.effect=='beat-build':
                relative=max(0,self.beats-self.effect_start_beats-1)
                index=relative//self.beats_per_color%len(self.effects)
                progress=(relative%self.beats_per_color+1)/self.beats_per_color
                brightness=max(3,min(self.level,round(brightness*progress)))
                if waking or index!=self.effect_index:
                    self.effect_index=index;packets=[led.color((0,30,60,120,190,240,280)[index],1000)]
            elif waking:
                packets=[led.effect(self.effects[self.effect_index]),led.direction(True)]
                self.last_effect_at=at
            elif self.effect in ('beat-tail','beat-running') and onset:
                index=max(0,self.beats-self.effect_start_beats-1)//self.beats_per_color%len(self.effects)
                if index!=self.effect_index:
                    self.effect_index=index;packets=[led.effect(self.effects[index])]
            elif self.effect=='auto' and onset and self.beats%16==0 and at-self.last_effect_at>=8:
                self.effect_index=(self.effect_index+1)%len(self.effects)
                packets=[led.effect(self.effects[self.effect_index])];self.last_effect_at=at
            if waking or brightness!=previous[1]:packets.append(led.brightness(brightness))
            if waking:packets.append(led.power(True))
        elif previous is None or previous[0]:packets=[led.power(False)]
        for packet in packets:
            if self.cancel and self.cancel.is_set():return
            await self.client.write_gatt_char(led.TX,packet,response=True);self.writes+=1
            await self.sleep(.035)
        self.previous=(on,brightness)

async def monitor(client,sink,level,delay,cancel,stop_path=None,controls=None,on_metrics=None):
    """Analyze the speaker monitor locally; no recording file, network service or microphone."""
    from collections import deque
    import os
    env=os.environ.copy();env.setdefault('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}')
    process=await asyncio.create_subprocess_exec('parec','--raw','--format=s16le','--rate=16000',
        '--channels=1','--latency-msec=30','--device='+sink+'.monitor',
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=env,limit=6400)
    frames=deque(maxlen=20);features=LiveFeatures();renderer=MusicRenderer(client,level,cancel=cancel)
    async def read():
        while not cancel.is_set():
            pcm=await process.stdout.readexactly(1600)
            frames.append(features.update(pcm,time.monotonic()))
    reader=asyncio.create_task(read());last_audio=time.monotonic();began=last_audio;count=0;peak=0.;next_frame=0.;delivery_total=0.;delivery_max=0.;telemetry_at=0.;last_level=0.;last_delivery=0.
    try:
        while not cancel.is_set():
            if stop_path and stop_path.exists():break
            if reader.done():
                try:reader.result()
                except asyncio.IncompleteReadError:print('Audio monitor closed; waiting for speaker.',flush=True)
                break
            now=time.monotonic();latest=None
            if controls:
                settings=controls();renderer.level=settings['brightness'];delay=settings['delay_ms']/1000
                renderer.configure_effect(settings['effect'],settings['beats_per_color'])
            if now>=next_frame:
                while frames and frames[0][0]+delay<=now:latest=frames.popleft()
            if latest:
                await renderer.apply(latest)
                delivery=max(0.,(time.monotonic()-latest[0])*1000)
                delivery_total+=delivery;delivery_max=max(delivery_max,delivery);last_level=latest[1];last_delivery=delivery
                last_audio=now;next_frame=now+.1;count+=1;peak=max(peak,latest[1])
            elif now-last_audio>.5 and renderer.previous and renderer.previous[0]:
                await renderer.apply((now,0,30,1000,False))
            if on_metrics and now-telemetry_at>=.5:
                on_metrics({'audio_level':last_level,'beats':renderer.beats,
                            'response_ms':round(last_delivery),'active_effect':renderer.effects[renderer.effect_index]})
                telemetry_at=now
            if now-began>=10:
                print('Live audio reactive: frames='+str(count)+' peak='+str(round(peak,3))+' writes='+str(renderer.writes)+' capture_to_write_ms='+str(round(delivery_total/max(1,count)))+' max_ms='+str(round(delivery_max)),flush=True)
                began=now;count=0;peak=0.;delivery_total=0.;delivery_max=0.
            await asyncio.sleep(.01)
    finally:
        reader.cancel()
        await asyncio.gather(reader,return_exceptions=True)
        if process.returncode is None:
            try:process.terminate()
            except ProcessLookupError:pass
            try:await asyncio.wait_for(process.wait(),2)
            except asyncio.TimeoutError:process.kill();await process.wait()
        await client.write_gatt_char(led.TX,led.power(False),response=True)
