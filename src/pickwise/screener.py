"""Quantitative pre-screen.

The LLM is good at reading context and weighing a thesis, but it should not be the thing
scanning 100 price series. This module does the number-crunching deterministically and hands
the agent a short, ranked list of candidates to research.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# Factor weights for the composite score. Momentum dominates, with trend confirmation,
# a preference for smoother names, and a quality overlay once fundamentals are known.
WEIGHTS = {
    "momentum_12_1": 0.30,
    "return_3m": 0.15,
    "trend": 0.15,
    "low_volatility": 0.10,
    "near_high": 0.10,
    "quality": 0.20,
}
OVERBOUGHT_RSI = 75
OVERBOUGHT_PENALTY = 0.5


def rsi(series: pd.Series, window: int = 14) -> float:
    delta = series.diff().dropna()
    gains = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    losses = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    last_loss = losses.iloc[-1]
    if last_loss == 0:
        return 100.0
    return float(100 - 100 / (1 + gains.iloc[-1] / last_loss))


def technical_factors(closes: pd.DataFrame) -> pd.DataFrame:
    """One row per ticker with raw (un-normalised) technical factors."""
    rows = {}
    for ticker in closes.columns:
        s = closes[ticker].dropna()
        if len(s) < 210:  # need enough history for a 200-day average
            continue
        last = s.iloc[-1]
        lookback = s.iloc[-min(len(s), TRADING_DAYS)]
        sma50, sma200 = s.iloc[-50:].mean(), s.iloc[-200:].mean()
        daily = s.pct_change().dropna()
        rows[ticker] = {
            "price": float(last),
            "return_1m": float(last / s.iloc[-21] - 1),
            "return_3m": float(last / s.iloc[-63] - 1),
            "momentum_12_1": float(s.iloc[-21] / lookback - 1),
            "volatility": float(daily.iloc[-63:].std() * np.sqrt(TRADING_DAYS)),
            "pct_from_high": float(last / s.iloc[-TRADING_DAYS:].max() - 1),
            "rsi_14": rsi(s),
            "above_sma50": bool(last > sma50),
            "sma50_above_sma200": bool(sma50 > sma200),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def zscore(s: pd.Series) -> pd.Series:
    std = s.std(ddof=0)
    if not std or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    return ((s - s.mean()) / std).clip(-3, 3)


def quality_score(f: dict) -> float:
    """Score in roughly [-1, 1] from fundamentals. Missing fields count as neutral."""
    points = []
    if (roe := f.get("return_on_equity")) is not None:
        points.append(np.clip((roe - 0.12) / 0.20, -1, 1))
    if (margin := f.get("profit_margin")) is not None:
        points.append(np.clip((margin - 0.10) / 0.15, -1, 1))
    if (growth := f.get("revenue_growth")) is not None:
        points.append(np.clip(growth / 0.15, -1, 1))
    if (pe := f.get("forward_pe")) is not None and pe > 0:
        points.append(np.clip((25 - pe) / 15, -1, 1))  # cheaper than ~25x is a plus
    if (de := f.get("debt_to_equity")) is not None:
        points.append(np.clip((100 - de) / 150, -1, 1))  # yfinance reports D/E in percent
    return float(np.mean(points)) if points else 0.0


def score(factors: pd.DataFrame, quality: dict[str, float] | None = None) -> pd.DataFrame:
    """Add normalised factor columns and a composite `score`; return sorted best-first."""
    df = factors.copy()
    df["trend"] = df["above_sma50"].astype(int) + df["sma50_above_sma200"].astype(int)
    df["quality"] = pd.Series(quality or {}, dtype=float).reindex(df.index).fillna(0.0)

    normalised = {
        "momentum_12_1": zscore(df["momentum_12_1"]),
        "return_3m": zscore(df["return_3m"]),
        "trend": df["trend"] - 1.0,  # 0/1/2 -> -1/0/+1
        "low_volatility": zscore(-df["volatility"]),
        "near_high": zscore(df["pct_from_high"]),
        "quality": df["quality"] * 2,  # stretch to a z-score-like range
    }
    df["score"] = sum(WEIGHTS[name] * values for name, values in normalised.items())
    df.loc[df["rsi_14"] > OVERBOUGHT_RSI, "score"] -= OVERBOUGHT_PENALTY
    return df.sort_values("score", ascending=False)


def shortlist(
    closes: pd.DataFrame,
    exclude: set[str] = frozenset(),
    pre_n: int = 25,
    final_n: int = 10,
    fundamentals_fn=None,
) -> pd.DataFrame:
    """Two-pass screen: rank on technicals, then re-rank the top `pre_n` with quality data.

    `fundamentals_fn` is injected so tests (and dry runs) can avoid the network.
    """
    tech = technical_factors(closes.drop(columns=list(exclude), errors="ignore"))
    first_pass = score(tech).head(pre_n)
    if fundamentals_fn is None:
        return first_pass.head(final_n)
    quality = {t: quality_score(fundamentals_fn(t)) for t in first_pass.index}
    return score(first_pass, quality).head(final_n)
