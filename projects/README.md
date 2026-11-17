# Vaca Inteligente Pocket backup

`vaca-pocket/` is the source backup of the working Pi Zero 2 W Pocket system,
including the Waveshare screen driver, three-button launcher, existing miniapps,
JBL/PulseAudio playback, dedicated Sats Bell wallet client, Wi-Fi hotspot setup,
service installers, test suite and third-party license notices.

This runs on Raspberry Pi OS with NetworkManager. It is kept here as a project
backup; it is not automatically included in the SeedSigner Buildroot image.

Source: https://github.com/Fabricio333/vaca-pocket/tree/feat/pi-satsbell-wifi
Source commit: `89f064c0d775e9bfce1c058d7ced2cc9f0d1a7cf`

See `vaca-pocket/README.md` for the base installation and
`vaca-pocket/docs/satsbell.md` for Sats Bell and phone Wi-Fi setup.
88 development tests passed; live provisioning/address claim, launcher startup,
JBL connection and audio playback completed on the Pi. The confirmed 22-sat payment was recovered once after fixing the service address
alias mismatch. Phone camera/hotspot transition still requires verification.

This source backup excludes wallet databases, private identities, API keys,
Wi-Fi passwords and login credentials. Preserve the private runtime database
separately using the instructions in the Sats Bell guide.
