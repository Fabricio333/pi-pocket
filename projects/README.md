# Raspberry Pi Pocket system backup

`nostr-wot-pocket/` is the source backup of the working Pi Zero 2 W Pocket system,
including the Waveshare screen driver, three-button launcher, existing miniapps,
JBL/PulseAudio playback, dedicated Sats Bell wallet client, Wi-Fi hotspot setup,
service installers, test suite and third-party license notices.

This runs on Raspberry Pi OS with NetworkManager. It is kept here as a project
backup; it is not automatically included in the SeedSigner Buildroot image.

Source: https://github.com/Fabricio333/nostr-wot-pocket/tree/feat/pi-satsbell-wifi
Source commit: `4cae763bd3b959fc5945d569db7e8ed88b4743af`

See `nostr-wot-pocket/README.md` for the base installation and
`nostr-wot-pocket/docs/satsbell.md` for Sats Bell and phone Wi-Fi setup.
67 development tests and 14 on-device tests passed; live provisioning/address claim, launcher startup,
JBL connection and audio playback completed on the Pi. The confirmed 22-sat payment was recovered once after fixing the service address
alias mismatch. Phone camera/hotspot transition still requires verification.

This source backup excludes wallet databases, private identities, API keys,
Wi-Fi passwords and login credentials. Preserve the private runtime database
separately using the instructions in the Sats Bell guide.
