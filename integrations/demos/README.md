# Runnable framework demos

Three self-contained projects, one per framework. Each runs the same
brief — *"draw a 6m×4m room with a door, measure it, render a labeled
plan"* — through a real LLM with Modulor as the only tool.

| demo | install | needs |
|---|---|---|
| [langchain/](langchain/) (LangGraph ReAct) | `pip install -r langchain/requirements.txt` | `ANTHROPIC_API_KEY` |
| [autogen/](autogen/) (AutoGen ≥0.4) | `pip install -r autogen/requirements.txt` | `OPENAI_API_KEY` |
| [crewai/](crewai/) | `pip install -r crewai/requirements.txt` | `OPENAI_API_KEY` |

All three import the same ~50-line adapter,
[`modulor_tool.py`](modulor_tool.py) — that file is unit-tested in
Modulor's CI (the demos are additionally compile-checked), so the
foundation cannot rot. The framework SDKs and a live LLM key are the only
parts CI cannot exercise for you.

Outputs land in `out/`: the document, and `demo_plan.png` — look at it;
that is the point of an agent-native CAD.
