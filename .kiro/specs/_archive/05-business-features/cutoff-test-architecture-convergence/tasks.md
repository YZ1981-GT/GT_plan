# Implementation Plan: 截止性测试架构收敛

## Overview

strangler（绞杀者）分步收敛：先建纯函数 canonical 判定层与 characterization 安全网（W0），再迁移判定（W1）、统一状态机（W2）、统一证据模型（W3）；后端并行收敛端点到富引擎并补全量抽样框（W4），前端迁移到 canonical 端点（W5），统一下游 A13 联动（W6），最后加契约守卫与差异矩阵并全量回归（W7）。每个任务完成即跑对应测试，任一既有 cutoff 测试变红即停在该任务。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2", "2.1"], "note": "安全网+canonical骨架，无前置" },
    { "id": 1, "tasks": ["3", "4"], "note": "判定收敛，依赖 W0" },
    { "id": 2, "tasks": ["5"], "note": "状态机统一，依赖 W1" },
    { "id": 3, "tasks": ["6", "7"], "note": "证据模型统一，依赖 W2" },
    { "id": 4, "tasks": ["8", "8.1", "9"], "note": "后端全量+端点，依赖 W0，可与 W1-W3 并行" },
    { "id": 5, "tasks": ["10"], "note": "前端迁移端点，依赖 W3+W4" },
    { "id": 6, "tasks": ["11"], "note": "下游联动，依赖 W2" },
    { "id": 7, "tasks": ["12", "13", "14", "14.1"], "note": "守卫+文档+回归，依赖全部" }
  ]
}
```

## Tasks

### Wave 0 — 安全网 + canonical 骨架

- [x] 1. characterization 安全网：锁定五套判定/三套模型现状
  - 为 `determineCutoffStatus`/`computeDateRange`/`isCutoffPeriodCrossing`/`markCutoffCrossPeriod`/`filterByCutoffWindow`/`isCrossPeriod`(K8/K9) 补 characterization 测试，逐字锁定当前输入→输出（含单日期降级、窗口端点、direction 分支）
  - 为三套 CutoffRow 的结论派生（useCycleCutoff `_recalcFormulas`、useK8/useK9 `_defaultConclusion`）补 characterization 测试
  - _Requirements: 8.1, 7.1_

- [x] 2. 新建 `cutoffCanonical.ts` 纯函数骨架（先并存不接线）
  - `computeWindow(cutoffDate, before, after)`、`inWindow(date, cutoffDate, before, after)`
  - `judgeCrossPeriod({bookDate, documentDate}, cutoffDate) → 'none'|'suspect'|'crossing'|'same'`
  - `CutoffConclusion` 类型 + `deriveConclusion(sample, cutoffDate)`（含缺侧→证据不完整、手工优先）
  - `mapLegacyConclusion(literal) → CutoffConclusion` 字面量映射表
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.4_

- [x]* 2.1 canonical 纯函数 PBT
  - fast-check 覆盖 P8/P9/P10（判定等价、单日期降级、窗口边界）+ P11/P12（状态机完备互斥、字面量映射满射）
  - 用 W0.1 characterization 断言 canonical 与各旧函数输入产出等价
  - _Requirements: 3.1, 3.3, 3.4, 4.1, 4.4_

### Wave 1 — 判定收敛

- [x] 3. useCutoffAutoSampling 判定迁移到 canonical（filterByCutoffWindow/markCutoffCrossPeriod 已委托；determineCutoffStatus 为独立方向语义保留，记入差异矩阵）
  - `markCutoffCrossPeriod`/`filterByCutoffWindow`/`determineCutoffStatus` 调用改委托 `cutoffCanonical`；旧导出保留为薄封装（避免破坏外部 import）
  - 保持 '可能跨期'/'待检查' 对外字面量经映射输出，UI 不变
  - 跑 cutoffAutoSampling.spec/property + cutoffJudgment.property 全绿
  - _Requirements: 3.1, 3.5, 7.1_

- [x] 4. useCycleCutoff/useK8Cutoff/useK9Cutoff 判定迁移到 canonical
  - 三处 `isCutoffPeriodCrossing`/`isCrossPeriod` 调用改委托 `cutoffCanonical.judgeCrossPeriod`；窗口计算改 `computeWindow`
  - 保持既有 CutoffRow 字段不变（本步只换判定，不换模型）
  - 跑 useI2Cutoff/useI6Cutoff/i6Integration/k8-pbt-cutoff 全绿
  - _Requirements: 3.1, 3.2, 7.1_

### Wave 2 — 状态机统一

- [x] 5. 结论派生统一走 `deriveConclusion` + 字面量映射
  - useK8/useK9 `_defaultConclusion` 已委托 `cutoffCanonical.deriveConclusion`(natural-month)，非法日期边界更严格(判证据不完整而非假绿正常)
  - useCycleCutoff 保留方向性(跨期多记/漏记)+期间回退结论(canonical 状态超集，经 mapLegacyConclusion 归一)，记入差异矩阵
  - 完成门禁 persistCompletion 已统一(存在 证据不完整 → ok=false，P0 已落)
  - 跑 k8-pbt-cutoff/useI2Cutoff/useI6Cutoff/i6Integration 全绿；验证 P6/P13
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 2.2_

### Wave 3 — 证据模型统一

- [x] 6. 新建 `cutoffSampleAdapter`：canonical 证据模型 + 适配器
  - `CutoffSample` 类型 + `fromCycleRow/fromK8Row/fromK9Row` 与 `toCycleRow/toK8Row/toK9Row` 双向适配（字段别名映射，K9 documentAmount 恒 0）
  - 禁止金额自动复制（documentAmount 缺失恒 0）在适配器层强制
  - `cutoffSampleAdapter.spec.ts` 8 测试全绿（P7 禁止复制 + Req2.5 往返保真 + 字段映射）
  - _Requirements: 2.1, 2.3, 2.5_

- [x] 7. 三底稿证据模型行为收敛（适配器可用 + 门禁已保证）
  - 行为要件已达成：自动取数仅得记账侧→documentDate/documentAmount 留空→证据不完整（Wave2 canonical deriveConclusion + P0 门禁）；禁止金额自动复制（P0 + 适配器强制）；迁移不丢数据（各底稿保留自序列化）
  - `cutoffSampleAdapter` 提供统一 CutoffSample 供未来共享 UI；**全量持久化 type-routing 判定为高churn低收益+丢非证据字段(recordPeriod/belongPeriod/conclusion)风险，故不强改**（记差异矩阵§3）
  - 跑三底稿全部测试全绿；P6/P7 由 canonical 层验证
  - _Requirements: 2.1, 2.2, 2.4, 2.5, 7.1_

### Wave 4 — 后端全量抽样框 + 端点收敛（可与 W1-W3 并行）

- [x] 8. `cutoff-test` 查询构建薄委托 `LedgerSamplingService.build_ledger_query`（Req1.2 薄委托路径）
  - run_cutoff_test 的日期范围/科目前缀/dataset 隔离全部收敛到 `build_ledger_query`
  - 🔴 **阈值口径统一（审计口径决策 2026-07-24，用户授权的有意行为变更）**：cutoff-test 改用富引擎 `GREATEST(debit,credit)>=t`（t=0 含零额凭证），与 cutoff-extract **完全对齐**，不再有阈值差异（差异矩阵§4）。凭证集合较原 `debit>t OR credit>t` 会含零额凭证，K8/K9/I2/I6 截止窗口凭证集合相应变化——已授权
  - account_codes 空→早返回空集合（Req1.5，不触库）；加性补全量 `stats`（Req5.4，现有调用方忽略不影响）
  - _Requirements: 1.1, 1.2, 1.5, 5.4_

- [x]* 8.1 后端契约测试（空科目守卫 + 自定义截止日窗口 + stats 字段）
  - TestCutoffTestService 新增 2 测试（空科目不触库返空+stats零 / cutoff_date=2025-06-30→window 2025-06-25~07-10）+ 原 empty 补 stats 断言；3 passed
  - 查询构造等价由 build_ledger_query 既有 PBT（test_filter_fields_map_to_sql_clauses：前缀/日期/方向）传递覆盖；13 既有 cutoff 集成测试保持全绿
  - _Requirements: 1.3, 1.4, 5.1, 5.2, 5.5_

- [x] 9. 覆盖率/MUS 抽样间隔基于全量统计（P0 已达成）
  - MUS/覆盖率是抽凭引擎（voucher-extract）职责，其全量 StatsResult(amount_total) 失真已在 P0 修复（不用截断后 items 重算）
  - cutoff-test 调用方（K8/K9/useCycleCutoff）仅导入 entries 不算 MUS；cutoff-test 返回全部行不分页，total_entries 即全量，无截断问题
  - 差异矩阵§4 记录
  - _Requirements: 5.3, 5.5_

### Wave 5 — 前端迁移到 canonical 端点

- [x] 10. K8/K9/useCycleCutoff 取数走 canonical 查询引擎（薄委托路径达成，无需改前端）
  - Task 8 选择 Req1.2 的"cutoff-test 薄委托 canonical 引擎"路径：三处调用方经 cutoff-test 已透明使用 `build_ledger_query`（canonical 查询引擎），无需切换端点、无需改前端
  - 已具备：cutoff_date（P1）+ 科目前缀匹配（P0，经 build_ledger_query）+ 全量 stats（Task 8 加性）；exclude_extracted 是 cutoff-extract 预览流（useCutoffAutoSampling）专用，自动取数 append/replace 语义不需要
  - useI2/useI6/i6Integration/k8-pbt-cutoff 保持全绿
  - _Requirements: 1.3, 1.4, 7.2_

### Wave 6 — 下游联动一致

- [x] 11. 跨期→A13 联动跨底稿一致
  - K8-6/K8-7 补齐 `a13:push-misstatement`（source K8-6/K8-7 + adjustableRows + 告警横幅），对齐既有 K9-6/7 与 useCycleCutoff(P1)
  - 统一 payload：wpCode/accountCode/projectId/source/items(voucherNo/amount/description/indexRef)/timestamp
  - get_diagnostics 全清；差异矩阵§5 记录三底稿一致
  - _Requirements: 6.1, 6.2, 6.3_

### Wave 7 — 契约守卫 + 差异矩阵 + 回归

- [x] 12. 契约守卫：检测新增绕过 canonical 的并行实现
  - `cutoffConvergenceGuard.spec.ts`（3 测试）：扫描 composables，断言 XOR（`OnOrBefore !==/===`）与自然月（`getFullYear()*12`）算术仅存于 cutoffCanonical.ts
  - 🔴 **④ F2 第三模式收敛**：f2CutoffJudgment.classifyCutoffTiming 委托 `cutoffCanonical.classifyCutoffBoundary`（方向子类 book-before-doc-after→early_book / doc-before-book-after→late_book），F2 不再持有裸 XOR 算术→**从守卫 allowlist 移除**（仅 canonical 自身豁免，单一真源更严格）
  - _Requirements: 8.3_

- [x] 13. 差异矩阵文档
  - `docs/proposals/cutoff-test-convergence-diff-matrix.md`：判定/模型/端点 → canonical 映射、语义差异、保留决策、字面量映射表、direction 语义对照、端点未合并原因
  - _Requirements: 8.2_

- [x] 14. 全量回归 + Checkpoint
  - 前端 121 测试全绿（canonical14+adapter8+guard3+i2pbt+useI2/I6+i6Integration+k8-pbt+cutoffAutoSampling+judgment.property）；后端 cutoff 13 passed
  - P0/P1 行为逐条保持（Req7.2 清单）；pre-existing 无关失败：test_cutoff_sampling_pbt 反斜杠字面量脆弱（build_ledger_query，本 spec 未改）
  - 未 Playwright（需 I2/I6/K8/K9 实例化项目）
  - _Requirements: 7.1, 7.2, 7.4_

- [ ]* 14.1 Playwright 端到端 — live 端点验证完成；UI round-trip 受 headless 环境限制未完成
  - **live 端点验证已通过**（shell HTTP 直连，项目 0ec33ac9 重药控股安徽 K8 6601，2026-07-24）：
    - normal window=2025-12-26~2026-01-10 / total=494 / truncated=False（安全上限未触发）
    - emptyGuard：空科目 → total=0（早返回不触库，Req1.5）
    - midYear：cutoff_date=2025-06-30 → window 2025-06-25~2025-07-10（任意截止日，Req1.4）
  - **UI round-trip 未完成**：Playwright MCP 在当前 headless 环境对该 SPA 反复 30s 超时（SPA 重渲染/后台 SSE 轮询），用户 Cancel 浏览器方式。UI 交互逻辑由 cutoffAutoSampling/canonical/adapter 单测 + PBT 覆盖；有稳定浏览器环境时可补 UI round-trip
  - _Requirements: 7.2_

## Notes

- **零回归铁律**：每个任务完成后跑对应测试；任一既有 cutoff 测试变红即停在该任务，不放宽断言、不跳用例。
- **并发风险**：动手前重读最新源码，仅暂存本 spec 明确编辑的文件，避免 last-write-wins 覆盖并发会话改动。
- **P0/P1 保持清单**（Req7.2）：cutoff_date 任意截止日、科目前缀匹配、双侧证据门禁、禁止金额自动复制、undo 必传 wp_id、confirmFill 提交 filled_voucher_nos、历史/撤销/排除限定 extraction_type='cutoff'、单份版本快照、跨期→A13 联动。
- **未 Playwright**：I2/I6/K8/K9 截止表需实例化项目方能端到端实测；本 spec 以单测/PBT + 契约守卫为主要验收，Playwright 为 optional checkpoint。
- **带 `*` 任务**：为 PBT/Playwright 加固项，按既定偏好同样执行；仅当无实例化项目时 14.1 保持待执行。
