"""Runnable AutoGen (>=0.4) demo: an assistant that drafts with Modulor.

    pip install -r requirements.txt
    export OPENAI_API_KEY=...
    python main.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from autogen_agentchat.agents import AssistantAgent
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient

from modulor_tool import DEMO_TASK, TOOL_DESCRIPTION, TOOL_NAME, modulor_run

cad_tool = FunctionTool(modulor_run, name=TOOL_NAME,
                        description=TOOL_DESCRIPTION)

agent = AssistantAgent(
    "drafter",
    model_client=OpenAIChatCompletionClient(model="gpt-4o"),
    tools=[cad_tool],
    reflect_on_tool_use=True)


async def main():
    os.makedirs("out", exist_ok=True)
    result = await agent.run(task=DEMO_TASK)
    print(result.messages[-1].content)
    print("\nartifacts: out/demo.json, out/demo_plan.png")


if __name__ == "__main__":
    asyncio.run(main())
