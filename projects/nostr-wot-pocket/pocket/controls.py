"""Three right-side buttons; joystick inputs are deliberately ignored."""
class ThreeButtonControls:
    def __init__(self):
        self.previous=set();self.repeat={};self.bottom_at=0;self.back_sent=False
    def update(self,held,now):
        held=set(held)&{'one','two','three'};events=set()
        for physical,logical in [('one','up'),('two','down')]:
            if physical in held:
                if physical not in self.previous:
                    events.add(logical);self.repeat[physical]=now+.45
                elif now>=self.repeat.get(physical,float('inf')):
                    events.add(logical);self.repeat[physical]=now+.16
        if 'three' in held and 'three' not in self.previous:
            self.bottom_at=now;self.back_sent=False
        if 'three' in held and not self.back_sent and now-self.bottom_at>=.8:
            events.add('back');self.back_sent=True
        if 'three' not in held and 'three' in self.previous and not self.back_sent:events.add('ok')
        self.previous=held
        return events
