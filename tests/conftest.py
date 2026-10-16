import numpy as np
import pandas as pd
import pytest

from pickwise.tools import Toolbox


@pytest.fixture
def closes() -> pd.DataFrame:
    """300 business days of synthetic prices with clearly different personalities."""
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2025-06-02", periods=300)
    t = np.arange(300)

    def walk(drift, vol, start=100.0):
        return start * np.exp(np.cumsum(drift + vol * rng.standard_normal(300)))

    return pd.DataFrame(
        {
            "STEADY": walk(0.0012, 0.008),  # smooth uptrend: should rank first
            "ROCKET": walk(0.0020, 0.035),  # strong but very volatile
            "FLAT": 100 + np.sin(t / 10),  # going nowhere
            "FALLING": walk(-0.0015, 0.012),  # downtrend: should rank last
            "SPY": walk(0.0005, 0.007, 500),
        },
        index=idx,
    )


@pytest.fixture
def fake_fundamentals():
    data = {
        "STEADY": {"return_on_equity": 0.30, "profit_margin": 0.25, "revenue_growth": 0.15,
                   "forward_pe": 20, "debt_to_equity": 40},
        "ROCKET": {"return_on_equity": -0.10, "profit_margin": -0.05, "revenue_growth": 0.60,
                   "forward_pe": None, "debt_to_equity": 250},
    }
    return lambda t: {"ticker": t, "name": f"{t} Inc.", **data.get(t, {})}


@pytest.fixture
def toolbox(closes, fake_fundamentals) -> Toolbox:
    from pickwise import screener

    candidates = screener.shortlist(closes, exclude={"SPY"}, final_n=3,
                                    fundamentals_fn=fake_fundamentals)
    return Toolbox(closes, candidates, history=[], fundamentals_fn=fake_fundamentals)
