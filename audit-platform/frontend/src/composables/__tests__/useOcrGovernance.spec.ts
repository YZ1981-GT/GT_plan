/**
 * useOcrGovernance — Vitest tests (Task 5.5, Wave 4)
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R5, R6, R12, R14
 *
 * Tests covering:
 * - API call construction (correct URLs, headers)
 * - Error handling (desensitized messages)
 * - Role-based UI state (buttons disabled for unauthorized roles)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// Mock http module
const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()

vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

import { useOcrGovernance } from '../useOcrGovernance'

describe('useOcrGovernance', () => {
  const projectId = 'proj-123'
  const year = 2025

  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ─── Role-Based UI State ─────────────────────────────────────────────

  describe('capability computed properties', () => {
    it('admin has all OCR capabilities', () => {
      const { canStartOcr, canRetryOcr, canConfirmOcr, canWritebackOcr } =
        useOcrGovernance(projectId, year, 'admin')

      expect(canStartOcr.value).toBe(true)
      expect(canRetryOcr.value).toBe(true)
      expect(canConfirmOcr.value).toBe(true)
      expect(canWritebackOcr.value).toBe(true)
    })

    it('auditor can start and confirm but not retry', () => {
      const { canStartOcr, canRetryOcr, canConfirmOcr, canWritebackOcr } =
        useOcrGovernance(projectId, year, 'auditor')

      expect(canStartOcr.value).toBe(true)
      expect(canRetryOcr.value).toBe(false)
      expect(canConfirmOcr.value).toBe(true)
      expect(canWritebackOcr.value).toBe(true)
    })

    it('manager can start, retry, confirm, and writeback', () => {
      const { canStartOcr, canRetryOcr, canConfirmOcr, canWritebackOcr } =
        useOcrGovernance(projectId, year, 'manager')

      expect(canStartOcr.value).toBe(true)
      expect(canRetryOcr.value).toBe(true)
      expect(canConfirmOcr.value).toBe(true)
      expect(canWritebackOcr.value).toBe(true)
    })

    it('qc has no OCR capabilities', () => {
      const { canStartOcr, canRetryOcr, canConfirmOcr, canWritebackOcr } =
        useOcrGovernance(projectId, year, 'qc')

      expect(canStartOcr.value).toBe(false)
      expect(canRetryOcr.value).toBe(false)
      expect(canConfirmOcr.value).toBe(false)
      expect(canWritebackOcr.value).toBe(false)
    })

    it('eqcr has no OCR capabilities', () => {
      const { canStartOcr, canRetryOcr, canConfirmOcr, canWritebackOcr } =
        useOcrGovernance(projectId, year, 'eqcr')

      expect(canStartOcr.value).toBe(false)
      expect(canRetryOcr.value).toBe(false)
      expect(canConfirmOcr.value).toBe(false)
      expect(canWritebackOcr.value).toBe(false)
    })

    it('readonly has no OCR capabilities', () => {
      const { canStartOcr, canRetryOcr, canConfirmOcr, canWritebackOcr } =
        useOcrGovernance(projectId, year, 'readonly')

      expect(canStartOcr.value).toBe(false)
      expect(canRetryOcr.value).toBe(false)
      expect(canConfirmOcr.value).toBe(false)
      expect(canWritebackOcr.value).toBe(false)
    })

    it('partner can start, retry, confirm, and writeback', () => {
      const { canStartOcr, canRetryOcr, canConfirmOcr, canWritebackOcr } =
        useOcrGovernance(projectId, year, 'partner')

      expect(canStartOcr.value).toBe(true)
      expect(canRetryOcr.value).toBe(true)
      expect(canConfirmOcr.value).toBe(true)
      expect(canWritebackOcr.value).toBe(true)
    })

    it('reactive role change updates capabilities', () => {
      const role = ref('readonly')
      const { canStartOcr, canRetryOcr } = useOcrGovernance(projectId, year, role)

      expect(canStartOcr.value).toBe(false)
      expect(canRetryOcr.value).toBe(false)

      role.value = 'admin'
      expect(canStartOcr.value).toBe(true)
      expect(canRetryOcr.value).toBe(true)
    })
  })

  // ─── API Call Construction ───────────────────────────────────────────

  describe('API call construction', () => {
    it('submitJob calls correct URL with POST', async () => {
      mockPost.mockResolvedValue({ data: { data: { job: { id: 'j1' }, created: true } } })

      const { submitJob } = useOcrGovernance(projectId, year, 'admin')
      await submitJob({
        attachment_id: 'att-1',
        attachment_version_id: 'av-1',
        content_hash: 'a'.repeat(64),
      })

      expect(mockPost).toHaveBeenCalledWith(
        `/api/projects/${projectId}/years/${year}/evidence/ocr/jobs`,
        expect.objectContaining({
          attachment_id: 'att-1',
          attachment_version_id: 'av-1',
          content_hash: 'a'.repeat(64),
        }),
      )
    })

    it('getJob calls correct URL with GET', async () => {
      mockGet.mockResolvedValue({ data: { data: { id: 'j1', state: 'queued' } } })

      const { getJob } = useOcrGovernance(projectId, year, 'admin')
      await getJob('j1')

      expect(mockGet).toHaveBeenCalledWith(
        `/api/projects/${projectId}/years/${year}/evidence/ocr/jobs/j1`,
      )
    })

    it('retryJob calls correct URL with POST', async () => {
      mockPost.mockResolvedValue({ data: { data: { job: { id: 'j1', state: 'queued' } } } })

      const { retryJob } = useOcrGovernance(projectId, year, 'admin')
      await retryJob('j1')

      expect(mockPost).toHaveBeenCalledWith(
        `/api/projects/${projectId}/years/${year}/evidence/ocr/jobs/j1/retry`,
      )
    })

    it('getTimeline calls correct URL', async () => {
      mockGet.mockResolvedValue({ data: { data: { job_id: 'j1', transitions: [] } } })

      const { getTimeline } = useOcrGovernance(projectId, year, 'admin')
      await getTimeline('j1')

      expect(mockGet).toHaveBeenCalledWith(
        `/api/projects/${projectId}/years/${year}/evidence/ocr/jobs/j1/timeline`,
      )
    })

    it('addConfirmation calls correct URL with PUT', async () => {
      mockPut.mockResolvedValue({ data: { data: { id: 'c1' } } })

      const { addConfirmation } = useOcrGovernance(projectId, year, 'admin')
      await addConfirmation('j1', 'r1', {
        field_name: 'amount',
        decision: 'accepted',
        confirmed_value: '100.00',
      })

      expect(mockPut).toHaveBeenCalledWith(
        `/api/projects/${projectId}/years/${year}/evidence/ocr/jobs/j1/results/r1/confirmations`,
        expect.objectContaining({ field_name: 'amount', decision: 'accepted' }),
      )
    })

    it('executeWriteback passes Idempotency-Key header', async () => {
      mockPost.mockResolvedValue({
        data: { data: { writeback_id: 'wb1', status: 'success', fields_written: 3 } },
      })

      const { executeWriteback } = useOcrGovernance(projectId, year, 'admin')
      await executeWriteback('j1', 'r1', {
        target_type: 'workpaper_cell',
        target_id: 'wp-123',
        idempotency_key: 'idem-key-001',
      })

      expect(mockPost).toHaveBeenCalledWith(
        `/api/projects/${projectId}/years/${year}/evidence/ocr/jobs/j1/results/r1/writeback`,
        expect.objectContaining({ target_type: 'workpaper_cell', target_id: 'wp-123' }),
        { headers: { 'Idempotency-Key': 'idem-key-001' } },
      )
    })

    it('previewMapping calls correct GET URL', async () => {
      mockGet.mockResolvedValue({
        data: { data: { result_id: 'r1', mapping: {}, all_required_decided: true, ready_for_writeback: true } },
      })

      const { previewMapping } = useOcrGovernance(projectId, year, 'admin')
      await previewMapping('j1', 'r1')

      expect(mockGet).toHaveBeenCalledWith(
        `/api/projects/${projectId}/years/${year}/evidence/ocr/jobs/j1/results/r1/mapping`,
      )
    })
  })

  // ─── Error Handling ──────────────────────────────────────────────────

  describe('error handling', () => {
    it('sets desensitized error on 403', async () => {
      mockPost.mockRejectedValue({
        response: { status: 403, data: { message: '目标不可访问' } },
      })

      const { submitJob, error } = useOcrGovernance(projectId, year, 'admin')
      const result = await submitJob({
        attachment_id: 'att-1',
        attachment_version_id: 'av-1',
        content_hash: 'a'.repeat(64),
      })

      expect(result).toBeNull()
      expect(error.value).toBe('目标不可访问')
    })

    it('sets conflict error on 409 for writeback', async () => {
      mockPost.mockRejectedValue({
        response: { status: 409, data: { message: 'version conflict' } },
      })

      const { executeWriteback, error } = useOcrGovernance(projectId, year, 'admin')
      const result = await executeWriteback('j1', 'r1', {
        target_type: 'cell',
        target_id: 'c1',
        idempotency_key: 'k1',
      })

      expect(result).toBeNull()
      expect(error.value).toBe('版本冲突，目标已被修改')
    })

    it('sets generic error on network failure', async () => {
      mockGet.mockRejectedValue(new Error('Network Error'))

      const { getJob, error } = useOcrGovernance(projectId, year, 'admin')
      const result = await getJob('j1')

      expect(result).toBeNull()
      expect(error.value).toBe('Network Error')
    })

    it('clears error on successful request', async () => {
      mockGet.mockRejectedValueOnce(new Error('first fail'))
      mockGet.mockResolvedValueOnce({ data: { data: { id: 'j1', state: 'queued' } } })

      const { getJob, error } = useOcrGovernance(projectId, year, 'admin')

      await getJob('j1')
      expect(error.value).not.toBeNull()

      await getJob('j1')
      expect(error.value).toBeNull()
    })
  })

  // ─── Loading State ───────────────────────────────────────────────────

  describe('loading state', () => {
    it('loading is true during request', async () => {
      let resolvePromise: (v: any) => void
      mockGet.mockReturnValue(new Promise(r => { resolvePromise = r }))

      const { getJob, loading } = useOcrGovernance(projectId, year, 'admin')

      expect(loading.value).toBe(false)
      const promise = getJob('j1')
      expect(loading.value).toBe(true)

      resolvePromise!({ data: { data: { id: 'j1' } } })
      await promise
      expect(loading.value).toBe(false)
    })
  })
})
