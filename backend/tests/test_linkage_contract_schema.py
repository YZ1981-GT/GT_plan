"""LinkageContract schema 序列化与字段完整性测试（P0 增强版）。"""
import pytest
from app.schemas.linkage_contract import (
    LinkageContract, SourceType, TargetType, LinkageStatus, LinkageConfidence,
    CONFIDENCE_LEVEL_MAP, ResolveRouteRequest, ResolveRouteResponse,
)


def test_full_contract_serialization():
    """完整 contract 序列化包含所有必要字段。"""
    contract = LinkageContract(
        source_type=SourceType.trial_balance,
        source_id="tb-row-001",
        source_cell="audited_amount",
        target_type=TargetType.workpaper,
        target_id="wp-id-001",
        target_cell="D12",
        amount="123456.78",
        basis="TB closing balance",
        status=LinkageStatus.current,
        confidence=LinkageConfidence.system,
        route="/projects/p1/workpapers/wp-id-001",
        audit_log_id="log-001",
        conflict_id=None,
    )
    data = contract.model_dump()
    assert data["source_type"] == "trial_balance"
    assert data["source_id"] == "tb-row-001"
    assert data["source_cell"] == "audited_amount"
    assert data["target_type"] == "workpaper"
    assert data["target_id"] == "wp-id-001"
    assert data["target_cell"] == "D12"
    assert data["amount"] == "123456.78"
    assert data["basis"] == "TB closing balance"
    assert data["status"] == "current"
    assert data["confidence"] == "system"
    assert data["route"] == "/projects/p1/workpapers/wp-id-001"
    assert data["audit_log_id"] == "log-001"
    assert data["conflict_id"] is None


def test_minimal_contract_defaults():
    """最小 contract 只需 source/target + type，其余为默认值。"""
    contract = LinkageContract(
        source_type=SourceType.ledger,
        source_id="ledger-001",
        target_type=TargetType.report,
        target_id="report-row-001",
    )
    data = contract.model_dump()
    assert data["status"] == "current"
    assert data["confidence"] == "system"
    assert data["source_cell"] is None
    assert data["target_cell"] is None
    assert data["amount"] is None
    assert data["route"] is None
    assert data["conflict_id"] is None


def test_source_type_enum_values():
    """SourceType 枚举包含所有预期值。"""
    expected = {
        "trial_balance", "ledger", "audit_sheet", "workpaper",
        "adjustment", "report", "note", "attachment", "ai",
    }
    actual = {e.value for e in SourceType}
    assert actual == expected


def test_target_type_enum_values():
    """TargetType 枚举包含所有预期值。"""
    expected = {
        "trial_balance", "ledger", "audit_sheet", "workpaper",
        "adjustment", "report", "note", "attachment", "ai",
    }
    actual = {e.value for e in TargetType}
    assert actual == expected


def test_linkage_status_enum_values():
    """LinkageStatus 枚举完整。"""
    expected = {"current", "stale", "conflict", "manual_override"}
    actual = {e.value for e in LinkageStatus}
    assert actual == expected


def test_linkage_confidence_enum_values():
    """LinkageConfidence 枚举完整。"""
    expected = {"system", "manual", "ai_suggested", "ai_confirmed"}
    actual = {e.value for e in LinkageConfidence}
    assert actual == expected


def test_confidence_level_property():
    """confidence_level 属性正确映射到 high/medium/low。"""
    c1 = LinkageContract(
        source_type=SourceType.trial_balance, source_id="x",
        target_type=TargetType.workpaper, target_id="y",
        confidence=LinkageConfidence.system,
    )
    assert c1.confidence_level == "high"

    c2 = LinkageContract(
        source_type=SourceType.trial_balance, source_id="x",
        target_type=TargetType.workpaper, target_id="y",
        confidence=LinkageConfidence.ai_suggested,
    )
    assert c2.confidence_level == "low"

    c3 = LinkageContract(
        source_type=SourceType.trial_balance, source_id="x",
        target_type=TargetType.workpaper, target_id="y",
        confidence=LinkageConfidence.ai_confirmed,
    )
    assert c3.confidence_level == "medium"


def test_confidence_level_map_covers_all_enums():
    """CONFIDENCE_LEVEL_MAP 必须覆盖所有 LinkageConfidence 枚举值。"""
    for conf in LinkageConfidence:
        assert conf in CONFIDENCE_LEVEL_MAP


def test_json_round_trip():
    """JSON 序列化/反序列化往返一致。"""
    contract = LinkageContract(
        source_type=SourceType.note,
        source_id="note-section-1",
        target_type=TargetType.attachment,
        target_id="att-001",
        status=LinkageStatus.stale,
        confidence=LinkageConfidence.ai_suggested,
    )
    json_str = contract.model_dump_json()
    restored = LinkageContract.model_validate_json(json_str)
    assert restored == contract


def test_resolve_route_request_model():
    """ResolveRouteRequest 模型基本验证。"""
    req = ResolveRouteRequest(
        target_type=TargetType.workpaper,
        target_id="D1",
    )
    assert req.target_type == TargetType.workpaper
    assert req.target_id == "D1"
    assert req.target_cell is None


def test_resolve_route_response_model():
    """ResolveRouteResponse 模型基本验证。"""
    resp = ResolveRouteResponse(
        route="/projects/p1/workpapers/wp-001",
        resolved_id="wp-001",
    )
    assert resp.route is not None
    assert resp.error is None


def test_source_target_type_enum_values_match():
    """前后端枚举一致性：SourceType 和 TargetType 值域必须完全一致。"""
    source_values = {e.value for e in SourceType}
    target_values = {e.value for e in TargetType}
    assert source_values == target_values
