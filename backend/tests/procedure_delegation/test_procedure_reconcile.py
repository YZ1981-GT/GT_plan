# Feature: procedure-delegation-notification — Task 5 模板 reconcile 与显式继承
"""ProcedureReconcileService 测试：Property P8 + PostgreSQL 集成（revision/别名/歧义/孤儿）。

Task 5 / 需求 1.6, 3.1-3.2, 3.8, 4.2-4.6 / Design C3、D4：

- **P8（reconcile 不确定项零继承）**：Requirements 3.1, 3.2, 3.8 —— 纯分类 Hypothesis PBT，
  任意 sources/targets，ambiguous/orphaned/conflict 的 source **绝不** 出现在 matched；
  matched 只用 exact_key/legacy_alias/normalized_content 三法且每个 source 恰属一类。
- **PostgreSQL 集成**：真实 reconcile/apply 行为（内容匹配迁移 revision、legacy alias 匹配、
  歧义零继承、孤儿零继承、一次性 preview 消费、篡改/版本 409）。

数据库约束/事务在 PostgreSQL 验证，不以 sqlite 替代（memory 铁律）。PBT 用项目 fast profile。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings as app_settings
from app.core.migration_runner import MigrationRunner
from app.services.procedure_reconcile_service import (
    METHOD_EXACT_KEY,
    METHOD_LEGACY_ALIAS,
    METHOD_NORMALIZED_CONTENT,
    ProcedureReconcileService,
    ReconcileDefn,
    classify,
    is_legacy_uuid_key,
)

_V105 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V105__procedure_row_tasks.sql"
)
_IS_PG = app_settings.DATABASE_URL.startswith("postgresql")
_METHODS = {METHOD_EXACT_KEY, METHOD_LEGACY_ALIAS, METHOD_NORMALIZED_CONTENT}


# ===========================================================================
# P8：reconcile 不确定项零继承（纯分类 PBT）
# Validates: Requirements 3.1, 3.2, 3.8
# ===========================================================================

# 内容寻址 key 池（含 ::）与 legacy key 池（不含 ::）
_CONTENT_KEYS = [f"D2A::D2A::{i:04x}" for i in range(6)]
_LEGACY_KEYS = ["row-1", "row-2", f"legacy-{uuid.uuid4().hex[:8]}", "index-0"]
_CONTENT_LABELS = ["c0", "c1", "c2", "c3"]


@st.composite
def _defn(draw, *, is_source: bool):
    key = draw(st.sampled_from(_CONTENT_KEYS + _LEGACY_KEYS))
    label = draw(st.sampled_from(_CONTENT_LABELS))
    aliases = draw(st.lists(st.sampled_from(_CONTENT_KEYS + _LEGACY_KEYS), max_size=3, unique=True))
    return ReconcileDefn(
        definition_key=key,
        normalized_content={"c": label},
        legacy_aliases=aliases,
        program_no=draw(st.sampled_from(["1", "2", "3"])),
        sheet_key="D2A",
        task_id=(str(uuid.uuid4()) if is_source else None),
    )


class TestP8ZeroInheritance:
    @given(
        sources=st.lists(_defn(is_source=True), max_size=6),
        targets=st.lists(_defn(is_source=False), max_size=6, unique_by=lambda d: d.definition_key),
    )
    @settings(max_examples=5)
    def test_uncertain_never_matched_and_partition(self, sources, targets):
        result = classify(sources, targets)

        matched_ids = {m["source_id"] for m in result["matched"]}
        ambiguous_ids = {a["source_id"] for a in result["ambiguous"]}
        orphaned_ids = {o["source_id"] for o in result["orphaned"]}
        conflict_ids = {c["source_id"] for c in result["conflict"]}

        # P8 核心：不确定项（歧义/孤儿/冲突）的 source 绝不出现在 matched
        uncertain = ambiguous_ids | orphaned_ids | conflict_ids
        assert matched_ids.isdisjoint(uncertain), (
            f"不确定项被错误继承: matched∩uncertain={matched_ids & uncertain}"
        )

        # 每个 source 恰属一类（分区）
        all_ids = matched_ids | uncertain
        assert len(all_ids) == len({s.task_id for s in sources})
        # 四类之间两两不相交
        buckets = [matched_ids, ambiguous_ids, orphaned_ids, conflict_ids]
        for i in range(len(buckets)):
            for j in range(i + 1, len(buckets)):
                assert buckets[i].isdisjoint(buckets[j])

        # matched 只用三种合法方法；exact_key 的 target 必等于 source
        for m in result["matched"]:
            assert m["method"] in _METHODS
            if m["method"] == METHOD_EXACT_KEY:
                assert m["target_key"] == m["source_key"]

        # unmatched target 恰为未被 matched 消费的 target
        consumed = {m["target_key"] for m in result["matched"]}
        unmatched = {u["target_key"] for u in result["unmatched"]}
        assert unmatched == {t.definition_key for t in targets} - consumed

    def test_exact_key_match(self):
        s = ReconcileDefn(definition_key="D2A::D2A::abcd", normalized_content={"c": "x"}, task_id="t1")
        t = ReconcileDefn(definition_key="D2A::D2A::abcd", normalized_content={"c": "x"})
        r = classify([s], [t])
        assert len(r["matched"]) == 1 and r["matched"][0]["method"] == METHOD_EXACT_KEY

    def test_content_match_when_key_changed(self):
        s = ReconcileDefn(definition_key="D2A::D2A::old0", normalized_content={"c": "same"}, task_id="t1")
        t = ReconcileDefn(definition_key="D2A::D2A::new0", normalized_content={"c": "same"})
        r = classify([s], [t])
        assert len(r["matched"]) == 1
        assert r["matched"][0]["method"] == METHOD_NORMALIZED_CONTENT
        assert r["matched"][0]["target_key"] == "D2A::D2A::new0"

    def test_alias_match(self):
        s = ReconcileDefn(definition_key="D2A::D2A::old0", normalized_content={"c": "a"}, task_id="t1")
        t = ReconcileDefn(
            definition_key="D2A::D2A::new0",
            normalized_content={"c": "b"},
            legacy_aliases=["D2A::D2A::old0"],
        )
        r = classify([s], [t])
        assert len(r["matched"]) == 1 and r["matched"][0]["method"] == METHOD_LEGACY_ALIAS

    def test_ambiguous_multi_alias(self):
        s = ReconcileDefn(definition_key="D2A::D2A::old0", normalized_content={"c": "a"}, task_id="t1")
        t1 = ReconcileDefn(definition_key="D2A::D2A::n1", normalized_content={"c": "b"}, legacy_aliases=["D2A::D2A::old0"])
        t2 = ReconcileDefn(definition_key="D2A::D2A::n2", normalized_content={"c": "c"}, legacy_aliases=["D2A::D2A::old0"])
        r = classify([s], [t1, t2])
        assert len(r["ambiguous"]) == 1 and not r["matched"]

    def test_orphaned_content_key(self):
        s = ReconcileDefn(definition_key="D2A::D2A::gone", normalized_content={"c": "z"}, task_id="t1")
        t = ReconcileDefn(definition_key="D2A::D2A::other", normalized_content={"c": "y"})
        r = classify([s], [t])
        assert len(r["orphaned"]) == 1 and not r["matched"]

    def test_legacy_uuid_unresolvable_is_conflict(self):
        s = ReconcileDefn(definition_key="row-7", normalized_content={"c": "z"}, task_id="t1")
        t = ReconcileDefn(definition_key="D2A::D2A::other", normalized_content={"c": "y"})
        r = classify([s], [t])
        assert len(r["conflict"]) == 1 and r["conflict"][0]["reason"] == "legacy_uuid_unresolvable"

    def test_alias_content_contradiction_is_conflict(self):
        s = ReconcileDefn(definition_key="D2A::D2A::old0", normalized_content={"c": "same"}, task_id="t1")
        t_alias = ReconcileDefn(definition_key="D2A::D2A::n1", normalized_content={"c": "diff"}, legacy_aliases=["D2A::D2A::old0"])
        t_content = ReconcileDefn(definition_key="D2A::D2A::n2", normalized_content={"c": "same"})
        r = classify([s], [t_alias, t_content])
        assert len(r["conflict"]) == 1 and r["conflict"][0]["reason"] == "alias_content_contradiction"

    def test_is_legacy_uuid_key(self):
        assert is_legacy_uuid_key("row-1")
        assert is_legacy_uuid_key(str(uuid.uuid4()))
        assert not is_legacy_uuid_key("D2A::D2A::abcd")


# ===========================================================================
# PostgreSQL 集成：真实 reconcile/apply 行为
# ===========================================================================


async def _apply_v105(engine) -> None:
    sql = _V105.read_text(encoding="utf-8")
    for stmt in MigrationRunner._split_sql_statements(sql):
        async with engine.begin() as conn:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (reconcile apply / preview integration)")
    engine = create_async_engine(app_settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    await _apply_v105(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _pick_project_wp_index(factory):
    async with factory() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT wp.project_id, wp.wp_index_id, wi.wp_code, "
                    "COALESCE(wi.audit_cycle, 'A') "
                    "FROM working_paper wp JOIN wp_index wi ON wi.id = wp.wp_index_id "
                    "WHERE wp.is_deleted = false AND wi.is_deleted = false LIMIT 1"
                )
            )
        ).first()
    return row


async def _pick_user(factory):
    async with factory() as s:
        row = (await s.execute(sa.text("SELECT id FROM users LIMIT 1"))).first()
    return row[0] if row else None


async def _insert_definition(
    factory, template_code, sheet_key, definition_key, revision, *, content_label, aliases=None
):
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_definitions "
                "(definition_key, template_code, template_revision_hash, sheet_key, "
                " source_locator, procedure_text, ref_snapshot, legacy_aliases, normalized_content) "
                "VALUES (:k, :tc, :h, :sk, '{}'::jsonb, :pt, '[]'::jsonb, "
                " CAST(:al AS jsonb), CAST(:nc AS jsonb))"
            ),
            {
                "k": definition_key,
                "tc": template_code,
                "h": revision,
                "sk": sheet_key,
                "pt": f"程序文本 {content_label}",
                "al": json.dumps(aliases or []),
                "nc": json.dumps({"c": content_label}),
            },
        )
        await s.commit()


async def _insert_task(
    factory, project_id, wp_index_id, wp_code, sheet_key, definition_key, revision, *,
    workflow="assigned", assignment_version=2, lock_version=1,
):
    task_id = uuid.uuid4()
    async with factory() as s:
        await s.execute(
            sa.text(
                "INSERT INTO procedure_row_tasks "
                "(id, project_id, wp_index_id, definition_key, sheet_key, wp_code, "
                " definition_revision_hash, audit_cycle_snapshot, applicability_status, "
                " workflow_status, assignment_version, lock_version) "
                "VALUES (:id, :pid, :wi, :dk, :sk, :wc, :h, 'A', 'execute', "
                " :wf, :av, :lv)"
            ),
            {
                "id": task_id, "pid": project_id, "wi": wp_index_id, "dk": definition_key,
                "sk": sheet_key, "wc": wp_code, "h": revision, "wf": workflow,
                "av": assignment_version, "lv": lock_version,
            },
        )
        await s.commit()
    return task_id


async def _task_row(factory, task_id):
    async with factory() as s:
        return (
            await s.execute(
                sa.text(
                    "SELECT definition_key, definition_revision_hash, workflow_status, "
                    "assignment_version, lock_version FROM procedure_row_tasks WHERE id=:id"
                ),
                {"id": task_id},
            )
        ).first()


async def _history_count(factory, task_id):
    async with factory() as s:
        return (
            await s.execute(
                sa.text("SELECT count(*) FROM procedure_row_task_history WHERE task_id=:id"),
                {"id": task_id},
            )
        ).scalar()


async def _cleanup(factory, definition_keys, task_ids):
    async with factory() as s:
        for tid in task_ids:
            await s.execute(sa.text("DELETE FROM procedure_row_task_history WHERE task_id=:id"), {"id": tid})
        for tid in task_ids:
            await s.execute(sa.text("DELETE FROM procedure_row_tasks WHERE id=:id"), {"id": tid})
        for k in definition_keys:
            await s.execute(sa.text("DELETE FROM procedure_row_definitions WHERE definition_key=:k"), {"k": k})
        await s.commit()


@pytest.mark.asyncio
class TestPgReconcile:
    async def test_content_match_migrates_revision_preserves_workflow(self, pg_engine):
        """内容匹配：key 变、内容不变 → 迁移到新 revision；workflow/assignment_version 不变 + 记 history。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, wp_code, _cycle = picked
        tmpl = f"{wp_code}A"
        old_key = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        new_key = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        old_rev, new_rev = "a" * 64, "b" * 64
        await _insert_definition(factory, tmpl, tmpl, old_key, old_rev, content_label="same")
        await _insert_definition(factory, tmpl, tmpl, new_key, new_rev, content_label="same")
        task_id = await _insert_task(factory, project_id, wp_index_id, wp_code, tmpl, old_key, old_rev)
        try:
            svc_factory = factory
            # preview
            async with svc_factory() as s:
                svc = ProcedureReconcileService(s)
                pv = await svc.preview(
                    project_id, actor_user_id=user_id, template_code=wp_code, target_revision=new_rev
                )
                await s.commit()
            assert pv["summary"]["matched"] >= 1
            # apply
            async with svc_factory() as s:
                svc = ProcedureReconcileService(s)
                res = await svc.apply(
                    project_id, actor_user_id=user_id, preview_id=uuid.UUID(pv["preview_id"]),
                    request_id="req-1", template_code=wp_code, target_revision=new_rev,
                )
                await s.commit()
            assert res["applied"] >= 1
            row = await _task_row(factory, task_id)
            assert row[0] == new_key           # definition_key 迁移
            assert row[1] == new_rev           # revision 更新
            assert row[2] == "assigned"        # workflow 不变
            assert row[3] == 2                 # assignment_version 不变
            assert row[4] == 2                 # lock_version +1
            assert await _history_count(factory, task_id) == 1
        finally:
            await _cleanup(factory, [old_key, new_key], [task_id])

    async def test_alias_match_migrates(self, pg_engine):
        """legacy alias 匹配：新定义 aliases 含旧 key → 迁移。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, wp_code, _cycle = picked
        tmpl = f"{wp_code}A"
        old_key = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        new_key = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        old_rev, new_rev = "c" * 64, "d" * 64
        await _insert_definition(factory, tmpl, tmpl, old_key, old_rev, content_label="alpha")
        await _insert_definition(
            factory, tmpl, tmpl, new_key, new_rev, content_label="beta", aliases=[old_key]
        )
        task_id = await _insert_task(factory, project_id, wp_index_id, wp_code, tmpl, old_key, old_rev)
        try:
            async with factory() as s:
                svc = ProcedureReconcileService(s)
                pv = await svc.preview(project_id, actor_user_id=user_id, template_code=wp_code, target_revision=new_rev)
                await s.commit()
            async with factory() as s:
                svc = ProcedureReconcileService(s)
                res = await svc.apply(
                    project_id, actor_user_id=user_id, preview_id=uuid.UUID(pv["preview_id"]),
                    request_id="req-alias", template_code=wp_code, target_revision=new_rev,
                )
                await s.commit()
            assert res["applied"] >= 1
            row = await _task_row(factory, task_id)
            assert row[0] == new_key
        finally:
            await _cleanup(factory, [old_key, new_key], [task_id])

    async def test_ambiguous_and_orphaned_zero_inheritance(self, pg_engine):
        """P8 集成：歧义/孤儿任务 apply 后零变化（definition/workflow/version 不变 + 无 history）。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, wp_code, _cycle = picked
        tmpl = f"{wp_code}A"
        old_amb = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        old_orph = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        n1 = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        n2 = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        old_rev, new_rev = "e" * 64, "f" * 64
        await _insert_definition(factory, tmpl, tmpl, old_amb, old_rev, content_label="amb")
        await _insert_definition(factory, tmpl, tmpl, old_orph, old_rev, content_label="orph")
        # 两个新定义都把 old_amb 列为 alias → 歧义
        await _insert_definition(factory, tmpl, tmpl, n1, new_rev, content_label="x", aliases=[old_amb])
        await _insert_definition(factory, tmpl, tmpl, n2, new_rev, content_label="y", aliases=[old_amb])
        t_amb = await _insert_task(factory, project_id, wp_index_id, wp_code, tmpl, old_amb, old_rev)
        t_orph = await _insert_task(factory, project_id, wp_index_id, wp_code, tmpl, old_orph, old_rev)
        try:
            async with factory() as s:
                svc = ProcedureReconcileService(s)
                pv = await svc.preview(project_id, actor_user_id=user_id, template_code=wp_code, target_revision=new_rev)
                await s.commit()
            assert pv["summary"]["ambiguous"] >= 1
            assert pv["summary"]["orphaned"] >= 1
            async with factory() as s:
                svc = ProcedureReconcileService(s)
                res = await svc.apply(
                    project_id, actor_user_id=user_id, preview_id=uuid.UUID(pv["preview_id"]),
                    request_id="req-amb", template_code=wp_code, target_revision=new_rev,
                )
                await s.commit()
            # 歧义/孤儿任务未被迁移
            amb_row = await _task_row(factory, t_amb)
            orph_row = await _task_row(factory, t_orph)
            assert amb_row[0] == old_amb and amb_row[1] == old_rev and amb_row[4] == 1
            assert orph_row[0] == old_orph and orph_row[1] == old_rev and orph_row[4] == 1
            assert await _history_count(factory, t_amb) == 0
            assert await _history_count(factory, t_orph) == 0
        finally:
            await _cleanup(factory, [old_amb, old_orph, n1, n2], [t_amb, t_orph])

    async def test_preview_one_time_consume_and_idempotent(self, pg_engine):
        """一次性消费：二次 apply（新 request_id）409；相同 request_id 幂等返回旧 result。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, wp_code, _cycle = picked
        tmpl = f"{wp_code}A"
        old_key = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        new_key = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        old_rev, new_rev = "1" * 64, "2" * 64
        await _insert_definition(factory, tmpl, tmpl, old_key, old_rev, content_label="same")
        await _insert_definition(factory, tmpl, tmpl, new_key, new_rev, content_label="same")
        task_id = await _insert_task(factory, project_id, wp_index_id, wp_code, tmpl, old_key, old_rev)
        try:
            async with factory() as s:
                svc = ProcedureReconcileService(s)
                pv = await svc.preview(project_id, actor_user_id=user_id, template_code=wp_code, target_revision=new_rev)
                await s.commit()
            pvid = uuid.UUID(pv["preview_id"])
            async with factory() as s:
                svc = ProcedureReconcileService(s)
                r1 = await svc.apply(
                    project_id, actor_user_id=user_id, preview_id=pvid,
                    request_id="rc-1", template_code=wp_code, target_revision=new_rev,
                )
                await s.commit()
            # 相同 request_id 幂等
            async with factory() as s:
                svc = ProcedureReconcileService(s)
                r_replay = await svc.apply(
                    project_id, actor_user_id=user_id, preview_id=pvid,
                    request_id="rc-1", template_code=wp_code, target_revision=new_rev,
                )
                await s.commit()
            assert r_replay == r1
            # 不同 request_id → 409 已消费
            async with factory() as s:
                svc = ProcedureReconcileService(s)
                with pytest.raises(HTTPException) as ei:
                    await svc.apply(
                        project_id, actor_user_id=user_id, preview_id=pvid,
                        request_id="rc-2", template_code=wp_code, target_revision=new_rev,
                    )
                await s.rollback()
            assert ei.value.status_code == 409
        finally:
            await _cleanup(factory, [old_key, new_key], [task_id])

    async def test_version_change_returns_409(self, pg_engine):
        """目标 task lock_version 自 preview 后变化 → apply 409（版本冲突）。"""
        factory = async_sessionmaker(pg_engine, expire_on_commit=False)
        picked = await _pick_project_wp_index(factory)
        user_id = await _pick_user(factory)
        if picked is None or user_id is None:
            pytest.skip("dev 库无可复用 project/wp_index/user")
        project_id, wp_index_id, wp_code, _cycle = picked
        tmpl = f"{wp_code}A"
        old_key = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        new_key = f"{tmpl}::{tmpl}::{uuid.uuid4().hex[:12]}"
        old_rev, new_rev = "3" * 64, "4" * 64
        await _insert_definition(factory, tmpl, tmpl, old_key, old_rev, content_label="same")
        await _insert_definition(factory, tmpl, tmpl, new_key, new_rev, content_label="same")
        task_id = await _insert_task(factory, project_id, wp_index_id, wp_code, tmpl, old_key, old_rev)
        try:
            async with factory() as s:
                svc = ProcedureReconcileService(s)
                pv = await svc.preview(project_id, actor_user_id=user_id, template_code=wp_code, target_revision=new_rev)
                await s.commit()
            # 外部 bump task lock_version
            async with factory() as s:
                await s.execute(
                    sa.text("UPDATE procedure_row_tasks SET lock_version=lock_version+1 WHERE id=:id"),
                    {"id": task_id},
                )
                await s.commit()
            async with factory() as s:
                svc = ProcedureReconcileService(s)
                with pytest.raises(HTTPException) as ei:
                    await svc.apply(
                        project_id, actor_user_id=user_id, preview_id=uuid.UUID(pv["preview_id"]),
                        request_id="rc-ver", template_code=wp_code, target_revision=new_rev,
                    )
                await s.rollback()
            assert ei.value.status_code == 409
        finally:
            await _cleanup(factory, [old_key, new_key], [task_id])
