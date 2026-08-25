# gclaude WT launch via PowerShell Start-Process

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: Confirmed that PowerShell Start-Process correctly passes args to WT and opens the active tab running the bat file.

**内容**: Finalized WT tab launch command in `C:\Users\User\.claude\skills\gclaude\SKILL.md`: uses `powershell.exe -Command "Start-Process wt.exe -ArgumentList '-w', '0', 'new-tab', '-d', '<PROJECT_ROOT>', 'cmd.exe', '/k', '<PROJECT_ROOT>\.cursor\runs\run_gclaude.bat'"` with absolute paths.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
