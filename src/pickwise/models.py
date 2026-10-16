"""Data shapes shared across the agent, report and tracker."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Pick(BaseModel):
    """The agent's final answer for the day."""

    ticker: str
    company: str
    headline: str = Field(description="One sentence a busy reader can act on.")
    conviction: Literal["low", "medium", "high"]
    horizon: str = Field(description='Expected holding window, e.g. "1-3 months".')
    thesis: list[str] = Field(description="Three to five bullet points making the case.")
    catalysts: list[str]
    risks: list[str]
    why_not_runner_up: str = Field(description="Why this beat the second-best candidate.")
    runner_up: str
    sources: list[str] = Field(default_factory=list, description="URLs consulted.")


class PickRecord(BaseModel):
    """What gets persisted to picks/history.json for performance tracking."""

    date: str
    ticker: str
    company: str
    conviction: str
    entry_price: float
    benchmark_entry_price: float
    model: str


# JSON schema for the terminal `submit_pick` tool. Kept explicit (rather than generated
# from the pydantic model) because strict tool use requires additionalProperties: false.
SUBMIT_PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "description": "Must be one of the shortlisted tickers."},
        "company": {"type": "string"},
        "headline": {"type": "string"},
        "conviction": {"type": "string", "enum": ["low", "medium", "high"]},
        "horizon": {"type": "string"},
        "thesis": {"type": "array", "items": {"type": "string"}},
        "catalysts": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "why_not_runner_up": {"type": "string"},
        "runner_up": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "ticker", "company", "headline", "conviction", "horizon", "thesis",
        "catalysts", "risks", "why_not_runner_up", "runner_up", "sources",
    ],
    "additionalProperties": False,
}
