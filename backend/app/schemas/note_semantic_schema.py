"""附注语义结构 sidecar Pydantic Schema

定义 table_data JSONB sidecar 中的语义结构类型：
- NoteRowType: 行类型枚举
- NoteSemanticColumn: 列语义定义 (col_id, label, source, amount_role)
- NoteSemanticRow: 行语义定义 (row_id, row_type, label, values, _cell_modes, _cell_meta)
- NoteSemanticTable: 表语义定义 (table_id, name, columns, rows)
- NoteSemanticMeta: 章节语义元数据 (_semantic 块)
- NotePolicyClause: 会计政策条款 (_policy_clauses 元素)
- NoteSemanticSidecar: 顶层容器

Validates: Requirements 3.1, 3.2, 3.3, 3.5
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ===========================================================================
# row_type 枚举
# ===========================================================================


class NoteRowType(str, Enum):
    """附注表格行类型枚举

    Requirements 3.2: 至少包括 table_title, group_header, data, subtotal,
    total, note_tip, footnote, blank, custom。
    """

    table_title = "table_title"
    group_header = "group_header"
    data = "data"
    subtotal = "subtotal"
    total = "total"
    note_tip = "note_tip"
    footnote = "footnote"
    blank = "blank"
    custom = "custom"


# ===========================================================================
# 列语义
# ===========================================================================


class NoteSemanticColumn(BaseModel):
    """列语义定义

    Requirements 3.3: 公式和取数绑定优先使用 col_id 而非列下标。
    """

    col_id: str = Field(..., description="列唯一标识，如 closing_balance")
    label: str = Field(default="", description="列显示名称，如 期末余额")
    source: str | None = Field(
        default=None,
        description="数据来源：workpaper | formula | manual | prior_note 等",
    )
    amount_role: str | None = Field(
        default=None,
        description="金额角色：opening | closing | current | prior 等",
    )


# ===========================================================================
# 单元格元数据
# ===========================================================================


class NoteCellMeta(BaseModel):
    """单元格元数据（_cell_meta 值）"""

    binding_id: str | None = Field(default=None, description="绑定注册表 ID")
    formula_id: str | None = Field(default=None, description="公式 ID")
    source: str | None = Field(default=None, description="数据来源标识")


# ===========================================================================
# 行语义
# ===========================================================================


class NoteSemanticRow(BaseModel):
    """行语义定义

    Requirements 3.2: 支持 row_id + row_type。
    Requirements 3.5: 保持 values[] 兼容，不破坏旧代码读取。
    """

    row_id: str = Field(..., description="行唯一标识，如 within_1_year")
    row_type: NoteRowType = Field(
        default=NoteRowType.data, description="行类型"
    )
    label: str = Field(default="", description="行显示名称，如 1年以内")
    values: list[Any] = Field(
        default_factory=list, description="单元格值数组，保持兼容"
    )
    cell_modes: dict[str, str] | None = Field(
        default=None,
        alias="_cell_modes",
        description="单元格模式映射，如 {'0': 'auto'}",
    )
    cell_meta: dict[str, NoteCellMeta] | None = Field(
        default=None,
        alias="_cell_meta",
        description="单元格元数据映射",
    )

    model_config = {"populate_by_name": True}


# ===========================================================================
# 表语义
# ===========================================================================


class NoteSemanticTable(BaseModel):
    """表语义定义

    Requirements 3.1: 支持 table_id 区分同一章节内多张表。
    """

    table_id: str = Field(..., description="表唯一标识，如 aging_analysis")
    name: str = Field(default="", description="表显示名称，如 账龄分析")
    columns: list[NoteSemanticColumn] = Field(
        default_factory=list, description="列语义定义列表"
    )
    rows: list[NoteSemanticRow] = Field(
        default_factory=list, description="行语义定义列表"
    )


# ===========================================================================
# 章节语义元数据
# ===========================================================================


class NoteSemanticMeta(BaseModel):
    """章节语义元数据（_semantic 块）

    存储在 table_data._semantic 中。
    """

    section_id: str = Field(..., description="章节 ID")
    semantic_section_id: str = Field(
        ..., description="语义章节 ID，用于跨模板版本映射"
    )
    variant: str | None = Field(
        default=None,
        description="模板变体：soe_standalone | soe_consolidated | listed_standalone | listed_consolidated",
    )
    scope: str | None = Field(
        default=None,
        description="范围：standalone | consolidated | both",
    )


# ===========================================================================
# 会计政策条款
# ===========================================================================


class NotePolicyClause(BaseModel):
    """会计政策条款定义（_policy_clauses 数组元素）

    Requirements 1.1: 条款化结构，包含 clause_id、标题、层级、
    本年/模板/上年内容、变量列表、差异/确认状态。
    """

    clause_id: str = Field(..., description="条款唯一标识，如 policy_revenue")
    title: str = Field(default="", description="条款标题，如 收入确认")
    level: int = Field(default=1, description="条款层级（1=一级标题，2=二级...）")
    current_text: str | None = Field(
        default=None, description="本年文本内容"
    )
    template_text: str | None = Field(
        default=None, description="模板文本内容"
    )
    prior_year_text: str | None = Field(
        default=None, description="上年文本内容"
    )
    variables: list[str] = Field(
        default_factory=list,
        description="条款中使用的变量名列表，如 ['company_name', 'year']",
    )
    diff_status: str = Field(
        default="unknown",
        description="差异状态：unchanged | changed | added | removed | unknown",
    )
    confirm_status: str = Field(
        default="pending",
        description="确认状态：pending | confirmed | rejected",
    )


# ===========================================================================
# 顶层容器
# ===========================================================================


class NoteSemanticSidecar(BaseModel):
    """附注语义结构 sidecar 顶层容器

    存储在 disclosure_notes.table_data 的 sidecar 字段中。
    包含 _semantic、_tables、_policy_clauses 三个可选块。
    """

    semantic: NoteSemanticMeta | None = Field(
        default=None,
        alias="_semantic",
        description="章节语义元数据",
    )
    tables: list[NoteSemanticTable] = Field(
        default_factory=list,
        alias="_tables",
        description="表语义定义列表",
    )
    policy_clauses: list[NotePolicyClause] = Field(
        default_factory=list,
        alias="_policy_clauses",
        description="会计政策条款列表",
    )

    model_config = {"populate_by_name": True}
