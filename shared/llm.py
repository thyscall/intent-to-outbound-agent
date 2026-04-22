"""Build the shared Gemini client used by all CrewAI agents.

This module constructs a LangChain-compatible chat model from environment
configuration and validates required credentials before execution. Keeping
model creation centralized ensures every stage uses the same runtime defaults.
"""

from __future__ import annotations

import os
from typing import Any


def get_gemini_llm() -> Any:
    """
    Build a ChatGoogleGenerativeAI instance for use with CrewAI Agent(llm=...).

    Requires GEMINI_API_KEY. Optional GEMINI_MODEL (default: gemini-2.0-flash).
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=0.7,
    )
