---
name: idea-scientist
description: 为一个研究问题生成有文献依据的科研 idea 和完整研究提案：找方法缺口、跨领域迁移机制、对抗式评审、写出结构化提案（改编自 IdeaScientist）。Use when asked to brainstorm, find innovation points for, or develop a grounded research idea or proposal.
---

# IdeaScientist：有文献依据的科研构思

本 Skill 把 IdeaScientist（github.com/jiarui-liu/IdeaScientist，CC BY-NC 4.0，仅限非商业使用）的多角色构思流程改写成可在 Claude 里直接运行的版本。原系统跑在离线论文库 Svalbard Idea Vault 上，并用强化学习分别训练各个角色；这里改用网页检索（arXiv、Semantic Scholar 等），没有训练出的权重，但保留了它的分工、文件接口、证据规则和评审标准。

**目标**：针对一个研究问题，产出**一个**聚焦、可落地、能讲成好故事、经得住对抗式评审的**方法学** idea，再扩写成一份不含编造结果的完整研究提案。不是 idea 清单，也不是五个组件拼成的大系统。

```
problem.md → gap_finder（每个挑战维度一次）→ gaps/ → innovator → candidates.md → reviewer → scores.md
                     ↑                          ↑                                    │
                     └──── reject：换缺口 ───────┴──── revise：带反馈改进 ─────────────┘
survive → report_writer → report.json → 校验（§6）→ report.md 交付（§8）
```

调度者（orchestrator）只做决策、维护 plan.md，自己不检索、不读论文；所有文献知识都通过各角色写出的文件传递。

**故事优先，结果看前景**：idea 值不值得做，先看它能不能讲成一篇好论文的故事：具体的失败 → 现有方法失败的根因 → 洞见 → 方法从洞见自然推出。很多顶会论文的方法一开始并没有超过 SOTA；拿一次没调参的小规模预实验和调好的基线比，没超过就放弃，会误杀好 idea。所以评审不因“不确定能否超过 SOTA”而否决 idea；提案在看到任何结果之前写好故事线和预实验的判读方法：什么算有前景、什么才算真正证伪、下判断前给多少迭代预算。本流程不跑实验，这部分（report.json 的 `story`、`pilot_guidance` 和每条预测的 `promise_signal`，见 §5.4）供研究者或下游的 autoresearch 工具判读预实验。

## 0. 明确问题

整轮工作都建立在问题表述上，所以先把它定下来，写入 problem.md：

```
Challenge: 现有方法在哪里失效、为什么难（尽量具体，最好带一个失败例子）
Problem definition: 形式化设定、输入、输出
Constraints（可选）: 算力、必须用的系统或数据集、目标会议等
Cutoff（可选）: YYYY-MM-DD
```

- 设了 Cutoff，就只使用该日期之前首次发布的论文。这是原论文的“盲测”设置，用来检验 idea 能否预见之后的工作。
- 不设 Cutoff，就使用全部文献，而且新颖性核查必须覆盖最新的论文。
- 用户只给了一个主题或一句话时，先替他起草 Challenge 和 Problem definition，给用户确认一次再开始；用户没有回应就按草稿继续，并在交付时说明。

## 1. 运行目录与文件所有权

在工作目录下新建 `idea_runs/<YYYYMMDD>_<短标题>/`：

| 文件 | 写入者 | 内容 |
|---|---|---|
| problem.md | 启动时写入，之后只读 | 问题表述 |
| plan.md | orchestrator | 目标、当前方向、状态、历史 |
| papers/<id>.md | 读论文的角色（追加式） | 单篇论文的逐目标摘要 |
| gaps/NN-<axis-slug>.md | gap_finder（每个维度一个文件） | 已有工作与开放缺口 |
| candidates.md | innovator（追加式） | 候选 idea C1、C2…… |
| scores.md | reviewer（追加式） | 每个候选的评审结论 |
| report.json | report_writer | 结构化提案 |
| report.md | 交付时由 report.json 渲染 | 给人读的提案 |

规则：每个文件只由它的所有者写；追加式文件只追加、不覆盖，追加前先读最新内容。某个文件有问题时，orchestrator 不自己改，而是带着反馈重新派发它的所有者。没有文件工具时，把这些产物作为带标题的段落放在对话里，规则不变。

## 2. 执行模式

**A. 子智能体模式（有 Agent / Task 之类的子智能体工具时优先使用）**
- 主对话扮演 orchestrator。每调用一次角色，就新开一个子智能体。
- 子智能体看不到本 Skill。每次派发时，把下列内容原样放进它的 prompt：§3 读论文协议、§5.0 不做的 idea 类型、该角色在 §5 的整节说明、problem.md 全文、本次任务字段（见 §4 任务契约）、运行目录的绝对路径。
- 角色完成后只回复一行状态；orchestrator 再去读它写出的文件，不看论文原文，也不看搜索结果。
- 不同维度的 gap_finder 可以并行（各写各的文件）；innovator 和 reviewer 一次只跑一个，保持深度优先。

**B. 单智能体模式（没有子智能体工具时）**
- 你依次扮演各个角色，每次切换时明确标出当前角色。
- 每个角色开始前，只重新读取该角色允许读的文件。角色之间只通过文件交接，不要把上一个角色没写进文件的想法带到下一个角色。
- 到 reviewer 时真正切换成怀疑者：主动去找推翻新颖性的论文，而不是为自己刚写的 idea 辩护。

## 3. 读论文协议（所有角色通用）

**论文 ID 与引用格式**
- 有 arXiv 版本的用 arXiv 号，不带版本号：`2401.12345`。没有的用 `doi:10.xxxx/yyyy`；OpenReview 论文没有 DOI 时用 `openreview:<forum id>`。
- 正文中一律用方括号引用，一个括号放一个 ID：`[2401.12345]`；多个就连写：`[2401.12345][doi:10.1145/3639322]`。不要用标题缩写、作者-年份、链接或圆括号。
- 摘要文件名：把 ID 中的 `/` 和 `:` 换成 `_`，例如 `papers/2401.12345.md`、`papers/doi_10.1145_3639322.md`。
- 如果连接了 Svalbard Idea Vault 的检索工具（例如提供 keyword_search / read_paper 的 MCP），优先用它，ID 改用 vault 的论文 ID，其余规则不变。

**检索**
- 用网页搜索找论文。查询短而具体（2-6 个词），使用该领域的准确术语；结果少就换说法重搜。
- 优先来源：arXiv、Semantic Scholar、OpenReview、ACL Anthology、PVLDB（vldb.org，开放获取）、会议官网。ACM DL 常有付费墙，可以找同一论文的 arXiv 版本。
- 优先打开搜索结果中出现过的链接。arXiv 摘要页上有 HTML 全文和 PDF 的链接，从那里进入正文。
- 设了 Cutoff 时，丢弃首次发布日期不早于 Cutoff 的论文（看 arXiv v1 的提交日期或正式发表日期）。

**“读过”的定义**
- 搜索结果、标题、摘要都不算读过。读论文 = 打开正文（HTML 或 PDF），带着 1-5 个具体的阅读目标去回答。阅读目标是具体的问题，例如“它用什么机制处理 <维度>？”“它自己承认在 <维度> 上有什么局限？”“哪个方法假设使它处理不了 <维度>？”
- 抓取工具支持传入提示（prompt）时，就把阅读目标作为提示传进去。
- 只拿得到摘要的论文（付费墙等）：在摘要文件中写 `Access: abstract-only`。这类论文不能支撑机制层面的论断，near-miss、来源机制、新颖性对比都不行。
- **只能引用本轮已有摘要文件的论文。**不要编造 ID，也不要引用摘要文件不支持的论断。

**摘要文件（追加式，跨调用累积）**

先看 `papers/<id>.md` 是否存在。已经回答过的目标直接复用，不重读；只为新目标读正文，并把答案追加到文件末尾，不覆盖已有内容。新文件的格式：

```
# <标题>
- ID: <id> | Date: <YYYY-MM-DD 或 YYYY-MM，首次发布> | Venue: <会议/期刊或 arXiv> | URL: <链接>
- Access: full-text        （只读到摘要时写 Access: abstract-only）
## What this paper does
（一段，≤120 词）
## Goal-by-goal answers
### Goal: <原样复述的问题>
（≤300 词；具体内容标出处，如 [Sec 3.2 / Eq 5]；正文回答不了就直说）
```

只写阅读目标问到的内容。几篇论文互不依赖时，在同一轮里并行读取。单个角色任务通常读 4-10 篇，软上限 20 篇。

## 4. Orchestrator（调度者，主对话）

你是 PI：决定下一步研究什么、何时深挖、何时转向、何时定稿。你不检索、不读论文，只派发角色、读它们写出的文件、维护 plan.md。想查点什么时，说明该派一个角色去查了。

**目标**：一个聚焦、尖锐、有依据的方法学 intuition。它要 (a) 针对一个真实的缺口；(b) 有清楚且读过原文的来源机制，跨领域优先，领域内也可以，但迁移不能只是重新发现最接近的已有工作；(c) 说清楚来源机制如何映射到本问题；(d) 点名关键的迁移风险；(e) 能讲成一个好故事，主张不依赖在所有基准上超过 SOTA；(f) 通过对抗式评审。

**任务契约**：每次派发的任务就是下列字段，不多不少。problem.md 会随任务一起给出，不要在任务里重述问题。
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
- 只接受方法学贡献：新的方法、技术、算法、模型或系统。基准、数据集、分析、立场文章、综述都不行；审计类、保真类 idea 也不做（定义见 §5.0），选缺口时跳过补法只能落在这两类的缺口。
- 故事优先：reject 只留给不做的类型（不是方法学贡献，或属于审计类、保真类）和让故事讲不成立的根本问题（缺口不真实、已被做过、核心假设与文献矛盾）。reviewer 以“效果不确定”“未必超过 SOTA”为由 reject 时，带上 `FEEDBACK` 让它按故事核查重审。
- 一切以文件为准。角色交回的内容单薄或缺引用时，带着更明确的要求重新派发，不要用自己的猜测去补。
- 没有固定次数。默认上限供参考：挑战维度 ≤4 个；每个缺口修改 ≤3 轮；连续 3 个方向被 reject，就停下来向用户汇报已有发现，问是否继续。

## 5. 角色说明

### 5.0 不做的 idea 类型（所有角色通用）

下面两类 idea 不做。判断看 idea 的核心贡献，也就是它的标题、论点、故事、创新点和方法，不看措辞：只换个说法、机制不变，仍然算。

- **审计类**：核心是对已有方法的输出或过程做事后检查、核查、监控或追溯，例如加一层审计或校验模块、提高可审计性、为追责记录溯源信息。
- **保真类**：核心是让结果对原始对象保持忠实或一致，例如保真、提高忠实度、加保持语义或分布一致的约束。

不算的情况：相关工作、问题背景或评估指标里出现这些词；方法用验证信号来训练或搜索（例如过程奖励），而不是事后检查结果。

### 5.1 gap_finder（相关工作与缺口）

你的任务只给一个挑战维度（AXIS）。你负责找出**同一问题定义、同一挑战**下这个维度上的已有工作，只深挖这一个维度，不铺开到所有维度。

**只找方法学缺口**：已有工作的方法本身（算法、模型机制、训练流程、目标函数、归纳偏置、credit assignment、表示）存在不足，需要提出或改进**方法**来弥补。不要输出基准/数据集缺口、纯实验缺口（“没人跑过这个实验”）、纯评测缺口或应用场景缺口，除非该场景暴露出具体的方法缺陷。诚实的结论不是方法学缺口时，宁可少报，甚至报 0 个，也不要包装。

步骤：
1. 检索：用 4-8 条查询，措辞采用本问题领域、本维度的准确术语，让这个维度上几乎重复的已有工作都进入视野。结果少就换说法重搜。目标是诚实地覆盖缺口，而不是走过场。
2. 阅读：按 §3 读选中的论文，阅读目标紧扣本维度。每个缺口都必须建立在读过的摘要文件上，不能只凭标题或摘要。几篇论文一起并行读。
3. 写入 OUTPUT 文件：

```markdown
## Axis: <与任务中的 AXIS 逐字一致，不改写、不缩写、不改大小写>
### What has been done
按机制分组，概述这个维度上已尝试过的方法（引用论文 ID 并点出具体机制，不只是列标题）。
### Open gaps on this axis
- **Gap:** 一句对比式陈述：已有方法通过 Y 做到 X，但 Y 留下了方法层面的问题 Z。点明具体任务/场景，以及你在挑战 Y 的哪个方法假设。
- **Near-miss methods and coverage:** [id] — 方法及其接近之处；[id] — 方法及其接近之处。说明读过的论文里反复出现的方法缺陷，列出检查过的 ID 或查询轨迹，以及它们为什么没有真正补上这个缺口。
- **Methodological deficiency:** near-miss 工作错过它的一个精确的方法学原因，并标注类型。
- **Why it matters:** 谁被卡住了，补上它能解锁什么新理解或新能力。
- **Evidence route:** 什么可观测的证据或对比，能表明未来某个方法补上了这个缺口。
```

各字段的要求：
- Open gaps：0-2 个最关键、最阻碍进展的缺口。只有一个站得住就写一个，没有就写 0 个。
- Near-miss：ID 必须是本轮读过的；至少 2 个，除非经过有记录的检索，该维度确实只有一个真正的 near miss。
- Methodological deficiency：类型从 missing mechanism / algorithmic limitation / wrong inductive bias / credit-assignment flaw / training-objective mismatch / representation limitation / method-scalability limit / 其他具体方法缺陷 中选。要说清方法本身哪里不够；实验证据可以作支撑，但缺陷必须关于方法。依据来自该论文摘要文件里的具体发现。
- Why it matters：不能只是刷 SOTA，也不能只说问题很难。
- Evidence route：只说如何检验，不要在这里提出解决方法。

质量标准：只有能指出一篇读过的论文“差一点做到、但因可识别的原因没做到”，缺口才算真实。一个论证扎实的缺口胜过几个浅的。

违反下列任一条的缺口一律不要输出：
- 不是方法学缺口，却包装成方法学缺口。
- 引用本轮没读的论文，或引用的论文的摘要文件不支持该论断；编造 ID 或局限。
- 把维度本身改写成缺口（“已有工作没有解决 <维度>”），没有新增具体的、有依据的缺陷。
- 把一篇论文的局限夸大成整个领域的缺口（除非 ≥2 篇读过的论文共有，或有记录的窄检索表明只有一个真正的 near miss）；仅凭“还没人做过 X”主张新颖性，却点不出具体的 near-miss 工作。
- 为了覆盖面凑数，或超出证据范围夸大。
- 补上它的自然办法只能是审计类或保真类 idea（见 §5.0），例如“缺少对输出的核查”“结果对原始数据不够保真”。
- 自我夸奖、元评论，或提及被评估、评分标准。

完成后只回复一行：维度名和新增的缺口数量。

### 5.2 innovator（构思）

每次只产出**一个**表述清楚、来源扎实的研究 intuition，不是选项清单，也不是论文初稿。交付物是一个清晰的想法：灵感从哪里来、为什么它可能补上缺口、概念上怎样用到本问题、能讲成怎样的故事。**不写**正式方法：不要伪代码、公式、架构图、超参数、实验计划，这些是 report_writer 的工作。你的任务是让 idea 和它的灵感来源一目了然，并用找到的文献说明它大概率可行。

任务给你目标编号（TARGET）和要攻的缺口（GAP），可能还有 BUILD_ON（要改进的候选和薄弱维度）。

步骤：
- a) **读输入**：同时查看所有 gaps 文件和 candidates.md，确认你要攻的具体缺口；每个 intuition 都必须对应 gaps 文件里一个有名字的缺口。然后决定新做还是改进：如果已经有一个针对该缺口、值得改进的候选（任务指向它，或它接近但有缺陷），就做出一个明显更好的版本（更清楚、来源更扎实，或补强被指出的薄弱维度），并保留已经成立的部分；否则从头形成一个新的 intuition。无论哪种，都输出一个新的 C<n>。
- b) **找来源机制**（idea 就从这里来）：用 6-10 条查询，寻找一种逻辑可以迁移到该缺口的机制或原理。**优先**刻意跨领域，覆盖 ≥3 个不同的子领域：本领域论文从没碰过的机制，往往带来最强、最新颖的迁移。但这只是偏好，不是硬性要求；最可能补上缺口的机制就在本领域内也可以，只要迁移不平凡、不是重新发现最接近的已有工作。改进已有候选时，只搜到足以补强其薄弱维度或找到更贴近的来源为止。各领域可以试探的方向举例：
  - 代码生成的强化学习：数学推理中的过程奖励；博弈 RL 中的树搜索回传（AlphaZero 式）；options / 分层 RL；策略梯度理论中的控制变量与基线；逆强化学习；基于势函数的奖励塑形；偏好 RL。
  - 个性化：bandit 探索；元学习；表示对齐；对话中的用户建模。
  - 数据库与查询优化：编译器中的 profile-guided optimization；鲁棒优化与分布偏移；在线学习中的探索-利用；不确定性校准（如 conformal prediction）；流式算法中的 sketch。
- c) **形成一个 intuition**：挑出最有希望、也最能讲成好故事的那个来源机制，先用一句话对自己说清楚，例如“min-form credit assignment 只在数学推理里用过——把它迁移到代码 RL”。再把它讲成故事：现有方法在哪里怎样失败 → 根因是什么 → 你的洞见 → 方法为什么从洞见自然推出。讲不顺，通常说明缺口或来源机制还没找准。
- d) **落实来源**：按 §3 读来源论文，阅读目标瞄准要迁移的机制，例如“核心机制是什么、为什么在那里有效？”“<机制> 依赖什么假设？”。读到足以 (i) 准确解释灵感，(ii) 论证迁移可行：该机制依赖的条件在本问题中也成立，或者可以使其成立。这种文献依据就是你的可行性论证。不要编造机制或来源；intuition 中承重的部分没有出处，就去读能定论的那篇论文。新颖性对比用到的最接近的领域内工作也**必须**读过，不能凭标题或摘要判断差异。来源论文和领域内对比论文互不依赖，一起并行读。

然后在 candidates.md 末尾追加一节，不覆盖已有候选。每一部分都要简短、平实、无歧义；标准是把 idea 讲清楚，而不是写得正式：

```markdown
### C<n> — <短标题>
- **Intuition:** 一到两句话，让不熟悉来源领域的人也能看懂。
- **Story:** 3-4 句故事线：现有方法在什么场景下怎样失败 → 根因 → 洞见 → 方法如何从洞见推出。
- **Gap it attacks:** gaps 文件中的具体缺口，以及现有方法的具体失败；补上它为什么重要、能解锁什么。
- **If improving prior candidate:** （仅在适用时）C<x> 的哪个弱点被解决、这次改了什么。
- **Source inspiration:** 来源论文 [id]、它们用的机制或原理、为什么在那里有效；标注新颖性类型。
- **How it maps to this problem:** 迁移过来后，什么扮演什么角色。
- **Why it could work / feasibility:** 机制依赖的条件，以及它为什么在这里也大概率成立；必须为真的关键假设。
- **Novelty vs. closest in-domain work:** 最接近的领域内论文 [id] 及具体差异。
- **Main risk:** 这个 intuition 出错或迁移失败最可能的原因。
```

各部分的要求：
- Intuition：说不清楚、说不短，就说明还没成形。
- Story：讲论文的故事，不讲方法细节。故事靠“失败真实、根因非显然、方法从洞见推出”成立，不能靠“会超过 SOTA”这类还没看到的结果成立。
- Gap it attacks：写现有方法的**具体**失败，不能写“没人做过 X”。
- Source inspiration：这是核心。依据你读到的内容，而不是标题或摘要。来源跨领域更好，领域内也可以，只要迁移不平凡。新颖性类型从 new-topic / recombination-of-distant-concepts / reinforcing-a-weak-connection 中选。
- How it maps to this problem：平实语言的概念翻译，不写伪代码、公式、架构或超参数。
- Why it could work：可行性靠来源文献论证，不靠实验计划。
- Novelty：一行即可。远领域组合也算新颖，但必须点名对手，不能凭感觉。
- Main risk：一行。

引用规则：每个 ID 都放进方括号，不用圆括号或裸数字。只引用本轮读过的论文；gaps 文件里已出现的论文是上游读过的，可以直接引用。其他论文（比如只是搜索命中的）必须先读再引用，否则不要引用。

idea 必须是方法学贡献，不是分析、基准、数据集、综述或立场文章，也不能是审计类或保真类（见 §5.0）：最有希望的来源机制落在这两类里，就换一个。这个候选基于什么、为什么，由 orchestrator 记在 plan.md 里，不写进 candidates.md。

完成后只回复一行：`C<n> created — <intuition 那句话>`，并注明是新做的还是改进了 C<x>。

### 5.3 reviewer（对抗式评审）

任务给你一个候选编号。默认立场是怀疑：找出这个 intuition **不该**进入论文阶段的理由，再判断它是否仍然站得住。要主动检索和阅读，不能只看 candidates.md 就下结论。

你最终要回答的是：**这能不能讲成一篇好论文的故事？** 文献能检验的东西（新颖性、来源、映射、迁移假设）要严格查；文献检验不了的东西（能否超过 SOTA、提升有多大）不是否决的理由。很多顶会论文的方法一开始并没有超过 SOTA，这类不确定性留给预实验去看前景。

1. 读 candidates.md 中目标 C<n> 的完整一节，也读 gaps 文件。
2. **来源核查**：必要时读来源论文，核实候选是否准确陈述了借用的机制或原理，以及它起作用的条件。不认可只靠标题或感觉支撑的说法。来源可以跨领域（更好），也可以在领域内；不因来源在领域内而扣分，迁移的新颖性在第 3 步判断。
3. **新颖性核查**（主动）：用“借用的机制 + 目标问题”构造查询去**证伪**新颖性差异，而不只是搜大领域。遇到相近的论文先看题录；需要正文细节才能确认是否重叠时，就按 §3 去读。判断候选点名的最接近工作是否已经做了同样的事，以及所说的差异是否真实。没有设 Cutoff 时，至少有一条查询专门针对最近一两年的新论文，因为网页上能搜到最新工作，撞车风险更高。
4. **概念映射核查**：你能否复述“来源机制搬到本问题后，什么扮演什么”？只有唤起性的类比、没有说明映射的，要扣分。但不要要求伪代码、公式、架构、超参数、实验计划或正式方法细节，那是 report_writer 的事。
5. **迁移可信度核查**：候选是否点明了迁移成立所必需的关键假设？在来源文献和目标缺口之下，这个假设是否可信？缺失或明显错误的迁移假设是真实的弱点。
6. **故事核查**：用一句话复述这篇论文的故事：“现有方法在 <场景> 上 <怎样失败>，因为 <根因>；我们注意到 <洞见>，所以 <方法>。”然后检查：失败是否具体，是这个领域的人会认的问题；根因是否非显然，并由读过的论文支撑；方法是否从洞见自然推出，跨领域迁移要讲得出“为什么偏偏是这个机制”，而不只是“它在别处有效，搬过来试试”；即使方法没有在所有基准上超过 SOTA，故事的主张（例如消除了这类失败，或以更低代价达到同等效果）是否仍然站得住。复述不出来，或中间要靠牵强的跳跃，就是故事的弱点。
7. **贡献类型核查**：必须是方法学贡献（新的方法、技术、算法、模型或系统）。分析、基准、数据集、综述、立场文章一律不通过，无论其他方面多好。核心贡献属于审计类或保真类（见 §5.0）的同样不通过，换个说法也不行；只是表述沾边、机制本身不属于这两类的，给 `revise(focus=clarity)`，在 Evidence 里指出要改的说法。
8. 在 scores.md 末尾追加：

```markdown
### C<n> verdict
- **Verdict:** survive | revise(focus=<dim>) | reject(reason=<简短原因>)
- **Evidence:**
  - [id] 1-2 句理由，或转述你所质疑的来源机制或已有工作机制
- **Story in 1 sentence:** 第 6 步复述的那句故事；复述不出来就写“讲不成”，并说明卡在哪一环
- **Strongest objection in 1 sentence:** 最大的一个问题
```

Verdict 的含义：
- `survive`：所有核查都通过，故事成立，可以交给 report_writer。
- `revise(focus=<dim>)`：问题可以修复。指出最弱的一个维度，从 `novelty`、`coherence`、`feasibility`、`clarity`、`mapping`、`grounding`、`story` 中选。
- `reject(reason=…)`：有根本性问题，或属于不做的类型（不是方法学贡献，或属于审计类、保真类）。写明原因，方便放弃这条线、另起炉灶。

reject 只用于两种情况：属于不做的类型（不是方法学贡献，或属于审计类、保真类）；有让故事讲不成立的根本问题（缺口不真实、核心机制已经有人做过、迁移依赖的关键假设与读过的文献矛盾，或者怎么改都讲不出一条成立的故事线）。“效果不确定”“未必能超过 SOTA”“提升可能不大”不是 reject 的理由，把它写进 Strongest objection，交给预实验看前景。

完成后只回复一行：`C<n>: <verdict>`。

### 5.4 report_writer（结构化提案）

把 survive 的 intuition 扩写成论文形态的方案提案，以**一个**合法的 JSON 对象写入 report.json，不写 markdown 正文。实验还没做，绝不能编造结果。

先读 gaps 文件、candidates.md 和 scores.md。目标候选就是提案的主题，评审意见要在提案里回应。

**事实依据**
- 引用的已有工作：先按 §3 读，只陈述摘要文件真正支持的内容。gaps 文件和 candidates.md 里已经出现的论文是上游读过的，可以直接引用。只在搜索结果里见过标题的论文不算读过，不能引用。
- 你提出的方法：可以是新的、未经验证的，但预期结果只能写成预测，绝不能写成观察到的结果。任何字段都不能出现编造的数字，也不能留 TODO 占位。
- 每个字段都要填。下面 schema 中的每个键都是必需的，要给出有实质内容、基于输入和引用文献的值。某字段看似不适用也要正面回应（例如写明“不需要训练模型”及理由），而不是删掉这个键。

**故事与预实验**

提案先要讲成一个好故事。`story.arc` 写论文的故事线：具体的失败 → 现有方法失败的根因 → 洞见 → 方法为什么从洞见推出 → 读者读完记住什么。`story.headline_claim` 是论文要守住的主张，它不能依赖“在所有基准上超过 SOTA”，例如“消除了这类失败”“以更低代价达到同等效果”。

预实验只看前景，不要求一开始就超过 SOTA：一次没调参的小规模预实验输给调好的基线，说明不了什么。研究者或下游的 autoresearch 工具会照你写的内容判读预实验，所以要在看到任何结果之前写清楚：
- `promise_signal`：每条预测“有前景”的早期信号。典型的是：在故事针对的那类失败上，方法相对自身消融（同一份代码、同样的调参预算）朝预测方向改善；或者故事依赖的诊断量按预测变化。主指标还低于 SOTA 也算有前景。
- `kill_condition`：只针对机制或故事被证伪，例如所诊断的失败在基线上根本不出现，或者迭代预算用完后，方法仍完全没有改变它要改变的那个量。不能写成“预实验没超过 SOTA/基线”。
- `pilot_guidance`：最小预实验怎么做；哪些结果不构成放弃的理由；下判断之前给多少轮调试、调参和扩大规模；主张不成立但机制有效时，同一个方法还能讲的备选故事。

信号和条件都要可观测、事先写定。不这样做，“有前景”就会变成什么结果都能自圆其说。

**写作步骤**
0. 读完输入后决定要引用哪些论文，把其中尚未读过、也不在 gaps/candidates 中的论文全部读完，可以并行。所有引用都读完之前不要开始写。
1. 在脑中组装完整的 JSON。写作中途可以、也应该检索和阅读，去核实你提到的每个具体东西：已有的基准、指标、数据集、模型或方法。能找到对应论文，就读它并在行内引用 [id]，不要无引用地提及。
2. 把整个对象写入 report.json：只有一个 JSON 对象，不加代码块围栏，前后没有任何文字。内容太长时可以分段写，但最终文件必须是一个合法的 JSON 对象。
3. 重新读取 report.json，确认它能解析为恰好一个合法的 JSON 对象；有错就修正后整体重写。

字段值用用户的语言书写，键名保持英文。`key_novelty` 和 `method` 写的是**你的**贡献，`baselines` 是你**将要**对比的方法：

```json
{
  "title": "<proposal title>",
  "topic_relevance": {
    "sub_topic": ["specific sub-areas this work belongs to"],
    "primary_focus": ["aspects addressed within the sub-topic"]
  },
  "one_sentence_thesis": "MUST be under 30 words, no jargon, no metric numbers.",
  "story": {
    "arc": "3-5 sentences: the concrete failure -> its root cause in existing methods -> the key insight -> why the method follows from it -> what the reader takes away.",
    "headline_claim": "the main claim the paper will defend; it must stand without beating SOTA on every benchmark (e.g. removes the targeted failure, or matches SOTA at lower cost).",
    "carrying_evidence": ["the 1-3 figures or tables that would carry the story, e.g. a diagnostic showing the failure on the baseline and its removal by the method"]
  },
  "core_problem": {
    "problem_statement": "1-2 sentences: be specific about what fails and why.",
    "why_it_matters": ["motivation ONLY — real-world impact + research gap in prior work; do NOT describe the solution here."],
    "concrete_example": "a specific input/output scenario showing what goes wrong with current approaches."
  },
  "key_novelty": {
    "main_idea": "short name for the contribution",
    "explanation": ["2-3 bullets, <=35 words each, intuition/analogy level, no formal notation"]
  },
  "problem_definition": {
    "formal_setting": "mathematical or formal description of the problem",
    "inputs": "what the system receives",
    "outputs": "what the system produces"
  },
  "key_terms": {"<term>": "<plain-language definition>"},
  "related_work": [
    {
      "sub_area": "...",
      "what_it_does": "mechanism-level summary of prior work in this sub-area, citing [id]",
      "open_gap": "the gap this prior work leaves that the proposal addresses",
      "citations": ["<paper ids, e.g. 2401.12345>"]
    }
  ],
  "method": {
    "high_level_flow": ["Group name: module1 -> module2"],
    "modules": [
      {"module": "name", "role": "what it does", "model": "exact architecture if any",
       "inputs": ["..."], "outputs": ["..."], "notes": "implementation details"}
    ],
    "novel_architectural_elements": ["STRICTLY structural design choices — how modules are arranged/connected"],
    "pseudocode": "the core algorithm as a code-block string",
    "design_choices": ["key design choice + why"],
    "theoretical_grounding": "mathematical / theoretical justification"
  },
  "model_details": {
    "base_model": "be specific, e.g. 'LLaMA-2-7B' not 'LLaMA-based'; or 'no model training' + why",
    "training": {
      "method": "e.g. 'supervised fine-tuning', 'RLHF', 'contrastive learning'",
      "objective_functions": ["Purpose: <plain language>. Formally: <notation>"],
      "adaptation": "e.g. 'LoRA (rank=16)' or 'Full fine-tuning'",
      "key_hyperparameters": {}
    }
  },
  "comparison_to_sota": {
    "related_methods": ["Name [id]: one-line description"],
    "key_differences": ["vs. <Method> [id]: <specific difference>"]
  },
  "proposed_evaluation": {
    "evaluation_setting": "how the method WOULD be evaluated",
    "benchmarks": [{"name": "benchmark or dataset to use", "task_type": "e.g. classification, generation, retrieval", "newly_constructed": false}],
    "baselines": ["methods to compare against"],
    "main_metrics": ["all metrics to report"],
    "ablations": ["ablation studies that isolate each contribution"]
  },
  "falsifiable_predictions": [
    {"pillar": "which design pillar this tests", "prediction": "one empirical claim the method implies",
     "promise_signal": "the early, cheap observation that counts as promising even while headline metrics still trail SOTA",
     "kill_condition": "the observation that would FALSIFY the mechanism or the story; never just 'not better than SOTA/baselines in a pilot'"}
  ],
  "pilot_guidance": {
    "minimal_pilot": "the cheapest experiment that tests the story's core mechanism: setting or data slice, the method vs. its own ablation under the same budget, the diagnostic to watch",
    "not_kill_reasons": ["early outcomes that must NOT be read as failure, e.g. headline metric below published SOTA with untuned hyperparameters"],
    "iteration_budget": "how many rounds of debugging, tuning and scaling to spend before judging, and what each round changes",
    "fallback_story": "if the mechanism works but the headline claim does not hold, the narrower story the same method still supports"
  },
  "limitations": ["3-5 concise bullets, acknowledged or apparent from the method"]
}
```

**引用规则**：在相关的字符串值内用方括号写论文 ID，一个括号一个 ID，例如 `[2401.12345][2310.06789]`。`related_work[].citations` 用纯 ID 字符串列表列出同一批 ID。只能引用本轮读过、或已在 gaps/candidates 中出现的论文。想引用的论文找不到可读的版本，就换一篇能读的等价论文，或者删掉这条论断。绝不编造 ID。

**写作质量**（来自原系统的评分标准）
- 标题和一句话论点只传达**一个**核心想法，不带无依据的性能主张。
- 忠实于指定的缺口和 intuition，不漂移到别的方案。
- 先把问题（现状与期望之间的差距）讲清楚，再推销方法；说明为什么朴素做法和现有方法不够。
- 给出一个具体的输入/输出例子，展示现有方法在哪里失败。
- 写清任务、输入、输出、评估目标和适用范围假设。
- 相关工作按主题或机制组织，陈述准确、评价公允。
- proposed_evaluation 直接检验核心主张；基线相关、够强、公平调参；规划消融和不确定性估计，使每个主张都能被单独检验。
- 新颖性写成一条可复用的洞见，并说明已有工作为什么没覆盖它。
- 方法自顶向下讲解，设计选择都有理由；给出复现所需的实现细节。
- story 一气呵成：从失败到方法，每一步都有依据、没有牵强的跳跃；headline_claim 不依赖全面超过 SOTA。
- falsifiable_predictions 覆盖主要的设计支柱，每条都有前景信号和明确的证伪条件；证伪条件针对机制或故事，而不是“没超过 SOTA”。
- pilot_guidance 在看到任何结果之前就能照着执行；备选故事事先写明，同样由机制支撑，不是事后换个说法。
- 不把贡献讲成审计类或保真类（见 §5.0）：标题、论点、故事、创新点和方法里不出现“审计”“保真”及同义说法，校验脚本会对此报 ERROR。写作中发现 idea 的核心其实属于这两类，不要靠换措辞掩盖，在回复里说明，由 orchestrator 处理。
- limitations 写出真实的假设、适用边界和可能的失效模式。
- 承重论断引用的是**真正**支持它的论文：对的论文，对的贡献。
- 禁止：把预期结果写成测得的结果，无论是定性的“优于/解决了”还是定量的“达到 92%”；使用 better、robust、efficient 之类的词却不给操作性定义；自我夸奖或提及评分标准。

完成后只回复一行：report.json 已写好、能解析，且每个引用的 ID 都有对应的摘要文件。

## 6. 收尾校验（交付前必须做）

这些检查对应原系统奖励函数里的“门槛”：任何一项不通过，提案就不合格。能执行代码时，运行下面的脚本，把运行目录作为参数；不能执行代码时，按同样的清单人工检查。

```bash
python3 - idea_runs/<run_dir> <<'EOF'
import json, re, sys, pathlib

run = pathlib.Path(sys.argv[1])
ID = r"(?:\d{4}\.\d{4,5}|doi:[^\[\]\s]+|openreview:[^\[\]\s]+)"
CITE = re.compile(r"\[(" + ID + r")\]")
VERSIONED = re.compile(r"\[(\d{4}\.\d{4,5}v\d+)\]")
REQUIRED = ["title", "topic_relevance", "one_sentence_thesis", "story", "core_problem",
            "key_novelty", "problem_definition", "key_terms", "related_work", "method",
            "model_details", "comparison_to_sota", "proposed_evaluation",
            "falsifiable_predictions", "pilot_guidance", "limitations"]
SUBFIELDS = {"story": ["arc", "headline_claim", "carrying_evidence"],
             "pilot_guidance": ["minimal_pilot", "not_kill_reasons", "iteration_budget", "fallback_story"]}
# a kill condition that only says "not better than SOTA / the baselines": a pilot that trails SOTA is not a kill
SOTA_KILL = re.compile(r"(?=.*(?:SOTA|state.of.the.art|baseline|基线|已有方法|现有方法|最强方法))"
                       r"(?=.*(?:(?:not|n't) (?:better|beat|outperform|exceed|surpass|improve)"
                       r"|fails? to (?:beat|outperform|exceed|surpass|improve)|no (?:better|gain|improvement)"
                       r"|worse than|underperform|lags? behind|falls? short|不优于|不如|不超过|未超过|没有?超过"
                       r"|未能超越|持平|落后|差于|劣于|没有提升|无提升))", re.I | re.S)
# wording of the excluded idea types (§5.0) in the fields that state the idea itself
AVOID = re.compile(r"审计|稽核|核查|审查|保真|忠实|audit|fidelity|faithful", re.I)
AVOID_FIELDS = ("title", "one_sentence_thesis", "story", "key_novelty", "method")
errors, warns, cited = [], [], {}

def strings(x, path=""):
    if isinstance(x, str):
        yield path, x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from strings(v, f"{path}[{i}]")

def digest(pid):
    return run / "papers" / (re.sub(r"[/:]", "_", pid) + ".md")

# 1) report.json is exactly one JSON object with every required field filled
try:
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("top level is not an object")
except Exception as e:
    sys.exit(f"ERROR report.json does not parse as one JSON object: {e}")
for k in REQUIRED:
    if report.get(k) in (None, "", [], {}):
        errors.append(f"missing or empty field: {k}")
for k, subs in SUBFIELDS.items():
    v = report.get(k)
    for s in subs if v not in (None, "", [], {}) else []:
        if not isinstance(v, dict) or v.get(s) in (None, "", [], {}):
            errors.append(f"missing or empty field: {k}.{s}")
preds = report.get("falsifiable_predictions")
for i, p in enumerate(preds if isinstance(preds, list) else []):
    if not (isinstance(p, dict) and all(str(p.get(x) or "").strip()
                                        for x in ("prediction", "promise_signal", "kill_condition"))):
        errors.append(f"falsifiable_predictions[{i}] needs prediction, promise_signal and kill_condition")
    elif SOTA_KILL.match(str(p["kill_condition"])):
        warns.append(f"falsifiable_predictions[{i}].kill_condition reads like 'not better than SOTA / baselines': "
                     "a pilot that trails SOTA is not a kill, so tie it to the mechanism or the story")

# 2) collect every cited id from the report and the upstream artifacts
for p, s in strings(report):
    for m in CITE.findall(s):
        cited.setdefault(m, p)
    for m in VERSIONED.findall(s):
        errors.append(f"drop the version suffix: [{m}] in {p}")
for i, rw in enumerate(report.get("related_work") or []):
    for c in (rw.get("citations") or []) if isinstance(rw, dict) else []:
        c = str(c).strip().strip("[]")
        if re.fullmatch(ID, c):
            cited.setdefault(c, f"related_work[{i}].citations")
        else:
            errors.append(f"related_work[{i}].citations has a non-ID entry: {c!r}")
for f in [run / "candidates.md", *sorted((run / "gaps").glob("*.md"))]:
    if f.exists():
        for m in CITE.findall(f.read_text(encoding="utf-8")):
            cited.setdefault(m, f.name)

# 3) every cited id was actually read (has a digest)
for pid, where in sorted(cited.items()):
    f = digest(pid)
    if not f.exists():
        errors.append(f"cited but never read (no papers/{f.name}): [{pid}] in {where}")
    elif re.search(r"Access:\s*abstract-only", f.read_text(encoding="utf-8")):
        warns.append(f"[{pid}] is abstract-only: it must not carry a mechanism-level claim")

# 4) with a cutoff, no paper on or after the cutoff may have been read
prob = run / "problem.md"
cut = re.search(r"Cutoff[^:：\n]*[:：]\s*(\d{4}-\d{2}-\d{2})", prob.read_text(encoding="utf-8")) if prob.exists() else None
if cut:
    c = cut.group(1)
    for f in sorted((run / "papers").glob("*.md")):
        d = re.search(r"Date:\s*(\d{4}(?:-\d{2}){0,2})", f.read_text(encoding="utf-8"))
        if not d:
            warns.append(f"{f.name}: no Date line, cannot check the cutoff")
        elif d.group(1) >= c:
            errors.append(f"{f.name}: dated {d.group(1)}, on or after the cutoff {c}")
        elif c.startswith(d.group(1)):
            warns.append(f"{f.name}: date {d.group(1)} is too coarse to compare with the cutoff {c}")

# 5) percentages outside evaluation/prediction fields may be claimed results
for p, s in strings(report):
    if not p.startswith(("proposed_evaluation", "falsifiable_predictions", "pilot_guidance", "model_details", "method")) \
            and re.search(r"\d+(?:\.\d+)?\s?%", s):
        warns.append(f"percentage in {p}: fine if it is a cited fact, not if it is a result of this method")

# 6) the idea itself must not be framed as an audit or fidelity idea (§5.0)
for p, s in strings({k: report.get(k) for k in AVOID_FIELDS}):
    m = AVOID.search(s)
    if m:
        errors.append(f"{p} frames the idea as audit / fidelity ('{m.group(0)}'): excluded by §5.0")

for e in errors:
    print("ERROR", e)
for w in warns:
    print("WARN ", w)
print(f"{len(cited)} cited ids checked: {len(errors)} errors, {len(warns)} warnings")
sys.exit(1 if errors else 0)
EOF
```

有 ERROR 时，把问题反馈给对应的角色重新派发（例如引用了没有摘要文件的 ID，就让 report_writer 去读那篇论文或删掉该引用），修好后再跑一遍。命中审计、保真类说法时，先判断 idea 的核心是否属于这两类：属于就退回 innovator 换方向，只是措辞沾边就让 report_writer 改掉这些说法。WARN 需要人工判断：百分比如果是转述已有论文的事实就没问题，如果是在断言本方法的结果，就必须改写成预测。证伪条件读起来像“没超过 SOTA/基线”时也会 WARN：除非它只在迭代预算用完之后、针对故事所说的那类失败才生效，否则让 report_writer 改成针对机制或故事的条件。

脚本查不到的几条，人工过一遍：一句话论点是否只有一个核心想法；故事线是否一气呵成；是否把预期结果写成了既成事实（“优于”“解决了”）；评审中的最强反对意见在提案里是否得到了回应。

## 7. 可选：自评打分

用户想给 idea 打分，或比较多次运行的结果时再做，结果写入 evaluation.md。最好交给一个全新的子智能体来做，没有看过构思过程的评审更可信。

- **质量**（各 1-10 分，每项一句理由）：actionability（有能力的研究者能否照着执行）；specificity（机制、公式、具名的数据集/基线/指标是否具体）；clarity（组织是否清楚、无歧义）；impact（如果成功，对领域有多重要）；story（能否讲成好论文的故事：失败具体、根因非显然、方法从洞见自然推出，不全面超过 SOTA 主张也站得住）；soundness（技术推理是否正确自洽、假设是否明确、是否承认失效模式、有无夸大）；relevance（是否正中 problem.md 的挑战）。锚点：1-2 严重不足；3-4 有重大缺口；5-6 部分合格但有关键缺口；7-8 强，缺口有限；9-10 极强且有充分支撑。
- **新颖性**（1-10）：相对最接近的已有工作（gaps 中的 near miss 加上 reviewer 找到的相近论文），提案多贡献了什么。锚点：1-2 核心机制与某篇参考相同；3-4 小改动或直接组合；5-6 明确的一步但重叠较多；7-8 实质不同；9-10 与参考高度不同。奖励真实、不显然的新意，不奖励换术语。
- **跨设定迁移**（0 或 1）：以下四条都由提案支持才给 1：(1) 指出了与目标不同的来源设定；(2) 从中引入了具体的机制、抽象或分析技术，只有引用或通用工具不算；(3) 指出了解释迁移为何成立的共享结构；(4) 说明了如何改造该机制来利用这一结构。附一段 ≤35 词的提案原文作证据，找不到就给 0。
- **机制非显然性**（两步，必须分开做）：
  1. 推导：让一个**从未看过提案**的子智能体，只拿 problem.md 和最接近的已有工作的摘要文件，独立推导最多 3 个候选机制，每个写清核心操作、推导步骤、每个非标准步骤来自哪篇参考、关键假设。
  2. 评级：冻结这份候选清单，再让另一个子智能体拿它对照提案评级，不得修补、合并或扩充候选。等级：`trivial_combination`（某个候选已直接包含核心机制）/ `routine_extension`（只需常规实现步骤就能从候选得到）/ `non_obvious_step`（所有候选都缺一个关键步骤或结构性观察）/ `surprising`（缺失的关键步骤还违背了已有文献建立的明确预期）。只有能指出缺失的关键步骤时，才给后两级。
  
  单智能体模式下做不到“盲推导”，跳过这一项。

## 8. 交付

1. 从 report.json 渲染 report.md，使用用户的语言。只改格式，不改内容：`[2401.12345]` 变成指向 `https://arxiv.org/abs/2401.12345` 的链接，`doi:` 开头的 ID 指向 `https://doi.org/…`；末尾附参考文献列表（标题、日期、链接，取自摘要文件）。
2. 把 report.md 和 report.json 交给用户。
3. 在对话里简要说明：一句话论点和故事线；攻的是哪个缺口；来源机制及迁移方式；评审结论和最强反对意见；主要风险；下一步：按 pilot_guidance 做最小预实验，先看故事的机制是否成立，不要求一开始就超过 SOTA。提案要交给 autoresearch 工具时，提醒用户让它按 promise_signal 和 kill_condition 判读预实验，而不是看有没有超过 SOTA。如果是在没有 survive 的情况下定稿，或者有承重的论文只读到了摘要，要明说。
