# 四表取数入口缺口清册（Task 1 产物 · 结构性推导 · 只读）

> **唯一真源**：本清册与同目录 `gap-inventory.json` 是 Task 4/4.1/5/6/7/8/9 的唯一输入（Requirement 1.5）。
> **漂移阻塞**：下游任务实现前必须重算 `gap-inventory.json > source_snapshot` 的 sha256 并比对 `aggregate_digest`；任一漂移即阻塞实现、重新推导清册（Requirement 1.6）。
> 覆盖 Requirements 1.1 / 1.2 / 1.3 / 1.4 / 1.5 / 1.6 / 5.4。

## 推导方法（禁 grep 按钮文字 · Requirement 1.1）

- **宿主全集**：从 `htmlRendererRegistry` 桶（`registry/entries/{core,forms,reports,programs,confirmations,specialized}.ts`）的显式 `HtmlRendererEntry[]` 数组推导 —— 数组本身即成员集，无 startsWith 分类器。`wp_code → componentType` 经 `backend/app/data/wp_code_overrides.json`（`_WP_CODE_OVERRIDE`）。**未**用 grep 按钮文案/写死页数枚举候选。
- **后端端点全集**：从 `backend/app/security/wp_bound_entry_coverage.json` 按 `route == /api/workpapers/{wp_id}/{x}/import-aux-balance` 匹配，实得 **8** 个：d1/d3/d5/d6/d7/f1/g7/k1。**无** d2 路由。
- **三元组判据（Requirement 1.2）**：某明细表"具备四表库取数能力"当且仅当同时满足
  - **T1** 报表行可解析科目码前缀（`ReportLineAccountSpec` / `report_line_accounts.resolve_report_line_accounts`）
  - **T2** 该科目在 `tb_aux_balance` 的往来单位/维度粒度有真实数据
  - **T3** 明细表有可承载行结构（store `item_id` + 字段）
- **按钮列**：仅在宿主已推导出后，读 `.vue` toolbar 填"前端按钮有/无"列，**不**用于判定候选资格。

## 缺口类型（Requirement 1.3）

| 类型 | 定义 | 处置 |
|---|---|---|
| G-A | 后端端点有 + 前端按钮无 | 只补前端入口 |
| G-B | 后端端点无 + 具备取数能力 | 端点（走共享件）+ 按钮都补 |
| G-C | 两侧都有但违铁律 | 迁移到共享件 |
| G-D | 不适合取数 | 只登记理由，不动代码 |

## 五列清册

| wp_code | 宿主组件 | store item_id | 现有入口（端点/按钮/AutoSeed） | gap 类型 |
|---|---|---|---|---|
| D1 | D1TabDetailCustomer.vue (`d1-notes-receivable`) | D1-2 detail rows | ✅ / ✅ / ✗ | 合规基线 |
| F1 | F1TabDetail.vue (`f1-prepayment`) | `F1-det-rows` | ✅ / ✅ / ✅ | 合规基线（范式源） |
| G7 | G7TabDetail.vue (`g7-long-term-equity-main`) | G7 detail rows | ✅ / ✅ / ✗ | 合规基线 |
| **K1** | GtK1OtherReceivables 明细 (`k1-other-receivables`) | `K1-2-detail-rows` | ✅ / **✗** / ✅ | **G-A** |
| **D2** | D2TabDetail.vue (`d2-accounts-receivable`) | D2 detail rows | **✗** / ✅ / ✗ | **G-C** |
| **D3** | D3TabDetail.vue (`d3-prepaid-accounts`) | D3-2 detail rows | ✅ / ✅ / ✗ | **G-C** |
| **D5** | D5TabDetail.vue (`d5-receivables-financing`) | D5-2 detail rows | ✅ / ✅ / ✗ | **G-C** |
| **D6** | D6TabDetail.vue (`d6-contract-assets`) | D6-2 detail rows | ✅ / ✅ / ✗ | **G-C** |
| **D7** | D7TabDetail.vue (`d7-contract-liabilities`) | D7-2 detail rows | ✅ / ✅ / ✗ | **G-C** |

**汇总**：G-A = {K1}（1）· G-B = {}（0）· G-C = {D2, D3, D5, D6, D7}（5）· G-D = {}（0）· 合规基线 = {D1, F1, G7}。
G-B 数 = 0 ⇒ DEC-5 拆批（>6）不适用。

## DEC-2 核实结论（D2 实际端点归属）

`useD2Detail.ts` 的 `importFromAuxBalance(projectId)` **不打**任何 `d2/import-aux-balance` 端点。它调用**通用读端点**

```
GET /api/projects/{project_id}/ledger/aux-balance-detail?account_code=1122&dim_type=客户&year={Y}
```

（`ledger_penetration.get_aux_balance_detail`），然后在 **TypeScript 前端**按 `aux_name` **客户端聚合**（等于第 5 份归集逻辑）。

- 该读端点**本身合规**：`get_active_filter` + `aux_type == dim_type` + `account_code LIKE 前缀`。
- 违铁律的是 **D2 前端**：③ 硬编码 `1122`（而 `d_account_resolver.py` 已有 `D2_SPEC(BS-006)` 可解析）；且**绕过**共享件 `aggregate_aux_by_name` 管道。

⇒ **D2 归入 G-C**：Task 4 须新建 `POST /api/workpapers/{wp_id}/d2/import-aux-balance`（走共享件），科目前缀由 `D2_SPEC(BS-006)` 解析，删除客户端聚合。注意 D2 无既有 `d2/import-aux-balance` 端点 ⇒ 其迁移是"G-C 带端点新建"，pre/post 金额对照须单独记（无既有双算基线可冻结）。

## 科目解析能力实证（T1）

`backend/app/services/d_cycle_extraction/d_account_resolver.py` 已声明为 `ReportLineAccountSpec`：
`D2_SPEC(BS-006, 兜底 1122)` · `D3_SPEC(BS-046, 兜底 2203)` · `D5_SPEC(BS-007, 兜底 1124)` · `D6_SPEC(BS-011, 兜底 1141)` · `D7_SPEC(BS-047, 兜底 2205)`。
`K1_ACCOUNT_SPEC(BS-009, 兜底 1221)` · `F1_REPORT_LINE_SPEC(BS-008, 兜底 1123)`。
迁移只需**替换调用 + 补 year 参数 + 科目码改解析**，报表映射真源已就位。

## blocked / deferred（Requirement 5.4 + DEC-4）

- **实证**：`use{D1,D2,D3,D5,D6,D7,F1}Detail.ts` + `useK1DetailAutoSeed.ts` 的明细行持久化子集**均无** `source_kind`/`source_dataset_id`。唯一带 `sourceKind` 的是 `useK1Adjustment.ts` —— 那是 K1 **调整分录**项（另一个 store item），不是本 spec 触碰的明细行。
- **决定**：按 design DEC-4，本 spec **不**给明细行加统一来源元数据（会动 5+ 循环 store 形态与契约 digest）。据 Requirement 5.4，全部 G-A/G-B/G-C 行**不携带**统一 `source_kind`/`source_dataset_id`，该能力在此登记为 **deferred**（不阻塞取数本身）。Task 9 证据仍应从端点响应上下文记录 `source_dataset_id`（即便不落库）。
- **升级条件**：若 Task 4/5/7 发现某目标循环连取数行本身都无法承载（T3 缺失），该循环须标 blocked/deferred 并**从最终完成数排除**。本清册所列宿主均满足 T3，故无一因此阻塞。

## G-D 登记（宁缺勿造 · Requirement 1.4）

本清册在 aux 明细表族内**无** G-D 条目。spec 范围（见 design）是 aux 往来单位/维度明细表宿主；此族外的宿主（纯序时账 P&L 循环、K0 函证聚合、报表/概要类组件）**不纳入候选** —— 它们对 aux 粒度不满足 T2/T3（数据在 `tb_ledger` 而非 `tb_aux_balance`，或无逐户行结构）。显式登记空 G-D 以示未强凑入口。

## Source Digest（Requirement 1.6 冻结）

见 `gap-inventory.json > source_snapshot`。`aggregate_digest = sha256(拼接每文件 "sha256:size:relpath\n")`：

```
sha256:da5aeae67f2edbb333d6449061f18c09e13de59d813bcda8c52f3a176c0b3651
```

被跟踪文件：`forms.ts` · `specialized.ts` · `wp_code_overrides.json` · `wp_bound_entry_coverage.json` · `aux_aggregation.py`。
