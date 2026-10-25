# G4-0d · D2-2 host unified path（浏览器网络取证）

状态：**§9.6 HTML DOM `marker_visible=true` 已锁（2026-09-11）** · `HOST-CONSUMES-UNIFIED-PATH` 谓词 1–8 有据

> 仍**不得**删 `/d2-sync/*`（DEC-08）。  
> **G4-0a**：`GtOnlyOfficeSheet.forceSave()` 已 fail-closed。  
> **G0-4**：entry 已投影 `ONLYOFFICE_VERIFIED`（见 `../g0-4-host-consumes-unified-path/`）；本目录是 runtime 源捕获。

## §6.4 `HOST-CONSUMES-UNIFIED-PATH` 矩阵

| # | 谓词 | 结果 | 证据 |
|---|---|---|---|
| 1 | `USER_SYNC_PREFIX` | **PASS** | `network-and-callback.json` |
| 2 | 无 `/d2-sync/*` | **PASS** | `d2_sync_hits=0` |
| 3 | callbackUrl room-bound | **PASS** | `callback_url_keys` |
| 4 | `application.state=applied` | **PASS** | `d908fa12-…` rev 31（marker `g4h709665`） |
| 5 | operation 非 error + `application_id` | **PASS** | `predicates-5-8.json` + 本轮 op `23784f8c-…` |
| 6 | content version `source=onlyoffice` + `operation_id` | **PASS** | rev 31 / `content_revision=31` |
| 7 | 不以 `oo_content_revision` 作正确性 | **PASS** | 业务 rev 走 `content_version` |
| 8 | 能力现算 | **PASS** | `capabilityForEntry(manifest)`；`d2_sync_status` 无字面量 `True` |

## §9.6 Playwright

| # | 条件 | 结果 |
|---|---|---|
| 1–5 / 7 | 真栈路径 + applied + rev 前进 | **PASS** |
| 6 | HTML DOM 显示 OO 写入值 | **PASS**（`store_mirrored=true` + `marker_visible=true`，marker=`g4h709665`） |
| 8 | 复原核查 | 部分（测试项目实例可保留 marker 作审计） |

### 本轮闭合的阻塞

1. **DOM 假失败**：Vue 受控 `el-input` 不写 `value` 属性，且 `input.value` 不进 `body.innerText`；改用 virtual text / `input.value`（排除搜索框）+ 硬断言。
2. **并行 forcesave 争 fence**：二次 forcesave 与首次 rematerialize 并行 → `result_bundle_identity_mismatch`，正确 marker 丢失。修复：room 会话级 `pg_advisory_lock` 串行 apply；`assert_can_initiate_request` 拒绝 in-flight apply；桥 `forcesaveInFlight` 门控。
3. **拆方法 NameError**：`_apply_settled_locked` 误用未定义 `merge` → `state.merge`。
4. **假绿**：confirm 失败被 try/catch 吞掉仍 exit 0；改硬断言 confirm + `cs_error===0` + store + DOM。
5. **CS error=1**：DocServer 注册晚；confirm 后等 35s，并对 `doc_not_online` 最多重试 3 次。

### 通过判据（已满足）

`forcesave_cs_error=0` + 新 `application.state=applied` + `html_dom_roundtrip.store_mirrored=true` + `marker_visible=true`。

证据：`network-and-callback.json`（`captured_at=2026-09-11T00:32…`）、`db-check.json`、`predicates-5-8.json`。
