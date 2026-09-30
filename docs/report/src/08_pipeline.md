# Data, Algorithms, Models and the Processing Pipeline {#ch-pipeline .chapter}

This chapter follows the numbers from raw sound to a transcript, explains each algorithm in plain terms first, and then gives the exact parameters used. Everything here is [VERIFIED] against `model/frontend.json`, the training and evaluation scripts, and `model/artifacts/*/metrics.json`, unless marked.

## The pipeline at a glance

Table: Every processing stage, with its parameters {#tab-stages}
| Stage | Where | Input → output | Key parameters |
|---|---|---|---|
| Acquisition | INMP441 + I2S DMA | sound → 24-bit samples | 16 kHz, MSB framing, left slot |
| Conversion | `reader_task` | 24-bit → int16 | `word >> 16` (bits 23:8) |
| Framing | microfrontend | 160 new samples → one 30 ms window | window 480 samples, hop 160 |
| Spectrum | microfrontend | window → 257 frequency bins | Hann window, 512-point real FFT, 16-bit fixed point (KissFFT) |
| Mel filterbank | microfrontend | bins → 40 band energies | 125–6 500 Hz |
| Noise reduction | microfrontend | subtract a slowly tracked noise floor per band | smoothing bits 10; even 0.025, odd 0.06; min signal 0.05 |
| PCAN gain control | microfrontend | normalise each band by its own recent level | strength 0.95, offset 80, gain bits 21 |
| Log | microfrontend | → 40 × uint16 (observed range 0–631) | scale shift 6 |
| Quantise | `ps_fe_to_int8` | uint16 → int8 | q = (v·256 + 333)/666 − 128 |
| Window | `kws_on_frame` | last 100 frames → 100 × 1 × 40 tensor | 1.02 s context, every 6 frames |
| Model | TFLite Micro | tensor → one int8 score | DS-CNN, 10 665 parameters |
| Smoothing + decision | `kws_on_frame` | scores → trigger | mean of 3 ≥ 0.80; 2 s refractory |
| Stream | `streamer_task` | ring → TCP | 571 ms pre-roll, 40 ms packets |
| Endpointing | `VadEndpointer` | stream → END | 300–4 000 Hz energy, keyword level − 20 dB, 0.7 s hang |
| ASR conditioning | `AsrFrontEnd` | stream → clean, level-normalised audio | 150 Hz 8th-order high-pass, keyword → −20 dBFS |
| Recognition | Vosk en-in-0.5 | audio → words with times | Kaldi-based, open vocabulary |

## Feature extraction: turning sound into 40 numbers

### The idea in simple words

A neural network this small cannot learn from raw samples efficiently. Instead, each 10 ms the device describes the last 30 ms of sound by *how much energy there is in each of 40 frequency bands*, spaced the way human hearing is (finer at low frequencies, coarser at high ones — the "mel" scale), on a logarithmic scale (so a quiet and a loud "Hey Vayro" look similar). A sequence of these 40-number frames is a picture of the sound — a spectrogram — and the model learns what "Hey Vayro" looks like in that picture.

### What the microfrontend does, step by step

1. **Window.** Take 480 samples (30 ms) and multiply them by a Hann window, which tapers the ends to zero so the frequency analysis is not polluted by the sharp edges of the cut.
2. **FFT.** A 512-point fast Fourier transform (the 480 samples padded to 512) gives the strength of 257 frequencies from 0 to 8 kHz, 31.25 Hz apart. This implementation uses 16-bit fixed-point arithmetic (KissFFT).
3. **Mel filterbank.** 40 overlapping triangular filters, from **125 Hz to 6 500 Hz**, sum the FFT energies into 40 bands. The 125 Hz floor keeps most of the desk fan's 61–70 Hz rumble out; the 6 500 Hz ceiling stays below the microphone's 6 768 Hz pass-band edge, so training audio and device audio see the same band (the study's option O1).
4. **Noise reduction.** For each band, a slowly moving estimate of the background level is subtracted (different smoothing for even and odd bands, keeping at least 5 % of the signal). A steady noise such as a fan fades from the features after a few seconds.
5. **PCAN (per-channel energy normalisation).** Each band is divided by a smoothed version of its own recent energy raised to a power (strength 0.95, offset 80). This acts like an automatic gain control per band, so the same word at 50 cm and at 2 m gives similar features.
6. **Log.** A fixed-point logarithm compresses the range; the output is 40 unsigned 16-bit numbers. On this device they stayed within 0–631.

The microfrontend is the front end of TensorFlow's own "micro_speech" example, used unmodified. Its noise reduction and PCAN state *adapt over time* — which is why the training data is built as continuous streams that start 2.5 s before each clip (see [[sec-mixing]]): the features of a clip depend on the audio before it, exactly as on the always-on device.

:::key
The design principle is **one definition, one implementation, two builds.** The same C files produce the device's features (compiled for the Xtensa core) and the training features (compiled for the PC as `libpsfe.so`), and both read the same `frontend.json`. The parity test showed the outputs are bit-identical — after one fix (Chapter 11).
:::

### From 16-bit features to the model's int8 input

Two mappings happen in sequence. First, `ps_fe_to_int8()` maps each uint16 feature to int8 with the micro_speech formula `(v·256 + 333)/666 − 128` (so the value 666 maps to +128, i.e. ≈ saturation). Second, because the trained model expects its input in its *own* quantisation (for v2b: scale 0.007567, zero point 4), a 256-entry lookup table, generated from the model's metadata, converts each int8 feature to the model's int8 scale: `lut[q] = clip(round(q/128/0.007567 + 4))`. Training fed the network `q/128` as floats; the lookup table is exactly that scaling, done in integer form. `eval_stream.py` uses the identical table, so the PC and the device feed the network the same bytes.

## The model: a small depthwise-separable CNN

### The concept

A normal convolution layer that turns 24 channels into 32 channels with a 5-tap filter needs 24 × 32 × 5 = 3 840 weights and as many multiply-accumulates per output step. A **depthwise-separable** convolution splits that into two cheap steps: a *depthwise* convolution filters each channel on its own (24 × 5 = 120 weights), then a *pointwise* 1 × 1 convolution mixes channels (24 × 32 = 768 weights) — 888 weights instead of 3 840, with little loss of accuracy. This is the idea behind the DS-CNN keyword-spotting models of Zhang et al. (2017) and many microcontroller models since.

### This model

The input is 100 time steps × 1 × 40 values. Although the code uses Keras `Conv2D` layers, every kernel is *k × 1*, so the network convolves along **time only**, and the 40 mel bands act as 40 input **channels**. In effect it is a 1-D temporal DS-CNN — the "frequency as channels" layout that the study's TC-ResNet discussion describes. [VERIFIED — `build_model()`]

!fig #fig-model figures/model.svg | Layer-by-layer structure of the shipped model, with output shapes, weights and multiply-accumulates computed from `build_model()`; the totals match `metrics.json` exactly. | 100

Points worth understanding:

- **Strides halve time three times** (10 → 20 → 40 → 80 ms per step), so the final 6 × 48 feature map summarises the whole 1.02 s window; a single dense layer then produces the score.
- **Two-thirds of the arithmetic is in the first layer** (141 120 of 212 584 MACs), because it is the only layer that mixes all 40 input channels at full time resolution.
- **"Valid" (no) padding everywhere.** The study's rule X5: a model with padding behaves differently when later converted to a stateful streaming form. By avoiding padding, the same trained weights could later be run incrementally without retraining (DEC-11). [VERIFIED — code; the conversion itself was not done]
- **BatchNorm after every convolution, then ReLU;** dropout 0.25 before the output during training only. BatchNorm is folded into the convolutions at export, which is why the int8 file contains only 5 operator types.
- **Training from scratch.** No weights are ever loaded; Keras' default initialisers with seed 26172 start every run. This is how the PS's ban on models pre-trained on assistant keywords is met by construction. [VERIFIED — E-14]

### Why a windowed model instead of a streaming one

The architecture proposed a *stateful streaming* model: each new frame updates internal state and the network does only the new work every 30 ms, costing about 1 % of a core. The implementation instead re-runs the network on the **whole 100-frame window every 60 ms** (DEC-11, approved by the user on 27 Sep). The reason was schedule risk: int8 streaming state in TensorFlow Lite Micro was the least-proven step in the plan and three days remained. The cost is CPU — inference takes about 3.9 % of core 1 instead of ≈ 1 % — which was measured and still fits under 10 %. [DOCUMENTED — decision; VERIFIED — cost]

## Data

### The keyword

"Hey Vayro", pronounced "Hey VAI-ro" (three syllables), was chosen by the user on 27 Sep (DEC-08); "Vayro" alone was considered and declined. The study recommended 3–4 syllables and phonetic distance from common words; the confusable list below shows which words were considered close.

A practical problem appeared immediately: the synthetic voices mispronounced the spelling. Phoneme probing (`model/data/tts_probe.py`) showed all three English voices said /veɪɹoʊ/ ("VAY-ro"); the spelling **"Hey Vyro"** gives /vaɪɹoʊ/, and for the Hindi voice **"हे वाइरो"** is correct. The keyword is unchanged; only the text given to the synthesiser differs (DEC-14). [DOCUMENTED]

### Sources

Table: Training data sources {#tab-data}
| Source | What | Used from | Role |
|---|---|---|---|
| Piper TTS, 4 voices | `en_US-libritts_r-medium` (multi-speaker US), `en_GB-vctk-medium` (UK), `en_US-l2arctic-medium` (non-native English), `hi_IN-pratham-medium` (Hindi) | v0 | synthetic positives and confusable negatives |
| LibriSpeech dev-clean | read English speech, first 5 s of each utterance | v0 | generic speech negatives; in v4 also the "command" after the keyword |
| Device-recorded room audio | recordings made through this INMP441 in this room ("beds") | v0 | background for mixing, and ambient negatives |
| Real speaker S01, session 1 | 23 located keywords + confusables + talk | v2 | real positives (3 windows each) and real negatives, plus 6 copies with extra room noise |
| Night recording, hours 1–5 | 5 h of the household at night (declared training hours) | v3 | extra beds, general negatives, and **hard negatives** |
| Household evening recording, training part | TV, conversation, prayer, 2 sessions | v4 | household negatives and hard negatives; extra beds |

### Synthetic speech (`gen_tts.py`)

Each clip picks a random speaker of the voice, a random speaking rate (`length_scale`), and random prosody noise. The **v2** set (used by v2a, v2b, v3, v4) was regenerated after the first live tests with two changes, both driven by measurements: faster speech (length scale 0.6–1.2 instead of 0.8–1.35, because the real speaker's keywords measured 0.42–0.78 s against a synthetic median of 0.79 s), and an expanded negative list (1.8× as many negatives) built around the words that had actually fooled v0 on the device — "Hey" alone, "Hey Vayu", "Hey bro", "Hero", "Pyro" — plus many "Hey + name" phrases. [VERIFIED — code comments, E-27]

Table: TTS v2 plan per voice (clips) {#tab-tts}
| Voice | Positives | Negatives | Note |
|---|---:|---:|---|
| en_US-libritts_r-medium | 1 400 | 1 980 | many speakers |
| en_GB-vctk-medium | 400 | 540 | |
| en_US-l2arctic-medium | 300 | 450 | dataset licensed non-commercial |
| hi_IN-pratham-medium | 120 | 162 | single speaker; training only; non-commercial share-alike |
| **Total** | **2 220** | **3 132** | 5 352 clips; 4 736 train / 616 validation |

**Speaker-disjoint split.** For each multi-speaker voice, the highest 12 % of speaker IDs go to validation only; LibriSpeech's last 8 speakers are validation only; the real speaker S01 was *excluded entirely* from v0/v1 training (so v0/v1 results on S01 are speaker-independent) and from v2 on only session 1 is used for training, session 2 for validation, session 3 for testing. The study's rule X15 ("split by speaker first, augment second") is followed: every split is by recording, time block or speaker, never by random window. [VERIFIED — `gen_tts.py`, `sources.json`]

### Mixing and labelling {#sec-mixing}

`build_dataset.py` never uses a clip on its own. Every example is built as a **continuous stream**: 2.5 s of a randomly chosen device-recorded bed (scaled by a random −10 to +4 dB, to imitate quieter and louder rooms), then the clip added into the continuing bed at a random signal-to-noise ratio of **0–25 dB** (measured in the 125–6 500 Hz band), then 0.4 s more bed. The host twin computes features over the whole stream from a reset state — so, as on the always-on device, noise reduction and PCAN have settled before the clip starts.

Windows of 100 frames are then cut and labelled by the **end of the keyword** (the study's end-of-keyword labelling, X13):

- **positive**: 3 windows whose last frame is 0–160 ms after the keyword's end (chosen at random among the 17 possible);
- **negative "prefix"**: windows ending 200 ms and 350 ms *before* the keyword's end — they contain "Hey Vy…" but not the whole word, which teaches the model not to fire early;
- windows in between are not used (masked);
- for negative clips: windows ending at, and 80/160 ms after, the clip end, and 200 ms before it;
- LibriSpeech: a window every 80 ms across the utterance; ambient: every 100 ms across 8 s of bed.

For real recordings (`add_real_run`) the keywords are located by energy inside each prompt window, positives are taken the same way, and negatives are every 4th window further than 0.3 s before and 1.2 s after any keyword — which includes the spoken confusables and free talk.

**Hard-negative mining** (v3, v4) is the one step that uses the deployed model's own mistakes: during the overnight and household recordings the device logged its score for every inference; every moment where v2b's live score was ≥ 0.30 in the *training* hours became a negative example (the window at that frame and ±3 frames, repeated 3 times). These are precisely the sounds the shipped model found keyword-like.

**Keyword-then-speech positives** (v4 only): half of the synthetic keywords were followed, after a 0–250 ms gap, by 0.5–1.5 s of LibriSpeech speech, because v2b missed keywords that were said straight before a command (single high scores suppressed by the 3-score average, E-51). Labels still mark the keyword's end.

### Dataset composition

Table: Windows per source in the training sets (from `metrics.json` data_meta) {#tab-dscomp}
| Source | v0 / v1 | v2a / v2b | v3 | v4 |
|---|---:|---:|---:|---:|
| TTS keyword (positive) | 11 898 | 11 832 | 11 832 | 5 916 |
| TTS keyword + continuation (positive) | — | — | — | 5 916 |
| real S01 keyword (positive) | — | 483 | 483 | 483 |
| TTS prefix (negative) | 7 932 | 7 888 | 7 888 | 7 888 |
| TTS confusables (negative) | 6 132 | 11 056 | 11 056 | 11 056 |
| LibriSpeech (negative) | 121 608 | 121 608 | 121 608 | 121 608 |
| room ambient (negative) | 34 000 | 34 000 | 34 000 | 34 000 |
| real S01 non-keyword (negative) | — | 16 758 | 16 758 | 16 758 |
| night hard negatives (×3) | — | — | 8 832 | 8 832 |
| night general negatives | — | — | 29 975 | 29 975 |
| household hard negatives (×3) | — | — | — | 6 501 |
| household general negatives | — | — | — | 9 175 |
| **Total (positives)** | **181 570 (11 898)** | **203 625 (12 315)** | **242 432 (12 315)** | **258 108 (12 315)** |
| Bed audio available for mixing | 115 s / 1 912 s | 3 709 s | 21 694 s | 25 530 s |
| Validation windows (positives) | 44 815 (1 422) | 45 569 (1 488) | 45 569 (1 488) | 45 569 (1 488) |

Only about **6 %** of the training windows are positive; the class weighting below compensates.

## Training

Table: Training configuration (`model/train/train.py`) {#tab-trainconf}
| Setting | Value |
|---|---|
| Input scaling | int8 feature q → q / 128 (float) |
| Augmentation | SpecAugment-style: one frequency mask of 0–3 bands and one time mask of 0–7 frames per example, masked cells set to the feature floor (−1.0) |
| Loss | binary cross-entropy |
| Class weight | v0, v1, v2a: balanced (positives weighted ≈ 14–16×); **v2b, v3, v4: positive weight 4** |
| Optimiser | Adam, cosine-decay learning rate from 1e-3 (v0: 3e-3, which oscillated) over all steps |
| Batch / epochs | 256 / up to 30, early stopping on validation PR-AUC with patience 8, best weights restored |
| Seed | 26172 (TensorFlow, NumPy and the dataset builder) |
| Hardware | the PC's CPU in WSL (no GPU); v2b trained in 421.6 s (16 epochs) |

The validation metric (area under the precision-recall curve on 1 s windows) is used only for early stopping. It is **not** the model-selection criterion — per-window scores say little about detections per hour of continuous audio, so selection was always done on real recordings with the device's own decision logic (next sections). [VERIFIED]

## Quantisation and export

The trained float model is converted to **full-integer int8** with TensorFlow Lite's post-training quantisation, calibrated on 500 training windows (250 positive, 250 negative, fixed seed). Inputs and outputs are int8 too. `export.py` then rebuilds the same network with a **fixed batch size of 1** and copies the weights across, because Keras 3's dynamic batch dimension made the converter emit extra SHAPE/STRIDED_SLICE/PACK operators; the static graph contains only CONV_2D, DEPTHWISE_CONV_2D, RESHAPE, FULLY_CONNECTED and LOGISTIC, and gives identical outputs (DEC-17).

Table: The shipped model's quantisation facts (v2b, `metrics.json`) {#tab-quant}
| Property | Value |
|---|---|
| File size | 28 024 B (SHA-256 `f7c913efdbb28f64…`) |
| Input quantisation | scale 0.007567, zero point 4 |
| Output quantisation | scale 1/256, zero point −128 (so p = (out + 128)/256, in steps of 1/256) |
| Largest float-vs-int8 difference on validation windows | 0.151 in probability |
| Tensor arena needed on the device | 13 404 B (`arena_used_bytes()`) |

The largest float-vs-int8 difference of 0.15 is on individual windows; it is the int8 model that was evaluated everywhere below, so this difference does not affect any reported result.

## Runtime inference and decision

The device runs the model every 6 feature frames (60 ms), i.e. 16.7 times per second, on the most recent 100 frames. The output *p* is averaged over the last **three** inferences (a 120 ms span), and a trigger fires when the average is at least **0.80** and at least **2 000 ms** have passed since the previous trigger. These four numbers (0.80, 3, 6, 2 000) are the "operating point"; they are stored with the model's selection outcome and compiled in through `sdkconfig.model`.

!fig #fig-post figures/posterior_s01s3.svg | The shipped model's scores during the first 50 s of the held-out session S01-s3, recorded live on the device (`posteriors_device.bin`). Each "Hey Vayro" produces a sharp peak; the averaged score must stay above 0.80 across three inferences. The peaks near 33 s and 45 s did not stay high across three inferences and produced no trigger — most likely missed keywords (this part of the session scored 4/6 and 2/3). | 100

Why average three scores? A single high score can come from a keyword-like fragment of other speech; a real keyword gives high scores on several consecutive windows as it slides through the 1 s context. Averaging trades a little latency (≈ 60–120 ms) for fewer false triggers — the same trade the study analysed as "smoothing window" (§8.2). It also causes a known failure: a keyword spoken *immediately* before a command sometimes produced only one high score and was missed (E-51) — the motivation for v4's continuation data.

## Evaluation methodology

### Device-identical replay

`model/eval/eval_stream.py` reproduces the device on the PC: host-twin features over the whole recording from a reset state, the same lookup table, TensorFlow Lite's *reference* integer kernels (the closest match to the device's integer arithmetic), inference every 6 frames, the same zero-initialised 3-score average, the same threshold and refractory. Because of parity (E-21, E-22), its detections equal the device's live detections — checked explicitly: 27 of 27 trigger times identical on S01 session 2 (E-26), 39 of 39 on the household recording (E-51), and 12 of 12 on the command session (E-57). This is what makes it legitimate to evaluate several models on the same recording, or to replay a recording through a new model. [VERIFIED]

### Scoring keyword sessions

Recording sessions follow a script of prompts (`host/scripts/kw_session_v2.txt`: 25 "Say: Hey Vayro" prompts at 0.5, 1 and 2 m including fast, slow and soft, then 16 confusable words and 12 s of free talk). Two scorers exist:

- **Prompt score** (primary): a keyword prompt is a *hit* if any detection falls between 0.3 s after the prompt starts and 1.5 s after it ends; a detection inside a confusable, talk or silence prompt (and not in that 1.5 s spill-over) is a *false activation*. It needs no labelling and tolerates speakers who start late. It was introduced after session 2 showed speakers drifting into the next prompt (DEC-20).
- **Labeller score** (secondary): locates each spoken keyword by energy in 300–4 000 Hz (20 ms frames, threshold = the prompt window's 20th percentile + 9 dB, gaps up to 0.3 s bridged, at most 2 s long) and measures the detection lag after the keyword's acoustic end.

### False activations per hour

Continuous recordings in which nobody said the keyword are replayed and every detection is a false activation. The result is always reported with its **exposure** (hours) and, where the count is small, an upper bound (for zero events in *T* hours, the "rule of three": fewer than 3/*T* per hour at 95 % confidence). Household recordings that include a test where the keyword *was* said have those minutes excluded.

### Declared splits and selection rules

Before each new model, the data split and the rule for choosing it were written to a file and committed *before* the results existed: `sources.json` (the night split declared before the night was recorded; the household split declared before v4 was built) and `model/artifacts/selection_rule_v2/v3/v4.json`. The outcomes are recorded next to them. Chapter 10 tells the history, including the two occasions when a rule was not followed and why.

## Model versions

Table: The six models and what distinguished them {#tab-models}
| Model | Built | Training data | Class weight | Epochs | Best val. PR-AUC | Main result |
|---|---|---|---|---:|---:|---|
| v0 | 27 Sep 14:01 | TTS v1 + LibriSpeech + short room beds | balanced, lr 3e-3 | 7 | 0.928 | first on-device model; S01 22/23 offline; fired on "Hey", "Hero", "Pyro" (E-25, E-27) |
| v1 | 27 Sep 14:45 | as v0, more room beds (1 912 s) | balanced | 23 | 0.949 | better validation score but worse on the real speaker (18/23 vs 22/23) → DEC-18: never select on synthetic validation |
| v2a | 27 Sep 18:36 | TTS v2 + S01 session 1 + beds | balanced | 30 | 0.921 | 19/25 at 0.80 but 5/16 confusables on validation |
| **v2b** | 27 Sep 18:43 | same as v2a | **positive weight 4** | 16 | 0.925 | **shipped** at 0.80: 22/25 held-out session, 20/25 new speaker |
| v3 | 28 Sep 07:01 | v2 + night beds + night hard negatives | 4 | 17 | 0.937 | household 19.9 FA/h vs v2b 15.8 → not shipped (E-51) |
| v4 | 28 Sep 22:56 | v3 + keyword-then-speech + household negatives | 4 | 19 | 0.921 | fewer false triggers (9 vs 13 held-out) but new speaker 14/25 → not shipped (DEC-26) |

Build times are the UTC timestamps in `metrics.json` converted to IST. All six share the architecture, 10 665 parameters, 212 584 MACs and 28 024 bytes. [VERIFIED]

## The recogniser side

The server does three things to the audio before and around recognition:

1. **Conditioning** (`AsrFrontEnd`): device speech arrives quiet (around −40 dBFS at 30–50 cm) on top of fan rumble at about −30 dBFS. A controlled test showed the recogniser turned a clean LibriSpeech sentence at that level with the room's background into the single word "that"; after an 8th-order 150 Hz high-pass filter and gain it decoded almost perfectly (E-45). The gain is set once per stream from the keyword's level in the pre-roll (speech → −20 dBFS), because a moving gain changed transcripts between near-identical takes (E-48).
2. **Endpointing** (`VadEndpointer`): an energy detector in the speech band ends the stream after 0.7 s of quiet following speech, or 1.5 s if no speech follows the keyword; never before 0.8 s; at most 6 s. It replaced Vosk's own end-of-utterance rule, which on this audio waited for its 5 s silence timeout and kept streams open so long that the next keywords could not be streamed (E-48).
3. **Recognition**: Vosk with the `en-in-0.5` Indian-English model (Kaldi-based, not a transformer), open vocabulary, word timestamps. The words that start before the end of the pre-roll are the keyword; the rest is reported as "after trigger" — the command. A 12-phrase grammar mode exists (`--grammar server/commands.json`) but was a development experiment and is not the validated configuration.
