/**
 * D2 凭证检查 Excel 导入合并口径测试
 *
 * spec: voucher-runtime-integrity-and-visibility-closure 任务 14（R5 + R7.4）
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { mergeVoucherRows } from '../useD2VoucherCheckEnhanced'
import type { VoucherCheckRow } from '../useD2VoucherCheckEnhanced'

function makeRow(overrides: Partial<VoucherCheckRow> = {}): VoucherCheckRow {
  return {
    rowId: `r-${Math.random().toString(36).slice(2, 8)}`,
    seq: 0,
    customerName: '',
    voucherDate: '',
    voucherNo: '',
    businessContent: '',
    counterpartAccount: '',
    counterpartDetail: '',
    debitAmount: 0,
    creditAmount: 0,
    supportingDoc: '',
    check1: '',
    check2: '',
    check3: '',
    check4: '',
    check5: '',
    indexRef: '',
    isAbnormal: '',
    remark: '',
    attachments: [],
    ...overrides,
  }
}

describe('mergeVoucherRows', () => {
  it('同号不同日 → 两行都保留', () => {
    const existing = [makeRow({ voucherNo: '0001', voucherDate: '2025-01-15' })]
    const incoming = [makeRow({ voucherNo: '0001', voucherDate: '2025-06-20' })]
    const result = mergeVoucherRows(existing, incoming)
    expect(result).toHaveLength(2)
    expect(result[0].voucherDate).toBe('2025-01-15')
    expect(result[1].voucherDate).toBe('2025-06-20')
  })

  it('同号同日 → 只保留第一行', () => {
    const existing = [makeRow({ voucherNo: '0001', voucherDate: '2025-06-15', check1: '已核' })]
    const incoming = [makeRow({ voucherNo: '0001', voucherDate: '2025-06-15', check1: '新核' })]
    const result = mergeVoucherRows(existing, incoming)
    expect(result).toHaveLength(1)
    expect(result[0].check1).toBe('已核') // 不被覆盖
  })

  it('已有行 check1~check5 不被覆盖', () => {
    const existing = [makeRow({
      voucherNo: '0002', voucherDate: '2025-03-01',
      check1: 'A', check2: 'B', check3: 'C', check4: 'D', check5: 'E',
    })]
    const incoming = [makeRow({
      voucherNo: '0002', voucherDate: '2025-03-01',
      check1: 'X', check2: 'Y', check3: 'Z',
    })]
    const result = mergeVoucherRows(existing, incoming)
    expect(result).toHaveLength(1)
    expect(result[0].check1).toBe('A')
    expect(result[0].check2).toBe('B')
    expect(result[0].check3).toBe('C')
  })

  // 号与日期取小值域，才会生成同号同日 / 同号不同日 / 无号的碰撞（随机长串几乎从不重复，等于没测去重）。
  // 原写法用 fc.char / fc.stringOf，fast-check 4 已删除，两条 PBT 一跑即 TypeError（从未真正执行过）。
  const rowsArb = fc.array(
    fc.record({ no: fc.constantFrom('0001', '0002', ''), date: fc.constantFrom('2025-01-01', '2025-06-01', '') }),
    { minLength: 0, maxLength: 8 },
  )
  const toRows = (data: Array<{ no: string; date: string }>) => data.map(d => makeRow({ voucherNo: d.no, voucherDate: d.date }))

  it('PBT: seq 始终连续且从 1 开始', () => {
    fc.assert(
      fc.property(rowsArb, rowsArb, (existingData, incomingData) => {
        const result = mergeVoucherRows(toRows(existingData), toRows(incomingData))
        result.forEach((r, i) => expect(r.seq).toBe(i + 1))
      }),
      { numRuns: 5 },
    )
  })

  it('PBT: 已有行原样保留在前；导入行按「号|日期」去重（无号的照加），与逐行模型一致', () => {
    fc.assert(
      fc.property(rowsArb, rowsArb, (existingData, incomingData) => {
        const existing = toRows(existingData)
        const incoming = toRows(incomingData)
        const result = mergeVoucherRows(existing, incoming)
        const seen = new Set(existing.filter(r => r.voucherNo).map(r => `${r.voucherNo}|${r.voucherDate}`))
        const kept = incoming.filter((r) => {
          if (!r.voucherNo) return true
          const key = `${r.voucherNo}|${r.voucherDate}`
          if (seen.has(key)) return false
          seen.add(key)
          return true
        })
        expect(result.map(r => r.rowId)).toEqual([...existing, ...kept].map(r => r.rowId))
      }),
      { numRuns: 5 },
    )
  })
})
