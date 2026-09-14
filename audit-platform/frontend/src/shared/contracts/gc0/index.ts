/**
 * G-C0 shared wire contract bundle — frontend TS bindings.
 *
 * Mirror of `backend/data/guidance/contracts/gc0/schema.json` and
 * `backend/app/services/guidance_gc0_contract.py`. Downstream specs (F1
 * formula toolbar, X2 custom Excel ingestion) MUST import these types
 * from this module — no local re-declarations allowed (Req 1.2 of the
 * workpaper-guidance-content-closure spec).
 *
 * This file is the single TS-side truth for the eight C0 top-level
 * types and the three discriminator unions. Schema, matrix and fixtures
 * are the source of truth on the backend; this module mirrors them and
 * is verified against them by
 * `backend/tests/test_guidance_gc0_conformance.py` (reverse-dup scan).
 */

export const GC0_CONTRACT_ID = 'G-C0' as const;
export const GC0_CONTRACT_VERSION = '1.0' as const;

/** The eight top-level wire types downstream specs must import (never redeclare). */
export const GC0_TOP_LEVEL_TYPES: readonly [
  'CanonicalWorkpaperLocation',
  'GuidanceSection',
  'SourceRef',
  'TemplateAuthorityIdentity',
  'CustomGuidanceHandoff',
  'ConsumerAck',
  'GuidanceRailAdapter',
  'EvidenceEnvelope',
] = [
  'CanonicalWorkpaperLocation',
  'GuidanceSection',
  'SourceRef',
  'TemplateAuthorityIdentity',
  'CustomGuidanceHandoff',
  'ConsumerAck',
  'GuidanceRailAdapter',
  'EvidenceEnvelope',
];

export type GC0TopLevelTypeName = (typeof GC0_TOP_LEVEL_TYPES)[number];

/**
 * The five discriminator unions and their variants. Kept in lockstep with
 * `GC0_DISCRIMINATORS` in `guidance_gc0_contract.py` and with the
 * `discriminators` block in `schema.json`.
 */
export const GC0_DISCRIMINATORS = {
  'EvidenceSubject.kind': [
    'contract',
    'catalog_entry',
    'runtime_entry',
    'operation',
  ] as const,
  'StableLocationAnchor.kind': [
    'page',
    'sheet',
    'section',
    'cell',
    'document',
    'whole_workbook',
  ] as const,
  'SourceLocator.kind': [
    'xlsx',
    'docx',
    'bcd_markdown',
    'methodology_publication',
    'project_evidence',
    'custom_artifact',
  ] as const,
  'TemplateAuthorityIdentity.phase': ['candidate', 'finalized'] as const,
  'CustomGuidanceHandoff.phase': ['candidate', 'finalized'] as const,
} as const;

export type GC0DiscriminatorKey = keyof typeof GC0_DISCRIMINATORS;

// ---------------------------------------------------------------------------
// Primitives / enums
// ---------------------------------------------------------------------------

export type GuidanceSectionKey =
  | 'purpose'
  | 'materials'
  | 'data_sources'
  | 'steps'
  | 'formulas'
  | 'judgments'
  | 'evidence'
  | 'common_errors'
  | 'completion';

// ---------------------------------------------------------------------------
// SourceLocator union (Req 5.2, design §1.1)
// ---------------------------------------------------------------------------

export interface DocxAnchor {
  kind: 'bookmark' | 'heading' | 'paragraph_hash';
  value: string;
}

export interface SourceLocatorXlsx {
  kind: 'xlsx';
  templateLineageId: string;
  templateVersionId: string;
  path: string;
  sheetUid: string;
  /** A1 bounded range, e.g. `A1`, `A1:B10`. */
  range: string;
}

export interface SourceLocatorDocx {
  kind: 'docx';
  templateLineageId: string;
  templateVersionId: string;
  path: string;
  anchor: DocxAnchor;
}

export interface SourceLocatorBcdMarkdown {
  kind: 'bcd_markdown';
  path: string;
  headingPath: string[];
  anchor: string;
}

export interface SourceLocatorMethodologyPublication {
  /** Authoritative exact can ONLY come from an active methodology_publication (Req 4.3). */
  kind: 'methodology_publication';
  publicationId: string;
  version: number;
  sectionKey: GuidanceSectionKey;
}

export interface SourceLocatorProjectEvidence {
  kind: 'project_evidence';
  projectId: string;
  evidenceId: string;
  revision: string;
}

export interface SourceLocatorCustomArtifact {
  /** Never exposes physical storage path; only authorityId + artifactSha256 + sheetUid + logical locator. */
  kind: 'custom_artifact';
  authorityId: string;
  artifactSha256: string;
  sheetUid: string;
  locator: string;
}

/** Discriminator = `kind`. Six variants. */
export type SourceLocator =
  | SourceLocatorXlsx
  | SourceLocatorDocx
  | SourceLocatorBcdMarkdown
  | SourceLocatorMethodologyPublication
  | SourceLocatorProjectEvidence
  | SourceLocatorCustomArtifact;

// ---------------------------------------------------------------------------
// SourceRef
// ---------------------------------------------------------------------------

export interface SourceRef {
  contractVersion: typeof GC0_CONTRACT_VERSION;
  refId: string;
  locator: SourceLocator;
  authorityDigest: string;
  contentDigest: string;
}

// ---------------------------------------------------------------------------
// GuidanceSection
// ---------------------------------------------------------------------------

export interface GuidanceSection {
  contractVersion: typeof GC0_CONTRACT_VERSION;
  key: GuidanceSectionKey;
  title: string;
  content: string;
  sourceRefs: SourceRef[];
}

// ---------------------------------------------------------------------------
// TemplateAuthorityIdentity (candidate | finalized)
// ---------------------------------------------------------------------------

export interface TemplateAuthorityIdentityCandidate {
  contractVersion: typeof GC0_CONTRACT_VERSION;
  phase: 'candidate';
  scope: 'organization' | 'project';
  organizationId: string;
  projectId: string | null;
  candidateId: string;
  candidateRevision: string;
  workbookLineageId: string;
  artifactSha256: string;
  policyVersion: string;
}

export interface TemplateAuthorityIdentityFinalized {
  contractVersion: typeof GC0_CONTRACT_VERSION;
  phase: 'finalized';
  scope: 'organization' | 'project';
  organizationId: string;
  projectId: string | null;
  templateId: string;
  templateVersionId: string;
  finalizationId: string;
  workbookLineageId: string;
  artifactSha256: string;
  policyVersion: string;
  manifestVersion: string;
}

/** Discriminator = `phase`. Candidate MUST NOT carry template/finalization fields (Req 1.4). */
export type TemplateAuthorityIdentity =
  | TemplateAuthorityIdentityCandidate
  | TemplateAuthorityIdentityFinalized;

// ---------------------------------------------------------------------------
// StableLocationAnchor union
// ---------------------------------------------------------------------------

export interface AnchorPage {
  kind: 'page';
}
export interface AnchorSheet {
  kind: 'sheet';
  sheetUid: string;
  sheetCode: string | null;
}
export interface AnchorSection {
  kind: 'section';
  sheetUid: string | null;
  sectionId: string;
}
export interface AnchorCell {
  kind: 'cell';
  sheetUid: string;
  addrId: string | null;
  rowKey: string | null;
  columnKey: string | null;
  a1: string | null;
}
export interface AnchorDocument {
  kind: 'document';
  anchorId: string | null;
}
export interface AnchorWholeWorkbook {
  kind: 'whole_workbook';
}

/** Discriminator = `kind`. Six variants. */
export type StableLocationAnchor =
  | AnchorPage
  | AnchorSheet
  | AnchorSection
  | AnchorCell
  | AnchorDocument
  | AnchorWholeWorkbook;

// ---------------------------------------------------------------------------
// CanonicalWorkpaperLocation
// ---------------------------------------------------------------------------

export type WorkpaperHost = 'html' | 'univer' | 'onlyoffice' | 'grid' | 'word';

export interface CanonicalWorkpaperLocation {
  contractVersion: typeof GC0_CONTRACT_VERSION;
  organizationId: string;
  projectId: string;
  fiscalYear: number;
  wpId: string;
  wpCode: string;
  entryId: string | null;
  host: WorkpaperHost;
  anchor: StableLocationAnchor;
  /** Presentation-only. Never used for identity. */
  display: { sheetName: string | null; sectionLabel: string | null };
  ownerEpoch: number;
  contextRevision: number;
}

// ---------------------------------------------------------------------------
// EvidenceEnvelope + EvidenceSubject union
// ---------------------------------------------------------------------------

export interface EvidenceSubjectContract {
  kind: 'contract';
  contractId: string;
}
export interface EvidenceSubjectCatalogEntry {
  kind: 'catalog_entry';
  templateLineageId: string;
  templateVersionId: string;
  wpCode: string;
  sheetUid: string | null;
}
export interface EvidenceSubjectRuntimeEntry {
  kind: 'runtime_entry';
  organizationId: string;
  projectId: string;
  wpId: string;
  entryId: string;
  sheetUid: string | null;
}
export interface EvidenceSubjectOperation {
  kind: 'operation';
  organizationId: string;
  projectId: string | null;
  operationId: string;
}

/**
 * Discriminator = `kind`.
 *
 * Organization-level contract/finalization evidence MUST use `contract`
 * variant — never fabricate `projectId`/`wpId` (Req 1.3).
 */
export type EvidenceSubject =
  | EvidenceSubjectContract
  | EvidenceSubjectCatalogEntry
  | EvidenceSubjectRuntimeEntry
  | EvidenceSubjectOperation;

export interface EvidenceArtifact {
  kind: 'trace' | 'screenshot' | 'report' | 'mutation';
  uri: string;
  sha256: string;
}

export type EvidenceVerdict = 'PASS' | 'FAIL' | 'BLOCKED' | 'STALE';

export interface EvidenceEnvelope {
  contractVersion: typeof GC0_CONTRACT_VERSION;
  evidenceId: string;
  runId: string;
  subject: EvidenceSubject;
  contractVersions: Record<string, string>;
  inventoryDigest: string | null;
  sourceDigests: Record<string, string>;
  operationIds: Record<string, string>;
  artifacts: EvidenceArtifact[];
  verdict: EvidenceVerdict;
  recordedAt: string;
}

// ---------------------------------------------------------------------------
// CustomGuidanceHandoff (candidate | finalized)
// ---------------------------------------------------------------------------

export interface CustomGuidanceHandoffBase {
  contractVersion: typeof GC0_CONTRACT_VERSION;
  handoffId: string;
  organizationId: string;
  projectId: string | null;
  wpId: string | null;
  wpCode: string;
  entryId: string;
  sheetUid: string;
  sheetCode: string | null;
  mappingVersion: string;
  formulaBoundaryVersion: string;
  guidanceRevision: string;
  sections: GuidanceSection[];
  staleFingerprint: string;
  supersedes: string | null;
  evidence: EvidenceEnvelope;
}

export interface CustomGuidanceHandoffCandidate
  extends CustomGuidanceHandoffBase {
  phase: 'candidate';
  authority: TemplateAuthorityIdentityCandidate;
  submittedBy: string;
  submittedAt: string;
}

export interface CustomGuidanceHandoffFinalized
  extends CustomGuidanceHandoffBase {
  phase: 'finalized';
  authority: TemplateAuthorityIdentityFinalized;
  finalizationId: string;
  confirmedBy: string;
  confirmedAt: string;
}

/** Discriminator = `phase`. */
export type CustomGuidanceHandoff =
  | CustomGuidanceHandoffCandidate
  | CustomGuidanceHandoffFinalized;

// ---------------------------------------------------------------------------
// ConsumerAck
// ---------------------------------------------------------------------------

export type ConsumerAckVerdict = 'ACCEPTED' | 'REJECTED';
export type ConsumerAckConsumer =
  | 'guidance'
  | 'renderer'
  | 'public_shell'
  | 'entry_namespace';

export interface ConsumerAck {
  contractVersion: typeof GC0_CONTRACT_VERSION;
  ackId: string;
  handoffId: string;
  handoffDigest: string;
  consumer: ConsumerAckConsumer;
  consumerVersion: string;
  verdict: ConsumerAckVerdict;
  validatedDigests: Record<string, string>;
  reasonCodes: string[];
  recordedAt: string;
}

// ---------------------------------------------------------------------------
// GuidanceRailAdapter
// ---------------------------------------------------------------------------

export interface GuidanceRailAdapter {
  contractVersion: typeof GC0_CONTRACT_VERSION;
  id: 'guidance';
  visible: boolean;
  disabledReason: string | null;
  location: CanonicalWorkpaperLocation;
  guidanceVersion: string | null;
  hasDraft: boolean;
  /** Signature: () => void | Promise<void>. */
  open: '() => void | Promise<void>';
  /** Signature: (options: { preserveDraft: boolean }) => void | Promise<void>. */
  close: '(options: { preserveDraft: boolean }) => void | Promise<void>';
}

// ---------------------------------------------------------------------------
// Type guards
// ---------------------------------------------------------------------------

export function isCandidateHandoff(payload: unknown): payload is CustomGuidanceHandoffCandidate {
  return (
    !!payload &&
    typeof payload === 'object' &&
    (payload as { phase?: unknown }).phase === 'candidate'
  );
}

export function isFinalizedHandoff(payload: unknown): payload is CustomGuidanceHandoffFinalized {
  return (
    !!payload &&
    typeof payload === 'object' &&
    (payload as { phase?: unknown }).phase === 'finalized'
  );
}

export function isCandidateAuthorityIdentity(
  payload: unknown,
): payload is TemplateAuthorityIdentityCandidate {
  return (
    !!payload &&
    typeof payload === 'object' &&
    (payload as { phase?: unknown }).phase === 'candidate'
  );
}

export function isFinalizedAuthorityIdentity(
  payload: unknown,
): payload is TemplateAuthorityIdentityFinalized {
  return (
    !!payload &&
    typeof payload === 'object' &&
    (payload as { phase?: unknown }).phase === 'finalized'
  );
}

export function isContractEvidenceSubject(subject: unknown): subject is EvidenceSubjectContract {
  return !!subject && typeof subject === 'object' && (subject as { kind?: unknown }).kind === 'contract';
}

export function isCatalogEntryEvidenceSubject(
  subject: unknown,
): subject is EvidenceSubjectCatalogEntry {
  return !!subject && typeof subject === 'object' && (subject as { kind?: unknown }).kind === 'catalog_entry';
}

export function isRuntimeEntryEvidenceSubject(
  subject: unknown,
): subject is EvidenceSubjectRuntimeEntry {
  return !!subject && typeof subject === 'object' && (subject as { kind?: unknown }).kind === 'runtime_entry';
}

export function isOperationEvidenceSubject(
  subject: unknown,
): subject is EvidenceSubjectOperation {
  return !!subject && typeof subject === 'object' && (subject as { kind?: unknown }).kind === 'operation';
}

export function isMethodologyPublicationLocator(
  locator: unknown,
): locator is SourceLocatorMethodologyPublication {
  return !!locator && typeof locator === 'object' && (locator as { kind?: unknown }).kind === 'methodology_publication';
}

// ---------------------------------------------------------------------------
// Fail-closed compatibility guard
// ---------------------------------------------------------------------------

/**
 * Thin frontend wrapper around `validateContractVersion` in
 * `./compatibility.ts`. Kept here so downstream specs can
 * `import { validateContractVersion } from '@/shared/contracts/gc0'`.
 */
export {
  validateContractVersion,
  type CompatibilityDecision,
  type CompatibilityReason,
  type CompatibilityOutcome,
} from './compatibility';
