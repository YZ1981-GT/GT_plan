"""附注语义离线导入兼容 — Task 10.7

处理新旧离线包导入兼容逻辑：
- 旧版离线包继续走现有导入路径 (10.7.1)
- 新版 semantic workbook 增加隐藏 _meta sheet (10.7.2)
- 用户修改隐藏语义列时标记 structure_conflict (10.7.3)
- 锁定单元格被改时标记 locked_cell_conflict (10.7.4)
- 公式列被改时标记 formula_override_attempt (10.7.5)

本模块不修改现有 note_offline_import_service.py，作为独立兼容层。
Requirements: 12.1, 12.2, 12.3, 12.4
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ImportConflictResult",
    "ConflictItem",
    "WorkbookVersion",
    "SEMANTIC_META_KEYS",
    "detect_workbook_version",
    "build_semantic_meta",
    "detect_import_conflicts",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# _meta sheet 中语义版本的标识键
SEMANTIC_META_KEYS = {"workbook_version", "template_type", "semantic_version"}

# 有效冲突类型
VALID_CONFLICT_TYPES = {
    "structure_conflict",
    "locked_cell_conflict",
    "formula_override_attempt",
}


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


class WorkbookVersion:
    """工作簿版本枚举。"""
    LEGACY = "legacy"
    SEMANTIC = "semantic"


@dataclass
class ConflictItem:
    """单个冲突条目。"""
    conflict_type: str
    section_id: str = ""
    table_id: str = ""
    row_id: str = ""
    col_id: str = ""
    cell_ref: str = ""
    old_value: Any = None
    new_value: Any = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_type": self.conflict_type,
            "section_id": self.section_id,
            "table_id": self.table_id,
            "row_id": self.row_id,
            "col_id": self.col_id,
            "cell_ref": self.cell_ref,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "detail": self.detail,
        }


@dataclass
class ImportConflictResult:
    """导入冲突检测结果。"""
    content_changes: list[dict[str, Any]] = field(default_factory=list)
    structure_conflicts: list[ConflictItem] = field(default_factory=list)
    locked_cell_conflicts: list[ConflictItem] = field(default_factory=list)
    formula_overrides: list[ConflictItem] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        """是否存在任何冲突。"""
        return bool(
            self.structure_conflicts
            or self.locked_cell_conflicts
            or self.formula_overrides
        )

    @property
    def all_conflicts(self) -> list[ConflictItem]:
        """所有冲突的合并列表。"""
        return (
            self.structure_conflicts
            + self.locked_cell_conflicts
            + self.formula_overrides
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_changes": self.content_changes,
            "structure_conflicts": [c.to_dict() for c in self.structure_conflicts],
            "locked_cell_conflicts": [c.to_dict() for c in self.locked_cell_conflicts],
            "formula_overrides": [c.to_dict() for c in self.formula_overrides],
            "has_conflicts": self.has_conflicts,
        }


# ---------------------------------------------------------------------------
# 版本检测 (Task 10.7.1, 10.7.2)
# ---------------------------------------------------------------------------


def detect_workbook_version(workbook_data: dict[str, Any]) -> str:
    """检测工作簿版本。

    通过 _meta sheet 中的 workbook_version / template_type / semantic_version
    来判断是否为新版 semantic workbook。

    Args:
        workbook_data: 解析后的工作簿数据，应包含 sheets 信息。
            期望格式: {"_meta": {"workbook_version": ..., ...}, ...}
            或 {"sheets": {"_meta": {...}}}

    Returns:
        "legacy" 或 "semantic"
    """
    # 尝试从 _meta key 直接获取
    meta = workbook_data.get("_meta", {})

    # 也支持嵌套在 sheets 下
    if not meta and "sheets" in workbook_data:
        meta = workbook_data["sheets"].get("_meta", {})

    if not meta:
        return WorkbookVersion.LEGACY

    # 检查是否包含语义版本标识
    has_version = "workbook_version" in meta
    has_type = "template_type" in meta
    has_semantic = "semantic_version" in meta

    if has_version or (has_type and has_semantic):
        return WorkbookVersion.SEMANTIC

    return WorkbookVersion.LEGACY


def build_semantic_meta(
    *,
    workbook_version: str = "2.0",
    template_type: str = "semantic",
    semantic_version: str = "1.0.0",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建 _meta sheet 数据。

    新版 semantic workbook 的隐藏 _meta sheet 应包含：
    - workbook_version: 工作簿格式版本
    - template_type: 模板类型（semantic/legacy）
    - semantic_version: 语义结构版本号
    """
    meta: dict[str, Any] = {
        "workbook_version": workbook_version,
        "template_type": template_type,
        "semantic_version": semantic_version,
    }
    if extra:
        meta.update(extra)
    return meta


# ---------------------------------------------------------------------------
# 冲突检测 (Task 10.7.3, 10.7.4, 10.7.5)
# ---------------------------------------------------------------------------


def detect_import_conflicts(
    original_data: dict[str, Any],
    imported_data: dict[str, Any],
    meta: dict[str, Any],
) -> ImportConflictResult:
    """检测导入冲突。

    对比原始导出数据和用户修改后的导入数据，识别三类冲突：
    1. structure_conflict: 隐藏语义列被修改
    2. locked_cell_conflict: 锁定单元格被修改
    3. formula_override_attempt: 公式列被修改

    Args:
        original_data: 原始导出时的数据快照。
            格式: {"sections": {"section_id": {"rows": [...], ...}}}
        imported_data: 用户修改后导入的数据。
            格式同 original_data。
        meta: _meta sheet 中的元数据，包含 cell_modes / formulas / semantic_columns 等。

    Returns:
        ImportConflictResult 包含所有冲突和内容变更。
    """
    result = ImportConflictResult()

    original_sections = original_data.get("sections", {})
    imported_sections = imported_data.get("sections", {})

    # 从 meta 提取锁定和公式信息
    cell_modes = meta.get("cell_modes", {})
    formulas = meta.get("formulas", {})
    semantic_columns = meta.get("semantic_columns", [])

    for section_id, imported_section in imported_sections.items():
        original_section = original_sections.get(section_id, {})
        if not original_section:
            # 新增 section 不算冲突，记为内容变更
            result.content_changes.append({
                "type": "section_added",
                "section_id": section_id,
            })
            continue

        _detect_section_conflicts(
            section_id=section_id,
            original_section=original_section,
            imported_section=imported_section,
            cell_modes=cell_modes.get(section_id, {}),
            formulas=formulas.get(section_id, {}),
            semantic_columns=semantic_columns,
            result=result,
        )

    return result


def _detect_section_conflicts(
    *,
    section_id: str,
    original_section: dict[str, Any],
    imported_section: dict[str, Any],
    cell_modes: dict[str, Any],
    formulas: dict[str, Any],
    semantic_columns: list[str],
    result: ImportConflictResult,
) -> None:
    """检测单个 section 内的冲突。"""
    original_rows = original_section.get("rows", [])
    imported_rows = imported_section.get("rows", [])

    for row_idx, imported_row in enumerate(imported_rows):
        if row_idx >= len(original_rows):
            # 新增行属于内容变更
            result.content_changes.append({
                "type": "row_added",
                "section_id": section_id,
                "row_idx": row_idx,
            })
            continue

        original_row = original_rows[row_idx]
        row_id = imported_row.get("row_id", f"row_{row_idx}")
        table_id = imported_row.get("table_id", "")

        original_cells = original_row.get("cells", original_row.get("values", []))
        imported_cells = imported_row.get("cells", imported_row.get("values", []))

        for col_idx, imported_val in enumerate(imported_cells):
            if col_idx >= len(original_cells):
                continue

            original_val = original_cells[col_idx]
            col_id = f"col_{col_idx}"
            cell_ref = f"{row_idx}:{col_idx}"

            # 值没变则跳过
            if _values_match(original_val, imported_val):
                continue

            # 检查是否为语义列（隐藏列）
            if _is_semantic_column(col_idx, semantic_columns):
                result.structure_conflicts.append(ConflictItem(
                    conflict_type="structure_conflict",
                    section_id=section_id,
                    table_id=table_id,
                    row_id=row_id,
                    col_id=col_id,
                    cell_ref=cell_ref,
                    old_value=original_val,
                    new_value=imported_val,
                    detail=f"隐藏语义列 col_{col_idx} 被修改",
                ))
                continue

            # 检查是否为锁定单元格
            cell_mode = cell_modes.get(cell_ref, "")
            if cell_mode in ("locked", "auto", "wp_data"):
                result.locked_cell_conflicts.append(ConflictItem(
                    conflict_type="locked_cell_conflict",
                    section_id=section_id,
                    table_id=table_id,
                    row_id=row_id,
                    col_id=col_id,
                    cell_ref=cell_ref,
                    old_value=original_val,
                    new_value=imported_val,
                    detail=f"锁定单元格 (mode={cell_mode}) 被修改",
                ))
                continue

            # 检查是否为公式列
            if cell_ref in formulas or _is_formula_column(col_idx, formulas):
                result.formula_overrides.append(ConflictItem(
                    conflict_type="formula_override_attempt",
                    section_id=section_id,
                    table_id=table_id,
                    row_id=row_id,
                    col_id=col_id,
                    cell_ref=cell_ref,
                    old_value=original_val,
                    new_value=imported_val,
                    detail=f"公式单元格被手工修改",
                ))
                continue

            # 普通内容变更
            result.content_changes.append({
                "type": "cell_changed",
                "section_id": section_id,
                "cell_ref": cell_ref,
                "old_value": original_val,
                "new_value": imported_val,
            })


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------


def _values_match(a: Any, b: Any) -> bool:
    """比较两个值是否相等（容忍类型差异）。"""
    if a is None and b is None:
        return True
    if a is None or b is None:
        # 空字符串视为 None
        if a == "" and b is None:
            return True
        if a is None and b == "":
            return True
        return False
    # 数值比较容忍 float/int
    try:
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return abs(float(a) - float(b)) < 1e-10
    except (TypeError, ValueError):
        pass
    # 字符串化后比较（处理 "100" vs 100）
    return str(a).strip() == str(b).strip()


def _is_semantic_column(col_idx: int, semantic_columns: list[str]) -> bool:
    """判断列是否为语义隐藏列。

    semantic_columns 可以是列索引列表或列名列表。
    """
    if not semantic_columns:
        return False
    # 支持整数索引或字符串索引
    return col_idx in semantic_columns or str(col_idx) in semantic_columns


def _is_formula_column(col_idx: int, formulas: dict[str, Any]) -> bool:
    """判断列是否为公式列。

    检查 formulas dict 中是否有以该列为目标的公式。
    """
    col_str = str(col_idx)
    for key in formulas:
        # 公式 key 格式: "row:col" 或 "col_id"
        parts = key.split(":")
        if len(parts) == 2 and parts[1] == col_str:
            return True
    return False
