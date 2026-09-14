/**
 * G8-6 凭证检查 — 异常判定 / 三态核对 / 默认未测
 */
import { describe, it, expect } from 'vitest'
import {
  enrichG8VoucherRow,
  recalcG8VoucherAbnormal,
  parseG8CheckState,
  formatG8CheckState,
  isG8VoucherFullyChecked,
  countG8VoucherUntested,
  parseG8SamplingParams,
  mapSampledToG8VoucherRow,
  computeG8AnomalyRate,
  calcG8SampleAbsAmount,
  calcG8CoverageRates,
  calcG8VoucherCompletion,
  buildG8VoucherSamplingMemo,
  mapG8OcrToVoucherFields,
  computeG8OcrMergePatch,
  extractG8OcrPayload,
  renderG8OcrPreview,
  type G8VoucherRow,
} from '../useG8VoucherCheck'
import { isG8SheetComplete } from '../g8SheetLabels'
import { mapCutoffToG8Voucher } from '../gCycleCutoffFill'
import type { ExtractedVoucher } from '../useCutoffAutoSampling'

function allPass(overrides: Partial<G8VoucherRow> = {}): G8VoucherRow {
  return enrichG8VoucherRow({
    voucherNo: '记-001',
    check1OriginalComplete: true,
    check2Authorization: true,
    check3Accounting: true,
    check4FairValueCorrect: true,
    check5OCICorrect: true,
    ...overrides,
  }, 1)
}

describe('parseG8CheckState', () => {
  it('空值与未测 → null', () => {
    expect(parseG8CheckState(null)).toBeNull()
    expect(parseG8CheckState(undefined)).toBeNull()
    expect(parseG8CheckState('')).toBeNull()
    expect(parseG8CheckState('未测')).toBeNull()
  })

  it('是/否映射', () => {
    expect(parseG8CheckState(true)).toBe(true)
    expect(parseG8CheckState('是')).toBe(true)
    expect(parseG8CheckState(false)).toBe(false)
    expect(parseG8CheckState('否')).toBe(false)
  })
})

describe('enrichG8VoucherRow 默认未测', () => {
  it('新建行核对项默认为 null', () => {
    const row = enrichG8VoucherRow({ voucherNo: '记-1' }, 1)
    expect(row.check1OriginalComplete).toBeNull()
    expect(row.check5OCICorrect).toBeNull()
    expect(row.isAbnormal).toBe(false)
    expect(row.forceAbnormal).toBe(false)
    expect(isG8VoucherFullyChecked(row)).toBe(false)
  })

  it('旧数据显式 true 保持通过', () => {
    const row = enrichG8VoucherRow({
      voucherNo: '记-2',
      check1OriginalComplete: true,
      check2Authorization: true,
      check3Accounting: true,
      check4FairValueCorrect: true,
      check5OCICorrect: true,
    }, 1)
    expect(row.isAbnormal).toBe(false)
    expect(isG8VoucherFullyChecked(row)).toBe(true)
  })
})

describe('recalcG8VoucherAbnormal 无粘滞', () => {
  it('未测不计入异常', () => {
    const row = enrichG8VoucherRow({ voucherNo: 'x' }, 1)
    expect(row.isAbnormal).toBe(false)
  })

  it('任一不通过 → 异常', () => {
    const row = allPass({ check4FairValueCorrect: false })
    expect(row.isAbnormal).toBe(true)
  })

  it('核对全部改回通过后异常自动清除（无 force）', () => {
    let row = allPass({ check3Accounting: false })
    expect(row.isAbnormal).toBe(true)
    row = recalcG8VoucherAbnormal({
      ...row,
      check3Accounting: true,
      forceAbnormal: false,
    })
    expect(row.isAbnormal).toBe(false)
  })

  it('forceAbnormal 在核对通过后仍保持异常，取消 force 后清除', () => {
    let row = allPass({ forceAbnormal: true })
    expect(row.isAbnormal).toBe(true)
    row = recalcG8VoucherAbnormal({ ...row, forceAbnormal: false })
    expect(row.isAbnormal).toBe(false)
  })
})

describe('formatG8CheckState / countG8VoucherUntested', () => {
  it('格式化三态', () => {
    expect(formatG8CheckState(true)).toBe('✓')
    expect(formatG8CheckState(false)).toBe('✗')
    expect(formatG8CheckState(null)).toBe('未测')
  })

  it('统计未测笔数', () => {
    const rows = [
      enrichG8VoucherRow({ voucherNo: 'a' }, 1),
      allPass(),
    ]
    expect(countG8VoucherUntested(rows)).toBe(1)
  })
})

describe('mapCutoffToG8Voucher', () => {
  it('回填默认未测；可能跨期用 forceAbnormal', () => {
    const v = {
      voucherDate: '2025-01-05',
      voucherNo: '记-88',
      summary: '购入股权',
      debitAmount: '100',
      creditAmount: '0',
      accountCode: '1503',
      accountName: '其他权益工具投资',
      counterpartAccount: null,
      voucherType: null,
      cutoffStatus: '可能跨期' as const,
      remark: '',
      selected: true,
    } satisfies ExtractedVoucher
    const row = mapCutoffToG8Voucher(v, 1)
    expect(row.check1OriginalComplete).toBeNull()
    expect(row.forceAbnormal).toBe(true)
    expect(row.isAbnormal).toBe(true)
    expect(row.source).toBe('截止')
  })

  it('非跨期不强制异常', () => {
    const v = {
      voucherDate: '2025-01-05',
      voucherNo: '记-89',
      summary: '正常',
      debitAmount: null,
      creditAmount: null,
      accountCode: '1503',
      accountName: null,
      counterpartAccount: null,
      voucherType: null,
      cutoffStatus: '正常' as const,
      remark: '',
      selected: true,
    } satisfies ExtractedVoucher
    const row = mapCutoffToG8Voucher(v, 2)
    expect(row.forceAbnormal).toBe(false)
    expect(row.isAbnormal).toBe(false)
  })
})

describe('抽样参数 / mapSampledToG8VoucherRow', () => {
  it('parseG8SamplingParams 容错默认', () => {
    expect(parseG8SamplingParams(null).targetSampleSize).toBe(0)
    expect(parseG8SamplingParams('{bad').samplingMethod).toBe('')
    const p = parseG8SamplingParams(JSON.stringify({
      testPopulation: '1503本期',
      targetSampleSize: 10,
      currentSampleSize: 3,
      samplingMethod: 'mus',
    }))
    expect(p.testPopulation).toBe('1503本期')
    expect(p.targetSampleSize).toBe(10)
    expect(p.currentSampleSize).toBe(3)
    expect(p.samplingMethod).toBe('mus')
  })

  it('抽凭样本映射借贷字段且默认未测', () => {
    const row = mapSampledToG8VoucherRow({
      voucherNo: '记-10',
      voucherDate: '2025-06-01',
      summary: '增资',
      debitAmount: '50000',
      creditAmount: '0',
      counterpartAccount: '1002',
      isHighValue: true,
    }, 1)
    expect(row.debitAmount).toBe(50000)
    expect(row.creditAmount).toBe(0)
    expect(row.counterAccount).toBe('1002')
    expect(row.check1OriginalComplete).toBeNull()
    expect(row.source).toBe('抽凭')
    expect(row.remark).toBe('高值必选')
  })

  it('computeG8AnomalyRate', () => {
    expect(computeG8AnomalyRate([])).toBe(0)
    const rows = [
      enrichG8VoucherRow({ voucherNo: 'a', check1OriginalComplete: false }, 1),
      enrichG8VoucherRow({
        voucherNo: 'b',
        check1OriginalComplete: true,
        check2Authorization: true,
        check3Accounting: true,
        check4FairValueCorrect: true,
        check5OCICorrect: true,
      }, 2),
    ]
    expect(computeG8AnomalyRate(rows)).toBe(50)
  })
})

describe('覆盖率 / 完成度 / 备忘', () => {
  it('calcG8SampleAbsAmount 取单边较大值', () => {
    expect(calcG8SampleAbsAmount([
      { debitAmount: 100, creditAmount: 0 },
      { debitAmount: 0, creditAmount: 50 },
    ])).toBe(150)
  })

  it('calcG8CoverageRates', () => {
    const rows = [
      enrichG8VoucherRow({ voucherNo: '1', debitAmount: 100, source: '抽凭' }, 1),
      enrichG8VoucherRow({ voucherNo: '2', debitAmount: 100, source: '抽凭' }, 2),
    ]
    const cov = calcG8CoverageRates(rows, {
      targetSampleSize: 10,
      currentSampleSize: 2,
      populationCount: 20,
      populationAmount: 1000,
    })
    expect(cov.countPct).toBe(10)
    expect(cov.amountPct).toBe(20)
    expect(cov.sampleAbsAmount).toBe(200)
  })

  it('calcG8VoucherCompletion 权重累计', () => {
    const empty = calcG8VoucherCompletion({
      params: parseG8SamplingParams(null),
      rows: [],
      conclusion: '',
    })
    expect(empty.pct).toBe(0)
    const full = calcG8VoucherCompletion({
      params: {
        ...parseG8SamplingParams(null),
        samplingMethod: 'mus',
        targetSampleSize: 2,
        currentSampleSize: 2,
      },
      rows: [
        enrichG8VoucherRow({
          voucherNo: '1', source: '抽凭',
          check1OriginalComplete: true,
          check2Authorization: true,
          check3Accounting: true,
          check4FairValueCorrect: true,
          check5OCICorrect: true,
        }, 1),
        enrichG8VoucherRow({
          voucherNo: '2', source: '抽凭',
          check1OriginalComplete: true,
          check2Authorization: true,
          check3Accounting: true,
          check4FairValueCorrect: true,
          check5OCICorrect: true,
        }, 2),
      ],
      conclusion: '未见异常',
    })
    expect(full.pct).toBe(100)
  })

  it('buildG8VoucherSamplingMemo 含关键段落', () => {
    const memo = buildG8VoucherSamplingMemo({
      params: {
        ...parseG8SamplingParams(null),
        samplingMethod: 'random',
        targetSampleSize: 5,
        currentSampleSize: 2,
        populationAmount: 10000,
      },
      rows: [enrichG8VoucherRow({ voucherNo: '记-1', debitAmount: 500, source: '抽凭' }, 1)],
      conclusion: '测试结论',
      coverage: { countPct: 40, amountPct: 5, sampleAbsAmount: 500 },
    })
    expect(memo).toContain('抽样参数')
    expect(memo).toContain('覆盖率')
    expect(memo).toContain('测试结论')
    expect(memo).toContain('随机抽样')
  })
})

describe('isG8SheetComplete G8-6', () => {
  function mapOf(entries: Array<[string, { conclusion?: string | null; remark?: string | null }]>) {
    return new Map(entries.map(([k, v]) => [k, { item_id: k, conclusion: v.conclusion ?? null, remark: v.remark ?? null }]))
  }

  const checkedRow = {
    check1OriginalComplete: true,
    check2Authorization: true,
    check3Accounting: true,
    check4FairValueCorrect: true,
    check5OCICorrect: true,
  }
  const untestedRow = {
    check1OriginalComplete: null,
    check2Authorization: null,
    check3Accounting: null,
    check4FairValueCorrect: null,
    check5OCICorrect: null,
  }

  it('仅结论或仅一行已测 → 未完成', () => {
    expect(isG8SheetComplete('G8-6', mapOf([
      ['G8-voucher-rows', { remark: JSON.stringify([untestedRow]) }],
      ['G8-voucher-conclusion', { conclusion: '结论' }],
    ]))).toBe(false)
    expect(isG8SheetComplete('G8-6', mapOf([
      ['G8-voucher-rows', { remark: JSON.stringify([checkedRow, untestedRow]) }],
    ]))).toBe(false)
  })

  it('全部已测 + 结论 → 完成', () => {
    expect(isG8SheetComplete('G8-6', mapOf([
      ['G8-voucher-rows', { remark: JSON.stringify([checkedRow, { ...checkedRow, check4FairValueCorrect: false }]) }],
      ['G8-voucher-conclusion', { conclusion: '存在公允计量差异，建议进一步核实。' }],
    ]))).toBe(true)
  })
})

describe('G8 OCR 映射', () => {
  it('mapG8OcrToVoucherFields 映射多字段与金额', () => {
    const { patch, lowConfidence } = mapG8OcrToVoucherFields({
      凭证日期: '2025-03-01',
      凭证编号: '记-88',
      摘要: '购入乙公司股权',
      对方科目: '银行存款',
      借方金额: '1,200.50',
      被投资单位: '乙公司',
    }, 0.95)
    expect(patch.voucherDate).toBe('2025-03-01')
    expect(patch.voucherNo).toBe('记-88')
    expect(patch.businessContent).toBe('购入乙公司股权')
    expect(patch.counterAccount).toBe('银行存款')
    expect(patch.debitAmount).toBe(1200.5)
    expect(patch.investeeName).toBe('乙公司')
    expect(lowConfidence).toEqual([])
  })

  it('支持 {value,confidence} 并标记低置信度', () => {
    const { patch, lowConfidence } = mapG8OcrToVoucherFields({
      voucherNo: { value: '记-1', confidence: 0.5 },
      summary: { value: '摘要', confidence: 0.9 },
    }, 0.9)
    expect(patch.voucherNo).toBe('记-1')
    expect(patch.businessContent).toBe('摘要')
    expect(lowConfidence).toContain('voucherNo')
    expect(lowConfidence).not.toContain('businessContent')
  })

  it('computeG8OcrMergePatch 不覆盖已填字段', () => {
    const merged = computeG8OcrMergePatch(
      {
        voucherDate: '2025-01-01',
        voucherNo: '',
        businessContent: '已有',
        counterAccount: '',
        debitAmount: 0,
        creditAmount: 100,
        investeeName: '',
        supportingDocDesc: '',
      },
      {
        voucherDate: '2025-06-01',
        voucherNo: '记-9',
        businessContent: 'OCR摘要',
        debitAmount: 500,
        creditAmount: 999,
      },
    )
    expect(merged.voucherDate).toBeUndefined()
    expect(merged.voucherNo).toBe('记-9')
    expect(merged.businessContent).toBeUndefined()
    expect(merged.debitAmount).toBe(500)
    expect(merged.creditAmount).toBeUndefined()
  })

  it('extractG8OcrPayload 兼容 summary 与 extracted_fields', () => {
    expect(extractG8OcrPayload({ data: { summary: '仅摘要' } }).fields.summary).toBe('仅摘要')
    expect(extractG8OcrPayload({
      data: { extracted_fields: { 凭证号: '记-2' }, confidence: 0.7 },
    })).toEqual({ fields: { 凭证号: '记-2' }, confidence: 0.7 })
  })

  it('renderG8OcrPreview 含置信度与字段', () => {
    const html = renderG8OcrPreview(
      { voucherNo: '记-1', debitAmount: 10 },
      ['voucherNo'],
      0.6,
    )
    expect(html).toContain('60%')
    expect(html).toContain('凭证编号')
    expect(html).toContain('需人工复核')
  })
})
