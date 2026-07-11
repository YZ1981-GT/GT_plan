"""ACNR-backed 公式引用校验共享 helper（acnr-consumer-wiring Req 9）。

三个公式校验消费点（WpFormulaService.save / routers.report_config /
routers.wp_user_formulas）统一走此 helper，使「引用是否存在」由 ACNR
``full_resolve`` 这一 canonical resolver 决定，替代直接调用 legacy
``address_registry.validate_formula_refs``。

核心语义（strangler-fig + fail-open）：
- **WP 域引用**（``WP(...)``）逐引用调 ``full_resolve``；``found=false`` →
  判定为悬空引用（issue）。这是 fail-closed，且仅在 WP 域「确定性未命中」时触发
  （Req 9.4）。
- **非 WP 域引用**（TB/SUM_TB/ROW/SUM_ROW/REPORT/NOTE/AUX/PREV）继续走 legacy
  ``address_registry.validate_formula_refs`` 校验（Req 9.4：这些域的 catalog
  覆盖尚未确认，保持旧路径）。
- **fail-open**：``full_resolve`` 抛异常（resolver 基础设施不可用）→ **整体回退**
  legacy ``validate_formula_refs`` + ``logger.warning``，绝不因 resolver 故障产生
  虚假 ``not_found`` 而阻断保存（Req 9.3）。

issue dict schema 与 legacy ``validate_formula_refs`` 保持一致
（``ref`` / ``uri`` / ``status='not_found'`` / ``message``），额外附 ``reason``
字段，确保 router 转 HTTP 422 的契约不变。

Requirements: 9.1, 9.3, 9.4
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.address_registry import (
    address_registry,
    formula_ref_to_uri,
)
from app.services.formula_grammar import RELAXED_FORMULA_PATTERNS

logger = logging.getLogger(__name__)

# WP 域公式函数（走 ACNR full_resolve）。其余函数名走 legacy。
_WP_FUNC = "WP"
# 非 WP 域函数名集合（走 legacy validate_formula_refs）。
_NON_WP_FUNCS = tuple(name for name in RELAXED_FORMULA_PATTERNS if name != _WP_FUNC)

_WP_PATTERN = RELAXED_FORMULA_PATTERNS[_WP_FUNC]


def _is_wp_ref(ref_text: str) -> bool:
    """判断某 ref_text 是否为 WP 域引用（``WP(...)``）。"""
    return ref_text.strip().upper().startswith("WP(")


def _expression_has_non_wp_ref(expression: str) -> bool:
    """expression 中是否出现任一非 WP 域函数 token（决定是否需要 legacy 校验）。"""
    return any(f"{name}(" in expression for name in _NON_WP_FUNCS)


def _make_wp_issue(ref_text: str) -> dict[str, Any]:
    """构造 WP 域 not_found issue，schema 兼容 legacy validate_formula_refs。"""
    uri = formula_ref_to_uri(ref_text)
    return {
        "ref": ref_text,
        "uri": uri,
        "status": "not_found",
        "reason": "not_found",
        "message": f"引用地址 {uri or ref_text} 在当前项目中不存在",
    }


async def validate_refs_via_acnr(
    db: AsyncSession,
    project_id: str,
    year: int,
    expression: str,
    template_type: str = "soe",
) -> list[dict]:
    """ACNR-backed 公式引用校验（Req 9 共享 helper）。

    拆分 expression 中的 WP 域引用与非 WP 域引用：
    - WP 域逐引用调 ``full_resolve``，``found=false`` → not_found issue。
    - 非 WP 域仍走 legacy ``validate_formula_refs``，合并其 issues。

    fail-open：任一 ``full_resolve`` 抛异常 → 整体回退 legacy 校验 + warning。

    Args:
        db: AsyncSession。
        project_id: 项目 id（str/UUID 均可，内部转 str）。
        year: 年度（传给 legacy 校验）。
        expression: 公式表达式。
        template_type: 模板类型，默认 'soe'（传给 legacy 校验）。

    Returns:
        issue dict 列表（空列表表示校验通过）。issue schema：
        ``{ref, uri, status:'not_found', reason:'not_found', message}``。

    Requirements: 9.1, 9.3, 9.4
    """
    pid = str(project_id)

    # 延迟导入避免与 resolver 的循环依赖，且便于测试打桩。
    from app.services.acnr.resolver import full_resolve

    # ── WP 域引用：逐引用 full_resolve ──────────────────────────────
    wp_refs = [m.group(0) for m in _WP_PATTERN.finditer(expression)]
    wp_issues: list[dict] = []
    try:
        for ref_text in wp_refs:
            result = await full_resolve(
                formula_ref=ref_text,
                project_id=pid,
                db=db,
            )
            if not result.found:
                wp_issues.append(_make_wp_issue(ref_text))
    except Exception as exc:  # noqa: BLE001 — fail-open：resolver 故障不阻断保存
        logger.warning(
            "ACNR full_resolve 校验失败，回退 legacy validate_formula_refs "
            "(project=%s): %s",
            pid,
            exc,
        )
        return await address_registry.validate_formula_refs(
            db, pid, year, expression, template_type
        )

    # ── 非 WP 域引用：走 legacy 校验并合并（过滤掉 WP 域 issue 避免重复）──
    non_wp_issues: list[dict] = []
    if _expression_has_non_wp_ref(expression):
        legacy_issues = await address_registry.validate_formula_refs(
            db, pid, year, expression, template_type
        )
        non_wp_issues = [
            issue
            for issue in legacy_issues
            if not _is_wp_ref(str(issue.get("ref", "")))
        ]

    return wp_issues + non_wp_issues
