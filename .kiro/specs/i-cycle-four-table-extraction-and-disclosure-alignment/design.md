# Design Document

## Overview

本设计把 I1~I6 的「四表取数 → 底稿 → 披露表 → 附注」四段链路各自的真源收敛到唯一位置，
并让六个循环共用同一批已验证的平台件，不新造机制：

```
account_chart(标准科目表)  report_config(报表行公式)      源模板 xlsx(披露结构唯一裁决者)
        │                          │                                  │
        └────────┬─────────────────┘                                  │
                 ▼                                                    │
   four_table/report_line_accounts.resolve_report_line_accounts       │
                 │  gross / provision / gross_standard / signed_codes │
                 ▼                                                    │
   four_table/leaf_aggregation.select_leaves + aggregate_leaves       │
                 │  叶子口径金额（叶子和 == 父额）                     │
                 ▼                                                    │
   _iN_*.py render                                                    │
     ├─ tb_values（键名不变，前端已在读）                              │
     ├─ tb_source_codes（新增，溯源面板消费）                          │
     ├─ adjudication_prefill（新增，按叶子科目名归类）                 │
     └─ tb_leaf_categories（新增，I1/I4 类别维度）                     │
                 ▼                                                    ▼
   前端 iNAccountScope.ts（科目单一真源）          fix_note_i_cycle_*_structure.py（幂等）
                 ▼                                                    ▼
   审定表「从四表库带入未审数」+ 溯源面板            note_template_{listed,soe}.json 的 columns/
                 ▼                                    guidance/两级表头/表名/行集
   披露表（动态类别列/行）                                            │
                 ▼                                                    │
   iNDisclosureSyncPayload（columns 显式 flat/group）◄────逐字对齐─────┘
                 ▼
   sync_from_workpaper → disclosure_notes.table_data.sub_table_data
```

### 设计约束（来自平台既有铁律，本设计不重新论证）

- 科目定位一律走报表行解析 + 叶子聚合共享件，禁 per-cycle 抄一份。
- 披露结构裁决者 = 源 xlsx；`附注模版/*.md` 在本仓库不存在，不得引为依据。
- 附注模板只能用幂等脚本改，配 `--check` 与三向比对守卫。
- `flat` 必须在 **seed（模板 `columns`）与推送（载荷 `columns`）两处**都声明。
- `_note_texts` 放 `sub_table_data` 内且带中文 `title`。
- 灰度开关 OFF 时输出逐字节等价。

## Architecture

### 后端分层

| 层 | 文件 | 职责 | 变更性质 |
|---|---|---|---|
| 共享件 | `app/services/four_table/report_line_accounts.py` | 报表行 → 科目 | **additive**：新增 `chart_conflict` 诊断字段（默认 None = 引入前等价） |
| 共享件 | `app/services/four_table/leaf_aggregation.py` | 叶子选择与聚合 | 不改 |
| 新建 | `app/services/four_table/i_cycle_accounts.py` | I1~I6 的 `ReportLineAccountSpec` 声明 + 类别分类规则（单一真源） | 新建 |
| 新建 | `app/services/four_table/i1_asset_categories.py` | I1 类别 dataclass（11 类 + `source_ref` 指向源 xlsx 单元格）+ `classify_i1_leaf()` | 新建 |
| 策略 | `app/routers/wp_render_strategies/_i1_intangible_assets.py` 等 6 个 | render：删硬编码前缀、改走共享件、输出溯源与预填 | 重写取数段 |
| 脚本 | `backend/scripts/fix/fix_i_cycle_prefill_presets.py` | 公式预设重写（幂等） | 新建 |
| 脚本 | `backend/scripts/fix/fix_note_i_cycle_structure.py` | 12 章节结构修订（幂等，复用 `_note_structure_kit`） | 新建 |

### 前端分层

| 层 | 文件 | 职责 |
|---|---|---|
| 科目真源 | `composables/i1AccountScope.ts` ~ `i6AccountScope.ts` | 报表行常量 + 兜底标准码 + `iNGrossQueryCodes(src)` + `iNAccountCode(src)`；运行态一律取 render 下发的 `tb_source_codes` |
| 类别真源 | `composables/i1CategoryScope.ts` | 11 类默认序列 + 稳定 key 生成 + 动态增删改名；上市列与国企行共用 |
| 溯源面板 | 复用 `shared/WpFourTableSourcePanel.vue` | 通过 props 传原值/备抵中文名；I5 不传 `provisionLabel` |
| seed 纯函数 | `composables/iNFourTableSeed.ts` | 审定表/披露表共用的预填纯函数 |
| 映射 | `composables/iNNoteSectionMap.ts` + `iNDisclosureSyncPayload.ts` | 表名常量 + `columns`（显式 flat/group）+ 载荷构建 |
| 勾稽 | `composables/iNDisclosureConsistency.ts` | 规则全取源模板 Excel 公式 |

### 幂等脚本的作用域切分

`fix_note_i_cycle_structure.py` 按 `--cycle` 参数分作用域执行，共 12 个 section rule：

| rule | 作用域 | 主要变更 |
|---|---|---|
| `i1_listed` | 五、26 | 主表列改动态类别（seed 用默认 11 类）+ ⑥表正名「重要单项无形资产」+ （2）表正名 + 补 columns/guidance |
| `i1_soe` | 八、27 | 主表行集 48 → 52（补齐四层 × 13）+ flat columns + guidance + text_sections 7 段 |
| `i2_listed` | 五、27 | 主表补标签列 + 两级 7 列；**补入 4 张缺失表**；text_sections 补源模板 8 段 |
| `i2_soe` | 八、28 | 两级 8 列 |
| `i3_listed` | 五、28 | ①两级 8 列 / ②两级 7 列；③④表名正名（关键假设表 / 业绩承诺表） |
| `i3_soe` | 八、29 | ①正名「（1）商誉账面价值」+ flat 5 列 |
| `i4_listed` | 五、29 | 两级 6 列 + 列名回源模板（期初数/期末数） |
| `i4_soe` | 八、30 | flat 7 列 + guidance |
| `i5_listed` | 五、31 | 两级 7 列；主表正名 + 「根据实际情况列示」入 guidance；②合同取得成本表正名 |
| `i5_soe` | 八、32 | flat 3 列，第 3 列改「年初余额」；②表正名 |
| `i6_listed` | 五、66 | flat 3 列 + guidance（财会〔2019〕6号） |
| `i6_soe` | 八、67 | 表名补「（按费用性质列示）」+ flat 3 列 |

## Components and Interfaces

### 0. 真实 DB 直跑推翻的两个初版假设（2026-08-01 实证，设计据此调整）

**① `row_code` 跨准则语义不同，不是编号平移。** 初版 `I_CYCLE_SOE_ROW_CODES` 假设同一循环
两套编号只是行次不同、公式一致。实证否定：

| row_code | listed_* 的 row_name | soe_* 的 row_name |
|---|---|---|
| `BS-040` | 其他非流动资产（formula None） | **固定资产减值准备**（formula None） |
| `BS-050` | **合同负债** = `TB('2205','期末余额')` | 其他非流动资产（formula None） |

而 `resolve_report_line_account_codes` 的**最后一级兜底查询**
（`applicable_standard NOT LIKE 'project:%' ... LIMIT 1`，无 `ORDER BY`）在按准则查不到公式时
会**任取一条**。I5 走 soe 的 `BS-050`（formula 为 None）→ 落到兜底 → 取到 listed 的「合同负债」
→ 解析出 `2205`（**其他应付款/合同负债，负债类**）且 `resolved_from='report_config'`。
这是平台级缺陷，I5 是第一个暴露它的循环。

→ **处置**：`i_cycle_accounts` **不依赖共享件的兜底路径**，自己按 `(row_code, applicable_standard)`
精确查 `row_name` + `formula`，并用 `I_CYCLE_EXPECTED_NAMES` **校验 `row_name`**；行名不符即视为
「该准则下无公式」，走段兜底码，并记 `row_name_mismatch` 诊断。共享件本身不改（零回归）。

**② 二分 gross/provision 装不下 I1 的三段结构。** 实证 I1 公式
`TB('1701','期末余额')-TB('1702','期末余额')` 经 `split_gross_provision` 把 `1702 累计摊销`
判成 **gross**（名称不含「减值准备/坏账准备/信用减值」）→ 原值口径变成 `1701 + 1702` = 净额，
而审定表需要原值 / 累计摊销 / 减值准备**三段分开**。

→ **处置**：I 类改用**段化声明** `ISegmentSpec`，每段独立认领科目码 + 独立兜底 + 独立方向语义。
`ICycleAccounts.gross` / `.provision` 保留为兼容视图（供既有溯源面板 props）。

**③ 父子双计实证**（三个真实项目，`1701`/`1702`/`1801` 全部）：旧口径（父行 + 子行一起累加）
/ 新口径（叶子）= **恰好 2.0000 倍**。叶子和与父行 `diff=0.00`。

### 1. `four_table/i_cycle_accounts.py`

```python
@dataclass(frozen=True)
class ISegmentSpec:
    segment: str                       # 'cost' / 'amortization' / 'impairment' / 'expense'
    label: str                         # 中文段名（审定表段标题）
    fallback: tuple[str, ...] = ()     # 段兜底标准码（account_chart 实证值）
    name_keywords: tuple[str, ...] = ()      # 从公式码集中认领本段的名称关键字
    exclude_keywords: tuple[str, ...] = ()   # 否决词
    claim_priority: int = 0            # 认领顺序（与展示顺序解耦）
    absolute: bool = False             # 备抵段：聚合结果取绝对值
    credit_is_increase: bool = False   # 备抵段：credit=计提、debit=转回
    occurrence: bool = False           # 损益段：取本期发生额而非余额

#: 每循环的报表行（按准则）+ 段声明。声明顺序 = 审定表展示顺序。
I_CYCLE_ROW_CODES: dict[str, dict[str, str]] = {
    "I1": {"listed": "BS-033", "soe": "BS-045"}, ...
}
I_CYCLE_SEGMENTS: dict[str, tuple[ISegmentSpec, ...]] = {
    "I1": (cost(1701), amortization(1702, 备抵), impairment(1703, 备抵)),
    "I2": (cost(1704),),
    "I3": (cost(1711), impairment(())),      # account_chart 无 1712 → 空集
    "I4": (cost(1801),),
    "I5": (cost(()),),                        # 无标准科目 → 空集（宁缺勿造）
    "I6": (expense(6604, occurrence=True),),
}

async def resolve_i_cycle_accounts(ctx, wp_code: str) -> ICycleAccounts: ...
def claim_segments(codes, name_by_code, segments) -> tuple[dict[str, list[str]], list[str]]: ...
def detect_chart_conflict(codes, name_by_code, expected_names, row_code) -> list[dict]: ...
```

**解析流程**（全程 fail-open）：

1. `fetch_applicable_standards(ctx)` → 派生准则；按 `soe*` / 否则 `listed` 取 `row_code`。
2. `_fetch_report_line(ctx, row_code, standards)`：`project:{id}` → 逐准则精确匹配 → 兜底任取
   一条。**每级都同时取 `row_name`**。
3. **行名校验**：`row_name` 未命中 `I_CYCLE_EXPECTED_NAMES[wp_code]` → 丢弃公式 +
   记 `row_name_mismatch` 诊断（这是拦住 I5 拿到「合同负债」公式的关键闸）。
4. `extract_codes_from_formula(formula)` → 标准码集；`extract_signed_codes` → 符号。
5. 名称字典 = 项目级 `account_chart`（`source='standard'`）∪ **平台静态
   `backend/data/standard_account_chart.json`**（项目标准科目表缺行时兜底，实证 `1703` 只在
   5 个项目有 → 不加静态兜底则冲突检测漏判）。
6. `claim_segments`：按 `claim_priority` 升序，每个码归入首个「命中 `name_keywords` 且不命中
   `exclude_keywords`」的段；未被认领的码进 `unclaimed`。
7. `detect_chart_conflict`：`unclaimed` 码里名称与 `expected_names` 不符者 → `chart_conflict`。
8. 段无认领码 → 用 `spec.fallback`；段 `resolved_from` 相应降为 `fallback`。
9. `to_original_codes_with_flag(ctx, 段标准码)` → 客户原始码前缀 + `exact` 标志。

**`detect_chart_conflict`（R1.5）** 返回 `[{"code": "1703", "chart_name": "无形资产减值准备",
"expected": "开发支出/研发支出", "row_code": "BS-046"}]`，render 原样放进
`tb_source_codes.chart_conflict`。**只诊断不改写** `report_config`。

### 2. `four_table/i1_asset_categories.py`

```python
@dataclass(frozen=True)
class I1Category:
    key: str            # 稳定 key，如 'land_use_right'
    label: str          # 中文标签
    keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...] = ()
    source_ref: str = ''   # 源 xlsx 坐标，如 'I1 底稿目录!A9'

I1_CATEGORIES: tuple[I1Category, ...] = (...)  # 11 类，顺序即优先级

def classify_i1_leaf(code: str, name: str) -> str: ...
def category_defs_payload() -> list[dict]: ...   # 下发前端，中文标签只此一份
```

分类顺序铁律（与 F2/N4 同款）：先「住房使用权」再「土地使用权」（前者含「使用权」易被后者吃掉需
用 `exclude_keywords`）；「非专利技术」必须先于「专利权」；「数据资源」独立；泛「其他」兜底放最后。

### 3. render 输出契约（六个循环统一）

```python
payload = {
    ...既有键（component_type / responses_snapshot / tb_values / project_context / sheets）...
    "tb_source_codes": {          # 新增，R3.1
        "row_code": "BS-045", "formula": "TB('1701','期末余额')-TB('1702','期末余额')",
        "gross_standard": ["1701"], "gross": ["1701"],
        "provision_standard": ["1702", "1703"], "provision": ["1702", "1703"],
        "resolved_from": "report_config", "provision_resolved_from": "report_config",
        "provision_exact": True,
        "parent_check": {"1701": {"leaf_sum": 0.0, "parent": 0.0, "diff": 0.0}},
        "chart_conflict": [],
        "unmapped": [],           # 未命中类别的叶子（R4.2）
    },
    "adjudication_prefill": {...},   # R4：按类别/项目行
    "tb_leaf_categories": [...],     # I1/I4：{key,label,codes,opening,closing,debit,credit}
}
```

**灰度**：`tb_source_codes` / `adjudication_prefill` / `tb_leaf_categories` 三键仅在
`HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED=True` 时输出；`tb_values` 的**取数口径修正（叶子聚合 +
科目纠偏）不受开关控制**——它修的是既有输出的错误值，开关只控制新增能力。这是有意的口径分离，
characterization 基线测试相应更新（R10.4 的「逐字节等价」限定在三个新增键）。

### 4. 前端科目单一真源（以 I2 为范式）

```ts
export const I2_REPORT_ROW_CODE = { listed: 'BS-035', soe: 'BS-046' } as const
export const I2_GROSS_FALLBACK_STANDARD = '1704'   // 🔴 禁 1717 / 1703
export function i2GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  return src?.gross?.length ? src.gross : [I2_GROSS_FALLBACK_STANDARD]
}
export function i2AccountCode(src?: TbSourceCodes | null): string { ... }
```

守卫按文件参数化断言「I 类源码不得出现 `1717` / `1911` / `6602` / `1712` 作科目码或请求参数」。

### 5. I1 类别配置（前端 `i1CategoryScope.ts`）

```ts
export interface I1CategorySlot { key: string; label: string; seq: number; removable: boolean }
export function defaultI1Categories(): I1CategorySlot[]     // 11 类，来自 category_defs_payload
export function i1CategoryColumnKey(slot: I1CategorySlot): string  // `${slot.key}_${slot.seq}`
export function addI1Category(list, label): I1CategorySlot[]       // 撞名拒绝
export function renameI1Category(list, key, label): I1CategorySlot[]
```

上市披露表列 = `[项目, ...categories.map(columnKey), 合计]`；国企披露表行 = 四层 × `[合计行,
...categories, ]`。两者共用同一份 `categories`，改一处两侧同步（R7.2）。

### 6. 附注模板 rule 声明（脚本内）

复用 `backend/scripts/fix/_note_structure_kit.py` 的 `flat_columns` / `two_period_columns` /
`rule` / `run_section` / `build_cli` / `ensure_text_sections`。改名走 `rule(aliases=...)`
（**不能进 `drops`**，`drop_tables` 在 `apply_plan` 前执行会连行删掉）。

## Data Models

### `TbSourceCodes`（前端视图模型，复用 `composables/shared/tbSourceCodes.ts`）

新增可选字段，既有消费者（K1/K2）不受影响：

```ts
export interface TbSourceCodes {
  row_code?: string; formula?: string | null
  gross?: string[]; gross_standard?: string[]
  provision?: string[]; provision_standard?: string[]
  resolved_from?: 'report_config' | 'fallback'
  provision_resolved_from?: 'report_config' | 'fallback'
  provision_exact?: boolean
  parent_check?: Record<string, { leaf_sum: number; parent: number; diff: number }>
  chart_conflict?: Array<{ code: string; chart_name: string; expected: string; row_code: string }>
  unmapped?: string[]
}
```

### `adjudication_prefill`

```python
# I1（三段 × 类别）
{"segments": [
    {"segment": "cost",       "rows": [{"key": "land_use_right", "label": "土地使用权",
                                        "codes": ["1701.01"], "opening": 0.0, "increase": 0.0,
                                        "decrease": 0.0, "closing": 0.0}, ...]},
    {"segment": "amortization", "rows": [...]},   # credit=增加 / debit=减少（R2.1）
    {"segment": "impairment",   "rows": [...]},
]}
# I4（单段 × 项目行）
{"rows": [{"key": "decoration", "label": "长期待摊费用_装修费", "codes": ["1801.03"], ...}]}
```

### 附注子表键（表名）与前端常量对应

| 循环 | 变体 | 附注表名（修订后） | 前端常量 |
|---|---|---|---|
| I1 | listed | `无形资产情况` / `重要单项无形资产` / `确认为无形资产的数据资源` / `未办妥产权证书的土地使用权情况` | `I1_LISTED_SUBTABLE` |
| I1 | soe | `无形资产分类` / `确认为无形资产的数据资源` | `I1_SOE_SUBTABLE` |
| I2 | listed | `研发支出` / `开发支出` / `开发支出（续：资本化情况）` / `重要的资本化研发项目` / `开发支出减值准备` | `I2_LISTED_SUBTABLE` |
| I2 | soe | `开发支出` | `I2_SOE_SUBTABLE` |
| I3 | listed | `商誉账面原值` / `商誉减值准备` / `商誉减值测试关键假设` / `业绩承诺完成及商誉减值情况` | `I3_LISTED_SUBTABLE` |
| I3 | soe | `（1）商誉账面价值` / `（2）商誉减值准备` | `I3_SOE_SUBTABLE` |
| I4 | listed / soe | `长期待摊费用` | `I4_*_SUBTABLE` |
| I5 | listed / soe | `其他非流动资产` / `合同取得成本` | `I5_*_SUBTABLE` |
| I6 | listed / soe | `研发费用（按费用性质列示）` | `I6_*_SUBTABLE` |

旧名（`项  目` / 财会30号整段 / `（1）商誉账面原值`(soe) / `研发费用`(soe) / 两处段落泄漏名）
进 `I{N}_LEGACY_OBSOLETE_TABLES`，由 `buildRemovedTableKeys` 与本次推送键求差集后发送（R6.6）。

## Error Handling

| 失败点 | 处置 | 依据 |
|---|---|---|
| `report_config` 无该行 / 公式为 None | 回退 `spec.fallback_gross`，`resolved_from='fallback'` | R1.4 |
| `account_mapping` 无反解记录 | 退化为标准码一级前缀，`provision_exact=False`；备抵侧叠名称过滤 | 共享件既有语义 |
| `account_chart` 查询失败 | 降级码族启发判定备抵；`chart_conflict` 返空（不误报） | R1.5 |
| 叶子聚合超时 / DB 异常 | `asyncio.wait_for(..., timeout=5.0)` + `except Exception` 记 warning，render 继续 | 平台 fail-open 铁律 |
| I5 无科目 | `gross=[]` + 不产生 `adjudication_prefill`；溯源面板显示「本项目无标准科目映射，需手工编制」 | R1.4 / R4.5 |
| I6 `6604` 在 `tb_balance` 0 命中 | `tb_values` 为 0 且 `parent_check` 全 0；溯源面板提示「本项目未设置 6604 研发费用科目，请核对是否挂在管理费用下」 | R1.3 实证 |
| 推送时主体类型不匹配 | 服务端 `detect_standard_conflict` 抛 `StandardMismatchError` → 409，前端 catch 静默不写 | R8.6 |
| 幂等脚本 `--check` 发现欠账 | 非零退出，CI job 失败 | R10.5 |
| 附注模板改名后旧表残留 | `_removed_table_keys` 与本次推送键求差集；从未推过的同名表不删 | R6.6 |

## Testing Strategy

### 后端

| 测试文件 | 覆盖 |
|---|---|
| `backend/tests/four_table/test_i_cycle_accounts.py` | Property 2/3；六循环 spec 的 row_code 与兜底码；`detect_chart_conflict` 对 BS-035 命中 `1703` 冲突；反向自检（把兜底码换成 `1717` 则断言失败） |
| `backend/tests/four_table/test_i1_asset_categories.py` | Property 5；11 类参数化 + PBT + 打乱顺序反向自检；实证叶子名（`无形资产_土地使用权` 等 6 个）归类正确 |
| `backend/tests/test_i_cycle_leaf_aggregation.py` | Property 1/4；构造父子并存 fixture 验证不双计；备抵 roll-forward |
| `backend/tests/test_hi_extraction_characterization.py` | Property 11（扩展现有文件，六循环全覆盖） |
| `backend/tests/test_note_i_cycle_structure.py` | Property 6/7/8/14；openpyxl 直读 6 个源 xlsx 交叉比对 12 章节；含反向自检与归一函数（处理 `项  目` 双空格、首尾空格、`（1）` 前缀） |
| `backend/tests/test_i_cycle_formula_presets.py` | Property 13；sheet 存在性、科目存在性、防成环、`wp_name` 语义 |

### 前端

| 测试文件 | 覆盖 |
|---|---|
| `composables/__tests__/iCycleAccountScope.spec.ts` | Property 2；参数化扫 6 个 `iNAccountScope.ts` + 12 个披露 Tab + 6 个审定表 Tab 源码（先 `stripComments()` + 反向自检） |
| `composables/__tests__/i1CategoryScope.spec.ts` | Property 5 前端侧；稳定 key 不撞、撞名拒绝、改名保值、上市列与国企行同源 |
| `composables/__tests__/iCycleNoteSubtableContract.spec.ts` | Property 6/7/10；接入共享 helper P1~P6，`columnsPending` 为空 |
| `composables/__tests__/iCycleDisclosureWiring.spec.ts` | Property 9/12；自调度检测、`el-input-number` 归零、AI 端点与 `context` 为对象、`:project-id` 已传 |

### 实测（Wave 8）

真实 DB 直跑 render（不依赖 uvicorn 重载）验证六循环的 `tb_source_codes` / 叶子勾稽 / 预填；
浏览器（chrome-devtools MCP）验证披露表动态类别增删、千分符、自动同步落库；postgres MCP 只读
核对 `disclosure_notes.table_data`。**实测数据用后复原**。

## Correctness Properties

### Property 1: 叶子聚合恒等于父科目行金额

对任意项目与任意 I 类循环，`aggregate_leaves` 的结果按科目族求和后，等于该科目族父行在
`tb_balance` 的对应字段值（容差 0.01 元）。父子并存时不得双计。

**Validates: Requirements 1.6, 3.3**

### Property 2: 科目码不含已证伪的字面量

I 类后端策略、前端 composable、公式预设三处源码中，作为科目码或查询参数出现的字符串集合
与 `{'1717', '1911', '6602', '1712'}` 的交集为空（`6602` 在 I6 之外的合法用途需显式豁免并写依据）。

**Validates: Requirements 1.2, 1.3, 5.3**

### Property 3: 解析落空时 render 仍返回可用载荷

对任意 I 类循环，当 `report_config` 无该行、`account_mapping` 为空、或 DB 抛异常时，
render 仍返回非 None 载荷，且 `tb_source_codes.resolved_from == 'fallback'`。I5 允许
`gross == []`（宁缺勿造），其余循环 `gross` 非空。

**Validates: Requirements 1.4, 1.5**

### Property 4: 备抵方向与符号

对备抵段（`1702`/`1703`），`increase` 取自 `credit_amount`、`decrease` 取自 `debit_amount`，
且输出到审定表/披露表的余额为非负数；roll-forward `opening + increase - decrease == closing`
恒成立（容差 0.01）。

**Validates: Requirements 2.1, 2.2**

### Property 5: 类别分类完备且互斥

`classify_i1_leaf` 对任意 `(code, name)` 返回恰好一个类别 key；`I1_CATEGORIES` 各类的
`keywords` 在叠加 `exclude_keywords` 后不存在「A 的关键字是 B 标签子串且 B 未排除 A」的情形；
打乱 `I1_CATEGORIES` 顺序后至少一条断言失败（反向自检）。

**Validates: Requirements 4.1, 4.2**

### Property 6: 附注模板列元数据与源 xlsx 三向一致

对 I 类 12 个章节的每张表：模板 `headers` 的叶子列名序列 == 源 xlsx 对应区域的末级表头序列 ==
前端同步载荷 `columns` 的 `label` 序列；两级表头的 `group` 序列 == 源 xlsx 合并区的父表头序列；
单级表的每列都有 `flat: true` 且无 `group`。

**Validates: Requirements 6.2, 6.3, 8.2**

### Property 7: 表名无泄漏且与前端常量逐字一致

I 类 12 个章节的所有表名：不等于其 `headers[0]`、不以中文冒号或「如下：」结尾、长度不超过 40 字、
且集合等于前端 `I{N}_{VARIANT}_SUBTABLE` 的值集合。

**Validates: Requirements 6.4, 6.6**

### Property 8: 动态区骨架行数与占位

纯动态行区的 seed 行数 == `max(源模板固定行数, 1)`，且 seed 行不含仅由占位符（`……` 作为**列头**、
`项目N`、`可无限量添加行`）构成的数据行；`……` 作为**行**且参与源模板小计公式时必须保留。

**Validates: Requirements 6.5, 7.4**

### Property 9: 自动同步由数据变更触发

I 类 12 个披露 Tab 的源码（去注释后）中，`scheduleAutoSync` 不出现在任何同步函数
（`syncToNotes` / `syncToDisclosureNotes` / `handleSync`）的函数体内，且存在
`watch([...], () => scheduleAutoSync(...))` 形态的调用。

**Validates: Requirements 8.1**

### Property 10: 载荷与模板列头逐字一致且合计行齐备

对任意 I 类推送载荷：`sub_table_data` 的每个键存在于附注模板的 `tables[].name`；每张表的
`columns` 长度 == 模板该表 `headers` 长度；含合计概念的表的行集包含一行标 `is_total` 且其
`label` 与附注模板实证字面一致。

**Validates: Requirements 8.2, 8.4**

### Property 11: 灰度 OFF 时新增键不出现

`HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED=False` 时，六个循环 render 的返回值不含
`tb_source_codes` / `adjudication_prefill` / `tb_leaf_categories` / `hi_extraction_enabled`
任一键。

**Validates: Requirements 10.4**

### Property 12: 金额控件收敛

I 类 12 个披露 Tab 与 6 个审定表 Tab 的 `el-input-number` 出现次数为 0；`WpAmountInput` 的
出现次数 > 0；比例 / 摊销年限 / 剩余摊销期限 / 折现率字段不使用 `WpAmountInput`。

**Validates: Requirements 9.1, 9.3**

### Property 13: 公式预设 sheet 与科目均可验证

I 类每个预设块的 `sheet`（或 `wp_name` 推导出的 sheet）存在于对应源模板 xlsx 的 `sheetnames`；
每个 `account_codes` 元素存在于 `account_chart` 标准科目表；明细表块不含 `WP()` 引用审定表。

**Validates: Requirements 5.2, 5.3, 5.4**

### Property 14: 分段枚举不被强行套用

I 类 12 个附注章节的表名与行标签中不出现账龄档位字面量（`1年以内` / `1至2年` / `2至3年` /
`3年以上` 等）；若后续引入摊销期限分段，其数据结构复用既有段位枚举类型。

**Validates: Requirements 11.1, 11.3**
