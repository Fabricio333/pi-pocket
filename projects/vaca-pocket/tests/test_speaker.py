import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pocket.speaker import Speaker

OLD='90:F2:60:5E:89:28'
NEW='AA:BB:CC:DD:EE:FF'
SINK='bluez_sink.AA_BB_CC_DD_EE_FF.a2dp_sink'

class SpeakerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        env=patch.dict(os.environ,{'POCKET_AUDIO_SINK':'bluez_sink.90_F2_60_5E_89_28.a2dp_sink','POCKET_SPEAKER_ADDRESS':OLD})
        env.start();self.addCleanup(env.stop)
        self.ctx=SimpleNamespace(sink='old')
        self.speaker=Speaker(self.ctx,self.temp.name)

    def test_volume_mute_bounds_and_persistence(self):
        s=self.speaker;s.set_volume(200);self.assertEqual(s.volume,100)
        s.set_volume(-10);self.assertEqual(s.volume,0)
        s.set_volume(65);s.set_mute(True)
        restored=Speaker(directory=self.temp.name)
        self.assertEqual(restored.volume,65);self.assertTrue(restored.muted)
        self.assertEqual((Path(self.temp.name)/'speaker.json').stat().st_mode&0o777,0o600)

    def test_pair_switch_route_volume_and_restore(self):
        s=self.speaker;calls=[]
        def command(args,**kwargs):
            calls.append(args)
            if args[:2]==['bluetoothctl','info']:return 'Name: New JBL\nPaired: no\nUUID: Audio Sink'
            if args==['pactl','list','short','sinks']:return '2 '+SINK+' module-bluez5-device.c'
            if args==['pactl','list','short','sink-inputs']:return '12 0 stream'
            return ''
        s.command=command;s.connect(NEW)
        self.assertEqual(self.ctx.sink,SINK)
        self.assertEqual(os.environ['POCKET_SPEAKER_ADDRESS'],NEW)
        self.assertIn(['pactl','set-sink-volume',SINK,'100%'],calls)
        self.assertIn(['pactl','move-sink-input','12',SINK],calls)
        self.assertIn(['bluetoothctl','disconnect',OLD],calls)
        self.assertTrue(any('NoInputNoOutput' in c for c in calls))
        self.assertEqual(Speaker(directory=self.temp.name).address,NEW)
        self.assertEqual(s.name,'New JBL')

    def test_invalid_or_failed_pair_does_not_replace_selected_speaker(self):
        s=self.speaker;original=s.sink
        with self.assertRaises(ValueError):s.connect('not an address')
        with patch.object(s,'command',side_effect=RuntimeError('pair failed')):
            with self.assertRaises(RuntimeError):s.connect(NEW)
        self.assertEqual(s.sink,original);self.assertEqual(self.ctx.sink,'old')

    def test_scan_lists_audio_devices_and_excludes_computer(self):
        def command(args,**kwargs):
            if args==['bluetoothctl','devices']:return 'Device '+OLD+' JBL Go 4\nDevice '+NEW+' Laptop'
            if args[:2]==['bluetoothctl','info']:
                return 'Icon: audio-card\nConnected: yes' if args[2]==OLD else 'Icon: computer'
            return ''
        self.speaker.command=command;self.speaker.scan()
        self.assertEqual([d['name'] for d in self.speaker.devices],['JBL Go 4'])

    def test_hardware_volume_changes_are_read_and_saved_without_resetting_speaker(self):
        calls=[]
        def command(args,**kwargs):
            calls.append(args)
            return 'Volume: front-left: 28898 / 44% / -21 dB' if args[1]=='get-sink-volume' else 'Mute: no'
        self.speaker.command=command;self.speaker.refresh()
        self.assertEqual(self.speaker.volume,44)
        self.assertEqual(Speaker(directory=self.temp.name).volume,44)
        self.assertFalse(any('set-sink-volume' in c for c in calls))

    def test_refresh_does_not_override_a_queued_volume_change(self):
        self.speaker.set_volume(65)
        self.speaker.command=lambda args,**kwargs:'Volume: 44%' if args[1]=='get-sink-volume' else 'Mute: no'
        self.speaker.refresh();self.assertEqual(self.speaker.volume,65)

    def test_device_controls_volume_pairing_and_mute(self):
        from pocket.apps.speaker import App
        from pocket.ui import UI
        s=self.speaker;self.ctx.ui=UI();self.ctx.speaker=s
        app=App(self.ctx);app.handle({'ok'});self.assertEqual(app.page,'volume')
        app.handle({'down'});self.assertEqual(s.volume,95)
        app.handle({'ok'});app.handle({'down'});app.handle({'ok'})
        self.assertEqual(app.page,'devices');self.assertEqual(app.render().size,(240,240))
        s.devices=[{'address':NEW,'name':'New speaker'}]
        app.handle({'down'});app.handle({'ok'})
        actions=[]
        while not s.jobs.empty():actions.append(s.jobs.get_nowait())
        self.assertIn(('connect',s.devices[0]),actions)
        app.selected=2;app.handle({'ok'});self.assertTrue(s.muted)
        self.assertEqual(app.render().size,(240,240))
