"""Lazy local UI for the NIP-46 Sky bridge. No account private keys on the Pi."""
import json, os, queue, shutil, subprocess, threading, time
from pathlib import Path
from PIL import Image
import qrcode
from ..ui import ROOT, ACCENT, CARD, MUTED
EMOTES=[(None,'Stop emote'),('groove','Dance'),('dance','Dance 2'),('lotus','Lotus'),
        ('pushup','Push-ups'),('jacks','Jumping jacks'),('yes','Nod'),('no','Shake head'),
        ('arms','Arms folded'),('crouch','Crouch'),('sangre','Sangreee…')]
ACTIONS=['Walk north','Walk east','Walk south','Walk west','Stop','Jump','Choose emote','Toggle run','Account']

class App:
    def __init__(self,context):
        self.ctx=context;self.messages=queue.Queue();self.child=None;self.page='intro';self.dirty=True
        self.status='Choose Connect';self.name='';self.qr=None;self.info=False;self.running=False
        self.state={'position':{'x':0,'z':3.2},'peers':[],'accepted':0,'seen':0,'sending':False}
        self.last_input=0;self.last_render=0;self.emote=0;self.closed=False;self.approval_stage=None
        self.relay='public.obelisk.ar';self.notice='';self.published=False
        self.selection=0;self.motion=(0,0);self.intro_choice=0;self.account_choice=0;self.forgetting=False
    def send(self,value):
        if self.child and self.child.poll() is None:
            try:self.child.stdin.write(json.dumps(value)+'\n');self.child.stdin.flush()
            except (OSError,BrokenPipeError):pass
    def connect(self):
        if self.child and self.child.poll() is None:return
        candidate=os.environ.get('POCKET_NODE') or shutil.which('node') or str(Path.home()/'.local/node/bin/node')
        bundle=ROOT/'bridge/dist/sky-bridge.mjs'
        if not Path(candidate).is_file() or not bundle.exists():
            self.page='setup';self.dirty=True;return
        env=os.environ.copy();env['NODE_NO_WARNINGS']='1'
        self.child=subprocess.Popen([candidate,str(bundle)],cwd=ROOT,stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1,env=env)
        child=self.child
        def read():
            try:
                for line in child.stdout:
                    try:self.messages.put(json.loads(line))
                    except ValueError:pass
            finally:self.messages.put({'type':'closed'})
        threading.Thread(target=read,daemon=True).start()
        self.status='Connecting signer…';self.page='waiting';self.dirty=True
    def handle(self,keys):
        if self.page=='emotes':
            if 'up' in keys:self.emote=(self.emote-1)%len(EMOTES);self.dirty=True
            if 'down' in keys:self.emote=(self.emote+1)%len(EMOTES);self.dirty=True
            if 'ok' in keys:
                self.motion=(0,0)
                self.send({'op':'input','x':0,'z':0,'run':self.running})
                self.send({'op':'emote','value':EMOTES[self.emote][0]})
                self.page='map';self.status='Sending '+EMOTES[self.emote][1];self.dirty=True
            return
        if self.page in ['intro','setup','failed']:
            if keys & {'up','down'}:self.intro_choice=1-self.intro_choice;self.dirty=True
            if 'ok' in keys:
                if self.intro_choice==0:self.connect()
                else:self.forget()
            return
        if self.page in ['pairing','auth','waiting']:
            if keys & {'up','down','ok'} and self.qr:self.info=not self.info;self.dirty=True
            return
        if self.page=='account':
            if keys & {'up','down'}:self.account_choice=1-self.account_choice;self.dirty=True
            if 'ok' in keys:
                if self.account_choice:self.forget()
                else:self.page='map';self.dirty=True
            return
        if 'up' in keys:self.selection=(self.selection-1)%len(ACTIONS);self.dirty=True
        if 'down' in keys:self.selection=(self.selection+1)%len(ACTIONS);self.dirty=True
        if 'ok' not in keys:return
        if self.selection<4:
            vector=[(0,-1),(1,0),(0,1),(-1,0)][self.selection]
            self.motion=(0,0) if self.motion==vector else vector
        elif self.selection==4:self.motion=(0,0);self.send({'op':'emote','value':None})
        elif self.selection==5:self.send({'op':'jump'})
        elif self.selection in [6,8]:
            self.motion=(0,0);self.send({'op':'input','x':0,'z':0,'run':self.running})
            self.page='emotes' if self.selection==6 else 'account'
        elif self.selection==7:self.running=not self.running
        self.dirty=True
    def forget(self):
        self.motion=(0,0);self.forgetting=True;self.send({'op':'forget'})
        file=Path(os.environ.get('POCKET_STATE_DIR',str(Path.home()/'.local/share/nostr-wot-pocket')))/'sky-session.json'
        file.unlink(missing_ok=True);self.page='intro';self.status='Signer forgotten';self.dirty=True
    def back(self):
        self.motion=(0,0);self.send({'op':'input','x':0,'z':0,'run':self.running})
        if self.page in ['emotes','account']:self.page='map';self.dirty=True;return True
        return False
    def tick(self,now):
        while True:
            try:event=self.messages.get_nowait()
            except queue.Empty:break
            kind=event.get('type')
            if kind in ['pairing','auth']:
                qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L,border=4,box_size=1)
                qr.add_data(event['uri']);qr.make(fit=True)
                self.qr=qr.make_image(fill_color='black',back_color='white').convert('RGB').resize((240,240),Image.Resampling.NEAREST)
                self.page=kind;self.info=False
            elif kind=='paired':
                self.page='waiting';self.qr=None;self.info=True;self.status='Signer connected'
            elif kind=='approval':
                stage=event.get('stage');self.approval_stage=stage if event.get('waiting') else None
                if event.get('waiting'):
                    self.status={'account':'Approve account access','relay':'Approve relay login',
                                 'movement':'Approve movement / emote'}.get(stage,'Waiting for approval')
                    if stage=='account':self.page='waiting';self.info=True
                    self.notice=''
                else:self.status='Approval received' if event.get('approved') else 'Approval cancelled or denied'
            elif kind=='status':
                self.status=event['status'].replace('-',' ').capitalize()
                if event['status'] in ['failed','refused']:self.page='failed'
            elif kind=='connected':
                self.page='map';self.relay=event['relay'].removeprefix('wss://');self.status='Waiting for relay';self.info=False
                self.name=event['pubkey'][:8]+'…'
            elif kind=='profile':
                if event.get('name'):self.name=event['name']
            elif kind=='state':self.state=event
            elif kind=='published':self.status='Relay accepted';self.published=True;self.notice=''
            elif kind=='observed':self.status='Visible on relay';self.notice=''
            elif kind=='error':self.notice=event.get('message','Connection error')
            elif kind=='closed' and not self.closed:
                self.page='intro' if self.forgetting else 'failed'
                self.status='Signer forgotten' if self.forgetting else 'Signer session closed';self.forgetting=False
            self.dirty=True
        if self.page=='map' and now-self.last_input>=.1:
            x,z=self.motion
            self.send({'op':'input','x':x,'z':z,'run':self.running});self.last_input=now
    def render(self):
        if self.page in ['pairing','auth'] and not self.info:return self.qr
        u=self.ctx.ui
        if self.page in ['intro','setup','failed']:
            im,d=u.base('Obelisk Sky','Remote signer · multiplayer')
            if self.page=='setup':
                u.text(d,107,'Install Sky runtime first',16)
                u.text(d,137,'See README → Sky setup',14,MUTED)
            elif self.page=='failed':
                u.text(d,103,self.status,16)
                u.text(d,135,self.notice or 'Check your signer app',13,MUTED)
            else:
                u.text(d,106,'Your avatar. Your signer.',16)
                u.text(d,137,'Three-button movement',15,MUTED)
            u.card(d,181,['Connect signer','Forget signer'][self.intro_choice],True)
            u.footer(d,'1 CONNECT  ·  2 FORGET  ·  3 HOME')
        elif self.page in ['waiting','pairing','auth']:
            im,d=u.base('Connect signer',self.status)
            u.text(d,108,'Waiting for approval' if self.approval_stage else 'Scan or approve in signer',17)
            u.text(d,140,'Check your remote signer',14,MUTED)
            u.text(d,170,'This connection stays open',14,MUTED)
            u.footer(d,'2 SHOW QR  ·  3 CANCEL' if self.qr else '3 CANCEL')
        elif self.page=='emotes':
            u=self.ctx.ui;im,d=u.base('Choose emote','Previous / next, then select')
            first=max(0,self.emote-2)
            for row,(_,label) in enumerate(EMOTES[first:first+3]):
                u.card(d,105+row*33,label,first+row==self.emote)
            u.footer(d,'PRESS APPLY  ·  2 BACK  ·  3 HOME')
        elif self.page=='account':
            im,d=u.base('Sky account',self.name)
            u.text(d,111,self.relay,17,MUTED)
            u.card(d,181,['Return to map','Forget signer'][self.account_choice],True)
            u.footer(d)
        else:
            im,d=u.base('Obelisk Sky',self.name)
            # A bounded plaza map: centre is the Obelisk, north is up.
            left,top,right,bottom=24,94,216,159
            d.rounded_rectangle((left,top,right,bottom),radius=10,fill=CARD)
            def dot(p):return (120+p['x']*18,126+(p['z']-.5)*6)
            d.rectangle((86,114,154,138),fill='#39304e',outline='#77678f')
            for p in self.state.get('peers',[]):
                x,y=dot(p)
                if left+3<x<right-3 and top+3<y<bottom-3:d.ellipse((x-2,y-2,x+2,y+2),fill=MUTED)
            x,y=dot(self.state['position']);d.ellipse((x-5,y-5,x+5,y+5),fill='#22c55e' if self.published else ACCENT)
            line=self.notice or self.status
            u.text(d,164,line,11,'#fbbf24' if self.notice else MUTED)
            label=ACTIONS[self.selection]
            if self.selection<4 and self.motion==[(0,-1),(1,0),(0,1),(-1,0)][self.selection]:label='Stop walking'
            if self.selection==7:label='Run: '+('ON' if self.running else 'OFF')
            u.card(d,183,label,True,'#0369a1')
            u.footer(d)
        return im
    def close(self):
        self.closed=True
        if self.child and self.child.poll() is None:
            self.send({'op':'close'})
            try:self.child.wait(timeout=2.5)
            except subprocess.TimeoutExpired:
                self.child.terminate()
                try:self.child.wait(timeout=1)
                except subprocess.TimeoutExpired:self.child.kill();self.child.wait()
        self.child=None
