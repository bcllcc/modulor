# Integrations — plug Modulor into your agent

Pick your runtime; everything here is copy-paste ready.

**One-command installs**

| runtime | install |
|---|---|
| **Claude Code (plugin)** | `/plugin marketplace add bcllcc/modulor` → `/plugin install modulor@modulor` — skill + MCP server in one step (manifests run through `claude plugin validate` in CI; versions pinned to the package by tests) |
| **Any MCP client** (Claude Desktop, registry clients) | listed on the official MCP registry as `io.github.bcllcc/modulor`; manual config in [mcp/README.md](mcp/README.md) |

**Copy-in artifacts** (these ecosystems have no install channel — by design)

| runtime | artifact |
|---|---|
| Claude Code (manual skill) | [claude-code/modulor/SKILL.md](claude-code/modulor/SKILL.md) — copy into `.claude/skills/` |
| Cursor | [cursor/modulor.mdc](cursor/modulor.mdc) — drop into `.cursor/rules/` |
| Codex / AGENTS.md agents | [codex/AGENTS-snippet.md](codex/AGENTS-snippet.md) — append to your `AGENTS.md` |
| GPT / Kimi / Qwen / DeepSeek (function calling) | [tool-definitions.json](tool-definitions.json) — generated OpenAI-format tools; usage in [zh-cn.md](zh-cn.md) |
| 国内模型接入（中文） | [zh-cn.md](zh-cn.md) |

**Runnable demo projects** — [demos/](demos/): LangChain/LangGraph,
AutoGen and CrewAI projects sharing one CI-tested adapter
([demos/modulor_tool.py](demos/modulor_tool.py)); snippets reference:
[python-frameworks.md](python-frameworks.md).

> Status note: the official MCP registry listing is **live and
> auto-published** on every release. Smithery: `smithery.yaml` is
> prepared but the listing awaits a one-time claim on smithery.ai by the
> repository owner.

Then teach your agent the patterns: [COOKBOOK.md](COOKBOOK.md) — eight
battle-tested recipes from floor plans to IFC handoff.

`tool-definitions.json` is generated from the live op registry
(`python scripts/export_tool_defs.py`) and always matches the API
contract.
