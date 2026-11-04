# 设计：两个税审案例全链路取数修复

## 1 证据摘要（探针在仓库外 `D:\gtt\probe`，只读）

| 编号 | 现象 | 根因位置 |
|---|---|---|
| R1 | 作业 246d0f62 的确认映射存为 `mapping_entries`（按列号），pipeline 读 `m.get("mappings")` ⇒ 恒空、一律按自动识别；前端 file_name 带 `00_` 前缀，pipeline 用不带前缀的 manifest 名拼 key，也对不上 | `pipeline.py` 确认映射解析段 |
| R2 | 「过账代码 / 原因代码」→ account_code、「凭证名称」→ account_name、「业务范围」→ voucher_date、「累计余额」→ opening_balance、「凭证种类 / 业务说明」→ voucher_date：4 字表头与别名差 2 个字即算命中，且取第一个命中 | `identifier._match_header` 编辑距离兜底 |
| R3 | SAP 表头（总账科目 / 短文本 / 总账科目：长文本 / 已结转余额 / 在制表期间的借方余额 / 报表期间的贷方余额 / 累计余额 / 借/贷标识 / 公司代码货币价值 / 会计年度/期间）无别名；单金额列 + S/H 方向无法拆借贷；期间「2025.011」解析为空 | 别名 JSON、`converter` |
| R4 | 案例 1 余额表「借贷方向」是科目方向、金额相对该方向带符号；`_resolve_direction` 贷 → `-abs` 丢符号（p17：父子不一致 2 → 保留符号后 0） | `converter._resolve_direction` |
| R5 | `recalc_unadjusted` 贷方类 `abs(closing)`，借方余额的贷方科目（累计亏损、留抵）变正 | `trial_balance_service` |
| R6 | 收入 / 成本分类表「其他」按名字找叫「其他」的明细；客户明细都叫不上类别名 ⇒ 全丢 | `RuleRunner` / `AccountBook.resolve` |
| R7 | SAP 平铺科目表无上级行，名称「一级-明细」；下级路径在 kids / descendants 里找不到 | `AccountBook.resolve`、`RuleRunner` |
| R8 | 一级科目自身无下级时列表为空（`len(path) > 1` 才回退本身；others 模式不回退） | `RuleRunner.entries` |
| R9 | 企业会计制度工会经费 / 职工教育经费挂其他应付款 | 规则路径 |
| R10 | 「处置非流动资产损失」与「非流动资产处置损失」 | `SYNONYMS` |
| R11 | `审核报告说明!B249`「XX元」，J249 即该数（I249=4，J~M 对应 {0}~{3}，正文只有 {1}~{3}） | 模型 JSON |

## 2 导入层

### 2.1 确认映射（R1）新模块 `ledger_import/sheet_mapping.py`

`resolve_sheet_mapping(sheet, filename, confirmed_list) -> SheetPlan(table_type, headers, col_mapping, ff_cols, source)`：

- 找确认项：`file_name` 全等 → 去掉 `^\d{2}_` 后全等 → 同 sheet 名唯一一项；
- 表头：`generate_canonical_headers(原表头)`（重复表头加 `#列号`，两个「公司代码」不再互相覆盖）；
- 有 `mapping_entries`：按 `column_index` → canonical 表头建 `col_mapping`；旧 `mappings` 字典照旧兼容；
- 确认项给了 `table_type`（非 unknown）以确认的为准；`ff_cols` 取确认映射里的科目编码 / 名称列号；
- 无确认项：沿用自动识别（置信度 ≥ 50）。

pipeline 只改为调用它、按 canonical 表头建行字典。

### 2.2 识别（R2 / R3）

- 编辑距离：两者较短一方 ≤ 5 字时容差 1，否则按配置（2）；遍历全部别名取**最小距离**，同距离先到先得。
- 别名（JSON `column_aliases` 与 `_RAW_HEADER_ALIASES` 同步）：account_code + 总账科目；account_name + 短文本、总账科目长文本；opening_balance + 已结转余额；closing_balance + 累计余额；debit_amount + 在制表期间的借方余额；credit_amount + 报表期间的贷方余额；direction + 借贷方向、借贷标识；voucher_date + 记账时间；summary + 业务说明、文本；accounting_period + 会计年度期间、会计月；currency_code + 货币；新字段 amount（单金额列）= 公司代码货币价值、金额、本币金额；新字段 counterpart_account = 对方科目、对方科目名称、对方科目编码。
- 序时账关键列替代：debit_amount / credit_amount 可由 amount 满足（JSON ledger / aux_ledger alternatives）；提交门同口径。
- 日期内容验证器接受 `2025.01.01`。

### 2.3 转换（R3 / R4）

- 方向 token 统一用集合，补 S / H / DR / CR；`_resolve_direction` 改为保留符号：贷 → `-amount`，借 → `amount`（金额相对科目方向带符号；无符号金额两种写法结果相同）。
- 序时账单金额列：借贷两列都没有值、有 amount 时拆分。有方向列：借 → debit = amount；贷 → 本批贷方行多数为负数（SAP 借正贷负）则 credit = -amount，否则 credit = amount（红字照带符号）；无方向列：正数借方、负数贷方取反。
- `parse_period_str` 补「2025.011 / 2025-11 / 202511 / 11月」，13~16 特殊期间并入 12。
- counterpart_account 透传进 tb_ledger。
- 前端列映射下拉补「金额（单列）」「对方科目」。

## 3 试算表（R5）

`recalc_unadjusted` 贷方类（含损益类无发生额兜底）`abs(x)` → `-x`：自然正数口径下借方余额的贷方科目存负数。下游报表 / 底稿按审定数取数的口径不变（正常方向仍为正）。

## 4 底稿取数

### 4.1 平铺科目（R7）

- `Node.local`：无上级、名称按 `-` / `_` / `－` 分段 ≥ 2 段的节点，取第 2 段起（「应付职工薪酬-应付工会经费」→「应付工会经费」）；其余等于末段名。名称比较（`match` / `_strict`）一律用 local。
- `resolve` 某级在 kids、descendants 都找不到时，在当前这组节点里按「去掉已走过的前 d 段后的剩余名」平铺匹配（多级「应交税费-应交增值税-进项税额」同理）。
- 列表名称显示 local。
- 抽出纯函数 `build_account_book(rows, mapping, monthly)`，`load_account_book` 只负责读库（离线验收复用）。

### 4.2 「其他」= 余项（R6）

路径末级为「其他」（name_key）且有上级路径时：`base = resolve(前缀)`；同表同前缀的其他具名类别（运行时从 `model["rules"]` 收集）各自 `resolve` 得到的节点及其下级排除；`余项 = base 的叶子中不在排除集内的`。base 无下级时余项 = base 本身。保证「各类别 + 其他 = 一级科目合计」。

### 4.3 无下级回退本身（R8）

`entries()` children / others 模式：base 全部没有下级时以 base 本身为候选（去掉 `len(path) > 1` 条件）。

### 4.4 回退路径与同义词（R9 / R10）

- `FALLBACK_PATHS = {("应付职工薪酬", "工会经费"): "其他应付款", ("应付职工薪酬", "职工教育经费"): "其他应付款"}`：原路径二级取不到时按回退一级再找。不含住房公积金（其他应付款-住房公积金是个人代扣部分）。
- SYNONYMS 补：非流动资产处置损失 ↔ 处置非流动资产损失；非流动资产处置利得 ↔ 处置非流动资产利得 / 收益。

## 5 审核说明（R11）

模型 JSON `B249`「本年损益金额XX元」→「本年损益金额{0}元」；生成脚本 `TEXT_FIXES` 登记同一条（原文对不上即失败）。

## 6 不改（报告中列为审计判断 / 缺输入）

餐饮收入归劳务；6610.38 归个税手续费返还；按摘要拆其他收益；案例 2 底稿 U/V 列审计调整（平台 0 条调整）；案例 2 改写的 `5-01-06!N15`；案例 1 3-03-01 手工固定资产分类；上年年末用审定期初数；往来重分类 / 待摊费用行 / 现金流量表（建议）；税审取数不含已审批调整（建议）。

## 6b 实施中新发现

- **R3b 合计行向下填充**：向下填充移出解析器，改在 pipeline 建行字典后由 `sheet_mapping.ForwardFill` 执行；科目编码 / 名称都空、且辅助核算 / 凭证号 / 摘要等明细标识也都空的行视为合计 / 小计行，不填（交校验按关键列为空跳过）。
- **R12 未结转损益**：损益类（标准科目表 category = revenue / expense）取本方向发生额时，期末余额非 0 的末级扣掉对方发生额；已结转（余额 0）照旧。取数 `AccountBook.measure / month` 与试算表 `recalc_unadjusted`（`open_debit / open_credit`）同口径。
- **R13 事业单位 / 民非专用表**：sheet 名带「（3)」的表，账套里有该表专用一级科目（标准企业科目表没有的名称）才取数，否则空、不报原因。
- **R8 补充**：列的是上级本身（无下级）时，金额路径（累计折旧）也取上级本身，不按名称找。

## 7 验收方法

- 离线链路探针：detect → identify → `resolve_sheet_mapping` → 读全部行 → prepare / validate / convert → `build_account_book`（映射只读取自案例项目）→ 规则 → 模型 → `check_tax_assurance_case` 比对。改前后各跑一次。
- V3：回滚事务内新建【测试】项目写入转换结果与映射副本，跑 `recalc_unadjusted` + 企业会计制度报表，读平衡差与未分配利润后回滚。
- 不重导用户项目；交付后提示用户重导（案例 2 只传 3 个 SAP 文件）。
