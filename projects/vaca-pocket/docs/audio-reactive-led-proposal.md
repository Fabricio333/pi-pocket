# Real-time audio-reactive lighting for Nostr WoT Pocket

Status: initial whole-strip BLE implementation in `nostr-wot-pocket/pocket/audio_reactive.py`. Live speaker-monitor analysis, cached PCM timelines, cancellation, brightness limits and timing controls are implemented. Physical synchronization and audio stability still require validation on the device; spatial effects remain unverified.

## Goal

Make the LED strip respond continuously to the sound coming from the Bluetooth speaker: bass pulses, beat-driven motion, frequency-based colors and synchronized thunder flashes.

The lighting should follow the actual audio rather than play an unrelated preset animation. Payment celebrations should use the same lighting engine, with reliable cancellation and a clean return to idle.

## Current setup and open questions

The setup uses a Raspberry Pi Zero 2 W, a Bluetooth speaker and a BLE LED controller. Previous device investigation established control over whole-strip colors and some controller-generated effects. It did not establish arbitrary control of individual LEDs.

We need to determine:

- Whether the strip is conventional RGB or individually addressable.
- Its voltage, controller model, connector labels and wiring.
- Whether its controller exposes usable real-time updates or only preset commands.
- How much delay the Bluetooth speaker introduces during actual playback.

Do not infer individual-pixel control from a moving built-in effect. A controller can generate spatial effects without exposing pixel data to another device.

## Recommended architecture

Analyze audio on the Pi and render LED effects on a dedicated controller. Keep the speaker connected through Bluetooth.

```text
Audio file or playback stream
            |
       Decoded PCM audio
            |
       +----+---------------------+
       |                          |
Bluetooth playback          Audio analysis
       |                   bands / beats / energy
Bluetooth speaker                 |
                         Synchronization buffer
                                  |
                         Small Wi-Fi updates
                                  |
                         LED effect controller
                                  |
                              LED strip
```

The Pi sends musical features rather than a network packet for every LED. The controller interpolates between updates and produces smooth animation locally. This separates audio analysis from the timing-sensitive work of driving an addressable strip.

For a conventional RGB strip, the same features can drive whole-strip brightness and color. Waves, chases and distinct colored sections require hardware that supports spatial control.

## Audio source options

| Source | Advantages | Limits |
| --- | --- | --- |
| Decoded audio from our own player | Clean signal, known playback position, no microphone needed | Requires access to the playback pipeline |
| Playback monitor or loopback | Can follow other applications playing through the Pi | Depends on the audio server and routing |
| Microphone near the speaker | Follows external music and the sound actually heard | Picks up speech and room noise; needs separate hardware and calibration |

Start with our own cached audio files. Precompute their feature timeline where useful, then synchronize that timeline to playback. This reduces CPU load for repeated celebrations. Use streaming analysis when supporting arbitrary or live audio.

## Audio analysis

Process small overlapping PCM windows and extract:

- **Level:** RMS energy with a noise floor, attack and release smoothing.
- **Frequency bands:** bass, midrange and treble energy using an FFT or filters.
- **Onsets:** sudden energy changes for kicks, snares and thunder attacks.
- **Beat confidence:** optional tempo tracking for steady music. Avoid forcing a beat grid onto speech or thunder.

Normalize gradually so quiet and loud tracks remain expressive. Cap gain around silence to prevent background noise from producing maximum brightness. Apply hysteresis or a short cooldown to avoid multiple triggers from a single hit.

Initial engineering targets are 20–50 feature updates per second and 30–60 animation frames per second on the controller. These are targets to measure on the actual hardware, not guaranteed performance. Start with one analysis worker and measure CPU load, audio underruns and network jitter on the Pi.

## Effect ideas

| Effect | Audio input | Behavior | Hardware |
| --- | --- | --- | --- |
| Bass glow | Smoothed bass energy | Warm brightness pulses with a fast attack and slower decay | Whole-strip RGB or addressable |
| Frequency palette | Relative band energy | Bass drives warm colors, mids purple and treble cool highlights | Whole-strip RGB or addressable |
| Beat chase | Confident onset events | A moving segment advances on each hit and leaves a fading trail | Spatial control |
| Bass wave | Bass onset and intensity | A wave expands from the center; stronger hits travel farther | Spatial control |
| Treble sparks | High-frequency transients | Short highlights appear over a slower background | Spatial control |
| Thunder storm | Audio envelope and transient timing | A bright attack, smaller follow-up flashes and a warm decay | Whole-strip RGB; spatial control adds branching motion |

Use a small number of layers: a background, one main movement and occasional highlights. Blend them within an overall brightness limit so the result remains readable rather than becoming continuous flashing.

## Synchronizing with the Bluetooth speaker

Bluetooth playback introduces delay. Sending light commands as soon as PCM is submitted can make the LEDs lead the sound.

Measure the difference between an audible click and its matching light flash, then apply an adjustable lighting delay. Use playback timing information where available and calibrate the remaining offset. Recheck after speaker reconnection, routing changes or playback restarts.

Use a monotonic clock for the local feature timeline. For scheduled rendering on another controller, estimate the clock offset and include sequence numbers and presentation times. Drop stale updates rather than replaying a backlog. If clock synchronization is not implemented initially, use immediate rendering and calibrate the measured end-to-end delay.

For a microphone-based implementation, the input already includes the speaker's playback delay. Compensate only for analysis and lighting latency; do not add the Bluetooth delay again.

## Controller and transport

A dedicated controller, such as an ESP32-based design, can accept feature updates over Wi-Fi and generate effects locally. The final board, firmware and strip must be selected after checking hardware compatibility.

A compact feature message can contain a sequence number, presentation time, level, three band energies, onset strength and effect selection. Prefer replacing old state with newer state over accumulating queued updates. A lost transient should not leave the strip stuck on.

BLE remains a possible experiment for modest whole-strip updates on the existing controller. Its supported protocol, command throughput and coexistence with Bluetooth speaker audio need measurement. It is not yet a verified path for smooth spatial effects.

The Pi and Wi-Fi LED controller must share a reachable network. Keep high-frequency rendering on the controller so network jitter does not directly become visible animation jitter.

## Playback and payment integration

The lighting engine should support start, stop, effect selection, brightness and a playback position or timing reference.

A verified payment starts one synchronized audio-and-light celebration. Starting another manual effect or cancelling a preview should stop the previous animation cleanly. No lighting event should mark an invoice paid: payment verification remains separate from the effects engine.

If the controller disconnects, audio may continue. When updates stop, the controller should fade to a defined idle state. Reconnecting must not replay an old celebration.

## Hardware checks before implementation

Identify voltage and strip type before connecting a new controller. For addressable LEDs, confirm the data protocol and whether level shifting is required. For conventional RGB, confirm that the controller's output stage matches the strip's voltage and current.

Use an appropriate power supply, wiring and brightness limit for the strip. Do not power a substantial LED load from the Pi's GPIO. Power-injection and fusing requirements depend on strip length and current.

## Implementation sequence

1. Identify the existing strip and controller; document which capabilities are proven.
2. Prototype audio analysis on one cached thunder track and one music clip.
3. Measure CPU load and audio stability while Wi-Fi and Bluetooth are active.
4. Drive a simple whole-strip pulse, then calibrate sound-to-light timing.
5. If spatial control is available, add a bass wave and beat chase.
6. Add cancellation, reconnect handling and the controller's idle timeout.
7. Integrate the verified-payment trigger and free preview controls.

## Acceptance criteria

- Bass-heavy sections visibly differ from treble-heavy sections.
- A quiet passage settles toward idle rather than producing random full-brightness flashes.
- A click/flash calibration makes timing adjustable and repeatable.
- Playback remains stable while analysis and lighting run.
- Cancelling a preview stops its audio and lighting without a later queued burst.
- Lost network updates cause a controlled fade to idle.
- Only a verified payment triggers the payment-confirmation flow.
- Any spatial effect is demonstrated on the physical strip before it is described as supported.

The first decision is hardware capability. We can build useful audio-reactive whole-strip lighting with basic RGB control; individually moving waves and sparks require verified spatial control.
