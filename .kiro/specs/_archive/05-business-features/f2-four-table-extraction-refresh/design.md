# Design Document

## Overview

把 F2-1 存货审定表的四表库取数从「一次性静默 seed（口径不稳健、无刷新、公式不可见）」升级为「**显式 `TB()` 取数公式驱动、可查看可编辑、可 🔄 刷新**」，对齐 E1 货币资金四表面板与 D 循环 `d_cycle_extraction` 已证范式。

核心不变量：**只新增取数公式列出 / 刷新 / 口径修正，不删除或改写既有 seed / F2-3~13 明细跨表带入 / F2-14 调整分录 / 审定 TB 核对 / 附注联动 / 导入导出**（灰度 `F2_FOUR_TABLE_EXTRACTION_ENABLED` 默认关时逐字节等价当前）。

### Wave 0 已验证事实（逐文件核实，非猜测）

| 事实 | 出处 | 对设计的影响 |
|------|------|-------------|
| F2-1 anchor = `F2-1-{block}-{rowKey}-{field}`，block∈{gross,impairment}，field∈{opening,increase,decrease,adjustment}，值存 `checklist_responses.conclusion` | `useF2Adjudication.ts::itemId` / `loadField`（读 `.conclusion`） | 取数写 opening/increase/decrease 三字段的 `conclusion`；adjustment 不动（来自 F2-14 跨表） |
| 原值 12 类 → block=`gross`（rowKey raw-materials..price-difference，账户 1401-1412）；跌价 1471 → block=`impairment`（rowKey `impairment-provision`） | `F2_CATEGORIES` / `buildBlockRows` | 取数公式锚点分两块 |
| 账户映射前后端一致 | 前端 `F2_ROW_KEY_ACCOUNT`(useF2CrossSheet) ∥ 后端 `F2_CATEGORIES` | 预设/锚点/聚合共用同一 rowKey→account 表 |
| 现 `_build_adjudication_prefill` 用 `_row_depth`+`by_depth[max]` 深度启发式；前端 seed 用 `closing−opening` 粗猜 increase/decrease | `_f2_inventory_main.py` / `useF2Adjudication.seedFromTbValues` | **口径 bug**：改 `_is_leaf` 叶子判定 + 分别取借/贷发生额 |
| **🔴 共享评估器 `wp_formula_eval_service._resolve_tb` 查 `TrialBalance`**，`_COLUMN_MAP` 只支持 期末余额/审定数→audited_amount、年初余额/期初余额→opening_balance、未审数→unadjusted_amount、AJE/RJE 调整；**无 借方/贷方发生额，无 tb_balance 访问** | `wp_formula_eval_service.py` | **决定性**：F2 `TB()` 语义（tb_balance 未审取数）≠ 通用 `TB()`（trial_balance 审定核对）→ F2 必须自有 tb_balance 求值服务，**不改共享 `_resolve_tb`**（改它污染全平台 TB() 语义） |
| `find_unsupported_formula_functions` 是纯字符串检测（AUX/PREV/LEDGER/COUNT_LEDGER） | `wp_formula_eval_service.py` | 保存校验复用（不依赖 DB / 不 eval） |
| d 循环已备 `_is_leaf` / `get_active_filter` / `resolve_effective`（预设∪用户 wp_formula 读时收敛，禁用>custom>预设）/ `anchor_registry.is_known_anchor` / `tier_a_seed`（render transient seed，手工优先，fail-open） | `d_cycle_extraction/{prefill,presets,anchor_registry,tier_a_seed}.py` | 复用 primitives 与范式，不另造 |
| d 循环 Tier A = trial_balance 审定核对标量（走 generic evaluator）；Tier B = tb_balance 未审 seed | `presets.tier_a_semantic` / `tier_b_provenance` | **F2 与 d 循环的语义差异**：F2 Tier A 就是 tb_balance 未审取数（因 F2-1 类别=科目可干净表达），非 trial_balance 审定核对 |

### F2 相较 D 循环的核心差异（决定 F2 走 Tier A tb_balance 取数）

D 循环审定表按信用风险组合/账龄/客户分类，TB 科目总额**无该维度** → 分类未审只能由明细 SUMIF 派生，四表库只能取「TB↔审定核对标量」（Tier A = trial_balance 审定核对，走 generic evaluator）；F2-1 是 **13 个固定类别、每类恰好一个科目**，故每类别的期初/增加/减少**能干净表达为 tb_balance 取数** → F2 Tier A = **tb_balance 未审取数**（新求值路径），这是本 spec 与 d 循环范式的关键分野。

---

## Architecture

### 决策 1（核心）：F2 `TB()` = tb_balance 未审取数，走 F2 专属求值服务，不改共享 `_resolve_tb`

- **问题**：共享 `wp_formula_eval_service._resolve_tb` 读 `trial_balance` 且列名映射到审定/未审列，**无法**表达 tb_balance 的期初/借方发生额/贷方发生额；改它会把全平台每个底稿的 `TB()` 语义从「trial_balance 审定」改成别的 → 严禁。
- **决策**：F2 的取数公式 `TB(account, 列)` / `ABS(TB(account, 列))` 由**新建 F2 专属服务 `f2_extraction`** 求值，读 `tb_balance`（复用 `_is_leaf` + `get_active_filter`），列名映射：`期初余额→opening_balance` / `期末余额→closing_balance` / `借方发生额→debit_amount` / `贷方发生额→credit_amount`。该服务是**预填（render seed）/ 刷新 / 公式管理面板取值**三处的**单一真源**（同 `get_active_filter` + 同叶子判定 + 同类别聚合，Property 一致性）。
- **语义消歧**：F2 面板每条公式标注「四表库未审取数（tb_balance，≠ 通用 TB() 的 trial_balance 审定核对）」（对齐 E1 四表面板早已用 `TB('1001','期末余额')` 表 tb_balance 取数的先例；d 循环 `tier_a_semantic` 的镜像思路）。
- **generic evaluator 的角色**：仅用于**保存时的语法/不受支持函数校验**（`find_unsupported_formula_functions`，纯字符串）；**绝不**用它求 F2 公式的值（否则 `借方发生额` 落到 `audited_amount` 返错值）。

### 决策 2：复用 d 循环预设读时收敛范式（预设 ∪ 用户 wp_formula）

- 新建 `backend/data/f2_extraction/f2_extraction_presets.json`（结构镜像 `d_cycle_extraction_presets.json`：`{ "F2": [ {sheet_name, anchor, expression, formula_type, description}, ... ] }`）。
- 新建 `f2_extraction/presets.py`（镜像 d 循环 `presets.py`）：`load_f2_presets()` mtime 缓存 + `resolve_effective(db, wp_id, project_id)`（预设 ∪ 用户 `wp_formula`，每锚点唯一，**禁用 > 用户 custom > 预设**，anchor 经 `is_known_anchor` 校验，未知丢弃 + 告警）。**不复用 d 循环的 `resolve_effective`**（它按 `wp_code` 从 d 循环预设文件读；F2 用自己的文件），但**结构逐一对齐**，禁用标记语义（`category=='__disabled__'` 或空表达式）一致。
- 锚点注册：新建 `f2_extraction/anchor_registry.py`（或扩 d 循环 anchor_registry 支持 F2）——`is_known_anchor(anchor)` 校验 anchor ∈ F2-1 真实锚点集合（36 = 13 类 × 3 字段，见 Data Models），防写到不存在字段（R6.4）。

### 决策 3：类别级 tb_balance 聚合（区别 d 循环 per-leaf）

- d 循环 `build_d_adjudication_prefill` 返回 **per-leaf 子科目行**；F2 需 **per-category 聚合**（每类别=一科目，聚合其全部叶子子科目的 opening/debit/credit/closing）。
- 复用 `_is_leaf`（防中间级 rollup 双算）+ `get_active_filter`；新建 `f2_extraction/extract.py::extract_f2_category_values(ctx)`：对每个 `F2_CATEGORIES` 的 account，取 `code == account or code.startswith(account)` 的行、只留叶子、按 field 分别 SUM：
  - 原值类（1401-1412）：`opening = Σ opening_balance`、`increase = Σ debit_amount`、`decrease = Σ credit_amount`、`closing = Σ closing_balance`。
  - 跌价 1471（备抵）：`opening = abs(Σ opening_balance)`、`increase(计提) = abs(Σ credit_amount)`、`decrease(转回/核销) = abs(Σ debit_amount)`、`closing = abs(Σ closing_balance)`。
  - 全零/无名子科目跳过；无子科目 → 该类别不产出（Property）。
- **公式驱动**：`extract_f2_category_values` 消费 `resolve_effective` 的有效公式（parse `TB(account,列)`/`ABS(...)` → 决定该锚点取哪个 account 的哪个 tb_balance 列），使「编辑公式 → 取数改变」为真。默认预设公式即上述标准映射，用户覆盖某锚点公式则按其 account+列取。

### 决策 4：公式管理 surface + 编辑（复用 wp_formula CRUD，值走 F2 service）

- `wp_surfaced_f.py` 的 F2-1 条目：把现有模糊「取自 F2-3~13 明细」「取自 F2-14 调整」**替换/补充**为显式 `TB(account,列)` 四表库取数条目（每锚点一条，附 `sheet_codes=['F2-1']`、`semantic`、`value`=F2 service 当前值）。
- 编辑经既有 `PUT /api/workpapers/{wp_id}/formulas`（不新造 CRUD）。**保存校验** = `find_unsupported_formula_functions`（拒 AUX/PREV/LEDGER → 422）+ **F2 列名校验**（表达式列名 ∉ {期初余额,期末余额,借方发生额,贷方发生额} → 422，避免 trial_balance-only 列如「审定数」误入）。
- 「恢复默认」= 删除用户 `wp_formula`（既有能力）→ resolve_effective 回落预设。
- GET 面板列表按选中 sheet（F2-1）过滤（复用 E1/D 的 sheet_codes 过滤，不逐条重求值，值由 surfacing 一次算好）。

### 决策 5：🔄 刷新入口（E1 范式）+ 覆盖确认

- F2-1 审定表工具栏「🔄 从四表库刷新取数」（受编辑权限门控，灰度关时不显示）。
- 点击 → 前端调刷新（或本地用 render 已带的 `tb_values`）→ 对每类别，若锚点**已有手工值**或 `isFromCrossSheet`（F2-3~13 明细带入）→ `ElMessageBox.confirm`（提示将以四表库值覆盖），确认后才覆盖；否则直接填（对齐 E1 `E1FourTableSourcePanel` 🔄重新取数）。
- 刷新后展示各类别取数 provenance（期初/增加/减少/期末 + 来源 `TB()` 公式），审计师可核对（对齐 E1 source 面板）。
- 刷新值与 render 预填、公式管理面板取值**同 F2 service 同快照** → 三处口径一致。

### 决策 6：Tier B render seed 口径修正 + 灰度

- `_build_adjudication_prefill` 改为委托 `extract_f2_category_values`：返回 `{rowKey: {opening, increase, decrease, closing}}`（新增 increase/decrease，不再让前端 `closing−opening` 粗猜）；`_is_leaf` 替 `_row_depth`+`by_depth[max]`（防双算）；分别取 `opening_balance`/`debit_amount`/`credit_amount`。
- 前端 `seedFromTbValues` 改为直接填 opening/increase/decrease 三字段（不再 `closing−opening`）。
- **手工/明细优先**：render 仅在无持久化 `F2-adjudication-data` 且各 F2-1 锚点未编辑时 seed（保持现有 `has_persisted_adjudication` 门控）；覆盖走决策 5 的 confirm。
- **灰度** `F2_FOUR_TABLE_EXTRACTION_ENABLED`（默认 False）：关闭时 render 输出 `adjudication_prefill`/`tb_values` 保持**当前口径逐字节等价**（旧 `_build_adjudication_prefill` 路径），无刷新入口、无显式公式 surface。开启时走新口径 + 刷新 + 公式 surface。

### 数据流

```
tb_balance ──(get_active_filter + _is_leaf + 类别聚合)──┐
                                                        ▼
              resolve_effective(预设∪用户wp_formula) ─→ extract_f2_category_values
                                                        │  (单一真源)
                    ┌───────────────────────┬───────────┴───────────┐
                    ▼                       ▼                        ▼
        render Tier B seed          🔄 刷新取数              公式管理面板取值
     (adjudication_prefill,       (前端确认后回填          (wp_surfaced_f 条目
      空表时,手工/明细优先)         opening/increase/         value + semantic)
                    │                decrease 锚点)                 │
                    ▼                       ▼                        ▼
        F2-1-{gross|impairment}-{rowKey}-{opening|increase|decrease}.conclusion
```

---

## Components and Interfaces

### 后端新增 `backend/app/services/f2_extraction/`

- `__init__.py`
- `presets.py`：
  - `load_f2_presets() -> list[dict]`（mtime 缓存读 `f2_extraction_presets.json`，缺失→[]）
  - `resolve_effective(db, wp_id, project_id) -> list[Binding]`（预设∪用户 wp_formula，禁用>custom>预设，anchor 校验）
  - `f2_tier_a_semantic(expression) -> str`（「四表库未审取数（tb_balance …）」标注）
- `anchor_registry.py`：`F2_ANCHORS: frozenset[str]`（36 项）+ `is_known_anchor(anchor) -> bool`
- `extract.py`：
  - `parse_tb_formula(expression) -> tuple[str, str, bool] | None`（→ (account, column, is_abs)；仅 `TB('c','列')` / `ABS(TB('c','列'))`；列 ∈ 四列集；非法→None）
  - `extract_f2_category_values(ctx, effective_bindings) -> dict[rowKey, {opening, increase, decrease, closing, formulas: {field: expr}, source_codes: list}]`（复用 `_is_leaf`/`get_active_filter`；跌价 abs 反转；空/异常 fail-open）
  - `F2_ROW_KEY_ACCOUNT`（与前端一致，单一真源，或从 `_f2_inventory_main.F2_CATEGORIES` 派生）
- `surface.py`：`build_f2_surfaced_formulas(db, wp) -> list[dict]`（供 `wp_surfaced_f.py` 调用；每锚点一条 `{anchor, expression, sheet_codes:['F2-1'], semantic, value, source, tier:'A', editable:True}`）

### 后端改动（additive / 灰度门控）

- `_f2_inventory_main.py::_build_adjudication_prefill`：灰度开 → 委托 `extract_f2_category_values`（新口径，返回 opening/increase/decrease/closing）；灰度关 → 保留旧路径（逐字节等价）。render 输出 `tb_values` 结构扩为含 increase/decrease（灰度关时仍旧 {opening, closing}）。
- `wp_surfaced_f.py`：F2-1 条目改由 `build_f2_surfaced_formulas` 提供（灰度开）。
- PUT `/formulas` 保存校验：对 F2 wp（wp_code 前缀 F2）追加 F2 列名校验分支（`find_unsupported` + 列 ∈ 四列集），非法 422。**Wave 0 需核实** PUT 端点现有校验是否 hard-couple generic evaluator；若是则改为按 wp_code 分支（F2 不走 generic eval 求值校验，只语法+列名）。
- 刷新端点：`POST /api/workpapers/{wp_id}/f2/refresh-extraction` → 返回 `extract_f2_category_values` 结果（前端确认后回填）；或前端直接用 render 已带的 `tb_values`（若无需重查则不加端点）。**设计取 render 已带 tb_values（新口径）+ 前端刷新按钮重读**，避免新端点；若刷新需绕过缓存重查则加轻端点。

### 前端改动

- `useF2Adjudication.seedFromTbValues`：改直接填 opening/increase/decrease（消费 render 新 `tbValues` 结构 `{opening, increase, decrease}`），删除 `closing−opening` 粗猜逻辑。
- 新增 `F2FourTableSourcePanel.vue`（对齐 `E1FourTableSourcePanel`）：展示各类别 provenance（来源科目 + `TB()` 公式 + 期初/增加/减少/期末）+ 🔄 刷新取数按钮（编辑权限门控），刷新前对已编辑/明细带入锚点 `ElMessageBox.confirm`。
- 公式管理面板（复用 E1/D 的 FormulaStatusPanel）：F2-1 节点显示 surfaced Tier A 公式（可编辑/恢复默认）。

### 复用（不新造）

`_is_leaf` / `get_active_filter`（d 循环 primitives）、`resolve_effective` 范式、`anchor_registry` 范式、`tier_a_seed` 手工优先 / fail-open 范式、`wp_formula` CRUD + `PUT /formulas`、`find_unsupported_formula_functions`、E1 `E1FourTableSourcePanel` UI 范式、FormulaStatusPanel。

---

## Data Models

### F2-1 锚点集合（`F2_ANCHORS`，36 项）

```
gross block（原值，12 类 × 3 字段）:
  F2-1-gross-{rowKey}-{opening|increase|decrease}
  rowKey ∈ {raw-materials, material-in-transit, revolving-materials, semi-finished,
            outsourced-processing, finished-goods, goods-in-transit, dev-products,
            dev-costs, contract-performance, consumable-bio, price-difference}

impairment block（跌价，1 类 × 3 字段）:
  F2-1-impairment-impairment-provision-{opening|increase|decrease}
```

（值存 `checklist_responses.conclusion`；adjustment 字段来自 F2-14 跨表，不在取数范围。）

### 预设条目（`f2_extraction_presets.json`）

```json
{
  "_meta": { "spec": "f2-four-table-extraction-refresh", "note": "F2 Tier A tb_balance 取数公式" },
  "F2": [
    { "sheet_name": "F2-1", "anchor": "F2-1-gross-raw-materials-opening",
      "expression": "TB('1401','期初余额')", "formula_type": "auto_calc",
      "description": "原材料期初未审 ← tb_balance 1401 叶子期初余额" },
    { "sheet_name": "F2-1", "anchor": "F2-1-gross-raw-materials-increase",
      "expression": "TB('1401','借方发生额')", ... },
    { "sheet_name": "F2-1", "anchor": "F2-1-gross-raw-materials-decrease",
      "expression": "TB('1401','贷方发生额')", ... },
    ...（1401-1412 各 3 条）...
    { "anchor": "F2-1-impairment-impairment-provision-opening",
      "expression": "ABS(TB('1471','期初余额'))", ... },
    { "anchor": "F2-1-impairment-impairment-provision-increase",
      "expression": "TB('1471','贷方发生额')", "description": "跌价计提 ← 1471 贷方发生额" },
    { "anchor": "F2-1-impairment-impairment-provision-decrease",
      "expression": "TB('1471','借方发生额')", "description": "跌价转回/核销 ← 1471 借方发生额" }
  ]
}
```

### 取数结果（`extract_f2_category_values` 返回）

```
{ rowKey: { opening: float, increase: float, decrease: float, closing: float,
            formulas: {opening: expr, increase: expr, decrease: expr},
            source_codes: [叶子科目码] } }
```

### F2 列名映射（tb_balance 列）

| 公式列名 | tb_balance 列 |
|---------|---------------|
| 期初余额 | opening_balance |
| 期末余额 | closing_balance |
| 借方发生额 | debit_amount |
| 贷方发生额 | credit_amount |

（不支持 审定数/未审数/AJE/RJE —— 那是 trial_balance 列，F2 取数不用。）

---

## Correctness Properties

### Property 1: 只取叶子防双算
对任意 tb_balance 科目层级结构，`extract_f2_category_values` 对某类别只累加叶子子科目（`_is_leaf`），中间级 rollup 与其子科目不同时计入。
**Validates: Requirements 4.1**

### Property 2: 增减分别取借/贷发生额（原值类）
原值类（1401-1412）某类别 increase = Σ叶子 debit_amount、decrease = Σ叶子 credit_amount，不等于 `closing−opening` 的粗猜。
**Validates: Requirements 4.2**

### Property 3: 跌价备抵取绝对值 + 反向
跌价 1471：opening = abs(Σopening)、increase = abs(Σcredit_amount)、decrease = abs(Σdebit_amount)。
**Validates: Requirements 1.3, 4.2**

### Property 4: 手工/明细优先不静默覆盖
若某锚点在 `responses_snapshot` 已有非空值或 `isFromCrossSheet`（F2-3~13 明细带入），render 预填不覆盖；刷新覆盖须经用户确认。
**Validates: Requirements 3.3, 4.4**

### Property 5: 无数据不报错不阻断
tb_balance 无某类别子科目 → 该类别不产出；查询异常 → 返回空、logger.warning、不阻断 render。
**Validates: Requirements 1.4, 4.5**

### Property 6: 预设读时收敛
`resolve_effective` = 预设 ∪ 用户 wp_formula，每锚点唯一，禁用 > 用户 custom > 预设；预设未落库不丢失（无用户覆盖时仍以 source=preset 出现）。
**Validates: Requirements 1.1, 2.3**

### Property 7: 锚点必属真实集合
预设/用户公式的 anchor 必 ∈ `F2_ANCHORS`（36 项），未知锚点丢弃 + 告警，不静默写空。
**Validates: Requirements 1.6, 6.4**

### Property 8: 公式驱动取数
编辑某锚点公式（改 account 或 列）→ `extract_f2_category_values` 按新公式的 account+列从 tb_balance 取值（「编辑公式即改变取数」为真）。
**Validates: Requirements 1.1, 2.2**

### Property 9: F2 求值走 tb_balance 不走 trial_balance
F2 取数公式的求值经 `f2_extraction`（读 tb_balance），**不**经 `wp_formula_eval_service._resolve_tb`（读 trial_balance）；共享 `_resolve_tb` 保持逐字节不变（全平台 TB() 语义不受影响）。
**Validates: Requirements 5.1, 6.3**

### Property 10: 支持列名 + 不支持列名拒绝
F2 公式列名 ∈ {期初余额,期末余额,借方发生额,贷方发生额} 才有效；trial_balance-only 列（审定数/未审数等）或非法列 → 保存 422。
**Validates: Requirements 5.2**

### Property 11: 不支持函数保存拒绝
表达式含 AUX/PREV/LEDGER/COUNT_LEDGER → `find_unsupported_formula_functions` 命中 → 保存 422，不静默落空。
**Validates: Requirements 5.3**

### Property 12: 求值幂等 + 三处口径一致
同一四表库快照下多次求值同一 F2 公式结果一致；render 预填 / 刷新 / 公式管理面板取值三处同 `get_active_filter` + 同叶子判定 + 同类别聚合 → 同值。
**Validates: Requirements 3.5, 5.4**

### Property 13: 恢复默认回落预设
删除用户 wp_formula 后 resolve_effective 该锚点回落预设公式。
**Validates: Requirements 2.3**

### Property 14: 灰度零回归
`F2_FOUR_TABLE_EXTRACTION_ENABLED=False` 时，render 输出 `adjudication_prefill`/`tb_values` 与旧 `_build_adjudication_prefill` 逐字节等价，无刷新入口、无显式公式 surface。
**Validates: Requirements 6.1, 6.2**

### Property 15: 来源可溯
刷新/求值的每个取数值可回指其 `TB()` 公式来源（account + 列 + 叶子科目码），provenance 面板展示。
**Validates: Requirements 2.4, 3.4, 7.2**

---

## Error Handling

- tb_balance 查询异常 / active_filter 失败 → `logger.warning` + 返回空 dict，render 不阻断（Property 5）。
- 公式 parse 失败（非 `TB()`/`ABS(TB())` 形态、列名非法） → 该锚点不取数 + 告警；保存时 422（Property 10）。
- year 缺失 → 取数跳过（fail-open，沿用现有值），不阻断。
- 未知 anchor → 丢弃 + 告警，绝不写库（Property 7）。
- 刷新前对已编辑/明细带入锚点必弹确认；用户取消 → 不覆盖。
- 灰度关 → 所有新路径短路，走旧逻辑。

---

## Testing Strategy

- **后端 PBT/单测**（`tests/f2_extraction/`）：`test_extract_leaf`（Property 1/2/3/5）、`test_presets_resolve`（Property 6/7/13）、`test_parse_tb_formula`（Property 8/10）、`test_column_validation`（Property 10/11）、`test_evaluator_isolation`（Property 9：F2 走 tb_balance，`_resolve_tb` 未改）、`test_prefill_idempotent`（Property 12）、`test_gray_zero_regression`（Property 14：灰度关 render 输出与基线逐字节等价）。
- **契约守卫**：`test_f2_extraction_contract`——F2 预设/用户公式全走 `f2_extraction` 求值、不调 generic `evaluate_wp_formula_expression` 求值路径；F2_ANCHORS 与前端 `useF2Adjudication` itemId 集合一致（防漂移）；F2 列名集合与 tb_balance 列映射一致。
- **前端 vitest**：`useF2Adjudication.seed` 消费新 tbValues 结构（opening/increase/decrease 直填，无 closing−opening）；`F2FourTableSourcePanel` provenance 渲染 + 刷新 confirm。
- **live round-trip（可选，Playwright/HTTP）**：实例化含存货余额的项目 → render tb_values 新口径 → 刷新回填 → 公式管理编辑某类别公式 → 值随之变 → 恢复默认回落 → RESTORED_IDENTICAL 零污染。灰度默认关时机制由 PBT/契约充分覆盖。

---

## Migration Path / Rollout（灰度分阶段）

- **M0（安全网）**：characterization 锁定灰度关时旧 `_build_adjudication_prefill` 输出 + F2-3~13 明细带入 / F2-14 调整 / 附注 / 导入导出零回归基线；建 `f2_extraction` 骨架 + F2_ANCHORS + 契约守卫 xfail。
- **M1（取数服务 + 口径修正）**：`extract.py`（_is_leaf + 类别聚合 + parse_tb_formula）+ presets + anchor_registry；`_build_adjudication_prefill` 灰度开委托新服务（关闭走旧），前端 seed 改直填。
- **M2（公式管理 surface + 编辑）**：`build_f2_surfaced_formulas` + `wp_surfaced_f.py` F2-1 显式条目 + PUT 校验 F2 列名分支。
- **M3（刷新入口 + provenance 面板）**：`F2FourTableSourcePanel.vue` + 🔄 刷新 + confirm 覆盖 + Playwright/HTTP live。

灰度开关默认 False，任一阶段可回退（关闭即逐字节等价当前）。
