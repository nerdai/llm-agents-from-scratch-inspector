"""Agent Inspector quickstart demo.

An `agent_builder` entrypoint script for `agent-inspector launch` (see
ADR-002 and `docs/overview.md`'s "Entrypoint discovery" section). Ports
Example 3 ("Caller-Driven Stepwise Execution with run_supervised()")
from `llm-agents-from-scratch`'s `examples/ch08.ipynb`: a Hailstone-
sequence agent equipped with a single `next_number` tool, driven one
`get_next_step()`/`run_step()` call at a time instead of the
notebook's own manual loop -- which is exactly what this Inspector's
UI does for you.

Run with:

    uv run agent-inspector launch demo.py

Requires a running Ollama daemon (`ollama serve`) with the
`qwen3:14b` model pulled (`ollama pull qwen3:14b`) -- or edit the
`OllamaLLM(...)` call below to point at a model you already have.

The `stop-at-one` skill this script's directory ships in
`.agents/skills/stop-at-one/` (same skill Example 3 uses) is
auto-discovered from the current working directory -- run the command
above from this repo's root so it's found.
"""

from llm_agents_from_scratch import LLMAgentBuilder
from llm_agents_from_scratch.llms import OllamaLLM
from llm_agents_from_scratch.tools import SimpleFunctionTool


def next_number(x: int) -> int:
    """Compute the next number in the Hailstone sequence from x."""
    if x % 2 == 0:
        return x // 2
    return 3 * x + 1


next_number_tool = SimpleFunctionTool(func=next_number)

agent_builder = (
    LLMAgentBuilder()
    .with_llm(
        OllamaLLM(model="qwen3:14b", think=False),
    )
    .with_tool(next_number_tool)
)
