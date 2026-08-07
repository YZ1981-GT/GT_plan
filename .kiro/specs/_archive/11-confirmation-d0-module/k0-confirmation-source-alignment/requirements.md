# Requirements Document

## Introduction

K0（管理循环函证）源模板 `backend/wp_templates/K/K0 管理循环函证.xlsx` 共 **11 张 sheet，其中 10 张 visible + 1 张 `GT_Custom` hidden**（无 E0 那种「隐藏 sheet 被渲染成页签」问题），底稿目录列明 9 条底稿索引（`K0A` + `K0-1`~`K0-8`）。本 spec 以**逐格精读源模板为唯一裁决依据**（openpyxl 直读 formula + cache + merged_cells + dataValidation），参照已收口的 `e0-confirmation-completion`（18/18）范式，对现有 K0 实现做结构对齐与联动补齐。

K0 的既有实现度**高于立项预估**：9 个 sheet 的 `componentType` 全部登记、后端有 `_k0_confirmation.py` / `_k0_confirmation_ai.py` / `_k0_confirmation_import_export.py` 三个策略、K0-5/K0-6 的**借贷拆表已实现**（源模板第 3 段「（1）本期借方发生额 /（2）本期贷方发生额」两张表）、四区块已在 `alternativeBlockManifest.ts` 登记（含 `sourceExtra` 依据）、K0-8 的 19 条舞弊迹象已由 `fraudRiskPresets.ts` 按源模板逐字锁死（后端守卫以 xlsx 为裁决者，六表 md5 全等）。故本 spec **不重做**这些部分，聚焦五类此前未覆盖的缺口：

1. **K0-1 下区四块完全缺失** —— 源模板 `C27 一、函证情况`（2 品种 × 8 指标矩阵）/ `I27 二、样本选择`（6 项）/ `S27 三、审计说明`（5 项）/ `C38 四、审计结论` 在平台上没有任何编制位置。`GtConfirmationSummary.vue` 现有 `isE0`/`isF0`/`isH0`/`isG0` 四个门控，`isK0` **零命中**。K0-1 的 8 个指标公式与 `f0SummaryAggregation` / `h0SummaryMatrix` **逐条同构**，故按 H0 已确立的范式办：**复用 `safeRatio`/`sumByCategory` 两个纯函数、指标与品种常量各自声明**（H0 的理由「一侧源模板改动不应波及另一侧」成立且已落地三次），SHALL NOT 重构成统一内核。
2. **列集含一个源模板不存在的伪列，且缺 G0/H0 已建的渠道列** —— `VARIANT_COLUMN_DEFS.send_memo` 把源模板 `C5:F5` 合并单元格的**分组表头**「发函询证纪要」当成了一个自由文本列；`row_conclusion` 被塞进 `send_memo` 组（G0/H0 已把同款列归入 `row_summary` 组并在注释中明确指出 K0/L0 的归属待修正）；K0-1 源模板**无**联系人/联系电话/币种三列（它们在 K0-2 的 `F`/`G` 列）而 `CYCLE_EXCLUDED_COLUMNS.K0` 为空数组 ⇒ 三列空列噪声；源模板 `G6 函证方式` 实为**渠道**（`K0-2!C7:C24` 的 DV 实测 `邮寄/跟函/电子函证/其他`，经 VLOOKUP 带入 `K0-1!G`）而 K0 未启用 G0/H0 已建的 `send_channel` variant 列。
3. **列标签与源模板用词分叉 10 处** —— 最关键的是 `account_type` 标注「科目」而源模板 `E6` 是「**账户/交易**」，这一列是下区矩阵 `SUMIF` 的品种维度，用词错会直接导致审计师填错分类键、矩阵恒为 0。G0/H0 已建 `CYCLE_COLUMN_LABEL_OVERRIDES` 机制（现仅含 `G0`/`H0` 两 key），K0 只需增声明。
4. **公式预设整块贴错标签** —— `prefill_formula_mapping.json` 的 K0 块 `sheet="审定表K0-1"` 在源 xlsx **不存在**，`cell_ref` 是审定表口径的「期初余额/未审数」，`account_codes` 只声明 `1221`（漏其他应付款 `2241`）→ 该块对 K0 完全不可用。
5. **三处源模板索引号笔误 + 底稿目录序号跳号** —— 需按意图实现并留证，不得静默改写源模板。

**范围外（明确不做）**：K0-8 舞弊迹象条目重做（`fraudRiskPresets.ts` 已是单一真源且已按源模板逐字重写，后端守卫在册）；K0-5/K0-6 四区块重构（`sourceExtra` 已登记依据，本 spec 只修 label 语义错与补源模板证据列）；`ConfirmationMaster.vue` 未用 `resolveConfirmationColumns` 的平台级遗留（列表视图=核心列概览属有意设计，注释已说明）；`RELIABILITY_COLUMN_CONFIG` 零消费方这一死配置的清理（平台级，D0/F0/G0/H0/L0 同款）；`wp_index` 双命名族数据迁移；`wp_render_schema/generated/` 运行时从不加载这一平台级事实（E0/K0 同款）。

**🔴 并发约束（本 spec 最重要的前置条件）**：

| 并发 spec | 状态 | 与本 spec 重叠的文件 |
|---|---|---|
| `f0-confirmation-linkage-and-structural-enhancement` | 28/31，含 1 个 `[-]` + 2 个 `[~]`，**并发会话正在跑** | `GtConfirmationSummary.vue`、`composables/f0SummaryAggregation.ts`、`composables/f0MatrixDataSources.ts` |
| `g0-confirmation-source-alignment` | 仅 requirements.md（2026-08-03 23:48 新建），**同族且同样计划泛化矩阵** | `confirmationColumnSpec.ts`、`cycleConfirmationMeta.ts`、`GtConfirmationSummary.vue`、`memoTemplates.ts`、`ReliabilityGrid.vue` |

故本 spec 的共享件改造（Wave 3）**必须等 F0 spec 收口后才动**；**矩阵泛化共享件由 K0/G0 两个 spec 中先落地者建**，后落地者只声明自己的品种配置并复用，不得各建一份（见 Requirement 11）。Wave 1（守卫）与 Wave 2（K0 专属文件 + 后端数据）不碰共享件，可先行。

## Requirements

### Requirement 1: 源模板事实固化守卫

**User Story:** 作为维护者，我需要一份以 openpyxl 直读源 xlsx 为裁决者的守卫，使后续任何会话都不必重新精读 K0 源模板，也不能凭"常识"改动 K0 结构。

#### Acceptance Criteria

1.1 WHEN 守卫运行 THEN 系统 SHALL 断言 `K0 管理循环函证.xlsx` 恰有 11 张 sheet，其中 `GT_Custom` 为 `hidden`、其余 10 张为 `visible`，且可见 sheet 名逐字等于：`底稿目录` / `函证程序表K0A` / `函证结果汇总表K0-1` / `核实被函证单位信息K0-2` / `跟函函证过程控制K0-3` / `函证差异调节表K0-4` / `其他应收款替代程序K0-5` / `其他应付款替代程序K0-6` / `邮件传真回函可靠性验证K0-7` / `函证程序舞弊风险评价表K0-8`。
1.2 WHEN 守卫检查底稿目录 THEN 系统 SHALL 断言 `D5:F13` 共 **9 行**，`F` 列索引号逐字为 `K0A`/`K0-1`~`K0-8`，且 `D` 列序号取值序列为 `[1,2,3,4,5,7,8,9,10]`（**序号 6 缺失、末号为 10 而仅 9 行**，源模板跳号事实）。
1.3 WHEN 守卫检查 K0-1 上区 THEN 系统 SHALL 断言 R5 段头为 `序号`(A5:A6) / `询证函索引号`(B5:B6) / `发函询证纪要`(C5:F5) / `1、发函信息`(G5:K5) / `2、收到回函`(L5:R5) / `3、回函金额确认`(S5:W5) / `4、未收到回函的替代程序`(X5:AA5) / `审计结论`(AB5:AB6)，R6 叶子列 **28 个**逐字一致（`选取样本目的`/`被询证单位名称`/`账户/交易`/`金额`/`函证方式`/`发函日期`/`发函单号/跟函记录索引号`/`收件地址`/`地址核查是否一致`/`是否收到回函`/`回函方式`/`是否相符`/`回函日期`/`回函快递单号`/`回函发出地址`/`发函地址与回函地址是否一致`/`回函金额`/`差异`/`可确认金额`/`调节索引（K1-12）`/`其他说明/备注`/`是否采取替代程序`/`替代后可确认金额`/`替代后不可确认金额`/`替代程序索引号`）。
1.4 WHEN 守卫检查 K0-1 数据区与公式 THEN 系统 SHALL 断言数据行为 `r7:r26`（20 行），`D/G/J/K/M/Q/R` 列为 `VLOOKUP($B{r},'核实被函证单位信息K0-2'!$A:$AL,{2,3,4,10,16,19,22},0)`，`T` 列为 `IF(L{r}="是",S{r}-F{r},"未回函")`。
1.5 WHEN 守卫检查 K0-1 下区 THEN 系统 SHALL 断言四块锚点 `C27 一、函证情况` / `I27 二、样本选择` / `S27 三、审计说明` / `C38 四、审计结论`；品种列头 `E28 其他应收款` / `F28 其他应付款`；8 个指标位于 `C29:C36` 且文字逐字一致；矩阵公式形态为 `SUMIF(E7:E26,E28,F7:F26)`（发函金额）/ `SUMIF(E7:E26,E28,U7:U26)`（回函确认）/ `SUMIF(E7:E26,E28,Y7:Y26)`（替代确认）/ `IF(ISERROR(E30/E29),0,E30/E29)`（三个比例）/ `(E35+E32)/E29`（末行，**无 ISERROR 兜底**）。
1.6 WHEN 守卫检查 K0-1 「二、样本选择」THEN 系统 SHALL 断言 6 项分别位于 `I28/I29/I30/I31/I33/I34`（**I32 为空、J32 承载样本计算器提示**），标签逐字为 `测试范围：`/`特定样本：`/`抽样总体：`/`确定的抽样样本量：`/`抽样方法：`/`抽样过程：`。
1.7 WHEN 守卫检查 K0-1 「三、审计说明」THEN 系统 SHALL 断言 5 项标题位于 `S28`/`X28`/`S32`/`X32`/`S36`，文字逐字为 `1.对询证函保持的控制的说明` / `2.对误差的分析` / `3.对以传真或电子邮件形式收到的回函的可靠性的考虑（K0-6）` / `4.针对不符事项的程序` / `5.针对未回函的替代程序`，且第 2 项的界定条件由 `X29`+`X30` 两格拼成一句、第 3 项的补充说明在 `S33`。
1.8 WHEN 守卫检查 K0-1 编制说明 THEN 系统 SHALL 断言 `A42 编制说明：` 下含准则 1312 第十条**六项**选样要求（`A46:A51`）、函证注意事项**8 条**（`B53:B60`）、参考结论 A/B/C（`A64:B66`）、`A67 后附审计证据`，及 `A40` 传真/电邮回函提示。
1.9 WHEN 守卫检查 K0-2 THEN 系统 SHALL 断言 **38 列 5 段**：`A5 函证索引`(rowspan2) / `B5:O5 被审计单位提供的被函证单位信息及核对（核实被函证单位信息）（注1）` / `P5:AA5 回函信息情况（回函核对记录）` / `AB5 第一次发函结果？（送抵/退回）（注2）` / `AC5 经核实的原因` / `AD5 该原因是否合理（是/否）\n（注3）` / `AE5 是否进行第二次发函？\n（是/否）` / `AF5:AK5 第二次发函的被函证单位信息` / `AL5 第二次发函结果？（送抵/退回）\n（注4）`，且 `AF6:AK6` 叶子列逐字为 `地址`/`邮编`/`联系人`/`联系电话`/`传真`/`信息是否核查一致`。
1.10 WHEN 守卫检查 K0-2 数据验证 THEN 系统 SHALL 断言 DV 覆盖行区**非对称**：被审计单位提供信息段为 `C7:C24`/`J7:J24`/`L7:L24`/`N7:N24`（到 24 行），回函段与二次发函段为 `P7:P26`/`Q7:R26`/`V7:X26`/`AB7:AB26`/`AD7:AE26`/`AK7:AK26`/`AL7:AL26`（到 26 行），并断言 `L7:L24` 的取值集合为 `发票/合同地址核实,电话核实,官网/公告查询,地图查询,邮件确认,其他方式`。
1.11 WHEN 守卫检查 K0-3 THEN 系统 SHALL 断言其为备忘录式叙述表，含**两套话术**（`A10:A13` 即时确认 / `A15:A17` 留函待寄回）+ **电话回访确认段**（`A18:A19`）+ 事后收回补记（`A21`）+ 3 个控制点（`A23:A25`，DV `是,否`）+ 签名行（`A27`），且 `A13`/`A17` 逐字含「工号为[XX]（如有）」。
1.12 WHEN 守卫检查 K0-4 THEN 系统 SHALL 断言 9 列（`询证函索引号`/`被询证单位名称`/`账户/交易`/`发函金额`/`回函金额`/`差异`/`差异原因`/`相关支持性证据`/`是否调整`）、数据行 `r6:r20`（15 行）、`F{r}=D{r}-E{r}`、合计行 `r21` 且 `D21/E21/F21=SUM(:20)`。
1.13 WHEN 守卫检查 K0-5/K0-6 THEN 系统 SHALL 断言各含 `A6 一、样本选取标准与规模`（6 项）+ `A11:E11` 函证项目余额表（`函证项目`/`年初余额`/`借方发生额`/`贷方发生额`/`期末余额`，`E12=B12+C12-D12`）+ **4 张检查表**（`A14` 期后收款/付款 / `A25` 期末余额支持性证据 / `A37`（1）本期借方发生额 / `A47`（2）本期贷方发生额）+ `A57 三、审计说明` + `A61 四、审计结论` + 编制说明 3 条替代程序要点；并断言 K0-5 段①证据组为 `银行回单{日期,付款方,金额}`+`支持性文件1{识别特征,信息1,信息2}`，K0-6 段①为 `付款审批单{日期/编号,是否经过恰当审批}`+`银行回单{日期,收款方,金额}`。
1.14 WHEN 守卫检查 K0-7 THEN 系统 SHALL 断言 **14 列**，其中 `G5:M5` 合并为父表头 `期末未收回原件函证可靠性验证`，叶子列逐字为 `被函证者身份确认（注1）`/`发函及回函传真信息及验证`/`发函邮箱`/`回函邮箱`/`邮箱可靠性验证（注2）`/`是否致电被函证者确认`/`对函证信息可靠性的考虑（注3）`，基本段为 `序号`/`函证索引号`/`被询证单位名称`/`回函方式`/`是否由审计项目组直接接收`/`是否寄回原件`，尾列为 `回函可靠性结论`；并断言源模板**无「回函日期」列**。
1.15 WHEN 守卫检查 K0-8 THEN 系统 SHALL 断言 19 条舞弊迹象 + `A25 ……` 可扩行 + `A26` 汇总行且 `H26='B50'`，列头为 `与函证程序有关的舞弊风险迹象`/`是否存在`/`索引号或信息来源`/`应对措施`，两条 tooltip 举例位于 `J19`/`J20`。
1.16 WHEN 守卫检查 K0A THEN 系统 SHALL 断言 **12 条程序**，D 列程序分类取值集合为 `{常规★, 备选, 舞弊应对/IPO/上市/新三板/重组}` 且第 12 条 D 列为 `常规★`、第 8 条无 E 列索引，E 列底稿索引号逐字一致（含 `K0-1/K0-2//K0-4` 这个源模板双斜杠事实）。
1.17 WHERE 守卫含反向自检 THE 系统 SHALL 在故意改写任一断言基准时打红（防正则失效或 `_norm` 归一过度导致断言空转）。

### Requirement 2: K0-1 列集与分段对齐源模板

**User Story:** 作为审计助理，我在 K0-1 上看到的列应当就是源模板的 28 列，不多不少，分段与用词与源模板一致，否则我不知道该往哪一格填、矩阵也聚合不出来。

#### Acceptance Criteria

2.1 WHEN 渲染 K0-1 宽表 THEN 系统 SHALL NOT 渲染 `send_memo` 列 —— 源模板 `C5:F5` 是**分组表头**「发函询证纪要」而非数据列，该列为伪列。
2.2 WHEN 撤回 `send_memo` 列 THEN 系统 SHALL 保留 `ConfirmationRow.send_memo` **字段**并在读取时兼容既有值（数据零丢失红线），SHALL 在 UI 上把既有非空值以只读提示呈现并说明「源模板无此列，请改填对应分段内的具体列」。
2.3 WHEN 渲染 K0-1 宽表 THEN 系统 SHALL 把 `sample_purpose`/`entity_name`/`account_type`/`amount` 四列归入 `send_memo`（发函询证纪要）段，把 `diff_ref_index`/`remark` 归入 `reply_amount`（回函金额确认）段，使分段与源模板 6 段逐段对应。
2.4 WHEN 渲染 K0-1 宽表 THEN 系统 SHALL 把 `row_conclusion` 归入 `row_summary`（行级审计结论）段 —— 与 G0/H0 的 `g0_row_conclusion`/`h0_row_conclusion` 一致（源模板 `AB5` 是与前五段并列的独立段，`confirmationColumnSpec.ts` 现有注释已指明 K0/L0 归属待修正）；SHALL NOT 继续挂在 `send_memo` 段下，SHALL NOT 为此新建第三个结论段。
2.5 WHERE 源模板用词与 BASE 列标签分叉 THE 系统 SHALL 在**既有** `CYCLE_COLUMN_LABEL_OVERRIDES` 中增 `K0` 声明（该机制已由 H0/G0 建好，现仅含两 key），K0 侧显示源模板用词：`账户/交易`(account_type) / `金额`(amount) / `询证函索引号`(confirm_index) / `发函单号/跟函记录索引号`(send_doc_no) / `收件地址`(entity_address) / `地址核查是否一致`(send_addr_match) / `是否收到回函`(is_replied) / `是否相符`(match_status) / `回函日期`(reply_date) / `差异`(difference) / `替代后可确认金额`(alt_confirmed) / `替代程序索引号`(alt_ref_index) / `其他说明/备注`(remark)；SHALL NOT 改动 `BASE_CONFIRMATION_COLUMNS` 的任何 label 或 `key`（`account_type` 是矩阵 SUMIF 的品种维度且已被 E0/F0/H0 消费）。
2.6 WHEN 渲染 K0-1 宽表 THEN 系统 SHALL 在 `CYCLE_EXCLUDED_COLUMNS.K0` 剔除源模板没有的 `contact_person`/`contact_phone`/`currency` 三列（它们在 K0-2 的 `F`/`G` 列），与 G0/H0 同款处置；SHALL 仅影响渲染，SHALL NOT 删除既有持久化字段值。
2.7 WHERE 源模板 `G6 函证方式` 实为**渠道**（`K0-2!C7:C24` 的 DV 为 `邮寄/跟函/电子函证/其他`，经 VLOOKUP 带入 `K0-1!G`）THE 系统 SHALL 为 K0 启用 G0/H0 已建的 `send_channel` variant 列；并 SHALL 保留 `confirmation_method` 作**显式登记的源外保留列**（承载准则 1312 的积极式/消极式，源模板无此列），label 改为「函证类型（积极式/消极式）」，与 G0/H0 处置一致。
2.8 WHEN 列集变更 THEN 系统 SHALL 保持 D0/E0/F0/G0/H0 五个循环的列集与标签**逐字节不变**（零回归支点）；L0 与 K0 共用 `send_memo`/`row_conclusion` variant，其变更 SHALL 在守卫中显式声明为**同步生效**并交叉锁死到 L0 源模板（若 L0 源模板用词不同则各自声明 override）。
2.9 WHEN 守卫运行 THEN 系统 SHALL 断言 `resolveConfirmationColumns('K0')` 覆盖源模板 R6 的 **28** 个叶子列（一一映射、含分段归属），且除 `confirmation_method` 这一显式登记的源外保留列外**不含任何源模板没有的列**。

### Requirement 3: K0-1 下区四块

**User Story:** 作为现场经理，我需要在 K0-1 上编制「函证情况／样本选择／审计说明／审计结论」四块，其中函证情况按科目自动聚合，否则整张汇总表无法得出函证覆盖率结论，也无法支撑审计意见。

#### Acceptance Criteria

3.1 WHEN K0-1 渲染 THEN 系统 SHALL 显示四块可折叠区域，标题逐字取自源模板（`一、函证情况` / `二、样本选择` / `三、审计说明` / `四、审计结论`）。
3.2 WHEN 「一、函证情况」渲染 THEN 系统 SHALL 按 **2 品种（其他应收款 / 其他应付款）× 8 指标**输出矩阵，指标顺序与文字逐字取自源模板 `C29:C36`。
3.3 WHEN 计算矩阵 THEN 系统 SHALL 按源模板公式取值：发函金额 = `Σ grid[账户/交易=品种].金额(F)`；回函确认金额 = `Σ grid[…].可确认金额(U)`；替代测试确认金额 = `Σ grid[…].替代后可确认金额(Y)`；三个比例为派生；末行 = `(替代+回函)/账面`。
3.4 IF 分母缺失或为 0 THEN 系统 SHALL 渲染「-」（null），SHALL NOT 产出 NaN/Infinity，也 SHALL NOT 用 0 冒充。
3.5 WHERE 「本期（期末）账面金额」行在源模板无公式（手填）THE 系统 SHALL 允许手工录入，并在有自动取数时以手工值优先。
3.6 WHEN 「二、样本选择」渲染 THEN 系统 SHALL 提供源模板 6 项（测试范围 / 特定样本 / 抽样总体 / 确定的抽样样本量 / 抽样方法 / 抽样过程），每项以源模板示例文字作 placeholder 并标注源模板锚点，并把 `J32` 样本计算器提示与 `J36` 抽样工具底稿引用就地展示；SHALL 沿用 G0 已确立的范式 —— 在 `ConfirmationSampling.vue` 内以 `isK0` 门控 + 字段映射表复用既有 `sampling_*` 持久化字段，文字真源 import 自 K0 侧声明文件；SHALL NOT 在组件内抄第二份文案，SHALL NOT 新造第二套抽样持久化字段名。
3.7 WHEN 「三、审计说明」渲染 THEN 系统 SHALL 提供源模板 **5 项**录入位置（对询证函保持的控制的说明 / 对误差的分析 / 对以传真或电子邮件形式收到的回函的可靠性的考虑 / 针对不符事项的程序 / 针对未回函的替代程序），每项配 AI 辅助与复核入口。
3.8 WHERE 既有共享 `ConfirmationNotes` 的 5 个字段（`note_general`/`note_exception`/`note_unreplied`/`note_alternative`/`note_other`）与源模板 5 项**不对应** THE 系统 SHALL 保留既有字段与既有值（零丢失），并以**per-cycle 说明项声明**的方式给 K0 提供源模板 5 项；SHALL 对能明确对应的项做只读引用而非重复录入（`针对未回函的替代程序`↔`note_alternative`），无法对应的项使用新键。
3.9 WHERE 源模板把一句话拆成两格（`X29`+`X30` 界定误差构成条件）THE 系统 SHALL 合并渲染为完整句子，SHALL NOT 出现半句话。
3.10 WHEN 「四、审计结论」渲染 THEN 系统 SHALL 提供结论录入位置，并以源模板 `A64:B66` 的参考结论 A/B/C 作可一键套用的选项。
3.11 WHEN 下区渲染 THEN 系统 SHALL 把源模板编制说明（准则 1312 第十条六项选样要求 / 函证注意事项 8 条 / 后附审计证据 / `A40` 传真电邮提示）作只读方法论上下文就地展示（折叠），SHALL NOT 让审计师去翻源 xlsx。
3.12 WHERE 下区新增录入位置 THE 系统 SHALL 使用独立持久化键，SHALL NOT 与上区 grid 或既有 `sampling`/`notes`/`conclusion` 键冲突。

### Requirement 4: 品种矩阵账面金额取数

**User Story:** 作为审计助理，我希望矩阵的「本期（期末）账面金额」能从四表库自动带入，而不是逐格手抄，也不希望它悄悄取错科目。

#### Acceptance Criteria

4.1 WHEN 声明 K0 矩阵品种 THEN 系统 SHALL 以声明式清单给出 2 个品种及其 `source_ref`，逐字标注为 `函证结果汇总表K0-1!E28` 与 `!F28`。
4.2 WHEN 取账面金额 THEN 系统 SHALL 按 `report_config` 实证映射取数：其他应收款 = **`BS-009`**（`soe_standalone` 公式为 `TB('1221') − TB('1231-03') + TB('1131')`，即**净额口径**）；其他应付款 = **`BS-050`**（`TB('2241') + TB('2231')`，`listed_standalone`/`soe_standalone` 侧含 `2231`）。
4.3 WHERE `report_config` 存在 `BS-075` 同名行「其他应付款」且 `formula` 为 NULL THE 系统 SHALL 按 **row_code 精确匹配**取 `BS-050`，SHALL NOT 按 row_name 匹配（同 K2 的 `BS-014`/`BS-017` 同名坑）。
4.4 WHERE 账面金额来自相邻循环审定表 THE 系统 SHALL 读取 K1 / K3 render-config 的既有取数出口；缺失时返回 `undefined`（**非 0**），使「本项目无此科目」与「余额为 0」可区分。
4.5 WHEN 品种科目码写入代码 THEN 系统 SHALL 只作**兜底与展示**，运行态一律走既有 `four_table/` 共享件与语义定位结果，SHALL NOT 让取数改回按硬编码码查询。
4.6 WHEN 守卫运行 THEN 系统 SHALL 断言品种清单与后端 K 循环 spec 声明的报表行**双向锁死**（前端多一个品种或后端改一个 row_code 都打红），并断言 `BS-009` 取的是净额口径（含备抵扣减）。

### Requirement 5: 公式预设纠正

**User Story:** 作为审计助理，我在公式管理页看到的 K0 预设应当对应真实存在的 sheet 与真实需要取数的格子，而不是一个指向不存在 sheet 的审定表口径块。

#### Acceptance Criteria

5.1 WHEN 修订 K0 公式预设 THEN 系统 SHALL 把 `sheet` 由 `审定表K0-1`（源 xlsx **无此 tab**）改为真实 tab 名 `函证结果汇总表K0-1`。
5.2 WHEN 修订 K0 公式预设 THEN 系统 SHALL 把 `account_codes` 由 `['1221']` 补齐为其他应收款与其他应付款两侧科目，并使 `cell_ref` 对应源模板下区矩阵的「本期（期末）账面金额」两格（`E29`/`F29`）而非审定表口径的「期初余额/未审数」。
5.3 WHERE 修订脚本运行 THE 系统 SHALL 提供 `--dry-run` / `--check` / `--apply` 三态且幂等（`--check` 在已修订后返回 0 项欠账），并带 round-trip 自检（`json.dumps` 不能逐字复现原文即 exit 非 0，防全文件重排与并发冲突）。
5.4 WHEN 校验器扫描预设 THEN 系统 SHALL 只扫**语义字段**（`formula`/`formula_type`/`account_codes`/`applies_when`），SHALL NOT 对 `description`/`notes` 整块做「不得出现 xxx」断言（说明文字会如实写出被纠正的反例）。
5.5 WHEN 守卫运行 THEN 系统 SHALL 断言 K0 预设块的 `sheet` 值存在于源 xlsx 的可见 sheet 名集合中，且**该断言对全部 7 个函证循环生效**（E0 的 `审定表E0-1` 同款笔误将因此打红，属已知预存在缺陷，登记为白名单并写明归属 spec）。

### Requirement 6: 源模板索引号笔误与底稿目录跳号

**User Story:** 作为质控复核人，我需要 UI 上的交叉索引指向真实存在的底稿，同时不因源模板笔误而让人以为平台改写了源模板。

#### Acceptance Criteria

6.1 WHERE 源模板存在三处索引号笔误 THE 系统 SHALL 按**意图**实现跳转目标：`K0-1!V6 调节索引（K1-12）` → `K0-4`（函证差异调节表）；`K0-1!S32 …可靠性的考虑（K0-6）` → `K0-7`（邮件传真回函可靠性验证，`K0-6` 实为其他应付款替代程序）；`K0-2!AA6 跟函函证控制过程（K1-11）` → `K0-3`（跟函函证过程控制）。
6.2 WHEN 展示修正后的索引号 THEN 系统 SHALL 在 tooltip 中标注源模板原值及「源模板索引号笔误」说明，SHALL NOT 静默改写，SHALL NOT 改动源 xlsx。
6.3 WHERE 底稿目录序号跳号（`[1,2,3,4,5,7,8,9,10]`，9 行末号为 10）THE 系统 SHALL 以**索引号**（`K0A`/`K0-1`~`K0-8`）作定位与展示的真源，SHALL NOT 依赖目录序号推导底稿数量或顺序。
6.4 WHEN 守卫运行 THEN 系统 SHALL 断言三处笔误映射在代码中有显式登记（含源模板原值与修正值两列），并断言 `wp_code_overrides.json` 的 K0 条目覆盖 9 个索引号且无一为 `skip`。

### Requirement 7: K0-5/K0-6 局部对齐源模板

**User Story:** 作为审计助理，我在 K0-5/K0-6 上录入的证据列应当是源模板要求的要素、列名语义不能反，否则替代程序做了也证明不了。

#### Acceptance Criteria

7.1 WHERE K0-5 段①「银行回单」的对方当事人在源模板 `G16` 逐字为「**付款方**」（其他应收款收回款项，对方是付款方）THE 系统 SHALL 把 `receipt_payer` 的 label 由「收款方」改为「付款方」；SHALL 保持 K0-6 段①对应列为「收款方」（源 `I16`），SHALL NOT 把两者统一。
7.2 WHEN K0-5 段① 渲染 THEN 系统 SHALL 补齐源模板 `I15:K16` 的 `支持性文件1{识别特征,信息1,信息2}` 三列；SHALL 保持源模板银行回单为「日期」单列的事实，对既有合成列「日期/编号」SHALL 保留字段并把 label 回归源模板用词。
7.3 WHERE 源模板 `O15`/`O26`/`O38` 逐字为「检查的关键证据和要素根据被审计单位具体情况修改」THE 系统 SHALL 把该红字提示作方法论上下文（琥珀色左边线+浅黄背景）就地展示在对应区块上方，使既有具体化证据列（审批单/借据协议等）的**源模板依据**可见。
7.4 WHEN 呈现 K0-5/K0-6 编制说明 THEN 系统 SHALL 内嵌源模板 3 条替代程序要点（检查本期付款、期后收货或回收 / 检查原始凭证 / 对回函可能性不高且余额重大的发函同时执行替代程序）。
7.5 WHERE 源模板 K0-5 `M46=SUM(M40:M45)` 对「索引号」文本列求和 THE 系统 SHALL NOT 实现该合计（源模板笔误），SHALL 在守卫中登记该笔误。
7.6 WHEN 守卫运行 THEN 系统 SHALL 以 openpyxl 直读源 xlsx 交叉比对 K0-5/K0-6 四区块列定义，断言两侧段①的对方当事人 label **必须不同**（反向自检：统一为同一词即打红），且既有源外增强区块（block4 往来对账）仍在 `SOURCE_EXTRA_MANIFEST` 登记内。

### Requirement 8: K0-2 第二次发函被函证单位信息

**User Story:** 作为审计助理，第一次发函被退回后我需要记录第二次发函所用的新单位信息，否则「是否进行第二次发函=是」之后没有任何可填的地方，二次发函过程无法留痕。

#### Acceptance Criteria

8.1 WHEN `is_second_send` 为真 THEN 系统 SHALL 提供源模板 `AF6:AK6` 六列录入位置：`地址`/`邮编`/`联系人`/`联系电话`/`传真`/`信息是否核查一致`。
8.2 WHEN 新增六列 THEN 系统 SHALL 以 additive 可选字段扩展 `EntityVerifyRow`，旧 `entity-verify-v1` payload 读回时为 `undefined`，写回 SHALL NOT 产生 `undefined` 键。
8.3 WHERE `is_second_send` 为假或未填 THE 系统 SHALL 折叠该六列区域，SHALL NOT 产生空列噪声。
8.4 WHEN 渲染 K0-2 THEN 系统 SHALL 把源模板五条编制说明（`A28:A41` 说明 1~5）作只读方法论上下文就地展示，其中说明 3「记录确认联系人身份的过程…注意核实联系人的身份并记录工号（若有）」SHALL 与 K0-3 的工号要求交叉呼应。
8.5 WHEN 守卫运行 THEN 系统 SHALL 断言六列字段名与源模板叶子列一一映射，且 `EntityVerifyRow` 的字段总数变化仅为 additive（无删除、无重命名）。

### Requirement 9: K0-7 按渠道可靠性列渲染（共享件缺口）

**User Story:** 作为审计助理，我需要按回函渠道填对应的可靠性核对项，而不是面对一堆不适用的列；同时已经在类型里声明的核对项必须真的能在界面上填。

#### Acceptance Criteria

9.1 WHERE `ReliabilityRow` 已声明 12 个按渠道核对字段（`signed_by_both`/`signer_in_public_list`/`envelope_addr_match`/`postmark_city_match`/`reply_info_complete`/`followup_flow_known`/`followup_identity_verified`/`followup_normal_process`/`esign_match`/`ip_match`/`platform_op_time`/`platform_feedback`）而 `ReliabilityGrid.vue` 对其**零引用** THE 系统 SHALL 判定为「类型加了、UI 从未渲染」的死字段，SHALL 在 UI 上提供录入位置或明确撤回，SHALL NOT 让其继续以死字段形态存在。
9.2 WHEN 渲染 K0-7 THEN 系统 SHALL 提供源模板 `G5:M5` 的父表头「期末未收回原件函证可靠性验证」，并使 `G:M` 七列在该父表头下分组。
9.3 WHERE 源模板 K0-7 **无「回函日期」列**而平台渲染了该列 THE 系统 SHALL 按循环控制该列可见性，SHALL 保持 D0/F0/G0/H0/L0 侧行为不变（其源模板是否有该列须各自核实，本 spec 只处置 K0 侧）。
9.4 WHEN 列标签渲染 THEN 系统 SHALL 使 K0 侧显示源模板用词：`被函证者身份确认`/`邮箱可靠性验证`/`对函证信息可靠性的考虑`/`是否由审计项目组直接接收`/`是否寄回原件`/`回函可靠性结论`。
9.5 WHERE `RELIABILITY_COLUMN_CONFIG`（14 列常量）被 `ReliabilityGrid.vue` **零引用** THE 系统 SHALL 在守卫中登记该死配置及其归属，SHALL NOT 在本 spec 内清理（平台级，六循环共享）。
9.6 WHEN 守卫运行 THEN 系统 SHALL 断言 12 个按渠道字段全部有 UI 消费方（源码级扫描），并含反向自检（删除任一渲染点即打红）。

### Requirement 10: K0-3 跟函话术补齐（共享件缺口）

**User Story:** 作为审计助理，我用跟函备忘录模板生成的文字应当包含源模板要求的全部核实要素（尤其工号与电话回访核实的具体内容），否则跟函过程记录不完整。

#### Acceptance Criteria

10.1 WHERE 源模板 `K0-3!A13`/`A17` 逐字要求记录处理人员「工号为[XX]（如有）」而通用话术（`IMMEDIATE_CONFIRM_TPL`/`LATER_FOLLOW_TPL`）**无工号占位** THE 系统 SHALL 补入工号占位；SHALL 使该补充对 D0/F0/G0/H0/K0/L0 六个通用循环同时生效（源模板同款要求）。
10.2 WHERE 源模板 `A18:A19` 的电话回访要求「与被函证单位工作人员确认其确实于[日期]接待我们的跟函人员」THE 系统 SHALL 在 `LATER_FOLLOW_TPL` 中补入该核实要点占位，SHALL NOT 只保留笼统的「跟踪确认结果」。
10.3 WHEN 修改通用话术 THEN 系统 SHALL 保持 `getTemplate(scenario)` 与 `getTemplate(scenario, boolean)` 两种旧签名的**调用形态**不变（零回归），E0 五段银行专属话术**逐字不变**。
10.4 WHEN 守卫运行 THEN 系统 SHALL 断言通用话术含工号占位与接待事实核实占位，且 E0 五段话术与源模板 `E0-7` 逐字一致（交叉锁死，防改通用话术时误伤 E0）。

### Requirement 11: 共享件所有权与并发边界

**User Story:** 作为维护者，我需要明确哪些改动属于本 spec、哪些属于并发 spec，否则两个会话会互相回退同一批文件。

#### Acceptance Criteria

11.1 WHERE `f0-confirmation-linkage-and-structural-enhancement`（28/31，含 `[-]`）正在被并发会话推进 THE 本 spec SHALL NOT 在其收口前改动 `GtConfirmationSummary.vue` / `f0SummaryAggregation.ts` / `f0MatrixDataSources.ts`。
11.2 WHERE 平台已存在三份品种矩阵（`e0SummaryMatrix.ts` 6×6 / `f0SummaryAggregation.ts` 4×8 / `h0SummaryMatrix.ts` 动态×8）且 H0 已确立范式「复用 `safeRatio`/`sumByCategory` 纯函数、指标与品种常量各自声明」THE 本 spec SHALL 沿用该范式新建 K0 侧矩阵，SHALL NOT 把三份重构成统一内核（重构半径覆盖 E0/F0/H0/G0 四个已收口或在跑的 spec，风险高于收益）。
11.3 WHEN 新建 K0 矩阵 THEN 系统 SHALL 保持 E0/F0/H0 三份矩阵的**渲染结果逐字节不变**（零回归支点），SHALL NOT 改动 `safeRatio`/`sumByCategory` 的行为（E0 侧分母为 0 返回 `0` 与 F0/H0 侧返回 `null` 是既有差异，各自实现，不统一）。
11.4 WHERE 本 spec 的改动落在共享件上（`confirmationColumnSpec.ts` 分段与标签覆盖机制 / `memoTemplates.ts` 通用话术 / `ReliabilityGrid.vue` 渠道列 / `entityVerifyTypes.ts` 二次发函列）THE 系统 SHALL 在守卫中对每个受影响循环声明「变更是否同步生效」，并对声明为「不变」的循环断言逐字节不变。
11.5 WHEN 本 spec 任务开始前 THEN 系统 SHALL 复查并发 spec 的 tasks.md mtime 与标记状态；IF 发现 `[-]` 仍在 THEN 系统 SHALL 只推进 Wave 1/Wave 2（不碰共享件的部分）。
11.6 WHEN 守卫运行 THEN 系统 SHALL 断言本 spec 新建的每个模块都有真实消费方（源码级扫描，零消费方即打红），防重演「模块写好从未接线」。

## Glossary

| 术语 | 含义 |
|---|---|
| K0 | 管理循环函证枢纽，源模板 `backend/wp_templates/K/K0 管理循环函证.xlsx`，10 张可见 sheet + 1 张 hidden `GT_Custom` |
| K0A | 函证程序表（12 条程序，D 列「程序分类」= 常规★/备选/舞弊应对·IPO 类） |
| K0-1 | 函证结果汇总表，上区 28 列 6 段 20 数据行 + 下区四块（函证情况矩阵/样本选择/审计说明/审计结论） |
| K0-2 | 核实被函证单位信息，38 列 5 段（提供信息核对 14 列 / 回函核对 12 列 / 一次发函结果 4 列 / 二次发函信息 6 列 / 二次发函结果 1 列） |
| K0-3 | 跟函函证过程控制，备忘录式叙述表（两套话术 + 电话回访 + 3 控制点 + 签名） |
| K0-4 | 函证差异调节表，9 列 15 行 + 合计行 |
| K0-5 / K0-6 | 其他应收款 / 其他应付款替代程序检查表，各 4 张检查表（段③按借贷拆两表） |
| K0-7 | 邮件传真回函可靠性验证，14 列（`G:M` 为「期末未收回原件函证可靠性验证」父表头下 7 列） |
| K0-8 | 函证程序舞弊风险评价表，19 条迹象 + 可扩行 + 汇总行（去向 B50） |
| 品种矩阵 | K0-1 下区「一、函证情况」= 2 品种（其他应收款/其他应付款）× 8 指标，按 `SUMIF(账户/交易, 品种, 金额|可确认金额|替代后可确认金额)` 聚合 |
| 账户/交易 | 源模板 K0-1 `E6` 列名，对应平台 `ConfirmationRow.account_type`（矩阵 SUMIF 的品种维度键） |
| 伪列 | 把源模板的**分组表头**（合并单元格）误当成数据列的实现，如 `send_memo`（源 `C5:F5` 是「发函询证纪要」段头） |
| 源外增强 | 源模板没有该区块/列、由平台自建的能力，须在 `SOURCE_EXTRA_MANIFEST` 显式登记依据 |
| 死字段 / 死配置 | 类型或常量已声明但零 UI 消费方（如 `ReliabilityRow` 的 12 个渠道字段、`RELIABILITY_COLUMN_CONFIG`） |
| 定位值 / 展示值 | 定位值 = 源模板真实 tab 名（用于 `?sheet=` 与请求）；展示值 = 底稿目录索引号（用于 UI），二者分离（H10 范式） |
| BS-009 / BS-050 | `report_config` 实证报表行：其他应收款（净额口径，含备抵扣减）/ 其他应付款（含 `2231`）；`BS-075` 是同名 NULL 行，须按 row_code 精确匹配 |
