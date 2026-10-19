"""真实 PostgreSQL：V197 / R197 本机优先路由迁移（spec llm-ocr-local-first-routing §4）。

为什么必须真库：迁移是 PG 专有 SQL（枚举类型转换、``~*`` 正则、部分唯一索引），SQLite 测不到；
R197 的关键性质是「本机、服务器同时启用时先停用本机行，再恢复旧的每类一条索引」——顺序错了
恢复索引那一步就会因重复而失败，只有真跑才知道。

隔离：同一事务里建临时 schema，``search_path`` 只含它（不含 public ⇒ 迁移里的 DROP INDEX /
ALTER TABLE 不可能解析到正式表）；枚举按正式库的取值复制一份，表由 ORM metadata 建（V197 之后的形态）。
整个事务最后回滚，不留任何对象。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.pg_only

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
LOCAL = "http://localhost:8100/v1"
ENTERPRISE = "https://ai.gt-china.com.cn:10010/v1"
OCR_HOST = "https://ai.gt-china.com.cn:10080"
NEW_INDEXES = {
    "uq_ai_model_config_active_chat_route",
    "uq_ai_model_config_active_embedding",
    "uq_ai_model_config_active_ocr_route",
}
OLD_INDEXES = {"uq_ai_model_config_active_non_ocr", "uq_ai_model_config_active_ocr_capability"}

# (名称, 类型, 提供商, 端点, OCR 能力, OCR 协议, 部署位置) —— V197 之后的形态，全部启用
_DUAL_ACTIVE = [
    ("Qwen3.5", "chat", "openai_compatible", LOCAL, None, None, "local"),
    ("qwen3.8", "chat", "custom", ENTERPRISE, None, None, "server"),
    ("paddleocr", "ocr", "paddleocr", None, "ocr", "local", "local"),
    ("paddleocrv6", "ocr", "paddleocr", OCR_HOST, "ocr", "paddlex_json", "server"),
    ("paddleocrvl-1.6", "ocr", "paddleocr", OCR_HOST, "layout_parsing", "paddlex_json", "server"),
    ("Qwen3.5-embed", "embedding", "openai_compatible", LOCAL, None, None, "local"),
]
# V197 之前的形态（无 deployment 列），覆盖回填的每个分支；都不启用
_PRE_V197 = [
    ("ollama-default", "chat", "ollama", None),
    ("vllm-default", "chat", "openai_compatible", None),
    ("deepseek-default", "chat", "deepseek", None),
    ("loopback-ip", "chat", "custom", "http://127.0.0.1:9000/v1"),
    ("loopback-v6", "chat", "custom", "http://[::1]:8100/v1"),
    ("loopback-upper", "chat", "custom", "https://LOCALHOST:8443/v1"),
    ("not-loopback", "chat", "custom", "http://localhost.localdomain/v1"),
    ("lan-gateway", "chat", "custom", "http://192.168.0.41:10010/v1"),
]


async def _run_file(conn, name: str) -> None:
    from app.core.migration_runner import MigrationRunner

    sql = (MIGRATIONS / name).read_text(encoding="utf-8")
    for statement in MigrationRunner._split_sql_statements(sql):
        await conn.exec_driver_sql(statement)


async def _indexes(conn, schema: str) -> set[str]:
    rows = await conn.execute(
        sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = :s AND tablename = 'ai_model_config'"),
        {"s": schema},
    )
    return {row[0] for row in rows}


async def _rejected(conn, sql: str, params: dict) -> bool:
    """在 SAVEPOINT 里执行一条应被约束拒绝的语句；被拒返回 True，事务照常可用。"""
    try:
        async with conn.begin_nested():
            await conn.execute(sa.text(sql), params)
    except sa.exc.DBAPIError:
        return True
    return False


async def _scenario() -> dict:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.models.ai_models import AIModelConfig

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise RuntimeError("本用例必须真实 PostgreSQL（DATABASE_URL 不是 postgresql）")
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=ssl_off)
    schema = f"kiro_v197_{uuid.uuid4().hex[:10]}"
    out: dict = {"schema": schema}
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                await _build_post_v197_table(conn, schema, AIModelConfig)
                await _phase_rollback(conn, schema, out)
                await _phase_upgrade(conn, schema, out)
            finally:
                await trans.rollback()
    finally:
        await engine.dispose()
    return out


async def _build_post_v197_table(conn, schema: str, model) -> None:
    await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    # 只含临时 schema：迁移里不带 schema 的 DROP INDEX / ALTER TABLE 不可能落到 public；
    # 建表时 SQLAlchemy 按 ORM 枚举在这里新建 ai_model_type_enum / ai_provider_enum。
    await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
    await conn.run_sync(lambda sync_conn: model.__table__.create(sync_conn))
    current = (await conn.execute(sa.text("SELECT current_schema()"))).scalar_one()
    assert current == schema, f"search_path 未生效：{current}"


_INSERT_POST = sa.text(
    "INSERT INTO ai_model_config (id, model_name, model_type, provider, endpoint_url, ocr_capability,"
    " ocr_protocol, deployment, is_active, is_deleted) VALUES (gen_random_uuid(), :name,"
    " CAST(:mt AS ai_model_type_enum), CAST(:pv AS ai_provider_enum), :ep, :cap, :proto, :dep, true, false)"
)
_INSERT_PRE = sa.text(
    "INSERT INTO ai_model_config (id, model_name, model_type, provider, endpoint_url, is_active, is_deleted)"
    " VALUES (gen_random_uuid(), :name, CAST(:mt AS ai_model_type_enum), CAST(:pv AS ai_provider_enum),"
    " :ep, false, false)"
)


async def _phase_rollback(conn, schema: str, out: dict) -> None:
    """R197：本机、服务器同时启用的状态下回滚 —— 先停本机行，再恢复每类一条的旧索引。"""
    for name, mt, pv, ep, cap, proto, dep in _DUAL_ACTIVE:
        await conn.execute(_INSERT_POST, {"name": name, "mt": mt, "pv": pv, "ep": ep, "cap": cap, "proto": proto, "dep": dep})
    out["indexes_before_rollback"] = await _indexes(conn, schema)
    await _run_file(conn, "R197__ai_model_config_deployment_local_first_routing.sql")
    out["active_after_rollback"] = set((await conn.execute(sa.text(
        "SELECT model_name FROM ai_model_config WHERE is_active"
    ))).scalars().all())
    out["indexes_after_rollback"] = await _indexes(conn, schema)
    out["deployment_column_after_rollback"] = (await conn.execute(sa.text(
        "SELECT count(*) FROM information_schema.columns"
        " WHERE table_schema = :s AND table_name = 'ai_model_config' AND column_name = 'deployment'"
    ), {"s": schema})).scalar_one()


async def _phase_upgrade(conn, schema: str, out: dict) -> None:
    """V197：在回滚后的旧形态上重新升级 —— 回填与运行时分类逐行一致，新索引按部署位置约束。"""
    from app.models.ai_models import AIProvider
    from app.services.llm_runtime import classify_model_deployment

    for name, mt, pv, ep in _PRE_V197:
        await conn.execute(_INSERT_PRE, {"name": name, "mt": mt, "pv": pv, "ep": ep})
    await _run_file(conn, "V197__ai_model_config_deployment_local_first_routing.sql")

    rows = (await conn.execute(sa.text(
        "SELECT model_name, provider::text, endpoint_url, ocr_protocol, deployment FROM ai_model_config"
    ))).all()
    out["backfill"] = {row[0]: row[4] for row in rows}
    out["runtime"] = {
        row[0]: classify_model_deployment(
            SimpleNamespace(endpoint_url=row[2], provider=AIProvider(row[1]), ocr_protocol=row[3])
        )
        for row in rows
    }
    out["indexes_after_upgrade"] = await _indexes(conn, schema)

    ids = {row[0]: row[1] for row in (await conn.execute(sa.text("SELECT model_name, id FROM ai_model_config"))).all()}
    activate = "UPDATE ai_model_config SET is_active = true WHERE id = :id"
    # 回滚时被停用的本机对话行：服务器行仍启用，本机槽位空着 ⇒ 可以重新启用
    out["reenable_local_chat_rejected"] = await _rejected(conn, activate, {"id": ids["Qwen3.5"]})
    out["second_local_chat_rejected"] = await _rejected(conn, activate, {"id": ids["vllm-default"]})
    out["second_server_chat_rejected"] = await _rejected(conn, activate, {"id": ids["deepseek-default"]})
    out["local_ocr_beside_server_rejected"] = await _rejected(conn, activate, {"id": ids["paddleocr"]})
    out["bad_deployment_rejected"] = await _rejected(
        conn, "UPDATE ai_model_config SET deployment = 'cloud' WHERE id = :id", {"id": ids["lan-gateway"]}
    )
    out["null_deployment_rejected"] = await _rejected(
        conn, "UPDATE ai_model_config SET deployment = NULL WHERE id = :id", {"id": ids["lan-gateway"]}
    )


def test_v197_r197_roundtrip_on_real_postgres():
    from app.models.ai_model_options import active_route_indexes

    out = asyncio.run(_scenario())

    # ORM 与迁移同一组索引名（SQLite 测试建表用 ORM，真库用迁移：两边必须一致）
    assert {index.name for index in active_route_indexes()} == NEW_INDEXES
    assert NEW_INDEXES <= out["indexes_before_rollback"]

    # R197：同类型（OCR 同能力槽）本机 + 服务器都启用时只保留服务器；向量本来只有一条，保留
    assert out["active_after_rollback"] == {"qwen3.8", "paddleocrv6", "paddleocrvl-1.6", "Qwen3.5-embed"}
    assert OLD_INDEXES <= out["indexes_after_rollback"]
    assert not (NEW_INDEXES & out["indexes_after_rollback"])
    assert out["deployment_column_after_rollback"] == 0

    # V197：回填与运行时 classify_model_deployment 逐行一致（含无端点取 provider 默认端点、大小写、IPv6）
    assert out["backfill"] == out["runtime"]
    assert out["backfill"]["Qwen3.5"] == "local" and out["backfill"]["paddleocr"] == "local"
    assert out["backfill"]["ollama-default"] == "local" and out["backfill"]["deepseek-default"] == "server"
    assert out["backfill"]["not-loopback"] == "server" and out["backfill"]["lan-gateway"] == "server"
    assert NEW_INDEXES <= out["indexes_after_upgrade"]
    assert not (OLD_INDEXES & out["indexes_after_upgrade"])

    # 启用约束按部署位置：本机、服务器各一条可并存，同位置第二条被拒
    assert out["reenable_local_chat_rejected"] is False
    assert out["second_local_chat_rejected"] is True
    assert out["second_server_chat_rejected"] is True
    assert out["local_ocr_beside_server_rejected"] is False
    assert out["bad_deployment_rejected"] is True
    assert out["null_deployment_rejected"] is True
