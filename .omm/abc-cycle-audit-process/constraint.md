# 约束（A/B/C 循环）

平台通用铁律见 `.omm/d-cycle-sales/constraint.md`。以下为 A/B/C 附加约束。

1. **整册纯前端组件必须注册 `_SELF_CONTAINED_DEDICATED`**（折叠单 sheet + 清空 html_data），
   render 返回 `{component_type, project_context}` 无 cells，否则被 GtGridSheet grid 兜底 shadow（假绿）。
2. **跨底稿 loader 用 `working_paper`（单数）**，禁 `JOIN working_papers`（复数，查询恒抛错被静默吞）。
3. **风险导向链单一真源**：B50 用 `b50_risk_reader`（从 checklist_responses 重建），下游 resolver 读它；
   B60 Table26 接同一真源；A13 用 `useA13MisstatementBridge`（挂 Shell）作错报唯一消费者。
4. **B19 关联方列名 `name`/`relation_type`/`is_controlled_by_same_party`**（`related_party_registry` 真列），
   禁用 `party_name`/`relationship_type`；B19 是全平台关联方唯一真源（写入 registry 供各循环核对）。
5. **新增 componentType 同步四处**：后端 DISPATCH + VALID_COMPONENT_TYPES + `checklist_responses` item_id 前缀白名单 +
   前端 htmlRendererRegistry。
6. **>100 行动态数据 JSON 打包存或从源重算**（不逐行存 checklist_responses，C24 血泪）。
7. **程序表走 `a-program-console`**（GtAProgramConsole），程序模板在 `procedure_table_templates.json`（无则源 xlsx 兜底）；
   sheet_name 过滤要容错空格 + 程序表尾码回退（`_sheet_name_matches`）。
8. **B 系列整册组件 UI 必须 Playwright 实测**（composable 齐 ≠ 渲染，B23 曾假绿）。
9. **双模式**（B1/B22/B23/B50/B60）：切 OO 前预拉 config「拉取成功才切」；程序表控制台类不参与双模式。
10. **wp_code_overrides.json 改动不热重载**（`_WP_CODE_OVERRIDE` import 时只加载一次）→ 需改 .py 触发 reload 或重启后端。
