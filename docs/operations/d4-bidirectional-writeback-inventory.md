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
| 9 | D4-9 | 重要客户结构分析 | d4-9-customer | ✅ d49-managed(三区,共享entry) | D4TabCustomerStructure | ✅ | ✅ (2026-09-20发布gen55,真OO待验) |
| 10 | D4-10 | 重要客户销售价格 | d4-price-analysis (9/10) | ✅ d410-managed(批次B,dict+总额行) | D4TabCustomerPrice | ✅ | ✅ (2026-09-20发布gen63,补rowId,真OO待验) |
| 11 | D4-11 | 产品销售价格分析 | d4-price-analysis (9/10) | ✅ d411-managed(批次B) | D4TabProductPrice | ✅ | ✅ (2026-09-20发布gen62,补rowId,真OO待验) |
| 12 | D4-12 | 合同检查 | gap-closure (0/5) | ❌ | — | — | 🔵 gap待做 |
| 13 | D4-13 | ERP账面核对 | d4-inspection (9/16) | ❌ | — | — | ⬜ evidence裁 N/A(纯叙述文本表) |
| 14 | D4-14 | 发生检查 | d4-inspection (9/16) | ❌ | D4TabOccurrence | legacy | 🔵 从零(32列七维嵌套,风险高) |
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
| 33 | D4-33 | 其他业务毛利率分析 | d4-33-36 (0/42) | ❌ 契约无 d433 | D4TabOtherMargin | **legacy** | 🔵 从零 |
| 34 | D4-34 | 其他业务收入合同测算 | d4-33-36 | ❌ | D4TabOtherContract | **legacy** | 🔵 从零 |
| 35 | D4-35 | 其他业务收入检查 | d4-33-36 | ✅ d435-managed | D4TabOtherCheck | ✅ | ✅ |
| 36 | D4-36 | 其他业务收入截止测试 | d4-33-36 | ❌ | D4TabOtherCutoff | **legacy** | 🔵 从零 |

## 统计（2026-09-20 批次A/A-5 后，契约 sheet_key 集合 **19 张**：d41/d42/d43/d45/d421/d422/d423/d424/d435/d4-29/d4-25/d4-26/d4-27/d4-28/d4-15/d4-16/**d4-30/d4-31/d4-32**）

> 🔴 **重要口径**：下方「✅」是**三维代码全绿（REQUEST_PATH 级）**——后端契约 + 前端接桥 + 宿主登记齐全。但**没有一张到主控 §6.4 的 `ONLYOFFICE_VERIFIED`**（需真实 OO 往返产生 `working_paper_content_application` state=applied + operation 终态 + OO 侧 content version，见 §9.5）。真 OO 验证是 env 门（start-dev.bat 全栈 + OO 容器），列为批次C。

- ✅ 三维代码全绿(REQUEST_PATH)：**27 张** — D4-1/2/3/5/6/9/10/11/15/16/17/18/19/**20**/21/22/23/24/25/26/27/28/29/30/31/32/35
  - 批次A(21~24) + 批次A-5(30~32) + 批次B(D4-6/9/10/11/17/18/19/20) 为 2026-09-20 落地；余此前已接桥
- 🔵 owner spec 待做/从零(后端无契约 + 前端仍 legacy)：**7 张** — D4-7/8/12/14/33/34/36
- ⬜ 裁决 single_html/N/A：**2 张** — D4-4/D4-13

> 校验：27 + 7 + 2 = 36 ✓（🟡 半接入类已清零）
> 契约集合现 **27 张**（+d420-managed，含 4 table：summary/provision/current/post returns）；entry `xlsx/gt-d4-operating-revenue` 当前 representation **gen64**（bundle d91cf0f2）。
> 剩余 7 张全属更硬一档：D4-12（多子表待侦查）· D4-14（32列七维嵌套）· D4-7/8/33/34/36（矩阵型/双区，`months[12]` 位置数组 + 密集内部公式，2-3x）。逐张比已完成的复杂。
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

### D4-12 合同检查（多子表，待侦查列布局）
### D4-14 发生检查（32 列七维嵌套，风险最高，可能需拆多 sheet 或裁 limited）
### D4-7 毛利率分析（双区：月度 obj `revenue[12]/cost[12]` 位置数组 + products 动态区）
### D4-8 产品毛利率（product×12月矩阵 + 密集内部公式 H=D-G/毛利率/变动分析 R-W）
### D4-33 其他业务毛利率（**2026-09-20 侦查+落地尝试完成，裁定 HTML-only：引擎不支持纯静态 cell sheet**）
- 模板 `其他业务毛利率分析表D4-33`（A1:M31）：**固定 12 月行**（R12-23）× **固定 3 业务类型列组**
  （出租固定资产 E-G / 出租无形资产 H-J / 销售材料 K-M，每组 收入/成本/毛利率）。合计 B/C/D、
  各组毛利率 G/J/M、合计行 24-27（合计/上年/变动额/变动比例）全 Excel 内部公式。
  受管输入 = 12 月 × 3 组 × 2（收入/成本）= **72 个 static cell**（E/F/H/I/K/L 列 × R12-23）。
- 前端 `D4-33-data` = `{bizTypes[], months{bizId:MonthEntry[12]}, priorYear}`，业务类型动态
  （addBizType/removeBizType，默认 3 个 biz-rent-fixed/intangible/sell-material），模板只有 3 固定列组。
- ✅ **provider 已写并过隔离 probe**（`phase5_d4_other_margin_sheet.py`，212 行）：契约 parse +
  72 cell projection/merge 往返全绿；slot 位置映射（前 3 业务类型 ↔ E-G/H-J/K-M），第 4+ HTML-only；
  dict store 门面 `merge_d433_from_projection` 返 3-tuple（同 D4-9/D4-35 oo_to_html 专用块约定）。
- 🔴 **落地被引擎硬约束挡下（context-gather 实证 + rematerialize 实测 RoundtripEquivalenceError）**：
  受管 cell 只能经 `ExcelIdentityBinding` 落盘，binding **必须**锚定一张 `row_identity` **动态表**的
  Excel Table `<tableParts>` 载体（materialize `managed_tables_of` 对 `not dynamic.has_dynamic_rows`
  直接 raise；extract `resolve_managed_region` 靠 Excel Table displayName 定位受管区）。D4-9 的
  `customer_totals` 静态标量能落盘仅因它**寄生**在同 sheet 两张动态表（current/prior）的 tableParts 上。
  **D4-33 整张只有静态表、无任何动态行维度**（12 月是固定枚举、业务类型是动态列但模板仅 3 固定列组）
  → 无载体 → materialize 写不进、反读缺全部 72 字段。
- **裁定：HTML-only**（`_INCLUDE_D433_MARGIN_SHEET=False`，同 D4-45 静态块 precedent，不进 Excel 契约）。
  wiring 已接但全 flag 门控 inert；守卫 `test_d4_33_margin_contract.py`（4 测试）钉住 provider 自洽 +
  live 契约不含 D4-33 的诚实状态。**解除条件**：引擎支持「纯静态 sheet 直写绝对坐标载体」，或给
  D4-33 造真实动态行表当载体（本表无动态行语义，属伪造，拒）。届时一键翻 flag=True 接入。
- 🔴 **同类矩阵张的引擎结论外推**：D4-7（月度双区）、D4-8（product×12月）若同样**无动态行维度**
  （纯固定行×固定列 static matrix），则同受此引擎约束 → HTML-only；若有真实动态行（如 product 可增删行）
  则可按动态表落地。逐张须先侦查「是否存在真实动态行维度」再定，不可一律套 static-cell provider。
### D4-34 其他业务合同测算（双区 rentals + consults）
### D4-36 其他业务截止（三区 forward + backward + params）

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
