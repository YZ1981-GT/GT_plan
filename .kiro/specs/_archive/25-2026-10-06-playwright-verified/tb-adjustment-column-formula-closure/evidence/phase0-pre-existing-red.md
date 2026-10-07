# Phase 0 Task 0.2 — 预存红项基线

采集时间：2026-09-28
采集命令：
```
python -m pytest tests/test_trial_balance.py tests/test_trial_balance_sign_passthrough.py \
  tests/test_adj_amount_source_parity.py tests/test_adj_e2e_integration.py \
  tests/test_adj_formula_resolution.py tests/test_adj_single_source_guard.py \
  tests/test_adj_handler_name_event_parity.py tests/test_adj_approved_event_properties.py -q --tb=line
```

结果：**7 failed, 92 passed**

## 归因证据（铁律㉔）

实施前 `git diff --numstat` 对下列 4 个文件**无输出**（= 与 HEAD 逐字一致）：

| 文件 | 状态 |
|---|---|
| `backend/app/services/trial_balance_service.py` | 与 HEAD 一致 |
| `backend/app/services/adjustment_amount_source.py` | 与 HEAD 一致 |
| `backend/tests/test_trial_balance.py` | 与 HEAD 一致 |
| `backend/tests/test_trial_balance_sign_passthrough.py` | 与 HEAD 一致 |

⇒ 这 7 个红项**既非本轮引入，也非并发会话触及这些文件所致**，是 HEAD 上的预存失败。

## 红项清单

| # | 测试 | 断言 | 实得 |
|---|---|---|---|
| 1 | `test_trial_balance.py::test_recalc_adjustments` | `aje_adjustment == 500` | `0.00` |
| 2 | `test_trial_balance.py::test_recalc_audited` | `audited == 13000` | `12000.00` |
| 3 | `test_trial_balance.py::test_recalc_audited_liability_credit_increase` | `aje == 1000` | `0.00` |
| 4 | `test_trial_balance.py::test_recalc_audited_liability_debit_decrease` | `aje == -1000` | `0.00` |
| 5 | `test_trial_balance.py::test_recalc_audited_revenue_credit_increase` | `aje == 500` | `0.00` |
| 6 | `test_trial_balance_sign_passthrough.py::test_audited_liability_credit_increase_direction` | `aje == 1000` | `0.00` |
| 7 | `test_trial_balance_sign_passthrough.py::test_audited_revenue_credit_increase_direction` | `aje == 500` | `0.00` |

七项**同一根因**：调整列恒 0。

## 🔴 根因：fixture 过时，不是引擎错

测试 fixture 只往**主表** `Adjustment` 塞遗留冗余列：

```python
Adjustment(
    project_id=pid, year=2025, company_code="001",
    adjustment_no="AJE-001", adjustment_type=AdjustmentType.aje,
    account_code="1001", account_name="库存现金",          # ← 主表冗余列
    debit_amount=Decimal("500"), credit_amount=Decimal("0"),  # ← 主表冗余列
    entry_group_id=group_id, created_by=FAKE_USER_ID,
)
```

而被测方法 `recalc_adjustments`（`trial_balance_service.py` L347-370）已被
`adj-formula-repair-and-approval-gate-wiring` 按 ADR-ADJ-001 改造为**读明细表**：

```python
.select_from(ae.join(adj, ae.c.adjustment_id == adj.c.id))
.where(
    adj.c.is_deleted == sa.false(),
    adj.c.review_status == "approved",                              # ADR-ADJ-003
    sa.or_(adj.c.origin.is_(None), adj.c.origin != "workpaper"),    # ADR-ADJ-002 / V124
)
.group_by(ae.c.standard_account_code, adj.c.adjustment_type)
```

fixture 从未创建 `AdjustmentEntry` 行 ⇒ JOIN 结果为空 ⇒ 调整列恒 0。

**判定：fixture 过时，引擎正确。** 与 memory.md 记录的 consol worksheet 同型教训一致
（「先读设计文档确认是引擎错还是 fixture 过时，不预设引擎会计 bug」）。
该 spec 改了生产代码口径但**未同步更新这 7 个测试**。

## 与本 spec 的关系

`recalc_adjustments` 是**正确的参照实现** —— 它已具备本 spec 要给
`get_summary_with_adjustments` 补上的全部三个过滤（B1 status / B2 origin / B3 明细表）。
即：同一文件内，recalc 路径已合规，summary 路径未合规。

## 🔴 采集中额外发现：同一聚合在仓库里有 3 份实现

| # | 位置 | 取数口径 | 过滤是否合规 |
|---|---|---|---|
| 1 | `adjustment_amount_source.adj_net` | 明细表 + JOIN | ✅（参数化） |
| 2 | `trial_balance_service.recalc_adjustments` | 明细表 + JOIN（**自己的内联 SQL，未走 adj_net**） | ✅ |
| 3 | `trial_balance_service.get_summary_with_adjustments` | **主表冗余列** | ❌ B1/B2/B3 |
| 4 | `trial_balance_service._get_summary_from_mapping` | 主表冗余列（待 0.8 确认） | ❌ |

`recalc_adjustments` 虽口径正确，但它是第 2 份独立实现。本 spec Phase 0 只收敛 #3/#4
（它们产出错误数字）；#2 的合并属"可更干净"而非"修正确性"，记为后续议题。

⚠️ 合并 #2 时需注意一处**语义差异**：`recalc_adjustments` 在 L405-416 用
`trial_balance.account_name` 解析科目方向，而 `adj_net` 内部用
`AdjustmentEntry.account_name` —— 两个 name 来源不同，`resolve_account_direction`
的结果可能不同。不可假定等价。

## 对 Phase 0 的影响

1. 这 7 个红**不阻塞** Phase 0 实施（它们测的是 recalc 路径，我改的是 summary 路径）
2. 但它们使 recalc 区域**失去回归保护**；且我的改动与它们同属一次迁移（主表→明细表）
3. ⇒ 决定：Phase 0 内顺带修这 7 个 fixture（把 `Adjustment` + 冗余列改为
   `Adjustment` + `AdjustmentEntry` 明细行），使测试套件能守护本轮改动。
   该修复作为独立步骤，不与口径改动混在同一 commit。
