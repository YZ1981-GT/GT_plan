"""V165 真实 PostgreSQL 守卫：`authorization_reject` 的 passed 行真的写得进、违规真的被拦。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure
Requirements: 5.6, 12.10, 12.11
Properties: P49 / P69

═══ 为什么必须真库 ═══

`test_evidence_schema_representability.py` 证的是**声明侧**（kind 推导 + 迁移 SQL 文本）。
但迁移 SQL 可能根本不被 PostgreSQL 接受，或 CHECK 写反了方向而「看起来」对 —— Task 29
复盘实测过「离线全绿、真库 CheckViolationError」。所以这里必须在 scratch schema 上真的
apply V151 → V165，再用真 INSERT 双向验证：

* 该场景的 `passed` 行（三实体全零）**现在写得进** —— 这正是 V165 要解除的欠账；
* 带 operation / application / recovery case 的行**仍被库层拒**（只豁免不加零约束，就等于
  允许伪造实体记 passed）；
* `standard` 的 `passed` 行仍必须有 operation+application —— 通用规则没被顺手放松。

外加：R165 必须**拒绝**在仍有该 kind 行时回滚（evidence 是审计轨迹，静默删除比回滚失败
危险），清行后才允许回滚并还原 V151 原文。

═══ 隔离与采集 ═══

scratch schema `tmp_v165_<hex>`，结束 `DROP SCHEMA CASCADE`。全部动作由**一次
`asyncio.run`** 落进快照（module fixture）—— 每个测试各自开 async 会污染共享连接池
（Task 21~29 实测：第二个起 `NoneType has no attribute send`）。采集异常**记录不穿透**：
穿透会让整个 module 变成 collection ERROR，而 `-rf` 只列 FAILED 不列 ERROR ⇒ 定向变异看
不到预期失败 ⇒ 误判 GREEN。`test_no_phase_crashed_during_collection` 是这个决定的另一半。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_V151 = _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
_V165 = _BACKEND / "migrations" / "V165__wpees_authorization_reject_kind.sql"
_R165 = _BACKEND / "migrations" / "R165__rollback_wpees_authorization_reject_kind.sql"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_v165_"
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

_TARGET = "quarantined_rejects_application_and_engine"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _err(exc: BaseException) -> str:
    import traceback

    frames = traceback.extract_tb(exc.__traceback__)[-6:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


class _SetupError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成"无数据"）。"""


async def _collect() -> dict[str, Any]:  # noqa: C901, PLR0915 - 一次采集覆盖全部分支
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    import sqlalchemy as sa

    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise _SetupError(
            "V165 的判据是「真库是否接受这些 CHECK、是否真的拦住违规行」，必须真实 "
            f"PostgreSQL；当前 DATABASE_URL 为 {settings.DATABASE_URL.split('://')[0]}。"
            "此处**不 skip**。"
        )
    for path in (_V151, _V165, _R165):
        if not path.exists():
            raise _SetupError(f"缺少迁移文件: {path}")

    schema = f"{_SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    snap: dict[str, Any] = {
        "schema": schema,
        "apply_errors": [],
        "phase_errors": {},
        "inserts": {},
        "constraints": {},
        "rollback": {},
    }

    admin = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    engine = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,
            connect_args={**ssl_off, "server_settings": {"search_path": schema}},
        )

        async with engine.begin() as conn:
            for stmt in [s.strip() for s in _STUB_DDL.strip().split(";") if s.strip()]:
                await conn.exec_driver_sql(stmt)

        # ── apply V151 → V165（顺序即生产顺序）──────────────────────────
        for label, path in (("V151", _V151), ("V165", _V165)):
            stmts = MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8"))
            for idx, stmt in enumerate(stmts, 1):
                try:
                    async with engine.begin() as conn:
                        await conn.exec_driver_sql(stmt)
                except Exception as exc:  # noqa: BLE001 - 记录后由守卫断言为空
                    snap["apply_errors"].append(
                        {"migration": label, "index": idx, "error": _err(exc)}
                    )

        # ── 约束现状（证明 V165 真的落到真库，而不是"文件里写了"）────────
        async with engine.begin() as conn:
            rows = (
                await conn.execute(
                    sa.text(
                        "SELECT conname, pg_get_constraintdef(oid) AS def "
                        "FROM pg_constraint "
                        "WHERE conrelid = (:rel)::regclass AND conname = ANY(:names)"
                    ),
                    {
                        "rel": f"{schema}.working_paper_entry_evidence_scenario",
                        "names": [
                            "ck_wpees_scenario_kind",
                            "ck_wpees_standard_requires_entities",
                            "ck_wpees_authorization_reject_zero_entities",
                            "ck_wpees_download_only_zero_entities",
                        ],
                    },
                )
            ).all()
        snap["constraints"] = {str(name): str(defn) for name, defn in rows}

        # ── 父行：project / wp / artifact ×2 / test_run ────────────────
        project, wp = uuid.uuid4(), uuid.uuid4()
        manifest_art, trace_art = uuid.uuid4(), uuid.uuid4()
        run = uuid.uuid4()
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("INSERT INTO projects (id, name) VALUES (:p, 'v165')"), {"p": project}
            )
            await conn.execute(
                sa.text("INSERT INTO working_paper (id, project_id) VALUES (:w, :p)"),
                {"w": wp, "p": project},
            )
            for art, kind, retention in (
                (manifest_art, "evidence", "evidence_manifest"),
                (trace_art, "trace_bundle", "trace_bundle"),
            ):
                await conn.execute(
                    sa.text(
                        "INSERT INTO working_paper_artifact "
                        "(id, project_id, wp_id, kind, state, relative_path, sha256, "
                        " size_bytes, document_type, retention_class, published_at) "
                        "VALUES (:id, :p, :w, :k, 'published', :path, :sha, 11, 'json', "
                        " :ret, now())"
                    ),
                    {
                        "id": art,
                        "p": project,
                        "w": wp,
                        "k": kind,
                        "path": f"v165/{kind}.json",
                        "sha": _d(str(art)),
                        "ret": retention,
                    },
                )
            await conn.execute(
                sa.text(
                    "INSERT INTO working_paper_sync_test_run "
                    "(id, entry_id, source_commit, runner_version, manifest_source_digest, "
                    " editability, room_model, scenario_profile_digest, onlyoffice_build, "
                    " browser_build, environment_digest, required_scenario_set_digest, "
                    " authority_model_definition_sha256, definition_bundle_sha256, "
                    " run_manifest_artifact_id, run_manifest_sha256, started_at, "
                    " aggregate_result) "
                    "VALUES (:id, 'xlsx/gt-d2-accounts-receivable', 'v165', 'v165', :d1, "
                    " 'editable', 'shared', :d2, 'oo', 'br', :d3, :d4, :d5, :d6, :art, :d7, "
                    " :now, 'unverified')"
                ),
                {
                    "id": run,
                    "d1": _d("manifest"),
                    "d2": _d("profile"),
                    "d3": _d("env"),
                    "d4": _d("required"),
                    "d5": _d("authority"),
                    "d6": _d("bundle"),
                    "art": manifest_art,
                    "d7": _d("runmanifest"),
                    "now": datetime.now(timezone.utc),
                },
            )

        ordinal = {"n": 0}

        async def _try_insert(
            label: str,
            *,
            kind: str,
            result: str,
            operations: int = 0,
            applications: int = 0,
            cases: int = 0,
        ) -> None:
            """真插一行，记录成功/失败（失败记 constraint 名，便于归因到具体 CHECK）。"""
            ordinal["n"] += 1
            payload = {
                "id": uuid.uuid4(),
                "run": run,
                "sid": f"{_TARGET}:{label}",
                "ord": ordinal["n"],
                "kind": kind,
                "result": result,
                "ops": [str(uuid.uuid4()) for _ in range(operations)],
                "apps": [str(uuid.uuid4()) for _ in range(applications)],
                "cases": [str(uuid.uuid4()) for _ in range(cases)],
                # 🔴 authority/bundle 摘要必须与所属 run **相等**：V151 的
                # `trg_wpees_identity`（BEFORE INSERT）会拒绝不一致的行（禁跨 run 复制
                # evidence）。用 per-label 摘要会让每一条都栽在这个触发器上，从而掩盖真正
                # 要测的 CHECK —— 本轮实测踩过。
                "authority": _d("authority"),
                "bundle": _d("bundle"),
                "d": _d(label),
                "art": trace_art,
            }
            sql = sa.text(
                "INSERT INTO working_paper_entry_evidence_scenario "
                "(id, run_id, scenario_id, ordinal, scenario_kind, result, operation_ids, "
                " application_ids, recovery_case_ids, authority_model_definition_sha256, "
                " definition_bundle_sha256, trace_bundle_artifact_id, trace_bundle_sha256, "
                " server_timeline_digest, database_snapshot_digest, browser_build) "
                "VALUES (:id, :run, :sid, :ord, :kind, :result, "
                " to_jsonb(CAST(:ops AS text[])), to_jsonb(CAST(:apps AS text[])), "
                " to_jsonb(CAST(:cases AS text[])), :authority, :bundle, :art, :d, :d, :d, "
                " 'br')"
            )
            try:
                async with engine.begin() as conn:
                    await conn.execute(sql, payload)
                snap["inserts"][label] = {"ok": True, "constraint": None}
            except Exception as exc:  # noqa: BLE001 - 违约是预期结果之一
                name = getattr(getattr(exc, "orig", None), "constraint_name", None)
                if name is None:
                    import re

                    m = re.search(r'constraint "([a-z0-9_]+)"', str(exc))
                    name = m.group(1) if m else None
                snap["inserts"][label] = {
                    "ok": False,
                    "constraint": name,
                    "error": _err(exc)[:300],
                }

        # 🔴 核心：欠账是否真解除
        await _try_insert("passed_zero_entities", kind="authorization_reject", result="passed")
        # 🔴 豁免不得被滥用
        await _try_insert(
            "passed_with_application",
            kind="authorization_reject",
            result="passed",
            operations=1,
            applications=1,
        )
        await _try_insert(
            "passed_with_operation_only",
            kind="authorization_reject",
            result="passed",
            operations=1,
        )
        await _try_insert(
            "passed_with_recovery_case",
            kind="authorization_reject",
            result="passed",
            cases=1,
        )
        # 🔴 通用规则不得被顺手放松
        await _try_insert("standard_passed_zero_entities", kind="standard", result="passed")
        await _try_insert(
            "standard_passed_with_entities",
            kind="standard",
            result="passed",
            operations=1,
            applications=1,
        )

        # ── R165：有该 kind 行时必须拒绝回滚；清行后允许并还原 V151 原文 ──
        r165_sql = _R165.read_text(encoding="utf-8")
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(r165_sql)
            snap["rollback"]["refused_while_rows_exist"] = False
        except Exception as exc:  # noqa: BLE001 - 预期抛错
            snap["rollback"]["refused_while_rows_exist"] = True
            snap["rollback"]["refusal_error"] = str(exc)[:300]

        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "DELETE FROM working_paper_entry_evidence_scenario "
                    "WHERE scenario_kind = 'authorization_reject'"
                )
            )
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(r165_sql)
            snap["rollback"]["succeeded_after_cleanup"] = True
        except Exception as exc:  # noqa: BLE001
            snap["rollback"]["succeeded_after_cleanup"] = False
            snap["rollback"]["cleanup_error"] = _err(exc)[:300]

        async with engine.begin() as conn:
            rows = (
                await conn.execute(
                    sa.text(
                        "SELECT conname, pg_get_constraintdef(oid) AS def "
                        "FROM pg_constraint "
                        "WHERE conrelid = (:rel)::regclass AND conname = ANY(:names)"
                    ),
                    {
                        "rel": f"{schema}.working_paper_entry_evidence_scenario",
                        "names": [
                            "ck_wpees_scenario_kind",
                            "ck_wpees_standard_requires_entities",
                            "ck_wpees_authorization_reject_zero_entities",
                        ],
                    },
                )
            ).all()
        snap["rollback"]["constraints_after"] = {
            str(name): str(defn) for name, defn in rows
        }
    except Exception as exc:  # noqa: BLE001 - 采集失败也要让守卫看见
        snap["phase_errors"]["collect"] = _err(exc)
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception as exc:  # noqa: BLE001
            snap["phase_errors"]["teardown"] = _err(exc)
        await admin.dispose()
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


class TestCollectionIntegrity:
    def test_no_phase_crashed_during_collection(self, snap: dict[str, Any]) -> None:
        assert snap["phase_errors"] == {}, snap["phase_errors"]

    def test_v151_and_v165_apply_cleanly(self, snap: dict[str, Any]) -> None:
        assert snap["apply_errors"] == [], snap["apply_errors"]


class TestConstraintsLandedInRealPostgres:
    def test_kind_domain_includes_authorization_reject(self, snap: dict[str, Any]) -> None:
        defn = snap["constraints"].get("ck_wpees_scenario_kind", "")
        assert "authorization_reject" in defn, defn

    def test_standard_constraint_exempts_the_new_kind(self, snap: dict[str, Any]) -> None:
        defn = snap["constraints"].get("ck_wpees_standard_requires_entities", "")
        assert "authorization_reject" in defn, defn

    def test_zero_entities_constraint_exists(self, snap: dict[str, Any]) -> None:
        assert "ck_wpees_authorization_reject_zero_entities" in snap["constraints"]

    def test_download_only_constraint_untouched(self, snap: dict[str, Any]) -> None:
        """那条要求 `recovery_case_ids >= 1`，新 kind 不得混进去。"""
        defn = snap["constraints"].get("ck_wpees_download_only_zero_entities", "")
        assert defn, "V151 的 download_only 约束不见了"
        assert "authorization_reject" not in defn, defn


class TestDebtIsActuallyCleared:
    def test_passed_row_with_zero_entities_is_now_writable(
        self, snap: dict[str, Any]
    ) -> None:
        """🔴 这一条就是 V165 的全部目的：欠账前它写不进去。"""
        got = snap["inserts"]["passed_zero_entities"]
        assert got["ok"] is True, got


class TestExemptionCannotBeAbused:
    @pytest.mark.parametrize(
        "label",
        ["passed_with_application", "passed_with_operation_only", "passed_with_recovery_case"],
    )
    def test_entities_on_the_new_kind_are_refused(
        self, snap: dict[str, Any], label: str
    ) -> None:
        got = snap["inserts"][label]
        assert got["ok"] is False, f"{label} 竟然写进去了 —— 豁免被滥用：{got}"
        assert got["constraint"] == "ck_wpees_authorization_reject_zero_entities", got


class TestGeneralRuleNotLoosened:
    def test_standard_passed_still_requires_entities(self, snap: dict[str, Any]) -> None:
        got = snap["inserts"]["standard_passed_zero_entities"]
        assert got["ok"] is False, f"standard 的 passed 行竟可零实体：{got}"
        assert got["constraint"] == "ck_wpees_standard_requires_entities", got

    def test_standard_passed_with_entities_still_works(self, snap: dict[str, Any]) -> None:
        got = snap["inserts"]["standard_passed_with_entities"]
        assert got["ok"] is True, got


class TestRollbackIsRealAndSafe:
    def test_rollback_refuses_while_evidence_rows_exist(self, snap: dict[str, Any]) -> None:
        assert snap["rollback"]["refused_while_rows_exist"] is True, snap["rollback"]
        assert "authorization_reject" in snap["rollback"].get("refusal_error", "")

    def test_rollback_succeeds_after_rows_are_adjudicated(
        self, snap: dict[str, Any]
    ) -> None:
        assert snap["rollback"]["succeeded_after_cleanup"] is True, snap["rollback"]

    def test_rollback_restores_v151_constraint_text(self, snap: dict[str, Any]) -> None:
        after = snap["rollback"]["constraints_after"]
        assert "ck_wpees_authorization_reject_zero_entities" not in after, after
        assert "authorization_reject" not in after.get("ck_wpees_scenario_kind", "")
        assert "authorization_reject" not in after.get(
            "ck_wpees_standard_requires_entities", ""
        )
