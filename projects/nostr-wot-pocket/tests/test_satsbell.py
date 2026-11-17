import base64
import json
import queue
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from coincurve import PublicKeyXOnly
from pocket.satsbell import Bell, Provider, Store, compact, eligible, sha

def payment(**kwargs):
    return {'amount':21000,'status':'success','extra':{'lnaddress':'123456@example.com'},
            'payment_hash':'a'*64, **kwargs}

class BellTests(unittest.TestCase):
    def test_default_provider_normalizes_only_known_address_aliases(self):
        provider=Provider('01'*32)
        provider.request=lambda *a,**kw:{'address':'682474@nostrwot.com'}
        self.assertEqual(provider.address(),'682474@zaps.nostr-wot.com')
        self.assertTrue(eligible(payment(extra={'lnaddress':'682474@zaps.nostr-wot.com'}),provider.address()))
        self.assertFalse(eligible(payment(extra={'lnaddress':'999999@zaps.nostr-wot.com'}),provider.address()))
        provider.request=lambda *a,**kw:{'address':'682474@unrelated.example'}
        self.assertEqual(provider.address(),'682474@unrelated.example')
        provider=Provider('01'*32,origin='https://custom.example')
        provider.request=lambda *a,**kw:{'address':'682474@nostrwot.com'}
        self.assertEqual(provider.address(),'682474@nostrwot.com')

    def test_sound_uses_existing_asset_and_reconnects_missing_sink(self):
        from pocket.satsbell import play_sound
        with patch('pocket.satsbell.subprocess.run',return_value=SimpleNamespace(stdout='')) as run:
            play_sound('bluez_sink.90_F2_60_5E_89_28.a2dp_sink')
            calls=[c.args[0] for c in run.call_args_list]
            self.assertEqual(calls[1],['bluetoothctl','--timeout','10','connect','90:F2:60:5E:89:28'])
            self.assertTrue(calls[2][-1].endswith('assets/audio/zap-announcement.wav'))
            from pathlib import Path
            self.assertTrue(Path(calls[2][-1]).is_file())

    def test_eligibility_boundaries_and_attribution(self):
        self.assertTrue(eligible(payment(),'123456@example.com'))
        self.assertTrue(eligible(payment(amount=22000),'123456@example.com'))
        for change in ({'amount':20999},{'amount':-21000},{'amount':21000.0},{'status':'pending'},
                       {'extra':{}},{'payment_hash':'invalid'}):
            self.assertFalse(eligible(payment(**change),'123456@example.com'))
        self.assertFalse(eligible(payment(),'999999@example.com'))

    def test_identity_and_receipts_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);secret=store.get('secret')
            self.assertTrue(store.receipt(payment(),'123456@example.com',False))
            self.assertFalse(store.receipt(payment(),'123456@example.com',False))
            store.db.close()
            store=Store(directory)
            self.assertEqual(store.get('secret'),secret)
            self.assertFalse(store.receipt(payment(),'123456@example.com',False))
            self.assertEqual(len(store.history()),1)

    def test_commit_before_ring_offline_baseline_and_release_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            events=queue.Queue();bell=Bell(directory,events)
            bell.store.set('wallet',{'inkey':'test'});bell.address='123456@example.com';bell.armed=True
            bell.provider.history=lambda key:[payment()]
            bell.scan(True);self.assertTrue(events.empty())
            bell.scan(False);self.assertTrue(events.empty())
            bell.provider.history=lambda key:[payment(payment_hash='b'*64)]
            bell.scan(False)
            self.assertEqual(events.get_nowait()[0],'satsbell-paid')
            self.assertEqual(len(bell.store.history()),2)
            bell.action('release');self.assertFalse(bell.armed)
            bell.provider.history=lambda key:[payment(payment_hash='c'*64)]
            bell.scan(False);self.assertTrue(events.empty())
            bell.armed=True;bell.store.set('release',False)
            bell.provider.history=lambda key:[payment(payment_hash='d'*64)]
            with patch.object(bell.store,'receipt',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):bell.scan(False)
            self.assertTrue(events.empty())

    def test_exact_body_bound_signature(self):
        provider=Provider('01'*32);calls=[]
        def request(path,body=None,headers=None):
            calls.append((path,body,headers))
            return {'version':2,'challenge':'c'*64,'transactionToken':'d'*64,'expiresAt':int(time.time())+60} if len(calls)==1 else {'ok':True}
        provider.request=request
        provider.operation('/api/v2/provision',{'name':'Sats Bell'})
        challenge=json.loads(calls[0][1]);raw=calls[1][1];headers=calls[1][2]
        event=json.loads(base64.b64decode(headers['Authorization'].split()[1]))
        self.assertEqual(challenge['payload'],sha(raw))
        self.assertIn(['transaction',sha('d'*64)],event['tags'])
        import hashlib
        digest=hashlib.sha256(compact([0,event['pubkey'],event['created_at'],27235,event['tags'],'']).encode()).digest()
        self.assertTrue(PublicKeyXOnly(bytes.fromhex(event['pubkey'])).verify(bytes.fromhex(event['sig']),digest))

    def test_bad_challenges_and_history_limit_fail_closed(self):
        provider=Provider('01'*32)
        provider.request=lambda *a,**kw:{'version':2,'expiresAt':1}
        with self.assertRaises(ValueError):provider.operation('/api/v2/provision',{})
        provider.request=lambda *a,**kw:[payment()]*10
        with self.assertRaisesRegex(ValueError,'scan limit'):provider.history('key')
        provider.request=lambda *a,**kw:{'data':[]}
        with self.assertRaises(ValueError):provider.history('key')

    def test_corrupt_database_does_not_create_new_identity(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'satsbell.sqlite3';path.write_bytes(b'broken storage')
            with self.assertRaises(Exception):Store(directory)
            self.assertEqual(path.read_bytes(),b'broken storage')

    def test_empty_or_missing_saved_identity_never_provisions_a_replacement(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'satsbell.sqlite3';path.touch()
            with self.assertRaisesRegex(ValueError,'storage is empty'):Store(directory)
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            with store.db:store.db.execute("DELETE FROM settings WHERE key='secret'")
            store.db.close()
            with self.assertRaisesRegex(ValueError,'identity is missing'):Store(directory)

    def test_screens_and_release_confirmation(self):
        from pocket.apps.satsbell import App
        from pocket.ui import UI
        with tempfile.TemporaryDirectory() as directory:
            bell=Bell(directory,queue.Queue());ctx=SimpleNamespace(ui=UI(),satsbell=bell)
            app=App(ctx)
            for page in ('menu','history','confirm'):
                app.page=page;self.assertEqual(app.render().size,(240,240))
            app.handle({'down'});self.assertFalse(bell.store.get('release',False))
            app.page='confirm';app.handle({'up'});self.assertTrue(bell.store.get('release'))
            bell.address='123456@example.com';app.selected=1;app.handle({'ok'})
            self.assertEqual(app.render().size,(240,240))
            self.assertEqual(app.render().getpixel((0,0)),(255,255,255))

    def test_wifi_page_requires_active_session_and_setup_password(self):
        from pocket.wifi_setup import Setup
        from http.server import ThreadingHTTPServer
        import threading,urllib.request,urllib.error
        setup=Setup();server=ThreadingHTTPServer(('127.0.0.1',0),setup.handler())
        threading.Thread(target=server.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url)
            setup.session={'expires':time.time()+60,'token':'secret'}
            self.assertIn(b'Connect SatsBell',urllib.request.urlopen(url).read())
            req=urllib.request.Request(url+'/connect',data=b'{"token":"wrong","ssid":"wifi"}')
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(req)
        finally:server.shutdown();server.server_close()

    def test_wifi_failed_join_restores_hotspot_and_removes_password_file(self):
        import importlib.machinery,importlib.util,io
        from pathlib import Path
        loader=importlib.machinery.SourceFileLoader('wifi_helper',str(Path(__file__).resolve().parents[1]/'ops/pocket-wifi'))
        spec=importlib.util.spec_from_loader(loader.name,loader)
        helper=importlib.util.module_from_spec(spec);loader.exec_module(helper)
        calls=[]
        def nm(*args,**kwargs):
            calls.append(args)
            if args[:2]==('connection','up') and args[2]!='SatsBell-Setup':raise RuntimeError('bad password')
            return ''
        with tempfile.TemporaryDirectory() as directory:
            helper.STATE=Path(directory)
            with patch.object(helper,'nm',side_effect=nm),patch.object(helper.sys,'stdin',io.StringIO('{"ssid":"Home","password":"incorrect"}')):
                with self.assertRaises(RuntimeError):helper.connect()
            self.assertIn(('connection','up','SatsBell-Setup'),calls)
            self.assertFalse((Path(directory)/'password').exists())

    def test_wifi_active_setup_does_not_replace_recovery_connection(self):
        from pocket.wifi_setup import Setup
        setup=Setup();setup.session={'expires':time.time()+600}
        with patch('pocket.wifi_setup.subprocess.run') as run:
            setup.open();run.assert_not_called()

    def test_wifi_qr_encodes_credentials_and_cycles_to_setup_url(self):
        from pocket.apps.wifi import App,wifi_payload
        from pocket.ui import UI
        self.assertEqual(wifi_payload('SatsBell-1234','012345abcdef'),
                         'WIFI:T:WPA;S:SatsBell-1234;P:012345abcdef;;')
        self.assertEqual(wifi_payload('a;b:c','x\\y"z,'),
                         'WIFI:T:WPA;S:a\\;b\\:c;P:x\\\\y\\"z\\,;;')
        session={'ssid':'SatsBell-1234','password':'012345abcdef',
                 'url':'http://192.168.4.1:8788','expires':time.time()+600}
        setup=SimpleNamespace(session=session,error='',open=lambda:self.fail('Hotspot should not restart'))
        app=App(SimpleNamespace(ui=UI(),wifi_setup=setup))
        for page in range(3):
            self.assertEqual(app.page,page)
            frame=app.render();self.assertEqual(frame.size,(240,240))
            if page<2:
                self.assertEqual(frame.getpixel((22,25)),(255,255,255))
                self.assertEqual({color for count,color in app.qrs[page].getcolors()}, {(0,0,0),(255,255,255)})
            app.handle({'ok'})
        self.assertEqual(app.page,0)

if __name__=='__main__':unittest.main()
