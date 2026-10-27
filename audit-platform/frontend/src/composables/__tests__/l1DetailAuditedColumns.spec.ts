/**
 * L1-2 明细表：审定四列 R~U 按模板公式计算（spec oo-writeback-template-parity-closure 第三批）。
 *
 * 模板 明细表L1-2：K=H+I−J；R=H+L+M；S=I+N+P；T=J+O+Q；U=R+S−T。
 * 修前前端只算 K，R~U 声明了字段却恒 0 ⇒ OO 侧有调整时两侧审定数不一致。
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import {
  DETAIL_ROWS_ITEM_ID,
  createEmptyDetailRow,
  recalcL1DetailRow,
  type DetailRow,
} from '@/composables/useL1FormData'
import { useL1Detail } from '@/composables/useL1Detail'

vi.mock('element-plus', () => ({
  ElMessageBox: { prompt: vi.fn() },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

function sample(): DetailRow {
  return {
    ...createEmptyDetailRow(),
    beginning: 1000, creditAmount: 300, debitAmount: 200,
    priorAje: 10, priorRje: -5, ajeIncrease: 20, ajeDecrease: 7, rjeIncrease: 3, rjeDecrease: 1,
  }
}

describe('recalcL1DetailRow', () => {
  it('逐列与模板同式', () => {
    const r = recalcL1DetailRow(sample())
    expect(r.endBalance).toBe(1100)      // K = 1000 + 300 − 200
    expect(r.auditedPrior).toBe(1005)    // R = 1000 + 10 − 5
    expect(r.auditedIncrease).toBe(323)  // S = 300 + 20 + 3
    expect(r.auditedDecrease).toBe(208)  // T = 200 + 7 + 1
    expect(r.auditedEnd).toBe(1120)      // U = R + S − T
  })

  it('不改录入列，存量里写坏的公式列被覆盖', () => {
    const r = recalcL1DetailRow({ ...sample(), auditedEnd: 999999, endBalance: -1 })
    expect(r.beginning).toBe(1000)
    expect(r.priorAje).toBe(10)
    expect(r.auditedEnd).toBe(1120)
    expect(r.endBalance).toBe(1100)
  })
})

describe('useL1Detail 编辑调整列', () => {
  it('改账项调整后审定列重算并随整表保存', () => {
    const detailRows = ref<DetailRow[]>([sample()])
    const saved: Array<Array<{ item_id: string; remark: string | null }>> = []
    const api = useL1Detail({ detailRows, debounceSave: (items: never) => saved.push(items) } as never)
    api.updateRow(0, 'ajeIncrease', 50)
    expect(detailRows.value[0].auditedIncrease).toBe(353)
    expect(detailRows.value[0].auditedEnd).toBe(1150)
    const last = saved.at(-1)!
    expect(last[0].item_id).toBe(DETAIL_ROWS_ITEM_ID)
    expect(JSON.parse(last[0].remark!)[0].auditedEnd).toBe(1150)
    expect(api.computedRows.value[0].auditedPrior).toBe(1005)
  })
})
