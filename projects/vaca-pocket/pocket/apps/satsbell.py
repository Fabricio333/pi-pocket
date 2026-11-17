"""Sats Bell on the existing 240x240 screen and three physical buttons."""
import time
import qrcode
from PIL import Image
from ..satsbell import get_bell
from ..ui import MUTED

def address_lines(address):
    number, separator, domain = address.partition('@')
    if domain == 'zaps.nostr-wot.com':
        domain = 'nostrwot.com'
    return number, '@' + domain if separator else ''

class App:
    def __init__(self, context):
        self.ctx = context; self.bell = get_bell(context)
        self.selected = 0; self.page = 'menu'; self.dirty = True; self.last = 0
        self.notice = ''; self.notice_until = 0; self.qr = None

    def handle(self, keys):
        if self.page == 'confirm':
            if 'up' in keys:
                self.bell.action('release'); self.page = 'menu'
            elif keys: self.page = 'menu'
            self.dirty = True
            return
        if self.page != 'menu':
            if keys: self.page = 'menu'; self.dirty = True
            return
        if 'up' in keys: self.selected = (self.selected - 1) % 5
        if 'down' in keys: self.selected = (self.selected + 1) % 5
        if 'ok' in keys:
            if self.selected == 0: self.bell.action('create')
            elif self.selected == 1:
                if self.bell.address:
                    qr = qrcode.QRCode(box_size=1, border=4)
                    number, domain = address_lines(self.bell.address)
                    qr.add_data('lightning:' + number + domain); qr.make(fit=True)
                    code = qr.make_image().convert('RGB')
                    scale = 240 // code.width
                    self.qr = Image.new('RGB', (240, 240), 'white')
                    code = code.resize((code.width * scale, code.height * scale), Image.Resampling.NEAREST)
                    self.qr.paste(code, ((240-code.width)//2, (240-code.height)//2)); self.page = 'qr'
            elif self.selected == 2: self.bell.action('test')
            elif self.selected == 3: self.page = 'confirm'
            else: self.page = 'history'
        self.dirty = True

    def back(self):
        if self.page != 'menu': self.page = 'menu'; self.dirty = True; return True
        return False

    def event(self, kind, value):
        if kind == 'satsbell-paid':
            self.notice = str(value['amount']) + ' sats received'; self.notice_until = time.monotonic()+10; self.dirty = True

    def tick(self, now):
        if self.notice and now>=self.notice_until: self.notice=''
        if now-self.last >= 1: self.last=now; self.dirty=True

    def render(self):
        if self.page == 'qr': return self.qr
        u = self.ctx.ui
        im, d = u.base('Doorbell', self.bell.error or self.notice or self.bell.status)
        if self.page == 'confirm':
            u.text(d, 110, 'Release this address?', 18)
            u.text(d, 143, '1 confirm / 2 cancel', 16)
        elif self.page == 'history':
            for i, (amount, missed, at) in enumerate(self.bell.store.history()[:4]):
                u.text(d, 105+i*25, f'{amount//1000} sats · '+('missed' if missed else 'rang'), 17)
        else:
            if self.bell.address:
                number, domain = address_lines(self.bell.address)
                u.text(d, 94, number, 42, bold=True)
                u.text(d, 137, domain, 17, MUTED)
            else:
                u.text(d, 111, 'No address yet', 19, bold=True)
            labels = ['Create address', 'Show address QR', 'Test JBL sound', 'Release address', 'Recent payments']
            first=max(0,self.selected-1)
            for i, label in enumerate(labels[first:first+2]): u.card(d, 156+i*30, label, first+i==self.selected)
        u.footer(d); return im

    def close(self): pass
