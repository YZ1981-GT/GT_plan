/**
 * useF2Adjustment — 科目表 / 推送集中表契约
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { F2_INVENTORY_ACCOUNTS } from '../f2AccountModel'

vi.mock('@/services/apiProxy', () => ({
  api: {
    post: vi.fn(),
  },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { useF2Adjustment } from '../useF2Adjustment'
import type { ChecklistResponse } from '../useF2FormData'

function makeMap(rows: unknown[]): Map<string, ChecklistResponse> {
  const map = new Map<string, ChecklistResponse>()
  map.set('F2-14-rows', {
    item_id: 'F2-14-rows',
    conclusion: null,
    remark: JSON.stringify(rows),
  })
  return map
}

describe('F2_INVENTORY_ACCOUNTS (CAS)', () => {
  it('lists 1412 as 商品进销差价 and 1471 as 存货跌价准备', () => {
    const byCode = Object.fromEntries(F2_INVENTORY_ACCOUNTS.map((a) => [a.code, a.name]))
    expect(byCode['1412']).toBe('商品进销差价')
    expect(byCode['1471']).toBe('存货跌价准备')
    expect(byCode['1406']).toBe('库存商品')
  })
})

describe('useF2Adjustment pushConfirmedToCentralModule', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('skips unbalanced groups and posts balanced AJE pair', async () => {
    ;(api.post as any).mockResolvedValue({ entry_group_id: 'grp-f2-1' })

    const rows = [
      {
        rowId: 'a1', seq: 1, summary: '补提跌价', accountCode: '1471', accountName: '存货跌价准备',
        debitAmount: 0, creditAmount: 100, entryType: 'AJE', indexRef: '', remark: '', noteItem: '',
      },
      {
        rowId: 'a2', seq: 2, summary: '补提跌价', accountCode: '6701', accountName: '资产减值损失',
        debitAmount: 100, creditAmount: 0, entryType: 'AJE', indexRef: '', remark: '', noteItem: '',
      },
    ]
    const allResponses = ref(makeMap(rows))
    const adj = useF2Adjustment({
      allResponses,
      isReadonly: ref(false),
      projectId: ref('proj-1'),
      auditYear: ref(2025),
    })

    // hydrate from map
    await Promise.resolve()
    expect(adj.isBalanced.value).toBe(true)

    const pushed = await adj.pushConfirmedToCentralModule()
    expect(pushed).toBe(1)
    expect(api.post).toHaveBeenCalledTimes(1)
    const [url, body] = (api.post as any).mock.calls[0]
    expect(url).toContain('/api/projects/proj-1/adjustments')
    expect(body.adjustment_type).toBe('aje')
    expect(body.description).toContain('[F2]')
    expect(body.line_items).toHaveLength(2)
    expect(eventBus.emit).toHaveBeenCalledWith('adjustment:updated')
    expect(adj.rows.value.every((r) => r.sourceGroupId === 'grp-f2-1')).toBe(true)
  })

  it('does not re-push rows that already have sourceGroupId', async () => {
    const rows = [
      {
        rowId: 'a1', seq: 1, summary: '已推', accountCode: '1401', accountName: '原材料',
        debitAmount: 50, creditAmount: 0, entryType: 'AJE', indexRef: '', remark: '', noteItem: '',
        sourceGroupId: 'existing',
      },
      {
        rowId: 'a2', seq: 2, summary: '已推', accountCode: '5001', accountName: '主营业务成本',
        debitAmount: 0, creditAmount: 50, entryType: 'AJE', indexRef: '', remark: '', noteItem: '',
        sourceGroupId: 'existing',
      },
    ]
    const adj = useF2Adjustment({
      allResponses: ref(makeMap(rows)),
      projectId: ref('proj-1'),
      auditYear: ref(2025),
    })
    await Promise.resolve()
    const pushed = await adj.pushConfirmedToCentralModule()
    expect(pushed).toBe(0)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('emits adjustment:created via eventBus on persist', async () => {
    const adj = useF2Adjustment({
      allResponses: ref(makeMap([])),
      projectId: ref('proj-1'),
      auditYear: ref(2025),
    })
    await Promise.resolve()
    adj.updateCell(adj.rows.value[0].rowId, 'debitAmount', 10)
    adj.updateCell(adj.rows.value[0].rowId, 'summary', '测试')
    // second line to keep something non-zero for publish
    adj.addRow()
    adj.updateCell(adj.rows.value[1].rowId, 'creditAmount', 10)
    adj.updateCell(adj.rows.value[1].rowId, 'summary', '测试')
    adj.publishAdjustments()
    expect(eventBus.emit).toHaveBeenCalledWith(
      'adjustment:created',
      expect.objectContaining({ wpCode: 'F2' }),
    )
  })

  it('confirmAndSync publishes and pushes balanced pending groups', async () => {
    ;(api.post as any).mockResolvedValue({ entry_group_id: 'grp-sync-1' })
    const rows = [
      {
        rowId: 'a1', seq: 1, summary: '同步推送', accountCode: '1471', accountName: '存货跌价准备',
        debitAmount: 0, creditAmount: 80, entryType: 'AJE', indexRef: '', remark: '', noteItem: '',
      },
      {
        rowId: 'a2', seq: 2, summary: '同步推送', accountCode: '6701', accountName: '资产减值损失',
        debitAmount: 80, creditAmount: 0, entryType: 'AJE', indexRef: '', remark: '', noteItem: '',
      },
    ]
    const adj = useF2Adjustment({
      allResponses: ref(makeMap(rows)),
      projectId: ref('proj-1'),
      auditYear: ref(2025),
    })
    await Promise.resolve()
    const pushed = await adj.confirmAndSync()
    expect(pushed).toBe(1)
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(eventBus.emit).toHaveBeenCalledWith(
      'adjustment:created',
      expect.objectContaining({ wpCode: 'F2' }),
    )
    expect(adj.rows.value.every((r) => r.sourceGroupId === 'grp-sync-1')).toBe(true)
  })

  it('quiet push skips toast when unbalanced', async () => {
    const { ElMessage } = await import('element-plus')
    const rows = [
      {
        rowId: 'a1', seq: 1, summary: '不平衡', accountCode: '1401', accountName: '原材料',
        debitAmount: 10, creditAmount: 0, entryType: 'AJE', indexRef: '', remark: '', noteItem: '',
      },
    ]
    const adj = useF2Adjustment({
      allResponses: ref(makeMap(rows)),
      projectId: ref('proj-1'),
      auditYear: ref(2025),
    })
    await Promise.resolve()
    const pushed = await adj.pushConfirmedToCentralModule({ quiet: true })
    expect(pushed).toBe(0)
    expect(api.post).not.toHaveBeenCalled()
    expect(ElMessage.warning).not.toHaveBeenCalled()
  })
})
