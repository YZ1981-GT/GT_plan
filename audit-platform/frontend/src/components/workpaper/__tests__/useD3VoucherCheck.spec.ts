/**
 * useD3VoucherCheck PBT 测试
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 覆盖 D3-7 凭证检查核心逻辑：异常率计算 + 跨期自动标记。
 *
 * 测试纯函数逻辑（computeAnomalyRate, shouldMarkCrossPeriod），不依赖 Vue 响应式。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  computeAnomalyRate,
  shouldMarkCrossPeriod,
  mapOcrToVoucherFields,
  isAllowedAttachment,
  mapSampledToVoucherRow,
  applyVoucherFillMode,
  summarizeAnomalies,
  computeCoverageFeedback,
  CONFIDENCE_THRESHOLD,
  CROSS_PERIOD_ANOMALY,
  type VoucherCheckRow,
} from '../composables/useD3VoucherCheck'

// ─── Generators ──────────────────────────────────────────────────────────────

/** isAbnormal 随机赋值（空字符串或非空字符串） */
const isAbnormalArb = fc.oneof(
  fc.constant(''),
  fc.constantFrom('跨期疑点', '金额异常', '凭证缺失', '对方科目异常'),
)

/** VoucherRow（仅异常率相关字段）生成器 */
const voucherRowArb = fc.record({
  isAbnormal: isAbnormalArb,
})

/** 日期生成器：合理范围内的日期 */
const dateArb = fc.date({
  min: new Date('2020-01-01'),
  max: new Date('2030-12-31'),
})

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD3VoucherCheck - Property-Based Tests', () => {
  /**
   * **Feature: d3-prepaid-accounts, Property 19: 凭证检查异常率计算正确性**
   *
   * For any 凭证检查行列表，anomalyRate应等于（isAbnormal非空行数 / 总行数 × 100%）。
   *
   * **Validates: Requirements 11.5**
   */
  describe('Property 19: 凭证检查异常率计算正确性', () => {
    it('anomalyRate === 非空异常行数/总行数×100', () => {
      fc.assert(
        fc.property(
          fc.array(voucherRowArb, { minLength: 1, maxLength: 50 }),
          (rows) => {
            const result = computeAnomalyRate(rows)

            // Manual calculation
            const anomalyCount = rows.filter(r => r.isAbnormal !== '').length
            const expectedRate = (anomalyCount / rows.length) * 100

            expect(result).toBeCloseTo(expectedRate, 10)
          }
        ),
        { numRuns: 100 }
      )
    })

    it('空数组时 anomalyRate = 0', () => {
      expect(computeAnomalyRate([])).toBe(0)
    })

    it('全部为空异常时 anomalyRate = 0', () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 50 }),
          (n) => {
            const rows = Array.from({ length: n }, () => ({ isAbnormal: '' }))
            expect(computeAnomalyRate(rows)).toBe(0)
          }
        ),
        { numRuns: 100 }
      )
    })

    it('全部非空异常时 anomalyRate = 100', () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 50 }),
          (n) => {
            const rows = Array.from({ length: n }, () => ({ isAbnormal: '异常' }))
            expect(computeAnomalyRate(rows)).toBeCloseTo(100, 10)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d3-prepaid-accounts, Property 20: 期后结转跨期自动标记**
   *
   * For any 期后结转检查行，当凭证日期早于对应收入确认日期时，
   * shouldMarkCrossPeriod 应返回 true。
   *
   * **Validates: Requirements 11.7**
   */
  describe('Property 20: 期后结转跨期自动标记', () => {
    it('voucherDate < revenueDate → 返回true', () => {
      fc.assert(
        fc.property(
          dateArb,
          dateArb,
          (voucherDate, revenueDate) => {
            const result = shouldMarkCrossPeriod(voucherDate, revenueDate)

            if (voucherDate < revenueDate) {
              expect(result).toBe(true)
            } else {
              expect(result).toBe(false)
            }
          }
        ),
        { numRuns: 100 }
      )
    })

    it('相同日期时返回false', () => {
      fc.assert(
        fc.property(
          dateArb,
          (date) => {
            const sameDateCopy = new Date(date.getTime())
            expect(shouldMarkCrossPeriod(date, sameDateCopy)).toBe(false)
          }
        ),
        { numRuns: 100 }
      )
    })

    it('voucherDate > revenueDate → 返回false', () => {
      fc.assert(
        fc.property(
          dateArb,
          fc.integer({ min: 1, max: 365 }),
          (revenueDate, daysAfter) => {
            const voucherDate = new Date(revenueDate.getTime() + daysAfter * 86400000)
            expect(shouldMarkCrossPeriod(voucherDate, revenueDate)).toBe(false)
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})

// ─── OCR 字段映射单元测试（Task 6 / Req 2.2, 2.8, 1.5） ──────────────────────

describe('mapOcrToVoucherFields - OCR 字段映射', () => {
  it('中文键映射到 VoucherCheckRow 字段', () => {
    const { patch } = mapOcrToVoucherFields({
      客户名称: '甲公司',
      凭证号: 'JZ-001',
      业务内容: '预收货款',
      贷方金额: '10000',
    })
    expect(patch.customerName).toBe('甲公司')
    expect(patch.voucherNo).toBe('JZ-001')
    expect(patch.businessContent).toBe('预收货款')
    expect(patch.creditAmount).toBe(10000)
  })

  it('未知键与空值被跳过', () => {
    const { patch } = mapOcrToVoucherFields({
      未知字段: 'xyz',
      客户名称: '   ',
      凭证号: 'JZ-002',
    })
    expect(patch).toEqual({ voucherNo: 'JZ-002' })
  })

  it('金额解析为 0 时跳过（视为无有效值）', () => {
    const { patch } = mapOcrToVoucherFields({ 贷方金额: 'abc', 借方金额: '0' })
    expect(patch.creditAmount).toBeUndefined()
    expect(patch.debitAmount).toBeUndefined()
  })

  it('整体置信度低于阈值 → 所有映射字段计入 lowConfidence', () => {
    const conf = CONFIDENCE_THRESHOLD - 0.1
    const { patch, lowConfidence } = mapOcrToVoucherFields({ 客户名称: '甲', 凭证号: 'A1' }, conf)
    expect(Object.keys(patch).sort()).toEqual(['customerName', 'voucherNo'])
    expect(lowConfidence.sort()).toEqual(['customerName', 'voucherNo'])
  })

  it('整体置信度高于阈值 → lowConfidence 为空', () => {
    const { lowConfidence } = mapOcrToVoucherFields({ 客户名称: '甲' }, 0.95)
    expect(lowConfidence).toEqual([])
  })

  it('支持 { value, confidence } 逐字段置信度', () => {
    const { patch, lowConfidence } = mapOcrToVoucherFields({
      客户名称: { value: '甲公司', confidence: 0.99 },
      凭证号: { value: 'JZ-9', confidence: 0.5 },
    })
    expect(patch.customerName).toBe('甲公司')
    expect(patch.voucherNo).toBe('JZ-9')
    expect(lowConfidence).toEqual(['voucherNo'])
  })
})

// ─── 抽凭回填映射与三模式（Task 7 / Req 7.2~7.6, 24.5） ──────────────────────

describe('mapSampledToVoucherRow - 抽样样本 → 检查表行', () => {
  it('映射凭证号/日期/金额/摘要/对方科目并标注来源=抽凭', () => {
    const row = mapSampledToVoucherRow({
      voucherNo: 'JZ-100',
      voucherDate: '2025-06-15',
      summary: '预收货款',
      counterpartAccount: '1002',
      debitAmount: null,
      creditAmount: '8888.50',
    })
    expect(row.voucherNo).toBe('JZ-100')
    expect(row.date).toBe('2025-06-15')
    expect(row.businessContent).toBe('预收货款')
    expect(row.counterAccount).toBe('1002')
    expect(row.creditAmount).toBe(8888.5)
    expect(row.debitAmount).toBeUndefined()
    expect(row.source).toBe('抽凭')
  })

  it('缺省字段安全降级为空值', () => {
    const row = mapSampledToVoucherRow({ voucherNo: 'JZ-1' })
    expect(row.voucherNo).toBe('JZ-1')
    expect(row.date).toBe('')
    expect(row.creditAmount).toBe(0)
    expect(row.source).toBe('抽凭')
  })
})

describe('applyVoucherFillMode - 抽凭回填三模式', () => {
  const mk = (no: string): VoucherCheckRow => mapSampledToVoucherRow({ voucherNo: no })

  it('append: 追加到末尾，长度 = 原 + 新', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 6 }), { maxLength: 10 }),
        fc.array(fc.string({ minLength: 1, maxLength: 6 }), { maxLength: 10 }),
        (a, b) => {
          const existing = a.map(mk)
          const incoming = b.map(mk)
          const result = applyVoucherFillMode(existing, incoming, 'append')
          expect(result.length).toBe(existing.length + incoming.length)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('replace: 以新集合替换现有行', () => {
    const existing = ['A', 'B'].map(mk)
    const incoming = ['C', 'D', 'E'].map(mk)
    const result = applyVoucherFillMode(existing, incoming, 'replace')
    expect(result.map(r => r.voucherNo)).toEqual(['C', 'D', 'E'])
  })

  it('merge: 按 voucherNo 去重，不重复添加已存在项', () => {
    const existing = ['A', 'B'].map(mk)
    const incoming = ['B', 'C'].map(mk)
    const result = applyVoucherFillMode(existing, incoming, 'merge')
    expect(result.map(r => r.voucherNo)).toEqual(['A', 'B', 'C'])
  })

  it('merge: 结果中非空 voucherNo 唯一', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 4 }), { maxLength: 12 }),
        fc.array(fc.string({ minLength: 1, maxLength: 4 }), { maxLength: 12 }),
        (a, b) => {
          // merge 契约：仅阻止「新增」重复，不对既有行做破坏性去重（既有行可能含
          // 用户手工录入的重复凭证号，静默删除即数据丢失）。故约束既有行 voucherNo
          // 唯一（与 canonical Property 8 的 uniqueVouchersArb 前置一致），验证 merge 后仍唯一。
          const uniqExisting = Array.from(new Set(a))
          const result = applyVoucherFillMode(uniqExisting.map(mk), b.map(mk), 'merge')
          const nos = result.map(r => r.voucherNo).filter(Boolean)
          expect(new Set(nos).size).toBe(nos.length)
        },
      ),
      { numRuns: 50 },
    )
  })
})

// ─── 异常汇总与跨底稿联动（Task 8 / Req 11.1~11.4） ──────────────────────────

describe('summarizeAnomalies - 异常汇总', () => {
  it('统计总笔数、跨期疑点笔数、按类型分组', () => {
    const rows = [
      { isAbnormal: '跨期疑点' },
      { isAbnormal: '跨期疑点' },
      { isAbnormal: '金额异常' },
      { isAbnormal: '' },
      { isAbnormal: '无原始凭证' },
    ]
    const s = summarizeAnomalies(rows)
    expect(s.total).toBe(4)
    expect(s.crossPeriod).toBe(2)
    expect(s.byType).toEqual({ 跨期疑点: 2, 金额异常: 1, 无原始凭证: 1 })
  })

  it('空/无异常 → total=0、crossPeriod=0', () => {
    expect(summarizeAnomalies([])).toEqual({ total: 0, crossPeriod: 0, byType: {} })
    expect(summarizeAnomalies([{ isAbnormal: '' }, { isAbnormal: '' }]))
      .toEqual({ total: 0, crossPeriod: 0, byType: {} })
  })

  it('total 恒等于 byType 各计数之和；crossPeriod ≤ total（PBT）', () => {
    const typeArb = fc.oneof(
      fc.constant(''),
      fc.constantFrom(CROSS_PERIOD_ANOMALY, '金额异常', '无原始凭证', '对方科目异常', '重复入账'),
    )
    fc.assert(
      fc.property(fc.array(fc.record({ isAbnormal: typeArb }), { maxLength: 60 }), (rows) => {
        const s = summarizeAnomalies(rows)
        const sumByType = Object.values(s.byType).reduce((a, b) => a + b, 0)
        expect(sumByType).toBe(s.total)
        expect(s.crossPeriod).toBeLessThanOrEqual(s.total)
        expect(s.crossPeriod).toBe(s.byType[CROSS_PERIOD_ANOMALY] || 0)
      }),
      { numRuns: 100 },
    )
  })
})

describe('computeCoverageFeedback - 覆盖率反馈', () => {
  const mkRow = (over: Partial<VoucherCheckRow>): VoucherCheckRow => ({
    ...mapSampledToVoucherRow({ voucherNo: 'X' }),
    ...over,
  })

  it('目标样本量>0 时计算笔数覆盖率、核对完成率、金额合计', () => {
    const rows = [
      mkRow({ debitAmount: 100, creditAmount: 0, checkItems: [true, true, true, true, true] }),
      mkRow({ debitAmount: 0, creditAmount: 200, checkItems: [true, false, true, true, true] }),
    ]
    const fb = computeCoverageFeedback(rows, 4)
    expect(fb.checkedCount).toBe(2)
    expect(fb.targetSampleSize).toBe(4)
    expect(fb.countCoverageRate).toBe(50)
    expect(fb.completedCount).toBe(1)
    expect(fb.completionRate).toBe(50)
    expect(fb.checkedAmount).toBe(300)
    expect(fb.lowCoverage).toBe(true)
  })

  it('无目标样本量：有检查行→覆盖率100，无行→0', () => {
    const fb1 = computeCoverageFeedback([mkRow({})], 0)
    expect(fb1.countCoverageRate).toBe(100)
    expect(fb1.lowCoverage).toBe(false)
    const fb0 = computeCoverageFeedback([], 0)
    expect(fb0.countCoverageRate).toBe(0)
    expect(fb0.completionRate).toBe(0)
  })

  it('覆盖率上限 100 且 lowCoverage 与不足关系一致（PBT）', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 40 }),
        fc.integer({ min: 0, max: 40 }),
        (nRows, target) => {
          const rows = Array.from({ length: nRows }, () => mkRow({}))
          const fb = computeCoverageFeedback(rows, target)
          expect(fb.countCoverageRate).toBeLessThanOrEqual(100)
          expect(fb.countCoverageRate).toBeGreaterThanOrEqual(0)
          if (target > 0) {
            expect(fb.lowCoverage).toBe(nRows < target)
          } else {
            expect(fb.lowCoverage).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('isAllowedAttachment - 附件类型校验', () => {
  it('接受图片与 PDF（按 MIME）', () => {
    expect(isAllowedAttachment(new File([''], 'a.png', { type: 'image/png' }))).toBe(true)
    expect(isAllowedAttachment(new File([''], 'a.pdf', { type: 'application/pdf' }))).toBe(true)
  })

  it('MIME 缺失时按扩展名兜底', () => {
    expect(isAllowedAttachment(new File([''], 'scan.JPEG', { type: '' }))).toBe(true)
    expect(isAllowedAttachment(new File([''], 'doc.pdf', { type: '' }))).toBe(true)
  })

  it('拒绝非图片/PDF 类型', () => {
    expect(isAllowedAttachment(new File([''], 'a.txt', { type: 'text/plain' }))).toBe(false)
    expect(isAllowedAttachment(new File([''], 'a.docx', { type: '' }))).toBe(false)
  })
})
