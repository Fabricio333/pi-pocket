"""Dedicated WoT v2 doorbell wallet; durable receipts precede sound requests."""
import base64
import hashlib
import json
import os
import queue
import secrets
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from coincurve import PrivateKey

ORIGIN = 'https://zaps.nostr-wot.com'
_sound_lock = threading.Lock()

def play_sound(sink,track=None,cancel=None):
    """Serialize cached playback and reconnect the configured Bluetooth sink."""
    from .ringtones import Ringtones,stop_preview
    if cancel is None:stop_preview()
    with _sound_lock:
        if cancel is not None and cancel.is_set():return None
        env = os.environ.copy()
        env['XDG_RUNTIME_DIR'] = '/run/user/1000'
        if sink.startswith('bluez_sink.'):
            sinks = subprocess.run(['pactl','list','short','sinks'], env=env,
                capture_output=True, text=True, timeout=5, check=True).stdout
            if sink not in sinks:
                address = sink.split('.')[1].replace('_', ':')
                subprocess.run(['bluetoothctl','--timeout','10','connect',address],
                    capture_output=True, timeout=15, check=True)
        from .ui import ROOT
        if track is None:track=Ringtones().next()
        path=track['path'] if track else ROOT/'assets/audio/doorbell-announcement.wav'
        title=track['title'] if track else 'Doorbell'
        print('Doorbell ringtone: '+title,flush=True)
        command=['paplay','--device='+sink,str(path)]
        if cancel is None:
            subprocess.run(command,env=env,timeout=30,check=True)
        else:
            player=subprocess.Popen(command,env=env)
            deadline=time.monotonic()+30
            try:
                while player.poll() is None:
                    if cancel.wait(.05):return None
                    if time.monotonic()>deadline:raise TimeoutError('Audio playback timed out')
                if player.returncode:raise subprocess.CalledProcessError(player.returncode,command)
            finally:
                if player.poll() is None:
                    player.terminate()
                    try:player.wait(timeout=2)
                    except subprocess.TimeoutExpired:player.kill();player.wait()
        return title

def compact(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False)

def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()

def eligible(payment, address, minimum=21):
    amount = payment.get('amount')
    return (type(amount) is int and amount >= minimum * 1000
            and payment.get('status') == 'success'
            and isinstance(payment.get('extra'), dict)
            and payment['extra'].get('lnaddress') == address
            and isinstance(payment.get('payment_hash'), str)
            and len(payment['payment_hash']) == 64
            and all(c in '0123456789abcdef' for c in payment['payment_hash']))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class Provider:
    def __init__(self, secret, origin=ORIGIN):
        self.key = PrivateKey(bytes.fromhex(secret))
        self.pubkey = self.key.public_key_xonly.format().hex()
        self.origin = origin
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path, body=None, headers=None):
        raw = body.encode() if isinstance(body, str) else None
        request = urllib.request.Request(self.origin + path, data=raw,
            headers={'Content-Type': 'application/json', 'User-Agent': 'SatsBell-Pi/1', **(headers or {})})
        with self.opener.open(request, timeout=20) as response:
            data = response.read(40961)
        if len(data) > 40960:
            raise ValueError('Provider response exceeds 40 KB')
        return json.loads(data)

    def operation(self, path, body):
        raw = compact(body)
        url = self.origin + path
        challenge = self.request('/api/v2/provision/challenge', compact({
            'url': url, 'method': 'POST', 'payload': sha(raw)}))
        if (challenge.get('version') != 2
                or type(challenge.get('expiresAt')) is not int
                or not time.time() < challenge['expiresAt'] <= time.time() + 120):
            raise ValueError('Invalid or expired v2 challenge')
        for field in ('challenge', 'transactionToken'):
            token = challenge.get(field)
            if not isinstance(token, str) or len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
                raise ValueError('Invalid v2 challenge token')
        token = challenge['transactionToken']
        event = {'pubkey': self.pubkey, 'created_at': int(time.time()), 'kind': 27235,
                 'tags': [['u', url], ['method', 'POST'], ['payload', sha(raw)],
                          ['challenge', challenge['challenge']], ['transaction', sha(token)]], 'content': ''}
        digest = hashlib.sha256(compact([0, event['pubkey'], event['created_at'],
            event['kind'], event['tags'], '']).encode()).digest()
        event.update(id=digest.hex(), sig=self.key.sign_schnorr(digest).hex())
        return self.request(path, raw, {'Authorization': 'Nostr ' + base64.b64encode(compact(event).encode()).decode(),
                                       'X-Nostr-Transaction': token})

    def address(self):
        value = self.request('/api/lightning-address?pubkey=' + self.pubkey)['address']
        if value is not None and (not isinstance(value, str) or value.count('@') != 1):
            raise ValueError('Invalid provider address')
        # This provider advertises its vanity domain in address lookup, while
        # settled LNbits receipts identify its canonical payment-service domain.
        # Normalize only these explicitly known aliases, never arbitrary domains.
        if value and self.origin == ORIGIN:
            username, domain = value.split('@')
            if domain in ('nostrwot.com', 'zaps.nostr-wot.com'):
                value = username + '@zaps.nostr-wot.com'
        return value or ''

    def history(self, inkey):
        result = []
        for page in range(500):
            rows = self.request('/api/v1/payments?' + urllib.parse.urlencode({
                'limit': 10, 'offset': page * 10, 'status': 'success',
                'sortby': 'time', 'direction': 'desc'}), headers={'X-Api-Key': inkey})
            if not isinstance(rows, list) or len(rows) > 10 or any(not isinstance(r, dict) for r in rows):
                raise ValueError('Invalid payment history')
            result.extend(rows)
            if len(rows) < 10:
                return result
        raise ValueError('Payment history scan limit reached')

class Store:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'satsbell.sqlite3'
        existed = path.exists()
        if existed and path.stat().st_size == 0:
            raise ValueError('Existing SatsBell storage is empty; restore a private backup')
        self.db = sqlite3.connect(path, check_same_thread=False)
        os.chmod(path, 0o600)
        self.db.execute('PRAGMA synchronous=FULL')
        if self.db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('SatsBell storage integrity check failed')
        if existed:
            tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'settings','receipts'} <= tables:
                raise ValueError('Existing SatsBell storage is incomplete; restore a private backup')
        self.db.executescript('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);'
            'CREATE TABLE IF NOT EXISTS receipts (hash TEXT PRIMARY KEY, amount INTEGER NOT NULL, address TEXT NOT NULL, missed INTEGER NOT NULL, at INTEGER NOT NULL);')
        self.lock = threading.RLock()
        if not self.get('secret'):
            if existed:
                raise ValueError('Saved SatsBell identity is missing; restore a private backup')
            self.set('secret', PrivateKey().secret.hex())

    def get(self, key, default=None):
        with self.lock:
            row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, compact(value)))

    def receipt(self, payment, address, missed):
        with self.lock, self.db:
            return self.db.execute('INSERT OR IGNORE INTO receipts VALUES (?,?,?,?,?)',
                (payment['payment_hash'], payment['amount'], address, int(missed), int(time.time()))).rowcount == 1

    def history(self):
        with self.lock:
            return self.db.execute('SELECT amount,missed,at FROM receipts ORDER BY at DESC,rowid DESC LIMIT 20').fetchall()

class Bell:
    def __init__(self, directory, events):
        self.store = Store(directory)
        self.provider = Provider(self.store.get('secret'))
        self.events = events
        self.commands = queue.Queue()
        self.status = 'Connecting'; self.error = ''; self.armed = False
        self.address = self.store.get('address', '')
        self.minimum = self.store.get('minimum', 21)
        self.thread = threading.Thread(target=self.run, daemon=True)

    def action(self, action):
        if action not in ('create', 'release', 'test'):
            raise ValueError('Unknown SatsBell action')
        if action == 'test':
            self.events.put(('satsbell-test', {}))
            return
        if action == 'release':
            self.store.set('release', True)
            self.store.set('create_requested', False)
            self.store.set('claim', None)
            self.armed = False
        elif action == 'create':
            self.store.set('create_requested', True)
        self.commands.put(action)

    def scan(self, silent):
        rows = self.provider.history(self.store.get('wallet')['inkey'])
        for payment in rows:
            if eligible(payment, self.address, self.minimum):
                # The synchronous SQLite commit completes before the event is published.
                missed = silent or self.store.get('release', False) or not self.armed
                if self.store.receipt(payment, self.address, missed) and not missed:
                    self.events.put(('satsbell-paid', {'amount': payment['amount'] // 1000}))

    def synchronize(self):
        self.armed = False
        if not self.store.get('wallet'):
            wallet = self.provider.operation('/api/v2/provision', {'name': 'Vaca Inteligente Doorbell'})
            if not isinstance(wallet, dict) or not all(isinstance(wallet.get(k), str) and wallet[k] for k in ('id', 'inkey', 'adminkey')):
                raise ValueError('Invalid wallet credentials')
            self.store.set('wallet', wallet)
        address = self.provider.address()
        if self.store.get('release', False):
            if address:
                self.provider.operation('/api/v2/release-username', {})
            self.store.set('address', ''); self.address = ''
            self.store.set('release', False)
        else:
            self.address = address
            self.store.set('address', address)
        self.scan(True)
        self.armed = bool(self.address) and not self.store.get('release', False)
        self.status = 'Ready to ring' if self.armed else 'Create an address'

    def create(self):
        if self.store.get('release', False):
            raise ValueError('Address release pending')
        self.synchronize()
        if self.address:
            return
        for _ in range(5):
            username = self.store.get('claim') or str(secrets.randbelow(900000) + 100000)
            self.store.set('claim', username)
            try:
                self.provider.operation('/api/v2/claim-username', {'username': username})
                self.synchronize()
                self.store.set('claim', None)
                return
            except urllib.error.HTTPError as exc:
                if exc.code != 409:
                    raise
                # Reconcile an uncertain prior claim before trying a different name.
                self.synchronize()
                self.store.set('claim', None)
                if self.address:
                    return
        raise ValueError('Address collision limit reached')

    def run(self):
        synced = False
        while True:
            try:
                if not synced:
                    self.synchronize(); synced = True
                    if self.store.get('create_requested') and not self.store.get('release', False):
                        self.create()
                        self.store.set('create_requested', False)
                try:
                    action = self.commands.get(timeout=3)
                except queue.Empty:
                    action = None
                if action == 'test':
                    self.events.put(('satsbell-test', {}))
                elif action == 'create':
                    self.create()
                    self.store.set('create_requested', False)
                elif action == 'release' or self.store.get('release', False):
                    self.synchronize()
                elif self.address:
                    self.scan(False)
                self.error = ''
            except Exception as exc:
                self.armed = False; synced = False
                self.status = 'Offline / retrying'
                self.error = ('Provider HTTP ' + str(exc.code)) if isinstance(exc, urllib.error.HTTPError) else str(exc)[:100]
                time.sleep(5)

def get_bell(context):
    if not hasattr(context, 'satsbell'):
        directory = os.environ.get('POCKET_STATE_DIR', str(Path.home() / '.local/share/nostr-wot-pocket'))
        context.satsbell = Bell(directory, context.events)
        context.satsbell.thread.start()
    return context.satsbell
