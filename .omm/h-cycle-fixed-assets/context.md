# 上下文：H 循环特有机制

渲染链路 / 持久化 / 跨底稿事件 / 共享能力见 `.omm/d-cycle-sales/context.md` 与 `shared-runtime/`。
本文只写 H 特有部分。

## 1. 每科目一个 `useH{n}FormData`，科目码在其顶部常量

`ACCOUNT_CODE_1601` / `_1602`（H1）、`ACCOUNT_CODE_1503` / `_1504`（H3）、`ACCOUNT_CODE_1605` / `_1604`（H4）、
`ACCOUNT_CODE_1631` / `_1632`（H5）、`ACCOUNT_CODE_1606`（H6）、`ACCOUNT_CODE_1621`（H7）、
`ACCOUNT_CODE_1901` / `_ACC_DEP=1902`（H8）、`ACCOUNT_CODE_2205` / `_FINANCE_COST=1802`（H9）、
`H10_ACCOUNT_CODE='6115'`（h10Constants）。H2 的 1604/1605 直接写在 Tab 组件与手册里（无独立常量文件）。

**TB 取数普遍用 `account_prefix` + `startsWith` 前缀匹配**（含子科目），回写用 `PUT /trial-balance/writeback`。
H7 例外：用 `account_codes` 参数 + `POST /trial-balance/writeback {items:[...]}` 批量形态。

## 2. Hx-1 审定表是「原值 / 折旧 / 减值」三段矩阵

不是简单的"未审+AJE+RJE"，而是**三段各自期初期末 × 未审·账项调整·审定 = 12 列**，
净值由公式派生（原值 − 累计折旧 − 减值），身份校验自动执行。
→ "从集中登记带入调整"在 H 循环走**单一账项调整列增量累加**（如 H2 的 `subjectPrefix:'1604'` / `direction:'debit'`），
不是 AJE/RJE 双列。

## 3. 折旧/折耗引擎复用 H1

`useH1DepreciationEngine`（直线法 + 减值分段重算）被 H3 / H5 / H7 / H8 复用：
- H5 另有单位产量法折耗（`depletion/`）
- H8 折旧期 = min(租赁期, 使用寿命)（CAS21）
- H3/H7 公允价值模式下不计折旧

## 4. 减值统一 CAS8 口径

迹象判断（≥2 项触发强制减值测试）→ 可收回金额 = MAX(公允价值净额, 使用价值 DCF/WACC/敏感性) → 减值准备；
**一经确认不得转回**（负数须核实不得冲回损益）。减值损失进 **K11 资产减值损失（6701）**，
并发 `impairment:calculated` 事件（已纳入 `crossWpEventBridge`）。

## 5. 跨底稿 pull 范式（H 循环自成一套）

`h{n}XxxPull.ts` 纯函数 + `resolveWpId`（`/api/custom-query/wp-id-by-code`）+ `loadResponseItem`
（`/api/workpapers/{wpId}/checklist-responses`）：
- `h1CipH2Pull`：H1-7 在建工程转入 ↔ H2 转固合计
- `h2H1TransferPull`：反方向（H2-5 转固 ↔ H1 实际入账原值）
- `h1SoeClearingH6Pull`：H6 清理净损益 → H1
- `h1FinanceLeaseG5Pull`：G5 融资租赁 → H1
- `h2L1LoanPull`：L1 借款 → H2 利息资本化（一般借款本金/利率）
- `h10RelatedH6Pull`：H6-2 净损益 → H10-1

纯提取函数单独 export 便于单测，是 H 循环的标准做法。

## 6. 每科目都有 `handbooks/` + `H{n}PreparationHandbookDialog.vue`

与 G 循环同款（marked + DOMPurify 双 tab）。另有 `handbooks/module-editing-handbook.md`（底稿编制模块级使用手册，
挂在生命周期视图「程序裁剪」阶段头部，不属某个科目）。

## 7. OCR 专用端点

- H1：`/h1/property-title-ocr`（不动产权证）+ `vehicle-title-ocr`（车辆行驶证）
- H3：`/h3/real-estate-title-ocr` + `/h3/contract-ocr`（租赁要素）
- 其余合同类复用 `/d4/contract-ocr`
统一范式：上传 → OCR → **确认弹窗** → **仅回填空字段**（不覆盖人工）。

## 8. H8 ↔ H9 双侧一致性

同一租赁合同的资产侧（H8）与负债侧（H9）必须租赁期 / 折现率(IBR) / 付款额一致：
- H8-5 租赁期确定 → 推送 H8-6 计量参数 / H8-8 折旧期 / H8-13 短期简化
- H8-12 终止 → `applyH8TerminationToH92Rows` 结清 H9-2 对应行
- 跨表键有多别名（`H8-initial-measurement` / `H9-1-initial-liability` 等）+ `h8:asset-updated` 落 `H9-h8-*`
