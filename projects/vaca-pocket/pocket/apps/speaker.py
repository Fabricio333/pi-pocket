"""Volume, mute and Bluetooth onboarding on the three-button display."""
import threading
from ..speaker import get_speaker
from ..ui import ACCENT,CARD,MUTED

class App:
    def __init__(self,context):
        self.ctx=context;self.speaker=get_speaker(context)
        self.page='menu';self.selected=0;self.device_selection=0;self.dirty=True;self.last=0

    def handle(self,keys):
        s=self.speaker
        if self.page=='volume':
            if 'up' in keys:s.set_volume(s.volume+5)
            if 'down' in keys:s.set_volume(s.volume-5)
            if 'ok' in keys:self.page='menu'
        elif self.page=='devices':
            count=len(s.devices)+1
            if 'up' in keys:self.device_selection=(self.device_selection-1)%count
            if 'down' in keys:self.device_selection=(self.device_selection+1)%count
            if 'ok' in keys:
                if self.device_selection==0:s.enqueue('scan')
                else:
                    device=s.devices[(self.device_selection-1)%len(s.devices)]
                    if s.enqueue('connect',device):
                        s.message='Connecting: '+device['name'];s.error='';self.page='menu'
        else:
            if 'up' in keys:self.selected=(self.selected-1)%4
            if 'down' in keys:self.selected=(self.selected+1)%4
            if 'ok' in keys:
                if self.selected==0:self.page='volume'
                elif self.selected==1:self.page='devices';s.enqueue('scan')
                elif self.selected==2:s.set_mute(not s.muted)
                else:
                    from ..satsbell import play_sound
                    def test():
                        try:play_sound(self.ctx.sink)
                        except Exception:s.error='Playback failed; reconnect speaker'
                    threading.Thread(target=test,daemon=True).start()
        self.dirty=True

    def back(self):
        if self.page!='menu':self.page='menu';self.dirty=True;return True
        return False

    def tick(self,now):
        if now-self.last>=2:
            self.last=now;self.dirty=True
            if self.page!='devices' and not self.speaker.busy:self.speaker.enqueue('refresh')

    def render(self):
        s=self.speaker;u=self.ctx.ui
        if self.page=='devices':
            im,d=u.base('Bluetooth speakers',s.error or s.message)
            u.text(d,100,'Put new speaker in pairing mode',12,MUTED)
            entries=['Search again']+[device['name'] for device in s.devices]
            self.device_selection%=len(entries);first=max(0,self.device_selection-2)
            for i,label in enumerate(entries[first:first+3]):u.card(d,119+i*32,label,first+i==self.device_selection)
        elif self.page=='volume':
            im,d=u.base('Volume',s.name)
            u.text(d,110,str(s.volume)+'%',58,ACCENT,True)
            d.rounded_rectangle((25,180,215,189),radius=4,fill=CARD)
            if s.volume:d.rounded_rectangle((25,180,25+int(190*s.volume/100),189),radius=4,fill=ACCENT)
            u.text(d,220,'1 +5%  ·  2 -5%  ·  3 DONE',10,MUTED)
            return im
        else:
            im,d=u.base('Speaker settings',s.name)
            u.text(d,97,str(s.volume)+'%',40,ACCENT,True)
            u.text(d,140,s.error or ('Muted' if s.muted else s.message),12,MUTED)
            labels=['Volume','Bluetooth speakers','Unmute speaker' if s.muted else 'Mute speaker','Test ringtone']
            first=max(0,self.selected-1)
            for i,label in enumerate(labels[first:first+2]):u.card(d,157+i*30,label,first+i==self.selected)
        u.footer(d);return im

    def close(self):pass
