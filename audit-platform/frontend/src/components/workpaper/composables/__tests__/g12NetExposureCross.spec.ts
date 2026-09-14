import { describe, it, expect } from 'vitest'
import {
  extractHedgeRelationId,
  findG12NetExposureInternalMismatches,
  findG12NetExposureLinkageIssues,
  findG12NetExposureCrossIssues,
  formatG12NetExposureCrossMessage,
  hasG12NetExposureData,
} from '../g12NetExposureCross'
import type { ChecklistResponse } from '../useF1FormData'

describe('g12NetExposureCross', () => {
  it('extractHedgeRelationId strips sheet prefix', () => {
    expect(extractHedgeRelationId('G12-2/HR-001')).toBe('HR-001')
    expect(extractHedgeRelationId('HR-002')).toBe('HR-002')
  })

  it('findG12NetExposureInternalMismatches flags net vs positions', () => {
    const issues = findG12NetExposureInternalMismatches([
      {
        rowId: 'r1', seq: 1, item: '外汇净头寸', currency: 'USD',
        position1Amount: '1,000万美元', position2Amount: '1,200万美元',
        netPosition: '支付100万美元', hedgingInstrument: '', indexRef: '',
      },
    ])
    expect(issues).toHaveLength(1)
    expect(issues[0].kind).toBe('net_calc_mismatch')
  })

  it('findG12NetExposureLinkageIssues flags missing G12-2/G12-4', () => {
    const rows = [{
      rowId: 'r1', seq: 1, item: '外汇净头寸', currency: 'USD',
      hedgeRelationId: 'HR-X',
      position1Amount: '', position2Amount: '', netPosition: '',
      hedgingInstrument: '远期合约A', indexRef: 'G12-2/HR-X',
    }]
    const issues = findG12NetExposureLinkageIssues(
      rows,
      ['远期合约B'],
      ['HR-Y'],
      ['远期合约C'],
      ['HR-Z'],
    )
    expect(issues.some((i) => i.kind === 'missing_in_g12_2')).toBe(true)
    expect(issues.some((i) => i.kind === 'missing_in_g12_4')).toBe(true)
  })

  it('findG12NetExposureCrossIssues integrates allResponses', () => {
    const allResponses = new Map<string, ChecklistResponse>([
      ['G12-hedge-detail-rows', {
        remark: JSON.stringify([{
          item: '外汇净头寸',
          hedgingInstrument: '远期A',
          rowKind: 'fv_allocation',
          indexRef: 'HR-1',
        }]),
      } as ChecklistResponse],
      ['G12-fv-test-rows', {
        remark: JSON.stringify([{ hedgeRelationId: 'HR-1', instrumentName: '远期A' }]),
      } as ChecklistResponse],
    ])
    const ok = findG12NetExposureCrossIssues([{
      rowId: 'r1', seq: 1, item: '项目', currency: 'USD',
      hedgeRelationId: 'HR-1',
      position1Amount: '100万美元', position2Amount: '80万美元',
      netPosition: '收20万美元', hedgingInstrument: '远期A', indexRef: 'HR-1',
    }], allResponses)
    expect(ok).toHaveLength(0)

    const bad = findG12NetExposureCrossIssues([{
      rowId: 'r2', seq: 2, item: '项目2', currency: 'USD',
      position1Amount: '100万美元', position2Amount: '80万美元',
      netPosition: '收20万美元', hedgingInstrument: '不存在工具', indexRef: '',
    }], allResponses)
    expect(bad.length).toBeGreaterThan(0)
  })

  it('detects currency mismatch between row and embedded amount', () => {
    const issues = findG12NetExposureInternalMismatches([{
      rowId: 'r3', seq: 3, item: '混币种', currency: 'USD',
      position1Amount: '100万欧元', position2Amount: '80万欧元',
      netPosition: '收20万欧元', hedgingInstrument: '', indexRef: '',
    }])
    expect(issues.some((i) => i.kind === 'currency_mismatch')).toBe(true)
  })
  it('formatG12NetExposureCrossMessage summarizes', () => {
    const msg = formatG12NetExposureCrossMessage([{
      rowId: 'r1', seq: 1, item: '外汇', hedgingInstrument: 'X',
      kind: 'missing_in_g12_4', detail: '未在 G12-4 找到',
    }])
    expect(msg).toMatch(/G12-5 交叉验证/)
    expect(msg).toMatch(/未在 G12-4/)
  })

  it('hasG12NetExposureData ignores legacy questionnaire', () => {
    expect(hasG12NetExposureData(new Map())).toBe(false)
    expect(hasG12NetExposureData(new Map([
      ['G12-net-exposure-rows', {
        remark: JSON.stringify([{ checkItem: '旧', compliance: 'ok' }]),
      } as ChecklistResponse],
    ]))).toBe(false)
    expect(hasG12NetExposureData(new Map([
      ['G12-net-exposure-rows', {
        remark: JSON.stringify([{ item: '外汇净头寸', netPosition: '支付200万美元' }]),
      } as ChecklistResponse],
    ]))).toBe(true)
  })
})
