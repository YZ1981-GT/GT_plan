# 设计文档：底稿科目结论 AI 副驾驶

## 概述

本 spec 将 AI 能力接入 D1-C / D2-C 科目结论场景，验证“LLM 作为底稿编制副驾驶”的最小闭环。治理层复用现有 `ai_content_log_service` 和 AI gate rule，不新增平行机制。

## 核心设计

### 1. AIConclusionContext

新增上下文组装服务：

- `backend/app/services/workpaper_ai_conclusion_context_service.py`

上下文结构：

```json
{
  "project_id": "uuid",
  "account_package_id": "D2_accounts_receivable",
  "wp_code": "D2",
  "conclusion_sheet": "D2-C",
  "audit_sheet_summary": {},
  "program_status_summary": {},
  "field_sources": {},
  "confirmation_summary": {},
  "analysis_summary": {},
  "adjustment_impact": {},
  "disclosure_impact": {},
  "missing": []
}
```

缺失信息进入 `missing`，不得在 prompt 中暗示 AI 自行补齐。

### 2. Prompt 边界

Prompt 要求输出：

- 审计目标。
- 已执行程序。
- 关键发现。
- 异常/差异说明。
- 结论草稿。
- 引用来源列表。
- 缺失资料提示。

Prompt 禁止：

- 直接改变系统金额。
- 编造函证、附件、程序状态。
- 输出未来源化的确定性判断。
- 绕过人工确认。

### 3. AI 内容日志复用

AI 生成后调用既有日志机制：

```text
generate_conclusion_draft
  -> build AIConclusionContext
  -> call model / existing AI service
  -> wrap_ai_output_with_log / ai_content_log_service
  -> return pending draft id
```

草稿进入结论字段前必须经过确认或修订后确认。

每条结论草稿日志必须携带目标绑定信息：

```json
{
  "account_package_id": "D2_accounts_receivable",
  "wp_id": "uuid",
  "wp_code": "D2",
  "sheet_type": "conclusion",
  "sheet_name": "D2-C",
  "field_id": "d2.conclusion.overall_conclusion"
}
```

该绑定用于工作包 pending 状态定位、AI 内容治理面板跳转、sign-off 阻断解释和保存结论时的后端校验。

### 4. 前端交互

新增或扩展组件：

- `WorkpaperAIConclusionPanel.vue`
- `AiContentConfirmDialog.vue` 复用或扩展。
- D1-C / D2-C 结论区域增加“生成 AI 草稿”入口。

状态：

- `pending`：显示 AI 草稿标签、来源摘要、确认/修订/拒绝按钮。
- `confirmed`：显示已确认标记、确认人、确认时间。
- `revised`：显示 AI 原文和用户修订文。
- `rejected`：显示拒绝原因，不进入结论。

### 5. Sign-off gate

现有 `AIContentMustBeConfirmedRule` 已扫描 `ai_content_log` pending 项。D1-C / D2-C 接入后不新增规则，只保证草稿写入日志且 pending 状态正确。

保存 D1-C / D2-C 正式结论时，后端必须根据目标绑定检查相关 AI log 状态：

- `pending`：拒绝保存为正式结论，返回待确认 AI 内容错误。
- `confirmed` / `revised_confirmed`：允许保存，并记录确认人。
- `rejected`：不得将 AI 草稿内容写入正式结论；用户可另行手写结论。

### 6. API 草案

- `POST /api/projects/{project_id}/account-packages/{package_id}/ai-conclusion/draft`
- `GET /api/projects/{project_id}/account-packages/{package_id}/ai-conclusion/context`
- `POST /api/ai-content-logs/{log_id}/confirm`
- `POST /api/ai-content-logs/{log_id}/revise-confirm`
- `POST /api/ai-content-logs/{log_id}/reject`

后 3 个优先复用已有 AI content log API；若已有路由命名不同，以既有路由为准。

## 不在范围

- 不实现通用聊天。
- 不覆盖所有底稿结论。
- 不替代复核意见。
- 不新增 AI 内容治理表。

## 现有代码锚点

### 后端

- `backend/app/services/ai_content_log_service.py`
- `backend/app/services/gate_rules_ai_content.py`
- `backend/tests/test_ai_content_confirm_flow.py`
- `backend/tests/test_ai_content_gate_rule.py`

### 前端

- `audit-platform/frontend/src/components/ai/AiContentConfirmDialog.vue`
- `audit-platform/frontend/src/components/ai/AiContentBadge.vue`
- `audit-platform/frontend/src/components/ai/AiContentPendingBanner.vue`
- `audit-platform/frontend/src/components/ai/AIContentReviewPanel.vue`

## 迁移策略

1. D1-C 先接入，使用最少上下文：审定表摘要、程序状态、字段来源、调整影响。
2. 确认 pending 阻断链路有效。
3. D2-C 再接入函证摘要、坏账/账龄、期后回款。
4. 将上下文组装能力抽象为后续复核回复、分析说明草稿可复用服务。

## 风险与回滚

- 风险：上下文不完整导致 AI 草稿质量不稳定。  
  回滚：缺失项显式展示，并允许用户只生成结构化提纲。
- 风险：AI 草稿绕过确认进入结论。  
  回滚：后端保存结论时检查 AI log 状态。
- 风险：前端确认交互与已有 AI 组件重复。  
  回滚：优先复用 `AiContentConfirmDialog`，只增加结论场景包装。
