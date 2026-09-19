# Requirements Document

## Introduction

平台「高级查询」有两条并行的前端消费路径，共用同一批后端端点却口径不一，导致维护分叉与显示不一致：

- **业务视图** = `CustomQueryDialog.vue`（🔍 高级查询弹窗，全员可用）。走 `POST /api/custom-query/execute`，用硬编码 `COLUMN_LABELS` 字典把英文列 key 中文化；导出走前端 `xlsx`；结果下钻 `cell_ref` 走 `wp-id-by-code`；右键溯源走 `address-resolve`。
- **高级构建器** = `CustomQueryTab.vue` / `AdvancedQueryBuilder.vue`（仅 admin/manager/partner）。同样走 execute，用 `normalizeColumns` 归一列，但**没有中文标签映射**，字段与结果列直接显示英文 key。

**已实证的技术事实（据此校正设计假设）**：

- 后端 execute 各 `_query_*` 返回的 `columns` 是 **`string[]`（英文 key），不含中文 `title`**；`normalizeColumns` 对 `string[]` 令 `title=key`。因此中文列标签**只在 `CustomQueryDialog` 的硬编码 `COLUMN_LABELS` 里存在**，Tab/Builder 显示英文 key。列标签收敛应做「前端共享中文标签映射」，**不改 execute 契约**。
- `cell_ref` 下钻跳 `WorkpaperEditor`（项目内实际底稿编辑器 + 高亮数据格），`address-resolve` 对 workpaper 返回 `route_path='/template-library'`（模板库模板详情）。**二者是不同语义目的（看项目实际数据 vs 看模板结构），不应合并**，只应共享 URI 构造/wp 解析纯函数与失败提示口径。

**已交付基线（本轮已直接完成，非本 spec 范围，仅作零回归约束）**：业务视图行数上限暴露 + 截断提示、查询历史（localStorage）、选区确认自动取数、转置空态中文化、指标树鉴权收敛到 `http.get`、`formatCell` 编码列不误格式化。

**本 spec 收敛三处不一致（纯前端为主，不改 execute 契约）**：

1. **列标签无统一真源**：中文标签只在 Dialog 硬编码，Tab/Builder 显示英文 → 抽共享标签映射，三方复用。
2. **导出逻辑分叉**：`CustomQueryDialog.exportResult` / `CustomQueryTab.onExportExcel` / `AdvancedQueryBuilder.doExport` 三份并行实现，列标题与文件名规则各写一套。
3. **跳转/溯源代码重复**：cell_ref 跳转与右键溯源各写一套 URI 构造/wp 解析/失败提示（跳转目的不同不合并，仅收敛共享纯函数与提示口径）。

## Glossary

| 术语 | 含义 |
|------|------|
| 业务视图 | `CustomQueryDialog.vue` 的「业务视图」页签，全员可用的树形数据源查询 |
| 高级构建器 | `CustomQueryTab.vue` / `AdvancedQueryBuilder.vue`，仅 admin/manager/partner 可用 |
| execute | `POST /api/custom-query/execute`，业务视图与构建器共用；返回 `columns` 为英文 `string[]`（本 spec 不改其契约） |
| 共享标签映射 | 新增前端单一真源 列 key→中文 映射（收敛现 `COLUMN_LABELS`），三方复用 |
| normalizeColumns | `useAcnrDrill.ts` 归一函数，把 `ColumnMeta[]`/`string[]` 统一为 `QueryColumnMeta{key,title,addrId,drillable,dtype}` |
| 共享导出工具 | 新增前端 xlsx 导出纯工具（列标题=共享标签、取值按 key、统一文件名规则），Dialog/Tab 复用 |
| cell_ref 下钻 | 结果 `cell_ref` 列跳 `WorkpaperEditor` + 高亮项目内实际数据格（经 `wp-id-by-code`） |
| 右键溯源 | 结果行右键跳 `address-resolve` 解析的模板库模板详情（`/template-library`） |

## Requirements

### Requirement 1: 列标签前端单一真源

**User Story:** 作为审计人员，我在业务视图与高级构建器看到的列名应一致且为中文，由同一份标签映射提供，避免高级构建器显示英文 key、也避免中文标签在多处各写一份。

#### Acceptance Criteria

1. WHEN 需要把列 key 转为显示标签 THEN 系统 SHALL 使用同一份共享标签映射（收敛现 `CustomQueryDialog.COLUMN_LABELS`），标签解析优先级为：共享映射 → 列自带 `title`（若后端下发且非等于 key）→ 列 key 本身（三级兜底）。
2. WHERE `CustomQueryDialog` / `CustomQueryTab` / `AdvancedQueryBuilder` 展示列名或字段名 THE 系统 SHALL 复用该共享标签映射，Tab/Builder 由此也显示中文标签。
3. WHEN 收敛完成 THEN 系统 SHALL 不修改后端 execute 的 `columns` 契约（仍为 `string[]`），列标签为纯前端展示层收敛。
4. WHEN 某列 key 不在共享映射中 THEN 系统 SHALL 回退列 key 原样显示，不报错、不留空。

### Requirement 2: 导出逻辑收敛

**User Story:** 作为审计人员，无论从业务视图还是高级构建器导出 Excel，列标题（中文）与文件名规则应一致，维护方只需维护一处导出实现。

#### Acceptance Criteria

1. WHEN 用户从业务视图或高级构建器（Tab）导出 Excel THEN 系统 SHALL 使用共享导出工具：列标题取共享标签映射的中文、取值按列 key、文件名含 项目/数据源/年度（或表标签）的一致规则。
2. WHERE 导出实现分散在 `CustomQueryDialog.exportResult` 与 `CustomQueryTab.onExportExcel` THE 系统 SHALL 收敛为共享前端 xlsx 工具，消除两份并行实现。
3. WHERE `AdvancedQueryBuilder.doExport` 走后端 `query/export-excel`（大数据场景）THE 系统 SHALL 保留其后端导出路径，但文件名规则与列标题口径与共享工具对齐（不强制改为前端 xlsx）。
4. WHEN 收敛完成 THEN 现有导出触发条件（无数据禁用、大数据确认）与后端 `query/export-excel` 契约 SHALL 保持不变。

### Requirement 3: 跳转与溯源共享解析核心

**User Story:** 作为审计人员，cell_ref 下钻（看项目实际数据格）与右键溯源（看模板结构）应各自可靠工作，其底层 URI 构造/wp 解析/失败提示不应各写一套导致行为漂移。

#### Acceptance Criteria

1. WHERE cell_ref 下钻与右键溯源共用的逻辑（wp_code→URI 构造、`workpaper:wp|sheet|cell` 拼装、解析失败提示文案）THE 系统 SHALL 抽取共享纯函数收敛，二者复用。
2. WHEN cell_ref 下钻 THEN 系统 SHALL 保持跳转目标为 `WorkpaperEditor` + 高亮项目内实际数据格（经 `wp-id-by-code`，语义不变）。
3. WHEN 右键溯源 THEN 系统 SHALL 保持跳转目标为 `address-resolve` 解析的模板详情（`/template-library`，语义不变）。
4. WHEN 解析目标不存在/未注册 THEN 系统 SHALL 给出明确一致的提示（如「底稿在当前项目不存在」「模板未在 registry」），不静默失败。
5. WHEN 收敛完成 THEN cell_ref 下钻与右键溯源的既有可跳转场景 SHALL 全部保持可跳转（零回归）。

### Requirement 4: 零回归与约束

**User Story:** 作为平台维护者，我要求收敛不改后端 execute 契约、不改变已交付的业务视图行为、不影响其它调用点。

#### Acceptance Criteria

1. WHEN 本次改动完成 THEN 系统 SHALL 不修改 `POST /api/custom-query/execute` 请求/响应契约；`test_advanced_query_hardening_wave012.py::TestExecuteContractBaseline` SHALL 全绿。
2. WHEN 未触及本 spec 收敛点 THEN 本轮已直接交付的业务视图能力（行数上限提示 / 查询历史 / 选区自动取数 / 转置空态 / 指标树鉴权 / formatCell 编码列）SHALL 行为不变。
3. WHERE 其它 `normalizeColumns` / `useAcnrDrill` / 导出 / 溯源调用点 THE 系统 SHALL 保持既有行为不变。
4. WHERE 新增前端工具/映射 THE 系统 SHALL 优先复用而非复制（共享标签映射、共享导出工具、共享解析纯函数）。

### Requirement 5: 正确性属性可测

**User Story:** 作为质量负责人，我希望标签三级兜底、导出列标题/取值、解析纯函数与失败提示有可测的正确性属性。

#### Acceptance Criteria

1. WHEN 编写测试 THEN 系统 SHALL 覆盖以下属性：①标签解析三级兜底（共享映射→title→key）②未知 key 原样回退 ③导出列标题=共享标签、取值=列 key、文件名规则 ④URI 构造纯函数正确（wp_code/sheet/cell → `workpaper:wp|sheet|cell`）⑤execute 契约不变。
2. WHERE 涉及前端纯逻辑 THE 系统 SHALL 以 vitest 覆盖（标签映射/兜底、导出行数据构造、URI 构造）；组件渲染以 get_diagnostics 全清 + Vite transform 200 验证；关键路径 Playwright round-trip（列名一致 / 导出 / 下钻跳转）。WHERE 涉及后端 THE 系统 SHALL 以 pytest 确认 execute 契约测试仍全绿（本 spec 不改后端）。
