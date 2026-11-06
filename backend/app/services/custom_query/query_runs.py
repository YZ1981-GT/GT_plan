"""高级查询运行记录登记（AQF §5）。

职责：将查询请求规范化为定义摘要，按运行身份幂等写入 query_runs，返回运行编号；
以及版本向量、显示标签的辅助工具。

降级策略（R1.6）：迁移未落库或写库出错时，返回 ``recorded=False`` 并带中文原因，
不让查询或导出失败。
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ─── 规范化 ─────────────────────────────────────────────────────────────────

_DEFINITION_EXCLUDE_BUSINESS = frozenset({"limit", "offset", "count_token"})
_DEFINITION_EXCLUDE_EXPORT = frozenset({"limit", "offset", "count_token", "headers", "file_name"})


def _canonical_value(value: Any) -> Any:
    """递归规范化：UUID 转小写字符串，dict 键排序，list 保序。"""
    if isinstance(value, dict):
        return {k: _canonical_value(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, str):
        # 尝试把合法 UUID 统一转小写
        try:
            return str(uuid.UUID(value)).lower()
        except (ValueError, AttributeError):
            return value
    return value


def canonical_json(value: Any) -> str:
    """规范 JSON：键排序，ensure_ascii=False，最紧凑分隔符。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def normalize_definition(body: Any, *, entry: str = "business") -> dict:
    """从请求体生成规范化定义 dict（去掉分页与凭证字段）。

    业务视图：去掉 limit / offset / count_token；
    导出请求：另外去掉 headers / file_name。
    结果键排序、UUID 统一小写，与 PBT 证明一致（R1.2）。
    """
    exclude = _DEFINITION_EXCLUDE_EXPORT if entry == "export" else _DEFINITION_EXCLUDE_BUSINESS
    if hasattr(body, "model_dump"):
        raw = body.model_dump(mode="json")
    elif hasattr(body, "__dict__"):
        raw = dict(vars(body))
    else:
        raw = dict(body)
    filtered = {k: v for k, v in raw.items() if k not in exclude}
    return _canonical_value(filtered)


def definition_hash(definition: dict) -> str:
    """SHA-256 摘要（16 进制小写 64 字符）。"""
    return hashlib.sha256(canonical_json(definition).encode()).hexdigest()


# ─── 登记 ────────────────────────────────────────────────────────────────────

_UPSERT_PG = text("""
INSERT INTO query_runs (
    id, user_id, entry, origin, template_id,
    project_id, year, source_key,
    definition, definition_hash, definition_version,
    scope, labels, version_vector, vector_hash, vector_weak,
    captured_at,
    execution_count, first_executed_at, last_executed_at,
    last_total, last_warnings,
    created_at, updated_at
) VALUES (
    :id, :user_id, :entry, :origin, :template_id,
    :project_id, :year, :source_key,
    cast(:definition AS jsonb), :definition_hash, 1,
    cast(:scope AS jsonb), cast(:labels AS jsonb),
    cast(:version_vector AS jsonb), :vector_hash, :vector_weak,
    :captured_at,
    1, now(), now(),
    :last_total, cast('[]' AS jsonb),
    now(), now()
)
ON CONFLICT ON CONSTRAINT uq_query_runs_identity DO UPDATE
   SET execution_count  = query_runs.execution_count + 1,
       last_executed_at = now(),
       last_total       = EXCLUDED.last_total,
       hidden_at        = NULL,
       updated_at       = now()
 WHERE query_runs.last_executed_at < now() - interval '60 seconds'
    OR query_runs.hidden_at IS NOT NULL
RETURNING id, execution_count
""")

_SELECT_BY_IDENTITY_PG = text("""
SELECT id, execution_count
  FROM query_runs
 WHERE user_id = :user_id
   AND entry   = :entry
   AND definition_hash = :definition_hash
   AND vector_hash     = :vector_hash
 LIMIT 1
""")

# SQLite fallback（单测环境）
_INSERT_SQLITE = text("""
INSERT OR IGNORE INTO query_runs (
    id, user_id, entry, origin, template_id,
    project_id, year, source_key,
    definition, definition_hash, definition_version,
    scope, labels, version_vector, vector_hash, vector_weak,
    captured_at,
    execution_count, first_executed_at, last_executed_at,
    last_total, last_warnings,
    created_at, updated_at
) VALUES (
    :id, :user_id, :entry, :origin, :template_id,
    :project_id, :year, :source_key,
    :definition, :definition_hash, 1,
    :scope, :labels,
    :version_vector, :vector_hash, :vector_weak,
    :captured_at,
    1, :now, :now,
    :last_total, '[]',
    :now, :now
)
""")

_UPDATE_SQLITE = text("""
UPDATE query_runs
   SET execution_count  = execution_count + 1,
       last_executed_at = :now,
       last_total       = :last_total,
       hidden_at        = NULL,
       updated_at       = :now
 WHERE user_id = :user_id
   AND entry   = :entry
   AND definition_hash = :definition_hash
   AND vector_hash     = :vector_hash
   AND (last_executed_at < datetime(:now, '-60 seconds') OR hidden_at IS NOT NULL)
""")


def _build_params(
    *,
    user_id: uuid.UUID,
    entry: str,
    origin: str,
    template_id: uuid.UUID | None,
    project_id: str | uuid.UUID | None,
    year: int | None,
    source_key: str,
    definition: dict,
    def_hash: str,
    scope: dict,
    labels: dict,
    version_vector: dict,
    vector_hash: str,
    vector_weak: bool,
    captured_at: datetime,
    last_total: int | None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "user_id": str(user_id),
        "entry": entry,
        "origin": origin,
        "template_id": str(template_id) if template_id else None,
        "project_id": str(project_id) if project_id else None,
        "year": year,
        "source_key": source_key[:200],
        "definition": canonical_json(definition),
        "definition_hash": def_hash,
        "scope": canonical_json(scope),
        "labels": canonical_json(labels),
        "version_vector": canonical_json(version_vector),
        "vector_hash": vector_hash,
        "vector_weak": vector_weak,
        "captured_at": captured_at.isoformat(),
        "last_total": last_total,
        "now": datetime.now(timezone.utc).isoformat(),
    }


async def record_run(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entry: str,
    origin: str = "direct",
    template_id: uuid.UUID | None = None,
    project_id: str | uuid.UUID | None,
    year: int | None,
    source_key: str,
    definition: dict,
    scope: dict | None = None,
    labels: dict | None = None,
    version_vector: dict | None = None,
    vector_hash: str = "",
    vector_weak: bool = False,
    captured_at: datetime | None = None,
    last_total: int | None = None,
) -> dict:
    """幂等登记运行记录，返回 {id, recorded, execution_count, reason?}。

    登记失败时返回 recorded=False 并带中文原因，不抛异常（R1.6）。
    """
    from app.services.custom_query.query_evidence import query_evidence_available

    if not await query_evidence_available(db):
        return {"recorded": False, "reason": "查询证据功能尚未启用（数据库迁移未执行）"}

    def_hash = definition_hash(definition)
    vhash = vector_hash or ("0" * 64)
    params = _build_params(
        user_id=user_id,
        entry=entry,
        origin=origin,
        template_id=template_id,
        project_id=project_id,
        year=year,
        source_key=source_key,
        definition=definition,
        def_hash=def_hash,
        scope=scope or {},
        labels=labels or {},
        version_vector=version_vector or {},
        vector_hash=vhash,
        vector_weak=vector_weak,
        captured_at=captured_at or datetime.now(timezone.utc),
        last_total=last_total,
    )

    dialect = db.get_bind().dialect.name
    try:
        async with db.begin_nested():
            if dialect == "postgresql":
                row = (await db.execute(_UPSERT_PG, params)).first()
                if row is None:
                    # 60 秒内重复执行，未更新：回读
                    row = (await db.execute(
                        _SELECT_BY_IDENTITY_PG,
                        {"user_id": params["user_id"], "entry": entry,
                         "definition_hash": def_hash, "vector_hash": vhash},
                    )).first()
                if row is not None:
                    return {"recorded": True, "id": str(row[0]), "execution_count": row[1]}
            else:
                # SQLite 单测
                await db.execute(_INSERT_SQLITE, params)
                await db.execute(_UPDATE_SQLITE, {
                    "user_id": params["user_id"], "entry": entry,
                    "definition_hash": def_hash, "vector_hash": vhash,
                    "last_total": last_total, "now": params["now"],
                })
                sel = await db.execute(
                    text("SELECT id, execution_count FROM query_runs WHERE user_id=:u AND entry=:e AND definition_hash=:d AND vector_hash=:v LIMIT 1"),
                    {"u": params["user_id"], "e": entry, "d": def_hash, "v": vhash},
                )
                row = sel.first()
                if row is not None:
                    return {"recorded": True, "id": str(row[0]), "execution_count": row[1]}
        return {"recorded": False, "reason": "运行记录未写入（无返回行）"}
    except Exception as exc:
        logger.warning("AQF 运行记录登记失败: %s", exc, exc_info=True)
        return {"recorded": False, "reason": f"运行记录写入失败：{type(exc).__name__}"}


__all__ = [
    "normalize_definition", "definition_hash", "canonical_json",
    "record_run",
]
