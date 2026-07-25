"""D-cycle Tier A render transient seed 共享助手（DRY，Wave 3/4）.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/  决策1/3 / R3（Property 6/7/11/13）

**「编辑公式即生效」成立的主机制**：D-cycle render（主灰度开关开）用 `resolve_effective`
的当前有效 Tier A 公式（预设 ∪ 用户 wp_formula，读时收敛）逐条 `evaluate_wp_formula_expression`
求值（经 `get_active_filter`，与 GET value / 保存同数据集版本口径 / Property 4），结果 seed
到 TB 核对行锚点（如 `D6-1-tb-amount`/`D2-adj-tb-amount`/`D4-1-adj-tb-6001` 等），
**只进 render 返回 payload、不落 checklist_responses/DB**（Property 13，对齐 D6 Tier B
`adjudication_prefill`）。前端 seed 优先级 = 持久层非空值 > responses_snapshot seed >
project_context.tb_amount fallback。

从 D6 `_d6_contract_assets.py::_seed_tier_a_reconciliation`（Task 4.1）提取为通用助手，
供 D1/D2/D3/D4/D5/D7 及 D6 复用（Task 4.2），避免 6× 复制。D4 双标量（6001/6051）由
`resolve_effective` 返回两条绑定，本助手的锚点遍历天然覆盖，无需特判。

**依赖注入（`resolve_effective` / `evaluate_wp_formula_expression`）**：各 render 策略模块
在其自身作用域 import 这两个函数并传入，使测试可 monkeypatch **调用方模块**（如
`d6.resolve_effective`）——与 Task 4.1 D6 现有测试范式一致，重构 D6 后其测试无需改动。

规则（逐条与 D6 原实现等价）：
  * **手工优先**（R3.2 / Property 6）：锚点在 `responses_snapshot`（持久层回显）已有非空
    seed 字段值 → 跳过（不覆盖真人工编辑；因 seed 不落库，仅真人工编辑会持久）。
  * **disabled 跳过**（R3.3）：source=disabled 的绑定不 seed 该锚点。
  * **写对字段**（R3.7 / 决策2）：写入 `_seed_fields.map` 登记字段（D1-D7 均 remark），
    未登记该锚点 seed 字段 → 跳过（只 seed 已核实读取字段的 TB 核对行，防错列 round-trip 断裂）。
  * **fail-open**（R3.4 / Property 11）：resolve 失败 / year 缺失 / 求值异常 / 有 eval_errors →
    跳过该锚点 seed（静默沿用 project_context.tb_amount，logger.warning 非用户通知），
    始终不阻断 render。
  * **默认等价**（R3.6 / Property 7）：未编辑的默认预设 `TB(code,'期末余额')` 求值与现
    project_context.tb_amount 口径一致。
"""

from __future__ import annotations

import logging

from app.services.d_cycle_extraction.anchor_registry import seed_field
from app.services.d_cycle_extraction.presets import SOURCE_DISABLED
from app.services.wp_parsed_data_service import format_cell_display_value

logger = logging.getLogger(__name__)


async def seed_tier_a_reconciliation(
    ctx,
    wp_code: str,
    responses_snapshot: dict,
    *,
    resolve_effective,
    evaluate_wp_formula_expression,
) -> None:
    """用有效 Tier A 公式求值 **transient seed** TB 核对行锚点进 responses_snapshot（原地）.

    Args:
        ctx: RenderContext（提供 db / wp_id / project_id / year）。
        wp_code: 循环 base wp_code（如 "D6"/"D2"/"D4"）——用于 resolve_effective 与
            seed_field 登记查询。
        responses_snapshot: 从 checklist_responses 加载的持久层回显 dict（原地修改）。
        resolve_effective: 读时收敛函数（由调用方 render 模块注入，供测试 monkeypatch）。
        evaluate_wp_formula_expression: 公式求值函数（同上）。

    全程 fail-open：任一环异常不抛、不阻断 render（外层调用方另有兜底 try/except）。
    """
    try:
        bindings = await resolve_effective(ctx.db, ctx.wp_id, wp_code, ctx.project_id)
    except Exception as e:  # noqa: BLE001 — 收敛读取失败一律 fail-open
        logger.warning(
            "%s render: resolve_effective 失败（fail-open，跳过 Tier A seed）: %s",
            wp_code, e,
        )
        return

    year = ctx.year
    for binding in bindings:
        anchor = (binding.get("anchor") or "").strip()
        if not anchor:
            continue
        # disabled 跳过（R3.3）
        if binding.get("source") == SOURCE_DISABLED:
            continue
        # 写对字段：仅 seed `_seed_fields.map` 登记的 TB 核对行锚点（决策2 / R3.7）
        field = seed_field(wp_code, anchor)
        if not field:
            continue
        # 手工优先：持久层已有非空值 → 不覆盖（R3.2 / Property 6）
        existing = responses_snapshot.get(anchor)
        if isinstance(existing, dict) and (existing.get(field) or "").strip():
            continue
        expression = (binding.get("expression") or "").strip()
        if not expression:
            continue
        # year 缺失 → fail-open 跳过（沿用 project_context.tb_amount）
        if year is None:
            logger.warning(
                "%s render: Tier A seed 缺 year，跳过锚点 %s（fail-open）", wp_code, anchor
            )
            continue
        try:
            value, errs = await evaluate_wp_formula_expression(
                ctx.db,
                project_id=ctx.project_id,
                year=int(year),
                expression=expression,
            )
        except Exception as e:  # noqa: BLE001 — 单锚点求值失败 fail-open
            logger.warning(
                "%s render: Tier A seed 求值失败 anchor=%s: %s", wp_code, anchor, e
            )
            continue
        if errs:
            # 有 eval_errors（悬空引用等）→ 不 seed（不静默落错误/0，R3.4）
            logger.warning(
                "%s render: Tier A seed 有 eval_errors anchor=%s errs=%s（跳过 seed）",
                wp_code, anchor, errs,
            )
            continue
        formatted = format_cell_display_value(value)
        remark_str = "" if formatted is None else str(formatted)
        # transient seed（不落库）：写入前端读取字段，保留另一字段既有值
        merged = dict(existing) if isinstance(existing, dict) else {}
        merged.setdefault("conclusion", "")
        merged.setdefault("remark", "")
        merged[field] = remark_str
        responses_snapshot[anchor] = merged
