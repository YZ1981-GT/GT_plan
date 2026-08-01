# Requirements Document

## Introduction

G5 长期应收款（科目 1531）的四表取数链路、公式预设、披露表结构、附注模板对齐。G5 与 D1/K1 同属「应收类 + 坏账减值」循环（ECL 三阶段 + 性质分类 + 动态组合账龄块），但 G5 是非流动资产侧，有独特的"未实现融资收益"折现抵减 + "1年内到期"报表分列。

**科目映射真源**：`report_config` DB 实测四准则一致 `BS-023 长期应收款 = TB('1531','期末余额')`。活体 `tb_balance` 叶子：`.01 押金/融资租赁款`、`.02 借款/长期保证金`、`.03 担保/长期借款`、`.11 分期收款销售商品`、`.99 一年内到期`。无独立备抵报表行（坏账准备在 `tb_balance` 内以减值准备子科目形态）。

**当前 P0 缺陷**：公式预设 `prefill_formula_mapping.json` 的 G5 块科目码**写成 `1503`**（其他权益工具投资），`wp_name` 也写错为「其他权益工具投资审定表」—— 取数从来就是错科目。

## Requirements

### 1. 四表取数链路修复

#### 1.1 后端 render 策略改走共享件
render 必须使用 `app/services/four_table/report_line_accounts` 解析 `BS-023` 获取标准科目码 `1531`，再通过 `leaf_aggregation.select_leaves` 获取叶子子科目并聚合期初/期末余额。禁止硬编码 `_G5_ACCOUNT_PREFIX`（当兜底常量保留）。

#### 1.2 输出 `tb_source_codes` 溯源字段
render 必须输出 `tb_source_codes`（含 `gross_standard`、`resolved_from`），前端溯源面板可消费。

#### 1.3 输出 `adjudication_prefill` 审定表预填
按叶子子科目名称归类为性质桶（融资租赁款/分期收款销售商品/分期收款提供劳务/押金保证金/其他），提供审定表可直接 seed 的预填数据。

#### 1.4 输出 `tb_values` 改为叶子聚合口径
叶子和 == 父科目行金额，不再用前缀匹配全表扫描。

### 2. 公式预设纠错

#### 2.1 科目码修正
G5 块的 `account_codes` 从 `["1503"]` 修正为 `["1531"]`，`wp_name` 从「其他权益工具投资审定表」修正为「长期应收款审定表」。

#### 2.2 公式表达式修正
所有 `TB('1503',...)` 改为 `TB('1531',...)`；所有 `ADJ('1503',...)` 改为 `ADJ('1531',...)`。

#### 2.3 补充披露 sheet 公式预设
新增两个披露 sheet 块的取数公式（底稿间 `WP()` 联动 G5-1→披露表）。

#### 2.4 补充 G5-2 明细表块
新增明细表取数（`TB('1531.%','期初余额')` / `TB('1531.%','期末余额')`）。

### 3. 附注模板结构修复

#### 3.1 国企 §八、17 补全
3 张表全部补 `columns`（flat）+ `guidance`（取源 xlsx 红字/提示）；部分项目表名泄漏为 `项  目` 的须正名。

#### 3.2 上市 §五、16 重建
当前 `tables=0`（空），需按源模板 8 张表结构重建（性质 / 坏账类别 / 单项期末+续 / 组合×动态 / 变动 / 核销 / 重要核销逐项），含两级表头的表须标 `group`。

#### 3.3 幂等脚本
`backend/scripts/fix/fix_note_g5_structure.py`（`--dry-run`/`--check`/`--apply`），带 `_aligned_by` 标记。

### 4. 披露→附注同步链路

#### 4.1 上市 Tab 同步载荷列定义对齐
`g5NoteSectionMap` 的 `G5_LISTED_SUBTABLE` 各表名须与模板 `tables[].name` 逐字一致；列定义须含正确的 `flat`/`group` 标记。

#### 4.2 国企 Tab 同步载荷列定义对齐
`G5_SOE_SUBTABLE` 各表名须与模板 `tables[].name` 逐字一致。

#### 4.3 动态组合表命名空间
前缀 `组合计提项目：` 的表须随组合块增删同步产生/清除附注子表。

#### 4.4 账龄枚举贯通
组合账龄块的档位须复用 `composables/disclosureAgingLabels.ts` 单一真源（3年段/5年段/自定义）。

### 5. 前端四表消费

#### 5.1 溯源面板
新增 `G5FourTableSourcePanel.vue`（或复用 `shared/WpFourTableSourcePanel.vue`），展示 `tb_source_codes` 溯源信息。

#### 5.2 审定表「从四表库带入未审数」按钮
审定表消费 `adjudication_prefill` 按性质桶 seed 到各行。

#### 5.3 `g5AccountScope.ts` 单一真源
运行态取 render 下发的 `tb_source_codes.gross_standard`，常量只作兜底+展示。

### 6. 守卫与测试

#### 6.1 后端守卫
`test_g5_account_scope.py`：科目解析 + 叶子聚合 + 归类 + 预填 + 反向自检。

#### 6.2 前端契约
`g5NoteSubtableContract.spec.ts`：共享 helper P1~P6 + G5 专属。

#### 6.3 公式预设守卫
`test_g5_formula_presets.py`：科目码一致 / sheet 名一致 / 语法合法。

#### 6.4 CI job
新增 `note-g5-structure` + `g5-four-table-extraction` 两个 CI job。
