# 底稿 HTML ↔ OnlyOffice 双向回写落地总控

> **状态**：ACTIVE · 实施总控  
> **基线日期**：2026-09-09  
> **覆盖范围**：本文列出的 8 个双向回写、联动与同步相关 spec  
> **动态状态真源**：各 spec 的 `tasks.md`、机器门禁及 evidence；本文不复制第二份任务正文  
> **取代关系**：本文取代 `docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md` 的“当前状态、人员分工、里程碑”部分；旧文档保留为历史调查与实证日志，不再维护动态状态  
> **长期架构真源**：生产代码与数据库约束优先于本文；本文负责跨 spec 的执行顺序、责任边界和验收门

---

## 1. 目标与完成定义

### 1.1 目标

将底稿的 HTML 结构化视图与 OnlyOffice Excel/Word 编辑视图落成一条真实、可审计、可恢复的双向链路：

```text
HTML 业务变更
  → 唯一业务提交
  → immutable content version
  → published representation
  → OnlyOffice room

OnlyOffice durable callback
  → immutable incoming artifact
  → application + extract + three-way merge
  → 唯一业务提交
  → canonical rematerialization
  → HTML/OnlyOffice 双侧刷新
```

落地后必须同时满足：

1. 一个业务变更只推进一次 `content_revision`；
2. representation-only 升级不推进业务版本；
3. HTML 与 OO 不存在各自独立的 current artifact；
4. callback durable 后可恢复、可重放、不会产生第二次业务提交；
5. 插行、删行、动态列及跨 sheet 引用按声明式 mutation plan 一次应用；
6. 冲突不静默选边，保留 base/current/incoming 三值与解决轨迹；
7. 每个双向 entry 都有请求路径、真实 OnlyOffice、浏览器 DOM、数据库 timeline 和 artifact digest 证据；
8. 无法合法双向的 entry 明确裁为 `single_html`、`single_onlyoffice`、`opaque`、`missing` 或 `unreachable`，不得保留“看起来能切换”的假双向入口。

### 1.2 三种“回写”必须分开

本文只在边界清楚时使用“双向回写”一词：

| 类型 | 定义 | 是否属于运行态 HTML ↔ OO 真双向 |
|---|---|---:|
| 运行态内容双向 | HTML projection 与 OO published artifact 经同一 content version、adapter、callback/application、merge 往返 | 是 |
| 模板 round-trip | OnlyOffice 模板编辑生成新模板版本，影响未来实例 | 否 |
| sidecar 联动 | guidance、formula record、UI rail 等独立记录的发布与消费 | 否 |

模板、guidance、formula 不得借“联动”名义暗中推进底稿业务 revision。

### 1.3 每个 entry 的完成定义

一个 entry 只有同时满足以下条件，才能标记为 `bidirectional_verified`：

- source-backed manifest 中有唯一稳定 `entry_id`；
- authority model、template/instrumentation/contract typed children 与 approved bundle 完整；
- current published representation 存在，且冻结 bundle、adapter、structure/identity digest；
- `PublishedIdentityObserver.observe()` 请求路径真跑成功；
- `WorkpaperSyncAdapterRegistry.register_from_manifest(session=...)` 真注册，`resolve_for_entry()` 可解析；
- render-config、materialize、extract 均使用同一份 frozen definitions；
- HTML → OO 与 OO → HTML 均产生合法 operation/application/timeline；
- same-field conflict、different-field merge、rollback、refresh/reopen 通过；
- 适用时插行、删行、排序、复制、动态列、跨 sheet 传播通过；
- 真实 OnlyOffice 与 Playwright required scenarios 已执行；
- evidence source commit、manifest digest、bundle digest、representation generation 均未 stale。

“类存在”“测试文件存在”“registry 绑定了计划”“首版 representation 已发布”均不能单独替代以上定义。

**另加一条宿主条件（2026-09-09 因 D2-2 实证补入）**：entry 的**用户宿主真实请求**必须命中统一 coordinator，并留下 application/operation/content version 三类记录。manifest 把 `capability` 写成 `bidirectional`、adapter 已注册、首版 representation 已发布，这三件事同时成立时**仍可能**是 legacy 旁路 —— D2-2 就是该形态的实例，详见 §2.4。

### 1.4 全局完成定义

全局 closure 必须由机器现算，而不是把 8 个 `tasks.md` 的 `[x]` 数量相加：

1. manifest 中每个 entry 均有能力裁决和验收状态；
2. `bidirectional` entry 全部达到 `bidirectional_verified`；
3. 非双向 entry 均有封闭 verdict、原因、owner 和解除条件；
4. writer/resolver/version domain 阻断项全部归零；
5. required scenarios 无 `failed`、无无理由 `unverifiable`、无 stale evidence；
6. legacy dual-mode、旧 endpoint、localStorage 基线和假成功文案按 source-backed deletion plan 删除；
7. 删除后重新生成 manifest、registry、evidence，并完整复验；
8. 归档门依赖所有业务迁移、真实 OO 与变异门，不允许提前归档。

---

## 2. 真源优先级与当前事实快照

### 2.1 真源优先级

发生冲突时按以下顺序裁决：

1. 数据库约束、生产调用链与运行态请求结果；
2. source-backed manifest、生成器、机器门禁和 evidence；
3. 各 spec 的 requirements/design/tasks；
4. 本总控；
5. 历史分工书、聊天记录和人工汇总数字。

不得用本文覆盖生产事实。发现漂移时先修生产或 spec 真源，再更新本文的裁决记录。

### 2.2 8 个 spec 的 2026-09-09 主/全任务双口径快照

此表仅是启动快照；执行时必须重新扫描行首 checkbox，并区分非 optional 主任务与包含 optional(*) 的全任务，不能把本表作为永久分母。

| 层级 | Spec | 快照（主/全任务） | 当前诚实状态 |
|---|---|---:|---|
| 同步内核 | `workpaper-html-onlyoffice-bidirectional-writeback-closure` | 66/77（主=全）；1、2、20、60、62、64 为 `[~]`；61、71、72、74、75 为 `[-]` | 内核已成形，全量 writer/resolver、Word 真 OO、最终变异与 legacy 删除未闭 |
| 生产表示准入 | `published-representation-production-path-and-lane-adjudication` | 28/28 主任务；43/43 全任务 | 可发布不等于运行态双向；消费门仍需统一现算 |
| 局部结构变更 | `excel-structural-row-insertion-and-shift-aware-verification` | 21/22 主任务；26/27 全任务；20 为 `[~]` | 位移能力接近完成，仍需真实生产闭环 |
| 工作簿传播 | `excel-workbook-wide-row-change-propagation` | 30/30（主=全） | 删除结构矩阵、CAS/幂等和生产接线仍需按本文复验 |
| 自定义实例 | `custom-workpaper-template-ingestion-and-sync-closure` | 15/19（主=全）；10、14、18、19 为 `[~]` | 受四个 SYNC gate、审批和真实 Playwright 阻塞 |
| 模板覆盖 | `excel-template-override-layer-and-onlyoffice-template-editor` | 25/27（主=全）；103、23 为 `[-]` | 未来模板链接近完成，仍缺 CAS、幂等、reconciler/永久变异 |
| Guidance sidecar | `workpaper-guidance-content-closure` | 18/23（主=全） | 工作卡与 C1/C2 未闭，不得宣称 closure |
| Formula sidecar/UI | `workpaper-page-formula-toolbar-closure` | 15/15（主=全） | sidecar 与 shell 完成，不代表物理 workbook 公式回写 |

### 2.3 禁止的状态表达

- discovery/characterization 完成但生产能力未交付：使用 `[~]`，不得使用 `[x]`；
- upstream 实现缺失：使用 `[-]` 并写明唯一解除条件；
- 环境不可用：使用 `UNVERIFIABLE`，不得写成实现失败；
- 机器判据失败：使用 `FAILED`，不得以人工说明改绿；
- 请求路径已通但真实 OO 未跑：最多 `REQUEST_PATH_VERIFIED`；
- 真实 OO 已跑但 source/evidence stale：退回 `STALE`。

### 2.4 D2-2 反例基线（2026-09-09 代码 + 数据库 + 浏览器三边实证）

D2-2「应收账款明细表」是全平台唯一被完整实现过双向算法的 Excel entry，因此它既是**第一迁移 canary**，也是当前**唯一可用的反例基线**。基线结论：

> **算法构件已齐，用户宿主未消费统一内核。** manifest 已登记 `capability: bidirectional`，但真实请求走 D2 专用旁路与 legacy callback，统一 room/application/content-version 内核在生产链上零命中。

因此本文对 D2-2 的裁决是 `REQUEST_PATH_LEGACY`，**不是** `bidirectional_verified`。

#### 2.4.1 五层身份不可混同

同一张表在六个层面有六个不同标识符，混用任一个都会推进到没人读的键上（表现为「代码改了但 OO 还是旧内容」）：

| 层 | 标识符 | 真源 |
|---|---|---|
| 业务 sheet code | `D2-2` | `wp_index.wp_code` |
| 工作簿物理 sheet | `明细表D2-2` | `d2_bidirectional_bridge.MANAGED_SHEET` |
| componentType | `d2-accounts-receivable` | `backend/app/data/wp_code_overrides.json` |
| sync manifest entry | `xlsx/gt-d2-accounts-receivable` | `backend/data/workpaper_sync_entry_manifest.json` |
| adapter / contract | `d2.receivable_detail` | `backend/data/workpaper_sync_contracts/d2.receivable_detail.json` |
| OO room entry | `xlsx-sheet/D2-2/D2-2` | `onlyoffice_room_identity.sheet_entry_id()` |

禁止把它们合并成一个 ID，也禁止用 manifest entry 反推 room entry。

#### 2.4.2 实际请求路径（浏览器只读观察）

登录后打开 D2 底稿并切到「明细表D2-2」，实际命中：

```text
GET /api/workpapers/{wp_id}/render-config
GET /api/workpapers/{wp_id}/checklist-responses
GET /api/workpapers/{wp_id}/d2-sync/status
GET /api/workpapers/{wp_id}/sheets/D2-2/onlyoffice-config?project_id=...
```

统一内核的用户面前缀 `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}`（`wp_sync_router.USER_SYNC_PREFIX`）**零命中**。

两处关键观测值：

- `/d2-sync/status` 返回 `bidirectional: true`，而该值在 `d2_sync_router.py::d2_sync_status()` 内是字面量常量，不是能力现算；
- `onlyoffice-config` 返回的 `editorConfig.callbackUrl` 指向 `/api/workpapers/{wp_id}/sheets/D2-2/onlyoffice-callback` 且 **query 为空**。而 `wp_onlyoffice_router._has_room_bound_callback_query()` 要求 `room_id/generation/doc_key/route_credential_id` 四项齐全才委派 `CallbackDeliveryService`；四项皆缺 ⇒ 结构上必然落进 legacy 分支。

#### 2.4.3 数据库基线（只读查询）

| wp | wp_code | file_version | content_revision | current_content_version | content applications |
|---|---|---:|---:|---|---:|
| `ef7f88e3…6c88` | D2 | 9 | 3 | `4bde6336…e0ed` | 0 |
| `4eac7362…e895` | D2-2 | 6 | 0 | NULL | 0 |
| `1cf770c2…f3f6` | D2 | 2 | 0 | NULL | 0 |

对有版本记录的 `ef7f88e3…6c88` 进一步展开：

- 3 个 `working_paper_content_version` 全部 `source='html'`、`operation_id IS NULL`；
- 3 个 representation 全部 `generation=1`、`reason='content_commit'`、`adapter_id='d2.receivable_detail'`；
- entry state 当前指针指向 revision 3 对应的 representation，`representation_generation=1`；
- 3 条 `working_paper_sync_operation` 全部 `direction='html_to_oo'` 且 `state='error'`，`error_stage='content_commit'`，错误码依次为 `excel_materialize_footer_anchor_drift`、`pending_mutation_payload_mismatch`、`roundtrip_projection_mismatch`，且 `room_id/application_id/forcesave_request_id` 均为 NULL；
- `working_paper_content_application` = **0**。

判读：HTML 侧提交与首版发布确实发生过，但 **OO→HTML 的 durable application 从未成立**；三条 html_to_oo 尝试全部在 commit 阶段失败。`content_revision` 与 `file_version` 的差值（3 对 9）正是「legacy callback 自增 file_version、不进业务版本域」的直接痕迹。

#### 2.4.4 已定位的迁移 gap

| # | Gap | 位置 | 违反的裁决 |
|---|---|---|---|
| 1 | 宿主用专用 bridge 而非统一 sync host | `audit-platform/frontend/src/components/workpaper/sync/useD2SyncBridge.ts` | §4.1 |
| 2 | HTML 保存直接 UPSERT + 自行 `db.commit()` | `checklist_responses.py::batch_save_checklist_responses` | §3.1 |
| 3 | 明细整表塞进单行 `remark` JSON（`item_id='D2-detail-rows'`） | `useD2FormData.ts` + `checklist_responses` | §3.1 |
| 4 | push/pull/forcesave 三个专用端点绕过 coordinator | `d2_sync_router.py` | §4.1 / §4.2 |
| 5 | `_write_store_rows()` 与 narratives 各自 commit，存在部分成功窗口 | `d2_sync_router.py` | §3.1 |
| 6 | 推进 `working_paper_oo_content_revision` 而非业务 revision | `_bump_oo_revision()` | §3.1 |
| 7 | `bidirectional: True` 为字面量 | `d2_sync_status()` | §1.3 |
| 8 | 无 fingerprint 时 `_assert_not_stale()` 放行 | `d2_sync_router.py` | §4.2 |
| 9 | 专用端点只依赖 `get_current_user`，未走 `require_wp_edit_permission + enforce_wp_gate` | `d2_sync_router.py` | §10.2 |
| 10 | callback URL 不含 room-bound 四项 | `get_sheet_onlyoffice_config()` | §4.2 |
| 11 | legacy callback 原地覆盖文件并 `wp.file_version += 1` | `post_sheet_onlyoffice_callback()` | §3.1 |
| 12 | 不产生 immutable incoming / application / three-way merge | 同上 | §4.2 |
| 13 | manifest `capability=bidirectional` 但 `browser_case`/`contract_test` 皆 `null` | manifest D2 entry | §1.3 |
| 14 | 共享 OO 组件把 forcesave 硬编码到 D2 专用端点 | `GtOnlyOfficeSheet.vue::forceSave()` | §4.2 |
| 15 | 专用端点的 artifact 与 room entry 固定为 D2（`_OO_WP_CODE`/`_OO_SHEET_PARAM = "D2-2"`） | `d2_sync_router.py` | §4.2 |

#### 2.4.5 gap 14/15 是平台级泄漏，不是 D2 局部问题

manifest 共 186 个 entry，其中 **179 个**挂载同一个 `GtOnlyOfficeSheet`；该组件 `forceSave()` 的请求字面量是 `/api/workpapers/{wpId}/d2-sync/forcesave`。而 `d2_sync_router._load_context()` 把 artifact 固定解析为 `{oo_dir}/D2-2.xlsx`，`_bump_oo_revision()` 固定推进 room entry `xlsx-sheet/D2-2/D2-2`。

含义：任何非 D2 宿主一旦调用 `forceSave()`，命令的是 D2-2 的文件与 D2-2 的 room。**替换顺序因此被固定**：必须先让宿主改用 `POST {USER_SYNC_PREFIX}/rooms/{room_id}/forcesave`，才能安全删除 `/d2-sync/*`；反序执行会同时打断 179 个 entry。

#### 2.4.6 可复用资产（迁移时保留，不重写）

- `d2.receivable_detail` contract：39 列、row UUID 稳定身份、formula mask、managed sheet 声明；
- `pilot_d2_large_json.py` 的 materialize/extract 算法；
- HTML 侧 debounce flush（`flushPendingSave()`）与切模式前 `forceSave()` 的耐久确认三态；
- sha256 + mtime_ns + size 的 stale 判据形态；
- `d2_bidirectional_bridge.py` 的字段映射与 narrative 块定义。

#### 2.4.7 必须替换项

| 现状 | 目标 |
|---|---|
| `useD2SyncBridge` | 统一 workpaper sync bridge/host |
| `/d2-sync/push-to-excel` | `POST {USER_SYNC_PREFIX}/materialize` |
| `/d2-sync/forcesave` | `POST {USER_SYNC_PREFIX}/rooms/{room_id}/forcesave` |
| `/d2-sync/pull-from-excel` | durable callback → `RequestApplicationService` → `OoToHtmlCoordinator` |
| legacy `sheets/{sheet}/onlyoffice-callback` | `POST /api/workpaper-sync/rooms/{room_id}/onlyoffice-callback` |
| checklist 直接 commit | `ContentMutationService.commit(...)` |
| `working_paper_oo_content_revision` | `working_paper.content_revision` + content version |

---

## 3. 不可违反的架构裁决

> **本节全部条款是 target invariant，不是现状陈述。** 生产代码中已知的违反项见 §2.4.4；每条裁决下方如标注「当前违反」，即表示该约束尚未在生产链上成立，禁止据本节文字宣称已达标。

### 3.1 唯一业务提交边界

生产真源：`backend/app/services/workpaper_sync/content_mutation.py`。

`ContentMutationService.commit(...)` 是 HTML save、upload、WOPI、OO callback、冲突解决、rollback 等业务 writer 的唯一 content commit 边界。它必须独占：

- business revision CAS；
- content version 创建；
- compatible representation 创建；
- entry current pointer；
- room baseline；
- durable outbox；
- 本次业务事务的唯一 commit。

任何业务 writer 自己推进 `_version`、`file_version`、`content_revision` 或自行 `session.commit()`，均视为 P0 缺陷。

**当前违反（2026-09-09 实证）**：`checklist_responses.py` 保存路径自行 `db.commit()`；`d2_sync_router.py` 的 `_write_store_rows()` 与 narratives 写入各自 commit；`wp_onlyoffice_router.py` legacy callback 分支自增 `wp.file_version`；`_bump_oo_revision()` 推进独立的 `working_paper_oo_content_revision`。这四处构成 §2.4.4 的 gap 2/5/6/11，是 Phase 1 的 writer inventory 首批对象。

### 3.2 representation-only 边界

生产真源：`backend/app/services/workpaper_sync/representations.py`。

`RepresentationService.finalize_candidate(...)` 只允许在既有 content version 上生成 immutable representation generation。它不得：

- 接受新的业务 projection；
- 创建 content version；
- 推进 `content_revision`；
- 修改历史 representation；
- 将 incoming artifact 原地晋升为 current。

### 3.3 canonical artifact 的四层职责

| 职责 | 唯一真源 | 禁止事项 |
|---|---|---|
| 文件字节、staging、incoming sealing、immutable publish | `workpaper_sync/artifacts.py` 的 `CanonicalArtifactRepository` | 不持有 DB session，不决定业务 current |
| 根目录与路径安全 | `workpaper_sync/canonical_paths.py` | 禁止各调用点自拼 `backend/storage` |
| config/download/callback/materialize/extract 等只读解析 | `workpaper_sync/resolution.py` 的 `CanonicalResolutionService` | candidate、alias、非 current 不得混入历史读取 |
| 业务版本及 current pointer | `ContentMutationService` / `RepresentationService` | 文件存在不等于数据库可见 |

### 3.4 `structure_hash` 单一语义裁决

**裁决：`structure_hash` 只表示 contract 管理范围内的结构与 identity 坐标摘要；整份文件字节摘要只使用 `artifact_sha256`。**

理由：

- `artifact_sha256` 已完整表达文件字节身份；
- 用同一个 `structure_hash` 同时保存全文件摘要和受管结构摘要会导致刚发布即漂移；
- adapter、entry gate 与 `PublishedIdentityObserver` 需要比较的是受管结构，不是 ZIP 字节；
- 未管理区域等值由独立 verifier 负责，不应挤入 `structure_hash`。

**当前生产事实（2026-09-09 已核代码调用链）**：该裁决的计算真源已经落地，不得再造第二份实现。

- `backend/app/services/workpaper_sync/publish_time_structure_hash.py` 已提供 `compute_structure_hash_from_artifact()`；
- 它直接复用 `published_identity_observer.recompute_structure_hash()` 与同一批结构观测原语，发布时刻和请求时刻没有两份公式；
- `content_mutation.py::_projection_structure_hash()` 已调用该函数；
- `projection_first_publication.py::publish_first_generation()` 已从 instrumentation spec 取得同构 anchors；
- `backend/scripts/fix/fix_projection_representation_rehash.py` 已能识别旧 representation，但当前 apply 路径复用 `publish_first_generation()` → `ContentMutationService.commit()` 并记录 `new_revision`；在修成 representation-only 前，它只能作为只读诊断入口，不能视为合规迁移宿主；
- `backend/tests/workpaper_sync/test_projection_structure_hash_semantics.py` 已锁定新旧语义和调用接线。

后续工作是**收敛与取证**，不是重写计算器：

1. 所有 publication/finalize 调用方只委托现有 `publish_time_structure_hash.py`，禁止复制 canonical digest 公式；
2. 首版发布不得再以整份 XLSX 归一化摘要填充 `structure_hash`；
3. 已发布 representation immutable，不允许原地改 hash；
4. rehash apply 禁止复用 `publish_first_generation()`；应以现有 content version 生成 candidate，经 `RepresentationService.finalize_candidate()` 创建新 generation 并切 pointer，business revision 必须保持不变；
5. 旧 generation 保留可审计，标记 superseded；
6. 迁移前后验证 visible content、unmanaged OOXML、bundle 与 artifact digest；
7. 请求路径用 `PublishedIdentityObserver` 对迁移后的 current generation 真重算；
8. 保持反向变异：改回 whole-file hash 或绕开共享函数时必须打红。

### 3.5 结构引擎只产计划，不拥有业务事务

`excel_row_shift.py` 与 `excel_workbook_row_change.py` 负责生成、校验、应用确定性的结构 mutation plan，但不得自行推进 business revision。

唯一执行顺序：

```text
resolve managed region
  → adjudicate typography placeholder
  → build local row plan
  → expand workbook-wide propagation plan
  → validate non-overlapping write set
  → stage once
  → verify once
  → ContentMutationService.commit once
```

局部位移与全工作簿传播必须有不相交 owner：

- local engine 拥有目标 sheet 内部坐标与本地结构；
- workbook engine 只扩展外部 sheet 对目标区间的引用；
- 同一公式 token 只能由一个 handler 改写；
- coordinator 对 write set 做重复坐标检测，发现双写立即失败。

### 3.6 模板与运行态实例严格隔离

模板覆盖链只影响未来实例：

```text
firm default / group custom / project override
  → versioned template resolution
  → future workpaper instantiation
```

运行态项目底稿的 OO callback 不得反写组织模板；模板 editor 的保存也不得改现有项目的 current representation。两者只能通过显式“从实例提升为模板候选”审批流程交汇。

### 3.7 Guidance 与 Formula 永久 sidecar，除非显式进入业务提交

当前裁决：

- Guidance 继续是 publication/supplement/rail；
- Formula v2 继续是 sidecar formula record 与页面 shell；
- 二者默认不写物理 XLSX/DOCX，不推进业务 revision。

若后续要求物理公式落入 workbook，必须新增独立 spec，将 formula address 解析、adapter materialize、OO 反向提取和冲突合并接入 `ContentMutationService`；不得直接在现有 toolbar 中偷偷写文件。

---

## 4. 生产双向时序

> **§4.1 与 §4.2 描述目标时序，不是当前生产链的实际走法。** 2026-09-09 实测：D2-2 宿主一次都没有经过 `MaterializeCoordinator`、`ContentMutationService`、`RoomService`、`CallbackDeliveryService`、`RequestApplicationService`、`OoToHtmlCoordinator`；其余 178 个挂载同一 OO 组件的 entry 亦无实证。判断某 entry 是否真走本节时序，必须用 §6.4 的 `HOST-CONSUMES-UNIFIED-PATH` 谓词，不能读本节文字。

### 4.1 HTML → OnlyOffice

唯一入口：`MaterializeCoordinator`，生产装配位于 `backend/app/routers/wp_sync_router.py`。

1. `SyncEndpointGuard` 先认证、route scope、scope index、可见性与权限；
2. source-backed manifest 解析唯一 entry；
3. 请求期 `build_production_registry()` + `register_from_manifest(session=...)`；
4. `assert_bidirectional_ready()` 校验 capability、authority、bundle、contract、room profile；
5. 创建带 expected revision、payload digest、TTL、Idempotency-Key 的 pending mutation；
6. coordinator 创建 operation shell；
7. adapter 按 frozen definitions materialize；
8. row/workbook mutation plan 在 staging 中应用并 roundtrip extract；
9. `ContentMutationService.commit(...)` 单事务发布业务版本和 compatible representation；
10. room/participant/baseline 与 operation terminal state 落库；
11. 返回 launch descriptor，前端不得自行拼 doc_key、URL 或 current path；
12. 重开时从 published current representation 解析，不读取 candidate/current alias。

失败原则：

- preflight 失败：零 operation、零 room、零 artifact；
- staging 后 DB 失败：只留下不可见 orphan，由 reconciliation 回收；
- revision CAS 失败：409，不自动覆盖；
- definition/identity drift：ERROR，不降级空 adapter。

### 4.2 OnlyOffice → HTML

唯一入口：`CallbackDeliveryService` + `OoToHtmlCoordinator`。

1. callback route credential/claim 校验；
2. 校验 callback status、room/generation、request correlation；
3. 安全下载 OO artifact；
4. `CanonicalArtifactRepository.seal_incoming()` 封存 immutable incoming；
5. durable 前失败返回非零 callback error；
6. durable 后立即 ACK `error=0`，后续失败进入 recovery，避免 OO 重放副作用；
7. `RequestApplicationService` authorization-first 冻结 request/application identity；
8. dedupe/fold request sequence，不产生第二个 application；
9. `OoToHtmlCoordinator` 只读取 application 绑定的 durable incoming；
10. adapter 基于 frozen bundle extract base/current/incoming；
11. three-way merge：不同字段自动合并，同字段形成 conflict；
12. 最终授权 fence 在 publish 前与写库前各执行一次；
13. resolved mutation 进入 `ContentMutationService.commit(...)`；
14. merged 与 incoming 不同则 canonical rematerialize，并要求 refresh/reopen；
15. operation/application/recovery/timeline/outbox 同步落终态；
16. HTML 刷新必须读取新 content version，不直接读取 callback 文件。

### 4.3 多人协作与关闭

共享 room 必须验证：

- 两个独立用户、同一 generation；
- A 发起 forcesave、B 的贡献仍进入聚合 artifact；
- initiator、route participant、contributors 分离记录；
- 两种关闭顺序；
- A terminal 前/后 B close；
- leader promotion 前 revoke/expire；
- 有 successor 接任与无 successor `recovery_required`；
- `reconcile_close_intents()` 重入幂等；
- 适用路径最终 exactly-one close-capture。

不得用同一浏览器 context 的两个 tab 冒充两个独立用户。

---

## 5. 8-spec 项目地图与责任边界

### 5.1 覆盖的 spec

1. `.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/`
2. `.kiro/specs/published-representation-production-path-and-lane-adjudication/`
3. `.kiro/specs/excel-structural-row-insertion-and-shift-aware-verification/`
4. `.kiro/specs/excel-workbook-wide-row-change-propagation/`
5. `.kiro/specs/custom-workpaper-template-ingestion-and-sync-closure/`
6. `.kiro/specs/excel-template-override-layer-and-onlyoffice-template-editor/`
7. `.kiro/specs/workpaper-guidance-content-closure/`
8. `.kiro/specs/workpaper-page-formula-toolbar-closure/`

### 5.2 分层责任

| 层 | 唯一责任 | 不负责 |
|---|---|---|
| 核心同步内核 | content/application/operation/room/callback/merge/recovery | 具体 Excel/Word 业务字段定义 |
| Published lane | definition DAG、首版 representation、lane adjudication | 业务 revision 与浏览器 UI |
| Structural row | 单 sheet 位移、identity、结构验证 | 跨 sheet 引用传播与 commit |
| Workbook propagation | 跨 sheet 依赖扩展、删除传播 | 本地 managed region 识别 |
| Custom ingestion | custom/opaque 项目实例、审批、staging CAS | 组织模板直接覆盖运行态实例 |
| Template override | 模板版本、解析优先级、未来实例 | 项目底稿 OO callback |
| Guidance | 指导内容、rail、handoff evidence | workbook body |
| Formula | formula sidecar、toolbar、shell | 未经新 spec 的物理 workbook 公式写入 |

### 5.3 共享文件锁

以下共享面禁止并行编辑：

| 文件/目录 | 冲突双方 | 接手规则 |
|---|---|---|
| `excel_row_shift.py`、`excel_materialize.py`、`excel_extract.py` | Structural ↔ Workbook propagation | Structural 完成本地 contract 和接线后，Workbook lane 接手；通过单一 handoff evidence 交接 |
| `wp_onlyoffice_router.py` | Template override ↔ 核心 Task 71/72 | Template override 收口并冻结接口后，核心清理 lane 接手 |
| manifest/overlay/共享生成器 | Published、核心、前端并发会话 | 收口时一次重生成；变更期间只记录 stale，不反复 approve |
| governance workflow | 多 spec CI | 仅追加归因明确的新 job，不覆盖其他在途 spec 字节区间 |

---

## 6. 跨-spec milestone registry

### 6.1 必须新增的机器真源

实施 Phase 0 新增：

```text
backend/data/workpaper_sync_program_milestones.json
backend/scripts/gen/generate_workpaper_sync_program_milestones.py
backend/tests/workpaper_sync/test_workpaper_sync_program_milestones.py
```

JSON 为生成投影，不允许人工改状态；generator 从 spec 主任务、manifest、生产符号、数据库只读探针和 evidence 重算。

建议 schema：

```json
{
  "schema_version": "workpaper-sync-program-milestones/v1",
  "generated_at": "<ISO-8601>",
  "source_commit": "<git-sha>",
  "manifest_digest": "<sha256>",
  "milestones": [
    {
      "id": "SYNC-UNIFIED-ROOM",
      "producer_spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
      "producer_tasks": ["21", "22", "23", "24", "25", "26", "27", "28", "29", "30"],
      "consumer_specs": ["custom-workpaper-template-ingestion-and-sync-closure"],
      "state": "REQUEST_PATH_VERIFIED",
      "machine_predicates": [
        {
          "id": "room.request-path",
          "result": "pass",
          "evidence_ref": "<repository-relative-path>",
          "source_digest": "<sha256>"
        }
      ],
      "blockers": [],
      "observed_at": "<ISO-8601>"
    }
  ]
}
```

状态封闭词表：

```text
BLOCKED
IMPLEMENTED
REQUEST_PATH_VERIFIED
ONLYOFFICE_VERIFIED
CLOSED
STALE
```

状态只能按顺序前进；source/manifest/bundle/evidence digest 变化时自动退为 `STALE`。

### 6.2 四个 SYNC gate 的生产映射

| Gate | 生产者与机器谓词 | 消费方 |
|---|---|---|
| `SYNC-ENTRY-NAMESPACE` | manifest entry 唯一；profile/source digest 双向锁死；registry `resolve_for_entry()`；无 matcher overlap | Custom Tasks 10/14 |
| `SYNC-MULTI-RESOLVER` | 所有 config/download/callback/materialize/extract intent 委托 `CanonicalResolutionService`；writer gate 的 `multi_resolver=0` | Custom Tasks 10/14、最终 legacy 删除 |
| `SYNC-DURABLE-APPLICATION` | callback durable sealing、application dedupe/sequence、durable 后 ACK=0、recovery 可重放 | Custom Task 14 |
| `SYNC-UNIFIED-ROOM` | RoomService、descriptor confirmation、forcesave/callback/close-intent 同 generation；无第二 room state | Custom Task 14 |

不得再使用 `producer_system: workpaper-sync-version-kernel` 这种无法定位任务和 evidence 的自然语言占位。

### 6.3 其他跨-spec gate

| Gate | Producer | Consumer |
|---|---|---|
| `PUBLISHED-ENTRY-READY` | Published lane + core Tasks 75/76 | registry、Excel/Word pilot、Custom |
| `ROW-MUTATION-READY` | Structural row | Workbook propagation、Published pilot |
| `WORKBOOK-PROPAGATION-READY` | Workbook propagation | Excel 全量 lane |
| `F-SHELL` | Formula shell | Guidance、Custom |
| `G-C0` / `G-ID` / `G-RAIL` / `G-HANDOFF-CONSUMER` | Guidance | Formula、Custom |
| `X-HANDOFF-CONFORMANCE` / `X-RUNTIME-EVIDENCE` | Custom | Guidance closure |
| `TEMPLATE-OVERRIDE-CHANGED` | Template override outbox/event | Guidance inventory stale/rebuild |

`TEMPLATE-OVERRIDE-CHANGED` 必须包含 template identity、old/new version、scope、source digest 和影响 inventory；consumer ACK 前不得把 guidance inventory 标为 fresh。

### 6.4 `HOST-CONSUMES-UNIFIED-PATH`（因 D2-2 实证新增，逐 entry 门）

**存在理由**：D2-2 同时满足「manifest capability=bidirectional」「adapter 已注册」「首版 representation 已发布」「专用 status 端点自报 bidirectional=true」，而真实宿主仍走 legacy 旁路。既有四个 SYNC gate 都不覆盖「宿主到底请求了谁」，所以必须新增本门。

**判据全部为机器现算，且必须逐 entry 独立评估**：

| # | 谓词 | 通过条件 | 反例（当前 D2-2） |
|---|---|---|---|
| 1 | 宿主请求前缀 | 进入编辑视图后的网络记录中出现 `USER_SYNC_PREFIX` 下的请求 | 只有 `/d2-sync/*` 与 `/sheets/{sheet}/onlyoffice-config` |
| 2 | 无旁路端点 | 该 entry 宿主不再请求 `/d2-sync/*` 及 legacy `sheets/{sheet}/onlyoffice-callback` | 三个 `/d2-sync/*` 全在用 |
| 3 | callback 绑定 | `editorConfig.callbackUrl` 带齐 `room_id`、`generation`、`doc_key`、`route_credential_id` | query 为空 |
| 4 | application 成立 | OO 编辑落盘后 `working_paper_content_application` 新增 1 行且 `state='applied'` | 累计 0 行 |
| 5 | operation 终态 | 对应 `working_paper_sync_operation` 到达非 error 终态，且 `application_id` 非空 | 3 条全 error，`application_id` 全 NULL |
| 6 | 业务版本推进 | 新增 content version 的 `source` 为 OO 侧且 `operation_id` 非空 | 3 个 version 全 `source='html'`、`operation_id` NULL |
| 7 | 无第二版本域 | 该 entry 往返期间 `working_paper_oo_content_revision` 不被用作正确性依据 | `_bump_oo_revision()` 是 push 的唯一版本推进 |
| 8 | 能力现算 | 前端能力开关来自服务端现算裁决，源码中不存在 `bidirectional` 字面量常量 | `d2_sync_status()` 返回字面量 `True` |

**状态语义**：8 项全 pass 才可置 `ONLYOFFICE_VERIFIED`；1–3 pass 但 4–6 未取证记 `REQUEST_PATH_VERIFIED`；出现任一旁路请求记 `REQUEST_PATH_LEGACY`（新增封闭词，仅本门使用）。

**consumer**：Phase 4 pilot 退出门、Phase 5 每批 canary、Phase 9 legacy 删除的 pre-delete eligibility。任何 entry 在本门未达 `ONLYOFFICE_VERIFIED` 前，不得把 manifest `capability` 当作双向完成证据。

---

## 7. 实施关键路径

```text
Phase 0 事实与总门治理
   ↓
Phase 1 canonical writer/resolver 与 structure_hash 统一
   ↓
Phase 2 行结构 mutation + workbook propagation
   ↓
Phase 3 首版 published representation + request-path adapter
   ↓
Phase 4 Excel pilots 真实双向
   ↓
Phase 5 Excel 全量 entry 迁移
   ↓
Phase 6 Word 稳定身份与真实双向
   ↓
Phase 7 Custom/opaque 实例闭环
   ↓
Phase 8 Template override + Guidance/Formula sidecar 联动
   ↓
Phase 9 全量 evidence、legacy 删除、归档
```

Template override 与 Guidance/Formula 可在 Phase 1–6 期间并行，但必须遵守共享文件锁；它们不能替代主链 gate。

---

## 8. 分阶段落地任务

### Phase 0：事实、状态和跨-spec DAG 收口

**目标**：先消除假绿与自然语言依赖。

交付：

1. 建 milestone registry、generator、guard；
2. 重新扫描 8 个 spec 的主任务/全任务双口径分母；
3. 将 discovery-only `[x]` 改为 `[~]`；
4. 修正文首过期数字：核心 74→77、workbook 26→30 等；
5. 核心 Task 72 增加对 Task 74 的依赖；
6. 将 Task 74 拆成：
   - 早期逐 writer/resolver 迁移实施；
   - 最后全局计数归零门；
7. 每个跨-spec gate 指向 producer task、机器谓词和 evidence；
8. 历史长篇调查从 tasks 正文下沉 evidence，正文只留当前阻塞与解除条件；
9. CI 增加 DAG 完整性：无孤儿 consumer、无不存在 producer、无依赖环。

退出门：

- 所有跨-spec gate 可由 generator 重算；
- 任何一条 spec checkbox 不能独自把 milestone 推到 `CLOSED`；
- archive DAG 不再能绕过 writer debt。

### Phase 1：canonical kernel 与 hash 语义统一

**目标**：保证后续任何 lane 只有一个业务版本和一套 identity。

交付：

1. 按 writer inventory 逐项迁入 `ContentMutationService.commit(...)`；
2. 删除各 writer 自有 revision/commit，但暂不删仍有调用方的兼容入口；
3. 所有读 intent 委托 `CanonicalResolutionService`；
4. 复核 publication/finalize 的全部调用点均委托现有 `publish_time_structure_hash.py`，删除残余 whole-file `structure_hash` 写法；
5. 先用 `fix_projection_representation_rehash.py` 只读识别旧语义 representation；将其 apply 路径从 `publish_first_generation()` 改为 `RepresentationService.finalize_candidate()` 并锁死 revision 不变后，才允许迁移命中项；
6. artifact root 全部委托 `canonical_paths.py`；
7. 对故意写错函数名、列名、参数形态的 fail-open 反向自检必须失败；
8. 补 `ContentMutationService` 与 `RepresentationService` 的事务边界变异。

退出门：

- 新增 writer 不能绕过统一 commit；
- first publication、content mutation、finalize 调用方和 observer 对同一 artifact 重算出相同 managed `structure_hash`；
- 旧语义 current representation 为零，旧 generation 保留且不再 current；
- representation-only 场景 revision 前后相等；
- 业务 mutation 恰新增一个 content version/revision。

### Phase 2：Excel 行结构与全工作簿传播

**目标**：在发布双向能力前，先保证动态结构不会静默错行。

交付：

1. BP-21：managed region 剔除受控区末尾纯省略号排版行；
2. row UUID、Table ref、shared formula、merge、DV/CF、hyperlink、autoFilter、rowBreak 完整处理；
3. local shift 与 workbook propagation 的 write-set owner 分离；
4. delete 与 insert 使用同一 plan identity、operation id、artifact expected generation；
5. `undeletable_rows` 下发 API/前端，禁止静默删；
6. `deleted_row_keys` 进入 operation timeline；
7. 非零 plan 重放命中同一幂等结果；
8. 对跨 sheet 公式逐 token 验证，不以“xlsx 可打开”代替公式指向正确；
9. x2t 不重算公式时，结果状态必须是 `CALC_UNVERIFIED`，不能宣称求值正确。

退出门：

- D2/H1 managed region 无排版占位行混入；
- K11 等跨 sheet 样本插删后逐引用定位正确；
- 同一坐标无 local/global 双写；
- insert/delete 的结构覆盖矩阵无未裁决项目。

### Phase 3：首版发布与请求路径 adapter

**目标**：把“representation 已存在”推进为“请求路径能安全消费”。

交付：

1. 沿 `template → instrumentation → contract → bundle → representation` provision；
2. first publication 使用统一 managed `structure_hash`；
3. `PublishedIdentityObserver` 只从 current published representation + frozen bundle 读取；
4. `build_production_registry()` 只绑定 source-backed registration plan；
5. 请求期必须执行 `register_from_manifest(session=...)`；
6. 未注册 entry 返回可操作、封闭原因，不静默跳过；
7. capability 仅在 observer、registry、render/materialize/extract 均成功后翻为 bidirectional；
8. manifest/overlay stale 时 fail-closed，不手工填 adapter id；
9. P spec 与核心 Tasks 75/76 只保留一个执行面、两处状态同步由 milestone registry 投影。

退出门：

- 至少一个合法 projection entry 在真实请求路径完成 render-config → materialize → extract；
- 缺 representation/bundle/contract 时明确拒绝；
- registry 不依赖当前 alias 重构历史 definitions；
- capability 与真实请求结果一致。

### Phase 4：Excel pilot 真双向（D2-2 为首个 canary）

Pilot：simple checklist、D2 large JSON、H1 grouped dynamic、G7 two-level dynamic。

#### Phase 4.0 执行顺序（因 §2.4 实证固定，不可调换）

**Phase 4 必须以 D2-2 为第一个 canary**，理由是它已具备 contract 与 materialize/extract 算法，剩下的全部是宿主与 writer 接线问题；用它验证迁移路径的成本最低、暴露面最完整。

D2-2 canary 的子步骤顺序也被 gap 14/15 锁死：

1. 宿主改用统一 sync host，`GtOnlyOfficeSheet.forceSave()` 从 `/d2-sync/forcesave` 切到 `POST {USER_SYNC_PREFIX}/rooms/{room_id}/forcesave`；
2. `onlyoffice-config` 的 callback URL 改为 room-bound 四项齐全，使 callback 进入 `CallbackDeliveryService` 委派分支；
3. HTML 保存从 checklist 直接 commit 迁到 `ContentMutationService.commit(...)`；
4. `/d2-sync/*` 三个端点在 `HOST-CONSUMES-UNIFIED-PATH` 达 `ONLYOFFICE_VERIFIED` 后才删除。

**禁止反序**：179 个 entry 共用 `GtOnlyOfficeSheet`，先删 `/d2-sync/*` 会同时打断它们的 forcesave。

D2-2 canary 完成后，才允许并行推进其余三个 pilot。

每个 pilot 必跑：

1. HTML 编辑 → 保存 → OO 重开值一致；
2. OO 编辑 → forcesave/close → HTML 刷新值一致；
3. different-field 自动 merge；
4. same-field conflict → resolve → canonical rematerialize；
5. status 6/2 dedupe；
6. same-application higher sequence fold，不 self-stale；
7. 跨 participant 相同 Idempotency-Key 冲突为 409，且不泄露旧 ID；
8. quarantined incoming 不得进入 application/engine；
9. rollback 使用 opaque version UUID，不用 numeric revision 路由；
10. browser crash/no-userdata recovery；
11. authorization-first claim；
12. 错误 bundle/fence/contributor 拒绝；
13. download-only 零 application/operation/content version；
14. merged≠incoming 时 refresh/reopen；
15. 适用 pilot 插行、删行、排序、复制；
16. 两个独立用户完整关闭矩阵；
17. Playwright console 零未解释 error，network 无失败/重复提交；
18. 数据库、artifact、DOM 三边一致。

退出门：四个 pilot 每个 required scenario 都有独立 application/operation/evidence；少一项保持 `UNVERIFIABLE`。此外每个 pilot 的 `HOST-CONSUMES-UNIFIED-PATH` 必须达 `ONLYOFFICE_VERIFIED`，且 D2-2 的 `working_paper_content_application` 必须由 0 变为可稽核的 `applied` 记录。

### Phase 5：Excel 全量 entry 迁移

交付：

1. 从 manifest 动态分波，不复制 entry 常量列表；
2. 每个 entry 独立 approved contract/bundle/evidence，不跨 entry 复用；
3. 按结构 profile 分批：固定表、动态行、动态列、两级表头、跨 sheet、opaque；
4. 每批先 1 个 canary，再扩大；
5. 每批迁移后重算 writer/resolver、manifest、registry、evidence；
6. legacy route 保留到该 entry 的 post-delete evidence 通过；
7. 任何一批失败只回退本批 pointer，不回退历史 content version。

退出门：所有 Excel entry 均为 verified bidirectional 或有明确非双向裁决；无假切换。

### Phase 6：Word 稳定身份与真双向

**前置裁决**：没有稳定字段身份时不得伪造 contract。

交付：

1. 业务模板方为目标 DOCX 提供 `${token}` 或逐实例审核的稳定 SDT tag 清册；
2. 禁止 `paragraph_index`、`run_index`、中文正则和 placeholder 文本作为协议身份；
3. 每个 Word entry 独立 tagged-SDT contract、authority model、bundle；
4. candidate 只修改结构化岛，Word-only 正文、样式、批注、修订、图片保持等值；
5. `WordEntryFinalizeGate` 通过后才发布 representation；
6. 建真实 Word adapter 构造点，不能先建 additive 死代码；
7. F2-22/F2-23 先做 pilot，再处理 generic/subcode/A16/A17；
8. 行 SDT 在 OO 9.4 不可靠的形态继续 fail-closed，不做单 entry 豁免；
9. 完整执行 Phase 4 的 callback/多人/恢复矩阵以及 Word-only 保留检查。

退出门：Word pilot 真 OO 通过；其余 entry 要么 verified，要么因业务输入缺失保持显式 blocked，不能用离线 engine 推绿。

### Phase 7：Custom/opaque 项目实例闭环

交付：

1. milestone registry 中四个 SYNC gate 达到所需状态；
2. custom xlsx artifact 作为唯一业务权威，不调用 projection writer；
3. authority model 使用 approved `custom_authoritative_ooxml` / `opaque_single_onlyoffice` bundle；
4. HTML editable grid → staging CAS → current artifact → OO；
5. OO durable callback → application → current artifact → projection refresh → HTML；
6. candidate、组织模板、模板版本保持只读，不能进入实例 resolver；
7. 三入口授权、双人审批、finalize saga、rollback、retention 完成；
8. `X-HANDOFF-CONFORMANCE` 与 `X-RUNTIME-EVIDENCE` 从 PARTIAL 变成机器重算 PASS；
9. Playwright 覆盖 HTML→OO→HTML 与 OO→HTML→OO 两个完整往返。

退出门：Custom Tasks 10/14/18/19 由对应 machine gate 和真实浏览器 evidence 解锁，不靠手工说明。

### Phase 8：模板覆盖与 sidecar 联动

#### 8.1 Template override

1. 解析顺序固定为 `project > group_custom > firm_default > authoritative`；
2. DB 版本审计为真源，`current{ext}` 只是可重建投影；
3. callback 保存带 base-version CAS 与 idempotency；
4. 先 DB 后 current；失败由 reconciler 修复；
5. 备份覆盖 `backend/storage/template_overrides/`；
6. OOXML 验收改为业务属性、受保护结构与可见内容等值，不要求无意义 zip 部件字节不变；
7. 发 `TEMPLATE-OVERRIDE-CHANGED` durable event；
8. Guidance consumer ACK 后重建 inventory；
9. 不回溯修改已创建底稿。

#### 8.2 Guidance 与 Formula

1. Guidance 完成全部工作卡及 C1/C2；
2. Formula 保持 sidecar，不声称物理 workbook 双向；
3. `G-*`、`F-SHELL`、`X-*` handoff 均进入 milestone registry；
4. inventory digest、source digest 变化自动 stale；
5. UI 只展示真实 capability，不展示不可达切换。

### Phase 9：全量验收、legacy 删除与归档

顺序不可交换：

1. 重新生成 source-backed manifest、overlay、milestones；
2. 全 entry required scenario evidence 重算；
3. 运行变异、容量、故障恢复、retention、脱敏和告警；
4. writer/resolver/version domain 全部归零；
5. 生成 source-backed deletion plan，逐文件绑定 digest、owner、replacement、rollback；
6. pre-delete eligibility 全绿后才删除；
7. 删除 legacy composable/factory/endpoint/localStorage/fallback/假成功文案；
8. 删除后再次执行全 entry evidence；
9. Task 72 必须依赖 Task 74 的归零结果；
10. evidence stale=0 后归档 8 个 spec，并保留本总控为运维 runbook。

---

## 9. 验证与证据矩阵

### 9.1 五层验证

| 层 | 目的 | 最低证据 |
|---|---|---|
| 静态/结构 | 唯一 owner、调用链、DAG、禁止路径 | AST/结构 guard，不能只 grep 字符串 |
| 单元/PBT | identity、merge、CAS、状态边、plan 纯函数 | targeted pytest、Hypothesis、变异 RED |
| PostgreSQL 集成 | FK、锁、唯一约束、单事务、幂等 | 真库 session；测试后完整复原 |
| OnlyOffice 9.4 | callback、forcesave、SDT/Excel identity、多人 room | 真实容器、真实文档、artifact/timeline |
| Playwright | 用户可见切换、刷新、冲突、恢复、DOM | 两个独立 context、network/console、截图/trace |

不得用低层证据替代高层：单元测试通过不能替代 OnlyOffice，OnlyOffice callback 成功不能替代 DOM 刷新。

### 9.2 每个 scenario 的 evidence bundle

每个 scenario 至少记录：

```text
run_id
entry_id / wp_id / project_id（证据中脱敏）
source_commit
manifest_digest
content_version_id / business_revision
representation_id / generation / artifact_sha256
bundle_id / bundle_digest / adapter_build_digest
structure_hash / identity_inventory_sha256
room_id / generation
request_id / delivery_id / application_id / operation_id
base/current/incoming/result artifact identities
required_scenario_id / result / landed
browser trace / screenshot / console / network summary
DB timeline snapshot
cleanup/restoration result
```

不得把 token、callback URL、Authorization、用户 PII 写入 evidence。

### 9.3 变异四态

所有关键 guard 的变异结果必须区分：

- `RED`：预期测试因目标缺陷打红；
- `GREEN`：守卫缺陷；
- `ANCHOR-MISS`：变异脚本未命中唯一锚点；
- `WRONG-TEST`：打红了非预期测试。

只看退出码不得算通过。变异完成后验证目标文件 hash 还原、无 `.mutbak` 残留。

### 9.4 浏览器最终验收

使用项目标准启动入口 `start-dev.bat`，真实访问前端 3030、后端 9980、OnlyOffice 8080。最终验收至少覆盖：

1. 结构化 HTML 修改金额、文本、枚举和动态行；
2. 打开 OO 后看到相同值与结构；
3. OO 修改后 HTML 无刷新丢值；
4. 同字段冲突显示三值与来源，可明确选择；
5. 不同字段自动合并；
6. 双人同时编辑，contributors 正确；
7. 浏览器崩溃后 recovery 可见、可恢复；
8. rollback 后两侧一致；
9. 关闭重开仍从 canonical published representation 读取；
10. console 无未解释错误，network 无重复 business commit。

### 9.5 明确不构成双向完成证据的项

以下任何一项、以及它们的组合，都**不得**用来把 entry 判为 `bidirectional_verified`：

1. `/api/workpapers/{wp_id}/d2-sync/status` 返回 `bidirectional: true`（该值是源码字面量）；
2. `/d2-sync/push-to-excel` 或 `/d2-sync/pull-from-excel` 返回 `ok: true`；
3. `/d2-sync/forcesave` 返回 durable（它只证明磁盘文件变了，不证明业务应用成立）；
4. `working_paper_oo_content_revision` 增长（这是 doc_key 轮转用的第二版本域）；
5. `working_paper.file_version` 增长（legacy callback 自增，独立于业务版本域）；
6. legacy `sheets/{sheet}/onlyoffice-callback` 返回 `error: 0`；
7. manifest 的 `capability`、`migration_state`、`adapter_id`、`review_status` 字段值；
8. 首版 representation 已存在，或 `working_paper_sync_entry_state` 有 current 指针；
9. HTML→HTML 的 persistence roundtrip 测试（如 `d2-maintainability-roundtrip.spec.ts`），它不含 OO；
10. contract/materialize/extract 的离线单元测试与 pilot 测试。

判定必须落到 §6.4 的 8 项谓词，其中第 4–6 项要求真实数据库记录。

### 9.6 D2-2 的真实 Playwright 条件

D2-2 的浏览器 evidence 只有同时满足以下条件才可采信：

1. 使用 `start-dev.bat` 启动的真实前后端与 OnlyOffice 容器；
2. 使用专用测试项目与测试底稿实例，不在真实客户项目上写入；
3. 记录进入 D2-2 视图后的完整 network 列表，并断言出现 `USER_SYNC_PREFIX` 请求、且不出现 `/d2-sync/*`；
4. 抓取 `editorConfig.callbackUrl` 的 query key 集合，断言含 room-bound 四项（**输出时不得包含 token、JWT、route credential 的值**）；
5. 在 OO 中真实改值 → forcesave → 断言数据库新增 `working_paper_content_application` 且 `state='applied'`；
6. 回到 HTML 断言 DOM 显示该值；
7. 记录 `content_revision` 前后差值恰为 1；
8. 测试结束复原测试数据，并核查数据本身而不是脚本 exit code。

当前状态：条件 3–7 全部未满足。本轮已完成的只读观察可作为**反例基线 evidence**，不能作为通过 evidence。

---

## 10. 风险与安全边界

### 10.1 数据库与文件安全

- 新 schema 只通过 `backend/migrations/V*.sql`，编号实施前重新扫描；
- migration 必须幂等并有配对回滚策略；
- repository flush-only，事务由 coordinator/service owner 持有；
- 文件先 immutable publish，DB 失败只产生 orphan，不切 current；
- incoming durable 与 quarantined 不可互转；
- candidate 永不进入 current resolver、room 或 evidence；
- 不以物理删除处理 tombstone/法律保留对象；
- 实测脚本先 dry-run、逐 entry 独立事务、最后核查数据而非只看 exit code。

### 10.2 授权与信息泄露

- authorization-before-cache/idempotency；
- 404/403 阶段与时序不得泄露项目、entry、operation 是否存在；
- route 指标不带 participant；
- callback URL、JWT、userdata 全部脱敏；
- wrong project/wp/entry/bundle/generation 必须 fail-closed；
- 禁止 `except Exception` 降级为“本项目无此数据”。

### 10.3 并发实施安全

- 每个共享文件同一时刻只有一个 lane owner；
- 共享 JSON/CI 文件只做归因型增量，不做全局等值回退；
- 发现 active spec mtime 秒/分钟级变化时暂停接手；
- 不清理其他会话的 `tmp_*`、`_wip_*`；
- 正式产物必须核查 git 跟踪状态，防止干净 checkout 缺文件。

---

## 11. 关键裁决与待业务输入

| ID | 裁决/阻塞 | 当前决定 | 解除条件 |
|---|---|---|---|
| DEC-01 | business revision owner | 仅 `ContentMutationService` | 永久架构约束 |
| DEC-02 | representation-only owner | 仅 `RepresentationService` | 永久架构约束 |
| DEC-03 | `structure_hash` 双语义 | 计算真源已统一为 `publish_time_structure_hash.py`；但现有 rehash apply 仍经业务 commit 推进 revision，暂不得用于迁移 | 改为 `RepresentationService` 新 generation、revision 不变，随后清零旧语义 current 并完成 observer 复验 |
| DEC-04 | row shift 与 workbook propagation 双 owner | local 只管目标 sheet；workbook 只扩展外部引用；coordinator 防双写 | Phase 2 write-set guard 通过 |
| DEC-05 | Formula 是否写物理 workbook | 当前永久 sidecar | 另立物理公式双向 spec 后才可改变 |
| BP-21 | managed region 末尾省略号排版行 | 从业务区间剔除，不推成披露数据行 | Phase 2 真模板守卫通过 |
| WORD-ID | DOCX 无稳定字段身份 | 禁止用中文正则/绝对索引伪造 contract | 模板方提供 token 或逐实例审核 tag 清册 |
| TEMPLATE-ORG | `template_admin`/Organization/tenant 默认值欠账 | 不以 `tenant_id='default'` 伪装组织隔离完成 | 平台组织模型和 enum 正式迁移 |
| DEC-06 | D2-2 的双向状态 | 裁为 `REQUEST_PATH_LEGACY`：算法构件齐备，宿主走专用旁路与 legacy callback，`working_paper_content_application`=0 | `HOST-CONSUMES-UNIFIED-PATH` 8 项谓词全 pass 且真实 OO 往返 evidence 落地 |
| DEC-07 | `capability` 字段能否作为完成依据 | 不能。manifest 的 capability/migration_state/adapter_id 只表示登记意图，不表示宿主行为 | 永久约束；完成依据只认 §6.4 谓词 |
| DEC-08 | `/d2-sync/*` 删除时机 | 只能在宿主切到统一路径且该门达 `ONLYOFFICE_VERIFIED` 之后 | 179 个 entry 共用的 `GtOnlyOfficeSheet.forceSave()` 已改指统一 forcesave 端点 |
| DEC-09 | 两个版本域并存 | `working_paper_oo_content_revision` 仅可用于 doc_key 轮转，禁止作为业务版本或正确性依据 | 迁移完成后由业务 revision 单独承担，届时评估是否删除该列 |
| DEC-10 | D2 大表 materialize 同步性能 | 🔴 **实测阻塞**：D2 的 28431 字段 / 729 行 projection 走统一 materialize **>300s 且阻塞 worker**。离线剖析 `push_html_to_excel` 呈**超线性（≈O(n²)）**：10行6.7s / 50行8.8s / 200行15.9s / 729行59.3s（每行成本 200→729 翻倍）。`ContentMutationService._stage_and_verify` 每次 materialize 解析工作簿 ≥3 次（materialize 内 extract substrate + 输出 extract 做 roundtrip + unmanaged before/after）。这是**可修的低效**（缓存 substrate extract / extract 改 O(n) / materialize 异步化），非固有成本。**在优化前 D2 真实 OO 往返不可完成，前端宿主也不得迁**（否则「在线编辑」>5min 并 wedge worker，比 legacy 更差）。store-projection 端点已交付并真实 HTTP 验证（G4-0c evidence）。 | materialize 对 D2 大表在可接受时间内完成（新增性能 spec：缓存/流式/异步） |

---

## 12. 首批可执行工作包

按以下顺序开工，完成一项立即更新 producer spec 与 milestone evidence：

1. **G0-1**：新增 program milestone registry、generator、guard；
2. **G0-2**：修正 8 个 spec 当前任务分母和 discovery-only 状态（[执行卡与 evidence](../../.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-2-denominator-discovery-state/README.md)）；
3. **G0-3**：补核心 Task 72 → Task 74 依赖，并将 Task 72 独立后移到 Wave 8 以满足“更早 Wave 或同 Wave 更小任务号”规则（[执行卡与 evidence](../../.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/g0-3-archive-writer-debt-dependency/README.md)）；
4. **G1-1**：枚举并锁死所有 `structure_hash` 写入点，统一委托现有 `publish_time_structure_hash.py`；
5. **G1-2**：只读识别旧 representation；修正 rehash apply 为 `RepresentationService` 新 generation 且 revision 不变，再执行迁移；
6. **G1-3**：对迁移后的 current generation 执行 observer + registry 请求路径复验；
7. **G2-1**：BP-21 落地与真模板守卫；
8. **G2-2**：local/workbook mutation write-set owner 与重复坐标 guard；
9. **G2-3**：delete 结构覆盖矩阵、CAS、operation timeline；
10. **G3-1**：请求期 registry 真注册与逐 entry render/materialize/extract；
11. **G0-4**：新增 `HOST-CONSUMES-UNIFIED-PATH` 的 8 项机器谓词与逐 entry 投影，并把 D2-2 当前值固化为反例基线（预期 `REQUEST_PATH_LEGACY`）；
12. **G4-0a**：`GtOnlyOfficeSheet.forceSave()` 从 `/d2-sync/forcesave` 切到统一 forcesave 端点（影响面 179 个 entry，必须先于任何删除动作）；
13. **G4-0b**：D2-2 的 `onlyoffice-config` 改发 room-bound callback URL，使 callback 进入 `CallbackDeliveryService`；
14. **G4-0c**：D2-2 的 HTML 保存从 checklist 直接 commit 迁入 `ContentMutationService.commit(...)`，并消除 `_write_store_rows()` 与 narratives 的双 commit 窗口；
15. **G4-0d**：D2-2 真实 OO 往返取证，按 §9.6 八条执行；通过后删除 `/d2-sync/*` 与专用 bridge；
16. **G4-1**：其余三类 Excel pilot 真实 OO + Playwright；
17. **G5-1**：按 manifest profile 分批迁移 Excel 全量 entry；
18. **G6-1**：取得 Word 稳定字段业务输入后执行 F2 pilot；
19. **G7-1**：四个 SYNC gate 解锁 Custom 全往返；
20. **G8-1**：template override CAS/reconciler/event 与 Guidance ACK；
21. **G9-1**：全量 evidence、writer gate 归零、legacy 删除、post-delete 复验。

每个工作包必须具备：owner、修改文件清单、输入 gate、输出 milestone、targeted tests、真实场景、回滚方案和 evidence 路径。缺任一项不得进入 `in_progress`。

---

## 13. 代码与证据索引

### 13.1 核心生产入口

- `backend/app/services/workpaper_sync/__init__.py`
- `backend/app/routers/wp_sync_router.py`
- `backend/app/services/workpaper_sync/content_mutation.py`
- `backend/app/services/workpaper_sync/representations.py`
- `backend/app/services/workpaper_sync/artifacts.py`
- `backend/app/services/workpaper_sync/canonical_paths.py`
- `backend/app/services/workpaper_sync/resolution.py`
- `backend/app/services/workpaper_sync/published_identity_observer.py`
- `backend/app/services/workpaper_sync/publish_time_structure_hash.py`
- `backend/app/services/workpaper_sync/adapters/registry.py`
- `backend/app/services/workpaper_sync/adapters/base.py`
- `backend/app/services/workpaper_sync/adapters/excel.py`
- `backend/app/services/workpaper_sync/materialize_coordinator.py`
- `backend/app/services/workpaper_sync/oo_to_html.py`
- `backend/app/services/workpaper_sync/rooms.py`
- `backend/app/services/workpaper_sync/callback_route.py`
- `backend/app/services/workpaper_sync/callback_download.py`
- `backend/app/services/workpaper_sync/callback_delivery.py`
- `backend/app/services/workpaper_sync/request_application.py`
- `backend/app/services/workpaper_sync/command_service.py`
- `backend/app/services/workpaper_sync/repository.py`
- `backend/app/services/workpaper_sync/models.py`
- `backend/app/models/workpaper_sync_models.py`
- `backend/migrations/V151__workpaper_sync_content_application_bundle_scope.sql`

### 13.2 Published 与 Excel 结构

- `backend/app/services/workpaper_sync/projection_lane_registry.py`
- `backend/app/services/workpaper_sync/projection_first_publication.py`
- `backend/app/services/workpaper_sync/projection_provisioning.py`
- `backend/app/services/workpaper_sync/projection_target_resolution.py`
- `backend/app/services/workpaper_sync/opaque_entry_gate.py`
- `backend/app/services/workpaper_sync/excel_row_shift.py`
- `backend/app/services/workpaper_sync/excel_workbook_row_change.py`
- `backend/app/services/workpaper_sync/excel_materialize.py`
- `backend/app/services/workpaper_sync/excel_extract.py`
- `backend/scripts/check/check_projection_lane_adjudication.py`
- `backend/scripts/check/check_excel_row_insertion_readiness.py`
- `backend/scripts/fix/fix_projection_representation_rehash.py`
- `backend/tests/workpaper_sync/test_projection_structure_hash_semantics.py`
- `backend/scripts/gen/generate_row_change_reachability.py`
- `backend/data/workpaper_row_change_reachability.json`

### 13.3 模板、Guidance、Formula、Custom

- `backend/app/services/wp_template_override.py`
- `backend/app/services/wp_template_finder.py`
- `backend/app/routers/wp_template_override_router.py`
- `backend/app/routers/wp_onlyoffice_router.py`
- `audit-platform/frontend/src/components/template-library/WpTemplateDetail.vue`
- `backend/app/services/guidance_gid.py`
- `audit-platform/frontend/src/shell/guidance/guidanceRailAdapter.ts`
- `backend/app/services/user_formula_v2.py`
- `audit-platform/frontend/src/shell/formula/`
- `backend/app/services/custom_template_ingestion/`
- `backend/app/routers/custom_template_ingestion.py`

### 13.4 D2-2 canary 与 legacy 旁路（§2.4 的取证位置）

- `backend/app/routers/d2_sync_router.py`：`/d2-sync/status|push-to-excel|forcesave|pull-from-excel`、`_load_context()`、`_bump_oo_revision()`、`_assert_not_stale()`
- `backend/app/services/workpaper_sync/d2_bidirectional_bridge.py`
- `backend/app/services/workpaper_sync/pilot_d2_large_json.py`
- `backend/data/workpaper_sync_contracts/d2.receivable_detail.json`
- `backend/app/routers/checklist_responses.py`：`batch_save_checklist_responses()`
- `backend/app/routers/wp_onlyoffice_router.py`：`get_sheet_onlyoffice_config()`、`_has_room_bound_callback_query()`、`_delegate_room_bound_callback()`、`post_sheet_onlyoffice_callback()`
- `backend/app/services/onlyoffice_room_identity.py`：`sheet_entry_id()`、`bump_oo_content_revision()`
- `backend/app/data/wp_code_overrides.json`
- `audit-platform/frontend/src/components/workpaper/GtD2AccountsReceivable.vue`
- `audit-platform/frontend/src/components/workpaper/GtOnlyOfficeSheet.vue`：`forceSave()`
- `audit-platform/frontend/src/components/workpaper/sync/useD2SyncBridge.ts`
- `audit-platform/frontend/src/components/workpaper/composables/useD2FormData.ts`
- `audit-platform/frontend/src/components/workpaper/sync/workpaperSyncEditorHostRuntime.ts`：统一宿主的拒绝挂载判据
- `backend/tests/test_d2_sync_durable_gate.py`：仅覆盖 fingerprint/stale 与端点存在
- `audit-platform/frontend/e2e/d2-maintainability-roundtrip.spec.ts`：HTML→HTML，不含 OO

### 13.5 历史与子议题文档

- `docs/operations/oo-html-bidirectional-writeback-5-lane-assignment.md`：历史实证日志
- `docs/operations/excel-row-insertion-mutation-handoff.md`：结构插行交接
- `docs/operations/bp-21-managed-region-typography-row-handoff.md`：BP-21 交接
- `docs/README.md`：文档分类规则

---

## 14. 维护规则

1. 本文只维护跨 spec 架构裁决、关键路径、milestone 和总体验收；
2. 单个任务的实现细节回写对应 spec，不复制到本文；
3. 调查过程和长日志写入 `evidence/`，本文只链接最终事实；
4. 当前数字必须带日期和取数方式；
5. 任何 milestone 变化必须由 generator/evidence 推动；
6. 生产事实与本文冲突时，本文立即标 stale，不得改机器事实迎合本文；
7. 全局 closure 后，本文转为运行维护与故障恢复 runbook，8 个 spec 按功能归档。

---

## 15. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-09 | 建立 8-spec 双向回写实施总控；取代旧五泳道文档的动态状态面；裁决 canonical owner、`structure_hash` 单一语义、结构 mutation owner、milestone registry、九阶段实施与真实 OO/Playwright 验收门。 |
| 2026-09-09 | 校验时确认 BP-30 统一计算器和生产调用已落地；同时发现 rehash apply 仍调用 `publish_first_generation()` 并推进 `new_revision`，故将其登记为 Phase 1 P0 阻塞：改为 `RepresentationService` 新 generation 且 revision 不变后才能迁移。 |
| 2026-09-10 | G4 canary 推进：交付 store-projection 只读端点（`GET .../sync/entries/{entry}/store-projection`，单一真源 `build_store_projection`，前端不重造 39 列映射），真实 HTTP 验证 D2 得 28431 字段 / 729 行 projection；`test_task28` 100 passed。真库只读纠正：D2/G7/H1 三个 entry 均已有 current published representation + approved bundle，`register_from_manifest` 全注册、`assert_bidirectional_ready` 全 PASS（推翻「D2 无供给必 422」的过时 docstring 推断）。新增 DEC-10：实测 D2 大表 materialize 同步 >300s 且超线性阻塞 worker，是 D2 真实 OO 往返与前端宿主迁移的前置阻塞，需专门性能优化。运维事件已如实记录并恢复（详见 evidence/g4-0c-store-projection-and-materialize-perf.md）。 |
| 2026-09-09 | 以 D2-2 为参照做落地核验（代码 + 只读数据库 + 浏览器只读观察三边）。新增 §2.4 反例基线（五层身份、实际请求路径、DB 基线、15 项 gap、平台级 forcesave 泄漏、可复用资产与替换清单）；将 §1.3 补入宿主条件，§3.1/§4.1/§4.2 明确为 target invariant 并登记当前违反项；新增 §6.4 `HOST-CONSUMES-UNIFIED-PATH` 八项谓词与 `REQUEST_PATH_LEGACY` 状态；Phase 4 改为 D2-2 首个 canary 并固定四步顺序；新增 §9.5 不构成证据清单与 §9.6 D2-2 真实 Playwright 条件；新增 DEC-06～DEC-09；首批工作包插入 G0-4、G4-0a～G4-0d 并顺延编号；新增 §13.4 取证位置索引。结论：总控可落地，但 D2-2 必须从「已完成样板」改记为「第一迁移 canary + 反例基线」。 |
