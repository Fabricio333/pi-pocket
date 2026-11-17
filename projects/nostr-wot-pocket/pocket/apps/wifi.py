import time
from ..wifi_setup import get_setup
from ..ui import MUTED

class App:
    def __init__(self,context):
        self.ctx=context;self.setup=get_setup(context);self.dirty=True;self.last=0
    def handle(self,keys):
        if 'ok' in keys:self.setup.open()
        self.dirty=True
    def tick(self,now):
        if now-self.last>=1:self.last=now;self.dirty=True
    def render(self):
        u=self.ctx.ui;im,d=u.base('Wi-Fi setup','Connect using your phone')
        session=self.setup.session
        if session and time.time()<session['expires']:
            u.text(d,105,session['ssid'],20,bold=True)
            u.text(d,134,session['password'],20,bold=True)
            u.text(d,164,'http://192.168.4.1:8788',15)
            u.text(d,191,self.setup.error or '10 min, then previous Wi-Fi',12,MUTED)
        else:
            u.text(d,105,'Open a temporary hotspot',17)
            u.text(d,135,'Paste Wi-Fi details on phone',15,MUTED)
            u.card(d,172,'Starting...' if self.setup.busy else 'Open setup hotspot',True)
            if self.setup.error:u.text(d,206,self.setup.error,12)
        u.footer(d);return im
    def close(self): pass
