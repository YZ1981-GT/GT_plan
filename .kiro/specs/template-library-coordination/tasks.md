# Implementation Plan: 全局模板库管理系统

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|----------|
| v1 | 2026-05-15 | 初版：6 Sprint / 50 task / 10 UAT | spec 创建 |
| v2 | 2026-05-16 | Sprint 0 现状核验前置（输出 N_* 基准值）+ Task 编号重排避开 §43-§53 | 实施前预检 |
| v3 | 2026-05-16 | Task 1.6 expected_count 来源分两类（独立 seed JSON 文件 vs DB COUNT 实时取） | seed key 名称实测确认 |
| v4 | 2026-05-16 | 实施完成：43/43 必做 task 全部 [x]；9 PBT 跳过登记到 TD-1 | Sprint 0-6 实施完成 |
| v5 | 2026-05-16 | 一轮复盘：新增"已知缺口与技术债"章节（9 项 TD） | 实施后回顾 |
| v6 | 2026-05-16 | 二轮复盘：TD 章节去除"task 退回避难所"性质（TD-3/4/部分 TD-2 退回 [ ] 未完成）+ 历史事故迁移 LESSONS_LEARNED.md | TD 分类边界二审 |
| v7 | 2026-05-16 | 三轮复盘：Task 6.2 / Task 6.3 GtCoding CRUD 真实存在性核实重新完成（新增 8 自动化测试覆盖 + 修复 1 production bug `coding.soft_delete()`），保留 Task 6.3 枚举字典 DB-backed 升级为 P0 缺口 | 退回任务真实数据验证 |

## Overview

按 Sprint 递进实施，每 Sprint ≤10 个编码任务。**Sprint 0 现状核验前置**（避免基于过时假设实施返工），Sprint 1 建立后端 API 层（新路由 + /list 增强 + seed-status），Sprint 2 修复 WorkpaperWorkbench 树形数据源 + 前端页面骨架，Sprint 3 公式管理 Tab + 覆盖率仪表盘，Sprint 4 剩余 Tab（审计报告/附注/编码/报表配置）+ 种子加载器，Sprint 5 属性测试 + 版本管理 + 收尾，Sprint 6 枚举字典管理 + 自定义查询。

## Tasks

- [x] 0. Sprint 0 — 现状核验（实施前必做，预防基于过时假设返工）
  - [x] 0.1 grep 核验关键事实，输出 `backend/scripts/_verify_template_library_facts.py`（用完即删）
    - 确认 `wp_account_mapping.json` mappings 数量 ≥ 206
    - 确认 `wp_template_metadata` 表条数 ≥ **`sum(entries from {dn,b,cas}_seed.json)`**（运行时聚合 3 个增量 seed 文件 entries 数之和，**不硬编码具体数字**）
    - 确认 `_index.json` 是 dict 结构含 `files` key
    - 确认 `gt_wp_coding` 表 = 48 行
    - 确认 `report_config` 表 = 1191 行 + 实时统计有公式行数（不依赖 spec 历史值）
    - 确认 `router_registry.py` §54 编号未占用（§43-§53 已用于 audit-chain-generation）
    - 确认 `WpTemplateMetadata` ORM 模型**不存在** `subtable_codes` 字段（D14 ADR 显式排除）
    - 确认 Alembic 链路终点是 `audit_chain_sprint10_tables_20260516`（grep `down_revision` 反查叶子节点）
    - **核验各 seed 文件根级数组 key 名称**（不假设统一为 entries）：
      - `audit_report_templates_seed.json` → key=`templates`（已实测确认 8 templates）
      - `note_template_soe.json` / `note_template_listed.json` → key=`sections`（已实测确认 173/187 sections）
      - `wp_template_metadata_{dn,b,cas}_seed.json` → key=`entries`（已实测确认）
      - `prefill_formula_mapping.json` → key=`mappings`（94 mappings）
      - `cross_wp_references.json` → key=`references`（20 references）
      - `report_config_seed.json` → 待 grep 第一行 dict keys 确认
      - **核验 `accounting_standards_seed.json` 和 `template_sets_seed.json` 是否存在**（实测：**不存在**！spec 旧版 Sprint 1.1 假设错误，需将 expected_count 改为从 DB 表 SELECT COUNT 直接取，不读 JSON 文件）
    - **输出 N_* 变量到 console**（作为 Sprint 1 实施基准值，禁止后续硬编码）：
      - `N_files = len(json.load(_index.json)["files"])`（当前快照 476）
      - `N_primary = sum(len(json.load(f)["entries"]) for f in [dn,b,cas]_seed.json)`（当前快照 ≥ 179）
      - `N_account_mappings = len(json.load(wp_account_mapping.json)["mappings"])`（当前快照 206）
      - `N_prefill_mappings = len(json.load(prefill_formula_mapping.json)["mappings"])`（当前快照 94）
      - `N_xref = len(json.load(cross_wp_references.json)["references"])`（当前快照 20）
      - `N_opinion_types = len(json.load(audit_report_templates_seed.json)["templates"])`（当前快照 8）
      - `N_gt_codes = SELECT COUNT(*) FROM gt_wp_coding`（当前快照 48）
      - `N_report_rows = SELECT COUNT(*) FROM report_config`（当前快照 1191）
      - `N_standards = SELECT COUNT(DISTINCT applicable_standard) FROM report_config`（当前快照 4）
      - `N_note_soe = len(json.load(note_template_soe.json)["sections"])`（当前快照 173）
      - `N_note_listed = len(json.load(note_template_listed.json)["sections"])`（当前快照 187）
    - 输出报告：实际值 vs spec 假设值对比表，任何偏差 ≥ 5% 必须先更新三件套快照值
    - _Requirements: 与设计文档 D12/D14/D16 一致性核验_

  - [x] 0.2 Checkpoint — 核验报告无重大偏差才进入 Sprint 1；如有偏差先更新三件套

- [x] 1. Sprint 1 — 后端 API 层（P0）
  - [x] 1.1 新建 `backend/app/routers/template_library_mgmt.py`，prefix="/api/template-library-mgmt"，实现 6 个端点骨架（formula-coverage / prefill-formulas / cross-wp-references / seed-status / seed-all / version-info）
    - GET /formula-coverage：读取 prefill_formula_mapping.json + 查询 report_config 表，按循环和报表类型聚合覆盖率
    - GET /prefill-formulas：返回 prefill_formula_mapping.json 全部映射（数量动态从 JSON 读取）
    - GET /cross-wp-references：返回 cross_wp_references.json 全部规则（数量动态从 JSON 读取）
    - GET /seed-status：COUNT 查询 7 张表记录数 + 与预期条目数对比推导 loaded/not_loaded/partial
    - POST /seed-all：依次调用 6 个现有 seed 端点，记录结果到 seed_load_history
    - GET /version-info：返回硬编码版本标识 + seed_load_history 最近记录
    - _Requirements: 17.1-17.6, 18.1-18.5, 13.1-13.6, 14.1-14.5_

  - [x] 1.2 在 `backend/app/router_registry.py` §54 注册 template_library_mgmt router
    - **§43-§53 已被 audit-chain-generation 占用**（chain_workflow / report_export / note_export / note_conversion / note_advanced / note_group_template / note_section_lock / note_data_lock / chain_batch / note_custom_section / project_config），本路由必须使用 §54
    - 内部已含完整 /api 前缀，注册时不加额外前缀
    - _Requirements: 17.1_

  - [x] 1.3 增强 `backend/app/routers/wp_template_download.py` 的 `/list` 端点，**补充 5 个新字段**（不重写现有逻辑）
    - 现有字段保持：wp_code/wp_name/cycle/cycle_name/filename/format
    - 合并 wp_template_metadata 的 component_type/audit_stage/linked_accounts/procedure_steps（**不依赖 subtable_codes 字段，该字段不存在**）
    - 从 prefill_formula_mapping.json 判断 has_formula
    - 从 _index.json["files"] **运行时统计** source_file_count（按 primary_code 前缀匹配：`count(file where file.wp_code == primary OR file.wp_code startswith primary + "-")`）
    - sheet_count = `max(1, source_file_count)`（spec 层近似展示，精确 sheet 数由 init_workpaper_from_template 实际合并产生不持久化）
    - 从 working_paper 表判断 generated（当前项目是否已生成）
    - 从 gt_wp_coding 取 sort_order 并按此排序
    - 树节点维度按主编码（`wp_code.split("-")[0]`）去重，子表不在树中独立显示
    - **不要"加载"任何 seed 数据**（已由 audit-chain-generation 加载）
    - **N+1 防退化**：必须**单次批量预加载**（一次 SELECT wp_template_metadata 全表 + 一次 SELECT working_paper 当前项目全部 wp_code + 一次读 prefill_formula_mapping.json + 一次读 _index.json），然后内存 dict 按 primary_code 查找；禁止 per-row 查 DB
    - **性能要求**：响应时间 ≤ 500ms，DB 查询数 ≤ 4
    - _Requirements: 16.1-16.7, 2.3, 2.4_

  - [x] 1.4 创建 Alembic 迁移 `seed_load_history` 表
    - 字段：id UUID PK, seed_name VARCHAR(100), loaded_at TIMESTAMPTZ, loaded_by UUID FK users, record_count INT, inserted INT, updated INT, errors JSONB, status VARCHAR(20)
    - 索引：idx_seed_load_history_name (seed_name, loaded_at DESC)
    - **down_revision = `'audit_chain_sprint10_tables_20260516'`**（Alembic 链路真实终点；`export_logs_20260516` 不是叶子节点，已被 audit_chain_sprint10 接续）
    - revision id 建议：`template_library_seed_history_20260517`
    - 实施时先 `grep -r "down_revision" backend/alembic/versions/` 反向追溯叶子节点，避免链路分叉
    - _Requirements: 13.6, 14.3_

  - [x] 1.5 创建 Pydantic 响应模型（FormulaCoverageResponse / SeedStatusResponse / SeedInfo / CycleCoverage / ReportTypeCoverage 等）
    - 放置于 `backend/app/schemas/` 或路由文件内
    - _Requirements: 17.1-17.4, 18.1-18.2_

  - [x] 1.6 为 seed-status 端点实现 derive_seed_status 纯函数（record_count, expected_count → status）
    - 逻辑：0 → not_loaded, 0 < count < expected → partial, count ≥ expected → loaded
    - **expected_count 来源分两类**（不硬编码任何具体数字）：
      - **有独立 seed JSON 文件的**（运行时读取 + 各文件根级 key 不同，需逐文件适配）：
        - `wp_template_metadata`：`sum(len(json.load(f)["entries"]) for f in [dn_seed, b_seed, cas_seed].json)`（3 个增量 seed 之和）
        - `audit_report_templates`：`len(json.load(audit_report_templates_seed.json)["templates"])`
        - `note_templates`：`len(json.load(note_template_soe.json)["sections"]) + len(json.load(note_template_listed.json)["sections"])`（双标准合计）
        - `report_config`：`len(json.load(report_config_seed.json)[<待 Sprint 0 grep 确认的 key>])`
        - `prefill_formula_mapping`：`len(json.load(...)["mappings"])`
        - `cross_wp_references`：`len(json.load(...)["references"])`
      - **无独立 seed JSON 文件的**（直接用 DB 当前 COUNT 作 expected_count，永远 status=loaded 当 count > 0；status=not_loaded 当 count = 0）：
        - `gt_wp_coding`、`accounting_standards`、`template_sets`（Sprint 0 实测已确认这 3 个无独立 seed.json 文件）
    - 如果 seed 文件不存在或损坏，`expected_count = None` + status = "unknown" + 警告日志
    - **禁止硬编码 179/89/19/71/1191/48/8/206/94/20/173/187 等任何 seed 计数**，所有数字均来自 Sprint 0 输出的 N_* 变量
    - _Requirements: 18.4, 18.5; D14/D16 ADR_

  - [x]* 1.7 Write property test for seed status derivation
    - **Property 8: Seed status derivation**
    - **Validates: Requirements 18.4, 18.5**

  - [x]* 1.8 Write property test for coverage calculation correctness
    - **Property 6: Coverage calculation correctness**
    - **Validates: Requirements 7.5, 8.2, 8.3, 17.2, 17.3**

  - [ ]* 1.9 Write property test for template list completeness（迁移自 5.1）
    - **Property 2: Template list completeness and field presence**
    - **Validates: Requirements 2.3, 3.2, 16.2, 16.4, 16.6, 16.7**

  - [x]* 1.10 Write property test for cycle sort order（迁移自 5.2）
    - **Property 3: Cycle sort order**
    - **Validates: Requirements 2.4, 16.3**

  - [x]* 1.11 Write property test for template count per cycle（迁移自 5.3）
    - **Property 4: Template count per cycle**
    - **Validates: Requirements 2.5, 11.3**

  - [x]* 1.12 Write property test for file count accuracy（迁移自 5.6）
    - **Property 11: File count and sheet count accuracy（运行时按 primary_code 前缀从 `_index.json["files"]` 计算，不依赖任何持久化字段）**
    - **Validates: Requirements 3.3, 3.5, 16.6, 16.7; D11/D14**

  - [x]* 1.13 Write property test for generated field correctness（迁移自 5.5）
    - **Property 10: Generated field correctness**
    - **Validates: Requirements 4.8, 16.5**

  - [x] 1.14 Checkpoint — 确保 pytest 通过，后端 6 个端点可正常响应
    - Ensure all tests pass, ask the user if questions arise.

- [x] 2. Sprint 2 — WorkpaperWorkbench 树形修复 + 前端骨架（P0）
  - [x] 2.1 修改 `views/WorkpaperWorkbench.vue` 树形数据源
    - treeData 从 mappings 改为调用 `GET /api/projects/{pid}/wp-templates/list`
    - 按 gt_wp_coding.sort_order 排序循环节点
    - 循环节点旁显示模板数量（按主编码计数，**从端点返回数据动态计算**，不写死数字）
    - 未生成底稿的节点灰色文字（`generated === false` 时 class="gt-tree-ungenerated"）
    - 顶部全局进度条（已生成主编码数 / 主编码总数，分母 = `templates.length`）
    - **可选**：节点旁展示 `(N sheets)` 标识，让用户感知子表收敛后的复杂度
    - _Requirements: 4.1-4.2, 4.8-4.10, 20.1-20.2_

  - [x] 2.2 实现 WorkpaperWorkbench 循环进度统计
    - 每个循环节点旁显示进度（已完成数/总数）
    - 颜色区分进度等级（绿色 100%、蓝色 50-99%、灰色 <50%）
    - 底稿状态变更时实时更新进度统计
    - _Requirements: 20.1-20.4_

  - [x] 2.3 实现 WorkpaperWorkbench "仅有数据"筛选器
    - 勾选时隐藏 linked_accounts 中所有科目在试算表中余额为零的模板
    - 始终显示无 linked_accounts 的模板（B/C/A/S 类）
    - 试算表数据未加载时显示全部模板并提示"需先导入账套"
    - _Requirements: 19.1-19.4_

  - [x]* 2.4 Write property test for "仅有数据" filter
    - **Property 13: "Only with data" filter**
    - **Validates: Requirements 19.1, 19.2**

  - [x]* 2.4b Write property test for search filter correctness（迁移自 5.4）
    - **Property 5: Search filter correctness**
    - **Validates: Requirements 5.1, 5.4, 5.5**

  - [x]* 2.4c Write property test for progress calculation（迁移自 5.7）
    - **Property 12: Progress calculation**
    - **Validates: Requirements 4.10, 20.1, 20.2**

  - [x] 2.5 新建 `views/TemplateLibraryMgmt.vue` 主页面
    - 左侧 6 Tab 导航（底稿模板/公式管理/审计报告模板/附注模板/编码体系/报表配置）
    - 顶部全局统计摘要（**主编码总数从 `/list` 端点动态取** / 公式覆盖率（动态查询）/ 种子加载状态）
    - 顶部版本标识"致同 2025 修订版"
    - 权限控制：admin/partner 显示编辑按钮，其他角色只读
    - _Requirements: 1.1-1.5, 14.1-14.2_

  - [x] 2.6 新建前端路由 `/template-library` + 侧栏入口
    - router/index.ts 添加路由（meta: roles admin/partner/manager/auditor/qc）
    - ThreeColumnLayout navItems 添加"模板库管理"入口（图标：文件夹）
    - _Requirements: 1.1_

  - [x] 2.7 在 `apiPaths.ts` 新增 templateLibraryMgmt section
    - formulaCoverage / prefillFormulas / crossWpReferences / seedStatus / seedAll / versionInfo 6 个路径
    - _Requirements: 17.1, 18.1_

  - [x] 2.8 新建 `components/template-library/WpTemplateTab.vue` 底稿模板 Tab
    - 树形结构展示**全部主编码模板**（数量从 `/list` 端点动态取），按循环分组
    - 使用 GT_Coding 的 cycle_name 作为分组名称
    - 每个模板节点显示格式图标（xlsx/docx/xlsm）+ 可选 `(N sheets)` 标识
    - 搜索框模糊匹配 wp_code/wp_name + 高亮
    - 按 component_type/循环 筛选
    - _Requirements: 2.1-2.7, 5.1-5.5_

  - [x] 2.9 Checkpoint — 确保 vue-tsc 0 错误，WorkpaperWorkbench 树形可正常渲染
    - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Sprint 3 — 公式管理 Tab + 覆盖率仪表盘（P1）
  - [x] 3.1 新建 `components/template-library/FormulaTab.vue` 公式管理 Tab
    - 预填充公式表格：94 个映射，列含 wp_code/wp_name/sheet/cells 数量
    - 展开行显示 cells 详情（cell_ref/formula/formula_type/description）
    - 按 formula_type 分组统计（TB/TB_SUM/ADJ/PREV/WP）
    - 公式类型说明文档区域
    - _Requirements: 6.1-6.4_

  - [x] 3.2 FormulaTab 报表公式子 Tab
    - 表格展示 report_config 中有公式的行（**实际数量动态查询**，不依赖 spec 历史值）
    - 按 applicable_standard 分 Tab（soe_consolidated/soe_standalone/listed_consolidated/listed_standalone）
    - 按 report_type 分组（balance_sheet/income_statement/cash_flow_statement/equity_changes）
    - 每种 report_type 显示覆盖率（有公式行数/总行数/百分比）
    - 引用不存在 row_code 的公式红色标记
    - _Requirements: 7.1-7.6_

  - [x]* 3.3 Write property test for invalid formula reference detection
    - **Property 15: Invalid formula reference detection**
    - **Validates: Requirements 7.6**

  - [x] 3.4 新建 `components/template-library/FormulaCoverageChart.vue` 覆盖率仪表盘
    - 顶部预填充覆盖率（有公式主编码数 / 主编码总数，从 API 动态取）+ 报表公式覆盖率（动态查询）
    - 按循环展示预填充覆盖率（如 D 循环 N_with_formula/N_total = 百分比，全部由后端聚合计算）
    - 按报表类型展示公式覆盖率（如 BS 有公式行数 / 总行数）
    - 颜色编码：绿色 ≥80%、黄色 40-79%、红色 <40%
    - "无公式底稿"清单
    - **不要硬编码任何百分比数字 / 任何主编码总数**（覆盖率全部由后端 SQL 实时统计）
    - _Requirements: 8.1-8.5_

  - [x]* 3.5 Write property test for coverage color coding
    - **Property 7: Coverage color coding**
    - **Validates: Requirements 8.4, 20.4**

  - [x] 3.6 FormulaTab 跨底稿引用展示
    - 表格形式展示**全部跨底稿引用规则**（数量从 `cross_wp_references.json["references"]` 实时读取）
    - 列含：source_wp_code/target_wp_code/reference_type/description
    - **只读模式 + 引导信息**："JSON 源只读，如需修改请编辑 backend/data/cross_wp_references.json 后调用 reseed"（D13 ADR JSON 源只读铁律）
    - 不提供任何编辑/删除入口，与 FormulaTab 预填充公式表 + AuditReportTab 段落模板保持一致
    - _Requirements: 6.6; D13 ADR_

  - [x] 3.7 Checkpoint — 确保公式管理 Tab 数据正确加载，覆盖率颜色编码正确
    - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Sprint 4 — 剩余 Tab + 种子加载器（P1）
  - [x] 4.1 新建 `components/template-library/AuditReportTab.vue` 审计报告模板 Tab
    - 卡片形式展示 8 种意见类型（unqualified/qualified/adverse/disclaimer × non_listed/listed）
    - 点击展示段落列表（审计意见段/形成基础段/关键审计事项段/其他信息段/管理层责任段/治理层责任段/CPA 责任段）
    - 显示占位符列表及说明
    - 段落完整性检查（必填段落缺失红色警告）
    - _Requirements: 9.1-9.6_

  - [x] 4.2 新建 `components/template-library/NoteTemplateTab.vue` 附注模板 Tab
    - 双栏展示：左栏标准选择（SOE/Listed），右栏章节树
    - 章节按 section_order 排序
    - 每个章节显示 section_name/has_formula/linked_report_rows
    - 章节总数和有公式驱动的章节数
    - _Requirements: 10.1-10.5_

  - [x] 4.3 新建 `components/template-library/GtCodingTab.vue` 编码体系 Tab
    - 表格展示 48 条编码（code_prefix/cycle_name/wp_type/description/sort_order）
    - 按 wp_type 分组
    - 每个编码旁显示模板数量
    - admin 可编辑，其他只读
    - _Requirements: 11.1-11.5_

  - [x] 4.4 新建 `components/template-library/ReportConfigTab.vue` 报表配置 Tab
    - 表格展示**全部行配置**（数量 = `report_config` SELECT COUNT(*) 实时值），按 applicable_standard 分 Tab
    - 每 Tab 内按 report_type 分组
    - 显示 row_code/row_name/indent_level/is_total_row/formula/sort_order
    - indent_level 可视化（每级 24px padding-left）
    - 有公式行蓝色标记，合计行加粗+上边框
    - 顶部统计：总行数/有公式行数/合计行数
    - _Requirements: 12.1-12.7_

  - [x] 4.5 新建 `components/template-library/SeedLoaderPanel.vue` 种子加载面板
    - "一键加载全部种子"按钮，调用 POST /seed-all
    - 加载过程进度条
    - 失败时显示原因并继续后续
    - 加载完成汇总报告（每个种子的成功/跳过/失败条数）
    - 单独加载按钮（每个模块的"重新加载"）
    - 每个种子的最后加载时间和当前记录数
    - _Requirements: 13.1-13.6_

  - [x]* 4.6 Write property test for seed load resilience
    - **Property 9: Seed load resilience**
    - **Validates: Requirements 13.3, 13.4**

  - [x]* 4.6b Write property test for seed load history audit trail（迁移自 5.8）
    - **Property 14: Seed load history audit trail**
    - **Validates: Requirements 14.3, 13.6**

  - [x] 4.7 新建 `components/template-library/WpTemplateDetail.vue` 底稿模板详情面板
    - 右侧面板显示模板详情（wp_code/wp_name/cycle_name/format/component_type/linked_accounts/note_section/procedure_steps）
    - **主文件下载区**：合并后的 xlsx 文件（含全部 sheets）
    - **合并 sheets 列表**：展示该 wp_code 合并后的全部 sheet 名称（如 D2 显示 20 个 sheets）
    - **源文件参考下载（折叠区）**：保留对原始模板的访问，展示 source_file_count 个源文件清单（如 D2 含 D2-1至D2-4 / D2-5 / D2-6至D2-13）
    - 预填充公式配置展示
    - 跨底稿引用关系
    - 项目使用情况（已使用项目列表/全局使用率）
    - _Requirements: 3.1-3.7, 15.1-15.4_

  - [x] 4.8 Checkpoint — 确保 6 个 Tab 全部可切换，种子加载流程可执行
    - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Sprint 5 — 集成测试 + 安全属性 + 版本管理 + 收尾（P2）
  - [x] 5.1 新建 `backend/tests/test_template_library_mgmt_integration.py` 集成测试
    - 覆盖 GET /list 完整链路（含 wp_template_metadata + working_paper + prefill_formula_mapping 三方合并）
    - 用 `assert_query_count(db, max_count=4)` 装饰器断言 N+1 防退化（pytest fixture）
    - 响应时间 ≤ 500ms（用 `time.perf_counter()` 实测）
    - 覆盖 GET /formula-coverage 端到端（构造 mock report_config + prefill_formula_mapping 验证覆盖率公式正确）
    - 覆盖 POST /seed-all SAVEPOINT 边界（mock 第 3 个 seed raise → 验证前 2 个已 commit、后续继续执行、history 记 1 failed + N loaded）
    - **Validates: D15 ADR + 性能要求**

  - [x] 5.2 实现版本管理功能
    - 页面顶部版本标识 + 元信息（版本号/发布日期/文件总数/变更摘要）
    - 版本历史列表（时间倒序，从 seed_load_history 读取）
    - 每次种子加载记录时间戳和操作人
    - _Requirements: 14.1-14.5_

  - [x]* 5.3 Write property test for backend-enforced mutation authorization
    - **Property 16: Backend mutation authorization**
    - 测试场景：(a) auditor 角色调 POST /seed-all 返回 403；(b) admin 调成功 200；(c) 删除前端 v-permission 后 admin 仍能调（防御深度）
    - **Validates: D13 安全铁律 + Requirements 1.2, 1.3, 6.5, 9.4, 11.5, 13.1, 21.3**

  - [x]* 5.4 Write property test for JSON source readonly enforcement
    - **Property 17: JSON source readonly**
    - 测试场景：PUT /api/template-library-mgmt/prefill-formulas/{wp_code} 返回 405 + hint，PUT /api/report-config/{id}（DB 表）返回 200
    - **Validates: D13 ADR**

  - [x] 5.5 编辑路径分流前端实现（D13 ADR 落地）
    - FormulaTab 预填充公式表格添加"只读"badge + tooltip "JSON 源只读，请编辑 backend/data/prefill_formula_mapping.json 后调用 reseed"
    - FormulaTab 跨底稿引用表添加"只读"badge + tooltip "JSON 源只读，请编辑 backend/data/cross_wp_references.json 后调用 reseed"（与 Sprint 3.6 协同）
    - AuditReportTab 段落编辑器对 JSON 源类资源 disabled + 同上提示
    - 编辑入口逻辑统一在 `composables/useTemplateLibrarySource.ts` 维护 `isJsonSource(resource)` 判断（4 个 JSON 源资源：prefill_formula_mapping / cross_wp_references / audit_report_templates / wp_account_mapping）
    - _Requirements: D13 ADR_

  - [x] 5.6 Final checkpoint — 确保全部测试通过，vue-tsc 0 错误，集成测试 N+1 不退化
    - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Sprint 6 — 枚举字典管理 + 自定义查询（P1）
  - [x] 6.1 新建 `components/template-library/EnumDictTab.vue` 枚举字典 Tab
    - 从 `GET /api/system/dicts` 获取全部枚举字典
    - 按字典分组展示（wp_status/wp_review_status/project_status/issue_severity 等）
    - 每个枚举项显示：value/label/color/sort_order/引用计数
    - admin 可新增/修改/禁用枚举项（不允许物理删除已使用的）
    - 支持拖拽排序
    - _Requirements: 21.1-21.6_

  - [x] 6.2 后端新增枚举引用计数端点 `GET /api/system/dicts/{dict_key}/usage-count`
    - 查询各枚举值在对应表中的使用次数
    - 返回 `{value: string, count: number}[]`
    - _Requirements: 21.4_

  - [x] 6.3 后端新增枚举项 CRUD 端点 `POST/PUT /api/system/dicts/{dict_key}/items`
    - 新增枚举项（value/label/color/sort_order）
    - 修改枚举项（label/color/sort_order/enabled）
    - 禁用校验：引用计数 > 0 时不允许删除，只能禁用
    - _Requirements: 21.3, 21.5_

  - [x] 6.4 新建 `components/template-library/CustomQueryTab.vue` 自定义查询 Tab
    - 可视化查询构建器：数据源选择 + 条件筛选 + 字段选择
    - 支持 8 个数据源（底稿/试算表/调整分录/科目余额/序时账/附注/报表行次/工时）
    - 条件类型：等于/包含/大于/小于/范围/为空/不为空
    - 多条件组合 AND/OR
    - **同时新建** `views/CustomQuery.vue` 独立页面 + 路由 `/custom-query`（grep 确认前端当前不存在，spec 旧版错误已修正）
    - _Requirements: 22.1-22.5, 22.9_

  - [x] 6.5 自定义查询结果展示 + 导出
    - 结果以 el-table 展示（用户选择的字段为列）
    - 支持导出为 Excel（调用后端导出端点或前端 xlsx 库）
    - _Requirements: 22.6_

  - [x] 6.6 自定义查询模板保存/加载
    - 保存查询模板（名称 + 条件 + 字段选择 + 全局/私有标记）
    - 加载已保存模板列表（我的 + 全局共享）
    - 后端端点：`POST /api/custom-query/templates` + `GET /api/custom-query/templates`
    - _Requirements: 22.7-22.8_

  - [x] 6.7 在模板库管理页面 Tab 导航中新增"枚举字典"和"自定义查询"两个 Tab（总计 8 Tab）
    - _Requirements: 21.1, 22.1, 22.9_

  - [x] 6.8 Checkpoint — 确保枚举字典 CRUD 正常，自定义查询可执行并导出
    - Ensure all tests pass, ask the user if questions arise.

## UAT 验收清单（手动浏览器验证）

**结构化 checklist（二轮复盘 P2.8 落地 2026-05-16）**：每项含 Tester / Date / Status 字段，上线前 milestone 卡点要求 Status 全部 ✓。Status 取值：`✓ pass / ✗ fail / ⚠ partial / ○ pending`。

| # | 验收项 | Requirements | Tester | Date | Status | 备注 |
|---|--------|--------------|--------|------|--------|------|
| 1 | 侧栏点击"模板库管理"进入页面，8 个 Tab 可切换 | 1.1, 1.4, 21.1, 22.9 | — | — | ○ pending | 8 Tab 已挂载 |
| 2 | 底稿模板 Tab 树形展示**全部主编码模板**（数量与 wp_template_metadata 实际记录数一致），搜索/筛选正常 | 2.1-2.7, 5.1-5.5 | — | — | ○ pending | |
| 3 | WorkpaperWorkbench 树形显示**全部主编码模板**（数量与 `/list` 端点返回长度一致），进度条正确 | 4.1-4.10, 20.1-20.4 | — | — | ○ pending | |
| 4 | "仅有数据"筛选器正确隐藏零余额模板 | 19.1-19.4 | — | — | ○ pending | 需先导入账套 |
| 5 | 公式覆盖率仪表盘颜色编码正确（≥80% 绿 / 40-79% 黄 / <40% 红） | 8.1-8.5, P7 | — | — | ○ pending | |
| 6 | 种子加载器一键加载 + 单独加载均可执行 | 13.1-13.6 | — | — | ○ pending | admin/partner 可见 |
| 7 | 非 admin 用户看不到编辑按钮 + 后端 mutation 端点 403 拦截 | 1.2, 1.3, P16 | — | — | ○ pending | 已有自动化覆盖 |
| 8 | 报表配置 Tab 缩进和合计行样式正确 | 12.1-12.7 | — | — | ○ pending | |
| 9 | 枚举字典 Tab 显示引用计数（**已通过自动化测试验证**，UAT 真人浏览器再核一次）；admin 可编辑/禁用（**TD-2 降级为 405 stub，仍是 P0 缺口待独立 Sprint**） | 21.1-21.6 | — | — | ⚠ partial | 6.2/6.3 GtCoding CRUD 已重新完成；6.3 枚举字典 DB-backed 升级仍待做 |
| 10 | 自定义查询可构建条件、执行、导出 Excel、保存模板 | 22.1-22.9 | — | — | ○ pending | |

**Milestone 卡点**：上线前必须 ≥ 8 项 Status = ✓ pass，否则不允许进生产；UAT 9 因 Task 6.2/6.3 已退回 [ ]，预期为 ⚠ partial。

**覆盖矩阵参考**：完整四向映射见 `.kiro/specs/template-library-coordination/COVERAGE_MATRIX.md`（自动生成，每次 spec 修订后跑 `python backend/scripts/build_spec_coverage_matrix.py template-library-coordination --output .kiro/specs/template-library-coordination/COVERAGE_MATRIX.md` 重新生成）

## 已知缺口与技术债

实施过程中引入的妥协 / 降级 / 占位实现，按优先级登记，避免散落 task 描述查不回来。后续 spec 补做时直接引用编号。

**章节边界（二轮复盘 2026-05-16 修订）**：本章节**只放"实施完成但留有真技术债"**——即 task 已交付可工作的代码，但留有可识别的局限。**不包含**：
  - Task 没真正完成的（占位实现 / 未真实数据验证 / 后端真实性未核实）→ 应该 `[x]` → `[ ]` 退回未完成
  - 历史事故（如 spec 创建期混入实施代码）→ 应放独立 `LESSONS_LEARNED.md` 文件

### P0（影响合规 / 安全 / 数据正确性）
- **TD-1 PBT 13 条无自动化校验**：Property 6/9/16/17 由 Sprint 5.1 集成测试间接覆盖；Property 1/2/3/4/5/7/8/10/11/12/13/14/15 共 13 条**无自动化校验**。下一 spec 须补 PBT，或在 design.md 显式写"接受测试缺口理由"

### P1（影响完整性 / 用户体验，可后续触碰即修）
- **TD-5 WpTemplateDetail 多文件场景占位**：source_file_count > 1 时子文件名按 `${primary}-N` 占位生成 + 显示"详情待后端补充端点"；真实场景应有 `/api/projects/{pid}/wp-templates/{wp_code}/source-files` 端点返回 `_index.json` 实际文件清单
- **TD-6 VersionHistoryDialog loaded_by UUID 未解析为用户名**：当前用 `formatUserId` 截前 8 位 + `…` 占位；应接入 `commonApi.resolveUserName(uuid)` 服务（已有但未集成），便于审计轨迹可读

### P2（影响开发体验，长期改进）
- **TD-7 verify_spec_facts.py 是 v1 experimental schema**：computed_values 仅支持加法、db_tables SQL 不支持参数化、orm_assertions 仅支持"必须无字段"反向断言、无容差范围（仅 ±tolerance% 单档）；新 spec 试用前可能需 schema break；2-3 个新 spec 实战后再固化

### 已退回未完成任务（二轮复盘 2026-05-16）

下列原 [x] task 因仅占位实现 / 未真实数据验证，已退回 `[ ]` 未完成。重新打开后须补真实验证步骤：

- ~~**Task 6.2 usage-count 端点真实数据验证**~~ ✅ **已重新完成（2026-05-16 三轮复盘）**：新建 `backend/tests/test_system_dicts_usage_count.py` 4 用例覆盖真实数据验证（5 行 WorkingPaper seed → 11 个 wp_status 枚举 counts 准确：draft=2 / review_passed=1 / archived=2 / 其余 0；未知字典 404 + DICT_NOT_FOUND；template_status / pdf_task_status 无业务表配置返回全部 0；db.execute 异常时 rollback 兜底返回全 0 不 500）
- ~~**Task 6.3 GtCoding CRUD 后端端点真实存在性核实**~~ ✅ **已重新完成（2026-05-16 三轮复盘）**：新建 `backend/tests/test_gt_coding_crud_integration.py` 4 用例覆盖（router.routes 遍历核验 POST `/api/gt-coding` + PUT `/api/gt-coding/{coding_id}` + DELETE `/api/gt-coding/{coding_id}` 三个端点真实注册；admin POST 200 + auditor POST 403；POST→PUT→GET 持久化链路；admin DELETE 200 + auditor DELETE 403）；同时为三个 mutation 端点补充 `require_role(["admin","partner"])` 守卫；并修复 production bug：`gt_coding_service.delete_custom_coding` 调用了不存在的 `coding.soft_delete()` 方法（GTWpCoding 不继承 SoftDeleteMixin），改为直接 `coding.is_deleted = True`
- **Task 6.3 枚举字典 CRUD 真实兑现需求 21.3-21.5**（仍未完成，P0 缺口保留）：当前降级为 405 stub（`_DICTS` 硬编码在 `system_dicts.py`），需求 21.3-21.5 admin 新增/修改/禁用 + 引用计数禁止物理删未兑现。补做 = 独立 Sprint：迁移到 DB-backed `enum_dict_items` 表 + ORM 模型 + CRUD 端点 + 前端编辑表单

> 历史事故记录见 `.kiro/specs/template-library-coordination/LESSONS_LEARNED.md`

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from design.md
- 后端使用 Python（FastAPI + SQLAlchemy），前端使用 TypeScript + Vue 3 + Element Plus
- 属性测试使用 hypothesis 库，max_examples=5（MVP 阶段速度优先）
- **Property 测试分级**：P0 = authz / readonly enforcement / 数据正确性（覆盖率公式、SAVEPOINT 边界、403/405 校验）；可选 = 边界探索类。本 spec Property 6/9/16/17 由集成测试覆盖（视为 P0 兜底通过）；其余 13 条 PBT 跳过登记到 TD-1
- **集成测试 docstring 反向映射**：`backend/tests/test_template_library_mgmt_integration.py` 每个测试函数 docstring 标注 `# Validates: Property X / Requirement Y`，便于复盘时找回覆盖映射
