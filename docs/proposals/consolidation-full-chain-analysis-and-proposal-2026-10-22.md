# 合并模块全链路分析与改进建议

> **日期**：2026-10-22  
> **范围**：合并模块树形构建、四表入库→试算表→底稿→报表→附注全链路、公式推送引擎、前端联动  
> **方法**：基于代码库全量调查（7 项 Task 逐项实证），非推测

---

## 一、全链路架构概览

### 1.1 数据流总图

```
四表入库(tb_balance/tb_ledger)
    │
    ▼ LEDGER_DATASET_ACTIVATED
TrialBalanceService.full_recalc
    │  recalc_unadjusted → trial_balance.unadjusted_amount
    │  recalc_adjustments → rje_adjustment / aje_adjustment
    │  recalc_audited → audited_amount = unadjusted + rje + aje + wp
    │
    ▼ TRIAL_BALANCE_UPDATED
    ├─→ formula_push.engine.run (单体项目)
    │     ├─→ 底稿明细表 (E1-2/E1-3 四表叶子科目行)
    │     ├─→ 底稿审定表 (E1-1 试算平衡表数/大厅调整数)
    │     ├─→ 底稿披露表 (各循环披露表)
    │     └─→ 附注 (按国企/上市 section 推送)
    │
    ├─→ ReportEngine (报表增量重算审定数)
    └─→ stale 标记 (报表/附注标记待更新)
```

```
调整分录审批(AJE/RJE)
    │
    ▼ ADJUSTMENT_APPROVED
adjustment_approved_recalc_handler
    │  recalc_adjustments → TB 调整列
    │  recalc_audited → audited_amount
    │
    ▼ TRIAL_BALANCE_UPDATED
    └─→ (同上全链路)
```

```
审定表发布门(publish_confirmed=True)
    │
    ▼ WORKPAPER_SAVED + publish_confirmed
_on_d_audit_determination_saved
    │  publish_rows → trial_balance.audited_amount
    │
    ▼ TRIAL_BALANCE_UPDATED
    └─→ (同上全链路)
```

```
合并抵销分录审批
    │
    ▼ ELIMINATION_APPROVED
consol_elimination_recalc_handler
    │
    ▼ consol_push_service.push (四步)
    │  ① worksheet: recalc_full → 差额表全节点×科目
    │  ② trial: recalculate_trial → consol_trial 表
    │  ③ report: generate_consol_reports → financial_report 表
    │  ④ notes: _refresh_notes → disclosure_notes 标 stale + 刷新公式
    │
    ▼ SSE: consol.pushed / consol.push_failed
    └─→ 前端自动刷新
```

---

## 二、树形自动构建（现状 ✅ 已实现）

### 2.1 三码推导机制

**数据源**：`projects` 表的 `company_code`、`parent_company_code`、`ultimate_company_code`、`relation_to_parent` 四个字段。

**推导逻辑**（`consol_group_tree.py`）：
- 同审计年度、未删、有企业代码的全部项目作为输入池
- 按企业代码聚合：同代码同年度的 `consolidated` 项目 + `standalone` 项目合为一个 `Entity`
- 按上级代码建立有向边，断环处理（`_break_cycles`）
- 无集内上级的企业按最终控制方挂靠（`_attach_by_ultimate`）

### 2.2 三节点自动生成

有合并项目（`report_scope='consolidated'`）的企业，`_TreeBuilder.consol_node` 一次生成三个节点：

| 节点 | role | kind | 说明 |
|------|------|------|------|
| XX集团（合并） | consol | aggregate | 合并项目，值 = Σ 直接子节点 |
| XX集团（合并差额） | consol_elim | elim | 承载已审批抵销分录 |
| XX集团（母公司） | parent | data/aggregate | 无分公司=单体审定数；有分公司=展开 |

母公司有分公司时，再展开为：

| 节点 | role | kind |
|------|------|------|
| XX集团（母分差额） | branch_elim | elim |
| XX集团（本部） | hq | data |
| 各分公司 | branch | data |

### 2.3 边界处理

- **上级代码 == 本企业代码**：`effective_parent_code` 返回 `None`，不建自环边 ✅
- **三者相等**（三码相同）：该企业是最终控制方，作为树根的合并节点 ✅
- **诊断机制**：`Diagnostic` 覆盖年度无法解析、企业代码空、非合并项目、重复项目、循环断开、脱挂、关系冲突、关系默认、单户缺失、分录孤儿等 12 种情况 ✅

### 2.4 ⚠️ 改进建议

| # | 问题 | 建议 | 优先级 |
|---|------|------|--------|
| T-1 | 项目创建时未自动触发树形构建预览 | 在 wizard 的 `basic_info` 步骤保存后，后端返回 `notices` 中增加「已识别集团关系」预览文案，前端在确认步骤展示树形缩略图（调 `GET /api/projects/tree?year=...&scope=all` 预览） | P2 |
| T-2 | 三码相等时未向用户确认「本企业即为最终控制方」 | 在 `BasicInfoStep` 组件中增加判断：当 `company_code === parent_company_code === ultimate_company_code` 时显示确认提示「本企业为最终控制方（母公司/总部）」，让用户明确确认 | P1 |
| T-3 | 分公司层级递归展开的母公司节点没有自己的合并项目时的数据来源 | 现实现已正确处理：母公司有分公司时 parent 节点为 aggregate（Σ 本部 + 各分公司），本部节点取单体项目审定数，无需修改 | — |

---

## 三、合并工作底稿与差额表联动（现状 ✅ 已实现）

### 3.1 差额表数据源

**唯一来源**：`elimination_entries` 表（ADR-CSP-001）。

差额表是**读时计算**的：每次请求 `GET /api/consolidation/worksheet/report-trial` 或点击「重新推送」时，后端实时从 `elimination_entries`（只取 `review_status='approved'`）+ 各数据叶子的 `trial_balance.audited_amount` 装配 `CalcBasis`，经 `node_values(basis)` 后序计算每个节点逐科目的金额。

### 3.2 五度量恒等式

`node_measures(basis)` 计算五个度量（`consol_calc_basis.py`）：

```
个别数(individual) + 调整(adjustment) + 权益抵销(elim_equity) + 往来交易抵销(elim_trade) = 合并数(consolidated)
```

此恒等式逐节点逐科目成立（P2），由 `CalcBasis` 的分桶累计保证。

### 3.3 合并试算表与差额表的联动

**合并试算表**（`consol_trial` 表）由 `consol_trial_service.recalculate_trial` 持久化：
- `individual_sum` = `aggregate_leaf_amounts()` 汇总全部数据叶子
- `consol_adjustment` = 差额节点「其他调整」类分录净额
- `consol_elimination` = 权益抵销 + 往来交易抵销净额
- `consol_amount` = individual_sum + adjustment + elimination
- `consolidation_breakdown` = JSONB 溯源（by_company 明细 + source_entry_ids）

### 3.4 报表差额表视图

`consol_report_view_service.breakdown_view()`：
- 列 = 汇总节点的直接子节点
- 每列按子节点的 consolidated 度量经 `report_values()` 求值
- 合计列 = 该节点自身的 consolidated 度量
- 线性行满足 Σ 列 = 合计；非线性行只给合计并注明

### 3.5 合并附注差额表

`consol_note_formula_service.note_breakdown()`：
- 与报表差额表同构：对汇总节点的每个子节点分别走 `BasisResolver → report_values()` 管线
- 附注公式引用报表行（如 `ROW('BS-006')`），从报表求值结果取值

### 3.6 ⚠️ 改进建议

| # | 问题 | 建议 | 优先级 |
|---|------|------|--------|
| D-1 | 合并工作底稿的调整抵销分录汇总表目前没有独立的汇总视图 | 在 ConsolWorksheetTabs 中增加「分录汇总表」子标签，调用 `GET /worksheet/summary` 按分录类型（equity/trade/internal_ar_ap/unrealized_profit/other_adjustment）分类汇总，每类显示借方合计、贷方合计、净额，并与差额表五度量对账 | P2 |
| D-2 | 差额表与合并试算表的关系在前端不够直观 | 合并试算表的穿透弹窗已实现（抵销列→分录明细、审定汇总→各节点个别数），但差额表按钮入口不够显眼——建议在合并报表 Tab 的工具栏增加「📊 差额表」快捷按钮直达 breakdown_view | P3 |

---

## 四、四表入库→试算表→底稿→报表→附注链条

### 4.1 链条现状逐段评估

| 段 | 环节 | 代码实现 | 状态 |
|----|------|---------|------|
| A | 四表入库 → LEDGER_DATASET_ACTIVATED | `ledger_import.pipeline` 激活数据集后发事件 | ✅ 已通 |
| B | LEDGER_DATASET_ACTIVATED → TB 重算 | `_auto_map_on_dataset_activated` → `full_recalc` | ✅ 已通 |
| C | TB 重算 → TRIAL_BALANCE_UPDATED | `recalc_audited` 后 `event_bus.publish` | ✅ 已通 |
| D | TRIAL_BALANCE_UPDATED → formula_push 引擎 | `triggers.on_trial_balance_updated` 过滤合并项目后调 `run_and_commit` | ✅ 已通 |
| E | formula_push → 底稿明细表 | E1 明细表由四表叶子科目推送（`E1.cash_rows.four_table` 等规则） | ✅ E1 专用 |
| F | formula_push → 底稿审定表 | balance_adj 类 30 个 binding（K/G/H/I）推送审定表（未审+调整+审定） | ✅ 30 码已覆盖 |
| G | formula_push → 底稿披露表/附注 | 全部 81 个 wp_code 已注册 binding，均有 `note_rows` 附注推送能力 | ✅ 81 码全覆盖 |
| H | formula_push → 附注实际写入 | 附注章节行不存在时 skip；真库已同步 93/1052 = 8.8% | ⚠️ 种子缺失 |
| I | 审定表发布门 → TB writeback → 下游级联 | `publish_confirmed=True` 门控 + 幂等 ack + `TRIAL_BALANCE_UPDATED` | ✅ 已通 |

### 4.2 实际覆盖范围（已实证更正）

🔴 **初版诊断的 C-1「E1 是唯一全自动推送的底稿」是错误的**。经现场核实 `_REGISTRY`，实际注册了 **81 个 wp_code**，D~N 全部循环均已接入公式推送引擎，具备底稿推送 + 附注推送能力：

| binding 类型 | 数量 | 覆盖 | 推送内容 |
|---|---|---|---|
| e1 (专用) | 1 | E1 | 四表叶子 + 审定表 + 附注 |
| k1 (专用) | 1 | K1 | 底稿 + 附注 |
| n3 (专用) | 1 | N3 | 底稿(conclusion列) + 附注 |
| tier_a (单公式锚点) | 7 | D1~D4/D6/D7/I6 | 底稿锚点 + 附注 |
| note_direct (附注直推) | 41 | D5/F/G/J/K8~13/L/M/N | 底稿 + 附注 |
| balance_adj (审定表) | 30 | K2~7/G1~10/H1~10/I1~5 | 审定表(未审+调整+审定) + 附注 |

`TRIAL_BALANCE_UPDATED` 触发后 81 个 wp_code **全部自动推送**，不需要用户手动拉取。

### 4.3 仍需关注的问题

| # | 问题 | 现状 | 建议 |
|---|------|------|------|
| C-2 | **附注真库已同步比例偏低**（93/1052 = 8.8%） | 81 个 binding 都有 `note_rows` 能力，但附注章节须先存在才能写入（`DisclosureNote` 行不存在则 skip） | 确保附注种子（`disclosure_notes` 行）在项目初始化时已生成，否则后端推送无目标行 |
| C-3 | **前端 `pullFromFourTable` 按钮仍存在** | 它与后端 formula_push 的自动推送是**并行路径**而非替代关系；前端按钮可作为手动兜底 | 确认两条路径写入同一字段且不冲突（当前已通过 CAS 版本校验保证） |
| C-4 | **损益类科目取数依赖 tb_ledger** | `recalc_unadjusted` 对 5xxx/6xxx 科目从序时账取发生额，若未导入则 fallback 到 `closing_balance abs` | 导入向导增加完整性校验：损益类有余额但无序时账时 warning |

---

## 五、调整分录确认→审定表/报表/试算表/附注链条

### 5.1 链条现状逐段评估

| 段 | 环节 | 状态 |
|----|------|------|
| A | AJE/RJE 审批 → ADJUSTMENT_APPROVED 事件 | ✅ |
| B | handler → recalc_adjustments (TB 调整列) + recalc_audited | ✅ |
| C | → TRIAL_BALANCE_UPDATED → formula_push (底稿审定表/披露表) | ✅ |
| D | → ReportEngine (报表审定数增量重算) | ✅ |
| E | → stale 标记 (报表/附注) | ✅ |
| F | 调整分录模块大厅实时更新 | ✅ |

### 5.2 调整→TB 的口径严格性

`recalc_adjustments` 只纳入 `review_status='approved'` 且 `origin≠'workpaper'` 的分录（ADR-ADJ-003 + V124 防双计），与 `formula_push.sources.load_hall_adjustments` 同口径。口径一致性由 `test_tb_context_matches_report_engine_including_sub_level_codes` 守卫。

### 5.3 发布门机制

审定表发布到 TB 经显式确认（`publish_confirmed=True`），杜绝普通保存误触 TB 回写。幂等由 `tb_publish_ack` 表的 `ON CONFLICT (publish_token) DO NOTHING` 保证。

### 5.4 ⚠️ 改进建议

| # | 问题 | 建议 | 优先级 |
|---|------|------|--------|
| A-1 | 审定表发布后下游级联是异步的，用户看不到进度 | 发布成功后前端 toast 加上「正在同步报表和附注…」提示，监听 `formula.pushed` SSE 事件后切换为「同步完成」 | P2 |
| A-2 | 底稿调整列 `wp_adjustment` 目前只由审定表发布门写入，其来源追溯不足 | 在试算表详情页增加「审定数构成」展开面板：`未审数 + RJE调整 + AJE调整 + 底稿调整 = 审定数`，每项可穿透到来源分录/底稿 | P3 |

---

## 六、合并模块树形与右侧报表/附注联动

### 6.1 现状

`ConsolidationIndex.vue` 管理 `currentConsolEntity` 状态（`{code, name, nodeKey}`），树节点选中后通过三条路径同步到右侧面板：

1. **集团架构 Tab 内 el-tree 点击** → `onTreeNodeClick` 直接更新状态
2. **中间栏 eventBus `consol-tree-select`** → `onConsolTreeSelect` 按节点类型分发
3. **外部刷新 eventBus `consol-refresh-entity`** → `onConsolRefreshEntity` 强制刷新

右侧面板消费 `currentEntityNodeKey` computed：
- 合并报表：请求带 `node_key` 参数 + 请求卫兵防过期
- 合并试算：ConsolTrialBalanceTab 通过 `selectedNodeKey` prop 同步
- 合并附注：ConsolNoteTab 通过 `currentEntity` prop 传入

### 6.2 ⚠️ 改进建议

| # | 问题 | 建议 | 优先级 |
|---|------|------|--------|
| U-1 | 左侧树形只在「集团架构」Tab 可见，切到其他 Tab 后无法切换企业 | 将企业树从集团架构 Tab 提取为左侧常驻面板（类似底稿模块的左侧导航树），所有 Tab 共享同一棵树，点击节点即切换右侧内容 | P1 |
| U-2 | 差额节点点击后打开分录面板是 overlay，遮挡了右侧报表 | 改为在右侧面板内嵌展示分录列表（类似底稿的行内展开），或改为 Drawer 从右侧滑出 | P2 |
| U-3 | 附注在树节点切换时的刷新逻辑已实现但依赖 ref 调用链 | 当前实现正确（`consolNoteTabRef.value?.onNoteNodeClick`），但若 ConsolNoteTab 未 mount 会静默忽略。建议改为 watch `currentConsolEntity` 在 ConsolNoteTab 内部响应 | P3 |
| U-4 | 合并附注的呈现方式需注意 | 附注按「国企版/上市版」展示，通过 `consolNoteTemplateType` 控制（soe/listed），每棵附注目录树是按当前 templateType 加载的。切换企业节点不影响 templateType，但应在企业的 `applicable_standard_v2` 与当前选择不一致时给出提示 | P2 |

---

## 七、四表库（四维表）显示与修复

### 7.1 四表导入入口

| 入口 | 组件 | 路由 | 状态 |
|------|------|------|------|
| 账套导入（主入口） | LedgerImportPage.vue | `/projects/:pid/ledger-import` | ✅ 四步向导 |
| 旧版数据导入 | DataImportPanel.vue | 无独立路由 | ⚠️ 遗留 |

### 7.2 四表导入后的链路

导入完成 → `LEDGER_DATASET_ACTIVATED` → TB 重算 → `TRIAL_BALANCE_UPDATED` → formula_push → 底稿/报表/附注

### 7.3 四表取数溯源面板

`WpFourTableSourcePanel.vue` 跨循环共用，展示「报表行 → 标准码 → 客户原始码」链路。已知问题：
- absent 态此前整块隐藏（已修复为显式说明）
- 后端两层「取不到数」原因不同（`EMPTY_REASON_NO_ACCOUNT` vs `EMPTY_REASON_NOT_IN_PROJECT`）
- 多槽循环（H3 四槽）需声明 `extraSlotKeys` 否则备抵科目来源不可见

### 7.4 ⚠️ 改进建议

| # | 问题 | 建议 | 优先级 |
|---|------|------|--------|
| F-1 | 四表导入后底稿取数仍需手动点按钮 | 核心改进：`TRIAL_BALANCE_UPDATED` 触发的 formula_push 自动推送到各循环审定表的「试算平衡表数」「大厅调整数」字段，无需用户手动拉取 | P1 |
| F-2 | 科目映射完成但用户未感知 | 科目映射成功后发 SSE 通知（已有 `sync.completed` 通道），前端顶栏提示「科目映射已完成，试算表已重算」 | P3 |
| F-3 | 四表导入页面缺少与合并模块的联动入口 | 合并项目的四表导入完成后，提示用户「建议返回合并模块点击重新推送以更新合并报表」或自动触发 `consol_push` | P2 |

---

## 八、附注推送打通方案（核心改进）

### 8.1 现状问题

| 维度 | 数据 |
|------|------|
| 附注总行数 | 1052 |
| 已由后端同步 | 93 (8.8%) |
| 标为 stale | 378 |
| **后端 binding 有附注推送能力** | **81 个 wp_code 全部有 `note_rows`** |
| 前端 buildXSyncPayload 函数数 | 69 个 |
| 前端推送触发条件 | 用户打开底稿页面时自动防抖推送 |

**根因重新判定**：81 个 binding 全部具备 `note_rows` + stage="note" 规则，`TRIAL_BALANCE_UPDATED` 时理论上都会推附注。已同步比例低（8.8%）的真实原因不是「后端只覆盖 E1」，而是：
1. **附注章节行不存在**：`_push_note` 查 `DisclosureNote` 表找不到目标 section 时 skip（`附注尚未生成「X」章节`）
2. **附注模板类型不匹配**：规则声明的 `sections.soe` / `sections.listed` 与实际项目模板类型不一致时 skip
3. **章节标题不匹配**：`section_title` 与规则期望的表名不一致时 skip（已有动态定位兜底但覆盖不全）
4. **附注表格定位失败**：`note_writer.locate_table` 在旧格式或空 `table_data` 中找不到表时 skip
5. **真库 0 个 consolidated 项目**：合并附注推送完全未在真实数据上跑过

### 8.2 分层打通策略

#### 第一层：解决附注种子缺失（P1 — 根因）

81 个 binding 的附注推送能力已就绪，但推送目标（`disclosure_notes` 行）不存在时引擎直接 skip。核心改进是确保附注行在推送前已存在：

**方案**：四表首次导入激活后 / 项目初始化时，按 template_type（soe/listed）自动生成全部附注章节种子行到 `disclosure_notes` 表，每个 section 一行（含 `note_section`、`section_title`、空 `table_data`），让后续 formula_push 有目标行可写。已有 `_push_note` 中的 `build_main_skeleton` 骨架机制可复用，但它只在推送时按需建骨架——改为提前批量建。

**工作量**：2 天。

#### 第二层：排查并修复附注推送 skip 原因（P1）

在真实 PG 上跑一次 `POST /api/projects/{pid}/formula-push/run`（手动触发），从返回的 `RunResult.items` 中统计 skip 原因分布：

- `附注尚未生成` → 第一层解决
- `章节标题不匹配` → 补齐 `formula_push_rules.json` 中的 section 映射或扩展动态定位
- `附注表格定位失败` → 检查旧格式 `table_data` 结构，必要时迁移为新格式
- `模板类型无对应章节` → 补齐 soe/listed 双版本 section 配置

**工作量**：3 天（含排查 + 修复）。

#### 第三层：前端 buildXSyncPayload 作为补充通道（已有 — 保持）

前端推送覆盖后端推不到的场景（载荷依赖 UI 运行时快照的底稿），权威源裁定不变。两条通道写入同一 `disclosure_notes` 表，CAS 版本校验保证不冲突。

### 8.3 合并模块特有的附注推送

合并附注走独立链路（`consol_push_service._refresh_notes`），不经 formula_push 引擎：
- `_mark_notes_stale()` 标记受影响章节
- `fill_note_sections()` 从 CalcBasis 经报表行级求值填入附注公式值

当前已实现，但受限于 `0 个真实 consolidated 项目`（真库无数据），合并附注推送从未在真实环境验证。

**建议**：使用 `seed_consol_uat.py` 种子脚本构造最小合成集团数据，在真实 PG 上进行一次完整的四步推送验证。

---

## 九、合并模块抵销分录→公式管理→报表/附注差额表链条

### 9.1 当前完整链路

```
用户录入/编辑抵销分录 (elimination_entries)
    │ review_status: draft
    │
    ▼ 用户审批
review_status: approved → ELIMINATION_APPROVED 事件
    │
    ▼ consol_elimination_recalc_handler
    │
    ▼ consol_push_service.push (四步)
    │
    ├──① worksheet: recalc_full
    │     └─ 从 elimination_entries (approved) + 各叶子 trial_balance
    │        装配 CalcBasis → node_values → 差额表全节点×科目
    │
    ├──② trial: recalculate_trial
    │     └─ trial_amounts(basis) → upsert consol_trial
    │        individual_sum / consol_adjustment / consol_elimination / consol_amount
    │
    ├──③ report: generate_consol_reports
    │     └─ 根节点 consolidated 度量 → report_values → upsert financial_report
    │        报表差额表 = breakdown_view (读时计算，列=子节点)
    │
    └──④ notes: _refresh_notes
          └─ fill_note_sections → 附注公式值刷新
             附注差额表 = note_breakdown (读时计算)

SSE: consol.pushed / consol.push_failed → 前端自动刷新
```

### 9.2 ✅ 已打通的环节

- 抵销分录录入/审批 → 差额表重算 ✅
- 差额表 → 合并试算表 ✅
- 差额表 → 合并报表（审定数） ✅
- 差额表 → 合并附注（公式值） ✅
- SSE 推送 → 前端自动刷新 ✅
- 上层合并项目级联推送 ✅

### 9.3 公式管理模块的角色

公式管理（`formula_settings`）是管理公式规则和推送配置的模块：
- **全局设置**：三层有效定义（本项目适配 → 订阅模板 → 全局 → 系统预设）
- **公式推送**面板只读展示 `formula_push_rules.json` 中的规则
- **手动推送**按钮触发 `POST /api/projects/{pid}/formula-push/run`

合并模块的推送不经 formula_push 引擎（走 `consol_push_service`），但两者共享 `CalcBasis` 计算口径。

---

## 十、全链路打通总体改进方案

### 10.1 按优先级排序的改进清单

#### P0（前置条件 — 必须先做）

| # | 改进项 | 涉及文件 | 工作量 |
|---|--------|---------|--------|
| P0-1 | **构造真实合并项目数据**：运行 `seed_consol_uat.py` 在真实 PG 上创建最小合成集团（母公司+2子公司+1分公司），每家导入四表并完成科目映射 | `backend/scripts/seed/seed_consol_uat.py` | 1 天 |
| P0-2 | **端到端 UAT**：在种子数据上走完单体链（四表→TB→底稿→报表→附注）+ 合并链（抵销分录→差额表→合并报表→合并附注），记录每个环节的数据正确性 | 手工验证 | 2 天 |

#### P1（核心打通）

| # | 改进项 | 涉及文件 | 工作量 |
|---|--------|---------|--------|
| P1-1 | **三码确认提示**：三码相等时在 BasicInfoStep 显示「本企业为最终控制方」确认 | `BasicInfoStep.vue` | 0.5 天 |
| P1-2 | **左侧树形常驻面板**：将企业树从集团架构 Tab 提取为左侧常驻面板，所有 Tab 可见 | `ConsolidationIndex.vue` + 新组件 `ConsolSidebar.vue` | 3 天 |
| P1-3 | **附注种子自动生成**：四表首次导入后/项目初始化时批量生成全部附注章节种子行，解决 formula_push 推送因目标行不存在而 skip 的根因 | `disclosure_note_service` + 启动/导入钩子 | 2 天 |
| P1-4 | **附注推送 skip 原因排查与修复**：在真实 PG 上跑手动推送，统计 skip 原因分布并逐类修复（标题不匹配/表格定位失败/模板类型缺配置） | `formula_push_rules.json` + `note_writer` | 3 天 |

#### P2（体验优化）

| # | 改进项 | 涉及文件 | 工作量 |
|---|--------|---------|--------|
| P2-1 | 合并模块分录汇总表视图 | `ConsolWorksheetTabs` 新子标签 | 2 天 |
| P2-2 | 子公司四表导入后自动通知合并项目重新推送 | `consol_push_service.broadcast_stale` 扩展 | 1 天 |
| P2-3 | 企业准则不一致提示（树节点切换时） | `ConsolidationIndex.vue` | 0.5 天 |
| P2-4 | 发布后下游级联进度提示 | 前端 SSE 监听 + toast | 1 天 |
| P2-5 | 四表导入完成后联动合并模块重新推送入口 | `LedgerImportPage.vue` + `consol_push` | 1 天 |

#### P3（改善与守卫）

| # | 改进项 | 涉及文件 | 工作量 |
|---|--------|---------|--------|
| P3-1 | 差额表快捷入口（报表 Tab 工具栏按钮） | `ConsolidationIndex.vue` | 0.5 天 |
| P3-2 | 审定数构成穿透面板（TB 详情页） | `TrialBalanceView` | 2 天 |
| P3-3 | 科目映射完成 SSE 通知 | `auto_account_mapping` | 0.5 天 |
| P3-4 | 合并附注真实 PG UAT 守卫测试 | `test_consol_push_pg.py` | 2 天 |

### 10.2 改进后的目标链路图

```
四表入库 → LEDGER_DATASET_ACTIVATED
    │
    ▼ auto
TB 重算 (unadjusted → adjustments → audited)
    │
    ▼ TRIAL_BALANCE_UPDATED
    ├─→ formula_push 自动推送 (81 个已接入底稿，全部自动)
    │     ├─→ 明细表 (E1 四表叶子科目)                    ← [已完成]
    │     ├─→ 审定表 (30 个 balance_adj 族自动推送)        ← [已完成]
    │     ├─→ 披露表/附注推送能力                          ← [已完成]
    │     └─→ 附注实际写入                                 ← [⚠️ 受种子缺失阻塞]
    │
    ├─→ 报表自动重算                                 ← [已完成]
    └─→ stale 标记                                   ← [已完成]

调整分录审批 → ADJUSTMENT_APPROVED
    │
    ▼ auto
TB 调整列重算 + 审定数重算
    │
    ▼ TRIAL_BALANCE_UPDATED
    └─→ (同上全链路，无需人工干预)

审定表发布 → publish_confirmed
    │
    ▼ 幂等 ack
TB writeback + TRIAL_BALANCE_UPDATED
    └─→ (同上全链路)

合并抵销分录审批 → ELIMINATION_APPROVED
    │
    ▼ auto
四步推送 (差额表 → 合并试算 → 合并报表 → 合并附注)
    │
    ▼ SSE
前端自动刷新 (左侧树形选中企业的报表/附注同步切换)  ← [P1-2 左侧常驻]
```

---

## 十一、实施路线图

### Phase 1（2 周）：数据基础 + 附注种子

1. P0-1：构造合并种子数据
2. P0-2：端到端 UAT，记录每个环节数据
3. P1-1：三码确认提示
4. P1-3：附注种子自动生成（解决推送 skip 根因）

### Phase 2（1.5 周）：附注修复 + 前端改造

5. P1-4：附注推送 skip 原因排查与逐类修复
6. P1-2：左侧树形常驻面板

### Phase 3（1 周）：体验优化

7. P2-1 ~ P2-5：分录汇总/四表联动/准则提示/级联进度/导入联动
8. P3-1 ~ P3-4：差额表入口/审定数穿透/映射通知/PG 守卫

---

## 十二、附录：关键代码文件索引

| 模块 | 文件 | 职责 |
|------|------|------|
| 树形构建 | `backend/app/services/consol_group_tree.py` | 三码推导企业树（纯函数 + 薄装载） |
| 树形服务 | `backend/app/services/consol_tree_service.py` | TreeNode 数据模型 + build_tree/build_tree_view |
| 项目模型 | `backend/app/models/core.py` | Project ORM（三码字段） |
| 合并计算 | `backend/app/services/consol_calc_basis.py` | CalcBasis + node_measures + trial_amounts |
| 报表求值 | `backend/app/services/consol_report_values.py` | BasisResolver + report_values |
| 合并推送 | `backend/app/services/consol_push_service.py` | 四步推送编排（worksheet→trial→report→notes） |
| 分录审批 | `backend/app/services/consol_elimination_recalc_handler.py` | ELIMINATION_APPROVED → push |
| 公式推送 | `backend/app/services/formula_push/engine.py` | 单体底稿/附注推送引擎 |
| 推送触发 | `backend/app/services/formula_push/triggers.py` | 事件→引擎接线 |
| 推送规则 | `backend/data/formula_push_rules.json` | 规则定义 |
| 推送取数 | `backend/app/services/formula_push/sources.py` | TB/ADJ 取数上下文 |
| TB 服务 | `backend/app/services/trial_balance_service.py` | 试算表重算三步 |
| 调整重算 | `backend/app/services/adjustment_approved_recalc_handler.py` | AJE/RJE 审批→TB 重算 |
| 审定表发布 | `backend/app/services/event_handlers_cycle_linkage.py` | 发布门→TB writeback |
| 前端合并页 | `frontend/src/views/ConsolidationIndex.vue` | 五 Tab 布局 + 树联动 |
| 前端企业树 | `frontend/src/composables/useGroupTree.ts` | 树形拉取/搜索/过滤 |
| 前端试算表 | `frontend/src/components/consolidation/ConsolTrialBalanceTab.vue` | 五列 + 穿透 |
| 前端导入 | `frontend/src/views/LedgerImportPage.vue` | 四步导入向导 |
| 合并模型 | `backend/app/models/consolidation_models.py` | ConsolTrial / EliminationEntry ORM |
