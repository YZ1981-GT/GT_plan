# Requirements Document

## Introduction

D4 循环的**其他业务收入组**四张底稿 —— **D4-33（其他业务毛利率分析表）、D4-34（其他业务收入合同测算表）、D4-35（其他业务收入检查表）、D4-36（其他业务收入截止性测试）** —— 与主营收入组（D4-13~20）同族，但治理状态落后一代：主营组已历经两个姊妹 spec（`d4-inspection-writeback-formula-io` 覆盖 D4-13/14/15/16，`d4-cutoff-return-writeback-formula-io` 覆盖 D4-17/18/19/20）完成「导入导出修复 + A13 双向回写 + 公式引擎接线」治理，**其他收入组四张表一张都没接**。

本 spec 治理三块能力缺口，参照 **D2-2 双向回写**（`workpaper-html-onlyoffice-bidirectional-writeback-closure` 的 html ↔ excel 双模式回写门控纪律）与 **D4 现有 spec** 的范式：

1. **双向回写（html ↔ excel 双模式）**：四张表现在都有「在线编辑」模式内嵌 `GtOnlyOfficeSheet`（excel 侧）与 html 结构化视图，**各自独立持久化**——excel 侧改动经 OO 保存落 `onlyoffice/` 目录的 xlsx，html 侧落 `checklist_responses`，**两侧互不感知、互不回写**。审计师在 OO 里改了一列收入，回到 html 视图看不到。D2-2 已解决的范式是「写侧成功才确认、反向只读校对绝不反写、fail-closed 可见报错」。
2. **公式管理（单一真源 + 用户二次编辑）**：D4-33 各业务类型的毛利率、D4-34 租赁/咨询两区的合同测算差异、D4-35 异常率、D4-36 跨期判定与跨期天数，全部在各组件内联散写；`useD4FormulaEngine` 里的 `calcGrossMarginRate`/`calcSubtotal`/`calcAnomalyRate`/`isCrossPeriod`/`calcCrossPeriodDays` **要么已实现却未被消费，要么语义与前端不一致**（详见现状表 D4-33 行）。用户要求的公式治理语义是「**预设一个基础上允许用户二次编辑**」——引擎纯函数是默认口径（真源），用户可对**本项目的本底稿**存覆盖公式，覆盖值必须在**表格显示、A13 回写金额、导入导出往返**三处口径完全一致。
3. **导入导出**：后端 `_SHEET_HEADERS` 对四张表**全部登记了中文列头**（D4-33 14 列 / D4-34 12 列 / D4-34-rental 10 列 / D4-34-consult 9 列 / D4-35 18 列 / D4-36 12 列 / D4-36-forward 11 列 / D4-36-backward 11 列），但 import/export 分发对四张表**全部落到 generic 兜底**（`_parse_generic_row` + `[data_row.get(h) for h in headers]`，`grep _parse_d4_3[3456]` 零命中），与前端英文 key / 嵌套结构彼此读不通；且 **item_id 全部错位**——后端兜底 `f"{sheet}-rows"` 而前端真实键是 `D4-33-data` / `D4-34-data` / `D4-35-data` / `D4-36-data`，导入落库后前端读不到、导出从空 map 读也是空 ⇒ 「有按钮实则断裂」的死链路。

### 🔴 一个前置发现：`useD4OtherGroup.ts` 是死代码

`audit-platform/frontend/src/components/workpaper/composables/useD4OtherGroup.ts`（9.5KB，声明 `OtherMarginRow`/`OtherContractRow`/`OtherCheckRow`/`OtherCutoffRow` 四套类型，持久化键 `D4-33-rows`/`D4-34-rows`/`D4-35-rows`/`D4-36-rows`）**grep 全库零消费者**——四个组件（`D4TabOtherMargin.vue`/`D4TabOtherContract.vue`/`D4TabOtherCheck.vue`/`D4TabOtherCutoff.vue`）全部自持 `ref` + 自写 `persistAll`，用的是 `D4-33-data`/`D4-34-data`/`D4-35-data`/`D4-36-data`。这是「假绿第①源」（additive 注入即死代码）的活样本：文件注释还写着「Task 15.1」「Requirements 15.1-15.8」，看起来像已交付。按平台铁律**死代码立即删除**（Requirement 1 AC9），不得留 DEPRECATED 注释供下轮再提议。

### 范围与非目标

- **不动** OnlyOffice 自身的 OOXML 写入与 `TB()`/`WP()` 公式运行时求值（另一套机制）。
- **不改** 四张表的源模板字段结构与业务语义：字段清单以组件现有 `BizType`/`RentalRow`/`ConsultRow`（D4-33/34）/ `CheckRow` + `SamplingParams`（D4-35）/ `CutoffForwardRow`+`CutoffBackwardRow`（D4-36）为准，严禁自造检查维度。
- **不把** 四张表金额聚合回 `trial_balance`：D4-33 是**分析表**（无审定金额列），D4-35/36 是**核查/取证底稿**（抽凭金额、跨期金额是取证金额不是审定金额）；D4-34 的 `diff` 是合同测算差异（应收尽收的差异），回写目标统一为 **A13 未更正错报** + **D4-1 审计说明**，与 D4 姊妹 spec 一致。
- **不复制** D2 的「底稿→附注 `sync-from-workpaper` 推送」链路：四张表 `note_workpaper_sync_registry.json` 零命中、无独立附注章节。仅借鉴 D2-2 的四条门控纪律（写侧/读侧分离 · 反向校对绝不反写 · 写成功才确认 · fail-open 不得掩盖接线错误）。
- **不重复** 姊妹 spec 已完成的 D4-13/14/15/16/17/18/19/20 修复。

### 🔴 现状实证（逐文件核实，非推断）

| 表 | 前端组件 / 真实持久化键 | 后端 `_SHEET_HEADERS` | import/export 分发 | item_id 错位 | 双向回写 | 公式 |
|---|---|---|---|---|---|---|
| **D4-33** 其他毛利率分析 | `D4TabOtherMargin.vue`；`D4-33-data`（`{bizTypes:[BizType]}`，**嵌套对象非数组**，每 `BizType` 含 12 月 `months[]` + `priorMonths[]`）/ `D4-33-note` / `D4-33-conclusion` | ✅ 已登记 14 列（月份 + 合计-收入/成本/毛利率 + 三业务类型各 3 列） | 🔴 走 `else`→`_parse_generic_row`；且**后端 export 有 `D4-33` 专属分支（预填 16 行：12 月+合计+上年数+变动额+变动比例）但 import 分发无对应分支** ⇒ 导出模板与导入解析不对称 | 🔴 `D4-33-rows` ≠ `D4-33-data` | ❌ 无（毛利率异常无出口） | ❌ **内联 `calcGrossMarginRate` 用「小数比率」口径**（`revenue-cost)/revenue`），引擎同名函数返回**百分比**（`*100`）⇒ 直接换用引擎会造成 100 倍偏差，且 `.auto-calc` 用的是 D4-19 旧样式（非蓝本 `.auto-calc-col`） |
| **D4-34** 合同测算 | `D4TabOtherContract.vue`；`D4-34-data`（**单 item_id 装两区**：`{rentals:[RentalRow], consults:[ConsultRow]}`）/ `D4-34-note` / `D4-34-conclusion` | ✅ 已登记 `D4-34`(12) / `D4-34-rental`(10) / `D4-34-consult`(9)；前端下拉三入口：`D4-34-rental` / `D4-34-consult` | 🔴 两区都走 generic ⇒ 英文 key 对中文列头读不通 | 🔴 后端兜底 `D4-34-rental-rows` / `D4-34-consult-rows` ≠ 前端单一 `D4-34-data` ⇒ **导入后前端读不到**；且主 `D4-34`(12 列) 在组件**无对应入口**（前端只用 `-rental`/`-consult` 两个子键）⇒ 死配置 | ❌ 无（`diff !== 0` 的差异无出口） | ❌ 内联 `diff = pn(actualRevenue) - pn(expectedRevenue)`（本地 `pn` 而非引擎 `parseNum`）；`.auto-calc` 旧样式 |
| **D4-35** 抽凭检查 | `D4TabOtherCheck.vue`；`D4-35-data`（**嵌套 `{rows, sampling, periodAmount}`**）/ `D4-35-note` / `D4-35-conclusion`；`CheckRow` 16 字段（含 6 个 `check1..check6`）；`isAnomalous` 是 **string**（`是`/`否`/`''`）非 boolean | ✅ 已登记 18 列 | 🔴 走 generic ⇒ 嵌套结构 vs 通用行读不通 | 🔴 `D4-35-rows` ≠ `D4-35-data` | ❌ 无（`isAnomalous==='是'` 无出口） | ❌ 内联 `anomalyCount`（`filter(r=>r.isAnomalous==='是')`）与 `checkRatio`，未用引擎 `calcAnomalyRate`/`calcCoverageRate`（引擎已有） |
| **D4-36** 截止性测试 | `D4TabOtherCutoff.vue`；`D4-36-data`（两区：`{forward:[CutoffForwardRow], backward:[CutoffBackwardRow]}`）/ `D4-36-note` / `D4-36-conclusion`；forward 11 字段（`voucherDate/voucherNo/voucherProduct/voucherQty/voucherAmount/docDate/docNo/docProduct/docQty/docAmount`）+ backward 11 字段（`doc*` 在前、`voucher*` 在后，**与 forward 顺序相反**） | ✅ 已登记 `D4-36`(12) / `D4-36-forward`(11) / `D4-36-backward`(11) | 🔴 走 generic；且 backward 的列头顺序与 forward 相反，generic 按列序取会**交叉错位** | 🔴 后端兜底 `D4-36-forward-rows` / `D4-36-backward-rows` ≠ 前端单一 `D4-36-data`；主 `D4-36`(12 列) 组件无入口 ⇒ 死配置 | ❌ 无（跨期疑点无出口） | ❌ 内联跨期判定 + 跨期天数 + 调整建议汇总（`otherCutoffSummary` 同型逻辑），未用引擎 `isCrossPeriod`/`calcCrossPeriodDays`/`calcSubtotal` |

> 蓝本参照：`useD4InspectionWriteback.ts`（**已存在且可复用**，`pushToA13(items, accountCode='6001', accountName='营业收入')` + `appendToD41Note`，走 `a13:push-misstatement` 形态 C，空项不 emit 且给中文提示）；`_d4_import_export.py` 的 D4-15/16/22/23 专用分支（`_parse_d4_XX_row` + 专用 export 行构造 + item_id 映射表）为**唯一可照抄的范式**；`useD4FormulaEngine`（纯函数库，`parseNum`/`calcSubtotal`/`calcProportion`/`calcGrossMarginRate`/`calcAnomalyRate`/`calcCoverageRate`/`isCrossPeriod`/`calcCrossPeriodDays`）；`useD4ImportExport`（三端点，四张表前端均已接入调用）。
> 反向参照（D2-2 双模式回写）：**只借鉴门控纪律**——html 与 excel 双模式各自可写，但**任一模式的保存必须产生一次显式的结构化数据同步动作**，同步失败必须 fail-closed（可见错误 + 不标记已同步），读侧只读校对发现差异时**只能提示、不得自动反写另一侧**（防双写冲突）。四张表的「在线编辑」模式已挂载 `GtOnlyOfficeSheet`，本 spec 补的是**OO 保存→结构化回读**这一段。

### 术语与判据约定（跨表统一）

- **可推送判据**：D4-33 = 某业务类型**合计毛利率**超阈值（预设默认 ±20 个百分点，需覆盖层可调）**或** 毛利率变动的**变动率绝对值超阈值**（默认 30%）；D4-34 = `diff !== 0`（应收尽收与实计不一致，两区各自判据，`diff` 符号不折叠）；D4-35 = `isAnomalous === '是'`；D4-36 = `isCrossPeriod === true`（跨期疑点，`×`）。
- D4-33 为定性风险，只有在人工认定具体金额与方向后才可进入 A13；不得固定推送 `amount: 0`。D4-34 保留 `diff` 符号并由人工认定，不使用 `abs(diff)`。D4-35/36 不把凭证或单据全额直接等同错报金额。
- **科目口径**：四表统一 `accountCode: '6051'`（其他业务收入），`accountName: '其他业务收入'`——**注意不是主营的 `6001`**，与 D4-33~36 属 6051 科目一致（这是与姊妹 spec 的唯一科目差异，守卫必须断言，防照抄 D4-13~20 时把 `6001` 抄过来）。
- **公式真源**：`useD4FormulaEngine` 的纯函数是**默认公式**（真源）；用户二次编辑覆盖按 `(wp_id, sheet_code, formula_key)` 三元组存 `checklist_responses` 的 `remark`（item_id = `{sheet}-formula-override`），**不新增数据库表**。
- **派生值不参与往返**：导入导出只搬运录入字段，派生值（毛利率/合计/差异/异常率/跨期判定/跨期天数/调整建议汇总）由公式引擎+覆盖层重算。
- **口径冲突先裁决**：D4-33 现有内联毛利率是**小数比率**、引擎 `calcGrossMarginRate` 返回**百分比**，两者差 100 倍。本 spec 裁决见 DEC-2（统一到引擎的百分比口径，前端展示处补 `%` 后缀），**不在组件里做局部 `*100` 打补丁**。

## Requirements

### Requirement 1: 四张表导入导出修复（item_id 全部错位 + 嵌套结构全部不匹配）

**User Story:** 作为审计师，我把 D4-33/D4-34/D4-35/D4-36 导出的数据带回来后，表格要真的显示导入的行，而不是全表读空或导入后前端毫无反应。

#### Acceptance Criteria

1. WHEN 后端导入 D4-33 THEN 必须新增专用 `_parse_d4_33_row(row, actual_headers)`，按后端既有 export 的 16 行形态（12 月 + 合计 + 上年数 + 变动额 + 变动比例）**逆向解析**回 `BizType[]` 嵌套结构：行首列识别业务类型名（空行/合计行归入上一业务类型），落库必须写回 `{bizTypes: [...]}` 而非数组；**导出模板与导入解析必须对称**（当前 export 有专属分支而 import 无，是明确的不对称缺陷）
2. WHEN 后端导入/导出 D4-34 THEN 必须新增 `_parse_d4_34_rental_row` 与 `_parse_d4_34_consult_row` 两个专用 parser + 对应 export 行构造，`RentalRow`（`tenant/period/area/unitPrice/contractRef/actualMonths/expectedRevenue/actualRevenue/indexRef`）与 `ConsultRow`（`client/project/duration/contractAmount/contractRef/expectedRevenue/actualRevenue/indexRef`）逐字段映射；落库必须**合并写回同一个 `D4-34-data`** 的 `{rentals, consults}`（不得覆盖另一区：导入 `-rental` 时必须保留既有 `consults`，反之亦然）
3. WHEN 后端导入/导出 D4-35 THEN 必须新增 `_parse_d4_35_row` 与专用行构造，`CheckRow` 16 字段（含 `check1..check6` 六个核对列）逐字段映射，`isAnomalous` 保持 **string** 语义（`是`/`否`/空），**不得**转 boolean；落库必须写回 `{rows, sampling, periodAmount}` 嵌套形态，其中 `sampling`（抽样参数 6 字段）与 `periodAmount` 走**独立通道**（不由行导入覆盖，保持既有值——否则导入一批凭据会把抽样设计冲掉）
4. WHEN 后端导入/导出 D4-36 THEN 必须新增 `_parse_d4_36_forward_row` 与 `_parse_d4_36_backward_row`，**必须按列头名（而非列序）映射**——backward 的 xlsx 列头顺序（单据在前、凭证在后）与 forward 相反，按位置取会交叉错位；落库必须**合并写回同一个 `D4-36-data`** 的 `{forward, backward}`（不得覆盖另一区）
5. WHEN 后端 item_id 映射 THEN 必须在 `_d4_import_export.py` 新增 `elif` 分支，把 sheet → item_id 映射固定为 `D4-33` → `D4-33-data`、`D4-34-rental`/`D4-34-consult` → `D4-34-data`、`D4-35` → `D4-35-data`、`D4-36-forward`/`D4-36-backward` → `D4-36-data`（**改后端映射，不改前端键**——前端键已被组件内 watch/persistAll/onBeforeUnmount 多处引用，后端四个 `-rows` 键当前零消费者）；文本区（`-note`/`-conclusion`）不走导入导出通道
6. WHEN 主 sheet 死配置 THEN 必须从 `_SUPPORTED_SHEETS` 与 `_SHEET_HEADERS` 中**删除** `D4-34`（12 列）与 `D4-36`（12 列）两个组件无对应入口的死配置（前端只用 `-rental`/`-consult` 与 `-forward`/`-backward` 子键），并断言删除后前端下拉不含该入口；**禁止**继续走 generic 静默落错键
7. WHEN 后端解析金额类字段 THEN 必须走 `_safe_float` 兜底（千分符/空串），且 D4-35 的 `amount`（string 类型，`'约 12%'` 之类非数值可能出现在其他列）**空串必须保持空串而非写 0**
8. WHEN 导入导出往返 THEN 四张表的录入字段必须逐字段一致；派生值由公式引擎重算，不参与往返比对（D4-33 的合计/毛利率/变动额/变动比例、D4-34 的 `diff`、D4-36 的 `isCrossPeriod`/`crossPeriodDays`/调整建议）
9. WHEN 交付 THEN 必须删除死代码 `audit-platform/frontend/src/components/workpaper/composables/useD4OtherGroup.ts`（grep 全库零消费者，键位 `D4-33-rows` 等与真实键 `D4-33-data` 全不符，注释仍标「Requirements 15.1-15.8」属误导性的假绿样本），**不留 DEPRECATED 注释**；删除后必须 grep 确认无残留 import

### Requirement 2: 双向回写 —— html ↔ excel 双模式数据同步

**User Story:** 作为审计师，我在 D4-33~36 的「在线编辑」模式（OnlyOffice）里改完数据保存后，回到 html 结构化视图能看到同一份数据；反向我改完 html 视图，excel 侧也是最新的。两侧不要各存一份互相不知道。

#### Acceptance Criteria

1. WHEN 四张表任一表在 excel（在线编辑）模式保存成功 THEN 必须触发一次显式的「excel → html」结构化同步，把 OO 侧最新行列数据回读到对应 item_id（`D4-33-data`/`D4-34-data`/`D4-35-data`/`D4-36-data`），并走既有 `d4:save-items` 通道落库
2. WHEN excel → html 同步失败 THEN 必须 fail-closed：给中文可见错误提示（不得静默）、**不得**把该表标记为「已同步」、html 视图保持改动前状态并明确提示「excel 侧改动未同步，请重试」
3. WHEN html → excel 反向 THEN 必须提供「同步到在线编辑」入口（工具条按钮，与「导入导出 ▾」并列），把当前结构化数据推送给 OO 侧；**该入口只允许人工触发，禁止在 html 保存时自动静默反写 excel**（防双写冲突）
4. WHEN 双向同步后存在差异（两侧数据不一致）THEN 只读校对应给出差异提示（哪些行/字段不一致），**禁止自动覆盖任一侧**；审计师决定保留哪侧
5. WHEN 同步状态显示 THEN 四张表工具条必须显示当前同步态（「已同步」/「excel 侧有未同步改动」/「html 侧有未同步改动」三态，中文彩色 tag，禁裸英文），只读态下按钮禁用
6. WHEN 双向回写实现 THEN 必须在**共享层**实现（新增 `useD4OtherGroupDualWriteback.ts` 或同类共享 composable，四张表共同调用），**禁止**在任一组件内联重写 OO 保存钩子或同步协议；四张表只传 sheet_code + 结构 adapter（四张表结构差异大：D4-33 是 `{bizTypes}`、D4-34 是 `{rentals,consults}`、D4-35 是 `{rows,sampling,periodAmount}`、D4-36 是 `{forward,backward}`，adapter 必须显式声明，不得用通用 JSON 猜测）
7. WHEN 双向回写落库路径 THEN 必须复用组件既有 `persistAll`/`flushSave` → `d4:save-items` → 宿主 `GtD4OperatingRevenue` PUT `checklist-responses` 通道，不得新造保存端点或旁路写 `allResponses`
8. WHEN 「在线编辑」模式未挂载或 OO 服务不可用 THEN html 侧功能必须完全不受影响（不得因 OO 探针失败而阻断 html 编辑/保存），差异提示退化为「在线编辑不可用」
9. WHEN 多子区表（D4-34 两区 / D4-36 两区）双向回写 THEN 同步必须**逐区独立**（导入/同步 `-rental` 不得冲掉 `consults`，同步 `forward` 不得冲掉 `backward`），与 Requirement 1 AC2/AC4 的合并写回语义一致
10. WHEN 四张表双向回写 THEN 必须至少一张表（D4-35，单区结构最简单）在浏览器真栈实测通过一次「html 改→同步到 excel→excel 改→回读 html」完整往返，其余三张以单元测试 + 代码结构判据验收

### Requirement 3: 双向回写 —— 差异/异常发现联动上下游

**User Story:** 作为审计师，这四张底稿发现的毛利率异常、合同测算差异、抽凭异常、跨期疑点，应该能一键推送到 A13 未更正错报汇总，并在 D4-1 审计说明留痕，形成风险导向可追溯链路。

#### Acceptance Criteria

1. WHEN D4-33 存在可推送项（业务类型合计毛利率超阈值，或毛利率变动率超阈值）THEN 必须提供「推送毛利率异常至 A13」入口，payload `wpCode:'D4-33'`、`accountCode:'6051'`、`accountName:'其他业务收入'`、`amount:0`（分析表，定性项）、`description` 必须写明「其他业务毛利率分析：{业务类型} 毛利率 {值}%，同比变动 {变动率}%，超阈值」，`indexRef:'wp:D4-33'`
2. WHEN D4-34 存在可推送项（`diff !== 0`）THEN 同上，`wpCode:'D4-34'`，`amount` 取 `abs(diff)`；描述必须区分租赁区/咨询区并带承租方或委托方名称、应计与实计金额、差异金额；租赁区与咨询区命中时**各自独立成条**（不合并）
3. WHEN D4-35 存在可推送项（`isAnomalous === '是'`）THEN 同上，`wpCode:'D4-35'`，`amount` 取 `parseNum(该行 amount)`，描述必须带凭证号 + 业务内容 + 6 个核对列中未通过项
4. WHEN D4-36 存在可推送项（`isCrossPeriod === true`）THEN 同上，`wpCode:'D4-36'`；forward 取 `docAmount`（已发/已验未记账），backward 取 `voucherAmount`（已记账未发/未验），描述必须带方向标识（账到单据/单据到账）+ 跨期天数 + 调整建议
5. WHEN 推送前无可推送项 THEN 必须以中文提示告知（如「无毛利率异常，无需推送」），不得静默、不得推空、不得抛错
6. WHEN 推送成功 THEN 必须给成功反馈（推送 N 项），并把同一批差异摘要 append 到 D4-1 审计说明（item_id `D4-1-adj-note`）
7. WHEN 只读态（`isReadonly`）THEN 推送入口必须禁用
8. WHEN 推送事件 THEN 必须走平台既有白名单事件 `a13:push-misstatement`，由 `useA13MisstatementBridge` 唯一消费者落 `unadjusted_misstatements`（禁止调不存在的 `POST /push-to-a13` 端点）
9. WHEN 四表接线 THEN 必须复用已存在的 `useD4InspectionWriteback`（`pushToA13` + `appendToD41Note`），**禁止**在任一组件内联重写事件构造或落库逻辑；若该共享件签名不足，只允许在共享件内扩展可选参数（如 `sourceSheet` 中文表名），不允许在组件内绕过
10. WHEN **科目码** THEN 四表推送必须用 `6051`/`其他业务收入`，**禁止**照抄姊妹 spec 的 `6001`（D4-13~20 是主营收入）；该字面量必须有守卫断言（Property 8）
11. WHEN 溯源 chip THEN 必须按 `cross_wp_references.json` 已登记关系校验/修正四张表的 `GtIndexChip`（现存 `D4-33 → wp:D4-3`、`D4-34 → wp:D4-33`、`D4-35 → wp:D4-34`、`D4-36 → wp:D4-35`），**禁止自造任何未在 `cross_wp_references.json` 登记的引用关系**；`D4-36` 还应补一条指向 `wp:D4-17`/`wp:D4-18` 的姊妹截止测试引用（若已登记）
12. WHEN 可推送项判据 THEN 必须集中在**一个共享声明**（新增 `d4OtherGroupPushPredicates.ts` 或写入 Requirement 2 的双向回写共享件），四张表共同引用，**禁止**在四个组件各写一份过滤条件（防口径漂移）

### Requirement 4: 公式管理 —— 引擎接线 + 覆盖层（单一真源 + 用户二次编辑）

**User Story:** 作为审计师，四张表的毛利率、合同测算差异、异常率、跨期判定都应该是公式自动算的、可看到公式来源；而且这些公式应该有平台预设的默认口径，我可以在**本项目**上按需二次编辑（比如「毛利率同比变动超过 30% 才算异常」改成 20%），改完之后表格里显示的值、推送到 A13 的值、导入导出的值必须全都是我改后的口径，不能改了一处另两处还是老口径。

#### Acceptance Criteria

1. WHEN D4-33 计算毛利率 THEN 必须接线引擎 `calcGrossMarginRate`，并按 DEC-2 裁决**统一改为引擎的百分比口径**（现有内联实现返回小数比率、引擎返回百分比，差 100 倍）：组件展示处补 `%` 后缀，**不得**在组件里做局部 `*100` 打补丁；同时接线 `calcSubtotal`（12 月合计）与 `calcChangeRate`（同比变动率）
2. WHEN D4-34 计算 `diff` THEN 必须替换为引擎 `calcChangeAmount(actualRevenue, expectedRevenue)`，并删除组件内联的本地 `pn` 函数改用引擎 `parseNum`（本地 `pn` 与引擎 `parseNum` 并存属第二套解析路径）
3. WHEN D4-35 计算异常率/覆盖率 THEN 必须接线引擎已有的 `calcAnomalyRate`（异常笔数/已检查笔数）与 `calcCoverageRate`（已检查金额/收入合计），组件内禁止内联 `filter().length` 与 `reduce`
4. WHEN D4-36 计算跨期判定 THEN 必须接线引擎 `isCrossPeriod` 与 `calcCrossPeriodDays`，并按**方向区分语义**：forward（账到单据）= 凭证在期内且单据在期后；backward（单据到账）= 单据在期内且凭证在期后——现有 `useD4OtherGroup.ts`（死代码）把两区混成一个 `isCrossPeriod(voucherDate, shipDate, bsDate)`，语义不区分方向，**不得**照抄；跨期汇总必须用 `calcSubtotal`
5. WHEN 公式是单一真源 THEN 统一使用 F-SHELL v2 effective definition；支持 `expression`/`refs`/`params` 编辑，后端权威执行并投影 HTML/OO。默认、custom、删除、恢复默认分开，禁止 `field_overrides` 或 checklist remark 公式库。
6. WHEN 用户编辑了覆盖公式 THEN 该覆盖值必须在**表格渲染值、A13 推送金额/判据、导出行构造值**三处生效为同一口径（Property 4 判定），不得存在第二套计算路径；覆盖层读取必须封装成单一函数（如 `getFormulaParam(sheet, key)`），四张表共同调用
7. WHEN 覆盖层缺失或解析失败 THEN 必须回退到引擎默认值且**给可见提示**（不得 fail-open 静默用默认值掩盖配置损坏——fail-open 掩盖接线错误是最贵一类缺陷）
8. WHEN 公式参数面板 THEN 四张表工具条必须提供「⚙ 公式设置」入口（弹窗），列出该表的预设公式清单（公式名/当前值/默认值/「恢复默认」按钮），中文全标注，只读态下「恢复默认」与「保存」禁用；**没有覆盖公式的表也必须能打开面板看到预设默认值**
9. WHEN 自动计算列显示 THEN 必须统一套蓝本自动列样式（对齐 D4-2 的 `.auto-calc-col`：灰底 + 虚线下划线），**替换 D4-34 现用的 `.auto-calc` 旧样式**，并在列头 tooltip 标注计算来源（如「实际收入 − 应计收入」），阈值类公式的 tooltip 文字必须随覆盖层实时反映当前生效值
10. WHEN 公式纯函数新增或接线 THEN 必须有单测覆盖数值结果（毛利率百分比口径、合计、差异、异常率、覆盖率、跨期双向语义），断言数值而非「函数存在」；若需新增纯函数（如方向化跨期判定 `isCrossPeriodForward`/`isCrossPeriodBackward`）必须保持无副作用、无 Vue 依赖（可单测可 PBT）
11. WHEN 覆盖公式影响导入导出 THEN 导入文件的派生列（合计/毛利率/差异/异常率/跨期判定/跨期天数）**必须由引擎+覆盖层重算**，不读文件值（防手改文件伪造结论），与 Requirement 1 AC8 同口径

### Requirement 5: 守卫、变异检验与真栈实测

**User Story:** 作为维护者，我要证据证明导入导出真的往返一致、双模式回写真的落库、公式覆盖真的三处同口径、科目码没抄错，而不是又一批「看着有按钮实则断裂」的死代码。

#### Acceptance Criteria

1. WHEN 修复导入导出 THEN 必须有后端 pytest 断言：四张表 parser 产出结构与前端类型**逐字段**一致（D4-33 的 `{bizTypes}` 嵌套 12 月 + prior、D4-34 的 `{rentals, consults}` 合并写回不互相覆盖、D4-35 的 `{rows, sampling, periodAmount}` 且 `sampling` 不被行导入冲掉、D4-36 的 `{forward, backward}` 且 backward 按列头名映射不错位），且 sheet → item_id 字面量分别等于 `D4-33-data`/`D4-34-data`/`D4-35-data`/`D4-36-data`
2. WHEN 编写守卫 THEN 必须做变异检验并四态判定（RED / GREEN=守卫缺陷 / ANCHOR-MISS / WRONG-TEST）；锚点至少含：把任一表 item_id 改回 `f"{sheet}-rows"` 必红 · 把 D4-35 parser 改回 `_parse_generic_row` 必红 · 把 D4-36 backward 改成按列序映射必红（交叉错位）· 把 D4-34 导入改成整对象覆盖（丢另一区）必红 · 把 D4-33 毛利率改回小数比率口径必红 · 把任一表 `accountCode` 从 `6051` 改成 `6001` 必红
3. WHEN 补 A13 回写入口 THEN 必须有前端 vitest 断言：按钮存在、`isReadonly` 禁用、点击真 `eventBus.emit('a13:push-misstatement')` 且 payload 的 `wpCode` 字面量正确（防四表互接错）、**`accountCode` 为 `6051` 且 `accountName` 为 `其他业务收入`**、D4-33 定性项 `amount` 为 `0` 且 D4-34 `amount` 等于 `abs(diff)`；无可推送项时不 emit
4. WHEN 补双模式回写 THEN 必须有前端守卫断言：excel→html 同步失败路径**可见错误 + 不标记已同步**（判行为，非字符串存在型）；html→excel 为人工触发（不存在 html 保存时自动反写 excel 的调用链）；多子区表逐区同步不互相覆盖
5. WHEN 公式接线与覆盖层 THEN 必须有前端守卫断言：四张表组件**不再**内联毛利率/差异/异常率/跨期判定逻辑，且公式引擎被真实调用（判调用链，禁纯字符串存在型）；**断言 D4-33 毛利率为百分比口径**（防回归到小数比率）；覆盖层「三处同口径」必须有专测
6. WHEN 删除死代码 THEN 必须有守卫断言 `useD4OtherGroup.ts` 不存在且全库 grep `useD4OtherGroup` 零命中（防重新引入）
7. WHEN 死配置清理 THEN 必须有守卫断言 `_SUPPORTED_SHEETS` 与 `_SHEET_HEADERS` 不含 `D4-34`（12 列主键）与 `D4-36`（12 列主键），且前端下拉不含对应入口
8. WHEN 全部交付 THEN 必须至少一次浏览器真栈实测：四张表各做一次导出→导入往返（值逐字对齐）+ 一次差异→A13 推送（A13 页面出现该错报且 `source_wp_code` 正确、科目为 6051）+ D4-35 做一次 html↔excel 双向回写往返 + 一次公式覆盖编辑后三处口径一致验证
9. WHEN 交付收口 THEN 必须校验 spec 三件套结构（`### Property N` 为整数、`**Validates: Requirements X.Y**` 交叉引用为 `X.Y` 形态、tasks 含 waves JSON）并确认全部正式产物无 `??` 未跟踪（本 spec 目录本身也必须入库——「spec 全绿 ≠ 产物已入库」，丢工作树即蒸发）

## Correctness Properties

### Property 1: 导入导出往返不丢字段

**Validates: Requirements 1.8, 1.7**

任意 `BizType[]`（D4-33）/ `{rentals, consults}`（D4-34）/ `{rows, sampling, periodAmount}`（D4-35）/ `{forward, backward}`（D4-36）实例，经 export 行构造 → 写 xlsx → import parser 解析后，其**录入字段**必须逐字段相等（含 D4-33 的 12 月 + 上年数嵌套、D4-34 两区合并写回不互相覆盖、D4-35 的 `sampling`/`periodAmount` 不被行导入冲掉、D4-36 的 backward 按列头名映射不交叉错位）；派生字段由引擎重算，不参与相等性比对，但重算结果必须与导入前一致。空金额保持空串（不得被写成 0）。

### Property 2: 后端 item_id 与前端持久化键恒等

**Validates: Requirements 1.5**

对四张表的所有可导入导出 sheet 键，`sheet → item_id` 映射结果必须等于组件 `allResponses` 实际使用的键（`D4-33` → `D4-33-data`；`D4-34-rental`/`D4-34-consult` → `D4-34-data`；`D4-35` → `D4-35-data`；`D4-36-forward`/`D4-36-backward` → `D4-36-data`）。任何 sheet 键不得回退到 `f"{sheet}-rows"` 兜底。

### Property 3: 多子区写入不互相覆盖

**Validates: Requirements 1.2, 1.4, 2.9**

对 D4-34（`rentals`/`consults`）与 D4-36（`forward`/`backward`）任一子区的导入或双模式同步，另一子区必须逐字段保持不变（含为空数组的态）。合并写回必须读取既有值再合并，不得整对象覆盖。

### Property 4: 公式覆盖值三处同口径

**Validates: Requirements 4.6, 4.11**

对任一被用户二次编辑覆盖的公式参数，同一覆盖值在**表格渲染值**、**A13 推送金额/判据**、**导出行构造值**三处产出必须一致（浮点容差 `1e-9`）；不得存在第四套计算路径。无覆盖时三处产出必须等于引擎默认值。

### Property 5: 毛利率口径唯一（百分比）

**Validates: Requirements 4.1, 5.5**

D4-33 的毛利率在所有出现位置（表格渲染、导出行构造、A13 描述文本、公式面板显示）必须为**百分比口径**（`(revenue-cost)/revenue × 100`，与引擎 `calcGrossMarginRate` 一致），全库不得存在返回小数比率的第二套毛利率计算路径。

### Property 6: 空项不推送

**Validates: Requirements 3.5**

当四表任一表的可推送项集合为空时，`pushToA13` 不得 emit 任何事件，且必须返回可被 UI 转为中文提示的空态信号（非静默、非抛错）。

### Property 7: 只读态禁写

**Validates: Requirements 3.7, 4.8**

当 `isReadonly === true` 时，四表所有推送入口、双模式同步入口、公式覆盖编辑入口、CRUD 入口、导入入口均不得触发写操作（不 emit 事件、不改 `allResponses`、不调保存端点）。

### Property 8: 科目码不越界（6051）

**Validates: Requirements 3.10, 5.3**

四张表 A13 推送 payload 的 `accountCode` 必须恒为 `6051`、`accountName` 恒为 `其他业务收入`；不得出现 `6001`/`营业收入`（那是主营收入组 D4-13~20 的科目，照抄即错）。D4-33 作为分析表 `amount` 恒为 `0` 且 `description` 必须包含定性标记词（毛利率/同比/超阈值）。

### Property 9: 双模式同步 fail-closed

**Validates: Requirements 2.2, 2.4**

excel → html 同步失败时，必须可见报错且同步态不得标记为「已同步」，html 侧数据保持改动前状态；只读校对的差异只能提示、不得自动覆盖任一侧。html → excel 必须为人工触发，不存在 html 保存时自动反写 excel 的调用路径。

### Property 10: 可推送判据单一真源

**Validates: Requirements 3.12, 1.9**

四张表的可推送项判据必须集中在一个共享声明中定义；组件内不得各自内联过滤条件。`useD4OtherGroup.ts` 必须已删除且全库无残留 import（防死代码以新名字复活）。

### Property 11: 覆盖层失败不静默回退

**Validates: Requirements 4.7**

公式覆盖层的 JSON 解析失败、item_id 缺失、字段类型错误三类异常，均不得静默回退到默认值；必须给出可见提示（日志或 UI）并保留默认值口径，且该异常必须可被守卫断言（不得为「吞异常返回默认值」的 fail-open 形态）。

### Property 12: 无死配置残留

**Validates: Requirements 1.6, 5.7**

`_SUPPORTED_SHEETS` 中每个 sheet 键必须在前端存在真实消费方（有下拉入口且组件有对应持久化通道）；不得存在「已登记但前端无入口」的静默 generic 落库路径。特别地 `D4-34`（12 列主键）与 `D4-36`（12 列主键）必须已删除。

## Decisions

- **DEC-1（已裁决）｜item_id 错位方向**：改**后端映射**，不改前端键。前端 `D4-33-data`/`D4-34-data`/`D4-35-data`/`D4-36-data` 已被各组件内 watch/persistAll/onBeforeUnmount 多处引用；后端四个 `f"{sheet}-rows"` 兜底键当前零消费者。与姊妹 spec 的 DEC-2 同方向。
- **DEC-2（已裁决）｜毛利率口径冲突**：统一到引擎 `calcGrossMarginRate` 的**百分比口径**，前端展示补 `%` 后缀；**禁止**在组件里做局部 `*100` 打补丁（那会制造第四套口径）。理由：引擎是单一真源，且姊妹 spec 与平台其他毛利率显示（D4-7/D4-8/D4-33 后端 export 的「合计-毛利率」列）均按百分比。
- **DEC-3（已裁决）｜主 sheet 死配置**：`D4-34`（12 列）与 `D4-36`（12 列）**删除**而非报错短路。前端只用 `-rental`/`-consult` 与 `-forward`/`-backward` 子键，主键从未有消费方；保留即 Property 12 的死配置。与姊妹 spec 的 DEC-1 同方向。
- **DEC-4（已裁决）｜死代码处置**：`useD4OtherGroup.ts` **直接删除**，不留 DEPRECATED 注释（平台铁律：死代码立即删除，否则每次复盘重复提议）。该文件类型定义与真实组件类型全不符（如声明 `OtherCheckRow.isAnomalous: boolean` 而真实是 string），留着只会误导。
- **DEC-5（已裁决）｜科目码**：四表统一 `6051`/`其他业务收入`。这是本 spec 与两个姊妹 spec（`6001`/`营业收入`）的唯一科目差异，**必须**有守卫断言防照抄错误（Property 8）。

## Glossary

| 术语 | 含义 |
|------|------|
| D4-33 | 其他业务毛利率分析表：`{bizTypes:[BizType]}`，每业务类型 12 月 + 上年数，算毛利率与同比变动 |
| D4-34 | 其他业务收入合同测算表：两区（房屋租赁 `RentalRow` / 咨询业务 `ConsultRow`），算应计收入 vs 实计收入差异 |
| D4-35 | 其他业务收入检查表（抽凭）：`{rows, sampling, periodAmount}`，6 个核对列 + 异常标记（string `是`/`否`） |
| D4-36 | 其他业务收入截止性测试：两区（账到单据 `forward` / 单据到账 `backward`），方向语义相反的跨期判定 |
| 双向回写（双模式） | html 结构化视图 ↔ excel（OnlyOffice 在线编辑）两个编辑面之间的数据同步，任一侧保存后另一侧可见最新数据 |
| 蓝本 D4-2 | 主营业务收入明细表，D4 循环公式+回写+导入导出最完备的参照实现（`.auto-calc-col` 样式来源） |
| 姊妹 spec | `d4-cutoff-return-writeback-formula-io`（D4-17~20）/ `d4-inspection-writeback-formula-io`（D4-13~16），已产出本 spec 复用的 `useD4InspectionWriteback` 与后端专用 parser 范式 |
| generic 兜底 | import/export 分发 `else` 分支：`_parse_generic_row`（存中文列头字符串 key）+ `[data_row.get(h) for h in headers]`（按中文列头取值），与前端英文 key / 嵌套结构读不通 |
| item_id | `checklist_responses` 的存储键；前后端不一致即数据断裂 |
| 死配置 | `_SUPPORTED_SHEETS`/`_SHEET_HEADERS` 已登记但前端无消费方的 sheet 键，静默走 generic 落错键 |
| `useD4OtherGroup.ts` | 🔴 **已裁决删除**的 D4-33~36 死代码 composable：grep 零消费者，键位 `D4-33-rows` 等与真实键 `D4-33-data` 全不符，跨期判定不区分方向 |
| `useD4InspectionWriteback` | 已存在的 D4 检查类回写共享件：`pushToA13`（a13 形态 C，空项不 emit）+ `appendToD41Note` |
| `a13:push-misstatement` | 平台错报推送事件（`crossWpEventBridge` 白名单），唯一消费者 `useA13MisstatementBridge` 写 `unadjusted_misstatements` |
| `d4:save-items` | 子表落库事件，宿主 `GtD4OperatingRevenue` 监听 → `formData.saveBatch` → PUT checklist-responses |
| `useD4FormulaEngine` | 前端公式纯函数库（`parseNum`/`calcSubtotal`/`calcGrossMarginRate`/`calcAnomalyRate`/`calcCoverageRate`/`isCrossPeriod`/`calcCrossPeriodDays` 等） |
| 公式覆盖层 | 用户二次编辑层：`(wp_id, sheet_code, formula_key)` → 值，存 `checklist_responses` 的 `{sheet}-formula-override` item_id，不新增表 |
| 6051 / 6001 | 其他业务收入 / 主营业务收入科目码；本 spec 全用 6051，姊妹 spec 全用 6001，照抄即错 |
| fail-closed | 失败即可见报错且不标记成功状态；相对 fail-open（吞异常静默继续） |
| round-trip | 导出数据再导入回来，录入字段逐字段一致（派生列由重算得出，不参与比对） |

> **三件套格式约定**：Property 的交叉引用统一写作 `**Validates: Requirements N.M**`（可逗号分隔多条）；`### Property` 序号为纯整数。上表 Glossary 中的字段名仅为术语解释，不构成校验引用。


**冲突与同步原则**：HTML/Excel 统一消费 `ContentMutationService` + `useWorkpaperSyncBridge`、durable callback、三方合并与 contract-bundle；禁止自建 bridge、仅 emit、Excel 优先或最后写胜出。公式统一 F-SHELL v2 mutation，后端权威执行，前端仅预览；effective definition 含 `expression`/`refs`/`params`，默认、custom、删除、恢复默认分开，禁止 `field_overrides` 公式库或 remark 冒充公式。A13 仅在人工认定金额及方向并 durable ack 后推送，定性风险不以 amount=0 入汇总，不使用 `abs(diff)`，不把凭证全额当错报。源模板由 `backend/wp_templates/` finder/index 实施前核定，核定前 blocked。

共同契约 `d4-dual-mode-formula-governance` 由其他代理创建，实施前必须链接其 requirements/design，禁止猜 AC。双向回写必须消费既有 `ContentMutationService`、`useWorkpaperSyncBridge`、durable callback、三方合并及批准的 contract-bundle representation；纠正现有 `useD4OtherGroupDualWriteback` 自行同步设想。事件需 durable ack 与幂等，不能仅 emit；HTML/Excel 必须是真双向回写，最后编辑胜出须保留三方合并审计。

F-SHELL v2 mutation 是唯一公式入口。同一 effective definition 投影 OO/HTML；formula mask 只保护普通值写入，授权公式编辑复用统一解析/权限/CAS/审计路径，不只回写结果。预设基础上可改 `expression`/`refs`/`params`，不得把 checklist remark 当 override、不得前后端各存默认值、不得把纯函数当可编辑声明。预设升级不覆盖 custom，删除/恢复默认分离，scope 固定 `wp/sheet/row/field`，声明单位；空/除零/error 不写 0，未知函数显式 blocked。

A13 与双向分开：人工认定错报金额及方向后才推送；定性风险不得直接 amount=0 入错报汇总；不得 abs(diff) 丢方向或将抽凭金额直接等同错报。源模板必须经 `backend/wp_templates/` 实际 finder/index 核定，两组声称不同模板未核定前为 blocked。验收逐张 HTML→OO→HTML、公式编辑重新打开、导出与不同项目隔离，不能以 D4-35 代表全组。
