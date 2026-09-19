# Requirements Document

## Introduction

G6 其他债权投资（科目 1505，报表行 BS-022，附注 五、15 / 八、16）底稿当前存在**科目映射全面错乱**（后端 render 取 1503、公式预设审定表取 1510、明细表取 1531，三处互相矛盾且均非权威真源 `report_config` 的 1505）、四表取数未接入共享件、公式预设含硬编码客户 AUX 公式、附注模板国企侧 columns 缺失等问题。需要全面修正科目映射、接入四表库共享提取架构、重写公式预设、核查并修复附注模板结构与披露同步链路。

**权威科目链路实证**：
- `report_config` BS-022 四准则一致：`TB('1505','期末余额')`
- 减值准备：无独立 `IMP-xxx` 报表行（G6 损失准备计入 OCI 不冲减账面价值，故报表无备抵科目行）
- `account_mapping`：`1503` 映射到"可供出售金融资产"（旧准则科目）；`1505` / `1510` 在 `tb_balance` **全库余额为 0**
- **实测活体**：9 个项目 `trial_balance` 标准码 `1503` 和 `1505` 余额均为 0 —— G6 是当前项目池中**无真实数据**的循环

**源模板结构**（`backend/wp_templates/G/G6 其他债权投资.xlsx`）：
- 审定表 G6-1：五区块（公允价值 / 摊余成本之投资成本·利息调整·账面余额·减值准备·账面价值），每区块含单项+组合+小计+一年内到期+合计
- 上市披露（180 行）：6 小节 14 张表（主表·情况·减值变动·重要投资期末/续：期初·6 张三阶段·计提转回核销·实际核销·重要核销逐项）
- 国企披露（69 行）：3 小节 —— (1)情况表 3 列 (2)重要投资 6 列 (3)减值准备计提情况交叉引用 G5 §八、15

## Requirements

### 1. 科目映射纠正

1.1 后端 render `_g6_other_bond_investment_main.py` 的 `_G6_ACCOUNT_PREFIX` 从 `"1503"` 改为 `"1505"`（对齐 `report_config` BS-022）。

1.2 新建前端单一真源 `composables/g6AccountScope.ts`（沿 G7 `g7AccountScope.ts` 范式），声明 `G6_REPORT_ROW_CODE = 'BS-022'` / `G6_GROSS_FALLBACK_STANDARD = '1505'` / 运行态一律取 render 下发的 `tb_source_codes`，常量只作兜底+展示。

1.3 后端 render 接入共享件 `four_table/report_line_accounts.py` 的 `resolve_report_line_account_codes`（传 `applicable_standards`），输出 `tb_source_codes` 供前端消费。

### 2. 四表库取数接入

2.1 后端 render 的 TB 取数改委托共享件 `four_table/leaf_aggregation.py` 的 `select_leaves` + `aggregate_leaves`（叶子口径，按 `1505` 前缀或报表行解析结果），删除裸 SQL 前缀匹配。

2.2 新增 `adjudication_prefill`（审定表未审数从 tb_balance 叶子预填）—— 由于 G6 审定表是五区块结构且仅公允价值段有意义（1505 本身就是公允价值口径），预填仅 block1（公允价值段）期初/期末。

2.3 输出 `tb_source_codes`（`{gross_standard, resolved_from}`）供前端溯源面板消费。

### 3. 公式预设重写

3.1 审定表 G6-1 块：`account_codes` 从 `["1510"]` 改为 `["1505"]`；5 条公式的科目全部从 `1510` 改 `1505`。

3.2 明细表 G6-2 块：`account_codes` 从 `["1531","1531.01","1531.02","1531.03"]` 改为 `["1505"]`；删除 2 条硬编码客户 AUX 公式（`1531_02_客户_132357` / `1531_02_项目名称_A6000`）；子科目条目改为 `1505.xx` 形态（或仅保留 `TB('1505','期初余额')` / `TB('1505','期末余额')` + ADJ + RJE + PREV）。

3.3 新增披露 sheet 块（上市/国企各一），按源模板第 (5) 小节减值变动矩阵与审定表的勾稽关系补公式。

### 4. 附注模板结构核查与修复

4.1 上市 §五、15：14 张表已有 columns 和 guidance（由 `fix_note_g_cycle_structure.py` 修复），核查 columns 的 key/label/group 是否与 `g6NoteSectionMap.ts` 的 `G6_LISTED_SUBTABLE` + `G6_LISTED_STAGE_SUBTABLE` 逐字一致。

4.2 国企 §八、16：当前只有 2 张表各 3/6 列 columns，核查是否与源模板一致（(1) 表 3 列 项目/期末余额/期初余额；(2) 表 6 列 其他债权投资项目/面值/摊余成本/公允价值/累计OCI变动/已计提减值准备）。

4.3 国企 text_sections 第 4 条「参照八、15（3）」交叉引用 → 国企侧**不推三阶段表**（宁缺勿造），仅推 (1) 情况表 + (2) 重要投资表。

### 5. 披露同步链路完善

5.1 核查 `G6TabDisclosureListed.vue` 的同步载荷（`syncToDisclosureNotes`）是否覆盖 14 张表 + `_note_texts` 中文 title + `_removed_table_keys`。

5.2 核查 `G6TabDisclosureSOE.vue` 的同步载荷是否只推 2 张表。

5.3 三阶段表的动态插行区域（「其中：」下方可扩行）需识别并正确处理 —— 每段有「按单项计提」+「按组合计提」两子段各含可扩明细行。

5.4 前端 `G6FourTableSourcePanel`（溯源面板）接入或新建，消费 `tb_source_codes`。

### 6. 前端审定表四表取数按钮

6.1 审定表 G6-1 新增「从四表库带入未审数」按钮（与 G7/K1/K2 同范式），读 render 下发的 `adjudication_prefill` seed block1 公允价值段。

6.2 G6-1 的 TB 核对行（试算平衡表数/差异数）从 `tb_values` 正确读取（当前后端取错科目 1503，修正后取 1505）。

### 7. 守卫与测试

7.1 后端 `test_g6_account_scope.py`：断言 render 科目为 1505 且不含 1503/1510/1531 字面量。

7.2 前端 `g6AccountScope.spec.ts`：断言 `G6_REPORT_ROW_CODE` / fallback / 运行态优先。

7.3 公式预设守卫：所有 G6 条目的 `account_codes` 只许含 `1505` 族。

7.4 附注结构守卫（复用 `g6NoteSubtableContract.spec.ts` 已有 14 表断言 + 扩展国企 2 表）。
