# Tasks — A5-1 现金流量表审计 精美 HTML 专属组件

## 1. 注册与后端配置

- [x] 1.1 VALID_COMPONENT_TYPES 新增 `a5-1-cashflow-audit`（`wp_classification_service.py`）
- [x] 1.2 wp_code_overrides.json 确认 A5-1 为 `skip`（若已存在则跳过）
- [x] 1.3 创建后端渲染策略 `_a51_cashflow.py` + RENDERER_DISPATCH 注册
- [x] 1.4 htmlRendererRegistry 注册 `a5-1-cashflow-audit`（lazy import）
- [x] 1.5 CashFlowVerification.vue 中 A5-1 Tab 改为渲染 GtA51CashflowAudit（自加载，传 wpId）
  - _Requirements: 1.1~1.6_

## 2. 前端 composable — useA51CashflowAudit.ts

- [x] 2.1 创建 composable 基础结构 + 静态常量定义
  - PROGRAM_STEPS(21条) + AUDIT_OBJECTIVES(3条)
  - AUDIT_ROWS(8行，含 id/项目名/type/sign)
  - RECONCILE_GROUPS(4组，每组含 items[])
  - CHECK4_SECTIONS(2部分) + CHECK5_ROWS(~10行)
  - OTHER_CF_GROUPS(3类×receive/pay)
  - ACCOUNTING_TIPS(4节)
- [x] 2.2 实现数据加载 + 字段读写 + debounce 保存
  - loadData(wpId): GET render-config → responses
  - refreshData(wpId): 模式切回时重载
  - getField / setField
  - debouncedSave: 2s debounce → PUT checklist-responses
  - flushPendingSave: onBeforeUnmount flush
  - lastSavedAt / saveError 状态
- [x] 2.3 实现全部自动计算函数
  - getAuditedAmount(rowId): 未审+调整
  - getAuditRow6Amount(): row1−row2−row3+row4+row5
  - getAuditRow8Amount(): row6−row7
  - getReconcileTotal(groupId): SUM(items.amount)
  - getReconcileDiff(groupId): total−报表数
  - getCheckDiff(rowId): 测算−原报
  - getCheck5Balance(): SUM(行1~7)−受限
  - getOtherCFTotal(groupId, side): SUM(10项)
  - programProgress: {filled, total:21}
  - _Requirements: 4~9, 11_

## 3. 前端 composable — useA51EditorMode.ts

- [x] 3.1 创建双模式管理 composable
  - mode: 'structured' | 'excel'
  - switching: boolean (loading 态)
  - onlyofficeHealthy: boolean
  - checkHealth(): GET /onlyoffice/health
  - switchToExcel(): flush → mode='excel'
  - switchToStructured(wpId): refreshData → mode='structured'
  - Tab 状态保留逻辑
  - _Requirements: 2.1~2.9_

## 4. 前端主组件 — GtA51CashflowAudit.vue

- [x] 4.1 创建主组件骨架：Props(wpId/readonly) + 顶部栏(el-segmented + 会计提示按钮 + 已保存状态) + el-tabs 6 Tab + Excel 模式区域
- [x] 4.2 实现 Tab 1: 程序表
  - 审计目标 3 条只读卡片（浅蓝背景）
  - 21 步骤卡片列表（层级缩进 level×24px）
  - Y/N/NA 色彩按钮 + 执行人 + 说明 + 索引号
  - 进度条 el-progress
  - 底部签字区（经理+日期）
  - _Requirements: 4.1~4.8_
- [x] 4.3 实现 Tab 2: 审定表
  - 8 行精美表格（项目/未审/调整/说明/审定数/备注）
  - audit-6/audit-8 自动计算行灰色不可编辑
  - 审计说明 textarea
  - 编制说明 el-collapse（6条只读）
  - _Requirements: 5.1~5.8_
- [x] 4.4 实现 Tab 3: 勾稽核对
  - 4 分组卡片（圆角+阴影）
  - 每组：项目行(名称/金额/备注/索引) + 合计(自动) + 报表数(input) + 差异(自动)
  - 差异≠0 红色高亮(#F56C6C + #FEF0F0)
  - 金额右对齐千分位
  - _Requirements: 6.1~6.7_
- [x] 4.5 实现 Tab 4: 核查-子公司
  - 取得 + 处置两卡片
  - ~10 行表格：项目/差异(自动)/原报数/测算数/测算依据
  - 差异≠0 红色加粗
  - 净额自动汇总行
  - _Requirements: 7.1~7.6_
- [x] 4.6 实现 Tab 5: 核查-明细
  - ~10 行现金明细表格
  - 期末余额自动汇总行
  - 底部注释小字灰色
  - _Requirements: 8.1~8.6_
- [x] 4.7 实现 Tab 6: 其他现金流量
  - 3 类（经营/投资/筹资）左右对照布局
  - 每侧 10 项(项目名可编辑+金额) + 合计(自动，灰色)
  - 金额右对齐千分位
  - 编制说明 el-collapse（9条只读）
  - _Requirements: 9.1~9.8_
- [x] 4.8 实现会计提示 el-drawer
  - 右侧抽屉 480px
  - 4 节内容渲染（实务问题/等价物范围/受限存款对照表18行/政府补助）
  - 只读排版
  - _Requirements: 10.1~10.5_

## 5. 测试

- [x] 5.1 vitest 单测 useA51CashflowAudit — 公式计算正确性
  - 审定数=未审+调整 / NaN容错
  - audit-6 = row1−row2−row3+row4+row5
  - audit-8 = row6−row7
  - reconcile diff = total−报表数
  - check diff = 测算−原报
  - check5 期末余额 = SUM−受限
  - otherCF 合计 = SUM(10项)
  - programProgress 计算
- [x] 5.2 vitest 单测 useA51EditorMode — 双模式切换逻辑
  - 健康检查成功/失败
  - 切换时 switching 状态
  - 切回时触发 refreshData
- [x] 5.3 契约测试 — componentType 注册验证
  - VALID_COMPONENT_TYPES 包含 a5-1-cashflow-audit
  - htmlRendererRegistry 包含 a5-1-cashflow-audit
  - RENDERER_DISPATCH 包含 a5-1-cashflow-audit
- [x] 5.4 后端集成测试 — _a51_cashflow.render 返回正确结构
- [ ]\* 5.5 PBT fast-check — 公式属性测试（任意数值输入→公式恒等式成立）
- [ ]\* 5.6 Playwright E2E — 双模式切换 + Tab 切换 + 自动保存验证

## 6. Checkpoint

- [x] 6.1 诊断清理：getDiagnostics 无错误
- [x] 6.2 功能验证：6 Tab 结构化渲染正常 + 双模式切换正常 + 自动保存正常 + 会计提示弹窗正常
  - _Requirements: ALL_

## Notes

- 所有 Tab 的行/步骤定义为前端静态硬编码（从模板提取），不需后端 xlsx 解析器
- 持久化走 checklist_responses（item_id 格式详见 design.md item_id 命名规范节）
- 后端 render 函数极简：只查 checklist_responses 返回 {responses}
- A5-1 在 wp_code_overrides 保持 skip，父组件通过 force_component_type 渲染
- 会计提示内容硬编码前端（~36 行文本，不从后端获取）
- 数值容错：parseFloat 失败按 0 处理，不阻断其他计算
- 双模式切换：切到 Excel 前 flush pending，切回时 refreshData
- Tasks marked with `*` are optional
