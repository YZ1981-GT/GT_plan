import { describe, it, expect } from 'vitest'
import {
  buildG12NetExposureAiContext,
  collectG12NetExposureIndexSuggestions,
  formatEvidenceDisplay,
  inferEvidenceType,
} from '../g12NetExposureEvidence'
import type { ChecklistResponse } from '../useF1FormData'

describe('g12NetExposureEvidence', () => {
  it('inferEvidenceType 从自由文本推断', () => {
    expect(inferEvidenceType('销售预算表')).toBe('sales_budget')
    expect(inferEvidenceType('采购合同')).toBe('order_contract')
    expect(inferEvidenceType('套期指定文件')).toBe('hedge_designation')
    expect(inferEvidenceType('董事会决议')).toBe('board_approval')
    expect(inferEvidenceType('估值报告')).toBe('valuation_doc')
    expect(inferEvidenceType('银行对账单')).toBe('bank_confirm')
    expect(inferEvidenceType('其他资料')).toBe('other')
    expect(inferEvidenceType('')).toBe('')
  })

  it('formatEvidenceDisplay 组合类型与明细', () => {
    expect(formatEvidenceDisplay('sales_budget', 'Q4预算')).toBe('销售/采购预算：Q4预算')
    expect(formatEvidenceDisplay('', '仅明细')).toBe('仅明细')
    expect(formatEvidenceDisplay('order_contract', '')).toBe('订单/合同')
  })

  it('collectG12NetExposureIndexSuggestions 从 G12-2/4/6 收集', () => {
    const m = new Map<string, ChecklistResponse>([
      ['G12-hedge-detail-rows', {
        remark: JSON.stringify([{ indexRef: 'HD-1', item: '外汇净头寸', hedgeRelationId: 'HR-1' }]),
      } as ChecklistResponse],
      ['G12-fv-test-rows', {
        remark: JSON.stringify([{ hedgeRelationId: 'HR-1', instrumentName: '远期A' }]),
      } as ChecklistResponse],
      ['G12-voucher-rows', {
        remark: JSON.stringify([{ indexNo: 'V-9', voucherNo: '记-1', hedgeRelationId: 'HR-1' }]),
      } as ChecklistResponse],
    ])
    const opts = collectG12NetExposureIndexSuggestions(m, ['自有索引'])
    const values = opts.map((o) => o.value)
    expect(values).toContain('HD-1')
    expect(values).toContain('G12-2/HD-1')
    expect(values).toContain('HR-1')
    expect(values).toContain('V-9')
    expect(values).toContain('自有索引')
    expect(values).toContain('G12-5')
  })

  it('buildG12NetExposureAiContext 含交叉摘要', () => {
    const ctx = buildG12NetExposureAiContext({
      rows: [{
        seq: 1,
        item: '外汇净头寸',
        currency: 'USD',
        netPosition: '支付200万美元',
        evidenceType: 'sales_budget',
        supportingEvidence: '预算',
        hedgingInstrument: '远期',
        indexRef: 'G12-2/1',
        hedgeRelationId: 'HR-1',
      }],
      incompleteCount: 0,
      crossIssues: [{ seq: 1, kind: 'net_calc_mismatch', detail: '净头寸与建议不符', item: '外汇净头寸' }],
      crossSummary: 'G12-5 交叉验证 — 1 处问题',
      auditNote: '已获取预算',
      testObjective: '检查支持性证据',
    })
    expect(ctx.交叉差异数).toBe(1)
    expect(ctx.交叉验证摘要).toContain('交叉验证')
    expect(ctx.测试行摘要[0].evidence).toContain('销售/采购预算')
  })
})
