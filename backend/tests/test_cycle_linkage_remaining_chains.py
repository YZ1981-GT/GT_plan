"""集成测试 — 补齐 3 条此前无运行时验证的联动链。

覆盖对象（均为"代码存在但缺运行时实测"的 handler）：
  1. _on_c_deviation_saved   (C{n}-2 偏差评价 → IssueTicket + 控制结论覆写)
  2. _on_c22_itgc_saved      (C22 ITGC → C21-1 findings)
  3. _on_b50_saved           (B50-3 风险评估 → risk_assessment override，闭包，
                              经全局 event_bus 注册表取出后直调)

验证方式：mock async_session_factory + 捕获 FieldOverrideService.set / session.add，
构造真实 EventPayload 调用 handler，断言真实写入行为（非 mock 不存在的方法）。
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType


# ---------------------------------------------------------------------------
# 捕获型 mock：session（支持 add/commit/rollback）+ FieldOverrideService.set
# ---------------------------------------------------------------------------


class _CapturingSession:
    def __init__(self):
        self.added: list = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, *a, **k):
        result = MagicMock()
        result.rowcount = 1
        return result

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class _CapturingFieldOverrideService:
    def __init__(self):
        self.calls: list[dict] = []

    async def set(self, **kwargs):
        self.calls.append(kwargs)


@pytest.fixture
def sample_project_id():
    return uuid.uuid4()


@pytest.fixture
def cap_svc():
    return _CapturingFieldOverrideService()


@pytest.fixture
def cap_session():
    return _CapturingSession()


def _patch_linkage(monkeypatch, cap_session, cap_svc):
    """Patch cycle_linkage 模块的 session factory / FieldOverrideService / cache."""

    @asynccontextmanager
    async def _fake_factory(*a, **k):
        yield cap_session

    monkeypatch.setattr(
        "app.services.event_handlers_cycle_linkage.async_session_factory",
        _fake_factory,
    )
    monkeypatch.setattr(
        "app.services.field_override_service.FieldOverrideService",
        lambda session: cap_svc,
    )
    monkeypatch.setattr(
        "app.services.event_handlers_cycle_linkage.invalidate_auto_cache",
        MagicMock(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 链 1：C偏差 → IssueTicket + 控制结论覆写
# ═══════════════════════════════════════════════════════════════════════════


class TestOnCDeviationSaved:
    @pytest.mark.asyncio
    async def test_deficiency_row_creates_issue_ticket(
        self, monkeypatch, cap_session, cap_svc, sample_project_id
    ):
        """step7='是' 的行 → session.add(IssueTicket) 真实被调用."""
        _patch_linkage(monkeypatch, cap_session, cap_svc)
        from app.services.event_handlers_cycle_linkage import _on_c_deviation_saved
        from app.models.phase15_models import IssueTicket

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "C2-2",
                "parsed_data": {
                    "rows": [
                        {"step7_report_deficiency": "是", "control_name": "审批控制",
                         "deviation_description": "缺审批"},
                        {"step7_report_deficiency": "否", "control_name": "复核控制"},
                    ]
                },
            },
        )
        await _on_c_deviation_saved(payload)

        # 仅第 1 行创建工单
        assert len(cap_session.added) == 1
        assert isinstance(cap_session.added[0], IssueTicket)
        assert cap_session.added[0].category == "control_deficiency"
        assert cap_session.committed is True

    @pytest.mark.asyncio
    async def test_invalid_conclusion_overrides_parent(
        self, monkeypatch, cap_session, cap_svc, sample_project_id
    ):
        """deviation_conclusion='无效且已放弃信赖' → 覆写父底稿 C2 结论为'无效'."""
        _patch_linkage(monkeypatch, cap_session, cap_svc)
        from app.services.event_handlers_cycle_linkage import _on_c_deviation_saved

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "C2-2",
                "parsed_data": {
                    "rows": [
                        {"conclusion": "无效且已放弃信赖"},
                    ]
                },
            },
        )
        await _on_c_deviation_saved(payload)

        # 两次 set：deviation_conclusion(C2-2) + conclusion(父 C2)
        assert len(cap_svc.calls) == 2
        scopes = {c["scope"] for c in cap_svc.calls}
        assert scopes == {"control_test_result:销售收入"}
        parent_call = next(c for c in cap_svc.calls if c["item_key"] == "C2")
        assert parent_call["field"] == "conclusion"
        assert parent_call["value"] == "无效"
        assert cap_session.committed is True

    @pytest.mark.asyncio
    async def test_invalid_wp_code_skips(
        self, monkeypatch, cap_session, cap_svc, sample_project_id
    ):
        """非 C{n}-2（n=2~15）→ 直接 return，无任何写入."""
        _patch_linkage(monkeypatch, cap_session, cap_svc)
        from app.services.event_handlers_cycle_linkage import _on_c_deviation_saved

        for wp_code in ["C1-2", "C16-2", "C2", "C2-1", "D1-2"]:
            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=sample_project_id,
                year=2025,
                extra={"wp_code": wp_code,
                       "parsed_data": {"rows": [{"step7_report_deficiency": "是"}]}},
            )
            await _on_c_deviation_saved(payload)

        assert len(cap_session.added) == 0
        assert len(cap_svc.calls) == 0
        assert cap_session.committed is False


# ═══════════════════════════════════════════════════════════════════════════
# 链 2：C22 ITGC → C21-1 findings
# ═══════════════════════════════════════════════════════════════════════════


class TestOnC22ItgcSaved:
    @pytest.mark.asyncio
    async def test_invalid_steps_write_findings(
        self, monkeypatch, cap_session, cap_svc, sample_project_id
    ):
        """C22 步骤结论='无效' → 写入 c21_1_findings（每 finding 4 字段）."""
        _patch_linkage(monkeypatch, cap_session, cap_svc)
        from app.services.event_handlers_cycle_linkage import _on_c22_itgc_saved

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "C22",
                "parsed_data": {
                    "steps": [
                        {"name": "访问控制", "domain": "安全", "conclusion": "无效"},
                        {"name": "变更管理", "domain": "变更", "conclusion": "有效"},
                    ]
                },
            },
        )
        await _on_c22_itgc_saved(payload)

        # 1 个无效步骤 × 4 字段(source/step/domain/conclusion)
        assert len(cap_svc.calls) == 4
        assert all(c["scope"] == "c21_1_findings" for c in cap_svc.calls)
        fields = {c["field"]: c["value"] for c in cap_svc.calls}
        assert fields["source"] == "C22"
        assert fields["step"] == "访问控制"
        assert fields["conclusion"] == "无效"
        assert cap_session.committed is True

    @pytest.mark.asyncio
    async def test_dict_conclusions_form(
        self, monkeypatch, cap_session, cap_svc, sample_project_id
    ):
        """step_conclusions 为 dict 形式同样支持."""
        _patch_linkage(monkeypatch, cap_session, cap_svc)
        from app.services.event_handlers_cycle_linkage import _on_c22_itgc_saved

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={
                "wp_code": "C22",
                "parsed_data": {
                    "step_conclusions": {"访问控制": "无效", "变更管理": "有效"}
                },
            },
        )
        await _on_c22_itgc_saved(payload)

        # 1 无效步骤 × 4 字段
        assert len(cap_svc.calls) == 4
        assert cap_session.committed is True

    @pytest.mark.asyncio
    async def test_all_effective_no_write(
        self, monkeypatch, cap_session, cap_svc, sample_project_id
    ):
        """全部步骤有效 → 无 findings，不写入."""
        _patch_linkage(monkeypatch, cap_session, cap_svc)
        from app.services.event_handlers_cycle_linkage import _on_c22_itgc_saved

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={"wp_code": "C22",
                   "parsed_data": {"steps": [{"name": "x", "conclusion": "有效"}]}},
        )
        await _on_c22_itgc_saved(payload)
        assert len(cap_svc.calls) == 0

    @pytest.mark.asyncio
    async def test_non_c22_skips(
        self, monkeypatch, cap_session, cap_svc, sample_project_id
    ):
        """wp_code != C22 → 直接 return."""
        _patch_linkage(monkeypatch, cap_session, cap_svc)
        from app.services.event_handlers_cycle_linkage import _on_c22_itgc_saved

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={"wp_code": "C21",
                   "parsed_data": {"steps": [{"name": "x", "conclusion": "无效"}]}},
        )
        await _on_c22_itgc_saved(payload)
        assert len(cap_svc.calls) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 链 3：B50-3 风险评估 → risk_assessment override（闭包，经全局总线取出）
# ═══════════════════════════════════════════════════════════════════════════


def _get_b50_handler():
    """注册事件 handlers 后，从全局 event_bus 取出 _on_b50_saved 闭包。

    既验证「已注册」也供直调验证运行时行为。
    """
    from app.services.event_handlers import register_event_handlers
    from app.services.event_bus import event_bus

    register_event_handlers()
    handlers = event_bus._handlers.get(EventType.WORKPAPER_SAVED, [])
    for h in handlers:
        if "_on_b50_saved" in getattr(h, "__qualname__", ""):
            return h
    return None


class TestOnB50Saved:
    @pytest.mark.asyncio
    async def test_b50_handler_registered(self):
        """B50 handler 真实注册到 WORKPAPER_SAVED（非仅 import 验证）."""
        assert _get_b50_handler() is not None

    @pytest.mark.asyncio
    async def test_b50_invalidates_auto_cache(self, sample_project_id):
        """B50 保存（wp_code='B50'）→ 失效本项目 auto_data 缓存，使 D~N 立即反映。

        新架构：认定层次风险单一真源是 checklist_responses（B50-T3-*），下游经
        b50_risk_reader 直接读取，此 handler 仅负责失效 auto_data 缓存。
        """
        handler = _get_b50_handler()
        assert handler is not None

        from app.services import procedure_table_auto_service as pts

        # 预置一条本项目缓存
        pts._set_cached(sample_project_id, 2025, "risk_for_cycle", {"summary": "旧值"})
        assert pts._get_cached(sample_project_id, 2025, "risk_for_cycle") is not None

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={"wp_code": "B50", "trigger": "checklist_response_save"},
        )
        await handler(payload)

        # 缓存已失效
        assert pts._get_cached(sample_project_id, 2025, "risk_for_cycle") is None

    @pytest.mark.asyncio
    async def test_b50_ignores_other_wp_code(self, sample_project_id):
        """非 B50 的 WORKPAPER_SAVED（如 B50-3 旧编码/其它底稿）→ 不失效缓存（no-op）."""
        handler = _get_b50_handler()
        assert handler is not None

        from app.services import procedure_table_auto_service as pts

        pts._set_cached(sample_project_id, 2025, "risk_for_cycle", {"summary": "保留"})

        payload = EventPayload(
            event_type=EventType.WORKPAPER_SAVED,
            project_id=sample_project_id,
            year=2025,
            extra={"wp_code": "B50-3"},
        )
        await handler(payload)

        # 非 B50 → 缓存保留
        assert pts._get_cached(sample_project_id, 2025, "risk_for_cycle") is not None
        # 清理
        pts.invalidate_auto_cache(sample_project_id, 2025)
