import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pocket.ringtones import Ringtones

class RingtoneTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);sounds=self.directory/'ringtones';sounds.mkdir()
        self.catalog=[{'id':str(i),'title':'Sound '+str(i),'file':str(i)+'.wav'} for i in range(5)]
        for t in self.catalog:(sounds/t['file']).write_bytes(b'test')
        (sounds/'catalog.json').write_text(json.dumps(self.catalog))
        self.pool=Ringtones(self.directory)

    def test_shuffle_has_no_repeats_and_persists_across_restart(self):
        first=[self.pool.next()['id'] for _ in range(2)]
        restarted=Ringtones(self.directory)
        first += [restarted.next()['id'] for _ in range(3)]
        self.assertEqual(set(first),{str(i) for i in range(5)})
        second=[restarted.next()['id'] for _ in range(5)]
        self.assertEqual(len(set(second)),5)
        self.assertNotEqual(first[-1],second[0])

    def test_ordered_mode_wraps_and_mode_persists(self):
        self.pool.set_mode('ordered')
        self.assertEqual([self.pool.next()['id'] for _ in range(7)],['0','1','2','3','4','0','1'])
        self.assertEqual(Ringtones(self.directory).mode,'ordered')
        self.assertEqual(Ringtones(self.directory).next()['id'],'2')
        with self.assertRaises(ValueError):self.pool.set_mode('invalid')

    def test_removed_files_are_skipped_and_empty_pool_has_fallback(self):
        for t in self.catalog[1:]:(self.directory/'ringtones'/t['file']).unlink()
        self.assertEqual(self.pool.next()['id'],'0')
        (self.directory/'ringtones/0.wav').unlink()
        self.assertIsNone(self.pool.next())

    def test_playback_selects_cached_clip_and_returns_its_title(self):
        from pocket.satsbell import play_sound
        track=self.pool.next()
        with patch('pocket.ringtones.Ringtones.next',return_value=track),patch('pocket.satsbell.subprocess.run') as run:
            self.assertEqual(play_sound('@DEFAULT_SINK@'),track['title'])
            self.assertEqual(run.call_args.args[0][-1],str(track['path']))

    def test_sound_mode_is_selectable_from_physical_button_menu(self):
        from pocket.apps.satsbell import App
        from pocket.ui import UI
        from types import SimpleNamespace
        bell=SimpleNamespace(address='123456@nostrwot.com',error='',status='Ready to ring')
        with patch('pocket.apps.satsbell.Ringtones',return_value=self.pool):
            app=App(SimpleNamespace(satsbell=bell,ui=UI()))
            app.handle({'up'});self.assertEqual(app.selected,5)
            app.handle({'ok'});self.assertEqual(app.page,'sounds')
            app.handle({'ok'});self.assertEqual(self.pool.mode,'ordered')
            self.assertEqual(app.render().size,(240,240))
            app.handle({'ok'});self.assertEqual(self.pool.mode,'shuffle')

    def test_play_all_is_ordered_and_does_not_advance_payment_rotation(self):
        from pocket.ringtones import Preview
        preview=Preview(self.pool);played=[]
        with patch('pocket.satsbell.play_sound',side_effect=lambda sink,track,cancel:played.append(track['id'])):
            preview.start('@DEFAULT_SINK@');preview.thread.join(timeout=4)
        self.assertFalse(preview.playing)
        self.assertEqual(played,['0','1','2','3','4'])
        self.pool.set_mode('ordered');self.assertEqual(self.pool.next()['id'],'0')

    def test_preview_stops_between_clips(self):
        from pocket.ringtones import Preview
        preview=Preview(self.pool);played=[]
        def stop(sink,track,cancel):played.append(track['id']);preview.stop()
        with patch('pocket.satsbell.play_sound',side_effect=stop):
            preview.start('@DEFAULT_SINK@');preview.thread.join(timeout=2)
        self.assertEqual(played,['0'])

    def test_regular_ring_interrupts_preview(self):
        from pocket.satsbell import play_sound
        with patch('pocket.ringtones.stop_preview') as stop,patch('pocket.ringtones.Ringtones.next',return_value=None),patch('pocket.satsbell.subprocess.run'):
            play_sound('@DEFAULT_SINK@')
        stop.assert_called_once()

    def test_cancel_terminates_in_progress_preview_audio(self):
        from pocket.satsbell import play_sound
        from unittest.mock import Mock
        cancel=Mock();cancel.is_set.return_value=False;cancel.wait.return_value=True
        player=Mock();player.poll.return_value=None
        track=self.pool.next()
        with patch('pocket.satsbell.subprocess.Popen',return_value=player):
            self.assertIsNone(play_sound('@DEFAULT_SINK@',track=track,cancel=cancel))
        player.terminate.assert_called_once();player.wait.assert_called_once_with(timeout=2)
