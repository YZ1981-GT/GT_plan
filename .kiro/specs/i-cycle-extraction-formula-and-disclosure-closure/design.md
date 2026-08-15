# Design Document

## Overview

I 循环取数 / 公式预设 / 披露 / 附注四块收口。核心判断：**既有骨架正确，本 spec 只做「收敛 + 补齐 + 纠错」，不重建**。

四块的因果关系（决定波次顺序）：

```
row_code 收敛（R1）─┐
I5 三态（R2）      ─┴→ 取数层正确 ──→ 溯源面板/带入按钮可信（R9）
                                    │
公式预设纠错（R3/R4）───────────────┤
                                    ↓
附注列元数据（R5/R6）──→ 披露载荷同构（R8）──→ 推送到附注有数据
动态插行（R7）─────────┘
```

R1 是全部下游的前提（取数错则一切下游无意义），但**它自己的风险最低** —— A/B 对照已实证
8 项目 × 6 循环实质差异 0 处。故 Wave 1 先打红 + 收敛 R1/R2，再并行推进预设与附注两条线。

## Architecture

### 取数链路（现状，本 spec 只改第 3 层的 row_code 表）

```
① tb_balance（客户原始码，多级子科目）
      │  get_active_filter（四表查询统一入口）
      ▼
② account_mapping（project_id, standard_account_code）反解
      │  to_original_codes_with_flag
      ▼
③ report_config.formula ← I_CYCLE_ROW_CODES[wp][entity]   ← 🔴 本 spec 改这里
      │  extract_signed_codes + row_name_matches 校验闸
      ▼
④ ISegmentSpec 段化认领（cost / amortization / impairment / expense）
      │  claim_segments（按 claim_priority + name_keywords + exclude_keywords）
      ▼
⑤ leaf_aggregation.select_leaves 叶子聚合（parent_check 三口径自检）
      ▼
⑥ tb_values / adjudication_prefill / tb_source_codes → render → 前端
```

**为什么第 ③ 层错了却没取到错数**：`i_cycle_accounts` 自建了 `row_name_matches` 校验闸，
错公式全被丢弃 → 六循环退化到第 ④ 层的段兜底码。兜底码恰好正确，故金额对。但报表行这一层
等于空转，且客户科目表用非标准码时兜底码前缀匹配不中会**静默取空**。

🔴 **错值实测是 11/12 不是 6/6**（spec 初稿只抓到 soe 一半）：

| 循环 | 现状 listed | 实际是什么 | 现状 soe | 实际是什么 | 正确码 |
|---|---|---|---|---|---|
| I1 | `BS-033` | 开发支出（=I2 的码） | `BS-045` | 应付账款 | `BS-032` |
| I2 | `BS-035` | 长期待摊费用（=I4 的码） | `BS-046` | 预收款项 | `BS-033` |
| I3 | `BS-037` | 其他非流动资产（=I5 的码） | `BS-047` | 合同负债 | `BS-034` |
| I4 | `BS-038` | 非流动资产合计（**派生行**） | `BS-048` | 应付职工薪酬 | `BS-035` |
| I5 | `BS-040` | 「流动负债：」（**节标题**，formula NULL） | `BS-050` | 其他应付款 | `BS-037` |
| I6 | `IS-006` | ✅ 研发费用（唯一正确） | `IS-024` | 四、净利润（派生行） | `IS-006` |

listed 侧是**整体错位一个循环**（与 L 循环公式预设「偏移一个循环」同型，见 memory）。
两个特殊形态：`BS-038` 是 `ROW()` 组合派生行 ⇒ `extract_signed_codes` 抽不出 `TB()` ⇒ codes 空；
`BS-040` formula 为 NULL ⇒ 同样落空。这两个即便行名闸被移除也不会取到错数，
但 `BS-045`~`BS-050` 与 `IS-024` 会 —— **行名闸是唯一拦住它们的东西**。

### row_code 收敛的三条约束

1. **listed 与 soe 同码** —— 实证四准则同码同名（`BS-032` 在四个 `applicable_standard`
   下 row_name 均为「无形资产」、formula 均为 `TB('1701')-TB('1702')`），故
   `I_CYCLE_ROW_CODES` 的两个键取值相同。这与 J/K/L 循环「按变体不同」是不同形态，
   守卫要显式断言「I 类两准则同码」防被按 J1 范式"修正"成两码。
2. **`i_cycle_specs.py` 零 render 消费方必须收敛** —— 两处各写一份是双真源，改一处另一处不动。
   🔴 但它的 row_code **六个全对**且带逐条 DB 实证注释（含 I5「1911 全库不存在故空兜底」、
   I6「6604 在 1 个项目 client 侧叫勘探费用故 `trust_report_config=False`」两条关键判断）
   ⇒ **它是判据来源**，处置 = 把正文常量迁入 `i_cycle_accounts` 后再删，
   **docstring 顶部映射表不得照搬**（自身 4 处错：I2 写成商誉公式、I3 写 `1721`、
   I5 写 `BS-039` 与正文矛盾、I1 备抵写 `IMP-011` 实为 `IMP-016`）。
   `I_PL_CYCLES` / `I_PL_POSITIVE_SIDE` 需单独 grep 消费方。
3. **行名闸保留** —— 它是拦住「跨准则取错行」的护栏（memory 已记 `BS-050` 在 soe 下
   formula 为 None 会让共享件兜底任取 listed 的「合同负债」），改对 row_code 后它转为
   防回退，不得删。

### 三个真源的分工（禁重造）

| 域 | 真源 | 消费方 |
|---|---|---|
| 报表行 ↔ 科目码 | `report_config` DB | `i_cycle_accounts` 查询 + 行名校验 |
| 科目名 ↔ 业务类别 | `i1_asset_categories.py`（声明式 + `source_ref`） | `i_cycle_prefill` 分类 + 前端 seed |
| 披露列结构 | 源 xlsx 披露 sheet（openpyxl 直读） | 模板 `columns` + 同步载荷，守卫三向比对 |

## Components and Interfaces

### 后端改动（全部 additive 或收敛，无新建服务）

| 文件 | 改动 |
|---|---|
| `four_table/i_cycle_accounts.py` | `I_CYCLE_ROW_CODES` 6 组取值改正；docstring 更新「本模块自建 row_code 表」的理由说明为「与 `report_config` 对账后的实证值」 |
| `four_table/i_cycle_specs.py` | 删除（零消费方）；若 `I_PL_CYCLES`/`I_PL_POSITIVE_SIDE` 有消费方则先迁入 `i_cycle_accounts` |
| `scripts/fix/fix_i_cycle_prefill_presets.py` | **新建** 幂等脚本：I1 块 sheet 名 `审定表I1-1`→`审定表I1`、I2 块 `6602`→`6604` + `account_codes` 自洽、12 张披露 sheet 预设登记 |
| `scripts/fix/fix_note_i_cycle_structure.py` | **新建** 幂等脚本：4 张表补 `columns`、2 处段落泄漏表名正名/移入 `text_sections` |
| `scripts/diagnose/diagnose_i_cycle_rowcode.py` | **新建** 只读诊断：row_code ↔ `report_config` row_name 对账 + A/B 金额对照复算 |

### 前端改动

| 文件 | 改动 |
|---|---|
| `composables/iCycleAccountScope.ts` | **新建**（若不存在）：六循环科目视图单一真源，复用 `shared/cycleAccountScope.ts` 工厂；`isAccountAbsent()` 区分「无此科目」与「余额为 0」 |
| `iXNoteSectionMap.ts` ×6 | 补 `columns` 的 `flat`/`group` 表态使与模板同构；I1 上市类别列改稳定 key |
| `i1/…TabDisclosure*.vue` | I1 两版四层/三层 `……` 实现为可扩类别行 |
| `i2/…TabDisclosureListed.vue` | 「研发支出」按费用性质可扩行 |
| 六个 `IXTabAdjudication.vue` | 挂溯源面板 + 「从四表库带入未审数」按钮（走 `adjudicationPrefillPlan`） |

### 守卫

| 文件 | 覆盖 |
|---|---|
| `backend/tests/four_table/test_i_cycle_row_code_evidence.py` | R1：连库对账 row_code ↔ row_name；两准则同码；`i_cycle_specs` 已删除；A/B 码集相等 |
| `backend/tests/four_table/test_i5_absent_account.py` | R2：I5 兜底空 + 三态可分 + 反向自检 |
| `backend/tests/test_i_cycle_formula_presets.py` | R3/R4：预设 sheet 名 ∈ 源 workbook 真实 tab；科目码与公式自洽；无成环；`--check` 归零 |
| `backend/tests/test_note_i_cycle_structure.py` | R5/R6：源 xlsx ↔ 模板 headers ↔ 同步 columns 三向；I1 上市列集 |
| `frontend/…/__tests__/iCycleAccountScope.spec.ts` | R9：读后端 py 源码交叉锁死槽键/row_code/兜底码 |
| `frontend/…/__tests__/iCycleNoteSubtableContract.spec.ts` | R8：子表名逐字 / columns 同构 / flat 表态 / `_note_texts` title |
| `frontend/…/__tests__/iCycleDynamicRows.spec.ts` | R7：可扩行 key 稳定不复用 / 骨架行数非写死 |
| `backend/scripts/diagnose/mutate_i_cycle_guards.py` | R11：变异检验，三态区分 + `.bak` + `--restore` |

## Data Models

### `ISegmentSpec`（既有，不改结构）

```python
@dataclass(frozen=True)
class ISegmentSpec:
    segment: str              # cost / amortization / impairment / expense
    label: str                # 中文段名，逐字取自源模板层标题
    source_ref: str           # 'sheet名!单元格'，守卫 openpyxl 交叉比对
    fallback: tuple[str, ...] # 段兜底标准码；空 tuple = 宁缺勿造
    name_keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...]
    claim_priority: int       # 认领顺序，与展示顺序解耦
    absolute: bool            # 备抵段：对聚合结果取绝对值
    credit_is_increase: bool  # 备抵段：credit 是计提
    occurrence: bool          # 损益段：走 trial_balance 本期发生额
```

### `I_CYCLE_ROW_CODES`（改动后）

```python
I_CYCLE_ROW_CODES: dict[str, dict[str, str]] = {
    "I1": {"listed": "BS-032", "soe": "BS-032"},   # 无形资产
    "I2": {"listed": "BS-033", "soe": "BS-033"},   # 开发支出
    "I3": {"listed": "BS-034", "soe": "BS-034"},   # 商誉
    "I4": {"listed": "BS-035", "soe": "BS-035"},   # 长期待摊费用
    "I5": {"listed": "BS-037", "soe": "BS-037"},   # 其他非流动资产
    "I6": {"listed": "IS-006", "soe": "IS-006"},   # 研发费用
}
```

保留 `dict[str, dict[str, str]]` 结构（不塌成 `dict[str, str]`）—— 结构本身表达
「row_code 可能按准则不同」这一平台事实，I 类恰好两准则相同不代表别的循环也如此。
`resolve_row_code(wp_code, standards)` 的签名与行为不变（命中 `soe*` 取 soe 键，否则 listed；
未知 wp_code 返空串），只是两键取值收敛为同值。

### `tb_source_codes` 载荷（既有键，本 spec 只增诊断）

```
{
  segments: [{segment, label, standard[], original[], resolved_from, found}],
  parent_check: {code: {leaf_sum, parent, trial, diff, convention}},
  parent_check_ok: bool,
  chart_conflict: [...],        # report_config 与 account_chart 冲突诊断
  unmapped: [...],             # 未归类叶子（原样透出给前端建行）
  category_defs: [...],        # 仅 I1
}
```

## Correctness Properties

### Property 1: row_code 与 report_config 行名一致
六个 I 循环 × 两准则共 12 个 `I_CYCLE_ROW_CODES` 取值，在 `report_config` 中的 `row_name`
必须命中 `I_CYCLE_EXPECTED_NAMES` 对应循环的期望语义。改动前该断言 **11/12 失败**
（仅 `I6.listed=IS-006` 通过）。

**Validates: Requirements 1.1, 1.7**

### Property 2: 两准则同码
I 类每个循环的 `listed` 与 `soe` 取值必须相同，且四个 `applicable_standard` 下
`row_name` 与 `formula` 均相同。防被按 J1「按变体不同」范式误改成两码。

**Validates: Requirements 1.2**

### Property 3: 零回归（码集与金额）
对每个真实项目 × 每个 I 循环，改动前后的 `standard` / `original` 码集、`tb_values`
全部键值、`parent_check` 全部字段、`adjudication_prefill` 必须逐字节相同；
唯一允许变化的是 `resolved_from`（`fallback` → `report_config`）。

**Validates: Requirements 1.4, 1.5**

### Property 4: 双真源已消除
仓库中「I 循环 row_code」这一语义只允许存在一份声明。`i_cycle_specs.py` 删除后
`SemanticAccountSpec(row_code=...)` 形态的 I 类声明必须为 0；若保留则必须是单向 re-export
（源码级断言其内无独立 row_code 字面量）。反向自检：删除前该断言必须打红（当时有两份）。

**Validates: Requirements 1.3**

### Property 5: 行名校验闸仍在
`row_name_matches` 必须仍被 `resolve_i_cycle_accounts` 调用，且对「行名不符的公式」
返回 False（用替身构造错行名，断言公式被丢弃）。

**Validates: Requirements 1.6**

### Property 6: I5 兜底空且三态可分
I5 `cost` 段 `fallback` 必须为空 tuple；`found=False` 时 `standard`/`original` 均为空列表；
`tb_source_codes` 能区分「无此科目」（`found=False`）与「余额为 0」（`found=True` 且金额 0）。
前端侧断言 I5 审定表与披露 Tab 在 `found=False` 时渲染「本项目无标准科目映射，需手工编制」
文案且不渲染 `0.00`（源码级：该文案存在 + 无 `?? 0` / `|| 0` 兜底把无科目态压成零）。

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 7: I5 反向自检
构造一个含 `1911` 或名为「其他非流动资产」的科目表替身，解析必须命中（证明不是判据写死为空）。

**Validates: Requirements 2.4**

### Property 8: 预设 sheet 名存在于源模板
I 类每个预设块的 `sheet` 值必须存在于对应源 workbook 的真实 tab 名集合。改动前
`审定表I1-1` 这一条必须打红。

**Validates: Requirements 3.1, 3.6**

### Property 9: 预设科目码与公式自洽
每个预设块的 `account_codes` 必须 ⊇ 该块全部公式引用的科目码（区间 `a~b` 端点除外）。
改动前 I2 明细表块（声明 `1704,5301` 而公式用 `6602`）必须打红。

**Validates: Requirements 3.3, 3.4**

### Property 10: 预设幂等
幂等脚本 `--check` 归零；二次 `--apply` 后 `prefill_formula_mapping.json` md5 逐字节不变；
round-trip 自检（`json.dumps` 能复现原文）。

**Validates: Requirements 3.5**

### Property 11: PREV sheet 实参与块名同步
改块 `sheet` 名时，块内公式实参里的旧 sheet 名必须同步改；守卫把实参残留计入欠账。

**Validates: Requirements 3.2**

### Property 12: 披露 sheet 预设登记完备
六循环 12 张披露 sheet 必须或有预设块、或在幂等脚本的显式「无预设」登记表中（带理由）。
有四表可取数的披露格（I1 三段期初/期末、I3 商誉原值与减值、I4 期初/本期摊销/期末）必须给出
`TB()` 公式；取数不可推导者必须是 `PLACEHOLDER` 且 description 非空并写明真源（禁空 description
的 `PLACEHOLDER` —— 那等于「有个格子没人知道从哪来」）。

**Validates: Requirements 4.1, 4.2**

### Property 13: 披露预设禁硬编码客户码
披露块公式中不得出现形如 `AUX('1701','类别','具体编码')` 的项目专属硬编码。

**Validates: Requirements 4.3**

### Property 14: 明细表块禁反引审定表（防成环）
同一 wp_code 内，明细表块的公式不得 `WP()` 引用本循环审定表；跨循环引用合法。

**Validates: Requirements 4.4**

### Property 15: 附注列元数据齐备
listed `五、26/28/31` 与 soe `八、27/32` 涉及的 4 张表 `columns` 长度必须 > 0；
无段落文本泄漏成表名（表名不得以 `[` 开头或长度 > 30）。

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

### Property 16: 列真源三向一致
源 xlsx 披露 sheet 的列头 ↔ 模板 `headers`/`columns[].label` ↔ 同步载荷 `columns[].label`
三者一致（去空白归一后）。

**Validates: Requirements 5.5, 5.7, 8.4**

### Property 17: flat 两处都加
单级表的 `flat` 必须同时出现在模板 `columns` 与同步载荷 `columns`；两级表必须声明 `group`
且不得与 `flat` 并存（`_extract_column_groups` 见任一 `flat` 即整表返 `[]`）。

**Validates: Requirements 5.6**

### Property 18: I1 上市列集与源模板一致
I1 上市披露主表列集必须与源模板 `附注披露信息（上市公司）!B10:M10` 一致（13 列），
或在守卫中登记「模板为动态列形态」的实证理由。

**Validates: Requirements 6.1, 6.2**

### Property 19: I1 类别真源非写死
I1 类别清单必须派生自源模板 `底稿目录!A9:A19`（12 类）+ `A20` 可扩位；
`i1_asset_categories.py` 的类别声明必须带 `source_ref`。

**Validates: Requirements 6.3**

### Property 20: 类别列 key 稳定且非中文
I1 上市类别列 key 必须形如 `{slot}_{seq}`，不得用中文 label 作 key（会撞键）。

**Validates: Requirements 6.4**

### Property 21: 动态可扩行数量与源模板一致
I1 上市 3 处 + I1 国企 4 处 + I2 上市 1 处 `……` 必须实现为可扩行；
I3/I4/I5/I6 必须为 0 处（不得凭空加可扩位）。

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 22: 骨架行数非写死
六循环披露组件源码中不得出现 `blankRows(p, <字面量>)`；行数必须 `max(seed 行数, 1)`。

**Validates: Requirements 7.4**

### Property 23: 动态行 key 不复用已删序号
新增类别的 seq 必须来自持久化单调计数器 `max(现有最大, 已存计数器) + 1`；
反向自检：不传计数器时必复用旧 key（复现旧缺陷形态）。

**Validates: Requirements 7.6**

### Property 24: 动态行新增需命名
需命名的动态行新增必须先 `ElMessageBox.prompt` 输入名称再建行（源码级断言 prompt 调用
在 addRow 之前）。

**Validates: Requirements 7.5**

### Property 25: 自动同步监听实际数据
六循环 12 个披露 Tab 必须接 `useDisclosureAutoSync`，且 `scheduleAutoSync` 不得写在
同步函数内（自调度 = 800ms 周期重复 POST + 骗过覆盖率守卫）。

**Validates: Requirements 8.1**

### Property 26: 宿主传 projectId
六个宿主向披露 Tab 必须传 `:project-id` 或 `v-bind="$props"`（漏传 = 同步永久静默失败）。

**Validates: Requirements 8.2**

### Property 27: 子表名逐字一致
六循环 `X_{LISTED,SOE}_SUBTABLE` 的每个值必须与附注模板 `tables[].name` 逐字一致
（否则产出孤儿子表）。

**Validates: Requirements 8.3**

### Property 28: `_note_texts` 带中文 title 且过滤空
`_note_texts` 每条必须有非空中文 `title`；全空时不产生该键。

**Validates: Requirements 8.5**

### Property 29: 溯源面板已挂载且 prop 合法
六个审定表 Tab 必须渲染溯源面板，且传入的每个属性名都在被调组件 `defineProps` 键集内
（传不存在的 prop = 静默失效，四层验证全查不出）。

**Validates: Requirements 9.1, 9.2**

### Property 30: 带入按钮走共享件
六个审定表的「从四表库带入未审数」必须走 `adjudicationPrefillPlan` 共享件，
不得各自实现 seed 逻辑；手工优先 / 幂等 / 「无此科目≠为 0」三条必须成立。

**Validates: Requirements 9.3**

### Property 31: 宿主 sheet 分发链完整
六个宿主模板中，`currentSheet` 分发链内不得出现裸 `v-if`（紧前同级兄弟为 `v-else-if`
的 `v-if` 即打红）；面板必须与 sheet 内容一起包在 `<template v-else-if>` 内。

**Validates: Requirements 9.4**

### Property 32: 金额控件选型
六循环披露与审定表的金额列必须用 `WpAmountInput`；比率 / 使用年限 / 摊销月份 / 占比列
不得套用（反向边界断言）。

**Validates: Requirements 9.5**

### Property 33: 源模板缺陷登记完备
`I_CYCLE_SOURCE_DEFECTS` 登记表必须覆盖 6 处已实证缺陷（I1 tab 名缺 `-1`、I2 `=#REF!`
15 格、I1 上市「购置/处置」笔误、I6 跨 workbook 引用（非笔误）、I5 序号缺失、
I3 hidden sheet），每条带 `source_ref` 与处置方式。

**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5**

### Property 34: I3 hidden sheet 已 skip
`市场平均收益率2017` 与 `GT_Custom` 必须在 `wp_code_overrides.json` 中按**完整 sheet 名**
标 `skip`（按尾码标会误杀同尾码的真实 sheet）。

**Validates: Requirements 10.6**

### Property 35: 源模板不被反改
本 spec 不得修改 `backend/wp_templates/I/**` 任何 xlsx（源码级断言 + 文件 md5 冻结）。

**Validates: Requirements 10.7**

### Property 36: Wave 1 守卫先打红
Wave 1 交付时，类 B 断言（被测实现）必须全红且失败消息写明「尚未实现（Wave N Task M）」；
类 A 断言（独立口径判据）必须全绿。

**Validates: Requirements 11.1, 11.2**

### Property 37: 变异检验三态
变异脚本必须区分 RED（守卫有效）/ GREEN（守卫缺陷）/ ANCHOR-MISS（脚本缺陷）；
锚点命中数必须恰为 1；备份落 `.bak` 且 `--restore` 可字节级还原。

**Validates: Requirements 11.3**

### Property 38: CI job 路径存在
新增 CI job 引用的每个文件路径必须存在（逐个 `Path.exists()` 断言）。

**Validates: Requirements 11.4**

### Property 39: 零回归前后对照
零回归判据必须是「施加改动前 vs 施加改动后」的前后对照，不得用 `git stash` 或
HEAD-swap（本 spec 改动文件混着并发会话未提交成果）。

**Validates: Requirements 11.5**

### Property 40: 真实库验收与浏览器实测
真实库验收必须覆盖 8 项目 × 6 循环；浏览器实测必须「录 ≥2 行数据 → 目标区域真出数 →
postgres 查落库 → 数据逐项复原」，缺一不算实测。
推送链路的「附注真有数据」只能运行态验证：推送后 `disclosure_notes.last_sync_at` 必须由
NULL/旧值**前移**，且 `sub_table_data` 的表数与本次推送表数一致（源码级守卫做不到这条 ——
子表名逐字一致与 columns 同构都可以静态验，但「写进去了」不能）。

**Validates: Requirements 11.6, 8.6**

### Property 41: 临时产物清理
收口时 `backend/scripts/diagnose/_wip_i_*` 必须清零（本 spec 自己的产物，不动他人的）。

**Validates: Requirements 11.7**

### Property 42: 既有守卫的错基线已改写
`test_i_cycle_accounts.py::TestResolveRowCode` 的 12 个参数化期望值必须与 `report_config`
实证一致（六循环两准则同码）；`test_empty_standards_returns_listed` 的期望必须为 `BS-032`。
该文件当前把 11 个错码逐条钉死为基线，是错码长期存活的直接原因。
反向自检：把任一期望值改回旧错码时 Property 1 必须打红（证明两个守卫互相锁死而非各说各话）。

**Validates: Requirements 1.8**

## Error Handling

| 场景 | 处置 |
|---|---|
| `report_config` 查不到该 row_code | 记 WARNING，退回段兜底码，`resolved_from='fallback'` |
| row_name 与期望语义不符 | 丢弃该公式 + 记 WARNING（现有行为，保留） |
| `account_mapping` 反解为空 | 用标准码本身作原始码前缀（现有行为） |
| 段兜底码为空且按名定位失败 | `found=False`，`standard`/`original` 空列表，前端显「本项目无此科目」 |
| `tb_balance` 查询失败 | fail-open 返 `[]` + WARNING，render 不阻断 |
| 叶子和与父额不平 | `parent_check.diff` 如实暴露，`parent_check_ok=False`，溯源面板告警 |
| `report_config` 与 `account_chart` 冲突 | `chart_conflict` 诊断输出，不擅自改 `report_config` |
| 幂等脚本 round-trip 自检失败 | exit 2 拒绝写盘（防重排整个 JSON 与并发会话互相回退） |
| 附注推送段边界解析失败 | fail-closed 跳过该表写入，绝不退化整表覆盖 |

## Testing Strategy

| 层 | 手段 |
|---|---|
| 类 A 独立口径 | 连库查 `report_config` 自行对账；openpyxl 直读源 xlsx；冻结基线 |
| 类 B 被测实现 | 真跑 `resolve_i_cycle_accounts` / 幂等脚本 `--check` / 读模板 JSON |
| 交叉锁死 | 前端守卫 `fs.readFileSync` 读后端 py 源码抽常量比对 |
| 反向自检 | 每个「必须为空 / 必须不存在」类断言都配「构造替身使其非空则命中」 |
| PBT | 段认领互斥性、叶子聚合守恒、动态行 key 不撞 |
| 变异检验 | `mutate_i_cycle_guards.py`，三态区分 + 字节级还原 |
| 真实库 | `verify_i_cycle_live.py`（只读，8 项目 × 6 循环六态输出） |
| 浏览器 | chrome-devtools 隔离上下文，录数据 → 出数 → 落库 → 复原 |
