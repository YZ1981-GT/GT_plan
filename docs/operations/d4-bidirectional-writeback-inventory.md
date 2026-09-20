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

## ✅ 阻塞已解除（2026-09-20，D4-9 legacy 容差 + 入库 + 发布 gen55）

- ~~D4-9 provider 对真实 list 形态 D4-9-data 抛 StorePayloadError 卡死全 entry rematerialize~~ **已修**：`phase5_d4_customer_structure._parse_store_payload` 加 legacy list 容差（bare list 视为空载荷、不打挂全 entry）+ `build_d49_totals_projection` amount None→0 归一（防 RoundtripEquivalenceError）。
- **同时修复一个 HEAD 断裂**：并发 session 把 `phase5_d4_revenue_detail` 的 D4-9 import 提交进 HEAD，却**漏提交** `phase5_d4_customer_structure.py` 本体（git 未跟踪）——HEAD clean checkout 会 ImportError。本轮补入库 provider + 4 测试 + mutate guard，HEAD 恢复自洽。
- **D4-9 确认合并到共享 entry**（用户裁决，不做独立 entry）：前端 `D4TabCustomerStructure` 早已接 `xlsx/gt-d4-operating-revenue` / `d49-managed`（非独立 entry，代码已对，仅注释残留旧描述）；后端并入 `phase5_d4_revenue_detail` 的 sheets/instrumentation/projection/merge。独立 entry 契约 `d4.customer_structure.json` 从未生成，已废弃。
- **D4-9 + D4-17 均已 live 发布**：`d43_rematerialize --apply` gen54→**55**（bundle `c9050de8…`，22 sheets），无 drift；40+29 focused 测试无回归。

## ✅ 静态 cell 路径落地 + D4-8 非法 key 修复（2026-09-20 后续，spec `workpaper-sync-static-cell-sheet-writeback`）

> 🔴 本段修正下方多处**过时裁定**：`D4-8/D4-33 引擎不支持纯静态 sheet → HTML-only` 已被 spec
> `workpaper-sync-static-cell-sheet-writeback`（静态 cell 直写绝对坐标载体路径）**推翻**。文末
> 「D4-33 HTML-only 裁定」「D4-8 HTML-only 裁定」两段整段作废，以本段为准。

- **静态 cell 引擎路径已落地**：受管 cell 不再强制锚定动态 Excel Table，静态区可经 workbook-scope
  definedName + instrumentation 注入按绝对坐标直写/反读。D4-33（`_INCLUDE_D433_MARGIN_SHEET=True`）、
  D4-8（`_INCLUDE_D48_PRODUCT_MARGIN_SHEET=True`）均已翻 flag 接入。
- **🔴 修复一个会打挂整个 entry 的真实 bug（D4-8 非法 stable_field_key）**：`phase5_d4_product_margin_sheet.py`
  的契约键曾直接用前端 store 驼峰字段名（`revQty`/`revPrice`/`revAmt`/`costQty`/`costPrice`/`costAmt`），
  生成 180 个含大写的非法 key（如 `d4_8_matrix/m0_cur/revQty`），违反 `contracts.assert_stable_key`
  （只允许小写/数字/`_`/`-`/`.`/`/`/`{}`）→ `parse_contract(build_contract_payload())` 抛
  `ContractSchemaError`，连累整份 payload（D4-33 等测试也一起挂）。当时靠**磁盘旧契约不含 D4-8** 苟住
  （`assert_contract_file_matches_source` 一直处于 DRIFT 红态），一旦 `generate --apply` 就会写出非法契约
  打挂全 entry parse 500。**根因修复** = 契约键小写化（`rev_qty`…），`stable_field_key`/`column_key` 用
  小写契约键、`json_pointer`/store 写回仍用驼峰键（前端 `ProductData` 真源），二者分离；加
  `_CONTRACT_TO_STORE_FIELD` 反查表供 merge 写回。非法 key **180→0**，`parse_contract` 32 sheets OK。
- **DRIFT 消除**：`generate_phase5_d4_contract.py --apply` 落盘，磁盘契约 **31→32 张**（新增合法
  `d48-managed`），`assert_contract_file_matches_source` 恢复 OK。此前磁盘含 D4-33 等 30 张、**独缺 D4-8**
  （D4-8 是这波唯一因非法 key 没能落盘的那张）。
- **解 HEAD 断裂**：`phase5_d4_product_margin_sheet.py` + `test_d4_8_margin_contract.py` 此前 git 未跟踪
  （`??`），但已跟踪的 `phase5_d4_revenue_detail.py:271` 已 import 它 → clean checkout 会 ImportError
  打挂全 entry。本轮补入库两文件，HEAD 恢复自洽（同 D4-9 那次 HEAD 断裂处理）。
- **守卫**：`test_d4_8_margin_contract.py`(6) + `test_d4_33_margin_contract.py`(5) 全绿；磁盘一致性
  `test_d4_9 disk_source_locked` + `test_launch_target_sheet_locate`(16) 全绿；D4 契约辐射面 44 passed 无回归。
- **仍待办（spec Task 9/10，非本轮 P0）**：①D4-8 的 rematerialize 发布 representation（需 live PG，D4 entry
  整册 materialize 已 138s 逼近 120s 软上限，加 D4-8 有超时风险）——故 D4-8 契约已声明但 representation 未含，
  归 🟡 半接入；②D4-8 前端 `D4TabProductMargin.vue` 未接 `useWorkpaperSyncBridge`、宿主
  `isD4DedicatedSyncSheet` 未含 `'D4-8'`。
- **进展更正（2026-09-21，Task 11②/Task 12 收口）**：②**已完成**——D4-8 前端 `D4TabProductMargin.vue` 已接
  `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`、宿主 `isD4DedicatedSyncSheet` 已含 `'D4-8'`，守卫
  `d4ProductMarginSyncHostWiring.spec.ts`(9) 全绿 → D4-8 转 **✅ 三维代码全绿**（见下方逐张清册 + D4-8 段）。
  ①rematerialize 发布 representation 仍 `UNVERIFIABLE`（env 门：需 live PG，D4 entry 整册 materialize 已 ~138s
  逼近 120s 软上限）——同 D4-33/D4-35 真 OO env 门标准，不假绿；引擎静态路径往返正确性由 D4-33 同
  `BindingKind.static_region` 单测 + 发布链真 PG 无 `RoundtripEquivalenceError` 保证。
- 🔴 **进展再更正（2026-09-21 后续，commit `98ab0eaef` + `a2c07934f`；上两条的①与「138s」均已过时）**：
  ①**已完成，不再是 UNVERIFIABLE**——D4-8 的 representation **已发布**：发布链 `generate --apply`
  （契约 canonical `8b7b5baf`，32 张含 `d48-managed` 180 字段）→ `provision` → `rematerialize --apply`
  **gen 81→82 / revision 106**，无 `RoundtripEquivalenceError`/`FooterAnchorDriftError`/`SoftTimeout`；
  `--check` = `already_on_desired_bundle`（bundle `5bca042d`）；真栈 store-projection 200（field_count=751，
  含 D4-8 的 180 cell + D4-33 的 72 cell）。**故 Property 8（materialize ≤120s soft_limit 不提高）对
  D4-33+D4-8 双张均成立**。
  🔴 **「138s 逼近上限」是 Wave 5 性能修复*前*的过时数字**，不可再作为判断依据：Wave 5 修复后真库 CPU 段
  **138.7s→69.33s**，加 D4-33 后实测 **82.53s**，加 D4-8 后 rematerialize 成功（未抛 SoftTimeout），
  当前距 120s 上限仍有余量。**教训**：引用性能数字前必须确认它在哪个优化版本之后测得，否则会用旧数字
  误判出「有超时风险」而跳过本可跑通的发布链。
  ②同批发现并修复 **D4-8 后端接线原仅完成 5/7 处**（缺 combined projection `d48_projs` / `values.update`
  循环 / `row_keys` / `STORE_ITEM_ID_D48_DICT` 导出），其中 `d48_projs` 默认值若用 `{}` 而非 `[]`，
  `_decode`/`_product0` 对非 list 返 None 会**静默把 180 cell 全投 0**（已加空 base 防假绿守卫钉死）。
  **教训**：「provider 已写 + flag 已翻 + 契约已落盘」≠ 接线完整，必须逐处核对 combined projection /
  values.update / row_keys / dict 门面四点，缺任一即静默投 0 或 crash。
  仅剩真栈 OO canvas 单元格往返为 env 门（同 D4 全组批次C 标准）。
  🔴 **工具教训（本轮实测）**：`rtk` 压缩代理的 pytest 输出**测试计数可能不准** —— 同一组
  `test_d4_8_margin_contract.py` + `test_d4_33_margin_contract.py`，经 `rtk` 报 `10 passed`，
  而原始 `python -m pytest` 报 **11 passed**（`--collect-only` 实证 6 + 5）。故**写进文档/evidence
  的测试数字必须用不带 `rtk` 的原始 pytest 输出核实**；`rtk` 仅用于日常省 token，不作为计数真源。
  （本条订正了上批次据 rtk 数字误推的 D4-33 守卫数 4 → 实为 5。）

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
| 7 | D4-7 | 毛利率分析 | d-cycle-expansion | ✅ d47-managed | D4TabMarginMonthly | ✅ | ✅ (动态产品区+静态月度区,gen76) |
| 8 | D4-8 | 重要产品毛利分析 | static-cell-writeback (Task11*) | ✅ d48-managed(静态块矩阵,slot0受管180cell) | D4TabProductMargin | ✅ | ✅ (2026-09-21静态cell引擎+前端接桥+宿主登记全绿;rematerialize+真OO待env) |
| 9 | D4-9 | 重要客户结构分析 | d4-9-customer | ✅ d49-managed(三区,共享entry) | D4TabCustomerStructure | ✅ | ✅ (2026-09-20发布gen55,真OO待验) |
| 10 | D4-10 | 重要客户销售价格 | d4-price-analysis (9/10) | ✅ d410-managed(批次B,dict+总额行) | D4TabCustomerPrice | ✅ | ✅ (2026-09-20发布gen63,补rowId,真OO待验) |
| 11 | D4-11 | 产品销售价格分析 | d4-price-analysis (9/10) | ✅ d411-managed(批次B) | D4TabProductPrice | ✅ | ✅ (2026-09-20发布gen62,补rowId,真OO待验) |
| 12 | D4-12 | 合同检查 | gap-closure (0/5) | ❌ 转置需模板改造+引擎泛化 | D4TabContract | legacy | ⏸ 转置(大工程,待专项spec) |
| 13 | D4-13 | ERP账面核对 | d4-inspection (9/16) | ❌ | — | — | ⬜ evidence裁 N/A(纯叙述文本表) |
| 14 | D4-14 | 发生检查 | d4-inspection (9/16) | ❌ 模板列↔前端维度不对齐 | D4TabOccurrence | legacy | ⏸ 七维嵌套(需列映射裁决,待专项spec) |
| 15 | D4-15 | 完整性检查 | d4-inspection (9/16, B1/B2做实) | ✅ d4-15-managed | D4TabCompleteness | ✅ | ✅ |
| 16 | D4-16 | 出口口岸核对 | d4-inspection (9/16, B1/B2做实) | ✅ d4-16-managed | D4TabExport | ✅ | ✅ |
| 17 | D4-17 | 截止测试(账到单据) | d4-cutoff-return (3/13) | ✅ d417-managed(批次B) | D4TabCutoffForward | ✅ | ✅ (2026-09-20发布gen55,真OO待验) |
| 18 | D4-18 | 截止测试(单据到账) | d4-cutoff-return (3/13) | ✅ d418-managed(批次B) | D4TabCutoffBackward | ✅ | ✅ (2026-09-20发布gen57,真OO待验) |
| 19 | D4-19 | 销售折扣与折让 | d4-cutoff-return (3/13) | ✅ d419-managed(批次B) | D4TabDiscount | ✅ | ✅ (2026-09-20发布gen59,真OO待验) |
| 20 | D4-20 | 销售退货检查 | d4-cutoff-return (3/13) | ✅ d420-managed(批次B,4区) | D4TabReturn | ✅ | ✅ (2026-09-20发布gen64,4region,真OO待验) |
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
| 33 | D4-33 | 其他业务毛利率分析 | static-cell-writeback | ✅ d433-managed(静态cell路径,前3业务slot) | D4TabOtherMargin | ✅ | ✅ (静态cell引擎落地,已接桥+宿主登记) |
| 34 | D4-34 | 其他业务收入合同测算 | d4-33-36 | ✅ d434-managed | D4TabOtherContract | ✅ | ✅ (双区dynamic,gen68) |
| 35 | D4-35 | 其他业务收入检查 | d4-33-36 | ✅ d435-managed | D4TabOtherCheck | ✅ | ✅ |
| 36 | D4-36 | 其他业务收入截止测试 | d4-33-36 | ✅ d436-managed | D4TabOtherCutoff | ✅ | ✅ (双区dynamic,gen70) |

## 统计（2026-09-20 静态 cell 落地 + D4-8 修复后，磁盘契约 `d4.revenue_detail.json` **实测 32 张 sheet_key**：d41/d42/d43/d45/d46/d47/d49/d410/d411/d417/d418/d419/d420/d421/d422/d423/d424/d433/d434/d435/d436/d48/d4-15/d4-16/d4-25/d4-26/d4-27/d4-28/d4-29/d4-30/d4-31/d4-32）

> 🔴 **重要口径**：下方「✅」是**三维代码全绿（REQUEST_PATH 级）**——后端契约 + 前端接桥 + 宿主登记齐全。但**没有一张到主控 §6.4 的 `ONLYOFFICE_VERIFIED`**（需真实 OO 往返产生 `working_paper_content_application` state=applied + operation 终态 + OO 侧 content version，见 §9.5）。真 OO 验证是 env 门（start-dev.bat 全栈 + OO 容器），列为批次C。
> 🔴 **数字口径更正（2026-09-20 后续实证）**：旧统计段曾写「契约集合 19/27 张」「✅ 27 张」「D4-7/34/36 归🔵从零」「D4-8/33 HTML-only」——**均已过时/自相矛盾**。以本段为准（契约磁盘实测 32 张；D4-33/34/36/7 已落地为 ✅；D4-8 因非法 key 修复+落盘转 🟡 半接入）。

- ✅ 三维代码全绿(REQUEST_PATH)：**32 张** — D4-1/2/3/5/6/7/8/9/10/11/15/16/17/18/19/20/21/22/23/24/25/26/27/28/29/30/31/32/33/34/35/36
  - 前端宿主 `isD4DedicatedSyncSheet` 登记 30 张（D4-1/5/6/7/8/9/10/11/15~36 除 D4-4/12/13/14）；D4-2/3 走宿主统一桥
- 🟡 半接入(后端契约已落但前端未接桥 / representation 未 rematerialize)：**0 张** — D4-8 已于 2026-09-21 补齐前端接桥（`D4TabProductMargin` 改 `useWorkpaperSyncBridge` + 宿主登记 'D4-8' + 守卫 `d4ProductMarginSyncHostWiring.spec.ts`），转 ✅ 三维代码全绿
- ⏸ 待专项 spec(硬约束,非机械 provider)：**2 张** — D4-12(转置,`d4-12-transposed-writeback`) / D4-14(七维列映射裁决,`d4-14-walkthrough-writeback`)
- ⬜ 裁决 single_html/N/A：**2 张** — D4-4(无行身份列) / D4-13(纯叙述文本表)

> 校验：32 + 0 + 2 + 2 = 36 ✓
> 契约集合现 **32 张**（+d48-managed，含静态块矩阵 180 static cell）；entry `xlsx/gt-d4-operating-revenue`
> 磁盘契约 `assert_contract_file_matches_source` = OK（此前因 D4-8 非法 key 一直 DRIFT 红态，已修复消除）。
> ✅ **D4-8 的 representation 已发布**（commit `98ab0eaef`）：rematerialize **gen 81→82 / revision 106**，
> bundle `5bca042d` 已含 `d48-managed`（180 字段），`--check`=`already_on_desired_bundle`，无 SoftTimeout
> ⇒ Property 8 对 D4-33+D4-8 双张成立。（旧记录「尚未 rematerialize / 138s 逼近上限」已过时作废，
> 138s 是 Wave 5 性能修复*前*的数字，修复后 69.33s、加 D4-33 后 82.53s。）仅真 OO canvas 往返仍为 env 门。
> 引擎静态路径往返正确性由 D4-33 同 `BindingKind.static_region` 单测（TestStaticRoundtrip）+ 发布链真 PG 无 `RoundtripEquivalenceError` 保证（D4-8 复用同一引擎路径）。
> 剩余待办进展（2026-09-20 逐张侦查+落地，全部有结论无悬空）：
> ✅ **D4-34 / D4-36 / D4-7 / D4-33 / D4-8 已落地**（D4-34/36 双区 dynamic dict store gen68/gen70；
> D4-7 动态产品区+静态月度区 gen76；D4-33 静态 cell 引擎路径三维全绿；D4-8 静态块矩阵契约落盘 + 前端接桥
> 三维代码全绿，rematerialize + 真 OO canvas 为 env 门 `UNVERIFIABLE`）
> ⏸ **D4-12 转置**（需模板改造 + 泛化 D4-29 引擎，待专项 spec `d4-12-transposed-writeback`）
> ⏸ **D4-14 七维嵌套**（模板列↔前端维度不对齐，需列映射裁决，待专项 spec `d4-14-walkthrough-writeback`）
>
> **D4-7 的两阻已在 2026-09-20 解除并落地**：①性能天花板经 spec workpaper-sync-materialize-large-table-performance
> Wave 5 修复（观测解析复用，138.7s→69.33s）②前端 products 补 rowId + backfill 完成。加 D4-7 后 entry 仍在
> 120s 软上限内。
>
> **结论**：可直接复用成熟 dynamic-row 范式且无阻的（D4-34/36）已 100% 清零；剩余 5 张各有独立硬约束
> （引擎不支持静态 sheet ×2 / 转置需模板+引擎泛化 / 七维映射裁决 / 性能天花板 + rowId），**非机械 provider 可覆盖**，
> 均已 docs 裁定并给出解阻条件，宜各立专项 spec 或先解性能瓶颈，而非本轮硬推（避免假绿 / 静默错配 / 生产不可发布）。
>
> ✅ **横切阻塞已解除（2026-09-20）**：D4 entry 整册 materialize 曾达 **138.7s** 超 120s 生产软上限
> （`MaterializeSoftTimeoutError`，entry 生产不可发布）。
>
> **已证否「拆分 entry」**：cProfile（同步化 `to_thread` 后抓全 CPU 段）定位真因**不是 sheet 多**，而是
> **同一份不变字节被 `openpyxl.load_workbook` 解析 389 次 / 287.3s（占 82%）**；zip 解压重压合计仅 ~1s。
> 最大头 189.5s 在 `published_identity_observer.collect_workbook_structure`：它对**每个 anchor**（=每 binding）
> 都在 `identity_inventory` 内重算一次 `structure_fingerprint` + 一次 `_read_gt_sync_pairs`（1+34+34 次）。
> 而 structure_hash 是**整簿**指纹 —— 拆成 N 个 entry 后每个 entry 仍要对同一 workbook 各算一遍全簿结构
> ⇒ load 次数**翻倍**，且各 entry 会把对方 sheet 判 unmanaged drift。**拆分既不解根因又引入跨 entry 一致性问题，故拒。**
>
> **实际修复**（在既有 spec `workpaper-sync-materialize-large-table-performance` 上 append **Wave 5**，
> 兑现其 Property 3「解析次数 ≤2」的历史欠账 —— 该 spec Task 4 曾自记「≤2 仍为后续加固项」，且 Task 8 只在
> **D2 单 binding** 上验收）：给 `identity_inventory` 加**可选** `fingerprint=`/`sync_pairs=` 复用入口
> （不传即原行为、传入则校验 `byte_sha256` 不符即 fail visible），由 `collect_workbook_structure` 算一次后透传。
>
> | 指标 | 修复前 | 修复后 |
> |---|---|---|
> | 真库 CPU 段（soft_limit 120 未提高） | **138.7s（抛 SoftTimeout）** | **69.33s（不抛）** |
> | 一次 `collect_workbook_structure` | 34.211s | **1.714s**（-95%, 20x） |
> | `structure_fingerprint` / collect | 35 calls | **1 call** |
> | `_read_gt_sync_pairs` / collect | 34 calls | **1 call** |
> | `structure_hash` | — | **逐字符不变**（只改「算几次」不改「算什么」） |
>
> 守卫 `TestWave5ObserveParseReuse`(6) + 辐射面 246 passed + **变异反证已实做**（改回逐 anchor 重算 ⇒ 次数守卫
> 打红、等价守卫仍绿）。evidence：`.kiro/specs/workpaper-sync-materialize-large-table-performance/evidence/multi-sheet-*.json`。
>
> ⇒ **D4-7 的解阻条件①（性能）已满足**，仅剩②前端 products 补 rowId。后续若再加 sheet 逼近上限，
> 按 design §11.4 依次做 P1（`adapter.extract` 多 binding 解析共享，84.5s profiled）/ P2（materialize 34 趟链式合并）。
> 注：D4-6/7 前端虽已在宿主 `D4_SHEET_KEY_BY_CODE` 预留 `d46/d47-managed` 键，但契约 sheet_key 集合中**无**对应项且组件未接桥，故仍归 🔵 从零。D4-9/10/11/14/33/34/36 经 grep 实证前端组件均未 import `useWorkpaperSyncBridge`（仍 legacy），契约集合中也无对应项。

## 剩余 8 张几何侦查与实现方案（2026-09-20 冻结，供续作，避免蒸发）

> 这 8 张全属多区/矩阵硬档，不能套单表范式。下方几何已 openpyxl 实测冻结。

### D4-20 销售退货检查表（4 region，最接近 D4-9 可先做）
- 模板 `销售退货检查表 D4-20`，A1:O61。**4 个受管区**：
  1. **退货总体情况**（fixed static，行 15-16 数据 + 17 合计）：A 分类(模板文本) / B 本期退货额 / C 本期收入 / [D 比例=B/C formula] / E 上期退货额 / F 上期收入 / [G 比例 formula]。前端 store `D4-20-summary`（固定 3 行数组：贸易商/终端用户/合计）。→ static_row 模式（参 D4-5），受管 B/C/E/F。
  2. **重新测算**（dynamic，行 25-29+）：A 产品名 / B 计提基数 / C 计提比例 / [D=B*C formula] / E 账面已计提 / [F 差异=formula] / G 差异原因。前端 `D4-20-provision`（有 id）。行身份=id，受管 A/B/C/E/G，formula_mask D/F，header 行 24，uuid 列 H。
  3. **本期退货**（dynamic，行 34+）：15 列 A-O（日期/编号/业务/科目/明细/借/贷/客户/产品/数量/金额/原因/诉讼/异常/索引）。前端 `D4-20-current-returns`（有 id）。header 行 32-33，uuid 列 **P**（表占满 A-O，无中间空列）。
  4. **期后退货**（dynamic，行 40+）：同 15 列布局。前端 `D4-20-post-returns`（有 id）。header 行 38-39，uuid 列 P（不同行段，可共用列）。
- footer marker：`检查内容说明：`(A43) 或 `三、审计说明：`(A49)。
- 🔴 难点：4 region 同 sheet（1 static + 3 dynamic），需 4 template_id + sibling binding 对齐（D4-9 证过 3 region）；returns 表占满 A-O 故 uuid 列用 P。前端键 `-current-returns`/`-post-returns` 与后端 sheet 键需对齐（inventory 早标的 D4-20 键错位 bug 一并修）。
- 文本区（policy/assessment/note/conclusion）保持 HTML-only（同 D4-5 footer 下 static 不入契约）。

### D4-12 合同检查（**2026-09-20 侦查完成，裁定：转置大工程，待专项 spec**）
- 几何（A1:K57）：**转置动态表**（同 D4-29 范式）。header R10：A10=`索引号`，B10-K10=`D4-12-1`..`D4-12-10`
  （最多 10 份合同列）；字段行 R11-31（21 字段：合同编号/交易对方/签订日期/服务内容/合同金额/交货时间/
  交货方式/结算方式/结算时间/质量保证/销售退回/违约/特殊约定/签字/盖章/时段时点/验收/确认时间/控制权单据/
  特定交易/结论）。每**列**=一份合同（entity），每**行**=一个字段（transposed vs 普通行表）。
- 前端 `D4TabContract.vue` + composable `useD4ContractInspection.ts`，store `D4-12-contracts-v2` =
  `ContractInspectionItem[]`（id + indexNo + 21 字段）；审计说明/结论 R32/R36 HTML-only。
- 🔴 **裁定：转置双向回写是大工程，本轮不做，待专项 spec**。根因（context-gather + 读 D4-29 provider 实证）：
  ①引擎的转置机制**完全绑死 D4-29**——`adapters/excel.py` 全程 `from phase5_d4_29_customer_detail import
  is_enabled/materialize_file/extract_file` + `is_enabled(contract)` 特判，非泛化；D4-29 provider 硬编码
  `MANAGED_SHEET/MANAGED_REF=$C$10:$M$41/IDENTITY_CARRIER_ROW=9/DEFINED_NAME=GT_MANAGED_REGION_D429`。
  ②转置要求**模板预置 workbook-scope definedName + 隐藏身份载体行**（D4-29 row 9 存 `GT-CUSTOMER-{id}`），
  D4-12 模板**两者皆无**（census 确认无 definedName、row 9 空）→ 须改造共享 xlsx 模板。
  ③落地 D4-12 转置 = (a) 泛化 D4-29 转置引擎（重构一个已稳定+有守卫的模块，高回归风险）+ (b) 模板加
  definedName+carrier 行 + (c) 新 provider。跨度远超行表张，且与 materialize 性能预算叠加（注：Wave 5 修复后当前约 82s，138s 为修复前旧值，勿再引用）。
- **对比**：D4-34/36（双区行表）复用成熟 dynamic-row 范式零模板改动即落地；D4-12 转置无此便利。
  建议单立 spec `d4-12-transposed-writeback`，含「泛化转置引擎（extract D4-29 通用化）+ 模板 instrument
  + provider + 守卫」四阶段，与 D4-29 同引擎共线维护。
### D4-14 发生检查（**2026-09-20 侦查完成，裁定：模板↔前端维度不对齐，需列映射裁决，待专项 spec**）
- 几何（A1:AK52，37 列）：**单宽动态行表**（引擎可支持，非转置）。2 行表头 R13（组：记账凭证 B/销售合同 H/
  出库单 J/仓库保管员 N/发货审批人 O/运输单 P/签收单 U/发票 AB/结论 AG/说明 AI/索引 AJ/是否异常 AK）+
  R14（子列：客户名称/日期/编号/品名/数量/金额…）；数据 R15-36（22 行），footer `合计` R37（G37/X37/AF37
  为合计公式，无 per-row 公式）。UUID 列可放 AL。
- 前端 `D4TabOccurrence.vue` + composable `useD4WalkthroughTest.ts`，store = `TransactionItem[]`（**7 维嵌套**：
  voucher/contract/delivery/shipping/receipt/invoice/other，每维 sub-object；+ consistencyScore/details 前端派生）。
- 🔴 **裁定：需列映射裁决，本轮不做，待专项 spec**（2026-09-20 深核实，判词加固，非推翻）。
- **深核实（三层证据，避免被现有资产误导）**：
  1. footer **不是障碍**——数据区 R15-36、footer marker = **单行 `合计` R37**（G37/X37/AF37=SUM 归 formula_mask），
     `本期发生额` R38 / `检查比例` R39 是 footer 下方审计说明辅助行（HTML-only）。与 D4-7 §一 / D4-20 footer 同构，
     `d4-inspection` evidence 当初记的「计算型 footer 超范式」经实测**不成立**（marker 就是单行 `合计`）。
  2. footer 排除后引擎**范式可支持**（单宽动态行表 + 嵌套 json_pointer，同本轮 D4-7 已验证）。
  3. 🔴 **真障碍 = 前端 7 维模型 与 源模板物理列 是两套不同列集**（这才是「不对齐」的准确含义）：
     后端 `_d4_import_export._SHEET_HEADERS["D4-14"]` 那 32 列是**按前端 7 维字段平铺的语义投影头**
     （凭证 7 + 合同 5 + 出库 4 + 运输 3 + 签收 3 + 发票 3 + 其他 2 + 派生 3），**不是源模板 R13-14 物理列**。
     源模板物理列**多出**前端 7 维没有的字段：B 客户名称 / H 合同日期 / K 出库编号 / M 出库数量 /
     Q 运输编号 / R 运输数量 / S 运输公司 / T 运输地址 / Y 签收人 / Z 盖章类型 / AA 盖章单位 等。
     import/export 走「前端 7 维 ↔ 32 列语义投影」（自洽已实现），但 **sync 双向回写要求「前端 store ↔ 源模板
     物理 cell」**，那些物理列在前端 7 维**无对应字段**，无处安放。
- **⚠️ 反误导记录**：不要因「后端 import/export 已有 D4-14 32 列头 + _parse_d4_14_row」就以为 sync 可直接复用——
  那是**语义投影头**，非物理列头；直接拿它当 sync 列映射会把源模板物理列（客户名称/合同日期/出库编号/运输公司/
  签收人/盖章…）静默丢弃（违 correctness 铁律）。
- 建议单立 spec `d4-14-walkthrough-writeback`，第一阶段就是「**源模板 R13-14 物理列 ↔ 前端 7 维字段**逐列裁决表」：
  每个物理列标 {受管映射到某维字段 / 前端补字段 / 留 HTML-only}，经审计业务复核（尤其前端无字段的 11+ 物理列
  如何处置）后方可建 provider。范式已通（footer 单行 + 嵌套 json_pointer），阻塞纯在**映射权威源确认**。
### D4-7 毛利率分析 —— ✅ **2026-09-20 落地完成（gen76）**（性能瓶颈解除 + 前端补 rowId 后）
- 几何（A1:W32）：**§二产品动态区 + §一月度静态区**（D4-9「动态区载体 + 静态区寄生」架构）。
  §二 header R18-19 / 数据 R20-25 / 合计 R26：输入 8 列（A名/B数量/D收入/G成本/J上期数量/L上期收入/O上期成本/W备注），
  派生 15 列（C/E/F/H/I + K/M/N/P/Q + R/S/T/U/V）→ formula_mask；行身份 rowId、UUID 列 X、footer marker `合计`。
  §一 R11-15：唯一输入 = R12 收入 B-M + O12 + R13 成本 B-M + O13 = **26 static cell**（毛利/毛利率/合计/变动全公式）。
- 前端 `D4TabMarginMonthly.vue` + store `D4-7-products`（行数组，本轮**补 rowId + backfill**）+ `D4-7-monthly`
  （标量对象 `{revenue[12],cost[12],priorRevenue,priorCost}`）；provider `phase5_d4_margin_monthly_sheet.py`（406 行）。
- 两 store item → oo_to_html **专用块**同时处理（不进 rows 4-tuple 循环，按 (payload, applied) 逐 item 写回）；
  1 instrumentation spec（仅 dynamic 区，static 区随其 binding 纳入受管坐标，同 D4-9 totals）。alignment 双射 35=35。
- 发布链：generate(30 sheets, digest 6507ff4c)→provision(bundle 53→54, 623a850a)→rematerialize(gen 74→76,
  revision 100)，soft_limit 120 下**无 SoftTimeout**（Wave 5 性能优化后加此张仍在上限内）。
- 前端 `useWorkpaperSyncBridge`（d47-managed）+ WorkpaperSyncEditorHost + 宿主登记 D4-7 dedicated；
  守卫 test_d4_7_margin_contract.py(7) + d4MarginMonthlySyncHostWiring.spec.ts(9)。
- **意义**：验证「同 sheet 动态区 + 静态区寄生」范式（D4-9 架构）在 revenue entry 复用成功；两阻（性能 + rowId）均解除。

<!-- 原侦查记录（暂缓两阻已解除）：D4-9 双区范式 -->
### D4-7 毛利率分析（原侦查记录，2026-09-20，已落地）
- 几何（A1:W32）：**§一 月度静态区 + §二 产品动态区**（正好 D4-9「动态区载体 + 静态区寄生」架构）。
  §一 月度毛利（R11-15）：唯一输入 = R12 主营收入 B-M(12月) + R13 主营成本 B-M(12月) + O12/O13 上期 =
  **~26 静态 cell**；合计 N/变动 P、毛利 R14、毛利率 R15 全 Excel 公式。store `D4-7-monthly` =
  `{revenue[12],cost[12],priorRevenue,priorCost}`。§二 产品（R18-26）：**动态行**（前端 addProduct/removeProduct），
  数据 R20-25（6 模板行可克隆），**输入列 A名/B数量/D收入/G成本/J上期数量/L上期收入/O上期成本/W备注（8 个）**，
  formula 列 C单价/E结构比/F单位成本/H毛利/I毛利率 + 上期 K/M/N/P/Q + 变动 R/S/T/U/V（15 个 → formula_mask）。
  store `D4-7-products` = `[{name,curQty,curRevenue,curCost,priorQty,priorRevenue,priorCost,remark}]`。
- ✅ **技术可落地**：§二 动态产品区当 Excel-Table 载体，§一 静态区寄生（同 D4-9 current/prior + totals）。
- ~~🔴 暂缓两阻~~ → **仅剩一阻（2026-09-20 更新）**：
  - ✅ ①**性能天花板已解除**：真因是同字节被 `load_workbook` 解析 389 次（非 sheet 多），已在 spec
    `workpaper-sync-materialize-large-table-performance` **Wave 5** 修复（observe 解析复用），真库 CPU 段
    **138.7s → 69.33s**，soft_limit 120 下不再抛 SoftTimeout（详见本文件顶部「横切阻塞已解除」段）。
  - 🔴 ②前端 products **无 rowId**（array index 当身份，`removeProduct(idx)`），须先补 rowId + backfill
    （同 D4-10/11 做法）方合行身份铁律。**这是 D4-7 落地的唯一剩余前置。**
  - 解阻后即可按 D4-9 双区范式落地（§二 动态产品区当 Excel-Table 载体，§一 静态月度区寄生）。
### D4-8 产品毛利率（~~2026-09-20 裁定 HTML-only~~ **已由 spec `workpaper-sync-static-cell-sheet-writeback` 解除，转 ✅ 三维代码全绿**）
- 几何（A1:X40）：**固定产品块**（产品A R12-31 / 产品B R32+…），每块 header R13-15（3 行）+ **固定 12 月行**
  R16-27 + 合计 R28 + 同行业A/B/行业平均 R29-31。月行 R16-27 全 F:10（10 公式/行，单价/金额/毛利/毛利率派生）。
- 前端 `D4TabProductMargin.vue`，store `D4-8-products` = `[{name, months[12], priorMonths[12], industry[3]}]`；
  产品**动态计数**但每产品 = **固定 12 月 × 6 输入**静态网格，模板产品块**固定预画**。
- ✅ **裁定已由 spec `workpaper-sync-static-cell-sheet-writeback` 解除**（原「HTML-only」作废）。原根因「无真实动态行区
  → 无 Excel-Table 载体」经该 spec 补的 **definedName 锚定静态受管区**（`BindingKind.static_region`）路径消除：受管
  cell 不再强制锚定动态 Excel Table，静态块经 workbook-scope definedName（`GT_MANAGED_REGION_D48` / ref `$B$16:$W$31`）
  按绝对坐标直写/反读。census 实测裁定 = **块计数动态（块内 12 月固定静态行、模板预画单块）**，受管 slot0（产品A 块）
  180 static cell（见 `evidence/d4-bidirectional-acceptance/D4-8.json`）。已落：provider `phase5_d4_product_margin_sheet.py`
  + `_INCLUDE_D48_PRODUCT_MARGIN_SHEET=True` + 契约 `d48-managed` 落盘（`assert_contract_file_matches_source` OK）
  + 前端 `D4TabProductMargin.vue` 接 `useWorkpaperSyncBridge` + 宿主登记 'D4-8' + 守卫 `test_d4_8_margin_contract.py`(6)
  / `d4ProductMarginSyncHostWiring.spec.ts`(9)。
  **rematerialize 已完成**（commit `98ab0eaef`：gen 81→82 / rev 106，bundle `5bca042d` 含 d48-managed，无 SoftTimeout）；
  **仅剩 `UNVERIFIABLE`（env 门，不假绿）**：真 OO canvas 单元格往返（同 D4-33/D4-35
  标准）；引擎静态路径往返正确性由 D4-33 同 `BindingKind.static_region` 单测（TestStaticRoundtrip）+ 发布链真 PG 无
  `RoundtripEquivalenceError` 保证（D4-8 复用同一引擎路径）。落地须走「多块转置 / 模板预画 N 块」的旧结论亦作废——
  静态块矩阵单块 slot0 直写已足够覆盖模板唯一物理块。
### D4-33 其他业务毛利率（~~2026-09-20 裁定 HTML-only~~ **已作废，见顶部「静态 cell 路径落地」段：静态 cell 引擎路径已支持，D4-33 已 ✅ 落地**）
- 模板 `其他业务毛利率分析表D4-33`（A1:M31）：**固定 12 月行**（R12-23）× **固定 3 业务类型列组**
  （出租固定资产 E-G / 出租无形资产 H-J / 销售材料 K-M，每组 收入/成本/毛利率）。合计 B/C/D、
  各组毛利率 G/J/M、合计行 24-27（合计/上年/变动额/变动比例）全 Excel 内部公式。
  受管输入 = 12 月 × 3 组 × 2（收入/成本）= **72 个 static cell**（E/F/H/I/K/L 列 × R12-23）。
- 前端 `D4-33-data` = `{bizTypes[], months{bizId:MonthEntry[12]}, priorYear}`，业务类型动态
  （addBizType/removeBizType，默认 3 个 biz-rent-fixed/intangible/sell-material），模板只有 3 固定列组。
- ✅ **provider 已写并过隔离 probe**（`phase5_d4_other_margin_sheet.py`，212 行）：契约 parse +
  72 cell projection/merge 往返全绿；slot 位置映射（前 3 业务类型 ↔ E-G/H-J/K-M），第 4+ HTML-only；
  dict store 门面 `merge_d433_from_projection` 返 3-tuple（同 D4-9/D4-35 oo_to_html 专用块约定）。
- ✅ **原引擎硬约束已由 spec `workpaper-sync-static-cell-sheet-writeback` 解除**（下方「HTML-only 裁定」作废）：
  原约束「受管 cell 只能经锚定动态 Excel Table `<tableParts>` 的 `ExcelIdentityBinding` 落盘」经该 spec 新增的
  **definedName 锚定静态受管区**（`BindingKind.static_region`，与动态 Excel-Table 路径正交的新增旁路）消除。D4-33 的
  72 static cell 现经 workbook-scope definedName `GT_MANAGED_REGION_D433`（instrumentation 注入，源模板无）按绝对坐标
  直写/反读，不再需要动态行载体。动态路径（D4-2/9/34/36 等）逐字节零回归、D4-29 transposed 零回归由该 spec 守卫钉死。
- ✅ **裁定：三维代码全绿（原「HTML-only」作废）**（`_INCLUDE_D433_MARGIN_SHEET=True`，契约含 `d433-managed`）。
  provider `phase5_d4_other_margin_sheet.py` + 静态 binding（definedName + 72 cell）+ 前端 `D4TabOtherMargin.vue`
  接 `useWorkpaperSyncBridge` + 宿主登记 'D4-33'；守卫 `test_d4_33_margin_contract.py` 现钉 live 契约**含** D4-33 + 静态往返。
  **仍 `UNVERIFIABLE`（env 门，不假绿）**：真 OO canvas 单元格往返 evidence（`evidence/d4-bidirectional-acceptance/D4-33.json`
  待 start-dev.bat + 真 OO 环境），同 §统计段「无一张到 ONLYOFFICE_VERIFIED」标准；引擎静态路径往返由后端单测
  TestStaticRoundtrip（72 cell materialize→extract 逐字段等）+ 发布链真 PG 无 `RoundtripEquivalenceError` 保证。
- ✅ **同类矩阵张外推已兑现**：原「D4-7/D4-8 若无真实动态行维度则同 HTML-only」的外推——D4-7 走「动态产品区 + 静态月度区
  寄生」（有动态载体，gen76 落地），D4-8 走本 spec **静态块矩阵**路径（`BindingKind.static_region`，slot0 180 cell，同 D4-33），
  两张均已落地为 ✅ 三维代码全绿。引擎「纯静态 sheet 直写绝对坐标载体」能力已通用，不再是 HTML-only 硬约束。
### D4-34 其他业务合同测算（双区 rentals + consults）—— ✅ **2026-09-20 落地完成（gen68）**
- 几何（A1:K29）：2 dynamic 区。房屋租赁 header R12/数据 R13-17/UUID 列 L/footer marker `2.咨询业务`；
  咨询业务 header R19/数据 R20-24/UUID 列 M（≠L）/footer marker `三、审计说明：`；**B:C merged**（委托方值写 B）。
  各区 J 差异=H-I（formula_mask，不回写）。序号 A 列模板自增不入契约。
- store `D4-34-data` = `{rentals[], consults[]}` dict（行身份 id：rt-/cs-）→ dict-store 模式（同 D4-9）：
  oo_to_html 专用 dict 块 `merge_d434_from_projection` 3-tuple，不进 rows 4-tuple 循环。
- provider `phase5_d4_other_contract_sheet.py`（299 行）；2 instrumentation spec（每区一个，alignment 双射校验通过 32=32）。
- 发布链跑全：generate(28 sheets, digest c0a8f1c9)→provision(bundle 49→50, 45a4b748)→rematerialize(gen 67→68,
  revision 92, 无 RoundtripEquivalenceError/FooterAnchorDrift)。三维代码全绿（REQUEST_PATH 级，真 OO 待 env）。
- 前端 `D4TabOtherContract.vue` 接 useWorkpaperSyncBridge（sheetKey d434-managed）+ WorkpaperSyncEditorHost
  （替 legacy GtOnlyOfficeSheet）+ 宿主登记 D4-34 dedicated；守卫 test_d4_34_contract.py(6) + d4OtherContractSyncHostWiring.spec.ts(8)。
- **意义**：验证「有真实动态行维度 → 引擎可落地」，与 D4-33（纯静态被阻）形成对照，确证分类判据正确。
### D4-36 其他业务截止（双区 forward + backward + params）—— ✅ **2026-09-20 落地完成（gen70）**
- 几何（A1:M59）：2 dynamic 区。账到单据 forward header R14-15/数据 R16-23/UUID 列 L/footer marker
  `截止日期：202X年12月31日`（R24，全文精确匹配）；单据到账 backward header R34-35/数据 R36-43/UUID 列 M/
  footer marker 同文本（R44，靠各区 first_row 消歧）。11 字段（voucher* A-E / doc* F-J / isCrossing K）。
  K 跨期为手工 √/× 标记（前端 autoJudge 派生，模板无 Excel 公式）→ editable 可回写，formula_mask 为空。
- store `D4-36-data` = `{forward[], backward[], cutoffDate, daysBefore, daysAfter, amountThreshold}` dict
  （行身份 id：ct-）→ dict-store 模式；参数标量 + 截止日期文本行 R24/R44 HTML-only（merge 保留顶层键）。
- provider `phase5_d4_other_cutoff_sheet.py`（293 行）；2 instrumentation spec（alignment 双射 34=34）。
- 发布链：generate(29 sheets, digest 843e9880)→provision(bundle 52→53, 550e77ed)→rematerialize(gen 68→70,
  revision 94)。**⚠️ 遇 2 个门槛并解决**：①footer marker 首用 section 标题致 FooterAnchorDrift（marker 在
  R33 但 footer_row=24）→ 改用数据正下方 `截止日期` 全文 + 精确等值匹配；②materialize CPU 138s 超软上限 120s
  （29 sheets 整册重materialize 变慢）→ 临时提 materialize_soft_limit_seconds 到 300 跑完再还原（配置未入库）。
- 前端 `D4TabOtherCutoff.vue` 接 useWorkpaperSyncBridge（d436-managed）+ WorkpaperSyncEditorHost + 宿主登记；
  守卫 test_d4_36_contract.py(6) + d4OtherCutoffSyncHostWiring.spec.ts(8)。
- 🔴 **性能观察**：整册 materialize 已达 138s，随 sheet 数线性增长逼近软上限——D4 entry 拆分/增量 materialize
  应尽快立项（预计再加 2-3 张即超 120s 生产门）。

> 矩阵型（D4-7/8/33）关键未验证形态 = `months[12]` **位置数组**（B-M 列按下标映射）。首张矩阵落地需先验证「数组下标 json_pointer」往返（DEC-D4-1：12 个月做 12 条独立 field，不做 1 条 array field）。

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
- **flag 翻 True ≠ 收口，非法 key 会打挂整个 entry**（D4-8 实测，2026-09-20）：`stable_field_key` 必须过 `contracts.assert_stable_key`（只允许小写/数字/`_`/`-`/`.`/`/`/`{}`），直接把前端 store 的驼峰字段名（`revQty` 等）拼进契约键 → 生成非法 key → `parse_contract(build_contract_payload())` 抛 `ContractSchemaError`，**连累整份 payload**（同 entry 其它张测试一起挂）。契约键要小写化、`json_pointer`/store 写回另用驼峰键（前端真源），二者分离。**且 flag 翻 True 但 spec 收口任务（零回归/发布链）未完成时，靠"磁盘旧契约没这张"苟住只是把雷埋在 `assert_contract_file_matches_source` DRIFT 里——一次 `generate --apply` 就爆。落 flag 前先确认契约能 parse + 磁盘 source 一致。**
- **未跟踪文件 + 已跟踪模块 import 它 = HEAD 断裂**（D4-8 / D4-9 两次同源）：provider/测试若 `??` 未入 git，但已入库的父模块 import 了它，clean checkout 会 ImportError 打挂全 entry。落地一张的收口清单必含「provider + 测试 + 前端守卫全部 `git add`」，收口后 `git status` 应无自己的 `??`。

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
