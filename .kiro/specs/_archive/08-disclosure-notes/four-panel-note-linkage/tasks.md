# Implementation Plan: 四栏视图附注联动 (Four-Panel Note Linkage)

## Overview

纯前端实现四栏侧边栏与主编辑区的真正联动导航。改动集中在 3 个组件 + eventBus 类型扩展，无后端变更。使用 TypeScript + Vue 3 + Vitest + fast-check。

## Tasks

- [x] 1. eventBus 新增事件类型
  - [x] 1.1 在 `src/utils/eventBus.ts` 添加 `CatalogNoteSelectPayload` 和 `NoteSectionChangedPayload` 接口，并在 Events 映射表注册 `'catalog:note-select'` 和 `'note:section-changed'` 事件
    - _Requirements: 2.1, 3.1_

- [x] 2. FourColumnCatalog.vue 防抖与状态管理
  - [x] 2.1 添加内部状态 `loadingProjectId`、`isNavigating`、`selectedKey`、`debounceTimer`，实现 300ms 防抖工具函数
    - 项目点击：debounce + set loadingProjectId + isNavigating 守卫
    - 附注章节点击：debounce + 乐观更新 selectedKey + 同章节守卫（currentNote 相同则 no-op）
    - _Requirements: 4.3, 4.4, 1.4, 2.4_
  - [x] 2.2 实现 `onSwitchProject` 方法：debounce 后 emit `{type:'switch_project', project_id, year}`，设置 loading/isNavigating 状态
    - _Requirements: 1.1, 4.1, 4.4_
  - [x] 2.3 实现附注章节点击逻辑：乐观更新 selectedKey 为 `note:${code}`，debounce 后 emit `{type:'note', code}`
    - _Requirements: 2.1, 4.2_
  - [x] 2.4 监听 `eventBus.on('note:section-changed')` 更新 `selectedKey`；监听 `props.project.id` 变化时清除 selectedKey；组件 unmount 时清理 eventBus 监听和 debounce timer
    - _Requirements: 3.1, 3.4_
  - [x]* 2.5 Write property tests for FourColumnCatalog debounce/state logic
    - **Property 8: 防抖仅执行最后一次** — 生成随机长度(2-20)点击序列，验证 300ms 内只有最后一个被执行
    - **Validates: Requirements 4.3**
    - **Property 9: 导航期间禁用交互** — isNavigating=true 时点击不触发任何导航
    - **Validates: Requirements 4.4**
    - **Property 2: 已选中项点击为空操作** — 当前选中项点击不触发导航
    - **Validates: Requirements 1.4, 2.4**
    - **Property 6: 项目切换清除选中状态** — project.id 变化 → selectedKey 重置为 ''
    - **Validates: Requirements 3.4**
    - **Property 7: 乐观更新立即生效** — 点击后 selectedKey 同步更新（不等 async）
    - **Validates: Requirements 4.2**
    - numRuns: 20

- [x] 3. DefaultLayout.vue 路由导航逻辑
  - [x] 3.1 重构 `onCatalogSelect`：按 item.type 分发到 `handleProjectSwitch` / `handleNoteNavigation` / 保持现有行为
    - _Requirements: 1.1, 2.1, 2.2_
  - [x] 3.2 实现 `handleProjectSwitch`：同项目 no-op 守卫 + `tabToRoute` 映射 + `router.push` + catch error 显示 ElMessage
    - _Requirements: 1.1, 1.4, 1.5_
  - [x] 3.3 实现 `handleNoteNavigation`：检测当前路由是否 DisclosureNotes，是则 `eventBus.emit('catalog:note-select')`，否则 `router.push` 附带 `?section=`
    - _Requirements: 2.1, 2.2_
  - [x] 3.4 实现 `tabToRoute` 辅助函数（reports→financial-reports, notes→disclosure-notes, workpapers→workpapers, trial_balance→trial-balance）
    - _Requirements: 1.1_
  - [x]* 3.5 Write property tests for DefaultLayout navigation logic
    - **Property 1: 项目切换生成正确路由路径** — 随机 projectId(UUID) + year(2020-2030) + activeTab(4种)，验证 router.push 参数
    - **Validates: Requirements 1.1**
    - **Property 4: 非附注页面章节点击生成正确导航路由** — 随机 noteSection + 非 DisclosureNotes 路由，验证 router.push 含 section query
    - **Validates: Requirements 2.2**
    - **Property 3: 同页附注章节点击触发 fetchDetail** — 随机 noteSection + route.name=DisclosureNotes，验证 eventBus.emit 参数
    - **Validates: Requirements 2.1**
    - numRuns: 20

- [x] 4. Checkpoint
  - Ensure all tests pass (`rtk npx vitest run`), ask the user if questions arise.

- [x] 5. DisclosureEditor.vue 外部导航接收与反向通知
  - [x] 5.1 在 `onMounted` 中增加 `route.query.section` 读取逻辑：有值时调用 `fetchDetail(section)` 并 `router.replace` 清除 query
    - _Requirements: 2.2, 2.3_
  - [x] 5.2 监听 `eventBus.on('catalog:note-select')`：同章节守卫 + 调用 `fetchDetail` + catch 显示 ElMessage.error + 失败回退
    - _Requirements: 2.1, 2.3, 2.4, 2.5_
  - [x] 5.3 添加 `watch(currentNote.note_section)` 反向通知：变化时 `eventBus.emit('note:section-changed', { noteSection })`
    - _Requirements: 3.1_
  - [x] 5.4 组件 unmount 时清理 `catalog:note-select` 监听
    - _Requirements: 2.1_
  - [x]* 5.5 Write property test for reverse sync
    - **Property 5: 反向同步 selectedKey 一致性** — 随机 noteSection 变化，验证 eventBus 发出 `note:section-changed` 载荷一致
    - **Validates: Requirements 3.1**
    - numRuns: 20

- [x] 6. Final checkpoint
  - Ensure all tests pass (`rtk npx vitest run`), ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property tests use fast-check with numRuns=20 per workspace convention
- 前端路径: `audit-platform/frontend/src/`
- 运行测试: `rtk npx vitest run`
- 无后端变更，纯前端路由+事件联动
