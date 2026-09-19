# Implementation Plan

## Tasks
- [ ] 1. 源模板核定 gate：逐 sheet 核定 D4-17/18/19/20 列头、六区结构、item_id、稳定 id、日期方向与空/零/未知边界；删除或显式拒绝 D4-20 死配置。
  - _Requirements: 1.1, 1.4, 3.1_
- [ ] 2. 共享公式/双模式 gate：接入 F-SHELL expression/refs/params/scope、后端权威执行与前端同定义预览，统一 mutation/sync/三方合并/ack/contract/representation。
  - _Requirements: 2.1, 2.2, 4.1_
- [ ] 3. 实现 D4-17/18/19/20 专用 IO 与公式：保持业务方向和六区结构，重算派生值、两侧 item_id、动态 id 和未知映射语义。
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.3_
- [ ] 4. 实现发现记录与人工确认门：跨期、折扣、退货、计提发现先留风险记录，人工确认方向/金额/证据后才形成 A13 请求。
  - _Requirements: 3.1, 3.2_
- [ ] 5. 接入 A13/D4-1 持久联动：复用共享件，落实 durable ack、幂等 source identity、D4-1 去重追加、独立重试和防回环。
  - _Requirements: 3.3_
- [ ] 6. 守卫与变异：验证专用 IO、item_id 双侧一致、截止非跨期语义、未知边界、公式同定义及四态变异。
  - _Requirements: 4.1_
- [ ] 7. 真栈验收与收口：Playwright 实测 HTML/Excel 往返、三方合并、ack 失败恢复、A13/D4-1 独立重试，并完成 spec 结构与产物检查。
  - _Requirements: 2.2, 4.1_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2"]},{"wave":3,"tasks":["3","4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6"]},{"wave":6,"tasks":["7"]}],"blocking":{"1":"源模板未核定不得实现 IO","2":"共享 gate 未满足不得宣称双模式完成","4":"未人工确认不得写 A13","5":"无 durable ack 不视为成功"}}
```

## 实施进度（2026-09-19，append-only；上方 1-7 原文不动）

> 三姊妹 D4 检查表 spec 一并推进。本 spec（D4-17/18/19/20）**可做实部分已完成**，双模式真同步桥 provider 因平台环境依赖单列 blocked（与 IPO spec 同一边界）。

### 已做实（做绿 + 守卫 + 变异，对应 Task 1/3/4/6 的可测部分）

- **后端专用 parser + 分发（Task 3）**：`_d4_import_export.py` 新增 `_parse_d4_17_row`/`_parse_d4_18_row`/`_parse_d4_19_row`/`_parse_d4_20_return_row`/`_parse_d4_20_provision_row`；import 分发接线 D4-17/18/19/D4-20-current/post/provision；export 行构造分支；派生列单源（isCutoff 留 None、discountRate=折扣/收入重算、shouldProvide=base×rate/diff 重算，不信文件值）。
- **D4-20 子表键错位修复（Task 1，DEC-2）**：后端 item_id 映射 D4-20-current→`D4-20-current-returns`、D4-20-post→`D4-20-post-returns`、provision→`D4-20-provision`（改后端对齐前端键，不改前端 6 处引用）；导入导出两侧对称。
- **死配置删除（Task 1，DEC-1）**：裸 `D4-20` 从 `_SUPPORTED_SHEETS` + `_SHEET_HEADERS` 删除（前端只用三子表，从不导入导出裸 D4-20）。
- **跨期公式收敛（Task 3）**：D4-17 `checkCutoff` 改用 `useD4FormulaEngine.isCrossPeriodForward`（取反）、D4-18 用 `isCrossPeriodBackward`（取反），删除内联日期比较（公式引擎单一真源）。
- **A13 + D4-1 联动（Task 4）**：四表接 `useD4InspectionWriteback` 推 A13——D4-17/18 推 `isCutoff===false` 跨期问题、D4-19 人工 prompt 错报金额（不把折扣额自动当错报）、D4-20 推 `isAbnormal==='是'` 异常退货；全人工 @click 触发。
- **守卫 + 变异（Task 6 可测部分）**：`backend/tests/test_d4_cutoff_return_io_roundtrip.py`（8 passed，往返 PBT + poison 派生值重算 + item_id 双侧一致 + 死配置删除 + 分发守卫）；前端 `d4CutoffReturnWriteback.spec.ts`（14 passed，wpCode 字面量 + 人工触发不在自动回调 + 跨期走引擎 + 发现≠自动错报过滤）。

### [blocked] 双模式真 OOXML 同步桥（Task 2 的同步桥部分 + Task 7 真 OO 往返）

- [ ] BB1 [blocked] 为 D4-17/18/19/20 在后端 `workpaper_sync` 建 managed sheet provider（照 `phase5_d4_ipo_checklist_sheets.py` 范式：字段列映射 + mapping_digest 冻结 + instrumentation + rows_table_payload + split/merge 投影）。
  - 已核定几何（权威 workbook `D/D4 收入底稿.xlsx` 含这 4 sheet）：D4-17/18 两级表头 row11/12 数据 row13 起 11 列 A-K（K 派生跨期）；D4-19 两级表头 row11/12 15 列 A-O（E 派生，UUID 用 Q 因 P 列被下拉选项占用）；**D4-20 一张物理 sheet 含 3 个受管区**（计提 row24/25-29、本期退货 row32/33/34+、期后退货 row38/39/40+）——「一 sheet 多受管区」是平台从未做过的新形态，IPO/D4-35 均为一 sheet 一区。
  - 阻塞原因：D4-20 多受管区是新形态有未知风险（footer 定位 + 多区行位移传播）；且真 OO 9.x 往返无环境可验（同 IPO spec B6 至今 blocked）。
  - _Requirements: 2.1, 2.2, 4.1_
- [ ] BB2 [blocked] 前端 D4-17/18/19/20 从裸 `GtOnlyOfficeSheet` 迁 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`（对齐 D4-35/IPO 蓝本），依赖 BB1 后端契约。
  - _Requirements: 2.1, 2.2, 2.3_
- [ ] BB3 [blocked] 真栈验收（Task 7）：Playwright 真实 HTML/Excel 往返、durable ack 失败恢复、A13/D4-1 独立重试。需 `start-dev.bat`（后端 9980 + 前端 3030 + OnlyOffice 服务）。
  - _Requirements: 2.2, 4.1_
