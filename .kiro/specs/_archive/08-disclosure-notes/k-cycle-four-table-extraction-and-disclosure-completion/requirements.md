# Requirements Document

## Introduction

K 循环（K3~K13，共 11 个循环）的「四表入库 → 底稿刷新取数 → 披露表 → 附注模块」全链路
目前是**断裂**的。K1（其他应收款）与 K2（其他流动资产）已由归档 spec
`k1-four-table-extraction-and-disclosure-alignment` /
`k2-four-table-extraction-and-dynamic-rows` 收口并建立了平台范式（共享件
`app/services/four_table/{report_line_accounts,leaf_aggregation}` + per-cycle
`kXAccountScope.ts` 科目单一真源 + `WpFourTableSourcePanel` 溯源面板 +
`shared/dynamicAdjudicationRows` 动态行共享件）。本 spec 把该范式推广到 K3~K13，
并按源模板复核两个披露表与附注模块的对应内容。

### 立项调查结论（只读实证，全部可复现）

**一、科目映射真源 = `report_config`（DB 实证，非 `formula_presets_seed.json`）**

| 循环 | 科目名 | 报表行 listed / soe | `formula` | 真值科目 | 现状硬编码 | 判定 |
|---|---|---|---|---|---|---|
| K3 | 其他应付款 | `BS-053` / `BS-075` | `TB('2241','期末余额')` | `2241` | `2241` | 码对，链路缺 |
| K4 | 其他流动负债 | `BS-058` / `BS-081` | `TB('2301','期末余额')` | **无实体科目** | `2245`（不存在） | 宁缺勿造 |
| K5 | 预计负债 | `BS-068` / `BS-094` | `TB('2801','期末余额')` | **`2801`** | **`2701` = 长期应付款** | 🔴 取错科目族 |
| K6 | 持有待售资产/负债 | `BS-015`/`BS-024` + `BS-056`/`BS-079` | 全 `None` | **无实体科目** | `1481`/`2605`（不存在） | 宁缺勿造 |
| K7 | 递延收益 | `BS-069` / `BS-095` | `TB('2401','期末余额')` | `2401` | `2401` | 码对，链路缺 |
| K8 | 销售费用 | `IS-004` / `IS-022` | `TB('6601','本期发生额')` | `6601` | `6601` | 码对，**口径错** |
| K9 | 管理费用 | `IS-005` / `IS-023` | `TB('6602','本期发生额')` | `6602` | `6602` | 同上 |
| K10 | 其他收益 | `IS-010` / `IS-030` | `TB('6117','本期发生额')` | `6117` | `6117` | 同上 |
| K11 | 资产减值损失 | `IS-017` / `IS-038` | **`None`** | `6701`（`account_chart` 实证） | `6701` | 码对（兜底），公式缺 |
| K12 | 营业外收入 | `IS-020` / `IS-041` | `TB('6301','本期发生额')` | `6301` | `6301` | 同上 |
| K13 | 营业外支出 | `IS-021` / `IS-043` | `TB('6711','本期发生额')` | `6711` | `6711` | 同上 |

- `2701` 在全部项目 `account_chart` 中一律是**长期应付款**（L5 循环科目，且有 4 个子科目
  `2701.01/.02/.03/.99`），`2801` 才是预计负债（`account_chart` 5 条 / `tb_balance` 39 行 /
  `trial_balance` 4 条均有）→ K5 属「取错整个科目族」，与已修的 K2（`1231` 坏账准备当
  其他流动资产）同级。
- `2245` / `2301` / `1481` / `2605` / `2331` 在 `account_chart`、`tb_balance`、
  `trial_balance` **三处零命中** → K4 与 K6 无论用哪个码都取不到数，必须宁缺勿造并留证。

**二、🔴 损益类「Σ借 − Σ贷」在含年末结转损益的全年账上结构性恒为 0**

活体逐行实证（项目 `005a6f2d`，`6601` 及其全部 40+ 子科目）：
`debit_amount == credit_amount`，`debit − credit == 0.00` **每一行都成立**
（父行 163,042,014.46 vs 163,042,014.46）。成因是序时账必有「结转损益」分录。
而 K8~K13 六个循环的 `_fetch_tb_income_statement` 全部写着
`"audited_amount": debit - credit` → **审定表试算表列恒 0**。
权威口径 = `trial_balance`（`report_config` 的 `TB('6601','本期发生额')` 读的就是它；
实证 6601 = 505,080,400.27 / 6602 = 72,957,201.11 均非 0），兜底取
`tb_balance.debit_amount`（费用类）或 `credit_amount`（收益类）。
与已修的 N4/N5 同款，本次是第 6~11 次重演。

**三、父子双计**：K3~K13 的 `_fetch_tb_data` / `_fetch_tb_income_statement` 用
`code == prefix or code.startswith(prefix)` 遍历全部 `tb_balance` 行并累加，
**父科目行与其全部子科目行同时被计入** → 汇总标量约为真值的 2 倍。
`trial_balance` 侧的 `LIKE '2701%'` 同理（父码与子码并存）。

**四、缺点号边界**：各循环 `_build_adjudication_prefill` 内自造的 `_is_leaf` 用
`c.startswith(code)` 判子科目，无点号边界 → `1221` 会误命中 `12210`。
F1 / G7 已删过同款实现，共享件 `filter_by_prefixes` / `select_leaves` 已修正。

**五、公式预设整块按「遗留 K 编号族」写成，与致同 2025 模板族全面错位**

`wp_index` 实测并存两套命名：致同 2025 模板族（`backend/wp_templates/K/*.xlsx` +
`RENDERER_DISPATCH` + `componentType` 三方一致）与遗留「审定表」族。
`prefill_formula_mapping.json` 的 K 块全部按遗留族写：

| wp_code | 预设块 `wp_name` | 预设 `account_codes` | 平台真实循环 | 真值科目 |
|---|---|---|---|---|
| K3 | 财务费用审定表 | `['6603']` | 其他应付款 | `2241` |
| K4 | 研发费用审定表 | `['6604']` | 其他流动负债 | 无 |
| K5 | 税金及附加审定表 | `['6403']` | 预计负债 | `2801` |
| K5 | 预计负债明细 | `['2241']` + 公式全 `TB('2701')` | 预计负债 | `2801` |
| K6 | 持有待售资产和负债审定表 | `['1481','2331']` + 病态区间 `TB_SUM('1481~2331')` | 持有待售 | 无 |
| K7 | 预付款项审定表 | `['1123']`（F1 科目） | 递延收益 | `2401` |
| K10 | 营业外收入审定表 | `['6301']` | 其他收益 | `6117` |
| K11 | 营业外支出审定表 | `['6711']` | 资产减值损失 | `6701` |
| K12 | 信用减值损失审定表 | `['6701']` | 营业外收入 | `6301` |
| K13 | 资产减值损失审定表 | `['6702']` | 营业外支出 | `6711` |
| K14~K18 | 资产处置收益/其他收益/投资收益/公允价值变动/递延收益 | — | **平台无此循环** | 孤儿块 |
| K8（附加块） | 管理费用分析程序 | 病态区间 `TB_SUM('6601~6603')` | — | 应按行分列 |
| K0 | 管理循环函证 | `['1221']` | 函证（跨科目） | 不应绑单一科目 |

即 K3~K7、K10~K13 九个循环的公式预设**整块贴错标签**，K14~K18 五块为孤儿。

**六、披露/附注侧现状**：`k-cycle-disclosure-alignment` 已完成 K1~K13 三批结构对齐
（sheet 名与源 xlsx tab 名逐字一致已复核通过，见 Task 1 的比对表），
本 spec 只做「按源模板逐 sheet 复核 + 动态插行区 + 账龄枚举贯通 + 残余偏差修订」，
不重做已对齐的部分。

## Requirements

### Requirement 1: K 循环科目定位一律走报表映射规则链路

**User Story:** 作为审计助理，我希望四表库入库后 K3~K13 的底稿能取到**本循环科目**的数，
而不是别的循环的科目，这样审定表未审数才可信。

#### Acceptance Criteria

1. WHEN K3~K13 的 render 需要定位科目 THEN 系统 SHALL 通过共享件
   `app/services/four_table/report_line_accounts.resolve_report_line_accounts`
   按 `report_config` 报表行解析，禁止在取数路径写死科目码字面量
2. WHEN 报表行解析成功 THEN 系统 SHALL 在 `tb_source_codes.resolved_from` 标注
   `report_config`；解析失败 THEN SHALL 标注 `fallback` 并使用 spec 声明的兜底码
3. WHEN K5 render 执行 THEN 系统 SHALL 使用 `2801`（预计负债）而**非** `2701`（长期应付款）
4. WHEN K4 / K6 无法定位到任何实体科目 THEN 系统 SHALL 返回空取数结果（宁缺勿造），
   并在代码注释与 `tb_source_codes` 中留下「三表零命中」的实证依据，不得回退到
   不存在的 `2245` / `1481` / `2605` / `2301`
5. WHEN 任一解析环节抛异常 THEN 系统 SHALL fail-open 回退兜底码，绝不阻断 render
6. WHEN 同一 row_code 在不同准则下公式语义不同 THEN 系统 SHALL 传入
   `applicable_standards` 按准则挑公式

### Requirement 2: 叶子口径聚合，消除父子双计与缺点号边界

**User Story:** 作为现场经理，我希望审定表未审数合计等于试算平衡表该科目金额，
不多算也不少算，这样才能签复核意见。

#### Acceptance Criteria

1. WHEN 从 `tb_balance` 聚合金额 THEN 系统 SHALL 只汇总**叶子**科目
   （复用共享件 `select_leaves` / `aggregate_leaves`），删除各循环自造的 `_is_leaf`
2. WHEN 前缀匹配科目码 THEN 系统 SHALL 要求点号边界（`code == p` 或
   `code.startswith(p + '.')`），复用共享件 `filter_by_prefixes`
3. WHEN 从 `trial_balance` 取标量 THEN 系统 SHALL 按**最长前缀**归属，父码与子码并存时
   不得双计
4. WHEN 聚合完成 THEN 叶子金额之和 SHALL 等于该科目父行金额（自检不变量）
5. WHEN 备抵类科目参与聚合 THEN 系统 SHALL 只对**聚合结果**取绝对值，不在行级翻转方向

### Requirement 3: 损益类循环改用发生额权威口径

**User Story:** 作为审计助理，我希望 K8~K13 审定表的试算表列显示真实的本期发生额，
而不是恒为 0。

#### Acceptance Criteria

1. WHEN K8~K13 render 取本期发生额 THEN 系统 SHALL **禁止**使用 `debit - credit`
2. WHEN 取本期发生额 THEN 系统 SHALL 以 `trial_balance` 为权威口径（`unadjusted_amount` /
   `audited_amount`），`tb_balance` 的方向侧发生额（费用类取 `debit`、收益类取 `credit`）
   作兜底
3. WHEN `trial_balance` 该科目金额为负 THEN 系统 SHALL 按科目方向语义归一后输出，
   并在 `tb_source_codes` 标注原始符号，不得静默翻正
4. WHEN 明细子科目预填审定表行 THEN 系统 SHALL 使用与汇总标量同一口径，
   使「明细行之和 == 汇总标量」成立

### Requirement 4: 取数溯源可见（消除 dead output）

**User Story:** 作为质量控制复核合伙人，我希望能看到底稿的每个数来自哪个科目、
经哪条报表规则映射，这样才能做逻辑追溯。

#### Acceptance Criteria

1. WHEN render 返回 THEN 系统 SHALL 输出 `tb_source_codes`（含 `gross`/`gross_standard`/
   `resolved_from`/`formula`/`row_code`）
2. WHEN 底稿审定表页渲染 THEN 前端 SHALL 用共用件
   `shared/WpFourTableSourcePanel.vue` 消费 `tb_source_codes` 并展示来源科目与报表行
3. WHEN 某循环无备抵科目 THEN 溯源面板 SHALL 不显示备抵行
4. WHEN `tb_source_codes` 无任何前端消费方 THEN 视为 dead output，SHALL 不予验收

### Requirement 5: 科目码单一真源（前端）

**User Story:** 作为开发者，我希望改一处科目码全循环生效，不用满仓库 grep 字面量。

#### Acceptance Criteria

1. WHEN 前端需要 K3~K13 的科目码 THEN SHALL 从 per-cycle `kXAccountScope.ts` 取，
   运行态优先使用 render 下发的 `tb_source_codes`，常量只作兜底与展示
2. WHEN 前端源码出现本循环科目码字面量作「科目码 / 请求参数 / 事件载荷」 THEN
   守卫测试 SHALL 失败
3. WHEN `writebackTB` / 序时账导入 / 抽凭 / EventBus / AI 上下文需要科目码 THEN
   SHALL 全部取自同一真源

### Requirement 6: 审定表「从四表库带入未审数」与动态行

**User Story:** 作为审计助理，我希望四表重新入库后点一下按钮就能把新子科目补进审定表，
而我手工填的行不被覆盖。

#### Acceptance Criteria

1. WHEN 用户点击「从四表库带入未审数」 THEN 系统 SHALL 按叶子科目名建行并回填金额
2. WHEN 匹配已有行 THEN 系统 SHALL **科目码优先于行名**，改名后不重复插行
3. WHEN 四表行金额与现值不同 THEN 系统 SHALL 弹确认（可选「仅补空值」）
4. WHEN 行为手工录入或历史行 THEN 系统 SHALL 永不覆盖
5. WHEN 源模板该表标注「根据实际情况列示/不存在的项目请删除」 THEN 审定表 SHALL 使用
   共享件 `composables/shared/dynamicAdjudicationRows.ts` 的动态行，历史固定行按
   `rowId` 沿用旧 rowKey 实现零丢数迁移

### Requirement 7: 公式预设按真实循环重写

**User Story:** 作为现场经理，我希望公式管理页里 K 循环的预设是本循环的科目和公式，
不是别的科目贴错标签。

#### Acceptance Criteria

1. WHEN 重写公式预设 THEN 系统 SHALL 提供幂等脚本（支持 `--dry-run` / `--check` /
   `--apply`），`--check` 在完成后 SHALL 报 0 项欠账
2. WHEN K3/K4/K5/K6/K7/K10/K11/K12/K13 的预设块存在 THEN `wp_name` 与
   `account_codes` 与公式 SHALL 与该循环真实科目一致
3. WHEN 预设块 wp_code 在平台无对应循环（K14~K18） THEN 系统 SHALL 移除该块并在脚本内
   记录移除依据
4. WHEN 预设含病态区间（`TB_SUM('1481~2331')` / `TB_SUM('6601~6603')`） THEN
   SHALL 改为按行分列的具体科目
5. WHEN 审定表块需要与明细表勾稽 THEN SHALL 补 `WP()` 联动；明细表块 SHALL 禁含 `WP()`
   防成环
6. WHEN 预设引用的科目码 THEN 守卫 SHALL 断言该码存在于标准科目表**且**属于本循环
   报表行引用的科目集合

### Requirement 8: 披露表按源模板复核与修订

**User Story:** 作为业务合伙人，我希望披露表的列结构、行集、小节标题与致同源模板逐字一致，
因为披露是交付物。

#### Acceptance Criteria

1. WHEN 复核披露表结构 THEN 系统 SHALL 以 `backend/wp_templates/K/*.xlsx` 为唯一裁决者
   （openpyxl 直读），不以任何 md 副本为准
2. WHEN 源模板为两级/三级表头 THEN 同步载荷 `columns` SHALL 用 `group` 表达；
   单级表头 SHALL 显式标 `flat`
3. WHEN 源模板列结构与现有底稿披露表不一致 THEN SHALL 按源模板修订底稿披露表
4. WHEN 源模板标注动态插行（「可无限量添加行」/「根据实际情况列示」） THEN 披露表
   SHALL 提供动态增删行，且不 seed 占位行
5. WHEN 披露表含账龄维度 THEN SHALL 复用账龄枚举（3 年段 / 5 年段 / 自定义），
   经 `composables/disclosureAgingLabels.ts` 单一真源映射为披露口径字面

### Requirement 9: 附注模块 K 类内容同步修订

**User Story:** 作为审计助理，我希望点「推送到附注」后附注模块的 TAB 页签、表格结构、
文本框内容都正确填充，不出现孤儿子表或空表头。

#### Acceptance Criteria

1. WHEN 修订附注模板 THEN 系统 SHALL 提供幂等脚本，`--check` 完成后报 0 项欠账
2. WHEN 附注子表名与同步载荷键不一致 THEN SHALL 修正为源模板表名，并通过
   `_removed_table_keys` 清理旧键
3. WHEN 附注表缺 `columns` / `guidance` THEN SHALL 补齐；`guidance` SHALL 为纯文本
   （禁 markdown 粗体）
4. WHEN `_note_texts` 写入 THEN SHALL 位于 `sub_table_data` 内、带中文 `title`、
   过滤空文本
5. WHEN 从披露表推送到附注 THEN 落库 `sub_table_data` SHALL 为 `{key: list[dict]}`
   业务键行形态，`_column_groups` 与源模板表头层级一致
6. WHEN 同一循环在两个变体的章节结构不对称 THEN SHALL 按变体分别发送载荷

### Requirement 10: 守卫与实测

**User Story:** 作为质量控制复核合伙人，我希望这些修复被测试钉死，下次不会悄悄回退。

#### Acceptance Criteria

1. WHEN 提交本 spec 的改动 THEN 后端 SHALL 有守卫断言：科目码属本循环报表行、
   禁 `debit - credit`、禁父子双计、`_fetch_*` 真实签名调用后返回非零
2. WHEN 提交本 spec 的改动 THEN 前端 SHALL 有守卫断言：源码禁出现错误科目码字面量、
   `tb_source_codes` 有消费方、`buildXColumns` 零入参可调
3. WHEN 读源码做守卫 THEN SHALL 先 `stripComments()` 并加反向自检
4. WHEN 披露/附注结构守卫 THEN SHALL 用 openpyxl 直读源 xlsx 做三向比对
   （源模板 ↔ 附注模板 headers ↔ 同步载荷 columns）
5. WHEN 本 spec 完成 THEN SHALL 对真实项目做 render 直跑与浏览器实测，
   并把测试数据复原
6. WHEN 新增守卫 THEN SHALL 挂入 `.github/workflows/governance-checks.yml`

## Glossary

| 术语 | 含义 |
|------|------|
| 四表库 | `trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance` 四张账务底表 |
| 原始码 | 客户科目表编码，点号分级（`2241.13.02`），存于 `tb_balance.account_code` |
| 标准码 | 平台标准科目编码，横杠分级（`1231-03`），存于 `trial_balance.standard_account_code` |
| 报表行 | `report_config` 的一行，`row_code` + `applicable_standard` + `formula` |
| 叶子科目 | 不存在以 `本码 + '.'` 开头的同数据集兄弟行的最明细科目 |
| 父子双计 | 汇总时把父科目行与其子科目行同时累加，导致金额约为真值 2 倍 |
| 宁缺勿造 | 无法干净映射时返回空结果，不臆造数据（平台铁律） |
| `tb_source_codes` | render 下发的取数溯源结构，供前端展示来源科目与报表行 |
| 致同 2025 模板族 | `backend/wp_templates/` 下的运行时权威模板，与 `componentType` 一致 |
| 遗留审定表族 | `wp_index` 中残留的旧命名（K2=销售费用审定表 等），公式预设误按此族编写 |
| 动态插行区 | 源模板标注「可无限量添加行 / 根据实际情况列示」的可增删行区域 |
| 账龄枚举 | 项目级账龄分档配置（3 年段 / 5 年段 / 自定义），披露口径经单一真源映射 |
