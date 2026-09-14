# Design Document

## Overview

本设计以一套规范模型替换旧 `exact_status + source + extract_exact_static()` 方案：

```text
Authoritative template / publication / custom facts
              ↓
Catalog Inventory Snapshot      Runtime Inventory Snapshot
              ↓                         ↓
      Stage Accounting + Continuous Health
              ↓
resolve_authoritative_exact → parent authoritative chain
              ↓
Versioned API → Host Location → Store → Sanitized Guidance UI
                                      ↘ GuidanceRailAdapter → F-SHELL

Custom candidate/finalized handoff → Guidance consumer → durable ConsumerAck
                                               ↘ runtime inventory evidence
```

核心裁决：

1. C0 contract bundle 是共享 wire schema 的唯一真源；formula/custom 不复制接口。
2. catalog 与 runtime inventory 分域、materialize、不可变；请求路径只读取 snapshot/索引，不全目录扫描。
3. standard exact 只认 active publication；模板和 legacy static 只进入 candidate/review pipeline。
4. `primary_source_kind + overlays[] + extraction_source` 与 resolution/completion 正交。
5. C2 milestone 绑定 cutoff，后续变化只更新持续健康并申请 reevaluation。
6. custom finalize 是 visibility saga，不宣称跨系统事务。

## 1. Normative C0 Contract Bundle

公共模块是 `G-C0` 唯一规范来源。下面是 wire 语义；具体语言绑定必须由同一 schema 生成或 conformance 验证。

### 1.1 GuidanceSection 与 SourceRef

```ts
type GuidanceSectionKey =
  | 'purpose' | 'materials' | 'data_sources' | 'steps' | 'formulas'
  | 'judgments' | 'evidence' | 'common_errors' | 'completion'

type SourceLocator =
  | { kind: 'xlsx'; templateLineageId: string; templateVersionId: string; path: string; sheetUid: string; range: string }
  | { kind: 'docx'; templateLineageId: string; templateVersionId: string; path: string; anchor: DocxAnchor }
  | { kind: 'bcd_markdown'; path: string; headingPath: string[]; anchor: string }
  | { kind: 'methodology_publication'; publicationId: string; version: number; sectionKey: GuidanceSectionKey }
  | { kind: 'project_evidence'; projectId: string; evidenceId: string; revision: string }
  | { kind: 'custom_artifact'; authorityId: string; artifactSha256: string; sheetUid: string; locator: string }

interface SourceRef {
  contractVersion: '1.0'
  refId: string
  locator: SourceLocator
  authorityDigest: string
  contentDigest: string
}

interface GuidanceSection {
  contractVersion: '1.0'
  key: GuidanceSectionKey
  title: string
  content: string
  sourceRefs: SourceRef[]
}
```

Locator kind 只描述“如何定位”。`custom_candidate/custom_confirmed` 是来源生命周期，绝不作为 locator kind。

### 1.2 TemplateAuthorityIdentity

```ts
type TemplateAuthorityIdentity =
  | {
      contractVersion: '1.0'
      phase: 'candidate'
      scope: 'organization' | 'project'
      organizationId: string
      projectId: string | null
      candidateId: string
      candidateRevision: string
      workbookLineageId: string
      artifactSha256: string
      policyVersion: string
    }
  | {
      contractVersion: '1.0'
      phase: 'finalized'
      scope: 'organization' | 'project'
      organizationId: string
      projectId: string | null
      templateId: string
      templateVersionId: string
      finalizationId: string
      workbookLineageId: string
      artifactSha256: string
      policyVersion: string
      manifestVersion: string
    }
```

Candidate identity 不伪造 template/finalization 字段；finalized identity 不再引用 mutable candidate revision 作为当前 authority。

### 1.3 CanonicalWorkpaperLocation

```ts
type StableLocationAnchor =
  | { kind: 'page' }
  | { kind: 'sheet'; sheetUid: string; sheetCode: string | null }
  | { kind: 'section'; sheetUid: string | null; sectionId: string }
  | { kind: 'cell'; sheetUid: string; addrId: string | null; rowKey: string | null; columnKey: string | null; a1: string | null }
  | { kind: 'document'; anchorId: string | null }
  | { kind: 'whole_workbook' }

interface CanonicalWorkpaperLocation {
  contractVersion: '1.0'
  organizationId: string
  projectId: string
  fiscalYear: number
  wpId: string
  wpCode: string
  entryId: string | null
  host: 'html' | 'univer' | 'onlyoffice' | 'grid' | 'word'
  anchor: StableLocationAnchor
  display: { sheetName: string | null; sectionLabel: string | null }
  ownerEpoch: number
  contextRevision: number
}
```

`display` 永不承担 identity。Formula spec 拥有 runtime state/reducer/provider；本 bundle 只定义 ready snapshot 的 wire contract。

### 1.4 EvidenceEnvelope subject union

```ts
type EvidenceSubject =
  | { kind: 'contract'; contractId: string }
  | { kind: 'catalog_entry'; templateLineageId: string; templateVersionId: string; wpCode: string; sheetUid: string | null }
  | { kind: 'runtime_entry'; organizationId: string; projectId: string; wpId: string; entryId: string; sheetUid: string | null }
  | { kind: 'operation'; organizationId: string; projectId: string | null; operationId: string }

interface EvidenceEnvelope {
  contractVersion: '1.0'
  evidenceId: string
  runId: string
  subject: EvidenceSubject
  contractVersions: Record<string, string>
  inventoryDigest: string | null
  sourceDigests: Record<string, string>
  operationIds: Record<string, string>
  artifacts: Array<{ kind: 'trace' | 'screenshot' | 'report' | 'mutation'; uri: string; sha256: string }>
  verdict: 'PASS' | 'FAIL' | 'BLOCKED' | 'STALE'
  recordedAt: string
}
```

organization 级 contract/finalization evidence 通过 subject 表达，不伪造 project/wp。

### 1.5 Candidate/finalized handoff 与 ConsumerAck

```ts
interface CustomGuidanceHandoffBase {
  contractVersion: '1.0'
  handoffId: string
  organizationId: string
  projectId: string | null
  wpId: string | null
  wpCode: string
  entryId: string
  sheetUid: string
  sheetCode: string | null
  mappingVersion: string
  formulaBoundaryVersion: string
  guidanceRevision: string
  sections: GuidanceSection[]
  staleFingerprint: string
  supersedes: string | null
  evidence: EvidenceEnvelope
}

type CustomGuidanceHandoff =
  | (CustomGuidanceHandoffBase & {
      phase: 'candidate'
      authority: Extract<TemplateAuthorityIdentity, { phase: 'candidate' }>
      submittedBy: string
      submittedAt: string
    })
  | (CustomGuidanceHandoffBase & {
      phase: 'finalized'
      authority: Extract<TemplateAuthorityIdentity, { phase: 'finalized' }>
      finalizationId: string
      confirmedBy: string
      confirmedAt: string
    })

interface ConsumerAck {
  contractVersion: '1.0'
  ackId: string
  handoffId: string
  handoffDigest: string
  consumer: 'guidance' | 'renderer' | 'public_shell' | 'entry_namespace'
  consumerVersion: string
  verdict: 'ACCEPTED' | 'REJECTED'
  validatedDigests: Record<string, string>
  reasonCodes: string[]
  recordedAt: string
}
```

ACK ledger 对 `(handoffId, handoffDigest, consumer, consumerVersion)` 幂等且 durable。

### 1.6 GuidanceRailAdapter

```ts
interface GuidanceRailAdapter {
  contractVersion: '1.0'
  id: 'guidance'
  visible: boolean
  disabledReason: string | null
  location: CanonicalWorkpaperLocation
  guidanceVersion: string | null
  hasDraft: boolean
  open(): void | Promise<void>
  close(options: { preserveDraft: boolean }): void | Promise<void>
}
```

Adapter 不拥有 DOM/CSS placement。`F-SHELL` 是唯一 shell owner。

### 1.7 Compatibility matrix

| Producer → Consumer | 1.x consumer | unknown major | missing required capability |
|---|---|---|---|
| `G-C0` location/evidence/section/ref | 接受已声明 minor | BLOCKED | BLOCKED |
| custom candidate handoff | 仅 review_pending | BLOCKED | REJECTED ACK |
| custom finalized handoff | 可进入完整验证 | BLOCKED | REJECTED ACK |
| rail adapter → shell | capability negotiation | 不挂载 | disabled reason |

Canonical fixtures 必须覆盖 organization/project scope、whole workbook、candidate/finalized、accepted/rejected ACK。

## 2. Identity and Inventory Architecture

### 2.1 Catalog inventory

```python
@dataclass(frozen=True)
class CatalogEntryKey:
    template_lineage_id: str
    template_version_id: str
    wp_code: str
    sheet_uid: str | None
```

输入：template finder/index/override、render-config facts、publication repository、custom-blank registry。显示名称和顺序是属性，不是 key。

### 2.2 Runtime inventory

```python
@dataclass(frozen=True)
class RuntimeEntryKey:
    organization_id: str
    project_id: str
    wp_id: str
    entry_id: str
    sheet_uid: str | None
```

运行态 entry 引用 catalog key 或 finalized custom authority。custom 创建、升级、回滚、withdraw 通过 event/outbox 更新 runtime projection。

### 2.3 Materialized snapshots

```python
@dataclass(frozen=True)
class GuidanceInventorySnapshot:
    run_id: str
    scope: Literal["catalog", "runtime"]
    cutoff_at: datetime
    input_digests: Mapping[str, str]
    entries: tuple[GuidanceInventoryEntry, ...]
    inventory_digest: str
```

Snapshot 一经写入不可变。读取 API 使用 latest pointer + digest-addressed bounded cache；source 变化创建新 run，不修改旧 run。请求路径禁止全目录扫描。

## 3. Provenance and State Model

```ts
type PrimarySourceKind = 'methodology_publication' | 'custom_confirmed' | 'none'
type OverlayKind = 'project_supplement'
type ExtractionSourceKind = 'template_candidate' | 'legacy_candidate' | 'custom_candidate' | 'none'
type ResolutionStatus = 'exact' | 'parent_inherited' | 'typed_fallback' | 'generic_fallback' | 'missing' | 'invalid' | 'stale' | 'not_applicable'
type CompletionStatus = 'complete' | 'review_pending' | 'required_pending' | 'blocked' | 'exempted' | 'out_of_scope'
```

`GuidanceProvenance`：

```ts
interface GuidanceProvenance {
  primarySourceKind: PrimarySourceKind
  primarySourceId: string | null
  overlays: Array<{ kind: OverlayKind; id: string; version: string }>
  extractionSource: { kind: ExtractionSourceKind; id: string; digest: string } | null
}
```

Pure evaluator 规则：

```text
complete ⇔ required
        ∧ resolution=exact
        ∧ primary source active/ACK-valid
        ∧ all 9 sections unique and non-empty
        ∧ every SourceRef valid for current authority
        ∧ no unresolved blocker
```

Candidate、legacy static、template extract、parent inheritance、fallback 都不能 complete。Supplement 可增加项目上下文，但不能修复 canonical required 缺段。

## 4. Denominator, Milestones and Health

对 entry id 集合核算：

```text
gross_required = complete ⊎ pending ⊎ blocked ⊎ valid_exempted
effective_required = gross_required - valid_exempted
PASS ⇔ complete = effective_required ∧ pending = ∅ ∧ blocked = ∅
```

`ExemptionRecord` 绑定 entry ids、scope、reason、owner、reviewer、source digest、approved/expires timestamps。过期或 digest 变化时在新 snapshot 中归 pending。

- **C1Milestone**：固定 catalog run，origin 为 standard/custom_blank。
- **C2Milestone**：固定 runtime run、scope 和 cutoff；依赖 C1、`X-HANDOFF-CONFORMANCE` 与 `X-RUNTIME-EVIDENCE`。
- **platform_guidance_health**：面向 latest runtime snapshot 的持续状态 `HEALTHY/DEGRADED/BLOCKED`。新 entry 或 stale 事件可使它降级并发出 `C2_REEVALUATION_REQUESTED`，但不修改历史 C2。

## 5. SourceRef Registry

`SourceRefRegistry` 是 locator 有效性的唯一判据：

```python
class SourceRefHandler(Protocol):
    kind: str
    def validate(self, ref: SourceRef, authority: AuthorityContext) -> SourceRefResult: ...
    def fingerprint(self, ref: SourceRef, authority: AuthorityContext) -> str: ...
```

规则：

- repository path 统一 POSIX 相对路径；绝对路径、UNC、`..`、symlink escape 拒绝；
- xlsx 必须使用 stable sheet uid + 有界 A1 range，范围须存在；
- docx anchor 必须唯一；
- BCD heading path/anchor 必须唯一；
- publication ref 必须指向 active/指定 immutable version；
- project evidence 先过 project visibility；
- custom artifact 只暴露 authority/artifact/sheet/locator，不暴露物理 storage path；
- digest、authority、withdraw、supersede、range/anchor 变化产生 invalid/stale，不 fallback 成“路径存在”。

## 6. Publication and Supplement

`GuidancePublication` 保存 immutable version、九段 sections、refs、source digests、review records 与状态。流程：

```text
extraction/legacy candidate → draft → independent review → immutable published
                                               ↘ rejected/rework
published → superseded / withdrawn → optional restore as new decision event
```

`ProjectGuidanceSupplement` 绑定 project/runtime entry/base publication/version/section，独立版本和权限。Response 分别返回 base 与 overlays provenance。

发布、撤回、恢复、supplement 变更写 audit/outbox，并使 inventory/response fingerprint stale。Legacy JSON 通过 migration importer 进入 draft，不直接成为运行时 exact。

## 7. Authoritative Resolution

```text
validate requested runtime/catalog identity
  → resolve_authoritative_exact(requested)
       ├─ active methodology publication → exact
       ├─ durable custom-confirmed ACK → exact
       └─ none/invalid/stale
  → parent authoritative exact
  → typed fallback
  → generic fallback
```

模板、docx、BCD 和 legacy static extraction 只为 review pipeline 产 candidate。它们可在管理界面预览，不在普通 endpoint 伪装 exact。

Response：

```ts
interface GuidanceResponse {
  contractVersion: '1.0'
  schemaVersion: string
  subject: EvidenceSubject
  requestedIdentity: object
  resolvedIdentity: object
  inherited: boolean
  provenance: GuidanceProvenance
  resolutionStatus: ResolutionStatus
  completionStatus: CompletionStatus
  resolutionReasons: string[]
  sections: GuidanceSection[]
  missingSections: GuidanceSectionKey[]
  version: string
  sourceDigest: string
  inventoryDigest: string
  generatedAt: string
}
```

## 8. Template, Sheet and Location Integration

Template authority 统一来自 `wp_template_finder`/index/override。Render-config 下发 template lineage/version、sheet uid/code 或 null reason。HTML/Univer/OnlyOffice host event 先生成稳定 location input，再由 formula spec runtime owner 归一为 `CanonicalWorkpaperLocation`。

- HTML：initial/deep-link/tab/navigate/locate/section 走同一 emitter；
- Univer：engine sheet id 映射 stable uid/code，native/custom/locate 汇流；
- OnlyOffice：外层单 sheet 用外层 identity；整册无可靠事件时使用 whole-workbook；
- 禁止名称 regex、数组下标、轮询、iframe DOM 穿透和伪事件。

## 9. API, Cache and Concurrency

服务端 response fingerprint 覆盖：subject、inventory digest、publication/custom authority、supplements、refs、questions/complexity、schema/contract version。Stable cache key 不含 `contextRevision`。

前端 key：

```text
projectId | wpId | entryId | stable sheet-or-whole identity | schemaVersion
```

`ownerEpoch/contextRevision` 只用于拒绝旧 async result。`setContext()` 是唯一 fetch owner：abort → clear data/AI/tab → optional short-TTL preview → ETag revalidate → identity/epoch/revision gate。

## 10. UI and Rail

UI 分层显示 primary source、overlays、extraction candidate、resolution、completion、publication/ACK/version、refs 和 missing sections。不可信内容统一 sanitize，失败退纯文本。

Guidance panel 删除旧内嵌 AI 和 fixed offset，只发布 `GuidanceRailAdapter`。`F-SHELL` 负责 trigger order、DOM、top/right/z-index、responsive panel、单展开和焦点管理。

## 11. Custom Handoff Consumer and Saga

Consumer pipeline：

```text
schema/major
 → phase discriminator
 → TemplateAuthorityIdentity
 → artifact + mapping + formula-boundary + guidance digests
 → nine sections
 → SourceRef registry
 → runtime membership projection
 → durable ConsumerAck
```

Candidate 只创建 review projection。Finalized handoff ACCEPTED 后，custom producer才能在自身 commit-visibility transaction 中把 version/entries 从 PENDING 切 ACTIVE。ACK rejected/timeout 时 visibility=0；重试复用 handoff digest 和 ack ledger。

这是一条 saga：immutable bytes/staged metadata → pending visibility → external ACKs → producer commit visibility；失败走 compensation，不宣称跨服务 ACID。

## 12. Error and Permission Model

读取先过 working-paper/project visibility。Publication、review、supplement、exemption、handoff consumer 各有服务端 capability。错误以 code/subject/operation/correlation 呈现；日志不含 token、正文或附件。

Broad `except` 只能转换为 explicit blocked/error，不得继续 success。打开中的 panel 在 capability 变化时 revalidate。

## 13. Ownership and External Milestones

| Concern / milestone | Owner | Consumers |
|---|---|---|
| `G-C0` shared wire bundle | guidance | formula `F1`、custom `X2` |
| `G-ID` template/sheet identity | guidance | formula location runtime、custom manifest |
| `G-RAIL` GuidanceRailAdapter behavior | guidance | formula integration closure |
| `F-SHELL` runtime location + public shell | formula | guidance browser integration、custom UI/runtime |
| `G-HANDOFF-CONSUMER` | guidance | custom finalize saga |
| `X-HANDOFF-CONFORMANCE` | custom | guidance Task 22 |
| `X-RUNTIME-EVIDENCE` | custom | guidance Task 23/health |

不存在 `X → G23 → X`：custom 只发布 conformance/runtime evidence，不等待 guidance C2 PASS。

## 14. Correctness Properties

### Property 1: C0 bundle 单源且未知 major fail-closed
**Validates: Requirements 1.1, 1.2, 1.5, 1.6**

### Property 2: Evidence subject 与 handoff 判别联合不会伪造不适用字段
**Validates: Requirements 1.3, 1.4**

### Property 3: catalog/runtime identity 稳定且 snapshots 不可变
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

### Property 4: gross/effective denominator 无遗漏无重复
**Validates: Requirements 3.1, 3.2, 3.3**

### Property 5: C1/C2 与持续健康互不篡改
**Validates: Requirements 3.4, 3.5, 3.6**

### Property 6: provenance、resolution、completion 三轴组合合法
**Validates: Requirements 4.1, 4.2, 4.4, 4.5, 4.6**

### Property 7: extraction candidate 永不成为 authoritative exact
**Validates: Requirements 4.3, 6.1, 7.3, 7.5**

### Property 8: authoritative exact 九段唯一且 refs 全有效
**Validates: Requirements 5.1, 5.2, 5.6**

### Property 9: SourceRef registry 对全部 locator kind fail-closed
**Validates: Requirements 5.3, 5.4, 5.5**

### Property 10: publication immutable，supplement 不改 canonical authority
**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

### Property 11: publication/supplement capability 由服务端强制
**Validates: Requirements 6.6, 12.2, 12.3**

### Property 12: child exact 与 parent authoritative chain 符合真实 authority
**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.6**

### Property 13: template/sheet identity 与 renderer authority 同源
**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**

### Property 14: response/cache 隔离且单 context 单请求
**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

### Property 15: 所有失败结构化可见且不会成功态放行
**Validates: Requirements 9.6, 12.1, 12.4, 12.5**

### Property 16: 三宿主始终发布最后一个可证明 location
**Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6**

### Property 17: guidance UI 三轴诚实且不执行不可信内容
**Validates: Requirements 11.1, 11.2, 11.3, 11.4**

### Property 18: rail adapter 不争夺公共 shell DOM/CSS
**Validates: Requirements 11.5, 11.6**

### Property 19: candidate/finalized handoff 与 durable ACK 状态一致
**Validates: Requirements 13.1, 13.2, 13.3, 13.4**

### Property 20: finalize visibility saga 永不暴露未 ACK entry
**Validates: Requirements 13.5, 13.6, 13.7**

### Property 21: contract/data/service/frontend行为守卫覆盖真实消费链
**Validates: Requirements 14.1, 14.2, 14.3**

### Property 22: 每个关键守卫变异后准确 RED
**Validates: Requirements 14.4**

### Property 23: 浏览器 evidence 绑定真实 subject/version/inventory
**Validates: Requirements 14.5, 14.6**

### Property 24: WIP 与外部里程碑均显式归因
**Validates: Requirements 15.1, 15.2, 15.3**

### Property 25: C1 只在 catalog effective denominator 全完成时成立
**Validates: Requirements 15.4**

### Property 26: C2 milestone 不被 cutoff 后事件改写
**Validates: Requirements 15.5**

### Property 27: closure 需要 tracked、可复现的全链证据
**Validates: Requirements 15.6**

## 15. Testing Strategy

| 层 | 重点 |
|---|---|
| Contract | C0 schema、fixtures、major/minor matrix、candidate/finalized、subject union、ACK |
| Inventory | catalog/runtime key、snapshot digest、stale、gross/effective accounting、C1/C2/health |
| Registry | 六类 locator 的真实 authority/digest/boundary 行为 |
| Publication | immutable lifecycle、review capability、supplement precedence、withdraw/stale |
| Resolution/API | child exact、parent chain、candidate 非 exact、membership、structured errors、ETag/cache |
| Host/store/UI | HTML/Univer/OO context、single fetch、race gate、三轴 UI、sanitize、rail adapter |
| Custom consumer | candidate review、finalized validation、ACK idempotency、visibility saga |
| Mutation | 单点破坏并区分 RED/GREEN/ANCHOR-MISS/WRONG-TEST |
| Browser | 三宿主、权限、切页、publication/supplement、F-SHELL adapter、trace/network/console |

Mutation harness 先校验单一锚点并保存 pristine bytes，finally 全字节恢复。历史测试数字、字符串存在、HTTP 200 或未跟踪 evidence 均不计完成。

## Non-Goals

- 不实现公式 provider、公式保存 API 或公共 shell DOM；
- 不实现自定义 workbook ingestion、projection 或 durable sync；
- 不伪造 OnlyOffice 原生 sheet 事件；
- 不用 AI 自动发布缺失九段；
- 不保留 legacy `exact_status`/static exact 作为第二运行时真源。
