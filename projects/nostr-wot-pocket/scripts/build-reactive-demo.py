"""Generate an original bass/mid/treble calibration clip, without downloaded music."""
import math,struct,wave
from pathlib import Path
rate=16000;audio=[]
for i in range(rate*7):
    t=i/rate
    if t<.5 or t>6.5:value=0
    else:
        section=int((t-.5)//2);frequency=[100,700,3500][min(section,2)]
        phase=(t-.5)%.5
        envelope=max(0,1-phase/.35)
        value=.5*envelope*math.sin(2*math.pi*frequency*t)
    audio.append(round(32767*value))
path=Path(__file__).resolve().parent.parent/'assets/audio/reactive-demo.wav'
with wave.open(str(path),'wb') as out:
    out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate)
    out.writeframes(struct.pack('<'+'h'*len(audio),*audio))
print(path)

# Six short clicks, one second apart, for audible/visible timing calibration.
clicks=[]
for i in range(rate*8):
    t=i/rate;phase=t%1
    value=.5*math.exp(-phase*100)*math.sin(2*math.pi*1000*t) if 1<=t<7 and phase<.06 else 0
    clicks.append(round(32767*value))
path=path.with_name('reactive-click.wav')
with wave.open(str(path),'wb') as out:
    out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate)
    out.writeframes(struct.pack('<'+'h'*len(clicks),*clicks))
print(path)
