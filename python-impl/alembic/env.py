"""Alembic 迁移环境配置。"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.base import Base
import db.models  # noqa: F401 — 确保所有模型注册到 Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# 优先使用环境变量覆盖
_pg_dsn = os.getenv("PG_DSN_SYNC") or os.getenv("PG_DSN")
if _pg_dsn:
    # alembic 需要同步 driver
    _pg_dsn = _pg_dsn.replace("+asyncpg", "+psycopg").replace("+aiosqlite", "")
    config.set_main_option("sqlalchemy.url", _pg_dsn)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
