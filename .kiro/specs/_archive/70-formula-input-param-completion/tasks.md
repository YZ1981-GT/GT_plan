# 任务：公式输入参数值智能补全

## Task 1: 参数补全映射表（formulaParamCandidates.ts）
- [x] 1.1 新建 `audit-platform/frontend/src/composables/formula/formulaParamCandidates.ts`
- [x] 1.2 定义 `PARAM_CANDIDATES` 映射表：每个函数每个参数位的候选来源
- [x] 1.3 定义 `TB_FIELDS` / `REPORT_FIELDS` / `ADJ_TYPES` 静态字段候选列表
- [x] 1.4 实现 `getCandidateConfig(funcName, argIndex)` 查询函数
- [x] 1.5 实现 `filterCandidates(items, prefix)` 前缀过滤（最多 50 条，value/label 双字段不区分大小写）

## Task 2: 科目列表缓存（useFormulaParamCache.ts）
- [x] 2.1 新建 `audit-platform/frontend/src/composables/formula/useFormulaParamCache.ts`
- [x] 2.2 实现 `loadAccountCodes(projectId)` —— 从 `GET /api/projects/{id}/trial-balance` 提取科目代码+名称
- [x] 2.3 按 projectId 缓存，同一会话不重复请求（防并发重复 pendingRequests）
- [x] 2.4 `clearParamCache(projectId?)` 项目切换时清缓存

## Task 3: FormulaInput 参数补全集成
- [x] 3.1 FormulaInput.vue 增加 `projectId` / `reportRows` / `wpCodes` 可选 props
- [x] 3.2 `updateSuggestions` 增加参数补全分支：`cursorContext` 非 null 时查映射表获取候选
- [x] 3.3 提取光标前引号后的输入前缀 `/'([^']*)$/`，过滤候选列表
- [x] 3.4 `acceptSuggestion` 处理引号闭合（插入 `值'` 并将光标移到闭合引号后）
- [x] 3.5 补全弹出时展示 `value - label` 格式（复用 suggestions `{ name, description }` 结构）

## Task 4: 宿主接线
- [x] 4.1 FormulaManagerDialog 给 FormulaInput 传入 `projectId`（复用 `props.projectId`）
- [x] 4.2 传入 `reportRows`（新增 `formulaInputReportRows` computed，从 `currentRows` 转换 `{ row_code, row_name }`）
- [x] 4.3 传入 `wpCodes`（新增 `formulaInputWpCodes` computed，从 `currentRows` 提取去重 wp_code）
  - 证据（2026-10-23）：FormulaManagerDialog 第 319 行 `<FormulaInput v-model="editFormula" :project-id="projectId" :report-rows="formulaInputReportRows" :wp-codes="formulaInputWpCodes" />`

## Task 5: 测试
- [x] 5.1 `formulaParamCandidates.spec.ts`（已存在）：映射表查询 + 过滤逻辑
- [x] 5.2 测试 `getCandidateConfig` 对 TB/ROW/REPORT/WP/ADJ/ABS/IF/未知函数/越界等返回正确配置（11 例）
- [x] 5.3 测试 `filterCandidates` 空前缀/前缀过滤/不区分大小写/数量限制/无匹配（5 例）
- [x] 5.4 跑全量前端测试确认无回归
  - 证据（2026-10-23）：formula 相关 61 个测试文件 668 passed / 3 skipped / 0 failed

## 实施说明（2026-10-23）

代码分析发现 Task 1~3 的核心模块（`formulaParamCandidates.ts` / `useFormulaParamCache.ts` / `FormulaInput.vue` 三个 props + updateSuggestions 参数补全分支 + acceptSuggestion 引号处理）已全部实现。唯一缺失的是 Task 4 宿主接线（FormulaManagerDialog 没有给 FormulaInput 传入 `projectId` / `reportRows` / `wpCodes`），导致科目代码、报表行次、底稿编码三类动态补全在实际使用中不生效。

本次实施：
- 改动文件 1 个：`FormulaManagerDialog.vue`（模板 +3 个 prop 绑定，script +14 行 computed）
- 新增文件 0 个（测试文件已存在）
- 回归：formula 目录 61 文件 668 passed / 0 failed
