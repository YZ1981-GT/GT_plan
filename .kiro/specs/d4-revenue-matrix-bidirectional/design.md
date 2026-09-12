# Design Document

## Overview

D4-2 是 Phase 5 的**第六个 canary、第五种行形态**：位置数组（positional array）。设计目标是「只补缺口，不新建路径」——复用既有八步范式与共享 infra，把新增面收敛到两处：①契约字段的 `json_pointer` 支持数组下标；②净化脚本要能区分外链公式与内部公式。

## Architecture

```
useD4RevenueDetail.ts (D4-2-rows: {product, months[12], ...})
        │  store JSON（数组下标 = 列位）
        ▼
phase5_d4_revenue_detail.py           ← 新增（第 6 个 provider 模块）
  MANAGED_FIELD_SPECS: A=product, B..M=months/0..months/11, N=formula, O=..., 备注
  build_store_projection / merge_projection_into_store_rows
        │
        ▼
共享 infra（不改）：ExcelInstrumentationSpec → DefinitionPublisher → build_excel_adapter
        │
        ├── Task 76 provisioner  → approved definition bundle
        ├── first_publication    → published representation（**非空** projection）
        └── oo_to_html            → 加 d4.revenue_detail 分支（数组形态写回）
```

### 现状事实（只读实测，作为设计前提）

| 事实 | 值 | 来源 |
|---|---|---|
| store 键 | `D4-2-rows` | `useD4RevenueDetail.ts` `STORAGE_KEY` |
| 行形态 | `product` + `months[12]` + 4 个标量 | 同上 `DetailRow` |
| 受管 sheet | `主营业务收入明细表D4-2`（A1:V32） | openpyxl 实测 |
| 模板 | `D/D4 收入底稿.xlsx`：46 sheet / 17 外链 / **270 个 `[n]` 公式格** | zip 级实测 |
| 真载荷 | 2 行 / 1739 B，落 wp_code=D4 | 真库实测 |
| 对照 | D3/D5/D6 各 0 个 `[n]` 公式格；D7 仅 6 处且在非受管 sheet | §11 |

## Components and Interfaces

### 1. `phase5_d4_revenue_detail.py`（新）

沿用 5 个既有 provider 的 9 段结构（冻结身份 / 权威模板哨兵 / 选型零回退守卫 / instrumentation payload / per-entry 契约 / store 拆分合并 / 发布 / adapter 注册 attach / 别名）。唯一新增语义：

```python
# months 展开成 12 条 spec，json_path 用数组下标（非 dict 键）
MONTH_COLUMNS = ("B","C","D","E","F","G","H","I","J","K","L","M")
def _month_field_specs():
    return tuple(
        (f"month_{i+1:02d}", col, "editable", "amount", f"months/{i}", f"{i+1}月")
        for i, col in enumerate(MONTH_COLUMNS)
    )
```

`_resolve_json_path` / `_set_json_path` 必须**按段判类型**：段为纯数字且游标是 list → 按 index 取/写；否则按 dict 键。既有 5 个 provider 的两个函数只处理 dict，故本模块的版本是**新实现**而非复制。

### 2. 净化脚本 `sanitize_d4_template_external_links.py`（新）

与 D3/D5/D6/D7 四份的差别是**公式分类**，不是删除机制：

```
分类判据（逐 <f> 文本）：
  含 [n]  → 外链公式 → 去 <f> 保 <v>
  不含 [n] → 内部公式 → 逐字节保留（含 =SUM(B12:M12)）
```

判据落点：净化前后对受管 sheet 做逐格快照 diff（必须 0），并**单独断言 N 列公式文本不变**。

### 3. `oo_to_html.py` 分支

```python
elif adapter_id == "d4.revenue_detail":
    from app.services.workpaper_sync import phase5_d4_revenue_detail as bridge
    store_item_id = bridge.STORE_ITEM_ID
    merge_kind = "rows"
    merge_rows_fn = bridge.merge_projection_into_store_rows
```

`merge_projection_into_store_rows` 内部用**数组感知**的 `_set_json_path`，保证写回后 `months` 仍是 list。

## Data Models

契约字段共 **18 条**：`product`(A) + `months/0..11`(B~M, 12 条) + `period_total`(N, formula) + `audit_adjustment`(O) + `prior_unadjusted` + `prior_adjustment` + `remark`（后三条按 D4-2 实际列位在 Task 1.1 逐格核定，本设计不预写死）。

## Correctness Properties

### Property 1

对任意长度 12 的数值数组 `months`，`_set_json_path(row, "months/{i}", v)` 后 `row["months"]` 仍是 `list` 且 `len == 12`，且仅第 `i` 位被改写。

**Validates: Requirements 1.2**

### Property 2

对任意 `i` ∉ [0,11]，`_resolve_json_path(row, f"months/{i}")` 与 `_set_json_path` 必须抛错（fail closed），不得返回 None 或静默追加。

**Validates: Requirements 1.4**

### Property 3

净化前后，受管 sheet 内**不含 `[n]`** 的 `<f>` 文本集合逐元素相等（内部公式零损伤）。

**Validates: Requirements 2.2**

### Property 4

净化后模板过真 OOXML 门，且 `.preclean.bak` 不过门（门负例非空）。

**Validates: Requirements 2.4**

### Property 5

first_publication 现算 projection 的 `row_keys[rows_table]` 长度等于 store 真实行数；每行贡献的 field 数 = 18。

**Validates: Requirements 3.2**

### Property 6

OO 回写经 `merge_projection_into_store_rows` 后，store 中 `months` 的 JSON 序列化形态是数组 `[...]` 而非对象 `{"0":...}`。

**Validates: Requirements 4.3**

## Testing Strategy

1. **先验证形态（阻塞门）**：`backend/tests/workpaper_sync/test_d4_positional_array_roundtrip.py` —— 最小 fixture 上跑 materialize→extract，覆盖 Property 1/2/6。此测试不通过则后续任务不启动（Requirement 1.5）。
2. **净化变异检验**：`backend/scripts/diagnose/mutate_d4_sanitize_guards.py` —— 四态（RED/GREEN/ANCHOR-MISS/WRONG-TEST）逐条判定，GREEN 即守卫有缺陷。
3. **发布链**：Task 76 `--check` → `--apply`；`fix_projection_first_publication --check`（10 stage 全过）→ `--apply`。
4. **§9.6 真栈 e2e**：`e2e/g5-1-d4-unified-path.spec.ts`，OO 写 A 列 `product`（文本列）。
5. **DB 三谓词**：venv 只读查 applied / checklist marker / `source=onlyoffice` + op 逐字一致。

## Open Decisions

- **DEC-D4-1**：契约里 12 个月是「12 条独立 field」还是「1 条 array field」。本设计选**12 条独立 field**（每列一个 stable key），理由：既有 merge/conflict/roundtrip 全部按 stable field 粒度工作，array 整体作为一个 field 会退回「把整 JSON 当一个字段比较」，那是 D2 AC 6.9/6.12 明令禁止的。
- **DEC-D4-2**：若 Task 1 证明数组下标路径在共享 extract 侧不可行（而非仅 provider 侧），则升级为「先给 `contracts.py` 增加 array 段支持」的前置任务，并同步通知其余 canary 的 owner（形态扩展影响共享件）。
