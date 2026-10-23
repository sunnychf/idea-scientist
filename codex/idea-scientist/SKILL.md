---
name: idea-scientist
description: 为一个研究问题生成有文献依据的科研 idea 和完整研究提案：找方法缺口、跨领域迁移机制、对抗式评审、写出结构化提案（改编自 IdeaScientist）。Use when asked to brainstorm, find innovation points for, or develop a grounded research idea or proposal; not for summarizing one paper or writing a survey.
---

# IdeaScientist：有文献依据的科研构思（Codex 版）

本 Skill 把 IdeaScientist（github.com/jiarui-liu/IdeaScientist，CC BY-NC 4.0，仅限非商业使用）的多角色构思流程改写成 Codex 能直接运行的版本。原系统在离线论文库 Svalbard Idea Vault 上检索，并用强化学习分别训练各个角色；这里改用 arXiv 和 Semantic Scholar 的公开接口（`scripts/paper.py`）加 Codex 的 web_search。没有训练出的权重，但保留了原系统的分工、文件接口、证据规则和评审标准。

**目标**：针对一个研究问题，产出**一个**聚焦、可落地、能讲成好故事、经得住对抗式评审的**方法学** idea，再扩写成一份不含编造结果的完整研究提案。不是 idea 清单，也不是五个组件拼成的大系统。

```
problem.md → gap_finder（每个挑战维度一次）→ gaps/ → innovator → candidates.md → reviewer → scores.md
                     ↑                          ↑                                    │
                     └──── reject：换缺口 ───────┴──── revise：带反馈改进 ─────────────┘
survive → report_writer → report.json → 校验（§6）→ report.md 交付（§8）
```

调度者（orchestrator）只做决策、维护 plan.md，自己不检索、不读论文；所有文献知识都通过各角色写出的文件传递。

**故事优先，结果看前景**：idea 值不值得做，先看它能不能讲成一篇好论文的故事：具体的失败 → 现有方法失败的根因 → 洞见 → 方法从洞见自然推出。很多顶会论文的方法一开始并没有超过 SOTA；拿一次没调参的小规模预实验和调好的基线比，没超过就放弃，会误杀好 idea。所以评审不因“不确定能否超过 SOTA”而否决 idea；提案在看到任何结果之前写好故事线和预实验的判读方法：什么算有前景、什么才算真正证伪、下判断前给多少迭代预算。本流程不跑实验，这部分（report.json 的 `story`、`pilot_guidance` 和每条预测的 `promise_signal`）供研究者或下游的 autoresearch 工具判读预实验。

**约定**：SKILL_DIR 是本文件所在的文件夹；RUN 是本轮运行目录的绝对路径；PY 是 §0 确定的 Python 命令。`references/` 里是读论文协议和各角色的完整说明；`scripts/` 里有 `paper.py`（检索、获取全文、按需阅读）、`check_run.py`（收尾校验）和 `render_report.py`（渲染报告）。

## 0. 环境检查（开始时做一次）

1. **Python**：依次试 `python --version`、`py -3 --version`、`python3 --version`，第一个能用的（3.8 及以上）就是 PY。都不能用时，检索和读论文改用 web_search，§6 的校验按清单人工完成。
2. **联网**：运行 `PY SKILL_DIR/scripts/paper.py ping`。脚本要访问 arXiv 和 Semantic Scholar，而 Codex 沙箱默认不让命令联网。被拦截时，按 Codex 的审批流程申请联网运行这条命令；审批界面如果提供“以后都允许这类命令”的选项，建议用户选它，免得子智能体反复请求。用户也可以在 `~/.codex/config.toml` 的 `[sandbox_workspace_write]` 段设置 `network_access = true`。实在联不了网就只用 web_search，并在交付时说明。
3. **web_search**：Codex 默认的 `cached` 模式可能查不到最新论文。没设 Cutoff 时，新颖性核查需要最新文献，可以提醒用户在 `~/.codex/config.toml` 顶部（任何 `[段]` 之前）加一行 `web_search = "live"`，然后重启 Codex。只提醒一次，不要因此停下。
4. **PDF**：ping 会报告是否装了 pypdf。没装时，只有 PDF 的论文会退化成 abstract-only，可以建议用户 `pip install pypdf`。
5. **Windows**：PowerShell 里读写本流程的文件时显式用 UTF-8：读用 `Get-Content -Encoding UTF8`，改文件优先用 apply_patch。命令输出里中文乱码时，先执行 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`。

## 1. 明确问题

整轮工作都建立在问题表述上，所以先把它定下来，写入 problem.md：

```
Challenge: 现有方法在哪里失效、为什么难（尽量具体，最好带一个失败例子）
Problem definition: 形式化设定、输入、输出
Constraints（可选）: 算力、必须用的系统或数据集、目标会议等
Cutoff（可选）: YYYY-MM-DD
```

- 设了 Cutoff，就只使用该日期之前首次公开的论文。这是原论文的“盲测”设置，用来检验 idea 能否预见之后的工作。`paper.py` 会自动读取这一行并过滤。
- 不设 Cutoff，就使用全部文献，而且新颖性核查必须覆盖最新的论文。
- 用户只给了一个主题或一句话时，先替他起草 Challenge 和 Problem definition，给用户确认一次再开始；用户没有回应就按草稿继续，并在交付时说明。

## 2. 运行目录与文件所有权

在当前工作区新建 `idea_runs/<YYYYMMDD>_<短标题>/`，这就是 RUN：

| 文件 | 写入者 | 内容 |
|---|---|---|
| problem.md | 启动时写入，之后只读 | 问题表述 |
| plan.md | orchestrator | 目标、当前方向、状态、历史 |
| papers/_fulltext/<id>.txt | paper.py fetch | 下载的全文（缓存） |
| papers/<id>.md | 读论文的角色（追加式） | 单篇论文的逐目标摘要 |
| gaps/NN-<axis-slug>.md | gap_finder（每个维度一个文件） | 已有工作与开放缺口 |
| candidates.md | innovator（追加式） | 候选 idea C1、C2…… |
| scores.md | reviewer（追加式） | 每个候选的评审结论 |
| report.json | report_writer | 结构化提案 |
| report.md | render_report.py | 给人读的提案 |

规则：每个文件只由它的所有者写；追加式文件只追加、不覆盖，追加前先读最新内容。某个文件有问题时，orchestrator 不自己改，而是带着反馈重新派发它的所有者。

## 3. 执行模式

**A. 子智能体模式（默认）**

Codex 默认开启子智能体。主线程扮演 orchestrator；每调用一次角色，就派生（spawn）一个新的子智能体，任务消息用下面的模板，把尖括号部分换成实际内容：

```
你是 idea-scientist 流程中的 <角色名> 角色，只负责这一个角色：不要运行 idea-scientist 的完整流程，也不要再派生子智能体。
先完整阅读并严格遵循这三个文件：
- <SKILL_DIR>/references/paper-protocol.md
- <SKILL_DIR>/references/idea-constraints.md
- <SKILL_DIR>/references/<角色名>.md
运行目录 RUN：<RUN 的绝对路径>（先读其中的 problem.md）
Python 命令 PY：<PY>；脚本目录：<SKILL_DIR>/scripts
任务：
<该角色的任务字段，见 §4 任务契约>
完成后只回复一行状态。
```

- 等子智能体完成后，去读它写出的文件；不要看它读过的论文原文，也不要看搜索结果。用完就关闭它。
- 不同维度的 gap_finder 可以同时派生（各写各的文件）；innovator 和 reviewer 一次只派一个，保持深度优先。
- 子智能体继承当前会话的沙箱和审批设置，联网审批可能出现在子智能体的线程里，需要用户到那里批准。
- 子智能体会多消耗 token。用户要求节省时，改用 B 模式。

**B. 单智能体模式（没有子智能体功能，或用户要求时）**

- 你依次扮演各个角色。每次切换角色时，先读 `references/` 下该角色的文件，并明确标出当前角色。`references/idea-constraints.md` 对所有角色都适用，开始时读一次。
- 每个角色开始前，只重新读取该角色允许读的文件。角色之间只通过文件交接，不要把上一个角色没写进文件的想法带到下一个角色。
- 到 reviewer 时真正切换成怀疑者：主动去找推翻新颖性的论文，而不是为自己刚写的 idea 辩护。

## 4. Orchestrator（调度者，主线程）

你是 PI：决定下一步研究什么、何时深挖、何时转向、何时定稿。你不检索、不读论文，只派发角色、读它们写出的文件、维护 plan.md。想查点什么时，说明该派一个角色去查了。

**目标**：一个聚焦、尖锐、有依据的方法学 intuition。它要 (a) 针对一个真实的缺口；(b) 有清楚且读过原文的来源机制，跨领域优先，领域内也可以，但迁移不能只是重新发现最接近的已有工作；(c) 说清楚来源机制如何映射到本问题；(d) 点名关键的迁移风险；(e) 能讲成一个好故事，主张不依赖在所有基准上超过 SOTA；(f) 通过对抗式评审。

**任务契约**：每次派发的任务就是下列字段，不多不少。子智能体会自己读 problem.md，不要在任务里重述问题。
- gap_finder：`AXIS: <一个挑战维度，用问题本身的准确术语写成的短语>`；`OUTPUT: gaps/NN-<slug>.md`。一个任务只给一个维度；问题涉及几个维度，就按维度分别派发，不要凑数。
- innovator：`TARGET: C<n>`（由你编号）；`GAP: <维度> / <gaps 文件中的那条缺口>`；可选 `BUILD_ON: C<x>; FOCUS: <评审指出的薄弱维度>`。不要替它给出 intuition 或机制，也不要替它决定新做还是改进。
- reviewer：`TARGET: C<n>`。
- report_writer：`TARGET: C<n>`。
- 重新派发去修正时，可以加 `FEEDBACK: <要补充或修正什么>`。

**常规路径**
1. 摸清全貌：在 plan.md 写下目标和候选挑战维度。先对最核心的维度派 gap_finder，读它写的 Open gaps；需要时再派其他维度。保持深度优先，不必把所有维度摸完才定方向。
2. 选方向：从 gaps 文件里挑一个最值得攻的缺口，写进 plan.md 作为当前方向，状态 `forming`。机制由 innovator 去找，你只选缺口。
3. 构思：派一次 innovator，指定这个缺口，它写出一个 C<n>。在 plan.md 记一条来源说明（基于什么、为什么这样走）。状态 `drilling`。
4. 对抗评审：派 reviewer 审这个 C<n>。状态 `under_review`。
5. 按结论行动：
   - `survive` → 状态 `survived`，进入第 6 步。
   - `revise(focus=<dim>)` → 再派 innovator：同一缺口，加 `BUILD_ON: C<n>; FOCUS: <dim>`，得到新的 C<m> 后再评审。修改 2-3 轮仍未 survive，按 reject 处理。
   - `reject(reason=…)` → 方向作废，状态 `dead`，回到第 2 步换一个缺口；需要更多全貌时先对新维度派 gap_finder。不要硬救。
6. 定稿：对 survive 的候选派 report_writer。
7. 完成：plan.md 标为完成，进入 §6 校验和 §8 交付。

**这是一张图，不是一条线。**每一步都根据文件的当前状态重新决定，可以重复、回退或跳跃。例如：gaps 写得单薄，就再派 gap_finder；innovator 找不到可填的缺口，就回去补全貌；report_writer 发现某个承重的来源机制落不了地、映射不清或迁移假设不成立，就退回 innovator；写作暴露出相关工作覆盖太薄、撑不起新颖性，就再派 gap_finder；某个角色出错或跑偏，就带着更明确的任务重试。唯一不变的规则：没有 `survive` 的候选，不派 report_writer；除非你明确决定冒险定稿，并在 plan.md 和交付时说明。

**plan.md 状态机**：始终显示当前方向及其状态（`forming` / `drilling` / `under_review` / `survived` / `dead`）。状态每变一次就更新，并在下方追加一行历史。

```
# Plan
Goal: <一句话目标>
Axes: 1) <维度> — explored (gaps/01-…)   2) <维度> — not yet
## Active direction
Gap: <维度> / <缺口>
Candidate: C<n>
Status: drilling
## History
- `forming` at step 1: picked <缺口> because …
- `drilling` at step 2: innovator → C1 (new)
```

**硬规则**
- 深度优先：选定一个缺口后，先把“构思 → 评审”走完再考虑别的。不要同时派 5 个 innovator 赌一个赢。
- 子任务要窄：“调研维度 Z”“针对缺口 G 产出一个 intuition”“评审 C7”。任务里出现“另外也考虑一下……”，就拆成几个任务。
- 跨领域的创造性交给 innovator。你的工作是选缺口，并靠 reviewer 保持诚实，不是自己发明机制。
- 只接受方法学贡献：新的方法、技术、算法、模型或系统。基准、数据集、分析、立场文章、综述都不行；审计类、保真类 idea 也不做（定义见 references/idea-constraints.md），选缺口时跳过补法只能落在这两类的缺口。
- 故事优先：reject 只留给不做的类型（不是方法学贡献，或属于审计类、保真类）和让故事讲不成立的根本问题（缺口不真实、已被做过、核心假设与文献矛盾）。reviewer 以“效果不确定”“未必超过 SOTA”为由 reject 时，带上 `FEEDBACK` 让它按故事核查重审。
- 一切以文件为准。角色交回的内容单薄或缺引用时，带着更明确的要求重新派发，不要用自己的猜测去补。
- 没有固定次数。默认上限供参考：挑战维度 ≤4 个；每个缺口修改 ≤3 轮；连续 3 个方向被 reject，就停下来向用户汇报已有发现，问是否继续。

## 5. 角色文件

| 角色 | 说明文件 | 产出 |
|---|---|---|
| gap_finder | references/gap_finder.md | gaps/NN-<slug>.md |
| innovator | references/innovator.md | candidates.md 末尾追加一个 C<n> |
| reviewer | references/reviewer.md | scores.md 末尾追加一条 verdict |
| report_writer | references/report_writer.md | report.json |

所有角色都遵循 references/paper-protocol.md（检索、获取全文、“读过”的定义、摘要文件格式、引用格式）和 references/idea-constraints.md（不做的 idea 类型）。

## 6. 收尾校验（交付前必须做）

运行 `PY SKILL_DIR/scripts/check_run.py RUN`。它对应原系统奖励函数里的“门槛”，任何一项不通过，提案就不合格：
- report.json 能解析成一个 JSON 对象，必需字段（含 `story`、`pilot_guidance` 的各子项）都有内容，每条预测都有前景信号和证伪条件，没有 TODO 之类的占位；
- report.json 的标题、论点、故事、创新点和方法里没有“审计”“保真”这类说法（references/idea-constraints.md）；
- gaps、candidates、scores 的格式符合各角色的规定（每个维度最多 2 个缺口，字段齐全）；
- report.json、gaps、candidates 引用的每个 ID 都有摘要文件，且摘要至少回答了一个阅读目标；
- 设了 Cutoff 时，读过的论文没有一篇在截止日期当天或之后首次公开。

有 ERROR 时，把问题反馈给对应的角色重新派发（例如引用了没读过的论文，就让 report_writer 去读或删掉该引用），修好后再跑一遍。命中审计、保真类说法时，先判断 idea 的核心是否属于这两类：属于就退回 innovator 换方向，只是措辞沾边就让 report_writer 改掉这些说法。WARN 需要人工判断：百分比如果是转述已有论文的事实就没问题，如果是在断言本方法的结果，就必须改写成预测。证伪条件读起来像“没超过 SOTA/基线”时也会 WARN：除非它只在迭代预算用完之后、针对故事所说的那类失败才生效，否则让 report_writer 改成针对机制或故事的条件。

脚本查不到的几条，人工过一遍：一句话论点是否只有一个核心想法；故事线是否一气呵成；是否把预期结果写成了既成事实（“优于”“解决了”）；评审中的最强反对意见在提案里是否得到了回应。没有 Python 时，按上面的清单逐条人工检查。

## 7. 可选：自评打分

用户想给 idea 打分，或比较多次运行的结果时，按 references/evaluation.md 做，结果写入 RUN/evaluation.md。

## 8. 交付

1. 运行 `PY SKILL_DIR/scripts/render_report.py RUN --lang zh`（用户用英文交流时用 `--lang en`），生成 RUN/report.md：引用变成链接，末尾附参考文献。没有 Python 时按同样的结构手工渲染。
2. 告诉用户 report.md 和 report.json 在工作区里的位置。
3. 在对话里简要说明：一句话论点和故事线；攻的是哪个缺口；来源机制及迁移方式；评审结论和最强反对意见；主要风险；下一步：按 pilot_guidance 做最小预实验，先看故事的机制是否成立，不要求一开始就超过 SOTA。提案要交给 autoresearch 工具时，提醒用户让它按 promise_signal 和 kill_condition 判读预实验，而不是看有没有超过 SOTA。如果是在没有 survive 的情况下定稿、有承重的论文只读到了摘要，或者因为没有网络只用了 web_search，要明说。
