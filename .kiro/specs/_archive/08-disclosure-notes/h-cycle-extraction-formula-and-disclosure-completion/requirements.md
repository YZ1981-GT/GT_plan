# Requirements Document

## Introduction

H 类（H1~H10，长期资产与租赁）的「四表入库 → 底稿取数 → 披露表 → 附注」全链收口。

前序 5 个 spec（`h1-fixed-assets-mapping-and-disclosure-alignment` / `h2-construction-in-progress-disclosure-alignment` / `h3-investment-property-disclosure-alignment` / `h5-oil-gas-disclosure-alignment` / `h7-biological-assets-disclosure-rebuild` / `h8-right-of-use-disclosure-alignment` / `h9-h10-remaining-disclosure-alignment`）已把**披露表结构与附注主章节**对齐，本 spec 不重做那部分，只补它们未覆盖的四类缺口：

1. **公式预设层**与四表库实际编码族脱节（数字级失效，非恒空）
2. **`adjudication_prefill`** 在 H1~H4 四个循环缺失（四表入库后审定表无法带入）
3. **公式引擎列名**未注册导致静默取错值
4. **会计政策章**（listed 三、/ soe 四、）下 H 类科目章节 `columns=0`、`aligned_by=None`

### 实证基线（2026-08-06，只读）

**源模板**：11 个 xlsx，H1~H10 各含 2 张披露 sheet（H5 上市侧存在但 registry 声明 `listed=null`），H0 无披露 sheet（函证循环，正常）。

**后端骨架已完整，不需重建**：10 个 `four_table/h{n}_account_scope.py` + `h_cycle_specs.py` 语义定位齐全；H1~H10 全部 render 已调 `resolve_semantic_accounts`；`report_config` 的 BS-027/028/029/031/063、IMP-010/011、IS-018 四准则**逐条正确**。

**`trial_balance` 两族并存实证**（10 项目，`unadjusted_amount` 合计）：

| 语义 | 预设/report_config 引用 | 实际主力 | 比值 |
|---|---|---|---|
| 使用权资产 | `1641` = 160,078.75 | **`1651` = 386,272,594.21** | 0.04% |
| 使用权资产累计折旧 | `1642` = 68,950.60 | **`1652` = 246,042,927.81** | 0.03% |
| 租赁负债 | `2601` = 98,176.48 | **`2651` = 146,970,513.03** | 0.07% |

**两族在同一项目内互斥**（逐项目 GROUP BY 实证）：5 个项目只有 `1651/1652/2651`、4 个项目只有 `1641/1642/2601`，唯一两族都有行的 `0ec33ac9` 双方均为 0.00 ⇒ 加和口径不产生双算。

`account_mapping` 实证反解：`1651 使用权资产 → 1641`(2 项目) 与 `→ 1651`(5 项目) **并存**，`2651 → 2601`(2) 与 `→ 2651`(5) 同理 ⇒ 标准码本身在项目间不统一，只能双族并取。

**`COLUMN_ALIASES` 只有 8 个键**（期末余额/审定数/年初余额/期初余额/未审数/本期发生额/RJE调整/AJE调整），无 `本期借方`/`本期贷方`；两个 `tb_data` 构造点也不产出这两个键；而 `_handle_tb` 对未知列 `account_data.get(resolved_col, account_data.get("期末余额", 0))` **静默回退期末余额**。H 类受影响 16 条公式，全库 72 处。

**`adjudication_prefill`** 在 `_h1_fixed_assets.py` / `_h2_construction_in_progress.py` / `_h3_investment_property.py` / `_h4_engineering_materials.py` 计数为 0；H5~H10 六个循环均为 2。

## Glossary

| 术语 | 本 spec 内的含义 |
|------|------------------|
| 旧族 / 新族 | 使用权资产与租赁负债存在两套标准编码：**旧族** = `1641`/`1642`/`1643`/`2601`/`2602`（CAS 21 早期编码）；**新族** = `1651`/`1652`/`2651`（现行编码）。两族在**同一项目内互斥**（实证见 R1）。 |
| 双族并取 | 报表公式与取数同时加和两族（`TB('1641')+TB('1651')`）。因项目内互斥，加和不产生双算。本 spec 选定的收口方式，**不改任何既有码**。 |
| 静默列回退 | `formula_engine._handle_tb` 对未注册列名回退取 `期末余额`：`account_data.get(resolved_col, account_data.get("期末余额", 0))`。故 `TB('1601','本期借方')` 返回的是期末余额，属「数字错」不是「取空」。 |
| 会计政策章 | listed 的「三、重要会计政策」与 soe 的「四、」章。其下的 H 类条目分两类：**政策表**（折旧年限/残值率/年折旧率，应保留）与 **md 重建重复落章**（与主章节同构的变动表，应处置）。 |
| 主章节 | H 类科目的正式披露章节：listed 五、21/22/23/24/25/47 + 三、资产处置收益；soe 八、21/22/23/24/25/26/52/75。均已带 `_aligned_by`。 |
| 库龄 | H4 工程物资/H6 固定资产清理的「挂账时长」。与应收款**账龄**不同构（前者是存货性质的库存时长，后者是债权逾期时长），故不复用账龄枚举。 |
| 单槽 / 多槽 spec | `SemanticAccountSpec.slots` 长度。`semantic_account_resolver` 的 `allow_report_config_tier = len(spec.slots) == 1` —— 多槽 spec 不消费 `report_config` 公式，故改 `report_config` 对多槽循环的语义定位零影响。 |

## Requirements

### Requirement 1: 双族并取的科目码单一真源

**User Story:** 作为审计助理，我希望使用权资产与租赁负债循环在任何客户账套下都能取到正确金额，而不必关心客户用的是 `1641` 族还是 `1651` 族。

#### Acceptance Criteria

1. WHEN 新建共享件声明双族科目 THEN 该声明必须是全平台唯一真源，公式预设生成器、`report_config` 迁移、守卫三方共同读取
2. WHEN 某语义存在双族 THEN 声明必须同时列出两族码并标注各自在 `trial_balance` 的实证行数与金额
3. WHEN 判断能否加和 THEN 必须以「两族在同一项目内互斥」为前置条件，该条件必须由连库守卫持续验证
4. IF 某项目同时出现两族且**均非零** THEN 守卫必须打红并要求人工裁决，不得静默加和
5. WHEN 声明双族 THEN 不得修改任何既有科目码字面量（避免「改对码反而暴雷」）

### Requirement 2: 公式预设与四表库实际编码族对齐

**User Story:** 作为审计助理，我希望四表入库后在公式管理里看到的 H 类公式能真正取到数，而不是取到 0.04% 的残值。

#### Acceptance Criteria

1. WHEN H8/H9 的审定表与明细表公式引用使用权资产或租赁负债 THEN 公式必须为双族加和形式
2. WHEN H3 审定表（成本模式）公式引用科目 THEN 必须引用投资性房地产族（`1521/1525/1526/1527`），而非当前错贴的使用权资产族
3. WHEN 修订预设 THEN 必须经幂等脚本执行，支持 `--dry-run` / `--check`，`--check` 退出码 0 表示无欠账
4. WHEN 幂等脚本写盘 THEN 必须做 round-trip 自检（`json.dumps` 不能逐字复现原文则拒绝写入）
5. WHEN 预设块声明 `accounts` THEN 该清单必须与同块公式实际引用的科目集合一致
6. WHEN H2 明细表预设含硬编码具体项目号 THEN 必须移除（`AUX('1604','项目名称','B510003',…)` 属项目专属污染）
7. WHEN H10 审定表「期初余额」取数 THEN 损益类无期初，必须走 `PREV()` 而非与「未审数」同公式

### Requirement 3: 公式引擎发生额列名注册

**User Story:** 作为审计助理，我希望明细表里「本期增加」「本期减少」取到的是真实发生额，而不是被静默替换成期末余额。

#### Acceptance Criteria

1. WHEN 公式引用 `本期借方` 或 `本期贷方` THEN 引擎必须能解析为对应字段，不得静默回退
2. WHEN `tb_data` 构造点无法提供发生额 THEN 该列必须返回明确的「不可用」信号而非 0 或期末余额
3. WHEN 引擎遇到未注册列名 THEN 必须记录可观测的警告，不得完全静默
4. WHEN 新增列别名 THEN 全库既有 468 处 `期末余额` / 376 处 `期初余额` 引用的求值结果必须逐字节不变
5. IF 修改静默回退行为会破坏既有底稿 THEN 必须先用 characterization 测试锚定现状再改

### Requirement 4: H1~H4 审定表四表预填

**User Story:** 作为审计助理，我希望四表入库后点「从四表库带入未审数」，固定资产、在建工程、投资性房地产、工程物资四个审定表都能自动填上。

#### Acceptance Criteria

1. WHEN H1/H2/H3/H4 的 render 执行 THEN 必须产出 `adjudication_prefill`
2. WHEN 预填按科目分类 THEN 分类依据必须是**科目名称**而非编码（客户子科目编码语义在项目间冲突）
3. WHEN 某分类在四表库无数据 THEN 该行不预填，不得凭空产出 0
4. WHEN 审定表已有持久化值 THEN 预填不得覆盖（手工优先）
5. WHEN 前端消费 `adjudication_prefill` THEN 必须经共享件 `adjudicationPrefillPlan`，不得各写一份
6. WHEN 宿主向审定表 Tab 传参 THEN 必须传 `:html-data`，否则预填与溯源面板均静默失效

### Requirement 5: 溯源面板覆盖 H3 两个审定表

**User Story:** 作为质量控制复核合伙人，我需要在每个审定表上看到取数来源科目与口径，以便追溯审计判断。

#### Acceptance Criteria

1. WHEN H3TabAdjudicationCost 或 H3TabAdjudicationFair 渲染 THEN 必须渲染溯源面板
2. WHEN 溯源面板渲染 THEN 传入的 prop 名必须与被调组件 `defineProps` 声明一致
3. WHEN 某槽在本项目无对应科目 THEN 面板必须显示「本项目无此科目」而非 0
4. WHEN `conflicts` 非空 THEN 面板必须以中文完整句展示冲突，不得渲染裸科目码数组

### Requirement 6: report_config 双族并取修正

**User Story:** 作为业务合伙人，我需要财务报表的使用权资产与租赁负债行取到全额，而不是 0.04% 的残值。

#### Acceptance Criteria

1. WHEN BS-031 使用权资产求值 THEN 公式必须并取两族原值并扣减两族备抵
2. WHEN BS-063 租赁负债求值 THEN 公式必须并取两族
3. WHEN 修订 THEN 必须经 `V*.sql` 迁移且幂等（`WHERE` 谓词重复执行命中 0 行）
4. WHEN 迁移应用后 THEN 必须验证 H8/H9 语义定位的 `resolved_from` 与码集**逐字不变**（多槽 spec 不吃 report_config 层）
5. WHEN 修订 THEN 必须同步核查 `report_formula_service` 的镜像表（公式有 5 条写入路径）
6. WHEN 迁移编号选定 THEN 必须先查 `schema_version` 已占用号，迁移号永不复用

### Requirement 7: 会计政策章 H 类章节结构对齐

**User Story:** 作为审计助理，我希望附注会计政策章下的 H 类表格有正确的列头与编制提示，而不是空壳。

#### Acceptance Criteria

1. WHEN 修订会计政策章 THEN 判据真源必须是附注模板源 docx，而非底稿披露 sheet（该章无对应披露 sheet）
2. WHEN 某表是真实会计政策表（折旧年限/残值率/年折旧率）THEN 必须补齐 `columns` 与 `guidance` 并保留
3. WHEN 某表与科目章节表完全同构 THEN 必须判定为 md 重建重复落章并按裁决处置
4. WHEN 表名是表头首格泄漏（如 `项  目`）THEN 必须正名为源 docx 的正式表名
5. WHEN 列头含 `……` 占位 THEN 必须展开为实际类别或标记为可扩位，不得原样保留
6. WHEN 修订 THEN 必须经幂等脚本，`--check` 退出码 0
7. WHEN 判定「重复章」THEN 不得删除母公司章节（listed 十六 / soe 十二），该判断已于 2026-08-05 被撤回

### Requirement 8: 附注同步的动态插行与可扩位识别

**User Story:** 作为审计助理，我希望披露表推送到附注时，源模板留的可扩行位能正确承载我新增的明细行。

#### Acceptance Criteria

1. WHEN 源模板某行标记为可扩位（`……` / `预留` / `可改名` / `可无限量添加行`）THEN 同步载荷必须能把动态行写入该位置
2. WHEN 可扩位无数据 THEN 不得推出空占位披露行
3. WHEN 动态行需命名 THEN 必须先经 `ElMessageBox.prompt` 输入名称再创建
4. WHEN 动态行生成稳定 key THEN 必须使用持久化单调计数器，不得复用已删除行的 key
5. WHEN 多个循环共享同一附注章节 THEN 推送必须声明 `_row_scope` 只替换自己那一段

### Requirement 9: H 类不引入账龄枚举

**User Story:** 作为业务合伙人，我不希望长期资产底稿套用应收款账龄口径，那会产生错误的披露分段。

#### Acceptance Criteria

1. WHEN H 类源码引用账龄枚举（`disclosureAgingLabels` / `useAgingConfig` / `AGING_BANDS`）THEN 守卫必须打红
2. WHEN H4 或 H6 需要记录挂账时长 THEN 该维度必须与账龄显式区分命名，不得复用账龄常量
3. WHEN H4/H6 的时长字段为枚举语义 THEN 前端必须改为点选控件（交互点选优先）
4. WHEN 守卫声明「H 类不适用账龄」THEN 必须配反向自检证明扫描面非空

### Requirement 10: 金额控件与底稿间联动

**User Story:** 作为审计助理，我希望 H 类底稿的金额输入带千分符，且审定表能从明细表自动带入。

#### Acceptance Criteria

1. WHEN H 类可编辑金额列渲染 THEN 必须使用 `WpAmountInput`，不得使用 `el-input-number :formatter`（该 prop 在 EP 2.13.6 不存在）
2. WHEN 替换金额控件 THEN 利率/年限/残值率/比例/数量列不得套用
3. WHEN H1-1 或 H2-1 审定表取数 THEN 必须经 `WP()` 从对应明细表带入
4. WHEN 明细表公式引用审定表 THEN 必须禁止（防成环）
5. WHEN 新增 `WP()` 联动 THEN 必须由守卫锁定方向（审定表可引明细表，反向禁止）

### Requirement 11: 守卫、CI 与真实库验收

**User Story:** 作为质量控制复核合伙人，我需要这些修复有持续生效的守卫，而不是一次性改动。

#### Acceptance Criteria

1. WHEN 新增守卫 THEN 必须对修订前的状态打红（先改后写无法区分守卫有效与空转）
2. WHEN 守卫编写完成 THEN 必须逐条做变异检验，变异未打红即视为守卫缺陷
3. WHEN 守卫读取源码 THEN 必须先剥离注释并配反向自检
4. WHEN 守卫按名单扫描 THEN 必须配「每项条目数 ≥ N」的存在性自检，防 KeyError 伪装成断言失败
5. WHEN 验收 THEN 必须对真实库逐项目直跑并诚实报告，不得用替身冒充
6. WHEN 验收产生数据变更 THEN 必须按实测前快照完整复原
7. WHEN 守卫完成 THEN 必须接入 CI

### Requirement 12: 无附注落点的变体必须显式声明不适用

**User Story:** 作为审计助理，我希望当某个准则变体下该科目根本不设附注章节时，页面明确告诉我「本版不适用」及其依据，而不是给我一张填了也没人要的表。

#### Acceptance Criteria

1. WHEN 某循环的某变体在 `note_template_variant_matrix.json` 中取值为 `null` 且对应模板章节数为 0 THEN 该变体的披露 Tab 必须渲染显式「本版不适用」页
2. WHEN 渲染不适用页 THEN 必须列出可复核的判据（源模板 sheet 名与内容摘要、变体矩阵取值、模板章节实测数、对侧变体章节号），不得只写一句结论
3. WHEN 源模板该 sheet **确有表格内容**（与「内容为无」不同）THEN 说明文案必须如实区分两者，不得声称源模板无内容
4. WHEN 该变体不适用 THEN 对应的同步载荷构造函数必须恒返回 `null`，且组件不得接入 `useDisclosureAutoSync` / `scheduleAutoSync`
5. WHEN 组件需要附注章节号（AI 提示、复核入口）THEN 不得用 `?? '编造章节号'` 兜底；该变体无章节号时必须传空并由下游按「无章节」处理
6. WHEN 守卫声明某变体不适用 THEN 必须配反向自检（payload 返非 null 必红 / 编造章节号必红）

## 范围外

- **母公司章节任何字段** —— 归 `parent-company-note-chapter-and-sourcing`
- **国企↔上市转换链路** —— 归 `soe-listed-note-conversion-correctness`
- **附注模板 `columns` 全库补齐与 legacy 快照迁移** —— 归 `note-template-columns-and-legacy-snapshot-closure`
- **H0 函证循环** —— 已由 `h0-confirmation-source-fidelity-and-linkage` 收口（24/24 已归档）
- **`trial_balance` 父子双算** —— 平台级 recalc 缺陷，H2/H8 只作实证登记
- **全库 72 处 `本期借方`/`本期贷方`** —— 本 spec 只修引擎与 H 类 16 处，其余循环各自跟进
- **存量 `el-input-number` 全平台替换** —— 本 spec 只做 H 类
