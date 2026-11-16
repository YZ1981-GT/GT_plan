# Design — M 循环表单存储 → 单元格投影

## §1 方案选择

### 1.1 三个候选

| 方案 | 做法 | 写入 | 迁移 | 漂移风险 | 评价 |
|---|---|---|---|---|---|
| A. 保存时同步投影 | 保存链路里多写一份 `parsed_data` | ✅ 写 | 无 | **高**（双写必漂移） | ❌ 倒退 |
| **B. 读时即时投影** | `resolve_wp_cell` 里加 fallback，即时把表单行投影成 `CellRecord` | **零** | **零** | **零** | ✅ **采纳** |
| C. 异步后台投影 | 定时/事件任务写 `parsed_data` | ✅ 写 | 需回填 | 中 | ❌ 有延迟 + 失败重试 |

### 1.2 为什么选 B

1. **零写入** ⇒ 与前一 spec「删掉 M 循环并行写入」同一方向，不倒退；
2. **零迁移** ⇒ 存量数据自动生效；
3. **单源** ⇒ `checklist_responses` 仍是唯一真源，投影是纯函数；
4. **可测** ⇒ 纯函数易写守卫 + 变异；
5. **零侵入 ACNR** ⇒ 不改 `extract_custom_cells` / `_storage_kind` / `reasons.py`。

## §2 实现位置

### 2.1 唯一改动点：`wp_cell_reader.resolve_wp_cell`

现状（`services/wp_cell_reader.py:128`）：

```python
records = extract_custom_cells(parsed_data if isinstance(parsed_data, dict) else None)
```

改为：

```python
records = extract_custom_cells(parsed_data if isinstance(parsed_data, dict) else None)
if not records:
    # M 循环等「表单录入」底稿：parsed_data 为空，数据在 checklist_responses
    records = await _project_form_storage_cells(db, wp_id, wp_code)
```

### 2.2 新模块：`services/wp_form_storage_projection.py`

纯函数 + 一个薄的 DB 读取封装：

```python
# ── 纯函数（可单测，零 IO）─────────────────────────────────
def project_form_rows_to_cells(
    *,
    wp_code: str,
    rows: Sequence[FormRow],          # (item_id, remark_json_text)
    sheet_name: str,
    first_data_row: int,
    field_columns: Mapping[str, str],  # json_key -> column letter
    last_data_row: int,
) -> tuple[list[ProjectedCell], list[str]]:
    """把逐行 JSON 投影成 (sheet, cell, value) 列表 + 失败原因。"""

# ── DB 读取封装（薄）──────────────────────────────────────
async def load_form_storage_cells(db, wp_id, wp_code) -> tuple[list[ProjectedCell], list[str]]:
    """查 checklist_responses + provider 配置，调纯函数。"""
```

### 2.3 item_id 前缀 → sheet 的登记

10 个 M 循环各一条，**必须与 provider `sheet_name` 逐值相等**（守卫断言）：

| wp_code | item_id 前缀 | provider `sheet_name` | `first_data_row` |
|---|---|---|---:|
| M1 | `M1-M1-2-row-` | `明细表M1-2` | 14 |
| M2 | `M2-M2-2-listed-row-` / `M2-M2-2-unlisted-row-` | `明细表（上市公司）M2-2` / `明细表（非上市公司）M2-2` | 13 |
| M3 | `M3-M3-2-row-` | `明细表M3-2` | 15 |
| M4 | `M4-2-row-` | `明细表M4-2` | 10 |
| M5 | `M5-2-row-` | `明细表M5-2` | 12 |
| M6 | `M6-2-row-` | `明细表M6-2` | 10 |
| M7 | `M7-2-row-` | `明细表M7-2` | 10 |
| M8 | `M8-2-row-` | `明细表M8-2` | 10 |
| M9 | `M9-2-row-` | `明细表M9-2` | 10 |
| M10 | `M10-2-row-` | `明细表M10-2` | 12 |

🔴 **M2 有两个 sheet**（上市 / 非上市），provider 当前只声明了非上市
（`m201-unlisted-managed`）⇒ 上市那半登记为「provider 缺声明，不支持」，给原因。

### 2.4 行号计算

```
行号 = first_data_row + i
其中 i 来自 item_id 的 `row-{i}` 段
```

🔴 **不做「跳过空行」之类的聪明处理** —— 空行的值就是空，投影照常输出；
取值层看到空值会返回 `cell_empty`（现有语义）。

### 2.5 审定表（`M{n}-1`）的裁决

审定表的 item_id 是 `M1-1-tb-amount` 这种**非行表**形态（不是 `row-{i}-data`）。

现读 provider 有 `DETERMINATION_SHEET`（如 `M1-1` 的 `m1-determination`，
`first_data_row=7`，字段 `project_name` / `prior_unadjusted` / …）。

**裁决**：本 spec **只做明细表**（逐行 JSON 形态，10 个 provider 都有）。
审定表单独登记为「待后续」，原因：它的 `item_id → 行号` 映射不是 `row-{i}` 而是
「按项目名查行」（`M1-1-tb-amount` 对应「应付股利」那一行），需要另一套定位逻辑。

⇒ `WP('M1-1','审定表M1-1','B7')` 仍返 0，但原因会从
「该底稿以表单方式录入」变成更具体的「审定表形态暂不支持投影」。

## §3 失败可见

新增原因码（登记进 `acnr/reasons.py` 的 `CELL_VALUE_REASONS`）：

| 原因码 | 文案 |
|---|---|
| `form_row_json_invalid` | 表单第 {i} 行的数据不是合法 JSON：{detail} |
| `form_field_not_in_provider` | 表单第 {i} 行的字段「{field}」不在 provider 声明里（前端多写了键） |
| `form_row_beyond_template` | 表单第 {i} 行的行号 {row} 超出模板数据区（{first}~{last}） |
| `determination_sheet_not_projected` | 审定表形态暂不支持投影（本 spec 只做明细表） |

## §4 验证设计

### 4.1 纯函数单测

- 10 个 provider 各自：`json_key → column` 逐值对拍（读 provider 现算，不手写）
- 正向：一条 `M1-M1-2-row-0-data` + `{"priorAdjAje": 100}` ⇒ `("明细表M1-2", "H14", 100)`
- 反向：非法 JSON / 未知字段 / 超行号 各给对应原因
- 幂等：同输入调两次结果相同

### 4.2 端到端（真库）

在【测试】项目里：
1. 写一条 `checklist_responses`（M1 明细表第 0 行，`priorAdjAje=100`）
2. 调 `evaluate_wp_formula_expression("WP('M1','明细表M1-2','H14')")`
3. 断言返回 `Decimal('100')`
4. 清理

### 4.3 变异（必须全 RED）

| 变异 | 期望 |
|---|---|
| 列号 `H` 改成 `I` | 取值失败 / 值不对 ⇒ RED |
| `first_data_row` 从 14 改 15 | 行偏移 ⇒ RED |
| 删 `priorAdjAje` 的 json_key 映射 | 该字段取不到 ⇒ RED |
| 解析失败当 0 | 原因不出现 ⇒ RED |
| 投影结果落库（写 `parsed_data`） | 「零写入」断言 ⇒ RED |

### 4.4 阴性对照

Excel 单元格类底稿（如 A1，`parsed_data.html_data` 有数据）的 `WP()` 行为**必须不变** ——
投影只在 `records` 为空时触发，不覆盖已有路径。

## §5 边界与非目标

- **不做**审定表投影（见 §2.5）
- **不做**M2 上市版（provider 缺声明）
- **不改** `extract_custom_cells` / `_storage_kind` / `reasons.py` 的现有逻辑（只加新原因码）
- **不写** `parsed_data`（零写入是本 spec 的核心约束）
- **不动**前端（投影纯后端）
