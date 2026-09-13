# -*- coding: utf-8 -*-
"""D4-1 审定数 TB 发布决策（独立人工动作 + 差异阈值二次确认 + 切模式不触发）。

Task 4.2 / Requirements 2.4, 1.5, 2.2：

> 将确认审定做成独立人工 TB 发布动作，读取 D4-1 快照，差异超过阈值二次确认；
> 切模式不得触发。

═══ 为什么是纯决策函数（单一真源）═══

TB 发布是「谁能触发、何时需要二次确认、发布来源取哪」的**判据**，前端确认弹窗门控
与后端发布守卫必须用同一套判据，否则两侧口径漂移（前端放行、后端拒绝或反之）。故这里
把判据收敛为纯函数 :func:`decide_d4_1_tb_publish`，不做实际 UPDATE（真实回写走平台标准
端点 `PUT /api/projects/{pid}/trial-balance/writeback`，带数据集/口径/审计留痕）。

═══ 判据（逐条对齐 Req）═══

- **独立人工动作（Req 1.5 / 2.4）**：只有 ``trigger == 'manual_confirm'`` 才允许发布；
  ``trigger == 'mode_switch'``（HTML/OO 切换）恒 **不发布**，返回 ``blocked_mode_switch``。
- **发布来源是 D4-1 快照（Req 2.2 / 2.4）**：审定合计取自 D4-1 页面快照
  （``snapshot_audited_total``），**不偷换为 TB**；TB 核对值（``tb_check_value``）仅用于
  差异比较，不作为发布金额。
- **差异阈值二次确认（Req 2.4）**：``|快照审定合计 − TB核对值| > 0.005`` 时必须二次确认；
  未确认（``second_confirmed=False``）→ ``needs_second_confirm``，取消（未确认）不写。
- **只读 fail-closed（Req 2.5）**：``is_readonly=True`` → ``blocked_readonly``，不写。
- **发布双科目（Req 2.4）**：确认通过后独立发布 ``6001`` 主营 + ``6051`` 其他业务收入
  两个科目金额（由调用方从快照拆分传入）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

__all__ = [
    "D4_1_TB_DIFF_THRESHOLD",
    "D4_1_MAIN_ACCOUNT_CODE",
    "D4_1_OTHER_ACCOUNT_CODE",
    "TbPublishTrigger",
    "TbPublishOutcome",
    "TbPublishDecision",
    "decide_d4_1_tb_publish",
]

# 差异阈值：绝对值大于半分即需二次确认（Req 2.4，与前端 disclosureEmptyTable ZERO_EPS 同口径）。
D4_1_TB_DIFF_THRESHOLD = Decimal("0.005")

# 发布双科目（营业收入审定表回写 trial_balance 的两个损益类科目）。
D4_1_MAIN_ACCOUNT_CODE = "6001"   # 主营业务收入
D4_1_OTHER_ACCOUNT_CODE = "6051"  # 其他业务收入

TbPublishTrigger = Literal["manual_confirm", "mode_switch"]
TbPublishOutcome = Literal[
    "publish",              # 允许发布
    "needs_second_confirm",  # 差异超阈值，需二次确认
    "blocked_mode_switch",   # 模式切换触发，恒不发布
    "blocked_readonly",      # 只读，不发布
    "invalid",               # 入参非法（快照缺失/非数值），fail-closed 不发布
]


def _to_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


@dataclass(frozen=True)
class TbPublishDecision:
    """一次 D4-1 TB 发布请求的裁决。"""

    outcome: TbPublishOutcome
    should_publish: bool
    diff: Decimal | None
    needs_confirm: bool
    reason: str
    # 发布金额（仅 outcome=='publish' 时非空）：{科目码: 审定数}
    publish_amounts: dict[str, Decimal] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "shouldPublish": self.should_publish,
            "diff": (str(self.diff) if self.diff is not None else None),
            "needsConfirm": self.needs_confirm,
            "reason": self.reason,
            "publishAmounts": {k: str(v) for k, v in self.publish_amounts.items()},
        }


def decide_d4_1_tb_publish(
    *,
    trigger: TbPublishTrigger,
    snapshot_audited_total: Any,
    tb_check_value: Any,
    main_audited: Any,
    other_audited: Any,
    is_readonly: bool = False,
    second_confirmed: bool = False,
) -> TbPublishDecision:
    """裁决是否发布 D4-1 审定数到 TB（纯函数，不写库）。

    Args:
        trigger: 触发来源。``'mode_switch'`` 恒不发布（Req 1.5）。
        snapshot_audited_total: D4-1 页面快照审定合计（发布来源，不偷换 TB）。
        tb_check_value: TB 核对值（仅供差异比较，不作发布金额）。
        main_audited / other_audited: 快照拆分出的 6001/6051 审定数（发布金额）。
        is_readonly: 只读态 → fail-closed 不发布。
        second_confirmed: 差异超阈值时用户是否已二次确认。

    Returns:
        TbPublishDecision；``should_publish`` 仅在 outcome=='publish' 为 True。
    """
    # 模式切换恒不发布（Req 1.5）——优先于一切，切模式绝不触发 TB。
    if trigger == "mode_switch":
        return TbPublishDecision(
            outcome="blocked_mode_switch",
            should_publish=False,
            diff=None,
            needs_confirm=False,
            reason="模式切换（HTML/OnlyOffice）不发布 TB；发布须由用户明确执行「确认审定」。",
        )

    # 只读 fail-closed（Req 2.5）
    if is_readonly:
        return TbPublishDecision(
            outcome="blocked_readonly",
            should_publish=False,
            diff=None,
            needs_confirm=False,
            reason="当前为只读状态，不可发布审定数到 TB。",
        )

    total = _to_decimal(snapshot_audited_total)
    tb = _to_decimal(tb_check_value)
    main = _to_decimal(main_audited)
    other = _to_decimal(other_audited)

    # 快照/核对值/发布金额任一非法 → fail-closed（不臆测、不发布）
    if total is None or tb is None or main is None or other is None:
        return TbPublishDecision(
            outcome="invalid",
            should_publish=False,
            diff=None,
            needs_confirm=False,
            reason="D4-1 快照审定合计、TB 核对值或发布金额缺失/非数值，拒绝发布（请人工核对）。",
        )

    diff = abs(total - tb)
    needs_confirm = diff > D4_1_TB_DIFF_THRESHOLD

    # 差异超阈值且未二次确认 → 需二次确认（取消即不写）
    if needs_confirm and not second_confirmed:
        return TbPublishDecision(
            outcome="needs_second_confirm",
            should_publish=False,
            diff=diff,
            needs_confirm=True,
            reason=(
                f"D4-1 审定合计（{total}）与 TB 核对值（{tb}）差异 {diff} 超过阈值 "
                f"{D4_1_TB_DIFF_THRESHOLD}，需二次确认后方可发布。"
            ),
        )

    # 通过：发布来源是快照拆分金额（6001/6051），不偷换 TB。
    return TbPublishDecision(
        outcome="publish",
        should_publish=True,
        diff=diff,
        needs_confirm=needs_confirm,
        reason="",
        publish_amounts={
            D4_1_MAIN_ACCOUNT_CODE: main,
            D4_1_OTHER_ACCOUNT_CODE: other,
        },
    )
