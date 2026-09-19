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
    get_s34_checklist,
)


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
async def test_get_s34_checklist_all_not_applicable():
    """db 返回空 → 全部 41 项 not_applicable, status=not_started."""
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)

    project_id = uuid4()
    checklist = await get_s34_checklist(project_id, mock_db)

    assert len(checklist) == 41
    for item in checklist:
        assert item["applicability"] == "not_applicable"
        assert item["status"] == "not_started"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. get_s34_checklist — 部分 applicable
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_s34_checklist_some_applicable():
    """db 返回部分 S34 wp_codes → 对应项 applicable + 状态正确映射."""
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

    project_id = uuid4()
    checklist = await get_s34_checklist(project_id, mock_db)

    assert len(checklist) == 41

    # 验证 applicable 项
    item_map = {item["wp_code"]: item for item in checklist}

    assert item_map["S34-1"]["applicability"] == "applicable"
    assert item_map["S34-1"]["status"] == "completed"

    assert item_map["S34-5"]["applicability"] == "applicable"
    assert item_map["S34-5"]["status"] == "in_progress"

    assert item_map["S34-10"]["applicability"] == "applicable"
    assert item_map["S34-10"]["status"] == "not_started"

    # 其余项保持 not_applicable
    not_applicable_items = [
        item for item in checklist
        if item["wp_code"] not in {"S34-1", "S34-5", "S34-10"}
    ]
    for item in not_applicable_items:
        assert item["applicability"] == "not_applicable"
        assert item["status"] == "not_started"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. router 注册
# ═══════════════════════════════════════════════════════════════════════════════


def test_router_registered():
    """s34_checklist_router 已注册于 router_registry/workpaper.py."""
    from app.router_registry import workpaper as wp_module

    source = inspect.getsource(wp_module)
    assert "s34_checklist" in source, (
        "S34 checklist 路由未在 router_registry/workpaper.py 中注册"
    )
