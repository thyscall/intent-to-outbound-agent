"""Build the shared Claude client used by all CrewAI agents.

This module constructs the chat model from environment configuration and
validates required credentials before execution. Keeping model creation
centralized ensures every stage uses the same runtime defaults.

CrewAI routes an ``anthropic/``-prefixed model to its native Anthropic provider,
which calls the official `anthropic` SDK directly rather than going through
LiteLLM. CrewAI >=1.0 rejects LangChain chat models, so this must be a
`crewai.LLM`, not a `ChatAnthropic`.
"""

from __future__ import annotations

import os
from typing import Any

# claude-3-5-sonnet retired in Oct 2025; claude-sonnet-5 is its documented
# replacement. Override with CLAUDE_MODEL (claude-opus-5 for the top tier).
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"

# Retired or non-resolving ids that would 404 at call time, mapped to the
# current equivalent so an old .env doesn't fail the run.
RETIRED_MODEL_ALIASES = {
    "claude-3-5-sonnet": "claude-sonnet-5",
    "claude-3-5-sonnet-20241022": "claude-sonnet-5",
    "claude-3-5-sonnet-20240620": "claude-sonnet-5",
    "claude-3-7-sonnet-20250219": "claude-sonnet-5",
    "claude-3-opus-20240229": "claude-opus-5",
    "claude-3-5-haiku-20241022": "claude-haiku-4-5",
}

MAX_TOKENS = 4096


def resolve_model(configured: str | None) -> str:
    """Map a configured model id onto one the API still serves."""
    model = (configured or "").strip() or DEFAULT_CLAUDE_MODEL
    return RETIRED_MODEL_ALIASES.get(model, model)


def get_claude_llm() -> Any:
    """
    Build a crewai.LLM bound to Claude, for use with Agent(llm=...).

    Requires CLAUDE_API_KEY (ANTHROPIC_API_KEY is also accepted, since that is
    what the Anthropic SDK itself reads). Optional CLAUDE_MODEL.

    Note there is deliberately no `temperature`: sampling parameters were
    removed on Claude Sonnet 5 / Opus 5 and the API rejects them with a 400.
    Steer these agents through their prompts instead.
    """
    from crewai import LLM

    api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("CLAUDE_API_KEY is not set")

    return LLM(
        model=f"anthropic/{resolve_model(os.getenv('CLAUDE_MODEL'))}",
        api_key=api_key,
        max_tokens=MAX_TOKENS,
    )
