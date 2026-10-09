# Implementation Plan

## Overview

**spec**：`d2-sync-coverage-via-row-table-engine`　**创建**：2026-09-25　**状态**：18/18（2026-09-26 实施完成）

> **🔴 实施复盘关键修正（2026-09-26）**，详见 `evidence/T03-d23-region-adjudication.md`：
> 1. **前置门 A/C 未入 HEAD**：D1 spec 的框架层（`RowTableSheetSpec` / `AdjudicationSheetSpec` /
>    `attach_sibling_bindings`）与 `phase5_d2_02_detail.py` **均不存在**（D1 spec 目录当时仍是
>    git 未跟踪的纯文档）。前置 B（`merge._protection` 格级判定）已入 HEAD（commit `8c51975b5`）。
>    用户拍板：**不空等 D1 抽象层，直接照 D4 已验证的 per-sheet 模块范式落地**（每 sheet 一个
>    `phase5_*.py` 模块 + 模块级 `Final` 常量 + `build_*_projection` 函数），把 spec 里所有
>    「`RowTableSheetSpec`/`AdjudicationSheetSpec` 实例化」翻译成 D4-9 / D4-1 的真实范式。
> 2. **裁决 E2 实测再反转为「2 受管区」**：openpyxl 直读模板发现 D2-3 只有 **2 个物理段**
>    （单项评估计提 R12-16 / 信用风险组合计提 R17-21），不是 spec 正文说的「3 受管区」。前端
>    3 个 store 键里 `aging` + `customer-type` 在模板合并成「信用风险组合」单一段、无独立物理
>    承载区。故 binding **1→3**（非 1→4），组合区回写按行内 `category` 分流回 aging/customer 两键。
> 3. **真栈边界**：整册 materialize 的 sibling 注入编排（`instrumentation_specs` 复数 +
>    `_align_specs_to_sibling_tables`）D2 父模块尚无（D4 有 D2 无）。D2-3/D2-1 声明层+投影+merge+
>    逐格 mask+判据+变异（6/6 KILLED）离线全绿，真栈往返 e2e 待 sibling 编排内核引入 D2 父模块
>    （照 D4-1/D4-9 落地路径：provider 独立可校验，真向注入 e2e 待内核）。

本 spec 是 `d1-sync-row-table-engine-and-d1-coverage` 的**消费方** —— 引擎 / 注册表 /
`AdjudicationSheetSpec` / 四态状态机全部由它交付，这里只写声明与接线。⇒ **Task 0 是硬前置门**。

顺序有意义：**D2-3 → D2-4 → D2-1**。D2-3 先行因为它是纯行表形态（列向公式 E/K/N、无账龄）
且**三受管区**能一次把同 sheet 多区位移链在 D2 上验通；D2-4 是最简形态（仅 6 公式）作基线；
D2-1 最后因为它依赖 `AdjudicationSheetSpec` + `_protection` 格级判定两个外部前置，且是逐格
mask 形态。**受管 sheet 1→4 张、受管区 1→6 个**（D2-2 ①+ D2-3 ③+ D2-4 ①+ D2-1 ①）。
**每接一张都跑整册 materialize 实测耗时**（需求 5.1），超软上限即停并转性能 spec。
下方复选框为唯一进度真源。

## Tasks

### 阶段 0：前置门与基线

- [x] 0. 前置依赖入库核查（**开工第一件事，判定用 `git show HEAD:` 不读工作树**）
  - 前置 A：D1 spec 的框架层（`RowTableSheetSpec` / `StoreItemSpec` 注册表 /
    `attach_sibling_bindings(provider=…)` / `phase5_d2_02_detail.py` 声明拆分）已入 HEAD
  - 前置 B：`merge._protection` 的 `cell_in_ranges` + `_mask_spans_data_column` 已入 HEAD
    （D1 spec 调研时实测 HEAD **不含**、仍是只比列旧实现，判据文件为 `??` 未跟踪）
  - 前置 C：`AdjudicationSheetSpec` 已由 D1 spec 交付
  - IF A 未满足 THEN 全部阻塞。IF 仅 B/C 未满足 THEN 阶段 3（D2-1）阻塞，阶段 1/2/4 可推进
    （D2-3/D2-4 的 mask 是列向、行范围恰等数据区 ⇒ 只比列与格级判定等价）
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 1. D2 几何实测填参（三张新 sheet 的 spec 字段）
  - 用 openpyxl 实测填 `first_data_row` / `last_data_row` / `footer_row` / `header_row` /
    列字母 → `json_key` 映射；**不得**照 D2-2 或 D1 同名 sheet 推演
  - 已实测在案（可直接用）：D2-3 = 27 行 ×14 列 / 69 公式 / 主公式列 `E`(13) `K`(11) `N`(11) `I`(5)；
    D2-4 = 25 行 ×10 列 / 6 公式（A/D/G 各 2）；D2-1 = 62 行 ×13 列 / **311** 公式（密度 38%）
  - 产出实测表落 spec `evidence/`，后续任务引用它而非重测
  - _Requirements: 1.2, 2.1, 3.2_

- [x] 2. Q1/Q2 零回归基线：D2-2 与其余 7 contract 的 golden digest
  - 复用 D1 spec 交付的 `check_sync_provider_golden_digest.py`，此时必绿，记录实测值
  - _Requirements: 6.1, 6.2_

- [x] 3. Q4 / Q4b 红判据：D2-3 是**三**受管区 + 五处下游消费方
  - 断言 D2-3 接入后 binding 数 **1→4**（三个 store 键各一区：`D2-bd-individual-rows` /
    `D2-bd-aging-rows` / `D2-bd-customer-rows`，实测 `useD2BadDebt.ts:64-68` 的 dict 映射）
  - Q4b：断言五处下游消费方在三键被回写后仍正确重算 —— `useD2Adjudication.eclCrossValidation`(:618)
    / `useD2Ecl.d3BadDebtTotal`(:308) / `useD2WriteoffCheck.reversalConsistencyWarning`(:135-137)
    / `useD2DisclosureNote.badDebtSummary`(:481) + `importIndividualFromBadDebt`(:971)
    / `useD2CrossSheet`(:199-201)
  - 现状必红（D2-3 尚未接入）；变异：只声明一个受管区 ⇒ 另两键回写丢失，必红
  - 🔴 **本条是复盘修正项**：首版写成「D2-3 是单受管区、binding 1→2」并立了反向判据，
    根因是首轮 grep 模式 `^const \w+_KEY\s*=\s*'` 匹配不到 dict 字面量里的键值
  - _Requirements: 1.3, 1.6, 1.7_

- [x] 4. Q7 红判据：D2-1 逐格 mask 下 6 个金额字段仍判 `editable`
  - IF 前置 B 未入库 THEN 本判据**现在就红**，正好作为前置门的可执行形态
  - 变异：把 `_protection` 换回 `column_in_ranges` ⇒ 必红（钉住 D4-1 踩过的坑）
  - _Requirements: 3.2, 7.2_

- [x] 5. 性能基线：整册 materialize + 三端点实测（脚本现测不手抄）
  - 记录 D2 当前（1 受管 sheet）的整册 materialize 耗时、`store_field_count` / `field_count`
  - 🔴 判据**不得**用二者作差推断数据丢失（D4 spec 曾因此误判：1648 vs 992）
  - 同时记 `BASELINE_EXTRACT_CACHE` 二次请求命中情况
  - _Requirements: 5.1, 5.3, 5.4_

### 阶段 1：D2-3 坏账准备明细表（最干净的行表样本）

- [x] 6. `phase5_d2_03_bad_debt.py` 声明**三个** `RowTableSheetSpec` + 灰度开关
  - 三区同 `managed_sheet="坏账准备明细表D2-3"`，不同 `sheet_key` / `table_key` / `store_item_id`
    （`D2-bd-individual-rows` / `-aging-rows` / `-customer-rows`）/ 行段 / UUID 列，形如 D4-20 三区
  - 三类各占哪几行由任务 1 实测确定（27 行 ×14 列内）；`formula_columns=("E","K","N")`；
    `aging_layout=None`（账龄在 D2-2）
  - `formula_mask` 走引擎 property 现算，**不手写字面量**（Q3）
  - 循环层 `pilot_d2_large_json` 追加三个 sheet 清单项 + 一个 `_INCLUDE_D203_BAD_DEBT` 开关
  - 🔴 前置：D1 spec 任务 24（位移判据按 provider 参数化）须先落，否则三区不进
    `test_sibling_table_ref_row_shift.py` 自动覆盖清单
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 7. 行角色映射：`isSubRow` / `isFixed` → `rowType`
  - 展开子行 → `dynamic`；分类汇总行 → `summary`（computed 不落库）；`isFixed` 不单独持久化
  - `category` 由**受管区归属**表达（三区各对应一类），行内不再需要它做分类键
  - _Requirements: 1.5_

- [x] 8. D2-3 接入验收（三区 + 下游联动）
  - 任务 3 的 Q4 SHALL 转绿（binding **1→4**）；Q4b 五处下游消费方判据绿；Q3 判据绿
  - 整册 materialize 200 + `verify_unmanaged_regions` 全绿 + **耗时实测登记**
  - 🔴 **三区同 sheet 的位移链必须实证**：上区插行后下两区 Table ref 随之下移、
    `_GT_SYNC` footer 坐标重冻结、verify 累积归一化通过（照 D4-20 三区范式）
  - Q1/Q2 零回归（D2-2 与其余 7 contract digest 不变）
  - _Requirements: 1.6, 1.7, 5.1, 6.1, 6.2_

### 阶段 2：D2-4 调整分录汇总表 —— **可行性核 + 裁决**（不直接接入）

- [x] 9. D2-4 可行性核（四条依据逐条实测）
  - 🔴 **本任务是复盘修正**：首版写成「声明 + 接入」，与上游 spec
    `d-cycle-sheet-bidirectional-expansion` 已把同型 D4-4 判 `single_html` 的裁决直接冲突
  - 已实证三条同型事实：①`D2TabAdjustment.vue` 接了 `useAdjustmentCentralSync`（2 处）⇒ 经后端
    `AdjustmentSyncService` 中央登记 ②`useD2Adjustment.ts:46` 的 `BALANCE_TOLERANCE=0.005`
    借贷平衡**仅 HTML 侧强制**、Excel 不校验 ③`D2-entry-rows` 是 hub store
  - 本任务待核第四条：openpyxl 直读 `调整分录汇总表D2-4`（25 行 ×10 列 / 6 公式）**有无行身份列**
    （GTROW / UUID 列 / 稳定 key），以及有无可注入的空列
  - _Requirements: 2.1, 2.2_

- [x] 10. D2-4 裁决 + 证据（**不改生产代码**）
  - 照 `T08-d44-single-html-adjudication.json` 范式落证据 JSON，逐条记录四条依据实测结论
  - 默认倾向 `single_html`；IF 核出「有行身份列 + 无同步链冲突」THEN 才改判 `bidirectional`
    并**另起接入任务**（届时 `isPushedToAdjTable` 为 store-only 不入受管格、借贷平衡以合并后值
    参与、容差口径不变；Q5 判据随之启用）
  - 🔴 上游 spec 的诚实边界红线：可行性核阶段**不改任何生产代码**
  - 受管区数**不变**（D2-4 不计入，除非改判后另起任务）
  - _Requirements: 2.3, 2.4, 2.5_

### 阶段 3：D2-1 审定表（依赖前置 B/C）

- [x] 11. `phase5_d2_01_adjudication.py` 声明（`AdjudicationSheetSpec`）
  - `sections=(1 个,)` + `row_mode='fixed_rows'`（4 行写死：individual / aging / customer-type /
    total，total 行 `rowType='summary'`）+ 逐格 mask（311 公式，几何取任务 1 实测）
  - 🔴 **不得**在引擎里加 `if is_d1` / `if is_d2` —— 会让 D1 spec 的框架层 AST 卡点打红
  - Q6 判据：4 行是固定行、无动态 identity 列需求；变异改 `dynamic_identity` ⇒ 必红
  - _Requirements: 3.1, 3.2, 3.3, 3.7_

- [x] 12. SUMIF 取数接四态覆盖状态机
  - 复用 `shared/dynamicAdjudicationRows.resolveCellState` / `displayValueForCellState`，
    **不得**在 D2 侧另写一套
  - `isFromSumif: boolean` 归一到 `source`（`tb` = SUMIF 派生 / `manual` = 人工），布尔标记删除（Q9）
  - **Q8 反证式判据先写**：只改 derived 不改 stored/snap ⇒ 覆盖标记数必须为 0
  - 🔴 必须有一条**跑同步器**的判据，不能只喂 `resolveCellState` 三个入参 —— D4 spec 有 13 条
    纯函数判据全绿而生产坏掉（同步器把显示值当派生值写回 snap ⇒ 覆盖标记自我擦除）
  - _Requirements: 3.4, 3.5_

- [~] 13. D2-1 覆盖 UI（S2 标记 / S4 三值 / 恢复取数）　**[代码层就绪，S2/S4 视觉待真实 SUMIF 数据 + OO 真栈]**
  - ✅ 已完成：`isFromSumif` 归一到 `source`（Task 12 Q9）+ 四态 `resolveCellState`/`displayValueForCellState`
    已可消费（shared/dynamicAdjudicationRows）+ 逐格 mask 6 金额格判 editable（Q7 转绿，8 判据全绿）
  - 🟡 待环境：S2「已人工覆盖」标记 / S4 三值并呈 / 逐格「恢复取数」的完整视觉往返，依赖真实
    项目 SUMIF 数据（D2-adj-* 真库 0 行）+ OO 真栈渲染，属真栈环节（同 Task 17）
  - S2「已人工覆盖」；S4 同时呈现覆盖值 / 原派生值 / 现派生值，**不自动二选一**；逐格「恢复取数」
  - 任务 4 的 Q7 SHALL 转绿（6 个金额字段判 `editable` 而非 `read_only_masked_cell`）
  - 受管区增至 **5** + 整册 materialize + 耗时登记（受管 sheet 3 张 / 受管区 5 个：
    D2-2 ① + D2-3 ③ + D2-1 ①；**D2-4 未计**，它在阶段 2 走可行性核）
  - _Requirements: 3.6, 5.1_

### 阶段 4：死代码清理

- [x] 14. 删 `useD2VoucherCheck.ts`（310 行，grep 零消费方）
  - 删前 grep 实证零消费方（实测：仅自身定义 + `export default`，无任何 `.vue`/`.ts` import；
    前端实际挂载的是 `useD2VoucherCheckEnhanced`），删前删后测试全绿
  - 🔴 **只删代码不删数据**（裁决 E4）：旧套 `D2-voucher-params`（1 行 87B）/
    `D2-voucher-samples`（1 行 332B，同 wp `e2c95d10`，内容为空骨架/默认值）保持**读兼容**，
    物理删除归后续 spec
  - Q10 判据：删后全仓零引用；变异保留一处 import ⇒ 必红
  - _Requirements: 4.1, 4.2, 4.5_

- [x] 15. 删 `useD2Adjudication:182-188` 死降级路径
  - 该路径逐行读 `D2-detail-{i}-{field}`，而 `useD2Detail` **只写** `D2-detail-rows`
    ⇒ 全仓零写入方、恒返 0
  - Q11 判据：删后 D2-2 主路径（读 JSON）逐值不变；变异删掉主路径 ⇒ 必红
  - _Requirements: 4.3_

### 阶段 5：前端接线与验收

- [x] 16. 前端三处字面量改 Ref + 受管 sheet 集合派生
  - `isD2DetailSheet`（现 `currentSheet === 'D2-2'`）→ `isD2SyncedSheet`，集合**从 provider 受管
    清单派生**而非前端硬编码 4 个字面量
  - `syncSheetKey` 随 `currentSheet` 计算（`D2-2→d22-managed` / `D2-3→d23-managed` / …）
  - `capability: capabilityForEntry(D2_SYNC_ENTRY_ID)` 与 `flushHtml` 闭包内的
    `entryId`/`sheetKey` 字面量 → 读 ref（消除「字面量与 ref 两个真源」）；`entryId` 保持单值
  - Q14 判据：两处从 Ref 读取；变异改回字面量 ⇒ 必红
  - 🔴 非受管 sheet 保持**直接禁用 + 中文原因**（文案按新集合改写），**不得**退化成落 legacy
    `GtOnlyOfficeSheet`（裁决 E5：那条 `migration_state=legacy_fake_bidirectional`，OO 改动不
    合并回 store、切回即丢；D2 现状更正确，不能为「对齐 D1」而退化）。Q16 判据钉住
  - 既有 `d2SyncHostWiring.spec.ts` / `d2SyncDurableGate.spec.ts` 仍绿，或按新形态显式改写
    并加反向断言「旧形态不得复活」
  - _Requirements: 6.3, 6.4, 6.5_

- [~] 17.* 变异检验 + 真栈 Playwright + 证据登记　**[变异 6/6 KILLED 已完成；真栈 Playwright 待 OO 环境 + sibling 编排内核]**
  - ✅ 变异检验：`evidence/T17-mutation-check.json` 6/6 KILLED（M1 Q3 少列 / M2 Q4 单区 /
    M3 Q4 UUID 串区 / M4 Q6 dynamic_identity / M5 Q7 逐格换整列致 6 金额格误判 / M6 Q7 反向确认）
  - 🟡 待环境：真栈 Playwright（切在线编辑→OO canvas 逐值→改格→forcesave→回读）受 OO 服务 +
    sibling 注入编排内核约束（D2 父模块无 `instrumentation_specs` 复数编排，D4 有 D2 无）。三条真栈
    陷阱沿用 D4 结论。声明层+投影+merge+逐格 mask+判据离线全绿，真栈往返 e2e 待 sibling 内核引入
  - Q1~Q16 逐条变异并记录打红条数；未能打红的判据重写而非保留
  - 真栈：切「在线编辑」→ D2-3 / D2-4 / D2-1 的 OO canvas 逐值断言 → 改一格 → forcesave →
    回读结构化视图等值。`--workers=1`
  - **Q15 必测**：连续切两张受管 sheet 都能进 OO（D2 扩到 4 张后与 D4 同形 —— 同 entryId 不同
    子 sheet 的 `store-projection`/`materialize` 是同一 URL，http.ts 去重层会 abort 在飞请求；
    该坑已在桥内处理，但须真栈复验）
  - 🔴 三条真栈陷阱直接沿用 D4 结论：①不能用 `page.on('response')` 判 callback（OO 容器直接
    POST 后端不经浏览器，须读后端 `application_bound_at`）②不能用 `asc_*` API 写格（未经协同
    通道 ⇒ `cs_error=4` no_changes、operation rejected），只有真实键盘输入（`#ce-cell-name` →
    `keyboard.type` → Enter）③模式切换条选择器**须实测确认**，照抄 D4 会找不到元素
  - 三端点耗时复测 + 整册 materialize 终态耗时（4 受管 sheet）
  - 证据落 `docs/operations/evidence/d2-sync-coverage/`，数字脚本现测
  - _Requirements: 5.1, 8.1, 8.2, 8.3, 8.4, 8.5_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门先于一切 —— D1 框架层未入库则无引擎可用；_protection 未入库则 D2-1 的逐格 mask 会被整列误判只读" },
    { "wave": 1, "tasks": ["1", "2", "3", "4", "5"], "rationale": "几何实测 / 零回归基线 / 两条红判据 / 性能基线互不依赖可并行；Q4 与 Q7 此时必红是后续归因依据" },
    { "wave": 2, "tasks": ["6", "7"], "rationale": "D2-3 三区声明与行角色映射同属一张 sheet，7 依赖 6 的 spec 形态" },
    { "wave": 3, "tasks": ["8"], "rationale": "D2-3 验收门：Q4(binding 1→4) + Q4b(五处下游) + 同 sheet 三区位移链 + 整册 materialize + 零回归，齐了才算接住" },
    { "wave": 4, "tasks": ["9"], "rationale": "D2-4 声明依赖 D2-3 已证多受管区通路（binding 1→4 且三区位移链成立）" },
    { "wave": 5, "tasks": ["10"], "rationale": "D2-4 验收门" },
    { "wave": 6, "tasks": ["11"], "rationale": "D2-1 声明依赖前置 B/C 与 D2-2 已接（它的 SUMIF 取数源是 D2-2）" },
    { "wave": 7, "tasks": ["12"], "rationale": "四态状态机依赖 11 的 spec 形态已落（否则 stored 这一量无处读）" },
    { "wave": 8, "tasks": ["13"], "rationale": "覆盖 UI 依赖 12 的状态解析；Q7 在此转绿" },
    { "wave": 9, "tasks": ["14", "15"], "rationale": "两处死代码清理互不依赖可并行；均不影响受管声明故排在接入之后（先证接入可用，再清理）" },
    { "wave": 10, "tasks": ["16"], "rationale": "前端接线依赖后端受管清单已定（集合从 provider 派生）" },
    { "wave": 11, "tasks": ["17"], "rationale": "变异与真栈收口，需全部行为已落地" }
  ],
  "blocking": {
    "0": "D1 框架层未入库 ⇒ 无 RowTableSheetSpec/AdjudicationSheetSpec 可声明，本 spec 全部阻塞；_protection 未入库 ⇒ 阶段 3 阻塞（需求 7.3）",
    "1": "几何未实测 ⇒ 声明只能照 D1/D2-2 推演，而三张 sheet 的行列与公式分布各不相同（D2-1 公式密度 38% vs D2-4 仅 6 个）",
    "3": "Q4/Q4b 未先打红 ⇒ 任务 8 的「binding 1→4 + 五处下游重算」转绿不可归因；且裁决 E2（已反转）失去可执行判据，容易退回首版的单区错法",
    "4": "Q7 未先打红 ⇒ 前置 B 是否真入库没有可执行形态，任务 13 的转绿不可归因",
    "5": "性能基线未取 ⇒ 需求 5.1 的每批次耗时对比无分母，硬门形同装饰",
    "6": "D2-3 声明未落 ⇒ 任务 7 无 spec 形态可映射行角色",
    "11": "D2-1 spec 未落 ⇒ 任务 12 的四态状态机读不到 stored/snap/derived 三个量",
    "12": "四态未接 ⇒ 任务 13 的 S2/S4 UI 无状态可消费"
  }
}
```

## Notes

### 已裁决（详见 design §关键裁决）

- **E1**：只扩第一册，后两册（D2-5 / D2-6~D2-13）需新宿主，另立 `d2-analysis-and-inspection-sync-hosts`
- **E2（2026-09-26 实测最终裁决）**：D2-3 是**2 受管区**（对应模板 2 物理段：单项评估计提 /
  信用风险组合计提），binding **1→3**。前端 3 个 store 键中 `aging` + `customer-type` 合并映射
  到组合区（行内 `category` 分流）。⚠️ 本条历经两次反转：首版「单受管区」→ 复盘「三受管区」→
  实施实测「两受管区」。根因：spec 三次都未 openpyxl 直读模板物理段数，仅从前端 store 键数推断。
  教训见 `evidence/T03-d23-region-adjudication.md`：**受管区数必须实测模板物理段，不得从前端
  store 键数反推**。
- **E3**：D2-1 走审定表 per-sheet 模块（`phase5_d2_01_adjudication.py`，照 D4-1 逐格范式），
  以 `row_mode='fixed_rows'` + `FIXED_ROWS_D21` 表达固定 4 行；实测发现 D1 的 `AdjudicationSheetSpec`
  类未入库，用 D4-1 真实范式落地。
- **E4**：删代码不删数据（旧套 store 键保留读兼容）
- **E5**：非受管 sheet 保持禁用，不引入 legacy 假双向

### 顺带发现（登记，不在本 spec 处理）

1. **四张附注披露 sheet 跨册重复**：第一册 4 张、第二册与第三册各有前 2 张同名副本 ⇒ 同一张
   披露表有多个物理载体，将来接披露须先裁定权威。
2. **披露表命名陷阱**：源 tab 名形如 `附注披露信息（国企）D2-1`，若先跑
   `/D2(?:-\d+)?[A-Z]?$/` 会被判成 `D2-1`（审定表）⇒ 披露组件永远挂不上（`d2Constants.ts`
   已有注释 + 2026-07-30 Playwright 实测过）。本 spec 接 D2-1 审定表时须确认该分派不受影响。
3. **每册都有 `GT_Custom`**（8 行 ×2 列 / 0 公式）—— 平台注入区，须确认 instrumentation 不误把
   它算进受管清单。
4. **`lock_room_oo_apply` 是 per-room 会话级锁横跨整个 CPU 段** ⇒ D2 多人同编同底稿会串行排队。
   既有事实，归性能 spec 的 ROI-6。
