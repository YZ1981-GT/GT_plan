# Requirements Document

## Introduction

L0 债务循环函证（长期应付款 / 应付债券）源模板逐 sheet 精读后，与平台现状比对出五类缺口。本 spec 参照 E0/G0/H0 已收口的范式修复。

**源模板事实基线**（`backend/wp_templates/L/L0 债务循环函证.xlsx`，openpyxl 直读，102076 字节）：

- **10 张 sheet = 9 visible + 1 hidden**（`函证差异检查表（示例）` 为 hidden）；`底稿目录!D3:F11` 索引 7 项：L0A / L0-1 / L0-2 / L0-3 / L0-4 / L0-5 / L0-6 / L0-7（共 8 行，序号列 `D5=D4+1` 递推）
- **程序表 tab 名是 `函证程序表F0A`**，而 `底稿目录!F4=L0A` —— 索引号真源是底稿目录，tab 名带 F0A 是源模板笔误
- **L0-1 上区 28 个数据列**（A..AB），5 段合并表头：`C5:F5 发函询证纪要` / `G5:K5 1、发函信息` / `L5:R5 2、收到回函` / `S5:W5 3、回函金额确认` / `X5:AA5 4、未收到回函的替代程序` / `AB5:AB7 审计结论`（rowspan，独立末列）
- **L0-1 下区四块**：`C28 一、函证情况`（2 品种 × 8 指标）/ `J28 二、样本选择`（6 项）/ `S28 二、审计说明`（源模板笔误，序号应为「三」；5 段）/ `C39 四、审计结论`；`A44` 起编制说明 26 行
- **L0-1 品种恰 2 个**：`E29 长期应付款` / `F29 应付债券`
- **L0-1 八指标公式**（与 F0-1/G0-1 逐条同构）：`E31=SUMIF($E$8:$E$27,E29,$F$8:$F$27)` / `E33=SUMIF(...,$U$8:$U$27)` / `E36=SUMIF(...,$Y$8:$Y$27)` / `E32=IF(ISERROR(E31/E30),0,E31/E30)` / `E34`、`E35` 同形 / `E37=(E36+E33)/E30`
- **L0A 12 条程序**（R7:R18），带 `D 程序分类`（`常规★` ×9 = R7/R9/R10/R11/R12/R15/R16/R17/R18；`舞弊应对/IPO/上市/新三板/重组` ×1 = R8；`备选` ×2 = R13/R14）与 `E 底稿索引号`（**R14 与 R18 的 E 列为空**，属源模板事实）；**程序 1 的 G7 批注逐字**「本函证不包含银行长期借款、银行短期借款函证，与银行借款相关函证详见货币资金循环」；程序 8 的 G14 批注含第三方平台技术提示3号链接
- **L0-1 数据有效性（真实格，非镜像残留）**：`C8:C27` = `A. 大额,B.异常,C.余额为0,D.账龄长,E.随机`；`L8:L27 N8:N27 X8:X27` = `√,×`。`JK8:JL27` / `JN8:JP27` 等远端列是**列重复产生的镜像残留 sqref**，不落在真实列上
- **L0-2 数据有效性**：`C7:C24` = `邮寄,跟函,电子函证,其他`（发函渠道）/ `P7:P26` = `纸质原件,电子函证,其他介质` / `L7:L24` = 6 项核实方式 —— 与 X0-2 六枢纽同构
- **L0-1!G 函证方式** 由 `=VLOOKUP(B8,'核实被函证单位信息L0-2'!A:AL,3,0)` 带入，即 L0-2!C 的渠道枚举
- **三处索引号笔误**：tab `函证程序表F0A`（应 L0A）/ `L0-1!V6 调节索引（F0-4）`（应 L0-4）/ `L0-2!AA6 跟函函证控制过程（F0-3）`（应 L0-3）

**科目映射真源**（`report_config` DB 实证，四准则一致）：长期应付款 `BS-064 = TB('2701','期末余额')`；应付债券 `BS-062 = TB('2502','期末余额')`。两者已由 `four_table/l_cycle_specs.py` 的 `L5_SPEC` / `L4_SPEC` 声明，本 spec **复用不重建**。

**范围外**（已核实无需改动）：L0-2 三区列集、L0-3 三个控制核对点 + 工号 + 签名、L0-5 抽样参数 6 项 + 审计说明/结论 + 4 区块 + 期初一致性核对、L0-6 可靠性列集与注1~注3、L0-7 十九条舞弊迹象 —— 均已由 `e0/g0/h0/k0` 系列 spec 在共享组件内收口，L0 直接受益。

## Requirements

### Requirement 1: 程序表 L0A 运行时可用

**User Story:** 作为审计助理，我打开 L0 程序表时应看到债务循环的 12 条函证程序，而不是存货循环的程序。

#### Acceptance Criteria

1.1. WHEN 调用 `get_template('L0A')` THEN 系统 SHALL 返回非 None 的模板对象，其 `name` 为债务循环语义且 `items` 长度为 12
1.2. WHEN 调用 `resolve_program_template_code('函证程序表F0A', 'L0')` THEN 系统 SHALL 返回 `L0A`（而非 `F0A`）
1.3. `L0A` 模板的 12 个 item 的 `description` SHALL 与源模板 `函证程序表F0A!B7:B18` 逐字一致
1.4. `L0A` 模板的 12 个 item SHALL 携带 `program_category`，取值逐条取自源模板 `D7:D18`
1.5. `L0A` 模板的 item `ref_index` SHALL 取自源模板 `E7:E18`，且 SHALL NOT 出现任何 `F0-` 前缀的索引号
1.6. 程序 1 的批注 SHALL 保留源模板 `G7` 原文（银行借款排除声明）；程序 8 的批注 SHALL 保留 `G14` 原文。两者 SHALL 承载在 item 的 `content` 末尾（`\n【提示】…`），SHALL NOT 新增 `hint` 之类不被 `ProcedureTableService` 透传的字段
1.9. item 的字段名 SHALL 与 `tables` 既有形态一致：`content`（必填，服务侧以 `item["content"]` 读取）/ `ref_index` / `program_category` / `auto_data_source` / `applicable_default`
1.7. 修复 SHALL 采用往 `tables` 增补 `L0A` 条目的加法式方案，SHALL NOT 改动 `tables` 内既有 121 条中任何一条
1.8. `F0A` 在 `tables` 中的既有条目（采购存货循环，12 items）SHALL 逐字节不变

### Requirement 2: 公式预设纠偏

**User Story:** 作为现场经理，L0 的取数公式必须指向长期应付款/应付债券，不能把源模板明确排除的银行借款算进来。

#### Acceptance Criteria

2.1. L0 预设块的 `sheet` SHALL 为源 xlsx 真实存在的 tab 名 `函证结果汇总表L0-1`（现值 `审定表L0-1` 在源 xlsx 中不存在）
2.2. L0 预设块的 `account_codes` SHALL 为 `['2701', '2502']`（现值 `['2001','2501']` 分别是短期借款与长期借款）
2.3. L0 预设 SHALL NOT 含区间函数 `SUM_TB`/`TB_SUM`（现值 `TB_SUM('2001~2501', ...)` 会把该区间内全部负债科目扫入）
2.4. L0 预设的 `cell_ref` SHALL 为矩阵手工覆盖键 `L0-1-matrix-{品种}-book_amount`（现值「期初余额」/「未审数」是审定表口径，而函证枢纽无审定表 → 预设永远落不到矩阵上）
2.8. L0 预设的 `formula_type` SHALL 为 `PLACEHOLDER`，SHALL NOT 写 `TB()` —— `cell_ref` 同时是手工覆盖键，写 `TB()` 会让「按码取到的 0」伪装成审计师手填值，压住语义定位拿到的 `undefined`，使「本项目无此科目」与「余额为 0」不可区分（与 R3.4 冲突）
2.9. `account_codes` SHALL 仅作展示与筛选，运行态取数 SHALL 走 `four_table` 语义定位；`2702 未确认融资费用` 列入时 SHALL 在 `description` 说明它是**独立一级科目**（非 `2701` 子科目，`LIKE '2701%'` 扫不到）且 `BS-064` 口径**不减**它
2.5. 修正 SHALL 由幂等脚本执行，`--check` 在修正后 SHALL 返回 0 项欠账
2.6. 幂等脚本 SHALL 带 round-trip 自检：`json.dumps` 不能逐字复现原文时以非零码退出
2.7. 幂等脚本的校验器 SHALL 只扫语义字段（`formula` / `formula_type` / `account_codes` / `cell_ref`），SHALL NOT 对整块序列化文本做「不得出现 xxx」断言（`description` 会如实写出被纠正的反例）

### Requirement 3: L0-1 下区四块

**User Story:** 作为审计助理，L0-1 汇总表下方应有函证情况矩阵、样本选择、审计说明、审计结论四块，而不是只有上区表格。

#### Acceptance Criteria

3.1. 「一、函证情况」SHALL 渲染 2 品种（长期应付款 / 应付债券）× 8 指标矩阵，指标顺序与 label 逐字取自源模板 `C30:C37`
3.2. 矩阵 8 指标的计算口径 SHALL 与源模板公式一一对应：发函金额 = 按品种对 `F` 列求和；回函确认金额 = 按品种对 `U` 列求和；替代测试确认金额 = 按品种对 `Y` 列求和；三个比例列按源模板 `ISERROR` 兜底返 0；末行 = `(替代+回函)/账面`
3.3. 账面金额 SHALL 由后端按语义科目定位下发，取数 SHALL 复用 `four_table/l_cycle_specs.py` 的 `L5_SPEC`（长期应付款）与 `L4_SPEC`（应付债券），SHALL NOT 新写科目定位逻辑
3.4. WHEN 某品种账面金额取数为空 THEN 系统 SHALL 区分「本项目无此科目」与「余额为 0」两态，且 SHALL 允许手工覆盖
3.5. 手工覆盖的 item_id SHALL 沿用 G0/K0 已确立的矩阵键形态 `L0-1-matrix-{品种}-{指标key}` —— **品种用源模板中文字面**（它同时是上区 `E 账户/交易` 列 SUMIF 的 criteria，非可改文案），**指标用稳定 key**（非中文 label）；SHALL NOT 另立第二套键形态
3.6. 「二、样本选择」SHALL 渲染源模板 6 项（`J29` 测试总体 / `J30` 特定样本 / `J31` 抽样总体 / `J32` 确定的抽样样本量 / `J34` 抽样方法 / `J35` 抽样过程），`J33` 的括注 SHALL 作为提示文本而非独立录入项
3.7. 「三、审计说明」SHALL 渲染源模板 5 段：`S29` 对询证函保持的控制的说明 / `W29` 对误差的分析（含 `W30`+`W31` 两格拼成的误差界定条件）/ `S33` 对以传真或电子邮件形式收到的回函的可靠性的考虑 / `S34` 针对不符事项的程序（含 `S35` 补充说明）/ `S36` 针对未回函的替代程序
3.8. 源模板 `S28` 的字面「二、审计说明」是序号笔误 THEN 平台 SHALL 显示「三、审计说明」并以 tooltip 标注源模板笔误
3.9. 「四、审计结论」SHALL 提供录入位，并以只读方式展示源模板 `A65:B68` 三条参考结论与 `A69` 后附审计证据说明
3.10. 下区各文本段 SHALL 落 `checklist_responses`，键前缀统一且与上区 grid 载荷互不覆盖
3.11. 下区 SHALL 由 `isL0` 门控，其余六枢纽的 `GtConfirmationSummary.vue` 渲染结果 SHALL 逐字节不变

### Requirement 4: L0-1 列集对齐源模板

**User Story:** 作为审计助理，L0-1 的列应与源模板 28 列一致，不要出现源模板没有的空列，也不要把合并段头当成一个可填列。

#### Acceptance Criteria

4.1. `send_memo` 是伪列 —— 源模板 `C5:F5` 是跨 4 列的合并段头（下辖 选取样本目的 / 被询证单位名称 / 账户/交易 / 金额），SHALL 从 `CYCLE_VARIANT_COLUMNS.L0` 撤除
4.2. 撤列 SHALL NOT 删除 `send_memo` 持久化字段值；既有值 SHALL 以只读方式呈现（数据零丢失红线）
4.3. `row_conclusion` 的 group SHALL 为 `row_summary`（源模板 `AB5:AB7` 是五段之外的独立末列），SHALL NOT 沿用 `send_memo`
4.4. `CYCLE_EXCLUDED_COLUMNS.L0` SHALL 含 `contact_person` / `contact_phone` / `currency` —— 源模板 L0-1 28 列中均无（联系人/电话在 L0-2 的 F/G 列）
4.5. SHALL 启用 variant 列 `send_channel` 承载源模板「函证方式」（渠道，`L0-2!C` 的 DV `邮寄/跟函/电子函证/其他` 经 VLOOKUP 带入 `L0-1!G`）
4.6. `confirmation_method` 的 L0 label SHALL 改为「函证类型（积极式/消极式）」，避免与渠道列同名；该列语义 SHALL 保持准则 1312 口径不变（其驱动可确认金额派生）
4.7. `CYCLE_COLUMN_LABEL_OVERRIDES.L0` SHALL 逐条取自源模板 `函证结果汇总表L0-1` 第 5/6 行表头字面
4.8. `diff_ref_index` 的源字面是「调节索引（F0-4）」，其中 `F0-4` 是索引号笔误 THEN label SHALL 显示为指向 `L0-4` 的正确索引，并以 tooltip 标注源模板笔误
4.9. 改动 SHALL 只增 L0 键 —— 其余六枢纽 `resolveConfirmationColumns` 输出 SHALL 逐字节不变
4.10. `confirmationColumnSourceManifest` 的 L0 条目 SHALL 与改后的 resolve 输出满足 `resolve ⊆ manifest`

### Requirement 5: 隐藏 sheet 不渲染为页签

**User Story:** 作为审计助理，L0 的页签应与 Excel 可见 sheet 一致，不应出现源模板里隐藏的示例表。

#### Acceptance Criteria

5.1. L0 的 render-config `sheets` SHALL 恰为 9 项，与 `函证差异检查表（示例）` 之外的 9 张可见 sheet 逐字一致
5.2. `函证差异检查表（示例）` 在 D0 与 F0 中是 **visible** THEN 处置 SHALL NOT 采用按裸 sheet 名标 `skip`（会误杀 D0/F0 的真实页签）
5.3. 处置 SHALL 采用 `{wp_code}-{sheet_name}` 复合键 skip 判定，加法式接在既有三条 skip 判定（全名 / 尾码 / 前缀码）之后
5.4. 复合键 skip 判定 SHALL 不改变任何既有 skip 行为：既有全名/尾码/前缀码命中路径 SHALL 优先且逐字节不变
5.5. D0 与 F0 的 render-config `sheets` 中 `函证差异检查表（示例）` SHALL 仍然存在
5.6. `cycleConfirmationMeta.L0.diffChecklistCode` SHALL 保持 `null`，与 5.1 的不渲染结论一致

### Requirement 6: 索引号笔误的定位/展示分离

**User Story:** 作为审计助理，跨表跳转要能定位到真实 sheet，同时界面上显示的索引号要是底稿目录裁决的正确值。

#### Acceptance Criteria

6.1. 定位值 SHALL 用源模板真实 tab 名；展示值 SHALL 用底稿目录 `F4:F11` 的索引号
6.2. 三处笔误 SHALL 逐条登记且带 tooltip 说明：程序表 tab `函证程序表F0A`（展示 L0A）/ `L0-1!V6`（展示 L0-4）/ `L0-2!AA6`（展示 L0-3）
6.3. 笔误登记 SHALL 采用 G0 已有的 `ConfirmationSheetRef` 机制（`sheetName` / `indexLabel` / `indexTypoNote`），SHALL NOT 新建第二套机制
6.4. `cycleConfirmationMeta.L0` 的既有 `*Code` 字段 SHALL 一个不删（加法式）

### Requirement 7: L0-5 区块标题与源模板对齐

**User Story:** 作为审计助理，L0-5 的区块标题应反映源模板的检查项，不应出现与程序表自相矛盾的用词。

#### Acceptance Criteria

7.1. block1 标题 SHALL 对齐源模板 `A13` 「1、检查期后付款」
7.2. block2 标题 SHALL 对齐源模板 `A20`「2、检查构成期末长期应付款余额的支持性文件（如合同等）」，SHALL NOT 含「银行对账单」「借款合同」等与 L0A 程序 1 银行借款排除声明矛盾的用词
7.3. block3 标题 SHALL 对齐源模板 `A28`「4、测试本期发生额」，其借贷两表副标题对齐 `A29`「（1）本期借方发生额」与 `A37`「（2）本期贷方发生额」
7.4. block4 SHALL 保持 `sourceExtra: true` 登记（源模板 L0-5 无抵质押/担保区块）
7.5. 标题改动 SHALL NOT 改变任何区块的 `block` key、列 key 与 `SUM_FIELDS`（已持久化数据零影响）
7.6. `alternativeBlockManifest.L05` 的 title SHALL 与组件实际渲染 title 逐字一致

### Requirement 8: 守卫与 CI

**User Story:** 作为质量控制复核合伙人，L0 的源模板事实必须被守卫钉死，避免下个会话又漂移回去。

#### Acceptance Criteria

8.1. SHALL 建后端守卫，以 openpyxl 直读源 xlsx 为裁决者，固化：9 visible + 1 hidden 的 sheet 状态、底稿目录 8 行索引、L0-1 五段表头与 28 列字面、8 指标公式、2 品种字面、L0A 12 条程序与分类、四处真实 DV、三处索引号笔误
8.2. 守卫 SHALL 含反向自检：断言镜像残留 sqref 确实存在于文件中但不覆盖真实格
8.3. SHALL 建前端守卫交叉锁死 L0 列集、矩阵指标 key、下区文案与后端导出的源模板 fixture
8.4. 每条守卫 SHALL 经变异检验（改一字看是否变红）；变异未打红 SHALL 视为守卫缺陷而非代码无误
8.5. 标签存在性断言 SHALL 带标签名边界（`<Foo(?=[\s/>])`），SHALL NOT 用 `toContain('<Foo')`
8.6. 读源码型守卫 SHALL 先 `stripComments()` 且配反向自检（断言原始源码确实含被禁字样）
8.7. 前端守卫的 `REPO_ROOT` SHALL 以双哨兵具体文件向上查找，SHALL NOT 写死回退级数
8.8. SHALL 挂 CI job，覆盖后端守卫、前端守卫、幂等脚本 `--check`

### Requirement 9: 波次隔离与共享件协调

**User Story:** 作为现场经理，L0 的改造不能把并发进行的 K0/F0 spec 弄坏。

#### Acceptance Criteria

9.1. 碰共享件的任务（`confirmationColumnSpec.ts` / `GtConfirmationSummary.vue` / `ConfirmationSampling.vue` / `alternativeBlockManifest.ts` / `wp_render_config.py`）SHALL 集中在独立波次
9.2. `confirmationColumnSpec.ts` 的改动 SHALL 为加法式最小 hunk，且与 K0 spec 的兼容判据 = 双方 record 各自键互不重叠
9.3. `GtConfirmationSummary.vue` 的 `isL0` 下区接入 SHALL 与 K0 spec 的 `isK0` 接入协调为同一次刀，SHALL NOT 并行编辑该文件
9.4. WHEN `f0-confirmation-linkage-and-structural-enhancement` 仍存在 `[-]` / `[~]` 标记 THEN 共享件波次 SHALL NOT 开工
9.5. L0 专属波次（程序表模板 / 公式预设 / 后端取数 / L0 专属声明文件与守卫）SHALL 零碰共享件，可独立推进
9.6. 改 `confirmationColumnSpec.ts` 后 SHALL 复查两处易过期断言：`confirmationColumnSpec.spec.ts` 的 `NO_EXCLUSION_CYCLES` 白名单与 `CONFIRMATION_SOURCE_MANIFEST` 的 L0 出处登记

### Requirement 10: 零回归

**User Story:** 作为质量控制复核合伙人，L0 的改造不得改变其余六个函证枢纽与 L1~L8 循环的任何既有行为。

#### Acceptance Criteria

10.1. D0 / E0 / F0 / G0 / H0 / K0 的 `resolveConfirmationColumns` 输出 SHALL 逐字节不变
10.2. D0 / E0 / F0 / G0 / H0 / K0 的 render-config `sheets` 集合 SHALL 逐字节不变
10.3. `F0A` / `E0A` / `D0A` / `G0A` / `H0A` / `K0A` 的 `get_template` 返回 SHALL 逐字节不变
10.4. L1~L8 循环的 render 输出 SHALL 不受本 spec 影响（本 spec 只读 `l_cycle_specs.py`，不改）
10.5. 共享组件（reliability / followup / alternativeD05 CheckBlock / entityVerify / fraudRisk）的既有 props 与渲染 SHALL 不变
10.6. 撤销伪列 SHALL NOT 触发任何既有项目的 `checklist_responses` / `html_data` 数据删除

## Glossary

| 术语 | 含义 |
|------|------|
| L0 | 债务循环函证枢纽（长期应付款 / 应付债券），源模板 `backend/wp_templates/L/L0 债务循环函证.xlsx` |
| L0A | 函证程序表（12 条程序）；源模板 tab 名笔误为 `函证程序表F0A`，索引号真源是底稿目录 `F4=L0A` |
| L0-1 | 函证结果汇总表（上区 28 列 + 下区四块） |
| 上区 | L0-1 第 5~27 行的函证明细 grid（5 段合并表头 + 20 行数据位） |
| 下区四块 | L0-1 第 28 行起的 一、函证情况 / 二、样本选择 / 三、审计说明 / 四、审计结论 |
| 品种 | 下区矩阵的列维度，取自 `L0-1!E29`「长期应付款」与 `F29`「应付债券」，对应上区 `E 账户/交易` 列的 SUMIF 条件 |
| 伪列 | 把源模板的跨列合并**段头**误实现成一个可填数据列（此处 = `send_memo`，源 `C5:F5` 下辖 4 列） |
| 镜像残留 sqref | Excel 列重复产生的远端列数据有效性引用（如 `JK8:JL27`），不落在真实列上，不得作为源模板事实 |
| 发函渠道 | `L0-2!C` 的 DV `邮寄/跟函/电子函证/其他`，经 VLOOKUP 带入 `L0-1!G`；平台字段 `send_channel` |
| 函证类型 | 准则 1312 的积极式/消极式，平台字段 `confirmation_method`，驱动可确认金额派生，与渠道不可互替 |
| 定位值 / 展示值 | 跨表跳转用真实 tab 名定位、界面用底稿目录索引号展示，两者分离以容纳源模板索引号笔误 |
| sourceExtra | 区块登记标记，表示该区块为平台自建增强而非源模板要求 |
