# Requirements Document

## Introduction

E 类（货币资金）四表取数链路与披露/附注结构对齐。本 spec 沿用 D1/K1/K2/F1/G7 已跑通的范式：
**科目单一真源（报表行解析）+ 共享四表件（叶子聚合）+ 披露表结构以源 xlsx 为唯一裁决者 + 附注侧以校验预设/附注模板为交付口径**。

### 循环范围

| 底稿 | 源模板 workbook | 说明 |
|------|----------------|------|
| E0 | `E0 货币资金 - 函证` | 9 个 `confirmation-*` 组件跨循环共享，**不在本 spec 范围**（仅记录 E0 公式预设 `wp_name='银行询证函'` 与源 xlsx 无对应 tab 的疑似贴错标签） |
| E1 | `E1-1至E1-11 …审定表明细表`<br>`E1-14至E1-15 …分析程序`<br>`E1-18至E1-23 …检查`<br>`E1-26至E1-32 …IPO/舞弊应对` | 本 spec 主体。**两张披露 sheet 均在第一个 workbook**：`附注披露信息(上市公司)` / `附注披露信息(国企)`（**半角括号**） |

### 已实证的事实基线（调查阶段结论，作为后续裁决依据）

**科目映射真源**

- `report_config`：`BS-002 货币资金 = TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')`，**四准则（listed/soe × standalone/consolidated）完全一致**
- `account_chart` 实证：`^10(0|1)[0-9]$` 范围内**只有** `1001 库存现金` / `1002 银行存款` / `1012 其他货币资金`（无银行业 `1003 存放中央银行款项` / `1011 存出保证金`）
- **货币资金无备抵科目**（不计提减值）→ `ReportLineAccountSpec` 不需要 `provision_row_code`
- `1502 = 持有至到期投资减值准备`（**不是**数字货币）

**活体 `tb_balance` 形态（10 个项目有货币资金数据，`df5b8403` 222 行最丰富）**

- `1002` 父科目与 `1002.001`~`1002.531` 子科目并存；叶子和 `20,751,212.11` == 父科目期末 ✓
- `1012` 存在**三层**：`1012.014` 金华小桔有车 + `1012.014.01` + `1012.014.02`；`490,611.21 + 257,346.11 = 747,957.32` == 中间层期初 ✓；叶子和 `461,130.20` == 父科目期末 ✓
- `1001` 该项目无子科目 → 一级科目自身即叶子
- **叶子科目名 = 银行户名 / 支付渠道名**（「金华招行基本户801」「金华结构性存款账户」「金华支付宝」「微信小程序」「聚合收款」「AFO」「小桔有车」）→ **不含受限类别关键字**，与 G1「客户叶子名多为银行户名不含品种关键字」同款

**附注章节落点**

- `note_template_variant_matrix.json`：货币资金 = **listed `五、1` / soe `八、1`**（`legacy_aliases.soe = ['五、1']`）
- **外币两张表的真正落点是跨循环共享章节** `外币货币性项目` = **listed `五、73` / soe `八、92`**（该章节同时承载 货币资金/应收账款/短期借款/长期借款/应付债券 各币种行）

**校验预设（列结构裁决者）**

`note_check_preset_formulas.json` 中货币资金 **两版各 6 条且完全相同**：

| id | 表 | 类型 | 公式 |
|----|----|------|------|
| F1-1 | ① 货币资金分类表 | 余额 | 报表.货币资金期末 = ①表.合计行.期末余额 |
| F1-2 | ① 货币资金分类表 | 余额 | 报表.货币资金期初 = ①表.合计行.期初余额 |
| F1-3 | ① 货币资金分类表 | 其中项 | ①表 sum(合计行以外明细行) = 合计行（每列独立） |
| F1-4 | ② 受限制的货币资金明细表 | 其中项 | ②表 sum(合计行以外明细行) = 合计行（每列独立） |
| F1-5 | ② 受限制的货币资金明细表 | 跨科目 | ②表.合计行.期末 = 报表.货币资金期末 − 补充资料③表."期末现金及现金等价物余额" |
| F1-6 | ② 受限制的货币资金明细表 | 跨科目 | ②表.合计行.期初 = 报表.货币资金期初 − 补充资料③表."期初现金及现金等价物余额" |

> 校验预设**两版同形**是「上市侧是否补②表」的核心依据（见 Requirement 6 待裁决点）。

## Requirements

### Requirement 1: 修复披露 Tab 运行时挂载失败（P0）

**User Story:** 作为审计助理，我打开 E1 披露 Tab 时页面必须能正常渲染，同步按钮与自动同步必须真实生效。

#### Acceptance Criteria

1.1 WHEN `E1TabDisclosure.vue` 挂载 THEN 组件不得抛 `ReferenceError`：现有 `watch([disclosureRows, restrictedRows, noteText, variant], …)` 位于第 62 行，而 `variant`(L83) / `disclosureRows`(L167) / `restrictedRows`(L452) / `noteText`(L493) 均在其后声明，`<script setup>` 的 `const` TDZ 使该 watch 在 setup 期即抛错，**整个披露 Tab 无法挂载**（`get_diagnostics` 已实测零诊断，属「只有浏览器挂载才暴露」类缺陷）
1.2 THE watch SHALL 移动到全部被监听 ref/computed 声明之后（且在 `syncToDisclosureNotes` 声明之后）
1.3 WHEN 本地 `type DisclosureVariant = 'listed' | 'soe'`（L81）与第 27 行 `import { …, type DisclosureVariant }` 重复 THEN 删除其中一处，保留单一来源
1.4 THE 修复 SHALL 附守卫：源码级断言「所有 `watch(` 的被监听标识符声明行号 < watch 行号」，并含反向自检
1.5 WHEN 修复后浏览器实测 THEN 披露 Tab 两变体均能挂载，且「静置期 0 次 POST + 数据变更 1 次 POST」

### Requirement 2: 四表取数收敛到共享件与报表行单一真源

**User Story:** 作为审计助理，四表入库后 E1 各明细底稿与审定表应自动有数据，且取数科目口径与报表映射一致、可追溯。

#### Acceptance Criteria

2.1 THE `_e1_monetary_fund.py` SHALL 复用 `app/services/four_table/`（`ReportLineAccountSpec` + `resolve_report_line_accounts` + `select_leaves` / `aggregate_leaves`），删除自造 `_fetch_leaf_accounts` / `_is_leaf`
2.2 WHEN 现有 `_is_leaf` 用 `c.startswith(code)` 判定 THEN 该实现**缺点号边界**：若客户同时存在 `1002.1` 与 `1002.11`，`1002.1` 会被误判为非叶子而整段丢失（活体 `df5b8403` 的 3 位编码未触发，属潜伏缺陷）→ 改由共享件处理
2.3 THE 明细预填 SHALL 按 `BS-002` 解析结果取数，删除硬编码 `_CASH_PREFIX/_BANK_PREFIX/_OTHER_PREFIX`；兜底码 `('1001','1002','1012')` 只作 `ReportLineAccountSpec.fallback_gross`
2.4 THE render SHALL 输出平台标准 `tb_source_codes`（含 `gross_standard` / `gross_original` / `resolved_from`），且**必须有前端消费方**（现状 grep 0 命中 = dead output）
2.5 THE 自检不变量 SHALL 成立：三个科目族各自「叶子和 == 父科目期末额」（活体已验 `1002` 与 `1012`）
2.6 WHEN 现有全零账户过滤（`abs(...) >= 0.005` 四项全零即剔除）作用于 `1002` THEN 会滤掉「本年新开立但期末余额为 0」的账户 → **E1-10 已开立银行账户清单核对的完整性程序被削弱**。THE 银行账户清单（`account_list`）SHALL 保留零余额账户，仅金额类明细预填沿用过滤
2.7 THE render SHALL 新增 `adjudication_prefill`：按 `1001/1002/1012` 三族叶子聚合出审定表 E1-1 的未审数期初/期末，**仅无持久化时预填**

### Requirement 3: E1 公式预设纠偏与补全（含披露页）

**User Story:** 作为现场经理，我在底稿当页的公式管理里应看到正确、完整的取数公式预设。

#### Acceptance Criteria

3.1 THE 「数字货币明细表」块 SHALL 纠正：现状 `account_codes=['1502']` + `TB('1502','期末余额')`，而 `1502 = 持有至到期投资减值准备` → **取错整个科目族**（同 K2 `1231` 范式）。数字货币按准则解释 15 号在「货币资金」项下二级列报，无独立标准科目 → 改为 `PLACEHOLDER` + 描述写明「客户自设二级科目，需项目级映射」，**不得臆造科目码**
3.2 THE 「货币资金分析程序」块 SHALL 纠正 `PREV('E1','分析程序E1-3','审定数')`：源 xlsx **无「分析程序E1-3」sheet**（`E1-3` 是「银行存款及其他货币资金明细表」；分析表实为「货币资金分析表E1-14」/「利息收入月度分析E1-15」）
3.3 THE `TB_SUM('1001~1012', …)` SHALL 改为显式 `TB('1001')+TB('1002')+TB('1012')`：当前标准科目表下区间等价于 `BS-002`（已实证），但客户若存在 `1003`/`1011` 即虚增，属脆弱写法
3.4 THE 两张披露 sheet SHALL 新增公式预设块（现状**完全空白**）：主表各行取自 E1-1 审定数（源 xlsx `B8=='货币资金审定表E1-1'!G7` 等逐格可查），外币表取自 E1-2/E1-3
3.5 THE 审定表 E1-1 块 SHALL 补底稿间 `WP()` 联动（← E1-2 现金明细 / ← E1-3 银行存款及其他货币资金明细 / ← E1-4 数字货币明细）；**明细表块禁写 `WP()` 防成环**
3.6 THE 守卫 SHALL 校验：每个块的 `sheet_name` 存在于源 xlsx tab 名集合、每个 `account_codes` 元素 ∈ 标准科目表 且 ∈ 本循环报表行引用的科目集合（`test_d_cycle_account_codes.py` 范式）

### Requirement 4: 披露表结构以源 xlsx 为唯一裁决者

**User Story:** 作为业务合伙人，底稿披露表的表结构、行集、列头必须与致同源模板逐字一致。

#### Acceptance Criteria

4.1 THE 上市披露表 SHALL 按源 xlsx `附注披露信息(上市公司)` 呈现 3 张表 + 4 段文本：
- 主表 R6~R16「货币资金」3 列（`项  目` / `期末数` / `期初数`），行 R8~R15 = 库存现金 / 银行存款 / 存放财务公司款项 / 其他货币资金 / 存款应计利息 / 数字货币 / 合计 / 其中：存放在境外的款项总额；R16 是**勾稽校验行**（`B16=B14-D62`）非披露行
- 外币性货币项目 R25~R32：**7 列两级**（`项  目` rowspan2 + `期末数{外币余额,折算率,人民币金额}` + `期初数{外币余额,折算率,人民币金额}`），行 = `货币资金：` + 其中：美元/日元/澳元/欧元（**派生自下方原币表**）
- 货币资金原币表 R35~R62：**7 列两级**（同上，子列为 `原币金额/折算率/人民币金额`），行 = 库存现金：/银行存款：/银行存款中：财务公司存款/其他货币资金： 各 × 人民币/美元/日元/澳元/欧元 + `合  计`
- 文本：R17 提示（汇率中间价 + 准则解释15号 + 数字货币）/ R18 正文（不存在受限款项）/ R19 括注 / R23 存款利息提示

4.2 THE 国企披露表 SHALL 按源 xlsx `附注披露信息(国企)` 呈现 4 张表 + 2 段括注：
- 主表 R6~R12「货币资金」3 列（`项 目` / `期末余额` / `年初余额`），行 = **现金**（不是"库存现金"）/ 银行存款 / 其他货币资金 / 数字货币 / `合  计`
- **受限制的货币资金明细** R15~R23 3 列（`项 目` / `期末余额` / `年初余额`），行 R17~R21 = 银行承兑汇票保证金 / 信用证保证金 / 履约保证金 / 用于担保的定期存款或通知存款 / 放在境外且资金汇回受到限制的款项，**R22 `…` 是动态插行标记**，R23 `合  计`
- 外币两表同上市
- 文本：R13 括注（受限/境外/潜在回收风险单独说明）/ R14 括注（数字货币二级明细）

4.3 WHEN 底稿现状 `LISTED_ITEMS` 的 overseas 行 label 为「其中：存放境外」THEN 改为源模板字面「其中：存放在境外的款项总额」
4.4 WHEN 底稿现状 `SOE_ITEMS` 首行为「现金」（已正确）THEN 保持；但**附注模板 soe 主表首行是「库存现金」**需按 Requirement 5 纠正
4.5 THE 币种与受限类别 SHALL 收敛为**单一真源**（per-cycle `e1CurrencyScope.ts` / `e1RestrictedScope.ts`），禁止组件内硬编码：现状 `SIMPLE_CURRENCIES` / `DETAILED_CURRENCIES` / `DETAILED_PROJECTS` 是 `E1TabDisclosure.vue` 内联常量
4.6 THE 币种枚举 SHALL 支持「预置 + 自定义增删」，且与附注 `五、73`/`八、92` 的币种行（美元/欧元/港币）**口径可对齐**（现状底稿是 美元/日元/澳元/欧元，两侧不一致）

> **说明：账龄枚举在 E 类不适用。** 货币资金无账龄维度。E 类与「账龄枚举（3年段/5年段/自定义）」对应的枚举维度是 **①币种** 与 **②受限类别**，本 spec 按同款「枚举驱动 + 动态插行 + 稳定 key」范式处理（参照 H7 `{slot}_{seq}`，**key 不能用 label**）。

### Requirement 5: 附注模板结构修订（五、1 / 八、1）

**User Story:** 作为质量控制复核合伙人，附注模块的货币资金章节表格结构必须与源模板和校验预设一致。

#### Acceptance Criteria

5.1 THE 两版全部表 SHALL 补齐 `columns`（现状 **listed 1 表 / soe 2 表全部 `columns=0`**）并显式标 `flat`（单级表头），`key` 逐字镜像 `e1NoteSectionMap.ts` 既有列键
5.2 THE 两版全部表 SHALL 补齐 `guidance`（现状全空 → TAB 无编制提示），内容只取源 xlsx 红字/括注 + 15 号文/准则解释 15 号条款，**纯文本禁 markdown 粗体**
5.3 THE soe 八、1 主表首行 SHALL 由「库存现金」改为源 xlsx R8 字面「**现金**」
5.4 THE soe 八、1 主表末行「其中：存放在境外的款项总额」SHALL 删除 —— 源 xlsx R13 是**括注文字**（`（如有因抵押、质押或冻结等对使用有限制、存放在境外、有潜在回收风险的款项应单独说明。）`）被 md 重建当成数据行 = **假行**
5.5 THE soe 受限表 SHALL 删除「金融企业法定存款准备金或备付金」行（源 xlsx **无此行**），并**补「合  计」行**（源 R23，且校验预设 F1-4 要求合计行）
5.6 THE soe 受限表 SHALL 不 seed `…` 占位行（源 R22 是动态插行标记，由底稿动态行驱动）
5.7 THE 附注列头字面 SHALL **不改动**（listed `期末余额/上年年末余额`、soe `期末余额/期初余额`）—— 按平台铁律「附注是交付物，列结构随附注模版 + 校验预设；底稿可按源 xlsx，同步时投影成附注形状」；本仓库无 `附注模版/*.md` 可复核，故保守不动，只补 columns/guidance
5.8 THE 幂等脚本 SHALL 提供 `--dry-run` / `--check` / `--apply`，复用 `backend/scripts/fix/_note_structure_kit.py`
5.9 THE 守卫 SHALL 三向比对：openpyxl 直读源 xlsx ↔ 附注模板 `headers`/`rows` ↔ 同步载荷 `columns`，并含反向自检

### Requirement 6: 上市侧「② 受限制的货币资金明细表」（✅ 用户已裁决 2026-08-01：**补**）

**User Story:** 作为业务合伙人，上市附注也要以表格形式披露受限资金；且每个项目的受限科目命名各不相同，取数必须动态识别而非写死类别。

#### Acceptance Criteria

6.1 THE 裁决依据 SHALL 记录（两侧证据冲突，按校验预设裁决）：
- **源 xlsx 上市披露 sheet 无受限表**，仅 R18 正文 + R19 括注（文字披露）
- **校验预设 listed 侧有 F1-4 / F1-5 / F1-6 三条明确引用「② 受限制的货币资金明细表」**，其中 F1-5/F1-6 是与现金流量表补充资料③表的跨科目勾稽（只有表格化才能自动校验）→ 不补则这三条在 listed 侧恒不可用
- 平台铁律「校验预设是列结构裁决者」→ **补**

6.2 THE 上市侧②表 SHALL 复用国企②表的行集与列结构（`项目` / `期末余额` / `上年年末余额`，列头 label 按 listed 变体），源模板 R18/R19 文字披露保留为 `_note_texts`
6.3 THE ②表 SHALL 为**条件表**：有受限行才推；无行不推空表**且进 `_removed_table_keys`**（有录入区块的条件表语义，K7 国企政府补助范式）
6.4 THE 两版②表 SHALL 共用同一套受限分类真源与取数逻辑（不得上市/国企各写一份）

### Requirement 11: 受限资金动态取数（映射规则驱动 + 项目自适应）

**User Story:** 作为审计助理，不同项目的受限资金科目命名千差万别（有的叫「保证金」，有的叫「冻结存款」，有的挂在其他货币资金、有的挂在银行存款定期户），四表入库后②表应能自动识别并带入，识别不出的要让我点选归类而不是被塞进错误类别。

#### Acceptance Criteria

11.1 THE 受限科目候选集 SHALL 由**映射规则驱动**：先经 `BS-002` 报表行解析得到 `1001`/`1002`/`1012` 三族标准码 → 经 `account_mapping` 反解为该项目的**原始码前缀** → 在此范围内取叶子。**不得跨出货币资金科目族**去猜（受限资金必然是货币资金的一部分，F1-5 勾稽即此含义）
11.2 THE 分类真源 SHALL 是一份声明式 dataclass `E1_RESTRICTED_BUCKETS`（`backend/app/services/four_table/e1_restricted_buckets.py`），每桶含 `key` / `label` / `keywords` / `exclude_keywords` / `source_ref`（指向源 xlsx 单元格，供 openpyxl 守卫反查）；5 个预置桶逐字取自源 xlsx R17~R21，第 6 类为「其他受限资金」
11.3 THE `classify_e1_restricted_leaf(name)` SHALL **名称优先 + 否决词否决 + 未命中返 `None`**（宁缺勿造）。活体实证的叶子名（「金华招行基本户801」「金华支付宝」「微信小程序」「聚合收款」「AFO」「小桔有车」「金华结构性存款账户」）必须全部返 `None`
11.4 WHEN 分类顺序存在关键字包含关系 THEN 顺序即优先级并由守卫钉死：`信用证保证金` 必须先于 `银行承兑汇票保证金`（否则「信用证保证金」不会被含「保证金」的桶提前吃掉需验证）、`用于担保的定期存款或通知存款` 的「担保」必须先于泛「存款」、`放在境外且资金汇回受到限制的款项` 的「境外」独立
11.5 THE render SHALL 输出 `restricted_prefill`：
```
{ buckets: { <bucketKey>: { opening, closing, codes: string[] } },
  unclassified: [{ code, name, opening, closing }],
  source: { report_row_code: 'BS-002', gross_standard: [...], resolved_from: ... } }
```
`unclassified` 是**未命中任何桶的货币资金叶子**，供前端点选归类——这是「项目科目各不相同」的兜底通道，**不得静默丢弃也不得臆造归类**
11.6 THE 前端②表 SHALL 提供「从四表库带入受限资金」：命中桶的自动填入对应类别行；`unclassified` 列在「待归类科目」面板，审计师可**点选归入某类 / 新建自定义类别 / 标记为不受限**
11.7 THE 人工归类结果 SHALL 持久化为 `E1-disclosure-{variant}-restricted-map`（`原始科目码 → bucketKey | '__unrestricted__'`），下次刷新取数时**人工归类优先于自动分类**；四表新增科目自动出现在 `unclassified`
11.8 THE ②表行 SHALL 支持动态插行（源 xlsx R22 `…` 即此语义）：新增类别须 `ElMessageBox.prompt` 先输名称；行 key 用稳定 key `restricted_{bucketKey|custom}_{seq}`，**禁用 label 作 key**
11.9 THE 「不受限」标记 SHALL 参与勾稽而非隐藏：被标 `__unrestricted__` 的叶子金额计入「货币资金合计 − 受限合计 = 现金及现金等价物」的差额侧，供 F1-5/F1-6 自动校验
11.10 THE 自动分类 SHALL 不覆盖已有金额：仅在该类别行金额为空或用户确认覆盖时写入（同 K2 `previewSeedFromPrefill` 范式）
11.11 THE 守卫 SHALL 含反向自检：打乱 `E1_RESTRICTED_BUCKETS` 顺序后，「信用证保证金」被错桶吃掉的用例必须失败；活体叶子名全 `None` 的用例必须存在

### Requirement 7: 外币两表的附注落点打通（五、73 / 八、92）

**User Story:** 作为审计助理，我在披露表录入的外币折算数据应能推送到附注的外币货币性项目章节。

#### Acceptance Criteria

7.1 THE 外币数据 SHALL 推送到**跨循环共享章节** `五、73`（listed）/ `八、92`（soe）「外币货币性项目」——现状底稿外币表**完全无同步路径**，录了永远进不了附注
7.2 WHEN 该章节为跨循环共享（现有 rows 含 应收账款/短期借款/长期借款/应付债券 各段）THEN E1 SHALL **只推「货币资金」段的行**，不得覆盖他循环段落；`_removed_table_keys` 只删本底稿上次推过的键
7.3 THE 列结构冲突 SHALL 如实处理：附注 `五、73`/`八、92` 现状 `headers=['项目','期末外币余额','折算汇率','期末折算人民币余额']` = **4 列仅期末**，而源 xlsx 外币表是 **7 列两级（期末+期初）**。因该章节跨循环共享，**不得单方面按 E 类源模板扩列**（会波及 D2/K/L 各循环）→ E1 侧投影为附注 4 列（只推期末），期初留在底稿；扩列另立平台级 spec
7.4 THE listed `五、73` 与 soe `八、92` 的行集差异 SHALL 保持（listed 16 行含 `可无限量添加行` 占位、soe 25 行含 `……`）—— 占位行属他循环骨架，E1 只按业务键推「货币资金」段
7.5 THE `五、73` 的 `可无限量添加行` 与 `八、92` 的 `……` SHALL 按平台铁律区分：作**列头**丢弃、作**行**保留（此处是行 → 保留）
7.6 THE listed 五、1 的 text_sections 首条「（外币信息，在"附注五、81、外币货币性项目"中披露）」SHALL 纠正章节号为 `五、73`（实证 `五、81` 是陈旧值）—— 属平台级 data-hygiene，本 spec 只改 E 类这一条并记录

### Requirement 8: 同步载荷完整性

**User Story:** 作为审计助理，点「同步到附注」后附注模块应完整拿到表格与文本。

#### Acceptance Criteria

8.1 THE 组件 SHALL 传入真实 `applicableStandards`（现状调 `buildE1SyncPayload(variant, wpId, **null**, snapshot)` → `current_standard` 永远 `*_standalone`，合并口径失效）；接 `useHostApplicableStandards`
8.2 THE 载荷 `columns` SHALL 显式标 `flat`（**seed 与推送两处都要加**，H8 已踩过只加一侧的坑）
8.3 THE 载荷 SHALL 携带 `_removed_table_keys`（复用 `disclosureSyncedTables.ts` 的 `buildRemovedTableKeys`），并做基线播种（R7.5 范式）
8.4 THE `_note_texts` SHALL 按源模板分段（现状只有 1 条「货币资金说明」）：上市 = 受限及境外款项说明 / 存款利息说明；国企 = 受限说明 / 数字货币说明；每条带**中文 title**，空文本过滤
8.5 THE 每个文本域 SHALL 配 AI 辅助 + 复核（后端 `_SECTION_PROMPTS` 同步登记，prompt ≥20 字且含「不得虚构」）
8.6 THE 主表合计行 SHALL 随载荷推送并标 `is_total`；合计行字面按**本章节实证**取（附注模板是「合计」，源 xlsx soe 是「合  计」→ 载荷走 `E1_NOTE_TOTAL_LABEL` 常量）

### Requirement 9: 勾稽校验与溯源

**User Story:** 作为 EQCR 技术复核人，我需要看到披露数据的勾稽结果与四表来源，能逐层追溯。

#### Acceptance Criteria

9.1 THE 勾稽引擎 SHALL 实现校验预设 F1-1~F1-6 全部 6 条（纯函数 + `WpDisclosureConsistencyPanel` 展示），容差 0.01 元
9.2 THE 勾稽 SHALL 额外实现源 xlsx 自带的两条：上市 `B16 = B14 − D62`（主表合计 − 原币表人民币合计）、`外币性货币项目` 各行 = 原币表对应四段之和
9.3 THE 溯源面板 SHALL 迁移到平台共用件 `WpFourTableSourcePanel.vue` + `tbSourceCodes.ts`（现状 `E1FourTableSourcePanel.vue` 自成一套，消费 `FourTableSourceRow[]` 而非 `tb_source_codes`）
9.4 THE 审定表 E1-1 SHALL 增「从四表库带入未审数」按钮 + 溯源条（显示 `BS-002` 解析结果与 `resolved_from`）
9.5 WHEN 受限类别无法从四表叶子名自动识别 THEN **宁缺勿造**：活体实证叶子名为银行户名/支付渠道名（「金华招行基本户801」「金华支付宝」「聚合收款」），不含「保证金」等受限关键字 → 只做关键字命中式建议（命中才 seed），未命中不臆造归类

### Requirement 10: 平台铁律合规

**User Story:** 作为现场经理，E 类改动必须遵守平台既有的数值格式、控件、表格与守卫铁律，不引入已知踩坑。

#### Acceptance Criteria

10.1 THE 金额显示 SHALL 走 `displayPrefs.fmtAmount()`（**store 成员，非模块级导出**）
10.2 THE 可编辑金额 SHALL 用 `WpAmountInput.vue`；现状 `E1TabDisclosure.vue` 与 `E1TabCashCount.vue` / `E1TabCreditReport.vue` 使用 `el-input-number :formatter`（EP 2.13.6 **无此 prop，千分符从未生效**）→ 全量替换并 grep 归零
10.3 THE 派生列（人民币金额 = 原币 × 折算率、合计行、账面价值）SHALL 读时推导，不持久化
10.4 THE Vue 模板属性 SHALL 禁用中文引号/特殊 Unicode
10.5 THE `saveBatch` / 防抖累积器 SHALL 按 itemId 去重
10.6 THE 新增 `build*Columns` SHALL 零入参可调并登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`
10.7 THE 披露 sheet 分发 SHALL 「附注」判定前置于 wp_code 正则，且「国企」「国有」「國企」三写法全认；`E1_DISCLOSURE_SHEET_NAME` 保持**半角括号**（源 xlsx 实证）

## Glossary

| 术语 | 含义 |
|------|------|
| E 类 | 货币资金循环（E0 函证 + E1 货币资金） |
| BS-002 | `report_config` 中「货币资金」报表行编码，公式 `TB('1001')+TB('1002')+TB('1012')`，四准则一致 |
| ①表 / ②表 | 校验预设对附注货币资金章节两张表的编号：①货币资金分类表（即主表）/ ②受限制的货币资金明细表 |
| F1-1~F1-6 | 货币资金校验预设 id（`F` = 附注章节序号前缀，与循环代号 F 无关） |
| 五、1 / 八、1 | 货币资金附注章节号（listed / soe） |
| 五、73 / 八、92 | 「外币货币性项目」附注章节号，**跨循环共享**（货币资金/应收账款/借款/应付债券） |
| 原币表 | 源 xlsx 披露 sheet R35~R62 的「货币资金」按原币列示表（7 列两级），外币性货币项目表由它派生 |
| 币种枚举 | E 类替代「账龄枚举」的枚举维度：人民币/美元/日元/澳元/欧元 + 自定义 |
| 受限类别枚举 | 国企②表的 5 类预置项 + 自定义（源 xlsx R22 `…` 为动态插行标记） |
| 叶子聚合 | `four_table.select_leaves`/`aggregate_leaves`，不变量「叶子和 == 父科目额」 |
| dead output | render 已下发但前端零消费的字段（本循环 `tb_source_codes` 现状即是） |
