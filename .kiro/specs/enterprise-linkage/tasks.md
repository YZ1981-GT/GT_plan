# 实施计划：企业级联动

## 概述

基于现有 SSE + EventBus + Redis 基础设施，实现调整分录与试算平衡表、底稿的实时联动，支持 6000 并发。按依赖顺序分 5 个 Sprint 推进。

## Tasks

- [x] 1. Sprint 1：基础设施层
  - [x] 1.1 创建 Alembic 迁移：adjustment_editing_locks 表 + adjustments.version 列
    - 按 design.md 数据模型建表，含部分唯一索引（WHERE released_at IS NULL）
    - _Requirements: 5.1, 5.5_

  - [x] 1.2 创建 Alembic 迁移：tb_change_history 表
    - 含 project_id/year/row_code/operation_type/operator_id/delta_amount/audited_after 等字段
    - _Requirements: 8.1, 8.2_

  - [x] 1.3 创建 Alembic 迁移：event_cascade_log 表
    - 含 steps JSONB、status 枚举、duration_ms 等字段
    - _Requirements: 7.1, 7.2_

  - [x] 1.4 实现 PresenceService（backend/app/services/presence_service.py）
    - Redis ZSET 存在线用户（score=timestamp），Hash 存编辑状态
    - 心跳 30s，60s 过期清理（ZRANGEBYSCORE）
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 1.5 实现 Presence API 路由（backend/app/routers/presence.py）
    - POST /heartbeat、GET /online、GET /editing 三个端点
    - 注册到 router_registry
    - _Requirements: 2.1, 2.4, 2.5_

  - [x] 1.6 扩展 SSE EventType 枚举
    - 新增 presence.joined/left/editing_started/editing_stopped + adjustment.batch_committed + linkage.cascade_degraded
    - 扩展事件 payload 的 extra 字段结构
    - _Requirements: 1.1, 1.2, 1.3, 2.5_

  - [x] 1.7 实现 ConflictGuardService（backend/app/services/conflict_guard_service.py）
    - 编辑锁获取/释放/心跳续期/过期清理
    - 乐观锁版本校验（WHERE version = expected）
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 1.8 实现 Conflict Guard API 路由
    - POST /{entry_group_id}/lock、PATCH /lock/heartbeat、DELETE /lock
    - 409 状态码返回锁定者信息
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 1.9 扩展 event_handlers.py 订阅调整分录事件触发 SSE 推送
    - ADJUSTMENT_CREATED/UPDATED/DELETED → notify_sse 推送给项目组在线成员
    - 按 ProjectAssignment.role 过滤推送内容
    - _Requirements: 1.1, 1.2, 1.3, 12.1_

  - [x] 1.10 实现增量事件拉取端点（GET /api/projects/{pid}/events/since）
    - 参数：last_event_id 或 since_timestamp
    - 返回断连期间的事件列表（最多 100 条）
    - 供前端 SSE 重连后拉取遗漏事件
    - _Requirements: 1.7, 11.3_

  - [x] 1.11 Checkpoint - 确保所有测试通过，有问题请询问用户

- [x] 2. Sprint 2：核心联动逻辑
  - [x] 2.1 实现 LinkageService（backend/app/services/linkage_service.py）
    - TB 行→调整分录关联查询（account_code JOIN adjustments）
    - TB 行→底稿关联查询（wp_account_mapping）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 2.2 实现影响预判逻辑（linkage_service.py 扩展）
    - 输入 account_code → account_mapping → report_config → wp_account_mapping 反向查找
    - 复用 formula_engine.py 的 TB()/SUM_TB() 解析
    - 已锁定报表（status=final）警告标记
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 2.3 实现 Linkage API 路由（backend/app/routers/linkage.py）
    - GET /tb-row/{row_code}/adjustments、/workpapers
    - GET /impact-preview（query: account_code, amount）
    - GET /change-history/{row_code}
    - _Requirements: 3.1, 3.3, 4.1, 8.3_

  - [x] 2.4 实现 TB 变更历史记录
    - 调整分录 CRUD 时写入 tb_change_history 表
    - 记录 operator_id/operation_type/delta_amount/audited_after
    - _Requirements: 8.1, 8.2, 8.4_

  - [x] 2.5 扩展批量提交为单次级联
    - batch_commit 完成后发布单条 ADJUSTMENT_BATCH_COMMITTED 事件
    - event_handlers 订阅此事件触发一次性 TB 重算（非逐条）
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 2.6 实现批量操作原子性
    - 批量提交中某笔校验失败 → 整批回滚 + 返回失败原因
    - _Requirements: 9.5_

  - [x] 2.7 实现批量重分类导入/导出（backend/app/routers/reclassification.py）
    - GET /template 导出 Excel 模板（预填科目列表）
    - POST /import 读取 Excel 按连续借贷平衡组拆分
    - POST /inline-submit 多行录入一键提交（借贷平衡门控）
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8_

  - [x] 2.8 实现事件级联日志记录
    - 每次级联执行写入 event_cascade_log（trigger_event/steps/status/duration_ms）
    - 失败时标记 degraded + 记录失败原因
    - _Requirements: 7.1, 7.2_

  - [ ]* 2.9 Property 15 测试：批量操作单次级联
    - **Property 15: 批量操作单次级联**
    - 生成 1-50 笔随机分录，验证只触发一次 recalc
    - **Validates: Requirements 9.1, 9.2, 9.3**

  - [ ]* 2.10 Property 17 测试：试算平衡表恒等式不变量
    - **Property 17: 试算平衡表恒等式不变量**
    - 生成随机调整分录集合，验证 audited = unadjusted + aje_dr - aje_cr + rcl_dr - rcl_cr
    - **Validates: Requirements 10.6**

  - [x] 2.11 Checkpoint - 确保所有测试通过，有问题请询问用户

- [x] 3. Sprint 3：前端集成
  - [x] 3.1 实现 usePresence composable（audit-platform/frontend/src/composables/usePresence.ts）
    - 30s 心跳上报（view_name + editing_info）
    - 订阅 SSE presence.* 事件更新在线列表
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.2 实现 PresenceAvatars.vue 组件
    - 显示当前视图在线成员头像列表
    - 接入 TrialBalance.vue 和 Adjustments.vue 顶部
    - _Requirements: 2.4_

  - [x] 3.3 实现 useConflictGuard composable（扩展 useEditingLock 模式）
    - resourceType: 'adjustment'，锁获取/释放/心跳
    - 版本冲突时自动刷新最新版本
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 3.4 实现 ConflictDialog.vue 冲突提示对话框
    - 显示"该分录正在被 [姓名] 编辑中"
    - 版本冲突时提示"已被他人修改"→ 自动刷新
    - _Requirements: 5.2, 5.5, 5.6_

  - [x] 3.5 实现 useLinkageIndicator composable
    - 调用 /linkage/tb-row/{row_code}/adjustments 和 /workpapers
    - 缓存结果，SSE 事件触发刷新
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.6 实现 LinkageBadge.vue + LinkagePopover.vue
    - 徽章显示关联数量（0 时隐藏）
    - 弹出面板显示分录摘要/底稿列表
    - 点击跳转到对应分录/底稿
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 3.7 实现 useImpactPreview composable
    - 输入防抖 300ms 后调用 /impact-preview
    - 返回受影响的 TB 行/报表行/底稿列表
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 3.8 实现 ImpactPreviewPanel.vue
    - 三栏展示：试算表行次 / 报表行次 / 底稿列表
    - 已锁定报表警告提示
    - 未映射科目提示
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 3.9 实现 useNavigationStack composable（穿透导航返回栈）
    - 记录 source_view/row_index/scroll_position
    - Backspace 键恢复上一跳转位置（非输入框内）
    - _Requirements: 6.5, 6.6_

  - [x] 3.10 扩展右键菜单跨模块跳转路径
    - 报表视图右键"查看调整明细" → 跳转试算表高亮对应行
    - 试算表右键"查看调整分录" → 跳转 Adjustments 筛选该科目
    - 试算表右键"查看关联底稿" → 跳转底稿列表筛选该科目
    - 底稿右键"溯源到试算表" → 跳转试算表高亮对应行
    - 所有跳转通过 useNavigationStack 记录来源
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 3.11 Checkpoint - 确保所有测试通过，有问题请询问用户

- [x] 4. Sprint 4：打磨与监控
  - [x] 4.1 实现通知疲劳控制（前端 localStorage）
    - 静默模式开关 + 通知频率配置（实时/5 分钟汇总/仅手动）
    - 5 分钟窗口 >10 条事件合并为汇总通知
    - 冲突守卫通知不受静默影响
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x] 4.2 实现事件级联监控（backend/app/services/event_cascade_monitor.py）
    - 记录级联链路耗时/步骤/状态
    - 成功率低于 95% 时告警
    - _Requirements: 7.1, 7.2, 7.4_

  - [x] 4.3 实现管理后台事件健康页面（backend/app/routers/admin_event_health.py）
    - GET /api/admin/event-health 返回最近 100 条级联记录
    - 含状态/耗时/失败原因
    - _Requirements: 7.3_

  - [x] 4.4 实现 SSE 降级轮询（前端）
    - SSE 断连 >10s → 橙色横幅 + 30s 轮询模式
    - SSE 恢复 → 停止轮询 + 拉取增量事件
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 4.5 实现权限过滤
    - SSE 推送按 ProjectAssignment.role 过滤
    - 助理只收到负责科目相关事件（workpaper_assignments 关联）
    - 联动指示器根据 ROLE_PERMISSIONS 决定是否显示底稿徽章
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x] 4.6 实现跨年度隔离
    - 所有联动查询强制带 project_id + year 条件
    - SSE 事件 payload 含 year 字段，前端过滤当前年度
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 4.7 实现一致性校验
    - 每次调整分录变更后验证借贷平衡
    - "一致性校验"按钮触发全量重算对比增量结果
    - 差异明细展示 + "修复"按钮
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 4.8 实现 degraded 状态前端横幅
    - 级联 degraded 时显示黄色"数据可能未同步"横幅
    - _Requirements: 7.5_

  - [x] 4.9 Checkpoint - 确保所有测试通过，有问题请询问用户

- [x] 5. Sprint 5：测试与验收
  - [ ]* 5.1 Property 9 测试：编辑锁互斥性
    - **Property 9: 编辑锁互斥性**
    - 生成随机用户对和 entry_group_id，验证并发锁行为
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [ ]* 5.2 Property 4 测试：Presence 视图记录一致性
    - **Property 4: Presence 视图记录一致性**
    - 验证心跳/过期/视图切换的状态正确性
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [ ]* 5.3 Property 22 测试：重分类导入拆分正确性
    - **Property 22: 重分类导入拆分正确性**
    - 生成随机借贷行序列，验证按平衡组拆分
    - **Validates: Requirements 16.2, 16.3, 16.4**

  - [ ]* 5.4 Property 19 测试：跨年度隔离
    - **Property 19: 跨年度隔离**
    - 生成跨年度调整分录，验证联动不跨年
    - **Validates: Requirements 14.1, 14.2, 14.3**

  - [ ]* 5.5 Property 11 测试：乐观锁版本冲突检测
    - **Property 11: 乐观锁版本冲突检测**
    - 验证 version 不一致时返回 409
    - **Validates: Requirements 5.5**

  - [ ]* 5.6 集成测试：调整分录→SSE→TB 重算→前端刷新全链路
    - 创建分录 → 验证 SSE 事件 → 验证 TB 增量重算 → 验证 affected_row_codes
    - _Requirements: 1.1, 1.4, 1.5, 1.6_

  - [ ]* 5.7 集成测试：批量提交→单次级联→汇总事件全链路
    - 批量 N 笔 → 验证只触发 1 次 recalc → 验证 1 条汇总 SSE
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 5.8 性能基准测试
    - TB 增量重算 < 500ms（129 行）
    - 影响预判 < 200ms
    - Presence 心跳 Redis < 1ms
    - 50 笔批量操作 < 10s
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.6_

  - [x] 5.9 Checkpoint - 确保所有测试通过，有问题请询问用户

## UAT 验收清单

1. 用户 A 创建调整分录，用户 B 试算表视图 3 秒内自动刷新
2. 试算平衡表行显示联动徽章，点击展开关联分录/底稿列表
3. 调整分录创建对话框实时显示影响预判面板
4. 用户 A 编辑分录时，用户 B 看到锁定图标和锁定者姓名
5. 批量提交 20 笔分录，系统一次性完成联动更新
6. SSE 断连后显示橙色横幅，恢复后自动拉取增量
7. 管理后台事件健康页面显示级联记录列表
8. 重分类 Excel 导入按借贷平衡组正确拆分

## Notes

- 标记 `*` 的任务为可选（测试类），可跳过以加速 MVP
- 每个 Sprint 末尾有 Checkpoint 确保增量验证
- 属性测试使用 Hypothesis 库（已安装 v6.152.4）
- 测试文件：`backend/tests/test_enterprise_linkage_properties.py`
- 前端复用现有 SSE 通道（ThreeColumnLayout 已连接）和 eventBus 分发机制
