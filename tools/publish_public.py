"""Build the PUBLIC copy of this repository's history (the one on GitHub) from the private working repository.

The working repository keeps raw evidence that must not be published: voice recordings, videos and feature
dumps derived from room audio. Its device logs also contain the home network's name and the router's
hardware address. This tool writes a second, parallel history to the ref `refs/public/main` in which, for
every commit of the source branch:

  * withheld paths are removed            (WITHHELD below)
  * network and account identifiers in text files are redacted   (redact() below)
  * the author / committer e-mail is replaced by a GitHub no-reply address
  * the message gets a trailer `Original-commit: <id in the private history>`, so commit ids cited in the
    evidence (for example the ids of selection rules committed before a test) can still be found with
    `git log --grep <id>`

Dates, author names, messages and order are unchanged; commits that become empty are dropped. The rewrite is
deterministic (same input -> same commit ids), so running it again after new work only appends commits and
the public branch can be pushed as a fast-forward.

Nothing is pushed by this tool. After the rewrite it scans every blob reachable from the public ref and
refuses to finish if anything that should have been removed or redacted is still there.

Usage (from the private repository, host venv or any Python 3.10+):
    python tools/publish_public.py                      # rewrite + verify -> refs/public/main
    python tools/publish_public.py --export D:\\path      # also fast-forward a clean clone at that path
Then, in the exported clone:  git push -u origin main
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC_REF = "refs/public/main"
NOREPLY = "179582332+Kartikinfinity@users.noreply.github.com"

# Paths that never enter the public history.
WITHHELD = [
    (re.compile(r"\.(wav|mp4|flac|mp3|ogg)$", re.I), "voice recordings and videos (speakers, household, TV)"),
    (re.compile(r"(^|/)features_device(_s\d+)?\.bin$"), "log-mel feature dumps derived from room audio (up to 309 MB)"),
    (re.compile(r"^SIH2026-IDEA-Presentation-Format.*\.pptx$"), "official SIH template (third-party file)"),
    (re.compile(r"^docs/submission/SIH_RESEARCH_ROADMAP\.md$"), "internal planning notes"),
]
MAX_BLOB = 50 * 1024 * 1024  # GitHub rejects files above 100 MB; keep well below
MAC = re.compile(rb"(?i)(?<![0-9a-f:])((?:[0-9a-f]{2}:){3})(?:[0-9a-f]{2}:){2}[0-9a-f]{2}(?![0-9a-f:])")
WINUSER = re.compile(rb"(?i)((?:[a-z]:|/mnt/[a-z]|/[a-z])(?:\\\\|\\|/)+users(?:\\\\|\\|/)+)[^\\/\s\"'<>|]+")


# Recognised text (ASR output) is derived from the audio. It is published only for streams of scripted test
# sessions, where the speaker read prompts; for every other stream (ambient household sound: family talk,
# television) the text is replaced by a placeholder. Timing, size and integrity fields are never touched.
TRANSCRIPT_KEEP = [re.compile(p) for p in (
    r"^evidence/server/20260928_180050/c192732_",          # E-48 command test
    r"^evidence/server/20260928_201836/c201837_act000[3-8]",  # E-49 command test
    r"^evidence/server/20260929_214632/",                  # draft demonstration take (prompted commands)
    r"^evidence/server/20260929_221342/",                  # demonstration take (E-61)
    r"^evidence/server/20260930_085548/",                  # T1 (keyword only)
)]
SERVER_LOG = re.compile(r"^evidence/(server|final|household)[^/]*\.std(out|err)\.log$")
PLACEHOLDER = b"[withheld: ambient audio]"


def redact_transcripts(path, data):
    keep = lambda p: any(rx.search(p) for rx in TRANSCRIPT_KEEP)  # noqa: E731
    if SERVER_LOG.search(path):
        data = re.sub(rb'(ASR: |after trigger: )"[^"\r\n]+"', rb'\1"' + PLACEHOLDER + b'"', data)
        return re.sub(rb'(heard: (?:\x1b\[\d+m)?)"[^"\r\n]+"', rb'\1"' + PLACEHOLDER + b'"', data)
    if not path.startswith("evidence/server/"):
        return data
    if path.endswith(".json") and not keep(path):
        data = re.sub(rb'("asr_(?:transcript|after_trigger)": )"(?:[^"\\]|\\.)+"', rb'\1"' + PLACEHOLDER + b'"', data)
        return re.sub(rb'"asr_words": \[\s*\{.*?\}\s*\]', b'"asr_words": []', data, flags=re.S)
    if path.endswith("/activations.csv") and b"'word':" in data:
        # Rows of one file can have different column sets (the header is written once), so the cells are found
        # by content: the word list "[{'conf': ..., 'word': ...}]" and the two cells before it
        # (asr_transcript, asr_after_trigger - the order in which server/ingest.py adds them).
        import csv
        import io
        rows = list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))
        folder = path.rsplit("/", 1)[0]
        for r in rows[1:]:
            stem = next((c for c in r if re.fullmatch(r"(c\d{6}_)?act\d{4}|replay_act\d{4}", c)), "")
            if keep(f"{folder}/{stem}.json"):
                continue
            for i, c in enumerate(r):
                if c.startswith("[{") and "'word':" in c:
                    r[i] = "[]"
                    for j in (i - 1, i - 2):
                        if j >= 0 and r[j]:
                            r[j] = PLACEHOLDER.decode()
        out = io.StringIO(newline="")
        csv.writer(out).writerows(rows)
        return out.getvalue().encode("utf-8")
    return data


def git(*args, stdin=None, env=None, text=True):
    r = subprocess.run(["git", "-C", str(ROOT), *args], input=stdin, capture_output=True, env=env,
                       **({"text": True, "encoding": "utf-8"} if text else {}))
    if r.returncode:
        sys.exit(f"git {' '.join(args[:3])} failed: {r.stderr if text else r.stderr.decode('utf-8', 'replace')}")
    return r.stdout


def wifi_ssid():
    """The network name is read from the git-ignored local file at run time; it is never written anywhere."""
    f = ROOT / "firmware" / "sdkconfig.wifi"
    if not f.exists():
        sys.exit("firmware/sdkconfig.wifi not found: cannot know which network name to redact - refusing to continue")
    m = re.search(r'CONFIG_PS_WIFI_SSID="([^"]+)"', f.read_text(encoding="utf-8"))
    p = re.search(r'CONFIG_PS_WIFI_PASSWORD="([^"]+)"', f.read_text(encoding="utf-8"))
    if not m or not p:
        sys.exit("SSID / password not found in firmware/sdkconfig.wifi")
    return m.group(1).encode(), p.group(1).encode()


def redact(data, ssid):
    """Text blobs only. Network name -> placeholder; MAC addresses keep their vendor prefix only;
    the Windows account name in absolute paths -> 'user'."""
    if b"\0" in data[:8192]:
        return data
    out = data.replace(ssid, b"home-wifi-redacted")
    out = MAC.sub(lambda m: m.group(1) + b"xx:xx:xx", out)
    out = WINUSER.sub(lambda m: m.group(1) + b"user", out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="master", help="branch of the private repository to publish")
    ap.add_argument("--export", default="", help="directory of a clean public clone to create / fast-forward")
    args = ap.parse_args()
    ssid, password = wifi_ssid()

    cache = {}  # blob id -> redacted blob id

    def public_blob(sha, path):
        key = (sha, path) if path.startswith("evidence/") else sha   # transcript handling depends on the path
        if key not in cache:
            size = int(git("cat-file", "-s", sha))
            if size > MAX_BLOB:
                sys.exit(f"blob {sha} ({path}) is {size} bytes and is not on the withheld list")
            data = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", sha], capture_output=True).stdout
            new = redact(data, ssid)
            if b"\0" not in new[:8192]:
                new = redact_transcripts(path, new)
            cache[key] = sha if new == data else git("hash-object", "-w", "--stdin", stdin=new, text=False).decode().strip()
        return cache[key]

    mapping, last_new, last_tree = {}, None, None
    dropped = {}
    # scratch index inside .git (same drive as the repository; the system temp drive may be full)
    fd, idx = tempfile.mkstemp(suffix=".idx", prefix="public-", dir=git("rev-parse", "--absolute-git-dir").strip())
    os.close(fd)
    os.unlink(idx)
    tmp_index = argparse.Namespace(name=idx)
    env_idx = dict(os.environ, GIT_INDEX_FILE=tmp_index.name)
    commits = git("rev-list", "--reverse", "--first-parent", args.source).split()
    for n, old in enumerate(commits, 1):
        raw = subprocess.run(["git", "-C", str(ROOT), "cat-file", "commit", old], capture_output=True).stdout
        head, _, message = raw.partition(b"\n\n")
        fields = dict(line.split(b" ", 1) for line in head.split(b"\n") if b" " in line and not line.startswith(b" "))
        entries = []
        for rec in subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "-z", old], capture_output=True).stdout.split(b"\0"):
            if not rec:
                continue
            meta, path = rec.split(b"\t", 1)
            mode, kind, sha = meta.decode().split()
            p = path.decode("utf-8")
            reason = next((why for rx, why in WITHHELD if rx.search(p)), None)
            if reason:
                dropped[p] = reason
                continue
            if kind != "blob":
                sys.exit(f"unsupported tree entry {kind} at {p}")
            entries.append(f"{mode} {public_blob(sha, p)}\t{p}".encode() + b"\0")
        git("read-tree", "--empty", env=env_idx)
        subprocess.run(["git", "-C", str(ROOT), "update-index", "-z", "--index-info"], input=b"".join(entries),
                       env=env_idx, check=True, capture_output=True)
        tree = git("write-tree", env=env_idx).strip()
        if tree == last_tree:          # nothing public changed in this commit
            mapping[old] = last_new
            continue

        def ident(value):  # b"Name <mail> 1790000000 +0530"
            m = re.match(rb"(.*) <[^>]*> (\d+ [+-]\d{4})$", value)
            return m.group(1).decode("utf-8"), m.group(2).decode()

        an, ad = ident(fields[b"author"])
        cn, cd = ident(fields[b"committer"])
        msg = redact(message, ssid).decode("utf-8").rstrip("\n")
        sep = "\n" if re.search(r"\n[A-Za-z-]+: [^\n]*$", msg) else "\n\n"   # join an existing trailer block
        msg = f"{msg}{sep}Original-commit: {old}\n"
        env = dict(os.environ, GIT_AUTHOR_NAME=an, GIT_AUTHOR_EMAIL=NOREPLY, GIT_AUTHOR_DATE=ad,
                   GIT_COMMITTER_NAME=cn, GIT_COMMITTER_EMAIL=NOREPLY, GIT_COMMITTER_DATE=cd)
        new = git("commit-tree", tree, *(["-p", last_new] if last_new else []), stdin=msg, env=env).strip()
        mapping[old], last_new, last_tree = new, new, tree
        print(f"[{n:3d}/{len(commits)}] {old[:7]} -> {new[:7]}  {msg.splitlines()[0][:80]}")
    if os.path.exists(tmp_index.name):
        os.unlink(tmp_index.name)
    git("update-ref", PUBLIC_REF, last_new)

    # ---- verification: nothing withheld or unredacted may be reachable from the public ref
    problems = []
    seen = set()
    account = os.environ.get("USERNAME", "").encode()   # the local Windows account name must not be published
    objects = [line.partition(" ") for line in git("rev-list", "--objects", PUBLIC_REF).splitlines()]
    info = [line.split() for line in
            git("cat-file", "--batch-check", stdin="\n".join(o[0] for o in objects) + "\n").splitlines()]
    kinds = {i[0]: i[1] for i in info}
    sizes = {i[0]: int(i[2]) for i in info}
    for sha, _, path in objects:
        if not path or sha in seen or kinds.get(sha) != "blob":
            continue
        seen.add(sha)
        if any(rx.search(path) for rx, _ in WITHHELD):
            problems.append(f"withheld path present: {path}")
        data = subprocess.run(["git", "-C", str(ROOT), "cat-file", "blob", sha], capture_output=True).stdout
        if len(data) > MAX_BLOB:
            problems.append(f"large blob: {path} ({len(data)} B)")
        if ssid in data or password in data:
            problems.append(f"network name or password present: {path}")
        if len(account) >= 4 and b"\0" not in data[:8192] and re.search(rb"(?i)\b" + re.escape(account) + rb"\b", data):
            problems.append(f"local account name present: {path}")
        if b"\0" not in data[:8192] and redact_transcripts(path, data).replace(b"\r\n", b"\n") != data.replace(b"\r\n", b"\n"):
            problems.append(f"ambient transcript present: {path}")
        if b"\0" not in data[:8192] and (MAC.search(data) and MAC.sub(lambda m: m.group(1) + b"xx:xx:xx", data) != data
                                         or WINUSER.sub(lambda m: m.group(1) + b"user", data) != data):
            problems.append(f"unredacted identifier: {path}")
    log = git("log", "--format=%ae%n%ce%n%B", PUBLIC_REF)
    if ssid.decode() in log or password.decode() in log:
        problems.append("network name or password in a commit message")
    mails = {m for m in git("log", "--format=%ae%n%ce", PUBLIC_REF).split() if m}
    if mails != {NOREPLY}:
        problems.append(f"unexpected commit e-mail(s): {len(mails - {NOREPLY})}")
    if problems:
        git("update-ref", "-d", PUBLIC_REF)
        sys.exit("VERIFICATION FAILED - public ref deleted:\n  " + "\n  ".join(problems[:40]))
    total = sum(sizes[s] for s in seen)
    why = {}
    for p, r in dropped.items():
        why[r] = why.get(r, 0) + 1
    print(f"\npublic history: {len(set(mapping.values()))} commits (from {len(commits)}), {len(seen)} blobs, "
          f"{total / 1048576:.1f} MB uncompressed, tip {last_new[:12]}")
    for r, c in why.items():
        print(f"  withheld: {c:4d} path(s) - {r}")
    changed = sum(1 for k, v in cache.items() if (k[0] if isinstance(k, tuple) else k) != v)
    print(f"  redacted: {changed} file version(s) (network name, MAC tails, account name in paths, ambient transcripts)")
    print("verification: PASS (no withheld path, no large blob, no network name/password, no full MAC, no-reply e-mail only)")

    if args.export:
        dst = pathlib.Path(args.export)
        if not (dst / ".git").exists():
            dst.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q", "-b", "main", str(dst)], check=True)
        run = lambda *a: subprocess.run(["git", "-C", str(dst), *a], check=True)  # noqa: E731
        run("fetch", "-q", str(ROOT), PUBLIC_REF)
        run("merge", "-q", "--ff-only", "FETCH_HEAD")
        print(f"exported to {dst} (branch main, fast-forwarded to {last_new[:12]})")


if __name__ == "__main__":
    main()
