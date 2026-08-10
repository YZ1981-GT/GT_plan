"""H 类审定表「从四表库带入未审数」的分段预填（共享编排件）。

**要补的缺口**

H5~H10 六个循环的 render 各自内联了一段约 25 行的灰度块：按语义槽逐个调
:func:`d_cycle_extraction.prefill.build_d_adjudication_prefill`，产出
``adjudication_segment_prefill``。而 **H1/H2/H3/H4 四个循环完全没有这一段**
（实测计数 0）—— 恰是 H 类数据量最大的四个（固定资产 / 在建工程 /
投资性房地产 / 工程物资），四表入库后审定表拿不到任何种子值。

**为什么抽共享件而不是复制第五、六、七、八份**

六份内联块逐字雷同（只有 `mode` 与 slot 前缀表不同），再抄四份 =
十份副本各自漂移。已实证的漂移代价：`report_formula_service` 的两条写入路径
（memory §踩坑铁律「未完成的重构」）。

**三条口径约定**

1. **逐槽逐码分段**，不做跨槽预聚合 —— 审计师可改归属，预聚合是有损表示
   （E1 已实测过这个坑）。
2. **槽 ``found=False`` 不产出段**（宁缺勿造）。全槽皆空时返回 ``None``，
   调用方据此**不写** ``adjudication_segment_prefill`` 键 ——「键不存在」
   与「键存在但 items 为空」对前端是两种语义。
3. **单槽超时 + 整体 fail-open**：任一槽取数超时/异常只丢该槽，不阻断 render。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 4.1~4.6 / Property 7~8
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal, Mapping

logger = logging.getLogger(__name__)

#: 单槽取数超时（秒）—— 与 H5~H10 既有内联块逐字一致，不得放宽
SLOT_TIMEOUT_SECONDS = 5.0

PrefillMode = Literal["balance", "occurrence"]


async def build_h_segment_prefill(
    ctx: Any,
    accounts: Any,
    slot_key_prefix: Mapping[str, str],
    *,
    mode: PrefillMode = "balance",
    cycle: str = "",
    timeout: float = SLOT_TIMEOUT_SECONDS,
) -> dict | None:
    """按语义槽逐码构造 ``adjudication_segment_prefill``。

    Args:
        ctx: `RenderContext`（含 db / project_id / year）。
        accounts: :func:`resolve_semantic_accounts` 的返回值（有 ``.slots``）。
        slot_key_prefix: ``H{n}_SLOT_KEY_PREFIX`` —— **只用它的键做遍历顺序**，
            值（前端 `tb_values` 键前缀）在本函数里不参与计算。
        mode: ``balance``（余额类）/ ``occurrence``（损益类发生额）。
        cycle: 循环号，仅用于日志。

    Returns:
        ``{"segments": [...], "enabled": True}``；**全槽皆空返回 ``None``**。

    每段形态::

        {"segment": <slot_key>, "account_prefix": <原始码>,
         "mode": <mode>, "items": [...]}
    """
    # 延迟导入：`d_cycle_extraction.prefill` 会拉起 DB 相关依赖，
    # 模块级导入会让本共享件在纯函数测试里也必须连库。
    from app.services.d_cycle_extraction.prefill import build_d_adjudication_prefill

    segments: list[dict] = []
    slots = getattr(accounts, "slots", None) or {}

    for slot_key in slot_key_prefix:
        slot = slots.get(slot_key)
        if not slot or not getattr(slot, "found", False):
            continue
        for code in getattr(slot, "codes", ()) or ():
            if not code:
                continue
            try:
                items = await asyncio.wait_for(
                    build_d_adjudication_prefill(
                        ctx, account_prefix=code, mode=mode
                    ),
                    timeout=timeout,
                )
            except Exception as e:  # noqa: BLE001 — 单槽失败不拖垮整个 render
                logger.warning(
                    "H 类审定表预填: %s 槽 %s 码 %s 取数失败: %s",
                    cycle or "?",
                    slot_key,
                    code,
                    e,
                )
                continue
            if items:
                segments.append(
                    {
                        "segment": slot_key,
                        "account_prefix": code,
                        "mode": mode,
                        "items": items,
                    }
                )

    if not segments:
        # 🔴 返 None 而非 {"segments": [], "enabled": True}：
        # 调用方据此不写该键，前端才能区分「本项目无此科目」与「取到空」。
        return None
    return {"segments": segments, "enabled": True}


async def attach_h_segment_prefill(
    ctx: Any,
    payload: dict,
    *,
    cycle: str,
    accounts: Any,
    slot_key_prefix: Mapping[str, str],
    mode: PrefillMode = "balance",
) -> bool:
    """把分段预填 **additive** 挂进 payload；无数据时一个键都不加。

    🔴 **除 ctx / payload 外一律关键字参数**（2026-08-06 定案）。首版签名是
    ``(payload, ctx, accounts, slot_key_prefix, *, cycle)`` 而 ``build_h_segment_prefill``
    是 ``(ctx, accounts, ...)`` —— 两者 ctx 位置相反，四个调用点**全部传错**：
    H1/H4 传 5 个位置参数（`TypeError: too many positional arguments`）、
    H2/H3 把 ctx 传进 payload 位（`payload.__setitem__` 打在 ctx 上）。
    两种错法都被 render 层 fail-open 吞成 WARNING，四层验证全绿。
    全关键字化后传错即 TypeError，不再有「顺序颠倒仍能绑定」的静默失效面。

    Returns:
        是否真的挂上了（供调用方决定要不要设 ``hi_extraction_enabled``）。
    """
    prefill = await build_h_segment_prefill(
        ctx, accounts, slot_key_prefix, mode=mode, cycle=cycle
    )
    if not prefill:
        return False
    payload["adjudication_segment_prefill"] = prefill
    payload["hi_extraction_enabled"] = True
    return True


__all__ = [
    "SLOT_TIMEOUT_SECONDS",
    "PrefillMode",
    "build_h_segment_prefill",
    "attach_h_segment_prefill",
]
