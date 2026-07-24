"""Agent Inspector quickstart demo -- Ollama Cloud variant.

Same Hailstone-sequence agent as `demo.py`, but pointed at Ollama
Cloud instead of a local daemon (see `llm-agents-from-scratch`'s
`examples/ch07.ipynb`, Example 4's `use_cloud` pattern) -- a script
for exercising/testing #90's cloud-vs-local detection
(`GET /api/agent-info`'s `ollama_host`/`is_local_ollama`, surfaced in
the app bar as an "ollama cloud" chip instead of the local daemon's
online/offline check).

Run with:

    export OLLAMA_API_KEY=<your key>
    uv run agent-inspector launch demo_cloud.py

No local `ollama serve` needed -- authentication is handled entirely
by the `ollama` package itself, which reads `OLLAMA_API_KEY` from the
environment (see `ollama._client.BaseClient.__init__`); nothing here
passes a key explicitly. Get one at https://ollama.com/settings/keys.

Doesn't pass `json_prompt_mode=True` the way `ch07.ipynb` does for
cloud reliability -- that parameter isn't in the version of
`llm-agents-from-scratch` this project currently depends on
(`>=0.0.19,<0.1.0`; added to the framework's own unreleased `main`
after 0.0.20). Worth adding here once a release with it ships.
"""

from llm_agents_from_scratch import LLMAgentBuilder
from llm_agents_from_scratch.data_structures import Task
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
        OllamaLLM(host="https://ollama.com", model="qwen3.5:397b-cloud"),
    )
    .with_tool(next_number_tool)
)

default_task = Task(
    instruction=(
        "Compute the full Hailstone sequence starting from 4, step by "
        "step using next_number, until you reach 1."
    ),
)
