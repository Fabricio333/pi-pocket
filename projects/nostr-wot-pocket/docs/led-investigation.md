# BLE LED investigation

Updated 2026-11-07. Goal: establish whether the existing 5 m strip (approximately 300 LEDs) can expose individual pixels or controllable sections through its present BLE controller.

## Hardware and transport observations

- Raspberry Pi Zero 2 W, Raspberry Pi OS Lite. Wi-Fi remained connected during the completed BLE scans and writes.
- User reports **three wires** from controller to strip and confirms the supplied app has effects. This is consistent with a digital data connection but does not establish chip type, LED voltage, or independently addressable pixel/group size.
- Advertised name: **GATT--DEMO**. Advertising service `2022` is not the actual primary control service. Use the explicitly selected device address, not a broad name filter that might adopt a neighbour's controller.
- `bluetoothctl` attempts sometimes reported “device not available” because the discovery entry expired or the fixed-delay connection ran before discovery found it. Bleak connected reliably using the actual scanned BLE device object.
- Connection does not require pairing. The BLE link and LED state are separate: colors persist after the client disconnects.

Observed GATT layout:

| Service | Characteristic | Properties | Observed handle |
| --- | --- | --- | --- |
| FFF0 | FFF3 | write, write without response | 13 |
| FFF0 | FFF4 | notify; CCCD 2902 at 17 | 15 |
| FF12 | FF15 | read, write without response | 19 |
| FF12 | FF14 | notify; CCCD 2902 at 23 | 21 |
| 1800 | 2A00 / 2A01 / 2A04 | device name / appearance / preferred connection parameters | 2 / 4 / 6 |
| 1801 | 2A05 | service-changed indication | 9 |

Expand short UUIDs as `0000xxxx-0000-1000-8000-00805f9b34fb`. Write control packets to **FFF3**. FF15's purpose is unknown; this investigation only reads it, never writes it.

## Confidence rules

“ATT write accepted” means Bluetooth delivered the write. It does **not** prove that firmware accepted the opcode, that the strip changed, or that only the requested LEDs lit. Visual outcomes below are kept separate from delivery logs. No LED-current or power measurements have been taken; a brightness setting is not a measured power limit.

## Commands and evidence

Wire frame: `BC <command> <payload length> <payload> 55`. One frame per GATT write.

| Purpose | Bytes | Confidence |
| --- | --- | --- |
| Fixed red | `BC 04 06 00 00 03 E8 00 00 55` | Combined working sequence resulted in user-confirmed whole-strip low red. H=0°, S=1000; this is not an RGB-triplet packet. |
| Brightness 10% | `BC 05 06 00 64 00 00 00 00 55` | Used in the confirmed low-red sequence. Level is per mille, separate from color. |
| Minimum reported brightness | `BC 05 06 00 03 00 00 00 00 55` | Delivered; strip was not visibly lit in the combined experiment. Do not assume the visible threshold is this low. |
| Power on | `BC 01 01 01 55` | Used in the confirmed low-red sequence; independently implemented in Findn integration. |
| Power off | `BC 01 01 00 55` | Established external protocol; not isolated as a local visual test yet. |
| Request configured count 1 | `BC 03 02 00 01 55` | Delivered but no one-LED result established. Outside secondary source's stated 8..300 UI range. No further count-1 probes planned. |
| Request configured count 8 | `BC 03 02 00 08 55` | Delivered; later fixed-red state still illuminated the whole strip. Not a successful segment selector. |
| Request configured count 300 | `BC 03 02 01 2C 55` | Delivered during comparison against 8; exact active length not visually established. |
| Red running | `BC 06 02 00 54 55` | Delivered in the completed trial; user confirmed the animation worked. |
| Red tailing | `BC 06 02 00 4D 55` | Delivered in the completed trial; no exact per-LED count captured. |
| Effect direction | `BC 07 01 01 55` forward; `BC 07 01 00 55` reverse | **Not a power command.** Earlier session descriptions incorrectly called this a power flag. |

Corrections to the initial experiments: `06` selects built-in effects, not a verified “static mode.” `07` controls effect direction. Never use arbitrary effect 0 or 1 as initialization; a fixed-color command exits effect mode in the independent implementation. A count configuration is not proof of an address/range-selection command.

## Visual history

1. A one-LED count, red, and brightness 1000 were delivered; the user reported nothing visibly lit. Individual command effects could not be isolated.
2. Sending the alternate `07` flag plus `01` on resulted in the user reporting the whole strip fading through colors. That established responsiveness, not individual LED addressing; later source review identified `07` as direction.
3. Count 8, undocumented effect 0, red, and brightness 3 resulted in the user reporting all off. No individual conclusion can be drawn about which command caused this.
4. Brightness 100, fixed red, the `07` direction flag, and `01` on resulted in **user-confirmed whole-strip low red**. This is the recovery baseline.

## Completed controlled trial

`probe-chase` applies only documented spatial effects at 10% brightness:

1. Requested count 8, red running forward, 10 seconds.
2. Requested count 300, same effect forward, 10 seconds.
3. Requested count 8, red tailing reverse, 10 seconds.
4. Restore requested count 8, fixed red, brightness 100, power on in `finally`.

The observer should distinguish a moving group of LEDs from the whole strip fading simultaneously, and note whether the active length changes between 8 and 300. Bluetooth writes alone cannot answer those questions. If the patterns move spatially, that demonstrates controller-generated spatial effects; it still does not establish an arbitrary per-pixel write API.

Executed 2026-11-07 21:27:27–21:28:03 UTC. All three stages completed and the restore writes were delivered. The user confirmed “the animation worked,” but an exact LED count or count-dependent active length was not established. No claim of arbitrary pixel control is made. Read-only FF15 returned `46 4F 54 41 00` (`FOTA\0`), identifying it as a firmware-related endpoint rather than an alternate lighting write channel. No writes were made to FF15.

## Speaker coexistence and app controls

The JBL Go 4 was paired with the adapter made bondable first. BlueZ reported `Paired: yes`, `Bonded: yes`, and `Connected: yes`, and PulseAudio exposed its A2DP sink. This fixes the earlier temporary pairing where `Bonded: no` caused reconnect failures. The app's peripheral worker maintains the BLE LED connection independently of classic Bluetooth audio. Wi-Fi is never disabled.

LED Controls now exposes documented spatial effects, steady red, off, brightness, and a free synchronized audio/light preview. The zap burst uses a white wipe, yellow and red running effects, then rapid whole-strip orange/yellow/white/other colors. Exact custom half-strip colors remain unavailable in the reviewed API. All device navigation now uses top/middle/bottom buttons; the joystick is ignored.

A later user-reported completed payment had no receipt on fresh queries to the two requested relays. This is recorded as a missing confirmation, not a failed or unpaid Lightning transfer. Investigation of that receipt was deferred at the user's request while finishing device controls; the hardware preview does not require another payment.

Subsequently the running service logged a verified 21-sat receipt at 21:53:43 UTC on November 7. This confirms a valid receipt arrived; it does not establish which previously reported wallet payment it corresponds to or visually confirm the audio/light response.

## Requested maximum-white opening and idle-off change

The user subsequently requested a maximum-white opening, then simultaneous differently colored halves, and all off when idle. The implemented opening is fixed white (`H=0,S=0`) followed by brightness 1000 for 0.6 seconds. Subsequent colors return to the base brightness. The final cleanup, startup/reconnect, and leaving LED Controls now send power off rather than restoring dim red.

The exact half-strip requirement remains unverified. A bounded experiment requests count 300 and orange, then count 150 and yellow, holding for eight seconds. This tests a possible prefix-overwrite behavior of addressable LEDs; it is not based on a known segment-address API. It restores the earlier count request of 8 and powers off in `finally`. The counts are configuration requests, not claims of physical pixel counts. No unsupported opcode or firmware characteristic is used.

Commands:

```sh
.venv/bin/pip install -r requirements-ble.txt
.venv/bin/python -m pocket.ble_led --address <LED_MAC> inspect
.venv/bin/python -m pocket.ble_led --address <LED_MAC> probe-chase --seconds 10
.venv/bin/python -m pocket.ble_led --address <LED_MAC> red --brightness 100
```

On this Pi the existing environment is `~/wot-venv`. Runtime logs go to `~/.local/share/nostr-wot-pocket/led-experiments.jsonl`; that private runtime directory is not part of the repository. Test plans and subsequent visual outcomes belong in this document.

## Open questions

## Payment-to-light delivery follow-up (November 7, 2026)

The user reported that free light previews worked but actual zaps did not activate the strip. The service logged verified 21-sat receipts at 21:53:43 and 21:58:49 UTC, so receipt validation succeeded. Those logs alone did not establish delivery to the display or LED worker. The exact original cause was not conclusively isolated.

Commit `4ab9092` routes the launcher's paid-screen handler directly to the same `celebrate()` function used by previews and adds logs for receipt queueing, UI receipt delivery, paid-screen drawing, LED queueing, and animation start/finish. The service was restarted with the updated modules.

A one-shot diagnostic replays an already-paid stored receipt: write its receipt ID to the private runtime `replay-receipt` file, then restart the service. The launcher accepts only an ID matching a stored paid record. This replays the confirmation and effects without creating an invoice, changing the payment ledger, or charging anything. It is an effects diagnostic, not a new settlement check.

The latest already-verified receipt was replayed at 22:00:45 UTC. Logs confirmed the paid-screen handler and LED queue, BLE connection at 22:00:50, animation start, and animation completion with lights off at 22:00:55. The 16 Python tests passed. A fresh live zap after this change has **not** been verified; replay success must not be described as a complete live-payment test. Simultaneous yellow/orange halves also remain visually unconfirmed.

## Remaining controller questions

- Exact strip/controller model, pixel chipset, supply voltage, and number of physical LEDs per addressable IC remain unknown.
- No reviewed implementation exposes an LED index, start/end segment, or raw pixel-buffer write. This is **not proof of impossibility**; it is the present evidence boundary.
- `03` count is reported in the decompilation notes but absent from the independent Home Assistant integration. It might apply only to some firmware or effect geometry.
- Unsupported arbitrary opcode fuzzing is intentionally avoided; timers, firmware-related characteristics, device identifiers, and RGB-order configuration are not modified.

## Sources

- Primary Findn implementation: https://github.com/hirotasoshu/ha-findn-led-ble/blob/main/custom_components/findn_led_ble/device_protocol.py
- Independent framing and cold-start notes: https://github.com/ronnygeo/GlowBridge/blob/main/docs/PROTOCOL.md
- Secondary reverse-engineering notes, including the unconfirmed count setting: https://github.com/Luiscrespo-bot/Tira-led/blob/main/Solucion

## Audio reactive prototype (November 9, 2026)

The first implementation uses the known whole-strip color, brightness and power commands at a 10 Hz feature rate. It analyzes cached PCM audio for payment celebrations and a live PulseAudio monitor of the JBL output for Mac music. No arbitrary pixel writes, firmware configuration or strip-count changes are involved. Bass, mids and treble choose a warm/purple/cyan palette; RMS attack/release controls brightness within the configured level. Silence turns the lights off.

A seven-second original calibration clip produced 100 captured feature frames over a 10-second measurement interval, a nonzero peak of 0.978 and 62 BLE writes. Before playback the same engine reported peak zero and just the initial three off-state writes. The service stayed connected. These are signal/transport observations, not confirmation of visible color accuracy or acoustic synchronization. All 37 Python tests passed on the Pi after deployment.

Mac Bluetooth input plus JBL Bluetooth output caused user-reported lag/stuttering and PulseAudio logged repeated underruns. A 300 ms explicit loopback buffer did not resolve the report. The Mac Bluetooth input was disconnected and the packaged Shairport Sync receiver configured as **WoT Pocket** over Wi-Fi, forwarding through the existing JBL sink. Mac AirPlay playback and listening/visual calibration remain user validation steps.

### Reactive commands versus working static commands

The user subsequently confirmed that simple LED commands worked while the sound tests did not light the strip. The first implementation's successful BLE writes therefore did not establish a visible reactive effect. The renderer now uses the working color→brightness→power-on order when waking, acknowledged writes with 35 ms gaps, a 5 Hz ceiling, and an audible-frame brightness floor of 40% of the configured limit. Silence still powers off. Physical retesting remains required; these changes address plausible packet pacing and visibility causes rather than claiming a proven firmware diagnosis.
