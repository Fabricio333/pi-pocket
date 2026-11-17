"""Local file-based controls for the headless server; no HTTP API."""
import argparse
import json
from .server import state_directory,write_json

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['status','live','off','red','test','invoice'])
    parser.add_argument('track',nargs='?',choices=['demo','thunder','zap','click'],default='demo')
    args=parser.parse_args();directory=state_directory()
    if args.action=='status':
        for name in ['server-status.json','led-status.json']:
            path=directory/name
            print(name+': '+(path.read_text() if path.exists() else 'not started'))
        return
    directory.mkdir(parents=True,exist_ok=True)
    inbox=directory/'server-command.json'
    if inbox.exists():parser.error('A command is pending; wait for the server to consume it')
    write_json(inbox,{'action':args.action,'value':args.track if args.action=='test' else None})
    print('Queued '+args.action)

if __name__=='__main__':main()
