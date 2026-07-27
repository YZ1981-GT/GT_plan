# 盘点与截止（E1-7 · E1-8 · E1-9 · E1-21 · E1-22 · E1-23）

## 盘点（存在性认定）

- **E1-7 / E1-8 库存现金盘点**：同一组件 `E1TabCashCount` 按 `variant='rmb' | 'fx'` 服务人民币 / 外币两张表。
  盘点日实点数 → 倒推资产负债表日余额（`calcCountDiff`），与账面比对出盘盈盘亏。
- **E1-9 银行存单盘点**（`E1TabCertificateCount`）：定期存单 / 大额存单实物盘点。

## 截止测试（E1-21 银行存款 / E1-22 其他货币资金）

同一组件 `E1TabCutoffTest` 按 `variant='bank' | 'other'`。
- 走共享 `GtCutoffAutoSampling`：`:default-conditions="{ cutoffDate }"` + `@applied`（AI 意见追加到审计说明）
- 自动提取走 `POST /sampling/cutoff-test`（**须传 `cutoff_date`**，否则后端按 year-12-31 推）
- 跨期判定用 `cutoffCanonical`（E1 属截止日两侧 XOR 一族）
- OCR 确认弹窗 `E1CutoffOcrConfirmDialog`（回单/流水截图）

**契约提醒**：截止组件的正确 prop 是 `:default-conditions` + `@applied`，
不是 `:cutoff-date` + `@close`（后者是曾经的错误绑定，会让组件收不到条件、也监听不到应用事件）。

## E1-23 收支检查情况表（`E1TabLargeCheck`）

**凭证级 15 列**（不是汇总表）：方向 / 所属科目 / 日期 / 凭证编号 / 业务内容 / 对方科目 / 对方明细科目 / 金额 /
银行回单日期·对方·金额 / 其他支持性文件 / 索引号 / 是否异常 / 异常说明。

- 抽凭：`GtVoucherSamplingEngine`，`account-code="1002"` + `initial-config-patch`（1001/1002/1012），
  回填映射到真实列（借方 = 收、贷方 = 支）
- 行级 📎 OCR：`E1LargeCheckOcrConfirmDialog`
- **早期坑**：曾传 `account-code="1001,1002,1012"`（引擎要单个）且回填字段与列定义不匹配 → `updateCell` 静默拒绝 = 数据丢失假象
