# gclaude explicit write and powershell start-process

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: Bash heredoc cat failed or had path escaping issues with forward slashes in Windows Terminal.

**内容**: Updated `/gclaude` skill in `C:\Users\User\.claude\skills\gclaude\SKILL.md`: `.bat` file is written explicitly via `Write` tool to `<PROJECT_ROOT>\.cursor\runs\run_gclaude.bat`, and launched via `powershell.exe -NoProfile -Command "Start-Process wt.exe -ArgumentList '-w', '0', 'new-tab', '--title', 'GClaude', '--tabColor', '#0078D7', '-d', '<PROJECT_ROOT>', 'cmd.exe', '/k', '<PROJECT_ROOT>\.cursor\runs\run_gclaude.bat'"`. All Windows paths in ArgumentList use backslashes.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
