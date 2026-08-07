"""Builds the agent: an OpenRouter ChatOpenAI model + the world tools
(2-4 depending on which modules are active) + the system prompt, wired
through plain `langchain.agents.create_agent` -- no framework middleware,
no injected tools, the prompt goes to the model verbatim. (The July 2026
ladder-v1 runs used deepagents, which silently added write_todos/file/
execute/task tools and appended its own scaffold prompt -- DEFECTS.md D15.
deepagents was removed 2026-08-06; reproducing those runs needs the
pre-removal checkout.) Step-gated mode gates place_order via langchain's
own HumanInTheLoopMiddleware -- the same middleware deepagents delegated
to, so the interrupt/resume payload shapes are unchanged. No fallback: a
missing OPENROUTER_API_KEY raises loudly."""

import os

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_openai import ChatOpenAI

from .prompt import SYSTEM_PROMPT


def build_model(model_slug: str) -> ChatOpenAI:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set in the server environment; "
            "export it before starting uvicorn (no fallback provider).")
    return ChatOpenAI(
        model=model_slug,
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        temperature=0,
        streaming=True,
        # ponytail: OpenAI caches automatically; Anthropic needs this top-level
        # flag (auto-advancing breakpoint, cache reads billed at 0.1x)
        extra_body=({"cache_control": {"type": "ephemeral"}}
                    if model_slug.startswith("anthropic/") else None),
    )


def build_agent(model_slug: str, mode: str, tools, checkpointer,
                system_prompt: str = SYSTEM_PROMPT):
    """mode = "autonomous" | "step_gated". Step-gated interrupts before
    place_order so a human approves each order; autonomous runs straight.
    system_prompt defaults to the base prompt; the masked task passes
    prompt.build_system_prompt(world) so any caller not yet updated is
    unchanged."""
    if mode not in ("autonomous", "step_gated"):
        raise ValueError(f"unknown mode {mode!r}")
    middleware = ([HumanInTheLoopMiddleware(interrupt_on={"place_order": True})]
                  if mode == "step_gated" else [])
    return create_agent(
        model=build_model(model_slug),
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
        checkpointer=checkpointer,
    )
