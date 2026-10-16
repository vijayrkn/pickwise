from datetime import date

import pytest

from pickwise import report, tracker
from pickwise.models import Pick, PickRecord


def record(day: str, ticker: str, entry: float, bench: float = 500.0) -> PickRecord:
    return PickRecord(date=day, ticker=ticker, company=ticker, conviction="medium",
                      entry_price=entry, benchmark_entry_price=bench, model="test")


def test_append_is_idempotent_per_day(tmp_path):
    path = tmp_path / "history.json"
    tracker.append(path, record("2026-10-01", "AAA", 10))
    tracker.append(path, record("2026-10-01", "BBB", 20))
    tracker.append(path, record("2026-10-02", "CCC", 30))
    assert [r.ticker for r in tracker.load_history(path)] == ["BBB", "CCC"]


def test_recent_tickers_cooldown():
    records = [record("2026-09-01", "OLD", 1), record("2026-10-10", "NEW", 1)]
    assert tracker.recent_tickers(records, date(2026, 10, 16), cooldown_days=30) == {"NEW"}


def test_performance_and_summary():
    records = [record("2026-10-01", "WIN", 100), record("2026-10-02", "LOSE", 100)]
    perf = tracker.performance(records, {"WIN": 110, "LOSE": 95, "SPY": 505}, "SPY")
    assert list(perf["ticker"]) == ["LOSE", "WIN"]  # newest first
    win = perf.set_index("ticker").loc["WIN"]
    assert win["return"] == pytest.approx(0.10)
    assert win["alpha"] == pytest.approx(0.09)
    stats = tracker.summary(perf)
    assert stats["hit_rate"] == 0.5 and stats["beat_benchmark_rate"] == 0.5


def test_replace_section_requires_markers():
    text = "a\n<!-- today:start -->\nold\n<!-- today:end -->\nb"
    assert "new" in report.replace_section(text, "today", "new")
    with pytest.raises(ValueError):
        report.replace_section("no markers", "today", "x")


def test_render_pick_contains_disclaimer(toolbox):
    ticker = toolbox.candidates.index[0]
    pick = Pick(ticker=ticker, company="Co", headline="h", conviction="high", horizon="1-3 months",
                thesis=["t"], catalysts=["c"], risks=["r"], why_not_runner_up="w",
                runner_up=toolbox.candidates.index[1], sources=["https://example.com"])
    md = report.render_pick(pick, "2026-10-16", 123.45, toolbox.candidates, "claude-opus-5-5")
    assert "Not financial advice" in md
    assert "$123.45" in md and "https://example.com" in md


def test_same_day_picks_excluded_from_stats():
    records = [record("2026-10-15", "OLD", 100), record("2026-10-16", "NEW", 100)]
    perf = tracker.performance(records, {"OLD": 101, "NEW": 100.01, "SPY": 500}, "SPY")
    assert tracker.summary(perf, as_of="2026-10-16")["picks"] == 1
    assert tracker.summary(perf.iloc[:1], as_of="2026-10-16") == {"picks": 0}
    md = report.render_track_record(perf, tracker.summary(perf, as_of="2026-10-16"))
    assert "**1 pick**" in md


def test_non_url_sources_are_not_rendered_as_links(toolbox):
    ticker = toolbox.candidates.index[0]
    pick = Pick(ticker=ticker, company="Co", headline="h", conviction="low", horizon="1-3 months",
                thesis=["t"], catalysts=["c"], risks=["r"], why_not_runner_up="w",
                runner_up=toolbox.candidates.index[1], sources=["get_fundamentals: X"])
    md = report.render_pick(pick, "2026-10-16", 1.0, toolbox.candidates, "m")
    assert "<get_fundamentals" not in md
    assert "Market and fundamental data only" in md
