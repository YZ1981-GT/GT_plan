"""单条公式的上下游依赖（公式管理中心「依赖关系」；spec formula-settings-wiring-closure R3.2）。

* 目标地址：``report:{报表类型}:{行次}`` / ``{报表类型}:{行次}`` / 裸行次（在本项目报表行里唯一匹配）/
  ``tb:{科目编码}``。
* 上游 = 目标公式（本项目有效定义）里的 TB / SUM_TB / ROW / SUM_ROW / REPORT / WP / NOTE / ADJ / PREV 引用。
* 下游 = 本项目报表、表间审核、底稿、附注、试算表明细各域有效公式里，精确引用目标的公式位
  （ROW / REPORT 按行次相等，SUM_ROW / SUM_TB 按区间包含，TB 按科目编码相等）。

旧实现查不存在的 ``ReportConfig.project_id``（报表地址一律 500）、按子串匹配公式位（与当初
``E1-1`` 串到 ``E1-10`` 同型）、下游走反向索引而 URI 口径对不上（科目地址永远 0 条）。
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings.effective import effective_slots

_TB = re.compile(r"(?<![A-Z_])TB\(\s*'([^']+)'\s*,\s*'([^']*)'\s*\)")
_SUM_TB = re.compile(r"SUM_TB\(\s*'([^']+)'\s*,\s*'([^']*)'\s*\)")
_ROW = re.compile(r"(?<![A-Z_])ROW\(\s*'([^']+)'\s*\)")
_SUM_ROW = re.compile(r"SUM_ROW\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")
_REPORT = re.compile(r"REPORT\(\s*'([^']+)'(?:\s*,\s*'([^']*)')?\s*\)")
_WP = re.compile(r"(?<![A-Z_])WP\(\s*'([^']+)'\s*,\s*'([^']+)'(?:\s*,\s*'([^']+)')?\s*\)")
_NOTE = re.compile(r"NOTE\(\s*'([^']+)'\s*,\s*'([^']+)'(?:\s*,\s*'([^']+)')?\s*\)")
_ADJ = re.compile(r"ADJ\(\s*'([^']+)'(?:\s*,\s*'([^']*)')?\s*\)")
_PREV = re.compile(r"PREV\(\s*'([^']+)'\s*,\s*'([^']+)'(?:\s*,\s*'([^']+)')?\s*\)")

#: 各域参与依赖分析的公式字段
FORMULA_FIELDS: dict[str, tuple[str, ...]] = {
    "report": ("formula", "aje_formula", "rje_formula"),
    "cross_check": ("left_ref", "right_ref"),
    "wp": ("expression",),
    "note": ("formula",),
    "tb_detail": ("formula",),
}
DOMAIN_LABELS = {"report": "报表", "cross_check": "表间审核", "wp": "底稿", "note": "附注", "tb_detail": "试算表明细"}


class DependencyTargetError(ValueError):
    """地址无法定位到唯一公式位。"""


def formula_text(domain: str, definition: dict | None) -> str:
    if not definition:
        return ""
    return " ".join(str(definition.get(f) or "") for f in FORMULA_FIELDS.get(domain, ())).strip()


def _in_range(code: str, start: str, end: str) -> bool:
    return start <= code <= end


def _same_prefix(a: str, b: str) -> bool:
    """行次区间只在同一张表的编码前缀内成立（``BS-001``~``BS-040`` 不含 ``IS-010``）。"""
    return a.rpartition("-")[0] == b.rpartition("-")[0]


def _split_range(text: str) -> tuple[str, str]:
    a, _, b = text.partition("~")
    return a.strip(), (b or a).strip()


def upstream_refs(formula: str, report_types: dict[str, str]) -> list[dict[str, Any]]:
    """公式文本 → 上游引用（去重、按出现顺序）。``report_types`` = 行次 → 报表类型。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(kind: str, label: str, addr: str) -> None:
        if addr not in seen:
            seen.add(addr)
            out.append({"type": kind, "label": label, "addr_id": addr})

    def row_addr(code: str) -> str:
        rt = report_types.get(code)
        return f"report:{rt}:{code}" if rt else f"report:{code}"

    for m in _SUM_TB.finditer(formula):
        add("trial_balance", f"SUM_TB('{m.group(1)}','{m.group(2)}')", f"tb:{m.group(1)}")
    for m in _TB.finditer(formula):
        add("trial_balance", f"TB('{m.group(1)}','{m.group(2)}')", f"tb:{m.group(1)}")
    for m in _SUM_ROW.finditer(formula):
        add("report", f"SUM_ROW('{m.group(1)}','{m.group(2)}')", f"report:{m.group(1)}~{m.group(2)}")
    for m in _ROW.finditer(formula):
        add("report", f"ROW('{m.group(1)}')", row_addr(m.group(1)))
    for m in _REPORT.finditer(formula):
        add("report", f"REPORT('{m.group(1)}')", row_addr(m.group(1)))
    for m in _WP.finditer(formula):
        parts = [p for p in m.groups() if p]
        add("workpaper", "WP(" + ",".join(f"'{p}'" for p in parts) + ")", "wp:" + "/".join(parts))
    for m in _NOTE.finditer(formula):
        add("note", f"NOTE('{m.group(1)}','{m.group(2)}')", f"note:{m.group(1)}")
    for m in _ADJ.finditer(formula):
        add("adjustment", f"ADJ('{m.group(1)}')", f"adj:{m.group(1)}")
    for m in _PREV.finditer(formula):
        add("prior", f"PREV('{m.group(1)}','{m.group(2)}')", f"prev:{m.group(1)}")
    return out


def references(formula: str, *, row_code: str | None = None, account: str | None = None) -> bool:
    """公式是否精确引用目标行次 / 科目。"""
    if row_code:
        if any(m.group(1) == row_code for m in _ROW.finditer(formula)):
            return True
        if any(m.group(1) == row_code for m in _REPORT.finditer(formula)):
            return True
        if any(_in_range(row_code, m.group(1), m.group(2)) and _same_prefix(m.group(1), row_code)
               for m in _SUM_ROW.finditer(formula)):
            return True
    if account:
        if any(m.group(1) == account for m in _TB.finditer(formula)):
            return True
        for m in _SUM_TB.finditer(formula):
            a, b = _split_range(m.group(1))
            if _in_range(account, a, b):
                return True
    return False


async def _slots(db: AsyncSession, project_id: uuid.UUID) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """各域有效定义 + 读取失败的域。

    每个域在独立保存点里读：PG 上一条语句失败会让整个事务进入 aborted，不隔离的话后面所有域
    （以及调用方事务）都跟着失败。失败的域如实返回给界面（「附注域未列入」），不当成「没有被引用」。
    """
    # 报表域是定位目标的依据，读不到就是真错误，不吞
    out: dict[str, dict[str, Any]] = {"report": await effective_slots(db, "report", project_id)}
    unavailable: list[str] = []
    for domain in FORMULA_FIELDS:
        if domain == "report":
            continue
        try:
            async with db.begin_nested():
                out[domain] = await effective_slots(db, domain, project_id)
        except Exception:  # noqa: BLE001 —— 单域取不到不拖垮依赖面板
            out[domain] = {}
            unavailable.append(domain)
    return out, unavailable


def _resolve_target(addr_id: str, report: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """→（kind, report slot_key, account）。"""
    text = (addr_id or "").strip()
    if text.startswith("tb:"):
        code = text[3:].strip()
        if not code:
            raise DependencyTargetError("科目编码为空")
        return "tb", None, code
    if text.startswith("report:"):
        text = text[len("report:"):]
    if ":" in text:
        if text in report:
            return "report", text, None
        raise DependencyTargetError(f"本项目报表里没有这一行：{text}")
    hits = [k for k in report if k.partition(":")[2] == text]
    if len(hits) != 1:
        raise DependencyTargetError("无法定位这一行（行次不存在或在多张报表里重复）")
    return "report", hits[0], None


async def formula_dependencies(db: AsyncSession, project_id: uuid.UUID, addr_id: str) -> dict[str, Any]:
    slots, unavailable = await _slots(db, project_id)
    report = slots.get("report") or {}
    kind, slot_key, account = _resolve_target(addr_id, report)
    report_types = {k.partition(":")[2]: k.partition(":")[0] for k in report}
    row_code = slot_key.partition(":")[2] if slot_key else None
    formula = formula_text("report", report[slot_key].definition) if slot_key else ""
    downstream: list[dict[str, Any]] = []
    for domain, items in slots.items():
        for key, slot in items.items():
            if domain == "report" and key == slot_key:
                continue
            text = formula_text(domain, slot.definition)
            if text and references(text, row_code=row_code, account=account):
                downstream.append({"type": domain, "label": f"{DOMAIN_LABELS[domain]} {slot.label or key}",
                                   "addr_id": f"report:{key}" if domain == "report" else f"{domain}:{key}"})
    return {"addr_id": f"report:{slot_key}" if slot_key else f"tb:{account}", "kind": kind, "formula": formula,
            "upstream": upstream_refs(formula, report_types) if formula else [],
            "downstream": downstream[:200], "downstream_total": len(downstream),
            "unavailable_domains": [{"domain": d, "label": DOMAIN_LABELS[d]} for d in unavailable]}
