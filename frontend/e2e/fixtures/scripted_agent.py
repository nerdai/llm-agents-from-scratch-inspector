"""``agent_builder`` entrypoint for the Playwright E2E suite (issue #62).

Started by ``frontend/playwright.config.ts``'s ``webServer`` as
``agent-inspector launch frontend/e2e/fixtures/scripted_agent.py --dev
--no-open --port <PORT>`` (see ADR-002 / ``docs/overview.md``'s
"Entrypoint discovery" section for the ``agent_builder`` convention
itself). Modeled on ``demo.py`` (same Hailstone-from-4 example, same
single ``next_number`` tool) but swaps ``OllamaLLM`` for a scripted,
network-free ``BaseLLM`` double so the whole suite runs in CI with no
live Ollama daemon -- mirroring ``tests/test_integration_loop.py``'s
``_SequencedLLM`` pattern.

This can't reuse ``_SequencedLLM`` as-is, though. That class plays back
a *finite, consumed* call queue -- perfect for the one linear test it
serves. This LLM instead backs the *entire* Playwright suite: many
independent spec files, each creating its own session, all against one
long-lived backend process. ``LLMAgentBuilder.build()`` (see
``agent/builder.py``) reuses the same ``llm`` instance across every
``.build()`` call -- one real ``LLMAgent`` per session, but all of them
sharing this one LLM object -- so a consumed queue would work for
exactly one test session and then silently break (or raise
``IndexError``) for every session after it.

Instead, ``_StatelessHailstoneLLM`` below derives its answer *purely*
from whatever's already in the arguments of the specific call it just
received -- no instance-level mutable state at all -- so it's safe to
reuse for any number of sessions, run in any order, indefinitely. The
convention that makes this possible: every step *instruction* this LLM
is ever asked to act on embeds a literal ``x=<N>`` for the next
``next_number(x)`` call (the fixed task text every spec file uses, or
an edited instruction a test substitutes via the "edit step" UI), and
every step *result* it ever reports back is just the resulting number,
as a bare string (so the *next* ``get_next_step()`` routing call can
read it back out just as mechanically). That keeps both directions of
the loop parseable from call content alone:

* ``structured_output()`` (the ``get_next_step()`` routing decision)
  reads the previous step's result back out of the prompt's
  ``<current-response>`` block (see the framework's own
  ``DEFAULT_GET_NEXT_INSTRUCTION_PROMPT``) and decides ``final_result``
  once that value is exactly ``"1"`` -- the Hailstone sequence's fixed
  point -- or once it isn't a bare integer at all (e.g. the
  acknowledgement text this LLM itself returns for a post-rejection
  step, which has no ``x=<N>`` to act on -- see ``chat()`` below), so
  the suite's reject-path tests can't ever spin this LLM into an
  infinite loop.
* ``chat()``/``continue_chat_with_tool_results()`` (the ``run_step()``
  turn) reads ``x=<N>`` out of the step instruction it's handed, calls
  the *real* ``next_number`` tool (a real Python function call, not
  scripted -- same as ``_SequencedLLM``'s own tool execution), and
  reports back its real return value verbatim.
"""

from __future__ import annotations

import re
from typing import Any, Sequence, cast

from llm_agents_from_scratch import LLMAgentBuilder
from llm_agents_from_scratch.base.llm import BaseLLM, StructuredOutputType
from llm_agents_from_scratch.base.tool import Tool
from llm_agents_from_scratch.data_structures import (
    ChatMessage,
    ChatRole,
    CompleteResult,
    NextStepDecision,
    Task,
    ToolCall,
    ToolCallResult,
)
from llm_agents_from_scratch.tools import SimpleFunctionTool

# Matches the literal `x=<N>` convention every step instruction in this
# suite's tasks (and every "next step" this LLM itself proposes) is
# expected to carry. The first match is always the intended one --
# every instruction this fixture ever produces or expects to be
# handed contains exactly one.
_X_PATTERN = re.compile(r"x\s*=\s*(-?\d+)")

# Matches the framework's own `<current-response>...</current-response>`
# wrapper from `DEFAULT_GET_NEXT_INSTRUCTION_PROMPT` -- reading the
# previous step's result back out of the *rendered prompt* rather than
# threading it through separately, since `structured_output()` only
# ever receives the one rendered `prompt` string.
_CURRENT_RESPONSE_PATTERN = re.compile(
    r"<current-response>\s*(.*?)\s*</current-response>",
    re.DOTALL,
)


def next_number(x: int) -> int:
    """Compute the next number in the Hailstone sequence from x.

    Verbatim copy of the same step function used by ``demo.py`` and
    ``tests/test_integration_loop.py`` -- kept duplicated rather than
    imported, same as those two, since it's the tool's whole
    definition, not shared library code.
    """
    if x % 2 == 0:
        return x // 2
    return 3 * x + 1


class _StatelessHailstoneLLM(BaseLLM):
    """A scripted, network-free, stateless ``BaseLLM`` double.

    See this module's docstring for why "stateless" (as opposed to
    ``_SequencedLLM``'s consumed-queue script) matters here.

    ``model`` is a real attribute (not just inherited absence) so
    ``agent-info.spec.ts`` can assert on ``GET /api/agent-info``'s
    ``model`` actually surfacing something, same as a real
    ``OllamaLLM``.
    """

    model: str = "scripted-test-llm"

    async def complete(self, prompt: str, **kwargs: Any) -> CompleteResult:
        """Unused on this suite's path; provided to satisfy BaseLLM."""
        raise NotImplementedError

    async def structured_output(
        self,
        prompt: str,
        mdl: type[StructuredOutputType],
        **kwargs: Any,
    ) -> StructuredOutputType:
        """Decide `next_step` vs. `final_result` from the rendered prompt.

        Reads the previous step's result back out of the prompt's
        ``<current-response>`` block: ``"1"`` (the Hailstone fixed
        point) or anything non-numeric (e.g. this LLM's own
        acknowledgement text after a rejection, which has nothing
        further to compute) ends the loop; any other integer continues
        it with a fresh ``x=<N>`` instruction for ``run_step()``.
        """
        match = _CURRENT_RESPONSE_PATTERN.search(prompt)
        current_response = match.group(1).strip() if match else ""
        try:
            x = int(current_response)
        except ValueError:
            return cast(
                StructuredOutputType,
                NextStepDecision(kind="final_result", content=""),
            )
        if x == 1:
            return cast(
                StructuredOutputType,
                NextStepDecision(kind="final_result", content=""),
            )
        return cast(
            StructuredOutputType,
            NextStepDecision(
                kind="next_step",
                content=f"Call next_number with x={x}.",
            ),
        )

    async def chat(
        self,
        input: str,
        chat_history: Sequence[ChatMessage] | None = None,
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[ChatMessage, ChatMessage]:
        """Call ``next_number`` with whatever ``x=<N>`` is in ``input``.

        ``input`` is the step instruction verbatim (the framework's
        ``run_step_user_message`` template is just ``"{instruction}"``)
        -- either the task's own instruction (the deterministic first
        step), a previous decision's ``content`` (this LLM's own
        ``f"Call next_number with x={x}."``), or an operator's edited
        instruction from the UI's "edit step" affordance. When no
        ``x=<N>`` is present at all -- the one case this suite
        exercises is the framework's own post-rejection instruction
        (``approval_rejection_feedback``, which has no such pattern) --
        there's nothing to call; acknowledge instead of guessing.
        """
        match = _X_PATTERN.search(input)
        if match is None:
            return (
                ChatMessage(role=ChatRole.USER, content=input),
                ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content="Acknowledged operator feedback.",
                    tool_calls=None,
                ),
            )
        x = int(match.group(1))
        tool_call = ToolCall(tool_name="next_number", arguments={"x": x})
        return (
            ChatMessage(role=ChatRole.USER, content=input),
            ChatMessage(
                role=ChatRole.ASSISTANT,
                content=f"Calling next_number with x={x}.",
                tool_calls=[tool_call],
            ),
        )

    async def continue_chat_with_tool_results(
        self,
        tool_call_results: Sequence[ToolCallResult],
        chat_history: Sequence[ChatMessage],
        tools: Sequence[Tool] | None = None,
        **kwargs: Any,
    ) -> tuple[list[ChatMessage], ChatMessage]:
        """Report the real tool result back verbatim, as a bare string.

        The bare-string convention is what lets the *next*
        ``structured_output()`` call read it straight back out of
        ``<current-response>`` -- see that method's docstring.
        """
        final_content = (
            str(tool_call_results[0].content) if tool_call_results else ""
        )
        return (
            [
                ChatMessage(role=ChatRole.TOOL, content=str(r.content))
                for r in tool_call_results
            ],
            ChatMessage(role=ChatRole.ASSISTANT, content=final_content),
        )


next_number_tool = SimpleFunctionTool(func=next_number)

agent_builder = (
    LLMAgentBuilder()
    .with_llm(_StatelessHailstoneLLM())
    .with_tool(next_number_tool)
)

# Matches `helpers.ts`'s `hailstoneTask(4)` exactly, so
# `agent-info.spec.ts` can assert the pre-session task field really
# came from this (#86), not a hardcoded frontend fallback -- while
# every other spec still overrides it via `createSession(page, task)`
# before submitting, so this has no effect on them.
default_task = Task(
    instruction="Compute next_number starting from x=4 until you reach 1.",
)
