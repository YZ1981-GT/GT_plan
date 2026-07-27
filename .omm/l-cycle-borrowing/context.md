# 上下文：L 循环特有机制

通用机制见 `.omm/d-cycle-sales/context.md` 与 `shared-runtime/`。本文只写 L 特有部分。

## 1. 科目码在各 `useL{n}FormData.ts`

L1 2001（写在手册/组件，无独立常量文件）、L2 `'2231'`、L3 `'2501'`、L4 `ACCOUNT_CODE='2502'`、
L5 `ACCOUNT_CODE_PAYABLE='2701'` + `ACCOUNT_CODE_UNRECOGNIZED='2702'`、L6 `'2601'`、L7 `'2801'`、
L8 `'6603'`（损益取发生额）。回写 `PUT /trial-balance/writeback` + `eventBus.emit('substantive:adjudicated')`。

## 2. 审定表双期结构是 L 循环的核心（曾大批做错）

**正确 = 期初/期末双期**（各未审/账项调整/重分类/审定）。历史上 L1/L2/L3/L4/L5 审定表都曾误做成
**单期 roll-forward**（期初/贷/借/期末/单列未审/AJE/RJE/审定），需按源模板重建为双期。
带一年内到期的（L3/L4/L5）加"减一年内到期 → 披露审定数"列（披露审定 = 审定 − 一年内到期，进非流动列报）。

**判定法**：审定表 X-1 若源模板有"期初数/期末数各(未审/账项调整/重分类/审定)"分组表头即双期结构，
单期 roll-forward 是误用。L6/L7 本就是两期动态行结构（正确）；L8 财务费用损益类结构不同不适用。

## 3. 审定表 hydrate 是 L 循环的高频缺陷

`useL{n}Adjudication` 必须从 `formData.allResponses` **hydrate**（同步 + async watch 二次，一次性 guard），
且 `updateRow` / update 函数必须 persist（不能只 mutate reactive 等 explicit save）。
历史上 L1/L2/L4/L5 都出现过"编辑不落库 / 刷新丢数据 / 只存计算列不存可编辑输入"。

## 4. 检查表凭证级（useL{n}VoucherCheck）

L1-6 合同检查 / L3-9 检查表 / L1-9 检查表等是凭证级：记账凭证行（日期/凭证号/业务内容/对方科目/借/贷）+
核对内容①~⑤ + 索引/异常/备注 + 检查比例（本期发生额来自 Lx-2 的 Σ计提/Σ支付）。
历史上 L2-4/L3-9 曾误做成合规 radio 清单，应重建为凭证级。

## 5. 动态行表存储：JSON-array 单键 + hydrate

Lx-2 明细 / 检查表的 rows 必须 **JSON-array 存单键**（如 `L3-L3-2-rows`）+ 从 allResponses hydrate，
不能用 flat per-field keys（`L3-det-{n}-{field}`）+ 组件本地 `ref([])` 无 hydration（= 刷新数据丢失，
get_diagnostics/Vite 200 查不出，仅刷新/Playwright 能抓）。内部字段 ↔ 后端字段用 toBackend/fromBackend 映射保模板零改。

## 6. 导入导出 round-trip

后端 `_SHEET_ITEM_ID` 必须与前端持久化键一致（`L3-L3-2-rows` 非 `L3-detail-rows`），
`_FIELD_MAPS` 值 = 前端 JSON 字段名，`_NUMERIC_FIELDS` 同名；
`INSERT checklist_responses` 必须带 `project_id`（NOT NULL → 导入恒 500，L3 踩过）。

## 7. 利息测算联动（365 天制）

L1-5 利息测算：应计利息 = 本金 × 年利率 × 计息天数 / 365，联动 **L2 应付利息** + **L8 财务费用**。
带息票据（F3-4）/ 长期借款 / 债券利息也汇入 L2；资本化部分进 H2 在建工程（CAS17）。

## 8. 一年内到期重分类

长期借款（L3）/ 应付债券（L4）/ 长期应付款（L5）的一年内到期部分 → 重分类（RJE）作流动负债列报；
审定表"减一年内到期 → 披露审定数"列即体现此重分类（披露审定 = 审定 − 一年内到期）。
逾期银行承兑（F3）→ 短期借款 2001/L1 重分类。

## 9. 「从集中登记带入调整」

L1 用 `useAdjudicationAdjustmentPull`（`subjectPrefix:'2001'` / `direction:'credit'` 负债贷方净额 = 贷 − 借），
**双期审定表带入 target 期末列**（endAje/endRje）；L 其余科目同范式。
