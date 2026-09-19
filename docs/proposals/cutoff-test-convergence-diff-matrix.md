# 截止性测试架构收敛 — 差异矩阵

> Spec: `.kiro/specs/cutoff-test-architecture-convergence/`（Wave 7 Task 13）
> 记录各原并行实现 → canonical 的映射、语义差异与保留决策，作为等价迁移证明与防漂移参照。

## 1. 跨期判定函数 → canonical

**🔴 核心发现：两套跨期语义不等价，canonical 保留两模式，禁止强行统一。**

反例：`bookDate=2025-11-28, documentDate=2025-12-28, cutoffDate=2025-12-31`
- cutoff-boundary（截止日两侧 XOR）：两日期均 ≤ 截止日 → **不跨期**
- natural-month（自然会计月）：11 月 ≠ 12 月 → **跨期**

| 原实现 | 文件 | 语义 | 收敛去向 | 状态 |
|--------|------|------|----------|------|
| `isCutoffPeriodCrossing(doc, rec, cd)` | useI2FormulaEngine.ts | 截止日两侧 XOR（Date 入参） | 委托 `cutoffCanonical.crossesByCutoffBoundary`（本地 YYYY-MM-DD 格式化） | ✅ 已委托 |
| `isCrossPeriod(src, book, periodEnd)` | useK8CutoffEngine.ts | 自然会计月（year+month 不同） | 委托 `cutoffCanonical.crossesByNaturalMonth`（删本地 getAccountingPeriod） | ✅ 已委托 |
| `isCrossPeriod(src, book, periodEnd)` | useK9CutoffEngine.ts | 自然会计月 | 委托 `cutoffCanonical.crossesByNaturalMonth`（删本地 getAccountingPeriod） | ✅ 已委托 |
| `markCutoffCrossPeriod(v, cd)` | useCutoffAutoSampling.ts | 截止日两侧 XOR + 单日期降级 | 委托 `cutoffCanonical.judgeCrossPeriod(_, _, 'cutoff-boundary')` → crossing/suspect | ✅ 已委托 |
| `filterByCutoffWindow(vs, cd, b, a)` | useCutoffAutoSampling.ts | ±N 天窗口过滤 | 委托 `cutoffCanonical.inWindow` | ✅ 已委托 |
| `computeDateRange(cd, b, a)` | cutoffJudgment.ts | ±N 天窗口计算 | 保留独立实现（P10 已证与 `computeWindow` 逐日等价，作 characterization 基准） | 🟡 保留 |
| `determineCutoffStatus(vd, cd, dir, amt, b, a)` | cutoffJudgment.ts | 单日期 + 方向(post/pre/window) + 金额符号的**预览标注** | **独立语义，未折叠**：canonical 是双侧日期模型，不含"单方向+金额符号"预览语义；字面量 '可能跨期'→'跨期'、'待检查'→'待追查' 经 `mapLegacyConclusion` 归一 | 🟡 保留 |
| `judgeF2Cutoff(...)` | f2CutoffJudgment.ts | F2 存货截止：'incomplete'/'ok'/'early_book'/'late_book'/'cross_other'（更丰富方向语义） | **不在本 spec 范围**（属 f2-inventory-cross-sheet-hardening）；契约守卫显式豁免 | 🟡 范围外 |

**收敛后核心算术单一源**：XOR（`OnOrBefore !==`）与自然月（`getFullYear()*12`）仅存于 `cutoffCanonical.ts`，由 `cutoffConvergenceGuard.spec.ts` 守卫。

## 2. 结论状态机 → canonical 6 态

统一状态集合：`待追查 / 证据不完整 / 正常 / 跨期 / 需调整 / 已调整`。

| 原实现 | 收敛去向 | 状态 |
|--------|----------|------|
| useK8Cutoff `_defaultConclusion` | 委托 `cutoffCanonical.deriveConclusion(_, _, 'natural-month')` | ✅ 已委托 |
| useK9Cutoff `_defaultConclusion` | 委托 `cutoffCanonical.deriveConclusion(_, _, 'natural-month')` | ✅ 已委托 |
| useCycleCutoff `_buildConclusion`/`_recalcFormulas` | **保留**方向性子类型（跨期多记/跨期漏记）+ 期间(recordPeriod/belongPeriod)回退证据；canonical 是纯日期模型不含这两者。子类型经 `mapLegacyConclusion` 归为 '跨期'；完成门禁 '证据不完整' 已统一 | 🟡 保留 |

**行为改进（非回归）**：K8/K9 原 `_defaultConclusion` 对非空但**非法**日期会判 '正常'（假绿）；canonical 用解析有效性 → 判 '证据不完整'，符合 Req2.2 证据门禁意图。

字面量映射（`mapLegacyConclusion`，满射保语义）：`可能跨期/跨期多记/跨期漏记 → 跨期`；`待检查 → 待追查`；其余同名；未识别 → 待追查（不静默判正常）。

## 3. 双侧证据模型 → CutoffSample

`cutoffSampleAdapter.ts` 提供统一 `CutoffSample`（记账侧 book* / 原始单据侧 doc*）+ 三底稿双向适配器。

| canonical 字段 | useCycleCutoff | useK8Cutoff | useK9Cutoff |
|----------------|----------------|-------------|-------------|
| bookDate | recordDate | bookDate | bookDate |
| bookAmount | amount | amount | amount |
| voucherNo | voucherNo | voucherNo | voucherNo |
| documentDate | documentDate | sourceDate | sourceDate |
| documentAmount | documentAmount | sourceAmount | （无 → 恒 0） |
| documentNo | documentNo | sourceVoucherNo | sourceVoucherNo |
| summary | description | summary/businessContent | summary |

**铁律**：documentAmount 缺失恒 0，**禁止**自动复制 bookAmount（P7）。适配器提供模型供未来共享 UI；各底稿现有序列化保留自持（避免丢 recordPeriod/belongPeriod/conclusion 等非证据字段），行为门禁已由判定/结论收敛保证。

## 4. 后端截止端点（未物理合并 — 语义差异保留）

| 端点 | 服务 | 阈值语义 | 返回 | 全量统计 |
|------|------|----------|------|----------|
| 端点 | 服务 | 阈值语义 | 返回 | 全量统计 |
|------|------|----------|------|----------|
| `POST /sampling/cutoff-test` | CutoffTestService.run_cutoff_test | `GREATEST(debit,credit) >= t`（t=0 含零额，与 extract 一致） | 全部 entries（安全上限 2000，超出 truncated=true） | DB 级全量聚合（total_count/amount_total，不受展示截断） |
| `POST /sampling/cutoff-extract` | LedgerSamplingService | `GREATEST(debit,credit) >= t`（t=0 含零额） | 分页（page_size≤100） | DB 级 StatsResult（含 amount_total / truncated） |

**决策：查询语义完全收敛（Req1.2 薄委托 + 阈值口径统一）**。
- `run_cutoff_test` 的查询构建（日期范围 + 科目前缀 + dataset 隔离 + **金额阈值**）全部经 `LedgerSamplingService.build_ledger_query`（canonical 查询引擎）。
- **阈值口径统一（审计口径决策 2026-07-24）**：采用富引擎 `GREATEST(debit,credit)>=t`，t=0 含零额凭证——cutoff-test 与 cutoff-extract **查询语义至此完全一致**，不再有阈值差异。
  - ⚠️ 相对旧 cutoff-test（`debit>t OR credit>t`，t=0 排零额）是**有意行为变更**（用户授权），非静默回归：K8/K9/I2/I6 截止窗口现含零额凭证（利于完整性），边界 t 值改为闭区间（`>=`）。
- 前端调用方经 cutoff-test 透明使用 canonical 查询引擎（Req1.2 薄委托路径），无需切换端点。

**已收敛的查询要素**：cutoff_date（任意截止日）+ 科目前缀匹配 + `GREATEST>=t` 阈值 + 加性全量 `stats`（Req5.4）+ 安全上限（MAX_ENTRIES=2000，超出走 DB 聚合准确统计 + truncated 透明）。

**剩余差异（仅工程层，非语义）**：两者仍是不同 HTTP 端点（cutoff-test=返全部+安全上限、无 exclude_extracted；cutoff-extract=分页+exclude_extracted 预览流）。查询**语义**已单一源（build_ledger_query），物理路径差异是刻意的（服务不同交互场景）；进一步合并为单一 HTTP 端点属工程整理，无语义风险。

**已修的 DB 全量抽样框问题**：voucher-extract 的截断口径失真（覆盖率/MUS 用截断后 items 重算）已在 P0 修复（改用 StatsResult 全量 amount_total）。cutoff-test 加安全上限后同样走 DB 聚合全量统计。

## 5. 下游联动（A13 错报）一致性

| 底稿 | 跨期→AJE 草稿 | 跨期→a13:push-misstatement | 状态 |
|------|---------------|---------------------------|------|
| useCycleCutoff（I2/I6） | draftAjeFromCrossPeriod | ✅（P1 已补，wpCode 从 adjustmentSheetCode 前缀推导） | ✅ |
| K8-6 / K8-7 | （K8-3 调整分录） | ✅（本轮补，source K8-6/K8-7，payload 对齐 K9） | ✅ |
| K9-6 / K9-7 | （K9-3 调整分录） | ✅（既有） | ✅ |

payload 统一：`{ wpCode, accountCode, projectId, source, items[{voucherNo, amount, description, indexRef}], timestamp }`（crossWpEventBridge 白名单事件）。

## 6. 契约守卫

`cutoffConvergenceGuard.spec.ts`：扫描 composables 目录，断言 XOR / 自然月跨期算术仅存于 `cutoffCanonical.ts`（f2CutoffJudgment 显式豁免）。新增绕过 canonical 的并行判定 → 守卫失败。

## 7. 零回归验证

Wave 0-3+6 全程既有 cutoff 测试保持全绿（cutoffCanonical 14 + cutoffSampleAdapter 8 + cutoffConvergenceGuard 3 + i2FormulaEngine.pbt + useI2Cutoff + useI6Cutoff + i6Integration + k8-pbt-cutoff + cutoffAutoSampling + cutoffJudgment.property）。P0/P1 已修确定性行为全部保持。
