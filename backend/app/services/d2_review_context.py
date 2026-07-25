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


# D2-2 明细行信用风险分类 → D2-1 审定表行 key（与前端 useD2CrossSheet SUMIF 对齐）
_D2_CLASSIFICATION_MAP: dict[str, str] = {
    "单项计提": "individual",
    "账龄组合": "aging",
    "客户类型组合": "customer-type",
}


def _sumif_detail(detail_rows: list[dict], classification: str, field: str) -> float:
    """对明细行按信用风险分类求和某字段（复现前端 sumif）。"""
    total = 0.0
    for row in detail_rows:
        cls = str(
            row.get("creditRiskClassification")
            or row.get("credit_risk_classification")
            or row.get("AI")
            or ""
        )
        if cls == classification:
            total += _parse_num(row.get(field))
    return total


def _d2_audited_total(by_id: dict[str, str | None], detail_rows: list[dict]) -> float:
    """D2-1 审定合计：审定表分项优先，缺失时回退明细 SUMIF（与前端一致）。

    修复：原实现仅在 D2-adj-* 分项非空时才计入，导致「明细已填但审定表未手工填」
    场景下 adj_total=0，误报「审定表无数据」/假不平衡。前端 adjudicationForDisclosure
    对每个分项在 adj 字段为空时回退 SUMIF(detail)，此处对齐。
    """
    total = 0.0
    for cn_cls, row_key in _D2_CLASSIFICATION_MAP.items():
        unadj = _parse_num(by_id.get(f"D2-adj-{row_key}-current-unadjusted"))
        if unadj == 0:
            unadj = _sumif_detail(detail_rows, cn_cls, "currentUnadjusted")
        aje = _parse_num(by_id.get(f"D2-adj-{row_key}-current-aje"))
        if aje == 0:
            aje = _sumif_detail(detail_rows, cn_cls, "currentAje")
        rje = _parse_num(by_id.get(f"D2-adj-{row_key}-current-rje"))
        if rje == 0:
            rje = _sumif_detail(detail_rows, cn_cls, "currentRje")
        total += unadj + aje + rje
    return total


async def _fetch_tb_1122(wp_id: str) -> float | None:
    """从 trial_balance 查 1122 应收账款审定额（DB 权威，v2 正数口径）。"""
    try:
        async with async_session() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT SUM(t.audited_amount) AS audited "
                        "FROM trial_balance t "
                        "JOIN working_paper wp ON wp.project_id = t.project_id "
                        "JOIN projects p ON p.id = t.project_id "
                        "WHERE wp.id = :wp_id AND wp.is_deleted = false "
                        "AND t.is_deleted = false "
                        "AND t.year = COALESCE(p.audit_year, "
                        "EXTRACT(YEAR FROM p.audit_period_end)::int) "
                        "AND t.standard_account_code LIKE '1122%'"
                    ),
                    {"wp_id": str(wp_id)},
                )
            ).first()
    except Exception as e:  # noqa: BLE001
        logger.warning("_fetch_tb_1122 failed: %s", e)
        return None
    if row and row.audited is not None:
        return float(row.audited)
    return None


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

    # ── D2-1 审定合计（三类加总，分项缺失回退明细 SUMIF，与前端一致）──
    adj_total = _d2_audited_total(by_id, detail_rows)

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

    # ── D2-2 vs TB(1122) —— 优先 DB 权威审定额，回退持久化 D2-adj-tb-amount ──
    tb_amount = await _fetch_tb_1122(wp_id)
    if tb_amount is None or tb_amount == 0:
        tb_amount = _parse_num(by_id.get("D2-adj-tb-amount"))
    if tb_amount and detail_total:
        tb_diff = round(detail_total - tb_amount, 2)
        ok = abs(tb_diff) < _TOLERANCE
        status = "✓ 平衡" if ok else "✗ 不平衡"
        lines.append(
            f"- D2-2↔TB(1122): 明细合计 {_fmt(detail_total)} vs 试算表审定 {_fmt(tb_amount)}，"
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
