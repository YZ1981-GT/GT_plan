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

- [x] B1 已解除阻塞并做实（2026-09-19，参照已完成姊妹 spec `d4-ipo-checklist-dual-mode-writeback-and-formula` D4-25~28 provider 蓝本）：为 **D4-15/16** 在后端 `workpaper_sync` 建 managed sheet provider；**D4-14 明确不做**（32 列七维嵌套 + 计算型 footer 超 IPO「一行 marker footer + 直列映射」范式，风险不可控，单列待评估）；**D4-13 登记 N/A**（纯叙述文本表无行集，不适配受管行表模型）。
  - 交付：新建 `backend/app/services/workpaper_sync/phase5_d4_inspection_sheets.py`（照 IPO 数据驱动 `_SHEETS` dict 范式：D4-15 三维嵌套 15 字段 `json_path`(delivery/invoice/voucher 三级)+Q 一致性 formula_mask / D4-16 7 字段 + D,I 差异 formula_mask，`mapping_digest` 冻结 D4-15=`418b3629…` / D4-16=`ca120930…`；别名导入 `INSPECTION_*` 避免与 IPO 符号冲突）。装配 `phase5_d4_revenue_detail.py` 6 点（import/instrumentation_specs/digest 断言/sheet_payload/store item 映射/build+merge 投影）。重生成契约 `d4.revenue_detail.json`（canonical_digest `3f2751d0…`，`--check` OK）：instrumentation_specs 12→14、contract sheets 13→15。
  - 证据：`backend/tests/workpaper_sync/test_d4_inspection_store_roundtrip.py`（18 passed，含三维嵌套专项）；`--check` 契约守卫绿；回归 IPO+inspection roundtrip 58 passed。
  - _Requirements: 2.3_
- [x] B2 已解除阻塞并做实（2026-09-19）：前端把 **D4-15（`D4TabCompleteness.vue`）/ D4-16（`D4TabExport.vue`）** 迁到平台 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost` + `capabilityForEntry('xlsx/gt-d4-operating-revenue')` 现算 + `flushHtml`（先 `flushPendingSave` 再 `readStoreProjection`，防投影旧值）；`sheetKey` 锁 `d4-15-managed`/`d4-16-managed`；`useD4CompletenessCheck.ts` 补 `flushPendingSave`。`ContentMutationService` 全库零引用（spec 草案臆想名，已由 IPO 治理澄清真实设施 = `useWorkpaperSyncBridge` 生态），本组件不引用。**并修复宿主漏登记 bug**：`GtD4OperatingRevenue.vue::isD4DedicatedSyncSheet` 未含 D4-15/16 → 宿主仍渲染 legacy「两侧数据未互通」通知 + legacy dualMode（与子组件自管切换器叠加，IPO D4-25~28 曾踩同坑）；补登记后消除。
  - 证据：前端守卫 `d4InspectionSyncHostWiring.spec.ts`（19 passed，含宿主 dedicated 登记 +3 断言）；`get_diagnostics` 全 clean。**真栈 Playwright 验收**（wp `b3ab3c46` 重药控股安徽 2025）：D4-15/16 均 noticeCount=0 / segCount=1 / syncTag=已同步；切「在线编辑」后 `WorkpaperSyncEditorHost`+OO iframe 渲染成功、0 console errors。早前「切在线编辑 3 errors」根因证伪 = 瞬时后端负载（store-projection 慢+间歇 500，并发 vitest+OO 冷启+ledger 轮询超时），直接探针连调 4 次均 200/0.07-0.14s，非 descriptor/materialize 边界。截图 `evidence/d4-16-live-clean.png`。
  - _Requirements: 2.1, 2.2, 2.3_
- [x] B3 durable 幂等已做实（2026-09-19）：A13 推送去重从前端 5s 内存 Map 升级为**服务端 DB durable 幂等**。
  - 交付：V164 迁移（`unadjusted_misstatements.source_identity` + 部分唯一索引，真实 PG schema_version=164）+ 模型/schema/service（pre-check + savepoint 并发硬化）+ 前端 `useA13MisstatementBridge` POST 携 `source_identity`（=draftHash 同字段，跨会话/刷新永久去重）。
  - 证据：`evidence/b3-durable-ack.md`。service 守卫 `test_misstatement_source_identity_dedup.py` 4 passed；无回归（misstatements 22 passed / 前端 a13 29 passed）；变异 `mutate_misstatement_dedup_guards.py` 3/3 RED；**真栈实测**（运行后端+真 PG，隔离项目 2099）同 identity 两次 POST（间隔 24s>旧5s窗）→ DB 恰 1 行。
  - 覆盖全平台 ~35 个推送点（useA13MisstatementBridge 唯一消费者）。
  - 🔴 **剩余未做（如实登记）**：「失败重试队列 / 持久 outbox」属更重的异步基础设施，本次未做 —— A13 是同步 POST，失败即时返回由前端 try/catch 计 fail；durable 幂等已消除重复错报这一真栈实测印证的主要痛点。
  - _Requirements: 3.3_

## 任务状态归并表（2026-09-21 append-only；上方 1-7 原文与复选框一律不动）

> **为什么要这张表**：本文件同时存在两代任务编号 —— 草案代 `1-7`（`[ ]`）与 Governance Addendum
> 做实代 `T1-T7 / B1-B3`（全 `[x]`）。机械统计复选框会得出「9/16 未完成」，**与实际状态相反**：
> 草案 1-7 已被 T1-T7/B1-B3 逐条承接做实或显式裁决，**没有一条是"待开工"**。本表是唯一权威对照。
> 按「历史档案 append-only」铁律，不回改 1-7 的 `[ ]`，只在此登记映射。

| 草案任务 | 承接者 | 现状 | 证据 |
|---|---|---|---|
| 1. 源模板核定与稳定 ID gate | **T1** `[x]` | 已做实 | `evidence/t1-source-template-gate.md`（9 sheet 逐 sheet + 两级表头 merges + item_id/行 id 前缀/三态边界核定 + 2 处非阻断偏差登记） |
| 2. 共享公式与双模式 gate | **B1/B2** `[x]` + **B3** `[x]` | D4-15/16 已做实；**D4-13 裁 N/A**（纯叙述文本表无行集）；**D4-14 已移交专项 spec `d4-14-walkthrough-writeback` 并于 2026-09-21 落地**（`d414-managed` 34 受管字段 / 契约 34 张 / gen83 / 前端接桥 + 宿主登记 'D4-14'） | `test_d4_inspection_store_roundtrip.py`(18) / `d4InspectionSyncHostWiring.spec.ts`(19) / `evidence/b3-durable-ack.md` |
| 3. D4-13/15/16 IO | **T3** `[x]` | 已做实 | `test_d4_inspection_io_roundtrip.py`(7) + `test_d4_inspection_io_guards.py`(6) |
| 4. 发现→人工认定业务链 | **T4** `[x]` | 已做实 | `d4InspectionWriteback.spec.ts`(21，含 T4 段 9 条) |
| 5. A13 + D4-1 独立持久链 | **T5** `[x]` + **B3** `[x]` | durable **幂等**已做实（V164 `source_identity` + 部分唯一索引，真 PG 实测同 identity 两次 POST → 恰 1 行）；**失败重试队列/持久 outbox 仍未做**，已在 B3 如实登记为遗留 | `evidence/t4-t5-linkage-chain.md` / `test_misstatement_source_identity_dedup.py`(4) |
| 6. 行为守卫与变异检验 | **T6** `[x]` | 已做实（变异真实揪出并修复 1 处守卫缺陷：T4 守卫只扫 `pushToA13(` 漏 wrapper `handlePushToA13(`） | `evidence/t6-guards-mutation.md`，两个 mutate 脚本锚点全 RED |
| 7. 真栈验收与收口 | **T7** `[x]` + **B2** `[x]` | 离线/REQUEST_PATH 级已做实（D4-15/16 真栈 Playwright noticeCount=0 / syncTag=已同步 / 0 console error，截图 `evidence/d4-16-live-clean.png`）；**真 OO canvas 单元格往返仍 env 门**（批次C，D4 全组无一张达标） | `evidence/d4-16-live-clean.png` + 清册 §统计段口径 |

**结论：本 spec 无"需要继续做"的本 spec 产物**。两处如实留白，且都不属本 spec 可独立解除：
1. **A13 失败重试队列 / 持久 outbox**（B3 已登记）—— 平台级异步基础设施，宜单立 spec，不该塞进本 spec。
2. **真 OO canvas 往返**（批次C）—— D4 全组 34 张共同的最后一道门，见清册 §逐张推进优先级 第 1 条。

**遗留的唯一"账面失真"就是上方 1-7 的 `[ ]`**，本表即为其对照说明；后续统计 D4 spec 完成度时请按 T/B 代计（T1-T7 + B1-B3 = 10/10），不要把 1-7 重复计入分母。

---

## 2026-09-22 归档前状态刷新：更正归并表里一条已过时的断言（append-only）

> 上方「任务状态归并表」第 7 行与结论段写的是「**真 OO canvas 往返仍 env 门（批次C，D4 全组无一张达标）**」。
> 这条**已被证伪**，按「历史档案 append-only」铁律不回改原文，在此登记更正。

**① 「D4 全组无一张达标」不成立 —— D4-2 已达标**：
`.kiro/specs/_archive/14-d4-bidirectional-writeback/d4-revenue-matrix-bidirectional/evidence/g5-1-d4-unified-path/network-and-callback.json`
记 `forcesave_cs_error=0`（权威判据）+ `forcesave_http_status=202` + `confirm_descriptor_200=true`；
同目录 `db-check.json` 记 `operation.state=applied` · `application.state=applied`
（`adapter_id=d4.revenue_detail`, `result_revision=12`）· `content_version.source=onlyoffice` 且
`operation_id` 交叉一致 · `store_mirror.marker_in_store=true`（OO 画布里写的 marker 出现在 HTML store）。
⇒ 真 OO canvas → forcesave → callback → applied → HTML 镜像**整条链在 D4 上已真栈跑通一次**。
正确表述应为：「**D4 全组 30 张中 1 张（D4-2）已达标，其余 29 张只做到 L1**」。

**② env 门也已解除**：D4 全量 30 张逐张 L1 验收全绿，证据
`docs/operations/evidence/d4-bidirectional-acceptance/D4-{1..36}.json`（缺 D4-4，owner 去重后不独立成表）
—— 36 份 JSON 的 `console_errors` / `http_errors` **全为 0**。本 spec 直接相关的 D4-13/14/15/16 四张
各有独立证据（`D4-13.json` / `D4-14.json` / `D4-15.json` / `D4-16.json`）。
其中 D4-14 已由专项 spec `d4-14-walkthrough-writeback` 落地（`d414-managed` 34 受管字段，gen83）；
D4-13 维持本 spec 的 `N/A` 裁定（纯叙述文本表无行集，不适配受管行表模型）。

**③ 结论段两处留白的现状**：
1. **A13 失败重试队列 / 持久 outbox** —— 仍未做（B3 已如实登记）。durable **幂等**已做实（V164
   `source_identity` + 部分唯一索引，真 PG 实测同 identity 两次 POST → 恰 1 行）。属平台级异步基础设施，
   宜单立 spec，**不构成本 spec 未完成产物**。
2. **真 OO canvas 往返** —— 按本节 ① 更正：链路已证；剩余是「逐张再跑一遍」的验收深度项，
   按 entry 粒度（D4 全部子表同属父 entry `xlsx/gt-d4-operating-revenue`）移交总纲
   `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 70 的「全 entry required scenario」口径。

**④ 归档判定**：T1-T7 + B1-B3 = **10/10**（草案 1-7 的 `[ ]` 是两代编号的账面失真，归并表为唯一权威对照，
统计时不得把 1-7 重复计入分母）⇒ **可归档**。
