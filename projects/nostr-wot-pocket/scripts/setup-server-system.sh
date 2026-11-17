#!/usr/bin/env bash
# Install the OS components required by the headless audio/LED service.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
  echo 'Run with sudo; no password belongs in the project configuration.' >&2
  exit 1
fi
pocket_user=${SUDO_USER:-}
if [[ -z "$pocket_user" || "$pocket_user" == root ]]; then
  echo 'Run from the normal server account with sudo.' >&2
  exit 1
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends bluez pulseaudio pulseaudio-utils pulseaudio-module-bluetooth shairport-sync avahi-daemon
systemctl enable --now bluetooth avahi-daemon
# The project uses a user AirPlay service against that same user's PulseAudio.
systemctl disable --now shairport-sync
loginctl enable-linger "$pocket_user"
echo "System audio setup complete for $pocket_user. User-service setup can now continue."
