import os, subprocess, threading
from ..ui import ROOT, MUTED

class App:
    def __init__(self,context):
        self.ctx=context;self.selected=0;self.player=None;self.dirty=True;self.previewing=False
        self.preview_cancel=threading.Event();self.playing_selected=None
    def play(self):
        self.stop()
        if self.selected==2:
            if self.previewing:return
            self.preview_cancel=threading.Event();cancel=self.preview_cancel
            self.previewing=True;self.playing_selected=2;self.dirty=True
            def preview():
                try:
                    from ..celebration import celebrate,prepare
                    worker=prepare()
                    if worker:worker.ready.wait(timeout=10)
                    if not cancel.is_set():celebrate(cancel)
                finally:
                    self.previewing=False;self.dirty=True
                    if self.playing_selected==2:self.playing_selected=None
            threading.Thread(target=preview,daemon=True).start();return
        if self.selected==3:return
        name=['thunder-natural.wav','zap-announcement.wav'][self.selected]
        env=os.environ.copy();env['XDG_RUNTIME_DIR']='/run/user/1000'
        self.player=subprocess.Popen(['paplay','--device='+self.ctx.sink,str(ROOT/'assets/audio'/name)],env=env,
                                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.playing_selected=self.selected
        self.dirty=True
    def stop(self):
        self.preview_cancel.set()
        if self.player and self.player.poll() is None:self.player.terminate();self.player.wait(timeout=2)
        self.player=None;self.playing_selected=None
    def handle(self,keys):
        if 'up' in keys:self.selected=(self.selected-1)%4;self.dirty=True
        if 'down' in keys:self.selected=(self.selected+1)%4;self.dirty=True
        if 'ok' in keys:
            if self.selected==3 or self.selected==self.playing_selected:self.stop();self.dirty=True
            else:self.play()
    def tick(self,now):
        if self.player and self.player.poll() is not None:self.player=None;self.playing_selected=None;self.dirty=True
    def render(self):
        u=self.ctx.ui;im,d=u.base('Thunder Lab','Cached audio. No synthesis.')
        first=max(0,self.selected-2)
        for i,label in enumerate(['Thunder only','Zap + voice','Zap + lights TEST','Stop playback'][first:first+3]):u.card(d,101+i*32,label,first+i==self.selected,'#b45309')
        u.text(d,203,'Preview only · no payment' if self.previewing else 'Choose a recording',12,MUTED)
        u.footer(d,'1 PLAY  ·  2 STOP  ·  3 HOME');return im
    def close(self):self.stop()
