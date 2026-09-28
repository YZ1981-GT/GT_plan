# 设计文档：披露表 → 附注 同步载荷的权威源归属

> 关联需求：#[[file:.kiro/specs/disclosure-payload-authority-source/requirements.md]]
> 工作流：Design-First。类型：架构决策 + 可靠性补齐。
> 与 `adj-formula-repair-and-approval-gate-wiring` 并行无冲突（改动文件零交集，见 §九）。

## §一 现状：能力齐备，覆盖率低

### 已具备（现读实证）

| 部件 | 位置 | 状态 |
|---|---|---|
| 后端同步服务 | `wp_disclosure_sync_service.sync_from_workpaper` / `sync_batch_from_workpaper` / `WpDisclosureSyncService.sync_from_html` | 可用 |
| 国企/上市双模板 | `backend/data/note_template_soe.json` / `note_template_listed.json` | 可用 |
| 跨主体守卫 | `_guard_standard_matches_project`（写前调用，拒绝则零写入） | 可用 |
| 年度权威解析 | `_resolve_target_year`，以 `projects.audit_year` 为准 | 可用 |
| 章节映射注册表 | `note_workpaper_sync_registry.json`（由脚本从前端真源生成） | 可用 |
| 前端载荷构造器 | `buildXSyncPayload` 系列 | 可用 |
| 前端自动同步 | `useDisclosureAutoSync`（单一实现） | 可用但有缺陷 |
| 就绪度信号 | `GtWpDisclosureSyncBar.vue` | 可用 |
| 后端兜底标 stale | `disclosure_stale_marker.py`（开关默认 false） | 可用 |

### 真实库现查

| 指标 | 值 |
|---|---|
| `disclosure_notes` 总行数 | 1052 |
| `last_sync_at IS NOT NULL` | 93（约 8.8%） |
| `is_stale = true` | 225 |

⇒ **不是「零同步」，是「低覆盖」**。`GtWpDisclosureSyncBar.vue` 文件头写的
「46 个 buildXSyncPayload 就绪但生产零同步记录」两个数字**均已过期**
（现算 109 个构造器 / 93 条同步记录）。本设计所有基数一律现算。

### 规模基数（现算，交付时重算）

| 指标 | 编写时现算值 |
|---|---|
| `buildXSyncPayload` export 定义数 | 109 |
| `syncToDisclosureNotes` 定义文件数（宿主） | 117 |
| `useDisclosureAutoSync` 实现文件数 | 1（单一真源） |
| `useDisclosureAutoSync` 调用点数 | 146 |
| 被调用但未见 export 定义的名字 | 1（`buildSyncPayload`） |
| `DISCLOSURE_AUTO_SYNC_ENABLED` 真实引用处 | 3 |

### 核心架构事实

同步载荷 `sub_table_data` + `sub_table_columns` 由前端 `buildXSyncPayload`
从 composable 行模型算出。后端 `WORKPAPER_SAVED` 的 `extra` 只有
`{wp_id, wp_code, trigger, item_ids, atomic}`（`PUT /api/workpapers/{wp_id}/checklist-responses`
发布，无 sheet_name、无表结构）⇒ 后端无法在事件里重建载荷。

---

## §二 决定性技术判断：载荷构造器是纯函数，但签名不统一

**现读实证**：

```ts
// d1NoteSectionMap.ts —— 位置参数形态
export function buildD1SyncPayload(
  variant: D1DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: D1DisclosureSnapshot,
): D1SyncPayload

// l1NoteSectionMap.ts —— 单 options 对象形态
export function buildL1SyncPayload(opts: L1SyncPayloadOptions)
// opts = { variant, categoryRows, categoryTotal, overdueRows, conclusionText }
```

两项结论：

1. ✅ **是纯函数**：入参全为纯数据，函数体内无 Vue 响应式依赖、无 `useRoute()`、无 DOM 访问。
   既有测试可直接调用（`buildD1SyncPayload('listed', 'wp-1', null, snap())`）
   ⇒ **理论上可离屏批量调用**。
2. 🔴 **签名形态不统一**：D1/D2 位置参数、L1 单 options 对象 ⇒
   离屏批量调用需要一层**逐构造器的适配**，成本与构造器数量成正比（现算 109）。

3. 🔴 **snapshot 的装载仍耦合组件**：snapshot 来自各循环 composable 的行模型
   （如 `disc.dataRows.value`），而部分 composable 依赖 `useAuditContext()`
   —— 其内部用 `inject` + `onScopeDispose()`，**必须 setup 顶层同步调用**
   ⇒ 装载层无法直接离屏复用，需先与载荷构造解耦。

⇒ 载荷构造本身可搬，**数据装载不可直接搬**。这是所有方案的成本分界线。

---

## §三 三方案 ROI 评估

### 方案 A：后端重建载荷

| 维度 | 评估 |
|---|---|
| 改动量 | 在后端重写 109 个构造器的等价逻辑 |
| 双写风险 | **必然漂移**：前端改了后端不知道 |
| 可自动化 | 否，逐个手写 |
| 回归面 | 全部披露 Tab |
| 失败模式 | 前后端载荷不一致 ⇒ 附注数据与底稿显示不符，且无人察觉 |

**已被既有代码明确否决**：`disclosure_stale_marker.py` 文件头明载
「要在后端重建载荷就得把每个循环的载荷逻辑双写一遍 → 违反 DRY 且必然漂移」。

**裁定：否决。** 不重复一个已被记录在案的否决结论。

### 方案 B：载荷规则下沉为声明式配置

**思路来源**：`gen_note_wp_sync_registry.py` 已把「附注章节映射」从前端唯一真源
生成为后端只读 JSON，模式已验证。

**为什么对载荷不成立**——两者性质不同：

| | 章节映射（已成功下沉） | 载荷结构（本方案目标） |
|---|---|---|
| 形态 | 字面量常量 `X_NOTE_SECTION = { listed: '五、4', soe: '八、4' }` | **计算结果** |
| 提取方式 | 正则匹配常量声明 | 无法正则提取 |
| 内含逻辑 | 无 | 条件分支 · 聚合 · 按名称合并（缺失侧补 0）· 比率转百分数（`fmtPct` 口径）· 列头按变体逐字措辞差异 · `_removed_table_keys` 清历史表名 · `_note_texts` 只收非空子节 |

载荷是**业务逻辑**而非配置。把它表达成声明式配置等于发明一门 DSL，
再把 109 个构造器翻译进去 —— 成本高于方案 A，且 DSL 表达力不足时必然出现「逃逸钩子」，
退化回双写。

**裁定：否决（技术不可行）。**

🔴 **本方案是我在前序对话中提出的建议，此处撤回。** 撤回依据 = §二 的现读实证：
载荷含计算而非常量，与章节映射不同型。章节映射能下沉恰恰是因为它是字面量。

### 方案 C：维持前端主导 + 补齐可靠性与可见性

| 维度 | 评估 |
|---|---|
| 改动量 | 修同步链缺陷（守卫覆盖现算 117 宿主）+ 新增覆盖率只读查询 |
| 双写风险 | 无（不迁移逻辑） |
| 可自动化 | 守卫可全量扫描 + 双向变异 |
| 回归面 | 同步调用时序与上下文获取，不动载荷内容 |
| 遗留代价 | 自动同步仍需用户**打开过该 Tab**；未打开的章节靠 `is_stale` + 覆盖率面板提示 |

**裁定：采纳为本 spec 范围。**

### 方案 D：离屏批量重放（前端主导 + 批量能力）

**思路**：既然载荷只有前端能算，就让前端在附注侧**按需批量算**
（附注章节 → 经 registry 反查 wp_code → 拉底稿数据 → 调对应构造器 → POST）。

| 维度 | 评估 |
|---|---|
| 可行性 | 载荷构造器是纯函数 ⇒ **可离屏调用**（§二.1） |
| 阻碍 1 | 109 个构造器**签名不统一** ⇒ 需逐个适配层（§二.2） |
| 阻碍 2 | snapshot **装载层耦合组件**（依赖 `useAuditContext` 等）⇒ 需先解耦（§二.3） |
| 前置依赖 | **必须先完成方案 C** —— 否则批量重放会把现有缺陷放大到全部章节 |

**裁定：不纳入本 spec，登记为后续路径（ADR-DPA-001 §后续）。**

理由：在可靠性缺陷未修、覆盖率不可观测的前提下引入批量重放，
等于在不知道当前哪里错的情况下把动作放大 109 倍。
方案 C 同时是 D 的前置条件与效果度量手段。

### 四方案对照

| | A 后端重建 | B 声明式下沉 | **C 前端主导+补齐** | D 离屏批量 |
|---|---|---|---|---|
| 技术可行 | 是 | **否** | 是 | 是 |
| 双写漂移 | 必然 | 必然（逃逸钩子） | 无 | 无 |
| 改动量 | 极大 | 极大 | **小** | 中 |
| 解决「未打开 Tab 不同步」 | 是 | 是 | **否** | 是 |
| 裁定 | 否决 | 否决 | **采纳** | 后续 |

---

## §四 方案 C 落地设计

### 组件 1：同步链缺陷全量守卫

**位置**：`audit-platform/frontend/src/components/workpaper/__tests__/disclosureSyncWiringAll.spec.ts`
（现有 `j1DisclosureSyncWiring.spec.ts` 只覆盖 J1 若干 Tab，本组件扩到全部宿主）

**两条不变量**（均源自 j1 spec 已记录的实测缺陷）：

1. `syncToDisclosureNotes` 函数体内**不得**出现 `useAuditContext`
   —— 该 composable 用 `inject` + `onScopeDispose()`，必须 setup 顶层同步调用；
   写在函数体内取不到 `year`（2026-07-30 浏览器实测某项目 `八、40` 的
   `_last_sync_at` 一直 NULL）。
2. `syncToDisclosureNotes` 函数体内**不得**调用 `scheduleAutoSync(syncToDisclosureNotes)`
   —— 调度自己 ⇒ 800ms 后自触发重复 POST。

**扫描口径**：宿主集合现算（编写时 117 个定义 `syncToDisclosureNotes` 的文件），
禁写死清单；**双向变异**——已修正的宿主必过、注入缺陷的样本必败。

### 组件 2：覆盖率只读查询

**后端**：新增只读端点，返回按 `wp_code` × 变体分组的
`{expected, synced, stale, never_synced}`。

- 「应同步」分母派生自 `note_workpaper_sync_registry.json`（禁手工第二份清单）
- 分母**排除项目未启用的底稿**（否则虚假缺口），启用判定走 `wp_index`
- 口径：`last_sync_at` 非空 = 已同步；`is_stale = true` = 过期
- 纯只读，不触发同步

**前端**：复用既有 `GtWpDisclosureSyncBar.vue` 的展示位 + 附注侧汇总面板，
**不新建独立页面**（功能收敛铁律）。

### 组件 3：注册表一致性 CI

重跑 `gen_note_wp_sync_registry.py --write` 后 JSON 无 diff，
防手工编辑与前后端漂移。该脚本文件头记录的两个正则陷阱须在守卫注释中保留引用：
不锚定 `const/let/var` 声明会让注释里的常量名咬到下一语句；
不用 `(?![\w])` 收尾会被 `X_NOTE_SECTION_DISPLAY` 覆盖（实测 H10 曾把
`八、75` 写成 `八、75 资产处置收益`）。

---

## §五 保持不动的既有不变量（只加守卫，不改实现）

| 不变量 | 现有实现 | 守卫要求 |
|---|---|---|
| 跨主体拒绝且零写入 | `_guard_standard_matches_project` 在任何写语句前调用 | Q8 |
| 空载荷不清既有子表 | 两条同步路径均已防护 | Q9 |
| `manual_override` 不被联动覆盖 | `conflict_resolution_service` 前置 hook | 需求 5.3 |
| 年度以 `projects.audit_year` 为权威 | `_resolve_target_year`；`_derive_year` 仅兜底 | 需求 5.4 |
| 变体章节号不串写 | `listed`/`soe` 各自章节号 | Q6 |
| 底稿保存不被同步失败反向破坏 | fail-soft 且必须留日志 | 需求 4.5 |

---

## §六 属性（Properties）

> PBT 一律 `max_examples=5`。

- **Q1 基数现算**：三方案评估引用的规模数字均由脚本现算，不引用代码注释旧值
  （反例：`GtWpDisclosureSyncBar.vue` 的「46 个」现算为 109）。
- **Q2 裁定有 ADR 且含否决理由**：A/B/D 三个未采纳方案各有明确否决/延后依据。
- **Q3 setup 顶层上下文**：全部宿主的 `syncToDisclosureNotes` 体内无 `useAuditContext`。
- **Q4 无自触发**：全部宿主的 `syncToDisclosureNotes` 体内无 `scheduleAutoSync(自身)`。
- **Q5 守卫覆盖全宿主 + 双向变异**：宿主集合现算；注入缺陷样本必败、正确样本必过。
- **Q6 覆盖率口径与真实库一致**：查询结果与直接 SQL 统计逐值相等。
- **Q7 分母排除未启用底稿**：项目未启用的 `wp_code` 不计入分母。
- **Q8 跨主体零写入**：国企项目请求上市章节 → 拒绝且 DB 无任何变更。
- **Q9 空载荷不清表**：空 `sub_table_data` 同步后既有子表内容不变。
- **Q10 注册表无 diff**：重跑生成脚本后文件字节一致。

---

## §七 架构决策记录（ADR）

### ADR-DPA-001：载荷权威源留在前端，本轮补可靠性而非迁移逻辑

**状态**：已接受

**决策**：采纳方案 C。载荷计算逻辑**继续住在前端** `buildXSyncPayload`，
后端维持「接收载荷 + 校验 + 写入」职责，不重建载荷。

**否决 A**：双写必然漂移，且该结论已由 `disclosure_stale_marker.py` 文件头记录在案。

**否决 B**：载荷是计算不是常量（§三 对照表），声明式化等于发明 DSL；
章节映射能下沉恰因其为字面量。**此方案为前序对话中我本人的建议，据现读实证撤回。**

**延后 D**：技术可行（构造器是纯函数）但需 109 个签名适配 + 装载层解耦，
且必须以方案 C 为前置，否则放大未知缺陷。

**代价（诚实记录）**：方案 C **不解决**「用户没打开过披露 Tab 就不会同步」。
缓解 = `is_stale` 标记 + 覆盖率面板让缺口可见可追。彻底解决须走方案 D。

### ADR-DPA-002：覆盖率观测复用既有展示位，不新建页面

**状态**：已接受

**决策**：覆盖率数据落在既有 `GtWpDisclosureSyncBar.vue` 展示位 + 附注侧汇总面板。

**理由**：平台已处功能收敛期（停加新功能，核心页做到极致）；
同步就绪度信号已有落点，再建页面会分散注意力且增加维护面。

### ADR-DPA-003：`DISCLOSURE_AUTO_SYNC_ENABLED` 作用域澄清，本轮不改默认值

**状态**：已接受

**背景**：现读该开关**只管后端兜底标 stale**，不管前端自动同步
（前端已在生产运行，刻意不加开关以免回退既有 Tab 行为）。默认 `false`，真实引用 3 处。

**决策**：本轮**不改默认值**，只在文档与代码注释中澄清作用域，
并把「开启前置条件」写明：组件 1 守卫全绿 + 覆盖率查询上线。

**理由**：开关名字听起来管整个自动同步，实际只管兜底路径。
在覆盖率不可观测前贸然开启，无法判断是改善还是制造噪声。

---

## §八 归档 spec 关系（append-only，不回填）

| 归档 spec | 关系 |
|---|---|
| `_archive/08-disclosure-notes/disclosure-sync-path-buildout`（58/58） | 建成同步路径；本 spec 补其可靠性与可观测 |
| `_archive/08-disclosure-notes/disclosure-table-sync-convergence`（45/45） | 同步收敛；本 spec 不改其收敛结论 |
| `_archive/08-disclosure-notes/soe-listed-note-conversion-correctness`（19/19） | 国企/上市转换正确性；本 spec 只加守卫不改逻辑 |
| `_archive/08-disclosure-notes/disclosure-note-follow-actual-content`（74/74） | 产出 `disclosure_stale_marker.py`；本 spec 沿用其「只标 stale」裁定并澄清开关作用域 |
| `_archive/08-disclosure-notes/disclosure-note-row-level-merge`（15/15） | 行级合并；属本 spec 的不动不变量 |

**待核实的疑似残留**：active 目录存在 `workpaper-page-formula-toolbar-closure`
（现扫 0/0、三件套不全），归档存在同名 17/17。本 spec 在 INDEX 登记时一并核实，
若确为残留空壳则登记说明（**不擅自删除历史目录**）。

---

## §九 风险

| # | 风险 | 缓解 |
|---|---|---|
| S1 | 全量守卫一上就大面积红（117 宿主里可能多数有缺陷 1/2） | 先只扫不改跑一次得**现算命中数**，按数量决定是否拆批修 |
| S2 | 覆盖率分母口径错 ⇒ 面板显示虚假缺口，比没有更糟 | Q6/Q7 双守卫：与直接 SQL 逐值对账 + 排除未启用底稿 |
| S3 | 修 `useAuditContext` 调用位置引入新的响应式时序问题 | 逐宿主改 + 既有 j1 守卫作回归基线 |
| S4 | 与 `adj-formula-repair-and-approval-gate-wiring` 冲突 | 改动文件零交集：本 spec 动前端披露 Tab 宿主 + 新增只读端点 + `disclosure_stale_marker` 注释；对方动 `prefill_engine`/`trial_balance_service`/`wp_cross_check_service`/`adjustment_service`/`EventType`。唯一潜在接触面 `event_handlers/_impl.py`：对方改 approved 订阅源，本 spec **不动该文件** |
| S5 | 新增只读端点未注册 router_registry ⇒ 前端 404 | tasks 显式含注册任务 + FastAPI 不热加载须重启 |
| S6 | 方案 C 不解决根本问题，用户预期落差 | ADR-DPA-001 已诚实记录代价；覆盖率面板使剩余缺口可量化，为方案 D 立项提供依据 |

---

## §十 交付前自查清单

- [ ] 每条需求至少被某 task 引用（判据引用闭合性，非仅编号连续）
- [ ] 每条属性 Q1~Q10 至少被某 task 引用
- [ ] 每条 ADR-DPA-001~003 至少被某 task 引用
- [ ] 所有计数标「现算 + 禁写死」，无写死行号、无写死宿主清单
- [ ] 所有「结构性零」断言配双向变异证明（Q5）
- [ ] 新增端点已在 `backend/app/router_registry/` 注册
- [ ] 探针文件已删（`backend/scripts/analyze/_adj*` 与本 spec 新增探针）
- [ ] 真实环境未实测项如实标 `[ ]*` + 「代码已改但未实测」措辞
- [ ] INDEX.md 登记（CRLF 安全写入 + 每行恰 4 个未转义 pipe 校验）
