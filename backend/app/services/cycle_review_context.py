"""通用跨底稿勾稽上下文 — 注入 AI 复核 user prompt（K/N 循环）

参照 D2 的 d2_review_context 设计，把「系统已计算的跨底稿勾稽结果」以确定性数字
注入 LLM 复核提示，使 AI 对照已知数字判断而非空泛推断，显著提升复核准确度。

覆盖：K1~K13（其他应收/其他流动资产/其他应付/其他流动负债/预计负债/持有待售/
递延收益/销售费用/管理费用/其他收益/资产减值损失/营业外收入/营业外支出）
      N1~N5（递延所得税资产/应交税费/递延所得税负债/税金及附加/所得税费用）

数据来源：
- 审定表合计 / 明细表合计：checklist_responses（与前端 useXCrossSheet 同键，保持口径一致）
- 试算表(TB)审定额/未审额：直接查 trial_balance（v2 正数口径），权威、不依赖前端持久化

设计约束：
- 全程 try/except fail-open，任何异常返回空串，绝不阻断复核主流程。
- 只有存在该循环相关 checklist item 时才输出（避免误注入）。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from app.core.database import async_session

logger = logging.getLogger(__name__)

_TOLERANCE = 0.01  # 金额容差（元）

# finding severity（对齐 design AuditCheckItem severity 取值，避免耦合 audit_check.models）
_SEV_BLOCKING = "blocking"
_SEV_WARNING = "warning"
_SEV_INFO = "info"


# ---------------------------------------------------------------------------
# 循环勾稽配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CycleReconConfig:
    """单循环勾稽配置。

    审定合计与明细合计的 item_id 与前端 useXCrossSheet 严格对齐，保持口径一致。
    """

    label: str                              # 科目中文名
    account_codes: tuple[str, ...]          # TB 科目前缀（审定↔TB 一致性核对 + 未审→审定幅度）
    is_occurrence: bool                     # 损益类（审定=发生额，非期末余额）
    audited_total_keys: tuple[str, ...]     # 审定表合计 item_id（多个则求和，如 N5 当期+递延）
    detail_total_keys: tuple[str, ...] = ()  # 明细表合计 item_id（取第一个非零）
    detail_rows_key: str | None = None       # 明细行 JSON item_id（行求和场景，如 N2/N3）
    detail_rows_field: str | None = None     # 行内金额字段名
    detail_rows_store: str = "conclusion"    # 明细行 JSON 存储字段（remark|conclusion）
    detail_label: str = "明细表"             # 明细侧展示标签


# 前端 useXCrossSheet / useXAdjudication / useXDetail 实测键（2026-07）。
_REGISTRY: dict[str, CycleReconConfig] = {
    # ── K 循环 ──────────────────────────────────────────────────────────
    "K1": CycleReconConfig(
        label="其他应收款", account_codes=("1221",), is_occurrence=False,
        audited_total_keys=("K1-1-audited-receivable",),
        detail_total_keys=("K1-2-end-subtotal",),
    ),
    "K2": CycleReconConfig(
        label="其他流动资产", account_codes=("1231",), is_occurrence=False,
        audited_total_keys=("K2-1-end-balance-total",),
        detail_total_keys=("K2-2-end-total",),
    ),
    "K3": CycleReconConfig(
        label="其他应付款", account_codes=("2241",), is_occurrence=False,
        audited_total_keys=("K3-1-audited-total",),
        detail_total_keys=("K3-2-detail-total",),
    ),
    "K4": CycleReconConfig(
        label="其他流动负债", account_codes=("2245",), is_occurrence=False,
        audited_total_keys=("K4-1-audited-total",),
        detail_total_keys=("K4-2-detail-total",),
    ),
    "K5": CycleReconConfig(
        label="预计负债", account_codes=("2701",), is_occurrence=False,
        audited_total_keys=("K5-1-audited-total",),
        detail_total_keys=("K5-2-detail-end-total", "K5-2-detail-total"),
    ),
    "K6": CycleReconConfig(
        label="持有待售", account_codes=("1481", "2605"), is_occurrence=False,
        audited_total_keys=("K6-1-audited-total",),
        detail_total_keys=("K6-2-detail-book-value-total", "K6-2-detail-total"),
    ),
    "K7": CycleReconConfig(
        label="递延收益", account_codes=("2401",), is_occurrence=False,
        audited_total_keys=("K7-1-audited-total",),
        detail_total_keys=("K7-2-detail-end-total",),
    ),
    "K8": CycleReconConfig(
        label="销售费用", account_codes=("6601",), is_occurrence=True,
        audited_total_keys=("K8-1-audited-total",),
        detail_total_keys=("K8-2-total-audited",),
    ),
    "K9": CycleReconConfig(
        label="管理费用", account_codes=("6602",), is_occurrence=True,
        audited_total_keys=("K9-1-audited-total",),
        detail_total_keys=("K9-2-detail-audited-total", "K9-2-total-audited"),
    ),
    "K10": CycleReconConfig(
        label="其他收益", account_codes=("6117",), is_occurrence=True,
        audited_total_keys=("K10-1-audited-total",),
        detail_total_keys=("K10-2-subtotal",),
    ),
    "K11": CycleReconConfig(
        label="资产减值损失", account_codes=("6701",), is_occurrence=True,
        audited_total_keys=("K11-1-audited-total",),
        detail_total_keys=("K11-2-total-occurrence",),
    ),
    "K12": CycleReconConfig(
        label="营业外收入", account_codes=("6301",), is_occurrence=True,
        audited_total_keys=("K12-1-audited-total",),
        detail_total_keys=("K12-2-subtotal",),
    ),
    "K13": CycleReconConfig(
        label="营业外支出", account_codes=("6711",), is_occurrence=True,
        audited_total_keys=("K13-1-audited-total",),
        detail_total_keys=("K13-2-subtotal",),
    ),
    # ── N 循环 ──────────────────────────────────────────────────────────
    "N1": CycleReconConfig(
        label="递延所得税资产", account_codes=("1811",), is_occurrence=False,
        audited_total_keys=("N1-1-total-audited",),
        detail_total_keys=("N1-2-total-deferred-tax-asset",),
    ),
    "N2": CycleReconConfig(
        label="应交税费", account_codes=("2221",), is_occurrence=False,
        audited_total_keys=("N2-1-total-audited",),
        detail_rows_key="N2-2-rows", detail_rows_field="endBalance",
        detail_rows_store="conclusion",
    ),
    "N3": CycleReconConfig(
        label="递延所得税负债", account_codes=("2901",), is_occurrence=False,
        audited_total_keys=("N3-1-end-balance-total",),
        detail_rows_key="N3-2-rows", detail_rows_field="endDeferredTaxLiability",
        detail_rows_store="conclusion",
    ),
    "N4": CycleReconConfig(
        label="税金及附加", account_codes=("6403",), is_occurrence=True,
        audited_total_keys=("N4-1-audited-total",),
        detail_total_keys=("N4-2-subtotal",),
    ),
    "N5": CycleReconConfig(
        label="所得税费用", account_codes=("6801",), is_occurrence=True,
        # 所得税费用 = 当期所得税费用 + 递延所得税费用（回填至审定表 sheet）
        audited_total_keys=("N5-1-current-tax", "N5-1-deferred-tax"),
    ),
}


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _parse_num(val: Any) -> float:
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _fmt(n: float) -> str:
    return f"{n:,.2f}"


def extract_cycle_code(wp_code: str | None) -> str | None:
    """从 wp_code 提取循环编码前缀，如 'K9-1' → 'K9'、'N2' → 'N2'。"""
    if not wp_code:
        return None
    m = re.match(r"([A-Z]\d+)", wp_code.strip(), re.IGNORECASE)
    return m.group(1).upper() if m else None


def _num_from_map(by_id: dict[str, dict[str, Any]], item_id: str) -> float:
    """从 checklist 映射读数值（优先 remark，回退 conclusion）。"""
    entry = by_id.get(item_id)
    if not entry:
        return 0.0
    return _parse_num(entry.get("remark")) or _parse_num(entry.get("conclusion"))


def _sum_rows_field(
    by_id: dict[str, dict[str, Any]],
    rows_key: str,
    field_name: str,
    store: str,
) -> tuple[float, bool]:
    """对明细行 JSON 内某字段求和；返回 (合计, 是否有行)。

    N2/N3 明细存为 JSON 数组，字段可能缺失时用 0（与前端一致，前端另有兜底公式，
    此处仅做合计核对，取行内已算好的期末值即可）。
    """
    entry = by_id.get(rows_key)
    if not entry:
        return 0.0, False
    raw = entry.get(store) or entry.get("remark") or entry.get("conclusion")
    if not raw:
        return 0.0, False
    try:
        rows = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return 0.0, False
    if not isinstance(rows, list) or not rows:
        return 0.0, False
    total = 0.0
    for row in rows:
        if isinstance(row, dict):
            total += _parse_num(row.get(field_name))
    return total, True


async def _fetch_tb_amounts(
    project_id: str, year: int, account_codes: tuple[str, ...]
) -> dict[str, float] | None:
    """查 trial_balance（v2 正数口径）该科目未审/审定合计。

    对多个科目前缀分别 LIKE 求和后累加。失败返回 None。
    """
    if not account_codes:
        return None
    total_unadj = 0.0
    total_audited = 0.0
    found = False
    try:
        async with async_session() as db:
            for code in account_codes:
                row = (
                    await db.execute(
                        text(
                            "SELECT SUM(unadjusted_amount) AS unadjusted, "
                            "SUM(audited_amount) AS audited "
                            "FROM trial_balance "
                            "WHERE project_id = :pid AND year = :year "
                            "AND is_deleted = false "
                            "AND standard_account_code LIKE :prefix"
                        ),
                        {"pid": project_id, "year": year, "prefix": f"{code}%"},
                    )
                ).first()
                if row:
                    if row.unadjusted is not None:
                        total_unadj += float(row.unadjusted)
                        found = True
                    if row.audited is not None:
                        total_audited += float(row.audited)
                        found = True
    except Exception as e:  # noqa: BLE001
        logger.warning("cycle_review_context TB fetch failed: %s", e)
        return None
    if not found:
        return None
    return {"unadjusted": total_unadj, "audited": total_audited}


async def _get_project_year(wp_id: str) -> tuple[str | None, int | None]:
    """从 working_paper JOIN projects 取 project_id + 审计年度。

    年度优先 projects.audit_year，回退 audit_period_end 的年份。
    """
    try:
        async with async_session() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT wp.project_id, p.audit_year, "
                        "EXTRACT(YEAR FROM p.audit_period_end)::int AS end_year "
                        "FROM working_paper wp "
                        "JOIN projects p ON wp.project_id = p.id "
                        "WHERE wp.id = :wp_id AND wp.is_deleted = false"
                    ),
                    {"wp_id": wp_id},
                )
            ).first()
    except Exception as e:  # noqa: BLE001
        logger.warning("cycle_review_context _get_project_year failed: %s", e)
        return None, None
    if not row:
        return None, None
    year = row.audit_year if row.audit_year else row.end_year
    return (str(row.project_id) if row.project_id else None), (int(year) if year else None)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


@dataclass
class _CycleReconData:
    """文本版与结构化版共用的中间计算结果（单一判定口径的唯一数据源）。"""

    cycle: str
    cfg: CycleReconConfig
    audited_total: float
    detail_total: float
    has_detail: bool
    tb: dict[str, float] | None  # {"unadjusted", "audited"} 或 None（无 TB 数据）


async def _compute_cycle_reconciliation(
    wp_id: str, wp_code: str
) -> _CycleReconData | None:
    """读 checklist + 算审定合计/明细合计/TB —— 文本版与结构化版共用核心。

    不在注册表返回 None；checklist 读取异常返回 None（fail-open）。
    此处集中「读 checklist + 算审定/明细/TB + 判定所需数据」，
    `build_cycle_reconciliation_context`（文本）与
    `build_cycle_reconciliation_findings`（结构化）都调用它，杜绝两套口径。
    """
    cycle = extract_cycle_code(wp_code)
    if not cycle or cycle not in _REGISTRY:
        return None
    cfg = _REGISTRY[cycle]

    # 1. 读 checklist_responses
    try:
        async with async_session() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT item_id, remark, conclusion FROM checklist_responses "
                        "WHERE wp_id = :wp_id"
                    ),
                    {"wp_id": str(wp_id)},
                )
            ).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("_compute_cycle_reconciliation checklist read failed: %s", e)
        return None

    by_id: dict[str, dict[str, Any]] = {
        r[0]: {"remark": r[1], "conclusion": r[2]} for r in rows
    }

    # 2. 审定表合计（多键求和）
    audited_total = sum(_num_from_map(by_id, k) for k in cfg.audited_total_keys)

    # 3. 明细表合计
    detail_total = 0.0
    has_detail = False
    for k in cfg.detail_total_keys:
        v = _num_from_map(by_id, k)
        if v:
            detail_total = v
            has_detail = True
            break
    if not has_detail and cfg.detail_rows_key and cfg.detail_rows_field:
        detail_total, has_detail = _sum_rows_field(
            by_id, cfg.detail_rows_key, cfg.detail_rows_field, cfg.detail_rows_store
        )

    # 4. TB 未审/审定（DB 权威）
    project_id, year = await _get_project_year(str(wp_id))
    tb: dict[str, float] | None = None
    if project_id and year:
        tb = await _fetch_tb_amounts(project_id, year, cfg.account_codes)

    return _CycleReconData(
        cycle=cycle,
        cfg=cfg,
        audited_total=audited_total,
        detail_total=detail_total,
        has_detail=has_detail,
        tb=tb,
    )


def _format_cycle_recon_text(data: _CycleReconData) -> str:
    """把中间计算结果格式化为 AI 复核 prompt 文本（纯函数，与结构化版同源数据）。"""
    cfg = data.cfg
    audited_total = data.audited_total
    detail_total = data.detail_total
    has_detail = data.has_detail
    tb = data.tb

    # 若既无审定/明细数据、也无 TB → 无可注入内容
    if audited_total == 0 and not has_detail and not tb:
        return ""

    amount_kind = "审定发生额" if cfg.is_occurrence else "审定期末余额"
    lines: list[str] = [
        f"## 系统已计算的跨底稿勾稽结果（{cfg.label}，请重点核对，勿忽略已知差异）"
    ]
    alerts: list[str] = []

    # ── 审定表 ↔ 明细表 ────────────────────────────────────────────────
    if audited_total or has_detail:
        if has_detail and audited_total:
            diff = round(audited_total - detail_total, 2)
            ok = abs(diff) < _TOLERANCE
            status = "✓ 平衡" if ok else "✗ 不平衡"
            lines.append(
                f"- 审定表↔{cfg.detail_label}: 审定合计 {_fmt(audited_total)} vs "
                f"{cfg.detail_label}合计 {_fmt(detail_total)}，差异 {_fmt(diff)} → {status}"
            )
            if not ok:
                alerts.append(
                    f"{cfg.label}审定表与明细表合计差异 {_fmt(diff)} 元，须追查漏项或计算偏差"
                )
        elif audited_total:
            lines.append(
                f"- 审定表合计: {_fmt(audited_total)}（{cfg.detail_label}暂无数据，无法完成双侧勾稽）"
            )
        elif has_detail:
            lines.append(
                f"- {cfg.detail_label}合计: {_fmt(detail_total)}（审定表暂无数据，无法完成双侧勾稽）"
            )

    # ── 审定表 ↔ 试算表（回写一致性 + 未审→审定幅度）──────────────────
    if tb:
        tb_unadj = tb["unadjusted"]
        tb_audited = tb["audited"]
        # 4a. 审定合计 ↔ TB 审定（仅当 TB 审定非零时判定；否则说明尚未回写）
        if tb_audited:
            if audited_total:
                tb_diff = round(audited_total - tb_audited, 2)
                ok = abs(tb_diff) < _TOLERANCE
                status = "✓ 一致" if ok else "✗ 不一致"
                lines.append(
                    f"- 审定表↔试算表({'/'.join(cfg.account_codes)}): 审定合计 "
                    f"{_fmt(audited_total)} vs 试算表{amount_kind} {_fmt(tb_audited)}，"
                    f"差异 {_fmt(tb_diff)} → {status}"
                )
                if not ok:
                    alerts.append(
                        f"{cfg.label}审定表合计与试算表{amount_kind}差异 {_fmt(tb_diff)} 元"
                        "（审定回写可能未执行或已过期，须核实）"
                    )
            else:
                lines.append(
                    f"- 试算表({'/'.join(cfg.account_codes)}){amount_kind}: "
                    f"{_fmt(tb_audited)}（审定表暂无合计）"
                )
        # 4b. 未审→审定 调整幅度（信息项，供 AI 判断调整合理性）
        #     仅当审定额已回写(非零)时才比较调整幅度；否则审定未做，
        #     展示未审额但不给出「-100%」式误导性调整净额。
        if tb_audited:
            adj_delta = round(tb_audited - tb_unadj, 2)
            lines.append(
                f"- 试算表{cfg.label}: 未审 {_fmt(tb_unadj)} → 审定 {_fmt(tb_audited)}，"
                f"调整净额 {_fmt(adj_delta)}"
            )
        elif tb_unadj:
            lines.append(
                f"- 试算表{cfg.label}未审 {_fmt(tb_unadj)}"
                "（审定额尚未回写，暂不比较调整幅度）"
            )

    # 无实质勾稽行（仅标题）→ 不注入
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
        "risk_level 建议 high，并给出可执行的整改建议；若均平衡，可将相应数据完整性检查项标记为通过。"
    )
    return "\n".join(lines)


def _map_cycle_recon_findings(data: _CycleReconData) -> list[dict]:
    """把中间计算结果映射为结构化 finding 列表（纯函数，与文本版同源数据）。

    与 `_format_cycle_recon_text` 共用同一 `_CycleReconData` + 同一容差 `_TOLERANCE`
    + 同一平衡判定，保证结构化 finding 的 passed/diff 与文本版平衡/不平衡结论一致。
    """
    cfg = data.cfg
    cycle = data.cycle
    audited_total = data.audited_total
    detail_total = data.detail_total
    has_detail = data.has_detail
    tb = data.tb

    # 与文本版同门槛：既无审定/明细数据、也无 TB → 无 finding
    if audited_total == 0 and not has_detail and not tb:
        return []

    amount_kind = "审定发生额" if cfg.is_occurrence else "审定期末余额"
    findings: list[dict] = []

    # ── 审定表 ↔ 明细表（cross_ref / warning）────────────────────────
    if audited_total or has_detail:
        if has_detail and audited_total:
            diff = round(audited_total - detail_total, 2)
            ok = abs(diff) < _TOLERANCE
            findings.append({
                "code": f"{cycle}-RECON-DETAIL",
                "passed": ok,
                "actual": round(audited_total, 2),
                "expected": round(detail_total, 2),
                "diff": diff,
                "message": (
                    f"审定表↔{cfg.detail_label}：审定合计 {_fmt(audited_total)} vs "
                    f"{cfg.detail_label}合计 {_fmt(detail_total)}，差异 {_fmt(diff)}"
                    + ("（平衡）" if ok else "（不平衡，须追查漏项或计算偏差）")
                ),
                "severity": _SEV_WARNING,
                "check_type": "cross_ref",
            })
        else:
            # 缺一侧数据 → 未覆盖（passed=None）
            present = "审定表" if audited_total else cfg.detail_label
            findings.append({
                "code": f"{cycle}-RECON-DETAIL",
                "passed": None,
                "actual": round(audited_total, 2) if audited_total else None,
                "expected": round(detail_total, 2) if has_detail else None,
                "diff": None,
                "message": (
                    f"审定表↔{cfg.detail_label}：仅一侧有数据（{present}），"
                    "无法完成双侧勾稽"
                ),
                "severity": _SEV_WARNING,
                "check_type": "cross_ref",
            })

    # ── 审定表 ↔ 试算表（balance / blocking）+ 未审→审定幅度（analysis / info）──
    if tb is not None:
        tb_unadj = tb["unadjusted"]
        tb_audited = tb["audited"]
        # 审定合计 ↔ TB 审定
        if tb_audited and audited_total:
            tb_diff = round(audited_total - tb_audited, 2)
            ok = abs(tb_diff) < _TOLERANCE
            findings.append({
                "code": f"{cycle}-RECON-TB",
                "passed": ok,
                "actual": round(audited_total, 2),
                "expected": round(tb_audited, 2),
                "diff": tb_diff,
                "message": (
                    f"审定表↔试算表({'/'.join(cfg.account_codes)})：审定合计 "
                    f"{_fmt(audited_total)} vs 试算表{amount_kind} {_fmt(tb_audited)}，"
                    f"差异 {_fmt(tb_diff)}"
                    + ("（一致）" if ok else "（不一致，审定回写可能未执行或已过期）")
                ),
                "severity": _SEV_BLOCKING,
                "check_type": "balance",
            })
        elif tb_audited or audited_total:
            # 缺一侧（审定表未填 或 TB 尚未回写）→ 未覆盖（passed=None）
            present = "审定表" if audited_total else "试算表"
            findings.append({
                "code": f"{cycle}-RECON-TB",
                "passed": None,
                "actual": round(audited_total, 2) if audited_total else None,
                "expected": round(tb_audited, 2) if tb_audited else None,
                "diff": None,
                "message": (
                    f"审定表↔试算表({'/'.join(cfg.account_codes)})：仅一侧有数据"
                    f"（{present}），无法核对回写一致性"
                ),
                "severity": _SEV_BLOCKING,
                "check_type": "balance",
            })
        # 未审→审定 调整幅度（信息项，恒 passed=None）
        if tb_audited:
            adj_delta = round(tb_audited - tb_unadj, 2)
            findings.append({
                "code": f"{cycle}-RECON-ADJ",
                "passed": None,
                "actual": round(tb_audited, 2),
                "expected": round(tb_unadj, 2),
                "diff": adj_delta,
                "message": (
                    f"试算表{cfg.label}：未审 {_fmt(tb_unadj)} → 审定 {_fmt(tb_audited)}，"
                    f"调整净额 {_fmt(adj_delta)}"
                ),
                "severity": _SEV_INFO,
                "check_type": "analysis",
            })
        elif tb_unadj:
            findings.append({
                "code": f"{cycle}-RECON-ADJ",
                "passed": None,
                "actual": None,
                "expected": round(tb_unadj, 2),
                "diff": None,
                "message": (
                    f"试算表{cfg.label}未审 {_fmt(tb_unadj)}"
                    "（审定额尚未回写，暂不比较调整幅度）"
                ),
                "severity": _SEV_INFO,
                "check_type": "analysis",
            })

    return findings


async def build_cycle_reconciliation_context(wp_id: str, wp_code: str) -> str:
    """构建 K/N 循环勾稽上下文文本；不在注册表或无数据时返回空串。

    重构为「共用核心 `_compute_cycle_reconciliation` + 文本格式化
    `_format_cycle_recon_text`」，与结构化版 `build_cycle_reconciliation_findings`
    共用同一 `_REGISTRY`、同一取数、同一判定逻辑，文本输出与重构前等价。
    """
    data = await _compute_cycle_reconciliation(wp_id, wp_code)
    if data is None:
        return ""
    return _format_cycle_recon_text(data)


async def build_cycle_reconciliation_findings(wp_id: str, wp_code: str) -> list[dict]:
    """结构化版勾稽产出：与 `build_cycle_reconciliation_context` 共用同一 `_REGISTRY`
    与计算（`_compute_cycle_reconciliation`），返回结构化 finding 列表。

    返回 `[{code, passed, actual, expected, diff, message, severity, check_type}, ...]`，
    覆盖三类 finding：
      · 审定表↔明细表（code `{cycle}-RECON-DETAIL`，cross_ref / warning）
      · 审定表↔试算表（code `{cycle}-RECON-TB`，balance / blocking —— 回写一致性关键）
      · 未审→审定幅度（code `{cycle}-RECON-ADJ`，analysis / info，恒 passed=None）

    单一判定口径（Property 5 / Req4.2）：与文本版共用 `_TOLERANCE` 与平衡判定。
      · passed：审定↔明细、审定↔TB 双侧数据齐全时 abs(diff)<_TOLERANCE→True 否则 False；
        缺一侧→None（未覆盖）；未审→审定幅度为信息项恒 None。
    fail-open：不在注册表 / 无数据返回 []（与文本版一致），异常返回 []。
    """
    try:
        data = await _compute_cycle_reconciliation(wp_id, wp_code)
    except Exception as e:  # noqa: BLE001 — fail-open，绝不阻断聚合
        logger.warning(
            "build_cycle_reconciliation_findings failed (%s): %s", wp_code, e
        )
        return []
    if data is None:
        return []
    return _map_cycle_recon_findings(data)


# ---------------------------------------------------------------------------
# 统一分发器（复核端点唯一入口）
# ---------------------------------------------------------------------------


async def build_review_reconciliation_context(wp_id: str, wp_code: str | None) -> str:
    """复核勾稽上下文统一入口：D2 走专用富勾稽，K/N 走通用勾稽，其余返回空串。

    单底稿复核（review_prompt）与批量复核（batch_review_service）共用此入口，
    集中「按循环选择勾稽构建器」逻辑，避免两处各自硬编码 D2 判断。
    """
    code = (wp_code or "").upper()
    try:
        if code.startswith("D2"):
            from app.services.d2_review_context import build_d2_reconciliation_context

            return await build_d2_reconciliation_context(str(wp_id))
        return await build_cycle_reconciliation_context(str(wp_id), code)
    except Exception as e:  # noqa: BLE001 — fail-open，绝不阻断复核
        logger.warning("build_review_reconciliation_context failed (%s): %s", wp_code, e)
        return ""


def append_reconciliation_to_user_prompt(user_prompt: str, recon_context: str) -> str:
    """将勾稽上下文追加到 user prompt（与 d2_review_context 同签名，供统一调用）。"""
    if not recon_context or not recon_context.strip():
        return user_prompt
    return f"{user_prompt}\n\n{recon_context}"


__all__ = [
    "CycleReconConfig",
    "build_cycle_reconciliation_context",
    "build_cycle_reconciliation_findings",
    "build_review_reconciliation_context",
    "append_reconciliation_to_user_prompt",
    "extract_cycle_code",
]
