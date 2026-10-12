# Requirements — 同步编辑器宿主纳入挂点发现契约（平台级缺陷闭环）

## Introduction

**缺陷一句话**：底稿同步的 entry 清册（`workpaper_sync_entry_manifest.json`）只能由
前端挂点发现器 `discover-workpaper-sync-mounts.mjs` 发现到的挂点派生，而该发现器的
组件白名单只有 `GtOnlyOfficeSheet` / `OnlyOfficeWordDialog` / `WorkpaperWordEditor`，
**不含 `WorkpaperSyncEditorHost`** —— 后者正是双向回写的真载体。于是：

> **一个宿主一旦完成双向回写迁移、删掉 legacy 标签，它在 manifest 里的 entry
> 就直接不存在。迁移越彻底，越早从清册里消失。**

这不是假设。现算（2026-10-01）：

| 事实 | 现算值 |
|---|---|
| 挂 `WorkpaperSyncEditorHost` 的宿主 | **96** |
| 其中「仅 EditorHost、无 legacy 挂点」 | **51** ⇒ 这 51 个在清册里**没有 entry** |
| 已真实消失过的 | **34 个 `d4/**` tab**（随 commit `cd9592ff5` 迁移后退出清册） |
| 本轮新消失的 | **17 个 A 类宿主**（A101/A111/A121/A171/A1721/A1731/A173/A174/A176/A177/A181/A182/A271/A3/A51/A81/A91） |
| 直接后果 | `xlsx/gt-a51-cashflow-audit` 等 17 条 entry 消失 ⇒ 其 adapter 永远无法注册；overlay 里那条 a51 `bidirectional` 裁决**不可兑现**（已被迫移入 `deferred_overrides`） |

**为什么不能用「加个 glob 规则」糊过去**：entry 的派生链是
`discovery.mounts → _group_source_facts → _entry_id → manifest.entries`，
没有被发现的挂点在链条起点就不存在。同时 `_entry_id(document_type, source_file)`
**不含 component**，若把 EditorHost 直接加进白名单，45 个「既挂 EditorHost 又挂 legacy」
的宿主会产出两个组、撞同一个 entry_id，生成器 `stable entry_id collision` 当场中止。

**为什么现在必须修**：缺口是单向棘轮 —— 每完成一个宿主的双向迁移，就多一个 entry 消失。
而 entry 是 adapter 注册、契约归属、representation 身份的主键，消失即能力永久不可达。

## 术语

- **挂点（mount）**：`.vue` 模板 AST 里一个被发现器识别的组件使用点，含 `file` /
  `component` / `documentType` / `sheetExpression` / `wpExpression` / `sourceSpan`。
- **entry**：manifest 的一行，主键 `entry_id = {document_type}/{kebab 化的宿主相对路径}`。
  它是 adapter 注册与 representation 身份的**稳定持久化键**，**绝对不可改**。
- **L1/L2/L3**：本 spec 定义的三层 document_type / entry 身份解析链（见 Requirement 2）。
- **双挂宿主**：同一 `.vue` 同时挂 `WorkpaperSyncEditorHost` 与某个 legacy 组件（现算 45 个）。
- **仅 EditorHost 宿主**：只挂 `WorkpaperSyncEditorHost`（现算 51 个）。

## Requirements

### Requirement 1 — 发现器纳入 `WorkpaperSyncEditorHost`，且不得静默漏掉

**User Story:** 作为平台维护者，我要让「挂了真双向载体」这件事成为挂点清册里的一等事实，
这样宿主完成迁移后它的 entry 仍然存在。

#### Acceptance Criteria

1. WHEN 发现器扫描 `.vue` 模板 THEN 它 SHALL 把 `<WorkpaperSyncEditorHost>` 的使用点
   作为挂点产出，`component == "WorkpaperSyncEditorHost"`、`sourceKind == "template_ast"`。
2. 发现器 SHALL 同时支持静态 `import` 与 `defineAsyncComponent(() => import(...))` 两种绑定形态
   （现算：96 个宿主里两种都有）。
3. WHEN 某个 EditorHost 挂点的 `documentType` 无法由 Requirement 2 的三层链解析 THEN
   发现器或生成器 SHALL **抛错中止**（fail closed），不得产出 `documentType: null` 的挂点，
   也不得默默跳过该挂点。
4. `stats.byComponent` SHALL 增加 `WorkpaperSyncEditorHost` 键；`sourceDigest` SHALL 随新挂点改变
   （⇒ overlay 的 `approved_source_digest` 复核门必然跳闸一次，这是设计意图）。
5. 🔴 **反向判据**：若把 `WorkpaperSyncEditorHost` 从白名单里摘掉，Requirement 4 的
   「无 entry 宿主数 == 0」判据 SHALL 打红 —— 证明本需求不是装饰。

### Requirement 2 — document_type / entry 身份的三层解析链，源码事实优先于人工裁决

**User Story:** 作为复核方，我要让尽可能多的宿主靠**源码自证**身份，只对真正无法自证的
部分给出人工裁决，这样规则表不会变成一张随代码漂移的手抄名单。

`WorkpaperSyncEditorHost` 的 props 只有 `descriptor` / `bridge`（现读实证）——
**没有 `wp-id`、没有 `sheet-name`、不带文档类型**，它同时服务 Excel 与 Word。
所以 document_type 必须另寻来源。

#### Acceptance Criteria

1. **L1（同文件兄弟挂点）** WHEN 某 EditorHost 挂点所在文件**还有** legacy 挂点 THEN
   该 EditorHost 挂点的 `documentType` SHALL 取兄弟挂点的 `documentType`。
   AND IF 兄弟挂点存在多个互不相同的 `documentType` THEN SHALL fail closed。
   （现算覆盖 **45** 个宿主，兄弟 document_type 全为 `xlsx`、零冲突。）
2. **L2（同模板 entry-id 字面量）** WHEN 文件内无 legacy 挂点 AND 模板里有**恰好一个**
   静态字面量 `entry-id="{xlsx|docx}/..."`（`GtEntrySyncCapabilityNotice` 的 prop）THEN
   SHALL 以该字面量为该宿主的 entry 身份声明，`documentType` 取其前缀。
   AND IF 存在多个互不相同的该字面量 THEN SHALL fail closed（不得任取其一）。
   （现算覆盖 **21** 个宿主：17 条声明值 == 自身路径派生值、4 条指向别的 entry。）
3. **L3（reviewed overlay 规则）** WHEN L1、L2 均不成立 THEN SHALL 要求 overlay 中存在
   匹配该文件的 reviewed 规则给出 entry 身份；无匹配规则 SHALL fail closed。
   （现算需要 L3 的是 **30** 个宿主，**全部**在 `audit-platform/frontend/src/components/workpaper/d4/` 下
   ⇒ 一条 glob 规则即可覆盖。）
4. 解析链 SHALL 严格按 L1 → L2 → L3 顺序，且**不得**有第四层兜底（例如「默认 xlsx」）。
   现算 96/96 全是 `xlsx`，但默认值会让第一个 docx 迁移宿主静默落到错误 document_type。
5. 🔴 **交叉校验（防规则写错）**：对同时具备 L1 与 L2 信号的宿主（现算 **41** 个），
   两者给出的 `documentType` SHALL 一致；现算不一致数为 **0**，若将来非 0 SHALL fail closed。
6. 🔴 **空分母防护**：L1 / L2 / L3 三层各自的覆盖数 SHALL 非零且三者之和 == EditorHost 宿主总数。
   任一层归零即说明口径坏了（而不是「该层恰好没有对象」），SHALL 打红。

### Requirement 3 — 一个宿主 + 一个 document_type = 一个 entry（消除 entry_id 碰撞）

**User Story:** 作为生成器，我要在同一 entry 里容纳同一宿主的多种挂点组件，这样
「宿主同时挂 legacy 与 EditorHost」这个**迁移中间态**不会撞 entry_id。

#### Acceptance Criteria

1. `_group_source_facts` 的分组键 SHALL 由 `(file, component)` 改为 `(file, document_type)`。
2. `_entry_id(document_type, source_file)` 的签名与算法 SHALL 逐字不变 ——
   entry_id 是持久化主键，**本 spec 不得改变任何既有 entry_id 的取值**。
3. WHEN 一个组含多个 `component` THEN 该 entry 的 `html_store` / `canonical_resolver` /
   `adapter_id` / `capability` / `migration_state` / `expected_profile` 默认值
   SHALL 来自**声明的组件优先级**中最高者，且优先级 SHALL 把 legacy 组件排在
   `WorkpaperSyncEditorHost` **之前**。
   🔴 这条优先级的目的是**零 capability churn**：45 个双挂宿主的 entry 取值因此逐字不变，
   本 spec 不顺手改任何一条既有 entry 的能力裁决。
4. 每个 entry SHALL 新增 `mount_components`（该 entry 实际出现过的组件集合，排序后）
   与 `sync_editor_host_mounted`（布尔）两个 source-backed 字段。
5. `manifest.entries[].mounts[]` SHALL 包含该组的**全部**挂点（含 EditorHost），
   且 `manifest_mount_ids` 与 `discovery.mounts` 的对账（仅 `sourceKind == "template_ast"`）
   SHALL 仍然逐个相等。
6. WHEN 某宿主的 EditorHost 挂点按 L2/L3 解析出的 entry 身份**不等于**其自身路径派生值 THEN
   该宿主 SHALL 成为 `parent_duplicate` entry，`parent_entry_id` 取声明值，
   `adapter_id` 置 null、`migration_state` 置 `parent_duplicate`（复用既有机制，不新造状态）。
7. `stable entry_id collision` 检查 SHALL 保留；本 spec 之后它 SHALL 仍然对真正的
   同键冲突打红（配变异证明：人为造一个同路径同 document_type 的第二组必须抛错）。

### Requirement 4 — 缺口本体必须被不变量钉死，且不得再次静默复发

**User Story:** 作为下一个接手的人，我要有一条判据直接回答「有没有宿主挂了同步载体却没有 entry」。

#### Acceptance Criteria

1. SHALL 存在判据：**每个挂 `WorkpaperSyncEditorHost` 的宿主在 manifest 里都有一条 entry**
   （独立或 parent_duplicate 皆可），无 entry 的宿主数 SHALL == 0。
2. SHALL 存在判据：该不变量的分母（EditorHost 宿主数）SHALL 非零且**现算**，不得写死 96
   —— 迁移在推进，写死即假红。
3. SHALL 存在判据：`manifest.stats` 自洽 —— `capability_counts` / `entry_count` 与
   `entries` 现算逐值相等。
   🔴 这条来自实证教训：2026-09-30 发现 HEAD 的 committed manifest `entries` 有 5 条
   bidirectional 而 `stats` 声明 4，坐实被手改过（`1ec6a1050` 改了 D1 却没重跑生成器），
   而**没有任何判据守住它**。
4. SHALL 存在判据：overlay 的 `deferred_overrides` 在本 spec 落地后 SHALL 为空 ——
   a51 裁决能且必须移回 `overrides`（这是本 spec 成功的终局验收）。
5. 🔴 **变异证明**：把 `WorkpaperSyncEditorHost` 从发现器白名单摘掉后，AC 4.1 SHALL 打红；
   把 L3 的 d4 glob 规则删掉后，生成器 SHALL fail closed 而不是静默少 30 条 entry。

### Requirement 5 — 复核门与下游产物的一致处置

**User Story:** 作为复核方，我要清楚知道这次改动让哪些产物与判据发生变化，以及哪些
**不属于**本 spec 的职责。

#### Acceptance Criteria

1. 本 spec SHALL 更新 overlay 的 `approved_source_digest` 并在 `review_basis` 写明
   「新增 96 条 EditorHost 挂点」这一归因；SHALL NOT 顺手批准任何无关的挂点变化。
2. SHALL 重生成 `workpaper_sync_entry_manifest.json`、前端投影、
   `workpaper_sync_legacy_baseline.json` 及其前端投影四件产物。
3. SHALL 把 a51 裁决从 `deferred_overrides` 移回 `overrides`，并删除
   `TestDeferredOverrideStaysRestorable` 整类（其存在前提已消失）。
4. 🔴 entry 数将由 **138 → 189**（+17 独立 + 34 parent_duplicate）。
   各 cycle 的**冻结 slice / record 产物**（`workpaper_sync_abcs_cycle_manifest_slice.json`、
   `workpaper_sync_task63_*` 等）与 manifest 的对账将再次不闭合。
   本 spec SHALL **逐条登记**这些失败并归因，SHALL NOT 代各 lane 的 owner 重生成其审阅产物。
5. SHALL 跑 `check_sync_provider_golden_digest.py` 并断言 G 域零漂移；
   IF 出现他人未提交改动导致的漂移 THEN SHALL 如实归因，SHALL NOT 执行 `--update`。
