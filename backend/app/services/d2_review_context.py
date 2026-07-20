"""D2 跨底稿勾稽上下文 — 注入 AI 复核 user prompt

从 checklist_responses 读取关键 item，计算与前端 useD2CrossSheet 对齐的
勾稽差异摘要，供 LLM 对照「已知数字」而非空泛推断。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from app.core.database import async_session

logger = logging.getLogger(__name__)

_TOLERANCE = 0.01  # 金额容差（元）


def _parse_num(val: Any) -> float:
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _safe_json_rows(remark: str | None) -> list[dict]:
    if not remark:
        return []
    try:
        data = json.loads(remark)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _fmt(n: float) -> str:
    return f"{n:,.2f}"


async def build_d2_reconciliation_context(wp_id: str) -> str:
    """构建 D2 勾稽上下文文本；非 D2 或无数据时返回空串。"""
    try:
        async with async_session() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT item_id, remark FROM checklist_responses "
                        "WHERE wp_id = :wp_id"
                    ),
                    {"wp_id": str(wp_id)},
                )
            ).fetchall()
    except Exception as e:
        logger.warning("build_d2_reconciliation_context failed: %s", e)
        return ""

    if not rows:
        return ""

    by_id: dict[str, str | None] = {r[0]: r[1] for r in rows}
    # 仅当存在 D2 相关 item 时才输出
    if not any(k.startswith("D2-") for k in by_id):
        return ""

    lines: list[str] = ["## 系统已计算的跨底稿勾稽结果（请重点核对，勿忽略已知差异）"]
    alerts: list[str] = []

    # ── D2-2 明细合计 ──
    detail_rows = _safe_json_rows(by_id.get("D2-detail-rows"))
    detail_total = 0.0
    for row in detail_rows:
        detail_total += _parse_num(
            row.get("currentAudited")
            or row.get("current_audited")
            or row.get("audited")
        )

    # ── D2-1 审定合计（三类加总）──
    adj_total = 0.0
    for row_key in ("individual", "aging", "customer-type"):
        unadj = _parse_num(by_id.get(f"D2-adj-{row_key}-current-unadjusted"))
        aje = _parse_num(by_id.get(f"D2-adj-{row_key}-current-aje"))
        rje = _parse_num(by_id.get(f"D2-adj-{row_key}-current-rje"))
        # 若无分项，尝试从明细聚合字段推断（无则跳过）
        if unadj or aje or rje:
            adj_total += unadj + aje + rje

    # 若审定分项全空，尝试用明细合计作为一侧
    if detail_total or adj_total:
        if adj_total == 0 and detail_total:
            # 仅有明细侧
            lines.append(
                f"- D2-2 明细审定合计: {_fmt(detail_total)}（D2-1 审定分项暂无数据，无法完成双侧勾稽）"
            )
        elif detail_total == 0 and adj_total:
            lines.append(
                f"- D2-1 审定合计: {_fmt(adj_total)}（D2-2 明细暂无数据，无法完成双侧勾稽）"
            )
        else:
            diff = adj_total - detail_total
            ok = abs(diff) < _TOLERANCE
            status = "✓ 平衡" if ok else "✗ 不平衡"
            lines.append(
                f"- D2-1↔D2-2 勾稽: 审定合计 {_fmt(adj_total)} vs 明细合计 {_fmt(detail_total)}，"
                f"差异 {_fmt(diff)} → {status}"
            )
            if not ok:
                alerts.append(
                    f"D2-1 与 D2-2 合计差异 {_fmt(diff)} 元，须追查原因"
                )

    # ── D2-2 vs TB ──
    tb_amount = _parse_num(by_id.get("D2-adj-tb-amount"))
    if tb_amount and detail_total:
        tb_diff = detail_total - tb_amount
        ok = abs(tb_diff) < _TOLERANCE
        status = "✓ 平衡" if ok else "✗ 不平衡"
        lines.append(
            f"- D2-2↔TB(1122): 明细合计 {_fmt(detail_total)} vs TB {_fmt(tb_amount)}，"
            f"差异 {_fmt(tb_diff)} → {status}"
        )
        if not ok:
            alerts.append(f"明细表与试算表 1122 差异 {_fmt(tb_diff)} 元")

    # ── D2-3 坏账 vs D2-9 ECL ──
    bd_current = 0.0
    for key in ("D2-bd-individual-rows", "D2-bd-aging-rows", "D2-bd-customer-rows"):
        for row in _safe_json_rows(by_id.get(key)):
            if row.get("isFixed") or row.get("is_fixed"):
                bd_current += _parse_num(
                    row.get("currentAudited") or row.get("current_audited")
                )
                break

    ecl_total = 0.0
    for row in _safe_json_rows(by_id.get("D2-ecl9-rows")):
        ecl_total += _parse_num(
            row.get("shouldProvision") or row.get("should_provision")
        )

    if bd_current or ecl_total:
        if bd_current and ecl_total:
            ecl_diff = ecl_total - bd_current
            ok = abs(ecl_diff) < _TOLERANCE
            status = "✓ 一致" if ok else "✗ 不一致"
            lines.append(
                f"- D2-3↔D2-9: 坏账准备本期 {_fmt(bd_current)} vs 单项ECL应计提 {_fmt(ecl_total)}，"
                f"差异 {_fmt(ecl_diff)} → {status}"
            )
            if not ok:
                alerts.append(f"坏账准备与单项 ECL 差异 {_fmt(ecl_diff)} 元")
        elif bd_current:
            lines.append(f"- D2-3 坏账准备本期合计: {_fmt(bd_current)}（D2-9 ECL 暂无数据）")
        else:
            lines.append(f"- D2-9 单项 ECL 应计提合计: {_fmt(ecl_total)}（D2-3 坏账暂无数据）")

    # ── D2-11 转回核销一致性告警（若存 remark）──
    writeoff_warn = by_id.get("D2-writeoff-section-analysis")
    if writeoff_warn and isinstance(writeoff_warn, str) and len(writeoff_warn) > 10:
        lines.append(f"- D2-11 转回/核销分析摘要: {writeoff_warn[:200]}")

    if len(lines) <= 1:
        return ""

    if alerts:
        lines.append("")
        lines.append("### 须优先关注的勾稽告警")
        for a in alerts:
            lines.append(f"- [高] {a}")

    lines.append("")
    lines.append(
        "复核要求：若上述勾稽显示不平衡/不一致，对应 finding 的 passed 必须为 false，"
        "risk_level 建议 high，并给出可执行的整改建议。"
    )
    return "\n".join(lines)


def append_reconciliation_to_user_prompt(
    user_prompt: str,
    recon_context: str,
) -> str:
    """将勾稽上下文追加到 user prompt"""
    if not recon_context or not recon_context.strip():
        return user_prompt
    return f"{user_prompt}\n\n{recon_context}"
