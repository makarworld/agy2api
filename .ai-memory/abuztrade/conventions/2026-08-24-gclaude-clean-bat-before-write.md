# gclaude clean bat before write

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: Fixed Write tool throwing 'Error writing file' when overwriting an unread existing bat file.

**内容**: Updated `/gclaude` skill: `run_gclaude.bat` and `gclaude_done.lock` are always deleted on startup before calling `Write` tool to prevent overwrite errors.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
