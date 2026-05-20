"""
test_f0_f2_confirmation_callback.py — F-F8 F0↔F2 函证反向回填集成测试

验证:
1. CW-176 (或新增的 F0→F2 反向回填条目) 存在于 cross_wp_references.json 且结构正确
2. EventType.CONFIRMATION_RECEIVED 存在于枚举（与 D 侧共享）
3. confirmation_service.apply_confirmation_result 通用化, 支持 wp_code="F0"
4. F0 函证回函时事件 payload 携带 wp_code="F0"
5. F0 触发的 stale 传播链路按 cross_wp_references 中 source_wp=F0 的条目下发

Spec: workpaper-f-purchase-inventory / Sprint 2 / Task 2.21
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CROSS_WP_REF_PATH = DATA_DIR / "cross_wp_references.json"


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def references() -> list[dict]:
    assert CROSS_WP_REF_PATH.exists(), (
        f"cross_wp_references.json not found at {CROSS_WP_REF_PATH}"
    )
    data = json.loads(CROSS_WP_REF_PATH.read_text(encoding="utf-8"))
    return data["references"]


@pytest.fixture(scope="module")
def f0_to_f2_reverse_entries(references) -> list[dict]:
    """所有 F0 → F2 且 category=data_flow_reverse 的条目"""
    return [
        r for r in references
        if r.get("source_wp") == "F0"
        and r.get("category") == "data_flow_reverse"
        and any(
            (t.get("wp_code") or "") == "F2"
            for t in r.get("targets", [])
        )
    ]


# ─── Test 1: F0→F2 反向回填条目存在且结构正确 ────────────────────────────────


class TestF0F2ReverseRefEntry:
    """验证 F0→F2 data_flow_reverse 条目存在于 cross_wp_references.json"""

    def test_at_least_one_reverse_entry(self, f0_to_f2_reverse_entries):
        """至少存在 1 条 F0→F2 反向回填条目"""
        assert len(f0_to_f2_reverse_entries) >= 1, (
            "F-F8 反向回填条目缺失: 需 ≥1 条 F0→F2 且 category=data_flow_reverse"
        )

    def test_source_sheet_contains_f0_1(self, f0_to_f2_reverse_entries):
        """source_sheet 应引用 F0-1 函证结果汇总表"""
        assert any(
            "F0-1" in (r.get("source_sheet") or "")
            for r in f0_to_f2_reverse_entries
        ), "至少需 1 条 source_sheet 含 'F0-1'"

    def test_target_sheet_references_f2(self, f0_to_f2_reverse_entries):
        """target sheet 应引用 F2 (审定表/明细表/...)"""
        for r in f0_to_f2_reverse_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "F2":
                    assert "F2" in (t.get("sheet") or ""), (
                        f"{r['ref_id']} F2 target sheet 不含 'F2': {t.get('sheet')}"
                    )

    def test_severity_warning(self, f0_to_f2_reverse_entries):
        """severity = warning (允许差异告警, 不阻断签字)"""
        for r in f0_to_f2_reverse_entries:
            assert r.get("severity") == "warning", (
                f"{r['ref_id']} severity 应为 warning, 实际为 {r.get('severity')}"
            )

    def test_trigger_field_present(self, f0_to_f2_reverse_entries):
        """trigger 字段应配置 eventBus confirmation:received"""
        for r in f0_to_f2_reverse_entries:
            trig = (r.get("trigger") or "").lower()
            assert "confirmation" in trig, (
                f"{r['ref_id']} trigger 字段缺失或不含 'confirmation': "
                f"{r.get('trigger')}"
            )

    def test_formula_uses_wp_syntax(self, f0_to_f2_reverse_entries):
        """target formula 使用 =WP('F0',...) 语法"""
        for r in f0_to_f2_reverse_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "F2":
                    assert t["formula"].startswith("=WP('F0'"), (
                        f"{r['ref_id']} formula 不是 =WP('F0',...): {t['formula']}"
                    )


# ─── Test 2: EventType.CONFIRMATION_RECEIVED 共享 ────────────────────────────


class TestConfirmationReceivedEventType:
    """F0 与 D0 共享同一事件类型 EventType.CONFIRMATION_RECEIVED"""

    def test_enum_member_exists(self):
        from app.models.audit_platform_schemas import EventType
        assert hasattr(EventType, "CONFIRMATION_RECEIVED")

    def test_enum_value(self):
        from app.models.audit_platform_schemas import EventType
        assert EventType.CONFIRMATION_RECEIVED.value == "confirmation.received"


# ─── Test 3: apply_confirmation_result 支持 wp_code 参数 ──────────────────────


class TestConfirmationServiceGeneric:
    """验证 apply_confirmation_result 已通用化, 支持 wp_code 参数."""

    def test_accepts_wp_code_kwarg(self):
        """signature 含 wp_code 参数"""
        import inspect
        from app.services.confirmation_service import apply_confirmation_result
        sig = inspect.signature(apply_confirmation_result)
        assert "wp_code" in sig.parameters, (
            "apply_confirmation_result 未通用化, 缺少 wp_code 参数"
        )

    def test_default_wp_code_is_d0(self):
        """默认 wp_code='D0' 保持向下兼容"""
        import inspect
        from app.services.confirmation_service import apply_confirmation_result
        sig = inspect.signature(apply_confirmation_result)
        param = sig.parameters["wp_code"]
        assert param.default == "D0"


# ─── Test 4: F0 函证调用触发事件 (集成) ─────────────────────────────────────


class TestF0ConfirmationEmitsEvent:
    """端到端: 调用 apply_confirmation_result(wp_code='F0') 触发
    EventType.CONFIRMATION_RECEIVED 事件, payload.extra.wp_code == 'F0'.
    """

    @pytest.mark.asyncio
    async def test_f0_emits_event_with_correct_wp_code(self, monkeypatch):
        from app.services.confirmation_service import apply_confirmation_result
        from app.services import event_bus as eb_module
        from app.models.audit_platform_schemas import EventType

        captured_events: list = []

        async def mock_publish(payload):
            captured_events.append(payload)

        monkeypatch.setattr(eb_module.event_bus, "publish_immediate", mock_publish)

        project_id = uuid4()
        confirmation_id = uuid4()
        result = await apply_confirmation_result(
            project_id=project_id,
            year=2026,
            confirmation_id=confirmation_id,
            reply_status="confirmed_match",
            reply_amount=2_500_000.0,
            wp_code="F0",
        )

        # 返回值含 wp_code
        assert result["wp_code"] == "F0"
        assert result["applied"] is True

        # 触发了 1 条 CONFIRMATION_RECEIVED 事件
        assert len(captured_events) == 1
        evt = captured_events[0]
        assert evt.event_type == EventType.CONFIRMATION_RECEIVED
        assert evt.project_id == project_id
        assert evt.year == 2026
        # 关键: extra.wp_code == "F0" (用于下游 stale 传播按 source_wp 路由)
        assert evt.extra["wp_code"] == "F0"
        assert evt.extra["confirmation_id"] == str(confirmation_id)

    @pytest.mark.asyncio
    async def test_d0_default_still_works(self, monkeypatch):
        """向下兼容: 不传 wp_code 时默认走 D0 路径"""
        from app.services.confirmation_service import apply_confirmation_result
        from app.services import event_bus as eb_module

        captured_events: list = []

        async def mock_publish(payload):
            captured_events.append(payload)

        monkeypatch.setattr(eb_module.event_bus, "publish_immediate", mock_publish)

        await apply_confirmation_result(
            project_id=uuid4(),
            year=2026,
            confirmation_id=uuid4(),
        )

        assert len(captured_events) == 1
        assert captured_events[0].extra["wp_code"] == "D0"


# ─── Test 5: F0 stale 下游链路 (cross_wp_references 路由验证) ────────────────


class TestF0StalePropagationRoutes:
    """验证 cross_wp_references 中 source_wp=F0 的条目可作为 stale 传播路由源.
    stale_engine 的实际订阅由 LinkageGraphBuilder 处理,本测试仅验证数据完整性.
    """

    def test_f0_source_entries_exist(self, references):
        """source_wp=F0 的条目 ≥ 1 条 (含反向回填 + F0 内部联动)"""
        f0_sources = [
            r for r in references if r.get("source_wp") == "F0"
        ]
        assert len(f0_sources) >= 1, (
            "source_wp=F0 的 cross_wp_references 条目缺失"
        )

    def test_f0_to_f2_target_exists(self, references):
        """source_wp=F0 且 target wp_code=F2 ≥ 1 条 (反向回填路径)"""
        f0_to_f2 = [
            r for r in references
            if r.get("source_wp") == "F0"
            and any(
                (t.get("wp_code") or "") == "F2"
                for t in r.get("targets", [])
            )
        ]
        assert len(f0_to_f2) >= 1, (
            "F0→F2 cross_wp_references 路由缺失,F0 函证回函无法传播 stale 至 F2"
        )

    def test_total_references_at_least_210(self, references):
        """总条目 ≥ 210 (含 175 baseline + 35 F-cycle 新增)"""
        assert len(references) >= 210, (
            f"Expected ≥210 total references, got {len(references)}"
        )
