# Design Document

## Overview

D4 营业收入四表取数与披露/附注对齐。核心设计判断：**一切科目定位走报表行驱动的动态解析**，不出现任何写死的科目码；披露与附注结构以**源 xlsx 为唯一裁决者**。

本 spec 不新造机制，全部复用平台既有单一真源：

| 能力 | 复用件 | 首建 spec |
|------|--------|-----------|
| 报表行 → 科目定位 | `four_table/report_line_accounts.resolve_report_line_accounts` | K1 |
| **区间码**展开（`SUM_TB('6001~6099')`） | `four_table/leaf_aggregation.sql_prefixes_for_specs` + `filter_by_code_specs` | F1（D4 是**第二个**消费方，此前仅 `_f1_prepayment.py`） |
| 叶子聚合 + **符号约定自动识别 + 父额自校验** | `four_table/leaf_aggregation.resolve_leaf_totals` | K1/F1 |
| 标准码 → 客户原始码反解 | `four_table/report_line_accounts.to_original_codes_with_flag` | K1 |
| 审定表动态行 | `composables/shared/dynamicAdjudicationRows.ts` | K2 |
| 溯源面板 | `shared/WpFourTableSourcePanel.vue` + `composables/shared/tbSourceCodes.ts` | K2 |
| 列转置 + 动态列（稳定 key） | `h7ListedDisclosureModel.ts` 范式 | H7 |
| 附注结构幂等脚本工具箱 | `backend/scripts/fix/_note_structure_kit.py` | D-cycle rest |
| 披露契约 helper（P1~P6） | `composables/__tests__/_disclosureSubtableContract.helper.ts` | 披露脚手架 |
| 账龄枚举 | `composables/disclosureAgingLabels.ts` | 平台 |
| AI 文本 | `composables/shared/wpAiText.ts` | N 循环 |
| 金额录入 / 格式 | `shared/WpAmountInput.vue` / `stores/displayPrefs.fmtAmount` | 平台 |

**账龄枚举说明（用户明确要求"用好枚举账龄模块"）**：D4 营业收入是损益类，源模板 8 个小节**均无账龄维度**（账龄适用于 D1/D2/K1 等应收类）。故 D4 不引入账龄档位；但（6）与剩余履约义务有关的信息表是**同族的"枚举驱动动态列"**问题（年度档位而非账龄档位），其列生成复用同一设计原则：档位由配置/审计年度派生、禁硬编码、key 与 label 分离。该判断写入守卫，防后续会话误加账龄。

## Architecture

### 取数链路（端到端）

```
四表入库
   │
   ├─ report_config（按 applicable_standards）
   │     IS-001 一、营业收入   = SUM_TB('6001~6099','本期发生额')
   │     IS-002 减：营业成本   = SUM_TB('6401~6499','本期发生额')
   │            ↓ resolve_report_line_accounts（共享件，区间原样返回）
   │     标准码规格集 {'6001~6099'} / {'6401~6499'}
   │            ↓ sql_prefixes_for_specs / filter_by_code_specs（共享件，F1 已验证）
   │     SQL 前缀谓词
   │            ↓ account_mapping 反解（逐项目，标准码 → 客户原始码）
   │     原始码集合（示例 0ec33ac9：6001, 6001.11, 6001.11.01…, 6001.17）
   │            ↓ select_leaves（点号边界，无 code+'.' 子行）
   │     叶子科目行 + 单侧发生额（收入取 credit、成本取 debit，COALESCE + 符号归一）
   │
   ├─→ ① D4-1 审定表   build_d4_adjudication_prefill()  → adjudication_prefill（动态行）
   ├─→ ② 附注（1）主表  build_d4_main_table_values()     → tb_values
   ├─→ ③ 附注（2）分行业 build_d4_segment_rows()          → segment_prefill（镜像配对）
   └─→ 溯源            build_d4_source_codes()           → tb_source_codes
```

### 收入/成本镜像配对（实证驱动）

```
收入叶子                              成本叶子                            配对依据
6001.11    营业收入_批发         ↔    6401.11    营业成本_批发            suffix '11'  ✓
6001.11.01 营业收入_批发_纯销    ↔    6401.11.01 营业成本_批发_纯销        suffix 精确  ✓
6001.16    营业收入_医疗收入     ↔    6401.16    营业成本_医疗支出        suffix ✓ / 名称≠（收入 vs 支出）
6001.15    营业收入_物业与租赁   ↔    （无对应成本子科目）                 成本列 = null（宁缺勿造）
（无）                           ↔    6401.12.01 营业成本_零售_货物成本    仅成本侧 → 单列成本行
```

配对算法（纯函数 `pair_revenue_cost_leaves`）：

1. **后缀优先**：剥离标准码前缀后的剩余部分完全相等即配对（`.11.02` ↔ `.11.02`）
2. **名称校验（非否决）**：去掉「营业收入_」「营业成本_」等前缀后比较，不等时仅记 `name_mismatch: true` 供 UI 提示，**不解除配对**（`.16 医疗收入/医疗支出` 是合法命名差异）
3. **配不上则留空**：收入有成本无 → 成本列 `null`；成本有收入无 → 生成仅成本行并标 `revenue_missing`
4. **禁按编码语义归类**：业务板块名一律取 `account_name`（同 N4 `6403` / F2 `14xx` 铁律——编码语义在项目间冲突）

### 变体差异（两版不得统一）

| 项 | 上市 五、62 | 国企 八、64 |
|----|------------|------------|
| 小节数 | 8 | 7（无试运行销售收入） |
| （2）表名 | 营业收入、营业成本按行业（或产品类型）划分 | 按行业（或产品类型）划分 |
| （3）叶子列名 | 主营业务收入 / 主营业务成本 | 收入 / 成本 |
| （4）表名 | 营业收入、营业成本按分解信息 | 营业收入分解信息 |
| （2）动态占位行 | 有 `......`（R27/R28 可扩区） | 无 |
| sheet tab 名 | 附注披露信息（上市公司） | 附注披露信息（国企） |

## Components and Interfaces

### 后端

**`backend/app/services/d4_extraction/account_scope.py`（新建，单一真源）**

```python
D4_REVENUE_ROW_CODE = "IS-001"            # 一、营业收入
D4_COST_ROW_CODE = "IS-002"               # 减：营业成本
D4_REVENUE_FALLBACK = ("6001~6099",)      # 兜底：区间，非单码
D4_COST_FALLBACK = ("6401~6499",)
D4_MAIN_REVENUE_STANDARD = "6001"         # 主营业务收入（审定表分段用）
D4_OTHER_REVENUE_STANDARD = "6051"        # 其他业务收入
D4_MAIN_COST_STANDARD = "6401"
D4_OTHER_COST_STANDARD = "6402"

async def resolve_d4_accounts(db, project_id, year, applicable_standards) -> D4AccountScope
def pair_revenue_cost_leaves(rev: list[LeafRow], cost: list[LeafRow]) -> list[SegmentPair]
def build_d4_source_codes(scope: D4AccountScope) -> dict
```

**`backend/app/services/d4_extraction/occurrence.py`（新建，范围已收窄）**

> 🔴 **不要在此再造符号归一**：`tb_balance` 侧的符号约定与父额勾稽已由共享件
> `resolve_leaf_totals(rows, prefix, absolute=True)` 完成，且该函数对**发生额
> （debit/credit）明确按「无方向语义 → 原样求和」处理**，正是 D4 所需。
> 本模块只补共享件覆盖不到的两处：

```python
def ledger_occurrence_expr(direction: Literal["credit", "debit"]):
    """`tb_ledger` 单侧发生额 SQL 表达式：``COALESCE(col, 0)``。

    禁用 ``credit_amount - debit_amount``：
      1) tb_ledger 对侧列存 NULL → 整个表达式 NULL（实测 10 项目中 8 个）；
      2) 含年末结转损益的全年账两侧恒等（实测 7/10）→ 净额结构性为 0。
    共享件 resolve_leaf_totals 作用于 tb_balance，不覆盖 tb_ledger。"""

def normalize_trial_balance_pl(amount) -> float | None:
    """`trial_balance` 损益类金额归一为正数口径；None 透传（不塌成 0）。

    仅用于 trial_balance —— 它不是 LeafRow、无 direction 列，故共享件的
    约定识别不适用（实证 df5b8403 的 6001 = -38,258,743.63）。"""
```

**`backend/app/services/auto_data_resolvers/_d4_revenue.py`（改造）**

- 4 个 resolver 全部改用 `get_active_filter`
- `d4_ledger_monthly` / `d4_ledger_monthly_by_product` 改 `occurrence_expr("credit")`
- `d4_analysis_indicators` 改走 `resolve_d4_accounts`（不再硬编码 `["6001","6051","6401","6402","1122"]`）+ `normalize_pl_sign`
- 上期无数据返回 `None` 而非 `0.0`

**`backend/app/routers/wp_render_strategies/_d4_operating_revenue.py`（改造）**

新增纯函数（可单测、无 DB 依赖）：
`build_d4_tb_values` / `build_d4_adjudication_prefill` / `build_d4_segment_prefill` / `build_d4_source_codes`
render 输出新增 `tb_values` / `adjudication_prefill` / `segment_prefill` / `tb_source_codes`。
**推翻既有「宁缺勿造」注释**并写明推翻依据（9 项目实证 + 源模板 4 行空白可扩行）。

**`backend/scripts/fix/fix_note_d4_revenue_structure.py`（新建幂等脚本）**

用 `_note_structure_kit` 的 `two_period_columns` / `flat_columns` / `rule` / `run_section` / `build_cli`；处理表名改名（`aliases`，**不进 drops**）、删 `header_label`、补 `columns`/`guidance`、`text_sections` 标题化与补段、动态年份列。

### 前端

| 文件 | 动作 |
|------|------|
| `composables/d4AccountScope.ts` | **新建** 单一真源：报表行常量 + 运行态取 `tb_source_codes`，常量仅兜底/展示 |
| `composables/d4DisclosureModel.ts` | **新建** 4 列变动表引擎 + 列转置模型（动态类别列 `{slot}_{seq}`）+（6）年度列派生 +（8）试运行 |
| `composables/d4NoteSectionMap.ts` | **重写** 表名对齐源模板、两级 `group`、补（6）（8）、`_removed_table_keys`、`_note_texts` 带中文 title |
| `composables/useD4Disclosure.ts` | 上市补上期两列；接 `segment_prefill`；删死代码类型；AI 接线 |
| `d4/core/D4TabDisclosureListed.vue` | 补上期列、（4）列转置、（6）（8）区块、`WpAmountInput`、AI、`fmtAmount` |
| `d4/core/D4TabDisclosureSoe.vue` | 同上（无（8）） |
| `composables/useD4Adjudication.ts` | 接 `adjudication_prefill` + 动态行 + `previewSeedFromPrefill` |
| `d4/core/D4TabAdjudication.vue` | 「从四表库带入未审数」按钮 + 溯源面板 |
| `d4/GtD4OperatingRevenue.vue` | 透传 `:html-data`、接 `useHostApplicableStandards` |

## Data Models

### `D4AccountScope`

```python
@dataclass(frozen=True)
class D4AccountScope:
    revenue_specs: tuple[str, ...]        # ('6001~6099',) 或 report_config 解析结果
    cost_specs: tuple[str, ...]
    revenue_resolved_from: str            # 'report_config' | 'fallback'
    cost_resolved_from: str
    revenue_original_codes: tuple[str, ...]   # account_mapping 反解，逐项目
    cost_original_codes: tuple[str, ...]
    unmapped_standard: tuple[str, ...]        # 标准码有、account_mapping 无映射
```

### `SegmentPair`（分行业/分产品披露行）

```python
@dataclass(frozen=True)
class SegmentPair:
    label: str                  # 业务板块名（取 account_name，禁按编码归类）
    suffix: str                 # 配对依据
    revenue_code: str | None
    cost_code: str | None
    current_revenue: Decimal | None
    current_cost: Decimal | None
    prior_revenue: Decimal | None
    prior_cost: Decimal | None
    name_mismatch: bool         # 名称不等但后缀配对成立（如 医疗收入/医疗支出）
    revenue_missing: bool
    cost_missing: bool
```

### 附注子表键 ↔ 源模板小节对照

| 键（= 附注模板 `tables[].name`） | 源模板小节 | 列形态 | 变体 |
|--------------------------------|-----------|--------|------|
| 营业收入和营业成本 / 营业收入、营业成本 | （1） | 5 列两级 | 上市 / 国企 |
| 营业收入、营业成本按行业（或产品类型）划分 / 按行业（或产品类型）划分 | （2） | 5 列两级 | 上市 / 国企 |
| 营业收入、营业成本按地区划分 | （3） | 5 列两级（叶子列名两版不同） | 两版 |
| 营业收入、营业成本按分解信息 / 营业收入分解信息 | （4） | 9 列列转置 + 动态类别列 | 上市 / 国企 |
| 与剩余履约义务有关的信息 | （6） | 4 列（动态年度） | 两版 |
| 试运行销售收入 | （8） | 5 列两级 | 仅上市 |

## Error Handling

| 场景 | 处理 | 理由 |
|------|------|------|
| 报表行查不到 / 公式为 NULL | 回退兜底区间码，`resolved_from='fallback'` | fail-open，不阻断 render |
| `account_mapping` 无该标准码映射 | 记入 `unmapped_standard` 并按标准码前缀直查 `tb_balance` | 保留可用性，同时暴露映射缺口 |
| 取数抛异常 | `logger.warning` + 该项返 `None`，render 其余部分正常 | 单点失败不让整张底稿打不开 |
| 上期数据缺失 | 返 `None`，前端显示「上期无数据」 | 禁把缺数据伪装成 0 |
| 成本侧配不上 | 成本列 `null` + `cost_missing=True` | 宁缺勿造 |
| 推送时准则冲突 | 服务端 `detect_standard_conflict` → 409 | 宁可不写也不写错章节 |
| 附注脚本改名冲突 | `rule(aliases=)` 而非 `drop_tables` | drop 在 apply 前执行会连行删掉 |

失败**不得**静默：所有 fail-open 分支必须留 `logger.warning`，前端保存失败必须给用户提示（禁裸 `catch {}`）。

## Testing Strategy

**后端**
- `backend/tests/d4_extraction/test_d4_account_scope.py` — 报表行解析 / 区间展开 / `account_mapping` 反解 / 镜像配对（含 PBT）
- `backend/tests/d4_extraction/test_d4_occurrence.py` — NULL 免疫 / 结转损益 / 符号归一 / 数据集隔离
- `backend/tests/d4_extraction/test_d4_render_prefill.py` — 真实签名 await 调用并断言非零；替身 `get_active_filter` 返 `sa.true()`；替身按绑定参数区分收入/成本两次查询
- `backend/tests/test_note_d4_revenue_structure.py` — openpyxl 直读源 xlsx 三向比对 + 反向自检
- `backend/tests/test_d4_formula_presets.py` — 口径 / 科目归属 / sheet 唯一 / 防成环
- 反向自检：打乱镜像配对优先级后断言特定用例失败；断言旧口径确实命中缺陷

**前端**
- `d4DisclosureModel.spec.ts` — 4 列引擎 / 列转置稳定 key / 年度列派生（含 PBT）
- `d4NoteSubtableContract.spec.ts` — 接共享 helper P1~P6 + D4 专属（两版列名不得统一、（8）仅上市）
- `d4FourTableWiring.spec.ts` — 源码级：无写死科目码、无自调度、`WpAmountInput` 归零、AI 四处齐备（先 `stripComments()` + 反向自检）

**实测（不可省）**
真实 DB 直跑 render 验金额（含负值项目 `df5b8403`、多 dataset 项目 `0ec33ac9`、有镜像缺口项目 `2aa00f57`）；浏览器 + postgres 只读验推送落库；验证后复原数据。

## Correctness Properties

### Property 1: 叶子和等于父科目发生额
对任意项目，`select_leaves` 得到的收入叶子发生额之和等于该标准码父科目在 `trial_balance` 的发生额（容差 0.01 元）。

**Validates: Requirements 2.5, 1.2**

### Property 2: 区间报表行不被当单码
给定 `SUM_TB('6001~6099',...)`，解析结果覆盖 `6002`…`6099` 的存在科目，而不仅 `6001`。

**Validates: Requirements 2.2, 2.3**

### Property 3: 发生额表达式对 NULL 免疫
对任意含 NULL 对侧列的 `tb_ledger` 行集，`occurrence_expr` 返回值非 NULL，且等于该侧非空值之和。

**Validates: Requirements 1.1, 1.2**

### Property 4: 结转损益不影响单侧口径
当行集包含使借贷两侧相等的结转分录时，单侧发生额仍为正的业务金额，而净额口径为 0。

**Validates: Requirements 1.3**

### Property 5: 数据集隔离
同一项目存在多个 dataset 时，取数结果等于 active dataset 单独取数结果，不是多版本之和。

**Validates: Requirements 1.4**

### Property 6: 符号归一幂等且不重复造
`normalize_trial_balance_pl` 对正值、负值分别返回同一正值；对 `None` 返回 `None`，不塌成 0。`tb_balance` 侧的符号处理一律由共享件 `resolve_leaf_totals` 承担，`d4_extraction` 内不出现第二份方向判定逻辑。

**Validates: Requirements 1.5, 1.6, 2.1**

### Property 7: 镜像配对不重不漏
配对结果中每个收入叶子最多出现一次、每个成本叶子最多出现一次；未配对项分别标 `cost_missing` / `revenue_missing`；配对项与未配对项的并集覆盖全部输入叶子。

**Validates: Requirements 2.5, 4.2**

### Property 8: 名称不等不解除配对
后缀相等而名称不等（医疗收入/医疗支出）时仍配对成立，仅 `name_mismatch=True`。

**Validates: Requirements 2.4, 4.2**

### Property 9: 预填手工优先
对已有手工值的审定表行，预填不改变其值；仅对空值行写入。

**Validates: Requirements 3.4, 3.5**

### Property 10: 宁缺勿造
无可映射叶子时 `adjudication_prefill` 与 `segment_prefill` 均为空集合，且 render 其余输出与改造前逐字节等价。

**Validates: Requirements 3.6, 2.7**

### Property 11: 子表键与模板逐字一致
`buildD4SyncPayload` 产出的每个 `sub_table_data` 键都存在于对应变体的附注模板 `tables[].name` 中。

**Validates: Requirements 6.1, 5.4**

### Property 12: 两版列名不得统一
（3）按地区表的叶子列名在上市与国企变体下不相等；（2）（4）表名在两版下不相等。

**Validates: Requirements 4.3, 5.4**

### Property 13: 列头表态完备
每张推送表的 `columns` 中，两级表头表声明 `group`、单级表声明 `flat`；不存在既无 `group` 又无 `flat` 的表。

**Validates: Requirements 5.2, 6.7**

### Property 14: flat 双侧一致
附注模板 seed 路径的 `columns` 与推送载荷 `columns` 对同一张表的 `flat` / `group` 表态一致。

**Validates: Requirements 6.7, 5.2**

### Property 15: 动态年度列由审计年度派生
（6）表年度列在审计年度变化时随之变化，不含硬编码年份字面量。

**Validates: Requirements 4.7, 5.5**

### Property 16: 列转置 key 稳定且不撞
（4）分解信息表的列 key 形如 `{slot}_{seq}`，在多个类别使用相同默认 label 时互不相同。

**Validates: Requirements 4.4**

### Property 17: 三向结构一致
源 xlsx 表头（openpyxl 直读）、附注模板 `headers`、推送 `columns` 三者列数与叶子列名一致。

**Validates: Requirements 5.2, 9.1**

### Property 18: text_sections 标题可识别
每个作为标题的 `text_sections` 段都能通过后端 `_is_table_title_paragraph` 判定，不会落进 `text_content`。

**Validates: Requirements 5.8**

### Property 19: guidance 纯文本
所有 `guidance` 不含 markdown 粗体标记，且内容可在源 xlsx 中找到出处。

**Validates: Requirements 5.7**

### Property 20: 移除键与推送键无交集
`_removed_table_keys` 与本次推送的 `sub_table_data` 键集合交集为空。

**Validates: Requirements 6.5**

### Property 21: 公式预设口径正确
D4 全部预设中不出现损益类科目搭配 `'期初余额'` / `'期末余额'` 的组合；引用的科目码均属于 `IS-001` / `IS-002` 解析出的科目集合。

**Validates: Requirements 7.1, 7.2, 7.8**

### Property 22: 预设块 sheet 唯一
D4 每个预设块声明 `sheet_name`，且 `(sheet_name, cell_ref)` 组合在 wp_code 内唯一（无撞键被吞）。

**Validates: Requirements 7.3, 7.5**

### Property 23: 预设不成环
明细表块不反向引用审定表块。

**Validates: Requirements 7.7**

### Property 24: 金额控件归零
两个披露 Tab 的 `el-input type="number"` 用于金额的计数为 0，`toLocaleString` 计数为 0。

**Validates: Requirements 8.1, 8.2**

### Property 25: AI 四处登记齐备
每个前端 AI target 在后端 `_SECTION_PROMPTS` 与 `_SUPPORTED_SECTIONS` 中都有条目，每条 prompt ≥20 字且含「不得虚构」。

**Validates: Requirements 8.3, 8.4**

### Property 26: 无自调度
`syncToDisclosureNotes` 函数体内不出现 `scheduleAutoSync`。

**Validates: Requirements 8.6**

### Property 27: builder 零入参可调
`buildD4*Columns` 在零入参调用下返回完整列集（每列有 `group` 或 `flat`）。

**Validates: Requirements 9.5, 9.6**

### Property 28: D4 不引入账龄档位
D4 披露模型与载荷中不出现账龄档位相关标识（源模板 8 小节均无账龄维度）。

**Validates: Requirements 4.1, 4.4**
