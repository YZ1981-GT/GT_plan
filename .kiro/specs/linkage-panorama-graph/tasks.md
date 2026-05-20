# Implementation Plan: 联动全景图 (Linkage Panorama Graph)

## Overview

基于 requirements.md 和 design.md，将联动全景图功能拆分为 2 个 Sprint：Sprint 1 后端端点 + D3 依赖 + ForceGraph 核心组件，Sprint 2 交互功能（zoom/filter/search/stale）+ 页面集成 + 测试。后端使用 Python（FastAPI + hypothesis PBT），前端使用 TypeScript（Vue 3 + D3.js + Element Plus + vitest + fast-check PBT）。

预计工时：3 天（Sprint 1: 1.5 天，Sprint 2: 1.5 天）

## Tasks

- [ ] 1. Sprint 1 — 后端端点 + D3 依赖 + ForceGraph 核心
  - [ ] 1.1 创建后端图数据聚合服务
    - 创建 `backend/app/services/linkage_panorama_aggregator.py`
    - 实现 `aggregate_graph_from_cwr(references)` 函数：遍历 400 条 CWR → 按 wp_code 去重聚合节点 → 生成边列表
    - 节点聚合：收集所有 `source_wp` + `targets[].wp_code` → 去重 → 推断 cycle（首字母 D~N / BS|IS|CFS|EQ→report / 其他→note）
    - 计算每个节点的 degree（出入度）
    - 实现 `overlay_stale_status(nodes, edges, stale_wp_codes)` 函数：将 DB 查询的 stale wp_codes 叠加到节点和边
    - 边 is_stale 规则：source 或 target 任一 stale → 边 stale
    - 实现 `compute_statistics(nodes, edges)` 函数：计算 node_count/edge_count/stale_node_count/stale_edge_count/blocking_edge_count
    - _Requirements: 9.2, 9.3_

  - [ ] 1.2 创建后端 linkage_panorama.py 路由
    - 创建 `backend/app/routers/linkage_panorama.py`
    - `GET /api/projects/{project_id}/linkage-panorama/graph-data` 端点
    - 加载 `cross_wp_references.json` → 调用 aggregator → 查询 DB `prefill_stale` → 叠加 stale → 返回 GraphDataResponse
    - 使用 `Depends(get_current_user)` 认证守卫 + 校验用户对 project_id 的访问权限
    - JSON 加载失败时返回 503 + 错误描述
    - 注册路由到 `router_registry.py`（§6 底稿域 或新增 §9 可视化域）
    - _Requirements: 9.1, 9.4, 9.5, 9.6, 9.7_

  - [ ] 1.3 编写后端单元测试
    - 创建 `backend/tests/test_linkage_panorama_endpoint.py`
    - 测试 GET graph-data happy path（返回 nodes + edges + statistics 结构）
    - 测试认证守卫（无 token → 401）
    - 测试 JSON 加载失败 → 503
    - 创建 `backend/tests/test_linkage_panorama_aggregator.py`
    - 测试空 CWR → 空图
    - 测试单条 CWR → 2 节点 1 边
    - 测试 cycle 推断逻辑（D1→D, BS→report, 附注→note）
    - 测试 degree 计算正确性
    - 测试 stale 叠加逻辑（source stale → 边 stale / target stale → 边 stale）
    - 测试 statistics 计算
    - _Requirements: 9.1~9.7_

  - [ ] 1.4 安装 D3.js 前端依赖
    - `npm install d3 --save` + `npm install @types/d3 --save-dev`
    - 确认 package.json 版本锁定（exact version）
    - 确认 TypeScript 类型正确引入（`import * as d3 from 'd3'` 无报错）
    - _Requirements: 依赖矩阵 D3.js_

  - [ ] 1.5 创建 usePanoramaGraph composable
    - 创建 `audit-platform/frontend/src/composables/usePanoramaGraph.ts`
    - 实现 `fetchGraphData()` → 调用 API → 存储 graphData
    - 实现 `d3Nodes` / `d3Links` computed：将 API 响应转换为 D3 simulation 所需格式
    - 实现 `selectedCycles` ref + `showOnlyStale` ref
    - 实现 `filteredNodes` / `filteredLinks` computed：根据 selectedCycles + showOnlyStale 过滤
    - 实现 `searchNodes(query)` 方法：按 wp_code 或 label 模糊匹配
    - 实现 `getCycleNodeCounts()` 方法：返回每个循环的节点数量
    - _Requirements: 2.1, 6.3, 7.2, 7.6, 8.5_

  - [ ] 1.6 创建 ForceGraph.vue 核心组件
    - 创建 `audit-platform/frontend/src/components/panorama/ForceGraph.vue`
    - Props: `nodes: D3Node[]`, `links: D3Link[]`, `width: number`, `height: number`
    - onMounted: 创建 SVG → 初始化 d3.forceSimulation → 设置 force 参数（charge=-300, linkDistance=80, collision, center）
    - 渲染节点：circle 元素 + 按 cycle 着色（CYCLE_COLOR_MAP）+ 按 degree 缩放半径
    - 渲染边：line 元素 + 按 severity 着色（SEVERITY_COLOR_MAP）+ 按 severity 设置线宽 + 箭头 marker
    - 渲染标签：text 元素显示 wp_code
    - tick handler：每帧更新所有 SVG 元素的 x/y 位置
    - watch(props.nodes/links)：数据变化时重启 simulation
    - onBeforeUnmount：停止 simulation + 清理事件
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 4.1, 4.2_

  - [ ] 1.7 创建 GraphLegend.vue 图例组件
    - 创建 `audit-platform/frontend/src/components/panorama/GraphLegend.vue`
    - 显示 11 个循环颜色 + 报表深蓝 + 附注深紫
    - 显示 3 个 severity 颜色（blocking 红 / warning 橙 / info 灰）
    - 固定定位在图区域右下角
    - _Requirements: 3.4, 4.4_

  - [ ] 1.8 注册前端路由
    - 在 `audit-platform/frontend/src/router/index.ts` 中注册 `/projects/:projectId/linkage-panorama` 路由
    - 组件：`() => import('@/views/LinkagePanoramaView.vue')`（懒加载）
    - 路由名称：`LinkagePanorama`
    - _Requirements: 1.1_

  - [ ] 1.9 创建 LinkagePanoramaView.vue 页面骨架
    - 创建 `audit-platform/frontend/src/views/LinkagePanoramaView.vue`
    - 全屏布局：顶部工具栏 48px + 图区域填满剩余高度
    - 工具栏：项目名称 + "联动全景图" 标题 + 占位 slot（过滤器/搜索/按钮在 Sprint 2 填充）
    - 加载状态：`v-loading` 指令覆盖图区域
    - 调用 `usePanoramaGraph` 获取数据 → 传递给 ForceGraph 组件
    - _Requirements: 1.2, 1.3, 1.5_

- [ ] 2. Sprint 2 — 交互功能 + 页面集成 + 测试
  - [ ] 2.1 实现缩放/拖拽交互
    - 在 ForceGraph.vue 中添加 `d3.zoom()` behavior
    - 缩放范围：scaleExtent([0.1, 5])
    - 缩放中心：鼠标指针位置
    - 拖拽画布：zoom translateExtent
    - 拖拽节点：d3.drag() 绑定到节点 → 拖拽释放后固定位置（fx/fy）
    - _Requirements: 6.1, 6.2, 2.6_

  - [ ] 2.2 实现 hover 高亮 + tooltip
    - 节点 hover：高亮该节点 + 直接相连的边和邻居节点，其余降低透明度至 20%
    - 边 hover：显示 tooltip（ref_id + description + source→target + severity + category）
    - 创建 `GraphTooltip.vue` 组件（绝对定位，跟随鼠标）
    - Stale 节点 hover：tooltip 追加"该底稿预填充数据已过期，需重新计算"
    - _Requirements: 3.5, 4.3, 8.3_

  - [ ] 2.3 实现点击节点跳转
    - 节点 click 事件：根据 node.cycle 决定跳转目标
    - workpaper 类：`router.push(/projects/:id/workpapers?wp_code=xxx)`
    - report 类：`router.push(/projects/:id/reports)`
    - note 类：`router.push(/projects/:id/disclosure-notes)`
    - 跳转前调用 `useNavigationStack().push()` 支持 Backspace 返回
    - 底稿不存在时 toast 提示"该底稿尚未创建"
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 2.4 创建 CycleFilter.vue 组件
    - 创建 `audit-platform/frontend/src/components/panorama/CycleFilter.vue`
    - el-select multiple：D~N 11 个循环 + "报表" + "附注"
    - 每个选项旁显示节点数量（如 "D (15)"）
    - 默认全选（不过滤）
    - 选择变化 → 更新 `usePanoramaGraph.selectedCycles`
    - 清空选择 → 恢复全图
    - _Requirements: 7.1, 7.4, 7.5, 7.6_

  - [ ] 2.5 创建 SearchLocator.vue 组件
    - 创建 `audit-platform/frontend/src/components/panorama/SearchLocator.vue`
    - el-autocomplete：输入时调用 `usePanoramaGraph.searchNodes(query)` 获取匹配节点
    - 选择结果 → emit `locate(nodeId)` → ForceGraph 平滑动画居中 + 放大 2x + 闪烁高亮 3 次
    - _Requirements: 6.3, 6.4_

  - [ ] 2.6 实现 Stale 状态叠加
    - ForceGraph 中对 `is_stale=true` 的边添加 `.edge-stale` class（CSS 动画闪烁 0.8s + 线宽 2x）
    - 对 `is_stale=true` 的节点添加 `.node-stale` class（黄色虚线边框）
    - 工具栏显示 stale 统计摘要："N 个底稿 / M 条引用处于过期状态"
    - "仅显示 stale" el-switch → 更新 `usePanoramaGraph.showOnlyStale`
    - _Requirements: 8.1, 8.2, 8.4, 8.5_

  - [ ] 2.7 实现重置视图 + 适应窗口按钮
    - "重置视图"按钮：恢复 zoom transform 为 identity（scale=1, translate=0,0）
    - "适应窗口"按钮：计算所有可见节点的 bounding box → 自动缩放使节点填满视口（含 10% padding）
    - _Requirements: 6.5, 6.6_

  - [ ] 2.8 完善 LinkagePanoramaView 页面集成
    - 工具栏集成：CycleFilter + SearchLocator + StaleToggle + 刷新/重置/适应按钮
    - 响应式布局：1920×1080 和 1366×768 适配（图区域自动填充）
    - 1366×768 下缩放 < 0.5x 时隐藏节点标签
    - 侧边栏入口：在项目侧边栏添加"联动全景图"菜单项
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.4_

  - [ ] 2.9 编写前端单元测试
    - 创建 `audit-platform/frontend/src/views/__tests__/LinkagePanorama.spec.ts`
    - 测试页面渲染 + 路由注册 + 工具栏元素存在
    - 创建 `audit-platform/frontend/src/components/__tests__/ForceGraph.spec.ts`
    - 测试 D3 simulation 初始化 + 节点/边 SVG 元素创建 + 颜色映射正确
    - 创建 `audit-platform/frontend/src/composables/__tests__/usePanoramaGraph.spec.ts`
    - 测试 fetchGraphData API 调用 + d3Nodes/d3Links 转换 + 过滤逻辑 + 搜索逻辑
    - _Requirements: 全部前端需求_

- [ ] 3. PBT 属性测试
  - [ ]* 3.1 Write property test: node count invariant (P1)
    - **Property 1: Node count invariant**
    - 创建 `backend/tests/test_linkage_panorama_pbt.py`
    - 使用 hypothesis 生成随机 CWR references 列表（随机 source_wp + targets[].wp_code）
    - 调用 `aggregate_graph_from_cwr` → 验证 `len(nodes) == len(set(all_wp_codes))`
    - 验证 nodes 列表中无重复 id
    - ≥ 100 iterations
    - **Validates: Requirements 9.3**

  - [ ]* 3.2 Write property test: edge endpoint validity (P2)
    - **Property 2: Edge endpoint validity**
    - 使用 hypothesis 生成随机 CWR references
    - 调用 `aggregate_graph_from_cwr` → 验证每条 edge 的 source 和 target 均存在于 nodes 的 id 集合中
    - ≥ 100 iterations
    - **Validates: Requirements 9.2, 2.1**

  - [ ]* 3.3 Write property test: stale subset invariant (P3)
    - **Property 3: Stale subset invariant**
    - 使用 hypothesis 生成随机 nodes + 随机 stale_wp_codes 子集
    - 调用 `overlay_stale_status` → 验证 stale_nodes ⊆ all_nodes 且 stale_edges ⊆ all_edges
    - 验证 edge.is_stale ↔ (source.is_stale OR target.is_stale)
    - ≥ 100 iterations
    - **Validates: Requirements 8.1, 8.2, 8.5**

- [ ] 4. Checkpoint — 全部测试通过 + 回归零失败
  - 运行 `python -m pytest backend/tests/test_linkage_panorama*.py -v`
  - 运行 `npx vitest --run` 确认前端测试全绿
  - 确认现有 useCrossModuleRefs / useStaleImpact 测试无回归
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional PBT tasks and can be skipped for faster MVP
- Sprint 1（后端 + D3 核心）预计 1.5 天，Sprint 2（交互 + 集成 + 测试）预计 1.5 天
- D3.js 作为新依赖引入，不替换已有 ECharts（两者共存，按需加载）
- 后端不新增 PG 表，纯聚合 cross_wp_references.json + 已有 DB prefill_stale 字段
- 后端 PBT 使用 hypothesis（≥ 100 iterations），前端 PBT 使用 fast-check（≥ 100 iterations）
- ForceGraph 组件使用 D3 直接操作 SVG DOM，Vue 仅管理生命周期（ADR-4）
