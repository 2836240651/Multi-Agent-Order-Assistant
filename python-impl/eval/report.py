"""eval/report.py：将 EvalResult 列表渲染为 Markdown 报告（可选 matplotlib 图表）。

用法（通常由 eval.runner CLI 调用）：
    from eval.report import generate_report
    path = generate_report(results)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eval.runner import EvalResult

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent.parent / "docs" / "eval_reports"


def generate_report(results: list[EvalResult], output_dir: Path | None = None) -> Path:
    """生成 Markdown 报告 + 可选 matplotlib 图表，返回报告路径。"""
    out = Path(output_dir) if output_dir else REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out / f"eval_{ts}.md"

    lines = _build_markdown(results, ts)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    _try_render_charts(results, out, ts)

    return report_path


def _build_markdown(results: list[EvalResult], ts: str) -> list[str]:
    from dataclasses import asdict

    total = len(results)
    passed = sum(1 for r in results if r.pass_)
    avg_score = sum(r.score for r in results) / max(1, total)
    avg_lat = sum(r.latency_ms for r in results) / max(1, total)
    pass_rate = passed / max(1, total) * 100

    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    lines: list[str] = [
        f"# Eval Report — {ts[:8]}",
        "",
        f"> 生成时间：{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}",
        "",
        "## 总览",
        "",
        "| 指标 | 值 |",
        "|------|----|",
        f"| 用例总数 | {total} |",
        f"| 通过数 | {passed} |",
        f"| 通过率 | {pass_rate:.1f}% |",
        f"| 平均得分 | {avg_score:.3f} |",
        f"| 平均延迟 | {avg_lat:.0f} ms |",
        "",
        "## 按类别汇总",
        "",
        "| 类别 | 总数 | 通过 | 通过率 | 均分 | 均延迟(ms) |",
        "|------|------|------|--------|------|------------|",
    ]

    for cat, cat_results in sorted(by_cat.items()):
        p = sum(1 for r in cat_results if r.pass_)
        s = sum(r.score for r in cat_results) / max(1, len(cat_results))
        l = sum(r.latency_ms for r in cat_results) / max(1, len(cat_results))
        pr = p / max(1, len(cat_results)) * 100
        lines.append(f"| {cat} | {len(cat_results)} | {p} | {pr:.1f}% | {s:.3f} | {l:.0f} |")

    lines += ["", "## 失败用例明细", ""]

    failed = [r for r in results if not r.pass_]
    if not failed:
        lines.append("_所有用例均通过。_")
    else:
        lines += [
            "| case_id | category | score | error/detail |",
            "|---------|----------|-------|--------------|",
        ]
        for r in failed[:50]:
            note = r.error or r.detail or ""
            note = note[:80].replace("|", "\\|")
            lines.append(f"| {r.case_id} | {r.category} | {r.score:.3f} | {note} |")
        if len(failed) > 50:
            lines.append(f"\n_（仅展示前 50 条，共 {len(failed)} 条失败）_")

    lines += ["", "## RAG 指标详情", ""]

    rag_results = [r for r in results if r.category == "rag"]
    if rag_results:
        metric_keys = ["keyword_match", "cit_hit", "ragas_context_precision",
                       "ragas_context_recall", "ragas_faithfulness", "ragas_answer_relevancy"]
        lines += [
            "| 指标 | 均值 |",
            "|------|------|",
        ]
        for k in metric_keys:
            vals = [r.actual.get(k, 0) for r in rag_results if isinstance(r.actual.get(k), (int, float))]
            if vals:
                avg = sum(vals) / len(vals)
                label = k.replace("ragas_", "")
                lines.append(f"| {label} | {avg:.3f} |")
    else:
        lines.append("_无 RAG 用例。_")

    lines += ["", "---", f"_报告由 `eval.runner` 自动生成，共 {total} 条用例。_"]
    return lines


def _try_render_charts(results: list[EvalResult], out: Path, ts: str) -> None:
    """尝试用 matplotlib 绘制通过率柱状图；未安装时静默跳过。"""
    try:
        import matplotlib  # type: ignore[import]
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore[import]
    except ImportError:
        logger.debug("matplotlib not installed, skipping chart generation")
        return

    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    cats = sorted(by_cat.keys())
    pass_rates = [
        sum(1 for r in by_cat[c] if r.pass_) / max(1, len(by_cat[c])) * 100
        for c in cats
    ]
    avg_scores = [
        sum(r.score for r in by_cat[c]) / max(1, len(by_cat[c]))
        for c in cats
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    ax1.bar(cats, pass_rates, color="#4C9BE8")
    ax1.set_title("通过率 (%)")
    ax1.set_ylabel("%")
    ax1.set_ylim(0, 105)
    for i, v in enumerate(pass_rates):
        ax1.text(i, v + 1, f"{v:.1f}%", ha="center", fontsize=9)

    ax2.bar(cats, avg_scores, color="#4CAF50")
    ax2.set_title("平均得分")
    ax2.set_ylabel("score")
    ax2.set_ylim(0, 1.05)
    for i, v in enumerate(avg_scores):
        ax2.text(i, v + 0.01, f"{v:.3f}", ha="center", fontsize=9)

    fig.suptitle(f"Eval Summary — {ts[:8]}", fontsize=12)
    plt.tight_layout()

    chart_path = out / f"eval_{ts}_chart.png"
    plt.savefig(chart_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("chart saved → %s", chart_path)


__all__ = ["generate_report"]
