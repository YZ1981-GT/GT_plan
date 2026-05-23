# 前后端联动测试 — 关键端点 Response Checklist

## 概述

账表导入功能涉及 5 个关键端点，前端组件直接依赖其响应结构。
任何字段变更必须同步更新对应的 TypeScript 接口。

---

## 关键端点清单

### 1. `POST /api/projects/{pid}/ledger-import/detect`

| 维度 | 值 |
|------|-----|
| 后端文件 | `backend/app/routers/ledger_import_v2.py` |
| 前端文件 | `audit-platform/frontend/src/components/ledger/LedgerImportDialog.vue` |
| 响应模型 | `LedgerDetectionResult` |
| 关键字段 | `upload_token`, `detected_year`, `files[].sheets[].table_type`, `files[].sheets[].column_mappings[]`, `total_rows_estimate`, `estimated_duration_seconds`, `scale_warnings` |

### 2. `POST /api/projects/{pid}/ledger-import/submit`

| 维度 | 值 |
|------|-----|
| 后端文件 | `backend/app/routers/ledger_import_v2.py` |
| 前端文件 | `audit-platform/frontend/src/components/ledger/LedgerImportDialog.vue` |
| 响应模型 | `{job_id, status}` |
| 关键字段 | `job_id: UUID`, `status: "queued"` |

### 3. `GET /api/projects/{pid}/ledger-import/active-job`

| 维度 | 值 |
|------|-----|
| 后端文件 | `backend/app/routers/ledger_import_v2.py` |
| 前端文件 | `audit-platform/frontend/src/layouts/ThreeColumnLayout.vue` |
| 响应模型 | 轮询状态对象 |
| 关键字段 | `status`, `progress` (0-100), `message`, `current_phase`, `queue_position`, `global_max_concurrent` |

### 4. `GET /api/projects/{pid}/ledger-import/jobs/{id}/diagnostics`

| 维度 | 值 |
|------|-----|
| 后端文件 | `backend/app/routers/ledger_import_v2.py` |
| 前端文件 | `audit-platform/frontend/src/components/ledger/DiagnosticPanel.vue` |
| 响应模型 | 诊断结果 |
| 关键字段 | `result_summary.findings[]`, `result_summary.blocking_findings[]`, 每条 finding 含 `code`, `severity`, `message`, `location`, `hint`, `explanation` |

### 5. `GET /api/projects/{pid}/ledger-import/datasets/history`

| 维度 | 值 |
|------|-----|
| 后端文件 | `backend/app/routers/ledger_datasets.py` |
| 前端文件 | `audit-platform/frontend/src/components/ledger/ImportTimeline.vue` |
| 响应模型 | `ActivationRecord[]` |
| 关键字段 | `id`, `dataset_id`, `action`, `performed_at`, `performed_by`, `reason`, `record_summary`, `duration_ms` |

---

## How to verify

1. **自动化 E2E**：运行 `python scripts/e2e_http_curl.py`
   - 覆盖端点 1-4 的完整链路（detect → submit → poll → diagnostics）
   - 含 Layer 3 DB 断言（去重 + 辅助和 = 主表）

2. **手动验证 DiagnosticPanel**：
   - 导入一份含错误的样本（如缺少关键列）
   - 确认 DiagnosticPanel 正确展示 findings + hint 卡片
   - 确认 drill_down 链接可跳转到明细

3. **批量回归**：运行 `python scripts/e2e_9_companies_batch.py`
   - 覆盖 9 家企业的多样化场景（单文件/多文件/CSV/大文件）

---

## 变更规约

> **If adding new fields to any response, update the corresponding TypeScript interface in the frontend.**

- 后端新增字段 → 同步更新 `ledgerImportV2Api.ts` 中的 interface
- 后端删除/重命名字段 → 前端组件必须同步修改，否则 vue-tsc 不会报错但运行时静默失败
- 响应结构变更（如 `errors[]` → `result_summary.findings[]`）→ 前端数据归一化层必须适配
