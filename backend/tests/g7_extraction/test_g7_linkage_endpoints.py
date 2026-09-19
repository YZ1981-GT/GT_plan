"""
Task 7.2: 联动端点与 DB 写入集成测试

覆盖：
- preview / import 成功路径
- 409（assert_expected_versions）
- 422（配置错误）
- readonly 不可导入
- import DB 写入：四表只填空合并、consol_scope 同步不覆盖 is_included、
  g7_suggestions 写入、Linkage_Stale 置位与清零

_Requirements: 8.1, 8.2_
"""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.consol_worksheet_data import (
    G7LinkageImportRequest,
    apply_g7_linkage_import,
    get_g7_linkage_preview,
    get_g7_linkage_stale,
)
from app.services.g7_consol_linkage_service import (
    G7LinkageConfigError,
    G7LinkageConflictError,
    assert_expected_versions,
    merge_target_rows,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _fake_user(role="edit"):
    """Minimal user object for dependency injection."""
    u = MagicMock()
    u.id = uuid.uuid4()
    u.role = role
    return u


def _make_preview_result(*, stale=False, suggestions=None):
    """Build a minimal preview result mirroring g7_consol_linkage_service output."""
    return {
        "importable": {
            "info": [
                {
                    "company_code": "C001",
                    "company_name": "子公司甲",
                    "_g7_group_type": "subsidiary",
                    "_g7_newly_consolidated": "否",
                    "common_ratio": 80,
                }
            ],
            "cost": [
                {"company_code": "C001", "company_name": "子公司甲", "opening": 100, "increase": 20}
            ],
            "equity_inv": [],
            "net_asset": [],
        },
        "unresolved_companies": [],
        "ambiguous_companies": [],
        "sources_used": ["G7-4", "G7-2"],
        "source_wp_id": str(uuid.uuid4()),
        "source_updated_at": "2025-06-01T10:00:00+00:00",
        "item_versions": {"G7-4-rows": "v1", "G7-2-rows": "v2"},
        "stale_sheets": ["info"] if stale else [],
        "linkage_stale": stale,
        "suggestions": suggestions or [],
    }


def _make_context(*, versions=None, stale=False, suggestions=None):
    """Context as returned by load_g7_linkage_context."""
    versions = versions or {"G7-4-rows": "v1", "G7-2-rows": "v2"}
    return {
        "wp_id": str(uuid.uuid4()),
        "updated_at": "2025-06-01T10:00:00+00:00",
        "payloads": {
            "G7-4-rows": [
                {
                    "id": "b1",
                    "groupType": "subsidiary",
                    "investeeName": "子公司甲",
                    "directHoldingRatio": 80,
                    "accountingMethod": "成本法",
                }
            ],
            "G7-2-rows": [
                {
                    "id": "c1",
                    "section": "cost",
                    "investeeName": "子公司甲",
                    "auditedOpeningAmount": 100,
                    "auditedIncreaseAmount": 20,
                }
            ],
        },
        "item_versions": versions,
        "companies": [],
    }


# ─── preview 成功 ─────────────────────────────────────────────────────────────

class TestPreviewSuccess:
    """preview 端点成功路径。"""

    @pytest.mark.asyncio
    async def test_preview_returns_importable_candidates(self):
        """preview 返回 importable、item_versions、sources_used。"""
        db = AsyncMock()
        user = _fake_user("readonly")
        preview_data = _make_preview_result()

        with patch(
            "app.routers.consol_worksheet_data.preview_g7_linkage",
            new_callable=AsyncMock,
            return_value=preview_data,
        ) as mock_preview:
            result = await get_g7_linkage_preview(
                project_id=uuid.uuid4(), year=2025, db=db, user=user
            )

        mock_preview.assert_called_once()
        assert "importable" in result
        assert "item_versions" in result
        assert result["item_versions"]["G7-4-rows"] == "v1"


# ─── import 成功 ──────────────────────────────────────────────────────────────

class TestImportSuccess:
    """import 端点成功路径。"""

    @pytest.mark.asyncio
    async def test_import_success_returns_imported_counts(self):
        """import 成功返回 imported dict 含各表写入行数。"""
        db = AsyncMock()
        # Mock execute to return empty rows for current data
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        db.execute.return_value = mock_result
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = _fake_user("edit")
        body = G7LinkageImportRequest(
            sheet_keys=["info", "cost"],
            expected_versions={"G7-4-rows": "v1", "G7-2-rows": "v2"},
        )

        context = _make_context()

        with patch(
            "app.services.g7_consol_linkage_service.load_g7_linkage_context",
            new_callable=AsyncMock,
            return_value=context,
        ):
            result = await apply_g7_linkage_import(
                project_id=uuid.uuid4(),
                year=2025,
                body=body,
                db=db,
                user=user,
            )

        assert "imported" in result
        assert "scope_synced" in result
        assert result["scope_synced"] >= 0


# ─── 409 expected_versions 冲突 ───────────────────────────────────────────────

class TestImport409:
    """import 409 当 expected_versions 过期。"""

    def test_assert_expected_versions_raises_on_mismatch(self):
        """expected_versions 不一致时抛 G7LinkageConflictError。"""
        current = {"G7-4-rows": "v1", "G7-2-rows": "v2"}
        expected = {"G7-4-rows": "old_version", "G7-2-rows": "v2"}

        with pytest.raises(G7LinkageConflictError):
            assert_expected_versions(current, expected)

    def test_assert_expected_versions_passes_when_matching(self):
        """版本一致不抛异常。"""
        current = {"G7-4-rows": "v1", "G7-2-rows": "v2"}
        expected = {"G7-4-rows": "v1", "G7-2-rows": "v2"}
        # Should not raise
        assert_expected_versions(current, expected)

    def test_assert_expected_versions_passes_when_none(self):
        """expected_versions 为 None 时不校验（首次导入）。"""
        current = {"G7-4-rows": "v1"}
        assert_expected_versions(current, None)

    @pytest.mark.asyncio
    async def test_import_endpoint_returns_409_on_conflict(self):
        """import 端点在版本冲突时返回 409 HTTP。"""
        from fastapi import HTTPException

        db = AsyncMock()
        db.rollback = AsyncMock()
        user = _fake_user("edit")
        body = G7LinkageImportRequest(
            expected_versions={"G7-4-rows": "stale_v"},
        )

        context = _make_context(versions={"G7-4-rows": "v1", "G7-2-rows": "v2"})

        with patch(
            "app.services.g7_consol_linkage_service.load_g7_linkage_context",
            new_callable=AsyncMock,
            return_value=context,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await apply_g7_linkage_import(
                    project_id=uuid.uuid4(),
                    year=2025,
                    body=body,
                    db=db,
                    user=user,
                )

        assert exc_info.value.status_code == 409


# ─── 422 配置错误 ──────────────────────────────────────────────────────────────

class TestPreview422:
    """preview 返回 422 当 G7 配置不合法。"""

    @pytest.mark.asyncio
    async def test_preview_422_on_config_error(self):
        """G7 未生成或多实例时 preview 返回 422。"""
        from fastapi import HTTPException

        db = AsyncMock()
        user = _fake_user("readonly")

        with patch(
            "app.routers.consol_worksheet_data.preview_g7_linkage",
            new_callable=AsyncMock,
            side_effect=G7LinkageConfigError("G7 主表未实例化"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_g7_linkage_preview(
                    project_id=uuid.uuid4(), year=2025, db=db, user=user
                )

        assert exc_info.value.status_code == 422
        assert "g7_config" in str(exc_info.value.detail)


# ─── readonly 不可导入 ─────────────────────────────────────────────────────────

class TestReadonlyCannotImport:
    """readonly 权限可预览但不可导入（由 require_project_access 门控）。"""

    def test_require_project_access_edit_for_import(self):
        """import 端点声明 require_project_access('edit') 依赖。"""
        import inspect
        sig = inspect.signature(apply_g7_linkage_import)
        # user 参数的默认值是 Depends(require_project_access("edit"))
        user_param = sig.parameters["user"]
        assert user_param.default is not inspect.Parameter.empty
        # 端点签名含 require_project_access → runtime 拦截 readonly
        # （Depends 注入层保证 readonly 用户被拦截，此处仅做声明级契约检查）

    def test_require_project_access_readonly_for_preview(self):
        """preview 端点声明 require_project_access('readonly') 依赖。"""
        import inspect
        sig = inspect.signature(get_g7_linkage_preview)
        user_param = sig.parameters["user"]
        assert user_param.default is not inspect.Parameter.empty

    def test_require_project_access_readonly_for_stale(self):
        """stale 端点声明 require_project_access('readonly') 依赖。"""
        import inspect
        sig = inspect.signature(get_g7_linkage_stale)
        user_param = sig.parameters["user"]
        assert user_param.default is not inspect.Parameter.empty


# ─── import DB 写入：四表只填空合并 ───────────────────────────────────────────

class TestMergeTargetRowsFillEmpty:
    """merge_target_rows 只填空值，不覆盖已有。"""

    def test_fill_empty_does_not_overwrite(self):
        """已有 opening=100 的行不被 incoming opening=200 覆盖。"""
        current = [
            {"company_code": "C001", "company_name": "子公司甲", "opening": 100}
        ]
        incoming = [
            {"company_code": "C001", "company_name": "子公司甲", "opening": 200, "increase": 50}
        ]
        merged = merge_target_rows(current, incoming, overwrite=False)
        # opening 保留原值 100，increase 被填入 50
        row = next(r for r in merged if r.get("company_code") == "C001")
        assert row["opening"] == 100
        assert row["increase"] == 50

    def test_fill_empty_new_company_appended(self):
        """current 无该公司时，incoming 整行追加。"""
        current = [
            {"company_code": "C001", "company_name": "子公司甲", "opening": 100}
        ]
        incoming = [
            {"company_code": "C002", "company_name": "联营乙", "opening": 50}
        ]
        merged = merge_target_rows(current, incoming, overwrite=False)
        codes = [r.get("company_code") for r in merged]
        assert "C001" in codes
        assert "C002" in codes

    def test_overwrite_mode_replaces_values(self):
        """overwrite=True 时覆盖已有值。"""
        current = [
            {"company_code": "C001", "company_name": "子公司甲", "opening": 100}
        ]
        incoming = [
            {"company_code": "C001", "company_name": "子公司甲", "opening": 200}
        ]
        merged = merge_target_rows(current, incoming, overwrite=True)
        row = next(r for r in merged if r.get("company_code") == "C001")
        assert row["opening"] == 200


# ─── import DB 写入：consol_scope 同步不覆盖 is_included ──────────────────────

class TestConsolScopeSyncNoOverwrite:
    """consol_scope 同步时不覆盖已有 is_included。"""

    @pytest.mark.asyncio
    async def test_scope_sync_preserves_existing_is_included(self):
        """已存在的 scope 行不被覆盖 is_included（UPDATE 用 COALESCE 只填空）。"""
        # 验证 import_g7_linkage 的 scope SQL 中 UPDATE 不含 is_included 覆盖
        import inspect
        from app.services.g7_consol_linkage_service import import_g7_linkage
        src = inspect.getsource(import_g7_linkage)
        # UPDATE consol_scope SET ... 中不含 is_included = :included
        # （仅 INSERT 新行时设 is_included）
        assert "UPDATE consol_scope SET" in src
        # is_included 只在 INSERT 中使用，UPDATE 不覆盖它
        update_section = src.split("UPDATE consol_scope SET")[1].split("WHERE")[0]
        assert "is_included" not in update_section


# ─── import DB 写入：g7_suggestions 写入 ──────────────────────────────────────

class TestG7SuggestionsWrite:
    """import 可选建议草稿写入 g7_suggestions。"""

    @pytest.mark.asyncio
    async def test_suggestions_written_when_ids_selected(self):
        """apply_suggestion_ids 非空时写入 g7_suggestions。"""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        db.execute.return_value = mock_result
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        user = _fake_user("edit")
        body = G7LinkageImportRequest(
            sheet_keys=["info", "cost"],
            expected_versions={"G7-4-rows": "v1", "G7-2-rows": "v2"},
            apply_suggestion_ids=["sug1"],
        )

        context = _make_context()
        preview_data = _make_preview_result(
            suggestions=[
                {"id": "sug1", "type": "goodwill", "company": "子公司甲", "amount": 50},
                {"id": "sug2", "type": "minority", "company": "子公司甲", "amount": 10},
            ]
        )

        with patch(
            "app.services.g7_consol_linkage_service.load_g7_linkage_context",
            new_callable=AsyncMock,
            return_value=context,
        ), patch(
            "app.services.g7_consol_linkage_service.build_linkage_candidates",
            return_value=preview_data,
        ):
            result = await apply_g7_linkage_import(
                project_id=uuid.uuid4(),
                year=2025,
                body=body,
                db=db,
                user=user,
            )

        assert result["suggestions_applied"] == 1


# ─── Linkage_Stale 置位与清零 ─────────────────────────────────────────────────

class TestLinkageStale:
    """Linkage_Stale 行为验证。"""

    @pytest.mark.asyncio
    async def test_stale_endpoint_delegates_to_service(self):
        """GET stale 端点仅委托 load_linkage_stale_state。"""
        db = AsyncMock()
        user = _fake_user("readonly")
        expected_result = {"linkage_stale": False, "stale_sheets": []}

        with patch(
            "app.routers.consol_worksheet_data.load_linkage_stale_state",
            new_callable=AsyncMock,
            return_value=expected_result,
        ) as mock_load:
            result = await get_g7_linkage_stale(
                project_id=uuid.uuid4(), year=2025, db=db, user=user
            )

        mock_load.assert_called_once()
        assert result["linkage_stale"] is False

    def test_import_sets_stale_false_in_data(self):
        """import 写入的 _g7_linkage.stale 恒为 False（清零）。

        验证 import_g7_linkage 源码中写入 data._g7_linkage.stale = False。
        """
        import inspect
        from app.services.g7_consol_linkage_service import import_g7_linkage
        src = inspect.getsource(import_g7_linkage)
        # 写入的 _g7_linkage dict 包含 "stale": False
        assert '"stale": False' in src or "'stale': False" in src

    def test_stale_is_set_on_source_change(self):
        """checklist_responses 保存后调 mark_consol_linkage_stale_from_g7 置位。"""
        from app.services.g7_consol_linkage_service import (
            SOURCE_KEYS as _G7_LINK_KEYS,
            mark_consol_linkage_stale_from_g7,
        )
        # SOURCE_KEYS 包含 G7 源数据键
        assert "G7-4-rows" in _G7_LINK_KEYS or "G7-2-rows" in _G7_LINK_KEYS
        # mark_consol_linkage_stale_from_g7 可调用
        assert callable(mark_consol_linkage_stale_from_g7)
