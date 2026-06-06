# Requirements Document

## Introduction

`ReportView.vue` 是致同审计平台前端最大的单文件组件（2944 行，whitelist 基线 2848），几乎是仓库默认卡点 1500 行的 2 倍。该文件聚合了 7 类报表（BS/IS/CFS/EQ/CFS 附表/减值准备）、跨表核对、多年度对比、公式管理、转换规则映射弹窗、审核结果弹窗、穿透弹窗、构成科目弹窗、附注引用 Drawer、溯源弹窗、单元格选中/右键菜单、stale 刷新、导入导出、全屏/搜索/复制、合并报表穿透、AI 对话面板等大量逻辑。

本 spec 是**纯重构**——零功能变更，仅通过抽取 composable 和子组件（SFC）将文件拆分到 1500 行以内。遵循仓库已验证的「先测后拆」模式（DisclosureEditor 2662→1757 已成功落地）。

### 现状分析（按区块拆解）

| 区块 | 行范围 (约) | 行数 | 可抽取目标 |
|------|------------|------|-----------|
| 模板：顶部横幅 + Tab 切换 | 1–140 | 140 | 保留（orchestrator 编排） |
| 模板：权益变动表矩阵 el-table | 141–295 | 155 | → `ReportEquityTable.vue` SFC |
| 模板：减值准备表矩阵 el-table | 296–340 | 45 | → `ReportImpairmentTable.vue` SFC |
| 模板：普通报表 el-table | 341–440 | 100 | 保留主文件（orchestrator 编排，190 行模板可控） |
| 模板：对比视图 el-table | 441–530 | 90 | 保留（已有 `MultiYearCompare.vue` 独立组件，执行时确认） |
| 模板：跨表核对面板 | 531–570 | 40 | 保留主文件 |
| 模板：穿透/构成/附注引用/溯源弹窗 | 506–930 | ~420 | → `ReportDialogs.vue` SFC（超 600 行则二次拆分） |
| 脚本：转换规则映射逻辑 | 1070–1200 | 130 | → `useReportMapping` composable |
| 脚本：报表获取/生成/审核 | 1200–1810 | 610 | → `useReportData` composable |
| 脚本：权益/减值列定义+行样式 | 1350–1500 | 150 | → `useReportColumns` composable |
| 脚本：单元格选中/右键/穿透全部处理 | 1860–2400 | 540 | → `useReportCellActions` composable |
| 脚本：跨表核对计算逻辑 | 1880–2000 | 120 | → `useReportCrossCheck` composable |
| 脚本：导出/复制/全屏 | 2400–2430 | 60 | → `useReportExport` composable |
| CSS 样式 | 2435–2944 | ~509 | → `report-view.css` 外置 scoped |

> **行号说明**：以上行范围为估算，实际以函数名/标签名为准（script 段实测 932–2433，style 段 2435–2944，模板段 1–930）。3 个标"保留"的小模板块（普通报表/对比视图/跨表核对，合计 ~230 行）默认留主文件由 orchestrator 编排；若最终主文件仍超 1500，再补抽为 SFC。

**瘦身后预期主文件行数**：~700 行（顶部横幅 + Tab 编排 + 小量胶水 + import）+ 外置 CSS ~50 行 scoped 导入 ≈ 750 行，远低于 1500 卡点。

### 已验证的同类先例

- **DisclosureEditor.vue**：2662→1757 行，抽取 7 composable（useNoteTree/useNoteSectionManage/useNoteCellActions 等）+ 2 SFC + CSS 外置 + HARD_CAP 1800 守护
- **WorkpaperEditor.vue**：抽取 8 子 SFC（GtWpRenderer/GtAuditSheet/GtGridSheet 等）+ 2 composable（useEditorMode/useWpRenderer）


## Glossary

- **ReportView（Report_View）**：致同审计平台前端的财务报表主视图（`audit-platform/frontend/src/views/ReportView.vue`），承载 7 类报表展示、交互、导出、审核功能。
- **composable**：Vue 3 中以 `useXxx` 命名的组合式函数，封装可复用的响应式逻辑，从 .vue 文件中分离业务逻辑。
- **SFC（Sub_Component）**：Vue 单文件组件（.vue），从主视图中提取的独立模板+逻辑+样式片段。
- **特征测试（Characterization_Test）**：在重构前捕获现有行为快照的测试，用于守护重构「行为零变化」。
- **HARD_CAP**：`check_file_size.py` 中登记的文件行数硬上限，超限 CI 失败，防止膨胀回弹。
- **whitelist 基线（Whitelist_Baseline）**：文件行数 whitelist 中的数值（当前 ReportView.vue = 2848），瘦身后应下调。
- **零功能回归（Zero_Regression）**：本 spec 实施后，报表模块所有既有能力的可观察行为均保持不变。
- **GT 紫令牌（GT_Purple_Tokens）**：`styles/gt-tokens.css` 定义的 CSS 变量体系，核心紫 `--gt-color-primary:#4b2d77`。
- **GtAmountCell**：平台统一金额展示组件，用于报表所有数值列。
- **useCellSelection**：已有的单元格框选 composable，管理多选/拖选/右键菜单状态。
- **棘轮机制（Ratchet）**：whitelist 基线只减不增 +5% 约束——瘦身后下调基线，后续增长不得超过新基线 5%。

## Requirements

### Requirement 1：零功能回归硬约束（最高优先级）

**User Story:** 作为审计平台用户，我希望报表模块重构后所有功能完全不变，以便日常审计工作不受影响。

#### Acceptance Criteria

1. THE Report_View SHALL 在瘦身后保持以下能力的可观察行为不变：7 类报表展示（BS/IS/CFS/EQ/CFS 附表/减值准备）、对比视图、跨表核对、多年度对比、公式管理、转换规则映射、导入导出、穿透弹窗、构成科目弹窗、审核弹窗、附注引用反查、溯源弹窗、单元格选中与框选、右键菜单全部操作、stale 刷新、全屏、搜索、复制
2. THE 报表模块既有 vitest 测试套件 SHALL 在本 spec 实施后全部通过
3. WHEN 瘦身完成，THE vue-tsc 类型检查 SHALL 对 ReportView.vue 及抽出的所有文件零错误
4. WHERE 本 spec 修改涉及用户可见文本，THE 文本 SHALL 保持原有中文不变
5. IF 本 spec 的任一改动导致既有测试失败，THEN THE 实施 SHALL 修复改动而非修改测试断言以掩盖回归
6. THE 瘦身 SHALL 不改变 ReportView.vue 对外暴露的路由路径、路由参数契约

### Requirement 2：主文件行数目标

**User Story:** 作为平台维护者，我希望 ReportView.vue 行数降到 1500 行以内，以便后续维护和代码审查成本下降。

#### Acceptance Criteria

1. THE ReportView.vue SHALL 在瘦身后行数不超过 1500 行
2. WHEN 瘦身完成，THE file_size_whitelist.txt 中 ReportView.vue 的基线 SHALL 被下调至瘦身后的实际行数（±10 行余量）
3. WHEN 瘦身完成，THE check_file_size.py 的 HARD_CAPS SHALL 登记 ReportView.vue 的显式行数上限以防后续膨胀回弹
4. THE 抽取出的每个 composable 和子组件文件 SHALL 不超过默认上限 1500 行

### Requirement 3：composable 抽取（逻辑层分离）

**User Story:** 作为平台维护者，我希望报表视图的复杂业务逻辑被分离为独立 composable，以便各关注点可单独测试和修改。

#### Acceptance Criteria

1. THE 瘦身 SHALL 抽取 `useReportData` composable 封装报表数据获取、生成、模板行加载、对比行合并、自动校对逻辑
2. THE 瘦身 SHALL 抽取 `useReportMapping` composable 封装转换规则（国企↔上市）的加载/保存/预设/模板应用逻辑
3. THE 瘦身 SHALL 抽取 `useReportCellActions` composable 封装单元格点击/双击/右键菜单全部处理函数、附注引用反查、穿透、溯源、合并明细
4. THE 瘦身 SHALL 抽取 `useReportCrossCheck` composable 封装跨表核对 7 条等式的数据加载与计算逻辑
5. THE 瘦身 SHALL 抽取 `useReportExport` composable 封装单表导出、全部导出、审核报告导出、表格复制功能
6. THE 瘦身 SHALL 抽取 `useReportColumns` composable 封装权益变动表/减值准备表的动态列定义、span-method、行样式、单元格取值逻辑
7. WHEN 每个 composable 被抽取后，THE composable SHALL 从主文件 import 并调用，主文件仅做编排（orchestrator 模式）
8. THE 每个抽取的 composable SHALL 有明确的输入参数和返回值类型定义

### Requirement 4：子组件抽取（模板层分离）

**User Story:** 作为平台维护者，我希望报表视图中复杂的模板片段被提取为独立子组件，以便减少主模板的认知负载。

#### Acceptance Criteria

1. THE 瘦身 SHALL 抽取 `ReportEquityTable.vue` 子组件封装权益变动表的 el-table 矩阵模板（含本年/上年动态列、三级表头）
2. THE 瘦身 SHALL 抽取 `ReportImpairmentTable.vue` 子组件封装减值准备表的 el-table 矩阵模板（含增加/减少嵌套列）
3. THE 瘦身 SHALL 抽取 `ReportDialogs.vue` 或多个独立弹窗子组件，封装穿透弹窗、构成科目弹窗、审核结果弹窗、溯源弹窗、转换规则弹窗、溯源选择弹窗
4. THE 每个子组件 SHALL 通过 props 接收数据、通过 emit 上报事件，遵循 Vue 3 单向数据流
5. THE 子组件 SHALL 放置在 `audit-platform/frontend/src/components/report/` 目录下
6. THE 子组件 SHALL 保持原有的 GT 紫令牌样式和 GtAmountCell 使用模式

### Requirement 5：CSS 外置

**User Story:** 作为平台维护者，我希望报表视图的 484 行 CSS 被外置到独立文件，以便主文件行数进一步缩减且样式独立维护。

#### Acceptance Criteria

1. THE 瘦身 SHALL 将 `<style scoped>` 中的样式外置到 `audit-platform/frontend/src/views/report-view.css`（或同级 .scss）
2. THE ReportView.vue SHALL 通过 `<style scoped src="./report-view.css" />` 或等价方式引入外置样式
3. THE 外置后的样式 SHALL 保持 scoped 作用域不变，不污染全局
4. THE 外置样式文件 SHALL 保持所有原有 CSS 类名和选择器不变

### Requirement 6：先测后拆——特征测试守护

**User Story:** 作为平台维护者，我希望瘦身前有特征测试守护现有行为，以便重构过程中任何行为偏差都能被自动检测。

#### Acceptance Criteria

1. WHEN 开始拆分前，THE 实施 SHALL 先补充 ReportView.vue 的特征测试，覆盖关键交互路径
2. THE 特征测试 SHALL 覆盖纯函数（无需 mount 整个组件）：权益表 span-method、行类型判定 6 种、跨表核对 7 条等式计算、formatReportAmount 格式化。需 mount 的交互用例（Tab 切换触发重载、刷新按钮调 API、对比视图合并）改为抽取后在对应 composable 单测覆盖，避免在 35+ 依赖的重组件上写脆弱 mount 测试
3. THE 特征测试 SHALL 与瘦身后抽出的 composable 单元测试一起通过
4. IF 瘦身过程中发现行为差异，THEN THE 实施 SHALL 修正抽取代码使其与原行为一致，而非修改特征测试断言

