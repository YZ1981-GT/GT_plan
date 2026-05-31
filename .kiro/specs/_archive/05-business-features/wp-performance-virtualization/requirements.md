# 需求文档：底稿性能与虚拟滚动

## 需求

### 需求 1：HTML 渲染器虚拟滚动
1. WHEN HTML 表格类组件渲染 >500 行数据，THEN SHALL 启用虚拟滚动（el-table-v2）
2. WHEN 虚拟滚动启用，THEN 滚动 SHALL 保持 60fps

### 需求 2：性能基准
1. THE system SHALL 使 HTML 底稿冷启动渲染 <50ms
2. THE system SHALL 使 500 行表格首次渲染 <200ms
3. THE system SHALL 使大表滚动帧率 ≥60fps

### 需求 3：条件启用
1. WHEN 数据行数 ≤500，THEN SHALL 使用普通 el-table（保持现有交互）
2. WHEN 数据行数 >500，THEN SHALL 自动切换到 el-table-v2 虚拟模式

## 范围边界
- 不改 Univer 性能
- 不做全链路压测（独立 UAT）
