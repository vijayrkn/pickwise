"""Thin wrapper around yfinance so the rest of the code never touches the network directly."""

from __future__ import annotations

import logging
from functools import lru_cache

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

FUNDAMENTAL_FIELDS = {
    "shortName": "name",
    "sector": "sector",
    "industry": "industry",
    "marketCap": "market_cap",
    "trailingPE": "trailing_pe",
    "forwardPE": "forward_pe",
    "pegRatio": "peg_ratio",
    "priceToBook": "price_to_book",
    "returnOnEquity": "return_on_equity",
    "profitMargins": "profit_margin",
    "operatingMargins": "operating_margin",
    "revenueGrowth": "revenue_growth",
    "earningsGrowth": "earnings_growth",
    "debtToEquity": "debt_to_equity",
    "freeCashflow": "free_cash_flow",
    "dividendYield": "dividend_yield",
    "beta": "beta",
    "recommendationKey": "analyst_consensus",
    "targetMeanPrice": "analyst_target_mean",
    "numberOfAnalystOpinions": "analyst_count",
}


def download_closes(tickers: list[str], period: str = "14mo") -> pd.DataFrame:
    """Adjusted daily closes, one column per ticker. Tickers with no data are dropped."""
    data = yf.download(
        tickers, period=period, auto_adjust=True, progress=False, threads=True, group_by="column"
    )
    closes = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    closes = closes.dropna(axis=1, how="all").ffill()
    missing = sorted(set(tickers) - set(closes.columns))
    if missing:
        log.warning("No price data for: %s", ", ".join(missing))
    return closes


@lru_cache(maxsize=256)
def fundamentals(ticker: str) -> dict:
    """Key valuation, quality and analyst fields for one ticker (None where unavailable)."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:  # yfinance raises a zoo of exception types on throttling
        log.warning("Fundamentals unavailable for %s: %s", ticker, exc)
        info = {}
    return {"ticker": ticker, **{out: info.get(src) for src, out in FUNDAMENTAL_FIELDS.items()}}


def latest_close(ticker: str) -> float | None:
    hist = yf.Ticker(ticker).history(period="5d", auto_adjust=True)
    return None if hist.empty else float(hist["Close"].iloc[-1])
