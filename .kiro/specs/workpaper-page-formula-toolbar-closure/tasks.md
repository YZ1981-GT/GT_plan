# Implementation Plan: 底稿页公式工具栏与公共能力壳层闭环

## Overview

实施顺序为“消费契约/清册 → 权限前置 → location runtime → 真实 toolbar outlets → dialog/provider/API → AI/review/rail → 行为与浏览器证据”。所有任务 required。

本 spec 的唯一性边界仅为 workpaper route。TB/report/note 等 domain-owned dialog 只登记 exclusion evidence，不纳入删除。共享 wire 类型 import 自 `G-C0`；本 spec 不复制。

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 0, "name": "契约与只读基线", "tasks": [1]},
    {"wave": 1, "name": "host 清册与红守卫", "tasks": [2]},
    {"wave": 2, "name": "capability 权限前置", "tasks": [3]},
    {"wave": 3, "name": "唯一 location runtime", "tasks": [4]},
    {"wave": 4, "name": "toolbar、provider 与 review 基础", "tasks": [5, 7, 10]},
    {"wave": 5, "name": "dialog 草稿与 AI 去重", "tasks": [6, 9]},
    {"wave": 6, "name": "用户公式 v2 与公共 shell", "tasks": [8, 11]},
    {"wave": 7, "name": "响应式、错误与旧链删除", "tasks": [12]},
    {"wave": 8, "name": "行为、变异与 F-SHELL", "tasks": [13]},
    {"wave": 9, "name": "五宿主 Playwright", "tasks": [14]},
    {"wave": 10, "name": "全量清册与归档", "tasks": [15]},
    {"wave": 11, "name": "实际接线补验", "tasks": [16]},
    {"wave": 12, "name": "定向与浏览器补验", "tasks": [17]}
  ],
  "critical_path": [1, 2, 3, 4, 5, 6, 8, 12, 13, 14, 15],
  "hard_dependencies": {
    "2": [1],
    "3": [1, 2],
    "4": [1, 2, 3],
    "5": [2, 3, 4],
    "6": [4, 5],
    "7": [3, 4],
    "8": [3, 6, 7],
    "9": [3, 4, 5],
    "10": [3, 4],
    "11": [4, 5, 9, 10],
    "12": [6, 8, 11],
    "13": [6, 7, 8, 9, 10, 11, 12],
    "14": [13],
    "15": [14],
    "16": [15],
    "17": [16]
  },
  "parallelizable": [
    [5, 7, 10],
    [6, 9],
    [8, 11]
  ],
  "external_dependencies": {
    "consumes": [
      {"milestone": "G-C0", "producer_spec": "workpaper-guidance-content-closure", "required_by_tasks": [1], "on_missing": "BLOCKED"},
      {"milestone": "G-ID", "producer_spec": "workpaper-guidance-content-closure", "required_by_tasks": [4], "on_missing": "BLOCKED"},
      {"milestone": "G-RAIL", "producer_spec": "workpaper-guidance-content-closure", "required_by_tasks": [11], "on_missing": "BLOCKED"}
    ],
    "produces": [
      {"milestone": "F-SHELL", "task": 13, "consumers": ["workpaper-guidance-content-closure:G20", "custom-workpaper-template-ingestion-and-sync-closure:X12", "custom-workpaper-template-ingestion-and-sync-closure:X18"]}
    ]
  }
}
```

## Tasks

### Contracts, Inventory and Permission

- [x] 1. 消费 `G-C0` 并冻结 workpaper-route 红基线
  - import/校验 CanonicalWorkpaperLocation、EvidenceEnvelope、GuidanceRailAdapter major version；不建立同名本地接口
  - 记录 nodeKey payload、唯一全局 dialog、单元格 FormulaEdit 链、旧 dict API、formula_type 双义、audit warning commit、重复 AI/review/fixed rails
  - 明确 TB/report/note domain dialogs 为 out-of-scope，不误计重复
  - 冻结共享文件/并发 WIP，文件存在不勾 task
  - _Requirements: 1.4, 2.1, 5.1, 5.3, 8.1, 8.3, 8.6, 13.1_

- [x] 2. 建立动态 host/outlet/duplicate inventory 与 mounted 红守卫
  - 从 renderer/render-config/adapter telemetry/runtime custom entries 推导 route scope、host、granularity、outlets 与公共能力
  - 清册重复 AI/ReviewPanel/rail/bare AI/fixed offset 和 domain exclusions，保存 run/digest
  - mounted 测试证明当前 CSS class 非 slot、outlet/入口/manager 唯一性红基线；grep 不计能力
  - 2026-09-08：`src/shell/formula/*`（inventory + telemetry + scanners + domain exclusions）；
    vitest 8 passed；证据 `basis/T02-host-inventory-run.json`；
    变异 3/3 RED（`mutate_formula_task2_host_inventory.py`：假 slot / CSS-as-outlet / 无 telemetry 却 supported）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 13.2_

- [x] 3. 前置 WorkpaperCapabilitySnapshot 与服务端 capability matrix
  - 覆盖 formula view/edit/history、AI review/assist、human review、guidance 和 disabled reasons/expiry
  - snapshot 未 ready/过期/epoch 不匹配时 provider/save/AI/review/rail 全 blocked
  - 所有 endpoint 服务端复验 visibility/project/wp/sheet/role；打开能力响应权限变化
  - 无权状态中文可解释且不泄漏 formula/thread/guidance metadata
  - 2026-09-08：`workpaper_capability` matrix + snapshot；路由
    `GET/POST /api/workpapers/{wp_id}/capability-snapshot|capability-assert`；
    前端 `assertCapabilityAllowed`；pytest 11 + vitest 3；变异 3/3 RED
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

### Location, Toolbar and Formula

- [x] 4. 消费 `G-ID` 并实现唯一 CanonicalLocationState runtime
  - `uninitialized/blocked/ready` 判别状态；ownerEpoch 跨 owner 单调、contextRevision 同 owner 单调
  - HTML/Univer/OnlyOffice/Grid/Word adapters 只 dispatch stable facts，shell reducer 唯一发布 C0 ready snapshot
  - 不可观测边界使用 page/sheet/document/whole-workbook；删除 label/下标/nodeKey identity
  - 异步结果按 subject+epoch+revision+capability gate 丢弃旧值
  - 2026-09-08：`gidSheetIdentity.ts` + `canonicalLocationState.ts`；vitest 7 + backend 3；变异 3/3 RED
  - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 5. 实现真实 named outlets、ToolbarHostAdapter 与 placement arbiter
  - 在 primary toolbar 的 AI 后/金额单位前增加真实 named slot；`GtWpToolbar` 增真实 compatibility slot
  - registration lease 覆盖 pending/primary/fallback/blocked；primary 未裁决时 fallback 不抢挂
  - mount/unmount/owner epoch 重算，拒绝重复/跨 owner/collision；active DOM 恰好一个入口或 blocked
  - 入口直接可见，不进入更多；CSS class 只作样式
  - 2026-09-08：`toolbarOutletArbiter.ts` + `WorkpaperPrimaryCapabilitiesHost.vue`；
    ThreeColumnLayout AI→primary→金额单位；GtWpToolbar compatibility slot；
    vitest 5；变异 3/3 RED
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 6. 接唯一 FormulaManager command 并实现 dirty draft pin
  - command 携带 C0 location、capability snapshot、ownerEpoch/revision；nodeKey 仅迁移 metadata
  - `ThreeColumnLayout` 保持 workpaper route 唯一 dialog owner；页面入口不误开 FormulaEditDialog
  - clean 时跟随 latest；dirty 时 pin 原 location，保存/丢弃/取消显式选择并重验权限/base version
  - 空位置显示 empty/partial/blocked，不造占位行
  - 2026-09-08：`openFormulaManagerCommand.ts`；layout EventBus→legacy metadata adapter；
    vitest 4；变异 dirty-follow RED
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 7. 建立正交 FormulaProviderRegistry、AggregateResult 与 lineage
  - origin/ruleKind/engine/protection 四维 descriptor，formulaFunction/ruleCategory 分字段
  - adapter 覆盖 platform/user/auto_data/logic+reasonableness/frontend engine，不复制真源
  - stable id+semantic digest 去重；collision blocked；provider timeout/error 形成 partial/blocked
  - 按 location granularity 查询，批量补 ACNR upstream/downstream/stale/current value/context fingerprint
  - 2026-09-08：`formulaProviderRegistry.ts` 五 adapter + aggregate + lineage enrich；
    vitest 5；变异 collision-takes-first RED
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 8. 上线 user formula API v2、逐项冲突、历史与 durable audit
  - 新 v2 list/batchMutate/history contract；旧 dict API 退出新能力路径
  - create/update/delete/restore 每项带 operation/action/location/target/function/category/refs/baseVersion/reason
  - 返回 per-item success/conflict/forbidden/invalid/error、field conflicts 和 overall success/partial/failed
  - stale/partial 保留草稿；恢复生成新版本；audit/outbox 失败阻断 commit
  - 2026-09-08：`user_formula_v2.py` + `wp_user_formulas_v2`；FE paths/types；
    pytest 5 + vitest 2；变异 audit-warn-then-commit RED（InMemoryAuditGate；durable DB/outbox 仍属 T13 收口）
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

### AI, Review and Shell

- [x] 9. 分离 AI review/assist taxonomy 并去除重复承载链
  - page/batch AI review、AI assist、human review、lifecycle review 使用不同 action/type/a11y 名称
  - 保留公共 AI review toolbar，按 inventory 成组删除业务按钮/refs/handlers/ReviewPanel
  - page/batch scope 绑定 ready location/selection + capability epoch
  - AI assist 只走 DSH adapter/PlatformAiChatPanel；无权/不支持显示 reason
  - 2026-09-08：`aiActionTaxonomy.ts` + D2 改挂 `GtWpAiReviewToolbar`；
    vitest 4；变异 assist-borrows-review RED
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 10. 统一 HumanReviewProvider 并迁移 canonical thread keys
  - canonical key 为 project/wp/sheetUid-or-whole/anchorId；五宿主共享 provider/scaffold
  - 先生成 legacy mapping/collision/orphan dry-run，再幂等迁移并保存 rollback evidence
  - create/reply/resolve/reopen/read 服务端分能力；刷新耐久、切页隔离
  - 无细粒度 anchor 时诚实降为 page/sheet/document/whole，不伪造 cell
  - 2026-09-08：`humanReviewProvider.ts` + `review_thread_keys.py`；
    evidence `basis/T10-review-key-migration-*.json`；vitest 3 + pytest 3；变异 2/2 RED
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [x] 11. 消费 `G-RAIL` 并实现 WorkpaperCapabilityShell/right-rail
  - shell 成为 location/toolbar/dialog command/capability/rail 唯一 owner
  - review→guidance→ai 单一 arbiter；guidance import adapter，AI 只 DSH，review 只统一 provider
  - 同时最多一个展开，preserve draft；visible=false/epoch stale/denied 不渲染不占位
  - DOM/gap/top/right/z-index/width/content inset 全归 shell；custom 只能消费 contract
  - 2026-09-08：消费 `shell/guidance` G-RAIL；`rightRailArbiter.ts` +
    `WorkpaperCapabilityShell.vue` + layout tokens；WorkpaperEditor 挂壳；
    vitest 7；变异 invisible-occupies-slot RED；live capability/DSH inject 仍属 T12
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [x] 12. 完成响应式、a11y、错误可见性与旧链删除
  - 1280/1440/1920 + 200% zoom 统一 shell layout；Word 可达则纳入，豁免需有期证据
  - keyboard/focus/Escape/scroll lock/return focus/中文 accessible name
  - provider/save/review/adapter/location 错误保留工作并结构化显示；日志不含敏感正文
  - 删除旧 nodeKey-only consumers、重复 dialog/events/bare mounts/fixed offsets/hardcoded availability 与 audit warning commit
  - 2026-09-08：`shellResponsiveLayout` / `shellA11y` / `shellStructuredError` /
    live `fetchCapabilitySnapshot` + DSH provide/inject；`GtWpReviewRail` 去 fixed 并在 shell 下抑制；
    Word exemption `basis/T12-word-host-exemption.json`；vitest 8；变异 broad-catch-success RED
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

### Evidence and Closure

- [x] 13. 定向行为、变异准确 RED 并发布 `F-SHELL`
  - 覆盖 inventory/location/capability/outlet/dialog/provider/v2 API/AI/review/rail/a11y
  - 变异 CSS-class-as-slot、fallback 抢挂、location 缺失、dirty 跟页、混合维度、collision 取首、旧 dict、audit warning commit、重复 AI、legacy thread key、invisible 占位
  - 锚点唯一，记录 RED/GREEN/ANCHOR-MISS/WRONG-TEST，finally 字节复原
  - conformance 全绿后发布 F-SHELL contract/evidence，供 custom X11/X12 消费
  - 2026-09-08：`fShellContract.ts` + `fShellConformance.spec.ts`（15）；
    `mutate_formula_task13_fshell.py` 11/11 RED；
    evidence `evidence/F-SHELL/{contract,envelope}.json` + `basis/T13-mutation-report.json`
  - _Requirements: 13.1, 13.2, 13.3, 13.5_

- [x] 14. Playwright 五宿主、权限、冲突与三 viewport 实测
  - 所有 reachable HTML/Univer/OnlyOffice/Grid/Word 首次、切 sheet/section/cell/document、快速切换
  - primary/fallback mounted 顺序、唯一 dialog、dirty pin、五类 provider、partial/collision、v2 conflict/audit failure
  - AI review/assist scope、review migration/thread、guidance rail、single-open 与权限 revalidate
  - 1280/1440/1920、zoom/keyboard；保存 location/capability/network/DOM/trace/截图/console/evidence
  - 2026-09-08：`e2e/workpaper-formula-toolbar-shell.spec.ts` 4/4 PASS；
    html/univer/onlyoffice/word reachable，grid skipped；
    evidence `basis/T14-playwright/` + `basis/T14-playwright-closure.md`；
    修复 `WORKPAPER_SHELL_ACTIVE_KEY` 拼写分叉与 `outletSlots` 去 crypto 阻断壳挂载
  - _Requirements: 13.4, 13.5, 12.1, 12.2, 12.5_

- [x] 15. 全量清册门、tracked 产物与归档
  - required workpaper hosts 全裁决；entry/manager/AI/review/rail 重复=0，domain exclusions 有证据
  - blocked host 仅允许有效 exemption；unconsumed adapter/stale evidence/旧 dict 新调用/audit warning commit=0
  - clean checkout 重跑定向/变异/Playwright；正式 schema/migration/tests/evidence 全 tracked
  - 回填真实数字、owner、blocker 和 INDEX；F-SHELL 的 producer fixtures/contract conformance 可在无 custom 实例时独立复现后归档
  - 2026-09-09：`fullInventoryGate.ts` + vitest 2 PASS；html/univer/onlyoffice/word reachable，grid exempted；
    forbidden duplicates=0；`inventoryDigest` 回填 F-SHELL envelope；
    evidence `basis/T15-*` + `evidence/F-SHELL/INDEX.md`；变异 3/3 RED；
    复盘修复：scanner 假阳、`outletSlots`/`sha256Hex` 去 browser crypto、Word exemption superseded
  - _Requirements: 13.6, 1.5, 12.5_

- [x] 16. 页面入口真实接线补验
  - compatibility 插槽附件前入口、唯一 Layout dialog、真实五字段、全册聚合、筛选重置、错误与请求隔离、用户 tab 真 wpId。
  - 历史 Task 1-15 不作为本次接线完成证据。
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [ ] 17. 定向行为测试与 localhost:3030 Playwright 补验
  - 验证真实组件消费、错误、慢旧请求、重开筛选和用户 tab；登录阻塞如实记。不 commit。
  - 2026-09-10：4 文件 19 例 PASS（新增真实 Dialog setup/watchers 4 例）；移除主查询 isCurrent 门控后竞态用例准确 RED，恢复后全绿。本次修改文件 git diff --check PASS。
  - Playwright 已访问 localhost:3030，重定向 /login?redirect=/；无可用登录态，页面按钮 DOM/真实底稿请求端到端验收未完成，因此本项保持未勾选。未 commit，spec 与新增测试尚未入库。
  - _Requirements: 14.6_

## Property Coverage

| Property | Implemented/verified by Task |
|---|---|
| 1 | 1, 2, 13, 15 |
| 2 | 1, 4, 13 |
| 3 | 4, 13, 14 |
| 4 | 3, 13, 14 |
| 5 | 2, 5, 13, 14, 15 |
| 6 | 6, 13, 14 |
| 7 | 6, 8, 13, 14 |
| 8 | 7, 13, 14 |
| 9 | 7, 13, 14 |
| 10 | 7, 13, 14 |
| 11 | 8, 13, 14 |
| 12 | 8, 12, 13, 14 |
| 13 | 9, 13, 14 |
| 14 | 10, 13, 14 |
| 15 | 5, 11, 12, 13, 14 |
| 16 | 11, 13, 14 |
| 17 | 12, 13, 14 |
| 18 | 12, 13, 14 |
| 19 | 1, 11, 13 |
| 20 | 13 |
| 21 | 14, 15 |
| 22 | 13, 14, 15 |
| 23 | 16, 17 |
| 24 | 16, 17 |

## Completion Notes

- `F-SHELL` 在 Task 13 行为/变异 conformance 通过后发布，不以实现文件存在提前发布。
- Task 15 回填 `inventoryDigest` 并写 `evidence/F-SHELL/INDEX.md` 后才可宣称归档闭环。
- `GtWpToolbar.__right` 不是 slot；只有真实 named outlet + mounted registration 才算能力。
- capability 是所有 provider/action 的前置依赖，不允许最后一波补权限。
- dirty draft 始终 pin 原 location；无草稿时才 follow latest。
- Word 可达即实测，不可达也必须有正式 exemption，不能从 denominator 消失。
- Grid 无实例时必须有正式 exemption（T15），不得 silent skip。
