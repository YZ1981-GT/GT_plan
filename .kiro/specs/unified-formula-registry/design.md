# 设计：统一公式注册表

> spec: `unified-formula-registry` · requirements R1~R5

## §1 现状分析（Step 0 调研结论）

公式碎片化分三层：

1. **存储碎片**：5 张表 + 1 JSON 文件 + 1 JSON 字段。`formula_settings/stores.py` 的 `DomainStore` 已统一了读写接口，但物理后端各异。
2. **执行碎片**：报表/表间审核走 L2→L1 内核；底稿预填充走独立 regex；公式管理页走 L1。
3. **函数列表碎片**：L1 `FunctionRegistry` 有 14 函数，`prefill_engine` 额外认 4 函数（LEDGER/LEDGER_DETAIL/TB_AUX/COUNT_LEDGER），前端解析器在 Step 0 补到 16 个。

**本 spec 只收敛层 1（目录）和层 3（函数列表），不动层 2（执行路径统一留 Step 2）**。理由：执行路径改动面极大（prefill_engine 1300+ 行、6 个独立 resolver），风险不适合与目录建设同批。

## §2 公式目录 service（R1）

```
backend/app/services/formula_catalog.py
```

### 核心函数

```python
async def build_catalog(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    domains: Iterable[str] | None = None,  # None = 全部 6 域
) -> list[CatalogEntry]
```

`CatalogEntry` 数据类：

```python
@dataclass
class CatalogEntry:
    addr_id: str          # ACNR 地址
    domain: str           # report / wp / note / cross_check / tb_detail / consol_note
    slot_key: str         # 域内公式位 key
    formula_text: str     # 拼接后的可读公式文本
    layer: str            # global / project / preset / template / pinned
    function_refs: list[str]  # 引用的函数名列表 ["TB", "ROW"]
    target_label: str     # 中文标签
```

实现：对每个域调 `effective_slots()`，遍历 slot → `formula_text()` 提取可读文本 → `_extract_function_names()` 提取引用的函数名 → 映射 slot_key → addr_id。

### 路由

```
GET /api/formula-catalog?project_id=...&domain=report,wp
GET /api/formula-catalog/stats?project_id=...
GET /api/formula-catalog/{addr_id}/dependencies?project_id=...
```

catalog 和 stats 挂 `get_current_user`（登录即可查目录）；dependencies 挂 `require_project_access("readonly")`（需项目成员）。

### addr_id 映射

| 域 | slot_key 示例 | addr_id 示例 |
|---|---|---|
| report | `balance_sheet:BS-002` | `report:balance_sheet:BS-002` |
| wp | `D2\|审定表D2-1\|E100` | `wp:D2/审定表D2-1/E100` |
| note | `五、1\|应收账款:value` | `note:五、1` |
| cross_check | `report_balance_sheet#00001` | `cross_check:report_balance_sheet#00001` |
| tb_detail | `1001\|月度明细` | `tb_detail:1001\|月度明细` |
| consol_note | `五、1\|2\|3` | `consol_note:五、1\|2\|3` |

report 域已有 addr_id 体系（`dependencies.py`），其余域加前缀 `{domain}:`。

## §3 函数注册表统一（R2）

### 新增 4 个占位 handler

在 `formula_engine.py` 的 `_REGISTRY` 里注册，category = `"底稿取数"`：

```python
def _handle_ledger(args, ctx, trace):
    """LEDGER('科目','方向','范围') — 底稿预填充专用，L1 内核无上下文直接返 0。"""
    trace.append(f"LEDGER({args}) = 0 (no-op in L1)")
    return Decimal("0")

_REGISTRY.register("LEDGER", _handle_ledger, arity=3, ...)
_REGISTRY.register("LEDGER_DETAIL", _handle_ledger_detail, arity=3, ...)
_REGISTRY.register("TB_AUX", _handle_tb_aux, arity=3, ...)
_REGISTRY.register("COUNT_LEDGER", _handle_count_ledger, arity=3, ...)
```

占位 handler 在 L1 返回 0 —— 这些函数的真实取数只在 `prefill_engine` 的异步路径里发生。注册它们的目的是：
- `validate_formula` 不再把合法的底稿公式标为 blocked
- `formulaSyntaxParser.ts` 可从后端动态获取完整函数列表
- `_is_blocked_formula` 的白名单自动扩展

### prefill_engine 正则派生

```python
# 替换硬编码的 _FORMULA_RE
from app.services.formula_engine import _REGISTRY
_KNOWN = "|".join(sorted(_REGISTRY.known_function_names()))
_FORMULA_RE = re.compile(rf"=({_KNOWN})\s*\(([^)]*)\)", re.IGNORECASE)
```

### formula_grammar 元数派生

```python
# formula_grammar.py
from app.services.formula_engine import _REGISTRY

def _build_arity() -> dict[str, int | list[int] | None]:
    out = {}
    for meta in _REGISTRY.list_all():
        out[meta["name"]] = meta["arity"]
    return out

FORMULA_ARITY: dict[str, int | list[int] | None] = _build_arity()
```

### 前端函数清单端点

```
GET /api/formula-functions → [{name, arity, minArgs, maxArgs, description, syntax, category}]
```

`formulaSyntaxParser.ts` 的 `KNOWN_FUNCTIONS` 和 `FUNCTION_ARITY` 改为运行时从此端点取（初始化一次，缓存到模块级变量）。渐进式：先加端点，前端按需消费（SSR 不依赖）。

## §4 公式位命名规范（R3）

写 `docs/reference/formula-slot-key-spec.md`，明确 6 域的：
- slot_key 格式（分隔符、各段含义）
- 与 ACNR addr_id 的转换规则
- 命名约束（长度、字符集、保留前缀）

这份文档作为后续所有域扩展的规范参考。

## §5 依赖图改经目录（R4）

`dependencies.py::formula_dependencies()` 目前直接调 `effective_slots()` 取 6 域公式。改为经 `formula_catalog.build_catalog()` 取统一目录后，从目录项的 `formula_text` 做解析。好处：
- 目录 → 依赖分析共用一套 addr_id，不再各自映射
- 未来加域（如自定义函数域）只改目录，依赖分析自动扩展

但目前 `dependencies.py` 需要 `effective_slots` 返回的 `definition` dict（不是纯文本），因为不同域的公式字段名不同。所以改法是：
- `build_catalog()` 额外返回 `raw_definition`（原始 dict）
- `dependencies.py` 改从 `build_catalog()` 取结果，用 `formula_text` 做上下游解析

## §6 不做的事（Scope Out）

1. **执行路径统一**（prefill_engine 改走 L1）—— 留 Step 2
2. **存储后端归一**（report_config 列 → formula_setting 表）—— 破坏性太大，留 Step 3+
3. **自定义函数注册持久化**（当前 `FormulaEngine.register_custom_function` 只在进程内生效）—— 留独立 spec
4. **公式推送与目录联动**（推送覆盖率从目录算）—— 留 Step 2 与执行统一同批

## §7 风险

- `prefill_engine` 的 `_FORMULA_RE` 改为动态生成后，import 顺序须保证 `formula_engine._REGISTRY` 已注册完毕再引用。解法：`_FORMULA_RE` 改为延迟初始化（第一次调用时才编译）。
- 占位 handler 返回 0 可能让 `validate_formula` 误判底稿公式为「可执行但结果为 0」。解法：handler 标记 `trace` 为 `no-op in L1`，前端/日志可识别。
