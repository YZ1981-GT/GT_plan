# 需求文档：审计证据收集体系（wp-evidence-collection）

## 引言

PBC（应收）+ 原始凭证（已收）+ 附件入网（关联）是同一审计证据收集体系的三个切面。当前 PBC router 是 developing 空壳，原始凭证识别停在正则版，附件游离在联动网络外。本 spec 统筹三者。

## 需求

### 需求 1：PBC 清单填实
1. THE system SHALL 把 pbc.py 从 developing 占位补成真 CRUD（模型已就绪）
2. WHEN PBC 项创建，THEN SHALL 支持关联到底稿/审计循环
3. WHEN 客户上传资料，THEN PBC 项状态 SHALL 从 pending→received

### 需求 2：PBC ↔ 底稿联动
1. WHEN 底稿编制时，侧栏 SHALL 显示"本底稿依赖的 PBC 项及收集状态"
2. WHEN PBC 项缺失证据，THEN SHALL 高亮提示

### 需求 3：原始凭证 LLM 识别（升级正则）
1. WHEN 上传原始凭证（记账凭证/发票/出入库单），THEN SHALL 用 LLM 识别（替代正则）
2. WHEN LLM 识别完成，THEN SHALL 逐份确认（复用 V3 Req6 确认流）
3. THE system SHALL 支持 evidence_group（一抽凭行↔多原始凭证）

### 需求 4：缺失资料催收
1. WHEN PBC 项逾期未收，THEN SHALL 自动建 IssueTicket（source=pbc）
2. WHEN 催收触发，THEN SHALL 通知相关人员

## 范围边界
- 依赖 vllm-httpx-bugfix（LLM 识别）
- 依赖 wp-traceability-panel（附件入网）
- 不做客户端 portal（仅内部系统）
