"""Vaca Inteligente identity, rendered with native UI shapes at any size."""
from PIL import Image, ImageDraw

NAME='Vaca Inteligente'
DOMAIN='vacainteligente.com'
BG='#071d18'
CARD='#11372d'
ACCENT='#34d399'
TEXT='#fff8e7'
MUTED='#a9c9ba'

# One simple cow mark for device screens and the local web interfaces.
SVG='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" role="img" aria-label="Vaca Inteligente">
<rect x="2" y="2" width="124" height="124" rx="34" fill="#34d399"/>
<path d="M40 42L30 19L54 35ZM88 42L98 19L74 35Z" fill="#fff8e7"/>
<ellipse cx="29" cy="56" rx="18" ry="12" fill="#11372d"/><ellipse cx="99" cy="56" rx="18" ry="12" fill="#11372d"/>
<rect x="35" y="31" width="58" height="72" rx="27" fill="#fff8e7"/>
<ellipse cx="50" cy="47" rx="13" ry="16" fill="#11372d"/>
<circle cx="49" cy="63" r="5" fill="#071d18"/><circle cx="79" cy="63" r="5" fill="#071d18"/>
<rect x="34" y="75" width="60" height="32" rx="16" fill="#a9c9ba"/>
<circle cx="51" cy="90" r="4" fill="#11372d"/><circle cx="77" cy="90" r="4" fill="#11372d"/>
</svg>'''

def logo(size=192):
    scale=4
    image=Image.new('RGBA',(128*scale,128*scale))
    d=ImageDraw.Draw(image)
    def box(value):return tuple(int(x*scale) for x in value)
    def rounded(bounds,radius,color):d.rounded_rectangle(box(bounds),radius=radius*scale,fill=color)
    rounded((2,2,126,126),34,ACCENT)
    for points in (((40,42),(30,19),(54,35)),((88,42),(98,19),(74,35))):
        d.polygon([(x*scale,y*scale) for x,y in points],fill=TEXT)
    for bounds in ((11,44,47,68),(81,44,117,68)):d.ellipse(box(bounds),fill=CARD)
    rounded((35,31,93,103),27,TEXT)
    d.ellipse(box((37,31,63,63)),fill=CARD)
    for x in (49,79):d.ellipse(box((x-5,58,x+5,68)),fill=BG)
    rounded((34,75,94,107),16,MUTED)
    for x in (51,77):d.ellipse(box((x-4,86,x+4,94)),fill=CARD)
    return image.resize((size,size),Image.Resampling.LANCZOS)
