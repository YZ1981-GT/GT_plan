"""科目工作包注册表服务

读取、验证和查询 account_package_registry.json。
核心规则：
- generated/*.yaml 不得作为生产 schema 引用
- report_row/note_section 为 null 时 mapping_status 必须为 pending_inventory_reconciliation
- mapping_status=pending_inventory_reconciliation 时 report_row/note_section 不得视为已确认

Requirements: 1.1, 1.5, 5.3
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "account_package_registry.json"
)

# 生产 schema 根目录
_PRODUCTION_SCHEMA_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "ledger_adapters"
    / "wp_render_schema"
)

VALID_MAPPING_STATUSES = [
    "confirmed_production",
    "pending_inventory_reconciliation",
    "conflict_requires_review",
]

VALID_SHEET_TYPES = [
    "procedure",
    "control_panel",
    "audit_sheet",
    "detail_table",
    "analysis",
    "adjustment",
    "disclosure",
    "conclusion",
    "confirmation_summary",
]

# 必填字段（包级别）
REQUIRED_PACKAGE_FIELDS = [
    "account_package_id",
    "cycle",
    "account_code",
    "account_name",
    "mapping_status",
    "primary_wp_code",
    "sheets",
]

# 必填字段（sheet 级别）
REQUIRED_SHEET_FIELDS = [
    "sheet_name",
    "sheet_type",
]


class RegistryValidationError(Exception):
    """注册表验证错误"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Registry validation failed: {errors}")


class AccountPackageRegistryService:
    """科目工作包注册表服务"""

    def __init__(self, registry_path: Path | None = None) -> None:
        self._registry_path = registry_path or _REGISTRY_PATH
        self._data: dict | None = None

    def load(self) -> dict:
        """加载注册表 JSON"""
        if self._data is not None:
            return self._data

        with open(self._registry_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

        return self._data

    def get_packages(self) -> list[dict]:
        """获取所有工作包配置"""
        data = self.load()
        return data.get("packages", [])

    def get_package(self, account_package_id: str) -> dict | None:
        """按 ID 获取单个工作包配置"""
        for pkg in self.get_packages():
            if pkg.get("account_package_id") == account_package_id:
                return pkg
        return None

    def get_packages_by_cycle(self, cycle: str) -> list[dict]:
        """按循环获取工作包列表"""
        return [
            pkg for pkg in self.get_packages()
            if pkg.get("cycle") == cycle
        ]

    def validate(self) -> list[str]:
        """验证注册表完整性，返回错误列表（空=通过）"""
        errors: list[str] = []
        data = self.load()

        packages = data.get("packages", [])
        if not packages:
            errors.append("Registry contains no packages")
            return errors

        for pkg in packages:
            pkg_id = pkg.get("account_package_id", "<unknown>")
            errors.extend(self._validate_package(pkg, pkg_id))

        return errors

    def validate_strict(self) -> None:
        """严格验证，失败抛异常"""
        errors = self.validate()
        if errors:
            raise RegistryValidationError(errors)

    def check_no_generated_refs(self) -> list[str]:
        """检查注册表不直接引用 generated/*.yaml 作为生产 schema

        Returns:
            违规引用列表（空=通过）
        """
        violations: list[str] = []
        for pkg in self.get_packages():
            pkg_id = pkg.get("account_package_id", "<unknown>")

            # 检查包级 schema_refs
            for ref in pkg.get("schema_refs", []):
                if self._is_generated_ref(ref):
                    violations.append(
                        f"Package '{pkg_id}' schema_refs contains generated ref: {ref}"
                    )

            # 检查 sheet 级 schema_ref
            for sheet in pkg.get("sheets", []):
                schema_ref = sheet.get("schema_ref")
                if schema_ref and self._is_generated_ref(schema_ref):
                    violations.append(
                        f"Package '{pkg_id}' sheet '{sheet.get('sheet_name')}' "
                        f"schema_ref is generated: {schema_ref}"
                    )

        return violations

    def get_effective_mapping_status(self, pkg: dict) -> str:
        """计算工作包有效 mapping_status

        规则：当 report_row 或 note_section 为 null/None 时，
        无论注册表声明的 mapping_status 是什么，
        有效状态强制为 pending_inventory_reconciliation。
        """
        report_row = pkg.get("report_row")
        note_section = pkg.get("note_section")

        if report_row is None or note_section is None:
            return "pending_inventory_reconciliation"

        return pkg.get("mapping_status", "pending_inventory_reconciliation")

    def is_mapping_confirmed(self, pkg: dict) -> bool:
        """判断工作包映射是否已确认

        只有 mapping_status != pending_inventory_reconciliation 时才视为已确认。
        pending 状态下 report_row/note_section 不得作为确定口径使用。
        """
        effective_status = self.get_effective_mapping_status(pkg)
        return effective_status == "confirmed_production"

    def get_confirmed_report_row(self, pkg: dict) -> str | None:
        """获取已确认的 report_row（pending 状态返回 None）"""
        if not self.is_mapping_confirmed(pkg):
            return None
        return pkg.get("report_row")

    def get_confirmed_note_section(self, pkg: dict) -> str | None:
        """获取已确认的 note_section（pending 状态返回 None）"""
        if not self.is_mapping_confirmed(pkg):
            return None
        return pkg.get("note_section")

    def invalidate_cache(self) -> None:
        """清除缓存，强制下次重新加载"""
        self._data = None

    # ─── Private helpers ─────────────────────────────────────────────────

    def _validate_package(self, pkg: dict, pkg_id: str) -> list[str]:
        """验证单个工作包配置"""
        errors: list[str] = []

        # 检查必填字段
        for field in REQUIRED_PACKAGE_FIELDS:
            if field not in pkg:
                errors.append(f"Package '{pkg_id}' missing required field: {field}")

        # 检查 mapping_status 有效值
        status = pkg.get("mapping_status")
        if status and status not in VALID_MAPPING_STATUSES:
            errors.append(
                f"Package '{pkg_id}' invalid mapping_status: {status}"
            )

        # 检查 mapping_status 与 report_row/note_section 一致性
        report_row = pkg.get("report_row")
        note_section = pkg.get("note_section")
        if (report_row is None or note_section is None) and status != "pending_inventory_reconciliation":
            errors.append(
                f"Package '{pkg_id}' has null report_row/note_section but "
                f"mapping_status is '{status}' (should be pending_inventory_reconciliation)"
            )

        # 检查 sheets
        sheets = pkg.get("sheets", [])
        if not sheets:
            errors.append(f"Package '{pkg_id}' has no sheets defined")

        for sheet in sheets:
            sheet_name = sheet.get("sheet_name", "<unknown>")
            for field in REQUIRED_SHEET_FIELDS:
                if field not in sheet:
                    errors.append(
                        f"Package '{pkg_id}' sheet '{sheet_name}' "
                        f"missing required field: {field}"
                    )

            sheet_type = sheet.get("sheet_type")
            if sheet_type and sheet_type not in VALID_SHEET_TYPES:
                errors.append(
                    f"Package '{pkg_id}' sheet '{sheet_name}' "
                    f"invalid sheet_type: {sheet_type}"
                )

        # 检查 schema_refs 不引用 generated
        for ref in pkg.get("schema_refs", []):
            if self._is_generated_ref(ref):
                errors.append(
                    f"Package '{pkg_id}' schema_refs contains "
                    f"generated reference: {ref}"
                )

        return errors

    @staticmethod
    def _is_generated_ref(ref: str) -> bool:
        """判断 schema 引用是否指向 generated 目录"""
        normalized = ref.replace("\\", "/")
        return (
            normalized.startswith("generated/")
            or "/generated/" in normalized
            or normalized == "generated"
        )
