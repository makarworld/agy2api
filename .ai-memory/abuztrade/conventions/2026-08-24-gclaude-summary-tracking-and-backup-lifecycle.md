# gclaude summary tracking and backup lifecycle

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: Interactive claude session does not exit to prompt, so tracking gclaude_summary.md file creation and stability serves as reliable completion trigger.

**内容**: Updated `/gclaude` skill completion detection: 1. On startup: copies `gclaude_summary.md` to `old_summary.md` and deletes `gclaude_summary.md`. 2. `gclaude` writes its final report to `.cursor/runs/gclaude_summary.md`. 3. Bash loop detects `gclaude_summary.md` creation and size stabilization (5 sec unchanged) or `gclaude_done.lock`, then Claude automatically reads summary and reviews diffs.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
