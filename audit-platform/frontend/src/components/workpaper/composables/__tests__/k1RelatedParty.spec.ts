import { describe, expect, it } from 'vitest'
import {
  addMissingK1RelatedPartyRows,
  batchMatchK1DetailRelatedParty,
  buildAgingDescription,
  computeK1MissingRelatedParties,
  computeK1RelatedPartySubtotal,
  inferMovementFromBalances,
  isK1RelatedPartyMarked,
  matchK1RelatedPartyFromRegistry,
  mergeRelatedPartyFromK1Detail,
  recalcK1RelatedPartyRow,
  rowBalanceGap,
} from '../useK1RelatedParty'

describe('useK1RelatedParty', () => {
  it('isK1RelatedPartyMarked 识别关联方标记', () => {
    expect(isK1RelatedPartyMarked('否')).toBe(false)
    expect(isK1RelatedPartyMarked('是')).toBe(true)
    expect(isK1RelatedPartyMarked('联营企业')).toBe(true)
  })

  it('matchK1RelatedPartyFromRegistry B19匹配', () => {
    expect(matchK1RelatedPartyFromRegistry('华为技术', ['北京华为技术有限公司'])).toBe('其他关联方')
    expect(matchK1RelatedPartyFromRegistry('无关公司', ['北京华为'])).toBe('否')
  })

  it('computeK1MissingRelatedParties 漏列检测', () => {
    const missing = computeK1MissingRelatedParties(
      ['甲公司', '乙公司'],
      [{ name: '甲公司' }],
    )
    expect(missing).toEqual(['乙公司'])
  })

  it('addMissingK1RelatedPartyRows 补充空行', () => {
    const rows = addMissingK1RelatedPartyRows([], ['丙公司'])
    expect(rows).toHaveLength(1)
    expect(rows[0].name).toBe('丙公司')
  })

  it('batchMatchK1DetailRelatedParty 批量匹配', () => {
    const rows = [
      { counterparty: '华为技术', relatedParty: '否' },
      { counterparty: '无关公司', relatedParty: '否' },
      { counterparty: '已标记', relatedParty: '联营企业' },
    ]
    const count = batchMatchK1DetailRelatedParty(rows, ['北京华为技术有限公司'])
    expect(count).toBe(1)
    expect(rows[0].relatedParty).toBe('其他关联方')
    expect(rows[1].relatedParty).toBe('否')
  })
  it('recalcK1RelatedPartyRow: 期末=期初+借-贷', () => {
    const row = recalcK1RelatedPartyRow({
      id: '1',
      name: 'A',
      relation: '控股股东',
      beginBalance: 100,
      debit: 50,
      credit: 20,
      endBalance: 0,
      provision: 10,
      aging: '',
      nature: '',
      postCollection: 0,
      indexNo: '',
      remark: '',
    })
    expect(row.endBalance).toBe(130)
    expect(rowBalanceGap(row)).toBe(0)
  })

  it('inferMovementFromBalances 反推借贷', () => {
    expect(inferMovementFromBalances(100, 150)).toEqual({ debit: 50, credit: 0 })
    expect(inferMovementFromBalances(100, 60)).toEqual({ debit: 0, credit: 40 })
    expect(inferMovementFromBalances(100, 100)).toEqual({ debit: 0, credit: 0 })
  })

  it('buildAgingDescription 拼接账龄', () => {
    const desc = buildAgingDescription({
      agingAudited: { within1: 100, y1to2: 50 },
    } as any)
    expect(desc).toContain('1年以内:100')
    expect(desc).toContain('1-2年:50')
  })

  it('mergeRelatedPartyFromK1Detail 同名合并', () => {
    const merged = mergeRelatedPartyFromK1Detail(
      [{
        id: 'x',
        name: '甲公司',
        relation: '联营企业',
        beginBalance: 0,
        debit: 0,
        credit: 0,
        endBalance: 0,
        provision: 0,
        aging: '旧账龄',
        nature: '旧性质',
        postCollection: 5,
        indexNo: 'K1-12',
        remark: '保留',
      }],
      [{
        counterparty: '甲公司',
        relatedParty: '是',
        beginBalance: 100,
        endBalance: 200,
        badDebtProvision: 20,
        nature: '往来款',
        agingAudited: { within1: 200 },
      } as any],
    )
    expect(merged).toHaveLength(1)
    expect(merged[0].endBalance).toBe(200)
    expect(merged[0].debit).toBe(100)
    expect(merged[0].provision).toBe(20)
    expect(merged[0].nature).toBe('往来款')
    expect(merged[0].postCollection).toBe(5)
    expect(merged[0].indexNo).toBe('K1-12')
  })

  it('computeK1RelatedPartySubtotal 汇总', () => {
    const sub = computeK1RelatedPartySubtotal([
      {
        id: '1', name: 'A', relation: '', beginBalance: 100, debit: 0, credit: 0,
        endBalance: 100, provision: 10, aging: '', nature: '', postCollection: 5,
        indexNo: '', remark: '',
      },
      {
        id: '2', name: 'B', relation: '', beginBalance: 200, debit: 50, credit: 0,
        endBalance: 250, provision: 20, aging: '', nature: '', postCollection: 0,
        indexNo: '', remark: '',
      },
    ])
    expect(sub.endBalance).toBe(350)
    expect(sub.provision).toBe(30)
    expect(sub.bookValue).toBe(320)
    expect(sub.postCollection).toBe(5)
  })
})
