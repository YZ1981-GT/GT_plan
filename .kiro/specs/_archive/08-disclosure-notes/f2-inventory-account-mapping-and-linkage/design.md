# Design: F2 存货科目映射与底稿间联动

## Overview

核心决策：**F2 存货分类的判据从「科目编码」换成「科目名称」**，理由是编码语义在本平台内
不唯一（两版标准科目表并存，`1405`/`1406`/`1407`/`1408`/`1411`/`1416`/`1461` 全部冲突）。

这不是新范式 —— 平台已有两处同款先例：

- `_n4_taxes_and_surcharges._classify_n4_subaccount(name)`：`6403` 子科目编码语义客户间冲突
  （`6403.02` 既是「城市维护建设税」也是「车船税」）→ 按名称归类；
- `_f1_prepayment.classify_f1_nature(name)`：`1123` 叶子名带业务语义 → 按名称归入五个性质桶。

F2 只是把同一手法用在**一级科目**上。

其余三项（叶子聚合委托共享件 / 项目科目表下发前端 / 公式预设重写）都是把已验证的
平台范式搬到 F2，不引入新机制。

## Architecture

```
account_chart(project_id, 14xx)          ← 项目实际科目表（含两个标准变体 + 客户自定义）
        │
        ├─→ classify_f2_category(name)   ← 新增纯函数（名称归类，顺序即优先级）
        │        │
        │        ├─→ project_context.inventory_accounts   → 前端 AJE 科目下拉 / 溯源
        │        └─→ 分类归集键
        ▼
tb_balance(14xx)  ──select_leaves()──→ 叶子行 ──按 classify 归集──→ adjudication_prefill
        │            （共享件，替代本地 _row_depth + max(by_depth)）
        ▼
trial_balance ← report_config BS-010 = SUM_TB('1401~1499','期末余额')   → F2-1 TB 核对标量
```

底稿间联动（源模板逐格实证，`F2存货.xlsx` 附注披露信息（上市公司））：

```
F2-3 原材料明细 ┐
F2-4 材料采购在途 │
F2-5 周转材料   ├─→ F2-2 明细汇总表 ─┐
…               │   （跌价计提/转回）  │
F2-13 消耗性生物 ┘                    ├─→ 披露 (2) 跌价准备变动表 (K/L/N/O/P 列)
                                      │   披露 (2)续 依据/原因 (I/J 列)
F2-1 审定表 ────────────────────────┴─→ 披露 (1) 分类表（E/B 列 期末/期初）
（E36..E48 原值 / E79..E91 跌价）          披露 (2) 期初余额列
F2-10 开发产品 ─────────────────────→ 披露 (6) 开发产品
F2-11 开发成本 ─────────────────────→ 披露 (5) 开发成本
```

## Components and Interfaces

### 1. `backend/app/services/f2_extraction/category_rules.py`（新建）

零依赖纯函数模块（后端唯一真源，`_f2_inventory_main` 与 `f2_extraction.extract` 都委托它）：

```python
#: 归类规则。顺序即优先级 —— 长词/限定词必须先判。
F2_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # 备抵最先（「存货跌价准备」含「存货」，写在后面会被泛化规则吃掉）
    ("impairment-provision", ("跌价准备", "减值准备")),
    ("price-difference",     ("进销差价", "商品进销差价")),
    ("contract-performance", ("合同履约成本", "合同取得成本")),
    ("consumable-bio",       ("消耗性生物资产", "生物资产")),
    ("dev-products",         ("开发产品",)),
    ("dev-costs",            ("开发成本",)),
    ("goods-in-transit",     ("发出商品",)),
    ("semi-finished",        ("自制半成品", "半成品", "在产品", "生产成本")),
    ("outsourced-processing",("委托加工",)),
    ("revolving-materials",  ("周转材料", "低值易耗品", "包装物", "损余物资")),
    ("material-in-transit",  ("材料采购", "在途物资")),
    ("raw-materials",        ("原材料", "材料成本差异")),
    ("finished-goods",       ("库存商品", "产成品", "贵金属", "抵债资产")),
)
F2_CATEGORY_DEFAULT = "other"

def classify_f2_category(account_name: str) -> str: ...
def is_f2_impairment_category(row_key: str) -> bool: ...
```

关键顺序论证（每条都对应一次实测冲突）：

- `跌价准备` 先于一切 —— 客户子科目名 `存货跌价准备_库存商品` 若先命中「库存商品」会
  把备抵算进原值（金额 −4,149,232.42 会反向抵减库存商品）。
- `合同履约成本` / `合同取得成本` 先于 `成本` 类泛词。
- `自制半成品` 组含 `生产成本` —— 变体 A 项目实测 `1405.03 修复件` 之类客户子科目
  仍按父级名归类（父级 `自制半成品`），故归集以**父级名 + 叶子名**双取（见下）。
- `材料采购`/`在途物资` 先于 `原材料` —— 「材料采购」含「材料」。
- `库存商品` 组兜底放最后。

叶子名可能是纯客户命名（如 `1405.03 修复件`、`1406.03 库存商品_外购商品（零售）`），
故归类入口为：

```python
def classify_f2_leaf(leaf_name: str, parent_name: str | None) -> str:
    """叶子优先按自身名归类；未命中（返回 other）时回退父级一级科目名。"""
```

### 2. `backend/app/routers/wp_render_strategies/_f2_inventory_main.py`

- `F2_CATEGORIES` 保留（rowKey/label 顺序 = 审定表行序），`account` 字段加注释
  「**兜底/展示用；运行时取数按名称归类，勿据此写死**」。
- 删除 `_row_depth`，`_build_adjudication_prefill` 改：
  1. 查 `account_chart` 得 `{code: name}`（fail-open 空 dict）；
  2. 查 `tb_balance` 14xx → `select_leaves` 取叶子；
  3. 逐叶子 `classify_f2_leaf(leaf.account_name, chart.get(top_code))` 归集；
  4. `impairment-provision` 桶取绝对值；
  5. 全零桶跳过。
- 新增 `project_context.inventory_accounts`（R3）与
  `project_context.tb_source_codes`（`BS-010` 解析结果 + 归类明细，供溯源面板）。

### 3. `backend/app/services/f2_extraction/extract.py`

`build_default_bindings` 的表达式改为**名称口径描述**而非 `TB('{account}',…)`：
由于 `TB()` 只吃编码，这里改为在 binding 里带 `row_key` 并由 `extract_f2_category_values`
按 `classify_f2_leaf` 归集；`expression` 保留为**展示字符串**
`按名称归类('库存商品','期初余额')`，并在 `formulas` 里原样下发给溯源面板。

> 灰度开关 `F2_FOUR_TABLE_EXTRACTION_ENABLED` 的默认值不动（本 spec 不改灰度策略），
> 两条路径都走同一个归类函数，故开/关行为一致。

### 4. `audit-platform/frontend/src/components/workpaper/composables/f2AccountModel.ts`

- `F2_ROW_KEY_ACCOUNT` / `F2_ACCOUNT_TO_ROW_KEY` / `F2_INVENTORY_ACCOUNTS`
  加显著注释「**兜底清单** —— 存货科目编码语义项目间冲突，运行时优先用
  `project_context.inventory_accounts`」。
- 新增 `resolveF2InventoryAccounts(fromRender, fallback)` 与
  `resolveF2AccountToRowKey(fromRender, fallback)` 两个纯函数，消费点改用它们。

### 5. `backend/data/prefill_formula_mapping.json`

`workpaper:F2` 现 71 条 → 重写。删除「编码=分类」类；保留/新增见 tasks Wave 4。

## Data Models

### render 输出（`project_context`）

| 键 | 变更 | 说明 |
|---|---|---|
| `inventory_accounts` | **新** | `[{code, name, row_key}]`，取自本项目 `account_chart` 14xx |
| `tb_source_codes` | **新** | `{row_code: 'BS-010', codes: [...], classified: {row_key: [codes]}}` |
| `tb_values` | 既有 | `{rowKey: {opening, closing}}`（前端 `useF2Adjudication.seedFromTbValues` 已在读） |
| `adjudication_prefill` | 既有（灰度） | `{rowKey: {opening, increase, decrease, closing, formulas, source_codes}}` |

`tb_values` 的键名与结构**不变**（前端已消费），只改「值从哪来」。

### 附注载荷不变

`f2NoteSectionMap` / `F2_LISTED_SUBTABLE` / `F2_SOE_SUBTABLE` 与
`note_template_{listed,soe}.json` 的 §五、9 / §八、10 一格不动。

## Correctness Properties

### Property 1: 分类不重不漏

对任意 14xx 叶子集合，各分类桶（含 `other`）的期末之和恒等于全部叶子期末之和。

**Validates: Requirements 1.3, 2.2**

### Property 2: 两个标准变体下归类一致

对变体 A 与变体 B 的 `(code, name)` 样本，`classify_f2_leaf` 的输出**只取决于名称**，
与编码无关；且「库存商品」在两版下都归 `finished-goods`。

**Validates: Requirements 1.1, 1.2, 6.1**

### Property 3: 备抵优先级

任何含「跌价准备」或「减值准备」的科目名恒归 `impairment-provision`，
即使同时含「库存商品」「原材料」等原值关键字。

**Validates: Requirements 1.1, 1.5**

### Property 4: 叶子名未命中时回退父级名

`classify_f2_leaf('修复件', '自制半成品') == 'semi-finished'`；
`classify_f2_leaf('修复件', None) == 'other'`（不臆造）。

**Validates: Requirements 1.2, 1.3**

### Property 5: 备抵取绝对值后为非负

`impairment-provision` 桶的 `opening`/`closing` 恒 ≥ 0（两种符号约定同解）。

**Validates: Requirements 1.5, 2.3**

### Property 6: 公式预设 cell_ref 页内唯一

运行态 `workpaper:F2` 的 `target_cell` 集合大小 == 条目数。

**Validates: Requirements 4.4**

## Error Handling

| 场景 | 处理 |
|---|---|
| `account_chart` 查不到 14xx | `inventory_accounts` 为 `[]`，前端回退静态清单；归类仍可用叶子自身名 |
| `tb_balance` 查询异常 | 返回 `{}`，审定表保持手工（fail-open，与改造前一致） |
| 叶子名与父级名都未命中 | 归 `other` 桶并在 `tb_source_codes.classified.other` 列出科目码，供审计师人工判断 |
| `report_config` 查不到 `BS-010` | 回退 `['1401~1499']` |

## Testing Strategy

| 层 | 文件 | 覆盖 |
|---|---|---|
| 后端纯函数 | `backend/tests/test_f2_category_rules.py` | Property 1~5 + 两变体参数化 + 反向自检 |
| 后端源模板 | `backend/tests/test_f2_source_template_facts.py` | openpyxl 直读两个披露 sheet 关键结构 |
| 公式预设 | `backend/tests/test_f2_formula_presets.py` | Property 6 + 禁写死编码分类 + `validate_formula` |
| 后端 render | 扩展既有 F2 render 测试 | `inventory_accounts` / `tb_values` 形态 |
| 前端 | `f2AccountModel.spec.ts` 扩展 | 兜底解析纯函数 + 消费点不得只依赖静态映射 |
| 活体 | 真实 DB 直跑 render（变体 A + 变体 B 各一个项目） | 桶之和 == 叶子合计 |
