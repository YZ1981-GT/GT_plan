# Requirements Document: 通用抽凭引擎组件

## Introduction

通用抽凭引擎组件（voucher-sampling-engine）从四表入库的 `tb_ledger` 表按审计师配置的抽样方法和条件自动提取凭证填充到抽凭底稿。审计抽凭是审计助理日常最高频操作之一，当前 D2-7（凭证抽样检查表）等底稿仍为手动录入方式。四表入库后 tb_ledger 已有完整凭证数据，应自动化这个流程。

本组件支持5种审计抽样方法（随机/金额分层/特定项目/系统/MUS），覆盖 CAS 1314 相关要求。支持预审/年审阶段隔离，版本链（历史抽凭记录对比），过程留痕可追溯。

**复用基础设施**：后端复用 `LedgerSamplingService`（cutoff-test-auto-sampling 定义）的 `build_ledger_query` / `execute_with_stats` / `record_extraction_log`，复用 `workpaper_extraction_log` 表（V095迁移），复用 `get_active_filter` 集成。在此基础上新增抽样方法学层、阶段隔离和版本链能力。

## Glossary

- **Sampling_Engine**: 抽凭引擎，后端按审计师配置的抽样方法从 tb_ledger 执行抽样算法的服务层
- **Sampling_Method**: 抽样方法，5种审计抽样算法之一（随机/金额分层/特定项目/系统/MUS）
- **Sampling_Config_Dialog**: 抽样条件配置弹窗，审计师选择抽样方法和配置参数的 el-dialog
- **Sampling_Preview_Dialog**: 抽样结果预览编辑弹窗，展示抽样结果供用户勾选和编辑的 el-dialog
- **Sampling_History_Drawer**: 抽凭历史侧栏，展示全部抽凭记录和版本对比的 el-drawer
- **Phase**: 审计阶段，取值 'preliminary'（预审）或 'final'（年审）
- **Coverage_Stats**: 覆盖率统计，包含笔数覆盖率和金额覆盖率
- **MUS**: 货币单元抽样（Monetary Unit Sampling），以货币单元为抽样单位的 PPS 抽样方法
- **Random_Seed**: 随机种子，用于保证抽样结果可复现的整数值
- **Fill_Strategy**: 填充策略，定义如何将抽样结果写入底稿（append/replace/merge）
- **LedgerSamplingService**: 通用序时账条件查询服务（cutoff spec 定义，本 spec 复用）
- **LedgerQueryFilters**: 通用查询过滤条件 Pydantic 模型（cutoff spec 定义，本 spec 复用）
- **GtVoucherSamplingEngine**: 通用抽凭引擎 Vue 组件，通过 props 配置化适用于多种底稿

## Requirements

### Requirement 1: 抽样方法选择与配置

**User Story:** As a 审计助理, I want to 在抽凭底稿中选择审计抽样方法并配置参数, so that 我能按 CAS 1314 要求客观确定抽样样本。

#### Acceptance Criteria

1. THE Sampling_Config_Dialog SHALL 以 el-radio-group 提供5种抽样方法选择：随机抽样、金额分层抽样、特定项目选取、系统抽样（等距）、MUS货币单元抽样
2. WHEN 用户选择随机抽样时, THE Sampling_Config_Dialog SHALL 显示参数配置区：样本量N（el-input-number，min=1，max=500）
3. WHEN 用户选择金额分层抽样时, THE Sampling_Config_Dialog SHALL 显示参数配置区：层级边界列表（动态增删行，每行含下限/上限金额 Decimal + 该层样本量 el-input-number）
4. WHEN 用户选择特定项目选取时, THE Sampling_Config_Dialog SHALL 显示参数配置区：重要性水平金额（el-input-number，Decimal 精度）+ 自定义条件组（可选：科目/摘要关键词/凭证类型）
5. WHEN 用户选择系统抽样时, THE Sampling_Config_Dialog SHALL 显示参数配置区：起始点（el-input-number，min=1）+ 间隔K（el-input-number，min=2）
6. WHEN 用户选择 MUS 货币单元抽样时, THE Sampling_Config_Dialog SHALL 显示参数配置区：样本量（el-input-number）+ 总体合计金额（只读，从查询统计自动计算）
7. THE Sampling_Config_Dialog SHALL 提供随机种子设置（el-input-number，可选），用于保证抽样结果可复现
8. THE Sampling_Config_Dialog SHALL 在用户点击"执行抽样"按钮时校验当前方法所有必填参数，校验失败时在对应字段下方显示红色提示

### Requirement 2: 通用过滤条件配置

**User Story:** As a 审计助理, I want to 配置抽样的通用过滤条件缩小抽样总体, so that 我能精确定义抽样范围。

#### Acceptance Criteria

1. THE Sampling_Config_Dialog SHALL 在抽样方法参数区下方显示通用过滤条件区（复用 LedgerQueryFilters 模型），包含：科目范围（el-select 多选，前缀匹配，默认=当前底稿关联科目编码）、期间范围（el-checkbox-group，会计月份 1-12 可多选）、金额范围（下限/上限 el-input-number，Decimal 精度）、方向（el-radio-group：借方/贷方/不限，默认不限）、凭证类型（el-checkbox-group：记/收/付/转/不限，默认不限）、摘要关键词（el-input，支持模糊匹配）
2. THE Sampling_Config_Dialog SHALL 提供"排除已抽过的凭证号"开关（el-switch，默认开启），启用时跨轮次去重防止重复抽取
3. WHEN "排除已抽过的凭证号"开关开启时, THE Sampling_Engine SHALL 从 workpaper_extraction_log 中查询该底稿历史抽凭记录的全部凭证号，将其加入 LedgerQueryFilters.exclude_voucher_nos 列表
4. THE Sampling_Config_Dialog SHALL 对科目范围支持前缀匹配（如输入"1122"匹配"112201"/"112202"等子科目）
5. THE Sampling_Config_Dialog SHALL 根据当前 phase（预审/年审）自动追加排除逻辑：年审阶段自动排除预审已抽到的凭证号

### Requirement 3: 抽样执行引擎

**User Story:** As a 审计助理, I want to 后端按配置的抽样方法从 tb_ledger 自动执行抽样算法, so that 我能快速获得符合统计学要求的凭证样本。

#### Acceptance Criteria

1. THE Sampling_Engine SHALL 通过 `POST /api/projects/{pid}/sampling/voucher-extract` 接收抽样请求，请求体包含：sampling_method（枚举5种）、sampling_params（JSON，各方法特有参数）、random_seed（可选整数）、phase（'preliminary'/'final'）、通用过滤条件（account_codes/period_range/amount_min/amount_max/direction_filter/voucher_type_filter/summary_keyword/exclude_extracted）、workpaper_id
2. THE Sampling_Engine SHALL 复用 LedgerSamplingService.build_ledger_query 构建基础查询，确保包含 project_id + year 安全隔离和 get_active_filter 数据集可见性
3. WHEN sampling_method 为 'random' 时, THE Sampling_Engine SHALL 在基础查询结果上使用 Python random.sample 随机抽取 N 笔，使用用户指定的 random_seed（未指定时自动生成并记录）
4. WHEN sampling_method 为 'stratified' 时, THE Sampling_Engine SHALL 按金额区间对基础查询结果分层，对每层分别执行 random.sample 抽取该层配置的样本量
5. WHEN sampling_method 为 'specific_item' 时, THE Sampling_Engine SHALL 从基础查询结果中筛选 GREATEST(COALESCE(debit_amount,0), COALESCE(credit_amount,0)) >= 重要性水平金额 的全部凭证
6. WHEN sampling_method 为 'systematic' 时, THE Sampling_Engine SHALL 将基础查询结果按 voucher_date + voucher_no 排序后，从起始点开始每隔 K 笔取 1 笔
7. WHEN sampling_method 为 'mus' 时, THE Sampling_Engine SHALL 使用累积金额法（cumulative monetary amount selection）：按凭证逐笔累积金额，以"总体金额/样本量"为间隔选取累积金额跨越间隔点的凭证
8. WHEN sampling_method 为 'mus' 且凭证金额为负时, THE Sampling_Engine SHALL 取绝对值参与权重计算
9. THE Sampling_Engine SHALL 返回抽样结果和统计信息：总体笔数、总体借方金额合计、总体贷方金额合计、样本笔数、样本借方金额合计、样本贷方金额合计、笔数覆盖率、金额覆盖率
10. THE Sampling_Engine SHALL 对所有金额字段使用 Decimal 精度（sa.Numeric(20,2)），返回时序列化为字符串避免浮点精度损失
11. IF 抽样结果超过 500 条, THEN THE Sampling_Engine SHALL 截断至 500 条并在响应中标记 truncated=true
12. THE Sampling_Engine SHALL 记录实际使用的 random_seed（含自动生成的情况），确保同参数+同种子重新执行可得到相同结果

### Requirement 4: 抽样结果预览编辑弹窗

**User Story:** As a 审计助理, I want to 在弹窗中预览抽样结果并可勾选编辑, so that 我能在填充前审核和调整样本。

#### Acceptance Criteria

1. THE Sampling_Preview_Dialog SHALL 在 el-dialog（宽度 80vw，最大高度 80vh）中以 el-table 展示抽样结果，列包含：勾选框 | 凭证号 | 凭证日期 | 摘要 | 借方金额 | 贷方金额 | 科目编码 | 科目名称 | 对方科目 | 凭证类型 | 会计期间 | 核查结果 | 备注
2. THE Sampling_Preview_Dialog SHALL 默认全部勾选，用户可取消勾选排除不适用的凭证
3. THE Sampling_Preview_Dialog SHALL 允许用户手动追加特定凭证：点击"追加"按钮弹出搜索框，从序时账中按凭证号/摘要/金额搜索选取
4. THE Sampling_Preview_Dialog SHALL 在表头上方显示抽样覆盖率统计卡片：总体笔数/金额 | 已勾选样本笔数/金额 | 笔数覆盖率% | 金额覆盖率%
5. THE Sampling_Preview_Dialog SHALL 允许用户 inline 编辑"核查结果"列（el-select：Y/N/异常，默认空）和"备注"列（el-input）
6. THE Sampling_Preview_Dialog SHALL 对金额列应用 displayPrefs.fmtAmount 格式化
7. WHEN 抽样结果超过 100 行时, THE Sampling_Preview_Dialog SHALL 启用 el-table 虚拟滚动以保证渲染性能
8. THE Sampling_Preview_Dialog SHALL 在底部显示填充策略选择和"确认填充"按钮

### Requirement 5: 预审/年审阶段隔离

**User Story:** As a 审计助理, I want to 抽凭结果按预审和年审阶段隔离管理, so that 年审抽凭不会覆盖预审数据且两阶段可独立查看。

#### Acceptance Criteria

1. THE GtVoucherSamplingEngine SHALL 对每行抽凭结果标记 phase 字段：'preliminary'（预审）或 'final'（年审），取值由当前操作阶段决定
2. WHEN 当前阶段为年审时, THE GtVoucherSamplingEngine SHALL 对预审阶段填充的行设为只读（不可编辑/不可删除），仅允许追加年审行
3. WHEN 当前阶段为年审时, THE Sampling_Engine SHALL 自动将预审已抽到的凭证号加入 exclude_voucher_nos，防止年审重复抽取预审已有凭证
4. THE GtVoucherSamplingEngine SHALL 提供三种视图模式切换（el-radio-group）：仅预审 | 仅年审 | 全量显示
5. WHEN 年审阶段执行填充时, THE Fill_Strategy SHALL 强制使用 append 模式（不允许 replace/merge 覆盖预审数据），填充结果追加到预审行之后
6. THE GtVoucherSamplingEngine SHALL 在视图切换时正确过滤显示行：仅预审模式只显示 phase='preliminary' 的行，仅年审模式只显示 phase='final' 的行

### Requirement 6: 版本链与历史对比

**User Story:** As a 现场经理, I want to 查看每次抽凭操作的完整历史记录并对比差异, so that 我能在 QC 复核时验证抽样的客观性和合规性。

#### Acceptance Criteria

1. THE Sampling_History_Drawer SHALL 复用 workpaper_extraction_log 表（extraction_type='voucher_sampling'），每次抽凭操作记录：时间戳 + 操作人 + 抽样方法 + 参数JSON + 随机种子 + 结果笔数 + 覆盖率 + phase
2. THE Sampling_History_Drawer SHALL 在 el-drawer 中按时间倒序展示该底稿全部抽凭记录列表，每条显示：操作时间 | 操作人 | 抽样方法 | 样本量 | 覆盖率 | 阶段标签，展开可查看完整参数详情JSON
3. THE Sampling_History_Drawer SHALL 支持"对比两次抽凭"功能：用户选择两条历史记录后，diff 展示新增行（绿色）/ 删除行（红色）/ 保留行（无标记），按凭证号匹配
4. THE Sampling_Engine SHALL 在每次填充前保存当前数据快照（before_data JSONB），支持撤销回滚
5. THE Sampling_History_Drawer SHALL 仅允许撤销最近一次非 undone 的填充操作（非最新记录的撤销按钮禁用）
6. THE Sampling_History_Drawer 记录 SHALL 不可物理删除，撤销操作仅标记 is_undone=true

### Requirement 7: 填充策略

**User Story:** As a 审计助理, I want to 选择不同的填充模式将抽样结果写入底稿, so that 我能灵活控制抽样数据如何与现有数据合并。

#### Acceptance Criteria

1. THE Fill_Strategy SHALL 支持三种模式：append（追加，默认）、replace（清空后重新填充）、merge（按凭证号去重合并）
2. WHEN 用户选择 append 模式时, THE Fill_Strategy SHALL 将已勾选的抽样结果追加到现有 samples 数组末尾，不影响已有行
3. WHEN 用户选择 replace 模式时, THE Fill_Strategy SHALL 先弹出 el-message-box 确认弹窗（"将覆盖现有N行数据，是否继续？"），确认后清空当前阶段的 samples 再填充
4. WHEN 用户选择 merge 模式时, THE Fill_Strategy SHALL 按凭证号（voucher_no）去重，已存在于 samples 中的凭证不重复添加，仅追加新凭证
5. WHEN 当前阶段为年审时, THE Fill_Strategy SHALL 强制使用 append 模式且禁用 replace/merge 选项（el-radio disabled + tooltip "年审阶段不可覆盖预审数据"）
6. THE Fill_Strategy SHALL 在填充完成后显示 el-message 成功提示（"成功填充N笔凭证"）

### Requirement 8: 执行留痕与合规性验证

**User Story:** As a 质量控制复核合伙人, I want to 验证每次抽凭的方法合规性和覆盖率充分性, so that 我能确保审计抽样符合 CAS 1314 要求。

#### Acceptance Criteria

1. THE Sampling_Engine SHALL 在 workpaper_extraction_log.extraction_criteria JSONB 中记录：sampling_method、sampling_params（完整参数JSON）、random_seed（实际使用值）、phase、coverage_stats（笔数覆盖率+金额覆盖率）
2. THE Sampling_Engine SHALL 记录完整操作留痕：操作人（从 auth context 获取 user_id）、操作时间戳、填充模式、总体笔数、实际填充笔数
3. THE GtVoucherSamplingEngine SHALL 自动计算并显示 CAS 1314 合规性提示：
   - WHEN 金额覆盖率 < 60% 时显示黄色警告"覆盖率偏低，建议增大样本量或调整抽样条件"
   - WHEN 特定项目选取的样本占比 > 50% 时显示提示"特定项目过多，建议增加随机样本补充"
   - WHEN MUS 样本量 < 期望样本量时显示提示"样本量不足"
4. THE Sampling_Engine 的留痕记录 SHALL 不可物理删除，撤销操作仅标记 is_undone=true
5. THE Sampling_History_Drawer SHALL 在 QC 复核视角下展示：抽样方法是否在5种合规方法内 + 种子是否由系统客观生成 + 覆盖率是否充分（>60%金额覆盖）

### Requirement 9: 结果二次编辑与批量操作

**User Story:** As a 审计助理, I want to 对填充到底稿的抽凭结果进行核查标记和批量操作, so that 我能高效完成凭证核查工作。

#### Acceptance Criteria

1. THE GtVoucherSamplingEngine SHALL 对已填充的每行支持 inline 编辑：核查结果（el-select：Y/N/异常，默认空）、异常标记（el-switch）、备注（el-input）
2. THE GtVoucherSamplingEngine SHALL 记录每次字段编辑的留痕：操作人 + 时间戳 + 字段名 + 旧值 + 新值，存入行级 edit_trail 数组
3. THE GtVoucherSamplingEngine SHALL 支持批量操作：全选（当前阶段行）→ 批量标记"已核查"（核查结果=Y）
4. WHEN 当前阶段为年审且行的 phase='preliminary' 时, THE GtVoucherSamplingEngine SHALL 禁止编辑该行（所有编辑控件 disabled）

### Requirement 10: 通用性设计与组件配置

**User Story:** As a 开发者, I want to 抽凭引擎组件支持配置化适用于不同科目底稿, so that 同一组件能复用于D2-7/D4-14/D4-15/E2-7等所有有凭证抽样需求的底稿。

#### Acceptance Criteria

1. THE GtVoucherSamplingEngine SHALL 通过以下 props 实现通用性：accountCode（string，关联科目编码）、phase（'preliminary'|'final'，当前审计阶段）、defaultMethod（Sampling_Method，默认抽样方法）、workpaperId（UUID，当前底稿ID）、projectId（UUID）、year（number）
2. THE GtVoucherSamplingEngine SHALL 适用于以下底稿（通过 props 配置差异化）：
   - D2-7 应收凭证抽查：accountCode="1122"，defaultMethod="random"
   - D4-14 收入发生检查：accountCode="6001"，defaultMethod="mus"
   - D4-15 收入完整性检查：accountCode="6001"，defaultMethod="random"
   - E2-7 应付凭证抽查：accountCode="2202"，defaultMethod="random"
3. THE GtVoucherSamplingEngine SHALL emit 'filled' 事件（payload 含填充的 samples 数组 + phase + fillMode），由父组件决定如何集成到自身数据结构
4. THE GtVoucherSamplingEngine SHALL emit 'phase-changed' 事件（payload 含新 phase 值），通知父组件阶段切换
5. THE GtVoucherSamplingEngine SHALL 作为独立 Vue 组件导出，可被任何抽凭底稿 Tab 通过 `<GtVoucherSamplingEngine :account-code="..." ... />` 方式嵌入

### Requirement 11: 与底稿现有功能集成

**User Story:** As a 审计助理, I want to 在D2凭证抽样Tab中使用自动抽凭功能, so that 我能同时使用自动抽凭和手动添加来完善凭证抽样检查表。

#### Acceptance Criteria

1. THE GtVoucherSamplingEngine SHALL 作为 D2TabVoucherCheck.vue 内嵌的"自动抽凭"功能区域，位于手动添加按钮上方
2. WHEN GtVoucherSamplingEngine emit 'filled' 事件时, THE D2TabVoucherCheck SHALL 将 payload 中的 samples 映射到 D2-7 凭证抽样明细表的列结构（voucher_no→凭证号、voucher_date→日期、debit_amount→借方金额、credit_amount→贷方金额、summary→摘要、counterpart_account→对方科目、account_code→科目编码）
3. THE D2TabVoucherCheck SHALL 保留现有手动"添加样本"按钮功能，自动抽凭与手动添加并存
4. THE GtVoucherSamplingEngine SHALL 将抽样参数区的数据（总体笔数/金额、样本量、抽样方法、覆盖率）自动回写到底稿参数区对应字段
5. WHEN 自动抽凭结果填充后, THE D2TabVoucherCheck SHALL 触发 debounce 自动保存（复用现有 2 秒 debounce 机制）

### Requirement 12: 抽样覆盖率计算

**User Story:** As a 审计助理, I want to 系统自动计算抽样覆盖率, so that 我能判断样本是否充分代表总体。

#### Acceptance Criteria

1. THE Sampling_Engine SHALL 自动计算笔数覆盖率：样本笔数 / 总体笔数 × 100%，精度保留两位小数
2. THE Sampling_Engine SHALL 自动计算金额覆盖率：样本金额合计 / 总体金额合计 × 100%，金额取 GREATEST(debit_amount, credit_amount) 的绝对值之和
3. THE GtVoucherSamplingEngine SHALL 在主界面持续显示当前覆盖率统计（实时更新），包含笔数覆盖率和金额覆盖率两个指标
4. THE Coverage_Stats SHALL 同时记录到 workpaper_extraction_log.extraction_criteria.coverage_stats 中，供 QC 复核查阅

### Requirement 13: 后端API端点

**User Story:** As a 开发者, I want to 有清晰定义的后端API支撑抽凭引擎前端功能, so that 前后端职责分离且接口稳定。

#### Acceptance Criteria

1. THE Sampling_Engine SHALL 提供 `POST /api/projects/{pid}/sampling/voucher-extract` 端点执行抽凭（含抽样算法），返回 { items: [...], stats: CoverageStats, truncated: bool }
2. THE Sampling_Engine SHALL 提供 `GET /api/projects/{pid}/sampling/voucher-history?wp_id={uuid}` 端点返回指定底稿的抽凭历史列表（按 created_at DESC）
3. THE Sampling_Engine SHALL 提供 `POST /api/projects/{pid}/sampling/voucher-undo?log_id={uuid}` 端点撤销指定抽凭操作，返回 before_data
4. THE Sampling_Engine SHALL 提供 `POST /api/projects/{pid}/sampling/voucher-compare` 端点对比两次抽凭记录，请求体含 log_id_a 和 log_id_b，返回 { added: [...], removed: [...], retained: [...] }
5. THE Sampling_Engine SHALL 复用 LedgerSamplingService 做基础查询构建，不重复实现查询逻辑

### Requirement 14: 数据库扩展

**User Story:** As a 开发者, I want to 复用已有的 workpaper_extraction_log 表存储抽凭日志, so that 无需新建表即可支撑抽凭引擎的留痕和版本链。

#### Acceptance Criteria

1. THE Sampling_Engine SHALL 复用 workpaper_extraction_log 表（V095迁移），使用 extraction_type='voucher_sampling' 区分于截止测试的 'cutoff' 类型
2. THE workpaper_extraction_log.extraction_criteria JSONB SHALL 对 voucher_sampling 类型包含以下字段：sampling_method（string）、sampling_params（object）、random_seed（integer）、phase（string）、coverage_stats（object: {count_rate, amount_rate}）
3. THE Sampling_Engine SHALL 使用已有索引 idx_extraction_log_wp_created（workpaper_id, created_at DESC）查询抽凭历史
4. THE Sampling_Engine SHALL 无需新建数据库表或迁移文件
