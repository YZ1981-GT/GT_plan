# Phase 0 Task 0.10 + 0.11 — 改造前后真库对比

## 结论：真库输出零差异，且这是**预期**结果

| 报表 | 改造前 | 改造后 | 差异 |
|---|---|---|---|
| `balance_sheet` | 129 行 / 调整列非零 **0** / 未审数非零 42 | 同 | **无** |
| `income_statement` | 78 行 / 调整列非零 **0** / 未审数非零 **0** | 同 | **无** |
| `cash_flow_statement` | `InvalidTextRepresentationError` | 同 | 无 |
| `cash_flow_supplement` | `InvalidTextRepresentationError` | 同 | 无 |

### 为何零差异不等于"改动无效"

真库**全库活体调整分录 = 0**（实测 `global_live_adjustments.live_total = 0`）：

| 项 | 实测值 |
|---|---|
| 该项目 `adjustments` | 34 条，**全部** `is_deleted=true`（2 approved + 32 draft） |
| 全库 `is_deleted=false` 的分录 | **0** |
| `trial_balance` 调整列非零 | **0 / 1386 行** |
| 主表遗留冗余列非零 | `dr_nz=0` `cr_nz=0` `code_nn=0` |

改造前的三个过滤缺失（B1/B2/B3）只在**存在活体分录**时才产生错误数字。
分母为 0 ⇒ 新旧口径都得 0 ⇒ 真库无法区分。

因此 Phase 0 的正确性证明**不依赖真库**，而由 37 个单测 + 4 次变异注入完成
（见下节）。这也是 tasks 0.1 要求先建基线的价值 —— 若不先建，
交付时看到"数字没变"会误判为改动未生效。

## 修正的可执行证明（替代真库 diff）

| 缺陷 | 守卫 | 变异注入验证 |
|---|---|---|
| **B1** 无 `review_status` 过滤 | `test_b1_draft_excluded_from_summary` + `test_b1_mutation_approved_appears` | 把 `include_statuses` 改 `frozenset()` → 打红 ✓ |
| **B2** 无 `origin` 过滤 | `test_b2_workpaper_origin_excluded_from_summary` + `test_b2_mutation_manual_origin_appears` | 把 `exclude_origins` 改 `frozenset()` → 打红 ✓ |
| **B3** 查主表遗留冗余列 | `test_b3_main_table_legacy_columns_not_read` + `test_b3_mutation_entry_row_appears` | 只写主表不建明细行 → 调整列为 0（改造前会是 8888） |
| **B4** 审定数未归一 | `test_b4_revenue_credit_increases_audited` + `test_p2_audited_equals_unadj_plus_net` | 把 `audited` 改回 `unadj + aje_dr - aje_cr` → 3 个测试打红 ✓ |
| **P2** 口径等价 | `test_p2_summary_matches_adj_net_batch` | 调**同一函数**取参照值 |
| 两路径一致 | `test_fallback_path_same_caliber` | 删 `report_config` 触发降级后断言同口径 |

测试总计：**37 passed + 1 xfailed**
（`test_tb_summary_adj_caliber.py` 13+1 / `test_adj_net_batch.py` 17 / `test_adj_caliber_property1.py` 7）

### 变异测试自身的一次失效与修正

首次注入 B4 变异时**未打红**。排查发现是注入位置错 —— 我把
`audited = unadj + aje_dr - aje_cr ...` 插在注释**之前**，而注释之后还有真正的
`audited = unadj + aje_net + rcl_net`，后者覆盖了前者 ⇒ **变异实际未生效**。

⚠️ 教训：**变异测试本身也要验证"变异确实生效"**。「注入后仍全绿」有两种解释
（守卫假绿 / 注入无效），不能直接归因于前者。修正注入位置后 B4 变异正确打红。

## 🔴 0.11 的原定验证目标无法执行

tasks 0.11 原文：「确认唯一 approved 的 `1122 借方 10,000` 正确落到资产负债表
应收账款行而非利润表营业收入行」。

**无法执行**：那笔分录（`AJE-017`）已于 `2026-09-28 08:17:59` 被软删除
（`is_deleted=true`，但 `deleted_at` 为 **NULL** —— 数据本身不一致）。
删除发生在本轮实施之前、用户截图之后。

替代验证：`test_b3_main_table_legacy_columns_not_read` 与
`test_p2_summary_matches_adj_net_batch` 已在受控数据上证明科目归属正确
（收入类分录只落收入行、费用类只落费用行）。

## 实施期新发现的相邻缺陷

### B7 — 公式路径只支持 3 个列名（**影响面大于 B1~B4**）

实测：`COLUMN_ALIASES` 注册 **14** 个列名，但 `get_summary_with_adjustments`
走 `execute_formula(f, tb_map, row_values)` → `FormulaContext.from_simple_map(tb_map)`，
后者只产 **3** 键（`审定数`/`期末余额`/`未审数`）⇒ 其余 **11 个恒 0**：

```
AJE调整 / RJE调整 / 借方发生额 / 年初余额 / 期初余额 / 本期借方 /
本期借方发生额 / 本期发生额 / 本期贷方 / 本期贷方发生额 / 贷方发生额
```

🔴 **真库利润表公式普遍使用 `本期发生额`**（`IS-001` 实为
`SUM_TB('6001~6099','本期发生额')`）⇒ **整张利润表 78 行未审数全空**，
与基线实测 `income_statement 未审数非零 = 0` 完全吻合，也解释了用户截图里
`IS-001` 未审数显示「—」。

处置：不在 Phase 0 范围（本 Phase 改调整列，B7 属未审数列），但已用
`xfail(strict=True)` 钉住 —— `test_b7_period_amount_column_should_resolve`
现在必红，一旦修好会 XPASS 失败强制回来删标记，缺陷不会被遗忘。
另加 `test_b7_documented_supported_columns` 如实断言现状边界（3 可用 / 11 恒 0），
使边界变化无论变好变坏都被发现。

修复方向：L2 预载发生额四键。`adjudication_writeback` 已有先例
（复用 `four_table/occurrence_by_standard_code.merge_occurrence_into_tb_data`）。

### 其他实施期发现

| 编号 | 内容 | 处置 |
|---|---|---|
| **B5** | `adjustment_service.py` 8 处读主表遗留列 | 记录于 `phase0-cross-cutting-scan.md`，建议独立 spec |
| **B6** | `misstatement_service.py` 3 处读主表遗留列，**会写库** | 同上 |
| — | `report_type` 枚举只 3 值而前端传 4 个 ⇒ 现金流量表/附表两个 tab 必报错 | 与本 spec 无关，另记 |
| — | 该项目 2 条 approved 分录 `is_deleted=true` 但 `deleted_at=NULL` | 数据一致性问题，另记 |

## Phase 0 交付摘要

**生产代码改动 2 文件**：
- `adjustment_amount_source.py`：新增 `adj_net_batch`（批量对偶）+ 模块头口径矩阵补第 4 行
- `trial_balance_service.py`：两条路径（主 + fallback）收敛到 `adj_net_batch`，
  修 B1/B2/B3/B4；清理死 import

**验证**：
- 本 spec 新增测试 37 passed + 1 xfailed
- 既存相关套件零回归（7 failed 与基线**逐项一致**，passed 92 → 116）
- 4 次变异注入全部正确打红后还原，grep `MUTATION` 无残留

**需求 1.1 的量化判据**：`adj.c.account_code` / `adj.c.debit_amount` /
`adj.c.credit_amount` 在 `trial_balance_service.py` 内引用数 = **0**（改造前 6 处）。

## 归因补充（Task 0.10 收尾时发现）

扩大回归面到 `test_event_bus.py` + `test_report_engine.py` 后，红项由 7 增至 **11**。
新增 4 项：

| 测试 | 归因 |
|---|---|
| `test_event_bus.py::TestOnAdjustmentChanged::test_on_adjustment_changed_updates_trial_balance` | 预存 |
| `test_report_engine.py::test_balance_sheet_values` | 预存 |
| `test_report_engine.py::test_income_statement_values` | 预存 |
| `test_report_engine.py::test_regenerate_affected` | 预存 |

**验证方法**（铁律㉔）：`git stash push -- backend/app/services/trial_balance_service.py
backend/app/services/adjustment_amount_source.py` 回到 HEAD 后单独跑这 4 项 ⇒
**同样 4 failed** ⇒ 确认预存，非本轮引入。随后 `git stash pop` 恢复
（`adjustment_amount_source.py` +136/−2、`trial_balance_service.py` +116/−99）。

这 4 项与前述 7 项同源：fixture 只写主表遗留冗余列，而生产代码已按
ADR-ADJ-001 改读明细表。`test_report_engine` 的 3 项另受 B7 影响
（报表公式用 `本期发生额`）。

**最终回归口径**：13 个测试文件 **169 passed / 11 failed / 1 xfailed**，
11 failed 全部经 stash 验证为预存。

## 🔴 迁移版本号已被并发会话占用

Task 0.10 收尾时 `git status` 显示工作树已存在：

```
backend/migrations/V166__sampled_vouchers_date_and_wp_scope.sql
backend/migrations/R166__rollback_sampled_vouchers_date_and_wp_scope.sql
```

⇒ **V166 已被占用**。本 spec Phase 2 的迁移须取更大号。

这正是 tasks 2.1 要求「**禁写死 V166**，必须重新扫 `backend/migrations/V*.sql`
取最大值 +1」的价值 —— 撰写 spec 时现算为 V165（故预期 V166），
但并发会话在此期间已加了 V166。若照 spec 文字写死会直接撞号，
而 `scan_migrations` 的同号检测会抛 `RuntimeError`（V040 冲突后已加该检测）。

---

# 追加：11 failed + 1 xfailed 全部修复（用户要求全修）

最终状态：**202 passed / 0 failed / 0 xfailed**（14 个测试文件）。

## 11 红分三组，根因各不同

诊断时**不预设**同源，逐组实证。结论是三组根因完全不同：

| 组 | 数量 | 根因 | 性质 |
|---|---|---|---|
| A | 8 | fixture 只写主表遗留冗余列 + 未显式 `approved` | 测试过时 |
| B | 3 | `generate_all_reports` 的自动 `full_recalc` 清空 fixture 数据 | 测试与生产契约不匹配 |
| C | 1 xfailed | **B7 生产代码缺陷** | 真缺陷 |

### 🔴 B 组的推测被证伪

原以为 B 组（`test_report_engine` 3 红）是 B7 导致。**逐层实测排除**：

| 探测层 | 实测值 | 结论 |
|---|---|---|
| `_resolve_tb('1001','期末余额')` | **50000** | 正常 |
| `evaluate_formula(BS-002 三 token 公式)` | **1150000** | 正常 |
| `TB_PATTERN.finditer` 匹配数 | **3** | 正常 |
| 预替换后表达式 | `50000.00 + 1000000.00 + 100000.00` | 正常 |
| L1 内核求值 | value=1150000, errors=[] | 正常 |

⇒ 公式链路**全程正常**，B7 不是原因。

真根因在 `ReportEngine.generate_all_reports` 开头：
```python
# 🔴 报表生成前自动 recalc trial_balance，确保基于最新逻辑计算
try:
    await tb_svc.full_recalc(project_id, year)
except Exception:
    ...  # fail-open
```
fixture 只种 `trial_balance`、没种上游 `tb_balance` + `account_mapping`
⇒ `recalc_unadjusted` 从空上游重算 ⇒ 把 fixture 种的值**清零**。

⚠️ `report_engine` 走**预替换路径**（`resolver.resolve_tb` → `_COLUMN_MAP`），
与 `get_summary_with_adjustments` 的 **ctx 注入路径**是两条独立通路，
B7 只影响后者。这一点在 requirements E2 已记录，诊断时据此才没走错方向。

## B7 修复（生产代码）

`get_summary_with_adjustments` 弃用 `execute_formula`（内部走 `from_simple_map`
只产 3 键），改**显式构造 `FormulaContext`**，预载 **9 键**：

| 键 | 来源 | 说明 |
|---|---|---|
| `期末余额` / `审定数` / `未审数` | `unadjusted_amount` | 🔴 **三者仍全等于 unadjusted，语义不可改** |
| `年初余额` | `opening_balance` | 新增 |
| `本期发生额` | `unadjusted − opening` | 与 `report_engine._period_amount` 未审模式同口径 |
| `AJE调整` / `RJE调整` | `adj_net_batch` 归一净额 | 与 TB 持久化列同源 |
| `本期借方` / `本期贷方` | 共享件 `merge_occurrence_into_tb_data` | fail-open 包裹 |

**为何三键不能改成真实映射**：本方法的公式只负责算「未审数列」。把 `审定数`
映射到真 `audited_amount` 会让未审数列变成审定数列 —— 那是语义破坏而非修复。

**🔴 借贷两键必须显式占位 `Decimal("0")`**：`merge_occurrence_into_tb_data`
只在 occurrence 有该科目时写键，而 `aggregate_occurrence` **有意不产零值键**。
不占位则无 `tb_balance` 数据的科目落进 `_resolve_tb_column` 的
「已注册但无数据」态 —— 与 B7 缺陷形态完全相同，只是范围小。

## 🔴 我的守卫假绿被自己的变异测试抓到一次

`test_b7_all_registered_columns_are_resolvable` 首版**在测试里自建 tb_data**，
注入变异后**没打红** ⇒ 无论生产代码怎么退化都会通过。

改为用 monkeypatch 截获 `FormulaContext.__init__` 收到的**真实** tb_data 后，
立刻抓出我自己的真实遗漏（借贷 6 个别名未预载）。改完再注入变异，正确打红。

⚠️ 教训：**守卫必须探测生产代码的真实产物**。在测试里复刻一份等价逻辑，
测的是复刻件而非被测对象。

判据设计上还有一点：按 **键存在性 / trace** 判而非按**值**判 ——
`本期借方` 无数据时 0 是「诚实的 0」（共享件注释明确说明 `aggregate_occurrence`
有意不产零值键），真缺陷形态是规范名根本不在 `tb_data` 里。

## A 组修复的关键前置发现

`Adjustment.review_status` 的 **server_default 是 `draft`**，而
`recalc_adjustments` 按 ADR-ADJ-003 只纳入 `approved`
⇒ **光补明细行不够**，必须显式设 `approved`。

三个必要条件缺一即调整列恒 0：
1. 建 `AdjustmentEntry` 明细行（ADR-ADJ-001）
2. 显式 `review_status=approved`（ADR-ADJ-003）
3. `origin` 非 `workpaper`（ADR-ADJ-002 / V124）

### 修复中我引入并修掉的新问题

补明细行后 `test_trial_balance_sign_passthrough.py` 的 `pg_factory` 收尾清理
触发 `ForeignKeyViolationError` —— 清理只删 `adjustments` 不删
`adjustment_entries`，而后者有 `adjustment_entries_adjustment_id_fkey` 指向主表。

且 **`AdjustmentEntry` 没有 `project_id` 列**，只能按 `adjustment_id`
子查询关联删，并且必须**先于** `adjustments` 删。修前该文件 **6 个测试全 ERROR**
（不只我改的 2 个）。

## B 组修复：上游种子口径必须与 recalc 严格对齐

`recalc_unadjusted` 对两类科目口径不同（实测源码确认，非推测）：

| 科目类别 | 取值来源 | 符号处理 |
|---|---|---|
| 资产 / 负债 / 权益 | `tb_balance.closing_balance`（v1 借正贷负） | 贷方类 `abs()` 转 v2 自然正数 |
| **损益类（5xxx/6xxx）** | **`debit_amount` / `credit_amount` 单边发生额** | 收入取贷方、费用取借方；`opening` 强制置 0 |

故 fixture 种 `TbBalance` 时必须分流，且方向判定**复用生产代码同一个
`resolve_account_direction`**，避免两处口径漂移。另需 1:1 自映射
`AccountMapping`（无映射时 `_resolved_std_subq()` 解析出 NULL 被过滤）。

## 变异证明（4 次，全部正确打红后还原）

| 变异 | 注入内容 | 打红 |
|---|---|---|
| FIX1 | `approved` → `draft` | `test_trial_balance.py` 5 个 ✓ |
| FIX2 | 去掉 `AdjustmentEntry` 创建 | 同上 5 个 ✓ |
| FIX3 | 不种 `TbBalance` 上游 | `test_report_engine.py` 3 个 ✓ |
| B7b | 去掉借贷发生额占位 | `test_b7_all_registered_columns_are_resolvable` ✓ |

还原后 grep `MUTATION` 仅剩 3 个正常的测试函数名
（`test_b1_mutation_approved_appears` 等双向变异守卫本身），无注入残留。

## 最终测试口径

| 文件 | 结果 |
|---|---|
| 14 个相关测试文件合跑 | **202 passed / 0 failed / 0 xfailed** |

改造前基线为 **169 passed / 11 failed / 1 xfailed**。
