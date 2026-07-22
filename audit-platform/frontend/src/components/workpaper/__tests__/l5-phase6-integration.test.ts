/**
 * L5 Phase 6 集成验证测试
 *
 * 验证目标：
 * - Task 6.1: EventBus 集成（publish + subscribe）
 * - Task 6.2: 跨底稿联动（GtIndexChip + cross_wp_ref + TB回写）
 * - Task 6.3: 版本链 + 复核对话集成
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Requirements: 2.8, 4.7, 8.3, 8.4
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mockEmit, mockOn, mockOff, mockPut, mockGet } = vi.hoisted(() => ({
  mockEmit: vi.fn(),
  mockOn: vi.fn(),
  mockOff: vi.fn(),
  mockPut: vi.fn().mockResolvedValue({}),
  mockGet: vi.fn().mockResolvedValue([]),
}))

// ─── Mock eventBus ──────────────────────────────────────────────────────────

vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: mockEmit,
    on: mockOn,
    off: mockOff,
  },
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: mockGet,
    put: mockPut,
  },
}))

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    userId: 'test-user',
    username: 'tester',
    user: { full_name: 'Test User', role: '审计助理' },
  }),
}))

vi.mock('@/stores/roleContext', () => ({
  useRoleContextStore: () => ({
    effectiveRole: 'manager',
  }),
}))

// ─── Task 6.1: EventBus 集成验证 ────────────────────────────────────────────

describe('Task 6.1: EventBus集成', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('useL5FormData.writebackTB publishes "substantive:adjudicated"', async () => {
    const { useL5FormData } = await import('../composables/useL5FormData')
    const { ref } = await import('vue')

    const formData = useL5FormData({
      wpId: ref('wp-001'),
      projectId: ref('proj-001'),
    })

    await formData.writebackTB({
      payableAmount: 1000000,
      unrecognizedAmount: 200000,
    })

    // 应发布两次（2701 + 未确认融资费用）
    const adjudicatedCalls = mockEmit.mock.calls.filter(
      (c) => c[0] === 'substantive:adjudicated'
    )
    expect(adjudicatedCalls.length).toBe(2)
    expect(adjudicatedCalls[0][1]).toMatchObject({
      accountCode: '2701',
      auditedAmount: 1000000,
      wpCode: 'L5',
    })
    expect(adjudicatedCalls[1][1]).toMatchObject({
      accountCode: '2702',
      auditedAmount: 200000,
      wpCode: 'L5',
    })
  })

  it('useL5Adjustment.saveAndPublish publishes "adjustment:created"', async () => {
    const { useL5Adjustment } = await import('../composables/useL5Adjustment')
    const { useL5FormData } = await import('../composables/useL5FormData')
    const { ref } = await import('vue')

    const formData = useL5FormData({
      wpId: ref('wp-001'),
      projectId: ref('proj-001'),
    })
    const adjustment = useL5Adjustment(formData)

    // 添加平衡的分录
    adjustment.entries.value = [
      {
        index: 1,
        type: 'AJE',
        description: '测试',
        accountCode: '2701',
        accountName: '长期应付款',
        debitAmount: 100,
        creditAmount: 0,
      },
      {
        index: 2,
        type: 'AJE',
        description: '测试',
        accountCode: '6603',
        accountName: '财务费用',
        debitAmount: 0,
        creditAmount: 100,
      },
    ]
    adjustment.switchType('AJE')

    await adjustment.saveAndPublish()

    const adjustmentCalls = mockEmit.mock.calls.filter(
      (c) => c[0] === 'adjustment:created'
    )
    expect(adjustmentCalls.length).toBe(1)
  })

  it('useL5CrossSheet.publishAmortizationCalculated emits "l5:amortization-calculated"', async () => {
    const { useL5CrossSheet } = await import('../composables/useL5CrossSheet')
    const { ref } = await import('vue')

    const allResponses = ref(new Map())
    allResponses.value.set('L5-L5-5-period-amortization', {
      item_id: 'L5-L5-5-period-amortization',
      conclusion: null,
      remark: '50000',
    })

    const crossSheet = useL5CrossSheet(allResponses)
    crossSheet.publishAmortizationCalculated()

    const amortCalls = mockEmit.mock.calls.filter(
      (c) => c[0] === 'l5:amortization-calculated'
    )
    expect(amortCalls.length).toBe(1)
    expect(amortCalls[0][1]).toMatchObject({
      wpCode: 'L5',
      periodAmortization: 50000,
    })
  })
})

// ─── Task 6.2: 跨底稿联动验证 ──────────────────────────────────────────────

describe('Task 6.2: 跨底稿联动', () => {
  it('useL5CrossSheet exposes crossWpReferences with L8 target', async () => {
    const { useL5CrossSheet } = await import('../composables/useL5CrossSheet')
    const { ref } = await import('vue')

    const allResponses = ref(new Map())
    const crossSheet = useL5CrossSheet(allResponses)

    expect(crossSheet.crossWpReferences).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          targetWpCode: 'L8',
          direction: 'to',
        }),
      ])
    )
  })

  it('amortizationToL8 computed provides periodAmortization', async () => {
    const { useL5CrossSheet } = await import('../composables/useL5CrossSheet')
    const { ref } = await import('vue')

    const allResponses = ref(new Map())
    allResponses.value.set('L5-L5-5-period-amortization', {
      item_id: 'L5-L5-5-period-amortization',
      conclusion: null,
      remark: '75000',
    })

    const crossSheet = useL5CrossSheet(allResponses)
    expect(crossSheet.amortizationToL8.value.periodAmortization).toBe(75000)
  })

  it('adjudicationVsDetail computes cross-sheet reconciliation', async () => {
    const { useL5CrossSheet } = await import('../composables/useL5CrossSheet')
    const { ref } = await import('vue')

    const allResponses = ref(new Map())
    allResponses.value.set('L5-L5-1-adjudication-total', {
      item_id: 'L5-L5-1-adjudication-total',
      conclusion: null,
      remark: '500000',
    })
    allResponses.value.set('L5-L5-2-rows', {
      item_id: 'L5-L5-2-rows',
      conclusion: null,
      remark: JSON.stringify([{ endBalance: 300000 }, { endBalance: 200000 }]),
    })

    const crossSheet = useL5CrossSheet(allResponses)
    expect(crossSheet.adjudicationVsDetail.value.isMatch).toBe(true)
    expect(crossSheet.adjudicationVsDetail.value.diff).toBe(0)
  })
})

// ─── Task 6.3: 版本链 + 复核对话验证 ────────────────────────────────────────

describe('Task 6.3: 版本链+复核对话集成', () => {
  it('GtL5LongTermPayables wires version trail via runtime boundary', async () => {
    const fs = await import('fs')
    const path = await import('path')
    const mainEntryPath = path.resolve(
      __dirname,
      '../GtL5LongTermPayables.vue'
    )
    const source = fs.readFileSync(mainEntryPath, 'utf-8')

    expect(source).toContain('useVersionTrail')
    expect(source).toContain("provide('scheduleAutoSnapshot'")
    expect(source).toContain('GtReviewDialog')
  })

  it('L5TabDisclosureListed subscribes to substantive:adjudicated', async () => {
    const fs = await import('fs')
    const path = await import('path')
    const filePath = path.resolve(
      __dirname,
      '../l5/core/L5TabDisclosureListed.vue'
    )
    const source = fs.readFileSync(filePath, 'utf-8')

    // Subscribe pattern
    expect(source).toContain("eventBus.on('substantive:adjudicated'")
    expect(source).toContain("eventBus.off('substantive:adjudicated'")
    // Inject openReviewDialog
    expect(source).toContain("inject<() => void>('openReviewDialog'")
  })

  it('L5TabDisclosureSoe subscribes to substantive:adjudicated', async () => {
    const fs = await import('fs')
    const path = await import('path')
    const filePath = path.resolve(
      __dirname,
      '../l5/core/L5TabDisclosureSoe.vue'
    )
    const source = fs.readFileSync(filePath, 'utf-8')

    expect(source).toContain("eventBus.on('substantive:adjudicated'")
    expect(source).toContain("eventBus.off('substantive:adjudicated'")
    expect(source).toContain("inject<() => void>('openReviewDialog'")
  })

  it('L5TabAmortization uses GtIndexChip with value="L8"', async () => {
    const fs = await import('fs')
    const path = await import('path')
    const filePath = path.resolve(
      __dirname,
      '../l5/amortization/L5TabAmortization.vue'
    )
    const source = fs.readFileSync(filePath, 'utf-8')

    expect(source).toContain('GtIndexChip')
    expect(source).toContain('value="L8"')
    expect(source).toContain("inject<() => void>('openReviewDialog'")
  })
})
