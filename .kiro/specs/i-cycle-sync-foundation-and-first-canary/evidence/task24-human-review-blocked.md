# Task 24* — 人工审核契约（依赖 BP-2 / BP-3）

**状态**：`[ ]*` 阻塞于 BP-2（人工审核 per-entry contract）+ BP-3（approved authority model）

## 阻塞说明

- BP-2：需产出第一条 `review.entry_id` 以 `xlsx/gt-i` 开头的 per-entry contract
  （现算 19 份契约中只有 `i6.research_development_expense_detail.json` 是 I 循环的，
  但其 review_status 仍为 `candidate`，需人工审核升级为 `approved`）
- BP-3：需 approved authority model + non-null approved definition bundle

## 判据

判据是「逐文件读 `review.entry_id`」**不是数契约个数**（Task 3 已裁）。
契约文件已就绪，等待人工审核流程。
