"""调整分录影响预览服务（L-2）

模拟调整分录对报表行/底稿的影响，**不写 DB**：仅读取 report_line_mapping、
account_chart、wp_account_mapping.json 进行计算。

输入：line_items + year
输出：affected_report_rows（按 report_type/row_code 聚合 delta）+ affected_workpapers（wp_code 列表）

性能要求：< 500ms（前端 debounce 500ms 触发）

核心算法：
  1) 对每个 line_item，从 AccountChart 读 direction（debit/credit）
  2) 计算"科目变动方向"signed delta：
     - debit 科目（资产/费用）：delta = debit - credit
     - credit 科目（负债/权益/收入）：delta = credit - debit
     - 该口径与 trial_balance.audited_amount 的累加方向一致
  3) 通过 ReportLineMapping 查每个 std code 落在哪些 (report_type, row_code) 上
     → 同 row 多 line 累加 delta
  4) 通过 wp_account_mapping.json 查每个 std code 关联哪些 wp_code → 去重列表
"""

from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import (
    AccountChart,
    AccountDirection,
    ReportLineMapping,
    TrialBalance,
)

logger = logging.getLogger(__name__)


# 公开 field 名（与 trial_balance / report 视图保持一致的中文字段名）
FIELD_AUDITED_CURRENT = "当期金额"


def _signed_delta(
    direction: AccountDirection | None, debit: Decimal, credit: Decimal
) -> Decimal:
    """根据科目方向计算 signed delta。

    debit 科目（资产/费用）：debit - credit > 0 表示金额增加。
    credit 科目（负债/权益/收入）：credit - debit > 0 表示金额增加。
    direction 缺失时按 debit 处理（避免静默丢数）。
    """
    if direction == AccountDirection.credit:
        return credit - debit
    return debit - credit


async def _load_account_directions(
    db: AsyncSession, project_id: UUID, account_codes: list[str]
) -> dict[str, AccountDirection]:
    """批量查 account_chart.direction，返回 {account_code: direction}。"""
    if not account_codes:
        return {}
    rows = (
        await db.execute(
            sa.select(AccountChart.account_code, AccountChart.direction).where(
                AccountChart.project_id == project_id,
                AccountChart.account_code.in_(account_codes),
                AccountChart.is_deleted.is_(False),
            )
        )
    ).all()
    out: dict[str, AccountDirection] = {}
    for code, direction in rows:
        # 同一 code 可能同时存在 standard / client 两条，任取其一即可
        out.setdefault(code, direction)
    return out


async def _load_report_line_mappings(
    db: AsyncSession, project_id: UUID, account_codes: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """批量查 report_line_mapping，返回 {account_code: [{report_type, row_code, row_name}, ...]}。

    仅返回 is_confirmed=True 的映射。
    """
    if not account_codes:
        return {}
    rows = (
        await db.execute(
            sa.select(
                ReportLineMapping.standard_account_code,
                ReportLineMapping.report_type,
                ReportLineMapping.report_line_code,
                ReportLineMapping.report_line_name,
                ReportLineMapping.mapping_sign,
            ).where(
                ReportLineMapping.project_id == project_id,
                ReportLineMapping.standard_account_code.in_(account_codes),
                ReportLineMapping.is_confirmed.is_(True),
                ReportLineMapping.is_deleted.is_(False),
            )
        )
    ).all()
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for code, rt, rcode, rname, mapping_sign in rows:
        out[code].append(
            {
                "report_type": rt.value if hasattr(rt, "value") else str(rt),
                "row_code": rcode,
                "row_name": rname,
                "mapping_sign": mapping_sign or "add",
            }
        )
    return out


def _find_workpapers_for_accounts(account_codes: list[str]) -> list[str]:
    """从 wp_account_mapping.json 查找受影响底稿 wp_code 列表（去重 + 排序）。"""
    if not account_codes:
        return []
    # 复用 wp_mapping_service 的缓存加载逻辑
    try:
        from app.services.wp_mapping_service import WpMappingService

        svc = WpMappingService(db=None)
        seen: set[str] = set()
        for code in account_codes:
            for m in svc.find_by_account_code(code):
                wp_code = m.get("wp_code")
                if wp_code:
                    seen.add(wp_code)
        return sorted(seen)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[preview_impact] load wp_account_mapping failed: %s", exc)
        return []


async def _load_account_names(
    db: AsyncSession, project_id: UUID, account_codes: list[str],
) -> dict[str, str]:
    rows = (await db.execute(sa.select(
        AccountChart.account_code, AccountChart.account_name,
    ).where(
        AccountChart.project_id == project_id,
        AccountChart.account_code.in_(account_codes),
        AccountChart.is_deleted == sa.false(),
    ))).all()
    out: dict[str, str] = {}
    for code, name in rows:
        if code and name:
            out.setdefault(str(code), str(name))
    return out


async def _load_note_impacts(
    db: AsyncSession, project_id: UUID, account_names: set[str],
) -> list[dict[str, Any]]:
    if not account_names:
        return []
    from app.models.account_note_mapping_models import AccountNoteMapping
    rows = (await db.execute(sa.select(AccountNoteMapping).where(
        AccountNoteMapping.project_id == project_id,
        AccountNoteMapping.account_name.in_(sorted(account_names)),
    ).order_by(AccountNoteMapping.section_id, AccountNoteMapping.row_name))).scalars().all()
    return [{
        "section_id": row.section_id,
        "row_name": row.row_name,
        "account_name": row.account_name,
        "mapping_type": row.mapping_type,
    } for row in rows]


async def _load_tb_impacts(
    db: AsyncSession,
    project_id: UUID,
    year: int | None,
    deltas: dict[str, Decimal],
    adjustment_type: str,
) -> list[dict[str, Any]]:
    if year is None or not deltas:
        return []
    rows = (await db.execute(sa.select(TrialBalance).where(
        TrialBalance.project_id == project_id,
        TrialBalance.year == year,
        TrialBalance.standard_account_code.in_(sorted(deltas)),
        TrialBalance.is_deleted == sa.false(),
    ).order_by(TrialBalance.company_code, TrialBalance.standard_account_code))).scalars().all()
    result: list[dict[str, Any]] = []
    for row in rows:
        delta = deltas.get(row.standard_account_code, Decimal("0"))
        aje = Decimal(str(row.aje_adjustment or 0))
        rje = Decimal(str(row.rje_adjustment or 0))
        audited = Decimal(str(row.audited_amount or 0))
        result.append({
            "company_code": row.company_code,
            "account_code": row.standard_account_code,
            "account_name": row.account_name,
            "adjustment_type": adjustment_type,
            "current_adjustment": aje if adjustment_type == "aje" else rje,
            "projected_adjustment": (aje if adjustment_type == "aje" else rje) + delta,
            "current_audited": audited,
            "projected_audited": audited + delta,
            "delta": delta,
        })
    return result


async def preview_impact(
    db: AsyncSession,
    project_id: UUID,
    line_items: list[dict[str, Any]],
    year: int | None = None,
    adjustment_type: str = "aje",
) -> dict[str, Any]:
    """模拟调整分录影响（不写 DB）。

    Parameters
    ----------
    db : AsyncSession
        只读会话（仅 SELECT，不会触发 commit/flush）
    project_id : UUID
    line_items : list[dict]
        每项包含 ``account_code``、``debit``（默认 0）、``credit``（默认 0）。
        兼容键名：``standard_account_code`` 同 ``account_code``。
    year : int | None
        当前预留字段，便于后续按 year 过滤映射版本（默认 None 表示项目当前生效版本）。

    Returns
    -------
    dict
        ``{
            "affected_report_rows": [
                {"report_type": "balance_sheet", "row_code": "BS-005",
                 "row_name": "应收账款", "field": "当期金额", "delta": Decimal},
                ...
            ],
            "affected_workpapers": ["D2", "K8", ...],
            "unmapped_accounts": ["9999", ...],
        }``

    Notes
    -----
    严格只读：函数全程只发出 SELECT，且 line_items 不会触发任何 INSERT/UPDATE。
    """
    # ── Step 1: 提取 + 归一化 account_codes ──
    accounts: list[tuple[str, Decimal, Decimal]] = []
    for li in line_items or []:
        code = (
            li.get("account_code")
            or li.get("standard_account_code")
            or ""
        )
        if not code:
            continue
        debit = Decimal(str(li.get("debit") or li.get("debit_amount") or 0))
        credit = Decimal(str(li.get("credit") or li.get("credit_amount") or 0))
        accounts.append((str(code).strip(), debit, credit))

    if not accounts:
        return {
            "affected_tb_accounts": [],
            "affected_report_rows": [],
            "affected_workpapers": [],
            "affected_notes": [],
            "judgment_items": [],
            "unmapped_accounts": [],
            "direction_unknown_accounts": [],
        }

    unique_codes = sorted({c for c, _, _ in accounts})

    # ── Step 2: 并行加载方向 + 报表行映射 ──
    direction_map = await _load_account_directions(db, project_id, unique_codes)
    rlm_map = await _load_report_line_mappings(db, project_id, unique_codes)

    # ── Step 3: 计算科目与每个 (report_type, row_code) 累计 delta ──
    row_acc: dict[tuple[str, str], dict[str, Any]] = {}
    account_deltas: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    unmapped: list[str] = []
    direction_unknown: list[str] = []

    for code, debit, credit in accounts:
        direction = direction_map.get(code)
        if direction is None:
            direction_unknown.append(code)
            if code not in rlm_map:
                unmapped.append(code)
            continue
        delta = _signed_delta(direction, debit, credit)
        account_deltas[code] += delta
        if code not in rlm_map:
            unmapped.append(code)
        if delta == 0:
            continue

        for row in rlm_map.get(code, []):
            key = (row["report_type"], row["row_code"])
            slot = row_acc.setdefault(
                key,
                {"row_name": row["row_name"], "delta": Decimal("0")},
            )
            mapping_sign = Decimal("-1") if row.get("mapping_sign") == "subtract" else Decimal("1")
            slot["delta"] += delta * mapping_sign

    affected_report_rows: list[dict[str, Any]] = []
    for (report_type, row_code), slot in sorted(row_acc.items()):
        if slot["delta"] == 0:
            continue
        affected_report_rows.append(
            {
                "report_type": report_type,
                "row_code": row_code,
                "row_name": slot["row_name"],
                "field": FIELD_AUDITED_CURRENT,
                "delta": slot["delta"],
            }
        )

    affected_workpapers = _find_workpapers_for_accounts(unique_codes)
    names = await _load_account_names(db, project_id, unique_codes)
    affected_notes = await _load_note_impacts(db, project_id, set(names.values()))
    affected_tb_accounts = await _load_tb_impacts(
        db, project_id, year, account_deltas, adjustment_type,
    )
    report_types = {row["report_type"] for row in affected_report_rows}
    cash_related = bool(report_types & {"cash_flow", "cashflow"}) or any(
        code.startswith(("1001", "1002")) for code in unique_codes
    )
    tax_related = any(code.startswith(("2221", "6801")) for code in unique_codes)
    judgment_items = [
        {
            "domain": "cash_flow",
            "label": "现金流量表影响",
            "status": "needs_judgment",
            "reason": "涉及现金或现金流映射，请判断经营、投资或筹资活动分类" if cash_related
            else "仅凭会计科目无法可靠判断是否影响现金流量表",
        },
        {
            "domain": "tax",
            "label": "税务影响",
            "status": "needs_judgment",
            "reason": "涉及税费科目，请判断当期所得税或递延所得税影响" if tax_related
            else "请判断该调整是否形成当期税务或递延所得税影响",
        },
    ]

    return {
        "affected_tb_accounts": affected_tb_accounts,
        "affected_report_rows": affected_report_rows,
        "affected_workpapers": affected_workpapers,
        "affected_notes": affected_notes,
        "judgment_items": judgment_items,
        "unmapped_accounts": sorted(set(unmapped)),
        "direction_unknown_accounts": sorted(set(direction_unknown)),
    }
