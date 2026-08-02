"""损益类循环 render 装配（K8~K13 六个循环共用）。

六个循环的 render 原本是**六份逐字复制**的代码，每份都带同一个缺陷
（`debit - credit` 恒零 + 父子双计 + 缺点号边界的自造 `_is_leaf`）。
本模块把公共部分收敛，各 `_kX_*.py` 只保留声明（sheets / meta / 循环特有上下文）。

spec: .kiro/specs/k-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 3.1~3.4 / Property 5, 6, 7
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from .k_cycle_specs import KCycleSpec
from .pl_occurrence import build_pl_payload
from .tb_fetch import load_project_context, load_responses_snapshot

logger = logging.getLogger(__name__)

#: 各循环 `checklist_responses` 加载上限（K8/K9 明细多，给足）
_RESPONSE_LIMIT = 5000


async def render_pl_cycle(
    ctx,
    spec: KCycleSpec,
    *,
    component_type: str,
    sheets: list[dict],
    meta: dict | None = None,
    responses_key: str = "responses_snapshot",
    extra_project_context: Callable[[object], Awaitable[dict]] | None = None,
) -> dict:
    """装配损益类循环的 render 返回值。

    Args:
        ctx: `RenderContext`。
        spec: :class:`~.k_cycle_specs.KCycleSpec`（损益类）。
        component_type: 前端组件类型（如 ``k8-selling-expenses``）。
        sheets: 该循环的 sheet 清单（sheet 名须与源 xlsx tab 名逐字一致）。
        meta: 循环特有的 `meta` 段（原样透传）。
        responses_key: checklist 快照的键名 —— K8/K9/K11/K12/K13 用
            ``responses_snapshot``，**K10 用 ``allResponses``**（前端已在读，
            改键名会静默断链）。
        extra_project_context: 可选的额外项目上下文加载器（K10 需要
            `applicable_standard_v2`）。

    Returns:
        render 字典。全程 fail-open。
    """
    label = f"{spec.wp_code} {spec.account_name}"
    responses = await load_responses_snapshot(
        ctx, spec.wp_code, limit=_RESPONSE_LIMIT, label=label
    )

    payload = await build_pl_payload(ctx, spec)

    project_context = await load_project_context(ctx, label=label)
    if extra_project_context is not None:
        try:
            project_context.update(await extra_project_context(ctx))
        except Exception as e:  # noqa: BLE001
            logger.warning("%s: 额外项目上下文加载失败: %s", label, e)

    occ = payload["occurrence"]
    logger.debug(
        "%s: 本期发生额 %.2f（来源 %s，原始符号 %d，叶子合计 %.2f）",
        label,
        occ.report_unadjusted,
        occ.source,
        occ.raw_sign,
        occ.leaf_total,
    )

    result: dict = {
        "component_type": component_type,
        "account_codes": payload["account_codes"],
        "income_statement": True,  # 标识损益类
        responses_key: responses,
        "tb_values": payload["tb_values"],
        "tb_source_codes": payload["tb_source_codes"],
        "adjudication_prefill": payload["adjudication_prefill"],
        "project_context": project_context,
        "prefix": spec.wp_code,
        "sheets": sheets,
    }
    if meta is not None:
        result["meta"] = meta
    return result


__all__ = ["render_pl_cycle"]
