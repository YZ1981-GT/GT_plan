# Requirements — M 循环表单存储 → 单元格投影

> **状态：0/12（2026-11-16 立项）**
>
> 来源：`m-cycle-key-naming-unification` 收尾时用户实测发现「公式管理的 `WP()` 表间链接
> 对 M 循环恒返 0」，追问「它们的数据在 parsed_data.html_data，你能把 M 循环也纳入进去吗？
> 这样更统一」⇒ 本 spec 承接。

## 1. 背景（2026-11-16 实测，不是推测）

### 1.1 现状：`WP()` 对 M 循环取不到值

真库实测（`evaluate_wp_formula_expression`，项目「重庆和平药房连锁有限责任公司_2025」）：

| 表达式 | 返回值 | 原因 |
|---|---|---|
| `WP('M1-1','审定表M1-1','B7')` | `Decimal('0')` | 该底稿以表单方式录入，数据不在单元格中，本期暂不支持取值 |
| `WP('M1','明细表M1-2','D14')` | `Decimal('0')` | 同上 |
| `WP('NONEXIST-99','x','A1')` | `Decimal('0')` | 项目中没有底稿 NONEXIST-99（**正确报错**） |
| `1+2` | `Decimal('3')` | `[]`（引擎本身正常） |

### 1.2 根因链（逐层追踪到最底）

```
WP(...) → wp_cell_target.read_formula_cell
        → wp_cell_reader.resolve_wp_cell          # 唯一取值入口
          → 查 working_paper.parsed_data          # ← M 循环这里是 None
          → extract_custom_cells(parsed_data)     # ← 返回 []
          → 无 CellRecord ⇒ state=missing
        → wp_cell_target._refine
          → _storage_kind(): checklist_responses 有行 ⇒ has_form=true
          ⇒ value_in_form_storage
            「该底稿以表单方式录入，数据不在单元格中，本期暂不支持取值」
```

### 1.3 真库现算：M 循环的 `parsed_data` 是空的

| 项目 | 底稿 | 表单行 | parsed_data | html_data |
|---|---|---:|---|---|
| 宜宾临港店_2025 | M1 | 1 | **None** | — |
| 重药安徽_2025 | M1 | 1 | `{audit_checks, audit_checks_at}` | **None** |
| 和平药房_2024 / 2025 | M1 | 0 / 1 | **None** | — |
| 宜宾临港店_2025 | M1-1 / M1-2 | 0 / 0 | **None** | — |

8 张里 7 张 `None`，1 张只有 `audit_checks`（与业务无关）。**`html_data` 一个都没有。**
数据只存在于 `checklist_responses`。

### 1.4 关键发现：不需要改 ACNR 的取值层

`extract_custom_cells`（`services/address_registry.py`）认三种形态：

| 形态 | 结构 | 判据 |
|---|---|---|
| ① 嵌套 | `html_data[sheet].cells["D14"] = {v: 123}` | `sheet_data.get("cells")` 是 dict |
| ② **扁平** | `parsed_data[sheet]["D14"] = 123` | **field 匹配 A1 地址正则** |
| ③ 顶层 | `parsed_data["cells"]["D14"]` | — |

🔴 **形态 ② 的判据只看「field 是不是 A1 地址」，不看数据来源。**

⇒ 只要能产出 `parsed_data["明细表M1-2"]["D14"] = 123`，`WP()` 立刻能取到值 ——
**不用改 `resolve_wp_cell`、不用改 `_storage_kind`、不用改 `extract_custom_cells`**。

## 2. 需求

### Requirement 1：M 循环的表单数据可被 `WP()` 取到

1. WHEN 公式引用 M 循环底稿的某单元格（如 `WP('M1','明细表M1-2','H14')`）THEN 系统 SHALL 返回该格的实际值，而不是 0。
2. 取值 SHALL 与 `checklist_responses` 的当前内容一致（保存后立即可取，无需额外同步步骤）。
3. 取不到时 SHALL 返回明确中文原因（沿用现有 `value_in_form_storage` 之外的新原因码），不得静默返 0。

### Requirement 2：投影是纯读、不落库

1. 投影 SHALL **不写入** `parsed_data`、不写入任何新表 —— `checklist_responses` 仍是唯一真源。
2. 投影 SHALL 是纯函数（同输入同输出，无副作用），可被单测直接调用。
3. 🔴 理由：本 spec 的前序 spec（`m-cycle-key-naming-unification` 任务 4）刚把 M 循环的
   整表 `*-full-data` 并行写入删掉（双写漂移缺陷）。投影若落库就是**倒退**。

### Requirement 3：映射规则单一来源

1. `json_key → 列号` SHALL 读 provider 的 `MSheetConfig.fields`（现成：
   `MFieldSpec(json_key='priorAdjAje', column='H', ...)`），**不得手写映射表**。
2. `行号` SHALL 读 provider 的 `first_data_row`（现成：M1=14 / M2=13 / M3=15 / M4=10 …），**不得硬编码**。
3. `item_id 前缀 → sheet` SHALL 有显式登记（10 个 M 循环各一条），且守卫断言登记项与
   provider `sheet_name` 逐值相等。

### Requirement 4：只覆盖已确认的存储形态

1. 逐行 JSON 形态（`M{n}-...-row-{i}-data`）SHALL 支持 —— 这是本 spec 的主体。
2. 整表 JSON 形态（`M{n}-2-full-data`）SHALL **不再出现**（前序 spec 已删），若检测到 SHALL 记 warning 并跳过。
3. 审定表形态（`M{n}-1-tb-amount` 等非行表键）SHALL 单独裁决：能定位到单元格的接，不能的登记为不支持并给原因。

### Requirement 5：失败可见，不伪造

1. 表单行 JSON 解析失败 SHALL 记原因，不得当成 0。
2. 字段不在 provider 声明里 SHALL 记原因（说明前端多写了键）。
3. 行号超出 provider 的 `last_data_row` SHALL 记原因（说明数据行数超模板）。

### Requirement 6：验证

1. 单元：投影纯函数的正向/反向（含 10 个 provider 各自的 `json_key → column` 逐值对拍）。
2. 端到端：真库真服务跑 `WP()` 取 M1 明细表某格，值必须等于 `checklist_responses` 里对应字段的值。
3. 变异：改列号 / 改行偏移 / 删 json_key 映射 / 把解析失败当 0 —— 全部必须 RED。
4. 阴性对照：Excel 单元格类底稿（如 A1）的 `WP()` 行为不变（不因本改动而改变）。
