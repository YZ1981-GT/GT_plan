"""附注公式自动生成器

根据附注模板的 check_presets 和 table_template 结构，
自动生成每个单元格的计算公式，供前端"应用自动运算"时执行。

参考文档：docs/NOTE_FORMULA_DSL.md（完整 DSL 语法参考 + _formulas schema）

公式类型：
- vertical_sum: 合计行 = 上方明细行之和
- horizontal_balance: 期初 + 增加 - 减少 = 期末
- book_value: 原值 - 累计折旧/摊销 - 减值准备 = 账面价值
- balance_check: 报表数 = 附注合计数

DSL 函数清单（_resolve_single_cross_ref）：
- TB('account_code','column')        — 试算表取数（已有）
- WP('wp_code','sheet','cell_ref')   — 底稿单元格取数（已有）
- REPORT('row_code','period')        — 财报取数（已有）
- NOTE('section','*','period')       — 当年其他附注合计（已有）
- cell(row, col) / SUM(start:end,c)  — 表内引用（已有）
- PRIOR('account_name','期末'|'期初') — 上年附注取数（Sprint 1.5 Task 1.5.2 新增）
- AGING('account_name','bucket')     — 账龄分桶（Sprint 1.5 Task 1.5.2 新增）

生成的公式存储在 DisclosureNote.table_data._formulas 中（dict[str, dict]，
key="row_idx:col_idx"，row/col 从 key 解出无需冗余存储）：
{
  "row_idx:col_idx": {
    "type": "vertical_sum",          # 公式分类
    "expression": "SUM(0:3, col)",   # DSL 表达式原文
    "description": "合计 = 子项之和",
    "category": "auto_calc",
    "source": "check_presets.sub_item",  # 公式来源
    "binding_id": None,              # Sprint 1.5 Task 1.5.4：关联 _cell_meta.binding_id
    "evaluated_at": "2026-..."       # Sprint 1.5 Task 1.5.4：execute 时写入 ISO timestamp
  }
}
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
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
                    "binding_id": None,  # Sprint 1.5 Task 1.5.4 占位，由 _build_with_binding 写实
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
                    "binding_id": None,  # Sprint 1.5 Task 1.5.4 占位
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
                        "binding_id": None,  # Sprint 1.5 Task 1.5.4 占位
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
                            "binding_id": None,  # Sprint 1.5 Task 1.5.4 占位
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


def _user_formula_to_def(rec: dict) -> tuple[str, dict] | None:
    """把一条用户集公式记录（``_user_formulas`` 的 list 元素）归一化为
    ``_formulas`` dict 条目形态 ``(key, fdef)``。

    用户集 shape（见 note_formula_service._normalize_record）：
    ``{target, formula, description, category, source, type}``，其中
    ``target`` 为 ``"row:col"`` 单元格键、``formula`` 为 DSL 表达式。
    归一化到执行态 ``{type, expression, description, category, source}``。

    无合法 ``target``（非 ``"row:col"`` / ``"t{n}:row:col"``）或无表达式者返回 None（跳过）。目标统一成
    ``note_formula_tables.formula_key`` 写法（``t0:1:2`` ≡ ``1:2``）。
    """
    from app.services.note_formula_tables import formula_key, parse_formula_key

    if not isinstance(rec, dict):
        return None
    parsed = parse_formula_key(rec.get("target") or rec.get("target_cell"))
    if parsed is None:
        return None
    target = formula_key(*parsed)
    expr = rec.get("formula")
    if expr is None:
        expr = rec.get("expression")
    expr = expr.strip() if isinstance(expr, str) else expr
    if not expr:
        return None
    return target, {
        "type": rec.get("type") or "",
        "expression": expr,
        "description": rec.get("description") or "",
        "category": rec.get("category") or "auto_calc",
        "source": rec.get("source") or "user_formula",
        "binding_id": rec.get("binding_id"),
    }


def _merge_formula_sets(
    template_formulas: dict[str, dict], user_formulas: list | None
) -> dict[str, dict]:
    """合并模板预设 ``_formulas`` 与用户集 ``_user_formulas``（ADR-FMC-04）。

    合并口径：
    - 以 ``"row:col"`` 为目标单元格键做去重合并。
    - 同键冲突时**用户集优先**（用户公式覆盖同键模板预设）。
    - 返回单一 dict，供 ``execute_note_formulas`` 对其**统一重算拓扑排序**
      （调用方对合并集一次性拓扑，而非两套各自排序后拼接）。

    ``user_formulas`` 为 None / 空 / 非 list 时等价于只有模板集（返回其浅拷贝）。目标键统一成
    ``formula_key`` 写法（多表章节 ``t{n}:row:col``），同一单元格不会因写法不同算两条。
    """
    from app.services.note_formula_tables import formula_key, parse_formula_key

    merged: dict[str, dict] = {}
    for key, fdef in (template_formulas or {}).items():
        parsed = parse_formula_key(key)
        merged[formula_key(*parsed) if parsed else key] = fdef
    if isinstance(user_formulas, list):
        for rec in user_formulas:
            conv = _user_formula_to_def(rec)
            if conv is None:
                continue
            key, fdef = conv
            # 用户集优先：同键直接覆盖模板预设（不是追加第二条）。
            merged[key] = fdef
    return merged


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


# ─────────────────────────────────────────────────────────────────────────────
# Task 9.1（Req 17.2/17.6）：附注执行器与 ACNR full_resolve 对齐
#   - 跨表 REPORT/TB/NOTE 域引用经 resolve_ref（复用 formula_management/engine.py
#     的 ACNR full_resolve 封装，fail-open：解析器故障不阻断执行）建立 canonical
#     addr_id 身份（Req 17.2 / Property 8）。
#   - 附注单元的稳定 addr_id（NOTE 域）供合并附注 reaggregate 后按 addr_id 精准刷新
#     受影响单元（Req 17.6），与统一寻址体系（note:{section}）一致，可溯源。
# ─────────────────────────────────────────────────────────────────────────────

# 仅 REPORT/TB/NOTE 三域 token（本任务对齐范围；PRIOR/AGING/WP 保持既有本地解析）。
_CROSS_REF_TOKEN_RE = None  # 惰性编译，见 _extract_cross_ref_tokens


def _note_cell_addr_id(note_section: str, row_idx: int, col_idx: int) -> str:
    """附注单元的稳定 addr_id（NOTE 域标识）。

    与 ConsolNoteTab / useNoteTree 的 ``note:{section}`` 寻址一致，附加 ``!{row}:{col}``
    定位到单元格，供 reaggregate 后按 addr_id 精准刷新与来源溯源（Req 17.6）。
    仅作标识用途，不参与求值。
    """
    return f"note:{note_section}!{row_idx}:{col_idx}"


def _extract_cross_ref_tokens(expression: Any) -> list[str]:
    """抽取表达式中的 REPORT/TB/NOTE 跨表引用 token（Req 17.2 对齐范围）。"""
    global _CROSS_REF_TOKEN_RE
    if not expression or not isinstance(expression, str):
        return []
    if _CROSS_REF_TOKEN_RE is None:
        import re as _re

        _CROSS_REF_TOKEN_RE = _re.compile(r"(?:REPORT|TB|NOTE)\([^)]*\)")
    return _CROSS_REF_TOKEN_RE.findall(expression)


async def _resolve_cross_refs_via_acnr(
    expression: Any,
    project_id: UUID,
    db: AsyncSession,
) -> dict[str, str]:
    """对表达式中的 REPORT/TB/NOTE 跨表引用逐条经 ACNR full_resolve 解析（Req 17.2）。

    复用 ``formula_management.engine.resolve_ref``（封装 ACNR full_resolve，fail-open）。
    返回 ``{token: canonical_addr_id}``（仅命中项）；解析器故障或未命中不阻断执行、
    亦不影响本地取数求值（求值仍走 cross_data，与 engine.py 语义一致：解析仅建立
    canonical 引用身份）。
    """
    tokens = _extract_cross_ref_tokens(expression)
    if not tokens:
        return {}
    # 惰性导入避免潜在循环依赖，并便于测试打桩。
    from app.services.formula_management.engine import resolve_ref

    resolved: dict[str, str] = {}
    pid = str(project_id) if project_id is not None else None
    for token in tokens:
        # resolve_ref 自身 fail-open（内部已捕获异常返回降级结果），此处再兜底一层。
        try:
            # 只建立引用身份，不校验存在性（取数走 cross_data；R5.1 显式声明）
            rr = await resolve_ref(formula_ref=token, project_id=pid, db=db, verify_existence=False)
        except Exception:  # noqa: BLE001 — 对齐 fail-open：解析器故障不阻断执行
            continue
        if getattr(rr, "found", False) and getattr(rr, "addr_id", None):
            resolved[token] = rr.addr_id
    return resolved


async def execute_note_formulas(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    note_section: str,
    *,
    affected_addr_ids: set[str] | None = None,
    cross_data: dict[str, Any] | None = None,
    regenerate: bool = False,
) -> dict[str, Any]:
    """执行附注表格中的自动运算公式，逐表回填（spec note-pull-header-formula-closure R3）。

    - 公式 = 模板层 ∪ 用户集（``_user_formulas``，同目标用户集优先）。模板层：章节存过 ``_formulas`` 用它（旧数据），
      否则按每张表当前结构现算预设（``note_formula_tables.section_preset_formulas``，不落库）；``regenerate=True``
      丢掉存过的 ``_formulas`` 改用现算预设。
    - 目标 ``行:列`` = 第 1 张表、``t{n}:行:列`` = 第 n+1 张；写入 ``_tables``（编辑器与 Word 读的位置），第 1 张表
      写完同步顶层镜像。每张表内按引用关系排序（被引用的格先算），循环引用的格不写。
    - 只写 auto 格（人工 / 锁定不动）；审核类公式（逻辑审核 / 合理性）不回填单元格；求值严格（引用全空 / 取不到 /
      写法认不出 ⇒ 不写、结果里写明原因）；值没变不算更新。
    - 跨表引用（TB / REPORT / WP / NOTE / PRIOR / AGING）有才预载；``cross_data`` 传空字典 ⇒ 首个用到的章节预载进去、
      多章节共用。经 ACNR full_resolve 建立 canonical 身份（Req 17.2）。
    - ``affected_addr_ids``：合并附注 reaggregate 后只刷新这些单元（``_note_cell_addr_id`` 形式，Req 17.6）。

    Returns: ``{"executed", "updated", "results": [{cell, table_index, type, old, new, status, reason?}], "anomalies"}``
    """
    from sqlalchemy.orm.attributes import flag_modified

    from app.services.formula_push.note_writer import sync_first_table_mirror
    from app.services.note_formula_tables import (
        CROSS_REF_RE, evaluate, iter_note_tables, parse_formula_key, section_preset_formulas, table_order,
    )

    note = (await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == note_section,
            DisclosureNote.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()
    if not note or not note.table_data:
        return {"executed": 0, "updated": 0, "results": [], "anomalies": []}

    td = note.table_data
    dropped = bool(regenerate and td.get("_formulas"))
    if dropped:
        td.pop("_formulas", None)
    stored = td.get("_formulas")
    template = stored if isinstance(stored, dict) and stored else section_preset_formulas(td)[0]
    formulas = _merge_formula_sets(template, td.get("_user_formulas"))

    need_cross = any(CROSS_REF_RE.search(str(f.get("expression") or "")) for f in formulas.values())
    if need_cross and not cross_data:
        loaded = await _load_cross_table_data(db, project_id, year)
        if cross_data is None:
            cross_data = loaded
        else:
            cross_data.update(loaded)  # 调用方给的空字典：多章节共用这一次预载
    resolve = (lambda token: _resolve_single_cross_ref(token, cross_data or {})) if need_cross else None

    tables = dict(iter_note_tables(td))
    by_table: dict[int, dict[tuple[int, int], tuple[str, dict]]] = {}
    exec_results: list[dict] = []
    for key, fdef in formulas.items():
        parsed = parse_formula_key(key)
        if parsed is None:
            continue
        if parsed[0] not in tables:
            exec_results.append({"cell": key, "table_index": parsed[0], "type": fdef.get("type"), "old": None,
                                 "new": None, "status": "skipped", "reason": f"章节没有第 {parsed[0] + 1} 张表"})
            continue
        by_table.setdefault(parsed[0], {})[(parsed[1], parsed[2])] = (key, fdef)

    executed = updated = 0
    wrote_first = False
    for t in sorted(by_table):
        cells = by_table[t]
        rows = tables[t].get("rows") if isinstance(tables[t].get("rows"), list) else []
        order, cyclic = table_order({cell: fdef.get("expression") for cell, (_k, fdef) in cells.items()})
        for cell in cyclic:
            key, fdef = cells[cell]
            exec_results.append({"cell": key, "table_index": t, "type": fdef.get("type"), "old": None, "new": None,
                                 "status": "skipped", "reason": "公式之间循环引用"})
        for row_idx, col_idx in order:
            key, formula_def = cells[(row_idx, col_idx)]
            row = rows[row_idx] if row_idx < len(rows) and isinstance(rows[row_idx], dict) else None
            if row is None:
                exec_results.append({"cell": key, "table_index": t, "type": formula_def.get("type"), "old": None,
                                     "new": None, "status": "skipped", "reason": "目标行超出表格"})
                continue
            # 只更新 auto 模式的单元格（Req 17.1）
            if (row.get("_cell_modes") or {}).get(str(col_idx), "auto") != "auto":
                continue
            cell_addr_id = (_note_cell_addr_id(note_section, row_idx, col_idx) if t == 0
                            else f"note:{note_section}!t{t}:{row_idx}:{col_idx}")
            if affected_addr_ids is not None and cell_addr_id not in affected_addr_ids:
                continue
            ftype = formula_def.get("type")
            if (formula_def.get("category") or "auto_calc") != "auto_calc":
                exec_results.append({"cell": key, "table_index": t, "type": ftype, "old": None, "new": None,
                                     "status": "skipped", "reason": "审核类公式不回填单元格"})
                continue
            expression = formula_def.get("expression", "")
            if ftype not in ("vertical_sum", "horizontal_balance", "book_value") and CROSS_REF_RE.search(str(expression)):
                resolved_refs = await _resolve_cross_refs_via_acnr(expression, project_id, db)
                if resolved_refs:
                    formula_def["resolved_refs"] = resolved_refs
            value, reason = evaluate(expression, rows, resolve)
            executed += 1
            values = row.get("values") if isinstance(row.get("values"), list) else []
            old_value = values[col_idx] if col_idx < len(values) else None
            if value is None:
                exec_results.append({"cell": key, "table_index": t, "type": ftype, "old": old_value, "new": None,
                                     "status": "skipped", "reason": reason})
                continue
            new_value = float(value)
            formula_def["evaluated_at"] = datetime.now(timezone.utc).isoformat()
            formula_def["addr_id"] = cell_addr_id  # Req 17.5：溯源 / reaggregate 精准刷新同一身份
            formula_def.setdefault("binding_id", None)
            exec_results.append({"cell": key, "table_index": t, "type": ftype, "old": old_value, "new": new_value,
                                 "status": "ok"})
            if _same_amount(old_value, new_value):
                continue
            values = list(values)
            while len(values) <= col_idx:
                values.append(None)
            values[col_idx] = new_value
            row["values"] = values
            updated += 1
            wrote_first = wrote_first or t == 0

    if wrote_first:
        sync_first_table_mirror(td)  # 第 1 张表写进 _tables[0] ⇒ 顶层镜像跟着改
    if updated or dropped or (stored and executed):
        note.table_data = td
        flag_modified(note, "table_data")
        await db.flush()

    anomalies = [{"cell": r["cell"], "table_index": r["table_index"], "message": "合计行为0，请检查子项是否有数据"}
                 for r in exec_results if r["status"] == "ok" and r["new"] == 0 and r.get("type") == "vertical_sum"]
    return {"executed": executed, "updated": updated, "results": exec_results, "anomalies": anomalies}


def _same_amount(old: Any, new: float) -> bool:
    """值没变（差 ≤ 0.005，与公式推送同一容差）不重写、不算更新。"""
    from app.services.consol_note_table_totals import to_decimal

    current = to_decimal(old)
    return current is not None and abs(float(current) - new) <= 0.005


# ---------------------------------------------------------------------------
# 跨表数据加载
# ---------------------------------------------------------------------------


def _index_prior_dynamic_rows(
    prior_index: dict[str, Any],
    *,
    keys: list[str],
    rows: list[dict],
) -> None:
    """把上年附注 dynamic_data 行按 label 索引到 ``prior_index[key][label]``.

    设计（Sprint A.3.2）：
    - 仅 row_type='dynamic_data' 的行参与索引（跳过 anchor / marker_end / 合计行）
    - label 取 ``row.label`` (trim 后)，空 label 跳过
    - 期末 = values[0]，期初 = values[1]（与 2-arg PRIOR total_rows 列对齐）
    - 同 label 多次出现 → 按累加（同名客户多笔）
    - 与 2-arg 兼容：``prior_index[key]`` 已有 closing/opening 平铺时不覆盖；额外把
      label dict 写到同 key 下（嵌套结构），通过 ``isinstance(...,dict) and 'closing'/'opening'``
      可区分。
    """
    if not keys or not isinstance(rows, list):
        return

    # 关键修复：上层 _load_cross_table_data 把 section_number / section_title 都
    # 指向同一个 entry dict（aliasing），如果直接按 key 迭代会对同一个 dict 重复
    # 累加。此处先按身份去重 section_dict（保留首次出现）。
    seen_ids: set[int] = set()
    unique_dicts: list[dict] = []
    for key in keys:
        section_dict = prior_index.get(key)
        if not isinstance(section_dict, dict):
            section_dict = {}
            prior_index[key] = section_dict
        if id(section_dict) in seen_ids:
            continue
        seen_ids.add(id(section_dict))
        unique_dicts.append(section_dict)

    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("row_type") != "dynamic_data":
            continue
        if r.get("is_total"):
            continue
        label = r.get("label")
        if not isinstance(label, str):
            continue
        label = label.strip()
        if not label:
            continue
        vals = r.get("values") or []
        closing = vals[0] if len(vals) > 0 else None
        opening = vals[1] if len(vals) > 1 else None
        try:
            closing_v = float(closing) if closing is not None else None
        except (TypeError, ValueError):
            closing_v = None
        try:
            opening_v = float(opening) if opening is not None else None
        except (TypeError, ValueError):
            opening_v = None

        for section_dict in unique_dicts:
            existing = section_dict.get(label)
            if isinstance(existing, dict) and ("closing" in existing or "opening" in existing):
                # 同 label 多次出现 → 累加
                if closing_v is not None:
                    existing["closing"] = (existing.get("closing") or 0.0) + closing_v
                if opening_v is not None:
                    existing["opening"] = (existing.get("opening") or 0.0) + opening_v
            else:
                section_dict[label] = {
                    "closing": closing_v if closing_v is not None else 0.0,
                    "opening": opening_v if opening_v is not None else 0.0,
                }


async def _load_cross_table_data(db: AsyncSession, project_id: UUID, year: int) -> dict[str, Any]:
    """预加载跨表数据供公式引用。

    Returns: {
        "report": {"BS-002": {"current": 1000, "prior": 900}, ...},
        "tb": {"1001": {"audited": 500, "unadjusted": 480, "opening": 450}, ...},
        "note_tables": {"五、3": <disclosure_notes.table_data>, ...},  # NOTE 按章节 / 行 / 列取数
        "wp": {"E1": {"审定表E1!B5": 50.0, "审定表E1!C5": 40.0}, ...},
        "prior": {"货币资金": {"closing": 1234.56, "opening": 1100.0}, ...},  # Sprint 1.5 D4 新增
        "aging": {"应收账款": {"1年以内": 100.0, "1-2年": 50.0, ...}, ...},  # Sprint 1.5 D4 新增
    }
    """
    from app.models.report_models import FinancialReport
    from app.models.audit_platform_models import TrialBalance
    from app.models.workpaper_models import WorkingPaper, WpIndex

    cross_data: dict[str, Any] = {
        "report": {},
        "tb": {},
        "note_tables": {},
        "wp": {},
        "prior": {},   # Sprint 1.5 Task 1.5.2: 上年附注期末/期初值（按 account_name 索引）
        "aging": {},   # Sprint 1.5 Task 1.5.2: 账龄分桶（按 account_name 索引）
    }

    # 加载报表数据
    try:
        async with db.begin_nested():  # 读失败只回滚这一步，不让调用方事务停在中止状态
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
        async with db.begin_nested():  # 读失败只回滚这一步，不让调用方事务停在中止状态
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
        async with db.begin_nested():  # 读失败只回滚这一步，不让调用方事务停在中止状态
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

    # 加载本年度附注表格：NOTE 引用按章节 / 行 / 列取数（与严格求值同一套匹配，spec formula-fetch-followup-defect-closure
    # R5.3）。原先只存每节最后一个合计行的前两列（「期末」= 第一列、「期初」= 第二列），引用明细行或第三列都取错数；
    # 也没排除已删除的附注（同章节的删除行可能盖掉现行行）
    try:
        async with db.begin_nested():  # 读失败只回滚这一步，不让调用方事务停在中止状态
            result = await db.execute(
                sa.select(DisclosureNote.note_section, DisclosureNote.table_data).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
        for section, table_data in result.all():
            if section and isinstance(table_data, dict):
                cross_data["note_tables"][section] = table_data
    except Exception:
        pass

    # ─── Sprint 1.5 Task 1.5.2: 加载上年（year-1）附注 → cross_data["prior"] ───
    # =PRIOR("货币资金","期末") 取上年附注期末值；按 account_name / section_title 索引
    # 失败静默 — 使函数返 None 而不抛错
    try:
        async with db.begin_nested():  # 读失败只回滚这一步，不让调用方事务停在中止状态
            prior_result = await db.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year - 1,
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
        for prior_note in prior_result.scalars().all():
            if not prior_note.table_data or not isinstance(prior_note.table_data, dict):
                continue
            rows = prior_note.table_data.get("rows") or []
            total_rows = [r for r in rows if r.get("is_total")]
            if not total_rows:
                continue
            values = total_rows[-1].get("values") or []
            closing = float(values[0]) if values and values[0] is not None else None
            opening = float(values[1]) if len(values) > 1 and values[1] is not None else None
            entry = {
                "closing": closing if closing is not None else 0.0,
                "opening": opening if opening is not None else 0.0,
            }
            # 同一科目/章节多 key 索引（account_name / section_title / section_number）
            section_title = (prior_note.section_title or "").strip()
            if section_title:
                cross_data["prior"][section_title] = entry
            section_number = (prior_note.note_section or "").strip()
            if section_number and section_number not in cross_data["prior"]:
                cross_data["prior"][section_number] = entry

            # ─── Sprint A.3.2：动态行 label 索引（按 section_number / section_title 分组）───
            # 把 dynamic_data 行按 label → {期末: closing, 期初: opening} 写到对应 section dict。
            # 期末列 = values[0]（首列数据列），期初列 = values[1]，与 2-arg 取 total_rows 列规则一致。
            try:
                _index_prior_dynamic_rows(
                    cross_data["prior"],
                    keys=[k for k in (section_number, section_title) if k],
                    rows=rows,
                )
            except Exception:
                # graceful：dynamic 索引失败不影响 2-arg 总行索引
                pass
    except Exception:
        pass

    # ─── Sprint 1.5 Task 1.5.2: 加载账龄分桶 → cross_data["aging"] ───
    # =AGING("应收账款","1年以内") 从 TbAuxLedger 反推 5 桶分布
    # 客户未提供辅助序时账时 cross_data["aging"] 为空 dict → =AGING 返 None
    try:
        from app.models.audit_platform_models import TbAuxLedger
        from app.services.note_source_resolvers import _AGING_BUCKETS

        # 加载 wp_account_mapping 关联的科目集合（保守全量加载，避免遗漏）
        from pathlib import Path
        import json as _json
        mapping_path = (
            Path(__file__).parent.parent.parent / "data" / "wp_account_mapping.json"
        )
        account_to_name: dict[str, str] = {}  # account_code -> account_name
        if mapping_path.exists():
            try:
                with open(mapping_path, "r", encoding="utf-8-sig") as f:
                    mappings = _json.load(f).get("mappings", [])
                for m in mappings:
                    name = m.get("account_name") or ""
                    if not name:
                        continue
                    for code in (m.get("account_codes") or []):
                        if code and code not in account_to_name:
                            account_to_name[code] = name
            except Exception:
                pass

        if account_to_name:
            from datetime import date as _date
            base_date = _date(int(year), 12, 31)
            async with db.begin_nested():  # 读失败只回滚这一步，不让调用方事务停在中止状态
                ledger_result = await db.execute(
                    sa.select(
                        TbAuxLedger.account_code,
                        TbAuxLedger.voucher_date,
                        TbAuxLedger.debit_amount,
                        TbAuxLedger.credit_amount,
                    ).where(
                        TbAuxLedger.project_id == project_id,
                        TbAuxLedger.year == year,
                        TbAuxLedger.is_deleted == sa.false(),
                        TbAuxLedger.voucher_date.isnot(None),
                        TbAuxLedger.account_code.in_(list(account_to_name.keys())),
                    ).limit(100000)  # 大数据量保护
                )
            # 累计：account_name -> bucket -> total
            aging_acc: dict[str, dict[str, float]] = {}
            for code, vdate, deb, cre in ledger_result.all():
                if vdate is None:
                    continue
                name = account_to_name.get(code)
                if not name:
                    continue
                try:
                    days = (base_date - vdate).days
                except Exception:
                    continue
                if days < 0:
                    continue
                # 分桶
                bucket = None
                for bk, (low, high) in _AGING_BUCKETS.items():
                    if low <= days < high:
                        bucket = bk
                        break
                if bucket is None:
                    continue
                d = float(deb) if deb is not None else 0.0
                c = float(cre) if cre is not None else 0.0
                slot = aging_acc.setdefault(name, {})
                slot[bucket] = slot.get(bucket, 0.0) + (d - c)
            cross_data["aging"] = aging_acc
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
    - PRIOR('account_name','期末'|'期初')                   (Sprint 1.5 D4)
    - AGING('account_name','1年以内'|'1-2年'|...|'5年以上')  (Sprint 1.5 D4)

    无法解析或科目/底稿/附注不存在时返回 None；TB 列存在但 account 不存在 → 0。
    """
    import re

    if not token or not isinstance(token, str):
        return None

    s = token.strip()

    # ─── Sprint A.3.2: PRIOR('section_number','label','期末'|'期初') ───
    # 上年附注按章节内动态行 label 匹配（dynamic_data 行）。
    # 索引：cross_data['prior'][section_number][label] = {'closing': ..., 'opening': ...}
    # 缺数据 → None；先试 3-arg 再降级到 2-arg 兼容老调用。
    m = re.fullmatch(r"\s*PRIOR\('([^']+)','([^']+)','([^']+)'\)\s*", s)
    if m:
        section = m.group(1)
        label = m.group(2)
        period = m.group(3)
        section_data = cross_data.get("prior", {}).get(section)
        if not isinstance(section_data, dict):
            return None
        # 嵌套 label dict 才算 3-arg 命中（防止与 2-arg 的 closing/opening 平铺结构混淆）
        label_data = section_data.get(label)
        if not isinstance(label_data, dict):
            return None
        if "期末" in period or period == "closing":
            val = label_data.get("closing")
            return float(val) if val is not None else None
        if "期初" in period or period == "opening":
            val = label_data.get("opening")
            return float(val) if val is not None else None
        return None

    # ─── Sprint 1.5 Task 1.5.2: PRIOR('account_name','期末'|'期初') ───
    # 上年附注期末/期初值取数；缺数据 → None（章节标 not_applicable）
    m = re.fullmatch(r"\s*PRIOR\('([^']+)','([^']+)'\)\s*", s)
    if m:
        account_name = m.group(1)
        period = m.group(2)
        prior_data = cross_data.get("prior", {}).get(account_name)
        if prior_data is None:
            return None
        if "期末" in period or period == "closing":
            val = prior_data.get("closing")
            return float(val) if val is not None else None
        if "期初" in period or period == "opening":
            val = prior_data.get("opening")
            return float(val) if val is not None else None
        return None

    # ─── Sprint 1.5 Task 1.5.2: AGING('account_name','bucket') ───
    # 5 桶：1年以内 / 1-2年 / 2-3年 / 3-5年 / 5年以上
    # 客户未提供辅助序时账时 cross_data["aging"] 为空 dict → 返 None
    m = re.fullmatch(r"\s*AGING\('([^']+)','([^']+)'\)\s*", s)
    if m:
        account_name = m.group(1)
        bucket = m.group(2)
        # bucket 白名单（与 _AGING_BUCKETS 对齐）
        valid_buckets = {"1年以内", "1-2年", "2-3年", "3-5年", "5年以上"}
        if bucket not in valid_buckets:
            return None
        aging_data = cross_data.get("aging", {}).get(account_name)
        if aging_data is None:
            # 客户未提供辅助序时账（aging 整体为空）或该科目无账龄数据 → None
            return None
        val = aging_data.get(bucket)
        if val is None:
            # 该桶在该科目下无数据（未发生过该龄段挂账）→ 返 0（同 TB 行为：科目存在桶不存在）
            return 0.0
        return float(val)

    # WP('wp_code','sheet','cell_ref')（参数间可有空格：与保存前校验的写法一致）
    m = re.fullmatch(r"\s*WP\(\s*'([^']+)'\s*,\s*'([^']*)'\s*,\s*'([^']+)'\s*\)\s*", s)
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

    # NOTE('章节','行'[,'列'])：按章节 / 行 / 列取数，与严格求值同一套匹配（含两参、参数间空格；spec
    # formula-fetch-followup-defect-closure R5.3）。原先忽略行名一律取最后一个合计行、「期末」取第一列。取不到 ⇒ None
    from app.services.formula_ref_preload import NOTE_RE, _note_cell

    m = NOTE_RE.fullmatch(s)
    if m:
        section = m.group(1).strip()
        table_data = cross_data.get("note_tables", {}).get(section)
        if table_data is None:
            return None
        value, _reason = _note_cell(table_data, section, m.group(2), m.group(3) or "")
        return float(value) if value is not None else None

    # REPORT('row_code','period')
    m = re.fullmatch(r"\s*REPORT\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)\s*", s)
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

    # TB('account_code','column')：科目按前缀合计（与报表 / 预载同口径、与保存前校验一致；原先只认精确码，
    # 一级科目码在试算表里只有下级行时恒取 0）
    m = re.fullmatch(r"\s*TB\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)\s*", s)
    if m:
        account_code = m.group(1).strip()
        column = m.group(2).strip()
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
        hits = [v for code, v in cross_data.get("tb", {}).items() if code and code.startswith(account_code)]
        # 列名合法但该科目及其下级都不存在 → 0
        return float(sum(float(v.get(col_key, 0) or 0) for v in hits))

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Sprint A.3.1：REGION('region_name','col_id', agg='sum') — 同表动态区域聚合
# ─────────────────────────────────────────────────────────────────────────────


_REGION_AGG_FUNCS = {
    "sum": lambda xs: sum(xs),
    "count": lambda xs: float(len(xs)),
    "max": lambda xs: max(xs) if xs else None,
    "min": lambda xs: min(xs) if xs else None,
    "avg": lambda xs: (sum(xs) / len(xs)) if xs else None,
}


def resolve_region_token(
    token: str,
    table_data: dict | None,
) -> float | None:
    """解析 REGION('region_name','col_id', agg='sum'|'count'|'max'|'min'|'avg') token.

    引用同表内的动态区域 ``_dynamic_regions[name=region_name]`` 在指定 col_id
    的聚合值（仅 axis=row 区域 + row_type=dynamic_data 行参与聚合）。

    Args:
        token: 形如 "REGION('客户','col_amount_end', agg='sum')"
        table_data: 含 _dynamic_regions / _columns_meta / rows 的 dict

    Returns:
        聚合值（float），无匹配 region / col / 数据时返 None；
        agg='count' 始终返非负数（无数据返 0.0）。

    支持 agg：sum / count / max / min / avg；默认 sum。

    无效输入（None / 非字符串 / 解析失败 / 缺 region / 缺 col_id）→ 返 None。
    """
    import re

    if not token or not isinstance(token, str):
        return None
    if not isinstance(table_data, dict):
        return None

    s = token.strip()
    # REGION('name','col', agg='sum')   或   REGION('name','col')
    m = re.fullmatch(
        r"\s*REGION\("
        r"\s*'([^']+)'\s*,"
        r"\s*'([^']+)'"
        r"(?:\s*,\s*agg\s*=\s*['\"]([^'\"]+)['\"]\s*)?"
        r"\)\s*",
        s,
    )
    if not m:
        return None

    region_name = m.group(1)
    col_id = m.group(2)
    agg_raw = (m.group(3) or "sum").strip().lower()
    agg = _REGION_AGG_FUNCS.get(agg_raw)
    if agg is None:
        return None

    # 1. 找到匹配 region（axis=row）
    regions = table_data.get("_dynamic_regions") or []
    target_region = None
    for r in regions:
        if not isinstance(r, dict):
            continue
        if r.get("axis") != "row":
            continue
        if r.get("name") == region_name:
            target_region = r
            break
    if target_region is None:
        return None

    start_idx = target_region.get("start_idx")
    end_idx = target_region.get("end_idx")
    if not isinstance(start_idx, int) or not isinstance(end_idx, int):
        return None
    if end_idx < start_idx:
        return None

    # 2. 找到 col_id 在 _columns_meta 中的位置
    columns_meta = table_data.get("_columns_meta") or []
    col_pos: int | None = None
    for idx, col in enumerate(columns_meta):
        if isinstance(col, dict) and col.get("id") == col_id:
            col_pos = idx
            break
    if col_pos is None:
        return None

    # 3. 在 [start_idx, end_idx] 范围内迭代 dynamic_data 行
    rows = table_data.get("rows") or []
    if not isinstance(rows, list):
        return None

    nums: list[float] = []
    for i in range(start_idx, min(end_idx + 1, len(rows))):
        r = rows[i]
        if not isinstance(r, dict):
            continue
        if r.get("row_type") != "dynamic_data":
            continue
        vals = r.get("values")
        if not isinstance(vals, list) or col_pos >= len(vals):
            continue
        v = vals[col_pos]
        if v is None:
            continue
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue

    if agg_raw == "count":
        # count 始终返非负数；无 dynamic_data 行时返 0
        return float(len(nums))

    if not nums:
        return None

    try:
        result = agg(nums)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return float(result) if result is not None else None


def exec_with_region(
    expression: Any,
    cross_data: dict[str, Any],
    table_data: dict | None,
) -> float | None:
    """REGION-aware 表达式解析：直接迭代 +/- 组合的 REGION + 其他跨表 token.

    支持组合：``REGION('A','col_x') + TB('1001','期末') - REGION('B','col_y')``

    Args:
        expression: 含 REGION + 其他 token 的表达式
        cross_data: 跨表数据（TB / WP / REPORT / NOTE / PRIOR / AGING）
        table_data: 同表内 _dynamic_regions / _columns_meta / rows

    Returns:
        - 数值（所有 token 解析成功）
        - None（任一 token 解析失败 / 表达式不合法）
    """
    import re

    if expression is None or not isinstance(expression, str):
        return None
    s = expression.strip()
    if not s:
        return None

    # 整体单 REGION 直接走 resolver（避免 +/- 拆分）
    region_pattern = re.compile(
        r"REGION\(\s*'[^']+'\s*,\s*'[^']+'(?:\s*,\s*agg\s*=\s*['\"][^'\"]+['\"])?\s*\)"
    )
    if region_pattern.fullmatch(s):
        return resolve_region_token(s, table_data)

    # 表达式由 +/- 拼接的 token 组成（REGION / TB / REPORT / WP / NOTE / PRIOR / AGING）
    token_pattern = re.compile(
        r"([+-]?)\s*("
        r"REGION\(\s*'[^']+'\s*,\s*'[^']+'(?:\s*,\s*agg\s*=\s*['\"][^'\"]+['\"])?\s*\)"
        r"|"
        r"(?:TB|REPORT|WP|NOTE|PRIOR|AGING)\([^)]*\)"
        r")"
    )
    matches = token_pattern.findall(s)
    if not matches:
        return None

    # 校验整体由这些 token + +/- 组成（不能混入未识别字符）
    rebuilt = "".join(f"{sign or '+'}{token}" for sign, token in matches)
    s_no_space = re.sub(r"\s+", "", s)
    rec_no_space = re.sub(r"\s+", "", rebuilt)
    if rec_no_space.lstrip("+") != s_no_space.lstrip("+"):
        return None

    total = 0.0
    for sign, token in matches:
        if token.startswith("REGION("):
            val = resolve_region_token(token, table_data)
        else:
            val = _resolve_single_cross_ref(token, cross_data)
        if val is None:
            return None
        total += -val if sign == "-" else val
    return total


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
        r"([+-]?)\s*((?:TB|REPORT|WP|NOTE|PRIOR|AGING)\([^)]*\))",
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
    """计算单个附注章节的公式覆盖率（全部表）。

    覆盖率 = 有预设公式的金额格 / 全部金额格（不含标签列；比例 / 说明列不计）。预设公式与执行器、公式管理同一套
    （``note_formula_tables.section_preset_formulas``：按结构生成的合计 / 账面价值 + 明细行取数公式）；原先按
    ``_check_presets`` 的英文预设名另算一遍（不分段的求和也算「已配置」，spec note-pull-followup-closure R8）。

    Returns: {"total_cells": N, "configured_cells": M, "coverage_pct": X.X}
    """
    from app.services.note_formula_tables import (
        amount_columns, iter_note_tables, parse_formula_key, section_preset_formulas,
    )

    if not table_data or not isinstance(table_data, dict):
        return {"total_cells": 0, "configured_cells": 0, "coverage_pct": 0.0}

    formulas, _notes = section_preset_formulas(table_data)
    targets = {parsed for key in formulas if (parsed := parse_formula_key(key))}
    total_cells = configured_cells = 0
    for t, table in iter_note_tables(table_data):
        rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        columns = set(amount_columns(table)) if table.get("headers") and rows else set()
        total_cells += len(rows) * len(columns)
        configured_cells += sum(1 for ti, r, c in targets if ti == t and r < len(rows) and c in columns)

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
