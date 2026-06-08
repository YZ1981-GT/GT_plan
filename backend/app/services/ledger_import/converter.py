"""数据转换层 — 原始行 → 标准化四表记录。

从 smart_import_engine.py 的 convert_balance_rows / convert_ledger_rows 提取，
适配 v2 模块化架构。

职责：
- convert_balance_rows: 余额表原始行 → (tb_balance_rows, tb_aux_balance_rows)
- convert_ledger_rows: 序时账原始行 → (tb_ledger_rows, aux_stats)
- 方向推断（借贷分列 vs 净额+方向）
- 辅助维度自动拆分（单列混合 → 多条辅助记录）
- 科目级次推断

设计原则：
- 纯函数，不依赖 DB
- 输入是 dict 列表（standard_field 为 key），输出也是 dict 列表
- 辅助维度解析委托给 aux_dimension.parse_aux_dimension
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from .aux_dimension import parse_aux_dimension
from .direction_resolver import resolve_account_direction
from .sign_convention_types import CURRENT_SIGN_CONVENTION

# 显式方向列 token（借/贷/D/C），与 direction_derivation 口径一致
_DEBIT_DIR_TOKENS = frozenset(["借", "借方", "D", "d", "debit", "Debit", "DEBIT"])
_CREDIT_DIR_TOKENS = frozenset(["贷", "贷方", "C", "c", "credit", "Credit", "CREDIT"])

__all__ = [
    "convert_balance_rows",
    "convert_balance_rows_v2",
    "convert_ledger_rows",
    "convert_ledger_rows_v2",
    "safe_decimal",
    "parse_date_val",
    "parse_period_str",
    "infer_level",
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def safe_decimal(val) -> Optional[Decimal]:
    """安全转 Decimal，失败返回 None。"""
    if val is None:
        return None
    try:
        s = str(val).strip().replace(",", "")
        if not s or s == "None":
            return None
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def parse_date_val(val) -> Optional[date]:
    """解析日期值，支持多种格式 + datetime 对象。"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s or s == "None":
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d",
                "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Excel 序列号
    try:
        serial = float(s)
        if 1 <= serial <= 100000:
            from datetime import timedelta
            return (datetime(1899, 12, 30) + timedelta(days=int(serial))).date()
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def parse_period_str(val) -> Optional[int]:
    """解析期间字符串为月份。如 '2025年1期' → 1。"""
    if val is None:
        return None
    s = str(val).strip()
    m = re.search(r"(\d+)\s*期", s)
    if m:
        return int(m.group(1))
    try:
        v = int(s)
        if 1 <= v <= 12:
            return v
    except (ValueError, TypeError):
        pass
    return None


def infer_level(code: str) -> int:
    """根据科目编码长度推断级次。"""
    code = code.replace(".", "").replace("-", "")
    if len(code) <= 4:
        return 1
    elif len(code) <= 6:
        return 2
    elif len(code) <= 8:
        return 3
    elif len(code) <= 10:
        return 4
    return 5


def _resolve_direction(direction_raw, amount: Optional[Decimal]) -> Optional[Decimal]:
    """根据方向字段调整金额符号。"""
    if amount is None or direction_raw is None:
        return amount
    d = str(direction_raw).strip()
    if d in ("贷", "贷方", "C", "c", "credit", "Credit"):
        return -abs(amount)
    if d in ("借", "借方", "D", "d", "debit", "Debit"):
        return abs(amount)
    return amount


def _is_known_direction_token(direction_raw) -> bool:
    """判断方向列的值是否为可识别的借/贷 token。"""
    if direction_raw is None:
        return False
    s = str(direction_raw).strip()
    return s in _DEBIT_DIR_TOKENS or s in _CREDIT_DIR_TOKENS


def _resolve_entry_direction(
    code: str,
    name: Optional[str],
    direction_raw,
    debit_amount: Optional[Decimal],
    credit_amount: Optional[Decimal],
) -> tuple[Optional[str], Optional[str]]:
    """判定一条序时账分录行的借贷方向（需求 4.2、5.2、5.3）。

    分录行的借贷本身明确：金额已分列在 debit_amount / credit_amount，
    因此方向直接由"哪一边非零"决定，**不改动金额口径**（不归一化分录金额）。

    判定优先级：
    1. 原始文件含显式方向列（借/贷/D/C）→ 直接采用（需求 5.3）。
    2. 借贷分列单边非零 → 由该非零侧决定（source=split_columns，需求 5.4）。
    3. 两侧皆非零（如合成的"本月合计"小计行）或皆为空 → 退化为按科目类别推断
       （调 direction_resolver，与余额行同一套规则），source 取类别推断来源。

    Returns:
        (entry_direction, entry_direction_source)
        - entry_direction ∈ {"debit", "credit"} 或 None（无法判定）
        - entry_direction_source ∈ DirectionSource 枚举值 或 None
    """
    # 1. 显式方向列优先
    if _is_known_direction_token(direction_raw):
        s = str(direction_raw).strip()
        if s in _DEBIT_DIR_TOKENS:
            return "debit", "explicit_direction"
        return "credit", "explicit_direction"

    # 2. 借贷分列：由非零侧决定
    debit_active = debit_amount is not None and debit_amount != 0
    credit_active = credit_amount is not None and credit_amount != 0
    if debit_active and not credit_active:
        return "debit", "split_columns"
    if credit_active and not debit_active:
        return "credit", "split_columns"

    # 3. 两侧皆非零 / 皆为空 → 按类别推断（与余额行同一套规则）
    direction, source = resolve_account_direction(code, name or "")
    return direction, source


def _apply_sign_convention(
    target: dict,
    code: str,
    name: Optional[str],
    *,
    opening_source_mode: Optional[str] = None,
    closing_source_mode: Optional[str] = None,
) -> None:
    """对单条余额行应用 v2 类别自然正数符号约定（需求 1、4、5）。

    传入的 opening_balance / closing_balance 为 v1 净额（借方为正、贷方为负）。
    本函数：
    - 调 direction_resolver 取科目正常方向（debit/credit）+ 来源；
    - 将净额归一为"类别自然正数"：正常方向为借方时存净额本身，为贷方时取反，
      使负债/权益/收入科目的贷方余额存为正数；
    - 当实际方向与类别正常方向相反（如负债出现借方余额）时，归一后值为负数，
      **保留该带符号值不强制翻正**（需求 1.5）；
    - 写 opening_direction / closing_direction（= 类别正常方向）及来源；
    - 写 sign_convention_version = v2；
    - 方向与类别冲突（归一后为负）时在 sign_anomaly_flags 记录异常（需求 4.5）。

    就地修改 target dict。opening_source_mode / closing_source_mode 用于标注方向来源
    （explicit_direction / split_columns），缺省时退化为类别推断来源。
    """
    direction, category_source = resolve_account_direction(code, name or "")
    opposite = "credit" if direction == "debit" else "debit"

    conflicts: list[dict] = []
    for period, mode in (
        ("opening", opening_source_mode),
        ("closing", closing_source_mode),
    ):
        bal_key = f"{period}_balance"
        net = target.get(bal_key)
        # 归一为类别自然正数：借方科目存净额，贷方科目取反
        if net is not None:
            stored = net if direction == "debit" else -net
            target[bal_key] = stored
            if stored < 0:
                conflicts.append({
                    "period": period,
                    "actual_direction": opposite,
                    "stored_amount": float(stored),
                })
        target[f"{period}_direction"] = direction
        target[f"{period}_direction_source"] = mode or category_source

    target["sign_convention_version"] = CURRENT_SIGN_CONVENTION
    if conflicts:
        target["sign_anomaly_flags"] = {
            "normal_direction": direction,
            "conflicts": conflicts,
        }


# ---------------------------------------------------------------------------
# 余额表转换
# ---------------------------------------------------------------------------


def _aggregate_aux_to_summary(
    aux_base_rows: list[dict],
    account_code: str,
    company_code: str,
) -> dict:
    """将多条带辅助维度的余额行聚合成一条虚拟主表汇总行。

    用于 Excel 里只有明细行没有汇总行的场景（如 1122 应收账款 只导出 2 家客户明细）。
    所有金额字段求和，raw_extra 追加 _aggregated_from_aux 标记以便后续溯源。
    """
    def _sum(field: str) -> Optional[Decimal]:
        vals = [r.get(field) for r in aux_base_rows if r.get(field) is not None]
        if not vals:
            return None
        total = Decimal(0)
        for v in vals:
            total += v
        return total

    first = aux_base_rows[0]
    raw_extra_base = dict(first.get("raw_extra") or {})
    raw_extra_base["_aggregated_from_aux"] = True
    raw_extra_base["_aux_row_count"] = len(aux_base_rows)

    return {
        "account_code": account_code,
        "account_name": first.get("account_name"),
        "company_code": company_code,
        "opening_balance": _sum("opening_balance"),
        "opening_debit": _sum("opening_debit"),
        "opening_credit": _sum("opening_credit"),
        "debit_amount": _sum("debit_amount"),
        "credit_amount": _sum("credit_amount"),
        "closing_balance": _sum("closing_balance"),
        "closing_debit": _sum("closing_debit"),
        "closing_credit": _sum("closing_credit"),
        "currency_code": first.get("currency_code") or "CNY",
        "raw_extra": raw_extra_base,
    }


def convert_balance_rows(
    rows: list[dict],
    *,
    default_company: str = "default",
) -> tuple[list[dict], list[dict]]:
    """余额表原始行 → (tb_balance_rows, tb_aux_balance_rows)。

    支持两种期初/期末模式：
    - 分列模式（opening_debit + opening_credit）→ 算 opening_balance
    - 净额+方向模式（opening_balance + direction）→ 按方向调符号

    含辅助维度的行自动拆分到 aux_balance_rows。

    主表去重规则（按 (company_code, account_code) 分组，每组产出 1 条主表行）：
    - 有汇总行（无 aux 的原始行）→ 主表用汇总行，丢弃带 aux 行对主表的重复写入
    - 仅有明细行（N 条带 aux）→ 主表聚合生成虚拟汇总行，raw_extra._aggregated_from_aux=true
    避免同一 account_code 在 tb_balance 里重复 N+1 次导致下游 SUM 翻倍。
    """
    aux_balance_rows: list[dict] = []
    # 分组索引：(company_code, account_code) → {summary: dict|None, aux_base_rows: list[dict]}
    # aux_base_rows 记录"带 aux 原始行的 base_row"（不含 aux_type/aux_code 等维度字段），
    # 仅在该组无 summary 时用于聚合生成虚拟汇总行。
    groups: dict[tuple[str, str], dict] = {}

    for row in rows:
        account_code = str(row.get("account_code", "")).strip()
        if not account_code:
            continue

        account_name = str(row.get("account_name", "")).strip() or None
        company_code = str(row.get("company_code", "")).strip() or default_company

        # ── 期初 ──
        od = safe_decimal(row.get("opening_debit"))
        oc = safe_decimal(row.get("opening_credit"))
        opening_bal = safe_decimal(row.get("opening_balance"))
        opening_dir = row.get("opening_direction") or row.get("direction")

        # 年初余额作为备选
        if od is None and oc is None and opening_bal is None:
            od = safe_decimal(row.get("year_opening_debit"))
            oc = safe_decimal(row.get("year_opening_credit"))

        # 方向来源（需求 5.3/5.4）：借贷分列优先标 split_columns，
        # 显式方向列标 explicit_direction，否则留空交由类别推断兜底。
        if od is not None or oc is not None:
            opening_balance = (od or Decimal(0)) - (oc or Decimal(0))
            opening_source_mode = "split_columns"
        elif opening_bal is not None:
            opening_balance = _resolve_direction(opening_dir, opening_bal)
            opening_source_mode = (
                "explicit_direction" if _is_known_direction_token(opening_dir) else None
            )
        else:
            opening_balance = None
            opening_source_mode = None

        # ── 期末 ──
        cd = safe_decimal(row.get("closing_debit"))
        cc = safe_decimal(row.get("closing_credit"))
        closing_bal = safe_decimal(row.get("closing_balance"))
        closing_dir = row.get("closing_direction") or row.get("direction")

        if cd is not None or cc is not None:
            closing_balance = (cd or Decimal(0)) - (cc or Decimal(0))
            closing_source_mode = "split_columns"
        elif closing_bal is not None:
            closing_balance = _resolve_direction(closing_dir, closing_bal)
            closing_source_mode = (
                "explicit_direction" if _is_known_direction_token(closing_dir) else None
            )
        else:
            closing_balance = None
            closing_source_mode = None

        debit_amount = safe_decimal(row.get("debit_amount"))
        credit_amount = safe_decimal(row.get("credit_amount"))

        # ── 辅助维度 ──
        aux_dim_str = str(row.get("aux_dimensions", "")).strip()
        if not aux_dim_str:
            # 多列格式
            aux_type_val = str(row.get("aux_type", "")).strip()
            aux_code_val = str(row.get("aux_code", "")).strip()
            if aux_type_val and aux_code_val:
                aux_name_val = str(row.get("aux_name", "")).strip() or aux_code_val
                aux_dim_str = f"{aux_type_val}:{aux_code_val} {aux_name_val}"

        base_row = {
            "account_code": account_code,
            "account_name": account_name,
            "company_code": company_code,
            "opening_balance": opening_balance,
            "opening_debit": od,
            "opening_credit": oc,
            "debit_amount": debit_amount,
            "credit_amount": credit_amount,
            "closing_balance": closing_balance,
            "closing_debit": cd,
            "closing_credit": cc,
            "currency_code": row.get("currency_code") or "CNY",
            "raw_extra": row.get("raw_extra"),
            # 方向来源模式（私有，仅供符号归一化后处理用，非 ORM 列）
            "_opening_source_mode": opening_source_mode,
            "_closing_source_mode": closing_source_mode,
        }

        if aux_dim_str:
            dims = parse_aux_dimension(aux_dim_str)
            valid_dims = [d for d in dims if d.get("aux_type")]
            if valid_dims:
                for dim in valid_dims:
                    aux_balance_rows.append({
                        **base_row,
                        "aux_type": dim["aux_type"],
                        "aux_code": dim.get("aux_code") or None,
                        "aux_name": dim.get("aux_name") or None,
                        "aux_dimensions_raw": aux_dim_str,  # 溯源原始维度字符串
                    })
                # 记录该组的带 aux base row，用于在无汇总行时聚合成虚拟汇总
                key = (company_code, account_code)
                g = groups.setdefault(key, {"summary": None, "aux_base_rows": []})
                g["aux_base_rows"].append(base_row)
                continue

        # 无辅助维度 → 作为该组的汇总行（若重复出现则用第一条）
        key = (company_code, account_code)
        g = groups.setdefault(key, {"summary": None, "aux_base_rows": []})
        if g["summary"] is None:
            g["summary"] = {
                **base_row,
                "level": infer_level(account_code),
            }

    # ── 按组装配主表 ──
    balance_rows: list[dict] = []
    for (company_code, account_code), g in groups.items():
        if g["summary"] is not None:
            # 场景 A：有汇总行 → 用汇总行，丢弃 aux_base_rows 对主表的重复写入
            balance_rows.append(g["summary"])
        elif g["aux_base_rows"]:
            # 场景 B：只有明细 → 聚合生成虚拟汇总行
            aggregated = _aggregate_aux_to_summary(
                g["aux_base_rows"], account_code, company_code,
            )
            aggregated["level"] = infer_level(account_code)
            balance_rows.append(aggregated)

    # ── 符号归一化后处理（v2 类别自然正数 + 方向字段 + 异常标记）──
    # 集中调用 direction_resolver，避免散落（需求 1、4、5）。
    for target in balance_rows:
        _finalize_balance_sign(target)
    for target in aux_balance_rows:
        _finalize_balance_sign(target)

    return balance_rows, aux_balance_rows


def _finalize_balance_sign(target: dict) -> None:
    """对一条主表/辅助余额行应用 v2 符号约定并清理私有字段。"""
    opening_mode = target.pop("_opening_source_mode", None)
    closing_mode = target.pop("_closing_source_mode", None)
    _apply_sign_convention(
        target,
        target.get("account_code", ""),
        target.get("account_name"),
        opening_source_mode=opening_mode,
        closing_source_mode=closing_mode,
    )


# ---------------------------------------------------------------------------
# 序时账转换
# ---------------------------------------------------------------------------


def convert_ledger_rows(
    rows: list[dict],
    *,
    default_company: str = "default",
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """序时账原始行 → (tb_ledger_rows, tb_aux_ledger_rows, aux_stats)。

    对齐旧引擎 `write_four_tables` 的辅助明细账拆分逻辑：
    - 主表 tb_ledger：所有行都写（每行一条）
    - 辅助表 tb_aux_ledger：含辅助维度的行按维度数拆分成 N 条

    符号约定（v2，需求 4.2、5.2）：
    - 每条分录行标 `entry_direction`（debit/credit）+ `entry_direction_source`；
    - 方向由借贷分列哪边非零决定（显式方向列优先，两侧皆非零/皆空时按科目类别推断）；
    - **金额口径不变**：分录借贷本身明确，不归一化分录金额（与余额行不同）。

    Returns:
        (ledger_rows, aux_ledger_rows, aux_stats)
        - ledger_rows: 标准化序时账行（含 _aux_dim_str 内部字段）
        - aux_ledger_rows: 辅助明细账行（含 aux_type/aux_code/aux_name/aux_dimensions_raw）
        - aux_stats: {"客户": 12345, "部门": 678, ...} 维度统计
    """
    ledger_rows: list[dict] = []
    aux_ledger_rows: list[dict] = []
    aux_stats: dict[str, int] = {}

    for row in rows:
        account_code = str(row.get("account_code", "")).strip()
        if not account_code:
            continue

        voucher_date = parse_date_val(row.get("voucher_date"))
        voucher_no = str(row.get("voucher_no", "")).strip()
        if not voucher_date or not voucher_no:
            continue

        debit_amount = safe_decimal(row.get("debit_amount"))
        credit_amount = safe_decimal(row.get("credit_amount"))

        # 分录行方向标记（需求 4.2、5.2）：方向由借贷分列哪边非零决定，
        # 显式方向列优先，两侧皆非零/皆空时按科目类别推断。
        # **金额口径不变**：分录借贷本身明确，不做归一化（与余额行不同）。
        entry_direction, entry_direction_source = _resolve_entry_direction(
            account_code,
            str(row.get("account_name", "")).strip() or None,
            row.get("direction") or row.get("entry_direction"),
            debit_amount,
            credit_amount,
        )

        # 辅助维度
        aux_dim_str = str(row.get("aux_dimensions", "")).strip()
        if not aux_dim_str:
            aux_type_val = str(row.get("aux_type", "")).strip()
            aux_code_val = str(row.get("aux_code", "")).strip()
            if aux_type_val and aux_code_val:
                aux_name_val = str(row.get("aux_name", "")).strip() or aux_code_val
                aux_dim_str = f"{aux_type_val}:{aux_code_val} {aux_name_val}"

        base_fields = {
            "account_code": account_code,
            "account_name": str(row.get("account_name", "")).strip() or None,
            "voucher_date": voucher_date,
            "voucher_no": voucher_no,
            "voucher_type": str(row.get("voucher_type", "")).strip() or None,
            "accounting_period": parse_period_str(row.get("accounting_period"))
                or (voucher_date.month if voucher_date else None),
            "debit_amount": debit_amount,
            "credit_amount": credit_amount,
            "summary": str(row.get("summary", "")).strip() or None,
            "preparer": str(row.get("preparer", "")).strip() or None,
            "company_code": str(row.get("company_code", "")).strip() or default_company,
            "currency_code": row.get("currency_code") or "CNY",
            # 方向标记（v2 符号约定，复用 V064 entry_direction 列）
            "entry_direction": entry_direction,
            "entry_direction_source": entry_direction_source,
        }

        # 辅助明细账拆分（对齐旧 write_four_tables:2126-2139）
        if aux_dim_str:
            dims = parse_aux_dimension(aux_dim_str)
            for dim in dims:
                if not dim.get("aux_type"):
                    continue
                aux_stats[dim["aux_type"]] = aux_stats.get(dim["aux_type"], 0) + 1
                aux_ledger_rows.append({
                    **base_fields,
                    "aux_type": dim["aux_type"],
                    "aux_code": dim.get("aux_code") or None,
                    "aux_name": dim.get("aux_name") or None,
                    "aux_dimensions_raw": aux_dim_str,
                    "raw_extra": row.get("raw_extra"),
                })

        ledger_rows.append({
            **base_fields,
            "raw_extra": row.get("raw_extra"),
            "_aux_dim_str": aux_dim_str,
        })

    return ledger_rows, aux_ledger_rows, aux_stats


# ---------------------------------------------------------------------------
# 结构化结果 v2 接口
# ---------------------------------------------------------------------------


def convert_balance_rows_v2(
    rows: list[dict],
    *,
    default_company: str = "default",
) -> "BalanceConversionResult":
    """余额表转换 — 返回结构化 BalanceConversionResult。

    保持纯函数特性，不访问 DB。新增：
    - warnings: 转换警告（如借贷两方同时非零）
    - sign_anomalies: 暂为空列表（待 Task 4 方向推导规则实现后填充）
    - stats: 转换统计摘要

    与 convert_balance_rows 行为一致，仅返回类型不同。
    """
    from .conversion_result import BalanceConversionResult
    from .sign_convention_types import CURRENT_SIGN_CONVENTION

    balance_rows, aux_balance_rows = convert_balance_rows(
        rows, default_company=default_company
    )

    stats = {
        "total_input_rows": len(rows),
        "balance_rows": len(balance_rows),
        "aux_balance_rows": len(aux_balance_rows),
        "sign_convention_version": CURRENT_SIGN_CONVENTION,
        "rows_with_direction": 0,
        "anomaly_count": 0,
    }

    return BalanceConversionResult(
        rows=balance_rows,
        aux_rows=aux_balance_rows,
        warnings=[],
        sign_anomalies=[],
        stats=stats,
    )


def convert_ledger_rows_v2(
    rows: list[dict],
    *,
    default_company: str = "default",
) -> "LedgerConversionResult":
    """序时账转换 — 返回结构化 LedgerConversionResult。

    保持纯函数特性，不访问 DB。新增：
    - warnings: 转换警告
    - sign_anomalies: 暂为空列表
    - stats: 转换统计摘要

    与 convert_ledger_rows 行为一致，仅返回类型不同。
    """
    from .conversion_result import LedgerConversionResult
    from .sign_convention_types import CURRENT_SIGN_CONVENTION

    ledger_rows, aux_ledger_rows, aux_stats = convert_ledger_rows(
        rows, default_company=default_company
    )

    rows_with_direction = sum(
        1 for r in ledger_rows if r.get("entry_direction") is not None
    )

    stats = {
        "total_input_rows": len(rows),
        "ledger_rows": len(ledger_rows),
        "aux_ledger_rows": len(aux_ledger_rows),
        "sign_convention_version": CURRENT_SIGN_CONVENTION,
        "rows_with_direction": rows_with_direction,
        "anomaly_count": 0,
    }

    return LedgerConversionResult(
        rows=ledger_rows,
        aux_rows=aux_ledger_rows,
        aux_stats=aux_stats,
        warnings=[],
        sign_anomalies=[],
        stats=stats,
    )
