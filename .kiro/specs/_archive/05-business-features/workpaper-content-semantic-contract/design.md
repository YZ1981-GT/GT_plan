# 设计文档：底稿内容语义契约

## 概述

本 spec 在现有 HTML/Univer 双轨底稿渲染之上增加语义层。目标是让平台理解每张 sheet、每个关键字段、每项审计程序的业务含义，同时保留现有渲染组件、schema 服务和启发式识别能力。

## 核心设计

### 1. SheetContentType

新增后端/前端共享枚举：

| 枚举 | 说明 |
|---|---|
| `control_panel` | 程序控制台、科目驾驶舱 |
| `audit_sheet` | 审定表 |
| `detail_table` | 明细表 |
| `analysis` | 账龄、趋势、毛利率、集中度等分析 |
| `procedure` | 审计程序执行表 |
| `control_understanding` | 内控了解 |
| `control_test` | 控制测试 |
| `confirmation_summary` | 函证汇总视图 |
| `disclosure` | 附注披露表 |
| `adjustment` | 调整分录视图 |
| `conclusion` | 科目结论和复核 |
| `legacy` | 历史/修订前/只读 |
| `unknown` | 迁移期未知类型 |

### 2. `sheet_type` 与 `componentType` 分层

`sheet_type` 描述业务语义，`componentType` 描述渲染组件。示例：

```yaml
sheets:
  - name: D1-1 应收票据审定表
    sheet_type: audit_sheet
    componentType: audit-sheet
```

渲染分发仍由 `componentType` 完成；导航、权限、来源面板、状态汇总优先读取 `sheet_type`。

### 3. RenderConfig 扩展

前端 `SheetRenderConfig` 增加可选字段：

```typescript
interface SheetRenderConfig {
  sheet_name: string
  componentType: WpComponentType
  sheet_type?: SheetContentType
  schema: Record<string, any>
  html_data: Record<string, any>
  cross_refs: CrossRefEntry[]
  field_sources?: Record<string, FieldSourceContract>
  program_status_refs?: string[]
}
```

迁移期 `sheet_type` 可为空；前端统一调用 `resolveSheetType(sheet)`，按 schema 显式值、后端推断值、前端启发式的顺序解析。

### 4. FieldSourceContract

后端 schema 与前端类型保持一致：

```json
{
  "field_id": "d1.audit_sheet.current_unadjusted",
  "label": "本期未审数",
  "source_type": "trial_balance",
  "source_ref": {
    "module": "trial_balance",
    "account_code": "1121",
    "amount_basis": "closing_balance"
  },
  "editable": false,
  "override_allowed": false,
  "requires_confirmation": false,
  "traceable": true,
  "stale_policy": "refresh_on_tb_updated"
}
```

`source_ref` 必须是对象，避免不可解析字符串。来源面板、stale 判断、复核追问和签发检查都读取此契约。

### 5. ProgramStatusContract

程序状态按项目持久化：

| 字段 | 说明 |
|---|---|
| `project_id` | 项目 |
| `account_package_id` | 科目工作包 |
| `program_code` | 程序编码 |
| `sheet_name` | 关联 sheet |
| `applicable` | 是否适用 |
| `status` | not_started / in_progress / completed / reviewed / rejected |
| `evidence_refs` | 附件、函证、抽样、访谈等证据 |
| `conclusion` | 程序结论 |
| `review_status` | 复核状态 |
| `updated_by` / `updated_at` | 留痕 |

初期可通过新表 `account_package_program_status` 实现；如果复用 `wp_index`，也必须提供等价字段和刷新后不丢失的保证。

### 6. Schema lint

新增脚本建议：

- `backend/scripts/check/check_wp_semantic_schema.py`
- 检查 `sheet_type` 是否在枚举内。
- 检查 `field_sources` 是否包含可解析 `source_type` 和 `source_ref`。
- 检查关键 sheet 是否绑定程序状态或明确声明无需绑定。
- P0 输出 warning，P2 支持 CI 阻断。

### 7. D1/D2 inventory 与口径对账

在任何 schema 迁移前，先输出 D1/D2 的真实结构清单，避免把 generated 草稿误当作生产 schema。当前实证口径：

| 对象 | 当前生产命中 | generated 草稿 | 说明 |
|---|---|---|---|
| D1 | `C-D1-disclosure.yaml` | `generated/D1.yaml` | `load_schema("D1")` 命中附注披露专属 schema；generated D1 仅作 sheet inventory |
| D2 | `C-D2-disclosure.yaml` | `generated/D2.yaml` / `generated/D2-1.yaml` | `load_schema("D2")` 命中附注披露专属 schema；D2 主体 generated 仍是草稿 |
| D2A | `D2A.yaml` | generated D2 内也有 D2A sheet | 根目录 `D2A.yaml` 是较高质量程序控制台 schema |
| D2-8 | `D-D2-8.yaml` | `generated/D2-6.yaml` 内也有 D2-8 sheet | 根目录 `D-D2-8.yaml` 是较高质量段落型 schema |
| D2-13 | `D-D2-13.yaml` | `generated/D2-6.yaml` 内也有 D2-13 sheet | 根目录 `D-D2-13.yaml` 是较高质量问答型 schema |

对账表至少包含：

- `wp_code`
- `account_code`
- `account_name`
- `report_row`
- `note_section`
- `cross_ref_note_code`
- `production_schema_path`
- `generated_schema_path`
- `sheet_inventory`
- `known_conflicts`

特别要标记 D1/D2 当前发现的口径冲突：

- `wp_account_mapping.json` 与 `cross_wp_references.json` 中 D1/D2 附注章节编号不完全一致。
- D2 在不同文件中出现 `BS-005`、`BS-008`、`五、3`、`五-1-1`、`5.7` 等不同表达。
- 前端静态引用中存在 D1 被误写为营业收入或收入循环总控台的情况。

## 不在范围

- 不废弃现有 Univer 编辑。
- 不改写 `htmlRendererRegistry`。
- 不要求历史 schema 一次性补齐。
- 不实现具体 D1/D2 工作包页面。
- 不把 `generated/` 下的自动生成 schema 直接作为线上渲染真源。
- 不修复前端 D1/D2/D4 静态入口文案；该项由 `workpaper-account-package-d1-d2-pilot` 承接。

## 现有代码锚点

### 后端

- `backend/app/services/wp_render_schema_service.py`
- `backend/app/services/wp_generic_processor.py`
- `backend/app/services/import_intelligence.py`
- `backend/data/wp_render_schema/*.yaml`

### 前端

- `audit-platform/frontend/src/composables/useWpRenderer.ts`
- `audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue`
- `audit-platform/frontend/src/components/workpaper/htmlRendererRegistry.ts`
- `audit-platform/frontend/src/composables/useDSalesCycleSheetGroups.ts`

## API 草案

- `GET /api/workpapers/{wp_id}/render-config`：扩展返回 `sheet_type`、`field_sources`、`program_status_refs`。
- `GET /api/projects/{project_id}/workpaper-semantic/schema-check?wp_code=`
- `GET /api/projects/{project_id}/workpaper-fields/source?wp_id=&field_id=`

## 迁移策略

1. 先输出 D1/D2 sheet inventory 与口径对账表。
2. 仅给 D1/D2 生产 schema / registry 增加 `sheet_type` 与关键字段来源。
3. `resolveSheetType` 保留现有启发式回退。
4. 增加 check 脚本，先以 warning 输出迁移建议。
5. D1/D2 试点验收后，再扩展 D4/F/H。

## 风险与回滚

- 风险：schema 字段命名与现有前端约定冲突。  
  回滚：新增字段全部可选，前端缺失时继续现有渲染。
- 风险：字段来源过细导致配置成本高。  
  回滚：P0 只覆盖审定表关键金额和结论字段。
- 风险：程序状态新表与既有复核状态重复。  
  回滚：先只记录程序级状态，不改变既有底稿复核流程。
