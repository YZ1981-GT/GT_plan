# Task 19 证据：上传 / WOPI / custom / F2 / rollback / 历史恢复 writer 迁入统一 revision 域

Requirements 2.2、2.11、9.11、12.6、12.7 · Property 50、Property 61

Task 19 分两个增量交付。增量一（custom cells 端点 / WOPI PutFile / 离线上传）与增量二
（F2-22 / F2-23 / 模板迁移回滚 / 历史快照回滚 / `.versions` 快照）共用同一套判据与清册。

---

## 一、逐 writer：lane 与理由

| writer | lane | 为什么是这条 lane |
|---|---|---|
| `custom_workpaper_cells::update_custom_cells` | A（`commit_bytes`，`custom_authoritative_ooxml`） | custom 底稿的权威是 xlsx 本体；投影（grid / parsed_data）永不作为内容提交（Req 2.11 / P50）。迁移后版本/内容/commit facts 全空，整行离开 writer 集合，正面判据在 `retired_writers` 台账 |
| `wopi_service::WOPIHostService.put_file` | A（`opaque_single_onlyoffice`） | WOPI PutFile 收到的就是 OOXML 本体 |
| `wp_download_service::WpUploadService.upload_file` | A（`opaque_single_onlyoffice`） | 离线上传的载荷就是 OOXML 本体；冲突早检查改比 `content_revision` |
| `_f2_stocktake_plan_sync::_save_fields`（F2-22） | A（`opaque_single_onlyoffice`） | **manifest 事实**：`workpaper_sync_entry_manifest.json` 里 F2 entry（`xlsx/gt-f2-stocktake-bundle`）`capability=single_onlyoffice` ⇒ 权威内容是 docx 本体，projection lane 会在 `HtmlOnlyCommitPlan.__post_init__` 直接拒绝。`checklist_responses` 里的 fields JSON 是派生视图 |
| `_f2_stocktake_summary_sync::_save_fields`（F2-23） | A（同上） | 同上；`entry_id` 带 sheet code，两张表不共用 entry scope |
| `wp_migration_service::WpMigrationService.rollback` | B（`commit_projection` → `stage_html_projection` + `commit_html_projection`） | 它恢复的**就是**结构化 projection（`working_paper.parsed_data`），手上没有 OOXML 字节可发布成 representation；凭空造一个空白 xlsx 是 Req 3.9 禁止的 |
| `version_trail_service::VersionTrailService.rollback_to_snapshot` | B | 恢复的是 `checklist_responses` 行，同上 |
| `wp_storage_service::WpStorageService.save_version` | 不进 lane | 它只把**当前**文件复制进 `.versions/`，内容一个字节没变 ⇒ 没有业务内容可提交。迁移内容 = **失去自己的计数器**，快照名改跟随真正在动的 `content_revision` |

两条 lane 的必需步骤元组互斥（A 有 `representation`/`entry_pointer` 无 `current_pointer`，
B 反之），因此谁也无法借另一条的完整性检查蒙混过关，也不存在跳过开关。走错 lane 被拒
两次且来源独立：**声明侧**（`HtmlOnlyCommitPlan.__post_init__` 看调用点声明的
`capability`）与**数据库事实侧**（`commit_html_projection` 查该 entry 是否已有
representation pointer）。装配层**不得**写死 capability —— 写死会让声明侧那道拒绝对所有
调用方变成不可达分支（Task 18 实测过的缺陷形态），`test_the_projection_lane_capability_is_declared_at_the_call_site` 逐条钉住。

## 二、顺带修掉的一个真实缺陷（lane 层）

projection lane 原本把 `working_paper_content_version.source` 与 outbox payload 的
`source` **写死成 `html`**。对 `wp_html_save` 是对的，对两条恢复 writer 是错的：一次回滚
在 evidence 与 timeline 里长得和一次用户编辑完全一样，而 `source` 正是 Requirement 2.3
点名必须落库的分桶依据。现在 `HtmlOnlyCommitPlan.source` 由调用方给出（默认仍是
`html`，因此 `wp_html_save` 行为逐字节不变），content version 与事件 payload 读同一个
`plan.source`。M28 / M29 是这两个方向各自的 falsifier。

## 三、被阻断、**未**迁移的一行（必须带着理由进 Task 20）

`app.routers.excel_html::rollback_file_version` —— 不是「没顾上」，是**签名上做不到**：

1. 它**没有 `wp_id`**。路由键是 `file_stem`，操作对象是
   `storage/projects/{pid}/excel_html/{file_stem}.structure.json`，因此没有 workpaper
   scope 可以开 content version，也没有 `content_revision` 可推进；
2. 它把 numeric version 当 **route key**（`POST /versions/{file_stem}/rollback/{version}`），
   而 Requirement 10.6 明令禁止。

整个 `excel_html` 模块是一套**活的**平行权威（自己的 structure.json、自己的版本快照、
自己的编辑锁、自己的 xlsx 回写），经 `router_registry` 真实挂载。收口只有两条路：把该
store 绑定到 workpaper 身份，或按 Requirement 12.9 删除 sidecar —— 两者都是产品决策，且
Requirement 12.7 明确要求「删除前必须有等价证据和 rollback 点」，目前两者都没有。裁决
理由已写进 overlay 的 `version_domain_note`。

## 四、清册与门（`inventory_row_diff.json`）

基线 = `inventory_before.json`（Task 19 之前）。`inventory_checkpoint_increment1.json` 是
增量一交付后的中间态，用来把两个增量的行区分开。

* 增量二后：`bypasses_unified_commit` 266 → **262**、`file_version` writer 6 → **5**、
  `owns_direct_commit` 107 → **105**。
* 21 条变动行**逐条归因**，`unattributed_rows = 0`：`MINE`（目标函数 / 裁决说明）、
  `MINE-LINE-SHIFT`（同文件纯行号位移，抹平行号字段后 facts 逐字节相等）、
  `MINE-COLLATERAL`（见下）。
* `workpaper_resolver_migration_matrix.json` 一并重生成：**79 行逐字节不变**，只有
  `inventory_digest` / `inventory_source_digest` / `matrix_digest` 三个链接字段变化 ——
  本次改动对 resolver 域零影响（`resolver_matrix_before.json` 是对照快照）。

归因**可复现**：`backend/scripts/diagnose/diff_workpaper_writer_inventory_rows.py`
（`MINE` 名单手写、不从 diff 反推；有 unattributed 即退出码 1）。

### 🔴 顺带发现的判据缺陷（Task 3 的谓词，不在本任务修复范围）

`has_characterization_test` 是**按名称就近**匹配的。两个实测例证：

1. 我为 `save_version` 新写的守卫提到了 `wp_storage_service`，于是同模块的
   `list_versions` 也被记成「有 characterization 测试」（`MINE-COLLATERAL`）；
2. `WpMigrationService.rollback` 在本任务开始前就被记成「有测试」，而那条测试
   （`test_wp_template_migration_property.py::TestProperty2RollbackRestoresData`）用
   `copy.deepcopy` 模拟回滚，**从未调用** `rollback()`。

后果：门里的 `writer_without_characterization_test`（165）是**高估覆盖**的乐观数字。
Task 20 若要用它作判据，得先把谓词从「名称就近」改成「真的调用了这个函数」。

## 五、测试

| 文件 | 结果 |
|---|---|
| `workpaper_sync/test_task19_writer_migration.py` | **70 passed**（新增 §五~§七 共 15 条判据） |
| Task 15/16/18/19 + `test_v151_schema_contract.py` 合跑 | **210 passed** |
| 反向引用面（13 个文件，见下） | **275 passed / 4 failed**，4 条全部预先存在 |
| `test_workpaper_writer_inventory.py` | **28 passed**（两处期望集合随生产同批搬动） |
| `workpaper_sync/test_task12_canonical_resolver.py` | **99 passed**（重生成 resolver matrix 后） |

预先存在的失败（与本任务无关，逐条给出根因）：

* `test_version_trail_integration.py::TestRollbackPermission`（3 条）—— 失败在
  `enforce_wp_gate` → `wp_bound_gate.resolve` → `_deny`（404），根本没走到
  `rollback_to_snapshot`；属并发的 visibility-isolation spec，涉及文件我一行未改；
* `test_wp_template_migration_integration.py::test_full_migration_flow` ——
  `ImportError: cannot import name '_read_xlsx_structure'`（该私有函数已不存在）；
* `test_archive_deprecated.py`（2 条）—— `X-Confirmation-Token` 中间件 403 与 Redis
  event-loop 503，环境性。

**`test_v151_schema_contract.py` 的悬案已裁决**：本次运行 **19 passed**（单跑与合跑、
`-p no:randomly` 与默认随机序都通），Task 18 的观察成立，Tasks 16/17 的 3 条失败不复现。

## 六、变异检验（`mutation_report_increment2.json` + `..._green_retry.json`）

18 条新变异，落点：`wp_migration_service` / `version_trail_service` /
`wp_storage_service` / 两个 F2 模块 / `content_mutation`（lane 的 source 透传）。

* 首轮 **16 RED / 2 GREEN**；两条 GREEN 都是**守卫缺陷**（不是无效变异），修完复跑
  **2 RED** ⇒ 合计 **18/18 RED**。
* 全 42 条（M01–M42）`--check-anchors` **42/42 OK**，可复现性未漂移。

### 两条 GREEN 的归因（都是同一类缺陷：判据没落到调用点）

* **M33**（`html_data={"checklist_responses": data_json}` → `html_data={}`）：接线判据只
  断言 `html_data` 这个**关键字在不在**，从不看里面是什么 ⇒ 空载荷照样绿。后果是
  content version 的 projection digest 与实际落库内容无关，任何两次回滚算出同一个
  hash。补 `test_the_projection_payload_comes_from_the_restored_snapshot` 后 RED。
* **M36**（F2-23 的 `entry_id` 丢掉 sheet code）：原判据自己拿 `_SHEET_CODE` 去调构造器，
  证明的是「构造器**能**产出两个不同 entry」，从不看 writer 调用点传了什么 ⇒ 补调用点
  AST 断言后 RED。

M31 首版用了跨行锚点，`--check-anchors` 直接判 ANCHOR-MISS（CRLF 工作树）；改单行注入
（在写内容之后再读一次 revision）同时暴露出原判据只看**第一次** revision 读取的漏洞，
判据随之改成断言 `max(revision_reads) < update_at`。

## 七、未验证 / 遗留

* **无真库行为测试**。本增量的判据是 AST 结构 + 真实执行（替身 session / 真实临时文件），
  **没有**新增 `_pg.py`。「恰一次 business revision」「同一个事务」「artifact 先耐久再写
  pointer」这三类承诺仍只由 Task 15/18 的 pg 测试在 lane 层面覆盖，**没有**逐 writer 的
  真库证据。增量一的 `test_task19_writer_migration.py` 文件头声称判据在
  `test_task19_writer_migration_pg.py`，**该文件从未存在** —— 悬空承诺，已在此登记。
* `test_version_trail_pbt.py` / `test_version_trail_integration.py` 的回滚用例改用
  `tests/_unified_content_commit_stub.py` 短路提交边界。该替身的文件头明确列出它**不**
  证明什么（单事务 / 恰一次 revision / lane 选择），防止后来者误引为真库证据。
* `WpStorageService.save_version` 仍以 `bypasses_unified_commit: true` 留在清册里：生成器
  把 `shutil.copy2` 算作 writer 事实，而它的 `content_stores_written` 已为空。这是谓词
  层面的分类问题（「artifact-only writer」没有独立类别），Task 20 需要给它一个正面类别，
  否则门永远差这一行。
* `WpMigrationService.migrate_workpaper`（同文件的兄弟方法）仍自行写 `parsed_data` 且
  `unadjudicated`：模板迁移不属本任务六个域，未动。
* `total_versions` 返回值多报 1（复制后才 listdir 再 `+1`）：既有形态，无消费方，本任务
  只逐字钉住现状（见 `test_the_storage_snapshot_no_longer_invents_a_version` 的注释），
  不顺手改返回值语义。
