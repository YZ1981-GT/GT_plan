/**
 * N2-7 免抵退税申报汇总表页：按 22 栏台账渲染并读回已存台账
 * （原先按已删除的 12 个月结构读 monthlyRows / diffMonths ⇒ 渲染即报错，且从不 loadLedger）。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'

const stored = new Map<string, any>()
const saveField = vi.fn(async () => {})

vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), info: vi.fn() } }))
vi.mock('../../../composables/useN2FormData', () => ({
  useN2FormData: () => ({
    allResponses: ref(stored),
    saveField,
    getField: () => null,
    debouncedSave: vi.fn(),
    loadData: vi.fn(async () => {}),
  }),
}))

import N2TabExportRefund from '../N2TabExportRefund.vue'

function mountPage() {
  return mount(N2TabExportRefund, {
    props: { wpId: 'wp-1', projectId: 'p-1', allResponses: new Map(), isReadonly: false },
    global: {
      stubs: {
        GtIndexChip: true,
        'el-table': { props: ['data'], template: '<div class="tbl"><div v-for="r in data" :key="r.line" class="tr">{{ r.line }}|{{ r.amount }}</div></div>' },
        'el-card': { template: '<div><slot /></div>' },
        'el-alert': { template: '<div><slot name="title" /><slot /></div>' },
      },
    },
  })
}

describe('N2TabExportRefund', () => {
  it('挂载不报错，渲染 22 栏，并读回已存台账重算公式栏', async () => {
    stored.set('N2-7-ledger', {
      item_id: 'N2-7-ledger',
      conclusion: JSON.stringify({
        params: { taxRateParam: 0.13, refundRateParam: 0.09, exemptMaterialCost: 0 },
        rows: [{ line: 1, amount: 1000 }, { line: 3, amount: 800 }, { line: 4, amount: 200 }],
      }),
    })
    const w = mountPage()
    await flushPromises()
    const rows = w.findAll('.tr').map((r) => r.text())
    expect(rows).toHaveLength(22)
    expect(rows[1]).toBe('2|1000') // ② = ③ + ④
    expect(rows[5]).toBe('6|40') // ⑥ = ① × (13% − 9%)
    expect(w.text()).toContain('免抵退税申报汇总表 N2-7')
  })
})
