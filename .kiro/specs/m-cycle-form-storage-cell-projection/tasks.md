# Tasks — M 循环表单存储 → 单元格投影

> **状态：11/12（2026-11-16 实施完成，余 8.3 回填）**
> 前序 spec `m-cycle-key-naming-unification` 收尾时实测发现 `WP()` 对 M 循环恒返 0，
> 用户提议「把 M 循环也纳入 parsed_data.html_data」。design 选方案 B（读时即时投影，零写入）。

## 实施结果（2026-11-16）

**端到端实测通过**（真库真服务，重药控股安徽_2025，savepoint 内造数据后回滚）：

| 表达式 | 值 | 原因 |
|---|---|---|
| `WP('M1','明细表M1-2','H14')` | **`Decimal('100')`** ✅ | `[]` |
| `WP('M1','明细表M1-2','R14')` | `0` | 「单元格内容不是数值：1年以内」（**正确** —— 文本格） |
| `WP('M1','明细表M1-2','H99')` | `0` | 「只有在线编辑文件…」（H99 不在数据区，回落原逻辑） |

**三层链路逐层验证**（`resolve_wp_cell` / `read_formula_cell` / `WPExecutor.read_sheet_cell`）
全部 `state=ok value=Decimal('100')`。

🔴 **实施中抓到的关键陷阱**：ACNR 的 `bind_wp_code` 把 sheet 绑到 **sheet 级底稿 `M1-2`**
而不是父底稿 `M1`，而 `checklist_responses` 的行挂在**父底稿的 `wp_id`** 下
⇒ 第一版投影只按 `M1` 查，永远查不到。修法：`load_form_storage_cells` 遇到未登记的
`M1-2` 时回落到父码 `M1`，**并换用父底稿的 wp_id**（`_parent_wp_id`）。

- [x] 1. 纯函数投影器
  - [x] 1.1 新建 `backend/app/services/wp_form_storage_projection.py`：`project_form_rows_to_cells(...)` 纯函数
    - 输入：`wp_code` / `rows[(item_id, remark)]` / `sheet_name` / `first_data_row` / `field_columns` / `last_data_row`
    - 输出：`(list[ProjectedCell], list[str])`（成功格 + 失败原因）
    - 零 IO、零副作用
  - [x] 1.2 `item_id 前缀 → (sheet_name, first_data_row)` 登记表（10 个 M 循环）
    - 🔴 每条必须与 provider `MSheetConfig.sheet_name` / `first_data_row` 逐值相等
    - M2 上市版登记为「provider 缺声明，不支持」+ 原因
  - [x] 1.3 行号 = `first_data_row + i`（i 取自 `row-{i}`），列号 = provider `json_key → column`
    - 不得手写映射表、不得硬编码行号

- [x] 2. 接入 `resolve_wp_cell`
  - [x] 2.1 `services/wp_cell_reader.py`：`records` 为空时 fallback 到表单投影
    - 🔴 只在 `not records` 时触发，不覆盖已有 `parsed_data` 路径（阴性对照）
  - [x] 2.2 新增 `load_form_storage_cells(db, wp_id, wp_code)` 薄封装（查 `checklist_responses` + provider 配置）
    - 每条 SQL 独立事务（PG 首条失败会 aborted 连带后续）

- [x] 3. 失败可见
  - [x] 3.1 `acnr/reasons.py` 加 4 个原因码：`form_row_json_invalid` / `form_field_not_in_provider` /
    `form_row_beyond_template` / `determination_sheet_not_projected`
  - [x] 3.2 审定表（`M{n}-1`）形态显式返回 `determination_sheet_not_projected`
    - 现读：审定表 item_id 是 `M1-1-tb-amount` 非行表形态，需「按项目名查行」，本 spec 不做

- [x] 4. 单元测试
  - [x] 4.1 纯函数正向：`M1-M1-2-row-0-data` + `{"priorAdjAje": 100}` ⇒ `("明细表M1-2", "H14", 100)`
  - [x] 4.2 10 个 provider 的 `json_key → column` 逐值对拍（读 provider 现算）
  - [x] 4.3 反向：非法 JSON / 未知字段 / 超行号 / 空行 各给对应原因
  - [x] 4.4 幂等：同输入调两次结果相同
  - [x] 4.5 🔴 「零写入」断言：调用投影后 `parsed_data` 逐字节不变

- [x] 5. 端到端真库验证
  - [x] 5.1 在【测试】项目写一条 M1 明细表第 0 行（`priorAdjAje=100`）
  - [x] 5.2 调 `evaluate_wp_formula_expression("WP('M1','明细表M1-2','H14')")` ⇒ 断言 `Decimal('100')`
  - [x] 5.3 清理写入数据

- [x] 6. 变异验证（全 RED）
  - [x] 6.1 列号 `H` → `I`
  - [x] 6.2 `first_data_row` 14 → 15
  - [x] 6.3 删 `priorAdjAje` 的 json_key 映射
  - [x] 6.4 解析失败当 0
  - [x] 6.5 投影结果落库（写 `parsed_data`）

- [x] 7. 阴性对照
  - [x] 7.1 Excel 单元格类底稿（A1 等）的 `WP()` 行为不变
  - [x] 7.2 现有 `test_wp_cell_reader*` / `test_acnr*` 全绿

- [x] 8. 收尾
  - [x] 8.1 干净 worktree 跑守卫
  - [x] 8.2 登记 INDEX
  - [ ] 8.3 回填 `m-cycle-key-naming-unification` 的 18 条 R2 —— 若本 spec 完成后用户在公式管理里
    能引用 M 循环格子，那 18 条可正式销案（或转为「由用户自行链接」）
