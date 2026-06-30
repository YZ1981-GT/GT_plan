# Implementation Plan: 底稿版本链通用组件

## Overview

实现底稿版本链通用组件，为所有底稿提供 field-level 数据版本历史（快照创建/时间线/diff对比/回滚）。按依赖顺序：DB迁移 → 后端服务 → API端点 → 前端composable → Vue组件 → 集成钩子 → PBT测试。

## Tasks

- [ ] 1. 数据库迁移 V096
  - [ ] 1.1 创建 `backend/migrations/V096_create_workpaper_snapshots.sql`
    - CREATE TABLE IF NOT EXISTS workpaper_snapshots（id UUID PK、project_id FK projects(id)、workpaper_id FK working_papers(id)、user_id UUID NOT NULL、snapshot_type VARCHAR(50) NOT NULL、description TEXT、change_summary TEXT、data_json JSONB NOT NULL、item_count INTEGER NOT NULL DEFAULT 0、data_size_bytes INTEGER NOT NULL DEFAULT 0、created_at TIMESTAMP NOT NULL DEFAULT now()）
    - CREATE INDEX IF NOT EXISTS idx_wp_snapshots_wp_created ON workpaper_snapshots(workpaper_id, created_at DESC)
    - CREATE INDEX IF NOT EXISTS idx_wp_snapshots_project ON workpaper_snapshots(project_id)
    - _Requirements: 9.1, 9.6, 9.7_

  - [ ] 1.2 在 `backend/app/models/audit_platform_models.py` 中添加 WorkpaperSnapshot ORM 模型
    - 定义所有列映射 + 类型注解（id, project_id, workpaper_id, user_id, snapshot_type, description, change_summary, data_json, item_count, data_size_bytes, created_at）
    - 添加 FK 关系（projects、working_papers）
    - _Requirements: 9.1_

- [ ] 2. 实现 VersionTrailService 后端核心服务
  - [ ] 2.1 创建 `backend/app/services/version_trail_service.py`
    - 定义 Pydantic 模型：SnapshotCreate、SnapshotMeta、SnapshotDetail、DiffItem、DiffResult、CompareRequest
    - 实现 `create_snapshot(db, project_id, workpaper_id, user_id, snapshot_type, description, change_summary)`
      - SELECT item_id, conclusion, remark, wp_ref FROM checklist_responses WHERE wp_id = :workpaper_id
      - 序列化为 JSON array，计算 len(json.dumps(data).encode()) 作为 data_size_bytes
      - 若 data_size_bytes > 2MB → 降级存储（仅 item_id 列表 + _degraded 标记）
      - 若无 change_summary 且存在前一快照 → 调用 compute_diff_pure 生成摘要
      - 调用 enforce_lifecycle 清理超限快照
      - INSERT INTO workpaper_snapshots
    - 实现 `create_snapshot_fire_and_forget` — try/except 包裹 create_snapshot，异常仅 logger.warning
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.5, 2.6, 9.1, 9.5_

  - [ ] 2.2 实现 `list_snapshots(db, workpaper_id, project_id, page, page_size)`
    - SELECT WHERE workpaper_id AND project_id ORDER BY created_at DESC
    - OFFSET/LIMIT 分页 + COUNT(*) 总数
    - 返回 (list[SnapshotMeta], total_count)
    - _Requirements: 3.1, 3.5, 10.5_

  - [ ] 2.3 实现 `get_snapshot_detail(db, snapshot_id, project_id)`
    - SELECT WHERE id AND project_id（安全隔离）
    - 返回完整 SnapshotDetail 含 data_json
    - _Requirements: 11.3, 10.5_

  - [ ] 2.4 实现 `compute_diff(db, version_a_id, version_b_id, project_id)` + `compute_diff_pure(data_a, data_b)`
    - 读取两个快照 data_json
    - 以 item_id 为 key 构建 dict_a / dict_b
    - added = set(dict_b.keys()) - set(dict_a.keys())
    - deleted = set(dict_a.keys()) - set(dict_b.keys())
    - common = set(dict_a.keys()) & set(dict_b.keys())
    - modified = common 中 conclusion/remark/wp_ref 任一字段不同的
    - unchanged_count = len(common) - len(modified)
    - 生成 summary 文本："新增X项，删除Y项，修改Z个字段"
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 11.5_

  - [ ] 2.5 实现 `rollback_to_snapshot(db, project_id, workpaper_id, snapshot_id, user_id)`
    - 验证 snapshot 属于指定 project_id + workpaper_id
    - 读取目标快照 data_json
    - 在同一事务内：DELETE FROM checklist_responses WHERE wp_id = workpaper_id
    - INSERT INTO checklist_responses (project_id, wp_id, item_id, conclusion, remark, wp_ref, updated_by, created_at, updated_at) — 逐行从 data_json 恢复
    - 创建新快照 snapshot_type='rollback', description="回滚到{target_created_at}的版本"
    - _Requirements: 5.2, 5.3, 5.4, 10.3_

  - [ ] 2.6 实现 `enforce_lifecycle(db, workpaper_id, max_snapshots=50)`
    - COUNT(*) WHERE workpaper_id
    - 若 > max_snapshots → 查询最老的 non-manual 快照 → DELETE 直到 count <= max_snapshots
    - 返回被清理数量
    - _Requirements: 9.2, 9.3, 9.4_

- [ ] 3. 实现版本链 API 端点
  - [ ] 3.1 创建 `backend/app/routers/version_trail.py`
    - `POST /api/projects/{pid}/workpapers/{wp_id}/versions` — 调用 create_snapshot → 返回 SnapshotMeta
    - `GET /api/projects/{pid}/workpapers/{wp_id}/versions?page=&page_size=` — 调用 list_snapshots → 返回 {items, total}
    - `GET /api/projects/{pid}/workpapers/{wp_id}/versions/{vid}` — 调用 get_snapshot_detail → 返回 SnapshotDetail
    - `POST /api/projects/{pid}/workpapers/{wp_id}/versions/compare` — 调用 compute_diff → 返回 DiffResult
    - `POST /api/projects/{pid}/workpapers/{wp_id}/versions/{vid}/rollback` — 权限校验(现场经理+) → 调用 rollback_to_snapshot → 返回新 SnapshotMeta
    - 验证 workpaper 属于 project（安全隔离）
    - 注册到 router_registry
    - _Requirements: 5.6, 10.1, 10.2, 10.3, 10.4, 10.5, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [ ] 4. Checkpoint - 后端服务验证
  - Ensure migration runs, service methods work. Ask user if questions arise.

- [ ] 5. 实现 useVersionTrail.ts composable
  - [ ] 5.1 创建 `audit-platform/frontend/src/components/workpaper/composables/useVersionTrail.ts`（~300行）
    - 定义 TypeScript 接口：SnapshotType、SnapshotMeta、DiffItem、DiffResult、UseVersionTrailOptions
    - 实现响应式状态：versions, totalCount, currentPage, loading, drawerVisible, diffResult, diffLoading, selectedVersions
    - 实现 `loadVersions(page?)` — GET /versions?page=&page_size=20
    - 实现 `createSnapshot(description?)` — POST /versions {snapshot_type:'manual', description}
    - 实现 `compareDiff(versionAId, versionBId)` — POST /versions/compare
    - 实现 `rollback(versionId)` — ElMessageBox.confirm 确认弹窗 → POST /versions/{vid}/rollback
    - 实现 canRollback computed（基于用户角色：现场经理+）
    - 实现 hasMore computed（currentPage * 20 < totalCount）
    - _Requirements: 3.1, 3.5, 4.1, 5.1, 5.5, 7.1, 7.3_

- [ ] 6. 实现 GtWpVersionTrail.vue 时间线侧栏
  - [ ] 6.1 创建 `audit-platform/frontend/src/components/workpaper/version-trail/GtWpVersionTrail.vue`（~350行）
    - 使用 useVersionTrail composable
    - el-drawer（direction=rtl，width=520px，title="版本历史"）
    - 顶部操作栏：el-input（描述输入）+ "保存版本"按钮
    - el-timeline 展示版本列表（按时间倒序）
    - 每条记录显示：时间戳 | 操作人 | snapshot_type 彩色标签 | 描述 | change_summary
    - snapshot_type 颜色映射：manual=蓝 auto_sampling=橙 auto_import=紫 review_sign=绿 status_change=灰 rollback=红
    - 展开显示详细变更列表
    - 版本对比：两个 el-radio 选择器 → "对比"按钮 → 展示 VersionDiffPanel
    - 回滚按钮（仅 canRollback 时显示）+ ElMessageBox 确认弹窗
    - 分页加载更多（el-button "加载更多" when hasMore）
    - defineEmits: 'rollback-completed'
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.1, 5.5, 7.1, 7.2, 7.3, 7.4_

- [ ] 7. 实现 VersionDiffPanel.vue diff 对比面板
  - [ ] 7.1 创建 `audit-platform/frontend/src/components/workpaper/version-trail/VersionDiffPanel.vue`（~250行）
    - Props: diffResult, versionA, versionB
    - 顶部统计卡片：新增X | 删除Y | 修改Z | 未变W
    - el-table 展示 diff 列表：item_id | 字段 | 版本A值 | 版本B值 | 变更类型
    - 行颜色：added=绿色背景 deleted=红色背景 modified=黄色背景
    - el-tag 变更类型标签（新增/删除/修改）
    - 空状态：两版本完全相同时显示"无差异"
    - _Requirements: 4.5, 4.6_

- [ ] 8. 底稿编辑器工具栏集成
  - [ ] 8.1 在底稿编辑器 toolbar 中添加"版本历史"按钮（clock icon）
    - 引入 GtWpVersionTrail 组件
    - 点击按钮 → 打开 drawer
    - 监听 @rollback-completed → 刷新底稿数据
    - 适配所有底稿类型（通过 workpaperId prop）
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 9. 自动快照钩子集成
  - [ ] 9.1 cutoff-test-auto-sampling 集成
    - 在 cutoff_sampling.py 的 fill 操作前调用 VersionTrailService.create_snapshot_fire_and_forget(snapshot_type='auto_sampling')
    - 传入 description 参数（提取条件摘要）
    - _Requirements: 2.1, 8.1_

  - [ ] 9.2 voucher-sampling-engine 集成
    - 在抽凭填充操作前调用 VersionTrailService.create_snapshot_fire_and_forget(snapshot_type='auto_sampling')
    - _Requirements: 2.1, 8.2_

  - [ ] 9.3 Excel批量导入集成
    - 在批量导入底稿数据前调用 create_snapshot_fire_and_forget(snapshot_type='auto_import')
    - _Requirements: 2.2_

  - [ ] 9.4 复核签字集成
    - 在复核签字操作时调用 create_snapshot_fire_and_forget(snapshot_type='review_sign')
    - 传入 description（签字人姓名+角色）
    - _Requirements: 2.3_

  - [ ] 9.5 状态变更集成
    - 在底稿状态变更时调用 create_snapshot_fire_and_forget(snapshot_type='status_change')
    - _Requirements: 2.4_

- [ ] 10. cutoff/voucher 集成升级（before_data → 版本链）
  - [ ] 10.1 修改 cutoff-test-auto-sampling 的 before_data 模式
    - 原：在 composable 内保存 before_data 到 workpaper_extraction_log
    - 新：改为调用 VersionTrailService.createSnapshot API（snapshot_type='auto_sampling'）
    - 保持 workpaper_extraction_log 的 before_data 字段向后兼容（同时写入）
    - _Requirements: 8.1, 8.3_

  - [ ] 10.2 修改 voucher-sampling-engine 的 before_data 模式
    - 同 10.1 逻辑
    - _Requirements: 8.2, 8.3_

- [ ] 11. Checkpoint - 前端组件验证
  - Ensure all frontend components render correctly, drawer opens, timeline shows. Ask user if questions arise.

- [ ] 12. 后端 PBT 测试
  - [ ]* 12.1 编写 Property 1 PBT：快照数据保真性
    - **Property 1: 快照数据保真性**
    - 生成器：`st.lists(st.fixed_dictionaries({item_id: st.text(min_size=1,max_size=50), conclusion: st.one_of(st.none(), st.text(max_size=20)), remark: st.one_of(st.none(), st.text(max_size=500)), wp_ref: st.one_of(st.none(), st.text(max_size=20))}))`
    - 断言：create_snapshot 后读取 snapshot.data_json deep-equals 输入的 checklist_responses 集合
    - **Validates: Requirements 1.1, 1.2, 1.5**

  - [ ]* 12.2 编写 Property 2 PBT：Diff 完备性
    - **Property 2: Diff 完备性**
    - 生成器：两组随机 checklist_responses 列表（item_id 可重叠可不重叠）
    - 断言：`set(added_ids) | set(deleted_ids) | set(modified_ids) | set(unchanged_ids) == set(all_ids_a) | set(all_ids_b)`
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [ ]* 12.3 编写 Property 3 PBT：Diff 互斥性
    - **Property 3: Diff 互斥性**
    - 生成器：同 P2
    - 断言：四个集合（added/deleted/modified/unchanged）pairwise disjoint
    - **Validates: Requirements 4.2, 4.3, 4.4**

  - [ ]* 12.4 编写 Property 4 PBT：回滚恢复保真性
    - **Property 4: 回滚恢复保真性**
    - 生成器：随机 data_json（快照内容）+ 随机当前 checklist_responses
    - 断言：rollback 后 SELECT checklist_responses WHERE wp_id deep-equals snapshot.data_json
    - **Validates: Requirements 5.2, 5.4**

  - [ ]* 12.5 编写 Property 5 PBT：回滚创建新版本
    - **Property 5: 回滚创建新版本**
    - 生成器：随机快照 + rollback 调用
    - 断言：rollback 后新增恰好 1 条 snapshot_type='rollback' 且 data_json == 目标快照 data_json
    - **Validates: Requirements 5.3**

  - [ ]* 12.6 编写 Property 6 PBT：生命周期上界
    - **Property 6: 生命周期上界**
    - 生成器：`st.integers(1,80)` 次 create + `st.sampled_from(['manual','auto_sampling','auto_import','review_sign','status_change'])` 类型
    - 断言：任何时刻 COUNT(*) WHERE snapshot_type != 'manual' <= 50
    - **Validates: Requirements 9.2, 9.3, 9.4**

  - [ ]* 12.7 编写 Property 8 PBT：安全隔离性
    - **Property 8: 安全隔离性**
    - 生成器：`st.uuids()` × 2 项目 + 随机快照分配
    - 断言：list_snapshots(project_a) 永不返回 project_b 的快照
    - **Validates: Requirements 10.5, 11.6, 12.3**

- [ ] 13. 前端 PBT 测试
  - [ ]* 13.1 编写 Property 7 PBT：不可变性
    - **Property 7: 不可变性**
    - 生成器：随机操作序列（create/list/diff/rollback）
    - 断言：任何操作序列后，已存在的快照 data_json 和 metadata 不被修改或删除（通过 mock API 验证请求中无 DELETE 或 PUT 到快照）
    - **Validates: Requirements 10.4**

  - [ ]* 13.2 编写 Diff 纯函数前端 PBT（补充验证）
    - 生成器：`fc.array(fc.record({itemId: fc.string({minLength:1}), conclusion: fc.option(fc.string()), remark: fc.option(fc.string()), wpRef: fc.option(fc.string())}))` × 2
    - 断言：完备性 + 互斥性（前端如果有 diff 展示逻辑的辅助函数）
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

- [ ] 14. 后端集成测试
  - [ ] 14.1 编写完整流程集成测试
    - 测试场景：创建手动快照 → 列表 → 详情 → 修改数据 → 再创建快照 → diff → 回滚 → 验证恢复
    - 测试安全隔离：项目A快照不可被项目B访问
    - 测试生命周期：创建51个auto快照验证purge
    - 测试回滚权限：审计助理调用返回403
    - 测试自动快照失败不阻塞：mock DB异常
    - 测试空底稿快照：checklist_responses=0条时正常创建
    - 测试2MB降级：构造大数据验证降级存储格式
    - _Requirements: 1.1, 2.5, 5.2, 5.6, 9.2, 9.5, 10.3, 10.5_

- [ ] 15. 前端单元测试
  - [ ] 15.1 编写 useVersionTrail.spec.ts 单元测试
    - loadVersions 正确请求 API + 填充 versions 数组
    - createSnapshot 调用后刷新列表
    - compareDiff 填充 diffResult
    - rollback 调用确认弹窗 + emit
    - canRollback 根据角色计算

  - [ ] 15.2 编写 GtWpVersionTrail.spec.ts 单元测试
    - 时间线渲染正确数量的节点
    - snapshot_type 颜色标签正确
    - 回滚按钮仅对有权限用户显示

- [ ] 16. Checkpoint - 全部测试验证
  - Ensure all tests pass (PBT + unit + integration). Ask user if questions arise.

- [ ] 17. 路由注册与契约验证
  - [ ] 17.1 注册 version_trail router 到 router_registry
    - 在 router_registry 对应分组中 import 并注册
    - 验证 `test_router_registry_completeness` 通过
    - _Requirements: 11.1_

- [ ] 18. 回归测试
  - [ ] 18.1 运行现有测试套件确保无回归
    - `rtk python -m pytest backend/tests/ -k "checklist_response or version" -v --tb=short`
    - `rtk npx vitest run --reporter=verbose` (version-trail 相关测试)
    - 确认无回归
    - 如有失败修复后重跑

- [ ] 19. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are PBT tasks
- 每个 Property 对应 design.md 中的一个 correctness property
- 最高迁移为 V094，本次使用 V096（V095 已被 cutoff-test-auto-sampling 占用）
- 后端 asyncpg 不支持 IN tuple 参数，必须用 `= ANY(:list)` + list 类型
- router_registry 注册必须完成否则端点 404
- VersionTrailService 设计为无状态静态方法，便于内部编程式调用（非 HTTP）
- 自动快照 fire-and-forget 模式：失败仅 warning 不阻塞主流程
- data_json 存储完整 checklist_responses 快照，不依赖 componentType
- 回滚需事务保证原子性（DELETE + INSERT + 创建回滚快照）
- 前端 PBT 使用 fast-check numRuns: 100，后端使用 hypothesis max_examples=100
- 2MB 降级存储仅保留 item_id 列表（无 remark 文本），前端展示时标注"数据已精简"
