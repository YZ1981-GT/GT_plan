# D4-1..36 双向回写逐张现状清册

> **基线日期**：2026-09-19（表格/统计基线）
> **最近更新**：2026-09-20（D4-1 同 sheet 双区双向落地 + 契约集合 15→16，见「增量更新」段）
> **目的**：为"逐张落地 D4 双向回写 + Playwright 验证"提供准确的起点清册。
> **判据三维**（缺一不可，对齐主控文档 §6.4 `HOST-CONSUMES-UNIFIED-PATH`）：
> 1. **owner spec** 进度（`.kiro/specs/*`）
> 2. **后端契约**：`d4.revenue_detail.json` 是否声明该 sheet（`{code}-managed`）+ provider 是否实现
> 3. **前端宿主**：组件在线编辑走 `useWorkpaperSyncBridge`（统一桥＝真双向）还是 legacy `GtOnlyOfficeSheet`（未接桥＝假双向/单向）
>
> **只有三维全绿才算"双向已落地"**；后端有契约但前端仍 legacy = "半接入"（后端可 materialize，但宿主没消费统一路径，OO→HTML 不成立）。

## 平台底座状态（2026-09-19 实测）

- **契约漂移 500 已修复并入库**（commit `c2e57f643` + 我的 provision/rematerialize）：`xlsx/gt-d4-operating-revenue` entry 当前 representation generation 49，bundle `665eed8a`（含 D4-15/16 Table）= desired bundle，`d43_rematerialize --check` 返回 `already_on_desired_bundle`。store-projection 恢复 200（真实后端实测 field_count=330/row_count=169）。
- **`useWpDetailGuard` CanceledError 假失败屏已修**（commit `79cf1b52e`）：切底稿竞态不再弹"加载底稿失败/canceled"全页屏。
- D4-2 DB 侧铁证：12 个 applied oo_to_html application + 12 个 source=onlyoffice content_version（双向真实往返）。

## 🔴 阻塞（2026-09-20 实测，影响整个 gt-d4-operating-revenue entry 发布）

- **D4-9 provider 对真实数据抛 StorePayloadError，卡死整个 entry 的 live rematerialize**。`phase5_d4_customer_structure.build_d49_store_projection` 的 `_parse_store_payload` 期望 `D4-9-data` 为 `{current, prior}` dict，但真实项目（首汽租车等）该 store 是 **list** 形态 → rematerialize 全 entry 事务回滚，卡在 gen54。D4-9 已入 HEAD 契约（21 sheets）但**从未 live 发布过**（gen54 = D4-6 的 20-sheet bundle，不含 D4-9）。
- **连带影响**：批次B 的 D4-17 provider 已完成 + 单测通过，但因共享同一 entry、desired bundle 含 D4-9，**无法 live 发布**（flag `_INCLUDE_D417_CUTOFF_SHEET` 暂关）。任何后续该 entry 的从零 sheet 发布都被 D4-9 挡住。
- **解除条件**：D4-9 owner 修 `_parse_store_payload` 兼容 list 形态（或前端 D4-9-data 统一为 dict）+ live rematerialize 通过。修复前该 entry 的发布管线冻结在 gen54。属主控 §10.3 并发 owner 文件，不擅改。

## 增量更新（2026-09-20，D4-1 落地）

> 基线段（上方）保持 2026-09-19 快照不改；本段记录此后的真实推进，供逐张清册与统计段引用。

- **D4-1 营业收入审定表：三维全绿（真双向）已落地**（commit `663c3f019`「feat(d4-1)：营业收入审定表同 sheet 双区双向回写 + 4 处共享内核缺口修复」）。owner spec `d4-1-adjudication-bidirectional-writeback-and-formula-io` = **10/12**（Task 1~10 全 `[x]`，仅 Task 11 e2e / Task 12 收口标 `[~]`，卡 start-dev.bat + 真实 OO 环境）。
- **裁决从 static-cell 改判为「同 sheet 双区动态行 UUID」**（重要更正，见文末几何核定段）：provider `phase5_d4_adjudication_sheet.py` 实现两张 row table —— 主营 `adjudication_main_rows`（R8 起 / UUID 列 W / TID `D41MAIN`）+ 其他 `adjudication_other_rows`（R14 起 / UUID 列 X / TID `D41OTHER`），共享 sheet_key `d41-managed`。清册 2026-09-19 版「D4-1 走 static-cell 模式，非行 UUID 模式」的裁决**已作废**。
- **契约 sheet 集合 15 → 16**：`d4.revenue_detail.json` 现声明 16 张（新增 `d41-managed`）。实测集合 = d42/d43/d45/d421/d422/d423/d424/d435/**d41**/d4-29/d4-25/d4-26/d4-27/d4-28/d4-15/d4-16。
- **发布链已跑全、DB 判据 GREEN**：live-PG `d43_rematerialize_dual_sheet.py --apply` 成功（generation 50→51、revision 75），entry 当前 representation `definition_bundle_sha256` = `af32bfbde3f1cff8…`（= 含 D4-1 的 desired bundle，此前卡在 665eed8a…gen50）；store-projection 含 D4-1 且不打挂 D4-2/3/25~28。
- **4 处共享内核缺口全部落地**（同 sheet 双区所需，主控 §5.3 共享锁下 GENERALIZE 不回归单动态表）：
  1. `excel_instrumentation._attach_table_part` XML 合并（往已有 `<tableParts>` 块内追加 `<tablePart>` 更新 count，不再畸形双块）——**这条同时解除了 D4-9 owner spec 的 Task 1 阻塞**（D4-9 现 1/15）。
  2. `phase5_d4_revenue_detail._attach_sibling_bindings` sibling binding 对齐（放弃 1 spec↔1 sheet 位置 zip，支持 2 spec 共享同 managed_sheet）。
  3. `excel_extract.managed_tables_of` extract 侧解析（一 sheet N 张动态表各自 binding、逐表反读合并；原硬抛 `ManagedRegionResolutionError` → 跳过兄弟表）。
  4. `excel_materialize` footer per-region 解析（按 REGION/table_name 经平行清册取 `GT_FOOTER_ROW_{TID}` + `_find_marker_row` 加 `min_row` 区分同名 `小计` marker；原 sheet_key→单 TID 假设在一 sheet N region 时回退裸键误判 → `FooterAnchorDriftError`）。
- **前端接桥 + 宿主登记已入库**：`D4TabAdjudication.vue` 接 `useWorkpaperSyncBridge`（entryId=`xlsx/gt-d4-operating-revenue`、sheetKey=`d41-managed`）+ `WorkpaperSyncEditorHost`；宿主 `GtD4OperatingRevenue.vue` 的 `isD4DedicatedSyncSheet` 已含 `'D4-1'`。前端守卫 `d4AdjudicationSyncHostWiring.spec.ts` + 后端守卫/变异 `test_d4_1_adjudication_*` / `mutate_d4_1_adjudication_guards.py` 全绿。
- **仍缺**：D4-1 的 e2e 证据 JSON（`docs/operations/evidence/d4-bidirectional-acceptance/D4-1.json`）尚未产出（Task 11 `[~]`，待真实 OO 环境）。目前证据目录仅 11 张（D4-2/3/5/15/16/25/26/27/28/29/35）。

## 逐张清册（分母 = 36）

图例：✅=三维全绿(真双向) · 🟡=后端接入但前端 legacy(半接入,需改前端接桥) · 🔵=owner spec 待做/从零 · ⬜=裁决为 single_html/N/A

| # | wp_code | 名称 | owner spec | 后端契约 | 前端组件 | 前端接桥? | 综合 |
|---|---------|------|-----------|---------|---------|----------|------|
| 1 | D4-1 | 营业收入审定表 | d4-1-adjudication (10/12) | ✅ d41-managed(同sheet双区) | D4TabAdjudication | ✅ | ✅ (2026-09-20落地,e2e证据待补) |
| 2 | D4-2 | 主营业务收入明细 | d4-revenue-matrix (11/13) | ✅ d42-managed | 宿主走桥 | ✅ | ✅ |
| 3 | D4-3 | 其他业务收入明细 | d-cycle-expansion (9/9) | ✅ d43-managed | D4TabOtherRevenue(宿主走桥) | ✅ | ✅ |
| 4 | D4-4 | 调整分录汇总 | gap-closure (0/5) | ❌ | — | — | ⬜ 已裁 single_html(无行身份列) |
| 5 | D4-5 | 会计政策检查 | d-cycle-expansion | ✅ d45-managed | D4TabPolicyCheck | ✅ | ✅ |
| 6 | D4-6 | 重要指标分析 | d-cycle-expansion | ✅ d46-managed(批次B从零) | D4TabIndicator | ✅ | ✅ (批次B 2026-09-20落地,真OO待验) |
| 7 | D4-7 | 毛利率分析 | d-cycle-expansion | ❌ (前端有 d47-managed 键但契约未声明) | D4TabMarginMonthly | legacy | 🔵 从零 |
| 8 | D4-8 | 重要产品毛利分析 | gap-closure (0/5) | ❌ | — | — | 🔵 gap待做 |
| 9 | D4-9 | 重要客户结构分析 | d4-9-customer (1/15) | ❌ 无 d49 契约 | D4TabCustomerStructure | legacy | 🔵 从零(Task1双区instrumentation已由D4-1借道落地,余待做) |
| 10 | D4-10 | 重要客户销售价格 | d4-price-analysis (9/10) | ❌ | D4TabCustomerPrice | legacy | 🔵 从零(price spec 已做上游取数联动,未做双向) |
| 11 | D4-11 | 产品销售价格分析 | d4-price-analysis (9/10) | ❌ | D4TabProductPrice | legacy | 🔵 从零(同上) |
| 12 | D4-12 | 合同检查 | gap-closure (0/5) | ❌ | — | — | 🔵 gap待做 |
| 13 | D4-13 | ERP账面核对 | d4-inspection (9/16) | ❌ | — | — | ⬜ evidence裁 N/A(纯叙述文本表) |
| 14 | D4-14 | 发生检查 | d4-inspection (9/16) | ❌ | D4TabOccurrence | legacy | 🔵 从零(32列七维嵌套,风险高) |
| 15 | D4-15 | 完整性检查 | d4-inspection (9/16, B1/B2做实) | ✅ d4-15-managed | D4TabCompleteness | ✅ | ✅ |
| 16 | D4-16 | 出口口岸核对 | d4-inspection (9/16, B1/B2做实) | ✅ d4-16-managed | D4TabExport | ✅ | ✅ |
| 17 | D4-17 | 截止测试(账到单据) | d4-cutoff-return (3/13) | 🟡 provider就绪(flag暂关) | D4TabCutoffForward | ✅ | 🟡 代码+单测就绪,契约门被D4-9阻塞 |
| 18 | D4-18 | 截止测试(单据到账) | d4-cutoff-return (3/13) | ❌ | D4TabCutoffBackward | legacy | 🔵 从零(BB1-3 blocked) |
| 19 | D4-19 | 销售折扣与折让 | d4-cutoff-return (3/13) | ❌ | D4TabDiscount | legacy | 🔵 从零(BB1-3 blocked) |
| 20 | D4-20 | 销售退货检查 | d4-cutoff-return (3/13) | ❌ | D4TabReturn | legacy | 🔵 从零(BB1-3 blocked) |
| 21 | D4-21 | 关联方销售/价格 | d4-21-24 (10/11) | ✅ d421-managed | D4TabRelatedPrice | ✅ | ✅ (批次A 2026-09-20接桥,真OO待验) |
| 22 | D4-22 | IPO重要指标分析 | d4-21-24 (10/11) | ✅ d422-managed | D4TabIpoIndicator | ✅ | ✅ (批次A接桥,真OO待验) |
| 23 | D4-23 | 收入与开票比较 | d4-21-24 (10/11) | ✅ d423-managed | D4TabInvoiceCompare | ✅ | ✅ (批次A接桥,真OO待验) |
| 24 | D4-24 | 第三方回款检查 | d4-21-24 (10/11) | ✅ d424-managed | D4TabThirdParty | ✅ | ✅ (批次A接桥,真OO待验) |
| 25 | D4-25 | IPO经销商检查 | ipo-checklist | ✅ d4-25-managed | D4TabDealer | ✅ | ✅ |
| 26 | D4-26 | 境外销售收入检查 | ipo-checklist | ✅ d4-26-managed | D4TabOverseas | ✅ | ✅ |
| 27 | D4-27 | 识别未披露关联方 | ipo-checklist | ✅ d4-27-managed | D4TabUndisclosedRp | ✅ | ✅ |
| 28 | D4-28 | 客户信息核查清单 | ipo-checklist | ✅ d4-28-managed | D4TabCustomerChecklist | ✅ | ✅ |
| 29 | D4-29 | 客户信息检查表 | ipo-fraud | ✅ d4-29-managed | D4TabCustomerDetail | ✅ | ✅ |
| 30 | D4-30 | 客户访谈记录汇总 | ipo-fraud (6/11) | ✅ d4-30-managed(批次A-5开门) | D4TabInterviewSummary | ✅ | ✅ (批次A-5 2026-09-20,真OO待验) |
| 31 | D4-31 | 客户访谈记录 | ipo-fraud (6/11) | ✅ d4-31-managed(singleton) | D4TabInterviewDetail | ✅ | ✅ (批次A-5,真OO待验+singleton边界) |
| 32 | D4-32 | 资金流水检查 | ipo-fraud (6/11) | ✅ d4-32-managed | D4TabFundFlow | ✅ | ✅ (批次A-5,真OO待验) |
| 33 | D4-33 | 其他业务毛利率分析 | d4-33-36 (0/42) | ❌ 契约无 d433 | D4TabOtherMargin | **legacy** | 🔵 从零 |
| 34 | D4-34 | 其他业务收入合同测算 | d4-33-36 | ❌ | D4TabOtherContract | **legacy** | 🔵 从零 |
| 35 | D4-35 | 其他业务收入检查 | d4-33-36 | ✅ d435-managed | D4TabOtherCheck | ✅ | ✅ |
| 36 | D4-36 | 其他业务收入截止测试 | d4-33-36 | ❌ | D4TabOtherCutoff | **legacy** | 🔵 从零 |

## 统计（2026-09-20 批次A/A-5 后，契约 sheet_key 集合 **19 张**：d41/d42/d43/d45/d421/d422/d423/d424/d435/d4-29/d4-25/d4-26/d4-27/d4-28/d4-15/d4-16/**d4-30/d4-31/d4-32**）

> 🔴 **重要口径**：下方「✅」是**三维代码全绿（REQUEST_PATH 级）**——后端契约 + 前端接桥 + 宿主登记齐全。但**没有一张到主控 §6.4 的 `ONLYOFFICE_VERIFIED`**（需真实 OO 往返产生 `working_paper_content_application` state=applied + operation 终态 + OO 侧 content version，见 §9.5）。真 OO 验证是 env 门（start-dev.bat 全栈 + OO 容器），列为批次C。

- ✅ 三维代码全绿(REQUEST_PATH)：**20 张** — D4-1/2/3/5/**6**/15/16/21/22/23/24/25/26/27/28/29/30/31/32/35
  - D4-21/22/23/24（批次A）+ D4-30/31/32（批次A-5）+ **D4-6（批次B 从零第一张，provider phase5_d4_indicator_sheet，gen54）** 为 2026-09-20 新接桥/开门/落地；余 12 张此前已接桥
- 🔵 owner spec 待做/从零(后端无契约 + 前端仍 legacy)：**14 张** — D4-7/8/9/10/11/12/14/17/18/19/20/33/34/36
- ⬜ 裁决 single_html/N/A：**2 张** — D4-4/D4-13

> 校验：20 + 14 + 2 = 36 ✓（🟡 半接入类已清零）
> 契约集合现 **20 张**（+d46-managed）；entry `xlsx/gt-d4-operating-revenue` 当前 representation gen54。
> 注：D4-6/7 前端虽已在宿主 `D4_SHEET_KEY_BY_CODE` 预留 `d46/d47-managed` 键，但契约 sheet_key 集合中**无**对应项且组件未接桥，故仍归 🔵 从零。D4-9/10/11/14/33/34/36 经 grep 实证前端组件均未 import `useWorkpaperSyncBridge`（仍 legacy），契约集合中也无对应项。

## 逐张推进优先级（建议，2026-09-20 修订）

1. **补齐 e2e 证据**：已做实 12 张（✅）中 D4-1 缺 e2e 证据 JSON（Task 11 `[~]`）；其余 11 张已有证据。待 start-dev.bat + 真实 OO 环境跑 `d4-bidirectional-acceptance.spec.ts` 全量确认真双向可用。
2. **修半接入的 7 张**（🟡）：前端从 legacy `GtOnlyOfficeSheet` 改为 `useWorkpaperSyncBridge`（D4-21/22/23/24）；D4-30/31/32 需后端开 `_INCLUDE_IPO_INTERVIEW_SHEETS` 并解决 D4-31 几何 — 每张改完 Playwright 验证。
3. **做从零的 15 张**（🔵）：按 owner spec 实现 provider + 契约 + 前端接桥 + Playwright — 工作量最大。**D4-9 优先**（Task 1 双区 instrumentation 已由 D4-1 借道落地，内核已就绪；且 D4-9 是 D4-1 双区模型的原始蓝本 owner）。
4. **D4-4/D4-13** 保持裁决，不做单元格双向。

## 关键教训（写入本清册以防再犯）

- **"契约里有 sheet" ≠ "双向已落地"**：D4-21/22/23/24 后端契约齐全（d4-21-24 spec 标 11/12），但前端在线编辑仍是 legacy `GtOnlyOfficeSheet`，OO→HTML 统一路径未消费。必须三维全绿。
- **前后端可能反向不一致**：D4-30/31/32 前端已接桥（sheetKey d4-30/31/32-managed），但后端 `_INCLUDE_IPO_INTERVIEW_SHEETS=False` 契约里根本没这些 sheet — 前端调 materialize 会因 sheet 未在契约而失败。
- **半成品接入会打挂整个 entry**：D4-15/16 曾因契约声明但 representation 未 rematerialize，导致整个 `gt-d4-operating-revenue` entry（连累 D4-2/3/25~28）store-projection 全线 500。改契约后必须跑 provision + rematerialize 发布链。
- **裁决 static-cell vs 动态行必须实测模板行为，不能只看当前数据区行数**：D4-1 清册初判 static-cell（因看到 R8-11/R14-17 只 4 行），但模板数据区实为**可扩动态行**，且前端早已用 `D4-1-rows` 动态行模型 —— 硬套 static 会与前端模型对不齐。裁决动态/静态要看「业务上能否增删行」，不是「当前占几行」。
- **同 sheet 双区双向 = 4 处共享内核缺口，不是加个 sheet 那么简单**（D4-1 实测）：`_attach_table_part` XML 合并 / sibling binding 对齐 / `excel_extract` 一 sheet N 表逐 binding 反读 / `excel_materialize` footer per-region 解析（同名 `小计` marker 靠 `min_row` 区分、`GT_FOOTER_ROW_{TID}` 靠平行清册）。任一没修都会在 rematerialize 阶段以 `ManagedRegionResolutionError` 或 `FooterAnchorDriftError` 暴雷。改这些共享文件受主控 §5.3 共享锁约束，须 GENERALIZE 不回归单动态表（既有 358 单 sheet 工作簿注入字节 sha256 零漂移 + 变异守卫）。
- **跨 spec 借道要双向登记**：D4-1 落地时顺带把 D4-9 owner spec 的 Task 1（`_attach_table_part` 合并）做实了，D4-9 因此从 0/15 变 1/15。这类"A spec 解除 B spec 阻塞"的情况，两边 tasks.md 和本清册都要同步，否则 B spec 会重复评估已完成的阻塞项。

## D4-1 几何核定与落地记录（2026-09-20 更新，对齐已入库实现 `phase5_d4_adjudication_sheet.py`）

> ⚠️ **裁决更正**：2026-09-19 版曾判「D4-1 走 static-cell 模式，非行 UUID 模式」——该结论在实现阶段被推翻。真实模板的两段数据区是**可扩的动态行**（不是固定 4+4 骨架），前端 `useD4Adjudication` 早已用 `D4-1-rows` 动态行模型 + per-field，故最终按**同 sheet 双区动态行 UUID** 落地（参照 D4-9 多 table 结构，非 D4-5 static_row）。static-cell 段整段作废。

**结构**（openpyxl 直读 `D/D4 收入底稿.xlsx` sheet `营业收入审定表D4-1`，dims A1:I80）：
- 表头：行 5「项目/本期数/上期数」+ 行 6「未审数/账项调整/重分类调整/审定数」（两级，本期 B-E / 上期 F-I）
- 主营业务收入段（section `main-revenue`）：数据行 **8 起**（R8-11 预留） + 行 12 小计；UUID 列 **W**；table `adjudication_main_rows` / TID `D41MAIN`
- 其他业务收入段（section `other-revenue`）：数据行 **14 起**（R14-17 预留） + 行 18 小计；UUID 列 **X**；table `adjudication_other_rows` / TID `D41OTHER`
- 行 19 合计、行 20 试算平衡表数(只读回显 `D4-1-adj-tb-6001/6051`)、行 21 差异数、行 22+ 审计说明/结论
- 列：A=项目名 · B/C/D=本期未审/账项调整/重分类(受管输入) · **E=本期审定(公式 `=SUM(B:D)`)** · F/G/H=上期三输入 · **I=上期审定(公式)**
- 受管字段 = 每区 label + 6 金额（B/C/D/F/G/H）；formula_mask = E/I 数据行 + 小计/合计/差异行（12/18/19/21）的 B-I。

**已落地（commit `663c3f019`，owner spec 10/12）**：
- provider `phase5_d4_adjudication_sheet.py`：两 row table + `MANAGED_FIELD_SPECS`(7 字段) + `_formula_mask_cells` + `sheet_payload_d41`(2 table) + `instrumentation_spec_d41`(2 spec 共享 sheet_key) + `build_store_projection_d41`(按 sectionKey 分流) + `merge_projection_into_d41_rows`；`EXPECTED_MAPPING_DIGEST_D41` 冻结。
- 6 点集成进 `phase5_d4_revenue_detail`（只加不动 D4-2/3/5/15/16/25~28）。
- **4 处共享内核缺口全修**（见上「增量更新」段①~④）——这是 D4-1 的真实工作量核心，也顺带解除了 D4-9 Task 1 阻塞。
- 发布链跑全：契约 `--check` OK / provision 幂等 / `d43_rematerialize --apply` gen50→51、bundle=desired `af32bfbd…`；store-projection 含 D4-1 不打挂 entry（DB 三判据 GREEN）。
- 前端 `D4TabAdjudication.vue` 接桥 + 宿主 `isD4DedicatedSyncSheet` 含 'D4-1'；`publishAdjudicated` 发布门不动（TB 发布分离，双向切换不触发 TB 发布）。
- 守卫全绿：后端 `test_d4_1_adjudication_contract.py`(10/10)/`test_d4_1_dual_region_managed_tables.py`(7)/`test_d4_1_sibling_binding_alignment.py`/`test_d4_1_footer_anchor_per_region.py`(10) + 变异 `mutate_d4_1_adjudication_guards.py`；前端 `d4AdjudicationSyncHostWiring.spec.ts`。

**仍待办**：
- Task 11 e2e（`d4-bidirectional-acceptance.spec.ts` 加 D4-1 + 证据 `evidence/.../D4-1.json`）标 `[~]`，卡 start-dev.bat + 真实 OO 环境（`UNVERIFIABLE`）。
- Task 12 收口同 `[~]`。
- 🔴 风险已缓解但仍需真栈确认：D4-1 是审定枢纽（下游 K9/D4-10/D4-21 取审定数 + TB 发布）；离线/DB 判据已绿，e2e 真栈往返（OO 改主营/其他行→切回 HTML 值一致、两区不串）是最后一道未验证门。
