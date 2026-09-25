# Implementation Plan

## Overview

**spec**：`d567-sync-coverage-via-row-table-engine`　**创建**：2026-09-25　**状态**：2/22（Task 0/1 完成；**前置门已解除**，Task 2~22 可解冻推进）

> ✅ **2026-09-26 前置门解除**（证据 `docs/operations/evidence/d567-sync-coverage/task0-preflight-gate.md`
> + 本次更新）：上游 `d1-sync-row-table-engine-and-d1-coverage` 框架层已完整交付并入 HEAD：
> - `phase5_row_table_sheet.py`：`RowTableSheetSpec` / `AgingLayout` / `AgingGroupSpec` / `StoreKind` /
>   `managed_field_specs()` / `build_store_projection` / `merge_projection_into_store_rows` /
>   `attach_sibling_bindings` 全部落地（Task 6~10），`git show HEAD:` 可读，119 用例全绿。
> - `phase5_adjudication_sheet.py`：`AdjudicationSheetSpec`（Task 31）已交付并 `git show HEAD:` 可读
>   （commit `f1ec1c67d`，提交信息明写 `unblocks: e1-sync-coverage-and-first-canary 前置 B`，
>   本次同样验证解除 d567 前置 B）；24 用例全绿（含变异反证）。
> - `store_item_registry.py`：`StoreItemSpec` / `StoreMergePlan` / `STORE_MERGE_REGISTRY`（Task 11/12）
>   已交付，10 个 adapter 全注册；`oo_to_html.py` 的 9 elif 链 + 6 hasattr 试探、`adapters/excel.py`
>   的 2 处 g7 字面量分支均已改注册表分派（Task 13/14）。
> - **四门禁全绿**：golden digest 零回归（23 个）/ P9 框架层零 wp_code 分支 / P10 全注册 /
>   O(1) 查表验证成立。
> - **决定性验证**：直接用 `RowTableSheetSpec`/`AdjudicationSheetSpec` 构造 D5-4/审定表D5
>   的最小声明实例，import 与实例化均成功（见本次会话验证记录）。
> > **`aging_layout` 参数化**（nested/flat 两路径，本 spec 依赖比 D3 更重的那部分）已用 D6/D7
> 真实原始数据驱动判据验证：`TestProperty3ManagedFieldSpecsD7Nested`（nested，19标量+8账龄=27
> 字段逐元组匹配 provider 原 `sorted()` 表达式）与 `TestProperty3ManagedFieldSpecsD6Flat`
> （flat，json_path 无 `/` 分隔符）均全绿，且 `TestProperty4AgingLayoutIsolation` 的变异反证
> （把 D6 flat 数据塞进 nested 分支）确认引擎会 fail-closed 拒绝混用，不静默产出错误路径。
> ⇒ **前置 A/B/C 均已满足**。前置 D（上游位移判据按 provider 参数化，Task 24）与前置 E（三家
> `adapter_registered`）**尚未验证**，仍按裁决 G6 处置：四组双区（Task 4/16/17）与真栈判据
> 如实标 `[ ]*`，其余 Task 2~22 声明层现在**可以解冻推进**（不再是"依赖不存在符号"的假绿风险）。

三循环合一（用户 B 方案裁决），纯**声明层** + 一处跨循环 bugfix。消费两个上游：
`d1-sync-row-table-engine-and-d1-coverage`（引擎 / `aging_layout` 参数化 /
`AdjudicationSheetSpec` / 四态状态机）与 `d-cycle-sheet-bidirectional-expansion`（裁决与分波，
其 **Wave 5 = D5-3/D6-3/D7-3** 正是本 spec 作业面）。⇒ **Task 0 是硬前置门**。

**受管区路线（三家独立计数、独立回滚 —— 三个 entry 爆炸半径天然隔离）**：

```
D5:  1 → 2 (D5-4) → 3 (审定表D5)                                      D5-3 可行性核
D6:  1 → 2 (D6-3) → 3 (D6-5) → 5 (D6-6 双区) → 6 (D6-8) → 8 (D6-9 双区) → 9 (D6-1)
                                                   D6-4 可行性核 / D6-7 形态核
D7:  1 → 3 (D7-4 双区) → 4 (D7-5) → 5 (D7-6) → 7 (D7-7 双区) → 8 (D7-1)  D7-3 可行性核
```

每家都**先单区后双区最后审定表**。D6(flat) 与 D7(nested) 建议同批推进，让引擎两条账龄路径在
同一轮对照验证（差异一旦出现能立即归因到 `aging_layout` 而非别处）。

🔴 **三家 `adapter_registered` 全 False**（真库只注册 `{d2,d4,g7,h1}`）⇒ 真栈实测跑不起来，
相关判据如实标 `[ ]*`，**不得**以合成测试冒充真栈。

## Tasks

### 阶段 0：前置门 + 独立 bugfix + 实测填参

- [x] 0. 前置依赖核查（**判定用 `git show HEAD:` 不读工作树**）✅ 2026-09-26
  完成：三框架文件 HEAD 全不存在，A/B/C/D 未满足、E 全 False；结论落 evidence，全部任务阻塞（Task 1 除外）
  - 前置 A：上游框架层 + **`aging_layout` 参数化**（上游任务 16：D3/D6/D7 nested+flat 收敛）已入 HEAD
    —— 🔴 本 spec 对上游依赖比 D3 更重：flat/nested 两条路径正是在 D6/D7 身上验证的
  - 前置 B：`AdjudicationSheetSpec` 已交付
  - 前置 C：`merge._protection` 格级判定 + `_mask_spans_data_column` 已入 HEAD
  - 前置 D：上游任务 24（位移判据按 provider 参数化）—— 未落则四组双区阻塞
  - 前置 E：三家 `adapter_registered` 是否已 True（实测现状**全 False**）
  - IF A 未满足 THEN 全部阻塞。IF B/C 未满足 THEN 三张审定表阻塞。IF D 未满足 THEN 四组双区阻塞。
    IF 仅 E 未满足 THEN 真栈阻塞并标 `[ ]*`。**Task 1（聚合键缺陷）不受任何前置阻塞**
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 1. 修 D6/D7 底稿目录聚合键缺陷（**独立交付，不依赖任何前置**）✅ 2026-09-26
  完成：`D6TabIndex.vue`/`D7TabIndex.vue` 四处聚合键改判真实写入方分区键（D6-6/D7-4/D7-7 双区任一有行即已填、D6-8→single），
  完成度判定提取为纯函数 `isD6/D7SheetComplete`（`d6/d7SheetLabels.ts`）供判据直接驱动、不镜像键名；
  红判据 `d67TabIndexAggregateKeyFix.spec.ts` 14 用例全绿，变异改回聚合键实测打红（Property 10/11）；
  四聚合键前端生产源码 `hasJsonRows` 调用零残留；5 文件 0 diagnostics
  - `D6TabIndex.vue:54` `hasJsonRows(m,'D6-6-rows')` → 判 `D6-6-block1-rows` 与 `D6-6-block2-rows`
    （任一有行即已填）；`:56` `'D6-8-rows'` → `D6-8-single-rows`
  - `D7TabIndex.vue:50` `'D7-4-rows'` → 判 `D7-4-credit-rows` 与 `D7-4-debit-rows`；
    `:56` `'D7-7-rows'` → 判 `D7-7-period-rows` 与 `D7-7-post-rows`
  - 🔴 **判据以真实写入方的键播种**、断言完成度为已填；**不得镜像错误键名** —— D1 那次
    「三个消费方单测都镜像同款错误锚点、测试恒绿而生产恒死」是同源事故
  - Property 10 / 11：变异改回聚合键 ⇒ 必红；grep 全仓确认四键零残留引用
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 2. 十三张 sheet **形态判定** + 几何实测填参 + 下游消费方 grep 补全
  - 🔴 **形态判定先于几何填参**（复盘补，需求 9）：每张先定 `binding_kind`
    （`excel_table` vs **`static_region`**）与 `row_identity_key`（`rowId` / **稳定 key** / 无），
    再填几何 —— 判为 `static_region` 的只需 definedName 锚点与绝对坐标，不需要 UUID 列 / Table /
    footer 行，且**绕开整条位移链**
  - 强命中 `static_region` 的候选：**D6-7**（58r×18c / **仅 7 公式**，首版漏了这个候选）；
    待判定的低公式密度表：**D7-5**（20r×8c/9f，与 D3-5 同型须同结论）、**D6-9**（30r×8c/10f）、
    **D6-5**（30r×14c/19f）
  - 参照 D4 三实现：`phase5_d4_erp_check_sheet`(D4-13 A6/A16 单 cell) /
    `phase5_d4_product_margin_sheet`(D4-8) / D4-33(72 static cell) /
    `phase5_d4_indicator_sheet`(D4-6 稳定 key 固定行，`ROW_IDENTITY_KEY_D46="key"` + 仍注入 UUID 列 I)
  - openpyxl 逐张实测几何（`first/last_data_row` / `footer_row` / `header_row` / 公式列归类 /
    有无可注入 UUID 列 / 双区各占哪几行）
  - 🔴 另两项复盘补：①各 sheet 的 note/conclusion/procedures item 若在 footer 之下，逐项核是否
    命中「footer 下 `static_row` 与插行 fail-closed 冲突」（先例 `HTML_ONLY_ITEM_IDS_D45`）⇒
    命中则登记 HTML-only 子集 ②三家宿主须覆盖**两套 gating**（`isD*DetailSheet` + 专用同步 sheet 链），
    漏后者会工具条叠加冲突（D4-35/D4-13 踩过）
  - 已实测在案可直接用：D5-4 26r×13c/18f(K6 I4) · 审定表D5 18r×12c/52f · D6-3 29r×14c/63f(N12 E11 K11) ·
    D6-5 30r×14c/19f · D6-6 53r×17c/19f · D6-8 48r×15c/58f(D21 F21) · D6-9 30r×8c/10f ·
    D6-1 43r×13c/**177f** · D7-4 43r×8c/32f(E13 D11) · D7-5 20r×8c/9f · D7-6 31r×11c/15f ·
    D7-7 48r×21c/19f · D7-1 32r×12c/84f
  - 🔴 **三张审定表的 `sections`/`row_mode` 必须实测**（裁决 G5）：四循环审定表形态已证互不相同
  - 🔴 **按值 grep 补全每个 store 键的下游消费方清单**（上游 P18 教训）
  - 产出实测表落 spec `evidence/`，后续任务引用它而非重测
  - 🔴 **本任务产出会改后续阶段顺序**：判为 `static_region` 的 sheet 绕开整条位移链
    （无 row_shift / footer 两门 / 兄弟 Table ref 维护）⇒ 风险显著低于行表 ⇒ 应**提前**接入，
    首版的「先单区后双区最后审定表」需据此调整为「先静态区、再单区、再双区、最后审定表」
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.6, 3.5, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

- [ ] 3. Property 1 零回归基线 + Property 2 红判据
  - 三家已接明细（`D5-2-rows`/`D6-2-rows`/`D7-2-rows`）+ 其余 contract 的 golden digest（必绿）
  - Property 2 红判据：断言 `managed_sheet` 与 `store_item_id` 逐字等于实测值。三例变异：
    `审定表D5`→`审定表D5-1`（sheet 找不到）/ `D6-8-single-rows`→`D6-8-rows`（零写入点键 ⇒ 投影恒空）
    / `D7-4-credit-rows`→`D7-4-rows`。🔴 四次事故背书，本 spec 最易犯的错
  - D5/D6 store 全库 0 行 ⇒ 合成 payload 驱动（需求 6.4）
  - _Requirements: 6.3, 6.4_

- [ ] 4. Property 3 红判据：四组双区 + Property 12 历史残留排除
  - 四组双区（D6-6 / D6-9 / D7-4 / D7-7）各断言受管区数与两键读回等值；现状必红
  - Property 12：D6 册的 `合同资产实质性程序表 D7A（原）`(104r) 与 D7 册的
    `合同负债实质性程序表 D8A（原）`(66r) 须被显式排除，且分派正则不误判
  - _Requirements: 2.3, 2.5, 3.1, 3.4, 6.6_

- [ ] 5. 三家性能基线 + `adapter_registered` 现状登记
  - 按循环**独立**记整册 materialize 与三端点耗时（混算会让「哪家退化」无法归因）
  - 若因 `adapter_registered=False` 跑不起来，如实登记「真库不可测」+ 合成基线替代口径
  - 🔴 `store_field_count` / `field_count` 记实测值，**不得**作差推断数据丢失
  - _Requirements: 6.1, 7.3_

### 阶段 1：D5（最小循环，2 张）

- [ ] 6. `phase5_d5_04_fair_value.py` 声明 + 开关
  - `store_item_id="D5-4-rows"`（实测）；`aging_layout=None` ⇒ 引擎「无分组」路径基准样本
  - 循环层 `phase5_d5_receivables_financing` 追加 sheet 清单项 + `_INCLUDE_D504` 开关
  - _Requirements: 1.1, 1.4_

- [ ] 7. `phase5_d5_01_adjudication.py` 声明（`AdjudicationSheetSpec`）
  - 🔴 `managed_sheet="审定表D5"` —— **实测名无 `-1` 后缀**，按 `审定表D5-1` 推演会 sheet 找不到
  - `sections`/`row_mode` 取 Task 2 实测值；逐格 mask（18r×12c/52f）
  - _Requirements: 1.2_

- [ ] 8. D5 接入验收（受管区 1→3）
  - Property 2 的 D5 部分转绿；Property 6（审定表形态实测）/ Property 7（逐格 mask 下 editable）绿
  - Property 8 四态：反证式判据 + **跑同步器**的判据（上游纯函数判据全绿而生产坏掉的教训）
  - Property 9：`D5-4-rows` 下游（`useD5CrossSheet` / `useD5FairValue`）在回写后正确重算
  - Property 13：D5 整册 materialize 200 + verify 全绿（若 `adapter_registered=False` 标 `[ ]*`）
  - _Requirements: 1.3, 1.5, 6.1, 6.3_

### 阶段 2：D6 单区三张（flat 路径）

- [ ] 9. `phase5_d6_03_impairment.py` + `phase5_d6_05_related_party.py` 声明
  - `D6-3-rows`(29r×14c/63f 主列 N12 E11 K11) / `D6-5-rows`(30r×14c/19f)；`aging_layout=flat`
  - _Requirements: 2.1, 2.2, 2.9_

- [ ] 10. `phase5_d6_08_ecl.py` 声明
  - 🔴 `store_item_id="D6-8-single-rows"` —— **不是 `D6-8-rows`**（后者全仓零写入点，
    误用会让整个受管区投影恒空）；48r×15c/58f 主列 D21 F21
  - _Requirements: 2.4_

- [ ] 11. D6 单区验收（受管区 1→2→3→4）
  - Property 2 的 D6 单区部分转绿；Property 5（flat 键派生 ≡ 原写法，变异走 nested ⇒ 必红）
  - Property 9：`useD6CrossSheet` / `D6TabWriteoffCheck` / `useD6EclCalculation` 在回写后正确重算
  - Property 13：D6 整册 materialize + 耗时登记
  - _Requirements: 2.8, 2.9, 6.1_

### 阶段 3：D7 单区两张（nested 路径，与 D6 同批对照）

- [ ] 12. `phase5_d7_05_long_term.py` + `phase5_d7_06_related_party.py` 声明
  - `D7-5-rows`(20r×8c/9f) / `D7-6-rows`(31r×11c/15f)；`aging_layout=nested`
  - 📌 D7-5 与 D3-5 同型（同为「账龄1年以上…检查表」、几何逐项相同）⇒ 声明骨架可复制
  - _Requirements: 3.2, 3.3, 3.7_

- [ ] 13. D7 单区验收 + 两条账龄路径对照
  - Property 5 的 nested 侧；🔴 **与 Task 11 的 flat 侧对照**：两路径输出差异须能归因到
    `aging_layout` 参数而非别处（裁决 G2 的落点）
  - Property 13：D7 整册 materialize + 耗时登记（受管区 1→2→3）
  - _Requirements: 3.7, 6.1_

### 阶段 4：四组双区（位移链）

- [ ] 14. `phase5_d6_06_inspection.py` 声明双区
  - `D6-6-block1-rows` / `D6-6-block2-rows`（`useD6Inspection`）；53r×17c，两区行段 Task 2 实测
  - 🔴 **不得**用聚合键 `D6-6-rows`（零写入点）
  - _Requirements: 2.3_

- [ ] 15. `phase5_d6_09_writeoff.py` 声明双区
  - `D6-9-reversal-rows` / `D6-9-writeoff-rows`（`useD6WriteoffCheck`）；30r×8c/10f
  - _Requirements: 2.5_

- [ ] 16. `phase5_d7_04_analysis.py` + `phase5_d7_07_inspection.py` 声明双区
  - `D7-4-credit-rows`/`-debit-rows`（43r×8c/32f）与 `D7-7-period-rows`/`-post-rows`（48r×21c/19f）
  - 🔴 **不得**用聚合键 `D7-4-rows` / `D7-7-rows`（零写入点）
  - _Requirements: 3.1, 3.4_

- [ ] 17. 四组双区验收（位移链逐组实证）
  - Property 3 转绿（D6 3→5、5→6 后 6→8；D7 3→5 后 5→7）
  - 🔴 **Property 4 逐组实证**：上区插行后下区 Table ref 随之下移 + `_GT_SYNC` footer 坐标重冻结
    + verify 累积归一化通过（照 D4-9/D4-20 范式）；依赖前置 D（上游任务 24）
  - Property 9：`useD7CrossSheet` / `useD7Detail` 对 `D7-7-post-rows` 的读取在回写后正确重算
  - Property 13：两家整册 materialize + 耗时登记
  - _Requirements: 2.3, 2.5, 3.1, 3.4, 3.8, 6.1, 7.4_

### 阶段 5：D6-1 / D7-1 审定表

- [ ] 18. `phase5_d6_01_adjudication.py` 声明
  - 逐格 mask（43r×13c / **177 公式** / 密度 **32%**，四循环里最高）；`sections`/`row_mode` 取
    Task 2 实测值，🔴 不得照 D1-1/D2-1/D3-1/D5 推演（裁决 G5）
  - **不得**在引擎加 `if is_d6` 分支（会让上游框架层 AST 卡点打红）
  - _Requirements: 2.6_

- [ ] 19. `phase5_d7_01_adjudication.py` 声明
  - 逐格 mask（32r×12c/84f）；`sections`/`row_mode` 实测
  - _Requirements: 3.5_

- [ ] 20. 两张审定表验收 + 四态状态机
  - Property 6（形态实测，变异改成 D1-1 的 3 区 ⇒ 必红）/ Property 7（逐格 mask 下 editable）
  - Property 8：反证式 + **跑同步器**的判据；复用 `shared/dynamicAdjudicationRows`，
    **不得**在 D6/D7 侧另写一套
  - S2 标「已人工覆盖」/ S4 三值不自动二选一 / 逐格「恢复取数」
  - 受管区：D6 8→9、D7 7→8（按实测区块数调整）+ 两家整册 materialize + 耗时登记
  - _Requirements: 2.6, 2.8, 3.5, 3.6, 6.1_

### 阶段 6：可行性核 + 前端接线 + 验收

- [ ] 21. 三张调整分录汇总表可行性核（**不改生产代码**）
  - D5-3 `D5-3-rows` / D6-4 `D6-4-rows` / D7-3 `D7-3-rows`；已实证三家宿主**各接
    `useAdjustmentCentralSync` 3 处** ⇒ 经后端 `AdjustmentSyncService` 中央登记、均为 hub store
  - 本任务待核：借贷平衡是否仅 HTML 侧强制 / 模板有无行身份列
  - 另含 **D6-7 减值准备会计政策检查形态核**（58r×18c / **仅 7 公式**）：
    🔴 **第一候选 `static_region`**（复盘补 —— 首版只给 `paragraph_block_bidirectional` /
    `single_html` 两个候选，漏了 D4-13 已验证的这条路径：大表但无动态行无公式正是它的形态），
    其次 `paragraph_block_bidirectional`（D4-5 范式），最后 `single_html`
  - Property 14：核阶段不改任何生产代码；变异改了 provider ⇒ 必红
  - 📌 **七张调整分录汇总表全部同型**（D1-5/D2-4/D3-3/D4-4 已判/D5-3/D6-4/D7-3）⇒ 建议统一裁决
    另立 `d-cycle-adjustment-sheets-single-html-adjudication`；IF 已立 THEN 本任务降级为引用其结论
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 22.* 前端接线 + 变异检验 + 真栈 + 证据
  - 前端三家宿主（现状均单张写死 `isD*DetailSheet = currentSheet === 'D*-2'`）：受管 sheet 集合
    **从 provider 受管清单派生**、`capability` 与 `flushHtml` 改读 `Ref`；非受管 sheet 保持现状
    + 中文原因，**不得**落 legacy 假双向。Property 15 钉住
  - Property 1~15 逐条变异并记录打红条数；未能打红的重写而非保留
  - 真栈**按循环分三段**：各自切「在线编辑」→ OO canvas 逐值断言 → 改一格 → forcesave → 回读等值。
    `--workers=1`。🔴 三陷阱沿用上游结论（不能用 `page.on('response')` 判 callback；不能用
    `asc_*` API 写格，须真实键盘输入 `#ce-cell-name` → `keyboard.type` → Enter）；
    **模式切换条选择器须逐循环实测**，照抄任一家都可能找不到元素
  - 🔴 IF 三家 `adapter_registered=False` 未解除 THEN 真栈整段标 `[ ]*` + 写明「代码已改但未实测，
    卡 adapter 未注册」，**不得**以合成测试冒充真栈
  - 证据落 `docs/operations/evidence/d567-sync-coverage/`，**按循环分子目录**，数字脚本现测
  - _Requirements: 6.5, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0", "1"], "rationale": "前置门先于一切；Task 1（聚合键缺陷）是纯前端 bugfix、不依赖任何前置，可与前置核查并行 —— 且先修掉它能让后续声明误用聚合键更易发现（那些键已从代码消失）" },
    { "wave": 1, "tasks": ["2", "3", "4", "5"], "rationale": "几何实测 / 零回归基线+Property 2 红判据 / 双区与残留 sheet 红判据 / 三家性能基线，互不依赖可并行" },
    { "wave": 2, "tasks": ["6", "7"], "rationale": "D5 两张声明依赖 Task 2 实测几何；D5 是最小循环，先跑通它验证整条声明链" },
    { "wave": 3, "tasks": ["8"], "rationale": "D5 验收门（受管区 1→3），含首次四态状态机接入" },
    { "wave": 4, "tasks": ["9", "10", "12"], "rationale": "D6 三张单区与 D7 两张单区可并行 —— 三个 entry 互不影响；D6(flat)/D7(nested) 同批是为让两条账龄路径对照验证" },
    { "wave": 5, "tasks": ["11", "13"], "rationale": "D6/D7 单区验收门，两条账龄路径在此对照（差异须能归因到 aging_layout）" },
    { "wave": 6, "tasks": ["14", "15", "16"], "rationale": "四组双区声明，依赖 Wave 5 已证单区通路；三条声明互不依赖可并行" },
    { "wave": 7, "tasks": ["17"], "rationale": "四组双区验收门 —— 位移链逐组实证，依赖前置 D（上游位移判据参数化）" },
    { "wave": 8, "tasks": ["18", "19"], "rationale": "两张审定表声明，依赖前置 B/C 与 Task 2 的区块数实测" },
    { "wave": 9, "tasks": ["20"], "rationale": "审定表验收 + 四态状态机，依赖 Task 18/19 的 spec 形态已落" },
    { "wave": 10, "tasks": ["21"], "rationale": "三张调整分录可行性核 + D6-7 形态核，独立于接入链，排在其后以免「不改代码」纪律与接入改动混淆归因" },
    { "wave": 11, "tasks": ["22"], "rationale": "前端接线依赖后端受管清单已定；变异与真栈收口需全部行为已落地" }
  ],
  "blocking": {
    "0": "上游框架层 + aging_layout 参数化未入 HEAD ⇒ D6/D7 声明无形态可依，全部阻塞；AdjudicationSheetSpec/_protection 未入库 ⇒ 阶段 5 阻塞；上游位移判据未参数化 ⇒ 阶段 4 四组双区阻塞；adapter_registered=False ⇒ 真栈阻塞",
    "2": "几何与形态未实测 ⇒ 声明只能按模式推演，而本 spec 有三处实证必错（审定表D5 无 -1 后缀 / D6-8-single-rows 非 D6-8-rows / D7-4 双键非聚合键）",
    "3": "Property 2 未先打红 ⇒ 按模式推演这个最易犯的错没有可执行判据（四次事故背书）",
    "4": "Property 3/12 未先打红 ⇒ Task 17 的双区转绿与残留 sheet 排除不可归因",
    "5": "三家性能基线未取 ⇒ 需求 6.1 的每批次耗时对比无分母；且必须按循环独立记，混算会让「哪家退化」无法归因",
    "6": "D5-4 声明未落 ⇒ Task 8 无验收对象，整条声明链未在最小循环上验证",
    "9": "D6 单区未落 ⇒ Task 11 的 flat 路径无实证对象，Task 14/15 的双区缺前置",
    "12": "D7 单区未落 ⇒ Task 13 的 nested 路径无实证对象，且失去与 flat 的对照",
    "18": "审定表 spec 未落 ⇒ Task 20 的四态状态机读不到 stored/snap/derived 三个量"
  }
}
```

## Notes

### 已裁决（详见 design §关键裁决）

- **G1**：三家合一 spec，但受管区计数 / materialize 实测 / 灰度开关三者**按循环独立**
- **G2**：D6(flat) 与 D7(nested) 同批推进，作引擎两条账龄路径的对照
- **G3**：`store_item_id` 与 `managed_sheet` 逐个实测，禁止按模式推演（三处实证必错）
- **G4**：聚合键缺陷独立交付（Task 1），判据**不得镜像错误键名**
- **G5**：三张审定表的 `sections`/`row_mode` 全部待实测
- **G6**：三家 `adapter_registered=False` 是真实前置，真栈须先解除、不得以合成冒充

### 继承上游四条纪律

「一 entry 一 adapter」不变 · 诚实边界（不是每张 sheet 都双向）· 可行性核硬门（有行身份列 +
无专用同步链冲突）· D4-4 已判 `single_html` 的判据适用于全部调整分录汇总表。

### D 类 spec 全景（本 spec 完成后 D1~D7 各有三件套）

| 循环 | spec | 受管区路线 |
|---|---|---|
| D1 | `d1-sync-row-table-engine-and-d1-coverage`（含框架层） | 1 → 22~23 |
| D2 | `d2-sync-coverage-via-row-table-engine` | 1 → 5 |
| D3 | `d3-sync-coverage-via-row-table-engine` | 1 → 8 |
| D4 | `d4-html-to-oo-store-contract-alignment`（已归档 `_archive/15-workpaper-sync-engine-hardening/`）（bugfix）+ 已有 30 受管 sheet | — |
| D5/D6/D7 | **本 spec** | 1→3 / 1→9 / 1→8 |

跨循环遗留（建议另立）：`d-cycle-adjustment-sheets-single-html-adjudication`（七张调整分录汇总表
统一裁决）· 发布链 seed（解除各家 `adapter_registered=False`）。
