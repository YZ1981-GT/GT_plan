# Requirements Document

## Introduction

K1「其他应收款」循环存在两类互相独立但同等严重的欠账，均已经 **DB 只读实证 + 源模板 openpyxl 直读**确认：

**一、四表库取数口径错误（数字是错的，不是缺的）**

K1 render 策略 `_k1_other_receivables.py` 用两条硬编码规则从 `tb_balance` 取数，两条都错：

1. **坏账准备取整个 `1231` 前缀** —— 而 `1231` 下挂的是按应收款种类拆分的备抵子科目
   （实证：`1231.01 坏账准备_应收票据` / `1231.02 坏账准备_应收账款` /
   `1231.03 坏账准备_其他应收款` / `1231.05 坏账准备_长期应收款`）。
   项目 `0ec33ac9`/2025 实测：K1 取到 **28,464,225.16**，其中 26,401,719.77 是
   **应收账款**的坏账；K1 真值应为 `1231.03` 的 **900,217.36** —— 虚增 **31.6 倍**。
2. **`_aggregate_prefix_deepest` 只取最深层级** —— 客户科目树是参差的（`1221.11`/`1221.12`
   无子科目，`1221.13`/`1221.15`/`1221.98` 有孙科目）。只取 depth=2 会**整段丢掉**
   `1221.11 个人往来`（3,597,359.45）与 `1221.12 保证金及押金`（55,035,942.52）。
   同项目实测：取到 **211,252,631.06**，叶子口径真值 **269,885,933.03**（= 父科目
   `1221` 期末余额，勾稽自洽），少了 **58,633,301.97（21.7%）**。
   更糟的是丢掉的正是 K1-1「款项性质分布」最核心的**保证金及押金**桶 → 性质预填恒 0。

前端 `GtK1OtherReceivables._loadTbData` 的 API 兜底路径同样用 `account_prefix=1231` 宽口径，
且会把父科目 `1231` 与子科目一起累加（`trial_balance` 里 `1231` 与 `1231-01..05` 并存）→ 双计。

**正确的科目映射链路**（DB 实证，三层）：

```
tb_balance.account_code（客户原始码，点号分级）      1221 / 1221.12 / 1231.03
      │ account_mapping(project_id, original → standard)
      ▼
trial_balance.standard_account_code（标准码，横杠分级）  1221 / 1231-03 / 1131
      │ report_config.formula（按项目 applicable_standard）
      ▼
报表行 BS-009「其他应收款」
   soe_standalone : TB('1221','期末余额') - TB('1231-03','期末余额') + TB('1131','期末余额')
   listed_* / soe_consolidated : TB('1221','期末余额')
```

平台已有同款链路的成品实现 —— `d_cycle_extraction/d1_account_resolver.py`（D1 应收票据）。
K1 必须复用而不是再造一套方言。

**二、披露表 / 附注结构与源模板不一致**

以 `backend/wp_templates/K/K1 其他应收款.xlsx` 两个披露 sheet 为唯一裁决者（附注模版 md
在本仓库不存在），逐格比对 `note_template_listed §五、8`（18 表）/ `note_template_soe §八、9`
（19 表）后确认的差异：

| # | 变体 | 问题 | 证据 |
|---|------|------|------|
| 1 | listed | 「本期计提、收回或转回的坏账准备情况」**两级表头被压扁成单级** | 源 `A91:A92`/`E91:E92` 合并 + `B92/C92/D92` 为阶段释义子表头 |
| 2 | listed | 「按账龄披露」行骨架是 **3年段**（1年以内/1-2/2-3/**3年以上**） | 源 `A13:A17` 是 **5年段**（1至2/2至3/**3至4/4至5/5年以上**） |
| 3 | listed | **缺 3 张表 + 对应文字段**：⑧应收政府补助 / ⑨因金融资产转移而终止确认 / ⑩转移且继续涉入 | 源 `A136:E141` / `A146:D150` / `A153:B159`；国企侧三张表都在 §八、9 |
| 4 | soe | 「按账龄披露其他应收款项」是 **5 列**（期末数/期初数 各含账面余额+坏账准备）、行是 **3年段且无小计/减坏账准备行** | 源 `A6:C15` 是 **3 列**（账 龄 \| 期末数 \| 期初数）+ 6 档 + 小 计 + 减：坏账准备 + 合 计 |
| 5 | soe | 同步载荷为迁就 ④ 的错列结构，把「小计 + 减：坏账准备」两行**压进合计行的额外两列** | `k1DisclosureSyncPayload.buildK1SoeSubTableData` 注释自述该 hack |
| 6 | soe | 「账龄组合」行骨架 3年段 | 源 `A49:A54` 6 档 |

**三、账龄枚举模块只贯通了一半**

`useAgingConfig(projectId,'K1')`（3年段 / 5年段 / 自定义）已接入 K1-2 明细表、K1-10、
两个披露 composable；但 **K1-1 审定表**的 `k1AdjudicationModel.K1_AGING_ROW_DEFS` 硬编码
`DEFAULT_K2_AGING_BUCKETS`（固定 6 档），且 `k1AdjudicationSync.AGING_SEG_KEYS` 硬编码
5年段的 6 个 key → 项目配 3年段时 `over3` **永远读不到**，K1-1 账龄分布凭空多 3 行空行、
少一档金额。

**四、公式管理预设不完整**

`prefill_formula_mapping.json` 的 K1-1 块只有 5 条通用样板（全部只引用 `1221`）：无坏账
`1231-03`、无 `1131/1132`、无 K1-1←K1-2/K1-3 的 `WP()` 跨底稿取数。

本 spec 只做 K1；K2~K13 沿用本 spec 建立的范式另立。

## Requirements

### Requirement 1：四表库→K1 科目定位经报表映射链路解析

**User Story:** 作为审计助理，我希望 K1 的坏账准备只取「其他应收款」自己的备抵科目，
这样审定表的坏账数才可信。

#### Acceptance Criteria

1.1 WHEN K1 render 解析科目 THEN 系统 SHALL 经「报表行 `BS-009` → `report_config.formula`
（按项目 `applicable_standard_v2` 派生的准则列表精确匹配）→ 标准码集 → `account_mapping`
反解 → 客户原始码集」链路定位，而非硬编码前缀。

1.2 WHEN 报表公式解析出多个标准码 THEN 系统 SHALL 按 `account_chart.direction=='credit'`
→ 科目名含「坏账准备/减值准备/信用减值」→ 码族前缀 `1231` 的优先级拆分为
「原值码集 / 备抵码集」，且两集合无交集、并集等于去重后的入参。

1.3 WHEN 备抵码集反解为原始码 THEN 结果 SHALL 精确到其他应收款对应子科目（实证 `1231.03`），
使应收票据/应收账款/长期应收款的坏账不被计入 K1。

1.4 IF 反解退化为宽前缀（该项目无 `account_mapping` 记录）THEN 系统 SHALL 叠加
「科目名含『其他应收款』」过滤，避免宽口径污染。

1.5 WHEN 报表行公式不含备抵科目（实证 `listed_*` 的 BS-009 只有 `TB('1221')`）
THEN 系统 SHALL 用兜底标准码 `1231-03` 并标注该侧 `resolved_from='fallback'`。

1.6 IF 链路任一环失败（无 report_config 行 / account_chart 空 / account_mapping 空 / DB 异常）
THEN 系统 SHALL 回退到与改动前等价的兜底科目并继续渲染，绝不抛错。

1.7 WHEN render 返回 THEN 输出 SHALL 含 `tb_source_codes` 取数溯源，且该字段被前端
K1 界面消费展示（不得成为 dead output）。

### Requirement 2：tb_balance 聚合改为叶子科目口径

**User Story:** 作为现场经理，我希望 K1 从四表库带出的原值等于科目余额表的期末余额，
这样才能和总账核对。

#### Acceptance Criteria

2.1 WHEN 聚合某科目前缀下的 `tb_balance` 行 THEN 系统 SHALL 只汇总**叶子行**
（不存在以 `该码 + '.'` 开头的同数据集兄弟行），而非只取最深层级。

2.2 WHEN 叶子集合确定 THEN 叶子金额之和 SHALL 等于该前缀父科目行的金额
（实证项目 `0ec33ac9`：269,885,933.03）。

2.3 WHEN 计算款项性质分布 THEN 系统 SHALL 遍历全部叶子（含 `1221.11`/`1221.12` 这类
一级叶子），使「保证金、押金」桶非零。

2.4 WHEN 备抵科目聚合 THEN 系统 SHALL 对聚合结果取绝对值（`tb_balance` 存在
「无符号 + 方向列」与「已带符号」两种约定并存），但 SHALL NOT 对原值科目做方向翻转
（实测存在 `direction='debit'` 且余额为负的合法叶子，翻转会破坏 2.2 勾稽）。

### Requirement 3：审定表 K1-1 四表预填补齐

**User Story:** 作为审计助理，我希望四表入库后打开 K1-1 就能看到未审数、并能显式重新带入。

#### Acceptance Criteria

3.1 WHEN 无持久化非零未审数 THEN 系统 SHALL 从四表库预填组合行、性质行、坏账行的
期初/期末（及原值行的借贷发生额）。

3.2 WHEN 存在任一 `K1-1-*-unadj` 非零 THEN 系统 SHALL NOT 覆盖（手工优先）。

3.3 WHEN 预填 THEN 系统 SHALL 同时预填「与经审计的财务报表核对」区三项：
`K1-1-fs-interest`（应收利息，标准码 `1132`）、`K1-1-fs-dividend`（应收股利 `1131`）、
`K1-1-fs-other-total`（报表数，`BS-009` 口径合计），且仅在对应项无持久化值时写入。

3.4 WHEN 用户点击 K1-1 的「从四表库带入未审数」按钮 THEN 系统 SHALL 重新套用预填，
只覆盖出现的类别、不清零未出现的类别。

3.5 WHEN 四表库无 K1 相关数据 THEN 系统 SHALL 返回空预填（不写 0 占位、不清空既有值）。

### Requirement 4：前端 TB 兜底口径与后端一致

**User Story:** 作为质量控制复核合伙人，我希望同一张底稿在不同加载路径下显示同一个数。

#### Acceptance Criteria

4.1 WHEN render 已下发 `tb_values` THEN 前端 SHALL 直接消费，不再发兜底请求。

4.2 IF 需要兜底请求 THEN 前端 SHALL 使用 render 下发的 `tb_source_codes.provision_standard`
（而非字面量 `1231`）作为查询口径。

4.3 WHEN 兜底请求返回父子科目并存的行集 THEN 前端 SHALL 只累加叶子（或最长前缀不重叠集），
不得父子双计。

### Requirement 5：账龄枚举模块贯通 K1-1

**User Story:** 作为项目组，我希望在项目里选了 3 年段后，K1 全部底稿的账龄档位一致。

#### Acceptance Criteria

5.1 WHEN 渲染 K1-1「二、其他应收款账龄分布」THEN 行集 SHALL 由
`useAgingConfig(projectId,'K1')` 的 `segments` 派生，而非固定 6 档常量。

5.2 WHEN 从 K1-2 聚合账龄到 K1-1 THEN 系统 SHALL 按传入的段 key 集合取值，
使 3 年段的 `over3` / 自定义段的 `custom-N` 均不丢失。

5.3 WHEN 项目账龄段变更 THEN K1-1 已录数据 SHALL 按段 key 保留，被移除的段
SHALL NOT 残留为幽灵行。

5.4 WHEN 账龄段为自定义 THEN K1-1 行标签 SHALL 取自定义段 label；披露侧标签
SHALL 继续走 `disclosureAgingLabels` 单一真源。

### Requirement 6：公式管理预设补齐

**User Story:** 作为现场经理，我希望在底稿的公式管理里看到 K1 的完整取数公式，可追溯可覆盖。

#### Acceptance Criteria

6.1 WHEN 查看 K1-1 公式预设 THEN 系统 SHALL 提供坏账准备期初/期末
（`TB('1231-03','期初余额')` / `TB('1231-03','期末余额')`）、应收股利 `TB('1131',…)`、
应收利息 `TB('1132',…)` 条目。

6.2 WHEN 查看 K1-1 公式预设 THEN 系统 SHALL 提供跨底稿取数
`WP('K1','明细表K1-2',…)`（原值合计）与 `WP('K1','坏账准备明细表K1-3',…)`（坏账期末审定）。

6.3 WHEN 查看 K1-2 明细表公式预设 THEN 系统 SHALL NOT 引入 `WP()`（防 K1-1↔K1-2 循环）。

6.4 WHEN `convert_prefill_presets()` 收敛 THEN K1 条目 SHALL 全部归入 `workpaper:K1`
且 `formula_type == 'auto_calc'`。

### Requirement 7：上市披露表 / §五、8 结构对齐源模板

**User Story:** 作为业务合伙人，我希望附注里的表格结构和致同模板逐格一致。

#### Acceptance Criteria

7.1 WHEN 渲染/推送「本期计提、收回或转回的坏账准备情况」THEN 列 SHALL 为两级表头：
`第一阶段 > 未来12个月预期信用损失` / `第二阶段 > 整个存续期预期信用损失(未发生信用减值)` /
`第三阶段 > 整个存续期预期信用损失(已发生信用减值)`，标签列与 `合计` 列不带 `group`
（混合分组，rowspan=2）。

7.2 WHEN seed「按账龄披露」行骨架 THEN 行 SHALL 为源模板 5 年段口径
（`1年以内` / `其中：0-X个月` / `X-Y个月` / `1年以内小计：` / `1至2年` / `2至3年` /
`3至4年` / `4至5年` / `5年以上` / `小计` / `减：坏账准备` / `合计`）。

7.3 WHEN 底稿上市披露表推送 THEN 载荷 SHALL 含源模板 ⑧「应收政府补助情况」、
⑨「因金融资产转移而终止确认的其他应收款情况」、⑩「转移其他应收款且继续涉入形成的
资产、负债的金额」三张表，且 §五、8 模板 SHALL 存在同名同列的表。

7.4 WHEN 上市披露表存在 ⑦资金集中管理 / ⑧⑨⑩ 的说明文字 THEN `_note_texts`
SHALL 逐条带中文 `title`，空文本过滤。

### Requirement 8：国企披露表 / §八、9 结构对齐源模板

**User Story:** 同上（国企版）。

#### Acceptance Criteria

8.1 WHEN seed/推送「按账龄披露其他应收款项」THEN 列 SHALL 为源模板 3 列
（`账  龄` / `期末数` / `期初数`，单级 `flat`），行 SHALL 含账龄档 + `小  计` +
`减：坏账准备` + `合  计`。

8.2 WHEN 构建国企同步载荷 THEN 系统 SHALL 忠实推送 `subtotal` / `provision` / `total`
三种 kind 的行，SHALL NOT 再把小计与坏账准备压进合计行的额外列。

8.3 WHEN seed「账龄组合」行骨架 THEN 行 SHALL 为源模板 6 档 + `合  计`。

8.4 WHEN 上述改动落地 THEN 「按坏账准备计提方法分类」主表/续表、「单项计提」、
「其他组合」、两张三阶段变动表的既有列结构 SHALL 零回归。

### Requirement 9：结构一致性守卫

**User Story:** 作为质控，我希望结构一旦对齐就不会被下一次改动悄悄破坏。

#### Acceptance Criteria

9.1 WHEN 运行 `fix_note_k_complex_structure.py --check` THEN 输出 SHALL 为零欠账。

9.2 WHEN 运行 K1 契约测试 THEN P1~P6 SHALL 全绿（子表名逐字 ⊆ 模板 / 章节号存在 /
`group`·`flat` 必表态 / 标签纯文本 / 标签列头对齐 `headers[0]` / 模板 headers 无 HTML），
且 `columnsPending` 逃逸阀 SHALL 保持为空。

9.3 WHEN 运行后端结构守卫 THEN 测试 SHALL 用 openpyxl **直读源 xlsx** 交叉比对
两级表头与列字面，并含反向自检（断言比对确实生效）。

9.4 WHEN 新增/改名子表 THEN 守卫 SHALL 同时校验 `K1_LISTED_SUBTABLE` /
`K1_SOE_SUBTABLE` 常量与模板 `tables[].name` 逐字一致。

### Requirement 10：端到端实测

**User Story:** 作为用户，我要看到「四表入库 → 底稿有数 → 推送 → 附注有数」真的通了。

#### Acceptance Criteria

10.1 WHEN 在真实项目打开 K1-1 THEN 界面 SHALL 显示非零未审数（性质行含保证金押金、
坏账行为 `1231.03` 口径、FS 三行有值）。

10.2 WHEN 在披露表点「推送到附注」（或触发自动同步）THEN §五、8 / §八、9 的
`last_sync_at` SHALL 前移，子表数与列元数据（`_column_groups` / `flat`）SHALL 与
本 spec 定义一致。

10.3 WHEN 实测完成 THEN 所有为实测写入的测试数据 SHALL 被复原。
