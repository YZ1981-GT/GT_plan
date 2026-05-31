# 实施计划：统一溯源面板 + 附件入网

## 任务

- [x] 1. 统一溯源端点
  - [x] 1.1 新建 `backend/app/services/unified_lineage_service.py`（委托 3 个 trace service，统一输出 LocateTarget）
  - [x] 1.2 新建 `backend/app/routers/lineage.py`（`GET /api/projects/{pid}/lineage`）+ 注册 router_registry
  - [x] 1.3 单元测试（mock 3 个 trace service，断言统一输出格式）

- [x] 2. 附件入网
  - [x] 2.1 迁移 `V0XX__attachment_lineage.sql`（新表 attachment_lineage）
  - [x] 2.2 ORM 模型 AttachmentLineage + schema
  - [x] 2.3 关联 API（`POST /api/attachments/{id}/link` 关联到 target_type+target_id+target_ref）
  - [x] 2.4 lineage 查询返回关联附件

- [x] 3. 前端 LineageGraphPanel.vue
  - [x] 3.1 新建组件（图谱视图：upstream→current→downstream 节点 + 附件节点）
  - [x] 3.2 节点点击 → useCellLocate 跳转
  - [x] 3.3 附件节点点击 → 预览
  - [x] 3.4 各模块右键菜单接入「数据溯源」→ 打开 LineageGraphPanel

- [x] 4. 反向链路补齐
  - [x] 4.1 usePenetrate 补 toWorkpaperFromNote（附注→底稿 cell 直达）
  - [x] 4.2 report_trace_service 返回 cell 级 LocateTarget（利用 cell_provenance）

- [x] 6. stale 影响预览 + 增量传播（proposal 第十章 P3 补漏）
  - [x] 6.1 把 `linkage.get_impact_preview` 串成 UI：改调整分录/底稿前弹出"将影响 N 张底稿 / M 报表行 / K 附注"预览
    - _Requirements: 5.1, 5.3_
  - [x] 6.2 stale 标记从全量改增量（按 account_code/wp_code 精确传播）
    - _Requirements: 5.2_
  - [x] 6.3 前端影响预览弹窗组件
    - _Requirements: 5.1, 5.3_

- [x] 7. 测试 + 验收
  - [x]* 5.1 属性测试（统一端点超集 / 附件关联可查 / 节点跳转参数正确）
  - [x]* 5.2 Playwright：从报表右键溯源 → 面板显示 → 点击底稿节点 → 定位高亮

## 说明
- 依赖 wp-locate-foundation（LocateTarget + useCellLocate）
- 不重写现有 trace service，只收口入口
