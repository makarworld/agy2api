# delegate-gclaude skill workflow

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: User requested a flow to plan with standard Claude, execute with gclaude, and review back in standard Claude.

**内容**: Created skill `delegate-gclaude` at `C:\Users\User\.claude\skills\delegate-gclaude\SKILL.md`. Workflow: Claude creates plan -> runs `C:\Users\User\bin\gclaude -p ... --dangerously-skip-permissions` -> receives summary -> Claude reviews git diff, runs verifications, updates plan.

**影响**: Global Claude skills configuration, available across all projects.
