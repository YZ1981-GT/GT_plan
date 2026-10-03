# Design Document

## Overview

本设计采用四条生命周期和一份整册项目实例：

```text
multipart upload
  → UploadArtifact (private quarantine → package/semantic preflight)
  → MappingDraft
  → immutable TemplateCandidate
       └─ static HTML/image/structure preview only
  → TemplatePublication(PENDING_VISIBILITY)
       ├─ finalized CustomGuidanceHandoff → G-HANDOFF-CONSUMER → ConsumerAck ledger
       ├─ renderer/F-SHELL/entry-namespace conformance ACKs
       └─ producer commit-visibility transaction → ACTIVE
  → one ProjectWorkbookInstance
       ├─ ProjectWorkbookSheetEntry A
       ├─ ProjectWorkbookSheetEntry B
       └─ shared artifact/current revision/workbook generation/OnlyOffice room
             ↔ editable/read-only HTML projection
             ↔ OnlyOffice durable application
```

关键约束：candidate 不进入生产 OnlyOffice；多 sheet 不复制 workbook；editable projection 不能缺 adapter；所有 HTML 写入在 staging copy 上完成并以客户端 base revision CAS；跨服务 finalize 是 visibility saga，不是 ACID。

## 1. Ownership and External Contracts

本 spec 只 import 以下共享契约，不复制字段定义：

- `G-C0`：`TemplateAuthorityIdentity`、candidate/finalized `CustomGuidanceHandoff`、`GuidanceSection`、`SourceRef`、`EvidenceEnvelope`、`ConsumerAck` wire schema；
- `G-ID`：template/sheet stable identity 与 authority rules；
- `G-HANDOFF-CONSUMER`：guidance handoff validator/ACK ledger；
- `F-SHELL`：runtime location、toolbar/rail/capability host contract；
- 既有 sync/version kernel：`AuthoritativeContentWriter`、content/representation revision、forcesave request/application/operation。

本 spec 自己拥有 ingestion policy、四生命周期 repository、workbook/sheet project model、projection manifest/adapter、finalize coordinator、custom operations 与 X evidence。

### 1.1 External sync gates

| Gate | 必须证明 |
|---|---|
| `SYNC-UNIFIED-ROOM` | 每个 `ProjectWorkbookInstance` 只有一个 active OO room/document key |
| `SYNC-MULTI-RESOLVER` | wp_code/wp_id/entry_id/document key 唯一解析到同一 workbook instance/generation |
| `SYNC-DURABLE-APPLICATION` | forcesave callback 字节 durable、application 幂等、content pointer 已提交 |
| `SYNC-ENTRY-NAMESPACE` | custom_cells 与 WOPI/offline 共用 entry/pointer/generation/rollback namespace |

这些 gate 未满足时，相关能力保持 BLOCKED；本 spec 不在文档中假定它们已存在。

## 2. Scope, Authorization and ApprovalIntent

所有 domain object 包含 `tenantId/organizationId`，project-local 对象再含 `projectId`。Scope 从 authenticated context 与服务端 project/template authority 产生，不信任客户端推断。

```ts
interface ApprovalIntent {
  approvalIntentId: string
  scope: 'organization' | 'project'
  organizationId: string
  projectId: string | null
  candidateId: string
  candidateDigest: string
  policyVersion: string
  requestedAction: 'publish_organization' | 'finalize_project' | 'upgrade' | 'rollback' | 'remap' | 'security_revoke'
  initiatorId: string
  requiredApproverClass: string
  authorizationEpoch: number
  createdAt: string
  expiresAt: string
}
```

ApprovalIntent immutable。Candidate/policy/scope/digest/authorizationEpoch 变化即失效。组织发布要求 initiator != approver；project mutation 使用独立 write fence，不能把权限写入 content fingerprint。

## 3. Ingestion Policy v1

政策是服务端单一版本对象，UI 通过只读 endpoint 展示，测试从同一对象取阈值。

| Policy key | v1 default | Gate |
|---|---:|---|
| `max_upload_bytes` | 50 MiB | streaming upload |
| `max_expanded_bytes` | 512 MiB | package total |
| `max_zip_entries` | 20,000 | package entries |
| `max_entry_compression_ratio` | 100:1 | per entry |
| `max_total_compression_ratio` | 100:1 | package total |
| `max_sheets` | 256 | semantic scan |
| `max_non_empty_cells` | 5,000,000 | semantic scan |
| `max_declared_range_cells` | 20,000,000 | sparse bomb |
| `max_xml_bytes/depth/nodes` | versioned values | XML parser |
| `max_relationships` | versioned value | OOXML graph |
| `cpu_seconds` | versioned value | worker |
| `wall_seconds` | 120 | worker |
| `max_ram_bytes` | versioned value | worker/container |
| `max_file_descriptors` | versioned value | worker |
| `max_temp_disk_bytes` | versioned value | worker |
| `organization_concurrency/storage_quota` | tenant policy | admission |
| `incoming_ttl` | 24 h | cleanup |
| `failed_artifact_ttl` | 7 d | cleanup |
| `candidate_ttl` | 30 d | cleanup |

Evidence 同时冻结 policy version、scanner build digest、worker image、parser/library versions 和实际资源用量。阈值或 scanner build 变化使旧 preflight stale。

## 4. Package Security Pipeline

### 4.1 Streaming quarantine

`UploadFile` chunk 写 private quarantine，边写边计算 SHA-256/size；storage key 仅由随机 ID 构造。关闭流后验证 extension/MIME/ZIP magic。Preflight 前不生成 public URL、OO config、runtime entry 或 project artifact。

### 4.2 Entry path canonicalization

每个 ZIP path 执行：

1. `\`→`/`；Unicode NFKC；
2. 拒绝 absolute、drive、UNC、`.`、`..`、空 segment；
3. 拒绝 trailing dot/space、colon/ADS、Windows device names；
4. 读取 external attrs，拒绝 symlink/reparse/special file；
5. 对 normalized path 做 Unicode casefold，拒绝 duplicate/collision；
6. 在受控 temp root 内验证 realpath boundary。

### 4.3 XML/OOXML policy

XML parser 禁 DTD/entity/network，限制 bytes/depth/nodes/relationships。Feature matrix：

| Feature | v1 decision |
|---|---|
| `.xlsx` | ALLOW_TO_PREFLIGHT |
| `.xlsm` | PREFLIGHT_ONLY / FINALIZE_BLOCKED |
| VBA/XLM/DDE/ActiveX/OLE/executable embedded | BLOCK |
| external link/relationship/data connection | BLOCK，v1 无 sanitizer |
| encrypted/password/corrupt | BLOCK |
| image/chart/drawing/comment | REVIEW + PRESERVE |
| names/tables/validation/CF/merge/hidden/protection | REVIEW + PRESERVE |
| unknown feature | BLOCK_PENDING_POLICY |

公式只 tokenization，不计算；worker 禁网。

## 5. Preflight Reports

`PackageReport` 保存 package graph、content types、relationships、findings、budgets 和 preservation inventory。`WorkbookReport` 保存 workbook relationships、cross-sheet formulas、defined names 和 sheet reports。

每个 `SheetReport` 包含 observed stable identity/name/order/visibility、ranges/freeze/protection/merge/hidden、cell types/formats/formulas/dependencies/errors、regions、stable key carriers、identity risks、guidance extraction candidates 和 projection recommendation。

Finding 统一为：

```ts
interface PreflightFinding {
  code: string
  severity: 'BLOCKER' | 'WARNING' | 'INFO'
  workbookLocator: string
  sheetUid: string | null
  sourceRef: SourceRef | null
  policyDecision: string
  remediation: string
}
```

`valid` 只能由 blocker + required warning decisions 派生；空/异常 report 永不 valid。

## 6. Four Lifecycle Repositories

### 6.1 UploadArtifact

```text
QUARANTINED → PREFLIGHT_RUNNING → PREFLIGHT_READY
                           ↘ PREFLIGHT_FAILED
non-active → REJECTED / EXPIRED
```

只描述原始字节和 preflight。

### 6.2 MappingDraft and TemplateCandidate

MappingDraft 是 optimistic-versioned mutable draft。`freezeCandidate()` 固定 artifact/policy/scanner/mapping/guidance/adapter digests，生成 immutable candidate revision：

```text
DRAFT → CANDIDATE_READY → SUPERSEDED / EXPIRED / REJECTED
```

Candidate 不表达 runtime visibility。

### 6.3 TemplatePublication

```text
PENDING_VISIBILITY → ACTIVE → WITHDRAWN
                  ↘ FAILED
ACTIVE → SECURITY_REVOKED
```

Publication 引用 finalized `TemplateAuthorityIdentity` 和 ACK ledger。

### 6.4 ProjectOperation

实例化、grid mutation、forcesave/application、merge、remap、upgrade、rollback、security migration 各自有 operation type：

```text
PENDING → APPLYING → COMMITTED
                 ↘ CONFLICT / BLOCKED / FAILED / COMPENSATED
```

所有 transition 使用 base revision、idempotency、lease、authorization epoch/write fence、input/output digests 和 injectable clock。

## 7. Stable Identity and Candidate Instrumentation

Stable identity 优先级：

1. workbook 已有不可变业务 key/defined-name/custom metadata carrier；
2. 用户确认后，在**新 immutable instrumented candidate** 中写入平台 metadata/defined-name carrier，并通过 reopen/package roundtrip/preservation diff；
3. 无法安全 instrument 时不允许 editable projection。

Instrumentation 不修改 quarantine original 或既有 candidate；它创建新 candidate revision/digest并使旧 evidence stale。Label、sheet order、row index 不是 carrier。

## 8. Mapping and Projection SPI

```ts
interface CustomProjectionManifest {
  manifestVersion: string
  workbookLineageId: string
  sheetUid: string
  projectionMode: 'editable_grid' | 'read_only_html' | 'onlyoffice_only'
  regions: RegionMapping[]
  fields: FieldMapping[]
  rowIdentity: IdentityRule | null
  columnIdentity: IdentityRule | null
  formulaBoundaryVersion: string
  preservationDecisions: PreservationDecision[]
  adapterId: string | null
  adapterVersion: string | null
}
```

Custom-owned adapter SPI：

```ts
interface CustomWorkbookAdapter {
  extract(bytes: ImmutableBytes, manifest: CustomProjectionManifest): ProjectionSnapshot
  validate(mutations: ManagedMutation[], base: ProjectionSnapshot): ValidationResult
  apply(staging: MutableStagingWorkbook, mutations: ManagedMutation[], manifest: CustomProjectionManifest): ApplyResult
  diff(before: ImmutableBytes, after: ImmutableBytes, manifest: CustomProjectionManifest): PreservationDiff
  rebase(base: ImmutableBytes, current: ImmutableBytes, incoming: ManagedMutation[]): RebaseResult
  merge(base: ImmutableBytes, current: ImmutableBytes, incoming: ImmutableBytes, manifest: CustomProjectionManifest): MergeResult
}
```

- editable_grid：manifest + adapter 必填；
- read_only_html：deterministic extractor 必填，mutation endpoint 不可用；
- onlyoffice_only：adapter/projection 可 null，不创建空 Grid。

## 9. Static Candidate Preview and Guidance

Candidate preview service 只输出 sanitized static HTML、server-rendered image 或 structure JSON。它使用一次性、短期、candidate-scoped token，但不产生生产 WOPI/OnlyOffice config。

External links、macros、objects 永不执行；所有 formula/property/comment 显示为文本。Preview 显示 managed/unmanaged、identity carriers、mode、preservation risks。

Guidance candidate 使用 import 自 G-C0 的 candidate handoff variant；不得补 finalization/confirmed fields。任何 candidate/policy/scanner/mapping/guidance digest 变化使 preview evidence stale。

## 10. Project Workbook Representation

```ts
interface ProjectWorkbookInstance {
  workbookInstanceId: string
  organizationId: string
  projectId: string
  wpId: string
  workbookLineageId: string
  pinnedTemplateVersionId: string
  currentArtifactId: string
  contentRevision: string
  representationRevision: string
  workbookGeneration: number
  onlyOfficeRoomId: string | null
  contextFingerprint: string
  authorizationEpoch: number
}

interface ProjectWorkbookSheetEntry {
  entryId: string
  workbookInstanceId: string
  sheetUid: string
  sheetCode: string | null
  wpCode: string
  componentType: string
  projectionMode: 'editable_grid' | 'read_only_html' | 'onlyoffice_only'
  manifestVersion: string | null
  guidanceRevision: string
}
```

一份 workbook 只有一个 current artifact、generation 和 room；child entries 只是导航/能力/manifest identity。Cross-sheet formulas、defined names 和 package parts 始终在整册保存。任何 write 先推进 workbook generation，再按 affected sheets 更新派生 projection。

Namespace migration 必须把 legacy wp_code custom_cells 与 wp_id WOPI/offline 映射到同一 `workbookInstanceId/entryId`，并证明 pointer/generation/rollback/evidence 唯一。

## 11. Finalize Visibility Saga

```text
lock candidate + ApprovalIntent + idempotency
 → verify policy/scanner/blockers/warnings/digests/capabilities
 → allocate finalized authority/publication/workbook-entry/manifest IDs
 → transaction: PENDING_VISIBILITY metadata + rollback point + outbox
 → submit finalized handoff to G-HANDOFF-CONSUMER
 → collect durable guidance/renderer/F-SHELL/namespace ACK ledger
 → all required ACCEPTED
 → producer transaction: publication + runtime entries ACTIVE
```

ACK 绑定 subject/handoff/conformance digest、consumer/version、verdict/reasons。任何 reject/timeout 保持 visibility=0；watchdog 可重发或 compensation。Immutable artifact 可以先存在，但 runtime readers 只读取 ACTIVE。该流程是 saga，不是跨系统 ACID。

## 12. Project Instantiate, Pin and Withdraw

ACTIVE publication 可实例化一份 ProjectWorkbookInstance；组织模板/candidate 保持只读。项目 context fingerprint 只含内容相关年度/准则/公司/template facts，不含权限。权限由 `authorizationEpoch/writeFence` 独立校验。

新 publication 只生成 available upgrade。WITHDRAWN 禁止新实例化，但 pinned 项目继续使用并显示风险。`SECURITY_REVOKED` 是独立高权限事件，可阻断 pinned instance，必须有影响清册、通知和恢复路径。

## 13. HTML → OOXML Staging CAS

正确流程：

```text
client mutation(base content/representation revision + auth epoch)
 → validate client base, membership, capability, manifest/adapter/type/protection
 → load immutable base bytes
 → clone private staging copy
 → adapter.apply(staging)
 → reopen + managed value readback + unmanaged preservation diff
 → refresh staged projections
 → AuthoritativeContentWriter.commit_bytes(expected=client base revision)
 → CAS success: atomically switch current pointer/generation
 → refresh affected child entries
```

CAS/adapter/diff/readback/writer 失败即删除 staging，不动 current。禁止先对 `ctx.wp.file_path` 原地 `write_cells_to_xlsx()`，也禁止先读取服务器“最新 revision”替代客户端 base 后提交。

## 14. OnlyOffice Durable Flow and External Gates

```text
request switch to HTML
 → resolve all identities via SYNC-MULTI-RESOLVER
 → verify one room via SYNC-UNIFIED-ROOM
 → forcesave request(operation id + expected generation)
 → command accepted
 → callback bytes durable + idempotent content application (SYNC-DURABLE-APPLICATION)
 → verify unified entry namespace (SYNC-ENTRY-NAMESPACE)
 → adapter refresh(expected content/representation revision)
 → HTML reload returned generation
```

Accepted 不等于 durable。Status 6/2/retry/nothing_to_save 都复用既有 kernel idempotency。Gate 缺失时 capability blocked，不创建 custom callback writer 绕开。

## 15. Merge and Remap

Adapter 以 base/current/incoming 做 field-level three-way merge。不同 stable fields 自动合并；同 field 不同 typed value输出 conflict。Unmanaged OOXML parts通过 preservation diff 保留。

Structural drift（rows/cols/sheet identity/cross-sheet formula/defined name/locator）生成 immutable `RemapCandidate`。确认后发布新 manifest/adapter mapping、迁移 report、guidance stale、review/formula anchor migration 和 rollback point。Carrier 丢失/重复不得 label 猜回。

所有 merge/remap 都是 ProjectOperation，可在 crash 后重放/补偿；current pointer 只在 CAS commit 后变化。

## 16. Upgrade, Rollback, References and Retention

Template/publication/version/manifest/guidance/adapter 均 immutable。Upgrade planner 输出 workbook/sheet/field/formula/preservation/guidance/adapter diff、migration conflicts、expected hash 和 rollback point。Apply 复用 staging/CAS；rollback 生成新审计 revision，不删历史。

`ArtifactReferenceGraph` 显式建边：

```text
UploadArtifact → Candidate → Publication
Publication → ProjectWorkbookGeneration
ProjectOperation → base/current/incoming/staging/result
RollbackPoint → WorkbookGeneration
Evidence/LegalHold/Lease → Artifact
```

Cleanup 使用 injectable clock：先 durable tombstone/intent，查询完整图和 lease/hold，再删 object，最后记录 result。Finalized/pinned/rollback/evidence/hold 引用不可删。

## 17. UI and F-SHELL Consumption

三个入口分别呈现真实 action/权限/成功语义。Ingestion wizard 展示 policy、preflight、mapping、identity、guidance、candidate、approval、finalize saga 和 blockers。

Candidate 只用静态 preview。ACTIVE project entries 通过 F-SHELL 注册 host facts、outlets、anchors/providers；不复制 formula button/dialog/location store/review/guidance/AI fixed rails。

## 18. Evidence and X Milestones

所有 evidence 使用 import 自 G-C0 的 envelope subject union，记录 digests、scanner build、authority、operation、revisions、room/entry identity、browser artifacts和 verdict。

- `X-HANDOFF-CONFORMANCE`：candidate 不 confirmed、finalized ACK、rejection visibility=0、stale、rollback conformance；
- `X-RUNTIME-EVIDENCE`：user-upload runtime inventory projection，以及 create/upgrade/rollback/withdraw/stale 时的 `C2_REEVALUATION_REQUESTED`。

Custom Task 19 发布这两个 milestone 后可按自身完成门归档；它**不等待** guidance Task 22/23 或 C2 verdict。

## 19. Correctness Properties

### Property 1: 三入口 action、副作用和成功语义互斥
**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**

### Property 2: scope、ApprovalIntent 与 initiator/approver 控制不可被后补或改写
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

### Property 3: capability/write fence 前置且读取权限不升级为 raw/publish 权限
**Validates: Requirements 2.6, 2.7**

### Property 4: 所有正式字节先进入 private quarantine 且 hash 可复现
**Validates: Requirements 3.1, 3.2**

### Property 5: policy、quota、scanner build 与资源失败均 fail-closed
**Validates: Requirements 3.3, 3.4, 3.5, 3.6, 3.7**

### Property 6: ZIP path/XML canonicalization 阻断 traversal、collision 与 parser abuse
**Validates: Requirements 4.1, 4.2**

### Property 7: xlsx/xlsm/宏/外链/未知 feature 按 v1 矩阵裁决且绝不执行
**Validates: Requirements 4.3, 4.4, 4.5, 4.6, 4.7**

### Property 8: preflight report 逐 workbook/sheet 可定位、非空且可复现
**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7**

### Property 9: 四条生命周期互不混用且 crash 后可恢复
**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7**

### Property 10: 一个多 sheet 项目只有一份 workbook current/generation/room
**Validates: Requirements 7.1, 7.2, 7.3, 7.4**

### Property 11: sheet/entry identity 稳定且所有 resolver/namespace 唯一
**Validates: Requirements 7.5, 7.6, 7.7**

### Property 12: editable/read-only/OO-only mode 与 identity/adapter 能力一致
**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8**

### Property 13: candidate preview 静态、安全、不可运行且不会伪造 confirmed
**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6**

### Property 14: finalize ACK saga 幂等且未全 ACCEPTED 时 visibility 永远为 0
**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7**

### Property 15: 项目只编辑自己的 pinned instance，普通 withdraw 不破坏已 pin 项目
**Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.6**

### Property 16: security revocation 与 authorization epoch 独立于 content fingerprint
**Validates: Requirements 11.5, 11.7**

### Property 17: HTML mutation 只在 staging 上应用，客户端 base CAS 失败时 current 字节不变
**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.7**

### Property 18: 成功 commit 推进整册 generation 并刷新受影响 child projections
**Validates: Requirements 12.6**

### Property 19: OnlyOffice 仅在统一 room/resolver/namespace 和 durable application 后刷新 HTML
**Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7**

### Property 20: three-way merge 不丢不同字段，同字段与结构冲突可见
**Validates: Requirements 14.1, 14.2, 14.3, 14.4, 14.5, 14.7**

### Property 21: crash recovery 不让 current pointer 指向半成品
**Validates: Requirements 14.6**

### Property 22: 版本/升级/回滚 immutable 且 retention 服从完整引用图
**Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7**

### Property 23: artifact 访问、审计和跨 spec 契约不泄漏、不复制真源
**Validates: Requirements 16.1, 16.2, 16.3, 16.4**

### Property 24: X milestones 单向发布 evidence，不等待 guidance C2
**Validates: Requirements 16.5, 16.6, 16.7**

### Property 25: 自动化、变异、Playwright 与 tracked evidence 共同决定 closure
**Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.5, 17.6**

## 20. Testing Strategy

| 层 | 重点 |
|---|---|
| Contract/auth | G/F imports、tenant scope、ApprovalIntent、epoch/write fence、role separation |
| Policy/upload | streaming hash、quota、cancel/retry、scanner build、resource budgets |
| Package/XML | NFKC/casefold/ADS/reserved/symlink、bomb、DTD/entity、macro/OOXML feature matrix |
| Semantic | multi-sheet/cross-sheet formula、ranges、identity carriers、preservation、guidance candidate |
| Lifecycle | four repositories、transition/idempotency/lease/watchdog/injectable clock |
| Representation | one workbook + child entries、namespace migration、multi-resolver、generation |
| Adapter | three modes、instrumentation、extract/apply/diff/rebase/merge、static preview |
| Finalize | pending visibility、ACK ledger、retry/compensation、ACTIVE gate |
| HTML write | client-base validation、staging readback/diff、writer CAS/current immutability |
| OO durable | unified room、forcesave accepted vs durable、application retry、nothing_to_save |
| Merge/version | different/same field、remap、upgrade/pin/withdraw/revoke/rollback |
| Retention | reference graph、legal hold/lease、tombstone、clock-controlled cleanup |
| Mutation | 单点破坏且区分 RED/GREEN/ANCHOR-MISS/WRONG-TEST |
| Playwright | 三入口、恶意/复杂文件、静态 preview、三模式、多 sheet、双向、版本、清理 |

不得用模板列表新增、HTTP 200、单个 `valid=true`、OnlyOffice 可打开、数据库 projection 更新或未跟踪 evidence 替代闭环证据。
