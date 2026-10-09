# F5-1 审定表：双区逐行公式集合实测（Task 21 证据）

取证脚本：`backend/scripts/analyze/_probe_f345_geometry.py F5 --sheets "营业务成本审定表F5-1" --header-rows 6,7,19 --data-range 8,29`
模板：`backend/wp_templates/F/F5 营业成本.xlsx`　sha256 `417e5ae7453528725f3ae5eb06f70d36269b089cd73a00884c835f4586267cb7`（只读，未改字节）

## 1. 几何

`营业务成本审定表F5-1` `visible` 60r × 14c（max_col = N）

| 行 | 角色 |
|---|---|
| R5 | 一级表头：`项目`(A5:A6) / `本期数`(B5:E5) / F5:I5 / J5:J6 |
| R6 | 二级表头：B 本期未审数 / C 账项调整 / D 重分类调整 / E 本期审定数 / F 上期未审数 / G 账项调整 / H 重分类调整 / I 上期审定数 |
| R7 | 区①标题 `主营业业成本：`（模板错字，见 §5） |
| **R8~R17** | **区①数据区（10 行）** |
| R18 | 区①小计 `=SUM(B8:B17)`，覆盖 B~I |
| R19 | 区②标题 `其他业务成本` |
| **R20~R25** | **区②数据区（6 行）** |
| R26 | 区②小计 `=SUM(B20:B25)`，覆盖 B~I |
| R27 | 合计 `=B26+B18`，覆盖 B~I |
| R28 | 试算平衡表数 |
| R29 | 差异数：仅 `E29=E27-E28`、`I29=I27-I28` |
| R30 起 | 审计说明 |

合并区 6 个：`A5:A6` `A1:J1` `J5:J6` `B5:E5` `A2:J2` `F5:I5`

## 2. 🔴 区① 主营业务成本（R8~R17）—— **不可受管**（不是"选择 HTML-only"）

每行 **9 列全是公式，含 A 列项目名**：

```
A8 = '主营业务成本月度明细表F5-2'!A11      ← 项目名也是公式
B8 = '主营业务成本月度明细表F5-2'!N11
C8 = '主营业务成本月度明细表F5-2'!O11
D8 = '主营业务成本月度明细表F5-2'!P11
E8 = B8+C8+D8
F8 = '主营业务成本月度明细表F5-2'!R11
G8 = '主营业务成本月度明细表F5-2'!S11
H8 = '主营业务成本月度明细表F5-2'!T11
I8 = F8+G8+H8
```

R9~R17 逐行同构，只是引用行号 A12→A20 递增。

⇒ 区① **零可编辑格**（A~I 九列全被公式占满，J 列空但属索引列）。spec 原记「主营区 HTML-only」是结论正确但理由不足：实测给出的是**更强的判定** —— 该区没有任何用户输入点，OO 侧写入只会被模板公式覆盖，**根本不该进受管清单**（受管它等于登记一个永远为只读投影的区）。

## 3. ✅ 区② 其他业务成本（R20~R25）—— 唯一可受管的区

每行**只 2 列公式**，六行完全同构：

```
E20 = B20+C20+D20
I20 = F20+G20+H20
```

⇒ A（科目名）/B/C/D/F/G/H/J 全可编辑，是真正的可编辑行表。

| 区 | sheet_key | table_key | 行范围 | 行数 | 公式列（只读） | 可编辑列 | uuid_col |
|---|---|---|---|---|---|---|---|
| 其他业务区 | `f51-managed` | `adjudication_other_rows` | R20~R25 | 6 | E,I | A,B,C,D,F,G,H,J | **K** |
| 主营区 | — | — | R8~R17 | 10 | 全 A~I | **无** | ❌ 不可受管 |

- footer 锚行 R26 `小计`，`footer_carries_total_formula=True`（B26~I26 全是 `SUM(B20:B25)` 形态）。
- 只声明一个区 ⇒ 无兄弟区 uuid_col 冲突。
- 表头取 `header_group_row=5, header_leaf_row=6`（契约 anchor `A5`）。区② 自己**没有**列表头行
  （R19 只有 A 列标题文字「其他业务成本」），故复用表级两级表头。anchor 与受管数据区之间隔着
  区①（R8~R17）与小计 R18 —— 按 D3-4 双区先例（段② 数据区 R22-23 而 anchor=A10）这是允许的。

## 3.1 前端 store 实测（FC-4：按值 grep，不推演）

`audit-platform/frontend/src/components/workpaper/composables/useF5Adjudication.ts`：

```ts
const OTHER_STORAGE_KEY = 'F5-1-adj-other-rows'     // ← store_item_id
interface StoredF5AdjRow {
  rowKey: string            // ← 🔴 行身份是 rowKey（不是 id / rowId）
  label: string             // → A 列（项目）
  isFixed: boolean          // → store-only（模板无列）
  currentUnadjusted: number // → B 本期未审数
  currentAje: number        // → C 账项调整
  currentRje: number        // → D 重分类调整
  priorUnadjusted: number   // → F 上期未审数
  priorAje: number          // → G 账项调整
  priorRje: number          // → H 重分类调整
  indexRef: string          // → J 索引
}
```

- 主营区 store key 是 `F5-1-adj-main-rows`（同文件），**不进受管清单**（§2 已证零可编辑格）。
- 🔴 行身份 `rowKey` 与 F5-2/3/5/8 四张的 `id` **不同** —— 同一册内两种行身份键，必须按值取。
- **无 BP-7**：载入路径 `storedOtherRows` 把 `safeParseRows` 的结果原样透传，不按下标重算
  `rowKey`；`addRow` 用 `${group}-${Date.now()}` 生成一次即持久化（`Date.now()` 不是行下标）。
  与 F5-2/3/5 的 `m-${Date.now()}-${i}`（`i` 是 `map` 下标，每次载入重算）**不同型**。
- 边界（登记不修）：历史行若 `rowKey` 缺失，框架层 `store_row_identity` 会 fail-closed 抛
  `RowTableStorePayloadError`（绝不退回数组下标）——这是期望行为，seed 阶段须保证 rowKey 齐备。

## 4. 🔴 修正 spec：全空列从 K 起，不是 J

实测列占用：

```
A:23  B:15  C:14  D:16  E:21  F:15  G:16  H:14  I:23  J:2  K:0  L:0  M:0  N:0  O:0  P:0  Q:0  R:0
全空列: ['K','L','M','N','O','P','Q','R']
```

spec design 记「J~N 全空」**有误**：`J` 列有 2 格非空（`J5:J6` 合并的索引表头），`J3` 还有 `=底稿目录!F4`。真正的全空列**从 K 起**。

⇒ uuid_col 取 **K**（K 列 fmt 纯 `General` 且 0 值，最干净；L 列虽空但带数字格式）。K 在 max_col=N 内，**无需扩列**。

## 5. FC-10 与 DV

- 百分比格式格：**整表 0 个** ⇒ FC-10 不命中，无需 pct mask。
- 数据验证：**整表 0 条**。

## 6. 模板错字（第 2 处，登记不改字节）

`A7 = '主营业业成本：'` —— 应为「主营业务成本：」。与 spec Task 2 已登记的 F5 其他错字同批，走覆盖层处置（`backend/wp_templates/` 运行时只读 + sha 冻结）。

## 7. 与 spec 记录的差异汇总

| spec design 记 | 实测 | 处置 |
|---|---|---|
| 主营区 R8-17 HTML-only | 一致，但理由更强：9 列全公式、零可编辑格 ⇒ 不可受管 | 证据补入拆区理由 |
| 其他业务区 R20-25 | 一致 ✅ | 按实测声明 |
| 小计 R18 / R26、合计 R27、试算 R28、差异 R29 | 一致 ✅ | — |
| 「J-N 全空」⇒ uuid_col 可取 J | **J 有值**，全空从 K 起 | uuid_col 改 **K** |
| R7 标题错字 | 确认 `主营业业成本：` | 登记覆盖层 |
