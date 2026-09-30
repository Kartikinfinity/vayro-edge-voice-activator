# Hardware Inventory and Technical Specifications {#ch-hardware .chapter}

## Inventory

The hardware is deliberately minimal: one microcontroller board, one microphone breakout, a USB cable to a PC, and the household's Wi-Fi router. There is no codec, no amplifier, no level shifter, no external RAM in use, no logic analyser and no loudspeaker test rig.

Table: Hardware actually used (and what was planned but not available) {#tab-hw}
| Item | Role | Physically used and tested? | Evidence |
|---|---|---|---|
| ESP32-S3 development board ("N16R8": 16 MB flash, 8 MB PSRAM) | runs capture, features, model, decision, Wi-Fi streaming | yes — every run | esptool identification `evidence/m1/esptool_flash_id.txt` [VERIFIED] |
| INMP441 MEMS microphone breakout (TDK InvenSense part) | the only sensor: digital audio over I2S | yes — every run | M1 runs E-02…E-05, E-18 [VERIFIED] |
| USB cable to the PC (native USB port of the S3) | power, flashing, console, telemetry and data capture | yes | `@BOOT reset=USB`, COM7 [VERIFIED] |
| Home Wi-Fi access point (2.4 GHz) | LAN between the board and the server PC | yes | `@NET wifi=up` [VERIFIED]; model not recorded [UNVERIFIED] |
| Desktop PC (Windows 11, Intel i3-8100, 4 cores, 15.9 GB RAM, no GPU) | ASR server, build host, training host (via WSL2) | yes | PROJECT_STATE §6 [DOCUMENTED] |
| Logic analyser (for GPIO duty-cycle and detection-pulse timing) | planned primary CPU and latency instrument | **no — not available** | C-06 [VERIFIED] |
| Loudspeaker playback rig with a GPIO marker (IN-1) | planned ground truth for "keyword end" | **no — not built** | [PLANNED] |
| 100 kΩ pull-down resistor on SD; 0.1 µF decoupling at the mic | recommended by the study (P-07, P-24) | **not recorded** | [UNVERIFIED] |

## The microcontroller: ESP32-S3

### What the chip is

The ESP32-S3 is a system-on-chip from Espressif: two processor cores, on-chip RAM, Wi-Fi and Bluetooth radios, and many peripherals on one piece of silicon. For this project the relevant parts are the two cores (one for audio, one for networking), the internal RAM (the budget), the I2S peripheral with DMA (the microphone), the vector instructions used by the neural-network kernels, the USB port (debugging and evidence), and Wi-Fi (streaming).

### Measured identity of this board

The first thing done with the board (26 Sep) was to read its identity with esptool and back up its entire flash — it held an unrelated Arduino sketch from 2024 (`D:\ps26172_backup\preexisting_flash_16MB.bin`). [DOCUMENTED]

Table: Chip identity reported by esptool v4.12.0 {#tab-chipid}
| Property | Value |
|---|---|
| Chip | ESP32-S3 (QFN56), revision v0.2 |
| Features | Wi-Fi, BLE, **embedded PSRAM 8 MB (AP_3v3)** |
| Crystal | 40 MHz |
| USB mode | USB-Serial/JTAG (native port, appears as COM7) |
| Flash | 16 MB, quad SPI, 3.3 V (flash ID manufacturer 0x68, device 0x4018) |

8 MB of in-package PSRAM corresponds to the "R8" variant, which the study notes is octal PSRAM and occupies GPIO35–37 [INFERRED from the study's variant table]. It does not matter here because **PSRAM is disabled in the firmware** and none of those pins is used. The firmware is also built for **4 MB of flash** (`CONFIG_ESPTOOLPY_FLASHSIZE_4MB`) although the chip has 16 MB; the firmware's own `@BOOT` line therefore reports `flash_bytes=4194304`, and the esptool reading is the authoritative one. [VERIFIED]

The physical board's maker and model, and whether it sits on a breadboard, are **not recorded** anywhere in the repository. [UNVERIFIED]

### Specifications that matter to this design

The following facts are quoted from the architecture study, which cites the ESP32-S3 datasheet v2.2 by page. The datasheet itself was not supplied, so they are [DOCUMENTED]; where the project measured something, the measurement is given alongside.

Table: ESP32-S3 facts used by the design {#tab-s3spec}
| Property | Datasheet value (via the study) | How it is used / what was measured |
|---|---|---|
| CPU | 2 × Xtensa LX7, up to 240 MHz, single-precision FPU | run at 240 MHz (`CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ=240`) [VERIFIED] |
| Vector extension (PIE) | 128-bit SIMD instructions | used by esp-nn's int8 kernels (0.47 multiply-accumulates per cycle measured, E-23) [DOCUMENTED] |
| Internal SRAM | 512 KB (plus 384 KB ROM, 16 KB RTC RAM) | 96 KB configured as cache (32 KB instruction + 64 KB data); the application's heap is 289 708 B in the product build [VERIFIED — `@MEM`] |
| Cache | 16/32 KB instruction, 32/64 KB data | 32 KB I + 64 KB D chosen, "biased toward data" because model weights stream from flash [VERIFIED — sdkconfig] |
| I2S | 2 controllers, master/slave, 8–32-bit slots, BCK 10 kHz–40 MHz, DMA | I2S0 as master receiver, 32-bit slots, 1.024 MHz [VERIFIED] |
| GDMA | shared DMA channels for peripherals | I2S receive uses 4 descriptors × 160 frames [VERIFIED] |
| System timer | 52-bit, 16 MHz | microsecond timestamps via `esp_timer_get_time()` [VERIFIED] |
| Wi-Fi | 802.11 b/g/n, 2.4 GHz | station mode, modem sleep disabled [VERIFIED] |
| USB | USB-Serial-JTAG + USB OTG | USB-Serial-JTAG used as console and capture link [VERIFIED] |
| Supply (module) | 3.0–3.6 V | powered from USB via the board's regulator [INFERRED] |
| Modem-sleep current @ 240 MHz | 32.9–107.9 mA depending on load (Table 5-9) | **not measured** on this board [UNVERIFIED] |

## The microphone: INMP441

### What it is

The INMP441 is a MEMS (micro-electro-mechanical) microphone with a built-in analog-to-digital converter and an I2S digital output. Because the conversion to numbers happens inside the microphone package, there is no analog wiring to pick up noise and no codec chip — three digital wires carry the audio.

### Specifications (from the datasheet via the study)

Table: INMP441 facts that constrain the design [DOCUMENTED] {#tab-micspec}
| Property | Value | Consequence here |
|---|---|---|
| Interface | I2S slave, 24-bit two's complement, MSB first | 32-bit slots, 24-bit samples; firmware keeps the top 16 bits |
| Frame | exactly 64 bit clocks per stereo frame | BCK = 64 × fs = 1.024 MHz at 16 kHz |
| Bit-clock range | 0.5–3.2 MHz | 1.024 MHz is well inside |
| Sample-rate range | 7.8–50 kHz | 16 kHz used |
| Channel select | L/R pin low → left slot; data line tri-stated in the other slot | L/R tied to ground; the right slot is empty |
| Supply | 1.62–3.63 V; 2.2 mA typical at 3.3 V | powered from 3.3 V |
| Sensitivity / SNR | −26 dBFS at 94 dB SPL; 61 dBA SNR | quiet speech at 1–2 m is only ~10–25 dB above the room floor |
| Pass band | ±0.04 dB up to 0.423 × fs (6 768 Hz at 16 kHz); −6 dB at fs/2 | mel filterbank stops at 6 500 Hz |
| Group delay | 17.2 / fs (1.078 ms at 16 kHz) | a fixed term inside the latency |
| Start-up | zero output for 2^18 bit clocks after power-up (≈ 256 ms) | 300 ms settle before measuring |

### What was measured on this unit

The M1 milestone (26–27 Sep) tested the microphone before anything was built on top of it. [VERIFIED unless marked]

- **It is in the left slot, and the right slot is truly empty**: the right slot read 100 % zeros, as expected with L/R tied low and the data line pulled low when tri-stated (E-18).
- **Framing**: with the standard "Philips" I2S format the 24-bit value arrived one bit late — its lowest bit was never 1 and sign bits leaked into the empty slot. With "MSB-justified" framing the lowest bit was 1 in 50.1–50.9 % of samples (as random audio should be) and the empty slot stayed zero. The firmware uses MSB-justified (E-18, DEC-06). The electrical root cause was not isolated. [VERIFIED behaviour; cause UNVERIFIED]
- **Mono mode halves DMA traffic**: stereo capture moved 127 963 B/s, mono 63 976 B/s (E-05).
- **No zero-output start-up period was seen** — the first non-zero sample came 0.56 ms after the clock started, on warm boots and one cold power-up. Instead the output carried a large low-frequency transient (DC up to 26 % of full scale) that decays in about 1.5 s; within the 125–6 500 Hz band the level reaches the room floor within 100 ms (E-04, E-19). [DOCUMENTED, small n]
- **The pass-band edge is visible**: in the recorded room noise, the 6 768–8 000 Hz band sits about 16 dB below the 4 000–6 768 Hz band (E-03; [[fig-psd]]).
- **Levels**: the room floor in the feature band was −52.9 dBFS (≈ 52 int16 units RMS, with a desk fan running); spoken words at about 0.5 m peaked at −38 to −42 dBFS per 100 ms (E-06). Low-frequency fan rumble (61–70 Hz lines, about −30 dBFS) dominates the broadband level (C-12) — this later forced a 150 Hz high-pass filter on the server (Chapter 11). [DOCUMENTED]

!fig #fig-psd figures/psd_m1.svg | Spectrum of 18 s of room sound recorded through the INMP441 on this board (run `20260926_214931_m1_msb_settle_warm`, no speech). The drop above 6 768 Hz is the microphone's own filter; the shaded band is the range the mel filterbank uses. Generated from the saved WAV by `docs/report/make_figures.py`. | 88

## Wiring

!fig #fig-wiring figures/wiring.svg | Wiring between the INMP441 and the ESP32-S3 as recorded in `firmware/sdkconfig.board`. | 100

Table: Connection table {#tab-wiring}
| Component / signal | Controller pin | Purpose | Notes |
|---|---|---|---|
| INMP441 SCK (bit clock) | GPIO6 | I2S0 BCK, driven by the ESP32-S3 at 1.024 MHz | the architecture's pin map had BCK on GPIO4 |
| INMP441 WS (word select) | GPIO5 | I2S0 WS, 16 kHz frame clock | as planned |
| INMP441 SD (serial data) | GPIO4 | I2S0 data in; 24-bit samples, MSB-justified | the plan had SD on GPIO6; pull-down not recorded |
| INMP441 L/R | GND | selects the left slot | confirmed by measurement |
| INMP441 VDD | 3V3 | supply | decoupling not recorded |
| INMP441 GND | GND | ground | — |
| (none) | GPIO15 | `INST_DETECT`: 10 ms pulse on each detection | driven, never measured |
| (none) | GPIO16 | `INST_ACTIVE`: high while a 10 ms hop is processed | driven, never measured |
| PC | native USB (USB-Serial-JTAG) | power, flashing, console, capture | COM7 on the PC |

**Planned versus actual.** The study's blueprint (§B5) put BCK on GPIO4 and SD on GPIO6. The board had already been wired the other way round (SCK→GPIO6, SD→GPIO4) before the project started, and the firmware was made to follow the real wiring through `firmware/sdkconfig.board` instead of rewiring (conflict C-05). This wiring was **reported by the user**; it is consistent with every measurement (live audio in the left slot, empty right slot), which is as strong a confirmation as software can give. [VERIFIED by measurement]

## The interfaces, explained

### I2S (the microphone link)

I2S is a three-wire serial audio bus. The **bit clock (BCK/SCK)** ticks once per data bit. The **word select (WS)** line changes level at the start of each channel's slot and so runs at the sample rate. The **data line (SD)** carries the sample bits, most significant bit first. The ESP32-S3 is the *master*: it generates both clocks, and the microphone clocks its data out on them.

The only subtlety that mattered is *when* the first bit appears. In "Philips" framing the MSB arrives one bit clock after WS changes; in "MSB-justified" framing it arrives on the WS edge. Pick the wrong one and every sample is shifted by one bit: the sound is still recognisable (only a factor of two and a lost bit), which is exactly why this kind of fault is dangerous — it looks almost right. The M1 alignment sweep tested four combinations and picked the one where the data behaved like real audio (Chapter 11).

### USB-Serial-JTAG (the evidence link)

The S3's native USB port appears on the PC as a serial port. The project uses it as a framed, CRC-checked binary link (`serial_link.c`): every message — text telemetry, raw audio, features, model outputs — is wrapped in a frame with a 4-byte sync word, type, length and a CRC-16. This made it possible to record hours of audio *through the real microphone* and to compare the device's internal numbers with the PC's, which is where most of the project's evidence comes from.

### Wi-Fi and TCP (the product link)

The board joins the home network as a Wi-Fi station and keeps one TCP connection to the server. Chapter 6 describes the protocol.

### GPIO (instrumentation)

Two pins are toggled by the firmware purely for measurement, following the MLPerf Tiny method the study recommended: GPIO16 is high while a 10 ms hop is being processed (its duty cycle *is* the pipeline's CPU share) and GPIO15 pulses on each detection. Without a logic analyser they were never read. [VERIFIED — code; measurement NOT RUN]

## Clocking and data-rate arithmetic

- Sample rate 16 000 Hz × 64 bit clocks per frame = **1.024 MHz** bit clock.
- Per 10 ms hop: 160 frames. In mono mode each frame is one 32-bit word, so the DMA delivers 640 bytes per hop (64 000 B/s); in stereo it would be 1 280 bytes (128 000 B/s).
- The firmware keeps only 16 bits per sample: 320 bytes per hop, **32 000 B/s** — the same rate that goes over Wi-Fi during a stream.
- DMA buffering: 4 descriptors × 160 frames = 40 ms of audio, so the processing task can be late by up to ~30 ms without losing samples. The driver counts overflows (`i2s_ovf`), and every product run reported **0** (e.g. E-60). [VERIFIED]

## Power

No current or energy measurement was made. Two design choices increase power on purpose: the CPU runs at 240 MHz (the study showed that halving the clock would roughly double the CPU percentage, and CPU is a hard gate while power has no target), and Wi-Fi modem sleep is disabled (`WIFI_PS_NONE`) so that packets from the server are not delayed to beacon intervals. The microphone's own 2.2 mA is negligible. Any statement about the device's power consumption would currently be [UNVERIFIED].

## What remains unverified about the hardware

- Board maker/model; breadboard or soldered; antenna type.
- The SD pull-down resistor and mic decoupling capacitor (the empty slot reading zero suggests the line is held low, but does not prove a resistor is fitted).
- How the breakout handles the microphone's CHIPEN (enable) pin.
- Supply quality and current draw.
