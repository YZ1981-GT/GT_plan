# Task 2：形态判定 + 几何逐格实测（F5）

**执行**：2026-09-26　`uuid_col` 共同缺陷的完整说明见
`.kiro/specs/f3-sync-coverage-and-first-canary/evidence/task2-morphology-and-geometry.md` §一。

模板：`F/F5 营业成本.xlsx`　**sha256 `417e5ae7453528725f3ae5eb06f70d36269b089cd73a00884c835f4586267cb7`**
（187,721 B，11 sheets）—— 与 spec 记载逐字一致。

## 一、canary：`重大调整核查表F5-8`（已声明并验通）

| 项 | 实测 | 与 spec |
|---|---|---|
| 尺寸 | 39r × **8c（H）** | 🔴 spec 写「39r×I」，实测 max_col=H；差异使 UUID 列 I **超出 max_col**（见 §二） |
| 公式总数 | **7**，全在页眉 R3/R4（引「底稿目录」）⇒ 数据区零公式 | ✅ |
| 表头 | **两级 R12/R13** | ✅ |
| 数据区 | **R14-29**（16 行） | ✅ |
| footer | **无合计** ⇒ 锚行 **R30** | ✅ |
| UUID 列 | 全空列 I/J/K/L ⇒ 取 **I** | ✅ |
| `formula_columns` | **`()`** | ✅ |
| 数据验证 | **无** | — |

表头合并区实测：
```
A12:A13  B12:B13  C12:C13  H12:H13     ← 四个纵向合并（单列跨两行）
D12:E12                                 ← 横向组「调整金额」→ D 借方 / E 贷方
F12:G13                                 ← 🔴 跨两行两列：F「调整理由」吞掉 G
F14:G14 … F29:G29                       ← 数据行逐行 F:G 合并（16 行）
```

表头逐列：`A 日期 · B 凭证号 · C 重大调整事项内容 · D-E 调整金额{借方/贷方} ·
F 调整理由（含 G） · H 理由是否充分`

⇒ 受管 **7 个字段**（A/B/C/D/E/F/H），**G 列不单独声明**（被 F 合并）。
判据 `test_merged_cells_justify_skipping_g` 逐格证明 16 个数据行的 `F{r}:G{r}` 合并都存在。

### 🔴 修正一：footer marker 逐字带全角冒号

spec Task 8 写 `footer_marker="三、审计说明"`（**无冒号**）。
逐格实测 **A30 = `'三、审计说明：'`**（带全角冒号）。

`assert_footer_anchor_stable` 是逐字匹配 ⇒ 用 spec 的值会定位失败。声明取实测值。
判据 `TestProperty3AnchorFooter::test_footer_marker_matches_template_verbatim` 直接比对模板格，
并单独断言 `endswith("：")`。

同时实测锚行 R30 整行**无任何公式** ⇒ `footer_carries_total_formula=False` 有据
（判据 `test_anchor_row_has_no_formula`）。

锚行之后的 HTML-only 区（已登记 `HTML_ONLY_ANCHOR_ROWS_F508`）：
R30「三、审计说明：」· R33「四、审计结论：」· R37「提示：」· R38/R39 两行编制提示。

### 🔴 修正二：UUID 列超出 `max_column`（扩列场景）

`max_column = 8（H）`，UUID 列 **I = 第 9 列** ⇒ 超出。
需求 2.5 / Property 6 要求「扩列后 `print_area` / `page_setup` 与基线一致」。
判据 `TestProperty6UuidColumnBeyondMaxCol` 已钉住 `max_col == 8` 与 `col(I) == 9 > max_col`
两条事实，并验证 I 列在模板中全空。

（同批发现 F4-7/F4-8/F4-1 的 uuid_col 也超各自 max_col —— 扩列不是 F5 独有，见 F4 证据 §一。）

### FC-10 逐格取证：F5 canary 零命中

`重大调整核查表F5-8` 全表 `number_format` 含 `%` 的格数 = **0**
（判据 `TestProperty19Fc10NotApplicableOnCanary`）。

## 二、F5-1 两区几何（60r × 14c，max_col=N；待 Task 21 声明）

| 区 | 标题行 | 数据区 | 小计 | uuid_col |
|---|---|---|---|---|
| 主营区 | R7「主营业**业**成本：」 | **R8-17**（10 行） | R18「小计」`SUM(B8:B17)` | —（HTML-only） |
| 其他业务区 | R19「其他业务成本」 | **R20-25**（6 行） | R26「小计」`SUM(B20:B25)` | **K** |

其后：R27「合计」· R28「试算平衡表数」· R29「差异数」· R30「1、审计说明」· R35「2、审计结论」·
R39「提示：」+ R40/R41 两行。

与 spec 一致（主营区 10 槽 R8-17 ✅、其他业务区 R20-25 / 小计 R26 ✅）。
两区小计的 SUM 均覆盖 **B~I 八列**。

🔴 **修正三：spec 说「F5-1 max_col N、J-N 全空」有误** —— 实测全空列从 **K** 开始
（12 个：K~V），**J 列有值**。⇒ 其他业务区的 uuid_col 取 **K**（不是 J）。

🔴 主营区判 **HTML-only**（裁决 F5-H3），故不分配 uuid_col。已登记在
`phase5_f5_cost_of_sales.HTML_ONLY_STORE_KEYS`，判据
`TestProperty17And24Registrations::test_f51_main_zone_is_html_only` 断言
`F5-1-adj-main-rows` 不在 `all_store_item_ids()`。

## 三、前端三元组实证（canary）

| 维度 | 实测 |
|---|---|
| store 键 | `F5-8-rows`（`useF5MajorAdjustment.ts` 的 `STORAGE_KEY`）；legacy 只有 `F5-8-conclusion`（结论键，非行数组键）⇒ 主键无别名冲突 |
| 增删行 | `addRow` / `removeRow` 各 1 |
| 行身份 | 🔴 **`id`**（`MajorAdjustmentRow.id`）—— **不是** `rowId`，与 D 类惯例相反（同 E1 教训） |
| 判定 | `excel_table` + `row_identity_key="id"` + `StoreKind.rows` |

契约里 `row_identity.json_pointer` = **`/rows/*/id`**（判据
`test_contract_row_identity_pointer_uses_id` 同时断言它不等于 `/rows/*/rowId`）。
投影侧 fail-closed 判据：给一行只带 `rowId` 而无 `id` ⇒ 必抛「缺少稳定行身份」。

store-only 字段：`netAmount`（借 − 贷，前端派生）。

## 四、BP-7 三处已修（Task 6，详见 `task0-prerequisites.md` 补-7）

`useF5MonthlyDetail.ts:133` / `useF5OtherCost.ts:146` / `useF5Comparison.ts:128`
三处下标派生行身份已收敛到 `f5RowIdentity.ts`，含「命中旧下标形态也重铸」与「载入即回写」两条
超出 spec 原文的处置。判据 17 passed，变异打红 5 条。

## 五、模板治理债汇总（登记，不改字节）

| 位置 | 问题 |
|---|---|
| sheet 名 `营业务成本审定表F5-1` | 「营业务」错字（spec 已知；改名会动 sha 与 135 处跨表引用） |
| F5-1 R2 标题 | 同样是「营业务成本审定表」 |
| **F5-1 R7 标题「主营业业成本：」** | 🔴 「主营业**业**」又一处错字（spec 未记，本次实测新增） |
| F5-7 `G31` | 引越界空区 `G56:G61`（sheet 仅 36 行）⇒ 审定数列主营业务成本漏算 6 项 —— Task 17 走模板覆盖层修 |
| 3 个残留 definedName | `AS2DocOpenMode` / `a暗暗` / `ffd`（后两个明显手工误建） |

## 六、其余 sheet 的实测策略

F5-5 / F5-3 / F5-2 / F5-7 / F5-6 的逐格几何在各自声明任务（Task 13/14/16/18/20）中随实测随声明。
本文件已覆盖阻塞面：canary 全量（含两处 spec 修正）+ F5-1 两区区界与 uuid_col 修正。
