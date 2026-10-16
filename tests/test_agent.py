"""Agent-loop tests against a scripted fake client: no network, no API key."""

import json
from types import SimpleNamespace as NS

import pytest

from pickwise.agent import AgentError, quant_only_pick, run_agent


def tool_use(id_, name, args):
    return NS(type="tool_use", id=id_, name=name, input=args)


def response(content, stop_reason="tool_use"):
    return NS(content=content, stop_reason=stop_reason, stop_details=None, model="fake-model",
              usage=NS(input_tokens=100, output_tokens=20))


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs):
        # Snapshot the history: the agent keeps appending to the same list.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.script.pop(0)


def submit_args(ticker, runner_up):
    return {"ticker": ticker, "company": "Steady Co", "headline": "Smooth compounder.",
            "conviction": "medium", "horizon": "1-3 months", "thesis": ["a", "b", "c"],
            "catalysts": ["earnings"], "risks": ["valuation"], "why_not_runner_up": "smoother",
            "runner_up": runner_up, "sources": []}


def test_agent_researches_then_submits(toolbox):
    top, second = toolbox.candidates.index[:2]
    client = FakeClient([
        response([tool_use("1", "get_price_action", {"ticker": top}),
                  tool_use("2", "get_fundamentals", {"ticker": top})]),
        response([tool_use("3", "submit_pick", submit_args(top, second))]),
    ])
    result = run_agent(toolbox, "2026-10-16", client=client)

    assert result.pick.ticker == top
    assert result.turns == 2 and result.input_tokens == 200
    # Both tool results went back together in one user message.
    results = client.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["1", "2"]
    assert json.loads(results[0]["content"])["ticker"] == top
    # Refusal fallback is opted into on every request.
    assert client.calls[0]["fallbacks"] == "default"


def test_off_shortlist_pick_is_rejected_and_retried(toolbox):
    top, second = toolbox.candidates.index[:2]
    client = FakeClient([
        response([tool_use("1", "submit_pick", submit_args("SPY", second))]),
        response([tool_use("2", "submit_pick", submit_args(top, second))]),
    ])
    result = run_agent(toolbox, "2026-10-16", client=client)
    error = client.calls[1]["messages"][-1]["content"][0]
    assert error["is_error"] and "not on today's shortlist" in error["content"]
    assert result.pick.ticker == top


def test_refusal_raises(toolbox):
    client = FakeClient([response([], stop_reason="refusal")])
    with pytest.raises(AgentError):
        run_agent(toolbox, "2026-10-16", client=client)


def test_nudges_when_model_stops_without_submitting(toolbox):
    top, second = toolbox.candidates.index[:2]
    client = FakeClient([
        response([NS(type="text", text="Thinking it over.")], stop_reason="end_turn"),
        response([tool_use("1", "submit_pick", submit_args(top, second))]),
    ])
    run_agent(toolbox, "2026-10-16", client=client)
    assert "submit_pick" in client.calls[1]["messages"][-1]["content"]


def test_quant_only_pick_takes_top_score(toolbox):
    result = quant_only_pick(toolbox)
    assert result.pick.ticker == toolbox.candidates.index[0]
    assert result.model == "quant-only"
