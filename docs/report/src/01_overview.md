# Project Overview and Engineering Objective {#ch-overview .chapter}

## The project in one paragraph

Think of a smart speaker, but split in two. A small, cheap chip sits in the room and does only one job: it waits to hear one particular phrase, **"Hey Vayro"**. It never sends the room's sound anywhere while it waits. When it hears the phrase, it immediately starts sending the audio — including a little of what came just before, so nothing is cut off — to a more powerful computer that works out what the person asked for ("turn on the light"). The chip is an **ESP32-S3** microcontroller with a digital **INMP441** microphone; the computer is a PC running an open-source speech recogniser. The project's job was to make the chip's part small, fast, accurate and provably within the limits the problem statement sets. [VERIFIED]

!fig #fig-overview figures/overview.svg | The whole system in five steps. Everything left of the dashed arrow runs continuously on the ESP32-S3; everything right of it runs only after a detection. | 100

## The problem being addressed

The problem statement (PS 26172, from ISRO) describes a common situation in voice-controlled devices. If a device sends *all* sound to a cloud recogniser, three things go wrong: it costs a lot (the server processes silence and background noise all day), it invades privacy (the room is always being recorded somewhere else), and it is slow (every request waits for the network). The PS asks for a **hybrid**: the edge device handles the "wake-up" moment locally, and the cloud does the heavy recognition only after that. [VERIFIED — PS text]

Technically, the PS asks for three things (full list in Chapter 3):

1. A **keyword spotting (KWS)** model — a small neural network that recognises one phrase — running *locally* on a low-power device.
2. On detection, **streaming the audio that follows** to a remote **automatic speech recognition (ASR)** server, with minimal data overhead and latency.
3. Doing this under hard limits: **less than 256 KB of RAM and less than 10 % CPU while idle-listening**, open-source tools only, no vendor wake-word SDK, and a keyword that the team trained itself.

:::simple
"Keyword spotting" and "speech recognition" are different jobs. Keyword spotting answers one yes/no question over and over ("was that 'Hey Vayro'?"). Speech recognition turns any speech into words. The first is small enough for a microcontroller; the second is not. This project runs the first on the chip and the second on a PC.
:::

## Real-world use and intended users

The PS gives the setting only as "voice-controlled IoT" under the theme **Smart Automation**; it names no user group or deployment environment. The project did not define a specific deployment either. Everything tested ran in one home: a desk, a household with a television and family members, and a home Wi-Fi network. Application ideas that appear in the team's documents (laboratory control rooms, assistive use, home automation) are [PLANNED] ideas, not tested use cases. [VERIFIED — no deployment study exists in the repository]

## Main technical challenges

Table: The challenges that shaped the design {#tab-challenges}
| Challenge | Why it is hard | Where it is handled |
|---|---|---|
| Always-on listening inside 256 KB RAM and 10 % CPU | The microphone, feature extraction and model run 100 times a second forever; Wi-Fi and the TCP/IP stack also need RAM | Chapters 7, 12 |
| "Near-zero false activations" | A household is full of speech-like sound (TV, conversation, singing) and the model is tiny | Chapters 8, 10, 12 |
| A brand-new keyword with almost no real recordings | No public dataset says "Hey Vayro"; the team had one speaker at first | Chapter 8 |
| Train/deploy mismatch | A model trained on features computed on a PC fails silently if the chip computes them even slightly differently | Chapters 7, 13 |
| Not losing the start of the command | The chip only knows the keyword was said *after* it ends; by then the user may already be speaking | Chapters 6, 7 |
| Measuring latency honestly | "Keyword end → ASR receives audio" spans two computers with different clocks | Chapters 10, 12 |
| Open-source compliance | The ESP32's Wi-Fi driver is closed source; vendor wake-word SDKs are the obvious shortcut and are forbidden | Chapters 2, 5 |

## Expected system behaviour

In words, the system is meant to behave like this: while nobody says the keyword, the device listens, computes, and sends nothing but occasional small clock-synchronisation packets. When someone says "Hey Vayro" and then a command, the device detects the keyword within a fraction of a second, and the server receives audio that starts shortly before the detection and continues until the speaker stops, then prints what was said. A second keyword said within two seconds of the first is ignored (the "refractory" period), and only one stream is open at a time.

## Input, processing, output

Table: What goes in, what happens, what comes out {#tab-ipo}
| Stage | What it is in this system |
|---|---|
| **Input** | Sound pressure at the INMP441 microphone, sampled 16 000 times a second as 24-bit numbers |
| Processing on the chip, every 10 ms | 160 new samples → 16-bit conversion → stored in a 0.75 s ring buffer → 40 log-mel "features" |
| Processing on the chip, every 60 ms | the last 100 feature frames (1.02 s) → int8 neural network → probability of "Hey Vayro" → average of the last 3 probabilities compared with 0.80 |
| **Output 1** (chip) | a detection event: telemetry line `@KW`, a pulse on GPIO15, and a stream request |
| **Output 2** (network) | audio packets: from 571 ms before the detection until the server says the speaker has stopped |
| Processing on the server | end-of-speech detection, 150 Hz high-pass filter + level correction, Vosk speech recognition |
| **Output 3** (server) | the recognised command text, plus WAV and JSON files recording exactly what arrived and when |

## Operating sequence

1. The board is powered from the PC's USB port. The firmware starts, waits for the PC's capture tool to open the port (up to 30 s), prints its identity and memory state, and checks the microphone.
2. It builds the feature extractor and the neural network, joins Wi-Fi, and opens one TCP connection to the server at a fixed address. It keeps that connection alive with a clock-synchronisation ping every 10 s.
3. From then on, core 1 processes audio in 10 ms steps without stopping; core 0 handles the network.
4. When the averaged score reaches 0.80, the device queues a stream request and carries on listening.
5. The streaming task sends a START message, then the 571 ms of stored audio as fast as the link allows, then new audio every 40 ms.
6. The server watches the level of the incoming audio. After 0.7 s of quiet (or 1.5 s with no speech at all) it tells the device to stop. The device sends END with its own statistics.
7. The server finishes recognition in a separate thread and prints and stores the transcript. The device is already listening for the next keyword.

## What was actually achieved

By 30 September 2026 the complete chain existed on real hardware and had been measured ([[tab-headline]] in the Executive Summary). The final firmware fits the strict RAM reading with about 5 kB to spare, idles below 10 % CPU on each core, detects the keyword with 88 % recall on a held-out session of the training speaker and 80 % on a new speaker, triggers falsely about once in five quiet hours but about 16 times an hour when a television is on, and delivers audio to the server a median 138 ms after the keyword ends. Chapters 10 to 14 give the evidence and the limits of each of these statements.
