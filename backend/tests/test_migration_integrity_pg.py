"""真实 PostgreSQL 守卫：迁移完整性与枚举漂移收口（spec migration-integrity-and-enum-drift-closure）。

判据全部是**这个库的现场状态**（触发器绑定、拒绝码、表注释、checksum 漂移、ORM 枚举绑定），
SQLite / mock 无从回答 —— 所以 ``DATABASE_URL`` 不是 PostgreSQL 时直接失败，不 skip。

写操作全部在一个最终 ROLLBACK 的事务里（每个探测再套 SAVEPOINT），结束后复查无残留。
全部采集一次 ``asyncio.run`` 落快照，逐条断言。

反向对照（证明夹具真的在看，而不是空转成绿）：
* ``pending``（ApprovalStatus 旧标签）写 review_status_enum 必须被拒 —— 该列确是共享枚举；
* 按原生枚举 ``gt_wp_type`` 绑定参数必须 42704 —— 修复前的症状在真库上仍可复现；
* checksum 比较确实发生（schema_version 与磁盘有 >100 个版本交集），且实测漂移全部落在登记表内；
* 空表的 evgov 表无法逐表实测 ⇒ 另用临时表绑定两个共享函数实测拒绝码，配合「绑定 × 事件」推出。
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_V171 = _BACKEND / "migrations" / "V171__confirmation_action_log_evgov_trigger_repair.sql"
_GUARD_TAG = f"mig-guard-{uuid.uuid4().hex[:8]}"
_EXPECTED = {"UPDATE": "23514", "DELETE": "23001"}  # check_violation / restrict_violation
_EVGOV_FUNCTION_FOR = {"UPDATE": "evgov_forbid_update", "DELETE": "evgov_forbid_delete"}


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _sqlstate(exc: BaseException) -> str:
    cur: BaseException | None = exc
    for _ in range(6):
        if cur is None:
            break
        code = getattr(cur, "sqlstate", None) or getattr(cur, "pgcode", None)
        if code:
            return str(code)
        cur = getattr(cur, "orig", None) or cur.__cause__
    return "?"


async def _attempt(conn, stmt, params=None) -> tuple[str | None, str]:
    """在 SAVEPOINT 里执行；返回 (SQLSTATE 或 None=成功, 首行报文)。"""
    try:
        async with conn.begin_nested():
            await conn.execute(stmt, params or {})
    except sa.exc.DBAPIError as exc:
        return _sqlstate(exc), str(getattr(exc, "orig", exc)).splitlines()[0]
    return None, ""


def _v171_comments() -> dict[str, str]:
    text = _V171.read_text(encoding="utf-8")
    return {
        m.group(1): m.group(2).replace("''", "'")
        for m in re.finditer(r"COMMENT ON TABLE (\w+) IS '((?:[^']|'')*)';", text)
    }


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.core.migration_drift_ledger import unexplained_checksum_drift
    from app.core.migration_runner import MigrationRunner
    from app.core.schema_drift_detector import (
        SchemaDriftDetector,
        collect_orm_enum_columns,
        fetch_public_enum_catalog,
    )
    from app.models.collaboration_models import ReviewStatus, WorkpaperReviewRecord
    from app.models.gt_coding_models import GTWpCoding, GTWpType

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise _HarnessError(f"本守卫判据是真实 PostgreSQL 的现场状态；当前 DATABASE_URL={settings.DATABASE_URL!r}")

    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=ssl_off)
    snap: dict[str, Any] = {"harness_errors": [], "rejections": {}, "skipped_tables": []}
    try:
        # ── 只读：checksum 漂移 / 枚举漂移（检测器自己的连接）────────────────────
        runner = MigrationRunner(engine=engine)
        drifts = await runner.detect_checksum_drift()
        snap["raw_drift_versions"] = [d.version for d in drifts]
        disk = {m.version for m in runner.scan_migrations()}
        async with engine.connect() as conn:
            stored = {r[0] for r in (await conn.execute(sa.text("SELECT version FROM schema_version"))).fetchall()}
        snap["schema_version_rows"], snap["disk_versions"] = len(stored), len(disk)
        snap["compared_versions"] = len(stored & disk)
        snap["unexplained_drift"] = [(d.version, d.stored_checksum, d.current_checksum)
                                     for d in unexplained_checksum_drift(drifts)]
        detector = SchemaDriftDetector(engine)
        snap["enum_items"] = [(i.table, i.column, i.detail) for i in await detector._diff_enums()]
        # 走检测器自己的接线（scan 调的就是它），不只是复算判据
        snap["checksum_items"] = [(i.table, i.detail) for i in await detector._diff_checksums()]
        from app.models.base import Base
        snap["orm_enum_columns"] = len(collect_orm_enum_columns(Base.metadata))

        async with engine.connect() as conn:
            # 两张模型表是历史基线表（V001 为 no-op 基线，迁移本身不建它们）：只跑过迁移的空库（如 CI 的
            # postgres 服务）里没有。缺表时明确报红并说明原因，不 skip —— 守卫需要已迁移的现场库。
            missing = [
                name for name in ("confirmation_action_log", "gt_wp_coding", "workpaper_review_records",
                                  "projects", "users")
                if not (await conn.execute(sa.text("SELECT to_regclass(:n) IS NOT NULL"),
                                           {"n": f"public.{name}"})).scalar()
            ]
            if missing:
                raise _HarnessError(f"现场库缺表 {missing}：本守卫需要已迁移且含历史基线表的库（不是只跑迁移的空库）")

        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                # ── 触发器绑定 / 函数体 / 表注释 ──────────────────────────────
                rows = (await conn.execute(sa.text("""
                    SELECT c.relname, t.tgname, p.proname,
                           (t.tgtype & 16) <> 0 AS on_update, (t.tgtype & 8) <> 0 AS on_delete
                    FROM pg_trigger t
                    JOIN pg_class c ON c.oid = t.tgrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    JOIN pg_proc p ON p.oid = t.tgfoid
                    WHERE n.nspname = 'public' AND NOT t.tgisinternal
                      AND (p.proname LIKE 'evgov_forbid_%' OR c.relname = 'confirmation_action_log')
                """))).fetchall()
                snap["triggers"] = sorted(
                    (r[0], r[1], r[2], ev)
                    for r in rows for ev, on in (("UPDATE", r[3]), ("DELETE", r[4])) if on
                )
                funcs = (await conn.execute(sa.text("""
                    SELECT p.proname, p.prosrc FROM pg_proc p
                    JOIN pg_namespace n ON n.oid = p.pronamespace
                    WHERE n.nspname = 'public' AND p.proname IN (
                        'evgov_forbid_update', 'evgov_forbid_delete',
                        'trg_conf_action_log_forbid_update', 'trg_conf_action_log_forbid_delete')
                """))).fetchall()
                snap["functions"] = {r[0]: r[1] for r in funcs}
                comments = (await conn.execute(sa.text("""
                    SELECT c.relname, d.description FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    LEFT JOIN pg_description d
                      ON d.objoid = c.oid AND d.classoid = 'pg_class'::regclass AND d.objsubid = 0
                    WHERE n.nspname = 'public' AND c.relkind = 'r'
                      AND c.relname IN ('confirmation_attachment_link', 'confirmation_action_log')
                """))).fetchall()
                snap["comments"] = {r[0]: r[1] for r in comments}

                # ── 拒绝码：confirmation_action_log 自插一行；其余 evgov 表取现有行 ──
                log_id = uuid.uuid4()
                code, msg = await _attempt(conn, sa.text(
                    "INSERT INTO confirmation_action_log (id, confirmation_id, project_id, action, actor_user_id, reason) "
                    "VALUES (:id, :c, :p, 'reverse', :u, :r)"
                ), {"id": log_id, "c": uuid.uuid4(), "p": uuid.uuid4(), "u": uuid.uuid4(), "r": _GUARD_TAG})
                if code is not None:
                    raise _HarnessError(f"插入 confirmation_action_log 失败：{code} {msg}")
                for table, _tg, _fn, event in snap["triggers"]:
                    row_id = log_id if table == "confirmation_action_log" else (
                        await conn.execute(sa.text(f'SELECT id FROM "{table}" LIMIT 1'))
                    ).scalar()
                    if row_id is None:
                        snap["skipped_tables"].append((table, event))
                        continue
                    stmt = (f'UPDATE "{table}" SET id = id WHERE id = :i' if event == "UPDATE"
                            else f'DELETE FROM "{table}" WHERE id = :i')
                    snap["rejections"][(table, event)] = await _attempt(conn, sa.text(stmt), {"i": row_id})

                # 与数据无关的实测：临时表绑定同两个共享函数（空表的 evgov 表靠「绑定 × 函数码」两条推出）
                probe_id = uuid.uuid4()
                await conn.execute(sa.text("CREATE TEMP TABLE _mig_guard_evgov (id uuid PRIMARY KEY) ON COMMIT DROP"))
                for event, fn in _EVGOV_FUNCTION_FOR.items():
                    await conn.execute(sa.text(
                        f"CREATE TRIGGER _mig_guard_{event.lower()} BEFORE {event} ON _mig_guard_evgov "
                        f"FOR EACH ROW EXECUTE FUNCTION public.{fn}()"))
                await conn.execute(sa.text("INSERT INTO _mig_guard_evgov (id) VALUES (:i)"), {"i": probe_id})
                snap["function_codes"] = {
                    "UPDATE": await _attempt(conn, sa.text(
                        "UPDATE _mig_guard_evgov SET id = id WHERE id = :i"), {"i": probe_id}),
                    "DELETE": await _attempt(conn, sa.text(
                        "DELETE FROM _mig_guard_evgov WHERE id = :i"), {"i": probe_id}),
                }

                # ── ORM 枚举绑定：gt_wp_coding.wp_type（非原生枚举 ⇒ 按 varchar 绑定）──
                gt = {}
                gt["insert"] = await _attempt(conn, sa.insert(GTWpCoding).values(
                    code_prefix="Z", code_range=_GUARD_TAG, cycle_name="迁移守卫", wp_type=GTWpType.general,
                ))
                try:
                    async with conn.begin_nested():
                        got = (await conn.execute(
                            sa.select(GTWpCoding.wp_type).where(
                                GTWpCoding.wp_type == GTWpType.general, GTWpCoding.code_range == _GUARD_TAG)
                        )).scalars().all()
                    gt["select"] = [type(v).__name__ + ":" + str(getattr(v, "value", v)) for v in got]
                except sa.exc.DBAPIError as exc:
                    gt["select"] = f"{_sqlstate(exc)} {exc.orig}"
                gt["native_bind_control"] = await _attempt(conn, sa.select(GTWpCoding.id).where(
                    GTWpCoding.__table__.c.wp_type == sa.bindparam(
                        "legacy", "general", type_=sa.Enum(GTWpType, name="gt_wp_type"))))
                snap["gt_wp_coding"] = gt

                # ── ORM 枚举绑定：workpaper_review_records.review_status（共享 review_status_enum）──
                rv = {}
                project_id = (await conn.execute(sa.text("SELECT id FROM projects LIMIT 1"))).scalar()
                user_id = (await conn.execute(sa.text("SELECT id FROM users LIMIT 1"))).scalar()
                if project_id is None or user_id is None:
                    raise _HarnessError("库里没有 projects / users 行，无法验证 workpaper_review_records 写入")
                rec_id = uuid.uuid4()
                rv["insert"] = await _attempt(conn, sa.insert(WorkpaperReviewRecord).values(
                    id=rec_id, project_id=project_id, workpaper_id=uuid.uuid4(), workpaper_type=_GUARD_TAG,
                    reviewer_id=user_id, review_date=sa.func.now(), review_status=ReviewStatus.pending_review,
                    issues_found=0, is_deleted=False,
                ))
                back = (await conn.execute(sa.select(WorkpaperReviewRecord.review_status).where(
                    WorkpaperReviewRecord.id == rec_id))).scalar()
                rv["readback"] = None if back is None else f"{type(back).__name__}:{back.value}"
                rv["legacy_label_control"] = await _attempt(conn, sa.text(
                    "SELECT CAST(:s AS review_status_enum)"), {"s": "pending"})
                snap["review_record"] = rv

                # ── 旧缺陷 ③：别的 schema 里的同名类型不得把标签并进 public（回滚事务内建，零残留）──
                scratch = f"tmp_migguard_{uuid.uuid4().hex[:10]}"
                await conn.execute(sa.text(f'CREATE SCHEMA "{scratch}"'))
                await conn.execute(sa.text(
                    f"CREATE TYPE \"{scratch}\".review_status_enum AS ENUM ('pending', '{_GUARD_TAG}')"))
                db_columns, db_enums = await fetch_public_enum_catalog(conn)
                snap["catalog_review_status_labels"] = sorted(db_enums.get("review_status_enum", ()))
                snap["catalog_review_status_column"] = db_columns.get(("workpaper_review_records", "review_status"))
            finally:
                await trans.rollback()

        async with engine.connect() as conn:
            snap["leftovers"] = {
                "confirmation_action_log": (await conn.execute(sa.text(
                    "SELECT count(*) FROM confirmation_action_log WHERE reason = :t"), {"t": _GUARD_TAG})).scalar(),
                "gt_wp_coding": (await conn.execute(sa.text(
                    "SELECT count(*) FROM gt_wp_coding WHERE code_range = :t"), {"t": _GUARD_TAG})).scalar(),
                "workpaper_review_records": (await conn.execute(sa.text(
                    "SELECT count(*) FROM workpaper_review_records WHERE workpaper_type = :t"),
                    {"t": _GUARD_TAG})).scalar(),
                "tmp_migguard_schemas": (await conn.execute(sa.text(
                    "SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'tmp\\_migguard\\_%'"))).scalar(),
            }
    except Exception as exc:  # noqa: BLE001 - 采集失败必须让守卫红
        snap["harness_errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        await engine.dispose()
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


def test_harness_ran_and_left_nothing_behind(snap) -> None:
    assert snap["harness_errors"] == []
    assert snap["leftovers"] == {"confirmation_action_log": 0, "gt_wp_coding": 0,
                                 "workpaper_review_records": 0, "tmp_migguard_schemas": 0}


# ── Requirement 1：V171 补齐 V128 缺失效果 ──────────────────────────────────


def test_action_log_triggers_bound_to_evgov_functions(snap) -> None:
    own = {(tg, fn, ev) for table, tg, fn, ev in snap["triggers"] if table == "confirmation_action_log"}
    assert own == {
        ("trg_conf_action_log_forbid_update", "evgov_forbid_update", "UPDATE"),
        ("trg_conf_action_log_forbid_delete", "evgov_forbid_delete", "DELETE"),
    }
    assert "trg_conf_action_log_forbid_update" not in snap["functions"], "首版专用函数应已删除"
    assert "trg_conf_action_log_forbid_delete" not in snap["functions"], "首版专用函数应已删除"


def test_every_evgov_binding_matches_its_event(snap) -> None:
    evgov = [(t, fn, ev) for t, _tg, fn, ev in snap["triggers"] if fn.startswith("evgov_forbid_")]
    assert len({t for t, _fn, _ev in evgov}) >= 9, evgov
    assert [x for x in evgov if _EVGOV_FUNCTION_FOR[x[2]] != x[1]] == []


def test_evgov_function_bodies_pinned_to_v108_v111(snap) -> None:
    upd, dele = snap["functions"]["evgov_forbid_update"], snap["functions"]["evgov_forbid_delete"]
    assert "check_violation" in upd and "restrict_violation" not in upd, upd
    assert "restrict_violation" in dele, dele


def test_action_log_rejects_update(snap) -> None:
    """替代 confirmation_evidence/test_properties_pbt.py 里的 xfail 占位（Requirements 8.3）。"""
    code, msg = snap["rejections"][("confirmation_action_log", "UPDATE")]
    assert code == "23514" and "confirmation_action_log" in msg, (code, msg)


def test_action_log_rejects_delete(snap) -> None:
    code, msg = snap["rejections"][("confirmation_action_log", "DELETE")]
    assert code == "23001" and "confirmation_action_log" in msg, (code, msg)


def test_shared_evgov_functions_raise_the_expected_codes(snap) -> None:
    """与数据无关：临时表绑定两个共享函数实测。配合「每条 evgov 绑定与事件匹配」，推出全部 evgov 表的拒绝码。"""
    codes = {ev: code for ev, (code, _msg) in snap["function_codes"].items()}
    assert codes == _EXPECTED


def test_other_evgov_tables_with_rows_keep_their_codes(snap) -> None:
    """有数据的其余 evgov 表逐表实测（空表跳过并记在 skipped_tables —— 由上一条用例兜底）。"""
    others = {k: v for k, v in snap["rejections"].items() if k[0] != "confirmation_action_log"}
    wrong = {k: v for k, v in others.items() if v[0] != _EXPECTED[k[1]] or k[0] not in v[1]}
    assert wrong == {}


def test_table_comments_match_v171(snap) -> None:
    expected = _v171_comments()
    assert set(expected) == {"confirmation_attachment_link", "confirmation_action_log"}
    assert snap["comments"] == expected


# ── Requirement 3：checksum 漂移可见且已逐条解释 ─────────────────────────────


def test_no_unexplained_checksum_drift(snap) -> None:
    assert snap["unexplained_drift"] == []
    assert snap["checksum_items"] == [], "检测器（health 数据源）报出了未解释漂移"


def test_checksum_comparison_actually_ran(snap) -> None:
    """「未解释为 0」不能来自没在比：schema_version 有登记、磁盘扫到迁移、两边有交集。

    不写死漂移版本：按当前文件建的新库本来就没有漂移（登记表此时不解释任何东西），那也是正确状态。
    本机开发库现场为 7 条（V042/046/105/128/143/151/163），全部被登记表逐字解释 —— 记在 tasks.md 证据里。
    """
    assert snap["schema_version_rows"] > 0 and snap["disk_versions"] > 100
    assert snap["compared_versions"] > 100
    from app.core.migration_drift_ledger import KNOWN_CHECKSUM_DRIFTS

    assert set(snap["raw_drift_versions"]) <= {k.version for k in KNOWN_CHECKSUM_DRIFTS}


# ── Requirement 4 / 5：枚举漂移与两个模型修复 ─────────────────────────────────


def test_live_enum_drift_is_empty(snap) -> None:
    assert snap["orm_enum_columns"] > 100, "ORM 原生枚举列数异常偏少：模型没有 import 全"
    assert snap["enum_items"] == []


def test_gt_wp_coding_query_and_insert_work(snap) -> None:
    gt = snap["gt_wp_coding"]
    assert gt["insert"] == (None, "")
    assert gt["select"] == ["GTWpType:general"]


def test_native_gt_wp_type_binding_still_fails_on_this_db(snap) -> None:
    """反向对照：修复前的绑定方式在真库上仍是 42704 —— 上面的「成功」确实来自修复。"""
    code, msg = snap["gt_wp_coding"]["native_bind_control"]
    assert code == "42704" and "gt_wp_type" in msg, (code, msg)


def test_review_record_accepts_pending_review(snap) -> None:
    rv = snap["review_record"]
    assert rv["insert"] == (None, "")
    assert rv["readback"] == "ReviewStatus:pending_review"


def test_legacy_pending_label_is_rejected_by_shared_enum(snap) -> None:
    code, _msg = snap["review_record"]["legacy_label_control"]
    assert code == "22P02"


def test_enum_catalog_ignores_same_named_types_in_other_schemas(snap) -> None:
    """旧缺陷 ③：查 pg_type 不限 schema 时，tmp_* 残留里的同名类型会把标签并进来 —— 真缺口被掩盖。
    （V168 之前 public.knowledge_source_type_enum 缺 knowledge_doc：旧实现先因 ①类名猜不中类型名而漏报，
    即使猜中，tmp_task25/26 残留里的同名类型带 knowledge_doc，并集后照样看不出缺口。）"""
    assert snap["catalog_review_status_labels"] == ["approved", "draft", "pending_review", "rejected"]
    assert snap["catalog_review_status_column"] == ("USER-DEFINED", "public", "review_status_enum")
