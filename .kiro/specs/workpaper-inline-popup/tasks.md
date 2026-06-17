# Implementation Plan

## P0: 弹窗框架 + A1-17 最小可用

- [x] 1. 前端: WpInlinePopup 弹窗容器组件
  - 接收 wpCode prop，动态加载对应子组件
  - el-dialog 自适应宽度（小型 600px / 大型 80vw）
  - 关闭时触发 save
  - _Requirements: 1.1~1.4_

- [x] 2. 前端: GtAProgramConsole 触发改造
  - INLINE_POPUP_WP_CODES 集合判定
  - 子底稿标签点击 → 弹窗而非路由跳转
  - 引入 WpInlinePopup 组件
  - 不影响其他非弹窗底稿的跳转行为
  - _Requirements: 1.1, 1.2_

- [x] 3. 前端: WpPopupProcedure（A1-17 对应数据）
  - 3 个程序步骤卡片
  - 每步：是否适用(下拉) + 执行说明(输入框) + 完成状态
  - 数据保存到 checklist_responses（item_id: A1-17-001~003）
  - 自动保存 debounce 2s
  - _Requirements: 2.3, 3.1, 3.2_

- [x] 4. 前端: 完成状态回显
  - A1 程序表渲染时批量查询子底稿 checklist_responses
  - 子底稿标签旁显示完成徽章（✓绿 / ◐进行中 / 无标记）
  - A1-17 完成规则：3步全标记
  - _Requirements: 4.1, 4.2_

- [x] 5. 集成验证（P0）
  - getDiagnostics 无报错
  - vitest 通过
  - Playwright: 打开 A1 → 点击 A1-17 标签 → 弹窗 → 填写 → 关闭 → 徽章
  - 回归: 非弹窗底稿仍正常跳转

## P1: A1-12 + A1-11

- [ ] 6. 前端: WpPopupChecklist（A1-12 核查表）
  - 14 条适用性判断列表 + 索引号输入
  - 第二部分自由文本区
  - 头部：业务分类标记（从项目信息读取）
  - 底部注释说明
  - 根据 business_category 自动提示适用性
  - _Requirements: 2.2, 5.1_

- [ ] 7. 前端: WpPopupSigning（A1-11 签字流转）
  - 签字审批链表格（6行审批人 × 签字+日期）
  - 签字状态持久化
  - _Requirements: 2.1_

## P2: A1-18 混合型

- [ ] 8. 前端: WpPopupMixedForm（A1-18 混合型）
  - Tab 式多面板：审计目标/过程 + 3个调节表 + 审计说明/结论
  - 调节表数据保存到 parsed_data（JSONB）
  - 程序步骤保存到 checklist_responses
  - 调节表金额预留取数接口
  - _Requirements: 2.4, 3.3_

- [ ] 9. 全量集成验证
  - 4 个子底稿弹窗全部可用
  - 完成状态回显全部正常
  - Playwright E2E 全路径
