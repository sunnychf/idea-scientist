# idea-scientist

为一个研究问题生成**有文献依据**的科研 idea 和完整研究提案的 Agent Skill，提供 Codex 和 Claude 两个版本。改编自 [IdeaScientist](https://github.com/jiarui-liu/IdeaScientist)（CC BY-NC 4.0）。

> An agent skill for grounded research ideation (gap finding → cross-domain mechanism transfer → adversarial review → structured proposal), adapted from IdeaScientist for OpenAI Codex and Claude. Instructions are in Chinese.

## 它做什么

```
problem.md → gap_finder（每个挑战维度一次）→ gaps/ → innovator → candidates.md → reviewer → scores.md
                     ↑                          ↑                                    │
                     └──── reject：换缺口 ───────┴──── revise：带反馈改进 ─────────────┘
survive → report_writer → report.json → 收尾校验 → report.md
```

- **gap_finder**：针对一个挑战维度，检索并精读同一问题下的已有工作，找出 0-2 个方法学缺口。
- **innovator**：优先跨领域寻找可以迁移过来的机制，形成一个有出处、能讲成故事的 intuition。
- **reviewer**：对抗式评审，主动检索去证伪新颖性，并检查 idea 能否讲成一篇好论文的故事，给出 survive / revise / reject。
- **report_writer**：把通过评审的 intuition 写成结构化提案（results-masked JSON），不编造任何实验结果；提案里写明故事线和预实验的判读方法。
- **orchestrator**：自己不检索、不读论文，只读各角色写出的文件，维护 plan.md 并决定下一步。

每条引用都必须来自本轮真正读过正文的论文。可以设置 Cutoff 日期做“盲测”：只用截止日期之前的文献，检验 idea 能否预见之后的工作。

### 故事优先，预实验看前景

很多顶会论文的方法一开始并没有超过 SOTA。自动科研工具却常拿一次没调参的小规模预实验去和调好的基线比，没超过就放弃 idea，误杀率很高。所以：

- reviewer 先问“能不能讲成好故事”：失败是否具体、根因是否非显然、方法是否从洞见自然推出。reject 只用于故事讲不成立的根本问题（缺口不真实、已被做过、核心假设与文献矛盾、不是方法贡献）；“效果不确定”“未必超过 SOTA”不是 reject 的理由。
- 提案的每条预测都有 `promise_signal`（算有前景的早期信号，例如在目标失败上相对自身消融有改善，哪怕主指标还低于 SOTA）；`kill_condition` 只针对机制或故事被证伪，不能是“预实验没超过 SOTA”。
- `pilot_guidance` 写明最小预实验、不构成放弃理由的情况、下判断前的迭代预算和备选故事。

这些都在看到任何结果之前写定，避免“有前景”变成什么结果都能自圆其说。本工具自己不跑实验，把 report.json 交给 autoresearch 工具时，让它按这几个字段判读预实验。

## 目录

| 路径 | 内容 |
|---|---|
| `codex/idea-scientist/` | Codex 版：`SKILL.md`、各角色说明（`references/`）、检索读论文与校验脚本（`scripts/`） |
| `claude/idea-scientist/` | Claude 版：单个 `SKILL.md`，使用 Claude 的网页搜索和子智能体 |
| `tests/` | Codex 版脚本的离线测试 |

## 安装

### Codex（CLI、IDE 插件、桌面应用）

把 `codex/idea-scientist` 复制到个人 Skill 目录 `~/.agents/skills/`。

Windows（PowerShell）：

```powershell
git clone https://github.com/sunnychf/idea-scientist.git
New-Item -ItemType Directory -Force "$env:USERPROFILE\.agents\skills" | Out-Null
Copy-Item -Recurse -Force .\idea-scientist\codex\idea-scientist "$env:USERPROFILE\.agents\skills\"
```

macOS / Linux：

```bash
git clone https://github.com/sunnychf/idea-scientist.git
mkdir -p ~/.agents/skills && cp -R idea-scientist/codex/idea-scientist ~/.agents/skills/
```

Skill 没出现的话，重启 Codex。推荐的设置：

- 在 `~/.codex/config.toml` 顶部（任何 `[段]` 之前）加一行 `web_search = "live"`。默认的 `cached` 模式可能查不到最新论文，新颖性核查会不准。
- 第一次运行 `scripts/paper.py` 时批准联网；也可以在 `[sandbox_workspace_write]` 段设置 `network_access = true`。
- 需要 Python 3.8 及以上。`pip install pypdf` 之后，只有 PDF 的论文也能读全文。

### Claude

- **Claude Code**：复制到 `~/.claude/skills/idea-scientist/`（项目级则放到 `.claude/skills/idea-scientist/`）。
- **Claude 应用**：把 `claude/idea-scientist` 文件夹打包成 zip（zip 根目录下是 `idea-scientist/` 文件夹），在 Customize > Skills 中添加。需要开启代码执行。

## 使用

Codex 里输入 `$idea-scientist`；Claude 里直接描述需求即可触发。最好同时给出：

```
Challenge: 现有方法在哪里失效、为什么难（最好带一个失败例子）
Problem definition: 设定、输入、输出
Cutoff（可选）: 2026-01-01
```

运行结果保存在工作区的 `idea_runs/<日期>_<短标题>/`：`gaps/`、`candidates.md`、`scores.md`、`papers/`（逐篇阅读摘要）、`report.json` 和 `report.md`。

## Codex 版的脚本

```bash
python scripts/paper.py ping                                   # 检查联网和 PDF 支持
python scripts/paper.py search "learned cardinality estimation" --run <RUN> --abstracts
python scripts/paper.py fetch 2401.12345 --run <RUN>           # 下载全文并打印章节目录
python scripts/paper.py show 2401.12345 --run <RUN> --section "3"
python scripts/check_run.py <RUN>                              # 收尾校验
python scripts/render_report.py <RUN> --lang zh                # 生成 report.md
```

数据来自 arXiv API、Semantic Scholar（可设置环境变量 `S2_API_KEY`）、Crossref 和 OpenReview。设了 Cutoff 时，脚本会自动过滤晚于截止日期的论文；论文的后续版本晚于截止日期时，只读 v1。

## 测试

```bash
python tests/test_paper.py
python tests/test_check_render.py
```

测试使用模拟数据，不需要联网。

## 与原项目的区别

- 没有原论文用强化学习为各角色训练的 LoRA 权重，效果取决于所用模型本身。
- 检索从离线的 Svalbard Idea Vault 换成了 arXiv、Semantic Scholar 和网页搜索。
- 提示词翻译成中文并做了精简；原奖励函数中的硬门槛改写成了收尾校验脚本。
- 评审和提案改成故事优先：reviewer 增加故事核查，提案增加 `story`、`pilot_guidance` 和每条预测的 `promise_signal`，`kill_condition` 只针对机制或故事。

## 致谢与许可

改编自 *IdeaScientist: Orchestrating Agents for Grounded Scientific Ideation*（<https://github.com/jiarui-liu/IdeaScientist>）。本仓库同样以 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) 发布，仅限非商业用途，详见 [LICENSE](LICENSE)。
