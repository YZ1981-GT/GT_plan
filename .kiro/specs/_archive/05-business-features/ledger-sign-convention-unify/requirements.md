# 账表符号约定统一 — 需求文档

## 引言

本特性统一账表数据入库时的金额符号约定，根治"入库层"与"下游层"符号约定不一致导致的试算表/报表借贷不平衡问题。

### 问题背景（已现状确认，实证）

当前系统存在两层互相打架的符号约定：

- **入库层**（`backend/app/services/ledger_import/converter.py` 的 `convert_balance_rows`）：
  `closing_balance = closing_debit - closing_credit`，采用 `v1_net_debit_positive`（借方为正、贷方为负）约定，导致负债/权益/收入科目的余额被存为**负数**。
- **下游层**（`backend/app/services/data_quality_service.py` 的 `_check_debit_credit_balance`）：
  已按 `account_category` 分方向汇总，注释明确"负债+权益+收入类，余额为正=贷方余额"，即下游**期望负债等科目存正数**。

两层约定冲突是此前"应交税费贷方正常余额被误判为负、试算表借贷不平衡"的真正根因。

### 目标

四表（`tb_balance` / `tb_aux_balance` / `tb_ledger` / `tb_aux_ledger`）入库时改为**按科目类别存自然正数**，源头统一后下游试算表、底稿、报表全部直接受益，不再各处临时判方向：

- 资产 / 成本 / 费用类 → 借方正常，存正数
- 负债 / 权益 / 收入类 → 贷方正常，存正数
- 平衡原则：会计恒等式"资产 = 负债 + 所有者权益"；分录级"借方类合计 = 贷方类合计"

### 现状已有产物（设计阶段需复用，勿重造）

- `backend/app/services/ledger_import/sign_convention_types.py` 已定义 `CURRENT_SIGN_CONVENTION = "v1_net_debit_positive"` 与方向来源枚举。
- V064 迁移已为四表加 `opening_direction` / `closing_direction` / `sign_convention_version` / `sign_anomaly_flags` 等方向字段。
- `backend/app/services/account_chart_service.py` 的 `_infer_category(code, name)` 已实现"名称关键词优先 + 编码首位兜底"的类别推断。
- 前端 `audit-platform/frontend/src/views/TrialBalance.vue` 的 `getDirection` 已有经过验证的资产备抵科目方向反向规则（正则）。

## 需求

### 需求 1：定义新符号约定（类别自然正数）

**用户故事：** 作为审计平台的数据架构维护者，我希望四表入库采用一套明确的、按科目类别存自然正数的符号约定，以便下游所有模块共享统一口径，消除符号歧义。

#### 验收标准

1. WHEN 系统定义符号约定版本 THEN 系统 SHALL 在 `sign_convention_types.py` 中新增版本标识（如 `v2_category_natural_positive`），与旧版 `v1_net_debit_positive` 并存且可区分。
2. WHEN 一条资产、成本或费用类科目余额入库 THEN 系统 SHALL 以借方为正常方向存储为正数。
3. WHEN 一条负债、权益或收入类科目余额入库 THEN 系统 SHALL 以贷方为正常方向存储为正数。
4. WHEN 一条记录按新约定写入 THEN 系统 SHALL 将该记录的 `sign_convention_version` 字段标记为新版本值。
5. IF 某科目余额方向与其类别的正常方向相反（如负债出现借方余额）THEN 系统 SHALL 保留该实际方向并以带符号方式如实存储，不强制翻为正数。

### 需求 2：科目类别与方向判断必须"编码 + 名称"双重判定

**用户故事：** 作为审计人员，我希望科目类别和借贷方向的判断同时依据科目编码和科目名称，而不是仅凭编码，以便正确处理那些编码归属与实际性质不符的科目。

#### 验收标准

1. WHEN 系统判断某科目的类别 THEN 系统 SHALL 同时使用科目编码和科目名称，且名称关键词匹配优先于编码前缀。
2. WHERE 已存在 `account_chart_service._infer_category(code, name)` 函数 THE 系统 SHALL 复用该函数进行类别推断，不新造一套并行逻辑。
3. IF 科目名称缺失或为空 THEN 系统 SHALL 退化为按编码前缀推断类别，并记录该判定的来源为低置信度。
4. WHEN 科目名称与编码前缀推断结果冲突 THEN 系统 SHALL 以名称关键词的判定为准。
5. WHEN 类别判定完成 THEN 系统 SHALL 在记录的方向来源字段中标注判定依据（名称匹配 / 编码兜底 / 用户覆盖等，对齐现有 `DirectionSource` 枚举）。

### 需求 3：资产备抵及反向科目方向特例处理

**用户故事：** 作为审计人员，我希望累计折旧、坏账准备、库存股等"备抵/反向"科目的方向被正确识别为与其编码大类相反，以便它们在试算表和报表中以正确符号列示。

#### 验收标准

1. WHEN 科目名称包含资产备抵关键词（累计折旧、累计摊销、坏账准备、各类减值准备、存货跌价准备、折耗等）THEN 系统 SHALL 将其正常方向判定为贷方（与其 1xxx 资产类编码相反）。
2. WHEN 科目名称命中"库存股"等权益备抵关键词 THEN 系统 SHALL 将其正常方向判定为借方（与其权益类编码相反）。
3. WHERE 前端 `TrialBalance.vue` 的 `getDirection` 已有经验证的备抵正则规则 THE 系统 SHALL 以该规则为基准在后端实现等价的备抵识别，保证前后端口径一致。
4. WHEN 备抵科目按其反向方向存储 THEN 系统 SHALL 在方向字段中标记实际方向，使下游能正确还原其对资产/权益的抵减效果。
5. IF 某科目同时命中多个方向关键词 THEN 系统 SHALL 以明确的优先级规则裁定唯一方向，并在设计文档中固化该优先级。

### 需求 4：入库时同步标记方向字段

**用户故事：** 作为下游报表/底稿模块，我希望每条入库记录除了正数金额外，还带有明确的借贷方向标记，以便我无需重新猜测就能决定该金额在报表中归入资产侧还是负债侧。

#### 验收标准

1. WHEN 一条余额记录入库 THEN 系统 SHALL 同时写入 `opening_direction` 和 `closing_direction`（取值 debit / credit），复用 V064 已有列。
2. WHEN 一条序时账/明细记录入库 THEN 系统 SHALL 写入该分录行的方向标记（对齐已有 `entry_direction` 字段）。
3. WHEN 方向字段被写入 THEN 系统 SHALL 一并写入方向来源（`*_direction_source`），标明该方向是显式列、借贷分列计算、类别推断还是用户覆盖。
4. IF 入库记录的金额为正数且方向已标记 THEN 下游模块 SHALL 能仅凭"金额 + 方向 + 类别"还原该科目在试算表/报表中的列示位置，无需再访问原始借贷列。
5. WHEN 方向与类别正常方向冲突（疑似异常）THEN 系统 SHALL 在 `sign_anomaly_flags` 中记录该异常，供诊断模块消费。

### 需求 5：改造 converter 入库写入逻辑

**用户故事：** 作为账表导入流程，我希望余额转换不再无脑地用"借方减贷方"，而是按科目类别与方向判定后存自然正数，以便入库结果与新符号约定一致。

#### 验收标准

1. WHEN `convert_balance_rows` / `convert_balance_rows_v2` 处理一行余额 THEN 系统 SHALL 先按需求 2、3 判定类别与方向，再按需求 1 存自然正数。
2. WHEN `convert_ledger_rows` / `convert_ledger_rows_v2` 处理一行分录 THEN 系统 SHALL 按同一套类别与方向规则标记 `entry_direction` 并保持金额口径一致。
3. WHERE 原始文件已含显式方向列（借/贷/D/C）THE 系统 SHALL 优先采用显式方向，而非重新推断。
4. WHERE 原始文件采用借贷分列（opening_debit / opening_credit）THE 系统 SHALL 按分列计算方向与金额，并转换为新约定正数。
5. WHEN converter 完成转换 THEN 转换结果的 `sign_convention_version` SHALL 为新版本，且不破坏既有的辅助维度拆分、主表去重等行为。
6. WHEN 同一账套被重复导入 THEN 新约定下的转换 SHALL 保持幂等（相同输入产生相同符号结果）。

### 需求 6：平衡校验口径统一

**用户故事：** 作为质量控制人员，我希望试算表、报表、调整分录、合并各环节的平衡校验在新符号约定下口径一致且通过，以便平衡结果真实反映数据正确性而非符号约定差异。

#### 验收标准

1. WHEN 系统执行分录级平衡校验 THEN 系统 SHALL 校验"借方类（资产+成本+费用）合计 = 贷方类（负债+权益+收入）合计"。
2. WHEN 系统执行报表级平衡校验 THEN 系统 SHALL 校验"资产合计 = 负债合计 + 所有者权益合计"。
3. WHERE 下游 `data_quality_service` / `consistency_gate` / `balance_diagnostics` 已按类别分方向校验 THE 系统 SHALL 以这些现有校验为目标态，使入库层向其对齐而非反向改动下游。
4. WHEN 损益类科目尚未结转到未分配利润 THEN 系统 SHALL 不简单套用"资产=负债+权益"，对齐 `cause_builders` 已有的损益未结转提示逻辑。
5. WHEN 新约定数据完成入库 THEN 一套完整、平衡的真实账套 SHALL 通过分录级平衡校验，差额 SHALL 在统一容差内（±1 元，容纳分/角舍入；该容差值在设计中固化为常量供各校验点共用）。
6. IF 现有校验逻辑因旧约定假设（如依赖 closing_balance 净额相消）而与新约定冲突 THEN 系统 SHALL 在设计中识别并调整这些冲突点，并以测试覆盖。
7. WHERE 调整分录（`adjustment_service`）的审定数 = 未调整数 + 调整数 THE 系统 SHALL 确认在未调整数符号变更后，调整数的符号规则与平衡校验同步对齐，使审定数计算正确。
8. WHERE 合并模块（`consol_report_service` / `cfs_worksheet_engine`）含独立的借贷平衡与"资产=负债+权益"校验 THE 系统 SHALL 在设计中盘点其符号假设并使其与新约定一致，且其既有容差（现为 1 元）与本需求统一。

### 需求 7：存量数据一次性迁移脚本

**用户故事：** 作为运维人员，我希望有一个一次性脚本把已入库的旧约定数据转换为新约定，以便切换约定后历史数据与新数据口径一致，不出现新旧混存导致的计算错误。

#### 验收标准

1. WHEN 运行迁移脚本 THEN 系统 SHALL 将旧约定（借正贷负）下负债/权益/收入类科目的余额符号翻转为新约定的自然正数。
2. WHEN 迁移脚本处理记录 THEN 系统 SHALL 同步补写/修正方向字段与 `sign_convention_version`，使迁移后记录标记为新版本。
3. WHEN 迁移脚本以 dry-run 模式运行 THEN 系统 SHALL 只统计将变更的行数与样例，不实际写库。
4. WHEN 迁移脚本实际执行 THEN 系统 SHALL 写审计留痕（迁移动作、影响行数、时间、操作者）。
5. WHEN 迁移脚本重复运行 THEN 系统 SHALL 幂等：已是新版本的记录不被再次翻转。
6. IF 某记录无法可靠判定类别/方向 THEN 系统 SHALL 跳过并记录到待人工复核清单，不擅自翻转。
7. WHEN 迁移完成 THEN 迁移后的数据 SHALL 通过需求 6 的平衡校验。
8. WHEN 迁移执行前 THEN 系统 SHALL 提供回退路径（迁移前快照或可逆翻转记录），使误判时能恢复到迁移前状态。
9. IF 迁移后平衡校验未通过或发现备抵科目漏覆盖 THEN 运维 SHALL 能通过回退路径恢复，并在修正规则后重跑迁移。

### 需求 8：回归测试与端到端实测验证

**用户故事：** 作为开发者，我希望新符号约定有完整的自动化测试和真实环境实测，以便确信改动不破坏既有功能且达成平衡目标。

#### 验收标准

1. WHEN 转换逻辑被测试 THEN 系统 SHALL 覆盖资产/负债/权益/收入/成本/费用各类、备抵科目反向、显式方向列、借贷分列等代表性场景，断言存储符号正确。
2. WHEN 平衡校验被测试 THEN 系统 SHALL 断言一套平衡账套在新约定下分录级与报表级校验均通过。
3. WHEN 迁移脚本被测试 THEN 系统 SHALL 断言旧约定数据迁移后符号正确、幂等、平衡通过。
4. WHEN 端到端实测执行 THEN 系统 SHALL 通过 Playwright 从前端验证：导入后试算表借方类合计=贷方类合计（差额≤容差）、报表平衡（资产=负债+权益）、底稿取数符号正确。
5. WHERE 使用 hypothesis 属性测试 THE 系统 SHALL 设置 `max_examples=5`（项目硬性约束，禁用默认 100）。

### 需求 9：tb_* 到 trial_balance 的符号传递一致性

**用户故事：** 作为报表/底稿模块，我希望从 tb_balance 生成 trial_balance 时符号不被二次翻转，以便下游消费的 `trial_balance.audited_amount` 与入库新约定口径一致。

#### 背景

下游真正消费的是 `trial_balance.audited_amount`（`data_quality_service` / `disclosure_engine` / 报表生成均读此字段），而非直接读 tb_*。tb_balance → trial_balance 存在生成步骤（`TrialBalanceService.full_recalc` / `chain_orchestrator._step_recalc_tb`）。若只改 tb_* 入库符号而生成逻辑仍按旧约定取数，符号会在中间环节被再翻一次，使整个改动失效。

#### 验收标准

1. WHEN `TrialBalanceService.full_recalc` 从 tb_balance 取数生成 trial_balance THEN 系统 SHALL 按新约定原样传递符号，不做基于旧约定的二次翻转。
2. WHEN trial_balance 记录生成 THEN 其 `audited_amount` / `unadjusted_amount` 等金额字段 SHALL 与来源 tb_balance 的新约定符号一致。
3. WHERE trial_balance 表存在或需要符号/方向标识 THE 系统 SHALL 在设计中确认其是否需同步携带约定版本或方向，避免下游无法区分。
4. WHEN 链路 tb_balance → trial_balance → financial_report 全程执行 THEN 各环节符号 SHALL 保持单一约定，端到端无符号翻转累积。
5. IF 生成逻辑中存在依赖旧约定（借正贷负）的取数或符号处理 THEN 系统 SHALL 在设计中识别并改造，以测试覆盖传递一致性。

### 需求 10：约定切换时点与过渡期语义

**用户故事：** 作为系统维护者，我希望明确新旧约定的切换时点和共存期下游的读数行为，以便迁移过程中不出现新旧混存导致的报表错误。

#### 验收标准

1. WHEN 本特性上线 THEN 系统 SHALL 明确定义切换时点：此后所有新导入按新约定写入并标记新版本。
2. WHILE 存量数据尚未迁移 THE 系统 SHALL 通过 `sign_convention_version` 区分每条/每数据集记录属于旧约定还是新约定。
3. WHEN 下游读取一个数据集的金额 THEN 系统 SHALL 能依据其约定版本采用正确的符号解释，不将 v1 数据按 v2 口径误读（反之亦然）。
4. IF 同一 project+year 出现 v1 与 v2 混存 THEN 系统 SHALL 有明确策略（优先要求迁移后再消费 / 按版本分别解释 / 阻断并提示），并在设计中固化该策略。
5. WHEN 迁移完成且数据集标记为新版本 THEN 下游 SHALL 统一按新约定消费，过渡期逻辑可安全退出。

### 需求 11：公式取数层符号一致性

**用户故事：** 作为底稿/报表的公式预填使用者，我希望 `=TB()` / `=TB_SUM()` / `=ADJ()` / `SUM_TB()` 等公式从 trial_balance 取数时符号与新约定一致，以便底稿和报表预填值正确。

#### 背景

`prefill_formula_mapping.json` 与 `report_config.formula` 中存在大量公式（`=TB('1122','期末余额')`、`=TB_SUM('1121~1122','期末余额')`、`=ADJ('1122','aje')`、`ROW(...)`），底稿单元格与报表行次通过这些公式从 trial_balance / adjustments 取数。TB 符号从负数变正数后，所有 `=TB(...)` 预填值随之变号；若公式求值器（formula_engine / data_fetch_custom / module_cell_resolver）隐含旧约定符号假设，底稿/报表预填会错。

#### 验收标准

1. WHEN 公式求值器（`data_fetch_custom` / `module_cell_resolver` / formula 预填路径）从 trial_balance 取数 THEN 系统 SHALL 按新约定原样返回符号，不做基于旧约定的隐式翻转。
2. WHERE `data_fetch_custom` 支持 `transform: direct|negate|abs|percentage` THE 系统 SHALL 盘点存量 `negate` 配置——这些配置可能是为纠正旧约定负数而设，新约定下会变成反向纠正。
3. IF 某 `negate` transform 配置原本用于纠正旧约定符号 THEN 迁移 SHALL 一并识别并处理（移除或反置），并记入待复核清单。
4. WHEN TB 改为正数后执行公式预填 THEN 典型案例（如 `=TB('2202','期末余额')` 应付账款）SHALL 预填为符合预期的正数。
5. WHEN 公式取数层被测试 THEN 系统 SHALL 覆盖 TB/TB_SUM/ADJ 公式在新约定下的求值符号正确性。

## 非功能性约束

1. **改动范围**：本特性改源头（四表入库符号），跨 `tb_balance`/`tb_aux_balance`/`tb_ledger`/`tb_aux_ledger` 四表，并影响试算表、底稿、报表三大下游。须走完整 spec 三件套（requirements → design → tasks）。
2. **复用优先**：复用 `_infer_category`、V064 方向字段、`sign_convention_types.py`、`TrialBalance.vue getDirection` 规则，禁止新造并行逻辑。
3. **向后兼容**：新旧约定版本并存且可识别；迁移完成前下游须能区分记录属于哪个约定版本。
4. **数据安全**：迁移脚本须 dry-run 可预览、幂等、有审计留痕、无法判定时不擅改。
5. **PG 运维**：迁移涉及的 SQL 须遵循项目 PG 规范（PG-only 语句加方言检测，按 account_category 翻符号用 set-based UPDATE）。
6. **语言**：用户可见文本与文档中文（技术术语保留英文）。
