"""Persistent shuffle bags and ordered playback for locally cached ring sounds."""
import json
import os
from pathlib import Path
import random
import sqlite3
import threading

_preview=None

def get_preview():
    global _preview
    if _preview is None:_preview=Preview()
    return _preview

def stop_preview():
    if _preview is not None:_preview.stop()

class Preview:
    def __init__(self,pool=None):
        self.pool=pool or Ringtones()
        self.cancel=threading.Event();self.playing=False;self.current='';self.error=''
        self.lock=threading.Lock();self.thread=None

    def start(self,sink):
        with self.lock:
            if self.playing:return
            tracks=self.pool.tracks()
            if not tracks:self.error='No sounds installed';return
            self.cancel=threading.Event();cancel=self.cancel
            self.playing=True;self.error=''
            def worker():
                from .satsbell import play_sound
                try:
                    for index,track in enumerate(tracks):
                        if cancel.is_set():break
                        self.current=str(index+1)+'/'+str(len(tracks))+' '+track['title']
                        play_sound(sink,track=track,cancel=cancel)
                        if cancel.wait(.25):break
                except Exception as exc:self.error=str(exc)[:80]
                finally:self.playing=False;self.current=''
            self.thread=threading.Thread(target=worker,daemon=True);self.thread.start()

    def stop(self):
        self.cancel.set()

def state_directory():
    return Path(os.environ.get('POCKET_STATE_DIR',str(Path.home()/'.local/share/nostr-wot-pocket')))

class Ringtones:
    def __init__(self, directory=None):
        self.directory=Path(directory) if directory is not None else state_directory()
        self.sounds=self.directory/'ringtones'
        self.path=self.directory/'ringtones.sqlite3'

    def tracks(self):
        try:catalog=json.loads((self.sounds/'catalog.json').read_text())
        except (OSError,ValueError):return []
        result=[]
        for track in catalog:
            filename=track.get('file','')
            if filename and Path(filename).name==filename and filename.endswith('.wav'):
                path=self.sounds/filename
                if path.is_file():result.append({**track,'path':path})
        return result

    def connect(self):
        self.directory.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=10)
        os.chmod(self.path,0o600)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE IF NOT EXISTS rotation (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        return db

    @staticmethod
    def read(db,key,default):
        row=db.execute('SELECT value FROM rotation WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def write(db,key,value):
        db.execute('INSERT OR REPLACE INTO rotation VALUES (?,?)',(key,json.dumps(value)))

    @property
    def mode(self):
        if not self.path.exists():return 'shuffle'
        db=self.connect()
        try:return self.read(db,'mode','shuffle')
        finally:db.close()

    def set_mode(self,mode):
        if mode not in ('shuffle','ordered'):raise ValueError('Unknown ringtone mode')
        db=self.connect()
        try:
            with db:
                self.write(db,'mode',mode)
                self.write(db,'remaining',[])
                self.write(db,'cursor',0)
        finally:db.close()

    def next(self):
        tracks=self.tracks()
        if not tracks:return None
        by_id={t['id']:t for t in tracks}
        db=self.connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                mode=self.read(db,'mode','shuffle')
                if mode=='ordered':
                    index=self.read(db,'cursor',0)%len(tracks)
                    chosen=tracks[index]
                    self.write(db,'cursor',(index+1)%len(tracks))
                else:
                    remaining=[i for i in self.read(db,'remaining',[]) if i in by_id]
                    if not remaining:
                        remaining=list(by_id)
                        random.SystemRandom().shuffle(remaining)
                        if len(remaining)>1 and remaining[0]==self.read(db,'last',None):
                            remaining[0],remaining[1]=remaining[1],remaining[0]
                    chosen=by_id[remaining.pop(0)]
                    self.write(db,'remaining',remaining)
                self.write(db,'last',chosen['id'])
            return chosen
        finally:db.close()
