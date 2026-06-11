# Integrations — plug Modulor into your agent

Pick your runtime; everything here is copy-paste ready.

| runtime | artifact |
|---|---|
| **Claude Code** | [claude-code/modulor/SKILL.md](claude-code/modulor/SKILL.md) — copy the `modulor/` folder into `.claude/skills/` (project) or `~/.claude/skills/` (global); or just add the MCP server below |
| **Any MCP client** (Claude Desktop, etc.) | [mcp/README.md](mcp/README.md) — `modulor mcp`, stdio, zero config |
| **Cursor** | [cursor/modulor.mdc](cursor/modulor.mdc) — drop into `.cursor/rules/` |
| **Codex / AGENTS.md agents** | [codex/AGENTS-snippet.md](codex/AGENTS-snippet.md) — append to your `AGENTS.md` |
| **GPT / Kimi / Qwen / DeepSeek** (function calling) | [tool-definitions.json](tool-definitions.json) — generated OpenAI-format tools; usage in [zh-cn.md](zh-cn.md) |
| **LangChain / LangGraph / AutoGen / CrewAI** | [python-frameworks.md](python-frameworks.md) — one function is the whole integration |
| **国内模型接入（中文）** | [zh-cn.md](zh-cn.md) |

Then teach your agent the patterns: [COOKBOOK.md](COOKBOOK.md) — eight
battle-tested recipes from floor plans to IFC handoff.

`tool-definitions.json` is generated from the live op registry
(`python scripts/export_tool_defs.py`) and always matches the API
contract.
