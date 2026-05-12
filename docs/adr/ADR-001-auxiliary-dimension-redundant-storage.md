# ADR-001：辅助维度冗余存储模型

**状态**：已实施（2026-05-10）
**决策者**：Sprint 8 Layer 2 v2 复盘
**相关代码**：
- `backend/app/services/ledger_import/converter.py` — `convert_balance_rows` / `convert_ledger_rows`
- `backend/app/routers/ledger_penetration.py` — `/balance-tree` 端点
- `audit-platform/frontend/src/components/ledger-import/LedgerBalanceTreeView.vue`

---

## 背景

账表导入时，同一行余额/序时账可能带多维度辅助核算（如"客户 × 项目 × 成本中心"）。如何存储和校验？

真实数据示例（YG36 重庆医药集团四川物流）：

```
原始行 A: 金融机构:YG0001,工商银行 ; 银行账户:3100035219100042014
         closing = 3948.93

原始行 B: 金融机构:YG0018,中国邮政储蓄银行 ; 银行账户:951004010002007700
         closing = 100.00

主表合计 closing = 4048.93
```

## 决策

**对含辅助维度的一行，在 `tb_aux_balance` / `tb_aux_ledger` 按维度数冗余存 N 条，每条都记原行金额。**

上例入库结果：

| 父主表 | aux_type | aux_code | aux_name | closing |
|--------|----------|----------|----------|---------|
| 1002   | 金融机构 | YG0001   | 工商银行 | 3948.93 |
| 1002   | 金融机构 | YG0018   | 邮储     | 100.00  |
| 1002   | 银行账户 | NULL     | 3100...  | 3948.93 |
| 1002   | 银行账户 | NULL     | 951...   | 100.00  |

共 4 条 aux_balance，冗余存储。

## 关键性质

**按 aux_type GROUP BY 求和 = 主表 closing**（冗余但自洽）：

```sql
SELECT aux_type, SUM(closing_balance) FROM tb_aux_balance
 WHERE account_code = '1002' AND project_id = :pid AND year = :yr
 GROUP BY aux_type;
-- 金融机构 | 4048.93   ← = 主表
-- 银行账户 | 4048.93   ← = 主表
```

**禁止**：平铺所有 aux 行求和（= 父 × N 维度数，会误报 mismatch）：

```sql
-- ❌ 反例：得到 8097.86 = 父 × 2，但这是正确数据不是 bug
SELECT SUM(closing_balance) FROM tb_aux_balance
 WHERE account_code = '1002';
```

## 实施要点

### 入库阶段

- `convert_balance_rows` 按原行的 `aux_dimensions` 解析出 N 个维度，每个维度 append 1 条 aux_balance_row，金额都 = 原行金额
- 主表去重：按 `(company_code, account_code)` 分组，每组最终产出 1 条主表行（有汇总行用汇总、仅明细则 `_aggregate_aux_to_summary` 生成虚拟汇总）
- `_aux_row_count` 记录聚合基数，方便溯源

### 校验/聚合阶段

- 所有涉及 `tb_aux_balance` 的一致性校验**必须**先 `GROUP BY aux_type` 再与主表比对
- `/balance-tree` 端点的 `mismatches` 字段按 `(account_code, aux_type)` 对校验，差额 > 1 元才记
- 前端 `LedgerBalanceTreeView` 用三层树形（父科目 > 维度组 > 明细）避免平铺误导用户

### 影响的代码路径（未来新增聚合逻辑必须遵守此模式）

- `validate_four_tables`（smart_import_engine.py:1210）
- `consistency_check_service._check_tb_vs_balance`
- `consistency_replay_engine`
- `import_intelligence` DQ-05
- 未来的合并工作底稿一致性校验

## 备选方案（已否决）

**方案 A：只存"主维度"，其他塞 raw_extra**

> 将一行里的第 1 个维度入 aux_balance，其余（如"银行账户"）塞原行 raw_extra 作属性。

否决原因：
- 无法支持"按银行账户穿透查询"（业务需求）
- 主维度顺序依赖解析策略，不稳定
- 和旧引擎行为不一致（需同步改 smart_import_engine，风险大）

**方案 B：建独立的 `aux_coordinate` 表存"坐标点"，aux_balance 变指针**

> 每行原始数据 = 一个坐标点，金额只存 1 次，aux_balance 变 N:1 关联表。

否决原因：
- 重构量巨大（4 张表 + 所有聚合路径）
- 真实价值低（当前冗余存储按维度聚合后完全正确）
- 穿透查询性能退化（需 JOIN）

## 命中的踩坑记录

1. **2026-05-10 Layer 2 v1**：`/balance-tree` 端点用"所有 aux 行求和"判 mismatch 得到 12 误报。修复 = 改按 aux_type 分组求和。详见 `dev-history.md`
2. **2026-05-10 Layer 3 扩大分析**：第一反应认为"冗余存储是 bug"想修 parse_aux_dimension，查真实 raw 数据后发现是校验算法 bug 不是数据 bug。教训：先按不同维度 GROUP BY 验证再判断

## 测试覆盖

- `backend/tests/ledger_import/test_converter_balance_dedup.py::test_multi_dimension_redundant_storage`（入库层）
- `backend/tests/ledger_import/test_converter_balance_dedup.py::test_multi_dimension_with_summary_row_dedup`（入库层 + 汇总行场景）
- `backend/tests/test_ledger_penetration.py::TestBalanceTreeEndpoint::test_multi_dimension_same_amount_no_mismatch`（端点层）

## 真实数据验证（2026-05-10）

YG36 四川物流 1002 银行存款：
- 主表 `tb_balance` 1 行，closing=4048.93
- 辅助 `tb_aux_balance` 4 行（金融机构 × 2 + 银行账户 × 2）
- `/balance-tree` 端点：2 维度组节点（每组求和 4048.93=父），mismatches=0
