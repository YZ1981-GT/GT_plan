"""附注 auto_pull 服务 — 跨底稿引用（cross_ref）真实取数.

Spec:   .kiro/specs/disclosure-note-linkage-and-slimdown/
Design: 缺口 2 — cross_ref auto_pull 真实取数
Reqs:   3.1, 3.3

本服务负责按 schema 中 ``cross_refs`` 定义（auto_pull=true, direction=inbound）
从来源底稿/报表/试算表拉取真实值，复用 ``note_source_resolvers.dispatch_resolver``
作为附注模块自有取数内核（不复用 custom_query 的 ``_query_workpaper_cell_range``，
避免 router→router 隐式耦合与 LibreOffice 重负载进热路径）。

取数结果为只读联动值，**不写入 table_data**（不污染手填数据）；
取数失败降级为占位 + 不可用标记，绝不阻断渲染。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class AutoPullResult:
    """单条 cross_ref auto_pull 取数结果.

    Attributes:
        ref_id: cross_ref 的唯一标识（schema 中定义）
        target_wp: 来源底稿编码（如 "D1-1"），可能为 None
        source_label: 溯源标识，如 "D1-1!审定数(期末)" 或 "D1-1!B7"
        value: 拉到的只读联动值（数值/字符串/None）
        available: 取数是否成功
        reason: 不可用原因（available=False 时填写）
    """

    ref_id: str
    target_wp: str | None
    source_label: str
    value: Any | None
    available: bool
    reason: str = ""


class NoteAutoPullService:
    """附注 cross_ref auto_pull 取数服务.

    复用 note_source_resolvers.dispatch_resolver / resolve_wp_data 取真实值，
    manual_override 单元格跳过，取数失败降级为占位 + 不可用标记。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def pull_for_section(
        self,
        project_id: UUID,
        year: int,
        schema: dict,
        *,
        note_table_data: dict | None = None,
    ) -> list[AutoPullResult]:
        """对 schema.cross_refs 中 auto_pull && direction==inbound 的项逐条取数.

        - 预热 _wp_cache（一次加载项目底稿 parsed_data）。
        - 逐 ref：manual_override 检查 → _resolve_binding → dispatch_resolver
          → 成功填值+来源标识 / 失败 available=False+reason。
        - 任一 ref 异常被捕获为 available=False，绝不中断整体。
        - 拉到的值不写入 table_data（只读联动）。

        Requirements: 3.1, 3.2, 3.3, 3.4, 3.7, 3.10
        """
        import sqlalchemy as sa

        from app.models.workpaper_models import WorkingPaper, WpIndex
        from app.services.note_source_resolvers import dispatch_resolver

        results: list[AutoPullResult] = []

        # 1. 提取 auto_pull && direction==inbound 的 cross_refs
        cross_refs = schema.get("cross_refs", [])
        if not isinstance(cross_refs, list):
            cross_refs = []
        qualifying_refs = [
            ref for ref in cross_refs
            if isinstance(ref, dict)
            and ref.get("auto_pull") is True
            and ref.get("direction") == "inbound"
        ]

        if not qualifying_refs:
            return results

        # 2. 预热 _wp_cache：一次加载项目所有底稿 parsed_data，keyed by wp_code
        wp_cache: dict[str, dict] = {}
        try:
            wp_result = await self.db.execute(
                sa.select(
                    WorkingPaper.parsed_data,
                    WpIndex.wp_code,
                )
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(
                    WorkingPaper.project_id == project_id,
                    WorkingPaper.is_deleted == sa.false(),
                    WorkingPaper.parsed_data.isnot(None),
                )
            )
            for parsed_data, wp_code in wp_result.all():
                if wp_code:
                    wp_cache[wp_code] = parsed_data or {}
        except Exception as cache_err:
            logger.warning("pull_for_section: preload wp_cache failed: %s", cache_err)

        # 3. 构建 resolver context
        ctx: dict[str, Any] = {
            "project_id": project_id,
            "year": year,
            "db": self.db,
            "_wp_cache": wp_cache,
        }

        # 4. 逐条处理每个 qualifying ref
        for ref in qualifying_refs:
            try:
                ref_id = ref.get("ref_id", "")
                target_wp = ref.get("target_wp")

                # 4a. manual_override 检查
                if self._is_manual_override(note_table_data, ref):
                    results.append(AutoPullResult(
                        ref_id=ref_id,
                        target_wp=target_wp,
                        source_label="",
                        value=None,
                        available=False,
                        reason="手工模式，跳过自动取数",
                    ))
                    continue

                # 4b. 解析 binding
                binding = self._resolve_binding(ref)
                if binding is None:
                    results.append(AutoPullResult(
                        ref_id=ref_id,
                        target_wp=target_wp,
                        source_label="",
                        value=None,
                        available=False,
                        reason="来源字段无法定位",
                    ))
                    continue

                # 4c. 调用 dispatch_resolver 取值
                value = await dispatch_resolver(binding, ctx)

                # 4d. 构建 source_label 溯源标识
                target_field = ref.get("target_field", "")
                source_cell = ref.get("source_cell", "")
                label_suffix = source_cell if source_cell else target_field
                source_label = (
                    f"{target_wp}!{label_suffix}" if target_wp and label_suffix else (target_wp or "")
                )

                # 4e. 判断取数成功/失败
                if value is not None:
                    results.append(AutoPullResult(
                        ref_id=ref_id,
                        target_wp=target_wp,
                        source_label=source_label,
                        value=value,
                        available=True,
                    ))
                else:
                    results.append(AutoPullResult(
                        ref_id=ref_id,
                        target_wp=target_wp,
                        source_label=source_label,
                        value=None,
                        available=False,
                        reason="来源数据为空",
                    ))

            except Exception as exc:
                # 5. 单条异常被捕获为 available=False，绝不中断整体
                ref_id = ref.get("ref_id", "") if isinstance(ref, dict) else ""
                target_wp = ref.get("target_wp") if isinstance(ref, dict) else None
                results.append(AutoPullResult(
                    ref_id=ref_id,
                    target_wp=target_wp,
                    source_label="",
                    value=None,
                    available=False,
                    reason=f"取数异常: {exc}",
                ))

        return results

    # Excel 单元格引用正则：A1, B7, AA12, $C$3, etc.
    _CELL_REF_PATTERN = re.compile(r"^\$?[A-Z]{1,3}\$?\d+$", re.IGNORECASE)

    def _resolve_binding(self, cross_ref: dict) -> dict | None:
        """将 target_field / source_cell 解析为 resolve_wp_data 可消费的 binding.

        优先级：
        1. 若 cross_ref 显式带 source_cell（Excel 引用如 B7）→ extract:"cell", cell_ref
        2. 否则若有 target_field → extract:"column_sum", value_cols:[target_field]
        3. 映射不到 → 返回 None（上层降级为占位 + 不可用，不报错）

        产出喂给 resolve_wp_data 的 binding dict:
        {source:"wp_data", wp_code, sheet, extract, cell_ref/value_cols}
        """
        if not isinstance(cross_ref, dict):
            return None

        target_wp = cross_ref.get("target_wp")
        if not target_wp or not isinstance(target_wp, str):
            return None

        sheet = cross_ref.get("target_sheet") or ""

        # --- 优先级 1：显式 source_cell ---
        source_cell = cross_ref.get("source_cell")
        if (
            isinstance(source_cell, str)
            and source_cell.strip()
            and self._CELL_REF_PATTERN.match(source_cell.strip())
        ):
            return {
                "source": "wp_data",
                "wp_code": target_wp,
                "sheet": sheet,
                "extract": "cell",
                "cell_ref": source_cell.strip(),
            }

        # --- 优先级 2：target_field → column_sum ---
        target_field = cross_ref.get("target_field")
        if isinstance(target_field, str) and target_field.strip():
            return {
                "source": "wp_data",
                "wp_code": target_wp,
                "sheet": sheet,
                "extract": "column_sum",
                "value_cols": [target_field.strip()],
            }

        # --- 映射不到 ---
        return None

    @staticmethod
    def _is_manual_override(note_table_data: dict | None, ref: dict) -> bool:
        """判断 auto_pull 目标单元格是否被标记 manual.

        判据：table_data.rows[row]._cell_modes[str(col)] != "auto" → 跳过自动取数，
        保留用户手工值。

        Requirements: 3.6
        """
        # 1. note_table_data 为 None 或非 dict → 无数据可查，允许取数
        if note_table_data is None or not isinstance(note_table_data, dict):
            return False

        # 2. 获取 source 定位信息
        source = ref.get("source") if isinstance(ref, dict) else None
        if source is None or not isinstance(source, dict):
            return False

        # 3. 获取 row/column 索引
        row_idx = source.get("row")
        col_idx = source.get("column")
        if row_idx is None or col_idx is None:
            return False

        # 4. 导航到 rows[row_idx]._cell_modes，处理越界等异常
        try:
            rows = note_table_data.get("rows")
            if not isinstance(rows, list):
                return False
            row = rows[row_idx]
            if not isinstance(row, dict):
                return False
            cell_modes = row.get("_cell_modes")
            if not isinstance(cell_modes, dict):
                return False
        except (IndexError, TypeError):
            return False

        # 5. 检查该单元格的模式：非 "auto" 则为手工模式，跳过取数
        mode = cell_modes.get(str(col_idx), "auto")
        return mode != "auto"
