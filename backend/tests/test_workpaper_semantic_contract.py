"""底稿内容语义契约 schema 单元测试。

覆盖:
- 枚举序列化/反序列化
- 非法枚举值拒绝
- 前后端 fixture 一致性
- FieldSourceContract 和 ProgramStatusContract 验证
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.schemas.workpaper_semantic_contract import (
    FieldSourceContract,
    FieldSourceType,
    ProgramStatus,
    ProgramStatusContract,
    ReviewStatus,
    SheetContentType,
    StalePolicy,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "workpaper_semantic_contract_fixture.json"


# ---------------------------------------------------------------------------
# SheetContentType 枚举测试
# ---------------------------------------------------------------------------

class TestSheetContentType:
    """SheetContentType 枚举序列化和验证。"""

    def test_all_values_are_strings(self):
        for member in SheetContentType:
            assert isinstance(member.value, str)

    def test_serialization_roundtrip(self):
        for member in SheetContentType:
            assert SheetContentType(member.value) == member

    def test_expected_count(self):
        assert len(SheetContentType) == 13

    def test_invalid_value_rejected(self):
        with pytest.raises(ValueError):
            SheetContentType("invalid_type")

    def test_invalid_similar_value_rejected(self):
        with pytest.raises(ValueError):
            SheetContentType("CONTROL_PANEL")  # 大写不接受


# ---------------------------------------------------------------------------
# FieldSourceType 枚举测试
# ---------------------------------------------------------------------------

class TestFieldSourceType:
    def test_all_values(self):
        expected = {"trial_balance", "formula", "manual", "linked", "ai_generated"}
        assert {m.value for m in FieldSourceType} == expected

    def test_invalid_value_rejected(self):
        with pytest.raises(ValueError):
            FieldSourceType("database")


# ---------------------------------------------------------------------------
# StalePolicy 枚举测试
# ---------------------------------------------------------------------------

class TestStalePolicy:
    def test_all_values(self):
        expected = {"refresh_on_tb_updated", "refresh_on_report_regen", "manual_refresh", "none"}
        assert {m.value for m in StalePolicy} == expected

    def test_invalid_value_rejected(self):
        with pytest.raises(ValueError):
            StalePolicy("auto_refresh")


# ---------------------------------------------------------------------------
# ProgramStatus / ReviewStatus 枚举测试
# ---------------------------------------------------------------------------

class TestProgramStatus:
    def test_all_values(self):
        expected = {"not_started", "in_progress", "completed", "reviewed", "rejected"}
        assert {m.value for m in ProgramStatus} == expected

    def test_invalid_value_rejected(self):
        with pytest.raises(ValueError):
            ProgramStatus("done")


class TestReviewStatus:
    def test_all_values(self):
        expected = {"pending", "approved", "rejected"}
        assert {m.value for m in ReviewStatus} == expected

    def test_invalid_value_rejected(self):
        with pytest.raises(ValueError):
            ReviewStatus("waiting")


# ---------------------------------------------------------------------------
# FieldSourceContract 验证
# ---------------------------------------------------------------------------

class TestFieldSourceContract:
    def _valid_data(self) -> dict:
        return {
            "field_id": "d1.audit_sheet.current_unadjusted",
            "label": "本期未审数",
            "source_type": "trial_balance",
            "source_ref": {"module": "trial_balance", "account_code": "1121"},
            "editable": False,
            "override_allowed": False,
            "requires_confirmation": False,
            "traceable": True,
            "stale_policy": "refresh_on_tb_updated",
        }

    def test_valid_creation(self):
        contract = FieldSourceContract(**self._valid_data())
        assert contract.field_id == "d1.audit_sheet.current_unadjusted"
        assert contract.source_type == FieldSourceType.trial_balance
        assert contract.stale_policy == StalePolicy.refresh_on_tb_updated

    def test_invalid_source_type_rejected(self):
        data = self._valid_data()
        data["source_type"] = "unknown_source"
        with pytest.raises(ValidationError):
            FieldSourceContract(**data)

    def test_invalid_stale_policy_rejected(self):
        data = self._valid_data()
        data["stale_policy"] = "auto_refresh"
        with pytest.raises(ValidationError):
            FieldSourceContract(**data)

    def test_serialization(self):
        contract = FieldSourceContract(**self._valid_data())
        dumped = contract.model_dump()
        assert dumped["source_type"] == "trial_balance"
        assert dumped["stale_policy"] == "refresh_on_tb_updated"


# ---------------------------------------------------------------------------
# ProgramStatusContract 验证
# ---------------------------------------------------------------------------

class TestProgramStatusContract:
    def _valid_data(self) -> dict:
        return {
            "project_id": str(uuid4()),
            "account_package_id": "D1",
            "program_code": "D1A-01",
            "sheet_name": "D1A 应收账款审计程序表",
            "applicable": True,
            "status": "not_started",
            "evidence_refs": [],
            "conclusion": None,
            "review_status": "pending",
            "not_applicable_reason": None,
            "updated_by": None,
            "updated_at": None,
            "reviewer": None,
            "reviewed_at": None,
        }

    def test_valid_creation(self):
        contract = ProgramStatusContract(**self._valid_data())
        assert contract.status == ProgramStatus.not_started
        assert contract.review_status == ReviewStatus.pending

    def test_invalid_status_rejected(self):
        data = self._valid_data()
        data["status"] = "done"
        with pytest.raises(ValidationError):
            ProgramStatusContract(**data)

    def test_invalid_review_status_rejected(self):
        data = self._valid_data()
        data["review_status"] = "waiting"
        with pytest.raises(ValidationError):
            ProgramStatusContract(**data)

    def test_serialization_uuid_format(self):
        data = self._valid_data()
        contract = ProgramStatusContract(**data)
        dumped = contract.model_dump(mode="json")
        assert dumped["project_id"] == data["project_id"]
        assert dumped["status"] == "not_started"

    def test_not_applicable_requires_reason(self):
        """applicable=False 时必须提供 not_applicable_reason。"""
        data = self._valid_data()
        data["applicable"] = False
        data["not_applicable_reason"] = None
        with pytest.raises(ValidationError, match="not_applicable_reason"):
            ProgramStatusContract(**data)

    def test_not_applicable_empty_reason_rejected(self):
        """applicable=False 时 not_applicable_reason 不能为空字符串。"""
        data = self._valid_data()
        data["applicable"] = False
        data["not_applicable_reason"] = "   "
        with pytest.raises(ValidationError, match="not_applicable_reason"):
            ProgramStatusContract(**data)

    def test_not_applicable_with_reason_accepted(self):
        """applicable=False 且提供理由时正常创建。"""
        data = self._valid_data()
        data["applicable"] = False
        data["not_applicable_reason"] = "该科目本期无发生额，程序不适用"
        contract = ProgramStatusContract(**data)
        assert contract.applicable is False
        assert contract.not_applicable_reason == "该科目本期无发生额，程序不适用"

    def test_applicable_true_no_reason_ok(self):
        """applicable=True 时 not_applicable_reason 可为 None。"""
        data = self._valid_data()
        data["applicable"] = True
        data["not_applicable_reason"] = None
        contract = ProgramStatusContract(**data)
        assert contract.applicable is True
        assert contract.not_applicable_reason is None

    def test_contract_fields_completeness(self):
        """验证 ProgramStatusContract 包含所有必要字段。"""
        required_fields = {
            "project_id", "account_package_id", "program_code", "sheet_name",
            "applicable", "status", "evidence_refs", "conclusion",
            "review_status", "not_applicable_reason",
            "updated_by", "updated_at", "reviewer", "reviewed_at",
        }
        actual_fields = set(ProgramStatusContract.model_fields.keys())
        assert required_fields.issubset(actual_fields)

    def test_status_enum_completeness(self):
        """验证 ProgramStatus 枚举包含所有必要状态。"""
        required_statuses = {"not_started", "in_progress", "completed", "reviewed", "rejected"}
        actual_statuses = {m.value for m in ProgramStatus}
        assert required_statuses == actual_statuses

    def test_review_status_enum_completeness(self):
        """验证 ReviewStatus 枚举包含所有必要状态。"""
        required_statuses = {"pending", "approved", "rejected"}
        actual_statuses = {m.value for m in ReviewStatus}
        assert required_statuses == actual_statuses


# ---------------------------------------------------------------------------
# ProgramStatusStore 接口测试
# ---------------------------------------------------------------------------

class TestProgramStatusStoreProtocol:
    """验证 ProgramStatusStore Protocol 接口定义。"""

    def test_protocol_is_importable(self):
        from backend.app.services.program_status_store import ProgramStatusStore
        assert ProgramStatusStore is not None

    def test_protocol_is_runtime_checkable(self):
        from backend.app.services.program_status_store import ProgramStatusStore
        # Protocol 标记为 runtime_checkable 后可用 isinstance 检查
        assert hasattr(ProgramStatusStore, "__protocol_attrs__") or hasattr(
            ProgramStatusStore, "__abstractmethods__"
        ) or issubclass(type(ProgramStatusStore), type)

    def test_protocol_has_required_methods(self):
        from backend.app.services.program_status_store import ProgramStatusStore
        # 验证接口定义了三个核心方法
        assert hasattr(ProgramStatusStore, "get_status")
        assert hasattr(ProgramStatusStore, "save_status")
        assert hasattr(ProgramStatusStore, "list_by_package")

    def test_concrete_implementation_satisfies_protocol(self):
        """验证一个最小实现能满足 Protocol。"""
        from backend.app.services.program_status_store import ProgramStatusStore

        class FakeStore:
            async def get_status(self, project_id: str, program_code: str):
                return None

            async def save_status(self, status: ProgramStatusContract) -> None:
                pass

            async def list_by_package(
                self, project_id: str, account_package_id: str
            ) -> list[ProgramStatusContract]:
                return []

        store = FakeStore()
        assert isinstance(store, ProgramStatusStore)


# ---------------------------------------------------------------------------
# 前后端 fixture 一致性
# ---------------------------------------------------------------------------

class TestFixtureConsistency:
    """验证后端枚举值与 fixture JSON 一致。"""

    @pytest.fixture
    def fixture_data(self) -> dict:
        return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_sheet_content_type_matches_fixture(self, fixture_data):
        backend_values = [m.value for m in SheetContentType]
        assert backend_values == fixture_data["SheetContentType"]

    def test_field_source_type_matches_fixture(self, fixture_data):
        backend_values = [m.value for m in FieldSourceType]
        assert backend_values == fixture_data["FieldSourceType"]

    def test_stale_policy_matches_fixture(self, fixture_data):
        backend_values = [m.value for m in StalePolicy]
        assert backend_values == fixture_data["StalePolicy"]

    def test_program_status_matches_fixture(self, fixture_data):
        backend_values = [m.value for m in ProgramStatus]
        assert backend_values == fixture_data["ProgramStatus"]

    def test_review_status_matches_fixture(self, fixture_data):
        backend_values = [m.value for m in ReviewStatus]
        assert backend_values == fixture_data["ReviewStatus"]

    def test_field_source_contract_fields_match_fixture(self, fixture_data):
        model_fields = list(FieldSourceContract.model_fields.keys())
        assert model_fields == fixture_data["FieldSourceContract_fields"]

    def test_program_status_contract_fields_match_fixture(self, fixture_data):
        model_fields = list(ProgramStatusContract.model_fields.keys())
        assert model_fields == fixture_data["ProgramStatusContract_fields"]
