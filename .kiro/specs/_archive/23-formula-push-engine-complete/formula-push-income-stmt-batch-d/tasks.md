# 任务：公式推送批 D — 损益类审定表

> 顺序即依赖。

- [x] 1. 现扫损益类科目清单
  - 从预设 + push rules 提取所有 6 开头科目码：6001/6051/6115/6602 共 4 条锚点
  - _需求：D3_

- [x] 2. `AdjudicationSpec` 加 `is_income_statement` 支持
  - 评估结论：不需要加字段。`TierAAnchorBinding.workpaper_targets()` 原样执行规则表达式，改 rule JSON 即可；`note_rows()` 已有 `_is_pl_code` 按 `"6"` 前缀判断
  - _需求：D1_

- [x] 3. 4 条锚点列名改写
  - D4-1×2/H10/I6 改为 `TB(code,'本期发生额')` + `trial_balance_audited_occurrence`
  - 预设库同步更新列名；fixture JSON 更新期望值；3 个测试文件同步断言值
  - 验证：BannedColumn 8 passed + D4 canary 19 passed + H10/I6 预设 13 passed
  - _需求：D2_

- [x] 4. 与报表引擎逐值对拍
  - `test_formula_push_income_stmt_parity.py` 14 passed：逐科目 `TB(code,'本期发生额')` == `audited − opening`
  - _需求：D5_

- [x] 5. 独占键 + 清册 + 全套回归
  - 独占键 `--check` 通过（113 个键，exit 0）；规则校验器 40/41 通过（1 个预存基线漂移）
  - _需求：D6_

## 阶段 3：损益类报表联动

- [x] 6. 损益类推送后利润表标 stale
  - 推送引擎本身不标 stale；stale 由上游调整分录事件链路通过 `_is_affected` 精确驱动，已覆盖损益类科目
  - `TestIncomeStatementStaleMapping` 验证 4 个科目精确命中利润表行、不误标资产负债表行
  - _需求：D7_

- [x] 7. 损益类发生额与报表利润表行逐值对拍
  - 合并入 `test_formula_push_income_stmt_parity.py`，总计 23 passed
  - 覆盖 6001/6051/6115/6602 全部 4 个损益类科目
  - _需求：D8_
