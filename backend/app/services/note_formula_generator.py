"""附注公式自动生成器

根据附注模板的 check_presets 和 table_template 结构，
自动生成每个单元格的计算公式，供前端"应用自动运算"时执行。

公式类型：
- vertical_sum: 合计行 = 上方明细行之和
- horizontal_balance: 期初 + 增加 - 减少 = 期末
- book_value: 原值 - 累计折旧/摊销 - 减值准备 = 账面价值
- balance_check: 报表数 = 附注合计数

生成的公式存储在 DisclosureNote.table_data._formulas 中：
{
  "row_idx:col_idx": {
    "type": "vertical_sum",
    "expression": "SUM(0:3, col)",  // 第0-3行同列求和
    "description": "合计 = 子项之和",
    "category": "auto_calc"
  }
}
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)


def generate_formulas_for_table(
    table_template: dict,
    check_presets: list[str],
    wp_mapping: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """根据表格模板和校验预设，自动生成单元格公式。

    扩展（L-4 task 4.1）：
    - 明细行 wp_mapping 优先 → 生成 =WP() 公式
    - 明细行 account_codes → 生成 =TB() 公式（多科目用 +）
    - 明细行 report_row_code → 生成 =REPORT() 公式（兜底）
    - 合计行（is_total）保持 vertical_sum 不变

    Args:
        table_template: {"headers": [...], "rows": [{"label", "account_codes", "is_total", "report_row_code"}]}
        check_presets: ["balance", "sub_item", "movement", "book_value"] 等
        wp_mapping: {label: {"wp_code", "sheet", "cell_closing", "cell_opening"}} 可选

    Returns: {"row_idx:col_idx": {"type": ..., "expression": ..., "description": ..., "category": ..., "source": ...}}
    """
    formulas: dict[str, dict] = {}
    headers = table_template.get("headers") or []
    rows = table_template.get("rows") or []
    wp_mapping = wp_mapping or {}

    if not rows or not headers:
        return formulas

    num_cols = len(headers) - 1  # 第0列是标签列
    if num_cols <= 0:
        return formulas

    # 检测每列对应的"期间"标签（期末 / 期初）
    period_columns = _detect_period_columns(headers[1:])  # 跳过标签列

    # 1. 明细行公式（wp_mapping > account_codes > report_row_code）
    for row_idx, row in enumerate(rows):
        if row.get("is_total"):
            continue

        label = (row.get("label") or "").strip()
        account_codes = row.get("account_codes") or []
        report_row_code = row.get("report_row_code")
        wp_cfg = wp_mapping.get(label) if label else None

        for col_idx, period_label in period_columns.items():
            if col_idx >= num_cols:
                continue

            key = f"{row_idx}:{col_idx}"
            expr: str | None = None
            source: str | None = None

            # 优先级 1：wp_mapping
            if wp_cfg:
                cell_field = "cell_closing" if "期末" in period_label else "cell_opening"
                cell_ref = wp_cfg.get(cell_field)
                if cell_ref:
                    expr = (
                        f"WP('{wp_cfg['wp_code']}','{wp_cfg.get('sheet', '')}',"
                        f"'{cell_ref}')"
                    )
                    source = "wp_mapping"

            # 优先级 2：account_codes（多科目用 + 累加）
            if not expr and account_codes:
                tb_parts = [f"TB('{code}','{period_label}')" for code in account_codes]
                expr = " + ".join(tb_parts)
                source = "account_codes"

            # 优先级 3：report_row_code 兜底
            if not expr and report_row_code:
                expr = f"REPORT('{report_row_code}','{period_label}')"
                source = "report_row_code"

            if expr:
                formulas[key] = {
                    "type": "cross_table",
                    "expression": expr,
                    "description": f"{label} {period_label}",
                    "category": "auto_calc",
                    "source": source,
                }

    # 2. 纵向合计公式（sub_item 预设）
    if "sub_item" in check_presets or "balance" in check_presets:
        total_indices = [i for i, r in enumerate(rows) if r.get("is_total")]
        for total_idx in total_indices:
            # 合计行上方的非合计行
            detail_start = 0
            for prev_total in total_indices:
                if prev_total < total_idx:
                    detail_start = prev_total + 1
            detail_end = total_idx - 1

            for col in range(num_cols):
                key = f"{total_idx}:{col}"
                formulas[key] = {
                    "type": "vertical_sum",
                    "expression": f"SUM({detail_start}:{detail_end}, {col})",
                    "description": f"合计 = 第{detail_start+1}~{detail_end+1}行之和",
                    "category": "auto_calc",
                    "source": "check_presets.sub_item",
                }

    # 3. 横向公式（movement 预设：期初+增加-减少=期末）
    if "movement" in check_presets:
        col_map = _detect_movement_columns(headers)
        if col_map:
            for row_idx, row in enumerate(rows):
                if row.get("is_total"):
                    continue
                if "closing" in col_map and "opening" in col_map:
                    closing_col = col_map["closing"]
                    key = f"{row_idx}:{closing_col}"
                    parts = []
                    if "opening" in col_map:
                        parts.append(f"cell({row_idx},{col_map['opening']})")
                    if "increase" in col_map:
                        parts.append(f"cell({row_idx},{col_map['increase']})")
                    if "decrease" in col_map:
                        parts.append(f"-cell({row_idx},{col_map['decrease']})")
                    formulas[key] = {
                        "type": "horizontal_balance",
                        "expression": " + ".join(parts) if parts else "",
                        "description": "期末 = 期初 + 增加 - 减少",
                        "category": "auto_calc",
                        "source": "check_presets.movement",
                    }

    # 4. 账面价值公式（book_value 预设）
    if "book_value" in check_presets:
        for row_idx, row in enumerate(rows):
            label = row.get("label", "")
            if "账面价值" in label and "期末" in label:
                original_idx = _find_row_by_keyword(rows, "原值期末")
                depreciation_idx = _find_row_by_keyword(rows, "累计折旧期末") or _find_row_by_keyword(rows, "累计摊销期末")
                impairment_idx = _find_row_by_keyword(rows, "减值准备期末") or _find_row_by_keyword(rows, "减值准备")

                for col in range(num_cols):
                    parts = []
                    if original_idx is not None:
                        parts.append(f"cell({original_idx},{col})")
                    if depreciation_idx is not None:
                        parts.append(f"-cell({depreciation_idx},{col})")
                    if impairment_idx is not None:
                        parts.append(f"-cell({impairment_idx},{col})")
                    if parts:
                        key = f"{row_idx}:{col}"
                        formulas[key] = {
                            "type": "book_value",
                            "expression": " + ".join(parts),
                            "description": "账面价值 = 原值 - 累计折旧/摊销 - 减值准备",
                            "category": "auto_calc",
                            "source": "check_presets.book_value",
                        }

    return formulas


def _detect_period_columns(data_headers: list[str]) -> dict[int, str]:
    """检测数据列（去掉首列标签）对应的"期末/期初"语义。

    返回 {col_idx (0-based 数据列): "期末" | "期初"}；
    非"期末/期初/本期/上期/年初/年末"列不返回（如"备注"列）。
    """
    mapping: dict[int, str] = {}
    for i, h in enumerate(data_headers):
        s = str(h or "")
        if "期末" in s or "本期" in s or "年末" in s:
            mapping[i] = "期末"
        elif "期初" in s or "上期" in s or "年初" in s:
            mapping[i] = "期初"
        # 其他列（如"备注"）不参与公式生成
    return mapping


def _detect_movement_columns(headers: list[str]) -> dict[str, int]:
    """检测变动表列（期初/增加/减少/期末）"""
    col_map: dict[str, int] = {}
    for i, h in enumerate(headers[1:], start=0):  # 跳过第0列标签
        h_str = str(h)
        if "期初" in h_str or "年初" in h_str:
            col_map["opening"] = i
        elif "增加" in h_str or "本期增加" in h_str:
            col_map["increase"] = i
        elif "减少" in h_str or "本期减少" in h_str or "摊销" in h_str or "计提" in h_str:
            col_map["decrease"] = i
        elif "期末" in h_str:
            col_map["closing"] = i
    return col_map


def _find_row_by_keyword(rows: list[dict], keyword: str) -> int | None:
    """按关键词查找行索引"""
    for i, r in enumerate(rows):
        if keyword in (r.get("label") or ""):
            return i
    return None


def _topological_sort_formulas(formulas: dict[str, dict], rows: list[dict]) -> list[str]:
    """拓扑排序公式：被引用的行先执行，引用方后执行。

    vertical_sum 类型的公式引用其他行，需要先算子项再算合计。
    其他类型（horizontal_balance/cross_table）无行间依赖，按原序。
    """
    import re

    keys = list(formulas.keys())
    # 构建依赖图：key → 依赖的 keys
    deps: dict[str, set[str]] = {k: set() for k in keys}

    for key, fdef in formulas.items():
        expr = fdef.get("expression", "")
        ftype = fdef.get("type", "")

        if ftype == "vertical_sum":
            # SUM(start:end, col) → 依赖 start~end 行的同列
            match = re.match(r"SUM\((\d+):(\d+),\s*(\d+)\)", expr)
            if match:
                start, end, col = int(match.group(1)), int(match.group(2)), int(match.group(3))
                for i in range(start, end + 1):
                    dep_key = f"{i}:{col}"
                    if dep_key in formulas:
                        deps[key].add(dep_key)

        elif ftype in ("horizontal_balance", "book_value"):
            # cell(row,col) → 依赖指定行列
            for m in re.finditer(r"cell\((\d+),(\d+)\)", expr):
                dep_key = f"{m.group(1)}:{m.group(2)}"
                if dep_key in formulas:
                    deps[key].add(dep_key)

    # Kahn's algorithm 拓扑排序
    in_degree = {k: len(deps[k]) for k in keys}
    queue = [k for k in keys if in_degree[k] == 0]
    sorted_result: list[str] = []

    while queue:
        node = queue.pop(0)
        sorted_result.append(node)
        for k in keys:
            if node in deps[k]:
                deps[k].discard(node)
                in_degree[k] -= 1
                if in_degree[k] == 0:
                    queue.append(k)

    # 如果有循环依赖，把剩余的追加到末尾
    remaining = [k for k in keys if k not in sorted_result]
    sorted_result.extend(remaining)

    return sorted_result


async def execute_note_formulas(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    note_section: str,
) -> dict[str, Any]:
    """执行附注表格中的自动运算公式，回填计算结果。

    支持的公式语法：
    - 表内引用: cell(row,col), SUM(start:end, col)
    - 跨表引用: REPORT('BS-002','期末'), TB('1001','审定数'), NOTE('五、3','合计','期末')

    流程：
    1. 加载附注数据
    2. 从 _formulas 中读取公式定义
    3. 预加载跨表数据（报表/试算表/其他附注）
    4. 按依赖顺序执行公式
    5. 将计算结果写回 table_data.rows[].values[]
    6. 只更新 mode=auto 的单元格

    Returns: {"executed": N, "updated": M}
    """
    result_q = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == note_section,
        )
    )
    note = result_q.scalar_one_or_none()
    if not note or not note.table_data:
        return {"executed": 0, "updated": 0}

    td = note.table_data
    rows = td.get("rows") or []
    formulas = td.get("_formulas") or {}

    if not formulas:
        # 尝试从模板自动生成
        check_presets = td.get("_check_presets") or []
        table_template = {"headers": td.get("headers", []), "rows": rows}
        formulas = generate_formulas_for_table(table_template, check_presets)
        if formulas:
            td["_formulas"] = formulas

    # 预加载跨表数据
    cross_table_data = await _load_cross_table_data(db, project_id, year)

    executed = 0
    updated = 0
    exec_results: list[dict] = []  # 每个公式的执行结果

    # 依赖排序：先执行被引用的行（子项），再执行引用方（合计行）
    sorted_keys = _topological_sort_formulas(formulas, rows)

    for key in sorted_keys:
        formula_def = formulas[key]
        parts = key.split(":")
        if len(parts) != 2:
            continue
        row_idx, col_idx = int(parts[0]), int(parts[1])

        if row_idx >= len(rows):
            continue

        row = rows[row_idx]
        values = row.get("values") or []
        cell_modes = row.get("_cell_modes") or {}

        # 只更新 auto 模式的单元格
        mode = cell_modes.get(str(col_idx), "auto")
        if mode != "auto":
            continue

        # 执行公式
        formula_type = formula_def.get("type")
        expression = formula_def.get("expression", "")
        calc_value = None

        if formula_type == "vertical_sum":
            calc_value = _exec_vertical_sum(rows, expression, col_idx)
        elif formula_type in ("horizontal_balance", "book_value"):
            calc_value = _exec_horizontal(rows, expression)
        elif formula_type == "cross_table":
            calc_value = _exec_cross_table(expression, cross_table_data)
        else:
            # 通用公式：尝试解析跨表引用
            calc_value = _exec_generic(expression, rows, cross_table_data)

        if calc_value is not None:
            # 确保 values 列表足够长
            while len(values) <= col_idx:
                values.append(None)
            old_value = values[col_idx]
            values[col_idx] = float(calc_value)
            row["values"] = values
            updated += 1
            exec_results.append({
                "cell": key, "type": formula_def.get("type"),
                "old": old_value, "new": float(calc_value), "status": "ok",
            })
        else:
            exec_results.append({
                "cell": key, "type": formula_def.get("type"),
                "old": None, "new": None, "status": "skipped",
                "reason": "计算结果为空",
            })

        executed += 1

    note.table_data = td
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(note, "table_data")
    await db.flush()

    # 异常检测：合计行为0但子项有数据
    anomalies = []
    for r in exec_results:
        if r["status"] == "ok" and r["new"] == 0 and r.get("type") == "vertical_sum":
            anomalies.append({"cell": r["cell"], "message": "合计行为0，请检查子项是否有数据"})

    return {"executed": executed, "updated": updated, "results": exec_results, "anomalies": anomalies}


# ---------------------------------------------------------------------------
# 跨表数据加载
# ---------------------------------------------------------------------------

async def _load_cross_table_data(db: AsyncSession, project_id: UUID, year: int) -> dict[str, Any]:
    """预加载跨表数据供公式引用。

    Returns: {
        "report": {"BS-002": {"current": 1000, "prior": 900}, ...},
        "tb": {"1001": {"audited": 500, "unadjusted": 480, "opening": 450}, ...},
        "notes": {"五、3": {"total_closing": 1200, "total_opening": 1100}, ...},
        "wp": {"E1": {"审定表E1!B5": 50.0, "审定表E1!C5": 40.0}, ...},
    }
    """
    from app.models.report_models import FinancialReport
    from app.models.audit_platform_models import TrialBalance
    from app.models.workpaper_models import WorkingPaper, WpIndex

    cross_data: dict[str, Any] = {"report": {}, "tb": {}, "notes": {}, "wp": {}}

    # 加载报表数据
    try:
        result = await db.execute(
            sa.select(
                FinancialReport.row_code,
                FinancialReport.current_period_amount,
                FinancialReport.prior_period_amount,
            ).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == sa.false(),
            )
        )
        for row_code, current, prior in result.all():
            cross_data["report"][row_code] = {
                "current": float(current) if current else 0,
                "prior": float(prior) if prior else 0,
            }
    except Exception:
        pass

    # 加载试算表数据
    try:
        result = await db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.audited_amount,
                TrialBalance.unadjusted_amount,
                TrialBalance.opening_balance,
            ).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        for code, audited, unadjusted, opening in result.all():
            cross_data["tb"][code] = {
                "audited": float(audited) if audited else 0,
                "unadjusted": float(unadjusted) if unadjusted else 0,
                "opening": float(opening) if opening else 0,
            }
    except Exception:
        pass

    # 加载底稿 cells（L-4 task 4.1 新增）
    try:
        wp_result = await db.execute(
            sa.select(WorkingPaper, WpIndex.wp_code)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
        for wp, wp_code in wp_result.all():
            if not wp_code or not wp.parsed_data:
                continue
            cells = wp.parsed_data.get("cells") or {}
            if cells:
                cross_data["wp"][wp_code] = {
                    k: float(v) if v is not None else 0
                    for k, v in cells.items()
                    if isinstance(v, (int, float))
                }
    except Exception:
        pass

    # 加载其他附注合计值
    try:
        result = await db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
            )
        )
        for note in result.scalars().all():
            if note.table_data and isinstance(note.table_data, dict):
                rows = note.table_data.get("rows") or []
                # 取最后一个合计行的第一列数值作为 total
                total_rows = [r for r in rows if r.get("is_total")]
                if total_rows:
                    values = total_rows[-1].get("values") or []
                    cross_data["notes"][note.note_section] = {
                        "total_closing": float(values[0]) if values and values[0] else 0,
                        "total_opening": float(values[1]) if len(values) > 1 and values[1] else 0,
                    }
    except Exception:
        pass

    return cross_data


# ─────────────────────────────────────────────────────────────────────────────
# L-4 task 4.1：单引用解析 + 多 token 加减组合
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_single_cross_ref(token: str, cross_data: dict[str, Any]) -> float | None:
    """解析单个跨表引用 token，返回数值或 None。

    支持：
    - TB('account_code','column')  column ∈ 期末/期初/审定数/未审数
    - REPORT('row_code','period')  period ∈ 期末/期初/current/prior
    - WP('wp_code','sheet','cell_ref')
    - NOTE('section','合计','期末'/'期初')

    无法解析或科目/底稿/附注不存在时返回 None；TB 列存在但 account 不存在 → 0。
    """
    import re

    if not token or not isinstance(token, str):
        return None

    s = token.strip()

    # WP('wp_code','sheet','cell_ref')
    m = re.fullmatch(r"\s*WP\('([^']+)','([^']*)','([^']+)'\)\s*", s)
    if m:
        wp_code = m.group(1)
        sheet = m.group(2)
        cell_ref = m.group(3)
        wp_data = cross_data.get("wp", {}).get(wp_code)
        if wp_data is None:
            return None
        # 优先匹配 "sheet!cell_ref" 复合 key，再退回单独 cell_ref
        composite = f"{sheet}!{cell_ref}" if sheet else cell_ref
        if composite in wp_data:
            return float(wp_data[composite])
        if cell_ref in wp_data:
            return float(wp_data[cell_ref])
        return None

    # NOTE('section','*','period')
    m = re.fullmatch(r"\s*NOTE\('([^']+)','([^']*)','([^']+)'\)\s*", s)
    if m:
        section = m.group(1)
        period = m.group(3)
        note_data = cross_data.get("notes", {}).get(section)
        if note_data is None:
            return None
        if "期末" in period:
            return float(note_data.get("total_closing", 0))
        if "期初" in period:
            return float(note_data.get("total_opening", 0))
        return None

    # REPORT('row_code','period')
    m = re.fullmatch(r"\s*REPORT\('([^']+)','([^']+)'\)\s*", s)
    if m:
        row_code = m.group(1)
        period = m.group(2)
        report_data = cross_data.get("report", {}).get(row_code)
        if report_data is None:
            return None
        if "期末" in period or "current" in period or "本期" in period:
            return float(report_data.get("current", 0))
        if "期初" in period or "prior" in period or "上期" in period:
            return float(report_data.get("prior", 0))
        return None

    # TB('account_code','column')
    m = re.fullmatch(r"\s*TB\('([^']+)','([^']+)'\)\s*", s)
    if m:
        account_code = m.group(1)
        column = m.group(2)
        # 列名识别（先做白名单：只接受预期列）
        col_key: str | None = None
        if "审定" in column or column == "audited":
            col_key = "audited"
        elif "未审" in column or column == "unadjusted":
            col_key = "unadjusted"
        elif "期初" in column or column == "opening":
            col_key = "opening"
        elif "期末" in column or column == "closing":
            # 期末余额 = 审定数
            col_key = "audited"
        else:
            return None
        tb_data = cross_data.get("tb", {}).get(account_code)
        if tb_data is None:
            # 列名合法但 account 不存在 → 默认 0
            return 0.0
        return float(tb_data.get(col_key, 0))

    return None


def _exec_cross_table(expression: Any, cross_data: dict[str, Any]) -> float | None:
    """执行跨表引用公式（支持多 token 加减组合）。

    支持语法：
    - 单引用：TB('1001','期末') / REPORT('BS-002','期末') / WP('E1','审定表E1','B5')
    - 加减组合：TB('1001','期末') + TB('1002','期末') - WP('E1','审定表E1','C5')

    任何 token 解析失败返回 None；空 / 非字符串 / 完全不匹配的字符串返回 None。
    """
    import re

    if expression is None or not isinstance(expression, str):
        return None
    s = expression.strip()
    if not s:
        return None

    # 切分 +/- 操作符（保留符号）
    # 例 "TB('1','期末') + TB('2','期末') - WP('E1','审定表','B5')"
    # 用正则把整个表达式拆为 [(sign, token), ...]
    pattern = re.compile(
        r"([+-]?)\s*((?:TB|REPORT|WP|NOTE)\([^)]*\))",
    )
    matches = pattern.findall(s)
    if not matches:
        return None

    # 把所有匹配的 token 还原拼接，验证整个 expression 由这些 token + +/- 组成
    reconstructed = "".join(
        f"{sign or '+'}{token}" for sign, token in matches
    )
    # 移除原 s 内的空白后再比较
    s_no_space = re.sub(r"\s+", "", s)
    rec_no_space = re.sub(r"\s+", "", reconstructed)
    # 允许首项无 + 号
    if rec_no_space.startswith("+"):
        rec_no_space_alt = rec_no_space[1:]
    else:
        rec_no_space_alt = rec_no_space
    if s_no_space not in (rec_no_space, rec_no_space_alt):
        return None

    total = 0.0
    for sign, token in matches:
        val = _resolve_single_cross_ref(token, cross_data)
        if val is None:
            return None
        if sign == "-":
            total -= val
        else:
            total += val
    return total


def _exec_generic(expression: str, rows: list[dict], cross_data: dict[str, Any]) -> float | None:
    """通用公式执行：支持混合引用（表内+跨表）"""
    import re

    # 先尝试跨表引用
    cross_result = _exec_cross_table(expression, cross_data)
    if cross_result is not None:
        return cross_result

    # 再尝试表内引用
    horizontal_result = _exec_horizontal(rows, expression)
    if horizontal_result is not None:
        return horizontal_result

    return None


def _exec_vertical_sum(rows: list[dict], expression: str, col_idx: int) -> float | None:
    """执行纵向求和：SUM(start:end, col)"""
    try:
        # 解析 SUM(0:3, 0)
        inner = expression.replace("SUM(", "").rstrip(")")
        parts = inner.split(",")
        range_part = parts[0].strip()
        start, end = [int(x.strip()) for x in range_part.split(":")]

        total = 0.0
        for i in range(start, end + 1):
            if i < len(rows):
                values = rows[i].get("values") or []
                if col_idx < len(values) and values[col_idx] is not None:
                    total += float(values[col_idx])
        return total
    except Exception:
        return None


def _exec_horizontal(rows: list[dict], expression: str) -> float | None:
    """执行横向公式：cell(row,col) + cell(row,col) - cell(row,col)"""
    try:
        import re
        result = 0.0
        # 匹配 cell(row,col) 和前面的 +/-
        tokens = re.findall(r'([+-]?)\s*cell\((\d+),(\d+)\)', expression)
        for sign, row_s, col_s in tokens:
            row_idx, col_idx = int(row_s), int(col_s)
            if row_idx < len(rows):
                values = rows[row_idx].get("values") or []
                if col_idx < len(values) and values[col_idx] is not None:
                    val = float(values[col_idx])
                    if sign == "-":
                        result -= val
                    else:
                        result += val
        return result
    except Exception:
        return None



# ─────────────────────────────────────────────────────────────────────────────
# L-4 task 4.1：覆盖率统计
# ─────────────────────────────────────────────────────────────────────────────


def compute_formula_coverage(table_data: dict | None) -> dict[str, Any]:
    """计算单个附注表格的公式覆盖率。

    覆盖率 = 可生成公式的 cell 数 / 数据列总 cell 数（不含标签列）

    Args:
        table_data: {"headers", "rows", "_check_presets", "_wp_mapping"?}

    Returns: {"total_cells": N, "configured_cells": M, "coverage_pct": X.X}
    """
    if not table_data or not isinstance(table_data, dict):
        return {"total_cells": 0, "configured_cells": 0, "coverage_pct": 0.0}

    headers = table_data.get("headers") or []
    rows = table_data.get("rows") or []
    if not headers or not rows:
        return {"total_cells": 0, "configured_cells": 0, "coverage_pct": 0.0}

    # 仅统计 _detect_period_columns 识别的"期末/期初"类列（备注列等不计入分母）
    period_cols = _detect_period_columns(headers[1:])
    num_period_cols = len(period_cols)
    if num_period_cols == 0:
        return {"total_cells": 0, "configured_cells": 0, "coverage_pct": 0.0}

    total_cells = len(rows) * num_period_cols
    check_presets = table_data.get("_check_presets") or []
    wp_mapping = table_data.get("_wp_mapping") or {}

    formulas = generate_formulas_for_table(
        {"headers": headers, "rows": rows},
        check_presets,
        wp_mapping=wp_mapping,
    )

    # 仅统计 period_cols 范围内的 configured cells
    configured_cells = 0
    for key in formulas:
        try:
            r_str, c_str = key.split(":", 1)
            c_idx = int(c_str)
            if c_idx in period_cols:
                configured_cells += 1
        except (ValueError, IndexError):
            continue

    coverage_pct = round(configured_cells * 100 / total_cells, 1) if total_cells else 0.0
    return {
        "total_cells": total_cells,
        "configured_cells": configured_cells,
        "coverage_pct": coverage_pct,
    }


async def compute_project_formula_coverage(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> dict[str, Any]:
    """项目级附注公式覆盖率统计（聚合所有 DisclosureNote）。

    Returns: {
        "total_cells": N,
        "configured_cells": M,
        "coverage_pct": X.X,
        "by_section": [{"note_section": "五、1", "total_cells": ..., "configured_cells": ..., "coverage_pct": ...}, ...],
    }
    """
    result = await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.false(),
        )
    )
    notes = list(result.scalars().all())

    total = 0
    configured = 0
    by_section: list[dict[str, Any]] = []
    for note in notes:
        td = note.table_data
        if not td:
            continue
        s = compute_formula_coverage(td)
        total += s["total_cells"]
        configured += s["configured_cells"]
        by_section.append({
            "note_section": note.note_section,
            **s,
        })

    coverage_pct = round(configured * 100 / total, 1) if total else 0.0
    return {
        "total_cells": total,
        "configured_cells": configured,
        "coverage_pct": coverage_pct,
        "by_section": by_section,
    }
