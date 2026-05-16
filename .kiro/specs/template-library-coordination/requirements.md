# 需求文档：全局模板库管理系统

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|----------|
| v1 | 2026-05-15 | 初版：22 需求 / 5 大模板库 + 编码体系覆盖 | spec 创建 |
| v2 | 2026-05-16 | 关键事实核验后修订：mappings 数量 118→206 / index 结构 list→dict / 8 ADR 增至 12 | 实施前 grep 核验 |
| v3 | 2026-05-16 | 7 处硬编码计数清零 | D16 ADR 落地 |
| v4 | 2026-05-16 | 13 处硬编码二次扫除 | 收尾自检 |
| v5 | 2026-05-16 | R1-R4 4 处可改进点：Sprint 0 N_* 输出 / seed key 实测核验 / Mermaid 节点描述化 / cross_wp_references 只读源声明 | 一致性审查 |
| v6 | 2026-05-16 | 二轮复盘：未提及修订；本轮聚焦 design.md / tasks.md 流程改进 | 二轮复盘 |

## 引言

致同审计作业平台包含 5 大模板库 + 1 套编码体系，当前各自独立管理、缺乏统一入口。管理员无法在一个界面总览全部模板资源，审计助理无法快速了解公式覆盖情况，项目经理无法查看模板与项目的关联状态。

本功能建立"模板库管理"统一页面，整合底稿模板库（**N_files** 物理文件 / **N_primary** 主编码 / **N_account_mappings** 科目映射）、公式管理库（**N_prefill_mappings** 预填充映射 / **N_prefill_cells** 单元格 / 报表公式动态统计）、审计报告模板库（**N_opinion_types** 种意见类型）、附注模板库（SOE/Listed 双标准）、致同编码体系（**N_gt_codes** 条）、报表行次配置（**N_report_rows** 行 / **N_standards** 标准），提供浏览、编辑、种子加载、版本管理、覆盖率统计等能力。所有 N_* 数字均为**运行时从 seed/DB 实时计算**，narrative 引用快照值仅作可读性参考（当前快照：files=476 / primary≥179 / account_mappings=206 / prefill_mappings=94 / prefill_cells=481 / opinion_types=8 / gt_codes=48 / report_rows=1191 / standards=4）。

**与 audit-chain-generation spec 的协同关系**：本 spec 是 audit-chain-generation 的**消费方**——后者已通过 `chain_orchestrator._step_generate_workpapers` + `load_wp_template_metadata.py` 完成 `wp_template_metadata` 表加载（运行时聚合 3 个增量 seed 文件 entries 之和，当前 ≥ 179 条）和 `wp_account_mapping.json` 扩展（206 条），本 spec 直接消费这些数据，不重复建设。

## 术语表

- **Template_Library_Page**：模板库管理页面，侧栏入口"模板库管理"，admin/partner 可编辑，其他角色只读
- **WP_Template_Library**：底稿模板库，`backend/wp_templates/` 目录（**N_files** 物理文件） + `_index.json` 索引（dict 结构含 description/version/files 三个 key） + 三个增量 seed 文件（`{dn,b,cas}_seed.json` 的 entries 之和 = 主编码总数 N_primary，**运行时聚合**） + `wp_account_mapping.json`（**N_account_mappings** 条科目映射）
- **Subtable_Convergence**：子表收敛策略（来自 audit-chain-generation 落地）—— 一个 wp_code 对应一个 wp_index 一个 xlsx 文件，多源文件（如 D2 审定表 + 分析程序 + 检查程序）自动合并为同一 xlsx 的多个 sheets（合并后 sheets 数由 `init_workpaper_from_template._merge_sheets_from_other_files` 运行时产生，spec 层不持久化精确值）
- **Formula_Library**：公式管理库，含预填充公式（`prefill_formula_mapping.json` 的 mappings + cells，**N_prefill_mappings/N_prefill_cells 实时读取**）和报表公式（`report_config.formula` 列动态统计，覆盖率通过 SQL 实时计算）
- **Cross_WP_References**：跨底稿引用规则，从 `cross_wp_references.json["references"]` **运行时读取**
- **Audit_Report_Templates**：审计报告模板库，`audit_report_templates_seed.json` 含**全部意见类型**段落模板（数量 N_opinion_types 实时读取）
- **Note_Templates**：附注模板库，通过 note_templates 路由加载，分 SOE（国企版）和 Listed（上市版）两套标准
- **GT_Coding**：致同编码体系，`gt_wp_coding` 表（**N_gt_codes** 条记录由 SELECT COUNT(*) 实时值），定义循环编码 B/C/D-N/A/S/T/Z
- **Report_Config**：报表行次配置，`report_config` 表（**N_report_rows** 行 / **N_standards** 标准均由 SQL 实时统计，覆盖 soe_consolidated/soe_standalone/listed_consolidated/listed_standalone 四种标准）
- **Seed_Loader**：种子数据加载器，一键将 `backend/data/` 目录下的 JSON 种子文件写入数据库
- **Formula_Coverage**：公式覆盖率，指有公式定义的底稿/行次占总数的百分比
- **Template_Version**：模板版本，当前为"致同 2025 修订版"

## 需求

### 需求 1：统一管理页面入口

**User Story:** 作为管理员，我想从侧栏直接进入模板库管理页面，以便集中管理所有模板资源。

#### 验收标准

1. THE Template_Library_Page SHALL 在侧栏导航中显示"模板库管理"入口（图标：文件夹）
2. WHEN 用户角色为 admin 或 partner 时，THE Template_Library_Page SHALL 显示编辑/删除操作按钮
3. WHEN 用户角色为 manager/auditor/qc 时，THE Template_Library_Page SHALL 以只读模式展示所有内容
4. THE Template_Library_Page SHALL 使用左侧 Tab 导航切换 6 个子模块：底稿模板、公式管理、审计报告模板、附注模板、编码体系、报表配置
5. THE Template_Library_Page SHALL 在顶部显示全局统计摘要（模板总数/公式覆盖率/种子加载状态）

### 需求 2：底稿模板库浏览

**User Story:** 作为审计助理，我想浏览全部主编码模板的完整列表，以便了解可用底稿清单。

#### 验收标准

1. THE WP_Template_Library SHALL 以树形结构展示**全部主编码模板**（数量 = 当前 wp_template_metadata 表中 distinct primary_code 的实际值），按循环分组
2. THE WP_Template_Library SHALL 使用 GT_Coding 的 cycle_name 作为树形分组的显示名称
3. WHEN 展开循环节点时，THE WP_Template_Library SHALL 显示该循环下所有模板的 wp_code、wp_name、format、component_type
4. THE WP_Template_Library SHALL 按 GT_Coding 的 sort_order 对循环进行排序
5. THE WP_Template_Library SHALL 在每个循环节点旁**动态计算**模板数量并展示（如"D 销售循环 (N)"，N = 该循环下的主编码计数）
6. THE WP_Template_Library SHALL 对每个模板节点显示格式图标（xlsx 用表格图标、docx 用文档图标、xlsm 用宏图标）
7. WHEN 模板在 wp_template_metadata 中有记录时，THE WP_Template_Library SHALL 显示 component_type 标签（univer/form/word/hybrid）

### 需求 3：底稿模板详情与文件管理

**User Story:** 作为管理员，我想查看单个底稿模板的详细信息和关联文件，以便了解模板结构。

#### 验收标准

1. WHEN 用户点击模板节点时，THE WP_Template_Library SHALL 在右侧面板显示模板详情
2. THE WP_Template_Library SHALL 在详情面板显示：wp_code、wp_name、cycle_name、format、component_type、linked_accounts、note_section、procedure_steps
3. THE WP_Template_Library SHALL 显示该 wp_code 对应的源文件清单（如 D2 含 D2-1 至 D2-4 审定表 + D2-5 分析程序 + D2-6 至 D2-13 检查程序，**实际生成时合并为同一 xlsx 多 sheets**）
4. WHEN 用户点击源文件名时，THE WP_Template_Library SHALL 提供下载该文件的功能（保留对原始模板的访问，便于参考）
5. THE WP_Template_Library SHALL 显示该模板已合并 sheets 的清单（如 D2 显示 20 个 sheets 的列表）
6. THE WP_Template_Library SHALL 显示该模板的预填充公式配置（从 prefill_formula_mapping 读取）
7. WHEN 模板有 cross_wp_references 引用时，THE WP_Template_Library SHALL 显示跨底稿引用关系图

### 需求 4：底稿模板树形完善（WorkpaperWorkbench 集成）

**User Story:** 作为审计助理，我想在底稿工作台看到全部主编码模板（覆盖 B/C/D-N/A/S 全 6 模块），以便了解完整的底稿清单。

#### 验收标准

1. THE Workbench_Tree SHALL 使用 `GET /api/projects/{pid}/wp-templates/list` 作为数据源，返回**全部主编码模板**（数量动态从端点取）
2. THE Workbench_Tree SHALL 按循环分组展示模板，每个循环节点显示循环名称和该循环下的模板数量（按主编码计数）
3. WHEN wp_code 首字母为 B 时，THE Workbench_Tree SHALL 根据编码范围区分初步业务活动（B1-B5）和风险评估（B10-B60）
4. WHEN wp_code 首字母为 C 时，THE Workbench_Tree SHALL 将其归类为控制测试
5. WHEN wp_code 首字母为 D/E/F/G/H/I/J/K/L/M/N 时，THE Workbench_Tree SHALL 将其归类为实质性程序
6. WHEN wp_code 首字母为 A 时，THE Workbench_Tree SHALL 将其归类为完成阶段
7. WHEN wp_code 首字母为 S 时，THE Workbench_Tree SHALL 将其归类为特定项目程序
8. WHEN 模板已在当前项目生成底稿时，THE Workbench_Tree SHALL 在节点上显示状态标记（已生成/编制中/已复核等）
9. WHEN 模板未在当前项目生成底稿时，THE Workbench_Tree SHALL 以灰色文字显示该节点
10. THE Workbench_Tree SHALL 在树形顶部显示全局进度条（已生成主编码数 / 主编码总数，分母从 `/list` 端点动态取）

### 需求 5：底稿模板搜索与筛选

**User Story:** 作为审计助理，我想通过关键词搜索和条件筛选快速定位底稿模板。

#### 验收标准

1. WHEN 用户在搜索框输入文字时，THE WP_Template_Library SHALL 按 wp_code 和 wp_name 进行模糊匹配过滤
2. THE WP_Template_Library SHALL 在搜索结果中高亮匹配的文字
3. WHEN 搜索框清空时，THE WP_Template_Library SHALL 恢复完整树形展示
4. THE WP_Template_Library SHALL 提供按 component_type 筛选（univer/form/word/hybrid/全部）
5. THE WP_Template_Library SHALL 提供按循环筛选（B/C/D-N/A/S/全部）
6. THE WP_Template_Library SHALL 提供"仅有数据"筛选器，隐藏 linked_accounts 中所有科目在试算表中余额为零的模板

### 需求 6：预填充公式查看（D13 ADR：JSON 源只读）

**User Story:** 作为管理员，我想查看底稿预填充公式配置，以便理解取数规则；如需修改请通过编辑 JSON 文件后重新加载种子的方式（git → seed → DB 单向流动）。

#### 验收标准

1. THE Formula_Library SHALL 以表格形式展示**全部预填充映射**（数量从 `prefill_formula_mapping.json["mappings"]` 实时读取），列包含：wp_code、wp_name、sheet、cells 数量
2. WHEN 用户展开某个映射时，THE Formula_Library SHALL 显示该映射下所有 cells 的详情（cell_ref、formula、formula_type、description）
3. THE Formula_Library SHALL 按 formula_type 分组统计：TB/TB_SUM/ADJ/PREV/WP 各有多少个单元格
4. THE Formula_Library SHALL 显示公式类型说明文档（TB 从试算表取数、TB_SUM 范围汇总、ADJ 调整分录、PREV 上年数据、WP 跨底稿引用）
5. WHEN 用户尝试编辑公式时，THE Formula_Library SHALL **以只读模式展示** + 提示"如需修改请编辑 backend/data/prefill_formula_mapping.json 后调用 reseed 端点"（D13 JSON 源只读铁律）
6. THE Formula_Library SHALL 显示**全部跨底稿引用关系**（从 `cross_wp_references.json["references"]` 实时读取），以有向图或表格形式展示源底稿→目标底稿的引用链

### 需求 7：报表公式管理

**User Story:** 作为管理员，我想查看和编辑报表行次公式，以便维护报表计算逻辑。

#### 验收标准

1. THE Formula_Library SHALL 以表格形式展示 report_config 中有公式的行（实际数量通过 SQL 实时统计），列包含：applicable_standard、report_type、row_code、row_name、formula
2. THE Formula_Library SHALL 按 applicable_standard 分 Tab 展示（soe_consolidated/soe_standalone/listed_consolidated/listed_standalone）
3. THE Formula_Library SHALL 按 report_type 分组（balance_sheet/income_statement/cash_flow_statement/equity_changes）
4. WHEN admin 用户编辑公式时，THE Formula_Library SHALL 提供公式语法校验（支持 TB/TB_SUM/ROW/SUM_ROW/SUM_TB/LEDGER/AUX/PREV/ADJ/NOTE 类型）
5. THE Formula_Library SHALL 显示公式覆盖率统计：每种 report_type 下有公式行数/总行数/覆盖率百分比（动态查询）
6. WHEN 公式引用了不存在的 row_code 时，THE Formula_Library SHALL 以红色标记该公式并提示"引用目标不存在"

### 需求 8：公式覆盖率统计仪表盘

**User Story:** 作为项目经理，我想看到公式覆盖率的全局统计，以便了解自动化取数的完备程度。

#### 验收标准

1. THE Formula_Library SHALL 在顶部显示覆盖率仪表盘，包含：预填充覆盖率（有公式的主编码数 / 主编码总数，动态查询）、报表公式覆盖率（有公式行数 / 总行数，动态计算）
2. THE Formula_Library SHALL 按循环展示预填充覆盖率（如 D 循环 N_with_formula/N_total = 百分比）
3. THE Formula_Library SHALL 按报表类型展示公式覆盖率（如 BS 有公式行数 / 总行数 = 百分比）
4. THE Formula_Library SHALL 用颜色编码标识覆盖率等级（绿色 ≥80%、黄色 40-79%、红色 <40%）
5. THE Formula_Library SHALL 列出"无公式底稿"清单，标注原因（B/C/A/S 类无审定表、函证类仅期初/未审数）

### 需求 9：审计报告模板查看（D13 ADR：JSON 源只读）

**User Story:** 作为管理员，我想查看审计报告段落模板，以便理解不同意见类型的报告措辞；如需修改请通过编辑 JSON 文件后重新加载种子的方式。

#### 验收标准

1. THE Audit_Report_Templates SHALL 以卡片形式展示**全部意见类型**（数量从 `audit_report_templates_seed.json["templates"]` 实时读取，覆盖 unqualified/qualified/adverse/disclaimer × non_listed/listed 等组合）
2. WHEN 用户点击某种意见类型时，THE Audit_Report_Templates SHALL 展示该类型下所有段落（审计意见段、形成基础段、关键审计事项段、其他信息段、管理层责任段、治理层责任段、CPA 责任段）
3. THE Audit_Report_Templates SHALL 显示每个段落的占位符列表（{entity_name}、{audit_period} 等）及其说明
4. WHEN 用户尝试编辑段落模板时，THE Audit_Report_Templates SHALL **以只读模式展示** + 提示"如需修改请编辑 backend/data/audit_report_templates_seed.json 后调用 reseed 端点"（D13 JSON 源只读铁律）
5. THE Audit_Report_Templates SHALL 显示每种意见类型的段落完整性（必填段落是否全部配置）
6. IF 必填段落缺失模板文本，THEN THE Audit_Report_Templates SHALL 以红色警告标记该段落

### 需求 10：附注模板管理

**User Story:** 作为管理员，我想查看附注模板的章节结构和公式配置，以便了解附注自动生成的覆盖范围。

#### 验收标准

1. THE Note_Templates SHALL 以双栏展示：左栏为标准选择（SOE 国企版/Listed 上市版），右栏为章节树
2. WHEN 用户选择标准后，THE Note_Templates SHALL 展示该标准下所有附注章节（按 section_order 排序）
3. THE Note_Templates SHALL 在每个章节节点显示：section_name、has_formula（是否有公式驱动数据）、linked_report_rows（关联的报表行次）
4. WHEN 用户点击章节时，THE Note_Templates SHALL 在右侧显示该章节的模板内容预览
5. THE Note_Templates SHALL 显示附注章节总数和有公式驱动的章节数

### 需求 11：致同编码体系展示

**User Story:** 作为审计助理，我想查看致同编码体系的完整层级结构，以便理解底稿分类逻辑。

#### 验收标准

1. THE GT_Coding SHALL 以表格形式展示**全部编码记录**（数量 = `gt_wp_coding` 表 SELECT COUNT(*) 实时值），列包含：code_prefix、cycle_name、wp_type、description、sort_order
2. THE GT_Coding SHALL 按 wp_type 分组展示（初步业务活动/风险评估/控制测试/实质性程序/完成阶段/特定项目）
3. THE GT_Coding SHALL 在每个编码旁显示该编码下的模板数量（从 WP_Template_Library 统计）
4. WHEN 用户角色非 admin 时，THE GT_Coding SHALL 以只读模式展示（无编辑按钮）
5. WHEN admin 用户编辑编码时，THE GT_Coding SHALL 校验 code_prefix 唯一性和 sort_order 连续性

### 需求 12：报表行次配置管理

**User Story:** 作为管理员，我想查看和管理报表行次配置，以便维护财务报表的行次结构。

#### 验收标准

1. THE Report_Config SHALL 以表格形式展示**全部行配置**（数量 = `report_config` 表 SELECT COUNT(*) 实时值），按 applicable_standard 分 Tab
2. THE Report_Config SHALL 在每个 Tab 内按 report_type 分组（资产负债表/利润表/现金流量表/权益变动表）
3. THE Report_Config SHALL 显示每行的：row_code、row_name、indent_level、is_total_row、formula、sort_order
4. THE Report_Config SHALL 用缩进可视化 indent_level（每级 24px padding-left）
5. WHEN 行有公式时，THE Report_Config SHALL 以蓝色标记 formula 列并支持点击查看公式详情
6. WHEN 行是合计行时，THE Report_Config SHALL 以加粗+上边框样式区分
7. THE Report_Config SHALL 在表格顶部显示统计：总行数/有公式行数/合计行数

### 需求 13：种子数据一键加载

**User Story:** 作为管理员，我想一键加载所有种子数据，以便在新部署环境快速初始化模板库。

#### 验收标准

1. THE Seed_Loader SHALL 提供"一键加载全部种子"按钮，依次调用以下端点：
   - POST /api/report-config/seed
   - POST /api/gt-coding/seed
   - POST /api/wp-template-metadata/seed
   - POST /api/audit-report/templates/load-seed
   - POST /api/accounting-standards/seed
   - POST /api/template-sets/seed
2. THE Seed_Loader SHALL 在加载过程中显示进度条（已完成/总数）
3. WHEN 某个种子加载失败时，THE Seed_Loader SHALL 显示失败原因并继续加载后续种子
4. THE Seed_Loader SHALL 在加载完成后显示汇总报告（每个种子的加载结果：成功条数/跳过条数/失败条数）
5. THE Seed_Loader SHALL 支持单独加载某一个种子（点击对应模块的"重新加载"按钮）
6. THE Seed_Loader SHALL 显示每个种子的最后加载时间和当前数据库中的记录数

### 需求 14：模板版本管理

**User Story:** 作为管理员，我想追踪模板库的版本信息，以便了解当前使用的模板版本和历史变更。

#### 验收标准

1. THE Template_Library_Page SHALL 在页面顶部显示当前模板版本标识（"致同 2025 修订版"）
2. THE Template_Library_Page SHALL 显示版本元信息：版本号、发布日期、文件总数、变更摘要
3. THE Template_Library_Page SHALL 记录每次种子加载的时间戳和操作人
4. WHEN 模板文件被更新时，THE Template_Library_Page SHALL 在版本历史中记录变更（新增/修改/删除的文件列表）
5. THE Template_Library_Page SHALL 支持查看版本历史列表（时间倒序）

### 需求 15：模板与项目关联展示

**User Story:** 作为项目经理，我想查看模板在各项目中的使用情况，以便了解模板的实际应用范围。

#### 验收标准

1. THE WP_Template_Library SHALL 在模板详情面板显示"项目使用情况"区域
2. THE WP_Template_Library SHALL 列出已使用该模板生成底稿的项目列表（项目名称、生成时间、当前状态）
3. THE WP_Template_Library SHALL 显示该模板的全局使用率（已使用项目数/总项目数）
4. WHEN 模板从未被任何项目使用时，THE WP_Template_Library SHALL 显示"暂无项目使用"提示

### 需求 16：模板列表 API 完善

**User Story:** 作为开发者，我想获取完整的底稿模板列表 API，以便前端树形控件和管理页面使用。

#### 验收标准

1. THE `GET /api/projects/{pid}/wp-templates/list` SHALL 返回**全部主编码模板条目**（数量 = wp_template_metadata 表中 distinct primary_code 的实际值）
2. WHEN 请求模板列表时，THE API SHALL 返回每条记录包含 wp_code、wp_name、cycle、cycle_name、format、component_type、linked_accounts、has_formula 字段
3. THE API SHALL 按 gt_wp_coding 的 sort_order 对循环进行排序
4. WHEN 模板在 wp_template_metadata 中有记录时，THE API SHALL 合并 component_type、audit_stage、linked_accounts、procedure_steps 字段到返回结果
5. THE API SHALL 在每条记录中包含 generated 布尔字段，标识该模板是否已在当前项目中生成底稿
6. THE API SHALL 在每条记录中包含 source_file_count 字段，标识该 wp_code 对应的源 xlsx 物理文件数量（合并前的源文件数，如 D2 有 3 个源文件）
7. THE API SHALL 在每条记录中包含 sheet_count 字段，标识合并后的 sheet 总数（如 D2 = 20 sheets）

### 需求 17：公式管理全局 API

**User Story:** 作为开发者，我想通过 API 获取公式覆盖率统计和公式详情，以便前端仪表盘展示。

#### 验收标准

1. THE `GET /api/template-library/formula-coverage` SHALL 返回全局公式覆盖率统计
2. THE API SHALL 返回按循环分组的预填充覆盖率（cycle、total_templates、templates_with_formula、coverage_percent）
3. THE API SHALL 返回按报表类型分组的报表公式覆盖率（report_type、total_rows、rows_with_formula、coverage_percent）
4. THE API SHALL 返回公式类型分布统计（formula_type、count）
5. THE `GET /api/template-library/prefill-formulas` SHALL 返回**全部预填充映射详情**（数量从 `prefill_formula_mapping.json["mappings"]` 实时读取）
6. THE `GET /api/template-library/cross-wp-references` SHALL 返回**全部跨底稿引用规则**（数量从 `cross_wp_references.json["references"]` 实时读取）

### 需求 18：种子数据状态 API

**User Story:** 作为开发者，我想通过 API 查询各种子数据的加载状态，以便前端显示加载进度和最后更新时间。

#### 验收标准

1. THE `GET /api/template-library/seed-status` SHALL 返回每个种子的加载状态
2. THE API SHALL 对每个种子返回：seed_name、last_loaded_at、record_count、status（loaded/not_loaded/partial）
3. THE API SHALL 检查以下种子：report_config、gt_wp_coding、wp_template_metadata、audit_report_templates、note_templates、accounting_standards、template_sets
4. WHEN 数据库中某种子记录数为 0 时，THE API SHALL 返回 status="not_loaded"
5. WHEN 数据库中某种子记录数少于 seed 文件中的条目数时，THE API SHALL 返回 status="partial"


### 需求 19：仅有数据筛选兼容

**User Story:** 作为审计助理，我想使用"仅有数据"筛选器隐藏无余额数据的底稿，以便聚焦有实际工作量的底稿。

#### 验收标准

1. WHEN "仅有数据"勾选时，THE Workbench_Tree SHALL 隐藏 linked_accounts 中所有科目在试算表中余额为零的模板
2. WHEN "仅有数据"勾选时，THE Workbench_Tree SHALL 始终显示无 linked_accounts 的模板（B/C/A/S 类）
3. WHEN "仅有数据"取消勾选时，THE Workbench_Tree SHALL 显示全部主编码模板（不施加 linked_accounts 过滤）
4. IF 试算表数据尚未加载，THEN THE Workbench_Tree SHALL 显示全部模板并在筛选器旁提示"需先导入账套"

### 需求 20：循环进度统计

**User Story:** 作为项目经理，我想看到每个循环的完成进度，以便掌握项目整体底稿编制情况。

#### 验收标准

1. THE Workbench_Tree SHALL 在每个循环节点旁显示进度（已完成主编码数 / 该循环总主编码数）
2. THE Workbench_Tree SHALL 在树形顶部显示全局进度条（已生成主编码数 / 主编码总数，分母从 `/list` 端点动态取）
3. WHEN 底稿状态变更时，THE Workbench_Tree SHALL 实时更新进度统计
4. THE Workbench_Tree SHALL 用颜色区分进度等级（绿色 100%、蓝色 50-99%、灰色 <50%）

### 需求 21：全局枚举字典管理

**User Story:** 作为管理员，我想在模板库管理页面集中查看和维护系统枚举字典，以便各子模块直接引用统一的枚举值。

#### 验收标准

1. THE Template_Library_Page SHALL 新增"枚举字典"Tab，展示系统全部枚举字典（从 `GET /api/system/dicts` 获取）
2. THE Template_Library_Page SHALL 按字典分组展示：wp_status / wp_review_status / project_status / issue_severity / adjustment_type / report_status 等
3. WHEN admin 用户编辑枚举项时，THE Template_Library_Page SHALL 支持新增/修改/禁用枚举值（不允许物理删除已使用的枚举）
4. THE Template_Library_Page SHALL 在每个枚举项旁显示引用计数（该值在系统中被多少条记录使用）
5. THE Template_Library_Page SHALL 支持枚举项排序（拖拽或 sort_order 字段）
6. WHEN 子模块需要枚举值时，SHALL 统一从 dictStore 获取（前端已有 `useDictStore`），不允许硬编码

### 需求 22：自定义查询管理

**User Story:** 作为审计助理，我想通过自定义查询功能检索系统内任意数据，以便灵活获取跨模块信息。

#### 验收标准

1. THE Template_Library_Page SHALL 新增"自定义查询"Tab，提供可视化查询构建器
2. THE 自定义查询 SHALL 支持查询以下数据源：底稿列表 / 试算表 / 调整分录 / 科目余额 / 序时账 / 附注 / 报表行次 / 工时记录
3. THE 自定义查询 SHALL 支持条件筛选（等于/包含/大于/小于/范围/为空/不为空）
4. THE 自定义查询 SHALL 支持多条件组合（AND/OR）
5. THE 自定义查询 SHALL 支持结果列选择（用户选择要显示的字段）
6. THE 自定义查询 SHALL 支持结果导出为 Excel
7. THE 自定义查询 SHALL 支持保存查询模板（命名保存，下次直接调用）
8. WHEN 用户保存查询模板时，THE 自定义查询 SHALL 支持设置为"全局共享"或"仅自己可见"
9. THE 自定义查询 SHALL 在侧栏"自定义查询"入口也可独立访问（**前端 CustomQuery.vue 当前不存在，需新建**；后端 `/api/custom-query` 端点已存在）
