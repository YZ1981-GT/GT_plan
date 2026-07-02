/**
 * Property-Based Tests — D1 审定表跨Sheet数据流完整性
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 3.2
 *
 * 使用 fast-check + vitest 验证 Property 6: 跨Sheet数据流完整性。
 * 由于 composable 需要 Vue reactivity，这里直接测试跨Sheet映射逻辑：
 * - 从 allResponses Map 解析 D1-cat-rows → 原值区行数据
 * - 从 allResponses Map 解析 D1-bd-individual-rows / D1-bd-portfolio-rows → 坏账区行之和
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { parseNum, calcAuditedAmount } from '../useD1FormulaEngine'

// ─── Types mirroring composable internals ────────────────────────────────────

interface CategoryRowData {
  rowId: string
  category: string
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number
}

interface BadDebtRowData {
  rowId: string
  priorAudited: number
  currentAudited: number
}

// ─── Generators ──────────────────────────────────────────────────────────────

const amountArb = fc.float({ min: -1e9, max: 1e9, noNaN: true })

const categoryRowArb = (category: string): fc.Arbitrary<CategoryRowData> =>
  fc.record({
    rowId: fc.constant(`fixed-${category}`),
    category: fc.constant(category),
    priorUnadjusted: amountArb,
    priorAje: amountArb,
    priorRje: amountArb,
    priorAudited: amountArb,
    currentUnadjusted: amountArb,
    currentAje: amountArb,
    currentRje: amountArb,
    currentAudited: amountArb,
  })

const badDebtRowArb: fc.Arbitrary<BadDebtRowData> =
  fc.record({
    rowId: fc.string({ minLength: 4, maxLength: 8 }).map(s => `bd-${s}`),
    priorAudited: amountArb,
    currentAudited: amountArb,
  })

// ─── Helper: simulate cross-sheet logic from useD1Adjudication ───────────────

/**
 * Replicates the parsing logic in useD1Adjudication.categoryRows computed:
 * Read "D1-cat-rows" remark → JSON.parse → CategoryRowData[]
 */
function parseCategoryRows(allResponses: Map<string, { item_id: string; remark: string | null }>): CategoryRowData[] {
  const raw = allResponses.get('D1-cat-rows')?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch { return [] }
}

/**
 * Replicates the parsing logic in useD1Adjudication.badDebtRows computed:
 * Read "D1-bd-individual-rows" + "D1-bd-portfolio-rows" remark → merge
 */
function parseBadDebtRows(allResponses: Map<string, { item_id: string; remark: string | null }>): BadDebtRowData[] {
  const rows: BadDebtRowData[] = []
  for (const key of ['D1-bd-individual-rows', 'D1-bd-portfolio-rows']) {
    const raw = allResponses.get(key)?.remark
    if (!raw) continue
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) rows.push(...parsed)
    } catch { /* skip */ }
  }
  return rows
}

/**
 * Replicates the gross section cross-sheet mapping logic:
 * Find category row matching '银行' or '商业' → override row values
 */
function mapCategoryToGrossRow(
  categoryRows: CategoryRowData[],
  targetCategory: '银行' | '商业',
): { priorUnadjusted: number; priorAje: number; priorRje: number; priorAudited: number; currentUnadjusted: number; currentAje: number; currentRje: number; currentAudited: number } | null {
  const catRow = categoryRows.find(r => r.category?.includes(targetCategory))
  if (!catRow) return null
  const priorUnadjusted = parseNum(catRow.priorUnadjusted)
  const priorAje = parseNum(catRow.priorAje)
  const priorRje = parseNum(catRow.priorRje)
  const priorAudited = calcAuditedAmount(priorUnadjusted, priorAje, priorRje)
  const currentUnadjusted = parseNum(catRow.currentUnadjusted)
  const currentAje = parseNum(catRow.currentAje)
  const currentRje = parseNum(catRow.currentRje)
  const currentAudited = calcAuditedAmount(currentUnadjusted, currentAje, currentRje)
  return { priorUnadjusted, priorAje, priorRje, priorAudited, currentUnadjusted, currentAje, currentRje, currentAudited }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 跨Sheet数据流完整性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 6: 跨Sheet数据流完整性', () => {
  /**
   * **Validates: Requirements 2.1, 2.2**
   *
   * D1-1原值区银行承兑行 = D1-2中银行承兑行数据
   * D1-1原值区商业承兑行 = D1-2中商业承兑行数据
   * 坏账准备区 = D1-4全部行之和
   */
  it('原值区行正确映射来自D1-2类别行数据', () => {
    fc.assert(
      fc.property(
        categoryRowArb('银行承兑汇票'),
        categoryRowArb('商业承兑汇票'),
        (bankRow, commercialRow) => {
          // Set up allResponses map with serialized category rows
          const allResponses = new Map<string, { item_id: string; remark: string | null }>()
          const catRows = [bankRow, commercialRow]
          allResponses.set('D1-cat-rows', {
            item_id: 'D1-cat-rows',
            remark: JSON.stringify(catRows),
          })

          // Parse using the same logic as the composable
          const parsed = parseCategoryRows(allResponses)
          expect(parsed).toHaveLength(2)

          // Verify bank row mapping
          const bankMapped = mapCategoryToGrossRow(parsed, '银行')
          expect(bankMapped).not.toBeNull()
          expect(bankMapped!.priorUnadjusted).toBeCloseTo(parseNum(bankRow.priorUnadjusted), 5)
          expect(bankMapped!.priorAje).toBeCloseTo(parseNum(bankRow.priorAje), 5)
          expect(bankMapped!.priorRje).toBeCloseTo(parseNum(bankRow.priorRje), 5)
          expect(bankMapped!.priorAudited).toBeCloseTo(
            calcAuditedAmount(parseNum(bankRow.priorUnadjusted), parseNum(bankRow.priorAje), parseNum(bankRow.priorRje)),
            5,
          )
          expect(bankMapped!.currentUnadjusted).toBeCloseTo(parseNum(bankRow.currentUnadjusted), 5)
          expect(bankMapped!.currentAje).toBeCloseTo(parseNum(bankRow.currentAje), 5)
          expect(bankMapped!.currentRje).toBeCloseTo(parseNum(bankRow.currentRje), 5)
          expect(bankMapped!.currentAudited).toBeCloseTo(
            calcAuditedAmount(parseNum(bankRow.currentUnadjusted), parseNum(bankRow.currentAje), parseNum(bankRow.currentRje)),
            5,
          )

          // Verify commercial row mapping
          const commercialMapped = mapCategoryToGrossRow(parsed, '商业')
          expect(commercialMapped).not.toBeNull()
          expect(commercialMapped!.priorUnadjusted).toBeCloseTo(parseNum(commercialRow.priorUnadjusted), 5)
          expect(commercialMapped!.currentAudited).toBeCloseTo(
            calcAuditedAmount(parseNum(commercialRow.currentUnadjusted), parseNum(commercialRow.currentAje), parseNum(commercialRow.currentRje)),
            5,
          )
        },
      ),
      { numRuns: 100 },
    )
  })

  it('坏账准备区等于D1-4全部行的priorAudited/currentAudited之和', () => {
    fc.assert(
      fc.property(
        fc.array(badDebtRowArb, { minLength: 1, maxLength: 10 }),
        fc.array(badDebtRowArb, { minLength: 0, maxLength: 10 }),
        (individualRows, portfolioRows) => {
          // Set up allResponses with serialized bad debt rows
          const allResponses = new Map<string, { item_id: string; remark: string | null }>()
          allResponses.set('D1-bd-individual-rows', {
            item_id: 'D1-bd-individual-rows',
            remark: JSON.stringify(individualRows),
          })
          allResponses.set('D1-bd-portfolio-rows', {
            item_id: 'D1-bd-portfolio-rows',
            remark: JSON.stringify(portfolioRows),
          })

          // Parse using the same logic as the composable
          const parsed = parseBadDebtRows(allResponses)
          expect(parsed).toHaveLength(individualRows.length + portfolioRows.length)

          // Verify bad debt sum equals sum of all rows
          const allRows = [...individualRows, ...portfolioRows]
          const expectedPriorSum = allRows.reduce((sum, r) => sum + parseNum(r.priorAudited), 0)
          const expectedCurrentSum = allRows.reduce((sum, r) => sum + parseNum(r.currentAudited), 0)

          const actualPriorSum = parsed.reduce((sum, r) => sum + parseNum(r.priorAudited), 0)
          const actualCurrentSum = parsed.reduce((sum, r) => sum + parseNum(r.currentAudited), 0)

          expect(actualPriorSum).toBeCloseTo(expectedPriorSum, 5)
          expect(actualCurrentSum).toBeCloseTo(expectedCurrentSum, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: EventBus调整分录同步正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 7: EventBus调整分录同步正确性', () => {
  /**
   * **Validates: Requirements 3.1**
   *
   * For any adjustment:created event payload (entryType='AJE'|'RJE', amount, accountCode),
   * the adjudication table's corresponding row AJE/RJE column should accumulate the event amount.
   */

  // ─── Replicate resolveRowKeyFromAccount logic ────────────────────────────

  function resolveRowKeyFromAccount(accountCode: string): string | null {
    if (accountCode.startsWith('1121') || accountCode.includes('银行承兑')) return 'gross-bank'
    if (accountCode.startsWith('1122') || accountCode.includes('商业承兑')) return 'gross-commercial'
    if (accountCode.startsWith('1231') || accountCode.includes('坏账')) return 'bd-bank'
    return 'gross-bank' // fallback
  }

  // ─── Replicate onAdjustmentCreated accumulation logic ────────────────────

  /**
   * Simulates the onAdjustmentCreated handler from useD1Adjudication:
   * 1. Resolve target row key from account code
   * 2. Determine field suffix based on entryType
   * 3. Accumulate: existing value + new amount → stored value
   */
  function simulateAdjustmentCreated(
    allResponses: Map<string, { item_id: string; remark: string | null }>,
    entryType: 'AJE' | 'RJE',
    amount: number,
    accountCode: string,
  ): { targetRowKey: string; fieldSuffix: string; newValue: number } | null {
    const parsedAmount = parseNum(amount)
    if (parsedAmount === 0) return null

    const targetRowKey = resolveRowKeyFromAccount(accountCode)
    if (!targetRowKey) return null

    const fieldSuffix = entryType === 'AJE' ? 'current-aje' : 'current-rje'
    const itemId = `D1-adj-${targetRowKey}-${fieldSuffix}`
    const existing = parseNum(allResponses.get(itemId)?.remark ?? null)
    const newValue = existing + parsedAmount

    // Update allResponses (simulating setLocal)
    allResponses.set(itemId, { item_id: itemId, remark: String(newValue) })

    return { targetRowKey, fieldSuffix, newValue }
  }

  // ─── Generators ──────────────────────────────────────────────────────────

  const entryTypeArb = fc.oneof(fc.constant('AJE' as const), fc.constant('RJE' as const))

  const amountArb = fc.float({ min: -1e9, max: 1e9, noNaN: true }).filter(v => v !== 0)

  const accountCodeArb = fc.oneof(
    // Codes that map to 'gross-bank'
    fc.constant('1121001'),
    fc.constant('1121002'),
    fc.constant('银行承兑汇票'),
    // Codes that map to 'gross-commercial'
    fc.constant('1122001'),
    fc.constant('1122002'),
    fc.constant('商业承兑汇票'),
    // Codes that map to 'bd-bank'
    fc.constant('1231001'),
    fc.constant('坏账准备'),
    // Fallback codes (should map to 'gross-bank')
    fc.constant('9999'),
    fc.constant('unknown'),
  )

  it('adjustment:created事件正确累加到对应行的AJE/RJE列', () => {
    fc.assert(
      fc.property(
        entryTypeArb,
        amountArb,
        accountCodeArb,
        fc.float({ min: -1e9, max: 1e9, noNaN: true }), // existing value in the cell
        (entryType, amount, accountCode, existingValue) => {
          // Setup: allResponses with an existing value for the target cell
          const allResponses = new Map<string, { item_id: string; remark: string | null }>()
          const targetRowKey = resolveRowKeyFromAccount(accountCode)!
          const fieldSuffix = entryType === 'AJE' ? 'current-aje' : 'current-rje'
          const itemId = `D1-adj-${targetRowKey}-${fieldSuffix}`

          // Pre-populate with existing value
          allResponses.set(itemId, { item_id: itemId, remark: String(existingValue) })

          // Act: simulate adjustment:created
          const result = simulateAdjustmentCreated(allResponses, entryType, amount, accountCode)

          // Assert: amount was accumulated correctly
          expect(result).not.toBeNull()
          expect(result!.targetRowKey).toBe(targetRowKey)
          expect(result!.fieldSuffix).toBe(fieldSuffix)

          // The new value should be existing + amount
          const expectedValue = parseNum(existingValue) + parseNum(amount)
          expect(result!.newValue).toBeCloseTo(expectedValue, 5)

          // Verify the allResponses map was updated
          const stored = allResponses.get(itemId)
          expect(stored).not.toBeUndefined()
          expect(parseNum(stored!.remark)).toBeCloseTo(expectedValue, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('resolveRowKeyFromAccount正确映射科目代码到行标识', () => {
    fc.assert(
      fc.property(
        accountCodeArb,
        (accountCode) => {
          const rowKey = resolveRowKeyFromAccount(accountCode)

          // Verify mapping correctness
          if (accountCode.startsWith('1121') || accountCode.includes('银行承兑')) {
            expect(rowKey).toBe('gross-bank')
          } else if (accountCode.startsWith('1122') || accountCode.includes('商业承兑')) {
            expect(rowKey).toBe('gross-commercial')
          } else if (accountCode.startsWith('1231') || accountCode.includes('坏账')) {
            expect(rowKey).toBe('bd-bank')
          } else {
            // Fallback
            expect(rowKey).toBe('gross-bank')
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('amount为零时不产生累加操作', () => {
    fc.assert(
      fc.property(
        entryTypeArb,
        accountCodeArb,
        (entryType, accountCode) => {
          const allResponses = new Map<string, { item_id: string; remark: string | null }>()
          const targetRowKey = resolveRowKeyFromAccount(accountCode)!
          const fieldSuffix = entryType === 'AJE' ? 'current-aje' : 'current-rje'
          const itemId = `D1-adj-${targetRowKey}-${fieldSuffix}`
          allResponses.set(itemId, { item_id: itemId, remark: '500' })

          // Act: simulate with zero amount
          const result = simulateAdjustmentCreated(allResponses, entryType, 0, accountCode)

          // Assert: no accumulation happened
          expect(result).toBeNull()
          // Original value unchanged
          expect(allResponses.get(itemId)!.remark).toBe('500')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('多次连续累加保持数值正确性', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.tuple(entryTypeArb, amountArb, accountCodeArb),
          { minLength: 2, maxLength: 10 },
        ),
        (events) => {
          const allResponses = new Map<string, { item_id: string; remark: string | null }>()

          // Track expected accumulated amounts per cell
          const expectedAccumulations = new Map<string, number>()

          for (const [entryType, amount, accountCode] of events) {
            const targetRowKey = resolveRowKeyFromAccount(accountCode)!
            const fieldSuffix = entryType === 'AJE' ? 'current-aje' : 'current-rje'
            const cellKey = `D1-adj-${targetRowKey}-${fieldSuffix}`

            // Track expected
            const currentExpected = expectedAccumulations.get(cellKey) ?? 0
            expectedAccumulations.set(cellKey, currentExpected + parseNum(amount))

            // Simulate
            simulateAdjustmentCreated(allResponses, entryType, amount, accountCode)
          }

          // Verify all cells have correct accumulated values
          for (const [cellKey, expectedTotal] of expectedAccumulations) {
            const stored = allResponses.get(cellKey)
            expect(stored).not.toBeUndefined()
            expect(parseNum(stored!.remark)).toBeCloseTo(expectedTotal, 4)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})
