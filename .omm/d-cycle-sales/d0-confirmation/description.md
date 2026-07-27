# D0 函证枢纽（跨循环共享）

D0 不是某个科目的底稿，而是**全平台函证能力的实现地**：9 个 `confirmation-*` componentType 在 D0 开发，被 E0/F0/G0/H0/K0/L0 直接复用，不为每个循环重复开发。

## 9 个 componentType（前端注册确认）

| componentType | 用途 |
|---|---|
| `confirmation-summary` | 函证汇总（编制真源，逐笔函证行） |
| `confirmation-entity-verify` | 主体身份核验 |
| `confirmation-followup` | 未回函跟进 / 催函 |
| `confirmation-diff-reconcile` | 差异调节 |
| `confirmation-diff-checklist` | 差异检查清单 |
| `confirmation-diff-securities` | 证券类差异 |
| `confirmation-fraud-risk` | 舞弊风险信号 |
| `confirmation-reliability` | 电子回函可靠性 |
| （替代程序族 `alternative-*`） | 未回函替代程序，8 套已收敛为工厂 `createAlternativeConfirmationData(config)` |

## 双真源与桥

- **编制真源**：`confirmation-summary` 的行数据存底稿 `checklist_responses`
- **台账真源**：后端 `confirmation` 表（状态机 + 项目级台账，`ConfirmationHub.vue` 消费）
- **桥**：`syncHubFromSummary`（底稿汇总行 upsert 到台账 + 状态机推进），由披露/汇总页显式按钮触发；批量走 `POST /confirmations/batch-sync`

## 状态机（后端 `_ALLOWED_TRANSITIONS`）

`pending 待发函 → sent 已发函 → returned 已回函 → matched 相符 / discrepancy 差异`

**严格单向**，终态无反向转换；点错只能删除重建（撤回能力是已识别缺口，见 concern）。

## 回函 → 下游

终态转换触发后端 `apply_confirmation_result` → `EventType.CONFIRMATION_RECEIVED`
→ `_on_confirmation_received` → `propagate_wp_stale(wp_code)` → 下游 D1/D2/D5 等标 stale；
前端 `eventBus.emit('confirmation:received')` → 明细表按对方名称/科目匹配回写 `isConfirmed` 与 `confirmedAmount`。

## 覆盖率口径（易误读，已在代码里改成真相标签）

- `confirmation_coverage` = 发函总额 / **科目审定总额（TB population）**；population 取不到时返回 `null` 并显示"需科目总体金额"占位，**不用 0 或行合计冒充**
- `confirmed_coverage` = 已确认额 / population
- `reply_coverage` = 已回函**笔数** / 已发函笔数（笔数口径，不是金额）
