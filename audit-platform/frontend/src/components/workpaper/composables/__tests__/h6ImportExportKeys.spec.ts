/**
 * H6 导入导出字段对齐 — 往返键名契约单测
 * 确保前端持久化键与 backend _h6_import_export field_keys 一致
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useH6Detail } from '../useH6Detail'
import { useH6Check } from '../useH6Check'

/** 与 backend/_h6_import_export.py 保持同步 */
const H6_2_EXPORT_KEYS = [
  'seq', 'assetName', 'originalCost', 'accumulatedDepreciation', 'impairmentProvision', 'netBookValue',
  'disposalReason', 'startDate',
  'disposalIncome', 'disposalExpenses', 'taxAmount', 'gainLoss',
  'transferAccount', 'completionDate',
  'status', 'refH1Code', 'refH10Code',
  'overOneYearProgress', 'remarks',
] as const

const H6_4_EXPORT_KEYS = [
  'date', 'voucherNo', 'category', 'assetName', 'counterpartAccount',
  'originalCost', 'accumulatedDepreciation', 'impairment', 'netValue',
  'clearingExpense', 'clearingIncome', 'clearingGainLoss',
  'toNonOperating', 'toDisposalGain', 'endingBalance',
  'clearingReason', 'approvedBy', 'indexRef', 'refH1Code', 'refH10Code',
  'check1', 'check2', 'check3', 'check4', 'check5',
  'isAbnormal', 'remark',
] as const

describe('H6 import/export field-key round-trip', () => {
  it('H6-2 persist 含规范导出键（含净值/净损益）', () => {
    const saved: Record<string, any> = {}
    const api = useH6Detail({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(new Map()),
      onSave: (id, val) => { saved[id] = val },
    })
    api.createFromH1Disposal({
      assetName: '叉车',
      originalCost: 100000,
      accDep: 20000,
      impairment: 5000,
      refH1Code: 'H1-8-1',
      disposalReason: '出售',
      startDate: '2025-01-15',
    })
    const rows = saved['H6-2-rows']
    expect(Array.isArray(rows)).toBe(true)
    expect(rows).toHaveLength(1)
    for (const key of H6_2_EXPORT_KEYS) {
      expect(rows[0]).toHaveProperty(key)
    }
    expect(rows[0].accumulatedDepreciation).toBe(20000)
    expect(rows[0].taxAmount).toBe(0)
    expect(rows[0].refH1Code).toBe('H1-8-1')
    expect(rows[0].netBookValue).toBe(75000)
  })

  it('H6-4 persist 扁平 check1–5 与导出键齐全', () => {
    const saved: Record<string, any> = {}
    const api = useH6Check({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(new Map()),
      onSave: (id, val) => { saved[id] = val },
    })
    api.addRow('机组')
    const row = api.rows.value[0]
    api.updateCell(row.rowId, 'originalCost', 1000)
    api.updateCell(row.rowId, 'accumulatedDepreciation', 100)
    api.updateCell(row.rowId, 'checks', [true, true, false, true, true])
    const rows = saved['H6-4-rows']
    expect(Array.isArray(rows)).toBe(true)
    for (const key of H6_4_EXPORT_KEYS) {
      expect(rows[0]).toHaveProperty(key)
    }
    expect(rows[0].check1).toBe(true)
    expect(rows[0].check2).toBe(true)
    expect(rows[0].check3).toBe(false)
    expect(rows[0].check4).toBe(true)
    expect(rows[0].check5).toBe(true)
    expect(rows[0].checks).toEqual([true, true, false, true, true])
  })

  it('旧键导入 H6-2（accDepreciation/tax/h1Reference）仍可归一', () => {
    const onSave = vi.fn()
    const map = new Map<string, any>()
    map.set('H6-2-rows', {
      item_id: 'H6-2-rows',
      remark: JSON.stringify([{
        assetName: '旧键资产',
        originalCost: 500,
        accDepreciation: 50,
        impairmentProvision: 0,
        tax: 10,
        disposalIncome: 400,
        disposalExpenses: 20,
        h1Reference: 'H1-old',
        h10Reference: 'H10-old',
        status: '清理中',
      }]),
      conclusion: null,
    })
    const api = useH6Detail({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(map),
      onSave,
    })
    expect(api.rows.value[0].accumulatedDepreciation).toBe(50)
    expect(api.rows.value[0].taxAmount).toBe(10)
    expect(api.rows.value[0].refH1Code).toBe('H1-old')
    expect(api.rows.value[0].refH10Code).toBe('H10-old')
    expect(api.rows.value[0].netBookValue).toBe(450)
  })
})
