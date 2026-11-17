"""Payment UI and QR dependencies are loaded only when the app opens."""
import math, threading, time
from urllib.error import HTTPError, URLError
from PIL import Image
import qrcode
from ..ui import MUTED, CARD, ACCENT

def invoice_error(exc):
    if isinstance(exc, HTTPError):
        return f'Invoice server HTTP {exc.code}'
    if isinstance(exc, (TimeoutError, URLError)):
        return 'Network request failed'
    return 'Invoice request rejected'

class App:
    def __init__(self,context):
        self.error='Invoice request failed';self.address_qr=None;self.current_address='fabri@nostrwot.com'
        self.ctx=context;self.page='intro';self.busy=False;self.dirty=True;self.qr=None;self.choice=0
        if context.invoice:
            from ..zap_backend import invoice_address
            self.current_address=invoice_address(context.invoice)
            self.make_qr(context.invoice)
    def make_qr(self,invoice):
        qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L,box_size=1,border=4)
        qr.add_data(invoice.upper());qr.make(fit=True)
        code=qr.make_image(fill_color='black',back_color='white').convert('RGB')
        self.qr=code.resize((240,240),Image.Resampling.NEAREST)
        self.page='qr';self.dirty=True
    def request(self):
        if self.busy:return
        self.busy=True;self.page='loading';self.dirty=True
        def worker():
            try:
                from ..zap_backend import create_invoice, invoice_address
                invoice=create_invoice(self.ctx.events)
                self.ctx.events.put(('invoice-provider',invoice_address(invoice)))
                self.ctx.events.put(('invoice',invoice))
            except Exception as exc:
                print('Invoice creation failed: '+str(exc),flush=True)
                self.ctx.events.put(('invoice-error',invoice_error(exc)))
        threading.Thread(target=worker,daemon=True).start()
    def handle(self,keys):
        if self.page=='qr':
            if keys & {'up','down','ok'}:self.page='intro';self.choice=0;self.dirty=True
        elif self.page=='intro':
            if keys & {'up','down'}:self.choice=1-self.choice if self.qr else 0;self.dirty=True
            if 'ok' in keys:
                if self.qr is not None and self.choice==0:self.page='qr';self.dirty=True
                else:self.request()
        elif self.page=='address':
            if keys & {'up','down','ok'}:self.page='intro';self.dirty=True
        elif self.page=='error':
            if keys & {'up','down'}:
                qr=qrcode.QRCode(box_size=1,border=4)
                qr.add_data('lightning:avidflower48@walletofsatoshi.com');qr.make(fit=True)
                code=qr.make_image(fill_color='black',back_color='white').convert('RGB')
                scale=240//code.width
                self.address_qr=Image.new('RGB',(240,240),'white')
                code=code.resize((code.width*scale,code.height*scale),Image.Resampling.NEAREST)
                self.address_qr.paste(code,((240-code.width)//2,(240-code.height)//2))
                self.page='address';self.dirty=True
            elif 'ok' in keys:self.request()
        elif self.page=='paid' and 'ok' in keys:self.request()
    def back(self):
        if self.page in ['qr','address']:self.page='intro';self.dirty=True;return True
        return False
    def event(self,kind,value):
        if kind=='invoice-provider':self.current_address=value;self.dirty=True
        elif kind=='invoice':self.busy=False;self.make_qr(value)
        elif kind=='invoice-error':self.error=value;self.busy=False;self.page='error';self.dirty=True
        elif kind=='paid':self.busy=False;self.qr=None;self.page='paid';self.dirty=True
    def tick(self,now):
        if self.page=='loading':self.dirty=True
    def render(self):
        if self.page=='qr':return self.qr
        if self.page=='address':return self.address_qr
        u=self.ctx.ui
        if self.page=='paid':
            im,d=u.base('Zap received!','Verified provider receipt')
            d.ellipse((92,105,148,161),fill='#22c55e');d.line((106,132,117,143,137,121),fill='white',width=5)
            u.text(d,173,'21 SATS',30,bold=True);u.footer(d,'1 NEW  ·  3 HOME')
        elif self.page=='loading':
            im,d=u.base('Creating invoice','Requesting a Lightning invoice')
            for i in range(8):
                a=i*math.pi/4;x=120+25*math.cos(a);y=148+25*math.sin(a)
                d.ellipse((x-5,y-5,x+5,y+5),fill=ACCENT if i==int(time.monotonic()*5)%8 else CARD)
            u.footer(d,'3 HOME  ·  RECEIPTS STAY ACTIVE')
        elif self.page=='error':
            im,d=u.base('Invoice unavailable');u.text(d,91,self.error,16)
            u.text(d,120,'WoS address QR: set sats',14,MUTED)
            u.text(d,145,'Server still needed to pay',14,MUTED)
            u.text(d,170,'No device confirmation',14,MUTED)
            u.text(d,220,'1/2 WoS ADDRESS  ·  3 RETRY',10,MUTED)
        else:
            im,d=u.base('Pay 21','Lightning to Fabri')
            name,domain=self.current_address.split('@',1)
            u.text(d,103,name+'@',24,bold=True);u.text(d,137,domain,22,bold=True)
            action=('Show current QR' if self.choice==0 else 'Create NEW invoice') if self.qr else 'Create 21-sat QR'
            u.card(d,181,action,True)
            u.footer(d,'1 CREATE QR  ·  3 HOME')
        return im
    def close(self):pass
