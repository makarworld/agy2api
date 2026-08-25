# gclaude auto-wait completion marker

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: User requested Claude to automatically await process completion instead of waiting for a manual user signal to review.

**内容**: Added Auto-Wait Completion to `/gclaude` skill: `.bat` creates `.cursor/runs/gclaude_done.lock` on exit, and Claude runs `wt.exe ... && while [ ! -f ...gclaude_done.lock ]; do sleep 2; done`. When gclaude finishes in WT tab, Claude immediately transitions to Step 3 (review, git diff, ruff, todos update) automatically without manual user input.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
