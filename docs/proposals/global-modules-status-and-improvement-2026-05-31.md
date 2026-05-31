# 全局功能模块现状盘点与改进建议（2026-05-31）

> 范围：7 个全局支撑模块 = ①地址坐标名称库 ②公式管理 ③高级查询 ④枚举字典 ⑤底稿模板库 ⑥国企版/上市版报告模板库 ⑦知识库
> 方法：逐模块 readCode 实证（service + router + data + 前端 view），不信文档自述；标注代码锚点。
> 定位：这 7 个是"横切支撑层"，被各业务模块（试算表/底稿/报表/附注/合并）共享调用，质量直接决定全平台数据一致性与可维护性。

---

## 〇、执行摘要（先看结论）

| 模块 | 完成度 | 健康度 | 最大隐患（一句话） |
|------|--------|--------|-------------------|
| ①地址坐标名称库 | ~85% | 🟠 | **存在两套并行系统**（内存版 `address_registry.py` vs 文件版 `address_registry_v2.py`）+ `l1_physical.json`(33.6MB) 全仓 0 引用疑似死文件 |
| ②公式管理 | ~70% | � | **公式求值引擎至少 4 套并行**（formula_engine/report_engine/formula_parser/formula_unified，两个都自称"统一引擎"）+ 审计留痕三处分裂；第四轮复盘从 🟠 升级 🔴 |
| ③高级查询 | ~90% | 🟢 | 两套查询入口（custom_query 业务视图 + query_builder 白名单 DSL）边界清晰，安全模型是标杆，最健康 |
| ④枚举字典 | ~85% | 🟢 | **设计健康**（API 主源 useDictStore + statusEnum.ts 显式 fallback + 版本校验）；增量空间是覆盖面（仅 10 类状态枚举） |
| ⑤底稿模板库 | ~80% | 🟠 | JSON `gt_template_library.json`(8 服务消费的主源) + PG `wp_template_registry`(新 DB 叠加层带 JSON fallback)，分层兜底但真源未拍板 |
| ⑥国企/上市报告模板库 | ~75% | 🟠 | report_config 5 种 standard 映射清晰，但**项目级克隆后无回填主模板机制**，优化不沉淀 |
| ⑦知识库 | ~70% | 🟠 | **三套并行**（KnowledgeDocument DB / KnowledgeService 文件系统 / KnowledgeIndexService PG向量RAG）；已有向量检索但只覆盖业务数据、用 PG+numpy 非已部署的 ChromaDB |

> **二次复盘修正（2026-05-31）**：初稿对 ④枚举字典 与 ⑤底稿模板库 的"双真相源"判断**过重**，二次 readCode 实证后下调严重度（详见 §十一 复盘修正）。④实为健康的"API 主源 + 常量 fallback"设计（初稿误称前端 `statusMaps.ts` 硬编码，实测该文件不存在，真实是 `constants/statusEnum.ts` 作 dictStore 降级兜底）；⑤实为"JSON 主源 + DB 叠加层"分层兜底（非对称双写）。

**最重磅横切发现**：多数模块存在"**新旧双轨/双源并存**"的腐化模式 —— 重构到一半（DB 化、统一化）但旧路径未删，形成"双真相源"。**二次复盘修正**：真正构成风险的是 ①地址库（两套并行系统）/ ②公式审计（三处分裂）/ ⑥报告模板（无回填）/ ⑦知识库（双轨）4 处；④枚举字典 与 ⑤底稿模板库 经实证是"主源 + 兜底"的合理分层（非对称双写），严重度下调。这仍是比单个功能缺失更需关注的系统性结构问题。

**合伙人视角投资判断**：这些是天天在用的核心支撑层（不像合并模块卡真实数据），改进 ROI 高。建议优先 P0 消除"双真相源"（地址库统一 / 模板库单源 / 知识库收口），再做 P1 功能增强。

---

## 一、地址坐标名称库（Address Registry）

### 现状（代码实证）

**存在两套并行实现**：

**A. 内存动态版** `backend/app/services/address_registry.py`（673 行，全局单例 `address_registry`）
- 地址格式 `{domain}://{source}/{path}#{cell}`，5 域：report/note/wp/tb/aux
- 运行时从 DB（report_config/trial_balance）+ JSON（note_template/wp_account_mapping）**动态构建** AddressEntry
- 缓存维度 `project_id × year × template_type × domain`，按域 TTL（tb 60s / report 300s）+ LRU 500 槽上限
- 公式引用语法 ↔ URI 双向互转（TB/SUM_TB/ROW/REPORT/NOTE/WP/AUX/PREV）
- 跳转路由生成 + 公式引用有效性校验（`validate_formula_refs`）
- 事件驱动失效：`event_handlers.py` 订阅 ADJUSTMENT_CREATED/LEDGER_DATASET_ACTIVATED → 按域 invalidate

**B. 文件静态版（V2）** `backend/app/routers/address_registry_v2.py` + 4 个巨型 JSON
- `address_registry_l1_physical.json` **33.6 MB** / `l2_semantic.json` 19.7 MB / `l3_dependencies.json` 9.9 MB（42163 边）/ `resolved_refs.json` 90 KB
- 三级模型：L1 物理坐标 / L2 语义锚点 / L3 跨 sheet 依赖
- 提供语义→物理解析、stale 影响 BFS、依赖查询
- 被 `linkage_graph_builder.py` 消费构建统一依赖图

### 🟠 问题

1. **双系统职责重叠、概念割裂**：内存版的 `wp://` 域 与 V2 的 L1/L2/L3 都在描述"底稿单元格地址"，但数据来源、缓存策略、API 路径完全独立，开发者不知道该用哪个。
2. **33 MB 静态 JSON 进 git**：L1 物理表 33.6MB，是仓库最大单文件之一；模块级 `_L2_CACHE` 全量常驻内存（19.7MB），多 worker 下内存放大。
3. **L1 物理文件 grep 0 加载**：`address_registry_l1_physical.json`（33MB）在 backend 代码中**0 处 import**（只有 docs 提及），疑似死数据。
4. **无 DB 持久化**：内存版重启即丢全部缓存，冷启动首个请求要全量重建（report+tb+note+wp 四域扫描）。

### 改进建议

- **P0 统一为单一地址服务**：明确 L1/L2/L3（设计期静态分析产物）vs 内存版（运行时动态）的边界 —— 建议 V2 三级文件**仅用于 linkage_graph 离线构建**，运行时一律走内存版 `address_registry`；在两个文件头部互相 `@see` 标注职责，避免误用。
- **P0 核实并清理 33MB 死文件**：grep 确认 `address_registry_l1_physical.json` 无运行时加载 → 若仅构建期用，移出 git tracked（生成物）或 gzip 压缩（同 `.hypothesis` 处理）。
- **P2 内存版加 Redis 二级缓存**：AddressEntry 按 `project:year:domain` 缓存到 Redis（TTL 对齐现有），冷启动/多 worker 共享，避免每 worker 各自重建。（与 §九 路线图 P2-9 一致归 P2 体验性能批次，不在本轮 6 spec P0+P1 范围）
- **P2 地址有效性校验接入公式管理保存流**：`validate_formula_refs` 已实现但需确认公式编辑保存时强制调用（防止存入悬空引用）。

---

## 二、公式管理（Formula Management）

> ⚠️ **第四轮复盘重大修正**：初稿称"统一公式引擎 formula_unified.py"**严重失实**。实证发现公式求值引擎**至少 4 套并行**，加上 note/依赖/反向索引共 **8 个 formula 相关 service**，是本盘点**最严重的隐性双源/多源问题**（初稿低估，健康度应从 🟠 调为 🔴）。

### 现状（代码实证，多引擎并行）

**至少 4 套独立的公式求值器（各有自己的 AST/eval）**：
| # | 文件 | 自述 | 求值实现 | 调用方 |
|---|------|------|---------|--------|
| 1 | `formula_engine.py` | 文件头自称"**统一公式引擎 — 唯一执行器**" | ast + 插件式函数注册 + FormulaResult | `/formula` router / report_config / trial_balance / prefill / event_handlers / wp_user_formulas |
| 2 | `report_engine.py` | Phase 1 报表主引擎 | `_safe_eval_expr`(ast) + ReportFormulaParser + `evaluate_formula` | reports / consol（ADR-CONSOL-101 已统一单体/合并到此） |
| 3 | `formula_parser.py` | AST 求值器 | tokenize + `FormulaEvaluator.evaluate` + `evaluate_formula` | report_config |
| 4 | `formula_unified.py` | "统一"公式解析 | `parse_formula` + `_safe_eval` | formula_to_display 预览 |

**另有 4 个 formula 周边 service**：`report_formula_service.py`(ReportFormulaService 填充) / `note_formula_engine.py`(附注，调 llm) / `note_formula_generator.py`(附注公式生成) / `formula_reverse_index.py` + `wp_formula_dependency.py`(依赖图)。

**前端**：`FormulaManagerDialog.vue` —— 报表/试算表/附注三处弹窗 + ThreeColumnLayout 全局入口。
**审计留痕**：`formula_audit_log` 表 + `core.Log` + 哈希链（三处，见下）。

### � 问题（修正后升级严重度）

1. **公式求值引擎至少 4 套并行**（**最严重，初稿漏报**）：`formula_engine` / `report_engine` / `formula_parser` / `formula_unified` 各有独立 AST 求值器 + 各自的 `evaluate_formula`/`_safe_eval*`。**两个文件都自称"统一引擎"**（formula_engine 文件头 + formula_unified 文件名），实际谁都没统一。同一 `TB()/SUM_TB()/ROW()` DSL 在 4 处各解析一遍，函数支持集（ABS/IF/ROUND/MAX/MIN/PREV/AUX）是否一致**无保证** —— 这正是 ADR-CONSOL-101 在合并侧踩过的"语义漂移"硬伤的全局版。
2. **审计留痕三处分裂**：`formula_audit_log` 表（懒建）+ `core.Log`(formula_updated) + 哈希链 `audit_log_entries`，口径/防篡改级别不一，查询要并三处。
3. **`formula_audit_log` 懒建表反模式**：`ensure_table` 每请求 `CREATE TABLE IF NOT EXISTS`，绕开 D6，drift detector 盲区。
4. **公式管理覆盖维度不全**：合并工作底稿 / 底稿单元格公式未纳入 FormulaManagerScope（见 consol proposal）。
5. **无公式版本对比/回滚 UI**：留痕记了 old/new 但前端不能用。

### 改进建议（修正后）

- **P0 公式求值引擎收敛盘点（新增，~2 天先调研）**：grep 4 套引擎的实际调用方 + diff 各自支持的函数集/DSL token，产出"哪套是真主引擎、其余该委托还是删除"的 ADR。**先做调研再动手**（4 套引擎调用面广，贸然合并风险高）—— 类比 ADR-CONSOL-101 合并侧已验证"复用 report_engine"路径，全局是否都向 report_engine（或 formula_engine）收敛需评审。这是公式管理真正的 P0，比审计留痕更根本。
- **P0 公式审计留痕收口哈希链**：废 `formula_audit_log` 懒建表 + `core.Log` formula_updated → 统一 `append_audit_log` 新增 `formula_changed` schema；查询视图走 action_type 过滤（前端 API 不变）。
- **P1 公式管理覆盖合并 + 底稿**：FormulaManagerScope 补合并报表/附注/底稿数据源节点。
- **P2 公式变更时间线 UI**：FormulaManagerDialog 加"历史"Tab + 一键回滚（复用时光机）。

---

## 三、高级查询（Advanced Query）

### 现状（代码实证）—— 相对最健康

**两套入口，边界清晰**：
- **业务视图查询** `routers/custom_query.py`（2300+ 行）：跨模块 cell 级查询（report:/note:/adj:/tb: URI）+ 模板保存（`CustomQueryTemplate` 表，scope=global/personal）+ 批量执行 + cell 回写（`snapshot_writer.py` 10 步事务）+ 跨 sheet 溯源
- **白名单 DSL 构建器** `routers/query_builder.py`（仅 admin/manager）：`TABLE_WHITELIST`（16 张只读 audit/财务表，显式排除 user/role/auth/token）+ `JOIN_WHITELIST`（以 projects 为中心）+ `OPERATOR_WHITELIST`，可视化条件 + SQL 预览 + Excel 导出
**前端**：`CustomQuery.vue`（独立页 /custom-query）+ `AdvancedQueryBuilder.vue`（S-3 构建器）+ `CustomQueryTab.vue`（模板库内嵌）；Dashboard 有"高级查询"快捷入口。

### 🟢 / 🟠 问题

1. **安全设计扎实**（优点）：白名单表 + 显式排除敏感表 + JOIN 登记制 + 算子白名单，SQL 注入面小，是 7 模块中安全性最好的。
2. **审计节流**：custom_query.execute 走 `audit_logger.log_action`（节流）—— 合理（查询高频），但 cell 回写/跨 sheet 溯源**不节流每次必记**（敏感操作），设计正确。
3. 🟠 **两套入口用户认知成本**：custom_query（业务视图）vs query_builder（白名单 DSL）功能有重叠（都能跨表查 + 导出 Excel），前端用 el-tabs「业务视图 + 高级构建器」分层（memory 已记），但仍需确认权限边界提示清晰。
4. 🟠 **cell 回写的 xlsx cache 同步**：`snapshot_writer` 第 7 步 `run_in_executor + openpyxl write` 回写 xlsx —— 大文件下可能阻塞，需确认有超时/降级。

### 改进建议

- **P2 入口合并提示**：在前端明确「业务视图（所有人）」vs「高级构建器（admin/manager）」的能力差异说明，避免用户困惑。
- **P2 查询结果缓存**：高频相同查询（如 dashboard 卡片）加 Redis 短 TTL 缓存，减 DB 压力（6000 并发目标）。
- **P3 query_builder 导出大结果集分页/流式**：避免一次性 openpyxl 全量构建大 Excel 内存峰值。
- **保持**：白名单安全模型是标杆，新增表/JOIN 必须走显式登记（已是铁律），不要为"方便"放开。

---

## 四、枚举字典（Enum Dictionary）

### 现状（代码实证）

**设计（DT-3 方案 B，干净）**：`routers/system_dicts.py`
- 代码默认值 `_DICTS`（10 类硬编码：wp_status/wp_review_status/adjustment_status/report_status/template_status/project_status/issue_status/pdf_task_status/workhour_status）
- DB 覆盖层 `enum_dict_overrides` 表（dict_key+value 主键，仅 label/color 可改，value 不可改）
- `GET /api/system/dicts` 合并代码默认 + DB override（override 非 NULL 覆盖）
- 写操作权限：仅 admin 改展示属性（label/color）；**枚举 value 本身硬编码不可增删**（D13 ADR，写 value 返 405 `ENUM_DICT_HARDCODED`）
- 引用计数 `usage-count`（Sprint 6 Task 6.2）+ reset 恢复默认
- **前端 API 主源 + 显式 fallback**（实证）：`stores/dict.ts` `useDictStore.load()` 启动调 `/api/system/dicts` + sessionStorage 缓存(CACHE_VERSION + 24h TTL) + `dictVersionCheck.ts` 版本校验失效；`constants/statusEnum.ts` 的 `STATUS_DICT` 是**文档化的降级兜底**（"dictStore 加载失败时可作为 fallback"），有 statusEnum.test.ts 守护中文 label + 合法 color
- 前端 `EnumDictManager.vue`（SystemSettings Tab）+ `EnumDictTab.vue`（模板库内嵌）

### 🟢 健康 / 🟠 增量空间

1. **双层设计合理**（优点）：value 硬编码（防业务逻辑断裂）+ label/color 可治理（满足展示定制），是正确取舍 —— 枚举 value 改了会断 service 分支判断，锁死 value 是对的。
2. **前端 API 主源设计正确**（优点，二次复盘修正）：`useDictStore` 运行时从 API 拉取为主源，`statusEnum.ts` 仅作加载失败兜底 + 有单测守护 —— **非"双维护漂移"**（初稿误判，且 `_DICTS` docstring 里"与前端 statusMaps.ts 保持一致"是陈旧注释，该文件实测已不存在/改名为 statusEnum.ts）。
3. 🟠 **覆盖面有限**（真正的增量空间）：仅 10 类状态枚举进字典；大量业务枚举（审计循环代号 A~N、抵销类型 EliminationEntryType、复核状态 ReviewStatusEnum 等）仍散在各 model `enum.Enum`，前端硬编码中文，未纳入字典治理。
4. 🟠 **enum_dict_overrides 降级静默**：表不存在时 `except` 降级为只返代码默认（合理），但本地 DB 漂移下 override 永远不生效用户无感知；且该表疑似靠 create_all 未入 D6。

### 改进建议

- **P1 修正 `_DICTS` 陈旧注释 + 明确单一真源**：把 docstring 的 "statusMaps.ts" 改为 "statusEnum.ts（fallback）"；明确 API 为运行时主源、statusEnum.ts 仅兜底，避免后人误以为要双维护。可选：写脚本从 `_DICTS` 生成 statusEnum.ts 的 STATUS_DICT 兜底块，保证兜底与主源不漂移。
- **P2 扩展字典覆盖到核心业务枚举**：把 EliminationEntryType / 审计循环代号 / 风险等级等高频展示枚举纳入 `_DICTS`（value 仍锁死，仅 label/color 可治理）。
- **P3 enum_dict_overrides 入 D6 迁移 + drift 守护**：确保 override 表三层一致。

---

## 五、底稿模板库（Workpaper Template Library）

### 现状（代码实证）

**分层兜底（主源是 JSON，DB 是新叠加层）**：
- **JSON 主源** `data/gt_template_library.json`（163KB，363 条 templates）—— **实测被 ~8 个服务消费为主索引**：`gt_coding_service` / `procedure_service`（降级层 2）/ `template_engine`（降级）/ `wp_template.generate_from_codes` / `wp_standard_conversion_service`（与 generate_from_codes 同源）+ 2 个 seed 脚本（init_template_library / init_wp_templates_to_knowledge）+ scan 脚本生成它
- **PG 表叠加层** `wp_template_registry`（`services/wp_template_registry.py`，advanced-query-enhancements-p1p2 Req4 引入）：wp_code/wp_name/cycle/account_codes/sheets/applicable_standard/version/source_origin；`load_tree` 读取 + `increment_version` 触发前端缓存失效 + **`table_exists` 降级判断**（表不存在/空时退回 JSON 或视全部为通用）
- 配套：`wp_account_mapping.json`（58KB，206 条 v2025-R5 科目映射）+ `workpaper_template_analysis.json`（349 模板/2602 sheet 扫描）+ `wp_template_metadata_*_seed.json`
- 前端 `TemplateLibraryMgmt.vue`（6 Tab：底稿模板/公式管理/审计报告模板/附注模板/编码体系/报表配置）+ `WpTemplateTab.vue` + `WpTemplateDetail.vue`

### 🟠 问题

1. **JSON 主源 vs DB 叠加层真源未拍板**（二次复盘修正：非对称"双写"，而是分层兜底）：`gt_template_library.json` 是 ~8 服务实际消费的主索引（文件路径/生成/科目映射），`wp_template_registry` 表是后加的"分类/版本/适用准则"叠加层并带 JSON 降级。两者**职责有交叠但非镜像**，问题是"真源未明确拍板" + registry 表数据如何与 JSON 同步无机制（scan 脚本只生成 JSON，不写表）。
2. **生成链路断点（已知）**：memory 记 `generate_from_codes` 创建 WorkingPaper 但从未设 parsed_data（NULL）→ HTML 渲染器"有记录无内容"（wp-generation-pipeline spec 待实施）。
3. **模板文件四级兜底**（memory）：知识库 → 原始 file_path → openpyxl 最小工作簿 → 空字节 —— 兜底链长说明模板文件管理不集中。
4. **applicable_standard 在 registry 是 list**（["soe"]/["listed"]/[] 通用），底稿层准则切换靠它（multi-standard-unification 已用）—— 但与项目级 `Project.applicable_standard_v2` 口径需对齐。

### 改进建议

- **P1 明确 registry（元数据真源）vs JSON（生成物/种子）边界**：registry 表作为"底稿模板清单 + 版本 + 适用准则"唯一真源；JSON 仅作种子导入 + 模板文件路径索引；在 service 头部标注，避免双写。
- **P1 接通生成链路**（依赖 wp-generation-pipeline spec）：`generate_from_codes` 后调 `populate_parsed_data` 填 html_data，消除"有记录无内容"。
- **P2 模板文件统一入知识库**：底稿 xlsx 模板统一存知识库「底稿模板库」分类（已有预制分类），消除四级兜底中的"原始 file_path"散落。
- **P2 registry version 联动前端缓存已实现**（X-Indicators-Schema-Version），保持。

---

## 六、国企版/上市版报告模板库（Report Template Library）

### 现状（代码实证）

**报表配置** `services/report_config_service.py` + `data/report_config_seed.json`（420KB）
- 5 种 `applicable_standard`：`soe_consolidated` / `soe_standalone` / `listed_consolidated` / `listed_standalone` / `enterprise`（降级兜底）
- `resolve_applicable_standard`：从 `Project.template_type`(soe/listed) + `report_scope`(consolidated/standalone) 组合
- `load_seed_data`（按 report_type+row_code+standard 判重幂等）+ `clone_report_config`（克隆为项目级 `project:{pid}` 可自定义）+ `update_config`（含 formula 审计留痚）
- `report_engine` 按 standard 生成四表 + coverage_stats + debug

**附注模板（国企/上市）** `data/note_template_soe.json`（540KB）+ `note_template_listed.json`（919KB）+ `note_soe_listed_diff.json`（65KB，106 共有/60 SOE 独有/71 Listed 独有/33 格式差异）+ `consol_note_sections_{soe,listed}.json`
- `disclosure_engine._load_templates` 按 template_type 加载 soe/listed JSON
- `note_conversion_service` 国企↔上市转换（D14，multi-standard-unification 已接通底稿层切换）

### 🟠 问题

1. **项目级克隆后无回填主模板机制**：`clone_report_config` 把标准配置克隆为 `project:{pid}`，项目改公式后**改进无法回流主模板**（其他项目不受益）。集团基线机制（GroupNoteTemplateBaseline）只覆盖附注，报表配置无对应的"项目优化→主模板沉淀"通道。
2. **报表配置 update 审计走 core.Log**（formula_updated）—— 与公式管理审计三处分裂问题同源（见 §二）。
3. **note_template JSON 巨大（soe 540KB + listed 919KB）**：纯文件加载，无 DB 化，模板局部改动要整文件重写，多人协作易冲突。
4. **国企/上市差异维护靠 diff JSON**：`note_soe_listed_diff.json` 是 mock（头标 is_mock，见 consol proposal），真实差异需审计师确认；模板演进时 diff 文件需同步手维护。
5. **5 种 standard × 四表的覆盖率不透明**：report_config_seed 是否对 4 个组合 standard 都全覆盖四表，无自动校验（仅 enterprise 兜底）。

### 改进建议

- **P1 报表配置加"主模板回填"通道**：仿附注 GroupNoteTemplateBaseline，项目级 report_config 优化后可"提交为主模板候选"（admin 审核后回填 standard 级），让优化沉淀复用。
- **P1 标准覆盖率校验脚本**：CI 加 `validate_report_config_coverage`，确保 soe/listed × consol/standalone 四组合对四表（BS/IS/CFS/EQ）行次无缺漏（复用 report-module-enhancement 的 formula_coverage 模式）。
- **P2 note_template 大文件 DB 化或分章节存储**：按章节拆分存储（disclosure_notes 表已有 section 粒度），避免整文件重写冲突。
- **P2 国企/上市 diff 接审计师真实数据**：去 mock，diff 由审计专业确认后入库（关联 consol proposal P-7）。
- **保持**：template_type + report_scope → standard 的组合映射设计清晰，是正确抽象。

---

## 七、知识库（Knowledge Base）

> ⚠️ **二次复盘重大修正**：初稿称"双轨 + ChromaDB 未接入"**不准确**。实证发现是**三套并行系统**，且**已有真实向量语义检索（基于 PG+numpy，非 ChromaDB）**。下方为修正后的准确现状。

### 现状（三套并行，代码实证）

| # | 系统 | 数据对象 | 检索方式 | 调用方 | 存储 |
|---|------|---------|---------|--------|------|
| A | `KnowledgeDocument`/`KnowledgeFolder`（`knowledge_folder_service.py`） | 用户上传的知识文件（9 分类，含底稿模板库）+ content_text + 版本链 + 权限 | `ilike('%kw%')` 朴素匹配 | `reference_doc_service.load_from_knowledge_base` | PG（content_text） |
| B | `KnowledgeService`（`knowledge_service.py`，旧） | 文件系统文档 | `list_documents(category)` | **全仓仅 1 处**（A 的降级分支） | 文件系统 |
| C | **`KnowledgeIndexService`（`knowledge_index_service.py`）** | **项目业务数据**（DocumentScan/AdjustmentEntry/TrialBalance/AuditReport/Contract/AuditFinding） | **真向量语义检索**（`AIService.embedding` + 余弦相似度 + top_k + 跨年 search_cross_year） | `ai_chat_service`（AI 对话 RAG） | PG `KnowledgeIndex` 表（embedding_vector 逗号串）+ numpy 内存算相似度 |

**关键实证**：
- C 是**已落地的 RAG 引擎**（build_index/semantic_search/incremental_update/add_document/search_cross_year + 有 test_knowledge_index + test_ai_services 守护），`ai_chat_service` 已用它做语义检索。
- `ai_service.py` **有 ChromaDB 客户端**（`_get_chromadb_client` + `embedding()`），但 ChromaDB **仅用于 health check**（`/api/v1/heartbeat`），**实际向量存储/检索走 PG `KnowledgeIndex` 表 + numpy**，ChromaDB 闲置。
- A（知识文件）与 C（业务数据向量）**互不连通**：C 的 `_fetch_project_texts` 索引 6 类业务数据，**不含 KnowledgeDocument**；A 的检索还停在 ilike。

### 🟠 问题（修正后）

1. **三套系统、检索能力割裂**：A（知识文件 ilike）/ B（文件系统 fallback）/ C（业务数据向量 RAG）各管一摊；**用户上传的知识文件（A）享受不到已存在的向量检索（C）**，C 的语义能力只覆盖业务数据。
2. **向量存储选型矛盾**：C 把 embedding 存 PG 文本列 + 每次 query 全表拉出 numpy 算余弦（O(N) 全扫，大库性能差），而平台**已部署 ChromaDB**（docker-compose + ai_service 客户端）却只做 health check —— 该用专业向量库的地方用了 PG 文本列。
3. **B 旧服务双轨**：`KnowledgeService` 全仓仅 A 的 1 处降级调用，是低风险可清的尾巴。
4. **content_text 填充率未知**：A 依赖 content_text 非 NULL 才命中 ilike，PDF/docx 导入是否提取不确定。
5. **知识库与底稿模板库职责交叉**：A 有「底稿模板库」分类，wp_template_registry 也管底稿模板。

### 改进建议（修正后，复用已有 C 引擎而非从零造）

- **P0 清理 B 旧服务（~0.5 天）**：`reference_doc_service` 删文件系统降级分支（仅 1 处），`KnowledgeService` 标 deprecated。
- **P1 A 接入 C 的向量引擎（~1.5 天，复用而非新建）**：把 `KnowledgeDocument` 纳入 `KnowledgeIndexService._fetch_project_texts`（新增 source_type=knowledge_doc），知识文件写入时 `incremental_update` 建向量；`reference_doc_service.load_from_knowledge_base` 改调 `KnowledgeIndexService.semantic_search`，ilike 作降级。**关键：不是"从零接 ChromaDB"，而是"把知识文件喂进已存在的 RAG 引擎"。**
- **P1 向量存储选型评审（~1 天）**：C 的 PG 文本列 + numpy 全扫在大库（6000 并发目标）会成瓶颈；评估迁移到已部署的 ChromaDB（ai_service 客户端已就绪）或 PG `pgvector` 扩展（带 ivfflat 索引），替代"逗号串 + 全表 numpy"。这是真正的技术选型债。
- **P2 content_text 填充保障**：导入 PDF/docx 复用 `wp_document_recognizer`/MinerU 提取 content_text。
- **P2 底稿模板归属统一**：底稿 xlsx 统一存知识库「底稿模板库」分类 + wp_template_registry 只存元数据引用。

---

## 八、横切发现与根因（最重要）

### 🔴 根因：多数模块"新旧双轨/双真相源"（复盘后收敛为 4 处）

逐模块都重构到一半、旧路径未删，形成系统性债务：

| 模块 | 双源 A（新/目标） | 双源 B（旧/遗留） | 风险 | 复盘判定 |
|------|------------------|------------------|------|---------|
| 地址坐标库 | 内存动态 `address_registry` | 文件 L1/L2/L3（33MB+）`address_registry_v2` | 职责重叠、L1 33MB 全仓 0 引用 | 🔴 真双源 |
| 公式求值引擎 | （无真正统一） | `formula_engine` + `report_engine` + `formula_parser` + `formula_unified` 4 套并行 | DSL 各解析一遍、函数集无保证一致、语义漂移 | 🔴 真多源（第四轮新增） |
| 公式审计 | 哈希链 `audit_log_entries` | `formula_audit_log` 表 + `core.Log` | 留痕三处分裂、查询要并三处 | 🔴 真分裂 |
| 报告模板库 | DB `report_config`（项目级克隆） | JSON seed + 无回填通道 | 优化不沉淀 | 🟠 缺回填 |
| 知识库 | DB `KnowledgeDocument`(A) + PG向量 `KnowledgeIndexService`(C) | 文件系统 `KnowledgeService`(B) | 三套割裂：A 享受不到 C 的向量检索；B 是旧尾巴 | 🟠 三套需收口 |
| ~~枚举字典~~ | API `useDictStore` + `_DICTS` | ~~前端 statusMaps.ts~~ | ~~双维护~~ | ✅ 复盘下调：API 主源 + statusEnum.ts 显式 fallback（健康），statusMaps.ts 不存在 |
| ~~底稿模板库~~ | PG `wp_template_registry` 叠加层 | JSON `gt_template_library.json` 主源 | ~~双写~~ | 🟡 复盘下调：分层兜底（非镜像双写），真源未拍板 |

**修正后的真问题**：地址库（真双系统）+ 公式审计（真三处分裂）是硬伤；报告模板（缺回填）+ 知识库（真双轨）是结构缺口；枚举字典 + 底稿模板库经实证是"主源 + 兜底"合理分层，仅需澄清真源/陈旧注释，不属于需重构的"双真相源"。

### 🟠 次要共性
- **懒建表反模式**：`formula_audit_log` / 多个 consol 表用 `CREATE TABLE IF NOT EXISTS` 绕开 D6 迁移（drift detector 盲区，呼应 consol C1/C3）。
- **巨型 JSON 进 git**：address L1 33MB / unified_dependency_graph 11.9MB / note_template_listed 919KB —— 生成物与源数据混存。
- **审计留痕口径不统一**：哈希链 / core.Log / 专用表三套并存，CAS 1131 合规复核困难。

---

## 九、改进路线图（按 ROI 排序）

> 📌 **以 §十八 统一治理总纲为准**：本节是初稿的逐项改进清单；经四轮复盘后，公式/检索/审计三处已升级为"单内核统一架构"（§十五/十六/十七），其工作量与次序以 §十八 总纲为权威。本节保留作功能点明细参考。

### P0 — 消除真"双真相源"（地基，必做，~4 人天）
1. **公式审计留痕收口哈希链**（~1.5 天）：废 `formula_audit_log` 懒建表 + `core.Log` formula_updated → 统一 `append_audit_log` 新增 `formula_changed` event_type schema；保留查询视图走 action_type 过滤。
2. **地址库双系统边界澄清 + 33MB 死文件清理**（~1 天）：L1 物理(33.6MB)全仓 0 引用已实证 → 移出 git tracked 或 gzip；两文件头互标 `@see` 职责（V2 三级文件仅 linkage_graph 离线构建用，运行时走内存版）。
3. **知识库收口 DB 模型**（~1.5 天）：旧 KnowledgeService 标 deprecated + 现有文件迁入 DB；reference_doc_service 移文件系统降级。

### P1 — 功能增强 + 真源澄清（沉淀复用，~6.5 人天）
4. **报表配置"主模板回填"通道 + 覆盖率 CI 校验**（~2 天）：项目优化沉淀 + soe/listed×consol/standalone 四组合无缺漏。
5. **底稿模板库真源拍板 + registry↔JSON 同步**（~1 天）：ADR 明确 JSON 为模板文件/生成主源、registry 表为分类/版本叠加层；补 scan 脚本同步写 registry 表（消除"表数据不知从哪来"）。
6. **枚举字典陈旧注释修正 + 真源声明**（~0.5 天，复盘下调：非重构）：`_DICTS` docstring "statusMaps.ts" → "statusEnum.ts（fallback）"；可选脚本从 `_DICTS` 生成 statusEnum.ts 兜底块防漂移。
7. **公式管理覆盖合并 + 底稿**（~1.5 天）：FormulaManagerScope 补合并报表/附注/底稿数据源节点。
8. **知识库 A 接入已有 C 向量引擎 + 存储选型评审**（~2.5 天）：把 KnowledgeDocument 喂进已存在的 `KnowledgeIndexService`（复用，非新建）；评估 C 的 PG+numpy 向量存储迁 ChromaDB/pgvector（详见 §12.4）。

### P2 — 体验与性能（~5 人天）
9. 地址库 Redis 二级缓存（冷启动/多 worker 共享）
10. 公式变更时间线 UI + 一键回滚（复用时光机）
11. 高级查询结果 Redis 缓存（6000 并发）+ 大结果集流式导出
12. note_template 大文件按章节 DB 化
13. 枚举字典扩展到核心业务枚举（EliminationEntryType 等）

### 外部依赖 / 待审计专业（不投全力）
- 国企/上市 diff 去 mock（待审计师真实数据，关联 consol P-7）
- 懒建表入 D6 迁移（依赖本地 schema 漂移大迁移 spec，956 漂移单独立项）

---

## 十、合伙人投资判断

- **这 7 个是天天在用的横切支撑层**（不像合并模块卡真实数据），改进 ROI 显著高于合并模块，建议优先级**高于** consol Phase 2/3。
- **P0「消除真双真相源」是地基止血**：地址库双系统 + 公式审计三处分裂不除，上层功能都在"改一处忘另一处"的脆弱基础上叠加。~4 人天投入，回报是全平台数据一致性 + 可维护性 + 自动化安全网覆盖。
- **P0/P1 共 ~10.5 人天可一轮做完**，且互相独立（可并行/按模块分批），无外部数据依赖，是当前最值得投入的方向。
- **建议落地方式**：每个 P0 项一个小 spec（bugfix 或 feature），逐个消除双源；P1 功能增强待 P0 地基稳固后启动。

---

## 附：核查方法与可信度

- 全程 readCode 实证（address_registry.py 673 行 / report_config_service.py / system_dicts.py / wp_template_registry.py / knowledge_folder_service.py / custom_query.py / query_builder.py 全文或关键段）+ grep 验证锚点（L1 物理 0 加载、formula 审计三处、双源文件大小）。
- 完成度/健康度为现场负责人判断，非文档自述；"双真相源"结论基于实际 grep 到的并行代码路径。
- 未覆盖：各模块前端 view 的交互细节（仅确认入口与挂载）、运行时性能实测（需压测）。

---

## 十一、二次复盘修正记录（2026-05-31，代码实证纠错）

初稿凭首轮 readCode 印象下了几处过重判断，二次复盘逐一回代码核对后修正如下（遵循"复盘必做代码实证"铁律）：

| # | 初稿判断 | 实证结果 | 修正 |
|---|---------|---------|------|
| 1 | ④枚举字典"前端 statusMaps.ts 硬编码，双维护漂移" | `statusMaps.ts` **不存在**（fileSearch 0 命中）；真实是 `constants/statusEnum.ts` 的 `STATUS_DICT`，且是 `useDictStore`(API 主源) 的**文档化 fallback**，有 statusEnum.test.ts 守护 | 🟢 下调为健康；`_DICTS` docstring 里 "statusMaps.ts" 是陈旧注释 |
| 2 | ⑤底稿模板库"PG registry vs JSON 双写" | `gt_template_library.json` 是 **~8 个服务消费的主索引**，`wp_template_registry` 表是**后加叠加层带 JSON 降级**（table_exists 守卫）；非对称镜像双写 | 🟡 下调为"分层兜底，真源未拍板" |
| 3 | ①地址库 L1"疑似死数据" | 全仓 grep `l1_physical` **0 处代码引用**（只 docs + 本文档自身）；scan 脚本只生成 l2/l3/resolved，不生成也不读 L1 | 🔴 维持，证据更强（确认 0 引用，非"疑似"） |
| 4 | "7 模块普遍双真相源" | 实证后真问题集中在 ①②⑥⑦ 4 处；④⑤ 是合理分层 | 修正横切结论范围 |

**复盘确认无误的判断**（维持）：
- ②公式审计三处分裂（formula_audit_log 表 + core.Log formula_updated + 哈希链）—— 三处 grep 实证属实
- ①地址库两套并行系统均已在 router_registry/system.py 注册（§内存版 + §59 V2），都是 live 非死代码
- ③高级查询白名单安全模型 + ④枚举字典双层设计 是标杆（维持 🟢）
- ⑥报告模板无回填通道 + ⑦知识库双轨 + ilike 检索 —— 维持

**方法论教训**：模块完成度/健康度评估，"双源"这类结论必须 grep 确认两条路径都是 live 且对称写入，否则容易把"主源 + 合理 fallback"误判为"双维护腐化"。本次 ④⑤ 即属此类误判，二次实证纠正。

---

## 十二、双源问题专项改进方案（针对程序实际情况，可直接落地）

> 本节对 4 处真双源问题给出**基于实际调用图**的专业方案：每处含「实际现状 → 根因 → 方案 → 落地步骤 → 调用方影响 → 风险与回滚」。调用图已 grep 实证。

### 12.1 公式审计三处分裂 → 收口哈希链（🔴 P0，~1.5 天）

**实际现状（调用图实证）**：
- 写入方 1：`routers/formula_audit_log.py` 的 `POST /api/formula-audit` + `report_config.py` 内联 INSERT（execute 动作）→ 写 `formula_audit_log` 表（`ensure_table` 每请求懒建）
- 写入方 2：`report_config_service.update_config` → 写 `core.Log` 表（`action="formula_updated"` + `_diff`）
- 写入方 3：合规哈希链 `audit_log_entries`（`append_audit_log`，防篡改，已有 consol_lifecycle 等 schema）
- 读取方：仅 `formula_audit_log.py` 的 `GET` 查询视图（前端公式管理历史）；service-dependency 图确认 `report_config → formula_audit_log`

**根因**：`formula_audit_log` 是早期为"公式专用查询"建的独立表，未与后来的合规哈希链统一；`core.Log` 是更早的通用日志。三者都在记"公式变了"，但防篡改级别（哈希链 > 专用表 > Log）、字段、查询入口全不同。

**方案（分两步，先统一写入再统一读取，不一刀切）**：
1. **写入收口**：新增 `EventType` 无关的 `append_audit_log` schema `formula_changed`（字段 `module/row_code/action/old_formula/new_formula/result_value/trace`）。三个写入方统一改调 `append_audit_log(action='formula.changed', details={...})`。
2. **读取兼容**：`formula_audit_log.py` 的 `GET` 改为查 `audit_log_entries WHERE action_type='formula.changed'`（payload JSONB 过滤 module/row_code），**保持前端 API 路径与返回结构不变**（前端零改动）。
3. **废表**：确认无其他读取后，`formula_audit_log` 表停写（保留历史数据只读一个迁移周期）+ 删 `ensure_table` 懒建；`core.Log` 的 formula_updated 分支删除。

**落地步骤**：
- ① `audit_log_helper.EVENT_TYPE_SCHEMAS` 加 `formula_changed` 必需字段集
- ② grep 3 个写入点改 `append_audit_log`（report_config 内联 / report_config_service.update_config / formula_audit_log POST）
- ③ `formula_audit_log.py` GET 改查哈希链 + payload 过滤，前端 apiPaths 不动
- ④ 删 `ensure_table`；老表数据可选一次性迁入哈希链或保留只读

**调用方影响**：前端公式历史查询 API 路径/结构不变（零改动）；后端 3 写入点改造。
**风险与回滚**：哈希链是 append-only，公式变更入链后不可改 —— 符合 CAS 1131（这正是目的）。回滚=保留老表停写期可双写过渡。
**收益**：公式变更留痕单一真源 + 防篡改 + QC/EQCR 一处查；消除懒建表 drift 盲区。

---

### 12.2 地址库两套系统 → **澄清职责而非合并**（🔴 P0 修正认知，~1 天）

**实际现状（调用图实证，修正"该合并"的初判）**：
- **V1 内存版** `address_registry.py`（单例）+ `routers/address_registry.py`（/api/address-registry）→ 前端 `stores/addressRegistry.ts` `useAddressRegistry` → **公式编辑器** `CellSelector.vue` / `FormulaRefPicker.vue` 消费（语义地址搜索/解析/校验/跳转）
- **V2 文件版** `address_registry_v2.py`（/api/address-registry/v2）读 L2/L3/resolved JSON → 前端 `useStaleImpact.ts` 消费（**stale 影响 BFS / 依赖查询 / 语义→物理解析**）
- **关键发现**：**两者不是冗余，是两个不同关注点**：V1 服务"公式编辑时选地址"，V2 服务"单元格变更的下游影响分析"。共用 "address-registry" 名字造成误解。

**根因**：命名撞车 + 文档未区分，让人以为是"新旧重复"。实际是「运行时动态地址目录（V1）」vs「设计期静态依赖图（V2）」两个正交能力。

**方案（不合并，明确边界 + 清死文件）**：
1. **重命名澄清**：V2 对外语义其实是"依赖/影响分析"，建议 router tag 与前端 service 命名向 `linkage`/`dependency` 靠拢（如 `useStaleImpact` 已经是对的），在两个 router 文件头互标 `@see`：V1=运行时地址目录（公式编辑用），V2=静态依赖图（影响分析用，linkage_graph 离线产物）。
2. **清 L1 死文件**：`address_registry_l1_physical.json`(33.6MB) 全仓代码 0 引用已实证 → `git rm` 移出 tracked（若构建需要则改 `.gitignore` + 文档注明生成命令）。同步评估 `unified_dependency_graph.json`(11.9MB) 是否运行时加载（linkage_graph_builder 生成它，确认消费方）。
3. **V1 加 Redis 二级缓存**（P1）：内存版单例重启丢缓存 + 多 worker 各建一份，按 `project:year:domain` 缓存到 Redis 共享。

**落地步骤**：
- ① 两 router 文件头加职责注释 + `@see` 互链
- ② `git rm --cached address_registry_l1_physical.json`（确认 scan 脚本不生成它 → 是历史遗留，直接删）
- ③ 前端不动（两套 store 各服务各的，本就分离）

**调用方影响**：零功能影响（仅命名/文档澄清 + 删死文件）。
**风险与回滚**：L1 删除前 `git log --oneline -- <file>` 确认无近期更新 + grep 二次确认 0 引用；删错可 git restore。
**收益**：消除"该用哪个"困惑 + 仓库瘦身 33MB；**避免错误地把两个正交能力强行合并**（这才是专业判断 —— 初判"合并"是错的）。

---

### 12.3 报告模板库克隆无回填 → 双向沉淀通道（🟠 P1，~2 天）

**实际现状（代码实证）**：
- `report_config_service.clone_report_config(project_id, standard)` 把 standard 级配置（soe_consolidated 等）克隆为 `applicable_standard="project:{pid}"`，项目可自定义公式
- `update_config` 改项目级公式 + 写 core.Log 留痕
- **缺口**：项目级优化（如某项目修对了一个公式）**只留在 `project:{pid}`，无通道回流 standard 主模板**，其他项目不受益；反向，主模板更新后已克隆项目**也不会同步**（克隆是一次性快照）

**根因**：克隆是"一次性 fork"，没有"主模板 ← 项目"的回填评审通道，也没有"主模板 → 项目"的更新推送。对比附注侧已有 `GroupNoteTemplateBaseline`（集团基线 + apply/diff/upgrade/feedback 双向机制），报表侧缺等价物。

**方案（仿附注 GroupNoteTemplateBaseline 成熟模式）**：
1. **回填评审通道**：项目级 report_config 行加"提交为主模板候选"动作 → 写入待审表 → admin 审核 → 合并回 standard 级（带版本号 + 审计留痕）。复用附注 baseline 的 `suggest_feedback`（child 反哺）设计。
2. **主模板更新 diff 推送**：standard 主模板升版时，对已克隆项目算 diff（仿 `diff_baseline`），前端提示"主模板已更新 N 行，是否同步"（保留项目本地覆盖）。
3. **覆盖率 CI 校验**：`validate_report_config_coverage` 脚本，确保 soe/listed × consolidated/standalone 四组合 standard 对四表（BS/IS/CFS/EQ）行次无缺漏（复用 report-module-enhancement 的 formula_coverage 模式）。

**落地步骤**：
- ① 新建 `ReportConfigBaseline` 表（或复用 GroupNoteTemplateBaseline 泛化）+ ORM + D6 迁移
- ② `report_config_service` 加 `suggest_to_master` / `apply_master_update` / `diff_vs_master` 方法
- ③ 前端 ReportConfigTab 加"提交主模板候选 / 同步主模板更新"入口
- ④ CI 覆盖率脚本 + 集成测试

**调用方影响**：新增能力，不破坏现有 clone/update；ReportConfigTab 加 UI。
**风险与回滚**：回填需 admin 审核门禁（防误把项目特例污染主模板）；feature flag 控制。
**收益**：报表公式优化跨项目沉淀复用（与附注 baseline 对齐，消除"报表是孤儿"）。

---

### 12.4 知识库三套系统 → 清旧轨 + 复用已有 RAG 引擎（🟠 P0/P1，~3 天）

**实际现状（调用图实证，二次复盘修正为三套）**：
- A `KnowledgeDocument`（DB）：用户知识文件，ilike 检索，`reference_doc_service` 调用
- B `KnowledgeService`（文件系统，旧）：**全仓仅 1 处调用**（A 的降级分支）
- C **`KnowledgeIndexService`（PG 向量 RAG，已落地）**：索引 6 类业务数据（TB/调整/报告/合同/发现/扫描件），`AIService.embedding` + 余弦相似度 + 跨年检索，`ai_chat_service` 消费；embedding 存 PG `KnowledgeIndex` 表（逗号串）+ numpy 全扫算相似度
- `ai_service` 有 ChromaDB 客户端但**仅 health check**，实际向量走 PG+numpy

**根因**：A（知识文件）与 C（业务数据 RAG）是两次独立演进，互不连通 —— C 的语义检索能力没覆盖 A 的知识文件；同时 C 的向量存储用 PG 文本列 + numpy 全扫（非专业向量库），是历史选型债；B 是可清的旧尾巴。

**方案（复用已有 C 引擎，不从零造）**：
1. **清 B（P0，~0.5 天）**：`reference_doc_service` 删文件系统降级分支（仅 1 处），`KnowledgeService` 标 deprecated。
2. **A 接入 C（P1，~1.5 天）**：`KnowledgeIndexService._fetch_project_texts` 加 `KnowledgeDocument`（新 source_type=knowledge_doc）；知识文件 create/update 钩子调 `incremental_update` 建向量；`reference_doc_service.load_from_knowledge_base` 改调 `semantic_search`，ilike 降级。**关键认知修正：不是"从零接 ChromaDB"，是"把知识文件喂进已存在的 RAG 引擎"。**
3. **向量存储选型（P1，~1 天）**：C 的"PG 逗号串 + numpy 全表扫"在大库 + 6000 并发会成瓶颈 → 评估迁 ChromaDB（客户端已就绪）或 PG `pgvector`（ivfflat 索引）。

**落地步骤**：
- ① grep 确认 KnowledgeService 仅 reference_doc_service 1 处（已实证）→ 删降级 + deprecated
- ② KnowledgeIndexService 加 knowledge_doc source_type + KnowledgeDocument CRUD 钩子建向量
- ③ reference_doc_service 改 semantic_search + ilike 兜底
- ④ 选型评审：pgvector vs ChromaDB（独立决策 + ADR）

**调用方影响**：A 检索升级（reference_doc_service 1 处）；C 加一个数据源（向后兼容）；ai_chat_service 不变。
**风险与回滚**：语义检索失败降级 ilike（双保险）；向量存储迁移是独立 P1，与 A 接入解耦。
**收益**：知识文件享受已有语义检索 + 消除"造重复 RAG"风险（C 已存在，复用即可）+ 暴露真正的向量存储选型债（PG 文本列 → 专业向量库）。

> **专业要点（复盘核心收获）**：初稿建议"接入 ChromaDB 向量检索"是在**不知道 C 已存在**的情况下提的，会导致重复造轮子。正确方案是"复用 C + 让 A 入网 + 修 C 的存储选型"。这印证了"评估前必须 grep 全部同类服务"的铁律 —— 知识/检索域实际有 3 个 service（folder/index/旧 service），漏看 index_service 就会误判。

---

### 12.5 四方案优先级与依赖

| 方案 | 优先级 | 工作量 | 调用方影响 | 独立性 |
|------|--------|--------|-----------|--------|
| 12.1 公式审计收口哈希链 | 🔴 P0 | 1.5 天 | 前端零改 | 独立 |
| 12.2 地址库澄清+清死文件 | 🔴 P0 | 1 天 | 零功能影响 | 独立 |
| 12.4(1) 知识库收口 DB | 🔴 P0 | 0.5 天 | 1 处改造 | 独立 |
| 12.4(2)(3) 向量检索 | 🟠 P1 | 2.5 天 | 惠及 RAG | 依赖 ChromaDB |
| 12.3 报表模板回填 | 🟠 P1 | 2 天 | 新增能力 | 可仿附注 baseline |

**建议执行顺序**：先做 3 个 P0（共 ~3 天，互相独立、调用方影响小、纯地基止血）→ 验证稳定后做 2 个 P1（功能增强）。每个方案建议独立一个 spec（bugfix 类：12.1/12.2/12.4-1；feature 类：12.3/12.4-2）。

**专业判断要点**：
- **12.2 不是"合并"而是"澄清"** —— 这是本轮最重要的认知修正：V1/V2 地址库服务两个正交关注点（公式编辑 vs 影响分析），强行合并会破坏各自优化空间，正确做法是命名/文档澄清 + 删真死文件（L1 33MB）。
- **12.1/12.4 收口风险低** —— 公式审计前端 API 不变、知识库仅 1 处调用点，是高 ROI 低风险的地基整理。
- **12.3 有现成范式** —— 报表回填直接仿附注 GroupNoteTemplateBaseline，不重新发明轮子。

---

## 十三、第三轮复盘修正（2026-05-31，知识库重大纠错）

应"再复盘，一定要专业"要求，对 §十二 落地方案的承重假设逐一回代码核对，发现 **§七/§12.4 知识库判断有重大遗漏**，修正如下：

| # | 前稿判断 | 第三轮实证结果 | 修正 |
|---|---------|--------------|------|
| 1 | 知识库"双轨"（KnowledgeDocument DB + KnowledgeService 文件系统） | **实为三套**：漏看了 `KnowledgeIndexService`（PG 向量 RAG，已落地，ai_chat_service 在用，有测试） | 双轨 → 三套并行 |
| 2 | "ChromaDB 配置就绪但知识库未接入向量检索" | **半错**：①确有真向量检索（C），但用 `AIService.embedding` + PG `KnowledgeIndex` 表（逗号串）+ numpy 余弦，**不是 ChromaDB**；②`ai_service` 的 ChromaDB 客户端**仅 health check**，存储/检索没用它 | 改为"已有 PG 向量 RAG，ChromaDB 闲置仅探活" |
| 3 | 建议"接入 ChromaDB 向量检索"（P1） | 会**重复造轮子**（C 已是完整 RAG 引擎） | 改为"A 知识文件喂进已有 C 引擎 + C 的存储选型评审（PG→pgvector/ChromaDB）" |

**为什么漏看**：首两轮 grep `knowledge_base`/`knowledge_service` 命中了 folder_service 和旧 service，但 `KnowledgeIndexService`（文件名 knowledge_index_service）+ `ai_service.embedding` 不在那批关键词里；本轮因 service-dependency 图里瞥见 `knowledge_index_service` + `ai_chat_service → knowledge_index_service` 才追进去。

**专业教训（强化"评估前 grep 全部同类服务"铁律）**：
- 一个能力域（检索/RAG）可能有 ≥3 个 service 分散实现，**grep 一两个关键词不足以覆盖**；应 grep 该域的多个同义词（knowledge / index / embedding / vector / semantic / chroma / rag）+ 看 service-dependency 图的入边出边，确认没有遗漏的并行实现，再下"是否重复/该接什么"的结论。
- **"建议接入 X 基建"前，必须先确认 X 是否已被某处接入** —— 否则会把"已有但选型欠佳"误判为"完全没有"，给出从零造的错误建议。本轮 ChromaDB 即此类：它被接了（health check）但没被正确用于存储，真问题是"选型/接法"不是"有无"。

**本轮维持无误的判断**：地址库 V1/V2 正交（不合并）/ 公式审计三处分裂 / 报表模板无回填 / 枚举字典健康 / 底稿模板库分层兜底 —— 这些第二轮已实证，第三轮抽查无新错。

---

## 十四、第四轮复盘修正（2026-05-31，公式引擎多源重大纠错）

应"继续仔细复盘，还有没考虑的地方"，**主动用知识库踩过的坑（漏看并行实现）去检查其他模块**，在公式管理发现同类、且更严重的遗漏：

| # | 前稿判断 | 第四轮实证结果 | 修正 |
|---|---------|--------------|------|
| 1 | "统一公式引擎 `formula_unified.py`" + report_engine 安全求值（=2 套） | **公式求值器至少 4 套并行**：`formula_engine.py`（自称"唯一执行器"）/ `report_engine.py`（_safe_eval_expr）/ `formula_parser.py`（FormulaEvaluator）/ `formula_unified.py`（_safe_eval）；加 note/依赖/反向索引共 **8 个 formula service** | 🟠 → 🔴，公式管理是最严重多源 |
| 2 | 公式管理主要问题=审计留痕分裂 | 审计分裂只是表象，**根本问题是 4 套求值引擎并行**（DSL 各解析、函数集无一致性保证） | P0 新增"引擎收敛盘点"，比审计留痕更根本 |
| 3 | 健康度 🟠 | 两个文件都自称"统一引擎"却谁都没统一，是典型"统一未遂"腐化 | 升级 🔴 |

**为什么这次能抓到**：知识库第三轮教训"一个能力域可能有 ≥3 个并行实现" → 本轮**主动 grep 公式域多关键词**（`def evaluate` / `_safe_eval` / `class.*Formula` / `formula_engine`）+ 看 service-dependency 图，立刻暴露 4 套引擎。**这正是把上一轮的方法论教训立即应用到其他模块的结果。**

**专业判断（公式引擎收敛要慎重）**：
- 4 套引擎调用面都很广（formula_engine 被 6+ 调用方用，report_engine 被 reports/consol 用），**不能贸然合并** —— 必须先 ADR 调研：diff 各自支持的函数集 + DSL token + 调用方依赖，确定"主引擎 + 其余委托/删除"路径，再分批迁移（参考 ADR-CONSOL-101 合并侧"先跑通注入版再删旧"的稳妥模式）。
- 这是比"审计留痕收口"更根本的 P0：审计记的是"公式变了"，但如果 4 套引擎对同一公式算出不同结果，留痕一致也没用。

**累计四轮复盘修正项**：①枚举字典（🟠→🟢，statusMaps.ts 不存在）②底稿模板库（双写→分层兜底）③地址库（合并→澄清，V1/V2 正交）④知识库（双轨→三套系统，已有 PG 向量 RAG）⑤**公式引擎（2 套→4 套，🟠→🔴）**。

**仍待后续复盘验证的盲区（诚实声明）**：本轮重点查了公式域；高级查询（custom_query vs query_builder 是否还有第三套查询路径）、报表生成（report_engine vs report_formula_service vs cfs_worksheet_engine 是否重叠）尚未用同样方法深挖，下一轮可继续。

---

## 十五、公式引擎统一架构设计（企业级 / 可维护 / 可扩展）

> 应"一定要统一、可维护、可扩展、企业级"要求。本节给出 4 套引擎收敛为**单一企业级公式内核**的目标架构 + 迁移路径。设计基于对 4 套引擎的逐一 readCode 实证（函数集/解析策略/接口/调用方）。

### 15.1 四套引擎能力实测对照（收敛决策依据）

| 维度 | `formula_engine.py` | `report_engine.py` | `formula_parser.py` | `formula_unified.py` |
|------|--------------------|--------------------|--------------------|--------------------|
| 自我定位 | "企业级唯一执行器" | Phase1 报表主引擎 | 递归下降解析器 | "统一"解析+预览 |
| 解析策略 | regex token 替换 | regex token 替换 | **真递归下降 parser**(tokenize+AST 节点) | regex |
| 函数集 | **最全**(TB/SUM_TB/ROW/SUM_ROW/REPORT/PREV/AUX/NOTE/WP + ABS/ROUND/MAX/MIN/IF) | TB/SUM_TB/ROW/SUM_ROW/REPORT/NOTE/WP/AUX/PREV | 同左(AST) | SUM/ABS/IF + 单元格引用 |
| 取数方式 | **纯函数+FormulaContext 注入**(无 DB 耦合) | DB 耦合(AmountResolver 注入，Phase1 改造) | DB 耦合(FormulaEvaluator 连执行器) | 内存 cells |
| 返回结构 | **FormulaResult**(value+errors+warnings+trace) | Decimal | Decimal | float/None |
| 扩展性 | **插件式函数注册**(register_custom_function) | 硬编码 | 硬编码 | 硬编码 |
| 安全求值 | safe_eval_expr(ast) | _safe_eval_expr(ast) | AST 求值 | _safe_eval(ast) |
| 校验 | **validate_formula**(括号/未知函数) | 无独立 | 解析期抛 ParseError | 无 |
| 调用面 | /formula router + report_config + trial_balance + prefill + event_handlers + wp_user_formulas | reports + consol | report_config | formula_to_display |

**收敛决策（实证结论）**：`formula_engine.py` 是**唯一已具备企业级特征的引擎**（纯函数 + 上下文注入 + 结果对象 + 插件注册 + 校验），应作为**统一内核**；`report_engine`/`formula_parser`/`formula_unified` 的独有价值分别是「DB 取数编排」「严谨递归下降解析」「显示预览」—— 这些应作为**内核之上的薄层**，而非各自重造求值器。

---

### 15.2 目标架构：三层单内核（Single-Kernel, Layered）

```
┌─────────────────────────────────────────────────────────────┐
│  L3 取数适配层（Resolver Adapters）— 各业务域只管"从哪取数"      │
│  ┌──────────────┬──────────────┬──────────────┬───────────┐  │
│  │TrialBalance  │ConsolTrial   │Note/WP       │Display    │  │
│  │Resolver(单体) │Resolver(合并) │Resolver(附注) │(预览mock) │  │
│  └──────┬───────┴──────┬───────┴──────┬───────┴─────┬─────┘  │
│         └──── 实现统一 AmountResolver Protocol ───────┘        │
├─────────────────────────────────────────────────────────────┤
│  L2 编排层（Orchestration）— 预加载数据 → 构建 FormulaContext   │
│  按 project/year/standard 批量取数填充 tb_data/row_cache/prior │
├─────────────────────────────────────────────────────────────┤
│  L1 公式内核（Kernel）= 升级后的 formula_engine.py             │
│  · parse（采用 formula_parser 的递归下降，替换脆弱 regex）       │
│  · FunctionRegistry（插件式，TB/SUM_TB/.../自定义）            │
│  · safe_eval（ast，统一安全求值）                              │
│  · FormulaContext 注入 + FormulaResult(value/errors/trace)    │
│  · validate_formula（语法+函数+地址有效性，接 address_registry）│
└─────────────────────────────────────────────────────────────┘
```

**核心原则（企业级四要素落地）**：
1. **统一**：全平台只有 **1 个求值内核**（formula_engine 升级版）。report/consol/note/底稿/试算表都经 L2 编排 + L3 取数适配调用同一 L1，**消灭 4 套并行求值器**。
2. **可维护**：解析/求值/取数三责分离 —— 改函数行为只改 L1 registry，改取数口径只改 L3 resolver，互不影响；审计/校验/trace 在内核统一产出（呼应 §12.1 公式审计收口哈希链）。
3. **可扩展**：新增函数 = L1 `register_function(name, handler)` 一行（已具备）；新增数据源 = L3 加一个 Resolver（实现 Protocol）；新增业务域（如未来现金流量表专属函数）= L2 加编排，**不碰内核**。
4. **企业级**：FormulaResult 带 errors/warnings/trace（审计可追溯）+ 解析缓存（同公式不重复解析）+ 校验前置（存悬空引用即拒）+ 地址有效性接 address_registry（§一）+ Decimal 全程（金额铁律）。

### 15.3 与已有资产的衔接（不推倒重来）

- **复用 Phase1 的 AmountResolver**（ADR-CONSOL-101 已建 `TrialBalanceResolver`/`ConsolTrialResolver`）→ 直接作为 L3 的两个实现，**架构已对**，只需把 L1 从 report_engine 内嵌求值器抽出为独立内核。
- **采纳 formula_parser 的递归下降解析**替换 formula_engine 的 regex token 替换（regex 对嵌套 `PREV(TB(...))` 等脆弱，parser 更严谨）—— 两者合并为内核的 parse 层。
- **formula_unified 的显示预览** → 降级为 L3 的一个 DisplayResolver（mock 数据），删除其独立 `_safe_eval`。
- **report_engine.evaluate_formula / consol** → 改委托 L1 内核（report_engine 退化为 L2 编排 + L3 取数，不再自带求值器）。

---

### 15.4 迁移路径（分 4 阶段，每阶段可独立验收，零功能回归）

> 铁律：4 套引擎调用面广（formula_engine 6+ 调用方 / report_engine 报表+合并），**禁止一次性合并**。参考 ADR-CONSOL-101 合并侧"先跑通注入版再删旧"的稳妥模式，分阶段迁移 + 每阶段回归基线全绿。

**阶段 0 — 内核固化（~2 天）**
- 把 formula_engine 的 `execute(formula, ctx)→FormulaResult` 确立为唯一内核 API；补 PBT：同一公式 + 同一 FormulaContext，4 套引擎当前输出**逐一对照建基线**（暴露现存语义差异）。
- 采纳 formula_parser 递归下降解析替换内核 regex（先并行跑、diff 一致再切）。
- 产出 ADR-FORMULA-001「单内核 + 三层架构 + AmountResolver Protocol」。

**阶段 1 — report_engine 委托内核（~1.5 天）**
- `report_engine.evaluate_formula` 改为：L2 编排（预载 tb_data/row_cache）→ 调 L1 内核；删除 report_engine 内嵌的 `_safe_eval_expr` + ReportFormulaParser 求值逻辑（保留取数）。
- 回归：单体报表全量基线（test_report_engine 等）逐位一致（同 R1 守门）。

**阶段 2 — consol + formula_parser + formula_unified 收口（~1.5 天）**
- consol 侧已走 report_engine（ADR-CONSOL-101），随阶段 1 自动收口。
- `formula_parser`（report_config 用）改委托内核；`formula_unified` 改为 DisplayResolver，删独立求值器。
- 回归：report_config / 公式预览相关测试。

**阶段 3 — 审计 + 校验收口（~1.5 天，并入 §12.1）**
- 内核 `validate_formula` 接 address_registry 地址有效性校验（存悬空引用即拒）。
- 公式变更统一 `append_audit_log(action='formula.changed')`（废 formula_audit_log 懒建表 + core.Log），FormulaResult.trace 入留痕。

**总计 ~6.5 人天**（含审计收口），分 4 阶段，每阶段独立可回滚。

### 15.5 验收标准（企业级达标线）

- ✅ **单内核**：全仓 grep 求值器（`_safe_eval`/`safe_eval_expr`/独立 AST eval）只剩 formula_engine 1 处；report_engine/formula_parser/formula_unified 无独立求值逻辑。
- ✅ **语义一致**：同一公式经任何业务域（report/consol/note/底稿）求值，函数集行为逐位一致（PBT 守门，关联 Q1 语义一致属性）。
- ✅ **可扩展验证**：新增 1 个示例自定义函数（如 `PCT(a,b)`）仅改 L1 registry 一处即全域可用。
- ✅ **可维护验证**：改 1 个取数口径（如 TB 默认列）仅改 L3 resolver 一处。
- ✅ **审计一致**：公式变更只落哈希链一处，trace 可追溯（CAS 1131）。
- ✅ **零回归**：单体报表 + 合并 + 附注 + 试算表公式既有测试全绿。

### 15.6 收益与风险

**收益**：消灭"统一未遂"（两个文件都自称统一却并行）；新增函数/数据源/业务域成本从"改 4 处+怕漏"降到"改 1 处"；公式语义全域可证一致（审计准确性根本保障）；为后续合并底稿公式、AI 公式建议等扩展打地基。

**风险与缓解**：
- 🔴 调用面广 → 分 4 阶段 + 每阶段回归基线（阶段 0 先建 4 引擎输出对照基线，暴露并固化现存差异，避免"统一"时悄悄改变某业务域结果）。
- 🟠 递归下降解析替换 regex 可能有边界差异 → 并行跑 diff 一致再切，保留 regex 一个版本周期降级。
- 🟠 formula_engine 现有 `execute` 是同步纯函数，但 L3 取数是 async → L2 编排层负责 async 取数后传同步 ctx 给 L1（职责清晰，内核保持纯函数可测）。

> **本节定位**：这是把 §二/§十四 暴露的"4 套引擎"问题落到**可执行的企业级统一方案**。建议独立成 spec `formula-engine-unification`（Design-First，含本节架构 + PBT 对照基线），是公式管理 🔴 的根治路径。

---

## 十六、检索/知识层统一架构（企业级 / 可维护 / 可扩展）

> 把 §七 三套知识/检索系统（KnowledgeDocument ilike / KnowledgeService 文件系统 / KnowledgeIndexService PG向量）收敛为单一检索内核。原则同 §十五：单内核 + 取数适配 + 存储可插拔。

### 16.1 目标架构：单检索内核 + 可插拔向量后端

```
┌─────────────────────────────────────────────────────────────┐
│  检索 API（统一入口）semantic_search(scope, query, top_k)      │
│  scope = project_data | knowledge_doc | cross_year | all      │
├─────────────────────────────────────────────────────────────┤
│  RetrievalKernel（= 升级后的 KnowledgeIndexService）           │
│  · 索引源插件：BusinessDataSource(TB/调整/报告/合同/发现)        │
│             + KnowledgeDocSource(知识文件)  ← 新增接入          │
│  · embed（AIService.embedding 统一）                          │
│  · 召回（向量 top_k + 余弦）+ ilike 降级                       │
├─────────────────────────────────────────────────────────────┤
│  VectorStore 抽象（可插拔后端）                                 │
│  ┌────────────────┬─────────────────┬────────────────────┐   │
│  │PgTextStore(现状)│PgVectorStore(P1) │ChromaStore(已有client)│ │
│  └────────────────┴─────────────────┴────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**企业级四要素落地**：
1. **统一**：只有 1 个检索内核（KnowledgeIndexService 升级），KnowledgeDocument 作为新索引源接入，不再 ilike 独立检索；旧 KnowledgeService 文件系统删除。
2. **可维护**：索引源（业务数据/知识文件）与存储后端（PG/ChromaDB）解耦，改一边不动另一边。
3. **可扩展**：新增可检索对象 = 加一个 IndexSource（实现 `fetch_texts(project)→[(type,id,text)]`）；新增向量后端 = 实现 VectorStore Protocol（add/query/delete），现 PG 文本列 → pgvector → ChromaDB 平滑迁移。
4. **企业级**：embed 统一走 AIService（模型可配）+ 向量检索失败降级 ilike（双保险）+ 归档锁定（lock_index 已有）+ 权限过滤（按 project）。

### 16.2 关键修正点（基于第三轮实证）

- **不是"从零接 ChromaDB"**：KnowledgeIndexService 已是完整 RAG（build/search/incremental/cross_year），只需 ①把 KnowledgeDocument 加为 IndexSource ②把 `_fetch_project_texts` 内的 6 类硬编码改为可注册 IndexSource 列表。
- **向量存储是真技术债**：现状 PG 逗号串 + numpy 全表扫（O(N) 每查），6000 并发下必成瓶颈 → 抽 VectorStore Protocol，P1 迁 pgvector（ivfflat 索引，DB 内算余弦）或已部署 ChromaDB（ai_service client 已就绪）。这是"企业级可扩展"的核心动作。

### 16.3 迁移路径（~4 天）
- 阶段 1（~0.5 天）：删 KnowledgeService 文件系统降级（reference_doc_service 1 处），标 deprecated。
- 阶段 2（~1.5 天）：`_fetch_project_texts` 重构为 IndexSource 注册表 + 接入 KnowledgeDocSource；reference_doc_service 改调 semantic_search。
- 阶段 3（~2 天）：抽 VectorStore Protocol + 实现 PgVectorStore（pgvector 扩展）/ ChromaStore，feature flag 切换，PgTextStore 保留降级。
- 独立成 spec `retrieval-kernel-unification`（Design-First）。

---

## 十七、审计留痕统一架构（企业级 / 合规）

> 把 §二/§12.1 三处公式审计（+ 全平台散落留痕）收敛为单一合规审计内核。这是 CAS 1131 工作底稿留痕的合规根基。

### 17.1 目标：唯一合规审计内核 = 哈希链 `append_audit_log`

```
所有业务写操作（公式变更/锁定/审批/删除/归档/AI生成/冲突调解...）
        │  统一调 append_audit_log(action_type, details{schema})
        ▼
  audit_log_entries（哈希链，防篡改，已有 7 类 event_type schema）
        │
        ├── 查询视图层（按 action_type 过滤，替代各专用表）
        │     formula.changed / consol_lifecycle / archive_unarchive ...
        └── 永不另建专用表（formula_audit_log/core.Log 废止）
```

**企业级要素**：
1. **统一**：全平台审计留痕只有哈希链 1 处（已有基建 + 7 类 schema），新增审计类型 = 加一个 EVENT_TYPE_SCHEMA（一行），不再建专用表。
2. **合规**：哈希链防篡改（entry_hash + prev_hash），满足 CAS 1131；QC/EQCR 一处可查全部留痕。
3. **可维护**：废 formula_audit_log 懒建表（绕 D6 反模式）+ core.Log formula_updated 分裂；查询走 action_type 过滤视图，前端 API 不变。
4. **可扩展**：新业务事件留痕 = 注册 schema + 调 append_audit_log，零表结构变更。

### 17.2 迁移（~1.5 天，并入 §15.4 阶段 3）
- 新增 `formula_changed` schema → 3 个公式写入点改调 append_audit_log。
- formula_audit_log GET 改查哈希链（action_type 过滤），前端零改。
- 废懒建表 + core.Log 分支。
- 独立成 spec `audit-trail-unification` 或并入 formula-engine-unification 阶段 3。

---

## 十八、统一治理总纲（三大内核 + 实施次序）

本轮"统一/可维护/可扩展/企业级"诉求，落到 **3 个单内核收敛** + 既有澄清动作：

| 治理项 | 现状 | 目标 | 模式 | 工作量 | spec |
|--------|------|------|------|--------|------|
| **公式内核** | 4 套求值器并行 | 单内核 formula_engine + 三层 | §十五 | ~6.5 天 | formula-engine-unification |
| **检索内核** | 3 套(ilike/文件/PG向量) | 单内核 + 可插拔 VectorStore | §十六 | ~4 天 | retrieval-kernel-unification |
| **审计内核** | 3 处(专用表/Log/哈希链) | 单内核哈希链 | §十七 | ~1.5 天 | audit-trail-unification |
| 地址库 | V1/V2 两套（正交） | **澄清非合并** + 清 33MB 死文件 | §12.2 | ~1 天 | （bugfix） |
| 报表模板回填 | 克隆无回填 | 仿附注 baseline 双向通道 | §12.3 | ~2 天 | report-config-baseline |
| 枚举字典 | 健康 | 仅修陈旧注释 | §四 | ~0.5 天 | （随手） |
| 底稿模板库 | 分层兜底 | 真源拍板 + registry↔JSON 同步 | §五 | ~1 天 | （bugfix） |

**实施次序（企业级地基优先）**：
1. **先三大内核统一**（公式 6.5 + 检索 4 + 审计 1.5，其中审计并入公式阶段3 ≈ 共 ~10.5 天）—— 这是"统一/可维护/可扩展"的根本，每个独立成 Design-First spec，分阶段零回归迁移。
2. **再澄清/补通道**（地址库澄清 + 报表回填 + 模板真源 + 枚举注释 ≈ ~4.5 天）。
3. **核心方法论**：每个内核统一都遵循同一企业级范式 = **单内核（求值/检索/留痕）+ 适配层（取数/索引源/schema）+ 可插拔后端（resolver/vectorstore）+ 分阶段迁移（先建对照基线再切，每阶段零回归）**。这套范式本身就是平台后续所有"消除多源"的标准打法。

> **总结**：本文档历经四轮代码实证复盘（§十一/十三/十四 + 本轮统一设计 §十五~十八），从"模块盘点"深化为"企业级统一架构方案"。三大内核（公式/检索/审计）是平台横切支撑层的根治方向，建议各立 Design-First spec 落地。

---

## 十九、"双向联动同步" vs "单一真源" —— 根本解决之辨（关键架构决策）

> 用户问：双源/多源能否实现真正联动（改一处，另一源自动同步），从根本上解决？
> **诚实结论：要分类型。"双向双写同步"是反模式（问题加倍）；"单一权威源 + 单向派生同步"才是根本解决，且平台已有此能力（EventBus + stale 传播）。**

### 19.1 为什么"两个可写源双向同步"是陷阱（不是根本解决）

把 A、B 两个源都保持可写、再互相同步，会引入**分布式一致性的全部经典难题**：

| 问题 | 后果 |
|------|------|
| **写冲突** | A 改成 X、B 同时改成 Y，谁赢？最后写入覆盖 = 丢数据 |
| **同步顺序/时序** | 事件乱序到达 → A→B 和 B→A 交叉 → 终态不确定 |
| **无限回环** | A 改 → 同步到 B → B 的 change 事件 → 又同步回 A → 死循环（需打标防回环，脆弱） |
| **部分失败** | 同步到一半崩了 → A、B 永久不一致，且无人知道 |
| **审计不可证** | 到底以哪个源为准做了审计判断？合规复核无法回答 |

**审计软件尤其不能接受**：CAS 1131 要求工作底稿数据可追溯、唯一、不可篡改。"两个都对、互相同步"在合规上等于"没有真相"。所以**双写双向同步是把"双源"问题伪装成"已联动"，实际更难维护**。

### 19.2 正解：单一权威源（SoT）+ 单向派生同步（平台已有此能力）

```
   权威源 (Source of Truth，唯一可写)
        │  变更 → 发事件（EventBus）
        ▼
   派生投影 (Derived Projection，只读，由事件重建)
   —— 缓存 / 索引 / 物化视图 / 另一种存储格式
```

- **只有一个源可写**（消除写冲突/回环/时序问题）。
- 其他"源"降级为**派生投影**（只读，由权威源经事件自动重建）—— 这恰好实现了你要的"改一处，别处自动变"，但是**单向**的，安全。
- 派生失败可重建（幂等），不会造成"双向永久不一致"。

**平台已经在用这个正确模式（实证）**：
- `address_registry` 订阅 `ADJUSTMENT_CREATED/LEDGER_DATASET_ACTIVATED` → 按域 `invalidate` 缓存（TB 是源，地址目录是派生）。
- `consol_trial_stale_handler` 订阅 `TRIAL_BALANCE_UPDATED` → 标母公司 consol_trial `is_stale`（子公司 TB 是源，合并数是派生）。
- `KnowledgeIndexService.incremental_update`：文档是源，向量索引是派生（文档变 → 重 embed）。
- 报表 `is_stale` 传播、`LINKAGE_STALE_CHANGED` 等 —— **全平台已建立"源变更 → 派生标脏/重建"的事件骨架**。

> 所以"联动"不用新发明，平台 EventBus + stale 传播已是基建；缺的是**把每处双源明确定义谁是权威源、谁是派生**，然后用已有事件机制把派生侧接上。

### 19.3 逐case裁定：联动同步适用吗？

| 双源 case | 类型 | 双向同步？ | 根本解决 |
|-----------|------|-----------|---------|
| **公式 4 套求值引擎** | 代码重复（算法） | ❌ 毫无意义 | **必须收敛为单内核**（§十五）。"同步 4 个算法"是伪命题——4 套对同一公式可能算出不同结果，同步什么？只能删到剩 1 套。 |
| **审计留痕 3 处** | 写扇出 | ❌ 有害 | **写到唯一哈希链**（§十七）。"同步 3 张审计表"= 每次写 3 份 = 正是现在的问题。根本解决是只写 1 处。 |
| **知识检索 3 套** | 数据派生 | ✅ 单向 | KnowledgeDocument 是源，向量索引是派生 —— 文档变更事件 → `incremental_update` 重建索引（§十六）。这就是你要的联动，且已有引擎。 |
| **底稿模板 JSON↔registry** | 数据派生 | ✅ 单向 | JSON 是源（scan 脚本生成），registry 表是派生 —— scan 时同步写 registry（§五 P1）。单向，安全。 |
| **地址库 V1/V2** | 正交（非同源） | ❌ 不适用 | 两者描述不同东西（公式编辑目录 vs 影响依赖图），不是同一数据的两份，无"同步"可言（§12.2）。 |
| **报表模板 项目↔主模板** | 双向意愿 | ⚠️ 受控传播 | 这是唯一"看似要双向"的：项目优化想回主模板、主模板更新想推项目。但**不能自动双写**——必须 ①主模板=权威源单向推送项目（diff 提示）②项目→主模板走**评审门禁**（admin 审核后才合并，非自动同步）。即"双向**受控**传播"而非"双向**自动**同步"（§12.3，仿附注 baseline）。 |

### 19.4 一句话总结

- **"改一处别处自动变"的体验** = 对的目标。
- **"两个可写源互相同步"的实现** = 错的手段（一致性地狱 + 合规不可证）。
- **正确手段** = 定一个权威源（SoT）+ 其余降为事件驱动的只读派生 + 跨主体优化走受控评审而非自动双写。
- **平台已具备**：EventBus + stale 传播骨架已在，三大内核统一（§十五~十八）正是"把多个对等源压成 1 个权威源 + N 个派生"——**收敛单源与事件联动不是二选一，而是同一个正确架构的两面**：先收敛出唯一权威源，再用联动让派生自动跟随。

> 因此 §十五~十八 的"单内核收敛"与你说的"联动同步"**并不矛盾**：收敛解决"谁是真相"，联动解决"真相变了别处怎么跟"。两者结合 = 真正的根本解决。

---

## 二十、第五轮代码实证补充（2026-05-31，公式引擎收敛细化 + 向量选型裁定）

基于 §十五 公式引擎统一架构 + §十六 检索内核统一的落地细化，第五轮 grep 实证发现以下文档未覆盖的盲区：

### 20.1 report_config.py 双引擎混用（公式收敛首批改造目标）

**实证**：`routers/report_config.py` 同一文件内同时 import 两套引擎：
```python
# report_config.py:406
from app.services.formula_parser import evaluate_formula  # 求值
from app.services.formula_engine import FormulaEngine      # 校验
```

**风险**：同一请求内，`formula_parser.evaluate_formula` 做实际求值（递归下降 AST），`FormulaEngine` 做校验/注册。两套引擎对同一公式的解析结果可能不一致（函数集差异、边界处理差异），导致"校验通过但求值错误"或反之。这比纯单引擎调用方更紧急——因为**同一请求内两套引擎交叉使用**，不一致会直接暴露给用户。

**建议**：§十五 阶段 0 的 PBT 对照基线，**优先覆盖 report_config 路由**的"同一公式经 formula_parser 求值 vs formula_engine 校验"是否一致。阶段 1 收敛时，report_config.py 应作为首批改造目标（消除同文件双引擎混用）。

### 20.2 formula_unified 实际职责澄清（底稿 Cell 公式，非报表 DSL）

**实证**：`formula_unified.py` 全仓仅 2 处调用：
- `routers/excel_html.py:683` — 底稿 HTML 渲染时执行单元格公式回写
- `routers/import_templates.py:569` — 模板导入时批量保存/执行公式

两处都是**底稿单元格级公式**（`=A1+B2`、`=SUM(C1:C10)` 类 Excel 语法），与 formula_engine/report_engine 的报表 DSL（`TB('1001','期末余额')`、`SUM_TB('10','期末余额')`、`ROW('BS-002')`）是**完全不同的语法域**。

**修正 §十五 架构**：`formula_unified` 不应简单删除或委托报表内核，而应明确为 **L3 底稿 Cell Resolver**（独立于报表 DSL 内核）。§十五 三层架构应区分：
- **报表 DSL 公式**（TB/SUM_TB/ROW/REPORT/NOTE/WP/AUX/PREV...）→ 统一内核（formula_engine 升级）
- **底稿 Cell 公式**（Excel 语法 `=SUM(A1:A10)`、`=IF(B2>0,C2,0)`）→ 独立 Cell Evaluator（formula_unified 改名为 `cell_formula_evaluator`，保持独立）

两者语法域不同（DSL 是自定义函数调用，Cell 是 Excel 兼容语法），强行统一反而引入不必要的复杂度。`formula_unified` 的"统一"命名是误导，实际是"底稿单元格公式执行器"。

### 20.3 note_formula_engine 排除出收敛范围

**实证**：`note_formula_engine.py` 包含 8 类 Validator（BalanceCheck / WideTableHorizontal / VerticalReconcile / CrossCheck / SubItemCheck / AgingTransition / CompletenessCheck / LLMReview），全部是**数据勾稽校验器**（输入数据 dict → 输出 findings list），不做公式字符串求值。

命名有误导（叫 "engine" 但不 eval 公式），但它与公式求值引擎是完全不同的关注点：
- 公式引擎：输入公式字符串 → 输出计算值（Decimal/FormulaResult）
- note_formula_engine：输入附注数据 → 输出校验发现（勾稽是否平衡）

**结论**：§十五 公式引擎收敛范围**明确排除 `note_formula_engine`**（它是 validator 不是 evaluator），避免误伤。文档 §二 已正确将其列为"周边 service"而非第 5 套引擎，本条确认该判断正确。

### 20.4 向量存储选型裁定：pgvector（非 ChromaDB）

§十六 留了"pgvector vs ChromaDB 评审"未给结论。基于实际情况裁定如下：

| 维度 | pgvector | ChromaDB |
|------|----------|----------|
| 部署 | PG 扩展（`CREATE EXTENSION vector`） | 已有 docker 容器 + ai_service 客户端 |
| 事务一致性 | 与业务数据同库同事务（删文档→向量级联删） | 独立存储，需双写+补偿 |
| 性能 | ivfflat/HNSW 索引，百万级 OK | 原生向量库，千万级 |
| 运维 | 零额外组件（PG 已有） | 多一个有状态容器 |
| 当前数据量 | 5 项目 × 6 类 ≈ 数千条 | 同左 |
| 迁移成本 | `ALTER TABLE + CREATE INDEX` | 需重写存储层 + 双写过渡 |

**裁定：选 pgvector**。理由：
1. **当前数据量极小**（数千条），pgvector 绰绰有余，无需引入额外组件
2. **事务一致性**：与业务数据同库 = 知识文件删除时向量自动级联删，无双写一致性问题（呼应 §十九 "单一权威源"原则）
3. **零额外运维**：ChromaDB 容器已部署但团队实际只用它做 health check（说明对它不熟），引入真实依赖有运维风险
4. **迁移路径最短**：`ALTER TABLE knowledge_index ADD COLUMN embedding vector(1536); CREATE INDEX idx_ki_embedding ON knowledge_index USING ivfflat (embedding vector_cosine_ops);`，现有 numpy 代码改为 `ORDER BY embedding <=> $1 LIMIT $k`（一行 SQL 替代全表扫描）

**ChromaDB 留作 Plan B**：当数据量超 100 万条（当前 ×200 倍）或需要多租户隔离时再评估迁移。§十六 VectorStore Protocol 抽象保证后续可平滑切换。

### 20.5 P0 执行顺序微调（串行递进）

§十二 建议 3 个 P0 互相独立可并行。从实际开发节奏考虑，建议**串行递进**：

| 顺序 | 方案 | 工作量 | 风险 | 理由 |
|------|------|--------|------|------|
| 1 | 12.2 地址库澄清+清死文件 | ~1 天 | 零功能影响 | 最简单、零风险、立即瘦身 33MB，提振信心 |
| 2 | 12.4(1) 知识库清旧 | ~0.5 天 | 1 处改造 | 同样简单，删 1 处降级分支 |
| 3 | 12.1 公式审计收口 | ~1.5 天 | 3 写入点改造 | 稍复杂（前端 API 不变但后端 3 处改），放最后有前两个热身 |

从"零功能影响"到"前端零改但后端 3 处改造"递进，降低首次改造的心理门槛 + 积累信心。

### 20.6 附加扫描建议：全仓懒建表清单

`formula_audit_log` 的 `ensure_table`（`CREATE TABLE IF NOT EXISTS` 绕 D6）不是孤例。建议 P0 公式审计收口时附带：

```bash
grep -rn "CREATE TABLE IF NOT EXISTS" backend/app/ --include="*.py" | grep -v migrations/ | grep -v tests/
```

产出"懒建表清单"，统一纳入 D6 迁移治理。这是一次性扫描（半小时），能暴露所有 drift detector 盲区（呼应 consol C1/C3 同类问题）。已知候选：`formula_audit_log` + 多个 consol 表（consol proposal 已记录）。

---

### 20.7 修正后的公式引擎收敛范围（精确版）

综合 §十五 + 本节 20.2/20.3 修正，公式引擎收敛的精确范围：

| 文件 | 收敛动作 | 理由 |
|------|---------|------|
| `formula_engine.py` | **升级为统一内核** | 唯一企业级特征（纯函数+Context+Result+插件注册） |
| `report_engine.py` | 求值逻辑委托内核，保留 L2 编排 | DB 取数编排有价值，求值器重复 |
| `formula_parser.py` | 递归下降解析并入内核 parse 层，删独立求值器 | 解析严谨但求值重复 |
| `formula_unified.py` | **改名 `cell_formula_evaluator`，保持独立** | 底稿 Cell 公式（Excel 语法），非报表 DSL |
| `note_formula_engine.py` | **排除，不动** | 是 validator 非 evaluator |
| `report_formula_service.py` | **排除，不动** | 是公式填充/seed，非求值 |

**收敛目标**：报表 DSL 求值器从 3 套（formula_engine + report_engine + formula_parser）→ 1 套（formula_engine 升级版）。底稿 Cell 公式 + 附注校验器各保持独立。


---

## 二十一、第六轮务实复盘：单源必单源 + 多源必联动（2026-05-31）

> 原则：该单源就必须单源（旧代码该删就删，但要小心验证无调用方再动手）；确实多源的必须做好联动（单一权威源 + 事件驱动派生同步）。不搞折中。

### 21.1 必须单源：删到只剩 1 套（旧代码删除清单）

| 问题 | 要删什么 | 删前验证 | 风险控制 |
|------|---------|---------|---------|
| **公式求值 3 套报表 DSL** | `report_engine._safe_eval_expr` 内嵌求值器 + `formula_parser.FormulaEvaluator.evaluate` 独立求值器 | §十五 阶段 0 先建 PBT 对照基线（4 引擎同一公式输出逐位对比），确认语义一致后再删 | 分阶段删（阶段1 删 report_engine 求值器 → 阶段2 删 formula_parser 求值器），每阶段回归基线全绿才继续 |
| **审计留痕 3 处** | `formula_audit_log` 表的 `ensure_table` 懒建 + 写入逻辑；`core.Log` 的 `formula_updated` 分支 | grep 确认 `formula_audit_log` 表仅 `formula_audit_log.py` GET 读取（已实证）；`core.Log formula_updated` 仅 `report_config_service.update_config` 写入 | 老表保留只读一个迁移周期（历史数据不丢），新写入统一走哈希链；前端 API 路径不变（改底层查询源） |
| **知识库旧 KnowledgeService** | `knowledge_service.py` 整个文件 + `reference_doc_service` 中的文件系统降级分支 | 已实证全仓仅 1 处调用（reference_doc_service 降级分支） | 删降级分支后 reference_doc_service 只走 DB 路径；若 DB 查询失败返空（不再 fallback 文件系统） |

**删除铁律**：
1. **删前必 grep 全仓确认 0 调用方**（排除 tests/ 和 docs/），不信文档自述
2. **删前必跑相关测试全绿**（建立"删前基线"）
3. **删后必跑同一测试集全绿**（确认无回归）
4. **大块删除用独立 commit + tag**（`pre-xxx-removal-YYYY-MM-DD`），方便回滚
5. **不要"注释掉"或"标 deprecated 永远不删"**——deprecated 超过 1 个 sprint 未删 = 永远不会删，必须在标记时同时建 task 限期删除

### 21.2 多源但正交：不联动，只澄清

| 问题 | 动作 | 不做什么 |
|------|------|---------|
| **地址库 V1/V2** | 两 router 文件头互标 `@see` 职责；V2 router tag 改为 `linkage-analysis`（非 `address-registry`） | **不合并**（正交能力强行合并会破坏各自优化空间） |
| **底稿 Cell 公式 vs 报表 DSL** | `formula_unified.py` 改名 `cell_formula_evaluator.py`；文件头标注"底稿单元格 Excel 公式，非报表 DSL" | **不统一进报表内核**（语法域不同） |

### 21.3 多源必须联动：3 处断裂点修复方案（代码实证）

以下 3 处经 grep 实证确认**联动断裂**（权威源变更后派生不更新）：

#### 21.3.1 知识文件→向量索引（🔴 最紧急，用户体验直接受损）

**断裂实证**：`knowledge_folders.py` 的 upload/update 端点写入 `KnowledgeDocument` 后，**不触发** `KnowledgeIndexService.incremental_update`。grep `incremental_update` 在非测试代码中 0 处被 knowledge_folders 调用。

**后果**：用户上传知识文件后，AI 对话（`ai_chat_service` → `semantic_search`）搜不到它——因为向量索引只覆盖 6 类业务数据，不含知识文件。

**修复**：
```python
# knowledge_folders.py — upload_document 端点末尾追加：
from app.services.knowledge_index_service import KnowledgeIndexService
index_svc = KnowledgeIndexService(db)
await index_svc.incremental_update(
    project_id=doc.project_id,  # 或 folder.project_id
    source_type="knowledge_doc",
    doc_id=str(doc.id),
    content=doc.content_text or "",
)
```

**权威源**：`KnowledgeDocument`（DB）
**派生**：`KnowledgeIndex` 向量表（embedding）
**联动机制**：CRUD 钩子直接调用（同事务，简单可靠）；未来可改 EventBus `KNOWLEDGE_DOC_UPDATED` 解耦
**工作量**：~0.5 天（含 update/delete 三个钩子 + 测试）

#### 21.3.2 底稿模板 JSON→registry 表（🟠 开发体验受损）

**断裂实证**：scan 脚本（`_scan_workpaper_templates.py`）生成 `gt_template_library.json` 后，**不写** `wp_template_registry` 表。grep `wp_template_registry` 在 scan 脚本中 0 命中。registry 表数据来源不明（疑似仅 seed 脚本首次灌入后再无更新）。

**后果**：模板库 JSON 更新（新增模板/修改分类）后，前端模板管理页（读 registry 表）看到的分类/版本/适用准则可能过时。

**修复**：scan 脚本末尾加同步逻辑：
```python
# _scan_workpaper_templates.py 末尾追加：
async def sync_registry_from_json(db: AsyncSession):
    """JSON 生成后同步写 registry 表（幂等 upsert）"""
    library = json.loads(Path("data/gt_template_library.json").read_bytes())
    for tpl in library["templates"]:
        await db.execute(
            insert(WpTemplateRegistry)
            .values(wp_code=tpl["code"], wp_name=tpl["name"], cycle=tpl["cycle_prefix"], ...)
            .on_conflict_do_update(index_elements=["wp_code"], set_={...})
        )
    await db.commit()
```

**权威源**：`gt_template_library.json`（scan 脚本生成）
**派生**：`wp_template_registry` 表（分类/版本/适用准则叠加层）
**联动机制**：scan 脚本末尾同步调用（批处理，非实时事件——因为 JSON 更新是低频离线操作）
**工作量**：~0.5 天

#### 21.3.3 报表主模板→已克隆项目（🟠 业务价值最大）

**断裂实证**：`report_config_service.update_config` 修改 standard 级配置后，**不通知**已克隆的 `project:{pid}` 配置。grep `clone_report_config` 后续无任何 EventBus 发布或 stale 标记逻辑。

**后果**：主模板公式修正后，已克隆的 N 个项目继续用旧公式出报表，审计师不知道主模板已更新。

**修复**：
```python
# report_config_service.py — update_config 末尾追加（仅 standard 级触发）：
if not config.applicable_standard.startswith("project:"):
    # 主模板变更 → 通知已克隆项目
    from app.services.event_bus import event_bus
    await event_bus.publish(EventType.REPORT_CONFIG_MASTER_UPDATED, {
        "standard": config.applicable_standard,
        "report_type": config.report_type,
        "row_code": config.row_code,
        "changed_by": actor_id,
    })

# event_handlers.py — 新增 handler：
async def _mark_cloned_configs_stale(payload):
    """主模板更新 → 已克隆项目标 stale"""
    standard = payload.details["standard"]
    # 查所有 applicable_standard LIKE 'project:%' 且 report_type+row_code 匹配的行
    # 标 is_stale=True（需 report_config 表加 is_stale 列，V039 迁移）
    ...

event_bus.subscribe(EventType.REPORT_CONFIG_MASTER_UPDATED, _mark_cloned_configs_stale)
```

**权威源**：`report_config` standard 级（soe_consolidated 等）
**派生**：`report_config` project 级（`project:{pid}` 克隆）
**联动机制**：EventBus `REPORT_CONFIG_MASTER_UPDATED` → handler 批量标 stale + 前端 banner 提示"主模板已更新，是否同步"
**工作量**：~1.5 天（含 V039 迁移 + handler + 前端 banner）

### 21.4 已正常联动的（确认无断裂，保持）

| 联动链路 | 权威源 | 派生 | 机制 | 状态 |
|---------|--------|------|------|------|
| 调整分录→地址库 V1 缓存 | DB trial_balance/adjustments | address_registry 内存缓存 | EventBus 7 类事件 → `invalidate(domain)` | ✅ 正常 |
| 调整分录→公式引擎 Redis 缓存 | DB trial_balance | FormulaEngine Redis cache | EventBus 8 类事件 → `invalidate_cache()` | ✅ 正常 |
| 枚举字典后端→前端 | `_DICTS` + DB override | useDictStore sessionStorage | `dictVersionCheck.ts` 版本校验 → 过期重拉 | ✅ 正常 |
| 子公司 TB→母公司 consol_trial | trial_balance | consol_trial.is_stale | EventBus `TRIAL_BALANCE_UPDATED` → stale handler | ✅ 正常 |

### 21.5 修正后的完整执行计划

综合 §二十（单源收敛）+ §二十一（联动修复），P0/P1 完整清单：

**P0 地基止血（~4 天，串行递进）**：
1. 地址库澄清 + 清 L1 死文件（~1 天）— 零风险热身
2. 知识库清旧 **+ 接联动**（~1 天）— 删 KnowledgeService + 知识文件→向量索引钩子
3. 公式审计收口哈希链（~1.5 天）— 3 写入点改造 + 废懒建表
4. 附带：全仓懒建表扫描清单（~0.5 天）

**P1 功能增强 + 联动补全（~6 天）**：
5. 底稿模板真源拍板 + JSON→registry 同步（~1 天）
6. 报表主模板→已克隆项目 stale 通知 + 回填评审通道（~2.5 天）
7. 知识库向量存储迁 pgvector（~1.5 天）
8. 公式引擎收敛阶段 0（PBT 对照基线 + ADR）（~1 天）

**总计 ~10 天**，P0 无外部依赖可立即启动，P1 各项互相独立可并行。


---

## 二十二、文档/文件夹级 LLM 知识库对话（核心功能需求，后续建 spec）

> 用户定位：**平台最实用的差异化能力**——把知识库从"存文件"变成"随时可问的专家"，审计师在任何程序中都能"问 AI"加速处理。

### 22.1 核心诉求

1. **任意文档/文件夹级 LLM 对话入口**：不只是全局 AI 对话，而是每个底稿、每个附注章节、每个知识库文件/文件夹都能发起上下文对话（右键/工具栏按钮）
2. **自动注入上下文**：用户不需要手动复制粘贴，系统自动把当前文档内容 + 关联知识库（同行业/同模板/同科目/同循环）作为 RAG 上下文喂给 LLM
3. **知识库最大化利用**：用户上传的参考资料（同行业审计报告、对比模板、审计准则、历史底稿）能被 AI 对话直接引用检索
4. **提升数据处理速度**：审计师在任何程序（底稿/附注/报表/试算表）中都能"问 AI"来加速填写、核对、分析、对比

### 22.2 典型使用场景

| 场景 | 用户操作 | AI 行为 |
|------|---------|---------|
| 底稿填写参考 | 打开 D2 应收账款底稿 → 点"AI 对话" | 自动注入当前底稿 parsed_data + 知识库中同行业/同科目的历史底稿 → 回答"参考去年同行业客户，应收账款减值比例通常多少" |
| 附注章节起草 | 打开货币资金附注章节 → 问"帮我起草这个章节" | 注入当前 TB 数据 + 知识库中附注模板范例 + 同行业已完成附注 → 生成初稿 |
| 模板对比 | 选中知识库"同行业审计报告"文件夹 → 问"和我当前项目报表有什么差异" | 注入文件夹下所有文档 + 当前项目报表数据 → 对比分析 |
| 准则查询 | 在任意页面 → 问"CAS 8 关于资产减值的规定" | 检索知识库中上传的准则文件 → 精准引用段落回答 |
| 底稿复核辅助 | 打开 E 类控制测试底稿 → 问"这个控制测试结论是否合理" | 注入底稿数据 + 知识库中控制测试指南 → 给出复核建议 |

### 22.3 技术前置依赖（已有基建 + 需补的联动）

| 前置 | 现状 | 需补 | 关联章节 |
|------|------|------|---------|
| RAG 引擎 | `KnowledgeIndexService` 已落地（semantic_search/build_index/incremental_update） | 无需新建 | §七 |
| 知识文件入向量索引 | 🔴 断裂（知识文件 CRUD 不触发 incremental_update） | §21.3.1 修复 | §21.3.1 |
| 向量存储性能 | PG 文本列 + numpy 全扫（O(N)） | 迁 pgvector（§20.4） | §20.4 |
| LLM 调用 | `ai_service.py` + vLLM 8100 已就绪 | 无需新建 | memory |
| 文档内容提取 | `wp_document_recognizer`/MinerU 已有 | 确保 content_text 填充率 | §七 |
| AI 内容确认流 | `wrap_ai_output_with_log` + `AIContentMustBeConfirmedRule` 已有 | 复用 | V3 Sprint 1 Req 6 |

### 22.4 初步架构设想（spec 细化时展开）

```
用户在任意页面点"AI 对话"
        │
        ▼
┌─────────────────────────────────────────────────┐
│  ContextBuilder（上下文构建器）                     │
│  ① 当前文档内容（parsed_data / content_text）      │
│  ② 关联知识库检索（semantic_search by 科目/行业/循环）│
│  ③ 项目上下文（TB/报表/附注摘要）                   │
│  ④ 用户自定义知识范围（可选文件夹/标签过滤）         │
└─────────────────┬───────────────────────────────┘
                  │ 组装 prompt（system + context + user query）
                  ▼
┌─────────────────────────────────────────────────┐
│  LLM 调用层（复用 ai_service / vLLM）              │
│  · streaming 响应                                 │
│  · token 预算控制（context window 管理）            │
│  · wrap_ai_output_with_log（审计留痕 + 确认流）     │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  前端 AI 对话面板（可嵌入任意页面的 Drawer/Panel）   │
│  · 对话历史                                       │
│  · 引用来源标注（哪个知识库文件/哪个底稿）           │
│  · "采纳"按钮 → 回写当前文档（走确认流）            │
└─────────────────────────────────────────────────┘
```

### 22.5 关键设计原则

1. **上下文自动 + 用户可控**：默认自动注入当前文档 + 关联知识，但用户可手动选择"额外参考哪些文件夹/文档"（类似 @mention 选知识范围）
2. **引用可追溯**：AI 回答必须标注引用来源（哪个知识库文件第几段 / 哪个历史底稿），审计师可验证
3. **确认流门禁**：AI 生成内容不直接写入底稿/附注，必须经用户确认（复用 `AIContentMustBeConfirmedRule`）
4. **token 预算管理**：知识库文档可能很大，需 chunk + 相关性排序 + 截断策略（top_k 最相关段落，非全文塞入）
5. **权限继承**：AI 对话只能检索用户有权限访问的知识文件（复用 KnowledgeDocument 权限模型）
6. **离线可用**：对话历史本地缓存，断网时可查看历史（不可发新问题）

### 22.6 与现有 AI 能力的关系

| 现有能力 | 定位 | 本需求扩展 |
|---------|------|-----------|
| `ai_chat_service`（全局 AI 对话） | 项目级通用对话，检索业务数据 | 扩展为**文档级对话**，注入当前文档上下文 |
| `wp_ai_services`（底稿 AI 填充） | 自动填充底稿字段 | 本需求是**交互式对话**（用户问→AI答→用户确认采纳） |
| `tsj_segmented_review_service`（TSJ 复核） | 自动分段复核出 findings | 本需求是**用户主动提问**（非自动触发） |
| `note_ai_assistant_service`（附注 AI） | 建议动态行/一致性检查 | 本需求覆盖附注但更通用（任意文档） |

**不重复造轮子**：复用 `KnowledgeIndexService.semantic_search` 做检索 + `ai_service` 做 LLM 调用 + `wrap_ai_output_with_log` 做留痕。新建的是 **ContextBuilder**（上下文组装）+ **前端对话面板**（可嵌入任意页面）。

### 22.7 实施建议

- **前置必做**（P0/P1 已规划）：§21.3.1 知识文件→向量索引联动 + §20.4 pgvector 迁移
- **spec 名称建议**：`doc-level-ai-chat`（文档级 AI 对话）
- **工作量预估**：~5-7 人天（后端 ContextBuilder + 端点 2天 / 前端对话面板 2天 / 集成测试+权限 1-2天 / Playwright UAT 1天）
- **优先级**：P1（在知识库联动修复之后，在公式引擎收敛之前——因为用户体验直接受益最大）

> 📌 后续建 spec 时以本节为需求输入，Design-First 展开 ContextBuilder 详细设计 + 前端组件方案。


---

## 二十三、底稿 AI 对话/复核弹窗 UX 改进（代码实证）

> 用户反馈：复核发现列表中"不太方便知道是哪个底稿"、"选中文档及位置坐标时不太行"。

### 23.1 现状问题（readCode 实证）

**TsjReviewFindings.vue** 当前显示：
- ✅ 有 `sheet` 名 + `cell_range`（如 `📄 Sheet1 A5:B10`）
- ✅ 有"📍 定位"按钮（emit `locate-cell` 事件）
- 🔴 **缺底稿名称/编号**：卡片头部只显示 severity + issue_type + sheet/cell，**不显示底稿名称（wp_name）或编号（wp_code）**。用户看到"📄 Sheet1 A5"不知道是哪个底稿的 Sheet1。
- 🔴 **定位跳转是 TODO**：`handleLocateCell` 只 emit 事件，注释写 `// TODO: 依赖 wp-locate-foundation 的 useCellLocate 实现实际跳转`。虽然 `wp-locate-foundation` spec 已完成（memory 记录），但 **SideStandardsTab 的 `onLocateCell` 只是再次 emit 给父组件**，未接入 `useCellLocate`。
- 🟠 **wpCode 传递链脆弱**：`SideStandardsTab` 把 `wpCode` prop 传给 `TsjReviewFindings`，但 findings 卡片模板里**不渲染 wpCode**（只用于 emit 参数）。

**SideStandardsTab.vue** 当前显示：
- 侧栏标题区只显示 `cycle: D`（推断的循环字母）+ 源文件名
- 复核按钮"🤖 用此提示词复核当前底稿"——**不显示当前底稿名称**，用户不确定复核的是哪个

### 23.2 改进方案

#### A. 复核发现卡片显示底稿标识（必做）

```vue
<!-- TsjReviewFindings.vue 卡片头部追加底稿标识 -->
<div class="gt-tsj-finding-header">
  <!-- 新增：底稿编号 + 名称 -->
  <el-tag size="small" type="primary" effect="plain" v-if="wpCode">
    📋 {{ wpCode }}
  </el-tag>
  <el-tag :type="severityTagType(item.severity)" size="small" effect="dark">
    {{ severityLabel(item.severity) }}
  </el-tag>
  ...
</div>
```

同时 `TsjFinding` interface 扩展 `wp_code?: string` + `wp_name?: string` 字段（后端 `tsj_structured_output_service` 返回时带上）。

#### B. 定位跳转接入 useCellLocate（必做）

```typescript
// SideStandardsTab.vue — onLocateCell 改为真实跳转：
import { useCellLocate } from '@/composables/useCellLocate'

const { locateCell } = useCellLocate()

function onLocateCell(target: { wpCode: string; sheet: string; cellRange: string }) {
  locateCell({
    wpCode: target.wpCode,
    sheetName: target.sheet,
    cellRef: target.cellRange,
  })
}
```

`useCellLocate` 已在 `wp-locate-foundation` spec 实现（memory 记录），支持 9 类 HTML componentType 全覆盖 + univer 委托 + 高亮幂等 3s 淡出。

#### C. 复核按钮明确显示底稿名称（体验优化）

```vue
<!-- SideStandardsTab.vue 复核按钮改为显示底稿编号 -->
<el-button ...>
  🤖 复核 {{ wpCode || '当前底稿' }}
</el-button>
```

#### D. 跨底稿复核场景（§二十二 联动）

当 §二十二 `doc-level-ai-chat` 落地后，复核发现可能来自**多个底稿**（用户在文件夹级发起对话）。此时 findings 列表需按底稿分组：

```
📋 D2-1 应收账款
  ├─ 🔴 高风险：Sheet1 B5 — 减值比例异常
  └─ 🟡 中风险：Sheet2 C10 — 期初期末不衔接

📋 D2-2 其他应收款
  └─ 🟡 中风险：Sheet1 A3 — 账龄分析缺失
```

### 23.3 后端配合改动

`tsj_structured_output_service.py` 返回的 `TsjReviewItem` 需补充：
- `wp_code: str` — 当前复核的底稿编号（从请求上下文传入）
- `wp_name: Optional[str]` — 底稿名称（可选，从 WorkingPaper.name 查）

当前 `wp_ai.py` 的 `tsj-review` 端点已有 `wpId` 路径参数，可从中查 `WorkingPaper.wp_code` + `name` 注入返回结果。

### 23.4 工作量与优先级

| 改动 | 工作量 | 优先级 |
|------|--------|--------|
| A. 卡片显示底稿编号 | ~0.5 天 | P0（用户直接痛点） |
| B. 定位跳转接入 useCellLocate | ~0.5 天 | P0（已有基建只需接线） |
| C. 复核按钮显示底稿名 | ~0.5 小时 | P0（一行改动） |
| D. 跨底稿分组 | ~1 天 | P1（依赖 §二十二） |

**建议纳入 `doc-level-ai-chat` spec 或独立小 bugfix spec `wp-ai-review-ux-fix`**。A/B/C 可立即做（无外部依赖），D 等 §二十二 落地后做。


---

## 二十四、6 spec 覆盖度对照（2026-05-31，两轮遗漏复盘后固化）

> 据本文档生成 6 个 spec（A formula-engine-unification / B retrieval-kernel-unification / C doc-level-ai-chat / D report-config-baseline / E wp-ai-review-ux-fix / F global-modules-cleanup），按梯队 A→F 实施。本节固化"哪条改进项进了哪个 spec / 未纳入及理由"，两轮逐条复盘确认。

### 已覆盖（P0 + P1 核心 = 单源/联动/澄清）

| 文档改进项 | 优先级 | spec |
|-----------|--------|------|
| 公式 4 引擎收敛单内核 + 收敛盘点 ADR | P0 | A |
| 公式审计留痕收口哈希链 | P0 | A 阶段3 |
| 公式管理覆盖底稿（合并部分已由 consol Phase2 ADR-205 完成） | P1 | A 需求8 |
| 知识库清 B 旧服务 | P0 | B 阶段1 |
| 知识文件→向量索引联动（A 接入 C） | P1 | B 阶段2 |
| 向量存储选型 pgvector | P1 | B 阶段3 |
| 文档级 LLM 对话 | 新功能 | C |
| 报表主模板回填 + 覆盖率 CI + 主模板→克隆 stale | P1 | D |
| 底稿 AI 复核 UX（编号/定位/按钮名） | bugfix | E |
| 地址库 V1/V2 澄清 + 33MB 死文件 | P0 | F |
| 底稿模板 JSON→registry 联动 + 边界澄清 | P1 | F |
| 枚举字典 _DICTS 陈旧注释 | P1 | F |
| 懒建表入 D6（account_note_mapping/consol_cell_comments） | §20.6 | F |

### 未纳入 6 spec → 已收进 spec G（global-modules-p2-polish，2026-05-31 补建）

> 为实现文档 100% 覆盖，新建第 7 个 spec **G `global-modules-p2-polish`** 收口全部 P2/P3 项（A~F 落地后启动）。

| 文档改进项 | 优先级 | 归属 |
|-----------|--------|------|
| 地址库 Redis 二级缓存 | P2 | G 阶段1（需求1） |
| 地址有效性校验接入公式保存流 | P2 | G 阶段1（需求2，与 A 互补） |
| 公式变更时间线 UI + 回滚 | P2 | G 阶段2（需求3，依赖 A） |
| 高级查询 Redis 缓存 + 流式导出 | P2/P3 | G 阶段3（需求4） |
| 枚举字典 扩展业务枚举 | P2 | G 阶段2（需求5，与 F 协调） |
| 枚举 enum_dict_overrides 入 D6 | P3 | G 阶段4（需求6.2） |
| note_template 大文件 DB 化 | P2 | G 阶段4（需求6.1，标 `*` 评估后做） |
| content_text 填充保障 | P2 | G 阶段4（需求6.3，保障 B 向量索引） |
| 底稿模板 接通生成链路 populate_parsed_data | P1 | **既存 `wp-generation-pipeline` spec**（非本批） |
| 底稿模板 入知识库 / version 联动 | P2 | version 联动已实现；入知识库归 B/G content_text |
| 国企/上市 diff 去 mock | 外部 | 卡审计师真实数据（关联 consol P-7），唯一不进 spec 项 |

### 最终覆盖结论（7 spec）

- **7 个 spec（A~G）实现盘点文档改进项 100% 覆盖**，唯一例外是「国企/上市 diff 去 mock」——卡审计师真实数据（外部依赖，文档已标"不投全力"），非工程可独立完成。
- 实施次序：A→B→C→D→E→F（核心，P0+P1）→ **G（P2/P3 体验性能，A~F 落地后）**。
- spec G 的需求3（公式时间线 UI）依赖 spec A 哈希链；需求5（枚举扩展）与 spec F 同 system_dicts.py 协调；其余互相独立。

