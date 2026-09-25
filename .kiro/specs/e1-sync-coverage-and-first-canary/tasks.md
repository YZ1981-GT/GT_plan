# Implementation Plan

## Overview

**spec**：`e1-sync-coverage-and-first-canary`　**创建**：2026-09-25　**复盘修正**：2026-09-25
**实施**：2026-09-26　**状态**：**8/23 完成（声明层）+ 15 项卡 upstream_gap / 未开工**

### 🔴 实施结论（2026-09-26，诚实分层）

**已真做完（有实跑证据，43 用例全绿）**：
Task 0 前置核查（A/B/C 三门全部已入 HEAD）· Task 1 slice 核对（未过期）·
Task 2 形态判定三元组实证 · Task 3 E1-P1 红判据 · Task 7 provider 从零建 ·
Task 8 canary E1-2 声明 · Task 13 E1-4 第二张（验证复用框架层零改动）·
Task 14 E1-11 唯一 static_region 声明。

**卡 upstream_gap 标 `[ ]*`**：Task 9 契约发布链五环的第③环（published representation）是
umbrella BP-61-1 登记的**平台级约束**（`working_paper_sync_entry_state` /
`working_paper_content_version` / `working_paper_content_representation` 三表近空，
**186 个 planned entry 一个都注册不上**）⇒ Task 10~12、15~22 的真栈段全部跑不起来，
如实标注、**不以合成测试冒充真栈**（Task 9 明令）。

**实测推翻 / 补正 spec 四处**（禁推演铁律的实证价值，裁决 H8 从键名扩展到形态后仍有漏网）：

1. 🔴 **E1-2 行身份字段名是 `id`，不是 D 类惯用的 `rowId`**（`useE1CashDetail.ts:104/144/285`
   的 `r.id`）。照抄 D 类会让 store-projection fail-closed 抛「缺稳定行身份」把**整个 entry
   打挂** —— D4-1 曾因 `rowKey`/`rowId` 之误踩过同款（「任何有真载荷的底稿一进在线编辑即 500」）。
2. 🔴 **E1-2 有不可删除的固定行 `fixed-rmb`**（`useE1CashDetail.ts:284` 硬挡 removeRow），
   对应模板 R15 人民币行 ⇒ 本张是「固定行 + 动态行」**混合身份**，两者同在 `id` 字段，
   `row_identity_key='id'` 可同时容纳、**无需拆区**。spec 描述 E1-2 时未提此事。
3. 🔴 **E1-11 的 store 键在 `.vue` 宿主里而非 composable**（`E1TabAccountCommitment.vue` 明写
   「No composable — directly uses allResponses」）。只在 `composables/useE1*.ts` 里 grep 会
   找不到 `E1-account-commit-check-summary` 而误判键名错 —— **搜索范围漏了 `.vue`**（判据已打红此错）。
4. 🔴 **E1-11 的 note/conclusion 用 `E1-commit-` 前缀，主键用 `E1-account-commit`** ——
   **不是**同一前缀派生。照「统一前缀」推演会造出 `E1-account-commit-audit-note` 这种不存在的键
   （判据已把这条反证钉住）。

**E1-P3 自省变异已落地并真打红**（Task 4 第 3 条的核心要求）：判据把「公式数 < 10 ⇒
`static_region`」这条**首版裁决 H3 的错法**复现出来 —— E1-9/E1-10/E1-11 实测各只 7 公式，
该阈值会把三张**全部**误判成静态区；实证只有 E1-11 成立（零 `-rows` 键），E1-9 的键是模板化
`` `E1-cash-count-${variant}-rows` ``、E1-10 是 `E1-account-list-rows`，两张都是动态行表。

**连字符陷阱实证成立**：同一 `useE1CashCount.ts` 里并存 `E1-cash-count-{variant}-rows`（新键）
与 `E1-cashcount-fx-summary-fx`（legacy 兜底键，**无连字符 + 双 `-fx` 后缀**）⇒ 投影须能读到
历史底稿，不得只认新键。

**顺带实证 spec 的「模板治理债」**：`glob('E1-1*')` 会同时匹配到第 2 册（`E1-14至E1-15`），
而第 2 册里确实残留 `货币资金分析表F1-6 (修订前)`（**F1 编号出现在 E 册**）⇒ spec 的顺带发现属实。

**新发现一条接入顺序约束**（spec 未载明，判据已钉）：`static_sheets` 是**寄生**在动态 primary
spec 上的字段 ⇒ 只开静态区而无动态区时 `instrumentation_specs()` 返回空、静态区**无处寄生**。
接入顺序必须**先 canary（动态）再 static_region** —— 这正好解释了 spec 为何把 Task 14 排在
Task 8 之后（原 rationale 只说「验证第二种 BindingKind」，实际还有这条硬约束）。

🔴 **与 D 类 spec 的差异只有一级（复盘修正）**：D 循环 slice 实测显示 7 个独立 entry 里
**只有 D2/D4 真注册了 adapter**，D1/D3/D5/D6/D7 均 `legacy_fake_bidirectional` + `adapter_id=None`
（`unverifiable_reasons` 含 `no_registered_sync_adapter`），**与 E1 同态**。真实差异只有
**provider 文件存在与否** ⇒ 本 spec 的 canary 链路比它们**多一步（建 provider）**，其后的
契约发布链五环 + adapter 注册是**六个循环共同的平台级缺口**（umbrella BP-61-1）。

🔴 **本 spec 是 umbrella `workpaper-html-onlyoffice-bidirectional-writeback-closure` 的
Task 47 下游 lane spec**，与 D4 lane 同型。已存在的上游产物复用不重造：E 循环 slice
（`backend/data/workpaper_sync_e_cycle_manifest_slice.json` 322 行）· 行身份守卫
`e1SyncEntryRowIdentity.spec.ts`（umbrella Property 23）· variant 金额守卫
`e1BankVariantIntegrity.spec.ts`。本 spec 的 `Property N` 一律读作 **`E1-P{N}`**，
引用上游写全 `umbrella Property N`（umbrella 自己踩过 BP 同号不同义的坑）。

消费三个上游：`d1-sync-row-table-engine-and-d1-coverage`（引擎 + **形态谱系三维**）·
`d-cycle-sheet-bidirectional-expansion`（四条纪律）· Phase 5 canary 范式。

**接入顺序形态驱动**（复盘修正后，理由见 design 裁决 H3/H8）：

```
1 (canary E1-2)  →  2 (E1-4 最小行表)  →  3 (E1-11 唯一 static_region)
  →  4 (E1-6)  →  7 (E1-7/8/9 共享 variant)  →  8 (E1-10 首遇 OCR)
  →  9 (E1-3 双 sheet 共享键)  →  10 (E1-1 审定表 + TB 发布门)
  —  E1-5 可行性核，不计入
```

🔴 **首版顺序基于错误的形态判定**（把 E1-9/E1-10/E1-11 三张全判成 `static_region` 强命中，
依据是「各只 7 公式」）。实证只有 E1-11 成立 ⇒ 低风险跳板只剩一张。

## Tasks

### 阶段 0：前置门 + slice 核对 + 形态判定 + 红判据

- [x] 0. 前置依赖核查 ✅ 2026-09-26：git show HEAD 判定前置 A/B/C 三门全部已入 HEAD（框架层+形态谱系三维 / AdjudicationSheetSpec 含 slot_driven+cross_volume / merge._protection 格级判定）；E1 无前置 D。证据 docs/operations/evidence/e1-sync-coverage/e1-form-verdicts.json（**判定用 `git show HEAD:` 不读工作树**）
  - 前置 A：上游框架层 + **形态谱系三维**（`binding_kind` / `row_identity_key` /
    HTML-only item 子集三个声明位）已入 HEAD
  - 前置 B：`AdjudicationSheetSpec` 已交付
  - 前置 C：`merge._protection` 格级判定 + `_mask_spans_data_column` 已入 HEAD
    （E1-1 密度 41% / 193 公式，比 D4-1 的 48 格 mask 风险更大）
  - 🔴 **E1 无前置 D**：与 D3/D567 的 `adapter_registered=False`（有 provider 缺发布链）不同，
    E1 是**连 provider 都没有** ⇒ 需求 1 的 canary 链路本身就是在解除这个前置
  - IF A 未满足 THEN 全部阻塞。IF B/C 未满足 THEN 阶段 6（E1-1）阻塞，其余可推进
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 1. **slice 核对 ✅ 2026-09-26：E 循环 slice 未过期（entry_id / migration_state=legacy_fake_bidirectional / adapter_id=None / profile 与 D1/D2/D3 同型 四项逐字吻合）。🔴 补正：slice 的 independent_entries 条目**不含** parent_duplicate_count / verification_state / unverifiable_reasons 字段（spec 正文引用的那些值来自 umbrella 的 D 循环 slice 对照，非 E 循环 slice 自身）⇒ parent_duplicate 路线裁决的依据应改述为「E 循环 slice 未登记 parent_duplicate」。路线 α 本体（子组件各挂挂载点）归 Task 10 + `parent_duplicate` 路线裁决**（复盘新增，不改生产代码）
  - 🔴 上游 slice 冻结于 umbrella Task 47 执行时，**可能已过期** ⇒ 逐项核对现状与 slice 是否仍一致：
    `entry_id` / `migration_state` / 五个 null 供给位（`adapter_id` / `authority_model` /
    `definition_bundle` / `instrumentation_candidate` / `published_representation`）/
    `scenario_profile_id` / 三条 `manifest_legacy_reasons` / 五条 `unverifiable_reasons`
  - ⇒ 核过之后，需求 1 的 `assert_entry_selectable` 四条事实**不再重新调研**，直接引用 slice
  - 🔴 **裁决 `parent_duplicate_count = 0` 怎么解**（slice 实测 E1 为 0，D4 为 31）：
    D4 每个受管 sheet 在 manifest 里有自己的条目，E1 一条都没有 ⇒「声明层 +1 per sheet」
    在 E1 上**不足以**让 manifest 扫出受管 sheet
  - 两条路线择一并留证：**路线 α**（取此）仿 D4，子组件各挂 `GtOnlyOfficeSheet` ⇒ manifest 产出
    `parent_duplicate` 条目，改动面大但全在前端声明层、工具链全复用；**路线 β**（否决）单挂载点 +
    sheet 维度 entry 扩展，要动 `_entry_id` 派生规则（持久化键，裁决 H2 已否决同类改动）
    且会让 E1 成为全平台唯一例外形态
  - 产出裁决 JSON 落 spec `evidence/`
  - _Requirements: 1.2, 7.3_

- [x] 2. 第一册形态判定 ✅ 2026-09-26：16 sheet 公式数逐张实测（E1-1=193 / E1-2=38 / E1-3 仅人民币=185 与 人民币及外币=567 / E1-4=52 / E1-9=E1-10=E1-11=7）+ E1-2/E1-4/E1-11 三张精确几何逐格实测 + store 键按值 grep（四种命名风格 + 模板化拼接 + legacy 兜底键全部实证）。推翻/补正 spec 四处见 Overview（**三元组实证**）+ 几何实测 + 下游消费方 grep 补全
  - 🔴 **`binding_kind` 判据是前端三元组，不是模板公式数**：
    `(store 键是否存在, addRow/removeRow 信号数, composable 归属)`
  - 实证基线（复盘已查）：**E1-11 是唯一 `static_region`**（零 `-rows` 键，仅
    `E1-account-commit` + `-check-summary`）；**E1-9 / E1-10 是动态行表**
    （`E1-cash-count-cert-rows` / `E1-account-list-rows`）
  - 🔴 首版把三张全判成 `static_region`（依据「各只 7 公式」）已被推翻 —— 模板公式数是 xlsx 侧
    几何量，与前端是否有动态行无因果关系（裁决 H8）
  - 🔴 **`store_item_id` 逐个按值 grep**，E1 有**四种命名风格**：①语义 `E1-cash-detail-rows`
    ②编号嵌套 `E1-ipo-E1-26-rows` ③模板化 `E1-cash-count-${variant}-rows`
    ④无连字符 `E1-cashcount-audit-note-${variant}`。最危险是③④同张并存：E1-8 同时有
    `E1-cash-count-fx-rows` 与 `E1-cashcount-audit-note-fx`，**一个连字符之差**（六次事故背书）
  - ⚠️ **模板化键按字面量 grep `-rows` 查不到**，必须按前缀查（首版因此误记
    「`useE1CashCount` 无 `-rows` 键、形态待核」）
  - 🔴 **E1-1 的 `sections`/`row_mode` 必须实测**，不得照 D1-1/D2-1/D3-1/D4-1 推演。已查明它是
    per-cell + 槽位驱动（`E1_SLOT_ORDER`）+ 三个值来源：本 sheet 人工 / 跨 sheet 聚合
    （`E1-bank-detail-{institution|finance|other}-{opening|total}-unaudited` 6 键取自 E1-3 分组小计）/
    跨册（`E1-accrued-interest-rows` 属**第 3 册**，范围外）
  - 🔴 grep 补全每个键的**下游 computed 消费方**（上游 P18 教训）；已知 `e1RestrictedScope.ts` /
    `useE1AccountList` 读 `E1-bank-detail-rows`；`E1-account-commit-snapshot` 是 E1-10↔E1-11 联动
  - note/conclusion/procedures item 若在 footer 之下，逐项核「footer 下 `static_row` 与插行
    fail-closed 冲突」（`HTML_ONLY_ITEM_IDS_D45` 先例）；**E1-7/8/9 是强候选**（三张各有
    `elements` / `audit-note` / `audit-conclusion` 三个 per-variant 文本键，与 D4-5 形态逐一对应）
  - 产出实测表落 spec `evidence/`，后续任务引用它而非重测
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 4.3, 4.7_

- [x] 3. E1-P1 红判据 ✅ 2026-09-26：slice 实测仍 legacy_fake_bidirectional + adapter_id=None（红形态已记录）；判据若见 adapter_registered 会红并提示更新 spec 状态。转绿归 Task 9（卡 upstream_gap）：canary 未通时 migrationState / reasonCodes 必红
  - 断言 `xlsx/gt-e1-monetary-fund` 的 `migrationState` 为 `adapter_registered` 且三条 reasonCodes
    （`template_only_open` / `no_durable_forcesave_ack` / `missing_adapter`）全消
  - **现状必红**（实测 `legacy_fake_bidirectional` + 三条 reasonCodes 齐在）；记录红的形态
  - _Requirements: 1.5_

- [ ] 4. E1-P2 / E1-P3 红判据：键名实证 + `binding_kind` 三元组（含**自省变异**）
  - E1-P2：断言 `store_item_id` 逐字等于实测值。变异 ①`E1-cash-detail-rows` → `E1-2-rows`
    ⇒ 投影恒空必红 ②`cash-count` → `cashcount` ⇒ 必红
  - E1-P3：断言每张受管 sheet 的三元组 → `BindingKind` 一致；E1-11 唯一 `static_region`
  - 🔴 **自省变异（第 3 条）**：把判据改回公式数阈值（`< 10 ⇒ static_region`）⇒ 三张都会判成
    `static_region`，必红。**这复现的正是本 spec 首版裁决 H3 的错法** —— 判据必须能打红自己的
    历史错误，否则下一轮原样复发
  - 变异 ④：E1-9/E1-10 声明成 `static_region` ⇒ `_plan_static_writes` 绝对坐标直写、插行后坐标
    全错必红；E1-11 声明成行表 ⇒ 会走整条位移链而它没有 Table，必红
  - _Requirements: 1.3, 2.2, 9.2_

- [ ] 5. E1-P8 红判据：公式管理双模式一致性 + E1-P12 零回归基线
  - E1-P8：断言 `open-formula-manager` 事件在**结构化视图与在线编辑两种模式下**都能到达顶层
    全局 `FormulaManagerDialog`。**现状只有 legacy 模式** ⇒ 双模式一致性无从验证，此时必红
  - 🔴 本判据同时钉住「不新建第二个按钮 owner」（`workpaper-page-formula-toolbar-closure`
    需求 1.4/2.4 红线）；E1 是公式管理**范式源头**，本 spec 不改其实现
  - E1-P12：其余 10 个 contract（b60/d1/d2/d3/d4/d5/d6/d7/g7/h1）golden digest 基线（必绿）
  - _Requirements: 6.2, 6.3, 8.3_

- [ ] 6. **E1-P16 / E1-P17 / E1-P18 红判据**（复盘新增三条，D 类 spec 均无）
  - 🔴 **E1-P16 OCR 第二写入方**：E1 有 7 个 `E1*OcrConfirmDialog`（全目录 OCR 提及 **454 次**），
    对 `-rows` 键是**整表替换**语义 ⇒ 与 OO forcesave 构成两个批量写入方。判据：受管 sheet 处于
    OO 编辑态时 OCR 确认入口 `disabled` + 中文原因可见。**D4 范式零 OCR**（d4 目录弹窗 0 个、
    提及 0 次；d5/d6/d7 全 0）⇒ 无先例可抄。变异：去掉 disabled / 改成写完自动 forcesave /
    只在 E1-10 禁用而漏 E1-11（两张各 43 次，成对出现）
  - 🔴 **E1-P17 TB 显式发布门**：E1-1 接 `data-testid="e1-publish-tb"` → `publishToTb`。三条断言：
    ①sync 回写路径对 `trial_balance` 写次数为 **0** ②未点发布前 `trial_balance` 不变
    ③两道既有 CI 守卫 `check_tb_writeback_no_direct_call` / `check_tb_publish_confirm_gate` 保持绿。
    变异：让 merge 顺带写 `trial_balance` / 在 sync 回写里调 `publishToTb`
  - 🔴 **E1-P18 E1-3 列集守恒**：`rmb` 与 `multi` 共用 `E1-bank-detail-rows` 但 `rmb` **不下发**
    原币列。判据：`multi` sheet 上 OO 回写一行后原币列（`fxCurrency`/`fxRate`）逐字不变。
    变异：两张都声明受管同一键 / 投影列集取两 variant 交集。
    与既有 `e1BankVariantIntegrity.spec.ts` 分工：那条守 HTML 侧跨 variant 金额守恒，本条守
    **OO 回写方向**引入的同一后果，两者互相独立地红/绿
  - _Requirements: 2.6, 3.6, 4.6, 9.2_

### 阶段 1：canary 链路（从零打通真双向）

- [x] 7. phase5_e1_monetary_fund.py 从零建 + ssert_entry_selectable ✅ 2026-09-26：ENTRY_ID/ADAPTER_ID/模板哨兵（实测 8317e2ba，145434 bytes，read 时比对）+ assert_entry_selectable（真 manifest 四条事实，require_wp_codes 默认 True 使第四条遗漏必红）+ 第一册 16 sheet 形态清单 + 三个 _INCLUDE_* 灰度开关 + CROSS_VOLUME_KEYS 跨册降级登记（需求 4.5）。12 用例全绿
  - 照 Phase 5 canary 范式（`phase5_d1_notes_receivable` / `phase5_d3_prepaid_receipts` 同构）
  - `assert_entry_selectable` 在**真 manifest + 真 finder** 上核四条事实 + 零回退；前三条由 Task 1
    的 slice 核对供给（entry 存在 / `independent=true` /
    profile == `xlsx.editable.shared.single.room_service_wired.v1` 与 D1/D2/D3 同型），
    **待核第四条**：`wp_code` 落点（查真库该 store 键落哪个 wp_code，照 D3/D5/D6/D7 裁决范式）
  - _Requirements: 1.2_

- [x] 8. phase5_e1_02_cash_detail.py canary 声明（E1-2 现金明细）✅ 2026-09-26：store_item_id=E1-cash-detail-rows（按值 grep）+ 两级表头 R13/R14 + 数据区 R15-21 + footer R22 + 公式列 E/G/I（G 乘法 / I 乘加混合）+ HTML_ONLY_ROWS_E102 登记 footer 下 R23。15 用例全绿，含 E1-P2 两条变异 + E1-P3 自省变异
  - `RowTableSheetSpec`，`store_item_id="E1-cash-detail-rows"`（实测值）；几何取 Task 2
  - 选它作 canary 的理由：34 行 ×22 列 / 38 公式，**且零 OCR、零跨 sheet 取数、键独立**
    —— 第一册里失败面最小的行表
  - _Requirements: 1.1, 1.3_

- [ ]* 9. 契约发布链五环（**任一环缺供给都会静默不注册**）
  🔴 **2026-09-26 如实登记为 `upstream_gap`，未伪装通过**：第③环 published representation 是
  umbrella BP-61-1 的**平台级**约束（`working_paper_sync_entry_state` /
  `working_paper_content_version` / `working_paper_content_representation` 三表近空，
  **186 个 planned entry 一个都注册不上**，连供给最完整的 Excel pilot 也一样；生产者是
  `ContentMutationService.commit(...)` 与 umbrella Tasks 36/77 的 finalize gate）。
  ⇒ E1 与 D1/D3/D5/D6/D7 六个循环卡在同一缺口，**不该在六个 spec 里各自把发布链重做一遍**。
  provider 侧就绪 + 判据先行已完成（Tasks 7/8/13/14）；本任务与其下游 Tasks 10~12、15~22
  的真栈段待 umbrella 解除该缺口后执行。
  - ①`build_contract_payload` → 生成器 `--apply` → `assert_contract_file_matches_source`
    ②approved bundle ③**published representation** ④`entry_state` ⑤`register_from_manifest()`
  - 🔴 判据须**逐环断言产物存在**，不得只看最终 `migrationState` —— 任一环缺供给时
    `register_from_manifest()` 会返回显式 reason 而不注册（D3/D5/D6 的 `adapter_registered=False`
    正是卡在③）
  - ⚠️ 上游 umbrella 的 BP-61-1 记录：`working_paper_sync_entry_state` /
    `working_paper_content_version` / `working_paper_content_representation` 三表长期近空，
    **186 个 planned entry 一个都注册不上** ⇒ 第③环是平台级约束，非本 spec 独有。IF 该约束仍在
    THEN 本任务如实登记为 `upstream_gap` 而非伪装通过
  - Task 3 的 E1-P1 SHALL 转绿（`legacy_fake_bidirectional` → `adapter_registered`，三条 reasonCodes 全消）
  - _Requirements: 1.4, 1.5_

- [ ] 10. 宿主接桥（保留 legacy 给未接 sheet）
  - `GtE1MonetaryFund.vue` 引入 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`，
    **保留** legacy `GtOnlyOfficeSheet`（D1 宿主同款 `v-if` / `v-else-if` 结构）
  - 按 Task 1 裁决的路线 α，受管 sheet 的子组件各挂挂载点以使 manifest 产出 `parent_duplicate`
  - 受管 sheet 集合**从 provider 受管清单派生**，不前端硬编码；`capability` 与 `flushHtml` 读 `Ref`
  - 🔴 覆盖**两套 gating**（`isE1DetailSheet` + 专用同步 sheet 链）—— 漏后者会工具条叠加冲突
    （D4-35/D4-13 踩过）
  - 🔴 未接 sheet 保持 legacy 但**显式登记**它们仍是 `legacy_fake_bidirectional`
    （OO 改动不合并回 store、切回即丢）—— 本 spec 缩小该范围、不掩盖它（E1-P13）
  - 🔴 目录完成度不回归：`E1TabDirectory.vue` 覆盖 19 编号**跨 4 册**，本 spec 只接第一册 ⇒
    须断言未受管 sheet 的完成度仍走 HTML 原路径
  - Task 5 的 E1-P8 SHALL 转绿（公式管理双模式一致）
  - ⚠️ E1 模式切换条选择器**须实测**（`GtE1MonetaryFund.vue:24` 有 `<el-segmented>`，
    与 D4-1 `.sync-mode-bar` / D4-2 `.d4-mode-toolbar` 都不同，照抄会找不到元素）
  - _Requirements: 1.6, 6.2, 8.5, 8.6, 8.7_

- [ ] 11. canary 验收：§9.6 三谓词 + DB 三谓词
  - E1-P4：`confirm 200` / `forcesave cs_error=0` / `store_mirrored` + `marker_visible`；
    DB 留 op / marker / store 键证据
  - E1-P11：整册 materialize 200 + **穿过** `verify_unmanaged_regions` + 耗时登记
  - E1-P12 零回归；E1-P10：`E1-cash-detail-rows` 下游消费方在回写后正确重算
  - 🔴 **本任务是后续全部接入的硬前置**：canary 未通不得声明第二张受管 sheet
    （照 `d-cycle-sheet-bidirectional-expansion` Wave 0→1 顺序纪律）
  - _Requirements: 1.7, 1.8, 2.5, 8.1, 8.3_

- [ ] 12. **批量 e2e 骨架：fixture + seed 脚本**（复盘新增，照搬 D4 lane 范式）
  - 产出 `e2e/fixtures/e1-l2-cases.json` + `e2e/e1-l2-oo-to-html-all.spec.ts` +
    `backend/scripts/e2e/seed_e1_publish_e2e.py`，结构照 D4 lane 的
    `d4-l2-cases.json`(389) / `d4-l2-oo-to-html-all.spec.ts`(541) / `seed_d4_publish_e2e.py`(395)
  - fixture 每 case 字段：`code` / `excel_name` / `sheet_key` / `table_key` / `edit_col` /
    `edit_key` / `edit_vt` / `first_data_row` / `last_data_row`
  - 🔴 **E1 需加两个 D4 没有的字段**：`variant`（E1-3 的 `rmb|multi`、E1-7/8/9 的 `rmb|fx|cert`）
    与 `ocr_dialog`（该 sheet 是否有 OCR 确认弹窗，供 E1-P16 断言）
  - 🔴 **E1 的 seed 必须额外解除 `missing_adapter`**（D4 的 seed 不需要这段，D4 早已注册 adapter）
  - 照搬四条纪律（全部来自 D4 踩过的坑）：**逐张而非批量**（UI forcesave 会卸编辑态；批量多格曾
    触发 `footer_anchor_drift` / conflict）· **只改安全目标**（只改投影里 `|amount| > 1` 且 key 不在
    `SKIP_KEYS` = `seq`/`index`/`row_no`/`no`/`order`/`month` 的金额格；文本/空数据记
    `no_safe_target` 而非硬失败）· **API 直打后端** `http://127.0.0.1:9980` 而非 vite 代理
    （避免代理中途挂掉导致 `page.request ECONNREFUSED`）· **七态结果枚举**
    `applied_store_ok` / `applied_store_miss` / `no_safe_target` / `type_fail` / `op_error` /
    `op_timeout` / `enter_fail`（区分「引擎错」与「该 sheet 无可安全编辑的格」，否则全盘统计会把
    后者误报成失败）
  - _Requirements: 9.3, 9.5_

### 阶段 2：E1-4 最小行表 + E1-11 唯一 `static_region`

- [x] 13. phase5_e1_04_digital.py 声明（E1-4 数字货币，22r 最小行表）✅ 2026-09-26：数据区 R10-16 七行预填序号 / footer R17 / 公式 H/I/K/L（I、L 为乘法）。🔴「复用框架层零改动」已被判据钉死：断言声明模块源码内**无 def / 无 class**（算法全在框架层）
  - `store_item_id="E1-digital-rows"`（实测）；22r×17c/52f
  - 🔴 本张的作用是**验证「第二张复用框架层零改动」** —— 它独立键、零 OCR、零跨 sheet 取数，
    若接它需要改框架层，说明框架层抽象不足，须先回上游 D1 spec 修
  - _Requirements: 2.1_

- [x]* 14. phase5_e1_11_commitment.py 声明 + 验收（**第一册唯一 static_region**）✅ 声明与判据交付（16 用例全绿）：零 -rows 键 / 无 composable（键在 .vue 宿主）/ 承诺函段落表单 / table_name+uuid_col 必空 + defined_name 必填 + row_identity_key 空 / 绕开位移链（无 Table 无 UUID 无 mask）/ OCR 第二写入方登记 / 命名不一致陷阱反证。**验收段卡 upstream_gap**：整册 materialize + E1-P16 OCR 禁用真栈验证 + E1-P11 耗时登记均需 adapter 已注册
  - 零 `-rows` 键，键为 `E1-account-commit` + `E1-account-commit-check-summary`
  - `static_region`：只声明 workbook-scope `defined_name` 锚点，**不建** Excel Table、
    **不注** UUID 列；binding 由 `_static_region_bindings(provider=…)` 自动生成，
    不需手动接线 `sibling_bindings`
  - 参照 D4 实现：`phase5_d4_erp_check_sheet`(D4-13 A6/A16 单 cell) /
    `phase5_d4_product_margin_sheet`(D4-8) / D4-33(72 static cell)
  - 受管区数按 definedName 锚点数计，而非行数
  - 🔴 E1-11 有 **OCR 提及 ×43** ⇒ E1-P16 在本任务须转绿（OCR 确认入口在 OO 编辑态下 disabled）
  - Task 4 的 E1-P3 SHALL 转绿：断言它**不产生** `row_shift`、不经 footer 两门、不注 UUID 列、
    不建 Excel Table ⇒ **绕开整条位移链**；同时断言 E1-9/E1-10 **不是** `static_region`
  - E1-P11 整册 materialize + 耗时登记；E1-P12 零回归
  - _Requirements: 2.1, 2.2, 2.4, 2.6, 8.1, 8.3_

### 阶段 3：E1-6 + E1-7/8/9（共享 composable，variant 参数化）

- [ ] 15. `phase5_e1_06_reconciliation.py` 声明（E1-6 余额调节表）
  - `store_item_id="E1-reconciliation-rows"`（实测）；56r×17c/14f
  - _Requirements: 2.1, 2.3_

- [ ] 16. `phase5_e1_07_08_09_cash_count.py` **一个文件声明三张** + `HTML_ONLY_ITEM_IDS_E1`
  - 🔴 **三张共享 `useE1CashCount`(534) 且只差 `variant` 参数**（`rmb` / `fx` / `cert`）⇒
    `RowTableSheetSpec` 只应差 `variant` 与列集，**不得复制三份** —— 与 D5/D6/D7 共享 33 个同名
    函数、只差 `aging_layout` 一参同范式
  - 键：`E1-cash-count-rmb-rows` / `-fx-rows` / `-cert-rows`；副键 `${storageKey}-summary`
    （E1-7/E1-8 的结转 summary，cert 无）；E1-9 另有 `E1-cert-signatures`
  - ⚠️ **legacy 兜底键 `E1-cashcount-fx-summary-fx`**（双 `-fx` 后缀，历史键，`useE1CashCount:268`
    仍在读）⇒ 投影须能读到历史底稿，不得只认新键
  - 🔴 **产出 `HTML_ONLY_ITEM_IDS_E1`**：三张各有 `E1-cashcount-elements-${variant}` /
    `-audit-note-${variant}` / `-audit-conclusion-${variant}` 三个 per-variant 文本键，与
    `HTML_ONLY_ITEM_IDS_D45` 的 `D4-5-credit-policy` / `-audit-note` / `-audit-conclusion`
    **形态逐一对应**（D4-5 正因此被判 HTML-only：footer 下 `static_row` 与插行 fail-closed 冲突）
  - 受管区 3→6；E1-P11 整册 materialize + 耗时登记
  - _Requirements: 2.1, 2.3, 2.4, 2.5_

### 阶段 4：E1-10 账户清单（首次遭遇 OCR 冲突源）

- [ ] 17. `phase5_e1_10_account_list.py` 声明 + OCR 冲突判据收口
  - `store_item_id="E1-account-list-rows"`（实测）；37r×12c/7f，**但是动态行表不是 static_region**
  - 🔴 **三向联动**：`useE1AccountList`(340) 另读 `E1-bank-detail-rows`（跨 sheet 取 E1-3 账户）
    与 `E1-account-commit-snapshot`（与 E1-11 联动）⇒ E1-P10 须断言这两个下游在回写后正确重算
  - 🔴 **OCR 提及 ×43**，与 E1-11 成对 ⇒ E1-P16 在本任务完整收口（两张都 disabled）
  - ⚠️ E1-3 此时**尚未受管**（排在阶段 5）⇒ 须确认跨 sheet 读 `E1-bank-detail-rows` 在
    「源 sheet 未受管」状态下行为不变
  - 受管区 6→7
  - _Requirements: 2.1, 2.5, 2.6_

### 阶段 5：E1-3 双 sheet 共享键（数据损坏级风险）

- [ ] 18. E1-3 同编号双 sheet 可行性核 + 裁决（**不改生产代码**）
  - 🔴 D 类**从未出现**此形态：`(仅人民币)` 92r×28c/185f 与 `(人民币及外币)` 89r×**41c**/**567f**
    （全平台单 sheet 公式最多），而前端只有一个 `E1-bank-detail-rows`
  - 🔴 **复盘已把风险从「待裁决」升级为数据损坏级**，实证：
    `useE1BankDetail.ts:9` `BankDetailVariant = 'rmb' | 'multi'` ·
    `E1TabBankDetail.vue:35` variant 由 sheet 名推导 · `useE1BankDetail.ts:61`
    `VARIANT_KEY='E1-bank-variant'`（variant 选择本身被持久化）· `useE1BankDetail.ts:110`
    注释明写「两 variant 字段集不同是 AC 1.9 的意图」，`rmb` 版**不下发**原币列
    （`fxCurrency`/`fxRate`）
  - ⇒ 两张同时受管时，OO 在 `rmb` sheet 上 forcesave 回写整行会把 `multi` 侧原币列写成缺省/抹零
    —— **正是既有守卫 `e1BankVariantIntegrity.spec.ts` 在守的缺陷形态**，OO 回写只是从第二个
    方向引入同一后果
  - **默认裁决：只接 `(人民币及外币)` 一张**（`multi` 是列集超集、`rmb` 是其投影子集，接超集不丢列），
    `(仅人民币)` 保持 legacy 并显式登记。IF 将来要两张都接 THEN 硬前置是**先把
    `E1-bank-detail-rows` 拆成两个键**（或引入 per-variant 列集投影），而**不是**让引擎支持
    「一 store item 投影到两张列集不同的 sheet」
  - 另须实测：项目实例化时是否两张都出现（若按客户有无外币二选一实例化，则只接对应那张）
  - E1-P5：裁决先于声明且不改生产代码；变异核阶段改了 provider ⇒ 必红
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6_

- [ ] 19. E1-3 按裁决结果声明 + 验收
  - Task 6 的 E1-P18 SHALL 转绿：`multi` sheet 上 OO 回写一行后原币列逐字不变
  - IF 选中 `(人民币及外币)` THEN 其逐格 mask 规模须实测登记（567 公式 / 41 列）；
    IF mask 覆盖数据区之外的行 THEN 须确认 `merge._protection` 格级判定已入库，
    否则受管金额字段会被整列误判只读（D4-1 踩过的坑）
  - ⚠️ 本张受管后，E1-10 的跨 sheet 读与 E1-1 的 6 个聚合键（
    `E1-bank-detail-{institution|finance|other}-{opening|total}-unaudited`）**源头变为受管** ⇒
    须回归 Task 17 的 E1-P10
  - 受管区 7→8 + 整册 materialize + 耗时登记
  - _Requirements: 3.4, 3.6, 8.1_

### 阶段 6：E1-1 审定表（193 公式 / 密度 41% + TB 发布门）

- [ ] 20. `phase5_e1_01_adjudication.py` 声明 + 四态覆盖状态机 + **TB 发布门守卫**
  - `AdjudicationSheetSpec`；逐格 mask（47r×10c / **193 公式** / 密度 **41%**）；
    `sections`/`row_mode` 取 Task 2 实测值，🔴 不得照 D1-1/D2-1/D3-1/D4-1 推演
  - **不得**在引擎加 `if is_e1` 分支（会让上游框架层 AST 卡点打红）
  - 四态状态机复用 `shared/dynamicAdjudicationRows.resolveCellState` /
    `displayValueForCellState`，**不得**在 E1 侧另写一套
  - 🔴 **三个值来源必须分别声明，派生格不可由 OO 侧直接写**（否则 OO 回写覆盖聚合结果）：
    本 sheet 人工（`E1-adj-diff-note` / `E1-adj-total-note` / `E1-adj-{item}-opening-unadj`）·
    跨 sheet 聚合（`E1-bank-detail-{institution|finance|other}-{opening|total}-unaudited` 6 键，
    取自 E1-3 分组小计 `useE1BankDetail:80-90`）· 跨册（`E1-accrued-interest-rows` 属**第 3 册**，
    范围外 ⇒ 须定义「第 3 册未受管」时的降级行为，**不得**因缺失把该格判成空或 0）
  - 槽位顺序取 `E1TabAdjudication.vue` 的 `E1_SLOT_ORDER` 常量，不另定义
  - 🔴 **Task 6 的 E1-P17 在本任务转绿**（TB 显式发布门）：①sync 回写路径对 `trial_balance`
    写次数为 0 ②未点 `e1-publish-tb` 前 `trial_balance` 不变 ③两道 CI 守卫
    `check_tb_writeback_no_direct_call` / `check_tb_publish_confirm_gate` 保持绿。
    **这是第一次「受管 sheet 与 TB 发布门落在同一张底稿」**，D 类四个 spec 均无此条
  - **E1-P9 反证式先写**：只改 `derived` 不改 `stored`/`snap` ⇒ 覆盖标记数必须为 0；
    🔴 另须一条**跑同步器**的判据（上游 13 条纯函数判据全绿而生产坏掉的教训）
  - S2 标「已人工覆盖」/ S4 三值不自动二选一 / 逐格「恢复取数」
  - E1-P6（形态实测）/ E1-P7（逐格 mask 下受管金额字段仍判 `editable`）转绿
  - 受管区 8→9（按实测区块数调整）+ 整册 materialize + 耗时登记
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 8.1_

### 阶段 7：可行性核 + 收口

- [ ] 21. E1-5 调整分录汇总可行性核 + 裁决（**第八张同型，不改生产代码**）
  - 已实证：`E1TabAdjustment.vue` 接 `useAdjustmentCentralSync` ⇒ 经后端 `AdjustmentSyncService`
    中央登记；`E1-adjustment-rows` 是 hub store；模板 26r×10c / 仅 7 公式
  - 待核：借贷平衡不变式是否仅 HTML 侧强制 / 有无行身份列
  - 照 `T08-d44-single-html-adjudication.json` 范式落证据；默认倾向 `single_html`
  - E1-P14：核阶段不改任何生产代码；变异改了 provider ⇒ 必红
  - 📌 **八张调整分录汇总表全部同型**（D1-5/D2-4/D3-3/D4-4 已判/D5-3/D6-4/D7-3/**E1-5**）
    ⇒ 建议统一裁决另立 **`cycle-adjustment-sheets-single-html-adjudication`**
    （🔴 去掉原建议的 `d-` 前缀 —— E1-5 证明它不只是 D 类问题）；IF 已立 THEN 降级为引用其结论
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 22.* 变异检验 + 真栈 + 证据登记
  - E1-P1 ~ E1-P18 逐条变异并记录打红条数；未能打红的重写而非保留
  - 🔴 **十条变异清单**见需求 9.2 表，其中第 3 条是**自省变异**（把 `binding_kind` 判据改回公式数
    阈值 —— 复现本 spec 首版裁决 H3 的错法）
  - 真栈：跑 Task 12 的 `e1-l2-oo-to-html-all.spec.ts` 全盘逐张 —— 切「在线编辑」→ OO canvas
    逐值断言 → 改一格 → forcesave → 回读结构化视图等值。`--workers=1`。达 §9.6 三谓词 + DB 三谓词
  - 🔴 三陷阱沿用上游结论：不能用 `page.on('response')` 判 callback（须读后端
    `application_bound_at`）；不能用 `asc_*` API 写格（须真实键盘输入 `#ce-cell-name` →
    `keyboard.type` → Enter）；**模式切换条选择器须实测**（E1 是 `<el-segmented>`，
    与 D4 两套都不同）
  - 🔴 **公式管理双模式判据必跑**（E1-P8）—— D 类 spec 都没写（它们的宿主没有公式管理入口）
  - 🔴 **OCR / TB 发布门 / E1-3 列集三条必跑**（E1-P16/17/18）—— 本 spec 独有
  - 三端点耗时复测；证据落 `docs/operations/evidence/e1-sync-coverage/`，数字脚本现测
  - _Requirements: 6.2, 8.1, 9.1, 9.2, 9.3, 9.4, 9.5_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门先于一切 —— 上游框架层与形态谱系未入 HEAD 则 E1-11 的 static_region 声明只能退回行表" },
    { "wave": 1, "tasks": ["1"], "rationale": "slice 核对 + parent_duplicate 路线裁决 —— 上游 slice 已冻结大量事实，须先核它是否过期；E1 的 parent_duplicate_count=0（D4 为 31）是接入机制的结构性前置，不裁决则声明层加 sheet 也扫不出受管 sheet" },
    { "wave": 2, "tasks": ["2", "3", "4", "5", "6"], "rationale": "形态判定（三元组实证）+ 五组红判据，互不依赖可并行；Task 6 的三条（OCR/TB门/E1-3列集）是复盘新增、D 类 spec 均无。全部红判据此时必红是后续归因依据" },
    { "wave": 3, "tasks": ["7"], "rationale": "provider 从零建 + assert_entry_selectable，前三条事实由 Task 1 的 slice 核对供给" },
    { "wave": 4, "tasks": ["8"], "rationale": "canary sheet 声明依赖 Task 2 实测几何与 Task 7 的 provider 骨架" },
    { "wave": 5, "tasks": ["9"], "rationale": "契约发布链五环 —— 任一环缺供给都会静默不注册；第③环 published representation 是 umbrella BP-61-1 登记的平台级约束" },
    { "wave": 6, "tasks": ["10"], "rationale": "宿主接桥依赖 adapter 已注册，并按 Task 1 裁决的路线 α 让 manifest 产出 parent_duplicate；同时使公式管理双模式一致性可验证" },
    { "wave": 7, "tasks": ["11", "12"], "rationale": "canary 验收门与批量 e2e 骨架可并行 —— fixture/seed 不依赖验收结果，但验收是后续接入的硬前置" },
    { "wave": 8, "tasks": ["13"], "rationale": "E1-4 最小行表验证「第二张复用框架层零改动」；若需改框架层说明上游抽象不足" },
    { "wave": 9, "tasks": ["14"], "rationale": "E1-11 唯一 static_region —— 验证第二种 BindingKind，同时首次收口 OCR 判据（该张 OCR 提及 43 次）" },
    { "wave": 10, "tasks": ["15", "16"], "rationale": "E1-6 与 E1-7/8/9 互不依赖可并行；后者三张合一个声明文件（共享 useE1CashCount、只差 variant），并产出 HTML_ONLY_ITEM_IDS_E1" },
    { "wave": 11, "tasks": ["17"], "rationale": "E1-10 首次遭遇 OCR 冲突源完整收口；其跨 sheet 读的 E1-3 此时尚未受管，须确认行为不变" },
    { "wave": 12, "tasks": ["18"], "rationale": "E1-3 裁决必须先于声明 —— 两 variant 共用同一 store 键但列集不同，是数据损坏级风险，D 类从未出现此形态" },
    { "wave": 13, "tasks": ["19"], "rationale": "E1-3 声明与验收；受管后 E1-10 跨 sheet 读与 E1-1 的 6 个聚合键源头变为受管，须回归 E1-P10" },
    { "wave": 14, "tasks": ["20"], "rationale": "E1-1 审定表最后 —— 依赖前置 B/C、Task 2 的区块数实测、以及 E1-3 已受管（6 个聚合键的源头）；同时收口 TB 显式发布门" },
    { "wave": 15, "tasks": ["21"], "rationale": "E1-5 可行性核独立于接入链，排在其后以免「不改代码」纪律与接入改动混淆归因" },
    { "wave": 16, "tasks": ["22"], "rationale": "变异与真栈收口，需全部行为已落地" }
  ],
  "blocking": {
    "0": "上游框架层与形态谱系三维未入 HEAD ⇒ 全部阻塞；AdjudicationSheetSpec/_protection 未入库 ⇒ 阶段 6 阻塞",
    "1": "slice 未核对 ⇒ 可能基于过期事实开工；parent_duplicate 路线未裁决 ⇒ 声明层加 sheet 也不会被 manifest 扫出（E1 为 0 条，D4 为 31 条）",
    "2": "形态与键名未实测 ⇒ 声明只能推演。E1 有四种命名风格（语义/编号嵌套/模板化/无连字符），且 cash-count 与 cashcount 一字之差（六次事故背书）；binding_kind 若按公式数推演会把 E1-9/E1-10 误判成 static_region",
    "3": "E1-P1 未先打红 ⇒ Task 9 的「migrationState 转 adapter_registered」不可归因",
    "4": "E1-P2/E1-P3 未先打红 ⇒ 键名推演与形态误判这两个最易犯的错没有可执行判据；缺自省变异则首版裁决 H3 的错法会原样复发",
    "5": "E1-P8 未先打红 ⇒ 公式管理双模式一致性在接桥后无对照；E1-P12 基线未取 ⇒ 零回归无分母",
    "6": "E1-P16/17/18 未先打红 ⇒ OCR 第二写入方、TB 发布门、E1-3 列集三条 D 类无先例的风险无判据兜底",
    "7": "provider 未建 ⇒ 后续全链无载体；assert_entry_selectable 未过 ⇒ 选型门未守，可能接错 entry",
    "9": "发布链任一环缺供给 ⇒ register_from_manifest() 静默不注册；第③环是 umbrella BP-61-1 的平台级约束，若仍在须如实登记 upstream_gap 不得伪装通过",
    "11": "canary 未通 ⇒ 不得声明第二张受管 sheet（上游 Wave 0→1 顺序纪律）；此时全部扩容阻塞",
    "18": "E1-3 未裁决 ⇒ Task 19 不知声明一张还是两张，且两张同时受管会抹零 multi 侧原币列",
    "20": "E1-3 未受管 ⇒ E1-1 的 6 个跨 sheet 聚合键源头未定；跨册键降级行为未定义 ⇒ 会把该格误判成空或 0"
  }
}
```

## Notes

### 已裁决（详见 design §关键裁决）

- **H1**：E1 是 canary 不是扩容，前半段必须走完整发布链；canary 未通不得接第二张
- **H2**：只覆盖第一册（5 册 / 56 sheets，一宿主一 entry）；后四册需新宿主另立
- **H3**（复盘已修正）：接入顺序**形态驱动**，但**只有 E1-11 是 `static_region`** ——
  首版按「各只 7 公式」把 E1-9/E1-10/E1-11 三张全判成 `static_region` 强命中，实证推翻两张
- **H4**（复盘强化）：E1-3 两 variant 共用 `E1-bank-detail-rows` 但**列集不同**，
  默认**只接 `(人民币及外币)`**；两张都接前须先拆键
- **H5**：**公式管理不改** —— E1 是范式源头（`D4TabOtherMargin.vue:32` 明写「同 E1 范式」，
  D4 是抄它的）；本 spec 只加两条判据（双模式一致 + 不新建第二个按钮 owner）
- **H6**：E1-5 是第八张同型调整分录表 ⇒ 统一裁决 spec 建议去掉 `d-` 前缀
- **H8**（复盘新增）：「禁推演」铁律适用面从**键名**扩展到**形态** —— `store_item_id` 按值 grep、
  `BindingKind` 按前端三元组、`row_identity_key` 按真跑一次，三项都不得几何推演
- **H9**（复盘新增）：E1-1 受管后 TB 回写**仍只经** `publishToTb` 显式门，sync 回写路径
  不得触达 `trial_balance`
- **H10**（复盘新增）：**OCR 是 E1 独有的第二写入方**（7 个确认弹窗 / 454 次提及；D4 为 0），
  受管 sheet 在 OO 编辑态时 OCR 入口禁用，不做无溯源的三方合并

### 🔴 两个「公式」概念不在一层，不得混淆

```
公式管理        wp_formula 表 / workpaper scope / 全局弹窗   审计师维护的跨底稿取数公式
formula_mask   契约声明 / 逐格或列向区间                    模板里的 Excel 内部公式
```

本 spec 只碰后者。「参照 D4 实现公式管理」易被读成要改前者 —— 实测 E1 侧已完整且 D4 是抄它的。

### 复盘查明的正面事实（无需修复）

`E1TabDirectory.vue` 声明 19 编号 × note/conclusion = **38 键，逐键反查写入方零缺失** ——
与 D6/D7 的四键零写入（`D6-6-rows`/`D6-8-rows`/`D7-4-rows`/`D7-7-rows`，底稿目录完成度恒「未填」）
正好相反 ⇒ 本 spec **不需要** D567 spec Task 1 那类修复。

⚠️ 反向教训：其中 10 个是模板化键（`-${variant}` 形态），按全字符串 grep 会误报成零写入。
**查「零写入键」时必须同时匹配模板化拼接**，否则会造出不存在的 bug。

### 顺带发现（登记，不在本 spec 处理）

**E 循环模板治理债**（比 D6/D7 各 1 张残留严重得多）：E0 函证册 **9 张**残留/参考 sheet
（含 `邮件传真回函核对记录F1-12` / `核实被函证单位信息F1-10-原` —— **F1 编号出现在 E0 册**）·
**`E0-5` 编号重复两张** · `货币资金分析表F1-6 (修订前)` 在 E1-14 册里。建议模板治理单独立项 ——
这些残留会让 sheet 分派正则、generated 映射、将来的受管清单都面临「同名 / 异循环编号」歧义。

**`E1TabDisclosure.vue` 2063 行**是 `e1/` 下最大组件，`E1TabDirectory` 的 19 个编号里**没有它**
⇒ 它对应两张附注披露 sheet（62r×10c / 153~158 公式，本 spec 范围外），但完成度未进目录，
建议与模板治理一并核。
