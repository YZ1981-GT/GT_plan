"""公式推送三态判定（纯函数，无 DB / IO）。

spec: chain-closure-phase2-formula-push-engine · design §五 · 需求 3.1~3.4

三类写入策略：

* ``system``   —— 系统值（试算平衡表数、大厅已确认调整），只由引擎写，总是跟随公式值。
* ``derived``  —— 派生值（汇总键、审定合计、语义槽），只由引擎写，总是跟随公式值。
* ``editable`` —— 用户也能改的值（四表种子明细行、附注数值），按三态判定：
  用户改过的不覆盖（manual）、锁定的不覆盖（locked）、首次遇到来源不明且与公式值
  不等的不静默覆盖（pending_confirm），其余跟随公式值（auto）。

判定表（顺序即优先级，与 design §五 逐行对应）：

==========  ====================================  ============  ===============
策略         条件                                   动作            新状态
==========  ====================================  ============  ===============
system/der  当前 = 公式值（含两者皆空）               unchanged      auto
system/der  当前 ≠ 公式值（公式值为空 ⇒ 写空）         write          auto
editable    状态 = locked 或目标自身模式 = locked      keep_locked    locked
editable    目标自身模式 = manual                   keep_manual    manual
editable    当前 = 公式值                           unchanged      auto
editable    当前为空                                write          auto
editable    有上次推送值且 当前 = 上次推送值          write          auto
editable    有上次推送值且 当前 ≠ 上次推送值          keep_manual    manual
editable    无上次推送值（首次）且 当前 ≠ 公式值      keep_pending   pending_confirm
==========  ====================================  ============  ===============

``unchanged`` 也把「上次推送值」记为公式值（``record_pushed=True``）：当前值已与公式值
一致，等同于刚推送过；否则公式后续变化时，旧的上次推送值会把这个一致的值误判成人工改动。
``keep_*`` 一律不动上次推送值。

「目标自身模式」由调用方从目标载荷折算：附注整节 ``_manual_override=True`` 或单元格
``_cell_modes[col]='locked'`` → ``locked``；单元格 ``_cell_modes[col]='manual'`` → ``manual``。

数值比较容差 0.005，与前端 ``e1AdjudicationPrefill.TOLERANCE`` 同口径
（前端判冲突 = ``abs(差) > 0.005``，故相等 = ``abs(差) <= 0.005``）；
「空」= ``None`` 或只含空白的字符串，与前端 ``isBlank`` 同口径（``0`` 不是空）。
非数值按全等比较。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.models.formula_push_models import PUSH_STATES

#: 写入策略
POLICIES: tuple[str, ...] = ("system", "derived", "editable")
#: 目标状态（与 V169 CHECK、ORM 同源）
STATES: tuple[str, ...] = PUSH_STATES
#: 判定动作
ACTIONS: tuple[str, ...] = ("unchanged", "write", "keep_locked", "keep_manual", "keep_pending")
#: 目标自身携带的外部模式（附注 ``_cell_modes`` / ``_manual_override`` 折算而来）
EXTERNAL_MODES: tuple[str | None, ...] = (None, "manual", "locked")
#: 用户动作
USER_ACTIONS: tuple[str, ...] = ("adopt", "lock", "unlock")
#: 数值比较容差（元）
TOLERANCE = 0.005

# 与 JS ``Number(str)`` 的十进制子集一致：拒绝 Python ``float`` 额外接受的
# ``1_000`` / ``inf`` / ``nan`` 等写法，避免两侧对「是不是数」判断不一。
_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


@dataclass(frozen=True)
class Decision:
    """一次判定的结果。"""

    action: str
    state: str
    #: 判定时当前值与公式值是否不等（面板「差异」）
    differs: bool
    #: 是否把 ``last_pushed_value`` 更新为本次公式值
    record_pushed: bool

    @property
    def writes(self) -> bool:
        return self.action == "write"

    @property
    def kept(self) -> bool:
        return self.action.startswith("keep_")


class PolicyError(ValueError):
    """判定入参不合法（调用方编程错误，不是数据问题）。"""


def is_blank(value: Any) -> bool:
    """``None`` 或只含空白的字符串。``0`` / ``"0"`` 不是空。"""
    return value is None or (isinstance(value, str) and value.strip() == "")


def as_number(value: Any) -> float | None:
    """能按数值比较则返回 float，否则 None（``bool`` 不算数值）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip()
        if not _NUMERIC_RE.match(text):
            return None
        number = float(text)
        return number if math.isfinite(number) else None
    return None


def values_equal(a: Any, b: Any) -> bool:
    """容差相等：两空相等；一空一非空不等；两数值差 ≤ 0.005 相等；其余全等。"""
    a_blank, b_blank = is_blank(a), is_blank(b)
    if a_blank or b_blank:
        return a_blank and b_blank
    na, nb = as_number(a), as_number(b)
    if na is not None and nb is not None:
        return abs(na - nb) <= TOLERANCE
    # 同类型才比：Python 里 ``True == 1``，不加类型约束会把布尔与数值判成相等
    return type(a) is type(b) and a == b


def decide(
    policy: str,
    *,
    formula_value: Any,
    current_value: Any,
    last_pushed_value: Any = None,
    prior_state: str | None = None,
    external_mode: str | None = None,
) -> Decision:
    """按判定表给出动作与新状态。

    :param policy: ``system`` / ``derived`` / ``editable``
    :param formula_value: 本次公式值。
        ``system`` / ``derived`` 可为空，表示「目标应为空」（如语义槽三值全 0 保持空白）：
        当前非空则写空、当前已空则不变。
        ``editable`` **不得为空** —— 来源缺失（如无四表数据）由调用方先判定并跳过，
        免得「无来源」被当成「公式值为空」去清空用户可编辑的目标。
    :param current_value: 目标当前值（``None`` = 目标无值）
    :param last_pushed_value: 引擎上次推送值（``None`` = 从未推送）
    :param prior_state: ``formula_push_state.state``（``None`` = 无状态行）
    :param external_mode: 目标自身的模式（附注单元格 ``manual`` / ``locked``）
    """
    if policy not in POLICIES:
        raise PolicyError(f"未知写入策略: {policy!r}（可选 {POLICIES}）")
    if prior_state is not None and prior_state not in STATES:
        raise PolicyError(f"未知目标状态: {prior_state!r}（可选 {STATES}）")
    if external_mode not in EXTERNAL_MODES:
        raise PolicyError(f"未知外部模式: {external_mode!r}（可选 {EXTERNAL_MODES}）")
    if policy == "editable" and is_blank(formula_value):
        raise PolicyError("可编辑目标的公式值为空：来源缺失须由调用方跳过，不得交给三态判定")

    equal = values_equal(current_value, formula_value)

    if policy in ("system", "derived"):
        if equal:
            return Decision("unchanged", "auto", differs=False, record_pushed=True)
        return Decision("write", "auto", differs=True, record_pushed=True)

    # ── editable ──
    if prior_state == "locked" or external_mode == "locked":
        return Decision("keep_locked", "locked", differs=not equal, record_pushed=False)
    if external_mode == "manual":
        return Decision("keep_manual", "manual", differs=not equal, record_pushed=False)
    if equal:
        return Decision("unchanged", "auto", differs=False, record_pushed=True)
    if is_blank(current_value):
        return Decision("write", "auto", differs=True, record_pushed=True)
    if last_pushed_value is not None:
        if values_equal(current_value, last_pushed_value):
            return Decision("write", "auto", differs=True, record_pushed=True)
        return Decision("keep_manual", "manual", differs=True, record_pushed=False)
    return Decision("keep_pending", "pending_confirm", differs=True, record_pushed=False)


def apply_user_action(action: str, *, policy: str, state: str) -> str:
    """用户在公式管理面板的操作 → 新状态。

    * ``adopt``  采用公式值：调用方以本次**重新算出**的公式值写入目标并记为上次推送值 → ``auto``
      （不用状态表里的 ``last_formula_value`` —— 它是上次运行的值，四表 / 试算表变过就已过时）
    * ``lock``   锁定：只对 ``editable`` 目标有意义 → ``locked``
    * ``unlock`` 解锁：``locked`` → ``pending_confirm``（下次推送重新判定，不直接覆盖）

    系统值 / 派生值只由引擎写，锁定它们会让下游永远拿不到新值，故拒绝。
    """
    if action not in USER_ACTIONS:
        raise PolicyError(f"未知操作: {action!r}（可选 {USER_ACTIONS}）")
    if policy not in POLICIES:
        raise PolicyError(f"未知写入策略: {policy!r}（可选 {POLICIES}）")
    if state not in STATES:
        raise PolicyError(f"未知目标状态: {state!r}（可选 {STATES}）")
    if action == "adopt":
        return "auto"
    if policy != "editable":
        raise PolicyError("系统值 / 派生值只由引擎维护，不能锁定或解锁")
    if action == "lock":
        return "locked"
    if state != "locked":
        raise PolicyError(f"只有已锁定的目标可以解锁（当前状态 {state}）")
    return "pending_confirm"
