"""Builds the deepagents agent: an OpenRouter ChatOpenAI model + the world
tools (2–4 depending on which modules are active) + the system prompt.
interrupt_on gates place_order in step-gated mode. No fallback: a missing
OPENROUTER_API_KEY raises loudly."""

import os

from deepagents import create_deep_agent
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
    interrupt_on = {"place_order": True} if mode == "step_gated" else None
    return create_deep_agent(
        model=build_model(model_slug),
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        interrupt_on=interrupt_on,
    )
