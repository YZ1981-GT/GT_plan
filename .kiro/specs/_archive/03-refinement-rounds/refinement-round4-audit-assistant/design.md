# Refinement Round 4 — 设计文档

## 概要

本轮聚焦审计助理视角，让助理在单页底稿编辑器内完成 80% 工作：程序要求侧栏、AI 助手侧栏、单元格级定位、上年对比、序时账穿透、附件就地插入。遵守 [README v2.2](../refinement-round1-review-closure/README.md)。

依赖 R1 需求 2 的 `IssueTicket.source='ai'` 枚举值（R1 已预留）。依赖现有 `attachment_service / ledger_penetration_service / continuous_audit_service / wp_chat_service`。

## 架构决策一览

| 决策 | 方案 | 理由 |
|------|------|------|
| AI 侧栏 | 直接嵌入现有 `AIChatPanel.vue`，不重构 | 组件已存在，只缺编辑器集成 |
| 程序要求侧栏数据源 | 聚合 `wp_manuals + procedures + continuous_audit.prior_year_summary` | 不新建表 |
| 单元格红点 | 读 `ReviewRecord where status='open'`（R1 落地的真源） | 与 R1 统一 |
| 对比上年 | 复用 `continuous_audit_service.get_prior_year_workpaper(wp_id)` | 服务已存在，补前端入口 |
| 按金额穿透 | 新增端点 `/ledger/penetrate-by-amount`，不改现有 `/penetrate` | 参数体系完全不同，独立更清晰 |
| 附件就地插入 | 复用 `attachment_service.upload` + `workpaper_attachment_link` | 不新建评审证据模型 |
| 预填充 provenance | `parsed_data.cell_provenance` JSONB，supersede 时清理旧值，最多保留 1 次 | 避免 JSONB 膨胀 |
| AI 脱敏 | AI 调用前先过 `export_mask_service`（若敏感字段） | 防止金额/客户名裸传 LLM |
| 焦点时长隐私 | **纯 localStorage** 不落库（跨轮约束 8） | 消除监控感 |
| 移动端编辑器 | 改只读 HTML 预览（复用 `excel_html_converter`），不做编辑 | Univer 移动端不成熟 |

## 数据模型变更

### 扩展既有字段

```python
# WorkingPaper.parsed_data JSONB 新增 key:
{
  ...既有...,
  "cell_provenance": {
    "D5": {
      "source": "trial_balance" | "prior_year" | "formula" | "ledger" | "manual",
      "source_ref": "E42" | "wp_A12!B3" | None,
      "filled_at": "2026-05-08T10:00:00",
      "filled_by_service_version": "prefill_v1.2"
    }
  }
}
# supersede 策略：重新填充时覆盖旧值，不保留历史（避免膨胀）
```

### 新增表

无。全部复用。

## API 变更

### 新增端点

```
# 按金额穿透（独立于 /ledger/penetrate）
GET /api/projects/{project_id}/ledger/penetrate-by-amount
  params: year, amount, tolerance?=0.01, account_code?, 
          date_from?, date_to?, summary_keyword?
  resp: {matches: [{strategy: 'exact'|'tolerance'|'code+amount'|'summary', items: [...]}]}

# 程序要求聚合
GET /api/projects/{project_id}/workpapers/{wp_id}/requirements
  resp: {manual: str|null, procedures: [...], prior_year_summary: {...}|null}

# 上年对比
GET /api/projects/{project_id}/workpapers/{wp_id}/prior-year
  resp: {wp_id, wp_code, file_url, conclusion, audited_amount} | 404

# 底稿 HTML 预览（移动端）
GET /api/projects/{project_id}/workpapers/{wp_id}/html
  resp: HTML string
  query: mask?=true  (脱敏开关)

# AI 侧栏带上下文问答（扩 wp_chat_service）
POST /api/workpapers/{wp_id}/chat
  body: {message, cell_context?: {cell_ref, value, formula}, procedure_code?}
  resp: {answer, sources: [...]}
  内部：若含敏感字段先过 export_mask_service
```

### 修改既有

```
# workpaper_fill_service.prefill 填充时回写 cell_provenance 到 parsed_data
# (既有签名不变，内部行为扩展)
```

## 前端变更

### 新增组件

```
src/components/workpaper/ProgramRequirementsSidebar.vue
src/components/workpaper/AiAssistantSidebar.vue
src/components/workpaper/PriorYearCompareDrawer.vue
src/components/workpaper/LedgerPenetrateDrawer.vue
src/components/workpaper/CellProvenanceTooltip.vue
src/components/workpaper/AttachmentDropZone.vue
src/components/workpaper/SmartTipList.vue    (替代现有单行 smartTip)
```

### 修改

```
src/views/WorkpaperEditor.vue    (加三栏布局：左程序要求 / 中 Univer / 右 AI)
src/views/MyProcedureTasks.vue    (openWP 时带 ?from_procedure=xxx)
src/views/PersonalDashboard.vue   (新增本周时间线卡片，数据来自 localStorage)
src/views/MobileWorkpaperEditor.vue  (替换为只读 HTML 预览 + 评论)
src/composables/useWorkflowGuide.ts  (补 first_login / first_open_workpaper / first_submit_review)
src/composables/useFocusTracker.ts   (新增；纯 localStorage 实现)
src/router/index.ts               (MobileWorkpaperEditor label 改简化查看版)
```

### Univer 集成

```
- 右键菜单注册 "穿透序时账" 仅金额单元格可见
- Cell hover tooltip 显示 provenance
- Cell decoration 渲染 ReviewRecord 红点
- dragover/drop 事件触发 AttachmentDropZone
```

## 跨轮约束遵守

| 约束 | 本轮落地 |
|------|----------|
| 1 通知字典 | 不新增 |
| 2 权限四点 | role='auditor' 无新动作，只消费既有 |
| 3 状态机 | 不涉及 |
| 4 SOD | 不涉及 |
| 5 SLA | 不涉及 |
| 6 归档章节化 | 不涉及 |
| 7 i18n | 不涉及 |
| 8 焦点时长 | **本轮核心落地**，纯 localStorage 不发后端 |

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 三栏布局屏幕空间不足 | 侧栏可折叠，折叠状态 `localStorage.wp_sidebar_collapsed` |
| AI 侧栏上下文包含敏感数据 | 调用前 `export_mask_service` 过滤金额/客户名 |
| 附件拖拽大文件阻塞 | 20MB 硬上限，超出友好拒绝 |
| 预填 provenance 膨胀 | supersede 策略：重填时覆盖不累积，最多 1 次历史 |
| 序时账穿透结果过多 | 超过 200 条截断提示，建议缩小过滤条件 |
| 焦点时长 localStorage 被清 | 可接受，文档明示非权威数据 |
| 移动端只读仍依赖 Univer 渲染慢 | 改走 `excel_html_converter` HTML 输出，移动端不加载 Univer |

## 测试策略

- 单元测试：`useFocusTracker` 按周归档键 / 按金额穿透四策略 / cell_provenance supersede
- 集成测试：`test_workpaper_editor_integration.py`（程序侧栏 + AI 侧栏 + 穿透 + 对比上年）
- 移动端测试：`test_mobile_workpaper_readonly.py` HTML 预览返回正确
- 性能：按金额穿透 P95 < 2s

## 补充设计（v1.1，需求 11~12）

### 需求 11 编辑软锁

```python
# backend/app/models/workpaper_editing_lock_models.py
class WorkpaperEditingLock(Base, TimestampMixin):
    __tablename__ = "workpaper_editing_locks"
    id: UUID
    wp_id: UUID (indexed, 非唯一——允许历史锁共存，查时过滤 released_at is null)
    staff_id: UUID
    acquired_at: datetime
    heartbeat_at: datetime (indexed)
    released_at: datetime | None
```

**策略**：查"有效锁"判断 `released_at is null AND heartbeat_at > now - 5min`。过期锁由下一次 acquire 或查询时惰性清理（设 `released_at=now`），不跑 worker。

**前端 heartbeat**：`setInterval(120_000)` 续期，失败（网络断/401）停止续期并提示"锁可能已失效"。

### 需求 12 OCR 字段填入

复用 `ocr_service_v2` 已有能力。新端点 `POST /api/attachments/{id}/ocr-fields`：
- 若 `attachment.ocr_status='completed'`，直接返回 `ocr_fields_cache`
- 若 `pending/failed`，异步触发 `unified_ocr_service.recognize + extract_fields`，202 + job_id，前端轮询
- 结果缓存到新字段 `Attachment.ocr_fields_cache: JSONB`（Alembic 新增）

`WorkpaperEditor` Univer 右键菜单依赖当前底稿的 `workpaper_attachment_link`，有关联才显示。

cell_provenance 扩展来源类型，`source='ocr'`、`source_ref='attachment:{id}:{field_name}'`，点击 tooltip 跳附件预览页高亮字段。
