# 需求文档

## 引言

本规格（spec）解决底稿模块运行时实测发现的根本问题——**「有账无稿」**：本机 PG（`audit_platform`）中底层账数据齐备（`tb_balance` 2428 行 / `tb_ledger` 82384 行；首汽租车项目 df5b8403 单项目 `tb_balance` 1654 / `tb_ledger` 30324 / 827 个科目），但 `working_paper`、`wp_index`、`audit_procedures`、`procedure_instances` 全部为 0 行——**底稿模块从未在真实数据上端到端跑通过一次**。

本 spec 的目标是让一个真实项目（df5b8403 首汽租车_2025，已导入 8 万行序时账）从「导入完成」端到端跑通到「生成可编辑底稿」，并把这条「账→稿」链路固化为可重复、可验证、有自动化测试保护的能力。这条链路是所有其他底稿 spec 的验证地基——没有真实的 `working_paper` 数据，其他底稿功能都缺乏验证基础。

### 实跑已确认的事实（需求据此撰写，不照抄过时判断）

1. **推荐链已验证可跑通**：`WpMappingService(db).recommend_workpapers(df5b8403, 2025, "standalone")` 对真实项目 827 个科目成功推荐 63 张底稿（A1/B1/B60/D0/D2/D2-2/D2-3/D2-4/D4/D6 等）。此步健康、有真实输出。
2. **生成端点实际会创建 `working_paper`**：阅读当前 `backend/app/routers/wp_template.py` 的 `generate_from_codes` 实现确认，它在创建 `wp_index` 后**确实创建 `WorkingPaper` 记录**（并调用 dataset 绑定 + 表头填充）。因此本 spec **不假定** `working_paper` 不会被创建，而是要求**在真实项目上实跑验证它是否被正确创建、`parsed_data` 是否被正确填充**。
3. **标准科目落地实测**：原始账表 `tb_balance` 只有 `account_code`/`company_code`/`account_name`/`currency_code`，**没有 `standard_account_code` 列**；而推荐/取数走的是 ORM `TrialBalance`（物理表 `trial_balance`，**含 `standard_account_code`**）。两表必须区分清楚，「标准科目在四表的落地方式」需作为显式验证需求点。

### 核心验收铁律

所有验收必须是「**在 df5b8403 这种有真实数据的项目上，该功能跑出正确结果**」，而非「端点存在 + 测试绿」。端点存在性 grep 与代码静态分析不构成验收证据。

## 术语表（Glossary）

- **Generation_Pipeline（生成管线）**：从推荐编码列表出发，创建底稿索引、底稿记录、模板文件并完成绑定与表头填充的端到端后端流程，入口为 `POST /api/projects/{project_id}/working-papers/generate-from-codes`。
- **Recommendation_Service（推荐服务）**：`WpMappingService.recommend_workpapers`，根据试算表有余额科目推荐需编制的底稿清单。
- **Wp_Index（底稿索引）**：`wp_index` 表记录，表示某项目下一张底稿的清单/索引项（`wp_code`、`wp_name`、`audit_cycle`、`status`），不含底稿文件内容。
- **Working_Paper（底稿记录）**：`working_paper` 表记录，表示一张实际底稿文件（`file_path`、`source_type`、`parsed_data`、`bound_dataset_id` 等），是可在编辑器中打开编辑的对象。
- **Trial_Balance（标准试算表）**：ORM `TrialBalance`，物理表 `trial_balance`，含 `standard_account_code`（标准科目编码），是推荐与取数的数据源。
- **TB_Balance（原始余额表）**：物理表 `tb_balance`，导入产生的原始账表，仅含 `account_code`，无 `standard_account_code`。
- **Standard_Account_Mapping（标准科目映射）**：将原始 `account_code` 映射到 `standard_account_code` 的落地机制（物理列或运行时映射），决定按标准科目取数的底稿能否正确填充。
- **Dataset_Binding（快照绑定）**：`bind_to_active_dataset`，底稿生成时绑定当时的 active `ledger_datasets`，用于数据快照与防篡改。
- **Header_Fill（表头填充）**：`wp_header_service.fill_workpaper_header`，向底稿文件写入致同标准表头（编制单位/审计期间/索引号/交叉索引等）。
- **Prerequisite_Checker（前置门禁）**：`PrerequisiteChecker` 的 `generate_workpapers` 检查，生成底稿前的前置条件校验。
- **Editor（底稿编辑器）/ HTML_Renderer（HTML 渲染器）**：前端打开 Working_Paper 进行编辑或渲染的组件，依赖 `working_paper` 与 `workpaper_sheet_classification` 数据。
- **Test_Project（验收项目）**：df5b8403（首汽租车_2025），PG 库 `audit_platform`，docker 容器 `audit-postgres`，作为本 spec 的真实数据验收基准。

## 需求（Requirements）

### 需求 1：生成底稿端到端打通

**用户故事（User Story）：** 作为审计项目负责人，我希望在已导入序时账的真实项目上，调用生成底稿端点后能真正建出底稿索引、底稿记录与模板文件，以便让「账→稿」链路在真实数据上端到端跑通，而不是停留在「有账无稿」状态。

#### 验收标准（Acceptance Criteria）

1. WHEN 操作者携带由 Recommendation_Service 推荐出的 `wp_codes` 列表调用 `POST /api/projects/{project_id}/working-papers/generate-from-codes`，THE Generation_Pipeline SHALL 为列表中每个 `wp_code` 创建对应的 Wp_Index 记录。
2. WHEN Generation_Pipeline 为某个 `wp_code` 创建 Wp_Index 记录，THE Generation_Pipeline SHALL 同步创建对应的 Working_Paper 记录并写入底稿模板文件到 `storage/projects/{project_id}/workpapers/` 路径。
3. WHEN 操作者在 Test_Project（df5b8403，2025 年度）上完成一次 generate-from-codes 调用，THE Generation_Pipeline SHALL 使该项目 `working_paper` 表的记录数大于 0。
4. WHEN Generation_Pipeline 完成单次生成调用，THE Generation_Pipeline SHALL 返回包含已创建底稿数量、已跳过底稿数量与失败底稿明细的结构化结果。
5. WHEN Generation_Pipeline 为某个 `wp_code` 创建 Working_Paper 记录，THE Generation_Pipeline SHALL 调用 Dataset_Binding 将该底稿绑定到当前项目的 active `ledger_datasets`。
### 需求 2：Wp_Index → Working_Paper 二段关系明确化

**用户故事：** 作为底稿模块维护者，我希望「底稿清单（Wp_Index）」与「可编辑底稿（Working_Paper）」之间的二段创建关系明确且可验证，以便消除「清单 vs 可编辑底稿」的模糊地带，确保每张索引都有可打开的底稿。

#### 验收标准

1. WHEN Generation_Pipeline 在 Test_Project 上完成生成，THE Generation_Pipeline SHALL 使每个新建的 Wp_Index 记录都存在一个 `wp_code` 与 `project_id` 匹配的 Working_Paper 记录。
2. WHEN Generation_Pipeline 创建某个 Working_Paper 记录，THE Generation_Pipeline SHALL 填充其 `parsed_data` 字段，使该字段包含底稿的表头内容与模板 sheet 结构。
3. IF 某个 Wp_Index 记录在生成完成后不存在与之匹配的 Working_Paper 记录，THEN THE Generation_Pipeline SHALL 将该情况记录为缺陷级别的诊断信息，包含缺失的 `wp_code` 与 `project_id`。
4. IF 某个 Working_Paper 记录的 `parsed_data` 字段为空或缺少 sheet 结构，THEN THE Generation_Pipeline SHALL 将该情况记录为缺陷级别的诊断信息，包含对应的 `wp_code`。
5. WHEN 验证者查询 Test_Project 的 `wp_index` 与 `working_paper` 表，THE Generation_Pipeline SHALL 使两表中同一 `wp_code` 的记录数保持一致。
### 需求 3：生成结果可在编辑器/HTML 渲染器中打开

**用户故事：** 作为审计助理，我希望生成出来的底稿能在前端底稿编辑器与 HTML 渲染器中正常打开并渲染，以便在 sheet_classification 种子数据就位后真正让 HTML 渲染器有底稿可渲、可编辑。

#### 验收标准

1. WHEN 操作者在编辑器中打开一张由 Generation_Pipeline 创建的 Working_Paper，THE Editor SHALL 加载该底稿的 `parsed_data` 并渲染其 sheet 内容。
2. WHEN 操作者打开一张 D 类底稿（如 D2-3 应收账款）的 Working_Paper，THE HTML_Renderer SHALL 根据 `workpaper_sheet_classification` 派生的 componentType 渲染该底稿，而非回退到空白或错误状态。
3. WHEN 操作者打开一张 B 目录底稿（如 B1 底稿目录）的 Working_Paper，THE HTML_Renderer SHALL 以 `b-index` componentType 渲染该底稿目录。
4. WHEN 操作者在 Test_Project 上完成生成后打开底稿，THE HTML_Renderer SHALL 至少成功渲染一张 D 类底稿与一张 B 目录底稿。
5. IF 某张 Working_Paper 缺少对应的 `workpaper_sheet_classification` 分类记录，THEN THE HTML_Renderer SHALL 按 `wp_code` 派生 componentType 进行渲染，并在诊断信息中标注该底稿缺少分类数据。
### 需求 4：标准科目落地澄清与规范

**用户故事：** 作为底稿取数逻辑维护者，我希望标准科目映射的落地方式被明确澄清并规范，以便消除「`tb_balance` 无 `standard_account_code` 而 `trial_balance` 有」造成的取数路径歧义，保证按标准科目取数的底稿能正确填充。

#### 验收标准

1. THE Generation_Pipeline SHALL 区分 TB_Balance（仅含 `account_code`）与 Trial_Balance（含 `standard_account_code`）两张表，并在文档中明确各自的数据来源与用途。
2. WHEN 某张底稿按标准科目取数，THE Generation_Pipeline SHALL 从 Trial_Balance 的 `standard_account_code` 取数，而非从 TB_Balance 的 `account_code` 取数。
3. WHERE 项目的 Trial_Balance 记录缺少 `standard_account_code`，THE Standard_Account_Mapping SHALL 将原始 `account_code` 映射为 `standard_account_code` 后供取数使用。
4. WHEN 验证者在 Test_Project 上检查按标准科目取数的底稿，THE Generation_Pipeline SHALL 使该底稿的取数结果与 Trial_Balance 中对应标准科目的余额一致。
5. IF 某个 `account_code` 无法映射到任何 `standard_account_code`，THEN THE Standard_Account_Mapping SHALL 记录该未映射科目，包含 `account_code` 与 `account_name`，并使生成流程继续处理其余科目。
### 需求 5：可重复性与幂等

**用户故事：** 作为审计项目负责人，我希望对同一项目重复执行底稿生成时已存在的底稿被正确跳过，以便重复执行不产生脏数据、不重复建记录，可以安全地多次运行生成流程。

#### 验收标准

1. WHEN Generation_Pipeline 处理一个已存在对应 Working_Paper 记录的 `wp_code`，THE Generation_Pipeline SHALL 跳过该 `wp_code` 的创建并将其计入已跳过数量。
2. WHEN 操作者对同一项目以相同 `wp_codes` 列表连续执行两次 generate-from-codes 调用，THE Generation_Pipeline SHALL 使该项目的 `working_paper` 记录数在两次调用后保持一致。
3. WHEN 操作者对同一项目以相同 `wp_codes` 列表连续执行两次 generate-from-codes 调用，THE Generation_Pipeline SHALL 使该项目的 `wp_index` 记录数在两次调用后保持一致。
4. WHILE Generation_Pipeline 跳过一个已存在的底稿，THE Generation_Pipeline SHALL 保留该底稿已有的 `parsed_data` 与 `bound_dataset_id` 不变。
5. WHEN Generation_Pipeline 完成一次包含跳过项的生成调用，THE Generation_Pipeline SHALL 在返回结果中分别列出新建的 `wp_code` 列表与跳过的 `wp_code` 列表。
### 需求 6：前置门禁与失败可诊断

**用户故事：** 作为审计助理，我希望底稿生成的前置条件不满足时能得到清晰可诊断的拦截原因，并且单张底稿失败不会中断整批生成，以便快速定位问题而不是面对静默失败或 500 错误。

#### 验收标准

1. IF Prerequisite_Checker 的 `generate_workpapers` 前置检查未通过，THEN THE Generation_Pipeline SHALL 返回 HTTP 422 状态码并附带说明未满足条件的中文诊断信息。
2. WHEN Prerequisite_Checker 拦截一次生成请求，THE Generation_Pipeline SHALL 在诊断信息中列出具体未满足的前置条件项，而非返回通用错误或 HTTP 500。
3. IF 某个 `wp_code` 在生成过程中抛出异常，THEN THE Generation_Pipeline SHALL 捕获该异常、记录该 `wp_code` 的失败原因，并继续处理列表中剩余的 `wp_code`。
4. WHEN Generation_Pipeline 完成一次包含失败项的生成调用，THE Generation_Pipeline SHALL 在返回结果中列出失败的 `wp_code` 及其对应的失败原因。
5. WHILE Generation_Pipeline 处理批量 `wp_codes`，THE Generation_Pipeline SHALL 使任一单个 `wp_code` 的失败不影响其余 `wp_code` 的 Wp_Index 与 Working_Paper 记录创建。
### 需求 7：验收标准升级为「真实数据跑通」

**用户故事：** 作为质控（QC）角色，我希望所有底稿生成相关功能的验收都建立在真实数据实跑出正确结果之上，以便杜绝「端点存在 grep / 单测绿」这类伪验收，确保交付的能力在真实项目上确实可用。

#### 验收标准

1. THE Generation_Pipeline SHALL 以 Test_Project（df5b8403，真实 8 万行序时账项目）作为所有功能验收的实跑数据基准。
2. WHEN 验证者验收任一底稿生成功能，THE Generation_Pipeline SHALL 要求验收证据为在 Test_Project 上实跑产生的真实结果，而端点存在性 grep 或单元测试通过不构成充分验收证据。
3. THE Generation_Pipeline SHALL 提供可执行的实跑验证步骤：对 Test_Project 调用 generate-from-codes、查询 `working_paper` 记录计数、在编辑器中打开生成的底稿。
4. WHEN 验证者执行实跑验证步骤，THE Generation_Pipeline SHALL 使 Test_Project 的 `working_paper` 计数大于 0 且至少一张 D 类底稿与一张 B 目录底稿可在编辑器中打开。
5. WHEN 验证者对真实 PG（容器 `audit-postgres`，库 `audit_platform`）执行查询验证，THE Generation_Pipeline SHALL 使 `wp_index`、`working_paper` 的真实记录数与生成调用返回的统计结果一致。
