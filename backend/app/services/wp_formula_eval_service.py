"""自定义底稿公式表达式求值（custom-workpaper-formula-binding 补强）。

将 wp_formula.expression 求值为 Decimal，供写回 parsed_data 目标单元格展示。

支持的取数函数（spec formula-governance-coverage-closure R6；与函数支持矩阵 ``wp_evaluator`` 列一致）：
TB / SUM_TB / WP（含三参与 ``Sheet!Cell`` 跨 sheet 引用）/ ROW / SUM_ROW / REPORT / NOTE / PREV / AUX / ADJ。
PREV / AUX / ROW / SUM_ROW / REPORT / NOTE 经 ``formula_ref_preload`` 严格按值代入（取不到数写进错误清单，
不代入 0）；PREV 三参（上年同底稿）按本底稿该字段的现行取数定义在上年数据上求值（``prev_wp_field``，spec
formula-fetch-and-wp-generation-defect-closure R2）；ADJ 经统一预载层（底稿口径：不排除底稿来源的调整分录）交 L1
内核。序时账（LEDGER / COUNT_LEDGER / LEDGER_DETAIL）、TB_AUX 不支持：保存时 422，求值时报错不求值。
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.services.dataset_query import get_active_filter
from app.services.formula_engine import COLUMN_ALIASES, FormulaContext, execute
from app.services.formula_engine import _A1_FIELD, _D23_SHEET_MARKER, WPExecutor
from app.services.four_table.occurrence_by_standard_code import (
    CREDIT_KEY,
    DEBIT_KEY,
    fetch_occurrence_by_standard_code,
)

logger = logging.getLogger(__name__)

#: 参数间允许空白（库内有 ``TB('1231', '期末余额')`` 写法）；前面不能紧挨标识符字符（``SUM_TB(`` 里的 ``TB(`` 不算）
_START = r"(?<![A-Za-z0-9_])"
_ARG = r"\s*'([^']+)'\s*"
_TB_PATTERN = re.compile(_START + r"TB\(" + _ARG + "," + _ARG + r"\)")
_SUM_TB_PATTERN = re.compile(_START + r"SUM_TB\(" + _ARG + "," + _ARG + r"\)")
# 三参 WP（D2-3 嵌套寻址）须先于两参匹配：WP('D2','坏账准备明细表D2-3','本期计提合计')
_WP3_PATTERN = re.compile(_START + r"WP\(" + _ARG + "," + _ARG + "," + _ARG + r"\)")
_WP_PATTERN = re.compile(_START + r"WP\(" + _ARG + "," + _ARG + r"\)")
#: 函数调用（先把引号内的文字抹掉，避免 sheet 名里的括号被当成函数）
_CALL_RE = re.compile(_START + r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_QUOTED_RE = re.compile(r"'[^']*'")
#: 全部代入之后还允许留给 L1 的函数：ADJ（预载）与纯运算函数
_KERNEL_FUNCTIONS = frozenset({"ADJ", "ABS", "ROUND", "MAX", "MIN", "IF", "PLACEHOLDER"})

#: 工作底稿可编辑公式不支持的函数（函数支持矩阵之外的 L1 函数）及原因。
#:
#: 历史（d-cycle-four-table-extraction-formulas 决策3）：Tier A 可编辑公式曾只支持 TB / SUM_TB / WP，
#: AUX / PREV 一并拒绝；spec formula-governance-coverage-closure R6 补齐了 AUX / PREV（两参）等 7 个函数，
#: PREV 三参由 spec formula-fetch-and-wp-generation-defect-closure R2 补齐；序时账归集仍由底稿预填充（Tier B）承担。
UNSUPPORTED_FUNCTION_REASONS: dict[str, str] = {
    "LEDGER": "序时账取数由底稿预填充承担，可编辑公式不支持",
    "COUNT_LEDGER": "序时账笔数由底稿预填充承担，可编辑公式不支持",
    "LEDGER_DETAIL": "序时账明细由底稿预填充承担，可编辑公式不支持",
    "TB_AUX": "辅助维度汇总请写 AUX('科目','辅助类型','列')",
}


def _strip_formula(expression: str | None) -> str:
    raw = (expression or "").strip()
    return raw[1:] if raw.startswith("=") else raw


def _called_functions(expression: str) -> list[str]:
    """按出现顺序列出调用的函数名（大写、去重；引号内文字不算）。"""
    names: list[str] = []
    for m in _CALL_RE.finditer(_QUOTED_RE.sub("''", expression)):
        name = m.group(1).upper()
        if name not in names:
            names.append(name)
    return names


def unsupported_formula_function_issues(expression: str | None) -> list[dict[str, str]]:
    """工作底稿可编辑公式里不支持的函数 → ``[{function, reason}]``（按声明顺序）。

    纯字符串检测（不依赖 DB），供保存端点写库前调用；求值时同样据此不求值（不静默 0）。
    """
    raw = _strip_formula(expression)
    if not raw:
        return []
    called = set(_called_functions(raw))
    return [{"function": name, "reason": reason}
            for name, reason in UNSUPPORTED_FUNCTION_REASONS.items() if name in called]


def find_unsupported_formula_functions(expression: str | None) -> list[str]:
    """不支持的函数名列表（去重、保持声明顺序）；详见 :func:`unsupported_formula_function_issues`。"""
    return list(dict.fromkeys(issue["function"] for issue in unsupported_formula_function_issues(expression)))

#: 列名 → ``trial_balance`` 的**真实列**。
#:
#: 🔴 **只许出现 `TrialBalance` 上真实存在的列名**（守卫
#: ``test_formula_tb_sign_passthrough::test_wp_formula_eval_column_map_is_pure_column``
#: 按白名单钉死）。改造前这里有两条死映射::
#:
#:     "借方发生额": "debit_amount",     # TrialBalance 无此列
#:     "贷方发生额": "credit_amount",    # TrialBalance 无此列
#:
#: 而取值处写 ``getattr(row, field, None)`` **带默认值** ⇒ 取不到列返 ``None``
#: → 归一成 ``Decimal("0")`` ⇒ **看着已注册、实则恒 0**（不是崩溃，所以没人发现）。
#: `trial_balance` 只有余额与调整列，**发生额明细只在 `tb_balance`**，故发生额
#: 一律走 :data:`_OCCURRENCE_COLUMNS` 分支，禁再写进本表。
_COLUMN_MAP = {
    "期末余额": "audited_amount",
    "审定数": "audited_amount",
    "年初余额": "opening_balance",
    "期初余额": "opening_balance",
    "未审数": "unadjusted_amount",
    "RJE调整": "rje_adjustment",
    "AJE调整": "aje_adjustment",
}

#: 发生额列名 → 归集结果里的**规范字段名**（`本期借方` / `本期贷方`）。
#:
#: 别名集合与规范名都取自 `formula_engine.COLUMN_ALIASES` / 共享件
#: `four_table.occurrence_by_standard_code`，**不在本文件另立第二套词表**。
#: 数据源 = ``tb_balance.debit_amount`` / ``credit_amount``，经
#: :func:`fetch_occurrence_by_standard_code` 按标准码归集（含叶子聚合，父子不双算）。
_OCCURRENCE_COLUMNS: dict[str, str] = {
    alias: canonical
    for alias, canonical in COLUMN_ALIASES.items()
    if canonical in (DEBIT_KEY, CREDIT_KEY)
}

#: 派生列：不是 ``trial_balance`` 的真实列，由两列相减得出（被减列, 减列）。与 L1 预载（``formula_preloader``）、
#: 推送取数（``formula_push.sources``）同口径：本期发生额 = 审定数 − 期初余额。
#: 🔴 原先 ``本期发生额`` 不在 :data:`_COLUMN_MAP` 里，``.get(列名, "audited_amount")`` 回退成审定数，
#: 专门处理它的 ``_period_amount`` 分支永远走不到（spec formula-fetch-followup-defect-closure R7）。
_DERIVED_COLUMNS: dict[str, tuple[str, str]] = {
    "本期发生额": ("audited_amount", "opening_balance"),
}


def _balance_field(column_name: str) -> str | tuple[str, str]:
    """余额 / 派生列名 → 真实列名或（被减列, 减列）；未注册列名抛 ``ValueError``（不再静默按审定数取）。"""
    if column_name in _DERIVED_COLUMNS:
        return _DERIVED_COLUMNS[column_name]
    field = _COLUMN_MAP.get(column_name)
    if field is None:
        raise ValueError(f"列名「{column_name}」未注册，无法取值（可用：{'、'.join(COLUMN_ALIASES)}）")
    return field


def _row_amount(row: TrialBalance, field: str | tuple[str, str]) -> Decimal:
    if isinstance(field, tuple):
        minuend, subtrahend = field
        return (getattr(row, minuend) or Decimal("0")) - (getattr(row, subtrahend) or Decimal("0"))
    val = getattr(row, field, None)
    return val if val is not None else Decimal("0")


async def _resolve_occurrence(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    column_name: str,
) -> dict[str, dict[str, Decimal]]:
    """发生额取数（`tb_balance` 叶子归集），供 TB / SUM_TB 的发生额列共用。

    🔴 **不要在 `TrialBalance` 上取发生额** —— 该表没有 `debit_amount` /
    `credit_amount` 两列（实测 ORM 列只有 `unadjusted_amount` / `rje_adjustment` /
    `aje_adjustment` / `audited_amount` / `opening_balance`），而原实现走
    `getattr(row, field, None)` **带默认值** ⇒ 取不到列时静默返 `Decimal("0")`，
    使「借方发生额 / 贷方发生额」这两个已登记的列名**恒为 0**（看着注册了、
    实则死映射，2026-08-06 实测）。该 service 有 24 个生产消费方
    （D1~D7 / H5~H10 / I1~I6 全部 render 策略）。

    fail-open 由 `fetch_occurrence_by_standard_code` 内部承担（异常返 `{}`）。
    """
    return await fetch_occurrence_by_standard_code(db, project_id, year)


async def _resolve_tb(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    account_code: str,
    column_name: str,
) -> Decimal:
    # ── 发生额列走 tb_balance（按**列名**判定，且门控早于 TrialBalance 查询） ──
    #
    # 🔴 必须按 `column_name` 判、不能按 `_COLUMN_MAP` 的结果判：发生额列已从
    # `_COLUMN_MAP` 移除，`.get(column_name, "audited_amount")` 对它们会回退成
    # 「审定数」—— 那正是本次要消除的静默回退，只是换了个位置。
    canonical = _OCCURRENCE_COLUMNS.get(column_name)
    if canonical is not None:
        occ = await _resolve_occurrence(db, project_id, year, column_name)
        return occ.get(account_code, {}).get(canonical, Decimal("0"))
    field = _balance_field(column_name)
    # 数据集版本口径统一（与 Tier B prefill 同口径，见决策3）：
    # 用 get_active_filter 替代裸 is_deleted，规避读到 superseded/staged 数据。
    active_filter = await get_active_filter(
        db, TrialBalance.__table__, project_id, year
    )
    row = (
        await db.execute(
            sa.select(TrialBalance).where(
                active_filter,
                TrialBalance.standard_account_code == account_code,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return Decimal("0")
    return _row_amount(row, field)


async def _resolve_sum_tb(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    code_range: str,
    column_name: str,
) -> Decimal:
    parts = code_range.split("~")
    if len(parts) != 2:
        return Decimal("0")
    start_code, end_code = parts[0].strip(), parts[1].strip()
    # ── 发生额区间求和走 tb_balance（同 `_resolve_tb`，按列名判定并早于查询） ──
    canonical = _OCCURRENCE_COLUMNS.get(column_name)
    if canonical is not None:
        occ = await _resolve_occurrence(db, project_id, year, column_name)
        total = Decimal("0")
        for code, cols in occ.items():
            # 与 TrialBalance 分支同口径：按标准码字符串区间比较
            if start_code <= code <= end_code:
                total += cols.get(canonical, Decimal("0"))
        return total
    field = _balance_field(column_name)
    # 数据集版本口径统一（与 Tier B prefill 同口径，见决策3）。
    active_filter = await get_active_filter(
        db, TrialBalance.__table__, project_id, year
    )
    rows = (
        await db.execute(
            sa.select(TrialBalance).where(
                active_filter,
                TrialBalance.standard_account_code >= start_code,
                TrialBalance.standard_account_code <= end_code,
            )
        )
    ).scalars().all()
    total = Decimal("0")
    for row in rows:
        total += _row_amount(row, field)
    return total


def _resolve_cross_sheet_refs(
    raw: str,
    parsed_data: dict | None,
    *,
    project_id: str | None = None,
    parent_wp_code: str | None = None,
) -> tuple[str, list[str]]:
    """将 ``=Sheet!Cell`` 跨 sheet 引用经 CrossSheetResolver 追溯解析为值后替换（Req 14.2）。

    复用 ``custom_query.cross_sheet_resolver.CrossSheetResolver``（BFS + 环检测 +
    ACNR addr_id 解析）追溯每个跨 sheet 引用链，取链首节点（目标单元）的值代入
    表达式；缺失/无法解析 → 代入 0 并记 warning（单条失败不阻断整体，Req 15.5 语义）。

    Returns:
        (substituted_expr, errors)。无 parsed_data 或无跨 sheet 引用时原样返回。
    """
    errors: list[str] = []
    if not parsed_data:
        return raw, errors

    # 延迟导入避免与 custom_query 包的循环依赖。
    from app.services.custom_query.cross_sheet_resolver import (
        CrossSheetResolver,
        _CROSS_SHEET_REF_PATTERN,
    )

    matches = list(_CROSS_SHEET_REF_PATTERN.finditer(raw))
    if not matches:
        return raw, errors

    # 只取值、不取身份：resolve_identity=False（async 上下文里同步桥接只会降级，需求 8.2）
    resolver = CrossSheetResolver(
        project_id=project_id, parent_wp_code=parent_wp_code, resolve_identity=False
    )
    expr = raw
    for match in matches:
        ref_text = match.group(0)
        ref_sheet = match.group(1) or match.group(2)
        ref_cell = match.group(3).upper()
        try:
            chain_resp = resolver.resolve(parsed_data, ref_sheet, ref_cell)
            node = chain_resp.chain[0] if chain_resp.chain else None
            raw_val = node.value if node is not None else None
            if raw_val is None:
                val = Decimal("0")
                errors.append(f"{ref_text}: 跨 sheet 引用目标缺失，代入 0")
            else:
                try:
                    val = Decimal(str(raw_val).replace(",", ""))
                except (InvalidOperation, ValueError):
                    val = Decimal("0")
                    errors.append(f"{ref_text}: 跨 sheet 引用值非数值，代入 0")
        except Exception as e:  # noqa: BLE001 — 单条失败不阻断整体求值
            logger.warning("跨 sheet 引用求值失败 %s: %s", ref_text, e)
            val = Decimal("0")
            errors.append(f"{ref_text}: {e}")
        expr = expr.replace(ref_text, str(val), 1)

    return expr, errors


async def evaluate_wp_formula_expression(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    expression: str,
    parsed_data: dict | None = None,
    parent_wp_code: str | None = None,
) -> tuple[Decimal, list[str]]:
    """求值自定义底稿公式表达式。

    支持：字面量、TB/SUM_TB、WP（含单元格地址 B5）、``Sheet!Cell`` 跨 sheet 引用
    （经 CrossSheetResolver 追溯，Req 14.2）、ROW/SUM_ROW/REPORT/NOTE/PREV（两参 / 三参）/AUX（严格按值代入）、
    ADJ（统一预载层，底稿口径）、四则运算与内置函数（委托 L1 execute）。
    取不到数（无上年试算表 / 上年同底稿字段无定义 / 无辅助核算 / 报表未生成 / 附注无该项）写进 errors，不静默 0；
    含不支持的函数时不求值，返回 (Decimal('0'), errors)。

    Args:
        parsed_data: 底稿 ``working_paper.parsed_data``（含 univer_snapshot），
            提供时启用 ``Sheet!Cell`` 跨 sheet 引用追溯求值。
        parent_wp_code: 父底稿码，供 CrossSheetResolver 构造 grammar_v1 3 参 WP。
    """
    from app.services.formula_preloader import preload
    from app.services.formula_ref_preload import substitute_value_refs

    errors: list[str] = []
    raw = (expression or "").strip()
    if not raw:
        return Decimal("0"), errors
    if raw.startswith("="):
        raw = raw[1:].strip()

    # 纯数字字面量
    try:
        return Decimal(raw.replace(",", "")), errors
    except (InvalidOperation, ValueError):
        pass

    # 不支持的函数：不求值（保存端点已 422；读取 / 渲染时求值预设也不能静默 0）
    unsupported = unsupported_formula_function_issues(raw)
    if unsupported:
        return Decimal("0"), [f"{issue['function']}：{issue['reason']}" for issue in unsupported]

    # 跨 sheet 引用（Sheet!Cell）先经 CrossSheetResolver 追溯解析为值代入（Req 14.2）
    raw, cross_errors = _resolve_cross_sheet_refs(
        raw,
        parsed_data,
        project_id=str(project_id) if project_id is not None else None,
        parent_wp_code=parent_wp_code,
    )
    errors.extend(cross_errors)

    # PREV / AUX / ROW / SUM_ROW / REPORT / NOTE 严格按值代入；须在 TB 代入之前（PREV(TB(...)) 里的 TB 是上年）
    substituted = await substitute_value_refs(raw, db=db, project_id=project_id, year=year, strict=True)
    errors.extend(substituted.missing)
    raw = substituted.expression

    expr = raw
    # 三参 WP（D2-3 嵌套寻址）先处理，避免被两参正则截断
    for match in _WP3_PATTERN.finditer(raw):
        wp_code, sheet_name, field = match.group(1), match.group(2), match.group(3)
        try:
            if _A1_FIELD.match(field) and _D23_SHEET_MARKER not in sheet_name:  # 三参 A1 按 sheet 精确取值（acnr T13）
                tr = await WPExecutor.read_sheet_cell(db, project_id, year, wp_code, sheet_name, field)
                val = tr.read.value if tr.read.state == "ok" else Decimal("0")  # 非 ok 时 0 只是占位
                if tr.read.state != "ok":
                    errors.append(f"{match.group(0)}：{tr.read.reason}")
            else:
                val = await WPExecutor.execute(
                    db, project_id, wp_code, sheet_name, field=field
                )
        except Exception as e:
            logger.warning("WP 三参求值失败 %s: %s", match.group(0), e)
            val = Decimal("0")
            errors.append(f"{match.group(0)}: {e}")
        expr = expr.replace(match.group(0), str(val), 1)

    for match in _WP_PATTERN.finditer(raw):
        # 跳过已被三参正则消费的片段（三参形态在 raw 中仍可被两参 finditer 命中前两参）
        if match.group(0) not in expr:
            continue
        wp_code, col = match.group(1), match.group(2)
        try:
            val = await WPExecutor.execute(db, project_id, wp_code, col)
        except Exception as e:
            logger.warning("WP 求值失败 %s: %s", match.group(0), e)
            val = Decimal("0")
            errors.append(f"{match.group(0)}: {e}")
        expr = expr.replace(match.group(0), str(val), 1)

    for match in _SUM_TB_PATTERN.finditer(raw):
        try:
            val = await _resolve_sum_tb(
                db, project_id, year, match.group(1), match.group(2)
            )
        except Exception as e:
            val = Decimal("0")
            errors.append(f"{match.group(0)}: {e}")
        expr = expr.replace(match.group(0), str(val), 1)

    for match in _TB_PATTERN.finditer(raw):
        try:
            val = await _resolve_tb(
                db, project_id, year, match.group(1), match.group(2)
            )
        except Exception as e:
            val = Decimal("0")
            errors.append(f"{match.group(0)}: {e}")
        expr = expr.replace(match.group(0), str(val), 1)

    # 代入后还剩取数函数 = 写法没认出来（参数没加单引号 / 少参数等）：报错，不让 L1 按空上下文求 0
    leftover = [name for name in _called_functions(expr) if name not in _KERNEL_FUNCTIONS]
    if leftover:
        errors.append(f"{'、'.join(leftover)} 写法无法识别（参数需用单引号括起，个数与函数说明一致）")
        return Decimal("0"), errors

    # ADJ 走统一预载层 → L1；底稿口径不排除底稿来源的调整分录（与报表口径排除 workpaper 相反）
    ctx = FormulaContext(tb_data={}, row_cache={})
    if "ADJ" in _called_functions(expr):
        gaps: list[str] = []
        ctx = await preload(db, project_id, year, [expr], adj_exclude_origins=frozenset(), gaps=gaps)
        errors.extend(gaps)
    result = execute(expr, ctx)
    errors.extend(result.errors)
    return result.value, errors
