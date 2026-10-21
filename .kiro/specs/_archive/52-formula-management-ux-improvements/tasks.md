# 公式管理体验优化 — 任务清单

> spec: `formula-management-ux-improvements`
> 优先级：A → D → B → E → G → C

## A 批：公式编辑器实时语法校验 + 地址选择增强

- [x] A1. 新建 `formulaSyntaxParser.ts`：tokenize + validate 纯函数，支持 TB/WP/NOTE/ROW/REPORT/SUM_ROW 6 种函数 + 数学运算符
- [x] A2. 新建 `formulaSyntaxParser.spec.ts`：≥20 例覆盖正确/错误/边界（未闭合引号、未知函数、嵌套括号）
- [x] A3. 新建 `FormulaInput.vue`：contenteditable + 覆盖层语法高亮 + debounce 500ms 校验 + inline 错误提示，v-model 兼容 string
- [x] A4. 新建 `FormulaParamPicker.vue`：TB/WP/NOTE/ROW 四种模式的参数选择 popover，数据源接 ACNR
- [x] A5. 改造 FormulaManagerDialog：编辑态替换 `<el-input>` 为 `<FormulaInput>` + 快捷按钮改用 `<FormulaParamPicker>`
- [x] A6. 浏览器实测：公式管理弹窗成功打开（和平药房_2025 报表页），129 行/90 公式/健康度 79%，内联编辑 FormulaInput 替换已接入，FormulaParamPicker 快捷按钮已替换，控制台无 Vue 编译或 JS 运行时错误

## D 批：待确认智能分组 + 批量适配

- [x] D1. 改造 FormulaPendingSyncDialog：按 domain 分组，computed grouped 逻辑 + 折叠展开 UI
- [x] D2. 组头增加域名标签 + 来源标签 + 数量 + 组级「全部采用」/「全部保留」按钮
- [x] D3. 浏览器实测：弹窗编译无报错，待确认分组 UI 代码已接入（FormulaPendingSyncDialog 含 groupedItems/toggleGroup/setGroupAll/折叠样式），当前项目无待确认事项故分组列表为空（功能正确——无数据时不显示分组）

## B 批：推送覆盖率仪表盘 + 空状态优化

- [x] B1. 后端新增 `GET /api/formula-push/coverage` 端点：读 coverage.json 按循环分组返回
- [x] B2. 公式看板（📊 弹窗）增加覆盖率区域：总进度条 + 按循环进度 + 不需推送循环标注原因
- [x] B3. FormulaPushPanel 空状态改进：按 wp_code 首字母匹配循环，显示具体不需推送原因文案
- [x] B4. 跑后端测试确认端点返回正确

## E 批：表间审核历史查看

- [x] E1. 后端新增 `GET /api/projects/{pid}/formula/cross-check-history`：查 draft_refresh_audit 近 20 次 + 每次的 cross_check_results
- [x] E2. FormulaManagerDialog 表间审核模式增加「执行历史」折叠区，列表展示 + 明细展开
- [x] E3. 增加两次执行结果对比（同 rule_id 横向对比，高亮变化项）— 代码已补写：ccHistoryPrevIssue + ccHistoryIssueDiffStyle，明细列按 rule_id 对比上一次执行，状态变化行高亮（pass→fail 红底 / fail→pass 绿底）
- [x] E4. 跑后端测试确认历史查询端点

## G 批：公式依赖关系可视化

- [x] G1. 后端新增 `GET /api/projects/{pid}/formula-settings/dependencies`：利用 reverse_index + parse_formula_dependencies 返回上下游依赖链
- [x] G2. FormulaManagerDialog 增加依赖面板：选中行后显示引用/被引用列表，点击可跳转
- [x] G3. 跑后端测试确认依赖查询端点

## C 批：模板发现性（需产品拍板）

- [x]* C1. ProjectWizard 创建成功后弹提示「建议订阅公式模板」
- [x]* C2. FormulaTemplateManager 列表匹配 applicable_scope 标「推荐」
- [x]* C3. 订阅确认前弹差异预览（复用 FormulaPublishPreviewDialog）— 已由 formula-global-settings-sync 实现
