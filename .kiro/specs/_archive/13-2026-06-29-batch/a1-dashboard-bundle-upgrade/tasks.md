# Tasks — A1 Dashboard 子底稿内嵌升级

## 1. useA1SubWorkpapers composable 实现

- [x] 1.1 创建 `composables/useA1SubWorkpapers.ts` — 类型定义 + A1_SUB_TABS 常量 + composable 骨架
  - 定义 A1SubTab 接口、A1_SUB_TABS 6 项配置、UseA1SubWorkpapersOptions/Return 接口
  - 导出 composable 函数签名
  - _Requirements: 1.2, 2.1~2.6, 3.1_

- [x] 1.2 实现 wp_id 解析逻辑 — loadWpIndex + wpIdMap + visibleTabs + hasAnySubTab
  - 调用 getWpIndex(projectId) 获取项目底稿索引
  - 按 regex `/^A1-1[1-6]$/` 过滤生成 wpIdMap
  - visibleTabs = A1_SUB_TABS.filter(tab => wpIdMap[tab.wpCode])
  - hasAnySubTab = visibleTabs.length > 0
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 9.1, 9.2, 9.3_

- [x] 1.3 实现依赖锁定逻辑 — isA17Completed / isA111Signed / isA111Locked / isA115Locked
  - isA111Locked = !isA17Completed
  - isA115Locked = !isA111Signed
  - 提供 lockReason 字符串
  - _Requirements: 4.1, 4.2, 5.1, 5.2_

- [x] 1.4 实现 EventBus 集成 — setupEventListeners / cleanup
  - 监听 'a17-audit-summary-completed' → isA17Completed = true
  - 监听 'a1-11-signing-completed' → isA111Signed = true
  - cleanup 移除监听器
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 1.5 实现初始依赖状态加载 — refreshDependencyStatus
  - 从 A1-11 checklist_responses 读取 sign-status 推导 isA111Signed
  - 从 /api/projects/{id}/completion-flags 读取 a17_completed 推导 isA17Completed
  - API 失败时降级为 locked（安全侧）
  - _Requirements: 4.4, 5.4_

- [x] 1.6 实现进度集成数据 — subWorkpaperCompletions / subCompletedCount / subTotalCount
  - 按 wpIdMap 中存在的条目计算总数
  - A1-11 完成状态用 isA111Signed，其他默认 not_started
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

## 2. GtA1Dashboard.vue 模板追加

- [x] 2.1 引入 composable 和 lazy 子组件 — imports + composable 初始化
  - import useA1SubWorkpapers, defineAsyncComponent
  - lazy import GtA111SigningForm / GtChecklistTable / GtAnalyticalReview
  - 初始化 composable，传入 projectId 和 wpId
  - _Requirements: 1.1, 2.1~2.6_

- [x] 2.2 追加子底稿 Tab 区域模板 — el-tabs + 折叠头 + 组件分发
  - 在 `.gt-a1-dashboard__phases` div 之后追加 Tab 区域
  - 折叠头（默认展开）
  - el-tabs type="border-card" + v-for visibleTabs
  - 按 tab.componentType 分发：signing-form → GtA111SigningForm, checklist → GtChecklistTable, analytical-review → GtAnalyticalReview
  - 传入 wp-id=wpIdMap[tab.wpCode], readonly=isSubTabReadonly(tab)
  - 锁定时顶部 el-alert 警告
  - _Requirements: 1.1, 1.2, 1.4, 2.1~2.6, 4.3, 5.3_

- [x] 2.3 实现 sheetName 路由 — watch props.sheetName + route.query.sheet
  - 匹配子底稿 Tab → subTabActive + subTabsExpanded=true
  - 不匹配 → 保持不变
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 2.4 集成进度环 — 修改 doneCount / progressPercentage 计算
  - doneCount += subWps.subCompletedCount
  - total = programs.length + subWps.subTotalCount
  - progressPercentage 使用新 total
  - _Requirements: 6.1, 6.2_

- [x] 2.5 实现 readonly 透传逻辑 — isSubTabReadonly helper
  - readonly = props.readonly || (tab.id === 'A1-11' && isA111Locked) || (tab.id === 'A1-15' && isA115Locked)
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 2.6 生命周期集成 — onMounted 加载 + onUnmounted cleanup
  - onMounted: loadWpIndex → refreshDependencyStatus
  - onUnmounted: subWps.cleanup()
  - _Requirements: 3.2, 10.5_

- [x] 2.7 追加 CSS — 子底稿区域样式
  - .gt-a1-dashboard__sub-workpapers 区域样式
  - .sub-wp-header 折叠头样式（与 phase-section__header 风格一致）
  - 锁定警告 margin
  - _Requirements: 1.4_

## 3. Checkpoint

- [x] 3.1 确保 TypeScript 编译通过，getDiagnostics 无报错
  - GtA1Dashboard.vue 和 useA1SubWorkpapers.ts 无类型错误

## 4. Property-Based Tests（fast-check）

- [ ]* 4.1 Property 1: wp_id 解析正确性
  - **Property 1: 随机 wp_index → wpIdMap 仅含 A1-1x 且映射正确**
  - 生成随机 wp_index 数组（含 A1-11~A1-16 + 干扰条目）→ 验证 wpIdMap 正确
  - **Validates: Requirements 3.1, 3.2, 3.4**

- [ ]* 4.2 Property 2: Tab 可见性由 wpIdMap 存在性驱动
  - **Property 2: 随机 A1-1x 子集 → visibleTabs 仅含存在的 Tab**
  - 生成随机 A1-11~A1-16 子集 → 验证 visibleTabs.length = subset.length
  - **Validates: Requirements 1.3, 3.3, 9.1, 9.2, 9.3**

- [ ]* 4.3 Property 3: A1-11 锁定由 A17 完成状态驱动
  - **Property 3: 随机 boolean → isA111Locked 正确**
  - 生成随机 isA17Completed → 验证 isA111Locked = !isA17Completed
  - **Validates: Requirements 4.1, 4.2, 4.3**

- [ ]* 4.4 Property 4: A1-15 锁定由 A1-11 签发状态驱动
  - **Property 4: 随机 boolean → isA115Locked 正确**
  - 生成随机 isA111Signed → 验证 isA115Locked = !isA111Signed
  - **Validates: Requirements 5.1, 5.2, 5.3**

- [ ]* 4.5 Property 5: sheetName 路由正确激活子底稿 Tab
  - **Property 5: 随机 sheetName → subTabActive 状态正确**
  - 生成随机 sheetName（合法/非法混合）→ 合法值激活对应 Tab，非法值保持不变
  - **Validates: Requirements 7.1, 7.2, 7.3**

- [ ]* 4.6 Property 6: readonly 透传一致性
  - **Property 6: 随机 readonly × Tab × locked → 子组件 readonly 正确**
  - 生成随机 boolean(readonly) × Tab × boolean(locked) → readonly = prop || locked
  - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [ ]* 4.7 Property 7: 进度环集成正确性
  - **Property 7: 随机 programs 数量 × 子底稿完成数 → 百分比正确**
  - 生成随机 N(total programs) × M(done) × S(subCompleted) × T(subTotal) → percentage = round(((M+S)/(N+T))*100)
  - **Validates: Requirements 6.1, 6.2**

- [ ]* 4.8 Property 8: EventBus 状态同步幂等
  - **Property 8: 随机事件序列 → 最终状态正确**
  - 生成随机事件序列 ('a17'|'a111')[] → 包含 'a17' 则 isA17Completed=true，包含 'a111' 则 isA111Signed=true
  - **Validates: Requirements 10.3, 10.4**

## 5. Unit Tests（vitest）

- [ ]* 5.1 composable 纯逻辑测试 — wpIdMap 过滤 + visibleTabs + hasAnySubTab
  - mock getWpIndex 返回混合数据 → 验证 wpIdMap 仅含 A1-1x
  - 空 wp_index → hasAnySubTab = false
  - _Requirements: 3.1, 3.3, 9.3_

- [ ]* 5.2 锁定逻辑测试 — isA111Locked / isA115Locked / lockReason
  - isA17Completed=false → isA111Locked=true + lockReason 有值
  - isA17Completed=true → isA111Locked=false + lockReason 为空
  - isA111Signed 同理
  - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 5.3_

- [ ]* 5.3 EventBus 集成测试 — 事件触发 → 状态更新 + cleanup 后不再响应
  - 触发 'a17-audit-summary-completed' → isA17Completed=true
  - 触发 'a1-11-signing-completed' → isA111Signed=true
  - cleanup 后再触发 → 状态不变
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ]* 5.4 进度环集成测试 — subCompletedCount / subTotalCount
  - wpIdMap 有 3 项 + isA111Signed=true → subTotalCount=3, subCompletedCount=1
  - wpIdMap 为空 → subTotalCount=0
  - _Requirements: 6.1, 6.2, 6.3_

- [ ]* 5.5 sheetName 路由测试 — 合法值激活 + 非法值不变
  - sheetName='A1-15' 且 A1-15 在 visibleTabs → active='A1-15'
  - sheetName='INVALID' → active 不变
  - _Requirements: 7.1, 7.3_

- [ ]* 5.6 readonly 透传测试 — 组合场景验证
  - props.readonly=true → 所有 Tab readonly=true（不论锁定状态）
  - props.readonly=false + A1-11 locked → A1-11 readonly=true, A1-12 readonly=false
  - _Requirements: 8.1, 8.2_

- [ ]* 5.7 适用性隐藏测试 — hasAnySubTab 为 false 时 Tab 区域不渲染
  - mock wp_index 无 A1-1x → Tab 区域 v-if=false
  - _Requirements: 1.3, 9.3_

## 6. Final Checkpoint

- [x] 6.1 确保所有功能代码 + 测试通过，如有疑问询问用户

## Notes

- 本次升级不新增任何 componentType — GtA1Dashboard 的 componentType `a1-dashboard` 已存在
- A1-11~A1-16 已在 wp_code_overrides 中映射为 `skip`（之前的聚合推送已完成）
- composable 采用与 useA17BundleState 相同的模式但更轻量（无仪表盘条、无 KAM 引用）
- GtA1Dashboard 现有代码保持不动，仅追加 ~100-150 行模板/脚本
- Tasks marked with `*` are optional but should be completed per user preference
