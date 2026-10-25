"""附注子表跨表勾稽校验。

spec: note-sub-table-formula-and-cross-check Phase 0

check_rules 声明格式（合并模板 JSON 中各表条目的可选字段）：
```json
{
  "check_rules": [
    {
      "check_id": "F5-8",
      "peer_section_id": "五-5-1",
      "peer_row_label": "合  计",
      "peer_col_index": 1,
      "self_row_label": "合  计",
      "self_col_index": 1,
      "relation": "equal",
      "tolerance": 0.01,
      "description": "账龄表合计账面余额 = 坏账分类表合计账面余额"
    }
  ]
}
```

校验执行：读两张子表的持久化 disclosure_notes 数据，按 row_label + col_index 定位单元格值，
返回 [{check_id, status, expected, actual, diff, description}]。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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
    mode: str = "cross_table"  # "cross_table" (模式 A) | "column_balance" (模式 B)
    # 模式 B 专用：列驱动变动表的列索引（期初 + 增加 - 减少 = 期末）
    opening_col: int = -1
    increase_col: int = -1
    decrease_col: int = -1
    closing_col: int = -1


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


# ─── 模板加载 ─────────────────────────────────────────────────────


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
        opening_col=int(r.get("opening_col", -1)),
        increase_col=int(r.get("increase_col", -1)),
        decrease_col=int(r.get("decrease_col", -1)),
        closing_col=int(r.get("closing_col", -1)),
    )


def _load_check_rules(template_type: str, section_id: str) -> list[CheckRule]:
    """从合并模板 JSON 加载指定章节的 check_rules。"""
    json_name = f"consol_note_sections_{template_type}.json"
    path = DATA_DIR / json_name
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    for entry in data:
        if entry.get("section_id") != section_id:
            continue
        raw_rules = entry.get("check_rules")
        if not isinstance(raw_rules, list):
            return []
        rules = []
        for r in raw_rules:
            if not isinstance(r, dict) or not r.get("check_id"):
                continue
            rules.append(_rule_from_dict(r))
        return rules
    return []


def load_all_check_rules(template_type: str) -> dict[str, list[CheckRule]]:
    """加载所有章节的 check_rules，返回 {section_id: [CheckRule]}。"""
    json_name = f"consol_note_sections_{template_type}.json"
    path = DATA_DIR / json_name
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, list[CheckRule]] = {}
    for entry in data:
        raw = entry.get("check_rules")
        if not isinstance(raw, list) or not raw:
            continue
        sid = entry.get("section_id", "")
        rules = []
        for r in raw:
            if not isinstance(r, dict) or not r.get("check_id"):
                continue
            rules.append(_rule_from_dict(r))
        if rules:
            result[sid] = rules
    return result


# ─── 单元格值提取 ─────────────────────────────────────────────────


def _to_decimal(value: Any) -> Decimal | None:
    """尝试把任意值转成 Decimal。"""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _find_row_by_label(rows: list, label: str) -> int | None:
    """按行标签（第一列）在 rows 中查找行索引。支持模糊匹配（去空格后比较）。"""
    target = label.replace(" ", "").replace("\u3000", "").strip()
    for i, row in enumerate(rows):
        if isinstance(row, list) and row:
            cell = str(row[0]).replace(" ", "").replace("\u3000", "").strip()
            if cell == target:
                return i
        elif isinstance(row, dict):
            cell = str(row.get("label", "")).replace(" ", "").replace("\u3000", "").strip()
            if cell == target:
                return i
    return None


def _cell_value(rows: list, row_index: int, col_index: int) -> Any:
    """从 rows 中提取指定位置的单元格值。"""
    if row_index < 0 or row_index >= len(rows):
        return None
    row = rows[row_index]
    if isinstance(row, list):
        if col_index < 0 or col_index >= len(row):
            return None
        return row[col_index]
    if isinstance(row, dict):
        values = row.get("values", [])
        if isinstance(values, list) and 0 <= col_index < len(values):
            return values[col_index]
    return None


# ─── 校验执行 ─────────────────────────────────────────────────────


async def _load_note_rows(
    db: AsyncSession, project_id: UUID, year: int, section_id: str,
) -> list | None:
    """从 disclosure_notes 或 consol_note_data 加载指定章节的 rows 数据。

    优先查 disclosure_notes（单体附注），无结果则查 consol_note_data（合并附注）。
    """
    # 先查 disclosure_notes
    from app.models.report_models import DisclosureNote

    result = await db.execute(
        sa.select(DisclosureNote.table_data).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == section_id,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    row = result.first()
    rows = _extract_rows_from_table_data(row[0] if row else None)
    if rows:
        return rows

    # 回退查 consol_note_data
    try:
        from app.models.consol_note_data_models import ConsolNoteData

        result = await db.execute(
            sa.select(ConsolNoteData.data).where(
                ConsolNoteData.project_id == project_id,
                ConsolNoteData.year == year,
                ConsolNoteData.section_id == section_id,
                ConsolNoteData.is_deleted == sa.false(),
            )
        )
        row = result.first()
        return _extract_rows_from_table_data(row[0] if row else None)
    except Exception:
        # consol_note_data 表可能不存在（SQLite 测试等）
        return None


def _extract_rows_from_table_data(table_data: Any) -> list | None:
    """从 table_data JSON 提取 rows。"""
    if not table_data:
        return None
    if isinstance(table_data, str):
        table_data = json.loads(table_data)
    if not isinstance(table_data, dict):
        return None
    # sub_table_data 中找
    sub = table_data.get("sub_table_data", {})
    rows = table_data.get("rows")
    if isinstance(rows, list) and rows:
        return rows
    for _key, val in sub.items():
        if isinstance(val, list):
            return val
    return None


def _check_column_balance(rule: CheckRule, rows: list) -> list[CheckResult]:
    """模式 B：变动表列平衡校验——期初 + 增加 - 减少 = 期末。
    
    对 self_row_label 指定的行（通常是"合计"行）校验四列恒等式。
    若 self_row_label 为 "*"，则对所有非空数据行逐行校验。
    """
    results: list[CheckResult] = []
    oc, ic, dc, cc = rule.opening_col, rule.increase_col, rule.decrease_col, rule.closing_col
    if any(c < 0 for c in (oc, ic, dc, cc)):
        results.append(CheckResult(
            check_id=rule.check_id, status="skipped", description=rule.description,
            reason="列索引配置不完整",
        ))
        return results

    target_rows: list[tuple[int, str]] = []  # (行号, 行标签)
    if rule.self_row_label == "*":
        for i, r in enumerate(rows):
            label = str(r[0]).strip() if isinstance(r, list) and r else ""
            if label:
                target_rows.append((i, label))
    else:
        ri = _find_row_by_label(rows, rule.self_row_label)
        if ri is not None:
            label = str(rows[ri][0]).strip() if isinstance(rows[ri], list) and rows[ri] else rule.self_row_label
            target_rows.append((ri, label))
        else:
            results.append(CheckResult(
                check_id=rule.check_id, status="skipped", description=rule.description,
                reason=f"找不到行「{rule.self_row_label}」",
            ))
            return results

    for ri, label in target_rows:
        opening = _to_decimal(_cell_value(rows, ri, oc))
        increase = _to_decimal(_cell_value(rows, ri, ic))
        decrease = _to_decimal(_cell_value(rows, ri, dc))
        closing = _to_decimal(_cell_value(rows, ri, cc))

        # 全空跳过
        if all(v is None for v in (opening, increase, decrease, closing)):
            continue

        o = opening or Decimal("0")
        i_val = increase or Decimal("0")
        d = decrease or Decimal("0")
        c = closing or Decimal("0")
        expected = o + i_val - d
        diff = abs(expected - c)
        tolerance = Decimal(str(rule.tolerance))

        cid = f"{rule.check_id}[{label[:15]}]" if rule.self_row_label == "*" else rule.check_id
        if diff <= tolerance:
            results.append(CheckResult(
                check_id=cid, status="pass", expected=str(expected), actual=str(c),
                description=f"{rule.description}（{label}）" if rule.self_row_label == "*" else rule.description,
            ))
        else:
            results.append(CheckResult(
                check_id=cid, status="fail", expected=str(expected), actual=str(c),
                diff=str(diff),
                description=f"{rule.description}（{label}）" if rule.self_row_label == "*" else rule.description,
            ))

    return results


async def check_note_cross_rules(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
    template_type: str,
) -> list[CheckResult]:
    """执行指定章节的全部 check_rules，返回校验结果列表。"""
    rules = _load_check_rules(template_type, section_id)
    if not rules:
        return []

    # 加载本表数据
    self_rows = await _load_note_rows(db, project_id, year, section_id)

    results: list[CheckResult] = []
    # 缓存 peer 表数据
    peer_cache: dict[str, list | None] = {}

    for rule in rules:
        if self_rows is None:
            results.append(CheckResult(
                check_id=rule.check_id,
                status="skipped",
                description=rule.description,
                reason=f"本章节 {section_id} 无附注数据",
            ))
            continue

        # ── 模式 B：列平衡（期初+增加-减少=期末）──
        if rule.mode == "column_balance":
            results.extend(_check_column_balance(rule, self_rows))
            continue

        # ── 模式 A：跨表比较 ──
        peer_sid = rule.peer_section_id
        if peer_sid not in peer_cache:
            peer_cache[peer_sid] = await _load_note_rows(db, project_id, year, peer_sid)
        peer_rows = peer_cache[peer_sid]

        if peer_rows is None:
            results.append(CheckResult(
                check_id=rule.check_id,
                status="skipped",
                description=rule.description,
                reason=f"对照章节 {peer_sid} 无附注数据",
            ))
            continue

        # 定位 self 单元格
        self_ri = _find_row_by_label(self_rows, rule.self_row_label)
        if self_ri is None:
            results.append(CheckResult(
                check_id=rule.check_id,
                status="skipped",
                description=rule.description,
                reason=f"本表找不到行「{rule.self_row_label}」",
            ))
            continue
        self_val = _to_decimal(_cell_value(self_rows, self_ri, rule.self_col_index))

        # 定位 peer 单元格
        peer_ri = _find_row_by_label(peer_rows, rule.peer_row_label)
        if peer_ri is None:
            results.append(CheckResult(
                check_id=rule.check_id,
                status="skipped",
                description=rule.description,
                reason=f"对照表找不到行「{rule.peer_row_label}」",
            ))
            continue
        peer_val = _to_decimal(_cell_value(peer_rows, peer_ri, rule.peer_col_index))

        # 校验
        if self_val is None and peer_val is None:
            results.append(CheckResult(
                check_id=rule.check_id,
                status="pass",
                expected=None,
                actual=None,
                description=rule.description,
            ))
        elif self_val is None or peer_val is None:
            results.append(CheckResult(
                check_id=rule.check_id,
                status="skipped",
                expected=str(peer_val) if peer_val is not None else None,
                actual=str(self_val) if self_val is not None else None,
                description=rule.description,
                reason="一方有值另一方为空",
            ))
        else:
            diff = abs(self_val - peer_val)
            tolerance = Decimal(str(rule.tolerance))
            if diff <= tolerance:
                results.append(CheckResult(
                    check_id=rule.check_id,
                    status="pass",
                    expected=str(peer_val),
                    actual=str(self_val),
                    description=rule.description,
                ))
            else:
                results.append(CheckResult(
                    check_id=rule.check_id,
                    status="fail",
                    expected=str(peer_val),
                    actual=str(self_val),
                    diff=str(diff),
                    description=rule.description,
                ))

    return results
