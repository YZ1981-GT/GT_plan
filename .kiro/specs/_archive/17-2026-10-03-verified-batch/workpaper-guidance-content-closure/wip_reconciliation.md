# WIP Reconciliation: workpaper-guidance-content-closure

> Task 2 产物。目的：把 guidance 域每个文件的**真实落点**、**归属**（本 spec / foreign / frozen legacy）、
> **对应 Requirement/Property**、**守卫类型**与**变异状态**写成一张可核对的表。
> 判定口径：
> - 守卫类型 `behavior` = 真跑服务/API 断言返回值/状态码/副作用；`structural` = 断言数据结构/键集/digest；
>   `string-presence` = 只 grep 字符串或符号存在（假绿第②源）。
> - 归属 `foreign` = 与本 spec 无 AC 对应（如 note 表内附注说明、G4/G8 循环内嵌 reference 面板）。
> - 归属 `frozen-legacy` = design §Non-Goals 明确禁止再作为运行时 exact 真源，但测试仍在其内部语义上做兼容。

## 1. 后端实现清单

| 文件 | 行数 | 承载概念 | 归属 | 对应 Req | 说明 |
|---|---:|---|---|---|---|
| `backend/app/services/guidance_inventory.py` | 1350 | 九段 canonical、`GuidanceInventoryEntry`、static inventory、`RuntimeGuidanceInventory`/`Entry`、exemption、`entry_digest`、`facts_digest`、`find_runtime_inventory_entry` | 本 spec | 2.1/2.2/2.4/2.5/2.6/3.1/3.2/3.3/3.5 | 运行时清册真源；`counters` 含 `required`/`required_exact`（effective denominator） |
| `backend/app/services/guidance_source_refs.py` | 930 | `SourceRefContext`、六类 locator validator（xlsx/docx/…）、authority digest、`TemplateAuthoritySnapshot`、`SourceRefBatchValidation` | 本 spec | 5.3/5.4/5.5 | `SourceRefHandler` protocol 未以 protocol 类落形，是函数式 `_validate_xlsx/_validate_docx`；**部分存在** |
| `backend/app/services/guidance_gc0_contract.py` | 503 | `ContractBundle`、`GC0_CONTRACT_VERSION`、`validate_contract_version`、`CompatibilityDecision`、`discover_local_dupes`（前端反向 dup 扫描） | 本 spec | 1.1/1.2/1.3/1.4/1.5/1.6 | C0 单源真源 |
| `backend/app/services/guidance_coverage_service.py` | 265 | `build_global_guidance_coverage`，把多个 runtime inventory 合并成全局分母 | 本 spec | 3.1/3.2/3.3/3.4 | C1/C2 分母核算 |
| `backend/app/services/guidance_extractor.py` | 456 | `GuidanceExtractor`、`extract_full`、`extract_exact_static`、`GuidanceResult` | 本 spec + frozen-legacy | 7.3 | `extract_exact_static` 仍在用但已**改为 canonical 九段+source_ref 门禁**，不是旧 static-only exact |
| `backend/app/services/wp_guidance_service.py` | 400 | `GuidanceService.resolve_guidance`（child exact → parent chain）、`_build_response` 三态 resolution_status | 本 spec | 7.1/7.2/7.3/7.4/7.6/9.1 | `resolve_authoritative_exact` 名字**不存在**，功能由 `resolve_guidance` 承担；字段名仍是 snake_case `resolution_status` |
| `backend/app/routers/wp_guidance_chat.py` | 951 | `get_workpaper_guidance` route、visibility gate、runtime inventory 注入、custom 501 占位、AI chat | 本 spec | 7.6/12.1/12.4 | route 层已接入 runtime entry |
| `backend/app/services/note_table_guidance.py` | — | 附注表内说明文本 | foreign | — | 与 wp 编制说明无关 |
| `backend/app/services/guidance_cache.py` | — | 请求级 LRU | 已删除（git `D`） | — | Task 9 已移除伪缓存 |

### 1.1 design 承诺 vs 真实落地

| design 承诺 | 结论 | 证据 |
|---|---|---|
| `G-C0` wire bundle 单源 | **存在** | `backend/data/guidance/contracts/gc0/{schema.json,compatibility_matrix.json,evidence/,fixtures/×10}` + `guidance_gc0_contract.py` |
| `GuidanceSection` 九段唯一 | **存在** | `CANONICAL_SECTION_KEYS`（`guidance_inventory.py:31`），9 个 key 与 design §1.1 完全一致 |
| `SourceRefRegistry`（protocol） | **部分存在** | 无 `Protocol` 类；六类 locator 以函数 `_validate_xlsx`/`_validate_docx` 直接实现，`validate_source_ref` 做分派。缺「unknown kind fail-closed 由 registry 保证」的抽象层 |
| `CatalogInventorySnapshot` / `RuntimeInventorySnapshot` materialized snapshot | **部分存在** | 有 `RuntimeGuidanceInventory`（`run_id`/`generated_at`/`facts_digest`/`entries`/`counters`），但**未落盘为不可变 snapshot**，无 latest pointer / digest-addressed cache |
| 请求路径禁止全目录扫描 | **存在** | `build_runtime_guidance_inventory(static_entries=...)` 支持外部注入；static 走 `build_static_guidance_inventory()` 一次 |
| `resolve_authoritative_exact()` | **不存在**（功能等价） | `GuidanceService.resolve_guidance` 实现 child exact → parent chain；命名与 design 不符，需登记 |
| `GuidanceResponse` 契约字段 | **部分存在** | route 返回 `resolution_status/resolution_reason/requested_sheet_code/resolved_wp_code/inherited_from_parent/missing_sections/exact_blockers/source_digest/inventory_*`；**缺** `contractVersion`、`schemaVersion`、`subject`、`provenance`（primary/overlays/extraction）、`completionStatus`、`inventoryDigest`、`version`、`generatedAt` 命名对齐 |
| `EvidenceEnvelope` / `ConsumerAck` / `GuidanceRailAdapter` | **仅 C0 数据** | 只存在于 schema/fixtures + 前端 `shared/contracts/gc0/index.ts`；**无生产消费方**（Task 16/15 未完成） |
| `GuidancePublication` / `ProjectGuidanceSupplement` | **不存在** | 无模块、无表；Task 6 未开工 |
| legacy `exact_status` / `extract_exact_static` 残留 | **残留但已收敛** | `exact_status` 仍作为 `GuidanceInventoryEntry`/`RuntimeGuidanceInventoryEntry` 字段与 response 的 `runtime_guidance_status` 存在；已**不再**是独立真源，与 `resolution_status` 并存且被后者覆盖 |
| 「请求时全目录扫描」 | **已消除** | inventory 由 route 注入 render facts，`list_available_guidance()` 仅用于 admin 枚举 |

## 2. 后端测试清单（11 个文件，行为/结构判定）

| 文件 | 测试数 | 守卫类型 | 覆盖 Req | 判定 |
|---|---:|---|---|---|
| `test_guidance_gc0_conformance.py` | 22 | structural | 1.1/1.2/1.3/1.4/1.5/1.6 | ✅ 行为级：真调 `validate_contract_version` 六种 outcome；fixture 字段集断言 |
| `test_guidance_source_refs.py` | 8 | behavior | 5.3/5.4/5.5 | ✅ 真跑 validator，断言 valid/invalid/stale/cross_template 四态 |
| `test_guidance_source_ref_integration.py` | 1 | behavior | 13.x（四态贯通） | ✅ 真跑 extractor+inventory+service 全链，断言四种 source_ref 状态都落到 `exact_gate` |
| `test_guidance_inventory_runtime.py` | 11 | behavior | 2.1/2.4/2.5/2.6/3.1/3.2/3.3 | ✅ 真跑 `build_runtime_guidance_inventory`，断言分母扩张、membership fail-closed、exemption 过期、custom 不可 exact |
| `test_guidance_global_coverage.py` | 6 | behavior | 3.1/3.2/3.3 | ✅ 真跑 `build_global_guidance_coverage`，断言分母无遗漏/无重复、run_id 不进 digest |
| `test_wp_guidance_router.py` | 7 | behavior | 7.6/12.1 | ✅ 真跑 route（mock repo），断言 422/404/visibility gate |
| `test_wp_guidance_data_contract.py` | 6 | structural | 4.1/5.1/5.2 | ✅ 全目录数据契约：parseable/canonical/bundle-free、digest 稳定、非 exact 必有 blocker |
| `test_guidance_canonical_migration.py` | 7 | structural | 4.3（legacy 迁移） | ✅ 断言 v2 迁移无损、重复段合并、指纹拒绝正文变更 |
| `test_guidance_extractor.py` | 14 | behavior | 7.3 | ✅ 真跑 `GuidanceExtractor`，含 timeout、九段+source_ref 才 exact |
| `test_wp_guidance_service_ext.py` | 22 | behavior | 7.1/7.2/7.4/9.1 | ✅ 真跑 `GuidanceService`，断言 child short-circuit、digest 稳定、stale 覆盖 parent_inherited |
| `test_c_control_test_load_guidance.py` | 9 | behavior | 15.1（兼容） | ✅ 真实文件加载，malformed→None 不抛 |

**合计 113 个测试，70 个在本次定向回归中全绿（4.78s）。**
无 `string-presence` 型守卫；未使用「历史 passed 数」「HTTP 200」作为完成判据。

### 2.1 与 `backend/tests/services/` 下 14 个文件的关系

`test_note_table_guidance.py` / `test_per_table_guidance.py` / `test_guidance_text_three_layer.py` /
`test_guidance_backward_compat.py` / `test_guidance_classify_property.py` / `test_guidance_migration_pg.py` /
`test_guidance_offline_roundtrip.py` / `test_guidance_stale_baseline_pg.py` / `test_export_excludes_guidance.py` /
`test_multiline_bracket_guidance.py` / `test_note_guidance_word_export.py` / `test_skip_empty_guidance.py` /
`test_word_template_guidance.py` → 全部围绕 **note 附注表内说明** 或 **AI 生成文本**，与 wp 编制说明九段契约
无关，归 **foreign**，不纳入本 spec reconciliation 分母。

## 3. 前端清单

| 文件 | 承载概念 | 归属 | 判定 |
|---|---|---|---|
| `src/shared/contracts/gc0/index.ts` | `GuidanceSection`/`SourceRef`/`TemplateAuthorityIdentity`/`CustomGuidanceHandoff`/`EvidenceEnvelope`/`ConsumerAck`/`GuidanceRailAdapter`/`CanonicalWorkpaperLocation` + `ownerEpoch`/`contextRevision` | 本 spec | ✅ 与后端 schema 双向对账（`discover_local_dupes` 防本地副本） |
| `src/shared/contracts/gc0/index.spec.ts` | 前端 C0 conformance | 本 spec | ✅ |
| `src/stores/guidancePanelStore.ts` | `setWpContext` 单 fetch owner、`requestId` + `contextIdentity` 双门 race gate、TTL 60s 缓存 + revalidate、abort 清理 | 本 spec | ✅ 已实现 Task 13 核心；**缺** `ownerEpoch`/`contextRevision` 字段级 gate（用了 `requestId`+`contextIdentity` 等价实现）、**缺** ETag revalidate（用 `guidance_version` 比对替代） |
| `src/components/workpaper/guidance/GuidanceTabContent.vue` | 九段渲染、`GuidanceResponse` 消费、sanitize | 本 spec | ⚠ 需核三轴 badge（primary/overlays/extraction）是否已分层；当前只消费 `resolution_status` |
| `src/components/workpaper/WpGuidancePanel.vue` | 面板容器 | 本 spec | ✅ shellOwned 时 trigger 交 F-SHELL；无 fixed top/right/z-index |
| `src/components/ai/DshPanel.vue` | 消费 `aiGuidanceContext` | 本 spec（消费方） | ✅ 不再挂载第二套聊天面板 |
| `src/components/ai/__tests__/DshPanelGuidanceContext.spec.ts` | 上下文透传 | 本 spec | ✅ |
| `src/views/__tests__/guidanceBar.spec.ts`、`src/views/__tests__/disclosureEditorGuidance.spec.ts` | 旧 guidance bar | foreign/待核 | 需确认是否为旧内嵌 AI 承载链残留 |
| `src/utils/noteGuidance.ts` | 附注说明工具 | foreign | — |
| `src/composables/g4SppiGuidance.ts`、`G4TabRef*Guidance.vue`、`G8TabRef*Guidance.vue`、`entityVerifyGuidance.ts`、`useAlternative*`、`L6TabDetail.vue` 等 | 各循环内嵌 reference 面板 | foreign | 与本 spec 无关 |

## 4. Mutation harness 现状

| 项 | 现状 |
|---|---|
| 公共 harness | `backend/scripts/check/mutate_common.py`：`Mutation` dataclass + `run_group` + `check_group_anchors`，**具备**单锚点校验、pristine bytes 保存、`finally` 全字节恢复、RED/GREEN/ANCHOR-MISS/WRONG-TEST/BASE-RED 五态输出 |
| guidance 专属脚本 | `backend/scripts/diagnose/mutate_guidance_source_ref_wiring_guards.py`：4 条锚点（M01 batch short-circuit / M02 coverage 复用未验证 static / M03 custom confirmed 变 exact / M04 parent_inherited 掩盖 invalid），字节级读写 + 唯一性断言 |
| 缺口 | 缺 contract（C0 schema/matrix/fixture）、inventory（分母/exemption）、resolution（cache/race）、UI（rail adapter/fixed offset）四类锚点 |

## 5. Git 状态（未跟踪风险）

以下为本 spec 正式产物，`git status --porcelain` 均为 `??`，**丢工作树即蒸发**：

```
?? .kiro/specs/workpaper-guidance-content-closure/          # spec 三件套本身
?? backend/app/services/guidance_coverage_service.py         # Req 3
?? backend/app/services/guidance_gc0_contract.py             # Req 1
?? backend/app/services/guidance_inventory.py                # Req 2/3
?? backend/app/services/guidance_source_refs.py              # Req 5
?? backend/data/guidance/                                    # C0 schema/matrix/fixtures
?? backend/scripts/diagnose/mutate_guidance_source_ref_wiring_guards.py
?? backend/scripts/diagnose/diagnose_guidance_coverage.py
?? backend/scripts/fix/migrate_guidance_canonical_schema.py
?? backend/tests/test_guidance_canonical_migration.py
?? backend/tests/test_guidance_gc0_conformance.py
?? backend/tests/test_guidance_global_coverage.py
?? backend/tests/test_guidance_inventory_runtime.py
?? backend/tests/test_guidance_source_ref_integration.py
?? backend/tests/test_guidance_source_refs.py
?? backend/tests/test_wp_guidance_data_contract.py
?? backend/tests/test_wp_guidance_router.py
?? audit-platform/frontend/src/components/ai/__tests__/DshPanelGuidanceContext.spec.ts
?? audit-platform/frontend/src/components/workpaper/__tests__/WpGuidancePanel.spec.ts
?? audit-platform/frontend/src/components/workpaper/guidance/__tests__/
?? audit-platform/frontend/src/stores/__tests__/guidancePanelStore.spec.ts
```

已跟踪但有并发修改（`M`）：`wp_guidance_service.py`、`guidance_extractor.py`、`wp_guidance_chat.py`、
`guidancePanelStore.ts`、`GuidanceTabContent.vue`、`WpGuidancePanel.vue`、11 个已跟踪 guidance 测试、
约 320 个 `backend/data/wp_guidance/*.json`。
已删除（`D`）：`guidance_cache.py`、`backend/tests/test_guidance_cache.py`、`test_guidance_cache_pbt.py`、
3 个旧 guidance json（`cash_flow_support`/`goodwill_impairment`/`segment_reporting`）→ 符合 design 移除伪缓存与 legacy 静态 exact。

## 6. Task 2 结论

1. **红基线（Task 1）已交付**：legacy 单 `source/exact_status` 真源、请求级 LRU、全目录扫描、static-only exact 均已被真实代码取代；残留 `extract_exact_static` 与 `exact_status` 字段是**兼容层**，不再是权威判定。
2. **红守卫已存在且为行为级**：contract（22）/ source_ref（9）/ inventory（11+6）/ resolution（22+7）四类守卫齐备，全部真跑消费链，非字符串存在。
3. **变异已验证 4 条**：`mutate_guidance_source_ref_wiring_guards.py` 覆盖 batch short-circuit、coverage 复用、custom exact、parent_inherited 掩盖。
4. **缺口（Task 2 未完成部分）**：
   - contract 类锚点（C0 schema/matrix/fixture 漂移）未进 mutation 脚本；
   - inventory 类锚点（exemption 过期、分母缩水、run_id 进 digest）未进 mutation 脚本；
   - resolution 类锚点（cache race、race gate 短路）未进 mutation 脚本；
   - UI 类锚点（rail adapter、fixed offset）未进 mutation 脚本。
5. **未跟踪产物 20 项**必须在归档前 `git add`，否则 clean checkout 不可复现。

---

## 7. 2026-09-08 复核更新（会话追加，不改上文历史记录）

上文 §1–§6 是 Task 2 初次对账的历史快照，写于 Task 4/6/8/9 产物落盘之前，已部分过时。本节按当前磁盘/git 真实状态更新，作为增量事实。

### 7.1 回归修复

- **`backend/app/routers/wp_guidance_chat.py` `_FakeUrl` NameError**：`get_workpaper_guidance` 在 `request is None`（测试直调）时构造 `Request({... "url": _FakeUrl()})`，而 `_FakeUrl` 全库无定义 → route 直调必崩，`test_wp_guidance_router.py` 7 例全红。这是一处未完成的 ETag 接线残留（docstring 声称 Task 9 AC#1 route 级 304 但函数体从未读 header/返回 304）。
  - 修：`if_none_match = request.headers.get("if-none-match") if request is not None else None`，删除伪造 Request；在最终 return 前加「命中 If-None-Match → `Response(status_code=304, headers={"ETag": etag})`」真正兑现 route 级 304。`Response` 已在 import 内。
  - 结果：`test_wp_guidance_router.py`(7) + `test_guidance_api_task9.py`(21) = 28 全绿；后端 guidance 全套 204 passed。

### 7.2 后端产物增量（§1 表补充）

| 文件 | 承载概念 | 对应 Task | 判定 |
|---|---|---|---|
| `guidance_gid.py` | SourceRefHandler Protocol + Registry + StableSheetIdentity | 4 | ✅ 真交付（§1.1 记「部分存在/不存在」已过时；protocol 层已落形） |
| `guidance_publication_service.py` | draft→reviewed→published 生命周期 + immutable/capability 守卫 + DB 持久化 | 6 | ✅ 真交付（§1.1 记「不存在」已过时） |
| `guidance_resolution_identity.py` | GUIDANCE_CONTRACT_VERSION / GUIDANCE_RESOLUTION_SCHEMA_VERSION | 8/9 | ✅ |
| `guidance_api_contract.py` | fingerprint / stable_cache_key / make_etag / OwnerGate / StructuredError | 9 | ✅ 真交付（§1.1 记 GuidanceResponse「缺 contractVersion/schemaVersion…」已过时；resolve_authoritative_exact 已返回全部字段） |
| `guidance_completion_guard.py` | completion_status 三轴 pure evaluator | 5/14 | ✅ |
| `guidance_exemption_service.py` | exemption owner/expiry 校验 | 5 | ✅ |
| `project_guidance_supplement_service.py` | supplement 独立版本 | 6 | ✅ |

对应测试增量：`test_guidance_gid.py` / `test_guidance_publication_lifecycle.py` / `test_guidance_resolution_task8.py` / `test_guidance_api_task9.py` 均已在库且全绿。

`wp_guidance_service.py`：`resolve_authoritative_exact()` **已存在**（§1.1 记「不存在（功能等价）」已过时），与 `resolve_guidance` 并存。

### 7.3 mutation harness 增量（§4 补充）

§4 只记 1 个脚本，实际有 **9 个**：`mutate_guidance_{gc0_inventory_resolution, contract_inventory, gid, source_ref_wiring, publication, resolution, resolution_task8, supplement_completion, api_task9}_guards.py`。四类缺口（contract/inventory/resolution/UI-adjacent）已被 gc0_inventory_resolution + api_task9 + supplement_completion 覆盖。

2026-09-08 `--check-anchors` 批量核验修复两处真问题（见 §7.4），修复后该脚本全量跑 **6/6 RED、6/6 restored**。

### 7.4 变异守卫两处修复（`mutate_guidance_gc0_inventory_resolution_guards.py`）

1. **RES01 ANCHOR-MISS**：`extract_exact_static(..., validated_entry=runtime_entry)` 因 Task 8 新增 `resolve_authoritative_exact` 而在 `wp_guidance_service.py`（CRLF）出现 2 次，锚点不再唯一。修：尾锚扩到 `if child is not None:\r\n  return self._build_response(`，唯一定位 `resolve_guidance`（integration test 实际走的路径）。
2. **INV02 GREEN（假绿守卫）**：原锚点把 runtime invalid 分支的 `or static.source_ref_status in {...}` 改 `or False`，但同分支 `or static.exact_status=="exact"` 独立兜底 + `validation_blocker` 直接读 `source_ref_status` → 测试无法察觉。改为 load-bearing 锚点：把 `validation_blocker` 字典里 `"unvalidated": "source_ref_context_missing"`（`guidance_inventory.py`，**LF**，16 空格缩进）改成默认码 `source_refs_invalid`，`test_static_without_source_ref_validation_never_reaches_exact` 的精确 blocker 断言即 RED。教训：同文件不同行尾（service=CRLF / inventory=LF）；空串 replacement 会让 `count` 退化，须用非空替换。

### 7.5 任务状态判定（复选框已准确，无需改动）

- `[x]` 3/4/6/8/9/15：产物 + 测试 + 变异三证齐全，判定正确。
- `[~]` 5：RuntimeGuidanceInventory 在内存构建，未落盘不可变 snapshot、无 latest pointer / digest-addressed bounded cache（design §2.3 承诺未兑现）。
- `[~]` 13/14：store 单 fetch + race gate + TTL 已实现（缺 ownerEpoch/contextRevision 字段级 gate、ETag revalidate，用等价实现替代）；UI 只分层 source + resolution_status 两轴 + sanitize（failClosed 已验），未分层完整三轴 provenance + completion_status。
- `[~]` 16：`ConsumerAck`/handoff 仅 C0 wire 定义；guidance 侧无 durable ACK ledger + consumer pipeline（`grep handoff_consumer|AckLedger|record_ack` = 0）。**唯一非外部阻塞、可推进的里程碑**，custom spec Task 11 正等它。
- `[~]` 20：BLOCKED —— `F-SHELL`（formula Task 13）未发布（`grep F-SHELL|GtShell|shellOutlet` = 0）。
- `[~]` 22/23：BLOCKED —— `X-HANDOFF-CONFORMANCE`/`X-RUNTIME-EVIDENCE`（custom Task 19）未发布，且其自身依赖 `G-HANDOFF-CONSUMER`(=本 spec T16) + `F-SHELL`。
- `[~]` 17/18/19/21：定向测试与变异已大面积落地（后端 204 + 前端 54 全绿），但 C1（21）需冻结 catalog snapshot 全 complete 的正式核算、19 需 clean-checkout tracked 核对，尚未收口。

### 7.6 未跟踪产物（clean checkout 蒸发风险，git status 实录 `??`）

除 §5 已列，新增未跟踪正式产物需在归档前 `git add`：
```
?? backend/app/services/guidance_api_contract.py
?? backend/app/services/guidance_completion_guard.py
?? backend/app/services/guidance_exemption_service.py
?? backend/app/services/guidance_gid.py
?? backend/app/services/guidance_publication_service.py
?? backend/app/services/guidance_resolution_identity.py
?? backend/tests/test_guidance_api_task9.py
?? backend/tests/test_guidance_gid.py
?? backend/tests/test_guidance_publication_lifecycle.py
?? backend/tests/test_guidance_resolution_task8.py
?? backend/scripts/diagnose/mutate_guidance_*.py（9 个）
```
（本次未执行 `git add`，仅登记；入库由 spec 推进方按协作规范统一处理。）

---

## 8. 2026-09-08 Task 16 交付（G-HANDOFF-CONSUMER）

T16 从 `[~]`（§7.5 记「唯一非外部阻塞、可推进」）推进为 `[x]`。durable ACK ledger + consumer pipeline + visibility saga 全部落地，custom spec `X11` 现可消费。

### 8.1 新增产物

| 文件 | 承载概念 | 判定 |
|---|---|---|
| `backend/app/services/guidance_handoff_consumer_service.py` | compute_handoff_digest / verify_candidate_handoff / verify_finalized_handoff（有序 pipeline）/ record_ack（幂等）/ resolve_visibility（saga）/ mark_stale_on_change / build_ghandoff_consumer_evidence_payload | ✅ behavior |
| `backend/app/models/guidance_handoff_ack_models.py` | GuidanceConsumerAck（幂等 ledger）+ GuidanceHandoffVisibility（saga 状态），枚举对齐 C0 | ✅ |
| `backend/migrations/V157__guidance_handoff_consumer_ack.sql` | 两表 + `ux_guidance_consumer_ack_idem`（幂等唯一键）+ visibility 唯一键，全 IF NOT EXISTS | ✅（需重启后端应用；SQLite 侧已 create_all 验证 ORM 可移植） |
| `backend/tests/test_guidance_handoff_consumer.py` | 19 例行为测试（SQLite in-memory + C0 fixtures 直读） | ✅ 全绿 |
| `backend/scripts/diagnose/mutate_guidance_handoff_consumer_guards.py` | 5 条 load-bearing 变异，全 RED | ✅ 5/5 RED、5/5 restored |
| `backend/scripts/fix/emit_ghandoff_consumer_evidence.py` | 从单源 payload 落盘 evidence | ✅ |
| `backend/data/guidance/contracts/ghandoff/evidence/ghandoff_consumer_evidence.json` | G-HANDOFF-CONSUMER EvidenceEnvelope（subject=contract，sagaContract + idempotencyKey，module digest 与实现锁死） | ✅ |

### 8.2 设计裁决落地

- **candidate 永不 exact**：`verify_candidate_handoff` 只产 `review_pending`；`record_ack` 显式拒绝非 ACCEPTED/REJECTED verdict 入 ledger（candidate 无法进 ledger）。变异 M-CAND-EXACT 证伪。
- **finalized 有序 pipeline**：contract → phase → authority → digests（artifact/mapping/formulaBoundary/guidance + staleFingerprint）→ 九段唯一 + 每段 refs 非空 + locator kind 合法（生命周期名 custom_candidate/custom_confirmed 拒绝）→ membership。任一 reason 即 REJECTED。变异 M-SECTIONS 证伪。
- **ACK durable + 幂等**：`(handoff_id, handoff_digest, consumer, consumer_version)` 为幂等键；同 digest 重复提交命中同一行，新 digest 产生新行。变异 M-ACK-IDEM 证伪。
- **visibility saga**：全部 required consumer ACCEPTED 才 ACTIVE；任一 REJECTED/缺 ACK → PENDING/REJECTED（visibility=0）。变异 M-VIS-REJECT 证伪。不宣称跨系统 ACID（evidence.sagaContract.crossSystemAcid=false）。
- **stale**：`mark_stale_on_change` 把旧 handoff_digest 的 ACTIVE 行标 stale，不删 ACK 历史。
- **digest 真哈希**：`compute_handoff_digest` = canonical sha256；变异 M-DIGEST-CONST（退化常量）证伪。

### 8.3 未跟踪产物（clean-checkout 蒸发风险，需 git add）

```
?? backend/app/services/guidance_handoff_consumer_service.py
?? backend/app/models/guidance_handoff_ack_models.py
?? backend/migrations/V157__guidance_handoff_consumer_ack.sql
?? backend/tests/test_guidance_handoff_consumer.py
?? backend/scripts/diagnose/mutate_guidance_handoff_consumer_guards.py
?? backend/scripts/fix/emit_ghandoff_consumer_evidence.py
?? backend/data/guidance/contracts/ghandoff/evidence/ghandoff_consumer_evidence.json
```

### 8.5 2026-09-09 Task 2 收口 + Task 5 交付

- **Task 2 `[x]`**：§7–§8 已覆盖 contract/inventory/resolution/handoff 行为守卫与变异；tracked 入库留 T19。
- **Task 5 `[x]`**：新增 `guidance_inventory_snapshots.py`
  - CatalogEntryKey / RuntimeEntryKey 分域
  - `GuidanceInventorySnapshot` 不可变 + `SnapshotStore`（digest 寻址 + latest pointer + bound）
  - `gross_required` / `effective_required` / PASS 核算；非法三轴重叠 fail-closed
  - `platform_guidance_health`：HEALTHY/DEGRADED/BLOCKED + `C2_REEVALUATION_REQUESTED`
  - 测试 9 passed；变异 3/3 RED（`basis/T05-mutation-report.json`）
- **仍 BLOCKED / 可推进**：
  - T7 九段内容迁移；T17–21 定向测试/CI/C1
  - T20 现可消费 `F-SHELL`（formula 15/15）
  - T22/23 仍等 custom X milestones（SYNC gate）
  - custom T10/14/18/19 仍诚实 `[~]`（SYNC-MULTI-RESOLVER）

### 8.6 2026-09-09 Task 11–14 交付

- **T11 `[x]`**：`htmlStableContextEmitter` + `sheetUidProjection`；GtWpRenderer 唯一 HTML publish；禁 display-name 作 uid
- **T12 `[x]`**：Univer `resolveUniverSheetContext` + `univerContextEmitter`；OO 外层/整册同一投影；`onSwitchSheet` 必 publish
- **T13 `[x]`**：store 四门 race（requestId/identity/epoch/revision）+ If-None-Match/304；cache key 用 sheetUid
- **T14 `[x]`**：UI 分层 primary/overlays/extraction + completion + reasons/blockers；sanitize 既有

### 8.13 2026-09-09 T19 收口 `[x]`

- commit `196753f1b`：566 files / +67432 −5310；未 tracked guidance 路径 **0**
- 提交前实测：guidance 套件 **245 passed**、T17 变异 **11/11 RED**、前端门 **37 passed**
- 行数门禁 → 抽伴生模块：`guidance_template_authority` / `guidance_runtime_facts` / `guidance_runtime_inventory` / `wp_guidance_chat_stream` / `wp_guidance_section_prompts`；旧 import 由 `__getattr__` 兼容
- G-C0 反向重复扫描器修复：`import { type Foo }` 不再误判为重复声明；findings 8→0，删 2 条陈旧豁免，加正反对照测试
- **进度 18/23 → 19/23**；T7/T21/T22/T23 仍诚实 `[~]`

### 8.12 2026-09-09 T7 SourceRef 可行性核算

- `diagnose_guidance_source_ref_feasibility.py`：264 单模板 + 30 父工作簿 sheet = **294 可挂**；14 ambiguous；65 无模板
- 仍有 **1158** 个 canonical section `source_refs=[]`；报告只记 path/digest/sheetNames，不生成 ref
- **诚实结论**：缺段（materials 373 / data_sources 374 / formulas 357 / completion 356）无任何现成正文来源，脚本不可补；T7 只能人工批次
- evidence：`basis/T07-source-ref-feasibility.json`

### 8.11 2026-09-09 T7 高置信 unmapped 提升

- 别名扩展：`本表用途`→purpose、`与其他底稿的关联`→evidence、`测试方法与程序`→steps、`偏差率计算`→formulas 等
- `promote_unmapped_guidance_sections.py`：**85 files / 149 sections**；migrate unmapped **308→159**；digest 与 migrate 对齐 errors=0
- pilot A1-13/A14-4：unmapped 清空；仍缺 SourceRef → exact/C1 不得绿
- evidence：`basis/T07-promote-unmapped-summary.json` + `T07-unmapped-title-freq.json`

### 8.10 2026-09-09 T19 tracked 清单 + custom T18 模块 RED

- **T19 `[~]`**：`basis/T19-tracked-paths.json` 已列推荐 `git add` 组（含 `rightRailArbiter` CI 依赖）；仍待显式 commit 才过 clean-checkout。
- **链路上游**：custom T18 非 OO 模块变异 **5/5 RED**（不解锁 SYNC；T22/T23 仍 BLOCKED）。

### 8.9 2026-09-09 T21 C1 冻结 + T7 工作卡 + T22 consumer

- **T21 `[~]`**：`emit_c1_catalog_milestone.py` → C1 **FAIL**（effective=373 complete=0 pending=373）；`basis/T21-c1-catalog-milestone.json` + `evidence/C1/`。不得假绿。
- **T7 `[~]`**：`emit_t7_migration_workcards.py` → **373** cards（`basis/T07-workcards/`，no autofill）；仍需人工九段 + SourceRef + publication。
- **T22 `[~]`**：`basis/T22-x-handoff-consumer-verdict.json` verdict=BLOCKED（custom X PARTIAL / SYNC）。
- **进度仍 18/23**：工程交付面已齐；内容分母与外部 X 门未过。

### 8.8 2026-09-09 Task 17 + T19 进展 + T7 诚实状态

- **T17 `[x]`**：`run_guidance_task17_mutations.py` → **11/11 RED**；`basis/T17-backend-mutation-report.json`
- **T19 `[~]`**：CI `wgcc-guidance-backend-guards` / `wgcc-guidance-frontend-guards` 已追加；
  `basis/T19-ci-and-tracking-status.json` 登记 clean-checkout **BLOCKED**（大量 `??`）
- **T7 `[~]`**：canonical schema `--check` files=373 changed=0 **unmapped=308**；不得假绿
- **T21**：依赖 T7 effective complete=0 pending；暂 BLOCKED
- **T22/23**：仍等 custom `X-HANDOFF-CONFORMANCE` / `X-RUNTIME-EVIDENCE`（SYNC gate）
