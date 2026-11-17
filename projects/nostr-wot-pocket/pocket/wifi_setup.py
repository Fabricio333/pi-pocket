"""Local password-entry page; only an explicitly opened ten-minute session works."""
import hmac
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = b'''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>SatsBell Wi-Fi</title>
<style>body{font:18px system-ui;max-width:420px;margin:3em auto;padding:1em;background:#100c20;color:white}input,button{box-sizing:border-box;width:100%;padding:14px;margin:8px 0;font:inherit}button{background:#a78bfa}</style>
<h1>Connect SatsBell</h1><p>Enter the setup password shown on the Pi screen, then your Wi-Fi details.</p>
<form id="f"><label>Setup password<input id="token" type="password" required></label><label>Wi-Fi name<input id="ssid" maxlength="32" required></label>
<label>Wi-Fi password<input id="password" type="password" autocomplete="new-password"></label><p>Leave blank only for an open network.</p><button>Save and connect</button></form><p id="result"></p>
<script>f.onsubmit=async e=>{e.preventDefault();result.textContent='Connecting...';try{let r=await fetch('/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:token.value,ssid:ssid.value,password:password.value})});result.textContent=(await r.json()).message}catch(e){result.textContent='Connection switched. Check the Pi screen. If joining failed, reconnect to the setup hotspot and retry.'}}</script>'''

class Setup:
    def __init__(self):
        self.session = None; self.error = ''; self.busy=False; self.server=None

    def open(self):
        if self.busy or (self.session and time.time()<self.session['expires']): return
        self.busy=True
        def worker():
            try:
                value=subprocess.run(['sudo','-n','/usr/local/sbin/pocket-wifi','start'],
                    capture_output=True,text=True,timeout=40,check=True)
                self.session=json.loads(value.stdout);self.error=''
                if not self.server:
                    self.server=ThreadingHTTPServer(('0.0.0.0',8788),self.handler())
                    threading.Thread(target=self.server.serve_forever,daemon=True).start()
            except Exception: self.error='Wi-Fi setup unavailable'
            finally: self.busy=False
        threading.Thread(target=worker,daemon=True).start()

    def handler(self):
        setup=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def reply(self,status,data,kind='application/json'):
                self.send_response(status);self.send_header('Content-Type',kind)
                self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"frame-ancestors 'none'")
                self.end_headers();self.wfile.write(data)
            def active(self):
                return setup.session and time.time()<setup.session['expires']
            def do_GET(self):
                if not self.active(): self.reply(403,b'{"message":"Open Wi-Fi setup on the Pi first"}');return
                self.reply(200,PAGE,'text/html; charset=utf-8')
            def do_POST(self):
                try:
                    if self.path!='/connect' or not self.active(): raise ValueError()
                    if self.headers.get('Origin') not in (None,'http://192.168.4.1:8788'): raise ValueError()
                    length=int(self.headers.get('Content-Length','0'))
                    if not 1<=length<=4096: raise ValueError()
                    data=json.loads(self.rfile.read(length))
                    if not hmac.compare_digest(str(data.get('token','')),setup.session['token']): raise ValueError()
                    ssid,password=data.get('ssid'),data.get('password','')
                    if not isinstance(ssid,str) or not 1<=len(ssid.encode())<=32: raise ValueError()
                    if not isinstance(password,str) or (password and not 8<=len(password)<=63): raise ValueError()
                    self.reply(202,b'{"message":"Saved request. Check the Pi screen; reconnect to setup if joining fails."}')
                    def join():
                        result=subprocess.run(['sudo','-n','/usr/local/sbin/pocket-wifi','connect'],
                            input=json.dumps({'ssid':ssid,'password':password}),capture_output=True,text=True,timeout=90)
                        setup.error='' if result.returncode==0 else 'Join failed. Retry setup page.'
                        if result.returncode==0: setup.session=None
                    threading.Thread(target=join,daemon=True).start()
                except (ValueError,TypeError): self.reply(400,b'{"message":"Check setup password, Wi-Fi name and password"}')
        return Handler

def get_setup(context):
    if not hasattr(context,'wifi_setup'): context.wifi_setup=Setup()
    return context.wifi_setup
