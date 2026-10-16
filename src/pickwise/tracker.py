"""Persist every pick and score it against the S&P 500 so the agent is held accountable."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .models import PickRecord


def load_history(path: Path) -> list[PickRecord]:
    if not path.exists():
        return []
    return [PickRecord(**row) for row in json.loads(path.read_text())]


def save_history(path: Path, records: list[PickRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [r.model_dump() for r in sorted(records, key=lambda r: r.date)]
    path.write_text(json.dumps(payload, indent=2) + "\n")


def append(path: Path, record: PickRecord) -> list[PickRecord]:
    """Add a record, replacing any existing pick for the same date (re-runs are idempotent)."""
    records = [r for r in load_history(path) if r.date != record.date]
    records.append(record)
    save_history(path, records)
    return records


def recent_tickers(records: list[PickRecord], as_of: date, cooldown_days: int) -> set[str]:
    """Tickers picked within the cooldown window, so the agent doesn't repeat itself."""
    return {
        r.ticker
        for r in records
        if (as_of - datetime.strptime(r.date, "%Y-%m-%d").date()).days < cooldown_days
    }


def performance(
    records: list[PickRecord], prices: dict[str, float], benchmark: str
) -> pd.DataFrame:
    """Return since pick vs. the benchmark over the same window, newest first."""
    rows = []
    bench_now = prices.get(benchmark)
    for r in records:
        now = prices.get(r.ticker)
        if now is None or bench_now is None:
            continue
        ret = now / r.entry_price - 1
        bench_ret = bench_now / r.benchmark_entry_price - 1
        rows.append({
            "date": r.date,
            "ticker": r.ticker,
            "conviction": r.conviction,
            "entry": r.entry_price,
            "current": now,
            "return": ret,
            "benchmark_return": bench_ret,
            "alpha": ret - bench_ret,
        })
    df = pd.DataFrame(rows)
    return df.sort_values("date", ascending=False).reset_index(drop=True) if not df.empty else df


def summary(perf: pd.DataFrame, as_of: str | None = None) -> dict:
    """Aggregate stats. Picks made on `as_of` are excluded: they have no holding period yet."""
    if as_of is not None and not perf.empty:
        perf = perf[perf["date"] < as_of]
    if perf.empty:
        return {"picks": 0}
    return {
        "picks": len(perf),
        "hit_rate": float((perf["return"] > 0).mean()),
        "beat_benchmark_rate": float((perf["alpha"] > 0).mean()),
        "avg_return": float(perf["return"].mean()),
        "avg_alpha": float(perf["alpha"].mean()),
    }
