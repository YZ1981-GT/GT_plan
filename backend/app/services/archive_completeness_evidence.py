"""归档完整性检查新增 5 类（spec attachment-archive-and-a-class-evidence 需求 5，design §7）。

| 类别 | 判据 | 阻断 |
|---|---|---|
| missing_files | 归档清单的缺件（与打包同一实现 ``archive_inventory``） | 是 |
| evidence_gaps | 有证据声明的底稿未满足、关键证据 OCR 未确认或状态不可判断 | 是 |
| unreplied_confirmations | 函证逐笔拆分 missing > 0（同一工作簿只报一次） | 是 |
| unconfirmed_ocr | 普通附件有识别结果但未人工确认 | 否 |
| orphan_files | 附件存储目录下本项目没有任何附件行 / 版本行引用的文件 | 否 |

非阻断类别查询失败 ⇒ 该类为空并记 WARNING（与 ``sampling_records`` 同口径）；``missing_files`` 查询失败 ⇒ 给一条
阻断项，不放行（检查不出来不等于没有缺件）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_CATEGORY_CODE = {"attachment": "附件", "deliverable": "交付件"}


def _item(code: str, name: str, status: str, assignee: str | None = None):
    from app.services.archive_completeness_service import CheckItem

    return CheckItem(wp_code=code, wp_name=name, assignee=assignee, status=status)


async def check_missing_files(db: AsyncSession, project_id: UUID) -> list:
    from app.services.archive_inventory import build_project_inventory

    try:
        inventory = await build_project_inventory(db, project_id)
    except Exception as exc:  # noqa: BLE001 — 阻断类别：查不出来按缺件处理
        logger.warning("归档清单检查失败 project=%s", project_id, exc_info=True)
        return [_item("清单", "归档清单", f"清单检查失败，无法确认文件是否齐全：{exc}")]
    return [
        _item(e.wp_code or _CATEGORY_CODE.get(e.category, e.category), e.label, e.reason)
        for e in inventory.missing
    ]


def _samples_status(samples: dict) -> str:
    """抽凭样本缺证据（spec attachment-voucher-evidence-binding 需求 6.2，非阻断）。"""
    labels = [str(m.get("label") or "") for m in (samples.get("missing_items") or [])[:3]]
    more = "等" if samples["missing"] > 3 else ""
    return (f"{samples['missing']} 笔抽凭样本未取得凭证证据（共 {samples.get('total', 0)} 笔）："
            f"{'、'.join(x for x in labels if x)}{more}")


async def check_evidence(db: AsyncSession, project_id: UUID) -> tuple[list, list]:
    """把统一四态就绪度映射为归档证据缺口和未回函；unknown 也是阻断缺口。"""
    from app.services.evidence_readiness import EvidenceReadinessService

    result = await EvidenceReadinessService(db).evaluate_project(project_id)
    gaps: list = []
    unreplied: list = []
    seen_breakdowns: set[frozenset[str]] = set()
    for row in sorted(result.workpapers, key=lambda item: (item.wp_code or "", str(item.wp_id))):
        if row.status == "not_declared":
            continue
        code = row.wp_code or "证据状态"
        name = row.wp_name or ""
        who = str(row.assignee) if row.assignee else None
        if row.status == "unknown":
            message = row.errors[0].get("message") if row.errors else "证据状态无法判断"
            gaps.append(_item(code, name, str(message), who))
            continue

        labels: list[str] = []
        for req in row.requirements:
            samples = req.get("samples")
            if isinstance(samples, dict) and samples.get("missing"):
                gaps.append(_item(code, name, _samples_status(samples), who))
            if req.get("satisfied"):
                continue
            breakdown = req.get("breakdown")
            if isinstance(breakdown, dict) and breakdown.get("missing"):
                key = frozenset(str(item.get("confirmation_id")) for item in breakdown.get("missing_items") or [])
                if key in seen_breakdowns:
                    continue
                seen_breakdowns.add(key)
                names = [str(item.get("counterparty") or "") for item in breakdown["missing_items"][:3]]
                more = "等" if breakdown["missing"] > 3 else ""
                unreplied.append(_item(
                    code, name,
                    f"{breakdown['missing']} 笔未回函且无替代程序：{'、'.join(value for value in names if value)}{more}",
                    who,
                ))
            else:
                labels.append(str(req["label"]))
        if "key_evidence_ocr_confirmation" in row.missing_types:
            labels.append("关键证据识别结果未人工确认")
        if labels:
            gaps.append(_item(code, name, "缺" + "、".join(labels), who))
    return gaps, unreplied


async def check_unconfirmed_ocr(db: AsyncSession, project_id: UUID) -> list:
    from app.models.attachment_models import Attachment
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from app.services.attachment_ocr_text import is_confirmed
    from app.services.attachment_wp_view import linked_wp_id_sets

    try:
        atts = [a for a in (await db.execute(
            sa.select(Attachment).where(
                Attachment.project_id == project_id, Attachment.is_deleted == sa.false(),
                Attachment.ocr_text.is_not(None),
            ).order_by(Attachment.created_at, Attachment.id)
        )).scalars().all() if (a.ocr_text or "").strip() and not is_confirmed(a)]
        if not atts:
            return []
        wp_sets = await linked_wp_id_sets(db, [a.id for a in atts])
        wp_ids = {w for ws in wp_sets.values() for w in ws}
        codes = dict((await db.execute(
            sa.select(WorkingPaper.id, WpIndex.wp_code).join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
            .where(WorkingPaper.id.in_(wp_ids))
        )).all()) if wp_ids else {}
        out = []
        for a in atts:
            linked = sorted({codes[w] for w in wp_sets.get(str(a.id), set()) if w in codes})
            out.append(_item("、".join(linked) or "未关联底稿", a.file_name, "识别结果未人工确认"))
        return out
    except Exception:  # noqa: BLE001 — 非阻断类别
        logger.warning("识别结果确认检查失败 project=%s", project_id, exc_info=True)
        return []


async def check_orphan_files(db: AsyncSession, project_id: UUID) -> list:
    from app.core.config import settings
    from app.services.archive_inventory import orphan_files

    try:
        base = Path(settings.ATTACHMENT_LOCAL_STORAGE_ROOT) / str(project_id)
        return [_item("附件目录", p.relative_to(base).as_posix(), "未被任何附件记录引用")
                for p in await orphan_files(db, project_id)]
    except Exception:  # noqa: BLE001 — 非阻断类别
        logger.warning("孤儿文件检查失败 project=%s", project_id, exc_info=True)
        return []
