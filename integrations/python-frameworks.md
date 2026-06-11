# Modulor in Python agent frameworks

The kernel is callable in-process — no subprocess, no server:

```python
from modulor import Cad, CadError

def modulor_run(doc: str, commands: list[dict]) -> dict:
    """Run Modulor CAD commands against a document file."""
    cad = Cad(doc)
    try:
        results = cad.run(commands)
    except CadError as e:
        return {"ok": False, "error": e.to_dict()}
    cad.save()
    return {"ok": True, "results": results}
```

That one function is the whole integration. Ready-made tool schemas
(OpenAI function format, coarse single-tool or fine 71-tool style) are in
[tool-definitions.json](tool-definitions.json).

## LangChain / LangGraph

```python
from langchain_core.tools import tool

@tool
def cad(doc: str, commands: list[dict]) -> dict:
    """Run Modulor CAD commands (draw plans, model 3D, export DXF/GLB/IFC).
    Each command is {"op": <name>, ...params}; discover ops with
    [{"op": "help"}]."""
    return modulor_run(doc, commands)

# llm.bind_tools([cad]) / add to your LangGraph ToolNode as usual
```

## AutoGen (>=0.4)

```python
from autogen_core.tools import FunctionTool

cad_tool = FunctionTool(
    modulor_run, name="modulor_run",
    description="Run Modulor CAD commands; see {'op':'help'} for the API.")
```

## CrewAI

```python
from crewai.tools import tool

@tool("modulor_run")
def cad(doc: str, commands: list[dict]) -> dict:
    """Run Modulor CAD commands against a document file."""
    return modulor_run(doc, commands)
```

## The verification loop (do this in every framework)

After building, have the agent check its own work:

```python
cad.run([{"op": "render", "path": "check.png", "labels": True}])
# feed check.png to a multimodal model, and/or:
cad.run([{"op": "measure", "kind": "area", "select": {"tags": ["plan"]}},
         {"op": "validate"}])
```

MCP-native frameworks: just spawn `modulor mcp` (see mcp/README.md) and
you get `cad_run` / `cad_ops` / `cad_render` (image-returning) for free.
