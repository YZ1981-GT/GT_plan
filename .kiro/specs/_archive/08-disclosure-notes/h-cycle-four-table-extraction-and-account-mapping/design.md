# Design Document

## Overview

本设计把 H 类循环的四表取数从「各自硬编码科目前缀」改造为「语义科目定位 + 共享件复用」。

**🔴 关键设计决策：复用并发会话已建立的 `semantic_account_resolver`，不另造 H 类专用件。**

调查初期我曾计划新建 `four_table/h_asset_layers.py` 做「原值 / 累计折旧 / 减值」三层分派。开工前 grep 消费方时发现并发 spec `g-cycle-extraction-mapping-and-disclosure-alignment` 已建成更通用的 `four_table/semantic_account_resolver.py`，并已用它改造完 H3（`h3_account_scope.py` + `_h3_investment_property.py`）。该共享件在两个关键点上优于我的原设计：

| 维度 | 原计划 `h_asset_layers` | 已有 `semantic_account_resolver` |
|---|---|---|
| 定位起点 | 报表行公式 → 标准码 | **本项目科目表的科目名** → 实际码 |
| 标准码不稳定的处理 | 未处理 | 已处理（实证 `1525` 在 1 个项目映射到 `1521`、4 个项目映射到 `1525`；按标准码查必在部分项目取空或混算） |
| 层数 | 固定三层 | **任意语义槽**（H3 用了 4 槽：原值/累计折旧/累计摊销/减值） |
| `report_config` 错码 | 无法发现 | `conflicts` 暴露到溯源面板 |
| 旧准则科目 | 无 | `unmapped_candidates` 提示人工映射 |
| 科目表缺失 | 无区分 | `chart_available` 区分「无此科目」与「科目表未导入」 |

故本 spec 的后端工作 = **为 H1/H2/H4/H5/H6/H7/H8/H9/H10 各建一份 `h{n}_account_scope.py` 声明语义槽**，并按 H3 已验证的 render 改造范式接线。**H3 不在本 spec 范围**（已由并发 spec 完成）。

**判断二：分层判定必须以科目名称为主，不能靠 `direction`。** `account_chart` 实证 `1525 投资性房地产累计折旧` / `1526 投资性房地产累计摊销` / `1527 投资性房地产减值准备` 的 `direction` **全是 `debit`**，而 `1622`/`1632`/`1642` 是 `credit` —— 同一语义两种标注。故 `SemanticAccountSlot.is_provision` 显式声明，不由方向推断。这与平台已有铁律一致（`6403` 税种、`1123` 款项性质、`14xx` 存货都按名称归类）。

**判断三：否决词是必填项不是优化。** `固定资产减值准备` 包含 `固定资产`、`使用权资产累计折旧` 包含 `使用权资产` —— 原值槽无否决词就会把全部备抵槽吃进去（虚增原值）。每个 H 循环的原值槽都必须声明否决词，并由守卫反向自检。

**判断四：H 类没有账龄分段，这是结论不是遗漏。** 逐格扫 20 个披露 sheet 只命中 H9 两处单行重分类与 H2 的「工程进度」列。把结论写成守卫比留悬念更有价值。

改造后的数据流：

```
四表入库
  └─ tb_balance（客户原始码，参差多级树）+ account_chart（客户 / 平台标准两份）
        │
        │  h{n}_account_scope.H{N}_ACCOUNT_SPEC（按科目**名称**声明语义槽）
        │  four_table.semantic_account_resolver.resolve_semantic_accounts
        │    ① 客户科目表按名称 → ② 平台标准表按名称
        │    → ③ report_config 公式给的码（须在本项目存在）→ ④ 兜底码（同上）→ ⑤ 返空
        ▼
  SemanticAccountResult{slots{gross, accum_dep, …}, conflicts, unmapped_candidates}
        │
        │  four_table.select_leaves + aggregate_leaves（叶子口径 + 点号边界）
        ▼
  render 输出：tb_values / adjudication_prefill / tb_source_codes / parent_check
        │
        ├─→ 前端 h{n}AccountScope.ts（运行态取 tb_source_codes，常量只作兜底）
        ├─→ 审定表「从四表库带入未审数」
        ├─→ WpFourTableSourcePanel（溯源，消灭 H1 的 dead output）
        └─→ 披露表 → sync-from-workpaper → 附注章节
```

## Architecture

### 分层与职责边界

| 层 | 位置 | 职责 | 本 spec |
|---|---|---|---|
| 通用科目定位（标准码路线） | `four_table/report_line_accounts.py` | 报表行 → 标准码 → 原始码 | **不改** |
| 通用叶子聚合 | `four_table/leaf_aggregation.py` | 叶子筛选 / 点号边界前缀过滤 / 聚合 / 父额 | **不改** |
| 语义科目定位 | `four_table/semantic_account_resolver.py` | 按科目名逐项目定位 + 多级回退 + 冲突检测 | **不改**（并发 spec 所有） |
| H3 科目规格 | `four_table/h3_account_scope.py` | H3 的 4 个语义槽 | **不改**（并发 spec 已完成） |
| **H 类各循环科目规格** | `four_table/h{n}_account_scope.py` ×9 | 各自的语义槽声明 + 槽键→`tb_values` 键前缀映射 | **新建** |
| 循环 render | `wp_render_strategies/_h{n}_*.py` ×9 | 接语义定位 + 纯函数构造输出 | **改造** |
| 段落预填 | `d_cycle_extraction/prefill.build_d_adjudication_prefill` | 按科目前缀构造子科目预填项 | 改调用方传参 |
| 前端科目真源 | `composables/h{n}AccountScope.ts` ×10 | 语义槽键 + 兜底码 + 运行态取值 | **新建** |
| 前端溯源 | `shared/WpFourTableSourcePanel.vue` + `composables/shared/tbSourceCodes.ts` | 展示各槽科目、来源、冲突 | 复用（可能扩 props） |
| 公式预设 | `backend/data/prefill_formula_mapping.json` | 底稿当页公式管理预设 | 幂等脚本改写 |

### 并发协作边界（必须遵守）

| 文件 | 归属 | 本 spec 行为 |
|---|---|---|
| `semantic_account_resolver.py` | 并发 spec | 只读消费，一行不改 |
| `report_line_accounts.py` / `leaf_aggregation.py` | 并发 spec 正在改 | 只读消费，一行不改 |
| `h3_account_scope.py` / `_h3_investment_property.py` / `test_h3_account_scope.py` | 并发 spec | **完全不碰** |
| `g_cycle_specs.py` / `e1_*` / `f3_*` / `f4_*` / `f5_*` / `tb_query.py` | 并发 spec | 不碰 |
| `h{1,2,4,5,6,7,8,9,10}_account_scope.py` | 本 spec | 新建 |
| `_h{1,2,4,5,6,7,8,9,10}_*.py` | 本 spec | 改造 |
| `prefill_formula_mapping.json` 的 H 类块 | 本 spec | 幂等脚本改写（H3 块也在其中 → 与并发会话确认后再动，否则只改 H3 以外的块） |

新建文件前一律 `str_replace` 优先 / 先 grep 消费方；改共享模块后 `get_diagnostics` 必须查全部消费方。

### H 类语义槽声明表（本 spec 的核心真源）

| 循环 | `row_code` | 语义槽（key ← 科目名） | 兜底标准码 | 备抵 | 口径 |
|---|---|---|---|---|---|
| H1 固定资产 | `BS-028` | `gross`←固定资产 / `accum_dep`←累计折旧 / `impairment`←固定资产减值准备 | `1601`/`1602`/`1603` | 后两槽 | 余额 |
| H2 在建工程 | `BS-029` | `gross`←在建工程 / `eng_mat`←工程物资 / `impairment`←在建工程减值准备 | `1604`/`1605`/— | 末槽 | 余额 |
| H4 工程物资 | `BS-029` | `gross`←工程物资 / `cip`←在建工程 | `1605`/`1604` | — | 余额 |
| H5 油气资产 | — | `gross`←油气资产 / `accum_depletion`←累计折耗 / `impairment`←油气资产减值准备 | `1631`/`1632`/— | 后两槽 | 余额 |
| H6 固定资产清理 | `BS-028` | `gross`←固定资产清理 | `1606` | — | 余额 |
| H7 生产性生物资产 | `BS-030` | `gross`←生产性生物资产 / `accum_dep`←生产性生物资产累计折旧 / `impairment`←生产性生物资产减值准备 | `1621`/`1622`/— | 后两槽 | 余额 |
| H8 使用权资产 | `BS-031` | `gross`←使用权资产 / `accum_dep`←使用权资产累计折旧 / `impairment`←使用权资产减值准备 | `1641`/`1642`/`1643` | 后两槽 | 余额 |
| H9 租赁负债 | `BS-063` | `gross`←租赁负债 / `unearned_finance`←未确认融资费用 | `2601`/`2602` | 末槽 | 余额 |
| H10 资产处置损益 | `IS-018` | `gross`←资产处置损益（含「资产处置收益」别名） | `6115` | — | **发生额** |

说明：
- H5 在 `report_config` 中**无 BS 报表行**（仅 `CFSS-005` 提折耗、`IMP-014` formula 为 NULL）→ `row_code=None`，溯源面板须明示「该科目无报表行映射」。
- H2 的 `1605 工程物资` 不是减值准备而是与在建工程同属 `BS-029` 的另一科目 → 独立槽 `eng_mat`，不塞备抵槽。H4 反向单列 `cip`。
- H9 的 `2602 未确认融资费用` 在 `account_chart` 中 `direction` 有 `debit`/`credit` 两种标注 → 必须显式 `is_provision=True`，靠名称定位。
- H10 的 `6115` 在 `account_chart` 里有三种名称（`资产处置损益` debit / `资产处置损益` credit / `资产处置收益` credit）→ `names` 须含两个别名。
- H1 的 `accum_dep` 槽科目名是裸「累计折旧」（不含「固定资产」前缀）→ 否决词必须排除 `投资性房地产`/`使用权资产`/`生产性生物资产`/`油气`，否则会跨循环误命中。这是 H 类最容易踩的一处。

### 否决词矩阵（原值槽必填）

| 循环 | 原值槽 `names` | `exclude_names` |
|---|---|---|
| H1 | 固定资产 | 累计折旧, 减值准备, 清理, 减值损失, 折旧 |
| H2 | 在建工程 | 减值准备, 物资, 减值损失 |
| H4 | 工程物资 | 减值准备, 减值损失 |
| H5 | 油气资产 | 累计折耗, 减值准备, 折耗, 减值损失 |
| H6 | 固定资产清理 | 减值准备 |
| H7 | 生产性生物资产 | 累计折旧, 减值准备, 折旧, 减值损失 |
| H8 | 使用权资产 | 累计折旧, 减值准备, 折旧, 减值损失 |
| H9 | 租赁负债 | 未确认融资费用, 一年内到期 |
| H10 | 资产处置损益, 资产处置收益 | — |

`H6.gross` 用「固定资产清理」精确匹配；但 `H1.gross` 的「固定资产」会**包含匹配**到「固定资产清理」→ H1 否决词含「清理」。这两条互为镜像，守卫须双向断言。

## Components and Interfaces

### 后端：`backend/app/services/four_table/h{n}_account_scope.py`（新建 ×9）

以 H8 为例，完全照抄 H3 已验证的形态：

```python
from .semantic_account_resolver import SemanticAccountSlot, SemanticAccountSpec

_GROSS_EXCLUDES = ("累计折旧", "减值准备", "折旧", "减值损失")

#: 槽键 → 前端 `tb_values` 键前缀（保持既有契约：rou_asset / rou_dep 原样不动）
H8_SLOT_KEY_PREFIX = {
    "gross": "rou_asset",
    "accum_dep": "rou_dep",
    "impairment": "rou_imp",      # 新增槽
}

H8_ACCOUNT_SPEC = SemanticAccountSpec(
    row_code="BS-031",
    slots=(
        SemanticAccountSlot(key="gross", names=("使用权资产",),
                            exclude_names=_GROSS_EXCLUDES,
                            fallback_standard_codes=("1641",), label="使用权资产原值"),
        SemanticAccountSlot(key="accum_dep", names=("使用权资产累计折旧", "累计折旧"),
                            exclude_names=("固定资产", "投资性房地产", "生产性生物资产"),
                            fallback_standard_codes=("1642",), label="累计折旧",
                            is_provision=True),
        SemanticAccountSlot(key="impairment", names=("使用权资产减值准备",),
                            exclude_names=("减值损失",),
                            fallback_standard_codes=("1643",), label="减值准备",
                            is_provision=True),
    ),
    legacy_standard_names=("融资租赁资产",),   # 旧准则同族 → 提示人工映射，不自动归槽
)
```

`legacy_standard_names` 的用法：H8 声明「融资租赁资产」（`1611`，旧准则），H9 声明「长期应付款」的融资租赁部分 —— 客户仍在用旧准则时进 `unmapped_candidates` 提示人工映射，本模块不猜跨准则拆分。

### 后端：各循环 render 改造形态（照抄 H3）

```python
async def _fetch_tb_data(ctx) -> tuple[dict, dict, dict]:
    accounts = await resolve_semantic_accounts(ctx, H8_ACCOUNT_SPEC)
    tb_rows = await _load_tb_rows(ctx)          # 全量 + get_active_filter（叶子判定需看全部兄弟行）
    trial_rows = await _load_trial_rows(ctx)    # 全量 + get_active_filter
    return (build_h8_tb_values(accounts, tb_rows, trial_rows),
            accounts.as_dict(),
            build_h8_parent_check(tb_rows, accounts))
```

`build_h{n}_tb_values(accounts, tb_rows, trial_rows)` 是**纯函数**（可独立单测），实现与 `build_h3_tb_values` 逐字同构：

- `tb_balance` 侧：`select_leaves(to_leaf_rows(tb_rows))` → `aggregate_leaves(leaves, slot.codes)` → 键 `{prefix}_unadjusted_{opening|closing|debit|credit}`
- `trial_balance` 侧：按**标准码精确匹配**（不用 LIKE 前缀，会把兄弟科目族吃进来）→ 键 `{prefix}_unadjusted` / `{prefix}_audited`
- 🔴 某槽 `not slot.found` 时**不产生任何键**（而非产生 0）—— 让前端能区分「本项目无此科目」与「余额为 0」

删除项（每个循环）：`_H{N}_ACCOUNT_PREFIXES` 常量、局部 `_is_leaf`（多处缺点号边界）、裸 SQL 查询。

备抵槽的增减方向：备抵（贷方）`credit_amount` = 计提（增加）、`debit_amount` = 转回核销（减少），与原值侧相反。`aggregate_leaves(..., absolute=True)` 用于备抵槽的余额输出。

`build_d_adjudication_prefill` 的调用改为按槽循环：
```python
for slot_key, prefix in H8_SLOT_KEY_PREFIX.items():
    slot = accounts.slots.get(slot_key)
    if not slot or not slot.found:
        continue
    for code in slot.codes:
        items = await build_d_adjudication_prefill(ctx, account_prefix=code, mode="balance")
```

### 前端：`composables/h{n}AccountScope.ts`（新建 ×10，含 H3）

```ts
export const H8_REPORT_ROW_CODE = 'BS-031'
export const H8_SLOT_KEYS = ['gross', 'accum_dep', 'impairment'] as const
/** 仅作兜底与展示；运行态一律取 render 下发的 tb_source_codes */
export const H8_FALLBACK_CODES: Record<H8SlotKey, readonly string[]> = {
  gross: ['1641'], accum_dep: ['1642'], impairment: ['1643'],
}
export function h8SlotCodes(src: TbSourceCodes | null | undefined, slot: H8SlotKey): string[]
/** TB 回写目标科目码（原值槽首码） */
export function h8WritebackCode(src?: TbSourceCodes | null): string
```

H3 侧也建一份（前端 scope 是本 spec 范围，后端 H3 不碰），以便 10 个循环的前端形态一致、守卫可参数化。

### 前端：溯源面板

`shared/WpFourTableSourcePanel.vue` 现为 K1/K2 的「原值 + 备抵」两行形态。`SemanticAccountResult` 是**任意槽数**，且多了 `conflicts` / `unmapped_candidates` / `chart_available` / `exact` 四类信息。设计选择：

1. 先评估扩展 `WpFourTableSourcePanel` 为可变槽列表的成本（K1/K2 现有 111 例守卫）。
2. 若扩展会打断既有守卫，则新建 `shared/WpSemanticAccountSourcePanel.vue` 专供语义定位路线，K1/K2 的标准码路线保留原面板；并在 Notes 记录取舍依据与「两个面板各自服务哪条定位路线」的边界。

面板须展示：各槽的科目码 + 命中科目名 + `resolved_from` + `exact`（非精确须提示复核）+ `conflicts`（橙色告警）+ `unmapped_candidates`（旧准则科目需人工映射）+ `chart_available=false`（提示「科目表未导入」）+ `parent_check` 差异条。

### 幂等脚本：`backend/scripts/fix/fix_h_cycle_prefill_presets.py`（新建）

- CLI：`--dry-run` / `--check` / `--apply` / `--only H8,H9`
- 真源：各 `h{n}_account_scope.py` 的兜底码 + openpyxl 直读源 xlsx 的 sheet 名（防漂移）
- 默认 `--only` **不含 H3**（该块归属待与并发会话确认）
- 硬约束：`--check` 返回欠账清单；断言「块内科目码 ⊆ 本循环声明的兜底码集 ∪ 本循环报表行引用集」

### 幂等脚本收敛：`fix_h1_note_section_alignment.py`

保留走共享 kit 的 `fix_note_h1_fixed_assets_structure.py` 为唯一真源。删除前先记录两者对同一批表的 guidance 差异作为取舍证据。

## Data Models

### render 下发的 `tb_source_codes`（= `SemanticAccountResult.as_dict()`）

```json
{
  "row_code": "BS-031",
  "formula": "TB('1641','期末余额')-TB('1642','期末余额')-TB('1643','期末余额')",
  "report_config_codes": ["1641", "1642", "1643"],
  "conflicts": [],
  "unmapped_candidates": [["1611", "融资租赁资产"]],
  "chart_available": true,
  "slots": {
    "gross": {
      "key": "gross", "label": "使用权资产原值", "is_provision": false,
      "codes": ["1641"], "standard_codes": ["1641"],
      "matched": [["1641", "使用权资产"]],
      "resolved_from": "account_chart_standard", "exact": true, "found": true
    },
    "accum_dep": { "...": "..." },
    "impairment": { "...": "..." }
  }
}
```

### `parent_check` 形态

```json
{
  "gross":      {"leaf_sum": 839186904.84, "parent": 839186904.84, "diff": 0.0},
  "accum_dep":  {"leaf_sum": 134523555.78, "parent": 134523555.78, "diff": 0.0},
  "impairment": {"leaf_sum": 0.0,          "parent": 0.0,          "diff": 0.0}
}
```

### `tb_values` 键名契约（保持现状，不改名）

| 循环 | 槽键 → 键前缀 |
|---|---|
| H1 | `gross`→`cost` / `accum_dep`→`dep` / `impairment`→`imp` |
| H2 | `gross`→`cip`（另出 `cip_1604` 别名）/ `eng_mat`→`eng_mat`（另出 `eng_mat_1605`）/ `impairment`→`cip_imp` |
| H4 | `gross`→`eng_mat_1605` / `cip`→`cip_1604` |
| H5 | `gross`→`cost` / `accum_depletion`→`dep` / `impairment`→`imp` |
| H6 | `gross`→（现状单科目键名，改造时逐字保留） |
| H7 | `gross`→`cost` / `accum_dep`→`dep` / `impairment`→`imp` |
| H8 | `gross`→`rou_asset` / `accum_dep`→`rou_dep` / `impairment`→`rou_imp`（新增） |
| H9 | `gross`→`lease_liability` / `unearned_finance`→`unearned_finance`（新增） |
| H10 | `gross`→（发生额标量，现状键名保留） |

每个前缀带 `_unadjusted_{opening|closing|debit|credit}`（`tb_balance` 侧）与 `_unadjusted` / `_audited`（`trial_balance` 侧）。改造只改**取数来源**，新增槽才新增键。任何既有键名变更须在 tasks 里单列并同步前端。

### H9 动态行模型

```ts
interface H9ListedCategoryRow { rowId: string; item: string; endBalance: number|null; lastYearEnd: number|null }
interface H9SoeLineRow { rowId: string; key: 'payment'|'unearned'|'reclass'|'extra'; item: string; endBalance: number|null; beginBalance: number|null }
```

- `rowId` 为稳定 key（`H9-listed-{seq}` / `H9-soe-extra-{seq}`），**不用 label**。
- 上市：现有 4 行降级为「首次进入的 seed」，可增删改名；`小计`/`减：一年内到期的租赁负债`/`合计` 为派生行不可删。
- 国企：`payment`/`unearned`/`reclass` 三行固定，`extra` 可增删（对应源模板 `A11` 的 `……`）；`租赁负债净额` 派生。
- 迁移零丢数：历史固定行持久化键沿用旧 rowKey，`rowId` 由旧键派生。

## Correctness Properties

### Property 1: 语义槽完备且互斥

各循环 `H{N}_ACCOUNT_SPEC` 的槽键唯一；对实证客户科目表，任一科目码最多被一个槽命中（原值槽与备抵槽无交集）。

**Validates: Requirements 2.1, 2.2**

### Property 2: 否决词有效且不可省

对每个循环的原值槽，若移除 `exclude_names`，则该槽会命中至少一个备抵科目（反向自检证明否决词是必填项而非优化）。特别地：H1 的「固定资产」不加「清理」否决词会命中 `1606 固定资产清理`；H8 的「使用权资产」不加「累计折旧」会命中 `1642`。

**Validates: Requirements 2.2, 2.3**

### Property 3: 裸备抵名不跨循环误命中

H1 的 `accum_dep`（名为裸「累计折旧」）在含 `1525 投资性房地产累计折旧` / `1622 生产性生物资产累计折旧` / `1642 使用权资产累计折旧` 的科目表中只命中 `1602`；H5/H7/H8 各自同理。

**Validates: Requirements 2.2, 2.3, 2.4**

### Property 4: 叶子和等于父科目额

对任一槽，`parent_check[slot].diff` 的绝对值 ≤ 0.01（父科目行存在时）。

**Validates: Requirements 3.1, 3.4, 12.2**

### Property 5: 前缀匹配要求点号边界

`filter_by_prefixes(rows, ['1601'])` 不命中 `account_code='16010'`；改造后的 9 个 render 中不存在无点号边界的 `startswith` 前缀匹配。

**Validates: Requirements 3.2**

### Property 6: 宁缺勿造

某槽 `found=False` 时 `tb_values` 不产生该槽的任何键，`adjudication_prefill` 为空集合；`chart_available=False` 时不产生「该项目无此科目」的误导结论。

**Validates: Requirements 1.8, 5.2**

### Property 7: 科目码属于本循环

各 `h{n}_account_scope.py` 的兜底码与公式预设中出现的每个科目码，① 存在于标准科目表 ② 属于本循环报表行公式引用集或本循环声明的兜底集。旧错误码（`1503`/`1504`/`1901`/`2205`/`1522`/`1523`/`2802`/`2803`）须被规则判否。

**Validates: Requirements 7.3, 11.2**

### Property 8: 前端无旧错误科目码

前端 H 类源码（去注释后）不出现旧错误码作为科目码、请求参数、事件载荷或 TB 回写目标；反向自检证明该正则能命中真实写法。

**Validates: Requirements 6.3, 6.4**

### Property 9: 损益口径不用借贷相减

H10 的取数与预设中不出现 `debit - credit` 形态，也不出现 `TB('6115','期初余额')` / `TB('6115','期末余额')`；发生额优先取 `trial_balance`。

**Validates: Requirements 5.4, 7.2**

### Property 10: 幂等脚本自洽且不回退已修正值

`fix_note_h2_construction_structure.py --dry-run` 对当前模板零变更（`report_row_code` 已为 `BS-029`）；H8 结构脚本的 guidance 不含 `**`；全部 H 类结构脚本 `--check` 零欠账。

**Validates: Requirements 8.1, 8.2, 8.3**

### Property 11: H9 动态行往返无损

对任意行序列，增行 → 改名 → 删行 → 推送载荷 → 反序列化后，剩余行的 `rowId` 与金额逐字保持；被删行的键进入 `_removed_table_keys` 且与本次推送键求差集后不含仍存在的行。

**Validates: Requirements 9.1, 9.2, 9.6**

### Property 12: 动态行 key 不用 label

同名新增被拒绝；改名后 `rowId` 不变、金额不丢。

**Validates: Requirements 9.3, 9.4**

### Property 13: H 类无期限分段（反向锁定）

openpyxl 直读 H1~H10 共 20 个披露 sheet，期限类判据词的命中集等于已登记白名单（H9 上市 `A12`、H9 国企 `A10`、H2 上市 `D31`/`A36`、H2 国企 `I26`）；白名单为空则守卫判为失效。

**Validates: Requirements 10.1, 10.2, 10.3**

### Property 14: 并发协作边界不被越过

本 spec 的 git diff 不含 `semantic_account_resolver.py` / `report_line_accounts.py` / `leaf_aggregation.py` / `h3_account_scope.py` / `_h3_investment_property.py`；且并发 spec 的相关测试（`test_h3_account_scope.py` / `test_semantic_account_resolver.py` / `test_g_cycle_specs.py`）保持与本 spec 开工前同样的通过状态。

**Validates: Requirements 2.5**

### Property 15: 宿主传参守卫无截断盲区

修复后的 `disclosureAutoSyncCoverage.spec.ts` 对含嵌套 `<template #slot>` 的宿主能扫到全部披露 Tab 使用点（H 类 22 个全部被检查），反向自检替身能命中漏传 `projectId` 的写法。

**Validates: Requirements 11.5, 11.6**

## Error Handling

| 失败点 | 处理 | 可观测性 |
|---|---|---|
| `account_chart` 查询失败 | `chart_available=False`，各槽退化为裸兜底码 | 溯源面板提示「科目表未导入」而非「无该科目」 |
| 名称在本项目科目表无命中 | 依次降级 客户表→标准表→`report_config` 码→兜底码→返空 | `resolved_from` 标注实际来源；`none` 时前端显示「本项目无此科目」 |
| 只命中包含匹配（非精确） | 照用但 `exact=False` | 溯源面板提示审计师复核 |
| `report_config` 码与语义结果不一致 | **以语义结果为准** | `conflicts` 橙色告警（实证 `report_config` 有 4 行错码） |
| 客户仍用旧准则科目 | 不自动归槽 | `unmapped_candidates` 提示人工映射（跨准则拆分是会计判断） |
| `account_mapping` 反解为空 | 客户码路线直接用客户码；标准码路线保留标准码 | 溯源面板显示实际用的码 |
| `tb_balance` 查询异常 | `tb_values` 返空 dict，render 继续 | 日志 `warning`；前端显示「未取数」而非 0 |
| `parent_check` 差异非 0 | 不阻断，原样下发 | 溯源面板红色差异条 |
| H5 无报表行（`row_code=None`） | 跳过公式查询，走名称定位 | 溯源面板明示「该科目无报表行映射」 |
| 幂等脚本 `--apply` 校验失败 | 不写盘，非 0 退出码 + 打印欠账 | `--check` 进 CI |

fail-open 的边界：**取数可以为空，但不能为错**。若兜底码不属于本循环报表行引用集（Property 7），守卫在 CI 阶段拦住，不在运行时静默纠正。

## Testing Strategy

### 后端

| 文件 | 覆盖 | 要点 |
|---|---|---|
| `backend/tests/four_table/test_h_cycle_account_scopes.py` | Property 1,2,3,6 | 9 个循环参数化；**反向自检**：移除否决词则原值槽命中备抵科目；实证客户科目表 fixture（含跨循环干扰项 `1525`/`1622`/`1642` 同时在场） |
| `backend/tests/test_h_cycle_account_codes.py` | Property 7 | 双条件：码 ∈ 标准科目表（读 `backend/data/standard_account_chart.json`，不连库）+ 码 ∈ 本循环报表行引用集；含旧错误码被判否的反向自检 |
| `backend/tests/test_h_cycle_formula_presets.py` | Property 7,9 | 科目码正确性 + 防成环（明细表禁引审定表）+ 语法合法性（按 prefill 词汇表放行 `ADJ`/`TB_SUM`/`LEDGER`/`AUX`/`PREV`）+ 禁硬编码具体项目编码 + H10 损益口径 |
| `backend/tests/test_h_cycle_no_maturity_buckets.py` | Property 13 | openpyxl 直读 20 个披露 sheet；白名单空则判失效 |
| 各循环 `test_h{n}_*` 扩展 | Property 4,5,6 | `build_h{n}_tb_values` 纯函数单测（照抄 H3 的测试形态）；`parent_check` 断言；空槽不产生键 |
| 替身要求 | — | 同表多次查询按 SQL/params 区分（D1 曾因替身不区分导致备抵==原值）；`get_active_filter` 的 mock 返回真实 `sa.true()` 不用 `MagicMock`（F2 曾因此假绿） |

### 前端

| 文件 | 覆盖 | 要点 |
|---|---|---|
| `composables/__tests__/hCycleAccountScope.spec.ts` | Property 8 | 10 个循环参数化；运行态优先 `tb_source_codes`；`stripComments()` + 反向自检 |
| `composables/__tests__/hCycleFourTableWiring.spec.ts` | Property 8 | 跨循环扫描 H 类源码禁旧错误码；`writebackTB` 目标走 scope |
| `composables/__tests__/h9DisclosureDynamicRows.spec.ts` | Property 11,12 | 含 PBT（任意行序列往返无损）；撞名拒绝；`rowId` 非 label |
| `composables/__tests__/h5NoteSectionMap.spec.ts` | R8.4 | 改现签名 + `undefined` 保护 |
| `__tests__/disclosureAutoSyncCoverage.spec.ts` | Property 15 | 修 `<template>` 正则截断 + 反向自检替身 |

### 零回归验证

- Property 14：`git diff --name-only` 不含并发 spec 归属的 6 个文件。
- 跑 `backend/tests/four_table` 全量（含并发会话的 `test_h3_account_scope.py` / `test_semantic_account_resolver.py`），与本 spec 开工前逐数对比。
- 前端 `npx vitest run h1 h2 h3 h4 h5 h6 h7 h8 h9 h10`（位置参数是**子串过滤**，不传 `-t ""`），与基线 2070 passed / 8 failed 对比；后端与基线 65 failed / 1247 passed 对比，逐条区分预存在与新增。

### 实测（Property 4 与 R12）

- 有活体数据：H1（`1601` 65 行 / `1602` 65 行 / `1603` 40 行）、H2（`1604` 45 行 / `1605` 5 行）、H6（`1606` 9 行）、H10（`6115` 30 行）→ 真实 DB 直跑 render，核对各槽科目码、`resolved_from`、`parent_check.diff`、预填金额。
- 无活体数据：H5（`1631`）、H7（`1621`）、H8（`1641`）、H9（`2601`）→ 只能验「解析出正确科目码 + 空值不造假」，须在 tasks 里明确标注验证边界，**不得把「空」记为通过**。
- 浏览器实测：H9 两版动态行（增/改名/撞名/删除/推送/`_removed_table_keys`/`last_sync_at` 前移），测后按快照复原。
