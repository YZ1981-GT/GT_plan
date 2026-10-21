# 任务：公式输入参数值智能补全

## Task 1: 参数补全映射表（formulaParamCandidates.ts）
- [ ] 1.1 新建 `audit-platform/frontend/src/composables/formula/formulaParamCandidates.ts`
- [ ] 1.2 定义 `PARAM_CANDIDATES` 映射表：每个函数每个参数位的候选来源
- [ ] 1.3 定义 `TB_FIELDS` / `REPORT_FIELDS` 静态字段候选列表
- [ ] 1.4 实现 `getCandidateConfig(funcName, argIndex)` 查询函数
- [ ] 1.5 实现 `filterCandidates(items, prefix)` 前缀过滤（最多 50 条）

## Task 2: 科目列表缓存（useFormulaParamCache.ts）
- [ ] 2.1 新建 `audit-platform/frontend/src/composables/formula/useFormulaParamCache.ts`
- [ ] 2.2 实现 `loadAccountCodes(projectId)` —— 从 `GET /trial-balance` 提取科目代码+名称
- [ ] 2.3 按 projectId 缓存，同会话不重复请求
- [ ] 2.4 项目切换时清缓存

## Task 3: FormulaInput 参数补全集成
- [ ] 3.1 FormulaInput.vue 增加 `projectId` / `reportRows` / `wpCodes` 可选 props
- [ ] 3.2 `updateSuggestions` 增加参数补全分支：`cursorContext` 非 null 时查映射表获取候选
- [ ] 3.3 提取光标前引号后的输入前缀，过滤候选列表
- [ ] 3.4 `acceptSuggestion` 处理引号闭合（`'值'`）
- [ ] 3.5 补全弹出时展示 `value - label` 格式

## Task 4: 宿主接线
- [ ] 4.1 FormulaManagerDialog 给 FormulaInput 传入 projectId
- [ ] 4.2 传入 reportRows（当前报表节点的行次列表）
- [ ] 4.3 传入 wpCodes（supported_wp_codes）

## Task 5: 测试
- [ ] 5.1 新建 `formulaParamCandidates.spec.ts`：映射表查询 + 过滤逻辑
- [ ] 5.2 测试 `getCandidateConfig` 对 TB/ROW/IF 等返回正确配置
- [ ] 5.3 测试 `filterCandidates` 前缀过滤和数量限制
- [ ] 5.4 跑全量前端测试确认无回归
