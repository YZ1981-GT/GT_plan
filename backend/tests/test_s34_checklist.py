"""S34 核查事项清单 — 后端单测.

Spec: .kiro/specs/s34-ipo-review-bundle/ Task 3.2
Validates: Requirements 3.2

测试内容：
1. S34_CHECKLIST_DATA 静态数据完整性（41条，seq连续，wp_code齐全）
2. regRef 结构正确性（title 与 name 匹配，csrc/sse/szse/bse 键齐全）
3. _wp_status_to_completion 映射逻辑
4. get_s34_checklist 全 not_applicable 场景（空 db）
5. get_s34_checklist 部分 applicable 场景（mock db 返回部分 S34-* 底稿）
6. router 在 router_registry 中注册
"""

import inspect
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.s34_checklist_service import (
    S34_CHECKLIST_DATA,
    _wp_status_to_completion,
    build_s34_risk_indicator,
    classify_s34_applicability,
    get_s34_checklist,
    is_s34_related_risk,
)
import app.services.s34_checklist_service as s34_checklist_service


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 静态数据完整性
# ═══════════════════════════════════════════════════════════════════════════════


class TestS34ChecklistDataCompleteness:
    """S34_CHECKLIST_DATA 数据完整性."""

    def test_exact_41_items(self):
        """必须恰好 41 项."""
        assert len(S34_CHECKLIST_DATA) == 41

    def test_seq_1_to_41_sequential(self):
        """seq 从 1 到 41 连续."""
        seqs = [item["seq"] for item in S34_CHECKLIST_DATA]
        assert seqs == list(range(1, 42))

    def test_all_wp_codes_present(self):
        """wp_codes 为 S34-1 ~ S34-41 全部存在."""
        expected = {f"S34-{i}" for i in range(1, 42)}
        actual = {item["wp_code"] for item in S34_CHECKLIST_DATA}
        assert actual == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 2. regRef 结构正确性
# ═══════════════════════════════════════════════════════════════════════════════


class TestS34ChecklistRegRefStructure:
    """每项的 reg_ref 结构正确."""

    def test_reg_ref_title_matches_name(self):
        """reg_ref.title 应与 item.name 一致."""
        for item in S34_CHECKLIST_DATA:
            assert item["reg_ref"]["title"] == item["name"], (
                f"seq={item['seq']}: reg_ref.title={item['reg_ref']['title']!r} != name={item['name']!r}"
            )

    def test_reg_ref_all_keys_present(self):
        """每个 reg_ref 都包含 csrc/sse/szse/bse/title 5个键."""
        required_keys = {"csrc", "sse", "szse", "bse", "title"}
        for item in S34_CHECKLIST_DATA:
            actual_keys = set(item["reg_ref"].keys())
            assert actual_keys == required_keys, (
                f"seq={item['seq']}: reg_ref keys={actual_keys}, expected={required_keys}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _wp_status_to_completion 映射
# ═══════════════════════════════════════════════════════════════════════════════


class TestWpStatusToCompletion:
    """_wp_status_to_completion 映射逻辑."""

    @pytest.mark.parametrize("status,expected", [
        ("draft_complete", "completed"),
        ("review_passed", "completed"),
        ("archived", "completed"),
        ("in_progress", "in_progress"),
        ("draft", "not_started"),
        ("pending", "not_started"),
        (None, "not_started"),
        ("", "not_started"),
    ])
    def test_mapping(self, status, expected):
        assert _wp_status_to_completion(status) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 4. get_s34_checklist — 全 not_applicable（db 返回空）
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_s34_checklist_empty_b50_is_pending_not_recommended(monkeypatch):
    """B50 无风险数据时显示待确认，不把空结果伪造成不适用或推荐。"""
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)
    monkeypatch.setattr(
        s34_checklist_service,
        "load_b50_risks",
        AsyncMock(return_value=[]),
    )

    checklist = await get_s34_checklist(uuid4(), mock_db)

    assert len(checklist) == 41
    for item in checklist:
        assert item["applicability"] == "unknown"
        assert item["status"] == "not_started"
        assert item["risk_indicator"] == "unknown"
        assert item["risk_data_available"] is False
        assert item["risk_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. get_s34_checklist — 部分 applicable
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_s34_checklist_some_applicable(monkeypatch):
    """有 B50 风险结论时，已有底稿为 applicable、缺底稿但有风险为 recommended。"""
    mock_db = AsyncMock(spec=AsyncSession)

    wp_id_1 = str(uuid4())
    wp_id_2 = str(uuid4())
    wp_id_3 = str(uuid4())

    # 模拟 db 返回 3 条记录：(wp_code, id, status)
    mock_rows = [
        ("S34-1", wp_id_1, "draft_complete"),   # → completed
        ("S34-5", wp_id_2, "in_progress"),       # → in_progress
        ("S34-10", wp_id_3, "draft"),            # → not_started
    ]

    mock_result = MagicMock()
    mock_result.fetchall.return_value = mock_rows
    mock_db.execute = AsyncMock(return_value=mock_result)
    monkeypatch.setattr(
        s34_checklist_service,
        "load_b50_risks",
        AsyncMock(return_value=[
            {
                "account": "收入确认",
                "cycle": "D",
                "risk_level": "H",
                "is_special_risk": False,
            },
        ]),
    )

    checklist = await get_s34_checklist(uuid4(), mock_db)

    assert len(checklist) == 41

    # 验证四象限中的「风险 + 已有底稿」与「风险 + 无底稿」
    item_map = {item["wp_code"]: item for item in checklist}

    assert item_map["S34-1"]["applicability"] == "applicable"
    assert item_map["S34-1"]["status"] == "completed"
    assert item_map["S34-1"]["risk_indicator"] == "identified"

    assert item_map["S34-5"]["applicability"] == "applicable"
    assert item_map["S34-5"]["status"] == "in_progress"

    assert item_map["S34-10"]["applicability"] == "applicable"
    assert item_map["S34-10"]["status"] == "not_started"

    assert item_map["S34-2"]["applicability"] == "recommended"
    assert item_map["S34-2"]["status"] == "not_started"
    assert item_map["S34-2"]["risk_count"] == 1


@pytest.mark.asyncio
async def test_get_s34_checklist_confirmed_unrelated_risk_is_not_applicable(monkeypatch):
    """有已读取但与 S34 无关的 B50 风险，缺少底稿时才确认不适用。"""
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)
    monkeypatch.setattr(
        s34_checklist_service,
        "load_b50_risks",
        AsyncMock(return_value=[{
            "account": "应收账款",
            "cycle": "D",
            "risk_level": "H",
            "is_special_risk": False,
        }]),
    )

    checklist = await get_s34_checklist(uuid4(), mock_db)

    assert {item["applicability"] for item in checklist} == {"not_applicable"}
    assert {item["risk_indicator"] for item in checklist} == {"none"}


# ═══════════════════════════════════════════════════════════════════════════════
# 6. P2.2 风险指示器与四象限
# ═══════════════════════════════════════════════════════════════════════════════


class TestS34RiskIndicator:
    """风险映射只接受 B50 真源中有明确 S34 语义的结论。"""

    def test_empty_b50_result_is_unknown(self):
        result = build_s34_risk_indicator([])
        assert result == {
            "risk_indicator": "unknown",
            "risk_data_available": False,
            "risk_count": 0,
            "risk_source": "b50_checklist",
        }

    def test_high_fraud_preset_account_is_s34_related(self):
        assert is_s34_related_risk({
            "account": "收入确认",
            "cycle": "D",
            "risk_level": "H",
            "is_special_risk": False,
        }) is True
        assert build_s34_risk_indicator([{
            "account": "收入确认",
            "cycle": "D",
            "risk_level": "H",
            "is_special_risk": False,
        }])["risk_indicator"] == "identified"

    def test_explicit_s_cycle_is_s34_related(self):
        assert is_s34_related_risk({
            "account": "其他事项",
            "cycle": "S",
            "risk_level": "M",
            "is_special_risk": False,
        }) is True

    def test_unrelated_b50_risk_does_not_trigger_s34(self):
        result = build_s34_risk_indicator([{
            "account": "应收账款",
            "cycle": "D",
            "risk_level": "H",
            "is_special_risk": False,
        }])
        assert result["risk_indicator"] == "none"
        assert result["risk_data_available"] is True
        assert result["risk_count"] == 0


class TestS34ApplicabilityQuadrants:
    @pytest.mark.parametrize("data,risk,workpaper,expected", [
        (True, True, True, "applicable"),
        (True, True, False, "recommended"),
        (True, False, True, "applicable"),
        (True, False, False, "not_applicable"),
        # 空 B50 数据不是“无风险”：没有底稿时保持待确认，不得推荐。
        (False, False, False, "unknown"),
        (False, False, True, "applicable"),
    ])
    def test_four_quadrants_and_empty_source(
        self, data, risk, workpaper, expected,
    ):
        assert classify_s34_applicability(data, risk, workpaper) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 7. router 注册
# ═══════════════════════════════════════════════════════════════════════════════


def test_router_registered():
    """s34_checklist_router 已注册于 router_registry/workpaper.py."""
    from app.router_registry import workpaper as wp_module

    source = inspect.getsource(wp_module)
    assert "s34_checklist" in source, (
        "S34 checklist 路由未在 router_registry/workpaper.py 中注册"
    )
