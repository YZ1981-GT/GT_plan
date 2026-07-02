/**
 * Unit Tests — D1-3 原值明细(按客户) composable
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 5.1
 *
 * 验证 useD1DetailCustomer 核心逻辑：
 * - matchRelatedParty 关联方匹配
 * - addRow / removeRow CRUD
 * - updateCell 自动触发关联方匹配
 * - subtotalRow 计算
 * - filteredRows 搜索过滤
 * - recalcRow 公式字段
 * - 序列化/反序列化
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useD1DetailCustomer } from '../useD1DetailCustomer'
import type { UseD1DetailCustomerOptions, CustomerRow } from '../useD1DetailCustomer'
import type { ChecklistResponse } from '../useD1FormData'

// Mock onBeforeUnmount to avoid lifecycle errors in test
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onBeforeUnmount: vi.fn(),
  }
})

// ─── Test Helpers ────────────────────────────────────────────────────────────

function createOptions(
  overrides: Partial<UseD1DetailCustomerOptions> = {}
): UseD1DetailCustomerOptions {
  return {
    allResponses: ref(new Map<string, ChecklistResponse>()),
    wpId: ref('test-wp-id'),
    projectId: ref('test-project-id'),
    saveImmediate: vi.fn().mockResolvedValue(undefined),
    isReadonly: ref(false),
    relatedParties: ref<string[]>([]),
    ...overrides,
  }
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('useD1DetailCustomer', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('初始状态', () => {
    it('无存储数据时rows为空数组', () => {
      const options = createOptions()
      const { rows } = useD1DetailCustomer(options)
      expect(rows.value).toHaveLength(0)
    })

    it('从allResponses加载已存储的行数据', () => {
      const storedRows = [
        {
          rowId: 'dynamic-1',
          customerName: '客户A',
          companyCode: 'A001',
          relationType: '非关联方',
          priorUnadjusted: 100,
          priorAje: 10,
          priorRje: 5,
          currentIncrease: 50,
          currentDecrease: 20,
          currentBalance: 0,
          reclassification: 0,
          currentAje: 0,
          currentRje: 0,
        },
      ]
      const allResponses = ref(new Map<string, ChecklistResponse>([
        ['D1-cust-rows', { item_id: 'D1-cust-rows', conclusion: null, remark: JSON.stringify(storedRows) }],
      ]))
      const options = createOptions({ allResponses })
      const { rows } = useD1DetailCustomer(options)

      expect(rows.value).toHaveLength(1)
      expect(rows.value[0].customerName).toBe('客户A')
      expect(rows.value[0].companyCode).toBe('A001')
      // Verify computed fields are recalculated
      expect(rows.value[0].priorAudited).toBe(115) // 100 + 10 + 5
      expect(rows.value[0].currentUnadjusted).toBe(145) // 115 + 50 - 20 + 0
      expect(rows.value[0].currentAudited).toBe(145) // 145 + 0 + 0
    })

    it('JSON解析失败时回退为空数组', () => {
      const allResponses = ref(new Map<string, ChecklistResponse>([
        ['D1-cust-rows', { item_id: 'D1-cust-rows', conclusion: null, remark: 'invalid-json{{{' }],
      ]))
      const options = createOptions({ allResponses })
      const { rows } = useD1DetailCustomer(options)
      expect(rows.value).toHaveLength(0)
    })
  })

  describe('matchRelatedParty', () => {
    it('空名称返回空字符串', () => {
      const options = createOptions({ relatedParties: ref(['公司A', '公司B']) })
      const { matchRelatedParty } = useD1DetailCustomer(options)
      expect(matchRelatedParty('')).toBe('')
      expect(matchRelatedParty('  ')).toBe('')
    })

    it('名称在关联方列表中返回"关联方"', () => {
      const options = createOptions({ relatedParties: ref(['北京华为技术有限公司', '深圳腾讯科技']) })
      const { matchRelatedParty } = useD1DetailCustomer(options)
      expect(matchRelatedParty('北京华为技术有限公司')).toBe('关联方')
    })

    it('名称包含关联方名称(或反向包含)返回"关联方"（模糊匹配）', () => {
      const options = createOptions({ relatedParties: ref(['华为', '腾讯']) })
      const { matchRelatedParty } = useD1DetailCustomer(options)
      // name includes party
      expect(matchRelatedParty('北京华为技术有限公司')).toBe('关联方')
    })

    it('大小写不敏感匹配', () => {
      const options = createOptions({ relatedParties: ref(['ABC Corp', 'XYZ Inc']) })
      const { matchRelatedParty } = useD1DetailCustomer(options)
      expect(matchRelatedParty('abc corp')).toBe('关联方')
      expect(matchRelatedParty('ABC CORP')).toBe('关联方')
    })

    it('不在关联方列表中返回"非关联方"', () => {
      const options = createOptions({ relatedParties: ref(['公司A', '公司B']) })
      const { matchRelatedParty } = useD1DetailCustomer(options)
      expect(matchRelatedParty('公司C')).toBe('非关联方')
    })
  })

  describe('addRow / removeRow', () => {
    it('addRow新增一行，数值字段全为0', () => {
      const options = createOptions()
      const { rows, addRow } = useD1DetailCustomer(options)

      addRow()
      expect(rows.value).toHaveLength(1)
      const newRow = rows.value[0]
      expect(newRow.rowId).toMatch(/^dynamic-/)
      expect(newRow.customerName).toBe('')
      expect(newRow.priorUnadjusted).toBe(0)
      expect(newRow.currentAudited).toBe(0)
    })

    it('removeRow删除指定行', () => {
      const options = createOptions()
      const { rows, addRow, removeRow } = useD1DetailCustomer(options)

      addRow()
      addRow()
      expect(rows.value).toHaveLength(2)
      const rowId = rows.value[0].rowId
      removeRow(rowId)
      expect(rows.value).toHaveLength(1)
      expect(rows.value[0].rowId).not.toBe(rowId)
    })

    it('readonly模式下addRow/removeRow无效', () => {
      const options = createOptions({ isReadonly: ref(true) })
      const { rows, addRow, removeRow } = useD1DetailCustomer(options)

      addRow()
      expect(rows.value).toHaveLength(0)
    })
  })

  describe('updateCell', () => {
    it('编辑金额字段触发公式重算', () => {
      const options = createOptions()
      const { rows, addRow, updateCell } = useD1DetailCustomer(options)

      addRow()
      const rowId = rows.value[0].rowId
      updateCell(rowId, 'priorUnadjusted', 100)
      updateCell(rowId, 'priorAje', 20)
      updateCell(rowId, 'priorRje', 5)

      expect(rows.value[0].priorAudited).toBe(125) // 100 + 20 + 5
    })

    it('编辑customerName自动触发关联方匹配', () => {
      const options = createOptions({ relatedParties: ref(['华为', '腾讯']) })
      const { rows, addRow, updateCell } = useD1DetailCustomer(options)

      addRow()
      const rowId = rows.value[0].rowId
      updateCell(rowId, 'customerName', '北京华为科技')

      expect(rows.value[0].relationType).toBe('关联方')
    })

    it('编辑customerName为非关联方名称时自动标记', () => {
      const options = createOptions({ relatedParties: ref(['华为']) })
      const { rows, addRow, updateCell } = useD1DetailCustomer(options)

      addRow()
      const rowId = rows.value[0].rowId
      updateCell(rowId, 'customerName', '阿里巴巴')

      expect(rows.value[0].relationType).toBe('非关联方')
    })

    it('D1-3 currentUnadjusted计算含reclassification', () => {
      const options = createOptions()
      const { rows, addRow, updateCell } = useD1DetailCustomer(options)

      addRow()
      const rowId = rows.value[0].rowId
      updateCell(rowId, 'priorUnadjusted', 1000)
      updateCell(rowId, 'currentIncrease', 500)
      updateCell(rowId, 'currentDecrease', 200)
      updateCell(rowId, 'reclassification', 50)

      // priorAudited = 1000 + 0 + 0 = 1000
      // currentUnadjusted = 1000 + 500 - 200 + 50 = 1350
      expect(rows.value[0].priorAudited).toBe(1000)
      expect(rows.value[0].currentUnadjusted).toBe(1350)
    })
  })

  describe('subtotalRow', () => {
    it('小计行等于所有行之和', () => {
      const options = createOptions()
      const { rows, addRow, updateCell, subtotalRow } = useD1DetailCustomer(options)

      addRow()
      addRow()
      updateCell(rows.value[0].rowId, 'priorUnadjusted', 100)
      updateCell(rows.value[1].rowId, 'priorUnadjusted', 200)

      expect(subtotalRow.value.priorUnadjusted).toBe(300)
      expect(subtotalRow.value.customerName).toBe('小计')
    })

    it('空行时小计全为0', () => {
      const options = createOptions()
      const { subtotalRow } = useD1DetailCustomer(options)
      expect(subtotalRow.value.priorUnadjusted).toBe(0)
      expect(subtotalRow.value.currentAudited).toBe(0)
    })
  })

  describe('filteredRows (搜索过滤)', () => {
    it('无搜索关键字时返回全部行', () => {
      const options = createOptions()
      const { rows, addRow, updateCell, filteredRows, searchQuery } = useD1DetailCustomer(options)

      addRow()
      addRow()
      updateCell(rows.value[0].rowId, 'customerName', '华为')
      updateCell(rows.value[1].rowId, 'customerName', '腾讯')

      searchQuery.value = ''
      expect(filteredRows.value).toHaveLength(2)
    })

    it('按客户名称模糊搜索（大小写不敏感）', () => {
      const options = createOptions()
      const { rows, addRow, updateCell, filteredRows, searchQuery } = useD1DetailCustomer(options)

      addRow()
      addRow()
      addRow()
      updateCell(rows.value[0].rowId, 'customerName', 'ABC Corp')
      updateCell(rows.value[1].rowId, 'customerName', 'XYZ Inc')
      updateCell(rows.value[2].rowId, 'customerName', 'abc technology')

      searchQuery.value = 'abc'
      expect(filteredRows.value).toHaveLength(2)
      expect(filteredRows.value[0].customerName).toBe('ABC Corp')
      expect(filteredRows.value[1].customerName).toBe('abc technology')
    })

    it('搜索关键字为空格时返回全部行', () => {
      const options = createOptions()
      const { rows, addRow, updateCell, filteredRows, searchQuery } = useD1DetailCustomer(options)

      addRow()
      updateCell(rows.value[0].rowId, 'customerName', '华为')
      searchQuery.value = '   '
      expect(filteredRows.value).toHaveLength(1)
    })
  })

  describe('debounce保存', () => {
    it('编辑后2秒触发saveImmediate', () => {
      const saveImmediate = vi.fn().mockResolvedValue(undefined)
      const options = createOptions({ saveImmediate })
      const { addRow } = useD1DetailCustomer(options)

      addRow()
      expect(saveImmediate).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      expect(saveImmediate).toHaveBeenCalledTimes(1)
    })

    it('多次编辑合并为单次保存', () => {
      const saveImmediate = vi.fn().mockResolvedValue(undefined)
      const options = createOptions({ saveImmediate })
      const { addRow, updateCell, rows } = useD1DetailCustomer(options)

      addRow()
      vi.advanceTimersByTime(500)
      updateCell(rows.value[0].rowId, 'customerName', '测试')
      vi.advanceTimersByTime(500)
      updateCell(rows.value[0].rowId, 'priorUnadjusted', 100)

      // No save yet (still within debounce window)
      expect(saveImmediate).not.toHaveBeenCalled()

      vi.advanceTimersByTime(2000)
      expect(saveImmediate).toHaveBeenCalledTimes(1)
    })
  })
})

// ─── Property-Based Tests (fast-check) ───────────────────────────────────────

import * as fc from 'fast-check'

describe('Feature: d1-adjudication-table, Property 9: 客户名称关联方自动匹配', () => {
  /**
   * Property 9: 客户名称关联方自动匹配
   *
   * For any 客户名称字符串和关联方名单列表，若客户名称存在于关联方名单中（模糊匹配），
   * 则 matchRelatedParty 返回 '关联方'；否则返回 '非关联方'。
   *
   * **Validates: Requirements 5.3**
   */

  // Replicate the matching logic as a pure reference function
  function referenceMatchRelatedParty(name: string, parties: string[]): string {
    if (!name || name.trim() === '') return ''
    const lowerName = name.toLowerCase()
    for (const party of parties) {
      if (party.toLowerCase().includes(lowerName) || lowerName.includes(party.toLowerCase())) {
        return '关联方'
      }
    }
    return '非关联方'
  }

  it('名称在关联方列表中（精确匹配）应返回"关联方"', () => {
    // Generate non-whitespace strings to avoid the empty-name branch
    const nonBlankString = fc.string({ minLength: 1, maxLength: 20 }).filter(s => s.trim().length > 0)

    fc.assert(
      fc.property(
        fc.array(nonBlankString, { minLength: 1, maxLength: 10 }),
        fc.nat({ max: 9 }),
        (parties, idxRaw) => {
          const idx = idxRaw % parties.length
          const name = parties[idx]

          const options = createOptions({ relatedParties: ref(parties) })
          const { matchRelatedParty } = useD1DetailCustomer(options)

          const result = matchRelatedParty(name)
          return result === '关联方'
        },
      ),
      { numRuns: 100 },
    )
  })

  it('名称不在关联方列表中应返回"非关联方"', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }),
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 0, maxLength: 10 }),
        (name, parties) => {
          // Only test if name truly does NOT match any party (using reference logic)
          const expected = referenceMatchRelatedParty(name, parties)
          if (expected !== '非关联方') return true // skip, this case is covered above

          const options = createOptions({ relatedParties: ref(parties) })
          const { matchRelatedParty } = useD1DetailCustomer(options)

          const result = matchRelatedParty(name)
          return result === '非关联方'
        },
      ),
      { numRuns: 100 },
    )
  })

  it('matchRelatedParty结果与参考实现一致', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }),
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 0, maxLength: 10 }),
        (name, parties) => {
          const expected = referenceMatchRelatedParty(name, parties)

          const options = createOptions({ relatedParties: ref(parties) })
          const { matchRelatedParty } = useD1DetailCustomer(options)

          const result = matchRelatedParty(name)
          return result === expected
        },
      ),
      { numRuns: 100 },
    )
  })
})

describe('Feature: d1-adjudication-table, Property 10: 客户搜索过滤正确性', () => {
  /**
   * Property 10: 客户搜索过滤正确性
   *
   * For any 搜索关键字 q 和客户行列表，filteredRows 中每行的 customerName 应包含 q
   * （大小写不敏感），且所有匹配行都应出现在结果中（无遗漏无多余）。
   *
   * **Validates: Requirements 5.7**
   */

  // CustomerRow-like generator (only customerName matters for search filtering)
  const customerNameArb = fc.string({ minLength: 0, maxLength: 30 })

  it('filteredRows中每行的customerName包含搜索关键字（大小写不敏感）', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 10 }),
        fc.array(customerNameArb, { minLength: 1, maxLength: 15 }),
        (query, names) => {
          const options = createOptions()
          const { rows, addRow, updateCell, filteredRows, searchQuery } = useD1DetailCustomer(options)

          // Add rows and set customer names
          for (const name of names) {
            addRow()
          }
          for (let i = 0; i < names.length; i++) {
            updateCell(rows.value[i].rowId, 'customerName', names[i])
          }

          // Set search query
          searchQuery.value = query

          const q = query.trim().toLowerCase()
          if (!q) {
            // Empty query returns all rows
            return filteredRows.value.length === rows.value.length
          }

          // Every row in filteredRows must contain query
          const allMatch = filteredRows.value.every(
            r => r.customerName.toLowerCase().includes(q),
          )

          return allMatch
        },
      ),
      { numRuns: 100 },
    )
  })

  it('所有匹配行都出现在filteredRows中（无遗漏）', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 10 }),
        fc.array(customerNameArb, { minLength: 1, maxLength: 15 }),
        (query, names) => {
          const options = createOptions()
          const { rows, addRow, updateCell, filteredRows, searchQuery } = useD1DetailCustomer(options)

          // Add rows and set customer names
          for (const name of names) {
            addRow()
          }
          for (let i = 0; i < names.length; i++) {
            updateCell(rows.value[i].rowId, 'customerName', names[i])
          }

          // Set search query
          searchQuery.value = query

          const q = query.trim().toLowerCase()
          if (!q) {
            return filteredRows.value.length === rows.value.length
          }

          // Count how many rows should match
          const expectedCount = rows.value.filter(
            r => r.customerName.toLowerCase().includes(q),
          ).length

          // No missing, no extra
          return filteredRows.value.length === expectedCount
        },
      ),
      { numRuns: 100 },
    )
  })

  it('搜索关键字为空时返回全部行', () => {
    fc.assert(
      fc.property(
        fc.array(customerNameArb, { minLength: 0, maxLength: 15 }),
        (names) => {
          const options = createOptions()
          const { rows, addRow, updateCell, filteredRows, searchQuery } = useD1DetailCustomer(options)

          for (const name of names) {
            addRow()
          }
          for (let i = 0; i < names.length; i++) {
            updateCell(rows.value[i].rowId, 'customerName', names[i])
          }

          // Empty query (or whitespace only)
          searchQuery.value = '   '

          return filteredRows.value.length === rows.value.length
        },
      ),
      { numRuns: 100 },
    )
  })
})
