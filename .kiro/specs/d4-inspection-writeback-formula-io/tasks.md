# Implementation Plan

## Tasks
- [ ] 1. 源模板核定与稳定 ID gate：逐 sheet 读取源 xlsx，核定 D4-13/14/15/16 列头、嵌套结构、item_id、动态 id、未知映射、日期/空零未知三态与文本 N/A。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.1_
- [ ] 2. 共享公式与双模式 gate：接入 F-SHELL preset/custom expression/refs/params/scope；后端权威执行、前端同定义预览；接入统一 mutation、sync、三方合并、contract、representation 与 durable ack，解析失败保留原值。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.2_
- [ ] 3. 实现 D4-13/15/16 IO：专用 parser/exporter、嵌套/英文 key 对齐、D4-13 双 item 文本锚点、D4-15 `D4-15-items`、D4-16 差异重算与动态 id 保留。
  - _Requirements: 1.2, 1.3, 1.4, 1.5_
- [ ] 4. 实现发现到人工认定的业务链：四表发现记录、方向/金额/证据确认 UI、来源追溯；确认前不得构造 A13 写入金额。
  - _Requirements: 3.1, 3.2, 3.4_
- [ ] 5. 接入 A13 与 D4-1 独立持久链：复用 `useD4InspectionWriteback` 和白名单事件，实现 durable ack、source identity 幂等、D4-1 去重追加、独立重试与防回环。
  - _Requirements: 3.3, 3.4_
- [ ] 6. 行为守卫与变异检验：覆盖 item_id/结构/未知映射/三态/方向互斥、后端与前端同定义执行及四态变异结果。
  - _Requirements: 4.1, 4.2, 5.1_
- [ ] 7. 真栈验收与收口：Playwright 真实 HTML/Excel 双向往返、三方合并、ack 成功/失败恢复、A13 与 D4-1 独立重试；最后完成 spec 校验与产物登记。
  - _Requirements: 2.3, 5.1, 5.2

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1"]},{"wave":2,"tasks":["2"]},{"wave":3,"tasks":["3","4"]},{"wave":4,"tasks":["5"]},{"wave":5,"tasks":["6"]},{"wave":6,"tasks":["7"]}],"blocking":{"1":"未完成源核定不得实现 IO","2":"未完成共享公式/双模式 gate 不得宣称完成","4":"未人工认定不得进入 A13","5":"无 durable ack 不得视为写入成功"}}
```

## Governance Gating Addendum（2026-09-19，append-only；上方 1-7 原文不动）

> **实施路线裁决（逐文件核实后）**：本 spec 四表（D4-13/14/15/16）的 **I/O 收口 + 公式单源 + A13/D4-1 人工确认链 + 行为守卫/变异** 已 90% 就位（后端专用 parser/exporter、前端四组件、`useD4ImportExport`/`useD4FormulaEngine`/`useD4InspectionWriteback` 全在且被消费），可做实收口 —— 拆为下方 T1-T7。
>
> **而 Task 2 / Task 7 中「真 OOXML 字节级双模式统一同步桥」部分不可诚实做绿**，与两个姊妹 spec（`d4-ipo-checklist-dual-mode-writeback-and-formula`、`d4-cutoff-return-writeback-formula-io`）撞同一堵墙，逐条实证如下 → 拆为下方 B1-B3 标 `[blocked]`：
> - 🔴 **`ContentMutationService` 在整个代码库零命中**（context-gatherer 全库搜索 + grep 实证）。Requirement 2.3 / design「统一经平台 `ContentMutationService`」引用的是一个**不存在的设施名**；平台真实双模式设施是 `useWorkpaperSyncBridge` 生态。
> - 🔴 **后端 `workpaper_sync` 契约未注册 D4-13~16**：grep `backend/data/workpaper_sync_contracts/*.json` 的 `d4-13-managed`~`d4-16-managed` / `d413`~`d416` **零命中**。已注册的只有 D4-2/3/5/21/22/23/24/35 + IPO 的 25~29。接同步桥须先为每张表建 instrumentation（Excel Table 受管区）+ contract（sheet_key/table_key/row_identity_key）+ definition bundle + published representation —— 属 `workpaper_sync` 独立重活，非本 spec 装得下。
> - 🔴 **D4-13 是纯叙述文本表**（源模板 `一、核对过程`/`二、核对结论` 两段文本，无行集），根本不适配「受管行表」同步模型（源模板核定实证：merges 仅 `A1:E1`/`A2:E2` 抬头，无数据表结构）。
> - 🔴 **同类 IPO spec design.md 已白纸黑字裁定**「不走 Phase 5 `workpaper_sync` OOXML 字节级路径」「不接附注同步（`no_projection_contract` 判定不变）」。本 spec 沿用同一诚实边界。
>
> **唯一「真双模式」样板是 D4-35（`D4TabOtherCheck.vue` + 后端 `d435-managed` 全套契约）**，其基础设施是专门单独建的，非复制可得。

- [x] T1. 源模板核定与稳定 ID gate（做实 Task 1）：逐 sheet 读 `backend/wp_templates/D/D4-13至D4-20主营业务收入-检查（Leap应对措施-检查）.xlsx`，核定 D4-13/14/15/16 的源列头（含两级表头 merges）↔ 后端 `_SHEET_HEADERS` ↔ item_id 三方对应，产出核定证据；显式登记源↔后端 header 偏差（D4-15「所载信息是否一致」vs 后端「核核信息是否一致」、D4-16 索引列合并）。
  - 证据：`evidence/t1-source-template-gate.md`（9 sheet 逐 sheet + 两级表头 merges 实证 + 4 表 item_id/行 id 前缀/派生列单源/三态边界核定通过 + 2 处非阻断偏差登记）。探针脚本用完即删。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.1_
- [x] T3. IO 收口（做实 Task 3）：为 D4-13/14/15/16 专用 parser/exporter 补往返无损测试（录入字段逐字段一致、派生值由公式重算不信文件值）+ item_id 双侧一致守卫（导出 `{sheet}-item_id` == 导入 `{sheet}-item_id`）。
  - 证据：新增 `backend/tests/test_d4_inspection_io_roundtrip.py`（7 passed，PBT 驱动真实 `_parse_d4_14/15/16_row`；poison 差异/一致性/分数被重算覆盖证派生列单源；item_id 双侧一致 + D4-13 文本锚点）。既有 `test_d4_inspection_io_guards.py`（6 passed）互补。
  - _Requirements: 1.2, 1.3, 1.4, 1.5_
- [x] T4. 发现→人工认定链（做实 Task 4）：守卫四表「发现记录不自动成错报」—— `amount:0` 定性事项不入 A13、`reason`/「否」非空不构成异常、确认前不构造 A13 写入金额。
  - 证据：扩展 `d4InspectionWriteback.spec.ts`（21 passed，含 T4 段 9 条）——四组件 `pushToA13`/`handlePushToA13` 必人工 `@click` 触发（不在 watch/debounce/onMounted 回调体内）；D4-13 金额人工 prompt + `!amount` 短路；D4-16 按 `diff!==0` 过滤非 reason 非空；D4-15 `isConsistent===false`；D4-14 conclusion 重大异常。`amount<=0 不入 A13` 由既有 `useA13MisstatementBridge.spec.ts` 覆盖。
  - _Requirements: 3.1, 3.2, 3.4_
- [x] T5. A13 + D4-1 独立持久链（做实 Task 5）：复用 `useD4InspectionWriteback`，守卫 source identity 幂等去重（`draftHash` 含 misstatementType 维度）、D4-1-adj-note 去重追加、只读态不推送、空项不 emit；**durable ack 现状 = best-effort try/catch，如实登记为遗留（无持久队列/重试），不伪称已实现**。
  - 证据：`evidence/t4-t5-linkage-chain.md`。幂等由 `a13MisstatementType.spec.ts::Property 9` 覆盖；D4-1-adj-note 去重追加/只读/空项由 `d4InspectionWriteback.spec.ts` 覆盖。durable ack 持久化/重试 → **B3 blocked**（平台级待建，不伪称已实现）。
  - _Requirements: 3.3, 3.4_
- [x] T6. 行为守卫与四态变异（做实 Task 6）：覆盖 item_id/三层嵌套结构/isConsistent 单源/portsDiff-taxDiff 重算/D4-13 双 item 文本锚点；变异脚本四态判定 RED/GREEN/ANCHOR-MISS/WRONG-TEST。
  - 证据：`evidence/t6-guards-mutation.md`。后端 `mutate_d4_inspection_io_guards.py`（3 锚点全 RED，green0，pass=true）；本 spec 新增前端 `backend/scripts/diagnose/mutate_d4_inspection_t4_guards.py`（3 锚点全 RED，green0，pass=true）。🔴 变异真实发现并修复守卫缺陷：首轮 M1=GREEN（T4 守卫只扫 `pushToA13(` 漏 wrapper `handlePushToA13(`）→ 修复后 M1 转 RED，基线 21 passed 不回归。
  - _Requirements: 4.1, 4.2, 5.1_
- [x] T7. 收口（做实 Task 7 的可做部分）：三件套 get_diagnostics 校验、产物 git add 入库、遗留登记（B1-B3 blocked 边界写清）。
  - 证据：见收口段（本次会话末）。B1-B3 保持 `[blocked]`，边界已在 Governance Addendum 写清。
  - _Requirements: 5.1_

- [ ] B1 [blocked] 为 D4-14/15/16 在后端 `workpaper_sync` 建 managed sheet 契约（instrumentation Excel 受管区 + contract sheet_key/table_key/row_identity_key + definition bundle + published representation），D4-13 纯文本表走文本型适配或显式登记 N/A。
  - 阻塞原因：属 `workpaper_sync` 独立工程；后端契约当前零注册这四表；须先有 owner 与真实 OO 9.x 往返验收环境。
  - _Requirements: 2.3_
- [ ] B2 [blocked] 前端把 D4-14/15/16 从裸 `GtOnlyOfficeSheet` 迁到平台 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost` + `capabilityForEntry(父级 entry)` 现算 + `flushHtml`(先 flushPendingSave 再 readStoreProjection)，对齐 D4-35 蓝本；删除 `ContentMutationService` 这一不存在的设施引用。
  - 阻塞原因：依赖 B1 的后端契约；`ContentMutationService` 不存在需先由治理 spec 澄清真实设施名。
  - _Requirements: 2.1, 2.2, 2.3_
- [ ] B3 [blocked] durable ack 加固：A13 推送从 best-effort try/catch 升级为持久 ack + 幂等 source identity + 独立重试队列（当前仅 `useA13MisstatementBridge` 逐笔 try/catch + ElMessage）。
  - 阻塞原因：durable 队列/重试是平台级基础设施，非单 spec 范围；需与治理 spec c3_linkage_contract 对齐后统一落。
  - _Requirements: 3.3_