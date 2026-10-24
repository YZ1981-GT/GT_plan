"""底稿域有效公式接入预填（design §12 wp，tasks 6.1）。

优先级：本项目（``wp_formula`` 行）> 全局（``formula_setting``）> 系统预设映射（``prefill_formula_mapping.json``）
> 模板内置公式。

* 初始化预填（``prefill_workpaper_xlsx``）：映射单元格换成有效公式后照原口径取数（``mapping_overrides``）；
  映射之外的有效公式走「用户公式」路径写成单元格公式（``user_formulas``）。
* 重新预填（``prefill_workpaper_real``）：有效公式覆盖 / 补充 xlsx 内置公式。A1 坐标直接定位；映射里的语义位置
  （如「期初余额」）用初始化同一套定位规则；只算单个取数函数，复合表达式记一条提示、交公式运行时。
  曾有全局定义、现已删除的公式位按系统预设重算，免得残留已删除全局公式算出的值。
* 只处理改过的公式位：从没有全局 / 本项目定义的映射单元格维持原行为（只在初始化时写值）。
* 已知限制：公式运行时（``formula_runtime``）与各循环 Tier A 预设只读 ``wp_formula`` 行，不读全局层；
  同步内核为有适配的项目写的行它们照常读到。
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings.definitions import ANY_SCOPE
from app.services.formula_settings.domain_stores import WP_SOURCES, _mapping_records, split_wp_slot, wp_slot

logger = logging.getLogger(__name__)
_A1 = re.compile(r"^[A-Z]{1,3}[0-9]{1,7}$")
_CALL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*)\)$")
_LAYER_TEXT = {"project": "本项目", "global": "全局", "preset": "系统预设"}
#: 检查类公式只出问题清单，绝不改值
_VALUE_TYPES = ("", "auto_calc")


@dataclass(frozen=True)
class CellFormula:
    sheet: str
    cell: str
    expression: str  # 不带前导「=」
    formula_type: str
    layer: str  # project / global / preset（全局已删除、回到预设）


def _expr(text: Any) -> str:
    return str(text or "").strip().lstrip("=").strip()


async def _load(db: AsyncSession, project_id: uuid.UUID, wp_id: uuid.UUID) -> tuple[str | None, list[CellFormula]]:
    from app.models.formula_setting_models import FormulaSetting
    from app.models.workpaper_models import WorkingPaper, WpFormula, WpIndex

    code = (await db.execute(sa.select(WpIndex.wp_code).join(
        WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id).where(WorkingPaper.id == wp_id))).scalar_one_or_none()
    if not code:
        return None, []
    rows = (await db.execute(sa.select(FormulaSetting).where(
        FormulaSetting.domain == "wp", FormulaSetting.layer == "global", FormulaSetting.scope == ANY_SCOPE,
        FormulaSetting.slot_key.startswith(f"{code}|", autoescape=True)))).scalars().all()
    presets = _mapping_records()
    out: dict[tuple[str, str], CellFormula] = {}
    for row in sorted(rows, key=lambda r: not r.is_deleted):  # 已删除在前，现行覆盖
        _, sheet, cell = split_wp_slot(row.slot_key)
        if row.is_deleted:
            preset = presets.get(row.slot_key)
            if preset is None:
                continue
            definition, layer = preset.definition or {}, "preset"
        else:
            definition, layer = row.definition or {}, "global"
        if _expr(definition.get("expression")):
            out[(sheet, cell)] = CellFormula(sheet, cell, _expr(definition.get("expression")),
                                             str(definition.get("formula_type") or "auto_calc"), layer)
    own = (await db.execute(sa.select(WpFormula).where(
        WpFormula.wp_id == wp_id, WpFormula.project_id == project_id,
        WpFormula.formula_source.in_(WP_SOURCES)))).scalars().all()
    for r in own:
        if _expr(r.expression):
            out[(r.sheet_name, r.target_cell)] = CellFormula(r.sheet_name, r.target_cell, _expr(r.expression),
                                                             r.formula_type or "auto_calc", "project")
    return code, sorted(out.values(), key=lambda c: (c.sheet, c.cell))


async def effective_cell_formulas(db: AsyncSession, project_id: uuid.UUID,
                                  wp_id: uuid.UUID) -> tuple[str | None, list[CellFormula]]:
    """本底稿改过的公式位的有效定义。只读，保存点隔离：读失败（如迁移未落库）按「无改动」降级。"""
    try:
        async with db.begin_nested():
            return await _load(db, project_id, wp_id)
    except Exception as exc:  # noqa: BLE001 —— 预填照原行为继续
        logger.warning("底稿有效公式读取失败，按预设预填 wp=%s: %s", wp_id, exc)
        return None, []


# ── 初始化预填 ────────────────────────────────────────────────────────────────


async def init_prefill_overrides(db: AsyncSession, project_id: uuid.UUID,
                                 wp_id: uuid.UUID) -> tuple[dict[str, dict], dict[str, str]]:
    """返回（``user_formulas``, ``mapping_overrides``），键都是 ``{sheet}!{cell}``。"""
    code, cells = await effective_cell_formulas(db, project_id, wp_id)
    presets = _mapping_records() if code else {}
    user: dict[str, dict] = {}
    overrides: dict[str, str] = {}
    for cf in cells:
        if cf.formula_type not in _VALUE_TYPES:
            continue
        if wp_slot(code or "", cf.sheet, cf.cell) in presets:
            overrides[f"{cf.sheet}!{cf.cell}"] = "=" + cf.expression
        elif _A1.match(cf.cell.strip().upper()):
            user[f"{cf.sheet}!{cf.cell.strip().upper()}"] = {"formula": "=" + cf.expression, "layer": cf.layer}
    return user, overrides


def _call(text: str) -> tuple[str, list[str]] | None:
    from app.services.prefill_engine import _parse_args

    m = _CALL.match(_expr(text))
    return (m.group(1).upper(), _parse_args(m.group(2))) if m else None


def _terms(expr: str) -> list[tuple[int, str]] | None:
    """按顶层加减号拆项（引号与括号内的不拆）；结构不完整返回 ``None``。"""
    out: list[tuple[int, str]] = []
    sign, buf, depth, quote = 1, "", 0, ""
    for ch in expr:
        if quote:
            buf += ch
            quote = "" if ch == quote else quote
            continue
        if ch in "'\"":
            quote, buf = ch, buf + ch
            continue
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth == 0 and ch in "+-":
            if buf.strip():
                out.append((sign, buf.strip()))
                sign, buf = 1, ""
            sign *= 1 if ch == "+" else -1
            continue
        buf += ch
    if quote or depth or not buf.strip():
        return None
    return [*out, (sign, buf.strip())]


def _term_value(term: str, preset_formula: str, tb_data: dict, adj_data: dict | None,
                account_codes: list[str]) -> float | None:
    try:
        return float(term)
    except ValueError:
        pass
    call = _call(term)
    if call is None:
        return None
    func, args = call
    if func == "TB" and len(args) >= 2:
        return (tb_data.get(args[0]) or {}).get(args[1])
    if func in ("TB_SUM", "SUM_TB") and len(args) >= 2 and account_codes:
        preset = _call(preset_formula or "")
        if preset is None or not preset[1] or preset[1][0] != args[0]:
            return None
        return sum((tb_data.get(code) or {}).get(args[1], 0) for code in account_codes)
    if func == "ADJ" and len(args) >= 2 and adj_data:
        return (adj_data.get(args[0]) or {}).get(args[1], 0)
    return None


def override_value(formula: str, preset_formula: str, tb_data: dict, adj_data: dict | None,
                   account_codes: list[str]) -> float | None:
    """初始化预填时按有效公式取映射单元格的值（取数口径同预设：TB / TB_SUM / ADJ，可用加减号相连）。

    TB、ADJ 按公式自己的科目取（多项相加时缺的科目按 0，全缺则不写）；TB_SUM 只在科目范围与预设相同
    （只改了列）时沿用映射科目清单 —— 范围展开要处理父子科目，交重新预填（公式引擎）算。
    含其他函数的公式初始化不取值（与预设一致），返回 ``None``。
    """
    terms = _terms(_expr(formula))
    if not terms:
        return None
    total, found = 0.0, False
    for sign, term in terms:
        value = _term_value(term, preset_formula, tb_data, adj_data, account_codes)
        if value is None:
            if _call(term) is None or _call(term)[0] not in ("TB",):
                return None  # 不支持的项：整条不取值
            continue  # 该科目试算表没有：按 0
        total, found = total + sign * float(value), True
    return total if found else None


# ── 重新预填 ──────────────────────────────────────────────────────────────────


def locate_cell(ws: Any, ref: str, wp_code: str) -> str | None:
    """公式位单元格 → A1 坐标。语义位置与初始化预填同一套规则；落在公式单元格上不覆盖（同初始化）。

    三参 PREV 公式位（系统预设是三参 PREV 的语义名）只认定位表（``prev3_prefill_locator``）：``write`` 格给坐标，
    ``verify``（模板公式）/ ``none`` / 模板与定位表不符一律不落格，不退回列头关键词猜格。
    """
    from app.services import prev3_prefill_locator as prev3
    from app.services.wp_template_xlsx_ops import (
        _find_column_by_keyword,
        _find_data_column,
        _find_first_data_row,
        _find_semantic_row,
        _is_formula_cell,
    )

    ref = (ref or "").strip()
    if _A1.match(ref.upper()):
        return ref.upper()
    if prev3.is_prev3_slot(wp_code, ws.title.strip(), ref):
        entry, _why = prev3.locate(ws, wp_code, ref)
        return entry.cell if entry is not None and entry.action == "write" else None
    col = _find_column_by_keyword(ws, ref)
    row = _find_first_data_row(ws, col) if col else None
    if col and row:
        cell = ws.cell(row=row, column=col)
        return None if _is_formula_cell(cell) else cell.coordinate
    row = _find_semantic_row(ws, ref, wp_code, ref)
    if row:
        cell = ws.cell(row=row, column=_find_data_column(ws, row))
        return None if _is_formula_cell(cell) else cell.coordinate
    return None


async def overlay_prefill_formulas(db: AsyncSession, project_id: uuid.UUID, wp: Any, wb: Any,
                                   found: list[dict], pattern: re.Pattern) -> tuple[list[dict], list[dict]]:
    """``prefill_workpaper_real`` 的扫描结果叠加有效公式：同一单元格以有效公式为准。返回（新清单, 提示）。"""
    code, cells = await effective_cell_formulas(db, project_id, wp.id)
    if not cells:
        return found, []
    sheets = {ws.title: (i, ws) for i, ws in enumerate(wb.worksheets)}
    overlay: dict[tuple[str, str], dict | None] = {}
    notes: list[dict] = []
    for cf in cells:
        if cf.formula_type not in _VALUE_TYPES or cf.sheet not in sheets:
            continue
        idx, ws = sheets[cf.sheet]
        coord = locate_cell(ws, cf.cell, code or "")
        if coord is None:
            continue
        original = "=" + re.sub(r"^TB_SUM\s*\(", "SUM_TB(", cf.expression, flags=re.I)
        m = pattern.fullmatch(original)
        if m is None:
            overlay[(cf.sheet, coord)] = None  # 不再按模板内置公式算（它已不是有效公式）
            notes.append({"cell": f"{cf.sheet}!{coord}",
                          "error": f"{_LAYER_TEXT.get(cf.layer, cf.layer)}公式不是单个取数函数，预填未计算，由公式运行时计算"})
            continue
        cell = ws[coord]
        overlay[(cf.sheet, coord)] = {
            "sheet": cf.sheet, "sheet_idx": idx, "cell": coord, "row": cell.row - 1, "col": cell.column - 1,
            "formula_type": m.group(1).upper(), "raw_args": m.group(2).strip(), "original": original,
            "cell_obj": cell, "layer": cf.layer,
        }
    kept = [f for f in found if (f["sheet"], f["cell"]) not in overlay]
    return kept + [v for v in overlay.values() if v is not None], notes
