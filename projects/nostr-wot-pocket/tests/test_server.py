import json,queue,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from pocket.server import Server,export_qr,write_json

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name);self.commands=[];self.played=[]
        self.backend=SimpleNamespace(create_invoice=lambda events:'lnbc-test',invoice_address=lambda invoice:'fallback@example.com')
        self.worker=SimpleNamespace(command=lambda *args:self.commands.append(args))
        self.server=Server(self.path,queue.Queue(),self.worker,self.backend,lambda **kwargs:self.played.append(kwargs))
    def test_control_commands_do_not_claim_payment(self):
        for action,expected in [('live','audio-live'),('off','off'),('red','steady')]:
            self.server.handle({'action':action});self.assertEqual(self.commands[-1],(expected,))
        self.assertNotIn('last_receipt',self.server.state)
        with self.assertRaises(ValueError):self.server.handle({'action':'paid'})
    def test_repeated_previews_have_separate_cancel_tokens(self):
        class ImmediateThread:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):self.target()
        def play(**kwargs):self.played.append(kwargs);kwargs['cancel'].set()
        self.server.celebrate=play
        with patch('pocket.server.threading.Thread',ImmediateThread):
            self.server.handle({'action':'test','value':'demo'});self.server.handle({'action':'test','value':'demo'})
        self.assertEqual(len(self.played),2)
        self.assertIsNot(self.played[0]['cancel'],self.played[1]['cancel'])
        self.assertFalse(self.server.cancel.is_set())
    def test_invoice_request_queues_result_and_status_exports_private_qr(self):
        self.server.handle({'action':'invoice'})
        kind,invoice=self.server.events.get(timeout=2)
        self.assertEqual(kind,'invoice')
        self.server.event(kind,invoice);self.server.status()
        self.assertTrue((self.path/'current-invoice.png').exists())
        self.assertEqual((self.path/'current-invoice.png').stat().st_mode&0o777,0o600)
        status=json.loads((self.path/'server-status.json').read_text())
        self.assertEqual(status['invoice_address'],'fallback@example.com')
        self.assertNotIn('lnbc-test',json.dumps(status))
    def test_paid_receipt_clears_only_its_invoice_and_triggers_one_celebration(self):
        self.server.invoice='invoice';self.server.state['qr']='current-invoice.png'
        (self.path/'current-invoice.png').write_text('QR')
        with patch.object(self.server,'play') as play:
            self.server.event('paid',{'invoice':'invoice','receipt':'signed-receipt-id'})
        play.assert_called_once_with('zap-announcement.wav')
        self.assertIsNone(self.server.invoice)
        self.assertFalse((self.path/'current-invoice.png').exists())
        self.assertEqual(self.server.state['last_receipt'],'signed-receipt-id')
    def test_shutdown_cancels_audio_and_lights(self):
        token=threading.Event();self.server.playbacks.append(token)
        self.server.close()
        self.assertTrue(token.is_set());self.assertEqual(self.commands[-1],('off',))
        self.assertFalse(json.loads((self.path/'server-status.json').read_text())['running'])

    def test_live_preview_does_not_overwrite_saved_settings(self):
        from pocket.settings import DEFAULTS
        self.worker.configure=lambda value:None
        self.server.handle({'action':'preview','value':dict(DEFAULTS,brightness=200)})
        self.assertEqual(self.server.settings['brightness'],200)
        self.assertEqual(json.loads((self.path/'calibration.json').read_text())['brightness'],100)
        self.server.handle({'action':'settings','value':self.server.settings})
        self.assertEqual(json.loads((self.path/'calibration.json').read_text())['brightness'],200)
        self.server.handle({'action':'restore'})
        self.assertEqual(self.server.settings['brightness'],100)
        self.assertEqual(json.loads((self.path/'calibration.json').read_text())['brightness'],200)

    def test_muting_payment_sound_keeps_payment_confirmation(self):
        self.server.settings['payment_sound']=False
        with patch.object(self.server,'play') as play:
            self.server.event('paid',{'invoice':'old-invoice','receipt':'real-verified-receipt'})
        play.assert_not_called()
        self.assertEqual(self.server.state['last_receipt'],'real-verified-receipt')
