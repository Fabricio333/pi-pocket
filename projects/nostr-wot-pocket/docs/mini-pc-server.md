# Mini PC audio, lighting and calibration

The headless runtime is `python -m pocket.server`. It uses the existing BLE and payment modules without importing GPIO or the LCD driver. The Pi's AirPlay service was disabled, its peripheral connections released, 28 invoice records copied into the private server state directory, and the Pi cleanly shut down.

The active route is **Mac → AirPlay “WoT Pocket Server” → mini PC → Bluetooth JBL**, with a separate BLE connection from the mini PC to the LED controller. The Mac and mini PC must share a network that permits AirPlay discovery.

## Installation

Run `sudo bash scripts/setup-server-system.sh` once from the normal server account. It installs BlueZ, PulseAudio with Bluetooth support, Shairport Sync and Avahi, enables Bluetooth, and enables user-service lingering. The packaged system AirPlay unit is disabled because this project runs its receiver in the same user session as PulseAudio.

Create `.venv-server` with `python3 -m venv .venv-server`, then install `requirements-server.txt`. No Pi-specific GPIO packages are required. Pair and trust the JBL using `bluetoothctl`. The LED controller uses its existing explicitly selected BLE address and does not require pairing.

Create `~/.config/nostr-wot-pocket/server.env` with mode 600, containing the private `POCKET_LED_ADDRESS`, `POCKET_SPEAKER_ADDRESS`, `POCKET_AUDIO_SINK`, and `PULSE_SINK`. Both sink values should name the JBL's PulseAudio A2DP sink. Set `POCKET_STATE_DIR` to `~/.local/share/nostr-wot-pocket-server` using an absolute path, and set `XDG_RUNTIME_DIR` and `PULSE_SERVER` for the user session. `POCKET_LED_BRIGHTNESS=100` is 10%; the mini PC baseline uses `POCKET_AUDIO_LED_DELAY_MS=0`.

Run `bash scripts/setup-server-user.sh` without sudo. The provided units assume the checkout is `~/nostr-wot-pocket`. They start automatically after reboot, including without an interactive login:

- `nostr-wot-pocket-server.service`: BLE, audio analysis and signed-receipt monitoring.
- `nostr-wot-airplay.service`: the Mac's AirPlay receiver.
- `nostr-wot-calibration.service`: the LAN control page on port 8787.

## LAN controls

Open `http://192.168.0.148:8787` on the current network. If the server address changes, use the new address and update `POCKET_WEB_ALLOWED_HOSTS`. The service defaults to all local interfaces; `POCKET_WEB_BIND` and `POCKET_WEB_PORT` can override its bind address and port. There is no public hosting or port forwarding.

Choose one effect at a time. Rainbow mix retains the original multicolor option. Beat Tails and Beat Chases hold one color for the selected number of detected beats. Beat Build increases whole-strip brightness with successive beats, then restarts in the next color. It does not claim individual-pixel filling. Additional controller presets include fades, brushes, opening/closing and two-color flows.

Slider changes and effect selections preview live without restarting the monitor or playback. **Save settings** persists the current configuration across restarts. **Restore working baseline** previews the initial baseline; save it explicitly to retain it. Brightness ranges from 1% to 100% in 1% steps. Settings use per-mille brightness internally.

Use the payment-sound checkbox to mute zap announcements while retaining signed payment confirmation. Test buttons are effects/audio diagnostics; they neither send money nor mark invoices paid. The page deliberately exposes no payment action or private invoice records.

The click test plays six clicks through the JBL and uses the live monitor to render them. Pause other music to judge timing. Positive delay values hold light updates; negative values remove waiting but cannot predict audio or erase processing/BLE latency. The displayed response is capture-to-BLE delivery, not a measured acoustic sound-to-light offset. Preset motion runs on the controller's own clock; brightness and color/effect transitions react to detected hits.

LAN commands are validated, queued as private files and executed by the existing LED owner. The HTTP server rejects unrecognized hosts, cross-origin browser writes, unsupported commands and out-of-range settings. It is intended for a trusted LAN and does not provide an Internet-facing account/login system.

## Local controls and state

From the checkout use `.venv-server/bin/python -m pocket.control status`, `live`, `off`, `red`, `test demo`, `test thunder`, `test click`, or `invoice`. Invoice creation keeps WoT/LNbits primary and Wallet of Satoshi as fallback. Its QR is exported to the private state directory. Creating invoices never spends funds.

Runtime invoice records, `calibration.json`, `calibration-baseline.json`, status and command files live in `POCKET_STATE_DIR` outside Git. API keys and system Bluetooth pairing keys are not copied into the repository.

Inspect services with `systemctl --user status nostr-wot-pocket-server nostr-wot-airplay nostr-wot-calibration`. View logs using `journalctl --user -u nostr-wot-pocket-server -f`.

## Verification

The full Python suite covers signed-invoice/receipt matching, fallback, headless playback, cancellation, settings preview/save, beat-counted color transitions and HTTP validation. Run `.venv-server/bin/python -m unittest discover -s tests`. Check frontend syntax with `node --check pocket/web_assets/app.js`.

A desktop and phone browser check verifies the effect buttons and Save control render, no JavaScript errors occur, and the phone page has no horizontal overflow. A user has confirmed music forwarding and a working multicolor effect; exact acoustic synchronization and individual preset appearance require physical observation.
