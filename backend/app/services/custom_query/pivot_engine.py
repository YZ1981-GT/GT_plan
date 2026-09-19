"""PivotEngine — 转置/透视引擎（高级查询模块）

Task 10.1（advanced-query-module）：定义 ``Grid`` / ``Cell`` 数据结构，并实现整表
行列互换 ``transpose(grid)`` 为**对称纯函数**。

设计要点（design.md §Components 5 PivotEngine）：

- 数据结构：``Grid: {row_labels[], col_labels[], cells[[Cell]]}``；
  ``Cell: {value, addr_id|None}``。``cells`` 为 ``R × C`` 的二维矩阵，
  ``cells[r][c]`` 对应 ``row_labels[r]`` × ``col_labels[c]`` 的交叉单元格。
- ``transpose``（R6.2）：整表行列互换——行标签与列标签互换、单元格矩阵转置。
- **round-trip**（R6.3）：``transpose(transpose(R)) == R``，在**单元格值、行标签、
  列标签、行列顺序**四个维度上与原结果集完全一致。为此 ``transpose`` 实现为
  **对称纯函数**：不修改入参、无 IO、无 async，仅依据标签长度确定维度做矩阵转置，
  从而对退化形态（空数据但有标签、空表）亦保持严格 round-trip。

Task 10.2（advanced-query-module）在此基础上补充 ``pivot()``：

- 交叉透视：按 ``PivotConfig{row_dims[], col_dims[], value_field, agg}`` 将平铺 ``rows``
  透视为行列交叉表 ``Grid``（R6.1）。
- 列基数上限（R6.4）：列维度产生的列数 > ``max_cols``（默认 512）→ ``PIVOT_COL_LIMIT``
  （含 ``actual`` / ``limit``），**不执行透视、不返回部分结果**；列基数校验在**构建
  网格之前**完成。
- addr_id 保留（R6.5 / R6.6）：交叉单元格由**单一源格**产生 → 携带该源格 ``addr_id``；
  由**多个源格聚合**产生 → 不携带 addr_id、渲染为不可下钻普通文本单元格。
- 空组合（R6.7）：某行维度 × 列维度组合在源数据中无对应值 → 交叉单元格置**空值**
  （``None``，**非 0、非报错**）。
- 聚合一致性（P7 共享）：sum/count/avg/min/max 复用 ``GroupingEngine`` 的参考实现
  （``_compute_agg``），保证「透视聚合」与「分组聚合」对同一源值集合结果一致。

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from fastapi import HTTPException

from app.services.custom_query.grouping_engine import (
    Agg as _GroupAgg,
    GroupingEngine as _GroupingEngine,
    _sort_key,
)


@dataclass
class Cell:
    """透视/结果网格中的单元格。

    - ``value``：单元格显示值（可为任意标量，含 ``None`` 表示空值）。
    - ``addr_id``：当且仅当该值由**单一可解析源格**产生时携带其 ACNR ``addr_id``
      以支持下钻（R6.5）；多源聚合或无源 → ``None``（R6.6，不可下钻）。

    ``Cell`` 为值对象：``dataclass`` 默认 ``__eq__`` 按字段逐一比较，使 round-trip
    等值判定（``transpose(transpose(g)) == g``）与对象身份无关。
    """

    value: Any = None
    addr_id: str | None = None


@dataclass
class Grid:
    """行列交叉结果网格。

    - ``row_labels``：行标签（长度 ``R``）。
    - ``col_labels``：列标签（长度 ``C``）。
    - ``cells``：``R × C`` 二维矩阵，``cells[r][c]`` 为第 ``r`` 行第 ``c`` 列的 ``Cell``。

    不变式：``len(cells) == len(row_labels)`` 且每行 ``len(cells[r]) == len(col_labels)``。
    由 ``pivot()`` 与客户端转置构造的 ``Grid`` 均满足该不变式。
    """

    row_labels: list[str] = field(default_factory=list)
    col_labels: list[str] = field(default_factory=list)
    cells: list[list[Cell]] = field(default_factory=list)

    # ── 维度 ──────────────────────────────────────────────────────────────
    @property
    def n_rows(self) -> int:
        return len(self.row_labels)

    @property
    def n_cols(self) -> int:
        return len(self.col_labels)

    # ── 序列化辅助（供导出/缓存/前端契约复用）──────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        """转为纯 ``dict``（``cells`` 内为 ``{value, addr_id}``）。"""
        return {
            "row_labels": list(self.row_labels),
            "col_labels": list(self.col_labels),
            "cells": [
                [{"value": c.value, "addr_id": c.addr_id} for c in row]
                for row in self.cells
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Grid":
        """从 ``to_dict`` 形态还原 ``Grid``。"""
        return cls(
            row_labels=list(data.get("row_labels", []) or []),
            col_labels=list(data.get("col_labels", []) or []),
            cells=[
                [
                    Cell(
                        value=(c or {}).get("value"),
                        addr_id=(c or {}).get("addr_id"),
                    )
                    for c in (row or [])
                ]
                for row in (data.get("cells", []) or [])
            ],
        )


@dataclass
class PivotConfig:
    """透视配置（design.md §Components 5 PivotEngine）。

    - ``row_dims``：行维度字段名清单（可空 → 单一聚合行）。
    - ``col_dims``：列维度字段名清单（可空 → 单一值列）。
    - ``value_field``：被聚合的值字段名（``count`` 计数可为空）。
    - ``agg``：聚合方式，∈ sum/count/avg/min/max（与 GroupingEngine 白名单一致）。
    - ``max_cols``：列基数上限（默认 512，R6.4）。

    与 ``query_orchestrator.PivotConfig`` 字段同名同义；``pivot()`` 以鸭子类型接受
    二者之一（读取 ``row_dims`` / ``col_dims`` / ``value_field`` / ``agg`` 属性），
    避免与编排层产生循环依赖。
    """

    row_dims: list[str] = field(default_factory=list)
    col_dims: list[str] = field(default_factory=list)
    value_field: str | None = None
    agg: str = "sum"
    max_cols: int = 512


#: 默认承载源格 ``addr_id`` 的行字段名（cell-fetch 结果按此键携带源格身份）
DEFAULT_ADDR_ID_KEY = "addr_id"


class PivotEngine:
    """转置/透视引擎。

    - ``transpose``（Task 10.1）：整表行列互换，对称纯函数保证 round-trip。
    - ``pivot``（Task 10.2）：交叉透视 + 列基数上限 + addr_id 单源保留 + 空组合空值。
    """

    def transpose(self, grid: Grid) -> Grid:
        """整表行列互换（R6.2），对称纯函数保证 round-trip（R6.3）。

        语义
        ----
        - 新行标签 = 原列标签；新列标签 = 原行标签。
        - 新矩阵 ``out[c][r] = grid.cells[r][c]``（矩阵转置）。

        实现为**对称纯函数**：
        - 维度以标签长度为准（``R = len(row_labels)``、``C = len(col_labels)``），
          从而对「空数据但有标签」等退化形态亦保持严格 round-trip
          （``transpose(transpose(g)) == g`` 在值 / 行标签 / 列标签 / 行列顺序上完全一致）。
        - 不修改入参（``row_labels`` / ``col_labels`` 复制新列表，``Cell`` 以 ``replace``
          产生浅拷贝），无 IO、无 async。
        - 对越界/缺失单元格以空 ``Cell`` 兜底，函数为全函数（不抛异常）。

        参数
        ----
        grid:
            满足 ``R × C`` 不变式的结果网格。

        返回
        ----
        转置后的新 ``Grid``（``C × R``）。
        """
        r_count = len(grid.row_labels)
        c_count = len(grid.col_labels)

        transposed: list[list[Cell]] = [
            [self._cell_at(grid.cells, r, c) for r in range(r_count)]
            for c in range(c_count)
        ]

        return Grid(
            row_labels=list(grid.col_labels),
            col_labels=list(grid.row_labels),
            cells=transposed,
        )

    @staticmethod
    def _cell_at(cells: list[list[Cell]], r: int, c: int) -> Cell:
        """安全读取 ``cells[r][c]``；越界/缺失 → 空 ``Cell``。

        以 ``replace`` 产生浅拷贝，确保 ``transpose`` 不与入参共享可变 ``Cell`` 引用
        （纯函数）；``Cell`` 字段为不可变标量，浅拷贝已足够隔离。
        """
        if 0 <= r < len(cells):
            row = cells[r]
            if 0 <= c < len(row):
                return replace(row[c])
        return Cell(value=None, addr_id=None)

    # ── 透视（Task 10.2）─────────────────────────────────────────────────
    def pivot(
        self,
        rows: list[dict[str, Any]],
        cfg: Any,
        *,
        max_cols: int = 512,
        addr_id_key: str = DEFAULT_ADDR_ID_KEY,
    ) -> Grid:
        """将平铺 ``rows`` 按 ``cfg`` 透视为行列交叉表 ``Grid``。

        语义（design.md §Components 5，R6.1/6.4/6.5/6.6/6.7）
        ----------------------------------------------------------------
        - 行维度 ``cfg.row_dims`` 的唯一值组合 → 行；列维度 ``cfg.col_dims`` 的唯一
          值组合 → 列；行 / 列标签均按维度组合**升序**排序。
        - 落入同一交叉单元格 ``(row_combo, col_combo)`` 的多个源行按 ``cfg.agg``
          聚合（sum/count/avg/min/max，复用 GroupingEngine 参考实现，P7 一致）。
        - **列基数上限**（R6.4）：列组合数 > ``max_cols`` → ``HTTPException(400,
          PIVOT_COL_LIMIT)``（含 ``actual`` / ``limit``），在**构建网格之前**校验，
          不执行透视、不返回部分结果。
        - **addr_id 保留**（R6.5/6.6）：交叉单元格恰由**单一源行**产生 → 携带该源行
          的 ``addr_id``（若源行未携带则为 ``None``）；由**多源聚合**产生 → ``None``
          （不可下钻）。
        - **空组合**（R6.7）：行 × 列组合在源数据中无对应源行 → 单元格值为 ``None``
          （非 0、非报错），addr_id 为 ``None``。

        参数
        ----
        rows:
            平铺结果行（``list[dict]``）；每行含各维度字段、``cfg.value_field`` 值，
            并可选携带 ``addr_id_key`` 键作为源格身份。
        cfg:
            透视配置（``PivotConfig`` 或字段同名的鸭子类型，如
            ``query_orchestrator.PivotConfig``）。
        max_cols:
            列基数上限（关键字参数，默认 512，R6.4）。
        addr_id_key:
            源行中承载 ``addr_id`` 的键名（默认 ``"addr_id"``）。

        返回
        ----
        透视后的 ``Grid``（满足 ``R × C`` 不变式）。

        错误
        ----
        列组合数超上限 → ``HTTPException(400, PIVOT_COL_LIMIT)``。
        """
        rows = list(rows or [])
        row_dims = list(getattr(cfg, "row_dims", []) or [])
        col_dims = list(getattr(cfg, "col_dims", []) or [])
        value_field = getattr(cfg, "value_field", None)
        agg = str(getattr(cfg, "agg", "sum") or "sum").lower()

        # ── 唯一行 / 列组合（升序），列基数校验在构建网格之前 ──
        row_keys = self._distinct_combos(rows, row_dims)
        col_keys = self._distinct_combos(rows, col_dims)

        # ── R6.4：列基数上限（先于任何网格构建）──
        actual_cols = len(col_keys)
        if actual_cols > max_cols:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "PIVOT_COL_LIMIT",
                    "message": (
                        f"透视列维度基数 {actual_cols} 超过上限 {max_cols}，"
                        "列维度基数过大，已中止透视"
                    ),
                    "actual": actual_cols,
                    "limit": max_cols,
                },
            )

        # ── 按 (row_combo, col_combo) 分桶源行 ──
        buckets: dict[tuple, list[dict[str, Any]]] = {}
        for row in rows:
            rk = tuple(row.get(d) for d in row_dims)
            ck = tuple(row.get(d) for d in col_dims)
            buckets.setdefault((rk, ck), []).append(row)

        agg_spec = _GroupAgg(field=(value_field or ""), func=agg)

        # ── 构建 R×C 交叉网格 ──
        cells: list[list[Cell]] = []
        for rk in row_keys:
            out_row: list[Cell] = []
            for ck in col_keys:
                sources = buckets.get((rk, ck))
                out_row.append(self._cross_cell(sources, agg_spec, addr_id_key))
            cells.append(out_row)

        return Grid(
            row_labels=[self._combo_label(rk, row_dims, "行") for rk in row_keys],
            col_labels=[
                self._combo_label(ck, col_dims, value_field or "值")
                for ck in col_keys
            ],
            cells=cells,
        )

    # ── 透视内部辅助 ─────────────────────────────────────────────────────
    def _distinct_combos(
        self, rows: list[dict[str, Any]], dims: list[str]
    ) -> list[tuple]:
        """源行中 ``dims`` 的唯一值组合，按维度组合升序排序。

        - 无维度（``dims`` 为空）→ 单一空组合 ``[()]``（单一聚合行 / 单一值列）。
        - 有维度但无源行 → 空列表（无行 / 无列）。
        """
        if not dims:
            return [()]
        seen: dict[tuple, None] = {}
        for row in rows:
            seen.setdefault(tuple(row.get(d) for d in dims), None)
        return sorted(
            seen.keys(),
            key=lambda combo: tuple(_sort_key(v) for v in combo),
        )

    def _cross_cell(
        self,
        sources: list[dict[str, Any]] | None,
        agg_spec: _GroupAgg,
        addr_id_key: str,
    ) -> Cell:
        """构造单个交叉单元格。

        - 无源行（``sources`` 为 None/空）→ 空值 ``None``、addr_id ``None``（R6.7）。
        - 恰一源行 → 值 = 聚合（等价该单值），addr_id = 该源行 ``addr_id``（R6.5）。
        - 多源行 → 值 = 聚合，addr_id = ``None``（不可下钻，R6.6）。
        """
        if not sources:
            return Cell(value=None, addr_id=None)

        value = _GroupingEngine._compute_agg(agg_spec, sources)
        if len(sources) == 1:
            return Cell(value=value, addr_id=sources[0].get(addr_id_key))
        return Cell(value=value, addr_id=None)

    @staticmethod
    def _combo_label(combo: tuple, dims: list[str], fallback: str) -> str:
        """维度组合 → 显示标签字符串。

        - 空组合（无维度）→ ``fallback``（如 value_field 名 / "行"）。
        - 多维度组合 → 各维度值以 " / " 连接。
        """
        if not combo:
            return fallback
        return " / ".join("" if v is None else str(v) for v in combo)
