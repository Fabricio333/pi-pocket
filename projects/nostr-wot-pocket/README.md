# Sats Bell and Wi-Fi setup

The Pi version now includes **Sats Bell**, a dedicated persistent Lightning
doorbell wallet with address QR, confirmed-payment monitoring and JBL sound, and
**Wi-Fi setup**, a temporary phone-accessible hotspot for pasting network details.
See [installation, controls, storage and acceptance checks](docs/satsbell.md).

# Nostr WoT Pocket

A miniapp launcher and bundled app marketplace for Raspberry Pi Zero 2 W with the Waveshare 1.3-inch 240×240 LCD HAT, joystick, and three buttons. Uses the official Nostr WoT icon and purple palette.

## Included miniapps

| App | What it does |
| --- | --- |
| Pay 21 | A full-screen Lightning QR for 21 sats to fabri@nostrwot.com. Validates NIP-57 receipts, shows confirmation, and plays cached thunder plus voice through Bluetooth. |
| Thunder Lab | Preview thunder-only or payment audio, without creating a payment. |
| Clock | Offline clock and date. |
| Obelisk Sky | Pair a NIP-46 remote signer, then use three-button menus to walk, jump and emote in the live village. |
| LED Controls | Choose built-in animations, adjust brightness, stop or switch off, and preview the synchronized zap celebration without paying. |

Only Pay 21 is installed by default. Open **App Market**, select an app, and choose **Install** then **Open**. This first marketplace installs entries from the catalog shipped with the project; it does not download or execute third-party apps. Installation state survives reboot. UI app modules are imported on open and released on exit. Outstanding invoices keep the receipt monitor running in the background, including after leaving Pay 21.

## Three-button controls

- Top right button (1): previous/up; holding repeats.
- Middle right button (2): next/down; holding repeats.
- Bottom right button (3): select on release.
- Hold bottom for 0.8 seconds: back; from an app's top-level screen, return home. Holding never also selects.
- The joystick is ignored throughout the device. Choose **App Market** from the launcher to install/open/remove apps. Installed app details provide Open and Remove as selectable actions.
- On a payment QR, any short button press opens its action menu; hold bottom to go back. In Sky, select a direction to start walking; select it again or choose Stop to stop. Jump, emotes, run, and account actions are entries in the same menu.

The QR uses all 240×240 pixels, including its required white quiet zone. The display is rotated 90° clockwise. Paid confirmation draws immediately and starts cached audio; the Bluetooth link adds its own playback latency. Voice synthesis runs on the development computer, not the Pi.

## Pi setup

Use Raspberry Pi OS Lite, enable SPI, and install the system libraries:

```sh
sudo apt-get install python3-venv python3-pil python3-numpy python3-spidev python3-gpiozero python3-lgpio pulseaudio pulseaudio-module-bluetooth
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pocket
```

Run from the project root. The Pi user needs SPI and GPIO access. Pair the speaker with Bluetooth bonding enabled and select its A2DP output. Set `POCKET_AUDIO_SINK` to the PulseAudio sink name if using an explicit output. A service template is in `scripts/nostr-wot-pocket.service`.

Runtime state lives in `~/.local/share/nostr-wot-pocket` (`POCKET_STATE_DIR` overrides this). It includes installed apps and outstanding invoices and must not be committed. No wallet spending keys are needed. The payment app creates an ephemeral signing key for each zap request and trusts receipts only from the public key advertised by the configured recipient's LNURL server. It also checks the exact invoice, recipient, event signatures, description hash, amount, and optional preimage. A receipt is the provider's attestation of payment; it is not an independently verified Lightning settlement proof.

Changing the payment recipient requires updating the recipient identity, provider identity, and LNURL endpoint together in `pocket/zap_backend.py`.

## Sky remote signer setup

Sky is an optional miniapp. Its Node process and signer SDK start only when you choose **Connect**. The Python launcher and payment app do not need Node.

On the development computer, run `npm ci --prefix bridge` and `node scripts/build-sky.mjs`. Copy `bridge/dist/sky-bridge.mjs` with the project to the Pi. Install an official Node.js 22 ARM64 runtime in `~/.local/node` on the Pi, or set `POCKET_NODE` to an existing Node executable. Verify the runtime against Node's published SHA-256 checksums before extracting it. The deployment used Node v22.23.4.

Open Obelisk Sky, choose **Connect signer** with top/middle, then press bottom to select. Scan the full-screen `nostrconnect://` QR in a compatible remote signer (for example Nostr WoT). Approve only `sign_event:20390` (movement) and `sign_event:22242` (relay AUTH), with auto-approval if you want responsive movement. Your account private key stays in the signer. A separate NIP-46 client transport key is stored with mode 0600 in `sky-session.json` in the runtime state directory, so you can reopen the app without pairing again. Choosing **Forget signer** deletes that local session; also revoke it in the signer when desired.

The default village relay is `wss://public.obelisk.ar`. The account must be admitted there, and other viewers must be on the same relay. Existing Sky clients render the native ephemeral kind 20390 events from this controller. A browser signed into the *same account* treats its own avatar as locally controlled and ignores remote motion for it; view from another admitted account to see the Pi avatar. The browser's own NIP-46 movement restriction does not prevent it from rendering other users' valid movement events.

Sky uses the same three-button menus as the launcher. Select north/east/south/west to walk continuously; select the active direction again or choose Stop to stop. Jump, Choose emote, Toggle run, and Account are selectable actions. Choosing an emote stops walking and one bottom-button confirmation sends it once. Hold bottom to leave a submenu or close the app. A first version is deliberately limited to the plaza, avoids the Obelisk plinth, and uses finite short destinations so a broken connection cannot cause endless movement. It does not run Sky's full building collision map. Signed events are checked against the requested template and expected user key; no posting, wallet, encryption or profile-edit permissions are requested. The map distinguishes connecting, relay acknowledgement, and receipt of your own event back from the relay; it does not claim a second human viewer is connected.

Pairing and human signature approval remain pending until you cancel; they do not have the SDK's old pairing timer or a short signature deadline. The production bridge uses the same underlying `nostr-tools` NIP-46 handshake with explicit cancellation and is tested alongside the SDK for compatibility. Account, relay-login and movement approval are separate UI states. The paired transport is saved before an account-access approval finishes, so that phase can resume after reopening. Late movement signatures are validated but not published with stale positions; the current action is signed afresh after approval instead. Pending emotes retain the selection and refresh their animation start time, so one confirmation is sufficient.

The same flow can use La Crypta's relay via `POCKET_SKY_RELAY=wss://lacrypta-relay.obelisk.ar` for a new pairing. A restored session keeps its previously selected relay. Movement events are capped to about one per second (jump exception 400ms), with backoff and a 30-second idle heartbeat.

Test without posting to any real relay: `node --test bridge/*.test.mjs`. `scripts/build-sky.mjs` bundles only the needed SDK subpath and dependencies; do not copy development `node_modules` to the Pi.

## BLE LEDs and synchronized zap celebration

Install the optional dependency with `.venv/bin/pip install -r requirements-ble.txt`. Set `POCKET_LED_ADDRESS` to the explicitly identified controller's MAC, `POCKET_SPEAKER_ADDRESS` to the paired speaker, and `POCKET_AUDIO_SINK` to its A2DP sink. These device addresses belong in private service configuration, not source. `POCKET_LED_BRIGHTNESS` defaults to 100/1000 (10%) for the color phase. At the user's request the opening is now solid full-strip white at 1000/1000 for 0.6 seconds, then the color phase returns to the selected level. The LED Controls slider can change that base level explicitly; brightness is a setting, not measured electrical power.

The worker holds the BLE connection while the JBL uses classic Bluetooth audio, and Wi-Fi stays enabled. It reconnects if the strip disappears; speaker maintenance checks for the audio sink and reconnects the paired speaker if missing. The JBL must be paired with bonding enabled; this was confirmed with `Paired: yes`, `Bonded: yes`.

A verified receipt for a Pay 21 invoice first draws the paid screen, then triggers cached audio and the preconnected LED worker. The pattern opens with full-white maximum brightness, uses red/yellow moving effects and rapid orange/yellow/white/other whole-strip colors, then turns all lights off. Startup/reconnect also leaves the strip off. **Custom yellow/orange halves and arbitrary individual pixels are not implemented or claimed.** A bounded prefix-overwrite experiment tests whether the count setting can preserve an orange second half while writing a yellow first half, but this must be visually verified before becoming a supported pattern.

Use **LED Controls → Zap + sound TEST** or **Thunder Lab → Zap + lights TEST** for a free preview. These do not create invoices, claim a payment, or change the receipt ledger. Selecting another light command cancels a preview. Holding bottom to leave the preview stops its audio and turns the lights off. Manual lighting remains active while using LED Controls; leaving that app turns the strip off. Off switches the lights off now; a subsequent valid zap celebration turns them on for the burst and off again afterward.

Observed transport, tested packets, corrections to early guesses, and the research boundary are in [docs/led-investigation.md](docs/led-investigation.md).

## Miniapp development

Each miniapp exports `App(context)` with `handle(keys)`, `tick(now)`, `render()`, and `close()` methods and a `dirty` flag. Add its public metadata to `catalog.json`. Display, input polling, lifecycle, and receipt notifications belong to the shell. Do not initialize GPIO inside a miniapp.

```sh
.venv/bin/python -m unittest discover -s tests
```

This device implementation uses Python and Nostr/Lightning protocols directly, rather than running a browser extension or the TypeScript SDK on the Pi.

See [THIRD_PARTY.md](THIRD_PARTY.md) for asset and driver provenance. Repository access is private initially.

### Invoice outages and address QR

Pay 21 renders QR codes locally using the existing Python dependencies. The fixed 21-sat invoice flow makes two public JSON requests: LNURL-pay discovery, then its callback with a signed NIP-57 request. It needs no wallet API key. The extension instead creates deposit invoices with authenticated `POST /api/v1/payments` and renders their QR locally; that API still depends on the invoice server.

If invoice creation fails, the display reports HTTP server errors separately from network failures. Press 1 or 2 on the error screen to display a locally generated `lightning:avidflower48@walletofsatoshi.com` address QR; press 3 to retry invoice creation. The address QR lets a compatible wallet choose the amount. It still requires the recipient server when paying, and does not create a tracked 21-sat invoice or trigger device payment confirmation or celebration. Press a button to return from the address QR.

### Automatic invoice provider fallback

Every new 21-sat invoice tries `fabri@nostrwot.com` (WoT/LNbits) first. Network failures, timeouts, HTTP 408/429 and HTTP 5xx errors trigger a second attempt at `avidflower48@walletofsatoshi.com` (Wallet of Satoshi), using its public LNURL-pay API. Other 4xx responses, changed provider identities and invalid invoices fail closed. The invoice QR fills the entire 240×240 screen with nearest-neighbor scaling; the receiving address appears on the payment details screen. No wallet API key or new server is required.

Each invoice saves its receiving address and pinned provider signing key. Receipt subscriptions include both providers and still require an exact matching invoice, signed zap request, recipient, amount and description hash before celebrating. Existing saved WoT invoices remain valid. Returning to create another invoice always tries WoT first. A fallback payment goes to the Wallet of Satoshi wallet, not the primary wallet.

Receipt monitoring also connects to `wss://relay.ditto.pub`. A paid Wallet of Satoshi invoice was observed there with a valid matching signed receipt while neither original relay held it. The same relay list is sent in new zap requests; reconnect queries replay pending invoices so missed receipts can confirm after restarting.

## Audio reactive lights and Mac playback

LED Controls has **React to audio**, **Reactive thunder TEST**, **Bass/treble TEST**, and **Audio/light delay**. Live mode captures only the configured JBL sink monitor through `parec`: no microphone, recording file, wallet API, or new network service is used for analysis. It follows any audio routed through that speaker, including Mac music and payment sounds. Bass maps to warm orange, mids purple, and treble cyan. RMS attack/release controls brightness, capped by the existing brightness setting; silence turns the strip off. This uses whole-strip color/brightness, without claiming individual-pixel effects.

The renderer is capped at 5 updates/second over the existing BLE link. Each packet uses an acknowledged write and a 35 ms gap. Audible frames use 40–100% of the configured brightness limit, keeping low-energy output visible; silence still switches off. Repeated commands are suppressed, stale frames are dropped, and delayed frames are bounded. Payment celebrations and free cached previews use a cached PCM feature timeline tied to the same monotonic playback origin. Stopping previews or selecting another lighting command cancels the audio and lights together. Live monitoring resumes after a payment celebration if it was enabled. Lights off or leaving LED Controls disables live mode. Controller disconnects do not replay old cached celebrations. The current BLE controller has no verified timeout command: a sudden link loss may leave its last color active until reconnection powers it off; guaranteed fade-on-link-loss requires controller support.

Lighting delay defaults to **+150 ms**, adjustable in 25 ms steps through LED Controls (−500 to +1000 ms). `POCKET_AUDIO_LED_DELAY_MS` supplies the startup default. Positive values delay the lights; a live stream cannot predict future sound. The offset is an initial estimate and requires listening/visual calibration after speaker reconnects. Brightness and delay adjustments are runtime settings. Run `python scripts/build-reactive-demo.py` to rebuild the original bass/mid/treble calibration clip.

### Mac → Wi-Fi AirPlay → Pi → Bluetooth JBL

The Pi can receive Mac audio over Bluetooth and forward it to the JBL, but this setup produced audible stuttering and PulseAudio underruns with two simultaneous Bluetooth audio links. Increasing the loopback buffer did not resolve the reported audio quality. Use the packaged `shairport-sync` AirPlay receiver over Wi-Fi instead, leaving Bluetooth for the JBL and BLE controller. AirPlay adds buffering and is intended for music, not low-latency monitoring.

The device deployment installs `shairport-sync`, copies `ops/shairport-sync-override.conf` to `/etc/systemd/system/shairport-sync.service.d/pocket.conf`, and restarts that service. The override runs as `pi` against its existing PulseAudio server; `ops/shairport-sync.conf` advertises **WoT Pocket** and uses the default audio sink, which must be the JBL. On the Mac choose **WoT Pocket** from Sound output/AirPlay, rather than the Bluetooth device named **pizero**. Both computers must share a network that permits multicast discovery. The Mac remains paired for optional testing but its Bluetooth audio link was disconnected. Wi-Fi power saving was disabled at runtime during troubleshooting.

## Mini PC server and LAN calibration

The project also runs headless on the mini PC, with AirPlay input, Bluetooth JBL output, live BLE lighting, invoice QR export and receipt monitoring. Open **http://192.168.0.148:8787** for effects, brightness, timing, beats per color and sound tests. Changes preview live; **Save settings** persists them. The existing multicolor effects remain available alongside beat-counted color tails, chases and brightness builds. See [mini PC installation and operation](docs/mini-pc-server.md).
