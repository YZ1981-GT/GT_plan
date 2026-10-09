# Phase 0 Task 0.8 — 触类旁通扫描结果

> 铁律：「发现一处反模式立即 grep 全仓找同类一次修完」。
> 本文件记录扫描口径、假阳修正过程、以及超出 Phase 0 范围的同类命中。

## 扫描口径的两次修正

### 首版口径错：正则匹配了任意表别名

首版用 `\.c\.(account_code|debit_amount|credit_amount)` 扫，得 **28 命中**。
但该正则会命中**任何**表别名，实际绝大多数是别的表：

| 别名 | 真实表 | 是否本缺陷 |
|---|---|---|
| `bal.c.` | `tb_balance` | ❌ 无关 |
| `child.c.` | `tb_balance` 自连接 | ❌ 无关 |
| `ac.c.` | 标准科目表 | ❌ 无关 |
| `ae.c.` | `adjustment_entries`（**正确**的表） | ❌ 无关，是修复后的目标 |
| `adj.c.` | `adjustments` 主表 | ✅ 本缺陷 |

### 修正版：先定位别名绑定再扫

改为先用 `^\s*(\w+)\s*=\s*Adjustment\.__table__` 取得该文件里主表的真实别名，
再只扫该别名的遗留列。**28 假阳 → 11 真实命中**。

> 这是「扫描口径必复核覆盖面」的又一实例：只看命中数会把 28 当成缺陷规模，
> 据此排工时会严重失真；反过来若首版只扫 `adj.c.` 而漏了别名可能叫 `a`/`adjt` 的文件，
> 又会假阴。两头都要防，故采用「先取别名再扫」。

## 真实命中：11 处 / 2 个文件

### 本 spec 已修（0 残留）

| 文件 | 命中 |
|---|---|
| `backend/app/services/trial_balance_service.py` | **0** ✓（改造前 6 处，Phase 0 已全部收敛） |

### 🔴 超出 Phase 0 范围的同类命中

#### B5 — `adjustment_service.py`（8 处）

| 行 | 列 | 上下文 |
|---|---|---|
| L190 | `account_code` | `array_agg(distinct adj.c.account_code)` |
| L453 | `debit_amount` | `sum(...).label("total_debit")` |
| L454 | `credit_amount` | `sum(...).label("total_credit")` |
| L793 | `account_code` | 按 `entry_group_id` 分组的净额查询 |
| L795 | `debit_amount` | `sum(dr) - sum(cr) AS net` |
| L796 | `credit_amount` | 同上 |
| L801 | `account_code` | `IN (account_codes)` |
| L809 | `account_code` | `GROUP BY` |

L785-812 那段的**自带注释**写道：
> 与 trial_balance_service.recalc_adjustments（Task 3.3）使用同一 direction_resolver 口径

但它读的是**主表遗留列**，而 `recalc_adjustments` 读的是明细表 ⇒ **注释声称同口径、实际不同源**。
且同样缺 `review_status` / `origin` 过滤（B1/B2 同型）。

实测后果：真库这三列全库 0 非零 ⇒ 该查询的 `net` **恒为 0**。

#### B6 — `misstatement_service.py`（3 处）

| 行 | 列 |
|---|---|
| L169 | `account_code` |
| L171 | `debit_amount` |
| L172 | `credit_amount` |

用途：把调整分录转为错报记录时读取金额。读废弃列 ⇒ 创建出的错报记录**金额为 0**。
🔴 **此处会写库**（创建 misstatement 行），比只读路径危害更大。

## 为何不在 Phase 0 内一并修

不是回避，是三条具体理由：

1. **形态不同，非机械替换**。`get_summary_with_adjustments` 要的是「按科目聚合」，
   而 B5 的 L785 要的是「按 `entry_group_id` 分组」、B6 要的是「逐明细行」。
   `adj_net_batch` 的返回形状（按科目聚合）**不适配**这两者，各需自己的取数函数。
2. **B6 会写库**。改数据源就改了写入内容，需要单独的基线 + 回归验证，
   混进本 Phase 会让 diff 不可评审。
3. **口径待定**。B5/B6 该用哪套 `include_statuses` / `exclude_origins` 尚未裁定 ——
   错报转换是否该纳入 draft？按 ADR-ADJ-002 的精神，「呈现类」不排除 origin，
   但错报是否属呈现类需要审计专业判断，不能由实现方自行决定。

## 建议

另起 spec 处理 B5/B6，范围 = 「`adjustments` 主表遗留冗余列全仓退役」，
内容应含：
- 逐调用点裁定口径（B5 的 3 个查询 + B6 的 1 个，共 4 处语义各异）
- 为「按 entry_group 分组」与「逐明细行」两种形态各补批量取数函数
- B6 的写库行为变更需真库基线对比
- 收尾：给 `Adjustment` 的 `account_code` / `debit_amount` / `credit_amount`
  三列加 deprecated 标注或迁移删除（实测全库 0 非零，已无数据依赖）

⚠️ 该 spec 还应顺带处理 evidence/phase0-pre-existing-red.md 记录的
「同一聚合 4 处实现」中的第 2 处（`recalc_adjustments` 自己的内联 SQL 未走 `adj_net`）。
