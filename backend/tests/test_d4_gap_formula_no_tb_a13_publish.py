# -*- coding: utf-8 -*-
"""C3 linkage 守卫：公式同步/解析**绝不**发布 TB / A13（Req 2.4 / 3.2）。

用户/spec 铁律：*公式同步不是 TB/A13；TB/A13 需显式确认*。这条是**否定式承诺**，必须
被证明*不可能*，而不是「当前没写」。这里用两道判据落实：

1. **源码面**：formula 路径涉及的模块源码里不得出现 trial_balance 写回 / adjustments /
   A13 misstatement / EventBus publish 的调用形态（字符级，锁死 import/调用点）。
2. **行为面**：跑一次 `apply_batch_mutate`（v2 formula 提交）+ 一次 `resolve_effective_formula`
   （有效公式解析），断言二者的产出里不含任何 TB/A13/publish 副作用信号，且 audit gate
   只记公式动作、不记审定/调整/错报。

变异检验：往 `apply_batch_mutate` 或 `effective_formula` 注入一处
`trial_balance.audited_amount` 写或 `eventBus publish('substantive:adjudicated')`，
判据 1 立刻打红（源码出现禁词），判据 2 的 audit kind 断言也会红。

Spec: d4-adjustment-and-analysis-gap-closure Task 4 / Task 5
Requirements: 2.4, 3.2
"""

from __future__ import annotations

import inspect

from app.services import user_formula_v2
from app.services.formula_management import effective_formula
from app.services.user_formula_v2 import (
    InMemoryAuditGate,
    UserFormulaV2Store,
    apply_batch_mutate,
)
from app.services.formula_management.effective_formula import (
    make_formula_key,
    resolve_effective_formula,
)


# 禁词：一旦公式路径源码里出现这些，说明公式同步偷偷发布了 TB/A13（Req 2.4 违反）。
_FORBIDDEN_IN_FORMULA_PATH = (
    "audited_amount",           # trial_balance 审定回写
    "aje_adjustment",           # trial_balance 调整回写
    "adjustment:created",       # A13 错报联动事件
    "substantive:adjudicated",  # TB 审定发布事件
    "a13:push-misstatement",    # A13 推错报
    "AdjustmentService",        # 集中调整服务
    "trial_balance",            # 试算表任意直写
)


class TestSourceLevelNoLeak:
    def test_user_formula_v2_source_has_no_tb_a13_publish(self) -> None:
        src = inspect.getsource(user_formula_v2)
        for bad in _FORBIDDEN_IN_FORMULA_PATH:
            assert bad not in src, f"user_formula_v2 泄漏 TB/A13 形态: {bad!r}"

    def test_effective_formula_source_has_no_tb_a13_publish(self) -> None:
        src = inspect.getsource(effective_formula)
        for bad in _FORBIDDEN_IN_FORMULA_PATH:
            assert bad not in src, f"effective_formula 泄漏 TB/A13 形态: {bad!r}"


class TestBehaviorLevelNoLeak:
    def test_batch_mutate_only_records_formula_audit_kind(self) -> None:
        store = UserFormulaV2Store()
        audit = InMemoryAuditGate()
        result = apply_batch_mutate(
            store=store,
            operation_id="op-1",
            items=[
                {
                    "commandVersion": "2.0",
                    "clientItemId": "c1",
                    "action": "create",
                    "location": {"wpId": "wp-D4-4"},
                    "target": {"cell": "C5"},
                    "formulaFunction": "TB",
                    "ruleCategory": "auto_calc",
                    "expression": "=TB(6001)",
                    "reason": "seed formula",
                }
            ],
            audit=audit,
            allowed=True,
        )
        assert result["committed"] is True
        # audit 只记公式动作，绝不记审定/调整/错报。
        assert len(audit.entries) == 1
        kind = audit.entries[0].get("kind", "")
        assert kind == "user_formula_v2.batchMutate"
        assert "adjudicat" not in kind and "adjustment" not in kind and "misstatement" not in kind

    def test_effective_formula_resolution_is_pure_no_side_effects(self) -> None:
        # 解析器只产出解析结果 dataclass，不接受任何 TB/A13 client/session 依赖。
        sig = inspect.signature(resolve_effective_formula)
        param_names = " ".join(sig.parameters.keys()).lower()
        for bad in ("session", "db", "trial", "adjustment", "eventbus", "a13"):
            assert bad not in param_names, f"resolve_effective_formula 不该有 {bad!r} 依赖"
        r = resolve_effective_formula(
            make_formula_key("wp-D4-4", "workpaper:D4-4", "r1", "C"),
            custom_expression="=TB(6001)+WP('D4-2')",
            preset_index={},
        )
        # 有效公式解析产出只读结果，state 属六态、不含发布信号。
        assert r.state in {"custom", "preset", "preset_missing", "corrupt", "stale", "blocked"}
