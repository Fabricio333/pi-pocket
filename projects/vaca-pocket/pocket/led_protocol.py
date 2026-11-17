"""Miracles Star / Findn packets. BLE acceptance is not firmware acknowledgement."""
import struct

TX='0000fff3-0000-1000-8000-00805f9b34fb'
NOTIFY='0000fff4-0000-1000-8000-00805f9b34fb'
# Effect IDs documented by ha-findn-led-ble's device_protocol.py.
EFFECTS={'red-running':0x54,'red-tailing':0x4D,'white-wipe':0x2C,'yellow-running':0x57,
         'green-tailing':0x4E,'blue-tailing':0x4F,'yellow-tailing':0x50,'cyan-tailing':0x51,'purple-tailing':0x52,
         'green-running':0x55,'blue-running':0x56,'cyan-running':0x58,'purple-running':0x59,
         'rainbow-gradient':0x0A,'rainbow-brush':0x1D,'colorful-energy':0x03,
         'rainbow-breathe':0x23,'blue-purple-flow':0x3E,'warm-cool-flow':0x3D,
         'rainbow-tail':0x4C,'rainbow-flow':0x37,'rainbow-running':0x5B}
def packet(command,data):
    payload=bytes(data)
    if len(payload)>255:raise ValueError('Payload too long')
    return bytes((0xBC,command,len(payload)))+payload+b'\x55'
def power(on):return packet(0x01,[int(bool(on))])
def brightness(level):
    if not isinstance(level,int) or not 3<=level<=1000:raise ValueError('Brightness must be 3..1000 per mille')
    return packet(0x05,struct.pack('>H',level)+bytes(4))
def color(hue=0,saturation=1000):
    if not 0<=hue<=360 or not 0<=saturation<=1000:raise ValueError('Invalid hue or saturation')
    return packet(0x04,struct.pack('>HH',round(hue),round(saturation))+bytes(2))
def effect(name):return packet(0x06,[0,EFFECTS[name]])
def direction(forward=True):return packet(0x07,[int(bool(forward))])
def count_probe(count):
    """Experimental configuration command, NOT a pixel range selector."""
    if not isinstance(count,int) or not 8<=count<=300:raise ValueError('Experimental count must be 8..300')
    return packet(0x03,struct.pack('>H',count))
