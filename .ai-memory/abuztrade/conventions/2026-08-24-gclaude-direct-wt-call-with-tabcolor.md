# gclaude direct wt call with tabColor

> **日期**: 2026-08-24  
> **作者**: abuztrade  
> **来源**: cursor:mcp  
> **对话**: MCP remember

---

**上下文**: PowerShell ArgumentList split 'GClaude: Execution' into separate tokens breaking WT command parser.

**内容**: Fixed WT argument syntax in `C:\Users\User\.claude\skills\gclaude\SKILL.md`: direct `wt.exe -w 0 new-tab --title "GClaude" --tabColor "#0078D7" -d "<PROJECT_ROOT>" cmd.exe /k "<PROJECT_ROOT>\.cursor\runs\run_gclaude.bat"` without PowerShell ArgumentList splitting that caused 0x80070002 file not found errors.

**影响**: C:\Users\User\.claude\skills\gclaude\SKILL.md
