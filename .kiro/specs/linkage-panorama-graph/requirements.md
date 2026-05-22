# Requirements Document — 联动全景图 (Linkage Panorama Graph)

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v0.1 | 2026-05-20 | 初始起草 |
| v0.2 | 2026-05-20 | Sprint 0 实测后补强：①节点数 60→128 ②severity 3 级→5 级 ③新增 A/B/C/S/other 类节点兜底规则 ④cross_module 类 target 处理 |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| cross_wp_references.json (400 条) | 数据源 | ✅ 已有 |
| unified_dependency_graph.json | 数据源 | ✅ 已有 |
| useCrossModuleRefs composable | 前端 | ✅ 已有（加载 CWR 数据） |
| useStaleImpact composable | 前端 | ✅ 已有（stale 传播链路） |
| D3.js | 前端新增依赖 | 🔲 需引入（~200KB gzipped） |
| Vue Router | 前端依赖 | ✅ 已有 |
| Element Plus | 前端依赖 | ✅ 已有 |
| WorkpaperEditor 路由 | 前端 | ✅ 已有（/projects/:id/workpapers/:wpId） |
| RBAC get_current_user | 后端 | ✅ 已有 |

## Introduction

### 业务痛点

1. **宏观视角缺失**：当前 400 条 cross_wp_references 散落在各 cell 上以紫/蓝/青色标签展示，合伙人/质控无法一眼看到整个项目的底稿依赖关系网络
2. **循环间依赖不可见**：D→K（折旧分摊到费用）、H→K（折旧分摊到管理费用）、N→报表（税金勾稽）等跨循环关键链路需逐个打开底稿才能发现
3. **Stale 影响范围不直观**：useStaleImpact 返回的 affected 列表是扁平文本，无法直观看到"一个底稿变更后影响了多少下游节点"的拓扑结构
4. **依赖断裂排查困难**：当 blocking 级别的 CWR 断裂时，合伙人需要手动追溯上下游关系，无可视化路径
5. **新成员理解成本高**：新加入项目的审计助理需要大量时间理解 11 个循环之间的数据流向
6. **质控抽查无全局地图**：质控人员无法快速定位"哪些底稿是关键枢纽节点（被多个下游引用）"
7. **项目仪表盘缺少联动维度**：partner-dashboard 有进度/VR/复核意见，但缺少"依赖关系健康度"维度

### 技术根因

- 前端无 `/projects/:id/linkage-panorama` 页面路由
- cross_wp_references.json 400 条数据仅在 WorkpaperEditor 内按单底稿维度加载（useCrossModuleRefs），无全量图加载端点
- unified_dependency_graph.json 已有节点+边结构但无前端可视化消费方
- D3.js 未引入项目（当前仅有 ECharts 用于图表）
- 无后端端点返回"全量图数据 + stale 状态叠加"的聚合结构

### 范围边界

**必做（In Scope）：**
- 新建 `/projects/:id/linkage-panorama` 页面路由
- D3.js 力导向图渲染 400 条 CWR 的宏观依赖关系
- 节点按循环着色（D=蓝/E=青/F=绿/G=金/H=橙/I=靛/J=粉/K=灰/L=棕/M=紫/N=红）
- 边按 severity 着色（blocking=红/warning=橙/info=灰）
- 点击节点跳转到对应底稿编辑器
- 缩放/拖拽/搜索定位交互
- 按循环过滤（只看某循环相关的联动）
- Stale 状态叠加显示（有 stale 影响的边闪烁/加粗）
- 响应式布局（适配 1920×1080 和 1366×768）
- 后端轻量 GET 端点返回图数据（聚合 CWR + stale 状态）

**排除（Out of Scope）：**
- 不涉及 unified_dependency_graph.json 的 L3 级别 42,163 条公式依赖（仅展示 CWR 宏观层）
- 不涉及实时 WebSocket 推送图变更（手动刷新）
- 不涉及图编辑功能（只读可视化）
- 不新增 PostgreSQL 表（纯聚合已有 JSON + DB stale 字段）
- 不影响现有 WorkpaperEditor 性能（图在独立视图中渲染）
- 不涉及 docx 类底稿节点（仅 xlsx 底稿 + 报表 + 附注）

## Sprint 0 实测基线（v0.2 补充）

执行 `python scripts/sprint0_panorama_baseline.py`（一次性，用完即删）实测结果：

| 变量 | 实测值 | 说明 |
|------|--------|------|
| `N_cwr_total` | 400 | cross_wp_references.json references 数组长度 |
| `N_cwr_with_wp_target` | 370 | 标准 CWR 边数（target 含 wp_code） |
| `N_cwr_cross_module` | 31 | target_module 类边数（target 无 wp_code，需虚拟模块节点） |
| `N_unique_wp_nodes` | 110 | 去重 wp_code 节点数 |
| `N_unique_module_nodes` | 18 | 去重 cross_module 虚拟节点数 |
| `N_total_unique_nodes` | 128 | 110 + 18 |
| `N_severity_blocking` | 75 | severity=blocking |
| `N_severity_warning` | 202 | severity=warning |
| `N_severity_info` | 75 | severity=info |
| `N_severity_recommended` | 19 | severity=recommended（B/C 类控制建议） |
| `N_severity_required` | 29 | severity=required（A 类必填提示） |
| `N_cycle_A` | 17 | A 类节点（A1/A5 重要性/调整等） |
| `N_cycle_B` | 5 | B 类节点（B15 重要性等） |
| `N_cycle_C` | 12 | C 类节点（C2~C15 控制测试） |
| `N_cycle_S` | 7 | S 类节点（专项程序） |
| `N_cycle_other` | 5 | 不可推断节点（PL/REPORT/T1/TB/disclosure） |

**起草前假设 vs Sprint 0 实测对比**：

| 维度 | 起草假设 | 实测 | 偏差影响 | 修正方案 |
|------|----------|------|----------|----------|
| 节点数 | ~60 | 128 | UI 布局/性能参数需调 | NFR 性能段更新到 128 节点+400 边 |
| 边数 | 400 | 370 标准 + 31 跨模块 = 401 | cross_module 需虚拟节点 | 新增 9.8 验收条款 |
| severity 级别 | 3 级 | 5 级（增 recommended/required） | 颜色/线宽映射缺 2 级 | Requirement 4 补 2 级颜色定义 |
| cycle 推断 | D~N + report + note 13 类 | 实际 17 类（含 A/B/C/S/other） | 推断函数必须有兜底 | Requirement 9.3 补"未匹配归 other" |
| target 结构 | 全部含 wp_code | 7.75% 是 cross_module 类 | 必须支持虚拟模块节点 | Requirement 9.8 新增 |



- **Panorama_Graph_Page**：联动全景图页面组件，路由 `/projects/:id/linkage-panorama`
- **Force_Graph**：D3.js 力导向图核心渲染组件
- **Graph_Node**：图中节点，代表一个底稿/报表/附注（按 wp_code 聚合）
- **Graph_Edge**：图中边，代表一条 CWR 引用关系
- **Cycle_Filter**：循环过滤器组件，支持按 D~N 循环筛选
- **Search_Locator**：搜索定位组件，输入 wp_code 或底稿名称定位节点
- **Stale_Overlay**：Stale 状态叠加层，对有 stale 影响的边施加视觉效果
- **Graph_Data_Endpoint**：后端聚合端点，返回全量图数据 + stale 状态
- **Cycle_Code**：审计循环代号（D/E/F/G/H/I/J/K/L/M/N + 报表/附注 + A/B/C/S 辅助类 + other 兜底）
- **Module_Node**：cross_module 类 target 的虚拟节点，id 形如 `__module__trial_balance`，cycle='module'

## Requirements

### Requirement 1: 全景图页面路由与布局

**User Story:** As a 合伙人, I want to 从项目侧边栏或仪表盘进入联动全景图视图, so that 我可以宏观把握整个项目的底稿依赖关系网络。

#### Acceptance Criteria

1. THE Panorama_Graph_Page SHALL 注册路由 `/projects/:id/linkage-panorama`，从 WorkpaperEditor 侧边栏和项目仪表盘均可进入
2. THE Panorama_Graph_Page SHALL 采用全屏布局，图区域占据视口 100% 宽度和可用高度（减去顶部工具栏 48px）
3. THE Panorama_Graph_Page SHALL 在顶部工具栏显示：项目名称 + "联动全景图"标题 + 循环过滤器 + 搜索框 + 刷新按钮
4. THE Panorama_Graph_Page SHALL 适配 1920×1080 和 1366×768 两种分辨率，图区域自动填充可用空间
5. WHEN 页面加载时, THE Panorama_Graph_Page SHALL 显示加载动画直到图数据获取完成且力导向布局稳定

### Requirement 2: D3.js 力导向图渲染

**User Story:** As a 合伙人, I want to 以力导向图形式看到所有底稿间的依赖关系, so that 我可以直观理解数据流向和关键枢纽节点。

#### Acceptance Criteria

1. THE Force_Graph SHALL 从 Graph_Data_Endpoint 加载全量 CWR 数据并渲染为力导向图（节点=底稿/报表/附注，边=CWR 引用）
2. THE Force_Graph SHALL 在 3000ms 内完成 400 节点+边的首次布局渲染（从数据加载到布局稳定）
3. THE Force_Graph SHALL 对每个 Graph_Node 显示 wp_code 文本标签（如 "D2"、"H1"、"K8"）
4. THE Force_Graph SHALL 对节点大小按出入度（被引用次数 + 引用他人次数）加权，枢纽节点显示更大
5. THE Force_Graph SHALL 对边使用有向箭头指示数据流向（source → target）
6. THE Force_Graph SHALL 在布局稳定后支持用户拖拽单个节点重新定位（拖拽释放后节点固定在新位置）

### Requirement 3: 节点按循环着色

**User Story:** As a 审计助理, I want to 通过颜色快速区分不同循环的底稿, so that 我可以直观看到跨循环的数据流向。

#### Acceptance Criteria

1. THE Force_Graph SHALL 对每个 Graph_Node 按其所属循环着色：D=蓝(#1976D2)/E=青(#00ACC1)/F=绿(#43A047)/G=金(#FDD835)/H=橙(#FB8C00)/I=靛(#3949AB)/J=粉(#EC407A)/K=灰(#78909C)/L=棕(#8D6E63)/M=紫(#AB47BC)/N=红(#E53935)
2. THE Force_Graph SHALL 对报表类节点（BS/IS/CFS/EQ）使用统一深蓝色(#0D47A1)
3. THE Force_Graph SHALL 对附注类节点使用统一深紫色(#4A148C)
4. THE Force_Graph SHALL 在图区域右下角显示颜色图例面板，列出所有循环代号及其对应颜色
5. WHEN 用户 hover 某个节点, THE Force_Graph SHALL 高亮该节点及其所有直接相连的边和邻居节点，其余节点和边降低透明度至 20%

### Requirement 4: 边按 severity 着色

**User Story:** As a 质控人员, I want to 通过边的颜色区分引用关系的严重程度, so that 我可以快速定位 blocking 级别的关键依赖。

#### Acceptance Criteria

1. THE Force_Graph SHALL 对每条 Graph_Edge 按其 severity 着色：blocking=红(#D32F2F)/warning=橙(#F57C00)/info=灰(#9E9E9E)/recommended=浅蓝(#42A5F5)/required=深橙(#EF6C00)
2. THE Force_Graph SHALL 对 blocking/required 级别的边使用 2px 线宽，warning 使用 1.5px，info/recommended 使用 1px
3. WHEN 用户 hover 某条边, THE Force_Graph SHALL 显示 tooltip 包含：ref_id + description + source_wp → target_wp + severity + category
4. THE Force_Graph SHALL 在图例面板中同时展示边的 severity 颜色说明

### Requirement 5: 点击节点跳转底稿

**User Story:** As a 审计助理, I want to 点击全景图中的某个节点直接跳转到对应底稿编辑器, so that 我可以从宏观视图快速进入具体底稿工作。

#### Acceptance Criteria

1. WHEN 用户单击某个 Graph_Node, THE Panorama_Graph_Page SHALL 跳转到对应底稿编辑器页面（`/projects/:id/workpapers/:wpId`）
2. WHEN 用户单击报表类节点, THE Panorama_Graph_Page SHALL 跳转到报表页面（`/projects/:id/reports`）
3. WHEN 用户单击附注类节点, THE Panorama_Graph_Page SHALL 跳转到附注编辑器页面（`/projects/:id/disclosure-notes`）
4. IF 对应底稿在当前项目中不存在, THEN THE Panorama_Graph_Page SHALL 显示 toast 提示"该底稿尚未创建"且不跳转
5. THE Panorama_Graph_Page SHALL 在跳转前调用 `useNavigationStack().push()` 以支持 Backspace 返回全景图

### Requirement 6: 缩放/拖拽/搜索定位

**User Story:** As a 合伙人, I want to 在全景图中自由缩放、拖拽画布、搜索定位特定底稿, so that 我可以聚焦查看感兴趣的区域。

#### Acceptance Criteria

1. THE Force_Graph SHALL 支持鼠标滚轮缩放（缩放范围 0.1x ~ 5x），缩放中心为鼠标指针位置
2. THE Force_Graph SHALL 支持鼠标左键拖拽画布平移
3. THE Search_Locator SHALL 提供搜索输入框，支持按 wp_code 或底稿描述模糊搜索
4. WHEN 用户在 Search_Locator 中选择某个结果, THE Force_Graph SHALL 平滑动画将该节点居中显示并放大至 2x + 闪烁高亮 3 次
5. THE Force_Graph SHALL 提供"重置视图"按钮，点击后恢复初始缩放比例和居中位置
6. THE Force_Graph SHALL 提供"适应窗口"按钮，点击后自动缩放使所有可见节点恰好填满视口（含 10% padding）

### Requirement 7: 按循环过滤

**User Story:** As a 项目经理, I want to 只查看某个循环相关的联动关系, so that 我可以聚焦分析特定循环的上下游依赖。

#### Acceptance Criteria

1. THE Cycle_Filter SHALL 提供多选下拉框，列出 D~N 共 11 个循环 + "报表" + "附注" 选项
2. WHEN 用户选择一个或多个循环, THE Force_Graph SHALL 仅显示所选循环的节点及其直接相连的边和邻居节点
3. WHEN 过滤激活时, THE Force_Graph SHALL 对不在过滤范围内的节点和边完全隐藏（非降低透明度）
4. THE Cycle_Filter SHALL 默认选中全部循环（即不过滤，显示完整图）
5. WHEN 用户清空过滤选择, THE Force_Graph SHALL 恢复显示完整图
6. THE Cycle_Filter SHALL 在每个选项旁显示该循环的节点数量（如 "D (15)"）

### Requirement 8: Stale 状态叠加显示

**User Story:** As a 合伙人, I want to 在全景图中看到哪些依赖关系当前处于 stale 状态, so that 我可以快速识别需要重新计算的底稿链路。

#### Acceptance Criteria

1. THE Stale_Overlay SHALL 对有 stale 影响的边施加 CSS 动画闪烁效果（0.8s 周期）+ 线宽加粗至原始的 2 倍
2. THE Stale_Overlay SHALL 对 prefill_stale=True 的底稿节点添加黄色虚线边框指示
3. WHEN 用户 hover 某个 stale 节点, THE Stale_Overlay SHALL 在 tooltip 中显示"该底稿预填充数据已过期，需重新计算"
4. THE Panorama_Graph_Page SHALL 在工具栏显示 stale 统计摘要："N 个底稿 / M 条引用处于过期状态"
5. THE Stale_Overlay SHALL 提供"仅显示 stale"切换按钮，激活后隐藏所有非 stale 的节点和边

### Requirement 9: 后端图数据端点

**User Story:** As a 前端开发者, I want to 通过单个 API 获取全量图数据（含节点、边、stale 状态）, so that 前端可以一次请求完成图渲染。

#### Acceptance Criteria

1. THE Graph_Data_Endpoint SHALL 提供 GET `/api/projects/{pid}/linkage-panorama/graph-data` 端点
2. THE Graph_Data_Endpoint SHALL 在响应中返回：nodes[]（wp_code + cycle + label + is_stale）+ edges[]（source + target + ref_id + severity + category + is_stale）+ statistics（节点数/边数/stale 数/blocking 数）
3. THE Graph_Data_Endpoint SHALL 从 cross_wp_references.json 加载全量 CWR 并聚合为图结构（按 wp_code 去重节点）；节点数量、边数量、severity 分布以运行时聚合结果为准（实测基线见 Sprint 0 段，禁止断言字面量）
4. THE Graph_Data_Endpoint SHALL 从数据库查询当前项目所有底稿的 prefill_stale 字段，叠加到对应节点
5. THE Graph_Data_Endpoint SHALL 在 ≤ 1000ms 内返回响应
6. THE Graph_Data_Endpoint SHALL 使用 `Depends(get_current_user)` 认证守卫，并校验用户对该 project_id 的访问权限
7. IF cross_wp_references.json 加载失败, THEN THE Graph_Data_Endpoint SHALL 返回 503 并附带错误描述
8. WHEN CWR target 字段为 cross_module 类（不含 wp_code，含 target_module + target_field）, THE Graph_Data_Endpoint SHALL 生成虚拟模块节点（id=`__module__{target_module}`，cycle='module'，label=target_module），并建立 source_wp → 虚拟节点的边
9. THE Graph_Data_Endpoint cycle 推断 SHALL 按以下顺序：①wp_code 首字母 ∈ {A,B,C,D,E,F,G,H,I,J,K,L,M,N,S} → 该字母（且首字母后非字母，避免 BS/EQ 误命中 B/E）②BS/IS/CFS/EQ 前缀 → 'report' ③"附注" 中文前缀或 NOTE 前缀 → 'note' ④`__module__` 前缀 → 'module' ⑤其余 → 'other'

## Non-Functional Requirements

### 性能

- 图渲染性能：CWR 实测节点数（≥ 100）+ 边数（≥ 370）在 3000ms 内完成首次布局（从数据加载到布局稳定）
- 后端端点响应时间 ≤ 1000ms
- 缩放/拖拽交互帧率 ≥ 30fps（在 1366×768 分辨率下）
- D3.js 力模拟迭代次数上限 300 次（防止低端设备卡顿）

### 兼容性

- 不影响现有 WorkpaperEditor 性能（图在独立视图/页面中渲染，不共享 D3 实例）
- 不新增 PostgreSQL 表（纯聚合 JSON 文件 + 已有 DB stale 字段）
- 兼容已有 useCrossModuleRefs 的数据结构（复用 RawReference 类型）
- D3.js 作为新依赖引入，不替换已有 ECharts（两者共存）

### 可观测性

- 后端日志记录每次图数据请求的 project_id + user_id + 响应耗时 + 节点数/边数
- 前端 console.info 记录力导向布局稳定耗时 + 节点/边渲染数量
- 前端 console.warn 记录图数据加载失败或布局超时

### 响应式

- 1920×1080：图区域 1920×(1080-48-48)px，节点标签全部显示
- 1366×768：图区域 1366×(768-48-48)px，节点标签在缩放 < 0.5x 时隐藏以减少视觉噪音

## Test Matrix

### 单元测试

| 文件 | 覆盖范围 |
|------|----------|
| `backend/tests/test_linkage_panorama_endpoint.py` | 图数据端点 + stale 叠加 + 错误降级 |
| `frontend/src/views/__tests__/LinkagePanorama.spec.ts` | 页面渲染 + 路由注册 + 工具栏交互 |
| `frontend/src/components/__tests__/ForceGraph.spec.ts` | D3 力导向图初始化 + 节点/边渲染 + 交互 |
| `frontend/src/composables/__tests__/usePanoramaGraph.spec.ts` | 数据加载 + 过滤 + 搜索逻辑 |

### PBT (Property-Based Tests)

| ID | Property | 描述 |
|----|----------|------|
| PBT-P1 | node_count_invariant | 过滤后可见节点数 ≤ 总节点数（单调递减） |
| PBT-P2 | edge_endpoint_validity | 任意边的 source 和 target 均存在于节点集合中（引用完整性） |
| PBT-P3 | stale_overlay_subset | stale 边集合 ⊆ 全部边集合（子集关系） |

### 集成测试

- 后端端点 → cross_wp_references.json 加载 → DB stale 查询 → 聚合响应
- 前端页面 → API 调用 → D3 渲染 → 交互（缩放/过滤/搜索/点击跳转）

### UAT

| # | 验收项 | P |
|---|--------|---|
| 1 | 从侧边栏/仪表盘可进入联动全景图页面 | P0 |
| 2 | 力导向图正确渲染全量 CWR 节点和边（数量以 Sprint 0 实测基线为准） | P0 |
| 3 | 节点按循环着色且图例正确 | P0 |
| 4 | 边按 severity 着色（blocking 红/warning 橙/info 灰） | P0 |
| 5 | 点击节点可跳转到对应底稿编辑器 | P0 |
| 6 | 缩放/拖拽/重置视图/适应窗口正常工作 | P1 |
| 7 | 搜索定位节点（输入 wp_code 居中高亮） | P1 |
| 8 | 按循环过滤正确隐藏/显示节点和边 | P1 |
| 9 | Stale 状态叠加显示（边闪烁 + 节点虚线框） | P1 |
| 10 | 首次布局渲染 ≤ 3000ms | P1 |
| 11 | 响应式适配 1366×768 分辨率 | P2 |
| 12 | 后端端点响应 ≤ 1000ms | P2 |

**上线门槛：P0 全部 ✓ + P1 ≥ 80% ✓**

## Success Criteria

- 合伙人/质控可在单页面内一眼看到整个项目 400 条 CWR 的宏观依赖关系网络
- 跨循环关键链路（如 H→K 折旧分摊、N→报表税金勾稽）通过颜色和布局直观可见
- 从全景图到任意底稿的跳转路径 = 1 次点击
- Stale 状态在图上直观可见，无需逐个打开底稿检查
- 首次布局渲染 ≤ 3s，交互帧率 ≥ 30fps

## Terminology

| 术语 | 定义 |
|------|------|
| CWR | Cross Workpaper Reference，跨底稿引用（cross_wp_references.json 中的条目） |
| 力导向图 | Force-Directed Graph，D3.js 提供的基于物理模拟的图布局算法 |
| Severity | CWR 引用断裂时的严重程度：blocking(阻断签字)/warning(警告)/info(提示) |
| Stale | 预填充数据过期状态，表示上游数据已变更但当前底稿未重新计算 |
| 循环 (Cycle) | 审计业务循环，D~N 共 11 个 |
| 枢纽节点 | 被多个下游引用的关键底稿节点（如 H1 折旧分配表被 K8/K9/F5 等引用） |
| 图例 (Legend) | 颜色说明面板，展示节点循环色和边 severity 色的对应关系 |
