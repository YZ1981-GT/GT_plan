# G5 长期应收款（1531）

componentType `g5-long-term-receivable`，主入口 `GtG5LongTermReceivable.vue`，后端 `_g5_long_term_receivable.py`。
唯一一个"应收类但归投资循环"的科目（融资租赁、分期收款销售形成的长期应收）。

## 子目录

| 目录 | 内容 |
|---|---|
| `core/` | 审定表 / 明细 / 调整 / 披露 |
| `measurement/` | 未实现融资收益、摊余成本计量（长期应收款净额 = 原值 − 未实现融资收益） |
| `impairment/` | 三阶段 ECL（`useG5StageClassification`：阶段迁移 + 触发条件标签 + 判断依据） |
| `voucher/` | G5-12 凭证检查（`useG5VoucherCheck`，异常可推 A13 错报，科目 1531） |
| `handbooks/` + `G5PreparationHandbookDialog` / `G5AuditTextCards` / `G5SheetStatusBar` / `G5ImportExportDropdown` | 手册与四件套 |

`g5Constants` / `g5AdjudicationItems`：`G5_ACCOUNT_CODE='1531'`、`G5_ACCOUNT_NAME='长期应收款'`。

## 关键机制

- **三阶段分类**（`useG5StageClassification`）：阶段迁移触发条件（逾期天数/信用评级/财务恶化…）→
  产生减值调整建议（对方科目 `1231 坏账准备`）+ 记录 `judgmentBasis` / `discrepancyNote`
- **账龄枚举**：G5 已接 `useAgingConfig('G5')`（3 年段 / 5 年段 / 自定义）
- **凭证异常 → A13**：`useG5VoucherCheck` 把 G5-12 异常映射为未更正错报（科目 1531）
- **跨循环**：融资租赁应收对应 H9 租赁负债/H8 使用权资产（出租方视角）；
  实质净投资的长期应收在 G7-16 未确认损失中作为"实质上构成净投资"的组成

## 与其他元素的关系

- 减值损失 → G14 信用减值损失（6702）
- 未实现融资收益摊销 → G11 投资收益（6111）或财务费用（视业务实质）
- 函证（承租人/购货方）→ G0
