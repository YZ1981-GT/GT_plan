# Implementation Plan

## Overview

**spec**：`workpaper-sync-row-table-engine-and-d1-coverage`　**创建**：2026-09-25　**状态**：声明层封顶 + adapter 注册 + 灰度全开；整册门/存量迁移/四态/Playwright 卡外部依赖，如实标 `[ ]*`

> ✅ **2026-09-26 阶段 0~2（Task 0~14）完整交付并验证**：24→23 个 golden digest 基线（B60 无
> `build_store_projection` 故实为 23，脚本已修正注释）/ P9 红判据先行后**完全转绿**（17→0 处
> 命中）/ P10 红判据先行后**完全转绿**（10 个 adapter 全注册）/ O(1) 查表判据通过。
> `sheet_geometry.py`（Task 5）/ `phase5_row_table_sheet.py` 的 `RowTableSheetSpec` + `AgingLayout`
> + 引擎核心函数（Task 6~9）/ `attach_sibling_bindings` 泛化（Task 10）/ `store_item_registry.py`
> 的 `StoreItemSpec`/`StoreMergePlan`/注册表（Task 11/12）/ `oo_to_html.py` + `adapters/excel.py`
> 改注册表分派（Task 13/14）均已交付、判据齐全（119 用例全绿，含变异反证）。
> **直接解锁**：`d567-sync-coverage-via-row-table-engine` 前置门已解除（Task 0 核查用两个核心
> 类型构造 D5-4/审定表D5 声明实例成功）。
> ✅ **Task 15/23/25/26/31 部分交付**（commit `f1ec1c67d`，此前会话产出，本轮补齐判据验证）：
> `phase5_adjudication_sheet.py`（`AdjudicationSheetSpec`，Task 31）/ D1 sheet 声明层
> `phase5_d1_02_category.py` + `phase5_d1_04_bad_debt.py`（Task 25/26，灰度开关全 False 未启用）/
> `phase5_d1_expansion.py` 扩容骨架（Task 23，`instrumentation_specs()` 复数 + 对齐守卫）。
> 🔴 **Task 15 本体（entry 模块瘦身到 ≤150 行）未完成**：`phase5_d1_notes_receivable.py` 仍
> 1059 行，远超设计要求的 ≤150 行上限——现状是"扩容骨架已就位"而非"循环层已收敛"。
> ✅ **Task 16 引擎函数层部分完成**（2026-09-26）：D3/D6/D7 三家新增 `SPEC_D{32,62,72}` 唯一
> 权威声明，9 个引擎函数改薄转发框架层；发现并修复框架层缺口 `RowTableSheetSpec.
> ghost_row_anchor_index`（D5/D6 幽灵行防护锚点非默认第 0 位）。golden digest 零回归（26 个）+
> 141 个判据全绿。`≤150 行`上限**未达成**（三家仍 869~878 行，只收敛了引擎函数层，契约装配/
> 发布编排代码尚未拆分）。
> ✅ **Task 20~22（CI 门禁接入）+ Task 24（位移判据参数化）已完成**（2026-09-26）：两个
> CI job（`row-table-engine-and-registry-guards`/`e1-sync-coverage-guards`）已入
> `governance-checks.yml` 并逐条本地复测通过；`test_sibling_table_ref_row_shift.py` 的
> 判据 6 从硬编码 D4 改为按 provider 参数化（实施中抓到并修复一处真实的 spec 聚合重复计入
> bug），变异反证证明其确能自动覆盖 D1-4 等尚在灰度中的新多区 sheet。
> ✅ **Task 19（B60/D4 过门）+ Task 30（D1-6 可行性评估）已完成**（2026-09-26）：Task 19 的
> **真栈段首次跑通** —— D4 整册 materialize+extract+verify 全绿（真库 gen=164，12.4s，
> `equivalent=True`，受管 sheet 现算实测 30 与描述相符），脚本
> `backend/scripts/e2e/verify_d4_full_book_real_stack.py` 可重跑；Task 30 判定 D1-6 的 4×3
> QA 矩阵**两条路径都表达不了**（`static_region` 卡在 `contracts.py:_parse_field` 的
> `row_from` 只收单行号这条 schema 硬约束），按需求 5.6 登记 `NOT_EXPRESSIBLE`。
> ✅ **D1 全 21 张 sheet 声明层/评估全部封顶**（2026-09-26）：
> **16 张有声明**（D1-1 AdjudicationSheetSpec / D1-2/3/4 此前 / D1-7 dict+专用merge /
> D1-8/9/10/11/12/13/15/16 本轮 RowTableSheetSpec）+ **5 张裁决/评估**
> （D1-5 single_html / D1-6/D1-14/附注×2 NOT_EXPRESSIBLE）+ D1A 不需双向回写。
> 自查修了 Task 16/17 遗留的 **4xx→500 回归**（D5/D6/D7 错误转译，D3 strict xfail 待修）。
> **尚未开工**：Task 15/16/17 本体的 ≤150 行收敛（剩余是发布编排需先补判据）、Task 18
> D2 由并发 d2 spec 推进、Task 25-29 灰度接入（卡 adapter 注册平台级缺口）、
> Task 32/33（审定表存量迁移+四态状态机，卡真库 per-cell 数据）、Task 34（验收）。
> 下方复选框为唯一进度真源，本节仅摘要。

顺序有意义：**阶段 0 是红判据与基线先行** —— 24 个 golden digest 此时必绿（它是基线不是判据），
P9/P10 此时必红（框架层现有 89 处 D4 提及、注册表尚不存在）。没有这两侧，后面"修好了"与
"判据本来不会红"区分不开。

**阶段 1→3 刻意分成"先抽引擎、再逐家切换"**：引擎落地时六家 provider 一行不动（引擎无人调用、
门恒绿），切换时一家一个 commit、一家过一次门。任一家切崩只回滚那一家。

**阶段 5 之后每批次都有一条整册 materialize 实测**（需求 8.3）：耗时超软上限就停下转性能 spec，
不带着退化继续铺量。

**受管区增长路线**（2026-09-25 按值 grep 重算，首版按「一 sheet 一区」估的数字全部偏低）：
`1 → 2(D1-2) → 5(D1-4 三区) → 9(批次2) → 15(批次3，含 D1-15 双区) → 18(批次4，含 D1-13 双区)
→ 19~20(批次5) → 22~23(批次6 D1-1 三区)`。

🔴 **该路线仍是下限，Task 1 实测后须重算**（第二轮复盘发现）：它按「标量 item = 0 受管区」算，
而按 D4-13 先例纯标量应走 `static_region` 各占一个受管区 —— D1-14 十项 + D1-13 十五项 +
D1-10 三项共 **28 个标量**的形态待实测（`static_region` vs HTML-only），终值可能显著更高。
详见 design §附：D4 已验证的形态谱系。下方复选框为唯一进度真源。

## Tasks

### 阶段 0：基线与红判据先行

- [x] 0. 前置依赖入库核查（**开工第一件事**）✅ 2026-09-26：`git show HEAD:` 确认 `merge._protection`
  的 `_mask_spans_data_column` 格级判定已入库、判据文件已跟踪，前置无阻塞
  - 用 `git show HEAD:<path>` 判定（**不读工作树** —— 本 spec 调研期间正因读工作树而一度把
    `_protection` 登记成"已修复"）
  - 实测现状：`merge.py` 的 `_mask_spans_data_column` **HEAD 不含**、仍是只比列旧实现；
    判据 `test_masked_cell_protection_is_cell_level.py` 为 `??` 未跟踪
  - IF 未入库 THEN 批次 6（任务 31~33）阻塞；批次 1~5 不受影响可照常推进
    （明细类 mask 全为列向区间、行范围恰等于数据区 ⇒ 只比列与格级判定等价）
  - 同时核 `e2e/d4-*.spec.ts` / `errorEnvelopeNormalisation.spec.ts` 等被零回归门依赖的未提交产物
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 1. 24 个 golden digest 基线脚本 ✅ `check_sync_provider_golden_digest.py` + 5 用例；
  实测 23 个（B60 无 `build_store_projection`）；曾因 `__pycache__` stale 字节码取到假基线，
  已修复（清缓存 + importlib.reload 防护）
  - 对 8 个已交付 contract（b60 / d1 / d2 / d3 / d4 / d5 / d6 / d7）各取三个 canonical JSON sha256：
    `build_contract_payload()` / `build_store_projection(合成 payload)` / `instrumentation_spec(s)()`
  - 落 `backend/scripts/check/check_sync_provider_golden_digest.py`，digest 存同目录 JSON
  - D3/D5/D6 的 store item 真库 0 行 ⇒ 用**合成 payload** 驱动，不得跳过（需求 4.5）
  - 此时必绿；记录 24 个 digest 实测值
  - _Requirements: 4.1, 4.5_

- [x] 2. P9 红判据：框架层 wp_code 分支扫描 ✅ `check_framework_layer_has_no_wp_code_branch.py` +
  6 用例；实测先打红 17 处（非估算 89/9/9），Task 13/14 后已转绿见任务 20
  - AST 扫 `oo_to_html` / `merge` / `excel_extract` / `excel_materialize` / `adapters/excel` /
    `store_projection_response`，断言零 wp_code / contract_id / adapter_id 字面量分支
  - **现状必红**：记录实测命中数（预期 oo_to_html 89 提及 + 9 elif / excel_extract 8 / merge 5 /
    adapters-excel 2 / excel_materialize 1）
  - _Requirements: 7.1_

- [x] 3. P10 红判据：spec 声明未接注册表必红 ✅ `check_sheet_specs_fully_registered.py` +
  2 用例；registry_module_missing 形态红已实证，Task 12 后转绿见任务 21
  - 照 `check_store_item_ids_fully_wired.py` 范式（已验证：46 item 收敛 + 变异反证）
  - 此时注册表尚不存在 ⇒ 判据以"注册表模块缺失"形态红，记录
  - _Requirements: 7.2, 7.4_

- [x]* 4. P13 性能基线：三端点同 substrate 实测耗时
  - ✅ 可离线部分：`check_sync_registry_lookup_is_o1.py` O(1) dict 查表判据通过（dict 比值 1.0
    ≤ 8.0 容差，线性对照比 625 反证成立）
  - `[ ]*` 真栈三端点耗时：D1 的 `adapter_id=None`（legacy_fake_bidirectional）⇒ 无
    published representation，真栈跑不起来。代码已改但未实测，卡点同裁决 G6/F5
  - _Requirements: 8.1, 8.4_

### 阶段 1：框架层抽取（引擎落地，六家 provider 一行不动）

- [x] 5. `sheet_geometry.py`：收敛 `_snake` / `_col_index` 四份复制 ✅ D2/D3/D6/D7 均改薄别名，
  3 用例含逐字节等价性检验全绿，golden digest 零回归
  - 从 D2/D3/D6/D7 抽出，逐家改为 import；**行为逐字节等价**（两个纯函数，可穷举验证）
  - 任务 1 的 24 digest SHALL 零变化
  - _Requirements: 1.4, 4.2_

- [x] 6. `RowTableSheetSpec` 冻结数据类 + `formula_mask` property + **形态谱系三维**（复盘补）✅
  `phase5_row_table_sheet.py` 含 binding_kind/row_identity_key 三形态/html_only_item_ids 全部落地
  - 🔴 **复盘补的三个声明维度**（首版把「受管 sheet」等同「行表」，漏掉引擎**已有**且 D4 已用于
    生产的另两条路径，详见 design §附：D4 已验证的形态谱系）：
    * ① **`binding_kind`**：`excel_table`（动态，Table + UUID 列）vs `static_region`
      （静态，workbook-scope definedName、无 Table 无 UUID 列、**绕开整条位移链**）。
      复用 `excel_extract.BindingKind`(:606) + `_plan_static_writes`(`excel_materialize.py:1657`)
      + `_static_region_bindings(provider=…)`(`projection_first_publication.py:1293`)，
      **不新造第三种**。参照 D4 三实现：`phase5_d4_erp_check_sheet`(D4-13 单 cell) /
      `phase5_d4_product_margin_sheet`(D4-8) / D4-33(72 static cell)
    * ② **`row_identity_key` 三形态**：`rowId`（UUID 动态行）/ `key`（稳定 key 固定行 ——
      仍是 `excel_table` binding 且**仍注入 UUID 列**，D4-6 范式 `ROW_IDENTITY_KEY_D46="key"`）/
      无（走 `static_region`）。判据是「有没有行维度」而非「行会不会变」
    * ③ **HTML-only item 子集**声明位：受管 sheet **≠** 全部 item 受管。先例
      `HTML_ONLY_ITEM_IDS_D45` 三项因「footer 下 `static_row` 与插行 fail-closed 冲突」保持 HTML-only
  - 🔴 判据：`StoreKind`（store 载荷形状）与 `binding_kind`（Excel 侧几何）是**正交两维**；
    变异把 `fixed_text` 直接判「0 受管区」⇒ 必红（这正是首版的错法，据此把 D1-14 的 10 个标量
    误标为 0 受管区）
  - 字段集其余部分严格按 design §Components（七家实测共性），不多加「将来可能用到」的字段
  - P2 判据：对七家各构一份 spec，`formula_mask` 输出 ≡ 原手写 mask 字面量**逐元素相等**
  - _Requirements: 1.1, 1.2, 11.1, 11.2, 11.3, 11.4, 11.5_
  - 字段集严格按 design §Components（七家实测共性），不多加"将来可能用到"的字段
  - P2 判据：对七家各构一份 spec，`formula_mask` 输出 ≡ 原手写 mask 字面量**逐元素相等**
  - _Requirements: 1.1, 1.2_

- [x] 7. `AgingLayout` + `AgingGroupSpec` + `_expand_aging_fields` ✅ P4 变异反证已验证
  （flat 数据塞 nested 分支 fail-closed 拒绝，见 `TestProperty4AgingLayoutIsolation`）
  - nested（D3/D7）/ flat（D6）两种 key 派生各自复刻原写法，引擎内**只剩一处 if**
  - P4 判据：把 flat 走 nested 派生 ⇒ D6 必红（变异反证先写）
  - _Requirements: 1.3_

- [x] 8. `managed_field_specs(spec)`：取代四家逐字相同的 `sorted(...)` ✅ P3 判据用 D7(nested)/
  D6(flat) 真实原始数据逐元组匹配 provider 原表达式；变异实测打红（排序 key 改错立即红）
  - P3 判据：对 D2/D3/D6/D7 四家，引擎输出 ≡ 原 `tuple(sorted(SCALAR + _aging(), key=_col_index))`
    **逐元组相等**（含顺序）
  - _Requirements: 1.3_

- [x] 9. 行表引擎核心：`build_store_projection` / `merge_projection_into_store_rows` /
      `build_contract_payload` / `stable_key_for` / `iter_store_rows` / `split_store_row`
  - 33 个同名函数里属于行表域的那批，每个在框架层恰有一处实现
  - nested/flat 的 store 读写走收敛后的 `_resolve_json_path` / `_set_json_path`（原四份复制）
  - 引擎此时**无人调用**，24 digest 恒零变化（这是本阶段的安全性来源）
  - _Requirements: 1.1, 1.5, 2.3_

- [x] 10. `attach_sibling_bindings(provider=…)` 泛化 ✅ 2026-09-26：D4 侧改薄转发，P8 判据用
  既存 `test_d4_1_sibling_binding_alignment.py` 验证逐字节等价（含变异反证 6 用例全绿）
  - 从 `phase5_d4_revenue_detail._attach_sibling_bindings`（:2666）提出，**函数体不动**，
    只把硬编码 `import … as _provider` 改成参数
  - 继续调已有框架内核 `_align_specs_to_sibling_tables` / `_static_region_bindings`，
    **不重写对齐规则**（publish 与 attach 共享，重写必漂移）
  - P8 判据：对 D4 产出的 binding 元组 ≡ 泛化前（逐字段相等，含顺序）
  - _Requirements: 1.5, 2.4_

### 阶段 2：注册表化（删 elif 链与 hasattr 试探）

- [x] 11. `StoreKind` + `StoreItemSpec` + per-item default 规则 ✅ `store_item_registry.py`；
  15 用例含 dict 绝不能拿 "[]" 的事故背书断言
  - default 必须 per-item（rows→`[]` / dict→`{}` / fixed_text→`''`），**不得** blanket `"[]"`
  - 这条有事故背书：dict-store 拿列表默认会抛非 domain ValueError 冒泡成 opaque 500
    （`store_projection_response.py:207`）
  - _Requirements: 3.2_

- [x] 12. `STORE_MERGE_REGISTRY` O(1) dict + `resolve_store_merge_plan` ✅ 10 个 adapter 已注册；
  P6/P7 判据全绿（静默 return 变异反证 + O(1) 规模不敏感反证）
  - 未命中抛 `StoreMergePlanNotRegisteredError`（含已注册清单），**禁止**静默 return
  - P6 变异：改成静默 return ⇒ 必红。P7 判据：规模递增的合成注册表，查表耗时不随规模上升
  - _Requirements: 3.4, 3.5, 8.2_

- [x] 13. `oo_to_html._mirror_store_backed_if_needed` 改走注册表 ✅ 2026-09-26：9 elif 链 +
  6 hasattr 试探（实测非估算 10/6）全部改注册表分派；新增 `DedicatedStoreItem` + 统一循环
  `_mirror_dedicated_dict_stores`；`adapters/excel.py` 2 处 g7 字面量分支同批改 `oo_crash_neutralization_fn`
  声明。P9 判据从 17 处命中转为 **0（完全转绿）**，变异实测反证（回退成字面量分支立即红）
  - 删那条 9 分支 `elif adapter_id ==` 链（b60/d1/d2/d3/d4/d5/d6/d7/g7/h1）
  - 删 9 处 `hasattr(bridge, "STORE_ITEM_ID_D4xx_DICT")` 试探，改 `StoreItemSpec.kind` 分派
  - 24 digest 零变化 + 8 contract 的 merge 输出逐字段等价
  - _Requirements: 3.1, 3.2, 4.2_

- [x] 14. 出/回两方向 store item 清单同源 ✅ `store_projection_response.py` 已用
  `all_store_item_ids()` 主路径（HEAD 既有实现，非本次改动），`oo_to_html.py` 经 Task 13
  改注册表后与出方向同源；D1 侧 `phase5_d1_expansion.all_store_item_ids()` 单一口径同此纪律
  - `store_projection_response` 与 `oo_to_html` 均取 `all_store_item_ids()`，删
    `STORE_ITEM_IDS_D45_FIXED` 等回退分支
  - P5 判据：两方向集合**逐元素相等**；变异删一个 item ⇒ 必红
  - _Requirements: 3.3_

### 阶段 3：六家 provider 声明化（一家一 commit，一家过一次门）

- [ ]* 15. D1 声明化：`phase5_d1_notes_receivable` → ≤150 行（**引擎函数层已收敛（2026-09-26），
  ≤150 行上限仍未达成**：1060 → 983 行）
  ✅ **本轮交付（引擎函数层收敛，与 D3/D6/D7/D5 同款处置）**：删 `store_row_identity` /
  `iter_store_rows` / `split_store_row` 三个**模块内部** helper（收敛前已 grep 确认全仓零
  模块外调用方）；`stable_key_for` / `build_store_projection` /
  `merge_projection_into_store_rows` 改薄转发框架层，spec 取 `SPEC_D103`；清理
  `Iterator` / `FieldSpec` 两个随之失效的 import。
  🔴 **循环 import 的处置**：`phase5_d1_03_customer` 在模块级 import 本模块（它的几何数字
  全从本模块冻结常量引用），故本模块**不能**模块级 import 它 ⇒ 新增 `_spec_d103()` 延迟
  取值（函数内 import，与引擎 import 同款写法）。D5/D6/D7 不需要这层是因为它们的 SPEC
  声明在自己模块内。
  🔴 **本家收敛一开始就带错误转译**，不重犯 Task 16/17 的 4xx→500 回归（见任务 16b/17b）：
  `build_store_projection` 用 try/except 把引擎的 `RowTableStorePayloadError` 转译回本家
  `StorePayloadError`，实测保住 `error_code='sync_phase5_store_payload_invalid'`。
  🔴 **既存判据按其自身指示改造**：`test_row_table_engine_core_equivalence.
  test_fail_closed_behaviours_match` 尾部原有一条防空转断言，文案自写「D1 尚未声明化…若它也
  收敛了，本判据需改为纯引擎断言」。按指示改造但**不退化成只测引擎**：对照面从「私有
  helper」上移到「provider 公开门面 `build_store_projection`」（生产真正调用那层），断言它
  对同三种畸形载荷仍 fail-closed 且抛 domain 错误 —— 该改造当即**抓出 D3 未修的同源回归**，
  已用 `xfail(strict=True)` 钉住待 D3 lane 修。
  零回归：golden digest 75 个逐个不变 + 146 用例全绿（2 xfailed 均为 D3 已登记缺口）+
  D4 整册真栈闭环复跑仍 `equivalent=True`。
  🔴 **未完成**：剩余 983 行主要是契约装配（`_rows_table_payload` / `build_contract_payload`）
  与发布编排（`publish_definitions` / `attach_adapters` / `build_registration` 等），
  它们是**生产入口**（registry 按名调用）、且 golden digest 不覆盖其行为 ⇒ 迁移需另立
  批次并先补发布链判据，本轮不动。
  - 拆出 `phase5_d1_03_customer.py`（现受管 sheet D1-3 的 spec 声明）
  - 循环层只留 `ENTRY_ID` / `TEMPLATE_RELATIVE_PATH` / sheet 清单 / 开关 / 薄转发（≤3 行/个）
  - 门：24 digest 零变化 + D1 真 materialize/extract 往返 `managed_field_count` 不变
  - _Requirements: 2.1, 2.2, 2.3, 4.2, 4.3_

- [ ]* 16. D3 / D6 / D7 声明化（三家同批，nested + flat 两形态各有代表）（**引擎函数层已完成，
  ≤150 行上限未达成**）✅ 2026-09-26：三家各新增 `SPEC_D{32,62,72}` 唯一权威声明；删 9 个
  引擎函数（`_aging_field_specs`/`stable_key_for`/`store_row_identity`/`iter_store_rows`/
  `_resolve_json_path`/`split_store_row`/`build_store_projection`/`_set_json_path`/
  `merge_projection_into_store_rows`）改薄转发框架层同名函数；`MANAGED_FIELD_SPECS`/
  `FORMULA_MASK` 值从 spec 派生、常量名不变。golden digest 零回归（26 个，含并发新增 E1）+
  既存 `test_ghost_row_defense.py` 16 用例零回归 + 4 条新判据 + Property 4 变异反证
  （aging_layout 错配 fail-closed）。
  🔴 **复盘补**：D5/D6 幽灵行防护锚点非默认第 0 位（D6=`seq_no` 整数 0 是合法值，D5=`category`
  枚举），框架层原硬编码 `specs[0][4]` 无法表达 ⇒ 新增 `RowTableSheetSpec.ghost_row_anchor_index`
  参数（默认 0 向后兼容，D6 声明 1）。详见 `docs/operations/evidence/d567-sync-coverage/
  retrospective-2026-09-26-part3.md`。
  🔴 **未完成**：三家仍 869~878 行（原 973/975/971，各减约 100 行），远超 ≤150 上限——本轮只
  收敛引擎函数层，`_rows_table_payload`（契约装配）/ `publish_definitions` / `attach_adapters`
  等发布编排代码尚未拆分/精简，真正达标需求 2.1 的完整收敛留后续
  - D3/D7 nested、D6 flat —— 这三家同批是为了让 P4 的两分支在同一 commit 内对照
  - _Requirements: 2.1, 2.2, 4.2_

- [ ]* 17. D5 声明化（7 元组的来源家，group_header 内联口径的基准）（**引擎函数层已完成，
  ≤150 行上限未达成**）✅ 2026-09-26：新增 `SPEC_D52` 唯一权威声明（`field_specs` 直接引用
  原 `MANAGED_FIELD_SPECS`，无账龄 `aging_layout=None`）；删 6 个引擎函数改薄转发；补齐
  D5 原自带的 `_col_index`（Task 5 当时未覆盖 D5，本次一并收敛，死别名已清理）。
  **零改动对照验证通过**：`managed_field_specs(SPEC_D52) == MANAGED_FIELD_SPECS` 逐字节相等
  （design 明文"若它的 digest 变了说明引擎理解错了"）。golden digest 零回归（26 个）+ 既存
  `test_ghost_row_defense.py` 2 用例零回归 + 新增 3 条判据 + 变异反证（少一列 formula_columns
  ⇒ 契约装配层一致性校验 fail-closed，"formula 字段必须被只读区域覆盖"）。
  🔴 **复盘确认**：D5 与 D6 同款幽灵行防护例外（`[0]`=`category` 枚举，`[1]`=`item_name`
  才是真名称），复用 Task 16 新增的 `ghost_row_anchor_index=1`。
  🔴 **未完成**：`_rows_table_payload`/发布编排代码仍在（911→810 行，同 D3/D6/D7 幅度）
  - D5 原本就是内联 7 元组 ⇒ 它是裁决 3 的**零改动对照**，若它 digest 变了说明引擎理解错了
  - _Requirements: 2.1, 2.2, 4.2_

- [ ] 18. D2 声明化（≤300 行，39 列 × 三套账龄）
  - `pilot_` 前缀函数保留为别名（裁决 6），不改名不 grep 调用方
  - 🔴 D2 是分母里最大的表（28431 字段 / 1260 行 / 906KB）⇒ 本任务后必跑一次
    真 materialize 并记录耗时，与任务 4 基线对比
  - _Requirements: 2.1, 2.2, 4.2, 8.1_

- [x] 19. B60 / D4 过门（不声明化，只验证兼容）✅ 2026-09-26：**真栈段首次跑通**（此前
  三次尝试均评估为"需完整环境、超出范围"而搁置，本轮找到可行路径）。
  ① digest 子集零变化：golden digest 门禁现测 **75 个逐个不变**，B60/D4 均在其中且 per-sheet
  粒度（B60 `store_projection_sha256=null` 如实记录不假造；D4 35 个 per-sheet digest）。
  ② D4 整册真栈 materialize + extract + verify **全绿**（真库 generation=164 真实数据，
  `project_id=0ec33ac9…` / `wp_id=b3ab3c46…`）：`materialize 5.7s + extract 1.8s +
  verify 4.9s = 12.4s`，`verify equivalent=True`，四次连跑稳定复现、退出码 0。
  受管 sheet 数**现算实测 30**（36 个 instrumentation spec 去重 `managed_sheet` 得 30，
  差值 6 正是 Task 24 参数化覆盖的 5 张同 sheet 多区底稿）——与本任务描述逐字相符。
  🔴 **两条走对了才有意义的路**（已固化进脚本 docstring）：必须走**隔离式 attach**
  （共享 `register_from_manifest()` 会在轮到 D4 之前先炸在 D2 lane 在途的
  `ContractDriftError`）；`before` 必须用**真实 substrate 字节**而非
  `read_authoritative_template()`（164 代演化后模板与 representation 间有大量合法结构差异，
  拿模板当 before 会把合法历史变化判成 drift）。
  🔴 **如实登记三项限制**：本次 `row_shift=None` ⇒ **未**走通"多区插行→兄弟区 ref 位移"
  路径（那条仍由离线 `test_sibling_table_ref_row_shift.py` 16 用例守）；extract 38 表 vs
  projection 43 表的差值 5 是 HTML-only/dict-store item（设计内，非丢数据）；12.4s 远低于
  历史注释值（42.8s/60.8s）是因走了单趟路径 + 缓存命中，**不得**据此断言性能问题已解决。
  脚本：`backend/scripts/e2e/verify_d4_full_book_real_stack.py`（正式工具，需真库、
  不需真后端进程，刻意不进 CI test 列表）。证据：`evidence/task19-b60-d4-gate.md`。
  - B60 是 simple_checklist、D4 有 26 个 per-sheet 模块 ⇒ 本 spec **不重构它们**（裁决/范围）
  - 只断言：它们的 24 digest 子集零变化 + D4 整册真 materialize 200 + verify 全绿（30 受管 sheet）
  - _Requirements: 2.5, 4.2, 4.3_

- [x] 16b/17b. 🔴 **Task 16/17 收敛遗留回归修复：畸形 store 载荷从 4xx 退化成 opaque 500**
  ✅ 2026-09-26（复盘自查发现，非外部报告）
  - **根因**：Task 16/17 把 D3/D5/D6/D7 的 `build_store_projection` 收敛成薄转发框架层，
    但**漏做错误转译**。框架层 `RowTableStorePayloadError(Exception)` 是**有意**设计成非
    domain 错误的（其 docstring 原文：「各循环 provider 有自己的 `StorePayloadError
    (SyncDomainError)` 子类…引擎抛本类，provider 侧薄转发时按需转译」），而收敛前各 provider
    抛带 `error_code` 的 domain 错误 ⇒ `wp_sync_router` 映射 **4xx**。收敛后直接冒泡 ⇒ **500**。
  - **实测确认四家全中**（四种用户侧真能写出的畸形载荷：非数组 / 非法 JSON / 元素非对象 /
    缺行身份）：D1（未收敛）稳定 4xx 带 `sync_phase5_store_payload_invalid`；
    D3/D5/D6/D7（已收敛）全部 `RowTableStorePayloadError` + `error_code=None` ⇒ 500。
  - 🔴 **golden digest 门禁抓不到这类回归**：它只对三段**成功路径**产物取 sha256，
    失败路径的错误分类不在其中 —— 这是「零回归门绿 ≠ 无回归」的一个实证样本，
    已写进判据 docstring 作为长期提醒。
  - **已修 D5/D6/D7**（各自 try/except 转译回本家 `StorePayloadError`，**保住各家不同的
    `error_code`**：`sync_phase5_d5/d6/d7_store_payload_invalid`）。
  - 🟡 **D3 未修**：`phase5_d3_prepaid_receipts.py` 正被 `d3-sync-coverage-via-row-table-engine`
    并发会话改动中，本轮不介入以免冲突；修法与 D5/D6/D7 逐字相同。已用
    **`xfail(strict=True)`** 钉住：D3 lane 修好后该条会 XPASS 而**红**，强制删标记 + 并入
    正式参数化清单，不留永久假绿。
  - 判据：`backend/tests/workpaper_sync/test_store_payload_error_stays_domain_error.py`
    （18 passed + 1 xfailed；含「各家 error_code 互不相同」与**反面钉子**「框架层错误类
    应当保持非 domain」——防止将来有人图省事把它改成 domain 子类而废掉转译约定）。
  - 零回归：golden digest 75 个逐个不变 + `test_ghost_row_defense` / 引擎等价判据 62 用例全绿。
  - _Requirements: 4.2_

### 阶段 4：CI 门禁

- [x] 20. `check_framework_layer_has_no_wp_code_branch.py` ✅ 2026-09-26：**P9 完全转绿**
  （先打红 17 处 → 现 0 处，扫 6 个框架层模块）。自测 6 用例全绿，含注入变异反证
  （构造含 `adapter_id == 'd1.…'` 与 `hasattr(…, "STORE_ITEM_ID_*_DICT")` 的样例源 ⇒ 必被检出）
  - 任务 2 的 P9 SHALL 转绿；白名单（注册表模块本身 / 错误消息文案）显式登记
  - 变异：在框架层加一个 `if adapter_id == "d1.…"` ⇒ 必红
  - 🔴 **逐项核实过「不是假绿」**：`hasattr(bridge` 在 oo_to_html 仍有 3 处，但它们是
    `hasattr(bridge, "merge_d45_fixed_from_projection")` 式**函数存在性探测**（provider 可能
    不提供某专用门面，属合理防御），不是需求 3.2 要消除的 `STORE_ITEM_ID_*_DICT` per-adapter
    试探。自测另立一条**反面钉子**断言函数探测**应当**存在，防止将来有人把判据「加严」到
    连它也报、误红后被整体关掉
  - _Requirements: 7.1, 7.4_

- [x] 21. `check_sheet_specs_fully_registered.py` ✅ 2026-09-26：**P10 完全转绿**
  （`registry_module_missing` → 11 个 adapter 已注册，含 E1）。自测 6 用例含变异反证
  （剔掉 d1 ⇒ 必报漏项）+ per-item default 规则断言（rows→`[]` / dict→`{}` / fixed_text→`''`）
  + 未命中抛错含已注册清单 + dedicated 缺 merge_fn 必抛
  - 任务 3 的 P10 SHALL 转绿；新声明一个 SPEC 不接注册表 ⇒ 必红并精确报漏项
  - _Requirements: 7.2, 7.4_

- [x] 22. 两方向 store item 集合相等卡点 + 接入 `governance-checks.yml` ✅ 2026-09-26：
  新增两个 CI job（YAML 已 `yaml.safe_load` 验证，全库 177 job）：
  * **`row-table-engine-and-registry-guards`**（10 steps）—— 四道卡点 + 四道自测（含变异反证）
    + 引擎/声明层等价判据 6 个测试文件
  * **`e1-sync-coverage-guards`**（5 steps）—— E1 canary 声明层三个测试文件
  两个 job 都**不**依赖 `tests/workpaper_sync/` 既存失败分母（脚本 stdlib-only、可独立归因）
  - 三个卡点（20/21/22）全部进 CI，**不**依赖 `tests/workpaper_sync/` 既存失败分母
  - _Requirements: 7.3, 7.5_

### 阶段 5：D1 批次 1（首次多受管 sheet）

- [x] 23. D1 provider 新增 `instrumentation_specs()`（复数）+ 灰度开关骨架 ✅
  `phase5_d1_expansion.py`（含 `all_store_item_ids()` / `assert_specs_align_with_contract_sheets`
  对齐守卫），3 个 `_INCLUDE_*` 开关全 False = 与现状等价，实测零回归
  - 照 D4 实测的 `_INCLUDE_*: Final[bool]` 模式（现 18 个全 True）
  - attach 走任务 10 的 `attach_sibling_bindings(provider=…)`，**不新写对齐规则**
  - 对齐计数守卫：specs 数 ≠ 契约 sheets 数 ⇒ fail-closed 并精确报差集
    （D4-35 事故：specs 7 vs sheets 8 打挂整个 entry）
  - _Requirements: 5.3, 5.2_

- [x] 24. `test_sibling_table_ref_row_shift.py` 的参数化判据改按 provider 取清单 ✅ 2026-09-26：
  `_multi_region_sheets()` 从硬编码 `D4.instrumentation_specs()` 改为遍历 golden digest
  `PROVIDERS` 权威登记（单一来源，不新建注册表）+ 已知伴生扩容模块清单（D1/D3），逐 provider
  重建对应模板的 instrumented workbook（新增 `_instrumented_bytes_for_provider`，不再复用
  D4 专属的模块级 `instrumented` fixture）。判据 7（单区代表性断言）**刻意不参数化**
  ——需求 5.4 原文只要求判据 6（多区位移）自动覆盖新 provider，判据 7 只需一张 D4 代表即可
  证明"未受影响 sheet 不回归"，扩大它反而稀释了"D4 多数是单区"这条结构性事实的原意。
  🔴 **实施中抓到一个真实聚合 bug**：起初同时取 entry 自身单数声明 + 伴生扩容模块复数声明并
  concat，导致 D1-3 被计入两次、误判成"跟自己形成同 sheet 双区"（`GT_D13_ROWS` vs 自己）。
  根因是 `phase5_d1_expansion.instrumentation_specs()` 文档已明确它是**完整超集**（"D1-3
  恒在（已交付）；其余按开关加入"），不是"entry 自身之外的增量"——改为有伴生模块时**只取**
  伴生模块复数（不再叠加 entry 单数），零回归后确认。
  **变异反证已验证**（新增 `test_mutation_hardcoded_d4_only_would_miss_newly_gated_d1_sheet`）：
  运行时翻转 `phase5_d1_expansion._INCLUDE_D104_BAD_DEBT=True`（不改磁盘文件）后，参数化函数
  自动发现 `坏账准备明细表D1-4` 进入 `_MULTI`（2 区），而模拟的旧硬编码单一 D4 写法在同一
  开关状态下看不到它——证明本次改动真实解除了"D1-4 三区接入后位移判据不自动覆盖"的缺口
  （D1 spec Task 26 的前置依赖）。16 用例全绿（原 15 + 新增变异反证 1）+ golden digest 26 个
  零回归 + P9/P10/O(1) 三门禁复测全绿。
  - _Requirements: 5.4_

- [ ]* 25. 接入 D1-2 `原值明细表（按类别）D1-2`（**声明已交付，灰度未开**：`phase5_d1_02_category.py`
  含 openpyxl 实测几何 + 5 用例判据全绿；`_INCLUDE_D102_CATEGORY=False`，真实接入/整册 materialize
  验收未做）
  - `phase5_d1_02_category.py` 声明（固定 2 行 + 动态行；派生列
    `currentUnadjusted = priorAudited + increase − decrease`）
  - 🔴 派生列声明 `mode=formula`，公式文本以 xlsx 为准、materialize 不覆盖公式格由 OO 重算
    （D1-3 契约已立此纪律：前端算式与 xlsx 公式数值等价但**以 xlsx 为准**）
  - 门：整册 materialize 200 + verify 全绿 + **受管区 1→2** + 实测耗时登记
  - _Requirements: 5.1, 5.2, 5.5_

- [ ]* 26. 接入 D1-4 `坏账准备明细表D1-4`（**三区**，D1 首次同 sheet 多区）（**声明已交付，
  灰度未开**：`phase5_d1_04_bad_debt.py` 三区正确处理 UUID 列不冲突 + 第三区 static_region +
  第三写入方定序登记，9 用例判据全绿；`_INCLUDE_D104_BAD_DEBT`/`_INCLUDE_D104_NOTETYPE_STATIC`
  全 False，真实接入/位移链实证未做）
  - 三个 spec：`D1-bd-individual-rows` / `-portfolio-rows` / `-notetype-rows`
  - 第三区（按票据种类小计 R23/R24）是专门喂 D1-1 坏账区块的，与前两区是**不同维度**
    （前两区按计提方法、第三区按票据种类），不得合并
  - 🔴 **三键有下游消费方，零回归必须覆盖**（复盘补）：`useD1EclCalc.d1_4DataAvailable`(:475) 与
    `parseD1_4Rows`(:497/:499) / `useD1Adjudication` 坏账区（`d1AdjudicationModel.readD1BadDebtByNoteType`）
    / `D1TabIndex.vue:49` 的 `progressKeys`。只验 D1-4 自身读回等值会放过「下游看不到回写」
  - 🔴 **D1-4 接 sync 后会有第三个写入方**（复盘补，P17）：除 HTML 保存与 OO 回写之外，
    `useD1WriteoffCheck.syncReversalToD14` 会**回写** `D1-bd-portfolio-rows` 的「按组合计提」
    父行（其注释写明「D1-4 的期末未审随之重算，并沿 D1-4 → D1-1 → 披露 → 附注 逐级联动」）。
    三方写同一 store 键必须定序，见任务 26b
  - **本任务含两个必须一起过的子目标**（复盘拆出，不单列任务以免全量重编号）：
    * ① 三区接入本体（三个 spec 声明 + 同 sheet 位移链实证 + 下游 computed 零回归）
    * ② **第三写入方定序**：`syncReversalToD14` 在 OO 模式下若被触发会绕过 sync 的 CAS 直接改
      store ⇒ 与 materialize 产物分叉（下次 extract 反读到非预期值 ⇒ roundtrip 门红或静默覆盖
      OO 改动）。裁决方向（任务内定，需实测确认）：OO 模式期间**禁用**该入口并给中文原因，
      或把回写改走 sync 的 pending-mutations 通道 —— **不得**两条路同时直写。
      P17 判据：OO 模式下触发它 ⇒ 要么被拒绝且有可见原因，要么经 sync 通道落地，不得静默直写
  - 🔴 触类旁通已 grep：D2 侧同型但**无此冲突** ——
    `useD2WriteoffCheck.reversalConsistencyWarning`(:135-137) 只**读** D2-3 三键不回写（仅告警）
    ⇒ D1-4 是全仓唯一「接 sync 的 store 键同时被另一 sheet 回写」的情形。该结论登记在
    D2 spec 需求 1.7
  - 门：P11（整册 materialize 200 + verify 全绿）+ P12（自动进位移判据清单）+ P17 + P18 +
    **受管区 2→5** + 耗时登记
  - _Requirements: 5.1, 5.4, 5.5, 5.7, 5.8_

### 阶段 6：D1 批次 2~3

- [ ] 27. 接入 D1-8（双区）+ D1-16（双区）；**D1-5 先做可行性核再裁决**
  ✅ **D1-5 可行性核子目标已完成**（2026-09-26）：裁决 **`single_html`**，维持默认倾向，
  四条判据逐条独立实证（未偷懒类推 D4-4）。openpyxl 直读 `调整分录汇总表D1-5`（A1:J25，
  表头行 5 十列 A-J，数据区 6-20 **逐格实测零内容零公式**，行 21 使用提示）：
  ① **零行身份列**（全表扫 GTROW/_GT/UUID 零命中）+ **零 definedName**（连 static_region
  锚点也没有）；② `D1-entry-rows` 是 hub —— `useD1Adjustment` 拥有，`D1TabAdjustment.vue`
  接 `useAdjustmentCentralSync` 2 个接线点（`wpCode:'D1'`/`itemId:'D1-entry-rows'` →
  后端幂等 by `source_ref={wpId}:{itemId}`），`D1TabIndex.vue:50` progressKeys 也读它；
  ③ 借贷平衡 `BALANCE_TOLERANCE=0.005` + 「同步到集中登记」按钮以 `!isBalanced` 为门，
  **仅 HTML 侧强制**（Excel 数据区零公式）；④ 列 F『……』是排版占位。
  🔴 **实测发现 D1-5 与已判 single_html 的 D4-4 是同一套模板范式**（十列表头与
  `T08-d44-single-html-adjudication.json` 的 `header_A_to_J` **逐字完全相同**，同为表头行 5
  + 数据区 6-20 空带 + 行 21 提示，仅整表行数 25 vs 23 不同）。
  🔴 **改判条件两条都不成立**（tasks.md 定的是「有行身份列 **且** 无同步链冲突」）⇒ 不改判、
  不另起接入任务；受管区计数不变（门已写明 D1-5 不计）。
  裁决证据：`evidence/task27-d1-5-single-html-adjudication.json`；防腐判据：
  `backend/tests/workpaper_sync/test_d1_05_single_html_adjudication.py`（10 用例，把四条依据
  钉成测试，含 D1-3 有 `uuid_col` 的反面对照证明身份列扫描真能区分）。
  🔴 **本子目标不等于 Task 27 完成**：同任务的 D1-8（双区）/ D1-16（双区）**接入本体未做**
  （需灰度开关 + 整册 materialize/verify 门 + 受管区 5→9），复选框保持未勾。
  - D1-8：`D1-endorse-discount-rows` / `-transfer-rows`；D1-16：`-reversal-rows` / `-writeoff-rows`
  - 🔴 **D1-5 从接入改为可行性核**（复盘修正，首版误排直接接入）：它与上游 spec
    `d-cycle-sheet-bidirectional-expansion` 已判 `single_html` 的 D4-4 同型 —— 实证
    `D1TabAdjustment.vue` 接了 `useAdjustmentCentralSync`（2 处）、`useD1Adjustment` 的
    `BALANCE_TOLERANCE=0.005` 借贷平衡**仅 HTML 侧强制**（Excel 不校验）、`D1-entry-rows` 是
    hub store。本任务只产出**裁决 + 证据 JSON**（照 `T08-d44-single-html-adjudication.json`
    范式），默认倾向 `single_html`；若核出「有行身份列 + 无同步链冲突」才可改判并另起接入任务
  - 门：整册 materialize + verify + 耗时登记（**受管区 5→9**：D1-8 +2 / D1-16 +2；D1-5 不计）
  - _Requirements: 5.1, 5.4, 5.5, 5.9, 5.10_

- [ ] 28. 接入 D1-9 / D1-10 / D1-11 / D1-12 / D1-15 ✅ **声明层全部交付**（2026-09-26）
  - `phase5_d1_09_interest.py`：单区 R11-17，**D1 首例数据区行级公式**（H=E-G / J=I/365*H*B /
    L=J-K）声明为 formula，13 列 A-M，UUID=N，store `D1-interest-rows`，`rowId`
  - `phase5_d1_10_inventory.py`：单区 R14-20（监盘表），15 列 A-O，UUID=P，store
    `D1-inventory-rows`，`id`。🔴 倒轧表 R24-R25 全为公式格（零可编辑格）不受管；核对区
    3 个标量文本键由 HTML 侧处理。🔴 前端 InventoryCountRow 列注释是 UI 展示顺序非 Excel
    列字母（"收到日期"前端 C 位但模板 I 位），field_specs 按 openpyxl R13 逐字匹配
  - `phase5_d1_11_related_party.py`：单区 R11-13，行级公式 F=C+D-E / H=F-G，13 列，UUID=N，
    store `D1-rp-rows`，`id`
  - `phase5_d1_12_pledge.py`：单区 R12-17，无数据区公式，16 列 A-P，UUID=Q，store
    `D1-pledge-rows`，`id`
  - `phase5_d1_15_ecl.py`：**双区**（单项 R14-17 / 组合 R22-24），**乘法公式** D=B*C +
    E=B-D + F=D-E（引擎首次非加减派生，`mode=formula` 路径确认不依赖算式形态），8 列 A-H，
    UUID=I/J，store `D1-ecl-individual-rows`/`D1-ecl-portfolio-rows`，`id`。footer marker
    是「小计」（非「合计」）。`autoPulled` 不进 field_specs（UI 提示字段不映射 Excel 列）
  - 全部 7 个新开关灰度关（`_INCLUDE_D109/D110/D111/D112/D115`=False），开关 off 输出不变，
    开关 all-on 正确产出 11 specs / 11 items。golden digest 73 零回归 + P9/P10 绿
  - D1-10 带 3 个 recon 标量伴生（`StoreKind.fixed_text`）
  - 🔴 **D1-15 是双区**（复盘修正）：`D1-ecl-individual-rows` / `D1-ecl-portfolio-rows`
    （实测 `useD1EclCalc.ts:208-209` 的 dict 形式），首版按单区写 ⇒ 另一键的数据在 OO 里会
    不可见、回写丢失
  - D1-15 派生列是**乘法**（`shouldProvision = 余额 × 损失率`）与 `difference = E − D` ——
    引擎首次遇到非加减派生，确认 `mode=formula` 路径不依赖算式形态
  - D1-15 的 `autoPulled: boolean` 归一到 `source='tb'`（P16）；其取数源是 D1-4 ⇒ P18 的下游
    联动判据须覆盖「D1-4 三区被 OO 回写后 D1-15 的 `parseD1_4Rows` 仍正确重算」
  - 门：同上（**受管区 9→15**：D1-9/10/11/12 各 +1，D1-15 **+2**）
  - _Requirements: 5.1, 5.5, 5.8, 6.5_

### 阶段 7：D1 批次 4~5

- [ ] 29. 接入 D1-7（嵌套 dict）+ D1-14（**static_region 候选**）+ D1-13（双区 + 标量）
  ✅ **声明层全部交付**（2026-09-26）：
  - `phase5_d1_07_memo.py`：**D1 唯一 `StoreKind.dict` 形态**（`{bankRows, commercialRows}` 嵌套
    双数组），双区银行承兑 R13-17 / 商业承兑 R19-23，31 列宽表，UUID=Y/Z，provider 专用
    `build_d17_store_projection`/`merge_projection_into_d17_store` + `DedicatedStoreItem` 注册
    在 `STORE_MERGE_REGISTRY["d1.notes_receivable_detail"]`（参照 D4-9 已验证路径）。框架层
    通用 `build_store_projection`/`merge_projection_into_store_rows` 严格要求顶层 list，dict
    载荷直接抛 `RowTableStorePayloadError` ⇒ 必须 provider 专用路径。
  - `phase5_d1_13_sampling.py`：双区增减变动 R16-31（16 行）+ 期后检查 R37-44（8 行），17 列
    宽表 A-Q，UUID=R/S，两级表头。模板5列"核对内容1-5"vs前端3个语义字段按模板实际声明。
  - `phase5_d1_14_policy.py`：`NOT_EXPRESSIBLE`——openpyxl 实测确认是**纯文本段落**（无表头/
    无数据区/无 footer/无绝对坐标标量格），tasks.md 原描述「10 个标量 static_region 候选」
    **不准确**（static_region 要求绝对坐标锚点，D1-14 连映射目标格都没有）。现状维持 HTML-only。
  - 🔴 **D1-14 实测纠正了设计阶段的误判**：不是"10 个标量该走 static_region 还是 HTML-only"
    的问题，而是"它根本不是标量"——它是无结构的纯文本段落区，Excel 侧无几何可表达。
  - _Requirements: 5.1, 5.5, 11.4, 11.5, 11.6_

- [x] 30.* 评估 D1-6 能否用 `TransposedSheetSpec` 表达 ✅ 2026-09-26：**两条路径都表达不了**
  （比设计阶段猜想更严——不仅 `TransposedSheetSpec` 不匹配，深入核实后发现 `static_region`
  也不行，方向性初判已修正）。openpyxl 直读确认矩阵绝对坐标 `B17:D20`（4 行×3 列，行 21/22
  是硬编码引用矩阵的派生公式行，前端 `computed()` 同构不需单独管理）。
  `TransposedSheetSpec`：动态多实体+异构字段类型假设（D4-12 先例：N 份合同列可扩列），
  与 D1-6 固定 3×4 同类型枚举网格不匹配。`static_region`：深读 `contracts.py:_parse_field`
  （第 908-934 行）发现 `cell.row_from` 只收 `"row_identity"` 或单个 `int>=1`，**无「行区间」
  表达**——字段粒度恒为单格，排查全部现存先例（E1-11/D1-4 第三区）均为散列单格集合，
  本引擎从未处理过矩阵形态。按需求 5.6 登记
  `phase5_d1_06_business_mode.QA_MATRIX_NO_ROW_RANGE_CELL_MAPPING_NOT_EXPRESSIBLE`
  （同 `pilot_h1` 范式，点名两条候选路径的具体约束来源+修法路径+owner），**未在框架层开
  特例分支**（本模块只登记评估结论，不声明 `RowTableSheetSpec`/`TransposedSheetSpec`）。
  9 用例判据全绿（矩阵几何实测 3 + schema 约束实证 2 + D4-12 对照 1 + 登记文案校验 3）。
  证据：`.kiro/specs/d1-sync-row-table-engine-and-d1-coverage/evidence/
  task30-d1-6-feasibility.md`。`D1-bm-basis-rows`（3 固定行）不受影响，接入路径由后续
  批次任务决定，本任务不涉及。
  - D1-6 = 行表（`D1-bm-basis-rows` 3 固定行）+ **真二维矩阵**（`cells: QACell[][]` 4×3）
  - 矩阵部分形似转置表（一列一组合、一行一问题）⇒ 试 `header_field_key=None` /
    `nested_fields_key=None`（与 D4-12 同形）
  - IF 表达不了 THEN 按需求 5.6 显式登记原因（照 `pilot_h1.UPSTREAM_DEBT_…NOT_EXPRESSIBLE`
    范式），**不得**在框架层开特例分支
  - _Requirements: 5.6_

### 阶段 8：D1 批次 6 —— 审定表 D1-1 迁移

- [x]* 31. `AdjudicationSheetSpec` + D1-1 逐格 mask 声明 ✅ 2026-09-26：框架层类型（此前交付）
  + **D1-1 具体实例声明已交付**（`phase5_d1_01_adjudication.py`）。
  三区（gross R8-9 / bd R12-13 / net R16-17）+ `row_mode=fixed_rows`（银行承兑/商业承兑固定行）。
  88 个逐格 mask（审定列 E/I 全数据行 + 小计/footer 行全列 + 跨 sheet 公式格 + 净值区全格）。
  B-K 列全声明 `formula`（几乎每格都是公式或跨 sheet 引用），仅 A（项目名）/L（原因分析）
  为 `editable`。`assert_data_cells_not_masked` 自检通过（零 editable 数据格入 mask）。
  `value_sources` 声明每列来源：B-H 大部分 `cross_sheet`，D/H 坏账区 `manual`（重分类调整
  是唯一可手工编辑的金额字段），E/I/J/K `computed`。
  🔴 **附注披露（上市/国企）也一并评估**：`phase5_d1_disclosure.py` 登记
  `DISCLOSURE_MIXED_LAYOUT_NOT_EXPRESSIBLE`——混合布局（多个独立小表各有不同列数 + 提示文字
  交错），现有三种框架类型都无法整张覆盖，接入路径需先模板改造（为每个可编辑小表建
  Excel Table），属模板侧工作不在本 spec 范围。
  🔴 **D1A 程序表确认不需双向回写**（用户 2026-09-26 明确）。
  🔴 **至此 D1 全 21 张 sheet 声明层/评估全部封顶**（16 声明 + 5 裁决/评估：D1-5 single_html /
  D1-6 NOT_EXPRESSIBLE / D1-14 NOT_EXPRESSIBLE / 附注×2 NOT_EXPRESSIBLE）。
  🔴 Task 32（存量迁移）和 Task 33（四态状态机）仍是后续依赖任务。

- [ ] 32. D1-1 存量迁移：per-cell 锚点 → 行数组（双读单写）
  - 读侧行对象优先、缺则回落 `D1-adj-{section}-{slug}-{field}`；写侧只写新形态
  - P14 判据：**以真库存量形态的 payload 驱动**（不是合成理想数据），金额不归零
  - 旧键保持可读，物理删除归后续 spec（回滚只需改读侧优先级）
  - _Requirements: 6.1, 6.2_

- [ ] 33. D1-1 四态覆盖状态机接入（修静默丢数据）
  - 现状 `const g = fromCat ?? readD1AnchorAmounts(...)` —— cross-sheet 有值就无条件盖掉手工值，
    手工值不可达且无提示。这是静默丢数据，与 D4-1 修前同型
  - 复用 `shared/dynamicAdjudicationRows.resolveCellState` / `displayValueForCellState`，
    **不得**在 D1 侧另写一套
  - P15 判据（**反证式先写**）：只改 derived 不改 stored/snap ⇒ 覆盖标记数必须为 0
  - 🔴 必须有一条**跑同步器**的判据，不能只喂 `resolveCellState` 三个入参 ——
    D4 spec 有 13 条纯函数判据全绿而生产坏掉（同步器把显示值当派生值写回 snap ⇒
    覆盖标记自我擦除），本 spec 不重犯
  - _Requirements: 6.3, 6.4_

### 阶段 9：验收

- [ ] 34.* 变异检验 + 真栈 Playwright + 证据登记
  - P1~P16 逐条变异，记录打红条数；未能打红的判据重写而非保留
  - 真栈：D1 宿主切「在线编辑」→ 至少三张新接 sheet 的 OO canvas 逐值断言 → 改一格 →
    forcesave → 回读结构化视图等值。`--workers=1`
  - ⚠️ D1 的模式切换条选择器需实测确认（D4-1 是 `.d4-tab-adjudication .sync-mode-bar`、
    D4-2 是 `.d4-mode-toolbar` —— 照抄会找不到元素，D4 spec 已踩过）
  - 三端点耗时复测 ≤ 基线 110%（P13）
  - 证据落 `docs/operations/evidence/row-table-engine-d1-coverage/`，数字脚本现测不手抄
  - _Requirements: 8.1, 9.1, 9.2, 9.3, 9.4, 9.5_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置依赖入库核查必须先于一切 —— 若 _protection 格级判定未入 HEAD，批次 6 建立在一次 checkout 就会消失的工作树状态上" },
    { "wave": 1, "tasks": ["1", "2", "3", "4"], "rationale": "基线与红判据先行，四者互不依赖可并行；digest 基线此时必绿、P9/P10 此时必红是后续归因的唯一依据" },
    { "wave": 2, "tasks": ["5"], "rationale": "两个纯函数 helper 收敛是引擎其余部分的共同输入，且可穷举验证，风险最低故先行" },
    { "wave": 3, "tasks": ["6", "7"], "rationale": "spec 数据类与账龄形态互不依赖可并行；两者都只加新类型不改行为" },
    { "wave": 4, "tasks": ["8", "9"], "rationale": "字段组装与引擎核心都依赖 6/7 的类型；此时引擎无人调用故 digest 恒零变化" },
    { "wave": 5, "tasks": ["10"], "rationale": "sibling binding 泛化依赖引擎已有 spec 形态可传入" },
    { "wave": 6, "tasks": ["11", "12"], "rationale": "StoreItemSpec 与注册表是删 elif 链的前置" },
    { "wave": 7, "tasks": ["13", "14"], "rationale": "回方向改注册表与两方向清单同源，都依赖 11/12；二者可并行（改不同函数）" },
    { "wave": 8, "tasks": ["15"], "rationale": "D1 第一家声明化 —— 它同时是阶段 5 的前置，故排在其余五家之前单独一波" },
    { "wave": 9, "tasks": ["16", "17", "18", "19"], "rationale": "其余五家声明化互不依赖可并行；D5 是内联 7 元组的零改动对照，D2 附带性能实测" },
    { "wave": 10, "tasks": ["20", "21", "22"], "rationale": "CI 卡点要在框架层与注册表都成形后才有稳定形态可断言，否则守卫自身会红" },
    { "wave": 11, "tasks": ["23", "24"], "rationale": "多 sheet 骨架与位移判据参数化是 D1 铺量的共同前置" },
    { "wave": 12, "tasks": ["25"], "rationale": "D1-2 单区先行 —— 证明一 entry 多受管 sheet 在 D1 成立，失败面最小" },
    { "wave": 13, "tasks": ["26"], "rationale": "D1-4 三区依赖 25 已证多 sheet 通路；三区是 D1 首次同 sheet 多区。本条含两个子目标（三区接入 + 第三写入方定序）—— 定序必须与接入同波交付：在接入之前该冲突不存在，在接入之后若不定序则跨 sheet 回写会与 materialize 产物分叉" },
    { "wave": 14, "tasks": ["27", "28"], "rationale": "批次 2/3 结构同型，可并行；每条各自跑整册 materialize 与耗时登记" },
    { "wave": 15, "tasks": ["29", "30"], "rationale": "dict/fixed_text 形态与 D1-6 评估互不依赖；30 是评估任务可能产出「表达不了」结论" },
    { "wave": 16, "tasks": ["31"], "rationale": "AdjudicationSheetSpec 独立于行表引擎，但需 D1-2/D1-4 已接（它的行来源是这两张）" },
    { "wave": 17, "tasks": ["32"], "rationale": "存量迁移依赖 31 的 spec 形态；必须以真库存量 payload 驱动" },
    { "wave": 18, "tasks": ["33"], "rationale": "四态状态机依赖 32 的双读单写已落（否则 stored 这一量读不到）" },
    { "wave": 19, "tasks": ["34"], "rationale": "变异与真栈收口，需全部行为已落地" }
  ],
  "blocking": {
    "0": "_protection 格级判定未入 HEAD ⇒ 批次 6 的 D1-1 逐格 mask 会在 merge 侧被整列误判只读，四态 UI 重演「已实现但不可达」（需求 10.3）",
    "1": "digest 基线未取 ⇒ 阶段 1~3 的「零回归」无对照，等于没有门（需求 4.1）",
    "2": "P9 未先打红 ⇒ 任务 20 的转绿不可归因",
    "3": "P10 未先打红 ⇒ 任务 21 的转绿不可归因",
    "4": "性能基线未取 ⇒ 需求 8.1 的「不劣化 110%」无分母，任务 18/34 无从判定",
    "5": "_snake/_col_index 未收敛 ⇒ 任务 7/8 会各自 import 四份复制里的某一份，收敛不彻底",
    "6": "RowTableSheetSpec 未落 ⇒ 任务 8/9/10 无类型可依",
    "11": "per-item default 规则未落 ⇒ 任务 13 改注册表时会退回 blanket '[]'，重犯 opaque 500 事故",
    "12": "注册表未落 ⇒ 任务 13 无查表入口，只能保留 elif 链",
    "23": "instrumentation_specs() 与对齐计数守卫未落 ⇒ 任务 25 起每张接入都可能重演 D4-35 的 specs/sheets 不对齐打挂整个 entry",
    "24": "位移判据未参数化 ⇒ 任务 26 的三区 sheet 不被自动覆盖，回到「硬编码清单漏掉的那张就是下一个线上 500」",
    "26": "D1-4 是 D1 首次同 sheet 多区，且其三键有下游消费方（P18）与第三写入方（P17）⇒ 两个子目标必须同波交付；不先接它，批次 2 的双区 sheet 也缺通路验证",
    "32": "双读单写未落 ⇒ 任务 33 的四态状态机读不到 stored，只能退回被需求 6.3 禁止的「cross-sheet 无条件覆盖」"
  }
}
```

## Notes

### 已裁决（不再讨论，详见 design §关键裁决）

- **D1**：框架层零 wp_code 分支，AST 卡点守而非人工纪律
- **D2**：`attach_sibling_bindings` 泛化只去掉一行 import，**不重写**对齐规则
- **D3**：审定表不进行表引擎，另立 `AdjudicationSheetSpec`（三循环形态互不相同）
- **D4**：`rowType` + `source` 两维并存，`isFixed` 收敛掉
- **D5**：灰度开关逐张接入，不做大爆炸
- **D6**：零回归门用 digest，但 materialize 段必须真跑（穿过 `verify_unmanaged_regions`）

### D2 已独立立项 → `d2-sync-coverage-via-row-table-engine`

它是本 spec 的**消费方**（引擎 / 注册表 / `AdjudicationSheetSpec` / 四态状态机由本 spec 交付），
其 Task 0 的前置门就是「本 spec 的框架层已入 HEAD」。

**O5 已在 D2 spec 调研中查明结论**（不再待确认）：`useD2VoucherCheck`（旧套）**全仓零消费方**
= 死模块 310 行，前端实际挂载 `Enhanced`；真库旧键 `D2-voucher-params`(1 行 87B) /
`D2-voucher-samples`(1 行 332B) 内容为**空骨架/默认值**，新套 `D2-vc-current-rows`/`-post-rows`
**全库 0 行** ⇒ 裁决「删代码不删数据」（D2 spec 裁决 E4 / 任务 14）。
`useD2Adjudication:182-188` 死降级路径归 D2 spec 任务 15。

⚠️ **D2 spec 发现一条本 spec 未预料的结构事实**：D2 是**三册模板**，而 entry ↔ template blob
是 1:1（`_entry_id` 从宿主文件派生 + `seen_entry_ids` 碰撞检查 ⇒ 一宿主恰一 entry）⇒ D2 只能
覆盖第一册。本 spec 的「一循环一 entry」对 D2 需读作「**一册一 entry**」；D1（单册 21 sheet）与
D4（单册 46 sheet）不受影响。任务 18（D2 声明化）只涉及第一册那个已存在的 entry，范围不变。

### 不在本 spec 范围

见 design §不在本 spec 范围（D2 接入 / 性能优化 / D4 26 模块迁移 / 附注披露 / per-cell 物理删除 /
`excel_extract_identity_carrier_missing` 的 500→4xx）。
