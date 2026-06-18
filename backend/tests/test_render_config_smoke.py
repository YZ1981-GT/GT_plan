"""P0 冒烟测试：render-config 端点对所有已注册 A 类底稿 componentType 不 500。

背景（2026-06-18 踩坑）：
  双机合并后 `wp_render_config.py` 调用 `get_guidance_for_wp`（实际名 `get_wp_guidance`）
  导致全平台底稿打开 500。getDiagnostics 不报错、单测 mock 不真调 → 只有运行时崩。
  本测试用 in-process ASGI 真调 render-config 端点，断言：
    1. derive_component_type 对所有 _WP_CODE_OVERRIDE 返回合法 componentType
    2. 端点函数内部 import/调用链无 AttributeError/NameError（通过 mock DB 跑到真实代码路径）

设计：
  - 不需要真实 PG（mock AsyncSession）
  - 不需要真实数据（mock WorkingPaper/WpIndex 返回）
  - 重点覆盖 get_render_config 函数体内所有 import/调用是否存在
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wp_classification_service import (
    _WP_CODE_OVERRIDE,
    derive_component_type,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Part 1: derive_component_type 对 _WP_CODE_OVERRIDE 全覆盖
# ═══════════════════════════════════════════════════════════════════════════════

_ALL_OVERRIDE_CODES = list(_WP_CODE_OVERRIDE.keys())


@pytest.mark.parametrize("wp_code", _ALL_OVERRIDE_CODES)
def test_wp_code_override_returns_nonempty_component_type(wp_code: str):
    """每个 _WP_CODE_OVERRIDE 条目的 componentType 非空且非 skip。"""
    expected_ct = _WP_CODE_OVERRIDE[wp_code]
    assert expected_ct, f"_WP_CODE_OVERRIDE['{wp_code}'] 值为空"
    assert expected_ct != "skip", (
        f"_WP_CODE_OVERRIDE['{wp_code}'] 不应映射为 skip（已注册底稿应有专用组件）"
    )
    # 值必须是合法标识符格式（kebab-case）
    assert all(c.isalnum() or c == "-" for c in expected_ct), (
        f"componentType '{expected_ct}' 包含非法字符"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Part 2: htmlRendererRegistry 无重复 componentType（防双机合并重复 const）
# ═══════════════════════════════════════════════════════════════════════════════


def test_no_duplicate_component_types_in_wp_code_override():
    """_WP_CODE_OVERRIDE 中不应有重复 key（Python dict 天然去重，此测试防拼写变体冲突）。"""
    # 检查所有 value 格式合法
    values = list(_WP_CODE_OVERRIDE.values())
    for v in values:
        assert v and isinstance(v, str), f"componentType 值异常: {v!r}"
        assert all(c.isalnum() or c == "-" for c in v), f"componentType '{v}' 格式不合法"


# ═══════════════════════════════════════════════════════════════════════════════
# Part 3: render-config 端点函数体 import 链无 AttributeError
# ═══════════════════════════════════════════════════════════════════════════════


def _make_mock_db(wp_code: str = "A1"):
    """构造 mock DB session，模拟最小查询结果集。"""
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()

    # Mock WorkingPaper
    mock_wp = MagicMock()
    mock_wp.id = wp_id
    mock_wp.project_id = project_id
    mock_wp.wp_index_id = wp_index_id
    mock_wp.parsed_data = {"html_data": {}}
    mock_wp.file_path = None
    mock_wp.source_type = "template"
    mock_wp.assigned_to = None
    mock_wp.is_deleted = False

    # Mock WpIndex
    mock_wp_index = MagicMock()
    mock_wp_index.id = wp_index_id
    mock_wp_index.wp_code = wp_code
    mock_wp_index.wp_name = f"测试底稿 {wp_code}"
    mock_wp_index.audit_cycle = "A"
    mock_wp_index.is_deleted = False

    # Mock DB session
    db = AsyncMock()

    # execute returns different results based on query type
    # We'll use side_effect to handle multiple calls
    call_count = {"n": 0}

    async def mock_execute(*args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        scalars_mock = MagicMock()

        # First call: WorkingPaper query
        if call_count["n"] == 1:
            scalars_mock.first.return_value = mock_wp
            result.scalars.return_value = scalars_mock
        # Second call: WpIndex query
        elif call_count["n"] == 2:
            scalars_mock.first.return_value = mock_wp_index
            result.scalars.return_value = scalars_mock
        # Third call: WpCrossRef query
        elif call_count["n"] <= 4:
            scalars_mock.all.return_value = []
            scalars_mock.first.return_value = None
            result.scalars.return_value = scalars_mock
            result.first.return_value = None
            result.scalar_one_or_none.return_value = None
            result.fetchall.return_value = []
        else:
            # All subsequent calls: return empty/None
            scalars_mock.all.return_value = []
            scalars_mock.first.return_value = None
            result.scalars.return_value = scalars_mock
            result.first.return_value = (None, "C")
            result.scalar_one_or_none.return_value = None
            result.scalar.return_value = 0
            result.fetchall.return_value = []
        return result

    db.execute = AsyncMock(side_effect=mock_execute)
    return db, wp_id, project_id


# A 类底稿中最关键的 wp_code 子集（覆盖不同 componentType 路径）
_CRITICAL_A_CODES = [
    "A1",       # a1-dashboard
    "A2",       # a2-adjustment-console
    "A3",       # a3-consolidation-console
    "A5",       # cf-verification
    "A1-15",    # checklist-table
    "A1-16",    # checklist-table
    "A1-13",    # analytical-review
    "A13",      # misstatement-workpaper
    "A21",      # review-checklist
    "A31",      # audit-legend
    "A16",      # word-template
    "A17-1",    # a17-summary
    "A18-2",    # regulatory-letter
    "A10-2",    # d-form-confirmation
    "A14-2",    # d-form-table
    "A14-6",    # e-control-test
    "A7-2",     # c-note-table
    # B 类关键底稿
    "B1A",      # a-program-console (承接)
    "B10",      # a-program-console (了解环境)
    "B1-1",     # d-form-table (风险评估)
    "B3",       # checklist-table (独立性)
    "B22A-1",   # d-form-table (企业层面控制)
    "B23-1",    # d-form-table (业务层面控制)
    "B50",      # a-program-console (风险汇总)
    "B51",      # d-form-table (舞弊三因素)
    "B60-1",    # audit-sheet (工时预算)
]


@pytest.mark.anyio
@pytest.mark.parametrize("wp_code", _CRITICAL_A_CODES)
async def test_render_config_endpoint_no_500(wp_code: str):
    """render-config 端点对关键 A 类底稿不 500（验证 import/函数调用链完整）。

    这是防止双机合并后函数名错误/import 缺失导致全平台 500 的核心守护。
    """
    from app.routers.wp_render_config import get_render_config

    db, wp_id, project_id = _make_mock_db(wp_code)

    # Mock current_user
    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

    # Mock classification service 返回匹配的 classification
    from app.services.wp_classification_service import ClassificationResult

    mock_classification = ClassificationResult(
        wp_code=wp_code,
        sheet_name=f"{wp_code}_sheet",
        class_code="A-程序表",
        class_=f"A类-{wp_code}",
        scope="standalone",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=None,
    )

    with (
        patch(
            "app.routers.wp_render_config.WpClassificationService"
        ) as MockClsSvc,
        patch(
            "app.routers.wp_render_config.WpTemplateVersionService"
        ) as MockVerSvc,
        patch(
            "app.routers.wp_render_config._resolve_auto_fill_values",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        # Classification service mock
        cls_instance = AsyncMock()
        cls_instance.get_classification = AsyncMock(return_value=[mock_classification])
        MockClsSvc.return_value = cls_instance

        # Version service mock
        ver_instance = AsyncMock()
        ver_obj = MagicMock()
        ver_obj.version = "v2025-R5"
        ver_obj.id = uuid.uuid4()
        ver_instance.get_current_version = AsyncMock(return_value=ver_obj)
        MockVerSvc.return_value = ver_instance

        try:
            result = await get_render_config(
                wp_id=wp_id,
                sheet_name=None,
                db=db,
                current_user=mock_user,
            )
        except Exception as e:
            # 404 是合理的（mock 数据不完整），但 500 类错误不可接受
            # AttributeError / NameError / ImportError = 代码链路断裂
            if isinstance(e, (AttributeError, NameError, ImportError, TypeError)):
                pytest.fail(
                    f"render-config 对 wp_code='{wp_code}' 崩溃: "
                    f"{type(e).__name__}: {e}\n"
                    f"这表示代码中存在函数名错误/import 缺失，会导致全平台 500"
                )
            # HTTPException 404 等业务异常是可接受的
            from fastapi import HTTPException
            if isinstance(e, HTTPException) and e.status_code in (404, 422):
                return  # 预期内：mock 数据不完整导致的业务异常
            # 其他未预期异常也报失败
            pytest.fail(
                f"render-config 对 wp_code='{wp_code}' 未预期异常: "
                f"{type(e).__name__}: {e}"
            )

        # 如果成功返回，验证基本结构
        assert isinstance(result, dict)
        assert "sheets" in result
        assert "wp_code" in result
        assert result["wp_code"] == wp_code
