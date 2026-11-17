import time
from ..ui import ACCENT, MUTED

class App:
    def __init__(self,context):self.ctx=context;self.second=None;self.dirty=True
    def handle(self,keys):pass
    def tick(self,now):
        second=int(time.time())
        if second!=self.second:self.second=second;self.dirty=True
    def render(self):
        u=self.ctx.ui;im,d=u.base('Clock',time.strftime('%A'))
        u.text(d,109,time.strftime('%H:%M'),53,ACCENT,True)
        u.text(d,171,time.strftime('%d %b %Y'),20,MUTED)
        u.footer(d,'3 HOME');return im
    def close(self):pass
