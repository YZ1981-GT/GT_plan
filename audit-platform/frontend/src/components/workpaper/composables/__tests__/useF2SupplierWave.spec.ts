import { describe, it, expect } from 'vitest'
import {
  emptyUndisclosedPartyRow,
  enrichUndisclosedPartyRow,
} from '../useF2UndisclosedPartyFormulas'
import {
  emptySupplierChecklistRow,
  enrichSupplierChecklistRow,
} from '../useF2SupplierChecklistFormulas'
import {
  emptyInterviewSummaryEntity,
  enrichInterviewSummaryEntity,
} from '../useF2InterviewSummaryFormulas'

describe('F2-67 undisclosed party', () => {
  it('匹配次数自动汇总并建议 Y', () => {
    const row = emptyUndisclosedPartyRow()
    row.name = '张三'
    row.supplierLegalPerson = 1
    row.marketingDept = 1
    const enriched = enrichUndisclosedPartyRow(row)
    expect(enriched.total).toBe(2)
    expect(enriched.suggestedRelated).toBe('Y')
    expect(enriched.isAbnormal).toBe(true)
  })
})

describe('F2-69 supplier checklist', () => {
  it('按五种核查方式计算完成度', () => {
    const row = emptySupplierChecklistRow()
    row.supplierName = 'S'
    row.selectionReason = '重大供应商'
    row.registryChecked = true
    row.internetChecked = true
    row.interviewChecked = true
    row.confirmationChecked = true
    row.siteVisitChecked = true
    row.finalIndexRef = 'F2-69-1'
    const enriched = enrichSupplierChecklistRow(row)
    expect(enriched.completionPct).toBe(1)
    expect(enriched.completedMethodCount).toBe(5)
    expect(enriched.isIncomplete).toBe(false)
  })
})

describe('F2-71 interview summary', () => {
  it('结论含疑点或金额不符时触发风险提示', () => {
    const entity = emptyInterviewSummaryEntity()
    entity.supplierName = 'S'
    entity.conclusion = '存在疑点，需进一步核查'
    entity.transactionAmountMatch = '否'
    const enriched = enrichInterviewSummaryEntity(entity)
    expect(enriched.riskFlags).toContain('结论存疑')
    expect(enriched.riskFlags).toContain('交易金额不符')
    expect(enriched.isRisk).toBe(true)
  })

  it('走访地址与注册地址不一致自动预警', () => {
    const entity = emptyInterviewSummaryEntity()
    entity.supplierName = 'S'
    entity.registeredAddress = '北京市朝阳区XX路1号'
    entity.visitAddress = '天津市滨海新区YY路9号'
    expect(enrichInterviewSummaryEntity(entity).isAddressMismatch).toBe(true)
    entity.visitAddress = '北京市朝阳区XX路1号'
    expect(enrichInterviewSummaryEntity(entity).isAddressMismatch).toBe(false)
  })
})
