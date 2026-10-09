# Task 8 · 选项 C 根治落地取证（G9 首条）

spec: `g-cycle-single-region-detail-lanes` · Task 8 · 2026-09-27

用户拍板：「你根据模版内容做根治，直接修改，改前端。要理解模版的编制思路和逻辑」
⇒ 阻塞 `evidence/task8-blocker-column-model-mismatch.md` 的四选项里取 **C（改前端对齐模板）**。

模板编制思路见同目录 `task8-template-design-logic.md`（先做 C-0 再动代码）。
本文只记**落地事实与判据结果**，不复述模板会计口径。

---

## 1. 为什么 C 是唯一不产生第二真源的选项

| 选项 | 后果 |
|---|---|
| A 只接真同构的条 | G9 只有 3 列真对上（A/B/AB）⇒ 双向回写价值近零，且「为什么只这 3 列」无法向审计业务解释 |
| B 立映射设计 spec | 把「前端自研列 ↔ 模板列」的错配**制度化**成一层映射，两套列体系长期并存 |
| **C 改前端** | 前端成为模板的忠实投影；错配消失而不是被翻译 |
| D 部分受管 | 同 A |
| ✗ 硬凑映射 | 现有判据只校验「声明↔模板几何一致」、**不校验**「前端字段语义↔模板列语义一致」⇒ 全绿通过却把 A 列的值写进 B 列 |

移除前端 15 列的依据**不是「模板里没有」而是会计口径错**：模板编制说明 A38-A43 五类全部 FVTPL，
CAS22 下不确认 OCI、不计提减值 ⇒ `ociChange` / `ociCumulative` / `impairmentLoss` /
`impairmentProvision` 四列是**会计错误**；`fairValueLevel` / `valuationMethod` 的权威源是
`公允价值测试表G9-4` / `公允价值层次披露G9-5` 两张表，留在 G9-2 是第二真源；余 6 列模板确实没有。

---

## 2. C-1 ~ C-4：前端

| 步 | 产物 | 要点 |
|---|---|---|
| C-1 | `composables/useG9Detail.ts`（完全重写） | `G9DetailRow` 28 字段按模板列序 **A..AB 逐列对应**；12 条模板公式由 `enrichG9DetailRow` 重算；`G9_SECTIONS` 三段（titleRow 11/18/25）；`migrateLegacyG9Row` + `G9MigrationStats` + 13 项 `DROPPED_LEGACY_FIELDS` |
| C-2 | `g9-other-noncurrent-financial/core/G9TabDetail.vue` | 四 tab（期初 / 变动 / 期末 / 补充）+ 嵌套 `el-table-column` 表达模板两级表头；移除 FVOCI 按钮与 L3 标记；迁移提示 `el-alert` |
| C-3 | 6 处跨表消费方 | 改 fallback 链 `closingAuditedFairValue ?? closingAdjusted ?? closingBalance`（存量数据迁移回写前仍可读，与 `gCycleSourceFv.ts` 现有三级 fallback 同范式） |
| C-4 | `__tests__/useG9Detail.spec.ts` | 35 tests 六组：12 公式 / 未审线 / O 列不进余额 / 迁移+丢弃计数 / 完整性四类 / 集成 |

三条实现层裁决：

- 🔴 **`P=C+M` / `Q=D+N` 走未审线**（期初未审 + 本期变动），**不是**从审定数推。模板逐格实测如此，
  会计上也只能如此：审定数含账项调整，若期末成本从审定成本推，本期调整会被重复计入。
- 🔴 **`O`（计入投资收益的股息）是损益项，不参与任何余额公式**。它在 `M9:O9` 分组下容易被误当变动分量。
- 🔴 **`parsed = computed` 同时产出 list + stats**，不在 computed 里写 ref —— 后者产生求值顺序依赖，
  判据实测踩到（迁移计数时而为 0）。

顺带修掉一处方向错误的跨表回写：`g9FvCrossHelpers.pushG9FvToDetail` 把 G9-4 的
「层次 / 估值方法 / 持有数量」写进 G9-2。层次与估值方法的权威源就是 G9-4，而 G9-2 按权威模板
重构后根本没有这三列 ⇒ **真删**（不是留 no-op），`useG9FairValueTest.pushToDetail` 改为只提示口径；
按层次汇总改走 `g9CrossHelpers.sumG9DetailLevel3Closing`（已改为「从 G9-4 取 Level3 资产名 → 筛 G9-2 行求和」）。

---

## 3. C-5：后端两文件 + 注册 + 契约

### 3.1 全库首例「一个 store 键 × 三个受管区」

`明细表G9-2` 三个受管区 R12-16 / R19-23 / R26-28（区标题行 R11·R18·R25 与小计行 R17·R24·R29 均不受管），
前端把三区的行存在**同一个** `G9-detail-rows` 数组里、用 `section` 字段标记区归属。

平台既有多区范式 `phase5_d3_04_analysis` 是「一区一个 `store_item_id`」—— 那要求前端拆键。**不拆**的理由：

- `G9-detail-rows` 有真库载荷 **605 B**（G 循环单键最大的主受管表载荷）
- 被 **8 个**跨表消费方读取
- 是 **BP-10** 登记的键

⇒ 拆键的波及面远大于在引擎加一层可选过滤。改为引擎声明：

```
RowTableSheetSpec.row_section_field = "section"
RowTableSheetSpec.row_section_value = "main" | "mandatory_fvtpl" | "designated_fvtpl"
```

两处必须**成对**，缺一就是「读得出但写不回」或「写回落错区」：

1. `iter_store_rows` 只 yield 本段的行 —— 🔴 过滤**放在重复身份校验之前**。
   放在之后会让三段各自把另两段的行算进 `seen`，第二段起必然误报「重复行身份」。
2. `merge_projection_into_store_rows` 给**新增行**补该字段值（OO 侧在区②插的行回到前端才落对区）。

引擎改动零回归：`phase5_row_table_sheet` 相关 26 passed。

### 3.2 `template_id` 逐区不同而 `sheet_key` 共享

| 维度 | 取值 | 不这样会怎样（实测） |
|---|---|---|
| `sheet_key` | **共享** `g902-managed` | 三个不同值 ⇒ 契约层产出三个同 `excel_name` 的 sheet 条目，装配冲突 |
| `template_id` | **逐区** `G92R1/R2/R3` | 共用一个 ⇒ `build_instrumentation_payload_for_sheets` 抛「多 sheet instrumentation 的 template_id 必须唯一，实得 ['G92','G92','G92']」（definedName `GT_MANAGED_REGION_{template_id}` 等按它命名，三区会争同一个名字） |
| `uuid_col` | 逐区 AC / AD / AE | — |

先例：`phase5_d3_04_analysis`（同一张 sheet 两区，`template_id=D34DEBIT/D34CREDIT`，`sheet_key` 单值）。

### 3.3 `ghost_row_anchor_index=1`

幽灵行锚点指 **B 列「投资项目」**（真正的业务名称），不是默认的 `[0]`（A 列「类别」）。
A 列是枚举且模板 R12/R19 本就有预填值 ⇒ 用它当锚点会让「只填了类别的空行」通不过幽灵行防护、
而「OO 侧只填了投资项目的真行」被当幽灵行剔除。与引擎注释里 D5 的同型例外一致
（D5 的 `[0]` 也是枚举 `category`）。判据 `test_merge_stamps_section_on_newly_inserted_rows` 实测踩到过。

### 3.4 entry 层三个 store 门面「遍历三段」

生产调用点只传**一份** payload、没有段参数：

- `store_projection_response.py:233` → `provider.build_store_projection(payload, contract=contract)`
- `projection_first_publication.py:1117` → 同上（`build_combined_store_projection` 只在
  `STORE_ITEM_IDS` 长度 > 1 时才走，G9 只有 1 个键 ⇒ 不触发）

⇒ 缺省必须覆盖三段，否则区②③的行在 OO 侧永远是空的，而 digest 照样算得出来（假绿）。

| 门面 | 组合方式 |
|---|---|
| `build_store_projection` | 三段各投一次，`values`/`row_keys` 合并；stable_key 相撞即抛（段间 `table_key` 不同 ⇒ 正常不会撞，撞了说明 sheet 层声明漂移） |
| `merge_projection_into_store_rows` | **顺序穿线**：上段 merged 结果作为下段 `base_rows`，`applied/visited` 累加、`touched` 取并集。三次独立 merge 再拼会互相覆盖（引擎单段 merge 收整个 store 数组、按 identity 索引回写，不属本段的行原样保留 ⇒ 穿线是安全的） |
| `iter_store_rows` | 串联三段（各段内部按 `section` 过滤） |

三者都接受 `section=` 显式指定单段，供逐段判据使用。另给排障用的 `split_store_payload_by_section`
（未登记的 section 值单独归 `""` 桶 —— 静默丢弃会让「前端写了第四个区」看不见）。

### 3.5 顺带修零回归门的同族假绿

`check_sync_provider_golden_digest._synthetic_rows` 造的合成行不带 `section` ⇒ 被引擎按段过滤掉
**全部**行 ⇒ projection 为空而 digest 仍算得出来。这正是该函数自己 docstring 警告的假绿的另一种形态。
修法：段值**从 spec 现取**盖章（`row_section_field` / `row_section_value`），不按 provider 名硬编码。
`_field_specs_and_row_key` 返回值从 2 元组扩成 3 元组（多一个 `stamp`）。

实测（合成行经三段投影）：

```
row0 前 5 键: {'rowId': 'synthetic-0', 'section': 'main', 'category': 'v0', 'investTarget': 'v0', 'openingCost': 100}
单段 projection values = 56          # 28 字段 × 2 行
三段全投 values = 168                 # 28 × 6
三段全投 row_keys = {r1: 2, r2: 2, r3: 2}
merge applied=0 visited=288 rows=6    # 从同一批行回投 ⇒ 恒等回路，无改动
iter 全段行数 = 6
拆段桶 = {designated_fvtpl: 2, main: 2, mandatory_fvtpl: 2, '': 0}
```

### 3.6 交付物清单

| 文件 | 说明 |
|---|---|
| `app/services/workpaper_sync/phase5_g9_02_detail.py` | sheet 层三段声明（`SPEC_G902_R1/R2/R3` + 28 字段 + 12 公式模板） |
| `app/services/workpaper_sync/phase5_g9_other_noncurrent.py` | entry 层（选型必要条件 / instrumentation 复数 / 契约装配 / 三段 store 门面 / matcher / 注册 / 发布链） |
| `scripts/gen/generate_phase5_g9_contract.py` | 契约生成（写盘前先过 `parse_contract`，照 G2 不照 F1） |
| `data/workpaper_sync_contracts/g9.other_noncurrent_detail.json` | canonical `95a6ae0ca66cbf7bb33c185034502b8aa05b40fdfb7cc92eba16aa2fafbedef1`；**一张 sheet 三条 tables** |
| `store_item_registry.STORE_MERGE_REGISTRY` | 挂 `g9.other_noncurrent_detail` plan（1 个 item + `oo_crash_neutralization_fn`） |
| `adapters/registry.DELIVERED_PER_ENTRY_CONTRACTS` | 交付登记行（`adapter_registered=False`，欠账同 BP-61-1） |
| `scripts/check/check_sync_provider_golden_digest.py` | 加 `("g9", "phase5_g9_other_noncurrent", "ADAPTER_ID", True, True)` + 段盖章修复 |
| `tests/workpaper_sync/test_g9_column_isomorphism.py` | 列同构判据（堵住猜测映射） |
| `tests/.../test_task49_g_cycle_migration.py` | `SLICE_DELIVERED_CONTRACTS` 加 G9 一行 |

**GC-2 裸 IF 口径修正**：tasks.md 原写「G9 册 84 格」是 `findall` **出现次数**；按生产函数
`neutralize_oo_crash_if_formulas` 的正则现算**格数**是 **42**（全在 `审定表G9-1`，受管表
`明细表G9-2` 零命中）。与 G2 的 21 vs 40 同源错误。受管表干净仍必须挂中性化：
per-file 策略，点同册任一 sheet 的在线编辑都会触发整册加载。

---

## 4. 判据结果

| 套件 | 结果 |
|---|---|
| `test_g9_column_isomorphism.py` | **60 passed** |
| `test_task49_g_cycle_migration.py` | **97 passed**（含新契约的 Property 20/21 字段级核验） |
| `test_g_single_region_p1_p3_p5_p6.py` | G9 两条 B 类红判据**转绿**（`test_provider_module_exists_and_declares_expected_ids[G9]` / `test_store_merge_plan_is_registered_with_oo_neutralization[G9]`）；余八条仍红 = 诚实的未交付 |
| `test_task13_contract_registry.py` | G9 已从「磁盘有／登记无」名单移除 |
| 前端 | G9/G1/G3 相关 **16 个 spec 全绿**（`useG9Detail` 35 · `g1g3RowIdentityBp7` 17 · `useG9FairValueTest` 13 · `useG9VoucherCheck` 20 · 其余 12 家） |
| `mutate_task49_g_cycle_migration_guards.py --check-anchors` | **61/61 OK, 0 MISS**，目标文件 md5 未变（slice 改动未破坏变异覆盖的锚点） |

`_digests_for('g9', …)` 单家实测：contract `95a6ae0ca66c` / projection `60fac0ffbde3` / sheets 1。

---

## 5. 未完成与外部依赖（不伪造）

| 项 | 状态 | 归属 |
|---|---|---|
| G9 进 golden digest **基线文件** | 🟡 阻塞 | 零回归门跑到 `f1` 就 `TypeError: build_store_projection() missing 1 required positional argument: 'payload'` —— `phase5_f1_prepayment` 用 `(store_item_id, payload, *, contract)` **两位置参**，与其余十二家的单位置参形态不一致（G2 的 docstring 早已登记过这个坑）。属 `f1-sync-coverage-and-first-canary` 作业面，并发会话在改，本 spec 不越界修 |
| P18 「九条全在 digest / 九条全发契约」 | 🔴 按设计仍红 | 要到 Task 15 九条齐备才转绿（红判据写成**正向**正是为此，见 Task 3~6 取证） |
| `adapter_registered=True` | 🔴 平台级欠账 | BP-1~BP-3：instrumentation candidate / 人工审核契约 / approved bundle 三缺（umbrella BP-61-1），与 D1/D3/D5/D6/D7/E1/F1~F5/G2 同一缺口 |
| Playwright 实测 | 🔴 待环境 | 需 `start-dev.bat`（后端 9980 + 前端 3030） |

**并发会话造成的既存红（逐条归因，不计入本 spec）**：

- `test_e1_provider_and_expansion.py::test_store_item_ids_no_duplicates`（E1 的 5→10，E1 作业面）
- `test_task13_contract_registry.py` 3 条：2 条源自 `ClosureGuardError: legacy characterization is stale`
  （工作树里 `workpaper_sync_entry_manifest.json` 被改成 `d3.prepaid_receipts_detail` / `capability=bidirectional`，
  manifest digest 与冻结的 legacy characterization 不再相等）；1 条是磁盘 `i6.*` 未登记 + 登记表 `f2.*` 无文件
- `test_g_foundation_p10_p16_g2_canary.py::test_f1_lane_broken_fixture_import…`（f1 作业面）
- 前端 60 个 `*NoteSubtableContract.spec.ts` 共 370 条：全是「子表名与模板不一致 ⇒ 孤儿子表」同一族，
  **横跨 D/E/F/G/H/I/J/K/L/M/N 全部循环**（连共享助手 `_disclosureSubtableContract.helper.spec.ts` 本身也红）
  ⇒ `note_template` 资产层的共性问题，与 G9-2 明细表列模型无关。G9 那 1 条失败的断言是
  「`其他非流动金融资产` 应存在于 附注 五、20」，模板现只有「种 类」

**既存 vue-tsc 报错（非本轮引入，行号回溯确认）**：`g6CrossHelpers`（泛型 T 上取具体属性，6 处）·
`useG9FairValueTest:369/448` 与 `useG9L3Reconciliation:277`（同属 `stripFormulaFields` /
`Enriched↔Raw` 泛型窄化问题，后者本轮未触碰即证明是既存）· `useWorkpaperScaffold:191` · `GtIndexChip:256/258`。

---

## 6. 复用件（供 C-6~C-10 余八条）

- `backend/scripts/fix/resync_g_slice_source_refs.py`（`--check` / `--apply`）：改前端后 slice 的
  `payload_column_source` / `row_identity_generator_source` / `row_identity_generator_form`
  一律**按值现取**（行号 grep，不手写）。新增 lane 往 `TARGETS` 加一行即可。
- `backend/scripts/analyze/_g_column_isomorphism_probe.py`：九条列数普查（C-6 逐条模板调研仍要用）。
- 一次性脚本已按规约删除：`_g9_tab_detail_rewrite.py` / `_g9_consumer_readpoints.py` /
  `_g9_drop_fv_pushback.py` / `_g9_fix_fvtest_spec.py` / `_g_slice_bp7_fixed_note.py` /
  `_g1g3_mint_refactor_spec.py` / `_probe_g9_digest.py`。

余八条的列数差（普查基线）：G6 是 **FVOCI** 口径 —— 与 G9 相反，它**确实有** OCI 与减值列，
不得照抄 G9 的移除清单。G1 27/56 · G10 19/35 · G13 12/21 · G14 13/19 · G11 13/16 ·
G3 33/32 · G8 23/24 · G12 10/10。

---

## 7. 教训

1. **判据钉住的是「代码形态」，取证只能跟着事实走**。G1/G3 行身份连改三轮 slice 都改不对，
   根因是把前缀常量放进共享模块使形态无法回源 —— 该改的是代码不是取证。
   （详见 tasks.md Task 7 的 2026-09-27 追加修正块。）
2. **列数相同不等于语义同构**。G9 的 `28 == 28` 是 3 真对上 + 15 前端独有 + 11 模板独有恰好凑成同数。
3. **「模板没有这列」和「这列是会计错误」要分开说**。前者可能是模板缺陷（本 spec 另有两处走覆盖层），
   后者必须删。判据依据写在会计口径上才站得住。
4. **合成载荷的假绿会跟着新形态一起进来**。引擎加一个可选过滤字段，零回归门的合成行就得跟着盖章，
   否则 digest 覆盖率静默归零。
