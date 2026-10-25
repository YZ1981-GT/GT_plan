# Design Document

## Overview

F5 营业成本从 legacy 假双向接成真双向：canary 取 F5-8（重大调整核查表，F5 唯一无 BP-7 的动态行表），
先修 BP-7 三处，再扩到 F5-5 → F5-3 → F5-2（12 行月度矩阵）→ F5-7（21 固定行 + 模板缺陷）→ F5-1 其他业务区；
F5-1 主营区判 HTML-only、F5-4 / F5-6 只做核。

F5 是 F 循环里**红基线最多**的 entry（7 条），且其中三条是**必须先修才能受管**的硬前置：
BP-7 三处（B4）、模板 `G31` 漏算 7 项（B2）、F5-2/F5-1 容量不一致（B3）。
另有两条是「F5 独有的极端情况」：公式管理页预设为 **0**（B1）、真库载荷为 **0**（需 seed 才能验收）。

F 循环共同裁决 FC-1~FC-13 见 `f1-sync-coverage-and-first-canary/design.md`。

## 上游锚定

沿用 F1 spec 上游锚定表。额外：
- **F2 spec** —— 模板缺陷走覆盖层的处置（F2-26!J9）是 F5-7!G31 的直接先例
- **F3 spec** —— FC-11 工具链根因修复由它负责；F3-H2「FC-5 例外」的裁决结构（三方向并列 + 默认最低风险）被 F5-7 复用
- **E1-2** —— 模板预填行登记范式（`PREFILLED_CURRENCY_ROWS_E102`）用于 F5-3 的三行预填标签
- `phase5_d4_*` 月度矩阵声明（D4-2 同型 12 月列）—— F5-2 的 `months[12]` nested 路径先例

## Architecture

### 接入顺序（前置驱动 + 形态驱动）

```
[BP-7 三处修复]                                   ← 硬前置，先做
F5-8 重大调整（canary：数据区零公式 / 无 BP-7 / 无 footer / 零跨 sheet）
  → F5-5 比较分析（6 行 + 合计；含除零变动率列）
  → F5-3 其他业务成本（11 行 + 三行预填标签）
  → [容量裁决] F5-2 月度明细（12 行 × 12 月列；nested months 路径）
  → [模板覆盖层修 G31] F5-7 成本倒轧（21 固定行稳定 rowKey）
  → F5-1 其他业务区（主营区 HTML-only）
F5-4：FC-6 可行性核　F5-6：形态核（244 公式三块，后置）
```

### 声明层结构

```
backend/app/services/workpaper_sync/
  phase5_f5_cost_of_sales.py        ← entry 层 provider
  phase5_f5_08_major_adjustment.py  ← canary
  phase5_f5_05_comparison.py
  phase5_f5_03_other_cost.py
  phase5_f5_02_monthly_detail.py
  phase5_f5_07_cost_rollforward.py
  phase5_f5_01_adjudication.py      ← 仅其他业务区一个 spec（主营区 HTML-only）
backend/data/workpaper_sync_contracts/f5.cost_of_sales_detail.json
backend/scripts/gen/generate_phase5_f5_contract.py
backend/scripts/e2e/seed_f5_publish_e2e.py   ← 🔴 真库零载荷，验收前必须 seed
```

### 受管区清单（逐格实测几何）

| sheet_key | managed_sheet | store_item_id | 行身份 | 表头 | 数据 | footer | UUID | formula_columns |
|---|---|---|---|---|---|---|---|---|
| `f58-managed` | 重大调整核查表F5-8 | `F5-8-rows` | `id` | R12/R13 | R14-29 | R30「三、审计说明」(无合计) | I | （无） |
| `f55-managed` | 与上年度比较分析表F5-5 | `F5-5-comparison-rows` | `id` | R9/R10 | R11-16 | R17「合计」 | P | D,G,H,I,J,K,L,M |
| `f53-managed` | 其他业务成本明细表F5-3 | `F5-3-other-cost-rows` | `id` | R9/R10 | R11-21 | R22「合计」 | O | E,F,J,K,L,M |
| `f52-managed` | 主营业务成本月度明细表F5-2 | `F5-2-monthly-rows` | `id` | R9/R10 | R11-22 | R23「合计」 | Y | N,Q,U,V,W |
| `f57-managed` | 成本倒轧表F5-7 | `F5-7-cost-rollforward` | `rowKey` | R10 | R11-31 | R32「三、审计说明」(无合计) | I | G（+派生行的 E/F/H） |
| `f51-other` | 营业务成本审定表F5-1 | `F5-1-adj-other-rows` | `rowKey` | R6 | R20-25 | R26「小计」 | Task 2 实测 | E,I |

不受管：F5-1 主营区（`F5-1-adj-main-rows`，裁决 F5-H3）· F5-4（FC-6）· F5-6（后置）· 底稿目录 / F5A / GT_Custom。

## Data Models

不新增数据模型。store 形态：`rows` + 行身份 `id`（F5-2/3/5/8）· `rows` + 稳定 `rowKey`（F5-7 / F5-1 其他业务区）。
F5-2 的 `months[12]` 用 nested json 路径（`months/0`…`months/11`），走引擎既有的 `resolve_json_path`（D4-2 同型）。

## 关键裁决

### 裁决 F5-H1：canary 选 F5-8

| 候选 | 数据区公式 | BP-7 | footer | 跨 sheet | 结论 |
|---|---|---|---|---|---|
| F5-2 月度明细 | 5 列 | 🔴 有 | 有 | F5-1 引它 167 处 | 面最大 |
| F5-5 比较分析 | 8 列（含除零） | 🔴 有 | 有 | 0 | 次选 |
| F5-3 其他业务 | 6 列 | 🔴 有 | 有 | F5-1 引 | 次选 |
| **F5-8 重大调整** | **0** | **无** | 无（锚行） | 0 | ✅ |

F5-8 同时验证两件事：**从零 canary 链路**（FC-1）与**无 footer 合计的锚行处置**（需求 1.4）——后者在 F5 有两张
（F5-7 / F5-8），先在最简的那张验通。

### 裁决 F5-H2：F5-7!G31 是 FC-5 的第二个例外 —— 模板错、前端对

与 F3-H2（F3-4 应计利息）不同的是：F3-4 的模板式只是**口径更粗**（漏天数折算），而 F5-7!G31 是**引用越界空区**
（`G56:G61` 在 36 行的 sheet 里根本不存在），求值恒为 0 ⇒ 审定数列的主营业务成本静默漏掉 6 项。这不是口径分歧而是
**模板 bug**。裁决：
- 默认①：经模板覆盖层修为 `=G24+G25+G26-G27-G28-G29-G30`（与 E/F/H 三列同型，形态可自证正确）
- 备选②：`G` 列整列 HTML-only + UI 中文提示

否决「以模板为权威修前端」——那等于把正确算法改错。🔴 本裁决与 F2-H5（F2-26!J9 走覆盖层）同源，
两者共同确立 F 循环的规则：**模板缺陷走覆盖层，FC-5 只适用于「两边都对、口径不同」的情形**。

### 裁决 F5-H3：F5-1 主营区 HTML-only（零 editable 字段）

模板 R8-17 的 A/B/C/D/F/G/H 七列全是 `='主营业务成本月度明细表F5-2'!X{r}`，E/I 是本行加总 ⇒ **整区零可编辑格**。
受管它只会把 F5-2 的派生值物化进 Excel 再读回 store，形成与 F5-2 的双源。判据：`F5-1-adj-main-rows` 不在
`all_store_item_ids()`。前端该键的 add/del 仍保留（HTML 侧的行管理不受影响）。

### 裁决 F5-H4：容量不一致按「≤10 行才受管」降级

三层容量：前端任意行 / F5-2 模板 12 行 / F5-1 主营区 10 槽。且 F5-2 自己的合计 `R23=SUM(N11:N22)` 覆盖 12 行 ⇒
品种数 11~12 时 `F5-1!B18 ≠ F5-2!N23`（模板内部就不一致，与本 spec 无关）。裁决同 F3-H5 / F4-H4：
**F5-2 品种数 ≤10 时受管，>10 时整表降级 legacy + 中文提示**（提示点明「超出审定表主营区槽位，F5-1 小计将漏算」）。
否决改模板（扩 F5-1 槽位或改 F5-2 SUM 区间都会动权威模板结构）。

### 裁决 F5-H5：F5-2 的 12 月列用 nested 路径，不展平

前端 `MonthlyDetailRow.months: number[]`（12 元素）。契约 field 的 `json_key` 用 `months/0`…`months/11`
（引擎 `resolve_json_path` 支持，D4-2 / D3 账龄组同机制）。否决展平成 `month1`…`month12` 顶层键 ——
那要改前端存储结构、影响 `updateMonth(id, monthIndex, value)` 与全部读方。

### 裁决 F5-H6：BP-7 三处一次修完，不分 spec

`useF5MonthlyDetail:133` / `useF5OtherCost:146` / `useF5Comparison:128` 三处同型（`?? \`prefix-${i}\``）。
按「触类旁通」铁律一次修完并加统一判据（含下标模式的 id 在载入后被重铸），不是「接哪张修哪张」。
🔴 slice 的 BP-7 `must_fix_before`（「把 `xlsx/gt-f5-cost-of-sales` 标 bidirectional 之前，也在 step 6 发布 contract 之前」）
把它定为双向硬前置，本 spec Task 顺序据此安排（BP-7 修复在 canary 与契约发布之前）。
🔴 其中只有 `useF5MonthlyDetail:133` 是 slice 原文登记的；另两处是本 spec 触类旁通实测新增。

### 裁决 F5-H7：真库零载荷 ⇒ 验收必须先 seed

F5 全部键真库 0 行（F 循环唯一）。canary 验收若直接跑，会出现「空表往返也算 `store_mirrored`」的假绿。
裁决：交付 `seed_f5_publish_e2e.py`（照 D4/E1 lane 的 seed 脚本范式），验收前 seed 最小载荷（F5-8 两行）。
wp_code 裁决条目的 `max_payload_bytes` 如实写 **0**，不伪造。

## Error Handling

| 场景 | 处理 | 依据 |
|---|---|---|
| 无 footer 合计（F5-7 / F5-8） | footer 指向下一锚行 + `footer_carries_total_formula=False` | 需求 1.4 |
| F5-5 变动率除零 | extract 记 `type_normalization_failure` + 保留原值 + 不入 store（PROTECTED_MODES） | 需求 4.4 |
| F5-2 品种数 > 10 | 整表降级 legacy + 中文提示（点明 F5-1 小计将漏算） | F5-H4 |
| F5-7!G31 未修 | G 列不受管 + UI 提示；不得以模板为权威 | F5-H2 |
| 行 id 含下标模式 | 载入即重铸并回写；判据必红 | F5-H6 |
| legacy 键被二次写入 | 判据必红（只写主键） | 需求 2.3 |
| F5-3 三行预填标签被当空行裁剪 | 登记为预填行（E1-2 范式） | 需求 4.2 |
| 真库零载荷直接验收 | 必须先 seed，否则算假绿 | F5-H7 |
| 发布链第③环缺供给 | 如实 `upstream_gap` | BP-61-1 |
| sync 路径触发 TB 写 | 判据必红 + CI 守卫 | FC-9 |

## Correctness Properties

🔴 编号 spec-scoped：`Property N` 读作 `F5-P{N}`。

### Property 1: canary 打通后 migration_state 与 legacy_reasons 正确变更
**Validates: 1.6**　`legacy_fake_bidirectional → adapter_registered`，三条 `legacy_reasons` 全消。
变异：跳过发布链任一环 ⇒ 状态不变。

### Property 2: `F5C` 幻影码与真码 `F5` 隔离 + 零载荷证据如实
**Validates: 1.2, 1.3**　①`_index.json` 无 `F5C` ②`assert_no_implicit_template_fallback('F5C')` 通过
③provisioner JOIN `wp_index` 用 `["F5"]` ④裁决条目 `max_payload_bytes == 0` 且附「F5 全部键真库 0 行」原文。
变异：用 `F5C` 查 finder / wp_index ⇒ 必红；把 `max_payload_bytes` 写成非 0 ⇒ 证据核对必红。

### Property 3: 无 footer 合计的两张表按锚行处置
**Validates: 1.4, 2.4**　F5-8 `footer_row=30` / `footer_marker="三、审计说明"` / `footer_carries_total_formula=False`；
F5-7 同款（R32）。变异：置 `True` ⇒ 引擎期待合计公式而锚行无公式，必红。

### Property 4: `store_item_id` 取主键不取 legacy 读回退键
**Validates: 2.1, 2.2**　变异 ①`F5-2-monthly-rows → F5-2-rows` ②`F5-7-cost-rollforward → F5-7-rows`（不存在）
⇒ 投影恒空必红；另断言受管区总数 == 6，legacy 键不产生额外 binding。

### Property 5: 受管后只写主键、legacy 键不被二次写入
**Validates: 2.3**　roundtrip 后 `F5-2-rows` / `F5-3-rows` / `F5-5-rows` / `F5-6-rows` / `F5-8-conclusion` 五个
legacy 键的 `updated_at` 不变；前端读回退仍能读到旧载荷。变异：回写同时写双键 ⇒ 漂移，必红。

### Property 6: UUID 列扩列不破坏打印区域
**Validates: 2.5**　F5-2 `Y` / F5-3 `O` / F5-8 `I` 三处 UUID 列 ≥ `max_col`；instrumentation 写入后
`print_area` / `page_setup` 与基线一致（逐属性比对）。

### Property 7: 宿主 `isHtmlSheet` 门控与两条 window 监听不回归
**Validates: 1.7**　接桥后 ①未迁移 sheet 仍走 legacy 兜底分支 ②`f5:save-items` 与 `substantive:adjudicated`
监听仍注册且 F5-7 校验区能取到 6401 审定数。变异：移除任一监听 ⇒ 校验区取数为空，必红。

### Property 8: 真库零载荷 ⇒ 必须 seed 后才三谓词
**Validates: 1.8**　未 seed 时验收脚本 SHALL 显式失败（不得因空表往返而判 `store_mirrored`）；
seed 两行后三谓词全绿。变异：允许空载荷通过 ⇒ 假绿，必红。

### Property 9: BP-7 三处载入即重铸稳定身份
**Validates: 3.1, 3.2, 3.3**　构造缺 `id` 与含下标型 id 的旧载荷 ⇒ 载入后全部 id 不匹配
`^(m-\d+-\d+|oc-migrated-\d+|cmp-migrated-\d+)$` 且已回写；插删行后同一逻辑行 id 不变。
变异：恢复任一处 `?? \`prefix-${i}\`` ⇒ 必红（三处各一个变异）。

### Property 10: 三张行表双模式派生列等价
**Validates: 4.1, 4.2, 4.3**　hypothesis（`max_examples=5`）：F5-5 `D=B*C` / `G=E*F` / `H,I,J` 差额、
F5-3 `E=B+C+D` / `J=G+H+I` / `L=E-J`、F5-2 `N=SUM(B:M)` / `Q=N+O+P` / `U=R+S+T` 的前端算值 == 模板公式求值。

### Property 11: F5-5 变动率除零符合实测语义
**Validates: 4.4**　构造上期为 0 行 ⇒ ①前端返 `'N/A'` ②extract 不抛、异常类型 `type_normalization_failure`
③store 中该字段不出现 `#DIV/0!`。变异：把 `K/L/M` 标 `editable` ⇒ 错误值进 store，必红。

### Property 12: F5-3 三行预填标签不被当空行裁剪
**Validates: 4.2**　空载荷 materialize 后 R11-13 仍为「出租固定资产 / 出租无形资产 / 出租包装物和商品」。

### Property 13: F5-2 `months[12]` nested 路径往返
**Validates: 4.3**　12 个 `json_key` 为 `months/0`…`months/11`；OO 改 B-M 任一格 ⇒ 对应下标元素变更，其余 11 个不变。
变异：展平成 `month1`…`month12` ⇒ 投影恒空必红。

### Property 14: F5-7 21 个固定 rowKey 逐字一致 + 派生行不 editable
**Validates: 5.1, 5.3**　rowKey 序列与 `F57_ROW_DEFS` 逐字相等（顺序敏感）；
四个 `rowType='formula'` 行（`directMaterialCost` / `productProductionCost` / `finishedGoodsCost` / `mainBusinessCOGS`）
的 E/F/H 列 `mode=formula`。变异：任一派生行标 editable ⇒ 必红。

### Property 15: F5-7!G31 修复后两侧审定数相等
**Validates: 5.2**　覆盖层生效路径：`G31` 求值 == 前端 `calcF57MainBusinessCOGS` 的审定口径结果；
降级路径：`G` 列不在 `field_specs` 且 UI 提示存在。变异：直接受管未修的 `G31` ⇒ 两侧不等，必红。

### Property 16: `F5-7-adjudicated-cogs` 不进 field_specs
**Validates: 5.4**　该键不在 `all_store_item_ids()`（跨表注入值）；校验区消费行为由 P7 守护。

### Property 17: F5-1 主营区判 HTML-only
**Validates: 6.1**　`F5-1-adj-main-rows` 不在 `all_store_item_ids()`；证据含「R8-17 七列全为引 F5-2 的公式、零 editable」。
变异：把主营区纳入受管 ⇒ 与 F5-2 双源，回写后 F5-2 与 F5-1 值可分叉，必红。

### Property 18: F5-2 容量裁决 —— ≤10 受管 / >10 降级且不丢数据
**Validates: 6.2, 4.5**　构造 12 品种载荷 ⇒ ①受管判定为关 ②legacy 读到全 12 行 ③中文提示含
「超出审定表主营区槽位」「F5-1 小计将漏算」。变异：无条件受管 ⇒ 11/12 行静默不进 F5-1，必红。

### Property 19: F5-1 其他业务区 formula_columns 实测 + FC-10 在 F5 不命中
**Validates: 6.3, 7.3**　①其他业务区仅 `E,I` 为 formula（B/C/D/F/G/H 手填）
②逐列断言模板全部百分比格式列（F5-2 `V,W` / F5-3 `F,K,M` / F5-5 `K,L,M`）均为 `mode=formula` ⇒ FC-10 不命中。
变异：把任一比例列标 editable ⇒ 前端百分数 × 模板小数格式，必红。

### Property 20: F5-1 受管后 sync 路径 TB 写次数为 0
**Validates: 6.4**　`publishToTb`（科目 6401、发生额口径）仍是唯一入口。变异：sync 回写里调 `publishToTb` ⇒ 必红。

### Property 21: FC-11 数据侧 —— F5 预设数从 0 变 14
**Validates: 7.2**　①块 `[226]` 的 `items` 键数为 0、`cells` 14 条
②`convert_prefill_presets()['workpaper:F5']` 长度 == 14（现状 0）
③块内 `PREV('F5','营业务成本审定表F5-1','审定数')` 的 sheet 名在模板中存在。
变异：保留 `items` 形态 ⇒ 预设数仍为 0，必红。

### Property 22: 其余 10 个 contract golden digest 不变
**Validates: 7.4**

### Property 23: 公式管理入口两模式可达 + 未接 sheet 显式登记假双向
**Validates: 7.1, 7.6**　入口 owner 唯一（F-SHELL）、F5 宿主 emit 0 次；F5-4 / F5-6 / F5-1 主营区在 slice 中
显式登记为 legacy 假双向（不静默遗漏）。

### Property 24: 零写入读键登记而不误接
**Validates: 7.5**　`D4-1-adj-main-rows` / `F5-2-detail-rows` 不在 `all_store_item_ids()`，证据记录其为兼容回退。

## Testing Strategy

红判据先行：阶段 0 先打红 P2 / P9 / P15 / P18 / P21（五条对应五条红基线）。
后端 pytest（`$env:PYTHONIOENCODING='utf-8'`，PBT `max_examples=5`）；前端 vitest；
真栈 Playwright `--workers=1`，fixture `e2e/fixtures/f5-l2-cases.json`。
🔴 F5 真库零载荷 ⇒ 全部真栈用例前置 `backend/scripts/e2e/seed_f5_publish_e2e.py`（P8 守护该前置不被跳过）。

## 顺带发现（登记，不在本 spec 处理）

1. 模板 sheet 名错字「**营业务**成本审定表F5-1」（应为「营业成本」）—— 改名会动 sha256 与 135 处跨表引用，
   属模板治理债；本 spec 反向要求 prefill 配置**对齐错字**（需求 7.2），否则解析不到。
2. 3 个残留 definedName（`AS2DocOpenMode` / `a暗暗` / `ffd`）—— 后两个明显是手工误建，建议 F 循环收口后统一清理。
3. F5-6（244 公式 / 分厂×产品×12 月三块）是 F 循环单 sheet 公式数最多的表，且 store 带 `F5-6-quantity-recon-plants`
   维度键 ⇒ 建议另立 spec（与 F2-64 IPO 册同属「多块矩阵」形态族）。
4. `F5-7-adjudicated-cogs` 这种「宿主监听事件写入他表 store」的跨表注入模式，全仓仅此一处 ⇒
   建议加 CI 守卫「store 写入方必在该 store 的 owner composable 内」，防止扩散。
