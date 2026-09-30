"""Build the PS26172 technical reconstruction report: docs/report/src/*.md -> HTML -> PDF (headless Chrome).

The Markdown dialect is deliberately small (see README section in src/00_front.md comments):
  # Title {#id .chapter|.front|.appendix}     headings (## and ### are numbered inside chapters/appendices)
  Table: caption {#tab-id}                   caption line directly above a pipe table
  !fig #fig-id figures/x.svg | caption | 90  figure (SVG inlined), optional width in %
  ::: key|why|example|simple|warn|evidence [title] ... :::   callout boxes (content is Markdown)
  ::: html ... :::                           raw HTML passthrough
  \\pagebreak                                 forced page break
  [[fig-id]] [[tab-id]] [[sec-id]]           cross-references ("Figure 6.1", "Table 3.2", "Section 7.4")
  [VERIFIED] [DOCUMENTED] [INFERRED] [UNVERIFIED] [PLANNED] [FUTURE]   evidence labels (badges)
Two passes: the first PDF's outline gives each heading's page; the second pass writes them into the contents.

Usage (host venv): python docs/report/build_report.py
"""
import html
import pathlib
import re
import subprocess
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = HERE / "src"
OUT_HTML = HERE / "PS26172_Technical_Report.html"
OUT_PDF = HERE / "PS26172_Technical_Report.pdf"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
TAGS = ("VERIFIED", "DOCUMENTED", "INFERRED", "UNVERIFIED", "PLANNED", "FUTURE")
CALLOUTS = {"key": "Key idea", "why": "Why it matters", "example": "In this project", "simple": "In simple words",
            "warn": "Caution", "evidence": "Evidence"}


# ---------------------------------------------------------------- inline
def inline(text, refs):
    codes = []

    def keep_code(m):
        codes.append(html.escape(m.group(1)))
        return f"\x00{len(codes) - 1}\x00"

    t = re.sub(r"`([^`]+)`", keep_code, text)
    t = html.escape(t, quote=False)
    t = t.replace("&lt;br&gt;", "<br>")
    t = re.sub(r"\[\[([a-z0-9\-]+)\]\]", lambda m: xref(m.group(1), refs), t)
    def tag(m):
        note = m.group(2).strip().lstrip("—–-:;,").strip()
        badge = f'<span class="tag tag-{m.group(1).lower()}">{m.group(1)}</span>'
        return badge + (f' <span class="tagnote">{note}</span>' if note else "")

    t = re.sub(r"\[(" + "|".join(TAGS) + r")([^\]]*)\]", tag, t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", t)
    return t


def xref(key, refs):
    if key not in refs:
        print(f"WARNING: unresolved reference [[{key}]]", file=sys.stderr)
        return f"<span class='bad-ref'>[[{key}]]</span>"
    label, _ = refs[key]
    return f'<a class="xref" href="#{key}">{label}</a>'


# ---------------------------------------------------------------- blocks
def parse_attrs(title):
    m = re.search(r"\s*\{([^}]*)\}\s*$", title)
    if not m:
        return title.strip(), None, set()
    ident, classes = None, set()
    for tok in m.group(1).split():
        if tok.startswith("#"):
            ident = tok[1:]
        elif tok.startswith("."):
            classes.add(tok[1:])
    return title[: m.start()].strip(), ident, classes


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


class Doc:
    def __init__(self, lines):
        self.lines = lines
        self.refs = {}   # id -> (label, kind)
        self.toc = []    # (level, number, title, id)

    # pass 1: numbering
    def number(self):
        chap = app = 0
        mode = "front"
        sec = sub = 0
        figs = tabs = 0
        prefix = "0"
        self.plan = []  # per line index: dict
        in_code = False
        for i, line in enumerate(self.lines):
            if line.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            h = re.match(r"^(#{1,4})\s+(.*)$", line)
            if h:
                lvl = len(h.group(1))
                title, ident, classes = parse_attrs(h.group(2))
                ident = ident or slug(title)
                base, k = ident, 2
                while ident in self.refs:          # unique ids: two sections may share a title ("Power")
                    ident, k = f"{base}-{k}", k + 1
                self.lines[i] = f"{h.group(1)} {title} {{#{ident} {' '.join('.' + c for c in sorted(classes))}}}"
                num = ""
                if lvl == 1:
                    sec = sub = 0
                    if "chapter" in classes or "appendix" in classes:
                        figs = tabs = 0
                    if "chapter" in classes:
                        chap += 1
                        mode, prefix, num = "chapter", str(chap), str(chap)
                    elif "appendix" in classes:
                        app += 1
                        mode = "appendix"
                        prefix = chr(64 + app)
                        num = f"Appendix {prefix}"
                    else:
                        mode, prefix = "front", "0"
                elif lvl == 2 and mode != "front":
                    sec += 1
                    sub = 0
                    num = f"{prefix}.{sec}"
                elif lvl == 3 and mode != "front":
                    sub += 1
                    num = f"{prefix}.{sec}.{sub}"
                label = {1: f"Chapter {num}" if mode == "chapter" else (num or title)}.get(lvl, f"Section {num}")
                self.refs[ident] = (label if num else title, "sec")
                self.plan.append((i, "h", lvl, title, ident, num, classes))
                if lvl <= 2:
                    self.toc.append((lvl, num, title, ident, classes))
                continue
            f = re.match(r"^!fig\s+#(\S+)\s+(\S+)\s*\|\s*(.*?)\s*(?:\|\s*(\d+))?\s*$", line)
            if f:
                figs += 1
                self.refs[f.group(1)] = (f"Figure {prefix}.{figs}", "fig")
                continue
            t = re.match(r"^Table:\s*(.*)$", line)
            if t:
                tabs += 1
                cap, ident, _ = parse_attrs(t.group(1))
                if ident:
                    self.refs[ident] = (f"Table {prefix}.{tabs}", "tab")
                self.lines[i] = f"Table: {cap} {{#{ident or 'tab-auto-' + str(i)}}}"
                self.refs.setdefault(ident or f"tab-auto-{i}", (f"Table {prefix}.{tabs}", "tab"))

    # pass 2: render
    def render(self, lines=None):
        lines = self.lines if lines is None else lines
        out = []
        i = 0
        para = []

        def flush():
            if para:
                out.append(f"<p>{inline(' '.join(para), self.refs)}</p>")
                para.clear()

        while i < len(lines):
            line = lines[i]
            s = line.rstrip()
            if not s.strip():
                flush()
                i += 1
                continue
            if s.startswith("```"):
                flush()
                lang = s[3:].strip()
                j = i + 1
                buf = []
                while j < len(lines) and not lines[j].startswith("```"):
                    buf.append(lines[j])
                    j += 1
                out.append(f'<pre class="code {lang}"><code>{html.escape(chr(10).join(buf))}</code></pre>')
                i = j + 1
                continue
            if s.strip() == "\\pagebreak":
                flush()
                out.append('<div class="pagebreak"></div>')
                i += 1
                continue
            m = re.match(r"^:::\s*(\w+)\s*(.*)$", s)
            if m and m.group(1) != "":
                flush()
                kind, title = m.group(1), m.group(2).strip()
                j, depth, buf = i + 1, 1, []
                while j < len(lines):
                    if re.match(r"^:::\s*\w+", lines[j]):
                        depth += 1
                    elif lines[j].strip() == ":::":
                        depth -= 1
                        if depth == 0:
                            break
                    buf.append(lines[j])
                    j += 1
                if kind == "html":
                    out.append("\n".join(buf))
                else:
                    head = title or CALLOUTS.get(kind, kind.title())
                    out.append(f'<div class="callout c-{kind}"><div class="c-head">{inline(head, self.refs)}</div>'
                               f"{self.render(buf)}</div>")
                i = j + 1
                continue
            h = re.match(r"^(#{1,4})\s+(.*)$", s)
            if h:
                flush()
                lvl = len(h.group(1))
                title, ident, classes = parse_attrs(h.group(2))
                ident = ident or slug(title)
                num = next((p[5] for p in self.plan if p[4] == ident), "")
                cls = " ".join(sorted(classes))
                if lvl == 1 and "chapter" in classes:
                    out.append(f'<h1 id="{ident}" class="{cls}"><span class="chapnum">Chapter {num}</span> '
                               f'<span class="chaptitle">{inline(title, self.refs)}</span></h1>')
                elif lvl == 1 and "appendix" in classes:
                    out.append(f'<h1 id="{ident}" class="{cls}"><span class="chapnum">{num}</span> '
                               f'<span class="chaptitle">{inline(title, self.refs)}</span></h1>')
                else:
                    n = f'<span class="secnum">{num}</span> ' if num else ""
                    out.append(f'<h{lvl} id="{ident}" class="{cls}">{n}{inline(title, self.refs)}</h{lvl}>')
                i += 1
                continue
            f = re.match(r"^!fig\s+#(\S+)\s+(\S+)\s*\|\s*(.*?)\s*(?:\|\s*(\d+))?\s*$", s)
            if f:
                flush()
                ident, path, cap, width = f.group(1), f.group(2), f.group(3), f.group(4) or "100"
                svg = (HERE / path).read_text(encoding="utf-8")
                svg = re.sub(r"<\?xml[^>]*\?>", "", svg)
                svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg)
                svg = re.sub(r"<svg\b", f'<svg style="width:{width}%;height:auto" ', svg, count=1)
                svg = re.sub(r'(<svg[^>]*?)\s(width|height)="[^"]*"', r"\1", svg, count=2)
                label = self.refs[ident][0]
                out.append(f'<figure id="{ident}">{svg}<figcaption><span class="fignum">{label}.</span> '
                           f"{inline(cap, self.refs)}</figcaption></figure>")
                i += 1
                continue
            t = re.match(r"^Table:\s*(.*)$", s)
            if t and i + 1 < len(lines) and lines[i + 1].startswith("|"):
                flush()
                cap, ident, _ = parse_attrs(t.group(1))
                j = i + 1
                rows = []
                while j < len(lines) and lines[j].startswith("|"):
                    rows.append(lines[j])
                    j += 1
                out.append(self.table(rows, cap, ident))
                i = j
                continue
            if s.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:\-|]+\|\s*$", lines[i + 1]):
                flush()
                j = i
                rows = []
                while j < len(lines) and lines[j].startswith("|"):
                    rows.append(lines[j])
                    j += 1
                out.append(self.table(rows, None, None))
                i = j
                continue
            if re.match(r"^\s*([-*]|\d+\.)\s+", s):
                flush()
                j = i
                items = []
                while j < len(lines) and lines[j].strip():
                    lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[j])
                    if lm:
                        items.append([len(lm.group(1)), lm.group(2), lm.group(3)])
                    elif items:
                        items[-1][2] += " " + lines[j].strip()
                    j += 1
                out.append(self.listing(items))
                i = j
                continue
            para.append(s.strip())
            i += 1
        flush()
        return "\n".join(out)

    def listing(self, items):
        html_out, stack = [], []
        for indent, marker, text in items:
            lvl = 0 if indent < 2 else 1
            tag = "ol" if marker[0].isdigit() else "ul"
            while len(stack) > lvl + 1:
                html_out.append(f"</li></{stack.pop()}>")
            if len(stack) < lvl + 1:
                html_out.append(f"<{tag}>")
                stack.append(tag)
            else:
                html_out.append("</li>")
            html_out.append(f"<li>{inline(text, self.refs)}")
        while stack:
            html_out.append(f"</li></{stack.pop()}>")
        return "".join(html_out)

    def table(self, rows, cap, ident):
        cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
        head, sep, body = cells[0], cells[1], cells[2:]
        align = ["right" if s.endswith(":") and not s.startswith(":") else ("center" if s.startswith(":") and s.endswith(":") else "left")
                 for s in sep]
        dense = " dense" if len(head) >= 6 else ""
        h = [f'<table class="t{dense}">']
        if cap:
            label = self.refs.get(ident, ("Table", ""))[0]
            h.insert(0, f'<div class="tablewrap" id="{ident}">')
            h.append(f'<caption><span class="fignum">{label}.</span> {inline(cap, self.refs)}</caption>')
        h.append("<thead><tr>" + "".join(f'<th style="text-align:{a}">{inline(c, self.refs)}</th>' for c, a in zip(head, align)) + "</tr></thead><tbody>")
        for r in body:
            r = r + [""] * (len(head) - len(r))
            h.append("<tr>" + "".join(f'<td style="text-align:{a}">{inline(c, self.refs)}</td>' for c, a in zip(r, align)) + "</tr>")
        h.append("</tbody></table>")
        if cap:
            h.append("</div>")
        return "".join(h)


# ---------------------------------------------------------------- pdf outline -> pages
def norm_title(t):
    """Outline titles: Chrome sometimes repeats a heading's text (top-of-page headings); compare letters+digits only."""
    t = " ".join(t.split())
    h = len(t) // 2
    if len(t) % 2 == 0 and t[:h] == t[h:]:
        t = t[:h]
    return re.sub(r"[^a-z0-9]", "", t.lower())


def pdf_heading_pages(pdf):
    d = pdf.read_bytes()
    objs = {int(m.group(1)): m.group(2) for m in re.finditer(rb"(\d+) 0 obj\s*(.*?)endobj", d, re.S)}

    def dict_of(n):
        return objs.get(n, b"")

    root_pages = None
    for n, body in objs.items():
        if re.search(rb"/Type\s*/Pages\b", body) and b"/Parent" not in body:
            root_pages = n
    order = []

    def walk(n):
        body = dict_of(n)
        if re.search(rb"/Type\s*/Page\b", body):
            order.append(n)
            return
        kids = re.search(rb"/Kids\s*\[(.*?)\]", body, re.S)
        for k in re.findall(rb"(\d+) 0 R", kids.group(1)) if kids else []:
            walk(int(k))

    walk(root_pages)
    page_of = {n: i + 1 for i, n in enumerate(order)}

    def pdf_string(raw):
        raw = raw.strip()
        if raw.startswith(b"<"):
            b = bytes.fromhex(raw[1:-1].decode())
            return b[2:].decode("utf-16-be") if b.startswith(b"\xfe\xff") else b.decode("latin-1")
        s = raw[1:-1]
        s = re.sub(rb"\\([nrtbf()\\])", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}.get(m.group(1), m.group(1)), s)
        s = re.sub(rb"\\(\d{1,3})", lambda m: bytes([int(m.group(1), 8)]), s)
        return s.decode("latin-1")

    res = {}
    for body in objs.values():
        t = re.search(rb"/Title\s*(<[0-9A-Fa-f\s]*>|\((?:\\.|[^\\)])*\))", body)
        dest = re.search(rb"/Dest\s*\[\s*(\d+) 0 R", body)
        if t and dest:
            res[norm_title(pdf_string(t.group(1)))] = page_of.get(int(dest.group(1)))
    return res, len(order)


def chrome_pdf(src, dst):
    uri = src.resolve().as_uri()
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--generate-pdf-document-outline", "--allow-file-access-from-files",
                        f"--print-to-pdf={dst}", uri], capture_output=True, text=True, timeout=300)
    if not dst.exists():
        raise SystemExit(f"chrome failed: {r.stderr[-2000:]}")


def build():
    md = []
    for f in sorted(SRC.glob("*.md")):
        md.extend(f.read_text(encoding="utf-8").splitlines())
        md.append("")
    doc = Doc(md)
    doc.number()
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    css = (HERE / "style.css").read_text(encoding="utf-8")

    def page(pages):
        toc = ['<nav class="toc" id="contents"><h1 class="front toc-title">Contents</h1><ol>']
        for lvl, num, title, ident, classes in doc.toc:
            if ident in ("contents", "title-page"):
                continue
            plain = re.sub(r"[`*]", "", title)
            key = norm_title(f"{num} {plain}")
            if lvl == 1:
                key = norm_title(f"Chapter {num} {plain}" if "chapter" in classes else (f"{num} {plain}" if num else plain))
            if lvl == 1:
                runs = (f"Chapter {num}" if "chapter" in classes else num, plain) if num else ("", plain)
            else:
                runs = (num, plain)
            doubled = "".join(norm_title(r) * 2 for r in runs)   # Chrome repeats each text run of a top-of-page heading
            numdbl = norm_title(runs[0]) * 2 + norm_title(runs[1])   # only the chapter label repeated
            pg = (pages.get(key) or pages.get(doubled) or pages.get(numdbl, "")) if pages else ""
            label = (f'<span class="toc-num">{num}</span>' if lvl == 2 else
                     (f'<span class="toc-num">{num}</span>' if num and "chapter" in classes else
                      (f'<span class="toc-num">{num.replace("Appendix ", "")}</span>' if num else '<span class="toc-num"></span>')))
            toc.append(f'<li class="l{lvl}"><a href="#{ident}">{label}<span class="toc-t">{inline(title, doc.refs)}</span>'
                       f'<span class="toc-dots"></span><span class="toc-pg">{pg}</span></a></li>')
        toc.append("</ol></nav>")
        body = doc.render()
        body = body.replace("<!--TOC-->", "\n".join(toc)).replace("@@COMMIT@@", head)
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>PS26172 Hey Vayro — Technical '
                f'Reconstruction Report</title><style>{css}</style></head><body>{body}</body></html>')

    tmp = HERE / "_pass1.pdf"
    OUT_HTML.write_text(page(None), encoding="utf-8")
    chrome_pdf(OUT_HTML, tmp)
    pages, n = pdf_heading_pages(tmp)
    # outline titles are the headings' text content: "Chapter 3 Title", "3.2 Title"
    OUT_HTML.write_text(page(pages), encoding="utf-8")
    chrome_pdf(OUT_HTML, OUT_PDF)
    pages2, n2 = pdf_heading_pages(OUT_PDF)
    tmp.unlink()
    missing = [t for lvl, num, t, ident, c in doc.toc if lvl <= 2 and ident not in ("contents",)
               and not any(norm_title(re.sub(r"[`*]", "", t)) in k for k in pages2)]
    print(f"pages {n2} (pass 1: {n}); headings in outline {len(pages2)}; TOC stable: {pages == pages2}; "
          f"chapters not found in outline: {missing}")
    print("written", OUT_PDF)


if __name__ == "__main__":
    build()
