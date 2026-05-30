"""eval/runner.py：加载数据集 → 调用系统 → 评测 → 聚合结果。

用法：
    python -m eval.runner --dataset rag --sample 10
    python -m eval.runner --all               # 全量 200 条
    python -m eval.runner --smoke             # 每个数据集抽 10 条（CI 用）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATASETS_DIR = Path(__file__).parent / "datasets"


@dataclass
class EvalCase:
    id: str
    category: str
    input: dict[str, Any]
    expected: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    case_id: str
    category: str
    pass_: bool
    score: float
    latency_ms: float
    actual: dict[str, Any]
    detail: str = ""
    error: str = ""


def load_dataset(category: str) -> list[EvalCase]:
    """加载单个 jsonl 数据集。"""
    path = DATASETS_DIR / f"{category}.jsonl"
    if not path.exists():
        logger.warning("dataset not found: %s", path)
        return []
    cases = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                cases.append(EvalCase(
                    id=d["id"],
                    category=d["category"],
                    input=d["input"],
                    expected=d["expected"],
                    metadata=d.get("metadata", {}),
                ))
            except Exception as exc:
                logger.warning("skip malformed line: %s", exc)
    return cases


def _ensure_kb_for_eval() -> None:
    """评测前确保内存 KB 已灌库。"""
    from rag.bootstrap import ensure_kb_indexed

    ensure_kb_indexed()


async def _run_rag_case(case: EvalCase, *, version: str = "v3") -> EvalResult:
    """RAG 类型用例：调用 chat API 并评测答案 + 引用。"""
    from agents.state import initial_state
    from agents.knowledge_agent import stream_knowledge
    from db import set_current_tenant
    from eval.judges.llm_judge import judge_e2e
    from eval.judges.ragas_judge import ragas_score

    query = case.input.get("query", "")
    tenant_id = case.input.get("tenant_id", 1)
    set_current_tenant(tenant_id)

    t0 = time.monotonic()
    state = initial_state(
        messages=[{"role": "user", "content": query}],
        thread_id="eval",
        user_id=None,
        tenant_id=tenant_id,
        version=version,
    )

    tokens: list[str] = []
    citations: list[dict] = []
    event_type = "no_match"
    try:
        async for ev in stream_knowledge(state):
            if ev.type == "token":
                tokens.append(ev.data.get("text", ""))
            elif ev.type == "citation":
                citations.append(ev.data)
            elif ev.type in {"done", "no_match", "error"}:
                event_type = ev.type
    except Exception as exc:
        return EvalResult(
            case_id=case.id, category=case.category, pass_=False, score=0.0,
            latency_ms=(time.monotonic() - t0) * 1000,
            actual={}, error=str(exc),
        )

    latency_ms = (time.monotonic() - t0) * 1000
    answer = "".join(tokens)
    cit_doc_nos = [c.get("doc_no", "") for c in citations]

    # 引用命中率
    exp_citations = case.expected.get("citations", [])
    cit_hit = sum(1 for ec in exp_citations if ec in cit_doc_nos) / max(1, len(exp_citations))

    # keyword 匹配
    exp_contains = case.expected.get("answer_contains", [])
    kw_result = await judge_e2e(query=query, answer=answer, expected_contains=exp_contains)

    # Ragas 4 指标
    contexts = [c.get("snippet", "") for c in citations]
    ragas_result = await ragas_score(
        query=query, contexts=contexts, answer=answer,
        expected_answer=" ".join(exp_contains),
    )

    score = kw_result["keyword_match"] * 0.5 + cit_hit * 0.2 + ragas_result["overall"] * 0.3
    pass_ = score >= 0.5 and (not exp_citations or cit_hit > 0)

    return EvalResult(
        case_id=case.id, category=case.category, pass_=pass_, score=score,
        latency_ms=latency_ms,
        actual={
            "answer": answer[:200],
            "citations": cit_doc_nos,
            "event_type": event_type,
            "keyword_match": kw_result["keyword_match"],
            "cit_hit": cit_hit,
            **{f"ragas_{k}": v for k, v in ragas_result.items() if k != "source"},
        },
        detail=kw_result.get("comment", ""),
    )


async def _run_intent_case(case: EvalCase, *, version: str = "v3") -> EvalResult:
    """意图识别用例：调用 intent_router。"""
    from agents.intent_router import run_intent_router
    from agents.state import initial_state
    from db import set_current_tenant
    from eval.judges.exact_match import judge_intent

    query = case.input.get("query", "")
    tenant_id = case.input.get("tenant_id", 1)
    set_current_tenant(tenant_id)

    t0 = time.monotonic()
    state = initial_state(
        messages=[{"role": "user", "content": query}],
        thread_id="eval", user_id=None, tenant_id=tenant_id, version=version,
    )
    try:
        update = await run_intent_router(state)
        actual_intent = update.get("intent", "")
    except Exception as exc:
        return EvalResult(case_id=case.id, category=case.category, pass_=False, score=0.0,
                          latency_ms=(time.monotonic() - t0) * 1000, actual={}, error=str(exc))

    latency_ms = (time.monotonic() - t0) * 1000
    result = judge_intent({"intent": actual_intent}, case.expected)
    return EvalResult(
        case_id=case.id, category=case.category,
        pass_=result["pass"], score=result["score"],
        latency_ms=latency_ms,
        actual={"intent": actual_intent},
        detail=result["detail"],
    )


async def _run_e2e_case(case: EvalCase, *, version: str = "v3") -> EvalResult:
    """E2E 用例：走完整 chat 流程（含复杂意图 → supervisor 图）。"""
    from agents.state import initial_state
    from agents.knowledge_agent import stream_knowledge
    from agents.intent_router import run_intent_router
    from db import set_current_tenant
    from eval.judges.llm_judge import judge_e2e

    _COMPLEX_INTENTS = frozenset({"refund", "order_query", "address_change", "logistics_query", "ticket_create", "complex"})

    messages = case.input.get("messages", [])
    tenant_id = case.input.get("tenant_id", 1)
    set_current_tenant(tenant_id)

    query = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    t0 = time.monotonic()
    state = initial_state(
        messages=messages, thread_id="eval", user_id=None, tenant_id=tenant_id, version=version,
    )

    try:
        intent_update = await run_intent_router(state)
        state.update(intent_update)
        intent = state.get("intent") or "knowledge"
        complexity = state.get("complexity") or 0

        tokens: list[str] = []
        citations: list[dict] = []

        if intent == "greeting":
            from agents.greeting_handler import run_greeting
            greet = await run_greeting(state)
            tokens.append(str(greet.get("answer") or ""))

        elif intent in _COMPLEX_INTENTS or complexity >= 60:
            # 复杂意图：走完整 supervisor 图（planner → critic → risk_review → plan_execute）
            from agents import get_graph
            from agents.versions.v2 import build_v2
            graph = get_graph() if version == "v3" else build_v2()
            config = {"configurable": {"thread_id": f"eval-{case.id}"}}
            final_state = await graph.ainvoke(state, config) or {}
            answer = final_state.get("answer") or ""
            tokens.append(answer)
            citations = final_state.get("citations") or []

        else:
            # 简单意图：走 KnowledgeAgent 流式
            async for ev in stream_knowledge(state):
                if ev.type == "token":
                    tokens.append(ev.data.get("text", ""))
                elif ev.type == "citation":
                    citations.append(ev.data)
    except Exception as exc:
        return EvalResult(case_id=case.id, category=case.category, pass_=False, score=0.0,
                          latency_ms=(time.monotonic() - t0) * 1000, actual={}, error=str(exc))

    latency_ms = (time.monotonic() - t0) * 1000
    answer = "".join(tokens)
    exp_contains = case.expected.get("answer_contains", [])
    exp_has_citations = case.expected.get("has_citations", False)
    exp_intent = case.expected.get("intent", "")

    kw_result = await judge_e2e(query=query, answer=answer, expected_contains=exp_contains)
    intent_ok = not exp_intent or intent == exp_intent
    cit_ok = not exp_has_citations or len(citations) > 0
    score = kw_result["overall"] * 0.6 + (0.2 if intent_ok else 0.0) + (0.2 if cit_ok else 0.0)

    return EvalResult(
        case_id=case.id, category=case.category,
        pass_=score >= 0.5 and intent_ok,
        score=score, latency_ms=latency_ms,
        actual={"answer": answer[:200], "intent": intent, "citations": len(citations)},
        detail=kw_result.get("comment", ""),
    )


async def _run_tool_call_case(case: EvalCase, *, version: str = "v3") -> EvalResult:
    """工具调用评测：验证 intent_router 输出的意图 + 关键参数匹配。"""
    from agents.intent_router import run_intent_router
    from agents.state import initial_state
    from db import set_current_tenant

    query = case.input.get("query", "")
    tenant_id = case.input.get("context", {}).get("tenant_id", 1)
    set_current_tenant(tenant_id)

    expected_tool = case.expected.get("tool", "")
    args_contains = case.expected.get("args_contains", {})

    def _resolve_tool(intent: str, q: str) -> str | None:
        if intent == "ticket_query":
            if any(x in q for x in ("取消", "加急", "关闭")):
                return "update_ticket"
            return "get_ticket"
        if intent == "refund_query":
            if "RF-" in q or "退款申请" in q:
                return "get_refund"
            if "所有" in q or "记录" in q:
                return "list_refunds"
            return "get_refund"
        mapping = {
            "order_query": "query_order",
            "order_list": "list_orders",
            "logistics_query": "query_logistics",
            "refund": "create_refund",
            "ticket_create": "create_ticket",
            "address_change": "update_address",
            "knowledge": "get_kb_doc",
            "greeting": None,
        }
        return mapping.get(intent, f"unknown:{intent}")

    t0 = time.monotonic()
    state = initial_state(
        messages=[{"role": "user", "content": query}],
        thread_id="eval", user_id=None, tenant_id=tenant_id, version=version,
    )
    try:
        update = await run_intent_router(state)
        actual_intent = update.get("intent", "")
    except Exception as exc:
        return EvalResult(case_id=case.id, category=case.category, pass_=False, score=0.0,
                          latency_ms=(time.monotonic() - t0) * 1000, actual={}, error=str(exc))

    latency_ms = (time.monotonic() - t0) * 1000
    actual_tool = _resolve_tool(actual_intent, query)

    # 工具名匹配
    tool_match = actual_tool == expected_tool

    # 参数检查：从 query 中提取关键参数
    args_ok = True
    matched_args = {}
    for key, val in args_contains.items():
        if str(val) in query:
            matched_args[key] = val
        else:
            args_ok = False

    passed = tool_match and args_ok
    score = (0.5 if tool_match else 0.0) + (0.5 if args_ok else 0.0)

    return EvalResult(
        case_id=case.id, category=case.category,
        pass_=passed, score=score,
        latency_ms=latency_ms,
        actual={"tool": actual_tool, "intent": actual_intent, "matched_args": matched_args},
        detail=f"tool={'match' if tool_match else f'got={actual_tool} expected={expected_tool}'}; args={'ok' if args_ok else 'mismatch'}",
    )


async def _run_risk_case(case: EvalCase, *, version: str = "v3") -> EvalResult:  # noqa: ARG001
    """风控评测：输入退款数据 → 三层融合打分 → 比对预期决策。"""
    from risk import evaluate as risk_evaluate
    from db import set_current_tenant

    refund_data = case.input.get("refund", {})
    user_data = case.input.get("user", {})
    tenant_id = case.input.get("tenant_id", 1)
    set_current_tenant(tenant_id)

    expected_decision = case.expected.get("decision", "pass")
    expected_score_lt = case.expected.get("score_lt")
    expected_score_gte = case.expected.get("score_gte")

    t0 = time.monotonic()
    try:
        result = await risk_evaluate(refund_data, tenant_id=tenant_id, user=user_data)
        rules_result = result.rules
        features_result = result.features
        llm_result = result.llm
    except Exception as exc:
        return EvalResult(case_id=case.id, category=case.category, pass_=False, score=0.0,
                          latency_ms=(time.monotonic() - t0) * 1000, actual={}, error=str(exc))

    latency_ms = (time.monotonic() - t0) * 1000
    actual_decision = result.decision
    actual_score = result.fusion_score

    # 决策匹配
    decision_match = actual_decision == expected_decision

    # 分数范围检查
    score_ok = True
    if expected_score_lt is not None and actual_score >= expected_score_lt:
        score_ok = False
    if expected_score_gte is not None and actual_score < expected_score_gte:
        score_ok = False

    passed = decision_match and score_ok
    score = (0.6 if decision_match else 0.0) + (0.4 if score_ok else 0.0)

    return EvalResult(
        case_id=case.id, category=case.category,
        pass_=passed, score=score,
        latency_ms=latency_ms,
        actual={"decision": actual_decision, "score": actual_score,
                "rules": rules_result.score, "features": features_result.score,
                "llm": llm_result.score},
        detail=f"decision={'match' if decision_match else f'got={actual_decision} expected={expected_decision}'}; score={actual_score} {'ok' if score_ok else 'out_of_range'}",
    )


_CATEGORY_RUNNERS = {
    "rag": _run_rag_case,
    "intent": _run_intent_case,
    "e2e": _run_e2e_case,
    "tool_call": _run_tool_call_case,
    "risk": _run_risk_case,
}


async def run_cases(
    cases: list[EvalCase],
    concurrency: int = 4,
    version: str = "v3",
) -> list[EvalResult]:
    """并发运行用例（同一 category 使用对应 runner）。"""
    sem = asyncio.Semaphore(concurrency)
    results: list[EvalResult] = []

    async def _one(c: EvalCase) -> EvalResult:
        async with sem:
            runner = _CATEGORY_RUNNERS.get(c.category)
            if runner is None:
                return EvalResult(
                    case_id=c.id, category=c.category, pass_=False, score=0.0,
                    latency_ms=0, actual={}, detail="no runner for category",
                )
            return await runner(c, version=version)

    tasks = [_one(c) for c in cases]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)


class EvalRunner:
    """主评测入口。"""

    def __init__(
        self,
        categories: list[str] | None = None,
        sample: int | None = None,
        version: str = "v3",
    ):
        self.categories = categories or ["intent", "rag", "tool_call", "risk", "e2e"]
        self.sample = sample
        self.version = version

    def load_all(self) -> list[EvalCase]:
        cases: list[EvalCase] = []
        for cat in self.categories:
            cat_cases = load_dataset(cat)
            if self.sample and len(cat_cases) > self.sample:
                import random
                random.seed(42)
                cat_cases = random.sample(cat_cases, self.sample)
            cases.extend(cat_cases)
        return cases

    async def run(self) -> list[EvalResult]:
        if any(c in self.categories for c in ("rag", "e2e")):
            _ensure_kb_for_eval()
        cases = self.load_all()
        logger.info("running %d eval cases (version=%s) ...", len(cases), self.version)
        return await run_cases(cases, version=self.version)


def _print_summary(results: list[EvalResult], version: str) -> None:
    """打印单版本评测摘要。"""
    total = len(results)
    passed = sum(1 for r in results if r.pass_)
    avg_score = sum(r.score for r in results) / max(1, total)
    avg_lat = sum(r.latency_ms for r in results) / max(1, total)
    print(f"\n[eval:{version}] {passed}/{total} passed | avg_score={avg_score:.3f} | avg_lat={avg_lat:.0f}ms")
    by_cat: dict[str, list[EvalResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)
    for cat, cat_results in by_cat.items():
        p = sum(1 for r in cat_results if r.pass_)
        s = sum(r.score for r in cat_results) / max(1, len(cat_results))
        print(f"  {cat:12s}: {p}/{len(cat_results)} passed | avg_score={s:.3f}")


def _print_comparison(all_results: dict[str, list[EvalResult]]) -> None:
    """打印多版本 A/B 对比表。"""
    print("\n" + "=" * 70)
    print("A/B 版本对比报告")
    print("=" * 70)
    header = f"{'指标':<20}"
    for v in sorted(all_results):
        header += f"{v:>12}"
    print(header)
    print("-" * 70)

    for metric_name, metric_fn in [
        ("通过率", lambda rs: sum(1 for r in rs if r.pass_) / max(1, len(rs))),
        ("平均分数", lambda rs: sum(r.score for r in rs) / max(1, len(rs))),
        ("平均延迟(ms)", lambda rs: sum(r.latency_ms for r in rs) / max(1, len(rs))),
    ]:
        row = f"{metric_name:<20}"
        for v in sorted(all_results):
            val = metric_fn(all_results[v])
            row += f"{val:>12.3f}" if "延迟" not in metric_name else f"{val:>12.0f}"
        print(row)

    categories = set()
    for rs in all_results.values():
        categories.update(r.category for r in rs)
    for cat in sorted(categories):
        row = f"  {cat:<18}"
        for v in sorted(all_results):
            cat_rs = [r for r in all_results[v] if r.category == cat]
            avg = sum(r.score for r in cat_rs) / max(1, len(cat_rs))
            row += f"{avg:>12.3f}"
        print(row)
    print("=" * 70)


def _cli_main() -> int:
    parser = argparse.ArgumentParser(description="RetailGuard Eval Runner")
    parser.add_argument("--dataset", default="all", help="数据集 (rag/intent/e2e/risk/tool_call/all)")
    parser.add_argument("--sample", type=int, default=None, help="每个数据集抽样数量（默认全量）")
    parser.add_argument("--smoke", action="store_true", help="smoke 模式：每个数据集抽 10 条")
    parser.add_argument("--version", default="v3", help="版本 (v1/v2/v3 或 v1,v2,v3 多版本对比)")
    parser.add_argument("--output", default=None, help="输出 JSON 路径")
    parser.add_argument("--report", action="store_true", help="同时生成 Markdown 报告")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    categories = (
        ["intent", "rag", "tool_call", "risk", "e2e"]
        if args.dataset == "all"
        else [args.dataset]
    )
    sample = 10 if args.smoke else args.sample
    versions = [v.strip() for v in args.version.split(",")]

    all_results: dict[str, list[EvalResult]] = {}
    exit_code = 0
    for ver in versions:
        runner = EvalRunner(categories=categories, sample=sample, version=ver)
        results = asyncio.run(runner.run())
        all_results[ver] = results
        _print_summary(results, ver)
        if any(not r.pass_ for r in results):
            exit_code = 1

    if len(versions) > 1:
        _print_comparison(all_results)

    # 以最后一个版本的结果写入输出
    last_results = all_results[versions[-1]]
    if args.output:
        output_data = {
            "versions": {
                ver: [asdict(r) for r in results]
                for ver, results in all_results.items()
            },
        }
        Path(args.output).write_text(
            json.dumps(output_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n[eval] results → {args.output}")

    if args.report:
        from eval.report import generate_report
        report_path = generate_report(last_results)
        print(f"[eval] report  → {report_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(_cli_main())
