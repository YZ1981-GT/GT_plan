import { describe, it, expect } from 'vitest'
import {
  buildG8VoucherCrossSnapshot,
  buildG8VoucherLinkHints,
  deriveG8AbnormalType,
  filterG8VoucherRowsBySource,
  countG8VoucherBySource,
  applyG8LinkHintSuggestions,
  formatG8AbnormalType,
  mapG8VoucherToMisstatementBody,
  mapG8VoucherToA13PushItem,
  selectG8QuantitativeAbnormals,
} from '../g8VoucherCross'
import type { ChecklistResponse } from '../useF1FormData'
import { enrichG8VoucherRow } from '../useG8VoucherCheck'

function resp(itemId: string, rows: unknown[]): [string, ChecklistResponse] {
  return [itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(rows) }]
}

describe('deriveG8AbnormalType', () => {
  it('无异常 → none', () => {
    const row = enrichG8VoucherRow({
      voucherNo: '1',
      check1OriginalComplete: true,
      check2Authorization: true,
      check3Accounting: true,
      check4FairValueCorrect: true,
      check5OCICorrect: true,
    }, 1)
    expect(row.abnormalType).toBe('none')
    expect(formatG8AbnormalType(row.abnormalType)).toBe('—')
  })

  it('仅公允不通过 → quantitative', () => {
    const row = enrichG8VoucherRow({
      voucherNo: '1',
      check1OriginalComplete: true,
      check2Authorization: true,
      check3Accounting: true,
      check4FairValueCorrect: false,
      check5OCICorrect: true,
    }, 1)
    expect(row.isAbnormal).toBe(true)
    expect(row.abnormalType).toBe('quantitative')
  })

  it('OCI 不通过 → qualitative', () => {
    const row = enrichG8VoucherRow({
      voucherNo: '1',
      check1OriginalComplete: true,
      check2Authorization: true,
      check3Accounting: true,
      check4FairValueCorrect: true,
      check5OCICorrect: false,
    }, 1)
    expect(row.abnormalType).toBe('qualitative')
  })

  it('公允+授权不通过 → mixed', () => {
    const row = enrichG8VoucherRow({
      voucherNo: '1',
      check2Authorization: false,
      check4FairValueCorrect: false,
    }, 1)
    expect(row.abnormalType).toBe('mixed')
  })

  it('仅 forceAbnormal → qualitative', () => {
    expect(deriveG8AbnormalType(enrichG8VoucherRow({
      voucherNo: '1',
      forceAbnormal: true,
      check1OriginalComplete: true,
      check2Authorization: true,
      check3Accounting: true,
      check4FairValueCorrect: true,
      check5OCICorrect: true,
    }, 1))).toBe('qualitative')
  })
})

describe('来源分池', () => {
  it('filter / count', () => {
    const rows = [
      enrichG8VoucherRow({ voucherNo: 'a', source: '抽凭' }, 1),
      enrichG8VoucherRow({ voucherNo: 'b', source: '截止' }, 2),
      enrichG8VoucherRow({ voucherNo: 'c', source: '手工' }, 3),
      enrichG8VoucherRow({ voucherNo: 'd' }, 4),
    ]
    expect(filterG8VoucherRowsBySource(rows, '抽凭')).toHaveLength(1)
    expect(filterG8VoucherRowsBySource(rows, '手工')).toHaveLength(2)
    expect(countG8VoucherBySource(rows)).toEqual({
      all: 4,
      抽凭: 1,
      截止: 1,
      手工: 2,
    })
  })
})

describe('G8-4/G8-5 联动提示', () => {
  it('公允差异 + 交易性特征', () => {
    const m = new Map<string, ChecklistResponse>([
      resp('G8-detail-rows', [{ rowId: 'd1', investeeName: '甲公司' }]),
      resp('G8-fv-test-rows', [{
        investeeName: '甲公司',
        closingUnadjustedFV: 100,
        closingAuditedFV: 150,
        fairValueLevel: 'Level3',
      }]),
      resp('G8-designation-rows', [{
        investeeName: '甲公司',
        tradingNearTermSale: 'yes',
        tradingPortfolioShortTerm: 'no',
        tradingDerivative: 'no',
        equityInstrument: 'yes',
        designatedFvtoci: 'yes',
        fvReliable: 'yes',
      }]),
    ])
    const snap = buildG8VoucherCrossSnapshot(m)
    expect(snap.details).toHaveLength(1)
    const hints = buildG8VoucherLinkHints('甲公司', snap)
    expect(hints.some((h) => h.code === 'fv-diff' && h.suggestCheck4Fail)).toBe(true)
    expect(hints.some((h) => h.code === 'fv-level3')).toBe(true)
    expect(hints.some((h) => h.code === 'desig-trading' && h.suggestCheck5Fail)).toBe(true)

    const row = enrichG8VoucherRow({ voucherNo: 'v1', investeeName: '甲公司' }, 1)
    const patch = applyG8LinkHintSuggestions(row, hints)
    expect(patch.check4FairValueCorrect).toBe(false)
    expect(patch.check5OCICorrect).toBe(false)
  })

  it('未挂接明细时提示', () => {
    const m = new Map<string, ChecklistResponse>([
      resp('G8-detail-rows', [{ rowId: 'd1', investeeName: '乙公司' }]),
    ])
    const hints = buildG8VoucherLinkHints('', buildG8VoucherCrossSnapshot(m))
    expect(hints.some((h) => h.code === 'no-detail')).toBe(true)
  })

  it('已通过的核对项不被应用建议覆盖', () => {
    const hints = [{
      code: 'fv-diff' as const,
      level: 'warning' as const,
      text: '差异',
      suggestCheck4Fail: true,
    }]
    const row = enrichG8VoucherRow({
      voucherNo: 'v',
      check4FairValueCorrect: true,
    }, 1)
    expect(applyG8LinkHintSuggestions(row, hints).check4FairValueCorrect).toBeUndefined()
  })
})

describe('A13 映射', () => {
  it('mapG8VoucherToMisstatementBody 写入科目与金额', () => {
    const body = mapG8VoucherToMisstatementBody(
      {
        voucherNo: '记-100',
        investeeName: '甲公司',
        abnormalDesc: '公允变动未入 OCI',
        debitAmount: 1200,
        creditAmount: 0,
        rowId: 'r1',
        abnormalType: 'quantitative',
        isAbnormal: true,
      },
      2025,
      '1503',
    )
    expect(body.year).toBe(2025)
    expect(body.misstatement_type).toBe('factual')
    expect(body.affected_account_code).toBe('1503')
    expect(body.misstatement_amount).toBe('1200')
    expect(String(body.misstatement_description)).toContain('记-100')
    expect(String(body.auditor_evaluation)).toContain('G8-6')
  })

  it('mapG8VoucherToA13PushItem 含索引与借贷', () => {
    const item = mapG8VoucherToA13PushItem({
      voucherNo: '记-9',
      investeeName: '乙公司',
      debitAmount: 0,
      creditAmount: 500,
      isAbnormal: true,
      abnormalDesc: '金额异常',
    })
    expect(item.wpCode).toBe('G8-6')
    expect(item.indexRef).toBe('G8-6/记-9')
    expect(item.creditAmount).toBe(500)
  })

  it('selectG8QuantitativeAbnormals 仅金额/混合', () => {
    const rows = [
      { isAbnormal: true, abnormalType: 'quantitative' },
      { isAbnormal: true, abnormalType: 'qualitative' },
      { isAbnormal: true, abnormalType: 'mixed' },
      { isAbnormal: false, abnormalType: 'quantitative' },
      { isAbnormal: true, abnormalType: 'none' },
    ]
    expect(selectG8QuantitativeAbnormals(rows)).toHaveLength(2)
  })
})
