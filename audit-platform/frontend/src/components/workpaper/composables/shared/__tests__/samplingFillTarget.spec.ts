/**
 * samplingFillTarget 共享件守卫（sampling-compliance-closure Wave 3 Task 17/18）
 *
 * Validates: Requirements 6.1, 6.2, 6.5
 * Properties: Property 16, Property 17
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  SAMPLING_METHOD_LABELS,
  SAMPLING_MIN_FIELDS,
  buildMethodologySummary,
  hasMethodologyContent,
  mapSampledRows,
  mapSampledToGenericRow,
  parseMethodology,
  samplingMethodLabel,
  samplingMethodologyItemKey,
  serializeMethodology,
  type SamplingMethodologySnapshot,
} from '../samplingFillTarget'

function makeMethodology(over?: Partial<SamplingMethodologySnapshot>): SamplingMethodologySnapshot {
  return {
    samplingMethod: 'mus',
    samplingInterval: '50000.00',
    sampleSize: 25,
    suggestedSampleSize: 27,
    tolerableMisstatement: '500000',
    expectedMisstatement: '100000',
    confidenceLevel: 0.95,
    accountCodes: ['1122'],
    randomSeed: '424242',
    batchId: 'batch-abcdef12',
    datasetId: 'ds-12345678',
    ...over,
  }
}

// ─── 持久化键 ────────────────────────────────────────────────────────────────

describe('samplingMethodologyItemKey', () => {
  it('按底稿编码构键（一底稿一条，最后一次抽样为准）', () => {
    expect(samplingMethodologyItemKey('D2')).toBe('D2-sampling-methodology')
    expect(samplingMethodologyItemKey('K8')).toBe('K8-sampling-methodology')
  })

  it('空 wpCode 回退到无前缀键而非产出 "-sampling-methodology"', () => {
    expect(samplingMethodologyItemKey('')).toBe('sampling-methodology')
    expect(samplingMethodologyItemKey('  ')).toBe('sampling-methodology')
  })

  it('不同底稿的键必不相同（防跨底稿互相覆盖）', () => {
    const keys = ['D2', 'D3', 'F3', 'K8', 'G7'].map(samplingMethodologyItemKey)
    expect(new Set(keys).size).toBe(keys.length)
  })
})

// ─── 方法名 ─────────────────────────────────────────────────────────────────

describe('samplingMethodLabel', () => {
  it('五种 canonical 方法都有中文名', () => {
    for (const m of ['random', 'stratified', 'specific_item', 'systematic', 'mus']) {
      expect(SAMPLING_METHOD_LABELS[m]).toBeTruthy()
      expect(samplingMethodLabel(m)).toBe(SAMPLING_METHOD_LABELS[m])
    }
  })

  it('未知方法原样返回（不吞掉未登记的新方法）', () => {
    expect(samplingMethodLabel('brand_new')).toBe('brand_new')
  })

  it('空值返回「未记录」而非空串', () => {
    expect(samplingMethodLabel(null)).toBe('未记录')
    expect(samplingMethodLabel('')).toBe('未记录')
  })

  it('取值域与后端 _METHOD_LABELS 的键一致', () => {
    expect(Object.keys(SAMPLING_METHOD_LABELS).sort()).toEqual(
      ['mus', 'random', 'specific_item', 'stratified', 'systematic'],
    )
  })
})

// ─── Property 17：渲染门控 ──────────────────────────────────────────────────

describe('hasMethodologyContent（bar 渲染门控）', () => {
  it('null / undefined / 空对象 → 无内容（bar 不渲染）', () => {
    expect(hasMethodologyContent(null)).toBe(false)
    expect(hasMethodologyContent(undefined)).toBe(false)
    expect(hasMethodologyContent({} as any)).toBe(false)
  })

  it('非对象输入不抛错', () => {
    expect(hasMethodologyContent('x' as any)).toBe(false)
    expect(hasMethodologyContent(5 as any)).toBe(false)
  })

  it('只要有方法/样本量/科目/间隔/种子任一即有内容', () => {
    expect(hasMethodologyContent({ samplingMethod: 'random' } as any)).toBe(true)
    expect(hasMethodologyContent({ sampleSize: 3 } as any)).toBe(true)
    expect(hasMethodologyContent({ accountCodes: ['1122'] } as any)).toBe(true)
    expect(hasMethodologyContent({ samplingInterval: '1' } as any)).toBe(true)
    expect(hasMethodologyContent({ randomSeed: '7' } as any)).toBe(true)
  })

  it('样本量为 0 且其余全空 → 无内容（0 不算"抽过样"）', () => {
    expect(hasMethodologyContent({ sampleSize: 0, accountCodes: [] } as any)).toBe(false)
  })
})

// ─── 摘要：只渲染有值项 ─────────────────────────────────────────────────────

describe('buildMethodologySummary', () => {
  it('齐备时含全部要素', () => {
    const text = buildMethodologySummary(makeMethodology())
    for (const token of ['方法=货币单元抽样', '科目=1122', '样本量=25', '系统建议=27',
                         '抽样间隔=50000.00', '可容忍错报=500000', '预期错报=100000',
                         '置信度=0.95', '随机种子=424242', '批次=batch-ab', '账套版本=ds-12345']) {
      expect(text).toContain(token)
    }
  })

  it('缺省项直接不出现，而不是显示「间隔: -」', () => {
    const text = buildMethodologySummary(
      makeMethodology({
        samplingInterval: null,
        suggestedSampleSize: null,
        tolerableMisstatement: null,
        expectedMisstatement: null,
        randomSeed: null,
        batchId: null,
        datasetId: null,
      }),
    )
    expect(text).not.toContain('抽样间隔')
    expect(text).not.toContain('随机种子')
    expect(text).not.toContain('账套版本')
    expect(text).not.toContain('-')       // 归档件上的「-」无法与「取不到」区分
    expect(text).toContain('方法=')       // 有值项仍在
  })

  it('null 方法学返回空串', () => {
    expect(buildMethodologySummary(null)).toBe('')
    expect(buildMethodologySummary(undefined)).toBe('')
  })

  it('PBT：任意输入都不抛错且返回字符串', () => {
    fc.assert(
      fc.property(fc.anything(), (v) => {
        expect(typeof buildMethodologySummary(v as any)).toBe('string')
      }),
      { numRuns: 20 },
    )
  })
})

// ─── 序列化往返 ─────────────────────────────────────────────────────────────

describe('serialize / parse 往返', () => {
  it('往返无损', () => {
    const m = makeMethodology()
    const parsed = parseMethodology(serializeMethodology(m))
    expect(parsed).toEqual(m)
  })

  it('空内容不落库（返回空串）', () => {
    expect(serializeMethodology(null)).toBe('')
    expect(serializeMethodology({} as any)).toBe('')
  })

  it('解析失败返回 null 而非半个对象', () => {
    expect(parseMethodology('{bad json')).toBeNull()
    expect(parseMethodology('')).toBeNull()
    expect(parseMethodology(null)).toBeNull()
    expect(parseMethodology('"just a string"')).toBeNull()
    expect(parseMethodology('123')).toBeNull()
  })

  it('解析出的空内容也返回 null（不把 {} 当有效方法学）', () => {
    expect(parseMethodology('{}')).toBeNull()
  })
})

// ─── Property 16：最小字段集映射 ────────────────────────────────────────────

describe('mapSampledToGenericRow（最小字段集）', () => {
  it('最小字段集恰为 6 项', () => {
    expect([...SAMPLING_MIN_FIELDS]).toEqual([
      'voucherNo', 'voucherDate', 'debitAmount', 'creditAmount', 'accountCode', 'summary',
    ])
  })

  it('camelCase 输入（抽凭引擎的 SampledVoucher）', () => {
    const row = mapSampledToGenericRow({
      voucherNo: 'V-1', voucherDate: '2025-06-01', debitAmount: '1000.5',
      creditAmount: null, accountCode: '1122', summary: '销售收款',
    })
    expect(row).toEqual({
      voucherNo: 'V-1', voucherDate: '2025-06-01', debitAmount: 1000.5,
      creditAmount: 0, accountCode: '1122', summary: '销售收款',
      // 往来单位（辅助明细账补全）：未提供时为空串 / false，不是 undefined ——
      // 宿主直接把它塞进「客户名称」列，undefined 会渲染成字符串 "undefined"
      partyName: '', partyAuxType: '', partyAmbiguous: false,
    })
  })

  it('往来单位：camelCase 与 snake_case 双兼容，歧义标记如实透传', () => {
    const camel = mapSampledToGenericRow({
      voucherNo: 'V-9', partyName: '重庆医药', partyAuxType: '客户',
    })
    expect(camel.partyName).toBe('重庆医药')
    expect(camel.partyAuxType).toBe('客户')
    expect(camel.partyAmbiguous).toBe(false)

    const snake = mapSampledToGenericRow({
      voucher_no: 'V-10', party_name: '国网重庆', party_aux_type: '供应商',
    })
    expect(snake.partyName).toBe('国网重庆')
    expect(snake.partyAuxType).toBe('供应商')
  })

  it('🔴 歧义时 partyName 必须留空（一键多名不得猜一个填进底稿）', () => {
    // 后端 enrich_items_with_aux_party 在一键多名时只标 ambiguous、不给 name。
    // 若这里把 ambiguous 的行也填上某个名字，等于替审计师做了没有依据的判断。
    const row = mapSampledToGenericRow({
      voucherNo: 'V-11', partyName: null, partyAmbiguous: true,
    })
    expect(row.partyName).toBe('')
    expect(row.partyAmbiguous).toBe(true)
  })

  it('snake_case 输入（部分宿主直接消费后端 items）', () => {
    const row = mapSampledToGenericRow({
      voucher_no: 'V-2', voucher_date: '2025-07-01', debit_amount: 0,
      credit_amount: '2000', account_code: '2202', summary: '采购付款',
    })
    expect(row.voucherNo).toBe('V-2')
    expect(row.voucherDate).toBe('2025-07-01')
    expect(row.creditAmount).toBe(2000)
    expect(row.accountCode).toBe('2202')
  })

  it('摘要兼容 businessContent / remark 别名', () => {
    expect(mapSampledToGenericRow({ businessContent: '业务内容' }).summary).toBe('业务内容')
    expect(mapSampledToGenericRow({ remark: '备注' }).summary).toBe('备注')
  })

  it('非法金额归 0，不产出 NaN（NaN 进底稿会让整表合计变 NaN）', () => {
    const row = mapSampledToGenericRow({ debitAmount: 'abc', creditAmount: Infinity })
    expect(row.debitAmount).toBe(0)
    expect(row.creditAmount).toBe(0)
    expect(Number.isNaN(row.debitAmount)).toBe(false)
  })

  it('非对象输入返回全空行且不抛错（一条脏样本不打掉整批回填）', () => {
    for (const bad of [null, undefined, 'x', 5, []]) {
      const row = mapSampledToGenericRow(bad)
      expect(row.voucherNo).toBe('')
      expect(row.debitAmount).toBe(0)
    }
  })

  it('PBT：输出恒含全部 6 个字段且金额为有限数', () => {
    fc.assert(
      fc.property(fc.anything(), (v) => {
        const row = mapSampledToGenericRow(v)
        for (const f of SAMPLING_MIN_FIELDS) expect(row).toHaveProperty(f)
        expect(Number.isFinite(row.debitAmount)).toBe(true)
        expect(Number.isFinite(row.creditAmount)).toBe(true)
      }),
      { numRuns: 20 },
    )
  })
})

describe('mapSampledRows', () => {
  it('过滤「凭证号与摘要都为空」的空行', () => {
    const rows = mapSampledRows([
      { voucherNo: 'V-1' },
      { summary: '只有摘要' },
      { debitAmount: 100 },      // 无凭证号无摘要 → 丢弃
      {},
    ])
    expect(rows).toHaveLength(2)
  })

  it('非数组返回空数组', () => {
    expect(mapSampledRows(null)).toEqual([])
    expect(mapSampledRows('x')).toEqual([])
  })

  it('保持原顺序', () => {
    const rows = mapSampledRows([{ voucherNo: 'A' }, { voucherNo: 'B' }, { voucherNo: 'C' }])
    expect(rows.map((r) => r.voucherNo)).toEqual(['A', 'B', 'C'])
  })
})
