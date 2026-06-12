"""Runnable CrewAI demo: a drafting crew member using Modulor.

    pip install -r requirements.txt
    export OPENAI_API_KEY=...
    python main.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crewai import Agent, Crew, Task
from crewai.tools import tool

from modulor_tool import DEMO_TASK, TOOL_DESCRIPTION, modulor_run


@tool("modulor_run")
def cad(doc: str, commands: list[dict]) -> str:
    """Run Modulor CAD commands against a document file."""
    return modulor_run(doc, commands)


cad.description = TOOL_DESCRIPTION

drafter = Agent(
    role="CAD drafter",
    goal="Produce precise drawings and verify them",
    backstory="You draft with Modulor and always render to check your work.",
    tools=[cad])

if __name__ == "__main__":
    os.makedirs("out", exist_ok=True)
    crew = Crew(agents=[drafter],
                tasks=[Task(description=DEMO_TASK,
                            expected_output="the measured wall area and the "
                                            "paths of the produced files",
                            agent=drafter)])
    print(crew.kickoff())
    print("\nartifacts: out/demo.json, out/demo_plan.png")
