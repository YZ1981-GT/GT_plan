"""跨科目校验门禁规则

Sprint 4 Task 4.8: 集成到签字前门禁 gate_engine（CROSS_CHECK_PASSED 规则）
S2 ADR-CCN-04: XR 进签字判据 — 年度单一来源 + 结果转五态 + observe/enforce
"""

import logging
import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase14_enums import GateType, GateSeverity
from app.services.gate_engine import GateRule, GateRuleHit, rule_registry

logger = logging.getLogger(__name__)

# observe/enforce 模式：observe 下 blocking 降为 warning，enforce 下保留 blocking
_ENFORCEMENT_MODE = os.environ.get("CONSISTENCY_GATE_ENFORCEMENT", "observe")


class CrossCheckPassedRule(GateRule):
    """跨科目校验通过规则

    签字前门禁：检查所有跨科目校验规则结果，按五态转换并汇总。
    ADR-CCN-04: 年度取 fetch_project_audit_year，skip→not_executed，
    observe/enforce 决定返回 severity。
    """

    rule_code = "R4-CROSS-CHECK"
    error_code = "CROSS_CHECK_FAILED"
    severity = "blocking"

    async def check(self, db: AsyncSession, context: dict) -> Optional[GateRuleHit]:
        """检查跨科目校验是否全部通过"""
        from app.services.wp_cross_check_service import CrossCheckService
        from app.services.project_audit_year import fetch_project_audit_year

        project_id = context.get("project_id")
        if not project_id:
            return None

        # ── 年度单一来源（ADR-CCN-04）───────────────────────────
        year = context.get("year") or await fetch_project_audit_year(db, project_id)
        if not year:
            return self.not_executed("项目未设置审计年度，未运行跨科目校验")

        # ── 执行全量校验 ────────────────────────────────────────
        svc = CrossCheckService(db)
        results = await svc.execute(project_id, year, trigger="sign_off")

        # ── 结果转五态（ADR-CCN-01）────────────────────────────
        failed_items: list[dict] = []
        not_executed_items: list[dict] = []
        error_items: list[dict] = []
        all_passed = True

        for r in results:
            status = r.get("status", "")
            rule_id = r.get("rule_id", "")
            description = r.get("description", "")
            details = r.get("details") or {}

            if status == "pass":
                continue
            elif status == "fail":
                all_passed = False
                # 查规则定义获取 severity
                rule_severity = _get_rule_severity(rule_id)
                failed_items.append({
                    "rule_id": rule_id,
                    "description": description,
                    "severity": rule_severity,
                    "left": r.get("left_amount"),
                    "right": r.get("right_amount"),
                    "diff": r.get("difference"),
                })
            elif status in ("skip", "not_executed"):
                all_passed = False
                reason = details.get("reason", "数据不足或规则未实现")
                not_executed_items.append({
                    "rule_id": rule_id,
                    "description": description,
                    "reason": reason,
                })
            elif status == "error":
                all_passed = False
                error_msg = details.get("error", "未知错误")
                error_items.append({
                    "rule_id": rule_id,
                    "description": description,
                    "error": error_msg,
                })
            else:
                # 未知状态视为 error
                all_passed = False
                error_items.append({
                    "rule_id": rule_id,
                    "description": description,
                    "error": f"未知结果状态: {status}",
                })

        # ── 全部通过 → 放行 ─────────────────────────────────
        if all_passed:
            return None

        # ── 汇总 severity ────────────────────────────────────
        has_blocking_fail = any(
            item.get("severity") == "blocking" for item in failed_items
        )

        # observe 下一律 warning；enforce 下有 blocking 级 failed 才 blocking
        enforcement = os.environ.get("CONSISTENCY_GATE_ENFORCEMENT", "observe")
        if enforcement == "enforce" and (
            has_blocking_fail or not_executed_items or error_items
        ):
            hit_severity = GateSeverity.blocking
        else:
            hit_severity = GateSeverity.warning

        # ── 拼消息（最多列 3 条问题）──────────────────────────
        problem_lines: list[str] = []
        for item in failed_items[:3]:
            problem_lines.append(
                f"{item['rule_id']}({item['description']}): "
                f"差额 {item.get('diff', '?')}"
            )
        for item in not_executed_items[:max(0, 3 - len(problem_lines))]:
            problem_lines.append(
                f"{item['rule_id']}({item['description']}): "
                f"未执行 - {item.get('reason', '')}"
            )
        for item in error_items[:max(0, 3 - len(problem_lines))]:
            problem_lines.append(
                f"{item['rule_id']}({item['description']}): "
                f"异常 - {item.get('error', '')}"
            )

        total_problems = (
            len(failed_items) + len(not_executed_items) + len(error_items)
        )
        extra_count = total_problems - len(problem_lines)
        if extra_count > 0:
            problem_lines.append(f"还有 {extra_count} 条")

        message = "跨科目校验未全部通过：" + "；".join(problem_lines)

        # ── ADR-CCN-06 指纹对齐：location 包含 diff/left/right ───
        # _compute_fingerprint_for_hit 提取 location 中全部数值型字段作
        # key_numbers，router 端的 body.key_numbers 需要传递同一组数值。
        # 如果 location 只有 counts 而 client 传 diff/left/right，两侧
        # key sets 不同 → 指纹永远不匹配 → blocking→warning 降级死代码。
        _sum_diff = sum(abs(item.get("diff") or 0) for item in failed_items)
        _sum_left = sum(abs(item.get("left") or 0) for item in failed_items)
        _sum_right = sum(abs(item.get("right") or 0) for item in failed_items)

        return GateRuleHit(
            rule_code=self.rule_code,
            error_code=self.error_code,
            severity=hit_severity,
            message=message,
            location={
                "project_id": str(project_id),
                "year": year,
                "failed_count": len(failed_items),
                "not_executed_count": len(not_executed_items),
                "error_count": len(error_items),
                "diff": round(float(_sum_diff), 2),
                "left": round(float(_sum_left), 2),
                "right": round(float(_sum_right), 2),
            },
            suggested_action="执行跨科目校验并修正差异，或确认已知偏差",
        )


def _get_rule_severity(rule_id: str) -> str:
    """从规则库获取规则的 severity，默认 warning"""
    from app.services.wp_cross_check_service import load_rules

    for rule in load_rules():
        if rule.get("rule_id") == rule_id:
            return rule.get("severity", "warning")
    return "warning"


def register_cross_check_rules():
    """注册跨科目校验规则到 sign_off 门禁"""
    rule_registry.register_all([GateType.sign_off], CrossCheckPassedRule())
    logger.info("[GATE] Cross-check rule R4-CROSS-CHECK registered to sign_off")
