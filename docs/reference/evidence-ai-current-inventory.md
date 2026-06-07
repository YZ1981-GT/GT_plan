# 附件证据、AI 内容、知识库现状盘点

> 输出时间：2026-06 P0 落地前盘点

## 1. 附件相关模型与 API

### 模型层

| 模型 | 文件 | 说明 |
|------|------|------|
| `Attachment` | `backend/app/models/attachment_models.py` | 附件主表，含 OCR/版本/存储类型 |
| `AttachmentWorkingPaper` | 同上 | 附件与底稿关联（行级绑定 row_ref） |

### 服务层

| 服务 | 文件 | 说明 |
|------|------|------|
| `attachment_service` | `backend/app/services/attachment_service.py` | 上传/下载/删除/OCR |
| `attachment_lineage_service` | `backend/app/services/attachment_lineage_service.py` | 附件血缘追溯 |
| `attachment_impact_service` | `backend/app/services/attachment_impact_service.py` | 删除前影响范围查询（P0 增强） |

### API 端点

| 路由 | 文件 | 说明 |
|------|------|------|
| `/api/projects/{pid}/attachments` | `backend/app/routers/attachments.py` | CRUD + 上传/下载 |

### 前端入口

| 组件/视图 | 文件 | 说明 |
|-----------|------|------|
| `AttachmentHub` | `audit-platform/frontend/src/views/AttachmentHub.vue` | 附件管理主视图 |
| `AttachmentPreviewDrawer` | `audit-platform/frontend/src/components/common/AttachmentPreviewDrawer.vue` | 预览抽屉 |

---

## 2. OnlyOffice / WOPI / vue-office / office_preview 实际入口

### 预览/编辑技术栈

| 技术 | 用途 | 入口 |
|------|------|------|
| OnlyOffice | 在线协同编辑 docx/xlsx | 后端 WOPI 接口 + 前端 OnlyOffice JS SDK |
| WOPI | Office 在线编辑协议 | 后端实现 WOPI host 端点 |
| vue-office (`@vue-office/docx`, `@vue-office/excel`) | 纯前端预览 | `AttachmentPreviewDrawer` 内按文件类型切换 |
| PDF.js / 内置浏览器预览 | PDF 预览 | 同上，PDF 类型走浏览器内置 |
| 后端预览服务 (LibreOffice 转 PDF) | 不支持前端直预览的格式 | `/api/preview/{id}` 返回 PDF 流 |

### 健康检查

- OnlyOffice 健康端点：`/healthcheck`（OnlyOffice 容器）
- 当前无统一 health 展示组件（P0-4 新建 `AttachmentActionBar` 解决）

---

## 3. AI 内容已有确认/待确认链路

### 模型层

| 模型/表 | 文件 | 说明 |
|---------|------|------|
| `ai_content_log` | `backend/app/services/ai_content_log_service.py` | AI 内容日志记录 |
| `ai_chat_session` / `ai_chat_message` | `backend/app/models/ai_models.py` | AI 对话持久化 |

### 服务层

| 服务 | 文件 | 说明 |
|------|------|------|
| `ai_content_gate` | `backend/app/services/ai_content_gate.py` | 状态机 + confirmed 门控 |
| `ai_content_log_service` | `backend/app/services/ai_content_log_service.py` | AI 内容日志 CRUD |
| `doc_ai_chat` | `backend/app/services/doc_ai_chat.py` | 文档级 AI 对话 |

### API 端点

| 路由 | 文件 | 说明 |
|------|------|------|
| `/api/ai-content/*` | `backend/app/routers/ai_content.py` | AI 内容管理 |
| `/api/projects/{pid}/ai-content/pending` | 同上 | 待确认列表 |

### 前端组件

| 组件 | 文件 | 说明 |
|------|------|------|
| `AiContentPendingBanner` | `.../components/ai/AiContentPendingBanner.vue` | 待确认计数横幅 |
| `AiContentConfirmDialog` | `.../components/ai/AiContentConfirmDialog.vue` | 确认弹窗 |

### 状态机当前定义

```
suggestion → draft → confirmed
suggestion → rejected
draft → rejected
```

- `AI_CONTENT_CONFIRMATION_STRICT` 模块级开关（默认 False = warning only）
- 已实现：`can_enter_formal_output(status, strict)` 门控函数

---

## 4. 复核相关模型与 API

### 服务层

| 服务 | 文件 |
|------|------|
| `review_conversation_service` | `backend/app/services/review_conversation_service.py` |
| `wp_review_service` | `backend/app/services/wp_review_service.py` |

### 前端

| 组件/视图 | 文件 |
|-----------|------|
| `ReviewWorkbench` | `audit-platform/frontend/src/views/ReviewWorkbench.vue` |
| `review/*` | `audit-platform/frontend/src/components/review/*` |

---

## 5. 交付件相关

| 项目 | 文件 |
|------|------|
| spec | `.kiro/specs/audit-report-deliverable-center` |
| `deliverable_service` | `backend/app/services/deliverable_service.py` |
| `export_task_service` | `backend/app/services/export_task_service.py` |

---

## 6. 知识库相关

| 服务 | 文件 | 说明 |
|------|------|------|
| `knowledge_index_service` | `backend/app/services/knowledge_index_service.py` | 向量索引管理 |
| `knowledge_folder_service` | `backend/app/services/knowledge_folder_service.py` | 文件夹管理 |
| `index_source` | `backend/app/services/index_source.py` | 索引来源 |

---

## 7. EvidenceRef 统一引用（MVP 已建）

| 层 | 文件 | 状态 |
|---|------|------|
| 后端 schema | `backend/app/schemas/evidence_ref.py` | ✅ MVP 已建 |
| 前端类型 | `audit-platform/frontend/src/types/evidenceRef.ts` | ✅ MVP 已建 |
| 影响范围 service | `backend/app/services/attachment_impact_service.py` | ✅ MVP stub |
| AI 门控 | `backend/app/services/ai_content_gate.py` | ✅ MVP 已建 |

---

## 8. P0 增强方向

1. **EvidenceRef schema**：增加路由解析、序列化工具函数
2. **附件影响范围**：从 stub 升级为真实引用查询（metadata JSON 方案）
3. **AttachmentActionBar**：统一预览/编辑/下载/引用动作
4. **AI 内容状态机**：增加 STRICT 环境变量配置、确认弹窗统一
