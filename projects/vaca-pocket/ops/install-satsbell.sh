#!/bin/sh
# Run from the project root on Raspberry Pi OS with NetworkManager.
set -eu
sudo apt-get install -y python3-gi gir1.2-nm-1.0
sudo install -m 0755 -o root -g root ops/pocket-wifi /usr/local/sbin/pocket-wifi
sudo sh -c 'printf "%s\n" "pi ALL=(root) NOPASSWD: /usr/local/sbin/pocket-wifi start, /usr/local/sbin/pocket-wifi connect, /usr/local/sbin/pocket-wifi restore" > /etc/sudoers.d/pocket-wifi'
sudo chmod 0440 /etc/sudoers.d/pocket-wifi
sudo visudo -cf /etc/sudoers.d/pocket-wifi
python3 - <<'PY'
import json
from pathlib import Path
p=Path.home()/'.local/share/nostr-wot-pocket/installed.json'
p.parent.mkdir(parents=True,exist_ok=True)
v=set(json.loads(p.read_text())) if p.exists() else {'pay21'}
v.update(('satsbell','wifi'))
p.write_text(json.dumps(sorted(v)))
PY
sudo systemctl restart nostr-wot-pocket
