"""签发一致性清单 —— 真 SQLite + 真 ORM（spec deliverable-writeback-and-online-edit-integrity Phase A）。

历史版本全靠 mock ``db.execute``：9 条 SQL 里 8 条对真实 schema 无效、在真实 PG 上恒「可签发」，而 mock 测试全绿。
本文件改为真表真行：每项检查一条正例一条反例 + 执行失败按阻断（fail-closed）+ 端点鉴权 / 年度。
SAVEPOINT 隔离（一项失败其余照常）只有 PG 能证明（SQLite 语句失败不中止事务），见 ``test_signoff_checklist_pg.py``。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.core.database import get_db
from app.deps import get_current_user
from app.models.ai_models import AIContent
from app.models.audit_platform_models import Adjustment, Materiality, TrialBalance, UnadjustedMisstatement
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.evidence_governance_models import AiContentGovernance
from app.models.report_models import AuditReport, DisclosureNote, FinancialReport
from app.models.v3_refinement_models import CrossModuleConflict
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services import ai_content_gate
from app.services.signoff_checklist_service import CheckSeverity, SignoffChecklistService

PID = uuid.uuid4()
OTHER_PID = uuid.uuid4()
YEAR = 2025
ACTOR = uuid.uuid4()

TABLES = [
    User.__table__, Project.__table__, ProjectUser.__table__, TrialBalance.__table__, Adjustment.__table__,
    CrossModuleConflict.__table__, AuditReport.__table__, WpIndex.__table__, WorkingPaper.__table__,
    FinancialReport.__table__, DisclosureNote.__table__, UnadjustedMisstatement.__table__, Materiality.__table__,
    AIContent.__table__, AiContentGovernance.__table__,
]


def _enum(model, column: str, value: str):
    """按列的枚举类取成员（不同模型的枚举类分散在各处，按列取避免猜导入路径）。"""
    return model.__table__.c[column].type.enum_class(value)


def _run(scenario):
    async def _main():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                return await scenario(session)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


# ─── 造数 ─────────────────────────────────────────────────────────────


def _tb(code: str = "1001", *, unadj: str = "100", aje: str = "0", audited: str = "100", pid=PID) -> TrialBalance:
    return TrialBalance(
        project_id=pid, year=YEAR, company_code="001", standard_account_code=code, account_name="货币资金",
        account_category=_enum(TrialBalance, "account_category", "asset"),
        unadjusted_amount=Decimal(unadj), aje_adjustment=Decimal(aje), rje_adjustment=Decimal("0"),
        wp_adjustment=Decimal("0"), audited_amount=Decimal(audited),
    )


def _report(*, status: str = "final", stale: bool = False, pid=PID) -> AuditReport:
    return AuditReport(
        project_id=pid, year=YEAR, opinion_type=_enum(AuditReport, "opinion_type", "unqualified"),
        status=_enum(AuditReport, "status", status), is_stale=stale,
    )


def _adj(no: str, status: str, *, deleted: bool = False, pid=PID, group=None) -> Adjustment:
    return Adjustment(
        project_id=pid, year=YEAR, company_code="001", adjustment_no=no,
        adjustment_type=_enum(Adjustment, "adjustment_type", "aje"), account_code="1001",
        entry_group_id=group or uuid.uuid4(), review_status=_enum(Adjustment, "review_status", status),
        is_deleted=deleted, created_by=ACTOR, debit_amount=Decimal("10"), credit_amount=Decimal("0"),
    )


async def _clean(s: AsyncSession) -> None:
    """一个可以签发的项目：试算表一致、报告已定稿，其他都没有。"""
    s.add_all([_tb(), _report()])
    await s.flush()


async def _checklist(s: AsyncSession):
    return await SignoffChecklistService(s).generate_checklist(project_id=PID, year=YEAR)


def _by(cl, category: str, severity: CheckSeverity | None = None) -> list:
    return [i for i in cl.items if i.category == category and (severity is None or i.severity == severity)]


# ─── 各项检查 ─────────────────────────────────────────────────────────


def test_clean_project_can_signoff_and_every_check_reports():
    async def _s(s):
        await _clean(s)
        return await _checklist(s)

    cl = _run(_s)
    assert cl.can_signoff is True and cl.has_warnings is False
    assert {i.category for i in cl.items} == {"trial_balance", "adjustment", "conflict", "report", "stale", "ai_content"}
    assert all(i.severity == CheckSeverity.info for i in cl.items), [i.message for i in cl.items]
    assert not any("执行失败" in i.message for i in cl.items)


def test_trial_balance_without_rows_blocks():
    async def _s(s):
        s.add(_report())
        await s.flush()
        return await _checklist(s)

    cl = _run(_s)
    assert cl.can_signoff is False
    assert "无数据" in _by(cl, "trial_balance", CheckSeverity.blocking)[0].message


def test_trial_balance_formula_mismatch_blocks_with_account_code():
    async def _s(s):
        s.add_all([_tb("1001"), _tb("1122", unadj="100", aje="20", audited="100"), _report()])
        await s.flush()
        return await _checklist(s)

    blocking = _by(_run(_s), "trial_balance", CheckSeverity.blocking)
    assert len(blocking) == 1 and "1122" in blocking[0].message


def test_unapproved_adjustments_block_once_per_entry():
    async def _s(s):
        await _clean(s)
        g = uuid.uuid4()
        s.add_all([
            _adj("AJE-1", "draft", group=g), _adj("AJE-1", "draft", group=g),  # 同一笔两行 ⇒ 只算一笔
            _adj("AJE-2", "pending_review"),
            _adj("AJE-3", "approved"),                       # 已审批：不算
            _adj("AJE-4", "draft", deleted=True),            # 已删除：不算
            _adj("AJE-9", "draft", pid=OTHER_PID),           # 其他项目：不算
        ])
        await s.flush()
        return await _checklist(s)

    cl = _run(_s)
    blocking = _by(cl, "adjustment", CheckSeverity.blocking)
    assert [b.message.split("（")[0] for b in blocking] == ["调整分录 AJE-1", "调整分录 AJE-2"]
    assert "为草稿" in blocking[0].message and "待复核" in blocking[1].message
    assert cl.can_signoff is False


def test_pending_cross_module_conflict_blocks_and_links_to_target():
    async def _s(s):
        await _clean(s)
        wp_id = uuid.uuid4()
        s.add_all([
            CrossModuleConflict(project_id=PID, source_module="workpaper", source_id=uuid.uuid4(),
                                target_module="workpaper", target_id=wp_id, target_field="审定数", status="pending"),
            CrossModuleConflict(project_id=PID, source_module="workpaper", source_id=uuid.uuid4(),
                                target_module="disclosure", target_id=uuid.uuid4(), target_field="表格",
                                status="resolved"),
        ])
        await s.flush()
        return wp_id, await _checklist(s)

    wp_id, cl = _run(_s)
    blocking = _by(cl, "conflict", CheckSeverity.blocking)
    assert len(blocking) == 1
    assert blocking[0].route == f"/projects/{PID}/workpapers/{wp_id}/edit"
    assert "底稿 → 底稿" in blocking[0].message


def test_missing_report_blocks_and_stale_report_warns():
    async def _missing(s):
        s.add(_tb())
        await s.flush()
        return await _checklist(s)

    async def _stale(s):
        s.add_all([_tb(), _report(status="draft", stale=True)])
        await s.flush()
        return await _checklist(s)

    missing = _by(_run(_missing), "report", CheckSeverity.blocking)
    assert missing and "未生成" in missing[0].message and missing[0].route == f"/projects/{PID}/audit-report"
    stale = _run(_stale)
    assert stale.can_signoff is True
    assert "过期" in _by(stale, "report", CheckSeverity.warning)[0].message
    assert "草稿" in _by(stale, "report", CheckSeverity.info)[0].message
    assert "无保留意见" in _by(stale, "report", CheckSeverity.info)[0].message


def test_stale_sources_each_warn_but_do_not_block():
    """底稿 / 报表行 / 附注 / 未更正错报的过期各一条 warning（与签字页「项目状态摘要」同源）。"""
    async def _s(s):
        await _clean(s)
        idx = WpIndex(project_id=PID, wp_code="E1", wp_name="货币资金")
        s.add(idx)
        await s.flush()
        old = datetime(2025, 1, 1, tzinfo=timezone.utc)
        s.add_all([
            WorkingPaper(project_id=PID, wp_index_id=idx.id, file_path="x.xlsx",
                         source_type=_enum(WorkingPaper, "source_type", "template"), prefill_stale=True),
            FinancialReport(project_id=PID, year=YEAR, report_type=_enum(FinancialReport, "report_type", "balance_sheet"),
                            row_code="BS-042", row_name="交易性金融负债", is_stale=True),
            DisclosureNote(project_id=PID, year=YEAR, note_section="八、1", section_title="货币资金", is_stale=True),
            UnadjustedMisstatement(project_id=PID, year=YEAR, misstatement_description="跨期", misstatement_amount=Decimal("5"),
                                   misstatement_type=_enum(UnadjustedMisstatement, "misstatement_type", "factual"),
                                   updated_at=old),
            Materiality(project_id=PID, year=YEAR, benchmark_type="revenue", benchmark_amount=Decimal("1000"),
                        overall_percentage=Decimal("1"), overall_materiality=Decimal("10"),
                        performance_ratio=Decimal("0.5"), performance_materiality=Decimal("5"),
                        trivial_ratio=Decimal("0.05"), trivial_threshold=Decimal("0.5"),
                        updated_at=old + timedelta(days=30)),
        ])
        await s.flush()
        return await _checklist(s)

    cl = _run(_s)
    warnings = _by(cl, "stale", CheckSeverity.warning)
    texts = " / ".join(w.message for w in warnings)
    assert len(warnings) == 4, texts
    assert "E1" in texts and "交易性金融负债" in texts and "八、1" in texts and "重要性水平" in texts
    assert cl.can_signoff is True and cl.has_warnings is True


def test_ai_content_pending_warns_and_strict_mode_blocks(monkeypatch):
    async def _s(s):
        await _clean(s)
        wp = uuid.uuid4()
        ctype = _enum(AIContent, "content_type", "note_draft")
        s.add_all([
            AIContent(project_id=PID, workpaper_id=wp, content_type=ctype, content_text="草稿",
                      confirmation_status=_enum(AIContent, "confirmation_status", "pending")),
            AIContent(project_id=PID, content_type=ctype, content_text="已采纳",
                      confirmation_status=_enum(AIContent, "confirmation_status", "accepted")),
            AIContent(project_id=PID, content_type=ctype, content_text="已删", is_deleted=True,
                      confirmation_status=_enum(AIContent, "confirmation_status", "pending")),
            AiContentGovernance(project_id=PID, audit_year=YEAR, entry_point="wp", model_name="m",
                                actor_type="user", actor_user_id=ACTOR, lifecycle_status="draft"),
            AiContentGovernance(project_id=PID, audit_year=YEAR, entry_point="wp", model_name="m",
                                actor_type="user", actor_user_id=ACTOR, lifecycle_status="confirmed"),
            AiContentGovernance(project_id=PID, audit_year=YEAR - 1, entry_point="wp", model_name="m",
                                actor_type="user", actor_user_id=ACTOR, lifecycle_status="draft"),
        ])
        await s.flush()
        return wp, await _checklist(s)

    wp, cl = _run(_s)
    warning = _by(cl, "ai_content", CheckSeverity.warning)
    assert len(warning) == 1 and "2 条" in warning[0].message, warning
    detail = _by(cl, "ai_content", CheckSeverity.info)
    assert detail and detail[0].route == f"/projects/{PID}/workpapers/{wp}/edit" and "附注草稿" in detail[0].message
    assert cl.can_signoff is True

    monkeypatch.setattr(ai_content_gate, "AI_CONTENT_CONFIRMATION_STRICT", True)
    _wp, strict = _run(_s)
    assert _by(strict, "ai_content", CheckSeverity.blocking) and strict.can_signoff is False


def test_check_failure_is_blocking_not_info(monkeypatch):
    """检查执行失败 = 无法确认 = 阻断（历史实现降级成 info「暂不可用」⇒ 恒可签发）。"""
    async def _boom(self, project_id, year, pid):
        raise RuntimeError("模拟查询失败")

    monkeypatch.setattr(SignoffChecklistService, "_check_report", _boom)

    async def _s(s):
        await _clean(s)
        return await _checklist(s)

    cl = _run(_s)
    failed = _by(cl, "report", CheckSeverity.blocking)
    assert len(failed) == 1 and "执行失败" in failed[0].message and "RuntimeError" in failed[0].message
    assert cl.can_signoff is False
    # 其余检查照常给结果
    assert _by(cl, "trial_balance", CheckSeverity.info) and _by(cl, "adjustment", CheckSeverity.info)


# ─── 端点：项目鉴权 / 年度 / 确认留痕 ───────────────────────────────────


class _Actor:
    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.auditor) -> None:
        self.id, self.role, self.is_active = uid, role, True
        self.username = f"u-{uid.hex[-4:]}"
        self.email = f"{self.username}@example.com"


def _api(scenario):
    """真路由 + 真鉴权依赖；``scenario(client, ids)``。"""
    from app.routers import signoff_checklist

    async def _main():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        ids = {k: uuid.uuid4() for k in ("member", "outsider", "named", "bare")}
        async with factory() as s:
            s.add_all([
                Project(id=PID, name="甲公司", client_name="甲", audit_year=YEAR, status=ProjectStatus.execution),
                Project(id=ids["named"], name="乙公司_2025", client_name="乙", status=ProjectStatus.execution),
                Project(id=ids["bare"], name="丙公司", client_name="丙", status=ProjectStatus.execution),
            ])
            for pid in (PID, ids["named"], ids["bare"]):
                s.add(ProjectUser(project_id=pid, user_id=ids["member"], role=ProjectUserRole.auditor,
                                  permission_level=PermissionLevel.readonly))
            s.add_all([_tb(), _report()])
            await s.commit()

        app = FastAPI()
        app.include_router(signoff_checklist.router)

        async def _db():
            async with factory() as session:
                yield session

        actor = {"user": _Actor(ids["member"])}
        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: actor["user"]
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await scenario(client, ids, actor)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


def test_endpoint_requires_project_membership():
    async def _s(client, ids, actor):
        ok = await client.get(f"/api/projects/{PID}/signoff/checklist", params={"year": YEAR})
        actor["user"] = _Actor(ids["outsider"])
        denied = await client.get(f"/api/projects/{PID}/signoff/checklist", params={"year": YEAR})
        denied_confirm = await client.post(f"/api/projects/{PID}/signoff/confirm-warning", json={"item_index": 0})
        actor["user"] = _Actor(ids["outsider"], role=UserRole.admin)
        admin = await client.get(f"/api/projects/{PID}/signoff/checklist", params={"year": YEAR})
        return ok, denied, denied_confirm, admin

    ok, denied, denied_confirm, admin = _api(_s)
    assert ok.status_code == 200 and ok.json()["can_signoff"] is True
    assert denied.status_code == 403 and denied_confirm.status_code == 403
    assert admin.status_code == 200


def test_endpoint_year_resolution_never_guesses_calendar_year():
    async def _s(client, ids, actor):
        own = await client.get(f"/api/projects/{PID}/signoff/checklist")            # audit_year 列
        named = await client.get(f"/api/projects/{ids['named']}/signoff/checklist")  # 名称后缀 _2025
        bare = await client.get(f"/api/projects/{ids['bare']}/signoff/checklist")    # 无任何年度线索
        return own, named, bare

    own, named, bare = _api(_s)
    assert own.status_code == 200 and own.json()["year"] == YEAR
    assert named.status_code == 200 and named.json()["year"] == YEAR
    assert bare.status_code == 422 and "审计年度" in bare.text


def test_confirm_warning_reports_failure_when_audit_log_cannot_be_written():
    """SQLite 无 ``app_audit_log``：留痕写不进 ⇒ 503，不再静默返回「已确认」。成功路径见 PG 用例。"""
    async def _s(client, ids, actor):
        return await client.post(f"/api/projects/{PID}/signoff/confirm-warning",
                                 json={"item_index": 1, "item_message": "x", "item_category": "stale"})

    resp = _api(_s)
    assert resp.status_code == 503 and "确认记录写入失败" in resp.text
