#!/usr/bin/env python3
"""Download source MP3s and prepare evenly leveled, short offline doorbell clips."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
import wave

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path.home()/'.local/share/nostr-wot-pocket/ringtones')
    args=parser.parse_args()
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise SystemExit('Install ffmpeg to prepare the clips; playback does not need it.')
    directory=args.directory;directory.mkdir(parents=True,exist_ok=True)
    originals=directory/'originals';originals.mkdir(exist_ok=True)
    catalog=json.loads((ROOT/'assets/audio/ringtones.json').read_text())
    def prepare(track):
        filename=track['file']
        if Path(filename).name!=filename or not filename.endswith('.wav'):raise ValueError('Invalid clip filename')
        original=originals/(Path(filename).stem+'.mp3')
        if not original.exists():
            request=urllib.request.Request(track['mp3'],headers={'User-Agent':'VacaInteligente/1.0'})
            with urllib.request.urlopen(request,timeout=30) as response:data=response.read(3_000_001)
            if len(data)>3_000_000:raise ValueError('Source clip too large')
            original.write_bytes(data)
        target=directory/filename;temp=target.with_suffix('.tmp')
        subprocess.run([ffmpeg,'-nostdin','-y','-v','error','-i',str(original),'-t','8',
            '-af','silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB,loudnorm=I=-18:TP=-3:LRA=7,adelay=150:all=1,afade=t=out:st=7.8:d=0.2',
            '-ar','22050','-ac','1','-c:a','pcm_s16le','-f','wav',str(temp)],check=True)
        with wave.open(str(temp)) as audio:
            duration=audio.getnframes()/audio.getframerate()
            if not .15<duration<=8.01:raise ValueError('Invalid clip duration')
        temp.replace(target)
        print(track['title']+' — '+str(round(duration,2))+' s',flush=True)
        return {**track,'seconds':round(duration,2)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        prepared=list(executor.map(prepare,catalog))
    temp=directory/'catalog.tmp';temp.write_text(json.dumps(prepared,indent=2)+'\n');temp.replace(directory/'catalog.json')
    print('Ready: '+str(len(prepared))+' offline ringtones',flush=True)

if __name__=='__main__':main()
