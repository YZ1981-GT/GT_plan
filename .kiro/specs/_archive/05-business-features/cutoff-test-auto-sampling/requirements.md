# Requirements Document: 通用截止测试自动提取组件

## Introduction

通用截止测试自动提取组件（cutoff-test-auto-sampling），从四表入库的 tb_ledger 表按用户自定义条件自动查询凭证并填充到截止测试底稿。审计截止测试的核心逻辑是检查资产负债表日前后的交易是否正确记录在正确的会计期间。当前平台截止测试Tab为手动录入（逐笔手填发票号/日期/金额），效率极低。四表入库后 tb_ledger 已有完整序时账数据，应自动提取填充。

本组件为跨科目通用组件，适用于D2截止测试/D4-17收入截止(账到单据)/D4-18收入截止(单据到账)/F2出入库截止等所有截止性测试sheet。后端查询逻辑将抽取为 `LedgerSamplingService`，后续 voucher-sampling-engine（抽凭引擎）将复用此service。

## Glossary

- **Cutoff_Test_Panel**: 截止条件配置面板，用户输入提取条件的UI区域
- **Extraction_Engine**: 自动提取引擎，后端从tb_ledger按条件SQL查询的服务层
- **LedgerSamplingService**: 通用序时账条件查询服务，被截止测试和抽凭引擎共享
- **Preview_Dialog**: 预览编辑弹窗，提取结果在el-dialog中展示供用户勾选编辑
- **Fill_Strategy**: 填充策略，定义如何将提取结果写入底稿数据（append/replace/merge）
- **Extraction_Log**: 提取日志，记录每次提取的时间戳+操作人+条件+结果的审计留痕
- **Cutoff_Judgment**: 跨期自动判定逻辑，根据截止测试类型自动标记可能跨期的凭证
- **Balance_Sheet_Date**: 资产负债表日（截止基准日），默认12月31日
- **Active_Dataset**: 通过get_active_filter查询的当前有效数据集
- **Workpaper_Snapshot**: 底稿数据快照，填充前自动保存的当前samples的JSON副本

## Requirements

### Requirement 1: 截止条件配置面板

**User Story:** As a 审计助理, I want to 在截止测试底稿中配置自动提取条件, so that 我能按截止测试需要精确定义凭证筛选范围。

#### Acceptance Criteria

1. THE Cutoff_Test_Panel SHALL 显示以下可配置条件字段：截止基准日（el-date-picker，默认=项目年度12月31日）、前窗口天数（el-input-number，默认5）、后窗口天数（el-input-number，默认10）、金额阈值（el-input-number，Decimal精度，默认0表示不限）、科目范围（el-select多选+前缀匹配，默认=当前底稿关联科目编码）、方向过滤（el-radio-group：借方/贷方/不限，默认不限）、凭证类型过滤（el-checkbox-group：记/收/付/转/不限，默认不限）、摘要关键词（el-input，支持模糊匹配）、排除已提取凭证（el-switch，默认开启）
2. WHEN 用户打开截止测试Tab时, THE Cutoff_Test_Panel SHALL 根据当前底稿关联科目自动填充科目范围默认值（如D2截止→1122，D4-17→6001，F2-25→1405/1403）
3. WHEN 用户修改截止基准日时, THE Cutoff_Test_Panel SHALL 自动重新计算日期窗口（基准日-前窗口天数 至 基准日+后窗口天数）并显示计算后的日期范围文字提示
4. THE Cutoff_Test_Panel SHALL 对科目范围支持前缀匹配（如输入"1122"匹配"112201"/"112202"等子科目）
5. WHEN 用户点击"开始提取"按钮时, THE Cutoff_Test_Panel SHALL 校验必填字段（截止基准日+科目范围），校验失败时在对应字段下方显示红色校验提示
6. THE Cutoff_Test_Panel SHALL 通过props接收当前底稿的配置参数（accountCode/cutoffDirection/defaultConditions），实现跨科目通用性

### Requirement 2: 后端自动提取引擎

**User Story:** As a 审计助理, I want to 后端从tb_ledger按条件自动提取凭证, so that 我能快速获得符合截止测试条件的凭证样本。

#### Acceptance Criteria

1. THE Extraction_Engine SHALL 通过 `POST /api/projects/{pid}/sampling/cutoff-extract` 接收提取请求，请求体包含：cutoff_date、days_before、days_after、amount_threshold、account_codes（列表）、direction_filter、voucher_type_filter、summary_keyword、exclude_extracted、workpaper_id、page、page_size
2. THE LedgerSamplingService SHALL 使用 `get_active_filter` 构建查询条件，确保只查询 active dataset 的数据
3. THE LedgerSamplingService SHALL 必须在查询中包含 `project_id = :pid AND year = :year` 条件实现安全隔离
4. THE LedgerSamplingService SHALL 对 account_codes 参数使用 `account_code LIKE ANY(:prefixes)` 实现前缀匹配（如 "1122" 匹配所有 "1122%" 的科目）
5. THE Extraction_Engine SHALL 对 voucher_date 构建范围条件：`voucher_date >= (cutoff_date - days_before) AND voucher_date <= (cutoff_date + days_after)`
6. WHEN direction_filter 为 "debit" 时, THE Extraction_Engine SHALL 添加 `debit_amount > 0` 条件；当为 "credit" 时添加 `credit_amount > 0` 条件
7. WHEN amount_threshold > 0 时, THE Extraction_Engine SHALL 添加 `GREATEST(COALESCE(debit_amount,0), COALESCE(credit_amount,0)) >= :threshold` 条件
8. WHEN summary_keyword 非空时, THE Extraction_Engine SHALL 添加 `summary ILIKE :pattern` 模糊匹配条件
9. THE Extraction_Engine SHALL 分页返回结果（默认page_size=50），同时返回统计摘要：总匹配笔数、借方合计金额、贷方合计金额、按凭证类型分类的笔数
10. IF 匹配结果超过500条, THEN THE Extraction_Engine SHALL 返回前500条数据并在响应中标记 `truncated=true` 和 `total_matched` 总数，提示用户收紧条件
11. THE Extraction_Engine SHALL 对所有金额字段使用 Decimal 精度（sa.Numeric(20,2)），返回时序列化为字符串避免浮点精度损失
12. WHEN exclude_extracted=true 时, THE Extraction_Engine SHALL 排除已在 workpaper_extraction_log 中记录过的凭证号（基于 workpaper_id + voucher_no 去重）

### Requirement 3: 预览编辑弹窗

**User Story:** As a 审计助理, I want to 在弹窗中预览提取结果并可勾选编辑, so that 我能在填充前审核和筛选凭证样本。

#### Acceptance Criteria

1. THE Preview_Dialog SHALL 在 el-dialog（宽度80vw，最大高度80vh）中以 el-table 展示提取结果，列包含：勾选框 | 凭证号 | 凭证日期 | 摘要 | 借方金额 | 贷方金额 | 科目编码 | 科目名称 | 对方科目 | 凭证类型 | 跨期判定 | 备注
2. THE Preview_Dialog SHALL 自动计算并显示"跨期判定"列（基于 voucher_date 与 cutoff_date 的比对结果，参见 Requirement 6 的判定逻辑）
3. THE Preview_Dialog SHALL 默认全部勾选，用户可取消勾选排除不需要的凭证
4. THE Preview_Dialog SHALL 允许用户编辑"备注"列（el-input inline编辑）
5. THE Preview_Dialog SHALL 在表头上方显示统计信息卡片：已勾选笔数/总笔数 | 跨期笔数 | 借方合计（已勾选）| 贷方合计（已勾选）
6. WHEN 跨期判定为"可能跨期"时, THE Preview_Dialog SHALL 以红色字体+背景高亮该行
7. THE Preview_Dialog SHALL 对金额列应用 displayPrefs.fmtAmount 格式化（千分位/负数红色括号/零值"-"）
8. WHEN 提取结果超过100行时, THE Preview_Dialog SHALL 启用 el-table 虚拟滚动以保证渲染性能
9. THE Preview_Dialog SHALL 在底部显示填充策略选择（el-radio-group）和"确认填充"按钮

### Requirement 4: 填充策略

**User Story:** As a 审计助理, I want to 选择不同的填充模式将提取结果写入底稿, so that 我能灵活控制提取数据如何与现有数据合并。

#### Acceptance Criteria

1. THE Fill_Strategy SHALL 支持三种模式：append（追加）、replace（替换）、merge（合并去重）
2. WHEN 用户选择 append 模式时, THE Fill_Strategy SHALL 将已勾选的提取结果追加到现有 samples 数组末尾，不影响已有行
3. WHEN 用户选择 replace 模式时, THE Fill_Strategy SHALL 先弹出 el-message-box 确认弹窗（"将覆盖现有N行数据，是否继续？"），确认后清空现有 samples 再填充已勾选结果
4. WHEN 用户选择 merge 模式时, THE Fill_Strategy SHALL 按凭证号（voucher_no）去重，已存在于 samples 中的凭证不重复添加，仅追加新凭证
5. THE Fill_Strategy SHALL 在填充完成后显示 el-message 成功提示（"成功填充N笔凭证，其中跨期M笔"）
6. THE Fill_Strategy SHALL 将提取的凭证数据映射为目标底稿的 samples 数据结构（字段映射：voucher_no→凭证号、voucher_date→凭证日期、debit_amount→借方金额、credit_amount→贷方金额、summary→摘要、counterpart_account→对方科目）

### Requirement 5: 执行留痕与提取历史

**User Story:** As a 现场经理, I want to 查看每次自动提取的完整记录, so that 我能在QC复核时验证抽样的客观性和完整性。

#### Acceptance Criteria

1. THE Extraction_Log SHALL 在每次执行填充时记录：操作时间戳（created_at）、操作人（user_id，从auth context获取）、提取条件JSON（extraction_criteria）、匹配总笔数（total_matched）、实际填充笔数（filled_count）、填充模式（fill_mode）、底稿ID（workpaper_id）、填充前数据快照（before_data JSON）
2. THE Extraction_Log SHALL 存储于新表 `workpaper_extraction_log`（需新增迁移 V095）
3. WHEN 用户点击"提取历史"按钮时, THE Extraction_Log SHALL 在侧栏面板（el-drawer）显示该底稿的所有提取记录列表，按时间倒序排列
4. THE Extraction_Log 每条记录 SHALL 显示：操作时间 | 操作人 | 填充模式 | 填充笔数 | 展开可查看完整提取条件JSON
5. `GET /api/projects/{pid}/sampling/cutoff-history?wp_id=` SHALL 返回指定底稿的提取历史列表，按 created_at DESC 排序
6. THE Extraction_Log SHALL 支持通过 `POST /api/projects/{pid}/sampling/cutoff-undo?log_id=` 执行撤销操作，将 samples 回滚到 before_data 状态
7. WHEN 用户点击某条历史记录的"撤销"按钮时, THE Extraction_Log SHALL 弹出确认弹窗（"将回滚到本次填充前的状态，是否继续？"），确认后执行回滚并刷新底稿数据
8. THE Extraction_Log SHALL 仅允许撤销最近一次填充操作（非最新记录的撤销按钮禁用并tooltip提示"仅可撤销最近一次操作"）

### Requirement 6: 跨期自动判定逻辑

**User Story:** As a 审计助理, I want to 系统自动判定凭证是否可能跨期, so that 我能快速聚焦需要重点核查的样本。

#### Acceptance Criteria

1. THE Cutoff_Judgment SHALL 支持以下判定模式（通过props传入cutoffDirection配置）：
   - "post_cutoff"（后截止，D2类型）：voucher_date > cutoff_date 且方向=借方 → 标记"可能跨期"
   - "pre_cutoff"（前截止，E2类型）：voucher_date < cutoff_date 且方向=贷方 → 标记"可能跨期"  
   - "window"（通用窗口）：voucher_date 在日期窗口内即标记"待检查"
2. THE Cutoff_Judgment SHALL 对每条凭证返回判定结果：枚举值为 "可能跨期" | "待检查" | "正常"
3. WHEN cutoffDirection 未指定时, THE Cutoff_Judgment SHALL 使用 "window" 模式作为默认判定逻辑
4. THE Cutoff_Judgment SHALL 在 Preview_Dialog 的"跨期判定"列和填充后的底稿数据中均显示判定结果
5. THE Cutoff_Judgment SHALL 在 Preview_Dialog 统计信息中显示"可能跨期"和"待检查"的笔数及金额合计
6. THE Cutoff_Judgment SHALL 作为纯函数实现（determineCutoffStatus），接受 voucher_date、cutoff_date、direction、amount 参数，返回判定枚举值，便于前后端共用

### Requirement 7: 通用性设计与组件配置

**User Story:** As a 开发者, I want to 截止测试自动提取组件支持配置化适用于不同科目, so that 同一组件能复用于D2/D4-17/D4-18/F2/E2等所有截止性测试sheet。

#### Acceptance Criteria

1. THE Cutoff_Test_Panel SHALL 通过以下props实现通用性：accountCode（string，关联科目编码）、cutoffDirection（"post_cutoff"|"pre_cutoff"|"window"，截止判定方向）、defaultConditions（object，默认提取条件覆盖）、workpaperId（UUID，当前底稿ID）、projectId（UUID）、year（number）
2. THE Cutoff_Test_Panel SHALL 适用于以下底稿（通过props配置差异化）：
   - D2 截止测试Tab：accountCode="1122"，cutoffDirection="post_cutoff"
   - D4-17 收入截止(账到单据)：accountCode="6001"，cutoffDirection="post_cutoff"
   - D4-18 收入截止(单据到账)：accountCode="6001"，cutoffDirection="pre_cutoff"
   - F2-25 存货截止测试：accountCode="1405,1403"，cutoffDirection="window"
   - E2 截止测试：accountCode="2202"，cutoffDirection="pre_cutoff"
3. THE Cutoff_Test_Panel SHALL 作为独立Vue组件 `GtCutoffAutoSampling.vue` 导出，可被任何截止测试Tab通过 `<GtCutoffAutoSampling :account-code="..." ... />` 方式嵌入
4. THE LedgerSamplingService SHALL 作为独立service模块（`backend/app/services/ledger_sampling_service.py`），不依赖任何特定底稿逻辑，仅依赖 tb_ledger 模型和 dataset_query
5. THE Cutoff_Test_Panel SHALL emit 'filled' 事件（payload含填充的samples数组），由父组件决定如何集成到自身数据结构

### Requirement 8: 与现有D2截止测试集成

**User Story:** As a 审计助理, I want to 在D2截止测试Tab中使用自动提取功能, so that 我能同时使用自动提取和手动添加来完善截止测试样本。

#### Acceptance Criteria

1. THE Cutoff_Test_Panel SHALL 作为D2TabCutoff.vue内嵌的"自动提取"功能区域，位于手动添加按钮上方
2. WHEN GtCutoffAutoSampling emit 'filled' 事件时, THE D2TabCutoff SHALL 将payload中的samples按当前填充策略合并到 useD2Cutoff 的 samples 响应式数组中
3. THE D2TabCutoff SHALL 保留现有手动"添加样本"按钮功能，自动提取与手动添加并存
4. THE D2TabCutoff SHALL 在已有样本行中标记数据来源（"自动提取"/"手动添加"），以便复核时区分
5. WHEN 自动提取结果填充后, THE D2TabCutoff SHALL 触发 debounce 自动保存（复用现有2秒debounce机制）

### Requirement 9: 版本快照与撤销

**User Story:** As a 审计助理, I want to 在每次自动填充前自动保存底稿快照, so that 我能在填充结果不符预期时一键撤销恢复。

#### Acceptance Criteria

1. WHEN 用户确认填充操作时, THE Fill_Strategy SHALL 在执行填充前自动将当前 samples 数据序列化为JSON并存入 workpaper_extraction_log.before_data 字段
2. THE workpaper_extraction_log.before_data SHALL 使用 JSONB 类型存储，记录填充前的完整 samples 数组状态
3. WHEN 用户执行撤销操作时, THE Extraction_Engine SHALL 从对应 log 记录读取 before_data，反序列化后替换当前 samples 数组，并触发自动保存
4. WHEN 撤销成功后, THE Extraction_Log SHALL 将该条记录标记为 `is_undone=true`，已撤销的记录在历史列表中显示灰色删除线样式
5. IF before_data 为空（首次填充前底稿无数据）, THEN THE Fill_Strategy SHALL 存储空数组 `[]` 作为 before_data

### Requirement 10: 与 voucher-sampling-engine 的共享层

**User Story:** As a 开发者, I want to 截止测试的后端查询逻辑可被抽凭引擎复用, so that 两个功能共享同一套经过测试的查询构建器。

#### Acceptance Criteria

1. THE LedgerSamplingService SHALL 提供以下可复用方法：
   - `build_ledger_query(project_id, year, filters: LedgerQueryFilters) -> Select`：构建带条件的SQLAlchemy Select对象
   - `execute_with_stats(db, query, page, page_size) -> tuple[list[dict], StatsResult]`：执行查询并返回分页数据+统计摘要
   - `record_extraction_log(db, log_data: ExtractionLogCreate) -> ExtractionLog`：记录提取日志
2. THE LedgerQueryFilters SHALL 定义为Pydantic模型，包含：date_range（start/end）、account_codes（list[str]）、amount_threshold（Decimal）、direction_filter（str）、voucher_type_filter（list[str]）、summary_keyword（str）、exclude_voucher_nos（list[str]）
3. THE LedgerSamplingService SHALL 内置 `get_active_filter` 调用，外部调用者无需关心 dataset 可见性逻辑
4. THE StatsResult SHALL 包含：total_count（int）、debit_total（Decimal）、credit_total（Decimal）、by_voucher_type（dict[str, int]）、truncated（bool）

### Requirement 11: 数据库迁移

**User Story:** As a 开发者, I want to 新增 workpaper_extraction_log 表存储提取日志和快照, so that 执行留痕和撤销功能有持久化存储支撑。

#### Acceptance Criteria

1. THE workpaper_extraction_log 表 SHALL 包含以下列：id（UUID PK）、project_id（UUID FK projects.id NOT NULL）、workpaper_id（UUID FK working_papers.id NOT NULL）、user_id（UUID NOT NULL）、extraction_type（VARCHAR(50) NOT NULL，值为 'cutoff'/'voucher_sampling'）、extraction_criteria（JSONB NOT NULL）、total_matched（INTEGER NOT NULL）、filled_count（INTEGER NOT NULL）、fill_mode（VARCHAR(20) NOT NULL，值为 'append'/'replace'/'merge'）、before_data（JSONB）、is_undone（BOOLEAN DEFAULT FALSE）、created_at（TIMESTAMP DEFAULT now()）
2. THE workpaper_extraction_log 表 SHALL 创建索引：`idx_extraction_log_wp_created`（workpaper_id, created_at DESC）用于历史查询
3. THE 迁移文件 SHALL 命名为 V095_create_workpaper_extraction_log.sql，使用 `IF NOT EXISTS` 防重复执行
4. THE workpaper_extraction_log 表 SHALL 创建索引：`idx_extraction_log_project`（project_id）用于项目级查询

