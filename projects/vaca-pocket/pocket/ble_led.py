"""Explicit-device BLE inspection and bounded low-brightness spatial experiments."""
import argparse, asyncio, datetime, json, os
from pathlib import Path
from . import led_protocol as protocol

async def run(args):
    from bleak import BleakScanner,BleakClient
    state=Path(os.environ.get('POCKET_STATE_DIR',str(Path.home()/'.local/share/nostr-wot-pocket')))
    state.mkdir(parents=True,exist_ok=True);log_file=state/'led-experiments.jsonl'
    def log(kind,**values):
        record={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'event':kind,**values}
        with log_file.open('a') as stream:stream.write(json.dumps(record)+'\n')
        print(json.dumps(record),flush=True)
    log('scan',address=args.address)
    device=await BleakScanner.find_device_by_address(args.address,timeout=30)
    if not device:raise RuntimeError('Specified controller not advertising')
    async with BleakClient(device,timeout=25) as client:
        log('connected',name=device.name)
        for service in client.services:
            log('service',uuid=service.uuid,characteristics=[{'uuid':c.uuid,'handle':c.handle,'properties':c.properties} for c in service.characteristics])
        try:
            await client.start_notify(protocol.NOTIFY,lambda sender,value:log('notification',uuid=sender.uuid,hex=bytes(value).hex()))
        except Exception as exc:log('notification-unavailable',error=str(exc))
        # FF15 is read-only here; its write capability may belong to firmware tooling.
        for uuid in ['00002a00-0000-1000-8000-00805f9b34fb','0000ff15-0000-1000-8000-00805f9b34fb']:
            try:log('read',uuid=uuid,hex=bytes(await client.read_gatt_char(uuid)).hex())
            except Exception as exc:log('read-unavailable',uuid=uuid,error=str(exc))
        async def write(label,data):
            await client.write_gatt_char(protocol.TX,data,response=True)
            log('att-write-accepted',label=label,hex=data.hex(),visual_result='unconfirmed')
            await asyncio.sleep(.25)
        async def restore():
            await write('restore configured count request 8',protocol.count_probe(8))
            await write('restore steady red',protocol.color())
            await write('restore 10 percent brightness',protocol.brightness(100))
            await write('restore power on',protocol.power(True))
            log('restored',requested_state='whole-strip dim red; visual confirmation still required')
        if args.action=='inspect':return
        if args.action=='red':
            await write('steady red',protocol.color());await write('brightness',protocol.brightness(args.brightness));await write('power on',protocol.power(True));return
        try:
            await write('test brightness 10 percent',protocol.brightness(100))
            await write('power on',protocol.power(True))
            trials=[(8,'red-running',True),(300,'red-running',True),(8,'red-tailing',False)]
            for number,(count,name,forward) in enumerate(trials,1):
                log('trial-start',trial=number,count_request=count,effect=name,direction='forward' if forward else 'reverse',duration=args.seconds)
                await write('experimental count request',protocol.count_probe(count))
                await write('documented effect',protocol.effect(name))
                await write('effect direction',protocol.direction(forward))
                await write('keep brightness low',protocol.brightness(100))
                await asyncio.sleep(args.seconds)
                log('trial-end',trial=number,visual_result='awaiting user observation')
        finally:await restore()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address',required=True,help='Explicit Bluetooth MAC; never adopt by name alone')
    parser.add_argument('action',choices=['inspect','red','probe-chase'])
    parser.add_argument('--seconds',type=float,default=10)
    parser.add_argument('--brightness',type=int,default=100)
    args=parser.parse_args()
    if not 2<=args.seconds<=30:parser.error('--seconds must be 2..30')
    asyncio.run(run(args))
if __name__=='__main__':main()
