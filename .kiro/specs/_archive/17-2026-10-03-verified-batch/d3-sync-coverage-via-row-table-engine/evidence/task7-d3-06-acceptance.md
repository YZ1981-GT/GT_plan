# Task 7 证据记录：D3-6 接入验收

**实施日期**：2026-09-26　**方法**：回归复核 Task 2/3 判据 + 新建 Property 5 独立判据 +
新建离线"注入+验证"判据（真实权威模板 → 真实 instrumentation 注入 → 真实
`verify_unmanaged_regions`）+ 新建前端 Property 9 判据 + 实测尝试翻转灰度开关（发现真实
阻塞点并据此定案，未强行翻转）。全程未连库、未依赖任何 mock 冒充真栈。

## 〇、灰度开关 `_INCLUDE_D306_RELATED_PARTY` 验收后的最终状态：**维持 False**

**依据（实测得出，不是凭空决定）**：

1. **requirements.md 需求 1.4/1.5 的字面要求**逐字重读：只要求"受管区从 1 增至 2，整册
   materialize 200 且 `verify_unmanaged_regions` 全绿，耗时按需求 6 记录"+"下游 computed
   消费方仍正确重算"，**没有**"必须永久打开开关"这一条。design.md/tasks.md 同样无此要求。
2. **参照姊妹 spec 现状**：`d1-sync-row-table-engine-and-d1-coverage` 的
   `_INCLUDE_D102_CATEGORY` 现仍 `False`——但读其 tasks.md 确认，D1 自己对应本任务粒度的
   Task 25（"接入 D1-2"）本身标记为 `[ ]*` **未开工**（"声明已交付，灰度未开：...真实接入/
   整册 materialize 验收未做"）。这不能作为"验收完成后应保持 False"的证据，只能证明"D1
   还没做到这一步"。
3. **参照更贴切的姊妹 spec `e1-sync-coverage-and-first-canary`**：其 Task 8（E1-2 canary
   声明，与本 spec Task 6 同构）已把 `_INCLUDE_E102_CASH_DETAIL` 翻为 `True`，注释明写
   "✅ 2026-09-26 开启：声明层判据齐全（15 用例）+ 契约已生成并双向锁死。⚠️ 真栈 materialize
   /§9.6 三谓词仍卡 adapter 未注册（umbrella BP-61-1 平台级缺口）"——即 E1 在真栈同样受阻的
   情况下，仍在"声明层完整"这一步就把开关翻为 `True`，真栈验收单独标注为 `upstream_gap`
   继续追踪。这与本任务最初的预判方向一致（声明层完整 ⇒ 可以翻开关，真栈单独标注）。
4. **🔴 但本任务在实测翻转开关的过程中发现了一个比 E1 先例更具体、更强的反向证据**（见
   下文"实测翻转开关的完整过程"），推翻了"直接照抄 E1 先例翻开关"这一步：翻开关不是单纯
   改一个布尔值——`phase5_d3_prepaid_receipts.py` 有 `assert_contract_file_matches_source()`
   这个磁盘契约 ↔ 现算 payload 的**双向锁死**机制（E1/D1 也有同款机制，是平台通用纪律）。
   翻开关后，`build_contract_payload()` 的现算结果立即与磁盘上已提交的
   `phase5_d3_prepaid_receipts_contract.json` 产生 digest 分叉，**立即打红 3 个既有判据文件
   共 11 个用例**（`test_d3_expansion.py` 3 条 / `test_d3_property3_4_dual_zone_baseline.py`
   3 条 / `test_task5_d3_performance_baseline.py` 5 条）——这些判据文件（Task 2/4/5 的产出）
   全部显式假设"当前 HEAD 状态 = 开关关闭"，是它们各自的基线前提。
5. **完整翻开关的动作实际是两步**：①改布尔常量 ②运行
   `generate_phase5_d3_contract.py --apply` 把新的契约 payload 写入受版本控制的磁盘文件。
   第②步是"修改一个受版本控制、被其它既有判据文件当作基线引用的产物文件"，其影响面超出
   Task 7 本身的验收范围（会让 Task 2/4/5 的既有基线判据一次性失真，它们此后需要重新确认
   "当前状态"的具体含义才能继续被引用）——这不是 Task 7 该单方面决定的事，需要与后续
   Task 8/9（D3-4/D3-5 接入）统一规划"何时批量重生成磁盘契约"，而不是每接一张就单独重生成
   一次（否则 Task 8/9 声明落地后又要再重生成一次，产生多次不必要的契约文件 diff）。
6. **结论**：声明层本身已完整验证（见下文各节），可以在**任何需要"看开关打开后的效果"的
   判据里用 `monkeypatch`/局部构造完成，不依赖开关默认值或磁盘契约文件同步**。开关的默认值
   `False`**继续保持**，与 Task 6 落地时的状态一致，留给后续任务（Task 8/9/10/11/12，届时
   D3-4/D3-5/D3-7 均已声明完毕）统一决定何时批量翻开关 + 重生成磁盘契约，避免多次重复
   生成。这个决定本身也已经用实测验证过其必要性（见下文"实测翻转开关的完整过程"），不是
   凭空拍板。

## 一、实测翻转开关的完整过程（如实记录，不隐藏"试过又改回去"这一步）

```
命令: 编辑 phase5_d3_expansion.py，_INCLUDE_D306_RELATED_PARTY 改为 True
验证: python -m pytest tests/workpaper_sync -k "d3 or D3" -v --tb=short
结果: 11 failed, 61 passed, 3 skipped, 8918 deselected, 3 warnings in 20.77s
```

失败清单（11 个，全部同一根因）：

```
FAILED test_d3_expansion.py::test_switches_off_equals_current_state
FAILED test_d3_expansion.py::test_alignment_guard_reports_exact_diff
FAILED test_d3_expansion.py::test_build_contract_payload_unchanged_when_switch_off
FAILED test_d3_property3_4_dual_zone_baseline.py::test_current_d3_managed_region_count_is_pre_expansion_baseline
FAILED test_d3_property3_4_dual_zone_baseline.py::test_d3_4_dual_zone_not_yet_reaching_target_count_of_four
FAILED test_d3_property3_4_dual_zone_baseline.py::test_d3_7_dual_zone_not_yet_reaching_target_count_of_seven
FAILED test_task5_d3_performance_baseline.py::test_synthetic_engine_layer_baseline_build_store_projection[1]
FAILED test_task5_d3_performance_baseline.py::test_synthetic_engine_layer_baseline_build_store_projection[10]
FAILED test_task5_d3_performance_baseline.py::test_synthetic_engine_layer_baseline_build_store_projection[50]
FAILED test_task5_d3_performance_baseline.py::test_synthetic_engine_layer_baseline_build_store_projection[200]
FAILED test_task5_d3_performance_baseline.py::test_real_db_payload_engine_layer_store_field_count
```

逐一定位根因（以 `test_real_db_payload_engine_layer_store_field_count` 为例，其余 10 条
报错逐字同款）：

```python
def assert_contract_file_matches_source() -> SyncContract:
    expected = build_contract_payload()
    on_disk = load_contract_from_disk()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise EntrySelectionError(
            "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
            f"disk={...} source={...}；"
            "请用 `... generate_phase5_d3_contract.py --apply` 重生成"
        )
```

实测报错：

```
app.services.workpaper_sync.phase5_d3_prepaid_receipts.EntrySelectionError:
磁盘 per-entry contract 与本模块现算 payload 不一致 ——
disk=2cfdb8594e0e8a49a8a51cffc0cd74ac6acca46c5c327ac581e66751a06f430f
source=6a94835b789aa0beb6f42e63ab785c69a9dd3e513b6f070b0bdbee326265fcc4；
请用 `... generate_phase5_d3_contract.py --apply` 重生成
```

**这是一个真实、有意的安全机制在正确工作**（不是 bug）：`phase5_d3_prepaid_receipts.py` 与
`phase5_e1_monetary_fund.py` 都有这套"磁盘契约 ↔ 现算 payload 双向锁死"（grep 确认
`contract_file_path()`/`assert_contract_file_matches_source()` 两侧都有，是平台通用纪律，
非 D3 独有）。翻开关后 `build_contract_payload()` 追加了 D3-6 的 sheet payload，现算结果
与磁盘上仍是"只有 D3-2 一张"的旧契约文件立即产生 digest 分叉，判据立刻检出并给出精确的
补救命令。

**验证后已改回 `False`**，重跑确认恢复原状：

```
命令: python -m pytest tests/workpaper_sync -k "d3 or D3" --tb=short
结果: 72 passed, 3 skipped, 8918 deselected, 3 warnings in 20.24s

命令: python scripts/check/check_sync_provider_golden_digest.py
结果: ✅ golden digest 零回归：26 个 digest 逐个不变
```

`phase5_d3_expansion.py` 里 `_INCLUDE_D306_RELATED_PARTY` 的最终状态是 `False`，但注释已
更新为记录本次实测发现的完整理由（见该文件本体），供 Task 8/9 决定统一翻开关时机时参照。

## 二、Property 2 D3-6 部分转绿——回归复核

**命令**：

```
cwd: backend
python -m pytest tests/workpaper_sync/test_d3_property2_store_item_id_exact_match.py -v --tb=short -rs
```

**结果**：`12 passed, 3 skipped`（与 Task 6 落地时的 `12 passed, 3 skipped` 逐字一致），
`test_d3_06_related_party_store_item_id` 保持 `PASSED`；D3-4/D3-5/D3-7 三条声明级判据保持
`SKIPPED`（对应声明模块仍不存在，属 Task 8/9/11 范围，不受本任务影响）。**回归复核确认成立，
无衰退。**

## 三、Property 1 零回归——回归复核

**命令**：

```
cwd: backend
python scripts/check/check_sync_provider_golden_digest.py
```

**结果**：`✅ golden digest 零回归：26 个 digest 逐个不变`。与 Task 2/6 的实测值逐字一致。
**回归复核确认成立。**

## 四、Property 5——补齐独立可执行判据（Task 6 的缺口）

**发现的缺口**：Task 6 证据文档 §三只用 Python REPL 交互式验证过
`SPEC_D306.formula_mask == ('F12:F16',)`，这次验证**没有落成持久化、可重跑的判据**——
对照上游范式（`test_e1_02_cash_detail_spec.py::test_formula_mask_is_engine_computed` /
`test_phase5_d1_sheet_specs.py::test_formula_mask_matches_e_h_k_columns` /
`test_d2_3_bad_debt_contract.py::test_formula_mask_matches_data_row_ranges` 等），每一个
已交付的 per-sheet 声明模块都有一条**独立**（不与 store_item_id 判据或扩容对齐判据混在
一起）的 `formula_mask` 断言，D3-6 之前唯独没有。

**补齐产出**：新建 `backend/tests/workpaper_sync/test_d3_06_related_party_spec.py`（4 条）：

| 测试 | 验证内容 |
|---|---|
| `test_formula_mask_is_engine_computed` | `formula_mask == ("F12:F16",)`，持久化钉住 REPL 交互验证过的值 |
| `test_formula_mask_derives_from_formula_columns_and_data_row_range` | 用与生产代码相同的构造表达式重新推导，钉住"为什么是这个值"而非只钉字面量 |
| `test_mutation_missing_formula_column_shrinks_mask`（变异） | 去掉 `formula_columns` 后 mask 必须跟着变空，证明非恒定装饰性属性 |
| `test_footer_sum_range_gap_is_a_template_defect_not_a_mask_bug` | 钉住 Task 6 记录的模板预存缺陷（footer SUM 只覆盖 3 行）不影响 mask 的行区间边界（16，非 14） |

**命令 + 结果**：

```
cwd: backend
python -m pytest tests/workpaper_sync/test_d3_06_related_party_spec.py -v --tb=short
======================== 4 passed in 1.03s ========================
```

**结论：Property 5 现在有独立、可重跑的判据文件，全部通过。**

## 五、受管区 1→2——回归复核（monkeypatch）

**命令**：

```
cwd: backend
python -m pytest tests/workpaper_sync/test_d3_expansion.py -v --tb=short
```

**结果**：`7 passed`（与 Task 6 落地时逐字一致），其中
`test_enabling_d306_adds_one_managed_region` 用 `monkeypatch.setattr(P,
"_INCLUDE_D306_RELATED_PARTY", True)` 打开开关后断言：

```python
instr = P.instrumentation_specs()
assert len(instr) == 1, f"受管区应 1→2（扩容面自身应新增 1 项），实得 {keys}"
items = set(P.all_store_item_ids())
assert items == {ENTRY.STORE_ITEM_ID, D306.STORE_ITEM_ID_D306}
```

**回归复核确认成立，受管区 1→2 的判据用 monkeypatch 验证通过（不依赖磁盘契约文件同步，
不受第〇节发现的"翻真开关会打红既有基线判据"问题影响——两者是不同层级：monkeypatch 只影响
当次调用的运行时布尔值，不触碰磁盘文件，因此不会与 `assert_contract_file_matches_source()`
冲突）。**

## 六、"整册 materialize 200"——真栈不可测（引用 Task 5 结论）+ 离线机制层真实验证

### 6.1 "整册 materialize"的精确定位（引用 Task 5 证据，不重新调研）

Task 5 证据（`evidence/task5-performance-baseline-and-adapter-status.md` §一）已精确定位：

* **三端点**：`POST .../pending-mutations` / `GET .../store-projection` /
  `POST .../materialize`（`wp_sync_router.py` :773/:786/:826），共享前置门
  `_registration(svc, scope)`（:713）。
* **"整册 materialize"** = `materialize()` 端点触发的
  `MaterializeCoordinator.materialize()`（`materialize_coordinator.py:1770`），与三端点共享
  同一前置门，非独立第四条路径。

### 6.2 真栈不可测——引用 Task 5 的两条卡点结论，未重复验证

Task 5 已两次独立实测确认：

1. D3 自身 manifest `capability="single_onlyoffice"`（非 `bidirectional`），`attach_adapters()`
   在任何 DB 查询之前短路返回 `()`。
2. 即使解除①，共享的全量 `register_from_manifest()` 会先在 **D2** 的契约漂移处中断
   （`ContractDriftError`），D3 自己是否已注册根本没有机会被判断到。

**本任务未重新验证这两条（避免重复劳动），直接引用 Task 5 的结论：真栈三端点/整册
materialize 在当前环境确认不可测，design.md 裁决 F5 的处置原则（真栈判据如实标 `[ ]*`，
不得以合成测试冒充真栈）适用不变。**

### 6.3 但"整册 materialize"背后的核心机制——离线真实验证（本任务新增，超出 Task 5 范围）

"整册 materialize"真正做的事——把受管区的 identity 载体（Excel Table / UUID 隐藏列 /
defined names）注入模板字节，再校验受管区之外的任何字节都不受影响——这件事的核心机制
（`excel_instrumentation.instrument_workbook_bytes` + `excel_extract.verify_unmanaged_regions`）
是**纯函数**，只吃/吐 bytes，不连库、不依赖 adapter 注册。这正是姊妹判据文件
`test_task42_h1_grouped_dynamic_pilot.py`（H1 首次接入时）采用的离线验证范式（该文件
docstring 第 5 条："插删重排复制真的跑在真实模板上：真实权威模板 → 真实注入产物 → 真实
extract"）。

**新建 `backend/tests/workpaper_sync/test_d3_06_offline_materialize_and_verify.py`（6 条）：**

| 测试类 | 测试 | 验证内容 |
|---|---|---|
| `TestInjectionProducesRealIdentityCarrier` | `test_raw_template_has_no_d306_table_before_injection` | 原始权威模板**真实确认**没有 `GT_D36_ROWS` Table（不是假设的前提，是 openpyxl 直读验证过的事实） |
| 同上 | `test_instrumented_bytes_contain_the_declared_table` | 注入后**真实出现**该 Table |
| 同上 | `test_resolve_managed_region_locates_it_on_instrumented_bytes` | `resolve_managed_region` 在注入产物上真实定位到受管区 |
| `TestVerifyUnmanagedRegionsIsRealNotVacuous` | `test_identity_before_equals_after_is_equivalent` | before==after 时判 `equivalent=True` |
| 同上 | `test_coverage_counts_are_not_all_zero` | 覆盖计数非空非零（`other_sheet_parts>0`，D3 其余 11 张 sheet 落入该 aspect），排除"手搓最小 xlsx 上未管理区域恒为空集，比对必然通过"这一类假绿 |
| 同上（变异） | `test_mutation_touching_an_unrelated_sheet_is_detected` | 改动与 D3-6 无关的另一张 sheet（D3-1）字节，`verify_unmanaged_regions` 正确判 `equivalent=False` 并给出差异细节 |

**命令 + 结果**：

```
cwd: backend
python -m pytest tests/workpaper_sync/test_d3_06_offline_materialize_and_verify.py -v --tb=short
======================== 6 passed in 1.22s ========================
```

**这是 D3/D1/E1 三个姊妹 spec 里第一个把这条离线机制真的跑通并验证的**（D1 Task 25/26、E1
Task 11 目前均仍是 `[ ]*`/未开工，本任务没有等它们先做出示例才动手）。

### 6.4 结论

真栈端到端"整册 materialize"确认不可测（引用 Task 5，标 `[ ]*`，卡点：D3 manifest
capability + D2 契约漂移连带阻塞，均为平台级/跨 spec 缺口，非本任务可解除）。但支撑它的
核心离线机制（注入 + 未管理区域校验）在 D3-6 上**真实验证通过，非合成冒充**。

## 七、`verify_unmanaged_regions` 离线判据——真实验证（覆盖于第六节，不重复列出）

见第六节 6.3——`test_d3_06_offline_materialize_and_verify.py` 的
`TestVerifyUnmanagedRegionsIsRealNotVacuous` 三条测试即是 `verify_unmanaged_regions` 本身
的离线验证（identity 一致性 + 覆盖计数非空 + 变异检出），不依赖 `adapter_registered`。
不再重复建第二份判据文件。

## 八、Property 9——D3-rp-rows 下游消费方在 OO 回写后仍正确重算

### 8.1 下游消费方清单（引用 Task 1 证据，未重新 grep）

Task 1 证据（`evidence/task1-sheet-morphology-and-geometry.md` §四）已 grep 实证
`D3-rp-rows` 的下游消费方清单：

| 消费方 | 位置 | 性质 |
|---|---|---|
| `D3TabIndex.isSheetComplete` | `D3TabIndex.vue:73` | 前端 computed，对 `allResponses` 变化响应式重算 |
| ACNR 导入导出映射表 | `_d3_import_export.py:159` | 后端静态配置，独立的导入/导出端点功能 |
| ACNR manifest | `d_cycle_ie_manifest.yaml:293` | 静态登记 |

**没有** `useD3CrossSheet` 或其它 composable 的跨 sheet computed 读取——只有自身 writer
（`useD3RelatedParty.ts`）+ 完成度判定 + 导入导出映射表。

### 8.2 哪一项适用"回写后仍正确重算"这个 Property，哪一项不适用

* **`D3TabIndex.isSheetComplete`**——适用。它是一个纯 Vue computed，对 `allResponses`
  prop（即 `D3-rp-rows` 等 store 键的实时值）的变化响应式重算，语义正是"给定 store 里的新
  值，下游判定是否正确响应"，与"这个新值是从 OO 回写、HTML 保存、还是任何其它写入路径产生
  的"这件事本身**正交**——Property 9 验证的是响应逻辑的正确性，不是验证数据变化的来源。
* **ACNR 导入导出映射表**——不适用。它是一个独立的、由用户显式触发的导入/导出端点功能
  （`POST /api/workpapers/{wp_id}/d3/export-data`），是静态配置字典（sheet code → store
  key），不是"live store 回写后自动重算"性质的消费方，不存在"重算"这个动作。

### 8.3 真栈不可测部分与可测部分的边界

"OO 回写"这个**动作本身**（真实通过 OnlyOffice 编辑器写格、真实触发 sync 引擎的 merge）
因 adapter 未注册而不可测（同第六节引用的 Task 5 结论）。但 Property 9 的判据主体
——"下游消费方在数据变化后是否正确重算"——是纯前端逻辑，可以完全离线用 Vitest + Vue Test
Utils 驱动，不需要冒充"OO 回写"这个动作本身。

### 8.4 前端离线验证——真实验证（全仓第一个 `D3TabIndex.spec.ts`）

**发现**：全仓此前不存在任何 `D3TabIndex.spec.ts`，但存在姊妹判据文件
`composables/__tests__/tabIndexAcnrCatalog.pbt.spec.ts`，其中已用 `shallowMount` +
`global.provide.jumpToSection` + Element Plus stub 的方式成功挂载了同一组件家族的
`D2TabIndex`/`D4TabIndex`（同一 props 形状：`wpId`/`projectId`/`allResponses: Map`/
`isReadonly`）。本任务复用这套已验证过的挂载范式，套用到 `D3TabIndex`。

**新建 `audit-platform/frontend/src/components/workpaper/d3/__tests__/D3TabIndex.spec.ts`
（5 条）：**

| 测试 | 验证内容 |
|---|---|
| completedCount 基线 | 空 `allResponses` 下的基线值可正常读取 |
| 写入非空行数组后正确 +1 | 模拟"OO 回写 → merge 进 store → allResponses 更新"落到前端的最终形态，`completedCount` 恰好 +1 |
| 空数组 `[]` 不误判完成 | 钉住 `hasJsonRows` 的 `parsed.length > 0` 分支，不因键存在就误判 |
| 非法 JSON 不崩且不误判完成 | 钉住 `hasJsonRows` 的 `try/catch` 分支 |
| 有数据回退到无数据，正确 -1 | 验证"仍正确重算"的双向性——不仅新增要涨，撤销/清空也要正确掉回去，不残留旧状态缓存 |

**命令 + 结果**：

```
cwd: audit-platform/frontend
npx vitest run src/components/workpaper/d3/__tests__/D3TabIndex.spec.ts --reporter=verbose
✓ src/components/workpaper/d3/__tests__/D3TabIndex.spec.ts (5 tests) 100ms
Test Files  1 passed (1)
     Tests  5 passed (5)
```

（仅有 `[Vue warn]: injection "Symbol(router)" not found` 的无害警告，因组件内部
`useRouter()` 在测试环境未提供路由上下文，不影响本文件覆盖的代码路径，不是断言失败。）

### 8.5 结论

**Property 9 真实验证通过**——前端逻辑层面完全验证（可测部分），"OO 回写"这个动作本身
因 adapter 未注册不可测（不可测部分，标 `[ ]*` 并引用 Task 5 结论），两者边界清晰、如实
分层，不是笼统标 `[ ]*` 掩盖掉本可以离线验证的那部分逻辑。

## 九、耗时登记

引用 Task 5 已有的引擎层合成基线数据（`evidence/task5-performance-baseline-and-adapter-status.md`
§三），不重新发明：

| n_rows | store_field_count | elapsed_ms |
|---|---|---|
| 1 | 27 | 0.313 ~ 0.361 |
| 10 | 270 | 0.556 ~ 0.609 |
| 50 | 1350 | 2.277 ~ 2.333 |
| 200 | 5400 | 8.948 ~ 9.289 |

该数据是**引擎层**耗时（`build_store_projection`），不含 HTTP 往返/guard/materialize 写盘
——跳过的正是第六节确认不可达的 adapter 分派层，是当前唯一可离线现测的替代信号。本任务
新增的离线机制层测试（第六节 6.3）未额外测耗时（该测试集中在"正确性"而非"性能"，且样本量
（单张模板一次注入）不足以产出有意义的性能基线，性能基线仍以 Task 5 的引擎层合成数据为准）。

## 十、全量回归验证（超出完成标准要求，作为额外确认）

```
cwd: backend
python -m pytest tests/workpaper_sync -k "d3 or D3" -v --tb=short
======== 72 passed, 3 skipped, 8918 deselected, 3 warnings in 20.05s ========
```

72 passed（Task 6 落地时是 62 passed，本任务新增 10 条全部通过：Property 5 独立判据 4 条
+ 离线 materialize/verify 6 条），3 skipped（D3-4/D3-5/D3-7 声明级判据，不受本任务影响），
零失败零回归。

```
cwd: backend
python scripts/check/check_sync_provider_golden_digest.py
✅ golden digest 零回归：26 个 digest 逐个不变
```

```
cwd: backend
python scripts/check/check_file_size.py
```

新建/改动的文件（`test_d3_06_related_party_spec.py` / `test_d3_06_offline_materialize_and_verify.py`
/ `phase5_d3_expansion.py`）均未出现在超限清单中（该清单现存违规项全部是本任务之前已存在
的历史文件，与本任务无关）。

```
cwd: audit-platform/frontend
npx vitest run src/components/workpaper/d3 --reporter=verbose
Test Files  1 passed (1)
     Tests  5 passed (5)
```

`d3/` 目录下此前无任何 spec 文件，本任务新建的 `D3TabIndex.spec.ts` 是唯一文件，无冲突。

## 十一、新建/改动文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/tests/workpaper_sync/test_d3_06_related_party_spec.py` | 新建 | Property 5 独立判据（4 条），补齐 Task 6 只做过 REPL 交互验证的缺口 |
| `backend/tests/workpaper_sync/test_d3_06_offline_materialize_and_verify.py` | 新建 | 离线"注入 + verify_unmanaged_regions"判据（6 条），"整册 materialize"核心机制的真实验证 |
| `audit-platform/frontend/src/components/workpaper/d3/__tests__/D3TabIndex.spec.ts` | 新建 | 全仓第一个 `D3TabIndex.spec.ts`，Property 9 前端离线判据（5 条） |
| `backend/app/services/workpaper_sync/phase5_d3_expansion.py` | 改动（注释） | `_INCLUDE_D306_RELATED_PARTY` 保持 `False`，注释更新为记录本任务实测翻转开关的完整过程与理由 |

未修改任何模板文件、未修改 Task 3/6 已交付的判据文件（`test_d3_property2_*.py` /
`test_d3_expansion.py` 本体逐字未改，只是被复用/引用）。

## 十二、结论汇总（回应「完成标准」逐项）

1. ✅ 灰度开关最终状态：**维持 `False`**，依据见第〇节（实测翻转发现会打红 3 个既有基线
   判据文件共 11 用例，翻开关的完整动作需同步重生成受版本控制的磁盘契约文件，影响面超出
   本任务单方面决定的范围，留给 Task 8/9 统一规划）。
2. ✅ Property 2/5/1 三项判据的验证结果：Property 2/1 回归复核通过（命令+输出见二/三节）；
   Property 5 发现缺口并补齐（4 条新判据，见四节）。
3. ✅ 受管区 1→2 的验证结果：`monkeypatch` 验证通过（见五节，7 passed）。
4. ✅ "整册 materialize 200"的验证结果：真栈端到端确认不可测（引用 Task 5，如实标 `[ ]*`），
   但核心离线机制真实验证通过（6 条新判据，见六节）。
5. ✅ `verify_unmanaged_regions` 的验证结果：真实验证通过（覆盖于六节的判据内，见七节）。
6. ✅ Property 9 的验证结果：分层验证——前端下游消费方逻辑真实验证通过（5 条新判据，见
   八节），"OO 回写"动作本身如实标 `[ ]*`（引用 Task 5 结论）。
7. ✅ 耗时登记：引用 Task 5 已有数据，未重新发明（见九节）。
8. ✅ 产出证据记录：即本文件。

## 十三：D3-6 接入验收是否通过

**部分通过**：声明层与离线可测部分（Property 1/2/5、受管区 1→2、`verify_unmanaged_regions`
机制本身、Property 9 前端下游消费方逻辑）**全部真实验证通过**，新增 15 条判据（后端 10 +
前端 5）全部通过、零回归；真栈相关部分（端到端"整册 materialize"、真实 OO 回写动作本身）
如实标 `[ ]*`，卡点是平台级/跨 spec 缺口（D3 manifest capability + D2 契约漂移，Task 5 已
定位，非本任务可解除）；灰度开关经实测后维持 `False`，理由是翻开关的完整动作会牵连 3 个
既有基线判据文件且需同步重生成磁盘契约，决定权留给后续任务统一规划，不是回避决策。
