/**
 * mapOcrFieldsToSubcontract — F2-35 OCR 字段映射
 */
import { describe, it, expect } from 'vitest'
import { mapOcrFieldsToSubcontract } from '../useF2SubcontractOcr'

describe('mapOcrFieldsToSubcontract', () => {
  it('maps contract target: supplier/orderNo/date → processor/contractNo/issueDate', () => {
    const patch = mapOcrFieldsToSubcontract(
      {
        supplier: '甲加工厂',
        purchaseOrderNo: 'WT-2025-01',
        orderDate: '2025-06-01',
        itemName: '钢材',
        amount: 0,
      },
      'contract',
    )
    expect(patch).toEqual({
      processor: '甲加工厂',
      contractNo: 'WT-2025-01',
      issueDate: '2025-06-01',
      remark: '品名 钢材',
    })
  })

  it('maps fee target: amount → fee and settlement remark', () => {
    const patch = mapOcrFieldsToSubcontract(
      {
        amount: 1200,
        invoiceNo: 'FP-9',
        orderDate: '2025-07-01',
        supplier: '甲加工厂',
      },
      'fee',
    )
    expect(patch.fee).toBe(1200)
    expect(patch.processor).toBe('甲加工厂')
    expect(patch.remark).toContain('结算单据 FP-9')
    expect(patch.remark).toContain('结算日 2025-07-01')
  })
})
