# 设计文档：统一溯源面板 + 附件入网（wp-traceability-panel）

## 概述

收口 3 个孤岛 trace service 到统一端点 + 统一前端血缘图组件 + 附件进入溯源网络。依赖 wp-locate-foundation 的 LocateTarget 契约和 useCellLocate。

## 架构

### 统一溯源端点

```
GET /api/projects/{pid}/lineage?object_type=wp_cell|report_row|note_cell|tb_row|adjustment&object_id=xxx&direction=both|upstream|downstream
```

返回：`{ upstream: LocateTarget[], downstream: LocateTarget[], current: LocateTarget, attachments: AttachmentRef[] }`

内部委托现有 3 个 trace service（不重写，收口入口）。

### LineageGraphPanel.vue

统一血缘图组件（替代散落的 GtTraceabilityDialog / TrialBalance 右键溯源 / ReportView 浮动条）：
- 任意模块右键「数据溯源」→ 打开同一面板
- 图谱视图（上游→当前→下游，节点可点击跳转）
- 点击节点 → 调 useCellLocate 定位到目标

### 附件入网

新增关联表 `attachment_lineage`：
```sql
CREATE TABLE attachment_lineage (
  id UUID PRIMARY KEY,
  attachment_id UUID REFERENCES wp_attachments(id),
  target_type VARCHAR(50),  -- wp_cell / report_row / note_section
  target_id UUID,
  target_ref VARCHAR(200),  -- "D2-3!B5" 精确位置
  created_at TIMESTAMP DEFAULT now()
);
```

附件进入溯源网络后，LineageGraphPanel 的 `attachments` 字段展示关联证据。

## 正确性属性

**Property 1**: 统一端点返回的 upstream/downstream 是现有 3 个 trace service 结果的超集。
**Property 2**: 附件关联后，lineage 查询能返回该附件。
**Property 3**: 图谱节点点击触发 locateCell 且参数正确。

## 不在范围
- 不重写现有 3 个 trace service（只收口入口）
- 不改 EventBus / 正向数据流
- stale 影响预览（独立增强，可后续加）
