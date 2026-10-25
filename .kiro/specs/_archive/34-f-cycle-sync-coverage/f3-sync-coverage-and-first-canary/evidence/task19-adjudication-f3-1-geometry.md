# F3-1 审定表：逐行公式集合实测（Task 19 证据）

取证脚本：`backend/scripts/analyze/_probe_f345_geometry.py F3 --sheets "审定表F3-1" --header-rows 5,6 --data-range 7,13`
模板：`backend/wp_templates/F/F3 应付票据.xlsx`　sha256 `06de707ba4d4f8d91534e872c7d135b9576cc3a012e3877b1f60db59ce6b3a6b`（只读，未改字节）

## 1. 几何

`审定表F3-1` `visible` 48r × 12c（max_col = L）

| 行 | 角色 |
|---|---|
| R1~R4 | 抬头（A3/C3/E3/J3、A4/C4/E4 引 `底稿目录`） |
| R5 | 一级表头：`项目`(A5:A6 合并) / `期初数`(B5:E5 合并) / `期末数`(F5:J5 合并) |
| R6 | 二级表头：B 未审数 / C 账项调整 / D 重分类调整 / E 审定数 / F 未审数 / G 账项调整 / H 重分类调整 / I 审定数 / J 索引 |
| **R7~R10** | **数据区（4 行）** |
| R11 | 合计 `=SUM(B7:B10)`，覆盖 B~I 八列 |
| R12 | 试算平衡表数（无公式，外部填） |
| R13 | 差异数：仅 `E13=E11-E12`、`I13=I11-I12` |
| R14 起 | 审计说明（R15 有 `D15=IF(E7=0,0,(I7-E7)/E7)`） |

合并区 5 个：`A5:A6` `A1:J1` `F5:J5` `B5:E5` `A2:J2`

## 2. 🔴 逐行公式集合差异 —— 确证须拆 spec

| 行 | A 列 | 公式列 | 列数 |
|---|---|---|---|
| R7 | `银行承兑汇票`（固定标签） | B,E,F,G,H,I | 6 |
| R8 | `商业承兑汇票`（固定标签） | B,E,F,G,H,I | 6 |
| R9 | 空 | E,I | 2 |
| R10 | 空 | E,I | 2 |

差异**不只是数量**，`I` 列语义根本不同：

```
# R7/R8 —— 跨表 SUMPRODUCT 按 A 列标签取数
B7 = SUMPRODUCT(('明细表F3-2'!$B$15:$B$30=$A7)*('明细表F3-2'!L$15:L$30))
I7 = SUMPRODUCT(('明细表F3-2'!$B$15:$B$30=$A7)*('明细表F3-2'!R$15:R$30))
E7 = B7+C7+D7

# R9/R10 —— 本行横向加总，不碰明细表
E9 = B9+C9+D9
I9 = F9+G9+H9          ← 与 I7 的 SUMPRODUCT 完全不同
```

裁决 **F3-H4（mask 行级不是矩形）成立**，拆两个区。

🔴 **区分维度按 D3-4 双区先例（`phase5_d3_04_analysis.py`）**：两区**共享单一 `sheet_key`**，靠
`table_key` / `template_id` / `table_name` / `uuid_col` 四项区分。不可给两区起两个 sheet_key ——
`managed_sheet` 映射到两个 sheet_key 会在契约装配时产生「同 excel_name 两个 sheet 条目」的冲突
（D3-4 docstring 已记该教训，其 design.md 旧骨架的 `d34-managed-credit`/`-debit` 即为过时示意）。

| 区 | table_key | 行范围 | 行数 | 公式列（只读） | 可编辑列 | uuid_col | table_name |
|---|---|---|---|---|---|---|---|
| 种子区 | `adjudication_seed_rows` | R7~R8 | 2 | B,E,F,G,H,I | C,D,J | **K** | `GT_F31_SEED_ROWS` |
| 空槽区 | `adjudication_slot_rows` | R9~R10 | 2 | E,I | A,B,C,D,F,G,H,J | **L** | `GT_F31_SLOT_ROWS` |

共享 `sheet_key = "f31-managed"`（照 F3-5 canary 的 `f35-managed` 命名惯例）。

- 兄弟区 uuid_col 必须互不相同（框架层用 uuid_col 配对 spec↔contract table，同列会抛 `ProviderCapabilityError`）。
- 两区共用 R5/R6 表头 ⇒ 都传 `header_group_row=5, header_leaf_row=6`，契约 anchor 同为 `A5`。
  按 D3-4 先例这是允许的（段② 数据区 R22-23 而 anchor=A10，中间隔着段① 与 footer）。
- 全空列实测 6 个：`K L M N O P`，K/L 均在 max_col=L 内，**无需扩列**。
- 种子区 A 列是固定标签且被 `SUMPRODUCT` 当匹配键 ⇒ **A 列不可受管**（改标签会让取数静默归零）。

## 3. FC-10 逐列取证（不命中）

百分比格式仅 2 格，且都在 R15 审计说明区，不在数据区 R7~R10：

- `D15` 百分比 + 有公式 ⇒ mode=formula
- `E15` 百分比 + 无公式 ⇒ 但位于说明区，非受管范围

⇒ 数据区 R7~R10 **无 FC-10 命中**，无需 pct mask。

## 4. 数据验证

无（整表 0 条 DV）。

## 5. 与 spec 记录的差异

| spec design 记 | 实测 | 处置 |
|---|---|---|
| 表头 R6 | R5+R6 **两级**（A5:A6 / B5:E5 / F5:J5 三处合并） | 按实测声明两级表头 |
| 数据 R7-10、合计 R11、试算 R12、差异 R13 | 一致 ✅ | — |
| R7/R8 6 公式列、R9/R10 2 公式列 | 一致 ✅ | — |
| （未记）I 列语义在两区不同 | R7/R8 是 SUMPRODUCT，R9/R10 是 F+G+H | 补入拆区理由，两区 field_specs 独立 |
