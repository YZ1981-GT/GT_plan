# 上下文：J 循环特有机制

通用机制见 `.omm/d-cycle-sales/context.md` 与 `shared-runtime/`。本文只写 J 特有部分。

## 1. J1 是「自持久化」模式（与多数循环不同）

J1 的凭证检查等表用 **localAllResponses Map + selfLoad（直接 GET `/api/workpapers/{id}/checklist-responses`）
+ 800ms 防抖 PUT**，不完全依赖父入口下发 `allResponses`。
主入口 `GtJ1EmployeeCompensation` 同时负责：
- `provide('jumpToSection')`（目录页跳转）
- 审定表/披露表的 `all-responses` + `save-immediate` 下发
- TB 回写 2211 + `eventBus.emit('substantive:adjudicated')`

**历史坑**：`_extract_json` 曾读不存在的 `content` 列（应读 `remark`），导致 render 输出的 8 个 `*_rows` 恒空。

## 2. J1 审定表「上期审定数 = 期初审定数」

源模板"本期未审/审定数与上期审定数比较"两列都以**期初审定为基数**，无需额外数据源。
变动列字段是 `unadjVsPriorDiff/Rate` + `auditedVsPriorDiff/Rate`（曾与 composable 的 `changeDiff/changeRate` 漂移，四列恒 undefined）。

## 3. J1 分配检查从序时账取数（纯前端）

`j1AllocationLedgerPull.ts`：拉 `/ledger/entries/2211` 游标分页，**只取贷方（计提）**，
`tailSegment` 取明细科目名末段作薪酬项目，`bucketForCounterpart` 按对方科目编码前缀归集：
`5001/4001→生产成本`、`5101/4101→制造费用`、`6602→管理费用`、`6601→销售费用`、其余→其他。
**对方科目为空的金额计入 `unattributedAmount` 如实提示，不臆造分配**（该列部分账套填充率低）。
落跨表键 `J1-7-total-{admin-expense,selling-expense,production-cost}` 供 K8/K9 核对。

## 4. J1 凭证检查表的三模视图（卡片 / 矩阵 / 在线编辑）

`J1TabGeneralCheck` + `J1VoucherCard`：`el-segmented` 三模——
- **卡片视图**：一笔凭证一张可展开卡（头部项目/凭证号/金额/核对进度色签；展开后可编辑字段 + 5 项核对勾选 +
  **按源模板每份外部单据拆独立字段**：贷方=职工薪酬计算表（月份/金额/是否恰当审批）；借方/期后=付款审批单 + 银行回单，各带 📎OCR）
- **矩阵视图**：紧凑表，核对列用可点击色块（on 绿 / off 灰）一键切换
- **在线编辑**：`GtOnlyOfficeSheet`（sheet-name = 源 xlsx tab 名如「检查表J1-8」）

证据字段存 `row.evidence`（calc/approval/bank 三对象，惰性 `ensureEvidence` 初始化）。
数据层复用 `useK1VoucherCheck`（额外字段靠 `...r` 展开透传），核对标签可经 `checkLabels` 参数定制。

## 5. J2 的「增减四栏」结构

J2-2 明细的通用结构：**未审数（期初/增/减/期末=C+D−E）+ 期初调整（账项调整 G）+
账项调整（增 H / 减 I）+ 审定数（期初 J=C+G / 增 K=D+H / 减 L=E+I / 期末 M=J+K−L）**，
用嵌套 `el-table-column` 做分组表头；`AdjRow` 模型区分 leaf / agg（agg 带 `add[]`/`sub[]` 数组，`baseOf()` 递归解析）。
这是 J 类明细表的通用范式，可表达任意勾稽公式（含"合计 = A + B − C"）。

## 6. J3 的引导式录入范式（平台首发）

`J3PlanDialog`（情况表 14 列）/ `J3VariationDialog`（检查表 19 列）：
分组卡片 + 点点点（radio / select filterable allow-create）+ **右侧实时分析面板**
（现金结算→重新计量警告 / 授予日 vs 行权日间隔 >60 月警倒签 / 缺公允价值方法 / 缺索引提示 /
测算 vs 账面差异实时勾稽）+ 确认后回写主表行。
**宽表（>10 列）录入改引导式弹窗**这一范式由 J3 首发，后被 K8-5 / K10-4 / B50 / B1 等复用。

## 7. AI 与手册

- J1/J2/J3 都有 `handbooks/{preparation,usage}.md` + `J{n}PreparationHandbookDialog`
- AI 走统一端点 `POST /api/workpapers/{wp_id}/ai/generate-text`，**context 必须是 `dict[str,str]`**
  （值全转字符串，传数字会 422）；J2 有 proven 范式 `inject<GenerateWorkpaperAiText>('generateAiText')`
- **审计结论不提供 A/B/C 套用模板按钮**（用户明确偏好：直接输入或 AI）
