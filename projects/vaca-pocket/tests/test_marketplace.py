import importlib, json, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from pocket.registry import Registry
from pocket.ui import UI

class MarketplaceTests(unittest.TestCase):
    def test_installed_apps_persist_and_unknown_app_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            r=Registry(directory)
            self.assertEqual(r.installed,{'pay21'})
            r.install('clock')
            self.assertIn('clock',Registry(directory).installed)
            r.uninstall('clock')
            self.assertNotIn('clock',Registry(directory).installed)
            with self.assertRaises(ValueError):r.install('arbitrary-code')

    def test_catalog_does_not_load_apps_and_uninstalled_apps_cannot_open(self):
        with tempfile.TemporaryDirectory() as directory:
            sys.modules.pop('pocket.apps.clock',None)
            r=Registry(directory)
            self.assertNotIn('pocket.apps.clock',sys.modules)
            with self.assertRaises(ValueError):r.open('clock',None)
            r.install('clock')
            app=r.open('clock',SimpleNamespace(ui=UI()))
            self.assertIn('pocket.apps.clock',sys.modules)
            self.assertEqual(app.render().size,(240,240))
            app.close();del app;r.unload('clock')
            self.assertNotIn('pocket.apps.clock',sys.modules)
            self.assertFalse(hasattr(sys.modules['pocket.apps'],'clock'))

    def test_payment_states_render_and_qr_fills_display(self):
        module=importlib.import_module('pocket.apps.pay21')
        ctx=SimpleNamespace(ui=UI(),invoice=None)
        app=module.App(ctx)
        for page in ['intro','loading','paid','error']:
            app.page=page
            self.assertEqual(app.render().size,(240,240))
        app.make_qr('LNBC210N1'+'A'*450)
        self.assertEqual(app.render().size,(240,240))
        self.assertEqual(app.render().getpixel((0,0)),(255,255,255))

    def test_text_is_within_horizontal_margins(self):
        ui=UI();image,draw=ui.base('A very long marketplace application title')
        captured=[]
        original=draw.text
        def capture(xy,value,**kwargs):
            measured={k:v for k,v in kwargs.items() if k!='fill'}
            captured.append(draw.textbbox(xy,value,**measured));return original(xy,value,**kwargs)
        draw.text=capture
        for value in ['fabri@nostrwot.com','Verified provider receipt','Extremely long app marketplace title','x'*300]:
            ui.text(draw,100,value,30,bold=True)
        for left,top,right,bottom in captured:
            self.assertGreaterEqual(left,12);self.assertLessEqual(right,228)

    def test_sky_screens_do_not_start_a_signer_until_connect(self):
        from pocket.apps.sky import App
        ctx=SimpleNamespace(ui=UI(),held=set())
        app=App(ctx)
        self.assertIsNone(app.child)
        for page in ['intro','setup','failed','waiting','map','emotes','account']:
            app.page=page
            self.assertEqual(app.render().size,(240,240))
        self.assertIsNone(app.child)
        app.close()

    def test_three_buttons_short_press_long_press_and_joystick_ignored(self):
        from pocket.controls import ThreeButtonControls
        buttons=ThreeButtonControls()
        self.assertEqual(buttons.update({'up','right','ok'},0),set())
        self.assertEqual(buttons.update({'one'},1),{'up'})
        self.assertEqual(buttons.update({'one'},1.1),set())
        self.assertEqual(buttons.update({'one'},1.5),{'up'})
        buttons.update(set(),2)
        self.assertEqual(buttons.update({'three'},3),set())
        self.assertEqual(buttons.update(set(),3.1),{'ok'})
        buttons.update({'three'},4)
        self.assertEqual(buttons.update({'three'},4.9),{'back'})
        self.assertEqual(buttons.update(set(),5),set())

    def test_emote_chooser_sends_once_and_does_not_walk_on_confirmation(self):
        from pocket.apps.sky import App, EMOTES
        ctx=SimpleNamespace(ui=UI(),held={'two'})
        app=App(ctx);app.page='map';app.selection=6;sent=[];app.send=sent.append
        app.handle({'ok'});self.assertEqual(app.page,'emotes')
        app.handle({'down'});app.handle({'ok'})
        self.assertEqual(app.page,'map')
        self.assertEqual([e for e in sent if e['op']=='emote'],[{'op':'emote','value':EMOTES[1][0]}])
        app.tick(1)
        self.assertEqual(sent[-1]['x'],0)
        app.selection=0;app.handle({'ok'});app.tick(3)
        self.assertEqual(sent[-1]['z'],-1)

    def test_payment_qr_controls_are_available_without_joystick(self):
        from pocket.apps.pay21 import App
        app=App(SimpleNamespace(ui=UI(),invoice=None))
        app.make_qr('LNBC210N1'+'A'*100)
        app.handle({'ok'});self.assertEqual(app.page,'intro')
        app.handle({'ok'});self.assertEqual(app.page,'qr')
        self.assertTrue(app.back());self.assertEqual(app.page,'intro')

    def test_led_control_menu_and_brightness_are_button_operated(self):
        from unittest.mock import patch
        from pocket.apps.leds import App,OPTIONS
        class Worker:
            level=100;mode='steady';reactive_delay=.15
            def __init__(self):
                import threading
                self.ready=threading.Event();self.ready.set();self.commands=[]
            def command(self,*args):self.commands.append(args)
        worker=Worker()
        with patch('pocket.celebration.prepare',return_value=worker):app=App(SimpleNamespace(ui=UI()))
        app.selected=next(i for i,x in enumerate(OPTIONS) if x[0]=='white-wipe');app.handle({'ok'});self.assertEqual(worker.commands[-1],('effect','white-wipe'))
        app.selected=next(i for i,x in enumerate(OPTIONS) if x[0]=='audio-live');app.handle({'ok'})
        self.assertEqual(worker.commands[-1],('audio-live',))
        app.selected=next(i for i,x in enumerate(OPTIONS) if x[0]=='delay');app.handle({'ok'})
        self.assertEqual(app.page,'delay');self.assertEqual(app.render().size,(240,240))
        app.handle({'down'});app.handle({'ok'})
        self.assertEqual(worker.commands[-1],('delay',.175))
        app.selected=next(i for i,x in enumerate(OPTIONS) if x[0]=='brightness')
        app.handle({'ok'});self.assertEqual(app.page,'brightness')
        app.handle({'down'});app.handle({'ok'})
        self.assertEqual(worker.commands[-1],('brightness',110))
        self.assertEqual(app.render().size,(240,240))

if __name__=='__main__':unittest.main()
