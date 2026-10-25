"""自定义 Excel 模板摄取与整册同步闭环 —— 服务包。

Spec: custom-workpaper-template-ingestion-and-sync-closure

已交付：
* Task 1–9：actions / authorization / policy / quarantine / scanner /
  semantic_preflight / lifecycles / identity+mapping+adapters / candidate；
* Task 10（域模型）：ProjectWorkbookInstance + 统一 pwi entry（SYNC 证明仍 BLOCKED）；
* Task 11：finalize_saga 消费 G-HANDOFF-CONSUMER；
* Task 12：F-SHELL ingestion wizard（前端）；
* Task 13：staging_cas；
* Task 14：sync_gates 只读探测（当前全 BLOCKED）；
* Task 15–17：merge_remap / publication_ops / retention。

外部仍 BLOCKED：SYNC 四 gate → Task 10 证明项 / Task 14 / 完整 Playwright。
"""
