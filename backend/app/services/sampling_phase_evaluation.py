"""两阶段合并评价（spec voucher-identity-writeback-and-audit-phase 任务 16，需求 7.5 / 7.6，ADR-VK-10）。

记号：P 推断错报，U 错报上限，E 样本实际错报合计（批次评价的 ``sample_error_total``）。

| 口径 | 全年推断错报 | 全年错报上限 |
|---|---|---|
| a 只抽剩余期间（remaining） | ΣP_预审 + P_年审 | ΣU_预审 + U_年审 |
| b 全年扣除预审已检样本（full_minus_interim） | ΣE_预审 + P_年审 | ΣE_预审 + U_年审 |

口径 a 两段总体不重叠，直接相加；口径 b 的年审总体已含预审截止前没被抽到的分录，再加预审推断就重复外推，
预审抽到的分录按实际错报计。预审批次缺 E 时不给口径 b 的合并结果、不以 0 代替（ADR-VK-10）。
全年错报上限与年审批次评价里的可容忍错报比较给出全年结论；两阶段科目范围不一致时结论标「仅供参考」。
预审批次只算年审批次抽凭之前的（年审总体是按那时的预审工作扣除的）。

- ``phase_evaluation``：``GET /sampling/phase-evaluation`` 展示用，不可用时给原因与 ``reason_code``，
  ``applicable=False`` 表示这个批次本来就不需要合并评价（预审批次、没有预审工作的年审批次），界面不显示。
- ``with_combined`` / ``attach_combined``：保存评价（``/voucher-evaluation``）与回填随带评价（``/cutoff-fill``）
  两条写入路径共用，把同一结果写进年审批次评价的 ``combined``；不可用就不写。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import WorkpaperExtractionLog
from app.models.workpaper_models import SampledVoucher

EXTRACTION_TYPE = "voucher_sampling"
MODE_LABELS = {"remaining": "口径 a 只抽剩余期间", "full_minus_interim": "口径 b 全年扣除预审已检样本"}
MISSING_E_MESSAGE = "预审批次缺少实际错报合计，请在预审批次重新保存评价"
#: 这些原因表示「本来就不需要合并评价」，界面不显示；其余是「需要但现在算不出」，要提示用户
NOT_APPLICABLE = frozenset({"batch_not_found", "not_final_batch", "no_final_batch", "no_mode"})
_CENT = Decimal("0.01")


def _amount(value: Any) -> Decimal | None:
    """评价里的金额串 → Decimal；缺失或不可解析返回 None（「没有」与「是 0」不同）。"""
    if value in (None, ""):
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _fmt(value: Decimal) -> str:
    return str(value.quantize(_CENT))


def _criteria(log: Any) -> dict:
    crit = getattr(log, "extraction_criteria", None)
    return crit if isinstance(crit, dict) else {}


def _codes(criteria: dict) -> list[str]:
    filters = criteria.get("filters") if isinstance(criteria.get("filters"), dict) else {}
    return sorted({str(c).strip() for c in filters.get("account_codes") or [] if str(c).strip()})


def _evaluation(criteria: dict) -> dict | None:
    ev = criteria.get("evaluation")
    return ev if isinstance(ev, dict) else None


def _unavailable(reason: str, code: str, **extra: Any) -> dict[str, Any]:
    return {"available": False, "applicable": code not in NOT_APPLICABLE, "reason_code": code,
            "reason": reason, **extra}


async def _logs(db: AsyncSession, workpaper_id: UUID) -> list[Any]:
    log = WorkpaperExtractionLog
    return list((await db.execute(
        sa.select(log)
        .where(log.workpaper_id == workpaper_id, log.extraction_type == EXTRACTION_TYPE, log.is_undone == sa.false())
        .order_by(log.created_at.desc())
    )).scalars().all())


async def _interim_attach_count(db: AsyncSession, project_id: UUID, workpaper_id: UUID) -> int:
    sv = SampledVoucher.__table__.c
    return int((await db.execute(
        sa.select(sa.func.count()).select_from(SampledVoucher.__table__).where(
            sv.project_id == project_id, sv.working_paper_id == workpaper_id, sv.batch_id.is_(None),
            sv.phase == "preliminary", sv.is_deleted == sa.false(),
        )
    )).scalar_one() or 0)


def combine(mode: str, interim: list[dict], final: dict) -> dict[str, Any]:
    """纯函数：按 ADR-VK-10 合并。``interim`` 每项含 projected / upper_limit / sample_error_total（Decimal 或 None），
    ``final`` 含 projected / upper_limit / tolerable_misstatement。调用方已确认所需分量齐全。"""
    p_f, u_f = final["projected"], final["upper_limit"]
    if mode == "remaining":
        part_p = sum((i["projected"] for i in interim), Decimal("0"))
        part_u = sum((i["upper_limit"] for i in interim), Decimal("0"))
        name_p, name_u = "预审各批推断错报", "预审各批错报上限"
    else:
        part_p = part_u = sum((i["sample_error_total"] for i in interim), Decimal("0"))
        name_p = name_u = "预审样本实际错报"
    projected, upper = part_p + p_f, part_u + u_f
    tol = final.get("tolerable_misstatement")
    if tol is None or tol <= 0:
        code, verdict = "undetermined", "年审批次未填可容忍错报，不给全年结论"
    elif upper <= tol:
        code, verdict = "acceptable", f"不超过可容忍错报 {_fmt(tol)} 元，可以接受"
    else:
        code, verdict = "not_acceptable", f"超过可容忍错报 {_fmt(tol)} 元，不可接受"
    message = (f"全年合并（{MODE_LABELS.get(mode, mode)}）：推断错报 = {name_p} {_fmt(part_p)} + 年审 {_fmt(p_f)} = "
               f"{_fmt(projected)} 元；错报上限 = {name_u} {_fmt(part_u)} + 年审 {_fmt(u_f)} = {_fmt(upper)} 元，{verdict}")
    return {
        "mode": mode,
        "interim_component": _fmt(part_p),
        "interim_upper_component": _fmt(part_u),
        "final_projected": _fmt(p_f),
        "final_upper_limit": _fmt(u_f),
        "projected": _fmt(projected),
        "upper_limit": _fmt(upper),
        "tolerable_misstatement": _fmt(tol) if tol is not None else None,
        "conclusion_code": code,
        "conclusion_message": message,
        "interim_batch_count": len(interim),
    }


def _pick_target(logs: list[Any], log_id: UUID | None) -> tuple[Any | None, dict | None]:
    """定位年审批次：给了 log_id 就只认它（不是年审批次如实说）；没给取最近一次带年审口径的。"""
    if log_id is not None:
        target = next((lg for lg in logs if lg.id == log_id), None)
        if target is None:
            return None, _unavailable("没有找到该抽凭批次（或已撤销）", "batch_not_found")
        if _criteria(target).get("phase") != "final":
            return None, _unavailable("该批次不是年审批次，不需要合并评价", "not_final_batch",
                                      final_log_id=str(target.id))
        return target, None
    target = next((lg for lg in logs if _criteria(lg).get("phase") == "final"
                   and _criteria(lg).get("final_population_mode") in MODE_LABELS), None)
    if target is None:
        return None, _unavailable("本底稿没有带年审口径的年审抽凭批次", "no_final_batch")
    return target, None


async def phase_evaluation(
    db: AsyncSession,
    *,
    project_id: UUID,
    workpaper_id: UUID,
    log_id: UUID | None = None,
    final_evaluation: dict | None = None,
) -> dict[str, Any]:
    """本底稿某个年审批次（缺省最近一次未撤销、带年审口径的）的全年合并评价。

    ``final_evaluation`` 给了就用它当年审分量（保存评价时用刚归一好的评价，不读库里旧的）。
    不可用时 ``{"available": False, "applicable": ..., "reason_code": ..., "reason": ...}``，原因写给用户看。
    """
    logs = await _logs(db, workpaper_id)
    target, refused = _pick_target(logs, log_id)
    if target is None:
        return refused
    crit = _criteria(target)
    mode = crit.get("final_population_mode")
    if mode not in MODE_LABELS:
        return _unavailable("该年审批次抽凭时本底稿没有预审工作，不需要合并评价", "no_mode", final_log_id=str(target.id))
    final_ev = final_evaluation if isinstance(final_evaluation, dict) else _evaluation(crit)
    p_f, u_f = (_amount(final_ev.get("projected")), _amount(final_ev.get("upper_limit"))) if final_ev else (None, None)
    if p_f is None or u_f is None:
        return _unavailable("年审批次尚未评价：先录入样本实际错报并推断错报", "final_not_evaluated",
                            final_log_id=str(target.id), mode=mode)

    interim_logs = [lg for lg in logs if _criteria(lg).get("phase") == "preliminary"
                    and lg.created_at < target.created_at]
    interim: list[dict] = []
    # 按抽凭先后编号指认批次（不写时刻：库里是 UTC，直接写进提示会与界面上的本地时间对不上）
    for seq, lg in enumerate(sorted(interim_logs, key=lambda x: x.created_at), start=1):
        ev = _evaluation(_criteria(lg))
        missing = {"final_log_id": str(target.id), "mode": mode, "missing_log_id": str(lg.id)}
        if not ev:
            need = "推断错报与错报上限" if mode == "remaining" else "样本实际错报合计"
            return _unavailable(f"第 {seq} 个预审批次尚未评价（缺{need}），无法合并", "interim_not_evaluated", **missing)
        item = {
            "seq": seq,
            "log_id": str(lg.id),
            "created_at": lg.created_at.isoformat(),
            "projected": _amount(ev.get("projected")),
            "upper_limit": _amount(ev.get("upper_limit")),
            "sample_error_total": _amount(ev.get("sample_error_total")),
            "account_codes": _codes(_criteria(lg)),
        }
        if mode == "remaining" and (item["projected"] is None or item["upper_limit"] is None):
            return _unavailable(f"第 {seq} 个预审批次的评价缺推断错报或错报上限，无法合并", "interim_not_evaluated",
                                **missing)
        if mode == "full_minus_interim" and item["sample_error_total"] is None:
            return _unavailable(f"第 {seq} 个{MISSING_E_MESSAGE}", "missing_sample_error_total", **missing)
        interim.append(item)

    final = {"projected": p_f, "upper_limit": u_f, "tolerable_misstatement": _amount(final_ev.get("tolerable_misstatement"))}
    combined = combine(mode, interim, final)
    final_codes = _codes(crit)
    scope_consistent = all(i["account_codes"] == final_codes for i in interim)
    notes: list[str] = []
    if not scope_consistent:
        notes.append("两阶段科目范围不一致，全年合并结果仅供参考")
    attach_count = await _interim_attach_count(db, project_id, workpaper_id)
    if attach_count:
        notes.append(f"另有预审手工挂凭 {attach_count} 张：其核对结果不在抽样评价里，未计入合并")
    combined["scope_consistent"] = scope_consistent
    combined["notes"] = notes
    if notes:
        combined["conclusion_message"] += "（" + "；".join(notes) + "）"
    return {
        "available": True,
        "applicable": True,
        "mode": mode,
        "final_log_id": str(target.id),
        "interim": [{**i, **{k: (_fmt(i[k]) if i[k] is not None else None)
                             for k in ("projected", "upper_limit", "sample_error_total")}} for i in interim],
        "final": {"projected": _fmt(p_f), "upper_limit": _fmt(u_f),
                  "tolerable_misstatement": combined["tolerable_misstatement"], "account_codes": final_codes},
        "combined": combined,
    }


async def with_combined(db: AsyncSession, *, project_id: UUID, log: Any, evaluation: dict) -> dict:
    """年审批次（带口径）的评价并上服务端现算的全年合并评价，返回新 dict；其他批次、或合并评价
    不可用时原样返回、不写 ``combined``。客户端传来的 ``combined`` 由评价白名单（``_normalize_evaluation``）丢弃。"""
    crit = _criteria(log)
    if crit.get("phase") != "final" or crit.get("final_population_mode") not in MODE_LABELS:
        return evaluation
    merged = await phase_evaluation(db, project_id=project_id, workpaper_id=log.workpaper_id, log_id=log.id,
                                    final_evaluation=evaluation)
    return {**evaluation, "combined": merged["combined"]} if merged.get("available") else evaluation


async def attach_combined(db: AsyncSession, *, project_id: UUID, log: Any) -> None:
    """回填随带评价时（``/cutoff-fill``）同样写入合并评价：整体赋新 dict（JSONB 原地改不触发脏检测）。"""
    crit = _criteria(log)
    ev = _evaluation(crit)
    if ev is None:
        return
    merged = await with_combined(db, project_id=project_id, log=log, evaluation=ev)
    if merged is not ev:
        log.extraction_criteria = {**crit, "evaluation": merged}
        await db.flush()
