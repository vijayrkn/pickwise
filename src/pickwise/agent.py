"""The research agent: Claude investigates the shortlist with tools and submits one pick."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import anthropic
import pandas as pd

from .models import Pick
from .tools import TOOL_DEFINITIONS, Toolbox
from .universe import sector_of

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
MAX_TURNS = 20
# Server-side refusal fallback: if the primary model declines, the API retries on
# Anthropic's recommended fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """\
You are Pickwise, an equity research analyst who publishes exactly one US stock idea per \
trading day for a general audience.

A quantitative screen (momentum, trend, volatility and quality factors) has already narrowed \
the universe to a shortlist. Your job is to do the judgment work the screen can't:

1. Review the shortlist and check get_pick_history so you don't repeat yourself.
2. Investigate the most promising three or four names with get_price_action and \
get_fundamentals.
3. Use web_search for recent news, earnings results and upcoming catalysts on your finalists. \
Prefer primary or reputable financial sources from the last 30 days.
4. Choose the single best risk/reward idea for a 1-3 month horizon and call submit_pick.

Standards:
- Ground every claim in the data you retrieved. `sources` holds only URLs from web search \
results you relied on; leave it empty if you used none.
- Be specific: numbers, dates and named catalysts beat adjectives.
- Name the real risks, including what would prove the thesis wrong.
- Set conviction honestly. "low" is a valid answer on a day with no standout idea.
- This is educational research, not personalised advice. Don't tell readers to buy, \
size positions or set price targets for them.
"""


class AgentError(RuntimeError):
    pass


@dataclass
class AgentResult:
    pick: Pick
    model: str
    turns: int
    input_tokens: int
    output_tokens: int


def _shortlist_brief(candidates: pd.DataFrame, as_of: str) -> str:
    cols = ["score", "price", "return_1m", "return_3m", "momentum_12_1", "volatility",
            "pct_from_high", "rsi_14", "quality"]
    table = candidates[[c for c in cols if c in candidates.columns]].round(3)
    table.insert(0, "sector", [sector_of(t) for t in table.index])
    return (
        f"Today is {as_of}. Here is today's quantitative shortlist, best composite score "
        f"first. Returns and volatility are fractions (0.05 = 5%).\n\n"
        f"{table.to_string()}\n\n"
        "Research these candidates and submit one pick."
    )


def _log_web_search(content) -> None:
    """Server-side search runs on Anthropic's infrastructure, so surface its outcome here.

    Errors don't raise: they arrive as a result block whose `content` is an error object
    (success is a list of results).
    """
    for block in content:
        if block.type == "server_tool_use" and block.name == "web_search":
            log.info("web_search(%s)", json.dumps(block.input)[:80])
        elif block.type == "web_search_tool_result":
            if isinstance(block.content, list):
                log.info("web_search -> %d results", len(block.content))
            else:
                error = getattr(block.content, "error_code", block.content)
                log.warning("web_search failed: %s", error)


def run_agent(
    toolbox: Toolbox,
    as_of: str,
    client: anthropic.Anthropic | None = None,
    model: str = MODEL,
    effort: str = "high",
) -> AgentResult:
    client = client or anthropic.Anthropic()
    messages: list[dict] = [
        {"role": "user", "content": _shortlist_brief(toolbox.candidates, as_of)}
    ]
    usage_in = usage_out = 0
    served_by = model

    for turn in range(1, MAX_TURNS + 1):  # noqa: B007 - `turn` is reported after the loop
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        usage_in += response.usage.input_tokens
        usage_out += response.usage.output_tokens
        served_by = response.model

        if response.stop_reason == "refusal":
            raise AgentError(f"Model declined the request: {response.stop_details}")

        messages.append({"role": "assistant", "content": response.content})
        _log_web_search(response.content)

        if response.stop_reason == "pause_turn":
            # A server tool (web search) hit its per-turn iteration limit; resend to continue.
            continue

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            if toolbox.submitted:
                break
            messages.append({
                "role": "user",
                "content": "Please finish your research and call submit_pick with one ticker.",
            })
            continue

        results = []
        for call in tool_calls:
            content, is_error = toolbox.run(call.name, call.input)
            log.info("tool %s(%s) -> %s", call.name, json.dumps(call.input)[:80],
                     "error" if is_error else "ok")
            results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": content,
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})

        if toolbox.submitted:
            break
    else:
        raise AgentError(f"No pick submitted after {MAX_TURNS} turns.")

    return AgentResult(
        pick=toolbox.submitted,
        model=served_by,
        turns=turn,
        input_tokens=usage_in,
        output_tokens=usage_out,
    )


def quant_only_pick(toolbox: Toolbox) -> AgentResult:
    """Deterministic fallback used by --no-llm: take the top-scored name and describe why."""
    candidates = toolbox.candidates
    top, runner_up = candidates.index[0], candidates.index[1]
    row = candidates.loc[top]
    f = toolbox.fundamentals_fn(top)
    pick = Pick(
        ticker=top,
        company=f.get("name") or top,
        headline=f"{top} ranks #1 on today's composite momentum, trend and quality screen.",
        conviction="low",
        horizon="1-3 months",
        thesis=[
            f"12-1 month momentum of {row['momentum_12_1']:.1%} and a 3-month return of "
            f"{row['return_3m']:.1%}.",
            f"Trading {abs(row['pct_from_high']):.1%} below its 52-week high with "
            f"RSI {row['rsi_14']:.0f}.",
            f"Annualised 3-month volatility of {row['volatility']:.1%}.",
        ],
        catalysts=["Not researched: quant-only mode skips the news and catalyst review."],
        risks=["Momentum reversals can be sharp.", "No qualitative research was performed."],
        why_not_runner_up=f"Composite score {row['score']:.2f} vs "
        f"{candidates.loc[runner_up, 'score']:.2f} for {runner_up}.",
        runner_up=runner_up,
    )
    toolbox.submitted = pick
    return AgentResult(pick=pick, model="quant-only", turns=0, input_tokens=0, output_tokens=0)
