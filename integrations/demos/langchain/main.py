"""Runnable LangChain/LangGraph demo: an agent that drafts with Modulor.

    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...   (or use any chat model you prefer)
    python main.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain.chat_models import init_chat_model
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

from modulor_tool import (DEMO_TASK, TOOL_DESCRIPTION, TOOL_NAME,
                          modulor_run)

cad_tool = StructuredTool.from_function(
    func=modulor_run, name=TOOL_NAME, description=TOOL_DESCRIPTION)

agent = create_react_agent(
    init_chat_model("anthropic:claude-sonnet-4-6"), tools=[cad_tool])

if __name__ == "__main__":
    os.makedirs("out", exist_ok=True)
    state = agent.invoke({"messages": [("user", DEMO_TASK)]})
    print(state["messages"][-1].content)
    print("\nartifacts: out/demo.json, out/demo_plan.png")
