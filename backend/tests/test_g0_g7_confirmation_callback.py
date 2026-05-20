"""
test_g0_g7_confirmation_callback.py — G-F8 G0↔G7 函证反向回填集成测试

验证:
1. G0→G7 反向回填条目（CW-267）存在于 cross_wp_references.json 且结构正确
2. EventType.CONFIRMATION_RECEIVED 存在于枚举（与 D0/F0 共享）
3. confirmation_service.apply_confirmation_result 支持 wp_code="G0"
4. G0 函证回函时事件 payload 携带 wp_code="G0"
5. G0 触发的 stale 传播链路按 cross_wp_references 中 source_wp=G0 的条目下发

Spec: workpaper-g-investment-cycle / Sprint 2 / Task 2.22
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
def g0_to_g7_reverse_entries(references) -> list[dict]:
    """所有 G0 → G7 且 category=data_flow_reverse 的条目"""
    return [
        r for r in references
        if r.get("source_wp") == "G0"
        and r.get("category") == "data_flow_reverse"
        and any(
            (t.get("wp_code") or "") == "G7"
            for t in r.get("targets", [])
        )
    ]


# ─── Test 1: G0→G7 反向回填条目存在且结构正确 ────────────────────────────────


class TestG0G7ReverseRefEntry:
    """验证 G0→G7 data_flow_reverse 条目存在于 cross_wp_references.json"""

    def test_at_least_one_reverse_entry(self, g0_to_g7_reverse_entries):
        """至少存在 1 条 G0→G7 反向回填条目"""
        assert len(g0_to_g7_reverse_entries) >= 1, (
            "G-F8 反向回填条目缺失: 需 ≥1 条 G0→G7 且 category=data_flow_reverse"
        )

    def test_source_sheet_references_g0(self, g0_to_g7_reverse_entries):
        """source_sheet 应引用 G0 函证表（如 G0-1 函证结果汇总表）"""
        assert any(
            "G0" in (r.get("source_sheet") or "")
            for r in g0_to_g7_reverse_entries
        ), "至少需 1 条 source_sheet 含 'G0'"

    def test_target_sheet_references_g7(self, g0_to_g7_reverse_entries):
        """target sheet 应引用 G7 (审定表/明细表/...)"""
        for r in g0_to_g7_reverse_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "G7":
                    assert "G7" in (t.get("sheet") or ""), (
                        f"{r['ref_id']} G7 target sheet 不含 'G7': {t.get('sheet')}"
                    )

    def test_severity_warning(self, g0_to_g7_reverse_entries):
        """severity = warning (允许差异告警, 不阻断签字)"""
        for r in g0_to_g7_reverse_entries:
            assert r.get("severity") == "warning", (
                f"{r['ref_id']} severity 应为 warning, 实际为 {r.get('severity')}"
            )

    def test_trigger_field_present(self, g0_to_g7_reverse_entries):
        """trigger 字段应配置 workpaper:saved:G0 或 confirmation:received"""
        for r in g0_to_g7_reverse_entries:
            trig = (r.get("trigger") or "").lower()
            assert "g0" in trig or "confirmation" in trig, (
                f"{r['ref_id']} trigger 字段缺失或格式不符: {r.get('trigger')}"
            )

    def test_formula_uses_wp_syntax(self, g0_to_g7_reverse_entries):
        """target formula 使用 =WP('G0',...) 语法"""
        for r in g0_to_g7_reverse_entries:
            for t in r["targets"]:
                if (t.get("wp_code") or "") == "G7":
                    formula = t.get("formula") or ""
                    assert formula.startswith("=WP('G0'"), (
                        f"{r['ref_id']} formula 不是 =WP('G0',...): {formula}"
                    )


# ─── Test 2: EventType.CONFIRMATION_RECEIVED 共享 ────────────────────────────


class TestConfirmationReceivedEventType:
    """G0 与 D0/F0 共享同一事件类型 EventType.CONFIRMATION_RECEIVED"""

    def test_enum_member_exists(self):
        from app.models.audit_platform_schemas import EventType
        assert hasattr(EventType, "CONFIRMATION_RECEIVED")

    def test_enum_value(self):
        from app.models.audit_platform_schemas import EventType
        assert EventType.CONFIRMATION_RECEIVED.value == "confirmation.received"


# ─── Test 3: apply_confirmation_result 支持 wp_code="G0" ──────────────────────


class TestConfirmationServiceSupportsG0:
    """验证 apply_confirmation_result 已通用化, 支持 wp_code='G0'."""

    def test_accepts_wp_code_kwarg(self):
        import inspect
        from app.services.confirmation_service import apply_confirmation_result
        sig = inspect.signature(apply_confirmation_result)
        assert "wp_code" in sig.parameters, (
            "apply_confirmation_result 未通用化, 缺少 wp_code 参数"
        )

    def test_docstring_mentions_g0(self):
        """docstring 应注明支持 G0 函证（按本任务约定追加）"""
        from app.services.confirmation_service import apply_confirmation_result
        doc = (apply_confirmation_result.__doc__ or "")
        assert "G0" in doc, "docstring 应注明支持 G0 函证 wp_code"


# ─── Test 4: G0 函证调用触发事件 (集成) ─────────────────────────────────────


class TestG0ConfirmationEmitsEvent:
    """端到端: 调用 apply_confirmation_result(wp_code='G0') 触发
    EventType.CONFIRMATION_RECEIVED 事件, payload.extra.wp_code == 'G0'.
    """

    @pytest.mark.asyncio
    async def test_g0_emits_event_with_correct_wp_code(self, monkeypatch):
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
            reply_amount=12_345_678.90,
            wp_code="G0",
        )

        # 返回值含 wp_code
        assert result["wp_code"] == "G0"
        assert result["applied"] is True

        # 触发了 1 条 CONFIRMATION_RECEIVED 事件
        assert len(captured_events) == 1
        evt = captured_events[0]
        assert evt.event_type == EventType.CONFIRMATION_RECEIVED
        assert evt.project_id == project_id
        assert evt.year == 2026
        # 关键: extra.wp_code == "G0" (用于下游 stale 传播按 source_wp 路由)
        assert evt.extra["wp_code"] == "G0"
        assert evt.extra["confirmation_id"] == str(confirmation_id)

    @pytest.mark.asyncio
    async def test_g0_alongside_d0_f0_no_collision(self, monkeypatch):
        """G0 / D0 / F0 三方调用互不影响 — payload.extra.wp_code 各自正确"""
        from app.services.confirmation_service import apply_confirmation_result
        from app.services import event_bus as eb_module

        captured_events: list = []

        async def mock_publish(payload):
            captured_events.append(payload)

        monkeypatch.setattr(eb_module.event_bus, "publish_immediate", mock_publish)

        for wp in ("D0", "F0", "G0"):
            await apply_confirmation_result(
                project_id=uuid4(),
                year=2026,
                confirmation_id=uuid4(),
                wp_code=wp,
            )

        wp_codes_seen = [evt.extra["wp_code"] for evt in captured_events]
        assert wp_codes_seen == ["D0", "F0", "G0"], (
            f"3 wp_code 顺序错误: {wp_codes_seen}"
        )


# ─── Test 5: G0 stale 下游链路 (cross_wp_references 路由验证) ────────────────


class TestG0StalePropagationRoutes:
    """验证 cross_wp_references 中 source_wp=G0 的条目可作为 stale 传播路由源.
    stale_engine 的实际订阅由 LinkageGraphBuilder 处理,本测试仅验证数据完整性.
    """

    def test_g0_source_entries_exist(self, references):
        """source_wp=G0 的条目 ≥ 1 条 (反向回填路径)"""
        g0_sources = [
            r for r in references if r.get("source_wp") == "G0"
        ]
        assert len(g0_sources) >= 1, (
            "source_wp=G0 的 cross_wp_references 条目缺失"
        )

    def test_g0_to_g7_target_exists(self, references):
        """source_wp=G0 且 target wp_code=G7 ≥ 1 条 (反向回填路径)"""
        g0_to_g7 = [
            r for r in references
            if r.get("source_wp") == "G0"
            and any(
                (t.get("wp_code") or "") == "G7"
                for t in r.get("targets", [])
            )
        ]
        assert len(g0_to_g7) >= 1, (
            "G0→G7 cross_wp_references 路由缺失,G0 函证回函无法传播 stale 至 G7"
        )

    def test_total_references_count(self, references):
        """总条目 ≥ 292 (含 G-cycle 新增 26 条 CW-267~292)"""
        assert len(references) >= 292, (
            f"Expected ≥292 total references, got {len(references)}"
        )
