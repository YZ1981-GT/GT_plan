# 设计文档：TSJ 提示词驱动 LLM 复核

## 概述

分 MVP（接线 1 天）→ 增强（分段+结构化 3-4 天）两阶段。核心是把已有的孤儿能力 `review_workpaper_with_prompt` 接线到 router + 前端入口，再增强为按认定分段 + 结构化输出 + 进确认流。

## MVP 设计

### 端点
`POST /api/workpapers/{wp_id}/ai/tsj-review`（wp_ai.py 新增，WP_AI_SERVICE_ENABLED 门控）

### 前端入口
SideStandardsTab.vue 加按钮 → 调端点 → 结果进 AiAssistantSidebar 或独立 drawer

## 增强设计

### 分段策略
按 TSJ 提示词的认定章节（`## 存在性` / `## 完整性` / ...）拆分，每段独立 LLM 调用。

### 结构化输出 JSON schema
```json
{
  "findings": [{
    "issue_type": "数值错误|逻辑错误|披露缺失|证据不足",
    "severity": "high|medium|low",
    "sheet": "应收账款明细",
    "cell_range": "B5:D5",
    "description": "...",
    "evidence_ref": "D2-3!B5",
    "remediation": "..."
  }]
}
```

### 写入 AiContent
每条 finding → `AiContent(content_type='risk_alert', target_cell='{wp_code}:{sheet}:{cell}', confirm_action='pending')`

## 正确性属性

**Property 1**: MVP 端点在 WP_AI_SERVICE_ENABLED=True 时返回非空 LLM 结果。
**Property 2**: 分段复核的段数 == TSJ 提示词中认定章节数。
**Property 3**: 结构化输出的每条 finding 都写入 AiContent 且 confirm_action=pending。

## 依赖
- vllm-httpx-bugfix（硬前置）
- wp-locate-foundation（需求 4 跳证据）
