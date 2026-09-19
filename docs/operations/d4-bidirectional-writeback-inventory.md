# D4-1..36 双向回写逐张现状清册

> **基线日期**：2026-09-19
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

## 逐张清册（分母 = 36）

图例：✅=三维全绿(真双向) · 🟡=后端接入但前端 legacy(半接入,需改前端接桥) · 🔵=owner spec 待做/从零 · ⬜=裁决为 single_html/N/A

| # | wp_code | 名称 | owner spec | 后端契约 | 前端组件 | 前端接桥? | 综合 |
|---|---------|------|-----------|---------|---------|----------|------|
| 1 | D4-1 | 营业收入审定表 | d4-1-adjudication (0/13) | ❌ 无 d41-managed | GtD4OperatingRevenue(专属) | legacy | 🔵 从零 |
| 2 | D4-2 | 主营业务收入明细 | d4-revenue-matrix (11/13) | ✅ d42-managed | 宿主走桥 | ✅ | ✅ |
| 3 | D4-3 | 其他业务收入明细 | d-cycle-expansion (8/8) | ✅ d43-managed | 宿主走桥 | ✅ | ✅ |
| 4 | D4-4 | 调整分录汇总 | gap-closure (0/5) | ❌ | — | — | ⬜ 已裁 single_html(无行身份列) |
| 5 | D4-5 | 会计政策检查 | d-cycle-expansion | ✅ d45-managed | D4TabPolicyCheck | ✅ | ✅ |
| 6 | D4-6 | 重要指标分析 | d-cycle-expansion | ❌ | D4TabKeyIndicator | ? | 🔵 待核 |
| 7 | D4-7 | 毛利率分析 | d-cycle-expansion | ❌ | D4TabGrossMargin | ? | 🔵 待核 |
| 8 | D4-8 | 重要产品毛利分析 | gap-closure (0/5) | ❌ | — | — | 🔵 gap待做 |
| 9 | D4-9 | 重要客户结构分析 | d4-9-customer (0/15) | ❌ | D4TabCustomerStructure | legacy | 🔵 从零(需先修同sheet双区instrumentation) |
| 10 | D4-10 | 重要客户销售价格 | d4-price-analysis (8/10) | ❌ | D4TabCustomerPrice | ? | 🔵 待核 |
| 11 | D4-11 | 产品销售价格分析 | d4-price-analysis (8/10) | ❌ | D4TabProductPrice | ? | 🔵 待核 |
| 12 | D4-12 | 合同检查 | gap-closure (0/5) | ❌ | — | — | 🔵 gap待做 |
| 13 | D4-13 | ERP账面核对 | d4-inspection (0/7) | ❌ | — | — | ⬜ evidence裁 N/A(纯叙述文本表) |
| 14 | D4-14 | 发生检查 | d4-inspection (0/7) | ❌ | D4TabOccurrence | legacy | 🔵 从零(32列七维嵌套,风险高) |
| 15 | D4-15 | 完整性检查 | d4-inspection (B1/B2做实) | ✅ d4-15-managed | D4TabCompleteness | ✅ | ✅ (本次修复入库) |
| 16 | D4-16 | 出口口岸核对 | d4-inspection (B1/B2做实) | ✅ d4-16-managed | D4TabExport | ✅ | ✅ (本次修复入库) |
| 17 | D4-17 | 截止测试(账到单据) | d4-cutoff-return (0/7) | ❌ | D4TabCutoffAtoB? | legacy | 🔵 从零 |
| 18 | D4-18 | 截止测试(单据到账) | d4-cutoff-return (0/7) | ❌ | D4TabCutoffBtoA? | legacy | 🔵 从零 |
| 19 | D4-19 | 销售折扣与折让 | d4-cutoff-return (0/7) | ❌ | D4TabDiscount? | legacy | 🔵 从零 |
| 20 | D4-20 | 销售退货检查 | d4-cutoff-return (0/7) | ❌ | D4TabReturn | legacy | 🔵 从零 |
| 21 | D4-21 | 关联方销售/价格 | d4-21-24 (11/12) | ✅ d421-managed | D4TabRelatedPrice | **legacy** | 🟡 半接入(后端有前端未接桥) |
| 22 | D4-22 | IPO重要指标分析 | d4-21-24 (11/12) | ✅ d422-managed | D4TabIpoIndicator | **legacy** | 🟡 半接入 |
| 23 | D4-23 | 收入与开票比较 | d4-21-24 (11/12) | ✅ d423-managed | D4TabInvoiceCompare | **legacy** | 🟡 半接入 |
| 24 | D4-24 | 第三方回款检查 | d4-21-24 (11/12) | ✅ d424-managed | D4TabThirdParty | **legacy** | 🟡 半接入 |
| 25 | D4-25 | IPO经销商检查 | ipo-checklist | ✅ d4-25-managed | D4TabDealer | ✅ | ✅ |
| 26 | D4-26 | 境外销售收入检查 | ipo-checklist | ✅ d4-26-managed | D4TabOverseas | ✅ | ✅ |
| 27 | D4-27 | 识别未披露关联方 | ipo-checklist | ✅ d4-27-managed | D4TabUndisclosedRp | ✅ | ✅ |
| 28 | D4-28 | 客户信息核查清单 | ipo-checklist | ✅ d4-28-managed | D4TabCustomerChecklist | ✅ | ✅ |
| 29 | D4-29 | 客户信息检查表 | ipo-fraud | ✅ d4-29-managed | D4TabCustomerDetail | ✅ | ✅ |
| 30 | D4-30 | 客户访谈记录汇总 | ipo-fraud (6/11) | ❌ 契约无(_INCLUDE_IPO_INTERVIEW=False) | D4TabInterviewSummary | 桥(d4-30-managed) | 🟡 前端接桥但后端契约关闭 |
| 31 | D4-31 | 客户访谈记录 | ipo-fraud (6/11) | ❌ 同上(几何未就绪) | D4TabInterviewDetail | 桥(d4-31-managed) | 🟡 前端接桥但后端契约关闭 |
| 32 | D4-32 | 资金流水检查 | ipo-fraud (6/11) | ❌ 同上 | D4TabFundFlow | 桥(d4-32-managed) | 🟡 前端接桥但后端契约关闭 |
| 33 | D4-33 | 其他业务毛利率分析 | d4-33-36 (0/进行中) | ❌ 契约无 d433 | D4TabOtherMargin | **legacy** | � 从零 |
| 34 | D4-34 | 其他业务收入合同测算 | d4-33-36 | ❌ | D4TabOtherContract | **legacy** | 🔵 从零 |
| 35 | D4-35 | 其他业务收入检查 | d4-33-36 | ✅ d435-managed | D4TabOtherCheck | ✅ | ✅ |
| 36 | D4-36 | 其他业务收入截止测试 | d4-33-36 | ❌ | D4TabOtherCutoff | **legacy** | 🔵 从零 |

## 统计（2026-09-19 契约 sheet_key 集合实证：d42/d43/d45/d421/d422/d423/d424/d435/d4-29/d4-25/d4-26/d4-27/d4-28/d4-15/d4-16 共 15 张）

- ✅ 三维全绿(真双向)：**11 张** — D4-2/3/5/15/16/25/26/27/28/29/35
- 🟡 半接入(后端有契约但前端仍 legacy / 前后端不一致)：**7 张** — D4-21/22/23/24(后端契约有前端legacy) + D4-30/31/32(前端接桥但后端契约 `_INCLUDE_IPO_INTERVIEW_SHEETS=False` 关闭)
- 🔵 owner spec 待做/从零(后端无契约 + 前端无桥)：**16 张** — D4-1/6/7/8/9/10/11/14/17/18/19/20/33/34/36 + D4-1
- ⬜ 裁决 single_html/N/A：**2 张** — D4-4/D4-13

> 注：D4-6/7/10/11/14/33/34/36 经 grep 实证前端组件均未 import `useWorkpaperSyncBridge`（仍 legacy 或无 OO），契约 sheet_key 集合中也无对应项，故归 🔵 从零。

## 逐张推进优先级（建议）

1. **先验证已做实的 11 张**（✅）：Playwright 逐张确认真双向可用 — 成本低、确认修复生效。
2. **修半接入的 8 张**（🟡）：前端从 legacy `GtOnlyOfficeSheet` 改为 `useWorkpaperSyncBridge`（D4-21/22/23/24/33）；D4-30/31/32 需后端开 `_INCLUDE_IPO_INTERVIEW_SHEETS` 并解决 D4-31 几何 — 每张改完 Playwright 验证。
3. **做从零的 14 张**（🔵）：按 owner spec 实现 provider + 契约 + 前端接桥 + Playwright — 工作量最大，D4-1 枢纽优先。
4. **D4-4/D4-13** 保持裁决，不做单元格双向。

## 关键教训（写入本清册以防再犯）

- **"契约里有 sheet" ≠ "双向已落地"**：D4-21/22/23/24 后端契约齐全（d4-21-24 spec 标 11/12），但前端在线编辑仍是 legacy `GtOnlyOfficeSheet`，OO→HTML 统一路径未消费。必须三维全绿。
- **前后端可能反向不一致**：D4-30/31/32 前端已接桥（sheetKey d4-30/31/32-managed），但后端 `_INCLUDE_IPO_INTERVIEW_SHEETS=False` 契约里根本没这些 sheet — 前端调 materialize 会因 sheet 未在契约而失败。
- **半成品接入会打挂整个 entry**：D4-15/16 曾因契约声明但 representation 未 rematerialize，导致整个 `gt-d4-operating-revenue` entry（连累 D4-2/3/25~28）store-projection 全线 500。改契约后必须跑 provision + rematerialize 发布链。
