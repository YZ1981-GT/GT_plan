"""合并附注子表勾稽校验（spec note-sub-table-formula-and-cross-check Phase 0；R7.5 重做读取与规则）。

规则声明在合并模板各表条目的 ``check_rules``：

- 模式 A 跨表（``mode`` 缺省 ``cross_table``）：本表 ``self_row_label`` 行第 ``self_col_index`` 列 = 同章另一张表
  ``peer_section_id`` 的 ``peer_row_label`` 行第 ``peer_col_index`` 列。两侧须同章节、行唯一、标题行库语义同期间同计量，
  说明写明两侧期间与行（守卫 ``tests/test_consol_note_check_rules_semantics.py``）。
- 模式 B 列平衡（``mode = column_balance``）：变动表逐行 期初 + Σ增加 − Σ减少 = 期末。期初 / 期末 / 增减列不在种子里写，
  一律由标题行库 ``rollforward_columns`` 按表头认；逐行函数 ``consol_note_table_totals.rollforward_balance`` 与「审核」共用。

执行：两张表都读**当前合并节点**已保存的合并附注（``resolve_node_scope`` + ``load_scoped_note_record``，与章节读写同一作用域，
根合并节点没有专属行时兼容读项目级旧行）；单元格转数与合计重算同一口径（``consol_note_table_totals.to_decimal``）。
返回 [{check_id, status, expected, actual, diff, description, reason}]。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.consol_node_scope import NodeScope, load_scoped_note_record, resolve_node_scope
from app.services.consol_note_formula_service import consol_note_tables, find_table
from app.services.consol_note_table_totals import rollforward_balance
from app.services.consol_note_table_totals import to_decimal as _to_decimal
from app.services.note_table_header_library import RollForward, rollforward_columns

logger = logging.getLogger(__name__)


# ─── 数据模型 ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class CheckRule:
    check_id: str
    peer_section_id: str
    peer_row_label: str
    peer_col_index: int
    self_row_label: str
    self_col_index: int
    relation: str  # "equal" | "column_balance"
    tolerance: float
    description: str
    mode: str = "cross_table"  # "cross_table"（模式 A）| "column_balance"（模式 B，列由标题行库认）


@dataclass
class CheckResult:
    check_id: str
    status: str  # "pass" | "fail" | "skipped"
    expected: str | None = None
    actual: str | None = None
    diff: str | None = None
    description: str = ""
    reason: str | None = None

    def to_dict(self) -> dict:
        d = {"check_id": self.check_id, "status": self.status, "description": self.description}
        if self.expected is not None:
            d["expected"] = self.expected
        if self.actual is not None:
            d["actual"] = self.actual
        if self.diff is not None:
            d["diff"] = self.diff
        if self.reason:
            d["reason"] = self.reason
        return d


# ─── 模板加载（合并附注模板，mtime 缓存，与章节接口 / 公式服务同一份） ─────────────────


def _rule_from_dict(r: dict) -> CheckRule:
    """从 JSON dict 构建 CheckRule（模式 A 跨表 / 模式 B 列平衡通用）。"""
    return CheckRule(
        check_id=r["check_id"],
        peer_section_id=r.get("peer_section_id", ""),
        peer_row_label=r.get("peer_row_label", ""),
        peer_col_index=int(r.get("peer_col_index", 0)),
        self_row_label=r.get("self_row_label", ""),
        self_col_index=int(r.get("self_col_index", 0)),
        relation=r.get("relation", "equal"),
        tolerance=float(r.get("tolerance", 0.01)),
        description=r.get("description", ""),
        mode=r.get("mode", "cross_table"),
    )


def _rules_of(entry: dict | None) -> list[CheckRule]:
    raw = entry.get("check_rules") if isinstance(entry, dict) else None
    return [_rule_from_dict(r) for r in raw or [] if isinstance(r, dict) and r.get("check_id")]


def _load_check_rules(template_type: str, section_id: str) -> list[CheckRule]:
    """指定章节的 check_rules（模板不存在 / 章节不存在 / 没有规则 ⇒ 空）。"""
    return _rules_of(find_table(template_type, section_id))


def load_all_check_rules(template_type: str) -> dict[str, list[CheckRule]]:
    """所有章节的 check_rules：{section_id: [CheckRule]}（没有规则的章节不出现）。"""
    return {e["section_id"]: rules for e in consol_note_tables(template_type) if (rules := _rules_of(e))}


def rollforward_for(template_type: str, section_id: str) -> RollForward | None:
    """模式 B 用的期初 / 期末 / 增减列：标题行库按该表模板表头认；不是变动表 ⇒ None。"""
    table = find_table(template_type, section_id)
    return rollforward_columns(table) if table else None


# ─── 单元格定位 ─────────────────────────────────────────────────


def _label(row: Any) -> str:
    if isinstance(row, list) and row:
        return str(row[0]).strip()
    if isinstance(row, dict):
        return str(row.get("label", "")).strip()
    return ""


def _find_row_by_label(rows: list, label: str) -> int | None:
    """按行名（第一列）找行：去半角 / 全角空格后相等，取第一行（规则的行在模板里唯一由守卫保证）。"""
    target = label.replace(" ", "").replace("\u3000", "").strip()
    for i, row in enumerate(rows):
        if _label(row).replace(" ", "").replace("\u3000", "") == target:
            return i
    return None


def _cell_value(rows: list, row_index: int, col_index: int) -> Any:
    """从 rows 中提取指定位置的单元格值（二维行或 ``{label, values}`` 对象行）。"""
    if row_index < 0 or row_index >= len(rows):
        return None
    row = rows[row_index]
    if isinstance(row, list):
        return row[col_index] if 0 <= col_index < len(row) else None
    if isinstance(row, dict):
        values = row.get("values", [])
        if isinstance(values, list) and 0 <= col_index < len(values):
            return values[col_index]
    return None


# ─── 已保存数据 ─────────────────────────────────────────────────


async def _load_note_rows(
    db: AsyncSession, scope: NodeScope, template_type: str, section_id: str, label: str,
) -> tuple[list | None, str | None]:
    """当前节点某章节已保存的合并附注行 → (行, None)；用不了 ⇒ (None, 原因)。``label`` = 「本章节」/「对照章节」。

    读取与章节读写同一函数（``load_scoped_note_record``）：显式节点只读本节点专属行，根合并节点没有专属行时兼容读项目级旧行，
    省略节点 = 项目级旧行。合并附注章节号（「五-5-1」）与单体附注（「八、5」）不是一套，这里不读单体附注。
    已保存数据的列数与模板不同（旧数据）时列号对不上，不校验。
    """
    record = await load_scoped_note_record(db, replace(scope, section_id=section_id))
    data = record.data if record is not None and isinstance(record.data, dict) else {}
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        return None, f"{label} {section_id} 无附注数据"
    headers, template = data.get("headers"), find_table(template_type, section_id)
    width = len(template.get("headers") or []) if template else 0
    if isinstance(headers, list) and headers and width and len(headers) != width:
        return None, f"{label} {section_id} 已保存数据 {len(headers)} 列，与模板 {width} 列不符"
    return rows, None


# ─── 校验 ───────────────────────────────────────────────────────


def _check_column_balance(rule: CheckRule, rows: list, flow: RollForward | None) -> list[CheckResult]:
    """模式 B：变动表逐行 期初 + Σ增加 − Σ减少 = 期末（列由标题行库认，逐行函数与「审核」共用）。

    ``self_row_label`` 为 ``*`` 时逐个有行名的行校验，否则只校验该行；没法勾稽的行（期初 / 期末都没数、方向不定的变动列有数、
    只填了余额）跳过，一行都校验不了时回一条 skipped。
    """
    def skipped(reason: str) -> list[CheckResult]:
        return [CheckResult(check_id=rule.check_id, status="skipped", description=rule.description, reason=reason)]

    if flow is None:
        return skipped("标题行库认不出这张表的期初 / 期末 / 增减列（不是变动表）")
    every = rule.self_row_label == "*"
    if every:
        targets = [(i, _label(r)) for i, r in enumerate(rows) if _label(r)]
    else:
        ri = _find_row_by_label(rows, rule.self_row_label)
        if ri is None:
            return skipped(f"找不到行「{rule.self_row_label}」")
        targets = [(ri, _label(rows[ri]) or rule.self_row_label)]
    tolerance = Decimal(str(rule.tolerance))
    results: list[CheckResult] = []
    for ri, label in targets:
        balance = rollforward_balance(flow, rows[ri]) if isinstance(rows[ri], list) else None
        if balance is None:
            continue
        expected, closing = balance
        diff = abs(expected - closing)
        results.append(CheckResult(
            check_id=f"{rule.check_id}[{label[:15]}]" if every else rule.check_id,
            status="pass" if diff <= tolerance else "fail",
            expected=str(expected), actual=str(closing), diff=None if diff <= tolerance else str(diff),
            description=f"{rule.description}（{label}）" if every else rule.description,
        ))
    return results or skipped("本表没有可勾稽的行（期初 / 期末 / 增减都没填，或方向不定的变动列有数）")


def _check_cross_table(rule: CheckRule, self_rows: list, peer_rows: list) -> CheckResult:
    """模式 A：本表一格 = 对照表一格（容差内）；两格都空算通过，只有一边有数跳过。"""
    def result(status: str, **kw: Any) -> CheckResult:
        return CheckResult(check_id=rule.check_id, status=status, description=rule.description, **kw)

    self_ri = _find_row_by_label(self_rows, rule.self_row_label)
    if self_ri is None:
        return result("skipped", reason=f"本表找不到行「{rule.self_row_label}」")
    peer_ri = _find_row_by_label(peer_rows, rule.peer_row_label)
    if peer_ri is None:
        return result("skipped", reason=f"对照表找不到行「{rule.peer_row_label}」")
    self_val = _to_decimal(_cell_value(self_rows, self_ri, rule.self_col_index))
    peer_val = _to_decimal(_cell_value(peer_rows, peer_ri, rule.peer_col_index))
    if self_val is None and peer_val is None:
        return result("pass")
    if self_val is None or peer_val is None:
        return result("skipped", expected=None if peer_val is None else str(peer_val),
                      actual=None if self_val is None else str(self_val), reason="一方有值另一方为空")
    diff = abs(self_val - peer_val)
    if diff <= Decimal(str(rule.tolerance)):
        return result("pass", expected=str(peer_val), actual=str(self_val))
    return result("fail", expected=str(peer_val), actual=str(self_val), diff=str(diff))


async def check_note_cross_rules(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
    template_type: str,
    *,
    node_key: str | None = None,
) -> list[CheckResult]:
    """执行指定章节的全部 check_rules，返回校验结果列表。

    本表与对照表都读 ``node_key`` 节点已保存的合并附注（省略 = 项目级旧行）；项目 / 年度 / 节点不合法抛
    ``NodeScopeError``（路由转 4xx）。``template_type`` 由调用方按项目实际口径解析（``resolve_note_template_type``）后传入。
    """
    rules = _load_check_rules(template_type, section_id)
    if not rules:
        return []
    scope = await resolve_node_scope(db, project_id, year, node_key, section_id)
    self_rows, self_reason = await _load_note_rows(db, scope, template_type, section_id, "本章节")
    flow = rollforward_for(template_type, section_id) if any(r.mode == "column_balance" for r in rules) else None
    peers: dict[str, tuple[list | None, str | None]] = {}
    results: list[CheckResult] = []
    for rule in rules:
        if self_rows is None:
            results.append(CheckResult(check_id=rule.check_id, status="skipped", description=rule.description,
                                       reason=self_reason))
        elif rule.mode == "column_balance":
            results.extend(_check_column_balance(rule, self_rows, flow))
        else:
            if rule.peer_section_id not in peers:
                peers[rule.peer_section_id] = await _load_note_rows(
                    db, scope, template_type, rule.peer_section_id, "对照章节")
            peer_rows, peer_reason = peers[rule.peer_section_id]
            if peer_rows is None:
                results.append(CheckResult(check_id=rule.check_id, status="skipped", description=rule.description,
                                           reason=peer_reason))
            else:
                results.append(_check_cross_table(rule, self_rows, peer_rows))
    return results
