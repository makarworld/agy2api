# gclaude bat direct env vars

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: Direct env vars in bat ensure claude CLI uses the local proxy with max-gem model cleanly without settings collisions.

**内容**: Updated `/gclaude` skill bat template: sets `ANTHROPIC_BASE_URL=http://127.0.0.1:26767/anthropic`, `ANTHROPIC_API_KEY=sk-my-super-secret-key-123`, `ANTHROPIC_MODEL=max-gem` directly in the `.bat` file before invoking `claude -p "..." --dangerously-skip-permissions`.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
