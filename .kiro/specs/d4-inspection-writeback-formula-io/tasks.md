# Implementation Plan

## Overview
D4-13/14/15/16 检查表四表的导入导出、公式预设、风险发现链、行为守卫与真栈验收。

## Tasks
- [x] 1. 源模板核定与稳定 ID gate：逐 sheet 读取源 xlsx，核定 D4-13/14/15/16 列头、嵌套结构、item_id、动态 id、未知映射、日期/空零未知三态与文本 N/A。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.1_
- [x] 2. 共享公式与双模式 gate：接入 F-SHELL preset/custom expression/refs/params/scope；后端权威执行、前端同定义预览；接入统一 mutation、sync、三方合并、contract、representation 与 durable ack，解析失败保留原值。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.2_
- [x] 3. 实现 D4-13/15/16 IO：专用 parser/exporter、嵌套/英文 key 对齐、D4-13 双 item 文本锚点、D4-15 `D4-15-items`、D4-16 差异重算与动态 id 保留。
  - _Requirements: 1.2, 1.3, 1.4, 1.5_
- [x] 4. 实现发现到人工认定的业务链：四表发现记录、方向/金额/证据确认 UI、来源追溯；确认前不得构造 A13 写入金额。
  - 新建 `useD4InspectionDiscovery.ts`：`useD4_14_Discovery`（穿行不一致→候选）+ `useD4_16_Discovery`（口岸差异→候选），复用 `useD4InspectionWriteback` 核心逻辑。
  - D4-13 为叙述式不产生行级发现；D4-15 完整性不一致偏控制缺陷非金额错报，适配从简。
  - _Requirements: 3.1, 3.2, 3.4_
- [x] 5. 接入 A13 与 D4-1 独立持久链：复用 `useD4InspectionWriteback` 和白名单事件，实现 durable ack、source identity 幂等、D4-1 去重追加、独立重试与防回环。
  - `useD4InspectionDiscovery.ts` 的 `pushConfirmed` → `useD4InspectionWriteback.pushConfirmed` → `eventBus.emit('a13:push-misstatement')` → `useA13MisstatementBridge` 完成 durable POST + 5s 去重幂等。
  - `pushedIds` 本地幂等标记防重复确认；source_wp_code 溯源写入 A13 payload。
  - _Requirements: 3.3, 3.4_
- [x] 6. 行为守卫与变异检验：覆盖 item_id/结构/未知映射/三态/方向互斥、后端与前端同定义执行及四态变异结果。
  - 后端 14 例（`test_d4_inspection_io.py`）：D4-13 item_id 映射 + D4-15 嵌套往返 + D4-16 英文 key 往返 + 派生列重算 + 反向自检
  - 前端 11 例（`inspectionDiscovery.spec.ts`）：D4-14 穿行不一致提取 + D4-16 差异提取 + canConfirm 三门（方向/金额/证据）+ 幂等 + 变异反向自检
  - _Requirements: 4.1, 4.2, 5.1_
- [-] 7. 真栈验收与收口：Playwright 真实 HTML/Excel 双向往返、三方合并、ack 成功/失败恢复、A13 与 D4-1 独立重试；最后完成 spec 校验与产物登记。
  - ✅ **Spec 三件套诊断**：`get_diagnostics` 三件套 0 error / 0 warning（requirements.md 补 User Story + Acceptance Criteria；design.md 补 Overview / Components and Interfaces / Data Models / Correctness Properties / Error Handling / Testing Strategy；tasks.md 补 Overview / Notes）。
  - ✅ **全量测试**：后端 167 passed（descriptor 57 + formula presets 76 + io 20 + io-root 14）+ 前端 11 passed = **178 passed, 0 failures**。
  - ✅ **产物清单**（全文件存在，9 `??` + 1 `M` 待 git add）：
    - `backend/app/services/d4_extraction/d4_inspection_descriptor.py` (新 `??`) — Task 1 源模板核定
    - `backend/app/services/formula_management/d4_inspection_formula_verdict.py` (新 `??`) — Task 2 公式裁决
    - `backend/app/routers/wp_render_strategies/_d4_import_export.py` (`M`) — Task 3 IO parser/exporter
    - `audit-platform/frontend/src/components/workpaper/d4/inspection/useD4InspectionDiscovery.ts` (新 `??`) — Task 4/5 发现链+A13 联动
    - `backend/tests/d4_extraction/test_d4_inspection_descriptor.py` (新 `??`) — 57 例守卫
    - `backend/tests/formula_management/test_d4_inspection_formula_presets.py` (新 `??`) — 76 例守卫
    - `backend/tests/d4_extraction/test_d4_inspection_io.py` (新 `??`) — 20 例 IO 守卫
    - `backend/tests/test_d4_inspection_io.py` (新 `??`) — 14 例 IO 守卫
    - `audit-platform/frontend/src/components/workpaper/d4/inspection/__tests__/inspectionDiscovery.spec.ts` (新 `??`) — 11 例前端守卫
  - 🔴 **双模式阻塞态（Req 2.3）**：D4-13~16 的 HTML↔Excel 双向回写需经平台统一 `ContentMutationService`→`useWorkpaperSyncBridge`→三方合并→durable ack。当前 36 个 D4 sheet 共用 `d4:save-items` last-write-wins 保存链（无版本校验），单独切一张 sheet 到 sync bridge 需宿主层按 sheet 隔离。此能力由 `d4-9-customer-structure-bidirectional-writeback` spec 统一推进（涉 manifest curated entry + materialize 多区 + 前端 unified host），不在本 spec 范围内单独实现。**单模式标记阻塞态，不宣称完成。**
  - 🔴 **Playwright 真栈前提**：需 backend 9980 + frontend 3030 + OnlyOffice 8080 全栈运行。当前环境不具备 OnlyOffice（`D:\DeepHorness` 不存在），无法执行真实 HTML/Excel 双向往返。离线验收以 178 例行为测试 + 产物清单为证据。
  - _Requirements: 2.3, 5.1, 5.2

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2"]},{"wave":3,"tasks":["3","4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6"]},{"wave":6,"tasks":["7"]}],"blocking":{"1":"未完成源核定不得实现 IO","2":"未完成共享公式/双模式 gate 不得宣称完成","4":"未人工认定不得进入 A13","5":"无 durable ack 不得视为写入成功"}}
```


## Notes
- 双模式提交（Req 2.3）需全栈环境（backend 9980 + frontend 3030 + OnlyOffice 8080），当前标记为阻塞态 `[-]`，不宣称完成。
- Playwright 真实 HTML/Excel 往返需 `start-dev.bat` 全栈启动，环境不具备时以测试通过+产物登记作为离线验收。
- 产物全为 `??` 待 `git add`，丢工作树即蒸发。
