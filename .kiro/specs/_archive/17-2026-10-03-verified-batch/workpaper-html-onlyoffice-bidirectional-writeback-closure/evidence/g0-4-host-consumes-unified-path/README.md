# G0-4：逐 entry 宿主统一路径谓词

> 状态：IN_PROGRESS
> 日期：2026-09-09
> 输出 milestone：`HOST-CONSUMES-UNIFIED-PATH`
> 当前 reviewed entry：`xlsx/gt-d2-accounts-receivable`

## 执行卡

<!-- G0-4-WORK-PACKAGE-JSON:START -->
```json
{
  "id": "G0-4",
  "name": "实施 HOST-CONSUMES-UNIFIED-PATH 八项逐 entry 谓词与 D2-2 诚实负例投影",
  "status": "IN_PROGRESS",
  "owner": "workpaper-html-onlyoffice-bidirectional-writeback-closure:program-governance",
  "producer_spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
  "input_gates": [
    "G0-1 program milestone registry 已通过独立 clean-checkout",
    "G0-2 denominator/discovery-only 修正已 CLOSED",
    "G0-3 Task 72 依赖 Task 74 且合法 Wave 顺序已 CLOSED",
    "D2-2 当前生产宿主仍走 /d2-sync/* 与 legacy callback，禁止伪报 unified/OnlyOffice verified"
  ],
  "output_milestone": "HOST-CONSUMES-UNIFIED-PATH",
  "modified_files": [
    "docs/operations/workpaper-html-onlyoffice-bidirectional-writeback-master-control.md",
    "backend/data/workpaper_sync_program_milestone_definitions.json",
    "backend/data/workpaper_sync_program_milestones.json",
    "backend/scripts/gen/generate_workpaper_sync_program_milestones.py",
    "backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py",
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-4-host-consumes-unified-path/README.md",
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-4-host-consumes-unified-path/index.json",
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-4-host-consumes-unified-path/d2-2/network.json",
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-4-host-consumes-unified-path/d2-2/editor-config.json",
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-4-host-consumes-unified-path/d2-2/database-snapshot.json"
  ],
  "targeted_tests": [
    "python -m py_compile backend/scripts/gen/generate_workpaper_sync_program_milestones.py backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py",
    "python backend/scripts/gen/generate_workpaper_sync_program_milestones.py --apply",
    "python backend/scripts/gen/generate_workpaper_sync_program_milestones.py --check",
    "rtk python -m pytest backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py -q --tb=short"
  ],
  "real_scenarios": [
    "definitions 必须显式封闭 8 个 host_path_entry_fact，逐 entry 各出现一次且均不得 grants_state",
    "D2-2 source/component trace 命中 /d2-sync/* 时 entry 必须投影 REQUEST_PATH_LEGACY",
    "callback query 缺 room_id/generation/doc_key/route_credential_id 任一项必须失败，必填键直接复用 callback_route.URL_BOUND_PARAMS 的源码真值",
    "runtime DB channel 为 NOT_RUN 时 application/operation/content-version 三项必须 UNVERIFIABLE，空数组不得解释为通过",
    "跨 entry decoy、错误 application-operation-version 关联、第二版本域与字面量 bidirectional=True 均不得假绿",
    "静态/source-clean 证据只能证明负例，不能提升 REQUEST_PATH_VERIFIED 或 ONLYOFFICE_VERIFIED"
  ],
  "rollback": {
    "strategy": "仅回退 G0-4 的 definitions、逐 entry evaluator、守卫、generated projection、总控参数名修正及本 evidence bundle；不回退 G0-1～G0-3，不修改任何生产 host/router/数据库数据",
    "data_migration": false,
    "reversible": true
  },
  "evidence_path": ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-4-host-consumes-unified-path/README.md"
}
```
<!-- G0-4-WORK-PACKAGE-JSON:END -->

## 开工裁决

本包只建立可复算的逐 entry 门和 D2-2 负例基线，不迁移生产路径。当前无真实 Playwright network capture、OnlyOffice 往返或同 run 业务数据库行，因此：

- D2-2 的目标投影是 `REQUEST_PATH_LEGACY`，不是 `REQUEST_PATH_VERIFIED`；
- application、operation、content version 三个运行态事实必须为 `UNVERIFIABLE/NOT_RUN`；
- manifest `capability=bidirectional`、adapter 注册、符号存在及静态源码都不能授予正向状态；
- `REQUEST_PATH_LEGACY` 只作为该门的负面 child classification，不加入全局正向 `_STATE_ORDER`，也不能满足 consumer required state；
- milestone 顶层继续 `BLOCKED`：空 producer task 是尚无正式生产迁移 owner 的真实治理 blocker，不借用无关已完成任务伪造 owner。

## 身份分列

| 层 | 当前 D2-2 值 |
|---|---|
| manifest entry | `xlsx/gt-d2-accounts-receivable` |
| adapter | `d2.receivable_detail` |
| componentType | `d2-accounts-receivable` |
| sheet selector | `D2-2` |
| physical tab | `明细表D2-2` |
| artifact | `D2-2.xlsx` |
| legacy room entry | `xlsx-sheet/D2-2/D2-2` |
| pilot matcher wp_code | `D2A` |

这些身份不得互换；特别是运行态 content version 本身没有 `entry_id`，只能经其 `operation_id` 关联到 exact-entry operation。

## 禁碰边界

- 不修改 `GtD2AccountsReceivable.vue`、`useD2SyncBridge.ts`、`GtOnlyOfficeSheet.vue`、`d2_sync_router.py`、`wp_onlyoffice_router.py` 或统一 sync kernel。
- 不删除 `/d2-sync/*`，不伪造 room-bound callback，不写业务数据库。
- 不把 deterministic source/component trace 标成 Playwright capture。
- 不把 isolated-PG classifier fixture 当作 D2-2 生产 evidence。
- G0-1/G0-2/G0-3 历史 evidence 保持历史快照，不回写新 digest 或新状态。

## 验收结果

- generator `--apply` 与 `--check` 均通过；projection digest：`d6eff0d1e9ba97e57f9d052d839ed3fd09ac2e82c19f426f8acd04848c301ee5`。
- targeted guard：`20 passed, 2 warnings`。
- D2-2 entry `xlsx/gt-d2-accounts-receivable` 投影为 `REQUEST_PATH_LEGACY`；8 项事实为 4 个静态 `fail`、3 个运行态 `unverifiable`、1 个第二版本域 `fail`。
- 顶层 `HOST-CONSUMES-UNIFIED-PATH` 仍为 `BLOCKED`，无 `REQUEST_PATH_VERIFIED`、`ONLYOFFICE_VERIFIED` 或 `CLOSED` 授权。
- G0-4 只闭合了可复算的负例基线与 evaluator；未执行真实 Playwright network capture、OnlyOffice roundtrip 或业务数据库写入，因此不构成生产迁移完成证据。
- 8 项覆盖变异已打红：删除任一 host predicate 会被 `_validate_host_path_definition` 拒绝。
- staged `diff --check` 仅剩总控文档第 3～7 行已有的 Markdown hard-break 尾随双空格；未修改该既有格式。
