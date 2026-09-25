# Implementation Plan

## Overview

**spec**：`workpaper-sync-row-table-engine-and-d1-coverage`　**创建**：2026-09-25　**状态**：0/35

顺序有意义：**阶段 0 是红判据与基线先行** —— 24 个 golden digest 此时必绿（它是基线不是判据），
P9/P10 此时必红（框架层现有 89 处 D4 提及、注册表尚不存在）。没有这两侧，后面"修好了"与
"判据本来不会红"区分不开。

**阶段 1→3 刻意分成"先抽引擎、再逐家切换"**：引擎落地时六家 provider 一行不动（引擎无人调用、
门恒绿），切换时一家一个 commit、一家过一次门。任一家切崩只回滚那一家。

**阶段 5 之后每批次都有一条整册 materialize 实测**（需求 8.3）：耗时超软上限就停下转性能 spec，
不带着退化继续铺量。

**受管区增长路线**（2026-09-25 复盘按值 grep 重算，首版按「一 sheet 一区」估的数字全部偏低）：
`1 → 2(D1-2) → 5(D1-4 三区) → 10(批次2) → 16(批次3，含 D1-15 双区) → 19(批次4，含 D1-13 双区)
→ 20~21(批次5) → 23~24(批次6 D1-1 三区)`。下方复选框为唯一进度真源。

## Tasks

### 阶段 0：基线与红判据先行

- [ ] 0. 前置依赖入库核查（**开工第一件事**）
  - 用 `git show HEAD:<path>` 判定（**不读工作树** —— 本 spec 调研期间正因读工作树而一度把
    `_protection` 登记成"已修复"）
  - 实测现状：`merge.py` 的 `_mask_spans_data_column` **HEAD 不含**、仍是只比列旧实现；
    判据 `test_masked_cell_protection_is_cell_level.py` 为 `??` 未跟踪
  - IF 未入库 THEN 批次 6（任务 31~33）阻塞；批次 1~5 不受影响可照常推进
    （明细类 mask 全为列向区间、行范围恰等于数据区 ⇒ 只比列与格级判定等价）
  - 同时核 `e2e/d4-*.spec.ts` / `errorEnvelopeNormalisation.spec.ts` 等被零回归门依赖的未提交产物
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [ ] 1. 24 个 golden digest 基线脚本
  - 对 8 个已交付 contract（b60 / d1 / d2 / d3 / d4 / d5 / d6 / d7）各取三个 canonical JSON sha256：
    `build_contract_payload()` / `build_store_projection(合成 payload)` / `instrumentation_spec(s)()`
  - 落 `backend/scripts/check/check_sync_provider_golden_digest.py`，digest 存同目录 JSON
  - D3/D5/D6 的 store item 真库 0 行 ⇒ 用**合成 payload** 驱动，不得跳过（需求 4.5）
  - 此时必绿；记录 24 个 digest 实测值
  - _Requirements: 4.1, 4.5_

- [ ] 2. P9 红判据：框架层 wp_code 分支扫描
  - AST 扫 `oo_to_html` / `merge` / `excel_extract` / `excel_materialize` / `adapters/excel` /
    `store_projection_response`，断言零 wp_code / contract_id / adapter_id 字面量分支
  - **现状必红**：记录实测命中数（预期 oo_to_html 89 提及 + 9 elif / excel_extract 8 / merge 5 /
    adapters-excel 2 / excel_materialize 1）
  - _Requirements: 7.1_

- [ ] 3. P10 红判据：spec 声明未接注册表必红
  - 照 `check_store_item_ids_fully_wired.py` 范式（已验证：46 item 收敛 + 变异反证）
  - 此时注册表尚不存在 ⇒ 判据以"注册表模块缺失"形态红，记录
  - _Requirements: 7.2, 7.4_

- [ ] 4. P13 性能基线：三端点同 substrate 实测耗时
  - 脚本现测 `store-projection` / `pending-mutations` / `materialize`，数字不手抄
  - 同时记录 `BASELINE_EXTRACT_CACHE` 二次请求命中情况（需求 8.4）
  - _Requirements: 8.1, 8.4_

### 阶段 1：框架层抽取（引擎落地，六家 provider 一行不动）

- [ ] 5. `sheet_geometry.py`：收敛 `_snake` / `_col_index` 四份复制
  - 从 D2/D3/D6/D7 抽出，逐家改为 import；**行为逐字节等价**（两个纯函数，可穷举验证）
  - 任务 1 的 24 digest SHALL 零变化
  - _Requirements: 1.4, 4.2_

- [ ] 6. `RowTableSheetSpec` 冻结数据类 + `formula_mask` property
  - 字段集严格按 design §Components（七家实测共性），不多加"将来可能用到"的字段
  - P2 判据：对七家各构一份 spec，`formula_mask` 输出 ≡ 原手写 mask 字面量**逐元素相等**
  - _Requirements: 1.1, 1.2_

- [ ] 7. `AgingLayout` + `AgingGroupSpec` + `_expand_aging_fields`
  - nested（D3/D7）/ flat（D6）两种 key 派生各自复刻原写法，引擎内**只剩一处 if**
  - P4 判据：把 flat 走 nested 派生 ⇒ D6 必红（变异反证先写）
  - _Requirements: 1.3_

- [ ] 8. `managed_field_specs(spec)`：取代四家逐字相同的 `sorted(...)`
  - P3 判据：对 D2/D3/D6/D7 四家，引擎输出 ≡ 原 `tuple(sorted(SCALAR + _aging(), key=_col_index))`
    **逐元组相等**（含顺序）
  - _Requirements: 1.3_

- [ ] 9. 行表引擎核心：`build_store_projection` / `merge_projection_into_store_rows` /
      `build_contract_payload` / `stable_key_for` / `iter_store_rows` / `split_store_row`
  - 33 个同名函数里属于行表域的那批，每个在框架层恰有一处实现
  - nested/flat 的 store 读写走收敛后的 `_resolve_json_path` / `_set_json_path`（原四份复制）
  - 引擎此时**无人调用**，24 digest 恒零变化（这是本阶段的安全性来源）
  - _Requirements: 1.1, 1.5, 2.3_

- [ ] 10. `attach_sibling_bindings(provider=…)` 泛化
  - 从 `phase5_d4_revenue_detail._attach_sibling_bindings`（:2666）提出，**函数体不动**，
    只把硬编码 `import … as _provider` 改成参数
  - 继续调已有框架内核 `_align_specs_to_sibling_tables` / `_static_region_bindings`，
    **不重写对齐规则**（publish 与 attach 共享，重写必漂移）
  - P8 判据：对 D4 产出的 binding 元组 ≡ 泛化前（逐字段相等，含顺序）
  - _Requirements: 1.5, 2.4_

### 阶段 2：注册表化（删 elif 链与 hasattr 试探）

- [ ] 11. `StoreKind` + `StoreItemSpec` + per-item default 规则
  - default 必须 per-item（rows→`[]` / dict→`{}` / fixed_text→`''`），**不得** blanket `"[]"`
  - 这条有事故背书：dict-store 拿列表默认会抛非 domain ValueError 冒泡成 opaque 500
    （`store_projection_response.py:207`）
  - _Requirements: 3.2_

- [ ] 12. `STORE_MERGE_REGISTRY` O(1) dict + `resolve_store_merge_plan`
  - 未命中抛 `StoreMergePlanNotRegisteredError`（含已注册清单），**禁止**静默 return
  - P6 变异：改成静默 return ⇒ 必红。P7 判据：规模递增的合成注册表，查表耗时不随规模上升
  - _Requirements: 3.4, 3.5, 8.2_

- [ ] 13. `oo_to_html._mirror_store_backed_if_needed` 改走注册表
  - 删那条 9 分支 `elif adapter_id ==` 链（b60/d1/d2/d3/d4/d5/d6/d7/g7/h1）
  - 删 9 处 `hasattr(bridge, "STORE_ITEM_ID_D4xx_DICT")` 试探，改 `StoreItemSpec.kind` 分派
  - 24 digest 零变化 + 8 contract 的 merge 输出逐字段等价
  - _Requirements: 3.1, 3.2, 4.2_

- [ ] 14. 出/回两方向 store item 清单同源
  - `store_projection_response` 与 `oo_to_html` 均取 `all_store_item_ids()`，删
    `STORE_ITEM_IDS_D45_FIXED` 等回退分支
  - P5 判据：两方向集合**逐元素相等**；变异删一个 item ⇒ 必红
  - _Requirements: 3.3_

### 阶段 3：六家 provider 声明化（一家一 commit，一家过一次门）

- [ ] 15. D1 声明化：`phase5_d1_notes_receivable` → ≤150 行
  - 拆出 `phase5_d1_03_customer.py`（现受管 sheet D1-3 的 spec 声明）
  - 循环层只留 `ENTRY_ID` / `TEMPLATE_RELATIVE_PATH` / sheet 清单 / 开关 / 薄转发（≤3 行/个）
  - 门：24 digest 零变化 + D1 真 materialize/extract 往返 `managed_field_count` 不变
  - _Requirements: 2.1, 2.2, 2.3, 4.2, 4.3_

- [ ] 16. D3 / D6 / D7 声明化（三家同批，nested + flat 两形态各有代表）
  - D3/D7 nested、D6 flat —— 这三家同批是为了让 P4 的两分支在同一 commit 内对照
  - 每家 ≤150 行；门同任务 15
  - _Requirements: 2.1, 2.2, 4.2_

- [ ] 17. D5 声明化（7 元组的来源家，group_header 内联口径的基准）
  - D5 原本就是内联 7 元组 ⇒ 它是裁决 3 的**零改动对照**，若它 digest 变了说明引擎理解错了
  - _Requirements: 2.1, 2.2, 4.2_

- [ ] 18. D2 声明化（≤300 行，39 列 × 三套账龄）
  - `pilot_` 前缀函数保留为别名（裁决 6），不改名不 grep 调用方
  - 🔴 D2 是分母里最大的表（28431 字段 / 1260 行 / 906KB）⇒ 本任务后必跑一次
    真 materialize 并记录耗时，与任务 4 基线对比
  - _Requirements: 2.1, 2.2, 4.2, 8.1_

- [ ] 19. B60 / D4 过门（不声明化，只验证兼容）
  - B60 是 simple_checklist、D4 有 26 个 per-sheet 模块 ⇒ 本 spec **不重构它们**（裁决/范围）
  - 只断言：它们的 24 digest 子集零变化 + D4 整册真 materialize 200 + verify 全绿（30 受管 sheet）
  - _Requirements: 2.5, 4.2, 4.3_

### 阶段 4：CI 门禁

- [ ] 20. `check_framework_layer_has_no_wp_code_branch.py`
  - 任务 2 的 P9 SHALL 转绿；白名单（注册表模块本身 / 错误消息文案）显式登记
  - 变异：在框架层加一个 `if adapter_id == "d1.…"` ⇒ 必红
  - _Requirements: 7.1, 7.4_

- [ ] 21. `check_sheet_specs_fully_registered.py`
  - 任务 3 的 P10 SHALL 转绿；新声明一个 SPEC 不接注册表 ⇒ 必红并精确报漏项
  - _Requirements: 7.2, 7.4_

- [ ] 22. 两方向 store item 集合相等卡点 + 接入 `governance-checks.yml`
  - 三个卡点（20/21/22）全部进 CI，**不**依赖 `tests/workpaper_sync/` 既存失败分母
  - _Requirements: 7.3, 7.5_

### 阶段 5：D1 批次 1（首次多受管 sheet）

- [ ] 23. D1 provider 新增 `instrumentation_specs()`（复数）+ 灰度开关骨架
  - 照 D4 实测的 `_INCLUDE_*: Final[bool]` 模式（现 18 个全 True）
  - attach 走任务 10 的 `attach_sibling_bindings(provider=…)`，**不新写对齐规则**
  - 对齐计数守卫：specs 数 ≠ 契约 sheets 数 ⇒ fail-closed 并精确报差集
    （D4-35 事故：specs 7 vs sheets 8 打挂整个 entry）
  - _Requirements: 5.3, 5.2_

- [ ] 24. `test_sibling_table_ref_row_shift.py` 的参数化判据改按 provider 取清单
  - 现状 `_multi_region_sheets()` 只从 D4 取 ⇒ 扩成 provider 参数化
  - P12 判据：D1 的多区 sheet 接入后**自动**进入覆盖清单；变异改回硬编码 D4 ⇒ 必红
  - _Requirements: 5.4_

- [ ] 25. 接入 D1-2 `原值明细表（按类别）D1-2`
  - `phase5_d1_02_category.py` 声明（固定 2 行 + 动态行；派生列
    `currentUnadjusted = priorAudited + increase − decrease`）
  - 🔴 派生列声明 `mode=formula`，公式文本以 xlsx 为准、materialize 不覆盖公式格由 OO 重算
    （D1-3 契约已立此纪律：前端算式与 xlsx 公式数值等价但**以 xlsx 为准**）
  - 门：整册 materialize 200 + verify 全绿 + **受管区 1→2** + 实测耗时登记
  - _Requirements: 5.1, 5.2, 5.5_

- [ ] 26. 接入 D1-4 `坏账准备明细表D1-4`（**三区**，D1 首次同 sheet 多区）
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

- [ ] 27. 接入 D1-8（双区）+ D1-16（双区）+ D1-5
  - D1-8：`D1-endorse-discount-rows` / `-transfer-rows`；D1-16：`-reversal-rows` / `-writeoff-rows`
  - D1-5 调整分录单区，含 `isPushedToAdjTable` 推送状态（store-only，不入受管格）
  - 门：整册 materialize + verify + 耗时登记（**受管区 5→10**：D1-8 +2 / D1-16 +2 / D1-5 +1）
  - _Requirements: 5.1, 5.4, 5.5_

- [ ] 28. 接入 D1-9 / D1-10 / D1-11 / D1-12 / D1-15
  - D1-10 带 3 个 recon 标量伴生（`StoreKind.fixed_text`）
  - 🔴 **D1-15 是双区**（复盘修正）：`D1-ecl-individual-rows` / `D1-ecl-portfolio-rows`
    （实测 `useD1EclCalc.ts:208-209` 的 dict 形式），首版按单区写 ⇒ 另一键的数据在 OO 里会
    不可见、回写丢失
  - D1-15 派生列是**乘法**（`shouldProvision = 余额 × 损失率`）与 `difference = E − D` ——
    引擎首次遇到非加减派生，确认 `mode=formula` 路径不依赖算式形态
  - D1-15 的 `autoPulled: boolean` 归一到 `source='tb'`（P16）；其取数源是 D1-4 ⇒ P18 的下游
    联动判据须覆盖「D1-4 三区被 OO 回写后 D1-15 的 `parseD1_4Rows` 仍正确重算」
  - 门：同上（**受管区 10→16**：D1-9/10/11/12 各 +1，D1-15 **+2**）
  - _Requirements: 5.1, 5.5, 5.8, 6.5_

### 阶段 7：D1 批次 4~5

- [ ] 29. 接入 D1-7（嵌套 dict）+ D1-14（纯标量）+ D1-13（**双区** + 标量）
  - D1-7 是一个 item 装两数组 `{bankRows, commercialRows}` ⇒ `StoreKind.dict` 首次用于 D1
  - D1-14 十个标量 ⇒ `StoreKind.fixed_text`，**无行受管区**
  - 🔴 **D1-13 是双区**（复盘补键名）：`D1-sampling-vouching-rows` /
    `D1-sampling-specific-samples`，外加 15 个标量走 `fixed_text`
  - 门：同上（**受管区 16→19**：D1-7 +1 / D1-14 +0 / D1-13 **+2**）
  - _Requirements: 5.1, 5.5_

- [ ] 30.* 评估 D1-6 能否用 `TransposedSheetSpec` 表达
  - D1-6 = 行表（`D1-bm-basis-rows` 3 固定行）+ **真二维矩阵**（`cells: QACell[][]` 4×3）
  - 矩阵部分形似转置表（一列一组合、一行一问题）⇒ 试 `header_field_key=None` /
    `nested_fields_key=None`（与 D4-12 同形）
  - IF 表达不了 THEN 按需求 5.6 显式登记原因（照 `pilot_h1.UPSTREAM_DEBT_…NOT_EXPRESSIBLE`
    范式），**不得**在框架层开特例分支
  - _Requirements: 5.6_

### 阶段 8：D1 批次 6 —— 审定表 D1-1 迁移

- [ ] 31. `AdjudicationSheetSpec` + D1-1 逐格 mask 声明
  - 审定表**不进**行表引擎（裁决 D3：三循环审定表形态互不相同，差异大于共性）
  - D1-1 三区（gross/bd/net）+ 逐格 mask（含小计/合计/差异行）
  - 依赖已修的 `merge._protection` 格级判定 + `_mask_spans_data_column`（本 spec 不重复处理）
  - _Requirements: 5.1_

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
