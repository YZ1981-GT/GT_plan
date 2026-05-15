# Implementation Plan: 全局模板库管理系统

## Overview

按 Sprint 递进实施，每 Sprint ≤10 个编码任务。Sprint 1 建立后端 API 层（新路由 + /list 增强 + seed-status），Sprint 2 修复 WorkpaperWorkbench 树形数据源 + 前端页面骨架，Sprint 3 公式管理 Tab + 覆盖率仪表盘，Sprint 4 剩余 Tab（审计报告/附注/编码/报表配置）+ 种子加载器，Sprint 5 属性测试 + 版本管理 + 收尾，Sprint 6 枚举字典管理 + 自定义查询。

## Tasks

- [ ] 1. Sprint 1 — 后端 API 层（P0）
  - [ ] 1.1 新建 `backend/app/routers/template_library_mgmt.py`，prefix="/api/template-library-mgmt"，实现 6 个端点骨架（formula-coverage / prefill-formulas / cross-wp-references / seed-status / seed-all / version-info）
    - GET /formula-coverage：读取 prefill_formula_mapping.json + 查询 report_config 表，按循环和报表类型聚合覆盖率
    - GET /prefill-formulas：返回 prefill_formula_mapping.json 全部 94 个映射
    - GET /cross-wp-references：返回 cross_wp_references.json 全部 20 条规则
    - GET /seed-status：COUNT 查询 7 张表记录数 + 与预期条目数对比推导 loaded/not_loaded/partial
    - POST /seed-all：依次调用 6 个现有 seed 端点，记录结果到 seed_load_history
    - GET /version-info：返回硬编码版本标识 + seed_load_history 最近记录
    - _Requirements: 17.1-17.6, 18.1-18.5, 13.1-13.6, 14.1-14.5_

  - [ ] 1.2 在 `backend/app/router_registry.py` §43 注册 template_library_mgmt router
    - 内部已含完整 /api 前缀，注册时不加额外前缀
    - _Requirements: 17.1_

  - [ ] 1.3 增强 `backend/app/routers/wp_template_download.py` 的 `/list` 端点，返回新增字段
    - 合并 wp_template_metadata 的 component_type/audit_stage/linked_accounts/procedure_steps
    - 从 prefill_formula_mapping.json 判断 has_formula
    - 从 _index.json 统计 file_count
    - 从 working_paper 表判断 generated（当前项目是否已生成）
    - 从 gt_wp_coding 取 sort_order 并按此排序
    - _Requirements: 16.1-16.6, 2.3, 2.4_

  - [ ] 1.4 创建 Alembic 迁移 `seed_load_history` 表
    - 字段：id UUID PK, seed_name VARCHAR(100), loaded_at TIMESTAMPTZ, loaded_by UUID FK users, record_count INT, inserted INT, updated INT, errors JSONB, status VARCHAR(20)
    - 索引：idx_seed_load_history_name (seed_name, loaded_at DESC)
    - _Requirements: 13.6, 14.3_

  - [ ] 1.5 创建 Pydantic 响应模型（FormulaCoverageResponse / SeedStatusResponse / SeedInfo / CycleCoverage / ReportTypeCoverage 等）
    - 放置于 `backend/app/schemas/` 或路由文件内
    - _Requirements: 17.1-17.4, 18.1-18.2_

  - [ ] 1.6 为 seed-status 端点实现 derive_seed_status 纯函数（record_count, expected_count → status）
    - 逻辑：0 → not_loaded, 0 < count < expected → partial, count ≥ expected → loaded
    - expected_count 从 seed 文件读取或硬编码（report_config=1191, gt_wp_coding=48, wp_template_metadata=179, audit_report_templates=8, note_templates=2, accounting_standards=166, template_sets=6）
    - _Requirements: 18.4, 18.5_

  - [ ]* 1.7 Write property test for seed status derivation
    - **Property 8: Seed status derivation**
    - **Validates: Requirements 18.4, 18.5**

  - [ ]* 1.8 Write property test for coverage calculation correctness
    - **Property 6: Coverage calculation correctness**
    - **Validates: Requirements 7.5, 8.2, 8.3, 17.2, 17.3**

  - [ ] 1.9 Checkpoint — 确保 pytest 通过，后端 6 个端点可正常响应
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 2. Sprint 2 — WorkpaperWorkbench 树形修复 + 前端骨架（P0）
  - [ ] 2.1 修改 `views/WorkpaperWorkbench.vue` 树形数据源
    - treeData 从 mappings 改为调用 `GET /api/projects/{pid}/wp-templates/list`
    - 按 gt_wp_coding.sort_order 排序循环节点
    - 循环节点旁显示模板数量（如"D 销售循环 (17)"）
    - 未生成底稿的节点灰色文字（`generated === false` 时 class="gt-tree-ungenerated"）
    - 顶部全局进度条（已生成底稿数/180）
    - _Requirements: 4.1-4.2, 4.8-4.10, 20.1-20.2_

  - [ ] 2.2 实现 WorkpaperWorkbench 循环进度统计
    - 每个循环节点旁显示进度（已完成数/总数）
    - 颜色区分进度等级（绿色 100%、蓝色 50-99%、灰色 <50%）
    - 底稿状态变更时实时更新进度统计
    - _Requirements: 20.1-20.4_

  - [ ] 2.3 实现 WorkpaperWorkbench "仅有数据"筛选器
    - 勾选时隐藏 linked_accounts 中所有科目在试算表中余额为零的模板
    - 始终显示无 linked_accounts 的模板（B/C/A/S 类）
    - 试算表数据未加载时显示全部模板并提示"需先导入账套"
    - _Requirements: 19.1-19.4_

  - [ ]* 2.4 Write property test for "仅有数据" filter
    - **Property 13: "Only with data" filter**
    - **Validates: Requirements 19.1, 19.2**

  - [ ] 2.5 新建 `views/TemplateLibraryMgmt.vue` 主页面
    - 左侧 6 Tab 导航（底稿模板/公式管理/审计报告模板/附注模板/编码体系/报表配置）
    - 顶部全局统计摘要（模板总数/公式覆盖率/种子加载状态）
    - 顶部版本标识"致同 2025 修订版"
    - 权限控制：admin/partner 显示编辑按钮，其他角色只读
    - _Requirements: 1.1-1.5, 14.1-14.2_

  - [ ] 2.6 新建前端路由 `/template-library` + 侧栏入口
    - router/index.ts 添加路由（meta: roles admin/partner/manager/auditor/qc）
    - ThreeColumnLayout navItems 添加"模板库管理"入口（图标：文件夹）
    - _Requirements: 1.1_

  - [ ] 2.7 在 `apiPaths.ts` 新增 templateLibraryMgmt section
    - formulaCoverage / prefillFormulas / crossWpReferences / seedStatus / seedAll / versionInfo 6 个路径
    - _Requirements: 17.1, 18.1_

  - [ ] 2.8 新建 `components/template-library/WpTemplateTab.vue` 底稿模板 Tab
    - 树形结构展示 180 个 wp_code，按循环分组
    - 使用 GT_Coding 的 cycle_name 作为分组名称
    - 每个模板节点显示格式图标（xlsx/docx/xlsm）
    - 搜索框模糊匹配 wp_code/wp_name + 高亮
    - 按 component_type/循环 筛选
    - _Requirements: 2.1-2.7, 5.1-5.5_

  - [ ] 2.9 Checkpoint — 确保 vue-tsc 0 错误，WorkpaperWorkbench 树形可正常渲染
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Sprint 3 — 公式管理 Tab + 覆盖率仪表盘（P1）
  - [ ] 3.1 新建 `components/template-library/FormulaTab.vue` 公式管理 Tab
    - 预填充公式表格：94 个映射，列含 wp_code/wp_name/sheet/cells 数量
    - 展开行显示 cells 详情（cell_ref/formula/formula_type/description）
    - 按 formula_type 分组统计（TB/TB_SUM/ADJ/PREV/WP）
    - 公式类型说明文档区域
    - _Requirements: 6.1-6.4_

  - [ ] 3.2 FormulaTab 报表公式子 Tab
    - 表格展示 report_config 中有公式的 316 行
    - 按 applicable_standard 分 Tab（soe_consolidated/soe_standalone/listed_consolidated/listed_standalone）
    - 按 report_type 分组（balance_sheet/income_statement/cash_flow_statement/equity_changes）
    - 每种 report_type 显示覆盖率（有公式行数/总行数/百分比）
    - 引用不存在 row_code 的公式红色标记
    - _Requirements: 7.1-7.6_

  - [ ]* 3.3 Write property test for invalid formula reference detection
    - **Property 15: Invalid formula reference detection**
    - **Validates: Requirements 7.6**

  - [ ] 3.4 新建 `components/template-library/FormulaCoverageChart.vue` 覆盖率仪表盘
    - 顶部预填充覆盖率 + 报表公式覆盖率
    - 按循环展示预填充覆盖率（如 D 循环 17/17=100%）
    - 按报表类型展示公式覆盖率（如 BS 55/129=43%）
    - 颜色编码：绿色 ≥80%、黄色 40-79%、红色 <40%
    - "无公式底稿"清单
    - _Requirements: 8.1-8.5_

  - [ ]* 3.5 Write property test for coverage color coding
    - **Property 7: Coverage color coding**
    - **Validates: Requirements 8.4, 20.4**

  - [ ] 3.6 FormulaTab 跨底稿引用展示
    - 表格形式展示 cross_wp_references.json 的 20 条规则
    - 列含：source_wp_code/target_wp_code/reference_type/description
    - _Requirements: 6.6_

  - [ ] 3.7 Checkpoint — 确保公式管理 Tab 数据正确加载，覆盖率颜色编码正确
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Sprint 4 — 剩余 Tab + 种子加载器（P1）
  - [ ] 4.1 新建 `components/template-library/AuditReportTab.vue` 审计报告模板 Tab
    - 卡片形式展示 8 种意见类型（unqualified/qualified/adverse/disclaimer × non_listed/listed）
    - 点击展示段落列表（审计意见段/形成基础段/关键审计事项段/其他信息段/管理层责任段/治理层责任段/CPA 责任段）
    - 显示占位符列表及说明
    - 段落完整性检查（必填段落缺失红色警告）
    - _Requirements: 9.1-9.6_

  - [ ] 4.2 新建 `components/template-library/NoteTemplateTab.vue` 附注模板 Tab
    - 双栏展示：左栏标准选择（SOE/Listed），右栏章节树
    - 章节按 section_order 排序
    - 每个章节显示 section_name/has_formula/linked_report_rows
    - 章节总数和有公式驱动的章节数
    - _Requirements: 10.1-10.5_

  - [ ] 4.3 新建 `components/template-library/GtCodingTab.vue` 编码体系 Tab
    - 表格展示 48 条编码（code_prefix/cycle_name/wp_type/description/sort_order）
    - 按 wp_type 分组
    - 每个编码旁显示模板数量
    - admin 可编辑，其他只读
    - _Requirements: 11.1-11.5_

  - [ ] 4.4 新建 `components/template-library/ReportConfigTab.vue` 报表配置 Tab
    - 表格展示 1191 行，按 applicable_standard 分 Tab
    - 每 Tab 内按 report_type 分组
    - 显示 row_code/row_name/indent_level/is_total_row/formula/sort_order
    - indent_level 可视化（每级 24px padding-left）
    - 有公式行蓝色标记，合计行加粗+上边框
    - 顶部统计：总行数/有公式行数/合计行数
    - _Requirements: 12.1-12.7_

  - [ ] 4.5 新建 `components/template-library/SeedLoaderPanel.vue` 种子加载面板
    - "一键加载全部种子"按钮，调用 POST /seed-all
    - 加载过程进度条
    - 失败时显示原因并继续后续
    - 加载完成汇总报告（每个种子的成功/跳过/失败条数）
    - 单独加载按钮（每个模块的"重新加载"）
    - 每个种子的最后加载时间和当前记录数
    - _Requirements: 13.1-13.6_

  - [ ]* 4.6 Write property test for seed load resilience
    - **Property 9: Seed load resilience**
    - **Validates: Requirements 13.3, 13.4**

  - [ ] 4.7 新建 `components/template-library/WpTemplateDetail.vue` 底稿模板详情面板
    - 右侧面板显示模板详情（wp_code/wp_name/cycle_name/format/component_type/linked_accounts/note_section/procedure_steps）
    - 文件列表（一个编码多个文件）+ 下载功能
    - 预填充公式配置展示
    - 跨底稿引用关系
    - 项目使用情况（已使用项目列表/全局使用率）
    - _Requirements: 3.1-3.6, 15.1-15.4_

  - [ ] 4.8 Checkpoint — 确保 6 个 Tab 全部可切换，种子加载流程可执行
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Sprint 5 — 属性测试 + 版本管理 + 收尾（P2）
  - [ ]* 5.1 Write property test for template list completeness
    - **Property 2: Template list completeness and field presence**
    - **Validates: Requirements 2.3, 3.2, 16.2, 16.4**

  - [ ]* 5.2 Write property test for cycle sort order
    - **Property 3: Cycle sort order**
    - **Validates: Requirements 2.4, 16.3**

  - [ ]* 5.3 Write property test for template count per cycle
    - **Property 4: Template count per cycle**
    - **Validates: Requirements 2.5, 11.3**

  - [ ]* 5.4 Write property test for search filter correctness
    - **Property 5: Search filter correctness**
    - **Validates: Requirements 5.1, 5.4, 5.5**

  - [ ]* 5.5 Write property test for generated field correctness
    - **Property 10: Generated field correctness**
    - **Validates: Requirements 4.8, 16.5**

  - [ ]* 5.6 Write property test for file count accuracy
    - **Property 11: File count accuracy**
    - **Validates: Requirements 3.3, 16.6**

  - [ ]* 5.7 Write property test for progress calculation
    - **Property 12: Progress calculation**
    - **Validates: Requirements 4.10, 20.1, 20.2**

  - [ ]* 5.8 Write property test for seed load history audit trail
    - **Property 14: Seed load history audit trail**
    - **Validates: Requirements 14.3, 13.6**

  - [ ] 5.9 实现版本管理功能
    - 页面顶部版本标识 + 元信息（版本号/发布日期/文件总数/变更摘要）
    - 版本历史列表（时间倒序，从 seed_load_history 读取）
    - 每次种子加载记录时间戳和操作人
    - _Requirements: 14.1-14.5_

  - [ ] 5.10 Final checkpoint — 确保全部测试通过，vue-tsc 0 错误
    - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Sprint 6 — 枚举字典管理 + 自定义查询（P1）
  - [ ] 6.1 新建 `components/template-library/EnumDictTab.vue` 枚举字典 Tab
    - 从 `GET /api/system/dicts` 获取全部枚举字典
    - 按字典分组展示（wp_status/wp_review_status/project_status/issue_severity 等）
    - 每个枚举项显示：value/label/color/sort_order/引用计数
    - admin 可新增/修改/禁用枚举项（不允许物理删除已使用的）
    - 支持拖拽排序
    - _Requirements: 21.1-21.6_

  - [ ] 6.2 后端新增枚举引用计数端点 `GET /api/system/dicts/{dict_key}/usage-count`
    - 查询各枚举值在对应表中的使用次数
    - 返回 `{value: string, count: number}[]`
    - _Requirements: 21.4_

  - [ ] 6.3 后端新增枚举项 CRUD 端点 `POST/PUT /api/system/dicts/{dict_key}/items`
    - 新增枚举项（value/label/color/sort_order）
    - 修改枚举项（label/color/sort_order/enabled）
    - 禁用校验：引用计数 > 0 时不允许删除，只能禁用
    - _Requirements: 21.3, 21.5_

  - [ ] 6.4 新建 `components/template-library/CustomQueryTab.vue` 自定义查询 Tab
    - 可视化查询构建器：数据源选择 + 条件筛选 + 字段选择
    - 支持 8 个数据源（底稿/试算表/调整分录/科目余额/序时账/附注/报表行次/工时）
    - 条件类型：等于/包含/大于/小于/范围/为空/不为空
    - 多条件组合 AND/OR
    - _Requirements: 22.1-22.5_

  - [ ] 6.5 自定义查询结果展示 + 导出
    - 结果以 el-table 展示（用户选择的字段为列）
    - 支持导出为 Excel（调用后端导出端点或前端 xlsx 库）
    - _Requirements: 22.6_

  - [ ] 6.6 自定义查询模板保存/加载
    - 保存查询模板（名称 + 条件 + 字段选择 + 全局/私有标记）
    - 加载已保存模板列表（我的 + 全局共享）
    - 后端端点：`POST /api/custom-query/templates` + `GET /api/custom-query/templates`
    - _Requirements: 22.7-22.8_

  - [ ] 6.7 在模板库管理页面 Tab 导航中新增"枚举字典"和"自定义查询"两个 Tab（总计 8 Tab）
    - _Requirements: 21.1, 22.1, 22.9_

  - [ ] 6.8 Checkpoint — 确保枚举字典 CRUD 正常，自定义查询可执行并导出
    - Ensure all tests pass, ask the user if questions arise.

## UAT 验收清单（手动浏览器验证）

1. 侧栏点击"模板库管理"进入页面，8 个 Tab 可切换
2. 底稿模板 Tab 树形展示 180 个模板，搜索/筛选正常
3. WorkpaperWorkbench 树形显示全部 180 个模板，进度条正确
4. "仅有数据"筛选器正确隐藏零余额模板
5. 公式覆盖率仪表盘颜色编码正确
6. 种子加载器一键加载 + 单独加载均可执行
7. 非 admin 用户看不到编辑按钮
8. 报表配置 Tab 缩进和合计行样式正确
9. 枚举字典 Tab 显示引用计数，admin 可编辑/禁用
10. 自定义查询可构建条件、执行、导出 Excel、保存模板

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from design.md
- 后端使用 Python（FastAPI + SQLAlchemy），前端使用 TypeScript + Vue 3 + Element Plus
- 属性测试使用 hypothesis 库，max_examples=5（MVP 阶段速度优先）
