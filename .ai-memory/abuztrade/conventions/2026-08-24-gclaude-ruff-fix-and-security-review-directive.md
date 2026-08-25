# gclaude ruff fix and security review directive

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: User requested gclaude to handle ruff checks + fixes and security review itself before finishing.

**内容**: Added ruff auto-fix and `/security-review` requirements to `gclaude` worker prompt in `C:\Users\User\.claude\skills\gclaude\SKILL.md`: `gclaude` runs plan, runs ruff check and fixes issues, runs `/security-review` on changes, runs tests, and outputs summary before creating `gclaude_done.lock`.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
