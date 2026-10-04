# Task 12 证据：D3-7「预收账款检查表」接入验收

**执行日期**：2026-09-26　**任务**：Task 12（D3-7 接入验收）
**Requirements 3.3, 3.4, 6.1**　**方法**：翻灰度开关 + 重生成磁盘契约 + Property 4 转绿 +
双区位移链实证 + Property 9 前端重算真验 + 整册 7 区 materialize + golden digest + 全量 D3 回归。
全程离线（不连库、不依赖 adapter 注册）。一次性探针（`_tmp_d37_task12_probe.py` /
`_tmp_d37_twopass_diff.py` / `_tmp_d37_twopass_5.py` / `_tmp_d37_fullbook.py`）用完即删。

---

## 一、翻开关 + 重生成契约（受管区 5→7）

- `phase5_d3_expansion._INCLUDE_D307_VOUCHER_CHECK`：`False → True`（Task 11 只声明不翻，本任务翻）。
- **D3-7 无模板缺陷**（Task 11 openpyxl 已确认）：两区合计行 A27/A39 精确「合计」、SUM 区间
  `G17:G26`/`G31:G38` 覆盖全部数据行、末行 R26/R38 非 BP-21 占位行 ⇒ **本任务不改模板**。
- 跑 `python backend/scripts/gen/generate_phase5_d3_contract.py --apply` 重生成磁盘契约：
  `canonical_digest=fb48ff50bc5d99e05b17c1dd26b42ae45cb7b481b70c58de3ee471adf5c6fffa`。
- `assert_contract_file_matches_source()` **通过**（双向锁死）。
- 受管区实测分布（探针核对）：**总数 7** = `d32-managed:1` + `d36-managed:1` +
  `d34-managed:2` + `d35-managed:1` + **`d37-managed:2`**。
- `d37-managed` 是**一个**契约 sheet 条目（`excel_name=预收账款检查表D3-7`）含**两 table**：
  `voucher_check_current_rows`（store `D3-vc-current-rows`，anchor A15，两级表头 header_rows=2）+
  `voucher_check_post_rows`（store `D3-vc-post-rows`，anchor A29，header_rows=2），两键各归其表。

---

## 二、Property 4（D3-P4）转绿

判据文件 `tests/workpaper_sync/test_d3_property3_4_dual_zone_baseline.py`（Task 4 红基线）迁移：

- `_STAGE2_REGIONS_BY_SHEET` 追加 `d37-managed:2`（总数 5→7）。
- `test_current_d3_managed_region_count_after_stage2_is_five`：断言值 `count==5 → count==7`，
  按 sheet_key 逐项钉死分布（函数名保留历史沿革，无外部代码引用）。
- `test_d3_7_dual_zone_not_yet_reaching_target_count_of_seven`：**从"未接入红基线"转绿**——
  照抄 D3-4 的 `test_d3_4_dual_zone_both_keys_declared_in_one_sheet` 改法，改为断言 D3-7 同一
  sheet 条目（共享 `d37-managed`）恰 2 个 table、两键 `D3-vc-current-rows`/`D3-vc-post-rows`
  各归其表 + 已接入 D3-4 两键的查法非空转见证。新增 `_D37_KEYS_BY_TABLE` 独立真源。
- **§2 三组合成变异用例原样保留不动**（`test_mutation_d3_4_*` / `test_mutation_d3_7_*` /
  `test_mutation_merging_*`）。
- 结果：**6 passed**（3 计数/双区判据 + 3 变异用例）。

---

## 三、双区位移链实证（新建 `test_d3_07_dual_zone_shift_and_verify.py`）

照抄 D3-4 `test_d3_04_dual_zone_shift_and_verify.py` 的 `_synthetic_definitions` +
`build_excel_adapter(sibling_bindings=…)` + `materialize` + `verify_unmanaged_regions` 范式，
走真实离线管线。**14 passed + 2 xfailed。**

| 判据 | 内容 | 结果 |
|---|---|---|
| 前提 | 两区共享 `d37-managed`、区①（17-26）在区②（31-38）之上 | ✅ |
| sibling 参数化覆盖 | D3-7 自动进入 `test_sibling_table_ref_row_shift._multi_region_sheets`（2 区） | ✅ |
| footer 形态对照 | 两区 footer 都是标准 `SUM(range)`（G27=SUM(G17:G26)/H27/G39），无 D3-4 段①散落单格公式漏算问题 | ✅ |
| 单趟位移 | 区①插 5 行 → 区②兄弟 Table ref 随之整体下移 + `verify_unmanaged_regions` equivalent | ✅ |
| 两趟累积 | 区①+5 / 区②+5 → `CompositeRowShift` 累积归一化 + verify equivalent | ✅ |
| `_GT_SYNC` 重冻结 | 区①插行后 `GT_FOOTER_ROW_D37CURRENT` 按 `row_shift.count` 下移；区②的 `GT_FOOTER_ROW_D37POST` 也随之下移（声明与物理同源） | ✅ |

### 🔴 实证发现两处引擎边界（登记不修，xfail strict）

与 D3-4 §7「footer 散落单格差异公式区间不扩张」同族——都是**上游行表引擎**
（`adapters/excel._sheet_cumulative_shift` / `CompositeRowShift` / footer 归一化）在特定位移
几何下的真实边界，非 D3-7 声明缺陷（几何/字段/footer marker 全部实测正确），修复须动引擎累积
归一化逻辑（blast radius 覆盖全平台同 sheet 多受管区、跨 lane），超出本 spec（纯声明层）范围。
按 Task 10 §7 已确立处置原则「引擎边界登记不修、如实暴露、不代为规避」钉为 `xfail(strict=True)`
（引擎修复后自动转红提醒摘标记）：

1. **孤立场景（primary=D3-7-current）区①插行数恰 == 2 撞行**：区①插 2 行 ⇒ 区① footer 从 27
   位移到 29 == 区②组标题行 29 ⇒ 累积归一化对 sheet 尾部（比例检查块 41-44 + note/conclusion）
   misalign ⇒ `managed_sheet_unmanaged_cells` 漂移。逐值扫描：N=11(插1)✅ N=13(插3)✅ N=14✅
   N=15(插5)✅ N=16✅，**仅 N=12(插2)❌**（与区②插行数无关）。触发条件精确锁定在 footer/header
   撞行临界点。
   → `TestKnownEngineBoundaryFooterHeaderCollision::test_region1_insert_exactly_two_rows_...`
2. **整册场景（primary=D3-2、D3-7 两区为 sibling）区①作为非主 sibling 插任意行**：full-book
   下 `cur≥15`（区①插行）即 DRIFT，`cur=5/post=13`（仅区②插）✅、`cur=5/post=5`（两区不插）✅。
   与孤立场景（+5/+5 通过）表现不同 ⇒ misalign 与「插行的那一区是不是主 binding + 是不是上区」
   相关，根同在 `_sheet_cumulative_shift` 对非主 sheet 同 sheet 多区的位移合并。
   → `TestKnownEngineBoundaryFooterHeaderCollision::test_fullbook_region1_sibling_insertion_...`

生产后果：均为 **fail-closed（显式 `adapter_unmanaged_region_drift` 500，非静默错数据）**，仅在
上述特定插行几何触发；正常接入路径（区②插行 / 区①插 ≠2 行的孤立场景 / +5/+5）不受影响。

---

## 四、Property 9（D3-P9）前端重算（可测部分真验 + OO 回写标 `[ ]*`）

判据文件 `audit-platform/frontend/src/components/workpaper/__tests__/useD3CrossSheet.spec.ts`
新增 Property 9 describe 块（8 tests 全绿：5 原有 + 3 新增），Vitest 真跑：

- `useD3CrossSheet.postPeriodSettlementSync` 读跨 sheet store 键 `D3-vc-post-rows`
  （`useD3CrossSheet.ts:366` 附近，D3-7 区②期后结转的下游消费方），按客户聚合贷方金额 + 合计。
- **可测部分真验**（前端逻辑层）：①给定 `D3-vc-post-rows` 载荷 → byCustomer 累加 + total 正确；
  ②**OO 回写后重算**：替换 `allResponses` Map（模拟回写已到达 store）→ computed 重算到新值、
  旧值不残留；③fast-check property（numRuns 100）：total ≡ SUM(creditAmount)、byCustomer 按
  非空客户名累加、无空客户名聚合键。
- **OO 回写动作本身标 `[ ]*`**：在线编辑 → OO canvas 键入 → forcesave → 后端 rematerialize →
  store 更新这一整段真栈不可测（D3 adapter 真库未注册，裁决 F5；OO 协同通道写格三陷阱，需求 8.4），
  同 Task 5/7 结论。这里用替换 Map 模拟"回写已到达 store"这一可观测结果，不冒充真栈。

---

## 五、整册 7 区 materialize + 引擎层耗时

同一文件 `test_d3_07_dual_zone_shift_and_verify.py`：

- **整册 7 区**（`TestFullBookSevenRegionMaterialize`）：D3-2 primary + D3-6 / D3-4借 / D3-4贷 /
  D3-5 / D3-7区① / D3-7区② 全 sibling，一次 `adapter.materialize` + `verify_unmanaged_regions`
  **equivalent=True**。7 区字段全部进 projection（断言覆盖全 7 区、非只前 5 区）。
  🔴 D3-7 区① 给 5 行（present-no-insert）、区② 给 13 行（+5 插行）——因区①作为非主 sibling
  插行触发 §三.2 引擎边界（登记不修），本判据用「区① present-no-insert + 区② 真插行 + 其余
  五区真插行」覆盖 7 区 verify 归一化（插行归一化边界另有专判据钉）。
- **引擎层耗时**（`TestEngineLayerTimingBaseline`，`build_store_projection` 1/10/50 行，
  两 spec 各测）：

  | store 键 | n=1 | n=10 | n=50 |
  |---|---|---|---|
  | D3-vc-current-rows | field=17 / 0.28ms | field=170 / 0.54ms | field=850 / 2.71ms |
  | D3-vc-post-rows | field=16 / 0.43ms | field=160 / 0.67ms | field=800 / 2.10ms |

  🔴 **引擎层非真栈**（同 Task 5/10 口径）：只测「provider 把 store payload 现算成 projection」
  纯函数耗时，不含 HTTP / registration / materialize 写盘 / OnlyOffice room。真栈端到端耗时
  受 D3 adapter 未注册阻塞（裁决 F5），标 `[ ]*`。

---

## 六、Property 1 golden digest（漂移只在 D3 d37 新增）

`python backend/scripts/check/check_sync_provider_golden_digest.py`：**87 个 digest 逐个不变，零回归**。

- D3-7 翻开关后 D3 契约整体 canonical digest 变（新增 d37 sheet），但门禁按 sheet 粒度 + provider
  级 `store_projection_sha256`/`instrumentation_sha256` 比对：
  - **d37-managed 是新增 sheet 条目 ⇒ additive**（base 无此 key，`_compare` 不判回归）；
  - D3 已有 4 张 sheet（d32/d36/d34/d35）digest **逐字不变**；
  - D3 `instrumentation_sha256` **不变**（d3 `plural_instr=False`，门禁读单数 `instrumentation_spec()`
    = D3-2 自身，不含扩容面）；D3 `store_projection_sha256` **不变**（用 `STORE_ITEM_ID`=D3-2）；
  - **其余 8 家 provider**（b60/d1/d2/d4/d5/d6/d7/e1）digest 逐个不变。
- 实测发现磁盘基线 `_sync_provider_golden_digest.json` **已含 d37-managed + d3 contract=fb48ff50**
  （本工作区 D3-7 声明期先前已同步过基线），`--update` 幂等（git 显示基线文件字节不变、无 diff）。
  ⇒ 漂移确认为**纯 additive 的 d37 新增**，未波及别的 provider 或 D3 已有 sheet。

---

## 七、全量 D3 回归

`python -m pytest tests/workpaper_sync -k "d3 or D3" -q --tb=line -p no:cacheprovider`：
**2 failed / 118 passed / 4 xfailed / 9090 deselected**。

### 两条失败均为已知红 / 并发 lane 在途，**非本任务引入（本任务新增失败 = 0）**

1. `test_task5_d3_performance_baseline.py::test_real_registration_path_fails_before_reaching_d3`
   （"DID NOT RAISE"）——**任务原文已列此为已知基线红**（真库 `register_from_manifest()` 断言
   抛错，与别 lane entry 契约漂移相关，与 D3-7 声明层零关联）。
2. `test_sibling_table_ref_row_shift.py::test_all_multi_region_sheets_shift_sibling_table_refs
   [...D1-8]`（`TypographyRowError` on `关联方关系及交易检查表D1-11`：声明的受管行末行 13 落在
   BP-21 排版占位行上）——**并发 lane 在途改动**：`git status` 实证
   `phase5_d1_11_related_party.py` 处于 **Modified** 状态（另一会话对 D1-11 的未提交编辑）。
   **归因证明**：把 `_INCLUDE_D307_VOUCHER_CHECK` 临时改回 `False` 重跑该参数化判据，同一批 D1
   sheet（D1-4/D1-7/D1-8/D1-13/D1-15/D1-16）**仍全部失败**同一个 D1-11 typography 错——⇒ 与
   D3-7 开关状态无关，纯 D1 lane 在途状态，随后已把开关恢复 True。

（任务原文另列的两条已知红 `test_row_table_engine_core_equivalence::…[d3]` /
`test_excel_row_insertion_scope_closure::…definition_store` 在本轮 `-k "d3 or D3"` 过滤集内通过
或未收集，不在本轮失败里。definition_store 内容寻址重发布同 Task 10 §11.4 处置：本任务同样不跑
`fix_task76…--apply`，如实登记为已知红、非本任务引入。）

### 本任务自身判据全绿（合并复核）

`test_d3_07_dual_zone_shift_and_verify.py` + `test_d3_property3_4_dual_zone_baseline.py` +
`test_d3_expansion.py` 合并跑：**29 passed / 2 xfailed**（2 xfail 为 §三登记的引擎边界）。
前端 `useD3CrossSheet.spec.ts`：**8 passed**（Vitest）。

---

## 八、结论（回应完成标准）

1. ✅ 开关 True + 契约重生成 + 受管区 **7** + `assert_contract_file_matches_source()` 通过（不改模板）。
2. ✅ Property 4（D3-P4）转绿；受管区计数判据更新为 7；三组变异用例保留不动。
3. ✅ 双区位移链：区①插行→区②下移 + verify equivalent（单趟 +5 / 两趟 +5/+5）+ `_GT_SYNC`
   `GT_FOOTER_ROW_D37CURRENT`/`D37POST` 重冻结；D3-7 进入 `test_sibling_table_ref_row_shift`
   参数化清单。🔴 实证两处引擎累积归一化边界（登记不修，xfail strict）。
4. ✅ Property 9 前端重算可测部分真验（byCustomer/total + OO 回写后重算 + fast-check）；OO 回写
   动作标 `[ ]*`。
5. ✅ 整册 **7 区** materialize + verify equivalent；引擎层耗时登记（1/10/50 行，非真栈）。
6. ✅ golden digest 零回归（87 digest）：漂移只在 D3 d37 新增（additive），其余 7 家 + D3 已有
   sheet 不变；`--update` 幂等（基线已含 d37）。
7. ✅ 全量 D3 回归 2 failed（均已知红/并发 lane，逐条确认非本任务引入，新增失败 = 0）；4 xfailed。
8. 未碰引擎代码 / 模板 / tasks.md 标题行与复选框 / 别的会话在途文件；一次性探针用完即删。
