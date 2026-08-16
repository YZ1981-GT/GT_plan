# Requirements Document

## Introduction

L 循环（债务循环，L0~L8）的「四表入库 → 底稿取数 → 披露表 → 附注模块」全链收口。

本 spec 的立项依据是 2026-08-09 的只读实证调查（结论已写入 `.kiro/steering/memory.md`）。调查结论分两层：

**取数链路本身已完整且正确**。共享件 `l_cycle_extraction/account_scope.py`（`LCycleSpec` 形态，生产真源）+ `l_cycle_extraction/render_support.build_l_tb_payload` 已把 L1~L8 八个 render 串起来，统一下发 `trial_balance` / `tb_source_codes` / `adjudication_prefill` / `l_bucket_defs` 四个键，含叶子聚合、父额勾稽、按科目名分类桶、「一年内到期」拆分；row_code 与兜底码已逐条与 `report_config` 对账。**本 spec 不重建取数链路**。

**缺陷集中在三处**：

1. **公式管理的 Tier A 预设整块错位** —— `prefill_formula_mapping.json` 里 5 个审定表块的 cells 公式实参偏移一个循环（L2 取长期借款 / L4 取租赁负债 / L5 取应付债券 / L6 取长期应付款 / L7 取预计负债），另 2 个明细表块整块贴错。其中四处是**活的错数**。既有守卫 `test_l_cycle_formula_presets.py` 只校验 `wp_name` 与 `account_codes`（这两项已被修对），cells 公式落在守卫盲区。

2. **L2 与 L4 的披露推送链路是死的** —— 四个披露 Tab 的 `useDisclosureAutoSync` / `syncToDisclosureNotes` / `buildXSyncPayload` 计数全为 0，而 `l4NoteSectionMap.ts` 的五张子表声明与附注 `五、46`（5 表）/`八、50`（2 表）都已备好 = 上游备齐、整条链仍是死的。

3. **附注列结构与源模板有局部不一致** —— soe `八、45`/`八、46` 列 key 是中文字面量且 `flat` 标在每一列上、`八、57` 列序与源模板相反、L4「优先股永续债变动情况」源模板是两级表头而模板压成单级、`五、52`/`八、57` 零 text_sections。

用户已拍板三个口径（2026-08-09）：**L2 接 K3 章节的「应付利息」子表**（实证该子表独立存在，走既有表级浅合并，不需行级合并）· **L7 维持宁缺勿造**但溯源面板显式显示「本项目无此科目」而非 0 · **L4 先接主表/增减变动/续表三张 + 可转债文字**，其他金融工具两张按条件表处理。

### 三件套审查轮补充裁决（2026-08-09，用户拍板「按建议执行」）

首版三件套交付后做了一轮实证核对，查出三处**照它施工会做错**的地方，已按用户裁决改写本文档：

**裁决 A（对应 Requirement 4 重写）：L2 与 K3 的「应付利息」子表收敛到 L2，K3 侧改只读。** 实证 `disclosureAutoSyncCoverage.spec.ts` 已把 L2 两个 Tab 登记为**有意豁免**，理由是「`buildK3SyncPayload` 已实装推这两张表 → L2 再推会同章节同表名互相覆盖」，且该理由成立（`buildK3SyncPayload` 确实推 `T.interest` 与 `T.interestOverdue`）。真实矛盾不是「谁该推」而是**两个数据源竞争同一张附注子表**：K3 侧数据来自披露 Tab **手工录入**（`Array.from({length:3})` 三个空行），L2 侧来自 **L2-2 明细自动 SUMIF 聚合**。源模板铁证在 L2 —— `L2!附注披露（上市公司）信息!B8 = SUMIF('明细表L2-2'!A:A, …, '明细表L2-2'!U:U)`，这张表本就该由 L2-2 明细驱动，K3 那份手工录入是重复录入。故收敛到 L2；K3 侧两张表改**只读展示 + 引导跳 L2**，其 `buildK3SyncPayload` 停止推送这两个键并进 `_removed_table_keys` 的反面（不删、只不推，见 AC 4.10~4.14）。

**裁决 B（对应 Requirement 5 与新增 Requirement 12）：先校正 `l4NoteSectionMap` 既有常量，再接推送。** 实证四处子表名与附注模板不一致（`movement` 少「的…（不包括…）」整段 · `otherFinInstrument` 缺 `（3）` 前缀 · `overdue: '已到期未偿付的应付债券'` 在模板中**不存在** · 缺 `应付债券（续）` 与 `期末发行在外的优先股、永续债等其他金融工具变动情况` 两张），且 `L4_WITHIN1Y_NOTE_SECTION` **只有 `soe` 一个键**。首版 AC 5.5「必须使用既有常量」与「必须与模板逐字一致」互相矛盾，照做会一次性产出 4 张孤儿子表。

**裁决 C（对应 Requirement 6.3）：`八、57` 列序改为对齐源模板**，不保留「登记偏离」这条逃逸阀。

### 术语与既有事实（防止返工）

- **`L_CYCLE_SPECS` 有两个同名导出**：`l_cycle_extraction/account_scope.py`（生产消费）与 `four_table/l_cycle_specs.py`（仅测试与 L0 消费）。本 spec 一律改前者；后者的 L7 `row_code` 分歧（`BS-068` vs `BS-071/BS-097`）在 Requirement 9 处置。
- **L0 不在本 spec 范围**：函证循环无披露 sheet，已由归档 spec `l0-confirmation-source-alignment` 收口；其「样本选择 6 项在 `L0SummaryLowerZone.vue` 内、共享组件里 `v-if="!isL0"` 有意关掉」是既有裁决，本 spec 不得触碰。
- **L6 无独立附注章节**：专项应付款并入 L5 的 `五、48`/`八、53`，由 `l5NoteSectionMap.ts` 统一承载（`L6_LISTED_SUBTABLE` / `L6_SOE_SUBTABLE`），本 spec 沿用。
- **预计负债（K5）/ 递延收益（K7）/ 租赁负债（H9）不属 L 循环** —— 它们正是错位公式误指的科目，本 spec 只修 L 侧、不动 K/H。

## Glossary

| 术语 | 含义 |
|------|------|
| L 循环 | 债务循环，L0 函证 + L1 短期借款 / L2 应付利息 / L3 长期借款 / L4 应付债券 / L5 长期应付款 / L6 专项应付款 / L7 其他非流动负债 / L8 财务费用 |
| Tier A 公式 | `prefill_formula_mapping.json` 中的公式预设，经 `convert_prefill_presets` 进入公式管理页并在 render 期求值 seed 到锚点 |
| cells 公式实参 | Tier A 预设里 `formula` 字段内 `TB('xxxx',...)` / `ADJ('xxxx',...)` 的科目码字符串 |
| 生产真源 | `l_cycle_extraction/account_scope.py` 的 `L_CYCLE_SPECS`（`LCycleSpec` 形态），被 render 真实消费 |
| 分桶 | `LBucket` 声明的叶子科目分类，按科目**名称**归类（禁按编码），顺序即优先级 |
| 一年内到期拆分 | L3/L4/L5 需把「一年内到期」部分从非流动部分中拆出，判定按名称前置于业务桶 |
| 宁缺勿造 | 无法干净映射到科目时返回空而非取错科目；L7 属此类 |
| 动态插行区 | 源模板中以 `…` / `……` / `可无限加行` / 空白行区标记的可扩位，附注侧对应 `row_type: expandable` |
| 表级浅合并 | `sync_from_workpaper` 按子表名合并 `sub_table_data`，未推送的子表保留 —— L2 接 K3 的安全前提 |
| dead output | 上游已产出而下游零消费的数据，本 spec 指 L2/L4 的 map 与附注章节已备好但推送链路不存在 |

## Requirements

### Requirement 1: 公式预设错位修正（审定表）

**User Story:** 作为审计助理，我在应付利息审定表上看到的「未审数」必须是应付利息的余额，而不是长期借款的余额。

#### Acceptance Criteria

1.1 WHEN 读取 `prefill_formula_mapping.json` 中 wp_code 为 L1~L8 的审定表块 THEN 每个 cell 的公式实参科目码必须属于该循环自己的科目（`L_CYCLE_SPECS[wp].fallback_codes`，L7 例外见 1.6）

1.2 WHEN 修正 `审定表L2-1` THEN 四个 cells 的公式实参必须由 `2501` 改为 `2231`，且 description 中的「长期借款」必须改为「应付利息」

1.3 WHEN 修正 `审定表L4-1` THEN 公式实参必须由 `2601` 改为 `2502`，description 中的「租赁负债」必须改为「应付债券」

1.4 WHEN 修正 `审定表L5-1` THEN 公式实参必须由 `2502` 改为 `2701`，description 中的「应付债券」必须改为「长期应付款」

1.5 WHEN 修正 `审定表L6-1` THEN 公式实参必须由 `2701` 改为 `2711`，description 中的「长期应付款」必须改为「专项应付款」

1.6 WHEN 处理 `审定表L7-1` THEN 因该循环 `fallback_codes` 为空（宁缺勿造），四个 cells 的 `formula_type` 必须改为 `PLACEHOLDER`，公式改为 `PLACEHOLDER('...')` 形态，description 必须写明「其他非流动负债在 CAS 无专属科目；`2801` 是预计负债、`2901` 是递延所得税负债，均不得采用」

1.7 WHEN 修正完成 THEN `审定表L1-1`/`审定表L3-1`/`审定表L8-1` 三块必须逐字节不变（它们本来就是对的，零回归）

1.8 WHEN 修正 description THEN 不得残留任何指向别的循环科目的中文名（如「租赁负债审定表」「预计负债审定表」）

### Requirement 2: 公式预设错位修正（明细表与分析程序）

**User Story:** 作为审计助理，应付债券明细表与长期应付款明细表应当各自有正确的取数预设，而不是互相占位。

#### Acceptance Criteria

2.1 WHEN 处理 `明细表L5-2` THEN 该块当前内容（`应付债券_面值_期初` 等 5 个 cell_ref + `TB('2502')` + `TB('2502.02')`）必须整块迁移到 wp_code `L4`、sheet `应付债券明细表L4-2`（源 xlsx 真实 tab 名）

2.2 WHEN 处理 `明细表L6-2` THEN 该块当前内容（`成本中心_TOP1` 等 5 个 AUX + `2701`）必须整块迁移到 wp_code `L5`、sheet `明细表L5-2`

2.3 WHEN 迁移完成 THEN L5 与 L6 各自的明细表必须有与本循环科目一致的预设，或显式登记「无预设」及理由

2.4 WHEN 处理 `L1 分析程序L1-3` 块 THEN 该 sheet 在源 xlsx 不存在（真实 tab 为 `调整分录汇总L1-3`），且公式 `TB_SUM('2001~2501','期末余额')` 会把 2201/2202/2203/2211/2221/**2231**/2241 整段负债扫进「债务」合计（其中 `2231` 恰是 L2 自己的科目 ⇒ 该合计里混着应付利息，跨循环双算）THEN 必须删除该块并在幂等脚本内登记删除依据

2.5 WHEN 修正 `PREV()` 实参 THEN 若某块的 sheet 名被改动，同块内 `PREV('LN','<旧 sheet 名>',...)` 的第二实参必须同步改为新 sheet 名（否则 `--check` 假绿）

2.6 WHEN 幂等脚本写盘 THEN 必须做 round-trip 自检（`json.dumps(indent=2)+"\n"` 逐字复现原文才允许写盘），防止重排整个文件与并发会话互相回退

### Requirement 3: 公式预设守卫扩面

**User Story:** 作为平台维护者，我需要一条判据能一次性抓住「cells 公式实参取到别的循环科目」这类错误，而不是每次靠人工比对。

#### Acceptance Criteria

3.1 WHEN 守卫扫描 L 类预设块 THEN 必须对每个 cell 抽取公式实参中的科目码，并断言其属于该循环的合法科目集（`fallback_codes` ∪ 该循环子科目前缀）

3.2 WHEN 某块的 `formula_type` 为 `PLACEHOLDER` THEN 守卫必须放行（不要求它含科目码），但必须要求 description 长度 ≥ 30 字且写明依据

3.3 WHEN 守卫检查 description THEN 同一块内 description 提到的科目中文名必须与 `wp_name` 中的科目名一致

3.4 WHEN 守卫检查 sheet 名 THEN 每个 L 类块的 `sheet` 必须存在于对应 wp_code 的源 xlsx 可见 sheet 名集合中（openpyxl 直读为裁决者）

3.5 WHEN 守卫检查区间函数 THEN `SUM_TB`/`TB_SUM` 的区间上下界必须落在同一循环的科目族内，跨循环区间必须打红

3.6 WHEN 抽取科目码 THEN 必须先识别并整体消费 `SUM_TB('a~b')` 形态（区间端点不是被引用科目），否则会把上界误判为「引用了别的循环科目」

3.7 WHEN 守卫运行 THEN 必须配反向自检：把某块公式改回错位形态时该守卫必须打红（证明判据非空转）

3.8 WHEN 守卫检查 `PREV()` THEN 其第二实参必须是该 wp_code 源 xlsx 的真实 tab 名

### Requirement 4: L2 应付利息接入 K3 章节（含 K3 侧收敛）

**User Story:** 作为审计助理，我在 L2 应付利息披露表填完数据后，点「推送到附注」应当能把数据写进附注的「应付利息」子表；同一份数据我只需要在一个地方填。

**背景（裁决 A）**：该子表当前有两个写者 —— K3 侧手工录入（已实装推送）与 L2 侧 L2-2 明细自动聚合（零链路）。源模板 `L2!附注披露（上市公司）信息!B8` 是 `SUMIF('明细表L2-2'!A:A,…)`，即该表本就由 L2-2 驱动。故本 spec 把写权收敛到 L2，K3 侧改只读展示 + 引导跳转。

#### Acceptance Criteria

4.1 WHEN 建立 `l2NoteSectionMap.ts` THEN 章节号必须取 K3 的 `五、42`（listed）/ `八、42`（soe），子表名必须逐字取自附注模板（listed `应付利息` + `重要的逾期未付利息`；soe `应付利息` + `重要的已逾期未支付的利息情况`）

4.2 WHEN 声明列定义 THEN 必须与附注模板 `columns` 的 key 逐字一致（`label`/`end_amount`/`prior_amount`；逾期表 `label`/`overdue_amount`/`overdue_reason`）

4.3 WHEN 声明行集 THEN listed 侧必须为源模板 7 行（分期付息到期还本的长期借款利息 / 企业债券利息 / 短期借款应付利息 / 划分为金融负债的优先股\永续债利息 / 其中：工具1 / 工具2 / 合计），soe 侧必须为源模板 6 行（前四行相同 + 其他利息 + 合计）

4.4 WHEN 两版行集不同 THEN 不得为「统一」而对齐 —— 两版不对称是源模板事实（listed 有「其中：工具1/工具2」、soe 有「其他利息」）

4.5 WHEN L2 推送 THEN 只能推自己负责的两张子表，`五、42`/`八、42` 内其余子表（其他应付款主表 / 应付股利 / 按款项性质 / 账龄超 1 年）必须原样保留

4.6 WHEN L2 推送 THEN 不得声明 `_removed_table_keys` 指向 K3 负责的子表

4.7 WHEN 披露 Tab 接线 THEN `L2TabDisclosureListed.vue` 与 `L2TabDisclosureSoe.vue` 必须接 `useDisclosureAutoSync`，watch 的必须是**实际数据**（与构建载荷所用字段一致），不得 `scheduleAutoSync(syncToNotes)` 自调度

4.8 WHEN 宿主传参 THEN `GtL2InterestPayable.vue` 必须给两个披露 Tab 传 `:project-id` 与 `:html-data`

4.9 WHEN 平台守卫 `disclosureAutoSyncCoverage.spec.ts` 运行 THEN L2 的两个 Tab 必须从 `MISSING_SYNC_PATH` 移出，且其中「L2 有意豁免」的注释块必须删除（该豁免依据已被本 spec 推翻）

4.10 WHEN 收敛 K3 侧写权 THEN `buildK3SyncPayload` 必须不再把 `interest` 与 `interestOverdue` 两张子表写入 `sub_table_data`，也不得把它们放进 `_removed_table_keys`（写权移交 ≠ 删表）

4.11 WHEN K3 侧改造 THEN 两个 K3 披露 Tab 的「应付利息」与「逾期未付利息」区块必须改为只读展示 + 「前往 L2 编辑」跳转入口，既有录入值不得删除（数据零丢失）

4.12 WHEN K3 主表（`其他应付款` 汇总表）计算「应付利息」汇总行 THEN 其取数口径必须改为读 L2 的持久化数据，不得继续读 K3 自己的 `interest` 录入区块

4.13 WHEN 守卫检查写权唯一性 THEN 必须断言全前端只有一个 payload 构造器会产出 `应付利息` 子表键（`buildL2SyncPayload`），`buildK3SyncPayload` 产出的键集不含该表名；反向自检：给 K3 加回该键必须打红

4.14 WHEN K3 侧存量数据已按 K3 键持久化 THEN 必须提供一次性迁移或读时回退（L2 侧无数据时读 K3 旧键展示），且在守卫中登记该回退的退役条件

### Requirement 5: L4 应付债券接入附注

**User Story:** 作为审计助理，我在 L4 应付债券披露表填完主表与增减变动后，点「推送到附注」应当能落到附注 `五、46`/`八、50`。

#### Acceptance Criteria

5.1 WHEN L4 披露 Tab 建立录入区块 THEN listed 侧必须覆盖三张表：主表（项目/期末余额/上年年末余额）· 增减变动（债券名称/面值/票面利率/发行日期/债券期限/发行金额 + 小计）· 续表（债券名称/期初余额/本期发行/按面值计提利息/溢折价摊销/本期偿还/期末余额/是否违约 + 小计/减：一年内到期的应付债券/合计）

5.2 WHEN L4 披露 Tab 建立录入区块 THEN soe 侧必须覆盖两张表：主表（项目/期末余额/期初余额 + 小计/减：一年内到期的应付债券/合计）· 增减变动（10 列：债券名称/面值/发行日期/债券期限/发行金额/年初应付利息/本期应计利息/本期已付利息/期末应付利息/期末余额）

5.3 WHEN 「划分为金融负债的其他金融工具」与「期末发行在外的优先股、永续债等其他金融工具变动情况」两张表 THEN 必须按条件表处理：有行才推；无行时不推空表**且**该表键进 `_removed_table_keys`（底稿有录入区块的条件表语义）

5.4 WHEN 可转债说明 THEN 必须提供文本录入位置并经 `_note_texts` 推送，且 `_note_texts` 必须带中文 `title`（不得让附注正文渲染成英文键）

5.5 WHEN L4 推送 THEN 必须使用 `l4NoteSectionMap.ts` 的 `L4_LISTED_SUBTABLE` / `L4_SOE_SUBTABLE` 常量，且这两个常量必须**先按附注模板 `tables[].name` 逐字校正**（既有声明与模板不一致，详见 5.11）

5.6 WHEN 一年内到期的应付债券 THEN listed 侧落 `五、43`（已有 `一年内到期的应付债券` + `一年内到期的应付债券（续）` 两张表）、soe 侧落 `八、46`（`（2）一年内到期的应付债券` + `一年内到期的应付债券` 两张表），必须分别发独立 payload（`sync_from_workpaper` 定位键只含 `note_section`）

5.7 WHEN 披露 Tab 接线 THEN 两个 Tab 必须接 `useDisclosureAutoSync` 且 watch 实际数据

5.8 WHEN 宿主传参 THEN `GtL4BondsPayable.vue` 必须给两个披露 Tab 传 `:project-id` 与 `:html-data`

5.9 WHEN 金额录入 THEN 必须用 `WpAmountInput`（不得用 `el-input-number :formatter`，该 prop 在 EP 2.13.6 不存在）；票面利率/债券期限/是否违约等非金额列不得套用

5.10 WHEN 平台守卫运行 THEN L4 两个 Tab 必须从 `MISSING_SYNC_PATH` 移出

5.11 WHEN 校正 `L4_LISTED_SUBTABLE` THEN 必须按附注模板 `五、46` 的真实表名逐字改写（实证 4 处不一致）：`movement` 由 `'应付债券增减变动'` 改为 `'应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）'` · `otherFinInstrument` 由 `'划分为金融负债的其他金融工具'` 改为 `'（3）划分为金融负债的其他金融工具'`（带序号前缀） · 新增 `cont: '应付债券（续）'` · 新增 `instrumentMovement: '期末发行在外的优先股、永续债等其他金融工具变动情况'`

5.12 WHEN 处理 `L4_LISTED_SUBTABLE.overdue`（`'已到期未偿付的应付债券'`）THEN 该表名在两份附注模板中均**不存在**（实证 `五、46` 五张表、`八、50` 两张表都没有它），且源 xlsx 两版披露 sheet 亦无该表 THEN 必须删除该键，不得为它凭空建表

5.13 WHEN 校正 `L4_SOE_SUBTABLE` THEN `movement` 同样由 `'应付债券增减变动'` 改为 `'应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）'`（`八、50` 两版表名与 listed 一致）

5.14 WHEN 处理 `L4_WITHIN1Y_NOTE_SECTION` THEN 该常量实测只有 `soe: '八、46'` 一个键 THEN 必须补 `listed: '五、43'`，否则 5.6 要求的 listed 侧第二个 payload 无落点

5.15 WHEN 校正上述常量 THEN 必须先核实 `sub_table_data` 内是否已有按旧表名持久化的数据；旧表名（`应付债券增减变动` / `划分为金融负债的其他金融工具` / `已到期未偿付的应付债券`）必须登记进 `L4_LEGACY_OBSOLETE_TABLES` 并在首次推送时经 `_removed_table_keys` 清理（与已推送键求差集后再发）

### Requirement 6: 附注列结构对齐源模板

**User Story:** 作为项目合伙人，附注里的表格列结构必须与致同源模板一致，否则交付件不合规。

#### Acceptance Criteria

6.1 WHEN 检查 soe `八、45`（一年内到期的长期借款）与 `八、46`（一年内到期的应付债券）THEN 列 key 必须由中文字面量（`项目`/`期末余额`/`期初余额`）改为平台惯例（`label`/`end_amount`/`prior_amount` 等），且 `flat` 只标在标签列上（不得每列都标）

6.2 WHEN 改写列 key THEN 必须核实 `sub_table_data` 内是否已有按旧 key 持久化的数据；若有则必须保证读写两侧同时切换或经投影器双向兜底，数据零丢失

6.3 WHEN 检查 soe `八、57`（其他非流动负债）THEN 必须**改为与源模板一致的列序**（源 xlsx `L7!附注披露信息(国企)!A6/B6/C6` = 项目 / 年初余额 / 期末余额；模板当前为 项目 / 期末余额 / 期初余额）—— 该处**已裁决为「改对齐」不留「登记偏离」逃逸阀**，两条路并存会让下个会话再判一次

6.3a WHEN 改 `八、57` 列序 THEN 列 key 亦须随语义走（`label` / `begin_amount` / `end_amount`），且必须核实既有 `sub_table_data` 是否按旧序持久化过；`l7NoteSectionMap.ts` 的 soe 列构造器必须同步改，两侧不得分叉

6.3b WHEN 处理 listed `五、52` THEN 其源模板列序为「项目 / 期末数 / 上年年末数」（`L7!附注披露信息（上市公司）!A6/B6/C6`），与 soe **相反是源模板事实**，不得为「统一」而对齐

6.4 WHEN 检查 listed `五、46` 的「期末发行在外的优先股、永续债等其他金融工具变动情况」THEN 源模板 `r063/r064` 是两级表头（发行在外的金融工具 + 期初余额/本期增加/本期减少/期末余额 × 数量/账面价值 = 1 + 8 = 9 列），而模板当前 5 列为 `label`/`begin_count`/`increase_count`/`decrease_count`/`end_count` = **只保留了「数量」、四个「账面价值」列整体丢失** THEN 修法必须是「先补 4 个 `*_value` 列（`begin_value`/`increase_value`/`decrease_value`/`end_value`）再加 `group`」，**不是只加 group**

6.4a WHEN 补 `五、46` t04 的列 THEN 列序必须按源模板交替（数量、账面价值 成对出现），标签列不得标 `flat`（`flat` 标在任一列即让 `_extract_column_groups` 整表返 `[]`，group 被永久打掉）

6.4b WHEN 处理 soe 侧同款表 THEN 源 xlsx `r052/r053` 结构相同但父表头用语为「期初数 / 本期增加 / 本期减少 / 期末数」（listed 是「期初余额…期末余额」）THEN 两版用语差异是源模板事实，不得统一；但 soe `八、50` 当前只有 2 张表、无该子表 ⇒ 本 spec 不为 soe 新建该表（宁缺勿造），仅登记差异

6.5 WHEN 检查 `五、52` 与 `八、57` THEN 两者 `text_sections` 均为 0，而源模板有说明段 THEN 必须补齐（listed 源模板无说明段则如实登记为零，不得自造）

6.6 WHEN 补列元数据 THEN 每张表必须同时有 `columns`（含 label/key/format）与 `guidance`，`guidance` 只许取源模板红字 / 附注模版括注 / 准则条款，不得自造披露内容

6.7 WHEN `guidance` 写入 THEN 必须是纯文本，不得含 markdown 粗体（会与平台级 `fix_note_bold_markers.py` 互相打架）

6.8 WHEN 修订附注模板 THEN 必须做成幂等脚本（`--dry-run` / `--check` / `--apply`），禁止手改 JSON

6.9 WHEN 幂等脚本运行两次 THEN 第二次必须 0 项欠账且两份模板 md5 逐字节不变

### Requirement 7: 动态插行区识别与推送

**User Story:** 作为审计助理，源模板里标着「可无限加行」「…」的位置，我应当能在底稿里增删行，且推送到附注后行数跟着走。

#### Acceptance Criteria

7.1 WHEN 识别源模板动态插行区 THEN 判据必须是源 xlsx 单元格文字（`……` / `…` / `可无限加行` / `可改名` / `预留`），并逐处登记 `source_ref`（sheet 名 + 单元格坐标）

7.2 WHEN L5 上市「按款项性质列示」THEN 源模板 r014（售后租回/分期付款之后）与 r018（未确认融资费用段内）各有一处 `…` THEN 底稿必须支持在这两段内增行

7.2a WHEN 识别 L2 的可扩区 THEN 源 xlsx `附注披露（上市公司）信息` 的 **r012/r013 是固定行**（「其中：工具1」「工具2」，各带 `SUMIF('明细表L2-2'!A:A,…)` 公式）**不是**动态插行区；L2 真实可扩区是 **r018~r033 的逾期未付利息 16 行**（每行 `=IF('明细表L2-2'!V{n}>0, …)` 由明细驱动，行数随明细行数走）THEN 守卫不得把 r012/r013 当可扩位断言

7.3 WHEN L4 上市「划分为金融负债的其他金融工具」THEN 源模板 r050 为「可无限加行」THEN 底稿必须支持增行

7.4 WHEN L4「期末发行在外的优先股、永续债等其他金融工具变动情况」THEN 源模板 r059/r070 为「可无限加行」THEN 底稿必须支持增行

7.5 WHEN L6/L7 的明细行区 THEN 源模板为空白可填区（L6 上市 r009~r018 十行、L7 两版 r007~r011 五行）THEN 底稿必须以动态行承载，不得写死行数

7.6 WHEN 动态行需要命名 THEN 必须先 `ElMessageBox.prompt` 输入名称再创建（平台既有范式）

7.7 WHEN 动态行骨架 THEN 不得预置空占位行（会被推成占位披露行），行数必须为 `max(seed 行数, 1)`

7.8 WHEN 动态行推送 THEN 附注侧对应表的 `row_type` 若已标 `expandable` 则必须保留（`expandable` 行在投影与 Word 导出中视为零可见内容）

7.9 WHEN 推送后删行 THEN 附注侧必须同步减少（整表覆盖语义），不得残留上次推送的过时明细

### Requirement 8: L7 宁缺勿造的呈现

**User Story:** 作为审计助理，其他非流动负债审定表没有取数时，我需要知道是「本项目无此科目」还是「余额为 0」。

#### Acceptance Criteria

8.1 WHEN L7 的 `resolve_l_scope` 返回 `prefill_supported=False` THEN 溯源面板必须显示「本项目无此科目，需手工填列」而不是显示 0

8.2 WHEN 显示该提示 THEN 必须同时展示 `note` 字段的依据说明（`2901` 是递延所得税负债 / `2801` 是预计负债 / 客户科目表无「其他非流动负债」科目）

8.3 WHEN L7 审定表渲染 THEN 「未审数」格必须可手工录入且不被预填覆盖

8.4 WHEN 平台既有共享面板 `WpFourTableSourcePanel` 已支持三态 THEN 必须复用它，不得新建第二套判据

8.5 WHEN 守卫检查 THEN 必须断言 L7 的 `fallback_codes` 为空元组，且反向自检「给它加兜底码会让守卫打红」

### Requirement 9: row_code 双真源收敛

**User Story:** 作为平台维护者，同一个循环的报表行编码不应有两份互相分叉的声明。

#### Acceptance Criteria

9.1 WHEN 比对 `l_cycle_extraction/account_scope.py` 与 `four_table/l_cycle_specs.py` THEN L7 的 row_code 分歧（`BS-071`/`BS-097` vs `BS-068`）必须收敛为一份

9.2 WHEN 收敛 THEN 必须以 `report_config` 实测为裁决依据，并在守卫中冻结该实证（行名 + 公式）

9.3 WHEN 收敛后 THEN 由于 L7 `fallback_codes` 为空且报表公式不采用，取数金额必须逐字节不变（零回归）

9.4 WHEN 保留两个模块 THEN 必须在两侧 docstring 交叉标注「另一份的用途与消费方」，防止下个会话改错那一份

9.5 WHEN `four_table/l_cycle_specs.py` 的 `L4_SPEC`/`L5_SPEC` 被 `l0_book_amounts.py` 消费 THEN 该消费关系必须保持（既有 `is` 同一性断言防双真源）

### Requirement 10: 守卫、CI 与验收

**User Story:** 作为平台维护者，本次修复必须有守卫钉死，且能在 CI 上持续保护。

#### Acceptance Criteria

10.1 WHEN 新增守卫 THEN 必须包含：公式预设科目一致性（Requirement 3）· 附注结构三向比对（源 xlsx ↔ 模板 headers ↔ 同步 columns）· 前端子表契约（`lCycleNoteSubtableContract.spec.ts` 扩面到 L2/L4）· 宿主传参 · 金额控件选型

10.2 WHEN 附注结构守卫运行 THEN 必须以 openpyxl 直读源 xlsx 为裁决者，并配反向自检证明扫描面非空

10.3 WHEN 守卫写完 THEN 必须逐条做变异检验（改一处看是否变红），并按 RED / GREEN / ANCHOR-MISS 三态判定；GREEN 表示守卫有缺陷必须修

10.4 WHEN 变异检验 THEN 变异脚本的备份必须落 `.bak` 且提供 `--restore`，锚点必须行级唯一（命中数 == 1），禁用含 `\n` 的跨行锚点（CRLF 工作树必 MISS）

10.5 WHEN CI 配置 THEN 必须新增 job 覆盖本 spec 的后端与前端守卫，并把幂等脚本的 `--check` 纳入步骤

10.6 WHEN 零回归验证 THEN 必须证明 L1/L3/L8 三个本来正确的循环取数金额逐字节不变，判据为「改动前 vs 改动后」前后对照（禁用 HEAD-swap，因工作树混着并发会话改动）

10.7 WHEN 真实库验收 THEN 必须对有 L 类数据的项目逐个直跑 render，输出 `tb_source_codes.resolved_from` / `parent_check.diff` / 各桶金额，并与独立 SQL 交叉核对

10.8 WHEN 浏览器实测 THEN 必须录入真实数据 → 看目标区域出数 → postgres 查 `checklist_responses` 与 `disclosure_notes` 落库，三者缺一不算实测

10.9 WHEN 实测完成 THEN 必须按实测前快照（含 `md5` 与 `jsonb_typeof`）逐项复原数据，并用独立只读查询核实

10.10 WHEN 收口 THEN 必须清理本 spec 产生的 `_wip_*` / `tmp_*` 临时产物

### Requirement 11: 范围外与不做事项

**User Story:** 作为平台维护者，我需要明确本 spec 不碰哪些东西，避免与并发 spec 互相回退。

#### Acceptance Criteria

11.1 WHEN 涉及 L0 函证循环 THEN 本 spec 不改任何 L0 组件与配置（已由归档 spec 收口）

11.2 WHEN 涉及 K3/K5/K7/H9 的科目与章节 THEN 本 spec 只读不改（预计负债 / 递延收益 / 租赁负债不属 L 循环）

11.3 WHEN 涉及 `report_config` 表数据 THEN 本 spec 不改（其错码由 `report-config-account-code-integrity` spec 负责）

11.4 WHEN 涉及 L4 源模板两组同索引号 sheet（两个 `L4-7`、两个 `L4-8` 且一个尾部带空格）THEN 本 spec 只加守卫防按尾码分发时撞车，不改源模板

11.5 WHEN 涉及 `procedure_table_templates.json` 根级独有的 `L0A` 条目（`get_template` 返 None）THEN 属平台级待办，本 spec 不处置

11.6 WHEN 本 spec 与并发 spec 共享文件（`prefill_formula_mapping.json` / 两份 `note_template_*.json` / `governance-checks.yml`）THEN 一律用幂等脚本 + 只显式暂存自己的路径，禁 `git add -A`

11.7 WHEN 涉及 `k3NoteSectionMap.ts` 与 K3 两个披露 Tab THEN 本 spec **只做「应付利息 / 逾期利息」两张子表的收敛**（Requirement 4.10~4.14），K3 的其余五张子表（其他应付款主表 / 应付股利 / 应付股利逾期 / 按款项性质 / 账龄超 1 年）逐字不改；`K3_INTEREST_ROWS` 常量在收敛后成为死常量，必须删除而非留 DEPRECATED 注释
