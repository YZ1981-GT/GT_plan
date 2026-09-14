# Requirements Document

## Introduction

E 循环（E0 函证 / E1 货币资金）的「四表入库 → 底稿刷新取数 → 披露表 → 推送附注」全链收口。

归档 spec `e1-four-table-extraction-and-disclosure-alignment`（20/20）已把**科目定位链路**建好且正确，本 spec 只补它留下的缺口，**不重建任何已通的部分**。

### 实证基线（2026-08-08，只读零改动）

**科目映射链路已通且正确**：

```
report_config.BS-002 = TB('1001')+TB('1002')+TB('1012')      ← 四准则一致、编码正确
      ↓ 只作提示与冲突检测，不作定位依据
semantic_account_resolver（按科目名在「本项目」account_chart 定位）
      ↓ ①client 表按名 ②standard 表按名 ③report_config 码(须本项目存在) ④兜底码 ⑤返空
5 槽 = cash(1001) / bank(1002) / other(1012) / finance_co(无兜底码) / digital(无兜底码)
      ↓ account_mapping 反解 → 原始码前缀 → fetch_tb_subtree(active dataset) → select_leaves
build_e1_*() 纯函数 → render html_data
      ↓ 宿主 GtE1MonetaryFund.seedFromFourTable()（persist-first，不覆盖已有）
allResponses → 各子 Tab（子 Tab 不需要 htmlData prop）
```

- 真实库 8 项目 `parent_check`「叶子和 == 父额」**8/8 全部成立**
- 既有守卫 **132 passed**；`fix_note_e1_monetary_fund_structure` / `fix_e1_prefill_presets` / `fix_e1_orphan_sheet_presets` 三个 `--check` 均 **0 欠账**
- 已接通：E1-1 审定表 5 槽预填 + TB 核对基准、E1-2/E1-3/E1-10 明细种子、跨 sheet 聚合键、披露 `restricted_prefill` 逐叶子、「重新取数」按钮

**账户级数据源实证（本 spec 的核心依据）**：

`tb_aux_balance` 的 `aux_type='银行账户'` 维度，`aux_dimensions_raw` 一行即含全部维度组合：

```
金融机构:YG0014,上海浦东发展银行;银行账户:58080155200000296
```

带 `get_active_filter` 后与 `tb_balance` **逐分勾稽成立**（8 项目 × 全部科目）：

| 项目 | 1002 账户数 | aux[银行账户] closing | tb_balance closing |
|---|---|---|---|
| 陕西华氏 `a7fc75e5` | 38 | −297,771,168.89 | −297,771,168.89 |
| 重药控股安徽 `0ec33ac9` | 22 | 4,703,056.26 | 4,703,056.26 |
| 重庆医药医疗器械 `52c04ed1` | 21 | 1,272,030.63 | 1,272,030.63 |
| 和平药房 2024 `f064f5e4` | 23 | 848,871.86 | 848,871.86 |
| 和平药房 2025 `2aa00f57` | 17 | 327,095.20 | 327,095.20 |
| 和平物流 `b39809ed` | 6 | 0.00 | 0.00 |
| 四川物流 `4f6dbc36` | 2 | 4,048.93 | 4,048.93 |
| 宜宾临港店 `c8621493` | 1 | 110.30 | 110.30 |

而客户 **1002 不分户**（`tb_balance` 叶子恒 1 行）⇒ E1-3 逐户列示与 E1-10 完整性核对**当前拿不到任何账户**。

**附注结构真源 = `docs/模版/` 两份 docx**（不是底稿 xlsx）。逐格比对结果：

| 项 | 源 docx | 模板 JSON 现状 | 判定 |
|---|---|---|---|
| listed 五、1 主表 | 8 行 | 8 行 | 一致 |
| soe 八、1 主表首行 | **库存现金** | 现金 | 不符 |
| soe 八、1 主表行数 | **6**（含「其中：存放在境外的款项总额」） | 5 | 不符 |
| soe 受限表类别数 | **6**（含「金融企业法定存款准备金或备付金」） | 5 | 不符 |
| 外币表列数 | 4（项目/期末外币余额/折算汇率/期末折算人民币余额） | 4 | 一致 |
| 外币表段数 | listed **3** / soe **5** | listed 3 / soe 5 | 一致（两版不对称是源 docx 事实） |
| soe 八、92 短期借款段 row_code | 短期借款 = `BS-041` | **`BS-031`（使用权资产）** | 错码 |

## Glossary

| 术语 | 含义 |
|---|---|
| 语义槽 | `SemanticAccountSlot`，按科目名在本项目 `account_chart` 定位的一个命名科目集合 |
| 账户级取数 | 从 `tb_aux_balance` 的 `银行账户`/`金融机构` 维度按「开户银行 + 银行账号」逐户取数 |
| 宿主种子化 | `GtE1MonetaryFund` 把 render 的四表预填写进 `allResponses`，子 Tab 经既有通道读（persist-first） |
| 受限桶 | `E1_RESTRICTED_BUCKETS` 的一个分类项，中文标签由后端单一真源下发 |
| 段级合并 | 共享附注表按段首行 `report_row_code` 切段，推送方只替换自己那一段（`_row_scope`） |

## Requirements

### Requirement 1: 账户级取数源接入（E1-3 / E1-10 逐户列示）

**User Story:** 作为审计师，我要在四表入库后于 E1-3 银行明细表看到逐个银行账户的行、在 E1-10 看到完整的已开立账户清单，以便执行逐户核对与账户完整性程序，而不是只看到一行「银行存款」汇总。

#### Acceptance Criteria

1.1 render 必须新增账户级取数：从 `tb_aux_balance` 取 `aux_type='银行账户'` 的行，查询一律经 `get_active_filter`（禁裸写 `is_deleted == False`）
1.2 每个账户行必须解析 `aux_dimensions_raw` 得到「开户银行名称」与「银行账号」两个字段；解析不出时账号取 `aux_name`、银行名留空（不臆造）
1.3 同一账号在 active dataset 内出现多行时按账号聚合求和，`opening_balance`/`closing_balance`/`debit_amount`/`credit_amount` 一律 `COALESCE(...,0)`
1.4 账户级取数按语义槽的原始码前缀归属（`bank` 槽 / `other` 槽），归属不了的账户进独立的 `unassigned` 清单而**不静默丢弃**
1.5 账户级合计必须与对应科目的 `tb_balance` 叶子金额勾稽；不平时在载荷里如实暴露差异而**不修正数据**
1.6 aux 侧无该科目数据时账户级清单返空数组，前端退回既有 `tb_balance` 叶子口径（零回归）
1.7 `account_list`（E1-10 用）必须**保留零余额账户**，与金额明细的全零过滤口径显式不同
1.8 载荷必须标注每条账户行的取数来源（`tb_aux_balance:银行账户:{账号}`）供溯源展示
1.9 E1-3 有两个同名 variant（`仅人民币` / `人民币及外币`，平台已有 variant 分流机制），账户级种子必须按当前 variant 产出：`rmb` 版不下发 `fxCurrency`，`multi` 版下发。**🔴 原币金额与汇率 aux 侧无数据源**（实测 `tb_aux_balance` 只有 `opening_fc` 一列且 `aux_type='银行账户'` 下**全库为 NULL**，**无 `closing_fc`、无汇率列**；308 行 `currency_code` 全为 `CNY`）⇒ `fxRate`/`openingFc`/`increaseFc` 等列一律**留空**由审计师填，禁由记账本位币金额反推。两个 variant 下产出的账户条数必须相同（外币账户在 `rmb` 版不丢弃，只是不带 `fxCurrency`）
1.10 「aux 侧存在非记账本位币账户而当前为 `rmb` 版」时必须产出提示信号「本项目有外币账户，建议使用『人民币及外币』版」。**该分支当前全库 0 命中**（`currency_code` 全 `CNY`）= 潜伏态，与 `digital`/`finance_co` 恒空同性质 ⇒ 守卫用替身构造非 CNY 账户验证分支可达，并断言「恒空时载荷形态仍合法」

### Requirement 2: 语义槽明细预填覆盖全部 5 槽

**User Story:** 作为审计师，若本项目确有「数字货币」或「存放财务公司款项」科目，我要对应明细表也能刷新取数，以便这两类按准则解释 15 号增设的项目同样可追溯。

#### Acceptance Criteria

2.1 `_DETAIL_SLOT_KEYS` 必须扩至含 `digital` 与 `finance_co`，两槽的明细行字段与既有三槽逐字同构
2.2 槽 `found=False` 时该槽明细返空数组，前端显示「本项目无此科目」而**不是 0**
2.3 `finance_co` 槽命中时，E1-3 的账户行必须自动归入 `finance` 分组而不要求审计师手工重分类
2.4 E1-4 数字货币明细表必须能被宿主种子化（新增 `E1-digital-detail-rows` 键与「重新取数」分支）
2.5 全库 8 项目这两槽 `found=False` 是数据事实，守卫必须断言「恒空时载荷形态仍合法且不产生 0 值行」
2.6 **披露主表的三个 `crossKey: ''` 行必须由语义槽预填**（`E1_MAIN_ROWS_LISTED` 的 `finance_co`「存放财务公司款项」/ `digital`「数字货币」/ `accrued`「存款应计利息」）。这三行的注释已明文承诺「由 render 的语义槽预填」而**当前无任何实现** = 未兑现的承诺（同 E1-4 预设 description 那处），且它比明细表更直接影响交付件（附注主表行）。`finance_co`/`digital` 取对应槽的审定合计；`accrued` 取 E1-1 审定表应计利息三行之和（口径见 8.6）
2.7 语义槽预填只在该行**无手工值**时生效（persist-first，同宿主种子化范式）；槽 `found=False` 时该行保持空白而**不写 0**

### Requirement 3: 公式预设对齐与补齐

**User Story:** 作为审计师，我要在公式管理页看到的 E 类预设都指向真实存在的 sheet、且每张能从四表取数的底稿都有预设，以便逐格追溯取数口径。

#### Acceptance Criteria

3.1 E0 预设块的 `sheet` 必须改为源 xlsx 真实 tab 名 `函证结果汇总表E0-1`，`wp_name` 改为 `函证结果汇总表`
3.2 必须为 E1-6 / E1-10 / E1-21 / E1-22 / E1-23 补预设块，取数口径与 render 一致
3.3 四表推不出的 sheet 必须**显式登记为无预设**并写明理由（≥15 字），而不是留空。**实测清单**：E1 侧 `调整分录汇总E1-5` / `库存现金（人民币）盘点表E1-7` / `库存现金（外币）盘点表E1-8` / `银行存单盘点表E1-9` / `银行账户情况承诺E1-11` / `企业信用报告信息查询记录E1-18` / `企业信用报告信息与账面核对记录E1-19`（**7 张**）+ E0 侧 `核实被函证单位信息E0-2` ~ `函证程序舞弊风险评价表E0-8`（**7 张**）
3.4 新增预设的 `sheet` 字面必须与源 xlsx tab 名逐字一致（openpyxl 直读比对）
3.5 明细表预设**禁引用审定表**（防成环）；审定表可用 `WP()` 引用明细表
3.6 预设修订必须由幂等脚本落地，`--check` 归零且二次 `--apply` 文件 md5 不变
3.7 **🔴 `银行存款及其他货币资金明细表(仅人民币)E1-3` 无预设** —— 只有 `(人民币及外币)E1-3` 有（4 cells）。两张是同 wp_code 的两个 variant、都是真实数据录入表 ⇒ 必须为 `仅人民币` 版补预设块（口径同 multi 版但不含原币/汇率格），否则用户选该 variant 时公式管理页全空
3.8 **🔴 覆盖面判据必须排除非数据表** —— `底稿目录`（5 个 workbook 各 1 张）与程序表（`货币资金实质性程序表E1A` / `货币资金实质性程序表E26A` / `函证程序表E0A`）天然无取数预设。判据若按「每个 visible sheet」会往登记表塞 8 条噪声、淹没真实信号 ⇒ 排除规则必须是**按类型的显式白名单**（目录页 + `*A` 程序表）并配「白名单实际命中数 == 8」的存在性自检，防白名单退化成逃逸阀
3.9 判据只覆盖 **visible** sheet；E0 workbook 的 11 张 hidden sheet（含 `函证结果汇总表E0-1（原）` / `(备份)` / `银行函证其他信息核对表E0-5` / `邮件传真回函核对记录F1-12`）已由 `wp_code_overrides` 标 `skip`，不进覆盖面。**🔴 hidden 的 `银行函证其他信息核对表E0-5` 与 visible 的 `应付银行承兑汇票发函记录表E0-5` 同尾码** ⇒ 预设 sheet 名比对一律用**全名**、禁按尾码匹配（平台既有 skip 消歧就靠全名条目）
3.10 **🔴 覆盖面必须按 sheet **名去重**后统计，不能按「每 workbook 每 sheet」计数** —— `底稿目录` 在 5 个 workbook 各有一张、名字相同，而预设块与登记表都是**按名索引**的 ⇒ 两种口径差 4。实测（2026-08-08，openpyxl 直读 `backend/wp_templates/E/` 5 个 workbook）：visible **出现次数 45 / 去重名 41**、hidden 11、现有预设块 **17**（其中 `审定表E0-1` 是错名不对应任何真实 sheet ⇒ 真实命中 **16**）、白名单**去重名 4**（`底稿目录` + 3 张 `*A` 程序表，出现次数 8）⇒ 缺口 = `41 − 4 − 16 = 21` 张。**21 张的处置分四路**：`函证结果汇总表E0-1` 由 3.1 改名后自动覆盖（1 张）· 3.2 补 5 张 · 3.7 补 1 张 · 3.3 登记 14 张（E1 侧 7 + E0 侧 7）。这五个数字必须在守卫里冻结为基线，配「数值来自实测复算而非预期」注释，只许因源模板变更而更新

### Requirement 4: 幂等脚本控制台输出不得使用非 ASCII 符号

**User Story:** 作为 CI 维护者，我要幂等脚本的退出码反映真实欠账，以便控制台编码问题不会把绿的判成红的。

#### Acceptance Criteria

4.1 `fix_e1_orphan_sheet_presets.py` 的 emoji `✅` 必须换为 ASCII 标记（`[OK]`/`[ERR]`）
4.2 全部 E 类幂等脚本在 GBK 控制台下 `--check` 必须 rc=0（0 欠账时）
4.3 守卫必须扫 E 类幂等脚本源码，禁止能到达控制台的字符串含**在 GBK/CP936 下不可编码**的字符。**🔴 判据是 `s.encode('gbk')` 是否抛 `UnicodeEncodeError`，不是「U+2000 以上非 CJK」** —— 实测 GBK **可**编码 `→`(U+2192) / `≥`(U+2265) / `—`(U+2014) / `─`(U+2500) / `【`(U+3010) / `·`(U+00B7)，**不可**编码 `✅`(U+2705) / `❌`(U+274C) / `⚠`(U+26A0) / `✔`(U+2714) / `✓`(U+2713) / `🔴`(U+1F534) / `░`(U+2591)。按前一种（过宽）口径写会误伤大量安全字符串、制造无谓 churn
4.4 扫描面必须覆盖**间接到达控制台**的字符串 —— 不只 `print(` 的字面参数，还包括 `changes.append(f"…")` 这类被后续 `print` 输出的收集器（`fix_e1_prefill_presets.py` 的变更说明就是这条路径）。docstring 与注释**不进**扫描面（不输出到控制台）
4.5 守卫必须配「中文汉字与 GBK 可编码符号不打红」的正向断言，防判据收得过紧后退化成噪声

### Requirement 5: 附注 soe 八、1 主表对齐源 docx

**User Story:** 作为附注交付件的编制者，我要国企货币资金章节的行集与附注模板 docx 逐字一致，以便交付件不缺行。

#### Acceptance Criteria

5.1 soe 八、1 主表首行标签必须改为 `库存现金`（源 docx r1）
5.2 soe 八、1 主表必须补「其中：存放在境外的款项总额」行（源 docx r6），置于合计行之后
5.3 底稿 soe 披露主表必须新增对应录入行，否则附注该行永无数据源
5.4 底稿 UI 保留源 xlsx 字面 `现金`，推送时按 `noteLabel` 投影为附注字面 `库存现金`（双口径，同「合计行字面」既有范式）
5.5 该行为「其中：」性质，不参与合计（`isMemo`）
5.6 listed 侧行集已与 docx 一致（8 行逐字吻合），**不得改动**
5.7 **soe 主表比 listed 少「存放财务公司款项」与「存款应计利息」两行，这是源 docx 事实、不得对齐** —— soe docx 主表只有 6 行（库存现金 / 银行存款 / 其他货币资金 / 数字货币 / 合  计 / 其中：存放在境外的款项总额）。连带后果：`finance_co` 槽（2.6）在 soe 附注**无落点**，扩槽后 soe 项目即使有该科目也不在附注主表列示 —— 这是准则口径差异，必须登记而非「补齐两版」
5.8 本条改动会打红三条锁定旧行为的既有断言（`E1_MAIN_ROWS_SOE` `toHaveLength(5)` / `sourceRef` 序列 `['A8'..'A12']` / `E1_MAIN_ROWS_SOE.some(r => r.key === 'overseas') === false`，后者注释写「国企版源 xlsx R13 是括注文字，不是数据行」）。必须**诚实改写**并在用例注释写明裁决依据：**附注行集真源是 docx 不是底稿 xlsx**，源 xlsx R13 的括注对应 docx 的正式数据行 r6

### Requirement 6: 受限表补齐第 6 类

**User Story:** 作为附注交付件的编制者，我要受限制货币资金明细覆盖源 docx 全部 6 类，以便金融企业口径也能列示。

#### Acceptance Criteria

6.1 两版受限表必须补「金融企业法定存款准备金或备付金」行，依据 = **soe 源 docx 受限表 r6**（该表在 soe docx 是 7×3，r1~r6 为六类，前 5 类顺序与模板现状逐字一致 ⇒ 只需在合计行前插一行、**不需重排**）
6.2 后端 `E1_RESTRICTED_BUCKETS` 必须新增对应桶，中文标签逐字取自源 docx 并带 `source_ref`
6.3 新桶的关键词不得与既有桶产生抢夺；声明位置必须使既有 6 项目的自动分类结果**逐条不变**
6.4 受限表保留合计行（源 docx 无，但校验预设 F1-4 要求「合计 = 各明细行之和」），该偏离必须在 guidance 写明依据
6.5 前端桶中文名仍只从后端 `bucketDefs` 取，不得抄第二份
6.6 **🔴 listed 侧受限表在源 docx 里不存在** —— listed「货币资金」标题下只有 1 张 9×3 主表，受限内容是两段文字（「期末，本公司不存在抵押、质押或冻结、或存放在境外且资金汇回受到限制的款项。」+ 披露要求括注）。故 listed 的受限表是**平台补充表**（前序 spec 按用户裁决补建、两版同构）⇒ 给 listed 补第 6 类的依据是「镜像 soe + 金融企业客户适用」而**非 listed docx**，必须在 guidance 与守卫注释里显式登记为有意偏离，并**禁止**把 listed 侧写成「与 listed docx 三向一致」（那条断言不可能成立）
6.7 **🔴 展示序必须与优先级序分离** —— `E1_RESTRICTED_BUCKETS` 的声明顺序是**匹配优先级**（信用证先于银行承兑、境外先于质押，含包含关系者必须先声明），而 docx/模板的**行序**是 银行承兑→信用证→履约→担保定期→境外→法定准备金，两者在 4 个位置不同（1↔2、4↔5 互换）。当前推送侧按 `bucketDefs` 数组索引排序 ⇒ **附注行序与 docx 不符**（既有守卫用例标题 `行序按后端 bucketDefs 声明顺序（与源模板行序一致）` 所声称的等价关系不成立，该标题本身即错）。必须引入独立展示序 —— **可由既有 `source_ref` 的单元格行号派生**（现值 `A17`/`A18`/`A19`/`A20`/`A21` 恰好就是 docx 行序），无需新增字段；并双向锁死「改优先级不影响展示序 / 改展示序不影响分类结果」
6.8 平台补充桶 `other`（其他受限资金，`source_ref=None`）在 docx 与模板行集里**都没有对应行** ⇒ 行序契约必须表述为「docx 六类（按 docx 序）+ 平台补充桶（排在六类之后）+ 合计行」，不得写成「== docx r1~r6」（那会把正确实现打红）
6.9 上述展示序改动必须**诚实改写**既有守卫用例（含其标题），不得为了让旧断言继续绿而保留错行序

### Requirement 7: 外币章节段 row_code 纠正

**User Story:** 作为跨循环共享表的维护者，我要段首行的 report_row_code 与 report_config 对账一致，以便段级合并既不错配也不整表跳过。

#### Acceptance Criteria

7.1 `note_template_soe.json` 八、92「短期借款」段首行 `report_row_code` 必须由 `BS-031` 改为 `BS-041`
7.2 `account_codes:['2001']` 保持不变（本来就是对的）
7.3 `e1FxNoteSectionMap.ts` 的段归属注释表必须同步改正
7.4 派生清单 `note_shared_table_segments.json` 必须重生成
7.5 守卫必须断言「外币表每个段首行的 `report_row_code` 在 `report_config` 里的 `row_name` 与段 `label` 语义一致」，并对 `BS-031→使用权资产` 这类错配打红
7.6 必须反向锁死「`BS-031` 仍归 H8 使用权资产」（防日后把 H8 的码改成 BS-041）

### Requirement 8: 披露逻辑忠实源模板取数链路

**User Story:** 作为审计师，我要披露表三张表的取数能追溯到源模板声明的上游底稿、受限明细能追溯到具体账户，以便复核时逐笔可查。

#### Acceptance Criteria

8.1 受限表必须同时支持两条取数链路：四表叶子按科目名自动分类（现状）+ **E1-3 逐户的「受限金额/受限原因」列归集**（源模板 soe 受限表的 SUMIF 口径）
8.2 两条链路结果不一致时在勾稽面板如实暴露差异，**不自动取其一**
8.3 E1-3 的「账户性质/主要用途」列（源模板 D 列）在其他货币资金段承载受限类别，取数时作为分类依据之一
8.4 受限「待归类」面板必须把「该科目无子科目明细」的父科目行与真正待判断的明细行**视觉区分**
8.5 银行存款期末为负（如 −297,771,168.89）时必须如实显示并给异常提示，不得取绝对值
8.6 主表「存款应计利息」行的取数口径必须与源模板一致（审定表应计利息三行之和），且在 guidance 写明「不属于现金及现金等价物」。docx 提示原文三条：①指基于实际利率法计提的应计但未到付息期的银行存款利息；②不包括已到期可收取但资产负债表日尚未收到的利息（逾期未收利息列示于「应收利息」）；③这部分利息不属于「现金及现金等价物」。**该行只在 listed 主表存在**（soe docx 无此行，见 5.7）
8.7 **🔴 L2 逐户归集的「受限原因」不得进 ②表列** —— 既有契约钉死②表只 3 列（`label`/`end_amount`/`prior_amount`，源模板即 3 列），受限事由走 `_note_texts` 文字说明段。L2 归集出的原因文本必须并入该文字段（去重后拼接），推列会打红既有断言 `colKeys == ['label','end_amount','prior_amount']`
8.8 **L2 链路的数据源是审计师在 E1-3 手填的 `restrictedAmount`/`restrictedReason`（源模板 AJ/AK 列，两字段已在 `USER_FIELDS` 里），不是账户级取数** —— `tb_aux_balance` **没有受限金额字段** ⇒ L2 依赖「E1-3 行已持久化」而非依赖 R1；R1 只是让 E1-3 有账户行可填（UX 前提，非数据依赖）

### Requirement 9: 动态插行区在底稿侧可达且推送正确

**User Story:** 作为审计师，我要在源模板留了可扩行的区域（受限类别、外币币种）能增删行并正确推进附注，以便不同客户的实际情况都能列示。

#### Acceptance Criteria

9.1 受限表的自定义类别能力（`customBucketKey`）必须有可达 UI 入口，新增前用 `ElMessageBox.prompt` 要求输入类别名
9.2 自定义类别行 key 必须稳定且**不复用已删序号**（需持久化单调计数器）
9.3 外币段推送必须保持「不写死币种表」（按底稿实际出现的币种动态产出）
9.4 受限表为空数组时不推空表且进 `_removed_table_keys`；`undefined` 时跳过且不进（条件表语义）
9.5 附注模板侧的 `expandable` 语义**归 C spec R11，本 spec 不改 `row_type` 取值域**

### Requirement 10: 守卫、CI 与真实库验收

**User Story:** 作为质量控制复核人，我要每处改动都有连库守卫、变异检验与真实库验收，以便结论可信而非「测试全绿但功能是死的」。

#### Acceptance Criteria

10.1 账户级取数必须有**真实库连库守卫**：至少 1 个项目命中账户级数据，且 aux 合计与 `tb_balance` 叶子勾稽成立
10.2 连库守卫必须用一次 `asyncio.run` + 专用 `NullPool` 引擎，禁借共享池（防污染其它连库测试）
10.3 附注结构改动必须由幂等脚本落地并配 openpyxl/python-docx 直读源 docx 的三向比对守卫
10.4 每个新守卫必须做变异检验并逐条打红，变异按「失败测试名集合差集」判定（不看退出码）
10.5 零回归必须双证：既有 132 个 E1 守卫全绿 + 未触碰模块的失败集合逐条相同
10.6 CI 必须新增 E 类 job（后端 + 前端各一），引用的文件必须全部存在
10.7 真实库验收脚本只读、默认 dry-run，无法验证时如实输出 `UNVERIFIABLE` 而不用 fixture 冒充
10.8 **🔴 `get_active_filter` 是 `async` 函数**（真实签名 `async def get_active_filter(db, table, project_id, year, *, force_dataset_id=None, current_user_id=None)`，模块 `app.services.dataset_query`）。漏 `await` 会让 `sa.and_(coroutine, ...)` 抛异常 → 被 fail-open 吞成 warning → 账户级清单恒空，与「本项目无 aux 数据」不可区分。该缺陷在 N5 与 D 循环各发生过一次（均为 P0）⇒ 守卫必须含**源码级断言**「`get_active_filter(` 前必须紧邻 `await`」+ 反向自检（去掉 `await` 必红）
10.9 守卫本身的判据必须落在**函数体内**而非「文件内出现」（用花括号/圆括号配对截函数体；`extractFunctionBody` 类实现要先跳过参数列表与内联返回类型注解，否则截到的是类型字面量）

### Requirement 11: 零回归红线

**User Story:** 作为平台维护者，我要已通的取数链路与既有数据契约不被改动，以便本次收口不打断其它循环与存量项目。

#### Acceptance Criteria

11.1 已通的科目定位链路（`e_cycle_specs` 5 槽、`resolve_semantic_accounts` 优先级）**不得改动**
11.2 既有跨 sheet 聚合键 `E1-adj-total-1001/1002/1012` 形态不得改（跨 spec 数据契约，后端 `wp_formula.py` 在引用）
11.3 既有明细种子键 `E1-cash-detail-rows` / `E1-bank-detail-rows` / `E1-account-list-rows` 不得改名
11.4 listed 五、1 与两版外币表的行集/列集不得改动
11.5 受限桶既有 6 项目的自动分类结果必须逐条不变（新增桶不得抢夺）
11.6 `_DETAIL_SLOT_KEYS` 扩槽后既有三槽的明细行字段与顺序不得变

## 范围外

- 附注模板 `row_type` 新增 `expandable` 取值 —— 归 `note-template-columns-and-legacy-snapshot-closure` R11
- 外币表扩列（底稿侧 7 列含期初 → 附注侧 4 列仅期末）—— 会波及 D2/K/L，需平台级 spec
- E0 函证模块的结构性改造 —— 归已归档的 `e0-confirmation-completion` 与未开工的 `e0-send-list-dedicated-components`
- E1 孤儿组件接线 —— 归 `e1-orphan-components-wiring`
- `trial_balance` 父子双算修正 —— 平台级缺陷，E1 已用叶子口径规避
- 银行账户完整性三方比对（四表 ∪ 央行清单 OCR ∪ E0-3 回函）—— 数据源涉及 OCR，够独立 spec
- 存量项目的附注数据迁移 —— 附注模板改动只对新建项目/重新生成生效，不做破坏性回填
