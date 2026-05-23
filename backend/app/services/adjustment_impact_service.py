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
            ).where(
                ReportLineMapping.project_id == project_id,
                ReportLineMapping.standard_account_code.in_(account_codes),
                ReportLineMapping.is_confirmed.is_(True),
                ReportLineMapping.is_deleted.is_(False),
            )
        )
    ).all()
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for code, rt, rcode, rname in rows:
        out[code].append(
            {
                "report_type": rt.value if hasattr(rt, "value") else str(rt),
                "row_code": rcode,
                "row_name": rname,
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


async def preview_impact(
    db: AsyncSession,
    project_id: UUID,
    line_items: list[dict[str, Any]],
    year: int | None = None,
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
            "affected_report_rows": [],
            "affected_workpapers": [],
            "unmapped_accounts": [],
        }

    unique_codes = sorted({c for c, _, _ in accounts})

    # ── Step 2: 并行加载方向 + 报表行映射 ──
    direction_map = await _load_account_directions(db, project_id, unique_codes)
    rlm_map = await _load_report_line_mappings(db, project_id, unique_codes)

    # ── Step 3: 计算每个 (report_type, row_code) 累计 delta ──
    # key = (report_type, row_code) → {"row_name", "delta"}
    row_acc: dict[tuple[str, str], dict[str, Any]] = {}

    # 同时收集 unmapped 科目（无 direction 也无 RLM）
    unmapped: list[str] = []

    for code, debit, credit in accounts:
        direction = direction_map.get(code)
        if direction is None and code not in rlm_map:
            unmapped.append(code)
            continue

        delta = _signed_delta(direction, debit, credit)
        if delta == 0:
            continue

        for row in rlm_map.get(code, []):
            key = (row["report_type"], row["row_code"])
            slot = row_acc.setdefault(
                key,
                {"row_name": row["row_name"], "delta": Decimal("0")},
            )
            slot["delta"] += delta

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

    # ── Step 4: 受影响底稿（wp_account_mapping.json） ──
    affected_workpapers = _find_workpapers_for_accounts(unique_codes)

    return {
        "affected_report_rows": affected_report_rows,
        "affected_workpapers": affected_workpapers,
        "unmapped_accounts": sorted(set(unmapped)),
    }
