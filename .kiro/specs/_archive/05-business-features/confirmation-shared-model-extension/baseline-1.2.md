# Task 1.2 零回归基线记录（Wave 0 / M0 gate）

> 非生产文件。本 spec 后续波次（2.x–5.x）不得破坏此基线；Property 2（task 6.1）以此处 Sync_Field_Set 为比对基准。
> 生成时间：2026-07-26。运行环境：`audit-platform/frontend`，vitest v3.2.4。

## 1. 零回归测试基线（全部 GREEN）

| 套件 | 命令 | Test Files | Tests | 结果 |
|------|------|-----------|-------|------|
| 函证域前端全量 | `npx vitest run src/components/workpaper/confirmation` | 37 passed (37) | 640 passed (640) | ✅ PASS |
| htmlRendererRegistry | `npx vitest run src/components/workpaper/__tests__/htmlRendererRegistry.spec.ts` | 1 passed (1) | 47 passed (47) | ✅ PASS |

> 说明：测试运行时 stderr 大量 `[Vue warn]: Failed to resolve component: el-*` 为测试环境未全局注册 Element Plus 组件的**噪声**，非失败；全部套件 Exit Code 0 且 0 failed。

### 八套 alternative characterization 测试（均含在「函证域前端全量」内，全部 GREEN）

| 枢纽 | 测试文件 | tests |
|------|---------|-------|
| D05 | `alternativeD05/composables/__tests__/useAlternativeData.spec.ts` | 23 |
| D06 | `alternativeD06/composables/useAlternativeD06Data.spec.ts` (+ `blockColumnConfigsD06.spec.ts` 18) | 7 |
| F05 | `alternativeF05/composables/__tests__/useAlternativeF05Data.spec.ts` | 10 |
| F06 | `alternativeF06/composables/__tests__/useAlternativeF06Data.spec.ts` | 9 |
| H05 | `alternativeH05/composables/__tests__/useAlternativeH05Data.spec.ts` | 10 |
| K05 | `k0-confirmation/composables/__tests__/useAlternativeK05Data.spec.ts` | 32 |
| K06 | `k0-confirmation/composables/__tests__/useAlternativeK06Data.spec.ts` | 31 |
| L05 | `l0-confirmation/composables/__tests__/useAlternativeL05Data.spec.ts` | 34 |

## 2. Sync_Field_Set 基线（Property 2 比对基准）

来源：`confirmation/coordination/syncHubFromSummary.ts`（读码实证，2026-07-26）。
即 `syncHubFromSummary` 实际映射到台账 `confirmation` 表的 `ConfirmationRow` 字段集合。

### 2.1 直接字段 → 台账列映射（create POST / update PUT）

| ConfirmationRow 字段 | 台账 confirmation 列 | 映射方式 |
|---|---|---|
| `entity_name` | `counterparty` | `String(row.entity_name).trim()` |
| `account_type` | `confirm_type` | `accountTypeToHubType(row.account_type)`（**仅传 account_type，未传 accountCode**） |
| `amount` | `book_amount` | `Number(row.amount) || null` |
| `reply_amount` | `confirmed_amount` | `Number(row.reply_amount) || null` |
| `difference`（或 `amount − reply_amount` 派生） | `diff_amount` | `row.difference != null ? Number(row.difference) : round(book − reply)` |
| `remark` | `diff_note` | `row.remark`（update 时 `|| hub.diff_note`） |
| `confirm_index` | `account_code` | `row.confirm_index`（update 时 `|| hub.account_code`） |

### 2.2 状态派生字段（`rowToHubStatus` 读取以下字段决定 transition 目标 status）

| ConfirmationRow 字段 | → status |
|---|---|
| `match_status` | `'相符'→matched` / `'不符'→discrepancy` / `'未回函'→sent` |
| `is_replied` | `true → returned` |
| `reply_date` | 有值 → returned |
| `send_date` | 有值 → sent |
| `confirmation_method` | 有值 → sent |

### 2.3 内部标记（非台账列，仅匹配/回写用）

| 字段 | 用途 |
|---|---|
| `_row_id` | `hubIdByRowId` 键（内部） |
| `_hub_confirmation_id` | 精确匹配 hub + 同步后回写行（内部） |

### 2.4 非行字段（options 参数，非 ConfirmationRow）

| option | 去向 |
|---|---|
| `wpId` | `wp_id` |
| `wpCode` / `year` | transition body（不入 confirmation 列，仅路由 CONFIRMATION_RECEIVED stale） |

### 2.5 台账 `confirmation` 表被写列合集

`confirm_type` · `counterparty` · `wp_id` · `account_code` · `book_amount` · `confirmed_amount` · `diff_amount` · `diff_note` · `status`

## 3. Property 2 断言口径

本 spec 新增的全部 additive 字段（`sample_purpose` / `send_doc_no` / `send_addr_match` / `reply_courier_no` / `reply_from_addr` / `send_reply_addr_match` / `use_alternative` / `alt_unconfirmed` / `row_conclusion` / `send_memo` / `account_no` / `fx_rate` / `amount_orig` / `confirmed_amount_orig` / `term_book` / `term_reply` / `term_match` / `term_note`）**均不得进入 §2 Sync_Field_Set**。

即：对同一批行，含新字段 vs 不含新字段，经 `syncHubFromSummary` 同步后台账 `confirmation` 表 §2.5 各列取值 **SHALL 逐字一致**。
