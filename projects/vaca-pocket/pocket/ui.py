from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .brand import BG, CARD, ACCENT, TEXT, MUTED, DOMAIN, logo

ROOT=Path(__file__).resolve().parent.parent
class UI:
    def __init__(self):
        self.fonts={}
        self.logo=logo()
    def text(self,d,y,value,size=20,color=TEXT,bold=False,x=120,anchor='mt',width=212):
        while True:
            key=(size,bold)
            if key not in self.fonts:
                name='DejaVuSans'+('-Bold' if bold else '')+'.ttf'
                self.fonts[key]=ImageFont.truetype(str(ROOT/'assets/fonts'/name),size)
            font=self.fonts[key]; b=d.textbbox((0,0),value,font=font)
            if b[2]-b[0]<=width or size<=10: break
            size-=1
        if b[2]-b[0]>width:
            while value and d.textbbox((0,0),value+'…',font=font)[2]>width:value=value[:-1]
            value+='…'
        d.text((x,y),value,font=font,fill=color,anchor=anchor)
    def base(self,title,subtitle=None):
        im=Image.new('RGB',(240,240),BG);d=ImageDraw.Draw(im)
        icon=self.logo.resize((25,25),Image.Resampling.LANCZOS)
        im.paste(icon,(12,9),icon)
        self.text(d,15,DOMAIN,12,MUTED,True,x=45,anchor='lt',width=183)
        self.text(d,45,title,26,bold=True)
        if subtitle:self.text(d,79,subtitle,13,MUTED)
        return im,d
    def startup(self,progress=0,label='Starting your pocket'):
        im=Image.new('RGB',(240,240),BG);d=ImageDraw.Draw(im)
        self.text(d,23,'VACA',24,bold=True)
        self.text(d,49,'INTELIGENTE',13,MUTED,True)
        icon=self.logo.resize((100,100),Image.Resampling.LANCZOS)
        im.paste(icon,(70,75),icon)
        self.text(d,184,DOMAIN,15,bold=True)
        d.rounded_rectangle((44,212,196,216),radius=2,fill=CARD)
        amount=max(0,min(1,progress))
        if amount:d.rounded_rectangle((44,212,44+int(152*amount),216),radius=2,fill=ACCENT)
        self.text(d,225,label,10,MUTED)
        return im
    def footer(self,d,value=None):self.text(d,220,'1 ↑  2 ↓  3 OK  ·  hold 3 BACK',10,MUTED)
    def card(self,d,y,label,selected=False,color=ACCENT):
        d.rounded_rectangle((12,y,228,y+29),radius=8,fill=color if selected else CARD)
        self.text(d,y+5,label,17,bold=selected)
