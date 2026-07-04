import { describe, it, expect } from 'vitest'
import { enrichInquiryRow, enrichMarketRow } from '../useF2RelatedPartyPricing'
import { enrichUndisclosedRow } from '../useF2UndisclosedParty'
import { enrichChecklistRow } from '../useF2SupplierChecklist'
import { enrichInterviewSummaryRow } from '../useF2InterviewSummary'

describe('F2-65/66 related party pricing', () => {
  it('spreadPct and isHighSpread when |spread| > 10%', () => {
    const ok = enrichInquiryRow({
      id: '1', relatedParty: 'A', itemName: 'x', relatedPrice: 105, thirdPartyName: 'B',
      inquiryPrice: 100, conclusion: '', remark: '',
    })
    expect(ok.spreadPct).toBeCloseTo(5, 1)
    expect(ok.isHighSpread).toBe(false)

    const bad = enrichMarketRow({
      id: '1', relatedParty: 'A', itemName: 'x', relatedPrice: 120, marketPrice: 100,
      conclusion: '', remark: '',
    })
    expect(bad.isHighSpread).toBe(true)
  })
})

describe('F2-67 undisclosed party', () => {
  it('high risk -> red; undisclosed confirmed -> orange', () => {
    expect(enrichUndisclosedRow({
      id: '1', supplierName: 'S', creditCode: '', legalRep: '', shareholderInfo: '',
      registeredAddress: '', regDate: '', registeredCapital: '', actualController: '',
      relationToClient: '', relationType: '控股股东', isDisclosed: '否', checkSources: [],
      checkDate: '', checker: '', checkConclusion: '', riskLevel: '中', followUp: '',
      indexNo: '', remark: '',
    }).highlightLevel).toBe('orange')

    expect(enrichUndisclosedRow({
      id: '1', supplierName: 'S', creditCode: '', legalRep: '', shareholderInfo: '',
      registeredAddress: '', regDate: '', registeredCapital: '', actualController: '',
      relationToClient: '', relationType: '控股股东', isDisclosed: '否', checkSources: [],
      checkDate: '', checker: '', checkConclusion: '', riskLevel: '高', followUp: '',
      indexNo: '', remark: '',
    }).highlightLevel).toBe('red')
  })
})

describe('F2-69 supplier checklist', () => {
  it('completionPct = completed / (total - na) × 100', () => {
    const row = enrichChecklistRow({
      id: '1', supplierName: 'S', overallEval: '', riskCategory: '', followUp: '',
      owner: '', completeDate: '2099-01-01', indexNo: '', remark: '',
      check1: '已完成', check2: '已完成', check3: '已完成', check4: '不适用', check5: '不适用',
      check6: '已完成', check7: '已完成', check8: '已完成', check9: '已完成', check10: '已完成',
    })
    expect(row.completionPct).toBe(100)
    expect(row.completedCount).toBe(8)
  })
})

describe('F2-71 interview summary', () => {
  it('flags 异常 and 存在疑点', () => {
    expect(enrichInterviewSummaryRow({
      id: '1', supplierName: 'S', interviewDate: '', method: '', interviewee: '',
      intervieweeTitle: '', summary: '', concerns: '', conclusion: '存在疑点',
    }).isFlagged).toBe(true)
  })
})
