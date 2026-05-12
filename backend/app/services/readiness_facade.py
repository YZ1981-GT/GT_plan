"""Readiness 门面共用逻辑 — R1 需求 3

将 ``gate_engine.evaluate()`` 的 ``hit_rules`` 按 ``rule_code`` 映射到
固定的 UI 类目（sign_off 8 项 / export_package 12 项），同时保留
legacy ``checks`` 数组向后兼容前端尚未切换到 ``groups`` 的页面。

本模块**不**直接调用 ``gate_engine``，避免循环导入；调用方传入
``GateEvaluateResult`` 与 UI 已检测到的额外项（如 independence
confirmed、KAM confirmed 等 wizard_state 条目），本门面负责聚合。

输出的统一 schema：

```jsonc
{
  "ready": true,                   // False iff decision == 'block' 或任一类目含 blocking finding
  "groups": [
    {
      "id": "l2_review",
      "name": "所有底稿二级复核通过",
      "status": "pass|warning|blocking|info",
      "findings": [
        {
          "rule_code": "QC-19",
          "error_code": "QC_PROCEDURE_MANDATORY_TRIMMED",
          "severity": "blocking",
          "message": "...",
          "location": {"wp_id": "..."},
          "action_hint": "..."
        }
      ]
    }
  ],
  "gate_eval_id": "uuid-v4",
  "expires_at": "2026-05-05T12:34:56+00:00",
  // --- 以下为 legacy 兼容字段（短期保留，Round 2 及之后可移除） ---
  "ready_to_sign": true,           // SignReadiness 旧字段
  "checks": [
    {"id": "l2_review", "label": "所有底稿二级复核通过", "passed": true, "detail": "全部通过"}
  ],
  "passed_count": 8,
  "total_checks": 8
}
```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Mapping

if TYPE_CHECKING:  # 仅用于类型提示，避免运行时循环导入
    from app.services.gate_engine import GateEvaluateResult, GateRuleHit

_logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 类目定义
# ------------------------------------------------------------------


@dataclass(frozen=True)
class CategoryDef:
    id: str
    label: str


# sign_off: 11 项（与 legacy SignReadinessService.check_sign_readiness 保持 id/label 对齐）
SIGN_OFF_CATEGORIES: tuple[CategoryDef, ...] = (
    CategoryDef("l2_review", "所有底稿二级复核通过"),
    CategoryDef("qc_all_pass", "QC 自检全部通过"),
    CategoryDef("no_open_issues", "无未解决复核意见"),
    CategoryDef("adj_approved", "调整分录全部审批"),
    CategoryDef("misstatement_eval", "未更正错报已评价"),
    CategoryDef("report_generated", "审计报告已生成"),
    CategoryDef("kam_confirmed", "关键审计事项已确认"),
    CategoryDef("independence", "独立性确认"),
    CategoryDef("subsequent_events", "期后事项审阅已完成"),
    CategoryDef("going_concern", "持续经营评价已完成"),
    CategoryDef("mgmt_representation", "管理层声明书已获取"),
)

# export_package: 12 项（与 legacy ArchiveReadinessService.check_readiness 对齐）
EXPORT_PACKAGE_CATEGORIES: tuple[CategoryDef, ...] = (
    CategoryDef("review_complete", "所有底稿复核通过"),
    CategoryDef("qc_passed", "所有底稿 QC 自检通过"),
    CategoryDef("no_open_issues", "无未解决的复核意见"),
    CategoryDef("adj_approved", "调整分录全部审批"),
    CategoryDef("misstatement_evaluated", "未更正错报已评价"),
    CategoryDef("report_generated", "审计报告已生成"),
    CategoryDef("kam_confirmed", "关键审计事项已确认"),
    CategoryDef("independence", "独立性确认已签署"),
    CategoryDef("subsequent_events", "期后事项审阅已完成"),
    CategoryDef("going_concern", "持续经营评价已完成"),
    CategoryDef("mgmt_representation", "管理层声明书已获取"),
    CategoryDef("index_complete", "底稿按索引编号排列"),
)

# 兜底类目：gate 规则 rule_code 不在映射表时归入此类，保证未来新增规则
# 不会在 UI 上消失（需求 3 验收标准 3）。
MISC_CATEGORY = CategoryDef("misc", "其他门禁规则")


# ------------------------------------------------------------------
# rule_code → category_id 映射
# ------------------------------------------------------------------
#
# 当前门禁规则清单（backend/app/services/gate_rules_phase14.py）：
#
#   QC-19 mandatory 程序裁剪       → 底稿质量类，归入 "qc_all_pass"
#   QC-20 conditional 裁剪无证据    → 底稿质量类，归入 "qc_all_pass"
#   QC-21 关键结论缺少证据锚点      → 底稿质量类，归入 "qc_all_pass"
#   QC-22 低置信单点依赖           → 底稿质量类，归入 "qc_all_pass"
#   QC-23 LLM 关键内容未确认        → 底稿质量类，归入 "qc_all_pass"
#   QC-24 LLM 采纳与裁剪冲突        → 底稿质量类，归入 "qc_all_pass"
#   QC-25 正文引用附注版本过期      → 报告/附注类，归入 sign=report_generated / archive=report_generated
#   QC-26 附注关键披露缺来源映射    → 报告/附注类，归入 sign=report_generated / archive=report_generated
#   CONSISTENCY-BLOCK 一致性差异    → 底稿/报告关联，归入 sign=l2_review / archive=review_complete
#   GATE-MISSTATEMENT 错报超重要性  → 错报评价类，归入 sign=misstatement_eval / archive=misstatement_evaluated
#
# 未来新规则（R1 Task 8 的 UnconvertedRejectedAJERule / EventCascadeHealthRule
# 等）应当在此追加；未追加的规则会通过 MISC_CATEGORY 展示。

_SIGN_OFF_RULE_CATEGORY: dict[str, str] = {
    "QC-19": "qc_all_pass",
    "QC-20": "qc_all_pass",
    "QC-21": "qc_all_pass",
    "QC-22": "qc_all_pass",
    "QC-23": "qc_all_pass",
    "QC-24": "qc_all_pass",
    "QC-25": "report_generated",
    "QC-26": "report_generated",
    "CONSISTENCY-BLOCK": "l2_review",
    "GATE-MISSTATEMENT": "misstatement_eval",
    # R1 需求 3 验收 7/8 新增
    "R1-AJE-UNCONVERTED": "misstatement_eval",
    "R1-EVENT-CASCADE": "misc",
    # R1 需求 10：独立性声明完整性
    "R1-INDEPENDENCE": "independence",
    # R6 需求 2：KAM + 独立性确认 GateRule
    "R6-KAM": "kam_confirmed",
    "R6-INDEPENDENCE": "independence",
    # R7 P2：期后事项 / 持续经营 / 管理层声明 GateRule
    "R7-SUBSEQUENT": "subsequent_events",
    "R7-GOING-CONCERN": "going_concern",
    "R7-MGMT-REP": "mgmt_representation",
}

_EXPORT_PACKAGE_RULE_CATEGORY: dict[str, str] = {
    "QC-19": "qc_passed",
    "QC-20": "qc_passed",
    "QC-21": "qc_passed",
    "QC-22": "qc_passed",
    "QC-23": "qc_passed",
    "QC-24": "qc_passed",
    "QC-25": "report_generated",
    "QC-26": "report_generated",
    "CONSISTENCY-BLOCK": "review_complete",
    "GATE-MISSTATEMENT": "misstatement_evaluated",
    # R1 需求 3 验收 8 新增（sign_off + export_package 双注册）
    "R1-EVENT-CASCADE": "misc",
    # R1 需求 10：独立性声明完整性
    "R1-INDEPENDENCE": "independence",
    # R6 需求 2：KAM + 独立性确认 GateRule
    "R6-KAM": "kam_confirmed",
    "R6-INDEPENDENCE": "independence",
    # R7 P2：期后事项 / 持续经营 / 管理层声明 GateRule
    "R7-SUBSEQUENT": "subsequent_events",
    "R7-GOING-CONCERN": "going_concern",
    "R7-MGMT-REP": "mgmt_representation",
}


def _category_id_for(rule_code: str, gate_type: str) -> str:
    table = (
        _SIGN_OFF_RULE_CATEGORY
        if gate_type == "sign_off"
        else _EXPORT_PACKAGE_RULE_CATEGORY
    )
    return table.get(rule_code, MISC_CATEGORY.id)


# ------------------------------------------------------------------
# status/severity 归并
# ------------------------------------------------------------------

_STATUS_ORDER = {"blocking": 3, "warning": 2, "info": 1, "pass": 0}


def _worst_status(findings: list[dict[str, Any]]) -> str:
    """按组内最严重 severity 汇总 status；无 finding 返回 'pass'。"""
    if not findings:
        return "pass"
    worst = "pass"
    for f in findings:
        sev = str(f.get("severity", "info"))
        if _STATUS_ORDER.get(sev, 0) > _STATUS_ORDER.get(worst, 0):
            worst = sev
    return worst


# ------------------------------------------------------------------
# 统一响应构造
# ------------------------------------------------------------------


def _hit_to_finding(hit: "GateRuleHit") -> dict[str, Any]:
    return {
        "rule_code": getattr(hit, "rule_code", ""),
        "error_code": getattr(hit, "error_code", ""),
        "severity": str(getattr(hit, "severity", "info")),
        "message": getattr(hit, "message", ""),
        "location": dict(getattr(hit, "location", {}) or {}),
        "action_hint": getattr(hit, "suggested_action", "") or "",
    }


def build_readiness_response(
    *,
    gate_type: str,
    gate_result: "GateEvaluateResult",
    extra_findings: Mapping[str, list[dict[str, Any]]] | None = None,
    gate_eval_id: str,
    expires_at_iso: str,
) -> dict[str, Any]:
    """根据 gate 评估结果构造统一 readiness 响应。

    Parameters
    ----------
    gate_type : 'sign_off' | 'export_package'
    gate_result : gate_engine.evaluate 的返回值
    extra_findings : 预检阶段计算的非 gate findings（例如独立性/KAM 确认），
        形如 ``{category_id: [finding_dict, ...]}``。每个 finding 至少
        带 ``severity / message``，用于补齐 8/12 项"非 gate 规则可检测"
        的业务信号（gate 还未覆盖时），便于 UI 保持原有体验。
    gate_eval_id : 幂等令牌
    expires_at_iso : ISO-8601 字符串（UTC）
    """
    categories = (
        SIGN_OFF_CATEGORIES if gate_type == "sign_off" else EXPORT_PACKAGE_CATEGORIES
    )

    # 初始化每个类目的 findings 桶
    buckets: dict[str, list[dict[str, Any]]] = {c.id: [] for c in categories}
    buckets[MISC_CATEGORY.id] = []

    # 1) 合并 gate hit_rules
    for hit in getattr(gate_result, "hit_rules", []) or []:
        cat_id = _category_id_for(getattr(hit, "rule_code", ""), gate_type)
        buckets.setdefault(cat_id, []).append(_hit_to_finding(hit))

    # 2) 合并 extra_findings（wizard_state / DB 统计等 gate 未覆盖的信号）
    if extra_findings:
        for cat_id, items in extra_findings.items():
            buckets.setdefault(cat_id, []).extend(items)

    # 3) 构造 groups（固定顺序：8/12 项类目 + misc 兜底）
    groups: list[dict[str, Any]] = []
    for c in categories:
        findings = buckets.get(c.id, [])
        groups.append(
            {
                "id": c.id,
                "name": c.label,
                "status": _worst_status(findings),
                "findings": findings,
            }
        )
    misc_findings = buckets.get(MISC_CATEGORY.id, [])
    if misc_findings:
        groups.append(
            {
                "id": MISC_CATEGORY.id,
                "name": MISC_CATEGORY.label,
                "status": _worst_status(misc_findings),
                "findings": misc_findings,
            }
        )

    # 4) decision 与 ready 的对齐
    #
    # - gate decision == 'block' → ready=False
    # - 任一 group 含 severity='blocking' 的 finding（包括 extra_findings）→ ready=False
    # - decision in ('allow', 'warn') 且无 blocking → ready=True
    #
    # 本轮 warn 不阻断签字/归档（与 GateEngine 同语义，warn 为提示）。
    gate_decision = str(getattr(gate_result, "decision", "allow"))
    has_blocking = any(
        (f.get("severity") == "blocking") for g in groups for f in g["findings"]
    )
    ready = (gate_decision != "block") and (not has_blocking)

    # 5) legacy 兼容字段
    checks = [
        {
            "id": g["id"],
            "label": g["name"],
            "passed": (g["status"] == "pass"),
            "detail": _render_detail(g["findings"]),
        }
        for g in groups
        if g["id"] != MISC_CATEGORY.id  # legacy 前端 8/12 项不含 misc
    ]
    passed_count = sum(1 for c in checks if c["passed"])

    response = {
        "ready": ready,
        "groups": groups,
        "gate_eval_id": gate_eval_id,
        "expires_at": expires_at_iso,
        # legacy 兼容（Round 2 之后若 UI 切换完成可移除）
        "checks": checks,
        "passed_count": passed_count,
        "total_checks": len(checks),
        "gate_decision": gate_decision,
        "gate_trace_id": str(getattr(gate_result, "trace_id", "")),
    }
    # SignReadiness 旧字段名
    if gate_type == "sign_off":
        response["ready_to_sign"] = ready
    return response


def _render_detail(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "全部通过"
    parts = []
    for f in findings[:3]:
        sev = f.get("severity", "")
        msg = f.get("message", "")
        parts.append(f"[{sev}] {msg}" if sev else msg)
    extra = len(findings) - 3
    if extra > 0:
        parts.append(f"…还有 {extra} 项")
    return "；".join(parts)


__all__ = [
    "SIGN_OFF_CATEGORIES",
    "EXPORT_PACKAGE_CATEGORIES",
    "MISC_CATEGORY",
    "build_readiness_response",
]
