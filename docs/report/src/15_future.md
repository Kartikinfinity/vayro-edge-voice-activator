# Future Technical Development {#ch-future .chapter}

Every item in this chapter is [FUTURE]: not implemented, not tested. Each follows from a limitation measured in Chapters 12 and 14, and is written so that it can be picked up as a work package: the limitation it addresses, the change, the subsystem, the resources, how to validate it, and what it could break.

## Reduce household false triggers without losing new speakers

- **Addresses:** 15.8 false triggers per hour with TV and conversation; v4's loss of recall on a new speaker.
- **Change:** record keyword sessions from 5–10 more speakers (different ages, accents, distances) *and* several hours of household audio from more than one home; retrain the same architecture with speaker-disjoint splits; mine hard negatives from household hours only; keep positives balanced across speakers.
- **Subsystem:** data and training (`model/data`, `model/train`); no firmware change unless the operating point moves.
- **Resources:** volunteers, the existing capture tool and scripts, ≈ 1 h of training per model on the current PC.
- **Validation:** declare the rule first (as with v3/v4) and include a new-speaker criterion; report recall per speaker and false triggers per condition with exposure; confirm live-equals-replay on at least one new recording.
- **Risks:** more negatives can narrow the keyword (the v4 effect); new speakers must never leak into the test set.

## Use the operating curve that already exists in the recordings

- **Addresses:** the choice of N = 3 and threshold 0.80 was made on one speaker's validation session.
- **Change:** because replay is exact, sweep the averaging length (3–10 scores), the threshold, and a two-threshold rule on the *existing* ≈ 13 h of recordings, and plot false triggers per hour against recall and against latency — the study's EXP-11 "latency-vs-FA/h operating curve".
- **Subsystem:** evaluation only (`eval_stream.py` already supports threshold and N sweeps).
- **Validation:** choose the point on validation data only; confirm on fresh recordings.
- **Risks:** longer averaging adds latency (≈ 60 ms per extra score) and more pre-roll memory.

## Convert the model to stateful streaming

- **Addresses:** inference costs ≈ 3.9 % of core 1 because the whole 1 s window is recomputed every 60 ms (DEC-11); the busiest-core margin is ≈ 0.5 point.
- **Change:** convert the trained "valid-padding" network to a streaming form that keeps each layer's recent outputs and computes only the new time steps (the reason X5 was followed), then run it every 30–60 ms.
- **Subsystem:** `model/train` (conversion), `kws_engine` (state buffers), `app_main.c` (scheduling).
- **Validation:** streaming outputs must equal windowed outputs on recorded audio (a new parity test), then EXP-2 again.
- **Risks:** extra RAM for layer state (must be re-measured against the 5 kB margin); TFLM support for the required state operators.

## Measure what is still estimated

- **Addresses:** the 10 ± 7 ms capture term; the unused GPIO instruments; n = 12 latency sample.
- **Change:** a logic analyser on GPIO15/GPIO16 and a loudspeaker playback rig that marks the keyword's end on a third channel (the study's IN-1/IN-2); ≥ 100 activations at several distances and volumes.
- **Subsystem:** test harness only.
- **Validation:** the hardware path and the software path must agree within their stated uncertainty.
- **Risks:** none to the product; loudspeaker playback is a different acoustic source from a person.

## Measure and reduce power

- **Addresses:** power has never been measured; Wi-Fi modem sleep is disabled.
- **Change:** measure current in idle listening and while streaming (USB power meter or shunt); then test modem sleep and a lower CPU clock, re-measuring latency and CPU.
- **Validation:** current in mA with conditions; the latency and CPU tests repeated.
- **Risks:** modem sleep delays server messages (the reason it was disabled); 160 MHz would raise CPU percentages by 1.5×.

## Make the device deployable

- **Addresses:** compiled-in server address and credentials; 30 s boot wait; a network change needs a rebuild (E-41).
- **Change:** store Wi-Fi and server settings in NVS with a provisioning method; discover the server (for example mDNS); remove the host-wait and the M1 probes from the product build (keep them in the capture build); add TLS established once at boot if the link leaves a trusted LAN.
- **Subsystem:** `netstream`, `app_main.c`, `sdkconfig.product`.
- **Validation:** EXP-1 and EXP-2 re-run (TLS costs heap); a network-change test; a cold-boot time measurement.
- **Risks:** TLS could consume the remaining RAM margin — the study estimated ≈ 16 kB steady state.

## Bound the heap and automate the checks

- **Addresses:** the RAM claim is measured, not enforced; parity and memory checks are run by hand.
- **Change:** the study's "arena discipline" (a bounded heap region and an allocation-failure hook that reports and halts); a CI job that builds the product firmware, runs the dependency gate, checks static RAM against a ceiling, and runs the parity test on a stored recording.
- **Validation:** a deliberate over-allocation must be caught.
- **Risks:** none functionally; time to set up.

## Compress the stream for poor networks

- **Addresses:** only 180 ms of ring slack beyond the pre-roll; untested on congested Wi-Fi; L3 not computed.
- **Change:** the study's IMA-ADPCM mode (4:1, negligible CPU) selectable per stream, a throughput probe, and an L3 measurement.
- **Validation:** word error rate with and without ADPCM on the same recordings; overruns and L3 under a throttled link.
- **Risks:** ASR accuracy loss; protocol complexity.

## Improve command recognition on the server

- **Addresses:** the off-the-shelf recogniser's accuracy (2/5 and 3/4 in small tests).
- **Change:** a measured comparison of the open-vocabulary model, the 12-phrase grammar mode already in `ingest.py`, and a larger or adapted non-transformer model, on a fixed set of recorded streams (possible offline with `replay_session.py`).
- **Validation:** word error rate and command accuracy on held-out recordings, with n reported.
- **Risks:** a grammar rejects anything outside its list.

## Prepare the model for commercial use

- **Addresses:** two TTS voices are licensed for non-commercial use only.
- **Change:** regenerate the synthetic set without `en_US-l2arctic-medium` and `hi_IN-pratham-medium` (a configuration change in `gen_tts.py`), retrain, and re-run the declared tests.
- **Risks:** fewer accented voices in training; the new model must be re-validated on the same test sets.
