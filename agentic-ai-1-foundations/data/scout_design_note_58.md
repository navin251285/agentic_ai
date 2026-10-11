# Scout design note: decisions from case studies

## 1. How we built our multi-agent research system (Anthropic)
- Source (engineering write-up, 2025-06-13): https://www.anthropic.com/engineering/multi-agent-research-system
- Decision (2026-10-09): Scout stays one agent. Consider sub-agents only for a class of questions the single agent fails on the eval, and price them at ~15x a chat first.
- Check: `check_a` -> holds

## 2. A postmortem of three recent issues (Anthropic)
- Source (post-mortem, 2025-09-17): https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues
- Decision (2026-10-09): Run 20 golden cases against production Scout every hour and alert on any failure; track the thumbs-down rate for breaks too small for the canary.
- Check: `check_b` -> holds

## 3. Replit agent deletes a production database during a code freeze
- Source (press report of an incident, 2025-07-22): https://www.eweek.com/news/replit-ai-coding-assistant-failure/
- Decision (2026-10-09): A freeze is the `answer` task, set in code, never a prompt line. Every overwrite keeps the previous version, and restore is one call.
- Check: `check_c` -> holds
