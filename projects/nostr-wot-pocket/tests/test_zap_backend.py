import hashlib
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
import bolt11
from coincurve import PrivateKey
from pocket import zap_backend as backend


def signed(event, key):
    event=dict(event, pubkey=key.public_key_xonly.format().hex())
    digest=backend.event_hash(event)
    return dict(event,id=digest.hex(),sig=key.sign_schnorr(digest).hex())


def invoice_for(raw,amount=21000):
    return bolt11.encode(bolt11.Bolt11(currency='bc',date=int(time.time()),
        amount_msat=bolt11.MilliSatoshi(amount),tags=bolt11.Tags([
            bolt11.Tag(bolt11.TagChar.payment_hash,'11'*32),
            bolt11.Tag(bolt11.TagChar.payment_secret,'22'*32),
            bolt11.Tag(bolt11.TagChar.description_hash,hashlib.sha256(raw.encode()).hexdigest()),
        ])),private_key='33'*32)


class ZapBackendTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for name,value in [('pending',{}),('STATE',Path(self.directory.name)/'state.json')]:
            patcher=patch.object(backend,name,value);patcher.start();self.addCleanup(patcher.stop)
        self.events=queue.Queue()

    def test_primary_is_always_first_and_success_skips_fallback(self):
        with patch.object(backend,'start'),patch.object(backend,'request_invoice',return_value='invoice') as call:
            self.assertEqual(backend.create_invoice(self.events),'invoice')
        self.assertEqual(call.call_args_list[0].args[1:],(backend.ENDPOINT,backend.PROVIDER,backend.PRIMARY_ADDRESS))
        self.assertEqual(call.call_count,1)

    def test_network_and_server_failures_use_fallback(self):
        failures=[URLError('DNS'),TimeoutError(),ConnectionError()]+[
            HTTPError(backend.ENDPOINT,status,'failure',{},None) for status in (408,429,500,502,503)]
        for failure in failures:
            with self.subTest(failure=failure),patch.object(backend,'start'),patch.object(backend,'request_invoice',side_effect=[failure,'fallback']) as call:
                self.assertEqual(backend.create_invoice(self.events),'fallback')
                self.assertEqual(call.call_args_list[1].args[1:],(backend.FALLBACK_ENDPOINT,backend.FALLBACK_PROVIDER,backend.FALLBACK_ADDRESS))

    def test_identity_invalid_invoice_and_client_errors_fail_closed(self):
        for failure in [ValueError('Invalid invoice'),RuntimeError('Identity changed'),HTTPError(backend.ENDPOINT,403,'Forbidden',{},None)]:
            with self.subTest(failure=failure),patch.object(backend,'start'),patch.object(backend,'request_invoice',side_effect=failure) as call:
                with self.assertRaises(type(failure)):backend.create_invoice(self.events)
                self.assertEqual(call.call_count,1)

    def test_signed_invoice_is_saved_with_its_provider_and_address(self):
        def get(url):
            if url==backend.FALLBACK_ENDPOINT:
                return dict(allowsNostr=True,nostrPubkey=backend.FALLBACK_PROVIDER,minSendable=1000,maxSendable=100000,callback='https://provider.example/callback?token=keep%2Bme')
            args=parse_qs(urlsplit(url).query)
            self.assertEqual(args['amount'],['21000'])
            self.assertEqual(args['token'],['keep+me'])
            import json
            self.assertTrue(backend.valid_event(json.loads(args['nostr'][0])))
            return {'pr':invoice_for(args['nostr'][0])}
        with patch.object(backend,'get',side_effect=get):
            invoice=backend.request_invoice(self.events,backend.FALLBACK_ENDPOINT,backend.FALLBACK_PROVIDER,backend.FALLBACK_ADDRESS)
        self.assertEqual(backend.invoice_address(invoice),backend.FALLBACK_ADDRESS)
        self.assertEqual(next(iter(backend.pending.values()))['provider'],backend.FALLBACK_PROVIDER)
        self.assertTrue(backend.STATE.exists())

    def test_fallback_identity_must_match_pin(self):
        with patch.object(backend,'get',return_value=dict(allowsNostr=True,nostrPubkey=backend.PROVIDER)):
            with self.assertRaisesRegex(RuntimeError,'identity'):
                backend.request_invoice(self.events,backend.FALLBACK_ENDPOINT,backend.FALLBACK_PROVIDER,backend.FALLBACK_ADDRESS)
        self.assertFalse(backend.pending)

    def test_receipts_are_bound_to_the_exact_invoice_and_provider(self):
        request=signed(dict(kind=9734,created_at=int(time.time()),content='',tags=[['p',backend.RECIPIENT],['amount','21000']]),PrivateKey())
        raw=backend.dumps(request);invoice=invoice_for(raw);key=PrivateKey()
        record=dict(invoice=invoice,request=request,provider=key.public_key_xonly.format().hex(),paid=False)
        event=signed(dict(kind=9735,created_at=int(time.time()),content='',tags=[['p',backend.RECIPIENT],['bolt11',invoice],['description',raw]]),key)
        self.assertTrue(backend.validate_receipt(event,record))
        self.assertFalse(backend.validate_receipt(event,dict(record,provider=backend.PROVIDER)))
        wrong=signed(dict(event,tags=[['p',backend.RECIPIENT],['bolt11',invoice_for(raw,22000)],['description',raw]]),key)
        self.assertFalse(backend.validate_receipt(wrong,record))
        backend.pending['test']=record
        with patch.object(backend,'save'):
            backend.process_receipt(event,self.events);backend.process_receipt(event,self.events)
        self.assertEqual(self.events.qsize(),1)

    def test_wos_receipt_relay_is_requested_and_watched(self):
        self.assertIn('wss://relay.ditto.pub',backend.RELAYS)
        sockets=[]
        class StopWatch(BaseException):pass
        class Socket:
            def send(self,raw):
                import json
                sockets.append(json.loads(raw))
            def recv(self):raise StopWatch()
            def close(self):pass
        with patch.object(backend.websocket,'create_connection',return_value=Socket()):
            with self.assertRaises(StopWatch):backend.watch('wss://relay.ditto.pub',self.events)
        self.assertIn(backend.FALLBACK_PROVIDER,sockets[0][2]['authors'])
        self.assertEqual(sockets[0][2]['#p'],[backend.RECIPIENT])
