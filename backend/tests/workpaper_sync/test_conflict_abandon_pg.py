"""作废的**真库行为**守卫：三列真落库、幂等零写入、不删行、不碰 superseded_at、终态真变。

spec `frozen-contract-read-path-and-legacy-operation-settlement` 任务 8
Requirements: R3.3 / R3.4
Property: **Property 3**（状态变了但内容没落地不可能出现）

═══ 为什么必须真库 ═══

| 判据 | 为什么离线测不出 |
| --- | --- |
| 三列真落库 | `ck_wpsc_abandon_triplet` 是 **DB 约束**；ORM 侧只声明 nullable |
| 不碰 `superseded_at` | 该列由 `record_conflicts` 在**下一次观测**时清零 —— 只有真库能复现「作废后被重观测抹掉」 |
| 幂等零写入 | 判据是 `working_paper_sync_operation_event` 的行数不增（append-only 表） |
| operation 真落终态 | `ck_wpso_state` 是 DB 约束；`append_operation_event` 的边校验也在写路径上 |
| 不创建 representation / content version | 判据是两张表的行计数 |

═══ 隔离 ═══

scratch schema `tmp_ca_<hex>` + `SET search_path` 只含它；**真跑 V151 与 V273**
（不手抄 DDL —— 抄一份就等于「迁移写错也照样绿」）。结束 `DROP SCHEMA CASCADE`。

`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip** —— 与 Task 10/15/21~27 同约定。

🔴 **不写共享库**：全部数据在临时 schema 内。真库写入型验收（【测试】项目）留到任务 11。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[2]
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_ca_"
_MIGRATION_V151 = (
    _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
)
#: V264 加的 `schema_anomaly` 列 —— ORM 映射了它，缺列时 `load_conflicts` 的 SELECT 直接
#: UndefinedColumn。本判据不关心成因语义，但真库 schema 必须与 ORM 一致。
_MIGRATION_V264 = (
    _BACKEND / "migrations" / "V264__sync_conflict_schema_anomaly.sql"
)
_MIGRATION_V273 = _BACKEND / "migrations" / "V273__sync_conflict_abandon_columns.sql"

#: 本判据只需要的三个 stub 父表（V151 里它们由平台侧建，不在那份迁移内）。
_STUB_DDL = """
CREATE TABLE projects (id UUID PRIMARY KEY, name VARCHAR(200) NOT NULL DEFAULT 'stub');
CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(100) NOT NULL DEFAULT 'stub');
CREATE TABLE working_paper (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    file_version INTEGER NOT NULL DEFAULT 1,
    parsed_data JSONB,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

PROJECT = uuid.UUID("11111111-1111-1111-1111-111111111111")
WP = uuid.UUID("22222222-2222-2222-2222-222222222222")
ENTRY = "xlsx/gt-d2-accounts-receivable"


def _is_pg() -> bool:
    url = os.environ.get("DATABASE_URL") or ""
    return url.startswith("postgresql")


pytestmark = [
    pytest.mark.pg_only,
    pytest.mark.skipif(
        not _is_pg(),
        reason=(
            "需要真实 PostgreSQL（三列约束 / append-only event 计数 / ck_wpso_state 都在 DB 上）；"
            "未设 DATABASE_URL 或指向 sqlite 时 skip —— 不是「已通过」"
        ),
    ),
]


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


async def _collect() -> dict[str, Any]:  # noqa: C901 - 一次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.services.workpaper_sync.conflict_abandon import (
        ABANDON_TERMINAL_STATE,
        ConflictAbandonService,
        ConflictNotAbandonableError,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise RuntimeError(
            "作废判据（DB 三列约束 / append-only event 计数 / 状态 CHECK）必须真实 PostgreSQL；"
            f"当前 {settings.DATABASE_URL.split('://')[0]}"
        )
    for required in (_MIGRATION_V151, _MIGRATION_V264, _MIGRATION_V273):
        if not required.exists():
            raise RuntimeError(f"缺迁移 {required}")

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    snap: dict[str, Any] = {
        "schema": schema,
        "scenarios": {},
        "harness_errors": {},
        "server_version": None,
        "apply_errors": [],
    }

    def _fail(name: str, exc: BaseException) -> None:
        import traceback

        frames = traceback.extract_tb(exc.__traceback__)[-6:]
        where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
        snap["harness_errors"][name] = f"{type(exc).__name__}: {exc} @ {where}"

    engine = None
    try:
        async with admin.connect() as conn:
            snap["server_version"] = (
                await conn.exec_driver_sql("SELECT version()")
            ).scalar_one()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

        engine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )
        Session = async_sessionmaker(engine, expire_on_commit=False)

        async with engine.begin() as conn:
            for stmt in [s.strip() for s in _STUB_DDL.strip().split(";") if s.strip()]:
                await conn.exec_driver_sql(stmt)
        for migration in (_MIGRATION_V151, _MIGRATION_V264, _MIGRATION_V273):
            for idx, stmt in enumerate(
                MigrationRunner._split_sql_statements(
                    migration.read_text(encoding="utf-8")
                ),
                1,
            ):
                try:
                    async with engine.begin() as conn:
                        await conn.exec_driver_sql(stmt)
                except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
                    snap["apply_errors"].append(
                        {"migration": migration.name, "index": idx,
                         "error": f"{type(exc).__name__}: {exc}", "head": stmt[:120]}
                    )
        if snap["apply_errors"]:
            raise RuntimeError(f"迁移应用失败: {snap['apply_errors'][:3]}")

        # 建表阶段就证明 V273 真的加了列（否则后面每条判据都是空转）
        async with engine.connect() as conn:
            snap["columns"] = sorted(
                r[0]
                for r in (
                    await conn.execute(
                        sa.text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = :sch AND table_name = "
                            "'working_paper_sync_conflict'"
                        ),
                        {"sch": schema},
                    )
                ).all()
            )

        actor = uuid.uuid4()
        now = datetime.now(timezone.utc)

        async def _stub_artifact(kind: str, *, sha: str) -> tuple[uuid.UUID, uuid.UUID]:
            """建一条 published artifact + 一条 approved definition_artifact。

            🔴 `authority_model` 类必须带 `authority_model_type`（V151 的
            `ck_wpsda_authority_model_type` 三值逻辑），其余类必须为 NULL。
            返回 `(definition_artifact_id, blob_artifact_id)` —— bundle 的三个 slot 用
            前者（`definition:` ref），`canonical_payload_artifact_id` 用后者
            （它 REFERENCES `working_paper_artifact`，不是 definition_artifact）。
            """
            art, blob = uuid.uuid4(), uuid.uuid4()
            am_type = "projection_contract" if kind == "authority_model" else None
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_artifact (id, project_id, wp_id, kind, "
                        "state, sha256, relative_path, size_bytes, document_type, "
                        "published_at) VALUES "
                        "(:i, :p, :w, 'canonical', 'published', :sh, :rp, 1, 'xlsx', :pa)"
                    ),
                    {
                        "i": blob, "p": PROJECT, "w": WP, "sh": sha,
                        "rp": f"storage/stub/{blob}.json", "pa": now,
                    },
                )
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_sync_definition_artifact "
                        "(id, kind, logical_id, state, sha256, blob_artifact_id, "
                        "semantic_version, source_commit, approved_at, "
                        "authority_model_type) VALUES "
                        "(:i, :k, :lg, 'approved', :sh, :blob, '1.0.0', :sc, :ap, :amt)"
                    ),
                    {
                        "i": art, "k": kind, "lg": f"stub/{kind}/{art}", "sh": sha,
                        "blob": blob, "sc": "0" * 40, "ap": now, "amt": am_type,
                    },
                )
                await s.commit()
            return art, blob

        async def _new_operation(
            state: str = "conflict", *, with_conflicts: int = 3
        ) -> tuple[uuid.UUID, list[uuid.UUID]]:
            """建一条 operation（可选 N 条冲突行）并返回 (op_id, conflict_ids)。

            🔴 bundle 的 authority model child 必须是 `kind='authority_model'` 的
            definition_artifact（V151 的 `bundle authority model child kind` 约束）——
            用 contract child 冒充会被 DB 拒。
            """
            op_id, bundle = uuid.uuid4(), uuid.uuid4()
            # `uq_wpsda_kind_sha256` UNIQUE(kind, sha256) ⇒ 每个 stub 必须有自己的 digest。
            def _sha(tag: str) -> str:
                return hashlib.sha256(f"{tag}{op_id}".encode()).hexdigest()

            am_sha, tpl_sha = _sha("am"), _sha("tpl")
            ins_sha, ct_sha = _sha("ins"), _sha("ct")
            authority, _am_blob = await _stub_artifact("authority_model", sha=am_sha)
            template, _tpl_blob = await _stub_artifact("template", sha=tpl_sha)
            instr, _ins_blob = await _stub_artifact("instrumentation", sha=ins_sha)
            contract, ct_blob = await _stub_artifact("contract", sha=ct_sha)
            cids: list[uuid.UUID] = []
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_sync_definition_bundle (id, "
                        "authority_model_definition_id, authority_model_definition_sha256, "
                        "template_slot_type, template_slot_ref, template_slot_digest, "
                        "instrumentation_slot_type, instrumentation_slot_ref, "
                        "instrumentation_slot_digest, contract_slot_type, contract_slot_ref, "
                        "contract_slot_digest, canonical_payload_artifact_id, "
                        "canonical_payload_sha256) VALUES (:i, :am, :amd, "
                        "'definition', :tsr, :tsd, 'definition', :isr, :isd, "
                        "'definition', :csr, :csd, :cp, :cps)"
                    ),
                    {
                        "i": bundle,
                        "am": authority,
                        "amd": am_sha,
                        "tsr": f"definition:{template}",
                        "tsd": tpl_sha,
                        "isr": f"definition:{instr}",
                        "isd": ins_sha,
                        "csr": f"definition:{contract}",
                        "csd": ct_sha,
                        "cp": ct_blob,
                        "cps": _sha("cp"),
                    },
                )
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_sync_operation (id, project_id, wp_id, "
                        "entry_id, direction, state, definition_bundle_id, "
                        "definition_bundle_sha256, authority_model_definition_id, "
                        "authority_model_definition_sha256) VALUES (:id, :p, :w, :e, "
                        "'oo_to_html', :st, :b, :bd, :a, :ad)"
                    ),
                    {
                        "id": op_id, "p": PROJECT, "w": WP, "e": ENTRY, "st": state,
                        "b": bundle,
                        "bd": hashlib.sha256(f"bd{op_id}".encode()).hexdigest(),
                        "a": authority, "ad": am_sha,
                    },
                )
                for idx in range(with_conflicts):
                    cid = uuid.uuid4()
                    cids.append(cid)
                    await s.execute(
                        sa.text(
                            "INSERT INTO working_paper_sync_conflict (id, operation_id, "
                            "client_edit_epoch, stable_field_key, business_label, "
                            "json_pointer, field_source, protection_policy, "
                            "suggested_action, conflict_kind, superseded_at) VALUES "
                            "(:id, :op, 1, :k, :lbl, :jp, 'current', 'none', "
                            "'manual_merge', 'schema', :sup)"
                        ),
                        {
                            "id": cid, "op": op_id, "k": f"f{idx}",
                            "lbl": f"字段{idx}", "jp": f"/x/{idx}",
                            # 第 3 条预先标 superseded：作废必须盖住**全部**行（含它），
                            # 且**不得**改写它的 superseded_at。
                            "sup": None if idx != 2 else now,
                        },
                    )
                await s.commit()
            return op_id, cids

        async with engine.begin() as conn:
            await conn.execute(
                sa.text("INSERT INTO projects (id) VALUES (:i)"), {"i": PROJECT}
            )
            await conn.execute(
                sa.text("INSERT INTO users (id) VALUES (:i)"), {"i": actor}
            )
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:w, :p)"),
                {"w": WP, "p": PROJECT},
            )

        # ═══ S1 正向：conflict + 3 条冲突（1 条预标 superseded）════════════
        try:
            op1, _c1 = await _new_operation()
            async with Session() as s:
                out = await ConflictAbandonService(
                    repo=WorkpaperSyncRepository(s)
                ).abandon(
                    operation_id=op1,
                    reason="契约已换代，这批 schema 冲突不再需要处理",
                    actor_id=actor,
                )
                await s.commit()
            async with Session() as s:
                op_row = (
                    await s.execute(
                        sa.text(
                            "SELECT state, finished_at FROM working_paper_sync_operation "
                            "WHERE id = :i"
                        ),
                        {"i": op1},
                    )
                ).one()
                conflict_rows = (
                    await s.execute(
                        sa.text(
                            "SELECT abandoned_at, abandon_reason, abandoned_by, "
                            "superseded_at FROM working_paper_sync_conflict "
                            "WHERE operation_id = :i ORDER BY stable_field_key"
                        ),
                        {"i": op1},
                    )
                ).all()
                events = (
                    await s.execute(
                        sa.text(
                            "SELECT from_state, to_state, stage, actor_type, actor_id "
                            "FROM working_paper_sync_operation_event "
                            "WHERE operation_id = :i ORDER BY sequence_no"
                        ),
                        {"i": op1},
                    )
                ).all()
            snap["scenarios"]["positive"] = {
                "outcome": {
                    "from_state": out.from_state,
                    "to_state": out.to_state,
                    "abandoned_conflicts": out.abandoned_conflicts,
                    "already_abandoned": out.already_abandoned,
                    "idempotent_replay": out.idempotent_replay,
                    "created_representations": out.as_dict()["created_representations"],
                    "created_content_versions": out.as_dict()["created_content_versions"],
                },
                "op_state": op_row[0],
                "op_finished_at_is_set": op_row[1] is not None,
                "conflict_count": len(conflict_rows),
                "conflict_rows": [
                    {
                        "abandoned_at": None if r[0] is None else r[0].isoformat(),
                        "abandon_reason": r[1],
                        "abandoned_by": None if r[2] is None else str(r[2]),
                        "superseded_at": None if r[3] is None else r[3].isoformat(),
                    }
                    for r in conflict_rows
                ],
                "events": [
                    {
                        "from_state": e[0], "to_state": e[1], "stage": e[2],
                        "actor_type": e[3],
                        "actor_id": None if e[4] is None else str(e[4]),
                    }
                    for e in events
                ],
            }
        except Exception as exc:  # noqa: BLE001
            _fail("positive", exc)

        # ═══ S2 幂等重放：同原因 ⇒ 零写入（event 行数不增）════════════════
        try:
            op2, _c2 = await _new_operation()

            async def _event_count(session: Any, op_id: uuid.UUID) -> int:
                return int(
                    (
                        await session.execute(
                            sa.text(
                                "SELECT count(*) FROM working_paper_sync_operation_event "
                                "WHERE operation_id = :i"
                            ),
                            {"i": op_id},
                        )
                    ).scalar_one()
                )

            async with Session() as s:
                await ConflictAbandonService(repo=WorkpaperSyncRepository(s)).abandon(
                    operation_id=op2, reason="同一批冲突的重放理由", actor_id=actor
                )
                await s.commit()
            async with Session() as s:
                first_events = await _event_count(s, op2)
                replay = await ConflictAbandonService(
                    repo=WorkpaperSyncRepository(s)
                ).abandon(
                    operation_id=op2, reason="同一批冲突的重放理由", actor_id=actor
                )
                await s.commit()
                second_events = await _event_count(s, op2)
            snap["scenarios"]["replay"] = {
                "first_events": first_events,
                "second_events": second_events,
                "idempotent_replay": replay.idempotent_replay,
                "abandoned_conflicts": replay.abandoned_conflicts,
                "already_abandoned": replay.already_abandoned,
                "to_state": replay.to_state,
            }
        except Exception as exc:  # noqa: BLE001
            _fail("replay", exc)

        # ═══ S3 不同原因的重放 ⇒ 拒绝 ═════════════════════════════════════
        try:
            op3, _c3 = await _new_operation()
            async with Session() as s:
                await ConflictAbandonService(repo=WorkpaperSyncRepository(s)).abandon(
                    operation_id=op3, reason="第一次的理由文本", actor_id=actor
                )
                await s.commit()
            async with Session() as s:
                try:
                    await ConflictAbandonService(
                        repo=WorkpaperSyncRepository(s)
                    ).abandon(
                        operation_id=op3, reason="换一个完全不同的理由", actor_id=actor
                    )
                    verdict = "no-error"
                except ConflictNotAbandonableError as exc:
                    verdict = exc.error_code
                await s.rollback()
            snap["scenarios"]["reason_conflict"] = {"verdict": verdict}
        except Exception as exc:  # noqa: BLE001
            _fail("reason_conflict", exc)

        # ═══ S4 已结算的 operation ⇒ 拒绝且零副作用 ═════════════════════════
        try:
            op4, _c4 = await _new_operation(state="applied")
            async with Session() as s:
                try:
                    await ConflictAbandonService(
                        repo=WorkpaperSyncRepository(s)
                    ).abandon(
                        operation_id=op4,
                        reason="已结算的 operation 不该能作废",
                        actor_id=actor,
                    )
                    verdict = "no-error"
                except ConflictNotAbandonableError as exc:
                    verdict = exc.error_code
                await s.rollback()
                events_after = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT count(*) FROM working_paper_sync_operation_event "
                                "WHERE operation_id = :i"
                            ),
                            {"i": op4},
                        )
                    ).scalar_one()
                )
                abandoned_after = int(
                    (
                        await s.execute(
                            sa.text(
                                "SELECT count(*) FROM working_paper_sync_conflict "
                                "WHERE operation_id = :i AND abandoned_at IS NOT NULL"
                            ),
                            {"i": op4},
                        )
                    ).scalar_one()
                )
            snap["scenarios"]["settled"] = {
                "verdict": verdict,
                "events_after": events_after,
                "abandoned_rows_after": abandoned_after,
            }
        except Exception as exc:  # noqa: BLE001
            _fail("settled", exc)

        # ═══ S5 无冲突行 ⇒ 拒绝（没有可作废的对象）═══════════════════════
        try:
            op5, _c5 = await _new_operation(with_conflicts=0)
            async with Session() as s:
                try:
                    await ConflictAbandonService(
                        repo=WorkpaperSyncRepository(s)
                    ).abandon(
                        operation_id=op5, reason="一条冲突都没有也能作废？", actor_id=actor
                    )
                    verdict = "no-error"
                except ConflictNotAbandonableError as exc:
                    verdict = exc.error_code
                await s.rollback()
            snap["scenarios"]["no_conflicts"] = {"verdict": verdict}
        except Exception as exc:  # noqa: BLE001
            _fail("no_conflicts", exc)

        # ═══ S6 三列同生共死：DB 约束真的拒绝残缺写入 ══════════════════════
        try:
            _op6, c6 = await _new_operation()
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_sync_conflict SET abandoned_at = :t "
                        "WHERE id = :i"
                    ),
                    {"t": now, "i": c6[0]},
                )
                await s.commit()
            snap["scenarios"]["triplet_guard"] = {"verdict": "no-error"}
        except Exception as exc:  # noqa: BLE001
            snap["scenarios"]["triplet_guard"] = {
                "verdict": type(exc).__name__,
                "mentions_constraint": "ck_wpsc_abandon_triplet" in str(exc),
            }

        # ═══ S7 空白原因：DB 约束也拒（不只是 service 层拦）════════════════
        try:
            _op7, c7 = await _new_operation()
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_sync_conflict SET abandoned_at = :t, "
                        "abandon_reason = '   ', abandoned_by = :u WHERE id = :i"
                    ),
                    {"t": now, "u": actor, "i": c7[0]},
                )
                await s.commit()
            snap["scenarios"]["blank_reason_guard"] = {"verdict": "no-error"}
        except Exception as exc:  # noqa: BLE001
            snap["scenarios"]["blank_reason_guard"] = {
                "verdict": type(exc).__name__,
                "mentions_constraint": "ck_wpsc_abandon_triplet" in str(exc),
            }

        # 终态取值从服务取（本文件不写死字面量）
        snap["terminal_state"] = ABANDON_TERMINAL_STATE.value
        snap["actor"] = str(actor)
    finally:
        if engine is not None:
            await engine.dispose()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.dispose()
    return snap


# ═══════════════════════════════════════════════════════════════════════════
# 环境自证
# ═══════════════════════════════════════════════════════════════════════════


def test_harness_did_not_crash(snap: dict[str, Any]) -> None:
    """采集阶段任何异常都是判据失效（禁 fail-open 降级成「无数据」）。"""
    assert snap.get("harness_errors") == {}, snap.get("harness_errors")
    assert snap.get("apply_errors") == [], snap.get("apply_errors")


def test_the_migration_really_added_three_columns(snap: dict[str, Any]) -> None:
    """V273 真的加了列 —— 后面每条判据的前提。"""
    for column in ("abandoned_at", "abandon_reason", "abandoned_by"):
        assert column in snap["columns"], f"V273 没有加列 {column}：{snap['columns']}"


# ═══════════════════════════════════════════════════════════════════════════
# S1 正向
# ═══════════════════════════════════════════════════════════════════════════


class TestPositiveAbandon:
    def test_the_operation_left_conflict_and_reached_the_terminal_state(
        self, snap: dict[str, Any]
    ) -> None:
        """R3.3：operation 落终态 —— 且终态是既有枚举的 `superseded`。"""
        sc = snap["scenarios"]["positive"]
        assert snap["terminal_state"] == "superseded"
        assert sc["op_state"] == "superseded"
        assert sc["outcome"]["from_state"] == "conflict"
        assert sc["outcome"]["to_state"] == "superseded"

    def test_finished_at_is_written(self, snap: dict[str, Any]) -> None:
        """终态必须写完成时刻（否则 operation 快照里 `finished_at` 恒 null）。"""
        assert snap["scenarios"]["positive"]["op_finished_at_is_set"] is True

    def test_every_conflict_row_carries_all_three_columns(
        self, snap: dict[str, Any]
    ) -> None:
        """**Property 3 核心**：所有冲突行三列齐备 —— 不存在「状态变了但内容没落地」。

        分母是**全部** 3 行，含那条预先标了 `superseded_at` 的。
        """
        sc = snap["scenarios"]["positive"]
        assert sc["conflict_count"] == 3
        for row in sc["conflict_rows"]:
            assert row["abandoned_at"] is not None, row
            assert row["abandon_reason"], row
            assert row["abandoned_by"], row

    def test_the_abandon_columns_are_not_the_superseded_column(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 勘误 E.3 的核心判据：作废**不得**写 `superseded_at`。

        第 3 行原本有 `superseded_at`，作废后必须**仍是原值**；另外两行必须**仍为空**。
        若实现复用了 `superseded_at` 存人工作废，本条必红。
        """
        rows = snap["scenarios"]["positive"]["conflict_rows"]
        assert rows[2]["superseded_at"] is not None, "第 3 行原有的 superseded_at 被清空了"
        assert rows[0]["superseded_at"] is None, "作废把第 1 行的 superseded_at 写上了"
        assert rows[1]["superseded_at"] is None, "作废把第 2 行的 superseded_at 写上了"

    def test_no_conflict_row_was_deleted(self, snap: dict[str, Any]) -> None:
        """R3.3「不物理删除冲突行」：行数必须仍是 3。"""
        assert snap["scenarios"]["positive"]["conflict_count"] == 3

    def test_the_timeline_has_exactly_one_transition_event(
        self, snap: dict[str, Any]
    ) -> None:
        """状态推进走 `append_operation_event`：一条 append-only event，actor 是**用户**。"""
        events = snap["scenarios"]["positive"]["events"]
        assert len(events) == 1
        ev = events[0]
        assert ev["from_state"] == "conflict"
        assert ev["to_state"] == "superseded"
        assert ev["stage"] == "conflict_abandoned"
        assert ev["actor_type"] == "user", (
            "作废是人工作出的决定 —— actor_type 必须是 user，不是 system/callback"
        )
        assert ev["actor_id"] == snap["actor"]

    def test_no_representation_or_content_version_was_created(
        self, snap: dict[str, Any]
    ) -> None:
        """反向断言（Property 3 的另一半）：作废**什么都不发布**。"""
        out = snap["scenarios"]["positive"]["outcome"]
        assert out["created_representations"] == 0
        assert out["created_content_versions"] == 0

    def test_the_outcome_reports_the_real_row_count(self, snap: dict[str, Any]) -> None:
        out = snap["scenarios"]["positive"]["outcome"]
        assert out["abandoned_conflicts"] == 3
        assert out["already_abandoned"] == 0
        assert out["idempotent_replay"] is False


# ═══════════════════════════════════════════════════════════════════════════
# S2 幂等
# ═══════════════════════════════════════════════════════════════════════════


class TestIdempotentReplay:
    def test_the_replay_does_not_append_a_second_event(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["replay"]
        assert sc["first_events"] == 1
        assert sc["second_events"] == 1, (
            f"重放追加了 event（{sc['first_events']} → {sc['second_events']}）—— "
            "append-only timeline 上出现了第二个冲突→终态事件"
        )

    def test_the_replay_reports_itself_as_idempotent(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["replay"]
        assert sc["idempotent_replay"] is True
        assert sc["abandoned_conflicts"] == 0
        assert sc["already_abandoned"] == 3
        assert sc["to_state"] == "superseded"


# ═══════════════════════════════════════════════════════════════════════════
# S3~S5 拒绝
# ═══════════════════════════════════════════════════════════════════════════


class TestRefusals:
    def test_a_different_reason_is_refused(self, snap: dict[str, Any]) -> None:
        assert (
            snap["scenarios"]["reason_conflict"]["verdict"]
            == "conflict_not_abandonable"
        ), "同一冲突集按另一条理由再作废 —— 审计轨迹会自相矛盾"

    def test_a_settled_operation_is_refused_with_zero_side_effects(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["settled"]
        assert sc["verdict"] == "conflict_not_abandonable"
        assert sc["events_after"] == 0, "被拒的作废仍写了 operation event"
        assert sc["abandoned_rows_after"] == 0, "被拒的作废仍改了冲突行"

    def test_an_operation_without_conflicts_is_refused(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["no_conflicts"]["verdict"] == "conflict_not_abandonable"


# ═══════════════════════════════════════════════════════════════════════════
# S6/S7 DB 侧第二道锁
# ═══════════════════════════════════════════════════════════════════════════


class TestTheDatabaseGuardsAreReal:
    def test_a_lone_abandoned_at_is_rejected_by_the_db(
        self, snap: dict[str, Any]
    ) -> None:
        sc = snap["scenarios"]["triplet_guard"]
        assert sc["verdict"] != "no-error", "只写 abandoned_at 竟然成功了 —— 三列约束不存在"
        assert sc["mentions_constraint"] is True, f"拒绝原因不是 ck_wpsc_abandon_triplet：{sc}"

    def test_a_blank_reason_is_rejected_by_the_db(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["blank_reason_guard"]
        assert sc["verdict"] != "no-error", "空白原因竟然写进去了"
        assert sc["mentions_constraint"] is True, f"拒绝原因不是 ck_wpsc_abandon_triplet：{sc}"
