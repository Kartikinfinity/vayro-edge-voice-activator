"""Fill the official SIH 2026 idea template (SIH2026-IDEA-Presentation-Format (3).pptx) with PS26172 content.

Keeps the template's masters, title placeholders, logo, team-name oval, footer band and slide numbers; keeps every
"idea details pointer" of the template as a heading; replaces the template's pointer text boxes with content shapes;
removes slide 7 (instructions: max 6 slides incl. title, upload as PDF). Every number cites the evidence ledger.
Usage (host venv): python docs/submission/build_ppt.py   -> docs/submission/PS26172_SIH2026_Idea.pptx
Team ID / name: docs/submission/team.json
"""
import json
import pathlib
import re
import shutil
import zipfile
from xml.sax.saxutils import escape

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TEMPLATE = ROOT / "SIH2026-IDEA-Presentation-Format (3).pptx"
WORK = HERE / "build"
OUT = HERE / "PS26172_SIH2026_Idea.pptx"
TEAM = json.loads((HERE / "team.json").read_text(encoding="utf-8"))
# Measured numbers of the SHIPPED firmware (v2b @ 0.80, DEC-26) - filled from the final confirmation runs (ledger E-60).
NUM = json.loads((HERE / "numbers.json").read_text(encoding="utf-8"))
LEDGER_N = len(re.findall(r"^\| E-\d+ \|", (ROOT / "docs" / "EVIDENCE_LEDGER.md").read_text(encoding="utf-8"), re.M))

EMU = 914400
NAVY, BLUE, ORANGE, GREEN, RED = "1F497D", "0070C0", "E46C0A", "2E7D32", "C0504D"
INK, MUTED, CARD, CARD2, LINE = "1A1A1A", "595959", "EEF3FA", "EAF5EA", "BFD0E6"


def emu(v):
    return int(round(v * EMU))


class Shapes:
    def __init__(self, start_id=200):
        self.n = start_id
        self.xml = []

    def _id(self):
        self.n += 1
        return self.n

    def box(self, x, y, w, h, paras, fill=None, line=None, geom="rect", anchor="t", inset=0.08, radius=6000,
            txbox=False, line_w=12700):
        i = self._id()
        geo = (f'<a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val {radius}"/></a:avLst></a:prstGeom>'
               if geom == "roundRect" else f'<a:prstGeom prst="{geom}"><a:avLst/></a:prstGeom>')
        fill_x = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else "<a:noFill/>"
        line_x = (f'<a:ln w="{line_w}"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line
                  else "<a:ln><a:noFill/></a:ln>")
        ins = emu(inset)
        body = "".join(paras) if paras else '<a:p><a:endParaRPr lang="en-US" sz="1000"/></a:p>'
        self.xml.append(
            f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="PS26172 {i}"/><p:cNvSpPr{" txBox=\"1\"" if txbox else ""}/><p:nvPr/>'
            f'</p:nvSpPr><p:spPr><a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(w)}" cy="{emu(h)}"/></a:xfrm>'
            f'{geo}{fill_x}{line_x}</p:spPr><p:txBody><a:bodyPr wrap="square" lIns="{ins}" tIns="{ins}" rIns="{ins}" '
            f'bIns="{ins}" anchor="{anchor}"><a:noAutofit/></a:bodyPr><a:lstStyle/>{body}</p:txBody></p:sp>')

    def text(self, x, y, w, h, paras, anchor="t", inset=0.0):
        self.box(x, y, w, h, paras, anchor=anchor, inset=inset, txbox=True)

    def arrow(self, x, y, w, h, color=MUTED, geom="rightArrow"):
        self.box(x, y, w, h, None, fill=color, geom=geom)


def run(t, sz, color=INK, b=False, i=False, font="Arial", u=False):
    t = escape(t)
    sp = ' xml:space="preserve"' if t != t.strip() else ""
    return (f'<a:r><a:rPr lang="en-US" sz="{int(sz * 100)}" b="{1 if b else 0}" i="{1 if i else 0}"'
            f'{" u=\"sng\"" if u else ""} dirty="0"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            f'<a:latin typeface="{font}"/><a:cs typeface="{font}"/></a:rPr><a:t{sp}>{t}</a:t></a:r>')


def para(runs, align="l", bullet=None, before=0, after=0, level_in=0.0, line=None):
    ppr = f' algn="{align}"'
    inner = ""
    if line:
        inner += f'<a:lnSpc><a:spcPct val="{int(line * 1000)}"/></a:lnSpc>'
    if before:
        inner += f'<a:spcBef><a:spcPts val="{int(before * 100)}"/></a:spcBef>'
    if after:
        inner += f'<a:spcAft><a:spcPts val="{int(after * 100)}"/></a:spcAft>'
    if bullet == "dot":
        ind = emu(0.16 + level_in)
        ppr += f' marL="{ind}" indent="{-emu(0.16)}"'
        inner += '<a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>'
    elif bullet == "diamond":
        ppr += f' marL="{emu(0.36)}" indent="{-emu(0.36)}"'
        inner += '<a:buFont typeface="Wingdings" pitchFamily="2" charset="2"/><a:buChar char="v"/>'
    else:
        inner += "<a:buNone/>"
    if isinstance(runs, str):
        runs = [runs]
    return f"<a:p><a:pPr{ppr}>{inner}</a:pPr>{''.join(runs)}</a:p>"


def bullets(items, sz=12, color=INK, gap=4):
    """items: str, or (bold_lead, rest)"""
    out = []
    for k, it in enumerate(items):
        rs = [run(it[0], sz, color, b=True), run(it[1], sz, color)] if isinstance(it, tuple) else [run(it, sz, color)]
        out.append(para(rs, bullet="dot", before=0 if k == 0 else gap))
    return out


def pointer(text, sz=18):
    """A template 'idea details pointer', kept verbatim as a navy heading."""
    return para(run(text, sz, NAVY, b=True), bullet="diamond")


def card(s, x, y, w, h, head, items, fill=CARD, head_color=NAVY, sz=13, head_sz=13.5):
    s.box(x, y, w, h, [para(run(head, head_sz, head_color, b=True), after=4)] + bullets(items, sz), fill=fill,
          line=None, geom="roundRect", inset=0.14)


def stat(s, x, y, w, h, value, label, color=NAVY, vsz=24, lsz=10.5, fill="FFFFFF", line=LINE):
    s.box(x, y, w, h, [para(run(value, vsz, color, b=True), align="ctr"),
                       para(run(label, lsz, MUTED), align="ctr", before=1)],
          fill=fill, line=line, geom="roundRect", anchor="ctr", inset=0.06)


# ---------------------------------------------------------------- slide builders
def slide2(s):
    s.text(0.5, 1.28, 12.3, 0.45, [pointer("Proposed Solution (Describe your Idea/Solution/Prototype)", 20)])
    y, h, w, g = 1.85, 3.72, 3.98, 0.18
    xs = [0.5, 0.5 + w + g, 0.5 + 2 * (w + g)]
    card(s, xs[0], y, w, h, "Detailed explanation of the proposed solution", [
        "ESP32-S3 + INMP441 microphone listen continuously; every 10 ms the chip computes a 40-band log-mel frame",
        "A 10.7 k-parameter DS-CNN (28 KB int8, TensorFlow Lite Micro + ESP-NN) scores the last 1 s every 60 ms",
        "“Hey Vayro” detected (mean of 3 scores ≥ 0.80) → 571 ms pre-roll + live audio stream over "
        "one warm TCP link",
        "Server: VAD ends the utterance, Vosk (Kaldi) ASR returns the command text"])
    card(s, xs[1], y, w, h, "How it addresses the problem", [
        "No audio leaves the device until the keyword is detected → privacy, zero cloud cost while idle",
        f"Inside the PS budget on real hardware: {NUM['ram_kib']} KiB peak RAM, {NUM['cpu_c3']} % idle CPU",
        "Low latency: first audio at the server ≈ 2 ms after detection; keyword end → server ≈ 95 ms",
        "Only open-source components; custom keyword trained from scratch (no pre-trained wake word)"])
    card(s, xs[2], y, w, h, "Innovation and uniqueness of the solution", [
        "Training and device share one bit-exact feature pipeline (12 000 / 12 000 frames identical)",
        "Pre-roll ring buffer: a command spoken with no pause after the keyword is never clipped",
        "The device logs every trigger with its score, so real-home false triggers can be mined for retraining",
        f"Selection rules declared before each test; {LEDGER_N} logged evidence entries"])
    sy, sh, sw, sg = 5.72, 1.08, 2.93, 0.19
    for k, (v, l) in enumerate([("28 KB", "int8 model · 13.4 KB tensor arena"),
                                (f"{NUM['ram_kib']} KiB", "peak RAM while streaming (< 256 KB)"),
                                (f"{NUM['cpu_c3']} %", f"idle CPU, both cores (busiest core {NUM['cpu_core_max']} %)"),
                                ("≈ 95 ms", "keyword end → server (median)")]):
        stat(s, 0.5 + k * (sw + sg), sy, sw, sh, v, l, color=ORANGE if k in (1, 2) else NAVY)


def slide3(s):
    s.box(0.5, 1.3, 3.55, 5.5, [pointer("Technologies to be used (e.g. programming languages, frameworks, hardware)",
                                        12.5)] + bullets([
        ("Hardware: ", "ESP32-S3 N16R8 (240 MHz, PSRAM off) + INMP441 I2S MEMS mic"),
        ("Firmware: ", "C / C++ on ESP-IDF 5.5.5 (FreeRTOS)"),
        ("TinyML: ", "TensorFlow Lite Micro + ESP-NN kernels, TFLM microfrontend"),
        ("Training: ", "Python, TensorFlow / Keras, Piper TTS (4 voices), LibriSpeech, our own recordings"),
        ("Server: ", "Python TCP ingest, energy VAD, Vosk / Kaldi ASR"),
        ("Verification: ", "bit-exact host twin of the front end, scripted capture and replay tools")], sz=12, gap=7),
        fill=CARD, geom="roundRect", inset=0.14)
    x0, W = 4.25, 8.6
    s.text(x0, 1.3, W, 0.42, [pointer("Methodology and process for implementation (Flow Charts/Images/ working "
                                      "prototype)", 12.5)])
    # runtime flow
    s.text(x0, 1.82, W, 0.3, [para(run("Runtime — on the ESP32-S3 until the keyword, then the server", 11,
                                       MUTED, b=True))])
    steps = [("Mic", "I2S, 16 kHz, 24-bit"), ("Front end", "30/10 ms, 40 log-mel"), ("DS-CNN", "int8, 1 s window, "
             "every 60 ms"), ("Decide", "mean of 3 ≥ 0.80, 2 s refractory"), ("Ring", "0.75 s, 571 ms pre-roll"),
             ("Wi-Fi TCP", "40 ms packets, warm link"), ("Server", "VAD end-point → Vosk ASR")]
    bw, aw = 1.02, 0.235
    for k, (t, d) in enumerate(steps):
        x = x0 + k * (bw + aw)
        fill = CARD if k < 5 else ("F2F2F2" if k == 5 else CARD2)
        col = NAVY if k < 5 else (MUTED if k == 5 else GREEN)
        s.box(x, 2.15, bw, 1.22, [para(run(t, 11.5, col, b=True), align="ctr"),
                                   para(run(d, 9.5, INK), align="ctr", before=2)],
              fill=fill, line=None, geom="roundRect", anchor="ctr", inset=0.05)
        if k < len(steps) - 1:
            s.arrow(x + bw + 0.035, 2.66, aw - 0.07, 0.2)
    s.text(x0, 3.42, 5 * (bw + aw) - aw, 0.3, [para(run("ESP32-S3 (edge)", 10, NAVY, b=True), align="ctr")])
    s.text(x0 + 5 * (bw + aw), 3.42, 2 * bw + aw, 0.3, [para(run("network · server", 10, GREEN, b=True),
                                                             align="ctr")])
    # model-making flow
    s.text(x0, 3.85, W, 0.3, [para(run("How the keyword model is made (all scripted, reproducible)", 11, MUTED,
                                       b=True))])
    mk = [("Data", "TTS “Hey Vayro”, speech, room & household audio"), ("Device-identical streams",
          "same front end, bit-exact twin"), ("Train", "DS-CNN from random init"), ("int8 export", "28 KB, 5 ops"),
          ("Select", "rule declared before the test"), ("Flash", "operating point ships with the model")]
    bw2, aw2 = 1.235, 0.235
    for k, (t, d) in enumerate(mk):
        x = x0 + k * (bw2 + aw2)
        s.box(x, 4.18, bw2, 1.12, [para(run(t, 11, NAVY, b=True), align="ctr"),
                                    para(run(d, 9.5, INK), align="ctr", before=2)],
              fill="FFFFFF", line=LINE, geom="roundRect", anchor="ctr", inset=0.05)
        if k < len(mk) - 1:
            s.arrow(x + bw2 + 0.035, 4.64, aw2 - 0.07, 0.2)
    s.box(x0, 5.5, W, 1.3, [
        para([run("Working prototype: ", 11.5, NAVY, b=True),
              run("ESP32-S3-N16R8 + INMP441 on a breadboard (SCK→GPIO6, WS→GPIO5, SD→GPIO4). The demo "
                  "video shows keyword → stream → transcript live on this board.", 11.5)]),
        para([run("Model: ", 11.5, NAVY, b=True),
              run("10 665 parameters · 212 584 MACs per inference · 28 024 B int8 · tensor arena "
                  "13 404 B · ops: Conv2D, DepthwiseConv2D, FullyConnected, Reshape, Logistic", 11.5)], before=5)],
        fill=CARD, geom="roundRect", inset=0.14)


def slide4(s):
    s.text(0.5, 1.28, 12.3, 0.4, [pointer("Analysis of the feasibility of the idea — measured on the physical "
                                          "prototype, final firmware", 16)])
    cols = [("Efficiency", [(f"{NUM['ram_kib']} KiB", "peak RAM, streaming (< 256 KB)"),
                            (f"{NUM['cpu_c3']} %", f"idle CPU, 2 cores (max core {NUM['cpu_core_max']} %)"),
                            ("28 KB", "model flash · 13.4 KB arena")]),
            ("Accuracy (shipped model v2b)", [("22 / 25", "held-out prompts, speaker 1, 0.5–2 m"),
                                              ("20 / 25", "new speaker, never trained on"),
                                              ("1 in 5 h", "false triggers, quiet night (held-out)")]),
            ("Latency", [("1.7 ms", "detection → first packet at server"),
                         ("≈ 95 ms", "keyword end → server (median)"),
                         ("136 ms", "keyword end → server (p95)")])]
    cw, cg = 3.98, 0.18
    for c, (head, stats) in enumerate(cols):
        x = 0.5 + c * (cw + cg)
        s.text(x, 1.72, cw, 0.3, [para(run(head, 12.5, NAVY, b=True))])
        sw = (cw - 2 * 0.1) / 3
        for k, (v, l) in enumerate(stats):
            stat(s, x + k * (sw + 0.1), 2.05, sw, 1.28, v, l, vsz=17, lsz=9)
    # risks table
    tx, ty, tw = 0.5, 3.52, 12.33
    c1 = 4.6
    s.box(tx, ty, c1, 0.4, [pointer("Potential challenges and risks", 13)], fill=CARD, anchor="ctr", inset=0.1)
    s.box(tx + c1 + 0.08, ty, tw - c1 - 0.08, 0.4, [pointer("Strategies for overcoming these challenges", 13)],
          fill=CARD2, anchor="ctr", inset=0.1)
    rows = [("TV / family speech still triggers: 15.1 per hour (held-out household audio)",
             "Mining the device’s own false triggers cut this to 10.4 /h (model v4), but v4 lost new-speaker "
             "recall (14/25), so v2b ships; next: retrain with more speakers and household audio together"),
            ("Real voices tested so far: two speakers (plus TTS voices in 4 accents)",
             "Scripted 3-minute sessions for new speakers; per-speaker results reported separately"),
            ("Server ASR word accuracy is set by the ASR model (Vosk en-in: 36 % WER published)",
             "Edge is ASR-agnostic: swap in a larger model or a command grammar on the server only"),
            ("Thin RAM margin; Wi-Fi or server outages",
             "Memory trims saved 9.6 KB; detection keeps running offline; auto-reconnect; ASR off the "
             "server’s receive path")]
    rh = 0.6
    for k, (r, st) in enumerate(rows):
        y = ty + 0.46 + k * (rh + 0.06)
        s.box(tx, y, c1, rh, [para(run(r, 10.5, INK))], fill="FFFFFF", line=LINE, anchor="ctr", inset=0.1)
        s.box(tx + c1 + 0.08, y, tw - c1 - 0.08, rh, [para(run(st, 10.5, INK))], fill="FFFFFF", line=LINE,
              anchor="ctr", inset=0.1)


def slide5(s):
    s.box(0.5, 1.3, 5.2, 5.5, [pointer("Potential impact on the target audience", 16).replace(
        "<a:buFont", '<a:spcAft><a:spcPts val="600"/></a:spcAft><a:buFont', 1)] + bullets([
        ("ISRO labs & control rooms: ", "hands-free voice commands where hands and eyes are busy — without "
                                         "streaming room audio all day"),
        ("Smart automation: ", "a ready wake-word front end for any ESP32-class home, office or factory device"),
        ("Assistive use: ", "voice control for elderly or motor-impaired users on low-cost hardware"),
        ("Indian developers & start-ups: ", "custom keyword with Indian-accent training data, no vendor SDK or "
                                            "licence fee")], sz=13.5, gap=9),
        fill=CARD, geom="roundRect", inset=0.16)
    for k, (v, l) in enumerate([("0 bytes", "of audio sent until the keyword is detected"),
                                ("32 kB/s", "16 kHz audio, only from keyword to end of command")]):
        stat(s, 0.7 + k * 2.45, 5.35, 2.3, 1.25, v, l, color=ORANGE if k else NAVY, vsz=20, lsz=9.5)
    s.text(5.95, 1.3, 6.9, 0.4, [pointer("Benefits of the solution (social, economic, environmental, etc.)", 14)])
    items = [("Social", "Privacy by design: the room is only heard by the chip until someone says “Hey Vayro”",
              NAVY, CARD),
             ("Economic", "Hardware ≈ ₹1 000 (estimate); open-source stack; no cloud cost while listening",
              ORANGE, "FDF0E6"),
             ("Environmental", f"Low compute ({NUM['cpu_c3']} % CPU idle); audio is sent only after the keyword, so traffic "
              "stays tiny. Wi-Fi is kept awake for latency; power not yet measured", GREEN, CARD2),
             ("Technical", "Reproducible: a new keyword = new recordings + the same scripts; every number traceable "
              "to an evidence log", NAVY, CARD)]
    w, h, g = 3.37, 2.35, 0.16
    for k, (head, txt, col, fill) in enumerate(items):
        x = 5.95 + (k % 2) * (w + g)
        y = 1.82 + (k // 2) * (h + g)
        s.box(x, y, w, h, [para(run(head, 16, col, b=True), after=8), para(run(txt, 13.5, INK), line=110)],
              fill=fill, geom="roundRect", inset=0.16)


def slide6(s):
    s.text(0.5, 1.28, 12.3, 0.4, [pointer("Details / Links of the reference and research work", 16)])
    refs = [
        ("Y. Zhang, N. Suda, L. Lai, V. Chandra, ", "“Hello Edge: Keyword Spotting on Microcontrollers”, "
         "arXiv:1711.07128, 2017 — DS-CNN architecture"),
        ("P. Warden, ", "“Speech Commands: A Dataset for Limited-Vocabulary Speech Recognition”, "
         "arXiv:1804.03209, 2018 — KWS background (not used for training)"),
        ("TensorFlow Lite Micro + microfrontend: ", "github.com/tensorflow/tflite-micro"),
        ("Espressif esp-tflite-micro and ESP-NN: ", "github.com/espressif/esp-tflite-micro · "
                                                    "github.com/espressif/esp-nn"),
        ("ESP-IDF v5.5 (FreeRTOS, drivers, lwIP): ", "github.com/espressif/esp-idf"),
        ("V. Panayotov et al., ", "“LibriSpeech: an ASR corpus based on public domain audio books”, "
         "ICASSP 2015 — openslr.org/12"),
        ("Piper TTS and voices: ", "github.com/OHF-Voice/piper1-gpl · huggingface.co/rhasspy/piper-voices"),
        ("D. Povey et al., ", "“The Kaldi Speech Recognition Toolkit”, ASRU 2011 · Vosk: "
                              "alphacephei.com/vosk"),
        ("Datasheets: ", "ESP32-S3 Technical Reference Manual (Espressif); INMP441 (TDK InvenSense)")]
    ps = [para([run(f"[{k + 1}]  ", 12.5, NAVY, b=True), run(a, 12.5, INK, b=True), run(b, 12.5, INK)],
               before=0 if k == 0 else 8) for k, (a, b) in enumerate(refs)]
    s.box(0.5, 1.8, 7.95, 5.0, ps, fill=CARD, geom="roundRect", inset=0.16)
    s.box(8.62, 1.8, 4.21, 5.0, [
        para(run("Our own research record", 14, NAVY, b=True), after=6)] + bullets([
            ("Evidence ledger: ", f"{LEDGER_N} entries, each tagged measured / estimated / proposed, with its raw data"),
            ("Selection rules: ", "written and committed before each held-out test"),
            ("SBOM: ", "every component and licence listed; the one closed Wi-Fi radio blob and the non-commercial TTS voices are disclosed"),
            ("Licence: ", "our code Apache-2.0; every component’s licence listed in the SBOM"),
            ("Demo video: ", TEAM.get("video_link", "link to be added"))], sz=12.5, gap=9),
        fill=CARD2, geom="roundRect", inset=0.16)


# ---------------------------------------------------------------- assemble
def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    zipfile.ZipFile(TEMPLATE).extractall(WORK)
    sl = WORK / "ppt" / "slides"

    # slide 1: fill the title-page fields (keep the template's bullet style, smaller so the long title fits)
    x = (sl / "slide1.xml").read_text(encoding="utf-8")
    fields = [("Problem Statement ID – ", "26172"),
              ("Problem Statement Title – ", "Low Latency and Efficient Voice Activator for Edge Devices"),
              ("Theme – ", "Smart Automation"), ("PS Category – ", "Hardware"),
              ("Team ID – ", TEAM["team_id"]), ("Team Name – ", TEAM["team_name"])]
    ps = "".join(
        f'<a:p><a:pPr marL="285750" indent="-285750"><a:lnSpc><a:spcPct val="100000"/></a:lnSpc><a:spcBef>'
        f'<a:spcPts val="{0 if k == 0 else 1500}"/></a:spcBef><a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>'
        f'</a:pPr>{run(a, 18, INK, b=True)}{run(b, 18, NAVY, b=False)}</a:p>' for k, (a, b) in enumerate(fields))
    m = re.search(r'(<p:sp>(?:(?!</p:sp>).)*?name="TextBox 9".*?<p:txBody>)(.*?)(</p:txBody></p:sp>)', x, re.S)
    body = re.match(r"(<a:bodyPr.*?(?:/>|</a:bodyPr>)<a:lstStyle/>|<a:bodyPr.*?(?:/>|</a:bodyPr>))", m.group(2), re.S)
    x = x[:m.start(2)] + body.group(1) + ps + x[m.end(2):]
    (sl / "slide1.xml").write_text(x, encoding="utf-8")

    builders = {2: slide2, 3: slide3, 4: slide4, 5: slide5, 6: slide6}
    for n, fn in builders.items():
        p = sl / f"slide{n}.xml"
        x = p.read_text(encoding="utf-8")
        # drop the template's pointer text box (its pointers are re-used verbatim as headings above)
        x = re.sub(r'<p:sp>(?:(?!</p:sp>).)*?name="TextBox 8".*?</p:sp>', "", x, count=1, flags=re.S)
        # team name in the oval
        x = x.replace("<a:t>Your Team Name</a:t>", f"<a:t>{escape(TEAM['team_name'])}</a:t>")
        x = re.sub(r"<a:t>Your</a:t>(.*?)<a:t>Team</a:t>(.*?)<a:t>Name</a:t>",
                   lambda mm: f"<a:t>{escape(TEAM['team_name'])}</a:t>{mm.group(1)}<a:t></a:t>{mm.group(2)}<a:t></a:t>",
                   x, count=1, flags=re.S)
        if n == 2:
            x = x.replace("<a:t>IDEA TITLE</a:t>", f"<a:t>{escape(TEAM['idea_title'])}</a:t>")
            x = re.sub(r'(<p:sp>(?:(?!</p:sp>).)*?name="Title 1".*?</p:sp>)',
                       lambda mm: mm.group(1).replace('sz="3600"', 'sz="2800"'), x, count=1, flags=re.S)
        s = Shapes()
        fn(s)
        x = x.replace("</p:spTree>", "".join(s.xml) + "</p:spTree>", 1)
        p.write_text(x, encoding="utf-8")

    # remove slide 7 (template instructions): sldIdLst entry, relationship, part, content type
    pres = (WORK / "ppt" / "presentation.xml").read_text(encoding="utf-8")
    rels = (WORK / "ppt" / "_rels" / "presentation.xml.rels").read_text(encoding="utf-8")
    rid = re.search(r'<Relationship Id="(rId\d+)"[^>]*Target="slides/slide7.xml"[^>]*/>', rels).group(1)
    pres = re.sub(rf'<p:sldId [^>]*r:id="{rid}"/>', "", pres)
    rels = re.sub(rf'<Relationship Id="{rid}"[^>]*/>', "", rels)
    (WORK / "ppt" / "presentation.xml").write_text(pres, encoding="utf-8")
    (WORK / "ppt" / "_rels" / "presentation.xml.rels").write_text(rels, encoding="utf-8")
    ct = (WORK / "[Content_Types].xml").read_text(encoding="utf-8")
    ct = re.sub(r'<Override PartName="/ppt/slides/slide7.xml"[^>]*/>', "", ct)
    (WORK / "[Content_Types].xml").write_text(ct, encoding="utf-8")
    (sl / "slide7.xml").unlink()
    r7 = sl / "_rels" / "slide7.xml.rels"
    if r7.exists():
        r7.unlink()

    if OUT.exists():
        OUT.unlink()
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        # [Content_Types].xml first, as Office writes it
        z.write(WORK / "[Content_Types].xml", "[Content_Types].xml")
        for f in sorted(WORK.rglob("*")):
            if f.is_file() and f.name != "[Content_Types].xml":
                z.write(f, f.relative_to(WORK).as_posix())
    print("written", OUT)


if __name__ == "__main__":
    main()
