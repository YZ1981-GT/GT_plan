# 需求文档：ADJ 取数修复与调整分录确认门接线

> 关联设计：#[[file:.kiro/specs/adj-formula-repair-and-approval-gate-wiring/design.md]]
> 工作流：Design-First。EARS 风格，关联设计 §六 属性 P1~P12。
> 类型：bugfix + 口径统一（**非新功能**）。

## 引言（Introduction）

用户目标是打通「四表库入库 → 试算表未审数 → 底稿明细表/披露表/审定表」上行链路，
与「分录确认 → 审定表/披露表/报表审定数/试算表审计调整/分录大厅」下行链路。

调研实证：链条骨架**已由既有事件总线打通**（`LEDGER_DATASET_ACTIVATED` →
`full_recalc` → `TRIAL_BALANCE_UPDATED` → `ReportEngine` → `REPORTS_UPDATED` →
`DisclosureEngine`），本 spec **不重建链条**，只修三处使链条在「调整分录」这一段
实际失效的缺陷：

1. **`ADJ()` 公式取数每次调用必抛 `ImportError`** —— 审定表调整列恒空（探针实测）。
2. **「项目组确认」不产生任何下游动作** —— 确认动作不发事件，下游只认「创建/草稿批量提交」。
3. **三套 ADJ 取数口径互不一致**，却各自注释声称「同口径」。

### 范围内

ADJ 取数修复（import / 类型参数 / 口径统一）· `ADJUSTMENT_APPROVED` 事件引入 ·
`on_event_adjustment_approved` 名实不符修正 · 试算表调整列按确认态过滤 ·
ADJ 求值端到端守卫（补测试盲区）。

### 范围外（明确不做）

- **不把 `ADJ()` 注册进 L1 内核 `formula_engine._REGISTRY`**。归档 spec 已裁定
  `ADJ()` 属 prefill 引擎专属函数，且 L1 是纯同步函数（"不依赖 async/DB，由 L2
  编排层预载后注入"），ADJ 需 DB 查询。收口路径见设计 §七 ADR-ADJ-004（留待后续）。
- 不改 `trial_balance.unadjusted_amount` / `aje_adjustment` / `rje_adjustment`
  三列的**派生列性质**（它们由聚合重算写入，公式不可直写；两套独立实现
  `formula_runtime/adapters/adjudication.py` 与 `custom_query/snapshot_writer_modules.py`
  均只开 `audited_amount` 一列，本 spec 维持该设计）。
- 不动四表库 → 试算表未审数的映射聚合路径（`recalc_unadjusted`）。
- 不做披露表 → 附注的载荷问题（另立 `disclosure-payload-authority-source`）。

## 术语（Glossary）

| 术语 | 含义 |
|------|------|
| ADJ() | prefill 公式函数 `ADJ('科目码','类型')`，取调整分录净额 |
| 三套口径 | `recalc_adjustments` / `_resolve_adj_formula` / `_get_adj_value` 各自的取数过滤条件 |
| 确认门 | 分录复核状态机到达 `approved` 这一事件点 |
| 派生列 | 由聚合重算写入、不接受公式直写的 trial_balance 列 |
| 现算值 | 交付时由脚本重新统计得出的计数，**禁写死进判据** |

---

## 需求 1：修复 `ADJ()` 取数的 import 缺陷

**用户故事**：作为审计助理，我希望审定表里的 AJE/RJE 调整列能自动取到调整分录金额，
而不是永远空白。

### 验收标准（Acceptance Criteria）

1. THE `prefill_engine._resolve_adj_formula` SHALL 从 `app.models.audit_platform_models`
   导入 `Adjustment` / `AdjustmentEntry`（当前写的 `app.models.phase10_models`
   **无此二者定义也无 re-export**，探针实测抛
   `ImportError: cannot import name 'Adjustment' from 'app.models.phase10_models'`）。
2. WHEN 任一 `=ADJ('code','type')` 预设被求值 THEN SHALL NOT 抛 `ImportError`。
3. WHEN 求值成功 THEN 返回值 SHALL 为 `Decimal`（无匹配数据时为 `Decimal("0")`，
   保持既有 fail-closed 语义，不返回 `None`）。
4. THE 修复 SHALL NOT 改变 `resolve_formula_value` 的对外签名与 `_FORMULA_RESOLVERS` 注册形态。
5. IF 其他 resolver 存在同类错误 import THEN SHALL 一并 grep 全量修复（触类旁通铁律），
   并在设计 §五 登记现算命中数。

---

## 需求 2：修复 `ADJ()` 第二参字面量不匹配

**用户故事**：作为审计助理，我希望 AJE 列取到的是审计调整、RJE 列取到的是重分类，
而不是两列显示同一个合计数。

### 验收标准

1. THE `_resolve_adj_formula` SHALL 识别预设实际使用的字面量 `aje_net` / `rje_net`
   （现算分布见设计 §五；当前实现只认 `AJE`/`审计调整`/`RJE`/`重分类`，
   而 `'aje_net'.upper() == 'AJE_NET'` 使两个分支**皆不命中** ⇒ 退化为不加
   `adjustment_type` 过滤 ⇒ AJE 与 RJE 返回同一合计）。
2. THE 类型归一 SHALL 同时兼容既有写法（`AJE`/`RJE`/`审计调整`/`重分类`），
   不得因修复而让历史写法失效。
3. WHEN 第二参无法归一到 `aje` 或 `rje` THEN 系统 SHALL 视为**非法入参**并在
   返回结构中上报该单元格错误，SHALL NOT 静默省略 `adjustment_type` 过滤。
4. THE 类型归一逻辑 SHALL 与 `wp_cross_check_service._get_adj_value` 的口径一致
   （后者 `adj_type_filter = "aje" if adj_type == "aje_net" else "rje"` 已匹配预设字面量）。
5. WHEN `prefill_formula_mapping.json` 中存在未替换的占位符第二参（现算 1 处 `'类型'`）
   THEN SHALL 由幂等修正脚本改为正确字面量，并配守卫防回归。

---

## 需求 3：统一三套 ADJ 取数口径

**用户故事**：作为项目经理，我希望底稿里 `ADJ()` 取到的数、试算表调整列的数、
交叉核对用的数三者一致，否则勾稽永远对不上。

### 验收标准

1. THE 三处实现 SHALL 收敛到**单一取数函数**（新建共享取数模块），三处改为调用它：
   `trial_balance_service.recalc_adjustments` · `prefill_engine._resolve_adj_formula` ·
   `wp_cross_check_service._get_adj_value`。
2. THE 统一口径 SHALL 显式声明以下四个维度（现状差异见设计 §五 对账表）：
   科目列（`adjustments.account_code` vs `adjustment_entries.standard_account_code`）·
   `review_status` 过滤 · `origin` 过滤 · 符号归一（`resolve_account_direction`）。
3. WHEN 三处口径统一后 THEN 同一 `(project_id, year, account_code, adj_type)` 输入
   SHALL 在三处返回**逐值相同**的 `Decimal`（关联属性 **P5**）。
4. THE 统一函数 SHALL 保留 `origin` 维度可参数化 —— `recalc_adjustments` 需排除
   `origin='workpaper'` 防与审定表 writeback 双计（V124 既有约定），而公式取数口径
   由设计 §七 ADR-ADJ-002 裁定，**不得靠注释声称一致而实际不同**。
5. IF 任一处无法收敛 THEN SHALL 在设计中显式记录原因与差异边界，
   SHALL NOT 留下自称「同口径」而实际不同的注释（当前三处注释均如此）。

---

## 需求 4：引入 `ADJUSTMENT_APPROVED` 事件（确认门）

**用户故事**：作为项目组成员，我希望**确认**调整分录后下游才联动，
而不是一创建草稿就把未定稿的数推到试算表和附注。

### 验收标准

1. THE `EventType` SHALL 新增成员 `ADJUSTMENT_APPROVED = "adjustment.approved"`
   （当前枚举无此成员；但 `trial-balance-version-timemachine` 的 trigger 枚举
   已含 `adjustment_approved` 字面量，说明设计早有预期）。
2. WHEN `AdjustmentService._change_review_status` 把状态改为 `ReviewStatus.approved`
   THEN 系统 SHALL 发布 `ADJUSTMENT_APPROVED`，payload 含 `project_id` / `year` /
   `account_codes`（受影响科目）/ `entry_group_id`。
3. THE 事件 SHALL 在**审批落库之后**发布（照搬 `ELIMINATION_APPROVED` 样板：
   `routers/consolidation.py` 在 `await db.commit()` 之后 publish）。
4. WHEN 状态改为 `rejected` 或回到 `draft` THEN SHALL 同样通知下游需要重算
   （否则已被计入的分录撤回后下游不回退）。事件形态由设计 §四 裁定。
5. IF 下游 handler 执行失败 THEN SHALL 记 error 日志但**不阻断审批本身**
   （审批已落库，重算为下游派生动作，对齐 ELIMINATION_APPROVED 的 EH3 约定）。
6. WHEN 同一分录组重复触发 `ADJUSTMENT_APPROVED` THEN 下游重算结果 SHALL 幂等
   （靠全量/按科目覆盖写，关联属性 **P8**）。

---

## 需求 5：修正 `on_event_adjustment_approved` 名实不符

**用户故事**：作为维护者，我希望 handler 的名字和它订阅的事件一致，
否则读代码的人会以为「确认后附注会标过期」，而实际触发条件是草稿批量提交。

### 验收标准

1. THE `event_handlers/_impl.py` 中 `on_event_adjustment_approved` SHALL 订阅
   `EventType.ADJUSTMENT_APPROVED`（当前订阅 `ADJUSTMENT_BATCH_COMMITTED`，
   docstring 亦写 `ADJUSTMENT_BATCH_COMMITTED →`，与函数名矛盾）。
2. THE 同组另两个 handler（`on_event_ledger_activated` / `on_event_workpaper_reviewed`）
   SHALL 保持现状不动（二者名实相符，已实证）。
3. WHEN 需要保留「草稿批量提交也标附注 stale」的行为 THEN SHALL 用**独立命名的
   handler** 订阅 `ADJUSTMENT_BATCH_COMMITTED`，SHALL NOT 复用 approved 命名。
   是否保留该行为由设计 §四 裁定并给出理由。
4. THE 修正 SHALL 在归档 spec `disclosure-note-full-revamp` 的勘误登记中说明
   （历史档案 append-only，**不回填修改归档 spec**，勘误写在本 spec 设计 §八）。

---

## 需求 6：试算表调整列按确认态过滤

**用户故事**：作为业务合伙人，我希望只有已确认的调整分录才影响试算表调整列和审定数，
未定稿的草稿不能进正式口径。

### 验收标准

1. THE `recalc_adjustments` SHALL 按 `review_status` 过滤（当前该文件
   `review_status` 出现 **0 次**，即草稿分录已计入 `aje_adjustment`/`rje_adjustment`
   并经 `recalc_audited` 进入 `audited_amount`）。
2. THE 纳入口径 SHALL 由设计 §七 ADR-ADJ-003 明确裁定（候选：仅 `approved` /
   `approved + pending_review` / 排除 `rejected`），并说明会计依据。
   对照既有先例：合并模块 ADR-CONSOL-102 裁定「只认 APPROVED，draft 不进合并数」。
3. WHEN 口径变更后 THEN `check_consistency` 的不变式
   `audited == unadjusted + rje + aje` SHALL 仍然成立（两侧同步过滤即自洽）。
4. WHEN 存在未纳入的分录 THEN 差额 SHALL 在 `trial_balance_full_view_service` 的
   `other_adjustment = audited - unadjusted - aje - rje` 列**可观测**，
   SHALL NOT 静默消失（该列已存在，本需求只要求差异可见）。
5. THE 变更 SHALL 回归全部消费 `aje_adjustment`/`rje_adjustment` 的下游
   （现算清单见设计 §五，含审定表通用规则 `wp_data_rules`「期末调整数 = aje + rje」
   与 `wp_audit_sheet_tb_service` 的 `sys_aje` 系统汇总参考值）。
6. IF 口径变更导致既有测试断言失败 THEN SHALL 逐条判定「是测试固化了错口径」
   还是「实现改错了」，SHALL NOT 直接改断言凑绿（假绿铁律）。

---

## 需求 7：补 ADJ 求值端到端守卫（测试盲区）

**用户故事**：作为维护者，我希望 ADJ 这类「一调用就崩」的缺陷能被测试立刻抓到，
而不是靠人工探针在数月后发现。

### 验收标准

1. THE 测试套件 SHALL 新增**真正执行 `ADJ()` 求值**的用例（当前含 ADJ 字面量的
   测试文件现算 12 个，但**真正调用求值的为 0**；两处 grep 命中 `_resolve_adj_formula`
   经现读均为误报——一处是字符串清单元素、一处是注释）。
2. THE 端到端用例 SHALL 覆盖：AJE 正常取数 · RJE 正常取数 ·
   **AJE 与 RJE 返回值必须不同**（锁死需求 2）· 贷方类科目符号归一 · 无数据返 0。
3. THE 守卫 SHALL 配**双向变异证明**：对同一扫描/断言口径，
   正样本（存在分录）必须命中非零，负样本（无分录）必须为 0，
   SHALL NOT 只做单向断言（单向断言无法区分「取数正确」与「恒空」）。
4. THE `_FORMULA_RESOLVERS` 注册表的**每个** resolver SHALL 有至少一个真实调用用例
   （防同类 lazy-import 缺陷藏在其他 resolver 里）。现算 registry 成员数见设计 §五。
5. THE 新增守卫 SHALL 能在**修复前红、修复后绿**（先写测试见红，再修实现）。
6. WHEN `prefill_formula_mapping.json` 新增 ADJ 预设且第二参不在归一白名单内
   THEN CI SHALL 失败（防占位符/错字面量再次进入）。

---

## 需求 8：确认后下游推送落到用户可见结果

**用户故事**：作为项目组成员，我确认分录后希望审定表、报表审定数、试算表调整列、
分录大厅四处都反映出来，不需要我逐个页面手动点刷新。

### 验收标准

1. WHEN `ADJUSTMENT_APPROVED` 发布 THEN 系统 SHALL 触发试算表调整列 + 审定数重算
   （复用既有 `TrialBalanceService.on_adjustment_changed`，按 `account_codes` 增量）。
2. WHEN 试算表更新 THEN 既有链路 SHALL 自动继续：`TRIAL_BALANCE_UPDATED` →
   `ReportEngine.on_trial_balance_updated` → `REPORTS_UPDATED` → `DisclosureEngine`
   （本需求**不新建**这段，只验证确认门接入后整链贯通）。
3. WHEN 确认发生 THEN 分录大厅 SHALL 收到 SSE 通知（既有
   `_notify_adjustment_event_sse` 目前只订阅 created/updated/deleted，
   是否扩订 approved 由设计 §四 裁定）。
4. THE 底稿 SHALL 按受影响科目标记 stale（既有 `_mark_workpapers_stale_by_account`
   同样只订阅 created/updated/deleted/batch_committed，需评估扩订）。
5. THE 验证 SHALL 有一个**端到端集成测试**：建分录（draft）→ 断言试算表调整列
   按裁定口径**未**变 → 确认（approved）→ 断言调整列与审定数已变 →
   断言 `TRIAL_BALANCE_UPDATED` 已发布（关联属性 **P9**）。
6. IF 整链任一段在真实环境未能实测（需 `start-dev.bat`）THEN SHALL 如实标
   `[ ]*` 并写明「代码已改但未实测」，SHALL NOT 标完成。

---

## 需求覆盖对照（判据 → 需求）

| 设计属性 / ADR | 覆盖需求 |
|---|---|
| P1 import 可解析 | 需求 1 |
| P2 类型归一双向 | 需求 2 |
| P3 非法第二参不静默 | 需求 2 |
| P4 单一取数函数 | 需求 3 |
| P5 三处返回逐值相同 | 需求 3 |
| P6 origin 维度可参数化 | 需求 3 |
| P7 确认门事件存在且落库后发 | 需求 4 |
| P8 重复触发幂等 | 需求 4 |
| P9 端到端整链贯通 | 需求 8 |
| P10 名实相符 | 需求 5 |
| P11 差额可观测 | 需求 6 |
| P12 双向变异守卫 | 需求 7 |
| ADR-ADJ-001 取数收敛位置 | 需求 3 |
| ADR-ADJ-002 公式取数的 origin 口径 | 需求 3 |
| ADR-ADJ-003 调整列纳入的确认态 | 需求 6 |
| ADR-ADJ-004 ADJ 进 L1 内核的收口路径（留待） | 范围外说明 |
| ADR-ADJ-005 rejected/撤回的回退语义 | 需求 4 |
