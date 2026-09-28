# 需求文档：披露表 → 附注 同步载荷的权威源归属

> 关联设计：#[[file:.kiro/specs/disclosure-payload-authority-source/design.md]]
> 工作流：Design-First。EARS 风格，关联设计 §六 属性 Q1~Q10。
> 类型：**架构决策 + 可靠性补齐**。本 spec 的第一产出是**方案裁定**，不是代码。

## 引言（Introduction）

用户目标链条的末段是「底稿披露表按国企或上市口径推送到附注模块的科目数据」。
调研实证：**能力已齐备，但生产覆盖率低**。

已具备（现读）：
- 后端同步服务 `wp_disclosure_sync_service.sync_from_workpaper` /
  `sync_batch_from_workpaper` / `WpDisclosureSyncService.sync_from_html`
- 国企/上市双模板权威源 `note_template_soe.json` / `note_template_listed.json`
- 跨主体类型守卫 `_guard_standard_matches_project`（拒绝在国企项目写上市章节）
- 前端载荷构造器 `buildXSyncPayload`（现算 **69** 个 export 定义 / 67 个去重名字；🔴 原写 109 是错数，见设计 §十四）
- 前端自动同步 `useDisclosureAutoSync`（单一实现；调用点数**持续漂移** 146 → 144 → 154，**禁写进判据**，见设计 §十四）
- 同步就绪度信号 `GtWpDisclosureSyncBar.vue`

真实库现查：`disclosure_notes` 共 **1052** 行，其中 `last_sync_at IS NOT NULL`
仅 **93** 行（约 8.8%），`is_stale = true` **225** 行。

### 核心矛盾

同步载荷 `sub_table_data` + `sub_table_columns` 由**前端** `buildXSyncPayload`
从各循环 composable 的行模型算出。后端 `WORKPAPER_SAVED` 事件的 `extra` 只有
`{wp_id, wp_code, trigger, item_ids, atomic}`（由 `PUT /api/workpapers/{wp_id}/checklist-responses`
发布，**无 sheet_name、无表结构**）⇒ 后端无法在事件里重建载荷，
只能标 `is_stale`（`disclosure_stale_marker.py`，灰度开关 `DISCLOSURE_AUTO_SYNC_ENABLED`
默认 **false**）。

⇒ **自动同步的能力边界由「载荷计算逻辑住在前端」这一架构事实决定。**
本 spec 要裁定这个归属，而不是绕过它。

### 范围内

三方案 ROI 评估与裁定 · 裁定方案的落地 · 同步可靠性缺陷修复 ·
覆盖率可观测化 · 不变量守卫。

### 范围外（明确不做）

- 不改国企/上市分流逻辑（`_guard_standard_matches_project` 与双模板已正确）
- 不改附注侧写入语义（行级合并 / manual_override 保护 / 乐观锁均已实现）
- 不做 ADJ 取数与调整分录确认门（另立 `adj-formula-repair-and-approval-gate-wiring`）
- 不重构 69 个载荷构造器的**业务内容**（只可能改它们的**宿主位置**）

## 术语（Glossary）

| 术语 | 含义 |
|------|------|
| 载荷 | `sub_table_data` + `sub_table_columns` + `section_id` + `sheet_name` 等同步入参 |
| 载荷构造器 | 前端 `buildXSyncPayload` 系列函数 |
| 权威源 | 载荷计算逻辑的唯一定义位置 |
| 变体 | `listed`（上市）/ `soe`（国企）两套附注口径 |
| 覆盖率 | `disclosure_notes` 中 `last_sync_at` 非空的占比 |
| 现算值 | 交付时脚本重新统计，**禁写死进判据** |

---

## 需求 1：完成三方案 ROI 评估并裁定权威源归属

**用户故事**：作为架构决策者，我需要在动手前知道三条路各自的改动量、风险和收益，
而不是先写代码再发现方向错。

### 验收标准

1. THE 评估 SHALL 覆盖三个方案，每个方案给出：改动文件数（现算）· 双写风险 ·
   前后端漂移风险 · 可自动化程度 · 回归面 · 失败模式。
   - **方案 A 后端重建载荷**：把每循环载荷逻辑在后端重写一遍
   - **方案 B 载荷规则下沉为声明式配置**：从前端唯一真源生成后端可读描述
   - **方案 C 维持前端主导 + 补齐可靠性与可见性**：不迁移逻辑，修同步链缺陷
2. THE 评估 SHALL 引用**已验证先例** `backend/scripts/gen_note_wp_sync_registry.py`
   —— 它已把「附注章节映射」从前端唯一真源 `*NoteSectionMap.ts` 生成为后端只读 JSON。
   评估须回答：该模式能否扩展到载荷**结构**（而非仅章节号）。
3. THE 评估 SHALL 现算规模基数：`buildXSyncPayload` export 定义数 ·
   `syncToDisclosureNotes` 宿主文件数 · `useDisclosureAutoSync` 调用点数。
   🔴 SHALL NOT 引用代码注释中的旧数字（`GtWpDisclosureSyncBar.vue` 文件头写
   「46 个 buildXSyncPayload」，现算为 **69**，**注释已过期**）。
   🔴 **勘误**：本条初版把现算值写成 109，经 120 种口径组合穷举确认无一命中，真值 69（见设计 §十四）。
   ⇒ 本条判据的教训升级为：**「换掉过期数字」时，新数字同样必须可复现，且必须写明口径**。
4. THE 裁定 SHALL 写成 ADR（设计 §七），含「为什么不选另两个」。
5. IF 三方案均不可接受 THEN SHALL 提出方案 D 并同样完成 ROI 评估，
   SHALL NOT 默认选择改动量最小的那个。
6. THE 裁定 SHALL 在动任何生产代码**之前**完成（Design-First）。

---

## 需求 2：修复已知的同步链可靠性缺陷

**用户故事**：作为审计师，我在披露表改完数据后希望它真的同步到附注，
而不是界面提示成功但附注侧 `last_sync_at` 永远为空。

### 验收标准

1. THE `syncToDisclosureNotes` SHALL NOT 在函数体内调用 `useAuditContext()`
   —— 该 composable 内部用 `useRoute()`（`inject`）+ `onScopeDispose()`，
   **必须在 setup 顶层同步调用**，写在函数体内会取不到 `year`。
   （已记录于 `j1DisclosureSyncWiring.spec.ts` 文件头，2026-07-30 浏览器实测
   某项目 `八、40` 的 `_last_sync_at` 一直为 NULL。）
2. THE `syncToDisclosureNotes` SHALL NOT 在自身内部调用
   `scheduleAutoSync(syncToDisclosureNotes)`（= 调度自己 ⇒ 800ms 后自触发重复 POST）。
3. THE 上述两条 SHALL 由守卫覆盖**全部宿主**，而非仅 J1
   —— 宿主数**现算**（编写时 117 个 `syncToDisclosureNotes` 定义文件）。
   现有 `j1DisclosureSyncWiring.spec.ts` 只覆盖 J1 的若干 Tab。
4. WHEN 守卫扫描全部宿主 THEN SHALL 配**双向变异证明**：
   已知正确的宿主必须通过、故意注入缺陷的样本必须失败。
5. WHEN 发现其他宿主存在同类缺陷 THEN 命中数 SHALL 现算登记，逐个修复；
   IF 现算为 0 THEN SHALL 提供变异证明说明扫描器非恒绿。
6. THE 修复 SHALL NOT 改动 69 个载荷构造器的业务内容（只动调用时序与上下文获取）。

---

## 需求 3：同步覆盖率可观测

**用户故事**：作为项目经理，我需要知道本项目哪些披露章节还没同步过，
而不是逐个打开 Tab 看。

### 验收标准

1. THE 系统 SHALL 提供项目级同步覆盖率查询：应同步章节总数 · 已同步数 ·
   过期数 · 从未同步数，按 `wp_code` / 变体分组。
2. THE 「应同步章节」集合 SHALL 派生自 `note_workpaper_sync_registry.json`
   （既有自动生成的只读注册表），SHALL NOT 手工维护第二份清单。
3. WHEN 查询执行 THEN 口径 SHALL 与真实库一致：`last_sync_at` 非空 = 已同步、
   `is_stale = true` = 过期（编写时现查：总 1052 / 已同步 93 / 过期 225，
   **交付时重算**）。
4. THE 覆盖率 SHALL 在前端可见（复用既有 `GtWpDisclosureSyncBar.vue` 的位置或附注侧面板，
   由设计 §四 裁定），SHALL NOT 新建独立页面。
5. IF 某 `wp_code` 在注册表中但项目未启用该底稿 THEN SHALL 排除出分母，
   SHALL NOT 计为「未同步」造成虚假缺口。
6. THE 查询 SHALL 只读，不触发任何同步动作。

---

## 需求 4：灰度开关与降级路径明确

**用户故事**：作为运维者，我需要知道自动同步出问题时怎么退回，以及退回后用户还能怎么做。

### 验收标准

1. THE `DISCLOSURE_AUTO_SYNC_ENABLED` 的**真实作用域** SHALL 在设计中写明
   —— 现读它只管后端兜底标 stale，**不管**前端自动同步（前端已在生产运行，
   不加开关以免回退既有 Tab 行为）。当前默认 `false`，真实引用 3 处（现算）。
2. WHEN 裁定方案引入新开关 THEN SHALL 写明：默认值 · 作用域 · 切换点 ·
   开启前置条件 · 关闭后的用户可用路径。
3. THE 任何自动同步路径 SHALL 保留手动同步按钮作为降级（现已同源幂等，须维持）。
4. IF 自动同步失败 THEN 附注侧 SHALL 至少标 `is_stale`，使用户可见「上游已变更」，
   SHALL NOT 静默失败。
5. THE 失败 SHALL NOT 反向破坏底稿保存（底稿已提交，fail-soft 且**必须留日志**）。

---

## 需求 5：不变量守卫

**用户故事**：作为维护者，我希望这条链上的关键不变量被测试锁死，
不会在下一轮循环 spec 里被悄悄改坏。

### 验收标准

1. 🔴 **本条已勘误（2026-09-28 实施期发现）** —— 原文写「在国企项目上请求上市章节同步
   SHALL 被拒绝且**零写入**」，**该表述与已裁决的设计冲突**。

   现读 `standard_unification_service.detect_standard_conflict` 源码明载：

   > 🔴 用户裁决（2026-08-16）：底稿不做准则门控，允许在国企项目编辑上市版披露
   > （合并模块场景：集团国企，下属有上市子公司）。entity 冲突降级为 warning 放行，
   > 不再 hard block。

   探针穷举 **162** 组 `(project_entity × requested_standard)` 组合，
   `detect_standard_conflict` **恒返回 None** ⇒ `_guard_standard_matches_project`
   内的 `raise StandardMismatchError` 分支是**死代码**。

   **修正后的验收标准**：跨主体同步 SHALL 被**放行**（符合 2026-08-16 裁决），
   但 SHALL NOT 静默 —— 必须产出含 `cross-entity` 的 WARNING 日志，
   使审计场景可事后追溯「谁在国企项目写了上市章节」。
   同主体同步 SHALL NOT 产出该警告（防守卫恒绿）。

   守卫：`test_disclosure_sync_invariants.py::TestCrossEntityGuard`
   —— 含 `xfail(strict=True)` 钉住原始诉求，若实现改回 hard block 则 XPASS 报错，
   强制回来更新本条（不会静默漂移）。
2. THE 空载荷 SHALL NOT 清空既有子表（既有防护，须有守卫锁死）。
3. THE `manual_override` 标记的目标字段 SHALL NOT 被联动写入覆盖。
4. THE 年度解析 SHALL 以 `projects.audit_year` 为权威，SHALL NOT 用服务器当前自然年
   （既有注释明载：2026 年做 2025 年报审计时会把数据写到错误年度，
   审计师在附注模块永远看不到）。
5. THE 注册表 `note_workpaper_sync_registry.json` SHALL 与前端真源一致
   —— CI SHALL 校验「重跑 `gen_note_wp_sync_registry.py` 后文件无 diff」，
   防手工编辑与漂移。
6. THE 守卫 SHALL 覆盖变体维度：同一 `wp_code` 的 `listed` 与 `soe` 章节号不得串写。

---

## 需求覆盖对照（判据 → 需求）

| 设计属性 / ADR | 覆盖需求 |
|---|---|
| Q1 三方案基数现算 | 需求 1 |
| Q2 裁定有 ADR 且含否决理由 | 需求 1 |
| Q3 setup 顶层上下文 | 需求 2 |
| Q4 无自触发 | 需求 2 |
| Q5 守卫覆盖全宿主 + 双向变异 | 需求 2 |
| Q6 覆盖率口径与真实库一致 | 需求 3 |
| Q7 分母排除未启用底稿 | 需求 3 |
| Q8 跨主体零写入 | 需求 5 |
| Q9 空载荷不清表 | 需求 5 |
| Q10 注册表无 diff | 需求 5 |
| ADR-DPA-001 权威源归属裁定 | 需求 1 |
| ADR-DPA-002 覆盖率观测落点 | 需求 3 |
| ADR-DPA-003 灰度开关作用域 | 需求 4 |
