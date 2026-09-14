# Tasks — A16 管理层声明书聚合组件

## 1. 注册与配置

- [x] 1.1 在 `htmlRendererRegistry.ts` 的 `HtmlComponentType` union 中新增 `'a16-bundle'`
- [x] 1.2 添加 lazy import: `const GtA16Bundle = defineAsyncComponent(() => import('./GtA16Bundle.vue'))`
- [x] 1.3 在 `REGISTRY_LIST` 中新增注册条目：componentType=`a16-bundle`, icon='📜', label='A16 管理层声明书', emits=[], contextProps='standard'
- [x] 1.4 更新 `wp_code_overrides.json`：`"A16"` → `"a16-bundle"`；`"A16-1"` ~ `"A16-7"` 全部映射为 `"skip"`
  - _Requirements: 1.1, 2.1, 2.2_
- [x] 1.5 后端 `wp_classification_service.py` 的 `VALID_COMPONENT_TYPES` 中新增 `"a16-bundle"`
  - _Requirements: 1.4_

## 2. Vue 组件实现

- [x] 2.1 创建 `GtA16Bundle.vue` — script setup + props 定义
  - Props: wpId(必填), sheetName?(可选), readonly?(可选)
  - 定义 TABS 静态数组（7 个 Tab：A16-1~A16-7 含 id/label/wpCode）
  - _Requirements: 1.2, 3.1_

- [x] 2.2 实现 wp_id 解析逻辑 — onMounted 调用 getWpIndex + wpIdMap 计算属性
  - 通过 getWpIndex(projectId) 获取项目底稿索引
  - 过滤 A16-* 条目生成 `wpIdMap: Record<string, string>`
  - visibleTabs 计算属性：仅保留 wpIdMap 中存在的 Tab
  - _Requirements: 5.1, 5.2, 5.3, 3.3_

- [x] 2.3 实现 sheetName 路由 — watch props.sheetName + route.query.sheet → 激活对应 Tab
  - 合法 Tab id → 切换 active；不合法 → 保持默认（第一个可见 Tab）
  - _Requirements: 4.1, 4.2_

- [x] 2.4 实现 template — el-tabs 渲染 WorkpaperWordEditor
  - 每个 Tab 渲染 WorkpaperWordEditor，传入 wp-id=wpIdMap[tab.wpCode] + readonly
  - _Requirements: 3.2, 6.1_

## 3. Checkpoint

- [x] 3.1 TypeScript 编译通过，组件代码无类型错误
  - getDiagnostics 验证 GtA16Bundle.vue + htmlRendererRegistry.ts 无错误

## 4. Property-Based Tests（fast-check）

- [ ]* 4.1 Property 1: wp_code_overrides 中 A16 系列映射正确
  - 读取 wp_code_overrides.json，验证 A16→a16-bundle，7 个子底稿→skip
  - **Validates: Requirements 2.1, 2.2**

- [ ]* 4.2 Property 2: 随机 wp_index → wpIdMap 映射正确
  - 生成随机 wp_index 数组（含若干 A16-* 条目 + 干扰条目）→ 验证 wpIdMap 仅含 A16-* 且映射正确
  - **Validates: Requirements 5.1, 5.2**

- [ ]* 4.3 Property 3: 随机 A16-* 子集 → 仅存在的 Tab 可见
  - 生成随机 A16-1~A16-7 子集 → 验证 visibleTabs 仅包含存在于 wpIdMap 的 Tab
  - **Validates: Requirements 3.3, 5.3**

- [ ]* 4.4 Property 4: 随机 sheetName → active Tab 状态正确
  - 生成随机 sheetName（合法/非法混合）→ 验证合法值激活对应 Tab，非法值保持默认
  - **Validates: Requirements 4.1, 4.2**

- [ ]* 4.5 Property 5: 随机 readonly 布尔值 → 子组件接收一致
  - 生成随机 boolean → 验证所有 WorkpaperWordEditor 的 readonly prop 一致
  - **Validates: Requirements 6.1**

## 5. Unit Tests（vitest）

- [ ]* 5.1 注册契约测试 — 验证 htmlRendererRegistry 包含 `a16-bundle`，contextProps='standard'
  - _Requirements: 1.1, 1.3_

- [ ]* 5.2 wp_code_overrides 映射测试 — A16→a16-bundle + 7 子底稿→skip
  - _Requirements: 2.1, 2.2_

- [ ]* 5.3 Tab 配置测试 — 验证 TABS 数组数量（7 Tab）、id/label/wpCode 正确
  - _Requirements: 3.1_

- [ ]* 5.4 wp_id 解析测试 — mock getWpIndex API → 验证 wpIdMap + visibleTabs
  - _Requirements: 5.1, 5.2, 5.3_

- [ ]* 5.5 sheetName 路由测试 — 合法值激活 + 非法值保持默认
  - _Requirements: 4.1, 4.2_

- [ ]* 5.6 只读模式透传测试 — readonly=true 时所有子组件 readonly prop 为 true
  - _Requirements: 6.1_

- [ ]* 5.7 后端 VALID_COMPONENT_TYPES 测试 — 验证包含 `a16-bundle`
  - _Requirements: 1.4_

## 6. Final Checkpoint

- [x] 6.1 确保所有测试通过，TypeScript 编译无错误

## Notes

- Tasks marked with `*` are optional
- 本组件是最简 bundle 模式：纯 Tab + WorkpaperWordEditor，无 composable、无联动、无完成追踪
- 参照 GtA11Bundle 实现模式，预计 ~80 行 Vue 代码
- 适用性完全由 wp_index 存在性决定（不同项目类型声明书种类不同）
