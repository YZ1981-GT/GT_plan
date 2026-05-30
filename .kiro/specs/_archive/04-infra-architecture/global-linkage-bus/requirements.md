# 全局联动总线（Unified Linkage Bus）— 需求文档

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v1.0 | 2026-05-17 | 初始版本 | GLOBAL_LINKAGE_ARCHITECTURE_PROPOSAL.md |

## 前言

### 业务痛点
- 底稿保存后下游模块（报表/附注）不知道数据已变更
- 公式管理改配置后引用方底稿不会 stale
- 附注/报表改了不会反向通知底稿
- 两套 stale 机制并存（eventBus 写 DB vs Address Registry 返回前端），互不通信
- 用户无法从单元格直接看到"我的数据从哪来、谁引用了我"

### 技术根因
- 三套公式引擎各管一段（report_engine / prefill_engine / formula_unified）
- 预填充双路径并存（mapping 语义行 vs engine 扫内嵌公式）
- 无统一依赖图，各模块独立维护引用关系
- 109 个 docx 底稿完全脱离联动链路

### 本 spec 定位
基于 `docs/GLOBAL_LINKAGE_ARCHITECTURE_PROPOSAL.md` 方案，实现统一联动总线，消除两套机制并存，打通全模块双向联动。

---

## 一、范围边界

### 1.1 必做（F 编号）

| # | 需求 | 模块 | 优先级 |
|---|------|------|--------|
| F1 | 统一依赖图构建（6 数据源合并） | 后端 | P0 |
| F2 | 统一 URI 寻址格式 `{module}:{code}:{sheet_name}:{label}` | 后端 | P0 |
| F3 | 运行时 label→物理坐标解析器 | 后端 | P0 |
| F4 | 地址解析三层优先级（override→header_rules→启发式） | 后端 | P0 |
| F5 | address_label_overrides.json 全局规则文件 | 后端 | P0 |
| F6 | Stale Propagation Engine 统一化 | 后端 | P0 |
| F7 | 统一引擎同时写 DB stale + SSE 推送前端 | 后端+前端 | P0 |
| F8 | 前端 useStaleImpact 改调统一端点 | 前端 | P0 |
| F9 | 反向索引构建（FormulaReverseIndex） | 后端 | P1 |
| F10 | report_config 改公式 → 底稿 stale | 后端 | P1 |
| F11 | prefill_mapping 改 → 底稿 stale | 后端 | P1 |
| F12 | 底稿保存 → 引用该底稿的其他底稿 stale（写 DB） | 后端 | P1 |
| F13 | 附注保存 → 引用该附注的底稿 stale | 后端 | P1 |
| F14 | 科目映射改 → 全链路 stale | 后端 | P1 |
| F15 | 报表行变更 → 引用该行的底稿 stale | 后端 | P1 |
| F16 | 109 个 docx 底稿占位符扫描 + 纳入联动 | 后端 | P2 |
| F17 | 前端统一 stale badge 样式（所有模块） | 前端 | P2 |
| F18 | SSE 推送 linkage:stale-changed 事件 | 后端+前端 | P2 |
| F19 | 公式穿透方向 1：从公式找引用方 | 后端+前端 | P2 |
| F20 | 公式穿透方向 2：从文档找公式 | 后端+前端 | P2 |
| F21 | 公式穿透方向 3：单元格右键公式详情 | 后端+前端 | P2 |
| F22 | 5 模块右键菜单统一接入 | 前端 | P2 |
| F23 | FormulaManagerDialog 增强（引用方列/健康度/URI 搜索） | 前端 | P2 |
| F24 | 用户手动校正 API（override/header-rule） | 后端 | P1 |
| F25 | 降级策略（引擎不可用时回退 event_handlers） | 后端+前端 | P1 |
| F26 | 审计日志（linkage_audit_log） | 后端 | P2 |
| F27 | 健康检查端点 /api/linkage/health | 后端 | P2 |
| F28 | 多项目隔离（stale 按 project_id 过滤） | 后端 | P0 |

### 1.2 排除（独立 Sprint）

| # | 排除项 | 理由 |
|---|--------|------|
| O1 | 三套公式引擎合并为一套 | 工程量过大，当前各管一段可接受 |
| O2 | 预填充双路径合并 | 两条路径各有适用场景，不合并 |
| O3 | 物理坐标硬编码到依赖图 | 设计决策：用语义 label，物理坐标运行时解析 |
| O4 | 前端实时 BFS 动画 | 锦上添花，不影响核心功能 |

---

## 二、功能需求

### 2.A 统一依赖图（F1-F5）

- F1：从 6 个数据源构建统一依赖图（prefill_formula_mapping / cross_wp_references / report_config.formula / L3 dependencies / note_account_mapping / account_mapping）
- F2：全部节点和边使用统一 URI 格式 `{module}:{code}:{sheet_name}:{label}`
- F3：运行时解析器将语义 label 翻译为物理坐标（全 sheet 扫描，不限前 3 行）
- F4：三层优先级（用户 override > header_rules > 启发式）
- F5：`address_label_overrides.json` 持久化用户校正规则

### 2.B Stale 传播引擎（F6-F8, F28）

- F6：`StalePropagationEngine.on_change(uri, project_id, year)` 统一入口
- F7：一次 BFS 同时写 DB stale 字段 + SSE 推送前端
- F8：前端 useStaleImpact 改调 `/api/linkage/impact`
- F28：BFS 传播按 project_id 隔离

### 2.C 反向联动（F9-F15）

- F9：FormulaReverseIndex 从公式文本解析"被引用方→引用方"反向索引
- F10：report_config PUT 追加 FORMULA_CONFIG_CHANGED 事件
- F11：seed 端点追加 PREFILL_MAPPING_CHANGED 事件
- F12：notify-cell-change 追加 mark_stale 写 DB
- F13：disclosure_notes PUT 追加 NOTE_SECTION_SAVED 事件
- F14：account_mapping 增删改追加 ACCOUNT_MAPPING_CHANGED 事件
- F15：generate_all_reports 对比新旧值发布 REPORT_ROW_CHANGED 事件

### 2.D docx + 前端统一展示（F16-F18）

- F16：mammoth 扫描 109 个 docx 占位符 → 注册为 URI 节点
- F17：所有模块统一 stale badge 样式（黄色圆点 + tooltip）
- F18：SSE 推送 `linkage:stale-changed` 事件，各模块订阅自动刷新

### 2.E 公式穿透 UI（F19-F23）

- F19：`GET /api/linkage/formula-usage` — 从公式找引用方
- F20：`GET /api/linkage/formulas-for` — 从文档找公式（WorkpaperSidePanel 新 Tab）
- F21：`GET /api/linkage/cell-detail` — 单元格公式详情弹窗（CellFormulaDetail.vue）
- F22：5 模块右键菜单追加"查看公式详情/来源/引用方/影响范围"
- F23：FormulaManagerDialog 增强（引用方列 + 健康度卡片 + URI 搜索 + Linkage Bus 集成）

### 2.F 运维保障（F24-F27）

- F24：用户手动校正 API（POST/GET/DELETE override + header-rule）
- F25：降级策略（_degraded 模式回退 event_handlers + 前端 503 静默）
- F26：linkage_audit_log 表记录每次传播（source_uri/affected_count/duration_ms）
- F27：`GET /api/linkage/health` 返回引擎状态

---

## 三、非功能需求

### 3.1 性能
- 依赖图内存加载 <1MB
- BFS 单次传播 <10ms（max_depth=5）
- label→物理坐标解析 Redis 缓存 TTL=24h

### 3.2 兼容性
- 保留 event_handlers.py 全部现有逻辑
- 保留 prefill_engine.py / report_engine.py 不改
- 旧端点 /v2/notify-cell-change 标 deprecated 保留 30 天

### 3.3 可扩展性
- 新模块接入 3 步（定义 URI + 添加数据源 + 添加 mark_stale 分支）
- 用户自定义联动规则（前端配置 → 即时生效）
- 插件化公式类型（注册 resolver + 添加边提取逻辑）

---

## 四、验收标准

| # | 验收项 | 量化指标 |
|---|--------|---------|
| 1 | 调整分录改 → 底稿+报表+附注全部 stale | 3 模块同时标记 |
| 2 | 底稿保存 → 下游底稿+报表+附注 stale | BFS ≤ 3 层 |
| 3 | 公式管理改 → 引用该公式的报表行 stale | 反向索引命中 |
| 4 | 附注改 → 引用该附注的底稿 stale | 反向边 |
| 5 | 前端任何模块看到 stale badge | SSE ≤ 2s 延迟 |
| 6 | 109 个 docx 底稿纳入联动 | 占位符注册率 ≥ 90% |
| 7 | 统一 URI 格式覆盖全部 6 模块 | WP/REPORT/NOTE/ADJ/TB/FORMULA 0 遗漏 |
| 8 | 用户自定义联动规则可用 | 前端配置 → 即时生效 |
| 9 | 科目映射改 → 全链路 stale | TB+报表+底稿+附注同时标记 |
| 10 | 公式穿透三向可达 | 全局→具体 / 具体→公式 / 单元格→详情 全通 |
| 11 | 单元格右键"查看公式详情"可用 | 5 模块全部接入 |
| 12 | 降级模式不阻断核心流程 | 引擎 503 时保存/编辑正常 |
