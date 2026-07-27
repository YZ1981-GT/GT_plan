# 待办（F 循环）

## 已立 spec 未实现

- **`f4-aging-enum-unification`**：F4-2 扁平 4+4 字段 → nested `agingCurrent/agingAudited` + `migrateF4FlatToNested`；
  F4-1 按段驱动 + `LEGACY_AGING_ROWKEY` 沿用既有 rowKey（3 年段零数据迁移）；保留 `aging-other` 残差行不计入 1 年以上；
  后端 `subject_aging_periods('F4')` 新增分支；前后端默认预设 F4=THREE_YEAR 显式登记。红线 = 3 年段逐字节零回归。

## 未做

- **F3-5 逾期票据重分类未落地**：只有文字提示，未生成 RJE 到 F3-3、未发 L1（短期借款 2001）/ F4（应付账款 2202）信号
- **F3 完整性（未入账应付票据）搜索程序缺失**：F4 有 `useF4UnrecordedCheck`，F3 无对应搜索程序（F3-7 期后区是凭证核对不是完整性搜索）
- **F3-4 带息票据 variance 不生成补提利息 AJE**、不与 L2 应付利息勾稽
- **F3-2 保证金字段不联动 E1 货币资金受限披露**
- **F2 存货导入导出的部分 sheet 未纳入**（凭证检查/监盘等以页面录入为主）
- **F3 后端 sheets 命名与源模板不一致待核**（`附注披露(上市)` vs 源模板 `附注披露信息(上市公司)`）
