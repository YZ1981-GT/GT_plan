# 附录 F：核心表字段说明（业务口径）

> 2026-11-20 重写。代替正文第 5 节只列字段名的写法：每个字段写清「存的是什么、有哪些取值、从哪来」，取值全部翻成中文。
> 依据：`backend/app/models/` 的模型定义、枚举和写入它的服务代码。写「未查明」的，是代码里没有说明、我也没找到写入逻辑，不是猜的。
> 只覆盖账表 → 试算表 → 调整 → 报表 → 附注 → 底稿 → 合并这条主链上的 19 张表。

## 先看这里：每张表都有的字段

下面这些字段每张表含义都一样，后面各表不再重复解释。

| 字段 | 含义 |
|---|---|
| `id` | 这一行的唯一编号，系统自动生成，没有业务含义 |
| `project_id` | 属于哪个审计项目 |
| `year` | 哪个年度的数据 |
| `company_code` | 公司代码。单体项目试算表固定为 `001`；账表导入时文件里没有就填 `default`；合并时用来区分子企业 |
| `is_deleted` / `deleted_at` | 是否已删除 / 删除时间。系统删数据只打标记，不真删 |
| `created_at` / `updated_at` | 创建时间 / 最后修改时间（UTC 时间，比北京时间晚 8 小时） |
| `created_by` / `updated_by` | 创建人 / 最后修改人（指向用户表） |
| `tenant_id` | 多租户预留字段，目前恒为 `default`，没用 |
| `dataset_id` | 这行数据属于哪一次导入的账套版本（见 `ledger_datasets`） |
| `import_batch_id` | 写库时的内部批次号，排查问题用，业务上不用看 |
| `raw_extra` | 原文件里没有对应字段的列，原样存下来，例如 `{"审核人": "张三", "状态": "已审核"}` |

**金额怎么存（重要）**
- 四张账表（余额表、序时账、辅助余额、辅助明细）里的借方、贷方金额都按原文件存，不改正负号。
- 余额字段（期初余额、期末余额）按「科目正常方向为正」存：资产、费用类借方余额为正；负债、权益、收入类贷方余额为正；方向反了才是负数（例如应付账款出现借方余额）。
- 试算表、报表里的金额同样是「正常方向为正」。

---

## 1. `ledger_datasets` 账套版本

每导入一次账表就产生一个版本。同一项目同一年度只有一个「生效」版本，查账、试算表都只看生效版本。

| 字段 | 中文名 | 含义 | 取值 |
|---|---|---|---|
| `status` | 版本状态 | 这个版本现在是否在用 | `staged` 已写入未生效 / `active` 当前生效 / `superseded` 已被新版本替代 / `failed` 导入失败 / `rolled_back` 已回滚 |
| `source_type` | 来源 | 这个版本怎么来的 | `import` 导入（默认）/ `migration` 迁移 / `rollback` 回滚 |
| `source_summary` | 来源说明 | 导入了哪些文件、金额单位、追加导入时继承了哪几个月 | JSON |
| `record_summary` | 行数统计 | 四张账表各写了多少行 | 例：`{"tb_balance": 435, "tb_ledger": 1681993, ...}` |
| `validation_summary` | 校验结果 | 导入校验发现几个问题、几个是拦截的 | JSON |
| `job_id` | 导入任务 | 是哪一次导入任务产生的 | 指向导入任务表 |
| `previous_dataset_id` | 上一版本 | 追加导入时基于哪个旧版本 | 指向本表 |
| `activated_by` / `activated_at` | 生效人 / 生效时间 | 谁、什么时候让它生效的 | |

## 2. `tb_balance` 科目余额表

导入的客户科目余额表，一行 = 一个客户科目。科目编码是客户自己的编码，不是标准科目。

| 字段 | 中文名 | 含义 | 取值 / 来源 |
|---|---|---|---|
| `account_code` | 科目编码 | 客户原始编码，如 `1122.01` | 文件「科目编码」列 |
| `account_name` | 科目名称 | 如「应收账款_应收货款」 | 文件「科目名称」列 |
| `level` | 科目级次 | 第几级科目 | 按编码长度推：去掉分隔符后 ≤4 位为 1 级，≤6 位 2 级，≤8 位 3 级，≤10 位 4 级，更长 5 级 |
| `opening_balance` | 期初余额 | 按「正常方向为正」存 | 优先取文件的年初借/贷，其次期初借/贷，其次单列期初余额 |
| `opening_debit` / `opening_credit` | 期初借方 / 期初贷方 | 文件里分列给出时的原值 | 原样 |
| `debit_amount` / `credit_amount` | 本期借方 / 本期贷方发生额 | 优先取文件「本年累计」，没有才取「本期发生额」 | 原样，不改正负 |
| `closing_balance` | 期末余额 | 按「正常方向为正」存 | 由期末借/贷或单列期末余额 + 方向列算出 |
| `closing_debit` / `closing_credit` | 期末借方 / 期末贷方 | 文件分列给出时的原值 | 原样 |
| `opening_qty` | 期初数量 | 数量核算的科目才有 | |
| `opening_fc` | 期初外币金额 | 外币核算的科目才有 | |
| `currency_code` | 币种 | | 文件没有就填 `CNY` |
| `opening_direction` / `closing_direction` | 期初 / 期末余额方向 | 余额实际在借方还是贷方 | `debit` 借 / `credit` 贷 |
| `opening_direction_source` / `closing_direction_source` | 方向怎么判出来的 | | `split_columns` 文件借贷分列、看哪边有数 / `explicit_direction` 文件有「方向」列 / `contra_account` 按备抵科目名称（累计折旧、坏账准备等）判 / `account_category_inferred` 按科目类别判 / `account_category_inferred_low_confidence` 科目名称为空、只能按编码判 |
| `sign_convention_version` | 符号口径版本 | 现在导入的都是 `v2_category_natural_positive`（正常方向为正）；为空的是老数据，存的是借正贷负 | |
| `sign_anomaly_flags` | 方向异常标记 | 余额方向和科目正常方向相反时记下来，例如负债出现借方余额 | 例：`{"normal_direction": "credit", "conflicts": [{"period": "closing", "actual_direction": "debit", "stored_amount": -100}]}`；正常时为空 |

## 3. `tb_ledger` 序时账

导入的凭证明细，一行 = 一条分录行。

| 字段 | 中文名 | 含义 | 取值 / 来源 |
|---|---|---|---|
| `voucher_date` | 凭证日期 | | 文件「记账日期 / 凭证日期」等列；为空的行不导入 |
| `voucher_no` | 凭证号 | | 为空的行不导入 |
| `voucher_type` | 凭证字 | 记 / 收 / 付 / 转 等 | 原样 |
| `accounting_period` | 会计期间（月份） | 1~12 | 文件「期间」列；没有就取凭证日期的月份 |
| `entry_seq` | 分录序号 | 凭证内第几行 | 原样 |
| `account_code` / `account_name` | 科目编码 / 名称 | 客户原始科目 | |
| `debit_amount` / `credit_amount` | 借方 / 贷方金额 | **该条分录**的金额 | 原样。注意不能映射成「借方合计 / 贷方合计」（那是整张凭证的合计），否则每行都会变成凭证总额 |
| `debit_qty` / `credit_qty` | 借方 / 贷方数量 | 数量核算才有 | |
| `debit_fc` / `credit_fc` | 借方 / 贷方外币金额 | 外币核算才有 | |
| `counterpart_account` | 对方科目 | | 原样 |
| `summary` | 摘要 | | 原样 |
| `preparer` | 制单人 | | 原样 |
| `entry_direction` | 分录方向 | 这条分录记在借方还是贷方 | `debit` / `credit`；文件有方向列用方向列，否则看借贷哪边有数 |
| `entry_direction_source` | 方向怎么判出来的 | | 同余额表 |

## 4. `tb_aux_balance` 辅助余额表 / `tb_aux_ledger` 辅助明细账

带核算维度（客户、供应商、部门、项目等）的余额和明细。字段和余额表、序时账基本相同，多了维度字段：

| 字段 | 中文名 | 含义 | 例子 |
|---|---|---|---|
| `aux_type` | 维度类型 | 按什么核算 | 客户 / 供应商 / 部门 / 银行账户 |
| `aux_type_name` | 维度类型名称 | 文件里的原始叫法 | |
| `aux_code` / `aux_name` | 维度编码 / 名称 | 具体哪个客户、哪个部门 | `C001` / 鞍钢集团公司总医院 |
| `aux_dimensions_raw` | 原始维度串 | 文件里的原文，一行有多个维度时会拆成多行，每行都带这个原文 | `客户:C001 鞍钢总医院;部门:D01 销售部` |

## 5. `account_mapping` 科目映射

把客户科目对应到标准科目，一行 = 一个客户科目。同一项目里一个客户科目只能映射一次。

| 字段 | 中文名 | 含义 | 取值 |
|---|---|---|---|
| `original_account_code` | 客户科目编码 | 余额表里的编码 | 如 `1122.01` |
| `original_account_name` | 客户科目名称 | | |
| `standard_account_code` | 标准科目编码 | 映射到的标准科目 | 如 `1122` |
| `mapping_type` | 映射方式 | 怎么建立的这条映射 | `auto_exact` 自动精确（相似度 ≥0.92）/ `auto_fuzzy` 自动模糊 / `manual` 人工 |

子科目没有映射时，会自动沿用最近一个已映射的上级科目的标准科目。

## 6. `trial_balance` 试算表

按标准科目汇总后的金额，一行 = 一个标准科目。报表全部从这里取数。

| 字段 | 中文名 | 含义 | 怎么来的 |
|---|---|---|---|
| `standard_account_code` | 标准科目编码 | | 科目映射 |
| `account_name` | 科目名称 | | 余额表同编码名称，没有再取标准科目表 |
| `account_category` | 科目类别 | | `asset` 资产 / `liability` 负债 / `equity` 权益 / `revenue` 收入 / `expense` 费用 |
| `unadjusted_amount` | 未审数 | 客户账面数 | 余额表最明细科目按映射汇总；损益类取本期发生额（收入取贷方、费用取借方），不取期末 |
| `opening_balance` | 期初数 | | 同上汇总；损益类为 0 |
| `aje_adjustment` | 审计调整 | 已审批的审计调整分录净额 | 调整分录汇总，按科目方向换算后的增减额 |
| `rje_adjustment` | 重分类调整 | 已审批的重分类分录净额 | 同上 |
| `wp_adjustment` | 底稿调整 | 从审定表「发布到试算表」带来的差额 | 只有在底稿里点发布并确认才写入；重导账表、重算调整时保留不清零 |
| `wp_publish_base` | 发布基数 | 发布那一刻的基数，用来算底稿调整差额 | 精确含义未查明 |
| `wp_published_at` | 最近发布时间 | 底稿最后一次发布到试算表的时间 | |
| `audited_amount` | 审定数 | | **未审数 + 审计调整 + 重分类调整 + 底稿调整** |
| `currency_code` | 币种 | | 默认 `CNY` |

## 7. `adjustments` 调整分录（每行一条借或贷）

一笔调整分录有几行借贷，就存几行，同一笔用 `entry_group_id` 串起来。

| 字段 | 中文名 | 含义 | 取值 |
|---|---|---|---|
| `adjustment_no` | 分录编号 | 如 `AJE-001` | 手填或自动编号；同年度不能重复 |
| `adjustment_type` | 分录类型 | | `aje` 审计调整 / `rje` 重分类调整 |
| `entry_group_id` | 分录组 | 同一笔分录的各行共用这个编号 | |
| `description` | 摘要 | | |
| `account_code` / `account_name` | 科目 | 这一行的科目 | |
| `debit_amount` / `credit_amount` | 借方 / 贷方金额 | 一行只能填一边，不能为负 | |
| `review_status` | 复核状态 | | `draft` 草稿 / `pending_review` 待复核 / `approved` 已通过 / `rejected` 已驳回。**只有已通过的才进试算表** |
| `reviewer_id` / `reviewed_at` / `rejection_reason` | 复核人 / 复核时间 / 驳回原因 | | |
| `audit_phase` | 审计阶段 | 录入时项目处于哪个阶段 | `preliminary` 预审 / `final` 年审（默认） |
| `content_revision` | 内容修订号 | 分录内容每改一次加 1，只改状态不加 | 防止两人同时改 |
| `external_reference` | 外部编号 | 导入时文件里的编号 | |
| `import_batch_id` | 导入批次 | 从 Excel 导入的才有 | |
| `passed_reason` | 不予更正原因 | 客户不同意调整、作为未更正错报时填写 | |
| `passed_communication_date` | 沟通日期 | 与管理层沟通未更正错报的日期 | |
| `origin` | 来源 | | `manual` 手工录入（默认）/ `workpaper` 来自底稿。来自底稿的不再计入审计调整列，避免和底稿调整重复 |
| `source_ref` | 来源底稿行 | 来自哪张底稿的哪一行 | 格式 `底稿id:行编号` |

## 8. `adjustment_entries` 调整分录明细

调整分录的明细行，试算表的调整列按这张表的标准科目汇总。

| 字段 | 中文名 | 含义 |
|---|---|---|
| `adjustment_id` | 所属分录 | 指向 `adjustments` |
| `entry_group_id` | 分录组 | 同上 |
| `line_no` | 行号 | 分录内第几行 |
| `standard_account_code` | 标准科目 | 汇总到试算表用的科目 |
| `detail_account_code` | 明细科目 | 审计师选的明细科目，用于推送到底稿明细表；为空表示没有更细的明细 |
| `account_name` | 科目名称 | |
| `report_line_code` | 报表行 | 对应的报表行编码 |
| `debit_amount` / `credit_amount` | 借方 / 贷方金额 | |

## 9. `report_config` 报表格式与公式

报表每一行的定义和取数公式。系统预置国企 / 上市 × 单体 / 合并四套；项目里改过的公式另存一份。

| 字段 | 中文名 | 含义 | 取值 |
|---|---|---|---|
| `report_type` | 报表 | 属于哪张报表 | `balance_sheet` 资产负债表 / `income_statement` 利润表 / `cash_flow_statement` 现金流量表 / `equity_statement` 所有者权益变动表 / `cash_flow_supplement` 现金流量表补充资料 / `impairment_provision` 资产减值准备表 |
| `row_number` | 行次 | 显示顺序 | |
| `row_code` | 行编码 | 如 `BS-008` | 资产负债表 BS、利润表 IS、现金流量表 CFS、权益变动表 EQ、补充资料 CFSS、减值准备表 IMP |
| `row_name` | 行名称 | 如「应收账款」 | |
| `indent_level` | 缩进层级 | 显示时缩进几格 | |
| `is_total_row` | 是否合计行 | | 是 / 否 |
| `parent_row_code` | 上级行 | | |
| `formula` | 取数公式 | 如 `TB('1122','期末余额')-TB('1231','期末余额')` = 应收账款减坏账准备 | 为空表示手工填或标题行 |
| `aje_formula` / `rje_formula` | 调整列公式 | 试算平衡表里这一行的审计调整 / 重分类列怎么算 | 为空时按公式里的科目自动汇总 |
| `formula_category` | 公式用途 | | `auto_calc` 取数 / `logic_check` 逻辑审核 / `reasonability` 合理性提示 |
| `formula_description` | 公式说明 | 给人看的简短说明 | |
| `formula_source` | 公式来源 | | 如「试算表审定数」「报表行次引用」「手工填列」 |
| `applicable_standard` | 适用范围 | 这行属于哪套报表 | `soe_standalone` 国企单体 / `soe_consolidated` 国企合并 / `listed_standalone` 上市单体 / `listed_consolidated` 上市合并 / `project:项目id` 某项目改过的公式 |
| `formula_version` | 版本号 | 每改一次加 1，防止两人同时改 | |
| `pinned` | 是否固定 | 项目选择「暂不跟随」全局公式更新时为是 | |
| `base_origin` | 跟随的上游 | 项目公式基于哪一层 | `global` 全局 / `template` 公式模板 |
| `base_version` / `base_definition` / `base_template_id` | 上游版本 / 上游公式快照 / 上游模板 | 用来判断项目是否改过、全局更新后是否冲突 | |
| `is_stale` | 待更新 | 全局公式更新后，项目这一行被标记需要处理 | |

公式写法：`TB('科目','列')` 取试算表（列可写 期末余额 / 年初余额 / 未审数 / 本期发生额 / 本期借方 / 本期贷方 / AJE调整 / RJE调整），`SUM_TB('起~止','列')` 按科目区间求和，`ROW('行编码')` 引用其他行。

## 10. `financial_report` 生成的报表

点「生成报表」后的结果，一行 = 一张报表的一行。

| 字段 | 中文名 | 含义 | 取值 |
|---|---|---|---|
| `report_type` / `row_code` / `row_name` | 报表 / 行编码 / 行名称 | 同 `report_config` | |
| `current_period_amount` | 本期金额 | 按公式算出的期末数或本期数 | 计算失败时保留旧值，新行为空，不写 0 |
| `prior_period_amount` | 上期金额 | 资产负债表取本年期初数；利润表等取上年数 | 没有来源时为空 |
| `formula_used` | 使用的公式 | 生成时实际用的公式 | |
| `source_accounts` | 涉及科目 | 公式用到了哪些标准科目，例 `["1122","1231"]` | 权益变动表、减值准备表这里存的是人工编辑的矩阵数据 |
| `generated_at` | 生成时间 | | |
| `is_stale` | 已过期 | 计算失败或上游数据变了，需要重新生成 | |
| `calc_error` | 失败原因 | 计算失败时的原因 | 成功时为空 |
| `blank_reason` | 留空原因 | 金额为空时写明原因 | 如「母公司汇总上年数未结转」 |
| `calc_version` / `run_id` / `provenance` | 计算版本 / 生成批次 / 来源记录 | 追溯是哪一次生成写的 | 系统内部用 |
| `indent_level` / `is_total_row` | 缩进 / 合计行 | 同 `report_config` | |

## 11. `disclosure_notes` 附注

一行 = 附注的一个章节（如「五、5 应收账款」）。表格里的数字不在单独的列里，都在 `table_data` 这个 JSON 里。

| 字段 | 中文名 | 含义 | 取值 |
|---|---|---|---|
| `note_section` | 章节号 | 如 `五、5` | 同项目同年度不重复 |
| `section_title` | 章节标题 | 如「应收账款」 | |
| `section_id` / `parent_section_id` / `level` | 章节编号 / 上级章节 / 层级 | 组成附注目录树 | |
| `sort_index` / `sort_order` | 排序 | | |
| `auto_numbering` / `lock_number` / `locked_number` | 自动编号 / 锁定编号 / 锁定的编号 | 章节号是自动排还是手工固定 | |
| `account_name` | 对应科目 | | |
| `content_type` | 内容类型 | | `table` 表格 / `text` 文字 / `mixed` 表格加文字 |
| `table_data` | 表格内容 | 表格的行、列、数值，以及每个格是自动取数、手工填写还是锁定 | JSON |
| `text_content` | 正文 | 文字说明 | |
| `guidance_text` | 编制指引 | 提示怎么写 | |
| `source_template` | 模板版本 | | `soe` 国企版 / `listed` 上市版 |
| `status` | 状态 | | `draft` 草稿 / `confirmed` 已确认 |
| `is_empty` | 本期无此项 | | 是 / 否 |
| `is_stale` | 待刷新 | 上游数据变了，附注需要刷新 | |
| `stale_source` | 什么变了 | | `trial_balance` 试算表 / `report` 报表 / `report_fallback` 报表（整体标记）/ `workpaper` 或 `workpaper_saved` 底稿；为空是老数据 |
| `last_sync_source` | 最近一次谁更新的数 | | `workpaper` 底稿推送 / `workpaper_html` 网页底稿推送 / `formula_push` 公式推送 |
| `last_sync_wp_id` / `last_sync_at` / `last_sync_user_id` | 最近同步的底稿 / 时间 / 操作人 | | |
| `is_local_override` | 本项目改过模板 | | |
| `bound_dataset_id` / `dataset_bound_at` | 绑定的账套版本 / 绑定时间 | 生成附注时用的是哪个账套版本 | |
| `source_project_id` / `consolidation_breakdown` | 来源项目 / 合并明细 | 合并附注穿透到子企业用 | |
| `template_lineage` / `text_template_vars` | 模板来源 / 正文变量 | 系统内部用 | 结构未查明 |

## 12. `wp_index` 底稿目录

一行 = 项目里的一张底稿（目录信息）。底稿编码在这张表，`working_paper` 里没有。

| 字段 | 中文名 | 含义 | 取值 |
|---|---|---|---|
| `wp_code` | 底稿编码 | 如 `D2`、`E1-1` | 同项目不重复 |
| `wp_name` | 底稿名称 | | |
| `audit_cycle` | 审计循环 | 一般与底稿编码首字母一致 | A 报表与调整 / B 控制了解 / C 控制测试 / D 销售与收款 / E 货币资金 / F 采购与存货 / G 投资 / H 固定资产 / I 无形资产 / J 职工薪酬 / K 管理 / L 筹资 / M 所有者权益 / N 税费 / S 专项 |
| `assigned_to` / `reviewer` | 编制人 / 复核人 | | |
| `status` | 目录状态 | | `not_started` 未开始 / `in_progress` 编制中 / `draft_complete` 初稿完成 / `review_passed` 复核通过 / `archived` 已归档 |
| `cross_ref_codes` | 交叉索引 | 引用了哪些其他底稿 | 结构未查明 |

## 13. `working_paper` 底稿文件

一行 = 一张底稿的文件和编制状态，通过 `wp_index_id` 对应到底稿目录。

| 字段 | 中文名 | 含义 | 取值 |
|---|---|---|---|
| `wp_index_id` | 底稿目录 | 指向 `wp_index` | |
| `file_path` | 文件位置 | 服务器上的 Excel 文件 | |
| `source_type` | 来源 | | `template` 模板生成 / `manual` 手工新建 / `imported` 导入 |
| `status` | 编制状态 | | `draft` 编制中 / `edit_complete` 编制完成待提交 / `under_review` 复核中 / `revision_required` 退回修改 / `review_passed` 复核通过 / `archived` 已归档（另有两个旧值 `review_level1_passed`、`review_level2_passed` 只为兼容老数据） |
| `review_status` | 复核进度 | 到第几级复核、什么结果 | `not_submitted` 未提交；`pending_levelN` 待 N 级复核；`levelN_in_progress` N 级复核中；`levelN_passed` N 级通过；`levelN_rejected` N 级退回（N = 1~4） |
| `assigned_to` / `reviewer` | 编制人 / 复核人 | | |
| `rejection_reason` / `rejected_by` / `rejected_at` | 退回原因 / 退回人 / 退回时间 | | |
| `partner_reviewed_at` / `partner_reviewed_by` | 合伙人复核时间 / 复核人 | | |
| `file_version` | 文件版本 | 文件每保存一次加 1 | |
| `content_revision` | 内容修订号 | 底稿内容每改一次加 1，用来防止两人同时改冲突 | |
| `prefill_stale` | 预填已过期 | 试算表变了，底稿里自动取的数需要刷新 | 是 / 否 |
| `prefill_tb_snapshot` | 上次预填时的试算表 | 用来对比试算表是否变过 | `{科目: 审定数}` |
| `consistency_status` | 数据一致性 | 底稿数和试算表是否一致 | `unknown` 未检查 / `inconsistent` 不一致；其他取值未查明 |
| `quality_score` / `procedure_completion_rate` | 质量评分 / 程序完成率 | 为空表示还没算 | |
| `bound_dataset_id` / `dataset_bound_at` | 绑定的账套版本 | 首次生成底稿时用的账套版本 | |
| `parsed_data` / `last_parsed_at` | 解析出的数据 / 解析时间 | 系统从文件里读出的数，内部用 | |
| `workflow_status` / `explanation_status` / `last_parsed_sync_at` | | 取值和用途未查明 | |

## 14. `checklist_responses` 底稿表单填写内容

网页版底稿里每个填写格的内容都存在这里，一行 = 一张底稿的一个填写项。没有模型，代码直接写 SQL。

| 字段 | 中文名 | 含义 |
|---|---|---|
| `wp_id` | 底稿 | 指向 `working_paper` |
| `item_id` | 填写项编号 | 每张底稿自己定义的格子编号，如 `S01-001`；以 `TOC-` 开头的是章节适用性 |
| `conclusion` | 结论 | 核对类底稿的结论，如 `Y` / `N` / `NA` |
| `remark` | 内容 | 填写的文字或数字 |
| `wp_ref` | 索引号 | 引用的其他底稿 |
| `updated_by` | 填写人 | |
| `content_version` | 版本号 | 防止两人同时改 |

同一张底稿同一个填写项只有一行。

## 15. `tb_publish_ack` 审定数发布记录

在审定表点「发布到试算表」并确认后记一行，防止同一次发布被重复执行。

| 字段 | 中文名 | 含义 |
|---|---|---|
| `wp_code` | 底稿编码 | 从哪张审定表发布的 |
| `publish_token` | 发布凭证 | 每次确认生成一个，重复提交时识别为同一次 |
| `confirmed_by` | 确认人 | |
| `accounts_updated` | 更新科目数 | 这次改了试算表几个科目 |

## 16. `formula_push_state` 公式推送状态

系统自动把试算表的数推到底稿和附注的格子里，这张表记每个格子的推送情况。

| 字段 | 中文名 | 含义 | 取值 |
|---|---|---|---|
| `addr_id` | 目标格子 | 推到哪个格子 | 底稿如 `E1/E1-1/行/字段`；附注如 `note://五、1/表/行.end` |
| `rule_id` | 推送规则 | 用的哪条规则 | |
| `domain` | 目标类型 | | `workpaper` 底稿 / `note` 附注 |
| `wp_id` / `note_section` | 目标底稿 / 附注章节 | | |
| `last_pushed_value` | 上次推送的值 | 系统上次写进去的数。格子当前值和它不一样，说明人改过，系统就不再覆盖 | 为空表示从没推送过 |
| `last_formula_value` / `current_value` | 最近公式值 / 格子当前值 | 按字段名理解，代码里没有说明 | |
| `state` | 格子状态 | | `auto` 自动 / `manual` 人工改过 / `locked` 锁定 / `pending_confirm` 待确认 |
| `last_run_id` | 最近推送批次 | | |
| `updated_by` | 最后处理人 | 人工采用或锁定时记人，系统推送时为空 | |

## 17. `consol_trial` 合并试算表

合并项目按标准科目汇总的结果，一行 = 一个标准科目。

| 字段 | 中文名 | 含义 |
|---|---|---|
| `standard_account_code` / `account_name` | 标准科目 | |
| `account_category` | 科目类别 | 同试算表 |
| `individual_sum` | 个别报表汇总 | 合并范围内各子企业审定数相加 |
| `consol_adjustment` | 合并调整 | 已审批的合并调整分录（存在 `elimination_entries`） |
| `consol_elimination` | 合并抵销 | 已审批的抵销分录（存在 `elimination_entries`） |
| `consol_amount` | 合并数 | **个别汇总 + 合并调整 + 合并抵销** |
| `consolidation_breakdown` | 按企业拆分 | 每家子企业贡献了多少，例 `{"by_company": [{"company_code": "...", "amount": ...}]}` |
| `is_stale` | 待重算 | 子企业试算表变了，需要重新汇总 |

## 18. `consol_worksheet` 合并差额表

企业树每个节点、每个科目一行，记该节点上的调整和抵销。

| 字段 | 中文名 | 含义 |
|---|---|---|
| `node_company_code` | 节点 | 格式 `企业代码:角色`，角色有 `consol` 合并户 / `consol_elim` 合并差额 / `parent` 母公司户 |
| `account_code` | 科目 | |
| `adjustment_debit` / `adjustment_credit` | 调整借方 / 贷方合计 | |
| `elimination_debit` / `elimination_credit` | 抵销借方 / 贷方合计 | |
| `net_difference` | 本节点差额 | |
| `children_amount_sum` | 下级合计 | 下级节点金额相加 |
| `consolidated_amount` | 合并数 | |

## 19. `elimination_entries` 合并抵销分录

| 字段 | 中文名 | 含义 | 取值 |
|---|---|---|---|
| `entry_no` | 分录编号 | | |
| `entry_type` | 分录类型 | | `equity` 权益抵销 / `internal_trade` 内部交易 / `internal_ar_ap` 内部往来 / `unrealized_profit` 未实现利润 / `other` 其他 |
| `account_code` / `account_name` / `debit_amount` / `credit_amount` / `description` | 科目、借贷金额、摘要 | | |
| `lines` | 分录明细 | 多行借贷的明细 | JSON |
| `entry_group_id` | 分录组 | 同一笔分录共用 | |
| `branch_entity_code` | 归属节点 | 记在哪个差额节点 | 为空 = 本合并项目的「合并差额」；有值 = 该企业的「母分差额」 |
| `related_company_codes` | 相关企业 | 只用于查询筛选，不影响金额 | |
| `origin` / `origin_key` | 来源 / 来源键 | 手工录入还是合并底稿生成 | 为空 = 手工；`ws_` 开头 = 合并工作底稿生成的草稿；`legacy_sheet` = 旧版明细表转入 |
| `is_continuous` / `prior_year_entry_id` | 是否延续上年 / 对应上年分录 | 连续编制的抵销分录 | |
| `review_status` | 复核状态 | | `draft` 草稿 / `pending_review` 待复核 / `approved` 已通过 / `rejected` 已驳回。只有已通过的进合并数 |
| `reviewer_id` / `reviewed_at` | 复核人 / 复核时间 | | |
