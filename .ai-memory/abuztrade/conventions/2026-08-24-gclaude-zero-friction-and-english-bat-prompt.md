# gclaude zero friction and english bat prompt

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: cmd.exe corrupted Cyrillic text in .bat causing syntax error, and Claude spent 1m15s overthinking before firing the tab.

**内容**: Fixed two issues in `/gclaude` skill (`C:\Users\User\.claude\skills\gclaude\SKILL.md`): 1. Fixed cmd.exe UTF-8 corruption (`'ана:' is not recognized`) by writing the `-p` prompt in English single-line syntax. 2. Added Zero-Friction rule: if plan path is passed, do zero unnecessary read/existence checks or cogitations—immediately write `.bat` and fire WT tab in one action.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
