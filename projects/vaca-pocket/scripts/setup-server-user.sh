#!/usr/bin/env bash
# Install only this project's services in the current user's systemd manager.
set -euo pipefail
pocket_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ $EUID -eq 0 ]]; then echo 'Run as the normal server user, without sudo.' >&2; exit 1; fi
for program in bluetoothctl pactl shairport-sync; do
  command -v "$program" >/dev/null || { echo "Missing $program: run setup-server-system.sh first" >&2; exit 1; }
done
if [[ ! -x "$pocket_root/.venv-server/bin/python" ]]; then
  python3 -m venv "$pocket_root/.venv-server"
  "$pocket_root/.venv-server/bin/pip" install -r "$pocket_root/requirements-server.txt"
fi
mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/nostr-wot-pocket"
if [[ ! -f "$HOME/.config/nostr-wot-pocket/server.env" ]]; then
  echo 'Create ~/.config/nostr-wot-pocket/server.env with the selected device addresses first.' >&2
  exit 1
fi
install -m 644 "$pocket_root/ops/server/pocket.service" "$HOME/.config/systemd/user/nostr-wot-pocket-server.service"
install -m 644 "$pocket_root/ops/server/airplay.service" "$HOME/.config/systemd/user/nostr-wot-airplay.service"
install -m 644 "$pocket_root/ops/server/web.service" "$HOME/.config/systemd/user/nostr-wot-calibration.service"
systemctl --user daemon-reload
systemctl --user enable --now pulseaudio.socket pulseaudio.service nostr-wot-pocket-server.service nostr-wot-airplay.service nostr-wot-calibration.service
