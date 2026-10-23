# 读论文协议（所有角色通用）

下文中，PY 是 Python 命令（Windows 上通常是 `python` 或 `py -3`，macOS/Linux 上是 `python3`），SKILL_DIR 是 idea-scientist 这个 Skill 的目录，RUN 是本轮运行目录的绝对路径。这三项都写在你收到的任务消息里。

## 论文 ID 与引用格式

- 有 arXiv 版本的用 arXiv 号，不带版本号：`2401.12345`。没有的用 `doi:10.xxxx/yyyy`；OpenReview 论文没有 DOI 时用 `openreview:<forum id>`；这三种都没有时，用检索脚本给出的 `s2:<id>`。
- 正文中一律用方括号引用，一个括号放一个 ID：`[2401.12345]`；多个就连写：`[2401.12345][doi:10.1145/3639322]`。不要用标题缩写、作者-年份、链接或圆括号。
- 摘要文件名：把 ID 里的 `/ : < > " \ | ? *` 和空白都换成 `_`，再加 `.md`，例如 `papers/2401.12345.md`、`papers/doi_10.1145_3639322.md`。`paper.py fetch` 会直接打印这个文件名。

## 检索

- 首选脚本：`PY SKILL_DIR/scripts/paper.py search "<查询>" --run RUN [--limit 10] [--abstracts]`。它同时查 arXiv 和 Semantic Scholar，按 ID 去重，每行输出 ID、首次公开日期、venue 和标题。带 `--run` 时会自动读取 problem.md 中的 Cutoff，过滤掉截止日期当天及之后的论文。标 `date?` 的条目日期不精确，读之前先用 fetch 确认。
- 补充：用 web_search 找脚本覆盖不到的论文（不在 arXiv、Semantic Scholar 收录不全）或最新工作。用 web_search 时，设了 Cutoff 就自己核对日期。
- 查询要短而具体（2-6 个词），用该领域的准确术语。不要用连字符（Semantic Scholar 不匹配带连字符的词）。结果少就换说法重搜。
- 先看标题挑候选，拿不准时再加 `--abstracts`，不要每次都加。
- 脚本报网络错误（退出码 3）时，按 Codex 的审批流程申请联网运行；仍不行就改用 web_search。

## 读论文

1. **获取全文**：`PY SKILL_DIR/scripts/paper.py fetch <id> --run RUN`。全文会存到 `RUN/papers/_fulltext/<文件名>.txt`（已存在就直接用缓存）。脚本会打印标题、首次公开日期、venue、获取方式（Access）、摘要文件应写的头部两行，以及带行号的章节目录。
   - 输出说这篇论文有 arXiv 版本时，改用它给出的 arXiv ID。
   - 设了 Cutoff 而论文在截止日期当天或之后首次公开，脚本会拒绝保存（退出码 4）：这篇论文不能读，也不能引用。
   - 后续版本晚于 Cutoff 时，脚本自动读 v1。
2. **按阅读目标只读需要的部分**，不要整篇打印：
   - `PY SKILL_DIR/scripts/paper.py show <id> --run RUN --section "3"`：按章节号或标题文字（如 "Related Work"）读一节
   - `PY SKILL_DIR/scripts/paper.py show <id> --run RUN --grep "<正则>" --context 3`：定位关键词
   - `PY SKILL_DIR/scripts/paper.py show <id> --run RUN --lines 120-200`：按行号读
   每次最多输出 400 行。
3. **脚本不可用时**（没有 Python、没有网络或抓取失败），用 web_search 打开论文页面来读（arXiv 的 abs 页上有 HTML 全文和 PDF 的链接）。只能拿到摘要时，摘要文件里写 `Access: abstract-only`。
4. 几篇论文互不依赖时，可以连续 fetch，再分别 show，不必读完一篇再找下一篇。

## “读过”的定义

- 搜索结果、标题、摘要都不算读过。读论文 = 带着 1-5 个具体的阅读目标，读了正文中与目标相关的部分并作答。阅读目标是具体的问题，例如“它用什么机制处理 <维度>？”“它自己承认在 <维度> 上有什么局限？”“哪个方法假设使它处理不了 <维度>？”
- `Access: abstract-only` 的论文不能支撑机制层面的论断，near-miss、来源机制、新颖性对比都不行。
- **只能引用本轮已有摘要文件、且摘要文件至少回答了一个阅读目标的论文。**不要编造 ID，也不要引用摘要文件不支持的论断。

## 摘要文件（追加式，跨调用累积）

先看 `RUN/papers/<文件名>.md` 是否存在。已经回答过的目标直接复用，不重读；只为新目标读正文，并把答案追加到文件末尾，不覆盖已有内容。新文件的格式如下，头部两行直接复制 fetch 打印的内容：

```
# <标题>
- ID: <id> | Date: <首次公开日期> | Venue: <venue> | URL: <链接>
- Access: full-text
## What this paper does
（一段，≤120 词）
## Goal-by-goal answers
### Goal: <原样复述的问题>
（≤300 词；具体内容标出处，如 [Sec 3.2 / Eq 5]；正文回答不了就直说）
```

只写阅读目标问到的内容。字段名和小节标题保持英文（校验脚本按它们检查），内容可以用用户的语言。单个角色任务通常读 4-10 篇，软上限 20 篇。

## Windows 提示

PowerShell 里读写这些文件时显式用 UTF-8：读用 `Get-Content -Encoding UTF8`，改文件优先用 apply_patch。命令输出里中文乱码时，先执行 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`。
