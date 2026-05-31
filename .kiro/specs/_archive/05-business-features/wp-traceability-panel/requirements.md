# 需求文档：统一溯源面板 + 附件入网

## 需求

### 需求 1：统一溯源端点
1. THE system SHALL 提供 `GET /api/projects/{pid}/lineage` 统一端点，接受 object_type + object_id + direction 参数
2. WHEN 查询任意对象的血缘，THEN SHALL 返回 upstream / downstream / current（LocateTarget 格式）+ 关联附件列表
3. WHEN 内部委托 wp_trace / report_trace / version_line service，THEN SHALL 统一输出格式（不暴露内部差异）

### 需求 2：统一血缘图组件
1. THE system SHALL 提供 LineageGraphPanel.vue 统一血缘图组件
2. WHEN 用户在任意模块右键「数据溯源」，THEN SHALL 打开同一面板（而非各模块各自的溯源 UI）
3. WHEN 用户点击图谱节点，THEN SHALL 调用 useCellLocate 跳转到目标位置
4. WHEN 血缘图含附件节点，THEN SHALL 显示附件缩略图/名称 + 点击可预览

### 需求 3：附件入网
1. THE system SHALL 支持将附件关联到具体位置（wp_cell / report_row / note_section）
2. WHEN 附件被关联，THEN lineage 查询 SHALL 返回该附件
3. WHEN 用户查看某 cell 的溯源，THEN SHALL 显示关联到该 cell 的所有附件（审计证据）

### 需求 4：反向链路补齐
1. WHEN 用户从附注查看某数字的来源，THEN SHALL 能追溯到具体底稿 cell（而非只到底稿级）
2. THE system SHALL 补齐 usePenetrate.toWorkpaperFromNote（附注→底稿 cell 直达）

### 需求 5：stale 影响预览 + 增量传播
1. WHEN 用户修改调整分录/底稿前，THE system SHALL 弹出影响预览"将影响 N 张底稿 / M 报表行 / K 附注"
2. WHEN 用户确认修改，THEN stale 标记 SHALL 按 account_code/wp_code 精确传播（增量，非全量）
3. WHEN 影响预览显示，THEN SHALL 列出具体受影响的底稿/报表/附注名称（可点击跳转）

## 范围边界
- 不重写现有 trace service（收口入口，内部复用）
- 不做 stale 影响预览（独立增强）
- 依赖 wp-locate-foundation 的 LocateTarget + useCellLocate
