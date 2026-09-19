# Implementation Plan

## Overview

零回归重构：八套函证替代 composable 收敛为「Shared_Core 工厂 + 每套薄适配器」。先补齐八套 Characterization 安全网（前置门），再建工厂，按 D05 试点→无附加能力组→H05→K05→L05→K06 压轴逐套迁移，每套迁移后其 characterization 测试即时全绿方进下一套。详见 requirements.md / design.md。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": [1, 2, 3], "description": "前置门：补齐 K05/K06/L05 Characterization 安全网" },
    { "wave": 1, "tasks": [4], "description": "建工厂 + 通用单测", "dependsOn": [0] },
    { "wave": 2, "tasks": [5], "description": "D05 试点迁移", "dependsOn": [1] },
    { "wave": 3, "tasks": [6, 7, 8], "description": "D06/F05/F06 无附加能力组（可并行）", "dependsOn": [2] },
    { "wave": 4, "tasks": [9], "description": "H05 迁移", "dependsOn": [3] },
    { "wave": 5, "tasks": [10], "description": "K05 迁移", "dependsOn": [4] },
    { "wave": 6, "tasks": [11], "description": "L05 迁移", "dependsOn": [5] },
    { "wave": 7, "tasks": [12], "description": "K06 压轴迁移", "dependsOn": [6] },
    { "wave": 8, "tasks": [13], "description": "全局验证", "dependsOn": [7] }
  ]
}
```

ASCII 概览：

```
Wave 0（前置门：补齐八套 Characterization 安全网，全部就位才可收敛）
  1. K05 characterization test
  2. K06 characterization test
  3. L05 characterization test
        │（Req 4：八套测试全部就位是收敛启动前置门）
        ▼
Wave 1（工厂）
  4. createAlternativeConfirmationData + 通用工厂单测（Property 1/3/4/5/6/7/8/9/10）
        ▼
Wave 2（试点）
  5. D05 迁移到工厂
        ▼
Wave 3（无附加能力组，可并行）
  6. D06 迁移   7. F05 迁移   8. F06 迁移
        ▼
Wave 4   9. H05 迁移（FormulaEngine 注入 + loadAll/persistAll/importFromSummary 旁挂）
        ▼
Wave 5   10. K05 迁移（+balanceSummary/getReconcileDiff + 构造重载）
        ▼
Wave 6   11. L05 迁移（命名比例 + emptyBase:zero + per-rule calcRatio + 独有导出）
        ▼
Wave 7   12. K06 迁移（压轴：http load/persist 旁挂 + 命名比例 + positional 构造）
        ▼
Wave 8   13. 全局验证（全套 vitest + diagnostics + Vite 全树 transform 冒烟）
```

铁律：每套迁移后其 Characterization_Test 立即全绿才进下一套；失败即停定位根因，不放宽断言（Req 5.3）。已绿套不回退（Req 5.5）。

---

## Tasks

- [x] 1. 补 K05 Characterization 测试（前置门）
  - 新建 `k0-confirmation/composables/__tests__/useAlternativeK05Data.spec.ts`，针对**收敛前现有实现**编写并通过
  - 覆盖八面：init 格式门（`alternative-k05-v1` 接受/非此拒绝）、公司 CRUD（默认 balance `其他应收款`/去重）、区块行 CRUD、`getBlockTotal`（SUM_FIELDS：b1 voucher/receipt、b4 self/other/self_balance）、`getCheckRatio('post_receipt'=b1.receipt_amount/base=closing_balance、'reconcile'=b4.self_balance)`、completionStatus、hasAbnormal、metrics（receipt←post_receipt/shipment←reconcile）、buildPayload（`_format` + receipt_check_ratio/reconcile_check_ratio）
  - 额外锁定独有面：`balanceSummary`（opening/debit/credit/closing=opening+debit-credit、postCheckRatio/reconcileRatio）、`getReconcileDiff(row)`=self-other、构造重载 `(wpId,projectId)` 与 `(props)` 两形态
  - 使用只建所需表/纯前端 composable（无需 DB）；vitest 全绿
  - _Requirements: 4.1, 4.2_

- [x] 2. 补 K06 Characterization 测试（前置门）
  - 新建 `k0-confirmation/composables/__tests__/useAlternativeK06Data.spec.ts`，针对现有实现编写并通过
  - 覆盖：公司 CRUD（默认 balance `其他应付款`/去重）、区块行 CRUD、`getBlockTotal`（SUM_FIELDS：b1 amount/paymentAmount、b2/b3/b4 amount）、**命名比例** `getPostPaymentRatio(c)=b1.paymentAmount/base(closing_balance??credit_amount)`、`getReconcileRatio(c)=b4.amount/base`、completionStatus、hasAbnormal、metrics（receipt←postPayment/shipment←reconcile）、buildPayload（`_format` alternative-k06-v1 + receipt_check_ratio/shipment_check_ratio）
  - **锁定异质 IO**：`loadAll` 从 render-config 提取 K0-6 sheet（mock http 返回含 `_format` 的 sheet → companies 载入；格式不符→空）、`persistAll` 逐块 POST `checklist-responses`（item_id `K0-6-alt-{entity}-block{N}-rows`，mock http 校验调用）、`importFromSummary`（mock k0/K0-6）、positional 构造 `(wpId,projectId)`
  - vitest 全绿（用 vi.mock '@/utils/http'）
  - _Requirements: 4.1, 4.2_

- [x] 3. 补 L05 Characterization 测试（前置门）
  - 新建 `l0-confirmation/composables/__tests__/useAlternativeL05Data.spec.ts`，针对现有实现编写并通过
  - 覆盖：公司 CRUD（默认 balance `长期应付款/借款`/去重）、区块行 CRUD、`getBlockTotal`（SUM_FIELDS：b1 voucher/repayment_principal/repayment_interest、b4 voucher/mortgage/guarantee）、**命名比例** `getRepaymentRatio(c)`（calcRepaymentRatio(b1.repayment_principal??voucher_amount, closing_balance)，**空基数返回 0 非 null**）、`getMortgageRatio(c)`（balance>0 ? b4.mortgage_amount??voucher_amount / balance *100 : 0）、completionStatus、hasAbnormal、metrics（receipt←repayment/shipment←mortgage）、buildPayload（alternative-l05-v1 + receipt_check_ratio/shipment_check_ratio）
  - 锁定独有面：`balanceSummary`（currentLoan=b3.voucher 合计、avg repayment/mortgage）、导出 `getBlockRows`/`getClosingBalance`、`importFromSummary`（内部调 importCompanies，mock l0/L0-5）
  - vitest 全绿
  - _Requirements: 4.1, 4.2_

- [x] 4. 建工厂 createAlternativeConfirmationData + 通用单测
  - 新建 `confirmation/coordination/createAlternativeConfirmationData.ts`（或 `alternativeD05/` 下共享层），实现 §3 API：state、公司 CRUD、区块行 CRUD、`getBlockTotal`(config.getSumFields+calcTotal)、通用 `getRatio(c,key)`（config.ratios/baseAmount/emptyBase/calcRatio，支持 per-rule calcRatio 覆盖）、getCompletionStatus、hasAbnormal、metrics(metricRatioKeys)、buildPayload(format+payloadKey)、可选 `htmlData` init+watch、暴露 `_getBlockRows/_ensureCompanyId/_generateId/_precise/_initFromHtmlData`
  - `AltConfig`/`RatioRule`/`AltCoreReturn` 类型定义
  - 新建工厂单测 `__tests__/createAlternativeConfirmationData.spec.ts`：用最小 fake config 验 Property 1/3/4/5/6/7/8/9/10（含 emptyBase null vs zero、per-rule calcRatio 覆盖、字段回退优先级、去重/seq/selectedCompanyId 回退）
  - `get_diagnostics` 无错误；vitest 全绿
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_
  - _Properties: 1, 3, 4, 5, 6, 7, 8, 9, 10_

- [x] 5. D05 迁移到工厂（试点）
  - 改 `alternativeD05/composables/useAlternativeData.ts` 为构造 AltConfig（format alternative-d05-v1 / defaultBalance `{}` / getSumFields / base=sales_amount / ratios receipt=b3.receipt_amount·shipment=b4.product_amount / payloadKey receipt_check_ratio·shipment_check_ratio / metricRatioKeys receipt·shipment / htmlData）调工厂 + `getCheckRatio(c,type)=core.getRatio` 别名；保留导出名 `useAlternativeData` 与返回签名逐字不变
  - D05 现有 `useAlternativeData.spec.ts` 不改断言、全绿；`get_diagnostics` 无错误
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 2.7, 5.1, 5.2_
  - _Properties: 1, 2, 9_

- [x] 6. D06 迁移到工厂
  - 改 `useAlternativeD06Data.ts`：format alternative-d06-v1 / defaultBalance `{}` / getSumFieldsD06 / base=sales_amount / **ratios receipt=b4.receipt_amount·shipment=b3.product_amount（与 D05 相反，配置表达非分支）** / metricRatioKeys receipt·shipment
  - D06 现有 spec 全绿；diagnostics 无错误
  - _Requirements: 1.1, 1.2, 1.3, 2.7, 5.2_
  - _Properties: 1, 2, 9_

- [x] 7. F05 迁移到工厂
  - 改 `useAlternativeF05Data.ts`：format alternative-f05-v1 / defaultBalance `{item_name:预付账款}` / getSumFieldsF05 / base=purchase_amount??sales_amount / ratios payment=b3.(payment_amount??bank_amount)·inbound=b4.(voucher_amount??invoice_amount) / payloadKey payment_check_ratio·inbound_check_ratio / metricRatioKeys receipt←payment·shipment←inbound；`getCheckRatio(c,'payment'|'inbound')` 别名
  - F05 现有 characterization spec 全绿；diagnostics 无错误
  - _Requirements: 1.1, 1.2, 1.3, 2.7, 5.2_
  - _Properties: 1, 2, 9_

- [x] 8. F06 迁移到工厂
  - 改 `useAlternativeF06Data.ts`：format alternative-f06-v1 / defaultBalance `{item_name:应付账款}` / getSumFieldsF06 / base 同 F05 / **ratios inbound=b3.(voucher??invoice)·payment=b4.(payment??bank)** / payloadKey inbound_check_ratio·payment_check_ratio / metricRatioKeys receipt←payment·shipment←inbound
  - F06 现有 characterization spec 全绿；diagnostics 无错误
  - _Requirements: 1.1, 1.2, 1.3, 2.7, 5.2_
  - _Properties: 1, 2, 9_

- [x] 9. H05 迁移到工厂
  - 改 `alternativeH05/composables/useAlternativeH05Data.ts`：config 注入 `calcTotal=calcBlockTotal(H0)`/`calcRatio=calcCheckRatio(H0)`/`parseNum(H0)`；format alternative-h05-v1 / defaultBalance `{item_name:固定资产}` / getSumFieldsH05 / base=closing_balance??ending_balance / ratios ownership=b2.(contract??invoice??payment)·acceptance=b1.voucher_amount / payloadKey ownership_check_ratio·post_acceptance_ratio / metricRatioKeys receipt←acceptance·shipment←ownership
  - **适配器旁挂**：`loading` ref、`importFromSummary`(http h0/H0-5)、`loadAll=()=>core._initFromHtmlData(props.htmlData())`、`persistAll=core.buildPayload`；构造 props+wpId/projectId 保留；`getCheckRatio(c,'ownership'|'acceptance')` 别名
  - H05 现有 characterization spec 全绿；diagnostics 无错误
  - _Requirements: 1.1, 1.2, 1.3, 2.7, 3.1, 3.2, 3.3, 5.2_
  - _Properties: 1, 2, 9_

- [x] 10. K05 迁移到工厂
  - 改 `k0-confirmation/composables/useAlternativeK05Data.ts`：注入 useK0FormulaEngine calc*；format alternative-k05-v1 / defaultBalance `{item_name:其他应收款}` / getSumFieldsK05 / base=closing_balance / ratios post_receipt=b1.receipt_amount·reconcile=b4.self_balance / payloadKey receipt_check_ratio·reconcile_check_ratio / metricRatioKeys receipt←post_receipt·shipment←reconcile
  - **适配器旁挂**：`balanceSummary`(computed 复用 core.getBlockTotal+companies)、`getReconcileDiff(row)`、`loading`、`importFromSummary`(k0/K0-5)、`loadAll`/`persistAll`；保留 default 导出 + 构造重载 `(wpId,projectId)‖(props)`、`getSumFieldsK05` 导出、`getCheckRatio(c,'post_receipt'|'reconcile')` 别名
  - K05 characterization spec（Task 1）全绿；diagnostics 无错误
  - _Requirements: 1.1, 1.2, 1.3, 2.7, 3.1, 3.2, 3.3, 5.2_
  - _Properties: 1, 2, 7, 9_

- [x] 11. L05 迁移到工厂
  - 改 `l0-confirmation/composables/useAlternativeL05Data.ts`：注入 useL0FormulaEngine（calcBlockTotal）；format alternative-l05-v1 / defaultBalance `{item_name:长期应付款/借款}` / SUM_FIELDS(L05) / base=closing_balance / **emptyBase:'zero'** / ratios repayment=b1.(repayment_principal??voucher_amount)+**per-rule calcRatio=calcRepaymentRatio**·mortgage=b4.(mortgage_amount??voucher_amount)+默认 calcRatio（balance>0 才算） / payloadKey receipt_check_ratio·shipment_check_ratio / metricRatioKeys receipt←repayment·shipment←mortgage
  - **适配器旁挂**：命名别名 `getRepaymentRatio/getMortgageRatio`、`balanceSummary`(currentLoan+avg)、导出 `getBlockRows`/`getClosingBalance`、`loading`、`importFromSummary`(l0/L0-5 内部调 importCompanies)、`loadAll`/`persistAll`；保留 default + named 导出
  - L05 characterization spec（Task 3）全绿；diagnostics 无错误
  - _Requirements: 1.1, 1.2, 1.3, 2.7, 3.1, 3.2, 3.3, 5.2_
  - _Properties: 1, 2, 7, 9, 10_

- [x] 12. K06 迁移到工厂（压轴，异质最大）
  - 改 `k0-confirmation/composables/useAlternativeK06Data.ts`：**不传 htmlData 给工厂**（工厂不 init/watch）；注入 useK0FormulaEngine；format alternative-k06-v1 / defaultBalance `{item_name:其他应付款}` / getSumFieldsK06 / base=closing_balance??credit_amount / ratios postPayment=b1.paymentAmount·reconcile=b4.amount / payloadKey receipt_check_ratio·shipment_check_ratio / metricRatioKeys receipt←postPayment·shipment←reconcile
  - **适配器逐字保留异质 IO**：原 `loadAll`（http render-config 提取 K0-6 sheet）与 `persistAll`（逐块 POST checklist-responses，item_id 模式不变）**不进工厂**；命名别名 `getPostPaymentRatio/getReconcileRatio`；positional 构造 `(wpId,projectId)`；保留 `BLOCK_TITLES_K06`/`getSumFieldsK06` 导出；末尾调 `loadAll()` 保留原 init 时机
  - K06 characterization spec（Task 2）全绿（含 IO mock 断言不变）；diagnostics 无错误
  - _Requirements: 1.1, 1.2, 1.3, 2.7, 3.1, 3.3, 5.2_
  - _Properties: 1, 2, 7, 9_

- [x] 13. 全局验证
  - 运行全部 confirmation vitest（八套 Characterization + 工厂单测 + coordination + 其它）→ 全绿
  - `get_diagnostics` 工厂 + 八套适配器 + 改动测试文件 → 无错误
  - Vite 全树 transform 冒烟：确认八套 composable + 68 caller 无 import 解析失败/命名导出缺失（前端崩溃类 bug 只 Vite 暴露）
  - 核对八套 Alt_Composable 文件行数较收敛前显著下降
  - 确认差异矩阵文档已就位（design.md §2 八套×15维矩阵即 Req 6.3 单一参考，无需另建文件）
  - _Requirements: 1.6, 6.1, 6.2, 6.3, 6.4, 6.5_
  - _Properties: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10_

## Notes

- 全部任务为必做（无 optional）。每套迁移是独立提交单元（Req 5.4），失败即停不放宽断言（Req 5.3），已绿套不回退（Req 5.5）。
- Wave 0 三个 characterization 测试是收敛前置门：八套测试全部就位才可启动 Task 4 之后任何迁移（Req 4.2）。
- 工厂**不吸收 IO**：K06 的 http loadAll / 逐块 persistAll 逐字保留在适配器（零回归关键，Req 3）。
- 无后端/DB 改动；纯前端 composable 重构。验证以 vitest + get_diagnostics + Vite 全树 transform 冒烟为准（前端崩溃类 bug 只 Vite 暴露）。
