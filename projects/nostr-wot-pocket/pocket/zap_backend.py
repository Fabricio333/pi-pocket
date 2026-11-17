"""Create NIP-57 invoices and accept only matching provider-signed receipts."""
import hashlib, json, os, subprocess, threading, time, urllib.parse, urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError
import bolt11
import websocket
from bech32 import bech32_encode, convertbits
from coincurve import PrivateKey, PublicKeyXOnly

RECIPIENT='d9590d95a7811e1cb312be66edd664d7e3e6ed57822ad9f213ed620fc6748be8'
PROVIDER='f8506d07c0734988fe5af5f25cead689f99088f006f7b490c7d094ae308679d0'
ENDPOINT='https://nostrwot.com/.well-known/lnurlp/fabri'
PRIMARY_ADDRESS='fabri@nostrwot.com'
FALLBACK_ADDRESS='avidflower48@walletofsatoshi.com'
FALLBACK_ENDPOINT='https://walletofsatoshi.com/.well-known/lnurlp/avidflower48'
FALLBACK_PROVIDER='be1d89794bf92de5dd64c1e60f6a2c70c140abac9932418fee30c5c637fe9479'
RELAYS=['wss://nos.lol','wss://relay.primal.net','wss://relay.ditto.pub']
lock=threading.Lock()
pending={}
started=False
STATE=Path(os.environ.get('POCKET_STATE_DIR',str(Path.home()/'.local/share/nostr-wot-pocket')))/'zap-invoices.json'
STATE.parent.mkdir(parents=True,exist_ok=True)
def dumps(value): return json.dumps(value,separators=(',',':'),ensure_ascii=False)
def event_hash(e):
    return hashlib.sha256(dumps([0,e['pubkey'],e['created_at'],e['kind'],e['tags'],e['content']]).encode()).digest()
def valid_event(e):
    try:
        digest=event_hash(e)
        return digest.hex()==e['id'] and PublicKeyXOnly(bytes.fromhex(e['pubkey'])).verify(bytes.fromhex(e['sig']),digest)
    except (ValueError,KeyError,TypeError): return False
def get(url):
    request=urllib.request.Request(url,headers={'User-Agent':'PiZero-WoT-Pay/1.0'})
    with urllib.request.urlopen(request,timeout=15) as r: value=json.load(r)
    if value.get('status')=='ERROR': raise RuntimeError(value.get('reason','Provider error'))
    return value
def save():
    temp=STATE.with_suffix('.tmp')
    temp.write_text(dumps(pending)); temp.replace(STATE)
def validate_receipt(e,record):
    """No side effects: check signature, exact invoice, request and payment hash."""
    try:
        if e['kind']!=9735 or e['pubkey']!=record['provider'] or not valid_event(e): return False
        tags={}
        for tag in e['tags']:
            if len(tag)>=2: tags.setdefault(tag[0],[]).append(tag[1])
        if tags.get('p')!=[RECIPIENT]: return False
        if tags.get('bolt11')!=[record['invoice']]: return False
        if len(tags.get('description',[]))!=1: return False
        description=tags['description'][0]
        request=json.loads(description)
        if request!=record['request'] or not valid_event(request): return False
        invoice=bolt11.decode(record['invoice'])
        if int(invoice.amount_msat)!=21000 or not invoice.is_mainnet(): return False
        if invoice.description_hash!=hashlib.sha256(description.encode()).hexdigest(): return False
        if 'preimage' in tags:
            if len(tags['preimage'])!=1: return False
            if hashlib.sha256(bytes.fromhex(tags['preimage'][0])).hexdigest()!=invoice.payment_hash: return False
        return True
    except Exception: return False
def announce():
    from .celebration import celebrate
    celebrate()
def process_receipt(e,events):
    with lock:
        matches=[r for r in pending.values() if not r.get('paid')]
    for record in matches:
        if not validate_receipt(e,record): continue
        with lock:
            if record.get('paid'): return
            record['paid']=True; record['receipt']=e['id']; save()
        print('VERIFIED PAYMENT: 21 sats; receipt '+e['id'],flush=True)
        events.put(('paid',record))
        print('Verified receipt queued for device UI: '+e['id'],flush=True)
        return
def watch(relay,events):
    delay=2
    while True:
        sock=None
        try:
            sock=websocket.create_connection(relay,timeout=12,origin='https://nostrwot.com')
            with lock:
                unpaid=[r['created_at'] for r in pending.values() if not r.get('paid')]
            since=min(unpaid,default=int(time.time()))-60
            sock.send(dumps(['REQ','pi-zaps',{'kinds':[9735],'authors':[PROVIDER,FALLBACK_PROVIDER],'#p':[RECIPIENT],'since':since}]))
            print('Receipt relay connected: '+relay,flush=True); delay=2
            while True:
                try: message=json.loads(sock.recv())
                except websocket.WebSocketTimeoutException:
                    sock.ping(); continue
                if message and message[0]=='EVENT' and len(message)==3:
                    process_receipt(message[2],events)
                elif message and message[0]=='CLOSED': raise RuntimeError('Subscription closed')
        except Exception as exc:
            print('Receipt relay retry '+relay+': '+str(exc)[:100],flush=True)
        finally:
            if sock: sock.close()
        time.sleep(delay); delay=min(30,delay*2)
def start(events):
    global started,pending
    if started: return
    if STATE.exists():
        try: pending=json.loads(STATE.read_text())
        except (ValueError,OSError): pending={}
    started=True
    for relay in RELAYS: threading.Thread(target=watch,args=(relay,events),daemon=True).start()
def create_invoice(events):
    start(events)
    try:
        return request_invoice(events,ENDPOINT,PROVIDER,PRIMARY_ADDRESS)
    except (HTTPError,URLError,TimeoutError,ConnectionError) as exc:
        if isinstance(exc,HTTPError) and exc.code not in (408,429) and exc.code<500:
            raise
        print('Primary invoice service unavailable; trying fallback.',flush=True)
    return request_invoice(events,FALLBACK_ENDPOINT,FALLBACK_PROVIDER,FALLBACK_ADDRESS)

def invoice_address(invoice):
    with lock:
        return next((r.get('address',PRIMARY_ADDRESS) for r in pending.values()
                     if r.get('invoice')==invoice),PRIMARY_ADDRESS)

def request_invoice(events,endpoint,provider,address):
    meta=get(endpoint)
    if not meta.get('allowsNostr') or meta.get('nostrPubkey')!=provider:
        raise RuntimeError('Zap provider identity changed')
    if not meta['minSendable']<=21000<=meta['maxSendable']: raise ValueError('Amount unavailable')
    secret=PrivateKey()
    lnurl=bech32_encode('lnurl',convertbits(endpoint.encode(),8,5))
    request={'kind':9734,'pubkey':secret.public_key_xonly.format().hex(),
             'created_at':int(time.time()),'content':'',
             'tags':[['p',RECIPIENT],['amount','21000'],['relays',*RELAYS],['lnurl',lnurl]]}
    digest=event_hash(request);request['id']=digest.hex();request['sig']=secret.sign_schnorr(digest).hex()
    assert valid_event(request)
    raw=dumps(request)
    callback=meta['callback']
    parsed=urllib.parse.urlsplit(callback)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Invalid invoice callback URL')
    query=dict(urllib.parse.parse_qsl(parsed.query,keep_blank_values=True))
    query.update(amount='21000',nostr=raw,lnurl=lnurl)
    response=get(urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query))))
    invoice=response['pr']; decoded=bolt11.decode(invoice)
    if int(decoded.amount_msat)!=21000 or not decoded.is_mainnet() or decoded.has_expired():
        raise ValueError('Invalid invoice amount or expiry')
    if decoded.description_hash!=hashlib.sha256(raw.encode()).hexdigest():
        raise ValueError('Invoice is not committed to our zap request')
    record={'invoice':invoice,'request':request,'provider':provider,'address':address,'created_at':int(time.time()),
            'paid':False,'expires_at':decoded.expiry_time}
    with lock:
        pending[decoded.payment_hash]=record;save()
    return invoice
