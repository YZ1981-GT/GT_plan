"""附注动态模型 Pydantic Schema（Sprint A.1）

定义 table_data JSONB 内部的结构化类型：
- A.1.1: RowType 枚举 + ColumnMeta + DynamicRegion（双 sidecar）
- A.1.2: BindingSource + CellBinding（多源 fallback 链）

这些结构存储在 disclosure_notes.table_data 的 _columns_meta / _dynamic_regions / binding 字段中，
不是独立的 DB 列，而是 JSONB 内部的 schema 约定。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ===========================================================================
# A.1.1: row_type / 列 sidecar 模型
# ===========================================================================


class RowType(str, Enum):
    """行类型枚举

    判定动态行：row.row_type.startswith('dynamic_')
    """

    data = "data"
    subtotal = "subtotal"
    total = "total"
    header_label = "header_label"
    dynamic_anchor = "dynamic_anchor"
    dynamic_data = "dynamic_data"
    dynamic_marker_end = "dynamic_marker_end"


class ColumnMeta(BaseModel):
    """列元数据（_columns_meta 数组元素）

    存储在 table_data._columns_meta[] 中，描述每一列的属性。
    """

    id: str = Field(..., description="列唯一标识，如 col_label / col_amount_end")
    label: str = Field(default="", description="列显示名称")
    header_path: list[str] = Field(
        default_factory=list,
        description="多级合并表头路径，如 ['本年', '期末余额']",
    )
    col_type: str = Field(
        default="fixed",
        description="列类型：fixed（固定列）| dynamic（动态列）",
    )
    value_type: str = Field(
        default="amount",
        description="值类型：amount | text | percent | date",
    )
    width: int = Field(default=120, description="列宽度（px）")
    is_frozen: bool = Field(default=False, description="是否冻结列")


class DynamicRegion(BaseModel):
    """动态区域定义（_dynamic_regions 数组元素）

    存储在 table_data._dynamic_regions[] 中，标记表格中可动态展开的区域。
    """

    name: str = Field(..., description="区域名称，如 '客户明细'")
    axis: str = Field(..., description="展开轴向：'row' | 'column'")
    start_idx: int = Field(..., description="起始索引（行号或列号）")
    end_idx: int = Field(..., description="结束索引（行号或列号）")
    expandable: bool = Field(default=True, description="是否允许用户手动展开")
    dynamic_source: str = Field(
        default="manual",
        description="数据源：manual | aux_balance | aux_ledger_aging | wp_data",
    )
    source_config: dict[str, Any] = Field(
        default_factory=dict,
        description="数据源配置（source-specific 参数）",
    )


# ===========================================================================
# A.1.2: binding 多源 fallback 模型
# ===========================================================================


class BindingSource(BaseModel):
    """数据绑定源配置

    7 种数据源：
    - trial_balance: 试算表取数
    - aux_balance: 辅助余额表
    - aux_ledger_aging: 辅助账龄分析
    - wp_data: 底稿数据
    - formula: 公式计算
    - prior_year_note: 上年附注
    - manual: 手工填列
    - consol_aggregation: 合并汇总（Phase 2）
    """

    source: str = Field(
        ...,
        description=(
            "数据源类型：trial_balance | aux_balance | aux_ledger_aging | "
            "wp_data | formula | prior_year_note | manual | consol_aggregation"
        ),
    )
    # 以下为 source-specific 字段，用 dict 承载灵活配置
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="数据源特定配置（如 account_codes / wp_code / sheet 等）",
    )


class CellBinding(BaseModel):
    """单元格数据绑定（多源 fallback 链）

    存储在 table_data.binding 或 cell 级别的 _binding 字段中。
    primary 失败时按 fallback 顺序尝试，最多 3 级（CI-9）。
    """

    primary: dict[str, Any] = Field(
        ..., description="主数据源配置"
    )
    fallback: list[dict[str, Any]] = Field(
        default_factory=list,
        description="回退数据源列表（按优先级排序，最多 3 级）",
    )
    show_provenance: bool = Field(
        default=True,
        description="是否在 _cell_provenance 中记录实际取数来源",
    )


class CellProvenance(BaseModel):
    """单元格数据溯源记录

    存储在 table_data._cell_provenance['{row_idx}:{col_id}'] 中。
    """

    source: str = Field(..., description="实际使用的数据源类型")
    fetched_at: str | None = Field(default=None, description="取数时间 ISO 格式")
    fallback_used: bool = Field(default=False, description="是否使用了 fallback")
    fallback_index: int | None = Field(
        default=None, description="使用的 fallback 索引（0-based）"
    )
    value: Any = Field(default=None, description="取到的值")
    source_detail: dict[str, Any] = Field(
        default_factory=dict,
        description="数据源详细信息（如 wp_code / account_codes 等）",
    )
