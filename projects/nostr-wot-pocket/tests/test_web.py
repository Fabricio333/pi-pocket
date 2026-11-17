import json, tempfile,threading,unittest
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pocket.web import handler
from pocket.settings import DEFAULTS

class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),handler(self.path))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
    def request(self,method,path,body=None,headers=None):
        connection=HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,
                           headers={'Content-Type':'application/json',**(headers or {})})
        response=connection.getresponse();status=response.status;data=response.read();connection.close()
        return status,data
    def test_page_assets_and_live_state_are_served_without_private_invoice_state(self):
        for path in ['/','/app.js','/style.css','/api/state']:
            self.assertEqual(self.request('GET',path)[0],200)
        (self.path/'server-status.json').write_text(json.dumps({'running':True,'qr':'PRIVATE-PATH','last_receipt':'PRIVATE-RECEIPT'}))
        _,data=self.request('GET','/api/state')
        self.assertNotIn(b'PRIVATE-',data)
        self.assertEqual(self.request('GET','/../server-status.json')[0],404)
    def test_preview_and_save_queue_distinct_actions(self):
        for endpoint,action in [('/api/preview','preview'),('/api/settings','settings')]:
            status,_=self.request('POST',endpoint,DEFAULTS)
            self.assertEqual(status,202)
            commands=[json.loads(p.read_text()) for p in (self.path/'commands').glob('*.json')]
            self.assertIn(action,[command['action'] for command in commands])
    def test_invalid_controls_and_cross_origin_requests_are_rejected(self):
        self.assertEqual(self.request('POST','/api/settings',dict(DEFAULTS,brightness=1001))[0],400)
        self.assertEqual(self.request('POST','/api/command',{'action':'paid'})[0],400)
        self.assertEqual(self.request('POST','/api/command',{'action':'test','value':'zap'})[0],400)
        self.assertEqual(self.request('POST','/api/command',{'action':'off'}, {'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('GET','/',headers={'Host':'evil.example'})[0],403)
