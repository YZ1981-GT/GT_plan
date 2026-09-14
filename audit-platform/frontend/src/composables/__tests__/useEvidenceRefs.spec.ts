/**
 * useEvidenceRefs — Vitest tests (Task 8.4, Wave 7 aggregation)
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening
 * Requirements: R1, R4, R9, R11, R15
 * Design: §6.2 (EvidenceRef), §10.2 (Vitest 边界)
 *
 * 汇总覆盖 evidence 状态维度的前端行为（此前无 Vitest）：
 *  - 证据关系双向查询（source / evidence 方向）与详情/创建/停用/影响
 *  - 大列表有界分页（has_more / next_cursor / limit 透传）与错误恢复
 *  - 跨项目脱敏错误（R1/R4：前端仅展示通用 "目标不可访问"，不泄露目标元数据）
 *  - 元数据不完整门禁提示、网络错误 fail-safe（返回 null 不崩）
 *
 * 前端仅展示/查询，鉴权与能力判定的唯一真源在后端；本测试断言前端在
 * 各类后端结果下的展示/恢复行为，不断言前端自行授权。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useEvidenceRefs } from '../useEvidenceRefs'
import type { EvidenceRefItem } from '../useEvidenceRefs'

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

const projectId = ref('project-001')
const year = ref(2025)

function makeRef(overrides: Partial<EvidenceRefItem> = {}): EvidenceRefItem {
  return {
    id: 'ref-001',
    project_id: 'project-001',
    audit_year: 2025,
    source_type: 'workpaper_cell',
    source_id: 'D2-1!B5',
    source_version: 2,
    evidence_type: 'attachment_version',
    evidence_id: 'att-001',
    attachment_version_id: 'av-001',
    target_version: 3,
    target_hash: 'a'.repeat(64),
    label: '银行回单',
    context: 'user-001',
    intent_hash: 'i'.repeat(32),
    status: 'active',
    created_at: '2025-06-01T10:00:00Z',
    ...overrides,
  }
}

/** ResponseWrapperMiddleware 信封：{ code, message, data } */
function envelope(data: unknown) {
  return { data: { code: 0, message: 'ok', data } }
}

/** 构造脱敏/门禁错误（axios error 形状） */
function apiError(errorCode: string, message?: string) {
  return {
    response: { data: { data: { error_code: errorCode, message } } },
  }
}

beforeEach(() => {
  mockedHttp.get.mockReset()
  mockedHttp.post.mockReset()
})

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('useEvidenceRefs — 证据状态双向查询 (R4)', () => {
  it('source 方向查询返回引用列表并回填 has_more/next_cursor', async () => {
    mockedHttp.get.mockResolvedValue(
      envelope({ items: [makeRef()], next_cursor: 'cur-2', has_more: true })
    )
    const { queryRefs, refs, hasMore, nextCursor } = useEvidenceRefs(projectId, year)

    const page = await queryRefs({ direction: 'source', source_type: 'workpaper_cell', source_id: 'D2-1!B5', limit: 50 })

    expect(page).not.toBeNull()
    expect(refs.value).toHaveLength(1)
    expect(refs.value[0].id).toBe('ref-001')
    expect(hasMore.value).toBe(true)
    expect(nextCursor.value).toBe('cur-2')
    // limit / direction 透传到后端
    const [, cfg] = mockedHttp.get.mock.calls[0]
    expect(cfg.params.direction).toBe('source')
    expect(cfg.params.limit).toBe(50)
  })

  it('evidence 方向查询命中同一引用（双向一致）', async () => {
    mockedHttp.get.mockResolvedValue(
      envelope({ items: [makeRef()], next_cursor: null, has_more: false })
    )
    const { queryRefs, refs } = useEvidenceRefs(projectId, year)

    await queryRefs({ direction: 'evidence', evidence_type: 'attachment_version', evidence_id: 'att-001' })

    expect(refs.value[0].id).toBe('ref-001')
    const [, cfg] = mockedHttp.get.mock.calls[0]
    expect(cfg.params.direction).toBe('evidence')
  })

  it('getRef 返回单条引用详情（版本/hash 完整）', async () => {
    mockedHttp.get.mockResolvedValue(envelope(makeRef({ target_version: 7 })))
    const { getRef } = useEvidenceRefs(projectId, year)

    const item = await getRef('ref-001')
    expect(item?.target_version).toBe(7)
    expect(item?.target_hash).toHaveLength(64)
  })
})

describe('useEvidenceRefs — 大列表有界分页 (R15)', () => {
  it('空列表时 refs 为空且 has_more=false', async () => {
    mockedHttp.get.mockResolvedValue(envelope({ items: [], next_cursor: null, has_more: false }))
    const { queryRefs, refs, hasMore } = useEvidenceRefs(projectId, year)

    await queryRefs({ direction: 'source' })
    expect(refs.value).toEqual([])
    expect(hasMore.value).toBe(false)
  })

  it('后端返回超量结果时 has_more=true 提示缩小范围，不无界加载', async () => {
    const many = Array.from({ length: 100 }, (_, i) => makeRef({ id: `ref-${i}` }))
    mockedHttp.get.mockResolvedValue(envelope({ items: many, next_cursor: 'cur-next', has_more: true }))
    const { queryRefs, refs, hasMore, nextCursor } = useEvidenceRefs(projectId, year)

    await queryRefs({ direction: 'source', limit: 100 })
    expect(refs.value).toHaveLength(100)
    expect(hasMore.value).toBe(true)
    expect(nextCursor.value).toBe('cur-next')
  })

  it('影响路径查询在 truncated 时返回截断标记（有界闭包）', async () => {
    mockedHttp.get.mockResolvedValue(
      envelope({
        nodes: [{ target_type: 'report_line', target_id: 'BS-1', distance: 1, path: ['ref-001'] }],
        total_visited: 100,
        truncated: true,
      })
    )
    const { queryImpact } = useEvidenceRefs(projectId, year)

    const res = await queryImpact({ source_type: 'workpaper_cell', source_id: 'D2-1!B5', max_depth: 10, limit: 100 })
    expect(res?.truncated).toBe(true)
    expect(res?.nodes[0].distance).toBe(1)
  })
})

describe('useEvidenceRefs — 错误恢复与跨项目脱敏 (R1/R4)', () => {
  it('跨项目/越权目标显示通用 "目标不可访问" 且不泄露元数据', async () => {
    mockedHttp.get.mockRejectedValue(apiError('SCOPE_NOT_FOUND_OR_FORBIDDEN', 'project mismatch: project-999'))
    const { queryRefs, error, refs } = useEvidenceRefs(projectId, year)

    const page = await queryRefs({ direction: 'source', source_id: 'foreign' })
    expect(page).toBeNull()
    expect(error.value).toBe('目标不可访问')
    // 不泄露后端原始 message（含其他项目 ID）
    expect(error.value).not.toContain('project-999')
    // 状态未被污染
    expect(refs.value).toEqual([])
  })

  it('创建引用命中元数据不完整门禁时给出中文引导', async () => {
    mockedHttp.post.mockRejectedValue(apiError('METADATA_INCOMPLETE'))
    const { createRef, error } = useEvidenceRefs(projectId, year)

    const res = await createRef({
      source_type: 'workpaper_cell',
      source_id: 'D2-1!B5',
      evidence_type: 'attachment_version',
      evidence_id: 'att-001',
    })
    expect(res).toBeNull()
    expect(error.value).toContain('元数据不完整')
  })

  it('网络错误时 fail-safe 返回 null 且给出网络错误提示，不抛出', async () => {
    mockedHttp.get.mockRejectedValue(new Error('Network Error'))
    const { queryImpact, error } = useEvidenceRefs(projectId, year)

    const res = await queryImpact({ source_type: 'workpaper_cell', source_id: 'D2-1!B5' })
    expect(res).toBeNull()
    expect(error.value).toBe('Network Error')
  })

  it('createRef 透传 Idempotency-Key（R9 幂等）', async () => {
    mockedHttp.post.mockResolvedValue(envelope({ id: 'ref-001', status: 'active', created: true }))
    const { createRef } = useEvidenceRefs(projectId, year)

    await createRef(
      { source_type: 'workpaper_cell', source_id: 'D2-1!B5', evidence_type: 'attachment_version', evidence_id: 'att-001' },
      'idem-key-abc'
    )
    const [, , cfg] = mockedHttp.post.mock.calls[0]
    expect(cfg.headers['Idempotency-Key']).toBe('idem-key-abc')
  })

  it('deactivateRef 返回状态转移结果（active→inactive）', async () => {
    mockedHttp.post.mockResolvedValue(
      envelope({ ref_id: 'ref-001', previous_status: 'active', new_status: 'inactive', reason: '证据已更新' })
    )
    const { deactivateRef } = useEvidenceRefs(projectId, year)

    const res = await deactivateRef('ref-001', '证据已更新')
    expect(res?.previous_status).toBe('active')
    expect(res?.new_status).toBe('inactive')
  })

  it('loading 在请求完成后复位', async () => {
    mockedHttp.get.mockResolvedValue(envelope({ items: [], next_cursor: null, has_more: false }))
    const { queryRefs, loading } = useEvidenceRefs(projectId, year)

    expect(loading.value).toBe(false)
    await queryRefs({ direction: 'source' })
    expect(loading.value).toBe(false)
  })
})
