/**
 * cutoffCanonical — 单一真源纯函数测试
 *
 * Spec: .kiro/specs/cutoff-test-architecture-convergence/ Wave 0 (Task 1 + 2.1)
 *
 * 双职责：
 * 1. characterization：以既有五套判定/窗口函数为基准，锁定 canonical 与其【等价】（P8/P9/P10）
 * 2. canonical 自身属性：状态机完备互斥（P11）、字面量映射保语义（P12）、双侧证据门禁（P6）
 *
 * 说明：跨期两套语义不等价（P8 分模式）——
 *   crossesByCutoffBoundary ≡ isCutoffPeriodCrossing（I2/I6）
 *   crossesByNaturalMonth   ≡ isCrossPeriod（K8/K9）
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'

import {
  computeWindow,
  inWindow,
  crossesByCutoffBoundary,
  crossesByNaturalMonth,
  classifyCutoffBoundary,
  judgeCrossPeriod,
  deriveConclusion,
  mapLegacyConclusion,
  CUTOFF_CONCLUSIONS,
  type CutoffConclusion,
} from '../cutoffCanonical'

// 既有实现（characterization 基准）
import { computeDateRange } from '../cutoffJudgment'
import { markCutoffCrossPeriod, filterByCutoffWindow } from '../useCutoffAutoSampling'
import { isCutoffPeriodCrossing } from '../useI2FormulaEngine'
import { isCrossPeriod as k8IsCrossPeriod } from '../useK8CutoffEngine'
import { isCrossPeriod as k9IsCrossPeriod } from '../useK9CutoffEngine'

// ─── 日期生成器 ───────────────────────────────────────────────────────────────

const arbDate = fc
  .date({ min: new Date('2023-01-01T00:00:00'), max: new Date('2027-12-31T00:00:00') })
  .map((d) => {
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  })

const arbDays = fc.integer({ min: 0, max: 60 })

function toDate(s: string): Date {
  return new Date(s + 'T00:00:00')
}

// ═══════════════════════════════════════════════════════════════════════════════
// P10 窗口边界等价：computeWindow / inWindow ≡ computeDateRange / filterByCutoffWindow
// ═══════════════════════════════════════════════════════════════════════════════

describe('P10 窗口边界等价', () => {
  it('computeWindow 与既有 computeDateRange 逐日一致', () => {
    fc.assert(
      fc.property(arbDate, arbDays, arbDays, (cd, before, after) => {
        const a = computeWindow(cd, before, after)
        const b = computeDateRange(cd, before, after)
        expect(a).toEqual(b)
      }),
      { numRuns: 60 },
    )
  })

  it('inWindow 与既有 filterByCutoffWindow 逐元素一致', () => {
    fc.assert(
      fc.property(
        fc.array(arbDate, { minLength: 0, maxLength: 8 }),
        arbDate,
        arbDays,
        arbDays,
        (dates, cd, before, after) => {
          const vouchers = dates.map((voucherDate) => ({ voucherDate }))
          const filtered = filterByCutoffWindow(vouchers, cd, before, after).map((v) => v.voucherDate)
          for (const d of dates) {
            const inFiltered = filtered.includes(d)
            expect(inWindow(d, cd, before, after)).toBe(inFiltered)
          }
        },
      ),
      { numRuns: 60 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P8 判定单一真源等价（分模式）
// ═══════════════════════════════════════════════════════════════════════════════

describe('P8 跨期判定分模式等价', () => {
  it('crossesByCutoffBoundary ≡ isCutoffPeriodCrossing（I2/I6）', () => {
    fc.assert(
      fc.property(arbDate, arbDate, arbDate, (bookDate, docDate, cd) => {
        const canonical = crossesByCutoffBoundary(bookDate, docDate, cd)
        const legacy = isCutoffPeriodCrossing(toDate(docDate), toDate(bookDate), toDate(cd))
        expect(canonical).toBe(legacy)
      }),
      { numRuns: 80 },
    )
  })

  it('crossesByNaturalMonth ≡ K8 isCrossPeriod', () => {
    fc.assert(
      fc.property(arbDate, arbDate, arbDate, (sourceDate, bookDate, periodEnd) => {
        const canonical = crossesByNaturalMonth(sourceDate, bookDate)
        const legacy = k8IsCrossPeriod(sourceDate, bookDate, periodEnd)
        expect(canonical).toBe(legacy)
      }),
      { numRuns: 80 },
    )
  })

  it('crossesByNaturalMonth ≡ K9 isCrossPeriod', () => {
    fc.assert(
      fc.property(arbDate, arbDate, arbDate, (sourceDate, bookDate, periodEnd) => {
        const canonical = crossesByNaturalMonth(sourceDate, bookDate)
        const legacy = k9IsCrossPeriod(sourceDate, bookDate, periodEnd)
        expect(canonical).toBe(legacy)
      }),
      { numRuns: 80 },
    )
  })

  it('两模式确实不等价（反例锁定，防未来误统一）', () => {
    // book=2025-11-28, doc=2025-12-28, cd=2025-12-31
    // boundary: 均≤cd → 不跨期; natural-month: 11月≠12月 → 跨期
    expect(crossesByCutoffBoundary('2025-11-28', '2025-12-28', '2025-12-31')).toBe(false)
    expect(crossesByNaturalMonth('2025-11-28', '2025-12-28')).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 第三模式：classifyCutoffBoundary 方向子类（F2 early_book/late_book 基座）
// ═══════════════════════════════════════════════════════════════════════════════

describe('classifyCutoffBoundary 方向子类（F2 收敛基座）', () => {
  it('账在期内单在期后 → book-before-doc-after（提前入账/early_book）', () => {
    expect(classifyCutoffBoundary('2025-12-28', '2026-01-05', '2025-12-31')).toBe('book-before-doc-after')
  })
  it('单在期内账在期后 → doc-before-book-after（推迟入账/late_book）', () => {
    expect(classifyCutoffBoundary('2026-01-05', '2025-12-28', '2025-12-31')).toBe('doc-before-book-after')
  })
  it('两侧同处一侧 → same', () => {
    expect(classifyCutoffBoundary('2025-12-10', '2025-12-20', '2025-12-31')).toBe('same')
    expect(classifyCutoffBoundary('2026-01-02', '2026-01-08', '2025-12-31')).toBe('same')
  })
  it('日期缺失/非法 → incomplete', () => {
    expect(classifyCutoffBoundary('', '2025-12-20', '2025-12-31')).toBe('incomplete')
    expect(classifyCutoffBoundary('2025-13-99', '2025-12-20', '2025-12-31')).toBe('incomplete')
  })
  it('crossesByCutoffBoundary 与 classifyCutoffBoundary 一致（派生关系）', () => {
    fc.assert(
      fc.property(arbDate, arbDate, arbDate, (book, doc, cd) => {
        const cls = classifyCutoffBoundary(book, doc, cd)
        const crosses = crossesByCutoffBoundary(book, doc, cd)
        expect(crosses).toBe(cls === 'book-before-doc-after' || cls === 'doc-before-book-after')
      }),
      { numRuns: 60 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P9 单日期降级等价：judgeCrossPeriod suspect ≡ markCutoffCrossPeriod 单日期降级
// ═══════════════════════════════════════════════════════════════════════════════

describe('P9 单日期降级等价', () => {
  it('仅记账侧日期时，suspect 判定与 markCutoffCrossPeriod 单日期降级一致', () => {
    fc.assert(
      fc.property(arbDate, arbDate, (bookDate, cd) => {
        // canonical：仅 bookDate（documentDate 空）
        const verdict = judgeCrossPeriod({ bookDate, documentDate: '' }, cd, 'cutoff-boundary')
        const canonicalCross = verdict === 'suspect'
        // legacy markCutoffCrossPeriod：voucherDate=bookDate，无 businessDate → 单日期降级
        const legacyCross = markCutoffCrossPeriod({ voucherDate: bookDate }, cd)
        expect(canonicalCross).toBe(legacyCross)
      }),
      { numRuns: 80 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P6 双侧证据门禁：缺任一侧日期 → 证据不完整（绝不正常）
// ═══════════════════════════════════════════════════════════════════════════════

describe('P6 双侧证据门禁', () => {
  it('缺原始单据侧日期 → 证据不完整（两模式均成立）', () => {
    fc.assert(
      fc.property(arbDate, arbDate, fc.constantFrom<'cutoff-boundary' | 'natural-month'>('cutoff-boundary', 'natural-month'), (bookDate, cd, mode) => {
        const c = deriveConclusion({ bookDate, documentDate: '' }, cd, mode)
        expect(c).not.toBe('正常')
        expect(c).toBe('证据不完整')
      }),
      { numRuns: 60 },
    )
  })

  it('缺记账侧日期 → 证据不完整', () => {
    fc.assert(
      fc.property(arbDate, arbDate, (documentDate, cd) => {
        const c = deriveConclusion({ bookDate: '', documentDate }, cd, 'cutoff-boundary')
        expect(c).toBe('证据不完整')
      }),
      { numRuns: 60 },
    )
  })

  it('无任何日期 → 证据不完整', () => {
    expect(deriveConclusion({ bookDate: '', documentDate: '' }, '2025-12-31', 'cutoff-boundary')).toBe('证据不完整')
  })

  it('双侧齐全同期 → 正常；跨期 → 跨期', () => {
    // 同月同侧 → 正常
    expect(deriveConclusion({ bookDate: '2025-12-10', documentDate: '2025-12-20' }, '2025-12-31', 'cutoff-boundary')).toBe('正常')
    // 分处截止日两侧 → 跨期
    expect(deriveConclusion({ bookDate: '2025-12-28', documentDate: '2026-01-05' }, '2025-12-31', 'cutoff-boundary')).toBe('跨期')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P11 状态机完备互斥
// ═══════════════════════════════════════════════════════════════════════════════

describe('P11 状态机完备互斥', () => {
  it('deriveConclusion 恒返回 6 态之一', () => {
    fc.assert(
      fc.property(
        fc.record({ bookDate: fc.oneof(arbDate, fc.constant('')), documentDate: fc.oneof(arbDate, fc.constant('')) }),
        arbDate,
        fc.constantFrom<'cutoff-boundary' | 'natural-month'>('cutoff-boundary', 'natural-month'),
        (pair, cd, mode) => {
          const c = deriveConclusion(pair, cd, mode)
          expect(CUTOFF_CONCLUSIONS).toContain(c)
        },
      ),
      { numRuns: 80 },
    )
    expect(new Set(CUTOFF_CONCLUSIONS).size).toBe(6)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// P12 字面量映射保语义
// ═══════════════════════════════════════════════════════════════════════════════

describe('P12 字面量映射保语义', () => {
  it('旧字面量映射到 6 态且归类正确', () => {
    const cases: Array<[string, CutoffConclusion]> = [
      ['正常', '正常'],
      ['可能跨期', '跨期'],
      ['跨期', '跨期'],
      ['跨期多记', '跨期'],
      ['跨期漏记', '跨期'],
      ['证据不完整', '证据不完整'],
      ['待检查', '待追查'],
      ['需调整', '需调整'],
      ['已调整', '已调整'],
      ['', '待追查'],
    ]
    for (const [input, expected] of cases) {
      expect(mapLegacyConclusion(input)).toBe(expected)
    }
  })

  it('未识别字面量兜底待追查（不静默判正常）', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const mapped = mapLegacyConclusion(s)
        expect(CUTOFF_CONCLUSIONS).toContain(mapped)
        // 非"正常"字面量绝不映射为正常
        if (s.trim() !== '正常') {
          expect(mapped).not.toBe('正常')
        }
      }),
      { numRuns: 60 },
    )
  })
})
