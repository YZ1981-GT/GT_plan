/**
 * useK12Adjustment —— K12-3 调整分录存储结构收敛（per-field → 单键 JSON 数组）
 *
 * spec: adjustment-import-export-contract / Task 3.1 / Task 3.3
 * Property 12：
 *   - 写入仅产生 JSON 键（K12-3-rows），不再写 legacy per-field 键
 *   - 仅有 per-field 历史数据时，读取结果与迁移前一致（历史数据不丢）
 *   - JSON 与 per-field 并存 → 以 JSON 为准
 *   - JSON 解析失败 → 回退 per-field 重建，绝不清空用户数据
 *   - 底稿通道导入（后端写 K12-3-rows JSON 数组）的数据前端可读
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useK12Adjustment, K12_ADJ_ROWS_KEY } from '../useK12Adjustment'

interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

function makeFormData(seed: Record<string, string | null> = {}) {
  const allResponses = ref<Map<string, ChecklistItem>>(new Map())
  for (const [k, v] of Object.entries(seed)) {
    allResponses.value.set(k, { item_id: k, conclusion: null, remark: v })
  }
  const debouncedSave = vi.fn((itemId: string, data: ChecklistItem) => {
    allResponses.value.set(itemId, data)
  })
  const saveBatch = vi.fn(async (items: { itemId: string; value: any }[]) => {
    for (const { itemId, value } of items) {
      const strVal =
        value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
      allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: strVal })
    }
  })
  return { allResponses, debouncedSave, saveBatch } as any
}

const LEGACY = {
  'K12-3-entry-1-type': 'AJE',
  'K12-3-entry-1-desc': '政府补助跨期调整',
  'K12-3-entry-1-code': '6301',
  'K12-3-entry-1-name': '营业外收入',
  'K12-3-entry-1-debit': '5000',
  'K12-3-entry-1-credit': null,
  'K12-3-entry-1-ref': 'K12-2#3',
  'K12-3-entry-1-remark': '经复核',
  'K12-3-entry-2-type': 'AJE',
  'K12-3-entry-2-desc': '政府补助跨期调整',
  'K12-3-entry-2-code': '2401',
  'K12-3-entry-2-name': '递延收益',
  'K12-3-entry-2-debit': null,
  'K12-3-entry-2-credit': '5000',
  'K12-3-entry-2-ref': '',
  'K12-3-entry-2-remark': '',
}

describe('useK12Adjustment — 存储结构收敛（Property 12）', () => {
  let formData: any

  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('写入只产生 JSON 单键，不再写 legacy per-field 键', () => {
    formData = makeFormData()
    const adj = useK12Adjustment(formData)
    adj.addEntry('AJE')
    adj.updateEntry(0, 'description', '罚款收入补确认')
    adj.updateEntry(0, 'creditAmount', 1234.5)

    const savedKeys = formData.debouncedSave.mock.calls.map((c: any[]) => c[0])
    expect(new Set(savedKeys)).toEqual(new Set([K12_ADJ_ROWS_KEY]))
    expect(savedKeys.some((k: string) => k.includes('-entry-'))).toBe(false)

    const payload = JSON.parse(formData.allResponses.value.get(K12_ADJ_ROWS_KEY)!.remark!)
    expect(Array.isArray(payload)).toBe(true)
    expect(payload).toHaveLength(1)
    expect(payload[0]).toMatchObject({
      type: 'AJE',
      description: '罚款收入补确认',
      creditAmount: 1234.5,
    })
  })

  it('仅有 per-field 历史数据时读取结果与迁移前一致（历史不丢）', () => {
    formData = makeFormData(LEGACY)
    const adj = useK12Adjustment(formData)
    adj.restoreEntries()

    expect(adj.entries.value).toHaveLength(2)
    expect(adj.entries.value[0]).toMatchObject({
      index: 1,
      type: 'AJE',
      description: '政府补助跨期调整',
      accountCode: '6301',
      accountName: '营业外收入',
      debitAmount: 5000,
      creditAmount: 0,
      refIndex: 'K12-2#3',
      remark: '经复核',
    })
    expect(adj.entries.value[1]).toMatchObject({ accountCode: '2401', creditAmount: 5000 })
    // 借贷平衡应能算出（5000 / 5000）
    expect(adj.ajeBalance.value.isBalanced).toBe(true)
  })

  it('per-field 重建后首次保存自然收敛为 JSON（旧键不主动删除）', () => {
    formData = makeFormData(LEGACY)
    const adj = useK12Adjustment(formData)
    adj.restoreEntries()
    adj.updateEntry(0, 'remark', '已复核')

    const payload = JSON.parse(formData.allResponses.value.get(K12_ADJ_ROWS_KEY)!.remark!)
    expect(payload).toHaveLength(2)
    // 旧 per-field 键仍在（不主动删除）
    expect(formData.allResponses.value.get('K12-3-entry-1-type')!.remark).toBe('AJE')
  })

  it('JSON 与 per-field 并存 → 以 JSON 为准', () => {
    formData = makeFormData({
      ...LEGACY,
      [K12_ADJ_ROWS_KEY]: JSON.stringify([
        {
          index: 1,
          type: 'RJE',
          description: 'JSON 优先',
          accountCode: '6301',
          accountName: '营业外收入',
          debitAmount: 0,
          creditAmount: 777,
          refIndex: '',
          remark: '',
        },
      ]),
    })
    const adj = useK12Adjustment(formData)
    adj.restoreEntries()

    expect(adj.entries.value).toHaveLength(1)
    expect(adj.entries.value[0].description).toBe('JSON 优先')
    expect(adj.entries.value[0].type).toBe('RJE')
  })

  it('JSON 解析失败 → 回退 per-field 重建，不清空用户数据', () => {
    formData = makeFormData({ ...LEGACY, [K12_ADJ_ROWS_KEY]: '{不是合法JSON' })
    const adj = useK12Adjustment(formData)
    adj.restoreEntries()

    expect(adj.entries.value).toHaveLength(2)
    expect(adj.entries.value[0].accountCode).toBe('6301')
  })

  it('底稿通道导入产物（后端 JSON 数组，字段可能为字符串/缺省）可被读取归一', () => {
    // 后端 import-data 把非数值列存为字符串；index 为文本列
    formData = makeFormData({
      [K12_ADJ_ROWS_KEY]: JSON.stringify([
        {
          id: 'uuid-1',
          index: '1',
          type: 'rje',
          description: '导入行',
          accountCode: '6301',
          accountName: '营业外收入',
          debitAmount: 0,
          creditAmount: 100,
          refIndex: 'X-1',
        },
      ]),
    })
    const adj = useK12Adjustment(formData)
    adj.restoreEntries()

    expect(adj.entries.value).toHaveLength(1)
    expect(adj.entries.value[0]).toMatchObject({
      index: 1,
      type: 'RJE',
      description: '导入行',
      creditAmount: 100,
      refIndex: 'X-1',
      remark: '',
    })
  })

  it('显式空数组不回退旧 per-field 数据（用户已清空）', () => {
    formData = makeFormData({ ...LEGACY, [K12_ADJ_ROWS_KEY]: '[]' })
    const adj = useK12Adjustment(formData)
    adj.restoreEntries()
    expect(adj.entries.value).toHaveLength(0)
  })

  it('saveAndPublish 只写 JSON 单键（借贷平衡时）', async () => {
    formData = makeFormData()
    const adj = useK12Adjustment(formData)
    adj.addEntry('AJE')
    adj.updateEntry(0, 'accountCode', '6301')
    adj.updateEntry(0, 'creditAmount', 100)
    adj.addEntry('AJE')
    adj.updateEntry(1, 'accountCode', '1122')
    adj.updateEntry(1, 'debitAmount', 100)

    await adj.saveAndPublish()

    expect(formData.saveBatch).toHaveBeenCalledTimes(1)
    const items = formData.saveBatch.mock.calls[0][0]
    expect(items).toHaveLength(1)
    expect(items[0].itemId).toBe(K12_ADJ_ROWS_KEY)
    expect(JSON.parse(items[0].value)).toHaveLength(2)
  })

  it('删除行后重编号并整体重写 JSON', () => {
    formData = makeFormData()
    const adj = useK12Adjustment(formData)
    adj.addEntry('AJE')
    adj.addEntry('AJE')
    adj.updateEntry(0, 'description', '第一笔')
    adj.updateEntry(1, 'description', '第二笔')
    adj.removeEntry(0)

    const payload = JSON.parse(formData.allResponses.value.get(K12_ADJ_ROWS_KEY)!.remark!)
    expect(payload).toHaveLength(1)
    expect(payload[0]).toMatchObject({ index: 1, description: '第二笔' })
  })
})
