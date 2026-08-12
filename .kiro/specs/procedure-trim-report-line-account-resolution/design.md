# Design Document

## Overview

把裁剪判据的科目金额定位从「程序名 ↔ 科目名子串匹配」改为「程序 → 报表行 → 报表公式 → 金额」。

**净新增只有两个后端模块 + 一处前端优先级调整**，三段映射的每一段都委托既有生产真源：

```
wp_code                              ← procedure_instances
   │  ① 跨循环索引（本 spec 新建，零新增映射知识）
   │     report_line_index.resolve_report_line_ref()
   │       └─ dispatch 到 four_table 既有 per-cycle 声明取 row_code
   ▼
row_code (BS-002)                    ← four_table/*_cycle_specs.py 既有常量
   │  ② report_config 按 applicable_standard 取该行的 formula
   ▼
formula "TB('1001',…)+TB('1002',…)+TB('1012',…)"   ← report_config 既有数据
   │  ③ 报表取数引擎求值（与报表页同一口径）
   │     ReportFormulaParser.execute()
   ▼
amount 4,467,536.12
```

### 三条关键设计判断

**判断 1：索引只做 dispatch，不持有任何 `row_code` 字面量。**

`four_table` 里已有 11 个循环的 `row_code` 声明（`d_cycle_specs.D2_SPEC.row_code == "BS-006"` 等）。若索引再抄一份，就成了平台反复治的双真源：某循环改了报表行号，索引不跟随，而两侧各自的单测都全绿（各用自己的常量构造样本）。故索引的实现形态是**函数 dispatch 表**，取值一律 `getattr(spec, "row_code")`，并配一条交叉锁死守卫。

**判断 2：金额走 `ReportFormulaParser` 而不是自己聚合科目。**

看起来更"轻"的做法是拿 `resolve_report_line_accounts()` 的 `gross_standard` 再自己求和，但那会引入第二个金额口径 —— 审计师会在报表页看到一个数、在裁剪建议里看到另一个数，且无从判断该信哪个。`ReportFormulaParser` 已处理前缀聚合（`_get_tb_rows_prefix`：`TB('2221')` 自动含 `222102`）、`SUM_TB` 区间、公式符号运算（`TB('1122') - TB('1231')`）。复用它使「裁剪建议的金额 = 报表上那个数」成为结构性事实而非巧合。

**判断 3：报表行映射优先、科目名匹配保留为兜底，且两者都不改 `decideTrim`。**

`procedure-trimming-and-delegation-intelligence` 已收口（26/26，含 12 条变异检验）。本 spec 只改「`accountAmount` 从哪来」，不动 9 档顺序、不动短路语义、不新增档位。`decideTrim` 的入参增加一个**只进 evidence 不参与判断**的 `amountSource` 标识。

## Architecture

### 数据流（改造后）

```
build_trim_decision_context(db, pid, year, cycles)
  ├─ _load_accounts()            ← 不变（科目名聚合，供档 4 数据存在性 + 循环级判定）
  ├─ _load_materiality()         ← 不变
  ├─ _load_risk()                ← 不变
  ├─ _load_completeness_override()← 不变
  ├─ _load_workpaper_entry()     ← 不变
  └─ _load_report_line_amounts() ← 【新增】additive 第六维
        │
        ├─ _collect_probe_wp_codes()  ← 复用（已有：取本项目待裁决程序的 wp_code）
        ├─ report_line_index.resolve_report_line_ref(wp_code, standards)
        └─ trim_report_line_amounts.resolve_trim_report_line_amounts()
              ├─ report_config 查 (report_type, row_code, applicable_standard)
              └─ ReportFormulaParser(db, pid, year).execute(formula, {})

前端 buildAndDecide(p, ctx, …)
  └─ resolveAccountAmount(p, ctx)   ← 【新增】
        ├─ ctx.report_line_amounts[wpCode]  优先（status === 'resolved'）
        └─ resolveAccountName(p, ctx)       兜底（现有科目名匹配，逐字不动）
```

### 为什么新增维度而不改 `_load_accounts`

`_load_accounts` 的输出（`{科目名: {amount, cycle}}`）有三个现存消费方：档 4 的 `subjectDataState` / `cycleHasData`、复核视图的金额未知统计、以及 `resolveAccountName` 自己。改它的结构会同时波及这三处，而本 spec 只需要「按 wp_code 查金额」这一条新能力 ⇒ 加第六维、原五维逐字不动，零回归由结构保证。

### wp_code 归一的两侧一致性

真实库 `procedure_instances.wp_code` 存在区间形态（实证 `D2-1至D2-4` / `E1-14至E1-15` / `D4-13至D4-20`）。归一规则 = 取首个「字母段 + 数字段」（`D2-1至D2-4` → `D2`）。

前端 `subjectPrefixOf()` 已有等价正则 `/^([A-Z]+\d+)/`。后端需要一份 Python 版，两侧语言不同无法共享实现 ⇒ 用**交叉锁死守卫**兜住：前端守卫读后端 py 源码抽正则字面量，在同一组样本（含真实库实际形态）上断言两侧归一结果逐个相等。

## Components and Interfaces

### 组件 1：`backend/app/services/four_table/report_line_index.py`（新建）

跨循环「wp_code → 报表行」索引。**本模块不含任何 `row_code` 字面量。**

```python
#: 非科目余额驱动循环（与 procedureTrimDecision.BALANCE_DRIVEN_CYCLES 的补集一致）
NON_BALANCE_DRIVEN_CYCLES: frozenset[str] = frozenset({"A", "B", "C", "S"})

REF_RESOLVED = "resolved"
REF_NO_REPORT_LINE = "no_report_line"
REF_NON_BALANCE_DRIVEN = "non_balance_driven"

@dataclass(frozen=True)
class ReportLineRef:
    wp_code: str                 # 归一后的底稿主码（D2-1至D2-4 → D2）
    row_code: str = ""           # 空 = 未解析出
    status: str = REF_NO_REPORT_LINE
    source_symbol: str = ""      # 取值出处，如 "d_cycle_specs.D2_SPEC.row_code"
    reason: str = ""             # 未解析时的中文原因

def normalize_wp_code(raw: str) -> str: ...
def resolve_report_line_ref(wp_code: str, applicable_standards=None) -> ReportLineRef: ...
def indexed_wp_codes() -> list[str]: ...      # 供守卫枚举覆盖面
```

dispatch 表按循环字母分发到既有件，**每个分支只做取值不做判断**：

| 循环 | 委托对象 | 准则维度 |
|------|---------|---------|
| D | `d_cycle_specs.spec_of(code).row_code` | 无 |
| E | `e_cycle_specs.E1_REPORT_ROW_CODE` | 无（四准则一致，已实证） |
| F | `f_cycle_specs.spec_of(code).row_code` | 无 |
| G | `g_cycle_specs.spec_of(code).row_code` | 无 |
| H | `h{n}_account_scope.H{n}_ACCOUNT_SPEC.row_code` | 无 |
| I | `i_cycle_accounts.resolve_row_code(code, standards)` | **有**（既有件已处理） |
| J | `j_cycle_account_scope.pick_spec(J{n}_SPEC_BY_ENTITY, standards).row_code` | **有**（既有件已处理） |
| K | `k_cycle_specs.get_k_cycle_spec(code).row_code_soe \| row_code_listed` | **有** |
| L | `l_cycle_specs.spec_of(code).row_code` | 无 |
| M | `m_cycle_specs.spec_of(code).row_code` | 无 |
| N | `n_cycle_specs.spec_of(code).row_code` | 无 |

- 循环字母 ∈ `NON_BALANCE_DRIVEN_CYCLES` → `status = REF_NON_BALANCE_DRIVEN`（不是失败，是不适用）
- dispatch 命中但 `spec_of()` 返 `None`（该 wp_code 未登记）→ `status = REF_NO_REPORT_LINE` + reason 写明是哪个循环的哪个码未登记
- `source_symbol` 必填：它是「这个 row_code 从哪来」的溯源，也是守卫做交叉锁死的锚

### 组件 2：`backend/app/services/trim_report_line_amounts.py`（新建）

报表行 → 金额。**四态，一律不兜 0。**

```python
AMOUNT_RESOLVED = "resolved"
AMOUNT_NO_REPORT_LINE = "no_report_line"       # 索引无落点
AMOUNT_FORMULA_UNAVAILABLE = "formula_unavailable"  # 该行无 TB 公式 / 含 ROW() / 求值失败
AMOUNT_STANDARD_UNSET = "standard_unset"       # 项目未设适用准则

@dataclass(frozen=True)
class ReportLineAmount:
    wp_code: str
    status: str
    amount: float | None = None      # 🔴 非 resolved 态恒 None，绝不为 0
    row_code: str = ""
    row_name: str = ""
    formula: str | None = None
    standard_codes: tuple[str, ...] = ()   # 参与计算的标准码（extract_account_codes 产出）
    applicable_standard: str = ""
    source_symbol: str = ""
    reason: str = ""

async def resolve_trim_report_line_amounts(
    db, project_id, year: int, wp_codes: list[str],
) -> dict[str, ReportLineAmount]: ...
```

实现要点：

1. **准则取值**复用项目既有字段；未设置 → 全部 `AMOUNT_STANDARD_UNSET`（不默认取某变体，R3.3）
2. `report_config` 按 `(row_code, applicable_standard, is_deleted=false)` 查一次批量取回，不逐 wp_code 发查询
3. `ReportFormulaParser` **每个项目只建一个实例**（它内部有 `_tb_cache` / `_tb_prefix_cache`，复用实例即天然批量）
4. 含 `ROW()` 引用的公式 → `AMOUNT_FORMULA_UNAVAILABLE`（判据：`parser.extract_row_refs(formula)` 非空）。不传假的 `row_cache` 去凑一个值
5. `standard_codes` 取 `parser.extract_account_codes(formula)`（既有方法），供溯源展示
6. 求值异常 → 记 **ERROR** 级日志（不是 WARNING）+ `AMOUNT_FORMULA_UNAVAILABLE`。本平台已多次出现 `except Exception` 把接线错误吞成「本项目无此数据」，故此处必须留下可检索的错误痕迹

### 组件 3：`backend/app/services/trim_decision_context.py`（改造，additive）

```python
DIM_REPORT_LINE = "report_line"          # 加入 DEGRADATION_DIMENSIONS

_RESULT_KEYS = (..., "report_line_amounts")   # 第八键

async def _load_report_line_amounts(db, project_id, year, cycles) -> tuple[dict, list[dict]]:
    """装配 {wp_code: ReportLineAmount.as_dict()}；整体失败 → {} + 一条 degradation。"""
```

- 复用 `_collect_probe_wp_codes()` 拿目标 wp_code 清单（与底稿录入探测同一口径，不新建第二套目标集）
- 既有七键**逐字不动**；`degradations` 新增维度取值域一条
- 整体取数失败 → `{}` + degradation（前端据此退回科目名兜底并标注）

### 组件 4：`audit-platform/frontend/src/services/commonApi.ts`（改造，additive）

```ts
export interface TrimReportLineAmount {
  status: 'resolved' | 'no_report_line' | 'formula_unavailable' | 'standard_unset'
  amount: number | null
  row_code: string
  row_name: string
  formula: string | null
  standard_codes: string[]
  applicable_standard: string
  source_symbol: string
  reason: string
}

export interface TrimDecisionContext {
  // …既有七键不动…
  /** {wp_code: 报表行金额}；空 dict 必伴随一条 report_line degradation */
  report_line_amounts: Record<string, TrimReportLineAmount>
}
```

### 组件 5：`audit-platform/frontend/src/views/ProcedureTrimming.vue`（改造）

新增 `resolveAccountAmount()`，**它是 `buildAndDecide` 取金额的唯一入口**：

```ts
type AmountSource = 'report_line' | 'account_name' | null

interface ResolvedAmount {
  amount: number | null
  source: AmountSource
  reportLine: TrimReportLineAmount | null
  accountName: string | null
  /** 两个来源都命中且金额不等时的差异描述（R5.2 溯源用） */
  divergence: string | null
}

function resolveAccountAmount(p: any, ctx: TrimDecisionContext): ResolvedAmount
```

优先级与既有代码的关系：

- `resolveAccountName()` **逐字不动**（仍是科目名兜底的唯一实现，也仍供复核视图定位科目名用）
- 报表行命中（`status === 'resolved'` 且 `amount` 是有限数）→ `source = 'report_line'`
- 否则退回科目名匹配 → `source = 'account_name'`
- 两者都命中且金额不等 → 采用报表行值，`divergence` 记两个数（R5.2）
- 两者都未命中 → `amount = null`（与改造前同）

### 组件 6：`procedureTrimDecision.ts`（改造，additive，不改判据）

```ts
export interface TrimDecisionInput {
  // …既有字段不动…
  /** 🔴 只进 evidence，不参与任何档位判断（R5.4） */
  amountSource?: 'report_line' | 'account_name' | null
  reportLine?: { rowCode: string; rowName: string; formula: string | null; standardCodes: string[] } | null
}

export interface TrimEvidence {
  // …既有字段不动…
  amountSource?: 'report_line' | 'account_name' | null
  reportLine?: { rowCode: string; rowName: string; formula: string | null; standardCodes: string[] } | null
}
```

**九档的条件表达式一律不引用这两个新字段** —— 守卫按源码级断言钉死（在 `decideTrim` 函数体内 `amountSource` / `reportLine` 只允许出现在 `buildEvidence` 的调用链里）。

### 组件 7：溯源展示（改造，复用既有机制）

- 裁剪建议列的 tooltip 与确认后写入 `skip_reason` 的规范文本：追加「取自报表行 {row_code} {row_name}（{formula}）」
- 兜底来源显式标注：建议列加一个 `el-tag`「科目名匹配」（区别于报表行映射），使复核者知道该金额可靠性较低（R6.3）
- 复核视图（Task 20 交付的只读视图）改读 `resolveAccountAmount()` 同一函数（R6.2）
- **不新建溯源字段**：报表行信息进既有 `TrimEvidence`，不另开一套（R6.4）

## Data Models

### 无迁移

本 spec **不新增数据库列、不改表结构、不改 `report_config` 数据**。`report_line_amounts` 是运行时装配的只读上下文，不持久化。

已落库的 `procedure_instances.suggestion_state`（`procedure-trimming-*` Task 11 的 V146）结构不变；报表行溯源信息进 `suggestion_state.evidence`（该字段是 JSONB，additive 加键零迁移）。

### `report_config` 读取键

```sql
SELECT row_name, formula
FROM report_config
WHERE row_code = :row_code
  AND applicable_standard = :standard
  AND is_deleted = false
-- 唯一索引 uq_report_config_type_code_standard (report_type, row_code, applicable_standard)
-- ⇒ 同一 (row_code, standard) 在不同 report_type 下理论可有多行；
--    实证 BS-*/IS-*/IMP-* 前缀与 report_type 一一对应，故按前缀推 report_type 并断言唯一
```

## Error Handling

| 情形 | 处理 | 可观测性 |
|------|------|---------|
| wp_code 无报表行落点 | `AMOUNT_NO_REPORT_LINE`，退回科目名兜底 | 前端标注「科目名匹配」 |
| 循环属 A/B/C/S | 索引返 `REF_NON_BALANCE_DRIVEN` | 不进 degradations（这是不适用，非降级） |
| 项目未设适用准则 | 全部 `AMOUNT_STANDARD_UNSET` + 一条 degradation | 摘要区标注 |
| `report_config` 该行无公式 | `AMOUNT_FORMULA_UNAVAILABLE` | reason 写明「报表行 {code} 未配置取数公式」 |
| 公式含 `ROW()` | `AMOUNT_FORMULA_UNAVAILABLE` | reason 写明「该行依赖其它报表行的计算结果」 |
| 公式求值抛异常 | `AMOUNT_FORMULA_UNAVAILABLE` + **ERROR 日志** | 日志含 wp_code / row_code / formula |
| 整个维度取数失败 | `{}` + degradation | 摘要区标注「未做报表行取数」 |

**一律不产生 0**：本平台已实证「编造 0 会让该程序被误判成低于任何阈值而产生裁剪建议」，而正确结论是「该维度对它不可用」。

## Testing Strategy

### 后端守卫（新建 3 个文件）

| 文件 | 覆盖 |
|------|------|
| `backend/tests/procedure_trim/test_report_line_index.py` | 索引零字面量 / 交叉锁死 / 覆盖面 / wp_code 归一 / A~S 不适用 / `report_config` 存在性（连库） |
| `backend/tests/procedure_trim/test_trim_report_line_amounts.py` | 四态 / 不兜 0 / 批量查询 / 前缀聚合 / 符号运算 / `ROW()` 拒解析 / 异常记 ERROR（连库真跑一次） |
| `backend/tests/procedure_trim/test_trim_context_report_line_wiring.py` | 第八键 additive / 既有七键零回归 / degradation 维度 / 目标集与 `_collect_probe_wp_codes` 同源 |

### 前端守卫（新建 2 个文件）

| 文件 | 覆盖 |
|------|------|
| `.../src/views/__tests__/trimAmountSourcePriority.spec.ts` | 优先级 / 兜底保留 / divergence / `resolveAccountName` 未被改动 / 复核视图同源 / 与后端归一正则交叉锁死 |
| `.../composables/__tests__/trimDecisionAmountSourceNeutrality.spec.ts` | **九档判断不引用 `amountSource` / `reportLine`**（源码级，函数体内出现位置受限）+ evidence 带这两个字段 |

### 变异检验（强制，≥8 条）

新建 `backend/scripts/check/mutate_report_line_resolution_guards.py`，逐条必须 RED：

1. 索引里写死一个 `row_code` 字面量（应被「零字面量」守卫打红）
2. 索引改取另一个循环的 spec（交叉锁死打红）
3. 归一正则去掉数字段（`D2-1至D2-4` → `D`）
4. A/B/C/S 从不适用改成无落点（两态混同）
5. 非 resolved 态把 `amount` 从 `None` 改成 `0.0`
6. 含 `ROW()` 的公式改为「传空 row_cache 强行求值」
7. 求值异常从 ERROR 降级为 WARNING
8. 前端优先级反转（科目名优先于报表行）
9. `decideTrim` 的某档条件引用 `amountSource`
10. 复核视图另算一份金额（不走 `resolveAccountAmount`）

判据按**失败测试名集合求差集**（不看退出码）；锚点行级唯一且 `hits == 1`；备份 `.bak` + `--restore` + md5 核验字节级还原；锚点禁用跨行字面量（工作树 CRLF）。

### 真实库验收

新建 `backend/scripts/diagnose/verify_report_line_amounts_live.py`（默认只读）：

- 遍历有 `procedure_instances` 的项目 × 各自准则变体，逐 wp_code 输出四态分布
- 对 `resolved` 态做**独立算术复核**：另按 `extract_account_codes` 拿到的标准码直接 SQL 聚合 `trial_balance`，与 `ReportFormulaParser` 结果比对（含减项公式的符号）
- 覆盖不到的准则变体输出 `UNVERIFIABLE`，不用构造数据冒充
- 连库用专用一次性 engine（`poolclass=NullPool`）+ 同 loop `dispose()`
- 中文输出前设 `PYTHONIOENCODING=utf-8` 或直接写盘

### 零回归基线

- `_load_accounts` / `_load_materiality` / `_load_risk` / `_load_completeness_override` / `_load_workpaper_entry` 五个维度的输出与改造前逐字节相同
- `decideTrim` 在 `amountSource` 缺省时的输出与改造前逐字相同（characterization）
- `backend/tests/procedure_trim/` 全目录基线 **328 passed / 1 skipped**（2026-08-12 实测），改造后新增例数应恰等于新守卫例数
- 零回归判据用「施加改动前 vs 施加改动后」前后对照，**禁用 HEAD-swap**（本仓库并发度高）

### 浏览器实测

E 循环是本 spec 的立项缺陷现场，必须在浏览器里证实：

- 切到 E 循环跑智能裁剪 → 建议列出现重要性类理由码
- 建议金额与 `report_config` 的 `BS-002` 公式独立计算结果一致（`1001 + 1002 + 1012` 的 `trial_balance` 聚合）
- 溯源可见报表行编码与公式原文
- 涉及写库的步骤按基线复原并以独立查询核实（复用 `backend/scripts/e2e/trim_e2e_baseline.py`，它已收六个域并经三次真实写入→复原验证）

## Correctness Properties

### Property 1: 索引零新增映射知识
索引模块的**代码**（剥注释与 docstring 后）不含任何形如 `BS-\d+` / `IS-\d+` / `IMP-\d+` 的字面量；每个 dispatch 分支的返回值都可追溯到 `four_table` 既有常量。
**Validates: Requirements 1.1, 1.2**

### Property 2: 索引与 per-cycle 声明交叉锁死
对索引覆盖的每个 wp_code，`resolve_report_line_ref().row_code` 与直接读对应 per-cycle 声明得到的 `row_code` 逐字相等；任一侧改动而另一侧未跟进即打红。
**Validates: Requirements 1.6**

### Property 3: 无落点与不适用两态可区分
A/B/C/S 循环返 `REF_NON_BALANCE_DRIVEN`；D~N 中未登记的 wp_code 返 `REF_NO_REPORT_LINE` 且 reason 非空。两态不得混同，也不得返回空串或抛异常。
**Validates: Requirements 1.3, 1.4**

### Property 4: 索引产出的报表行在真实库存在
索引覆盖的每个 `row_code` 在 `report_config`（`is_deleted = false`）中至少有一行。
**Validates: Requirements 1.5**

### Property 5: wp_code 归一覆盖真实库实际形态
`normalize_wp_code` 对真实库 `procedure_instances.wp_code` 的全部 distinct 取值都能归一到「字母段 + 数字段」，且与前端 `subjectPrefixOf` 在同一组样本上结果逐个相等。
**Validates: Requirements 1.7**

### Property 6: 金额复用报表引擎且不按槽拆
金额解析模块调用 `ReportFormulaParser`；其代码不含第二份公式求值或科目求和实现，也不引用 `SemanticAccountSpec` 的 slot 结构。
**Validates: Requirements 2.1, 2.5**

### Property 7: 前缀聚合与区间语义成立
`TB('code')` 的结果含该码全部子科目（构造 `1231` 与 `1231-03` 双行样本验证）；`SUM_TB('lo~hi')` 覆盖区间内全部科目。
**Validates: Requirements 2.2, 2.3**

### Property 8: 公式符号运算正确
含减项的公式（`TB('1122') - TB('1231')`）结果等于各项按符号加权和，不等于各项绝对值之和。
**Validates: Requirements 2.4**

### Property 9: `ROW()` 引用一律拒解析
公式含 `ROW()` 时状态为 `formula_unavailable` 且 `amount` 为 `None`；不得传入伪造的 `row_cache` 求出部分结果。
**Validates: Requirements 2.6**

### Property 10: 按准则取到各自的行与公式
同一 wp_code 在不同 `applicable_standard` 下取到对应的 `row_code` 与 `formula`；对公式按变体不同的行（`BS-006`），四个变体的 `standard_codes` 集合不全相同。准则选择一律经既有件，不另写判断。
**Validates: Requirements 3.1, 3.2, 3.4**

### Property 11: 准则未设置即不可解析
项目 `applicable_standard` 缺失时全部返 `standard_unset`，不落到任何默认变体。
**Validates: Requirements 3.3**

### Property 12: 四态可区分且非 resolved 恒无金额
状态取值域恰为四态；任何非 `resolved` 态的 `amount` 为 `None`（不是 `0`、不是缺键）；每态有独立且互不相同的中文 reason 模板。
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 13: 异常记 ERROR 且不阻断
求值异常时日志级别为 ERROR 且消息含 wp_code / row_code；该 wp_code 转不可解析而其余 wp_code 与其余五个维度不受影响。
**Validates: Requirements 4.4, 4.5**

### Property 14: 报表行优先、科目名兜底、差异留痕
报表行 `resolved` 时 `source === 'report_line'`；未命中时退回 `account_name`；两者都命中且金额不等时采用报表行值并填 `divergence`。
**Validates: Requirements 5.1, 5.2**

### Property 15: 未命中零回归且九档语义不变
`report_line_amounts` 为空时 `buildAndDecide` 的入参与 `decideTrim` 的输出与改造前逐字相同；`decideTrim` 的档位数量与顺序不变；九档条件表达式不引用 `amountSource` / `reportLine`；上下文既有七键逐字节不变。
**Validates: Requirements 5.3, 5.4, 5.5, 5.6**

### Property 16: 溯源字段齐备且不新建第二套
`resolved` 态的 evidence 含 `rowCode` / `rowName` / `formula` / `standardCodes` 四项；这些信息落在既有 `TrimEvidence` 内，不存在并行的第二套溯源字段。
**Validates: Requirements 6.1, 6.4**

### Property 17: 裁剪页与复核视图金额同源
两处的金额与来源都由 `resolveAccountAmount()` 派生；相同输入下逐项相等（源码级断言复核视图无第二个取金额实现）。
**Validates: Requirements 6.2**

### Property 18: 兜底来源在界面上显式可辨
`source === 'account_name'` 时建议列渲染兜底标记；`source === 'report_line'` 时不渲染该标记。
**Validates: Requirements 6.3**

### Property 19: 守卫分类明确且变异全 RED
Wave 1 守卫的类 A 全绿、类 B 全红且失败消息含「尚未实现（Task N）」；变异脚本 ≥8 条逐条 RED，判据按失败测试名集合求差集。
**Validates: Requirements 7.1, 7.2**

### Property 20: 真实库验收诚实报告
验收脚本对覆盖不到的准则变体输出 `UNVERIFIABLE`；`resolved` 态经独立 SQL 聚合复核一致。
**Validates: Requirements 7.3**

### Property 21: 浏览器实测与数据复原
E 循环在浏览器中产出重要性类建议且金额与独立计算一致；写库步骤按基线复原并经独立查询核实。
**Validates: Requirements 7.4, 7.6**

### Property 22: CI job 可解析且无重名
新增 job 经 `yaml.safe_load` 可解析、名称与既有 job 无重复、引用的测试文件全部已存在。
**Validates: Requirements 7.5**

## Notes

### 与并发 spec 的边界

- **`e-cycle-extraction-formula-and-disclosure-completion`**：本 spec 只**读** `e_cycle_specs.E1_REPORT_ROW_CODE`，不改该模块。若届时该 spec 正在改 E 循环的 spec 常量，本 spec 的交叉锁死守卫会自动跟随（这正是判断 1 的目的）。
- **`i-cycle` / `k-cycle` / `l-cycle` / `g7-column-alignment`**：同上，本 spec 对它们的声明只读不写。
- **`report_config` 数据**：本 spec 不改。若真实库验收发现错码，登记独立议题（范式见已归档的 `report-config-account-code-integrity`）。
- **`procedure-trimming-and-delegation-intelligence`**：已归档（26/26）。本 spec 是它的后继，改动集中在 `trim_decision_context.py` 与 `ProcedureTrimming.vue`，两文件届时应无并发写入者。

### 已知不做（避免后续会话重复提议）

- **不改 `decideTrim` 的 9 档顺序**：D 循环因完整性豁免不产生金额类建议是设计使然。
- **不补 `resolveAccountName` 那个未实现的第二匹配方向**：实证即便补上也救不了本例（程序名「货币资金 - 函证（Leap应对措施-函证）」不被「其他货币资金」包含），且报表行映射一旦生效它就退居兜底。
- **不把金额解析搬到前端**：`report_config` 与 `trial_balance` 都在后端，前端拿不到公式求值所需的科目行。
- **不为 `cash_flow_statement` / `equity_statement` 补 `TB()` 公式**：这两类报表行不是科目余额驱动循环的对象。
- **不做报表行 → 明细科目的反向展开**：裁剪判据只需行级合计。

### 落地顺序硬约束

1. 组件 1（索引）必须先于组件 2（金额），后者依赖前者的 `ReportLineRef`。
2. 组件 3（上下文接线）必须在组件 2 之后，且**必须在同一轮里跑通零回归**（既有七键逐字节比对）。
3. 前端组件 5/6/7 必须在组件 3 下发新键之后；在此之前前端读到 `undefined` 应表现为「退回科目名兜底」（守卫覆盖该态）。
4. 浏览器实测最后做，且须在变异检验全 RED 之后。
