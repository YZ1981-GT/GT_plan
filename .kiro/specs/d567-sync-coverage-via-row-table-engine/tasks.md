# Implementation Plan

## Overview

**spec**：`d567-sync-coverage-via-row-table-engine`　**创建**：2026-09-25　**状态**：**20/22**
（Task 0~21 完成；Task 22 部分（宿主受管集合已扩，capability/flushHtml Ref 化与变异清单未做）；
真栈全段 `[ ]*` 卡 adapter 未注册）

> ✅ **2026-09-30 Task 20 交付**：Property 7（模板锚定逐格 mask，20 passed）+ Property 8
> 四态状态机三家 composable 全线接入 + 共享徽标 UI 接入 7 个派生列位（判据 59 + 15 条）。
> 🔴 该轮抓到并修掉**后端 fail-closed 真缺陷**：D7-1 区1 误锁 36 格、D6-1 区1+区2 误锁 60 格
> 手工录入格（声明注释称有 SUMIF 公式，模板实测为空）⇒ 审计师在 OO 里改不了，D4-1 同型。
> 7 处变异逐一验证判据承重。详见 Task 20 条目。

> ✅ **2026-09-26 声明层全量交付**：16 个 sheet 声明文件 + 3 个 expansion 模块 + 三家契约接线。
> 三家受管区：**D5 1→3**（d52+d54+d51-adj）· **D6 1→11 table**（d62+d63+d65+d68+d66×2+d69×2+d61-adj×3）
> · **D7 1→9 table**（d72+d75+d76+d74×2+d77×2+d71-adj×2）。
> 判据 43 passed（Property 2 31 条 + Property 3/12 12 条）。
>
> 🔴 **两处真实卡点（`[ ]*`，非本 spec 缺陷）**：
> ① **adapter_registered 全 False** —— 实测根因是 manifest capability=`single_onlyoffice`（非
>    `bidirectional`）+ `adapter_id=None`。翻它需走 **reviewed overlay 裁决 + manifest 重生成**
>    （D2/D4/G7/H1 的路径，属 umbrella Task 36/77）。本轮曾手工改 manifest 试注册 ⇒ 撞
>    `sync_contract_structure_drift`（真库旧 bundle 不认新契约），**已回滚**——仓库明文警告
>    「提前把 capability 改成 bidirectional 就是跳过顺序，manifest 会宣称双向可用而 registry
>    里一个 adapter 都没有」。发布链（`publish_definitions` → bundle → representation binding）
>    需后端运行时 context（project_id/wp_id/schema），离线脚本跑不通。
> ② **D7-4/D7-7 双区位移链 2 红** —— 接入双区后自动进 `test_sibling_table_ref_row_shift` 参数化
>    清单，需真实 instrumentation 注入才能过，同卡 ①。
>
> 🔴 **并发会话冲突实录**：本轮工作期间三家 provider 被并发会话重构为
> `build_orchestration(Phase5EntryConfig(...))` 配置驱动模式，我对 provider 的首轮改动
> （`instrumentation_specs()` 复数 / `STORE_ITEM_IDS` / `build_combined_store_projection` /
> `merge_combined_projection`）**全部被覆盖丢失**；三个前端 Vue 宿主的 `isD*DetailSheet` 改动
> **同样丢失**（交付前 `git status` 复核发现无 diff 才察觉）。
> 二轮改为最小侵入：只改 `build_contract_payload`（配置暴露的 `build_contract_payload_fn` 扩展点）
> + 新建共享模块 `phase5_d567_expansion_contract.py`（三家共用，避免三份复制）。
> **两项未重做**：① 多 item store-projection 注册（`STORE_ITEM_IDS` +
> `build_combined_store_projection` + `merge_combined_projection`）—— 需改 provider 本体，与重构后的
> 配置驱动架构如何共存需裁决 ② 前端宿主接线 —— 需先定受管清单下发机制。二者均入未完成清单。
>
> 🔴 **交付纪律教训**：长任务中途必须 `git status --porcelain` 复核自己的改动是否还在，
> 不能只凭"我刚才编辑过"就认定交付成功。本轮两批改动被覆盖，都是交付前复核才发现。

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

- [x] 2. 十三张 sheet **形态判定** + 几何实测填参 + 下游消费方 grep 补全 ✅ 2026-09-26
  证据 `evidence/task2-sheet-morphology-and-geometry.md`：14 张 sheet openpyxl 逐行实测（几何/公式列/
  合计行/候选 UUID 列/merged）+ 逐张形态判定 + 13 个 store 键的写入方与下游消费方 grep 补全。
  🔴 **抓到 6 处 sheet 名与 spec 原文不符**（裁决 G3 实证）：D6-3「减值准备测算」→**「合同资产减值准备
  明细表」** · D6-8 去「合同资产」前缀 · D6-9 加顿号「、」+尾「表」 · D7-5 尾加「表」 · D7-6
  「关联方合同负债检查」→**「关联方关系及交易检查表」** · D7-7「凭证检查」→「检查表」。按原名声明会
  attach fail-closed。
  🔴 **审定表形态三家互不相同**（裁决 G5 实证）：审定表D5 **1 区**（2 行数据 + OCI 扣减，52f）/
  D6-1 **3 区**（原值/坏账/净值各 5 行，**177f 密度 32%**）/ D7-1 **2 区**（性质 6 行+账龄 4 行，84f，
  与 D3-1 同型可复制骨架）。
  🔴 **D6-7 形态核**：58r×18c 仅 **7 公式**、无合计行 ⇒ `static_region` 首选（Task 21 留证）。
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

- [x] 3. Property 1 零回归基线 + Property 2 红判据 ✅ 2026-09-26
  Property 1：`check_sync_provider_golden_digest.py` 实测 D5/D6/D7 **零漂移**（唯一漂移是 E1 的
  instrumentation，属并发会话，与本 spec 无关）。
  Property 2：新建 `test_d567_property2_store_item_id_exact_match.py`（**31 passed**）——3 个已接明细
  恒绿 + 13 个 managed_sheet 真名 + 10 个 store_item_id 实测值 + **5 条变异必红**（`审定表D5-1` 带后缀 /
  `D6-8-rows` / `D7-4-rows` / `D6-6-rows` / `D7-7-rows` 四个零写入点聚合键）。
  - 三家已接明细（`D5-2-rows`/`D6-2-rows`/`D7-2-rows`）+ 其余 contract 的 golden digest（必绿）
  - Property 2 红判据：断言 `managed_sheet` 与 `store_item_id` 逐字等于实测值。三例变异：
    `审定表D5`→`审定表D5-1`（sheet 找不到）/ `D6-8-single-rows`→`D6-8-rows`（零写入点键 ⇒ 投影恒空）
    / `D7-4-credit-rows`→`D7-4-rows`。🔴 四次事故背书，本 spec 最易犯的错
  - D5/D6 store 全库 0 行 ⇒ 合成 payload 驱动（需求 6.4）
  - _Requirements: 6.3, 6.4_

- [x] 4. Property 3 红判据：四组双区 + Property 12 历史残留排除 ✅ 2026-09-26
  新建 `test_d567_property3_12_dual_zone_and_residual.py`（**12 passed**）。Property 3：三家受管区计数
  逐项钉死 + 四组双区（d66/d69/d74/d77）present 断言（接入后从红转绿）。Property 12：两个残留 sheet
  （D6 册 `合同资产实质性程序表 D7A（原）` 104r / D7 册 `合同负债实质性程序表 D8A（原）` 66r）
  **openpyxl 确认真实存在于模板** 且不在契约 sheets 中（非空分母断言）。
  - 四组双区（D6-6 / D6-9 / D7-4 / D7-7）各断言受管区数与两键读回等值；现状必红
  - Property 12：D6 册的 `合同资产实质性程序表 D7A（原）`(104r) 与 D7 册的
    `合同负债实质性程序表 D8A（原）`(66r) 须被显式排除，且分派正则不误判
  - _Requirements: 2.3, 2.5, 3.1, 3.4, 6.6_

- [x] 5. 三家性能基线 + `adapter_registered` 现状登记 ✅ 2026-09-26
  证据 `evidence/task5-performance-baseline.md`：按循环独立记（合成 5 行 payload，非真栈）——
  D5 contract=95.5ms proj=1.0ms 85 fields / D6 contract=257.3ms proj=0.4ms 150 fields /
  D7 contract=278.2ms proj=0.8ms 135 fields。`field_count` 差异来自 D6(flat)/D7(nested) 账龄展开。
  `adapter_registered` 三家全 False，根因已实测到 manifest capability 层（见 Overview 卡点①）。
  - 按循环**独立**记整册 materialize 与三端点耗时（混算会让「哪家退化」无法归因）
  - 若因 `adapter_registered=False` 跑不起来，如实登记「真库不可测」+ 合成基线替代口径
  - 🔴 `store_field_count` / `field_count` 记实测值，**不得**作差推断数据丢失
  - _Requirements: 6.1, 7.3_

### 阶段 1：D5（最小循环，2 张）

- [x] 6. `phase5_d5_04_fair_value.py` 声明 + 开关 ✅ 2026-09-26
  13 字段（A-M）/ 4 公式列 **G**(=F-E 剩余天数) **I**(=D*H*G/365 贴现利息) **J**(=D-I) **K**(=J)/
  数据行 12-16 / footer 17「合计」/ UUID 列 N / `aging_layout=None`（引擎无分组路径基准样本）。
  🔴 实测落差登记：模板公式用 **÷365** 而前端 `recalcFairValueRow` 用 **÷360**，声明按模板实测。
  新建 `phase5_d5_expansion.py`（灰度开关 `_INCLUDE_D504_FAIR_VALUE=True`）。
  - `store_item_id="D5-4-rows"`（实测）；`aging_layout=None` ⇒ 引擎「无分组」路径基准样本
  - 循环层 `phase5_d5_receivables_financing` 追加 sheet 清单项 + `_INCLUDE_D504` 开关
  - _Requirements: 1.1, 1.4_

- [x] 7. `phase5_d5_01_adjudication.py` 声明（`AdjudicationSheetSpec`）✅ 2026-09-26
  🔴 `managed_sheet="审定表D5"` **无 -1 后缀**（裁决 G3 三处实证必错之首，已由 Property 2 钉住）。
  **1 区**（`section_key="main"`，数据 R7-R8 应收票据/应收账款，小计 R9）+ footer 三行
  （合计 R11 = R9-R10 OCI 扣减 / TB R12 / 差异 R13 只 E/I）。`row_mode=fixed_rows`。
  逐格 mask **46 格**现算（`_build_cell_mask()`，不手写字面量）。
  per-cell 键模板 `D5-1-adj-{slug}-{field}`（**无 section 维度**，与前端 `makeItemId` 逐字对齐）。
  `current_unadjusted=cross_sheet`（派生格不可 OO 直写）。
  - 🔴 `managed_sheet="审定表D5"` —— **实测名无 `-1` 后缀**，按 `审定表D5-1` 推演会 sheet 找不到
  - `sections`/`row_mode` 取 Task 2 实测值；逐格 mask（18r×12c/52f）
  - _Requirements: 1.2_

- [~] 8. D5 接入验收（受管区 1→3）—— 声明+契约绿，Property 8/9 与真栈未做
  ✅ 受管区 **1→3**（d52 + d54 + d51-adj），契约重生成通过 `assert_contract_file_matches_source()`；
  Property 2 的 D5 部分转绿；Property 6（审定表形态实测）由 Task 7 的几何断言覆盖。
  `[ ]` **Property 8 四态**（反证式 + 跑同步器）：前端 `useD5Adjudication.ts` 现仍是
  `crossSheetCurrent !== 0 ? cross : manual` 二选一，**未接** `resolveCellState`/
  `displayValueForCellState`（D3-1 已接，D5 未接）⇒ 四态状态机在 D5 侧未实施。
  `[ ]` **Property 9**（`D5-4-rows` 下游 `useD5CrossSheet`/`useD5FairValue` 回写后重算）未写判据。
  `[ ]*` **Property 13 整册 materialize** 真栈不可测（卡 adapter 未注册，见 Overview 卡点①）。
  - Property 2 的 D5 部分转绿；Property 6（审定表形态实测）/ Property 7（逐格 mask 下 editable）绿
  - Property 8 四态：反证式判据 + **跑同步器**的判据（上游纯函数判据全绿而生产坏掉的教训）
  - Property 9：`D5-4-rows` 下游（`useD5CrossSheet` / `useD5FairValue`）在回写后正确重算
  - Property 13：D5 整册 materialize 200 + verify 全绿（若 `adapter_registered=False` 标 `[ ]*`）
  - _Requirements: 1.3, 1.5, 6.1, 6.3_

### 阶段 2：D6 单区三张（flat 路径）

- [x] 9. `phase5_d6_03_impairment.py` + `phase5_d6_05_related_party.py` 声明 ✅ 2026-09-26
  **D6-3**（真名「合同资产减值准备明细表D6-3」）：14 字段 / 3 公式列 E(=C+D) K(=F+G+H-I-J) N(=K+L+M)/
  数据行 12-21（含双分类：单项 12-16 + 组合 18-21）/ footer 22 / UUID 列 O。
  **D6-5**：14 字段 / 2 公式列 F(=C+D-E 期末余额) H(=F-G 账面价值)/ 数据行 10-12 / footer 13 /
  🔴 UUID 列 **O**（首版写 M 撞受管最后列 N，被 `InstrumentationError` 打红后修正——UUID 必须严格在
  `managed_last_col` 右侧）。
  新建 `phase5_d6_expansion.py`。两张 `aging_layout=None`（sheet 自身无账龄组，不同于 D6-2）。
  - `D6-3-rows`(29r×14c/63f 主列 N12 E11 K11) / `D6-5-rows`(30r×14c/19f)；`aging_layout=flat`
  - _Requirements: 2.1, 2.2, 2.9_

- [x] 10. `phase5_d6_08_ecl.py` 声明 ✅ 2026-09-26
  🔴 `store_item_id="D6-8-single-rows"`（**不是** `D6-8-rows` 零写入点聚合键，Property 2 已钉住）。
  真名「减值准备测算D6-8」。8 字段（A-H）/ 2 公式列 D(=B*C 期末应计提) F(=D-E 差异)/
  数据行 12-17（单项计提区）/ footer 18「小计」/ UUID 列 I。
  🔴 **只覆盖单项计提区**：D6-8 模板另有组合1（R22-28）/组合2（R31-36）两段，但 store 侧走独立键
  `D6-8-groups`（非 rows 形态），不在本 spec 行表范围，已在模块 docstring 登记。
  - 🔴 `store_item_id="D6-8-single-rows"` —— **不是 `D6-8-rows`**（后者全仓零写入点，
    误用会让整个受管区投影恒空）；48r×15c/58f 主列 D21 F21
  - _Requirements: 2.4_

- [~] 11. D6 单区验收（受管区 1→2→3→4）—— 声明+契约绿，Property 5/9 与真栈未做
  ✅ 受管区 **1→4**（d62+d63+d65+d68），Property 2 的 D6 单区部分转绿，契约锁死通过。
  `[ ]` **Property 5**（flat 键派生 ≡ 原写法，变异走 nested 必红）：三张 D6 新 sheet 实测
  `aging_layout=None`（sheet 自身无账龄组）⇒ **本判据在本轮无分母**；flat 路径仍只由已接的 D6-2
  承载（上游 D1 spec 的 `TestProperty3ManagedFieldSpecsD6Flat` 已覆盖）。如实登记而非假绿。
  `[ ]` **Property 9**（`useD6CrossSheet`/`useD6EclCalculation` 回写后重算）未写判据。
  `[ ]*` Property 13 真栈同卡点①。
  - Property 2 的 D6 单区部分转绿；Property 5（flat 键派生 ≡ 原写法，变异走 nested ⇒ 必红）
  - Property 9：`useD6CrossSheet` / `D6TabWriteoffCheck` / `useD6EclCalculation` 在回写后正确重算
  - Property 13：D6 整册 materialize + 耗时登记
  - _Requirements: 2.8, 2.9, 6.1_

### 阶段 3：D7 单区两张（nested 路径，与 D6 同批对照）

- [x] 12. `phase5_d7_05_long_term.py` + `phase5_d7_06_related_party.py` 声明 ✅ 2026-09-26
  **D7-5**（真名「账龄1年以上合同负债检查表D7-5」尾带「表」）：8 字段 / **无数据行公式列**
  （9 处公式全在 header/footer）⇒ `formula_columns=()` + `footer_carries_total_formula=True`/
  数据行 11-13 / footer 14 / UUID 列 I。与 D3-5 同型，骨架复制。
  **D7-6**（真名「关联方关系及交易检查表D7-6」，**不是** spec 原写的「关联方合同负债检查」）：
  11 字段 / 1 公式列 F(=C+E-D 期末余额)/ 数据行 12-14 / footer 15 / UUID 列 L。
  新建 `phase5_d7_expansion.py`。
  - `D7-5-rows`(20r×8c/9f) / `D7-6-rows`(31r×11c/15f)；`aging_layout=nested`
  - 📌 D7-5 与 D3-5 同型（同为「账龄1年以上…检查表」、几何逐项相同）⇒ 声明骨架可复制
  - _Requirements: 3.2, 3.3, 3.7_

- [~] 13. D7 单区验收 + 两条账龄路径对照 —— 声明+契约绿，对照与真栈未做
  ✅ 受管区 **1→3**（d72+d75+d76），Property 2 的 D7 单区部分转绿。
  `[ ]` **两条账龄路径对照**（裁决 G2 的落点）：D7-5/D7-6 实测 `aging_layout=None`（sheet 自身无账龄组）
  ⇒ **本轮无 nested/flat 对照分母**；两条路径仍只由已接的 D6-2(flat)/D7-2(nested) 承载。
  如实登记而非假绿 —— 裁决 G2 的对照价值在本轮新增 sheet 上不成立。
  `[ ]*` Property 13 真栈同卡点①。
  - Property 5 的 nested 侧；🔴 **与 Task 11 的 flat 侧对照**：两路径输出差异须能归因到
    `aging_layout` 参数而非别处（裁决 G2 的落点）
  - Property 13：D7 整册 materialize + 耗时登记（受管区 1→2→3）
  - _Requirements: 3.7, 6.1_

### 阶段 4：四组双区（位移链）

- [x] 14. `phase5_d6_06_inspection.py` 声明双区 ✅ 2026-09-26
  🔴 用真实写入方分区键 `D6-6-block1-rows` / `D6-6-block2-rows`（**不用** 零写入点聚合键 `D6-6-rows`）。
  区①本期变动（17 字段 A-Q / 数据 17-30 / footer 31 / UUID **R**）；
  区②期后检查（数据 34-39 / footer 40 / UUID **S**）。🔴 两区 UUID 列必须不同（避免行身份串区）。
  两区共享 `sheet_key="d66-managed"` ⇒ 契约里归**同一** sheets 条目的 tables[]（见 Task 16 的分组修复）。
  - `D6-6-block1-rows` / `D6-6-block2-rows`（`useD6Inspection`）；53r×17c，两区行段 Task 2 实测
  - 🔴 **不得**用聚合键 `D6-6-rows`（零写入点）
  - _Requirements: 2.3_

- [x] 15. `phase5_d6_09_writeoff.py` 声明双区 ✅ 2026-09-26
  真名「减值准备转回、核销检查表D6-9」（**含顿号「、」**）。
  区①转回 `D6-9-reversal-rows`（8 字段 / 数据 14-16 / footer 17 / UUID **I**）；
  区②核销 `D6-9-writeoff-rows`（8 字段 / 数据 20-22 / footer 23 / UUID **J**）。
  🔴 footer marker = **「合  计」**（含两个空格，openpyxl 实测，非纯两字）。
  - `D6-9-reversal-rows` / `D6-9-writeoff-rows`（`useD6WriteoffCheck`）；30r×8c/10f
  - _Requirements: 2.5_

- [x] 16. `phase5_d7_04_analysis.py` + `phase5_d7_07_inspection.py` 声明双区 ✅ 2026-09-26
  🔴 用真实写入方分区键（**不用** `D7-4-rows` / `D7-7-rows` 零写入点聚合键）。
  **D7-4**：区①借方 `D7-4-debit-rows`（4 字段 / 数据 12-15 / 🔴 **footer 16** —— R11「本期借方发生额
  合计」在数据行**之上**是特殊结构，footer 必须取数据区之后的 R16「差异」/ UUID **H**）；
  区②贷方+期末 `D7-4-credit-rows`（7 字段 / 数据 27-36 / footer 37「小计」/ UUID **I**）。
  **D7-7**（真名「合同负债检查表D7-7」）：区①本期 `D7-7-period-rows`（18 字段 / 数据 17-30 /
  footer 31 / UUID **S**）；区②期后 `D7-7-post-rows`（数据 34-39 / footer 40 / UUID **T**）。
  🔴 UUID 列首版写 R/S 撞 `managed_last_col=R`，被 `InstrumentationError` 打红后改 S/T。
  - `D7-4-credit-rows`/`-debit-rows`（43r×8c/32f）与 `D7-7-period-rows`/`-post-rows`（48r×21c/19f）
  - 🔴 **不得**用聚合键 `D7-4-rows` / `D7-7-rows`（零写入点）
  - _Requirements: 3.1, 3.4_

- [~] 17. 四组双区验收（位移链逐组实证）—— Property 3 转绿，Property 4/9 与真栈未做
  ✅ **Property 3 转绿**：D6 受管区 4→8（d66×2 + d69×2）、D7 3→7（d74×2 + d77×2），
  `test_d567_property3_12` 的四条 `*_dual_zone_now_present` 全绿。
  🔴 **三处实测修复**（首版必错，被引擎校验打红后改）：
  ① `_expansion_sheets_payload` **必须按 sheet_key 分组** —— 双区两 spec 共享 sheet_key，
     不分组产生重复条目 ⇒ 契约解析器 `sheet_key 重复` fail-closed；
  ② D7-4 借方区 `footer_row=11→16` —— R11「本期借方发生额合计」在数据行 R12-15 **之上**
     （特殊结构：总计在上、明细在下），引擎要求 footer 严格在数据区之后；
  ③ D7-7 UUID 列 R→**S/T** —— R 是 `managed_last_col`，UUID 必须严格在其右侧。
  `[ ]*` **Property 4 位移链**（上区插行 ⇒ 下区 Table ref 下移 + `_GT_SYNC` footer 重冻结 +
  累积归一化）：接入后 D7-4/D7-7 自动进 `test_sibling_table_ref_row_shift` 参数化清单，
  **2 条红** —— 需真实 instrumentation 注入（Excel Table 实体）才能过，同卡点①。
  `[ ]` Property 9（`useD7CrossSheet`/`useD7Detail` 对 `D7-7-post-rows` 回写后重算）未写判据。
  - Property 3 转绿（D6 3→5、5→6 后 6→8；D7 3→5 后 5→7）
  - 🔴 **Property 4 逐组实证**：上区插行后下区 Table ref 随之下移 + `_GT_SYNC` footer 坐标重冻结
    + verify 累积归一化通过（照 D4-9/D4-20 范式）；依赖前置 D（上游任务 24）
  - Property 9：`useD7CrossSheet` / `useD7Detail` 对 `D7-7-post-rows` 的读取在回写后正确重算
  - Property 13：两家整册 materialize + 耗时登记
  - _Requirements: 2.3, 2.5, 3.1, 3.4, 3.8, 6.1, 7.4_

### 阶段 5：D6-1 / D7-1 审定表

- [x] 18. `phase5_d6_01_adjudication.py` 声明 ✅ 2026-09-26
  **3 区**（🔴 实测值，不照 D1-1/D2-1/D3-1/D5 推演 —— 裁决 G5）：原值 `block1`（数据 R8-12，小计 R13，
  减项 R14，合计 R15）+ 坏账准备 `block2`（R17-21，小计 R22，减项 R23，合计 R24）+ 净值 `block3`
  （R26-30，小计 R31，减项 R32，合计 R33）+ footer（TB R34 / 差异 R35 只 E/I）。
  逐格 mask **230 格**现算（43r×13c / 177 公式 / 密度 **32%**，四循环最高）。
  per-cell 键 `D6-1-adj-{section}-{slug}-{field}`，section ∈ {block1, block2, block3}
  （与前端 `useD6Adjudication` 的 `blockKey` 逐字对齐）。
  🔴 **零 `if is_d6` 分支**：几何全部实例化时传入，框架层 AST 卡点不受影响。
  🔴 登记：前端 block1/block2 有**动态行**（`D6-1-adj-{block}-rowKeys` 可增删），但模板是固定 5 行 ⇒
  声明按 `fixed_rows`（Excel 几何固定，动态性在 JSON store 层面）。
  - 逐格 mask（43r×13c / **177 公式** / 密度 **32%**，四循环里最高）；`sections`/`row_mode` 取
    Task 2 实测值，🔴 不得照 D1-1/D2-1/D3-1/D5 推演（裁决 G5）
  - **不得**在引擎加 `if is_d6` 分支（会让上游框架层 AST 卡点打红）
  - _Requirements: 2.6_

- [x] 19. `phase5_d7_01_adjudication.py` 声明 ✅ 2026-09-26
  **2 区**（与 D3-1 同型，骨架复制）：性质分类（`section_key="nature"`，数据 R8-13 六行，小计 R14，
  减项 R15，合计 R16）+ 账龄分类（`"aging"`，数据 R20-23 四行，合计 R24）+ footer（TB R25 / 差异 R26 只 E/I）。
  逐格 mask **112 格**现算。per-cell 键 `D7-1-adj-{section}-{slug}-{field}`，section ∈ {nature, aging}
  （与前端 `useD7Adjudication` 的 `block` token 逐字对齐）。
  - 逐格 mask（32r×12c/84f）；`sections`/`row_mode` 实测
  - _Requirements: 3.5_

- [x] 20. 两张审定表验收 + 四态状态机 ✅ 2026-09-30（Property 7/8 齐 + 三家 UI 接线；余 2 项 `[ ]*` 外部依赖）
  ✅ 受管区：D6 8→**11 table**（d61-adj 3 sections）、D7 7→**9 table**（d71-adj 2 sections）；
  三张审定表契约全部接入并通过 `assert_contract_file_matches_source()`。
  ✅ Property 6（形态实测）由 Task 7/18/19 的几何断言覆盖（区块数/section_key/行号逐条钉死）。
  🔴 **契约解析器要求每 table ≥1 field** ⇒ 审定表 table 给每 section 一个 `item_name` 锚点 field
  （per-cell 值不走行表 field 路径，走 `checklist_responses` 逐格存取）。
  ✅ **Property 7 已交付（2026-09-30）**：`backend/tests/workpaper_sync/test_d567_property7_cell_mask_vs_template.py`
  （20 passed + 1 skipped）。🔴 **判据口径与 D3-1 不同，且这是必须的**：D3-1 那套
  「`value_source == manual` 且 `value_type == amount` ⇒ 不得 mask」**直接搬过来会产生 30 个假阳**
  （D5-1 main 10 格 + D6-1 block3 20 格 —— 那些格在模板里**真有公式**）。故改为**锚定模板册**
  （`backend/wp_templates/D/*.xlsx`）三向判据：①模板有公式 ⇒ 必须 mask ②模板无公式且字段非
  `computed` ⇒ 必须不 mask（P7 本体）③模板无公式且 `computed` ⇒ 允许 mask（保守）。
  该口径与 D3-1 的**实际状态**自洽（D3-1 区2 的 F 是 `cross_sheet` 却未 mask —— 「派生不可 OO 直写」
  由 `is_oo_writable()` **独立机制**保证，与 mask 是两套机制，不可混为一谈）。
  🔴🔴 **该判据首次运行即抓到并修掉真缺陷（fail-closed，D4-1 同型）**：
    · `D7-1` 区1（nature R8-R13）原声明整行 mask `B-K`，注释称「性质区有 SUMIF cross_sheet 公式」
      —— **模板实测该前提不成立**（B/C/D/F/G/H 全为空），**36 格**手工录入格被锁死；
      表内自证：**同一张表**区2（aging R20-R23）模板形态完全一致，声明却只 mask E/I/J/K。
    · `D6-1` 区1（R8-R12）+ 区2（R17-R21）同型，**60 格**被锁死；
      区3（净值 R26-R30）模板里 B–I 确是 `=B8-B17` 派生公式 ⇒ 整行 mask **正确**，保持不动。
    · `D5-1` 声明与模板**逐格完全一致**（46 == 46，对称差 0）⇒ 无需改动；其「手工金额格」
      分母为 **0**（模板全是 SUMIF），**如实登记空分母**，不硬凑三家口径一致。
    修复后对称差：D5-1 = 0 / D7-1 = 0 / D6-1 只剩 ③ 类允许项 11 格。
    变异验证：H（D7 退回整行 mask）→ 精确点名 36 格红；I（D5 漏掉 B9）→ 精确点名 B9 红。
    登记豁免：D6-1 的 `A17-A21`/`A26-A30` 模板是 `=A8` 镜像公式却未 mask（与框架不变量
    `assert_data_cells_not_masked()`「禁 mask 数据行 editable 列」直接冲突）⇒ 用**可伪证**豁免
    （验证真在 A 列 + 真在数据行 + 真是同列自引用镜像 + 名单无失效条目），不是「写个理由就放行」。
  ✅ **Property 8 四态状态机已接前端（2026-09-30）**，三家 composable + UI 全线贯通：
    · `useD5Adjudication.ts`：3 个派生格（notes/acc ← D5-2 聚合、oci ← D5-4），
      原 `cross !== 0 ? cross : manual` 已替换
    · `useD7Adjudication.ts`：双区 × 两列 = 4 组；修掉两处反模式 ——
      nature 的 `agg ? agg.X : manual`（聚合对象一存在就**无条件**盖掉手工值，三家最激进）
      与 aging 的 `isFromCrossSheet = crossCurrent !== 0 || crossPrior !== 0`（**一个标志管两列**，
      期末一有值就把期初手工值切成 0）
    · `useD6Adjudication.ts`：block1/block2 × 两列；修掉 `map.has(prefix-currentUnadjusted)`
      的**三重**缺陷（空串 remark 也为 true 就掐断上游 / 只看 current 键却决定 prior /
      **与同步器根本不兼容** —— 同步器把派生值落进 stored 后 `has` 恒真 ⇒ 上游取数被自己永久关掉）。
      🔴 block3（净值）**不接**状态机：它是 `block1 − block2` 纯公式区，消费的已是两区**显示值**
      ⇒ 覆盖自动透传（已加判据钉死透传）。
    · 🔴 **降级逻辑上提到共享层**：`shared/dynamicAdjudicationRows.ts` 新增
      `resolvePerCellDerivedState(stored, snap, derived)`，三家共用一份。理由：`snap === null`
      （迁移前存过值的格 / 同步器没跑过）**不能**直接丢给 `resolveCellState` ——
      `resolveCellState(0, null, 100)` 判 S4 ⇒ 显示 stored=0，**上游 100 被吞**；且 per-cell 形态下
      同步器判 S2/S4 会**跳过写 snap** ⇒ snap 永远 null ⇒ 该格**永久**显示 0 且永久标已覆盖、
      **不可自愈**（D1 实测同形回归）。读侧与写侧**必须都走**这个入口，手写第二份谓词两个方向都错。
    · UI：新增**共享**徽标 `shared/DerivedCellOverrideBadge.vue`（S2 黄「已人工覆盖」/ S4 红
      「覆盖·上游已变」+ tooltip 三值并呈 + 「恢复取数」），接入三家 Tab 共 **1+2+4 = 7** 个派生列位。
      不复制 D4 的内联块（9 个列位会复制九份必漂移）；组件只依赖 `cellOverrides[field]` 契约，
      不感知区块/行键语义。
    判据：`d5/d6/d7CellOverrideRender.spec.ts` **59 条** + `d567AdjCellOverrideUi.spec.ts` **15 条**。
    变异验证 7 处全部承重：A 摘降级→2 红 · B/E 不冻结 snap→6 红 · C nature 退回→5 红 ·
    D aging 一标志管两列→3 红 · F 退回 `map.has`→8 红 · G 摘 snap 清理→1 红 · J 摘一个徽标→1 红。
    🔴 **诚实记录**：F 变异下「空串」「同步器落库后」两条**仍绿** —— 同步器会先把空串/旧值规范成
    派生值，掩盖读侧问题 ⇒ 已把这两条定性改为「结果级守卫」而非「反证」，并补一条直接断言
    空串→null 的鉴别判据。鉴别力实在「覆盖检出组」。
    🔴 **顺带修掉一个我自己会引入的缺陷**：`removeDynamicRow` 原不清 `-snap` 键 ⇒ 孤儿快照，
    同名类别日后重现时 `stored=null, snap=旧值, derived=新值` ⇒ 判 S4 显示 0（变异 G 守护）。
  `[ ]*` 整册 materialize 真栈同卡点①（adapter 未注册，代码已改但未真栈实测）。
  `[ ]*` Playwright 实测三家徽标与「恢复取数」的真实交互（待 `start-dev.bat` 环境）。
  - Property 6（形态实测，变异改成 D1-1 的 3 区 ⇒ 必红）/ Property 7（逐格 mask 下 editable）
  - Property 8：反证式 + **跑同步器**的判据；复用 `shared/dynamicAdjudicationRows`，
    **不得**在 D6/D7 侧另写一套
  - S2 标「已人工覆盖」/ S4 三值不自动二选一 / 逐格「恢复取数」
  - 受管区：D6 8→9、D7 7→8（按实测区块数调整）+ 两家整册 materialize + 耗时登记
  - _Requirements: 2.6, 2.8, 3.5, 3.6, 6.1_

### 阶段 6：可行性核 + 前端接线 + 验收

- [x] 21. 三张调整分录汇总表可行性核（**不改生产代码**）✅ 2026-09-26
  证据 `evidence/task21-adjustment-feasibility.json`：D5-3 / D6-4 / D7-3 **三张全判 `single_html`**
  （两门均 FAIL：①模板无行身份列，行身份只在前端 JSON store 的 rowId ②store 键被
  `useAdjustmentCentralSync` → 后端 `AdjustmentSyncService` 中央登记占用，OO 回写会绕过借贷平衡校验）。
  写入方逐个实测：`useD5Adjustment.ts`(`D5-3-rows`) / `useD6Adjustment.ts`(`D6-4-rows`) /
  `useD7Adjustment.ts`(`D7-3-rows`)。
  **D6-7 形态核**：58r×18c / 仅 **7 公式** / 无合计行 ⇒ `static_region` **首选**（与 D4-13 同型：
  大表但无动态行无公式），次选 `paragraph_block_bidirectional`，末选 `single_html`；裁决留给接入任务。
  ✅ **Property 14**：本任务零生产代码改动（只产证据 JSON）。
  📌 七张调整分录汇总表已全部同型确认（D1-5/D2-4/D3-3/D4-4 已判/D5-3/D6-4/D7-3）⇒ 建议统一裁决
  另立 `d-cycle-adjustment-sheets-single-html-adjudication`。
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

- [ ] 22.* 前端接线 + 变异检验 + 真栈 + 证据 —— **本轮零交付**
  🔴 **本轮改动被并发会话覆盖丢失**：曾把三家宿主的 `isD*DetailSheet` 从 `currentSheet === 'D*-2'`
  改为 `SET.has(currentSheet)` + `D*_SHEET_KEY_MAP` 映射表，交付前 `git status` 复核发现三个 Vue
  文件**无 diff** ⇒ 改动已被覆盖。**未重做**（前端工作量不大但需与后端受管清单下发机制一并设计，
  见未完成清单 #2）。三家现状仍是单张写死。
  `[ ]` **Property 15**：受管集合从 provider 派生 + `capability`/`flushHtml` 读 `Ref` —— 未做。
  `[ ]` **Property 1~15 逐条变异**（需求 8.1）—— 未做。
  `[ ]*` **真栈三段**（切在线编辑 → OO canvas 逐值 → 改一格 → forcesave → 回读等值）：
  卡 adapter 未注册（Overview 卡点①）。本轮尝试过手工翻 manifest capability + 离线跑发布链，
  撞 `sync_contract_structure_drift` 后**已回滚 manifest**，如实登记为 `upstream_gap` 而非 failed。
  `[ ]` 证据目录 `docs/operations/evidence/d567-sync-coverage/` 未建（本轮证据落 spec `evidence/`）。
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

### 🔴 本轮未完成清单（下一轮必做，按优先级）

> 🔄 **2026-09-30 更新**：原清单 #1（四态接前端）与 #4（Property 7 判据）**已交付**，见 Task 20 条目。
> 其余各项状态与阻塞原因逐条重核如下。

| # | 欠账 | 归属 Task | 阻塞原因 |
|---|---|---|---|
| ~~1~~ | ~~三家四态状态机接前端~~ | 20 | ✅ **2026-09-30 已交付**：三家 composable + 共享徽标 UI 7 个派生列位；判据 59 + 15 条；7 处变异全部承重 |
| ~~4~~ | ~~Property 7 逐格 mask 判据~~ | 20 | ✅ **2026-09-30 已交付**，但**没照 D3 抄**：D3 口径在 D5/D6 会产 30 个假阳，改为锚定模板册三向判据；顺带修掉 D6/D7 共 **96 格** fail-closed 误锁 |
| 2 | **前端宿主受管集合接线**（三家 `isD*DetailSheet` 仍单张写死；Property 15 要求从 provider 派生 + `capability`/`flushHtml` 改 `Ref`） | 22 | 本轮改动被并发覆盖已丢；需先定「provider 受管清单如何下发前端」（render-config 加字段？新端点？） |
| 3 | **多 item store-projection 注册**（`STORE_ITEM_IDS` + `build_combined_store_projection` + `merge_combined_projection`） | — | 首轮做过但被并发重构覆盖；需裁决它与 `build_orchestration` 配置驱动架构如何共存 |
| 5 | **Property 9 下游重算判据**（各 store 键的 computed 消费方） | 8/11/13/17 | 无阻塞，需逐键写 vitest |
| 6 | **Property 1~15 逐条变异** | 22 | 部分完成：Property 7/8 的变异已做（7 处，见 Task 20）；其余 Property 待逐条 |
| 7 | **Property 4 位移链 2 红** | 17 | 卡 adapter 注册（真实 instrumentation 注入） |
| 8 | **真栈三段** | 22 | 卡 adapter 注册（reviewed overlay + 发布链，属 umbrella Task 36/77） |
| 9 | **Playwright 实测三家徽标/恢复取数交互** | 20 | 待 `start-dev.bat` 环境（代码已改并有 74 条单测，但未真实浏览器实测） |
| 10 | **D6-1 的 A 列镜像公式未 mask**（`A17-A21`/`A26-A30` 模板是 `=A8` 却未 mask） | 20 | 与框架不变量 `assert_data_cells_not_masked()`「禁 mask 数据行 editable 列」**直接冲突**，改任一侧都会动别的判据面 ⇒ 本轮显式登记为**可伪证豁免**，留待框架层裁决 |

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
