# Task 11~18 证据：G2 canary 交付 + 收口交棒

spec: `g-cycle-sync-foundation-and-first-canary`
日期：2026-09-27

## 一、交付清单

### 后端新建
| 文件 | 作用 |
|---|---|
| `app/services/workpaper_sync/phase5_g2_interest_receivable.py` | entry 层 provider（`phase5_*` 声明式范式，非 G7 pilot 形态） |
| `app/services/workpaper_sync/phase5_g2_02_detail.py` | 明细表G2-2 薄声明 `SPEC_G202` |
| `scripts/gen/generate_phase5_g2_contract.py` | 契约生成（写盘前先跑 `parse_contract`） |
| `data/workpaper_sync_contracts/g2.interest_receivable_detail.json` | canonical_digest `27dc403f…` |
| `scripts/fix/fix_g_cycle_wp_code_adjudication.py` | 17 条 G wp_code 裁决（一 entry 一条） |
| `scripts/fix/fix_g_slice_bp5_status_and_registry_alias.py` | Task 9 的两条登记回填 |
| `scripts/fix/fix_g_slice_g2_key_convergence_registrations.py` | **Task 18 新增**：键收敛后的 slice 登记回填 |
| `tests/workpaper_sync/test_g2_frontend_managed_sheet_parity.py` | **Task 15/18 新增**：前端受管清单 ↔ provider parity |

### 前端新建
| 文件 | 作用 |
|---|---|
| `components/workpaper/composables/g2StorageContract.ts` | `G2_ITEM_IDS` 单一真源（叶子模块零 import） |
| `components/workpaper/sync/g2ManagedSheets.ts` | **Task 15 新增**：受管 sheet 单一来源清单 |
| `e2e/fixtures/g2-l2-cases.json` | **Task 16 新增**：真栈用例集 + seed 裁决证据 |
| `e2e/g2-l2-oo-to-html-all.spec.ts` | **Task 16 新增**：P15 前置 + canary 用例 |

## 二、Task 15 宿主接桥

`GtG2InterestReceivable.vue`（+83 −3）：

- 受管判定 `isG2SyncManagedSheet = isG2OoWiredRowsSheet(currentSheet)` —— **从受管清单派生**，
  由后端 parity 契约测试守护与 provider `all_managed_sheet_names()` 一致。
- 🔴 **不照 F 循环**：F1/F3/F4/F5 四条 lane 都在宿主内联 `F*_SHEET_KEY_BY_CODE`，注释写
  「从 provider 受管清单派生」而实现是硬编码，没有判据能在漂移时报红。本 lane 照 D3
  （仓库里唯一把这件事做实的样本）。
- P14 保留共享基座：`useG2DualMode`（→ `useWorkpaperEntryDualMode`）未内联展开。
- legacy `GtOnlyOfficeSheet` 模板挂载点保留 2 个（OO 模式非受管分支 + 未迁移 sheet 兜底）。
- `GtEntrySyncCapabilityNotice` 保留（AC 1.4）。
- `.oo-container { min-height:600px; height:calc(100vh - 200px) }`（sizing 守卫 47 落点全绿）。

### 接桥中现算发现的三处 F 循环既存缺陷（本 lane 未复制）

1. **`readStoreProjection` 多余属性** —— F/D 多处传 `sheetKey`，而入参类型是
   `WorkpaperSyncEntryScope` 恰三段 `{projectId,wpId,entryId}`。现查端点
   `GET /sync/store-projection` **不收** `sheet_key`（按 provider `all_store_item_ids()`
   投影整个 entry 的全部受管区）⇒ 传了被静默丢弃 + TS excess property 报错。
   **不是数据缺陷**（整 entry 投影覆盖每个受管区），是死参数。本 lane 按真实签名传三段。
2. **`WP_BRIDGE_IN_FLIGHT_STATES.has(...)`** —— 它是 `readonly WorkpaperSyncBridgeState[]`
   不是 `Set`，`.has` 是类型错误（桥内部自己用 `.includes`，见 `useWorkpaperSyncBridge.ts:1320`）。
   本 lane 用 `.includes`。
3. **`WorkpaperSyncEditorHost` 的 props** —— 只有 `descriptor`(必填) / `bridge`(必填) /
   `documentServerUrl?` / `docsApiLoader?` / `contentRefresh?` / `trackOperation?`。
   F 循环额外传的 `wp-id`/`project-id`/`readonly` **不是 props**，会以 DOM 属性落到根 div。
   本 lane 只传两个必填 + `ref`，并按 D1/D2 同款用 `syncOoDescriptor` computed 保持 ref 追踪。

## 三、Task 16 真栈验收（`[ ]*`，代码已交付但真栈未实测）

### 裁决 GF-H2「不 seed」的现算证据（真 PG，2026-09-27）

```sql
SELECT cr.wp_id, jsonb_array_length(cr.remark::jsonb) AS row_count,
       wp.project_id, wi.wp_code, wi.wp_name
FROM checklist_responses cr
JOIN working_paper wp ON wp.id = cr.wp_id
LEFT JOIN wp_index wi ON wi.id = wp.wp_index_id
WHERE cr.item_id = 'G2-2-detail-rows';
```

| wp_id | row_count | remark_bytes | project_id | wp_code |
|---|---|---|---|---|
| `ede443da-3848-4a3f-af21-848559aa0e25` | **1** | **475** | `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49` | G2 应收利息 |

⇒ 真实载荷已存在，交付 seed 脚本会覆盖真数据 + 掩盖空表假绿 ⇒ 不 seed。

### P15：为什么前置断言必须先跑

空表往返会让三谓词**全部成立**（出去 0 行、回来 0 行、镜像一致）⇒ `store_mirrored` 为真而
什么都没验证。故 `g2-l2-oo-to-html-all.spec.ts` 的第一条用例是前置断言，且**不带**
`pending_adapter` 跳过。静态守卫 `TestGfP15RealStackPreconditions`（8 条）锁：

- fixture 声明 `min_row_count ≥ 1` + `must_assert_before_skip`；
- 证据数字（475 / 1 行 / UUID / 可复跑 SQL）齐全，不留占位；
- **位置判据**：行数断言出现在 `c.result_enum === 'pending_adapter'` 之前；
- 前置用例体内无 `test.skip`（环境缺位应诚实报红，不绿着跳过）；
- 仓库里不存在 G2 seed 脚本（GF-H2 可证伪）；
- `--workers=1` + `mode: 'serial'` 落在文件里。

🔴 位置判据首版踩坑：`src.find('pending_adapter')` 命中了文件头 docstring（556 < 3140，
自造红）⇒ 改为定位**可执行谓词** `c.result_enum === 'pending_adapter'`。与仓库反复登记的
「符号名 grep 会误报」同类。

### fixture 加载形态：F1 lane 的 e2e 根本加载不了（既存缺陷，已登记）

```
$ npx playwright test e2e/f1-l2-oo-to-html-all.spec.ts --list
TypeError: Module ".../f1-l2-cases.json" needs an import attribute of "type: json"
Total: 0 tests in 0 files
```

F1 用 `import cases from './fixtures/f1-l2-cases.json'`，Playwright 的 Node ESM 加载器直接
拒绝 ⇒ **整个 spec 文件加载失败、一条用例都跑不起来**，而 CI 上看不出区别（本来就 skip）。
D4 lane 用 `readFileSync`，本 lane 照 D4；
`test_fixture_is_loaded_in_a_form_playwright_can_actually_load` +
`test_f1_lane_broken_fixture_import_is_registered_not_silently_copied` 两条守住
（后者在 F1 修好后会打红，提示移除登记）。

本 lane 实测：`--list` → `Total: 2 tests in 1 file` ✅

## 四、Task 17 FC-9 TB 红线（G2 侧）

`TestGfP16TbRedLine` 由 5 条扩到 7 条：

| 判据 | 锁什么 |
|---|---|
| `test_provider_module_never_writes_trial_balance` | provider + 薄声明代码区零 TB 写入形态 |
| `test_mutation_publish_to_tb_in_sync_path_makes_red_line_fire` | **新增变异**：注入 `publish_to_tb` / legacy writeback 端点 ⇒ 扫描必报（证明 `not in` 形态有牙齿） |
| `test_bridged_host_sync_path_carries_no_tb_write` | **新增**：Task 15 接桥新增的 `flushHtml`/`reloadHtml` 是 sync 路径在宿主侧的新落点，provider 侧扫描覆盖不到 |
| `test_publish_gate_remains_the_only_entrance` | `publishToTb` 计数基线 3 + 端点真实存在 |
| `test_legacy_dual_tb_keys_are_both_kept` | 主键 `G2-1-tb` + legacy 回退键 `G2-1-adj-tb-1132` 都在；契约不得声明 TB 键 |
| `test_account_code_is_1132_and_balance_caliber` | 科目 1132、非 `PL_CYCLES` 成员（余额口径） |
| `test_adjudication_sheet_is_deferred_not_silently_managed` | GF-H5：`adjudication_spec()` 恒 None |

「把 TB 写入塞进 `flushHtml`」是接桥后最自然的错误写法（「反正都要 flush，顺手把审定数推
到 TB」），故单列一条 + 同时锁 legacy 监听器 `g2:writeback-trial-balance` 不得复活。

## 五、Task 18 收口

### 5.1 键收敛的下游后果：上游守卫 4 红已修（不是绕开）

Task 13 把 `G2-2-detail-rows` 收敛成 storage contract 单一真源后，上游
`test_task49_g_cycle_migration.py` 有 4 条红 —— 每条断言消息都写着「若已开始收敛，请更新
登记与本判据」，即这些字段就是为「事实变了要回填」设计的。`fix_g_slice_g2_key_convergence_registrations.py`
（幂等 `--check`/`--apply`，写盘前现算前提校验）改 9 处：

| 登记 | 改前 → 改后 | 为什么 |
|---|---|---|
| `transport_key_kind` | `literal_item_id` → `storage_contract_member_item_id` | 取值逐字照既有同族样本 G5-2-rows / G6-11-rows，不自造枚举 |
| `primary_table.owner_module` | `useG2Detail.ts` → `g2StorageContract.ts` | 真源换位置 |
| `primary_table.owner_constant` | `STORAGE_KEY` → `G2_ITEM_IDS.G2_2_DETAIL_ROWS` | 同上 |
| `primary_table.owner_declaration_kind` | `module_constant` → `storage_contract_object_member` | 同上 |
| `payload_column_source` | `#L517` → `#L519` | 守卫取 `[line-1:line+3]` 四行窗口；停在 L517 时窗口落在 `function persistRows` 声明处，remark/conclusion 双双扫不到 ⇒ `remark_only` 被误判成「两列都没写」 |
| `row_identity_generator_source` | `#L146` → `#L150` | 该 ref 只用于解析文件、不读行号（非红因），一并改正避免「看着精确其实过期」 |
| 摘要 `transport_key_kind_counts` | literal −1 / storage_contract +1 | 逐 entry 现算必须等于摘要 |
| 摘要 `duplicated_item_id_literals_in_g_cycle` | 80 → **79** | 脚本按守卫同口径**自己复算**，不抄守卫数字（抄数字等于两处各写一份真源） |
| `BP-10.partial_progress` | 新增 | `status` **仍是** `REGISTERED_NOT_FIXED`：79 条未收敛，不因动了一条就标已修 |

### 5.2 「本 slice 契约数 = 0」前提失效 ⇒ 按原指引补字段级判据

交付 G2 契约后两条判据必红，且原文明写「必须在此补齐字段级判据
（stable_field_key / json_pointer / mode / value_type / source_ref 与 col_ 占位拒绝）」。落地为：

- 新常量 `SLICE_DELIVERED_CONTRACTS`（entry_id → 契约文件名）= 字段级判据的**分母**；
- `test_slice_contract_delivery_is_exactly_the_declared_set`（改写）：磁盘现算 **==** 登记，
  双向咬（登记了没文件 / 有文件没登记都红）；且「其余 entry 仍为 0」这半句也可复核；
- `test_delivered_slice_contracts_pass_property_20_21_field_level`（**新增**）：逐字段六锁；
- `test_registry_delivered_contracts_contain_no_slice_entry` → 改名
  `..._match_the_declared_slice_delivery`：registry 里的本 slice entry **==** 已登记交付面。

🔴 `mode` / `value_type` 的允许集合从引擎枚举 `contracts.FieldMode` / `ValueType` **现读**，
不在判据里手抄（首版抄成 `read_write/read_only/write_only`，与真实的
`editable/formula/auto_source/word_only` 完全不搭，判据直接自造红）。

上游文件：**96 passed → 97 passed**（净 +1 条新增判据），变异脚本 `baseline_backend_passed`
同步 96 → 97 并在注释里写明来源。

### 5.3 全部变异复跑：61/61 有牙齿

`python backend/scripts/diagnose/mutate_task49_g_cycle_migration_guards.py --run all`

- 锚点自检 **61/61 OK、0 MISS**（两条锚点随本 spec 的真实修复而重指向，见下）；
- 判定：**60 RED** + 1 ERROR(M47)；M47 的 ERROR 是**我自己的 `--restore` 与后台 run 撞车**
  （`--restore` 把 `.mutbak` 还原并删除，M47 随后的还原步骤 `FileNotFoundError`，且测试
  实际跑在已被还原的原文上）⇒ 单条复核：原文 `1 passed` / 变异 `1 failed` / 还原
  sha256 逐字节一致 ⇒ **RED**。全部 61 条 `restored=True`，仓库无 `.mutbak` 残留。

两条锚点重指向（都因本 spec 的真实修复）：

| 变异 | 改动 |
|---|---|
| M45 | 方向取反：原「status 从 `REGISTERED_NOT_FIXED` 谎报成 `FIXED`」→ Task 5 真修后 slice 合法变 FIXED、旧 anchor 消失 ⇒ 改成「从已修谎报回未修」（守卫已按修复后形态断言 `== FIXED`，仍能打红） |
| M26 | 基数 80 → 79（Task 13 收敛后现扫值），变异语义不变（把规模数字改小） |

### 5.4 「整册 materialize/verify」：可跑的跑了，跑不了的钉成可证伪事实

生产整册链（`materialize_projection` + `verify_unmanaged_regions`）需要
`FrozenEntryDefinitions` + `ExcelIdentityBinding`，只能由 registry/resolution 从**已注册
adapter** 取。G2 的 manifest capability 仍是 `single_onlyoffice` ⇒ `attach_pilot_adapters`
走 capability 门返回空 ⇒ 该链在 G2 上不可达（与 Task 14 第③环、Task 16 真栈同一阻塞）。
参照 `scripts/e2e/verify_d4_full_book_real_stack.py` 的注释：D4 是 D 循环唯一
`adapter_registered=True` 的 entry，故也是唯一能真跑这条的。

可跑且有意义的那一半已落地为 `TestGfP19EngineLevelRoundTrip`（4 条）：

- 用**真库录制的 475 B 载荷**（逐字，含账龄双组 `agingPrior`/`agingAudited` 与
  `eclStage`/`indexRef`）跑 store → `build_store_projection` → `merge_projection_into_store_rows`
  → store 的无损往返；
- 变异「抽掉一个受管字段」⇒ 往返结果必与原载荷不等（证明「无损」不是恒真装饰）；
- 阻塞登记判据断言 `manifest_capability_enabled() is False` 且 `attach` 返回 `()` ——
  capability 一放开它就打红，提示来跑真的那条。

### 5.5 公式管理入口两模式可达

G2 的公式管理 / 版本历史 / 编制手册 / 能力提示挂在同一条工具条上，其渲染条件只有
`currentSheet !== '底稿目录'`，**不带** `renderMode` ⇒ 两模式都在。
`test_toolbar_entries_stay_reachable_in_both_modes` 按**位置**锁：工具条条件里不得出现
`renderMode`/`isOoMode`/`onlyoffice`，且模式两分支都在工具条之后。
（接桥时最容易顺手把工具条塞进 `v-if="!isOoMode"`，那样切到在线编辑就再也点不到公式管理，
是只有真人点一次才发现的缺陷。）

### 5.6 P21：既有产物复用，未被替换

| 既有产物 | 本 spec 的动作 |
|---|---|
| `tests/workpaper_sync/test_task49_g_cycle_migration.py`（179 KB / 97 条） | **在内改写 3 条 + 新增 1 条**，未另起替代文件 |
| `tests/four_table/test_g_cycle_formula_presets.py` | Task 7 在内加 Property 11（4 条） |
| `scripts/diagnose/mutate_task49_g_cycle_migration_guards.py`（61 条） | 在内重指向 2 条 + 基线数 +1，未另起 |
| `data/workpaper_sync_g_cycle_deletion_plan.json`（51 KB 删除清册） | Task 9 回填 1 处，结构未替换 |

另起的 6 个判据文件各有显式理由（见 `task2-task4-red-baselines.md` 与本文件）：
上游 3147 行守卫冻结的是 **slice 事实**，下游实施基线塞进去会混淆两类事实；
F 循环已确立「每 spec 独立判据文件」。

## 六、裁决 GF-H5 登记：13 张审定表另立第五份 spec

**裁决**：G 循环 13 张审定表（G1-1 / G2-1 / G3-1 / G4-1 / G5-1 / G6-1 / G8-1 / G9-1 /
G10-1 / G11-1 / G12-1 / G13-1 / G14-1）的覆盖**不进本轮四份 lane spec**，另立第五份
`g-cycle-adjudication-sheets-coverage`。本 spec 的 `adjudication_spec()` 恒 `None`，
前后端两侧同时锁（`test_adjudication_sheet_is_deferred_on_both_sides`）。

### 三条共性证据（为什么它们该归一份 spec 而不是分散到各 lane）

1. **形态共性：逐格 mask，不是行表。** 审定表是 `AdjudicationSheetSpec` 的 per-cell 形态，
   走**第二套桥**，与本轮四份 spec 全部基于的 `RowTableSheetSpec` 行表桥不是同一条路径。
   D4 已实证「把两者并进同一个布尔会切错桥 + 工具条叠加」（D4-35/D4-13）。
2. **裸 IF 共性：13/13 全命中。** RG-4 现算 13 张审定表**全部**命中裸 IF 中性化
   （如审定表G5-1 = 61 格 / 122 次，2:1 嵌套），同一处置在 13 张上一次做完成本最低；
   分散到各 lane 会让 `oo_crash_neutralization_fn` 的挂载在 13 个地方各写一遍。
3. **TB 红线共性：审定表是唯一合法发布门所在。** 13 张全部承载
   `publish-to-tb` 显式确认门（G2=3 处 / G5=4 处，writeback 共 11 处），
   且 GC-9 现算三家缺口（G1 在组件层 `G1TabAdjudication.vue:356`、G4-main 真缺、
   G6-main 真缺且是回归）。TB 口径必须整循环一次裁清，不能按 lane 各判一次。

## 七、两条既存阻塞的具名登记（非本 lane 引入，不顺手改）

### 7.1 `check_sync_provider_golden_digest.py` 整体仍红 —— F1 既存 bug

`build_store_projection` 的签名形态是刚性的：零回归门按
`mod.build_store_projection(rows, contract=contract)` 调用 ⇒ **单位置参** `payload`。
F1 / F2 写成 `(store_item_id, payload, *, contract)` 两位置参 ⇒ 门上直接
`TypeError: missing 1 required positional argument: 'payload'`。
D1/D3/D5/D6/D7/E1/F3/F4/F5 九家用单位置参形态全部通过；**G2 照 E1 形态**（最完备：
单位置参 + 可选 `store_item_id`，兼容多受管区）。

不修 F1 的理由：`phase5_f1_prepayment.py` / `f1.prepayment_detail.json` 是并发会话的在飞
未跟踪文件，改会冲突。已在 `test_g_foundation_p20_golden_digest_baseline.py` 的
`KNOWN_PRE_EXISTING_BLOCKERS` 具名登记（含 owner spec + ≥60 字理由），
F1 修好后判据会打红提示移除。baseline 文件 labels 仅 `b60,d1..d7,e1`（9 家），
无 f1/g2 ⇒ `--update` 当前跑不了。

### 7.2 `test_workpaper_sync_legacy_baseline.py` 2 红 —— 长期既存 + 并发会话在飞

`build_baseline(manifest)` 现算 vs 磁盘生成物：**12 条 entry 漂移**，其中
**11 条非本 lane**（d1 / d2 / d3 / d5 / d6 / d7 / e1 / f1 / f3 / f4 / f5），
本 lane 只贡献第 12 条 g2。

决定性证据：`d1` 与 `d2` 的宿主**不在**并发会话的修改清单里 ⇒ 该生成物自 D1/D2 canary
**提交时**起就没重生成，这条门在 main 上已红很久；`backend/data/workpaper_sync_legacy_baseline.json`
本身工作树未修改 ⇒ 红来自已提交状态。

不重生成的理由：①11/12 的漂移不属本 lane，重生成等于把别人的进度
（`single_mode_switch_visible_count` 128→123、`missing_adapter_count` 138→133）
记到本次提交名下；②会把并发会话**在飞**的宿主改动固化进两个大生成物
（其中 `workpaperSyncManifest.generated.ts` 已被他们修改），必然冲突。

## 八、交棒清单

### 8.1 三份 lane spec 的 entry 集合

| lane spec | entry 集合 | 受管面起点 |
|---|---|---|
| `g4-g6-shared-workbook-three-entry-lanes` | `g4.bond_main` / `g4.sppi_inventory` / `g4.ecl_stage` / `g6.other_bond_main` / `g6.sppi_fair_value` / `g6.ecl_stage` | 六条 lane，`sheet_keys` = `g402/g407/g409/g602/g605/g611-managed`；G4 sha256 `da3a3480…` / G6 `63bf38c7…` |
| `g5-nested-sections-and-template-defects` | `g5.long_term_receivable_detail` | 三段嵌套 + 模板缺陷；G5 sha256 `c59bba69…` |
| `g-cycle-single-region-detail-lanes` | `g1` / `g3` / `g8` / `g9` / `g10` / `g11` / `g12` / `g13` / `g14`（9 条） | 单区明细，GC-2 的 17 条中性化归属里 9 条属此 |

🔴 **g4-g6 spec 的 entry 表漏了 G4-ecl 的 BP-6**（slice `blocked_by` 现算：BP-6 标在
G4-ecl / G5 / G6-main / G6-sppi / G6-ecl 五条上）⇒ 实施时按实测补，不按 spec 表抄。

### 8.2 本 spec 已裁的 GC-1~GC-10 引用点

| 裁决 | 落点（下游直接引用，不重裁） |
|---|---|
| GC-1 pointer 按 entry_id | `data/workpaper_sync_entry_wp_code_adjudication.json`（32 条，digest `6f0452304a1e0114…`）；守卫 `test_g_foundation_p5_gc1_pointer_isolation.py`（9 条）。G4B/G6O 两组**必须**声明互斥 `sheet_keys` |
| GC-2 裸 IF 中性化 | 规则=「已交付者一律带 `oo_crash_neutralization_fn`，未交付者登记归属」；`StoreMergePlan.provider_module` 必填 ⇒ plan 不能先于 provider |
| GC-5 json_pointer 指 remark | 契约 `review.html_store.json_pointer` 不得写 conclusion、不得双写 |
| GC-6 / RG-9 键按值取 | 禁按 sheet 号推演：`明细表G2-2` 的键是 `G2-2-detail-rows` 不是 `G2-2-rows` |
| GC-8 prefill 改名 | `[169] 明细表G13-2` / `[170] 明细表G14-2`；守卫在 `tests/four_table/test_g_cycle_formula_presets.py` Property 11 |
| GC-9 TB 缺口 | 缺口是**两家**（G4-main / G6-main）不是三家：G1 的门在组件层 `G1TabAdjudication.vue:356` |
| GC-10 PROVIDERS | 实测 = b60 d1 d2 d3 d4 d5 d6 d7 e1 f1（**不含** g7/h1，spec design 写错）+ 本 lane 新增 g2 |
| FC-8 OCR 冲突 | 重裁「**适用**且当前不冲突」：G 有 10 个 OCR 写入站点，但键全落非受管 sheet（G2 受管 `G2-2-detail-rows` vs OCR `G2-8-*`），判据锁空交集 |
| GF-H1 canary 选型 | 明细表G2-2（单级表头 R9 / 数据 R10-15 / footer R16 / 公式列 E·H·J / `uuid_col=N`） |
| GF-H2 不 seed | 见 §三 |
| GF-H5 审定表后置 | 见 §六 |

### 8.3 下游必须照抄的三条形态

1. `build_store_projection(payload, *, contract, limits=None, store_item_id=None)` ——
   **单位置参**（照 E1，不照 F1/F2）。
2. 契约 `sheets[]` 必须用引擎 `spec_to_contract_sheet_payload(spec)` 产出 ——
   F1 手写形态缺 `anchor`，会抛 `ContractSchemaError: table anchor 必须是 A1 单元格`。
3. 前端受管清单 = 「集中声明 + 后端 parity 契约测试」（照 D3 / 本 lane），
   **不照** F 循环的宿主内联 map。

### 7.3 并发会话在飞改动导致的 2 红（G1，不属本 lane）

收口最后一跑：**265 passed / 2 failed**，两条红都在 G1 上：

```
test_payload_column_mode_is_declared_and_matches_the_write_site
  xlsx/gt-g1-trading-financial-assets: 声称 conclusion_only，但 useG1Detail.ts#L653 附近
  实测 remark=False conclusion=False
test_row_identity_key_and_generator_are_source_backed
  xlsx/gt-g1-trading-financial-assets: slice 声明的生成器形态 '`row-${Date.now()}`'
  在 useG1Detail.ts 里逐字找不到
```

根因现算：`useG1Detail.ts` 于 **2026-09-27 08:37** 被改（本会话开始时它还是干净的），
源码注释自述属 **`g-cycle-single-region-detail-lanes` Task 7**：
行身份铸造收口到 `newRowId(G_ROW_ID_PREFIX.g1Detail)`，取代原
`row-${Date.now()}`（无随机后缀，同毫秒连加两行会撞 id）。

⇒ 这是**那条 lane 的合法修复**，与本 lane 无关；它触发的 slice 登记回填
（G1 的 `row_identity_generator_form` + `payload_column_source` 行号）属该 lane 的收口动作，
与本 lane 为 G2 做的 §5.1 完全同型。**本 lane 不代改他们的在飞文件。**

本 lane 自身的判据面：`test_g_foundation_*`(5 文件) + `test_g2_frontend_managed_sheet_parity.py`
+ `tests/four_table/test_g_cycle_formula_presets.py` 全绿；上游
`test_task49_g_cycle_migration.py` 除上述 2 条并发红外 95 passed。

## 九、本 lane 判据面总账（2026-09-27 收口）

| 文件 | 条数 |
|---|---|
| `test_g_foundation_p1_p3_fc_reinterpretation.py` | 36 |
| `test_g_foundation_p4_p8_p17_p18_red_baselines.py` | 50 |
| `test_g_foundation_p20_golden_digest_baseline.py` | 12 |
| `test_g_foundation_p5_gc1_pointer_isolation.py` | 9 |
| `test_g_foundation_p10_p16_g2_canary.py` | **43**（P16 +2 / P15 +8 / P19 +4） |
| `test_g2_frontend_managed_sheet_parity.py` | **11**（新建） |
| `test_task49_g_cycle_migration.py`（上游，在内改） | **97**（96 +1） |
| `tests/four_table/test_g_cycle_formula_presets.py` | 9 |
| 合计 | **267**（含并发红 2 条） |

变异：`mutate_task49_g_cycle_migration_guards.py` **61/61 有牙齿**，锚点 61/61 OK，
报告落 `evidence/mutation_report_task18.json`。

前端：`e2e/tsconfig.json` 下 `tsc --noEmit` 对本 lane 两个新文件 **0 错**；
`playwright --list` = 2 tests；`workpaperSyncEditorHostSizing` 47 落点全绿。

🔴 **宿主类型核验的复现方式**：仓库全量 `vue-tsc --noEmit` 在本机 **OOM**
（14 GB 堆仍 `Ineffective mark-compacts`，与本 lane 改动无关）。本轮用**临时**作用域
tsconfig（`include` = 宿主 + `sync/g2ManagedSheets.ts` + `composables/g2StorageContract.ts`
+ `composables/useG2DualMode.ts` + `src/env.d.ts`，其余编译选项照
`tsconfig._f345-canary.json`）核到「本 lane 四个文件 0 错」，用完即删（`_` 前缀一次性规约）。
需复核时按此清单重建即可。
