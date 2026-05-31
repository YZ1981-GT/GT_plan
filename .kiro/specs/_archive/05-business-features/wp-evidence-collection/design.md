# 设计文档：审计证据收集体系

## 概述
PBC CRUD 填实 + PBC↔底稿联动 + 原始凭证 LLM 识别升级 + evidence_group + 催收。统筹三个切面为一个证据管理闭环。

## 核心设计
- PBC CRUD：模型已就绪（PBCChecklist + PbcStatus + schemas），补 router service
- PBC↔底稿：底稿侧栏新增"证据收集"tab 显示关联 PBC 项状态
- LLM 识别：新建 wp_document_recognizer（替代 wp_ocr_voucher_service 正则），按 doc_type 调 LLM
- evidence_group：voucher_row.attachment_id 单值→数组，支持一行关联多原始凭证
- 催收：PBC 逾期→自动建 IssueTicket（source=pbc 已预留）

## 依赖
- vllm-httpx-bugfix（LLM）
- wp-traceability-panel（附件入网 attachment_lineage 表）
