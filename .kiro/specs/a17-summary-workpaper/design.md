# A17 重大事项概要底稿 — 设计文档

## 前置依赖

> **权威定义**：[completion-phase-infra](../completion-phase-infra/requirements.md)。  
> issue_tickets 映射以 infra 为准，本文 §issue_tickets 为摘要引用。

## 架构总览

A17 系列 14 个子底稿按 4 种模式处理：

| 模式 | 底稿 | componentType | 格式 |
|------|------|---------------|------|
| 弹窗 | A17-3/3-1/4/6 | WpPopupDocxEditor | 信函型 docx |
| 核对表 | A17-5-1~5-5 | checklist-table | xlsx→HTML |
| 签署 | A17-7/7A | independence-signing | 已有，本 spec 不增强 |
| 专用 HTML | A17-1, A17-2-1 | a17-summary / kam-workpaper | 结构化编辑+Word 导出 |

### 与 A18-2 共享的「结构化函件编辑」抽象

A17-1（11 章节）与 A18-2（4 议题）共性：

| 共性 | 实现策略 |
|------|----------|
| 分段编辑 + 提示栏不导出 | 共享 CSS 令牌 + 折叠面板组件（可抽 `GtStructuredSection.vue`） |
| 数据存 checklist_responses | 统一 item_id 命名规范（见下） |
| Word 导出 | 共用 `docx_template_filler.py` |
| 表头/签名区 | A18-2 专用；A17-1 无信函表头 |

不强制共用一个 Vue 组件，但**导出管线、颜色语义、checklist_responses 契约必须共用**。

### 适用性判定（统一口径）

```python
# 唯一入口：ProcedureTableService._check_applicable
# 数据源：procedure_table_templates.json 步骤级 applicable_categories
# 项目分类：business_category → get_category_prefix() → "A"|"B"|"C"
# 禁止：template_type == 'listed'、project.is_listed 混用于 A17 适用性
```

弹窗 chip 灰显逻辑：`applicable=false` → `GtIndexChip` disabled + 不加入弹窗触发。

---

## 组件设计

### GtA17Summary.vue（A17-1）

**布局**：左侧目录 + 右侧章节编辑区（见 requirements §4）

**数据模型**：`checklist_responses` 表 — 章节 item_id 见 [persistence.md](../completion-phase-infra/persistence.md)。

章节定义外置：`backend/data/a17_chapter_definitions.json`（id/标题/提示/数据来源/是否必填）

### GtKamWorkpaper.vue（A17-2-1，A17-plus）

**数据模型**：`checklist_responses` 表

| 字段 | KAM | 示例 |
|------|-----|------|
| item_id | `A17-2-1-KAM-001`~`NNN`（**必须带 wp 前缀**，避免与 A1-15 等冲突） | `A17-2-1-KAM-003` |
| conclusion | KAM 标题/风险领域 | `收入确认` |
| remark | **JSON 字符串（固定 schema）** | 见下 |
| wp_ref | 引用底稿 | `D4,B50` |

**KAM remark JSON schema（前后端 Pydantic + 前端 TS 双校验）**：

```json
{
  "situation": "string",
  "reason": "string",
  "response": "string",
  "refs": "string",
  "wording_review": "pending|done|na",
  "governance_confirmed": false
}
```

### A17-5 xlsx 核对表解析

- 列映射权威：`a17_xlsx_audit.json`（**PRE-4-0 / X-A17**）
- 实现：infra [PRE-4-1~2](../completion-phase-infra/tasks.md)
- 输出：与 `GtChecklistTable` 兼容的 `{ sections, toc, stats }`

### issue_tickets 取数映射（P1 舞弊/违规章节）

见 [completion-phase-infra §issue_tickets](../completion-phase-infra/requirements.md#issue_tickets-取数映射舞弊违规)。P1 仅计数+标题列表，禁止 `category='fraud'`，不自动填充正文。

### LLM 生成服务（A17-plus）

`backend/app/services/a17_llm_service.py` — 见原设计，A17-plus 阶段实现。

### Word 导出

- A17-1/A17-2-1 均调用共享 `docx_template_filler.py`
- A17 专用编排：`a17_word_exporter.py`（调用 filler，传入章节/KAM 数据）
- **不在 a17_word_exporter 内重复实现颜色语义**

### 审计报告 KAM 联动

```
P3 MVP:  A17-2-1 (authoritative) ──push──▶ 审计报告 KAM 段落
P4+ opt: 报告修订 ──stale──▶ A17-2-1 标记（不自动回写）
```

---

## 技术方案

### 后端新增

| 文件 | 分期 | 职责 |
|------|------|------|
| `checklist_xlsx_parser.py` | infra PRE-4 | A17-5-x 解析 |
| `a17_xlsx_audit.json` | audit X-A17 | 列映射 |
| `a17_chapter_definitions.json` | core | 11 章元数据 |
| `a17_summary_service.py` | core | 章节取数（仅就绪源） |
| `a17_word_exporter.py` | core | Word 导出编排 |
| `a17_llm_service.py` | plus | LLM 生成 |
| `backend/data/wp_llm_prompts/a17/` | plus | Prompt 模板 |

### 前端新增

| 组件 | 分期 |
|------|------|
| `GtA17Summary.vue` | core |
| `GtKamWorkpaper.vue` | plus |
| htmlRendererRegistry: `a17-summary`, `kam-workpaper` | core / plus |

### _WP_CODE_OVERRIDE 新增

```python
"A17-1": "a17-summary",
"A17-2-1": "kam-workpaper",      # plus
"A17-5-1": "checklist-table",
"A17-5-2": "checklist-table",
"A17-5-3": "checklist-table",
"A17-5-4": "checklist-table",
"A17-5-5": "checklist-table",
# A17-7 已有: "independence-signing"
```
