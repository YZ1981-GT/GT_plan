# T03 · D2-3 受管区数裁决（实测反转 spec 裁决 E2）

**日期**：2026-09-26　**任务**：Task 3（Q4 红判据前置裁决）　**判定依据**：openpyxl 直读模板 + `useD2BadDebt.ts` 直读

## 结论：D2-3 是 **2 个物理受管区**，binding **1→3**，不是 spec 裁决 E2 说的「3 受管区 / binding 1→4」

## 实测冲突

| 侧 | 事实 | 出处 |
|---|---|---|
| 前端 store | **3 个键** `D2-bd-individual-rows` / `D2-bd-aging-rows` / `D2-bd-customer-rows` + 3 块 UI 表 | `useD2BadDebt.ts:64-68` `CATEGORY_KEYS` dict |
| 前端分类 | `category: 'individual' \| 'aging' \| 'customer-type'` 三值 | `useD2BadDebt.ts` `BadDebtRow` |
| Excel 模板 | **只有 2 个物理段**：①「按单项评估计提」小计行 12 / 数据 13-16；②「信用风险组合计提」小计行 17 / 数据 18-21 | `T01-d2-geometry-probe.json` |

## 为什么不能硬凑 3 受管区

模板段②「信用风险组合计提」是**单一物理数据区**（R18-21，`E17=SUM(E18:E21)`），不区分「账龄组合」vs「客户类型组合」。前端把它拆成 aging / customer-type 两个 store 键，纯属 **UI 分类需要**，模板里没有对应的独立物理承载区。

若照 spec 裁决 E2 强行声明 3 受管区，aging 区与 customer-type 区都要落在同一物理区 R18-21，两区的 UUID/row_identity 会在同一批物理行里**串区**——OO 回写时无法区分某行归 aging 还是 customer-type。这正是 D4-1 用不同 UUID 列（W/X）+ 不同物理段避免的问题，而 D2-3 段②根本没有第二个物理段可分。

## 裁决（照 D4-9 单 sheet 双区范式）

D2-3 声明 **2 个受管区**，与模板 2 个物理段一一对应：

| 受管区 table_key | 物理段 | 小计行 | 数据行 | UUID 列 | 承载前端分类 |
|---|---|---|---|---|---|
| `bad_debt_individual_rows` | 按单项评估计提 | 12 | 13-16 | O（AM 右侧首空列之一） | `individual` |
| `bad_debt_combined_rows` | 信用风险组合计提 | 17 | 18-21 | P | `aging` + `customer-type`（行内 `category` 字段区分） |

- footer 合计行 22（`=B12+B17`）→ `formula_mask` + footer 不入受管
- 审计说明 23 / 审计结论 27 在 footer 下 → HTML-only，不受管
- 公式列 `E`(=B+C+D) / `K`(=B+SUM(F:G)-SUM(H:J)) / `N`(=K+L+M) → `formula_mask`
- store：单 item？否 —— D2-3 前端是**三个独立 store 键**，不是 D4-9 的单 item 嵌套。故后端 merge 需把 combined 区的行按行内 `category` 回写到 `aging` / `customer-type` 两个 store 键；individual 区回写到 `individual` 键。三键**读兼容全部保留**。

binding：D2-2 ① + D2-3 ② = **3**（1→3）。

## 对 spec 的影响（复盘阶段修正）

spec 裁决 E2、需求 1.3/1.6、Task 3/6/8、design Property 4 全部按「3 受管区 / binding 1→4」写。实测证明模板只有 2 物理段，正确值是「2 受管区 / binding 1→3」。这是 spec 基于「前端 3 键」推断、未实测模板物理段数导致的偏差。复盘阶段将据本 evidence 修正 spec 三件套（与 spec 自己「实测优先、诚实边界」的纪律一致）。

保留的 spec 意图：三个 store 键的数据全部双向可见、下游 5 处消费方回写后正确重算——这些**不因受管区从 3 改 2 而减损**，combined 区回写按 category 分流回 aging/customer-type 两键即可满足。
