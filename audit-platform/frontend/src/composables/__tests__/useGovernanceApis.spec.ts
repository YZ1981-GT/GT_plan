/**
 * useGovernanceApis — Vitest tests（Wave 9 UI 接线）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * 验证新增治理 composable 命中正确后端端点、正确解包 {code,message,data} 信封、
 * 并透传项目/年度 scope 到路径。仅覆盖核心接线正确性，不 mock 业务逻辑。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

import http from '@/utils/http'
import { useCitationGovernance } from '../useCitationGovernance'
import { useAiEvidenceGate } from '../useAiEvidenceGate'
import { useReviewGovernance } from '../useReviewGovernance'
import { useArchiveGovernance } from '../useArchiveGovernance'
import { useLegalHoldGovernance } from '../useLegalHoldGovernance'
import { useEvidenceMetrics } from '../useEvidenceMetrics'

const mocked = http as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

const projectId = ref('proj-1')
const year = ref(2025)
const BASE = '/api/projects/proj-1/years/2025/evidence'

function envelope(data: unknown) {
  return { data: { code: 0, message: 'ok', data } }
}

beforeEach(() => {
  mocked.get.mockReset()
  mocked.post.mockReset()
})

describe('useCitationGovernance', () => {
  it('列表命中 /citations 并解包 items', async () => {
    mocked.get.mockResolvedValue(envelope({ items: [{ id: 'c1' }] }))
    const { listCitations, citations } = useCitationGovernance(projectId, year)
    await listCitations({ ai_content_log_id: 'ai-1' })
    expect(mocked.get).toHaveBeenCalledWith(`${BASE}/citations`, {
      params: { ai_content_log_id: 'ai-1' },
    })
    expect(citations.value).toHaveLength(1)
  })

  it('定位命中 /citations/{id}/locate', async () => {
    mocked.get.mockResolvedValue(envelope({ citation_id: 'c1', status: 'valid' }))
    const { locateCitation } = useCitationGovernance(projectId, year)
    const r = await locateCitation('c1')
    expect(mocked.get).toHaveBeenCalledWith(`${BASE}/citations/c1/locate`)
    expect(r?.status).toBe('valid')
  })

  it('批量校验命中 POST /citations/validate', async () => {
    mocked.post.mockResolvedValue(envelope({ all_valid: true, valid: [], stale: [], invalid: [] }))
    const { validateCitations } = useCitationGovernance(projectId, year)
    const r = await validateCitations(['c1', 'c2'])
    expect(mocked.post).toHaveBeenCalledWith(`${BASE}/citations/validate`, { citation_ids: ['c1', 'c2'] })
    expect(r?.all_valid).toBe(true)
  })
})

describe('useAiEvidenceGate', () => {
  it('确认命中 POST /ai/generations/{id}/confirm', async () => {
    mocked.post.mockResolvedValue(envelope({ confirmed: true }))
    const { confirmGeneration } = useAiEvidenceGate(projectId, year, ref('auditor'))
    await confirmGeneration('ai-1')
    expect(mocked.post).toHaveBeenCalledWith(`${BASE}/ai/generations/ai-1/confirm`, {})
  })

  it('资格检查命中 GET /ai/generations/{id}/eligibility', async () => {
    mocked.get.mockResolvedValue(envelope({ content_id: 'ai-1', status: 'draft', eligible: false, reasons: [] }))
    const { checkEligibility } = useAiEvidenceGate(projectId, year, ref('auditor'))
    const r = await checkEligibility('ai-1')
    expect(mocked.get).toHaveBeenCalledWith(`${BASE}/ai/generations/ai-1/eligibility`)
    expect(r?.eligible).toBe(false)
  })

  it('preflight 命中 POST /ai/formal-output/preflight', async () => {
    mocked.post.mockResolvedValue(envelope({ passed: true, verdict: 'pass', watermark: 'wm', evidence_count: 0, degraded: false, blocking_reasons: [] }))
    const { formalOutputPreflight } = useAiEvidenceGate(projectId, year, ref('partner'))
    const r = await formalOutputPreflight({ target_id: 't1', target_type: 'note' })
    expect(mocked.post).toHaveBeenCalledWith(`${BASE}/ai/formal-output/preflight`, { target_id: 't1', target_type: 'note' })
    expect(r?.watermark).toBe('wm')
  })

  it('service 角色无确认能力（canConfirmAi=false）', () => {
    const { canConfirmAi } = useAiEvidenceGate(projectId, year, ref('service'))
    expect(canConfirmAi.value).toBe(false)
  })
})

describe('useReviewGovernance', () => {
  it('加载命中 GET /reviews/{id}', async () => {
    mocked.get.mockResolvedValue(envelope({ review_id: 'r1', status: 'open', evidence: [] }))
    const { getReview, reviewState } = useReviewGovernance(projectId, year)
    await getReview('r1')
    expect(mocked.get).toHaveBeenCalledWith(`${BASE}/reviews/r1`)
    expect(reviewState.value?.status).toBe('open')
  })

  it('关闭命中 POST /reviews/{id}/close 带说明与 severity', async () => {
    mocked.post.mockResolvedValue(envelope({ status: 'closed' }))
    const { closeReview } = useReviewGovernance(projectId, year)
    await closeReview('r1', '已核实', 'high')
    expect(mocked.post).toHaveBeenCalledWith(`${BASE}/reviews/r1/close`, {
      closing_explanation: '已核实',
      severity: 'high',
    })
  })

  it('完成阻断命中 GET /reviews/completion-block', async () => {
    mocked.get.mockResolvedValue(envelope({ blocked: true, re_review_required_reviews: ['r1'] }))
    const { checkCompletionBlock, completion } = useReviewGovernance(projectId, year)
    await checkCompletionBlock()
    expect(mocked.get).toHaveBeenCalledWith(`${BASE}/reviews/completion-block`)
    expect(completion.value.blocked).toBe(true)
  })
})

describe('useArchiveGovernance', () => {
  it('构建命中 POST /archive/manifests', async () => {
    mocked.post.mockResolvedValue(envelope({ success: true, manifest_id: 'm1', version: 1 }))
    const { buildManifest } = useArchiveGovernance(projectId, year)
    const r = await buildManifest()
    expect(mocked.post).toHaveBeenCalledWith(`${BASE}/archive/manifests`, { policy_version: undefined })
    expect(r?.success).toBe(true)
  })

  it('离线验签命中 POST /archive/verify 包装 package', async () => {
    mocked.post.mockResolvedValue(envelope({ verified: true }))
    const { verifyPackage } = useArchiveGovernance(projectId, year)
    await verifyPackage({ manifest: {} })
    expect(mocked.post).toHaveBeenCalledWith(`${BASE}/archive/verify`, { package: { manifest: {} } })
  })
})

describe('useLegalHoldGovernance', () => {
  it('创建命中 POST /legal-holds', async () => {
    mocked.post.mockResolvedValue(envelope({ legal_hold_id: 'h1', direct_count: 1, transitive_count: 0 }))
    const { createHold } = useLegalHoldGovernance(projectId, year)
    await createHold({ reason: '诉讼', seed_nodes: [{ node_type: 'attachment_version', node_id: 'av1' }] })
    expect(mocked.post).toHaveBeenCalledWith(`${BASE}/legal-holds`, {
      reason: '诉讼',
      seed_nodes: [{ node_type: 'attachment_version', node_id: 'av1' }],
    })
  })

  it('清理命中 POST /legal-holds/purge-jobs 并解包 unmet_conditions', async () => {
    mocked.post.mockResolvedValue(envelope({ allowed: false, delta: 0, unmet_conditions: ['hold_active'], tombstone_id: null }))
    const { createPurgeJob } = useLegalHoldGovernance(projectId, year)
    const r = await createPurgeJob({ node_type: 'attachment_version', node_id: 'av1' })
    expect(mocked.post).toHaveBeenCalledWith(`${BASE}/legal-holds/purge-jobs`, {
      node_type: 'attachment_version',
      node_id: 'av1',
      retention_expired: undefined,
      purge_reason: undefined,
      content_hash: undefined,
      retention_policy_version: undefined,
    })
    expect(r?.allowed).toBe(false)
    expect(r?.unmet_conditions).toContain('hold_active')
  })
})

describe('useEvidenceMetrics', () => {
  it('命中全局 GET /api/evidence-governance/metrics（无 project/year）', async () => {
    mocked.get.mockResolvedValue(envelope({ upload: { total: 1 } }))
    const { loadMetrics, metrics } = useEvidenceMetrics()
    await loadMetrics()
    expect(mocked.get).toHaveBeenCalledWith('/api/evidence-governance/metrics')
    expect(metrics.value?.upload?.total).toBe(1)
  })

  it('403 脱敏为无权提示', async () => {
    mocked.get.mockRejectedValue({ response: { data: { data: { error_code: 'SCOPE_NOT_FOUND_OR_FORBIDDEN' } } } })
    const { loadMetrics, error } = useEvidenceMetrics()
    await loadMetrics()
    expect(error.value).toContain('无权')
  })
})
