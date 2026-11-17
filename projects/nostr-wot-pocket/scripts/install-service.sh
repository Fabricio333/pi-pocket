#!/usr/bin/env bash
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo on the Raspberry Pi.'; exit 1; }
project=$(cd -- "$(dirname -- "$0")/.." && pwd)
[[ "$project" == /home/pi/nostr-wot-pocket ]] || { echo 'Install the source in /home/pi/nostr-wot-pocket first.'; exit 1; }
install -m 644 "$project/scripts/nostr-wot-pocket.service" /etc/systemd/system/nostr-wot-pocket.service
loginctl enable-linger pi
systemctl daemon-reload
systemctl enable --now nostr-wot-pocket.service
