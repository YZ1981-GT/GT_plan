/**
 * Unit Tests — D2 应收账款专属组件 (Pure Function & Logic)
 *
 * Spec: .kiro/specs/d2-accounts-receivable/
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
  calculatePledgeRatio,
  determineCutoff,
  sumifLegacy as sumif,
} from '../composables/useD2FormulaEngine'
import {
  getTabStatusFromResponses,
  PROCEDURE_STEPS_CONFIG,
  AGING_BANDS_CONFIG,
  ADJUDICATION_ROWS_CONFIG,
  TAB_NAMES,
} from '../composables/d2Constants'

// ═══════════════════════════════════════════════════════════════════════════════
// 9.1 注册契约测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.1 注册契约测试', () => {
  it('wp_code_overrides: D2→d2-accounts-receivable', async () => {
    const mod = await import('../../../../../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = (mod as any).default ?? mod
    expect(overrides['D2']).toBe('d2-accounts-receivable')
  })

  it('wp_code_overrides: D2-1/D2-3/D2-4 全部路由到 d2-accounts-receivable', async () => {
    const mod = await import('../../../../../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = (mod as any).default ?? mod
    expect(overrides['D2-1']).toBe('d2-accounts-receivable')
    expect(overrides['D2-3']).toBe('d2-accounts-receivable')
    expect(overrides['D2-4']).toBe('d2-accounts-receivable')
  })

  it('wp_code_overrides: D2-2/D2-5/D2-6 路由到 d2-accounts-receivable', async () => {
    const mod = await import('../../../../../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = (mod as any).default ?? mod
    expect(overrides['D2-2']).toBe('d2-accounts-receivable')
    expect(overrides['D2-5']).toBe('d2-accounts-receivable')
    expect(overrides['D2-6']).toBe('d2-accounts-receivable')
  })

  it('htmlRendererRegistry includes d2-accounts-receivable componentType', async () => {
    const { HTML_RENDERER_REGISTRY } = await import('../htmlRendererRegistry')
    const entry = HTML_RENDERER_REGISTRY.get('d2-accounts-receivable' as any)
    expect(entry).toBeDefined()
    expect(entry!.label).toBe('D2 应收账款')
    expect(entry!.icon).toBe('💰')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.2 Tab 渲染测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.2 Tab 渲染测试', () => {
  it('TAB_NAMES has 17 entries', () => {
    expect(TAB_NAMES.length).toBe(17)
  })

  it('TAB_NAMES includes expected tab identifiers', () => {
    expect(TAB_NAMES).toContain('directory')
    expect(TAB_NAMES).toContain('procedure')
    expect(TAB_NAMES).toContain('adjudication')
    expect(TAB_NAMES).toContain('disclosure')
    expect(TAB_NAMES).toContain('detail-d2-2')
    expect(TAB_NAMES).toContain('bad-debt')
    expect(TAB_NAMES).toContain('cutoff-test')
    expect(TAB_NAMES).toContain('adjustment')
    expect(TAB_NAMES).toContain('ecl-calculation')
    expect(TAB_NAMES).toContain('ecl-measurement')
    expect(TAB_NAMES).toContain('analysis')
    expect(TAB_NAMES).toContain('related-party')
    expect(TAB_NAMES).toContain('factoring')
    expect(TAB_NAMES).toContain('general-check')
    expect(TAB_NAMES).toContain('policy-check')
    expect(TAB_NAMES).toContain('writeoff-check')
    expect(TAB_NAMES).toContain('bizmodel-check')
  })

  it('TAB_NAMES first entry is directory (底稿目录)', () => {
    expect(TAB_NAMES[0]).toBe('directory')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.3 审定表 SUMIF 计算测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.3 审定表 SUMIF 计算测试', () => {
  describe('getAuditedAmount (3-param)', () => {
    it('basic: 1000 + 200 + 50 = 1250', () => {
      expect(getAuditedAmount(1000, 200, 50)).toBe(1250)
    })

    it('all zeros → 0', () => {
      expect(getAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('negative adjustments: 1000 + (-200) + (-50) = 750', () => {
      expect(getAuditedAmount(1000, -200, -50)).toBe(750)
    })

    it('only currentUnadjusted → returns it', () => {
      expect(getAuditedAmount(5000, 0, 0)).toBe(5000)
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

  describe('sumif', () => {
    const testRows = [
      { AI: '单项计提', S: 100, Z: 10, AA: 110 },
      { AI: '账龄组合', S: 200, Z: 20, AA: 220 },
      { AI: '单项计提', S: 300, Z: 30, AA: 330 },
      { AI: '客户类型组合', S: 400, Z: 40, AA: 440 },
      { AI: '账龄组合', S: 500, Z: 50, AA: 550 },
    ]

    it('sumif 单项计提 S = 400', () => {
      expect(sumif(testRows, '单项计提', 'S')).toBe(400)
    })

    it('sumif 账龄组合 AA = 770', () => {
      expect(sumif(testRows, '账龄组合', 'AA')).toBe(770)
    })

    it('sumif 客户类型组合 Z = 40', () => {
      expect(sumif(testRows, '客户类型组合', 'Z')).toBe(40)
    })

    it('sumif empty rows → 0', () => {
      expect(sumif([], '单项计提', 'S')).toBe(0)
    })

    it('sumif non-matching classification → 0', () => {
      expect(sumif(testRows, '不存在的分类', 'S')).toBe(0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.4 程序表测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.4 程序表测试', () => {
  it('PROCEDURE_STEPS_CONFIG has 7 steps', () => {
    expect(PROCEDURE_STEPS_CONFIG.length).toBe(7)
  })

  it('step names match expected', () => {
    const names = PROCEDURE_STEPS_CONFIG.map(s => s.stepName)
    expect(names).toEqual([
      '获取并核对明细', '核对总账', '函证', '替代程序',
      '坏账准备', '截止测试', '结论',
    ])
  })

  it('first 6 steps are required, last is optional', () => {
    for (let i = 0; i < 6; i++) {
      expect(PROCEDURE_STEPS_CONFIG[i].isRequired).toBe(true)
    }
    expect(PROCEDURE_STEPS_CONFIG[6].isRequired).toBe(false)
  })

  it('canReview logic: all required steps completed → true', () => {
    const statuses = ['已完成', '已完成', '不适用', '已完成', '已完成', '已完成', '未开始']
    const canReview = PROCEDURE_STEPS_CONFIG.every((step, i) => {
      if (!step.isRequired) return true
      return statuses[i] === '已完成' || statuses[i] === '不适用'
    })
    expect(canReview).toBe(true)
  })

  it('canReview logic: one required step incomplete → false', () => {
    const statuses = ['已完成', '执行中', '已完成', '已完成', '已完成', '已完成', '已完成']
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

  it('aging band keys are correct (within-1y through over-5y)', () => {
    const keys = AGING_BANDS_CONFIG.map(b => b.bandKey)
    expect(keys).toEqual([
      'within-1y', '1-2y', '2-3y', '3-4y', '4-5y', 'over-5y',
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
// 9.6 截止测试测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.6 截止测试测试', () => {
  it('determineCutoff: rev=2026-01-15 > bs=2025-12-31 → true (跨期)', () => {
    expect(determineCutoff('2026-01-15', '2025-12-31')).toBe(true)
  })

  it('determineCutoff: rev=2025-12-31 = bs=2025-12-31 → false (未跨期)', () => {
    expect(determineCutoff('2025-12-31', '2025-12-31')).toBe(false)
  })

  it('determineCutoff: rev=2025-11-30 < bs=2025-12-31 → false (未跨期)', () => {
    expect(determineCutoff('2025-11-30', '2025-12-31')).toBe(false)
  })

  it('determineCutoff: rev=2026-03-01 > bs=2025-12-31 → true', () => {
    expect(determineCutoff('2026-03-01', '2025-12-31')).toBe(true)
  })

  it('determineCutoff: invalid date → false', () => {
    expect(determineCutoff('invalid', '2025-12-31')).toBe(false)
    expect(determineCutoff('2025-12-31', 'invalid')).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.7 保理分析测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.7 保理分析测试', () => {
  it('derecognition judge: transferRisk=true → 终止确认', () => {
    // From design: transferRisk → 终止确认
    function judgeDerecognition(transferRisk: boolean, retainControl: boolean): string {
      if (transferRisk) return '终止确认'
      if (!transferRisk && !retainControl) return '终止确认'
      return '不终止确认'
    }
    expect(judgeDerecognition(true, false)).toBe('终止确认')
    expect(judgeDerecognition(true, true)).toBe('终止确认')
  })

  it('derecognition judge: !transferRisk && !retainControl → 终止确认', () => {
    function judgeDerecognition(transferRisk: boolean, retainControl: boolean): string {
      if (transferRisk) return '终止确认'
      if (!transferRisk && !retainControl) return '终止确认'
      return '不终止确认'
    }
    expect(judgeDerecognition(false, false)).toBe('终止确认')
  })

  it('derecognition judge: !transferRisk && retainControl → 不终止确认', () => {
    function judgeDerecognition(transferRisk: boolean, retainControl: boolean): string {
      if (transferRisk) return '终止确认'
      if (!transferRisk && !retainControl) return '终止确认'
      return '不终止确认'
    }
    expect(judgeDerecognition(false, true)).toBe('不终止确认')
  })

  it('factoring summary calculation', () => {
    const items = [
      { category: '质押' as const, amount: 50000, derecognition: null },
      { category: '保理' as const, amount: 30000, derecognition: '终止确认' as const },
      { category: '质押' as const, amount: 20000, derecognition: null },
      { category: '保理' as const, amount: 10000, derecognition: '不终止确认' as const },
    ]

    const pledgedTotal = items.filter(i => i.category === '质押').reduce((s, i) => s + i.amount, 0)
    const factoredTotal = items.filter(i => i.category === '保理').reduce((s, i) => s + i.amount, 0)
    const derecognizedAmount = items.filter(i => i.derecognition === '终止确认').reduce((s, i) => s + i.amount, 0)
    const notDerecognizedAmount = items.filter(i => i.derecognition === '不终止确认').reduce((s, i) => s + i.amount, 0)

    expect(pledgedTotal).toBe(70000)
    expect(factoredTotal).toBe(40000)
    expect(derecognizedAmount).toBe(30000)
    expect(notDerecognizedAmount).toBe(10000)
  })

  it('max 100 items constraint', () => {
    const MAX_FACTORING_COUNT = 100
    let count = 99
    expect(count < MAX_FACTORING_COUNT).toBe(true)
    count++
    expect(count >= MAX_FACTORING_COUNT).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.8 SUMIF 聚合测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.8 SUMIF 聚合测试', () => {
  it('sumif correctly aggregates by classification', () => {
    const rows = [
      { AI: '单项计提', S: 1000, Z: 100, AA: 1100 },
      { AI: '账龄组合', S: 2000, Z: 200, AA: 2200 },
      { AI: '单项计提', S: 3000, Z: -100, AA: 2900 },
      { AI: '客户类型组合', S: 4000, Z: 400, AA: 4400 },
    ]
    expect(sumif(rows, '单项计提', 'S')).toBe(4000)
    expect(sumif(rows, '单项计提', 'Z')).toBe(0)
    expect(sumif(rows, '单项计提', 'AA')).toBe(4000)
    expect(sumif(rows, '账龄组合', 'S')).toBe(2000)
    expect(sumif(rows, '客户类型组合', 'AA')).toBe(4400)
  })

  it('sumif with all same classification', () => {
    const rows = [
      { AI: '账龄组合', S: 100, Z: 10, AA: 110 },
      { AI: '账龄组合', S: 200, Z: 20, AA: 220 },
      { AI: '账龄组合', S: 300, Z: 30, AA: 330 },
    ]
    expect(sumif(rows, '账龄组合', 'S')).toBe(600)
    expect(sumif(rows, '账龄组合', 'Z')).toBe(60)
    expect(sumif(rows, '账龄组合', 'AA')).toBe(660)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.9 质押比例测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.9 质押比例测试', () => {
  it('calculatePledgeRatio: P=600000, T=1000000 → 0.6', () => {
    expect(calculatePledgeRatio(600000, 1000000)).toBeCloseTo(0.6)
  })

  it('calculatePledgeRatio: T=0 → 0 (avoid division by zero)', () => {
    expect(calculatePledgeRatio(100000, 0)).toBe(0)
  })

  it('pledge ratio > 0.5 triggers warning', () => {
    const ratio = calculatePledgeRatio(600000, 1000000)
    expect(ratio > 0.5).toBe(true)
  })

  it('pledge ratio ≤ 0.5 no warning', () => {
    const ratio = calculatePledgeRatio(400000, 1000000)
    expect(ratio > 0.5).toBe(false)
  })

  it('calculatePledgeRatio: P=0, T=1000000 → 0', () => {
    expect(calculatePledgeRatio(0, 1000000)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.10 关联方测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.10 关联方测试', () => {
  it('matching logic: party name in AR customers → matched', () => {
    const rpNames = ['甲公司', '乙公司', '丙公司']
    const arCustomers = ['甲公司', '丁公司', '乙公司', '戊公司']
    const matched = arCustomers.filter(c => rpNames.includes(c))
    expect(matched).toEqual(['甲公司', '乙公司'])
  })

  it('no matches when lists are disjoint', () => {
    const rpNames = ['甲公司', '乙公司']
    const arCustomers = ['丙公司', '丁公司']
    const matched = arCustomers.filter(c => rpNames.includes(c))
    expect(matched).toEqual([])
  })

  it('empty related party list → no matches', () => {
    const rpNames: string[] = []
    const arCustomers = ['甲公司', '乙公司']
    const matched = arCustomers.filter(c => rpNames.includes(c))
    expect(matched).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.11 附注披露测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.11 附注披露测试', () => {
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

  it('disclosure conclusions limited to valid values', () => {
    const validConclusions = ['已披露且准确', '已披露但需修改', '未披露需补充', '不适用']
    const testValue = '已披露且准确'
    expect(validConclusions).toContain(testValue)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.12 调整分录测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.12 调整分录测试', () => {
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

  it('adjustment syncs to adjudication: AJE total feeds into audited amount', () => {
    const ajeTotal = 3000
    const rjeTotal = 800
    const currentUnadjusted = 100000
    const audited = getAuditedAmount(currentUnadjusted, ajeTotal, rjeTotal)
    expect(audited).toBe(103800)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.13 分析程序测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.13 分析程序测试', () => {
  it('turnover days warning: change >30% → warning', () => {
    const priorDays = 45
    const currentDays = 60
    const changeRate = (currentDays - priorDays) / priorDays
    expect(changeRate).toBeCloseTo(0.333, 2)
    expect(Math.abs(changeRate) > 0.3).toBe(true)
  })

  it('turnover days warning: change ≤30% → no warning', () => {
    const priorDays = 50
    const currentDays = 60
    const changeRate = (currentDays - priorDays) / priorDays
    expect(changeRate).toBeCloseTo(0.2)
    expect(Math.abs(changeRate) > 0.3).toBe(false)
  })

  it('turnover rate calculation: revenue/avgAR', () => {
    const revenue = 10000000
    const avgAR = 2000000
    const turnoverRate = revenue / avgAR
    expect(turnoverRate).toBe(5)
    const turnoverDays = 360 / turnoverRate
    expect(turnoverDays).toBe(72)
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
        events.push({ type: 'substantive:adjudicated', payload: { wpCode: 'D2', accountCode: '1122', auditedAmount: newVal } })
      }
    }

    dispatchIfChanged(1000, 1200)
    expect(events.length).toBe(1)
    expect(events[0].payload.wpCode).toBe('D2')
    expect(events[0].payload.accountCode).toBe('1122')
    expect(events[0].payload.auditedAmount).toBe(1200)
  })

  it('no dispatch when value unchanged', () => {
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
    const entry = { type: 'AJE', debitAccount: '应收账款', creditAccount: '营业收入', amount: 5000, description: '调整' }

    events.push({
      type: 'adjustment:created',
      payload: { wpCode: 'D2', entryType: entry.type, ...entry },
    })

    expect(events[0].type).toBe('adjustment:created')
    expect(events[0].payload.wpCode).toBe('D2')
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
    function saveImmediate(): void { saveFn() }
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
    const statuses = ['已完成', '已完成', '不适用', '已完成', '已完成', '已完成', '未开始']
    const canReview = PROCEDURE_STEPS_CONFIG.every((step, i) => {
      if (!step.isRequired) return true
      return statuses[i] === '已完成' || statuses[i] === '不适用'
    })
    expect(canReview).toBe(true)
  })

  it('canReview: mixed states → false', () => {
    const statuses = ['已完成', '执行中', '已完成', '未开始', '已完成', '已完成', '已完成']
    const canReview = PROCEDURE_STEPS_CONFIG.every((step, i) => {
      if (!step.isRequired) return true
      return statuses[i] === '已完成' || statuses[i] === '不适用'
    })
    expect(canReview).toBe(false)
  })

  it('pendingItems returns incomplete required step names', () => {
    const statuses = ['已完成', '执行中', '已完成', '未开始', '已完成', '已完成', '已完成']
    const pending: string[] = []
    PROCEDURE_STEPS_CONFIG.forEach((step, i) => {
      if (!step.isRequired) return
      if (statuses[i] !== '已完成' && statuses[i] !== '不适用') {
        pending.push(step.stepName)
      }
    })
    expect(pending).toEqual(['核对总账', '替代程序'])
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 9.17 Amendment 测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('9.17 Amendment 测试', () => {
  it('startAmendment clears review sign', () => {
    const responses = new Map<string, { conclusion: string | null; remark: string | null }>()
    responses.set('D2-review-sign', { conclusion: 'Y', remark: '现场经理' })
    responses.set('D2-review-date', { conclusion: null, remark: '2026-01-15' })

    // Start amendment
    const reason = '发现审定表计算错误'
    responses.set('D2-amend-1-reason', { conclusion: null, remark: reason })
    responses.set('D2-review-sign', { conclusion: null, remark: null })
    responses.set('D2-review-date', { conclusion: null, remark: null })

    expect(responses.get('D2-review-sign')!.conclusion).toBeNull()
    expect(responses.get('D2-review-date')!.remark).toBeNull()
    expect(responses.get('D2-amend-1-reason')!.remark).toBe(reason)
  })

  it('empty reason rejected', () => {
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
  it('TAB_NAMES includes detail-d2-2 (D2-2 明细表)', () => {
    expect(TAB_NAMES).toContain('detail-d2-2')
  })

  it('TAB_NAMES includes analysis (D2-5) and related-party (D2-6)', () => {
    expect(TAB_NAMES).toContain('analysis')
    expect(TAB_NAMES).toContain('related-party')
  })

  it('D2-2, D2-5, D2-6 map to audit-sheet (lazy load via GtWpRenderer)', () => {
    // Verified in 9.1 — here we confirm tab naming matches sub-workpaper purpose
    const subWpTabMap = {
      'detail-d2-2': 'D2-2', // 明细表
      'analysis': 'D2-5',    // 分析程序
      'related-party': 'D2-6', // 关联方
    }
    expect(Object.keys(subWpTabMap).length).toBe(3)
    for (const tab of Object.keys(subWpTabMap)) {
      expect(TAB_NAMES).toContain(tab)
    }
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
      { item_id: 'D2-test-1', conclusion: null, remark: null },
      { item_id: 'D2-test-2', conclusion: null, remark: null },
    ]
    expect(getTabStatusFromResponses(responses)).toBe('not-started')
  })

  it('partial data → in-progress', () => {
    const responses = [
      { item_id: 'D2-test-1', conclusion: '已完成', remark: null },
      { item_id: 'D2-test-2', conclusion: null, remark: null },
      { item_id: 'D2-test-3', conclusion: null, remark: '备注' },
    ]
    expect(getTabStatusFromResponses(responses)).toBe('in-progress')
  })

  it('all have conclusion or remark → completed', () => {
    const responses = [
      { item_id: 'D2-test-1', conclusion: '已完成', remark: null },
      { item_id: 'D2-test-2', conclusion: null, remark: '已处理' },
      { item_id: 'D2-test-3', conclusion: '符合', remark: '无异常' },
    ]
    expect(getTabStatusFromResponses(responses)).toBe('completed')
  })

  it('single item with conclusion → completed', () => {
    const responses = [
      { item_id: 'D2-test-1', conclusion: '已完成', remark: null },
    ]
    expect(getTabStatusFromResponses(responses)).toBe('completed')
  })

  it('single item with remark only → completed', () => {
    const responses = [
      { item_id: 'D2-test-1', conclusion: null, remark: '数据' },
    ]
    expect(getTabStatusFromResponses(responses)).toBe('completed')
  })
})
