# 15 · 底稿同步引擎硬化批次（2026-09-25 归档）

同一批归档 5 个 spec，共同面是 **底稿 HTML↔OnlyOffice 双向回写的引擎层**：物化（materialize）
写盘路径、行位移传播、静态受管区、解析复用与性能、以及 D4-1 枢纽底稿的 store↔契约口径对齐。
它们与 `14-d4-bidirectional-writeback/`（逐张底稿的接线批次）是**同一条链的上下游**：14 号批次
接的是「每张表怎么挂」，本批次修的是「挂上去之后引擎怎么把字节写对」。

## 一览

| spec | 进度 | 一句话 |
|---|---|---|
| `d4-html-to-oo-store-contract-alignment` | **18/18** | D4-1 审定表派生行入 store + 逐格四态覆盖状态机；连带修掉三层行位移缺陷（兄弟 Table ref 不位移 / `_GT_SYNC` footer 不重冻结 / verify 表达不了多趟累积插行）与 `merge` 的列级只读误判 |
| `workpaper-sync-static-cell-sheet-writeback` | **12/12** | `BindingKind` 静态受管区（definedName 锚点，无 UUID 列 / 无 Table）全链路：extract / materialize / observer / instrumentation；落地 D4-33、D4-8 |
| `oo-single-pass-materialize-and-room-leave` | **11/11** | 物化从 39 趟链式改单趟写入（一次 load → 全 binding → 一次 save）+ `workbook_read_scope()` 解析复用 + participant 主动 `leave` 路径 |
| `workpaper-sync-materialize-large-table-performance` | **12/12** | `identity_inventory` 接受已算 fingerprint/sync_pairs；真库 D4 一次 collect **34.2s → 1.7s**，rematerialize 138.7s → **69.33s**（软上限 120 未放宽）⇒ 该 entry 恢复可发布 |
| `multi-sheet-materialize-defined-name-shift-normalization` | **10/10** | 多 sheet 多趟物化的 defined-name 位移声明并集（`MaterializeWorkbookChangeSet`）+ verify 按 `table_key` 分派 per-sheet shift，解除 `adapter_unmanaged_region_drift` |

## 归档口径

与 14 号批次同口径：**自有产物全部就位 + 真栈证据齐 + 残留有明确接收方**，不是「全部验完」。

- 真栈闭环已取到的（非声称，evidence 在各 spec 目录或 `docs/operations/evidence/`）：
  - D4-1 HTML→OO 方向 `e2e/d4-1-adjudication-oo-visibility.spec.ts` **1 passed**，OO canvas 实读
    B12..B18 七行金额与 projection 逐值相等、`B19=SUM(B8:B18)` 正确扩张；
  - D4-1 覆盖往返 `e2e/d4-1-override-roundtrip.spec.ts` **1 passed**，
    `created → application_bound → rematerializing → applied` 全程 + store 落新值；
  - D4-35 / D4-13 canvas 逐值 + 几何断言 `e2e/d4-35-d4-13-oo-visibility.spec.ts` **1 passed**；
  - 多 sheet 真实 PG + `d4-29-managed` materialize **200**（`replayed=False`）；
  - 大表性能真库 rematerialize `status=rematerialized`（gen 75 / rev 99）**69.33s**，不再抛 `MaterializeSoftTimeoutError`。
- **⚠️ 归档时 `--workers=1` 串行仍是硬约束**（OnlyOffice 8080 单实例并发 contention 会假失败）。

## 移交给别处的残留（逐条有接收方）

| 残留 | 接收方 |
|---|---|
| `excel_extract_identity_carrier_missing` 是 domain error 却以 **500** 返回（前端按「服务器内部错误」自动重试 3 次） | router 错误分类面 —— 归 `workpaper-html-onlyoffice-bidirectional-writeback-closure`（平台总纲） |
| 同一 representation generation 内重复 materialize ⇒ OO 按 `doc_key` 缓存的文档与磁盘 staged xlsx 分叉（`UpdateVersion expired`） | 待立项（临时解：`docker restart audit-onlyoffice`） |
| 多个历史 generation 的 room 仍 `state='active'`（AC 2.8 显式 supersede 未全程生效） | 平台总纲 AC 2.8 |
| D4-8 / D4-33 / D4-35 真 OO canvas **单元格编辑**往返（canvas 非 DOM，Playwright 无法可靠输入） | 与 14 号批次「全 entry required scenario」同批，归平台总纲 Task 70 |
| `structure_fingerprint` 仍有 38 calls / 20.2s 在 collect 之外；`adapter.extract` 多 binding 解析共享（P1） | 已不阻塞生产（69.33s < 120s）；按需再开性能批次 |
| D4-7 解阻仅剩「前端 products 补 rowId」（性能条件①已由本批次满足） | D4 循环接线面 |

## 方法论教训（这批次抓到的，值得记住）

1. **「判据绿而生产红」不是玄学，是判据没覆盖真实路径。** `materialize` + `extract` 全绿曾与生产
   500 并存 —— 判据只覆盖 adapter 两个方法，而生产路径在它们**之后**还有 `verify_unmanaged_regions`。
2. **错误信息指错对象比信息少更贵。** `assert_identity_carriers_usable` 原打印 `dynamic_tables[0]`
   （D4 契约第 0 项恒为 `d42-managed`）⇒ 无论哪个 binding 失败文案都指向 D4-2，排查白绕一圈。
3. **不要拿两个计数作差去推断数据丢失。** `store_field_count`(1648) 与 `field_count`(992) 的差值
   ≠「store 被吞了多少业务值」；实际是探针读错响应层级（投影体在 `data.projection` 不在 `data` 顶层）。
4. **不能用 `page.on('response')` 判 OO callback** —— OO 容器**直接** POST 后端，不经浏览器。
5. **纯函数判据覆盖不到时序/数据来源缺陷。** 13 条四态纯函数判据全绿而生产行为是坏的（覆盖标记
   下一 tick 自我擦除 / S4 态不可达），因为它们只喂三个入参、从不跑写这三个量的同步器。
6. **变异 harness 自身会假绿**：还原动作放进单条变异的 `try/finally` 而 `ANCHOR-MISS` 分支 `continue`
   跳过还原 ⇒ 下一轮把「已被变异的文件」当 pristine 快照，级联出一串假结论。
