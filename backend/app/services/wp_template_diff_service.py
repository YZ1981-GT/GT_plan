"""模板版本 diff 引擎

对比两版本 xlsx 模板，生成 sheet/列级 diff（新增/删除/改名）。
用于模板版本升级时的数据迁移决策。

Spec: wp-template-migration
Requirements: 1.1, 1.2
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ColumnDiff:
    """列级变化"""
    sheet_name: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)  # (old, new)


@dataclass
class TemplateDiff:
    """模板版本 diff 结果"""
    added_sheets: list[str] = field(default_factory=list)
    removed_sheets: list[str] = field(default_factory=list)
    renamed_sheets: list[tuple[str, str]] = field(default_factory=list)  # (old, new)
    column_diffs: list[ColumnDiff] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """是否有任何变化"""
        return bool(
            self.added_sheets
            or self.removed_sheets
            or self.renamed_sheets
            or self.column_diffs
        )

    def summary(self) -> dict[str, Any]:
        """生成摘要信息"""
        return {
            "added_sheets": len(self.added_sheets),
            "removed_sheets": len(self.removed_sheets),
            "renamed_sheets": len(self.renamed_sheets),
            "column_changes": len(self.column_diffs),
            "has_changes": self.has_changes,
        }


def _read_template_structure(file_path: str | Path) -> dict[str, list[str]]:
    """纯函数：读 xlsx → 返回 {sheet_name: [column_headers]}

    读取每个 sheet 第一行作为列标题。
    使用 read_sheet_values 统一适配器（calamine/openpyxl 自动切换）。
    无 DB、无副作用。
    """
    from app.services.xlsx_read_adapter import list_sheet_names, read_sheet_values

    file_path = Path(file_path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        return {}

    try:
        sheet_names = list_sheet_names(file_path)
    except Exception as e:
        logger.warning("无法加载模板文件 %s: %s", file_path, e)
        return {}

    structure: dict[str, list[str]] = {}

    for sheet_name in sheet_names:
        try:
            rows = read_sheet_values(file_path, sheet_name)
        except Exception:
            structure[sheet_name] = []
            continue
        headers: list[str] = []
        if rows and rows[0]:
            for cell in rows[0]:
                if cell is not None:
                    headers.append(str(cell).strip())
        structure[sheet_name] = headers

    return structure


def _detect_renamed_sheets(
    old_sheets: set[str],
    new_sheets: set[str],
    old_structure: dict[str, list[str]],
    new_structure: dict[str, list[str]],
    similarity_threshold: float = 0.7,
) -> list[tuple[str, str]]:
    """检测可能的 sheet 改名（基于列标题相似度）

    策略：对于每个被删除的 sheet，在新增 sheet 中找列标题最相似的。
    相似度 = 共有列数 / max(旧列数, 新列数)
    """
    removed = old_sheets - new_sheets
    added = new_sheets - old_sheets

    if not removed or not added:
        return []

    renamed: list[tuple[str, str]] = []
    used_new: set[str] = set()

    for old_name in sorted(removed):
        old_cols = set(old_structure.get(old_name, []))
        if not old_cols:
            continue

        best_match: str | None = None
        best_score: float = 0.0

        for new_name in sorted(added):
            if new_name in used_new:
                continue
            new_cols = set(new_structure.get(new_name, []))
            if not new_cols:
                continue

            common = len(old_cols & new_cols)
            total = max(len(old_cols), len(new_cols))
            score = common / total if total > 0 else 0.0

            if score > best_score:
                best_score = score
                best_match = new_name

        if best_match and best_score >= similarity_threshold:
            renamed.append((old_name, best_match))
            used_new.add(best_match)

    return renamed


def _detect_renamed_columns(
    old_cols: list[str],
    new_cols: list[str],
) -> list[tuple[str, str]]:
    """检测可能的列改名（基于位置匹配）

    策略：如果旧列和新列在相同位置，且旧列被删除、新列被新增，
    则视为改名。
    """
    old_set = set(old_cols)
    new_set = set(new_cols)
    removed = old_set - new_set
    added = new_set - old_set

    if not removed or not added:
        return []

    renamed: list[tuple[str, str]] = []
    used_new: set[str] = set()

    # 按位置匹配
    for i, old_col in enumerate(old_cols):
        if old_col not in removed:
            continue
        if i < len(new_cols) and new_cols[i] in added and new_cols[i] not in used_new:
            renamed.append((old_col, new_cols[i]))
            used_new.add(new_cols[i])

    return renamed


def generate_template_diff(
    old_path: str | Path,
    new_path: str | Path,
) -> TemplateDiff:
    """对比两版本模板 xlsx，生成 TemplateDiff

    Args:
        old_path: 旧版本模板文件路径
        new_path: 新版本模板文件路径

    Returns:
        TemplateDiff 包含 sheet/列级增删改名信息
    """
    old_structure = _read_template_structure(old_path)
    new_structure = _read_template_structure(new_path)

    old_sheets = set(old_structure.keys())
    new_sheets = set(new_structure.keys())

    # 检测 sheet 改名
    renamed_sheets = _detect_renamed_sheets(
        old_sheets, new_sheets, old_structure, new_structure
    )
    renamed_old = {r[0] for r in renamed_sheets}
    renamed_new = {r[1] for r in renamed_sheets}

    # 新增/删除 sheet（排除已识别为改名的）
    added_sheets = sorted(new_sheets - old_sheets - renamed_new)
    removed_sheets = sorted(old_sheets - new_sheets - renamed_old)

    # 列级 diff（共有 sheet + 改名 sheet）
    column_diffs: list[ColumnDiff] = []

    # 共有 sheet 的列对比
    common_sheets = old_sheets & new_sheets
    for sheet_name in sorted(common_sheets):
        old_cols = old_structure[sheet_name]
        new_cols = new_structure[sheet_name]
        col_diff = _compute_column_diff(sheet_name, old_cols, new_cols)
        if col_diff:
            column_diffs.append(col_diff)

    # 改名 sheet 的列对比
    for old_name, new_name in renamed_sheets:
        old_cols = old_structure[old_name]
        new_cols = new_structure[new_name]
        col_diff = _compute_column_diff(new_name, old_cols, new_cols)
        if col_diff:
            column_diffs.append(col_diff)

    diff = TemplateDiff(
        added_sheets=added_sheets,
        removed_sheets=removed_sheets,
        renamed_sheets=renamed_sheets,
        column_diffs=column_diffs,
    )

    logger.info(
        "模板 diff 完成: %s",
        diff.summary(),
    )
    return diff


def _compute_column_diff(
    sheet_name: str,
    old_cols: list[str],
    new_cols: list[str],
) -> ColumnDiff | None:
    """计算单个 sheet 的列级 diff"""
    old_set = set(old_cols)
    new_set = set(new_cols)

    # 检测列改名
    renamed = _detect_renamed_columns(old_cols, new_cols)
    renamed_old = {r[0] for r in renamed}
    renamed_new = {r[1] for r in renamed}

    added = sorted(new_set - old_set - renamed_new)
    removed = sorted(old_set - new_set - renamed_old)

    if not added and not removed and not renamed:
        return None

    return ColumnDiff(
        sheet_name=sheet_name,
        added=added,
        removed=removed,
        renamed=renamed,
    )
