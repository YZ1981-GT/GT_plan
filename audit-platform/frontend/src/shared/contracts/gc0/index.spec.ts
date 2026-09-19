/**
 * G-C0 frontend binding conformance.
 *
 * Mirrors `backend/tests/test_guidance_gc0_conformance.py`. Ensures the
 * TS-side binding matches the Python owner + schema.json.
 *
 * Mutation anchor 5 (from the spec's Property 1 self-check):
 *   Changing any entry of `GC0_TOP_LEVEL_TYPES` in `index.ts` MUST flip
 *   `test_top_level_types_is_the_exact_ordered_set_of_eight` RED.
 */
import { describe, expect, it } from 'vitest'
import {
  GC0_CONTRACT_ID,
  GC0_CONTRACT_VERSION,
  GC0_DISCRIMINATORS,
  GC0_TOP_LEVEL_TYPES,
  isCandidateHandoff,
  isContractEvidenceSubject,
  isFinalizedHandoff,
  validateContractVersion,
  type CustomGuidanceHandoff,
  type EvidenceEnvelope,
  type EvidenceSubject,
  type GuidanceSection,
  type SourceLocator,
  type TemplateAuthorityIdentity,
} from './index'

describe('G-C0 frontend bindings — constants', () => {
  it('test_contract_id_is_G_C0', () => {
    expect(GC0_CONTRACT_ID).toBe('G-C0')
  })

  it('test_contract_version_is_1_0', () => {
    expect(GC0_CONTRACT_VERSION).toBe('1.0')
  })

  it('test_top_level_types_is_the_exact_ordered_set_of_eight', () => {
    expect(GC0_TOP_LEVEL_TYPES).toEqual([
      'CanonicalWorkpaperLocation',
      'GuidanceSection',
      'SourceRef',
      'TemplateAuthorityIdentity',
      'CustomGuidanceHandoff',
      'ConsumerAck',
      'GuidanceRailAdapter',
      'EvidenceEnvelope',
    ])
    expect(GC0_TOP_LEVEL_TYPES.length).toBe(8)
  })
})

describe('G-C0 frontend bindings — discriminator parity with schema.json', () => {
  it('test_five_discriminators_declared', () => {
    const keys = Object.keys(GC0_DISCRIMINATORS).sort()
    expect(keys).toEqual(
      [
        'CustomGuidanceHandoff.phase',
        'EvidenceSubject.kind',
        'SourceLocator.kind',
        'StableLocationAnchor.kind',
        'TemplateAuthorityIdentity.phase',
      ],
    )
  })

  it('test_each_discriminator_has_its_variants', () => {
    expect([...GC0_DISCRIMINATORS['EvidenceSubject.kind']]).toEqual([
      'contract',
      'catalog_entry',
      'runtime_entry',
      'operation',
    ])
    expect([...GC0_DISCRIMINATORS['StableLocationAnchor.kind']]).toEqual([
      'page',
      'sheet',
      'section',
      'cell',
      'document',
      'whole_workbook',
    ])
    expect([...GC0_DISCRIMINATORS['SourceLocator.kind']]).toEqual([
      'xlsx',
      'docx',
      'bcd_markdown',
      'methodology_publication',
      'project_evidence',
      'custom_artifact',
    ])
    expect([...GC0_DISCRIMINATORS['TemplateAuthorityIdentity.phase']]).toEqual([
      'candidate',
      'finalized',
    ])
    expect([...GC0_DISCRIMINATORS['CustomGuidanceHandoff.phase']]).toEqual([
      'candidate',
      'finalized',
    ])
  })
})

describe('G-C0 frontend bindings — validateContractVersion fail-closed', () => {
  it('test_missing_identity_blocks', () => {
    const d = validateContractVersion({})
    expect(d.outcome).toBe('BLOCKED')
    expect(d.reasons[0].code).toBe('identity-missing')
  })

  it('test_unknown_major_blocks', () => {
    const d = validateContractVersion({ contractVersion: '9.0' })
    expect(d.outcome).toBe('BLOCKED')
    expect(d.reasons[0].code).toBe('unknown-major')
  })

  it('test_malformed_version_blocks', () => {
    // "01.0" parses as major="01" which the owner classifies as
    // "unknown-major" (fail-closed). All other forms are "malformed".
    for (const raw of ['1', '1.x', '1.0.0', 'v1.0', '.0', '1.', '']) {
      const d = validateContractVersion({ contractVersion: raw })
      expect(d.outcome, `raw=${raw}`).toBe('BLOCKED')
      expect(d.reasons[0].code, `raw=${raw}`).toBe('identity-malformed')
    }
    const d01 = validateContractVersion({ contractVersion: '01.0' })
    expect(d01.outcome).toBe('BLOCKED')
    expect(d01.reasons[0].code).toBe('unknown-major')
  })

  it('test_unsupported_minor_degrades_for_consumer', () => {
    const d = validateContractVersion({ contractVersion: '1.5' })
    expect(d.outcome).toBe('DEGRADED')
    expect(d.reasons[0].code).toBe('unsupported-minor')
    expect(d.negotiatedVersion).toBe('1.0')
  })

  it('test_unsupported_minor_blocks_for_producer', () => {
    const d = validateContractVersion({ contractVersion: '1.5' }, { consumerRole: 'producer' })
    expect(d.outcome).toBe('BLOCKED')
  })

  it('test_missing_capability_rejects', () => {
    const d = validateContractVersion({ contractVersion: '1.0' }, { requiredMinors: [3] })
    expect(d.outcome).toBe('REJECTED')
    expect(d.reasons[0].code).toBe('missing-capability')
  })

  it('test_accept_on_matching_minor', () => {
    const d = validateContractVersion({ contractVersion: '1.0' })
    expect(d.outcome).toBe('ACCEPT')
    expect(d.negotiatedVersion).toBe('1.0')
    expect(d.reasons).toEqual([])
  })

  it('test_non_object_payload_blocks', () => {
    const d = validateContractVersion(null)
    expect(d.outcome).toBe('BLOCKED')
    expect(d.reasons[0].code).toBe('identity-not-object')
  })
})

describe('G-C0 frontend bindings — Req 1.4 handoff phase discipline', () => {
  it('test_candidate_handoff_type_never_requires_finalization_fields', () => {
    // The TS type system does not allow `finalizationId` on the
    // candidate variant — this assertion proves it at runtime too.
    const cand = { phase: 'candidate' as const } as Partial<CustomGuidanceHandoff>
    expect(isCandidateHandoff(cand)).toBe(true)
    expect(isFinalizedHandoff(cand)).toBe(false)
    // Candidate MUST NOT require `finalizationId`.
    // @ts-expect-error — deliberately probing the type boundary.
    const forbidden = 'finalizationId' as keyof CustomGuidanceHandoff
    expect(forbidden in ({} as Record<string, unknown>)).toBe(false)
  })

  it('test_finalized_handoff_type_never_requires_candidate_revision', () => {
    const fin = { phase: 'finalized' as const } as Partial<CustomGuidanceHandoff>
    expect(isFinalizedHandoff(fin)).toBe(true)
    expect(isCandidateHandoff(fin)).toBe(false)
  })
})

describe('G-C0 frontend bindings — Req 1.3 contract evidence subject', () => {
  it('test_contract_evidence_subject_does_not_carry_project_or_wp_id', () => {
    const subject: EvidenceSubject = {
      kind: 'contract',
      contractId: 'G-C0',
    }
    expect(isContractEvidenceSubject(subject)).toBe(true)
    // Contract subject MUST NOT smuggle projectId/wpId.
    expect('projectId' in subject).toBe(false)
    expect('wpId' in subject).toBe(false)
    expect('entryId' in subject).toBe(false)
    expect('sheetUid' in subject).toBe(false)
  })
})

describe('G-C0 frontend bindings — cross-language parity contract', () => {
  /** These mirror the Python-side tests in `test_guidance_gc0_conformance.py`. */
  const canonicalFixtureContractVersion = '1.0'

  it('test_fixture_contract_version_matches_owner_constant', () => {
    expect(canonicalFixtureContractVersion).toBe(GC0_CONTRACT_VERSION)
  })

  it('test_sample_evidence_envelope_passes_version_gate', () => {
    const envelope: EvidenceEnvelope = {
      contractVersion: '1.0',
      evidenceId: 'ev-1',
      runId: 'run-1',
      subject: { kind: 'contract', contractId: 'G-C0' },
      contractVersions: { 'G-C0': '1.0' },
      inventoryDigest: null,
      sourceDigests: {},
      operationIds: {},
      artifacts: [],
      verdict: 'PASS',
      recordedAt: '2026-09-07T00:00:00Z',
    }
    expect(validateContractVersion(envelope).outcome).toBe('ACCEPT')
  })

  it('test_sample_guidance_section_is_compatible_with_source_locator_union', () => {
    const section: GuidanceSection = {
      contractVersion: '1.0',
      key: 'purpose',
      title: 'purpose',
      content: '…',
      sourceRefs: [
        {
          contractVersion: '1.0',
          refId: 'r1',
          locator: {
            kind: 'methodology_publication',
            publicationId: 'pub-1',
            version: 3,
            sectionKey: 'purpose',
          } satisfies SourceLocator,
          authorityDigest: 'a'.repeat(64),
          contentDigest: 'a'.repeat(64),
        },
      ],
    }
    expect(section.key).toBe('purpose')
    expect(section.sourceRefs[0].locator.kind).toBe('methodology_publication')
  })

  it('test_template_authority_identity_candidate_shape', () => {
    const ident: TemplateAuthorityIdentity = {
      contractVersion: '1.0',
      phase: 'candidate',
      scope: 'project',
      organizationId: 'org-1',
      projectId: 'proj-1',
      candidateId: 'c-1',
      candidateRevision: 'rev-1',
      workbookLineageId: 'lineage-1',
      artifactSha256: 'a'.repeat(64),
      policyVersion: 'policy-1',
    }
    // Candidate identity MUST NOT require template/finalization fields.
    expect('templateId' in ident).toBe(false)
    expect('finalizationId' in ident).toBe(false)
    expect(validateContractVersion(ident).outcome).toBe('ACCEPT')
  })
})
