# 按项目订阅失效与写 stale 端点鉴权（ACNR P2 批次）

本批次把 ACNR 底座的两组收口落地：D8（T23/T25）给三个会写 stale 的端点加项目鉴权、修掉一个越权写（IDOR），并把硬编码的年度 2025 换成按项目审计年度补齐；D9（T27/T28）把前端 `useAcnr` 从"进程级单订阅"改成"按当前项目订阅 SSE 失效、随项目切换切订阅、随 scope 释放",并补测试证明解析缓存按项目隔离。批次覆盖三个提交：`60168a027`（D8 代码）、`841308327`（D8 文档/勾选）、`64eade2e1`（D9），相对上一批 P0（`d1da8ea95`）。

Watch for：
- （confirmed，非阻塞）本批次**不包含** 409 快照错误不回退 V1 的处置。`addressRegistry.ts` 的 `resolve`/`validate` 仍是 `catch (e) { console.warn(...) }` 后无条件落 legacy V1，没有对 409 做区分——这属于 T18 / R2-F13（D5），tasks.md 标 `[ ]` 未做，后端版本锁 409 映射也未入库。评审指令点名了该项，但它不在已交付批次内，记为证据缺口。
- （confirmed，非阻塞）T28 的浏览器实测如实标 `[ ]*`「代码已改但未实测」，依赖尚未入库的 acnr_targets / display 取数管线（P0/P1 T10/T14/T16）；无截图，符合其自述的延后理由。
- （confirmed，非阻塞）统一中文显示、外部命名空间中文提示（T29/T31）均为后续任务，本批次未涉及。
- 测试通过数与 tsc 变异证明取自提交信息，按指令未重跑。

**Verdict**: APPROVED

## High-level view

D8 的越权写修复是干净的。`POST /api/linkage-bus/impact` 现在在写 stale 之前先对 `body.project_id` 做 `assert_project_permission(..., "edit")`，年度缺省时经 `fetch_project_audit_year` 补齐、补不出返 422 `YEAR_REQUIRED`（不再写死 2025）；会写库的 `GET /impact-by-addr` 改成只读 `preview_impact`（不写 DB、不推 SSE、不记审计）并挂 `readonly` 访问；无鉴权即按任意 project_id 写 stale 的 `notify-cell-change` 下线为 410 且不触达数据。前端对应把日历年兜底去掉、无 project_id 不发请求、403 静默不阻断保存，三处行为都收敛在 `useStaleImpact.notify` 一个函数里，`useEditorSave` 只是委托它。

鉴权棘轮朝正确方向收紧：identity-only 基线 87→84，两个 linkage-bus 端点进 `_FIXED_ENDPOINTS` 显式承接，年度棘轮删掉 `address_registry_v2.py` 条目，都是只减不增。鉴权测试除 401/403 外还断言了该放行的身份（edit 成员、admin、readonly 走只读预览）真能用，满足"测放行"的要求。

D9 的订阅模型正确。`useAcnr` 签名改 `MaybeRefOrGetter<string|null|undefined>`，只有在存在 effect scope（组件 setup / Pinia setup store）时才订阅，并用 `watch(currentProjectId, …, {immediate:true})` 在 A→B 切换时先 cleanup A 再建 B、`onScopeDispose` 释放；普通函数内调用不订阅（无从释放连接）。无参 `useAcnr()` 的合法例外（全局模板库、只列目录）登记在 `acnrCatalogOnlyCallers.ts`，由 AST 守卫双向校验（多一个、少一个、登记不存在文件都红）。

失效隔离本就在 `_onAcnrInvalidate` 里（仅 project_id → 只清该项目 resolve 缓存；携带新 catalog_version → bump epoch 全清），本批补的两个测试证明了"A 失效后 B 仍命中"与"catalog_version 变化清目录级"，属于补证不是补实现，描述与代码一致。

多项目 SSE 的浏览器级验收被如实推迟（依赖未入库的取数管线），单测层面的隔离已覆盖；多 worker + Redis pub/sub 本机不具备，降级到 TTL 收敛也写清了。

<details>
<summary>Issues (3)</summary>

1. **409 快照回退 V1 未在本批次处置** — `addressRegistry.ts` 的 `resolve`/`validate` 仍无条件 catch 后落 legacy，没有 409 区分；属 T18/R2-F13（D5）后续工作，非本批次缺陷。评审指令点名但不在交付范围，记为证据缺口，不阻断本批次。
2. **T28 多项目 SSE 浏览器实测缺截图/查库读回** — 如实标 `[ ]*`，依赖未入库的 acnr_targets/display 管线，单测隔离已覆盖；待管线到位后补，不阻断。
3. **测试结果与 tsc 变异证明来自提交信息** — 按评审指令未重跑 coder 已跑套件；若后续怀疑可窄范围点抽 `useAcnr_project_subscription.spec.ts` 与单区域 tsc。

</details>

<details>
<summary>Details</summary>

### 写 stale 的 IDOR 修复与年度补齐

`notify-cell-change` 原实现是本批次修掉的核心越权点：它 `body: dict` 取任意 `project_id`、`year` 写死 2025，不做任何项目鉴权就 `await stale_engine.on_change(uri, project_id, year)` 写 DB stale 标记，且整段裹在 `try/except: pass` 里"永不阻断主操作"。任何登录用户可据此往不属于自己的项目写 stale。本批次把它下线为 410 `ENDPOINT_GONE`、去掉请求体、只留 `get_current_user`、不触达数据，并在前端删掉 `notifyCellChange` 常量——不是加鉴权补丁而是直接退役（前端已无调用方）。

真正承接写 stale 的 `POST /api/linkage-bus/impact` 现在首句 `assert_project_permission(db, current_user, body.project_id, "edit")`，`ImpactRequest.project_id` 从 `str` 收紧为 `UUID`、`year` 从必填 `int` 改 `int | None = Field(None, ge=2000, le=2100)`。年度缺省（None 或 ≤0）时 `fetch_project_audit_year` 补、仍补不出返 422 `YEAR_REQUIRED`，彻底去掉硬编码 2025。`GET /impact-by-addr` 从"会写库的 GET"改为只读 `stale_engine.preview_impact`（新增方法，只做 BFS、显式不写 DB/不推 SSE/不记审计，降级时返回空影响而非回退到写操作的 `mark_stale`），并挂 `require_project_access("readonly")`。

鉴权测试（`test_stale_write_endpoint_authz.py`）既测拒绝也测放行：edit 成员与 admin 非成员 200 且 `on_change` 恰 1 次、拿到请求里的项目与年度；review/readonly 对 `/impact` 403；readonly 对 `/impact-by-addr` 200 且走 `preview_impact`（`on_change` 0 次）；缺年度能补 200、补不出 422；`notify-cell-change` 登录 410、未登录 401 且 AST 断言函数体只有 raise。覆盖了"该放行的角色真能用"这一常被漏掉的维度。

### 前端 stale 通知的降级与年度

前端三处行为收敛在 `useStaleImpact.notify` 一个函数：`if (!payload.project_id) return`（后端要项目鉴权，裸发必 403，先不发）、`if (payload.year) body.year = payload.year` 否则不带 year 交后端补、`if (e?.response?.status === 403) return null`（无权访问静默跳过、不阻断保存）。`useEditorSave` 不自己拼请求，只把 `project_id`/`year`（`wpDetail.value?.year`，可 undefined）传给 `notify`，整段非阻塞 try/catch。年度不再 `|| new Date().getFullYear()` 兜底日历年——与后端"按项目审计年度补齐"同口径，避免日历年与审计年度不一致时写错 stale。

### useAcnr 按项目订阅与生命周期

签名 `useAcnr(projectId?: MaybeRefOrGetter<string|null|undefined>)` 后，`currentProjectId()` 用 `toValue` 解包 ref/getter/静态串。订阅只在 `getCurrentScope()` 为真时建立：

```
if (getCurrentScope()) {
  let _cleanupSSE = () => {}
  watch(currentProjectId, (pid) => { _cleanupSSE(); _cleanupSSE = subscribeInvalidation(pid) }, { immediate: true })
  onScopeDispose(() => { _cleanupSSE() })
}
```

`subscribeInvalidation` 按 projectId 引用计数复用同一总线订阅（同项目多处只建一个、空值 no-op），cleanup 把 refCount 减到 0 才真正 close。A→B 切换、同项目复用、scope 释放归零、普通函数不订阅、空项目不建连接、store getter 切换——`useAcnr_project_subscription.spec.ts` 用 stub 的 open/close/active 计数逐项断言，`beforeEach` 用花括号体（避开"表达式体 mockReset 被当 teardown"的坑），mock 用持久 `mockResolvedValue` 而非 `mockResolvedValueOnce`（`clearAllMocks` 不清 Once 队列的问题不触发）。

`stores/addressRegistry.ts` 改 `useAcnr(() => _projectId.value)`：store 是 Pinia setup store（effect scope 内），refresh 切 `_projectId` 时内部 watch 同步切订阅、随 store 释放。这把 store 单例的订阅也纳入了按项目隔离，不再是全局一个订阅吃所有项目的失效。

resolve 系列的缺省项目从静态 `projectId` 改 `currentProjectId() || undefined`，在调用时点解析当前项目值，cache key 仍含 `project_id: pid`，不同项目各自成键、互不污染，与 `_clearResolveCacheForProject` 的按项目清除一致。

### 无参 useAcnr 登记守卫

`acnrSubscriptionLedger.spec.ts` 用 TypeScript 编译器 API + `@vue/compiler-sfc` 解析非测试 `.ts` 与 `.vue` 的 `<script>`，收集所有零参 `useAcnr()` 调用的文件集合，断言恰好等于 `ACNR_CATALOG_ONLY_CALLERS`（两条：FormulaTab.vue、useAcnrCatalogIndex.ts）。双向校验（extra + missing）+ 登记文件存在性 + `noArgFiles.size === registered.size` 防空转。注释里的 `useAcnr()` 因走 AST 天然排除。独立 grep 复核：生产代码里零参 `useAcnr()` 只出现在 `.spec.ts` 与注释行，未见漏登的生产调用点，与守卫结论一致。

### 失效隔离（补证非补实现）

`_onAcnrInvalidate(projectId, payload)`：`catalog_version` 变化 → `invalidateModuleCache()`（epoch++ 全清）；否则 `_clearResolveCacheForProject(projectId)`（只删 key 含 `"project_id":"<pid>"` 的 resolve 条目）。断线重连 `onReconnect` 也只清该项目。T28 的两个新测试证明"A 收到项目级失效只清 A、B 仍命中（epoch 不变）"与"带新 catalog_version 清目录级 + bump epoch"。commit 信息明确说明隔离逻辑本就存在（design §12.1）、本批补测试，与代码现状吻合，没有把补证当补实现。

</details>

<details>
<summary>文件清单</summary>

D8（`60168a027`）
- `backend/app/routers/linkage_bus.py` — `/impact` 加 edit 鉴权+年度补齐；`/impact-by-addr` 改只读 preview+readonly
- `backend/app/routers/address_registry_v2.py` — `notify-cell-change` 下线为 410、去请求体
- `backend/app/services/stale_propagation_engine.py` — 新增只读 `preview_impact`
- `backend/tests/acnr/test_stale_write_endpoint_authz.py` — 鉴权世界（401/403/放行/410/AST）
- `backend/tests/test_project_endpoint_authz_body_carried.py` — identity 基线 87→84、两端点入 `_FIXED_ENDPOINTS`
- `backend/tests/test_audit_year_calendar_fallback_ratchet.py` + `auditYearCalendarFallbackBaseline.json` — 删 v2 条目
- `backend/tests/test_stale_impact_boundary_unit.py` / `test_stale_impact_schema_pbt.py` — 按只读 preview 契约重写
- 前端 `composables/useStaleImpact.ts` / `useEditorSave.ts` / `services/apiPaths/system.ts` — 去日历年兜底、无项目不发、403 静默、删常量

D9（`64eade2e1`）
- `services/acnr/useAcnr.ts` — 签名改 MaybeRefOrGetter、scope 内 watch 订阅、resolve 缺省项目改当前项目
- `composables/useCurrentProjectId.ts`（新）、`services/acnr/acnrCatalogOnlyCallers.ts`（新登记表）
- `stores/addressRegistry.ts` — `useAcnr(() => _projectId.value)`
- 27 个消费组件/composable — 全部改带当前项目（props/路由/useCurrentProjectId/函数入参）
- `services/acnr/tests/acnrSubscriptionLedger.spec.ts`（新，3）、`useAcnr_project_subscription.spec.ts`（新，9）
- `tsconfig._acnr-d9-subscription.json`（新，单区域变异证明）

完整 diff：`git show 60168a027`、`git show 64eade2e1`
</details>
