"""
test_d2_d0_confirmation_callback.py — F6 D2↔D0 函证双向回填集成测试

验证:
1. CW-136 存在于 cross_wp_references.json 且结构正确
2. EventType.CONFIRMATION_RECEIVED 存在于枚举
3. confirmation_service.apply_confirmation_result 包含事件 emit 调用

Spec: workpaper-d-sales-cycle / Sprint 2 / F6 task 2.13
"""
import json
from pathlib import Path
from uuid import uuid4

import pytest

# ─── 路径常量 ─────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CROSS_WP_REF_PATH = DATA_DIR / "cross_wp_references.json"


# ─── Test 1: CW-136 存在且结构正确 ──────────────────────────────────────────

class TestCW136Exists:
    """验证 CW-136 在 cross_wp_references.json 中存在且字段完整"""

    @pytest.fixture(scope="class")
    def references(self) -> list[dict]:
        assert CROSS_WP_REF_PATH.exists(), f"cross_wp_references.json not found at {CROSS_WP_REF_PATH}"
        data = json.loads(CROSS_WP_REF_PATH.read_text(encoding="utf-8"))
        return data["references"]

    def test_cw136_exists(self, references: list[dict]):
        """CW-136 条目存在"""
        ref_ids = [r["ref_id"] for r in references]
        assert "CW-136" in ref_ids, "CW-136 not found in cross_wp_references.json"

    def test_cw136_source_wp(self, references: list[dict]):
        """CW-136 source_wp = D0"""
        entry = next(r for r in references if r["ref_id"] == "CW-136")
        assert entry["source_wp"] == "D0"

    def test_cw136_target_wp_code(self, references: list[dict]):
        """CW-136 target wp_code = D2"""
        entry = next(r for r in references if r["ref_id"] == "CW-136")
        assert len(entry["targets"]) >= 1
        assert entry["targets"][0]["wp_code"] == "D2"

    def test_cw136_category(self, references: list[dict]):
        """CW-136 category = data_flow_reverse"""
        entry = next(r for r in references if r["ref_id"] == "CW-136")
        assert entry["category"] == "data_flow_reverse"

    def test_cw136_severity(self, references: list[dict]):
        """CW-136 severity = warning"""
        entry = next(r for r in references if r["ref_id"] == "CW-136")
        assert entry["severity"] == "warning"

    def test_cw136_source_sheet(self, references: list[dict]):
        """CW-136 source_sheet 包含 D0-1"""
        entry = next(r for r in references if r["ref_id"] == "CW-136")
        assert "D0-1" in entry["source_sheet"]

    def test_cw136_target_sheet(self, references: list[dict]):
        """CW-136 target sheet 包含 D2-1"""
        entry = next(r for r in references if r["ref_id"] == "CW-136")
        assert "D2-1" in entry["targets"][0]["sheet"]

    def test_cw136_formula(self, references: list[dict]):
        """CW-136 target formula 使用 =WP('D0',...) 语法"""
        entry = next(r for r in references if r["ref_id"] == "CW-136")
        formula = entry["targets"][0]["formula"]
        assert formula.startswith("=WP('D0'")

    def test_total_references_updated(self, references: list[dict]):
        """总条目数 >= 136"""
        assert len(references) >= 136


# ─── Test 2: EventType.CONFIRMATION_RECEIVED 存在 ────────────────────────────

class TestConfirmationReceivedEventType:
    """验证 EventType 枚举包含 CONFIRMATION_RECEIVED"""

    def test_enum_member_exists(self):
        from app.models.audit_platform_schemas import EventType
        assert hasattr(EventType, "CONFIRMATION_RECEIVED")

    def test_enum_value(self):
        from app.models.audit_platform_schemas import EventType
        assert EventType.CONFIRMATION_RECEIVED.value == "confirmation.received"


# ─── Test 3: confirmation_service emit 调用 ───────────────────────────────────

class TestConfirmationServiceEmit:
    """验证 confirmation_service.apply_confirmation_result 包含事件 emit"""

    def test_service_module_importable(self):
        """confirmation_service 模块可导入"""
        from app.services import confirmation_service  # noqa: F401

    def test_apply_confirmation_result_exists(self):
        """apply_confirmation_result 函数存在"""
        from app.services.confirmation_service import apply_confirmation_result
        assert callable(apply_confirmation_result)

    def test_source_contains_event_emit(self):
        """源码包含 CONFIRMATION_RECEIVED 事件发布"""
        import inspect
        from app.services.confirmation_service import apply_confirmation_result
        source = inspect.getsource(apply_confirmation_result)
        assert "CONFIRMATION_RECEIVED" in source
        assert "publish_immediate" in source

    @pytest.mark.asyncio
    async def test_apply_emits_event(self, monkeypatch):
        """调用 apply_confirmation_result 后确实触发 CONFIRMATION_RECEIVED 事件"""
        from app.services.confirmation_service import apply_confirmation_result
        from app.services import event_bus as eb_module
        from app.models.audit_platform_schemas import EventType

        captured_events: list = []

        async def mock_publish(payload):
            captured_events.append(payload)

        monkeypatch.setattr(eb_module.event_bus, "publish_immediate", mock_publish)

        project_id = uuid4()
        confirmation_id = uuid4()
        await apply_confirmation_result(
            project_id=project_id,
            year=2026,
            confirmation_id=confirmation_id,
            reply_status="confirmed_match",
            reply_amount=100000.0,
        )

        assert len(captured_events) == 1
        evt = captured_events[0]
        assert evt.event_type == EventType.CONFIRMATION_RECEIVED
        assert evt.project_id == project_id
        assert evt.year == 2026
        assert evt.extra["wp_code"] == "D0"
        assert evt.extra["confirmation_id"] == str(confirmation_id)
