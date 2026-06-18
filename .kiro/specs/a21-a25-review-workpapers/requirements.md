# A21~A25 各角色复核底稿（配置驱动重构）

## 背景

A21~A25 是审计完成阶段 **5 个角色** 的结构化复核检查底稿：

| 底稿 | 角色 | 子底稿（财报 / 内控） | xlsx sheet |
|------|------|----------------------|------------|
| A21 | 项目现场负责人 | A21-1 / A21-2 | 复核表 + 复核记录 |
| A22 | 项目负责经理 | A22-1 / A22-2 | 同上 |
| A23 | 项目合伙人 | A23-1 / A23-2 | 同上 |
| A24 | 质量复核合伙人 | A24-1（大型国企 / 非国企）/ A24-2 | 同上 |
| A25 | 质量控制复核人 | A25-1（大型国企 / 非国企）/ A25-2 | 同上 |

当前 `ReviewChecklistPanel.vue` 是壳组件：调不存在的 API → 降级 5 条硬编码 → 无持久化。

**核心需求**：配置驱动；按 `business_category` + `audit_type` + `is_large_soe` 选模板；检查项与 auto_na 来自 **实物 xlsx audit**，非手写臆测。

---

## audit-xlsx（A21~A25 专用）

> 产出 `backend/data/a21_a25_xlsx_audit.json`；与 infra **PRE-4 方法论** 同构，但 **不占用** A17 的 `a17_xlsx_audit.json`。  
> **未完成 audit 前**：`review_checklist_templates.json` 仅作草稿，**不得**标 P0 绿。

| 文件 | 说明 |
|------|------|
| A21-1 ~ A23-2 | 各 2 sheet（复核表 + 复核记录）；检查项约 15~25 条/表 |
| A24-1 ×2 / A25-1 ×2 | 大型国企 vs 非国企文件名各一；audit 须区分 `enterprise_variant` |
| A24-2 / A25-2 | 内控版 |

**DoD**：audit JSON 含每模板 sheet 名、检查项 seq/content、列语义（Y/N/NA/备注/索引号）、签字区位置；条数与实物一致。

---

## 前置依赖

| 依赖 | 来源 | 说明 |
|------|------|------|
| `checklist_responses` | V085 ✅ | wp_id + item_id 唯一 UPSERT |
| `projects.business_category` | 已有 ✅ | A/B/C；适用性 **唯一入口** 与 A17 相同（`get_category_prefix` + `applicable_categories`） |
| PRE-2 `docx_template_filler.py` | infra ✅ | P2 xlsx/Word 导出复用颜色语义 |
| [persistence.md](../completion-phase-infra/persistence.md) | infra | item_id 契约（本 spec 增量见 design） |
| [e2e-matrix.md](../completion-phase-infra/e2e-matrix.md) | infra | E20–E22 |
| `seed_fix_projects.py` | infra E-FIX | 须含 A21-1~A25 子码（非仅父码 A21） |

### 缺失字段（迁移 **V087**，⚠️ V086 已被 A16 占用）

| 字段 | 类型 | 说明 |
|------|------|------|
| `projects.audit_type` | VARCHAR(32) DEFAULT 'financial' | financial / internal_control / combined |
| `projects.is_large_soe` | BOOLEAN DEFAULT false | 影响 A24-1 / A25-1 国企版选择 |

### START GATE：与「底稿级复核」的边界

| 机制 | 层次 | 本 spec 关系 |
|------|------|--------------|
| `WpReviewStatus` + submit-review | 单张底稿编制/复核状态机 | **不替代**；A21 auto_check 可 **读取** 汇总 |
| `review_records` 表 | 单元格复核批注（对话式） | **不用于** A21~A25 签字 |
| A21~A25 | 角色级结构化复核记录 | **权威填写面**；持久化 → `checklist_responses` |

签字（P0 轻量方案）：`checklist_responses` item_id `{wp_code}-sign`；P1 可升级独立 `review_signing` 表。

---

## 适用条件

| 条件 | A21 | A22 | A23 | A24 | A25 |
|------|-----|-----|-----|-----|-----|
| A 类 | ✅ | ✅ | ✅ | ✅ | ✅ |
| B 类 | ✅ | ✅ | ✅ | ❌ | ❌ |
| C 类 | ✅ | ✅ | ❌ | ❌ | ❌ |

- `audit_type=combined` → 同时适用 -1（财报）与 -2（内控）子底稿
- A24/A25：`is_large_soe` → 选 A24-1 / A25-1 国企版或非国企版（见 audit 文件名）

**适用性判定（与 A17 统一）**：

```python
# 唯一入口：ProcedureTableService._check_applicable
# 步骤级 applicable_categories + business_category 前缀
# 禁止：另写一套与程序表分叉的 select_* 逻辑（版本选择服务仅返回 wp_code 列表，不重复判 applicable）
```

---

## A1 程序表联动（须与实物 / JSON 对账后定稿）

现状 `procedure_table_templates.json`：**仅 seq15** 指向 `A24,A25`；**无** A21→A22→A23 步骤。

本 spec **P1** 须扩充 A1（或文档化「底稿目录直开、程序表只挂质控」——二选一，**实施前在 audit 阶段确认 A1 实物程序表**）：

| seq（建议） | 程序 | ref_index | applicable_categories | auto_data_source（P1） |
|-------------|------|-----------|----------------------|------------------------|
| 15a | 现场负责人复核 | `A21-1` / `A21-2` | A,B,C | `a21_sign_status` |
| 15b | 项目负责经理复核 | `A22-1` / `A22-2` | A,B,C | `a22_sign_status` |
| 15c | 项目合伙人复核 | `A23-1` / `A23-2` | A,B | `a23_sign_status` |
| 15（现有） | 项目质量控制复核 | `A24,A25` | A,B | `review_progress` |

> A17-5 核对表内「经理/合伙人是否已复核底稿」预设索引 A22/A23 — **引用** 本系列签字状态，不替代 A21~A25 底稿本身。

---

## 交付分期

| 分期 | 范围 | DoD |
|------|------|-----|
| **audit** | 10× xlsx 深读 → `a21_a25_xlsx_audit.json` | 条数与实物一致 |
| **lite** | A21-1 单模板全链路 | 15 条渲染；勾选刷新不丢；auto_na 灰化 |
| **core** | 5 角色 × 财报/内控 + 签字 + A1 联动 | B 类打开 A24 → 不适用；签字 pass → A1 ✓ |
| **plus** | 预填建议 + xlsx 导出 + E2E | E20–E22 绿 |

---

## 需求

### 1. 定义文件（权威源 = audit JSON）

- 从 `a21_a25_xlsx_audit.json` 生成 **`a21_a25_review_definitions.json`**
- 每模板：`role` / `audit_type` / `applicable_categories` / `enterprise_variant` / `items[]`
- `auto_na_condition`：`no_component_auditor` / `no_it_audit` / `not_large_soe` / `no_internal_control_audit` 等（见 design）

### 2. 版本选择（类比 A17-5）

- `a21_a25_version_selector.py` + `GET /api/a21/applicable-review-templates`
- 返回 `[{ wp_code, mandatory, applicable, reason }]`；程序表/底稿列表展示 badge

### 3. 前端 `GtReviewChecklist.vue`（替换 `ReviewChecklistPanel.vue`）

1. **角色信息栏**：角色 + 审计类型 + business_category  
2. **检查项区**：Y / N / NA + 备注；auto_na → disabled + 灰化  
3. **复核记录区**：textarea → `{wp_code}-record`  
4. **签字区**：通过 / 退回 → `{wp_code}-sign`  

进度：NA 不计入分母；未填完适用项时禁用「通过」。

### 4. 持久化（与 infra 一致）

| 数据 | item_id | conclusion | remark |
|------|---------|------------|--------|
| 检查项 | `{wp_code}-chk-{seq:02d}` | Y / N / NA | 备注 |
| 复核记录 | `{wp_code}-record` | done | 正文 |
| 签字 | `{wp_code}-sign` | pass / reject | JSON(signer, date, comment) |

debounce 1500ms → PUT `/api/workpapers/{wpId}/checklist-responses`

### 5. 签字联动（core）

- POST `review-sign` → 写 `-sign` → 更新 A1 `procedure_instances` 对应步骤（见上表 auto_data_source）
- `GtAProgramConsole.checkCompletion` 扩展 A21/A22/A23/A24/A25 case（读 `-sign` conclusion）

### 6. 导出（plus，PRE-2）

- checklist_responses → 回填 xlsx 模板（√ / N/A / 备注 / 签字区）
- 不重复实现颜色语义

### 7. 自动预填建议（plus）

- 底稿完成率、调整分录复核状态等 → UI 建议勾选（可覆盖，非 LLM）

---

## 现状与差距

| 能力 | 目标 | 代码现状 | 分期 |
|------|------|----------|------|
| xlsx audit | `a21_a25_xlsx_audit.json` | ❌ | audit |
| 定义 JSON | 来自 audit | ⚠️ `review_checklist_templates.json` 草稿（条数不足） | lite |
| GtReviewChecklist | 配置驱动 | ✅ GtReviewChecklist.vue | lite |
| checklist_responses | UPSERT | ✅ debounce 1500ms | lite |
| version_selector | 10+ 子码 | ✅ a21_a25_version_selector | core |
| 签字 + A1 联动 | `-sign` + procedure | ✅ review-sign + A1 seq15–17 | core |
| ReviewWorkflowService | 薄封装或废弃 | ✅ get_review_progress 读 checklist | core |
| 子码 wp_index | A21-1 等 | ✅ seed FIX-A | seed E-FIX |
| xlsx 导出 | PRE-2 | ✅ a21_xlsx_exporter | plus |
| E2E E20–E22 | Playwright | ✅ a21-lite / a21-core-plus | plus |

## 关联模块

- A1 程序表（步骤 status / checkCompletion）
- A17-5（核对项引用 A22/A23 签字）
- completion-phase-infra（持久化、PRE-2、E-FIX）
- `ReviewWorkflowService`（见 design §后端整合，避免双写）
