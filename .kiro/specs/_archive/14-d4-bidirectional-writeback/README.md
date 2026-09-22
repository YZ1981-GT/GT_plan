# 14 · D4 营业收入底稿双向回写（HTML ↔ OnlyOffice）

**归档日期**：2026-09-22
**归档分支**：`work/2026-09-14-d4-dual-mode-p0-fixes`
**归档口径**：14 个 spec 的**自有产物**全部就位且有真栈证据；残留项均已逐一登记并移交明确接收方（见下 §三）。

---

## 一、这批 spec 解决了什么

把 D 循环枢纽底稿组 **D4-1 ~ D4-36（30 张实际成表，D4-4 owner 去重后不独立成表）** 从
「legacy `GtOnlyOfficeSheet` + 本地 `editorMode` ref + 单向写」迁到平台统一双向同步链路：

```
HTML store ──flushHtml──► pending-mutations ──► materialize ──► OnlyOffice 9.4
     ▲                                                              │
     └── oo_to_html 镜像 ◄── applied ◄── callback(durable) ◄── forcesave
```

平台侧设施为 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost` + 后端 `workpaper_sync`
（instrumentation → contract → definition bundle → published representation → room/participant 协议）。

**entry 粒度事实**：D4 全部 30 张子表挂在**唯一父 entry** `xlsx/gt-d4-operating-revenue`
（adapter `d4.revenue_detail`，`room_model=shared`）。manifest 里 21 条 `xlsx/d4/...` 子入口一律
`parent_duplicate`，不进独立入口分母。该 entry 现为平台 4 个 `capability=bidirectional` +
`migration_state=adapter_registered` 的 entry 之一（另三个：D2 / G7 / H1）。

---

## 二、14 个 spec 一览（归档时复选框实扫）

| spec | 覆盖底稿 | 进度 |
|---|---|---|
| `d4-1-adjudication-bidirectional-writeback-and-formula-io` | D4-1 审定表（枢纽） | 12/12 |
| `d4-revenue-matrix-bidirectional` | D4-2 / D4-3 收入矩阵（`months[12]` 位置数组） | 13/13（1 `[~]` 已说明） |
| `d4-9-customer-structure-bidirectional-writeback` | D4-9 客户结构（同 sheet 双区 + sibling sheet） | 12/12（3 `[~]` 已说明） |
| `d4-price-analysis-writeback-linkage` | D4-10 / D4-11 价格分析 + 风险联动 | 9/9（1 `[~]` 已说明） |
| `d4-12-transposed-writeback` | D4-12 合同检查（**转置** sheet 双向回写） | 15/15 |
| `d4-14-walkthrough-writeback` | D4-14 穿行测试（`d414-managed` 34 受管字段） | 12/12（1 `[~]` 已说明） |
| `d4-inspection-writeback-formula-io` | D4-13/14/15/16 检查组 I/O + 公式 + A13 链 | T1-T7 + B1-B3 = 10/10 |
| `d4-cutoff-return-writeback-formula-io` | D4-17/18/19/20 截止/退货组 | 13/13 |
| `d4-21-24-oo-bidirectional-and-cross-sheet-formula` | D4-21~24 + 跨表公式 | 10/10（1 `[~]` 已说明） |
| `d4-ipo-checklist-dual-mode-writeback-and-formula` | D4-25/26/27/28 IPO 清单组 | 28/28（2 `[~]` 已说明） |
| `d4-ipo-fraud-writeback-formula-io` | D4-29~32 IPO/舞弊组 | 11/11 |
| `d4-33-36-writeback-formula-and-io-closure` | D4-33/34/35/36 其他组 | 35/35（2 `[ ]*` + 5 `[~]` 已说明） |
| `d4-adjustment-and-analysis-gap-closure` | D4-4 / D4-8 / D4-12 缺口核定 | 1/1 + 4 条显式 **N/A 作废** |
| `d4-dual-mode-formula-governance` | **总纲**：C0~C4 契约（owner 矩阵 / sync / formula / linkage / 验收矩阵） | 16/16 |

> **`d4-inspection-writeback-formula-io` 的统计陷阱**：该文件同时存在两代任务编号 —— 草案代 `1-7`（`[ ]`）
> 与做实代 `T1-T7 / B1-B3`（全 `[x]`）。机械统计复选框会得出「9/16 未完成」，与实际状态相反。
> 其 tasks.md 内的「任务状态归并表」是唯一权威对照，统计时**不得把 1-7 重复计入分母**。

---

## 三、验收分层与残留（归档时如实登记，勿当成全绿）

### L1 —— 逐张 30/30 全绿 ✅

判据：进「在线编辑」走统一路径（`/sync/**`）→ `store-projection` 200 → `materialize` 200 →
callbackUrl 含 `room_id`/`generation`/`doc_key`/`route_credential_id` → `wp-sync-host` 挂载 + OO iframe
→ **无 `/d2-sync/*` legacy 旁路**。

证据：`docs/operations/evidence/d4-bidirectional-acceptance/D4-{1..36}.json`（36 份，`console_errors`
与 `http_errors` 全为 0）。脚本：`audit-platform/frontend/e2e/d4-bidirectional-acceptance.spec.ts`。

⚠️ **逐张 L1 必须 `--workers=1` 串行跑**：多 worker 并行会因 OnlyOffice 8080 单实例并发 contention
产生假失败（2026-09-21 实证：5-worker 并行全挂 / serial 5 passed，**非** wiring gap）。

### L2 —— 真 OO canvas 完整往返，只做了 1 张（D4-2）🟡

判据：在 OO 画布真实写格 → forcesave（权威判据 `cs_error=0`，`4=no_changes` 不算）→ callback durable
→ application **applied** → HTML store 镜像可见。

证据：`d4-revenue-matrix-bidirectional/evidence/g5-1-d4-unified-path/network-and-callback.json`
（`forcesave_cs_error=0` / `forcesave_http_status=202` / `confirm_descriptor_200=true`）+ 同目录
`db-check.json`（`operation.state=applied` / `application.state=applied` /
`content_version.source=onlyoffice` 且 `operation_id` 交叉一致 / `store_mirror.marker_in_store=true`，
且 `months` 仍是长度 12 的位置数组 ⇒ 位置数组往返等值在真栈成立）。

**残留**：其余 29 张的 per-sheet L2 未逐张跑。按总纲 Req 14.1「不得用一条 applied operation 覆盖全部场景」，
D4-2 这一条**不能**替 29 张签收。该残留按 entry 粒度归父 entry，**移交
`workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 70 的「全 entry required scenario」口径**
统一推进，不再挂在本批 spec 上。

### 其他已登记残留

- **A13 失败重试队列 / 持久 outbox**（`d4-inspection` B3）：durable **幂等**已做实（V164 `source_identity`
  + 部分唯一索引，真 PG 实测同 identity 两次 POST → 恰 1 行）；**失败重试队列未做**，属平台级异步基础设施，宜单立 spec。
- **导出→导入往返 + 差异→A13 推送（科目 6051）+ 跨项目隔离 + 公式重开** 的浏览器实测（`d4-33-36` 5.4 / B6）：
  代码层守卫已覆盖同一行为，浏览器侧未跑。

---

## 四、留在 active 的相关 spec（**不在本批**）

- `workpaper-html-onlyoffice-bidirectional-writeback-closure` —— 平台总纲，仍有 **5 个 `[-]`**
  （Tasks 61 / 71 / 72 / 74 / 75），`legacy_fake_bidirectional` 现为 137，**不具备归档条件**。
- `d-cycle-sheet-bidirectional-expansion` —— 9/9 但**只有 tasks.md + README.md，无 requirements/design**，
  范围是 D1–D7 全循环（D4-3 为首 canary），非纯 D4，留待单独裁决。
- `oo-html-writeback-performance` / `workpaper-sync-static-cell-sheet-writeback` /
  `excel-*` 系列 / `workpaper-page-formula-toolbar-closure` —— 平台同步引擎侧，与 D4 正交。

---

## 五、逐轮修复史（真栈根因，非猜测）

完整五轮记录见 **`docs/operations/d4-bidirectional-writeback-inventory.md`**（append-only）：

| 轮次 | 主题 |
|---|---|
| 第一~二轮 | 逐张侦查 + 后端受管面（instrumentation / contract / provider）逐组落地 |
| 第三轮 | `value_type=json` 单元格往返 + 转置 sheet `other_sheet_parts` 假 drift（方案 A：转置 part 并入 `all_managed_parts`）+ D4-2 L2 真栈跑通 |
| 第四轮 | 前端「在线编辑」切换器不可达 7 张全修 —— 6 类真 bug（`.fields` undefined render crash / `debounceTimer` TDZ / `ooHealthy` 竞态 / 错误健康端点 404 / 缺 descriptor computed / e2e 定位器 `(?!\d)` 误命中字母后缀）+ 全 20 张 dedicated sync L1 全绿 |
| 第五轮 | 僵死 lease × 从未接管内容 room 的 500 死循环（`room_never_took_custody` 治本分流）· 公式删除恒假成功（缺 `project_id`）· `_ORDER_PREFIX_RE` 贪心吞正文破坏 stable key identity · OO 健康探针阻塞 IO + 逐底稿重打（httpx 异步 + 15s TTL 缓存）· room 序号守卫判据收窄+扩面 · 证据 `sheet_name` 改记观测值 |
