"""Command-line entry point: `pickwise run`, `pickwise screen`, `pickwise track`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

import anthropic

from . import market_data, report, screener, tracker
from .agent import DEFAULT_EFFORT, MODEL, quant_only_pick, run_agent
from .models import PickRecord
from .tools import Toolbox
from .universe import BENCHMARK, all_tickers

ROOT = Path.cwd()
PICKS_DIR = ROOT / "picks"
HISTORY = PICKS_DIR / "history.json"
README = ROOT / "README.md"
COOLDOWN_DAYS = 30

log = logging.getLogger("pickwise")


def _load_market(as_of: date):
    history = tracker.load_history(HISTORY)
    closes = market_data.download_closes(all_tickers() + [BENCHMARK])
    exclude = tracker.recent_tickers(history, as_of, COOLDOWN_DAYS) | {BENCHMARK}
    candidates = screener.shortlist(
        closes, exclude=exclude, fundamentals_fn=market_data.fundamentals
    )
    return history, closes, candidates


def cmd_screen(args) -> int:
    _, _, candidates = _load_market(date.today())
    cols = ["score", "price", "return_3m", "momentum_12_1", "volatility", "rsi_14", "quality"]
    print(candidates[cols].round(3).to_string())
    return 0


def cmd_run(args) -> int:
    if not args.no_llm and not os.environ.get("ANTHROPIC_API_KEY"):
        log.error("ANTHROPIC_API_KEY is not set in this shell. Export it first, or use "
                  "--no-llm for a quant-only pick.")
        return 1
    as_of = date.today()
    as_of_str = as_of.isoformat()
    history, closes, candidates = _load_market(as_of)
    log.info("Shortlist: %s", ", ".join(candidates.index))

    toolbox = Toolbox(closes, candidates, history, market_data.fundamentals)
    try:
        result = quant_only_pick(toolbox) if args.no_llm else run_agent(
            toolbox, as_of_str, model=args.model, effort=args.effort
        )
    except anthropic.AuthenticationError:
        log.error("ANTHROPIC_API_KEY was rejected. Create a new key in the Claude Console and "
                  "update it (locally, or the repository secret for the GitHub workflow).")
        return 1
    pick = result.pick
    price = float(closes[pick.ticker].dropna().iloc[-1])
    log.info("Pick: %s (%s conviction) via %s in %d turns, %d in (%d cached) / %d out tokens",
             pick.ticker, pick.conviction, result.model, result.turns,
             result.input_tokens, result.cached_input_tokens, result.output_tokens)

    markdown = report.render_pick(pick, as_of_str, price, candidates, result.model)
    if args.dry_run:
        print(markdown)
        return 0

    PICKS_DIR.mkdir(exist_ok=True)
    (PICKS_DIR / f"{as_of_str}.md").write_text(markdown)
    records = tracker.append(HISTORY, PickRecord(
        date=as_of_str,
        ticker=pick.ticker,
        company=pick.company,
        conviction=pick.conviction,
        entry_price=round(price, 4),
        benchmark_entry_price=round(float(closes[BENCHMARK].dropna().iloc[-1]), 4),
        model=result.model,
    ))
    _refresh_results(records, closes, pick, as_of_str)
    print(f"Published picks/{as_of_str}.md -> {pick.ticker}")
    return 0


def _refresh_results(records, closes, pick, as_of_str) -> None:
    """Re-price every past pick at the latest close: README table and each pick file."""
    tickers = {r.ticker for r in records} | {BENCHMARK}
    missing = sorted(tickers - set(closes.columns))
    if missing:  # past picks can drop out of today's screen; fetch them separately
        closes = closes.join(market_data.download_closes(missing, period="5d"), how="outer")
    prices = {c: float(closes[c].dropna().iloc[-1]) for c in closes.columns}
    price_date = closes[BENCHMARK].dropna().index[-1].date().isoformat()
    perf = tracker.performance(records, prices, BENCHMARK)
    track_md = report.render_track_record(perf, tracker.summary(perf, as_of_str), price_date)
    report.update_readme(README, track_md, pick, as_of_str)
    n = report.update_pick_files(PICKS_DIR, perf, price_date)
    log.info("Re-priced %d past picks at the %s close", n, price_date)


def cmd_track(args) -> int:
    records = tracker.load_history(HISTORY)
    if not records:
        print("No picks yet.")
        return 0
    tickers = sorted({r.ticker for r in records} | {BENCHMARK})
    closes = market_data.download_closes(tickers, period="5d")
    prices = {c: float(closes[c].dropna().iloc[-1]) for c in closes.columns}
    perf = tracker.performance(records, prices, BENCHMARK)
    print(perf.round(4).to_string(index=False))
    print(tracker.summary(perf))
    if args.write:
        _refresh_results(records, closes, None, date.today().isoformat())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pickwise", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Screen, research and publish today's pick.")
    run.add_argument("--dry-run", action="store_true", help="Print the pick; write nothing.")
    run.add_argument("--no-llm", action="store_true", help="Quant-only pick, no API calls.")
    run.add_argument("--model", default=MODEL)
    run.add_argument(
        "--effort", default=DEFAULT_EFFORT, choices=["low", "medium", "high", "xhigh", "max"]
    )
    run.set_defaults(func=cmd_run)

    sub.add_parser("screen", help="Print today's quantitative shortlist.").set_defaults(
        func=cmd_screen
    )
    track = sub.add_parser("track", help="Show performance of past picks.")
    track.add_argument("--write", action="store_true",
                       help="Also re-price the README table and every pick file.")
    track.set_defaults(func=cmd_track)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.verbose:
        logging.getLogger("pickwise").setLevel(logging.INFO)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
