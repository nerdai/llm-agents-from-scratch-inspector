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

    export OLLAMA_API_KEY=<your key>
    uv run agent-inspector launch demo.py

The LLM comes from `make_llm()`, the same helper the
`llm-agents-from-scratch` chapter notebooks use. Export
`OLLAMA_API_KEY` (create one at https://ollama.com/settings/keys) to
run on Ollama Cloud, which is recommended -- no local `ollama serve`
needed. Without a key it falls back to a local Ollama with `qwen3:14b`
(`ollama pull qwen3:14b`), starting the service if needed.
`LLM_PROVIDER=openai` or `anthropic` switches provider, as in the
notebooks (those need the library's `openai`/`anthropic` extras).

Deliberately doesn't wire up the notebook's `stop-at-one` skill (its
own `run_supervised(..., explicit_only_skills=["stop-at-one"])` call
hides the skill from the model's visible catalog -- something only
settable per-request, not from an `agent_builder` script, per ADR-002)
-- a discoverable-but-visible skill measurably destabilizes smaller/
quantized models like `qwen3:14b` here (extra tool-catalog complexity
gives it more surface to stumble on), so this Quickstart stays with
just the one tool for a reliably smooth first run.
"""

from llm_agents_from_scratch import LLMAgentBuilder
from llm_agents_from_scratch.data_structures import Task
from llm_agents_from_scratch.notebook_utils import make_llm
from llm_agents_from_scratch.tools import SimpleFunctionTool


def next_number(x: int) -> int:
    """Compute the next number in the Hailstone sequence from x."""
    if x % 2 == 0:
        return x // 2
    return 3 * x + 1


next_number_tool = SimpleFunctionTool(func=next_number)

agent_builder = (
    LLMAgentBuilder().with_llm(make_llm()).with_tool(next_number_tool)
)

# Optional (see #86 / discovery.py): pre-fills the UI's task field at
# launch time instead of the frontend hardcoding this Quickstart's own
# example task.
default_task = Task(
    instruction=(
        "Compute the full Hailstone sequence starting from 4, step by "
        "step using next_number, until you reach 1."
    ),
)
