# Requirements Document

## Introduction

G0（投资循环函证）源模板 `backend/wp_templates/G/G0 投资循环函证.xlsx` 共 **10 张 sheet 且全部 visible**（无隐藏 sheet 问题），底稿目录列明 9 条底稿索引。本 spec 以**逐格精读源模板为唯一裁决依据**，参照已收口的 `e0-confirmation-completion`（18/18）范式，对现有 G0 实现做结构对齐与联动补齐。

G0 此前有两个已归档 spec（`g0-confirmation` 7/7、`g0-investment-diff-model` 14/14），它们把**两张差异核对表**做得相当完整（`g0DiffSourceManifest.ts` 已逐列对源模板 R5/R6 锁死）。本 spec **不重做差异表**，聚焦三类此前未覆盖的缺口：

1. **G0-1 下区四块完全缺失** —— 源模板「一、函证情况（品种×8 指标矩阵）/ 二、样本选择（6 项）/ 三、审计说明（5 项）/ 四、审计结论」在平台上没有任何编制位置。F0 有矩阵（`isF0` 门控）、E0 有矩阵，G0 两者都没有；而 G0-1 的 8 个指标公式与 `f0SummaryAggregation.buildF0SummaryMatrix` **逐条同构**，应当复用/泛化而非再抄一份。
2. **跨表导航与索引号真源错位** —— `CrossWorkpaperNav.vue` 写死 `D0-*`；`cycleConfirmationMeta.G0.diffSecuritiesCode='G0-3S'` 指向不存在的底稿；G0 是单 `wp_code` 多 sheet 工作簿，跳转机制用错。
3. **取数与裁剪信息丢失** —— G0 公式预设贴错标签 + 病态科目区间；G0A 的「程序分类」（常规★/备选/IPO 专项）未落地导致备选程序默认勾选。

**范围外（明确不做）**：两张差异核对表的列集重做（已由归档 spec 覆盖，只做源模板笔误登记与守卫）；`ConfirmationMaster.vue` 未用 `resolveConfirmationColumns` 的平台级遗留；`wp_index` 双命名族数据迁移（每条遗留记录都被活体 `working_paper` 引用，属平台级 spec）；`workpaper_sheet_classification.functional_type` 为 NULL 的平台级补齐（D0/E0/F0 同款，非 G0 独有）。

**🔴 并发约束**：`f0-confirmation-linkage-and-structural-enhancement`（40/41，含 1 个 `[-]`，并发会话正在跑）改的是同一批共享件（`GtConfirmationSummary.vue` / `cycleConfirmationMeta.ts` / `GtConfirmationFollowup.vue` / `ReliabilityGrid.vue` / `GtConfirmationFraudRisk.vue`）。本 spec 的共享件改造（Wave 2/3）**必须等 F0 spec 收口后才动**，否则必然互相回退。Wave 1（守卫）与 Wave 4（G0 专属文件 + 后端数据）可先行。

## Requirements

### Requirement 1: 源模板事实固化守卫

**User Story:** 作为维护者，我需要一份以 openpyxl 直读源 xlsx 为裁决者的守卫，使后续任何会话都不必重新精读源模板，也不能凭"常识"改动 G0 结构。

#### Acceptance Criteria

1.1 WHEN 守卫运行 THEN 系统 SHALL 断言 `G0 投资循环函证.xlsx` 恰有 10 张 sheet、**全部 `sheet_state == 'visible'`**，且 sheet 名逐字等于：`底稿目录` / `函证程序表G0A` / `函证结果汇总表G0-1` / `核实被函证单位信息G0-2` / `跟函函证过程控制G0-3` / `函证差异核对表G0-3（证券投资）` / `函证差异核对表G0-4(非证券投资)` / `替代程序检查表G0-6` / `邮件传真回函可靠性验证G0-7` / `函证程序舞弊风险评价表F0-8`。
1.2 WHEN 守卫检查 G0-1 上区 THEN 系统 SHALL 断言 R5 段头为 `序号`(A5:A7)/`询证函索引号`(B5:B7)/`发函询证纪要`(C5:F5)/`1、发函信息`(G5:K5)/`2、收到回函`(L5:R5)/`3、回函金额确认`(**U5:W5**)/`4、未收到回函的替代程序`(X5:AA5)/`审计结论`(AB5:AB7)，28 个叶子列逐字一致（A/B/AB 在 R5，其余在 R6）。
1.3 WHEN 守卫检查 G0-1 下区 THEN 系统 SHALL 断言四块锚点 `C19 一、函证情况` / `J19 二、样本选择` / `S19 三、审计说明` / `C30 四、审计结论`，矩阵指标 8 行（C21~C28）逐字一致，且矩阵公式为 `SUMIF($E$8:$E$17, 品种, $F$8:$F$17)` / `SUMIF(..., U)` / `SUMIF(..., $Y$)` / `(E27+E24)/E21` 形态。
1.4 WHEN 守卫检查 G0-2 THEN 系统 SHALL 断言 38 列 3 段（`B5:O5` 被审计单位提供的被函证单位信息及核对 / `P5:AA5` 回函信息情况 / `AB5:AL5` 第一次发函结果及二次发函）与 R6 叶子列逐字一致。
1.5 WHEN 守卫检查 G0-3（跟函）与 F0-8（舞弊）THEN 系统 SHALL 断言其正文与 `D0 收入循环函证.xlsx` 的 `跟函函证过程控制D0-3` / `函证程序舞弊风险评价表D0-8` **逐字相同**（证明共享组件无需 G0 专属分叉）。
1.6 WHEN 守卫检查 G0A THEN 系统 SHALL 断言 12 条程序；D 列程序分类逐条为 `常规★`(1,3,4,5,6,9,10,12) / `IPO/上市/新三板/重组/舞弊应对`(2) / `备选`(7,8) / `舞弊应对/IPO/上市/新三板/重组`(11)；E 列底稿索引号逐字一致且**第 8、12 条 E 列为空**。
1.7 WHEN 守卫检查 G0-6 THEN 系统 SHALL 断言表头字段 `A5 会计科目`/`D5 投资产品/名称`、区块锚点 `A9 1.检查初始投资协议、公司章程等` / `A16 （1）本期借方发生额` / `A24 （2）本期贷方发生额` / `A32 3.检查期后是否被出售或赎回`，及每区块两级表头逐字一致。
1.8 WHERE 守卫含反向自检 THE 系统 SHALL 在故意改写任一断言基准时打红（防正则失效导致断言空转）。

### Requirement 2: G0-1 列集对齐源模板

**User Story:** 作为审计助理，我在 G0-1 上看到的列应当就是源模板的 28 列，不多不少，用词与源模板一致。

#### Acceptance Criteria

2.1 WHEN 渲染 G0-1 THEN 系统 SHALL 提供源模板 `AB 审计结论` 列（行级审计结论），复用 K0/L0 既有的 `row_conclusion` 字段而非新造。
2.2 WHEN 渲染 G0-1 THEN 系统 SHALL 从列集中剔除源模板没有的 `contact_person`（联系人）/ `contact_phone`（联系电话）/ `currency`（币种）三列。
2.3 WHERE 源模板 `E6` 列名为「账户/交易」而 BASE 列 `account_type` 标签为「科目」THE 系统 SHALL 支持**按循环覆盖列标签**，G0 侧显示「账户/交易」；SHALL NOT 改动 `key`（`account_type` 是矩阵 SUMIF 的品种维度且已被 F0/E0 消费）。
2.4 WHEN 列标签按循环覆盖 THEN 系统 SHALL 保持 D0/E0/F0/H0/K0/L0 六个循环列集与标签**逐字节不变**（零回归支点）。
2.5 WHEN 守卫运行 THEN 系统 SHALL 断言 `resolveConfirmationColumns('G0')` 的列标签集合与源模板 R6 的 28 个叶子列**一一映射且无剩余**（含分段归属）。

### Requirement 3: G0-1 下区四块

**User Story:** 作为现场经理，我需要在 G0-1 上编制「函证情况／样本选择／审计说明／审计结论」四块，其中函证情况按投资品种自动聚合，否则整张汇总表无法得出函证覆盖率结论。

#### Acceptance Criteria

3.1 WHEN G0-1 渲染 THEN 系统 SHALL 显示四块可折叠区域，标题与锚点逐字取自源模板（`一、函证情况` / `二、样本选择` / `三、审计说明` / `四、审计结论`）。
3.2 WHEN 「一、函证情况」渲染 THEN 系统 SHALL 按投资品种 × 8 指标输出矩阵，指标顺序与文字逐字取自源模板 C21~C28。
3.2.1 WHERE 裁决门 A = 「列 8 个品种 + 预留可扩展 + 有就显示没有隐藏」（2026-08-04 用户裁决）THE 系统 SHALL 声明 8 个品种作为**候选全集**，渲染时只显示「有内容」的品种列。
3.2.2 WHEN 判定某品种「有内容」THEN 系统 SHALL 以三条**任一成立**为判据：① grid 上区存在 `account_type` == 该品种的行 ② 该品种取到了账面金额（相邻 G 循环 render-config 的 `project_context.tb_amount`）③ 该品种有手工录入值（账面金额手填或矩阵格手工覆盖）。
3.2.3 IF 8 个品种**无一**满足「有内容」THEN 系统 SHALL 显示全部候选品种（避免空白区且避免录入死锁）。
3.2.4 WHEN 矩阵渲染 THEN 系统 SHALL 提供「显示全部品种」开关（默认关）。**理由**：若严格只显示有内容的品种，审计师无法为一个尚无数据的品种录入账面金额 → 永久无法让它「有内容」，形成死锁。该开关是「有就显示没有隐藏」的必要配套，SHALL NOT 省略。
3.2.5 WHERE 源模板 `H20` 是 `……` 可扩位 THE 系统 SHALL 支持在候选全集之外新增自定义品种（名称需与 grid 上区 `account_type` 取值一致才参与聚合），并在新增时提示该要求。
3.2.6 WHEN 品种列可见性变化 THEN 系统 SHALL NOT 丢弃被隐藏品种的已录入值（隐藏只影响渲染）。
3.3 WHEN 计算矩阵 THEN 系统 SHALL 按源模板公式取值：发函金额 = `Σ grid[品种].账面期末余额(F)`；回函确认金额 = `Σ grid[品种].可确认金额(U)`；替代测试确认金额 = `Σ grid[品种].替代后可确认金额(Y)`；三个比例为派生；末行 = `(替代+回函)/账面`。
3.4 IF 分母缺失或为 0 THEN 系统 SHALL 渲染「-」（null），SHALL NOT 产出 NaN/Infinity，也 SHALL NOT 用 0 冒充。
3.5 WHERE 「本期（期末）账面金额」行在源模板无公式（手填）THE 系统 SHALL 允许手工录入，并在有自动取数时以手工值优先。
3.6 WHEN 「二、样本选择」渲染 THEN 系统 SHALL 提供源模板 6 项（测试总体 / 特定样本 / 抽样总体 / 确定的抽样样本量 / 抽样方法 / 抽样过程），每项以源模板示例文字作 placeholder；SHALL 复用替代程序组件既有的 `SamplingConfig`（`alternativeD05Types.ts`）的 5 个同义字段（`specific_samples`/`sampling_population`/`sample_size`/`sampling_method`/`sampling_process`），使汇总表与替代程序表口径统一。
3.6.1 WHERE `SamplingConfig.test_scope` 的源语义是「测试范围」（源 `G0-6!A7`，5 个点选项）而 G0-1 的首项是「测试总体」（源 `G0-1!J20`，叙述性）THE 系统 SHALL 新增 additive 字段 `test_population`，SHALL NOT 复用 `test_scope` 承载测试总体（二者语义不同）。
3.6.2 WHERE `ConfirmationSampling.vue` 的唯一消费方 `GtConfirmationSummary.vue` 服务全部七枢纽（实测）THE 6 项表单 SHALL 由 `cycle === 'G0'` 门控，其余六枢纽 SHALL 继续渲染既有 4 项（裁决门 E = **isG0 门控**，2026-08-04 用户裁决）。**理由**：七枢纽 X0-1 的样本选择块在源模板同构（memory 实证「`X0-1!C8` 选样目的 5 项亦同构」），平台级统一为 6 项在业务上更正确，但会改变其余六循环的既有 UI 与 R11.1 冲突 → 本 spec 只做 G0，平台级统一登记为待收敛项。
3.6.3 WHEN 6 项表单以门控实现 THEN 系统 SHALL 使门控为**渲染层**概念：`SamplingConfig` 的 6 个字段对全部枢纽都可读写（数据模型不分叉），SHALL NOT 让 G0 之外的枢纽因门控而丢失已存的 6 项数据。
3.7 WHEN 「三、审计说明」渲染 THEN 系统 SHALL 提供源模板 5 项录入位置（1 对询证函保持的控制的说明 / 2 对误差的分析 / 3 对以传真或电子邮件形式收到的回函的可靠性的考虑 / 4 针对不符事项的程序 / 5 针对未回函的替代程序），每项配 AI 辅助与复核入口。
3.8 WHERE 源模板把一句话拆成两格（`X21+X22` 界定误差构成条件 / `S26` 未函证其他信息说明）THE 系统 SHALL 合并渲染为完整句子，SHALL NOT 出现半句话。
3.9 WHEN 「四、审计结论」渲染 THEN 系统 SHALL 提供结论录入位置，并以源模板 A54~A57 的参考结论 A/B/C 作可一键套用的选项。
3.10 WHEN 下区渲染 THEN 系统 SHALL 把源模板编制说明（A33~A58：准则 1312 第十条六项选样要求 / 函证注意事项 8 条 / 后附审计证据）作只读方法论上下文就地展示（折叠），SHALL NOT 让审计师去翻源 xlsx。
3.11 WHERE 下区新增录入位置 THE 系统 SHALL 使用独立持久化键，SHALL NOT 与上区 grid 或既有 `sampling`/`conclusion` 键冲突。

### Requirement 4: 品种矩阵账面金额取数

**User Story:** 作为审计助理，我希望矩阵的「本期（期末）账面金额」能从四表库自动带入，而不是逐格手抄。

#### Acceptance Criteria

4.1 WHEN 声明 G0 矩阵品种 THEN 系统 SHALL 以声明式清单给出品种及其 `source_ref`；源模板 `E20/F20/G20` 三个品种（交易性金融资产 / 长期股权投资 / 债权投资）标注 `G0-1!E20..G20`，其余品种标注 `函证程序表G0A!B7`（程序 1 明列的 7 个品种）。
4.2 WHEN 取账面金额 THEN 系统 SHALL 按 `report_config` 实证映射取数：交易性金融资产=`BS-003`(1101)／债权投资=`BS-021`(1504)／长期应收款=`BS-023`(1531)／其他债权投资=`BS-022`(1506)／长期股权投资=`BS-024`(1511)／其他权益工具投资=`BS-025`(1507)／其他非流动金融资产=`BS-026`(1519)／交易性金融负债=`BS-042`(2101)。
4.3 WHERE 账面金额来自相邻循环审定表 THE 系统 SHALL 读取对应 G 循环 render-config 的 `project_context.tb_amount`；缺失时返回 `undefined`（非 0），使「本项目无此科目」与「余额为 0」可区分。
4.4 WHEN 品种科目码写入代码 THEN 系统 SHALL 只作**兜底与展示**，运行态一律走既有 `four_table/g_cycle_specs.py` 与语义定位结果，SHALL NOT 让取数改回按硬编码码查询。
4.5 WHEN 守卫运行 THEN 系统 SHALL 断言品种清单与 `g_cycle_specs.py` 的报表行声明**双向锁死**（前端多一个品种或后端改一个 row_code 都打红）。

### Requirement 5: 跨表导航与 CrossRef 按循环解析

**User Story:** 作为审计助理，我在 G0 任一 sheet 上点「本笔相关底稿」，应当跳到 G0 自己的 sheet，而不是看到 D0 的清单或「未找到」。

#### Acceptance Criteria

5.1 WHEN `CrossWorkpaperNav.vue` 渲染 THEN 系统 SHALL 使用 `buildCrossWorkpaperNavDefs(wpCode)` 生成导航项，SHALL NOT 保留写死的 `D0-*` 定义。
5.2 WHEN 导航目标位于同一工作簿 THEN 系统 SHALL 走同工作簿 `?sheet=` 切页（复用 `utils/normalizeSheetName.resolveSheetNameByDeepLink`），SHALL NOT 调用 `wp-id-by-code`。
5.3 WHERE `wp_index` 实测无 `G0-3S`/`G0-6`/`G0-7`/`G0-8` 记录 THE 系统 SHALL NOT 产生指向这些 wp_code 的跳转入口。
5.4 WHEN 解析 G0 差异表 THEN 系统 SHALL 区分两张表：证券投资差异（tab `函证差异核对表G0-3（证券投资）`，目录索引 G0-4）与非证券投资差异（tab `函证差异核对表G0-4(非证券投资)`，目录索引 G0-5）。
5.5 WHEN `cycleConfirmationMeta` 声明 G0 THEN 系统 SHALL 用真实可定位的标识替换 `diffSecuritiesCode:'G0-3S'`，并保持 D0/E0/F0/H0/K0/L0 六个循环的 meta **逐字节不变**。
5.6 WHEN 守卫运行 THEN 系统 SHALL 断言 `buildCrossWorkpaperNavDefs` 有真实消费方（源码级扫描组件模板/脚本），防再次退化为零消费方。

### Requirement 6: 索引号真源与展示分离

**User Story:** 作为质控复核人，我需要 UI 上的底稿索引号与源模板底稿目录一致，同时不因源模板 tab 名笔误而导致定位落空。

#### Acceptance Criteria

6.1 WHEN 声明 G0 各 sheet THEN 系统 SHALL 同时保存**定位值**（源模板真实 tab 名，逐字含全/半角括号）与**展示值**（底稿目录索引号），二者分离（H10 范式）。
6.2 WHERE 源模板 tab 名索引号与底稿目录不一致 THE 系统 SHALL 以**底稿目录为裁决者**给出展示值：证券差异表 → `G0-4`；非证券差异表 → `G0-5`；舞弊风险评价表 → `G0-8`。**（裁决门 B = 本方案，2026-08-04 用户裁决）**
6.3 WHEN 展示修正后的索引号 THEN 系统 SHALL 在 tooltip 中标注源模板 tab 名原值及"源模板索引号笔误"说明，SHALL NOT 静默改写。
6.4 WHEN 定位/请求 sheet THEN 系统 SHALL 一律使用真实 tab 名，SHALL NOT 使用修正后的索引号，也 SHALL NOT 改写源 xlsx 或 `workpaper_sheet_classification`。
6.5 WHEN 守卫运行 THEN 系统 SHALL 断言三处笔误映射与 `workpaper_sheet_classification` 的 G0 记录（10 条）互相一致，且 `wp_code_overrides.json` 中 `函证差异核对表G0-3（证券投资）`/`函证差异核对表G0-4(非证券投资)`/`函证程序舞弊风险评价表F0-8` 三条**全名键**存在。

### Requirement 7: G0-6 替代程序区块对齐源模板

**User Story:** 作为审计助理，我在 G0-6 上录入的列应当是源模板要求的证据要素，缺一项就无法证明替代程序做到位。

#### Acceptance Criteria

7.1 WHEN G0-6 渲染 THEN 系统 SHALL 提供表头字段「会计科目」与「投资产品/名称」（源 `A5`/`D5`）。
7.2 WHEN 区块① 渲染 THEN 系统 SHALL 按源模板 `A10:E10` 提供列：被投资单位 / 投资比例 / 投资金额 / **投资条款** / 索引号；SHALL NOT 出现源模板没有的记账凭证 5 列。
7.3 WHEN 区块② 渲染 THEN 系统 SHALL 按源模板提供 记账凭证{日期/凭证编号/业务内容/对方科目/金额} + **支持性文件1{识别特征/信息1/信息2}** + **支持性文件2{识别特征/信息1/信息2}** + 索引号 + 是否异常，并保留借方/贷方双区结构（源 `A16`/`A24`）。
7.4 WHEN 区块③ 渲染 THEN 系统 SHALL 按源模板提供 记账凭证 5 列 + **投资协议/交易确认单/交割单{日期或编号 / 被投资单位名称 / 金额}** + **银行回单{日期或编号 / 付款方 / 金额}** + 索引号 + 是否异常。
7.5 WHERE 既有实现含源模板之外的增强列（持仓证明 / 股利收入 / 公允价值佐证 / block3 的 处置金额·净收入·卖出数量·成交价·原始成本·手续费·处置损益·银行到账）THE 系统 SHALL 保留为显式登记的「源外增强」，逐列写明理由，SHALL NOT 丢弃任何既有字段（数据零丢失红线）。**（裁决门 C = 保留，2026-08-04 用户裁决）**
7.6 WHEN G0-6 编制指导渲染 THEN 系统 SHALL 使文案与现行区块标题一致，SHALL NOT 保留描述已废弃四区块（持仓证明/投资收益股利/处置收益/公允价值佐证）的陈旧段落。
7.7 WHEN G0-6 渲染 THEN 系统 SHALL 保留源模板 `A6 一、样本选取标准与规模`（含测试范围 5 个点选项）/ `A40 三、审计说明` / `A43 四、审计结论` / 编制说明 3 条替代程序要点。
7.8 WHEN 守卫运行 THEN 系统 SHALL 以 openpyxl 直读源 xlsx 交叉比对四区块列定义，并断言源外增强列全部在登记清单内。

### Requirement 8: G0A 程序分类落地

**User Story:** 作为现场经理，我需要程序表按「常规★／备选／IPO 专项」区分默认适用性，否则备选和 IPO 专项程序会在普通项目上被默认勾选，虚增工作量并污染完成率。

#### Acceptance Criteria

8.1 WHEN G0A 模板加载 THEN 系统 SHALL 为 12 条程序提供源模板 D 列的程序分类值。
8.2 WHEN 程序分类落地 THEN 系统 SHALL 写入 `program_category` 字段（前端 `GtAProgramConsole.vue` 已有「类别」列 + 类别筛选 radio-group + `categoryTagType` 配色，且 `hasCategory` 在全空时隐藏该列 → G0A 当前无类别列即因该字段缺失），使项目组可按「常规★／备选／IPO 专项」筛选并批量裁剪。
8.3 WHEN 表达「非默认执行」THEN 系统 SHALL NOT 依赖 `applicable_default: "no"`。**实证**：`_a_program.py` 只把 `applicable == "na"` 映射为 `status='not_applicable'`，`"no"` 与 `"yes"` 渲染结果相同 → 写 `"no"` 是死配置；而 `"na"` 只能由 `applicable_categories` 与项目业务类别不匹配时产生，现有取值域是业务类别前缀（`['A','B']`/`['A']`）而非 IPO 标记。故本 spec 只落 `program_category`（+ 必要时 `applicable_note` 说明理由），「按项目属性自动裁剪 IPO 专项程序」属平台级改造，记入遗留。
8.4 WHERE `procedure_table_templates.json` 同时存在 `/tables/G0A`（12 条，`get_template` 只读 `tables` → 运行时生效）与根级 `/G0A`（8 条自造内容、索引号写错）THE 系统 SHALL 以 `/tables/G0A` 为唯一权威并加守卫钉死；SHALL NOT 单独删除根级 `/G0A`（**实证根级共 66 条同族条目、其中 57 条与 `tables` 重复且内容分叉**，只删 G0 一条会造成不一致）。
8.5 WHEN 守卫运行 THEN 系统 SHALL 断言 G0A 的 12 条 `content`/`ref_index`/程序分类与源模板逐字一致；SHALL 断言 `get_template('G0A')` 返回的是 12 条版本（而非根级 8 条）；WHERE 根级 `/G0A` 仍存在 THE 守卫 SHALL 断言其与 `/tables/G0A` 内容不同并**在断言消息中指向平台级议题**（防被误当成已收敛）。
8.6 WHEN 修改 `applicable_default` THEN 系统 SHALL 不影响其余 120 个 `tables` 模板与 66 条根级条目（零回归，以 Task 3 基线快照比对）。
8.7 WHEN 登记平台级议题 THEN 系统 SHALL 记录**9 条根级独有的程序表在运行时不可用**（`get_template` 返回 `None`）：`L0A`（L 循环函证程序表）· `M1A` · `S1` · `S2` · `S3` · `S8` · `S10` · `S11` · `S13`；SHALL NOT 在本 spec 内修复（属平台级 spec）。

### Requirement 9: G0 公式预设纠偏

**User Story:** 作为审计助理，我在公式管理页看到的 G0 取数公式应当指向真实存在的 sheet 与正确的科目，而不是把应收账款和存货算进投资循环。

#### Acceptance Criteria

9.1 WHERE G0 预设块 `sheet` 为 `审定表G0-1`（源 xlsx 无此 tab）THE 系统 SHALL 改为真实 tab 名 `函证结果汇总表G0-1`。
9.2 WHERE G0 预设公式为 `TB_SUM('1101~1511', ...)` THE 系统 SHALL 改为按品种的离散 `TB()` 条目（R4.2 的 8 个科目），SHALL NOT 使用跨科目族区间。
9.3 WHEN 预设条目重写 THEN 系统 SHALL 使 `cell_ref` 对应 G0-1 下区矩阵的品种账面金额格，SHALL NOT 保留 G0-1 不存在的 `期初余额`/`未审数` 锚点。
9.4 WHEN 纠偏以幂等脚本实施 THEN 脚本 SHALL 提供 `--dry-run`/`--check`，`--check` 在无欠账时 exit 0，并含 round-trip 自检（`json.dumps` 不能逐字复现原文即 exit 2）。
9.5 WHEN 守卫校验预设 THEN 系统 SHALL 只扫语义字段（`formula`/`account_codes`/`cell_ref`/`sheet`），SHALL NOT 对整块 `json.dumps` 做"不得出现 xxx"断言（描述文字会如实写出被纠正的反例）。
9.6 WHEN 守卫运行 THEN 系统 SHALL 断言 G0 预设引用的每个科目码都在标准科目表内、且属于 G 循环报表行引用的科目集合。

### Requirement 10: 源模板自身缺陷按意图实现

**User Story:** 作为维护者，我需要源模板的缺陷被逐条登记并按意图实现，而不是被照抄进平台、也不是被静默"顺手修正"后让守卫打红。

#### Acceptance Criteria

10.1 WHEN 登记源模板缺陷 THEN 系统 SHALL 逐条记录以下 7 项，每条含源锚点、缺陷描述、平台处置方式：
  - `函证结果汇总表G0-1!U5:W5` 段头「3、回函金额确认」位置右移，导致 `S 回函金额` 与 `T 差异` 两列**无段归属**（D0-1/F0-1 同构表均为 `S5:W5`，是正确意图的旁证）
  - `底稿目录!D7` 序号硬写 2（其余为 `=D(n-1)+1`），导致序号列显示 1,2,3,2,3,4,3,4,5
  - `函证结果汇总表G0-1!E24` 公式 `SUMIF($E$8:$E$17,E$20,U8:U179)` 行号越界（应 `U8:U17`）
  - `函证结果汇总表G0-1!S24` 交叉引用写「（G0-6）」，而回函可靠性验证是 G0-7
  - `核实被函证单位信息G0-2!AA6` 写「跟函函证控制过程（G0-2）」自引用，应为 G0-3
  - `函证差异核对表G0-3（证券投资）!M` 列公式 `=J−G`，与表头声明 `③=①−②` 及同组 `K=E−H`/`L=F−I` 方向相反（应 `=G−J`）
  - 三处 tab 名索引号笔误（见 R6.2）
10.2 WHEN 平台实现涉及上述缺陷 THEN 系统 SHALL 按**意图**实现（矩阵求和范围取实际行数；交叉引用文案指向正确 sheet；差异列方向统一为 账面−回函），SHALL NOT 照抄错误。
10.3 WHERE 源模板文字含笔误但作为只读方法论上下文展示 THE 系统 SHALL 原样保留原文并加标注，守卫按原文断言（防被"顺手修正"后三向比对打红）。
10.4 WHEN 守卫运行 THEN 系统 SHALL 对每条缺陷同时断言"源模板确实存在该缺陷"与"平台实现已按意图纠正"，二者缺一即打红。

### Requirement 11: 共享件零回归与并发边界

**User Story:** 作为维护者，我需要 G0 的改造不破坏其余六个函证枢纽，也不与并发运行的 F0 spec 互相回退。

#### Acceptance Criteria

11.1 WHEN 改造共享件（`confirmationColumnSpec.ts` / `cycleConfirmationMeta.ts` / `GtConfirmationSummary.vue` / `CrossWorkpaperNav.vue` / `ConfirmationSampling.vue`）THEN 系统 SHALL 使 D0/E0/F0/H0/K0/L0 的既有行为**逐字节不变**，并以既有守卫全绿为验收条件。**`ConfirmationSampling.vue` 由 R3.6.2 的 `isG0` 门控满足本条**（六枢纽渲染路径不变），SHALL NOT 以「源模板同构」为由把 6 项推给其余枢纽。
11.2 WHERE 用户已裁决「各自实现后收敛」（裁决门 D = D-2，2026-08-04）THE 系统 SHALL 在 G0 专属目录内实现矩阵与下区（`g0SummaryMatrix.ts` / `g0SummaryLowerZone.ts` / `G0SummaryLowerZone.vue`），SHALL NOT 改动 `f0SummaryAggregation.ts` 与 `e0SummaryMatrix.ts` 与 `E0SummaryLowerZone.vue`（并发 spec 在用）。
11.2.1 WHEN 实现 G0 矩阵 THEN 系统 SHALL 在模块头逐行登记与 `f0SummaryAggregation.ts` 的**同源关系与差异点**（指标 8 个同构 / 品种不同 / 账面取数来源不同），并 SHALL 声明 `CONVERGENCE_TARGET` 常量指向收敛 spec 名，使收敛时能机器定位全部副本。
11.2.2 WHEN 守卫运行 THEN 系统 SHALL 断言 G0 矩阵与 F0 矩阵对**同一输入**产出**逐字节相同的指标序列与派生值**（同源性证明）；一旦两侧算法漂移即打红，使收敛前不会先出现口径分叉。
11.3 WHERE `E0SummaryLowerZone.vue` 实测为零消费方（E0 spec Task 18 建好未接线）THE 系统 SHALL NOT 修改它，SHALL 在 Notes 登记「E0 接线属 E0 侧遗留」；G0 侧自建组件 SHALL 有真实消费方（零消费方即视为未交付）。
11.4 WHERE `confirmationColumnSpec.ts` 是唯一的共享列注册表（无「各自一份」的选项）THE 系统 SHALL 只做**加法式**改动（新增 `CYCLE_COLUMN_LABEL_OVERRIDES` 表 + 两个既有 record 的 `G0` 键），每次改动 SHALL 用 `str_replace` 最小 hunk 而非整文件覆写；WHEN 与 `h0-confirmation-source-fidelity-and-linkage` 的同名任务撞车 THEN SHALL 以「双方 record 各自键互不重叠」为兼容判据，并在 Notes 记录撞车时间点。
11.5 WHERE `GtConfirmationSummary.vue` 正被 `f0-confirmation-linkage-and-structural-enhancement`（含 `[-]`/`[~]`）改动 THE 系统 SHALL 把 G0 逻辑全部放进 G0 自有文件，在该组件内只加**最小挂载 hunk**（import + `isG0` computed + 一个条件渲染块），SHALL NOT 重排既有代码。
11.6 WHEN 新建模块 THEN 系统 SHALL 先 grep 消费方确认不存在同名实现（并发会话可能已建好并接线）。
11.7 WHEN 任一新建模块交付 THEN 系统 SHALL 断言其存在真实消费方（零消费方即视为未交付）。
11.8 WHEN 本 spec 收口 THEN 系统 SHALL 在 Notes 登记**收敛 spec 的范围与判据**：待收敛副本清单（`e0SummaryMatrix` / `f0SummaryAggregation` / `g0SummaryMatrix` / `h0SummaryMatrix` + `E0SummaryLowerZone` / `G0SummaryLowerZone` / `H0SummaryLowerZone`）· 收敛后每份的删除条件 · 收敛不得改变任一循环既有输出（以各自的基线快照为准）。
11.5 WHEN 新建模块 THEN 系统 SHALL 先 grep 消费方确认不存在同名实现（并发会话可能已建好并接线）。
11.6 WHEN 任一新建模块交付 THEN 系统 SHALL 断言其存在真实消费方（零消费方即视为未交付）。

## Glossary

| 术语 | 含义 |
|---|---|
| G0 | 投资循环函证工作簿，单 `wp_code='G0'` 含 10 张 sheet（非 10 个独立 wp_code） |
| 底稿目录索引号 | 源模板 `底稿目录!F4:F12` 列明的 9 条索引（G0A / G0-1 … G0-8），**索引号真源** |
| tab 名 | sheet 的真实名称（openpyxl `wb.sheetnames`），**定位真源**；三处含索引号笔误 |
| 品种 | G0-1 下区矩阵的列维度，对应上区 `E 账户/交易` 列取值（交易性金融资产/债权投资/…），平台字段 `account_type` |
| 8 指标 | 源模板 `C21:C28` 的函证情况指标（账面金额/发函金额/发函占比/回函确认/回函占发函/回函占账面/替代确认/回函+替代占账面） |
| 下区四块 | G0-1 `R19` 起的 一、函证情况 / 二、样本选择 / 三、审计说明 / 四、审计结论 |
| 程序分类 | G0A `D` 列（常规★ / 备选 / IPO·上市·新三板·重组·舞弊应对），项目组裁剪程序的依据 |
| 源外增强 | 平台在源模板列之外增加的列，须逐列登记理由并保留（数据零丢失） |
| 七枢纽 | D0/E0/F0/G0/H0/K0/L0 七个函证循环，共享 confirmation 组件族 |
| 零消费方 | 模块/组件已实现但无任何调用点，等同未交付 |
