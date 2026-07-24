"""NoteFormulaEvaluator — 附注表内公式求值编排层（Wave 2 / Task 3.1）.

Spec:   .kiro/specs/disclosure-note-formula-and-report-sync/ Wave2 (Task 3.1)
Design: 决策1（复用既有内核不新造求值器）+ NoteFormulaEvaluator 薄编排层
Reqs:   1.1 / 1.4 / 1.5 / 3.2 / 8.2

职责（薄编排）
--------------
遍历 note ``table_data`` 各单元格，对"公式驱动"（``_cell_modes[str(col)]`` 非
manual/locked 且 binding.source ∈ formula-family）单元格做**第二遍求值回填**。

为什么需要第二遍
----------------
``disclosure_engine._build_with_binding`` 首遍逐格 ``dispatch_resolver`` 取数，
但 **公式家族 source（sum/report/aging）** 依赖同表其它单元格 / 报表数在首遍
建好后才能算（合计=分项之和 需分项先落值；report 需报表数据），且 Wave1 的
``dispatch_resolver`` 并未注册 sum/report/aging（它们由 ``resolve_formula`` 直接
承载），故首遍这些单元格拿不到值。本编排层在首遍之后再跑一遍专门解算它们。

契约
----
- 仅回填 ``_cell_modes[str(col)]`` 非 manual/locked 的公式家族单元格
  （manual/locked 一律**保留原值**，Property 6）。
- 数据源单元格（trial_balance/ledger_sum/... 首遍已取数）**不重复求值**
  （source 不在 formula-family → 跳过，避免二次 DB 查询）。
- 单元格级 **fail-open**：任一格求值异常 → 保留原值 + 记 issue，不中断整表
  （Req1.4 / 8.2）。
- **幂等**：相同 table_data + ctx 二次求值结果一致（Req1.5）。
- 返回**新 table_data**（deepcopy，不就地改），便于后续 ``note_cell_merge``
  合并保留 manual/locked。
- 支持多表 ``_tables``。

灰度（零回归）
--------------
公式家族 resolver（``resolve_formula`` / ``resolve_prior_year_note`` value 模式）
内部已受 ``DISCLOSURE_NOTE_FORMULA_ENABLED`` 约束（关闭一律返 None）→ 关闭时本
编排逐格得 None → **保留原值** → 逐字节零回归（Property 12）。调用方另在开关关时
旁路（Task 3.2），避免无谓的遍历/deepcopy。

binding 从何而来
----------------
优先取单元格内嵌 binding（``_cell_meta[str(col)]["binding"]`` — Design 的
Cell_Binding 前向模型，单测走此路径）；否则经 ctx 提供的 ``_cell_binding_resolver``
回调重建（集成路径复用 ``disclosure_engine._resolve_cell_binding``，不重复造
binding 解析）。都取不到 → 该格无操作（Req："无 binding 元数据则无操作"）。
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)

# 公式家族 source —— 需第二遍解算的单元格（sum/report/aging 依赖同表/报表；
# prior_year_note value 模式为单元格级取上年数）。数据源 source（trial_balance
# 等）首遍已取数，不在此集合，evaluate_table 一律跳过不重复求值。
FORMULA_FAMILY_SOURCES: frozenset[str] = frozenset(
    {"sum", "report", "aging", "prior_year_note"}
)

# dispatch_resolver 未注册 sum/report/aging（Wave1 由 resolve_formula 直接承载），
# 故这三者路由到 resolve_formula；其余（prior_year_note 等）走 dispatch_resolver。
_RESOLVE_FORMULA_DIRECT: frozenset[str] = frozenset({"sum", "report", "aging"})


class NoteFormulaEvaluator:
    """附注表内公式求值编排层（无状态外部依赖，每次 evaluate_table 重置 issues）。"""

    def __init__(self) -> None:
        # 最近一次 evaluate_table 记录的单元格级求值异常（可选观测，非必需）
        self.issues: list[dict[str, Any]] = []

    async def evaluate_table(
        self,
        table_data: dict[str, Any] | None,
        ctx: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """遍历 table_data 公式家族单元格 → 求值回填，返回新 table_data。

        - 不就地修改入参（deepcopy）。
        - 单表 / 多表（``_tables``）自动识别；多表时把 ``_tables[0]`` 的
          headers/rows 镜像到顶层（兼容前端老代码读 ``table_data.rows``）。
        - table_data 非 dict → 原样返回。
        """
        self.issues = []
        if not isinstance(table_data, dict):
            return table_data

        result = deepcopy(table_data)
        base_ctx = dict(ctx) if isinstance(ctx, dict) else {}

        tables = result.get("_tables")
        if isinstance(tables, list) and tables:
            for t_idx, tbl in enumerate(tables):
                if isinstance(tbl, dict):
                    await self._evaluate_single_table(tbl, base_ctx, t_idx)
            first = tables[0]
            if isinstance(first, dict):
                # 镜像首表到顶层（与 note_cell_merge 同款兼容处理）
                result["headers"] = deepcopy(first.get("headers", []))
                result["rows"] = deepcopy(first.get("rows", []))
                if "name" in first:
                    result["name"] = first.get("name", "")
        else:
            await self._evaluate_single_table(result, base_ctx, 0)

        return result

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    async def _evaluate_single_table(
        self,
        table: dict[str, Any],
        base_ctx: dict[str, Any],
        table_index: int,
    ) -> None:
        """就地解算单张表的公式家族单元格（table 是 result 内的深拷贝子对象）。"""
        rows = table.get("rows")
        if not isinstance(rows, list):
            return

        # per-table ctx：暴露当前单表供 sum source 反查兄弟单元格
        # （resolve_formula 的 _current_cell_value 读 ctx["table_data"]）。
        # 传入的是单张表 dict（含 rows），故 table_index 归零。
        cell_ctx = dict(base_ctx)
        cell_ctx["table_data"] = table
        cell_ctx["table_index"] = 0

        for r_idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            values = row.get("values")
            if not isinstance(values, list):
                continue
            cell_modes = row.get("_cell_modes")
            cell_modes = cell_modes if isinstance(cell_modes, dict) else {}
            label = row.get("label", "") or ""

            for c_idx in range(len(values)):
                mode = cell_modes.get(str(c_idx))
                # Property 6：manual / locked 一律保留原值，不覆盖。
                if mode in ("manual", "locked"):
                    continue
                try:
                    binding = self._cell_binding(row, table_index, c_idx, base_ctx)
                    if not isinstance(binding, dict):
                        continue
                    source = binding.get("source")
                    if source not in FORMULA_FAMILY_SOURCES:
                        # 数据源单元格首遍已取数 —— 跳过不重复求值。
                        continue
                    new_val = await self._resolve(binding, cell_ctx)
                    # fail-open / 缺数据：None → 保留原值（零回归）。
                    if new_val is not None:
                        values[c_idx] = new_val
                except Exception as err:  # 单元格级 fail-open — 保留原值，不中断整表
                    self.issues.append(
                        {
                            "table_index": table_index,
                            "row": r_idx,
                            "col": c_idx,
                            "label": label,
                            "error": str(err),
                        }
                    )
                    logger.warning(
                        "NoteFormulaEvaluator: cell (t=%s r=%s c=%s label=%s) "
                        "raised %s; keeping original value (fail-open)",
                        table_index, r_idx, c_idx, label, err,
                    )

    @staticmethod
    def _cell_binding(
        row: dict[str, Any],
        table_index: int,
        col_idx: int,
        ctx: dict[str, Any],
    ) -> dict[str, Any] | None:
        """取该格 binding：内嵌 ``_cell_meta[col].binding`` 优先 → ctx 回调重建。

        ctx 回调 ``_cell_binding_resolver`` 签名：
            ``(table_index, label, col_idx, cell_meta) -> dict | None``
        集成路径包一层 ``disclosure_engine._resolve_cell_binding``（不重复造解析）。
        """
        meta = row.get("_cell_meta")
        if isinstance(meta, dict):
            slot = meta.get(str(col_idx))
            if isinstance(slot, dict) and isinstance(slot.get("binding"), dict):
                return slot["binding"]

        provider = ctx.get("_cell_binding_resolver")
        if callable(provider):
            try:
                b = provider(
                    table_index,
                    row.get("label", "") or "",
                    col_idx,
                    meta if isinstance(meta, dict) else {},
                )
                return b if isinstance(b, dict) else None
            except Exception:
                # 回调异常不得冒泡 — 视为无 binding
                return None
        return None

    @staticmethod
    async def _resolve(binding: dict[str, Any], ctx: dict[str, Any]) -> Any:
        """路由：sum/report/aging → resolve_formula（Wave1 直调 API）；
        其余（prior_year_note 等）→ dispatch_resolver（现有分发器，语义不改）。

        两条路径均 fail-open（内部 try/except，返 None 不抛）。
        """
        from app.services.note_source_resolvers import (
            dispatch_resolver,
            resolve_formula,
        )

        source = binding.get("source")
        if source in _RESOLVE_FORMULA_DIRECT:
            return await resolve_formula(binding, ctx)
        return await dispatch_resolver(binding, ctx)


__all__ = ["NoteFormulaEvaluator", "FORMULA_FAMILY_SOURCES"]
