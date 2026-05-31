# 需求文档：底稿前端体验优化

## 需求

### 需求 1：侧栏 13→4 功能组收敛
1. WHEN 用户打开底稿侧栏，THEN SHALL 显示 4 个功能组（而非 13 个平铺 tab）
2. WHEN 功能组内有未处理项，THEN 组标签 SHALL 显示汇总 badge 数字

### 需求 2：横幅折叠
1. WHEN 多个信息性横幅同时满足条件，THEN SHALL 折叠为一行摘要 + 展开按钮
2. WHEN 阻断性状态（归档/编辑锁）存在，THEN SHALL 常驻显眼不折叠

### 需求 3：首次渐进引导
1. WHEN 用户首次打开底稿编辑器，THEN SHALL 显示 spotlight 引导（el-tour）
2. WHEN 用户点击"跳过"或"不再提示"，THEN SHALL 记录到 localStorage 不再显示

### 需求 4：门禁引导式
1. WHEN 用户进入生成/导出页面，THEN SHALL 主动显示前置条件满足状态（而非点了才报错）
2. WHEN 某前置条件未满足，THEN SHALL 显示一键跳转去处理的链接

### 需求 5：异步进度统一
1. THE system SHALL 提供 AsyncJobProgress.vue 统一进度条组件
2. WHEN 任何异步任务（import/export/archive/generate）执行，THEN SHALL 使用统一进度组件

### 需求 6：错误处理 component 层治理
1. WHEN `audit-elmessage-error.mjs` 扫描范围扩展到 `components/workpaper/`，THEN SHALL 检出裸 ElMessage.error 用法
2. WHEN ProcedureTrimmingPanel 等组件有裸 ElMessage.error，THEN SHALL 改为 handleApiError 统一封装
3. WHEN 组件有手工拼接 `error.value='...'+err.message` 模式，THEN SHALL 改为统一错误处理

### 需求 7：quality_score 驱动决策 + 指标口径统一
1. WHEN 底稿提交复核，THE system SHALL 检查 quality_score 是否低于阈值并给出警告
2. THE system SHALL 在 PM 看板按 quality_score 排序（低分优先，找薄弱底稿）
3. THE system SHALL 统一 completion_rate 计算口径（当前 7+ 处各算各的，收口到一个 service）

### 需求 8：审计轨迹前端可视化
1. WHEN 用户点击底稿单元格，THE system SHALL 支持查看该 cell 的编辑历史时间线（谁何时改了什么）
2. THE system SHALL 接入已有的 `wp_audit_trail_service.get_cell_history` 后端能力

## 范围边界
- 不改子面板内部逻辑
- 不删任何功能（收纳≠删除）
- 不引入新 UI 库
