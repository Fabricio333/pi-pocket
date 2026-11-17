"""Validated, persistent calibration values shared by the daemon and LAN controls."""
EFFECTS={'auto':'Rainbow mix','beat-tail':'Beat Tails','beat-running':'Beat Chases',
         'rainbow-tail':'Rainbow Tail','rainbow-flow':'Rainbow Flow','rainbow-running':'Rainbow Chase','beat-build':'Beat Build',
         'rainbow-gradient':'Rainbow Fade','rainbow-brush':'Color Brush','colorful-energy':'Color Energy',
         'rainbow-breathe':'Rainbow Bloom','blue-purple-flow':'Blue / Purple Flow','warm-cool-flow':'Yellow / Cyan Flow'}
DEFAULTS={'brightness':100,'delay_ms':0,'effect':'auto','beats_per_color':4,'payment_sound':True}

def validate(value):
    if not isinstance(value,dict) or not set(DEFAULTS)-{'payment_sound'}<=set(value) or set(value)-set(DEFAULTS):raise ValueError('Invalid calibration settings')
    value={**DEFAULTS,**value}
    if type(value['payment_sound']) is not bool:raise ValueError('payment_sound must be true or false')
    for key,minimum,maximum in [('brightness',10,1000),('delay_ms',-500,1000),('beats_per_color',1,16)]:
        if type(value[key]) is not int or not minimum<=value[key]<=maximum:
            raise ValueError(f'{key} must be an integer from {minimum} to {maximum}')
    if not isinstance(value['effect'],str) or value['effect'] not in EFFECTS:raise ValueError('Unknown lighting effect')
    return dict(value)
