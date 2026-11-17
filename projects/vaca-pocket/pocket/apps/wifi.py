import time
import qrcode
from PIL import Image
from ..wifi_setup import get_setup
from ..ui import MUTED
from ..brand import BG

def wifi_payload(ssid, password):
    def escape(value):
        return ''.join('\\'+c if c in '\\;,:"' else c for c in value)
    return 'WIFI:T:WPA;S:'+escape(ssid)+';P:'+escape(password)+';;'

def qr_image(payload):
    qr=qrcode.QRCode(box_size=1,border=4,error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(payload);qr.make(fit=True)
    code=qr.make_image(fill_color='black',back_color='white').convert('RGB')
    scale=196//code.width
    if scale<1:raise ValueError('Setup QR is too large')
    code=code.resize((code.width*scale,code.height*scale),Image.Resampling.NEAREST)
    canvas=Image.new('RGB',(196,196),'white')
    canvas.paste(code,((196-code.width)//2,(196-code.height)//2))
    return canvas

class App:
    def __init__(self,context):
        self.ctx=context;self.setup=get_setup(context);self.dirty=True;self.last=0
        self.page=0;self.cached=None;self.qrs=[]
    def handle(self,keys):
        session=self.setup.session
        if session and time.time()<session['expires']:
            if keys & {'ok','down'}:self.page=(self.page+1)%3
            elif 'up' in keys:self.page=(self.page-1)%3
        elif 'ok' in keys:self.page=0;self.setup.open()
        self.dirty=True
    def tick(self,now):
        if now-self.last>=1:self.last=now;self.dirty=True
    def render(self):
        u=self.ctx.ui;im,d=u.base('Wi-Fi setup','Connect using your phone')
        session=self.setup.session
        if session and time.time()<session['expires']:
            key=(session['ssid'],session['password'],session['url'])
            if key!=self.cached:
                self.qrs=[qr_image(wifi_payload(*key[:2])),qr_image(key[2])];self.cached=key;self.page=0
            if self.page<2:
                im=Image.new('RGB',(240,240),BG)
                from PIL import ImageDraw
                d=ImageDraw.Draw(im)
                u.text(d,3,'Scan to join Wi-Fi' if self.page==0 else 'Scan to open setup',16,bold=True)
                im.paste(self.qrs[self.page],(22,25))
                u.text(d,225,'3 NEXT · hold 3 BACK',10,MUTED)
                return im
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
