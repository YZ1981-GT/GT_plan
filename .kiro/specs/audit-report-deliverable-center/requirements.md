# 需求文档：审计报告交付件管理中心

## 简介

审计报告交付件管理中心（Deliverable Center）为审计项目提供统一的交付物生命周期管理能力。当前系统的附注/报表/审计报告导出仅以浏览器 blob 直接下载形式完成，不保留导出记录，不支持版本管理，无法满足审计完成阶段对交付物的追溯、协作和归档需求。

本功能将构建一个集「选择性导出 → 平台留存 → 版本管理 → 在线预览 → 在线编辑 → 审批流 → 归档」为一体的交付物管理中心，与底稿 A 循环（完成与报告阶段）深度关联，作为审计完成阶段的核心产出管理入口。

## 术语表

- **Deliverable_Center**：交付件管理中心，前端页面模块，展示项目所有交付物的列表、版本链和状态流
- **Export_Dialog**：导出选择弹窗，用户在触发导出时弹出的章节/表格选择面板
- **Deliverable**：交付物实体，一次导出操作产生的逻辑记录（对应后端 `word_export_task` 表的扩展）
- **Version_Chain**：版本链，同一交付物多次导出形成的有序版本序列
- **Export_Task_Service**：后端已有的导出任务服务（`export_task_service.py`）
- **Approval_Flow**：审批流，交付物从 draft 到 final 需经项目经理/合伙人确认的流程
- **Completeness_Check**：完整性检查，验证项目审计报告三件套（报告+报表+附注）是否齐全
- **Online_Editor**：在线编辑器，基于 OnlyOffice Document Server 的 Word/Excel 文档在线编辑能力（docx 用 Document Editor，xlsx 用 Spreadsheet Editor）
- **OnlyOffice_Server**：OnlyOffice Document Server，作为独立服务（Docker 容器）部署的文档协同编辑引擎，提供 docx/xlsx 的高保真在线编辑、JWT 鉴权加载与保存回调能力，与现有本地优先架构一致
- **Archive_Lock**：归档锁定，交付物标记为已归档后不可编辑的状态
- **A_Cycle**：审计循环 A（完成与报告阶段），审计报告/报表/附注是该阶段的核心产出
- **Data_Snapshot**：数据快照，交付物生成时刻底层数据（试算表、底稿、附注）的版本或哈希记录，用于交付物溯源，对接已有的 `report_snapshot_service`
- **EQCR_Gate**：质量复核关卡，交付物进入 confirmed/signed 状态前必须通过的项目质量复核（Engagement Quality Control Review）校验点
- **Hash_Chain**：哈希链，每个交付物版本文件哈希按序写入的防篡改链式记录，遵循项目「审计只写哈希链」治理裁定
- **Permission_Matrix**：权限矩阵，定义各角色对交付物各类操作（导出、预览、编辑、审批、归档等）的访问控制规则，确保职责分离
- **Standard_Trio**：标准三件套，标准年度审计的核心交付物组合，由审计报告正文 + 财务报表 + 附注三类交付物构成
- **Special_Report**：专项报告，标准三件套之外的各类专项业务交付物，如专项审计报告、内控鉴证报告、约定程序报告、验资报告等
- **Audit_Report_Editor**：审计报告正文编辑器（AuditReportEditor），生成 audit_report 数据的源模块，其产出作为审计报告正文交付物的来源
- **Event_Linkage**：事件驱动联动链，已实现的数据更新传播机制（TRIAL_BALANCE_UPDATED → REPORTS_UPDATED → 附注更新 + 审计报告财务数据刷新），由 event_bus.py / event_handlers.py 实现
- **Opinion_Type**：审计意见类型，审计报告正文的核心结论分类，依据 CSA 1501/1502/1503/1504 准则共 5 类：标准无保留意见（unqualified）、带强调事项段的无保留意见（unqualified_with_emphasis）、保留意见（qualified）、否定意见（adverse）、无法表示意见（disclaimer）
- **Emphasis_Paragraph**：强调事项段，在不影响无保留意见的前提下，提醒报告使用者关注财务报表中已恰当列报或披露事项的可编辑段落
- **KAM**：关键审计事项（Key Audit Matters），审计师根据职业判断认为对本期财务报表审计最为重要的事项，每个事项条目含「事项描述 + 审计应对」结构
- **PIE**：公共利益实体（Public Interest Entity），包括上市公司及其他对公众利益负有重大责任的实体，对关键审计事项披露负有强制要求
- **Report_Body_JSON**：审计报告正文结构化段落 JSON 主源，审计报告正文交付物的主数据源，以段落数组形式存储（每个段落含 section_name 段落名称、section_order 段落顺序、content 段落内容、is_required 是否必需、可编辑空白块等字段），用于占位符替换、段落级增删与 KAM 多条目管理，生成时由该主源渲染为 HTML（在线预览）与 docx（交付下载）
- **Placeholder_Mapping_Registry**：占位符映射注册表，维护命名占位符到数据源路径映射关系的可配置注册表，将自动映射类占位符（如 {entity_name}、{entity_short_name}、{audit_period}、{report_scope}、{signing_partner}、{report_date}）与财务数据类占位符（如 {total_assets}、{total_revenue}、{net_profit}）映射到对应数据源路径（项目信息、financial_report 报表行等），支持新增占位符无需改动核心渲染逻辑
- **Report_Date_Compliance**：报告日期合规校验，对审计报告日期是否符合审计准则约束（不早于注册会计师获取充分适当审计证据之日，通常等于或晚于管理层/治理层批准财务报表之日）进行校验的能力，报告日期作为可校验字段而非纯文本占位符
- **Prior_Period_Info**：上期比较信息，审计报告中对上期财务报表比较数据的审计情形标注及相应措辞处理，区分本所前期审计、前任注册会计师审计、上期未经审计三种情形

## 交付优先级分级 (P0/P1/P2)

为实现功能收敛、避免一次实施摊子过大，本规格将各需求按交付优先级分为三级。落地实施时按 P0 → P1 → P2 的顺序推进。

- **P0 核心闭环**：需求 1（选择性导出）、需求 2（双路径存储）、需求 3（中心页面）、需求 4（版本管理）、需求 5（在线预览）、需求 21（生成入口一致性）、需求 24（报告正文模板 + 占位符映射）、需求 22（意见类型模板矩阵）、需求 23（KAM 处理）
- **P1 质量与合规**：需求 8（完整性检查）、需求 13（数据快照溯源）、需求 19（三件套数据一致性）、需求 14（签章 + EQCR）、需求 17（权限矩阵）、需求 25（报告日期合规）、需求 28（OnlyOffice 降级）、需求 29（callback 鉴权）
- **P2 增强**：需求 6（OnlyOffice 在线编辑）、需求 7（审批流）、需求 10/30（打包下载 + 异步）、需求 11（归档锁定）、需求 12（水印）、需求 15（哈希链）、需求 16（编辑回写边界）、需求 9（A 循环关联）、需求 18（正文纳入体系，与 24 配合）、需求 20（专项报告扩展）、需求 26（上期比较）、需求 27（项目生命周期联动）

> **说明**：P2 中部分项可在 P0/P1 稳定后迭代。OnlyOffice 在线编辑（需求 6）依赖 OnlyOffice 部署，故归入 P2。

## 需求

### 需求 1：选择性导出

**用户故事：** 作为审计师，我希望在导出附注/报表/审计报告时能选择具体章节或表格，以便只导出当前需要的内容而非全量。

#### 验收标准

1. WHEN 用户点击导出按钮, THE Export_Dialog SHALL 弹出并展示当前文档的全部章节和表格列表供勾选
2. THE Export_Dialog SHALL 默认全选所有章节和表格
3. WHEN 用户取消选择部分章节后点击确认, THE Export_Dialog SHALL 仅将被勾选的章节内容传递给导出引擎
4. WHEN 用户未勾选任何章节, THE Export_Dialog SHALL 禁用确认按钮并提示至少选择一个章节
5. THE Export_Dialog SHALL 支持按文档类型（审计报告、财务报表、附注）展示不同的章节结构树
6. WHEN 导出的文档类型为附注, THE Export_Dialog SHALL 以附注目录结构为选择项，支持展开/折叠层级选择

### 需求 2：双路径存储（本地下载 + 平台留存）

**用户故事：** 作为审计师，我希望导出文件既下载到本地又保存到平台，以便在团队协作时随时找回历史导出物。

#### 验收标准

1. WHEN 导出任务完成, THE Export_Task_Service SHALL 同时将文件保存到平台存储并触发浏览器下载
2. THE Export_Task_Service SHALL 将每次导出产生的文件元信息（文件名、大小、类型、导出者、导出时间、选择的章节列表）记录到 Deliverable 表
3. IF 平台存储写入失败, THEN THE Export_Task_Service SHALL 仍然完成浏览器下载并以 toast 警告用户平台留存失败
4. IF 浏览器下载被阻止, THEN THE Export_Task_Service SHALL 仍然完成平台存储并提示用户可从交付管理中心重新下载
5. THE Export_Task_Service SHALL 对接已有的 ExportTask 状态机流程（draft→generating→generated→editing→confirmed→signed）

### 需求 3：交付管理中心前端页面

**用户故事：** 作为项目经理，我希望有一个集中的页面查看所有历史导出物及其版本，以便追踪交付进度和管理文件。

#### 验收标准

1. THE Deliverable_Center SHALL 展示当前项目的所有交付物列表，按文档类型分组（审计报告、财务报表、附注、全套包）
2. THE Deliverable_Center SHALL 为每个交付物显示：文件名、版本号、文档类型、导出者、导出时间、当前状态、文件大小
3. WHEN 用户点击某交付物的版本号, THE Deliverable_Center SHALL 展开显示该交付物的完整版本链（所有历史版本按时间倒序排列）
4. THE Deliverable_Center SHALL 提供按文档类型、状态、时间范围的筛选功能
5. THE Deliverable_Center SHALL 提供关键字搜索（匹配文件名和导出者）
6. WHEN 用户点击下载按钮, THE Deliverable_Center SHALL 触发对应版本文件的浏览器下载
7. THE Deliverable_Center SHALL 在页面顶部显示交付物完整性状态（三件套是否齐全）

### 需求 4：版本管理

**用户故事：** 作为审计师，我希望每次重新导出同类文档时自动生成新版本，以便回溯对比不同版本的变化。

#### 验收标准

1. WHEN 用户对同一文档类型再次执行导出, THE Export_Task_Service SHALL 自动创建新版本记录并递增版本号
2. THE Version_Chain SHALL 保留所有历史版本文件不做删除，直到交付物被归档
3. THE Deliverable_Center SHALL 支持任意两个版本之间的元信息对比（导出时间、章节选择差异、文件大小差异）
4. WHEN 交付物状态为 confirmed 或 signed, THE Export_Task_Service SHALL 在用户再次导出时创建新的独立交付物而非追加版本

### 需求 5：在线预览

**用户故事：** 作为审计师，我希望在平台内直接预览已导出的 Word/PDF 文档，而无需下载到本地打开。

#### 验收标准

1. WHEN 用户在 Deliverable_Center 点击预览按钮, THE Deliverable_Center SHALL 在弹窗或新面板中渲染文档内容
2. THE Deliverable_Center SHALL 支持 .docx 格式文件的在线预览（复用已有 @vue-office/docx 组件）
3. THE Deliverable_Center SHALL 支持 .pdf 格式文件的在线预览（复用已有 @vue-office/pdf 组件）
4. IF 文件格式不支持在线预览, THEN THE Deliverable_Center SHALL 显示提示并提供下载链接
5. WHILE 文档正在加载预览, THE Deliverable_Center SHALL 显示加载进度指示器

### 需求 6：在线编辑

> **交付优先级：分阶段交付。** P1 阶段先实现只读预览能力（见需求 5）；P2 阶段再实现本节基于 OnlyOffice 的在线编辑能力。采用 OnlyOffice Document Server 而非 TipTap 的原因：OnlyOffice 对 Word/Excel 的编辑保真度更高（保留复杂格式、表格、样式），可规避 docx↔富文本双向转换的格式丢失问题；单项目并发编辑人数少（小团队），OnlyOffice 的协同编辑能力已足够，不构成可扩展性瓶颈。

**用户故事：** 作为审计师，我希望在平台内直接编辑已导出的 Word/Excel 文档，以便在不离开平台的情况下高保真地修改交付物内容。

#### 验收标准

1. WHEN 用户在 Deliverable_Center 点击编辑按钮, THE Online_Editor SHALL 通过集成 OnlyOffice_Server 在前端嵌入 OnlyOffice 编辑器打开文档的在线编辑视图
2. WHERE 交付物为 docx 文档, THE Online_Editor SHALL 以 OnlyOffice Document Editor 模式加载；WHERE 交付物为 xlsx 报表, THE Online_Editor SHALL 以 OnlyOffice Spreadsheet Editor 模式加载
3. WHEN 编辑器加载交付物文件, THE Online_Editor SHALL 通过 OnlyOffice 的 config 配置与 JWT 鉴权加载该交付物文件
4. WHEN 用户在 OnlyOffice 编辑器中保存编辑内容, THE OnlyOffice_Server SHALL 通过回调地址（callback URL）将编辑后的文件回传平台，且 THE Export_Task_Service SHALL 据此创建新版本记录
5. WHILE 交付物状态为 confirmed 或 signed, THE Online_Editor SHALL 以只读模式打开 OnlyOffice 编辑器
6. WHILE 交付物状态为 archived, THE Online_Editor SHALL 以只读模式打开 OnlyOffice 编辑器并显示归档锁定提示
7. THE OnlyOffice_Server SHALL 作为独立服务以 Docker 容器形式部署，与现有本地优先架构保持一致

### 需求 7：交付物审批流

**用户故事：** 作为合伙人，我希望交付物须经审批确认后才能标记为最终版，以确保文件质量和合规性。

#### 验收标准

1. WHEN 审计师提交交付物审批请求, THE Approval_Flow SHALL 将交付物状态从 editing 变更为 pending_approval
2. WHEN 项目经理或合伙人批准审批, THE Approval_Flow SHALL 将交付物状态变更为 confirmed 并记录审批人和审批时间
3. WHEN 审批人驳回审批, THE Approval_Flow SHALL 将交付物状态退回 editing 并记录驳回原因
4. THE Approval_Flow SHALL 在审批请求提交和审批完成时通知相关用户（站内消息）
5. THE Deliverable_Center SHALL 在交付物状态栏显示当前审批进度和审批人

### 需求 8：交付物完整性检查

**用户故事：** 作为项目经理，我希望系统自动检查审计报告三件套是否完整，以确保交付物在归档前无遗漏。

#### 验收标准

1. THE Completeness_Check SHALL 验证项目是否已生成审计报告、财务报表（至少含资产负债表和利润表）、附注三类交付物
2. WHEN 任一类交付物缺失, THE Completeness_Check SHALL 在 Deliverable_Center 顶部显示缺失项的警告提示
3. WHEN 所有三件套均存在且至少有一个版本状态为 confirmed, THE Completeness_Check SHALL 显示完整性通过的绿色标识
4. THE Completeness_Check SHALL 在用户尝试归档项目时自动执行，若不通过则阻止归档操作

### 需求 9：底稿 A 循环关联

**用户故事：** 作为审计师，我希望交付管理中心与底稿 A 循环（完成与报告阶段）关联，以便从底稿视角直接访问核心交付物。

#### 验收标准

1. THE Deliverable_Center SHALL 在底稿 A 循环（完成与报告阶段）的侧边导航中提供快捷入口
2. WHEN 用户从 A 循环底稿页面点击交付物入口, THE Deliverable_Center SHALL 自动筛选显示与当前项目关联的交付物
3. THE Deliverable_Center SHALL 在 A 循环底稿的阶段概览区域显示交付物完整性摘要
4. WHEN 交付物状态变更（如新版本创建或审批完成）, THE Deliverable_Center SHALL 同步更新 A 循环底稿的阶段进度标记

### 需求 10：交付物打包下载

**用户故事：** 作为审计师，我希望能一键下载整套审计报告（报告+报表+附注），以便提交给客户时保证文件完整。

#### 验收标准

1. WHEN 用户在 Deliverable_Center 点击打包下载按钮, THE Deliverable_Center SHALL 将所有 confirmed 状态的最新版本交付物打包为 ZIP 文件并触发下载
2. IF 三件套不完整, THEN THE Deliverable_Center SHALL 在打包前警告用户缺失项，并允许用户选择是否继续
3. THE Deliverable_Center SHALL 在 ZIP 内按文档类型建立子目录（审计报告/财务报表/附注）
4. THE Deliverable_Center SHALL 在 ZIP 内包含一份交付物清单文件（deliverable_manifest.txt），列出文件名、版本号和状态

### 需求 11：归档与锁定

**用户故事：** 作为项目经理，我希望将交付物标记为已归档后锁定编辑，以确保已完结项目的交付物不被意外修改。

#### 验收标准

1. WHEN 项目经理点击归档按钮, THE Deliverable_Center SHALL 将项目所有 confirmed/signed 状态的交付物变更为 archived 状态
2. WHILE 交付物状态为 archived, THE Deliverable_Center SHALL 禁止任何编辑和新版本创建操作
3. THE Deliverable_Center SHALL 在归档操作前执行完整性检查，若不通过则提示并要求确认
4. IF 需要解除归档, THEN THE Deliverable_Center SHALL 仅允许 admin 角色执行解除操作，并记录操作日志

### 需求 12：交付物水印支持

> **交付优先级：P2 可选。** 本需求为增强项，不阻塞 P1 核心交付流程，可在核心能力稳定后再行实现。

**用户故事：** 作为合伙人，我希望未最终确认的交付物在预览和下载时带有"草稿"水印，以防止未定稿文件被误用。

#### 验收标准

1. WHILE 交付物状态为 draft 或 editing, THE Deliverable_Center SHALL 在预览时叠加半透明"草稿 DRAFT"水印
2. WHILE 交付物状态为 draft 或 editing, THE Export_Task_Service SHALL 在生成下载文件时嵌入"草稿"水印
3. WHEN 交付物状态变更为 confirmed 或 signed, THE Export_Task_Service SHALL 生成无水印的正式版本供下载

### 需求 13：数据快照溯源绑定

**用户故事：** 作为审计师，我希望导出交付物时锁定底层数据快照，以便交付物可追溯到生成时刻的数据状态。

#### 验收标准

1. WHEN 导出任务完成, THE Export_Task_Service SHALL 记录本次交付物绑定的 Data_Snapshot 标识与哈希（试算表、底稿、附注的版本或哈希）
2. THE Export_Task_Service SHALL 在交付物元信息中记录其绑定的 Data_Snapshot 引用
3. THE Export_Task_Service SHALL 通过已有的 report_snapshot_service 生成并读取 Data_Snapshot
4. WHEN 用户预览交付物, THE Deliverable_Center SHALL 对比交付物绑定的 Data_Snapshot 哈希与当前底层数据哈希
5. IF 当前底层数据哈希与交付物绑定的 Data_Snapshot 哈希不一致, THEN THE Deliverable_Center SHALL 显示数据已过时（stale）提示

### 需求 14：电子签章与 EQCR 复核衔接

**用户故事：** 作为合伙人，我希望交付物在 EQCR（项目质量复核）通过后才能进入 confirmed/signed 状态，并支持签章信息记录，以确保交付物符合质量复核要求。

#### 验收标准

1. WHEN 用户请求将交付物变更为 confirmed 状态, THE EQCR_Gate SHALL 验证该项目的 EQCR 复核已通过
2. IF 项目 EQCR 复核未通过, THEN THE EQCR_Gate SHALL 阻止交付物进入 confirmed 状态并提示需先完成 EQCR 复核
3. WHEN 交付物变更为 signed 状态, THE Approval_Flow SHALL 记录签章人、签章时间与签章类型（项目合伙人 / 复核合伙人）
4. WHERE 当前用户角色为 EQCR 复核角色, THE Deliverable_Center SHALL 对交付物仅提供只读访问

### 需求 15：交付物哈希链与防篡改

**用户故事：** 作为合伙人，我希望每个交付物版本写入哈希链，以便归档后可验证交付物未被篡改（遵循项目「审计只写哈希链」治理裁定）。

#### 验收标准

1. WHEN 生成或编辑产生新的交付物版本, THE Hash_Chain SHALL 计算该版本文件哈希并写入哈希链
2. THE Hash_Chain SHALL 提供完整性校验能力，校验当前文件哈希与链上记录是否一致
3. IF 当前文件哈希与 Hash_Chain 链上记录不一致, THEN THE Hash_Chain SHALL 返回完整性校验失败结果并标识被篡改的版本
4. WHEN 交付物归档, THE Hash_Chain SHALL 记录最终哈希作为防篡改基线

### 需求 16：在线编辑回写边界

**用户故事：** 作为系统，我需要在线编辑交付物时只修改交付物副本而不回写源附注/报表数据，以避免源数据与交付物分叉造成不一致。

#### 验收标准

1. WHEN 用户在线编辑交付物, THE Online_Editor SHALL 仅修改交付物 docx 副本，源附注/报表数据保持不变
2. WHEN 用户预览交付物且其绑定的源数据在编辑后已更新, THE Deliverable_Center SHALL 提示交付物可能已与最新源数据不一致
3. WHERE 用户需使用最新源数据生成交付物, THE Deliverable_Center SHALL 引导用户重新导出生成新交付物，而非编辑旧版本

### 需求 17：交付物操作权限矩阵

**用户故事：** 作为系统管理者，我希望有清晰的权限矩阵控制各角色对交付物的操作，以确保职责分离。

#### 验收标准

1. WHERE 用户角色为审计师及以上, THE Permission_Matrix SHALL 允许执行交付物导出/创建操作
2. WHERE 用户为项目成员（含 EQCR 只读角色）, THE Permission_Matrix SHALL 允许执行交付物预览/下载操作
3. WHERE 用户角色为审计师及以上且交付物状态不为 confirmed/signed/archived, THE Permission_Matrix SHALL 允许执行在线编辑操作
4. WHERE 用户角色为项目经理或合伙人, THE Permission_Matrix SHALL 允许执行交付物审批操作
5. WHERE 用户角色为项目经理及以上, THE Permission_Matrix SHALL 允许执行交付物归档操作
6. WHERE 用户角色为 admin, THE Permission_Matrix SHALL 允许执行交付物解除归档操作
7. WHERE 用户角色为 EQCR 复核角色, THE Permission_Matrix SHALL 对交付物全程仅提供只读访问

### 需求 18：审计报告正文纳入交付物体系

**用户故事：** 作为审计师，我希望审计报告正文与财务报表、附注并列作为标准三件套交付物，统一在交付中心管理，以便对核心交付物进行一致的版本、预览、编辑与归档管理。

#### 验收标准

1. THE Deliverable_Center SHALL 将审计报告正文作为与财务报表、附注并列的标准交付物类型进行管理
2. THE Export_Task_Service SHALL 以 Audit_Report_Editor 生成的 audit_report 数据作为审计报告正文交付物的来源
3. WHEN 用户对审计报告正文执行选择性导出, THE Export_Dialog SHALL 支持审计报告正文的段落级选择（见需求 1）
4. THE Deliverable_Center SHALL 将 Standard_Trio（审计报告正文 + 财务报表 + 附注）识别为标准年度审计交付物组合

### 需求 19：三件套数据一致性校验

**用户故事：** 作为项目经理，我希望系统校验标准三件套交付物是否基于同一数据快照生成，以避免出现报表已重算但附注或审计报告仍是旧数据就交付的情况。

#### 验收标准

1. THE Export_Task_Service SHALL 为 Standard_Trio 中每个交付物记录其绑定的 Data_Snapshot 标识（数据版本或哈希），数据更新通过已有 Event_Linkage（TRIAL_BALANCE_UPDATED → REPORTS_UPDATED → 附注更新 + 审计报告财务数据刷新）传播
2. WHEN 用户执行打包或交付操作, THE Completeness_Check SHALL 校验 Standard_Trio 各交付物绑定的 Data_Snapshot 是否来自同一次数据更新（同一数据版本或哈希）
3. IF Standard_Trio 各交付物绑定的 Data_Snapshot 不一致（如报表为新数据而附注为旧数据）, THEN THE Completeness_Check SHALL 在打包或交付前显示数据不一致警告，并提示用户先重新生成滞后的交付物
4. THE Completeness_Check SHALL 在原有齐全性检查（见需求 8）基础上同时执行数据一致性检查，二者均通过方视为完整性通过

> **design 阶段可行性说明**：本需求依赖 report_snapshot_service 能为审计报告正文、报表、附注三类交付物生成统一的快照标识。design 阶段需验证三类交付物的快照粒度可对齐；若不可对齐，需设计统一快照封装层以统一三类交付物的 Data_Snapshot 标识。

### 需求 20：专项报告扩展性

**用户故事：** 作为系统，我希望交付物类型可扩展，除标准三件套外还能纳入各类专项报告（如专项审计报告、内控鉴证报告、约定程序报告、验资报告等），以便交付中心适配多种审计业务类型。

#### 验收标准

1. THE Deliverable_Center SHALL 以可扩展的枚举或配置定义交付物文档类型（doc_type），且不将类型硬编码为仅 Standard_Trio
2. WHERE 系统新增 Special_Report 类型, THE Deliverable_Center SHALL 无需改动核心逻辑即可对其提供列表、版本、预览、编辑与归档的通用管理能力
3. THE Completeness_Check SHALL 按项目类型配置必需件清单（标准年报审计对应 Standard_Trio；专项业务对应相应的 Special_Report）
4. WHEN 项目类型为专项业务, THE Completeness_Check SHALL 依据该项目类型配置的必需件清单执行齐全性检查

### 需求 21：三类核心交付物生成入口一致性

**用户故事：** 作为审计师，我希望报表、附注、审计报告正文三类核心交付物都有一致、显眼的"生成"入口，以便获得统一的操作体验。

#### 验收标准

1. THE Deliverable_Center SHALL 在报表页提供显眼的"生成报表"按钮，复用已有的 generateReports 一键生成能力
2. THE Deliverable_Center SHALL 在附注页提供显眼的"生成附注"按钮
3. THE Deliverable_Center SHALL 在审计报告页提供显眼的"生成报告"按钮
4. WHEN 用户点击任一生成入口, THE Deliverable_Center SHALL 在生成前执行前置检查，校验生成所需的底层数据是否就绪
5. WHILE 生成任务执行中, THE Deliverable_Center SHALL 显示一致的进度反馈
6. WHEN 生成任务完成, THE Deliverable_Center SHALL 显示一致的生成结果提示
7. THE Deliverable_Center SHALL 使报表、附注、审计报告三处生成入口的交互模式（前置检查、进度反馈、结果提示）保持一致

### 需求 22：审计报告意见类型模板矩阵

**用户故事：** 作为审计师，我希望审计报告正文模板覆盖全部审计意见类型，并按公司类型（国企/上市）区分，以便针对不同审计结论生成正确的报告正文。

#### 验收标准

1. THE Deliverable_Center SHALL 提供覆盖 5 类 Opinion_Type 的审计报告正文模板：标准无保留意见（unqualified）、带强调事项段的无保留意见（unqualified_with_emphasis）、保留意见（qualified）、否定意见（adverse）、无法表示意见（disclaimer）
2. THE Deliverable_Center SHALL 按"Opinion_Type × 公司类型（国企 soe/non_listed + 上市 listed）"的组合提供审计报告正文模板
3. WHERE Opinion_Type 为带强调事项段的无保留意见（unqualified_with_emphasis）, THE Deliverable_Center SHALL 在标准无保留意见模板基础上增加可编辑的 Emphasis_Paragraph
4. WHERE Opinion_Type 为保留意见（qualified）、否定意见（adverse）或无法表示意见（disclaimer）, THE Deliverable_Center SHALL 在模板中包含"形成X意见的基础"段落以说明保留、否定或无法表示意见的事由
5. WHEN 用户生成审计报告正文, THE Export_Task_Service SHALL 按项目选定的 Opinion_Type 与公司类型加载对应的审计报告正文模板
6. WHERE 审计报告正文包含 Emphasis_Paragraph 或其他事项段, THE Deliverable_Center SHALL 将其作为可选段落，允许用户按需增加或删除

### 需求 23：关键审计事项（KAM）差异化处理

**用户故事：** 作为审计师，我希望系统按公司类型/主体性质正确处理关键审计事项段，以符合上市公司及公共利益实体（PIE）的披露要求。

#### 验收标准

1. WHERE 项目为上市公司或公共利益实体（PIE）, THE Deliverable_Center SHALL 在审计报告正文中强制包含 KAM 段且为必填
2. WHERE 项目为非上市且非 PIE 主体, THE Deliverable_Center SHALL 将 KAM 段作为可选段落，允许包含或省略
3. WHERE Opinion_Type 为无法表示意见（disclaimer）, THE Deliverable_Center SHALL 不出具 KAM 段
4. IF 上市或 PIE 项目在审计报告定稿（final）前 KAM 段为空, THEN THE Deliverable_Center SHALL 阻止定稿并提示 KAM 为必填项，沿用现有 KAM 校验逻辑
5. THE Deliverable_Center SHALL 支持 KAM 段包含多个事项条目，且每个条目含"事项描述 + 审计应对"结构

### 需求 24：审计报告正文模板选择与占位符自动映射

**用户故事：** 作为审计师，我希望按项目选择对应的报告正文模板和审计意见类型后，系统自动将公司名称、简称、财务数据等占位符映射填充并随上游变更自动刷新，点击"生成正文"后保存到交付管理中心，以便高效生成数据准确、随源变更保持同步的审计报告正文。

#### 验收标准

1. WHEN 用户按项目选择审计报告正文模板（Opinion_Type 与公司类型的组合）, THE Deliverable_Center SHALL 加载对应的 Report_Body_JSON 段落模板
2. THE Export_Task_Service SHALL 以 Report_Body_JSON（结构化段落 JSON）作为审计报告正文交付物的主数据源进行存储
3. WHEN 加载 Report_Body_JSON 模板, THE Export_Task_Service SHALL 按 Placeholder_Mapping_Registry 将自动映射类占位符（公司全称 {entity_name}、公司简称 {entity_short_name}、审计期间 {audit_period}、报告口径 {report_scope}、签字人 {signing_partner}、报告日期 {report_date}）从项目信息提取并填充
4. WHEN 加载 Report_Body_JSON 模板, THE Export_Task_Service SHALL 按 Placeholder_Mapping_Registry 将财务数据类占位符（资产总计 {total_assets}、营业收入 {total_revenue}、净利润 {net_profit} 等）从 financial_report 报表行提取并填充
5. THE Export_Task_Service SHALL 将手工填写类占位符（如 [请填写保留意见事项]、[请添加关键审计事项]）保留为可编辑提示文本，由用户填写
6. WHEN 上游财务数据通过 Event_Linkage（REPORTS_UPDATED → AuditReportService.on_reports_updated）发生变更, THE Export_Task_Service SHALL 自动刷新 Report_Body_JSON 中的财务数据类占位符
7. WHEN 用户点击"生成正文", THE Export_Task_Service SHALL 由 Report_Body_JSON 主源渲染 HTML（用于在线预览）与 docx（用于交付下载），绑定 Data_Snapshot 数据快照（见需求 13），并保存到 Deliverable_Center 创建新版本（见需求 2 与需求 4）
8. THE Placeholder_Mapping_Registry SHALL 为可配置且可扩展，新增占位符 SHALL 无需改动核心渲染逻辑

### 需求 25：审计报告日期合规校验

**用户故事：** 作为合伙人，我希望审计报告日期符合准则约束，避免报告日期早于审计证据获取完成日或财务报表批准日，以确保报告日期合规。

#### 验收标准

1. THE Report_Date_Compliance SHALL 校验审计报告日期不早于注册会计师获取充分适当审计证据之日
2. THE Report_Date_Compliance SHALL 校验审计报告日期等于或晚于管理层/治理层批准财务报表之日
3. IF 用户设定的报告日期早于 EQCR 复核通过日或财务报表批准日, THEN THE Report_Date_Compliance SHALL 警告并要求用户确认
4. THE Report_Date_Compliance SHALL 将报告日期作为可校验字段处理，而非纯文本占位符

### 需求 26：上期比较信息处理

**用户故事：** 作为审计师，我希望审计报告正确处理上期比较信息的措辞，区分首次接受委托与连续审计，以符合上期比较信息的责任披露要求。

#### 验收标准

1. THE Deliverable_Center SHALL 支持标注上期比较数据的审计情形：本所前期审计、前任注册会计师审计、上期未经审计
2. WHERE 为首次接受委托（前任注册会计师审计或上期未经审计）, THE 审计报告正文 SHALL 包含相应的"其他事项段"说明上期比较信息的责任
3. THE Deliverable_Center SHALL 将 Prior_Period_Info 作为已知扩展维度，由 design 阶段细化具体模板措辞

### 需求 27：交付物与项目生命周期联动

**用户故事：** 作为项目经理，我希望交付中心的归档状态与项目整体生命周期联动，避免状态不一致，以保证交付物状态与项目阶段一致。

#### 验收标准

1. WHEN 项目整体归档, THE Deliverable_Center SHALL 同步将其交付物置为 archived 状态
2. WHEN 交付物全部归档完成, THE Deliverable_Center SHALL 反映到项目阶段状态，标记完成与报告阶段完结
3. THE Deliverable_Center SHALL 使交付物状态与项目生命周期（进行中、已完成、已归档）保持一致

### 需求 28：OnlyOffice 服务不可用降级

> **工程健壮性，重要。** 遵循项目三级降级风格。

**用户故事：** 作为系统，我希望在 OnlyOffice 服务不可用时优雅降级，避免编辑功能整体瘫痪，以保证核心交付能力不中断。

#### 验收标准

1. IF OnlyOffice_Server 不可用, THEN THE Online_Editor SHALL 降级为只读预览（@vue-office）并提示用户下载到本地编辑
2. THE Deliverable_Center SHALL 在 OnlyOffice 不可用时仍保证预览、下载、版本管理等核心功能可用
3. THE Deliverable_Center SHALL 提供 OnlyOffice 服务健康检查

### 需求 29：OnlyOffice 回调安全鉴权

> **安全刚需。**

**用户故事：** 作为系统，我希望 OnlyOffice 保存回调（callback）必须经过鉴权校验，防止伪造回调覆盖交付物，以保证交付物的安全完整。

#### 验收标准

1. WHEN OnlyOffice_Server 通过 callback URL 回传文件, THE Export_Task_Service SHALL 校验回调请求的 JWT 签名
2. IF callback 的 JWT 签名校验失败, THEN THE Export_Task_Service SHALL 拒绝该回调并记录安全日志
3. THE Export_Task_Service SHALL 仅接受来自已配置 OnlyOffice 服务的合法 callback 请求

### 需求 30：打包下载异步化与进度反馈

**用户故事：** 作为审计师，我希望打包下载全套交付物（可能数十 MB）异步执行并显示进度，避免阻塞，以获得流畅的打包下载体验。

#### 验收标准

1. WHEN 用户触发打包下载（见需求 10）, THE Export_Task_Service SHALL 以异步任务执行打包
2. WHILE 打包任务执行中, THE Deliverable_Center SHALL 通过 SSE（复用现有 event_bus.broadcast_raw 机制）显示打包进度
3. WHEN 打包完成, THE Deliverable_Center SHALL 提供 ZIP 下载链接
