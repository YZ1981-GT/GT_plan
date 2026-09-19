import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useG2Adjustment,
  createEmptyG2AdjustmentRow,
  G2_ACCOUNT_CODE,
} from '../useG2Adjustment'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/services/apiProxy'

function setup(opts?: { projectId?: string; readonly?: boolean }) {
  const allResponses = ref(new Map<string, ChecklistResponse>())
  const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
  const debouncedSave = (itemId: string, data: Partial<ChecklistResponse>) => {
    saves.push({ id: itemId, data })
    allResponses.value.set(itemId, {
      item_id: itemId,
      conclusion: data.conclusion ?? null,
      remark: data.remark ?? null,
      ...data,
    } as ChecklistResponse)
  }
  const hook = useG2Adjustment({
    allResponses,
    debouncedSave,
    isReadonly: ref(!!opts?.readonly),
    wpId: ref('wp-1'),
    projectId: ref(opts?.projectId ?? 'proj-1'),
    auditYear: ref(2025),
  })
  return { ...hook, allResponses, saves }
}

describe('useG2Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('空行默认科目为 1132 / 账项调整', () => {
    const row = createEmptyG2AdjustmentRow()
    expect(row.accountCode).toBe(G2_ACCOUNT_CODE)
    expect(row.category).toBe('账项调整')
    expect(row.reportItem).toBe('应收利息')
  })

  it('增删改行并持久化到 G2-4-rows', () => {
    const { rows, addRow, updateCell, removeRow, saves, debitTotal, creditTotal, isBalanced } = setup()
    addRow()
    expect(rows.value).toHaveLength(1)
    expect(saves.some((s) => s.id === 'G2-4-rows')).toBe(true)

    const id = rows.value[0].rowId
    updateCell(id, 'debitAmount', 100)
    updateCell(id, 'creditAmount', 100)
    updateCell(id, 'description', '测试调整')
    expect(debitTotal.value).toBe(100)
    expect(creditTotal.value).toBe(100)
    expect(isBalanced.value).toBe(true)

    removeRow(id)
    expect(rows.value).toHaveLength(0)
  })

  it('报表调整不计入 1132 净调整', () => {
    const { rows, addRow, updateCell, netAjeToG2 } = setup()
    addRow()
    const id = rows.value[0].rowId
    updateCell(id, 'debitAmount', 50)
    updateCell(id, 'category', '报表调整')
    expect(netAjeToG2.value).toBe(0)

    updateCell(id, 'category', '账项调整')
    expect(netAjeToG2.value).toBe(50)
  })

  it('确认时派发事件并回写 G2-1-rows', () => {
    const created: any[] = []
    const confirmed: any[] = []
    const onCreated = (e: Event) => created.push((e as CustomEvent).detail)
    const onConfirmed = (e: Event) => confirmed.push((e as CustomEvent).detail)
    window.addEventListener('adjustment:created', onCreated)
    window.addEventListener('g2:adjustment-confirmed', onConfirmed)

    const { addRow, updateCell, publishAdjustment, rows, saves } = setup()
    addRow()
    updateCell(rows.value[0].rowId, 'accountCode', '1132')
    updateCell(rows.value[0].rowId, 'accountName', '应收利息')
    updateCell(rows.value[0].rowId, 'debitAmount', 500)
    updateCell(rows.value[0].rowId, 'creditAmount', 0)
    addRow()
    updateCell(rows.value[1].rowId, 'accountCode', '1002')
    updateCell(rows.value[1].rowId, 'accountName', '银行存款')
    updateCell(rows.value[1].rowId, 'debitAmount', 0)
    updateCell(rows.value[1].rowId, 'creditAmount', 500)
    publishAdjustment()

    expect(created.length).toBeGreaterThanOrEqual(1)
    expect(confirmed).toHaveLength(1)
    expect(confirmed[0].netAdjustment).toBe(500)
    const save = saves.find((s) => s.id === 'G2-1-rows')
    expect(save).toBeTruthy()
    const store = JSON.parse(String(save!.data.remark))
    expect(store['gross-collective'].closingAdjustment).toBe(500)

    window.removeEventListener('adjustment:created', onCreated)
    window.removeEventListener('g2:adjustment-confirmed', onConfirmed)
  })

  it('从调整分录模块同步仅导入相关科目行', async () => {
    ;(api.get as any).mockResolvedValue({
      data: {
        data: {
          items: [
            {
              adjustment_no: 'AJE-001',
              adjustment_type: 'AJE',
              description: '调增应收利息',
              entry_group_id: 'g2',
              line_items: [
                { standard_account_code: '1132', account_name: '应收利息', debit_amount: 1000, credit_amount: 0 },
                { standard_account_code: '1002', account_name: '银行存款', debit_amount: 0, credit_amount: 1000 },
              ],
            },
            {
              adjustment_no: 'AJE-002',
              adjustment_type: 'AJE',
              description: '无关分录',
              line_items: [
                { standard_account_code: '1122', account_name: '应收账款', debit_amount: 1, credit_amount: 0 },
              ],
            },
          ],
        },
      },
    })

    const { syncFromAdjustmentModule, rows } = setup()
    const n = await syncFromAdjustmentModule()
    expect(n).toBe(1)
    expect(rows.value).toHaveLength(1)
    expect(rows.value[0].accountCode).toBe('1132')
    expect(rows.value[0].debitAmount).toBe(1000)
    expect(rows.value[0].remark).toContain('调整分录模块')
  })

  it('兼容旧版 AJE/RJE 字段导入', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    allResponses.value.set('G2-4-rows', {
      item_id: 'G2-4-rows',
      conclusion: null,
      remark: JSON.stringify([
        { id: 'old-1', entryType: 'RJE', summary: '重分类', accountCode: '1132', debit: 0, credit: 200 },
      ]),
    })
    const hook = useG2Adjustment({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
    })
    expect(hook.rows.value).toHaveLength(1)
    expect(hook.rows.value[0].category).toBe('报表调整')
    expect(hook.rows.value[0].description).toBe('重分类')
    expect(hook.rows.value[0].creditAmount).toBe(200)
  })
})
