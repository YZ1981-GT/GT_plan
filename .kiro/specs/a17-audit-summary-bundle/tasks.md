# Tasks — A17 审计总结聚合组件

## 1. 注册与配置

- [x] 1.1 在 `htmlRendererRegistry.ts` 的 `HtmlComponentType` union 中新增 `'a17-bundle'`
- [x] 1.2 在 `REGISTRY_LIST` 中新增注册条目：componentType=`a17-bundle`, icon='📋', label='A17 审计总结聚合', emits=[], contextProps='standard'
- [x] 1.3 添加 lazy import: `const GtA17Bundle = defineAsyncComponent(() => import('./GtA17Bundle.vue'))`
- [x] 1.4 更新 `wp_code_overrides.json`：将 `"A17"` 映射为 `"a17-bundle"`；将 `"A17-1"`, `"A17-2-1"`, `"A17-3"`, `"A17-3-1"`, `"A17-4"`, `"A17-5-1"`, `"A17-5-2"`, `"A17-5-3"`, `"A17-5-4"`, `"A17-5-5"`, `"A17-6"`, `"A17-7"` 全部映射为 `"skip"`
  - _Requirements: 1.1, 1.2, 2.1, 2.2_
- [x] 1.5 后端 `wp_classification_service.py` 的 `VALID_COMPONENT_TYPES` 中新增 `"a17-bundle"`
  - _Requirements: 7.1, 7.2_
继续

## 2. Vue 组件实现（基础 Tab 分发）

- [x] 2.1 创建 `GtA17Bundle.vue` — script setup + props + Tab 配置常量
  - Props: wpId(必填), sheetName?(可选), readonly?(可选)
  - 定义 `TabDef` 接口和 `TABS` 静态数组（9 个 Tab 定义，含 id/label/kind/wpCode/tracked）
  - _Requirements: 1.3, 1.4, 3.1_

- [x] 2.2 实现 wp_id 解析逻辑 — onMounted 调用 getWpIndex + wpIdMap 计算属性
  - 通过 getWpIndex(projectId) 获取项目底稿索引
  - 过滤 A17-* 条目生成 `wpIdMap: Record<string, string>`
  - _Requirements: 5.1, 5.2, 5.4_

- [x] 2.3 实现 A17-5 适用性过滤 — applicableA17_5 计算属性 + visibleTabs 计算属性
  - 按 wpIdMap 中是否存在对应 wp_code 判断 A17-5-1~5-5 适用性
  - visibleTabs 过滤掉 wp_id 不存在的 Tab（A17-5 系列按适用性过滤）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 5.3_

- [x] 2.4 实现 sheetName 路由 — watch props.sheetName + route.query.sheet → 激活对应 Tab
  - 合法 Tab id → 切换 active；不合法/不在可见列表 → 保持不变（默认 program）
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 2.5 实现 template 模板 — el-tabs 渲染 + 按 Tab.kind 分发子组件
  - kind='program' → GtAProgramConsole (embedded=true, wp-id=props.wpId)
  - kind='a17-summary' → GtA17Summary (project-id, wp-id=wpIdMap[tab.wpCode])
  - kind='word' → WorkpaperWordEditor (wp-id=wpIdMap[tab.wpCode], readonly)
  - kind='checklist' → GtEmbeddedChecklist (wp-id=wpIdMap[tab.wpCode], readonly)
  - kind='independence' → IndependenceSigning (wp-id=wpIdMap[tab.wpCode], readonly)
  - 所有子组件透传 readonly prop
  - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 8.1_

## 3. useA17BundleState composable 实现

- [x] 3.1 创建 `composables/useA17BundleState.ts` — 类型定义 + composable 骨架
  - 定义 CompletionStatus / SubTabCompletion / SignOffPrecondition / KamReference 类型
  - 定义 UseA17BundleStateOptions / UseA17BundleStateReturn 接口
  - 导出 useA17BundleState 函数签名
  - _Requirements: 9.1_

- [x] 3.2 实现完成状态推导逻辑 — deriveA17_5Status / deriveA17_1Status / deriveA17_7Status
  - A17-5: 从 checklist_responses 读取所有 item.conclusion，全非空=completed / 部分=in_progress / 全空=not_started
  - A17-1: 从 checklist_responses 读取 A17-1-ch* 的 remark，按必填章节判断
  - A17-7: 从 checklist_responses 读取 sign_status 项判断
  - 导出纯函数以便单元测试
  - _Requirements: 9.2, 9.3, 9.4, 9.5_

- [x] 3.3 实现 completionMap 计算属性 + refreshCompletionStatus 方法
  - 并行加载各 tracked 子表的 checklist_responses
  - 调用推导函数计算各子表状态
  - 提供 refreshCompletionStatus() 手动刷新入口
  - _Requirements: 9.5, 9.6_

- [x] 3.4 实现联动锁定逻辑 — isA17_6Locked / isA17_7Locked 计算属性
  - A17-5 status !== 'completed' → A17-6/A17-7 locked
  - 提供 lockReason 字符串用于界面警告显示
  - _Requirements: 10.1, 10.2, 11.1, 11.2_

- [x] 3.5 实现签发前置条件逻辑 — signOffPreconditions / signOffReady
  - 三个前置条件：A17-1 completed + A17-5 completed + A17-7 completed
  - signOffReady = all satisfied
  - _Requirements: 12.1, 12.2, 12.3_

- [x] 3.6 实现 KAM 引用加载 — loadKamReferences
  - 调用 GET /api/projects/{projectId}/kam-references
  - 返回 KamReference[] 存入 ref
  - 错误降级为空数组
  - _Requirements: 13.1, 13.2, 13.3, 13.5_

## 4. 联动 UI 集成

- [x] 4.1 GtA17Bundle 集成 useA17BundleState — 初始化 + Tab 切换刷新
  - onMounted 调用 refreshCompletionStatus + loadKamReferences
  - Tab 从 A17-5 切走时触发 refreshCompletionStatus
  - _Requirements: 9.6_

- [x] 4.2 实现 A17-6/A17-7 锁定 UI — 覆盖 readonly + 警告横幅
  - isA17_6Locked 时 A17-6 子组件 readonly=true（覆盖 props.readonly）
  - isA17_7Locked 时 A17-7 子组件 readonly=true
  - 锁定时在 Tab 内容顶部显示 el-alert 类型=warning，文案为 lockReason
  - _Requirements: 10.3, 10.4, 11.3, 11.4_

- [x] 4.3 实现签发前置条件 UI — program Tab 签发按钮 + 阻断提示
  - program Tab 底部显示签发前置条件清单（✓/✗ + 标签）
  - signOffReady=false 时签发按钮 disabled
  - 用户点击禁用按钮时 ElMessage.warning 列出未完成项
  - _Requirements: 12.4, 12.5_

- [x] 4.4 实现 A17-1 KAM 引用传递 — 将 kamReferences 传入 GtA17Summary
  - GtA17Summary 新增可选 prop `kamReferences?: KamReference[]`
  - 在 ch12（关键审计事项）章节的引导提示区展示引用摘要
  - _Requirements: 13.3, 13.4_

- [x] 4.5 实现完成状态仪表盘 — Tab 栏上方状态条
  - 渲染 4 个状态指示器（A17-1 / A17-5 / A17-6 / A17-7）
  - 三色图标：绿色 ✓ / 黄色 ◐ / 灰色 ○
  - signOffReady 时额外显示"可签发"绿色标签
  - 点击指示器切换到对应 Tab
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

## 5. Checkpoint

- [x] 5.1 确保 TypeScript 编译通过，组件代码无类型错误
  - 确保所有测试通过，如有疑问询问用户

## 6. Property-Based Tests（fast-check）

- [ ]* 6.1 Property 1: 子底稿编码 skip 映射完整性
  - **Property 1: wp_code_overrides 中 A17 系列映射正确**
  - 读取 wp_code_overrides.json，验证 A17→a17-bundle，12 个子底稿→skip
  - **Validates: Requirements 2.1, 2.2**

- [ ]* 6.2 Property 2: wp_id 解析与传播
  - **Property 2: 随机 wp_index → wpIdMap 映射正确**
  - 生成随机 wp_index 数组（含若干 A17-* 条目 + 干扰条目）→ 验证 wpIdMap 仅含 A17-* 且映射正确
  - **Validates: Requirements 3.3, 5.1, 5.4**

- [ ]* 6.3 Property 3: Tab 可见性由 wp_index 存在性驱动
  - **Property 3: 随机 A17-5 子集 → 仅存在的 Tab 可见**
  - 生成随机 A17-5-* 子集 → 验证 visibleTabs 中仅包含存在于 wpIdMap 的 A17-5 Tab
  - **Validates: Requirements 3.6, 6.1, 6.2, 6.3, 6.4**

- [ ]* 6.4 Property 4: sheetName 路由正确激活 Tab
  - **Property 4: 随机 sheetName → active Tab 状态正确**
  - 生成随机 sheetName（合法/非法混合）→ 验证合法值激活对应 Tab，非法值保持不变
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

- [ ]* 6.5 Property 5: readonly 属性透传
  - **Property 5: 随机 readonly 布尔值 → 子组件接收一致**
  - 生成随机 boolean → 验证所有子组件的 readonly prop 与父一致
  - **Validates: Requirements 8.1**

- [ ]* 6.6 Property 6: A17-5 完成状态推导正确性
  - **Property 6: 随机 checklist_responses → deriveA17_5Status 推导正确**
  - 生成随机 responses 数组（conclusion 为 string|null）→ 验证：全非空=completed / 部分=in_progress / 全空=not_started / 空数组=not_started
  - **Validates: Requirements 9.2, 9.3, 9.4**

- [ ]* 6.7 Property 7: 联动锁定一致性
  - **Property 7: A17-5 status → A17-6/A17-7 locked 状态正确**
  - 生成随机 CompletionStatus → 验证 completed 时 unlocked，其他时 locked
  - **Validates: Requirements 10.1, 10.2, 11.1, 11.2**

- [ ]* 6.8 Property 8: 签发前置条件逻辑正确性
  - **Property 8: 三子表随机 status → signOffReady 正确**
  - 生成 3 个随机 CompletionStatus → signOffReady = 三者全 completed
  - **Validates: Requirements 12.1, 12.2, 12.3**

- [ ]* 6.9 Property 9: 仪表盘状态与 completionMap 同步
  - **Property 9: 随机 completionMap → dashboardItems 映射正确**
  - 生成随机 4 子表状态 → 验证 statusToDisplay 映射：completed→✓/green, in_progress→◐/yellow, not_started→○/gray
  - **Validates: Requirements 14.2, 14.3, 14.4**

## 7. Unit Tests（vitest）

- [ ]* 7.1 注册契约测试 — 验证 htmlRendererRegistry 包含 `a17-bundle`，contextProps='standard'；wp_code_overrides A17→a17-bundle + 12 子底稿→skip
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 7.3_

- [ ]* 7.2 Tab 配置测试 — 验证 TABS 静态数组顺序、数量（9 Tab）、kind/wpCode 正确
  - _Requirements: 3.1_

- [ ]* 7.3 wp_id 解析测试 — mock getWpIndex API → 验证 wpIdMap 计算正确 + 子组件接收正确 wp_id
  - _Requirements: 5.1, 5.2, 5.4_

- [ ]* 7.4 适用性过滤测试 — 无 A17-5 条目时隐藏 / 部分存在时仅显示对应 Tab
  - _Requirements: 6.1, 6.3, 6.4_

- [ ]* 7.5 sheetName 路由测试 — 合法值激活 + 非法值保持默认
  - _Requirements: 4.1, 4.4_

- [ ]* 7.6 只读模式透传测试 — readonly=true 时所有子组件 readonly prop 为 true
  - _Requirements: 8.1_

- [ ]* 7.7 后端 VALID_COMPONENT_TYPES 测试 — 验证包含 `a17-bundle`
  - _Requirements: 7.1, 7.2_

- [ ]* 7.8 useA17BundleState 完成状态推导测试 — 各推导函数输入输出验证
  - deriveA17_5Status: 全填/部分/空/空数组 → 正确 status
  - deriveA17_1Status: 必填章节判定
  - deriveA17_7Status: sign_status 判定
  - _Requirements: 9.2, 9.3, 9.4_

- [ ]* 7.9 联动锁定集成测试 — mock completionMap 状态变化 → A17-6/A17-7 readonly 正确
  - completionMap['A17-5']='completed' → A17-6/A17-7 unlocked
  - completionMap['A17-5']='in_progress' → A17-6/A17-7 locked + 警告显示
  - _Requirements: 10.1, 10.2, 10.3, 11.1, 11.2, 11.3_

- [ ]* 7.10 签发前置条件测试 — 验证 signOffPreconditions 列表正确 + signOffReady 逻辑
  - 三者全 completed → ready=true
  - 任一非 completed → ready=false
  - _Requirements: 12.1, 12.2, 12.3_

- [ ]* 7.11 仪表盘渲染测试 — 验证 dashboardItems 正确生成 + 点击切换 Tab
  - 4 个指示器正确渲染
  - 状态变化时图标/颜色更新
  - 点击跳转到对应 Tab
  - _Requirements: 14.1, 14.2, 14.6_

- [ ]* 7.12 KAM 引用加载测试 — mock API → 验证 kamReferences 正确填充 + 错误降级
  - 正常返回 → kamReferences 有值
  - API 失败 → kamReferences 为空数组
  - _Requirements: 13.1, 13.5_

## 8. Final Checkpoint

- [x] 8.1 确保所有测试通过，如有疑问询问用户
  - 运行 vitest（单元测试 + property tests）
  - 验证 TypeScript 编译无错误
  - 验证 componentType 契约测试通过

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 本组件已从"简单 Tab 分发器"升级为"带联动逻辑的聚合组件"
- 新增 `useA17BundleState` composable 管理跨 Tab 状态联动
- composable 仅做数据读取和状态推导，不做数据写入（写入由各子组件自行处理）
- 联动刷新策略：挂载全量 + Tab 切走按需刷新 + 手动刷新按钮
- Property tests 新增 P6~P9 覆盖联动逻辑的正确性
