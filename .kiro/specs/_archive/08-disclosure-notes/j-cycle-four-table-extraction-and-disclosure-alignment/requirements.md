# Requirements Document

## Introduction

J 类（职工薪酬）共 3 个循环：J1 应付职工薪酬、J2 长期应付职工薪酬/设定受益计划净资产、J3 股份支付。
本 spec 收口「四表库入库 → 底稿刷新取数 → 披露表 → 推送附注」全链，并按源 xlsx 逐格校正披露/附注结构。

### 调查结论（本 spec 的事实基础，全部经 DB 只读 / openpyxl 直读实证）

**科目映射真源（`report_config` 实证）**

| 循环 | 变体 | 报表行 | 公式 | 科目 |
|---|---|---|---|---|
| J1 应付职工薪酬 | listed_* | `BS-051` | `TB('2211','期末余额')` | `2211` |
| J1 应付职工薪酬 | soe_* | `BS-069` | `TB('2211','期末余额')` | `2211` |
| J2 长期应付职工薪酬 | listed_* | `BS-067` | **NULL** | 兜底 `2705` |
| J2 长期应付职工薪酬 | soe_* | `BS-093` | **NULL** | 兜底 `2705` |
| 设定受益计划净资产 | listed_* | `BS-023` | **NULL** | 资产侧，无独立科目（由 J2-1 派生） |
| J3 股份支付 | 全 | `EQ-011`/`EQ-012` | NULL（权益变动表行） | `4001`/`4002` + 现金结算走 `2211` |

**P0 缺陷（数字是错的，不是缺）**

- **J2 取错整个科目族**：`_j2_defined_benefit_plan.ACCOUNT_CODE = "2221"` = **应交税费**；长期应付职工薪酬实为 **`2705`**。
  活体 7 个项目 `2221` 有 18~72 行数据、`2705` 有 7~20 行 → J2-1 审定表预填出的是**全部税种行**，TB 核对数是应交税费余额。
- **J2 公式预设用 `2611`**（活体 `account_chart` 无此码）→ `审定表J2-1` / `明细表J2-2` 共 12 条公式恒空。
- **附注 八、54 两张表同名 `计划资产`**（tables[2] 变动表 / tables[5] 构成表）→ `sub_table_data` 以表名为键，必丢一张整表。

**取数天然映射（本 spec 的关键设计资产）**

活体 `account_chart` 实证，客户子科目与披露行**逐项对应**（同 F1 `1123` / G7 `1511` 范式）：

- `2211.01 短期薪酬` → J1 披露（1）短期薪酬；其下 `.01 工资` / `.03 福利费` / `.04 社会保险`（`.04.01 医疗` / `.04.02 工伤` / `.04.03 生育`）/ `.05 住房公积金` / `.06 工会经费` / `.07 职工教育经费` / `.02 短期带薪缺勤` / `.99 其他短期薪酬` **逐行对应**
- `2211.02 设定提存计划` → J1 披露（2）设定提存计划；`.02.01 基本养老保险` / `.02.02 失业保险` / `.02.03 企业年金` **逐行对应「其中：」四项**
- `2211.07 离职后福利` → 主表「离职后福利-设定提存计划」
- `2705.01 设定受益计划` / `2705.02 辞退福利` → J2-2 明细表「一 / 二」行
- `2705.01.02 当期服务成本` / `.03 过去服务成本` / `.04 结算利得` / `.05 利息净额` / `.06 重新计量设定收益负债` → J2 披露「设定受益计划变动情况」的变动行

**账龄枚举适用性裁决**

J1/J2 **均无账龄披露**。J2 的「未折现的离职后福利预计到期分析」是**到期分析**（未来 4 档：一年以内 / 一到两年 / 二到五年 / 五年以上），
CAS 9 固定档位，语义与账龄（过去）相反 → **不套用项目账龄枚举（3 年段 / 5 年段 / 自定义）**。本 spec 显式声明该判定并加反向守卫。

## Requirements

### Requirement 1: J2 科目族纠正与四表取数链路

**User Story:** 作为审计助理，我希望 J2 底稿显示的是长期应付职工薪酬（2705）的数据，而不是应交税费（2221），以便审定数可用。

#### Acceptance Criteria

1. WHEN 渲染 J2 底稿 THEN 系统 SHALL 通过 `four_table.resolve_report_line_accounts` 按变体解析报表行（listed `BS-067` / soe `BS-093`），公式为 NULL 时回退兜底标准码 `2705`
2. WHEN 报表行解析完成 THEN 系统 SHALL 输出 `tb_source_codes`（含 `gross` / `gross_standard` / `resolved_from` / `formula`）供前端溯源面板消费
3. WHEN 预填 J2-1 审定表 THEN 系统 SHALL 用 `four_table.select_leaves` 的**叶子口径**聚合（不得用「最深层级」），并满足「叶子金额之和 == 父科目 `2705` 期末金额」
4. WHEN `2705` 无数据 THEN 系统 SHALL 返回空预填（宁缺勿造），不得回退到任何其它科目族
5. IF 源码中出现 `2221` 或 `2611` 作 J2 科目码 THEN 守卫测试 SHALL 失败

### Requirement 2: J1 叶子口径与平铺科目形态

**User Story:** 作为审计助理，我希望 J1-1 审定表预填涵盖全部 2211 子科目，不因科目树层级参差而丢段。

#### Acceptance Criteria

1. WHEN 预填 J1-1 审定表 THEN 系统 SHALL 用叶子口径聚合，且四级科目（`2211.01.01.01`）不得被丢弃
2. WHEN 科目树参差（`2211.05 劳动保护费` 无三级子科目）THEN 该二级叶子 SHALL 出现在预填结果中
3. WHEN 客户科目表为**无点号平铺**形态（`221101` / `221102` / `221103` / `221104`）THEN 系统 SHALL 通过 `account_mapping` 反解或前缀匹配将其纳入
4. WHEN 存在借方性质的负余额叶子 THEN 系统 SHALL 保留符号（不得无条件 `abs()`），以保「叶子和 == 父额」勾稽成立
5. WHEN 渲染 J1 底稿 THEN 系统 SHALL 输出 `tb_source_codes` 且前端有消费方（不得是 dead output）

### Requirement 3: J1/J2 分类与行映射单一真源

**User Story:** 作为开发者，我希望科目→披露行的归类只有一份声明，避免前后端各写一套字面量。

#### Acceptance Criteria

1. WHEN 归类 `2211` 叶子 THEN 系统 SHALL 使用声明式规则表（含 `source_ref` 指向源 xlsx 单元格），按**科目名称**优先、编码兜底
2. WHEN 归类规则含互为子串的关键字 THEN 规则 SHALL 提供 `exclude_keywords` 否决词并由守卫验证顺序敏感性
3. WHEN 前端需要科目码 THEN 前端 SHALL 从 render 下发的 `tb_source_codes` 取，常量仅作兜底与展示
4. IF J1/J2 前端源码出现 `'2211'` / `'2705'` 字面量作请求参数或事件载荷 THEN 守卫测试 SHALL 失败

### Requirement 4: 公式预设修订

**User Story:** 作为现场经理，我希望公式管理页里 J 类的预设指向真实科目与真实 sheet，取数不恒空。

#### Acceptance Criteria

1. WHEN 加载 J2 公式预设 THEN 全部 `TB()` / `ADJ()` 的科目码 SHALL 为 `2705`（不得为 `2611`）
2. WHEN 加载 J1 预设 THEN sheet 名 SHALL 全部存在于源 xlsx 的 tab 名清单中（`分析程序J1-3` 不存在，源实为 `调整分录汇总表J1-3`）
3. WHEN 加载 J3 预设 THEN sheet 名 SHALL 为 `股份支付情况表J3-1`（`审定表J3-1` 在源 xlsx 不存在），科目码 SHALL 为 `4001`/`4002`（权益结算）与 `2211`（现金结算）
4. WHEN 加载 J1-2 / J1-7 预设 THEN SHALL 不含硬编码的具体成本中心编码（现有 12 条 `AUX('2211','成本中心','010102',…)` 属某项目污染）
5. WHEN 加载 J1-1 / J2-1 审定表预设 THEN SHALL 含 `WP()` 底稿间联动条目；明细表块 SHALL 不含 `WP()`（防成环）
6. WHEN 校验预设科目码 THEN 守卫 SHALL 断言码 ∈ 标准科目表 且 码 ∈ 本循环报表行引用的科目集合

### Requirement 5: J1 披露/附注结构按源 xlsx 校正

**User Story:** 作为业务合伙人，我希望附注列头与行集与源模板逐字一致，交付物不缩水。

#### Acceptance Criteria

1. WHEN 构建 J1 上市同步列 THEN 列 label SHALL 为 `上年年末数` / `本期增加` / `本期减少` / `期末数`（源 R6）；国企为 `期初余额` / `本期增加` / `本期减少` / `期末余额`（源 R8）
2. WHEN 两变体列头不同 THEN 守卫 SHALL 断言两版列定义**不得相同**
3. WHEN seed 附注 八、40「短期薪酬列示」THEN 行集 SHALL 为源 R17~R28 的 12 行 + 合计，其中「其中：」层为 `医疗保险费` / `工伤保险费` / `生育保险费` / `其他` **4 项**（现模板为 3 项且把「医疗保险费及生育保险费」合并，属臆造）
4. WHEN seed 附注 五、40「短期薪酬」THEN SHALL 保留源 R24 的 `……` 可扩行（在「社会保险费」SUM 范围内，属真实可扩明细位）
5. WHEN seed 附注 五、40「设定提存计划」THEN「其中：」层行标签 SHALL 逐字取源 R42~R45（含 `1．` ~ `4．` 序号）

### Requirement 6: J2 披露/附注结构按源 xlsx 重建

**User Story:** 作为审计助理，我希望国企与上市两版 J2 披露表结构分别对齐源模板，而不是把上市结构抄进国企。

#### Acceptance Criteria

1. WHEN seed 附注 八、54 THEN SHALL 删除 `计划资产`（变动表）与 `设定受益计划净负债（净资产）` 两张表 —— 国企源模板把三组横向并入一张 7 列表，无这两张独立表；删除后 `计划资产` 同名冲突自愈
2. WHEN 删除表 THEN 同步载荷 SHALL 上报 `_removed_table_keys`（与本次推送键求差集），清理存量孤儿子表
3. WHEN 定义 八、54 的 7 列表 THEN 表名 SHALL 为 `设定受益计划情况`（源 R12 段落名）；group 名 SHALL 为 `设定受益计划义务现值` / `计划资产的公允价值` / `设定受益计划净负债（净资产）`；叶子 label SHALL 为 `本期金额` / `上期金额`
4. WHEN seed 八、54 的 7 列表 THEN 行集 SHALL 补齐源 R23 / R25 / R26 三行（`设定受益计划净负债（净资产）的重新计量` / `2．计划资产的回报（计入利息净额的除外）` / `3．资产上限影响的变动（计入利息净额的除外）`）
5. WHEN seed 八、54 主表 THEN 行标签 SHALL 逐字取源 R7~R9（`设定受益计划净负债` / `符合设定受益计划条件的其他长期职工福利的净负债（不适用删除）` / `一年后支付的辞退福利`）
6. WHEN seed 五、49「设定受益计划义务现值：」THEN 行集 SHALL 补齐源 R27 / R28 两行
7. WHEN 定义敏感性分析列 THEN 上市末列 label SHALL 为 `计划负债减少`、国企为 `计划负债减小`（源 D90 / D69），守卫 SHALL 断言两版不得统一
8. WHEN 修订 八、54 交叉引用文本 THEN SHALL 指向 `八、40`（现为 `八、39` = 合同负债；源模板 `八、35` = 衍生金融负债，两者皆错）

### Requirement 7: J2 披露表动态插行

**User Story:** 作为审计助理，我希望能按项目实际情况增删计划资产明细行与其他变动行。

#### Acceptance Criteria

1. WHEN 源模板行为 `1、……` / `2、……` / `……` 且落在父行 SUM 范围内 THEN 该位置 SHALL 提供动态增删行（计划资产构成表的权益工具投资 / 债务工具投资各 3 位、义务现值与计划资产的「四、其他变动」、精算假设末行）
2. WHEN 新增行需要名称 THEN SHALL 先 `ElMessageBox.prompt` 输入名称再创建
3. WHEN 父行为 SUM 派生 THEN 父行金额 SHALL 只读并由子行求和推导
4. WHEN 动态行被删除 THEN 同步载荷 SHALL 不再包含该行，且父行合计随之变化
5. WHEN 行 key 生成 THEN SHALL 使用稳定 key `{group}_{seq}`（不得用 label 作 key —— 源模板多个默认名同为 `……`，会撞键）

### Requirement 8: 设定受益计划净资产（五、17）落点

**User Story:** 作为审计助理，当计划资产大于义务现值形成净资产时，我希望附注五、17 也能收到数据。

#### Acceptance Criteria

1. WHEN 补 五、17 模板 THEN SHALL 补齐 `columns`（5 列 flat：项目 / 期初余额 / 本期增加 / 本期减少 / 期末余额）与 `guidance`
2. WHEN J2-1 净负债（净资产）表期末为**净资产**（义务现值 < 计划资产）THEN 上市侧 SHALL 额外推送一个 payload 到 五、17
3. WHEN 为净负债状态 THEN SHALL 不推送 五、17（宁缺勿造），且不误删该章已有内容
4. WHEN 国企项目 THEN SHALL 不推送 五、17（`variant_matrix` 的 soe 侧为 null）

### Requirement 9: 底稿→披露 取数联动与「刷新取数」

**User Story:** 作为审计助理，四表入库后我希望打开底稿就有数，点一次「推送到附注」附注就有数。

#### Acceptance Criteria

1. WHEN J1-1 / J2-1 审定表无持久化数据 THEN SHALL 从四表叶子预填未审数（期初 / 期末），并提供「从四表库带入未审数」按钮
2. WHEN 四表重新入库且出现新叶子科目 THEN 「刷新取数」SHALL 按**科目码优先于行名**匹配已有行，新科目自动插行，已有行金额有变化时弹确认
3. WHEN 用户手工录入或历史行存在 THEN 刷新取数 SHALL 不覆盖（手工优先）
4. WHEN 披露表数据变更 THEN SHALL 触发自动同步（watch 实际数据，不得 `scheduleAutoSync(syncToDisclosureNotes)` 自调度）
5. WHEN 宿主向披露 Tab 传参 THEN SHALL 传 `:project-id` 与 `:html-data`（缺任一即静默失效）

### Requirement 10: 守卫与验证

**User Story:** 作为质量控制复核合伙人，我希望这些修订被测试钉死，不会被后续会话回退。

#### Acceptance Criteria

1. WHEN 运行后端守卫 THEN SHALL 用 openpyxl **直读源 xlsx** 交叉比对表名 / 列头 / 行集（三向比对：源 xlsx ↔ 模板 headers ↔ 同步 columns）
2. WHEN 守卫读源码做正则断言 THEN SHALL 先 `stripComments()` 并配反向自检（断言原始源码含被禁字样）
3. WHEN 幂等脚本执行 THEN `--check` SHALL 报 0 项欠账，`--dry-run` SHALL 可预览
4. WHEN 新增 `build*Columns` THEN SHALL 登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE` 且零入参可调
5. WHEN 断言账龄枚举不适用 THEN 守卫 SHALL 反向锁死「到期分析 4 档不得替换为项目账龄档位」
6. WHEN 提交前 THEN SHALL 对真实项目跑通 render + 浏览器实测披露→附注推送，并复原测试数据

### Requirement 11: J3 现状核查（只报告不新建）

**User Story:** 作为技术复核人，我希望明确 J3 的披露缺口属于平台级结构问题而非本次遗漏。

#### Acceptance Criteria

1. WHEN 核查 J3 THEN SHALL 确认源 xlsx 无「附注披露信息」sheet 且代码无披露 Tab（合规），并登记到 `CYCLES_WITHOUT_DISCLOSURE` 附依据
2. WHEN 核查附注 THEN SHALL 记录 `十二、股份支付`（listed，5 个 level-2 节 / 6 表，章节号为 md 截断值）与 `八、83 股份支付`（soe，3 表）**无底稿数据来源**
3. WHEN 报告该缺口 THEN SHALL 不自造披露表（宁缺勿造），交用户裁决是否另立 spec

## Glossary

| 术语 | 含义 |
|---|---|
| J1 / J2 / J3 | 应付职工薪酬 / 长期应付职工薪酬·设定受益计划净资产 / 股份支付 |
| DBO | Defined Benefit Obligation，设定受益计划义务现值 |
| 计划资产 | 设定受益计划持有的、用于支付职工福利的资产（按公允价值计量） |
| 净负债（净资产） | 义务现值 − 计划资产公允价值；为负即净资产（落附注五、17） |
| 设定提存计划 | CAS 9：企业只需按期缴存固定金额，无后续义务（基本养老/失业/企业年金） |
| 设定受益计划 | CAS 9：除设定提存计划外的离职后福利计划，需精算 |
| 到期分析 | 未折现的离职后福利按未来支付期间分档（≠ 账龄，档位由 CAS 9 固定 4 档） |
| 报表行 | `report_config.row_code`，如 `BS-069`；其 `formula` 是科目映射真源 |
| 叶子口径 | 只汇总无子科目的科目（`select_leaves`），保证「叶子和 == 父额」 |
| `tb_source_codes` | render 下发的取数溯源载荷，前端科目码的唯一运行态来源 |
