import { describe, it, expect } from 'vitest'
import {
  findG12NetExposureFvAmountMismatches,
  findG12NetExposureLinkageIssues,
} from '../g12NetExposureCross'
import { isG12NetExposureSheetComplete } from '../g12NetExposureComplete'
import type { ChecklistResponse } from '../useF1FormData'

describe('findG12NetExposureFvAmountMismatches', () => {
  it('flags large variance vs G12-4 closing FV', () => {
    const issues = findG12NetExposureFvAmountMismatches(
      [{
        rowId: 'r1', seq: 1, item: '外汇', currency: 'USD',
        hedgeRelationId: 'HR-1',
        position1Amount: '', position2Amount: '',
        netPosition: '支付200万美元', hedgingInstrument: '远期A', indexRef: '',
      }],
      [{ hedgeRelationId: 'HR-1', instrumentClosingFV: 500000 }],
    )
    expect(issues).toHaveLength(1)
    expect(issues[0].kind).toBe('fv_amount_mismatch')
  })

  it('passes when net abs matches closing FV within tolerance', () => {
    const issues = findG12NetExposureFvAmountMismatches(
      [{
        rowId: 'r1', seq: 1, item: '外汇', currency: 'USD',
        hedgeRelationId: 'HR-1',
        position1Amount: '', position2Amount: '',
        netPosition: '支付200万美元', hedgingInstrument: '', indexRef: '',
      }],
      [{ hedgeRelationId: 'HR-1', instrumentClosingFV: 2_000_000 }],
    )
    expect(issues).toHaveLength(0)
  })
})

describe('findG12NetExposureLinkageIssues', () => {
  it('matches by hedgeRelationId first', () => {
    const rows = [{
      rowId: 'r1', seq: 1, item: '项目', currency: 'USD',
      hedgeRelationId: 'HR-1',
      position1Amount: '', position2Amount: '', netPosition: '',
      hedgingInstrument: '', indexRef: '',
    }]
    expect(findG12NetExposureLinkageIssues(
      rows, [], ['HR-1'], [], ['HR-1'],
    )).toHaveLength(0)
  })
})

describe('isG12NetExposureSheetComplete', () => {
  const completeRow = {
    rowId: 'r1', item: '外汇净头寸', currency: 'USD',
    position1Desc: '销售', position2Desc: '采购', netPosition: '支付200万美元',
    hedgeRelationId: 'HR-1', hedgingInstrument: '远期A', indexRef: 'G12-2/HR-1',
    position1Amount: '1,000万美元', position2Amount: '1,200万美元',
  }

  it('requires rows, note, conclusion and no cross issues', () => {
    const m = new Map<string, ChecklistResponse>([
      ['G12-net-exposure-rows', { remark: JSON.stringify([completeRow]) } as ChecklistResponse],
      ['G12-net-exposure-audit-note', { remark: '已获取支持性证据' } as ChecklistResponse],
      ['G12-net-exposure-conclusion', { conclusion: '未见异常' } as ChecklistResponse],
      ['G12-hedge-detail-rows', { remark: JSON.stringify([{ hedgeRelationId: 'HR-1', hedgingInstrument: 'A' }]) } as ChecklistResponse],
      ['G12-fv-test-rows', { remark: JSON.stringify([{ hedgeRelationId: 'HR-1', instrumentName: 'A', instrumentClosingFV: 2_000_000 }]) } as ChecklistResponse],
    ])
    expect(isG12NetExposureSheetComplete(m)).toBe(true)
  })

  it('false when note or conclusion missing', () => {
    const m = new Map<string, ChecklistResponse>([
      ['G12-net-exposure-rows', { remark: JSON.stringify([completeRow]) } as ChecklistResponse],
    ])
    expect(isG12NetExposureSheetComplete(m)).toBe(false)
  })
})
