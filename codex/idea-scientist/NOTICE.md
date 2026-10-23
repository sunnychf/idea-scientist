# Notice

This skill is adapted from IdeaScientist (https://github.com/jiarui-liu/IdeaScientist), licensed under
CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/). Non-commercial use only.

Changes from the original: the role, orchestrator and rubric prompts were translated into Chinese and condensed
into Codex skill instructions; retrieval over the Svalbard Idea Vault was replaced by the arXiv and Semantic
Scholar public APIs (scripts/paper.py) and web search; the reward's hard gates were reimplemented as a run
validator (scripts/check_run.py); review and proposal were made story-first (a story check in review; `story`,
`pilot_guidance` and per-prediction `promise_signal` fields; kill conditions target the mechanism or the story,
not whether a pilot beats SOTA); audit- and fidelity-type ideas are excluded (references/idea-constraints.md);
no trained weights are included.
