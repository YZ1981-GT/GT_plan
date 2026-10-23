# 需求：公式输入参数值智能补全

## 背景
FormulaInput 组件已实现 21 个函数名补全 + 语法高亮 + 实时校验。`cursorContext(expr, cursor)` 已能识别光标在哪个函数的第几个参数（返回 `{ funcName, argIndex }`）。缺少的是**参数值补全**——输入 `TB('` 后补全科目代码，输入 `ROW('` 后补全行次。

## 功能需求

### R1 科目代码补全（TB / SUM_TB / ADJ / AUX / PREV / PRIOR / LEDGER 系列）
- R1.1 当 `cursorContext` 返回 `{ funcName: 'TB', argIndex: 0 }` 时，展示当前项目的科目代码列表
- R1.2 列表项格式：`科目代码 - 科目名称`（如 `1001 - 库存现金`），选中后插入 `'1001'`（带引号）
- R1.3 支持输入前缀实时过滤（输入 `10` 过滤出 `1001/1002/...`）
- R1.4 科目列表从 `GET /api/projects/{id}/trial-balance` 缓存获取（同一项目同一会话只请求一次）
- R1.5 同样适用于 SUM_TB/ADJ/AUX/PREV/PRIOR/LEDGER/LEDGER_DETAIL/TB_AUX/COUNT_LEDGER 的第一个参数

### R2 字段名补全（TB / REPORT 等第二个参数）
- R2.1 `TB` 第二参数：展示 `期末余额 / 期初余额 / 发生额 / 变动额 / AJE调整 / RJE调整`
- R2.2 `REPORT` 第二参数：展示 `期末 / 期初 / current / prior`
- R2.3 字段候选是静态的（不需要后端请求），硬编码在前端

### R3 报表行次补全（ROW / SUM_ROW / REPORT 的第一个参数）
- R3.1 当函数名是 ROW/SUM_ROW/REPORT 且 argIndex=0 时，展示当前报表节点的行次列表
- R3.2 列表项格式：`行次 - 项目名称`（如 `BS-002 - 货币资金`），选中后插入 `'BS-002'`
- R3.3 行次列表从 FormulaManagerDialog 传入（不额外请求后端）

### R4 底稿编码补全（WP 第一个参数）
- R4.1 `WP` 第一参数展示底稿编码列表（从 `supported_wp_codes` 或项目底稿列表获取）
- R4.2 列表项格式：`编码 - 名称`

### R5 交互规范
- R5.1 补全下拉在输入引号 `'` 后触发（参数值是字符串，以引号开头）
- R5.2 键盘 ↑↓ 选择、Enter/Tab 接受、Escape 关闭（与函数名补全一致）
- R5.3 选中后自动插入完整的带引号的值（`'1001'`）并将光标移到引号后
- R5.4 候选列表最多 50 条，按前缀匹配优先排序

## 非功能需求
- NF1 不引入新外部依赖（纯 Vue/TS 实现）
- NF2 科目列表缓存按 `projectId` 键控，项目切换时清缓存
- NF3 补全弹出不阻塞输入（异步加载科目列表时显示 loading 态或不弹出）
