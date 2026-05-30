"""精确匹配 judge：意图识别 / 工具调用名称 / 决策字段精确匹配。"""
from __future__ import annotations

from typing import Any


def judge_intent(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """判断意图是否符合预期。actual 为 API 实际输出中提取的 intent 字段。"""
    got = (actual.get("intent") or "").strip().lower()
    exp = (expected.get("intent") or "").strip().lower()
    match = got == exp
    return {
        "pass": match,
        "score": 1.0 if match else 0.0,
        "detail": f"got={got!r} expected={exp!r}",
    }


def judge_tool_call(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """判断工具调用名称与参数包含（子集语义）。"""
    got_tool = actual.get("tool") or actual.get("tool_name") or ""
    exp_tool = expected.get("tool") or ""
    tool_match = got_tool.strip().lower() == exp_tool.strip().lower()

    exp_args = expected.get("args_contains") or {}
    got_args = actual.get("args") or actual.get("tool_args") or {}
    args_match = all(
        str(v) in str(got_args.get(k, ""))
        for k, v in exp_args.items()
    )

    ok = tool_match and args_match
    return {
        "pass": ok,
        "score": (1.0 if tool_match else 0.5) * (1.0 if args_match else 0.6),
        "detail": f"tool match={tool_match}, args match={args_match}",
    }


def judge_risk_decision(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """判断风控决策：decision + score 阈值。"""
    got_decision = actual.get("decision", "")
    exp_decision = expected.get("decision", "")
    decision_match = got_decision == exp_decision

    score_val = float(actual.get("fusion_score", actual.get("score", 0)))
    score_lt = expected.get("score_lt")
    score_gte = expected.get("score_gte")
    score_ok = True
    if score_lt is not None:
        score_ok = score_val < score_lt
    elif score_gte is not None:
        score_ok = score_val >= score_gte

    ok = decision_match and score_ok
    return {
        "pass": ok,
        "score": 1.0 if ok else (0.5 if decision_match else 0.0),
        "detail": f"decision={got_decision!r}(exp={exp_decision!r}), score={score_val:.1f}",
    }


__all__ = ["judge_intent", "judge_tool_call", "judge_risk_decision"]
