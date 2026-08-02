# Requirements Document

## Introduction

I 类六个循环（I1 无形资产 / I2 开发支出 / I3 商誉 / I4 长期待摊费用 / I5 其他非流动资产 /
I6 研发费用）目前**四表入库后底稿基本取不到数、披露表结构与源模板严重不符、附注模块列元数据
全缺**。本 spec 把 D/F/G/H/K/N 各循环已跑通的范式（`four_table` 共享件 + 报表行科目解析 +
叶子聚合 + `tb_source_codes` 溯源 + 源 xlsx 唯一裁决 + 幂等模板脚本 + 三向比对守卫）推广到 I 类，
使「四表入库 → 底稿刷新取数 → 披露表编制 → 推送附注」全链贯通。

### 只读实证（本次调查，全部可复现）

**科目映射真源** = `report_config`（四准则一致）+ `account_chart`（`source='standard'`）：

| 循环 | 科目（account_chart） | listed 行 | soe 行 | report_config formula | render 硬编码 | 判定 |
|---|---|---|---|---|---|---|
| I1 无形资产 | `1701` 无形资产 / `1702` 累计摊销 / `1703` 无形资产减值准备 | BS-033 | BS-045 | `TB('1701','期末余额')-TB('1702','期末余额')`（**未减 1703**） | `1701`/`1702`/`1703` | 码对，但**父子双计** |
| I2 开发支出 | **`1704`** | BS-035 | BS-046 | **`TB('1703','期末余额')` — 错，1703 是无形资产减值准备** | **`1717`（account_chart 无此码）** | 取数**恒空** |
| I3 商誉 | `1711`（**无 `1712` 商誉减值准备**） | BS-037 | BS-047 | `TB('1711','期末余额')`；`IMP-017 十六、商誉减值准备` formula=None | `1711` | 码对，父子双计 |
| I4 长期待摊费用 | `1801` | BS-038 | BS-048 | `TB('1801','期末余额')` | `1801` | 码对，父子双计 |
| I5 其他非流动资产 | **无标准科目** | BS-040 | BS-050 | **None** | **`1911`（不存在）** | 取数**恒空** |
| I6 研发费用 | `6604`（**全库 `tb_balance` 0 命中**，实际挂在 `6602.11 管理费用_研发费用`） | IS-006 | IS-024 | `TB('6604','本期发生额')` | **`6602`（管理费用）** | **数字完全错** |

- **父子双计实证**：`tb_balance` 里 `1701` 与 `1701.01~.06` 并存，且 `1701` 期末
  197,647,740.84 == 子科目之和（`.01` 141,838,373.77 + `.02` 55,800,568.01 + `.05` 8,799.06）。
  现有 render 对每个 `startswith('1701')` 的行累加 → **恰好 2 倍虚增**。I3/I4 同款。
- **I6 取错科目族的量级**：`6602` 管理费用全库借方 624,269,327.68，`6604` 研发费用 0 行 →
  当前显示的「研发费用」实际是管理费用全额。
- **客户子科目天然对应披露维度**（同 F1 `1123`→五性质桶 / G7 `1511`→变动列范式）：
  `1701.01~.06` = 土地使用权 / 软件 / 专利权 / 非专利技术 / 商标权 / 特许经营权；
  `1702.*` / `1703.*` 同构 → I1 披露表「三层 × 类别」全部可预填。
  `1801.02~.99` = 大修理支出 / 装修费 / 货柜货架 / GSP认证费 / 一年以上租赁费 / 其他 → I4 项目行。
  `5301.01/.02` = 研发支出_费用化 / 资本化 → I2 上市「费用化金额 / 资本化金额」两列口径。
- **灰度 `HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 默认 `False`** → I 类四表取数增强目前整体是暗的。

**公式预设**（`backend/data/prefill_formula_mapping.json`，I 类 18 块）审定表块**整体错位**：
I2 块 `wp_name='商誉审定表'` codes `['1711']`；I3 块 `wp_name='长期待摊费用审定表'` codes
`['1801']`；I4 块 `wp_name='开发支出审定表'` codes `['1703']`；I5 块 codes `['1811']`（递延
所得税资产）；I6 块 codes `['6602']`（管理费用）；I1 块缺 `1703`。明细块 I2 用 `['1801','6602']`、
I4 用 `['1801','1811']`、I2 资本化判断块用 `['1801']`、I3 明细块 4 条引用不存在的 `1712`。
另 `PREV('I1','审定表I1-1',…)` 引用不存在的 sheet（源模板是 `审定表I1`）、`无形资产分析程序`
块引用源 xlsx 不存在的 sheet 且用病态区间 `TB_SUM('1701~1702','期末余额')`。

**披露结构（源 xlsx 逐格实证，唯一裁决者）vs 附注模板现状**：

| 作用域 | 源模板 | note_template | 缺口 |
|---|---|---|---|
| I1 上市 五、26 | 列转置：`项目` + **11 个动态类别列**（`底稿目录!A9:A19`）+ `合计`；行 38（四层）；另 ⑥单项无形资产 3 列表 + （2）未办妥产权证书的土地使用权情况 3 列表；说明 ①~⑥ | 4 表；主表仅 6 列（写死 4 类）；⑥表名 = 整段财会〔2018〕30号文字；（2）表名 = `项  目` | 列结构错 + 丢动态性 + 2 处表名泄漏 |
| I1 国企 八、27 | 5 列 flat；行 **52**（四层 × 13 = 合计 + 11 类别 + `……`）；说明 ①~⑦ | 主表 48 行 | 缺 4 行 |
| I2 上市 五、27 | **5 张表**：①研发支出按费用性质（两级 5 列）②开发支出（两级 7 列）③`续：`资本化时点（4 列）④（1）重要的资本化研发项目（6 列）⑤（2）开发支出减值准备（5 列） | **1 张表、4 列、且缺标签列** | **缺 4 张表 + 主表压扁 + 缺标签列** |
| I2 国企 八、28 | 开发支出（**两级 8 列**：本期增加{内部开发支出,其他} / 本期减少{确认为无形资产,转入当期损益,其他}） | 1 表 5 列 | 压扁丢 3 子列 |
| I3 上市 五、28 | ①商誉账面原值（**两级 8 列**）②商誉减值准备（**两级 7 列**）+ 多段文本 | 4 表；①②各 5 列压扁；③④表名是段落泄漏且源 xlsx 无对应表 | 压扁 + 2 表存疑 |
| I3 国企 八、29 | ①商誉**账面价值**（5 列）②商誉减值准备（5 列） | ①名写「账面原值」 | 表名漂移 |
| I4 上市 五、29 | **两级 6 列**：项目 / 期初数 / 本期增加 / 本期减少{本期摊销,其他减少} / 期末数 | 5 列压扁 + 列名漂移（期初数→期初余额） | 压扁 + 列名 |
| I4 国企 八、30 | 7 列 flat（含「其他减少的原因」） | 7 列一致 | 仅缺 columns/guidance |
| I5 上市 五、31 | **两级 7 列**：项目 / 期末数{账面余额,减值准备,账面价值} / 上年年末数{账面余额,减值准备,账面价值} | 3 列 | 严重压扁（丢 4 列） |
| I5 国企 八、32 | 3 列：项目 / 期末余额 / **年初余额** | 第 3 列写「期初余额」 | 列名漂移 |
| I6 两版 五、66 / 八、67 | 3 列 flat：项目 / 本期发生额 / 上期发生额 | 列一致 | 国企表名缺「（按费用性质列示）」 |

- **全 20 张表 `columns=0` 且 `guidance=0` 字**；前端 6 个 `iXNoteSectionMap.ts` /
  `iXDisclosureSyncPayload.ts` 的 `flat:` / `group:` 表态**均为 0 次** → seed 与推送两条路径都会
  被 `_infer_groups_from_headers` 反猜出凭空父表头。
- **`I2_DISCLOSURE_SHEET_NAME` 漂移**：常量写 `附注披露信息（上市公司）`/`（国有企业）`，源 xlsx
  实为 `附注披露（上市公司）`/`（国有企业）`（无「信息」二字）。I1 才带「信息」。
- **I1/I2/I3 六个披露 Tab 自调度**：`autoSync.scheduleAutoSync(syncToNotes)` 写在 `syncToNotes`
  函数体内 → 800ms 周期重复 POST，且骗过 `disclosureAutoSyncCoverage` 覆盖率守卫（平台既有
  16 处已修，这是遗漏的第 17~22 处）。
- **12 个披露 Tab 共 62 处 `el-input-number`、0 处 `WpAmountInput`** → 千分符从未生效。
- **账龄枚举不适用 I 类**：六个循环源模板披露 sheet 无任何账龄表。可类比的分段维度是 I1 ⑥表
  「剩余摊销期限」与 I4「摊销年限」，但源模板未要求分段披露，故不强行套用（见 R11）。

## Glossary

| 术语 | 含义 |
|---|---|
| 四表库 | `tb_balance`（余额表，客户原始码）/ `trial_balance`（试算表，标准码）/ `tb_ledger`（序时账）/ `tb_aux_balance`（辅助余额） |
| 报表行科目解析 | `four_table.report_line_accounts.resolve_report_line_accounts`：`report_config.formula` → 标准码 → `account_mapping` 反解 → 客户原始码前缀 |
| 叶子聚合 | `four_table.leaf_aggregation.select_leaves` / `aggregate_leaves`：只累加无子科目的叶子行，保证「叶子之和 == 父额」 |
| `tb_source_codes` | render 下发的取数溯源结构（报表行 / 公式 / 标准码 / 原始码 / 解析来源） |
| 类别配置 | I1 源模板 `底稿目录!A9:A20` 的「无形资产类别设置」，项目级可改，驱动披露表的动态列（上市）与动态行（国企） |
| `flat` / `group` | `ColumnDef` 的列元数据：`flat` 显式单级（禁前缀推断），`group` 声明两级表头的父表头 |
| 自调度 | 反模式：`scheduleAutoSync(fn)` 写在 `fn` 自己的函数体内 → 周期重复 POST 且骗过覆盖率守卫 |

## Requirements

### Requirement 1: 科目映射走报表行真源，禁硬编码前缀

**User Story:** 作为审计助理，我希望四表入库后 I 类底稿取到的是本循环真实科目的金额，而不是别的
科目族或双计后的两倍值。

#### Acceptance Criteria

1. WHEN I1~I6 的 render 需要定位科目 THEN 系统 SHALL 通过
   `four_table.report_line_accounts.resolve_report_line_accounts` 按报表行解析，而不是模块级
   硬编码前缀常量。
2. WHEN 解析 I2 开发支出 THEN 系统 SHALL 使用 `1704`（`account_chart` 实证）作为兜底码，且
   SHALL NOT 使用 `1717` 或 `1703`。
3. WHEN 解析 I6 研发费用 THEN 系统 SHALL 使用 `6604` 作为兜底码，且 SHALL NOT 使用 `6602`。
4. WHEN 解析 I5 其他非流动资产（`report_config` formula 为 None 且无标准科目）THEN 系统 SHALL
   返回空科目集并在 `tb_source_codes` 标注 `resolved_from='fallback'` 与空 `gross`，
   SHALL NOT 臆造科目码，且 SHALL NOT 因此阻断 render。
5. WHEN `report_config` 的公式与 `account_chart` 语义冲突（实证 BS-035/BS-046 开发支出引用
   `1703`）THEN 系统 SHALL 以 `account_chart` 为准取兜底码，并在 render 输出中标注该冲突供
   平台级 data-hygiene 复核，SHALL NOT 静默改写 `report_config`。
6. WHEN 聚合 `tb_balance` 金额 THEN 系统 SHALL 只累加**叶子**科目（无 `code + '.'` 子行），使
   「叶子之和 == 父科目行金额」恒成立。

### Requirement 2: 备抵与损益口径

**User Story:** 作为现场经理，我希望减值准备、累计摊销这类备抵科目的增减方向和符号是对的，
损益类科目不会因年末结转而恒为 0。

#### Acceptance Criteria

1. WHEN 聚合备抵科目（`1702` 累计摊销 / `1703` 无形资产减值准备）的增减 THEN 系统 SHALL 以
   `credit_amount` 为增加（计提）、`debit_amount` 为减少（转回/核销）。
2. WHEN 备抵科目余额以负数存储 THEN 系统 SHALL 对输出到审定表/披露表的备抵金额取绝对值，
   使其与源模板「减：累计摊销 / 减值准备」的正数口径一致。
3. WHEN 取 I6 研发费用（损益类）金额 THEN 系统 SHALL 优先取 `trial_balance` 的本期发生额口径，
   SHALL NOT 用 `tb_balance` 的 `debit_amount - credit_amount`（含结转损益分录时恒为 0）。
4. WHEN `IMP-016 十五、无形资产减值准备` / `IMP-017 十六、商誉减值准备` 存在但 formula 为 None
   THEN 系统 SHALL 通过 `ReportLineAccountSpec.provision_row_code` 尝试解析，解析落空时回退
   兜底码（I1 → `1703`；I3 → 空集，因 `account_chart` 无商誉减值准备科目）。

### Requirement 3: 取数溯源可审计

**User Story:** 作为质量控制复核合伙人，我需要看到每个金额来自哪个报表行、哪个标准科目、哪些
客户原始子科目，以便追溯。

#### Acceptance Criteria

1. WHEN I1~I6 的 render 完成 THEN 系统 SHALL 在返回载荷中输出 `tb_source_codes`，含
   `row_code` / `formula` / `gross_standard` / `gross` / `provision_standard` / `provision` /
   `resolved_from` / `provision_exact`。
2. WHEN 前端渲染 I 类审定表 THEN 系统 SHALL 有可见的取数溯源面板消费 `tb_source_codes`，
   SHALL NOT 让它成为无消费方的 dead output。
3. WHEN 叶子聚合结果与父科目行金额不等 THEN 系统 SHALL 在 `tb_source_codes` 内输出
   `parent_check` 差异，供溯源面板提示。

### Requirement 4: 审定表未审数按子科目预填

**User Story:** 作为审计助理，我希望四表入库后点一下就能把未审数按类别/项目带进审定表，不用手抄。

#### Acceptance Criteria

1. WHEN I1 审定表需要未审数 THEN 系统 SHALL 按 `1701`/`1702`/`1703` 的叶子子科目**名称**归入
   I1 类别（土地使用权/住房使用权/专利权/非专利技术/商标权/著作权/特许经营权/软件/矿产权/
   数据资源/其他），SHALL NOT 按子科目编码写死映射。
2. WHEN 子科目名未命中任何类别 THEN 系统 SHALL 归入「其他」并在溯源面板列出该子科目，
   SHALL NOT 静默丢弃。
3. WHEN I4 审定表需要未审数 THEN 系统 SHALL 按 `1801` 的叶子子科目名生成项目行。
4. WHEN 底稿已有持久化录入 THEN 「从四表库带入未审数」SHALL 弹确认后才覆盖，且 SHALL NOT
   覆盖手工录入的非四表列。
5. WHEN 四表无该科目数据 THEN 系统 SHALL 不产生预填行（宁缺勿造）。

### Requirement 5: 公式预设与本循环科目一致

**User Story:** 作为现场经理，我在公式管理页看到的 I 类预设应当是本循环的科目与本循环真实存在的
sheet，而不是别的循环的。

#### Acceptance Criteria

1. WHEN 加载 `workpaper:I1`~`workpaper:I6` 的公式预设 THEN 每个块的 `account_codes` SHALL 只
   含本循环报表行引用的科目（或 `account_chart` 实证的正确兜底码）。
2. WHEN 预设引用 sheet 名 THEN 该 sheet SHALL 存在于对应源模板 xlsx 的 `sheetnames` 中。
3. WHEN 预设引用科目码 THEN 该码 SHALL 存在于 `account_chart` 标准科目表（禁 `1712`/`1717`/
   `1911`）。
4. WHEN 审定表块需要联动明细表 THEN SHALL 用 `WP()` 引用本循环明细表；明细表块 SHALL NOT 反向
   引用审定表（防成环）。
5. WHEN 预设块声明 `wp_name` THEN 该名称 SHALL 与本循环科目语义一致（禁「I2 块叫商誉审定表」）。

### Requirement 6: 附注模板结构对齐源模板

**User Story:** 作为业务合伙人，附注里 I 类各表的列头和行必须与致同源模板一致，否则交付物不合格。

#### Acceptance Criteria

1. WHEN 修订 I 类 12 个附注章节 THEN SHALL 通过幂等脚本完成（带 `--dry-run` / `--check`），
   SHALL NOT 直接手改 `note_template_*.json`。
2. WHEN 源模板表头是两级（I2 上市①②/I2 国企/I3 上市①②/I4 上市/I5 上市）THEN 附注模板
   `columns` SHALL 用 `group` 表达父表头 + 叶子 `label`，SHALL NOT 压扁成带前缀的单级列。
3. WHEN 源模板表头是单级 THEN `columns` SHALL 标 `flat: true`，以禁用
   `_infer_groups_from_headers` 前缀推断。
4. WHEN 表名是表头首格泄漏或段落文本泄漏（I1 上市 `项  目` 与财会30号整段、I3 上市 2 处、
   I5 两版 1 处）THEN SHALL 正名为源模板的小节标题，并把原文字移入 `guidance` 或
   `text_sections`。
5. WHEN 源模板存在附注模板缺失的表（I2 上市 4 张）THEN SHALL 补入，行集按源模板的动态区语义
   处理（纯动态区只 seed 合计行）。
6. WHEN 表名改动 THEN 前端 `IX_*_SUBTABLE` 常量 SHALL 同步，且旧名 SHALL 进
   `_removed_table_keys`（仅与本次推送键求差集后发送）。
7. WHEN 每张表补完 THEN SHALL 有取自源模板红字 / 15 号文 / 财会文号的 `guidance`（纯文本，
   禁 markdown 粗体）。

### Requirement 7: 披露表结构与动态区

**User Story:** 作为审计助理，披露表要能按项目实际情况增删类别/项目行，不能写死。

#### Acceptance Criteria

1. WHEN I1 上市披露表渲染类别列 THEN 列 SHALL 由项目级「无形资产类别设置」驱动（源模板
   `底稿目录!A9:A20` 的 11 类 + `……` 动态区），列 key SHALL 用稳定 key（`{slot}_{seq}`）
   而非 label（默认叶子名可能重复）。
2. WHEN I1 国企披露表渲染类别行 THEN 行 SHALL 由同一份类别配置驱动，四层（原值/累计摊销/
   减值准备/账面价值）SHALL 复用同一类别序列。
3. WHEN I2/I3/I4/I5 披露表渲染动态项目行 THEN SHALL 支持增删改名，新增需命名的 SHALL 先
   `ElMessageBox.prompt` 输入名称。
4. WHEN 动态区骨架行数 THEN SHALL 取 `max(seed 行数, 1)`，SHALL NOT 预置空占位行（会被推成
   占位披露行）。
5. WHEN 四表重新入库出现新子科目 THEN 披露表 SHALL 能按科目码优先匹配已有行（改名后不重复
   插行），并对已有行金额变化弹确认。
6. WHEN 源模板小节标注「根据实际情况列示；不存在的项目请删除」（I5 上市）THEN 该提示 SHALL
   进 `guidance` 而非表名。

### Requirement 8: 推送到附注全链贯通

**User Story:** 作为审计助理，我在披露表录完数据点「同步到附注」（或自动同步）后，附注模块对应
章节应当有完整的表格与文本。

#### Acceptance Criteria

1. WHEN 披露表数据变更 THEN 系统 SHALL 通过 watch 实际数据触发 `scheduleAutoSync`，
   SHALL NOT 在同步函数体内调度自己。
2. WHEN 推送载荷声明 `columns` THEN 每列 SHALL 显式表态 `flat` 或 `group`，且与附注模板
   `columns` 逐字一致。
3. WHEN 推送 `_note_texts` THEN 每条 SHALL 带中文 `title`，空文本 SHALL 过滤，且 SHALL 放在
   `sub_table_data` 内（顶层会被 pydantic 静默丢弃）。
4. WHEN 合计/小计行存在 THEN 载荷 SHALL 包含该行并标 `is_total`，字面 SHALL 按本章节附注模板
   实证取值（不套用全局常量）。
5. WHEN 推送目标章节 THEN `sheet_name` SHALL 与源 xlsx tab 名逐字一致（I2 两版去掉「信息」）。
6. WHEN 项目主体类型与披露变体不匹配 THEN 系统 SHALL 依赖既有服务端 `detect_standard_conflict`
   守卫返回 409，前端 SHALL NOT 写入错误章节。

### Requirement 9: 金额控件与 UI 铁律

**User Story:** 作为审计助理，我在 I 类披露表里输入金额时希望看到千分符与两位小数，和平台其它
循环一致。

#### Acceptance Criteria

1. WHEN 披露表/审定表渲染可编辑金额 THEN SHALL 用 `WpAmountInput`，I 类 12 个披露 Tab 的
   `el-input-number` 残留数 SHALL 为 0。
2. WHEN 渲染只读金额 THEN SHALL 走 `displayPrefs.fmtAmount()`（setup 顶层 inject 取得）。
3. WHEN 比例 / 摊销年限 / 剩余期限 / 笔数等非金额字段 THEN SHALL NOT 套用 `WpAmountInput`。

### Requirement 10: 守卫与零回归

**User Story:** 作为 EQCR 技术复核人，我需要这次改造有自动化守卫钉住结论，且不破坏其它循环。

#### Acceptance Criteria

1. WHEN 附注模板结构修订完成 THEN SHALL 有后端守卫用 openpyxl **直读源 xlsx** 与模板 `headers`、
   前端同步 `columns` 做三向比对，并含反向自检。
2. WHEN 前端映射改动 THEN SHALL 接入共享契约 helper（P1~P6），且 `columnsPending` 逃逸阀
   SHALL 为空。
3. WHEN 引入 `four_table` 共享件的新能力 THEN 既有消费者（D1/K1/K2/F1/G7 等）SHALL 逐字节等价。
4. WHEN 灰度开关 `HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 为 False THEN render 输出
   SHALL 与改造前逐字节等价（characterization 基线）。
5. WHEN CI 运行 THEN SHALL 新增 I 类结构守卫 job，并保持既有 job 全绿。

### Requirement 11: 分段枚举的适用性裁决

**User Story:** 作为现场经理，我想知道账龄枚举模块在 I 类是否适用，避免无意义的套用。

#### Acceptance Criteria

1. WHEN 评估账龄枚举模块在 I 类的适用性 THEN 系统 SHALL 以源模板披露 sheet 为依据，记录
   「I1~I6 披露表无账龄维度」的实证结论。
2. IF 后续要为 I1 ⑥表「剩余摊销期限」或 I4「摊销年限」引入分段枚举 THEN SHALL 复用既有段位
   枚举机制（3 年段 / 5 年段 / 自定义）的数据结构，SHALL NOT 新造一套。
3. WHEN 源模板未要求分段披露 THEN SHALL NOT 在附注表中强行插入分段行。
