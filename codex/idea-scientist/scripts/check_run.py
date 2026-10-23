#!/usr/bin/env python3
"""Final checks for an idea-scientist run directory.

Covers the hard gates of the original IdeaScientist reward (valid JSON, every field filled, every cited
paper actually read, no paper on or after the cutoff) plus the schemas of gaps/, candidates.md and scores.md,
and the story-first fields (story, pilot_guidance, a promise signal for every prediction).

Usage: python check_run.py RUN_DIR        (exit code 1 when any ERROR is found)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ID = (r"(?:\d{4}\.\d{4,5}|[a-z][a-z\-]*(?:\.[A-Za-z]{2})?/\d{7}"
      r"|doi:[^\[\]\s]+|openreview:[^\[\]\s]+|s2:[^\[\]\s]+)")
CITE = re.compile(r"\[(" + ID + r")\]")
VERSIONED = re.compile(r"\[(\d{4}\.\d{4,5}v\d+)\]")
REQUIRED = ["title", "topic_relevance", "one_sentence_thesis", "story", "core_problem", "key_novelty",
            "problem_definition", "key_terms", "related_work", "method", "model_details",
            "comparison_to_sota", "proposed_evaluation", "falsifiable_predictions", "pilot_guidance", "limitations"]
SUBFIELDS = {"story": ["arc", "headline_claim", "carrying_evidence"],
             "pilot_guidance": ["minimal_pilot", "not_kill_reasons", "iteration_budget", "fallback_story"]}
PRED_FIELDS = ("prediction", "promise_signal", "kill_condition")
GAP_FIELDS = ["Near-miss methods and coverage", "Methodological deficiency", "Why it matters", "Evidence route"]
CAND_FIELDS = ["Intuition", "Story", "Gap it attacks", "Source inspiration", "How it maps to this problem",
               "Why it could work / feasibility", "Novelty vs. closest in-domain work", "Main risk"]
REVISE_DIMS = {"novelty", "coherence", "feasibility", "clarity", "mapping", "grounding", "story"}
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b|待补|待定|<(?:proposal title|term|plain-language definition|"
                         r"Method|specific difference|notation|plain language)>")
NUMBERS_OK = ("proposed_evaluation", "falsifiable_predictions", "pilot_guidance", "model_details", "method")
# a kill condition that only says "not better than SOTA / the baselines": a pilot that trails SOTA is not a kill
SOTA_KILL = re.compile(r"(?=.*(?:SOTA|state.of.the.art|baseline|基线|已有方法|现有方法|最强方法))"
                       r"(?=.*(?:(?:not|n't) (?:better|beat|outperform|exceed|surpass|improve)"
                       r"|fails? to (?:beat|outperform|exceed|surpass|improve)|no (?:better|gain|improvement)"
                       r"|worse than|underperform|lags? behind|falls? short|不优于|不如|不超过|未超过|没有?超过"
                       r"|未能超越|持平|落后|差于|劣于|没有提升|无提升))", re.I | re.S)
GOAL = re.compile(r"^\s*###\s*Goal\s*:", re.M | re.I)


def read(path):
    return path.read_text(encoding="utf-8-sig")


def safe_name(pid):
    return re.sub(r'[/:<>"\\|?*\s]', "_", pid)


def label(name):
    return re.compile(r"\*\*\s*" + r"\s*".join(map(re.escape, name.split())) + r"\s*:?\s*\*\*", re.I)


def strings(x, path=""):
    if isinstance(x, str):
        yield path, x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from strings(v, f"{path}[{i}]")


def date_status(date, before):
    d = date[:10]
    lo, hi = {4: (d + "-01-01", d + "-12-31"), 7: (d + "-01", d + "-31")}.get(len(d), (d, d))
    return "ok" if hi < before else "post" if lo >= before else "?"


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2
    run = Path(argv[1])
    errors, warns = [], []
    err, warn = errors.append, warns.append

    # 1) report.json is exactly one JSON object with every required field filled
    try:
        report = json.loads(read(run / "report.json"))
        if not isinstance(report, dict):
            raise ValueError("the top level is not an object")
    except Exception as e:
        print(f"ERROR report.json is missing or does not parse as exactly one JSON object: {e}")
        return 1
    for key in REQUIRED:
        if report.get(key) in (None, "", [], {}):
            err(f"report.json: field '{key}' is missing or empty")
    for key, subs in SUBFIELDS.items():
        value = report.get(key)
        if value in (None, "", [], {}):
            continue
        if not isinstance(value, dict):
            err(f"report.json: '{key}' must be an object with {', '.join(subs)}")
            continue
        for sub in subs:
            if value.get(sub) in (None, "", [], {}):
                err(f"report.json: {key}.{sub} is missing or empty")
    preds = report.get("falsifiable_predictions")
    if isinstance(preds, list):
        for i, p in enumerate(preds):
            if not (isinstance(p, dict) and all(str(p.get(k) or "").strip() for k in PRED_FIELDS)):
                err(f"report.json: falsifiable_predictions[{i}] needs 'prediction', 'promise_signal' and "
                    "'kill_condition'")
            elif SOTA_KILL.match(str(p["kill_condition"])):
                warn(f"report.json: falsifiable_predictions[{i}].kill_condition reads like 'not better than SOTA / "
                     "baselines': fine only once the iteration budget is spent on the targeted failure; a pilot "
                     "that trails SOTA is not a kill, so tie it to the mechanism or the story")
    thesis = str(report.get("one_sentence_thesis") or "")
    if len(re.findall(r"[A-Za-z0-9][\w'\-]*", thesis)) > 30 or len(re.findall(r"[\u4e00-\u9fff]", thesis)) > 60:
        warn("report.json: one_sentence_thesis is longer than 30 words")
    for path, s in strings(report):
        if PLACEHOLDER.search(s):
            err(f"report.json:{path} contains a placeholder (TODO / template text)")
        if not path.startswith(NUMBERS_OK) and re.search(r"\d+(?:\.\d+)?\s?%", s):
            warn(f"report.json:{path} has a percentage: fine if it is a cited fact, not if it is a result of "
                 "the proposed method")

    # 2) upstream artifacts follow their schemas
    gap_files = sorted((run / "gaps").glob("*.md")) if (run / "gaps").is_dir() else []
    if not gap_files:
        err("gaps/ has no gap files")
    for f in gap_files:
        text = read(f)
        n_axis = len(re.findall(r"^\s*##\s*Axis\s*:", text, re.M | re.I))
        if n_axis != 1:
            err(f"gaps/{f.name}: expected exactly one '## Axis:' header, found {n_axis}")
        for head in ("What has been done", "Open gaps on this axis"):
            if not re.search(r"^\s*###\s*" + re.escape(head), text, re.M | re.I):
                warn(f"gaps/{f.name}: missing '### {head}'")
        blocks = re.split(r"^\s*[-*]\s*\*\*\s*Gap\s*:?\s*\*\*", text, flags=re.M | re.I)[1:]
        if len(blocks) > 2:
            err(f"gaps/{f.name}: {len(blocks)} gaps; at most 2 per axis")
        for k, block in enumerate(blocks, 1):
            missing = [n for n in GAP_FIELDS if not label(n).search(block)]
            if missing:
                err(f"gaps/{f.name}: gap {k} is missing {', '.join(missing)}")
    cand = run / "candidates.md"
    if not cand.exists():
        err("candidates.md not found")
    else:
        parts = re.split(r"^\s*###\s*(C\d+)\b", read(cand), flags=re.M)
        if len(parts) < 3:
            err("candidates.md has no '### C<n> — <title>' section")
        for name, body in zip(parts[1::2], parts[2::2]):
            missing = [n for n in CAND_FIELDS if not label(n).search(body)]
            if missing:
                err(f"candidates.md {name}: missing {', '.join(missing)}")
    scores = run / "scores.md"
    verdicts = []
    if not scores.exists():
        warn("scores.md not found: the proposal was never reviewed")
    else:
        parts = re.split(r"^\s*###\s*(C\d+)\s+verdict", read(scores), flags=re.M | re.I)
        for name, body in zip(parts[1::2], parts[2::2]):
            m = re.search(r"\*\*\s*Verdict\s*:?\s*\*\*\s*:?\s*`?\s*(survive|revise\s*\(\s*focus\s*=\s*(\w+)\s*\)"
                          r"|reject\s*\(.*?\))", body, re.I)
            if not m:
                warn(f"scores.md {name}: verdict is not survive / revise(focus=<dim>) / reject(reason=...)")
                continue
            verdicts.append(m.group(1).lower())
            if m.group(2) and m.group(2).lower() not in REVISE_DIMS:
                warn(f"scores.md {name}: revise focus '{m.group(2)}' is not one of {', '.join(sorted(REVISE_DIMS))}")
        if not any(v.startswith("survive") for v in verdicts):
            warn("no candidate has a 'survive' verdict: say so when delivering")

    # 3) every cited id was read: a digest exists and answers at least one goal
    strict, soft = {}, {}
    for path, s in strings(report):
        for m in CITE.findall(s):
            strict.setdefault(m, f"report.json:{path}")
        for m in VERSIONED.findall(s):
            err(f"report.json:{path}: drop the version suffix in [{m}]")
    related = report.get("related_work")
    for i, rw in enumerate(related if isinstance(related, list) else []):
        cites = rw.get("citations") if isinstance(rw, dict) else None
        if not cites:
            warn(f"report.json: related_work[{i}] has no citations")
            continue
        for c in cites:
            c = str(c).strip().strip("[]")
            if re.fullmatch(ID, c):
                strict.setdefault(c, f"report.json:related_work[{i}].citations")
            else:
                err(f"report.json: related_work[{i}].citations has a non-ID entry {c!r}")
    for f in gap_files + [cand]:
        if f.exists():
            for m in CITE.findall(read(f)):
                strict.setdefault(m, f.relative_to(run).as_posix())
    if scores.exists():
        for m in CITE.findall(read(scores)):
            soft.setdefault(m, "scores.md")
    pdir = run / "papers"
    digests = {f.name.lower(): f for f in pdir.glob("*.md")} if pdir.is_dir() else {}

    def digest(pid):
        return digests.get(safe_name(pid).lower() + ".md")

    for pid, where in sorted(strict.items()):
        f = digest(pid)
        if f is None:
            err(f"[{pid}] is cited in {where} but was never read (no papers/{safe_name(pid)}.md)")
            continue
        text = read(f)
        if not GOAL.search(text):
            err(f"papers/{f.name} answers no '### Goal:', so [{pid}] does not count as read ({where})")
        if re.search(r"Access:\s*abstract-only", text, re.I):
            warn(f"[{pid}] is abstract-only: it must not carry a mechanism-level claim ({where})")
    for pid in sorted(soft):
        if pid not in strict and digest(pid) is None:
            warn(f"[{pid}] is cited in scores.md but was never read")

    # 4) with a cutoff, nothing read may be first released on or after it
    prob = run / "problem.md"
    cutoff = None
    if prob.exists():
        m = re.search(r"Cutoff[^:：\n]*[:：]\s*(\d{4}-\d{2}-\d{2})", read(prob))
        cutoff = m.group(1) if m else None
    else:
        warn("problem.md not found")
    if cutoff:
        for f in sorted(digests.values()):
            m = re.search(r"Date:\s*(\d{4}(?:-\d{2}){0,2})", read(f))
            date = m.group(1) if m else None
            fetched = pdir / "_fulltext" / (f.stem + ".txt")
            if fetched.exists():
                m2 = re.search(r"^Date:\s*(\d{4}(?:-\d{2}){0,2})", read(fetched), re.M)
                if m2:
                    if date and date != m2.group(1):
                        warn(f"papers/{f.name}: Date {date} differs from the fetched record {m2.group(1)}; "
                             "the fetched date is used")
                    date = m2.group(1)
            if not date:
                warn(f"papers/{f.name}: no Date, so the cutoff cannot be checked")
                continue
            status = date_status(date, cutoff)
            if status == "post":
                err(f"papers/{f.name}: first released {date}, on or after the cutoff {cutoff}")
            elif status == "?":
                warn(f"papers/{f.name}: date {date} is too coarse to compare with the cutoff {cutoff}")

    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    print(f"{len(strict)} cited ids checked: {len(errors)} errors, {len(warns)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
