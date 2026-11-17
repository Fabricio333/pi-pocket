import asyncio,math,struct,tempfile,threading,unittest,wave
from pathlib import Path
from unittest.mock import patch
from pocket import audio_reactive as audio,led_protocol as led,celebration

class Client:
    def __init__(self):self.frames=[]
    async def write_gatt_char(self,uuid,payload,response=False):self.frames.append(payload)

def pcm(frequency=0,amplitude=.4,rate=16000):
    return struct.pack('<'+'h'*1600,*[round(32767*amplitude*math.sin(2*math.pi*frequency*i/rate)) for i in range(1600)])

class AudioReactiveTests(unittest.TestCase):
    def test_live_palette_distinguishes_bass_mids_treble(self):
        for frequency,hue in [(100,30),(700,280),(3500,190)]:
            self.assertEqual(audio.LiveFeatures().update(pcm(frequency),0)[2],hue)
    def test_silence_decays_to_off_without_gain_explosion(self):
        feature=audio.LiveFeatures();feature.update(pcm(100),0)
        for i in range(50):frame=feature.update(pcm(),i*.1)
        self.assertEqual(frame[1],0)
        self.assertFalse(frame[4])
        self.assertLess(audio.LiveFeatures().update(pcm(100,.001),0)[1],.03)
    def test_cached_pcm_analysis_and_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.wav'
            with wave.open(str(path),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(pcm(100)*10)
            frames,duration=audio.analyze(path)
            self.assertEqual(duration,1.)
            self.assertEqual(len(frames),5)
            self.assertEqual(frames[0][2],30)
            self.assertIs(frames,audio.analyze(path)[0])
            with self.assertRaises(ValueError):audio.analyze(path,100)
    def test_render_skips_late_frames_and_always_turns_off(self):
        client=Client();cancel=threading.Event()
        frames=[(i*.1,1,i*30,1000,False) for i in range(5)]
        stats=asyncio.run(audio.render(client,frames,0,0,100,cancel,clock=lambda:1))
        self.assertEqual(stats['dropped_frames'],4)
        self.assertEqual(client.frames[-1],led.power(False))
        self.assertIn(led.color(120,1000),client.frames)
        self.assertNotIn(led.color(0,1000),client.frames)
    def test_cancelled_render_does_not_flash_and_finishes_off(self):
        client=Client();cancel=threading.Event();cancel.set()
        asyncio.run(audio.render(client,[(0,1,30,1000,True)],0,0,100,cancel))
        self.assertEqual(client.frames,[led.power(False)])
    def test_render_uses_monotonic_delay(self):
        client=Client();now=[0]
        async def sleep(seconds):now[0]+=seconds
        asyncio.run(audio.render(client,[(0,1,30,1000,False)],0,.15,100,threading.Event(),clock=lambda:now[0],sleep=sleep))
        self.assertGreaterEqual(now[0],.15)
    def test_live_render_caps_brightness_and_deduplicates_packets(self):
        client=Client();renderer=audio.LiveRenderer(client,100)
        frame=(0,1,30,1000,False)
        asyncio.run(renderer.apply(frame));count=len(client.frames)
        asyncio.run(renderer.apply(frame))
        self.assertEqual(len(client.frames),count)
        self.assertIn(led.brightness(100),client.frames)
        self.assertNotIn(led.brightness(1000),client.frames)
        asyncio.run(renderer.apply((1,0,30,1000,False)))
        self.assertEqual(client.frames[-1],led.power(False))
    def test_manual_command_cancels_active_reactive_job(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict('os.environ',{'POCKET_STATE_DIR':directory}):
            worker=celebration.LedWorker('test');worker.active_cancel=threading.Event();worker.live_enabled=True
            worker.command('off')
            self.assertTrue(worker.active_cancel.is_set())
            self.assertFalse(worker.live_enabled)
            self.assertEqual(worker.jobs.get()['generation'],worker.generation)

    def test_monitor_stops_capture_and_lights_on_cancel(self):
        cancel=threading.Event()
        class Source:
            async def readexactly(self,size):
                await asyncio.sleep(.01)
                return pcm(100)
        class Process:
            stdout=Source();returncode=None;terminated=False
            def terminate(self):self.terminated=True;self.returncode=0
            async def wait(self):return self.returncode
        class CancellingClient(Client):
            async def write_gatt_char(self,uuid,payload,response=False):
                await super().write_gatt_char(uuid,payload,response)
                if payload==led.power(True):cancel.set()
        process=Process();client=CancellingClient()
        async def run():
            with patch.object(asyncio,'create_subprocess_exec',return_value=process):
                await asyncio.wait_for(audio.monitor(client,'speaker',100,0,cancel),2)
        asyncio.run(run())
        self.assertTrue(process.terminated)
        self.assertEqual(client.frames[-1],led.power(False))

    def test_pcm_render_failure_still_attempts_off(self):
        class FailingClient(Client):
            async def write_gatt_char(self,uuid,payload,response=False):
                self.frames.append(payload)
                if payload[1]==4:raise RuntimeError('BLE failure')
        client=FailingClient()
        with self.assertRaises(RuntimeError):
            asyncio.run(audio.render(client,[(0,1,30,1000,False)],0,0,100,threading.Event()))
        self.assertEqual(client.frames[-1],led.power(False))

    def test_low_energy_wake_uses_visible_brightness_and_paced_acknowledged_writes(self):
        calls=[];pauses=[]
        class AcknowledgedClient:
            async def write_gatt_char(self,uuid,payload,response=False):calls.append((payload,response))
        async def pause(seconds):pauses.append(seconds)
        renderer=audio.LiveRenderer(AcknowledgedClient(),100,sleep=pause)
        asyncio.run(renderer.apply((0,.04,30,1000,False)))
        self.assertEqual([x[0][1] for x in calls],[4,5,1])
        self.assertTrue(all(response for _,response in calls))
        self.assertTrue(all(seconds>=.035 for seconds in pauses))
        self.assertEqual(calls[1][0],led.brightness(52))
        self.assertEqual(calls[-1][0],led.power(True))

    def test_music_uses_multicolor_motion_and_beats_change_brightness(self):
        client=Client()
        async def pause(seconds):pass
        renderer=audio.MusicRenderer(client,100,sleep=pause)
        asyncio.run(renderer.apply((0,.3,30,1000,False)))
        baseline=renderer.previous[1]
        asyncio.run(renderer.apply((.1,.3,190,1000,True)))
        self.assertGreater(renderer.previous[1],baseline)
        self.assertIn(led.effect('rainbow-tail'),client.frames)
        self.assertFalse(any(packet[1]==4 for packet in client.frames))
        asyncio.run(renderer.apply((.4,.3,280,1000,False)))
        self.assertLess(renderer.previous[1],90)

    def test_music_silence_dims_before_poweroff_and_keeps_effect_between_beats(self):
        client=Client()
        async def pause(seconds):pass
        renderer=audio.MusicRenderer(client,100,sleep=pause)
        asyncio.run(renderer.apply((0,.5,30,1000,True)))
        initial=sum(packet[1]==6 for packet in client.frames)
        asyncio.run(renderer.apply((.1,0,30,1000,False)))
        self.assertEqual(client.frames[-1],led.brightness(3))
        asyncio.run(renderer.apply((.3,.5,30,1000,True)))
        self.assertEqual(sum(packet[1]==6 for packet in client.frames),initial)
        asyncio.run(renderer.apply((2,0,30,1000,False)))
        self.assertEqual(client.frames[-1],led.power(False))

    def test_music_effect_changes_are_bounded_and_remain_in_documented_catalog(self):
        client=Client()
        async def pause(seconds):pass
        renderer=audio.MusicRenderer(client,100,sleep=pause)
        for beat in range(1,33):
            asyncio.run(renderer.apply((beat,.4,30,1000,True)))
        effects=[packet for packet in client.frames if packet[1]==6]
        self.assertEqual(effects,[led.effect('rainbow-tail'),led.effect('rainbow-flow'),led.effect('rainbow-running')])

    def test_beat_build_advances_brightness_then_changes_color(self):
        client=Client()
        async def pause(seconds):pass
        renderer=audio.MusicRenderer(client,100,sleep=pause,effect='beat-build',beats_per_color=4)
        levels=[]
        for beat in range(1,6):
            asyncio.run(renderer.apply((beat,.5,30,1000,True)))
            levels.append(renderer.previous[1])
        self.assertEqual(levels[:4],sorted(levels[:4]))
        self.assertLess(levels[4],levels[3])
        colors=[p for p in client.frames if p[1]==4]
        self.assertEqual(colors,[led.color(0,1000),led.color(30,1000)])
        self.assertFalse(any(p[1]==6 for p in client.frames))

    def test_beat_tail_holds_one_color_for_four_beats(self):
        client=Client()
        async def pause(seconds):pass
        renderer=audio.MusicRenderer(client,100,sleep=pause,effect='beat-tail',beats_per_color=4)
        for beat in range(1,6):asyncio.run(renderer.apply((beat,.5,30,1000,True)))
        self.assertEqual([p for p in client.frames if p[1]==6],[led.effect('red-tailing'),led.effect('yellow-tailing')])
