"""自定义取数引擎 — 支持跳行跳列、任选单元格、溯源跳转

核心能力：
1. 自定义取数规则：用户可任选源表（底稿/试算表/报表/附注）的任意单元格
2. 跳行跳列：不要求连续区域，支持离散单元格组合
3. 溯源链路：每个取数结果记录完整来源路径，支持双向跳转
4. 可视选择：前端通过表格点选生成取数规则，后端存储+执行

═══ 取数规则定义格式 ═══
{
    "rule_id": "uuid",
    "target": {"type": "note", "section": "五、1", "row": 0, "col": 1},
    "source": {"type": "trial_balance", "account_code": "1001", "field": "audited_amount"},
    "transform": "direct",  // direct|negate|abs|percentage
    "description": "货币资金期末余额取自试算表1001审定数"
}

═══ 溯源记录格式 ═══
{
    "trace_id": "uuid",
    "target_location": "note:五、1:0:1",
    "source_location": "trial_balance:1001:audited_amount",
    "value": "1234567.89",
    "fetched_at": "2025-01-15T10:30:00",
    "rule_id": "uuid"
}
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance

_logger = logging.getLogger(__name__)


# ═══ 数据源类型 ═══

class SourceType:
    TRIAL_BALANCE = "trial_balance"
    REPORT = "report"
    NOTE = "note"
    WORKPAPER = "workpaper"
    AUX_BALANCE = "aux_balance"
    LEDGER = "ledger"


# ═══ 变换类型 ═══

class Transform:
    DIRECT = "direct"          # 直接取值
    NEGATE = "negate"          # 取反（借贷方向转换）
    ABS = "abs"                # 绝对值
    PERCENTAGE = "percentage"  # 百分比（÷100）
    SUM = "sum"                # 多源求和
    DIFF = "diff"              # 两源相减


# ═══ 取数规则定义 ═══

class FetchRule:
    """单条取数规则

    统一格式：与 note_formula_generator 的 _formulas 兼容。
    预设公式可通过 from_note_formula() 转换为 FetchRule。
    """

    def __init__(self, data: dict):
        self.rule_id = data.get("rule_id", str(uuid.uuid4()))
        self.target = data.get("target", {})
        self.sources = data.get("sources", [])  # 支持多源
        # 兼容单源格式
        if not self.sources and "source" in data:
            self.sources = [data["source"]]
        self.transform = data.get("transform", Transform.DIRECT)
        self.description = data.get("description", "")
        self.created_by = data.get("created_by")
        self.created_at = data.get("created_at", datetime.now(timezone.utc).isoformat())
        # 来源标记（preset=预设公式/custom=用户自定义）
        self.origin = data.get("origin", "custom")

    @classmethod
    def from_note_formula(cls, key: str, formula_def: dict, note_section: str) -> "FetchRule":
        """从 note_formula_generator 的 _formulas 格式转换

        key 格式: "row_idx:col_idx"
        formula_def: {"type": "vertical_sum", "expression": "SUM(0:2, 1)", ...}
        """
        parts = key.split(":")
        row_idx = int(parts[0]) if len(parts) > 0 else 0
        col_idx = int(parts[1]) if len(parts) > 1 else 0

        return cls({
            "rule_id": f"preset_{note_section}_{key}",
            "target": {"type": "note", "section": note_section, "row": row_idx, "col": col_idx},
            "sources": [{"type": "note_internal", "expression": formula_def.get("expression", "")}],
            "transform": Transform.DIRECT,
            "description": formula_def.get("description", ""),
            "origin": "preset",
        })

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "target": self.target,
            "sources": self.sources,
            "transform": self.transform,
            "description": self.description,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "origin": self.origin,
        }


# ═══ 溯源记录 ═══

class TraceRecord:
    """取数溯源记录"""

    def __init__(
        self,
        target_location: str,
        source_location: str,
        value: str,
        rule_id: str,
    ):
        self.trace_id = str(uuid.uuid4())
        self.target_location = target_location
        self.source_location = source_location
        self.value = value
        self.rule_id = rule_id
        self.fetched_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "target_location": self.target_location,
            "source_location": self.source_location,
            "value": self.value,
            "rule_id": self.rule_id,
            "fetched_at": self.fetched_at,
        }


# ═══ 自定义取数服务 ═══

class CustomFetchService:
    """自定义取数引擎

    支持：
    - 跳行跳列任选单元格
    - 多源组合（SUM/DIFF）
    - 溯源链路记录
    - 双向跳转（目标→源、源→目标）
    """

    def __init__(self, db: AsyncSession, project_id: UUID, year: int):
        self.db = db
        self.project_id = project_id
        self.year = year
        self._traces: list[TraceRecord] = []

    async def execute_rule(self, rule: FetchRule) -> dict[str, Any]:
        """执行单条取数规则，返回计算结果+溯源记录"""
        values = []
        source_locations = []

        for source in rule.sources:
            val = await self._fetch_from_source(source)
            values.append(val)
            source_locations.append(self._format_source_location(source))

        # 应用变换
        result = self._apply_transform(values, rule.transform)

        # 生成溯源记录
        target_loc = self._format_target_location(rule.target)
        for src_loc in source_locations:
            trace = TraceRecord(
                target_location=target_loc,
                source_location=src_loc,
                value=str(result) if result is not None else "",
                rule_id=rule.rule_id,
            )
            self._traces.append(trace)

        return {
            "rule_id": rule.rule_id,
            "value": float(result) if result is not None else None,
            "target": target_loc,
            "sources": source_locations,
            "traces": [t.to_dict() for t in self._traces[-len(source_locations):]],
        }

    async def execute_rules(self, rules: list[dict]) -> dict[str, Any]:
        """批量执行取数规则"""
        results = []
        for rule_data in rules:
            rule = FetchRule(rule_data)
            result = await self.execute_rule(rule)
            results.append(result)

        # 持久化溯源记录到项目配置
        await self._persist_traces()

        return {
            "executed": len(results),
            "results": results,
            "traces": [t.to_dict() for t in self._traces],
        }

    async def _persist_traces(self):
        """持久化溯源记录到 Project.wizard_state.fetch_trace_history"""
        if not self._traces:
            return
        try:
            from app.models.core import Project
            from sqlalchemy.orm.attributes import flag_modified

            project = (await self.db.execute(
                sa.select(Project).where(Project.id == self.project_id)
            )).scalar_one_or_none()
            if not project:
                return

            ws = project.wizard_state or {}
            history = ws.get("fetch_trace_history", [])

            # 追加新记录（保留最近500条）
            for t in self._traces:
                history.append(t.to_dict())
            if len(history) > 500:
                history = history[-500:]

            ws["fetch_trace_history"] = history
            project.wizard_state = ws
            flag_modified(project, "wizard_state")
            await self.db.flush()
        except Exception as e:
            _logger.warning("persist traces failed: %s", e)

    def get_traces(self) -> list[dict]:
        """获取所有溯源记录"""
        return [t.to_dict() for t in self._traces]

    # ═══ 溯源查询 ═══

    async def trace_target(self, target_location: str, rules: list[dict]) -> list[dict]:
        """正向溯源：目标单元格 → 数据来源

        用户点击附注/底稿中的某个数值，显示它的数据来源。
        """
        traces = []
        for rule_data in rules:
            rule = FetchRule(rule_data)
            target_loc = self._format_target_location(rule.target)
            if target_loc == target_location:
                for source in rule.sources:
                    traces.append({
                        "rule_id": rule.rule_id,
                        "source": source,
                        "source_location": self._format_source_location(source),
                        "description": rule.description,
                        "jump_url": self._build_jump_url(source),
                    })
        return traces

    async def trace_source(self, source_location: str, rules: list[dict]) -> list[dict]:
        """反向溯源：数据来源 → 引用它的目标

        用户在试算表/底稿中修改数据后，显示哪些附注/报表引用了它。
        """
        targets = []
        for rule_data in rules:
            rule = FetchRule(rule_data)
            for source in rule.sources:
                if self._format_source_location(source) == source_location:
                    targets.append({
                        "rule_id": rule.rule_id,
                        "target": rule.target,
                        "target_location": self._format_target_location(rule.target),
                        "description": rule.description,
                        "jump_url": self._build_jump_url_target(rule.target),
                    })
        return targets

    # ═══ 内部方法 ═══

    async def _fetch_from_source(self, source: dict) -> Decimal | None:
        """从指定数据源取值"""
        src_type = source.get("type", "")

        if src_type == SourceType.TRIAL_BALANCE:
            return await self._fetch_trial_balance(source)
        elif src_type == SourceType.REPORT:
            return await self._fetch_report(source)
        elif src_type == SourceType.NOTE:
            return await self._fetch_note(source)
        elif src_type == SourceType.AUX_BALANCE:
            return await self._fetch_aux_balance(source)
        elif src_type == SourceType.WORKPAPER:
            return await self._fetch_workpaper(source)
        else:
            _logger.warning("unknown source type: %s", src_type)
            return None

    async def _fetch_trial_balance(self, source: dict) -> Decimal | None:
        """从试算表取数 — 支持任意科目+任意字段"""
        account_code = source.get("account_code", "")
        field = source.get("field", "audited_amount")

        result = await self.db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == self.project_id,
                TrialBalance.year == self.year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        val = getattr(row, field, None)
        return Decimal(str(val)) if val is not None else None

    async def _fetch_report(self, source: dict) -> Decimal | None:
        """从报表取数 — 支持任意报表行+任意列"""
        from app.models.report_models import FinancialReport
        row_code = source.get("row_code", "")
        # 报表数据存在 financial_report 表
        result = await self.db.execute(
            sa.select(FinancialReport).where(
                FinancialReport.project_id == self.project_id,
                FinancialReport.year == self.year,
                FinancialReport.row_code == row_code,
                FinancialReport.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        # 默认取 amount 字段
        field = source.get("field", "amount")
        val = getattr(row, field, None)
        return Decimal(str(val)) if val is not None else None

    async def _fetch_note(self, source: dict) -> Decimal | None:
        """从其他附注取数 — 支持跳行跳列"""
        from app.models.report_models import DisclosureNote
        section = source.get("section", "")
        row_idx = source.get("row", 0)
        col_idx = source.get("col", 0)

        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == self.project_id,
                DisclosureNote.year == self.year,
                DisclosureNote.note_section == section,
            )
        )
        note = result.scalar_one_or_none()
        if not note or not note.table_data:
            return None

        rows = note.table_data.get("rows", [])
        if row_idx < len(rows):
            values = rows[row_idx].get("values", [])
            if col_idx < len(values) and values[col_idx] is not None:
                return Decimal(str(values[col_idx]))
        return None

    async def _fetch_aux_balance(self, source: dict) -> Decimal | None:
        """从辅助余额表取数"""
        from app.models.audit_platform_models import TbAuxBalance
        account_code = source.get("account_code", "")
        aux_code = source.get("aux_code", "")
        field = source.get("field", "closing_balance")

        query = sa.select(TbAuxBalance).where(
            TbAuxBalance.project_id == self.project_id,
            TbAuxBalance.year == self.year,
            TbAuxBalance.account_code == account_code,
            TbAuxBalance.is_deleted == sa.false(),
        )
        if aux_code:
            query = query.where(TbAuxBalance.aux_code == aux_code)

        result = await self.db.execute(query.limit(1))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        val = getattr(row, field, None)
        return Decimal(str(val)) if val is not None else None

    async def _fetch_workpaper(self, source: dict) -> Decimal | None:
        """从底稿 parsed_data 取数"""
        from app.models.workpaper_models import WorkingPaper, WpIndex
        wp_code = source.get("wp_code", "")
        data_key = source.get("data_key", "audited_amount")

        # 查找底稿
        result = await self.db.execute(
            sa.select(WorkingPaper)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WpIndex.project_id == self.project_id,
                WpIndex.wp_code == wp_code,
                WorkingPaper.is_deleted == sa.false(),
            )
            .limit(1)
        )
        wp = result.scalar_one_or_none()
        if not wp or not wp.parsed_data:
            return None

        val = wp.parsed_data.get(data_key)
        if val is not None:
            try:
                return Decimal(str(val))
            except Exception:
                return None
        return None

    def _apply_transform(self, values: list[Decimal | None], transform: str) -> Decimal | None:
        """应用变换"""
        # 过滤 None
        valid = [v for v in values if v is not None]
        if not valid:
            return None

        if transform == Transform.DIRECT:
            return valid[0]
        elif transform == Transform.NEGATE:
            return -valid[0]
        elif transform == Transform.ABS:
            return abs(valid[0])
        elif transform == Transform.PERCENTAGE:
            return valid[0] / Decimal("100")
        elif transform == Transform.SUM:
            return sum(valid, Decimal("0"))
        elif transform == Transform.DIFF:
            if len(valid) >= 2:
                return valid[0] - valid[1]
            return valid[0]
        else:
            return valid[0]

    def _format_target_location(self, target: dict) -> str:
        """格式化目标位置为可读字符串"""
        t = target.get("type", "")
        if t == "note":
            return f"note:{target.get('section', '')}:{target.get('row', 0)}:{target.get('col', 0)}"
        elif t == "workpaper":
            return f"workpaper:{target.get('wp_code', '')}:{target.get('sheet', '')}:{target.get('cell', '')}"
        elif t == "report":
            return f"report:{target.get('row_code', '')}:{target.get('col', '')}"
        return f"{t}:{target}"

    def _format_source_location(self, source: dict) -> str:
        """格式化数据源位置"""
        t = source.get("type", "")
        if t == SourceType.TRIAL_BALANCE:
            return f"trial_balance:{source.get('account_code', '')}:{source.get('field', '')}"
        elif t == SourceType.REPORT:
            return f"report:{source.get('row_code', '')}:{source.get('field', '')}"
        elif t == SourceType.NOTE:
            return f"note:{source.get('section', '')}:{source.get('row', 0)}:{source.get('col', 0)}"
        elif t == SourceType.AUX_BALANCE:
            return f"aux_balance:{source.get('account_code', '')}:{source.get('aux_code', '')}:{source.get('field', '')}"
        elif t == SourceType.WORKPAPER:
            return f"workpaper:{source.get('wp_code', '')}:{source.get('data_key', '')}"
        return f"{t}:{source}"

    def _build_jump_url(self, source: dict) -> str:
        """构建跳转URL（前端路由）"""
        t = source.get("type", "")
        pid = str(self.project_id)
        if t == SourceType.TRIAL_BALANCE:
            return f"/projects/{pid}/trial-balance?highlight={source.get('account_code', '')}"
        elif t == SourceType.REPORT:
            return f"/projects/{pid}/reports?row={source.get('row_code', '')}"
        elif t == SourceType.NOTE:
            return f"/projects/{pid}/disclosure-notes?section={source.get('section', '')}"
        elif t == SourceType.WORKPAPER:
            return f"/projects/{pid}/workpapers?code={source.get('wp_code', '')}"
        elif t == SourceType.AUX_BALANCE:
            return f"/projects/{pid}/ledger?tab=aux&account={source.get('account_code', '')}"
        return ""

    def _build_jump_url_target(self, target: dict) -> str:
        """构建目标跳转URL"""
        t = target.get("type", "")
        pid = str(self.project_id)
        if t == "note":
            return f"/projects/{pid}/disclosure-notes?section={target.get('section', '')}"
        elif t == "workpaper":
            return f"/projects/{pid}/workpapers?code={target.get('wp_code', '')}"
        elif t == "report":
            return f"/projects/{pid}/reports?row={target.get('row_code', '')}"
        return ""
