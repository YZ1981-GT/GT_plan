# Requirements Document

## Introduction

G 循环（投资与金融工具，G1~G14）的「四表入库 → 底稿刷新取数 → 披露表 → 附注模块」全链核查。

归档 spec `g5/g6/g7-four-table-extraction-and-disclosure-alignment` 已把 G5/G6/G7 三个循环打通，
memory 记载「G 循环四表取数全收口（2026-08-01）」。本次逐层复核发现该结论**不成立**：
收口只覆盖了各循环的 `main` render 策略，而**映射真源本身是错的** —— 四表取数的裁决者
`report_config` 有四行科目码错误，且是「越正确接入共享件、取数越错」的形态。

### 只读实证（DB + 源 xlsx + 源码，2026-08-01）

**A. `report_config` 科目映射真源有 4 行错码（平台级 P0，非 G 循环局部问题）**

`account_chart`（`source='standard'`，6 个项目**口径完全一致、无变体分叉**）与
`trial_balance.account_name`（recalc 落库）双向实证的科目语义：

| 标准码 | 真实科目名 | 归属循环 |
|---|---|---|
| 1504 | 债权投资 | G4 |
| 1505 | **债权投资减值准备** | G4 备抵 |
| 1506 | **其他债权投资** | G6 |
| 1507 | **其他权益工具投资** | G8 |
| 1519 | **其他非流动金融资产** | G9 |
| 6701 | **资产减值损失** | K11 |
| 6702 | **信用减值损失** | G14 |

而 `report_config`（四准则一致）写的是：

| 报表行 | 行名 | 现公式 | 实际取到 | 应为 |
|---|---|---|---|---|
| BS-022 | 其他债权投资 | `TB('1505')` | 债权投资减值准备 | `TB('1506')` |
| BS-025 | 其他权益工具投资 | `TB('1506')` | 其他债权投资 | `TB('1507')` |
| BS-026 | 其他非流动金融资产 | `TB('1507')` | 其他权益工具投资 | `TB('1519')` |
| IS-016 | 信用减值损失 | `TB('6701','本期发生额')` | 资产减值损失 | `TB('6702','本期发生额')` |
| IS-017 | 资产减值损失 | `TB('6702','本期发生额')` | 信用减值损失 | `TB('6701','本期发生额')` |

- BS-022/025/026 是**连续偏移一位**（写公式时假设 1504~1507 连续为「债权投资 / 其他债权投资 /
  其他权益工具投资 / 其他非流动金融资产」，而平台标准科目表在 1504 与 1506 之间插了
  `1505 债权投资减值准备`，且其他非流动金融资产跳到 1519）。
- IS-016 与 IS-017 **整整互换**。铁证：同库 `CFSS-003 加：资产减值损失 = TB('6701','发生额')`
  与 `CFSS-004 信用减值损失 = TB('6702','发生额')` **是对的** → 现金流量表补充资料与利润表
  自相矛盾，只能是利润表两行笔误。
- `1519` 与 `1506` 在整个 `report_config` 里**零引用**（`formula LIKE '%1519%'` 命中 0 条）。

**活体影响（唯一有余额的一组）**：`trial_balance` 实测 6701 合计 3,876,759.84 /
6702 合计 126,151,230.15 → G14 信用减值损失取到 3.87M（虚减 122,274,470.31），
K11 资产减值损失取到 126.15M（虚增同额）。**两个循环的钱互换了**，且利润表本身也错。
15xx 一族当前活体余额均为 0.00（`account_mapping` 无 1504~1507/1519 映射记录）→
G4/G6/G8/G9 目前是「逻辑错但金额看不出」的潜伏态。

**B. 共享件的「report_config 优先」放大了 A 的破坏力**

`four_table/report_line_accounts.resolve_report_line_accounts` 的优先级是
「报表公式解析成功 → 用解析结果；失败 → 用调用方 `fallback_gross`」。
`_g14_credit_impairment_loss.py` 声明 `ReportLineAccountSpec(row_code="IS-016", fallback_gross=("6702",))`
—— 兜底码是**对的**，但因 IS-016 解析成功返回 `6701`，兜底**永远用不上**。
即：G14 render 看似「已按科目表纠正为 6702」，运行态实际取 6701。
G6（`BS-022`/fallback `1505`）、G8（`BS-025`/fallback `1506`）、G9（`BS-026`/fallback `1507`）
的兜底码本身也抄了 report_config 的错值 → 两条路都错。

**C. G 循环 render 只有 `main` 策略接了共享件，子策略仍硬编码旧科目**

| 文件 | 硬编码码 | 真值 | 判定 |
|---|---|---|---|
| `_g4_bond_investment_ecl.py` | `1501` | 1504 | `1501 持有至到期投资`（旧准则），取数恒空 |
| `_g4_bond_investment_sppi.py` | `1501` | 1504 | 同上 |
| `_g6_other_bond_investment_ecl.py` | `1503` | 1506 | `1503 可供出售金融资产`（旧准则），取数恒空 |
| `_g6_other_bond_investment_main_service.py` | `1503` | 1506 | 同上 |
| `_g7_long_term_equity_main_service.py` | `1511` | 1511 | 码对但仍是字面量（违反单一真源铁律） |

且 `_g6_other_bond_investment_main.py` **无 `adjudication_prefill`**（G 循环唯一缺失者）。

**D. `tb_source_codes` / `adjudication_prefill` 在 11 个循环是 dead output**

后端 13 个 G render 已全部输出 `tb_source_codes` + 12 个输出 `adjudication_prefill`，
但前端消费点实测：

| 循环 | AccountScope 单一真源 | 四表溯源面板 | 「从四表库带入未审数」 |
|---|---|---|---|
| G5 / G6 / G7 | ✅ | ✅ | ✅ |
| G1 | ✅（`g1AccountScope.ts`） | ❌ | ❌ |
| G2 G3 G4 G8 G9 G10 G11 G12 G13 G14 | ❌ | ❌ | ❌ |

即「四表入库后能刷新取数的底稿就都有数据」在 11 个循环**不成立** —— 后端算了，前端不读。

**E. 公式预设（`prefill_formula_mapping.json`）5 类缺陷**

1. **G4 审定表 `TB_SUM('1504~1507','期末余额')`**（accounts 声明 `['1504','1505','1506','1507']`）
   → 把 G4 债权投资 + 其备抵 + G6 其他债权投资 + G8 其他权益工具投资**四个科目全加进 G4**。
2. **损益类四循环全用「期初余额 / 期末余额」而非「本期发生额」**（G11 `TB('6111','期初余额')`、
   G12 `TB('6115',…)`、G13 `TB('6101','期初余额')`、G14 `TB('6701',…)`）。平台权威口径
   见 `report_config` 的 `IS-011/IS-015` 均为 `本期发生额`；且损益类含年末结转分录时
   借贷两侧恒相等（memory 铁律）。
3. **G12 预设科目 `6115`**（= 资产处置损益，H10 的科目）而 render 用 `6103`（净敞口套期收益）
   → 预设与 render 分叉，预设侧取错科目族。
4. **G14 预设科目 `6701`**（资产减值损失）而真值 `6702`；**G4-2 残留 `TB('1501.03')`**
   （不存在的旧科目）+ 描述文字仍写「1501 债权投资」；**G8-2 残留 `TB('1525')`/`TB('1526')`/
   `TB('1527')`**（= 投资性房地产累计折旧 / 累计摊销 / 减值准备，H3 的科目族）+ 描述写「1521」。
5. **G1 有一个幽灵 sheet 块 `分析程序G1-3`** —— 源 xlsx 的 G1-3 实为 `调整分录汇总G1-3`，
   该 sheet 名不存在 → 整块预设永不命中。
6. **9 个循环缺披露 sheet 预设块**（仅 G1/G5 有），**11 个循环缺明细表块**。

**F. 附注模板结构欠账集中在 G10/G11/G13/G14（8 章节 12 表）**

既有幂等脚本 `fix_note_g_cycle_structure.py --check` 覆盖 G4/G5/G6/G8/G9/G12 全绿，
G7 另有 4 个专属脚本。**未覆盖：G1/G2/G3（结构本已干净）+ G10/G11/G13/G14（全欠）**：

| 章节 | 欠账 |
|---|---|
| 五、34 交易性金融负债 | 3 表 `columns=0` + 无 guidance；T0 行集被压成 6 行（源 8 行，丢「衍生金融负债」「其他」，「其中：发行的交易性债券」被压成裸「其中：」）；T1/T2 表名是**段落文本泄漏**；T2 表名与表头**硬编码年份 `2025年`** |
| 五、35 衍生金融负债 | 1 表 `columns=0` + 无 guidance + 只剩合计行（源 5 空行 + 合计） |
| 八、34 / 八、35 | 同上（3 表 `columns=0`，1 张段落泄漏名） |
| 五、69 投资收益 | 2 表 `columns=0`；T1 表名 `项  目` 泄漏（应为「处置交易性金融资产取得的投资收益明细」） |
| 八、70 投资收益 | 1 表 `columns=0`；章节标题带 `【下表中不适用的项目，删除】`（应移入 guidance） |
| 三、公允价值变动收益 | 2 表 `columns=0`；T1 表名 `项  目` 泄漏且**整张表是 G11 的孤儿**（行集与 五、69 T1 逐字相同）；**23 段 `text_sections` 全属附注「九、公允价值」章**（三层次划分 / 估值技术 / 层级调节表 / 不以公允价值计量但披露其公允价值）= md 重建污染 |
| 八、72 公允价值变动收益 | 1 表 `columns=0` + 无 guidance（行集与源模板一致） |
| 三、信用减值损失 | 1 表 `columns=0`；表名 `项  目` 泄漏；行集比源模板多「合同资产减值损失」 |
| 八、73 信用减值损失 | 1 表 `columns=0` + 无 guidance（行集一致） |

**G. G2 / G3 / K1 三循环共用 五、8 / 八、9（其他应收款）章节**

新准则把应收利息、应收股利并入其他应收款 → 三个循环推同一章节。实证：

- `sub_table_data` 是**按表名浅合并**（`wp_disclosure_sync_service.py` L484-490）→ 表格层安全 ✅
- 模板 五、8 的 `[1] 应收利息分类`/`[2] 重要逾期利息` 属 G2、`[3] 应收股利`/
  `[4] 重要的账龄超过1年的应收股利` 属 G3、其余 17 张属 K1 → 表名无交集 ✅
- 🔴 **`text_content` 与 `_note_texts` 是整体替换**（L533-534、L627-632：无 `_note_texts`
  时甚至把 `text_content` 置 `None`）→ K1 录的 10 段说明会被 G2 的一段
  `soe-audit-note` 整体覆盖，反之亦然。三个循环**都开了自动同步** → 用户在 K1 写完说明、
  回 G2 改一个数字，K1 的说明当场消失。
- 🔴 **G2 listed 推孤儿表**：`buildG2ListedSubTableData` 直接复用 soe 的三张表，
  但 listed 模板 五、8 **没有** `坏账准备计提情况`（只有 soe 八、9 的 `[3]` 有）→ 该表永为孤儿。
- `sheet_name` 分叉：K1 用 `附注披露信息(上市公司）`（前半后全），G2/G3 用
  `附注披露信息（上市公司）`（全全）→ `_last_sync_sheet` 被最后同步方覆盖，
  附注「打开同步底稿」深链指向随之漂移。

**H. 账龄枚举**：G2/G3/G5 底稿侧已接 `useAgingConfig`（3 年段 / 5 年段 / 自定义），
G5 披露侧已收敛到 `disclosureAgingLabels.ts`。G2 的账龄未进披露载荷（G2 推的三张表无账龄维度，
账龄在 K1 owns 的 `按账龄披露` 表里）→ 需确认 G2 的 ECL 账龄是否应回流。

---

## Requirements

### Requirement 1: 报表映射真源纠偏（平台级）

**User Story:** 作为审计助理，我需要资产负债表与利润表按正确科目取数，否则底稿、报表、附注三处同时错。

#### Acceptance Criteria

1. WHEN 系统解析报表行 `BS-022 其他债权投资` THEN 公式 SHALL 引用 `TB('1506','期末余额')`
2. WHEN 系统解析报表行 `BS-025 其他权益工具投资` THEN 公式 SHALL 引用 `TB('1507','期末余额')`
3. WHEN 系统解析报表行 `BS-026 其他非流动金融资产` THEN 公式 SHALL 引用 `TB('1519','期末余额')`
4. WHEN 系统解析报表行 `IS-016 信用减值损失` THEN 公式 SHALL 引用 `TB('6702','本期发生额')`
5. WHEN 系统解析报表行 `IS-017 资产减值损失` THEN 公式 SHALL 引用 `TB('6701','本期发生额')`
6. 纠偏 SHALL 以幂等迁移（`backend/migrations/V*.sql`，`IF NOT EXISTS` / 条件更新）落地，
   且只在**现值等于已实证错值**时更新（防覆盖用户自定义的 `project:` 级配置）
7. WHERE 存在 `applicable_standard LIKE 'project:%'` 的项目级覆盖 THE 系统 SHALL 不修改该行
   并在迁移日志列出，交由人工复核
8. WHEN 迁移执行后 THEN 守卫 SHALL 断言「`report_config` 引用的每个科目码都存在于
   `account_chart` 且科目名与报表行名语义一致」，并对本次 5 行做逐行钉死
9. 守卫 SHALL 含反向自检：若把某行改回错值则断言必须失败

### Requirement 2: G 循环 render 科目定位单一真源化

**User Story:** 作为开发者，我需要 G 循环所有 render 策略从同一处拿科目码，不再各写字面量。

#### Acceptance Criteria

1. WHEN `_g4_bond_investment_ecl.py` / `_g4_bond_investment_sppi.py` 需要科目码
   THEN 它们 SHALL 复用 G4 的 `ReportLineAccountSpec(row_code='BS-021')` 解析结果，
   且源码中 SHALL NOT 出现 `'1501'` 字面量作科目码
2. WHEN `_g6_other_bond_investment_ecl.py` / `_g6_other_bond_investment_main_service.py`
   需要科目码 THEN 同上（`BS-022`），源码 SHALL NOT 出现 `'1503'` 字面量作科目码
3. WHEN `_g7_long_term_equity_main_service.py` 需要科目码 THEN SHALL 取解析结果，
   SHALL NOT 出现 `'1511'` 字面量作科目码
4. WHEN G6 的 `main` render 执行 THEN 输出 SHALL 含 `adjudication_prefill`
   （无可映射子科目时为 `None`，宁缺勿造）
5. 各 render 的 `fallback_gross` SHALL 与 `account_chart` 实证值一致
   （G6→`1506`、G8→`1507`、G9→`1519`、G14→`6702`）
6. WHEN 报表公式解析成功但结果与 `fallback_gross` 不一致 THEN render SHALL 在
   `tb_source_codes` 中标注该冲突（新增 `fallback_conflict` 字段），供溯源面板告警
7. 守卫 SHALL 参数化断言「每个 G render 源码不得出现属于其它循环的科目码字面量」，
   并含 `stripComments()` 与反向自检

### Requirement 3: 四表取数结果的前端消费（消 dead output）

**User Story:** 作为审计助理，四表入库后我打开任一 G 循环底稿就应看到已取数，并能追溯来源。

#### Acceptance Criteria

1. WHERE 循环 ∈ {G1, G2, G3, G4, G8, G9, G10, G11, G12, G13, G14}
   THE 系统 SHALL 提供 per-cycle `g{n}AccountScope.ts` 单一真源
   （报表行号 + 兜底标准码 + 运行态取 render 下发的 `tb_source_codes`）
2. WHEN 底稿渲染 THEN 审定表 SHALL 展示四表取数溯源面板，复用平台共享件
   `shared/WpFourTableSourcePanel.vue`（无备抵科目的循环不传 `provisionLabel`）
3. WHEN 用户点击审定表「从四表库带入未审数」THEN 系统 SHALL 用 `adjudication_prefill`
   填充，且 SHALL NOT 覆盖已有手工录入值
4. WHEN 四表重新入库后出现新子科目 THEN 「带入」SHALL 按科目码优先匹配已有行
   （改名后不重复插行），未命中则新建行
5. WHEN 某循环无 `adjudication_prefill` 数据 THEN 界面 SHALL 显示「四表库暂无该科目数据」
   而非静默空转
6. 守卫 SHALL 扫描全部 G 循环宿主，断言「render 输出的 `tb_source_codes` 至少有一个前端消费点」
   （防再次退化为 dead output）

### Requirement 4: 公式预设纠偏与补全

**User Story:** 作为现场经理，我需要公式管理页里 G 循环的预设公式取数正确、覆盖到披露表。

#### Acceptance Criteria

1. WHEN G4 审定表预设求期初 / 期末 THEN 公式 SHALL 为 `TB('1504', …)`，
   SHALL NOT 使用区间 `TB_SUM('1504~1507', …)`
2. WHEN 损益类循环（G11 / G12 / G13 / G14）预设取数 THEN 口径 SHALL 为 `本期发生额`，
   SHALL NOT 使用 `期初余额` / `期末余额`
3. WHEN G12 预设取数 THEN 科目 SHALL 为 `6103`；G14 SHALL 为 `6702`
4. G4-2 SHALL NOT 引用 `1501.03`；G8-2 SHALL NOT 引用 `1525` / `1526` / `1527`
5. 每个预设块的 `sheet` SHALL 存在于对应源 xlsx 的 `wb.sheetnames`
   （删除幽灵块 `分析程序G1-3` 或改为真实 sheet）
6. 每个预设块的 `wp_name` SHALL 与该循环科目语义一致（不得贴错标签）
7. WHERE 循环有披露 sheet THE 系统 SHALL 为两个变体各提供预设块
   （取数来源为审定表 / 明细表的 `WP()` 联动或 `TB()`）
8. 明细表块 SHALL NOT 引用 `WP()` 指向本循环审定表（防公式成环）
9. 纠偏 SHALL 以幂等脚本 `backend/scripts/fix/fix_g_cycle_prefill_presets.py`
   （`--dry-run` / `--check` / 默认 apply）落地
10. 守卫 SHALL 断言：科目码 ∈ `account_chart` ∧ 科目码 ∈ 本循环报表行引用的科目集合
    ∧ sheet 名 ∈ 源 xlsx ∧ 损益类口径为 `本期发生额` ∧ 无成环

### Requirement 5: 附注模板结构对齐源模板（G10 / G11 / G13 / G14）

**User Story:** 作为业务合伙人，我需要附注表格的列头、行集与致同源模板逐字一致。

#### Acceptance Criteria

1. WHEN 附注章节 ∈ {五、34, 五、35, 八、34, 八、35, 五、69, 八、70, 三、公允价值变动收益,
   八、72, 三、信用减值损失, 八、73} THEN 每张表 SHALL 有非空 `columns` 且每列显式表态
   `flat` 或 `group`
2. 每张表 SHALL 有非空 `guidance`，内容取自源模板红字 / 15 号文条款 / 以「勾稽：」前缀标注的工具提示，
   且 SHALL 为纯文本（不含 markdown 粗体标记）
3. WHEN 表名是表头首格泄漏（`项  目`）或段落文本泄漏 THEN SHALL 改为致同措辞的正式表名，
   并同步前端 `X_*_SUBTABLE` 常量与载荷 `_removed_table_keys`
4. WHEN 五、34 主表行集与源模板不一致 THEN SHALL 还原为源模板 8 行
   （交易性金融负债 / 其中：发行的交易性债券 / 衍生金融负债 / 其他 /
   指定为以公允价值计量且其变动计入当期损益的金融负债 / 其中：债券 / 其他 / 合计）
5. WHERE 源模板某表下方是空白可扩行区 THE 模板 SHALL seed 对应数量的空行骨架 + 合计行
6. WHEN 表名或表头含年份字面量（五、34 T2 的 `2025年`）THEN SHALL 去年份化
   （改「本年」/「上年」），防跨年度漂移
7. 修订 SHALL 以幂等脚本 `backend/scripts/fix/fix_note_g_liability_and_pl_structure.py` 落地，
   支持 `--dry-run` / `--check`，`--check` 输出 0 项欠账
8. 守卫 SHALL 用 openpyxl 直读源 xlsx，三向比对（源 xlsx ↔ 模板 headers ↔ 同步 columns），
   并含反向自检

### Requirement 6: 披露表结构与内容优化（对齐源模板披露逻辑）

**User Story:** 作为审计助理，我需要披露表的录入结构、联动与勾稽和源模板的披露思路一致。

#### Acceptance Criteria

1. WHEN 源模板某披露列有取数公式（如 五、34 的 B / E 列引 `审定表G10-1`）
   THEN 底稿披露表 SHALL 提供对应的「从审定表带入」联动，SHALL NOT 要求用户重复录入
2. WHERE 源模板某列无公式（如 五、34 的「本期增加」/「本期减少」）
   THE 底稿 SHALL 保留为手工录入列，并在编制提示中说明
3. WHEN 源模板存在动态插行区 THEN 披露表 SHALL 支持动态增删行，
   行 key SHALL 为稳定标识（`{slot}_{seq}`），SHALL NOT 用中文 label 作 key
4. WHEN 源模板行是「其中：」结构标签 THEN 该行 SHALL NOT 作为动态明细行的默认名，
   且金额全零的占位骨架行 SHALL NOT 推送到附注
5. WHEN 披露表有合计 / 小计行 THEN 同步载荷 SHALL 包含该行并带 `is_total`；
   行型判定 SHALL 先去空白（源模板写「合  计」）
6. WHEN 披露表金额可编辑 THEN SHALL 使用 `WpAmountInput`；只读金额 SHALL 走
   `displayPrefs.fmtAmount()`；`el-input-number :formatter` 残留数 SHALL 为 0
7. WHEN 披露表有文本域 THEN 每个文本域 SHALL 有 AI 辅助按钮，请求 SHALL 走
   `POST /api/workpapers/{wpId}/ai/generate-text` 且 `context` 为 `dict[str,str]`，
   prompt SHALL 含「不得虚构」约束
8. 系统 SHALL 提供披露内部勾稽引擎（纯函数）+ 紧凑单行 bar 面板，
   规则全部取自源模板 Excel 公式
9. WHERE 循环涉及账龄 THE 披露侧账龄档位 SHALL 走单一真源 `disclosureAgingLabels.ts`，
   随项目账龄配置（3 年段 / 5 年段 / 自定义）联动，SHALL NOT 写死档位字面量

### Requirement 7: 多循环共章节的说明文本保护（G2 / G3 / K1）

**User Story:** 作为审计助理，我在其他应收款附注里录的说明，不应因为改了应收利息底稿而消失。

#### Acceptance Criteria

1. WHEN 多个底稿推送同一附注章节 THEN 后端 SHALL 按 `section` 键浅合并 `_note_texts`
   （同 `sub_table_data` 语义），SHALL NOT 整体替换
2. WHEN 某次推送的 `_note_texts` 为空 THEN 系统 SHALL 保留既有文本，
   SHALL NOT 将 `text_content` 置为 `None`
3. WHEN 某底稿需要删除自己曾推送的说明段 THEN SHALL 经显式 `_removed_text_sections` 语义，
   且只允许删除该底稿曾推送过的 `section` 键
4. `text_content` SHALL 由合并后的 `_note_texts` 全量重排生成，顺序按章节内既有顺序稳定
5. WHEN G2 推送 listed 变体 THEN SHALL NOT 推送 `坏账准备计提情况`
   （listed 模板无此表），该表 SHALL 仅在 soe 变体推送
6. G2 / G3 / K1 的 `X_DISCLOSURE_SHEET_NAME` SHALL 与各自源 xlsx 的 tab 名逐字一致
   （守卫用 openpyxl 直读比对，不得只比对常量与 registry）
7. 守卫 SHALL 断言「同一附注章节的多个 owner 的子表名集合两两无交集」，
   清单从各循环 `X_*_SUBTABLE` 常量派生

### Requirement 8: 附注污染清理（三、公允价值变动收益）

**User Story:** 作为质量控制复核合伙人，我需要附注章节只包含属于它的内容。

#### Acceptance Criteria

1. WHEN 章节 `三、公允价值变动收益` 存在表名 `项  目` 且其行集与 `五、69` 的第二张表逐字相同
   THEN 该表 SHALL 被识别为 G11 孤儿并清理
2. WHEN 该章节的 `text_sections` 内容属于附注「九、公允价值」章
   THEN SHALL 被识别为 md 重建污染并清理
3. 清理 SHALL 以默认 dry-run 的脚本落地，`--apply` 属破坏性写库 SHALL 需用户显式确认
4. 清理判据 SHALL 基于**内容比对**（行集逐字相同 / 文本主题）而非章节号白名单
5. 清理后若该章节无剩余子表 THEN SHALL 保留 `_tables` seed 骨架并撤回
   `_source` / `_last_sync_*` 让其回退 legacy 渲染
6. 清理 SHALL 配套 `--rollback`（备份落 `table_data._template_lineage._legacy_backup`）
7. 守卫 SHALL 断言清理后 `--check` 归零，且**不误删**该章节自己的正确内容

### Requirement 9: 全链实测

**User Story:** 作为业务合伙人，我要看到「四表入库 → 底稿有数 → 推送 → 附注有数」在真实项目上跑通。

#### Acceptance Criteria

1. 系统 SHALL 在真实项目上验证 render 下发的 `tb_source_codes.resolved_from` 与解析出的科目码
2. 系统 SHALL 用 postgres 只读复核「叶子科目之和 == 父科目余额」的勾稽不变量
3. 系统 SHALL 用浏览器验证审定表「从四表库带入未审数」后金额与四表库一致
4. 系统 SHALL 验证披露表推送后附注 `last_sync_at` 前移、子表数与列元数据正确
5. 系统 SHALL 验证 G2 / K1 交替同步后**双方说明文本都还在**（Requirement 7 的活体证据）
6. 实测产生的测试数据 SHALL 在验证后完整复原，并记录复原证据

## Glossary

| 术语 | 含义 |
|---|---|
| 四表库 | `trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance` 四张导入表的统称 |
| 报表映射规则 | `report_config` 表按 `applicable_standard` 存的报表行公式（`TB()` / `ROW()` / `SUM_TB()`） |
| 科目映射三层 | `tb_balance.account_code`（客户原始码，点号）→ `account_mapping` → `trial_balance.standard_account_code`（标准码，横杠）→ `report_config.formula` → 报表行 |
| 标准码 / 原始码 | 标准码是平台统一编码（`1231-03`）；原始码是客户科目表编码（`1231.03`） |
| 反解 | 标准码经 `account_mapping` 查回该项目原始码前缀集的过程；无映射时退化为标准码一级段 |
| 叶子科目 | 无 `code + '.'` 子行的 `tb_balance` 科目；聚合必须只取叶子（叶子和 == 父额） |
| 兜底码 / fallback | `ReportLineAccountSpec.fallback_gross`，报表公式解析失败时使用 |
| dead output | 后端 render 已输出但前端零消费的字段 |
| 段落文本泄漏 | md 重建脚本把说明段落当成表名写进 `tables[].name` |
| 表头首格泄漏 | md 重建把表头第一格（如 `项  目`）当成表名 |
| 孤儿子表 | 底稿推送的表名在附注模板中不存在，附注永不渲染 |
| 动态插行区 | 源模板中留白可扩展的行区（对应披露表的动态增删行） |
| 账龄枚举 | 项目级账龄配置（3 年段 / 5 年段 / 自定义），单一真源 `useAgingConfig` + `disclosureAgingLabels.ts` |
| 三向比对 | 守卫同时校验「源 xlsx ↔ 附注模板 headers ↔ 同步载荷 columns」 |
| 反向自检 | 守卫内断言「若把值改回错误形态则断言必须失败」，防断言空转 |
