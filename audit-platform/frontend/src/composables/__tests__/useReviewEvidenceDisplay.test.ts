/**
 * useReviewEvidenceDisplay — Vitest tests（Task 6.5, Wave 5）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R9, R10, R12
 * Design: §4.6, §5.4
 *
 * Tests evidence display component behavior with mock API:
 * - Version/hash/OCR-AI confirmation/stale path/locator display
 * - Completion blocked status
 * - QC/EQCR evidence view computed properties
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useReviewEvidenceDisplay } from '../useReviewEvidenceDisplay'
import type { ReviewOpinionDisplay, CompletionBlockStatus } from '../useReviewEvidenceDisplay'

// ─── Mock http ───────────────────────────────────────────────────────────────

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import http from '@/utils/http'
const mockedHttp = http as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

// ─── Fixtures ────────────────────────────────────────────────────────────────

const SAMPLE_EVIDENCE_ITEM = {
  evidence_ref_id: 'ref-001',
  evidence_type: 'attachment_version',
  source_version: 3,
  content_hash: 'a'.repeat(64),
  ocr_confirmed: true,
  ocr_confirmation_at: '2025-06-01T10:00:00Z',
  ocr_confirmed_by: 'user-ocr',
  ai_confirmed: false,
  ai_confirmation_at: null,
  ai_confirmed_by: null,
  is_stale: false,
  stale_path: [],
  locator: 'storage://project/att/v3',
  locator_type: 'opaque' as const,
}

const SAMPLE_OPINION: ReviewOpinionDisplay = {
  opinion_id: 'opinion-001',
  status: 'closed',
  severity: 'high',
  content: '发现重大错报',
  created_by: 'user-creator',
  closed_by: 'user-closer',
  closing_explanation: '问题已解决',
  created_at: '2025-05-01T00:00:00Z',
  closed_at: '2025-06-01T00:00:00Z',
  evidence_items: [SAMPLE_EVIDENCE_ITEM],
}

const SAMPLE_STALE_OPINION: ReviewOpinionDisplay = {
  ...SAMPLE_OPINION,
  opinion_id: 'opinion-002',
  status: 're_review_required',
  evidence_items: [
    {
      ...SAMPLE_EVIDENCE_ITEM,
      is_stale: true,
      stale_path: ['node-1', 'node-2'],
    },
  ],
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('useReviewEvidenceDisplay', () => {
  const projectId = ref('project-001')
  const year = ref(2025)

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('loadOpinionEvidence', () => {
    it('loads opinion with full evidence display (R10.4)', async () => {
      mockedHttp.get.mockResolvedValueOnce({
        data: { data: SAMPLE_OPINION },
      })

      const { loadOpinionEvidence } = useReviewEvidenceDisplay(projectId, year)
      const result = await loadOpinionEvidence('opinion-001')

      expect(result).not.toBeNull()
      expect(result!.opinion_id).toBe('opinion-001')
      expect(result!.evidence_items).toHaveLength(1)

      const item = result!.evidence_items[0]
      // R10.4: shows source version
      expect(item.source_version).toBe(3)
      // R10.4: shows hash
      expect(item.content_hash).toBe('a'.repeat(64))
      // R10.4: shows OCR human confirmation record
      expect(item.ocr_confirmed).toBe(true)
      expect(item.ocr_confirmed_by).toBe('user-ocr')
      // R10.4: shows AI confirmation
      expect(item.ai_confirmed).toBe(false)
      // R10.4: shows stale status
      expect(item.is_stale).toBe(false)
      // R10.4: shows locatable reference (not just excerpt)
      expect(item.locator).toBe('storage://project/att/v3')
      expect(item.locator_type).toBe('opaque')
    })

    it('handles API error gracefully', async () => {
      mockedHttp.get.mockRejectedValueOnce({
        response: { data: { error_code: 'SCOPE_NOT_FOUND_OR_FORBIDDEN' } },
      })

      const { loadOpinionEvidence, error } = useReviewEvidenceDisplay(
        projectId,
        year
      )
      const result = await loadOpinionEvidence('opinion-999')

      expect(result).toBeNull()
      expect(error.value).toBe('目标不可访问')
    })
  })

  describe('loadTargetReviewEvidence', () => {
    it('loads all opinions for a target', async () => {
      mockedHttp.get.mockResolvedValueOnce({
        data: { data: { opinions: [SAMPLE_OPINION, SAMPLE_STALE_OPINION] } },
      })

      const { loadTargetReviewEvidence, opinions } =
        useReviewEvidenceDisplay(projectId, year)
      await loadTargetReviewEvidence({
        target_type: 'workpaper',
        target_id: 'wp-001',
      })

      expect(opinions.value).toHaveLength(2)
      expect(opinions.value[0].status).toBe('closed')
      expect(opinions.value[1].status).toBe('re_review_required')
    })
  })

  describe('checkCompletionBlocked', () => {
    it('returns blocked=true when re_review_required exists', async () => {
      const blockStatus: CompletionBlockStatus = {
        blocked: true,
        blocking_opinions: [
          {
            opinion_id: 'opinion-002',
            severity: 'high',
            status: 're_review_required',
            content: '证据已失效',
          },
        ],
      }
      mockedHttp.get.mockResolvedValueOnce({
        data: { data: blockStatus },
      })

      const { checkCompletionBlocked, isCompletionBlocked } =
        useReviewEvidenceDisplay(projectId, year)
      const result = await checkCompletionBlocked({
        target_type: 'workpaper',
        target_id: 'wp-001',
      })

      expect(result.blocked).toBe(true)
      expect(result.blocking_opinions).toHaveLength(1)
      expect(isCompletionBlocked.value).toBe(true)
    })

    it('returns blocked=false when all reviews resolved', async () => {
      mockedHttp.get.mockResolvedValueOnce({
        data: { data: { blocked: false, blocking_opinions: [] } },
      })

      const { checkCompletionBlocked, isCompletionBlocked } =
        useReviewEvidenceDisplay(projectId, year)
      await checkCompletionBlocked({
        target_type: 'workpaper',
        target_id: 'wp-001',
      })

      expect(isCompletionBlocked.value).toBe(false)
    })
  })

  describe('computed properties', () => {
    it('hasStaleEvidence detects stale items', async () => {
      mockedHttp.get.mockResolvedValueOnce({
        data: { data: { opinions: [SAMPLE_STALE_OPINION] } },
      })

      const { loadTargetReviewEvidence, hasStaleEvidence } =
        useReviewEvidenceDisplay(projectId, year)
      await loadTargetReviewEvidence({
        target_type: 'workpaper',
        target_id: 'wp-001',
      })

      expect(hasStaleEvidence.value).toBe(true)
    })

    it('hasStaleEvidence is false when no stale items', async () => {
      mockedHttp.get.mockResolvedValueOnce({
        data: { data: { opinions: [SAMPLE_OPINION] } },
      })

      const { loadTargetReviewEvidence, hasStaleEvidence } =
        useReviewEvidenceDisplay(projectId, year)
      await loadTargetReviewEvidence({
        target_type: 'workpaper',
        target_id: 'wp-001',
      })

      expect(hasStaleEvidence.value).toBe(false)
    })

    it('hasReReviewRequired detects re_review_required status', async () => {
      mockedHttp.get.mockResolvedValueOnce({
        data: { data: { opinions: [SAMPLE_STALE_OPINION] } },
      })

      const { loadTargetReviewEvidence, hasReReviewRequired } =
        useReviewEvidenceDisplay(projectId, year)
      await loadTargetReviewEvidence({
        target_type: 'workpaper',
        target_id: 'wp-001',
      })

      expect(hasReReviewRequired.value).toBe(true)
    })
  })

  describe('evidence display completeness (R10.4)', () => {
    it('displays all required fields: version, hash, confirmations, stale, locator', async () => {
      const fullOpinion: ReviewOpinionDisplay = {
        ...SAMPLE_OPINION,
        evidence_items: [
          {
            evidence_ref_id: 'ref-full',
            evidence_type: 'attachment_version',
            source_version: 5,
            content_hash: 'b'.repeat(64),
            ocr_confirmed: true,
            ocr_confirmation_at: '2025-03-15T08:00:00Z',
            ocr_confirmed_by: 'user-ocr-full',
            ai_confirmed: true,
            ai_confirmation_at: '2025-03-16T09:00:00Z',
            ai_confirmed_by: 'user-ai-full',
            is_stale: true,
            stale_path: ['attachment:v4', 'evidence_ref:ref-full'],
            locator: 'storage://project/att/v5/page3#region(100,200,300,400)',
            locator_type: 'page_region',
          },
        ],
      }
      mockedHttp.get.mockResolvedValueOnce({
        data: { data: fullOpinion },
      })

      const { loadOpinionEvidence } = useReviewEvidenceDisplay(projectId, year)
      const result = await loadOpinionEvidence('opinion-full')

      const item = result!.evidence_items[0]
      // Version
      expect(item.source_version).toBe(5)
      // Hash
      expect(item.content_hash).toHaveLength(64)
      // OCR human confirmation record
      expect(item.ocr_confirmed).toBe(true)
      expect(item.ocr_confirmation_at).toBe('2025-03-15T08:00:00Z')
      expect(item.ocr_confirmed_by).toBe('user-ocr-full')
      // AI confirmation
      expect(item.ai_confirmed).toBe(true)
      expect(item.ai_confirmation_at).toBe('2025-03-16T09:00:00Z')
      expect(item.ai_confirmed_by).toBe('user-ai-full')
      // Stale status + path
      expect(item.is_stale).toBe(true)
      expect(item.stale_path).toEqual(['attachment:v4', 'evidence_ref:ref-full'])
      // Locatable reference (not just excerpt)
      expect(item.locator).toContain('page3#region')
      expect(item.locator_type).toBe('page_region')
    })
  })
})
