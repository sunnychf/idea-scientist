#!/usr/bin/env python3
"""Search, fetch and read papers for the idea-scientist skill. Standard library only.

  python paper.py ping
  python paper.py search "QUERY" [--run RUN | --before YYYY-MM-DD] [--limit 10] [--abstracts] [--source all|arxiv|s2]
  python paper.py fetch ID --run RUN [--refresh]
  python paper.py show ID --run RUN [--section TEXT | --grep REGEX [--context N] | --lines A-B]

ID forms: 2401.12345, arXiv:2401.12345v2, arXiv / DOI / OpenReview URLs, doi:10.1145/...,
openreview:<forum id>, s2:<Semantic Scholar paperId>.
With --run, the Cutoff written in RUN/problem.md is applied automatically.
Optional: set S2_API_KEY for Semantic Scholar; install pypdf (or put pdftotext on PATH) for PDF-only papers.
Exit codes: 0 ok, 2 usage error, 3 network error, 4 refused (first released on/after the cutoff), 5 not found.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = "idea-scientist-skill/1.0 (research ideation; https://github.com/jiarui-liu/IdeaScientist)"
ARXIV_API = "https://export.arxiv.org/api/query"
S2_API = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "title,venue,year,publicationDate,externalIds,url,abstract"
TIMEOUT = 30
MAX_LINES = 400
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
STOPWORDS = set("a an and are as at be by for from in into is of on or the to with via using toward towards".split())
NEW_ARXIV = r"\d{4}\.\d{4,5}"
OLD_ARXIV = r"[a-z][a-z\-]*(?:\.[A-Za-z]{2})?/\d{7}"


class NetError(Exception):
    pass


class UsageError(Exception):
    pass


class NotFound(Exception):
    pass


# ---------------------------------------------------------------- helpers

def http_get(url, headers=None, tries=3):
    """Return (status, final_url, body). Retries 429/5xx; raises NetError if the host is unreachable."""
    hdrs = {"User-Agent": UA}
    hdrs.update(headers or {})
    wait, last = 2.0, None
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=TIMEOUT) as resp:
                return resp.status, resp.geturl(), resp.read()
        except urllib.error.HTTPError as e:
            try:
                body = e.read() or b""
            except Exception:
                body = b""
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                retry_after = (e.headers.get("Retry-After") or "") if e.headers else ""
                time.sleep(min(float(retry_after), 30.0) if retry_after.isdigit() else wait)
                wait *= 2.5
                continue
            return e.code, url, body
        except Exception as e:  # DNS failure, refused or sandbox-blocked socket, timeout
            last = e
            if attempt < min(tries, 2) - 1:
                time.sleep(wait)
                wait *= 2.5
                continue
            break
    raise NetError(f"{url}: {last}")


def s2_headers():
    key = os.environ.get("S2_API_KEY")
    return {"x-api-key": key} if key else {}


def squash(text):
    return " ".join((text or "").split())


def shorten(text, n):
    text = squash(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def safe_name(pid):
    return re.sub(r'[/:<>"\\|?*\s]', "_", pid)


def parse_id(raw):
    s = urllib.parse.unquote(raw.strip().strip("[]").strip())
    m = re.match(r"https?://(?:www\.|export\.)?(?:arxiv\.org|ar5iv\.labs\.arxiv\.org|ar5iv\.org)/"
                 r"(?:abs|pdf|html)/([^?#]+?)(?:\.pdf)?/?(?:[?#].*)?$", s, re.I)
    if m:
        s = m.group(1)
    m = re.match(r"https?://(?:dx\.)?doi\.org/(.+)$", s, re.I)
    if m:
        s = "doi:" + m.group(1)
    m = re.match(r"https?://openreview\.net/(?:forum|pdf)\?(?:.*&)?id=([^&#]+)", s, re.I)
    if m:
        s = "openreview:" + m.group(1)
    if s.lower().startswith("arxiv:"):
        s = s[6:]
    m = re.fullmatch(rf"({NEW_ARXIV}|{OLD_ARXIV})(?:v\d+)?", s)
    if m:
        return "arxiv", m.group(1)
    low = s.lower()
    if low.startswith("doi:"):
        return "doi", s[4:].strip().lower()
    if re.match(r"10\.\d{4,9}/\S+$", s):
        return "doi", s.lower()
    if low.startswith("openreview:"):
        return "openreview", s.split(":", 1)[1].strip()
    if low.startswith("s2:"):
        return "s2", s.split(":", 1)[1].strip()
    raise UsageError(f"unrecognized paper id: {raw}")


def canon(kind, val):
    return val if kind == "arxiv" else f"{kind}:{val}"


def check_date(value):
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        raise UsageError(f"bad date {value!r}: use YYYY-MM-DD")
    return value


def cutoff_from_run(run):
    if not run:
        return None
    prob = Path(run) / "problem.md"
    if not prob.exists():
        return None
    m = re.search(r"Cutoff[^:：\n]*[:：]\s*(\d{4}-\d{2}-\d{2})", prob.read_text(encoding="utf-8-sig"))
    return m.group(1) if m else None


def date_status(date, before):
    """'ok' if surely before the cutoff, 'post' if surely on/after it, '?' if the date is too coarse."""
    if not before:
        return "ok"
    if not date:
        return "?"
    d = date[:10]
    lo, hi = {4: (d + "-01-01", d + "-12-31"), 7: (d + "-01", d + "-31")}.get(len(d), (d, d))
    if hi < before:
        return "ok"
    if lo >= before:
        return "post"
    return "?"


def require_run(run):
    if not run:
        raise UsageError("--run RUN_DIR is required")
    p = Path(run)
    if not p.is_dir():
        raise UsageError(f"run directory not found: {run}")
    return p


def fulltext_path(run, pid):
    return Path(run) / "papers" / "_fulltext" / (safe_name(pid) + ".txt")


# ---------------------------------------------------------------- sources

def arxiv_query(params):
    status, _, body = http_get(ARXIV_API + "?" + urllib.parse.urlencode(params))
    if status != 200:
        raise NetError(f"arXiv API returned HTTP {status}")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise NetError(f"arXiv API returned unreadable XML: {e}")
    items = []
    for e in root.findall("a:entry", ATOM):
        id_url = squash(e.findtext("a:id", "", ATOM))
        title = squash(e.findtext("a:title", "", ATOM))
        if "/abs/" not in id_url or not title:
            continue
        aid = re.sub(r"v\d+$", "", id_url.split("/abs/", 1)[1])
        prim = e.find("arxiv:primary_category", ATOM)
        cat = prim.get("term", "") if prim is not None else ""
        items.append({
            "id": aid,
            "title": title,
            "abstract": squash(e.findtext("a:summary", "", ATOM)),
            "date": squash(e.findtext("a:published", "", ATOM))[:10],
            "updated": squash(e.findtext("a:updated", "", ATOM))[:10],
            "authors": [squash(a.findtext("a:name", "", ATOM)) for a in e.findall("a:author", ATOM)],
            "venue": f"arXiv {cat}".strip(),
            "url": f"https://arxiv.org/abs/{aid}",
        })
    return items


def arxiv_terms(query):
    try:
        tokens = shlex.split(query)
    except ValueError:
        tokens = query.split()
    parts = []
    for tok in tokens:
        tok = tok.replace('"', "").strip()
        if not tok or tok.lower() in STOPWORDS:
            continue
        parts.append(f'all:"{tok}"' if " " in tok else f"all:{tok}")
    if not parts:
        raise UsageError("empty query")
    return " AND ".join(parts)


def s2_item(p):
    ext = p.get("externalIds") or {}
    arx = ext.get("ArXiv")
    doi = ext.get("DOI")
    if arx:
        pid = re.sub(r"v\d+$", "", arx)
    elif doi:
        pid = "doi:" + doi.lower()
    else:
        pid = "s2:" + str(p.get("paperId") or "")
    date = p.get("publicationDate") or (str(p["year"]) if p.get("year") else "")
    return {
        "id": pid,
        "title": squash(p.get("title")),
        "abstract": squash(p.get("abstract")),
        "date": date[:10],
        "venue": squash(p.get("venue")),
        "url": p.get("url") or "",
        "authors": [squash(a.get("name")) for a in (p.get("authors") or []) if a.get("name")],
        "pdf": ((p.get("openAccessPdf") or {}).get("url") or ""),
        "arxiv": re.sub(r"v\d+$", "", arx) if arx else "",
    }


def s2_search(query, limit, before):
    params = {"query": squash(query.replace("-", " ").replace('"', "")), "limit": str(min(max(limit, 10), 100)),
              "fields": S2_FIELDS}
    if before:
        params["publicationDateOrYear"] = ":" + (dt.date.fromisoformat(before) - dt.timedelta(days=1)).isoformat()
    status, _, body = http_get(f"{S2_API}/paper/search?" + urllib.parse.urlencode(params), s2_headers())
    if status != 200:
        hint = " (rate limited: retry later or set S2_API_KEY)" if status == 429 else ""
        raise NetError(f"Semantic Scholar returned HTTP {status}{hint}")
    return [s2_item(p) for p in (json.loads(body).get("data") or []) if p.get("title")]


def meta_s2(key):
    url = f"{S2_API}/paper/{urllib.parse.quote(key, safe=':/')}?fields={S2_FIELDS},authors,openAccessPdf"
    status, _, body = http_get(url, s2_headers())
    if status == 404:
        return None
    if status != 200:
        raise NetError(f"Semantic Scholar returned HTTP {status}")
    return s2_item(json.loads(body))


def meta_crossref(doi):
    status, _, body = http_get("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/:;()<>"))
    if status != 200:
        return None
    m = json.loads(body).get("message") or {}
    parts = ((m.get("issued") or {}).get("date-parts") or [[None]])[0]
    date = "-".join(str(int(x)) if i == 0 else f"{int(x):02d}" for i, x in enumerate(parts) if x)
    return {
        "id": "doi:" + doi,
        "title": squash((m.get("title") or [""])[0]),
        "abstract": squash(re.sub(r"<[^>]+>", " ", m.get("abstract") or "")),
        "date": date,
        "venue": squash((m.get("container-title") or [""])[0]),
        "url": m.get("URL") or f"https://doi.org/{doi}",
        "authors": [squash(f"{a.get('given', '')} {a.get('family', '')}") for a in (m.get("author") or [])],
        "pdf": "",
    }


def meta_openreview(forum):
    notes = []
    for base in ("https://api2.openreview.net", "https://api.openreview.net"):
        status, _, body = http_get(f"{base}/notes?id={urllib.parse.quote(forum)}")
        if status == 200:
            notes = (json.loads(body) or {}).get("notes") or []
            if notes:
                break
    if not notes:
        return None
    note = notes[0]
    content = note.get("content") or {}

    def val(key):
        v = content.get(key)
        return v.get("value") if isinstance(v, dict) else v

    ms = note.get("odate") or note.get("pdate") or note.get("cdate") or note.get("tcdate")
    date = dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date().isoformat() if ms else ""
    return {
        "id": "openreview:" + forum,
        "title": squash(val("title")),
        "abstract": squash(val("abstract")),
        "date": date,
        "venue": squash(val("venue")) or "OpenReview",
        "url": f"https://openreview.net/forum?id={forum}",
        "authors": [squash(a) for a in (val("authors") or []) if isinstance(a, str)],
        "pdf": f"https://openreview.net/pdf?id={forum}",
    }


# ---------------------------------------------------------------- full text

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript", "svg", "button", "form", "head"}
SKIP_CLASSES = ("ltx_page_navbar", "ltx_page_footer", "ltx_TOC", "ltx_page_logo")
BLOCK = {"p", "div", "section", "article", "main", "li", "ul", "ol", "figure", "figcaption", "table", "thead",
         "tbody", "tr", "blockquote", "pre", "dd", "dt", "dl", "caption"}
HEADS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class _HTMLText(HTMLParser):
    """HTML to text with markdown headings; keeps LaTeX for <math alttext=...> (arXiv / ar5iv LaTeXML)."""

    def __init__(self, root_class=""):
        super().__init__(convert_charrefs=True)
        self.root_class = root_class
        self.lines, self.buf, self.stack = [], [], []
        self.in_root = 0 if root_class else 1
        self.skip = 0
        self.math = False

    def active(self):
        return self.in_root > 0 and not self.skip and not self.math

    def flush(self, prefix=""):
        text = squash("".join(self.buf))
        text = re.sub(r"\$ ([.,;:!?)\]])", r"$\1", re.sub(r"([(\[]) \$", r"\1$", text))
        self.buf = []
        if text:
            self.lines.append(prefix + text)

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            if tag in ("br", "hr") and self.active():
                self.flush()
            return
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        is_root = bool(self.root_class) and self.root_class in classes
        is_skip = tag in SKIP_TAGS or any(c in classes for c in SKIP_CLASSES)
        self.stack.append((tag, is_root, is_skip))
        if is_root:
            self.in_root += 1
        if is_skip:
            self.skip += 1
        if not self.active():
            return
        if tag == "math":
            alt = squash(attrs.get("alttext"))
            if alt:
                self.buf.append(f" ${alt}$ ")
            self.math = True
        elif tag in HEADS or tag in BLOCK:
            self.flush()

    def handle_endtag(self, tag):
        if tag in VOID or all(t != tag for t, _, _ in self.stack):
            return
        while self.stack:
            t, is_root, is_skip = self.stack.pop()
            if t == "math":
                self.math = False
            elif self.active():
                if t in HEADS:
                    self.flush("#" * HEADS[t] + " ")
                elif t in BLOCK:
                    self.flush()
                elif t in ("td", "th"):
                    self.buf.append(" | ")
            if is_skip:
                self.skip -= 1
            if is_root:
                if self.active():
                    self.flush()
                self.in_root -= 1
            if t == tag:
                break

    def handle_data(self, data):
        if self.active():
            self.buf.append(data)


def html_to_text(html):
    parser = _HTMLText("ltx_document" if "ltx_document" in html else "")
    parser.feed(html)
    parser.close()
    parser.flush()
    out = []
    for line in parser.lines:
        if line.startswith("#") and out and out[-1] != "":
            out.append("")
        out.append(line)
    return "\n".join(out)


PDF_HEAD = re.compile(r"^(?:(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+)?([A-Z][A-Za-z0-9 ,:&()/\-]{1,70})$")
COMMON_HEADS = {"abstract", "introduction", "related work", "background", "preliminaries", "method", "methods",
                "approach", "experiments", "evaluation", "results", "discussion", "conclusion", "conclusions",
                "references", "acknowledgments", "acknowledgements", "appendix", "limitations"}


def mark_pdf_headings(text):
    out = []
    for line in text.splitlines():
        s = line.strip()
        m = PDF_HEAD.match(s)
        if m and len(s.split()) <= 8 and not s.endswith("."):
            num, name = m.group(1), m.group(2).strip()
            if num and int(num.split(".")[0]) <= 20:
                out.append("#" * (2 + num.count(".")) + " " + s)
                continue
            if not num and name.lower() in COMMON_HEADS:
                out.append("## " + s)
                continue
        out.append(line)
    return "\n".join(out)


def pdf_to_text(data):
    text, how = None, ""
    try:
        from pypdf import PdfReader
    except ImportError:
        PdfReader = None
    if PdfReader is not None:
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = []
            for i, page in enumerate(reader.pages, 1):
                try:
                    pages.append(f"[page {i}]\n{(page.extract_text() or '').strip()}")
                except Exception:
                    pages.append(f"[page {i}]")
            text, how = "\n\n".join(pages), "pdf/pypdf"
        except Exception:
            text = None
    if text is None and shutil.which("pdftotext"):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "paper.pdf"
            src.write_bytes(data)
            r = subprocess.run(["pdftotext", "-enc", "UTF-8", str(src), "-"], capture_output=True, timeout=180)
            if r.returncode == 0:
                pages = r.stdout.decode("utf-8", "replace").split("\f")
                text = "\n\n".join(f"[page {i}]\n{p.strip()}" for i, p in enumerate(pages, 1) if p.strip())
                how = "pdf/pdftotext"
    if text is None:
        return None, "no PDF text extractor (pip install pypdf)"
    if len(re.sub(r"\[page \d+\]|\s", "", text)) < 1000:
        return None, "the PDF has no extractable text (scanned?)"
    return mark_pdf_headings(text), how


def pdf_from_url(url, tried):
    try:
        status, _, body = http_get(url, tries=2)
    except NetError as e:
        tried.append(f"pdf: {e}")
        return None, ""
    if status != 200 or not body.lstrip().startswith(b"%PDF"):
        tried.append(f"pdf: HTTP {status}" + (" (not a PDF)" if status == 200 else ""))
        return None, ""
    text, how = pdf_to_text(body)
    if text is None:
        tried.append(f"pdf: {how}")
        return None, ""
    return text, how


def arxiv_fulltext(aid, version, tried):
    sources = [("arxiv-html", f"https://arxiv.org/html/{aid}{version}")]
    if not version:  # ar5iv only serves the latest version
        sources.append(("ar5iv-html", f"https://ar5iv.labs.arxiv.org/html/{aid}"))
    for label, url in sources:
        try:
            status, _, body = http_get(url, tries=2)
        except NetError as e:
            tried.append(f"{label}: {e}")
            continue
        if status == 200 and b"ltx_document" in body:
            text = html_to_text(body.decode("utf-8", "replace"))
            if len(text) > 2000:
                return text, label
        tried.append(f"{label}: HTTP {status}" + (" (no full-text document)" if status == 200 else ""))
    return pdf_from_url(f"https://arxiv.org/pdf/{aid}{version}", tried)


# ---------------------------------------------------------------- output

def read_lines(path):
    return path.read_text(encoding="utf-8-sig").splitlines()


def header_of(lines):
    head = {"Title": lines[0][2:].strip() if lines and lines[0].startswith("# ") else ""}
    for ln in lines[1:15]:
        if ln.startswith("-----"):
            break
        if ":" in ln:
            k, v = ln.split(":", 1)
            head[k.strip()] = v.strip()
    return head


def outline(lines, limit=80):
    heads = [(i + 1, ln) for i, ln in enumerate(lines) if i > 0 and re.match(r"#{1,6} ", ln)]
    for n, ln in heads[:limit]:
        print(f"  L{n:<6}{ln}")
    if len(heads) > limit:
        print(f"  ... {len(heads) - limit} more headings (use --grep to locate them)")
    if not heads:
        print("  (no headings detected: use --grep or --lines)")


def print_summary(run, path, cached):
    lines = read_lines(path)
    h = header_of(lines)
    pid = h.get("ID", "")
    date = h.get("Date", "").split(" ")[0]
    access = h.get("Access", "").split(" ")[0]
    digest = Path(run) / "papers" / (safe_name(pid) + ".md")
    print(f"{'Cached' if cached else 'Saved'}: {path} ({len(lines)} lines)")
    print(f"Title: {h.get('Title', '')}")
    print(f"Cite as: [{pid}]")
    if h.get("Note"):
        print(f"Note: {h['Note']}")
    if access != "full-text":
        print("Access is abstract-only: this paper cannot support mechanism-level claims.")
    state = "exists: reuse answered goals, append only new ones" if digest.exists() else "new"
    print(f"Digest file: {digest} ({state})")
    print("Digest header (put these two lines right under '# <title>'):")
    print(f"- ID: {pid} | Date: {date} | Venue: {h.get('Venue', '')} | URL: {h.get('URL', '')}")
    print(f"- Access: {access}")
    print("Outline (line numbers):")
    outline(lines)
    print(f'Next: paper.py show {pid} --run "{run}" --section "<number or title>"'
          f' | --grep "<regex>" --context 3 | --lines A-B')
    return 0


def print_range(lines, start, end, note=""):
    end = min(end, len(lines))
    if end - start + 1 > MAX_LINES:
        note = f"(truncated at {MAX_LINES} lines; continue with --lines {start + MAX_LINES}-{end})"
        end = start + MAX_LINES - 1
    for n in range(start, end + 1):
        print(f"{n:>6}| {lines[n - 1]}")
    if note:
        print(note)


def save_fulltext(path, meta, access, how, text):
    head = [f"# {meta.get('title') or meta['id']}",
            f"ID: {meta['id']}",
            f"Date: {meta.get('date') or 'unknown'} (first public release)",
            f"Venue: {meta.get('venue') or ''}",
            f"URL: {meta.get('url') or ''}",
            f"Access: {access} ({how})"]
    authors = meta.get("authors") or []
    if authors:
        head.append("Authors: " + ", ".join(authors[:8]) + (" et al." if len(authors) > 8 else ""))
    if meta.get("note"):
        head.append(f"Note: {meta['note']}")
    head.append("-" * 40)
    body = text or "## Abstract\n" + (meta.get("abstract") or "(no abstract available)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(head) + "\n" + body.strip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------- commands

def cmd_ping(args):
    ok = True
    checks = (("arXiv API", f"{ARXIV_API}?id_list=1706.03762&max_results=1", {}),
              ("arXiv pages", "https://arxiv.org/abs/1706.03762", {}),
              ("Semantic Scholar", f"{S2_API}/paper/ARXIV:1706.03762?fields=title", s2_headers()))
    for name, url, hdrs in checks:
        try:
            status, _, _ = http_get(url, hdrs, tries=1)
            print(f"{name}: HTTP {status}")
            ok = ok and (status == 200 or name == "Semantic Scholar")
        except NetError as e:
            print(f"{name}: unreachable ({e})")
            ok = ok and name == "Semantic Scholar"
    try:
        import pypdf
        print(f"pypdf: {pypdf.__version__}")
    except ImportError:
        print("pypdf: not installed (PDF-only papers will be abstract-only; `pip install pypdf` enables them)")
    print("pdftotext: " + ("found" if shutil.which("pdftotext") else "not found"))
    if not ok:
        print("arXiv is unreachable from this shell: approve network access for this command, or use web_search.")
    return 0 if ok else 3


def cmd_search(args):
    before = check_date(args.before) if args.before else cutoff_from_run(args.run)
    pool = min(args.limit * 3, 50) if before else args.limit
    lists, notes = [], []
    if args.source in ("all", "arxiv"):
        try:
            lists.append(arxiv_query({"search_query": arxiv_terms(args.query), "start": "0",
                                      "max_results": str(pool), "sortBy": "relevance",
                                      "sortOrder": "descending"}))
        except NetError as e:
            notes.append(f"arXiv failed: {e}")
    if args.source in ("all", "s2"):
        try:
            lists.append(s2_search(args.query, pool, before))
        except NetError as e:
            notes.append(f"Semantic Scholar failed: {e}")
    if not lists:
        raise NetError("; ".join(notes))
    results, by_id, by_title = [], {}, {}
    for i in range(max(len(lst) for lst in lists)):
        for lst in lists:
            if i >= len(lst):
                continue
            item = lst[i]
            tkey = re.sub(r"[^a-z0-9]", "", item["title"].lower())[:80]
            hit = by_id.get(item["id"]) or (by_title.get(tkey) if tkey else None)
            if hit:
                if item["venue"] and item["venue"].lower() not in hit["venue"].lower():
                    hit["venue"] = f"{hit['venue']}; {item['venue']}" if hit["venue"] else item["venue"]
                hit["abstract"] = hit["abstract"] or item["abstract"]
                if hit["id"].startswith(("doi:", "s2:")) and not item["id"].startswith(("doi:", "s2:")):
                    by_id.pop(hit["id"], None)
                    hit["id"], hit["date"] = item["id"], item["date"] or hit["date"]
                    by_id[hit["id"]] = hit
                continue
            status = date_status(item["date"], before)
            if status == "post":
                continue
            item = dict(item, flag=status)
            results.append(item)
            by_id[item["id"]] = item
            if tkey:
                by_title[tkey] = item
    print(f"query: {args.query} | cutoff: {before or 'none'} | results: {min(len(results), args.limit)}")
    for note in notes:
        print(f"NOTE {note}")
    for item in results[: args.limit]:
        flag = " date?" if item.get("flag") == "?" else ""
        print(f"[{item['id']}] {item['date'] or '????'}{flag} | {item['venue'] or '-'} | {item['title']}")
        if args.abstracts and item["abstract"]:
            print("    " + shorten(item["abstract"], 320))
    if not results:
        print("(no results: rephrase with fewer or more standard terms)")
    return 0


def cmd_fetch(args):
    run = require_run(args.run)
    kind, val = parse_id(args.id)
    before = cutoff_from_run(run)
    pid = canon(kind, val)
    path = fulltext_path(run, pid)
    if path.exists() and not args.refresh:
        return print_summary(run, path, cached=True)
    tried, note = [], ""
    if kind == "arxiv":
        found = arxiv_query({"id_list": val, "max_results": "1"})
        if not found:
            raise NotFound(f"[{pid}] is not on arXiv")
        meta = found[0]
    elif kind in ("doi", "s2"):
        try:
            s2 = meta_s2(("DOI:" + val) if kind == "doi" else val)
        except NetError as e:
            if kind != "doi":
                raise
            s2 = None
            tried.append(str(e))
        if s2 and s2.get("arxiv"):
            note = f"{pid} has an arXiv version: cite it as [{s2['arxiv']}]"
            print(f"Note: {note}")
            kind, val, pid = "arxiv", s2["arxiv"], s2["arxiv"]
            path = fulltext_path(run, pid)
            if path.exists() and not args.refresh:
                return print_summary(run, path, cached=True)
            found = arxiv_query({"id_list": val, "max_results": "1"})
            if not found:
                raise NotFound(f"[{pid}] is not on arXiv")
            meta = found[0]
            if s2.get("venue") and s2["venue"].lower() not in meta["venue"].lower():
                meta["venue"] += f"; {s2['venue']}"
        else:
            meta = s2 or (meta_crossref(val) if kind == "doi" else None)
            if not meta:
                raise NotFound(f"[{pid}] was not found" + (f" ({'; '.join(tried)})" if tried else ""))
    else:
        meta = meta_openreview(val)
        if not meta:
            raise NotFound(f"[{pid}] was not found on OpenReview")
    meta["id"] = pid
    notes = [note] if note else []
    status = date_status(meta.get("date", ""), before)
    if status == "post":
        print(f"REFUSED: [{pid}] was first released {meta['date']}, on or after the cutoff {before}. "
              "Do not read or cite it.")
        return 4
    text, how = None, ""
    if kind == "arxiv":
        version = "v1" if before and meta.get("updated", "") >= before else ""
        if version:
            notes.append("later versions are after the cutoff, so v1 is used")
        text, how = arxiv_fulltext(val, version, tried)
    elif meta.get("pdf"):
        text, how = pdf_from_url(meta["pdf"], tried)
    if notes:
        meta["note"] = "; ".join(notes)
    save_fulltext(path, meta, "full-text" if text else "abstract-only", how or "abstract", text)
    if not text:
        print("Full text unavailable" + (": " + "; ".join(tried) if tried else "") + ".")
    if status == "?":
        print(f"WARNING: the date {meta.get('date') or 'unknown'} is too coarse to compare with the cutoff "
              f"{before}; confirm the first release date before relying on this paper.")
    return print_summary(run, path, cached=False)


def cmd_show(args):
    run = require_run(args.run)
    kind, val = parse_id(args.id)
    pid = canon(kind, val)
    path = fulltext_path(run, pid)
    if not path.exists():
        print(f"No saved full text for [{pid}]. Run `paper.py fetch {pid} --run ...` first; if fetch reported "
              "an arXiv version, use that ID.")
        return 5
    lines = read_lines(path)
    if args.lines:
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", args.lines.strip())
        if not m:
            raise UsageError("--lines takes A-B, e.g. 120-200")
        print_range(lines, max(1, int(m.group(1))), int(m.group(2)))
        return 0
    if args.section:
        query = args.section.strip().lower()
        numeric = re.fullmatch(r"\d+(?:\.\d+)*\.?|[A-Z](?:\.\d+)*", args.section.strip())
        heads = []
        for i, ln in enumerate(lines):
            m = re.match(r"(#{1,6})\s+(.*)", ln)
            if m and i > 0:
                heads.append((i, len(m.group(1)), m.group(2).strip().lower()))
        hit = None
        for i, level, text in heads:
            if numeric:
                if re.match(re.escape(query.rstrip(".")) + r"\.?\s", text + " "):
                    hit = (i, level)
                    break
            elif text.lstrip("0123456789. ") == query:
                hit = (i, level)
                break
        if hit is None and not numeric:
            hit = next(((i, level) for i, level, text in heads if query in text), None)
        if hit is None:
            print(f"No heading matches {args.section!r}. Outline:")
            outline(lines)
            return 5
        start, level = hit
        end = next((i for i, lv, _ in heads if i > start and lv <= level), len(lines))
        print_range(lines, start + 1, end)
        return 0
    if args.grep:
        try:
            rx = re.compile(args.grep, re.I)
        except re.error:
            rx = re.compile(re.escape(args.grep), re.I)
        hits = [i for i, ln in enumerate(lines) if rx.search(ln)]
        if not hits:
            print(f"No line matches {args.grep!r}.")
            return 0
        shown, last = 0, -1
        for i in hits[:40]:
            lo, hi = max(0, i - args.context), min(len(lines) - 1, i + args.context)
            if lo > last + 1 and last >= 0:
                print("  --")
            for n in range(max(lo, last + 1), hi + 1):
                print(f"{n + 1:>6}{'*' if rx.search(lines[n]) else '|'} {lines[n]}")
                shown += 1
            last = hi
            if shown >= MAX_LINES:
                break
        if len(hits) > 40 or shown >= MAX_LINES:
            print(f"({len(hits)} matching lines in total; narrow the pattern)")
        return 0
    return print_summary(run, path, cached=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping", help="check network access and PDF support")
    p = sub.add_parser("search", help="search arXiv and Semantic Scholar")
    p.add_argument("query")
    p.add_argument("--run", help="run directory; its problem.md Cutoff is applied")
    p.add_argument("--before", help="only papers first released before this date (YYYY-MM-DD)")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--abstracts", action="store_true", help="also print a short abstract")
    p.add_argument("--source", choices=("all", "arxiv", "s2"), default="all")
    p = sub.add_parser("fetch", help="download a paper's full text into RUN/papers/_fulltext/")
    p.add_argument("id")
    p.add_argument("--run", required=True)
    p.add_argument("--refresh", action="store_true", help="download again even if cached")
    p = sub.add_parser("show", help="print part of a fetched paper")
    p.add_argument("id")
    p.add_argument("--run", required=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--section", help="heading number (3, 3.2, A) or heading text")
    g.add_argument("--grep", help="regular expression, case-insensitive")
    g.add_argument("--lines", help="line range A-B")
    p.add_argument("--context", type=int, default=2, help="context lines for --grep")
    args = ap.parse_args(argv)
    try:
        return {"ping": cmd_ping, "search": cmd_search, "fetch": cmd_fetch, "show": cmd_show}[args.cmd](args)
    except UsageError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2
    except NetError as e:
        print(f"NETWORK ERROR {e}\nThe sandbox may be blocking network access: approve network access for "
              "this command, or fall back to web_search.", file=sys.stderr)
        return 3
    except NotFound as e:
        print(f"NOT FOUND {e}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    sys.exit(main())
