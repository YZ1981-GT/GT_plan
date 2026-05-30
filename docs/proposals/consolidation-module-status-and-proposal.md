# 合并模块现状分析与开发建议

- **日期**：2026-05-30
- **作者**：Kiro（代码实证调研，非凭印象）
- **方法**：fileSearch + grepSearch + readFile 实证全部资产，标注"已接线 / 孤儿 / mock 数据 / 外部阻塞"
- **状态**：调研报告 + 建议（非实施 spec，落地需立三件套）

---

## 〇、执行摘要（TL;DR — 合伙人决断，其余是论据）

**一句话**：合并模块"骨架健全、核心管线断裂、关键操作无留痕、无项目级权限、且无真实客户数据"——**当前不可用于正式合并报告**。

**5 层隐患**（详见各章）：
- **A 工程**：公式引擎复制旧 eval / 死代码挂在路由 / sync-async 混用 / 缺编排者
- **B 会计**：🔴 individual_sum 子公司加总无实现路径（合并第一步就断）/ worksheet 与 trial 两套计算未对账 / 🔴 **负商誉处理违反 CAS 20（编造"25% 阈值+递延摊销"逻辑）** / 🔴 **不支持同一控制下企业合并（整类计算路径缺失，国企版刚需）** / 少数股东持股比例字段语义两处不一致
- **W 工作底稿**：🔴 三套数据模型并行互不连通（差额表引擎 / 15 张致同底稿 JSON blob / consol_trial）——**用户填的 15 张底稿不参与任何合并计算**，正确的差额表引擎被架空
- **C 基础设施**：🔴 合并表从未进 D6 迁移（无 schema 演进能力）/ 编排者源码被删剩 pyc / 锁定 bug 对 drift detector 隐形
- **P 合伙人**：🔴 关键操作零审计留痕（违 CAS 1131）/ 🔴 无项目级权限（子公司间数据越权）/ 签字快照空壳 / 从未端到端跑通

**决断（投资建议）**：
1. **不投全力做完**——无真实合并客户数据（PG 0 个 consolidated），Phase 4 验收卡死，做完只能合成自测，ROI 低
2. **但 Phase 0 必须做（~3 人天止血防误用）**：①B1/B2/C1 通核心管线 ②P1 审计留痕（合规红线）③P5 项目级权限（数据隔离红线）④P3 标"开发中不可用"防团队误用 ⑤C3 consol_lock 进 ORM+迁移
3. **Phase 1-3 待真实集团客户立项再做**（届时 Phase 4 数据就位，一气呵成）
4. **优先级低于**当前天天在用的核心模块（WorkpaperEditor/List 瘦身、6000 并发、LLM 接入）

**为什么是 Phase 0 而非全做**：合并是"有客户才用"的高端业务，当前无真实合并客户。在无真实需求数据时做完整开发 = 为不存在的需求过度投资。Phase 0 的价值是**止血（让合并数逻辑成立）+ 合规（留痕+权限）+ 防误用（标记）**，用最小代价消除"团队误用错误合并数出报告"的风险，把弹药留给有真实需求的地方。

---

## 一、结论速览

合并模块**不是"没开发"，而是"三层完成度断层"**：

| 层次 | 完成度 | 说明 |
|------|--------|------|
| **数据模型层** | ✅ ~95% | ORM 表齐全（Company/ConsolScope/抵销/内部交易/组成部分审计师/合并试算/合并底稿）|
| **算法/服务层** | ✅ ~85% | 15+ consol service 实装，纯函数算法有单测覆盖 |
| **报表合并主链** | ⚠️ ~50% | 引擎/抵销/穿透接线在，但 **individual_sum 子公司加总无写入路径（B1）→ 合并数实际不成立**；且 trial/worksheet 两套计算未对账（B2）|
| **附注合并（D8/D12）** | ⚠️ ~40% | 核心 V2 函数**孤儿**（写了没接线）+ 章节映射是 mock 数据 |
| **三级穿透（合并→单体→底稿）** | ❌ ~10% | 仅 README stub，字段/端点/组件全缺 |
| **真实数据验收** | ❌ 0% | PG 0 个 consolidated 项目，无母子真实数据（外部阻塞）|

**一句话**：报表合并**看起来能跑实则合并第一步（子公司加总 individual_sum）就没实现**——consol_amount 实际只算了抵销额丢了子公司本体；附注合并是半成品（关键代码孤立 + mock 数据）；三级穿透没动；且存在两套未对账的并行计算模型。**这不是"补功能"，是"合并核心算法链路从未端到端跑通"** + 上层一堆孤儿/死代码。所有真实验收还卡在没有合并母子数据。

> ⚠️ **headline 修正（深入读代码后）**：初判"报表合并 ~80% 能跑"过于乐观——`recalculate_trial` 的 `individual_sum`（各子公司加总）无任何写入路径（B1），意味着合并数 = 仅抵销额，**合并报表根本不成立**。真实完成度更接近"积木齐全但核心管线断裂"。

---

## 一-B、用户新增 3 诉求现状（2026-05-30 代码实证）

> 用户诉求：①项目是合并时自动在合并模块生成树形 ②前端一键刷新把树形下报表/附注数值更新 ③合并用户对单体项目锁定，锁定后单体数据无法修改。
> **实证结论：积木都在，但散、缺编排、缺自动触发、锁定覆盖窄。**

### 诉求 ①：合并项目自动生成树形 — ⚠️ 半（有按需拉取，无自动触发）
- ✅ 已有 `GET /api/consolidation/worksheet/tree`（consol_worksheet.py → consol_tree_service.build_tree，从 projects.parent_project_id 递归 BFS 建树）
- ✅ 前端 ConsolidationIndex.vue「集团架构树」Tab 已渲染 org-node 树
- ❌ **缺自动触发**：树是前端打开 Tab 时按需 pull，不是"项目标记为 consolidated（report_scope=consolidated / consol_level>1）时自动生成/初始化"
- ❌ **缺关联校验**：建树纯靠 parent_project_id，但项目创建/wizard 时未强制建立母子关系，也无"该合并项目下应挂哪些单体"的配置入口

### 诉求 ②：一键刷新树形下报表+附注 — ⚠️ 散（多个独立 recalc，无级联编排）
现有独立刷新端点（各自为政）：
- `POST /api/consolidation/worksheet/recalc`（合并底稿全量重算 recalc_full）
- `POST /api/consolidation/trial/recalculate`（合并试算表重算）
- `POST /api/consolidation/notes/{pid}/{year}/reaggregate`（附注重新汇总，靠 mock CSV）
- `POST /api/consol-note-sections/refresh/{pid}/{year}/{section_id}`（单章节公式刷新）
- ❌ **缺统一编排**：没有"一键刷新整棵树"的级联编排端点——应 = 遍历树节点 → 各单体取最新审定数 → worksheet 重算 → trial 重算 → report 重算 → notes 重汇总，按依赖顺序一次跑完 + 进度反馈（SSE）
- ❌ 前端缺"一键刷新"总按钮（现有刷新按钮是各 Tab 局部）

### 诉求 ③：单体项目锁定 — ⚠️ 代码框架在但**实际不可用**（缺 DB 列，运行时静默失效）
- ✅ **后端代码已写**：`ConsolLockService`（consol_enhanced_service.py）lock/unlock/check_lock，UPDATE projects.consol_lock + consol_lock_by + consol_lock_at
- ✅ **路由已接线**：`POST /api/consolidation/{pid}/lock` + `/unlock` + `/lock-status`（report_trace.py）
- ✅ **强制依赖已建**：`check_consol_lock`（deps.py）设计为锁定时返回 **HTTP 423**
- ❌ **致命缺口：`consol_lock` 列不存在**——grep 实证 ORM Project 模型（core.py）**无 consol_lock 字段** + `backend/migrations/*.sql` **无任何添加该列的迁移**。后果：
  - `lock_project` 的 `UPDATE projects SET consol_lock=true` 运行时会因列不存在**失败**
  - `check_consol_lock` 的 try/except SAVEPOINT 容错（注释明写"Column may not exist"）会让 SELECT 失败时**静默 pass** → 锁定检查永远放行
  - **净效果：锁定功能当前是装饰性的，实际锁不住任何东西**
- ⚠️ **强制覆盖窄**（即使补了列）：仅 `trial_balance.py`（1 端点）+ `adjustments.py`（4 端点）挂了 `check_consol_lock`；底稿/附注/序时账/报表写端点未挂
- ❌ **缺前端**：树节点"锁定/解锁"操作 + 锁定态 banner

### 诉求落地建议（并入主路线阶段 A/B）
| 诉求 | 后端工作 | 前端工作 |
|------|---------|---------|
| ① 自动建树 | wizard/项目创建 + scope 变更时，若 consolidated 则校验/初始化母子关系 + 触发建树缓存 | 合并项目入口自动展示树 + 母子关系配置 UI |
| ② 一键刷新 | 新建级联编排端点 `POST /api/consolidation/{pid}/{year}/refresh-all`（树遍历 + 按依赖顺序 recalc worksheet→trial→report→notes + SSE 进度）| 树顶部"一键刷新"按钮 + 进度条 |
| ③ 锁定 | **①先补 V0XX 迁移加 consol_lock/consol_lock_by/consol_lock_at 列（幂等）+ ORM Project 模型同步**（三层一致校验铁律）②`check_consol_lock` 扩展到底稿/附注/序时账/报表全部写端点（grep 全写端点批量挂）③去掉静默 pass 容错（列存在后应让真实错误暴露）| 树节点锁定/解锁按钮 + 锁定态 banner + canEdit 禁用 |

> ⚠️ **诉求 ③ 是"看起来做了实际没生效"的典型**——符合 memory「三层一致校验铁律：DB 迁移 + ORM Mapped[] + service 方法，任一缺失即伪绿」，此处 DB 列 + ORM 双缺失，service 写了也白写。


---

## 二、已就绪资产（代码实证）

### 2.1 数据模型（backend/app/models/consolidation_models.py）
- `Company` / `ConsolScope`（合并范围）/ 抵销分录 / 内部交易 / 往来对账 / 组成部分审计师 / 审计意见
- 11 个枚举（ConsolMethod / ScopeCompanyType / EliminationEntryType / TradeType 等）
- `Project.parent_project_id`（nullable）+ `Project.consol_level`（default=1）— core.py:84/87 实证存在

### 2.2 服务层（15+ consol service，全部实装）
| service | 职责 | 接线状态 |
|---------|------|---------|
| `consol_tree_service` | 企业树构建（build_tree/find_node/get_descendants）| ✅ 被多处调用 |
| `consol_worksheet_engine` | 合并底稿全量重算（recalc_full + 批量加载优化）| ✅ |
| `consol_trial_service` | 合并试算表（借贷平衡校验）| ✅ |
| `consol_scope_service` | 合并范围 CRUD + summary | ✅ |
| `consol_report_service` | 合并报表生成（1100+ 行，最大）| ✅ |
| `consol_pivot_service` | 透视查询 + Excel 导出 + 模板 | ✅ |
| `consol_drilldown_service` | TB 级三向穿透（企业/抵销/末端试算）| ✅ 接 consol_worksheet 路由 |
| `consol_elimination_rules` | 4 类预设抵销规则 + wp_code 校验 | ✅ |
| `consol_note_aggregation_service` | 附注章节聚合（5 种方法 + 模糊合并 + DAG 校验）| ⚠️ 接 reaggregate 路由但靠 mock 映射 |
| `consol_disclosure_service` | 合并附注生成（1267 行）| ⚠️ 老版接线，V2 孤儿 |
| `consol_cross_template_service` | 跨模板章节翻译（国企↔上市）| ❌ **孤儿**（0 router 引用，仅文件内部互调）|
| `consol_note_stale_handler` | 子公司附注变更 → 合并 stale | ✅ EventBus 注册 |

### 2.3 路由（已注册 §6 合并报表组，router_registry/system.py）
`consolidation` / `consol_scope` / `consol_trial` / `internal_trade` / `component_auditor` / `goodwill` / `forex` / `minority_interest` / `consol_notes` / `consol_report` / `consol_worksheet` / `consol_worksheet_data` / `consol_note_sections` / `consol_cell_comments` — 14 个 router 全部 include。

### 2.4 前端（已实装）
- `ConsolidationIndex.vue`（多 Tab：合并工作底稿 / 集团架构树 / 试算平衡表 / 合并报表）
- `ConsolSnapshots.vue`（合并数据快照）
- `ConsolWorksheetTabs` / `ConsolTrialBalanceTab` / `ConsolCatalog.vue`（章节树）/ `ConsolNoteTab.vue`（附注编辑，含"重新汇总"按钮）
- `ConsolNoteTreeEnhanced.vue`（附注树增强）

---

## 三、关键缺口（代码实证，按严重度排序）

### 缺口 1：附注合并 V2 核心函数是孤儿 ⚠️ 高
- `generate_full_consol_notes`（consol_disclosure_service.py:792）是 D8「合并附注完整开发」的核心——7 步骤消费子公司单体附注汇总。
- **grep 实证：0 个 router/调用方引用**，只在自己文件里定义。
- 实际接线的 `consol_notes.py` 路由 `create_consol_notes` / `get_consol_notes` 调的是**老版** `generate_consol_notes_sync`——只生成 7 个合并专用章节（合并范围/商誉/少数股东等），**完全不消费子公司单体附注**。
- 后果：前端点"生成合并附注"拿到的是骨架章节，不是真正从子公司汇总的数据。
- **同类孤儿**：`consol_cross_template_service`（D14 国企↔上市跨模板共存，3 个 API）也是 0 router 引用，仅文件内部互调——写了没接线。

### 缺口 2：章节映射是 mock 数据 ⚠️ 高
- `backend/data/consol_note_section_mapping.csv` 头部明确标 `# is_mock=true ... 等 P-5 真数据`。
- 23 条单体→合并章节映射 + 抵销规则，是简化占位，等审计师提供真实映射。
- `aggregate_section` / `reaggregate` 路由依赖此 CSV，mock 数据下汇总结果不可用于真实底稿。

### 缺口 3：三级穿透（合并→单体→底稿）几乎未动 ❌ 高
（对应 active stub `consol-note-three-level-drilldown`）
- `disclosure_notes` 缺 `source_project_id` / `consolidation_breakdown` JSONB 字段（grep 0 命中）
- 缺端点 `GET /api/notes/{section}/consol-breakdown`（grep 0 命中）
- 缺 `note_consol_drilldown_service`（不存在）
- 缺前端 `ConsolBreakdownDialog.vue`（不存在）+ DisclosureEditor 右键"查看合并明细"（grep 0 命中）
- 注：**TB 级穿透已有**（consol_drilldown_service），缺的是**附注级**穿透。

### 缺口 4：真实合并母子项目数据缺失 ❌ 阻塞性（外部）
- 文档记录 PG 5 项目全单体，0 个走 consolidated 模式（本次 Docker 未运行无法实时复核，沿用最近实测）。
- 后果：即使把上述代码补齐，也**无法 UAT 验收**——没有真实母子公司数据跑端到端。
- 候选数据：重庆医药集团多家子公司已存在，建立 parent_project_id 关系即可（README 记录）。

### 缺口 5：测试只到算法层，无端到端 ⚠️ 中
- `test_consol_note_aggregation.py` 等是纯函数单测（aggregate_cell / fuzzy_merge / DAG），合成数据，全绿。
- **缺真实子公司 → 合并的端到端集成测试**（依赖缺口 4 的数据）。

### 缺口 6：合并↔单体项目联动不完整 ⚠️ 高（用户 2026-05-30 明确诉求）

> 用户核心诉求：合并项目与单体项目应是**双向感知、自动联动**的关系，不是两个孤立模块。

**已有联动（代码实证）**：
| 联动点 | 现状 | 实证 |
|--------|------|------|
| 母子关系数据模型 | ✅ | `Project.parent_project_id`（core.py:84）+ `consol_level`（core.py:87）|
| 企业树构建 | ✅ 按需 | `consol_tree_service.build_tree` 从 parent_project_id BFS 递归 |
| 附注 stale 传播 | ✅ | `consol_note_stale_handler` 订阅 NOTE_UPDATED → 递归向上 `_find_consol_parents` → `mark_consol_sections_stale` |
| 程序裁剪批量下发 | ✅ | `procedure_service.batch_apply(parent_project_id, cycle, target_ids)` 从母项目方案批量应用到子公司 |
| 共享配置集团可见性 | ✅ | `shared_config_service` group 模板按 parent_project_id 判断同集团可见 |
| 连续审计继承母子关系 | ✅ | `continuous_audit_service` 创建下年项目时 `parent_project_id=prior.parent_project_id` |
| 前端项目列表树形展示 | ✅ | `MiddleProjectList.vue` 按 parent_project_id 构建树 + `FourColumnCatalog.vue` 分组 |
| 合并 Hub 入口 | ✅ | `ConsolidationHub.vue` 过滤 report_scope=consolidated 项目 |
| 仪表盘集团进度 | ✅ | `ManagementDashboard.vue` 集团审计进度图 + `dashboard_service` 子公司进度对比 |

**缺失联动（grep 实证 0 命中）**：
| 缺失联动 | 影响 | 说明 |
|----------|------|------|
| **单体项目感知"我被合并锁定"** | 单体用户不知道自己被锁 | 无 banner/toast 提示"本项目已被合并项目 XXX 锁定"；`check_consol_lock` 返回 423 但前端无对应 UI 处理 |
| **合并项目创建时自动初始化母子关系** | 用户需手动建关系 | wizard 设 report_scope=consolidated 后不自动弹出"选择子公司"配置；consol_scope 需手动添加 |
| **单体数据变更→合并自动刷新** | 合并数据过时 | stale 传播只标记"过时"，不自动触发重算；用户需手动点各 Tab 的刷新按钮 |
| **一键级联刷新（树遍历）** | 操作碎片化 | 无统一编排端点，worksheet/trial/report/notes 各自独立 recalc |
| **锁定覆盖全写端点** | 锁了等于没锁 | 仅 TB+adjustments 5 端点挂 check_consol_lock；底稿/附注/序时账/报表写端点未挂 |
| **consol_lock DB 列不存在** | 锁定功能运行时失效 | ORM 无字段 + 无迁移 → lock_project SQL 失败 → check_consol_lock 静默 pass |
| **单体项目→合并项目快速跳转** | 导航断裂 | 单体项目 UI 无"查看所属合并项目"入口 |
| **合并项目→单体项目快速跳转** | 导航断裂 | 树节点点击只显示信息卡，无"进入该单体项目"直接路由 |
| **子公司数据完整度检查** | 合并前无校验 | 无"子公司 TB 是否已审定 / 附注是否已生成"的前置校验，直接合并可能拿到空数据 |
| **合并范围变更→自动重建树** | 手动刷新 | consol_scope 增删子公司后树不自动更新 |

**联动设计建议（补入阶段 A/B）**：

1. **锁定闭环**（阶段 A 最高优先）：
   - 补 V0XX 迁移加 `consol_lock` / `consol_lock_by` / `consol_lock_at` 三列
   - ORM Project 模型同步加 `Mapped[bool]` + `Mapped[UUID|None]` + `Mapped[datetime|None]`
   - `check_consol_lock` 去掉静默 pass（列存在后应暴露真实错误）
   - 批量挂到全部写端点（grep `@router.post|put|delete` + `require_project_access("edit")` 的端点全加）
   - 前端：单体项目检测 `consol_lock=true` 时显示 `ConsolLockedBanner`（类似 ArchivedBanner），禁用编辑按钮

2. **一键级联刷新**（阶段 A）：
   - 新建 `consol_cascade_refresh_service.py`：
     ```
     async def refresh_all(db, parent_project_id, year):
       tree = await build_tree(db, parent_project_id)
       # 1. 遍历叶子节点→根节点（自底向上）
       # 2. 每个节点：recalc_full(worksheet) → recalculate_trial → 
       # 3. 根节点：generate_consol_report → reaggregate_notes
       # 4. 返回 {nodes_refreshed, errors, duration}
     ```
   - 路由 `POST /api/consolidation/{pid}/{year}/refresh-all`
   - 前端：ConsolidationIndex 顶部"🔄 一键刷新全部"按钮 + SSE 进度条

3. **自动建树 + 合并范围联动**（阶段 B）：
   - wizard 完成时若 report_scope=consolidated → 自动弹出"配置合并范围"步骤（选择已有单体项目挂为子公司）
   - consol_scope 增删子公司 → EventBus 发 `CONSOL_SCOPE_CHANGED` → 自动重建树缓存
   - 前端 ConsolidationIndex 监听 scope 变更自动刷新树

4. **双向导航**（阶段 B）：
   - 单体项目 header 显示"所属集团：XXX"链接 → 点击跳转合并项目
   - 合并项目树节点"进入项目"按钮 → 路由到该单体项目
   - 合并项目列表中单体项目显示"🔒 已锁定"标签

5. **子公司数据完整度前置校验**（阶段 B）：
   - 一键刷新前检查：各子公司 TB 是否有审定数（audited_amount 非全 0）+ 附注是否已生成
   - 不满足时提示"子公司 XXX 数据不完整，合并结果可能不准确"（warning 不阻断）

---

## 四、建议路线（分三阶段，按依赖与可启动性排序）

### 阶段 A：先做"不依赖真实数据"的接线收尾（纯工程，可立即启动）
**目标**：消除孤儿代码 + 锁定闭环 + 一键刷新，让合并模块真正可用。
1. **锁定闭环**（最高优先，1 人天）：
   - V0XX 迁移加 `consol_lock BOOLEAN DEFAULT false` / `consol_lock_by UUID` / `consol_lock_at TIMESTAMPTZ` 到 projects 表
   - ORM Project 模型同步 3 字段
   - `check_consol_lock` 去掉静默 pass + 批量挂到全部写端点（底稿/附注/序时账/报表）
   - 前端 `ConsolLockedBanner.vue`（单体项目检测锁定态显示）
2. **一键级联刷新**（1 人天）：
   - `consol_cascade_refresh_service.py`（树遍历 → worksheet → trial → report → notes 按依赖顺序）
   - `POST /api/consolidation/{pid}/{year}/refresh-all` + SSE 进度
   - 前端"一键刷新全部"按钮 + 进度条
3. **V2 附注接线**（0.5 人天）：
   - `generate_full_consol_notes` 接入 consol_notes.py 路由（feature flag 切换新/老版）
   - `consol_cross_template_service` 接入 reaggregate 路径
4. **附注级穿透后端**（1 人天）：
   - 迁移 V0XX：`disclosure_notes` 加 `source_project_id` / `consolidation_breakdown` JSONB
   - 新建 `note_consol_drilldown_service` + `GET /api/notes/{section_id}/consol-breakdown`
5. **集成测试骨架**（0.5 人天）：合成母子数据 mock 端到端链路验证
- **阶段 A 合计**：~4 人天，纯后端+少量前端 banner，无外部依赖。

### 阶段 B：前端联动 + 穿透 UI + 自动建树（依赖阶段 A 后端）
1. **穿透 UI**（1 人天）：
   - `ConsolBreakdownDialog.vue`——合并行右键"查看合并明细"→ 列出 N 家子公司金额 → 点击跳转
   - `DisclosureEditor.vue` / `ConsolNoteTab.vue` 右键菜单加"查看合并明细"项
   - `linkage_graph_builder` 加合并 NOTE → 单体 NOTE 父子边
2. **双向导航**（0.5 人天）：
   - 单体项目 header 显示"所属集团：XXX"链接 → 跳转合并项目
   - 合并项目树节点"进入项目"按钮 → 路由到单体项目
   - 合并项目列表中锁定的单体项目显示"🔒"标签
3. **自动建树 + 合并范围联动**（1 人天）：
   - wizard 完成时若 report_scope=consolidated → 自动弹出"配置合并范围"步骤
   - consol_scope 增删子公司 → EventBus `CONSOL_SCOPE_CHANGED` → 自动重建树
   - 前端 ConsolidationIndex 监听 scope 变更自动刷新
4. **子公司数据完整度前置校验**（0.5 人天）：
   - 一键刷新前检查各子公司 TB 审定数 + 附注生成状态
   - 不满足时 warning 提示（不阻断）
- **阶段 B 合计**：~3 人天，纯前端+少量后端 EventBus。

### 阶段 C：真实数据准备 + 端到端 UAT（外部阻塞解除后）
1. 把重庆医药集团子公司挂到一个合并母项目下（建 parent_project_id 关系）。
2. 审计师提供真实章节映射替换 mock CSV（P-5）+ 列语义标注（P-1）。
3. 真实跑 `generate_full_consol_notes` → 验证 7 合并章节 + 子公司汇总数据正确。
4. UAT-1~5（合并附注列表 / 右键明细 / 跳转 / 穿透链路 / 依赖图父子边）。
5. **工作量估**：3-4 人天 + 审计师 1-2 人天（外部）。

### 优先级建议
- **可立即启动**：阶段 A（接线收尾最有价值——消除"写了没用"的孤儿代码，ROI 高）
- **紧随其后**：阶段 B（前端穿透，用户 2026-05-17 明确诉求）
- **等外部**：阶段 C（卡真实数据 + 审计师，不可控）

---

## 四-B、架构级专业建议（现场负责人视角，代码实证发现的根本性隐患）

> 上面是"缺什么"，这里是"现有实现有什么根本性问题"——这些不修，补再多功能都是在腐化的地基上加楼。

### A1：合并公式引擎复制了单体的旧 `eval()` 实现 — 🔴 严重（安全 + 语义双重隐患）
- **实证**：`report_engine.py`（Phase 1 主引擎）已把公式求值重构为 `_safe_eval_expr`（基于 `ast.parse` 递归求值，支持 ABS/IF/比较运算，**禁用 eval**）；但 `consol_report_service._execute_formula`（合并引擎）**仍用裸 `eval(safe_expr, {"__builtins__": {}}, {})`**，且只支持 `+−×÷()`。
- **双重问题**：
  1. **安全**：虽有 regex 白名单 `^[\d\.\+\-\*\/\(\)\s]+$` 兜底，但 eval 始终是反模式（memory「彻底解决不绕开」），主引擎已证明 ast 方案可行
  2. **语义不一致**：单体报表公式支持 ABS()/IF()，合并报表不支持 → **同一张报表的单体版和合并版，公式行为可能不同**，这是审计数据准确性的硬伤
- **根因**：合并模块 Phase 2 起步时复制了 Phase 1 的旧公式逻辑，之后 Phase 1 重构了 eval，合并这边没跟进 → 典型"复制粘贴 + 各自演进"腐化
- **建议**：合并引擎**复用** `report_engine` 的公式解析器（注入不同数据源 resolver 即可），删除 `consol_report_service` 内重复的 `_execute_formula`/`_resolve_*`/`_extract_account_codes`。这是"根本解决"，不是打补丁。

### A2：数据源切换靠"复制整个引擎"而非"注入数据源" — 🟠 设计债
- **实证**：合并报表 = "复用 Phase 1 Report_Engine，数据源从 trial_balance 切到 consol_trial.consol_amount"，但实现方式是**整个 ConsolReportService 重写一遍 generate/execute/resolve**，而非把"数据源"抽象为可注入的 resolver。
- **后果**：Phase 1 报表引擎每次改进（新公式函数、新校验），合并引擎都要手动同步，长期必然漂移（A1 就是已发生的漂移）。
- **建议**：抽象 `AmountResolver` 接口（`resolve_tb(account, year)` / `resolve_sum(range, year)`），`report_engine` 接受注入。单体注入 `TrialBalanceResolver`，合并注入 `ConsolTrialResolver`。一套引擎两个数据源，消除重复。

### A3：sync/async 混用 — 🟠 一致性隐患
- **实证**：`ConsolReportService.__init__(self, db: AsyncSession)` 声明 async session，但方法体内用 `self.db.query(...).filter(...).all()`（**同步 Session API**），且有 `generate_consol_reports_sync` / `verify_balance_sync` / `generate_consol_workpaper_sync` / `generate_consol_notes_sync` 一组 sync 包装。
- **后果**：async session 上调 sync query 在 SQLAlchemy 2.0 下行为依赖 greenlet，易触发 `MissingGreenlet`（memory 已记录类似 F6 事故）；sync/async 双轨增加维护面。
- **建议**：统一为 async（`await self.db.execute(select(...))`），sync 包装仅在确需同步上下文（如 worker）保留并用 `run_sync` 桥接。

### A4：锁定/外部导入服务有"写了就崩"的死代码 — 🔴 严重
- **实证**：`consol_enhanced_service.ExternalReportImportService.import_external_report(self, db, project_id, data)` 方法体内引用 `self.db`（签名是 `db` 参数不是 self.db）、`kwargs`、`year`、`company_code`、`file_content` **全部未定义** → 一调用必抛 `AttributeError`/`NameError`。
- **配合 consol_lock 列不存在**（前述）→ 这个 service 的 lock + import 两大功能**实际都跑不通**，是"看起来实现了"的空壳。
- **建议**：①ExternalReportImportService 要么修复签名+参数（kwargs→显式参数），要么标记 stub 不接线；②lock 先补列（前述）。**不能让崩溃代码挂在已注册路由上**（report_trace.py 已 include）。

### A5：合并是"全量重算"而非"增量" — 🟡 性能（6000 并发目标下的隐患）
- **实证**：`consol_worksheet_engine.recalc_full` 是全量重算（虽有批量加载优化 `_batch_load_*`）；一键刷新若级联全树全量重算，大集团（几十家子公司 × 几千科目）单次刷新可能数十秒。
- **后果**：与项目"6000 并发"目标冲突；同步端点会阻塞 asyncpg pool（memory 已记录 SSE+轮询打爆 pool 的事故）。
- **建议**：①一键刷新走**后台 worker + SSE 进度**（不占请求连接）②中期考虑增量重算（只重算 stale 标记的节点/科目，stale 传播已有基础设施可复用）。

### A6：合并模块缺统一编排者（Orchestrator）— 🟠 架构缺位
- **实证**：有 `consolidation_orchestrator`（pyc 存在）但合并的"建树→取数→worksheet→trial→report→notes"全链路没有一个统一编排入口，散在各 router。
- **后果**：用户"一键刷新"诉求本质是要这个编排者；缺它导致前端要手动按顺序点 4 个刷新按钮，且无法保证依赖顺序正确（notes 依赖 report 依赖 trial 依赖 worksheet）。
- **建议**：新建 `consol_cascade_refresh_service` 作为唯一编排者，定义清晰的 DAG 执行顺序 + 失败隔离 + 进度上报（阶段 A 已列）。

### 架构建议优先级
| # | 问题 | 严重度 | 修复时机 |
|---|------|--------|---------|
| A4 | 锁定/导入死代码 | 🔴 | 阶段 A 立即（配合 consol_lock 列）|
| A1 | 合并公式 eval + 语义不一致 | 🔴 | 阶段 A（接线 V2 时顺手统一）|
| A6 | 缺编排者 | 🟠 | 阶段 A（一键刷新即编排者）|
| A2 | 引擎复制非注入 | 🟠 | 阶段 A/B（与 A1 一起做）|
| A3 | sync/async 混用 | 🟠 | 阶段 B（重构时统一）|
| A5 | 全量重算性能 | 🟡 | 阶段 C 后（真实数据压测暴露后再优化）|

> **现场负责人判断**：A1+A4 必须在"加新功能前"先修——它们是已经在腐化/已经崩溃的地基。A2/A6 是趁这次合并模块攻坚一并理顺架构的最佳时机（否则下次还要重来）。A5 留到有真实大集团数据压测后再做，避免过早优化。

---

## 四-C、审计专业正确性 + 数据一致性建议（更深一层，最易被忽视）

> 前面 A 系列是"工程质量"，这一层是"会计逻辑对不对 + 数据可不可信"——审计软件这一层错了，前面做得再漂亮都是错的合并数。

### B1：合并试算表 `individual_sum` 没有自动汇总路径 — 🔴 严重（合并的第一步就断了）
- **实证**：`consol_trial.consol_amount = individual_sum + consol_adjustment + consol_elimination`（recalculate_trial），但：
  - `individual_sum`（各子公司同科目加总）只有 server_default=0，**全仓 grep 无任何代码写入它**
  - 唯一的 `upsert_trial_row` 只设 account_name/category，**不设 individual_sum**
  - → `recalculate_trial` 实际算出 `consol_amount = 0 + 0 + elimination`，**合并数 = 仅抵销额，丢了所有子公司本体数据**
- **会计后果**：这是合并的最基础步骤（"先加总各子公司，再抵销"），加总这一步缺失 = 合并报表根本不成立。
- **建议**：`recalculate_trial` 必须先遍历企业树各子公司的 trial_balance.audited_amount，按 standard_account_code 加总写入 individual_sum，再叠加 adjustment/elimination。这是 cascade_refresh 编排者的核心一步。

### B2：两套并行的合并计算模型未对账 — 🔴 严重（数据可信度）
- **实证**：存在**两条独立的合并计算路径**：
  - 路径 1：`consol_trial`（individual_sum + adjustment + elimination → consol_amount）→ 喂给 `consol_report_service` 出报表
  - 路径 2：`consol_worksheet` + `consol_worksheet_engine.recalc_full`（_calc_node 按企业树逐节点算 → ConsolWorksheet）→ 喂给 pivot/drilldown
- **问题**：两条路径各算各的，**没有任何对账校验**确保它们结果一致。报表用路径 1、穿透用路径 2 → 用户在报表看到的数和穿透下钻看到的数可能对不上。
- **建议**：①明确单一事实源（建议以 worksheet 树形计算为准，trial 作为其投影）②或加对账校验（两路径结果 diff > 容差则告警）③长期应合并为一条计算管线。

### B3：抵销分录全靠手工录入，无自动生成内部交易抵销 — 🟠 专业完整性
- **实证**：`recalculate_trial` 只消费 `EliminationEntry`（review_status=APPROVED 的已录入抵销），`consol_elimination_rules` 有 4 类预设规则（internal_ar/revenue/inventory/dividend）但 `calculate_elimination_amount` 实证是从 child_projects 按规则算——**但这套规则未接入 recalculate_trial 主链**（trial 只读已录入的 EliminationEntry，不调 elimination_rules 自动生成）。
- **会计后果**：内部往来/内部交易/未实现利润抵销全靠审计师手工录入 EliminationEntry，自动化的 elimination_rules 是孤立的。大集团内部交易上百笔，纯手工不现实。
- **建议**：`auto_generate_eliminations` 端点（consolidation.py 已有）应接入 elimination_rules，从子公司内部交易数据自动生成抵销分录草稿（标 draft，审计师复核后 APPROVED）。

### B4：少数股东权益 / 商誉计算与试算表脱节 — 🟠 待核实但高风险
- **实证**：`consol_report_service` import 了 GoodwillCalc/MinorityInterest + get_goodwill_list/get_mi_list，报表层会读；但 `recalculate_trial` 的 consol_amount 公式里**没有 MI/商誉项**——它们是报表层另外加的"合并特有行次"。
- **风险**：少数股东权益既影响试算平衡（贷方权益）又影响报表行次，两处分别处理易不平。verify_balance 是否把 MI/商誉纳入平衡校验需核实（本次未深入 verify_balance 实现）。
- **建议**：明确 MI/商誉在"试算表层"还是"报表层"处理，统一口径，verify_balance 校验时确保两边一致。

### B5：跨年合并（上年数）链路未验证 — 🟡
- **实证**：`_execute_formula(..., is_prior=True)` 用 `query_year = year - 1` 读上年 consol_trial。但若上年合并未跑过（consol_trial 上年无数据），上年数全为 0。
- **建议**：连续审计场景下，合并项目的上年数应从上年合并结果结转（continuous_audit_service 已结转单体，需确认是否结转合并层）。

### B6：负商誉处理违反 CAS 20 — 🔴 会计准则错误（审计软件最不能错）
- **实证**：`goodwill_service.calculate_goodwill` 的负商誉处理：
  ```python
  treatment = "计入损益" if abs(goodwill) < acquisition_cost * 0.25 else "递延收益摊销"
  ```
- **准则错误**：CAS 20《企业合并》规定，负商誉（合并成本 < 享有可辨认净资产公允价值份额）经复核后**全额计入当期损益（营业外收入）**——**没有"递延收益摊销"，更没有"25% 阈值"判断**。这是**编造的会计逻辑**（"递延收益摊销"是旧准则/早期 IFRS 做法，现行 CAS 已废止）。商誉计算公式本身（成本−可辨认净资产FV×母持股比例）是对的，错的是负商誉的后续处理分支。
- **风险**：审计软件出具的商誉处理建议违反现行准则，签字合伙人若采信会出错。
- **建议**：删除 25% 阈值 + 递延摊销分支，负商誉统一"计入当期损益"，并提示审计师"需复核合并成本与可辨认净资产公允价值的计量"。

### B7：少数股东持股比例字段语义在两处不一致 — 🟠 计算口径 bug
- **实证**：`minority_interest_service.calculate_mi` 把 `minority_share_ratio` 当**少数股东比例**直接用（`minority_equity = net_assets * ratio/100`，正确）；但 `consol_disclosure_service` 里 `minority_ratio = (1 - mi.minority_share_ratio or 1) * 100`——把同一字段当**母公司持股比例**求补数。
- **风险**：同一个 `minority_share_ratio` 字段，一处理解为"少数股东%"、一处理解为"母公司%"→ 附注展示的少数股东持股比例可能算反（如母 80% 子 20%，附注可能显示 80%）。
- **建议**：统一字段语义（建议明确为"少数股东持股比例"），修正 consol_disclosure_service 的补数逻辑，加单测锁定口径。

### B8：不支持"同一控制下企业合并"——整类合并业务计算路径缺失 — 🔴 会计覆盖面硬缺口
- **背景**：CAS 20《企业合并》分两类，会计处理截然不同：
  | 维度 | 非同一控制（购买法）| 同一控制（类似权益结合法）|
  |------|------|------|
  | 净资产计量 | 公允价值 | **账面价值** |
  | 商誉 | 产生商誉 | **不产生商誉**（对价差额调资本公积，不足冲留存收益）|
  | 合并时点 | 购买日起合并 | **视同自最终控制方控制之日一直是一体** |
  | 比较报表 | 不追溯 | **追溯调整上年比较数** |
- **实证**：系统**只实现了非同一控制（购买法）路径**，同一控制完全缺失：
  - 披露层：附注模板有"同一控制/非同一控制企业合并"章节（note_soe_listed_diff / note_template_bindings）+ 关联方有 `is_controlled_by_same_party` 字段——**但只是文字/表格披露占位，不参与计算**
  - 计算层 🔴：`ConsolScope`/`Company` 模型**无 `combination_type` 字段**（无法区分子公司是哪类合并）；`consol_worksheet_engine` 只一套逻辑无同一控制分支；`EliminationEntryType`（equity/internal_trade/internal_ar_ap/unrealized_profit/other）**无同一控制特有的资本公积/留存收益调整类型**；`GoodwillCalc` 是购买法专属，**无"同一控制不算商誉"拦截**
- **后果**：若对同一控制合并用现有引擎跑，会**错误算出商誉**（同一控制根本不该有）、**不做追溯调整**、**对价差额无处入资本公积**——出具的合并报表违反 CAS 20。
- **业务影响**：同一控制合并在**国企集团内部重组**中极其常见（本系统主打国企版！），这个缺口直接影响核心目标客户群。
- **建议**：①`ConsolScope` 加 `combination_type`（同一控制/非同一控制）字段 ②计算引擎按类型分支：同一控制走账面价值 + 资本公积调整 + 追溯，非同一控制走现有购买法 ③抵销枚举补同一控制调整类型 ④同一控制时拦截商誉计算。**这是大工作量（不是补字段，是补一整套会计处理路径），但对国企客户是刚需**。

> **现场负责人加注（B6+B8 会计正确性）**：B6（负商誉算错）+ B8（同一控制缺失）共同说明——**合并模块的会计覆盖只做了"非同一控制购买法"的一半，且那一半还有准则错误**。B8 比 B6 严重得多：B6 是一个分支算错（改几行），B8 是整类合并业务（同一控制）的计算路径完全没有。对一个**主打国企版**的审计系统，缺同一控制合并是核心能力缺失。**强烈建议：合并所有会计计算路径请懂 CAS 20/33 的审计专业人员逐一过一遍准则符合性**——这类缺口/错误纯靠读代码发现不了，必须懂准则的人核。


> **现场负责人加注（会计正确性）**：B6 是整个调研里**唯一的"会计准则硬错误"**——前面 A/B1-5/C/W 都是"没接通/没实现/架构差"，B6 是"实现了但算错/建议错"。审计软件的会计逻辑错误比"功能没做"更危险（功能没做用户知道不能用，逻辑错了用户会采信错误结果）。**B6/B7 应在 Phase 0-1 优先修，且合并所有会计计算（商誉/少数股东/未实现利润抵销/权益法）都应请审计专业逐一复核准则符合性**——这类错误代码 review 看不出来，必须懂准则的人核。


### B 系列优先级
| # | 问题 | 严重度 | 时机 |
|---|------|--------|------|
| B1 | individual_sum 无汇总路径（合并第一步断） | 🔴 | 阶段 A（cascade_refresh 必含）|
| B2 | 两套计算模型未对账 | 🔴 | 阶段 A（定单一事实源）|
| B3 | 抵销全手工，自动规则孤立 | 🟠 | 阶段 B（接入 auto_generate）|
| B4 | MI/商誉与试算表脱节 | 🟠 | 阶段 A/B（先核 verify_balance）|
| B5 | 跨年合并上年数结转 | 🟡 | 阶段 C（连续审计场景）|
| B6 | 负商誉处理违反 CAS 20（编造逻辑）| 🔴 | Phase 0-1（会计准则硬错误）|
| B7 | 少数股东持股比例字段语义两处不一致 | 🟠 | Phase 0-1（加单测锁口径）|
| B8 | 不支持同一控制下企业合并（整类缺失，国企刚需）| 🔴 | 独立大模块（需审计专业 + 大工作量）|

> **现场负责人判断**：B1+B2 比前面所有 A 系列都更致命——A 系列是"代码质量差但可能还能跑出数"，B1 是"合并第一步加总就没实现，跑出来的就是错的"。**强烈建议阶段 A 第一件事就是把 individual_sum 自动汇总 + 单一事实源对账做掉**，否则一键刷新刷出来的是错误合并数，比不刷新更危险（用户会信任错误数据）。这也解释了为什么"PG 0 个 consolidated 项目"——可能不只是没数据，是这条链路从未真正端到端跑通过。



## 四-D、合并模块内部衔接专项建议（用户点名的 4 块）

> 逐块读代码后的具体改进——这些是合并模块"内部齿轮怎么咬合"的问题。

### 衔接 1：合并工作底稿（ConsolWorksheet）— 引擎对，但孤立于报表
- **现状实证**：`consol_worksheet_engine._calc_node` 是**真正正确的合并引擎**——后序遍历企业树，叶子节点取 trial_balance.audited_amount，中间节点 = Σ(子节点 consolidated_amount) + 抵销 + 调整，根节点 consolidated_amount = 最终合并数。算法是对的。
- **核心问题**：worksheet 算出的正确合并数**没有任何桥接回 consol_trial**（grep 实证：consolidated_amount 只被 pivot/drilldown/triple_format_adapter 读，从不写入 consol_trial.consol_amount）。而报表服务读的是 consol_trial（individual_sum=0 的空表）。
- **改进建议**：
  1. **确立 worksheet 为单一合并事实源**——report_service 直接从 ConsolWorksheet.consolidated_amount（根节点）取数出报表，废弃 consol_trial 的独立计算
  2. 或：recalc_full 末尾把根节点结果**回写** consol_trial.consol_amount（trial 退化为 worksheet 的投影，供报表/校验复用）
  3. 前端合并工作底稿支持：科目行点击 → 展开该科目在各子公司的明细（worksheet 已有 node_company_code 维度数据，缺前端下钻 UI）

### 衔接 2：抵销分录 → 试算平衡表 — 双路径不一致 🔴
- **现状实证**：抵销分录被**两处各自消费**：
  - worksheet 引擎：`_get_elimination_map` 按 related_company_codes 关联到节点，进 _calc_node 的 elim_debit/credit（**消费全部 EliminationEntry，不分审批状态**）
  - trial 服务：`recalculate_trial` 只消费 `review_status == APPROVED` 的 EliminationEntry
- **问题**：同一批抵销分录，worksheet 用全部、trial 只用已审批 → **两路径抵销口径都不一致**（叠加 B1/B2，结果必然对不上）
- **改进建议**：
  1. 统一抵销消费口径（建议都只认 APPROVED，draft 不进合并数）
  2. 抵销分录录入后 → EventBus 触发 worksheet + trial 增量重算（现在改抵销分录不自动重算）
  3. `auto_generate_eliminations`（已有端点）接入 `consol_elimination_rules`，从子公司内部往来/交易自动生成抵销草稿（B3），审计师审批后入合并数
  4. 抵销分录页提供"抵销影响预览"——录入前看到该分录对合并报表哪些行次的影响

### 衔接 3：与上年数据的衔接 — 几乎空白 🟠
- **现状实证**：
  - 报表层 `_execute_formula(is_prior=True)` 读 `consol_trial(year-1)`——但上年若没跑过合并，consol_trial 上年表为空 → 上年数全 0
  - worksheet/notes 层**完全没有上年数概念**（recalc_full 只算当年）
  - `continuous_audit_service` 创建下年项目时继承了 parent_project_id/consol_level，但**没有结转上年合并结果**（只结转单体 TB）
- **问题**：合并报表"本年/上年"两列，上年列实际取不到数；附注变动分析（本年vs上年）在合并层无数据基础
- **改进建议**：
  1. 连续审计创建合并项目下年时，把上年 ConsolWorksheet/consol_trial/合并附注**结转为下年期初/上年对比数**
  2. 或：上年数实时从"上年合并项目"的合并结果拉取（需上年合并项目存在且已跑）
  3. 明确合并上年数的来源策略（结转 vs 实时拉取），写入 ADR
  4. 跨年抵销分录的连续性（上年抵销对本年期初的影响，如未实现利润在本年实现的转回）——审计专业要求，当前完全缺失

### 衔接 4：合并附注/报表右键查看汇总明细 — 后端缺字段端点，前端缺组件 🔴
- **现状实证**：
  - TB 级穿透有（consol_drilldown_service：drill_to_companies/eliminations/trial_balance，接 consol_worksheet 路由）
  - **附注级 + 报表级穿透全缺**：`consolidation_breakdown`/`source_project_id` 字段 0 命中、`consol-breakdown` 端点 0 命中、`ConsolBreakdownDialog.vue` 不存在、右键"查看合并明细"0 命中
- **改进建议**（分报表/附注两条）：
  1. **报表右键**：合并报表某行 → 右键"查看汇总明细" → 调 ConsolWorksheet（已有 node_company_code 明细）展示该报表行对应科目在各子公司的金额 + 抵销额 → 点子公司金额跳转该单体报表。**报表穿透可立即做**（worksheet 数据已在，只缺端点+UI）
  2. **附注右键**：合并附注某行 → 右键"查看合并明细" → 需先有 consolidation_breakdown 字段（记录该合并行由哪些子公司哪些章节汇总而来）→ 这依赖 B1 的汇总过程同时写 provenance
  3. **统一穿透组件**：`ConsolBreakdownDialog.vue` 同时服务报表和附注（props 区分 source=report|note），列出 N 家子公司金额 + 占比 + 抵销 + 跳转链接
  4. **provenance 是关键**：合并汇总（B1）时必须同步记录每个合并值的来源明细（哪些子公司贡献多少），否则事后无法反查——建议 individual_sum 汇总时同时写 consolidation_breakdown JSONB

### 衔接专项优先级
| 衔接块 | 关键改进 | 严重度 | 时机 |
|--------|---------|--------|------|
| 1 工作底稿→报表 | worksheet 作单一事实源 / 回写 trial | 🔴 | Phase 0（与 B1/B2 一体）|
| 2 抵销→试算 | 统一口径 + 自动生成 + 事件重算 | 🔴 | Phase 0-2 |
| 4 报表右键穿透 | worksheet 数据已在，补端点+UI 可先做 | 🟠 | Phase 2-3 |
| 4 附注右键穿透 | 依赖 B1 写 provenance | 🟠 | Phase 2-3 |
| 3 上年衔接 | 结转策略 + ADR | 🟡 | Phase 3-4 |

> **现场负责人判断**：衔接 1+2 与 B1/B2 是同一个根问题的不同切面——**合并模块有两套计算（worksheet 对、trial 空），必须先并成一套**，这是 Phase 0 的核心。衔接 4 的报表穿透因为 worksheet 明细数据已存在，是"低垂的果实"可早做出彩；附注穿透和 provenance 要等 B1 汇总链路建好。衔接 3 上年数是审计专业硬需求但不阻塞当年合并，放后面。

---

## 四-G、合并工作底稿专项深挖（用户重点关注）

> 合并工作底稿是合并的"操作台"，逐组件读代码后发现**最严重的结构问题：三套数据模型互不连通**。

### W1：合并工作底稿存在三套互不连通的数据模型 — 🔴 最严重结构问题
逐层读代码后实证，"合并底稿"在系统里其实是**三个独立、互不喂数的数据世界**：

| # | 数据模型 | 存什么 | 谁写 | 谁读 |
|---|---------|--------|------|------|
| 模型 1 | `ConsolWorksheet` 表（node×account×year）| 差额表：调整/抵销/children_sum/consolidated_amount | `consol_worksheet_engine.recalc_full`（树形计算引擎，算法正确）| pivot / drilldown / triple_format_adapter |
| 模型 2 | `consol_worksheet_data` 表（sheet_key→JSON content）| 15 张致同底稿（净资产表/模拟权益法/少数股东权益/投资成本/内部交易等）的**原始 JSON blob** | 前端 15 个 worksheet 组件 `saveWorksheetData`（不透明 JSON）| 前端组件回显 |
| 模型 3 | `consol_trial` 表 | individual_sum + adjustment + elimination → consol_amount | `upsert_trial_row`（手工）| `consol_report_service` 出报表 |

- **致命问题**：**用户在前端实际填的 15 张致同底稿（模型 2）= 不透明 JSON blob，既不喂模型 1 的计算引擎，也不喂模型 3 的报表**。即：
  - 审计师辛苦填的净资产表/模拟权益法/少数股东权益计算 → 只是存了个 JSON，**不参与任何合并数计算**
  - 合并差额表引擎（模型 1，算法对）→ 与用户填的底稿（模型 2）完全脱节
  - 报表（模型 3）→ 读的是空的 consol_trial
- **后果**：**三套各填各的，没有一条贯通的数据流**。这解释了为什么合并模块"看起来组件齐全"却"从未产出正确合并报表"——不是某个环节断，是三个环节根本没接上。

### W2：15 张致同底稿存为不透明 JSON blob，无结构化字段 — 🟠 不可计算/不可校验
- **实证**：`consol_worksheet_data` 表按 sheet_key 存 `content` JSON（saveWorksheetData PUT 整张表 rows 进 JSON）。15 张表（净资产表/模拟权益法/少数股东权益/投资成本法/权益法/资本公积/抵消后长投/抵消后投资收益/内部往来/内部交易/内部现金流/股比变动等）全是 blob。
- **问题**：JSON blob 意味着 ①后端无法对底稿做公式校验/勾稽 ②无法被合并引擎消费 ③无法做单元格级穿透/留痕 ④schema 演进困难（前端改字段后端无感）。
- **建议**：关键计算类底稿（净资产表/模拟权益法/少数股东权益）应有结构化模型 + 后端勾稽校验，纯展示类（基本信息表）可留 blob。

### W3：前端勾稽计算全在客户端，后端无校验 — 🟠 数据可信度
- **实证**：NetAssetSheet 的 `calcRowTotal = 母公司 + Σ各子企业`、EquitySimSheet 模拟权益法、MinorityInterestSheet 少数股东权益计算**全在前端 .vue 算**，后端只存结果 JSON。
- **风险**：①前端算错/被篡改后端无兜底 ②底稿间勾稽链（净资产表→模拟权益法→少数股东权益→抵消分录）只在前端 computed 隐式连 ③审计软件计算应后端可复算（监管可要求复算）。
- **建议**：核心勾稽下沉后端（至少加校验层：前端算完后端复算比对，不一致告警）。

### W4：差额表引擎（模型1）本应是主干却被架空 — 🟠 架构错配
- **实证**：`consol_worksheet_engine._calc_node` 树形后序遍历（叶子取审定数→中间节点 Σ子节点+抵销+调整→根=合并数）是**教科书级正确的合并差额表算法**，但它不消费 15 张致同底稿、算出的 consolidated_amount 不回写 trial 不喂报表 → 正确引擎被架空，旁边 15 张底稿各算各的。
- **建议**：以差额表引擎为合并计算主干，15 张致同底稿作为"差额来源的明细支撑表"挂接（净资产表/模拟权益法结果→生成抵销/调整分录→进差额表引擎→出合并数）。这是三套模型并一套的核心。

### W 系列优先级
| # | 问题 | 严重度 | 时机 |
|---|------|--------|------|
| W1 | 三套数据模型不连通 | 🔴 | Phase 0（与 B1/B2 同根，定主干）|
| W4 | 差额表引擎被架空 | 🟠 | Phase 0-1（定为主干）|
| W3 | 勾稽计算全在前端无后端校验 | 🟠 | Phase 1-2 |
| W2 | 底稿存 blob 不可计算 | 🟡 | Phase 2-3 |

> **现场负责人判断（工作底稿专项）**：合并工作底稿的根问题不是"缺功能"，是"**三套数据模型并行、用户填的底稿不参与计算**"。正确目标架构是单一主干——**差额表引擎（模型1）作计算核心，15 张致同底稿作明细支撑表喂入，trial/report 作引擎结果投影**。这与 B1/B2/衔接1 是同一件事的切面，都指向 Phase 0 的"三合一"。在理顺主干前给 15 张底稿加再多录入/美化，都是加"填了不算数"的表格——建议 Phase 0 先出一份"合并数据流主干设计 ADR"再动手。
---

## 四-E、Schema / 基础设施级隐患（最底层，最易被自动化安全网漏掉）

> 这一层是"模块能不能在新环境部署起来 + 自动化安全网能不能发现问题"——比业务逻辑更底层。

### C1：合并所有表从未进 D6 迁移，靠 create_all 兜底 — 🔴 部署隐患
- **实证**：grep `consol_trial|consol_worksheet|consol_scope|elimination_entries|consol_lock` 在 `backend/migrations/*.sql` = **0 命中**。合并模块全部表（ConsolTrial/ConsolWorksheet/ConsolScope/EliminationEntry/Company/GoodwillCalc/MinorityInterest 等）**没有任何 D6 迁移脚本**。
- **现状如何工作**：靠 `init_tables.py` 的 `Base.metadata.create_all()` 首次建表（migration_runner 注释承认"现有表已通过 create_all 创建，V001 自动标记已应用"）。
- **致命后果**：`create_all` **只在表不存在时建表，对已存在的表不做任何 ALTER**。所以：
  - 任何后期加到 ORM 的合并字段（如 consol_lock）→ 在已部署 DB **永远不会出现**（这正是 B-lock 的根因）
  - 合并模块在"老库升级"路径上**完全没有 schema 演进能力**——只有全新建库才拿得到最新结构
- **建议**：①补一个 V0XX 合并模块 schema 基线迁移（把 ORM 现状固化为 IF NOT EXISTS 幂等 SQL）②此后合并表所有改动走 D6（memory「三层一致校验铁律」+「D6 唯一入口」）③consol_lock 列就在这个迁移里加

### C2：合并编排者源码已被删，只剩 stale .pyc — 🟠 架构断代
- **实证**：`consolidation_orchestrator` 只有 `__pycache__/consolidation_orchestrator.cpython-312.pyc`，**对应的 .py 源文件不存在**（fileSearch 仅命中 pyc）。
- **含义**：合并模块曾经有过统一编排者，某次重构**删了源码但 pyc 残留**——A6"缺编排者"不是"从没有"，是"有过被删"。这也解释了为什么现在合并各步骤散在各 router（编排层被抽空了）。
- **风险**：stale .pyc 可能被误 import（若有代码还 `from ...consolidation_orchestrator import`），行为不可预测。
- **建议**：①grep 确认无现存代码 import 它 → 删除 stale .pyc（应加 .gitignore `__pycache__`）②重建编排者 = Phase 0 的 cascade_refresh_service（正好填这个空）

### C3：锁定 bug 对所有自动化安全网隐形 — 🔴 可观测性盲区
- **实证**：`schema_drift_detector` 设计为对比 **ORM Base.metadata vs DB 实际 schema**。但 consol_lock：
  - 不在 ORM（service 用裸 SQL `UPDATE projects SET consol_lock=...`）→ drift detector 不会报 orm_extra
  - 不在 DB → 也无 db_extra
  - → **锁定 bug 对 drift detector、/api/health degraded、CI 全部隐形**
- **深层教训**：**用裸 SQL 操作未在 ORM 声明的列，是自动化 schema 安全网的盲区**——drift detector 只能保护"ORM 声明的"字段。这类"ORM 没声明但 SQL 在用"的字段是监控真空。
- **建议**：①consol_lock 必须进 ORM（不只是迁移）——三层一致（DB列+ORM Mapped+service）才能被 drift detector 守护 ②建立规约：service 层禁止裸 SQL 操作未在 ORM 声明的列（grep `UPDATE \w+ SET` 审查）

### C 系列优先级
| # | 问题 | 严重度 | 时机 |
|---|------|--------|------|
| C1 | 合并表无 D6 迁移（无 schema 演进能力）| 🔴 | Phase 0（补基线迁移）|
| C3 | 锁定 bug 对安全网隐形 | 🔴 | Phase 0（consol_lock 进 ORM+迁移）|
| C2 | 编排者源码被删剩 pyc | 🟠 | Phase 0（删 pyc + 重建为 cascade_refresh）|

> **现场负责人判断**：C1+C3 揭示了一个系统性问题——**合并模块是"create_all 时代"的遗留，没跟上 D6 迁移体系**。这意味着它在生产老库上的 schema 是"冻结在首次建库那一刻"的，后续所有 ORM 改动都没落地。Phase 0 必须先补合并 schema 基线迁移，把整个模块纳入 D6 治理，否则 consol_lock 只是冰山一角——任何后加的合并字段都有同样命运。这比单纯修 consol_lock 一个列更根本。

---

## 四-F、合伙人视角：审计风险 / 执业准则 / 可上线性 / 投资决策

> 前面 A/B/C 是技术。这一层是**作为签字合伙人，敢不敢用这个模块出具合并报告、要不要现在投入开发**。

### P1：合并关键操作零审计留痕 — 🔴 执业准则硬伤（CAS 1131）
- **实证**：grep `consol*` / `report_trace` 路由的 audit_log/audit_logger 写入 = **0 命中**。系统有完善的哈希链审计日志基础设施（`audit_log_writer_worker` entry_hash 链式防篡改），但**合并模块的关键操作一个都没接入**：
  - 谁、何时**锁定/解锁**了哪个子公司 → 无记录
  - 谁**审批**了哪笔抵销分录（review_status→APPROVED）→ 无记录
  - 谁、何时触发了**合并重算** → 无记录
- **合伙人风险**：CAS 1131《审计工作底稿》要求关键审计判断可追溯。合并是高风险领域（抵销、少数股东权益是舞弊/差错高发区），关键操作无留痕 = **质控（QC/EQCR）无法复核合并过程，监管检查无法还原**。这是出报告的合规红线。
- **建议**：合并所有写操作（lock/unlock/抵销审批/recalc/范围变更）必须 `audit_logger` 留痕（操作人+时间+前后值），纳入现有哈希链。**这是上线前的强制项，不是 nice-to-have**。

### P2：合并数据无"签字冻结"机制 — 🟠 与底稿签字体系脱节
- **实证**：单体底稿有 WpFileStatus（review_passed/archived）+ dataset 版本锁定（"签字时看到什么，之后永远是什么"）。合并侧**有 ConsolSnapshot 表 + create/list 端点**（report_trace.py），**但实证 create_snapshot 只存 `{"created_at": ...}` 空壳，不快照真实合并报表/附注数据** → 是"快照框架在、快照内容空"。
- **合伙人风险**：合并报告签字后，若子公司数据或抵销分录被改，合并结果会变，但签字时的版本没有真实数据快照 → 无法证明"签字时合并数是多少"。
- **建议**：把 ConsolSnapshot.snapshot_data 填实（签字时序列化 consol_trial/worksheet/report/notes 全量结果 + 哈希），签字后锁定为只读版本。框架已在，缺的是"真正存数据"。

### P3：合并模块从未端到端跑通 — 🔴 可上线性存疑
- **实证综合**（A/B/C 三轮）：individual_sum 无汇总路径（B1）+ 两套计算未对账（B2）+ 表无迁移（C1）+ PG 0 个 consolidated 项目 → **这个模块大概率从未在真实母子数据上端到端产出过一份正确的合并报表**。
- **合伙人判断**：当前状态**不可用于真实出报告**。前端 ConsolidationIndex 多 Tab 看起来完整，但底层合并数不成立——这是"演示能跑、生产不可用"的典型，最危险（容易误判为已完成）。
- **建议**：在 Phase 0 修复 + 一个真实母子项目端到端验证通过前，**合并模块应标记"开发中，不可用于正式合并报告"**，避免审计团队误用产出错误合并数。

### P4：投资决策（要不要现在做、做多少）
作为合伙人的成本/收益判断：

| 维度 | 评估 |
|------|------|
| **沉没成本** | 已投入大量代码（15+ service / 14 router / 多前端组件 / 完整数据模型），**弃之可惜**——大部分是可复用资产，缺的是"接线 + 核心管线 + 留痕" |
| **完成增量成本** | Phase 0-2（核心可用）~7 人天纯工程，无外部依赖；Phase 3 前端 ~3 人天；Phase 4 真实 UAT 卡外部数据 |
| **业务价值** | 合并审计是高端业务（集团客户、收费高），但**当前无真实合并客户数据**（PG 0 个）→ 短期无实际需求拉动 |
| **风险** | 不修但保留 = 误用风险（团队可能以为能用）；修 = 7-10 人天但短期无真实场景验证 |

**合伙人结论（投资建议）**：
1. **不要现在投全力做完**——没有真实合并客户数据（Phase 4 卡死），做完也只能合成数据自测，ROI 低且无法真实验收
2. **但 Phase 0 的"止损 + 防误用"必须做**（~3 人天）：①修 B1/B2/C1 让合并数至少在逻辑上成立 ②P1 审计留痕（合规红线）③P3 加"开发中不可用"标记防误用 ④C3 consol_lock 进 ORM+迁移
3. **Phase 1-3 待有真实集团客户立项时再做**（届时 Phase 4 数据也就位，一气呵成 + 真实 UAT）
4. **优先级排序**：合并模块整体 **低于** 当前在用核心模块的打磨（WorkpaperEditor/WorkpaperList 瘦身、6000 并发、LLM 接入），因为那些是天天用的，合并是"有客户才用"的

> **签字合伙人一句话**：这个模块"骨架健全、神经未通、且没留脚印"。现在花 3 人天做 Phase 0（通核心管线 + 加审计留痕 + 防误用标记）止血，剩下的等真实集团客户来了再投入——**没有真实合并数据时做完整开发，是在为不存在的需求过度投资**。

### P5：合并接口无项目级权限控制 — 🔴 数据隔离 / 独立性风险
- **实证**：全部 consol 路由（worksheet/trial/scope/report/notes/consolidation 抵销）只挂 `get_current_user`，**无一个用 `require_project_access`**（对比单体 adjustments/trial_balance 都挂了 require_project_access("edit")）。
- **风险**：任何登录用户都能调合并穿透/透视/导出 → **子公司 A 的审计助理能通过合并接口看到子公司 B 的全部数据**。集团审计中各子公司常由不同团队/不同事务所做，这违反数据隔离 + 独立性要求（CAS 1101）。
- **建议**：合并接口按"母项目可见性 + 子公司参与关系"做权限控制——能看合并的人 = 母项目团队 + 各自子公司团队只能看自己节点。穿透到子公司明细时校验调用者对该子公司的访问权。

### P6：金额精度 — 基本合规（计算 Decimal），仅 1 处入口隐患
- **实证（澄清，非缺口）**：合并核心计算用 Decimal（`_decimal` + worksheet `ZERO=Decimal` + recalc 全 Decimal），符合「金额 Decimal 铁律」；展示/导出层 `_float`/`_safe_float` 转 float 是常见做法（Excel cell 值），可接受。
- **唯一隐患**：`consol_enhanced_service.import_external_report` 的 `amount = float(row[1])` 在**数据写入入口**用 float（外部报表导入 trial_balance），有精度损失风险——但该方法本身是 A4 死代码，修 A4 时一并改为 Decimal 即可。
- **建议**：修 A4 时入口改 Decimal；计算层已合规无需动。

---

## 四-H、用户点名的 5 大能力 — 现状横切总表（公式管理联动为新核实）

> 用户关注的 5 个跨模块能力，逐一对照前面各章 + 公式管理新核实，给统一裁定。

### H-公式管理联动（本轮新核实）— ⚠️ 部分感知，合并未真正接入
- **实证**：`FormulaManagerScope` 枚举**含 `consol_note`（合并附注）** + SCOPE_LABEL_MAP 有"合并附注"标签——公式管理中心**知道有合并附注这个 scope**。但：
  - 公式管理树（数据源侧栏 treeData）只有 试算平衡表/报表/附注 三类，**无"合并工作底稿"/"合并报表"数据源节点**
  - `formula_audit_log` 的 module 维度支持 report/note 等，但**合并的差额表/抵销/底稿公式未纳入公式审计日志**
  - 合并的"公式"目前散在 consol_report_service（report 公式复用，但用旧 eval=A1）+ 15 张底稿前端 computed（W3）+ note_aggregation（mock CSV）——**没有统一在公式管理中心可见/可编辑/可留痕**
- **裁定**：公式管理对合并是"认得合并附注这个名字，但合并的实际公式（差额表/抵销/底稿勾稽）没接进来"。
- **建议**：合并的公式（差额表计算规则、抵销规则、底稿勾稽公式）统一纳入公式管理中心（数据源树加"合并"节点）+ formula_audit_log（module='consol'）+ 复用 report_engine 安全解析器（解决 A1）。

### 5 大能力横切裁定表
| 用户诉求 | 当前状态 | 对应章节 | 裁定 |
|---------|---------|---------|------|
| **与单体项目模块联动** | 部分（stale 传播/树形/裁剪下发有，自动建树/锁定感知/级联刷新缺）| 缺口6 + 衔接3 | ⚠️ 半 |
| **合并数据溯源互动**（穿透明细）| TB 级穿透有，报表级/附注级穿透全缺 + provenance 缺 | 衔接4 + W1 | 🔴 缺 |
| **国企↔上市模板转换** | consol_cross_template_service（3 API）**孤儿，0 router 引用** | A1 同类孤儿 | 🔴 孤儿 |
| **自定义查询合并各种值** | consol_pivot_service 完整（行列维度/透视/转置/Excel导出/模板）| §2.2 服务层 | ✅ 较完整（但查的是 ConsolWorksheet，受 W1 三套不连通影响，查的可能是"填了不算数"的数）|
| **公式管理联动** | 认得 consol_note scope，但合并实际公式未接入管理中心/审计日志 | H-公式管理（本轮）| ⚠️ 部分 |

> **现场负责人横切判断**：这 5 大能力**全部受 W1"三套数据模型不连通"这个根问题制约**——
> - 自定义查询（pivot）虽"较完整"，但它查的是 ConsolWorksheet，而用户填的 15 张底稿在另一套模型（consol_worksheet_data），所以**查询查不到用户实际填的底稿数据**
> - 溯源穿透要 provenance，但 provenance 要在 B1 汇总时写，B1 还没实现
> - 公式管理要纳入合并公式，但合并公式散在三套模型里，先得三合一
> - 模板转换 service 是孤儿，接线即可但同样要先有统一的章节/数据模型
>
> **结论：这 5 大能力不是 5 个独立功能要分别开发，而是同一个地基（三套模型并一套 + 数据流主干）之上的 5 个出口。Phase 0 的"数据流主干 ADR"必须把这 5 个出口都作为设计输入一次性想清楚**，否则又会变成"5 个各自接线但底层还是不连通"。这是比逐个补功能更重要的顶层设计决策。

---

## 四-I、前后端联动专项（用户补充关注）

> 合并模块前后端契约的对齐与陷阱——光后端对、前端调不到/调了假成功，等于没做。

### F1：前后端 API 路径定义齐全且对齐良好 — ✅ 基础好
- **实证**：前端 `apiPaths` 的 `consolidation`/`consolNoteSections`/`consolWorksheetData` 路径定义完整，覆盖 scope/trial/eliminations/internalTrade/componentAuditor/goodwill/forex/minorityInterest/notes/reports/worksheet 全部后端端点；`consolidationApi.ts` + `commonApi.ts` 有对应封装。**契约对齐是这个模块少有的健康面**。

### F2：前端锁定 API 齐全，但配合后端 consol_lock 缺列 = "假成功"陷阱 — 🔴 前后端联动最危险的坑
- **实证**：前端 `commonApi` 有 `lockProject`/`unlockProject`/`checkLockStatus`（调 `P_consol.lock/unlock/lockStatus`）——**前端锁定调用层完整**。
- **致命联动陷阱**：配合后端 consol_lock 列不存在（B-lock / C1 / C3）：
  - 前端点"锁定" → 后端 `UPDATE projects SET consol_lock=...` 列不存在静默失败 → **但 HTTP 仍返回 200**
  - 前端 `checkLockStatus` → 后端 SELECT 失败走 SAVEPOINT 静默 pass → 返回 `{locked: false}`
  - → **前端显示"锁定成功"，实际没锁；用户以为锁了，子公司照样能改** = 比"功能没做"更危险的"假成功"
- **建议**：补 consol_lock 列后，前端需对 checkLockStatus 的真实状态做 UI 反馈（锁定态 banner + 编辑禁用），并在锁定操作后回读确认。

### F3：前端调不到 V2 附注 / 一键刷新 — 🟠 接线缺口
- **实证**：前端 `consolidation.notes` 只定义了 `list`（老版 generate_consol_notes_sync）+ `save`，**没有 reaggregate / full（V2）/ refresh-all 的路径定义** → 即使后端接线了 V2（A1 建议），前端也调不到。
- **建议**：前后端要同步——后端接 V2 时，前端 apiPaths 补 reaggregate/refresh-all 路径 + UI 入口（按钮）。

### F4：合并写操作无前端 423 锁定拦截处理 — 🟠 联动体验
- **实证**：单体 check_consol_lock 返回 423，但前端 http 拦截器是否对 423 做"项目已锁定"友好提示需核实（grep 未见合并专门的 423 handler）。
- **建议**：http 拦截器统一处理 423 → ElMessage"项目已被合并锁定" + 刷新锁定态。

### F5：合并数据变更后前端无实时刷新 — 🟠 联动时效
- **实证**：单体改数据 → stale 传播标记母项目（consol_note_stale_handler 后端有），但**前端合并页无 SSE/轮询感知 stale** → 用户在合并页看到的可能是过时数据，不知道子公司已改。
- **建议**：合并页订阅 stale 事件（SSE），子公司数据变更时提示"子公司数据已更新，建议重新汇总"。

### 前后端联动优先级
| # | 问题 | 严重度 | 时机 |
|---|------|--------|------|
| F2 | 锁定假成功（前端调通+后端静默失败）| 🔴 | Phase 0（与 consol_lock 列同修）|
| F3 | 前端调不到 V2/一键刷新 | 🟠 | Phase 1-2（与后端接线同步）|
| F4 | 423 锁定无前端友好处理 | 🟠 | Phase 1 |
| F5 | 合并页无 stale 实时感知 | 🟠 | Phase 2-3 |
| F1 | API 路径对齐 | ✅ | 已健康 |

> **现场负责人判断（前后端联动）**：F2 是最隐蔽危险的——**前后端各自看都"对"（前端有调用、后端有端点），但合起来是"假成功"**（列不存在导致静默失败但返 200）。这类"单看两端都没错、合起来错"的联动 bug，是 grep 单端代码发现不了的，必须端到端联调 + 真实点一遍 UI 才暴露（呼应 memory「改动后必 Playwright 实测铁律」）。**Phase 0 修 consol_lock 时必须前后端一起验**：补列 → 后端锁 → 前端点锁定 → 真去改子公司数据验证被拦 423 → 前端显示锁定态。少任何一环都是假闭环。

---

## 五、立 spec 建议

合并附注完整开发涉及 3+ 组件 + 跨前后端 + >500 行改动，按"改动前先 spec 三件律"应立完整三件套。建议：

- **spec 名**：建议改为 `consol-module-completion`（范围已超出"附注三级穿透"，涵盖锁定闭环 + 一键刷新 + 架构修复 + 联动 + 穿透）；原 `consol-note-three-level-drilldown` stub 并入
- **范围**：架构修复（A1/A4/A6）+ 锁定闭环 + 一键级联刷新 + V2 接线 + 三级穿透 + 双向联动
- **Phase 划分**：
  - **Phase 0（基础设施 + 核心管线修复，最高优先，~3 人天）**：
    - **数据流主干 ADR 先行**：W1/W4 定"差额表引擎为主干 + 15 张致同底稿作明细支撑表喂入 + trial/report 作引擎投影"，把三套数据模型并成一套（这是后面所有衔接的设计前提，必须先拍板）
    - **C1/C3**：补合并模块 D6 schema 基线迁移（V0XX，把 ORM 现状固化 + 加 consol_lock 三列）+ consol_lock 进 ORM Project 模型（纳入 drift detector 守护）+ C2 删 stale pyc
    - **B1**：individual_sum 自动汇总（遍历子公司树 TB → 加总，复用 worksheet `_calc_node` 的正确逻辑）
    - **B2/衔接1**：确立 worksheet 为单一合并事实源，report_service 改读 ConsolWorksheet.consolidated_amount（或回写 trial）
    - **A4**：ExternalReportImportService 死代码修复或下线
    - → 没有 Phase 0，后面全是在错误合并数 + 无法演进的 schema + 三套不连通的底稿上加功能
  - **Phase 1（架构修复 + 锁定闭环，~2 人天）**：A1 公式引擎统一（复用 report_engine）+ 衔接2 抵销口径统一 + 锁定全端点覆盖 + ConsolLockedBanner
  - **Phase 2（编排 + 接线，~2 人天）**：A6/C2 cascade_refresh 编排者（重建被删的 orchestrator，含 B1 汇总步骤）+ 一键刷新端点 + V2 附注接线 + B3 自动抵销 + 衔接4 报表穿透（低垂果实）+ 集成测试
  - **Phase 3（前端联动 + 附注穿透，~3 人天）**：附注穿透 UI（依赖 B1 provenance）+ 双向导航 + 自动建树 + 完整度校验
  - **Phase 4（真实数据 UAT + 上年衔接，外部阻塞）**：真实母子数据 + 审计师映射 + 衔接3 上年结转 + 端到端 UAT
- **不做**：多级合并穿透（A 合并 B+C，B 又合并 D+E）、抵消分录穿透（ConsolWorksheet 已提供）、合并附注直接编辑（当前只读生成）、A5 增量重算（留压测后）

---

## 六、风险与注意

| 风险 | 缓解 |
|------|------|
| V2 接线后改变前端"生成合并附注"行为 | feature flag 双版本并存，灰度切换 + 老版兼容保留 |
| mock CSV 替换真实映射时章节 ID 不匹配 | section_title 跨项目 alias 表（README TD-A）|
| consolidation_breakdown JSONB 大表查询慢 | GIN 索引（README TD-B）|
| 阶段 A 写完无真实数据无法验收 | 合成母子数据集成测试先证链路；真实 UAT 显式标"待数据"不伪绿 |
| 合并 stale 传播链（子公司 stale→母 stale）| consol_note_stale_handler 已实装，扩展覆盖 V2 路径 |

---

## 附：本次调研未能实时核实项（诚实声明）
- **PG consolidated 项目数 + 实际 DB schema**：Docker 未运行，无法实时查询。consol 表是否真在 PG（create_all 是否跑过）、consol_lock 是否真缺，需 Docker 起来后 `\d projects` + `SELECT count(*) FILTER (WHERE consol_level>1)` 复核。
- **算法单测全绿 ≠ 端到端正确**：consol 单测是纯函数合成数据，未跑真实母子端到端。
- **A4 死代码 / C2 stale pyc**：基于静态读代码 + grep 0 import 判定，未实跑触发。
- **worksheet vs trial 谁更可信的最终裁定**：建议 worksheet（算法实证正确），但需与审计专业确认合并口径后定单一事实源。
- **MI/商誉在 verify_balance 的处理**：B4 未深入读 verify_balance 实现，待核。
- **前端合并 god component 质量**：ConsolidationIndex.vue（1412 行）等未做拆分/质量评估（属另一治理维度）。
