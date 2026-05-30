"""模型规格表：profile → 主备模型 + provider 配置。

设计.md §7.3。W1 实现最小可用版本（light + medium），完整路由 W4 引入。
配置最终应迁移到 config/model_routing.yaml；W1 暂硬编码。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Provider = Literal["openai", "anthropic", "deepseek", "glm", "dashscope", "mimo", "echo"]


@dataclass
class ModelSpec:
    """单个模型的调用规格。"""

    name: str
    provider: Provider
    base_url: str | None = None
    max_tokens: int = 2048
    temperature: float = 0.7
    # 价格：input/1k tokens, output/1k tokens（USD，仅用于成本计算）
    price_in_per_1k: float = 0.0
    price_out_per_1k: float = 0.0
    # 标识是否流式
    streaming: bool = True
    # 备用回退
    extras: dict[str, str] = field(default_factory=dict)


# === 默认 profile 表（W1 简化版） ===
PROFILE_SPECS: dict[str, list[ModelSpec]] = {
    # 轻量：意图识别 / greeting / query 改写
    "light": [
        ModelSpec(
            name="mimo-v2.5",
            provider="mimo",
            max_tokens=512,
            temperature=0.3,
            price_in_per_1k=0.0001,
            price_out_per_1k=0.0002,
        ),
        ModelSpec(
            name="mimo-v2-pro",
            provider="mimo",
            max_tokens=512,
            temperature=0.3,
            price_in_per_1k=0.0002,
            price_out_per_1k=0.0004,
        ),
    ],
    # 中等：KnowledgeAgent / TicketHandler / 风控 LLM 评分
    "medium": [
        ModelSpec(
            name="mimo-v2.5",
            provider="mimo",
            max_tokens=2048,
            temperature=0.5,
            price_in_per_1k=0.0001,
            price_out_per_1k=0.0002,
        ),
        ModelSpec(
            name="mimo-v2-pro",
            provider="mimo",
            max_tokens=2048,
            temperature=0.5,
            price_in_per_1k=0.0002,
            price_out_per_1k=0.0004,
        ),
    ],
    # 重量：Planner / Critic（W3 真正使用）
    "heavy": [
        ModelSpec(
            name="mimo-v2.5-pro",
            provider="mimo",
            max_tokens=4096,
            temperature=0.4,
            price_in_per_1k=0.0003,
            price_out_per_1k=0.0006,
        ),
        ModelSpec(
            name="mimo-v2.5",
            provider="mimo",
            max_tokens=4096,
            temperature=0.4,
            price_in_per_1k=0.0001,
            price_out_per_1k=0.0002,
        ),
    ],
}


__all__ = ["ModelSpec", "Provider", "PROFILE_SPECS"]
