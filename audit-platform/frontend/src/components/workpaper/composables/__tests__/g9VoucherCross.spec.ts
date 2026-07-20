/**
 * G9-6 跨表联动 / A13 / OCR 纯函数测试
 */
import { describe, it, expect } from 'vitest'
import {
  buildG9VoucherCrossSnapshot,
  buildG9VoucherLinkHints,
  applyG9LinkHintSuggestions,
  selectG9QuantitativeAbnormals,
  mapG9VoucherToMisstatementBody,
  mapG9VoucherToA13PushItem,
  mapG9OcrToVoucherFields,
  computeG9OcrMergePatch,
  extractG9OcrPayload,
  isG9AllowedOcrAttachment,
  matchG9AssetKey,
} from '../g9VoucherCross'
import type { ChecklistResponse } from '../useF1FormData'

function resp(remark: string): ChecklistResponse {
  return { item_id: 'x', conclusion: null, remark } as ChecklistResponse
}

describe('buildG9VoucherCrossSnapshot', () => {
  it('解析明细/公允/L3', () => {
    const m = new Map<string, ChecklistResponse>([
      ['G9-detail-rows', resp(JSON.stringify([
        { rowId: 'd1', assetName: '基金A', classification: 'FVTPL', fairValueLevel: 'Level3', isRelatedParty: true, impairmentLoss: 100 },
      ]))],
      ['G9-fv-test-rows', resp(JSON.stringify([
        { assetName: '基金A', closingUnadjustedFV: 1000, closingAuditedFV: 1200, fairValueLevel: 'Level3' },
      ]))],
      ['G9-l3-rows', resp(JSON.stringify([
        { assetName: '基金A', variance: 50 },
      ]))],
    ])
    const snap = buildG9VoucherCrossSnapshot(m)
    expect(snap.details).toHaveLength(1)
    expect(snap.details[0].isRelatedParty).toBe(true)
    expect(snap.fvByAsset.get(matchG9AssetKey('基金A'))?.diff).toBe(200)
    expect(snap.l3ByAsset.get(matchG9AssetKey('基金A'))?.variance).toBe(50)
  })
})

describe('buildG9VoucherLinkHints / apply', () => {
  it('公允差异建议复核公允价值', () => {
    const m = new Map<string, ChecklistResponse>([
      ['G9-detail-rows', resp(JSON.stringify([{ rowId: 'd1', assetName: 'X' }]))],
      ['G9-fv-test-rows', resp(JSON.stringify([
        { assetName: 'X', closingUnadjustedFV: 10, closingAuditedFV: 5000, fairValueLevel: 'Level2' },
      ]))],
    ])
    const snap = buildG9VoucherCrossSnapshot(m)
    const hints = buildG9VoucherLinkHints('X', snap)
    expect(hints.some((h) => h.code === 'fv-diff' && h.suggestCheckFairValueFail)).toBe(true)

    const patch = applyG9LinkHintSuggestions({
      isAbnormal: false,
      forceAbnormal: false,
      abnormalDesc: '',
      checkOriginal: null,
      checkAuthorized: null,
      checkAccounting: null,
      checkClassification: null,
      checkFairValue: null,
      checkImpairment: null,
    }, hints)
    expect(patch.checkFairValue).toBe(false)
  })

  it('未挂接时提示选明细', () => {
    const m = new Map<string, ChecklistResponse>([
      ['G9-detail-rows', resp(JSON.stringify([{ rowId: 'd1', assetName: 'Y' }]))],
    ])
    const hints = buildG9VoucherLinkHints('', buildG9VoucherCrossSnapshot(m))
    expect(hints.some((h) => h.code === 'no-detail')).toBe(true)
  })

  it('不覆盖已通过的核对项', () => {
    const patch = applyG9LinkHintSuggestions({
      isAbnormal: false,
      forceAbnormal: false,
      abnormalDesc: '',
      checkOriginal: null,
      checkAuthorized: null,
      checkAccounting: null,
      checkClassification: null,
      checkFairValue: true,
      checkImpairment: null,
    }, [{
      code: 'fv-diff',
      level: 'danger',
      text: 'diff',
      suggestCheckFairValueFail: true,
    }])
    expect(patch.checkFairValue).toBeUndefined()
  })
})

describe('A13 mapping', () => {
  it('select quantitative + map bodies', () => {
    const rows = [
      { isAbnormal: true, abnormalType: 'quantitative', voucherNo: 'v1', debitAmount: 100, creditAmount: 0, assetName: 'A', abnormalDesc: '公允' },
      { isAbnormal: true, abnormalType: 'qualitative', voucherNo: 'v2', debitAmount: 50, creditAmount: 0 },
    ]
    const q = selectG9QuantitativeAbnormals(rows)
    expect(q).toHaveLength(1)
    const body = mapG9VoucherToMisstatementBody(q[0] as any, 2025)
    expect(body.affected_account_code).toBe('1504')
    expect(body.misstatement_amount).toBe('100')
    const item = mapG9VoucherToA13PushItem(q[0] as any)
    expect(item.wpCode).toBe('G9-6')
    expect(item.indexRef).toBe('G9-6/v1')
  })
})

describe('OCR helpers', () => {
  it('map + merge empty only', () => {
    const { patch, lowConfidence } = mapG9OcrToVoucherFields({
      summary: '购入基金',
      借方: '1000',
      凭证号: { value: '记-1', confidence: 0.5 },
    }, 0.9)
    expect(patch.businessContent).toBe('购入基金')
    expect(patch.debitAmount).toBe(1000)
    expect(patch.voucherNo).toBe('记-1')
    expect(lowConfidence).toContain('voucherNo')

    const merged = computeG9OcrMergePatch(
      { businessContent: '已有', debitAmount: 0, voucherNo: '' },
      patch,
    )
    expect(merged.businessContent).toBeUndefined()
    expect(merged.debitAmount).toBe(1000)
    expect(merged.voucherNo).toBe('记-1')
  })

  it('extract payload + file type', () => {
    const { fields, confidence } = extractG9OcrPayload({
      data: { summary: 'x', confidence: 0.7 },
    })
    expect(fields.summary).toBe('x')
    expect(confidence).toBe(0.7)
    expect(isG9AllowedOcrAttachment(new File([''], 'a.pdf', { type: 'application/pdf' }))).toBe(true)
    expect(isG9AllowedOcrAttachment(new File([''], 'a.txt', { type: 'text/plain' }))).toBe(false)
  })
})
