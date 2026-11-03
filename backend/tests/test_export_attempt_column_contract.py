# -*- coding: utf-8 -*-
"""export 任务表 4 列的三层一致（spec runtime-performance-and-reload-hardening-followup 任务 2b）。

`/api/health` 的 `schema_drift` 长期常驻 4 条 `type_mismatch`：

    export_job_attempts.error_type         ORM=VARCHAR vs DB=TEXT
    export_job_attempts.diagnostic_detail  ORM=JSONB   vs DB=TEXT
    export_job_attempts.file_path          ORM=TEXT    vs DB=VARCHAR
    export_job_items_v2.file_path          ORM=TEXT    vs DB=VARCHAR

🔴 对齐方向**不是**「ORM 说什么就改 DB」。逐处现读写入方与前端契约后：

* `diagnostic_detail` 两处写入方写的都是**字符串**（`"".join(traceback.format_exception_only(...))`
  与超时恢复的 f-string），DB 是 TEXT，前端 `deliverableApi.ts` 声明 `string | null` 且按
  `<pre>` 纯文本展示 ⇒ 写错的是 ORM 那一层（`JSONB` + `Mapped[dict]`）。若反过来把 DB 改成
  JSONB，那两处写纯文本会当场崩（非法 JSON 字面量）—— 把一个静默不一致换成运行时故障。
* `error_type` 写的是 `type(exc).__name__`，V181 建表就是 TEXT ⇒ 同样改 ORM。
* `file_path` 写的是交付件路径（版本化文件名会追加 `_v<n>`，无长度上界）⇒ 改 DB，V223（原 V215，2026-10-30 同步改号）把
  VARCHAR(500) 放宽成 TEXT（放宽无损，不会让任何现有写入失败）。

判据：ORM 四列类型、两处写入方仍写字符串、前端 TS 契约、以及真 PG 上的实际列类型。
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
_FRONTEND_API = (
    _BACKEND.parent / "audit-platform" / "frontend" / "src" / "services" / "deliverableApi.ts"
)

#: (ORM 属性, 期望的 SQLAlchemy 类型名)。期望值写死，不从被测模型反推。
_EXPECTED_ORM_TYPES = {
    ("ExportJobAttempt", "error_type"): "TEXT",
    ("ExportJobAttempt", "diagnostic_detail"): "TEXT",
    ("ExportJobAttempt", "file_path"): "TEXT",
    ("ExportJobItem", "file_path"): "TEXT",
}


def _column_type(class_name: str, attr: str) -> str:
    from app.models import phase13_models as models

    model = getattr(models, class_name)
    column = model.__table__.c[attr]
    return str(column.type).split("(")[0].upper()


def test_orm_declares_text_for_all_four_columns():
    actual = {key: _column_type(*key) for key in _EXPECTED_ORM_TYPES}
    assert actual == _EXPECTED_ORM_TYPES


def test_diagnostic_detail_is_not_a_json_column():
    """反向判据：谁把它改回 JSONB / dict，这里就红（写入方会当场崩）。"""
    from app.models import phase13_models as models

    column = models.ExportJobAttempt.__table__.c["diagnostic_detail"]
    assert "JSON" not in str(column.type).upper()
    annotation = models.ExportJobAttempt.__annotations__.get("diagnostic_detail", "")
    assert "dict" not in str(annotation), "注解仍写 dict 会让读取方按对象用"
    assert "str" in str(annotation)


@pytest.mark.parametrize("module_path, func_name", [
    ("app.services.export_job_service", "retry_failed_items"),
    ("app.services.full_deliverables_executor", None),
])
def test_writers_assign_text_not_dict(module_path, func_name):
    """写入方给 diagnostic_detail 赋的必须是字符串表达式，不是 dict 字面量。

    AST 判据（不看文本）：找 `*.diagnostic_detail = <expr>` 的赋值，右值不得是 `ast.Dict`。
    """
    import importlib

    module = importlib.import_module(module_path)
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    assigns = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute) and target.attr == "diagnostic_detail"
            for target in node.targets
        )
    ]
    assert assigns, f"{module_path} 应有 diagnostic_detail 写入方（判据不空转）"
    for node in assigns:
        assert not isinstance(node.value, ast.Dict), ast.unparse(node)


def test_frontend_contract_declares_string():
    """跨语言契约：前端把这两列当字符串，ORM 不得再声明成对象。"""
    source = _FRONTEND_API.read_text(encoding="utf-8")
    for field in ("diagnostic_detail", "error_type", "file_path"):
        match = re.search(rf"^\s*{field}:\s*(.+)$", source, re.MULTILINE)
        assert match, f"前端契约缺 {field}"
        assert "string" in match.group(1), (field, match.group(1))


@pytest.fixture(scope="module")
def pg_column_types() -> dict[str, str]:
    import asyncio

    async def _scan() -> dict[str, str] | None:
        # 只读契约探针不借应用全局连接池：asyncpg 连接绑定创建它的 ProactorEventLoop，
        # 前一个 asyncio.run 关闭 loop 后，全局池若还留着连接，本 fixture 再 checkout 会在
        # pool_pre_ping 报 Event loop is closed。独立 NullPool engine 在同一个 loop 内创建、
        # 查询、dispose，不污染后续测试，也不受前序测试污染（见 tests/_pg_shared_engine.py）。
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from app.core.config import settings

        if not str(settings.DATABASE_URL).startswith("postgresql"):
            return None
        connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
        probe_engine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args=connect_args,
        )
        try:
            async with probe_engine.connect() as conn:
                rows = await conn.execute(sa.text(
                    "SELECT table_name || '.' || column_name, udt_name "
                    "FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND ("
                    "  (table_name = 'export_job_attempts' AND column_name IN "
                    "   ('error_type', 'diagnostic_detail', 'file_path'))"
                    "  OR (table_name = 'export_job_items_v2' AND column_name = 'file_path'))"
                ))
                return {row[0]: row[1] for row in rows}
        finally:
            await probe_engine.dispose()

    result = asyncio.run(_scan())
    if result is None:
        pytest.skip("需 PostgreSQL（V223 后的真实列类型）")
    return result


def test_pg_columns_are_text_after_v215(pg_column_types):
    assert pg_column_types == {
        "export_job_attempts.error_type": "text",
        "export_job_attempts.diagnostic_detail": "text",
        "export_job_attempts.file_path": "text",
        "export_job_items_v2.file_path": "text",
    }


def test_v215_is_idempotent_and_has_rollback():
    forward = _BACKEND / "migrations" / "V223__export_file_path_text.sql"
    rollback = _BACKEND / "migrations" / "R223__rollback_export_file_path_text.sql"
    assert forward.exists() and rollback.exists()
    text = forward.read_text(encoding="utf-8")
    # 幂等：只在列仍不是 text 时才转
    assert "udt_name <> 'text'" in text
    assert "ALTER COLUMN file_path TYPE text" in text
    back = rollback.read_text(encoding="utf-8")
    assert "varchar(500)" in back and "udt_name = 'text'" in back
