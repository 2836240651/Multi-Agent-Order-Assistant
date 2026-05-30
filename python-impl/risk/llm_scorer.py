"""risk/llm_scorer.py：LLM 语义风险评分层（中等模型）。

Pydantic 强约束输出；LLM 不可用时设 unavailable=True 并返回 score=50（中立），
融合层会重归一化权重以排除 LLM 项。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "llm_scorer.md"

_FALLBACK_SYSTEM = """你是电商风控评估专家。根据退款申请信息，输出 JSON 风险评分。
格式：{"score": 0-100, "reason": "简短原因（30字内）", "confidence": 0.0-1.0}
不要输出其他内容。分数含义：0=完全正常，100=极高风险。"""


def _load_system_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8").strip()
    return _FALLBACK_SYSTEM


class LLMScorerOutput(BaseModel):
    score: float = Field(ge=0, le=100)
    reason: str = Field(max_length=200)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)

    @field_validator("score", mode="before")
    @classmethod
    def clamp_score(cls, v):
        return max(0.0, min(100.0, float(v)))


@dataclass
class LLMResult:
    score: float
    reason: str
    confidence: float
    unavailable: bool = False


def _safe_parse(text: str) -> LLMScorerOutput | None:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return LLMScorerOutput.model_validate(json.loads(text[start:end + 1]))
    except Exception as exc:
        logger.debug("llm_scorer parse error: %s", exc)
        return None


def _heuristic_risk_score(refund: dict[str, Any]) -> LLMResult:
    """无真实 LLM 时的启发式评分（评测/echo 模式）。"""
    amount = float(refund.get("amount", 0))
    rate = float(refund.get("refund_rate_30d", 0))
    desc = str(refund.get("description", "") or refund.get("reason", ""))
    score = 5.0
    if amount >= 5000:
        score += 70
    elif amount >= 2000:
        score += 50
    elif amount >= 500:
        score += 50
    if rate >= 0.7:
        score += 45
    elif rate >= 0.45:
        score += 28
    if any(k in desc for k in ("批量", "代退", "恶意", "套现")):
        score += 40
    score = min(100.0, score)
    return LLMResult(
        score=score,
        reason="启发式风险估计（本地无 LLM key）",
        confidence=0.75,
        unavailable=False,
    )


async def evaluate_llm(refund: dict[str, Any]) -> LLMResult:
    """调用 LLM 评分。失败 → 启发式或 unavailable 中立分。"""
    from config import settings
    from llm import call_llm

    if settings.RAG_USE_LOCAL_FALLBACK or settings.is_test:
        return _heuristic_risk_score(refund)

    system = _load_system_prompt()
    user_content = (
        f"退款信息：\n"
        f"- 金额：¥{refund.get('amount', '?')}\n"
        f"- 下单距今：{refund.get('days_since_order', '?')} 天\n"
        f"- 收货距今：{refund.get('days_since_delivery', '?')} 天\n"
        f"- 用户近30天退款次数：{refund.get('user_refund_count_30d', 0)}\n"
        f"- 退款原因：{refund.get('reason', '未填写')}\n"
        f"- 商品描述：{refund.get('product_name', '未知')[:50]}\n"
        f"- 用户备注：{refund.get('description', '')[:100]}"
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    try:
        result = await call_llm(profile="medium", messages=messages, stream=False)
        text = result.text if hasattr(result, "text") else str(result)
        parsed = _safe_parse(text)
        if parsed:
            return LLMResult(score=parsed.score, reason=parsed.reason, confidence=parsed.confidence)
        logger.warning("llm_scorer: parse failed, using neutral score")
        return LLMResult(score=50.0, reason="[parse_failed]", confidence=0.3, unavailable=True)
    except Exception as exc:
        logger.warning("llm_scorer unavailable: %s", exc)
        return LLMResult(score=50.0, reason=f"[unavailable] {str(exc)[:60]}", confidence=0.0, unavailable=True)


__all__ = ["LLMResult", "LLMScorerOutput", "evaluate_llm"]
