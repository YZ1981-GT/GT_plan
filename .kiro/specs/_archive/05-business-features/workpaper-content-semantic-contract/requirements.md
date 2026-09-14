# 需求文档：底稿内容语义契约

## 需求

### 需求 1：SheetContentType 语义契约
1. THE system SHALL 定义 `SheetContentType` 枚举，用于描述 sheet 的审计语义角色。
2. WHEN render schema 已配置 `sheet_type`，THE system SHALL 优先使用 schema 显式值。
3. WHEN render schema 未配置 `sheet_type`，THE system SHALL 回退到现有 sheet 名称/表头启发式识别。
4. THE system SHALL NOT 用 `sheet_type` 替代现有 `componentType`；`componentType` 继续负责前端渲染组件分发。

### 需求 2：字段来源契约
1. THE system SHALL 定义 `FieldSourceContract`，覆盖字段来源、来源引用、编辑权限、人工确认、stale 策略和审计追踪。
2. WHEN 审定表、明细表、附注披露表展示自动填充字段，THE system SHALL 暴露字段来源信息。
3. WHEN 字段允许人工覆盖，THE system SHALL 记录覆盖原因、覆盖人、覆盖时间和原始系统值。
4. WHEN 上游来源变化，THE system SHALL 按字段级 stale 策略标记受影响字段。

### 需求 3：程序状态契约
1. THE system SHALL 定义 `ProgramStatusContract`，覆盖程序是否适用、执行状态、证据、复核状态、结论和责任人。
2. WHEN 用户修改程序状态，THE system SHALL 持久化到项目级状态存储，不得只保存在前端内存。
3. WHEN 程序被裁剪或标记不适用，THE system SHALL 要求填写理由并留痕。
4. WHEN 程序状态影响下游签发或复核，THE system SHALL 能返回可解释的阻断或提醒原因。

### 需求 4：Schema 迁移与校验
1. THE system SHALL 支持 D1/D2 render schema 手工配置 `sheet_type`、`field_sources` 和程序状态绑定。
2. THE system SHALL 提供 schema lint/check 脚本，检查缺失、非法枚举和不一致配置。
3. WHEN 迁移期 schema 缺失 `sheet_type`，THE system SHALL 记录 warning 而不是立即阻断。
4. WHEN 迁移进入 P2，THE system SHALL 可将关键 schema 缺失 `sheet_type` 升级为 CI 阻断。
5. THE system SHALL 在迁移前输出 D1/D2 sheet inventory 与口径对账表，明确生产 schema、generated 草稿、report_row、note_section 和 cross-ref 口径。
6. THE system SHALL NOT 将 `backend/data/wp_render_schema/generated/*.yaml` 直接视为生产 schema 真源；generated schema 只能作为 inventory 和迁移建议来源，除非经过人工审核并迁移到生产 schema 路径。

### 需求 5：前端消费
1. WHEN 工作包或底稿导航展示 sheet，THE system SHALL 优先按 `sheet_type` 分组。
2. WHEN 字段具备来源契约，THE system SHALL 在单元格/字段来源面板中展示来源、是否可编辑、是否 stale。
3. WHEN 程序状态存在，THE system SHALL 在控制台和复核入口展示状态摘要。

## 范围边界

- 不重写 `htmlRendererRegistry`，不改变 `componentType` 的渲染分发职责。
- 不一次性迁移全部 `wp_render_schema`，P0 只覆盖 D1/D2 试点所需 schema。
- 不重写现有 `_detect_sheet_type` 和 `import_intelligence.detect_sheet_type_by_content`，迁移期作为回退。
- 不在本 spec 中实现完整 D1/D2 工作包 UI，工作包试点由 `workpaper-account-package-d1-d2-pilot` 承接。

## 实施批次

- **P0a 语义契约最小闭环**：类型定义、D1/D2 schema 显式 `sheet_type`、字段来源契约、程序状态契约。
- **P0b 校验工具**：schema lint/check 脚本、warning 输出、测试样例。
- **P1 扩展迁移**：对其余 schema 生成启发式建议，人工确认后批量补充。
- **P2 CI 治理**：关键 schema 缺失语义字段时阻断 CI。

## Properties / 验收不变量

1. **Property 1：语义与渲染分层**  
   任一 sheet 可以同时拥有 `sheet_type` 和 `componentType`，两者不得互相覆盖。
2. **Property 2：schema 优先**  
   schema 显式 `sheet_type` 存在时，启发式识别不得覆盖它。
3. **Property 3：来源可追踪**  
   任一自动填充字段必须能展示来源类型、来源引用和 stale 策略。
4. **Property 4：状态持久化**  
   程序状态刷新页面后不得丢失。
5. **Property 5：迁移可回退**  
   缺失 `sheet_type` 的历史 schema 必须可继续通过启发式渲染。

## 依赖关系

- 依赖现有 `WpRenderSchemaService`、`useWpRenderer`、`htmlRendererRegistry`。
- 被 `workpaper-account-package-d1-d2-pilot` 使用。
- 与 `platform-linkage-contract-stale` 的来源、stale 和穿透契约协同。

## UAT 场景

1. 打开 D1 底稿，导航按 `sheet_type` 识别控制台、审定表、明细表、附注和结论。
2. 点击 D1 审定表本期未审数字段，能看到来源为试算表、不可编辑、stale 策略。
3. 修改 D1 控制台程序状态，刷新页面后状态仍保留。
4. 删除某个非关键 schema 的 `sheet_type`，系统回退启发式识别并输出 warning。
5. 查看 D1/D2 inventory，对同一科目的 report_row、note_section、cross-ref note code 不一致项能被标记出来。
