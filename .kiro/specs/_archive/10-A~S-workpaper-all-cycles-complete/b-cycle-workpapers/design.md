# B 类底稿（承接与计划）— 设计文档

## 1. 架构总览

B 类底稿复用 A 类已验证的渲染管线：

```
wp_account_mapping.json (注册)
  → WpClassificationService (_WP_CODE_OVERRIDE)
    → get_render_config (componentType 分发)
      → 前端 htmlRendererRegistry → 对应 Vue 组件
```

### 1.1 componentType 路由规划

| wp_code 模式 | componentType | 前端组件 | 说明 |
|-------------|--------------|---------|------|
| B1A, B1B, B2, B10~B13, B18, B19, B30, B40, B50 | `a-program-console` | GtAProgramConsole | 程序表（复用现有） |
| B1-1, B1-2 | `d-form-table` | GtDFormTable | 风险评估矩阵 |
| B1-5, B3 | `checklist-table` | GtChecklistTable | 核对表式 |
| B2-5, B22A-1~5, B22C, B50-1~4, B51, B52 | `d-form-table` | GtDFormTable | 评价/风险汇总表 |
| B22B | `d-form-table` | GtDFormTable | 控制矩阵（用 d-form-table 多列模式） |
| B13-2~5 | `analytical-review` | 复用 A1-13 组件 | 未审报表初步分析 |
| B15 | `redirect` | — | 重定向到 Materiality 模块 |
| B23-1~14, B23-15 | `d-form-table` | GtDFormTable(多sheet) | 业务层面控制 |
| B30-2A/2B, B60-1 | `audit-sheet` | GtAuditSheet | 含公式计算 |
| 所有 .docx | `word-template` | WorkpaperWordEditor | OnlyOffice/降级 |

### 1.2 设计决策：不新增 componentType

经评估，`control-matrix` 和 `risk-matrix` 的需求可用现有 `d-form-table` 通过 schema 配置满足：
- 控制矩阵 = d-form-table + `render_hint: "risk_badge"` 列配置（红/黄/绿着色）
- 风险汇总 = d-form-table + `render_hint: "risk_level"` + 条件着色

不新增 componentType 可减少前端组件数量，保持架构简洁。

## 2. 数据模型

### 2.1 wp_account_mapping 新增条目

需在 `wp_account_mapping.json` 中注册所有 B 类 wp_code（当前仅有 B1A/B1B/B10/B40/B50/B60 等少数几个）。
新增约 60 条，覆盖：B1-1~B1-7, B2~B2-12, B3, B3-1, B5~B5-9, B10~B19-1, B22A-1~B22C, B23-1~B23-15, B30~B30-15, B40~B40-2, B50-1~B50-4, B51~B52, B60-1~B60D。

### 2.2 procedure_table_templates.json 扩展

为 B 类程序表（B1A/B1B/B2/B10~B13/B18/B19/B30/B40/B50）添加模板定义，格式同 A1~A17：

```json
{
  "B1A": {
    "name": "业务承接程序表",
    "items": [
      {"seq": 1, "content": "了解委托目的和需求", "ref_index": "B1-4"},
      {"seq": 2, "content": "了解被审计单位基本情况", "ref_index": "B10"},
      {"seq": 3, "content": "评估风险（含独立性）", "ref_index": "B1-1", "auto_data_source": "b1_risk_score"},
      ...
    ]
  }
}
```

### 2.3 _WP_CODE_OVERRIDE 扩展

在 `wp_classification_service.py` 的 `_WP_CODE_OVERRIDE` 中添加 B 类映射：

```python
# B 类 — 承接与计划
"B1A": "a-program-console",
"B1B": "a-program-console",
"B1-1": "d-form-table",
"B1-2": "d-form-table",
"B1-5": "checklist-table",
"B2": "a-program-console",
"B2-5": "d-form-table",
"B3": "checklist-table",
"B10": "a-program-console",
"B11": "a-program-console",
"B12": "a-program-console",
"B13": "a-program-console",
"B13-2": "analytical-review",
"B15": "redirect-materiality",  # 特殊：重定向
"B18": "a-program-console",
"B19": "a-program-console",
"B22A-1": "d-form-table",
"B22A-2": "d-form-table",
"B22A-3": "d-form-table",
"B22A-4": "d-form-table",
"B22A-5": "d-form-table",
"B22B": "d-form-table",
"B22C": "d-form-table",
"B23-1": "d-form-table",  # ... B23-2~14 同
"B23-15": "d-form-table",
"B30": "a-program-console",
"B40": "a-program-console",
"B50": "a-program-console",
"B50-1": "d-form-table",
"B50-2": "d-form-table",
"B50-3": "d-form-table",
"B50-4": "d-form-table",
"B51": "d-form-table",
"B52": "d-form-table",
"B60-1": "audit-sheet",
```

### 2.4 auto_data_source 新增 resolvers

在 `auto_data_resolvers.py` 中新增 B 类专用 resolver：

| source 名 | 用途 | 数据来源 |
|-----------|------|---------|
| `b1_risk_score` | B1A seq3 风险评分摘要 | B1-1/B1-2 xlsx 解析结果 |
| `b2_communication_status` | B2 前任沟通完成状态 | field_overrides |
| `b3_independence_status` | B3 独立性确认状态 | checklist_responses |
| `b15_materiality_summary` | B15 重要性摘要 | Materiality 模块 |
| `b19_related_party_count` | B19 关联方识别数 | related_party_registry |
| `b22_entity_control_status` | B22 企业层面控制完成率 | field_overrides scope=B22 |
| `b23_walkthrough_progress` | B23 穿行测试完成率 | field_overrides scope=B23 |
| `b50_risk_summary` | B50 风险汇总统计 | B50-1~4 数据 |
| `b51_fraud_factor_count` | B51 舞弊因素已识别数 | field_overrides |

## 3. B23 业务层面控制通用 schema

B23 系列 14 组结构高度相似，设计一套通用 YAML schema（仅 `cycle_name` 参数化）：

```yaml
# backend/data/ledger_adapters/wp_render_schema/B23-generic.yaml
wp_code_pattern: "B23-{n}"
template_version: "v2025-R5"
sheets:
  穿行测试记录:
    component_type: d-form-table
    fields:
      - {name: control_objective, label: 控制目标, type: text, readonly: true}
      - {name: control_activity, label: 控制活动, type: textarea}
      - {name: test_procedure, label: 测试程序, type: textarea}
      - {name: test_result, label: 测试结果, type: enum, enum: [有效, 无效, 不适用]}
      - {name: conclusion, label: 结论, type: enum, enum: [设计有效, 设计无效, 无法评估]}
    dynamic_table:
      add_row_button: true
      max_rows: 50
  评价设计有效性:
    component_type: d-form-table
    fields:
      - {name: control_point, label: 控制点, type: text}
      - {name: design_effectiveness, label: 设计有效性, type: enum, enum: [有效, 无效]}
      - {name: implementation_status, label: 执行情况, type: enum, enum: [已执行, 未执行]}
  控制偏差记录:
    component_type: d-form-table
    fields:
      - {name: deviation_desc, label: 偏差描述, type: textarea}
      - {name: cause, label: 原因, type: textarea}
      - {name: impact, label: 影响评估, type: enum, enum: [重大, 一般, 轻微]}
      - {name: remediation, label: 改进措施, type: textarea}
```

B23-1~14 共用此 schema，仅通过 `wp_code` 参数区分所属循环。

## 4. 联动实现方案

### 4.1 B→A 联动（EventBus）

```python
# B3 独立性完成 → A17-7 状态更新
EventPayload(
    event_type=EventType.CHECKLIST_COMPLETED,
    project_id=pid,
    wp_code="B3",
    account_codes=None,
    metadata={"target_linkage": "A17-7"}
)
```

### 4.2 B→C 联动（B23 设计有效→C 类自动关联）

B23 穿行测试结论写入 `field_overrides` scope=`b23_walkthrough:{cycle}`：
- 设计有效 → C 类控制测试底稿 auto_data_source 读取，显示"穿行测试已确认设计有效"
- 设计无效 → C 类底稿标注"⚠️ 穿行测试发现设计缺陷"

### 4.3 B50→D~N 联动（风险传递）

B50-3 认定层次风险数据存入 `field_overrides` scope=`risk_assessment`，
各循环 D~N 程序表 `auto_data_source: "risk_for_cycle"` 读取对应循环的已识别风险。

## 5. 前端路由

B 类底稿不需要新的顶层页面，复用现有底稿路由：
- `/projects/:pid/workpapers/:wpId` → GtWpRenderer → 按 componentType 路由

特殊处理：
- B15 → render-config 返回 `redirect: true, delegated_module: "materiality"`，前端自动跳转

## 6. 测试策略

1. 单元测试：`_WP_CODE_OVERRIDE` 覆盖所有新增 B 类 wp_code（扩展 smoke test）
2. 集成测试：B 类程序表 JSON 模板全量校验（seq 连续、ref_index 存在）
3. E2E：至少 B1A/B10/B22A-1/B23-1/B50/B60 各一个 Playwright 打开验证
