"""Offline tests for codex/idea-scientist/scripts/paper.py: every network call is served from fixtures.

Usage: python tests/test_paper.py [WORK_DIR]
"""
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True  # keep __pycache__ out of the skill folder
SKILL = Path(__file__).resolve().parents[1] / "codex" / "idea-scientist"
WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="idea-scientist-test-"))
spec = importlib.util.spec_from_file_location("paper", SKILL / "scripts" / "paper.py")
paper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paper)


def atom(entries):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" '
           'xmlns:arxiv="http://arxiv.org/schemas/atom">',
           '<title type="html">ArXiv Query</title><opensearch:totalResults>%d</opensearch:totalResults>' % len(entries)]
    for aid, pub, upd, title, cat in entries:
        out.append(f"""<entry><id>http://arxiv.org/abs/{aid}v2</id><updated>{upd}T10:00:00Z</updated>
<published>{pub}T09:00:00Z</published><title>{title}
  (extended)</title><summary>  We study {title.lower()} and propose a method.
  It works.</summary><author><name>Ada Lovelace</name></author><author><name>Alan Turing</name></author>
<arxiv:comment>12 pages</arxiv:comment><link href="http://arxiv.org/abs/{aid}v2" rel="alternate" type="text/html"/>
<arxiv:primary_category term="{cat}" scheme="http://arxiv.org/schemas/atom"/>
<category term="{cat}" scheme="http://arxiv.org/schemas/atom"/></entry>""")
    out.append("</feed>")
    return "\n".join(out).encode()


ERROR_FEED = atom([]).replace(b"</feed>", b"<entry><id>http://arxiv.org/api/errors#incorrect_id_format_for_x</id>"
                              b"<title>Error</title><summary>incorrect id format for x</summary></entry></feed>")

ENTRIES = {
    "2401.00001": ("2401.00001", "2024-01-02", "2024-03-05", "Learned Cardinality Estimation With Sketches", "cs.DB"),
    "2512.00002": ("2512.00002", "2025-12-30", "2026-02-10", "Robust Join Ordering Under Drift", "cs.DB"),
    "2602.00003": ("2602.00003", "2026-02-01", "2026-02-01", "A Post Cutoff Optimizer", "cs.DB"),
}

LATEXML = """<!DOCTYPE html><html><head><title>t</title><script>var x = 1;</script></head><body>
<div class="ltx_page_main"><header class="desktop_header">Report issue for preceding element</header>
<nav class="ltx_page_navbar"><ul><li>1 Introduction</li><li>3 Method</li></ul></nav>
<div class="ltx_page_content"><article class="ltx_document ltx_authors_1line">
<h1 class="ltx_title ltx_title_document">Learned Cardinality Estimation With Sketches</h1>
<div class="ltx_abstract"><h6 class="ltx_title ltx_title_abstract">Abstract</h6>
<p class="ltx_p">We estimate join sizes with <math alttext="O(\\log n)" class="ltx_Math"><semantics><mrow><mi>O</mi></mrow>
<annotation encoding="application/x-tex">O(\\log n)</annotation></semantics></math> memory.</p></div>
<section id="S1" class="ltx_section"><h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">1 </span>Introduction</h2>
<div class="ltx_para"><p class="ltx_p">Query optimizers rely on cardinality estimates <cite class="ltx_cite">[<a href="#bib.bib1">1</a>]</cite>.
Errors compound across joins.</p></div></section>
<section id="S2" class="ltx_section"><h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">2 </span>Related Work</h2>
<div class="ltx_para"><p class="ltx_p">Sampling based estimators are cheap but miss rare joins.</p></div></section>
<section id="S3" class="ltx_section"><h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">3 </span>Method</h2>
<div class="ltx_para"><p class="ltx_p">We combine count-min sketches with a learned correction.</p></div>
<section id="S3.SS1" class="ltx_subsection"><h3 class="ltx_title ltx_title_subsection"><span class="ltx_tag ltx_tag_subsection">3.1 </span>Sketch Layer</h3>
<div class="ltx_para"><p class="ltx_p">Each column keeps a sketch of width <math alttext="w" class="ltx_Math"><mi>w</mi></math>.</p>
<table class="ltx_tabular"><tr><td>Dataset</td><td>Rows</td></tr><tr><td>IMDB</td><td>74M</td></tr></table></div></section>
<section id="S3.SS2" class="ltx_subsection"><h3 class="ltx_title ltx_title_subsection"><span class="ltx_tag ltx_tag_subsection">3.2 </span>Correction</h3>
<div class="ltx_para"><p class="ltx_p">A small model corrects the sketch bias.</p></div></section></section>
<section id="S4" class="ltx_section"><h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">4 </span>Limitations</h2>
<div class="ltx_para"><p class="ltx_p">The approach assumes static data distributions.<br>Updates require rebuilding sketches.</p></div></section>
<section id="bib" class="ltx_bibliography"><h2 class="ltx_title ltx_title_bibliography">References</h2>
<ul class="ltx_biblist"><li class="ltx_bibitem">[1] V. Leis et al. How good are query optimizers, really? PVLDB 2015.</li></ul></section>
""" + "<div class=\"ltx_para\"><p class=\"ltx_p\">" + ("Filler sentence about estimation quality. " * 60) + "</p></div>" + """
</article></div><footer class="ltx_page_footer">Generated by LaTeXML</footer></div></body></html>"""


def make_pdf(pages):
    objs, kids = [], []
    font_id = 3 + 2 * len(pages)
    for i, lines in enumerate(pages):
        page_id, content_id = 3 + 2 * i, 4 + 2 * i
        kids.append(f"{page_id} 0 R")
        ops = ["BT", "/F1 10 Tf", "72 740 Td", "13 TL"]
        for ln in lines:
            ops.append("(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objs.append((page_id, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
                              f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()))
        objs.append((content_id, b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
    objs = [(1, b"<< /Type /Catalog /Pages 2 0 R >>"),
            (2, f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode())] + objs
    objs.append((font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    objs.sort()
    data, offsets = bytearray(b"%PDF-1.4\n"), {}
    for oid, body in objs:
        offsets[oid] = len(data)
        data += b"%d 0 obj\n" % oid + body + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for oid in range(1, len(objs) + 1):
        data += b"%010d 00000 n \n" % offsets[oid]
    data += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(data)


PDF = make_pdf([
    ["Robust Join Ordering Under Drift", "Abstract", "We study join ordering when data drifts over time."]
    + [f"Body sentence number {i} about plans and drift in the optimizer." for i in range(25)],
    ["1 Introduction", "Optimizers pick plans with stale statistics."]
    + [f"Introduction filler sentence {i} on robustness of plans." for i in range(20)]
    + ["2 Robust Planning", "We choose plans that minimize worst case regret.", "References",
       "[1] Someone. A paper. 2020."],
])

S2_SEARCH = {"total": 4, "offset": 0, "data": [
    {"paperId": "a" * 40, "title": "Learned Cardinality Estimation With Sketches (extended)", "venue": "SIGMOD",
     "year": 2024, "publicationDate": "2024-06-09", "externalIds": {"ArXiv": "2401.00001", "DOI": "10.1145/1111111"},
     "url": "https://www.semanticscholar.org/paper/aaa", "abstract": None},
    {"paperId": "b" * 40, "title": "Robust Query Optimization via Plan Diagrams", "venue": "VLDB", "year": 2023,
     "publicationDate": "2023-05-02", "externalIds": {"DOI": "10.14778/2222222"}, "url": "u2",
     "abstract": "Plan diagrams reveal fragile choices."},
    {"paperId": "c" * 40, "title": "Something From 2026", "venue": "CIDR", "year": 2026, "publicationDate": None,
     "externalIds": {}, "url": "u3", "abstract": None},
    {"paperId": "d" * 40, "title": "Robust Join Ordering Under Drift (Extended)", "venue": "PVLDB", "year": 2025,
     "publicationDate": "2025-11-01", "externalIds": {"DOI": "10.14778/9999999"}, "url": "u4", "abstract": None},
    {"paperId": "e" * 40, "title": "Year Only Twenty Twenty Five", "venue": "", "year": 2025,
     "publicationDate": None, "externalIds": {}, "url": "u5", "abstract": None},
]}

CALLS = []
MODE = {"net_down": False, "s2_429": False}


def fake_http_get(url, headers=None, tries=3):
    CALLS.append(url)
    if MODE["net_down"]:
        raise paper.NetError(f"{url}: <urlopen error [Errno -3] Temporary failure in name resolution>")
    if url.startswith(paper.ARXIV_API):
        q = paper.urllib.parse.parse_qs(paper.urllib.parse.urlparse(url).query)
        if "id_list" in q:
            aid = q["id_list"][0]
            if aid == "x":
                return 200, url, ERROR_FEED
            return 200, url, atom([ENTRIES[aid]] if aid in ENTRIES else [])
        assert "all:" in q["search_query"][0], q
        return 200, url, atom(list(ENTRIES.values()))
    if url.startswith(paper.S2_API + "/paper/search"):
        if MODE["s2_429"]:
            return 429, url, b'{"message": "Too Many Requests"}'
        q = paper.urllib.parse.parse_qs(paper.urllib.parse.urlparse(url).query)
        assert "-" not in q["query"][0]
        if "publicationDateOrYear" in q:
            assert paper.re.fullmatch(r":\d{4}-\d{2}-\d{2}", q["publicationDateOrYear"][0]), q
            if q["publicationDateOrYear"][0] == ":2025-12-31":
                CALLS.append("S2 day-before ok")
        return 200, url, json.dumps(S2_SEARCH).encode()
    if url.startswith(paper.S2_API + "/paper/"):
        key = paper.urllib.parse.unquote(url.split("/paper/", 1)[1].split("?", 1)[0])
        if key == "DOI:10.1145/1111111":
            return 200, url, json.dumps(S2_SEARCH["data"][0]).encode()
        if key == "DOI:10.14778/2222222":
            item = dict(S2_SEARCH["data"][1], openAccessPdf={"url": "https://vldb.example/p2222.pdf", "status": "GREEN"},
                        authors=[{"name": "Grace Hopper"}])
            return 200, url, json.dumps(item).encode()
        if key == "DOI:10.1145/3333333":
            return 429, url, b"{}"
        return 404, url, b'{"error": "Paper not found"}'
    if url.startswith("https://api.crossref.org/works/"):
        return 200, url, json.dumps({"status": "ok", "message": {
            "title": ["A Crossref Only Paper"], "container-title": ["Proceedings of the ACM on Management of Data"],
            "issued": {"date-parts": [[2024, 3]]}, "URL": "https://doi.org/10.1145/3333333",
            "abstract": "<jats:p>We do things.</jats:p>", "author": [{"given": "Edgar", "family": "Codd"}]}}).encode()
    if url == "https://arxiv.org/html/2401.00001":
        return 200, url + "v2", LATEXML.encode()
    if url.startswith("https://arxiv.org/html/") or url.startswith("https://ar5iv.labs.arxiv.org/html/"):
        return 404, url, b"<html>No HTML for this paper</html>"
    if url in ("https://arxiv.org/pdf/2512.00002v1", "https://vldb.example/p2222.pdf", "https://openreview.net/pdf?id=AbCdEf123"):
        return 200, url, PDF
    if url.startswith("https://api2.openreview.net/notes"):
        return 200, url, json.dumps({"notes": [{"id": "AbCdEf123", "forum": "AbCdEf123", "odate": 1695859200000,
                                               "cdate": 1695800000000, "content": {
            "title": {"value": "An OpenReview Paper"}, "abstract": {"value": "Abstract here."},
            "venue": {"value": "ICLR 2024 poster"}, "authors": {"value": ["Yoshua B"]}}}]}).encode()
    if url.startswith("https://arxiv.org/abs/") or url.startswith(paper.S2_API):
        return 200, url, b"ok"
    raise AssertionError(f"unexpected url {url}")


paper.http_get = fake_http_get
try:
    import pypdf  # noqa: F401
    HAS_PDF = True
except ImportError:
    HAS_PDF = bool(shutil.which("pdftotext"))
print(f"PDF extractor available: {HAS_PDF}")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = paper.main(list(argv))
    return code, out.getvalue() + err.getvalue()


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        check.failed += 1


check.failed = 0

# --- id parsing
cases = {"2401.00001": ("arxiv", "2401.00001"), "arXiv:2401.00001v3": ("arxiv", "2401.00001"),
         "https://arxiv.org/abs/2401.00001v2": ("arxiv", "2401.00001"), "https://arxiv.org/pdf/2401.00001.pdf": ("arxiv", "2401.00001"),
         "https://arxiv.org/abs/cs/0112017": ("arxiv", "cs/0112017"), "[2401.00001]": ("arxiv", "2401.00001"),
         "doi:10.1145/ABC.123": ("doi", "10.1145/abc.123"), "https://doi.org/10.14778/3611479.3611527": ("doi", "10.14778/3611479.3611527"),
         "10.1145/3639322": ("doi", "10.1145/3639322"), "https://openreview.net/forum?id=AbC_d-1&noteId=x": ("openreview", "AbC_d-1"),
         "openreview:XyZ": ("openreview", "XyZ"), "s2:" + "a" * 40: ("s2", "a" * 40)}
for raw, want in cases.items():
    got = paper.parse_id(raw)
    check(got == want, f"parse_id({raw!r}) -> {got}")
check(paper.safe_name('doi:10.1002/(SICI)1097<693::AID>3.0.CO;2-O') == "doi_10.1002_(SICI)1097_693__AID_3.0.CO;2-O", "safe_name strips Windows-illegal characters")
check(paper.date_status("2025", "2026-01-01") == "ok" and paper.date_status("2026", "2026-01-01") == "post"
      and paper.date_status("2026-03", "2026-03-15") == "?" and paper.date_status("2026-02-01", "2026-01-01") == "post", "date_status")

# --- run dir with a cutoff (full-width colon, as a Chinese user might type)
rd = WORK / "run"
shutil.rmtree(rd, ignore_errors=True)
rd.mkdir(parents=True)
(rd / "problem.md").write_text("Challenge: x\nProblem definition: y\nCutoff（可选）：2026-01-01\n", encoding="utf-8")

# --- search
code, out = run("search", "learned cardinality-estimation for joins", "--run", str(rd), "--limit", "10", "--abstracts")
print(out)
check(code == 0, "search exits 0")
check("cutoff: 2026-01-01" in out, "search reads the cutoff from problem.md")
check("2602.00003" not in out and "Something From 2026" not in out, "post-cutoff papers are filtered")
check(out.count("[2401.00001]") == 1 and "SIGMOD" in out, "arXiv and S2 records merge by arXiv id, venue kept")
check(out.count("Robust Join Ordering") == 1 and "PVLDB" in out, "arXiv and S2-DOI records merge by title")
check("[doi:10.14778/2222222]" in out and "Plan diagrams reveal" in out, "DOI-only paper listed with abstract")
check("S2 day-before ok" in CALLS, "S2 date filter is the day before the cutoff")
code, out = run("search", "join ordering", "--before", "2025-06-01")
line = next((l for l in out.splitlines() if "Year Only" in l), "")
check("2025 date?" in line, "year-only date that straddles the cutoff is flagged date?")
MODE["s2_429"] = True
code, out = run("search", "join ordering", "--before", "2026-01-01", "--source", "all")
check(code == 0 and "NOTE Semantic Scholar failed" in out and "[2401.00001]" in out, "S2 rate limit degrades to arXiv only")
MODE["s2_429"] = False
code, out = run("search", "x", "--before", "2026-13-01")
check(code == 2 and "bad date" in out, "bad --before rejected")

# --- fetch arXiv with LaTeXML HTML
code, out = run("fetch", "https://arxiv.org/abs/2401.00001v2", "--run", str(rd))
print(out)
ft = rd / "papers" / "_fulltext" / "2401.00001.txt"
text = ft.read_text(encoding="utf-8")
check(code == 0 and ft.exists(), "fetch saves full text")
check("Date: 2024-01-02" in text and "Access: full-text (arxiv-html)" in text, "header has v1 date and access")
check("Report issue" not in text and "Generated by LaTeXML" not in text and "var x" not in text, "page chrome skipped")
check("$O(\\log n)$ memory" in text and "width $w$." in text, "math kept as LaTeX alttext, no space before punctuation")
check("## 1 Introduction" in text and "### 3.1 Sketch Layer" in text and "###### Abstract" in text, "headings converted")
check("IMDB | 74M |" in text, "table rows kept")
check("static data distributions.\nUpdates require" in text, "<br> splits lines")
check("- ID: 2401.00001 | Date: 2024-01-02 | Venue: arXiv cs.DB | URL: https://arxiv.org/abs/2401.00001" in out, "digest header printed")
code, out = run("fetch", "2401.00001", "--run", str(rd))
check(code == 0 and out.startswith("Cached:"), "second fetch uses the cache")

# --- show
code, out = run("show", "2401.00001", "--run", str(rd), "--section", "3")
print(out)
check(code == 0 and "3 Method" in out and "3.2 Correction" in out and "4 Limitations" not in out, "--section 3 prints 3 incl. subsections")
code, out = run("show", "2401.00001", "--run", str(rd), "--section", "3.1")
check("Sketch Layer" in out and "Correction" not in out, "--section 3.1 stops at 3.2")
code, out = run("show", "2401.00001", "--run", str(rd), "--section", "related work")
check("Sampling based estimators" in out, "--section by title text")
code, out = run("show", "2401.00001", "--run", str(rd), "--grep", "sketch(es)? bias|rebuild", "--context", "1")
check(code == 0 and "*" in out and "Updates require rebuilding" in out, "--grep with context")
code, out = run("show", "2401.00001", "--run", str(rd), "--grep", "(unbalanced")
check(code == 0, "--grep falls back to a literal for an invalid regex")
code, out = run("show", "2401.00001", "--run", str(rd), "--lines", "1-1000")
check("truncated at 400 lines" in out or out.count("\n") <= 405, "--lines is capped")
code, out = run("show", "2401.00001", "--run", str(rd), "--section", "Nonexistent")
check(code == 5 and "Outline" in out, "unknown section shows the outline")

# --- fetch: post-cutoff refusal, v1 selection with PDF fallback
code, out = run("fetch", "2602.00003", "--run", str(rd))
check(code == 4 and "REFUSED" in out and not (rd / "papers/_fulltext/2602.00003.txt").exists(), "post-cutoff paper refused")
CALLS.clear()
code, out = run("fetch", "2512.00002", "--run", str(rd))
print(out)
t2 = (rd / "papers/_fulltext/2512.00002.txt").read_text(encoding="utf-8")
check(code == 0 and "https://arxiv.org/html/2512.00002v1" in CALLS and "https://arxiv.org/pdf/2512.00002v1" in CALLS
      and not any("ar5iv" in c for c in CALLS), "later versions after cutoff -> v1, ar5iv skipped")
if HAS_PDF:
    check("Access: full-text (pdf/" in t2 and "## 1 Introduction" in t2 and "## 2 Robust Planning" in t2
          and "## References" in t2 and "## Abstract" in t2, "PDF text extracted with headings")
else:
    check("Access: abstract-only" in t2 and "pip install pypdf" in out, "no PDF extractor -> abstract-only with a hint")
check("v1 is used" in t2, "v1 note recorded")

# --- fetch DOI: S2 says it has an arXiv version -> switch ID; DOI with OA PDF; Crossref fallback; OpenReview
code, out = run("fetch", "doi:10.1145/1111111", "--run", str(rd))
check(code == 0 and "cite it as [2401.00001]" in out and "Cached:" in out, "DOI with arXiv version switches to the arXiv ID")
code, out = run("fetch", "https://doi.org/10.14778/2222222", "--run", str(rd))
t3 = (rd / "papers/_fulltext/doi_10.14778_2222222.txt").read_text(encoding="utf-8")
check(code == 0 and ("Access: full-text (pdf/" in t3) == HAS_PDF and "Venue: VLDB" in t3 and "Grace Hopper" in t3, "DOI open-access PDF")
code, out = run("fetch", "doi:10.1145/3333333", "--run", str(rd))
t4 = (rd / "papers/_fulltext/doi_10.1145_3333333.txt").read_text(encoding="utf-8")
check(code == 0 and "Access: abstract-only" in t4 and "Date: 2024-03 " in t4 and "We do things." in t4
      and "abstract-only" in out, "S2 429 -> Crossref metadata, abstract-only")
code, out = run("fetch", "https://openreview.net/forum?id=AbCdEf123", "--run", str(rd))
t5 = (rd / "papers/_fulltext/openreview_AbCdEf123.txt").read_text(encoding="utf-8")
check(code == 0 and "Date: 2023-09-28" in t5 and "ICLR 2024 poster" in t5 and ("full-text (pdf/" in t5) == HAS_PDF, "OpenReview note + PDF")
code, out = run("fetch", "2401.99999", "--run", str(rd))
check(code == 5 and "NOT FOUND" in out, "unknown arXiv id -> not found")
code, out = run("show", "doi:10.1145/1111111", "--run", str(rd))
check(code == 5 and "arXiv version" in out, "show on the DOI points to the arXiv ID")

# --- network down
MODE["net_down"] = True
code, out = run("fetch", "2401.00002", "--run", str(rd))
check(code == 3 and "NETWORK ERROR" in out and "approve network access" in out, "network failure -> exit 3 with guidance")
code, out = run("ping")
check(code == 3 and "unreachable" in out, "ping reports unreachable")
MODE["net_down"] = False
code, out = run("ping")
check(code == 0 and "pypdf" in out, "ping ok")
code, out = run("fetch", "2401.00001", "--run", str(WORK / "missing"))
check(code == 2 and "run directory not found" in out, "missing run dir")

print(f"\n{check.failed} failures")
sys.exit(1 if check.failed else 0)
