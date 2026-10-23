"""Tests for codex/idea-scientist/scripts/check_run.py and render_report.py on constructed run directories.

Usage: python tests/test_check_render.py [WORK_DIR]
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "codex" / "idea-scientist"
WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="idea-scientist-test-"))
failed = 0


def check(cond, msg):
    global failed
    print(("PASS " if cond else "FAIL ") + msg)
    failed += 0 if cond else 1


def sh(script, *args):
    r = subprocess.run([sys.executable, "-I", str(SKILL / "scripts" / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


DIGEST = """# {title}
- ID: {pid} | Date: {date} | Venue: {venue} | URL: {url}
- Access: {access}
## What this paper does
它提出了一个方法。
## Goal-by-goal answers
### Goal: 它用什么机制处理连接基数估计？
用 sketch 加学习校正 [Sec 3]。
"""

GAPS = """## Axis: 连接基数估计误差
### What has been done
基于采样的方法 [2401.00001]，基于学习的方法 [doi:10.14778/2222222]。
### Open gaps on this axis
- **Gap:** 已有方法通过静态 sketch 估计连接大小，但 sketch 不随数据漂移更新。
- **Near-miss methods and coverage:** [2401.00001] — 学习校正；[doi:10.14778/2222222] — 计划图。
- **Methodological deficiency:** representation limitation：sketch 是静态的。
- **Why it matters:** 优化器在数据更新后选错计划。
- **Evidence route:** 在漂移负载上比较 q-error。
"""

CANDS = """### C1 — 漂移感知 sketch
- **Intuition:** 把流式算法里的衰减窗口用到基数 sketch 上。
- **Story:** 数据更新后静态 sketch 仍按旧分布估计，优化器因此选错连接顺序；根因是统计信息没有有效期；流式算法用衰减窗口让旧数据逐渐失效，用到 sketch 上就能跟上漂移。
- **Gap it attacks:** 连接基数估计误差 / 静态 sketch。
- **Source inspiration:** [2512.00002] 的鲁棒规划；新颖性类型 recombination-of-distant-concepts。
- **How it maps to this problem:** 窗口对应统计信息的有效期。
- **Why it could work / feasibility:** 漂移是渐进的。
- **Novelty vs. closest in-domain work:** [2401.00001] 不处理漂移。
- **Main risk:** 突变漂移下失效。
"""

SCORES = """### C1 verdict
- **Verdict:** survive
- **Evidence:**
  - [2401.00001] 没有处理漂移。
- **Story in 1 sentence:** 静态 sketch 跟不上漂移，因为统计没有有效期，所以给 sketch 加衰减窗口。
- **Strongest objection in 1 sentence:** 突变漂移。
"""

REPORT = {
    "title": "漂移感知的连接基数估计",
    "topic_relevance": {"sub_topic": ["查询优化"], "primary_focus": ["基数估计"]},
    "one_sentence_thesis": "让基数 sketch 随数据漂移衰减更新，从而在数据变化后仍能选对连接顺序。",
    "story": {"arc": "数据更新后，静态 sketch 仍按旧分布估计连接大小，优化器因此选错连接顺序 [2401.00001]。根因是统计信息没有有效期。"
                     "流式算法用衰减窗口让旧数据逐渐失效；把它用到 sketch 上，估计就能跟上漂移。",
              "headline_claim": "在渐进漂移的负载上消除静态 sketch 的估计滞后",
              "carrying_evidence": ["q-error 随时间变化的曲线：静态 sketch 逐步变差，衰减 sketch 保持平稳"]},
    "core_problem": {"problem_statement": "静态 sketch 在数据漂移后失准 [2401.00001]。",
                     "why_it_matters": ["已有研究报告约 30% 的查询计划因估计误差变慢 [doi:10.14778/2222222]。"],
                     "concrete_example": "插入新数据后，连接 A⋈B 的估计偏小 100 倍。"},
    "key_novelty": {"main_idea": "衰减窗口 sketch", "explanation": ["统计信息有有效期。"]},
    "problem_definition": {"formal_setting": "给定查询 Q 和数据库 D_t。", "inputs": "Q, D_t", "outputs": "|Q(D_t)| 的估计"},
    "key_terms": {"q-error": "估计值与真实值之比的最大值"},
    "related_work": [{"sub_area": "学习型估计", "what_it_does": "用模型校正 sketch [2401.00001]。",
                      "open_gap": "不处理漂移。", "citations": ["2401.00001", "doi:10.14778/2222222"]}],
    "method": {"high_level_flow": ["统计: 窗口 sketch -> 估计"], "modules": [{"module": "窗口 sketch", "role": "维护统计",
               "model": "count-min", "inputs": ["更新流"], "outputs": ["计数"], "notes": "宽度 w"}],
               "novel_architectural_elements": ["sketch | 校正 两层结构"], "pseudocode": "```\nfor t in stream: decay(); add(t)\n```",
               "design_choices": ["指数衰减，因为简单"], "theoretical_grounding": "误差界随窗口增大而减小。"},
    "model_details": {"base_model": "不训练大模型：只用一个小型 MLP 做校正", "training": {"method": "监督学习",
                      "objective_functions": ["Purpose: 降低 q-error。Formally: min log q"], "adaptation": "全量训练",
                      "key_hyperparameters": {"w": 2048}}},
    "comparison_to_sota": {"related_methods": ["Sketch+ML [2401.00001]: 学习校正"], "key_differences": ["vs. Sketch+ML [2401.00001]: 处理漂移"]},
    "proposed_evaluation": {"evaluation_setting": "JOB 负载加漂移", "benchmarks": [{"name": "JOB", "task_type": "estimation",
                            "newly_constructed": False}], "baselines": ["PostgreSQL"], "main_metrics": ["q-error 的 95% 分位数"],
                            "ablations": ["去掉衰减"]},
    "falsifiable_predictions": [{"pillar": "衰减", "prediction": "漂移后 q-error 低于静态 sketch",
                                 "promise_signal": "漂移最剧烈的查询上，q-error 比去掉衰减的版本低",
                                 "kill_condition": "窗口调好后，有无衰减对漂移后的 q-error 都没有影响"}],
    "pilot_guidance": {"minimal_pilot": "在 JOB 的一个子集上注入渐进漂移，比较衰减 sketch 和去掉衰减的版本",
                       "not_kill_reasons": ["窗口未调时，整体 q-error 仍高于 PostgreSQL"],
                       "iteration_budget": "两轮：先核对实现，再调窗口宽度",
                       "fallback_story": "只对渐进漂移有效时，讲成渐进漂移下的低成本修正"},
    "limitations": ["突变漂移下失效"],
}


def build(root, cutoff="2026-01-01", crlf=False, bom=False):
    shutil.rmtree(root, ignore_errors=True)
    (root / "papers" / "_fulltext").mkdir(parents=True)
    (root / "gaps").mkdir()

    def w(rel, text):
        if crlf:
            text = text.replace("\n", "\r\n")
        (root / rel).write_text(text, encoding="utf-8-sig" if bom else "utf-8", newline="")

    w("problem.md", f"Challenge: 基数估计在漂移下失准\nProblem definition: 估计连接大小\nCutoff（可选）：{cutoff}\n")
    w("gaps/01-cardinality.md", GAPS)
    w("candidates.md", CANDS)
    w("scores.md", SCORES)
    papers = [("2401.00001", "Learned Cardinality Estimation With Sketches", "2024-01-02", "arXiv cs.DB", "https://arxiv.org/abs/2401.00001"),
              ("doi:10.14778/2222222", "Robust Query Optimization via Plan Diagrams", "2023-05-02", "VLDB", "https://doi.org/10.14778/2222222"),
              ("2512.00002", "Robust Join Ordering Under Drift", "2025-12-30", "arXiv cs.DB", "https://arxiv.org/abs/2512.00002")]
    for pid, title, date, venue, url in papers:
        name = pid.replace(":", "_").replace("/", "_")
        w(f"papers/{name}.md", DIGEST.format(title=title, pid=pid, date=date, venue=venue, url=url, access="full-text"))
        w(f"papers/_fulltext/{name}.txt", f"# {title}\nID: {pid}\nDate: {date} (first public release)\n" + "-" * 40 + "\nbody\n")
    data = json.dumps(REPORT, ensure_ascii=False, indent=2)
    w("report.json", data)
    return root


# --- good run (plus CRLF + BOM variant, as Windows tools may write)
good = build(WORK / "good")
code, out = sh("check_run.py", good)
print(out)
check(code == 0 and "0 errors" in out, "good run passes")
check("percentage in" not in out or "core_problem.why_it_matters" in out, "percentage outside evaluation fields is warned")
check("why_it_matters[0] has a percentage" in out, "cited-fact percentage gets a WARN, not an ERROR")
check("proposed_evaluation" not in out, "percentages inside proposed_evaluation are allowed")
check("not better than SOTA" not in out, "mechanism-level kill condition is not flagged")
win = build(WORK / "win", crlf=True, bom=True)
code, out = sh("check_run.py", win)
check(code == 0, "CRLF line endings and UTF-8 BOM are accepted:\n" + out)
story = build(WORK / "story")
(story / "scores.md").write_text(SCORES.replace("survive", "revise(focus=story)"), encoding="utf-8")
code, out = sh("check_run.py", story)
check(code == 0 and "revise focus" not in out, "story is a valid revise dimension")

# --- bad run: every gate tripped once
bad = build(WORK / "bad")
r = dict(REPORT)
r["limitations"] = []
r["title"] = "TODO"
r["falsifiable_predictions"] = [{"pillar": "x", "prediction": "y", "kill_condition": "z"},
                                {"pillar": "x", "prediction": "y", "promise_signal": "p",
                                 "kill_condition": "预实验中 q-error 不优于 PostgreSQL 基线"}]
r["story"] = dict(REPORT["story"], headline_claim="")
r["pilot_guidance"] = "跑一下看看"
r["comparison_to_sota"] = {"related_methods": ["A [2405.00001]"], "key_differences": ["vs. B [2402.11111v2]"]}
r["related_work"] = [dict(REPORT["related_work"][0], citations=["Smith et al. 2023", "2401.00001"])]
(bad / "report.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
(bad / "gaps/01-cardinality.md").write_text(GAPS.replace("- **Evidence route:** 在漂移负载上比较 q-error。\n", "")
                                            + "- **Gap:** 二\n- **Gap:** 三\n", encoding="utf-8")
(bad / "candidates.md").write_text("".join(line for line in CANDS.splitlines(keepends=True)
                                           if not line.startswith(("- **Story:**", "- **Main risk:**"))),
                                   encoding="utf-8")
(bad / "scores.md").write_text(SCORES.replace("survive", "revise(focus=vibes)") + "\n- [2409.00009] 仅题录\n", encoding="utf-8")
(bad / "papers/2512.00002.md").write_text("# T\n- ID: 2512.00002 | Date: 2025-12-30 | Venue: arXiv | URL: u\n- Access: abstract-only\n", encoding="utf-8")
(bad / "papers/2601.00001.md").write_text(DIGEST.format(title="Late", pid="2601.00001", date="2025-12-01", venue="arXiv",
                                                        url="u", access="full-text"), encoding="utf-8")
(bad / "papers/_fulltext/2601.00001.txt").write_text("# Late\nID: 2601.00001\nDate: 2026-01-15 (first public release)\n", encoding="utf-8")
code, out = sh("check_run.py", bad)
print(out)
expect = {
    "field 'limitations' is missing or empty": "empty required field",
    "title contains a placeholder": "TODO placeholder",
    "falsifiable_predictions[0] needs 'prediction', 'promise_signal' and 'kill_condition'": "prediction without promise signal",
    "falsifiable_predictions[1].kill_condition reads like 'not better than SOTA": "SOTA-style kill condition is warned",
    "story.headline_claim is missing or empty": "story sub-field",
    "'pilot_guidance' must be an object": "pilot guidance shape",
    "drop the version suffix in [2402.11111v2]": "versioned arXiv id",
    "non-ID entry 'Smith et al. 2023'": "non-ID citation entry",
    "[2405.00001] is cited in report.json:comparison_to_sota.related_methods[0] but was never read": "unread citation",
    "3 gaps; at most 2 per axis": "laundry-list gaps",
    "gap 1 is missing Evidence route": "gap schema",
    "candidates.md C1: missing Story, Main risk": "candidate schema",
    "papers/2512.00002.md answers no '### Goal:'": "digest without answered goals",
    "[2512.00002] is abstract-only": "abstract-only warning",
    "Date 2025-12-01 differs from the fetched record 2026-01-15": "digest date vs fetched date",
    "papers/2601.00001.md: first released 2026-01-15, on or after the cutoff 2026-01-01": "cutoff violation uses fetched date",
    "revise focus 'vibes'": "unknown revise dimension",
    "no candidate has a 'survive' verdict": "no survive",
    "[2409.00009] is cited in scores.md but was never read": "reviewer citation warning",
}
for needle, what in expect.items():
    check(needle in out, what)
check(code == 1, "bad run exits 1")

broken = build(WORK / "broken")
(broken / "report.json").write_text('{"a": 1}{"b": 2}', encoding="utf-8")
code, out = sh("check_run.py", broken)
check(code == 1 and "does not parse as exactly one JSON object" in out, "two JSON objects rejected")

# --- render
code, out = sh("render_report.py", good)
md = (good / "report.md").read_text(encoding="utf-8")
print(md[:1800])
check(code == 0, "render exits 0")
check("[[2401.00001]](https://arxiv.org/abs/2401.00001)" in md, "arXiv citation linked")
check("[[doi:10.14778/2222222]](https://doi.org/10.14778/2222222)" in md, "DOI citation linked")
check("## 参考文献" in md and "- [2401.00001] Learned Cardinality Estimation With Sketches (arXiv cs.DB, 2024-01-02)" in md, "reference list from digests")
check("| 衰减 | 漂移后 q-error 低于静态 sketch | 漂移最剧烈的查询上，q-error 比去掉衰减的版本低 "
      "| 窗口调好后，有无衰减对漂移后的 q-error 都没有影响 |" in md, "predictions table")
check("## 故事线" in md and md.index("## 故事线") < md.index("## 核心问题")
      and "**核心主张**: 在渐进漂移的负载上消除静态 sketch 的估计滞后" in md, "story comes first")
check("## 预实验判读" in md and "- 窗口未调时，整体 q-error 仍高于 PostgreSQL" in md, "pilot guidance")
check(md.count("```") == 2 and "for t in stream" in md, "pseudocode fences normalized")
code, out = sh("render_report.py", good, "--lang", "en", "--out", WORK / "report_en.md")
en = (WORK / "report_en.md").read_text(encoding="utf-8")
check(code == 0 and "## References" in en and "## Falsifiable predictions" in en
      and "## Story" in en and "## Pilot guidance" in en, "English labels")

print(f"\n{failed} failures")
sys.exit(1 if failed else 0)
