# gclaude skip plan creation if path provided

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: User pointed out unnecessary plan recreation when an existing plan path is already provided.

**内容**: Updated `/gclaude` skill: if the user passes an existing plan file path (e.g. `C:\Users\User\.claude\plans\*.md` or `.cursor/plans/*.md`) with intent to execute/delegate, immediately skip plan generation and dispatch the existing plan path to `gclaude` in WT new tab.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
