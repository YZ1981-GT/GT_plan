"""报表规则映射 → 科目编号解析（单一真源：report_config.formula）。

审定表 / 四表取数应参照报表配置中的「报表科目 ↔ 具体科目编号」规则映射，
而非在各渲染策略里硬编码科目前缀，以适配项目级自定义映射（企业编码/口径差异）。

用法::

    codes = await resolve_report_line_account_codes(
        db, project_id, "BS-002", fallback=["1001", "1002", "1012"]
    )

解析优先级：项目级配置 (``project:{id}``) → 标准级配置（各标准该行公式一致，取其一）；
解析 formula 中的 ``TB('code',...)`` / ``SUM_TB('start~end',...)`` 科目；
无匹配时返回 ``fallback``（保证零回归）。
"""
from __future__ import annotations

import re
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# 与 report_engine._TB_PATTERN / _SUM_TB_PATTERN 同源语义（此处独立小正则，避免循环依赖）
_TB_RE = re.compile(r"TB\('([^']+)'")
_SUM_TB_RE = re.compile(r"SUM_TB\('([^']+)'")


def extract_codes_from_formula(formula: str | None) -> list[str]:
    """从报表公式中提取引用的科目编号（TB 单码 + SUM_TB 区间 ``start~end``）。"""
    if not formula:
        return []
    codes: set[str] = set()
    for m in _TB_RE.finditer(formula):
        codes.add(m.group(1).strip())
    for m in _SUM_TB_RE.finditer(formula):
        parts = m.group(1).split("~")
        if len(parts) == 2:
            codes.add(f"{parts[0].strip()}~{parts[1].strip()}")
    return sorted(codes)


async def resolve_report_line_account_codes(
    db: AsyncSession,
    project_id: UUID | str,
    row_code: str,
    *,
    fallback: list[str],
) -> list[str]:
    """解析某报表行(row_code)在 report_config 规则映射中的源科目编号。

    Args:
        db: 异步会话。
        project_id: 项目 ID（用于项目级 ``project:{id}`` 覆盖优先）。
        row_code: 报表行次编码（如货币资金 ``BS-002``）。
        fallback: 无规则映射时的兜底科目编号（保证零回归）。

    Returns:
        科目编号列表（单码或 ``start~end`` 区间）；解析失败或无配置返回 ``fallback`` 副本。
    """
    try:
        row = (
            await db.execute(
                sa.text(
                    "SELECT formula FROM report_config "
                    "WHERE row_code = :rc AND applicable_standard = :std "
                    "AND is_deleted = false LIMIT 1"
                ),
                {"rc": row_code, "std": f"project:{project_id}"},
            )
        ).fetchone()
        if row is None or not row.formula:
            row = (
                await db.execute(
                    sa.text(
                        "SELECT formula FROM report_config "
                        "WHERE row_code = :rc "
                        "AND applicable_standard NOT LIKE 'project:%' "
                        "AND is_deleted = false LIMIT 1"
                    ),
                    {"rc": row_code},
                )
            ).fetchone()
        codes = extract_codes_from_formula(row.formula if row else None)
        return codes or list(fallback)
    except Exception:  # noqa: BLE001 — 规则映射解析失败一律回退，绝不阻断渲染
        return list(fallback)


def build_trial_balance_code_filter(
    codes: list[str], param_prefix: str = "acc"
) -> tuple[str, dict[str, str]]:
    """按科目编号列表构建 trial_balance/tb_balance 的 SQL 过滤子句 + 参数。

    - 单码 ``1001`` → ``standard_account_code LIKE :accN``（``1001%`` 前缀匹配子科目）
    - 区间 ``1401~1499`` → ``standard_account_code BETWEEN :accN_lo AND :accN_hi``（含右界近似 ``~9`` 尾）

    Returns:
        ``(where_clause, params)``；``codes`` 为空时返回 ``("1=0", {})``（不匹配任何行）。
    """
    if not codes:
        return "1=0", {}
    clauses: list[str] = []
    params: dict[str, str] = {}
    for i, code in enumerate(codes):
        key = f"{param_prefix}{i}"
        if "~" in code:
            lo, hi = (p.strip() for p in code.split("~", 1))
            clauses.append(
                f"(standard_account_code >= :{key}_lo AND standard_account_code <= :{key}_hi)"
            )
            params[f"{key}_lo"] = lo
            params[f"{key}_hi"] = hi + "\uffff"  # 覆盖区间上界下所有子科目
        else:
            clauses.append(f"standard_account_code LIKE :{key}")
            params[key] = f"{code}%"
    return "(" + " OR ".join(clauses) + ")", params
