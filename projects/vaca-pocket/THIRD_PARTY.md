# Third-party materials

- Nostr WoT icon and lockup: https://nostrwot.com/icon-512.png and https://nostrwot.com/brand/nostr-wot/lockup-dark.svg. Brand ownership remains with Nostr WoT. Included for this project's requested branding; no independent trademark license is implied.
- Waveshare `ST7789.py` and `config.py`: official demo archive https://files.waveshare.com/upload/b/bd/1.3inch_LCD_HAT_code.7z. The configuration file retains the manufacturer's MIT permission notice. The import is adjusted for Python package use.
- DejaVu Sans fonts: copied from the development machine's DejaVu font package. Original license text is retained in `assets/fonts/LICENSE`.
- Announcement voice: synthesized locally with Piper using `en_US-lessac-medium` from https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/lessac/medium. Voice model card is retained in `assets/audio/VOICE_MODEL_CARD`. Model weights are not included. Piper: https://github.com/OHF-Voice/piper1-gpl.
- Thunder effects: procedurally synthesized for this project; no external recordings used.

Dependency licenses remain with their respective projects. No general source license has been selected for this private project yet.

The optional Sky bridge uses `nostr-wot-sdk/signers` (GPL-3.0-only), `nostr-tools` and `ws`; versions and dependencies are locked in `bridge/package-lock.json`. The source and reproducible bundle build remain in this repository. Node.js is downloaded separately from nodejs.org and is not committed. Sky wire compatibility references the public Obelisk Sky `client/src/nostr/motion.ts`, `client/src/player/controller.ts` and `client/src/nostr/remoteSigner.ts`; this project does not modify or deploy the Sky website.

The additional multicolor effect identifiers follow the documented Findn controller mapping in [ha-findn-led-ble](https://github.com/hirotasoshu/ha-findn-led-ble/blob/main/custom_components/findn_led_ble/device_protocol.py). No spatial pixel-buffer API is inferred from these built-in effects.
