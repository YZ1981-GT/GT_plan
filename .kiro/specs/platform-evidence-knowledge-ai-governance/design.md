# 设计文档：附件证据、知识库与 AI 治理闭环

## 概述

本 spec 将附件、复核证据、交付件、知识库和 AI 内容治理串成证据闭环。目标是让每个审计结论、复核意见、AI 建议、交付文件都能追溯到证据来源，并能被合伙人、质控和 EQCR 查验。

## 核心设计

### 1. EvidenceRef

新增统一证据引用结构：

| 字段 | 说明 |
|---|---|
| `evidence_type` | attachment / workpaper_cell / report_paragraph / note_table / ai_output / deliverable |
| `evidence_id` | 证据 ID |
| `project_id` | 项目 |
| `year` | 年度 |
| `label` | 展示名称 |
| `route` | 可跳转路由 |
| `hash` | 文件或内容 hash |
| `version` | 版本 |

附件、复核意见、AI 内容和交付件都可挂 EvidenceRef。

### 2. 附件证据属性

扩展附件元数据：

- 来源
- 取得日期
- 提供方
- 关联底稿
- 是否关键证据
- 引用次数
- OCR/AI 识别状态

删除或替换前调用影响范围查询。

### 3. Office 预览/编辑统一入口

前端统一动作：

| 动作 | 技术实现 |
|---|---|
| 预览 | vue-office / PDF / 后端预览 |
| 编辑 | OnlyOffice/WOPI |
| 下载 | 文件服务 |
| 引用 | EvidenceRef |

用户不感知 OnlyOffice、WOPI、vue-office、LibreOffice 等技术差异。

### 4. 复核意见证据链

复核意见新增证据引用：

```text
review issue
  -> target object
  -> evidence refs
  -> response
  -> close evidence
```

关闭必须提供关闭依据。

### 5. 交付件中心

交付件中心作为报告、附注、签发文件和归档文件的唯一文件真源：

- 版本链
- 文件 hash
- 预览路径
- 下载路径
- 签发状态
- 来源快照

与 `audit-report-deliverable-center` spec 对齐。

### 6. 知识库真源与索引

明确：

- DB 文档元数据为主源。
- 文件系统/对象存储保存原文。
- 向量索引为派生物。

索引记录包含文档版本，文档更新后旧索引 stale。

### 7. AI 内容状态机

```text
suggestion -> draft -> confirmed
suggestion -> rejected
draft -> rejected
```

AI 内容进入底稿/附注/报告/签发/EQCR 前必须 confirmed。

## 不在范围

- 不重写 LLM provider。
- 不更改现有报告导出主流程。
- 不对历史 AI 输出强制补全 prompt。

## 现有代码锚点

### 附件与证据

- `backend/app/services/attachment_service.py`
- `backend/app/routers/attachments.py`
- `backend/app/models/attachment_models.py`
- `backend/app/services/attachment_lineage_service.py`
- `audit-platform/frontend/src/views/AttachmentHub.vue`
- `audit-platform/frontend/src/components/common/AttachmentPreviewDrawer.vue`

### 复核与质量

- `backend/app/services/review_conversation_service.py`
- `backend/app/services/wp_review_service.py`
- `audit-platform/frontend/src/views/ReviewWorkbench.vue`
- `audit-platform/frontend/src/components/review/*`

### 交付件

- `.kiro/specs/audit-report-deliverable-center`
- `backend/app/services/deliverable_service.py`
- `backend/app/services/export_task_service.py`

### 知识库与 AI

- `backend/app/services/knowledge_index_service.py`
- `backend/app/services/knowledge_folder_service.py`
- `backend/app/services/index_source.py`
- `backend/app/services/ai_content_log_service.py`
- `backend/app/routers/ai_content.py`
- `audit-platform/frontend/src/components/ai/AiContentPendingBanner.vue`
- `audit-platform/frontend/src/components/ai/AiContentConfirmDialog.vue`

## EvidenceRef 与 LinkageContract 边界

- `EvidenceRef` 表示“证据引用”，回答“审计结论依赖哪些证据”。
- `LinkageContract` 表示“数据流引用”，回答“数字从哪里来、影响哪里去”。
- 同一对象可以同时存在两种关系，例如附件 OCR 金额进入底稿时，附件是 EvidenceRef，金额流转是 LinkageContract。

## API 草案

- `GET /api/projects/{pid}/evidence/impact?evidence_type=&evidence_id=`
- `POST /api/projects/{pid}/evidence/refs`
- `GET /api/projects/{pid}/ai-content/pending`
- `POST /api/ai-content/{id}/confirm`
- `POST /api/ai-content/{id}/reject`
- `GET /api/projects/{pid}/knowledge/citations/{citation_id}`

## 迁移策略

1. 先对新上传附件记录证据属性，历史附件不强制回填。
2. AI 内容治理先接入 `ai_content` 已有确认链路，再扩展到底稿/附注/报告。
3. 交付件部分复用 `audit-report-deliverable-center`，本 spec 不重复建版本模型。
4. 知识库先形成真源 ADR，再做索引迁移。

## 风险与回滚

- 风险：附件影响范围查询成本高。  
  回滚：先展示已知引用，未知引用标记“可能存在未扫描引用”。
- 风险：AI confirmed 校验阻断现有生成流程。  
  回滚：先 warning 后 blocking，按模块逐步启用。
