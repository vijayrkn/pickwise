import pandas as pd

from pickwise import screener


def test_technical_factors_skip_short_history(closes):
    short = closes.iloc[-100:]
    assert screener.technical_factors(short).empty


def test_uptrend_beats_downtrend(closes):
    ranked = screener.score(screener.technical_factors(closes.drop(columns="SPY")))
    assert ranked.index[0] == "STEADY"
    assert ranked.loc["STEADY", "score"] > ranked.loc["FALLING", "score"]
    assert ranked.loc["STEADY", "trend"] == 2
    assert ranked.loc["FALLING", "trend"] == 0


def test_rsi_bounds():
    rising = pd.Series(range(1, 50), dtype=float)
    assert screener.rsi(rising) == 100.0
    assert 0 <= screener.rsi(pd.Series([1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2.0])) <= 100


def test_quality_score_rewards_profitable_reasonable_companies(fake_fundamentals):
    good = screener.quality_score(fake_fundamentals("STEADY"))
    bad = screener.quality_score(fake_fundamentals("ROCKET"))
    assert good > 0 > bad
    assert screener.quality_score({}) == 0.0


def test_shortlist_respects_exclusions(closes, fake_fundamentals):
    result = screener.shortlist(closes, exclude={"SPY", "STEADY"}, final_n=2,
                                fundamentals_fn=fake_fundamentals)
    assert "STEADY" not in result.index
    assert "SPY" not in result.index
    assert len(result) == 2


def test_overbought_penalty_applied(closes):
    factors = screener.technical_factors(closes.drop(columns="SPY"))
    baseline = screener.score(factors)["score"]
    factors.loc["FLAT", "rsi_14"] = 90
    penalised = screener.score(factors)["score"]
    assert penalised["FLAT"] == baseline["FLAT"] - screener.OVERBOUGHT_PENALTY
