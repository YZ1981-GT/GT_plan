/**
 * L1-2 明细表：稳定行身份 + 单条 store item。
 *
 * spec: l-cycle-true-adapter-registration · Task 5b
 *
 * 🔴 守的是「位置化行身份已被换掉」这件事本身：
 * 旧形态 `L1-det-{rowIndex+1}-{field}` 在 `removeRow()` 后靠 `_triggerSaveAll()`
 * 重建整个序列，删中间行会让后续行的 item_id 全部错位、用户填的值静默跟错行。
 * 契约 schema 的 `FORBIDDEN_ROW_IDENTITY_KINDS` 也明含 index/ordinal/position/array_index。
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import {
  DETAIL_ROWS_ITEM_ID,
  createEmptyDetailRow,
  type DetailRow,
} from '@/composables/useL1FormData'
import { useL1Detail } from '@/composables/useL1Detail'

vi.mock('element-plus', () => ({
  ElMessageBox: { prompt: vi.fn() },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

interface SavedItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

function harness(rows: DetailRow[] = []) {
  const detailRows = ref<DetailRow[]>(rows)
  const saved: SavedItem[][] = []
  const formData = {
    detailRows,
    debounceSave: (items: SavedItem[]) => saved.push(items),
  }
  return { detailRows, saved, api: useL1Detail(formData as never) }
}

function rowWith(bank: string): DetailRow {
  return { ...createEmptyDetailRow(), bank }
}

describe('createEmptyDetailRow', () => {
  it('每次铸出的 rowId 都不同（唯一性优先于确定性）', () => {
    const ids = new Set(Array.from({ length: 50 }, () => createEmptyDetailRow().rowId))
    expect(ids.size).toBe(50)
  })

  it('字段齐全并对齐模板 28 列 + 2 个 HTML-only 字段', () => {
    const row = createEmptyDetailRow()
    // A..AB 共 28 个受管字段
    for (const key of [
      'seqNo', 'loanType', 'bank', 'startDate', 'endDate', 'rate', 'rateKind',
      'beginning', 'creditAmount', 'debitAmount', 'endBalance',
      'priorAje', 'priorRje', 'ajeIncrease', 'ajeDecrease', 'rjeIncrease', 'rjeDecrease',
      'auditedPrior', 'auditedIncrease', 'auditedDecrease', 'auditedEnd',
      'purpose', 'guarantee', 'contractNo', 'isOverdue', 'confirmationRef',
      'creditReportChecked', 'remark',
    ]) {
      expect(row, `缺受管字段 ${key}`).toHaveProperty(key)
    }
    // HTML-only（模板无对应列，契约不映射）
    expect(row).toHaveProperty('amount')
    expect(row).toHaveProperty('currency')
    expect(row.rowId).toMatch(/^l12-\d+-/)
  })
})

describe('删行不动其余行的身份', () => {
  it('删中间行后，其余行 rowId 逐个不变（位置化缺陷的反例）', () => {
    const rows = ['A', 'B', 'C', 'D'].map(rowWith)
    const before = rows.map((r) => r.rowId)
    const { detailRows, api } = harness(rows)

    api.removeRow(1) // 删 B

    expect(detailRows.value.map((r) => r.bank)).toEqual(['A', 'C', 'D'])
    expect(detailRows.value.map((r) => r.rowId)).toEqual([before[0], before[2], before[3]])
  })

  it('按 rowId 删能删中目标行（排序后下标不可信时的正解）', () => {
    const rows = ['A', 'B', 'C'].map(rowWith)
    const target = rows[1].rowId
    const { detailRows, api } = harness(rows)

    expect(api.removeRowById(target)).toBe(true)
    expect(detailRows.value.map((r) => r.bank)).toEqual(['A', 'C'])
    expect(api.removeRowById('不存在的身份')).toBe(false)
  })
})

describe('持久化形态', () => {
  it('整表只发一条 item，item_id 恰为 L1-2-rows', () => {
    const { saved, api } = harness(['A', 'B'].map(rowWith))

    api.updateRow(0, 'beginning', 100)

    expect(saved).toHaveLength(1)
    expect(saved[0]).toHaveLength(1)
    expect(saved[0][0].item_id).toBe(DETAIL_ROWS_ITEM_ID)
    expect(DETAIL_ROWS_ITEM_ID).toBe('L1-2-rows')
  })

  it('载荷是 DetailRow[] 的 JSON，且每行带 rowId', () => {
    const { saved, api } = harness(['A', 'B'].map(rowWith))

    api.updateRow(1, 'creditAmount', 50)

    const payload = JSON.parse(saved[0][0].remark as string) as DetailRow[]
    expect(payload).toHaveLength(2)
    expect(payload.every((r) => typeof r.rowId === 'string' && r.rowId.length > 0)).toBe(true)
  })

  it('🔴 不再产生任何 `L1-det-` 前缀的 item_id（旧位置化通道已拆除）', () => {
    const { saved, api } = harness(['A', 'B', 'C'].map(rowWith))

    api.updateRow(0, 'beginning', 1)
    api.removeRow(2)

    const allIds = saved.flat().map((i) => i.item_id)
    expect(allIds.length).toBeGreaterThan(0)
    expect(allIds.filter((id) => id.startsWith('L1-det-'))).toEqual([])
    expect(new Set(allIds)).toEqual(new Set([DETAIL_ROWS_ITEM_ID]))
  })

  it('空表落 null 而不是 "[]" 字符串（与后端 EMPTY_STORE_PAYLOAD 语义分开）', () => {
    const rows = [rowWith('A')]
    const { saved, api } = harness(rows)

    api.removeRow(0)

    expect(saved[0][0].remark).toBeNull()
  })
})

describe('负债口径派生仍成立', () => {
  it('endBalance = 期初 + 贷方 − 借方（与模板 K=H+I-J 同义）', () => {
    const { detailRows, api } = harness([rowWith('A')])

    api.updateRow(0, 'beginning', 1000)
    api.updateRow(0, 'creditAmount', 500)
    api.updateRow(0, 'debitAmount', 200)

    expect(detailRows.value[0].endBalance).toBe(1300)
  })
})
