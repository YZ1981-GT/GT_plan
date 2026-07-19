import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useG3Adjustment,
  createEmptyG3AdjustmentRow,
  G3_ACCOUNT_CODE,
} from '../useG3Adjustment'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
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
  const hook = useG3Adjustment({
    allResponses,
    debouncedSave,
    isReadonly: ref(!!opts?.readonly),
    wpId: ref('wp-1'),
    projectId: ref(opts?.projectId ?? 'proj-1'),
    auditYear: ref(2025),
  })
  return { ...hook, allResponses, saves }
}

describe('useG3Adjustment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('空行默认科目为 1131 / 账项调整', () => {
    const row = createEmptyG3AdjustmentRow()
    expect(row.accountCode).toBe(G3_ACCOUNT_CODE)
    expect(row.category).toBe('账项调整')
    expect(row.reportItem).toBe('应收股利')
  })

  it('增删改行并持久化到 G3-3-rows', () => {
    const { rows, addRow, updateCell, removeRow, saves, debitTotal, creditTotal, isBalanced } = setup()
    addRow()
    expect(rows.value).toHaveLength(1)
    expect(saves.some((s) => s.id === 'G3-3-rows')).toBe(true)

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

  it('报表调整计入 netRJE 而非 netAJE', () => {
    const { rows, addRow, updateCell, netAdjustments } = setup()
    addRow()
    const id = rows.value[0].rowId
    updateCell(id, 'debitAmount', 50)
    updateCell(id, 'category', '报表调整')
    expect(netAdjustments.value.netAJE).toBe(0)
    expect(netAdjustments.value.netRJE).toBe(50)

    updateCell(id, 'category', '账项调整')
    expect(netAdjustments.value.netAJE).toBe(50)
    expect(netAdjustments.value.netRJE).toBe(0)
  })

  it('确认时派发事件并回写 G3-1-adj-rows', () => {
    const created: any[] = []
    const confirmed: any[] = []
    const onCreated = (payload: any) => created.push(payload)
    const onConfirmed = (payload: any) => confirmed.push(payload)
    eventBus.on('adjustment:created', onCreated)
    eventBus.on('g3:adjustment-confirmed', onConfirmed)

    const { addRow, updateCell, publishAdjustment, rows, saves } = setup()
    addRow()
    updateCell(rows.value[0].rowId, 'accountCode', '1131')
    updateCell(rows.value[0].rowId, 'accountName', '应收股利')
    updateCell(rows.value[0].rowId, 'debitAmount', 500)
    updateCell(rows.value[0].rowId, 'creditAmount', 0)
    addRow()
    updateCell(rows.value[1].rowId, 'accountCode', '6111')
    updateCell(rows.value[1].rowId, 'accountName', '投资收益')
    updateCell(rows.value[1].rowId, 'debitAmount', 0)
    updateCell(rows.value[1].rowId, 'creditAmount', 500)
    publishAdjustment()

    expect(created.length).toBeGreaterThanOrEqual(1)
    expect(confirmed).toHaveLength(1)
    expect(confirmed[0].netAJE).toBe(500)
    expect(confirmed[0].accountCode).toBe('1131')
    const save = saves.find((s) => s.id === 'G3-1-adj-rows')
    expect(save).toBeTruthy()
    const store = JSON.parse(String(save!.data.remark))
    expect(store[0].closingAJE).toBe(500)
    expect(store[0].investeeName).toBe('账项调整汇总')

    eventBus.off('adjustment:created', onCreated)
    eventBus.off('g3:adjustment-confirmed', onConfirmed)
  })

  it('从调整分录模块同步仅导入相关科目行', async () => {
    ;(api.get as any).mockResolvedValue({
      data: {
        data: {
          items: [
            {
              adjustment_no: 'AJE-001',
              adjustment_type: 'AJE',
              description: '调增应收股利',
              entry_group_id: 'g3',
              line_items: [
                { standard_account_code: '1131', account_name: '应收股利', debit_amount: 1000, credit_amount: 0 },
                { standard_account_code: '6111', account_name: '投资收益', debit_amount: 0, credit_amount: 1000 },
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
    expect(n).toBe(2)
    expect(rows.value).toHaveLength(2)
    expect(rows.value.every((r) => ['1131', '6111'].includes(r.accountCode))).toBe(true)
    expect(rows.value[0].remark).toContain('调整分录模块')
  })

  it('确认时向集中调整表 POST 平衡分录组并打 sourceGroupId', async () => {
    ;(api.post as any).mockResolvedValue({ entry_group_id: 'eg-g3-1' })
    const { addRow, updateCell, publishAdjustment, rows } = setup()
    addRow()
    const dId = rows.value[0].rowId
    updateCell(dId, 'description', '宣告股利')
    updateCell(dId, 'debitAmount', 800)
    updateCell(dId, 'creditAmount', 0)
    addRow()
    const cId = rows.value[1].rowId
    updateCell(cId, 'description', '宣告股利')
    updateCell(cId, 'accountCode', '6111')
    updateCell(cId, 'debitAmount', 0)
    updateCell(cId, 'creditAmount', 800)

    publishAdjustment()
    await vi.waitFor(() => {
      expect(api.post).toHaveBeenCalled()
    })

    expect(api.post).toHaveBeenCalledWith(
      expect.stringContaining('/adjustments'),
      expect.objectContaining({
        adjustment_type: 'aje',
        year: 2025,
        description: expect.stringContaining('宣告股利'),
        line_items: expect.arrayContaining([
          expect.objectContaining({ standard_account_code: '1131', debit_amount: 800 }),
          expect.objectContaining({ standard_account_code: '6111', credit_amount: 800 }),
        ]),
      }),
      expect.anything(),
    )
    expect(rows.value.every((r) => r.sourceGroupId === 'eg-g3-1')).toBe(true)

    // 再次确认不应重复 POST
    ;(api.post as any).mockClear()
    publishAdjustment()
    await new Promise((r) => setTimeout(r, 30))
    expect(api.post).not.toHaveBeenCalled()
  })

  it('不平衡分录组不推送集中表', async () => {
    ;(api.post as any).mockResolvedValue({ entry_group_id: 'x' })
    const { addRow, updateCell, publishAdjustment, rows } = setup()
    addRow()
    updateCell(rows.value[0].rowId, 'description', '单边')
    updateCell(rows.value[0].rowId, 'debitAmount', 100)
    updateCell(rows.value[0].rowId, 'creditAmount', 0)
    publishAdjustment()
    await new Promise((r) => setTimeout(r, 30))
    expect(api.post).not.toHaveBeenCalled()
    expect(rows.value[0].sourceGroupId).toBeFalsy()
  })

  it('兼容旧版 AJE/RJE 字段与旧存储键', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    allResponses.value.set('G3-3-adjustment-rows', {
      item_id: 'G3-3-adjustment-rows',
      conclusion: JSON.stringify([
        { id: 'old-1', entryType: 'RJE', summary: '重分类', accountCode: '1131', debit: 0, credit: 200 },
      ]),
      remark: null,
    })
    const hook = useG3Adjustment({
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
