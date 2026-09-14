"""附注联动服务 — 附注取数 + 一致性校验 + 一键取数（P1 落地，替换原桩实现）

原实现三方法均为桩：check_consistency 恒返回 consistent=True、one_click_fetch 恒 0、
fetch_note_data 只 dump 全部 TB 审定数无节映射。本次按真实数据模型落地：

- 数据源：`trial_balance`（standard_account_code / account_name / audited_amount，v2 正数口径），
  经 `get_active_filter` 走 active dataset 可见性。
- 附注侧：`disclosure_notes.table_data`（JSONB，形如 {rows:[{label,values:[期末/本期,期初/上期],
  is_total}], headers:[...]}），科目主体取 `account_name`。
- 匹配：按 `account_name` 精确匹配 TB 行并汇总 audited；仅在存在可比 TB 数字时比较/取数，
  否则如实标记 skipped（不臆造映射，不假绿）。

只读服务，不改写 disclosure_notes（避免破坏各异的 table_data 结构）；one_click_fetch 返回
每节可从 TB 带入的审定数预览，由前端决定是否应用。
"""

from __future__ import annotations

import uuid
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 金额比较容差（元）。小于此差异视为一致。
_TOLERANCE = Decimal("0.01")


def _to_decimal(val: Any) -> Decimal | None:
    """把任意 value 尽量转 Decimal；无法转返回 None（不抛错）。"""
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _extract_note_current_total(table_data: Any) -> Decimal | None:
    """从附注 table_data 提取"本期/期末"合计（values[0]）。

    规则：优先取 is_total 行的 values[0]；无合计行时，若仅一条数据行也取其 values[0]；
    values[0] 非数值或全空则返回 None（表示该节无可比金额，跳过而非误判）。
    """
    if not isinstance(table_data, dict):
        return None
    rows = table_data.get("rows")
    if not isinstance(rows, list) or not rows:
        return None

    def _first_value(row: Any) -> Decimal | None:
        if not isinstance(row, dict):
            return None
        values = row.get("values")
        if not isinstance(values, list) or not values:
            return None
        return _to_decimal(values[0])

    # 优先合计行
    for row in rows:
        if isinstance(row, dict) and row.get("is_total"):
            v = _first_value(row)
            if v is not None:
                return v
    # 单数据行兜底
    data_rows = [r for r in rows if isinstance(r, dict) and not r.get("is_total")]
    if len(data_rows) == 1:
        return _first_value(data_rows[0])
    return None


class WpNoteLinkageService:
    """底稿与附注联动服务（真实实现）。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 内部：加载 TB 审定数（按 account_name 汇总）
    # ------------------------------------------------------------------
    async def _load_tb_audited_by_name(
        self, project_id: uuid.UUID, year: int
    ) -> dict[str, Decimal]:
        """返回 {account_name: sum(audited_amount)}，走 active dataset 可见性。"""
        from app.models.audit_platform_models import TrialBalance  # 延迟导入避免环依赖
        from app.services.dataset_query import get_active_filter

        try:
            active_filter = await get_active_filter(self.db, TrialBalance.__table__, project_id, year)
        except Exception:  # noqa: BLE001 — 无 dataset 治理时回退基础过滤
            active_filter = TrialBalance.is_deleted.is_(False)

        stmt = (
            select(
                TrialBalance.account_name,
                func.coalesce(func.sum(TrialBalance.audited_amount), 0),
            )
            .where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                active_filter,
                TrialBalance.account_name.isnot(None),
            )
            .group_by(TrialBalance.account_name)
        )
        result = await self.db.execute(stmt)
        out: dict[str, Decimal] = {}
        for name, amt in result.all():
            if not name:
                continue
            out[str(name).strip()] = _to_decimal(amt) or Decimal("0")
        return out

    async def _load_notes(self, project_id: uuid.UUID, year: int) -> list[Any]:
        from app.models.report_models import DisclosureNote

        stmt = select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted.is_(False),
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------
    # 附注取数：返回该节匹配到的 TB 审定数（+全量兜底供既有 LinkageFacade 消费）
    # ------------------------------------------------------------------
    async def fetch_note_data(
        self,
        *,
        project_id: uuid.UUID,
        year: int,
        note_section_code: str,
    ) -> dict:
        """从 TB 取该附注节对应科目的审定数。

        - `data`：全部 TB 审定数（按 standard_account_code），保持既有 LinkageFacade 消费契约。
        - `matched`：按本节 account_name 精确匹配到的审定数（None 表示无可比 TB 行）。
        """
        from app.models.audit_platform_models import TrialBalance
        from app.models.report_models import DisclosureNote
        from app.services.dataset_query import get_active_filter

        try:
            active_filter = await get_active_filter(self.db, TrialBalance.__table__, project_id, year)
        except Exception:  # noqa: BLE001
            active_filter = TrialBalance.is_deleted.is_(False)

        stmt = select(
            TrialBalance.standard_account_code, TrialBalance.audited_amount
        ).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            active_filter,
        )
        rows = (await self.db.execute(stmt)).all()
        data = {code: (float(amt) if amt is not None else 0.0) for code, amt in rows}

        # 匹配本节 account_name → TB 审定数
        matched: float | None = None
        note_stmt = select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == note_section_code,
            DisclosureNote.is_deleted.is_(False),
        )
        note = (await self.db.execute(note_stmt)).scalars().first()
        if note is not None and note.account_name:
            by_name = await self._load_tb_audited_by_name(project_id, year)
            hit = by_name.get(str(note.account_name).strip())
            if hit is not None:
                matched = float(hit)

        return {
            "note_section_code": note_section_code,
            "source": "trial_balance",
            "data": data,
            "matched": matched,
        }

    # ------------------------------------------------------------------
    # 一致性校验：附注合计 vs TB 审定数（按 account_name 匹配）
    # ------------------------------------------------------------------
    async def check_consistency(
        self,
        *,
        project_id: uuid.UUID,
        year: int,
    ) -> dict:
        """校验附注合计与 TB 审定数一致性。

        仅比较"存在可比 TB 审定数 + 附注有数值合计"的节；其余如实计入 skipped，
        不臆造映射、不假绿。返回 inconsistencies 列表（差异超容差项）。
        """
        by_name = await self._load_tb_audited_by_name(project_id, year)
        notes = await self._load_notes(project_id, year)

        inconsistencies: list[dict] = []
        checked = 0
        skipped = 0

        for note in notes:
            name = (note.account_name or "").strip()
            note_total = _extract_note_current_total(note.table_data)
            tb_amt = by_name.get(name) if name else None

            if note_total is None or tb_amt is None:
                skipped += 1
                continue

            checked += 1
            diff = (note_total - tb_amt).copy_abs()
            if diff > _TOLERANCE:
                inconsistencies.append(
                    {
                        "note_section": note.note_section,
                        "section_title": note.section_title,
                        "account_name": name,
                        "note_amount": float(note_total),
                        "tb_audited_amount": float(tb_amt),
                        "difference": float(note_total - tb_amt),
                    }
                )

        return {
            "project_id": str(project_id),
            "year": year,
            "consistent": len(inconsistencies) == 0,
            "checked_sections": checked,
            "skipped_sections": skipped,
            "inconsistencies": inconsistencies,
        }

    # ------------------------------------------------------------------
    # 一键取数（只读预览）：列出每节可从 TB 带入的审定数
    # ------------------------------------------------------------------
    async def one_click_fetch(
        self,
        *,
        project_id: uuid.UUID,
        year: int,
    ) -> dict:
        """遍历附注节，返回每节可从 TB 带入的审定数预览（只读，不改写 table_data）。

        不直接改写 disclosure_notes（各节 table_data 结构各异，改写风险高）；返回预览供前端
        逐节确认后应用。`available_sections` = 能匹配到 TB 审定数的节数。
        """
        by_name = await self._load_tb_audited_by_name(project_id, year)
        notes = await self._load_notes(project_id, year)

        sections: list[dict] = []
        available = 0
        for note in notes:
            name = (note.account_name or "").strip()
            tb_amt = by_name.get(name) if name else None
            if tb_amt is None:
                continue
            available += 1
            note_total = _extract_note_current_total(note.table_data)
            sections.append(
                {
                    "note_section": note.note_section,
                    "section_title": note.section_title,
                    "account_name": name,
                    "tb_audited_amount": float(tb_amt),
                    "current_note_amount": float(note_total) if note_total is not None else None,
                }
            )

        logger.info(
            "one_click_fetch preview project=%s year=%s available=%d",
            project_id, year, available,
        )
        return {
            "project_id": str(project_id),
            "year": year,
            "available_sections": available,
            "sections": sections,
        }
