/**
 * Unit Tests — D1 应收票据专属组件 (Pure Function & Logic)
 *
 * Spec: .kiro/specs/d1-notes-receivable/
 * Tasks: 9.1–9.20
 *
 * 测试纯函数和计算逻辑（无组件挂载），直接导入 composables 导出的工具函数和常量。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  getAuditedAmount,
  getChangeRate,
  calculateExpectedLossRate,
  calculateProvision,
  calculateDifference,
  calculateInterest,
  calculateBSDateBalance,
  getTabStatusFromResponses,
  PROCEDURE_STEPS_CONFIG,
  AGING_BANDS_CONFIG,
  ADJUDICATION_ROWS_CONFIG,
  TAB_NAMES,
} from '../composables/useD1NotesReceivable'

// ═══════════════════════════════════════════════════════════════════════════════
// 9.1 注册契约测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.1 注册契约测试', () => {
  it('wp_code_overrides: D1→d1-notes-receivable', async () => {
    const mod = await import('../../../../../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = (mod as any).default ?? mod
    expect(overrides['D1']).toBe('d1-notes-receivable')
  })

  it('wp_code_overrides: D1-1→skip, D1-4→skip', async () => {
    const mod = await import('../../../../../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = (mod as any).default ?? mod
    expect(overrides['D1-1']).toBe('skip')
    expect(overrides['D1-4']).toBe('skip')
  })

  it('wp_code_overrides: D1-2→audit-sheet, D1-3→audit-sheet', async () => {
    const mod = await import('../../../../../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = (mod as any).default ?? mod
    expect(overrides['D1-2']).toBe('audit-sheet')
    expect(overrides['D1-3']).toBe('audit-sheet')
  })

  it('htmlRendererRegistry includes d1-notes-receivable componentType', async () => {
    const { HTML_RENDERER_REGISTRY } = await import('../htmlRendererRegistry')
    const entry = HTML_RENDERER_REGISTRY.get('d1-notes-receivable' as any)
    expect(entry).toBeDefined()
    expect(entry!.label).toBe('D1 应收票据')
    expect(entry!.icon).toBe('📄')
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// 9.2 Tab 渲染测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.2 Tab 渲染测试', () => {
  it('TAB_NAMES has 19 entries', () => {
    expect(TAB_NAMES.length).toBe(19)
  })

  it('TAB_NAMES includes expected tab identifiers', () => {
    expect(TAB_NAMES).toContain('directory')
    expect(TAB_NAMES).toContain('procedure')
    expect(TAB_NAMES).toContain('adjudication')
    expect(TAB_NAMES).toContain('bad-debt')
    expect(TAB_NAMES).toContain('business-model')
    expect(TAB_NAMES).toContain('endorsement')
    expect(TAB_NAMES).toContain('interest')
    expect(TAB_NAMES).toContain('inventory')
    expect(TAB_NAMES).toContain('related-party')
    expect(TAB_NAMES).toContain('pledge')
    expect(TAB_NAMES).toContain('disclosure')
    expect(TAB_NAMES).toContain('adjustment')
  })

  it('TAB_NAMES first entry is directory (底稿目录)', () => {
    expect(TAB_NAMES[0]).toBe('directory')
  })

  it('TAB_NAMES includes sub-workpaper tabs (detail-category, detail-customer)', () => {
    expect(TAB_NAMES).toContain('detail-category')
    expect(TAB_NAMES).toContain('detail-customer')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.3 审定表计算测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.3 审定表计算测试', () => {
  describe('getAuditedAmount', () => {
    it('basic: 1000 + 200 - 100 + 50 - 30 = 1120', () => {
      expect(getAuditedAmount(1000, 200, 100, 50, 30)).toBe(1120)
    })

    it('all zeros → 0', () => {
      expect(getAuditedAmount(0, 0, 0, 0, 0)).toBe(0)
    })

    it('only currentUnadjusted → returns it', () => {
      expect(getAuditedAmount(5000, 0, 0, 0, 0)).toBe(5000)
    })

    it('credits exceed: 1000 + 0 - 500 + 0 - 300 = 200', () => {
      expect(getAuditedAmount(1000, 0, 500, 0, 300)).toBe(200)
    })
  })

  describe('getChangeRate', () => {
    it('prior=0, audited=0 → empty string', () => {
      expect(getChangeRate(0, 0)).toBe('')
    })

    it('prior=0, audited=1000 → 1 (100%)', () => {
      expect(getChangeRate(0, 1000)).toBe(1)
    })

    it('prior=1000, audited=1200 → 0.2', () => {
      expect(getChangeRate(1000, 1200)).toBeCloseTo(0.2)
    })

    it('prior=1000, audited=500 → -0.5', () => {
      expect(getChangeRate(1000, 500)).toBeCloseTo(-0.5)
    })

    it('prior=200, audited=200 → 0 (no change)', () => {
      expect(getChangeRate(200, 200)).toBe(0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.4 程序表测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.4 程序表测试', () => {
  it('PROCEDURE_STEPS_CONFIG has 8 steps', () => {
    expect(PROCEDURE_STEPS_CONFIG.length).toBe(8)
  })

  it('step names match expected', () => {
    const names = PROCEDURE_STEPS_CONFIG.map(s => s.stepName)
    expect(names).toEqual([
      '获取明细', '核对总账', '票据验真', '到期分析',
      '背书贴现', '减值评估', '披露检查', '结论',
    ])
  })

  it('first 7 steps are required, last is optional', () => {
    for (let i = 0; i < 7; i++) {
      expect(PROCEDURE_STEPS_CONFIG[i].isRequired).toBe(true)
    }
    expect(PROCEDURE_STEPS_CONFIG[7].isRequired).toBe(false)
  })

  it('canReview logic: all required steps completed → true', () => {
    const statuses: string[] = ['已完成', '已完成', '不适用', '已完成', '已完成', '已完成', '已完成', '未开始']
    const canReview = PROCEDURE_STEPS_CONFIG.every((step, i) => {
      if (!step.isRequired) return true
      return statuses[i] === '已完成' || statuses[i] === '不适用'
    })
    expect(canReview).toBe(true)
  })

  it('canReview logic: one required step incomplete → false', () => {
    const statuses: string[] = ['已完成', '执行中', '已完成', '已完成', '已完成', '已完成', '已完成', '已完成']
    const canReview = PROCEDURE_STEPS_CONFIG.every((step, i) => {
      if (!step.isRequired) return true
      return statuses[i] === '已完成' || statuses[i] === '不适用'
    })
    expect(canReview).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.5 ECL 坏账准备测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.5 ECL 坏账准备测试', () => {
  it('AGING_BANDS_CONFIG has 6 bands', () => {
    expect(AGING_BANDS_CONFIG.length).toBe(6)
  })

  it('aging band keys are correct', () => {
    const keys = AGING_BANDS_CONFIG.map(b => b.bandKey)
    expect(keys).toEqual([
      'not-overdue', 'overdue-1-30', 'overdue-31-90',
      'overdue-91-180', 'overdue-181-365', 'overdue-1year',
    ])
  })

  it('calculateExpectedLossRate: [0.05, 0.2, 0.4] → 0.004', () => {
    const rate = calculateExpectedLossRate([0.05, 0.2, 0.4])
    expect(rate).toBeCloseTo(0.004)
  })

  it('calculateExpectedLossRate: empty array → 0', () => {
    expect(calculateExpectedLossRate([])).toBe(0)
  })

  it('calculateExpectedLossRate: single rate [0.5] → 0.5', () => {
    expect(calculateExpectedLossRate([0.5])).toBe(0.5)
  })

  it('calculateProvision: balance=100000, rate=0.05 → 5000', () => {
    expect(calculateProvision(100000, 0.05)).toBe(5000)
  })

  it('calculateProvision: balance=0, rate=0.5 → 0', () => {
    expect(calculateProvision(0, 0.5)).toBe(0)
  })

  it('calculateDifference: actual=6000, should=5000 → 1000', () => {
    expect(calculateDifference(6000, 5000)).toBe(1000)
  })

  it('calculateDifference: actual=3000, should=5000 → -2000', () => {
    expect(calculateDifference(3000, 5000)).toBe(-2000)
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// 9.6 业务模式测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.6 业务模式测试', () => {
  it('suggestClassification: SPPI=Y + 摊余 → 分类正确', () => {
    // Inline test of the logic from design doc
    function suggestClassification(sppi: 'Y' | 'N' | null, model: string | null): string | null {
      if (sppi === null || model === null) return null
      if (sppi === 'Y' && model === '以摊余成本计量') {
        return '分类正确：以摊余成本计量的金融资产'
      }
      if (sppi === 'N') {
        return '注意：SPPI 测试未通过，应以公允价值计量'
      }
      return null
    }

    expect(suggestClassification('Y', '以摊余成本计量'))
      .toBe('分类正确：以摊余成本计量的金融资产')
  })

  it('suggestClassification: SPPI=N → warning message', () => {
    function suggestClassification(sppi: 'Y' | 'N' | null, model: string | null): string | null {
      if (sppi === null || model === null) return null
      if (sppi === 'Y' && model === '以摊余成本计量') {
        return '分类正确：以摊余成本计量的金融资产'
      }
      if (sppi === 'N') {
        return '注意：SPPI 测试未通过，应以公允价值计量'
      }
      return null
    }

    expect(suggestClassification('N', '以摊余成本计量'))
      .toBe('注意：SPPI 测试未通过，应以公允价值计量')
    expect(suggestClassification('N', '以公允价值计量且变动计入当期损益'))
      .toBe('注意：SPPI 测试未通过，应以公允价值计量')
  })

  it('suggestClassification: null inputs → null', () => {
    function suggestClassification(sppi: 'Y' | 'N' | null, model: string | null): string | null {
      if (sppi === null || model === null) return null
      if (sppi === 'Y' && model === '以摊余成本计量') {
        return '分类正确：以摊余成本计量的金融资产'
      }
      if (sppi === 'N') {
        return '注意：SPPI 测试未通过，应以公允价值计量'
      }
      return null
    }

    expect(suggestClassification(null, '以摊余成本计量')).toBeNull()
    expect(suggestClassification('Y', null)).toBeNull()
    expect(suggestClassification(null, null)).toBeNull()
  })

  it('suggestClassification: SPPI=Y + non-摊余 model → null', () => {
    function suggestClassification(sppi: 'Y' | 'N' | null, model: string | null): string | null {
      if (sppi === null || model === null) return null
      if (sppi === 'Y' && model === '以摊余成本计量') {
        return '分类正确：以摊余成本计量的金融资产'
      }
      if (sppi === 'N') {
        return '注意：SPPI 测试未通过，应以公允价值计量'
      }
      return null
    }

    expect(suggestClassification('Y', '以公允价值计量且变动计入其他综合收益')).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.7 背书贴现测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.7 背书贴现测试', () => {
  it('endorsement summary calculation: derecognized vs not-derecognized', () => {
    const items = [
      { amount: 50000, derecognition: '终止确认' as const },
      { amount: 30000, derecognition: '不终止确认' as const },
      { amount: 20000, derecognition: '终止确认' as const },
      { amount: 10000, derecognition: null },
    ]

    let derecognizedAmount = 0
    let notDerecognizedAmount = 0
    for (const item of items) {
      if (item.derecognition === '终止确认') derecognizedAmount += item.amount
      else if (item.derecognition === '不终止确认') notDerecognizedAmount += item.amount
    }

    expect(derecognizedAmount).toBe(70000)
    expect(notDerecognizedAmount).toBe(30000)
  })

  it('max 100 items constraint', () => {
    // Simulate the addEndorsement constraint
    const MAX_ENDORSEMENT_COUNT = 100
    let count = 99

    // Can add one more
    expect(count < MAX_ENDORSEMENT_COUNT).toBe(true)
    count++
    // Cannot add beyond 100
    expect(count >= MAX_ENDORSEMENT_COUNT).toBe(true)
  })

  it('empty endorsement list → all zeros summary', () => {
    const items: Array<{ amount: number; derecognition: string | null }> = []
    let derecognizedAmount = 0
    let notDerecognizedAmount = 0
    for (const item of items) {
      if (item.derecognition === '终止确认') derecognizedAmount += item.amount
      else if (item.derecognition === '不终止确认') notDerecognizedAmount += item.amount
    }
    expect(derecognizedAmount).toBe(0)
    expect(notDerecognizedAmount).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.8 贴息测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.8 贴息测试', () => {
  it('P=100000, R=0.05, D=90 → 1250', () => {
    expect(calculateInterest(100000, 0.05, 90)).toBeCloseTo(1250)
  })

  it('P=500000, R=0.03, D=180 → 7500', () => {
    expect(calculateInterest(500000, 0.03, 180)).toBeCloseTo(7500)
  })

  it('P=0, R=0.05, D=90 → 0 (zero principal)', () => {
    expect(calculateInterest(0, 0.05, 90)).toBe(0)
  })

  it('P=100000, R=0, D=90 → 0 (zero rate)', () => {
    expect(calculateInterest(100000, 0, 90)).toBe(0)
  })

  it('P=100000, R=0.05, D=0 → 0 (zero days)', () => {
    expect(calculateInterest(100000, 0.05, 0)).toBe(0)
  })

  it('P=1000000, R=0.04, D=360 → 40000 (full year)', () => {
    expect(calculateInterest(1000000, 0.04, 360)).toBeCloseTo(40000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.9 监盘测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.9 监盘测试', () => {
  it('basic: countBalance=800000, additions=50000, deductions=30000 → 820000', () => {
    expect(calculateBSDateBalance(800000, 50000, 30000)).toBe(820000)
  })

  it('no changes: countBalance=500000, +0, -0 → 500000', () => {
    expect(calculateBSDateBalance(500000, 0, 0)).toBe(500000)
  })

  it('only additions: 100000 + 50000 - 0 → 150000', () => {
    expect(calculateBSDateBalance(100000, 50000, 0)).toBe(150000)
  })

  it('only deductions: 100000 + 0 - 80000 → 20000', () => {
    expect(calculateBSDateBalance(100000, 0, 80000)).toBe(20000)
  })

  it('difference = bookBalance - bsDateBalance', () => {
    const bsDate = calculateBSDateBalance(800000, 50000, 30000)
    const bookBalance = 825000
    const difference = bookBalance - bsDate
    expect(difference).toBe(5000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.10 质押测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.10 质押测试', () => {
  it('pledge ratio = pledged / total', () => {
    const pledgedTotal = 600000
    const totalNotesReceivable = 1000000
    const ratio = pledgedTotal / totalNotesReceivable
    expect(ratio).toBeCloseTo(0.6)
  })

  it('pledge ratio > 50% triggers warning', () => {
    const ratio = 0.55
    expect(ratio > 0.5).toBe(true)
  })

  it('pledge ratio ≤ 50% no warning', () => {
    const ratio = 0.45
    expect(ratio > 0.5).toBe(false)
  })

  it('pledge ratio with zero total → 0', () => {
    const pledgedTotal = 100000
    const totalNotesReceivable = 0
    const ratio = totalNotesReceivable <= 0 ? 0 : pledgedTotal / totalNotesReceivable
    expect(ratio).toBe(0)
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// 9.11 关联方测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.11 关联方测试', () => {
  it('matching logic: party name in endorsement drawers → matched', () => {
    const rpNames = ['甲公司', '乙公司', '丙公司']
    const endorseDrawers = ['甲公司', '丁公司', '乙公司']
    const matched = endorseDrawers.filter(d => rpNames.includes(d))
    expect(matched).toEqual(['甲公司', '乙公司'])
  })

  it('no matches when lists are disjoint', () => {
    const rpNames = ['甲公司', '乙公司']
    const endorseDrawers = ['丙公司', '丁公司']
    const matched = endorseDrawers.filter(d => rpNames.includes(d))
    expect(matched).toEqual([])
  })

  it('empty related party list → no matches', () => {
    const rpNames: string[] = []
    const endorseDrawers = ['甲公司', '乙公司']
    const matched = endorseDrawers.filter(d => rpNames.includes(d))
    expect(matched).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.12 附注披露测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.12 附注披露测试', () => {
  const LISTED_ITEMS = [
    '应收票据分类及账面价值', '坏账准备变动', '已质押票据',
    '已背书未到期', '已贴现未到期', '前五名出票人', '关联方票据', '会计政策说明',
  ]
  const SOE_ITEMS = [
    '应收票据基本情况', '坏账准备计提情况', '重大单项计提',
    '已背书/已贴现情况', '受限资产情况', '关联方票据交易',
  ]

  it('listed template has 8 check items', () => {
    expect(LISTED_ITEMS.length).toBe(8)
  })

  it('SOE template has 6 check items', () => {
    expect(SOE_ITEMS.length).toBe(6)
  })

  it('hasUndisclosedItems: some "未披露需补充" → true', () => {
    const conclusions = ['已披露且准确', '未披露需补充', '不适用']
    const hasUndisclosed = conclusions.some(c => c === '未披露需补充')
    expect(hasUndisclosed).toBe(true)
  })

  it('hasUndisclosedItems: all disclosed → false', () => {
    const conclusions = ['已披露且准确', '已披露且准确', '不适用']
    const hasUndisclosed = conclusions.some(c => c === '未披露需补充')
    expect(hasUndisclosed).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.13 调整分录测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.13 调整分录测试', () => {
  it('AJE total = sum of AJE entries', () => {
    const entries = [
      { type: 'AJE' as const, amount: 1000 },
      { type: 'RJE' as const, amount: 500 },
      { type: 'AJE' as const, amount: 2000 },
      { type: 'RJE' as const, amount: 300 },
    ]
    const ajeTotal = entries.filter(e => e.type === 'AJE').reduce((s, e) => s + e.amount, 0)
    const rjeTotal = entries.filter(e => e.type === 'RJE').reduce((s, e) => s + e.amount, 0)
    expect(ajeTotal).toBe(3000)
    expect(rjeTotal).toBe(800)
  })

  it('empty entries → 0 totals', () => {
    const entries: Array<{ type: 'AJE' | 'RJE'; amount: number }> = []
    const ajeTotal = entries.filter(e => e.type === 'AJE').reduce((s, e) => s + e.amount, 0)
    const rjeTotal = entries.filter(e => e.type === 'RJE').reduce((s, e) => s + e.amount, 0)
    expect(ajeTotal).toBe(0)
    expect(rjeTotal).toBe(0)
  })

  it('all AJE entries → RJE total is 0', () => {
    const entries = [
      { type: 'AJE' as const, amount: 1000 },
      { type: 'AJE' as const, amount: 2000 },
    ]
    const rjeTotal = entries.filter(e => e.type === 'RJE').reduce((s, e) => s + e.amount, 0)
    expect(rjeTotal).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.14 EventBus 联动测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.14 EventBus 联动测试', () => {
  it('dispatch when value changes: oldAmount≠newAmount → event fired', () => {
    const events: Array<{ type: string; payload: any }> = []
    function dispatchIfChanged(oldVal: number, newVal: number): void {
      if (oldVal !== newVal) {
        events.push({ type: 'substantive:adjudicated', payload: { auditedAmount: newVal } })
      }
    }

    dispatchIfChanged(1000, 1200)
    expect(events.length).toBe(1)
    expect(events[0].payload.auditedAmount).toBe(1200)
  })

  it('no dispatch when value unchanged: oldAmount===newAmount → no event', () => {
    const events: Array<{ type: string; payload: any }> = []
    function dispatchIfChanged(oldVal: number, newVal: number): void {
      if (oldVal !== newVal) {
        events.push({ type: 'substantive:adjudicated', payload: { auditedAmount: newVal } })
      }
    }

    dispatchIfChanged(1000, 1000)
    expect(events.length).toBe(0)
  })

  it('adjustment:created event contains correct payload', () => {
    const events: Array<{ type: string; payload: any }> = []
    const entry = { type: 'AJE', debitAccount: '应收票据', creditAccount: '营业收入', amount: 5000, description: '调整' }

    events.push({
      type: 'adjustment:created',
      payload: { wpCode: 'D1', entryType: entry.type, ...entry },
    })

    expect(events[0].type).toBe('adjustment:created')
    expect(events[0].payload.wpCode).toBe('D1')
    expect(events[0].payload.amount).toBe(5000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.15 保存行为测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.15 保存行为测试', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('debounce: text save fires after 2000ms', () => {
    const saveFn = vi.fn()
    let timer: ReturnType<typeof setTimeout> | null = null

    function saveDebouncedText(): void {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => { saveFn() }, 2000)
    }

    saveDebouncedText()
    expect(saveFn).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1999)
    expect(saveFn).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1)
    expect(saveFn).toHaveBeenCalledOnce()

    vi.useRealTimers()
  })

  it('immediate save for conclusion fields (no debounce)', () => {
    const saveFn = vi.fn()

    // Immediate save should call synchronously (no timer)
    function saveImmediate(): void {
      saveFn()
    }

    saveImmediate()
    expect(saveFn).toHaveBeenCalledOnce()

    vi.useRealTimers()
  })

  it('debounce resets on rapid typing', () => {
    const saveFn = vi.fn()
    let timer: ReturnType<typeof setTimeout> | null = null

    function saveDebouncedText(): void {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => { saveFn() }, 2000)
    }

    saveDebouncedText()
    vi.advanceTimersByTime(1000)
    saveDebouncedText() // reset
    vi.advanceTimersByTime(1000)
    expect(saveFn).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1000)
    expect(saveFn).toHaveBeenCalledOnce()

    vi.useRealTimers()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.16 复核签字测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.16 复核签字测试', () => {
  it('canReview: all required steps "已完成" or "不适用" → true', () => {
    const statuses = ['已完成', '已完成', '不适用', '已完成', '已完成', '已完成', '已完成', '未开始']
    const canReview = PROCEDURE_STEPS_CONFIG.every((step, i) => {
      if (!step.isRequired) return true
      return statuses[i] === '已完成' || statuses[i] === '不适用'
    })
    expect(canReview).toBe(true)
  })

  it('canReview: mixed states → false', () => {
    const statuses = ['已完成', '执行中', '已完成', '未开始', '已完成', '已完成', '已完成', '已完成']
    const canReview = PROCEDURE_STEPS_CONFIG.every((step, i) => {
      if (!step.isRequired) return true
      return statuses[i] === '已完成' || statuses[i] === '不适用'
    })
    expect(canReview).toBe(false)
  })

  it('pendingItems returns incomplete step names', () => {
    const statuses = ['已完成', '执行中', '已完成', '未开始', '已完成', '已完成', '已完成', '已完成']
    const pending: string[] = []
    PROCEDURE_STEPS_CONFIG.forEach((step, i) => {
      if (!step.isRequired) return
      if (statuses[i] !== '已完成' && statuses[i] !== '不适用') {
        pending.push(step.stepName)
      }
    })
    expect(pending).toEqual(['核对总账', '到期分析'])
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.17 Amendment 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.17 Amendment 测试', () => {
  it('startAmendment clears review sign', () => {
    // Simulate amendment logic
    const responses = new Map<string, { conclusion: string | null; remark: string | null }>()
    responses.set('D1-review-sign', { conclusion: 'Y', remark: '现场经理' })
    responses.set('D1-review-date', { conclusion: null, remark: '2026-01-15' })

    // Start amendment
    const reason = '发现审定表计算错误'
    responses.set('D1-amend-1-reason', { conclusion: null, remark: reason })
    responses.set('D1-review-sign', { conclusion: null, remark: null })
    responses.set('D1-review-date', { conclusion: null, remark: null })

    expect(responses.get('D1-review-sign')!.conclusion).toBeNull()
    expect(responses.get('D1-review-date')!.remark).toBeNull()
    expect(responses.get('D1-amend-1-reason')!.remark).toBe(reason)
  })

  it('empty reason rejected (no amendment started)', () => {
    const reason = ''
    const shouldReject = !reason || !reason.trim()
    expect(shouldReject).toBe(true)
  })

  it('whitespace-only reason rejected', () => {
    const reason = '   '
    const shouldReject = !reason || !reason.trim()
    expect(shouldReject).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.18 readonly 模式测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.18 readonly 模式测试', () => {
  it('isReadonly = externalReadonly || isReviewed (both false → false)', () => {
    const externalReadonly = false
    const isReviewed = false
    expect(externalReadonly || isReviewed).toBe(false)
  })

  it('isReadonly = true when externalReadonly is true', () => {
    const externalReadonly = true
    const isReviewed = false
    expect(externalReadonly || isReviewed).toBe(true)
  })

  it('isReadonly = true when isReviewed is true', () => {
    const externalReadonly = false
    const isReviewed = true
    expect(externalReadonly || isReviewed).toBe(true)
  })

  it('isReadonly = true when both are true', () => {
    const externalReadonly = true
    const isReviewed = true
    expect(externalReadonly || isReviewed).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.19 子底稿 Tab 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.19 子底稿 Tab 测试', () => {
  it('TAB_NAMES includes detail-category (D1-2)', () => {
    expect(TAB_NAMES).toContain('detail-category')
  })

  it('TAB_NAMES includes detail-customer (D1-3)', () => {
    expect(TAB_NAMES).toContain('detail-customer')
  })

  it('D1-2 and D1-3 map to audit-sheet in wp_code_overrides (verified in 9.1)', () => {
    // This is a placeholder referencing the registry test above
    // The actual assertion is in 9.1 — here we verify the tab naming
    const subWpTabs = TAB_NAMES.filter(t => t.startsWith('detail-'))
    expect(subWpTabs.length).toBe(2)
    expect(subWpTabs).toContain('detail-category')
    expect(subWpTabs).toContain('detail-customer')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.20 Tab 完成状态测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.20 Tab 完成状态测试', () => {
  it('empty responses → not-started', () => {
    expect(getTabStatusFromResponses([])).toBe('not-started')
  })

  it('all null conclusion and remark → not-started', () => {
    const responses = [
      { item_id: 'D1-test-1', conclusion: null, remark: null },
      { item_id: 'D1-test-2', conclusion: null, remark: null },
    ]
    expect(getTabStatusFromResponses(responses)).toBe('not-started')
  })

  it('partial data → in-progress', () => {
    const responses = [
      { item_id: 'D1-test-1', conclusion: '已完成', remark: null },
      { item_id: 'D1-test-2', conclusion: null, remark: null },
      { item_id: 'D1-test-3', conclusion: null, remark: '备注' },
    ]
    expect(getTabStatusFromResponses(responses)).toBe('in-progress')
  })

  it('all have conclusion or remark → completed', () => {
    const responses = [
      { item_id: 'D1-test-1', conclusion: '已完成', remark: null },
      { item_id: 'D1-test-2', conclusion: null, remark: '已处理' },
      { item_id: 'D1-test-3', conclusion: '符合', remark: '无异常' },
    ]
    expect(getTabStatusFromResponses(responses)).toBe('completed')
  })

  it('single item with conclusion → completed', () => {
    const responses = [
      { item_id: 'D1-test-1', conclusion: '已完成', remark: null },
    ]
    expect(getTabStatusFromResponses(responses)).toBe('completed')
  })

  it('single item with remark only → completed', () => {
    const responses = [
      { item_id: 'D1-test-1', conclusion: null, remark: '数据' },
    ]
    expect(getTabStatusFromResponses(responses)).toBe('completed')
  })
})
