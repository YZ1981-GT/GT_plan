# Design: F1 取数链路与披露表源模板保真

## Overview

本设计把 F1 的「四表库 → 底稿 → 披露表 → 附注」链路上 5 处已实证的缺口补齐，
原则是**复用平台既有单一真源，不新造机制**：

- 科目定位/叶子聚合继续走 `app/services/four_table`（K1 建、D1/K2/F1 已委托）；
- 减值准备新增的第二取数源复用 `report_account_mapping.build_trial_balance_code_filter`
  （与 `_fetch_f1_1123_audited` 同一范式）；
- 披露②表的数据源切换只改 `useF1DisclosureSoe` 的行构造，列定义 / 载荷 / 附注模板**一格不动**；
- 公式预设只往 `prefill_formula_mapping.json` 加块，走既有 `convert_prefill_presets` 收敛；
- 关联方识别只改 `build_f1_detail_rows_from_aux` 的一个入参，端点查询与 merge 语义不变。

### 源模板逐格实证（本设计的唯一裁决依据）

`backend/wp_templates/F/F1 预付账款.xlsx`（运行时权威副本）：

| sheet | 位置 | 内容 |
|---|---|---|
| `长期挂款检查表F1-5` | R5 表头 | A 债务人名称 / B 期末余额 / C 账龄 / E 未偿还或未结转的原因 / I 计提坏账准备金额 / **J 审定余额** |
| `附注披露信息(国企)` | A18~E18 | `A=RIGHT($A$3,…)`（被审计单位名）/ `B='长期挂款检查表F1-5'!A6` / `C=…!J6` / `D=…!C6` / `E=…!E6` |
| `附注披露信息(国企)` | R8:R10 | ①表**三级**表头 7 列（期末数{账面余额{金 额,比例（%）},坏账准备} × 期末/期初） |
| `附注披露信息(上市公司)` | B10~E13 | `='审定表F1-1'!I17..I20`（期末）/ `E17..E20`（上年年末） |
| `附注披露信息(上市公司)` | A28~B32 | `='实质性分析F1-4'!A41..A45` / `B41..B45`（前五名） |

### 科目映射链路（本 spec 的第 3 项缺口所在层）

```
tb_balance.account_code            客户原始码（点号）   1123.02.01 / 1231.03
        │ account_mapping(original → standard)          ← 项目级、可缺失
        ▼
trial_balance.standard_account_code 标准码（横杠）      1123 / 1231-04
        │ report_config.formula（按 applicable_standard 精确匹配）
        ▼
报表行 BS-008「预付款项」= TB('1123','期末余额')        ← 四准则同形，不减备抵
```

实证要点（项目 `0ec33ac9` / 2025）：

- `account_mapping` 把 `1123` 全部子科目收敛到标准码 `1123`（`minimal_prefix_set = ['1123']`）；
- 备抵侧 `1231-04` **在 `account_mapping` 中不存在**，但**在 `trial_balance` 中存在**
  （`坏账准备-预付账款`，金额 0）→ 现「标准码 → 反解 → `tb_balance` 前缀」路径必然退化为
  宽前缀 `1231`，叠「预付」名称过滤后为空；而标准码直查 `trial_balance` 可精确命中。
- 这解释了为什么 `TB('1231-04','期末余额')`（公式预设，走 `trial_balance`）与
  `impairment_prefill`（走 `tb_balance`）口径不同。

## Architecture

```
后端 render（_f1_prepayment.py）
  ├─ resolve_report_line_accounts(BS-008)            → gross / provision（原始码+标准码）
  ├─ _fetch_f1_leaf_rows → select_leaves             → 叶子行
  ├─ build_nature_prefill                            → adjudication_prefill.nature
  ├─ build_impairment_prefill (tb_balance 路径)   ┐
  └─ _fetch_provision_from_trial_balance (新)     ┴→ resolve_impairment_prefill (新纯函数)
                                                      → impairment_prefill  + tb_source_codes.provision_trial

后端归集端点（_f1_import_export.py）
  └─ aggregate_f1_detail_rows_from_aux
        ├─ _fetch_related_party_names (新)           → 关联方名单
        └─ build_f1_detail_rows_from_aux(..., related_parties=)  → relationType 自动标注

前端
  GtF1Prepayment.vue
    ├─ f1ImpairmentPrefill      （既有）
    ├─ f1ClientName （新）      ← project_context.client_name
    └─ F1TabDisclosureSoe
          └─ useF1DisclosureSoe
                └─ buildSoeOver1Rows (新纯函数)
                      ├─ F1-5 行（F1-lt-rows）  ← 优先
                      ├─ crossSheet.longTermRows ← F1-5 空时回退
                      ├─ over1MetaMap             ← 手工覆盖优先
                      └─ defaultCreditorUnit      ← 被审计单位名
```

数据流不变量：披露②表**只读**F1-5，永不回写；覆盖值只落披露表自己的 meta 键。

## Components and Interfaces

### 1. `backend/app/routers/wp_render_strategies/_f1_prepayment.py`

新增纯函数（可单测、无 I/O）：

```python
def resolve_impairment_prefill(
    tb_balance_result: dict[str, float] | None,
    trial_balance_end: float | None,
) -> dict[str, float] | None:
    """合并两条减值准备取数路径。

    优先 tb_balance 路径（同时给期初+期末）；其为空且 trial_balance 期末非零时
    退化为 ``{"end": x}``（**不含 prior** —— trial_balance v2 无期初列，不臆造）。
    两条都空返回 None（宁缺勿造）。
    """
```

新增 DB 函数（fail-open，与 `_fetch_f1_1123_audited` 同范式）：

```python
async def _fetch_provision_from_trial_balance(
    ctx: RenderContext, standard_codes: list[str]
) -> float | None:
    """按备抵**标准码**从 trial_balance 取期末减值准备（审定优先、回退未审，取绝对值）。"""
```

`render` 变更：
- `tb_source_codes` 增加 `provision_trial`（标准码列表）与 `provision_trial_amount`；
- `impairment_prefill` 改由 `resolve_impairment_prefill` 产出。

### 2. `backend/app/routers/wp_render_strategies/_f1_import_export.py`

```python
def match_related_party(name: str, registry: Sequence[str]) -> str | None:
    """双向包含匹配（去空白归一）；命中返回名单项，否则 None。纯函数。"""

def build_f1_detail_rows_from_aux(
    aux_entries, segments, *, row_limit=..., row_id_factory=None,
    related_parties: Sequence[str] | None = None,   # 新增，缺省 None = 行为不变
) -> list[dict]
```

`aggregate_f1_detail_rows_from_aux` 增查 `related_party_registry` 并透传（查询失败 fail-open 传 `None`）。

### 3. `audit-platform/frontend/src/components/workpaper/composables/useF1DisclosureSoe.ts`

新增导出纯函数（零 Vue 依赖，便于 PBT）：

```ts
export interface F1SoeOver1Source { kind: 'f1-5' | 'f1-2' | 'manual' }

export function buildSoeOver1Rows(input: {
  longTermSheetRows: F1LongTermSourceRow[]   // F1-5（F1-lt-rows）
  crossSheetRows: F1CrossLongTermRow[]       // F1-2 派生（回退）
  dynamicRows: F1SoeOver1Row[]               // 披露表手工新增
  metaMap: Record<string, Over1Meta>         // 手工覆盖（按债务单位名键）
  defaultCreditorUnit: string                // 被审计单位名
}): F1SoeOver1Row[]
```

优先级：`metaMap` 覆盖 > 源行值 > 缺省值；行源选择 = F1-5 非空则用 F1-5，否则用 F1-2。

`F1SoeOver1Row` 增字段 `source: 'f1-5' | 'f1-2' | 'manual'`（UI 显示来源 tag，载荷不推）。

### 4. `audit-platform/frontend/src/components/workpaper/f1/F1TabDisclosureSoe.vue`

- ②表新增「来源」列（只读 tag：F1-5 / F1-2 / 手工），紧随「债权单位」；
- 「债权单位」输入框 `placeholder` = 被审计单位名，值为空时显示缺省值（灰字）；
- 表格上方 `.src-hint` 琥珀块补一句源模板口径说明（数据源 = F1-5，期末余额取审定余额）。

### 5. `backend/data/prefill_formula_mapping.json`

新增 3 个 `wp_code="F1"` 块。`cell_ref` 全部带 sheet 语义前缀以保证页内唯一：

| sheet | cell_ref | formula |
|---|---|---|
| `附注披露信息(上市公司)` | 披露上市_账龄小计期末 | `=WP('F1','审定表F1-1','按账龄期末审定合计')` |
| | 披露上市_账龄小计上年年末 | `=WP('F1','审定表F1-1','按账龄期初审定合计')` |
| | 披露上市_减值准备期末 | `=TB('1231-04','期末余额')` |
| | 披露上市_减值准备上年年末 | `=TB('1231-04','期初余额')` |
| | 披露上市_合计行核对 | `=TB('1123','期末余额')` |
| | 披露上市_前五名合计 | `=WP('F1','实质性分析F1-4','前五名期末余额合计')` |
| `附注披露信息(国企)` | 披露国企_账龄小计期末 | `=WP('F1','审定表F1-1','按账龄期末审定合计')` |
| | 披露国企_账龄小计期初 | `=WP('F1','审定表F1-1','按账龄期初审定合计')` |
| | 披露国企_坏账准备期末 | `=TB('1231-04','期末余额')` |
| | 披露国企_坏账准备期初 | `=TB('1231-04','期初余额')` |
| | 披露国企_合计行核对 | `=TB('1123','期末余额')` |
| | 披露国企_超1年审定余额合计 | `=WP('F1','长期挂款检查表F1-5','审定余额合计')` |
| | 披露国企_前五名合计 | `=WP('F1','明细表F1-2','前五名期末审定合计')` |
| `长期挂款检查表F1-5` | 长期挂款_期末余额合计 | `=WP('F1','明细表F1-2','超1年期末审定合计')` |
| | 长期挂款_坏账准备合计 | `=TB('1231-04','期末余额')` |
| | 长期挂款_单户期末余额 | `=AUX('1123','客户','XX单位','期末余额')` |

> 🔴 `长期挂款审定合计`（已存在于 F1-1 块）与新增的 `披露国企_超1年审定余额合计` 表达式相同
> 但 `cell_ref` 不同 —— 这是**有意**的：`page_key` 忽略 sheet，同名会被静默去重丢弃。

## Data Models

### `checklist_responses` 键（F1，本 spec 涉及）

| item_id | 形态 | 说明 |
|---|---|---|
| `F1-det-rows` | JSON array | F1-2 明细行（含 `relationType` / `agingAudited` / `agingPrior`） |
| `F1-lt-rows` | JSON array | F1-5 长期挂款行（含 `auditedBalance` / `aging` / `reason`） |
| `F1-note-soe-over1-rows` | JSON array | 披露②表**手工新增**行（不含 F1-5/F1-2 派生行） |
| `F1-note-soe-over1-meta` | JSON object | 按债务单位名键的覆盖值 `{creditorUnit?, agingLabel?, reason?}` |
| `F1-note-soe-aging-bad-debt` | JSON object | 按账龄段键的逐段坏账准备 `{end, prior}` |

### render 输出（`project_context`）

| 键 | 变更 | 说明 |
|---|---|---|
| `client_name` | 既有 | 新增消费方：披露②表「债权单位」缺省值 |
| `tb_source_codes.provision` | 既有 | `tb_balance` 反解后的原始码前缀 |
| `tb_source_codes.provision_trial` | **新** | 备抵**标准码**（`1231-04` 等） |
| `tb_source_codes.provision_trial_amount` | **新** | `trial_balance` 期末减值准备 |
| `impairment_prefill` | 语义扩展 | 可为 `{end, prior}`（tb_balance 路径）或 `{end}`（trial_balance 路径） |

### 附注载荷（`sub_table_data`）不变

②表仍推 5 键 `creditor_unit / debtor_unit / end_balance / aging / reason`，
列定义 `F1_SOE_COLUMNS` 一格不动 —— 本 spec 只改**这些值从哪来**。

## Correctness Properties

### Property 1: F1-5 优先且回退零回归

`buildSoeOver1Rows` 在 `longTermSheetRows` 非空时输出行数 = F1-5 有效行数 + 手工新增行数；
在 `longTermSheetRows` 为空时输出与改造前（`crossSheetRows` + 手工新增）逐字段相等。

**Validates: Requirements 1.1, 1.3**

### Property 2: 手工覆盖单调优先

对任意 `metaMap`，若 `metaMap[name].reason` 为非空串，则输出行的 `reason` 恒等于该值，
与 F1-5 / F1-2 的 `reason` 无关；清空覆盖后回落到源行值。

**Validates: Requirements 1.4, 2.2**

### Property 3: 债权单位永不为空（有缺省值时）

对任意输入，若 `defaultCreditorUnit` 非空，则输出的每一行 `creditorUnit` 均非空串。

**Validates: Requirements 2.1, 2.3**

### Property 4: 期末余额取审定口径

对来自 F1-5 的行，输出 `endBalance` 恒等于该 F1-5 行的 `auditedBalance`
（= 期末余额 − 计提坏账准备），而非 `endBalance` 原值。

**Validates: Requirements 1.1, 1.2**

### Property 5: 减值准备合并的宁缺勿造

`resolve_impairment_prefill(None, None)` 返回 `None`；
`resolve_impairment_prefill(None, 0.0)` 返回 `None`（零值不算命中）；
`resolve_impairment_prefill({"end": a, "prior": b}, c)` 恒返回 `{"end": a, "prior": b}`（tb_balance 优先）。

**Validates: Requirements 3.2, 3.3**

### Property 6: 关联方匹配对空名单是恒等变换

`build_f1_detail_rows_from_aux(entries, segs, related_parties=None)` 与
`related_parties=[]` 的输出，与改造前逐字段相等（全部 `非关联方`）。

**Validates: Requirements 5.3**

### Property 7: 关联方匹配双向包含且去空白

`match_related_party` 对 `("  重庆和平药房连锁有限责任公司分店 ", ["重庆和平药房连锁有限责任公司"])`
与 `("重庆和平药房", ["重庆和平药房连锁有限责任公司"])` 均命中；对无交集名称返回 `None`。

**Validates: Requirements 5.2**

### Property 8: 公式预设 cell_ref 页内唯一

运行态 `convert_prefill_presets()` 中 `page_key == "workpaper:F1"` 的条目，
`target_cell` 集合大小 == 条目数（无静默去重丢弃）。

**Validates: Requirements 4.2, 4.5**

## Error Handling

| 场景 | 处理 |
|---|---|
| `report_config` 查不到 `BS-008` | `resolve_report_line_accounts` 内部 fail-open 回退 `('1123',)`，render 不抛 |
| `trial_balance` 查询异常 | `_fetch_provision_from_trial_balance` 捕获 → `rollback()` → 返回 `None`，减值准备退回 tb_balance 路径 |
| `related_party_registry` 查询异常 | 传 `related_parties=None` → `relationType` 行为与改造前逐字一致 |
| F1-5 行 JSON 解析失败 | `safeParseJson` 返回 `[]` → ②表回退 F1-2 派生行（Property 1 的回退分支） |
| `client_name` 为空 | 「债权单位」保持空串并由 `F7-9` 完整性校验提示（不臆造名称） |
| 披露②表某行 `debtorUnit` 为空 | 该行不进载荷（避免推出无主体的披露行） |

所有后端新增路径一律 fail-open：取数失败只降级为「无预填」，绝不阻断 render。

## Testing Strategy

| 层 | 文件 | 覆盖 |
|---|---|---|
| 源模板事实 | `backend/tests/test_f1_source_template_facts.py` | openpyxl 直读断言 F1-5 表头与国企②表四列公式指向，含反向自检 |
| 后端纯函数 | `backend/tests/test_f1_four_table_extraction.py`（扩展） | `resolve_impairment_prefill` 三态 + PBT |
| 后端纯函数 | `backend/tests/test_f1_related_party_match.py` | 双向包含匹配 / 空名单恒等 / merge 语义 |
| 公式预设 | `backend/tests/test_f1_formula_presets.py` | `cell_ref` 页内唯一 / 三 sheet 齐备 / `validate_formula` 空错误 / 防循环 |
| 前端纯函数 | `useF1DisclosureSoe.spec.ts`（扩展） | Property 1~4，含 PBT |
| 前端契约 | `f1NoteSubtableContract.spec.ts`（扩展） | 列常量 ↔ 附注模板 `columns` ↔ 源 xlsx 三方一致 |
| 活体 | chrome-devtools + postgres 只读 | F1-5 → ②表 → 推送 → §八、7 落库，数据完整复原 |

PBT 生成器一律收敛到金额域（`min`/`max` 有界、`noNaN`），防 `±Infinity` 漏进公式。
