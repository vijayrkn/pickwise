<div align="center">

# 📈 Pickwise

**An autonomous AI research agent that publishes one well-reasoned stock idea every trading day and keeps score of itself.**

[![CI](https://github.com/vijayrkn/pickwise/actions/workflows/ci.yml/badge.svg)](https://github.com/vijayrkn/pickwise/actions/workflows/ci.yml)
[![Daily pick](https://github.com/vijayrkn/pickwise/actions/workflows/daily-pick.yml/badge.svg)](https://github.com/vijayrkn/pickwise/actions/workflows/daily-pick.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Haiku%205.5-D97757)
![License](https://img.shields.io/badge/license-MIT-green)

</div>

> [!WARNING]
> **Not financial advice.** Pickwise is an educational project in agent design. Picks are generated automatically, may be wrong, and ignore your personal situation.

## Today's pick

<!-- today:start -->
### 2026-11-26: [V](picks/2026-11-26.md) · Visa Inc.

> Visa: steady double-digit growth at a less stretched multiple than the defensive crowd

Conviction: 🟠 Medium · Horizon: 1-3 months · [Full write-up →](picks/2026-11-26.md)
<!-- today:end -->

## Track record

Every pick is logged with its entry price and scored against the S&P 500 (SPY) over the same window. Every run re-prices all past picks at the latest close, here and in each pick's own file. Nothing gets deleted, so the misses stay on the record too.

<!-- track-record:start -->
**5 picks** · Hit rate **0%** · Beat S&P 500 **20%** · Avg return **-4.41%** · Avg alpha **-1.68%**

| Picked | Ticker | Conviction | Entry price | Price on 2026-11-25 | Change since pick | S&P 500 same period | vs S&P 500 |
|---|---|---|---|---|---|---|---|
| 2026-11-26 | [V](picks/2026-11-26.md) | medium | $424.39 | $424.39 | 0.00% | +0.00% | 0.00% |
| 2026-11-25 | [LLY](picks/2026-11-25.md) | medium | $1,392.22 | $1,392.22 | 0.00% | +0.00% | 0.00% |
| 2026-11-24 | [ABBV](picks/2026-11-24.md) | medium | $300.28 | $294.48 | 🔴 -1.93% | -0.29% | 🔴 -1.64% |
| 2026-11-23 | [TXN](picks/2026-11-23.md) | medium | $291.19 | $270.19 | 🔴 -7.21% | -0.77% | 🔴 -6.44% |
| 2026-10-19 | [EOG](picks/2026-10-19.md) | low | $157.82 | $148.31 | 🔴 -6.03% | -6.62% | 🟢 +0.59% |
| 2026-10-16 | [MSFT](picks/2026-10-16.md) | medium | $526.26 | $489.93 | 🔴 -6.90% | -6.01% | 🔴 -0.90% |
<!-- track-record:end -->

Full history: [`picks/`](picks/)

---

## How it works

Pickwise splits the job between deterministic code and the LLM, giving each the part it's best at:

```mermaid
flowchart LR
    A[~100 US large caps<br/>11 sectors] --> B[Quant screen<br/>momentum · trend · volatility]
    B --> C[Quality overlay<br/>ROE · margins · growth · valuation]
    C --> D[Top 10 shortlist]
    D --> E{{Claude research agent}}
    E -- get_price_action --> F[(Price data)]
    E -- get_fundamentals --> G[(Fundamentals)]
    E -- web_search --> H[(News & catalysts)]
    E -- get_pick_history --> I[(Past picks)]
    E -- submit_pick --> J[Daily write-up<br/>+ README update]
    J --> K[Performance tracker<br/>vs S&P 500]
    K -.feedback.-> E
```

1. **Screen (code).** Pulls a year of prices for the universe in one batch call and computes 12-1 month momentum, 3-month return, trend (50/200-day averages), volatility, distance from the 52-week high, and RSI. The top 25 then get a quality score from fundamentals and are re-ranked to a 10-name shortlist. Anything picked in the last 30 days is excluded.
2. **Research (agent).** Claude Haiku 5.5 gets the shortlist and a toolset. It decides which names deserve a closer look, pulls price action and fundamentals, searches the web for recent earnings and catalysts, and checks its own track record before committing.
3. **Decide (structured output).** The agent must call `submit_pick` with a strict JSON schema (thesis, catalysts, risks, conviction, and why it beat the runner-up). Off-shortlist tickers are rejected, and the agent is told to try again.
4. **Publish and track (code).** A GitHub Action runs every weekday before the US open. It writes `picks/YYYY-MM-DD.md`, appends to `picks/history.json`, refreshes this README, and commits.

### Design choices

| Decision | Why |
|---|---|
| The quant screen runs *before* the LLM | Cheap, reproducible and testable. The model spends its effort on judgment, not arithmetic. |
| Strict tool schemas plus a terminal `submit_pick` tool | Output is guaranteed to parse. Validation errors go back to the model as `is_error` tool results so it can self-correct. |
| Server-side web search | Fresh news without running a scraper. Results come with citations, which end up in `sources`. |
| The agent sees its own track record | Discourages repetition and overconfidence. "Low conviction" is an allowed answer. |
| Claude Haiku 5.5 at `low` effort by default | A run costs about 2-3 cents (mostly the two web searches), or roughly $0.50 a month. The quant screen already does the heavy lifting, so the model only has to weigh 2-3 finalists. Use `--model claude-opus-5-5 --effort high` for deeper research. |
| Prompt caching and a tight research budget | Every turn resends the conversation, so the repeated prefix is cached (billed at 10% of the input rate). The agent is capped at 8 turns and 3 web searches. |
| Refusal fallback on larger models | With Opus or Sonnet, `fallbacks: "default"` retries a declined request on a fallback model inside the same call. Haiku doesn't offer this, so a refusal ends the run with a clear error. |
| `--no-llm` quant-only mode | The pipeline still runs (and CI can exercise it) without an API key. |

## Quick start

```bash
git clone https://github.com/vijayrkn/pickwise && cd pickwise
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pickwise screen                 # today's quantitative shortlist
pickwise run --no-llm --dry-run # quant-only pick, nothing written
export ANTHROPIC_API_KEY=sk-ant-...
pickwise -v run --dry-run       # full agent run (Haiku), printed to the terminal
pickwise -v run --dry-run --model claude-opus-5-5 --effort high  # deeper, pricier run
pickwise run                    # publish to picks/ and update README
pickwise track                  # performance of every past pick
pickwise track --write          # re-price the README table and pick files
```

### Run it on your own fork

1. Fork the repo.
2. Make sure web search is enabled for your organization in the [Claude Console](https://console.anthropic.com) settings. Without it the agent still runs, but on price and fundamentals only.
3. Add an `ANTHROPIC_API_KEY` secret under **Settings → Secrets and variables → Actions**.
4. Enable workflows on the **Actions** tab. The `Daily pick` workflow runs at 13:00 UTC on weekdays, and you can also trigger it by hand.

Without the secret, the workflow falls back to quant-only picks.

## Project layout

```
src/pickwise/
├── universe.py     # tickers by sector + benchmark
├── market_data.py  # yfinance wrapper (prices, fundamentals)
├── screener.py     # factor maths and composite ranking
├── tools.py        # tool schemas + implementations the agent can call
├── agent.py        # Claude tool-use loop, system prompt, quant-only fallback
├── report.py       # Markdown write-up and README sections
├── tracker.py      # pick history and performance vs SPY
└── cli.py          # `pickwise run | screen | track`
tests/              # offline tests with synthetic prices and a scripted fake Claude client
```

## Testing

```bash
pytest -q && ruff check src tests
```

The suite runs fully offline. Price series are synthetic with known shapes (steady uptrend, volatile, flat, downtrend), and the agent loop runs against a scripted fake client. The tests cover parallel tool results, rejection of off-shortlist picks, refusal handling, and nudging the agent when it stalls.

## Roadmap

- [ ] Sector-neutral mode (one pick per sector per week)
- [ ] Email and Slack delivery of the daily write-up
- [ ] Rolling equity curve chart in the README
- [ ] Earnings-calendar awareness to avoid picking the day before a report

## License

MIT © Vijay Ramakrishnan
