/**
 * Unit Tests — useA51CashflowAudit + useA51EditorMode
 *
 * Spec: .kiro/specs/a5-1-cashflow-audit/
 * Tasks: 5.1, 5.2
 *
 * Coverage:
 * - 5.1: All formula functions (getAuditedAmount, getAuditRow6Amount, getAuditRow8Amount,
 *         getReconcileTotal, getReconcileDiff, getCheckDiff, getCheck5Balance,
 *         getOtherCFTotal, programProgress)
 * - 5.2: useA51EditorMode (checkHealth, switchToExcel, switchToStructured, double-switch guard)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useA51CashflowAudit, PROGRAM_STEPS, RECONCILE_GROUPS } from '../composables/useA51CashflowAudit'
import { useA51EditorMode } from '../composables/useA51EditorMode'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn() },
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function setup() {
  const wpId = ref('wp-a51-001')
  const composable = useA51CashflowAudit({ wpId })
  return { composable, wpId }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Task 5.1: useA51CashflowAudit — 公式计算正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('useA51CashflowAudit — getAuditedAmount', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns unadjusted + adjustment', () => {
    const { composable } = setup()
    composable.setField('a51-audit-1.unadjusted', '1000')
    composable.setField('a51-audit-1.adjustment', '200')
    expect(composable.getAuditedAmount('1')).toBe(1200)
  })

  it('NaN → 0 fallback for unadjusted', () => {
    const { composable } = setup()
    composable.setField('a51-audit-1.unadjusted', 'abc')
    composable.setField('a51-audit-1.adjustment', '100')
    expect(composable.getAuditedAmount('1')).toBe(100)
  })

  it('NaN → 0 fallback for adjustment', () => {
    const { composable } = setup()
    composable.setField('a51-audit-1.unadjusted', '500')
    composable.setField('a51-audit-1.adjustment', 'xyz')
    expect(composable.getAuditedAmount('1')).toBe(500)
  })

  it('both NaN → 0', () => {
    const { composable } = setup()
    composable.setField('a51-audit-1.unadjusted', '')
    composable.setField('a51-audit-1.adjustment', '')
    expect(composable.getAuditedAmount('1')).toBe(0)
  })

  it('handles negative values', () => {
    const { composable } = setup()
    composable.setField('a51-audit-2.unadjusted', '-300')
    composable.setField('a51-audit-2.adjustment', '50')
    expect(composable.getAuditedAmount('2')).toBe(-250)
  })

  it('handles decimal values', () => {
    const { composable } = setup()
    composable.setField('a51-audit-3.unadjusted', '100.55')
    composable.setField('a51-audit-3.adjustment', '0.45')
    expect(composable.getAuditedAmount('3')).toBeCloseTo(101)
  })
})

describe('useA51CashflowAudit — getAuditRow6Amount', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('row6 = row1 − row2 − row3 + row4 + row5', () => {
    const { composable } = setup()
    // row1=1000, row2=100, row3=50, row4=200, row5=30
    composable.setField('a51-audit-1.unadjusted', '1000')
    composable.setField('a51-audit-1.adjustment', '0')
    composable.setField('a51-audit-2.unadjusted', '100')
    composable.setField('a51-audit-2.adjustment', '0')
    composable.setField('a51-audit-3.unadjusted', '50')
    composable.setField('a51-audit-3.adjustment', '0')
    composable.setField('a51-audit-4.unadjusted', '200')
    composable.setField('a51-audit-4.adjustment', '0')
    composable.setField('a51-audit-5.unadjusted', '30')
    composable.setField('a51-audit-5.adjustment', '0')
    // expected: 1000 - 100 - 50 + 200 + 30 = 1080
    expect(composable.getAuditRow6Amount()).toBe(1080)
  })

  it('returns 0 when all fields empty', () => {
    const { composable } = setup()
    expect(composable.getAuditRow6Amount()).toBe(0)
  })

  it('handles adjustments in formula', () => {
    const { composable } = setup()
    composable.setField('a51-audit-1.unadjusted', '500')
    composable.setField('a51-audit-1.adjustment', '100') // row1 = 600
    composable.setField('a51-audit-2.unadjusted', '50')
    composable.setField('a51-audit-2.adjustment', '10')  // row2 = 60
    // row3~5 are 0
    // expected: 600 - 60 - 0 + 0 + 0 = 540
    expect(composable.getAuditRow6Amount()).toBe(540)
  })
})

describe('useA51CashflowAudit — getAuditRow8Amount', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('row8 = row6 − row7', () => {
    const { composable } = setup()
    composable.setField('a51-audit-1.unadjusted', '1000')
    composable.setField('a51-audit-1.adjustment', '0')
    composable.setField('a51-audit-7.unadjusted', '800')
    composable.setField('a51-audit-7.adjustment', '0')
    // row6 = 1000 - 0 - 0 + 0 + 0 = 1000, row7 = 800
    // row8 = 1000 - 800 = 200
    expect(composable.getAuditRow8Amount()).toBe(200)
  })

  it('negative result when row7 > row6', () => {
    const { composable } = setup()
    composable.setField('a51-audit-1.unadjusted', '100')
    composable.setField('a51-audit-1.adjustment', '0')
    composable.setField('a51-audit-7.unadjusted', '500')
    composable.setField('a51-audit-7.adjustment', '0')
    // row6 = 100, row7 = 500 → row8 = -400
    expect(composable.getAuditRow8Amount()).toBe(-400)
  })
})

describe('useA51CashflowAudit — getReconcileTotal', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('sums all items in group 1', () => {
    const { composable } = setup()
    const group = RECONCILE_GROUPS[0] // group id '1', 10 items
    // Set first 3 items
    composable.setField('a51-reconcile-1-1.amount', '100')
    composable.setField('a51-reconcile-1-2.amount', '200')
    composable.setField('a51-reconcile-1-3.amount', '300')
    // rest are empty (→ 0)
    expect(composable.getReconcileTotal('1')).toBe(600)
  })

  it('returns 0 for empty group', () => {
    const { composable } = setup()
    expect(composable.getReconcileTotal('2')).toBe(0)
  })

  it('returns 0 for non-existent group', () => {
    const { composable } = setup()
    expect(composable.getReconcileTotal('99')).toBe(0)
  })

  it('handles negative amounts', () => {
    const { composable } = setup()
    composable.setField('a51-reconcile-3-1.amount', '500')
    composable.setField('a51-reconcile-3-2.amount', '-100')
    composable.setField('a51-reconcile-3-3.amount', '50')
    expect(composable.getReconcileTotal('3')).toBe(450)
  })
})

describe('useA51CashflowAudit — getReconcileDiff', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('diff = total − report_amount', () => {
    const { composable } = setup()
    composable.setField('a51-reconcile-1-1.amount', '500')
    composable.setField('a51-reconcile-1-2.amount', '300')
    composable.setField('a51-reconcile-1.report_amount', '750')
    // total=800, report=750, diff=50
    expect(composable.getReconcileDiff('1')).toBe(50)
  })

  it('returns negative when report > total', () => {
    const { composable } = setup()
    composable.setField('a51-reconcile-2-1.amount', '100')
    composable.setField('a51-reconcile-2.report_amount', '500')
    // total=100, report=500, diff=-400
    expect(composable.getReconcileDiff('2')).toBe(-400)
  })

  it('returns 0 when equal', () => {
    const { composable } = setup()
    composable.setField('a51-reconcile-4-1.amount', '300')
    composable.setField('a51-reconcile-4.report_amount', '300')
    expect(composable.getReconcileDiff('4')).toBe(0)
  })
})

describe('useA51CashflowAudit — getCheckDiff', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('diff = estimated − reported', () => {
    const { composable } = setup()
    composable.setField('a51-check4-acquire-1.estimated', '1000')
    composable.setField('a51-check4-acquire-1.reported', '900')
    expect(composable.getCheckDiff('check4-acquire', '1')).toBe(100)
  })

  it('returns 0 when both empty', () => {
    const { composable } = setup()
    expect(composable.getCheckDiff('check4-dispose', '3')).toBe(0)
  })

  it('handles NaN gracefully', () => {
    const { composable } = setup()
    composable.setField('a51-check5-1.estimated', 'not_a_number')
    composable.setField('a51-check5-1.reported', '100')
    expect(composable.getCheckDiff('check5', '1')).toBe(-100)
  })
})

describe('useA51CashflowAudit — getCheck5Balance', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('balance = SUM(rows 1~7 estimated) − restricted(row 9 estimated)', () => {
    const { composable } = setup()
    // Set rows 1-7 estimated
    composable.setField('a51-check5-1.estimated', '100')
    composable.setField('a51-check5-2.estimated', '200')
    composable.setField('a51-check5-3.estimated', '50')
    composable.setField('a51-check5-4.estimated', '0')
    composable.setField('a51-check5-5.estimated', '0')
    composable.setField('a51-check5-6.estimated', '0')
    composable.setField('a51-check5-7.estimated', '30')
    // Row 9 = restricted
    composable.setField('a51-check5-9.estimated', '80')
    // SUM(1~7) = 380, restricted = 80 → balance = 300
    expect(composable.getCheck5Balance()).toBe(300)
  })

  it('returns 0 when all empty', () => {
    const { composable } = setup()
    expect(composable.getCheck5Balance()).toBe(0)
  })

  it('negative balance when restricted > sum', () => {
    const { composable } = setup()
    composable.setField('a51-check5-1.estimated', '50')
    composable.setField('a51-check5-9.estimated', '200')
    // SUM=50, restricted=200 → -150
    expect(composable.getCheck5Balance()).toBe(-150)
  })
})

describe('useA51CashflowAudit — getOtherCFTotal', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('sums 10 items for receive side', () => {
    const { composable } = setup()
    composable.setField('a51-other-1-receive-1.amount', '100')
    composable.setField('a51-other-1-receive-2.amount', '200')
    composable.setField('a51-other-1-receive-3.amount', '50')
    // items 4-10 are empty → 0
    expect(composable.getOtherCFTotal('1', 'receive')).toBe(350)
  })

  it('sums 10 items for pay side', () => {
    const { composable } = setup()
    composable.setField('a51-other-2-pay-1.amount', '500')
    composable.setField('a51-other-2-pay-5.amount', '300')
    expect(composable.getOtherCFTotal('2', 'pay')).toBe(800)
  })

  it('returns 0 for empty group', () => {
    const { composable } = setup()
    expect(composable.getOtherCFTotal('3', 'receive')).toBe(0)
  })

  it('handles all 10 items filled', () => {
    const { composable } = setup()
    for (let i = 1; i <= 10; i++) {
      composable.setField(`a51-other-1-pay-${i}.amount`, '10')
    }
    expect(composable.getOtherCFTotal('1', 'pay')).toBe(100)
  })
})

describe('useA51CashflowAudit — programProgress', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockPut.mockReset()
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('total is always 21', () => {
    const { composable } = setup()
    expect(composable.programProgress.value.total).toBe(21)
  })

  it('filled = 0 when no conclusions set', () => {
    const { composable } = setup()
    expect(composable.programProgress.value.filled).toBe(0)
  })

  it('counts Y as filled', () => {
    const { composable } = setup()
    composable.setField('a51-program-step-1.conclusion', 'Y')
    composable.setField('a51-program-step-2.conclusion', 'Y')
    expect(composable.programProgress.value.filled).toBe(2)
  })

  it('counts N as filled', () => {
    const { composable } = setup()
    composable.setField('a51-program-step-1.conclusion', 'N')
    expect(composable.programProgress.value.filled).toBe(1)
  })

  it('counts NA as filled', () => {
    const { composable } = setup()
    composable.setField('a51-program-step-1.conclusion', 'NA')
    expect(composable.programProgress.value.filled).toBe(1)
  })

  it('does not count empty or invalid conclusions', () => {
    const { composable } = setup()
    composable.setField('a51-program-step-1.conclusion', '')
    composable.setField('a51-program-step-2.conclusion', 'maybe')
    composable.setField('a51-program-step-3.conclusion', 'Y')
    expect(composable.programProgress.value.filled).toBe(1)
  })

  it('counts all 21 when all set', () => {
    const { composable } = setup()
    for (const step of PROGRAM_STEPS) {
      composable.setField(`a51-program-${step.id}.conclusion`, 'Y')
    }
    expect(composable.programProgress.value.filled).toBe(21)
  })

  it('mixes Y/N/NA correctly', () => {
    const { composable } = setup()
    composable.setField('a51-program-step-1.conclusion', 'Y')
    composable.setField('a51-program-step-2.conclusion', 'N')
    composable.setField('a51-program-step-3.conclusion', 'NA')
    composable.setField('a51-program-step-4.conclusion', '')
    expect(composable.programProgress.value.filled).toBe(3)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Task 5.2: useA51EditorMode — 双模式切换逻辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('useA51EditorMode — checkHealth', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('sets onlyofficeHealthy=true when API returns healthy', async () => {
    mockGet.mockResolvedValue({ healthy: true })
    const { onlyofficeHealthy, checkHealth } = useA51EditorMode()
    await checkHealth()
    expect(onlyofficeHealthy.value).toBe(true)
  })

  it('sets onlyofficeHealthy=false when API returns unhealthy', async () => {
    mockGet.mockResolvedValue({ healthy: false })
    const { onlyofficeHealthy, checkHealth } = useA51EditorMode()
    await checkHealth()
    expect(onlyofficeHealthy.value).toBe(false)
  })

  it('sets onlyofficeHealthy=false on network error', async () => {
    mockGet.mockRejectedValue(new Error('Network error'))
    const { onlyofficeHealthy, checkHealth } = useA51EditorMode()
    await checkHealth()
    expect(onlyofficeHealthy.value).toBe(false)
  })

  it('sets onlyofficeHealthy=false when response is null', async () => {
    mockGet.mockResolvedValue(null)
    const { onlyofficeHealthy, checkHealth } = useA51EditorMode()
    await checkHealth()
    expect(onlyofficeHealthy.value).toBe(false)
  })
})

describe('useA51EditorMode — switchToExcel', () => {
  it('sets mode to excel after flush', async () => {
    const { mode, switchToExcel } = useA51EditorMode()
    const flushFn = vi.fn().mockResolvedValue(undefined)
    expect(mode.value).toBe('structured')
    await switchToExcel(flushFn)
    expect(mode.value).toBe('excel')
    expect(flushFn).toHaveBeenCalledTimes(1)
  })

  it('sets switching=true during transition', async () => {
    const { switching, switchToExcel } = useA51EditorMode()
    let switchingDuringFlush = false
    const flushFn = vi.fn().mockImplementation(async () => {
      switchingDuringFlush = switching.value
    })
    await switchToExcel(flushFn)
    expect(switchingDuringFlush).toBe(true)
    expect(switching.value).toBe(false)
  })

  it('resets switching=false even on flush error', async () => {
    const { switching, switchToExcel } = useA51EditorMode()
    const flushFn = vi.fn().mockRejectedValue(new Error('save failed'))
    await switchToExcel(flushFn).catch(() => {})
    expect(switching.value).toBe(false)
  })
})

describe('useA51EditorMode — switchToStructured', () => {
  it('sets mode to structured after refresh', async () => {
    const { mode, switchToExcel, switchToStructured } = useA51EditorMode()
    const flushFn = vi.fn().mockResolvedValue(undefined)
    const refreshFn = vi.fn().mockResolvedValue(undefined)

    await switchToExcel(flushFn) // go to excel first
    expect(mode.value).toBe('excel')

    await switchToStructured('wp-001', refreshFn)
    expect(mode.value).toBe('structured')
    expect(refreshFn).toHaveBeenCalledWith('wp-001')
  })

  it('sets switching=true during transition', async () => {
    const { switching, switchToStructured } = useA51EditorMode()
    let switchingDuringRefresh = false
    const refreshFn = vi.fn().mockImplementation(async () => {
      switchingDuringRefresh = switching.value
    })
    await switchToStructured('wp-001', refreshFn)
    expect(switchingDuringRefresh).toBe(true)
    expect(switching.value).toBe(false)
  })
})

describe('useA51EditorMode — double-switch prevention', () => {
  it('prevents double switch when already switching', async () => {
    const { switchToExcel, switching } = useA51EditorMode()
    let resolveFlush: () => void
    const slowFlush = new Promise<void>((r) => { resolveFlush = r })
    const flushFn = vi.fn().mockReturnValue(slowFlush)

    // Start first switch (won't resolve yet)
    const p1 = switchToExcel(flushFn)

    // Try second switch while first is in progress
    const flushFn2 = vi.fn().mockResolvedValue(undefined)
    const p2 = switchToExcel(flushFn2)

    // Second call should be no-op (switching guard)
    expect(flushFn2).not.toHaveBeenCalled()

    // Complete first switch
    resolveFlush!()
    await p1
    await p2

    // Only first flush was called
    expect(flushFn).toHaveBeenCalledTimes(1)
    expect(flushFn2).not.toHaveBeenCalled()
  })

  it('prevents switchToStructured when already switching', async () => {
    const { switchToExcel, switchToStructured } = useA51EditorMode()
    let resolveFlush: () => void
    const slowFlush = new Promise<void>((r) => { resolveFlush = r })
    const flushFn = vi.fn().mockReturnValue(slowFlush)

    const p1 = switchToExcel(flushFn)

    const refreshFn = vi.fn().mockResolvedValue(undefined)
    const p2 = switchToStructured('wp-001', refreshFn)

    expect(refreshFn).not.toHaveBeenCalled()

    resolveFlush!()
    await p1
    await p2
  })
})
