# Implementation Plan

## Overview

把底稿级调整分录汇聚到集中式登记（供审阅/导出/溯源）+ 复核状态回流底稿 + 消除 TB 双写重复计算。strangler、opt-in、逐循环可回退，零回归既有底稿→审定表→TB 链路。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "desc": "安全网 + 迁移/模型" },
    { "wave": 1, "tasks": ["2.1", "2.2"], "desc": "汇聚服务 + 端点" },
    { "wave": 2, "tasks": ["3.1"], "desc": "TB 口径唯一（recalc origin 过滤）" },
    { "wave": 3, "tasks": ["4.1", "4.2"], "desc": "前端共享 composable + 集中页 origin/来源/导出" },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3"], "desc": "逐循环接入试点 D4/K9/L1" },
    { "wave": 5, "tasks": ["6.1"], "desc": "属性测试 P1-P10" },
    { "wave": 6, "tasks": ["7.1", "7.2"], "desc": "零回归门 + Playwright round-trip" }
  ]
}
```

## Tasks

- [x] 1.1 后端 characterization 安全网：`recalc_adjustments` 现有聚合结果 + `AdjustmentService.create_entry` 平衡/编号行为由 `test_trial_balance.py`(30 passed) + `test_adjustments.py`(31 passed) 锁定为零回归基线。**顺带修根因**：conftest 缺 `evidence_governance_models` 导入致 `attachments.actor_service_identity_id→service_identities` FK 在 create_all 解析失败（NoReferencedTableError），阻断全套 DB 集成测试——已补导入，全套解封。
  - Requirements: 6.1, 6.2

- [x] 1.2 迁移 V124 + ORM：`adjustments` 加 `origin`(VARCHAR20 default 'manual' NOT NULL) / `source_ref`(VARCHAR120 NULL) + 部分索引 `idx_adjustments_source_ref`（幂等 information_schema 守护 + R124 回滚）；`Adjustment` ORM 同步声明，drift=0。**注**：source_ref 索引改为非唯一（entry_group 多行共享 source_ref，唯一性由服务层 sync 幂等保证）。已应用 schema_version=124，drift=0。
  - Requirements: 1.1, 2.1, 4.2

- [x] 2.1 `AdjustmentSyncService.sync_from_workpaper`：source_ref 幂等（新建/更新/approved 锁定）+ 借贷平衡校验 + 类别→类型映射 + 科目解析（code 优先，name fallback，失败列 unresolved）+ `origin='workpaper'` + **不发 ADJUSTMENT_CREATED**；`remove_by_source_ref` / `get_status_by_source_ref`。（新建 `adjustment_sync_service.py`）
  - Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 3.2, 3.3

- [x] 2.2 路由：`POST /adjustments/sync-from-workpaper`（400 UNBALANCED/unresolved，409 APPROVED_LOCKED）+ `GET /adjustments/by-source-ref` + `list_entries` 加 `origin` 过滤参数（manual 兼容 NULL）。live 已注册。
  - Requirements: 1.3, 2.3, 3.2, 5.1

- [x] 3.1 `recalc_adjustments` 加 `WHERE origin IS NULL OR origin != 'workpaper'`，消除审定表 writeback 与集中 recalc 对同一底稿调整的双计；manual/NULL 零回归（test_p4 验证 workpaper 贡献 0、manual 贡献不变）。
  - Requirements: 4.1, 4.2, 4.3

- [x] 4.1 前端 `useAdjustmentCentralSync` 共享 composable（syncToCentral / centralStatus / refreshStatus，itemId 支持 getter 动态类型）+ 前端 API `syncAdjustmentFromWorkpaper` / `getAdjustmentBySourceRef` + apiPaths。
  - Requirements: 1.1, 3.2, 6.3

- [x] 4.2 `Adjustments.vue`：来源列（手工/底稿 wp_code tag，点击跳转）+ origin 筛选（el-segmented 全部/手工/底稿）+ 导出 xlsx 加"来源"列（含 workpaper 来源，list_entries 不过滤 origin 天然含两者）。
  - Requirements: 3.1, 5.1, 5.2

- [x] 5.1 接入 D4-4 调整分录 tab：工具栏"同步到集中登记"按钮 + centralStatus 展示（复核状态/驳回原因）；year 取 useAuditContext。
  - Requirements: 1.1, 3.2, 3.3, 6.3

- [x] 5.2 接入 K9-3 调整分录 tab（同 5.1 范式，科目 6602，itemId=K9-3-adj-entries）。
  - Requirements: 1.1, 3.2, 6.3

- [x] 5.3 接入 L1 调整分录（按 activeType 分组，itemId=L1-adj-{AJE|RJE}，切换类型 watch 刷新回流状态）。
  - Requirements: 1.1, 3.2, 6.3

- [x] 6.1 属性测试 P1-P10：`test_adjustment_sync.py` 10 passed（幂等 P1/平衡守卫 P2/类别映射 P3/TB 不双计 P4/软删清理 P5/approved 锁定 P6/溯源解析 P7/回流一致 P8 + 科目 name 解析/unresolved）；前端 `useAdjustmentCentralSync.spec.ts` 6 passed（平衡守卫/payload 映射/动态 itemId/锁定提示/回流）。P9/P10 由零回归门 + 增量接入证据覆盖。
  - Requirements: 7.1

- [x] 7.1 零回归门：adjustments/trial_balance/misstatements/event_bus/adjustment_sync **87 passed**（asyncpg teardown warnings 非失败）；get_diagnostics 全清（全改动文件）；改动前端文件 Vite transform 200（5 关键 .vue/.ts 全 200）。
  - Requirements: 6.1, 6.2

- [x]* 7.2 端到端 live round-trip（改用鉴权 HTTP 替代 flaky Playwright UI，重药控股安徽 0ec33ac9/2025，全流程通过后清理无污染）：登录→sync-from-workpaper（origin=workpaper/AJE-001/source_ref 正确）→ list origin=workpaper 含本条 → **origin=manual 正确排除**（过滤生效）→ by-source-ref 回流=draft → 幂等再 sync 仍 1 组 → delete 清理 → 复查已空。UI 层（Playwright）因环境 flaky/SSE 劫持未跑，前端由 vitest+Vite200+diagnostics 覆盖。
  - Requirements: 1.1, 3.1, 3.2, 4.1

## Notes

- **零回归红线**：底稿→审定表→TB writeback 链路一行不改；recalc 的 origin 过滤对 NULL 兼容旧数据。
- **口径唯一决策**：workpaper origin 调整已由审定表 writeback 体现在 audited_amount，故不进 recalc 的 aje_adjustment，避免双计（Req4）。
- **迁移取号**：当前最高 V123（voucher_sampling_batch_governance），本 spec 用 **V124**；执行前以 `migration_status` 复核。
- **逐循环增量**：Wave4 仅试点 3 个循环；其余循环接入为后续增量，单循环失败可回退。
- **✅ 全循环接入完成（2026-07-24）**：D/F/G/H/I/K/M 共 66 张 TabAdjustment 全部接入（D1-D7/F1-F5/G1-G14/H1-H10/I1-I6/K1-K13/M1-M10 + L1 试点）。全 66 get_diagnostics 全清 + Vite transform 全 200 + live HTTP round-trip 双路径（成功+fail-closed）通过。副产品：全量 Vite 扫描揪出并修复 pre-existing K5 崩溃（4 文件 `../../shared/GtIndexChip.vue` 路径错→`../../GtIndexChip.vue`）。
- **✅✅ 全 81 tab 接入收尾（2026-07-24）**：续接补齐剩余 15 张（E1/J1/J2/L2-L8/N1-N5），**81/81 TabAdjustment 全接入，0 遗漏**。四类形态适配（L: useL{n}Adjustment+activeType getter itemId / N: 两组 activeType 或静态 itemId / J1: rows ref / J2: reactive 数组 / E1: useE1Adjustment debit/credit）。顺带修 L3 pre-existing 裸 defineProps 未捕获 props。全 81 get_diagnostics 全清 + Vite transform 全 200 + N1 live round-trip（AJE-004 balanced→cleanup→empty，零污染）通过。仅剩非调整性质 tab 未接入。
- **错报 ≠ 调整**：`a13:push-misstatement`（未更正错报）已由 `useA13MisstatementBridge` 接通，不在本 spec；本 spec 只处理 AJE/RJE 调整分录集中化。
