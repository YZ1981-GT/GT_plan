# Implementation Plan

## Tasks
- [x] 1. 源模板核定 gate：逐 sheet 核定 D4-17/18/19/20 列头、六区结构、item_id、稳定 id、日期方向与空/零/未知边界；删除或显式拒绝 D4-20 死配置。
  - _Requirements: 1.1, 1.4, 3.1_
  - 产物：`backend/app/routers/wp_render_strategies/_d4_cutoff_return_io_spec.py`（列头↔英文 key↔派生↔方向单一真源，源锚点=`D4-13至D4-20…检查.xlsx`）；`_d4_import_export._validate_sheet` 显式拒绝主 D4-20（六区无单一存储）；源事实守卫 `backend/tests/test_d4_cutoff_return_io.py::TestSourceGate`（openpyxl 直读逐 sheet 核定，4 例）。
- [x] 2. 共享公式/双模式 gate：接入 F-SHELL expression/refs/params/scope、后端权威执行与前端同定义预览，统一 mutation/sync/三方合并/ack/contract/representation。
  - _Requirements: 2.1, 2.2, 4.1_
  - 已落：截止 √/× 单一真源 = `useD4FormulaEngine.isCutoffOk`（前端）↔ `_d4_import_export._cutoff_is_ok`（后端），两 Tab 的本地 `checkCutoff` 已改为委派 `isCutoffOk`；`cutoffDate` 落库 `D4-1{7,8}-cutoff-date` 使 HTML 重算与 IO 重算共用同一参数。写回链复用既有 `d4:save-items`→`formData.saveBatch`→`checklist_responses`（durable PUT）+ OnlyOffice `GtOnlyOfficeSheet`。**注：F-SHELL effective-definition 编辑 UI / CAS / 三方合并轨迹属总纲 `d4-dual-mode-formula-governance` 平台件，本 spec 复用其协议、未在此重造。**
- [x] 3. 实现 D4-17/18/19/20 专用 IO 与公式：保持业务方向和六区结构，重算派生值、两侧 item_id、动态 id 和未知映射语义。
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.3_
  - 已落：`_d4_import_export` 新增 spec 驱动 `_parse_cutoff_return_row`/`_export_cutoff_return_row`/`_recompute_derived`，导入 dispatch 与导出 dispatch 均接入 `CUTOFF_RETURN_SPECS`；派生 `isCutoff`/`discountRate`/`shouldProvide`/`diff` 忽略文件值由公式重算；`_resolve_item_id` 修正 D4-20-current→`D4-20-current-returns`、D4-20-post→`D4-20-post-returns`；未知列不默归、全空行跳过；前端四 Tab 导入后 `reloadWorkpaperData()` 重载。守卫 `test_d4_cutoff_return_io.py`（21 例全绿，变异 `_cutoff_is_ok` 取反 2 例 RED 已验）+ `useD4FormulaEngine.spec.ts` isCutoffOk（5 例）。
- [x] 4. 实现发现记录与人工确认门：跨期、折扣、退货、计提发现先留风险记录，人工确认方向/金额/证据后才形成 A13 请求。
  - _Requirements: 3.1, 3.2_
  - 产物：`useD4InspectionWriteback.ts`（`canConfirm` 门 = 金额>0 且证据非空 且方向已定 → 否则不可确认；reason/"否"非空不算证据）。D4-17（跨期收入多计=贷）/D4-18（发货未记=收入完整性=贷）/D4-20 provision（计提差异=借/贷可选）各加「发现告警条 + 逐项确认弹窗（方向下拉/金额可编/证据索引）」，勾选且齐全才 `pushConfirmed`。不自动推整笔凭证、不推 amount=0。守卫 `useD4InspectionWriteback.spec.ts` 8 例（含变异 `canConfirm` 去金额门 3 例 RED 已验）。
- [x] 5. 接入 A13/D4-1 持久联动：复用共享件，落实 durable ack、幂等 source identity、D4-1 去重追加、独立重试和防回环。
  - _Requirements: 3.3_
  - 复用平台唯一消费者 `useA13MisstatementBridge`（`POST /api/projects/{pid}/misstatements` durable + 5s 去重窗口幂等 + `source_wp_code` 溯源 + amount≤0 丢弃 + crossWpEventBridge 双投防回环）。本地 `pushedIds`(sourceId) 作幂等 source identity 防重复确认；sourceId 内联进 description 使桥侧 dedup hash 生效。**注：durable ack 由桥侧 POST 完成，发 event 不代表成功——符合 Req 3.3「事件不代表成功」。**
- [x] 6. 守卫与变异：验证专用 IO、item_id 双侧一致、截止非跨期语义、未知边界、公式同定义及四态变异。
  - _Requirements: 4.1_
  - 产物：`backend/tests/test_d4_cutoff_return_io.py`（源事实4 + 死配置/item_id 8 + 往返/派生/边界 9 = 21 例）；`useD4FormulaEngine.spec.ts` 新增 isCutoffOk 5 例。变异检验：`_cutoff_is_ok` 取反 → roundtrip + non_cross 两例 RED（已验并回退）。**注：真栈往返/双模式浏览器实测归 Task 7。**
- [ ] 7. 真栈验收与收口：Playwright 实测 HTML/Excel 往返、三方合并、ack 失败恢复、A13/D4-1 独立重试，并完成 spec 结构与产物检查。
  - _Requirements: 2.2, 4.1_

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2"]},{"wave":3,"tasks":["3","4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6"]},{"wave":6,"tasks":["7"]}],"blocking":{"1":"源模板未核定不得实现 IO","2":"共享 gate 未满足不得宣称双模式完成","4":"未人工确认不得写 A13","5":"无 durable ack 不视为成功"}}
```