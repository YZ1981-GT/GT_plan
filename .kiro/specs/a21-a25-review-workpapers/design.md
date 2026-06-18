# A21~A25 复核底稿 — 设计文档

## 架构决策

### 配置驱动 vs 代码分支

**决策：纯配置驱动**。5 角色 × 审计类型 × 企业规模 = 10+ 变体，全部由 JSON 定义文件 + 运行时项目上下文决定，前端组件零分支。

### componentType 复用

保持 `review-checklist` componentType 不变（A21~A25 已映射），替换底层组件实现。

```python
# _WP_CODE_OVERRIDE 保持不变
"A21": "review-checklist",
"A22": "review-checklist",
"A23": "review-checklist",
"A24": "review-checklist",
"A25": "review-checklist",
```

### 与 A1-15/A1-16 checklist-table 的区别

| 维度 | checklist-table (A1-15) | review-checklist (A21~A25) |
|------|------------------------|---------------------------|
| 数据源 | xlsx 逐行解析 529 条目 | JSON 定义 15~25 条 |
| 适用性 | 手动标记 4 种(Y/XI/XW/NA) | 二值(Y/NA) + auto_na |
| 签字 | 无 | 复核通过/退回 + review_records |
| 复核记录 | 无 | textarea 自由文本 |
| 多角色 | 单一 | 5 角色配置切换 |

---

## 数据模型

### JSON 定义文件：`a21_a25_review_definitions.json`

```json
{
  "templates": {
    "A21-1": {
      "role": "site_leader",
      "role_label": "项目现场负责人",
      "audit_type": "financial",
      "audit_type_label": "财务报表审计",
      "applicable_categories": ["A", "B", "C"],
      "enterprise_variant": null,
      "items": [
        {
          "seq": 1,
          "content": "具体审计计划已经实施，已完成的工作底稿与具体审计计划的交叉索引。",
          "auto_na_condition": null,
          "category": "completeness"
        },
        {
          "seq": 10,
          "content": "对于利用组成部分注册会计师的工作，已获取了独立性等声明…",
          "auto_na_condition": "no_component_auditor",
          "category": "component"
        }
      ]
    },
    "A24-1-soe": {
      "role": "quality_reviewer",
      "role_label": "质量复核合伙人",
      "audit_type": "financial",
      "audit_type_label": "财务报表审计",
      "applicable_categories": ["A"],
      "enterprise_variant": "large_soe",
      "items": [...]
    }
  },
  "auto_na_conditions": {
    "no_component_auditor": {
      "label": "无组件单位审计师",
      "check": "project.has_component_auditor === false"
    },
    "no_it_audit": {
      "label": "无 IT 审计程序",
      "check": "project.has_it_audit === false"
    },
    "not_large_soe": {
      "label": "非大型国企",
      "check": "project.is_large_soe === false"
    }
  },
  "role_priority": ["site_leader", "manager", "partner", "quality_reviewer", "eqcr"]
}
```

### 模板选择算法

```python
def select_review_templates(project) -> list[str]:
    """根据项目上下文返回应生成的复核底稿 wp_code 列表"""
    category = project.business_category  # A/B/C
    audit_type = project.audit_type       # financial/internal_control/combined
    is_soe = project.is_large_soe         # bool

    templates = []
    for code, defn in DEFINITIONS["templates"].items():
        # 1. 业务类别过滤
        if category not in defn["applicable_categories"]:
            continue
        # 2. 审计类型匹配
        if audit_type == "combined" or defn["audit_type"] == audit_type:
            pass  # 匹配
        else:
            continue
        # 3. 企业变体匹配
        if defn["enterprise_variant"] == "large_soe" and not is_soe:
            continue
        if defn["enterprise_variant"] == "non_soe" and is_soe:
            continue
        templates.append(code)
    return templates
```

---

## 前端设计

### GtReviewChecklist.vue（替换 ReviewChecklistPanel.vue）

Props：`projectId`, `wpId`, `wpCode`

```
┌──────────────────────────────────────────────┐
│  角色: 项目现场负责人  |  财务报表审计  | A类  │  ← 角色信息栏
├──────────────────────────────────────────────┤
│  进度: ████████░░ 12/15 (80%)                │
├──────────────────────────────────────────────┤
│  ☑ 1. 具体审计计划已经实施…                   │  ← 检查项
│  ☑ 2. 工作底稿的审计结论已有清晰表述…          │
│  ☐ 3. 全部财务报表项目的审计工作底稿…          │
│  …                                           │
│  ▨ 10. 组件单位审计师… [N/A - 无组件审计]     │  ← auto_na 灰化
│  …                                           │
├──────────────────────────────────────────────┤
│  复核记录：                                   │  ← 自由文本区
│  ┌────────────────────────────────────────┐  │
│  │                                        │  │
│  └────────────────────────────────────────┘  │
├──────────────────────────────────────────────┤
│  签字: ________  日期: ____   [通过] [退回]   │
└──────────────────────────────────────────────┘
```

### 数据流

1. `onMounted` → 从 JSON 定义加载当前 wp_code 对应的检查项
2. 调 `/projects/{pid}/working-papers/{wpId}/checklist-responses` 加载已保存数据
3. 调 `/projects/{pid}/review-context` 获取 auto_na 条件判定结果
4. 渲染：auto_na 命中的项自动灰化 + disabled
5. 用户勾选 → debounce 1500ms → PUT checklist-responses
6. 点击"通过" → POST review_records + 同步 A1 步骤状态

---

## 后端设计

### 新增文件

| 文件 | 分期 | 职责 |
|------|------|------|
| `backend/data/a21_a25_review_definitions.json` | P0 | 定义文件 |
| `backend/app/services/review_checklist_service.py` | P0 | 加载定义 + auto_na 判定 |
| `backend/app/routers/review_checklist.py` | P1 | review-context + 签字端点 |

### API 端点

```
GET  /api/projects/{pid}/review-context
     → { has_component_auditor, has_it_audit, is_large_soe, audit_type, business_category }

POST /api/projects/{pid}/working-papers/{wpId}/review-sign
     → { action: "pass"|"reject", comment?: string }
     → 写入 checklist_responses item_id="{wp_code}-sign" (P0 轻量方案)
     → P1 可升级为独立 review_signing 表
```

checklist-responses 端点已有（复用）。

### 前置迁移 V086（P0 Task 0 前置）

```sql
-- V086__projects_audit_context.sql
ALTER TABLE projects ADD COLUMN IF NOT EXISTS audit_type VARCHAR(32) DEFAULT 'financial';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS is_large_soe BOOLEAN DEFAULT false;
COMMENT ON COLUMN projects.audit_type IS 'financial/internal_control/combined';
COMMENT ON COLUMN projects.is_large_soe IS '大型国企标记（影响 A24/A25 模板选择）';
```

### review_records 表说明

**不用于签字**。该表是逐单元格复核批注（comment_text + reply + resolve），与本 spec 的"复核通过/退回"无关。

签字方案（P0）：`checklist_responses` 的 `{wp_code}-sign` item，conclusion = "pass"/"reject"，remark = JSON({signer_id, signer_name, signed_at, comment})。

### auto_na 判定逻辑（后端）

```python
async def get_review_context(db, project_id) -> dict:
    """从项目数据推导 auto_na 条件"""
    project = await get_project(db, project_id)
    # has_component_auditor: 检查 wp_index 有无 A10-2(函证-组件审计师)底稿
    has_component = await db.scalar(text(
        "SELECT EXISTS(SELECT 1 FROM wp_index WHERE project_id=:pid AND wp_code LIKE 'A10-2%')"
    ), {"pid": str(project_id)})
    # has_it_audit: 检查 A27(IT审计总结)或 B 循环 IT 底稿
    has_it = await db.scalar(text(
        "SELECT EXISTS(SELECT 1 FROM wp_index WHERE project_id=:pid AND wp_code IN ('A27', 'A27-1'))"
    ), {"pid": str(project_id)})
    return {
        "has_component_auditor": has_component or False,
        "has_it_audit": has_it or False,
        "is_large_soe": project.is_large_soe if hasattr(project, 'is_large_soe') else False,
        "audit_type": project.audit_type if hasattr(project, 'audit_type') else "financial",
        "business_category": project.business_category or "A",
    }
```

### wp_code fallback 确认

wp_index 中已有 A21-1/A21-2 等子底稿码。`_WP_CODE_OVERRIDE` 映射的是父级 A21→review-checklist。
`wp_classification_service.derive_component_type` 对子码（如 A21-1）会先精确匹配 `_WP_CODE_OVERRIDE["A21-1"]`（不存在），然后截取父级码 A21 再查→命中 review-checklist。

**需确认**：`_match_dispatch_key` 或 classification 的 fallback 逻辑是否支持此行为。如不支持，P0 需显式添加 A21-1/A21-2/A22-1/A22-2… 到 override。

---

## 持久化契约

与 [completion-phase-infra/persistence.md](../completion-phase-infra/persistence.md) 一致。

| 数据 | item_id 模式 | conclusion | remark |
|------|-------------|------------|--------|
| 检查项 | `{wp_code}-chk-{seq:02d}` | Y/N/NA | 备注文本 |
| 复核记录 | `{wp_code}-record` | done | 记录正文 |
| 签字状态 | `{wp_code}-sign` | pass/reject | JSON({signer, date, comment}) |

示例：`A21-1-chk-01`, `A21-1-chk-15`, `A21-1-record`, `A21-1-sign`

---

## 不做

- 不建独立程序表（A21~A25 作为 A1 程序表的引用步骤存在）
- 不做 AI 自动复核（P2 仅做完成度预填建议，非 LLM 判断）
- 不改 _WP_CODE_OVERRIDE（已正确映射）
- 不处理 A26/A27（docx 弹窗已完善）/ A28（Univer 直开）
