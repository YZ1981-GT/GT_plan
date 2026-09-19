/**
 * useG14Adjudication — 审定表与 G14-2 同步
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useG14Adjudication } from '../useG14Adjudication'
import { G14_CHANGE_RATE_THRESHOLD } from '../g14Constants'
import { isChangeRateExceeding } from '../useG14FormulaEngine'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as object, onMounted: vi.fn(), onBeforeUnmount: vi.fn() }
})

const { mockPost } = vi.hoisted(() => ({ mockPost: vi.fn(async () => ({ message: 'ok' })) }))
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({ data: [] }), post: mockPost },
}))

vi.mock('element-plus', () => ({
  ElMessageBox: { confirm: vi.fn(async () => 'confirm') },
  ElMessage: { warning: vi.fn(), success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

describe('useG14Adjudication', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('本期数自 G14-2 明细同步', () => {
    const allResponses = ref(new Map())
    const adj = useG14Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })

    adj.detail.updateCell('ar', 'currentUnadjusted', 1000)
    adj.detail.updateCell('ar', 'currentAdjustment', 50)

    const row = adj.dataRows.value.find((r) => r.rowKey === 'ar')
    expect(row?.currentUnadjusted).toBe(1000)
    expect(row?.currentAdjustment).toBe(50)
    expect(row?.currentAudited).toBe(1050)
  })

  it('|变动率|>30% 触发原因必填', () => {
    const rate = 0.35
    expect(isChangeRateExceeding(rate, G14_CHANGE_RATE_THRESHOLD)).toBe(true)
    expect(isChangeRateExceeding(0.2, G14_CHANGE_RATE_THRESHOLD)).toBe(false)
  })

  it('明细与审定同步时 detailCrossValidation 为 null', () => {
    const allResponses = ref(new Map())
    const adj = useG14Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })

    adj.detail.updateCell('ar', 'currentUnadjusted', 1000)
    adj.detail.updateCell('ar', 'currentAdjustment', 50)

    expect(adj.detailMismatch.value).toBe(false)
    expect(adj.detailCrossValidation.value).toBeNull()
  })

  it('总体变动概述与缺原因计数（对齐 xlsx 审计说明）', () => {
    const allResponses = ref(new Map())
    const adj = useG14Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })

    adj.detail.updateCell('ar', 'currentUnadjusted', 1300)
    adj.updatePriorField('ar', 'priorUnadjusted', 1000)

    const row = adj.dataRows.value.find((r) => r.rowKey === 'ar')
    expect(row?.changeRate).toBeCloseTo(0.3, 5)
    expect(row?.reasonRequired).toBe(false)
    expect(row?.indexRef).toBe('wp:D2-1')

    adj.detail.updateCell('ar', 'currentUnadjusted', 1400)
    const row2 = adj.dataRows.value.find((r) => r.rowKey === 'ar')
    expect(row2?.reasonRequired).toBe(true)
    expect(adj.missingReasonCount.value).toBe(1)
    expect(adj.hasMissingReasons.value).toBe(true)
    expect(adj.overallChangePctText.value).toMatch(/增加/)
    expect(adj.overallChangeExceedsThreshold.value).toBe(true)
    expect(adj.statusSummary.value.reasonOk).toBe(false)
    expect(adj.statusSummary.value.changeWarn).toBe(true)

    adj.updatePriorField('ar', 'reasonAnalysis', '应收账龄迁徙导致 ECL 上升')
    expect(adj.missingReasonCount.value).toBe(0)
    expect(adj.statusSummary.value.reasonOk).toBe(true)
  })

  // spec: tb-writeback-explicit-publish-gate Task 12（test-follows-source）——
  // 发布前守卫（原因缺失/差异未清/合计变动率超阈）已从 publishAdjudicated 迁到 publishToTb。
  // publishAdjudicated 现为 emit-only（不写 TB、不 gate）；发布门守卫在 publishToTb 内。
  it('差异未清或原因缺失时 publishToTb 不发布（守卫）；补齐后走 POST publish-to-tb', async () => {
    const allResponses = ref(new Map())
    const adj = useG14Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })

    adj.detail.updateCell('ar', 'currentUnadjusted', 1400)
    adj.updatePriorField('ar', 'priorUnadjusted', 1000)
    adj.updateTrialBalance(1400)

    // 合计变动率超阈但原因未填 → 守卫拦下，不发 POST
    await adj.publishToTb()
    expect(mockPost).not.toHaveBeenCalled()

    // 补齐原因分析 + 审计说明 → 守卫通过 → 走显式发布门 POST publish-to-tb（6702 occurrence）
    adj.updatePriorField('ar', 'reasonAnalysis', 'ECL 阶段迁移')
    adj.updateAuditNote('合计变动超 30%，主要为应收账款坏账计提增加')
    await adj.publishToTb()
    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]!
    expect(url).toContain('/api/workpapers/wp-1/audit-determination/publish-to-tb')
    expect(body.sheet_name).toMatch(/G14-1/)
    expect(body.writeback_rows[0]).toMatchObject({ account_code: '6702', amount_kind: 'occurrence' })
  })

  it('|变动额|≥10万 亦触发原因必填（P2 金额阈值）', () => {
    const allResponses = ref(new Map())
    const adj = useG14Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    // 变动率仅 10%，但变动额 10 万
    adj.detail.updateCell('ar', 'currentUnadjusted', 1_100_000)
    adj.updatePriorField('ar', 'priorUnadjusted', 1_000_000)
    const row = adj.dataRows.value.find((r) => r.rowKey === 'ar')
    expect(row?.changeRate).toBeCloseTo(0.1, 5)
    expect(row?.reasonRequired).toBe(true)
    expect(adj.missingReasonCount.value).toBe(1)
  })

  it('上期为 0 且本期有发生额时原因必填', () => {
    const allResponses = ref(new Map())
    const adj = useG14Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    adj.detail.updateCell('ar', 'currentUnadjusted', 5000)
    const row = adj.dataRows.value.find((r) => r.rowKey === 'ar')
    expect(row?.changeRate).toBeNull()
    expect(row?.reasonRequired).toBe(true)
  })

  it('statusSummary 在 TB 勾稽通过时 allOk', () => {
    const allResponses = ref(new Map())
    const adj = useG14Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    adj.detail.updateCell('ar', 'currentUnadjusted', 500)
    adj.updatePriorField('ar', 'priorUnadjusted', 500)
    adj.updateTrialBalance(500)
    expect(adj.statusSummary.value.tbOk).toBe(true)
    expect(adj.statusSummary.value.detailOk).toBe(true)
    expect(adj.statusSummary.value.reasonOk).toBe(true)
    expect(adj.statusSummary.value.allOk).toBe(true)
  })
})
