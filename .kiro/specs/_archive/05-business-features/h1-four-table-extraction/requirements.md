# Requirements Document

## Introduction

H1 固定资产的四表库（`tb_balance` / `trial_balance` / `tb_ledger` / `tb_aux_balance`）取数目前只覆盖**审定表 H1-1 一层**（按分类预填未审数）。作为整个 H1 数据中枢的 **H1-2 明细表没有任何四表库取数入口**——H1-4/H1-7/H1-8/H1-9/H1-10/H1-16/H1-17/H1-18/H1-19 与上市/国企披露表全部从 H1-2 带入，而 H1-2 自身只能手工新增或 xlsx 导入。同时 H1-12 折旧测算与 H1-13 折旧分配的「账面折旧数」只能从对方底稿（K8/K9/I6/F2/F5）按行名模糊匹配拉取，对方底稿未编制时全空；H1-18 关联交易检查表拿不到项目关联方登记表清单，无法做漏项完整性核对；H1-1 的试算平衡表核对科目为硬编码，未走项目可覆盖的报表行规则映射。

本特性把 H1 的四表取数从"审定表一层"扩展为"明细表 + 折旧账面数 + 上下文 + 报表行映射"，并严格遵守**宁缺勿造**：数据条件不满足时不产生 seed、不用近似值冒充，只如实说明原因。

已在需求阶段完成的数据条件核实（真实库实证，作为范围硬约束）：

- `tb_balance` 的 1601/1602/1603 **有完整多级子科目**（如 1601.01 房屋建筑物 / 1601.02 机器设备 / … / 1601.99 其他，与 1602 一一对应），可支撑**分类级**明细取数。
- `tb_aux_balance` 中 160% 科目仅 87 行、`aux_type` 只有 `FFLEX10`（3 个 aux_name）与「项目名称」（3 行，且落在 1604 在建工程），**不存在资产卡片维度** → 卡片级（单台资产）明细无法从四表库获得。
- `tb_ledger` 1602 分录 1519 行中 `counterpart_account` 非空仅 135 行（≈9%）；按 `voucher_no` 归集同凭证借方分录时，实测抽样凭证内混入银行存款 3.2 亿、应付账款 1.1 亿等大量无关业务（凭证为多业务合并记账），**远大于当年折旧总额** → 折旧按对方科目（费用归属）归集在当前数据条件下不可靠。
- `tb_ledger` 1602 贷方**合计**可靠（实测某项目 2025 年折旧合计 3,443,913），可支撑总额层核对。

## Glossary

- **四表库**：`trial_balance`（试算表）/ `tb_balance`（余额表）/ `tb_ledger`（序时账）/ `tb_aux_balance`（辅助余额表）
- **Leaf_Account**：叶子科目，即其科目码不是任何其它科目码前缀的科目（父子同时累加会双算）
- **Category_Level_Seed**：分类级取数，按固定资产五类（房屋及建筑物/机器设备/运输设备/办公设备/其他设备）生成 H1-2 明细行
- **Card_Level_Detail**：卡片级明细，单台资产一行（资产编号/名称/取得日期等），来源为客户资产台账，非四表库
- **Persist_First**：仅当目标存储键为空时才写入取数结果，已有审计师数据一律不覆盖
- **Provenance**：取数溯源，包含来源科目码、`TB('code','列名')` 公式文本、期初/增/减/期末四值
- **Extraction_Flag**：灰度开关 `H1_FOUR_TABLE_EXTRACTION_ENABLED`，默认 False
- **Counterpart_Availability**：折旧对方科目可用性判定结果（`counterpart_account` 填充率与凭证粒度是否支持按费用归属归集）
- **Report_Line_Mapping**：`report_account_mapping.resolve_report_line_account_codes`，按 `report_config` 报表行公式解析科目码（项目级可覆盖）

## Requirements

### Requirement 1: H1-2 明细表分类级四表取数

**User Story:** 作为审计助理，我希望 H1-2 明细表能一键从余额表生成按类别的明细骨架并带上金额，而不是从空表开始逐行手打。

#### Acceptance Criteria

1. WHEN 后端渲染 H1 底稿 AND Extraction_Flag 为 True THEN 系统 SHALL 从 `tb_balance` 的 1601/1602/1603 **Leaf_Account** 生成明细级取数载荷，**按固定资产分类聚合为一行**（原值 1601.0x 与累计折旧 1602.0x 是同类资产的两个侧面，按单科目码拆行会产出「折旧行原值为 0」的错乱明细），每行包含 category、来源科目码清单、原值期初/增/减/期末、累计折旧期初/增/减/期末、减值期初/增/减/期末。
2. WHEN 汇总叶子科目 THEN 系统 SHALL 排除父级科目（1601 与 1601.01 同时存在时只取子科目），且发生额归一为非负数。
3. WHEN 前端 H1-2 挂载 AND 存储键 `H1-2-rows` 为空 THEN 系统 SHALL 以 Persist_First 方式用取数载荷生成明细行；WHEN `H1-2-rows` 已有行 THEN 系统 SHALL NOT 覆盖，仅在页面提供「重新取数」显式动作。
4. WHEN 生成明细行 THEN 每行 SHALL 携带 Provenance（来源科目码与 `TB('code','期末余额')` 公式文本），并在行备注标注来源为余额表取数。
5. WHEN 取数生成的行被写入 THEN 系统 SHALL NOT 编造 Card_Level_Detail 字段（资产编号/取得日期/使用年限/残值率/存放地点等一律留空），并在页面提示卡片级明细需由客户台账导入或手工补录。
6. IF `tb_balance` 无 1601/1602/1603 数据 THEN 系统 SHALL 不生成任何行并提示「余额表无固定资产科目数据」。

### Requirement 2: 明细增减与序时账合计核对

**User Story:** 作为现场经理，我希望知道 H1-2 登记的本期增减合计与序时账发生额是否一致，以判断明细表是否完整。

#### Acceptance Criteria

1. WHEN Extraction_Flag 为 True THEN 系统 SHALL 提供 1601 借方合计（本期增加）与贷方合计（本期减少）的四表库取数结果。
2. WHEN H1-2 明细存在数据 THEN 系统 SHALL 展示「明细增减合计 vs 序时账发生额」核对，并在差异绝对值超过 1 元时给出告警。
3. WHEN 序时账无 1601 分录 THEN 系统 SHALL 显示"未取到序时账发生额"而不是显示 0 并判定为一致。
4. WHEN 展示核对结果 THEN 系统 SHALL NOT 自动修改 H1-2 任何行（只读核对）。

### Requirement 3: 折旧账面数取数（总额层可靠、归属层按数据条件）

**User Story:** 作为审计助理，我希望 H1-12 的账面折旧与 H1-13 的分配合计能直接从序时账取到权威总额，而不是等对方底稿编制完才有数。

#### Acceptance Criteria

1. WHEN 请求折旧取数 THEN 系统 SHALL 从 `tb_ledger` 1602 贷方发生额取本期折旧**合计**与月度分布，并使用数据集有效过滤（不得跨 staged/superseded 数据集重复累加）。
2. WHEN H1-12 展示账面折旧 THEN 系统 SHALL 允许一键带入该合计，且以 Persist_First 方式不覆盖已填值。
3. WHEN H1-13 折旧分配存在数据 THEN 系统 SHALL 展示「分配合计 vs 序时账折旧合计」核对与差异告警。
4. WHEN 判定 Counterpart_Availability THEN 系统 SHALL 先探测 `counterpart_account` 填充率与凭证粒度；IF 不满足可用条件 THEN 系统 SHALL NOT 提供按对方科目（费用归属）的自动归集，并明确提示「序时账未记录对方科目/凭证为合并记账，费用归属需人工或对方底稿核对」。
5. WHEN Counterpart_Availability 满足条件 THEN 系统 SHALL 提供按对方科目归集的折旧分布，且与现有对方底稿拉取结果并列展示互为佐证，不得互相覆盖。

### Requirement 4: 项目上下文补齐（关联方与资产负债表日）

**User Story:** 作为审计助理，我希望 H1-18 能直接看到关联方登记表清单并提示漏登记，H1-17 的年检过期判定使用系统统一的资产负债表日。

#### Acceptance Criteria

1. WHEN 后端渲染 H1 底稿 THEN `project_context` SHALL 包含 `related_parties`（关联方登记表有效记录）与 `bs_date`（资产负债表日）。
2. WHEN H1-18 存在关联方登记表清单 THEN 系统 SHALL 展示「登记表有但本表未登记」的漏项告警，且支持一键补充为待填行。
3. WHEN 关联方登记表为空 THEN 系统 SHALL 显示"关联方登记表暂无数据"提示而不产生任何告警计数。
4. WHEN H1-17 判定年检过期 THEN 系统 SHALL 优先使用注入的 `bs_date`，仅在缺失时回退现有推导逻辑。

### Requirement 5: 审定表试算平衡核对走报表行规则映射

**User Story:** 作为业务合伙人，我希望 H1-1 与试算表的核对口径跟随项目自定义的报表科目映射，而不是写死 1601/1602/1603。

#### Acceptance Criteria

1. WHEN 后端为 H1-1 计算试算平衡表核对金额 THEN 系统 SHALL 通过 Report_Line_Mapping 解析固定资产报表行对应科目码。
2. IF 项目未配置对应报表行公式 THEN 系统 SHALL 回退现有硬编码科目码（1601/1602/1603），保证零回归。
3. WHEN 解析成功 THEN `project_context` SHALL 输出所用科目码清单供页面溯源展示。
4. WHEN 项目映射包含 H1 明细未覆盖的科目 THEN 系统 SHALL 如实呈现差异（不得为消差异而调整取数口径）。

### Requirement 6: 灰度与零回归

**User Story:** 作为质量控制复核合伙人，我希望新取数能按项目灰度启用，且关闭时现有底稿行为逐字节不变。

#### Acceptance Criteria

1. WHEN Extraction_Flag 为 False THEN H1 render 输出 SHALL 与本特性实现前逐字节等价（不含新增取数字段）。
2. WHEN Extraction_Flag 为 False THEN 前端 SHALL NOT 展示任何四表取数入口或来源面板。
3. WHEN Extraction_Flag 为 True 且任一取数环节抛错 THEN 系统 SHALL fail-open（该环节返回空并记录警告），不得阻断 render 或页面加载。
4. WHEN 本特性交付 THEN 现有 H1 前后端测试 SHALL 全部通过，且既有 H1-1 分类预填、H1-2 手工/导入、各 H1-x 内部带入行为不变。

### Requirement 7: 取数溯源可见

**User Story:** 作为复核人，我希望看到每个取数数字来自哪个科目、用什么公式，以及能整体重新取数。

#### Acceptance Criteria

1. WHEN H1-2 / H1-12 / H1-13 展示取数结果 THEN 页面 SHALL 提供来源面板列出来源科目码、公式文本、期初/增/减/期末四值。
2. WHEN 审计师点击「重新取数」THEN 系统 SHALL 二次确认后覆盖持久化取数行，并保留手工新增行。
3. WHEN 取数结果为空 THEN 来源面板 SHALL 显示空态与原因（无数据 / 数据条件不满足 / 灰度未启用）。

### Requirement 8: 数据条件不满足时宁缺勿造

**User Story:** 作为业务合伙人，我不接受系统用近似值或猜测填充底稿，宁可留空让审计师处理。

#### Acceptance Criteria

1. WHEN 四表库缺少对应维度（如资产卡片维度）THEN 系统 SHALL NOT 用科目级数字拆分或平摊生成卡片级行。
2. WHEN 分类归类无法判定 THEN 系统 SHALL 归入「其他设备」并标记需复核，且不得静默丢弃金额。
3. WHEN 任一取数字段无可靠来源 THEN 系统 SHALL 留空而非填 0（0 会被读作"已核实为零"）。

### Requirement 9: 正确性属性可测

**User Story:** 作为质量控制复核合伙人，我希望关键取数口径由属性化测试与契约守卫锁定，防止后续漂移。

#### Acceptance Criteria

1. WHEN 交付 THEN 系统 SHALL 提供覆盖叶子过滤、Persist_First、发生额归一、fail-open、灰度等价、宁缺勿造等属性的测试。
2. WHEN 交付 THEN 系统 SHALL 提供契约守卫，断言四表查询统一经数据集有效过滤入口，且不新增第二套取数口径。
