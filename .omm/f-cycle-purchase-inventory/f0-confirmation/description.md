# F0 函证（复用 D0）

F 循环的函证走 D0 的 `confirmation-*` 组件族（见 `.omm/d-cycle-sales/d0-confirmation/`），无独立实现。

## F 侧的消费点

- **F1 预付账款**：`F1TabConfirmationProcedure` + `F1ConfirmationUsageGuide` 是 F1 内的函证程序页，
  向供应商函证预付余额；回函经 `confirmation:received` 回写明细行
- **F4 应付账款**：应付函证是**完整性认定**的核心（少记负债风险），
  与 `F4TabUnrecordedCheck`（未入账应付搜索）+ 期后付款测试共同构成完整性证据链
- **F3 应付票据**：票据敞口 / 承兑行信息可经银行函证获得（与 E1、L1 共用同一封银行函证）
- **替代程序**：未回函走 `alternative-*` 族（F05 / F06 两套，已收敛进
  `createAlternativeConfirmationData(config)` 工厂）

## 应付类函证的特殊性

应收函证防"多记资产"，应付函证防"少记负债" —— **应付函证的关键不是回函相符，而是"发了多少家、有没有漏发"**。
所以 F4 的函证覆盖率要跟供应商总体（而非仅账面有余额的供应商）比对，并配合未入账搜索与期后付款测试。
