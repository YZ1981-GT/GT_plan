# 架构改进建议汇总

> 2026-06-22 初版，按模块分节，后续持续补充。

---

## 复盘：交叉主题与优先级（2026-06-22）

全文 10 个模块 60+ 条建议。复盘后提炼出 **6 条贯穿性主题** + **分级行动清单**。单条建议详见对应章节，这里给"为什么这些问题反复出现"和"先做什么"。

### 交叉主题（根因比单点更重要）

1. **写入路径碎片化 —— 缺统一"保存后处理编排层"**
   底稿有 4 条写入路径（§2.2/§2.17/§5.14），各自实现乐观锁（4 种字段 §2.17）、事件发布（其中 §5.7 还发到孤立总线）、stale 标记、审计。合并模块 commit 所有权也不一（§10.1）。**根因同一**：没有 `WorkpaperSaveOrchestrator` 统一后处理。修这一个抽象能一次性收敛 §2.2/§2.17/§5.7/§5.8/§5.14。

2. **缓存正确性 + 规模化双重欠债**
   正确性 bug：§9.1（报表缓存 key 缺 year，串年度）。规模悬崖：§3.7（wp 域每存即失效全量重建）、§3.12（无 single-flight 踩踏）、§4.4（formula 缓存 scan 全库）、§6.4（dict 无后端缓存）。缓存是这套系统最薄弱的横切面。

3. **多 worker / 分布式就绪度不足**
   §7.1（导入并发控制全进程内内存态）、§3.7/§3.12（per-process 缓存）、§5.8（进程内事件总线）。**6000 并发目标与"大量进程内状态"矛盾**——当前实现隐含"单 worker"假设。规模化前必须盘清哪些状态要外置到 PG/Redis。

4. **授权/安全集中在 custom_query**
   §5.12（execute IDOR）、§5.13（cell-writeback 跨项目写 + 零授权）、§5.1（SQL f-string）、§4.1（公式黑名单校验）。高级查询模块是攻击面最集中处。

5. **单一真源缺失 —— 同一事实多处定义**
   公式正则 3 处（§9.2）、枚举字典前端两份（§6.2）+ 前后端手动同步（§6.1）、componentType 白名单双份（§2.15）、列映射读写各一份（§5.2）、build_preparation_info 两份（§2.9）、_has_grid_cells 三份（§2.5）。

6. **静默降级掩盖错误（审计场景高危）**
   §4.8（未知函数/除零→0）、§3.4（build_entries 吞异常返空）、§2.4（rollback 散弹）。审计系统里"静默的 0 / 空列表"比报错更危险。

### 分级行动清单

| 级别 | 条目 | 理由 |
|------|------|------|
| **P0 立即（正确性/安全）** | §5.12 IDOR、§5.13 跨项目写+越权、§9.1 报表缓存串年度 | 已核实的数据泄露/污染/串数 bug |
| **P1 规模化前必修** | §7.1 多 worker 并发、§3.7 wp 缓存悬崖、§3.12 缓存踩踏 | 6000 并发目标的硬阻断 |
| **P2 低风险高收益即时** | §4.6 加 lru_cache、§5.7+§5.8 收口事件总线、§6.2 删重复枚举、§2.5/§2.9 去重 | 改动小、收益明确、无架构风险 |
| **P3 架构治理（渐进，需 spec）** | §2.2 SaveOrchestrator、§1.4 services 子包化、§1.1 god 文件拆分、§1.6 命名统一、§2.13 统一 stale graph | 跨多模块，需 spec 三件套 |

> 建议顺序：先 P0（独立小修，当周可完成）→ P2（顺手清理）→ P1（规模化专项，需压测验证）→ P3（长期重构，逐模块推进）。

### 本次分析的边界（诚实声明）

- **已实测核实**：§5.12/§5.13（读完整调用链）、§9.1（读缓存 key 构造）、§4.6（确认无 lru_cache）、§5.7（确认无订阅者）、§11.1（确认 dotted-path 加载）、§17.1（确认权限矩阵存在但未接入）。
- **基于代码结构推断、未压测**：§3.7/§3.12/§7.1/§18.1 的性能/内存悬崖结论是静态推断，**需实际压测/内存监控确认量级**再投入。
- **已覆盖模块**：一~十九（全局/底稿/地址库/公式/高级查询/枚举/账表导入/附注/报表/合并/QC/EQCR/审计报告/归档/独立性/工时/权限矩阵/OCR/AI-LLM）。
- **仍未深入**：知识库/向量检索、通知/SSE、数据管理生命周期、模板库治理、看板/仪表盘、PBC/函证 后端深层。
- 部分"建议"是方向性的，落地前需 spec 三件套细化（>500 行/3+ 组件/跨前后端 触发铁律）。

### 模块覆盖地图（截至 2026-06-22）

| # | 模块 | 状态 | 🔴 数 |
|---|------|------|-------|
| 一 | 全局架构 | ✅ 已分析 | 0 |
| 二 | 底稿 | ✅ 已分析 | 1（2.17） |
| 三 | 地址坐标库 | ✅ 已分析 | 2（3.7/3.12） |
| 四 | 公式管理 | ✅ 已分析 | 1（4.6） |
| 五 | 高级查询 | ✅ 已分析 | 3（5.7/5.12/5.13） |
| 六 | 枚举字典 | ✅ 已分析 | 1（6.2） |
| 七 | 账表导入 | ✅ 已分析 | 1（7.1） |
| 八 | 附注 | ✅ 已分析 | 0 |
| 九 | 报表 | ✅ 已分析 | 1（9.1） |
| 十 | 合并报表 | ✅ 已分析 | 0 |
| 十一 | QC 质控 | ✅ 已分析 | 1（11.1） |
| 十二 | EQCR | ✅ 已分析 | 0 |
| 十三 | 审计报告 A17 | ✅ 已分析 | 0 |
| 十四 | 归档 | ✅ 已分析 | 0 |
| 十五 | 独立性 | ✅ 已分析 | 0 |
| 十六 | 工时 | ✅ 已分析 | 0 |
| 十七 | 权限矩阵 | ✅ 已分析 | 1（17.1） |
| 十八 | OCR | ✅ 已分析 | 1（18.1） |
| 十九 | AI/LLM | ✅ 已分析 | 0 |
| — | 知识库/向量、通知/SSE、数据生命周期、模板库治理、看板、PBC | ⬜ 未深入 | — |

### 全部 🔴 清单（13 条，按 P 级）

| P 级 | 条目 | 一句话 | 核实状态 |
|------|------|--------|---------|
| **P0** | §5.12 | custom-query/execute 无项目授权（IDOR） | 已核实 |
| **P0** | §5.13 | cell-writeback 零授权 + 跨项目写（wp_code 无 project 过滤） | 已核实 |
| **P0** | §9.1 | 报表 Redis 缓存 key 缺 year → 跨年度串数 | 已核实 |
| **P0** | §11.1 | QC python 规则 dotted-path 加载，"沙箱"仅超时 | 已核实 |
| **P0/P3** | §17.1 | 权限矩阵已存在但未强制接入（5.12/5.13 的根因） | 已核实 |
| **P1** | §7.1 | 导入并发控制全进程内内存态，多 worker 失效 | 推断（需压测） |
| **P1** | §3.7 | wp 域缓存每存即失效 + 全项目重建悬崖 | 推断（需压测） |
| **P1** | §3.12 | 缓存无 single-flight，踩踏 | 推断（需压测） |
| **P1** | §18.1 | OCR 引擎 per-process ~500MB×worker | 推断（需测内存） |
| **P2** | §4.6 | parse_to_ast 声称可缓存实际无 lru_cache | 已核实 |
| **P2** | §5.7 | 写回事件发到无人订阅的孤立 EventBus | 已核实 |
| **P2** | §6.2 | 函证枚举两份前端定义已漂移 | 已核实 |
| **P2/P3** | §2.17 | 四条写入路径乐观锁字段各异，互不感知 | 已核实 |

> 一周可落地的独立小修：P0 的 §5.12/§5.13/§9.1/§11.1 + P2 的 §4.6/§5.7/§6.2（均改动小、已核实、无架构风险）。

### 新增系统性发现（QC~AI 轮）

- **§17.1 授权基建未强制接入**：权限矩阵（`permission_matrix_service`）单一真源已存在，但 §5.12/§5.13 等端点绕过它 → §5.12/§5.13 不是孤立 bug，而是"授权未系统性强制"的症状。建议 CI/lint 强制敏感端点声明 operation code。
- **§11.1 QC python 规则受限 RCE 面**：dotted-path 加载任意类，"沙箱"仅超时。需前缀白名单 + admin 限制。
- **§18.1 OCR per-process 内存 ×N**：多 worker 下 PaddleOCR ~500MB×N，建议 OCR 独立服务化。
- **静态 JSON 资源无热重载是反复出现的模式**（§3.2/§13.1/§15.1/§19.1）：override/prompt/questions/rules/config 散落各处各自缓存。建议沉淀一个统一的「mtime 热重载 JSON 资源加载器」基础设施复用。

---

## 一、全局架构层

### 1.1 God Service 巨型文件（>1500行）

| 文件 | 行数 | 符号数 | 风险 |
|------|------|--------|------|
| smart_import_engine.py | 3145 | — | 导入全流程单文件 |
| consistency_gate.py | 2359 | — | 门禁规则全堆一起 |
| report_engine.py | 2004 | — | 报表生成引擎 |
| event_handlers.py | 1929 | 64 | **132 个依赖符号**，最大耦合点 |
| disclosure_engine.py | 1929 | 65 | 附注披露引擎 |
| formula_engine.py | 1651 | 109 | 公式引擎 |

**建议**：
- `event_handlers.py` 按事件域拆分（import_handlers / workpaper_handlers / report_handlers / note_handlers）
- `smart_import_engine.py` 拆为 pipeline stages（detect → validate → transform → write）
- `formula_engine.py` 按公式类型拆子模块（TB / SUM_TB / REF / CROSS）

### 1.2 前端巨型 Vue 组件

| 组件 | 行数 |
|------|------|
| LedgerPenetration.vue | 3977 |
| TrialBalance.vue | 2945 |
| DisclosureEditor.vue | 2370 |
| FormulaManagerDialog.vue | 1942 |
| ConsolidationIndex.vue | 1766 |

**建议**：拆为 composable（逻辑） + 子组件（UI） + 常量文件，目标单 .vue ≤ 800 行。

### 1.3 EventBus 影响面（132 符号 / 50+ 文件）

- 引入事件 schema 注册表（TypedEventPayload 联合体），编译期约束契约
- 按 domain 分组：import_events / workpaper_events / report_events
- 各域有独立 handler 注册入口

### 1.4 services/ 扁平结构已到极限（622 文件）

按业务域建子包：
```
services/
  notes/           # note_*.py（50+ 文件）
  workpaper/       # wp_*.py（60+ 文件）
  consol/          # consol_*.py（20+ 文件）
  export/          # export_*.py + *_exporter.py
  stale/           # 所有 stale 传播
  gate/            # gate_*.py
  qc/              # qc_*.py
  eqcr/            # eqcr_*.py
```

### 1.5 Router 过度碎片化（270+ 文件）

- 循环计算 router（wp_f2_* / wp_g_* / wp_h_* ... wp_n_*）合并为 `cycle_computation_router.py`（用 tags 分组）
- 单一 endpoint router 合并到最近 domain router

### 1.6 命名不一致

| 现状 | 问题 | 建议 |
|------|------|------|
| note_stale_service / stale_propagation_engine / report_stale_service | 同一概念三种命名 | stale/ 子目录统一 |
| feature_flag_service / feature_flags | 职责重叠 | 合并 |
| workpaper_summary_service / workpaper_summaries_service | 单复数混用 | 统一 |
| cache_manager / cache_service | 边界模糊 | 明确层次 |

### 1.7 前端 commonApi.ts（1537 行）

拆为 domain API 模块（已有 ledgerImportApi.ts 作为模板）。

### 1.8 潜在性能问题

- `RoleContextService.get_project_role` 3 次顺序 DB 查询 → 加 per-request / Redis TTL 缓存
- event_handlers 工厂模式每次 session + flush 幂等检查 → 事件风暴时压 DB

---

## 二、底稿模块（Workpaper）

### 2.1 `_get_render_config_impl` 巨型函数（700+ 行）

当前一个函数做了 7 步：查 wp → 查 classification → scope/redirect → 公共数据 → per-sheet dispatch。

**建议**：拆为 pipeline step 对象：
```python
steps = [
    ResolveWorkpaperStep,       # wp + wp_index + project check
    ResolveClassificationsStep, # classifications + package aggregation
    CheckRedirectStep,          # scope/redirect 判断
    PrepareContextStep,         # cross_ref + year + template
    DispatchSheetsStep,         # per-sheet componentType + render
]
```

### 2.2 底稿保存 3 条路径，后处理逻辑重复

| 入口 | 场景 |
|------|------|
| `wp_html_save.save_html_data` | HTML 类组件 |
| `wp_editor_router.save_univer_data` | Univer 网格编辑 |
| `onlyoffice_callback_service.put_file` | OnlyOffice 回调 |

三条路径各自实现版本冲突检测、审计日志、事件发布、prefill_stale 标记。

**建议**：抽取 `WorkpaperSaveOrchestrator`：
```python
class WorkpaperSaveOrchestrator:
    async def after_save(self, db, wp, user, trigger: str, extra: dict):
        """统一后处理：版本递增 + stale 标记 + 审计日志 + 事件发布"""
```
各入口只负责"数据写入"，后处理调同一函数。

### 2.3 RENDERER_DISPATCH 只覆盖 10/43 种 componentType

后端策略：b-index / a-program-console(×4) / audit-sheet / checklist-table / analytical-review / c-note-table / univer

缺失的 33 种类型（d-form-* / confirmation-* / bad-debt-sheet / cf-verification 等）走 `schema_data = None` 直返旧数据。

**建议**：
- 短期：d-form-* 和 confirmation-* 补 RENDERER_DISPATCH 策略（至少 grid_fallback）
- 长期：定位 RENDERER_DISPATCH 为"可选的服务端预取优化"，前端组件 mount 时自行取数据

### 2.4 事务 rollback 防御散弹

render 策略中大量 `try: await db.rollback() except: pass`，甚至需要 `SELECT 1` 探测事务存活。

**根因**：策略函数和主函数共用 session，某步失败污染整个 session。

**建议**：
- 方案 A（推荐）：render 策略内用 SAVEPOINT（`async with db.begin_nested():`）
- 方案 B：容易出错的取数放到独立只读 session

### 2.5 `_has_grid_cells` 重复定义 3 处

`_univer_grid.py` 和 `_c_note.py` 各有一份完全相同的函数。

**建议**：提取到 `_utils.py` 共享。

### 2.6 wp_code_overrides.json 550+ 条映射维护负担

815 个 wp_code 中 550+ 需要 override，新增底稿必须手动添加。

**建议**：
- 强化 class_code 派生算法精度，让 override 只保留"例外"（目标收敛到 50-100 条）
- 当前大量 override 是因为 classify_sheet 不够精确的补偿

### 2.7 前端 GtWpRenderer 多职责

同时负责 tab 管理 + componentType 分发 + onlyoffice/整本 Excel 判断。

**建议**：拆为：
- `WpSheetTabs.vue` — tab 切换/图标/排序
- `WpComponentRenderer.vue` — componentType → 子组件实例化

### 2.8 底稿模板文件管理缺少统一抽象

模板路径解析散布在：`_resolve_template_path`（wp_render_config）、`wp_template_finder.py`、`wp_template_registry.py`。

**建议**：统一为 `TemplateLocator` 接口：
```python
class TemplateLocator:
    def locate(self, wp_code: str, version: str | None = None) -> Path | None: ...
```

### 2.9 `build_preparation_info` 重复实现

`wp_preparation_info_service.py:23` 和 `wp_render_config.py:355` 各有一份 `build_preparation_info` / `_build_preparation_info`。

**建议**：统一调用 service 层的，router 层删除私有副本。

### 2.10 WpIndex JOIN 查询散布 30+ 处

由于 `WorkingPaper` 表无 `wp_code` 列（在 `WpIndex` 表），几乎每个需要 wp_code 的查询都要写一遍 `JOIN WpIndex`。分布在 30+ 个 service 文件中。

**建议**：
- 方案 A：在 WorkingPaper 模型上加 `@hybrid_property wp_code`（lazy JOIN / subquery），让调用方透明访问
- 方案 B：提供 `WorkpaperQuery` 工具类封装常用的 wp+wp_index JOIN 查询（`by_id`, `by_wp_code`, `by_project`）
- 方案 C（推荐）：创建 DB VIEW `workpaper_with_code` 物化 JOIN，底层用 PG materialized view + 索引

### 2.11 auto_data_resolvers 缺少超时保护

35+ 个 resolver 函数执行不受时间限制。如果某个 resolver 执行慢 SQL（如 `_completion` resolver 对全项目 COUNT），render_config 整体等待。

**建议**：
- 给 `resolve_auto_data_source` 加 `asyncio.wait_for(timeout=3.0)` 保护
- 超时返回 `{"summary": "⏱ 取数超时", "_timeout": True}`，前端显示加载中图标

### 2.12 离线导出/导入 round-trip 缺少自动化验证

`WpOfflineExportService` 和 `WpOfflineImportService` 支持 xlsx 离线编辑场景，但搜索发现 **没有 round-trip 属性测试**（export → edit → import → diff = 0）。

**建议**：添加 PBT 验证「export → import（不修改）→ cell diff = 0」的等价性属性。

### 2.13 StalePropagationEngine 基于静态 JSON 依赖图

`unified_dependency_graph.json` 是编译时生成的静态文件。如果用户新建了自定义底稿/公式引用关系，stale 传播无法覆盖。

**建议**：
- 短期：保持静态图 + 在 `wp_formula_dependency.py` 的 `DependencyGraph` 运行时动态补充
- 长期：合并静态图 + 动态图为统一的运行时 stale graph

### 2.14 render_config API 响应体积可能很大

多 sheet 底稿（如 D2 有 14 sheet）每个 sheet 都返回完整 html_data（含 cells dict），导致 render_config 响应可能达到 MB 级别。

**建议**：
- 支持 `?sheet_name=xxx` 按需加载单 sheet（已有 sheet_name 参数，确认前端是否利用了）
- 或采用分层加载：首次返回 sheet 列表 + 元数据，前端切 tab 时按需请求单 sheet 数据

### 2.15 前端 componentType 白名单双重维护

`useEditorMode.ts` 中有 `HTML_COMPONENT_TYPES` Set 和 `htmlRendererRegistry.ts` 中有 `HTML_COMPONENT_TYPE_SET`。两者需要保持同步。

**建议**：`useEditorMode` 直接引用 `htmlRendererRegistry` 的 Set，消除双重维护。registry 已经是单一真源，composable 不应再维护独立副本。

### 2.16 底稿测试覆盖评估

| 区域 | 测试情况 |
|------|---------|
| wp_classification_service + derive_component_type | ✅ 多循环测试引用，但**无独立的 PBT** |
| wp_render_config（端到端） | ✅ smoke test + checklist/analytical_review 集成测试 |
| wp_html_save | ✅ cross_ref 传播测试 |
| wp_editor_router.save_univer_data | ❌ **无直接测试**（仅通过 e2e 间接覆盖） |
| RENDERER_DISPATCH 策略函数 | ⚠️ 仅 checklist + analytical_review 有集成测试 |
| wp_offline_export/import round-trip | ❌ 无 PBT |
| StalePropagationEngine.on_change | ⚠️ 仅通过 mock 在 H/I 循环回填测试中验证 |

**建议优先补充**：
1. `save_univer_data` 路径的集成测试（版本冲突 + 事件发布）
2. `derive_component_type` 的 PBT（随机 class_code → 结果 ∈ VALID_COMPONENT_TYPES ∪ raise）
3. render 策略的 contract test（每种 componentType → 返回结构符合前端接口）

### 2.17 🔴 四条写入路径乐观锁字段各不相同

底稿数据有 4 条写入路径，各自用**不同的乐观锁字段**做并发冲突检测：

| 路径 | 冲突检测字段 | 冲突响应 |
|------|------------|---------|
| `wp_html_save.save_html_data` | `schema_version` + `parsed_data._version`(data_version) | 409 |
| `wp_editor_router.save_univer_data` | `file_version`(expected_version) | 409 VERSION_CONFLICT |
| `onlyoffice_callback_service.put_file` | OnlyOffice doc_key 内部机制 | docserver 侧 |
| `custom_query.snapshot_writer` | `updated_at` vs `X-File-Opened-At` | 409 WritebackConflict |

同一份 `working_paper` 的并发保护用了 4 套不同的"版本号"语义（schema_version / file_version / _version / updated_at）。两条路径并发写同一底稿时，**各自的乐观锁互不感知**——A 走 html_save 改了 file_version 不变，B 走 univer_save 检查 file_version 通过，可能互相覆盖。

**建议**：统一乐观锁字段（推荐 `file_version` 单调递增 + `updated_at`），所有写入路径共用同一冲突检测函数（并入 §2.2 的 `WorkpaperSaveOrchestrator`）。

### 2.18 三套锁服务无统一协调层

`editing_lock_service`（资源级编辑锁）、`wp_cell_lock_service`（单元格锁）、`wp_sheet_lock_service`（sheet 锁）三套独立锁机制。一个底稿可能同时被资源锁 + sheet 锁 + cell 锁约束，但三者无统一仲裁——获取 cell 锁时不检查是否已有他人持 sheet/资源锁，可能出现"持 cell 锁但整表被他人资源锁"的矛盾态。

**建议**：建立锁层级协调（资源锁 > sheet 锁 > cell 锁），获取细粒度锁前校验粗粒度锁不冲突；或文档明确三者适用边界互斥不叠加。

---

## 三、地址坐标名称库模块（Address Registry）

### 模块现状

存在**两套并行的地址注册表系统**，命名相似但定位不同：

| 系统 | 文件 | 数据来源 | 用途 |
|------|------|---------|------|
| V1（运行时动态） | `address_registry.py`（60 符号 / 1183 行）+ `routers/address_registry.py` | DB 实时构建（report/note/wp/tb/aux 5 域） | 公式编辑选址、悬空引用校验、跳转路由 |
| V2（静态预生成） | `routers/address_registry_v2.py` | 4 个静态 JSON（L2 语义锚点 / resolved refs / L3 依赖 / CWR） | stale 影响分析、语义→坐标解析 |

核心能力：URI 格式 `{domain}://{source}/{path}#{cell}` ↔ 公式语法（`TB()`/`NOTE()`/`WP()`...）双向转换。

### 3.1 V1/V2 双系统职责边界模糊

两个 router（`/api/address-registry` 和 v2）都提供 `resolve` / `stats` 端点，但数据来源完全不同（DB vs JSON）。前端调用方需要清楚知道何时用哪个，否则数据不一致。

**建议**：
- 文档化两者边界（已有 `@see` 注释，但不够）
- 长期：V2 的静态 JSON 作为 V1 的"预计算缓存层"，V1 作为统一入口按需回退到 DB 构建，对外只暴露一套 API

### 3.2 V2 模块级全局缓存无失效机制

`address_registry_v2._load()` 用 4 个模块级全局变量 `_L2_CACHE/_RESOLVED_CACHE/_DEPS_CACHE/_CWR_CACHE` 缓存 JSON，**首次加载后永不失效**（无 mtime 检查）。JSON 更新后必须重启进程。

**建议**：对齐 `wp_code_override_loader` 的 mtime 热重载模式，或至少提供 `/invalidate` 端点。

### 3.3 URI 解析正则与公式正则分散维护

`_URI_PATTERN`、`_FORMULA_PATTERNS`（9 个函数正则）、`cross_sheet_resolver._CROSS_SHEET_REF_PATTERN`、`address_registry.py` 内的 `_CELL_ADDRESS_RE` 等正则散布多处，且 domain 白名单（report/note/wp/tb/aux）硬编码在正则里。

**建议**：
- 集中 domain 枚举为单一 `AddressDomain` enum，正则从 enum 动态生成
- URI ↔ formula 转换是核心契约，应有 round-trip PBT（`uri_to_formula_ref(formula_ref_to_uri(x)) == x`）

### 3.4 `build_*_entries` 系列异常吞噬

`build_report_entries` / `build_note_entries` 都用 `except Exception: logger.error; return []` 兜底。如果某个数据源构建失败，**静默返回空列表**——前端公式编辑器选址列表会缺失该域地址，但用户无感知。

**建议**：返回结构区分"无数据"和"构建失败"，前端对失败态显示警告。

### 3.5 jump_route 字符串拼接易错

`build_jump_route` 用字符串拼接生成前端路由（`?year=...&tab=...&highlight=...`）。query 参数顺序/转义靠手写，前端路由变更时易脱节。

**建议**：路由生成移到前端（后端只返回结构化 `{domain, source, path, cell}`，前端 router 统一构造 URL），消除前后端路由格式耦合。

### 3.6 search 关键词过滤是 Python 全量线性扫描

`AddressRegistryService.search` 在 domain 为空时 `get_all`（加载 report+note+wp+tb+aux 全部 5 域条目），再在 Python 内对每个 entry 的 `label/uri/formula_ref/account_code/row_code` 做 5 次 `substring.lower()` 匹配。一个中大型项目地址条目可达数千~上万条，公式编辑器每次输入关键词都触发一次全量线性扫描。

**建议**：
- 关键词搜索下沉：domain 为空时仍按需限定（前端先选域再搜）
- 或对 entries 建轻量倒排索引（按 label/account_code 分词），缓存在 slot 内
- search 已有 `limit` 但**静默截断**（见 3.8）

### 3.7 🔴 wp 域缓存在每次底稿保存后失效 + 重建成本 O(全项目单元格)

`WORKPAPER_SAVED` / `wp_parsed_data_service` / `wp_structure` 都触发 `invalidate_async(pid, domain='wp')`。而 wp 域重建 `_build_custom_wp_cell_entries` 会**查询项目内所有 working_paper 的 parsed_data，逐底稿 `extract_custom_cells` 提取所有单元格**。

后果：高频编辑场景（目标 6000 并发）下，每次保存使 wp 域缓存变冷，下一次公式编辑器/选址请求触发一次 O(项目全部底稿 × 全部单元格) 的重建 + 全量 JSONB 反序列化。这是明显的**性能悬崖**。

**建议**：
- 增量失效：只重建被改动 wp_id 的条目（slot 内按 wp_id 分桶），而非整域失效
- 或 wp 域改为"按 wp_code 懒加载"——validate/resolve 单个 `WP('D2-1','B5')` 时只查该 wp 的 parsed_data，不预构建全项目
- 静态来源（wp_account_mapping.json / wp_fine_rules）与动态来源（DB 单元格）分槽缓存，静态部分不随保存失效

### 3.8 validate_formula_refs 为校验一个引用加载整域全部条目

校验单条公式时，对每个涉及域 `_get_domain` 取**全部条目**构建 `uri_set`，再判断公式中的 URI 是否 ∈ 集合。校验一个 `WP('D2-1','B5')` 却要加载全项目所有底稿单元格地址。

**建议**：改为**定点存在性检查**——`exists(domain, uri)` 直接查该 URI 对应的最小数据（如 WP 只查目标 wp_code 的该 cell 是否存在），避免全域物化。

### 3.9 search 的 limit 静默截断无分页信号

`return results[:limit]`（默认 100）。超出部分被丢弃，前端无法知道"还有更多"，用户搜索的引用若排在 100 名后将找不到。

**建议**：返回 `{items, total, has_more}`，前端显示"仅显示前 100 条，请细化关键词"。

### 3.10 AddressEntry.value 用 float（与金额 Decimal 铁律冲突）

`AddressEntry.value: Optional[float]`。虽当前 `build_*_entries` 未填充 value（留 None），但字段类型为 float，未来若缓存金额会丢精度，与 memory 铁律「报表金额用 Decimal」冲突。

**建议**：改 `Optional[Decimal]` 或 `Optional[str]`（序列化安全）。

### 3.11 wp 域三数据源一致性风险

wp 域条目来自 3 个来源：`wp_account_mapping.json`（静态）+ `wp_fine_rules/*.json`（静态 cross_references）+ DB 自定义单元格（动态）。静态 JSON 的 wp 映射可能与项目实际底稿不一致（如底稿已删但 JSON 仍有条目），导致选址列表出现"幽灵地址"。

**建议**：静态 JSON 条目在返回前与项目实际 wp_index 求交集过滤，剔除项目中不存在的 wp_code。

### 3.12 🔴 缓存击穿无 single-flight 保护（缓存踩踏）

`_get_domain` 的 L1/L2 双级缓存命中很好，但**缓存未命中时无单飞（single-flight）保护**。结合 §3.7（wp 域每次保存即失效），在 6000 并发目标下会出现典型的**缓存踩踏（cache stampede）**：某项目 wp 域缓存刚失效，N 个并发请求同时 miss → 同时触发 `build_workpaper_entries`（全项目底稿全单元格扫描 + 全 JSONB 反序列化），DB 与 CPU 被 N 倍放大。

**建议**：
- 为 `_get_domain` 加 per-(slot_key) 的 `asyncio.Lock` 单飞，同一 slot 并发 miss 只构建一次，其余 await 复用结果
- 配合 §3.7 的增量失效，从根上降低重建频率

---

## 四、公式管理模块（Formula Management）

### 模块现状

公式能力分散在多个文件，已有明确的 L1 内核收口努力：

| 文件 | 行数/符号 | 角色 |
|------|----------|------|
| `formula_engine.py` | 1651 / 109 | **L1 内核**，`_REGISTRY`(FunctionRegistry) 单一真源，`execute`/`evaluate_formula` |
| `formula_parse_utils.py` | 40 符号 | tokenize/parse AST + **已废弃** `FormulaEvaluator`（委托 L1） |
| `report_engine.py:ReportFormulaParser` | — | 报表专用 TB/SUM_TB/ROW resolver（实现 AmountResolver Protocol） |
| `wp_formula_service.py` | 168 行 | 自定义底稿公式 CRUD（DB 持久化 + 悬空引用校验） |
| `wp_formula_dependency.py` | — | 底稿间公式依赖图 `DependencyGraph` |
| `note_formula_engine.py` / `note_formula_generator.py` / `note_formula_dependency_service.py` | — | 附注专用公式 |
| `cell_formula_evaluator.py` / `wp_formula_eval_service.py` / `wp_formula_linkage_service.py` | — | cell 级 / 底稿级求值 |

### 4.1 自定义表达式安全校验用黑名单（脆弱）

`_validate_custom_expression` 用黑名单拦截危险关键字：
```python
dangerous = ['import ', 'exec(', 'eval(', '__', 'open(', 'os.', 'sys.', 'subprocess']
```
黑名单天然不全——如 `getattr`、`globals()`、`compile`、`\x` 编码绕过、`lambda` 等都未拦截。虽然后续 `ast.parse(mode="eval")` 限制为表达式，但黑名单给人虚假安全感。

**建议**：
- 改用 **AST 白名单**：解析后遍历节点，只允许 `BinOp/UnaryOp/Num/Call(限定函数名)/Name(限定标识符)`，遇到 `Attribute/Subscript/Lambda/Comprehension` 等一律拒绝
- 这是安全校验铁律（memory: 安全校验永远不砍），值得做扎实

### 4.2 废弃代码仍在仓库（FormulaEvaluator + parse_utils.evaluate_formula）

`formula_parse_utils.py` 的 `FormulaEvaluator` 和 `evaluate_formula` 已标 `DeprecationWarning`，但仍保留约 200 行实现 + `_eval_node` 本地求值逻辑（与 L1 内核并存）。

**风险**：两套求值逻辑可能行为漂移；新人误用废弃 API。

**建议**：确认无生产调用后（仅测试引用），删除废弃实现，测试改为直接测 L1 内核。codegraph 已确认 `FormulaEvaluator` 主要被测试引用。

### 4.3 多个 `evaluate_formula` 同名函数

至少 3 处 `evaluate_formula`：`formula_engine`（L1 权威）、`formula_parse_utils`（废弃）、`report_engine`（报表）。同名易混淆 import。

**建议**：废弃的删除后，报表的重命名为 `evaluate_report_formula` 或作为 `ReportFormulaParser.execute` 的内部方法，避免裸模块级同名函数。

### 4.4 公式缓存失效粒度粗

`FormulaEngine.invalidate_cache` 用 `redis.scan_iter(match="formula:*:{project_id}:*")` 模式删除。`scan_iter` + 批量 delete 在大 key 空间下有性能开销，且 `formula:*`（无 project_id 时）会扫全库。

**建议**：
- 维护 project → formula keys 的索引集合（Redis Set），失效时直接取集合删除，避免 scan
- 或用 Redis key 的 TTL 自然过期 + 版本号（project 级 version bump 使旧缓存逻辑失效）

### 4.5 公式依赖图与 stale 引擎未统一

`wp_formula_dependency.DependencyGraph`（底稿间公式依赖）和 `StalePropagationEngine`（静态 JSON 依赖图）是两套依赖图。公式新增/修改时，stale 传播能否感知存疑（见 §2.13）。

**建议**：公式 save 时（`wp_formula_service.save`）同步更新运行时依赖图，喂给统一的 stale 传播。

### 4.6 🔴 parse_to_ast 声称可缓存但实际未缓存

`formula_engine.py` 顶部 `from functools import lru_cache`，且 `parse_to_ast` docstring 写「解析结果可缓存（同公式不重复解析）」，但**全文件无任何 `@lru_cache` 应用**——每次 `execute` 都重新 `_tokenize` + 递归下降 parse。

报表生成场景对成百上千行公式求值，很多公式结构重复（同一模板不同行），重复 parse 是纯浪费 CPU。

**建议**：对 `parse_to_ast` 加 `@lru_cache(maxsize=2048)`（formula 字符串可哈希，AST 不可变可安全共享）。这是低风险高收益的即时优化。

### 4.7 AST 求值无递归深度保护（自定义公式 DoS 隐患）

`_eval_ast` 纯递归，无深度上限。用户自定义公式（`wp_formula_service` 允许用户写表达式）若构造深度嵌套（如 `((((...))))` 或长链 `A+A+A+...`），可触发 Python `RecursionError`，被通用 `except Exception` 兜成 "AST 求值失败"。虽不崩溃，但属于可被滥用的资源消耗点。

**建议**：parser 阶段限制嵌套深度 / token 数上限（如 ≤ 200 tokens、嵌套 ≤ 32 层），超限直接 `FormulaParseError`，在 save 校验时拒绝。

### 4.8 未注册函数 / 除零静默返回 0（掩盖错误）

- `_eval_func_node`：未知函数名（如把 `TB` 误写成 `TBB`）→ trace 记 "unknown" + 返回 `Decimal("0")`，**不进 errors**。
- `_eval_ast` 除法：`right != 0 else Decimal("0")`——除零静默返回 0。

后果：用户公式写错函数名或除零，结果显示 0 而非报错，审计场景下"0"是个危险的正确外观。

**建议**：
- 未注册函数 → `result.errors.append`（save 校验时即拒绝）
- 除零 → `result.warnings.append("除零，按 0 处理")`，trace 标注，前端可提示

### 4.9 regex 降级路径仍全量保留（~150 行并行实现）

`_execute_regex` 是与 AST 路径并存的完整求值实现，注释称"保留一个版本周期作降级"。AST 已是生产默认且经 parallel diff 验证。两套求值逻辑长期并存 = 行为漂移风险 + 维护负担（如 SUM_TB 的 prefix 匹配语义两路径需手动对齐）。

**建议**：确认 AST 路径稳定后，移除 regex 路径 + `_PARSE_MODE` 开关，单测改为只验 AST。

### 4.10 `note_formula_engine` 命名误导（实为勾稽校验非求值）

`note_formula_engine.py` 名为 "formula engine"，但实际是**附注勾稽校验引擎**（8 类校验：余额核对/横向勾稽/纵向勾稽/交叉校验/其中项/账龄衔接/完整性/LLM 审核），与 `formula_engine.py`（取数求值 L1 内核）职责完全不同。同含 "formula_engine" 易误导开发者以为是同类求值器。

**建议**：重命名为 `note_reconciliation_engine` / `note_check_engine`，与取数求值的 `formula_engine` 区分。同理审视 `note_formula_generator`（生成附注公式）/`note_formula_dependency_service`（附注公式依赖）的命名归类，明确"取数求值"与"勾稽校验"两类不同语义。

---

## 五、高级查询模块（Custom Query / 跨模块单元格查询）

### 模块现状

`services/custom_query/` 子包，实现"把各模块数据虚拟化为 Excel 网格 + cell 级跨模块查询 + 双向写回"：

| 文件 | 角色 |
|------|------|
| `module_cell_resolver.py` | source URI 路由器，5 模块（report/note/adj/tb/workpaper）虚拟 sheet 列映射 + `_query_*_cells` |
| `cross_sheet_resolver.py` | BFS 遍历 `=Sheet!Cell` 引用链（max 3 层，环检测） |
| `snapshot_writer.py` | cell 级写回 parsed_data JSONB，乐观锁冲突检测 |
| `metrics.py` | 查询指标 |

### 5.1 `snapshot_writer` 动态列名拼进 SQL（whitelisted 但有隐患）

adj/tb 模块写回用 f-string 拼列名：
```python
text(f"UPDATE adjustments SET {col_name} = :new_val ...")
```
`col_name` 来自硬编码白名单 `_ADJ_COLUMNS[col_idx]`（有 `if not col_name: raise` 保护），目前**安全**。但 f-string 拼 SQL 列名是危险模式，未来若白名单来源变化易引入注入。

**建议**：
- 加显式断言 `assert col_name in _ADJ_COLUMNS_SET`（双保险）
- 或用 SQLAlchemy Core `update().values(**{col_name: val})` 替代裸 SQL，让 ORM 处理标识符转义

### 5.2 虚拟 sheet 列映射硬编码且分散

每个 `_query_*_cells` 的 A/B/C/D... 列映射写在 docstring + 代码两处（如 report: A=row_code, B=row_name...）。`snapshot_writer` 又各维护一份 `_REPORT_COLUMNS`/`_NOTE_COLUMNS`/`_ADJ_COLUMNS`。**读路径和写路径的列映射各一份，易脱节**。

**建议**：抽取单一 `MODULE_COLUMN_SCHEMA` 配置（module → 列序 → 字段名），读写共用，新增列只改一处。

### 5.3 cross_sheet_resolver 与 cell 提取耦合

`cross_sheet_resolver` 的 BFS 算法依赖 `extract_cell(wp_id, sheet, cell)` 从 snapshot 取值，但 resolver 本身不持有 DB。引用链解析与数据提取边界需清晰。

**建议**：将 `extract_cell` 定义为注入的 Protocol，resolver 只负责 BFS 图遍历逻辑，便于单测（mock extract）。

### 5.4 写回 xlsx 缓存同步是 best-effort

`snapshot_writer` 写回 JSONB 后用 `run_in_executor + openpyxl` 同步 xlsx 缓存。若 xlsx 写失败，JSONB 已 commit，**两者不一致**（下次从 xlsx 读会拿旧值）。

**建议**：
- 明确 JSONB 为权威源（已是设计），xlsx 仅为导出缓存，读路径永远优先 JSONB
- xlsx 同步失败时标记 `xlsx_cache_stale=True`，导出前按需重建

### 5.5 source URI 格式有两种风格

`module_cell_resolver` 用 `report:balance_sheet|C5:C10`（冒号+竖线），而 `address_registry` 用 `report://BS/BS-002#期末`（双斜杠+井号）。两套 URI 语法并存增加认知负担。

**建议**：长期统一为一种 URI 语法，或文档明确两者适用范围（address_registry=公式引用语义地址；custom_query=虚拟网格物理坐标）。

### 5.6 round-trip 契约已有意识但需补 PBT

`format_source_uri` 注释声明 "round-trip property: format(parse(uri)) == uri"，但需确认有对应 PBT。

**建议**：补 `parse_source_uri` ↔ `format_source_uri` 的 round-trip 属性测试（含 workpaper 三段式 + 边界）。

### 5.7 🔴 写回事件发到孤立的本地 EventBus（跨引用/SSE/stale 不触发）

`snapshot_writer` 双向写回 cell 后，第 7 步 `emit("cross-ref:updated", ...)` 用的是 **`custom_query/metrics.py` 里自定义的本地 `_EventBus`**，而非主系统 `app.services.event_bus.EventBus`。经 codegraph 确认：**没有任何代码 `.on("cross-ref:updated")` 订阅该本地总线**——这个 emit 实际是空操作。

后果：通过高级查询双向写回修改单元格时，虽然写了 JSONB + `prefill_stale=True`，但**不会**：
- 发布 `WORKPAPER_SAVED` 到主事件总线
- 触发下游 stale 传播 / cross_ref 更新检测
- SSE 推送给其他正在编辑的用户

即这是第 4 条底稿写入路径（见 §2.2），且与前 3 条行为不一致——下游联动静默失联。

**建议**：
- 删除 `custom_query.metrics._EventBus`，写回后改用主 `event_bus.publish(EventPayload(WORKPAPER_SAVED, ...))`，复用 §2.2 建议的 `WorkpaperSaveOrchestrator` 统一后处理
- 这是与"联动是核心价值"铁律直接冲突的 bug，建议优先修

### 5.8 系统中存在两个 EventBus 实现

承上：`app.services.event_bus.EventBus`（主，进程内事件总线 + SSE + Redis stream）和 `custom_query.metrics._EventBus`（本地玩具实现）。两个同名概念易混淆，且本地的那个是孤立的。

**建议**：移除本地 `_EventBus`，全局只保留一个事件总线。

### 5.9 `_query_*_cells` 全量取数后 Python 切片（over-fetch）

即使查询单个 cell（如 `report:bs|C5:C5`），`_query_report_cells` 仍从 DB 拉取该模块**全部数据行**构建虚拟 sheet，再在 `_extract_cells_from_virtual_sheet` 内按 range 切片（已有 `MAX_CELLS=500` / `INTEGER_COL_LIMIT=100` 保护输出）。报表行数有限影响小，但 tb/adj 明细行多时是明显 over-fetch。

**建议**：cell_range 的行区间下推到 SQL（`LIMIT/OFFSET` 或 `WHERE row BETWEEN`），避免全表物化。

### 5.10 虚拟 sheet 金额值保留为 float

`_extract_cells_from_virtual_sheet` 对 `isinstance(value, (int, float))` 的金额「keep numeric」原样返回 float。与 memory 金额 Decimal 铁律冲突，跨模块取的报表/TB 金额经 float 可能丢精度。

**建议**：金额列统一转 `str(Decimal)` 或在序列化层用 Decimal，前端按字符串解析金额。

### 5.11 cross_sheet_resolver 的 extract_cell 与 BFS 耦合，难单测

`cross_sheet_resolver` BFS 遍历依赖 `extract_cell(wp_id, sheet, cell)` 取值，提取逻辑与图遍历混在一起。

**建议**：`extract_cell` 抽为注入的 Protocol，resolver 只做 BFS + 环检测 + 截断，提取由调用方注入，便于 mock 单测引用链算法。

### 5.12 🔴 execute_query 缺项目级授权（已核实 IDOR）

**已核实完整调用链**（`custom_query.py` L972~L1110）：`execute_query` 仅 `Depends(get_current_user)`，从 L988 起直接用 `body.project_id`（变量 `pid`）分发到 14 个 `_query_*`，全程**无任何 `project_id ∈ 用户可见项目` 校验**。`current_user` 仅用于①缓存 key②审计日志。

结论：**确认 IDOR**——任意已登录用户传他人 `project_id` 即可读取该项目报表/试算表/附注/调整/底稿/工时数据。`deps.py` 已有 `get_visible_project_ids`（L350）可用但未接入。

**建议**（安全铁律，最高优先）：`execute_query` + `batch-execute` 入口加 `pid ∈ get_visible_project_ids(current_user)` 否则 403。

### 5.13 🔴 cell-writeback 越权 + 跨项目写入（已核实，比预估更严重）

**已核实完整调用链**：
1. 非 workpaper 模块：仅全局角色白名单 `user_role not in (admin/manager/partner/senior/assistant)`（几乎放行所有角色），无项目成员校验。
2. **workpaper 模块：完全无授权检查**——router 的角色检查包在 `if body.module != "workpaper"` 分支内，workpaper 直接跳过；`snapshot_writer._write_workpaper_cell` 收到 `user` 参数但**从不校验权限**，只做乐观锁。
3. **🔴 跨项目写入 bug**：router 用 `SELECT id FROM working_paper WHERE wp_code = :code LIMIT 1` 定位底稿——**无 project_id 过滤、无 ORDER BY**。多项目共享同一 wp_code（如各项目都有 D2-1）时，写回命中**任意项目**的同码底稿，造成跨项目数据污染。

**建议**（最高优先）：
- workpaper 写回 lookup 必须带 `project_id`（请求体须含 project_id 并参与 WHERE）
- `_write_workpaper_cell` 加项目成员 + 编辑权限校验（复用 `require_project_access("edit")`）
- 所有模块统一项目级授权，不用全局角色兜底

### 5.14 cell-writeback 与主保存路径重复造轮子

`cell-writeback` 是第 4 条底稿写入路径（见 §2.2/§2.17），自己实现了乐观锁（updated_at vs X-File-Opened-At）、xlsx 同步、事件（孤立总线 §5.7）、审计日志，与其他 3 条路径逻辑重复但行为不一致。

**建议**：与 §2.2 `WorkpaperSaveOrchestrator` 合并，写回只负责定位 cell + 设值，后处理（版本/事件/stale/审计）走统一编排。

---

## 六、全局枚举字典模块（Enum Dict）

### 模块现状

枚举字典采用「代码默认值 + DB 覆盖」双层：
- 后端 `system_dicts.py` 的 `_DICTS`（硬编码 9+ 类：wp_status/adjustment_status/... + confirmation_dicts 11 类）
- `enum_dict_overrides` 表（V015）：仅允许覆盖 `label`/`color`，`value` 由代码锁定
- `GET /dicts` 合并返回，前端启动时拉一次缓存到 sessionStorage

### 6.1 前端 dictLabels 与后端 _DICTS 手动同步

`EnumDictManager.vue` 内 `dictLabels`（字典中文名映射）注释明写「与后端 _DICTS 同步维护」——**手动同步**。后端新增字典类型，前端忘改就显示英文 key。

**建议**：字典的中文名（dict_key label）也由后端 `/dicts` 返回（如 `{dict_key, dict_label, items}`），前端不再维护副本。

### 6.2 🔴 函证枚举有两份前端定义且已漂移

存在两个文件定义函证字典 key，且**都导出同名 `ConfirmationDictKey` 类型**：
- `confirmationDicts.ts`：`CONFIRMATION_DICTS`（11 类，较新统一版）
- `confirmationEnums.ts`：`CONFIRMATION_DICT_KEYS`（6 类，旧版，含 `MATCH_STATUS: 'confirmation_match'`，但新版无此键；新版有 `DIFF_TYPE/STATUS/REPLY_RELIABILITY` 等旧版没有）

两份内容已不一致，同名类型易 import 错文件导致 key 拼写不一致。

**建议**：合并为一份（保留 `confirmationDicts.ts` 11 类版），删除 `confirmationEnums.ts`，全部引用收口到统一文件。

### 6.3 枚举 value 不可运行时新增（设计限制）

`value` 由代码 `_DICTS` 锁定，DB 只能覆盖 label/color；新增枚举值（如新增一种"回函方式"）需改源码 + 重启，前端拿到 405 `ENUM_DICT_HARDCODED`。对 6000 用户的业务系统，运营想加一个状态值就得发版，灵活性不足。

**建议**：评估是否将"可运营扩展"的字典（如回函方式/差异类型）改为 DB 完全可增删，"系统语义强绑定"的字典（如状态机 status）保持代码锁定。两类分治。

### 6.4 GET /dicts 全表扫 overrides + 无缓存层

`get_system_dicts` 每次 `sa.select(EnumDictOverride)` 全表加载所有覆盖项再在 Python 合并。表虽小，但每个用户会话启动都打一次；无后端缓存（仅靠前端 sessionStorage）。

**建议**：后端加进程级缓存（overrides 变更时失效，类似 wp_code_override mtime 模式），或合并结果缓存到 Redis 短 TTL。

---

## 七、账表导入模块（Ledger Import）

### 模块现状

DB 驱动的导入作业（`import_jobs` 表为权威源）+ 3 级识别（sheet 名/表头/内容并行加权）+ 适配器注册表（用友/金蝶/SAP/通用，JSON 热重载）+ smart_import_engine 写四表。架构成熟，识别层（identifier）+ 适配器（AdapterRegistry）设计良好。

### 7.1 🔴 并发控制为进程内内存态，多 worker 失效

`import_queue_service` 的 `_import_locks`（项目锁）、`_acquire_mutex`（asyncio.Lock）、`_MAX_CONCURRENT_IMPORTS=3`（全局并发上限）均为**模块级内存变量**，注释明示"单 worker 内有效"。`import_job_runner` 的 `_cancel_events`/`_running_tasks`/`_stop_event` 为**类级内存字典**。

后果：6000 并发目标通常需多 uvicorn worker / 多实例部署，此时：
- "同项目同时只允许一个导入"无法跨进程保证 → 同项目并发导入可能双写
- 全局并发 ≤ 3 失效 → 实际并发 = 3 × worker 数
- `request_cancel` 信号无法跨进程送达 → 取消请求落到非执行进程时静默失败

注：`import_jobs` 表 + JobStatus 提供作业状态的跨进程持久化，但**并发闸门和取消信号是进程本地的**。

**建议**：
- 项目级互斥改用 PG advisory lock（`pg_advisory_xact_lock`）或 Redis 分布式锁
- 全局并发上限用 DB 计数（`SELECT count(*) WHERE status='running'`）或 Redis 信号量
- 取消信号经 DB 标志位（`import_jobs.cancel_requested`）+ 执行进程轮询，而非内存 Event

### 7.2 smart_import_engine 巨型文件（3145 行）

见 §1.1。账表导入的核心写四表逻辑全集中于此，建议拆 pipeline stages（detect→validate→transform→write_four_tables）。

---

## 八、附注模块（Disclosure Notes）

### 模块现状

附注是服务数量最多的域（50+ `note_*` 服务 + `disclosure_engine`）。`note_fill_engine` 4 种取数模式（合计/明细/分类/变动）清晰；勾稽校验走 `note_formula_engine`（见 §4.10 命名问题）。

### 8.1 disclosure_engine 巨型文件（1929 行 / 65 符号）

见 §1.1。附注披露引擎职责过重，建议按披露类型（货币资金/应收/存货...）或按阶段（取数/勾稽/渲染/导出）拆分。

### 8.2 note_* 服务命名爆炸（50+ 文件）

`note_fill_engine` / `note_formula_engine` / `note_formula_generator` / `note_formula_dependency_service` / `note_auto_pull_service` / `note_source_resolvers` / `note_wp_data_resolver` ... 50+ 个 note_ 前缀服务，职责边界模糊（多个"取数"服务、多个"公式"服务）。

**建议**：建 `services/notes/` 子包并按职责二级分组（`notes/fill/`、`notes/formula/`、`notes/resolve/`、`notes/export/`），配合 §1.4 整体子包化。

### 8.3 附注取数链路与底稿/报表强耦合

`note_fill_engine` 4 模式都从底稿审定表 / TB / report 取数，附注 stale 依赖 §2.13 的 stale 传播。附注是数据链路最下游（report→notes），上游任一环 stale 未正确传播都会导致附注陈旧。

**建议**：纳入 §2.13 统一 stale graph，确保 report→notes 边可靠传播。

---

## 九、报表模块（Report）

### 模块现状

`report_engine`（2004 行）公式驱动：`report_config` 逐行执行 TB()/SUM_TB()/ROW()/PREV() 生成四表 + 增量更新 + 平衡校验 + 穿透 + Redis 缓存。`ReportFormulaParser` 求值委托 L1 内核（见 §4）。

### 9.1 🔴 报表 Redis 缓存 key 缺 year（多年度碰撞）

`_cache_key(project_id, report_type)` = `f"report:{project_id}:{report_type}"`——**不含 year**。但 `get_report_cached(project_id, year, report_type)` 入参有 year，却未进入 key。

后果：审计平台支持多年度共存（memory: multi_year_coexist），同项目同 report_type 的 2024 与 2025 报表**共用同一缓存 key**，先缓存的年度数据会被另一年度命中返回——**跨年度串数据**，10 分钟 TTL 内持续错误。

**建议**（优先，正确性 bug）：`_cache_key` 加入 year → `f"report:{project_id}:{year}:{report_type}"`，同步修正 `_invalidate_report_cache`。

### 9.2 公式 token 正则三处重复定义

TB/SUM_TB/ROW/REPORT/NOTE/WP/PREV/AUX 的正则在至少 3 处各定义一份：`report_engine.py`（`_TB_PATTERN`...）、`formula_engine.py`（`_TOKEN_PATTERNS`）、`address_registry.py`（`_FORMULA_PATTERNS`）。函数签名变更需三处同步，易漂移。

**建议**：抽取单一 `formula_grammar.py` 集中所有函数名 + 正则 + 参数元数（arity），三方 import 复用。

### 9.3 report_engine god 文件（2004 行）

见 §1.1。建议拆 ReportFormulaParser（求值）/ ReportGenerator（生成编排）/ ReportBalanceChecker（平衡校验）/ ReportCache（缓存）。

---

## 十、合并报表模块（Consolidation）

### 模块现状

30+ `consol_*` 服务。`consol_cascade_refresh_service` 是设计良好的统一编排者：DAG 自底向上（tree→worksheet→trial→reconcile→report→notes）+ 失败隔离（关键步中断/下游步续跑）+ 幂等。

### 10.1 级联刷新混合事务所有权（违 flush-only 铁律）

`consol_cascade_refresh_service` 编排中：`recalc_full` **内部自行 commit**，而 `recalculate_trial` 只 flush（由编排者统一 commit）。同一条 DAG 链路里 commit 所有权不一致，违背"service 只 flush 不 commit"铁律。

后果：若 trial 之后的 report/notes 步失败，trial 已 commit 落库 → **部分成功的中间态**（虽设计上接受"部分成功"，但合并数据半新半旧对审计是风险）。

**建议**：统一 commit 所有权到编排层（所有被编排 service 改为只 flush），全链路单事务，失败整体回滚；或显式分阶段事务 + 每阶段状态标记，让前端明确知道刷到哪一步。

### 10.2 consol_* 服务碎片化 + orchestrator 删除史

ADR-CONSOL-201 注释记录 `consolidation_orchestrator` 曾被删到"剩 stale pyc"后重建。30+ consol_ 服务（aggregation/auto_elimination/cascade_refresh/cross_template/disclosure/drilldown/elimination_rules/individual_sum/note_aggregation/pivot/reconciliation/refresh_job/report/scope/snapshot/tree/trial/worksheet + 多个 stale_handler）职责切得很细但缺顶层导航。

**建议**：建 `services/consol/` 子包并在 README/模块 docstring 标注 DAG 依赖图（哪些是编排者、哪些是被编排的纯算服务、哪些是 stale handler），降低"删错文件"风险。

### 10.3 多个 consol stale handler 分散注册

`consol_note_stale_handler` / `consol_trial_stale_handler` / `consol_elimination_recalc_handler` 各自 `register_*` 到主 event_bus。与全局 stale 体系（§2.13）+ 附注 stale（§8.3）共同构成多套 stale 链，缺统一视图。

**建议**：纳入 §1.3 / §2.13 的统一事件域 + stale graph 治理。

---

## 十一、QC 质控模块（Quality Control）

### 模块现状

`qc_engine`（14 条规则：5 阻断 + 8 警告 + 1 提示）+ `qc_rule_executor`（多 expression_type 分派）+ `qc_rule_definition_service`（规则 CRUD + 版本管理）+ dry-run + 案例库 + 巡检。规则可 DB 配置 + 版本化，设计灵活。

### 11.1 🔴 python 类型规则按 dotted-path 加载执行（受限 RCE 面）

`qc_rule_executor` 对 `expression_type='python'` 的规则用 `importlib.import_module` **按 dotted path 加载任意类并执行**，所谓"沙箱 timeout=10s"**只是 `asyncio.wait_for` 超时，不是真沙箱**——被加载代码对 DB/文件系统/网络无任何限制。

风险：`QcRuleDefinition` 经 `create_rule` API 创建，若 `expression`(dotted path) 可由非超管用户控制，等价于"加载并运行代码库内任意类"（虽不能注入新代码，但可触发有副作用的类）。

**建议**（安全铁律）：
- dotted path 强制前缀白名单（如必须以 `app.services.qc_rules.` 开头）
- 创建/编辑 `python` 类型规则限 admin
- 文档明确"沙箱"仅为超时，不要给安全错觉；考虑真正隔离（子进程 + 资源限制）

### 11.2 expression_type 半实现（sql/regex 抛 NotImplementedError）

`python`/`jsonpath` 已实现，`sql`/`regex` 预留抛 `NotImplementedError`。规则定义表允许存这两类，但执行即报错。

**建议**：create_rule 校验时拒绝未实现的 expression_type，避免存入"创建成功但执行必失败"的规则。

---

## 十二、EQCR 模块（项目质量控制复核）

### 模块现状

设计良好：`eqcr_service` 仅为向后兼容入口，实拆为 `eqcr_workbench_service` + `eqcr_domain_service`；`eqcr_shadow_compute_service` 提供**独立取数通道**（影子计算，不写项目组数据，对比团队结果找差异）+ Redis 日限流。职责分离清晰，无突出结构问题。

### 12.1 影子计算限流 Redis 不可用时 fail-open

`eqcr_shadow_compute_service` 限流（日 20 次）在 Redis 不可用时降级为**不限流**（log warning）。对限流器是合理的"可用性优先"取舍，但影子计算会调 `consistency_replay_engine`（重算），无限流时若 Redis 故障可能被滥用压垮后端。

**建议**：Redis 不可用时降级为**进程内内存计数兜底**（而非完全不限流），或对影子计算加并发上限。

---

## 十三、审计报告模块（A17 / KAM）

### 模块现状

`a17_llm_service`（章节/KAM 草稿 LLM 生成，RAG 检索同行业知识库，embedding 404 降级 ilike）+ `a17_summary_service` + `a17_word_exporter` + 版本选择器。**生成结果为"建议稿"，用户编辑后采纳，不自动写入**——符合审计留痕要求，好设计。

### 13.1 prompt 模板 import 时加载（改 prompt 需重启）

`_CHAPTER_SYSTEM = _load_prompt(...)` 等在模块 import 时一次性读取 4 个 prompt 文件。调整 prompt 文案需重启进程。与 §3.2 同类模式（静态资源无热重载）。

**建议**：prompt 改为首次使用时懒加载 + mtime 热重载，便于运营调优 prompt 不停服。

---

## 十四、归档模块（Archive）

### 模块现状

`archive_orchestrator`（gate→wp_storage→push_to_cloud→purge_local 串行 + 断点续传 + SHA-256 完整性）+ `archive_section_registry`（注册式章节生成器）+ PDF 生成器。编排 + 完整性校验设计成熟。

### 14.1 章节定义双源（硬编码 ARCHIVE_SECTIONS + registry 并存）

`archive_orchestrator` 用硬编码 `ARCHIVE_SECTIONS = ["gate","wp_storage","push_to_cloud","purge_local"]`，注释承认"Task 16 会创建 archive_section_registry，本任务先用硬编码"。但 `archive_section_registry` **已存在**（注册了 00 封面/01 签字/02 EQCR/03 质控/04 独立性/05 AI 贡献/99 日志）。两套章节定义并存：orchestrator 的流程步骤 vs registry 的归档文件章节。

**建议**：明确两者语义（orchestrator=归档动作流程；registry=归档产物章节），文档区分；若意图统一则完成迁移删除硬编码。

---

## 十五、独立性模块（Independence）

### 模块现状

`independence_service`（核心四角色 signing_partner/manager/qc/eqcr 各自提交声明 + SignatureRecord + 审计日志）+ `independence_signing_service` + 问题模板 JSON。逻辑清晰，规模小，无突出问题。

### 15.1 问题模板进程级缓存无失效

`_questions_cache` 进程级单例，`independence_questions.json` 改动需重启。同 §3.2/§13.1 模式——建议统一一个"带 mtime 热重载的 JSON 资源加载器"基础设施，所有静态 JSON 资源（override/prompt/questions/rules）复用。

---

## 十六、工时模块（Workhour）

### 模块现状

`workhour_service`（CRUD + 校验 + LLM 预填）+ approve/budget/entries/list 多 router。标准业务 CRUD，无突出结构问题。

### 16.1 router 碎片化

工时相关 router 有 `workhour_approval` / `workhour_approve` / `workhour_budget` / `workhour_entries` / `workhour_list` / `workhours` 6 个文件，命名高度重叠（approval vs approve）。

**建议**：合并为 `workhour_router.py`（用 tags/子路由分组），消除 approve/approval 歧义，纳入 §1.5 router 治理。

---

## 十七、权限矩阵模块（Permission Matrix）

### 模块现状

`permission_matrix_service` 是**纯 Python 的角色→操作映射单一真源**（OPERATION_CODES + ROLE_OPERATIONS，角色继承 admin>partner>manager>auditor）。设计本身清晰、无 DB 依赖、易测。

### 17.1 🔴 权限矩阵已存在却未被普遍应用（与 §5.12/5.13 同根）

系统**有**良好的权限判断单一真源，但 §5.12（custom-query/execute）/§5.13（cell-writeback）等端点**完全绕过它**，直接 `get_current_user` 后裸操作或用临时全局角色白名单。即"轮子已造好，部分关键端点没用"。

**建议**（系统性）：
- 审计**所有写/敏感读端点**是否经过「`permission_matrix` 操作校验 + `require_project_access` 项目成员校验」两层
- 建立 CI 检查或 lint：敏感 router 必须声明所需 operation code，缺失则告警
- §5.12/5.13 不是孤立 bug，而是"授权基建未强制接入"的系统性缺口

### 17.2 ROLE_OPERATIONS 仅系统角色，项目职责维度待确认

docstring 称"系统角色 × 项目职责 → 操作权限"，但 `ROLE_OPERATIONS` 只按系统角色映射。项目职责（scope_cycles / 项目内角色）维度是否真正参与权限判断需确认——否则"现场经理只能改自己分派循环的底稿"这类项目级约束无法表达。

**建议**：确认项目职责维度落地位置（deps 层 or matrix 层），文档化两层授权模型（系统角色能力 + 项目成员范围）。

---

## 十八、OCR 模块（Unified OCR）

### 模块现状

`unified_ocr_service` 三引擎自动选择 + 回退链（PaddleOCR 精度 / Tesseract 速度 / MinerU 兜底）+ 延迟初始化。回退设计（引擎不可用自动切换）健壮。

### 18.1 OCR 引擎 per-process 加载，多 worker 内存 ×N

引擎延迟初始化但加载后常驻进程（PaddleOCR ~500MB）。多 uvicorn worker 部署时，**每个 worker 各自加载一份**，内存占用 = 500MB × worker 数。6000 并发若开多 worker，OCR 内存可能成为部署瓶颈。

**建议**：
- OCR 抽为**独立服务/进程**（单独容器，所有 worker 共享），经 HTTP/队列调用，而非每个 web worker 内嵌引擎
- 或限制仅特定 worker 承载 OCR（worker 角色分工）

### 18.2 首请求冷启动延迟

延迟初始化使首个 OCR 请求承担 ~500MB 模型加载延迟。

**建议**：启动后台预热（lifespan 内异步预加载，类似 main.py 的 libreoffice/template 健康检查）。

---

## 十九、AI / LLM 模块

### 模块现状

`llm_client`（vLLM/OpenAI 兼容 + 熔断器 closed/open/half-open + 超时 + 降级）+ `unified_ai_service`（AIService + AIPluginService + OCR facade）+ `structured_llm_service` / `tsj_*`。熔断 + 超时 + 降级三件套齐全，韧性设计好。

### 19.1 熔断器 + config 为 per-process / import 时读取

`_CircuitBreaker` 是模块级单例（per-process，多 worker 各自计数——对熔断器**可接受**甚至更优）；`_BASE_URL/_API_KEY/_MODEL = settings.X` 在 import 时求值，改 LLM 配置需重启。

**建议**：LLM 配置改为运行时读取（`settings.LLM_BASE_URL` 每次调用读，或支持 reload），便于切换模型/端点不停服。

### 19.2 多 facade 叠加（unified_ai / ai_service / ai_plugin / llm_client）

`unified_ai_service` 包 `ai_service` + `ai_plugin_service` + `unified_ocr_service`，而 `ai_service` 内部又调 `llm_client`。facade 层级较深，新调用方易困惑该用哪一层。

**建议**：文档明确分层（`llm_client`=底层传输+熔断；`ai_service`=能力封装；`unified_ai_service`=对外门面），对外只暴露 `unified_ai_service`。

### 19.3 AI 内容须可审计（关联既有 ai_content_gate / watermark）

系统已有 `ai_content_gate` / `ai_contribution_watermark` / `ai_content_log_service`——AI 生成内容需留痕、加水印、过审。这是审计平台的合规要求，方向正确，建议确保所有 LLM 出口（含 a17/note_ai/wp_ai/doc_ai_chat）都经过 gate + watermark，不要有旁路。

---

## 附：代码规模快照（2026-06-22）

| 维度 | 数值 |
|------|------|
| Codegraph | 79k 节点 / 160k 边 / 4449 文件 |
| 后端 Services | 622 文件 / 207,642 行 |
| 后端 Routers | 270+ 文件 / 79,443 行 |
| 后端 Tests | 1068 文件 / 313,801 行 |
| 前端源码 | 729 Vue + TS / 275,898 行 |
| 总计 | ~876,784 行（不含 data/migrations） |
