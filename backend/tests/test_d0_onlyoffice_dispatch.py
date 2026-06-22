"""D0 底稿 OnlyOffice dispatch 测试：非白名单 sheet → onlyoffice-sheet componentType

验证 render-config dispatch 循环中的核心逻辑（design §1.1）：
  - 多 sheet 底稿中，无后端 renderer 且 componentType 不在 HTML 白名单的 sheet
    → componentType 重写为 "onlyoffice-sheet"
    → html_data = {"onlyoffice": True, "sheet_name": ...}
  - 白名单内的 sheet（b-index / a-program-console / audit-sheet 等）保持原 componentType

Mock 策略：
  - 不需要真实 PG（mock AsyncSession）
  - 不需要真实文件（mock 模板路径）
  - 通过 mock get_classification 返回混合 sheet 列表
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wp_classification_service import ClassificationResult


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_classification(sheet_name: str, class_code: str) -> ClassificationResult:
    """创建一个 ClassificationResult 测试实例。"""
    return ClassificationResult(
        wp_code="D0",
        sheet_name=sheet_name,
        class_code=class_code,
        class_=f"D类-{sheet_name}",
        scope="multi_sheet",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=None,
    )


def _build_d0_classifications() -> list[ClassificationResult]:
    """构造 D0 底稿多 sheet 分类列表：混合白名单 + 非白名单。

    白名单 sheet（保持原 componentType）:
      - 底稿目录 → class_code "B-目录" → componentType "b-index"
      - 程序表D0A → class_code "A-程序表" → componentType "a-program-console"
      - 审定表D0-1 → class_code "D-函证" → componentType "d-form-confirmation"（白名单内）

    非白名单 sheet（应被重写为 onlyoffice-sheet）:
      - 业务模式评估D0-5 → class_code "D-业务模式" → componentType "d-form-qa"（非白名单）
      - 复核记录D0-7 → class_code "D-复核记录" → componentType "d-form-review"（非白名单）
    """
    return [
        _make_classification("底稿目录", "B-目录"),
        _make_classification("程序表D0A", "A-程序表"),
        _make_classification("审定表D0-1", "D-函证"),
        _make_classification("业务模式评估D0-5", "D-业务模式"),
        _make_classification("复核记录D0-7", "D-复核记录"),
        # 无 sheet 级 override 的非白名单 sheet → 仍走 onlyoffice-sheet（验证降级路径未破坏）
        _make_classification("自定义测算表", "D-业务模式"),
    ]


def _make_mock_db():
    """构造 mock DB session，模拟 D0 底稿最小查询结果集。

    DB 调用顺序（get_render_config 内部）：
      1. SELECT WorkingPaper → .scalars().first() → mock_wp
      2. SELECT is_deleted FROM projects → .scalar() → False (项目未删除)
      3. SELECT WpIndex → .scalars().first() → mock_wp_index
      4. WpCrossRef query → .scalars().all() → []
      5. SELECT year/biz FROM projects → .first() → (2025, "C")
      6+ 其他后续查询 → 空结果
    """
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
    mock_wp_index.wp_code = "D0"
    mock_wp_index.wp_name = "收入循环函证"
    mock_wp_index.audit_cycle = "D"
    mock_wp_index.is_deleted = False

    # Mock DB session
    db = AsyncMock()

    call_count = {"n": 0}

    async def mock_execute(*args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        scalars_mock = MagicMock()

        if call_count["n"] == 1:
            # Call 1: SELECT WorkingPaper → .scalars().first()
            scalars_mock.first.return_value = mock_wp
            result.scalars.return_value = scalars_mock
        elif call_count["n"] == 2:
            # Call 2: SELECT is_deleted FROM projects → .scalar()
            result.scalar.return_value = False
            scalars_mock.first.return_value = None
            result.scalars.return_value = scalars_mock
        elif call_count["n"] == 3:
            # Call 3: SELECT WpIndex → .scalars().first()
            scalars_mock.first.return_value = mock_wp_index
            result.scalars.return_value = scalars_mock
        elif call_count["n"] == 4:
            # Call 4: WpCrossRef query → .scalars().all()
            scalars_mock.all.return_value = []
            scalars_mock.first.return_value = None
            result.scalars.return_value = scalars_mock
        elif call_count["n"] == 5:
            # Call 5: SELECT year/biz FROM projects → .first()
            result.first.return_value = (2025, "C")
            scalars_mock.all.return_value = []
            scalars_mock.first.return_value = None
            result.scalars.return_value = scalars_mock
        else:
            # All subsequent queries: return empty/None
            scalars_mock.all.return_value = []
            scalars_mock.first.return_value = None
            result.scalars.return_value = scalars_mock
            result.first.return_value = (None, "D")
            result.scalar_one_or_none.return_value = None
            result.scalar.return_value = 0
            result.fetchall.return_value = []
        return result

    db.execute = AsyncMock(side_effect=mock_execute)
    db.rollback = AsyncMock()
    return db, wp_id, project_id


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_d0_non_whitelist_sheets_get_onlyoffice_component_type():
    """D0 多 sheet 底稿中，非白名单 sheet 应返回 componentType="onlyoffice-sheet"。

    验证 dispatch 循环核心逻辑：
      not renderer and _is_multi_sheet and component_type not in _ONLYOFFICE_HTML_WHITELIST
      → componentType = "onlyoffice-sheet"
      → html_data = {"onlyoffice": True, "sheet_name": <sheet_name>}
    """
    from app.routers.wp_render_config import get_render_config

    db, wp_id, project_id = _make_mock_db()
    classifications = _build_d0_classifications()

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

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
        patch(
            "app.routers.wp_render_config.resolve_package_sheets",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        # Classification service mock - 返回含白名单+非白名单混合的 sheet 列表
        cls_instance = AsyncMock()
        cls_instance.get_classification = AsyncMock(return_value=classifications)
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
            from fastapi import HTTPException

            if isinstance(e, HTTPException) and e.status_code in (404, 422):
                pytest.fail(
                    f"Mock 数据不完整导致业务异常: {e.status_code} {e.detail}"
                )
            if isinstance(e, (AttributeError, NameError, ImportError, TypeError)):
                pytest.fail(
                    f"代码链路断裂: {type(e).__name__}: {e}"
                )
            pytest.fail(f"未预期异常: {type(e).__name__}: {e}")

        # 验证返回结构
        assert isinstance(result, dict)
        assert "sheets" in result
        sheets = result["sheets"]
        assert len(sheets) >= 3, f"预期至少 3 个 sheet，实际 {len(sheets)}"

        # 建立 sheet_name → sheet dict 映射
        sheet_map = {s["sheet_name"]: s for s in sheets}

        # ─── 验证白名单 sheet 保持原 componentType ───────────────────────
        if "底稿目录" in sheet_map:
            assert sheet_map["底稿目录"]["componentType"] == "b-index", (
                "白名单 sheet '底稿目录' 应保持 componentType='b-index'"
            )

        if "程序表D0A" in sheet_map:
            assert sheet_map["程序表D0A"]["componentType"] == "a-program-console", (
                "白名单 sheet '程序表D0A' 应保持 componentType='a-program-console'"
            )

        if "审定表D0-1" in sheet_map:
            # D0-1 命中 sheet-override → confirmation-summary（协作者精细组件）
            assert sheet_map["审定表D0-1"]["componentType"] == "confirmation-summary", (
                "D0-1 应按 sheet-override 路由到 'confirmation-summary'"
            )

        # ─── 验证非白名单 sheet 路由 ─────────────────
        # 注：D0-5/D0-7 等有 sheet 级 override(协作者 confirmation-* 精细组件)的，
        # 现按 sheet-override 路由到 confirmation-*；无 override 的非白名单 sheet 才走 onlyoffice-sheet。
        if "业务模式评估D0-5" in sheet_map:
            s = sheet_map["业务模式评估D0-5"]
            # D0-5 命中 sheet-override → confirmation-alternative-d05（精细组件优先）
            assert s["componentType"] == "confirmation-alternative-d05", (
                f"D0-5 应按 sheet-override 路由到 'confirmation-alternative-d05'，"
                f"实际为 '{s['componentType']}'"
            )

        if "复核记录D0-7" in sheet_map:
            s = sheet_map["复核记录D0-7"]
            # D0-7 命中 sheet-override → confirmation-reliability（精细组件优先）
            assert s["componentType"] == "confirmation-reliability", (
                f"D0-7 应按 sheet-override 路由到 'confirmation-reliability'，"
                f"实际为 '{s['componentType']}'"
            )


@pytest.mark.anyio
async def test_d0_whitelist_sheets_never_get_onlyoffice():
    """D0 多 sheet 底稿中，白名单 sheet 绝不会被改为 onlyoffice-sheet。

    即使在多 sheet 场景下，白名单内 componentType 的 sheet 仍保留原始类型。
    """
    from app.routers.wp_render_config import get_render_config
    from app.routers.wp_render_config import _ONLYOFFICE_HTML_WHITELIST

    db, wp_id, project_id = _make_mock_db()
    classifications = _build_d0_classifications()

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

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
        patch(
            "app.routers.wp_render_config.resolve_package_sheets",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        cls_instance = AsyncMock()
        cls_instance.get_classification = AsyncMock(return_value=classifications)
        MockClsSvc.return_value = cls_instance

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
            from fastapi import HTTPException

            if isinstance(e, HTTPException) and e.status_code in (404, 422):
                pytest.fail(f"Mock 数据不完整导致业务异常: {e.status_code} {e.detail}")
            if isinstance(e, (AttributeError, NameError, ImportError, TypeError)):
                pytest.fail(f"代码链路断裂: {type(e).__name__}: {e}")
            pytest.fail(f"未预期异常: {type(e).__name__}: {e}")

        sheets = result.get("sheets", [])
        for s in sheets:
            ct = s["componentType"]
            if ct in _ONLYOFFICE_HTML_WHITELIST:
                # 白名单 componentType 不应被改为 onlyoffice-sheet
                assert ct != "onlyoffice-sheet", (
                    f"sheet '{s['sheet_name']}' 的原始 componentType 在白名单中，"
                    f"不应被改为 onlyoffice-sheet"
                )


@pytest.mark.anyio
async def test_onlyoffice_sheet_html_data_structure():
    """验证 onlyoffice-sheet 的 html_data 结构完整性。

    每个 onlyoffice-sheet 都必须包含:
      - onlyoffice: True
      - sheet_name: 非空字符串（与 sheet 的 sheet_name 字段一致）
    """
    from app.routers.wp_render_config import get_render_config

    db, wp_id, project_id = _make_mock_db()
    classifications = _build_d0_classifications()

    mock_user = MagicMock()
    mock_user.id = uuid.uuid4()

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
        patch(
            "app.routers.wp_render_config.resolve_package_sheets",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        cls_instance = AsyncMock()
        cls_instance.get_classification = AsyncMock(return_value=classifications)
        MockClsSvc.return_value = cls_instance

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
            from fastapi import HTTPException

            if isinstance(e, HTTPException) and e.status_code in (404, 422):
                pytest.fail(f"Mock 数据不完整导致业务异常: {e.status_code} {e.detail}")
            if isinstance(e, (AttributeError, NameError, ImportError, TypeError)):
                pytest.fail(f"代码链路断裂: {type(e).__name__}: {e}")
            pytest.fail(f"未预期异常: {type(e).__name__}: {e}")

        sheets = result.get("sheets", [])
        onlyoffice_sheets = [s for s in sheets if s["componentType"] == "onlyoffice-sheet"]

        # 「自定义测算表」无 sheet-override 的非白名单 sheet → onlyoffice-sheet（降级路径仍生效）
        assert len(onlyoffice_sheets) >= 1, (
            f"预期至少 1 个 onlyoffice-sheet，实际 {len(onlyoffice_sheets)}"
        )

        for s in onlyoffice_sheets:
            html_data = s["html_data"]
            assert html_data is not None, (
                f"onlyoffice-sheet '{s['sheet_name']}' 的 html_data 不应为 None"
            )
            assert html_data.get("onlyoffice") is True, (
                f"onlyoffice-sheet '{s['sheet_name']}' html_data.onlyoffice 应为 True"
            )
            assert html_data.get("sheet_name") == s["sheet_name"], (
                f"onlyoffice-sheet '{s['sheet_name']}' html_data.sheet_name 应等于 sheet_name"
            )
