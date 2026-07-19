/**
 * useG1FairValueTest — G1-6 公允价值测试单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  enrichFvRow,
  migrateFvRaw,
  validateG1Level3,
  getEnabledValuationColumns,
  useG1FairValueTest,
  type G1FairValueRow,
} from '../useG1FairValueTest'
import type { ChecklistResponse } from '../useF1FormData'

function baseRow(patch: Partial<G1FairValueRow> = {}): G1FairValueRow {
  return enrichFvRow({
    id: '1',
    seq: 1,
    securityName: '测试股',
    securityCode: '600000',
    quantity: 1000,
    bookUnitFv: 10,
    bookValue: 10000,
    fvLevel: 1,
    valuationMethod: '市场报价',
    methodConsistentWithPrior: 'yes',
    quoteDate: '2020-12-31',
    quoteSource: '上交所',
    quoteValue: 10.5,
    marketValue: 0,
    level1Diff: 0,
    observableDesc: '',
    level2Result: 0,
    level2Diff: 0,
    valuationTechnique: '',
    unobservableInput: '',
    unobservableInputValue: '',
    assumption: '',
    sensitivityAnalysis: '',
    level3Result: 0,
    level3Diff: 0,
    testedValue: 0,
    activeDiff: 0,
    valuationDocIndex: '',
    conclusion: '',
    remark: '',
    ...patch,
  })
}

describe('enrichFvRow / migrateFvRaw', () => {
  it('L1 测试值 = 数量×报价，差异 = 测试 − 账面', () => {
    const r = baseRow()
    expect(r.marketValue).toBe(10500)
    expect(r.testedValue).toBe(10500)
    expect(r.activeDiff).toBe(500)
    expect(r.level1Diff).toBe(500)
  })

  it('L2 测试值取 level2Result', () => {
    const r = baseRow({ fvLevel: 2, level2Result: 10200, quoteValue: 0 })
    expect(r.testedValue).toBe(10200)
    expect(r.activeDiff).toBe(200)
  })

  it('迁移旧字段 quantity/bookValue', () => {
    const r = migrateFvRaw(
      { id: 'x', securityName: '旧债', quantity: 100, bookValue: 9800, fvLevel: 2, level2Result: 9900 },
      1,
    )
    expect(r.bookValue).toBe(9800)
    expect(r.quantity).toBe(100)
    expect(r.testedValue).toBe(9900)
    expect(r.fvLevel).toBe(2)
  })
})

describe('validateG1Level3 / getEnabledValuationColumns', () => {
  it('非 Level3 不校验', () => {
    expect(validateG1Level3(baseRow({ fvLevel: 1 }))).toEqual([])
  })

  it('Level3 缺技术与不可观察输入', () => {
    expect(validateG1Level3(baseRow({ fvLevel: 3 }))).toEqual(['估值技术/假设', '不可观察输入值'])
  })

  it('Level3 填齐后通过', () => {
    expect(
      validateG1Level3(
        baseRow({
          fvLevel: 3,
          valuationTechnique: '收益法(DCF)',
          unobservableInput: 'WACC 9%',
        }),
      ),
    ).toEqual([])
  })

  it('层次互斥列', () => {
    expect(getEnabledValuationColumns(1).enabledCols).toContain('quoteSource')
    expect(getEnabledValuationColumns(2).enabledCols).toContain('level2Result')
    expect(getEnabledValuationColumns(3).enabledCols).toContain('valuationTechnique')
  })
})

describe('useG1FairValueTest', () => {
  it('加载旧 conclusion 数据并迁移', () => {
    const legacy = [{
      id: 'old-1',
      securityName: '旧债',
      securityCode: 'X1',
      quantity: 100,
      bookValue: 9800,
      fvLevel: 2,
      observableDesc: '可比债收益率',
      valuationMethod: '市场法',
      level2Result: 9900,
    }]
    const map = ref(new Map<string, ChecklistResponse>([
      ['G1-6-rows', { conclusion: JSON.stringify(legacy) } as ChecklistResponse],
    ]))
    const { rows, stats } = useG1FairValueTest({
      allResponses: map,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(rows.value[0].securityName).toBe('旧债')
    expect(rows.value[0].quantity).toBe(100)
    expect(rows.value[0].bookValue).toBe(9800)
    expect(rows.value[0].fvLevel).toBe(2)
    expect(rows.value[0].testedValue).toBe(9900)
    expect(stats.value.level2).toBe(1)
  })

  it('亦可从 remark 加载', () => {
    const map = ref(new Map<string, ChecklistResponse>([
      ['G1-6-rows', {
        remark: JSON.stringify([{ id: 'r1', securityName: '从remark', quantity: 1, bookValue: 100, fvLevel: 1 }]),
      } as ChecklistResponse],
    ]))
    const { rows } = useG1FairValueTest({
      allResponses: map,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(rows.value[0].securityName).toBe('从remark')
  })

  it('persist 同时写入 conclusion 与 remark', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const save = vi.fn()
    const { updateRow, rows } = useG1FairValueTest({
      allResponses: map,
      debouncedSave: save,
      isReadonly: ref(false),
    })
    updateRow(rows.value[0].id, { securityName: 'A股' })
    const call = save.mock.calls.find((c) => c[0] === 'G1-6-rows')
    expect(call?.[1].conclusion).toBeTruthy()
    expect(call?.[1].remark).toBe(call?.[1].conclusion)
  })

  it('syncFromDetail 从 G1-2 带入', () => {
    const detail = [{
      id: 'd1',
      securityName: '明细股',
      securityCode: '000001',
      closingQuantity: 500,
      unitFairValue: 12,
      closingFairValue: 6000,
      auditedClosingFvTotal: 6100,
      fairValueSource: '1',
      quoteDate: '2020-12-31',
      indexRef: 'G1-2',
    }]
    const map = ref(new Map<string, ChecklistResponse>([
      ['G1-2-rows', { conclusion: JSON.stringify(detail) } as ChecklistResponse],
    ]))
    const { syncFromDetail, rows } = useG1FairValueTest({
      allResponses: map,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    const n = syncFromDetail()
    expect(n).toBe(1)
    expect(rows.value[0].securityName).toBe('明细股')
    expect(rows.value[0].quantity).toBe(500)
    expect(rows.value[0].bookValue).toBe(6000)
    expect(rows.value[0].fvLevel).toBe(1)
  })
})
