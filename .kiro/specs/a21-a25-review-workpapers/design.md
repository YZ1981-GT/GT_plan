# A21~A25 各角色复核底稿 — 设计文档

## 前置依赖

> **权威定义**：[completion-phase-infra](../completion-phase-infra/requirements.md)（PRE-2、持久化、E-FIX）。  
> item_id 增量注册：[persistence.md](../completion-phase-infra/persistence.md) §review-checklist。

---

## 架构总览

| 模式 | 底稿 | componentType | 持久化 | 打开方式 |
|------|------|---------------|--------|----------|
| 角色复核 HTML | A21-1 ~ A25-2 | `review-checklist` | checklist_responses | 底稿目录 / A1 chip（P1） |
| 程序表父码 | A21 ~ A25 | `a-program-console` 或目录聚合 | procedure_instances | 可选；**不**替代子码填写 |
| 归档交付 | 同上 | xlsx 导出（plus） | PRE-2 filler | plus |

**xlsx 两 sheet → UI 两区**：

| 实物 sheet | UI 区域 | item_id |
|------------|---------|---------|
| 复核表（检查项） | 检查项列表 | `{wp_code}-chk-{seq:02d}` |
| 复核记录 | textarea | `{wp_code}-record` |
| 模板签字区 | 通过/退回按钮 | `{wp_code}-sign` |

---

## 架构决策

### 配置驱动 vs 代码分支

**纯配置驱动**：10+ 变体由 `a21_a25_review_definitions.json` + 项目上下文决定；`GtReviewChecklist.vue` 零角色分支。

### 持久化唯一源（⚠️ 与现有代码对齐）

| 决策 | 说明 |
|------|------|
| **权威表** | `checklist_responses`（与 A17/A18 一致） |
| **`ReviewChecklistRecord`** | core 阶段 **停止新写入**；只读迁移或废弃 |
| **`ReviewWorkflowService.get_review_panel`** | 重构为：读 definitions + checklist_responses + review-context；**不**再维护平行 item 列表 |
| **`review_records`** | 仅单元格批注；**禁止**用于 A21~A25 签字 |

### componentType 与 override（P0 必做）

父码 fallback 不可靠时须 **显式注册子码**：

```python
# wp_classification_service._WP_CODE_OVERRIDE（P0 追加）
"A21-1": "review-checklist", "A21-2": "review-checklist",
"A22-1": "review-checklist", "A22-2": "review-checklist",
"A23-1": "review-checklist", "A23-2": "review-checklist",
"A24-1": "review-checklist", "A24-2": "review-checklist",
"A25-1": "review-checklist", "A25-2": "review-checklist",
# 父码保留
"A21": "review-checklist", ... "A25": "review-checklist",
```

`htmlRendererRegistry`：`review-checklist` → `GtReviewChecklist.vue`（替换 `ReviewChecklistPanel.vue`）。

### 与 checklist-table (A1-15) 的区别

| 维度 | checklist-table | review-checklist |
|------|-----------------|------------------|
| 数据源 | xlsx 529 行 parser | audit → definitions JSON |
| 适用性 | Y/XI/XW/NA 四态 | Y/N/NA + auto_na |
| 签字 | 无 | pass/reject → `-sign` |
| 复核记录 | 无 | `-record` textarea |
| 多角色 | 单表 | 5 角色 × 审计类型 |

---

## 数据模型

### `a21_a25_xlsx_audit.json`（audit 阶段产出）

每模板条目：`wp_code`, `sheets[]`, `items[]`（seq, content, columns, cell_ref 可选）, `sign_block`（可选）。

### `a21_a25_review_definitions.json`（runtime 权威）

由 audit JSON 生成；结构见 requirements §1。`review_checklist_templates.json` 在 audit 完成后 **合并或废弃**，避免双源。

### 版本选择：`a21_a25_version_selector.py`

```python
async def get_applicable_review_templates(db, project_id) -> list[dict]:
    """类比 a17_5_version_selector；返回 wp_code + mandatory + applicable + reason"""
```

规则摘要：

- `business_category` 前缀过滤 A21~A25 可达角色  
- `audit_type` → -1 / -2 / 两者  
- `is_large_soe` → A24-1 / A25-1 文件名变体  
- A 类才 applicable A24/A25  

API：`GET /api/projects/{pid}/a21/applicable-review-templates`

---

## 前端设计

### GtReviewChecklist.vue

Props：`projectId`, `wpId`, `wpCode`

```
┌──────────────────────────────────────────────┐
│  角色: 项目现场负责人  |  财报审计  | A类        │
├──────────────────────────────────────────────┤
│  进度: ████████░░ 12/15 (80%)                │
├──────────────────────────────────────────────┤
│  ☑ 1. 具体审计计划已经实施…                   │
│  ▨ 10. 组件单位… [N/A - 无组件审计]           │
├──────────────────────────────────────────────┤
│  复核记录： [ textarea ]                      │
├──────────────────────────────────────────────┤
│  [通过] [退回]                                │
└──────────────────────────────────────────────┘
```

### 数据流

1. `GET /api/projects/{pid}/a21/review-definitions?wp_code=A21-1` → items + meta  
2. `GET /api/workpapers/{wpId}/checklist-responses` → 已保存  
3. `GET /api/projects/{pid}/review-context` → auto_na 布尔  
4. 勾选 → debounce 1500ms → PUT checklist-responses  
5. 通过/退回 → POST `.../review-sign` → 写 `{wp_code}-sign` → PATCH procedure_instances（core）

---

## 后端设计

### 文件

| 文件 | 分期 | 职责 |
|------|------|------|
| `data/a21_a25_xlsx_audit.json` | audit | 实物列映射 |
| `data/a21_a25_review_definitions.json` | lite | 运行时定义 |
| `services/review_checklist_service.py` | lite | 加载定义 + review-context + auto_na |
| `services/a21_a25_version_selector.py` | core | 适用模板列表 |
| `routers/a21_review.py`（或扩 `review_workflow.py`） | lite/core | definitions / review-context / review-sign |

### API

```
GET  /api/projects/{pid}/review-context
GET  /api/projects/{pid}/a21/applicable-review-templates
GET  /api/projects/{pid}/a21/review-definitions?wp_code=A21-1
POST /api/workpapers/{wpId}/review-sign
     → body: { action: "pass"|"reject", comment?: string }
     → 写 checklist_responses item_id="{wp_code}-sign"
```

checklist-responses CRUD：**已有**，复用。

### 迁移 V087

```sql
-- V087__projects_audit_context.sql（⚠️ 非 V086）
ALTER TABLE projects ADD COLUMN IF NOT EXISTS audit_type VARCHAR(32) DEFAULT 'financial';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS is_large_soe BOOLEAN DEFAULT false;
```

### auto_na 判定（review-context）

```python
async def get_review_context(db, project_id) -> dict:
    # has_component_auditor: wp_index 存在组件审计相关底稿
    # has_it_audit: A27 / B60-2-x 等
    # is_large_soe, audit_type, business_category 来自 projects
```

### checkCompletion（GtAProgramConsole）

| case | 判定 |
|------|------|
| A21 / A22 / A23 | 对应 `-1`/`-2` 子码 `-sign` conclusion=pass（按 audit_type 选子码） |
| A24 / A25 | 适用子码 `-sign` pass；不适用 → none |

auto_data_source（A1 procedure）：`a21_sign_status`, `a22_sign_status`, `a23_sign_status`, `review_progress`（已有 A24/A25）。

---

## 持久化契约

| 数据 | item_id | conclusion | remark |
|------|---------|------------|--------|
| 检查项 | `{wp_code}-chk-{seq:02d}` | Y/N/NA | 备注 |
| 复核记录 | `{wp_code}-record` | done | 正文 |
| 签字 | `{wp_code}-sign` | pass/reject | JSON |

示例：`A21-1-chk-01`, `A21-1-record`, `A21-1-sign`

完成态（checkCompletion）：适用子码 `-sign` = pass。

---

## E2E 与种子

| ID | 内容 | 夹具 |
|----|------|------|
| E20 | A21-1 勾选 1 项 → 刷新不丢 | FIX-A |
| E21 | 签字 pass → A1 步骤 ✓ | FIX-A |
| E22 | xlsx 导出含 √ | FIX-A |

`seed_fix_projects.py`：FIX-A/B 须含 **A21-1, A22-1, A23-1, A24-1, A25-1** 等子码实例。

---

## 不做

- 不建 A21~A25 独立程序表 JSON（子码靠目录 + A1 ref_index）
- 不用 LLM 自动复核（plus 仅规则预填）
- 不用 `review_records` 存签字
- 不处理 A26/A27/A28（已有其他 spec）
