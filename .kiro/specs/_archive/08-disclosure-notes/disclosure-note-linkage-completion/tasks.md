# Implementation Plan

## Overview

按五个独立可发布面分波实施，全部增量 / 灰度默认关 / 分批可回退。Wave 0 建安全网与共享封装；Wave 1 自动同步试点（N1）；Wave 2 URL 收敛 + 契约守卫；Wave 3 合并附注 V2 落库；Wave 4 stale 回填 + 公式灰度按项目；Wave 5 自动同步按循环铺开；Wave 6 收尾验证。各 Wave 独立，失败可单独回退。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "description": "安全网 + 共享封装" },
    { "wave": 1, "tasks": ["2.1", "2.2"], "description": "自动同步试点 N1 + 属性测试" },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3"], "description": "URL 收敛迁移 + 契约守卫" },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3"], "description": "合并附注 V2 落库 + 穿透激活 + PBT" },
    { "wave": 4, "tasks": ["5.1", "5.2", "6.1", "6.2"], "description": "stale 回填脚本 + 公式灰度按项目 + 看板暴露" },
    { "wave": 5, "tasks": ["7.1", "7.2", "7.3", "7.4"], "description": "自动同步按循环铺开（D/E/F、G、H、I/J/K/M/N）" },
    { "wave": 6, "tasks": ["8.1", "8.2"], "description": "零回归门 + live/Playwright*" }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 安全网与共享封装
  - [x] 1.1 建 characterization 零回归基线（后端）
    - 跑并记录既有 `disclosure` / `consol` 相关测试当前绿状态作为基线（`test_wp_disclosure_sync*` / `test_consol_disclosure_v2` / `test_note_readiness_and_stale` 等）
    - 确认 `CONSOL_NOTES_V2_ENABLED=False` / `DISCLOSURE_NOTE_FORMULA_ENABLED=False` 时现状行为，作为 Property 9 / Property 12 的对照锚点
    - _Requirements: 6.1_
  - [x] 1.2 新建前端共享 `useDisclosureAutoSync` composable
    - `composables/useDisclosureAutoSync.ts`：`scheduleAutoSync(syncFn)`（防抖 800ms + 只读 gate + `.catch(()=>{})` 静默）+ `cancelPending()`
    - 不接任何 tab，仅提供封装 + 单测占位
    - _Requirements: 1.2, 1.3, 1.4, 1.6_

- [x] 2. Wave 1 — 自动同步试点（N1）
  - [x] 2.1 N1 披露 tab 接入自动同步
    - `N1TabDisclosureListed.vue` / `N1TabDisclosureSoe.vue`：保存成功回调末尾 `autoSync.scheduleAutoSync(syncToDisclosureNotes)`；`isReadonly` gate；`onBeforeUnmount(cancelPending)`
    - 手动「同步到附注」按钮保留不变（同源 payload + canonical URL）
    - _Requirements: 1.1, 1.5, 1.7_
  - [x] 2.2 自动同步属性测试
    - `useDisclosureAutoSync.spec.ts`：Property 1（防抖合并）/ 2（失败静默不抛）/ 3（只读不触发）/ 4（同源 syncFn）
    - _Requirements: 7.1_

- [x] 3. Wave 2 — URL 收敛 + 契约守卫
  - [x] 3.1 迁移 H3/H4 到 canonical
    - `H3TabDisclosureListed/SOE`（`/api/disclosure-notes/{pid}/…` → canonical）、`H4TabDisclosureListed`（去 `{year}` 段 → canonical + payload 带 year）
    - 产出逐字节等价（section/表格/说明/年度不变）
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 3.2 迁移 H5/J1/D6 到 canonical
    - `H5TabDisclosureSoe` + `J1TabDisclosureListed/Soe`（`/api/disclosure-notes/{pid}/{year}/{section}/…` → canonical）、`useD6Disclosure.ts`（**先核实相对路径 `sync-from-workpaper` 实际拼接的完整 URL 与 baseURL 前缀**，再迁 canonical）；payload 显式带 `useAuditContext().year`
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 3.3 URL 契约守卫
    - `disclosureSyncUrlContract.spec.ts`：扫描披露 tab 断言无非 canonical `sync-from-workpaper` 字面量（GtCNoteTable 等 allowlist 例外）
    - _Requirements: 2.5, 7.2_

- [x] 4. Wave 3 — 合并附注 V2 落库
  - [x] 4.0 核实 V2 章节 table_data 与附注渲染契约兼容性
    - 读 `aggregate_section` 产出的 `table_data` 结构 vs 前端附注模块渲染契约（`sub_table_data`/`_tables`/`headers`）；判定"直接落库可渲染"或"需结构适配"或"回退仅落 provenance"（design §组件3 三选一）
    - 结论写入 4.1 落库策略；避免落库后前端合并章节空表/报错
    - _Requirements: 3.1, 6.5_
  - [x] 4.1 实现 `_persist_consol_sections_v2`
    - `consol_disclosure_service.py` 新增落库函数：逐章节 upsert（active→软删复活→新建）、写 `source_project_id`/`consolidation_breakdown`/`last_sync_source='consolidation'`、`_resolve_section_meta` 解析 title/account_name（source_template 取自 `generate_full_consol_notes` 的 `template_type` 参数）、`_manual_override` 锁定跳过、逐章节 fail-open、按 4.0 结论决定 table_data 落库形态
    - `generate_full_consol_notes` 末尾 `if settings.CONSOL_NOTES_V2_ENABLED: await _persist_consol_sections_v2(...)`（默认 False 不落库）；顺带把 `consol_cascade_refresh_service` 的 `getattr(settings,"CONSOL_NOTES_V2_ENABLED",True)` fallback 默认 True 对齐 config 的 False（防属性缺失时误落库）
    - _Requirements: 3.1, 3.3, 3.4, 3.5, 3.6_
  - [x] 4.2 落库幂等 / fail-open / 开关关零改动 PBT
    - `test_consol_notes_v2_persist.py`：Property 7（幂等+不覆盖锁定）/ 8（fail-open）/ 9（开关关零改动）
    - _Requirements: 7.3_
  - [x] 4.3 穿透激活验证
    - 断言落库后 `note_consol_drilldown_service` 对该章节 `has_breakdown=true` 且 `by_company` 非空（Property 10）
    - _Requirements: 3.2, 7.3_

- [x] 5. Wave 4a — stale 回填
  - [x] 5.1 stale 回填脚本
    - `backend/scripts/backfill_note_stale_source.py`：只读判定（有 REPORT linkage→report / 否则 report_fallback）+ 单条 UPDATE + `--dry-run`/`--apply`，幂等
    - _Requirements: 4.1, 4.4, 4.5_
  - [x] 5.2 回填属性测试
    - `test_backfill_note_stale_source.py`：Property 11（幂等 / is_stale=false 不写 / 无法判定回退 report_fallback）
    - _Requirements: 4.2, 4.3, 7.4_

- [x] 6. Wave 4b — 公式灰度按项目
  - [x] 6.1 统一入口 + 消费点改造
    - 新建 `note_formula_gray_service.is_note_formula_enabled(db, project_id)`（全局 True 全开 / 否则查 `wizard_state` / 异常 fail-open False）
    - 4 处消费点（`disclosure_engine` ×2 / `note_source_resolvers._formula_enabled` / `report_note_sync_service`）改调它；`generate_notes` 入口解析一次传下游
    - `PUT /api/disclosure-notes/{pid}/formula-gray`（manager+，写 `wizard_state` JSONB，`flag_modified`）
    - _Requirements: 5.1, 5.3, 5.4, 6.1_
  - [x] 6.2 就绪度暴露 + 公式灰度 PBT
    - `build_readiness().summary` 加 `formula_enabled`；`NoteReadinessPanel` 显示"公式求值：已启用/未启用"
    - `test_note_formula_gray_service.py`：Property 12（按项目 + 关闭态零改动 + fail-open）/ 13（看板一致）
    - _Requirements: 5.2, 5.5, 7.5_

- [x] 7. Wave 5 — 自动同步按循环铺开
  - [x] 7.1 D / E / F 循环披露 tab 接入自动同步
    - D1/D2/E1/F1/F2/F3 各披露 tab 保存成功回调接 `scheduleAutoSync`（复用 Wave 0 封装，一行接入）
    - _Requirements: 1.1, 6.3_
  - [x] 7.2 G 循环披露 tab 接入
    - G1/G2/G3/G6/G7/G10/G11/G13/G14 披露 tab 接入
    - _Requirements: 1.1, 6.3_
  - [x] 7.3 H 循环披露 tab 接入
    - H1/H2/H3/H4/H5/H6/H8/H9/H10 披露 tab 接入（H 系已在 Wave 2 收敛 URL）
    - _Requirements: 1.1, 6.3_
  - [x] 7.4 I / J / K / M / N 循环披露 tab 接入
    - I1/I2/I3/I4/I5/I6/J1/K1/M*/N1 披露 tab 接入
    - _Requirements: 1.1, 6.3_

- [x] 8. Wave 6 — 收尾验证
  - [x] 8.1 全量零回归门
    - 全套 disclosure/consol 相关后端测试 + 前端 disclosure vitest 全绿；契约守卫 --strict 通过；`git stash` 对照证无新增回归；改动文件 get_diagnostics 全清 + 前端 Vite transform 200 + 后端 AST OK
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [x]* 8.2 live / Playwright 端到端
    - 真实项目开 `CONSOL_NOTES_V2_ENABLED` → 生成合并附注 → 穿透 `has_breakdown=true`（create→verify→还原，零污染）
    - 披露 tab 保存后自动同步 → 就绪度看板 / 状态条转"已同步"；公式灰度按项目开启后 readiness 显示"已启用"
    - _Requirements: 1.5, 3.2, 5.2_

## Notes

- **零回归红线**：`CONSOL_NOTES_V2_ENABLED` / `DISCLOSURE_NOTE_FORMULA_ENABLED` 全局默认保持 False；未接自动同步的 tab、既有手动按钮、既有后端端点、`consol_note_data` 存储全部不动。
- **不碰表**（用户拍板）：本 spec 无任何 drop / 清空表操作；空 `note_*` 表与备份表清理另开运维工单。无新增 DB 列（V2 用既有 `source_project_id`/`consolidation_breakdown`；stale_source V129 已加；公式项目 override 存 `wizard_state` JSONB）。
- **迁移取号**：本 spec 不新增迁移文件（stale 回填走脚本）。
- **URL 迁移铁律**：改 URL 只动前端调用方，后端历史端点保留；payload 结构不变、显式带 year。
- **自动同步铺开**：`useDisclosureAutoSync` 一处封装、各 tab 一行接入；按循环分批（Wave 5），每批独立可回退。
- **V2 落库复用**：`_persist_consol_sections_v2` 复用单体 `sync_from_workpaper` 的复活/元数据/幂等/manual-override 范式，不新造第二套 upsert 语义。
- **live 铁律**：真实项目验证用 create→verify→还原 + `RESTORED_IDENTICAL` 断言，避免污染；Playwright 注意并发会话 SSE 劫持（addInitScript 中和 EventSource）。
