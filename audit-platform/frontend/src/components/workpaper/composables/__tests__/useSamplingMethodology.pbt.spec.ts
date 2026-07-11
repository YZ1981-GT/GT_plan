/**
 * Property-Based Tests — 抽样方法学纯函数（voucher-check-sampling-integration）
 *
 * Spec: .kiro/specs/voucher-check-sampling-integration/
 * Task: 3（design 「Correctness Properties」Property 1~12）
 *
 * 使用 fast-check + vitest，max_examples≈5（numRuns: 5）验证：
 * - Property 1  样本量单调性（computeSampleSize）
 * - Property 2  MUS 间隔一致性（computeMusInterval / computeSampleSize）
 * - Property 3  高值全选（markHighValueItems）
 * - Property 4  污染率有界 / projected 非负（projectMisstatement）
 * - Property 5  错报上限下界（computeUpperMisstatementLimit）
 * - Property 6  结论边界（deriveSamplingConclusion）
 * - Property 7  总体校验对称性（reconcilePopulation）
 * - Property 8  填充模式守恒（applyFillMode，既有回归）
 * - Property 9  版本 diff 互斥完备（computeVersionDiff，既有回归）
 * - Property 10 参数校验（validateSamplingConfig）
 * - Property 11 截止窗口过滤边界（filterByCutoffWindow）
 * - Property 12 跨期判定位置单调（markCutoffCrossPeriod）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import Decimal from 'decimal.js'
import {
  reliabilityFactor,
  computeMusInterval,
  computeSampleSize,
  markHighValueItems,
  projectMisstatement,
  computeUpperMisstatementLimit,
  deriveSamplingConclusion,
  reconcilePopulation,
  validateSamplingConfig,
  computeVersionDiff,
  CAS1314_RELIABILITY_TABLE,
  type SampledVoucher,
  type SamplingConfig,
  type SamplingMethod,
  type Phase,
  type FillMode,
  type EditTrailEntry,
} from '../useSamplingAlgorithms'
import { applyFillMode } from '../useVoucherSampling'
import { filterByCutoffWindow, markCutoffCrossPeriod } from '../useCutoffAutoSampling'

const RUNS = { numRuns: 5 }

// ─── Shared Generators ─────────────────────────────────────────────────────

/** 置信度取自 CAS1314 表的精确档位，避免最近邻映射歧义 */
const arbConfidence: fc.Arbitrary<number> = fc.constantFrom(
  ...CAS1314_RELIABILITY_TABLE.map((r) => r.confidence),
)

/** 构造 SampledVoucher（可指定 phase / 金额 / 错报 / 高值标识） */
function sampledVoucherArb(opts?: {
  phase?: Phase
  isHighValue?: boolean
}): fc.Arbitrary<SampledVoucher> {
  return fc.record({
    voucherNo: fc.string({ minLength: 1, maxLength: 8 }),
    voucherDate: fc.constant('2025-06-30'),
    summary: fc.constant<string | null>(null),
    debitAmount: fc.integer({ min: 0, max: 500000 }).map((n) => String(n)),
    creditAmount: fc.constant<string | null>('0'),
    accountCode: fc.constant('2203'),
    accountName: fc.constant<string | null>(null),
    counterpartAccount: fc.constant<string | null>(null),
    voucherType: fc.constant<string | null>(null),
    accountingPeriod: fc.constant<number | null>(6),
    checkResult: fc.constant('' as const),
    abnormal: fc.constant(false),
    remark: fc.constant(''),
    selected: fc.boolean(),
    phase: opts?.phase ? fc.constant(opts.phase) : fc.constantFrom('preliminary' as Phase, 'final' as Phase),
    editTrail: fc.constant([] as EditTrailEntry[]),
    isHighValue: opts?.isHighValue != null ? fc.constant(opts.isHighValue) : fc.boolean(),
    actualMisstatement: fc.integer({ min: 0, max: 500000 }).map((n) => String(n)),
  })
}

/** 唯一 voucherNo 数组（用于 Property 8） */
function uniqueVouchersArb(phase?: Phase, minLen = 0, maxLen = 6): fc.Arbitrary<SampledVoucher[]> {
  return fc
    .array(sampledVoucherArb({ phase }), { minLength: minLen, maxLength: maxLen })
    .map((vs) => {
      const seen = new Set<string>()
      return vs.filter((v) => (seen.has(v.voucherNo) ? false : (seen.add(v.voucherNo), true)))
    })
}

/** YYYY-MM-DD 格式化 */
function fmt(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 基准日 + offset 天 → YYYY-MM-DD */
function dateFromOffset(cutoff: string, offsetDays: number): string {
  const base = new Date(cutoff + 'T00:00:00')
  base.setDate(base.getDate() + offsetDays)
  return fmt(base)
}

// ═══════════════════════════════════════════════════════════════════════════
// Property 1: 样本量单调性
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 1: 样本量单调性', () => {
  /** **Validates: Requirements 15.1, 15.2** */

  it('可容忍错报增大 → 样本量不增', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 100000, max: 100000000 }).map(String), // populationAmount
        fc.integer({ min: 0, max: 1000 }).map(String), // expected（远小于 tolerable）
        fc.integer({ min: 5000, max: 50000 }), // t1 base
        fc.integer({ min: 5000, max: 50000 }), // delta
        arbConfidence,
        (pop, expected, t1, delta, conf) => {
          const tolLow = String(t1)
          const tolHigh = String(t1 + delta)
          const sizeLow = computeSampleSize(pop, tolLow, expected, conf)
          const sizeHigh = computeSampleSize(pop, tolHigh, expected, conf)
          expect(sizeHigh).toBeLessThanOrEqual(sizeLow)
        },
      ),
      RUNS,
    )
  })

  it('置信度提高 → 样本量不减', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 100000, max: 100000000 }).map(String),
        fc.integer({ min: 10000, max: 80000 }).map(String), // tolerable
        fc.integer({ min: 0, max: 1000 }).map(String), // expected
        (pop, tol, expected) => {
          const confidences = CAS1314_RELIABILITY_TABLE.map((r) => r.confidence)
          for (let i = 1; i < confidences.length; i++) {
            const sLow = computeSampleSize(pop, tol, expected, confidences[i - 1])
            const sHigh = computeSampleSize(pop, tol, expected, confidences[i])
            expect(sHigh).toBeGreaterThanOrEqual(sLow)
          }
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 2: MUS 间隔一致性
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 2: MUS 间隔一致性', () => {
  /** **Validates: Requirements 15.2, 17.1** */

  it('间隔 = 可容忍/可信赖度系数，且 > 0；样本量 = ceil(总体/间隔)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 100000, max: 100000000 }).map(String),
        fc.integer({ min: 10000, max: 100000 }).map(String), // tolerable
        fc.integer({ min: 0, max: 5000 }).map(String), // expected
        arbConfidence,
        (pop, tol, expected, conf) => {
          const interval = computeMusInterval(tol, conf, expected)
          const intervalNum = parseFloat(interval)

          // 间隔恒 > 0（tolerable > 0）
          expect(intervalNum).toBeGreaterThan(0)

          // 间隔 = tolerable / reliabilityFactor(conf, expected/tolerable)
          const load = new Decimal(expected).gt(0)
            ? new Decimal(expected).div(new Decimal(tol)).toNumber()
            : 0
          const rf = reliabilityFactor(conf, load)
          const expectedInterval = new Decimal(tol).div(rf).toNumber()
          expect(Math.abs(intervalNum - expectedInterval)).toBeLessThanOrEqual(0.01)

          // 样本量 = ceil(总体金额 / 间隔)
          const size = computeSampleSize(pop, tol, expected, conf)
          expect(size).toBe(Math.ceil(parseFloat(pop) / intervalNum))
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 3: 高值全选
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 3: 高值全选', () => {
  /** **Validates: Requirements 17.2, 17.3** */

  it('金额 ≥ 间隔者 isHighValue=true 且 selected=true；金额 < 间隔者不被强制选中', () => {
    fc.assert(
      fc.property(
        fc.array(sampledVoucherArb(), { minLength: 1, maxLength: 8 }),
        fc.integer({ min: 1, max: 300000 }).map(String), // interval
        (vouchers, interval) => {
          const intv = new Decimal(interval)
          const result = markHighValueItems(vouchers, interval)
          expect(result.length).toBe(vouchers.length)

          for (let i = 0; i < result.length; i++) {
            const v = result[i]
            const amount = Decimal.max(
              new Decimal(v.debitAmount || '0').abs(),
              new Decimal(v.creditAmount || '0').abs(),
            )
            if (amount.gte(intv)) {
              expect(v.isHighValue).toBe(true)
              expect(v.selected).toBe(true)
            } else {
              expect(v.isHighValue).toBe(false)
              // 未被强制选中：保留原 selected
              expect(v.selected).toBe(vouchers[i].selected)
            }
          }
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 4: 污染率有界 / projected 非负
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 4: 污染率有界', () => {
  /** **Validates: Requirements 18.2, 18.3** */

  it('projected ≥ 0（含 MUS/经典两法）', () => {
    fc.assert(
      fc.property(
        fc.array(sampledVoucherArb(), { minLength: 0, maxLength: 8 }),
        fc.constantFrom<SamplingMethod>('mus', 'random', 'systematic'),
        fc.integer({ min: 1000, max: 200000 }).map(String), // interval
        fc.integer({ min: 100000, max: 100000000 }).map(String), // population
        (samples, method, interval, pop) => {
          const r = projectMisstatement(samples, method, interval, pop)
          expect(new Decimal(r.projected).gte(0)).toBe(true)
          expect(new Decimal(r.knownHighValue).gte(0)).toBe(true)
        },
      ),
      RUNS,
    )
  })

  it('样本错报全为 0 → projected = 0', () => {
    fc.assert(
      fc.property(
        fc.array(sampledVoucherArb(), { minLength: 1, maxLength: 8 }),
        fc.constantFrom<SamplingMethod>('mus', 'random'),
        fc.integer({ min: 1000, max: 200000 }).map(String),
        (samples, method, interval) => {
          const zeroed = samples.map((s) => ({ ...s, actualMisstatement: '0' }))
          const r = projectMisstatement(zeroed, method, interval, '1000000')
          expect(new Decimal(r.projected).toNumber()).toBe(0)
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 5: 错报上限下界
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 5: 错报上限下界', () => {
  /** **Validates: Requirements 18.4** */

  it('UML ≥ projected ≥ 0', () => {
    fc.assert(
      fc.property(
        fc.array(sampledVoucherArb(), { minLength: 0, maxLength: 8 }),
        fc.constantFrom<SamplingMethod>('mus', 'random', 'systematic'),
        fc.integer({ min: 1000, max: 200000 }).map(String),
        fc.integer({ min: 100000, max: 100000000 }).map(String),
        (samples, method, interval, pop) => {
          const r = projectMisstatement(samples, method, interval, pop)
          const uml = computeUpperMisstatementLimit(r)
          expect(new Decimal(uml).gte(new Decimal(r.projected))).toBe(true)
          expect(new Decimal(r.projected).gte(0)).toBe(true)
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 6: 结论边界
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 6: 结论边界', () => {
  /** **Validates: Requirements 18.5, 18.6** */

  it('UML ≤ tolerable → accepted；UML > tolerable → 不接受', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1000000 }).map(String), // uml
        fc.integer({ min: 0, max: 1000000 }).map(String), // tolerable
        (uml, tol) => {
          const c = deriveSamplingConclusion(uml, tol)
          const expected = new Decimal(uml).lte(new Decimal(tol))
          expect(c.accepted).toBe(expected)
        },
      ),
      RUNS,
    )
  })

  it('边界 UML == tolerable → 视为可接受', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 1000000 }).map(String), (v) => {
        expect(deriveSamplingConclusion(v, v).accepted).toBe(true)
      }),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 7: 总体校验对称性
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 7: 总体校验对称性', () => {
  /** **Validates: Requirements 19.2, 19.3** */

  it('diff = |samplingPop − book|；withinThreshold = diff ≤ book × thresholdPct', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 100000000 }).map(String), // samplingPop
        fc.integer({ min: 1, max: 100000000 }).map(String), // book (>0)
        fc.constantFrom(0, 0.01, 0.05, 0.1), // thresholdPct
        (sp, book, pct) => {
          const r = reconcilePopulation(sp, book, pct)
          const expectedDiff = new Decimal(sp).minus(new Decimal(book)).abs()
          expect(new Decimal(r.diff).toNumber()).toBeCloseTo(expectedDiff.toNumber(), 2)
          const threshold = new Decimal(book).times(pct)
          expect(r.withinThreshold).toBe(expectedDiff.lte(threshold))
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 8: 填充模式守恒（既有 applyFillMode 回归）
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 8: 填充模式守恒', () => {
  /** **Validates: Requirements 7.3, 7.4, 7.5** */

  const arbFillMode: fc.Arbitrary<FillMode> = fc.constantFrom('append', 'replace', 'merge')

  it('append 结果长度 = 原 + 新', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb(undefined, 0, 6),
        uniqueVouchersArb('final', 1, 6),
        (existing, selected) => {
          const result = applyFillMode(existing, selected, 'append', 'final')
          expect(result.length).toBe(existing.length + selected.length)
        },
      ),
      RUNS,
    )
  })

  it('merge 后同 phase 内 voucherNo 唯一', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb('final', 1, 6),
        uniqueVouchersArb('final', 1, 6),
        (existing, selected) => {
          const result = applyFillMode(existing, selected, 'merge', 'final')
          const phaseNos = result.filter((v) => v.phase === 'final').map((v) => v.voucherNo)
          expect(new Set(phaseNos).size).toBe(phaseNos.length)
        },
      ),
      RUNS,
    )
  })

  it('replace 仅替换当前 phase 行，不动其他 phase', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb('preliminary', 1, 5),
        uniqueVouchersArb('final', 0, 5),
        uniqueVouchersArb('final', 1, 6),
        (preliminary, existingFinal, selected) => {
          const existing = [...preliminary, ...existingFinal]
          const result = applyFillMode(existing, selected, 'replace', 'final')
          const resultPre = result.filter((v) => v.phase === 'preliminary')
          expect(resultPre.length).toBe(preliminary.length)
          for (let i = 0; i < preliminary.length; i++) {
            expect(resultPre[i]).toEqual(preliminary[i])
          }
          expect(result.filter((v) => v.phase === 'final').length).toBe(selected.length)
        },
      ),
      RUNS,
    )
  })

  it('三模式结果均为 existing ∪ selected 的子集', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb(undefined, 0, 6),
        uniqueVouchersArb('preliminary', 1, 5),
        arbFillMode,
        (existing, selected, mode) => {
          const result = applyFillMode(existing, selected, mode, 'preliminary')
          const allNos = new Set([
            ...existing.map((v) => v.voucherNo),
            ...selected.map((v) => v.voucherNo),
          ])
          for (const item of result) {
            expect(allNos.has(item.voucherNo)).toBe(true)
          }
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 9: 版本 diff 互斥完备（既有 computeVersionDiff 回归）
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 9: 版本 diff 互斥完备', () => {
  /** **Validates: Requirements 9.3** */

  const arbNos = fc.array(fc.string({ minLength: 1, maxLength: 8 }), { minLength: 0, maxLength: 15 })

  it('added / removed / retained 互斥且并集 = A ∪ B', () => {
    fc.assert(
      fc.property(arbNos, arbNos, (a, b) => {
        const { added, removed, retained } = computeVersionDiff(a, b)
        const addedSet = new Set(added)
        const removedSet = new Set(removed)
        const retainedSet = new Set(retained)

        // 互斥
        for (const v of addedSet) {
          expect(removedSet.has(v)).toBe(false)
          expect(retainedSet.has(v)).toBe(false)
        }
        for (const v of removedSet) {
          expect(retainedSet.has(v)).toBe(false)
        }

        // 完备：并集 = A ∪ B
        const union = new Set([...a, ...b])
        const resultUnion = new Set([...added, ...removed, ...retained])
        expect(resultUnion.size).toBe(union.size)
        for (const v of union) expect(resultUnion.has(v)).toBe(true)
      }),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 10: 参数校验
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 10: 参数校验', () => {
  /** **Validates: Requirements 20.2, 20.3** */

  it('预期错报 ≥ 可容忍错报 → 校验失败', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 10000, max: 100000 }), // tolerable
        fc.integer({ min: 0, max: 50000 }), // extra (expected = tolerable + extra ≥ tolerable)
        (tol, extra) => {
          const config: SamplingConfig = {
            samplingMethod: 'mus',
            musSampleSize: 30,
            accountCodes: ['2203'],
            periodRange: [1, 2, 3],
            directionFilter: 'all',
            voucherTypeFilter: [],
            summaryKeyword: '',
            excludeExtracted: true,
            confidenceLevel: 0.95,
            tolerableMisstatement: String(tol),
            expectedMisstatement: String(tol + extra),
          }
          const errors = validateSamplingConfig(config)
          expect(errors.expectedMisstatement).toBeTruthy()
        },
      ),
      RUNS,
    )
  })

  it('统计法（mus）缺置信度或可容忍错报 → 校验失败', () => {
    fc.assert(
      fc.property(fc.boolean(), fc.boolean(), (dropConfidence, dropTolerable) => {
        // 至少丢一个必填项
        const missConfidence = dropConfidence || (!dropConfidence && !dropTolerable)
        const config: SamplingConfig = {
          samplingMethod: 'mus',
          musSampleSize: 30,
          accountCodes: ['2203'],
          periodRange: [1, 2, 3],
          directionFilter: 'all',
          voucherTypeFilter: [],
          summaryKeyword: '',
          excludeExtracted: true,
          confidenceLevel: missConfidence ? undefined : 0.95,
          tolerableMisstatement: dropTolerable ? undefined : '50000',
        }
        const errors = validateSamplingConfig(config)
        if (missConfidence) expect(errors.confidenceLevel).toBeTruthy()
        if (dropTolerable) expect(errors.tolerableMisstatement).toBeTruthy()
      }),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 11: 截止窗口过滤边界
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 11: 截止窗口过滤边界', () => {
  /** **Validates: Requirements 25.1, 25.3** */

  it('结果内每张凭证日期落在 [cutoff−daysBefore, cutoff+daysAfter]，窗口外一律排除', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('2025-12-31', '2025-06-30', '2026-01-15'), // cutoffDate
        fc.integer({ min: 0, max: 15 }), // daysBefore
        fc.integer({ min: 0, max: 15 }), // daysAfter
        fc.array(fc.integer({ min: -40, max: 40 }), { minLength: 0, maxLength: 12 }), // 相对基准日偏移
        (cutoff, daysBefore, daysAfter, offsets) => {
          const vouchers = offsets.map((off, i) => ({
            voucherNo: `V${i}`,
            voucherDate: dateFromOffset(cutoff, off),
          }))
          const result = filterByCutoffWindow(vouchers, cutoff, daysBefore, daysAfter)

          const cutoffMs = new Date(cutoff + 'T00:00:00').getTime()
          const lowMs = cutoffMs - daysBefore * 86400000
          const highMs = cutoffMs + daysAfter * 86400000

          // 结果内均在窗口内
          for (const v of result) {
            const d = new Date(v.voucherDate + 'T00:00:00').getTime()
            expect(d).toBeGreaterThanOrEqual(lowMs)
            expect(d).toBeLessThanOrEqual(highMs)
          }

          // 窗口外的输入均被排除
          const resultNos = new Set(result.map((v) => v.voucherNo))
          for (const v of vouchers) {
            const d = new Date(v.voucherDate + 'T00:00:00').getTime()
            const inside = d >= lowMs && d <= highMs
            expect(resultNos.has(v.voucherNo)).toBe(inside)
          }
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 12: 跨期判定位置单调
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-check-sampling-integration, Property 12: 跨期判定位置单调', () => {
  /** **Validates: Requirements 25.5** */

  it('记账日期与业务发生日期分居基准日两侧 → true；同侧 → false', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('2025-12-31', '2025-06-30'), // cutoff
        fc.integer({ min: -30, max: 30 }), // 记账日期偏移
        fc.integer({ min: -30, max: 30 }), // 业务发生日期偏移
        (cutoff, bookOff, bizOff) => {
          const v = {
            voucherNo: 'X',
            voucherDate: dateFromOffset(cutoff, bookOff),
            businessDate: dateFromOffset(cutoff, bizOff),
          }
          // side: offset > 0 视为"期后"，offset ≤ 0 视为"期内/当日"
          const bookAfter = bookOff > 0
          const bizAfter = bizOff > 0
          const expected = bookAfter !== bizAfter
          expect(markCutoffCrossPeriod(v, cutoff)).toBe(expected)
        },
      ),
      RUNS,
    )
  })

  it('单日期降级：无业务发生日期时，记账日落在基准日之后 → 跨期疑点', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('2025-12-31', '2025-06-30'),
        fc.integer({ min: -30, max: 30 }),
        (cutoff, bookOff) => {
          const v = { voucherNo: 'X', voucherDate: dateFromOffset(cutoff, bookOff) }
          expect(markCutoffCrossPeriod(v, cutoff)).toBe(bookOff > 0)
        },
      ),
      RUNS,
    )
  })
})
