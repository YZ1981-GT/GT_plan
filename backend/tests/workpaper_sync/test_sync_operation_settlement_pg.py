"""结算后复核探针的**真库**守卫：三列约束真生效 + READ ONLY 真挡写 + 三跳 JOIN 真读回。

spec `frozen-contract-read-path-and-legacy-operation-settlement` 任务 9
Requirements: R3.4
Property: **Property 3**（「状态变了但内容没落地」不可能出现）

═══ 为什么必须真库（离线测不出的四件事）═══

| 判据 | 为什么离线测不出 |
| --- | --- |
| 三列 / 两列约束真的拒残缺写入 | `ck_wpsc_abandon_triplet` / `ck_wpsc_resolution_pair` 是 DB 约束 |
| `SET TRANSACTION READ ONLY` 真的挡住写 | 只有 PG 会拒 |
| 探针的**三跳 JOIN** 真的把版本链读回来了 | `result_representation_id → representation → content_version` 是两次 JOIN；桩会「都读对了」 |
| `base_content_version_revision` 真的是 revision 前进的基线 | 必须有两代真实 content version 才看得出 |

═══ 隔离 ═══

scratch schema `tmp_sosr_<hex>` + `SET search_path` 只含它；**真跑 V151 / V264 / V273**
（不手抄 DDL —— 抄一份就等于「迁移写错也照样绿」）。结束 `DROP SCHEMA CASCADE`。
🔴 **不写共享库**：全部数据在临时 schema 内。真实库的只读复核由
`check_sync_operation_settlement.py --all` 承担（它跑在 `SET TRANSACTION READ ONLY` 里）。
`DATABASE_URL` 非 PostgreSQL 时**直接失败而不是 skip** —— 与 Task 10/15/21~27 及任务 8
的 PG 守卫同约定。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[2]
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_sosr_"
_MIGRATION_V151 = (
    _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
)
_MIGRATION_V264 = _BACKEND / "migrations" / "V264__sync_conflict_schema_anomaly.sql"
_MIGRATION_V273 = _BACKEND / "migrations" / "V273__sync_conflict_abandon_columns.sql"

#: 本判据只需要的三个 stub 父表（V151 里它们由平台侧建，不在那份迁移内）。
_STUB_DDL = """
CREATE TABLE projects (id UUID PRIMARY KEY, name VARCHAR(200) NOT NULL DEFAULT 'stub');
CREATE TABLE users (id UUID PRIMARY KEY, username VARCHAR(100) NOT NULL DEFAULT 'stub');
CREATE TABLE working_paper (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id),
    file_version INTEGER NOT NULL DEFAULT 1,
    content_revision BIGINT NOT NULL DEFAULT 0,
    parsed_data JSONB,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

PROJECT = uuid.UUID("11111111-1111-1111-1111-111111111111")
WP = uuid.UUID("22222222-2222-2222-2222-222222222222")
ENTRY = "xlsx/gt-d4-operating-revenue"


def _is_pg() -> bool:
    url = os.environ.get("DATABASE_URL") or ""
    return url.startswith("postgresql")


pytestmark = [
    pytest.mark.pg_only,
    pytest.mark.skipif(
        not _is_pg(),
        reason=(
            "需要真实 PostgreSQL（DB 三列约束 / SET TRANSACTION READ ONLY / "
            "三跳 JOIN 都在 DB 上）；未设 DATABASE_URL 或指向 sqlite 时 skip —— 不是「已通过」"
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

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise RuntimeError(
            "结算复核探针判据（DB 约束 / READ ONLY / 三跳 JOIN）必须真实 PostgreSQL；"
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
        "apply_errors": [],
        "server_version": None,
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
                MigrationRunner._split_sql_statements(migration.read_text(encoding="utf-8")),
                1,
            ):
                try:
                    async with engine.begin() as conn:
                        await conn.exec_driver_sql(stmt)
                except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
                    snap["apply_errors"].append(
                        {
                            "migration": migration.name,
                            "index": idx,
                            "error": f"{type(exc).__name__}: {exc}",
                            "head": stmt[:120],
                        }
                    )
        if snap["apply_errors"]:
            raise RuntimeError(f"迁移应用失败: {snap['apply_errors'][:3]}")

        actor = uuid.uuid4()
        now = datetime.now(timezone.utc)

        async def _artifact(kind: str, *, sha: str, state: str = "published") -> uuid.UUID:
            art = uuid.uuid4()
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_artifact (id, project_id, wp_id, kind, "
                        "state, sha256, relative_path, size_bytes, document_type, "
                        "published_at) VALUES "
                        "(:i, :p, :w, :k, :st, :sh, :rp, 1, 'xlsx', :pa)"
                    ),
                    {
                        "i": art,
                        "p": PROJECT,
                        "w": WP,
                        "k": kind,
                        "st": state,
                        "sh": sha,
                        "rp": f"storage/stub/{art}.bin",
                        "pa": now,
                    },
                )
                await s.commit()
            return art

        async def _definition(kind: str, *, sha: str) -> uuid.UUID:
            """approved definition_artifact（authority_model 类必须带类型）。"""
            def_id = uuid.uuid4()
            blob = await _artifact("canonical", sha=hashlib.sha256(f"{sha}blob".encode()).hexdigest())
            am_type = "projection_contract" if kind == "authority_model" else None
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_sync_definition_artifact "
                        "(id, kind, logical_id, state, sha256, blob_artifact_id, "
                        "semantic_version, source_commit, approved_at, "
                        "authority_model_type) VALUES "
                        "(:i, :k, :lg, 'approved', :sh, :blob, '1.0.0', :sc, :ap, :amt)"
                    ),
                    {
                        "i": def_id,
                        "k": kind,
                        "lg": f"stub/{kind}/{def_id}",
                        "sh": sha,
                        "blob": blob,
                        "sc": "0" * 40,
                        "ap": now,
                        "amt": am_type,
                    },
                )
                await s.commit()
            return def_id

        async def _bundle(tag: str) -> dict[str, Any]:
            """approved bundle（三 slot + authority model）。"""

            def _sha(extra: str) -> str:
                return hashlib.sha256(f"{tag}{extra}".encode()).hexdigest()

            am_sha, tpl_sha, ins_sha, ct_sha = (
                _sha("am"),
                _sha("tpl"),
                _sha("ins"),
                _sha("ct"),
            )
            authority = await _definition("authority_model", sha=am_sha)
            template = await _definition("template", sha=tpl_sha)
            instr = await _definition("instrumentation", sha=ins_sha)
            contract = await _definition("contract", sha=ct_sha)
            payload = await _artifact("canonical", sha=_sha("cp"))
            bundle = uuid.uuid4()
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_sync_definition_bundle (id, "
                        "authority_model_definition_id, authority_model_definition_sha256, "
                        "template_slot_type, template_slot_ref, template_slot_digest, "
                        "instrumentation_slot_type, instrumentation_slot_ref, "
                        "instrumentation_slot_digest, contract_slot_type, contract_slot_ref, "
                        "contract_slot_digest, canonical_payload_artifact_id, "
                        "canonical_payload_sha256, state, approved_at) VALUES (:i, :am, :amd, "
                        "'definition', :tsr, :tsd, 'definition', :isr, :isd, "
                        "'definition', :csr, :csd, :cp, :cps, 'approved', :ap)"
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
                        "cp": payload,
                        "cps": _sha("cps"),
                        "ap": now,
                    },
                )
                await s.commit()
            return {"bundle": bundle, "authority": authority, "authority_sha": am_sha, "canonical_sha": _sha("cps")}

        async def _content_version(revision: int, *, tag: str) -> uuid.UUID:
            """immutable content version（必须至少有一侧 artifact）。"""
            proj = await _artifact(
                "projection", sha=hashlib.sha256(f"cv{tag}{revision}".encode()).hexdigest()
            )
            cv = uuid.uuid4()
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_content_version (id, wp_id, revision, "
                        "source, projection_artifact_id, projection_sha256) "
                        "SELECT :i, :w, :r, 'onlyoffice', :pa, a.sha256 "
                        "FROM working_paper_artifact a WHERE a.id = :pa"
                    ),
                    {"i": cv, "w": WP, "r": revision, "pa": proj},
                )
                await s.commit()
            return cv

        async def _representation(
            *, cv_id: uuid.UUID, bundle_info: dict[str, Any], generation: int, tag: str
        ) -> uuid.UUID:
            art = await _artifact(
                "canonical", sha=hashlib.sha256(f"rep{tag}{generation}".encode()).hexdigest()
            )
            rep = uuid.uuid4()
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_content_representation (id, wp_id, "
                        "content_version_id, entry_id, generation, document_type, "
                        "artifact_id, artifact_sha256, definition_bundle_id, "
                        "definition_bundle_sha256, authority_model_definition_id, "
                        "authority_model_definition_sha256, adapter_id, "
                        "adapter_build_digest, structure_hash, identity_inventory_sha256, "
                        "reason) SELECT :i, :w, :cv, :e, :g, 'xlsx', :a, ar.sha256, :b, :bsh, "
                        ":am, :amsh, 'stub-adapter', :abd, :sh, :iis, 'content_commit' "
                        "FROM working_paper_artifact ar WHERE ar.id = :a"
                    ),
                    {
                        "i": rep,
                        "w": WP,
                        "cv": cv_id,
                        "e": ENTRY,
                        "g": generation,
                        "a": art,
                        "b": bundle_info["bundle"],
                        "bsh": bundle_info["canonical_sha"],
                        "am": bundle_info["authority"],
                        "amsh": bundle_info["authority_sha"],
                        "abd": hashlib.sha256(f"abd{tag}{generation}".encode()).hexdigest(),
                        "sh": hashlib.sha256(f"st{tag}{generation}".encode()).hexdigest(),
                        "iis": hashlib.sha256(f"iis{tag}{generation}".encode()).hexdigest(),
                    },
                )
                await s.commit()
            return rep

        async def _operation(*, bundle_info: dict[str, Any], state: str) -> uuid.UUID:
            op_id = uuid.uuid4()
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_sync_operation (id, project_id, wp_id, "
                        "entry_id, direction, state, definition_bundle_id, "
                        "definition_bundle_sha256, authority_model_definition_id, "
                        "authority_model_definition_sha256) VALUES "
                        "(:id, :p, :w, :e, 'oo_to_html', :st, :b, :bd, :a, :ad)"
                    ),
                    {
                        "id": op_id,
                        "p": PROJECT,
                        "w": WP,
                        "e": ENTRY,
                        "st": state,
                        "b": bundle_info["bundle"],
                        "bd": hashlib.sha256(f"bd{op_id}".encode()).hexdigest(),
                        "a": bundle_info["authority"],
                        "ad": bundle_info["authority_sha"],
                    },
                )
                await s.commit()
            return op_id

        async def _event(op_id: uuid.UUID, seq: int, frm: str | None, to: str) -> None:
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_sync_operation_event (operation_id, "
                        "sequence_no, from_state, to_state, stage, actor_type, actor_id) "
                        "VALUES (:o, :s, :f, :t, 'stub', 'system', :a)"
                    ),
                    {"o": op_id, "s": seq, "f": frm, "t": to, "a": actor},
                )
                await s.commit()

        async def _conflict(op_id: uuid.UUID, idx: int, **cols: Any) -> uuid.UUID:
            cid = uuid.uuid4()
            payload: dict[str, Any] = {
                "id": cid,
                "op": op_id,
                "k": f"f{idx}",
                "lbl": f"字段{idx}",
                "jp": f"/x/{idx}",
                "at": None,
                "rs": None,
                "by": None,
                "rat": None,
                "rby": None,
                "rval": None,
                "sup": None,
            }
            payload.update(cols)
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_sync_conflict (id, operation_id, "
                        "client_edit_epoch, stable_field_key, business_label, json_pointer, "
                        "field_source, protection_policy, suggested_action, conflict_kind, "
                        "abandoned_at, abandon_reason, abandoned_by, resolved_at, "
                        "resolved_by, resolved_value, superseded_at) VALUES "
                        "(:id, :op, 1, :k, :lbl, :jp, 'current', 'none', 'manual_merge', "
                        "'schema', :at, :rs, :by, :rat, :rby, "
                        "CAST(:rval AS jsonb), :sup)"
                    ),
                    payload,
                )
                await s.commit()
            return cid

        async with engine.begin() as conn:
            await conn.execute(sa.text("INSERT INTO projects (id) VALUES (:i)"), {"i": PROJECT})
            await conn.execute(sa.text("INSERT INTO users (id) VALUES (:i)"), {"i": actor})
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:w, :p)"),
                {"w": WP, "p": PROJECT},
            )

        # ═══ S1 作废形态：三列齐备 + superseded + timeline 齐 ═════════════════
        try:
            info = await _bundle("abandon")
            op_ab = await _operation(bundle_info=info, state="conflict")
            for idx in range(3):
                await _conflict(
                    op_ab,
                    idx,
                    at=now,
                    rs="契约已换代，这批 schema 冲突不再需要处理",
                    by=actor,
                )
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "UPDATE working_paper_sync_operation SET state='superseded', "
                        "finished_at=:f WHERE id=:i"
                    ),
                    {"f": now, "i": op_ab},
                )
                await s.commit()
            await _event(op_ab, 1, None, "created")
            await _event(op_ab, 2, "created", "conflict")
            await _event(op_ab, 3, "conflict", "superseded")
            snap["scenarios"]["abandoned_op"] = str(op_ab)
        except Exception as exc:  # noqa: BLE001
            _fail("abandoned", exc)

        # ═══ S2 DB 三列约束真的拒残缺写入 ═══════════════════════════════════════
        try:
            info2 = await _bundle("triplet")
            op_triplet = await _operation(bundle_info=info2, state="conflict")
            try:
                await _conflict(op_triplet, 0, at=now)
                snap["scenarios"]["triplet_guard"] = {"verdict": "no-error"}
            except Exception as exc:  # noqa: BLE001
                snap["scenarios"]["triplet_guard"] = {
                    "verdict": type(exc).__name__,
                    "mentions_constraint": "ck_wpsc_abandon_triplet" in str(exc),
                }
            # 空白原因也必须被拒
            try:
                await _conflict(op_triplet, 1, at=now, rs="   ", by=actor)
                snap["scenarios"]["blank_reason_guard"] = {"verdict": "no-error"}
            except Exception as exc:  # noqa: BLE001
                snap["scenarios"]["blank_reason_guard"] = {
                    "verdict": type(exc).__name__,
                    "mentions_constraint": "ck_wpsc_abandon_triplet" in str(exc),
                }
            # 只写 reason（无 at/by）也必须被拒
            try:
                await _conflict(op_triplet, 2, rs="只有原因")
                snap["scenarios"]["lone_reason_guard"] = {"verdict": "no-error"}
            except Exception as exc:  # noqa: BLE001
                snap["scenarios"]["lone_reason_guard"] = {
                    "verdict": type(exc).__name__,
                    "mentions_constraint": "ck_wpsc_abandon_triplet" in str(exc),
                }
        except Exception as exc:  # noqa: BLE001
            _fail("triplet", exc)

        # ═══ S3 DB 两列约束（裁决轨迹）真的拒残缺写入 ═══════════════════════════
        try:
            info3 = await _bundle("resolvepair")
            op_rp = await _operation(bundle_info=info3, state="conflict")
            try:
                await _conflict(op_rp, 0, rat=now)
                snap["scenarios"]["resolution_pair_guard"] = {"verdict": "no-error"}
            except Exception as exc:  # noqa: BLE001
                snap["scenarios"]["resolution_pair_guard"] = {
                    "verdict": type(exc).__name__,
                    "mentions_constraint": "ck_wpsc_resolution_pair" in str(exc),
                }
            # 正例：成对写入必须成功（否则上面的红是「什么都写不进去」的假红）
            await _conflict(
                op_rp, 1, rat=now, rby=actor, rval=json.dumps({"present": True, "value": 1})
            )
            snap["scenarios"]["resolution_pair_positive"] = {"verdict": "ok"}
        except Exception as exc:  # noqa: BLE001
            _fail("resolution_pair", exc)

        # ═══ S4 探针的三跳 JOIN 真的把版本链读回来了 ═══════════════════════════
        try:
            info4 = await _bundle("chain")
            base_cv = await _content_version(4, tag="chain")
            base_rep = await _representation(
                cv_id=base_cv, bundle_info=info4, generation=1, tag="chain"
            )
            result_cv = await _content_version(5, tag="chain")
            result_rep = await _representation(
                cv_id=result_cv, bundle_info=info4, generation=2, tag="chain"
            )
            async with Session() as s:
                await s.execute(
                    sa.text(
                        "INSERT INTO working_paper_sync_entry_state (wp_id, entry_id, "
                        "current_representation_id, representation_generation) "
                        "VALUES (:w, :e, :r, 2)"
                    ),
                    {"w": WP, "e": ENTRY, "r": result_rep},
                )
                await s.commit()

            from scripts.check import check_sync_operation_settlement as CLI

            async with engine.connect() as conn:
                await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
                try:
                    chain = await CLI._load_version_chain(
                        conn,
                        op={
                            "application_id": None,
                            "wp_id": WP,
                            "entry_id": ENTRY,
                            "definition_bundle_id": info4["bundle"],
                            "room_id": None,
                        },
                        is_sqlite=False,
                    )
                    # 🔴 第三跳：直接调探针自己的函数（不是另发一条 SQL）——
                    #    短路这一跳的变异必须让读数变 None，从而打红下面三条断言。
                    probe_rep = await CLI._load_representation_facts(
                        conn, rep_id=result_rep, is_sqlite=False
                    )
                    # 第二跳：entry_state
                    entry_row = (
                        await conn.execute(
                            sa.text(
                                CLI._ENTRY_STATE_SQL.format(
                                    wp_id_expr=CLI._uuid_expr("s.wp_id", "wp_id", is_sqlite=False)
                                )
                            ),
                            {"wp_id": WP, "entry_id": ENTRY},
                        )
                    ).mappings().one()
                finally:
                    await conn.rollback()
            snap["scenarios"]["chain"] = {
                "base_rep": str(base_rep),
                "result_rep": str(result_rep),
                "base_cv_revision": 4,
                "result_cv_revision": 5,
                "entry_state_present": chain.entry_state_present,
                "entry_current": chain.entry_current_representation_id,
                "entry_generation": chain.entry_representation_generation,
                "entry_row_generation": int(entry_row["representation_generation"]),
                # 🔴 探针**自己**的读数（变异 m3 的靶点：第三跳被短路时这两个变 None）
                "probe_result_representation_generation": (
                    None if probe_rep is None else int(probe_rep["generation"])
                ),
                "probe_result_content_version_revision": (
                    None if probe_rep is None or probe_rep["revision"] is None
                    else int(probe_rep["revision"])
                ),
            }
        except Exception as exc:  # noqa: BLE001
            _fail("chain", exc)

        # ═══ S5 探针端到端跑通（在只读事务里）═════════════════════════════════
        try:
            from scripts.check import check_sync_operation_settlement as CLI

            async with engine.connect() as conn:
                await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
                try:
                    reports = await CLI.collect_report(
                        conn,
                        operation_id=uuid.UUID(snap["scenarios"]["abandoned_op"]),
                        include_orphans=False,
                    )
                finally:
                    await conn.rollback()
            assert len(reports) == 1, f"期望 1 条报告，实得 {len(reports)}"
            r = reports[0]
            snap["scenarios"]["probe"] = {
                "state": r.state,
                "is_terminal": r.is_terminal,
                "ok": r.ok,
                "conflicts": r.conflicts.as_dict(),
                "timeline_len": len(r.timeline),
                "verdicts": {v.rule_id: v.ok for v in r.verdicts},
                "known_gaps": list(r.known_gaps),
            }
        except Exception as exc:  # noqa: BLE001
            _fail("probe", exc)

        # ═══ S6 READ ONLY 真的挡住写 ═══════════════════════════════════════════
        try:
            async with engine.connect() as conn:
                await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
                try:
                    await conn.execute(
                        sa.text("UPDATE working_paper SET content_revision = 999 WHERE id = :w"),
                        {"w": WP},
                    )
                    snap["scenarios"]["read_only_guard"] = {"verdict": "no-error"}
                except Exception as exc:  # noqa: BLE001
                    snap["scenarios"]["read_only_guard"] = {
                        "verdict": type(exc).__name__,
                        "mentions_read_only": "read-only" in str(exc).lower()
                        or "readonly" in str(exc).lower(),
                    }
                finally:
                    await conn.rollback()
        except Exception as exc:  # noqa: BLE001
            _fail("read_only_guard", exc)

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


def test_the_three_columns_really_exist(snap: dict[str, Any]) -> None:
    """V273 真的加了列 —— 后面每条判据的前提（由 `collect_report` 成功读出证明）。"""
    assert snap["scenarios"]["probe"]["conflicts"]["total"] == 3


# ═══════════════════════════════════════════════════════════════════════════
# S1/S5 作废形态 → 探针必须判绿
# ═══════════════════════════════════════════════════════════════════════════


class TestTheAbandonedOperationPassesTheProbe:
    def test_the_operation_is_terminal_superseded(self, snap: dict[str, Any]) -> None:
        probe = snap["scenarios"]["probe"]
        assert probe["state"] == "superseded"
        assert probe["is_terminal"] is True

    def test_every_conflict_row_is_abandoned_with_all_three_columns(
        self, snap: dict[str, Any]
    ) -> None:
        """**Property 3 的作废方向**：三列齐备，且没有未处理行。"""
        conflicts = snap["scenarios"]["probe"]["conflicts"]
        assert conflicts["total"] == 3
        assert conflicts["abandoned"] == 3
        assert conflicts["triplet_complete"] == 3
        assert conflicts["unsettled"] == 0
        assert conflicts["is_fully_settled"] is True

    def test_the_timeline_has_three_contiguous_events(self, snap: dict[str, Any]) -> None:
        """④ 段：append-only timeline 逐条可查，且 `sequence_no` 连续。"""
        probe = snap["scenarios"]["probe"]
        assert probe["timeline_len"] == 3
        assert probe["verdicts"]["V2_event_sequence_is_contiguous_from_one"] is True

    def test_v7_is_green_and_v6_is_not_applicable(self, snap: dict[str, Any]) -> None:
        """作废方向：V7 绿（不发布内容）；V6 对作废终态不适用（也绿）。"""
        verdicts = snap["scenarios"]["probe"]["verdicts"]
        assert verdicts["V7_superseded_created_no_representation"] is True
        assert verdicts["V6_applied_has_new_representation_and_newer_revision"] is True

    def test_the_whole_probe_passes(self, snap: dict[str, Any]) -> None:
        assert snap["scenarios"]["probe"]["ok"] is True, snap["scenarios"]["probe"]["verdicts"]
        assert snap["scenarios"]["probe"]["known_gaps"] == []


class TestTheDatabaseGuardsAreReal:
    def test_a_lone_abandoned_at_is_rejected(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["triplet_guard"]
        assert sc["verdict"] != "no-error", "只写 abandoned_at 竟然成功了 —— 三列约束不存在"
        assert sc["mentions_constraint"] is True, sc

    def test_a_blank_reason_is_rejected(self, snap: dict[str, Any]) -> None:
        sc = snap["scenarios"]["blank_reason_guard"]
        assert sc["verdict"] != "no-error", "空白原因竟然写进去了"
        assert sc["mentions_constraint"] is True, sc

    def test_a_lone_reason_is_rejected(self, snap: dict[str, Any]) -> None:
        """只写 reason（无 at/by）—— 同生共死约束的另一侧。"""
        sc = snap["scenarios"]["lone_reason_guard"]
        assert sc["verdict"] != "no-error", "只写 reason 竟然成功了"
        assert sc["mentions_constraint"] is True, sc

    def test_a_lone_resolved_at_is_rejected(self, snap: dict[str, Any]) -> None:
        """`ck_wpsc_resolution_pair`（V151 的既有约束）真的在。"""
        sc = snap["scenarios"]["resolution_pair_guard"]
        assert sc["verdict"] != "no-error", "只写 resolved_at 竟然成功了"
        assert sc["mentions_constraint"] is True, sc

    def test_a_complete_resolution_pair_is_accepted(self, snap: dict[str, Any]) -> None:
        """正例：成对写入必须成功 —— 否则上面的红是「什么都写不进去」的假红。"""
        assert snap["scenarios"]["resolution_pair_positive"]["verdict"] == "ok"


# ═══════════════════════════════════════════════════════════════════════════
# S4 三跳 JOIN 真的读回版本链（变异 m3 的靶点）
# ═══════════════════════════════════════════════════════════════════════════


class TestTheVersionChainIsReadThroughRealJoins:
    """探针 ③ 段必须**现读** representation → content_version，不能只看外键非空。

    🔴 变异 m3（探针的读法漏掉版本链指针，只查 operation 表）会打红这一整组：
    那时 `result_representation_generation` / `result_content_version_revision`
    恒 `None`，而下面四条断言都要求它们是真值。
    """

    def test_the_representation_row_is_readable(self, snap: dict[str, Any]) -> None:
        """🔴 探针**自己**读出的 generation / revision 必须是真值（变异 m3 的靶点）。

        断言落在 `_load_version_chain` 的返回值上，而不是测试里另发一条 SQL ——
        后者与探针的读法无关，把第三跳短路掉也照样绿（首轮实测 m3 MISS 即此因）。
        """
        chain = snap["scenarios"]["chain"]
        assert chain["probe_result_representation_generation"] == 2, (
            "探针的 `_load_version_chain` 没读到 representation.generation"
        )
        assert chain["probe_result_content_version_revision"] == 5, (
            "探针的 `_load_version_chain` 没读到 content_version.revision"
        )

    def test_a_separate_query_agrees_with_the_probe(self, snap: dict[str, Any]) -> None:
        """独立查询与探针读数逐值一致（双向对账，memory 铁律 ㉑）。

        探针的第三跳与「另发一条同口径 SQL」必须给出同一答案 —— 这是
        「扫描口径与权威字段双向对账」在本判据上的形式。
        """
        chain = snap["scenarios"]["chain"]
        assert chain["probe_result_representation_generation"] is not None
        assert chain["probe_result_content_version_revision"] is not None
        assert chain["probe_result_content_version_revision"] == chain["result_cv_revision"]
        assert chain["probe_result_representation_generation"] == 2

    def test_the_revision_advances_from_base_to_result(self, snap: dict[str, Any]) -> None:
        """`base` content version 的 revision < `result` 的 revision（V6 的核心判据）。

        🔴 两边的 revision 都取**现读值**：`base_cv_revision` 来自库里
        `working_paper_content_version` 的真实行，`result` 一侧取探针的读数
        （`probe_result_content_version_revision`）。把任一侧换成我写死的常量，
        这条断言就变成「断言我自己填的字面量」—— 变异 m3 短路第三跳时它照样绿。
        """
        chain = snap["scenarios"]["chain"]
        assert chain["base_cv_revision"] == 4, "base content version 的 revision 现读不是 4"
        assert chain["probe_result_content_version_revision"] == 5, (
            "探针没读到 result content version 的 revision"
        )
        assert (
            chain["probe_result_content_version_revision"] > chain["base_cv_revision"]
        ), "revision 没有从 base 前进到 result"

    def test_the_entry_state_pointer_is_readable(self, snap: dict[str, Any]) -> None:
        """第二跳：`working_paper_sync_entry_state` 的 current pointer。"""
        chain = snap["scenarios"]["chain"]
        assert chain["entry_state_present"] is True
        assert chain["entry_current"] == chain["result_rep"]
        assert chain["entry_generation"] == 2
        assert chain["entry_row_generation"] == 2

    def test_the_two_representations_are_distinct(self, snap: dict[str, Any]) -> None:
        """「新 representation」的前提：result ≠ base（否则 V6 会判「没有新代际」）。"""
        chain = snap["scenarios"]["chain"]
        assert chain["result_rep"] != chain["base_rep"]


# ═══════════════════════════════════════════════════════════════════════════
# S6 只读由库强制
# ═══════════════════════════════════════════════════════════════════════════


class TestTheReadOnlyTransactionIsEnforcedByTheDatabase:
    def test_a_write_inside_the_read_only_transaction_is_rejected(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 变异 m4（探针带写操作）必须让这条形态红：写语句在 READ ONLY 里被库拒。

        这条同时证明「探针标称只读」不是一句承诺 —— 库会拦。
        """
        sc = snap["scenarios"]["read_only_guard"]
        assert sc["verdict"] != "no-error", (
            "READ ONLY 事务里 UPDATE 竟然成功了 —— 只读没被库强制"
        )
        assert sc["mentions_read_only"] is True, f"拒绝原因不是只读事务：{sc}"
