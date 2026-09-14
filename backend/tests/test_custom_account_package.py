"""用户自定义科目工作包测试

spec workpaper-account-multifile-aggregation 需求 6：
- 导出 D2 模板（含 sheet_type + 字段定义）
- 导出→编辑→导入往返：解析 + 校验通过
- 非法模板拒绝（明确错误清单，不静默）
- 优先级解析（项目>事务所）+ 行业字段

纯函数部分无需 DB；DB 往返用 pg_only 标记（无 PG 时 skip）。

Requirements: 6.2, 6.3, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import uuid

import pytest
import yaml

from app.services.custom_account_package_service import (
    CustomPackageValidationError,
    export_package_template,
    parse_and_validate,
    validate_package_json,
)


# ─── 导出 ────────────────────────────────────────────────────────────────


class TestExportTemplate:
    def test_export_d2_yaml(self):
        """导出 D2 模板含 account_name/industry/sheets + sheet_type 合法值提示。"""
        text = export_package_template("D2")
        assert text is not None
        doc = yaml.safe_load(text)
        assert doc["wp_code"] == "D2"
        assert doc["account_name"] == "应收账款"
        assert isinstance(doc["sheets"], list) and len(doc["sheets"]) >= 14
        assert "_valid_sheet_types" in doc
        # 每个 sheet 有 sheet_name/sheet_type
        for s in doc["sheets"]:
            assert "sheet_name" in s and "sheet_type" in s

    def test_export_unknown_returns_none(self):
        assert export_package_template("Z99") is None


# ─── 校验 ────────────────────────────────────────────────────────────────


class TestValidation:
    def _valid_pkg(self) -> dict:
        return {
            "wp_code": "D2",
            "account_name": "应收账款",
            "industry": ["商贸"],
            "sheets": [
                {"sheet_name": "审定表D2-1", "sheet_type": "audit_sheet", "source_wp_code": "D2"},
                {"sheet_name": "明细表D2-2", "sheet_type": "detail_table", "source_wp_code": "D2"},
            ],
        }

    def test_valid_passes(self):
        assert validate_package_json(self._valid_pkg()) == []

    def test_missing_wp_code(self):
        pkg = self._valid_pkg()
        del pkg["wp_code"]
        errors = validate_package_json(pkg)
        assert any("wp_code" in e for e in errors)

    def test_missing_account_name(self):
        pkg = self._valid_pkg()
        del pkg["account_name"]
        errors = validate_package_json(pkg)
        assert any("account_name" in e for e in errors)

    def test_empty_sheets(self):
        pkg = self._valid_pkg()
        pkg["sheets"] = []
        errors = validate_package_json(pkg)
        assert any("sheets" in e for e in errors)

    def test_illegal_sheet_type(self):
        pkg = self._valid_pkg()
        pkg["sheets"][0]["sheet_type"] = "bogus_type"
        errors = validate_package_json(pkg)
        assert any("bogus_type" in e for e in errors)

    def test_sheet_missing_name(self):
        pkg = self._valid_pkg()
        del pkg["sheets"][0]["sheet_name"]
        errors = validate_package_json(pkg)
        assert any("sheet_name" in e for e in errors)


# ─── 解析往返 ────────────────────────────────────────────────────────────


class TestParseRoundtrip:
    def test_export_edit_import_roundtrip(self):
        """导出 D2 → 加一个 sheet → parse_and_validate 通过。"""
        text = export_package_template("D2")
        doc = yaml.safe_load(text)
        # 用户编辑：加一个自定义分析 sheet
        doc["sheets"].append(
            {"sheet_name": "商贸专用分析表D2-X", "sheet_type": "analysis", "source_wp_code": "D2"}
        )
        edited_text = yaml.safe_dump(doc, allow_unicode=True)
        pkg = parse_and_validate(edited_text)
        assert pkg["wp_code"] == "D2"
        # 辅助说明键被剔除
        assert not any(str(k).startswith("_") for k in pkg)
        assert any("商贸专用分析表" in s["sheet_name"] for s in pkg["sheets"])

    def test_parse_invalid_raises_with_errors(self):
        """非法模板抛 CustomPackageValidationError 携带明确清单。"""
        bad = yaml.safe_dump({"account_name": "x", "sheets": []}, allow_unicode=True)
        with pytest.raises(CustomPackageValidationError) as exc:
            parse_and_validate(bad)
        assert len(exc.value.errors) > 0

    def test_parse_malformed_yaml(self):
        with pytest.raises(CustomPackageValidationError):
            parse_and_validate("{ this is : not : valid : yaml")


# ─── DB 往返 + 优先级（pg_only）──────────────────────────────────────────


@pytest.mark.pg_only
class TestCustomPackageDBRoundtrip:
    @pytest.mark.asyncio
    async def test_import_then_resolve_uses_custom(self):
        """导入自定义 D2（仅 2 sheet）→ resolve_package_sheets 优先返回自定义。"""
        from app.core.database import async_session as async_session_factory
        from app.services.custom_account_package_service import import_custom_package
        from app.services.wp_account_package_resolver import resolve_package_sheets

        project_id = uuid.uuid4()
        package_json = {
            "wp_code": "D2",
            "account_name": "应收账款（自定义）",
            "industry": ["商贸"],
            "sheets": [
                {"sheet_name": "审定表D2-1", "sheet_type": "audit_sheet", "source_wp_code": "D2"},
                {"sheet_name": "商贸明细表D2-2", "sheet_type": "detail_table", "source_wp_code": "D2"},
            ],
        }
        async with async_session_factory() as db:
            await import_custom_package(
                db, scope="project", scope_id=project_id, package_json=package_json
            )
            results = await resolve_package_sheets(db, "D2", project_id)
            assert results is not None
            # 自定义 2 sheet + 合成底稿目录 = 3（覆盖内置 14+1 sheet）
            assert len(results) == 3
            names = [r.sheet_name for r in results]
            assert "商贸明细表D2-2" in names
            assert names[0] == "底稿目录"

            # 清理
            import sqlalchemy as sa
            await db.execute(sa.text(
                "DELETE FROM custom_account_packages WHERE scope_id = :sid"),
                {"sid": str(project_id)})
            await db.commit()
