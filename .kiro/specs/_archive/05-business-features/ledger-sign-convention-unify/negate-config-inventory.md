# 存量 `negate` transform 配置盘点清单（Task 5.2 产出）

> 任务：盘点存量 `data_fetch_custom` 的 `negate` transform 配置，识别哪些是为纠正旧约定（借正贷负）负数而设——这些配置在 v2（类别自然正数）下会变成反向纠错。
> 需求：11.2 / 11.3。设计：design.md 「发现 6」+「关键风险」。下游清单：downstream-consumers.md E 组。
> 性质：**盘点产出**，本任务不改配置数据本身（改动留给 Task 6.4 迁移）。

## 结论（TL;DR）

**存量 `negate`（及 `abs`）transform 配置数量 = 0。Task 6.4 无需处理任何 negate 配置数据。**

- 静态代码：`negate` 字面量仅出现在 ① 枚举定义 ② 前端下拉选项 ③ 测试用例三处，**无任何 JSON 配置 / DB seed / 预设公式生成 negate**。
- 运行时数据（真实 PG）：`custom_fetch_rules` 在所有项目中均为空（0 个项目配置），`negate=0` / `abs=0`；相关机制 `sum_minus` 在 `disclosure_notes` 中出现 0 次。

## 盘点方法

1. **配置数据存储位置定位（codegraph + grep 实证）**：
   - `data_fetch_custom` 的取数规则**不存在于任何 JSON 配置文件**。`grepSearch "\"transform\""`（`**/*.json`）= 0 命中。
   - 唯一持久化路径：`Project.wizard_state.custom_fetch_rules`（DB JSONB），由 `POST /api/projects/{id}/custom-fetch/save-rules` 写入（见 `backend/app/routers/data_fetch_custom.py`）。按 `target_type:target_id` 为 key，value 含 `rules: list[dict]`，每条 rule 带 `transform` 字段。
2. **静态全仓搜索** `negate` / `Transform.NEGATE` / `"transform"`：见下「静态命中分类」。
3. **运行时 DB 扫描**：一次性脚本 `_scan_negate_transform_configs.py` 遍历全部 `projects.wizard_state.custom_fetch_rules`，统计 `transform=negate/abs` 的规则；并扫 `disclosure_notes.table_data` 中 `sum_minus` 出现次数。脚本已用完删除。

## 静态命中分类（区分"合法机制" vs"存量配置数据"）

| 命中位置 | 类型 | 判定 |
|---|---|---|
| `backend/app/services/data_fetch_custom.py:62` `Transform.NEGATE = "negate"` | 枚举定义（合法显式配置机制，Task 5.1 已确认） | **非配置数据，保留** |
| `data_fetch_custom.py:441-443` `_apply_transform` 中 `elif transform == Transform.NEGATE: return -valid[0]` | 求值逻辑（仅在显式配置时翻转，default=direct 不翻） | **非配置数据，保留** |
| `data_fetch_custom.py:14` docstring 示例注释 `// direct|negate|abs|percentage` | 文档注释 | **非配置数据，保留** |
| `audit-platform/frontend/src/components/formula/CellSelector.vue:30` `<el-option value="negate" label="取反" />` | 前端 UI 下拉项（用户可选机制） | **非配置数据，保留** |
| `backend/tests/test_formula_tb_sign_passthrough.py:152` `_apply_transform([8000], Transform.NEGATE)` | 单元测试 | **非配置数据，保留** |
| `from_note_formula()`（data_fetch_custom.py:102） | 预设公式→FetchRule 转换器，**硬编码 `transform=Transform.DIRECT`** | **预设永不产出 negate** |

**关键判定**：以上全部是"提供 negate 这一显式配置能力"的代码/机制（合法、Task 5.1 已确认求值器对 direct 原样透传不隐式翻转），**不是"存量配置数据里实际用了 negate 的条目"**。需求 11.2/11.3 关心的是后者——而后者数量为 0。

## 运行时 DB 扫描结果（真实 PG，`audit_platform`）

```
projects_with_custom_fetch_rules = 0
total_custom_fetch_rules        = 0
negate_count                    = 0
abs_count                       = 0
disclosure_notes_sum_minus_occurrences = 0
```

即：当前没有任何项目配置过自定义取数规则，自然也没有任何 `negate`/`abs` 配置；附注绑定层的 `sum_minus`（负债类取反相关机制）在存量附注数据中也未被使用。

## 逐条判定清单

| # | negate 配置条目 | 来源 | 判定 | 理由 |
|---|---|---|---|---|
| — | （无） | — | — | 存量 negate transform 配置数量为 0，无条目可列 |

> 判定口径（供将来若出现 negate 配置时复用）：
> - **移除/反置**：该 negate 针对负债/权益/收入等贷方类科目、原为把旧约定负数翻正展示 → v2 下 TB 已是正数，negate 会把正数翻成负数（反向纠错），须移除。
> - **保留**：该 negate 是合法业务取负（如现金流量表"资产增加=现金流出"语义、或对某审定数刻意取相反数展示），与符号约定无关 → 保留。

## 对 Task 6.4 的交接

- **Task 6.4 关于 negate 配置的工作量 = 0**：无 negate/abs 存量配置数据需要在迁移时移除或反置。
- Task 6.4 可在迁移脚本中**保留一个轻量防御性检查**（可选）：迁移时顺带扫描 `custom_fetch_rules` 的 `transform=negate`，若未来出现则按上表口径记入待复核清单。但当前无数据，非阻塞项。
- 相关机制 `sum_minus`（`note_source_resolvers` / `disclosure_trace`，对负债类取相反数）属代码层显式机制而非配置数据，且当前存量数据 0 占用；其 v2 符号正确性由 Task 5.3（disclosure 读 audited_amount 符号假设确认）覆盖，不在本盘点的"配置数据"范畴内。

## 复核可重跑

如需在数据增长后复核，重建一次性脚本遍历 `projects.wizard_state.custom_fetch_rules`（按 `transform` 字段计数 negate/abs），逻辑见本任务执行记录。当前结果：**0**。
