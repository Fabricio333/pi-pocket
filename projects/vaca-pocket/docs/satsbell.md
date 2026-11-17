# Sats Bell for the Pi Zero

Uses the existing Waveshare ST7789 240×240 screen, three right-side buttons,
coincurve Nostr signing, NetworkManager and PulseAudio/JBL output. There is no
ESP32 wiring or LCD1602 requirement. Install with `sh ops/install-satsbell.sh`.
The Python environment must include system site packages for the existing GPIO
drivers; the root Wi-Fi helper uses the OS Python with libnm installed by this script.

Open **Doorbell**. Buttons 1/2 move through the menu; button 3 selects; hold 3
to return home. Create an address, show its Lightning QR, test the two-tone chime and Spanish “Hay alguien en la puerta” JBL announcement, release
with confirmation, or inspect recent receipts. Pay the actual displayed address
at least 21 sats after **Ready to ring**. No payment is sent automatically.
The wallet is dedicated to this app and remains identical across restarts.
Closing the app keeps monitoring active; restarting the launcher resumes it.

The default provider is `https://zaps.nostr-wot.com`.
The default provider's `nostrwot.com` vanity address is normalized to its
`zaps.nostr-wot.com` payment-metadata address. Only those two explicitly known
domains are aliases; username and settled-payment checks remain exact.
V2 operation requests use
exact-body hashes, signed kind-27235 events and transaction-token binding.
Certificate-validated HTTPS rejects redirects and limits bodies to 40 KB.
The full history is scanned in pages of ten with a 500-page hard stop.
Only successful incoming integer-msat payments matching the active address and
threshold qualify. SQLite uses synchronous FULL transactions and a unique payment
hash; the receipt commits before a sound event. Offline/recovery baseline receipts
stay silent. Release intent persists before the service request and gates ringing.
Corrupt storage fails without resetting identity. A commit followed by power loss
can suppress a ring, so receipt records prove a request rather than physical sound.

Private state is `~/.local/share/nostr-wot-pocket/satsbell.sqlite3` (mode 0600).
It contains identity, wallet API keys and receipts. For a private backup, stop the
launcher, copy this database to private storage, then restart. Never commit it.
There is no withdrawal UI or ESP32 backup import in this Pi version. The existing
Pay 21 app remains separate; Sats Bell does not reuse its recipient or fallback.

## Wi-Fi setup

Open **Wi-Fi setup**, press button 3 and read the generated SSID/password on the
screen. The first screen shows a **Wi-Fi QR**: scan it with the phone camera
and accept the prompt to join the WPA2 hotspot. Press button 3 for a second QR
that opens **http://192.168.4.1:8788**; press it again for the typed credentials.
Buttons 1/2 also cycle these pages. Hold button 3 to return home.
Enter the same setup password, paste the new Wi-Fi name and password, and submit.
Keep the phone connected if it warns that the hotspot has no internet. A blank
network password selects an open network. Credentials are saved by NetworkManager.

The single radio switches away from its current Wi-Fi eight seconds after opening
setup. Payments are reconciled silently when it reconnects. The temporary hotspot
expires after ten minutes and restores the previous connection if no network was
successfully joined. Failed joins bring back the setup hotspot for another try.
The page only accepts changes during an explicitly opened session with its random
setup password; credentials are passed to the root helper over stdin. The helper
is root-owned with a narrowly scoped sudo rule. The interface supports WPA personal
and open 2.4 GHz networks, not enterprise authentication.

## Verification

Run `.venv-server/bin/python -m unittest discover -s tests -v` on the development
machine. Device acceptance still requires checking readable display, physical
buttons, hearing the test sound, paying the real displayed address, rebooting to
verify no replay, and completing a phone hotspot/network transition. An SSH-only
test must not deliberately start the hotspot without an observer at the screen.

The device interface and setup page are branded **Vaca Inteligente**
(`vacainteligente.com`). The setup hotspot is named `VacaInteligente-XXXX`.
Legacy service names and private state paths are retained so updates find the
existing wallet, installed apps and payment journal.
