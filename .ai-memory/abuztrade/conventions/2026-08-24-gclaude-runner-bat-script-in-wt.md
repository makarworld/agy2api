# gclaude runner bat script in WT

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: Command was not executing in new WT tab due to Windows CLI quote escaping.

**内容**: Fixed WT tab dispatch in `/gclaude` skill: creates `.cursor/runs/run_gclaude.bat` with UTF-8 (`chcp 65001`), runs `C:\Users\User\bin\gclaude` with `--dangerously-skip-permissions`, and launches via `wt.exe -w 0 new-tab -d "." cmd.exe /c ".cursor\runs\run_gclaude.bat"`.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
