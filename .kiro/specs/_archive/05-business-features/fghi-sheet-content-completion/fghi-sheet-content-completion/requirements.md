# Requirements Document

## Introduction

本 spec 将 E1 货币资金已验证的「逐 sheet 深度打磨」质量标准推广到 **F 存货 / G 投资 / H 固定资产·生物资产·租赁 / I 无形资产·研发** 四个循环的全部前端 sheet 组件。

核心目标：让每个 sheet 组件对照其源模板（`基础数据/致同通用审计程序及底稿模板（2025年修订）/BCD类底稿md/{cycle}/`）补全缺失的标准内容，同时**结合各 sheet 自身的业务结构与特点**打磨（不无脑套用统一模板），并在改动后用 Playwright 实测确认可正常打开、无 console error。

### 质量标杆（E1 已完成）

E1 的 18 个 tab 已按以下六项标准清单完成，作为本 spec 的直接蓝本与验收参照：
1. 审计目标 `el-alert`（info，源模板"一、审计目标"）
2. 编制提示 `<details>` 折叠（CAS 依据 + 填写要点）
3. 主表格字段完整（对照源模板"三、XX表"列，不缺列）
4. 审计说明 `el-card` + autosize `textarea`（持久化 checklist_responses）
5. 审计结论 `el-card` + autosize `textarea`（持久化 checklist_responses）
6. tab-toolbar（`GtIndexChip` canonical `value="wp:{code}"` + 共 N 行 tag）

### 范围边界

- **只补内容、打磨呈现**，不改数据流架构 / composable 核心算法 / 后端取数契约。
- 组件**已有**的审计目标/编制提示/审计说明/结论**不重复**添加，只补缺失项。
- **不臆造 AI**：仅当该循环组件已存在 `useX{Cycle}AiGenerate` composable 时才接 🤖AI 按钮；否则审计说明/结论只用纯 textarea。
- **不臆造抽凭/OCR/EventBus**：已有的联动保留原样，不新增业务联动逻辑。
- E 循环已完成，不在本 spec 范围（仅作蓝本）。
- 后端 render 策略/取数只在「因打磨暴露的既有 bug（如 SQL 列漂移、responses_snapshot 未解析）」范围内修复，不做新功能。

---

## Glossary

- **cycle**：F/G/H/I 四个审计循环之一。
- **entry 组件**：某底稿主入口（如 `GtF1Prepayment.vue`），按 `sheetName` prop v-if 分发子 tab。
- **sheet 组件**：entry 下的子 tab（如 `f1/F1TabDetail.vue`），是打磨的最小单位。
- **源模板**：对应循环的 `{cycle}循环底稿模板库.md`。
- **六项标准清单**：审计目标 alert / 编制提示 details / 主表字段完整 / 审计说明 textarea / 审计结论 textarea / tab-toolbar。

---

## Requirements

### Requirement 1: 审计目标 alert 覆盖

**User Story:** 作为审计师，我希望每个 F/G/H/I sheet 顶部有清晰的审计目标说明，以便快速理解该底稿要证实的认定。

#### Acceptance Criteria

1. WHEN 打开任一 F/G/H/I sheet 组件 THEN 该组件 SHALL 在主体内容顶部渲染一个 `el-alert`（`type="info"`、`:closable="false"`）展示该 sheet 的审计目标。
2. WHERE 源模板对应章节存在"一、审计目标"文本 THE 审计目标内容 SHALL 与源模板语义一致（可精炼，不得虚构不存在的目标）。
3. IF 某 entry 下不同 sheet 审计目标不同（如按 `sheetCode` 区分）THEN 组件 SHALL 按当前 sheet 动态展示对应审计目标，而非单一硬编码。
4. IF 组件已存在审计目标 alert THEN 本需求 SHALL 视为已满足，不重复添加。

### Requirement 2: 编制提示 details 覆盖

**User Story:** 作为审计助理，我希望每个 sheet 有可折叠的编制提示，以便在填写时对照 CAS 依据和要点。

#### Acceptance Criteria

1. WHEN 打开任一 F/G/H/I sheet 组件 THEN 该组件 SHALL 渲染一个 `<details>` 折叠块，包含该底稿的编制要点与相关 CAS/准则依据。
2. WHERE 源模板存在"提示/编制说明/方法论"文本 THE 编制提示内容 SHALL 提炼自源模板，保持业务准确。
3. IF 组件已存在编制提示 details THEN 本需求 SHALL 视为已满足，不重复添加。

### Requirement 3: 主表格字段完整性（结合 sheet 自身结构）

**User Story:** 作为审计师，我希望每个 sheet 的主表列与源模板一致，不缺关键列，以便完整记录审计工作。

#### Acceptance Criteria

1. WHEN 对照源模板"三、XX表"的列定义 THEN sheet 主表 SHALL 覆盖源模板列出的关键列（如存货明细的 数量/单价/成本/可变现净值/跌价准备；固定资产的 原值/累计折旧/减值/账面净值 等）。
2. IF 源模板某列在当前组件缺失 THEN 组件 SHALL 补齐该列（可编辑列用对应控件，计算列只读 + tooltip 说明来源）。
3. WHERE 某 sheet 具有独特业务结构（如 F2 存货监盘的监盘要素、G4 债券的 SPPI 测试、H1 固定资产折旧、I6 研发费用归集）THE 打磨 SHALL 结合该 sheet 特点补全，而非套用其他 sheet 的表结构。
4. WHILE 补列 THE 组件 SHALL NOT 破坏既有 composable 的取数/计算/联动逻辑（列绑定字段名对齐 composable 数据模型）。

### Requirement 4: 审计说明 + 审计结论 textarea 及持久化

**User Story:** 作为审计师，我希望每个 sheet 能录入并保存审计说明与结论，以便留痕。

#### Acceptance Criteria

1. WHEN 打开任一 F/G/H/I sheet 组件 THEN 该组件 SHALL 渲染"审计说明"和"审计结论"两个 `el-card`，各含 autosize `textarea`（说明 `minRows≈5`、结论 `minRows≈3`）。
2. WHEN 用户编辑审计说明/结论 THEN 组件 SHALL 通过 `props.saveImmediate([item])`（或该循环等价保存回调）持久化到 `checklist_responses`，`item_id` 命名 `{code}-{sheet}-audit-note` / `{code}-{sheet}-audit-conclusion`，`conclusion: null`。
3. WHEN 组件挂载 THEN 组件 SHALL 从 `props.allResponses.get(item_id)?.remark` 恢复已保存内容。
4. IF 同一 entry 存在多变体（如按 `sheetCode`/版本区分）THEN item_id SHALL 携带区分后缀以避免串写。
5. WHERE 该循环存在 `useX{Cycle}AiGenerate` composable THE 审计说明/结论卡片 SHALL 提供 🤖AI 辅助按钮；OTHERWISE 只提供纯 textarea（不臆造 AI）。

### Requirement 5: tab-toolbar 与索引 chip

**User Story:** 作为审计师，我希望每个 sheet 有统一的工具栏展示底稿索引与行数，以便交叉引用与定位。

#### Acceptance Criteria

1. WHEN 打开任一含动态表格的 F/G/H/I sheet THEN 组件 SHALL 在表格上方提供 tab-toolbar，含 `GtIndexChip`（canonical `value="wp:{code}"`）。
2. WHERE sheet 主表为动态行表格 THE toolbar SHALL 展示"共 N 行" tag。
3. IF 组件已有符合规范的 toolbar THEN 本需求 SHALL 视为已满足。

### Requirement 6: 非回归工程约束（铁律守卫）

**User Story:** 作为维护者，我希望打磨不引入运行时崩溃或编码损坏，以便底稿稳定可用。

#### Acceptance Criteria

1. WHILE 修改 .vue 文件 THE 实现 SHALL 只使用 str_replace 类编辑工具，SHALL NOT 使用 PowerShell `Set-Content`/`-replace`（防 UTF-8 中文损坏）。
2. WHEN 组件访问 `props.allResponses`/`wpId`/`projectId`/`htmlData`/`isReadonly` THEN SHALL 遵守 ref-unwrap 契约（props 声明解包类型，需 ref 时 `toRef` 重包），SHALL NOT 出现 `props.x.value` 反模式；`check_wp_ref_contract.py --strict` SHALL exit 0。
3. WHEN 组件 import composables THEN 相对路径 `../` 深度 SHALL 正确；`fix_wp_composables_import_depth.py --check` SHALL 通过。
4. WHEN 组件模板绑定 composable 返回值 THEN SHALL 解构到顶层或显式 `.value`，SHALL NOT 出现嵌套-ref 绑定（`:data="obj.rows"` 无 `.value`）。
5. WHEN 改动完成 THEN 每个改动文件 `get_diagnostics` SHALL 零错误，且 Vite transform（`/src/.../X.vue`）SHALL 返回 200。

### Requirement 7: 既有 bug 顺带修复

**User Story:** 作为审计师，我希望打磨过程中发现的既有渲染 bug 被一并修复，以便 sheet 真正可用。

#### Acceptance Criteria

1. IF 打磨中发现后端 render 策略裸 SQL 列漂移（如 `applicable_standards` 已改名 `applicable_standard_v2`，或 JSONB dict 未类型防御）THEN SHALL 修复为 `applicable_standard_v2 AS applicable_standards` + `isinstance` 防御。
2. IF 发现 entry 未解析 `htmlData.responses_snapshot` 导致 seed 空白 THEN SHALL 补 `_mergeResponses` 合并逻辑。
3. IF 发现 selfLoad 键名 bug / 导航事件名 bug（`navigate` vs `navigate-sheet`）/ 持久化断路 THEN SHALL 按既有铁律修复。

### Requirement 8: Playwright 实测验证

**User Story:** 作为审计师，我希望每个循环打磨后被实际打开验证，以便确认没有白屏或崩溃。

#### Acceptance Criteria

1. WHEN 某循环所有 sheet 打磨完成 THEN SHALL 用 Playwright 登录（admin/admin123）导航到该循环代表性底稿，抽验至少 2 个 sheet 渲染正常。
2. WHEN 抽验 sheet THEN 页面 SHALL 展示审计目标/编制提示/审计说明/审计结论，且 console SHALL 无 error。
3. WHERE 服务未启动 THE 实现 SHALL 先启动 `start-dev.bat`（后端 9980 + 前端 3030）再实测。

### Requirement 9: 覆盖完整性

**User Story:** 作为项目负责人，我希望 F/G/H/I 每个 sheet 都被处理，不遗漏。

#### Acceptance Criteria

1. WHEN 本 spec 完成 THEN F/G/H/I 四循环的全部 entry 组件的每个可打磨 sheet SHALL 至少满足 Req1/Req2/Req4（审计目标 + 编制提示 + 审计说明/结论）。
2. WHERE 某 sheet 为纯静态文档/程序表（无表单填报）THE 该 sheet MAY 豁免主表字段补列（Req3），但仍 SHALL 满足审计目标/编制提示（若源模板有）。
3. WHEN 完成 THEN SHALL 产出一份逐 entry/sheet 的覆盖清单（tasks.md 即为清单），标注每 sheet 的处理状态。
