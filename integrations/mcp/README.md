# Modulor as an MCP server

`modulor mcp` serves the Model Context Protocol over stdio with three
tools: `cad_run` (execute op batches), `cad_ops` (discover the API),
`cad_render` (returns a PNG **image** the model can look at).

## Claude Code

```bash
claude mcp add modulor -- modulor mcp
```

or in `.mcp.json` / `~/.claude.json`:

```json
{"mcpServers": {"modulor": {"command": "modulor", "args": ["mcp"]}}}
```

## Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "modulor": {"command": "modulor", "args": ["mcp"]}
  }
}
```

## Any other MCP client

Transport: stdio, newline-delimited JSON-RPC 2.0. Command: `modulor mcp`
(requires `pip install modulor`, Python ≥ 3.10). No environment variables,
no network, no credentials — documents are plain files at the paths you
pass in tool arguments.

## Typical session

1. `cad_ops` once to see the catalog (or trust the tool description).
2. `cad_run` with `{"doc": "model.json", "commands": [...]}`.
3. `cad_render` with `{"doc": "model.json", "camera": "iso"}` — look at
   the returned image, then iterate with more `cad_run` calls.
