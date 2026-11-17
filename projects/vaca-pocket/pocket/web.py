"""LAN-only calibration dashboard. Commands are queued for the existing LED owner."""
import json
import os
from pathlib import Path
import socket
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from uuid import uuid4
from .server import state_directory,write_json
from .settings import DEFAULTS,EFFECTS,validate
from .brand import SVG
ASSETS=Path(__file__).parent/'web_assets'

def read_json(path,default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def handler(directory):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,status,data,content_type='application/json'):
            body=json.dumps(data).encode() if content_type=='application/json' else data
            self.send_response(status);self.send_header('Content-Type',content_type)
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def valid_host(self):
            host=urlsplit('//'+self.headers.get('Host','')).hostname
            allowed={'localhost','127.0.0.1','::1',socket.gethostname(),socket.gethostname()+'.local'}
            allowed.update(os.environ.get('POCKET_WEB_ALLOWED_HOSTS','192.168.0.148').split(','))
            return host in allowed
        def do_GET(self):
            if not self.valid_host():return self.respond(403,{'error':'Unknown host'})
            path=urlsplit(self.path).path
            if path=='/brand.svg':return self.respond(200,SVG.encode(),'image/svg+xml')
            if path=='/api/state':
                daemon=read_json(directory/'server-status.json',{})
                led=read_json(directory/'led-status.json',{})
                settings=daemon.get('calibration',read_json(directory/'calibration.json',dict(DEFAULTS)))
                return self.respond(200,{'online':bool(daemon.get('running') and time.time()-daemon.get('at',0)<20),
                    'led':led,'settings':settings,'saved_settings':daemon.get('saved_calibration',settings),'effects':EFFECTS,'error':daemon.get('error')})
            files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if path not in files:return self.respond(404,{'error':'Not found'})
            name,content_type=files[path]
            return self.respond(200,(ASSETS/name).read_bytes(),content_type)
        def do_POST(self):
            if not self.valid_host():return self.respond(403,{'error':'Unknown host'})
            origin=self.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=self.headers.get('Host'):
                return self.respond(403,{'error':'Use the controls on this page'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                return self.respond(415,{'error':'JSON required'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:raise ValueError('Invalid request size')
                value=json.loads(self.rfile.read(size))
                if self.path in ('/api/settings','/api/preview'):command={'action':'settings' if self.path=='/api/settings' else 'preview','value':validate(value)}
                elif self.path=='/api/command':
                    if not isinstance(value,dict):raise ValueError('Invalid command')
                    action=value.get('action');track=value.get('value')
                    if action not in ('live','off','red','restore','test'):raise ValueError('Unknown command')
                    if action=='test' and track not in ('click','demo','thunder'):raise ValueError('Unknown test')
                    command={'action':action,'value':track}
                else:return self.respond(404,{'error':'Not found'})
                commands=directory/'commands';commands.mkdir(mode=0o700,exist_ok=True)
                if len(list(commands.glob('*.json')))>30:return self.respond(429,{'error':'Wait for pending controls'})
                write_json(commands/(str(time.time_ns()).zfill(20)+'-'+uuid4().hex+'.json'),command)
                self.respond(202,{'queued':True})
            except (ValueError,TypeError,KeyError) as exc:self.respond(400,{'error':str(exc)})
    return Handler

def main():
    directory=state_directory();directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    server=ThreadingHTTPServer((os.environ.get('POCKET_WEB_BIND','0.0.0.0'),int(os.environ.get('POCKET_WEB_PORT','8787'))),handler(directory))
    print('Calibration dashboard listening on port '+str(server.server_port),flush=True)
    try:server.serve_forever()
    finally:server.server_close()
if __name__=='__main__':main()
