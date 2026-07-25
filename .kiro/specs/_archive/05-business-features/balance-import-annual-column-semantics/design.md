# Design Document

## Overview

按"**年度优先 + 月度兜底（替代组）**"改造余额表导入，覆盖三个环节：识别层（区分年初/期初、识别本年累计）、分类层（年度=key、月度=recommended、不误阻断）、落库层（期初优先取年初、发生额优先取本年累计）。所有改动对"整年单期导出（年初=期初、本年累计=本期）"逐值等价、零回归，仅对"月度导出（年初≠期初）"产生修正。

复盘（核对真实代码，见 requirements §Introduction）确认涉及 **后端改动点 A/B/B2/C/D/E/F**（必做）+ **G/H**（可选：前端向导标签 + legacy 字段组校验）+ **1 处前端已完成**：

| # | 组件 | 现状 | 目标 |
|---|------|------|------|
| A | `identifier.py::_MERGED_HEADER_MAPPING`（双行合并表头·点号，`_match_header` 最先命中，v2 截图路径） | 年初余额→opening_*、本年累计/累计发生额→debit/credit_amount（合并） | 年初余额→year_opening_*、本年累计→year_debit/credit（区分） |
| B | `data/ledger_recognition_rules.json::column_aliases`（顶层，识别层 header→field 匹配权威真源） | 年初借/贷→opening_*、年初余额→opening_balance；本年累计无别名 | 拆出 year_opening_*/year_debit/year_credit；期初/本期保留 |
| B2 | `identifier.py::_RAW_HEADER_ALIASES`（Python 内置兜底，JSON 缺失/加载失败时用） | 同样合并：opening_balance:[年初余额,期初余额]、opening_debit:[年初借方,期初借方] | 与 B 同步拆年度/月度；保证 fallback 路径口径一致（测试/JSON失败鲁棒性） |
| C | `detection_types.py::KEY_COLUMNS/RECOMMENDED_COLUMNS["balance"]` | opening_balance/debit/credit 为 key | 年初/本年累计/期末为 key；期初/本期为 recommended |
| D | `identifier.py::_BUILTIN_ALTERNATIVES` + `_alt_to_key` 提升逻辑 | opening_balance→(opening_debit+opening_credit) 组合提升；无年度替代 | 加年度→月度单字段替代（仅识别打分）；`_alt_to_key` 仅对组合型（含 `+`）提升 |
| E | `converter.py::convert_balance_rows`（v2 生效，第353-361/425行）+ `smart_import_engine.py::convert_balance_rows`（legacy，第1038-1047/1080行；**两处逻辑完全相同、均有 bug**） | 期初优先 opening、发生额只取本期、丢弃本年累计 | 期初优先 year_opening、发生额优先 year_debit/credit、月度兜底 |
| F | `submit_gate.py::CRITICAL_COLUMNS["balance"]` | 仅认 opening_balance/closing_balance/(debit+credit) | 补年度/分列替代组，年度分列表不被硬拦 |
| G | 前端 `AccountImportStep.vue::_KEY_FIELDS_BY_TYPE`/`_IMPORTANT_FIELDS_BY_TYPE`/`hasDebit` 检查（第二个导入 UI：项目向导"数据导入"） | year_opening_* 标 key 但**不含 year_debit/year_credit**；opening_*/debit_amount 标 key；发生额校验只认 debit_amount | 与新语义对齐：year_debit/year_credit 计入 key 与发生额校验；opening_*/debit_amount 降为 important（外观/提示一致，不改其硬性 required=account_code） |
| H | （可选，legacy 向导后端）`smart_import_engine._RECOMMENDED_FIELD_GROUPS["balance"]` debit/credit 组 + `has_debit`/`has_credit` 校验 | debit_amount 组仅 `{"debit_amount"}`、has_debit 仅认 debit_amount | 补 year_debit/year_credit，年度-only 文件不误报"缺发生额"警告（opening 组已含 year_opening_*） |
| — | 前端 `ColumnMappingEditor.vue::availableStandardFields` | **已补** year_*/company_code（本轮前置修复，保留） | 无需再改（tier 来自后端） |

**已核对确认不改的对齐参照**：
- `smart_import_engine.py::_MERGED_HEADER_MAP`（legacy 合并表头映射，`_` 下划线分隔）**已正确区分** `year_opening_debit`/`year_debit`——**legacy 表头映射无需改动**，legacy 路径只需改 converter 取数（E）。
- `smart_import_engine.py::FIELD_LABELS` **已含** year 字段中文标签（`year_opening_debit:"年初借方"`/`year_debit:"本年累计借方"`）——前端映射下拉能显示，无需改。
- JSON `table_signatures.{type}.{key_columns,recommended_columns}.*.aliases` 是第三处别名，但**不被 header 匹配读取**（识别层只读顶层 `column_aliases`；`table_signatures.*` 仅 `.alternatives`+`.content_validator` 被读）——**不修改**（避免"改了没用"）。新年度 key 列（year_opening_debit 等）在 JSON `table_signatures.balance.key_columns` **无条目**，故其 `alternatives` 由 `_BUILTIN_ALTERNATIVES` 兜底提供（见 §D）；现有 closing_balance 的 alternative 仍从 JSON 读取（保留）。

**范围边界**：
- 本 spec 仅改 `table_type == "balance"`。**`aux_balance`（辅助余额表）不在范围**——其 KEY_COLUMNS 保持现状（opening_balance/closing_balance/debit/credit）；若辅助余额表同有年初/本年累计维度问题，另立 spec。
- `AccountImportStep.vue`（组件 G）的后端走 `smart_import_engine`，其**落库正确性已由 E 覆盖**（legacy converter 同步改）；G 仅是前端分类标签/提示的一致性对齐，且其硬性 required 只有 account_code（不会误阻断），故列为**可选对齐**（不做也不产生数据错误，只是标签不一致）。

## Architecture

数据流与改动点定位：

```
上传余额表
  │
  ▼
detector（切表头 / 双行合并 → 点号 "年初余额.借方金额"）
  │
  ▼
identifier._match_header
  ├─(A) _match_merged_header（点号）  ← 修：年初/本年累计 区分
  └─(B) JSON column_aliases（单行）   ← 修：拆年度别名
  │  产出每列 standard_field
  ▼
identifier.classify_column_tier + _alt_to_key  ← (C)(D) 修：年度=key/月度=recommended，单字段替代不提升
  │  产出 column_tier（前端「关键列/次关键列」分区）
  ▼
前端映射编辑器（用户确认/调整） → ConfirmedMappingDTO
  │
  ▼
SubmitGate.validate（CRITICAL_COLUMNS 硬校验）  ← (F) 修：补年度/分列替代组
  │
  ▼
prepare_rows_with_raw_extra（按 column_mapping 落 standard_field 键）
  │
  ▼
converter.convert_balance_rows  ← (E) 修：期初优先年初、发生额优先本年累计
  │  产出 tb_balance 行（opening_balance/debit_amount/credit_amount/closing_balance）
  ▼
trial_balance（下游底稿/报表取数）
```

**核心不变量**：`trial_balance` 表结构不变（无年度/月度分列），年度数据经"年度优先"落进既有的 `opening_balance` / `debit_amount` / `credit_amount` 列；月度数据仅在无年度列时兜底落库。

## Components and Interfaces

### A. identifier.py `_MERGED_HEADER_MAPPING`（点号合并表头）

区分年度组，对齐 `smart_import_engine._MERGED_HEADER_MAP`：

```python
_MERGED_HEADER_MAPPING = {
    "年初余额": {"借方金额": "year_opening_debit", "贷方金额": "year_opening_credit",
                "借方": "year_opening_debit", "贷方": "year_opening_credit",
                "_default": "opening_balance"},   # 年度净额单列无独立字段，落 opening_balance（R1.8 边界）
    "期初余额": {"借方金额": "opening_debit", ...},          # 不变
    "期末余额": {"借方金额": "closing_debit", ...},          # 不变
    "本期发生额": {"借方金额": "debit_amount", ...},         # 不变
    "本年累计": {"借方金额": "year_debit", "贷方金额": "year_credit",
                "借方": "year_debit", "贷方": "year_credit", "_default": "year_debit"},   # 修
    "累计发生额": {同 本年累计 → year_debit/year_credit},     # 修
}
```

### B. JSON `column_aliases`

拆分（新增 year 字段、期初/本期收窄）：

```jsonc
"year_opening_debit": ["年初借方", "年初借方余额"],
"year_opening_credit": ["年初贷方", "年初贷方余额"],
"year_debit": ["本年累计借方", "累计借方", "本年累计"],
"year_credit": ["本年累计贷方", "累计贷方"],
"opening_debit": ["期初借方", "期初借方余额"],       // 移除「年初借方」(→ year_opening_debit)
"opening_credit": ["期初贷方", "期初贷方余额"],       // 移除「年初贷方」(→ year_opening_credit)
"opening_balance": ["期初余额", "年初余额"],          // 保留「年初余额」净额（R1.5：无独立年度净额字段，年度净额并入 opening_balance）；仅「年初借方/贷方」借贷分列 → year_opening_*
"debit_amount": ["本期借方", "借方发生额", "借方本期", "本期借方发生额", "借方金额", "借方", "Debit", "DR"],
"credit_amount": ["本期贷方", "贷方发生额", ...],
```

`table_signatures.balance.key_columns.*.aliases` 是**惰性数据**（不被 header 匹配读取，见组件表参照说明），**不改**；列 tier 以 Python `KEY_COLUMNS` 为准。

### B2. identifier.py `_RAW_HEADER_ALIASES`（Python 内置兜底）

与 §B 同步拆分（JSON 缺失/加载失败时的一致性保障）：

```python
_RAW_HEADER_ALIASES = {
    ...
    "opening_balance": ["期初余额"],                    # 移除「年初余额」
    "opening_debit": ["期初借方", "期初借方余额"],       # 移除「年初借方」
    "opening_credit": ["期初贷方", "期初贷方余额"],
    "year_opening_debit": ["年初借方", "年初借方余额"],  # 新增
    "year_opening_credit": ["年初贷方", "年初贷方余额"],
    "year_debit": ["本年累计借方", "累计借方", "本年累计"],  # 新增
    "year_credit": ["本年累计贷方", "累计贷方"],
    "debit_amount": ["借方金额", "本期借方", "借方发生额", ...],  # 保留本期语义
    ...
}
```

`_build_header_alias_table` 的 `source = _RULES.get("column_aliases", _RAW_HEADER_ALIASES)` 不改——只改兜底 dict 内容，使 JSON/fallback 两路径口径一致。

### C. detection_types.py 分层

```python
KEY_COLUMNS["balance"] = {
    "account_code",
    "year_opening_debit", "year_opening_credit",   # 年初
    "year_debit", "year_credit",                   # 本年累计
    "closing_balance",                             # 期末（净额；分列经 D 的组合替代提升）
}
RECOMMENDED_COLUMNS["balance"] = {
    "account_name", "level", "company_code", "currency_code", "accounting_period",
    "opening_balance", "opening_debit", "opening_credit",   # 期初（月度）
    "debit_amount", "credit_amount",                        # 本期（月度）
    "closing_debit", "closing_credit",                      # 期末分列（经组合替代提升为 key）
    "aux_dimensions",
}
```

### D. identifier.py 替代组 + 提升守卫

```python
_BUILTIN_ALTERNATIVES = {
    "closing_balance": ["closing_debit+closing_credit"],   # 组合型 → 提升 key（重构净额需两半）
    "year_opening_debit": ["opening_debit"],               # 单字段（月度兜底）→ 仅识别打分，不提升
    "year_opening_credit": ["opening_credit"],
    "year_debit": ["debit_amount"],
    "year_credit": ["credit_amount"],
}

# _alt_to_key 构建处加守卫：
for key_col in KEY_COLUMNS.get(winning_type, set()):
    for alt_group in _get_alternatives(winning_type, key_col):
        if "+" not in alt_group:      # 单字段替代不提升为 key（避免月度列被迫必填）
            continue
        for alt_field in alt_group.split("+"):
            _alt_to_key.add(alt_field)
```

`_score_table_type` 计分逻辑不变（其对单字段/组合替代都按 `alt_group.split("+") ⊆ matched` 判定，天然支持月度兜底满足年度 key 覆盖）。

**🔴 aux_balance 消歧（复盘补强）**：年度语义改造后，`year_opening_*` 替代含 `opening_balance` 使 balance 对"含 aux 维度的净额表"也达 6/6，且月度列进入 balance RECOMMENDED 抬高其 bonus → 会盖过 aux_balance（即使 sheet 名为「辅助余额表」）。修复：`_NEGATIVE_SIGNALS["balance"]` 追加 `aux_type` / `aux_code`——含辅助维度列的表命中 balance 负向信号 `key_score *= 0.5`，回归判定为 aux_balance；不影响无 aux 列的普通余额表。

**`_get_alternatives` 取数路径（已核对）**：先读 JSON `table_signatures.balance.key_columns.{col}.alternatives`，无则回退 `_BUILTIN_ALTERNATIVES`。新年度 key 列（year_opening_debit/year_opening_credit/year_debit/year_credit）在 JSON `key_columns` **无条目** → 走 `_BUILTIN_ALTERNATIVES` 兜底（故上面加在 `_BUILTIN` 即生效）；`closing_balance`（仍 key）的 alternative 仍从 JSON 读取。**opening_balance 移出 KEY 后**，`_alt_to_key` 循环不再处理它 → opening_debit/opening_credit 不再经 opening_balance 被提升为 key（正确，期初保持 recommended）。

**content_validator 说明（已知边界）**：新年度 key 列在 JSON `table_signatures.balance.key_columns` 无条目 → 无 `content_validator` → 内容层数值校验对这些列**跳过**（仅用 header 置信度）。可接受（不产生错误，只是少一层数值加权）；如需数值校验可选把 year 列补进 JSON `key_columns`（含 `content_validator:"numeric"`+`alternatives`），非本 spec 必需。

### E. converter.py `convert_balance_rows`（+ legacy 同步）

**🔴 取数优先级必须用显式 `is None`，禁用 `or`**（`Decimal(0)` 是合法余额/发生额但 falsy，`or` 会把 0 误判为缺失跳到兜底）：

```python
def _first_decimal(*vals):
    """按顺序返回首个非 None 的 Decimal（Decimal(0) 视为有值），全缺返回 None。"""
    for v in vals:
        d = safe_decimal(v)
        if d is not None:
            return d
    return None

# ── 期初：年度优先（年初 → 期初分列 → 期初净额）──
od = _first_decimal(row.get("year_opening_debit"), row.get("opening_debit"))
oc = _first_decimal(row.get("year_opening_credit"), row.get("opening_credit"))
opening_bal = safe_decimal(row.get("opening_balance"))
# （替换原"od/oc/opening_bal 全空才用 year_opening"的兜底顺序 → 改为年初优先）

# ── 发生额：本年累计优先（本年累计 → 本期）──
debit_amount = _first_decimal(row.get("year_debit"), row.get("debit_amount"))
credit_amount = _first_decimal(row.get("year_credit"), row.get("credit_amount"))

# ── 期末：不变 ──
```

- **年度优先自动惠及 aux→汇总聚合**：`_aggregate_aux_to_summary` 对无汇总行的科目按 `base_row` 求和，而 `base_row` 存的是上面已按年度优先解析后的 `od`/`debit_amount`，故该路径无需单独改。
- **year_* 键穿透已自证**：现有 v2 converter 第 360 行、legacy 第 1045 行本就 `row.get("year_opening_debit")` 作兜底，证明 year_opening_* 标准字段能穿过映射管线进入 converter row dict；本改动只调整取数顺序，不涉及键是否到达（Wave1 加断言核实 year_debit 同样到达）。
- **下游方向推断保留**：`od`/`oc` 用 `_first_decimal` 解析后仍为 Decimal，喂给现有 split_columns 分支（`if od is not None or oc is not None:` → `opening_balance=(od or 0)-(oc or 0)` + `opening_source_direction` 由 od/oc 派生）；年初/期初都无借贷分列而仅有净额时，od=oc=None → 落 `elif opening_bal is not None:` 净额+方向分支——**方向推断逻辑不动**，只是 od/oc 的来源从"期初优先"变"年初优先"。
- **legacy 只改 converter 取数**：legacy `smart_import_engine.convert_balance_rows` 第 1038-1047/1080 行应用同一 `_first_decimal` 取数顺序（与 v2 双路径口径一致）；legacy 的表头映射 `_MERGED_HEADER_MAP` 已正确区分年度/月度（见组件表），**不改**。

### F. submit_gate.py `CRITICAL_COLUMNS["balance"]`

```python
"balance": [
    {"account_code", "opening_balance"},
    {"account_code", "closing_balance"},
    {"account_code", "debit_amount", "credit_amount"},
    # 新增年度/分列替代组：
    {"account_code", "year_opening_debit", "year_opening_credit"},
    {"account_code", "closing_debit", "closing_credit"},
    {"account_code", "year_debit", "year_credit"},
],
```

### G. 前端 AccountImportStep.vue（可选对齐，第二个导入 UI）

仅调整前端分类常量使标签/提示与新语义一致（不改硬性 required=account_code，不影响落库）：

```ts
// _KEY_FIELDS_BY_TYPE["balance"]：year_debit/year_credit 计入 key；opening_*/debit_amount/credit_amount 移到 important
balance: new Set(['account_code','account_name',
  'year_opening_debit','year_opening_credit','year_debit','year_credit',
  'closing_balance','closing_debit','closing_credit','aux_dimensions']),
// _IMPORTANT_FIELDS_BY_TYPE["balance"] 增：opening_balance/opening_debit/opening_credit/debit_amount/credit_amount
// hasDebit 发生额校验：由 fields.has('debit_amount') 扩为 也认 year_debit（hasCredit 同理认 year_credit）
```

### H. 后端 smart_import_engine 字段组校验（可选，legacy 向导后端）

legacy 引擎的完整性校验也应认年度列，避免年度-only 文件在向导路径误报"缺发生额"（warning 级，不阻断落库）：

```python
# _RECOMMENDED_FIELD_GROUPS["balance"]：opening 组已含 year_opening_*；对齐发生额组
("debit_amount", {"debit_amount", "year_debit"}),      # 现为 {"debit_amount"}
("credit_amount", {"credit_amount", "year_credit"}),   # 现为 {"credit_amount"}
# 校验函数 has_debit/has_credit（约第 967 行）同理：
# has_debit = any(f in fields for f in ("debit_amount", "year_debit"))
# has_credit = any(f in fields for f in ("credit_amount", "year_credit"))
```

## Data Models

标准字段↔中文↔维度（与后端 `FIELD_LABELS` 一致）：

| 标准字段 | 中文 | 维度 | 分层 |
|---|---|---|---|
| account_code | 科目编码 | — | key |
| year_opening_debit / year_opening_credit | 年初借/贷 | 年度 | key |
| year_debit / year_credit | 本年累计借/贷 | 年度 | key |
| closing_balance | 期末余额（净额） | — | key |
| closing_debit / closing_credit | 期末借/贷 | — | recommended（组合替代→key） |
| opening_balance / opening_debit / opening_credit | 期初余额/借/贷 | 月度 | recommended |
| debit_amount / credit_amount | 本期借/贷 | 月度 | recommended |

`trial_balance` 落库列不变：`opening_balance` / `debit_amount` / `credit_amount` / `closing_balance`（+ unadjusted/audited 等，不涉及）。

## Correctness Properties

### Property 1: 整年导出等价性（年初=期初、本年累计=本期）
构造一行使 `year_opening_* == opening_*` 且 `year_debit/credit == debit_amount/credit_amount`，`convert_balance_rows` 结果的 opening_balance/debit_amount/credit_amount/closing_balance 与"仅保留月度列"的转换结果逐值相等。
**Validates: Requirements 5.1, 6.1**

### Property 2: 期初年度优先（年初≠期初）
一行 `year_opening_debit/credit` 与 `opening_debit/credit` 不同时，转换结果 opening_balance 由年初派生（= year_opening_debit − year_opening_credit，经符号规范化）。
**Validates: Requirements 4.1, 6.2**

### Property 3: 发生额本年累计优先（本年累计≠本期）
一行 `year_debit/credit` 与 `debit_amount/credit_amount` 不同时，转换结果发生额由本年累计派生。
**Validates: Requirements 4.2, 6.2**

### Property 4: 月度兜底
一行仅含月度列（无 year_*）时，转换结果由月度列派生，与变更前实现逐值一致。
**Validates: Requirements 4.4, 6.3**

### Property 5: 分类正确（年度 key / 月度 recommended）
同时含年度与月度列时，`classify_column_tier` 对 year_opening_*/year_debit/year_credit 返回 key，对 opening_*/debit_amount/credit_amount 返回 recommended。
**Validates: Requirements 2.1, 2.2, 2.3, 6.4**

### Property 6: 月度列不误阻断（识别+关键列）
仅含月度列的 balance（account_code + 期初 + 本期 + 期末）经替代组 `_score_table_type` 仍识别为 balance，且关键列覆盖满足（不阻断）。
**Validates: Requirements 2.4, 6.5**

### Property 7: 提升守卫（单字段替代不提升、组合型提升）
`_alt_to_key` 对单字段替代（如 year_opening_debit←opening_debit）不把 opening_debit 提升为 key；对组合型（closing_balance←closing_debit+closing_credit）把两分列提升为 key。同时含年初与期初列时，opening_debit 的 tier 保持 recommended。
**Validates: Requirements 3.2, 3.3, 3.4**

### Property 8: 点号合并表头区分年度
`_match_merged_header("年初余额.借方金额") == year_opening_debit`、`_match_merged_header("本年累计.借方金额") == year_debit`、`期初余额.借方金额 == opening_debit`、`本期发生额.借方金额 == debit_amount`、`期末余额.借方金额 == closing_debit`。
**Validates: Requirements 1.7**

### Property 9: 单行别名区分年度
经 `_match_header`（JSON 别名）：年初借方→year_opening_debit、期初借方→opening_debit、本年累计借方→year_debit、本期借方/借方发生额→debit_amount。
**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

### Property 10: SubmitGate 接受年度/分列文件
`SubmitGate.validate` 对 {account_code, year_opening_debit, year_opening_credit} / {account_code, closing_debit, closing_credit} / {account_code, year_debit, year_credit} 任一组合的映射通过（不抛 missing_critical_columns）；同时保持原三组合仍通过。
**Validates: Requirements 2.5, 5.2**

### Property 11: 期末逻辑不变
期末取数（closing_debit/credit 优先，closing_balance 次之）与变更前逐值一致。
**Validates: Requirements 4.3**

### Property 12: 零回归——现有测试
`backend/tests/ledger_import/` 全套通过（按新语义更新的断言不得放宽/跳过绕过真实回归）。
**Validates: Requirements 5.3, 5.4**

### Property 14: aux_balance 不被误判为 balance（复盘补强）
含 `aux_type`/`aux_code` 维度列的余额表（即使含 opening_balance/debit_amount/credit_amount 净额与发生额列、且 sheet 名为「辅助余额表」）仍被识别为 `aux_balance`，不因年度语义改造（balance 替代组 + RECOMMENDED bonus）被误判为 `balance`。
**Validates: Requirements 5.4（不改辅助表识别）**

### Property 15: 年初余额净额单列显式映射（R1.5 稳健性）
`_match_header("年初余额")`（单行净额列，无点号、无借贷分列）经**精确别名**映射到 `opening_balance`（confidence=exact，不再依赖 Levenshtein 年↔期 的偶然邻近）。
**Validates: Requirements 1.5**

### Property 13: 年初净额单列边界（_default → opening_balance）
`_match_merged_header` 对点号形式且 group=年初余额、sub 非借贷子列（如 `年初余额.金额`，命中 `_default`）返回 `opening_balance`（非 year_*，因无独立年度净额字段）；有年度借贷分列时（Property 8）仍正确区分为 year_opening_*。注：`_match_merged_header` 仅处理含 `.` 的合并表头，裸 `年初余额`（无 `.`）返回 None（不适用本 property）。
**Validates: Requirements 1.8**

### Property 14: _RAW_HEADER_ALIASES 兜底路径也区分年度
`reload_rules` 传入不含 `column_aliases` 的最小 rules（触发 `_build_header_alias_table` 回退 `_RAW_HEADER_ALIASES`）后，`_match_header("年初借方")==year_opening_debit`、`_match_header("期初借方")==opening_debit`、`_match_header("本年累计借方")==year_debit`——fallback 与 JSON 路径口径一致。
**Validates: Requirements 1.9, 6.6**

## Error Handling

- **Decimal(0) 与 None 区分**：取数优先级用显式 `is None` 判断，不用 `or`（0 是合法余额/发生额，不得被当缺失跳到兜底）。
- **年初净额单列**（`年初余额` `_default`）：无 `year_opening_balance` 字段，落 `opening_balance`（已知边界，R1.8）；有年度借贷分列时转换器年度优先仍正确。
- **别名收窄的兼容**：移除「年初借方」→opening_debit 后，历史已落库数据不受影响（本改动只影响新导入的识别；trial_balance 已存数值不动）。
- **JSON 热加载**：`column_aliases` 改动经 `reload_rules()`/进程重启生效（识别层 `_RULES` 模块级缓存）；测试直接调 `reload_rules`/`_rebuild_aliases` 或断言 `_match_header`。
- **key 列自动映射置信度门槛（已核对 `ColumnMatch.passes_threshold`）**：key 列 `confidence>=80` 才自动映射，recommended 只需 `>=50`。年度列升为 key 后其自动映射门槛升到 80——精确别名匹配得 `exact_match_confidence=95`（过），但纯 Levenshtein/子串模糊匹配得 `fuzzy_match_confidence=70`（<80，不自动应用，需人工在映射编辑器确认）。年度列表头应能精确命中别名（95），故正常无碍；异形表头需人工确认属预期（key 列本就该人工把关）。此为既有 key 列行为，非新增机制。
- **`_RAW_HEADER_ALIASES` fallback**：仅 JSON 缺失/加载失败时命中；改动内容后经 `reload_rules(最小path)`/重启生效，测试可传只含极简 rules（无 column_aliases）的临时 JSON 验证 fallback 路径。

## Testing Strategy

- **单元（映射层）**：`_match_merged_header`（点号，Property 8）、`_match_header`（JSON 别名，Property 9）。
- **单元（分类层）**：`classify_column_tier` + `identify` 后各列 tier（Property 5、7）；`_score_table_type` 月度兜底覆盖（Property 6）。
- **单元（SubmitGate）**：新增/保留 critical 组合（Property 10）。
- **PBT（hypothesis，`max_examples=5`）**：converter 等价性/年度优先/月度兜底（Property 1-4、11）——生成年初/期初/本年累计/本期/期末各借贷值，断言取数优先级与等价性。
- **回归**：`python -m pytest backend/tests/ledger_import/`（Property 12）；对因语义更新需改断言的用例（如显式 mapping 的 test_raw_extra 若涉及）逐一核实非放宽。
- **验证命令**：`python -m py_compile`（改动 .py）+ 上述 pytest。

## Notes

- 前端 `availableStandardFields`（year_*/company_code）本轮已补，无需再动。
- 不改 `trial_balance` 表结构、序时账识别/转换、下游取数契约（R5.4）。
- Legacy `smart_import_engine.convert_balance_rows` 与 v2 `converter.convert_balance_rows` 同步改，避免 feature flag 两路径口径分叉（R4.5）。
