# 上下文：I 循环特有机制

通用机制见 `.omm/d-cycle-sales/context.md` 与 `shared-runtime/`。本文只写 I 特有部分。

## 1. 科目码常量位置

每科目 `useI{n}FormData.ts` 顶部：
`ACCOUNT_CODE_1701/1702/1703`（I1 原值/累计摊销/减值准备，**回写三个科目**）、
`ACCOUNT_CODE_1717`（I2）、`ACCOUNT_CODE_1711`（I3）、`ACCOUNT_CODE_1801`（I4）、
`ACCOUNT_CODE_1911`（I5）、`ACCOUNT_CODE_6602`（I6，与 K9 管理费用同码——研发费用在管理费用下）。
`useI{n}Adjudication.ts` 里也各自重复了一份同名常量（回写用），改动要两处同步。

## 2. I5 审定表是三层矩阵 + 双调整

`useI5Adjudication`：**原值 / 减值 / 净值** 三层，且有**期初账项调整 + 期初重分类调整**
（`openingAje` / `openingRje`），期末 = F + H − I（对齐源模板列公式）。
默认 10 类 + 可从 D7 / M12 / G2-13 带入；旧字段回写净值审定供 I5-1 消费。

## 3. I2 / I6 有 `cutoff/`（研发支出截止测试）

两者共用基座 `useCycleCutoff`（配置驱动的通用循环截止测试）：
- 正向（记账 → 原始凭证）与反向（原始凭证 → 记账）双向
- 跨期判定用 `isCutoffPeriodCrossing`（**截止日两侧 XOR** 口径，已委托 `cutoffCanonical.crossesByCutoffBoundary`）
- 跨期 → `draftAjeFromCrossPeriod` 生成 AJE 草稿到 I2-3 / I6-3，并发 `a13:push-misstatement`
- 自动提取走 `POST /sampling/cutoff-test`（历史上曾调不存在的 `ledger/cutoff-samples` 致 404，已修）

## 4. I3 商誉的减值是唯一实质程序

商誉不摊销，故 I3 没有 `amortization/`，只有 `impairment/`：
- 资产组 / 资产组组合的认定与商誉分摊
- 可收回金额（DCF：预测期 / 增长率 / WACC / 敏感性）
- **业绩承诺**跟踪（并购对赌未达标是减值强信号）
- 减值一经确认不得转回（CAS8）

## 5. 附注章节（权威 `note_template_variant_matrix`）

| 科目 | 上市 | 国企 |
|---|---|---|
| I1 无形资产 | 五、26 | 八、27 |
| I2 开发支出 | 五、27 | 八、28 |
| I3 商誉 | 五、28 | 八、29 |
| I4 长期待摊费用 | 五、29 | 八、30 |
| I5 其他非流动资产 | 五、31 | 八、32 |
| I6 研发费用 | 五、66 | 八、67 |

I1 上市变动表列头随 `categories` 动态（`buildI1ListedColumns(state)`）；
I2 附注是两级表头扁平合并（"本期增加-内部开发支出"等）；
I5 上市"期末/上年年末" vs 国企"期末/期初"列头不同。

## 6. 正反向跳转与结构化推送

I1~I6 全部登记：正向 `noteDisclosureJump`（精确章节号谓词）+ 反向 `noteDisclosureReverseJump`（节级 map）
+ `buildI{n}SyncPayload` + `_sub_table_columns` 列头（已进覆盖率守卫）。
I5 另有 `i5-2 → i5-1` 的 seed 链（`openingAje` / `openingRje` 写入）。
