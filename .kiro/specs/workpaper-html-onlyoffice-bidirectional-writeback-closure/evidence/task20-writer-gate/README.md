# Task 20 证据：writer / version domain gate —— **未过**，红且具名

Requirements 2.1、2.2、2.12、9.11 · Property 4、Property 61

**结论先行**：门**仍是红的**（`total blocking facts = 917`，退出码 1）。Task 20 正文点名的五条
准则（原六条，`multi_resolver` 已移交 Task 30）里 **3 条为零、2 条阻塞**。两条阻塞项各有名字与归属，
没有一条是「忘了做」；把它们变绿都需要**放宽谓词**、**改小分母**或**替产品做决定**，三者本任务都不做。

> 按 Task 20 自己的写法：**本门未过，Wave 2 coordinator 与任何 adapter pilot 不得宣称 base 可靠。**

---

## 〇、分母（scope）裁决：**universal，不是 Task 3 那几个 lane**

两条阻塞项（236 / 261）之所以是三位数，是因为清册的分母是**整个** `backend/app` 的 269 个生产
writer，而 Task 3 的人工裁决只覆盖 50 行。于是存在一条极便宜的「关门」路径：把分母改小 —— 宣布
Task 3 正文点名的那几个 lane 才是 scope，其余「不在范围内」，两条计数当场归零，而门的输出与真的
迁完**逐字相同**。

**这条路径已被裁决为不成立**，依据是 spec 自己的文字（不是本任务的主张）：

| 出处 | 原话 |
|---|---|
| requirements.md · Requirement 2 User Story | 「我要**所有内容 writer** 使用同一 revision 协议」 |
| requirements.md · AC 2.2 | 「**任何绕过入口的 writer** SHALL 被清册与 CI 阻断」 |
| design.md · Property 61 标题 | 「**所有 writer** 进入唯一 revision 域」 |
| design.md · Rollout 第 3 条 | 「先将**全部生产 writer/resolver** 迁入唯一 content revision 域……writer matrix 未归零时禁止 bulk」 |

窄读法（「Task 3 正文枚举的那几个 lane 才是 scope」）在 spec 里找不到落脚点，且有三处内部反驳：

1. **Task 3 第三条在窄读法下是恒真空句**：「任何未裁决 writer 使统一 revision gate 保持红」——
   一份按「已裁决」定义的清册里不可能存在未裁决行。这条准则只有在「发现是结构性的、裁决是人工的、
   发现到而未裁决即欠账」的读法下才有内容。
2. **Task 3 自己的 reviewed overlay 越过了那个枚举**：它把 **6 行**裁决进了 `template_provisioning`，
   而这个 domain 既不在 Task 3 正文的 lane 枚举里、也不在门的 `_REQUIRED_DOMAINS` 里。若枚举就是
   scope，Task 3 自己那 6 条裁决全部越界。
3. **门的 `_REQUIRED_DOMAINS` 本来就是覆盖地板而非天花板**：它是生成器 `_DOMAINS`（13 个）的**真**
   子集（11 个），语义是「某个 lane 掉到零行 = 发现谓词悄悄瞎了一整条道」，不是「只算这几条」。

结论：**236 行是真欠账，Task 20 不能关。** 分母不是本门的自由度。

为了让「悄悄改小分母」这个动作将来必须浮到人面前，scope 本身已变成 4 条可打红判据
（`test_task20_writer_gate.py` §7），且全部经变异检验（M16–M20，见 §六）：

| 判据 | 守什么 | 收窄手法一旦发生 |
|---|---|---|
| `..._denominator_is_every_production_module_under_backend_app` | 发现面 = `backend/app` 全部生产模块；**独立重算**一遍模块集后与生成器实际走过的逐个比对 | 改 `_APP_ROOT` ⇒ 红（M16） |
| `..._production_source_predicate_excludes_exactly_the_non_shipping_trees` | 非交付目录排除表**双向**：该挡的挡住 + 业务包一个不许挡 | 往排除表塞业务包 ⇒ 红（M17） |
| `..._both_workpaper_content_stores_stay_in_the_denominator` | `working_paper` + `checklist_responses` 都留在内容存储表里（谓词行为级，非计数式） | 删掉第二存储 ⇒ 红（M18） |
| `..._universal_scope_is_the_specs_own_definition_not_this_files` | 上表四句 spec 原话逐句唯一存在；`_REQUIRED_DOMAINS ⊊ _DOMAINS`；overlay 里仍有裁决落在门点名的 lane 之外 | 抹掉反证 ⇒ 红（M19）；改 spec 原话 ⇒ 红（M20） |

四条都**不**断言「欠账仍然存在」—— 说的是发现面、spec 文字与 domain 表的形状。欠账真的还完之后
（每行都裁决、每行都经统一入口）本节仍然全绿。

## 一、Task 20 点名的准则

| # | 任务正文 | 门里的 issue key | 计数 | 判定 |
|---|---|---|---|---|
| 1 | 生产写路径未裁决=0 | `unadjudicated_writer` | **236** | ❌ 阻塞 |
| 2 | 绕过统一 commit=0 | `bypasses_unified_commit` | **261** | ❌ 阻塞 |
| 3 | bidirectional projection-only / 双 revision=0 | `keeps_legacy_write_path_beside_unified_commit` | 0 | ✅ |
| 4 | representation upgrade 增 business revision=0 | `representation_upgrade_increments_business_revision` | 0 | ✅ |
| 5 | after-save 增 revision=0 | `after_save_still_increments_revision` | 0 | ✅ |
| — | 多 resolver writer=0（**已移交 Task 30**） | `multi_resolver` | 4 | 归属 Task 30，见 §四.3 |

🔴 **第 3、4 条在本任务之前门里并不存在** —— 门只评四条。「没评过」与「评过且为零」在报告里长得
一模一样，这本身就是一个 fail-open 入口：Task 20 若照原样收口，会拿两条**从未被检查**的准则去
声明 base 可靠。两条准则已补上（各自带非空源码分母 + 注入 falsifier），
`test_the_gate_evaluates_every_criterion_task20_names` 逐条钉住五个 key 都在。

**关于第 3、5 条的分母，两点诚实登记**：

* 第 3 条的分母 = **7** 个到达统一入口的 writer（`save_html_data`、两个 F2 `_save_fields`、
  `VersionTrailService.rollback_to_snapshot`、`WOPIHostService.put_file`、`WpUploadService.upload_file`、
  `WpMigrationService.rollback`）；空分母时门抛错而非报绿（M10 是 falsifier）。
* 第 5 条在 `entries` 里的分母**是 0** —— 没有任何 `entries` 行的 domain 是 `orchestrator_side_effect`
  （`WorkpaperSaveOrchestrator.after_save` 已由 Task 16/18 迁走、进了 `retired_writers` 台账）。它是
  **经退役台账正向评估**的：台账要求该函数在源码里仍然存在（`source_state=present_and_clean`）且
  声明为空的事实真的为空，`_build_retired_writers` 在事实回归时直接抛错（门退出码 2）。所以这条准则
  **确实被评估**，但 `entries` 侧那个 `if domain == "orchestrator_side_effect"` 分支目前不可达 ——
  已登记，见 §九。

## 二、门的全部准则：前 → 后

前值 = `inventory_before.json`（Task 19 收口态）用**同一口径**重算；`n/a` = 该准则本任务新增。

| 准则 | 前 | 后 | 说明 |
|---|---|---|---|
| `unadjudicated_writer` | 236 | 236 | 结构性欠账，见 §四 |
| `unadjudicated_resolver` | 34 | 34 | 同上 |
| `bypasses_unified_commit` | 262 | **261** | −1：`save_version` 进 artifact-snapshot 类别（§三.2） |
| `writes_legacy_version_field` | 5 | 5 | |
| `owns_direct_commit` | 105 | 105 | |
| `keeps_legacy_write_path_beside_unified_commit` | n/a | **0** | 新增，分母 = 7 个统一入口调用方 |
| `after_save_still_increments_revision` | 0 | 0 | Task 16/18 已清 |
| `representation_upgrade_increments_business_revision` | n/a | **0** | 新增，分母 = 1（升级器） |
| `artifact_snapshot_writer_not_verifiable` | n/a | **0** | 新增，分母 = 1（快照 writer） |
| `retired_writer_not_verifiable` | 0 | 0 | |
| `multi_resolver` | 4 | 4 | Task 12 已登记 deferred，见 §四.3 |
| `non_canonical_resolver_only` | 64 | 64 | |
| `writer_without_characterization_test` | 165 | **208** | +43：谓词收紧，**变差是正确方向**（§三.1） |
| `missing_required_domain` | 0 | 0 | 11 个域全部有源码支撑的行 |
| **合计** | **875** | **917** | |

原始输出：`gate_blockers.json`（含每条准则的完整行名 + 按模块的分布）。

## 三、本任务修掉的两个谓词缺陷（Task 19 交接）

### 1. `has_characterization_test` 从「名称就近」改成「真的有调用点」

Task 19 记录的两条 false credit，现已双向证实修好：

| 行 | 改前记账 | 改后 |
|---|---|---|
| `WpStorageService.list_versions` | Task 19 守卫（**从未调用**它，只提到了同模块的类名） | `[]` |
| `WpMigrationService.rollback` | 3 个文件，含用 `copy.deepcopy` 模拟回滚、**从未调用**它的属性测试 | 只剩 Task 19 守卫（真的 `WpMigrationService(session).rollback(...)`） |

新谓词：测试文件里必须存在一个**调用表达式**，其被调用者经绑定解析到该 writer ——
`from m import f` 后 `f(...)`、`import m` 后 `m.f(...)`、`Cls.method(...)`、`Cls(...).method(...)`、
以及 `x = Cls(...)` 后 `x.method(...)`。打桩字符串（`monkeypatch.setattr("app.x.y", ...)`）不再算证据。

**代价（诚实登记）**：**52 行失去记账、0 行新增**，因此 165 → 208。其中相当一部分是**真的有测试、
但只经 HTTP 路由驱动**的 router（`client.post("/api/...")` 里没有任何提到函数名的调用点），例如
`WOPIHostService.put_file`（`test_wopi_working_paper_qc_review.py` 确实在测它）、
`h1_depreciation_calc`、`k_expense_analysis` 等。所以：

* 旧的 165 是**高估覆盖**（乐观）；新的 208 是**低估覆盖**（悲观）。两个数字都不是真实覆盖率。
* 门要的是 fail-closed，悲观方向是正确的偏置；但**不得**把 208 读成「208 个 writer 没有测试」。
* 未补的能力（已登记）：按路由装饰器路径匹配 `client.post("<path>")`，可把 HTTP 驱动的调用点找回来。
  本任务没做——它需要路由前缀/`router_registry` 解析，是独立一块，且不影响门的红绿。

失去记账的完整名单在 `characterization_credit_delta.json`。

### 2. artifact-snapshot：给 `save_version` 一个**正面类别**，不是豁免

`WpStorageService.save_version` 把**当前**文件复制进 `.versions/`，内容零字节变化 ⇒ 它没有业务内容
可提交，`bypasses_unified_commit` 对它永远到不了零（Task 19 已登记这一行「门永远差它」）。

类别从**目标路径**派生，两个条件都必须成立：

1. 函数里**每一次** artifact 写的目标都能追到快照命名空间（`.versions` / `.upgrade-candidates`）；
   追不到的目标记 `unclassified`，有一个就失去类别；
2. 函数零业务内容事实（零 content store / 零 version 字段 / 零被跟踪 SQL 列 / 零 after_save / 零委派）。

**爆炸半径实测 = 1 行**。这不是运气：清册里有 **15** 个 writer「零业务内容事实」，其中 14 个写的是
**权威** artifact（`excel_html` 的 structure.json、模板落地、自定义底稿生成……）。一个宽泛的
「无内容事实 ⇒ 不算绕过」会一次性放掉 15 行，包括那套活的平行权威。两个条件各有**实测代表**：

* `save_univer_data` —— artifact 写**全部**落在 `.versions/`，但它同时推进 `file_version` 并写
  `working_paper` ⇒ 被条件 2 挡住；
* `WOPIHostService.put_file` —— 还有两处非快照目标 ⇒ 被条件 1 挡住。

类别**自带可打红的义务**（门的 `artifact_snapshot_writer_not_verifiable`）：必须被裁决、必须读
**统一**计数器（`content_revision`，即快照名跟随真正在动的那个）、不得读写 legacy 字段。注入
`wp.file_version += 1` 后该行**失去类别、重回门内**（注入实验 I4）。

## 四、门被什么挡住（逐条具名）

### 1. `unadjudicated_writer` = 236（结构性）

Task 3 只裁决了 50 行；清册的分母是**整个** `backend/app` 的 269 个 writer，而 §〇 已裁定这个
分母就是 spec 要的分母。剩下 236 行要归零，等于给每一个写底稿内容的 router/service 写一条经人工
复核的 `version_domain_note`。生成器刻意**从不发明裁决**（`the generator never invents an
adjudication`），所以这一项只能靠真实评审推进，不能靠脚本。

分布见 `gate_blockers.json`。按「为什么被认成 writer」归类（236 行）：

| 结构事实 | 行数 | 说明 |
|---|---|---|
| 单跳委派到某个直接内容 writer | 91 | 入口层（router）委派给 `_save_html_data` 之类 |
| 裸 SQL 写内容存储列 | 86 | 其中 `checklist_responses.remark` 68 / `.conclusion` 29 / `working_paper.parsed_data` 9 |
| 直接赋值 `parsed_data` / `file_path` | 48 | |
| 写 artifact 且自己解析底稿路径 | 9 | |
| 兼有内容字段与 SQL 列 | 2 | |

🔴 **`checklist_responses` 那 97 行有一条现成的 lane 却没人进去**：生成器的 `_DOMAINS` 里声明了
`checklist_response_store`，而 overlay 里**零条**裁决用它。这条 lane 是被声明出来、然后空着的 ——
换句话说 236 行里最大的一块（97 行）在结构上已经被识别为同一个域，只差人工裁决。本任务不代替评审
填它（生成器从不发明裁决），但把它记在这里，让下一位不必再重新发现一遍。

### 2. `bypasses_unified_commit` = 261 = **236 未裁决 + 25 已裁决但未迁移**

25 个「已裁决、有理由、仍未迁移」的行是本 spec 后续任务的工作面（`custom` 5、`dedicated_router` 6、
`template_provisioning` 4、`upload_import` 3、`wopi` 2、`f2_word_sync` 2、`oo_callback` 1、
`export_storage_resolver` 1、`rollback` 1）。其中两行是 Task 19 明确交接的：

* **`app.routers.excel_html::rollback_file_version`** —— **签名上做不到**，不是没顾上：它**没有
  `wp_id`**（路由键是 `file_stem`，因此没有 workpaper scope 可开 content version、没有
  `content_revision` 可推进），且把 numeric version 当 route key（Requirement 10.6 明令禁止）。
  整个 `excel_html` 模块是经 `router_registry` 真实挂载的**活的平行权威**。收口只有两条路：把该
  store 绑定到 workpaper 身份，或按 Requirement 12.9 删除 sidecar —— **两者都是产品决策**，且
  Requirement 12.7 要求「删除前必须有等价证据与 rollback 点」，目前两者都没有。
  → **本任务不做**。理由已在 overlay 的 `version_domain_note` 里，
  `test_the_gate_is_red_and_names_its_blocking_rows` 钉住这一行仍在阻塞名单里、且理由文本仍提到
  `wp_id` / `10.6` / `12.7`。
* **`WpMigrationService.migrate_workpaper`** —— 自行用裸 SQL 改写 `parsed_data`，`template_provisioning`
  域（不属 Task 19 的六个域）。裁决已在 overlay 里（Task 19 README 说它 `unadjudicated` 是**过时的**：
  清册实测 `status=adjudicated`），但未迁移，且它 `swallows_exceptions=true`。

另外值得记一笔：**统一提交边界自己也在这 261 里** ——
`WorkpaperSyncRepository.bump_content_revision` 是 CAS 的最内层写入者，它当然不会调用
`ContentMutationService`（它是被调用方），却因此被记成「绕过」，且 `unadjudicated`。这是谓词的
**分层缺陷**（把「唯一允许的版本写入者」与「绕过统一入口的 writer」混在一个判据里），不是真实欠账。
本任务**没有**动它 —— 修它要在生成器里引入「统一提交实现层」这个第三类，属谓词分层变更，会动到
Task 3 的分母定义；在这里顺手改，等于用「让数字好看」的方式碰一个共享判据。**已登记，建议单独立项。**

### 3. `multi_resolver` = 4（**已移交 Task 30**，其后再移交 Task 71 —— 见本节末尾）

四行全在 `wp_onlyoffice_router`（`get_sheet_onlyoffice_config` / `get_sheet_wopi_contents` /
`get_whole_excel_grid` / `post_sheet_onlyoffice_callback`），Task 12 的 resolver 矩阵里**已登记
`status=deferred`**，理由原文：「OO config/callback 的 substrate 必须是 room/staged representation，
依赖 **Task 21** room_service 与 **Task 25/26** coordinator」。

这里原本是一处真实的循环依赖：这条准则要归零需 Task 21/25/26 先落地，而 Task 20 又是 Task 25 的
依赖 ⇒ 按原措辞门永远打不开。**spec 层裁决已完成**：tasks.md 把该 criterion 移交给 **Task 30**
（Task 20 侧写「已移交 Task 30」，Task 30 侧写「自 Task 20 移交至本门」并把这 4 个函数名逐一列出）。

🔴 **移交 ≠ 无人守，也 ≠ 门里删掉计算**：归属方正是靠
`check_workpaper_writer_revision_gate.py` 的 `multi_resolver` 计数验零，所以门**仍在算**这条准则。
守卫按此分了两张表（`_TASK20_CRITERIA` / `_RELOCATED_CRITERIA`），并把「归属」本身交给 tasks.md 的
两句显式交接语派生（§6 的 `test_the_criteria_homing_agrees_with_tasks_md`），文档与判据表一旦不一致
就红。

📌 **2026-08-29 后续（第二跳，本任务结论不变）**：Task 30 实测该 criterion 在**它那个位置**同样不可
满足（供给只能来自 Task 36 的逐 entry `finalizeCandidate`，而 Task 36 依赖 Task 30 —— 同形的第二次
成环），故 tasks.md 已把裁决归属再移交 **Task 71**（`legacy_delete` gate 成员）。移交链因此是
**Task 20 → Task 30 → Task 71**；本节标题里的「已移交 Task 30」指的是**第一跳**，Task 20 的放手对象
没有变。守卫侧随之改成派生而非硬写：表名 `_TASK30_CRITERIA` → `_RELOCATED_CRITERIA`，三个测试
改名（`test_the_gate_still_evaluates_the_relocated_criterion` /
`test_the_gate_names_exactly_the_rows_the_owner_must_clear` /
`_task71_multi_resolver_rows_from_tasks_md`），归属推导改成**链式**（`relinquished == ["20","30"]`、
`assumed == ["71"]`）—— 原来的单值 dict 会被第二跳把第一跳静默覆盖掉。详见
`evidence/task30-closure-gate/README.md` 的「2026-08-29 spec 修订」一节。

⚠️ **一处 tasks.md 与门行为的措辞不一致，本任务未改（登记）**：Task 20 正文写的是「本门**不再评估**
该 criterion」，而门实际上仍把 `multi_resolver` 计入 `has_debt` ⇒ 它仍参与本门的退出码（4 行）。
两者的正确读法是守卫里那句「换了门，不是没了门」。**没有改成按归属分区退出码**，理由是：本门另有
913 条 Task-20-自有阻塞事实，减掉这 4 条对红绿结论零影响，而「让门少阻塞 4 行」正好是本任务反复
拒绝的那类改动 —— 在结论不变时收窄一道门，纯是下行风险。建议在 Task 30 临近收口时一并处理
（届时 4 这个数字才真的决定红绿）。

## 五、注入实验（Task 20 的「注入旧路径必须打红」）

`inject_task20_legacy_version_paths.py` —— 往**生产源码**注入，重生成清册，量门的准则计数，还原，
再重生成并校验 digest 回到基线。**5/5 RED**，全部字节级还原、digest 复原：

| # | 注入点 | 注入内容 | 门新点名的准则 |
|---|---|---|---|
| I1 | `wp_html_save::save_html_data`（已迁移） | `wp.file_version = ... + 1` | `keeps_legacy_write_path_beside_unified_commit` + `writes_legacy_version_field` |
| I2 | 同上 | `wp.parsed_data['_version'] = 2` | 同上两条 |
| I3 | 同上 | `await db.commit()` | `keeps_legacy_write_path_beside_unified_commit` + `owns_direct_commit` |
| I4 | `wp_storage_service::save_version` | `wp.file_version = ... + 1` | `bypasses_unified_commit` + `writes_legacy_version_field`（**失去** snapshot 类别） |
| I5 | `excel_instrumentation::stage_and_register_candidate` | `bump_content_revision(...)` | `representation_upgrade_increments_business_revision` |

注意 I3：它既不写 legacy 字段也不写 `content_revision`，**只有把「第二个事务边界」也算进双 revision
准则**才抓得到（Requirement 2.4 / 13.1）。M09 是这一条的反向变异。

顺带证明了清册的 fail-closed：五次注入后**未**重生成时，门一律拒绝评估
（`source digest is stale`，`stale_gate_refused=true`），而不是拿旧文件照旧评估。

## 六、变异检验（`mutation_report.json` / `mutation_report_scope.json`）

19 条，落点是本任务的「生产代码」= **判据机器**（生成器 + 门），其中 M20 落在 design.md（provenance
判据的唯一可能 falsifier 就是改 spec 原话）。**18 RED / 1 GREEN**。

**M16–M20 是 §〇 分母判据的检验**（`mutation_report_scope.json`），**5/5 RED，且每条都命中预测的那
一条测试**，无 GREEN / 无 WRONG-TEST / 无 ANCHOR-MISS：

| # | 收窄手法 | 落点 | 命中判据 |
|---|---|---|---|
| M16 | `_APP_ROOT` 收到 `app/routers` ⇒ services 侧 writer 整批离开分母 | 生成器 | `..._denominator_is_every_production_module_under_backend_app` |
| M17 | 往「非交付目录」排除表塞 `routers` ⇒ 伪装成无害排除规则 | 生成器 | `..._production_source_predicate_...`（+ 分母判据同时红） |
| M18 | 删 `checklist_responses` 内容存储 ⇒ 97 行一次性离开分母 | 生成器 | `..._both_workpaper_content_stores_stay_in_the_denominator` |
| M19 | 把 `template_provisioning` 收进 `_REQUIRED_DOMAINS` ⇒ **只抹掉反驳窄读法的那条证据**，不改任何计数 | 门 | `..._universal_scope_is_the_specs_own_definition_not_this_files` |
| M20 | 把 design.md 的「所有 writer」改成自指的「清册内 writer」 | design.md | 同上 |

M19 值得单独记：它**一个计数都不改**，只让 `adjudicated - required` 变空，于是「Task 3 自己越过了
枚举」这条反证消失、窄读法再无实证反驳。这类「删证据而不改数字」的变异是最难察觉的一档，也正是
provenance 判据存在的理由。

M01–M15（`mutation_report.json`）**13 RED / 1 GREEN**：

**唯一的 GREEN 是 M04，一个声明期就写明的负对照**（把 `ast.Import` 分支已有的绑定重写一遍 = 无效
变异）。它存在的意义是证明判定不是「改任何一行都红」。因此 `--run all` 的**退出码是 1 by
construction**，不是失败信号；逐条判定在报告 JSON 里。

首轮 **10 RED / 2 GREEN / 2 WRONG-TEST**，四条非 RED 逐条归因：

| 变异 | 首轮 | 归因 | 处置 |
|---|---|---|---|
| M04 | GREEN | **无效变异**（声明期即预期） | 保留为负对照 |
| M08 | GREEN | **判据缺陷**：反例同时触发两条判据（「没读统一计数器」∧「读了 legacy 字段」），拿掉任一条仍红 ⇒ 第一条是不可达分支。正是 Task 19 记录的「两条拒绝共用一个出口」形态 | 补 case (b2)：快照名不含任何版本号、一个 version 字段都不读 ⇒ 只剩一条判据命中。复跑 RED |
| M06 | WRONG-TEST | **判据缺陷**：两条清册级判据读的是**磁盘**清册，而变异只改生成器不重生成 ⇒ 它们看到的还是旧文件、恒绿 | 改读新增的 `regenerated` fixture（现场从源码推导）。复跑 RED |
| M14 | WRONG-TEST | **脚本缺陷**：锚点选在 `try:` 行，`insert` 落进 try 块导致缩进错误 ⇒ 源码 SyntaxError ⇒ 生成器直接抛、守卫全变 **ERROR 而不是 FAIL**（差集判定看不到 ERROR） | 改锚到同缩进的独立语句行。复跑 RED |

M06 的教训值得单独记：**清册级判据必须读现场重新推导的清册**，读磁盘那份等于把判据钉在「上次谁跑过
`--apply`」上。磁盘与源码一致由 `test_inventory_on_disk_matches_the_ast` 单独保证，两者分工不重叠。

## 七、清册行差异归因（`inventory_row_diff.json`）

`diff_task20_writer_inventory_rows.py` —— Task 19 用手写 MINE 名单（它改的是几个具体函数）；本任务改
的是**谓词本身**，影响面天然全表，名单式归因没有意义，改用**形状式归因**：剥掉本任务新增的键后两侧
必须逐字节相等，剩下的差异只允许落在三类里。

* 行分母 **320 → 320**（新增 0 / 删除 0）
* 变动 **320** 行，`unattributed_rows = 0`：
  * `MINE-NEW-KEYS-ONLY` **244** —— 只多出新增的 fact/verdict 键（值为空）
  * `MINE-CHARACTERIZATION-CALLSITE` **75** —— characterization 证据变化
  * `MINE-ARTIFACT-SNAPSHOT-CATEGORY` **1** —— `save_version` 的 bypass 翻转
* 新增 fact 键：`artifact_write_targets` / `representation_candidate_calls` / `revision_bump_calls`
* 新增 verdict 键：`artifact_snapshot_only` / `writes_business_content` /
  `keeps_legacy_write_path_beside_unified_commit`

`workpaper_resolver_migration_matrix.json` 一并重生成（清册 digest 变了）：**79 行逐字节不变**，只有
`inventory_digest` / `inventory_source_digest` / `matrix_digest` 三个链接字段变化 ⇒ 本次改动对 resolver
域零影响（`resolver_matrix_before.json` 是对照快照）。

## 八、测试

| 范围 | 结果 |
|---|---|
| `workpaper_sync/test_task20_writer_gate.py`（§1–§6 共 28 条 + §7 分母 4 条 = 32 条） | **32 passed** |
| `test_workpaper_writer_inventory.py`（Task 3，同批搬动 2 处期望） | **28 passed** |
| 两个守卫文件合跑（变异基线） | **60 passed**（96s）；`baseline_backend_passed` 已同步 56 → 60 |
| 反向引用面 + Task 12/15/16/17/18/19 | **400 passed / 1 failed → 修后 green**（那 1 条是 Task 12 矩阵 freshness，重生成后过） |

§7 的辐射面只有这两个守卫文件：本轮改动是**只加判据**（新增 4 条测试 + 一个共享 `source_scan`
fixture），生成器、门、清册、overlay 一个字节未动 —— 门的 917 条阻塞事实与各准则计数在改动前后
逐条相同（改动后复跑：236 / 261 / 4 / 208 / 917，退出码 1）。

同批搬动的两处期望值（改动与所有者同批，各有变异 falsifier）：

* `test_adjudications_are_domain_labels_not_bypass_exemptions` —— bypass 的再推导加入
  `artifact_snapshot_only` 项，并要求拿到类别的行必须在**源码事实**上成立（M07 是 falsifier）；
* `test_only_the_migrated_writers_reach_the_unified_commit_boundary` —— bypass 计数算式显式减去
  **具名的**快照类别集合（写成 `== {save_version}`，名单漂移即红），而不是让算式自己少一个。

## 九、未验证 / 遗留（不含已在 §四 具名的阻塞项）

* **无真库行为测试**。本任务的判据全部是 AST 结构 + 真实执行（现场跑生成器/门），没有新增 `_pg.py`。
  门本身不碰数据库，所以这不是缺口；但「一次业务应用恰一次 revision」这类承诺仍只由 Task 15/18 的 pg
  测试覆盖。
* **characterization 谓词的 HTTP 路由证据未实现**（§三.1），52 行被低估。
* **`bump_content_revision` 被记成「绕过统一入口」**（§四.2）—— 谓词分层缺陷，建议单独立项。
* **`checklist_response_store` 是被声明出来又空着的 lane**（§四.1）—— 236 行里最大的一块（97 行）
  结构上已归为同一域，只差人工裁决。生成器从不发明裁决，故本任务不填。
* **`after_save_still_increments_revision` 在 `entries` 侧分母为 0**（§一）—— 该准则经退役台账正向
  评估、确实在跑，但 `entries` 里的 `if domain == "orchestrator_side_effect"` 分支当前不可达。它不是
  假绿（台账那条会抛错），但也不该长期是不可达分支；等有第二个副作用 handler 进 `entries` 时复核。
* **tasks.md 说「本门不再评估 `multi_resolver`」，门实际仍把它计入退出码**（§四.3）—— 措辞与行为
  不一致，本任务有意未改（结论不变时收窄门是纯下行风险），留到 Task 30 收口时处理。
* 门的 `owns_direct_commit`(105) / `non_canonical_resolver_only`(64) / `unadjudicated_resolver`(34)
  不在 Task 20 点名的准则里，本任务未推进，计数与改造前一致。

## 十、文件清单

| 文件 | 角色 |
|---|---|
| `inventory_before.json` / `overlay_before.json` | 改造前快照（归因基线） |
| `inventory_row_diff.json` | 320 行逐条归因，`unattributed_rows=0` |
| `characterization_credit_delta.json` | 52 行失去记账 / 0 行新增的完整名单 |
| `gate_blockers.json` | 门的每条准则前后计数 + 完整阻塞行名 + 按模块分布 |
| `injection_report.json` | 5 条生产注入 → 门准则计数变化 + 还原核验 |
| `mutation_report.json` | M01–M15 逐条判定（13 RED / 1 GREEN 负对照） |
| `mutation_report_scope.json` | M16–M20 逐条判定（§〇 分母判据，5/5 RED 且全部命中预测项） |
| `resolver_matrix_before.json` | resolver 矩阵对照快照（79 行不变） |
