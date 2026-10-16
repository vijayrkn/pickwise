"""Tools the research agent can call.

Every tool reads from data that was already fetched for the screen (or a cached fundamentals
lookup), so a research session is cheap, fast and reproducible.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from .models import SUBMIT_PICK_SCHEMA, Pick, PickRecord
from .universe import BENCHMARK, sector_of

WEB_SEARCH_MAX_USES = 6

TOOL_DEFINITIONS = [
    {
        "name": "get_fundamentals",
        "description": (
            "Valuation, profitability, growth, balance-sheet and analyst-consensus fields for a "
            "ticker. Fields are null when the data provider has no value. debt_to_equity is in "
            "percent; growth and margin fields are fractions (0.12 = 12%)."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_price_action",
        "description": (
            "Trailing returns (1w to 1y), distance from 52-week high/low, moving averages, RSI "
            "and 3-month performance relative to the S&P 500 for a ticker."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_pick_history",
        "description": (
            "Previous picks with their return and alpha versus the S&P 500 so far. Use it to "
            "avoid repeating recent picks and to stay honest about what has and hasn't worked."
        ),
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "submit_pick",
        "description": (
            "Submit today's single pick. Call exactly once, after research is complete. The "
            "ticker must come from the shortlist."
        ),
        "strict": True,
        "input_schema": SUBMIT_PICK_SCHEMA,
    },
    {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": WEB_SEARCH_MAX_USES,
    },
]


def _round(value, ndigits: int = 4):
    return round(float(value), ndigits) if value is not None and pd.notna(value) else None


@dataclass
class Toolbox:
    closes: pd.DataFrame
    candidates: pd.DataFrame
    history: list[PickRecord]
    fundamentals_fn: Callable[[str], dict]
    submitted: Pick | None = field(default=None, init=False)

    def run(self, name: str, args: dict) -> tuple[str, bool]:
        """Execute a tool call. Returns (content, is_error)."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"Unknown tool: {name}", True
        try:
            return handler(**args), False
        except ValueError as exc:
            return str(exc), True

    def _check_ticker(self, ticker: str) -> str:
        ticker = ticker.upper().strip()
        if ticker not in self.closes.columns:
            raise ValueError(f"{ticker} is not in the screened universe.")
        return ticker

    def _tool_get_fundamentals(self, ticker: str) -> str:
        ticker = self._check_ticker(ticker)
        return json.dumps(self.fundamentals_fn(ticker), default=str)

    def _tool_get_price_action(self, ticker: str) -> str:
        ticker = self._check_ticker(ticker)
        s = self.closes[ticker].dropna()
        last = s.iloc[-1]
        window = s.iloc[-252:]

        def ret(days: int):
            return _round(last / s.iloc[-days - 1] - 1) if len(s) > days else None

        bench = self.closes.get(BENCHMARK)
        rel_3m = None
        if bench is not None and len(s) > 63:
            rel_3m = _round((last / s.iloc[-64]) - (bench.iloc[-1] / bench.iloc[-64]))
        row = self.candidates.loc[ticker] if ticker in self.candidates.index else None
        return json.dumps({
            "ticker": ticker,
            "sector": sector_of(ticker),
            "as_of": s.index[-1].strftime("%Y-%m-%d"),
            "price": _round(last, 2),
            "returns": {"1w": ret(5), "1m": ret(21), "3m": ret(63), "6m": ret(126), "1y": ret(251)},
            "relative_to_spy_3m": rel_3m,
            "high_52w": _round(window.max(), 2),
            "low_52w": _round(window.min(), 2),
            "pct_from_52w_high": _round(last / window.max() - 1),
            "sma_50": _round(s.iloc[-50:].mean(), 2),
            "sma_200": _round(s.iloc[-200:].mean(), 2),
            "rsi_14": _round(row["rsi_14"], 1) if row is not None else None,
            "annualised_volatility_3m": _round(row["volatility"]) if row is not None else None,
        })

    def _tool_get_pick_history(self) -> str:
        if not self.history:
            return "No previous picks yet - this is the first one."
        prices = {c: float(self.closes[c].dropna().iloc[-1]) for c in self.closes.columns}
        rows = []
        for r in self.history[-15:]:
            now, bench = prices.get(r.ticker), prices.get(BENCHMARK)
            rows.append({
                "date": r.date,
                "ticker": r.ticker,
                "conviction": r.conviction,
                "return": _round(now / r.entry_price - 1) if now else None,
                "alpha_vs_spy": _round(
                    (now / r.entry_price) - (bench / r.benchmark_entry_price)
                ) if now and bench else None,
            })
        return json.dumps(rows)

    def _tool_submit_pick(self, **fields) -> str:
        pick = Pick(**fields)
        pick.ticker = pick.ticker.upper().strip()
        if pick.ticker not in self.candidates.index:
            allowed = ", ".join(self.candidates.index)
            raise ValueError(f"{pick.ticker} is not on today's shortlist ({allowed}).")
        self.submitted = pick
        return f"Pick recorded: {pick.ticker}."
