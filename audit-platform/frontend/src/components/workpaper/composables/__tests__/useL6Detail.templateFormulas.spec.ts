/**
 * L6-2 明细表：审定四列 P~S 由未审 + 调整算出（原先手填），附注取 L6-L6-2-rows
 * （spec oo-writeback-template-parity-closure 第三批）。
 *
 * 模板 明细表L6-2：G=C+D−E−F；P=C+H+I；Q=D+J+M；R=E+K+N；S=F+L+O；T=P+Q−R−S。
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn() },
}))

import {
  L6_DETAIL_ROWS_ITEM_ID,
  readL6DetailRows,
  recalcL6DetailRow,
  useL6Detail,
  type L6DetailRow,
} from '../useL6Detail'

function sample(project = '甲专项'): L6DetailRow {
  return {
    rowId: 'l62det-1', key: 'l62det-1', seq: 1, project,
    fundSource: '', approvalNo: '', purpose: '',
    beginBalance: 1000, creditIn: 300, carryForward: 200, refund: 50, endBalance: 0,
    ajeBegin: 10, ajeCredit: 20, ajeCarryFwd: 7, ajeRefund: 2,
    rjeBegin: -5, rjeCredit: 3, rjeCarryFwd: 1, rjeRefund: 4,
    // 手填的旧审定值：重算后必须被模板公式覆盖
    auditedBegin: 99, auditedCredit: 99, auditedCarryFwd: 99, auditedRefund: 99, auditedEnd: 99,
    docRef: '', indexRef: '', completionStatus: '', remark: '',
  }
}

describe('recalcL6DetailRow', () => {
  it('逐列与模板同式，覆盖手填的旧审定值', () => {
    const r = recalcL6DetailRow(sample())
    expect(r.endBalance).toBe(1050)      // G = 1000 + 300 − 200 − 50
    expect(r.auditedBegin).toBe(1005)    // P = 1000 + 10 − 5
    expect(r.auditedCredit).toBe(323)    // Q = 300 + 20 + 3
    expect(r.auditedCarryFwd).toBe(208)  // R = 200 + 7 + 1
    expect(r.auditedRefund).toBe(56)     // S = 50 + 2 + 4
    expect(r.auditedEnd).toBe(1064)      // T = P + Q − R − S
  })
})

describe('useL6Detail', () => {
  it('改调整列后审定列重算并随整表保存', () => {
    const debouncedSave = vi.fn()
    const detailRows = ref<L6DetailRow[]>([sample()])
    const api = useL6Detail({ debouncedSave } as any, detailRows)
    api.updateRow(0, 'ajeRefund', 12)
    expect(detailRows.value[0].auditedRefund).toBe(66)
    expect(detailRows.value[0].auditedEnd).toBe(1054)
    const rowsCall = debouncedSave.mock.calls.filter(([id]) => id === L6_DETAIL_ROWS_ITEM_ID).at(-1)!
    expect(JSON.parse(rowsCall[1].remark)[0].auditedEnd).toBe(1054)
    expect(api.computedRows.value[0].auditedBegin).toBe(1005)
  })
})

describe('readL6DetailRows（附注取数）', () => {
  it('从整表 JSON 读并重算；坏载荷 / 缺载荷给空表', () => {
    const responses = new Map([[L6_DETAIL_ROWS_ITEM_ID, { remark: JSON.stringify([sample()]) }]])
    const rows = readL6DetailRows(responses)
    expect(rows).toHaveLength(1)
    expect(rows[0].auditedEnd).toBe(1064)
    expect(readL6DetailRows(new Map())).toEqual([])
    expect(readL6DetailRows(new Map([[L6_DETAIL_ROWS_ITEM_ID, { remark: '{坏' }]]))).toEqual([])
  })
})
