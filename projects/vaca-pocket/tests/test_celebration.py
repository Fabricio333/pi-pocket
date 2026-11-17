import asyncio, unittest
from unittest.mock import patch
from pocket import celebration,led_protocol as led

class FakeClient:
    def __init__(self,fail_once=False):self.frames=[];self.fail_once=fail_once
    async def write_gatt_char(self,uuid,payload,response=False):
        self.frames.append(payload)
        if self.fail_once and payload==led.effect('yellow-running'):
            self.fail_once=False;raise RuntimeError('temporary write failure')

async def no_sleep(seconds):pass

class CelebrationTests(unittest.TestCase):
    def test_pattern_starts_max_white_then_colors_and_finishes_off(self):
        client=FakeClient();asyncio.run(celebration.light_pattern(client,100,no_sleep))
        self.assertIn(led.effect('yellow-running'),client.frames)
        self.assertIn(led.color(30,1000),client.frames)
        self.assertIn(led.color(60,1000),client.frames)
        self.assertIn(led.color(0,0),client.frames)
        white=client.frames.index(led.color(0,0))
        self.assertEqual(client.frames[white+1],led.brightness(1000))
        levels=[p for p in client.frames if p[1]==5]
        self.assertEqual(levels.count(led.brightness(1000)),1)
        self.assertEqual(client.frames[-2:],[led.brightness(100),led.power(False)])
        self.assertFalse(any(p[1]==3 for p in client.frames))

    def test_restore_is_attempted_after_effect_error(self):
        client=FakeClient(fail_once=True)
        with self.assertRaises(RuntimeError):asyncio.run(celebration.light_pattern(client,100,no_sleep))
        self.assertEqual(client.frames[-2:],[led.brightness(100),led.power(False)])

    def test_half_probe_is_bounded_and_finishes_off(self):
        client=FakeClient();asyncio.run(celebration.half_strip_probe(client,100,no_sleep))
        self.assertIn(led.count_probe(150),client.frames)
        self.assertEqual(client.frames[-1],led.power(False))

    def test_audio_and_leds_share_timeline_and_cancel_together(self):
        import threading
        order=[];cancel=threading.Event()
        class Worker:
            ready=threading.Event()
            def reactive(self,frames,start,duration,token):
                order.append('lights');self.token=token
                self.start=start
        class Player:
            returncode=0
            def poll(self):return 0
            def wait(self,timeout):pass
        worker=Worker();worker.ready.set()
        def spawn(*args,**kwargs):order.append('audio');return Player()
        with patch.object(celebration,'prepare',return_value=worker),patch('pocket.audio_reactive.analyze',return_value=(((0,1,30,1000,False),),1.)),patch.object(celebration.subprocess,'Popen',side_effect=spawn):
            celebration.celebrate(cancel)
        self.assertEqual(order,['audio','lights'])
        self.assertIs(worker.token,cancel)
        self.assertTrue(cancel.is_set())

if __name__=='__main__':unittest.main()
