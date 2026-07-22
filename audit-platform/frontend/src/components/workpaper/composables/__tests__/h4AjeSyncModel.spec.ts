/**
 * h4AjeSyncModel — H4-2 ↔ H4-3 AJE 双向同步单测
 */
import { describe, it, expect } from 'vitest'
import {
  H42_AJE_MARKER,
  encodeH42AjeRemark,
  parseH42AjeRemark,
  emSideSignedAmount,
  buildH42AjePairsForRow,
  mergeH42AjeIntoH43,
  applyH43AjeBackToDetails,
  sumDetailCostAjeNet,
  isH42AjeAutoRow,
} from '../h4AjeSyncModel'

describe('h4AjeSyncModel', () => {
  it('remark 编解码往返', () => {
    const r = encodeH42AjeRemark('row-1', 'increase')
    expect(r).toContain(H42_AJE_MARKER)
    expect(parseH42AjeRemark(r)).toEqual({ detailRowId: 'row-1', kind: 'increase' })
    expect(parseH42AjeRemark('手工备注')).toBeNull()
  })

  it('emSideSignedAmount 各 kind 借贷方向正确', () => {
    expect(emSideSignedAmount('begin', 100)).toEqual({ debit: 100, credit: 0 })
    expect(emSideSignedAmount('begin', -40)).toEqual({ debit: 0, credit: 40 })
    expect(emSideSignedAmount('decrease', 50)).toEqual({ debit: 0, credit: 50 })
    expect(emSideSignedAmount('impair', 30)).toEqual({ debit: 0, credit: 30 })
    expect(emSideSignedAmount('impair', -10)).toEqual({ debit: 10, credit: 0 })
  })

  it('单行生成借贷平衡成对分录', () => {
    const pairs = buildH42AjePairsForRow({
      rowId: 'd1',
      name: '水泥',
      ajeBegin: 100,
      ajeIncrease: 0,
      ajeDecrease: 40,
      ajeImpair: 20,
    }, 1)
    // begin 2行 + decrease 2行 + impair 2行
    expect(pairs).toHaveLength(6)
    const debit = pairs.reduce((s, r) => s + r.debitAmount, 0)
    const credit = pairs.reduce((s, r) => s + r.creditAmount, 0)
    expect(debit).toBeCloseTo(credit, 5)
    expect(pairs.every(isH42AjeAutoRow)).toBe(true)
    expect(pairs.every(r => r.indexRef === 'H4-2')).toBe(true)
  })

  it('merge 清除旧自动行并保留手工行', () => {
    const existing = [
      { rowId: 'manual', remark: '手工', accountCode: '1605', debitAmount: 1, creditAmount: 0, seq: 1 },
      { rowId: 'old-auto', remark: encodeH42AjeRemark('x', 'begin'), accountCode: '1605', debitAmount: 9, creditAmount: 0, seq: 2 },
      { rowId: 'h47', remark: 'H4-7-aje-auto', accountCode: '6701', debitAmount: 5, creditAmount: 0, seq: 3 },
    ]
    const { rows, added, cleared } = mergeH42AjeIntoH43(existing, [{
      rowId: 'd1', name: 'A', ajeIncrease: 200, ajeBegin: 0, ajeDecrease: 0, ajeImpair: 0,
    }])
    expect(cleared).toBe(1)
    expect(added).toBe(2) // 1605 + 2202
    expect(rows.some(r => r.rowId === 'manual')).toBe(true)
    expect(rows.some(r => r.remark === 'H4-7-aje-auto')).toBe(true)
    expect(rows.some(r => r.rowId === 'old-auto')).toBe(false)
  })

  it('推送后再回写明细 AJE 闭环', () => {
    const detail = [{
      rowId: 'd1',
      name: '钢筋',
      ajeBegin: 100,
      ajeIncrease: 50,
      ajeDecrease: 20,
      ajeImpair: 10,
    }]
    const { rows: h43 } = mergeH42AjeIntoH43([], detail)
    // 在 H4-3 改 begin 自动行金额：1605 借改为 180
    const edited = h43.map((r) => {
      const p = parseH42AjeRemark(r.remark)
      if (p?.kind === 'begin' && String(r.accountCode).startsWith('1605')) {
        return { ...r, debitAmount: 180, creditAmount: 0 }
      }
      if (p?.kind === 'begin' && r.accountCode === '4104') {
        return { ...r, debitAmount: 0, creditAmount: 180 }
      }
      return r
    })
    const { rows: back, updated, matchedLines } = applyH43AjeBackToDetails(detail, edited)
    expect(matchedLines).toBeGreaterThan(0)
    expect(updated).toBe(1)
    expect(back[0].ajeBegin).toBe(180)
    expect(back[0].ajeIncrease).toBe(50)
    expect(back[0].ajeDecrease).toBe(20)
    expect(back[0].ajeImpair).toBe(10)
  })

  it('sumDetailCostAjeNet = begin+inc−dec', () => {
    expect(sumDetailCostAjeNet([
      { rowId: '1', ajeBegin: 10, ajeIncrease: 20, ajeDecrease: 5 },
      { rowId: '2', ajeBegin: 0, ajeIncrease: 0, ajeDecrease: 3 },
    ])).toBe(22)
  })
})
