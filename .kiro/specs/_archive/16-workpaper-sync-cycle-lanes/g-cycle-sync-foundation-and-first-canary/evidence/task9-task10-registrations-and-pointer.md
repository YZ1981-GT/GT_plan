# Task 9 / 10 证据：BP-6/9/11 登记（复用上游守卫）+ GC-1 pointer 隔离

**执行时间**：2026-09-27

## Task 9：BP-6 / BP-9 / BP-11 —— **上游守卫已覆盖，本 spec 不重造**

需求 7.3 与 GF-P21 都要求「复用既有 G 产物，不重造」。核上游守卫
`backend/tests/workpaper_sync/test_task49_g_cycle_migration.py`（**96 个 test**）的覆盖面：

| 本 spec 需求 | 上游守卫里的判据 | 覆盖 |
|---|---|---|
| 2.5 BP-6（manifest capability 是组件级默认值，不得为对齐而改 overlay） | `test_manifest_mirror_divergence_is_registered_not_silently_equal` · `test_capability_is_enum_or_explicitly_pending` · `test_capability_matches_honest_capability` · `test_capability_blockers_reference_real_preconditions` | ✅ |
| 2.4 BP-9（`useG1DualMode.ts` 跨 G1-E1 共用，不删，E1 行为不变） | `test_cross_cycle_shared_composable_is_registered_with_its_consumers`（逐消费方核 import + **全仓反查**消费方恰是那两个 + 校验 `e_cycle_deferred_registration` 的重述解锁条件） | ✅ |
| 2.6 BP-11（不可达旧桩 `notice=0`、不进受管清单） | `test_unreachable_stub_is_registered_and_still_has_zero_inbound_edges`（按**模块边**判、带反向自检）· `test_in_runtime_index_flag_recomputes_and_g_cycle_has_no_unreachable_workbook` | ✅ |
| 顺带：AC 1.4 notice 义务 | `test_every_pending_entry_host_mounts_the_notice` 等 4 条 | ✅ |
| 顺带：GC-5 null 占位双向锁 | `test_payload_null_placeholder_is_declared_both_ways` | ✅ |
| 顺带：BP-7 实际缺陷面 | `test_positional_row_identity_defects_are_real_and_exhaustive` | ✅ |
| 顺带：BP-10 80 处重复声明 | `test_duplicated_item_id_literal_scale_is_recomputable` | ✅ |
| 顺带：FD-2 http 客户端探针 | `test_http_probe_is_client_specific` | ✅ |

⇒ **本 spec 不新增 BP-6/9/11 判据**（新建会变成同一不变式两处各写一份，改一处另一处不红）。
本 spec 的义务落在「让上游守卫**保持真实且全绿**」上 —— 见下。

## 🔴 上游守卫本轮从 2 红修到 96 全绿（一条是我引起、一条是既存）

跑之前实测：`2 failed, 94 passed`。

### 红①：`test_bp5_g1_fallback_sheet_labels_point_at_nonexistent_tabs` —— 我的 Task 5 引起

该判据原本断言「**真的**有 5 条不是权威 tab」+ `status == 'REGISTERED_NOT_FIXED'`，
断言消息里逐字写着「若已修好，请更新 BP-5 的 status 与本判据」。
Task 5 修好后它按设计打红。处置（照该指引）：

* slice `BP-5.status`：`REGISTERED_NOT_FIXED` → **`FIXED`**，并新增 `fixed_note`
  （逐条改名清单 + 原 `why_not_fixed_here` 的复核结论 + ACNR 旁证）；
* 守卫改写为「18/18 逐字命中」+ **正向锁空格**（`by_code["G1A"] == '…G1A '`）；
* 缺陷触发路径（`resolveOoSheetName` → `resolveG1SheetLabel` → 兜底表回落）的逐字断言
  **保留不动** —— 路径仍在，只是兜底表的值现在是对的；删掉它会让「将来把值改错」重新无声。

🔴 顺带纠正了 BP-5 原 `why_not_fixed_here` 的理由①（「改成带空格的值会让按『编码紧贴表名、
无空格』约定写的比对行为改变」）：按值复核**不成立** ——
`resolveG1SheetLabel` 的正则是 `new RegExp(\`${escaped}\\s*$\`)`，本就容忍尾随空白；
`extractG1SheetCode` 用 `sheetName.match(/(G1A|G1-\d+)/i)`，对 `…G1A ` 照样返回 `G1A`。
理由②（把兜底表换成 render-config 下发）仍未做，但它是**另一条**更彻底的修法，不是本条的阻塞。

### 红②：`test_unreachable_stub_is_registered_and_still_has_zero_inbound_edges` —— **既存**失败

根因：`htmlRendererRegistry.ts` 在 commit `82f58ea44`（feat(d4-ipo)）被**拆分重构**
（1465 行 → 361 行），组件登记移到 `registry/entries/{core,forms,programs,confirmations,
reports,specialized}.ts`；清册登记的那条**同名局部别名**
`const GtG6OtherBondEcl = defineAsyncComponent(() => import('./GtG6OtherBondInvestmentEcl.vue'))`
随之消失。现算：`htmlRendererRegistry.ts` 全文 `GtG6OtherBond` **零命中**。

**不是我引起**：`git status` 显示该文件未被本轮改动；`git log -S "const GtG6OtherBondEcl"`
最近一次触碰即 `82f58ea44`（HEAD 的祖先）。
同一事实也已让**前端 vitest** 红了（工作树 `vitest-output.txt` 逐字记着
`× G6 集成: 注册表 ECL -> InvestmentEcl > htmlRendererRegistry imports GtG6OtherBondInvestmentEcl`）。

**生产没有问题**：G6-ecl 在 `registry/entries/specialized.ts` 以**直接 import** 登记
（`componentType: 'g6-other-bond-investment-ecl'` → `import('../../GtG6OtherBondInvestmentEcl.vue')`），
且**同名别名已随重构消失** —— 正是 BP-11 登记里警告的那个「按符号名判会误报」的坑被消除了。
旧桩 `GtG6OtherBondEcl.vue` 仍在磁盘、仍零入边（BP-11 实质结论不变）。

处置：
* 清册 `unreachable_stub_to_delete.registry_homonymous_alias` 改为
  `alias_still_exists=false` + `removed_by`（归因到 `82f58ea44`）+
  `live_registration_now`（现行登记处 / componentType / import specifier / 形态）；
  `guard` 字段第②条同步改为「按拆分后的子模块登记判」；
* 守卫改为聚合读 `registry/entries/*.ts`，并新增两条：
  `htmlRendererRegistry.ts` 里**不得**再出现 `GtG6OtherBond`（别名复活即红）、
  清册登记的现行登记处必须真有该 componentType 与该 import；
* 🔴 判据形态**不改回按符号名** —— `components.d.ts`（unplugin-vue-components 生成物）与
  `workpaperSyncManifest.generated.ts`（把旧桩登记为 hostPath）里仍有该字符串，
  按符号名判照样误报。「按模块边判」这条纪律与别名在不在无关。

两条修复由幂等脚本 `backend/scripts/fix/fix_g_slice_bp5_status_and_registry_alias.py`
承载（`--check` / `--apply`），**写盘前先现算核实前提**（别名真的没了 / specialized.ts 真有登记 /
G1A 标签真带空格），前提不成立就拒绝改登记 —— 防把一种失真换成另一种。

结果：`96 passed`。

## 变异脚本同步：61 个锚点从 3 条失配修到 0 条

`backend/scripts/diagnose/mutate_task49_g_cycle_migration_guards.py` 有 3 条锚点已失配
（锚点失配 ⇒ 变异恒失效 ⇒ 对应判据**没有自省**）：

| 变异 | 失配原因 | 处置 |
|---|---|---|
| **M32** | 本轮 BP-5 修复令旧值（不带空格）消失 | **方向反转**：原来是「把错的改对，看守卫是否逼作者改 status」，现在是「把对的改回错的（去掉尾部空格），看守卫是否阻止回退」 |
| **M48** | registry 拆分令同名别名消失 | **重指向** `registry/entries/specialized.ts` 的直接 import（新增 `SPECIALIZED_ENTRIES_TS` 常量） |
| **M59** | **既存漂移**：`SYNC_ADAPTER_REGISTERED_ENTRY_IDS` 已从手工 `= []` 改成派生值（`WORKPAPER_SYNC_MANIFEST.filter(e => e.capability === 'bidirectional')`） | **重指向** filter 谓词那一行，放宽成「全都算已注册」（语义等价于原变异：前端谎报某 entry 已注册） |

🔴 M59 第一版锚点写成**跨行**，被脚本自带的自检拦下：
「anchor 含换行 —— 工作树是 CRLF，跨行锚点在字节/整行匹配下必然 MISS」⇒ 改单行锚点。

三条变异实跑验收（`--run M32,M48,M59`）：

```
M32 判定 RED  还原=True  命中 want：…::test_bp5_g1_fallback_sheet_labels_point_at_nonexistent_tabs
M48 判定 RED  还原=True  命中 want：…::test_unreachable_stub_is_registered_and_still_has_zero_inbound_edges
M59 判定 RED  还原=True  命中 want：…::test_registered_entry_ids_agree_with_the_slice
RED 3 / OK 3
```

`--check-anchors`：**61 条全部命中，0 失配**。

⚠️ 过程记录：首次运行被终端中断，`specialized.ts` 与 `workpaperEntrySyncNotice.ts` 一度留在变异态
（各有 `.mutbak`）。已用 `--restore` 还原并逐文件核对（`git diff` 空 + 关键行逐字复核 +
`.mutbak` 残留为 0）。**中断变异脚本必须立刻查 `.mutbak`**。

## Task 10：GC-1 pointer 隔离判据（GF-P5）

新建 `backend/tests/workpaper_sync/test_g_foundation_p5_gc1_pointer_isolation.py`（**9 passed**）。
它同时是下游 `g4-g6-shared-workbook-three-entry-lanes` 的 **G46-P1 / P2 / P3** 的地基。

**复用 F2 的真构造脚手架，不重造**：`registration()` / `manifest_of()` /
`install_contract()` / `StubAdapter` 直接 `from tests.workpaper_sync.test_f2_p2_rg3_matcher_overlap import`
（F2 与 G4/G6 形态同型：一册多 entry 共用幻影码 ⇒ 靠互斥 `sheet_keys` 分域；抄一份会变判据双真源）。

判据清单：

| 判据 | 内容 |
|---|---|
| `test_three_same_code_entries_register_and_resolve_independently[G4/G6]` | 🔴 **BP-8 真验收点**：三条同码 entry **依次**真跑 `registry.register()`，每注册一条就重新解析**已注册的全部** —— 任一条被顶掉即红。只验前两条会漏掉「第三条顶掉前两条」 |
| `test_sheet_keys_are_pairwise_disjoint[G4/G6]` | 三条 matcher 两两 `overlaps() == ()` 且 `sheet_keys` 交集为空 |
| `test_mutation_pointer_by_wp_code_makes_them_collide[G4/G6]` | 变异：pointer 改按 wp_code（= `sheet_keys` 置空、域退化为整册）⇒ 第二条注册即 `MatcherOverlapError` |
| `test_g4_and_g6_do_not_collide_with_each_other` | 六条一起注册全部成功、逐条按 `entry_id` 解析正确（否则「分域」这个解法本身不成立） |
| `test_entry_state_primary_key_is_entry_id_not_wp_code` | 读 ORM：`WorkpaperSyncEntryState` 主键 == 复合键 `(wp_id, entry_id)`；**不得**有不含 `entry_id` 的唯一约束/唯一索引 |
| `test_reverse_self_check_fk_constraints_are_not_counted_as_unique` | 反向自检（见下） |

六条 lane 的 `sheet_keys`（取 g4-g6 design 的受管区）：
`g402-managed` / `g407-managed` / `g409-managed` · `g602-managed` / `g605-managed` / `g611-managed`。

### 🔴 判据自身的一次假红（记下来防重犯）

`test_entry_state_primary_key_is_entry_id_not_wp_code` 第一版遍历
`state.__table__.constraints` 的**全部**约束，把 `wp_id` 上的 **`ForeignKeyConstraint`**
当成「只按 wp_id 唯一」，判出一个**并不存在**的 BP-8 缺陷 ——
真实 ORM 是 `wp_id` / `entry_id` 双 `primary_key=True` 的复合主键，完全正确。
修法：只看 `PrimaryKeyConstraint` / `UniqueConstraint` / `unique=True` 的索引，
并补一条反向自检断言「`wp_id` 上确实有单列外键」——证明那层过滤不是多余防御。

⇒ **GC-1 在 ORM 层已成立**，六条 lane 的实施只需保证 pointer/entry_state 一律按 `entry_id` 写。
