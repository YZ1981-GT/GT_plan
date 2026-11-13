# 设计文档：S9　利润表净利润以下行的公式补全（income-statement-lower-section-formulas）

> 需求编号：requirements §1 三条记 R1（净利润以下各行补公式）、R2（归属行的组成行有值）、R3（组成行未定义以 warning 可见之后的补全）；§4 的综合收益总额合计行问题记 R4。
> 现状基线：分支 HEAD `4c0a1e0a6` + 母 spec 整合树 `tmp_fhic/integ`（`d91f5f804`，含 ADR-FHIC-05 逐行计算、ADR-FHIC-23 归属行种子与合计行守卫）。数字为 2026-10-29 共享库只读现算。

## 0. 结论

只补「净利润以下」得不到对的数：净利润的上游本身是坏的 —— 国企两套「营业利润」「营业总成本」没有公式，「利润总额」三套写错（把营业外收入、政府补助、营业外支出直接相加），投资收益、公允价值变动、信用减值、资产减值、资产处置五个叶子行没有取数。所以本设计把范围定为**整条利润链**（§4 D1，默认采纳）：叶子行取数 → 营业总成本 → 营业利润 → 利润总额 → 净利润 → 其他综合收益 → 综合收益总额，归属行沿用母 spec。国企利润表的小计行排在明细行之前（营业总成本、其他综合收益两段），按行号顺序求值必然遇到「引用行未就绪」，所以求值顺序要改成依赖拓扑序；这一项原在 S1，建议移到本 spec（§4 D2）。另有两条外部前提必须告知用户：①活项目的试算表与报表是旧代码算出、之后没再重算的陈旧结果（华氏营业收入把三级科目全部相加再取负，约为实际的 3 倍；和平药房报表营业收入 = −(2 × 一级 + 三级)），现行代码重算出的是自然正数，所以补完公式后要先按 §4 D3 重算试算表再重新生成，否则利润的量级和符号都是错的；修法是已有工具的运维动作，不需要另立 spec。②手工输入行（少数股东损益、其他综合收益明细等）在重新生成时会被写成 0。

## 1. 现状复核

| # | 交接结论 | 现算 | 判定 |
|---|---|---|---|
| 1 | R1：国企 IS-046 / 048 / 049 / 053 / 054 / 072 无公式 | 成立；国企两套 IS-046~072 只有 IS-073 有公式 | 成立 |
| 2 | R1：上市 IS-029~032 / 049 无公式 | 成立；**另漏列 IS-024「四、净利润」**（同样无公式），以及 IS-026（持续经营净利润）、IS-033 / IS-039（两个小计） | 交接清单不全 |
| 3 | R2：归属行组成行全为 0 | 活项目 5 个（全部 `soe_standalone`）IS-046 以下全为 0；IS-074 / IS-075 非零是因为旧公式 `SUM_ROW('IS-001','IS-073')` 把整张表加在一起（母 spec X2 待执行） | 成立 |
| 4 | R4：综合收益总额只加其他综合收益一段 | 国企 IS-073 = `SUM_ROW('IS-054','IS-072')`、上市 IS-050 = `SUM_ROW('IS-032','IS-049')`：不含净利润，且区间同时含小计行与它的明细行（明细一旦有值就重复计算） | 成立，且多一个重复计算 |
| 5 | （交接未列）上游利润链 | 国企两套 IS-007「营业总成本」、IS-040「营业利润」无公式；IS-044「利润总额」：合并 `SUM_ROW('IS-041','IS-043')`（营业外收入 + 政府补助 + 营业外支出），单体 `ROW('IS-040')+ROW('IS-041')-ROW('IS-043')`（形状对，但 IS-040 为空）；上市两套 IS-019「营业利润」无公式，IS-022「利润总额」= `SUM_ROW('IS-020','IS-021')`（营业外收入 + 营业外支出）。四套利润表有公式的行：国企 16/78、上市 15/55 | 新增：净利润的上游是错的 |
| 6 | （交接未列）叶子行取数 | 投资收益（6111）、公允价值变动收益（6101）、信用减值损失（6702）、资产减值损失（6701）、资产处置收益（6115）四套都没有公式；华氏 2025 试算表 6111 审定 69,414,915.44、6702 审定 65,472,778.72，报表上这些行为 0 | 新增 |
| 7 | （交接未列）生成器特殊公式表 | `report_formula_service` 利润表特殊表里有 5 条映射到错误科目：「其他综合收益的税后净额」→ `TB('3102')`（活项目其他综合收益科目码是 4003）、「综合收益总额」→ `TB('6801')`（所得税费用）、「汇兑收益」→ `TB('6603')`（财务费用）、「基本 / 稀释每股收益」→ `TB('6901' / '6902')`；「信用减值损失」「资产减值损失」映射不带负号，与「损失以“－”号填列」的列报相反。`fill_all_formulas` 只填公式为空的行，这些行现在为空 ⇒ 是潜在写入方 | 新增 |
| 8 | （交接未列）求值顺序 | 单体三路按行号求值，母 spec 的逐行计算对「引用了排在后面且有公式的行」报「引用行未就绪」；合并路径 `consol_report_values.ordered_rows` 同样按「报表类型 → 行号」排序；母 spec 守卫 `test_report_row_ref_order_guard.py` 把一切前向引用（不论被引用行有无公式）冻结为 0。国企利润表「二、营业总成本」（IS-007）在其明细 IS-008~025 之前，「六、其他综合收益的税后净额」（IS-053）在其明细之前 | 新增：需要拓扑序 |
| 9 | （交接未列）试算表符号口径 | 活项目报表营业收入 4/5 为负（华氏 IS-001 = −20,283,811,823.52）。原因不在现行口径：现行 `TrialBalanceService.recalc_unadjusted` 只汇总叶子科目，损益类取单边发生额、贷方类科目取绝对值，算出的是自然正数（`CURRENT_SIGN_CONVENTION = v2_category_natural_positive`，spec `ledger-sign-convention-unify`），与报表公式的正数口径一致。真库这些值是旧代码算出、之后没再重算的陈旧结果：华氏试算表 6001 = −(一级 6,798,732,711.94 + 二级 6,798,732,711.94 + 三级 6,686,346,399.64)，即三级全加再取负；和平药房试算表 6001 = 520,711,448.85（与一级相符），报表 IS-001 却是 −1,044,179,479.82 = −(2 × 520,711,448.85 + 2,756,582.12)，报表 2026-05-25 生成后没再重算。另外 8 个有试算表的真实项目，余额表 `tb_balance.sign_convention_version` 全部为空（v1，共 5,890 行），口径检查 `sign_convention_guard.check_sign_convention_readiness` 会提示先跑迁移脚本。已有工具：符号迁移 `backend/scripts/migrate/migrate_sign_convention_v2.py`（按项目 + 年度，`--dry-run`、`--recalc-trial-balance` 迁移后全量重算试算表、`--rollback --batch-id`），共享库从未执行（备份表 `_sign_migration_backup` 0 行）；类别更正 `migrate_account_category_correction.py`（`--dry-run` / `--commit` / `--rollback`），2026-06-11 在共享库执行过一次（批次 `11ddbb5a`，科目表 129 行、试算表 20 行） | 新增：外部前提；修法是运维，不是新 spec（§4 D3） |
| 10 | （交接未列）无公式行的写入 | `_generate_report` 对无公式行写 0（母 spec ADR-FHIC-01 现读）；报表格手工改值在重新生成时被覆盖，属 `excel-style-table-editing` 的待拍板项 | 新增：手工输入行存不住 |
| 11 | 合并路径 | 合并报表按 `{模板}_consolidated` 的公式逐行求值（`consol_report_values`），公式须线性（`±ROW`、`±TB`、`SUM_ROW`、乘除常数）才能按列分解；少数股东损益 / 少数股东权益在 `REPORT_ONLY_SUBJECTS` 里，科目表没有对应科目 | 本设计的公式全部线性；少数股东两行只能是输入行 |
| 12a | 实施期追加（2026-11-01，任务 0）：种子利润表行数与有公式行数 | 国企两套各 78 行、上市两套各 55 行；实施前有公式的行只有归属行（soe_consolidated 2、soe_standalone 1、listed_consolidated 2、listed_standalone 1，全部来自母 spec ADR-FHIC-23 的种子）。基线产物 `tmp_is_lower_section/baseline/seed_rows.json` + `row_map.txt` | 成立 |
| 12b | 实施期追加（2026-11-01，任务 1）：权威模板逐行核对 | 四版模板的利润表 sheet（国企 `3-利润表（企财02表）`、上市 `利润表`）用 openpyxl 逐行读 A 列行名 + C 列公式，核对表 `tmp_is_lower_section/format_check.md`。§2 与模板**不符一处**：国企 IS-007 营业总成本，详见 §2 勘误 ① | §2 已回改 |
| 12c | 实施期追加（2026-11-01，任务 3）：特殊公式表与种子口径打架的行名 | design §1 第 7 行登记了 5 条错误映射；同源守卫现场另抓出 **4 条**（「营业总成本」与模板恒等式口径并存；「利息费用」「利息收入」各自映到财务费用 6603 全额；「以摊余成本计量的金融资产终止确认收益」映到投资收益 6111 全额）⇒ ADR-ISL-04 的删除清单从 5 条扩到 9 条 | 交接清单不全 |
| 12 | （交接未列）科目类别 | 旧的一刀切前缀映射（6 → expense、4 → revenue，见类别更正脚本的文档字符串）留下的错类别仍在：和平药房、医疗器械的科目表与试算表都把 6001 营业收入记为 expense，和平药房另把 4104 利润分配记为 revenue；宜宾科目表同样错、试算表已对；华氏这几个科目已对（2026-06-11 那次更正）。`recalc_unadjusted` 只在新建行时写类别，不更新已有行。利润表公式按科目码取数，不受影响；按类别汇总的重要性水平基数、一致性门禁、数据校验受影响。注意 `backend/data/standard_account_chart.json` 是旧科目体系（4001 = 生产成本），不能拿来判类别对错 | 新增：不在本 spec 范围，与 §4 D3 同批运维 |

## 2. 公式权威文本（本表是四套利润表这些行的唯一定义）

行分三类：**恒等行**（同表其他行的加减）、**取数行**（`TB` 取试算表）、**输入行**（试算表没有来源，不写公式，由手工或合并模块给值）。加减号按国企、上市两版官方报表格式逐行核对后再落种子（任务 1 的第一步），核对结论写进任务记录；本表与官方格式不符处以官方格式为准并回改本表。

**国企两套（`soe_consolidated` / `soe_standalone`，行次相同）**

| 行次 | 行名 | 公式（单体不同时括注） |
|---|---|---|
| IS-007 | 二、营业总成本 | `ROW('IS-008')+…+ROW('IS-025')+ROW('IS-029')`（IS-008~IS-025 全部为加项，再加 IS-029；IS-026~028 是财务费用的「其中」，不加）—— 见下方勘误 ① |
| IS-031 | 投资收益 | `TB('6111','本期发生额')` |
| IS-036 | 公允价值变动收益 | `TB('6101','本期发生额')` |
| IS-037 | 信用减值损失 | `-TB('6702','本期发生额')` |
| IS-038 | 资产减值损失 | `-TB('6701','本期发生额')` |
| IS-039 | 资产处置收益 | `TB('6115','本期发生额')` |
| IS-040 | 三、营业利润 | `ROW('IS-001')-ROW('IS-007')+ROW('IS-030')+ROW('IS-031')+ROW('IS-034')+ROW('IS-035')+ROW('IS-036')+ROW('IS-037')+ROW('IS-038')+ROW('IS-039')`（IS-032 / 033 是投资收益的「其中」，不加） |
| IS-044 | 四、利润总额 | `ROW('IS-040')+ROW('IS-041')-ROW('IS-043')`（IS-042 是「其中：政府补助」，不加） |
| IS-046 | 五、净利润 | `ROW('IS-044')-ROW('IS-045')` |
| IS-048 | 1.归属于母公司所有者的净利润 | `ROW('IS-046')-ROW('IS-049')`（单体 `ROW('IS-046')`） |
| IS-051 | 1.持续经营净利润 | `ROW('IS-046')-ROW('IS-052')` |
| IS-053 | 六、其他综合收益的税后净额 | `ROW('IS-054')+ROW('IS-072')`（单体 `ROW('IS-054')`） |
| IS-054 | 归属于母公司所有者的其他综合收益的税后净额 | `ROW('IS-055')+ROW('IS-062')` |
| IS-055 | （一）不能重分类进损益的其他综合收益 | `SUM_ROW('IS-056','IS-061')` |
| IS-062 | （二）将重分类进损益的其他综合收益 | `SUM_ROW('IS-063','IS-071')` |
| IS-073 | 七、综合收益总额 | `ROW('IS-046')+ROW('IS-053')` |
| IS-074 / IS-075 | 归属行 | 母 spec 需求 6.1，不改 |

输入行：IS-003~006、IS-009~020（金融企业专用的 △▲ 项）、IS-026~029、IS-032~035、IS-042、IS-049、IS-052、IS-056~061、IS-063~072、IS-076~078（每股收益）。

**上市两套（`listed_consolidated` / `listed_standalone`，行次相同）**

| 行次 | 行名 | 公式（单体不同时括注） |
|---|---|---|
| IS-011 | 投资收益 | `TB('6111','本期发生额')` |
| IS-015 | 公允价值变动收益 | `TB('6101','本期发生额')` |
| IS-016 | 信用减值损失 | `-TB('6702','本期发生额')` |
| IS-017 | 资产减值损失 | `-TB('6701','本期发生额')` |
| IS-018 | 资产处置收益 | `TB('6115','本期发生额')` |
| IS-019 | 二、营业利润 | `ROW('IS-001')-ROW('IS-002')-ROW('IS-003')-ROW('IS-004')-ROW('IS-005')-ROW('IS-006')-ROW('IS-007')+ROW('IS-010')+ROW('IS-011')+ROW('IS-014')+ROW('IS-015')+ROW('IS-016')+ROW('IS-017')+ROW('IS-018')` |
| IS-022 | 三、利润总额 | `ROW('IS-019')+ROW('IS-020')-ROW('IS-021')` |
| IS-024 | 四、净利润 | `ROW('IS-022')-ROW('IS-023')` |
| IS-026 | 其中：持续经营净利润 | `ROW('IS-024')-ROW('IS-027')` |
| IS-029 | 其中：归属于母公司股东的净利润 | `ROW('IS-024')-ROW('IS-030')`（单体 `ROW('IS-024')`） |
| IS-031 | 五、其他综合收益的税后净额 | `ROW('IS-032')+ROW('IS-049')`（单体 `ROW('IS-032')`） |
| IS-032 | 归属于母公司股东的其他综合收益的税后净额 | `ROW('IS-033')+ROW('IS-039')` |
| IS-033 | （一）不能重分类进损益的其他综合收益 | `SUM_ROW('IS-034','IS-038')` |
| IS-039 | （二）将重分类进损益的其他综合收益 | `SUM_ROW('IS-040','IS-048')` |
| IS-050 | 六、综合收益总额 | `ROW('IS-024')+ROW('IS-031')` |
| IS-051 / IS-052 | 归属行 | 母 spec 需求 6.1，不改 |

输入行：IS-008 / 009、IS-012~014、IS-027、IS-030、IS-034~038、IS-040~049、IS-053~055。

**勘误 ①（2026-11-01，任务 1 按权威模板回改本表）** —— 国企 IS-007「二、营业总成本」：

- 本表初版写成 `+IS-008…+IS-012 −IS-013 +IS-014 −IS-015 +IS-016…+IS-025`，且注明「IS-026~029 是财务费用的『其中』，不加」。
- 权威模板现读：`soe_consolidated` 的 `3-利润表（企财02表）!C12 = SUM(C13:C30)+C34`、`soe_standalone!C11 = SUM(C12:C29)+C33`。
  按模板行 → 行次映射（合并版 C13=IS-008 … C30=IS-025、C31~C33=IS-026~028、C34=IS-029），即
  **IS-008~IS-025 全部为加项，再加 IS-029**。
- 两处不符：① IS-013「△减：摊回保险服务费用」与 IS-015「△减：分出再保险财务收益」在模板里是 `SUM` 的加项
  —— 行名带「减：」由用户按负数填列（金融类专用输入行），公式里再减一次就是双重变号；
  ② IS-029「其他」不是财务费用的「其中」项（IS-026~028 才是），它与 IS-021~IS-025 同级、模板显式 `+C34`，初版漏加。
- 本表已按模板回改；守卫 `test_soe_total_cost_covers_all_detail_rows` 逐加项断言非零后比对（变异 M10 验证）。

恒等检查（由公式推得，测试逐条断言）：合并口径「归母综合收益 + 少数综合收益 = 综合收益总额」、单体口径「归母综合收益 = 综合收益总额」；「营业利润 + 营业外收入 − 营业外支出 − 所得税 = 净利润」。符号按平台正数口径（收入、利得为正，费用、损失为正数存于试算表，列报为负的损失行取负号），与现有 `TB('6001')`、`TB('6601')` 写法一致。

## 3. 架构裁定

**ADR-ISL-01 求值顺序 = 依赖拓扑序（§4 D2）。** 新模块 `backend/app/services/report_eval_order.py`：`eval_order(rows) -> EvalOrder(order, cycles)`，按 `ROW` / `SUM_ROW`（区间按与求值同一口径展开）建依赖图，Kahn 算法，入度相同按「报表类型序 → 行号 → 行次」稳定排序；环上的行进 `cycles`，计算时失败「循环引用：…」。母 spec 的单体三路（`_generate_report`、`regenerate_affected`、`recalculate_stale_rows`）与合并路径 `consol_report_values.ordered_rows` 都改调它。`report_row_compute._not_ready` 的「排在后面」判据随之变为「依赖未算完」。母 spec 守卫 `test_report_row_ref_order_guard.py` 的「前向 = 0」改为「环 = 0、悬空 = 0、跨表规则不变」，并保留它的违规样本自检；本条改的是母 spec 已交付的守卫判据，按 append-only 在本 spec 登记勘误，不改母 spec 文档。

**ADR-ISL-02 输入行显式登记，提示改写。** 输入行在 `report_config` 写 `formula_source='input'`（公式为空）。母 spec 逐行计算对「`ROW` 引用无公式行」给的提示「组成行 … 未定义公式」改为：被引用行 `formula_source='input'` ⇒ 「组成行 … 为手工输入行」；其余无公式行保持原文案。手工输入行在重新生成时被写成 0 的问题不在本 spec 解决（§1 第 10 行，归 `excel-style-table-editing` 的待拍板项），提示文案注明「重新生成会清零」直到那边拍板。

**ADR-ISL-03 种子 + 经同步内核发布存量。** 四套种子 `backend/data/report_config_seed.json` 按 §2 写入公式与 `formula_source`（恒等行 `identity`、取数行 `special`、输入行 `input`）。存量库用正式工具 `backend/scripts/fix/publish_income_statement_chain.py`（沿用母 spec `republish_report_seed_rows.py` 的做法）：默认只读，逐行列出旧公式 / 旧来源、目标公式 / 目标来源与动作；`--apply` 只改安全状态：空公式、7 条已知坏式（§1 第 4、5 行）、公式正确但来源是安全旧值、空公式且来源为空的输入行登记；任何已有公式 / 未登记来源均判第三种定义，列出、不改、退出码 2。目标逐行取种子，不在工具里复制公式或输入行清单；经 `publish_global(source="seed")` 发布（有本项目适配的项目进待确认，执行定义变化才按母 spec ADR-04 标过期），可重复执行（第二次 0 变更）。归属行 8 行仍由母 spec 的 X2 工具处理，本工具不碰。

**ADR-ISL-04 生成器特殊公式表与本表同源。** 删除 §1 第 7 行的 5 条错误映射；实施期同源守卫另抓出 4 条双口径 / 子项冒充父项映射，共删除 9 条（详 §3.1）；「信用减值损失」「资产减值损失」改为带负号。守卫 `test_income_statement_formula_single_source.py`：对四套利润表，`fill_all_formulas` 的策略 1~5 对 §2 涉及的每个行名产生的公式要么为空、要么与 §2 逐字相等；`formula_source='input'` 的行不得被任何策略编公式。

**ADR-ISL-05 试算表陈旧只提示（§4 D3）。** 不改试算表数据、不改公式。报表生成时检查两项，任一成立就在利润表结果追加 warning「试算表是按旧口径算出的，利润表各行的金额和符号可能不对，请先全量重算试算表再生成报表」：①`check_sign_convention_readiness` 报余额表含 v1 行；②SQL 先以 `account_category in {revenue, expense}` 缩小损益范围，再按 `resolve_account_direction(code, name)` 判贷方方向，审定数为负则提示（这样历史上误标为 expense 的 6001 仍能检出）。两项查询分别放 SAVEPOINT，查询失败回滚到保存点后只记日志，不毒化外层报表生成事务。warning 经 `/api/reports/generate` 的 `warnings` 字段回传，前端报表页用 warning toast 展示；行级 formula / 悬空提示不在生成 toast 重复轰炸。数据修复按 §4 D3 由用户决定，本 spec 不执行。

### 3.1 实施勘误与落点（2026-11-01）

**ADR-ISL-01 落点与母 spec 守卫判据勘误。** 新模块 `backend/app/services/report_eval_order.py`：
`eval_order(rows) -> EvalOrder(order, cycles)`（Kahn + Tarjan 求环，入度相同按「报表类型序 → 行号 → 行次」稳定排序）、
`plan_for_configs`（生产入口：行次重复等结构问题降级为行号序并记告警，不让报表生成整体失败）、
`order_within_type`（把一张表的行按全局拓扑位置排序）。接入点四处：`ReportEngine._generate_report`、
`recalculate_stale_rows`、`regenerate_affected`、`consol_report_values.ordered_rows`。

- 🔴 **拓扑序只改求值顺序，不改展示顺序**：`_generate_report` 原先按行号迭代并把行 dict 顺序返回给前端与缓存，
  直接改迭代顺序会把报表显示顺序一起改掉。实施改为「带行号收集 → 返回前按行号重排」。
- 🔴 **母 spec 守卫 `test_report_row_ref_order_guard.py` 的判据由「前向 = 0」改为「环 = 0」**（本 spec 范围内的
  判据变更，母 spec 文档 append-only 不改）：拓扑序下「小计行引用排在后面的明细行」本就是国企利润表 IS-007 / IS-053
  的真实排版，是合法的；真正算不出来的只有循环引用。悬空、跨表、未识别、结构四条判据不变；环的判定在守卫里
  独立实现（逐节点 DFS 判「能否回到自身」），与生产 Tarjan 互为对照；不能用「摘入度 / 出度 0」法，
  两个环之间的单向路径节点也会一直有入边和出边，却不在任何环上。守卫自检样本同步调整：原 `row_forward` / `row_self` / `sum_forward`
  三条改为 `cycle_self` / `cycle_pair` / `two_cycles_with_bridge` / `cycle_via_range`，并新增 `test_forward_reference_is_legal_under_topological_order`。
- `report_row_compute.compute_row` 对 `scope.cycles` 里的行 **fail-closed**：返回 `state="cycle"`、不求值、不写值、
  从依赖缓存里删除（上一轮的陈旧值也要删）—— 否则引用它的行会读到假数。

**ADR-ISL-02 落点。** `RowScope` 新增 `input_codes`（`formula_source='input'` 的无公式行）与 `cycles` 两个字段
（都有默认值，不破坏既有 `RowScope(codes, formula_less)` 调用）；提示按引用对象二分：引用手工输入行 ⇒
「组成行 … 为手工输入行；重新生成会清零，请确认手工金额后再生成」，其余无公式行保持「组成行 … 未定义公式」。
判定覆盖 `ROW` 与 `SUM_ROW` 区间两种引用形态（`_formula_less_components`）。

**ADR-ISL-04 删除清单由 5 条扩到 9 条**（§1 第 12c 行）：新增「营业总成本」「利息费用」「利息收入」
「以摊余成本计量的金融资产终止确认收益」。前者与权威模板的恒等式口径并存，后三条都是把「其中」子项映到父项科目全额。
同源守卫 `test_income_statement_formula_single_source.py` 的判据是「生成器五条策略对 §2 涉及行名的产出，
要么为空、要么与种子逐字相等」+「`formula_source='input'` 的行不得被任何策略编公式」，9 条删除逐条反向钉死。

**ADR-ISL-05 落点。** 新模块 `backend/app/services/report_tb_staleness.py`，挂在 `generate_all_reports` 的
利润表分支（`type_coverage["warnings"]` 追加一条 `{"type": "stale_trial_balance", "message": …}`，与既有
`dangling_row_ref` 条目同结构）。两项查询分别放 `begin_nested()` SAVEPOINT：PG 任一 SQL 报错只回滚本提示查询，
不会把外层报表生成事务留在 aborted；异常只记日志、不拦生成。贷方方向由 `resolve_account_direction(code, name)` 判，
SQL 同时扫 revenue / expense，保证历史上误标为 expense 的 6001 仍能检出；多 company_code 同一科目去重后提示。
`routers/reports.py::_generation_warnings` 只提取该生成级提示（不重复推逐行告警），API 返回 `warnings`；
`useReportData.onGenerate` 去重后用 `ElMessage.warning` 展示。浏览器证据见 §5.0。
符号约定那项用 PG 专有的 `to_regclass` 探表，SQLite 上跑不了 ⇒ 单测把故障注在**被测函数的下一层**
（替换 `check_sign_convention_readiness`），贷方损益为负那项用真 ORM 落库现查。

## 4. 待用户拍板

| # | 事项 | 建议 |
|---|---|---|
| D1 | 范围：只补净利润以下（交接原文）还是整条利润链 | 整条利润链（§2）；只补下半段时净利润 = 错的利润总额 − 所得税 |
| D2 | 拓扑序求值从 S1 移到本 spec | 移过来；不移则本 spec 等 S1 完成该项后才能实施 |
| D3 | 真实项目试算表 / 报表陈旧（§1 第 9、12 行；活项目报表营业收入 4/5 为负） | 不另立 spec：口径统一已由 `ledger-sign-convention-unify` 交付，缺的是对真实项目跑一遍已有工具（写真实数据，须用户放行，逐项目执行）：①`migrate_account_category_correction.py --dry-run` 核对后 `--commit --operator <admin>`（先更正类别，重算新建的试算表行才拿到对的类别）；②`migrate_sign_convention_v2.py --project <id> --year <年度> --dry-run` 核对后加 `--recalc-trial-balance` 执行（迁移余额表并全量重算试算表；只修试算表数字也可以只做全量重算，但口径检查会一直提示 v1）；③重新生成报表（与母 spec X3 同批）。本 spec 只做 ADR-05 的提示 |
| D4 | 存量发布（ADR-03 工具 `--apply`）与真实项目重新生成 | 在 D3 完成前只发布到全局定义、不重新生成真实项目报表；与母 spec X2、X3 同批决定 |
| D5 | 手工输入行被重新生成清零 | 与 `excel-style-table-editing` 的「报表重新生成覆盖格内改值」一并拍板 |

## 5. 测试与变异

### 5.0 实施结果（2026-11-01）

S9 自有测试 **108 个节点**：本地非 PG **104 passed**，真 PG 外层回滚 **3 passed / 1 xfailed**（完整 `ReportEngine` 因 X1 schema 未执行而诚实 xfail）。

| 文件 | 节点数 | 覆盖 |
|---|---:|---|
| `test_report_eval_order.py` | 11 | `eval_order` 纯函数（无依赖保持行号序、前向引用、`SUM_ROW` 区间展开、跨表、环只报真环成员、自引用、行次重复 fail-closed、类型序与生产一致）+ `compute_row` 环 fail-closed 三例（不求值、清陈旧缓存、阴性对照照常求值） |
| `test_income_statement_formula_single_source.py` | 12 | 生成器五条策略 × 四套 × 种子不矛盾；input 行不得被编公式；9 条删除映射反向钉死；两条减值负号（特殊表 + 种子两侧） |
| `test_income_statement_gold_parity.py` | 22 | 四套恒等检查、合并 / 单体归属加总、减值列报为负、生产 vs 金标准逐行按分、营业总成本逐加项、手工输入提示 |
| `test_gold_is_evaluator_independence.py` | 9 | AST 独立性（禁 import 生产模块、只许标准库）+ 反向变异 + 注释不误报 + 五种生产写法可解析 |
| `test_report_tb_staleness.py` | 11 | 干净 v2 无提示、v1 残留、历史错分 expense 的 6001、同码多公司去重、两项同时命中、费用类为负不误报、项目 / 年度隔离、SQL 失败回保存点后外层事务仍可用 |
| `test_publish_income_statement_chain.py` | 35 | 目标取自种子、归属行跳过、六类动作、7 条已知坏式逐字、input 元数据、只读零写语句、`--apply` 等于目标、幂等、第三种定义阻断、缺行不新增、命令行 |
| `test_report_generation_warning_wire.py` | 4 | 只提取陈旧试算表 warning、去重与坏形状、AST 钉住 `/generate` 回执真实返回该字段 |
| `test_income_statement_pg.py` | 4 | 真 PG 四套逐行 / 合并 / 线性对拍；完整生成 X1 前置；发布工具 apply + 重放；第三种定义阻断（全部外层回滚） |

母 spec 报表守卫同步绿：`test_report_row_ref_order_guard.py`（新判据）、`test_report_formula_generator_guard.py`、
`test_report_seed_attribution_rows.py`。

### 5.1 磁盘变异（13 条全部打红）

脚本 `tmp_is_lower_section/mutate.py`：逐条注入 → 跑指定用例 → 必须红 → 逐字节还原 + sha256 核对。

| 编号 | 注入的缺陷 | 打红用例 |
|---|---|---|
| M1 | 拓扑序改回行号序 | `test_report_eval_order` |
| M2 | IS-037 信用减值损失去掉负号 | 金标准对拍 |
| M3 | 发布工具把第三种定义也列入可自动改写集合 | 发布工具第三种定义用例 |
| M4 | 特殊表恢复「综合收益总额 → 6801」 | 同源守卫 |
| M5 | 综合收益总额退回不含净利润的 `SUM_ROW` | 金标准对拍（R4 回归） |
| M6 | 手工输入行提示退回「未定义公式」 | 金标准对拍 |
| M7 | 循环引用不再 fail-closed | `test_report_eval_order` |
| M8 | 陈旧提示只看符号约定、不看贷方损益为负 | 陈旧提示用例 |
| M9 | 金标准独立性判据放空 | 独立性守卫 |
| M10 | 国企营业总成本漏加 IS-029 | 营业总成本逐加项用例 |
| M11 | 存量发布工具遗漏 `formula_source=input` 行 | 发布工具 input 行非空转用例 |
| M12 | `/api/reports/generate` 丢弃 warning | warning API AST 接线守卫 |
| M13 | 不再按 `resolve_account_direction` 判贷方方向 | 历史错分 expense 的 6001 用例 |

🔴 **首轮 M7 / M10 存活，两条都是判据不足（不是实现错）**，已补强后转红：

- **M10**：`IS-029`「其他」在合成夹具里是 0 ⇒ 公式漏掉这个加项在数值上没有差异，断言恒成立。
  修法 = 给它非零输入，并对本夹具真正赋值的每个加项断言非零（「有断言」≠「断言看得见」）。
- **M7**：四套种子本来无环（`plan.cycles == ()`），`compute_row` 的循环引用分支**从未被任何用例执行过**。
  修法 = 补三例（环上的行不求值 / 清掉上一轮陈旧缓存值 / 阴性对照：同一 scope 下非环行照常求值）。

### 5.2 真 PG、共享库只读与浏览器证据

**真 PG（共享库 `audit_platform`，外层事务一律回滚）**：`test_income_statement_pg.py` = **3 passed / 1 xfailed**。

- 四套准则分别用真 `Project` + 真 `trial_balance` 行，经 `ReportFormulaParser` → 生产拓扑序 → `compute_row`，
  逐行按分等于独立金标准；`consol_report_values.report_values` 与「手工输入行 = 0」金标准同值；全部目标公式
  `validate_linear(...) is None`。
- 正式发布工具：事务内把 204 个目标模拟为旧状态，首次 `--apply` 覆盖 7 条已知坏式 + 公式空行 +
  `formula_source=input`，四准则各一条 publish；第二次全部已是目标、0 publish；输入行已有 custom 公式时退出码 2。
  测试前后用唯一 request_id 前缀查 `formula_publish` 均为 0，S9 临时项目剩余 0。
- 唯一 xfail：共享库尚未执行 formula-hub 决策项 X1，现查 `financial_report` 缺 `provenance` / `run_id`，
  `report_generation_run` 表不存在；当前工作区 ORM 已引用这些字段，完整 `ReportEngine.generate_all_reports` 无法运行。
  X1 执行后该用例自动进入完整生成断言，不能把 schema 前置缺失冒充 S9 通过。

**共享库只读**：`publish_income_statement_chain.py --json tmp_is_lower_section/publish_dry_run.json`，
`SET TRANSACTION READ ONLY`，退出码 0：目标 **204 行** = 空公式 54、已知坏式 7、来源待更新 1、输入行待登记 142、
已是目标 0、第三种定义 0、缺行 0；四准则固定 request_id 均无既有发布记录。PG 回滚测试后重跑同一只读命令，
六项计数逐值相同，证明回滚没有污染共享定义。`baseline/live_readonly.json` 另记录：共享库余额表 v1/NULL
116,306 行、v2 2,120 行；四套利润表 `formula_source='input'` 均为 0；当前 5 个有利润表结果的项目中，
目标行共 85 条、非零 15 条，非零归属行仍是旧 `SUM_ROW('IS-001', ...)` 大数。完整重算前置确实存在。

**浏览器运行时**：后端 9980 已停，且标准启动会自动应用未获批的 V236/V237，未擅自启动；3030 实际由
`tmp_formula_template_uat/verify_wt` 提供且该树 `MultiYearCompare.vue` 有预存非 async `await` 语法错。
因此在主工作区临时起 Vite 3040（用后即停），浏览器拦截全部 `/api/**`：模拟登录 / 项目只读数据，
`POST /api/reports/generate` 仅在浏览器内返回候选回执，真实后端未触达。证据
`tmp_is_lower_section/browser_evidence.json` + `screenshots/generation_warning.png`：生成 POST 1 次、
warning 可见、成功提示可见、console error 0、page error 0、意外写请求 0。

**回归**：核心回归 **235 passed / 8 skipped**（S9 + 母 spec 三路 + 合并报表 + 生成器 / 行引用 / 归属行守卫），
前端 `useReportData.spec.ts` **14 passed**；单区域 vue-tsc 中本轮新增错误 0，仍有 3 条同文件预存类型债
（两条旧测试夹具缺 `ReportConsistencyCheck.noResult/checks`，一条旧 `balanceCheckResult` 缺 `checks`）。
受影响宽选集 1,556 节点跑出 72 red / 41 skip；逐文件单跑确认其中 3 条属于 S9 契约变化并已修
（合并报表合法前向引用、合并附注合法前向展开、利润表 special 数量阈值），其余集中于并发 S1/S5、
旧真库假设与测试顺序污染；不把它们计入 S9，也未跨域擅改。真实模板种子计数两条现有红经新旧算法逐格差分
证明 `added=0 / removed=0`，与拓扑序无关，保留不改。

### 5.3 原始测试与变异计划

- 纯函数：`eval_order` 夹具（无依赖保持行号序、小计在明细前、跨表、环、`SUM_ROW` 区间展开）；守卫新判据的违规样本（环、悬空）。
- 金标准：测试内独立求值器（只读种子文本与合成试算表，不 import 生产报表模块），四套各一份正数口径合成试算表（含投资收益、减值损失、营业外收支、所得税，合并口径另给少数股东两行输入值），逐行与生产生成结果比对，并断言 §2 的恒等检查。
- 真 PG（回滚事务内【测试】项目）：四套各生成一次利润表，逐行等于金标准；合并口径经 `consol_report_values` 求值与单体同值（同一合成数据挂到合并节点）；`validate_linear` 对 §2 全部公式为 `None`。
- 工具：只读模式输出与快照库比对；`--apply` 后再跑为 0 变更；第三种公式 ⇒ 退出码 2 且不写。
- 守卫：ADR-04 同源守卫；母 spec 合计行守卫与行引用守卫（新判据）全绿。
- 磁盘变异：`eval_order` 改回行号序 ⇒ 国企 IS-007 / IS-053 用例红；IS-037 去掉负号 ⇒ 金标准用例红；工具放开「只改空公式或已知坏式」⇒ 第三种公式用例红；特殊表恢复「综合收益总额 → 6801」⇒ 同源守卫红。
