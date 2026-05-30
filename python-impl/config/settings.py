"""应用级配置：pydantic-settings 加载 .env → defaults → 暴露单例 settings。

设计.md §8.2 配置分层：defaults → .env → YAML（业务参数）→ Redis 热加载（运行时）。
本文件实现前三层；Redis 热加载在 W4 引入。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent  # python-impl/


class Settings(BaseSettings):
    """全局配置入口。"""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === 数据库 ===
    PG_DSN: str = "postgresql+psycopg://retailguard:retailguard@localhost:15432/retailguard"
    PG_DSN_SYNC: str = "postgresql+psycopg://retailguard:retailguard@localhost:15432/retailguard"
    REDIS_URL: str = "redis://localhost:16379/0"
    QDRANT_URL: str = "http://localhost:16333"
    QDRANT_API_KEY: SecretStr | None = None

    # === LLM ===
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    ANTHROPIC_API_KEY: SecretStr | None = None
    DEEPSEEK_API_KEY: SecretStr | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    GLM_API_KEY: SecretStr | None = None
    GLM_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    DASHSCOPE_API_KEY: SecretStr | None = None
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MIMO_API_KEY: SecretStr | None = None
    MIMO_BASE_URL: str = "https://token-plan-cn.xiaomimimo.com/v1"

    # === 鉴权 ===
    JWT_SECRET: SecretStr = SecretStr("change_me_min_32_chars_for_production_use")
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_TTL: int = 1800
    REFRESH_TOKEN_TTL: int = 604800

    # === Langfuse ===
    LANGFUSE_PUBLIC_KEY: SecretStr | None = None
    LANGFUSE_SECRET_KEY: SecretStr | None = None
    LANGFUSE_HOST: str = "http://localhost:13000"

    # === MCP ===
    MCP_API_TOKEN: SecretStr | None = None

    # === 应用 ===
    APP_ENV: Literal["dev", "prod", "test"] = "dev"
    APP_DEFAULT_TENANT: str = "tenant-a"
    APP_DEFAULT_VERSION: Literal["v1", "v2", "v3"] = "v3"
    LOG_LEVEL: str = "INFO"

    # === RAG ===
    RAG_EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    RAG_RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RAG_COLLECTION: str = "kb_v1"
    RAG_EMBED_DIM: int = 1024
    # 本地回退：测试/无 GPU 环境下使用 hashing-based fake embedder，不下载真模型
    RAG_USE_LOCAL_FALLBACK: bool = True
    RAG_PARENT_CHARS: int = 1200
    RAG_CHILD_CHARS: int = 350
    RAG_OVERLAP_CHARS: int = 80
    RAG_SHORT_DOC_CHARS: int = 400
    RAG_RERANK_THRESHOLD: float = 0.3
    RAG_TOPK_VECTOR: int = 20
    RAG_TOPK_BM25: int = 20
    RAG_TOPK_RERANK: int = 5

    # === 知识库目录 ===
    KB_DIR: str = str(ROOT_DIR.parent / "docs" / "knowledge_base")

    @property
    def is_dev(self) -> bool:
        return self.APP_ENV == "dev"

    @property
    def is_test(self) -> bool:
        return self.APP_ENV == "test"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

__all__ = ["Settings", "settings", "get_settings", "ROOT_DIR"]
