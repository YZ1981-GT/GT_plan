/**
 * L5-2 明细表：审定四列 L~O 与披露两列 R/S 按模板公式计算
 * （spec oo-writeback-template-parity-closure 第三批）。
 *
 * 模板 明细表L5-2（三个受管区逐行同式）：E=B−C+D；L=B+F+G；M=C+H+J；N=D+I+K；
 * O=L−M+N；R=L−P；S=O−Q。修前前端只算 E，其余公式列恒 0。
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn() },
}))

import { createL5DetailRow, recalcL5DetailRow, useL5Detail, type L5DetailRow } from '../useL5Detail'

function sample(): L5DetailRow {
  return {
    ...createL5DetailRow('某融资租赁'),
    beginning: 1000, periodRepayment: 200, periodIncrease: 300,
    priorAdjustment: 10, priorReclass: -5,
    ajeDebit: 7, ajeCredit: 20, rjeDebit: 1, rjeCredit: 3,
    minusPriorDue: 100, minusEndDue: 150,
  }
}

describe('recalcL5DetailRow', () => {
  it('逐列与模板同式', () => {
    const r = recalcL5DetailRow(sample())
    expect(r.endBalance).toBe(1100)           // E = 1000 − 200 + 300
    expect(r.auditedBeginning).toBe(1005)     // L = 1000 + 10 − 5
    expect(r.auditedDebit).toBe(208)          // M = 200 + 7 + 1
    expect(r.auditedCredit).toBe(323)         // N = 300 + 20 + 3
    expect(r.auditedEnding).toBe(1120)        // O = L − M + N
    expect(r.disclosureBeginning).toBe(905)   // R = L − P
    expect(r.disclosureEnding).toBe(970)      // S = O − Q
  })
})

describe('useL5Detail', () => {
  it('载入即按模板补齐公式列；编辑调整后重算并随整表保存', () => {
    const debouncedSave = vi.fn()
    const allResponses = ref(new Map<string, any>([
      ['L5-L5-2-rows', { remark: JSON.stringify([{ ...sample(), auditedEnding: 0 }]) }],
    ]))
    const detailRows = ref<L5DetailRow[]>([])
    const api = useL5Detail({ allResponses, debouncedSave } as any, detailRows)
    expect(detailRows.value[0].auditedEnding).toBe(1120)
    api.updateRow(0, 'minusEndDue', 20)
    expect(detailRows.value[0].disclosureEnding).toBe(1100)
    const [itemId, payload] = debouncedSave.mock.calls.at(-1)!
    expect(itemId).toBe('L5-L5-2-rows')
    expect(JSON.parse(payload.remark)[0].disclosureEnding).toBe(1100)
    expect(api.computedRows.value[0].auditedCredit).toBe(323)
  })
})
