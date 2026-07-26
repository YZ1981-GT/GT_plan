# Implementation Plan

## Overview

按源模板重建 N1-5，并把「不确认」金额与原因打通到附注（上市 `五、30` / 国企 `八、31`）未确认一节的可弥补亏损部分。按波次推进：先建安全网与纯函数（可单测、零 UI 风险），再换 UI，再打通附注与导入导出，最后跨表回归与零回归门。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3"], "depends_on": ["1.1", "1.2"] },
    { "wave": 2, "tasks": ["2.4", "3.1", "3.2"], "depends_on": ["2.1", "2.2", "2.3"] },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3"], "depends_on": ["2.1", "2.3"] },
    { "wave": 4, "tasks": ["5.1", "5.2"], "depends_on": ["2.1"] },
    { "wave": 5, "tasks": ["6.1", "6.2"], "depends_on": ["2.1", "3.1"] },
    { "wave": 6, "tasks": ["7.1", "7.2", "7.3"], "depends_on": ["2.4", "3.1", "3.2", "4.1", "4.2", "4.3", "5.1", "5.2", "6.1", "6.2"] }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 安全网与基线冻结
- [x] 1.1 冻结既有行为基线（characterization）
  - 新建 `audit-platform/frontend/src/components/workpaper/__tests__/n1LossCheckBaseline.spec.ts`
  - 锁定改造前必须不变的契约：`N1_SUB_TABLE_KEYS` 四键、`buildN1SyncPayload` 的 `columns` 键集合与 `sub_table_data` 键集合恒相同、`N1-5-total-recognizable` 为 `remark` 字符串
  - 锁定 `deriveUnrecognizedFromLoss` 现行为（后续作为 legacy 兼容路径保留，不得静默改语义）
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 1.2 冻结后端 N1-5 IE 现状基线
  - 在 `backend/tests/test_n1_deferred_tax_assets_integration.py` 追加 characterization：改造前 `_SUPPORTED_SHEETS` 五张表齐备、每张 `item_id` 与前端读取键一致、`storage_field` 为 `conclusion`
  - _Requirements: 7.2, 8.1_

- [x] 2. Wave 1 — 新模型与纯函数
- [x] 2.1 重建 `useN1LossCheck`（新模型 + 派生 + 持久化）
  - 按 design «Data Models» 实现 `N1LossRow` / `N1LossComputedRow` / `N1LossLeadRow` / `N1LossTotals`
  - 派生规则：`auditedAmount = bookAmount + auditAdjustment`；`isExpired = expiryYear < auditYear`（`auditYear` 由 options 传入，禁用 `new Date()`）；届满行 `effectiveRecognized = 0`；`unrecognizedAmount = max(0, auditedAmount − effectiveRecognized)`；`recognizableAsset = effectiveRecognized × taxRate`
  - 行级标记：`splitMismatch` / `basisMissing` / `sufficiencyConflict`
  - 持久化：`N1-5-rows`（`conclusion`）、`N1-5-lead-rows`（`conclusion`）、`N1-5-total-recognizable`（`remark`，语义不变）
  - 异步 hydrate（`watch(allResponses, immediate)` + 一次性 guard）
  - _Requirements: 1.2, 1.3, 2.1, 2.2, 3.1, 3.4, 3.5, 5.1_

- [x] 2.2 迁移纯函数 `migrateLegacyLossRows` + `legacyInfo`
  - 按 design 映射规则实现；按 `expiryYear` 去重保证幂等；未知项留空不猜测
  - `legacyInfo` computed：新键为空且旧键有行时 `canImport = true`；旧键 JSON 损坏时 `canImport = false`
  - 旧键 `N1-5-loss-rows` 只读不删
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 2.3 附注取数入口 `deriveUnrecognizedLossPayload`
  - 在 `useN1DisclosureSource.ts` 新增 `N1_LOSS_ROWS_KEY_V2` 与 `deriveUnrecognizedLossPayload`（按 `expiryYear` 聚合、升序、`reason` 用 `；` 连接）
  - 新键无行时 `hasData = false`、`rows = []`
  - `deriveUnrecognizedFromLoss` 标 `@deprecated`，仅在新键无行且旧键有行时作为兼容读数并返回 `isLegacyEstimate: true`
  - _Requirements: 4.1, 4.4, 6.1_

- [x] 2.4 纯函数属性测试（Property 1-10）
  - 新建 `__tests__/n1LossCheckModel.spec.ts`：Property 1/2/3/4/10（派生规则）
  - 新建 `__tests__/n1LossMigration.spec.ts`：Property 7/8
  - 新建 `__tests__/n1UnrecognizedLossPayload.spec.ts`：Property 5/6/9
  - _Requirements: 9.1, 9.2_

- [x] 3. Wave 2 — UI 重建
- [x] 3.1 重建 `N1TabLossCheck.vue` 结构化视图
  - 列顺序对齐源模板；派生列只读 + `formula-col` 虚线 + tooltip 公式来源
  - 点选控件：`是否充足` `el-select`（是／否）、来源三选 `el-checkbox` ×3
  - 新增行先 prompt 到期年度（`/^\d{4}$/`）
  - 顶部旧版数据 alert（`legacyInfo.canImport` 时显示 + 「一键带入旧版数据」）；行级勾稽提示区
  - 引导行区（期末未分配利润 / 其中：可抵扣亏损）+ 合计区（上期不确认 / 本期审定 / 确认 / 不确认 / 可确认递延税资产）
  - AI 辅助与复核入口沿用现状（`generateN1Text`，context 全转字符串）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.3, 2.4, 3.2, 3.3, 6.1_

- [x] 3.2 扩展 `N1LossJudgmentMatrix.vue` 为可点选判断矩阵
  - 判断项列换为源模板语义（届满 / 是否充足 / 来源三选 / 依据已填 / 索引已填）
  - 新增 `readonly` prop 与 `toggle` emit；`readonly` 时行为与现状一致（零回归）
  - `N1TabLossCheck` 消费 `toggle` → `lossCheck.updateRow`
  - _Requirements: 1.6, 8.1_

- [x] 4. Wave 3 — 附注未确认一节打通
- [x] 4.1 两个附注 tab 改用新取数
  - `N1TabDisclosureListed.vue` / `N1TabDisclosureSoe.vue`：未确认明细的「可抵扣亏损」行与亏损到期表改由 `deriveUnrecognizedLossPayload` 供数
  - `hasData = false` 时该节 `el-alert`「待 N1-5 编制」，金额传 `null`
  - 「可抵扣暂时性差异」部分来源保持不变
  - _Requirements: 4.1, 4.4, 4.5, 8.2_

- [x] 4.2 结构化推送对齐（`sync-from-workpaper`）
  - 组装 `N1DisclosureSnapshot` 时 `unrecognizedRows` 追加 `{ item: '可抵扣亏损', amount: totalUnrecognized, priorAmount: totalPriorUnrecognized }`，`lossExpiryRows` 用不确认口径
  - 不改 `n1NoteSectionMap` 的子表键与 `columns`（键集合恒相同）
  - _Requirements: 4.3, 8.2_

- [x] 4.3 附注刷新联动
  - N1-5 保存后经既有事件通道使当前打开的附注页刷新未确认一节（复用 `disclosure:note-text-updated` / 底稿保存刷新链，不新增无消费者事件）
  - _Requirements: 4.2, 5.4_

- [x] 5. Wave 4 — 导入导出对齐
- [x] 5.1 后端 `_SUPPORTED_SHEETS['N1-5']` 更新为新列
  - headers / `_FIELD_MAPS` / `_NUMERIC_FIELDS` / `_INT_FIELDS`（`expiryYear`）/ `_SHEET_ITEM_ID`（改为 `N1-5-rows`）
  - `sufficient` 与来源三选的解析规则（是/否、√）
  - 派生列不进入解析结果
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 5.2 IE 契约与 Round_Trip 测试（Property 11）
  - `test_n1_deferred_tax_assets_integration.py` 追加：headers 与 field_keys 一致、`item_id === 'N1-5-rows'`、`expiryYear` 为 int、`_export_row → _parse_row` 逐字段相等
  - 前端调用方显式传 `sheet='N1-5'`（回归断言）
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 6. Wave 5 — 跨表带入不回退
- [x] 6.1 `N1-5 → N1-4` 带入可弥补亏损
  - `N1TabCalcTable.vue` 的「从 N1-5 带入可弥补亏损」按新模型取数（按到期年度或合计生成／更新行，仅填空值不覆盖手工数据）
  - `N1-5-total-recognizable` 继续写入且与 Property 4 一致
  - _Requirements: 5.1, 5.2_

- [x] 6.2 `N1-5 → N1-1` 带入「可抵扣亏损」分类行
  - 只写该分类行的未审／审定金额，不动其他分类（不清零）
  - _Requirements: 5.3_

- [x] 7. Wave 6 — 验证与收尾
- [x] 7.1 属性覆盖核对（Property 1-12）
  - 逐条核对 design «Correctness Properties» 与测试用例的映射，缺口补齐
  - Property 12（跨表键不回退）在 `n1-integration.spec.ts` 断言
  - _Requirements: 9.1, 9.2_

- [x] 7.2 零回归门
  - 前端：`n1-contract.spec.ts` / `n1-integration.spec.ts` / 本 spec 新增测试全绿；改动文件 `get_diagnostics` 全清；Vite transform 200
  - 后端：`test_n1_deferred_tax_assets_integration.py` 全绿
  - 因结构变更必须调整的断言在提交说明中记录为 basis 改变
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x]* 7.3 live Round_Trip（需 N1 实例化项目）
  - 鉴权 HTTP `create → verify → cleanup`：导入 N1-5 → `N1-5-rows` 有值且字段逐字对应 → 附注 `五、30` 未确认一节子表 rows 与合计正确 → 恢复原状（零污染）
  - _Requirements: 7.2, 4.3_

## Notes

- 旧键 `N1-5-loss-rows` 永不主动删除（Req 6.4），迁移只读它。
- 附注共用章节 `五、30` / `八、31` 的四张子表 owner 仍是 N1，N3 不得推送这两张表（见 spec `n1-disclosure-note-linkage` Decision 1 方案 A）。
- 金额取不到时一律写 `null`，禁止用 0 冒充（`buildN1SyncPayload` 的 `nz()` / `sumNullable()` 已保证）。
- `auditYear` 必须由调用方传入（`props.year` → 项目 `audit_year`），禁止在 composable 内回退当前自然年。
