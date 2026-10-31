"""公式时间轴真 PG 合同（spec formula-hub-integrity-closure 任务 28；需求 10.1~10.3；ADR-FHIC-16）。

- 5 类来源各用真实 ORM 行在 pg_tx 内写入 1 条，build_timeline 返回 5 类各 ≥ 1。
- 医疗器械 5e193c68 只读 total ≥ 1。
- 注入子源失败 → unavailable_sources 非空、其余来源照常。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy import select, text

from app.models.audit_log_models import AuditLogEntry
from app.models.core import Project
from app.models.formula_push_models import FormulaPushRun
from app.models.formula_setting_models import (
    FormulaPublish,
    FormulaSyncItem,
    FormulaTemplate,
    FormulaTemplateSubscription,
    FormulaTemplateVersion,
)
from app.services.formula_timeline_service import (
    EVENT_TYPES,
    _SOURCE_LABELS,
    build_timeline,
)

pytestmark = pytest.mark.pg_only

YEAR = 2025
MED_DEVICE_NAME_PATTERN = "%医疗器械%"
MED_DEVICE_ID = uuid.UUID("5e193c68-0000-0000-0000-000000000000")  # 仅作注释，实际按名称查


# ── helpers ──────────────────────────────────────────────────────────────────

async def _find_med_device(session) -> uuid.UUID:
    """查找医疗器械项目（未删、名称含关键字、恰 1 个）。"""
    rows = (await session.execute(
        select(Project.id, Project.name).where(
            Project.is_deleted == sa.false(),
            Project.name.ilike(MED_DEVICE_NAME_PATTERN),
        ).order_by(Project.name)
    )).all()
    if not rows:
        pytest.skip("快照库无医疗器械项目")
    assert len(rows) == 1, f"医疗器械应恰 1 个，实得 {[(str(r.id), r.name) for r in rows]}"
    return rows[0].id


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _create_test_project(session) -> uuid.UUID:
    """在 pg_tx 事务内创建【测试】项目。"""
    project = Project(
        name=f"【测试】fh_t28_timeline_{uuid.uuid4().hex[:10]}",
        client_name="【测试】公式中枢",
    )
    session.add(project)
    await session.flush()
    return project.id


async def _insert_audit_log(session, project_id: uuid.UUID) -> None:
    """插入 1 条 formula.changed 审计日志（payload 含 project_id）。"""
    import hashlib
    prev_hash = hashlib.sha256(b"test_timeline_prev").hexdigest()
    entry_hash = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    entry = AuditLogEntry(
        action_type="formula.changed",
        object_type="formula_setting",
        payload={"project_id": str(project_id), "module": "report", "row_code": "R001", "action": "update"},
        user_id=uuid.uuid4(),
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    session.add(entry)
    await session.flush()


async def _insert_publish(session) -> None:
    """插入 1 条 published 状态的全局发布记录。"""
    pub = FormulaPublish(
        domain="report",
        scope="*",
        source="seed",
        status="published",
        change_set=[{"slot": "test", "action": "add"}],
        published_by=uuid.uuid4(),
    )
    session.add(pub)
    await session.flush()


async def _insert_template_version(session, project_id: uuid.UUID) -> None:
    """插入 1 个模板 + 订阅 + 版本。"""
    tmpl = FormulaTemplate(
        name=f"【测试】t28_tmpl_{uuid.uuid4().hex[:8]}",
        domains=["report"],
    )
    session.add(tmpl)
    await session.flush()

    sub = FormulaTemplateSubscription(
        project_id=project_id,
        domain="report",
        template_id=tmpl.id,
        template_version=1,
        is_active=True,
    )
    session.add(sub)
    await session.flush()

    ver = FormulaTemplateVersion(
        template_id=tmpl.id,
        version=1,
        snapshot={"report": {"slot_1": {"formula": "TB('1001','审定数')"}}},
        published_by=uuid.uuid4(),
    )
    session.add(ver)
    await session.flush()


async def _insert_push_run(session, project_id: uuid.UUID) -> None:
    """插入 1 条推送运行记录。"""
    run = FormulaPushRun(
        project_id=project_id,
        year=YEAR,
        trigger_source="manual",
        status="succeeded",
        written_count=5,
        skipped_count=1,
    )
    session.add(run)
    await session.flush()


async def _insert_conflict(session, project_id: uuid.UUID) -> None:
    """插入 1 条已解决的冲突记录。"""
    item = FormulaSyncItem(
        project_id=project_id,
        domain="report",
        slot_key="R001",
        reason="conflict",
        status="resolved",
        resolution="adopt",
    )
    session.add(item)
    await session.flush()


# ── 测试 ─────────────────────────────────────────────────────────────────────

class TestTimelineFiveSources:
    """需求 10.1：五类来源各用真实字段，真 ORM 各 1 条。"""

    @pytest.mark.asyncio
    async def test_five_sources_each_one_event(self, pg_tx):
        """在 pg_tx 事务内写入 5 类各 1 条，build_timeline 返回 5 类各 ≥ 1。"""
        pid = await _create_test_project(pg_tx)

        await _insert_audit_log(pg_tx, pid)
        await _insert_publish(pg_tx)
        await _insert_template_version(pg_tx, pid)
        await _insert_push_run(pg_tx, pid)
        await _insert_conflict(pg_tx, pid)

        result = await build_timeline(pg_tx, pid, YEAR)

        assert "events" in result
        assert "event_types" in result
        assert "unavailable_sources" in result
        assert result["unavailable_sources"] == [], f"不应有不可用来源：{result['unavailable_sources']}"
        assert result["total"] >= 5, f"至少 5 条事件，实得 {result['total']}"

        type_counts = {}
        for evt in result["events"]:
            t = evt["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        for etype in EVENT_TYPES:
            assert type_counts.get(etype, 0) >= 1, f"类型 {etype} 应 ≥ 1，实得 {type_counts.get(etype, 0)}"

    @pytest.mark.asyncio
    async def test_audit_log_uses_real_ts_field(self, pg_tx):
        """审计日志用 ts 字段（非 created_at），payload->>'project_id' 过滤。"""
        pid = await _create_test_project(pg_tx)
        await _insert_audit_log(pg_tx, pid)

        result = await build_timeline(pg_tx, pid, YEAR)
        audit_events = [e for e in result["events"] if e["type"] == "formula_changed"]
        assert len(audit_events) >= 1
        # timestamp 应来自 ts 字段（非 None）
        assert audit_events[0]["timestamp"] is not None

    @pytest.mark.asyncio
    async def test_publish_uses_published_at_and_status_published(self, pg_tx):
        """发布记录按 status='published' 过滤，时间来自 published_at。"""
        pid = await _create_test_project(pg_tx)
        await _insert_publish(pg_tx)

        result = await build_timeline(pg_tx, pid, YEAR)
        pub_events = [e for e in result["events"] if e["type"] == "global_publish"]
        assert len(pub_events) >= 1
        evt = pub_events[0]
        assert evt["timestamp"] is not None
        # detail 应含 change_set 和 published_by
        assert "change_set" in evt["detail"]
        assert "published_by" in evt["detail"]


class TestMedicalDevice:
    """需求 10.3：医疗器械只读复核 total ≥ 1。"""

    @pytest.mark.asyncio
    async def test_medical_device_total_ge_1(self, pg_tx):
        med_id = await _find_med_device(pg_tx)
        result = await build_timeline(pg_tx, med_id, YEAR)
        assert result["total"] >= 1, f"医疗器械时间轴 total 应 ≥ 1，实得 {result['total']}"


class TestUnavailableSources:
    """需求 10.2：任一子源失败 → unavailable_sources 非空、其余来源照常。"""

    @pytest.mark.asyncio
    async def test_injected_failure_produces_unavailable_sources(self, pg_tx):
        """monkeypatch 审计日志子源抛异常 → unavailable_sources 含该来源、其余 4 源照常。"""
        pid = await _create_test_project(pg_tx)

        # 插入其余 4 源各 1 条（审计日志源被注入失败，不用插）
        await _insert_publish(pg_tx)
        await _insert_template_version(pg_tx, pid)
        await _insert_push_run(pg_tx, pid)
        await _insert_conflict(pg_tx, pid)

        # 注入审计日志子源查询失败
        original_fn = build_timeline.__module__
        import app.services.formula_timeline_service as tl_mod

        _orig = tl_mod._audit_log_events

        async def _exploding(*args, **kwargs):
            raise RuntimeError("模拟审计日志查询失败")

        tl_mod._audit_log_events = _exploding
        try:
            result = await build_timeline(pg_tx, pid, YEAR)
        finally:
            tl_mod._audit_log_events = _orig

        # unavailable_sources 非空
        unavail = result["unavailable_sources"]
        assert len(unavail) >= 1, f"应有不可用来源，实得空列表"
        sources = [u["source"] for u in unavail]
        assert _SOURCE_LABELS["audit_log"] in sources, f"审计日志应在不可用列表中：{unavail}"

        # 其余 4 源照常
        type_counts = {}
        for evt in result["events"]:
            t = evt["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        for etype in ["global_publish", "push_run", "conflict_resolved"]:
            assert type_counts.get(etype, 0) >= 1, f"注入失败后类型 {etype} 应 ≥ 1"

    @pytest.mark.asyncio
    async def test_all_sources_fail_returns_empty_events(self, pg_tx):
        """全部 5 源都失败 → events 空、unavailable_sources 含 5 条。"""
        pid = await _create_test_project(pg_tx)

        import app.services.formula_timeline_service as tl_mod

        originals = {}
        source_fns = ["_audit_log_events", "_publish_events", "_template_events",
                       "_push_events", "_conflict_events"]
        for name in source_fns:
            originals[name] = getattr(tl_mod, name)

            async def _exploding(*args, _name=name, **kwargs):
                raise RuntimeError(f"模拟 {_name} 失败")

            setattr(tl_mod, name, _exploding)

        try:
            result = await build_timeline(pg_tx, pid, YEAR)
        finally:
            for name, fn in originals.items():
                setattr(tl_mod, name, fn)

        assert result["events"] == []
        assert result["total"] == 0
        assert len(result["unavailable_sources"]) == 5
