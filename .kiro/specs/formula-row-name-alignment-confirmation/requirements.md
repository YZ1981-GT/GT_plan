# Requirements Document

## Introduction

审定表 / 附注披露表的取数依赖**行项目名称**与账套（四表库）明细名称对齐。现状问题：底稿里相当一部分行名是**模板固定写死**的（源 xlsx 的行标签），而实际账套明细名由被审计单位自己命名，两者常常不一致 ⇒ 公式取数落空（表现为「刷新了但没数」或某些行恒 0），审计师无法知道是"真的没有这笔"还是"名字没对上"。

本 spec 要做的是：**把"名称对齐"从隐式猜测变成一次显式的、可持久化、可追溯的用户裁决**。用户点「刷新」时，若存在无法自动匹配的行名，弹窗让用户手动确认对应关系（支持一对多 / 多对多 / 多对一），确认结果落库并在后续刷新中复用，同时保留"来源可溯"（哪一行的数来自哪个账套明细名、是自动匹配还是人工确认）。

### 已确认的红基线与硬约束（不得违反）

1. **toolbar 归属**：`workpaper-page-formula-toolbar-closure` 这个 active spec **独占** workpaper route 的 toolbar outlets 与页面级 FormulaManager owner，并明写「后续 spec 只消费 `F-SHELL`，不能再建第二个 location owner、公式按钮、dialog 或 fixed rail」。同时它已确认红基线：`GtWpToolbar.vue` **只有 `.gt-wp-toolbar__right` CSS 容器，没有 Vue slot**。⇒ 本 spec 的刷新入口**必须走该 spec 的 outlet 契约**，不得自己在 `GtWpToolbar.vue` 里加第二个按钮 owner。
2. **既有全局刷新弹窗不是本 spec 的东西**：`components/formula/GtRefreshScopeDialog.vue` 是「合伙人全局一键刷新 · 选择刷新范围」（走 `/api/workpapers/refresh-scopes` + `/api/workpapers/draft-refresh`，挂在 `ThreeColumnLayout`）。它解决的是**刷哪些作用域**，本 spec 解决的是**名字怎么对上**，两者是不同关注点，不得合并成一个弹窗，也不得复制它的 scope 树。
3. **科目定位真源**：`backend/app/services/four_table/report_line_accounts.py::ReportLineAccountSpec` 是报表行 → 科目码的声明式真源，`leaf_aggregation.py::select_leaves/aggregate_leaves` 做叶子聚合。既有的**唯一**名称相关钩子是 `provision_name_filter`（仅在反解退化为宽前缀时叠加的名称过滤词）。⇒ 本 spec 不得再造第二套科目定位逻辑，只在**名称维度**补一层可确认映射。
4. **用户覆盖的既有机制**：`workpaper_field_overrides` 表（迁移 V076，ORM `workpaper_field_override_models.py`，按 `project_id` / `year` / `scope` 索引）是平台既有的「系统自动值 + 用户可覆盖」存储。⇒ 本 spec 必须先评估复用它，只有证明其形态不足（本映射是 N:M 关系而非单字段值）才允许新建表 + 新迁移。

## Requirements

### Requirement 1: 未匹配行名的可见化（先让问题看得见）

**User Story:** 作为审计师，我要能一眼看出「这一行取不到数是因为名字没对上」，而不是看着一个 0 猜原因。

#### Acceptance Criteria

1. WHEN 底稿按行名取数 THEN 每一行必须产出可观测的匹配状态：`auto_matched` / `unmatched` / `user_confirmed` / `ambiguous`（多个候选），不得只返回金额
2. WHEN 某行状态为 `unmatched` 或 `ambiguous` THEN 前端必须在该行给出可见标识与可点击入口，不得静默显示 0
3. WHEN 一行的数来自人工确认映射 THEN 必须可追溯出「映射到哪个/哪些账套明细名、由谁在何时确认」
4. WHEN 账套侧新增/改名导致既有确认映射失效 THEN 该行必须回落为 `unmatched` 并提示需重新确认，不得继续用过期映射出数

### Requirement 2: 刷新时的手动确认弹窗（一对多/多对多/多对一）

**User Story:** 作为审计师，我点刷新后希望一次性把对不上的名字全部确认掉，而不是逐行去猜。

#### Acceptance Criteria

1. WHEN 用户触发刷新且存在 `unmatched`/`ambiguous` 行 THEN 必须弹出对齐确认弹窗，列出「底稿行名」与「候选账套明细名」两侧
2. WHEN 弹窗展示候选 THEN 候选必须来自真实账套数据（四表库当前 active dataset），并按相似度或金额量级给出排序提示，不得让用户在全量清单里盲找
3. WHEN 用户建立映射 THEN 必须同时支持：一个底稿行 ↔ 多个账套明细名（一对多）、多个底稿行 ↔ 一个账套明细名（多对一）、以及两侧都多的组合（多对多）
4. WHEN 存在多对一映射 THEN 必须显式告知同一账套明细将被多行引用及其口径后果（是否重复计入合计），并要求用户确认，不得静默双算
5. WHEN 用户确认后 THEN 弹窗关闭并立即用新映射重算受影响行；未确认的行保持 `unmatched` 不伪造数值
6. WHEN 用户取消 THEN 不得写入任何映射，本次刷新按既有自动匹配结果结算

### Requirement 3: 映射持久化与复用

**User Story:** 作为审计师，我确认过一次的对应关系不该下次刷新又要重做。

#### Acceptance Criteria

1. WHEN 评估存储方案 THEN 必须先给出「复用 `workpaper_field_overrides` 是否可承载 N:M 映射」的书面结论；若新建表则必须写明为何既有机制不足
2. WHEN 映射落库 THEN 作用域必须至少含 project + year + 底稿（wp_code/sheet）+ 行标识，保证跨项目/跨年度不串
3. WHEN 同一作用域再次刷新 THEN 已确认映射必须自动生效且不再弹窗（除非映射已失效）
4. WHEN 需要新迁移 THEN 必须是 `backend/migrations/V*.sql` 且全部 DDL 幂等（`IF NOT EXISTS`）
5. WHEN 用户要修正历史确认 THEN 必须有入口可重新打开弹窗并覆盖既有映射，覆盖必须留痕（谁改的、改前是什么）

### Requirement 4: 刷新入口补齐（消费 F-SHELL，不自建按钮 owner）

**User Story:** 作为审计师，没有刷新按钮的底稿我也要能触发取数刷新。

#### Acceptance Criteria

1. WHEN 需要在底稿工具栏暴露刷新入口 THEN 必须通过 `workpaper-page-formula-toolbar-closure` 提供的 toolbar outlet / `F-SHELL` 契约注入，**禁止**在 `GtWpToolbar.vue` 内新增第二个按钮 owner 或绕开 outlet 直接改 DOM
2. WHEN 该 outlet 尚不可用 THEN 本 spec 的入口任务必须显式 BLOCKED 并记录依赖，不得以「先临时加一个按钮」绕过
3. WHEN 枚举「哪些底稿缺刷新入口」THEN 清单必须从真实 renderer registry / render-config / 已挂载宿主推导，不得用 grep 按钮文字或写死页面数量
4. WHEN 入口渲染 THEN 位置为工具栏「导入」右侧（既有 `导入` 按钮 emit `import-data`），且在只读态下必须禁用

### Requirement 5: 不伪造、不静默、可复核

**User Story:** 作为质控复核人，我要能判断一张表的数是真取到的还是被兜底填出来的。

#### Acceptance Criteria

1. WHEN 任何一行无法匹配 THEN 不得以 0 / 空 / 上期值伪装成已取数
2. WHEN 自动匹配采用了模糊/相似度策略 THEN 该行状态必须是 `ambiguous` 且必须经人工确认才可落为 `user_confirmed`，不得把模糊命中直接当精确命中
3. WHEN 落地映射机制 THEN 必须有守卫测试证明「删掉映射查询/改错作用域键」会打红（变异检验），不得只测「函数存在」
4. WHEN 本 spec 交付 THEN 必须有一次真栈实测（浏览器）证明：不一致的行名经弹窗确认后，该行金额从 0 变为账套真实值
