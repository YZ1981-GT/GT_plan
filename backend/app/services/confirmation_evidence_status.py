"""函证底稿「函证」证据声明的逐笔判定（spec attachment-confirmation-evidence-loop 需求 6，ADR-ACE-07）。

改造前：底稿下只要有任意一份函证附件，「函证回函件」就判满足，看不出哪几笔缺回函、哪几笔做了替代程序。
这里按底稿所在工作簿（同一编码族：``D0`` / ``D0-1`` … ``D0-8``，整册一张或拆成多张两种形态都覆盖）登记的函证逐笔判：

- 已回函：有回函件，或状态为已回函 / 相符 / 差异；
- 替代程序：未回函，但族内替代程序页（``html_data`` 里 ``_format`` 以 ``alternative-`` 开头的页）有该函证对象的公司，
  且公司任一检查行上挂了附件（行级证据 ``row:{行 id}``）；公司 ↔ 函证按函证索引号（同步时写进函证的
  ``account_code``）或名称（去空白、全角括号转半角、不区分大小写）对应；
- 其余缺证据：无发函件且状态为待发函 ⇒「未发函」，否则「未回函且未做替代程序」。

族内没有登记函证 ⇒ 返回 None，调用方沿用原判定。只读查询。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment
from app.models.confirmation_models import Confirmation, ConfirmationAttachmentLink
from app.models.wp_optimization_models import EvidenceLink
from app.models.workpaper_models import WorkingPaper, WpIndex

REASON_NOT_SENT = "未发函"
REASON_NO_EVIDENCE = "未回函且未做替代程序"
_REPLIED_STATUSES = frozenset({"returned", "matched", "discrepancy"})
_SHEET_SUFFIX = re.compile(r"-\d+[A-Za-z]?$")
_BLOCK_ROWS = re.compile(r"block\d+_rows")


def workbook_code_of(wp_code: str | None) -> str:
    """``D0-5`` → ``D0``、``D0-4b`` → ``D0``（与前端 ``importFromSummary.workbookCodeOf`` 同口径）。"""
    return _SHEET_SUFFIX.sub("", (wp_code or "").strip())


def normalize_name(name: Any) -> str:
    text = re.sub(r"\s+", "", str(name or "")).replace("（", "(").replace("）", ")")
    return text.casefold()


@dataclass(frozen=True)
class _Company:
    index: str
    name: str
    has_evidence: bool


def _alternative_companies(parsed: Any) -> list[dict]:
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except (TypeError, ValueError):
            return []
    html = parsed.get("html_data") if isinstance(parsed, dict) else None
    if not isinstance(html, dict):
        return []
    out: list[dict] = []
    for sheet in html.values():
        if isinstance(sheet, dict) and str(sheet.get("_format") or "").startswith("alternative-"):
            out.extend(c for c in sheet.get("companies") or [] if isinstance(c, dict))
    return out


def _row_cells(company: dict) -> set[str]:
    cells: set[str] = set()
    for key, rows in company.items():
        if _BLOCK_ROWS.fullmatch(str(key)) and isinstance(rows, list):
            cells.update(f"row:{r['_row_id']}" for r in rows if isinstance(r, dict) and r.get("_row_id"))
    return cells


async def _family(db: AsyncSession, project_id: UUID, wp_code: str | None) -> list[UUID]:
    book = workbook_code_of(wp_code)
    if not book:
        return []
    rows = (await db.execute(
        sa.select(WorkingPaper.id, WpIndex.wp_code)
        .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
            WpIndex.wp_code.like(f"{book}%"),
        )
    )).all()
    return [wid for wid, code in rows if workbook_code_of(code) == book]


async def _companies(db: AsyncSession, family: list[UUID]) -> list[_Company]:
    """族内替代程序页的公司；有证据 = 公司任一检查行的 ``row:{行 id}`` 在同一底稿上挂了未删除的附件。

    底稿数据（``parsed_data``）体量大，只在族内确有函证时才读。
    """
    parsed_rows = (await db.execute(
        sa.select(WorkingPaper.id, WorkingPaper.parsed_data).where(WorkingPaper.id.in_(family))
    )).all()
    pages = [(wid, _alternative_companies(parsed)) for wid, parsed in parsed_rows]
    pages = [(wid, comps) for wid, comps in pages if comps]
    if not pages:
        return []
    linked: dict[UUID, set[str]] = defaultdict(set)
    rows = (await db.execute(
        sa.select(EvidenceLink.wp_id, EvidenceLink.cell_ref)
        .join(Attachment, Attachment.id == EvidenceLink.attachment_id)
        .where(
            EvidenceLink.wp_id.in_([wid for wid, _ in pages]),
            EvidenceLink.cell_ref.like("row:%"),
            Attachment.is_deleted == sa.false(),
        )
    )).all()
    for wid, cell in rows:
        linked[wid].add(cell)
    return [
        _Company(
            index=str(comp.get("confirm_index") or "").strip(),
            name=normalize_name(comp.get("entity_name")),
            has_evidence=bool(_row_cells(comp) & linked[wid]),
        )
        for wid, comps in pages for comp in comps
    ]


def _has_alternative(conf: Confirmation, companies: list[_Company]) -> bool:
    index = (conf.account_code or "").strip()
    name = normalize_name(conf.counterparty)
    return any(
        c.has_evidence and ((index and c.index == index) or (name and c.name == name))
        for c in companies
    )


async def confirmation_breakdown(db: AsyncSession, project_id: UUID, wp_code: str | None) -> dict | None:
    """本底稿所在工作簿登记的函证逐笔判定；族内没有函证 ⇒ None。"""
    family = await _family(db, project_id, wp_code)
    if not family:
        return None
    confs = (await db.execute(
        sa.select(Confirmation)
        .where(Confirmation.project_id == project_id, Confirmation.wp_id.in_(family))
        .order_by(Confirmation.created_at, Confirmation.id)
    )).scalars().all()
    if not confs:
        return None
    counts: dict[tuple[UUID, str], int] = {}
    for cid, role, n in (await db.execute(
        sa.select(ConfirmationAttachmentLink.confirmation_id, ConfirmationAttachmentLink.role, sa.func.count())
        .join(Attachment, Attachment.id == ConfirmationAttachmentLink.attachment_id)
        .where(ConfirmationAttachmentLink.confirmation_id.in_([c.id for c in confs]), Attachment.is_deleted == sa.false())
        .group_by(ConfirmationAttachmentLink.confirmation_id, ConfirmationAttachmentLink.role)
    )).all():
        counts[(cid, role)] = int(n)
    companies = await _companies(db, family)

    replied = alternative = 0
    missing: list[dict[str, str]] = []
    for conf in confs:
        if counts.get((conf.id, "inbound"), 0) > 0 or conf.status in _REPLIED_STATUSES:
            replied += 1
        elif _has_alternative(conf, companies):
            alternative += 1
        else:
            not_sent = counts.get((conf.id, "outbound"), 0) == 0 and conf.status == "pending"
            missing.append({
                "confirmation_id": str(conf.id),
                "counterparty": conf.counterparty,
                "confirm_type": conf.confirm_type,  # 律师函没有替代程序页：界面按类型给补救提示
                "reason": REASON_NOT_SENT if not_sent else REASON_NO_EVIDENCE,
            })
    return {
        "total": len(confs), "replied": replied, "alternative": alternative,
        "missing": len(missing), "missing_items": missing,
    }
