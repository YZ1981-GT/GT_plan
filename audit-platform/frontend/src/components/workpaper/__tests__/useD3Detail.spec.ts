/**
 * useD3Detail PBT 测试
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 覆盖 D3-2 明细表核心逻辑：行公式链、动态行添加、关联方匹配、搜索过滤、函证标记。
 *
 * 测试纯函数逻辑（recalcRowFormulas, createEmptyRow, matchRelatedPartyPure,
 * filterRowsBySearch, applyConfirmationCompleted），不依赖 Vue 响应式。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcPriorAudited,
  calcEndBalance,
  calcEndUnadjusted,
  calcEndAudited,
} from '../composables/useD3FormulaEngine'
import {
  recalcRowFormulas,
  createEmptyRow,
  matchRelatedPartyPure,
  filterRowsBySearch,
  applyConfirmationCompleted,
  type DetailRow,
} from '../composables/useD3Detail'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 金额生成器：[-1e9, 1e9] 有限浮点数 */
const amountArb = fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })

/** 非负金额生成器 */
const nonNegAmountArb = fc.float({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true })

/** 4种款项性质 */
const NATURE_OPTIONS = [
  '预收销售固定资产款',
  '预收销售土地使用权款',
  '合同不成立时已收取的对价',
  '其他',
] as const

/** DetailRow 生成器 */
const detailRowArb: fc.Arbitrary<DetailRow> = fc.record({
  rowId: fc.uuid(),
  customerName: fc.string({ minLength: 0, maxLength: 30 }),
  companyCode: fc.string({ minLength: 0, maxLength: 10 }),
  nature: fc.constantFrom(...NATURE_OPTIONS),
  relationType: fc.constantFrom('非关联方', '实际控制人', '控股股东', '联营', '其他关联方'),
  priorUnadjusted: amountArb,
  priorAdjustment: amountArb,
  priorReclass: amountArb,
  priorAudited: amountArb,
  agingPrior: fc.record({
    within1: nonNegAmountArb,
    y1to2: nonNegAmountArb,
    y2to3: nonNegAmountArb,
    over3: nonNegAmountArb,
  }),
  debit: nonNegAmountArb,
  credit: nonNegAmountArb,
  endBalance: amountArb,
  entityReclass: amountArb,
  endUnadjusted: amountArb,
  endAje: amountArb,
  endRje: amountArb,
  endAudited: amountArb,
  agingAudited: fc.record({
    within1: nonNegAmountArb,
    y1to2: nonNegAmountArb,
    y2to3: nonNegAmountArb,
    over3: nonNegAmountArb,
  }),
  isConfirmed: fc.constantFrom('', 'Y', 'N'),
  postPeriodSettlement: nonNegAmountArb,
  remark: fc.string({ minLength: 0, maxLength: 20 }),
})

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD3Detail - Property-Based Tests', () => {
  /**
   * **Feature: d3-prepaid-accounts, Property 5: 明细表D3-2行内公式链正确性**
   *
   * For any 明细行输入值组合，以下公式链必须成立：
   * - 期初审定余额 H = E + F + G
   * - 期末余额 O = H + N - M（贷方科目：期初审定+贷方-借方）
   * - 期末未审余额 Q = O + P
   * - 期末审定数 T = Q + R + S
   *
   * **Validates: Requirements 4.4, 10.3**
   */
  describe('Property 5: D3-2行公式链正确性', () => {
    it('H=E+F+G; O=H+N-M; Q=O+P; T=Q+R+S', () => {
      fc.assert(
        fc.property(
          amountArb, // E: priorUnadjusted
          amountArb, // F: priorAdjustment
          amountArb, // G: priorReclass
          amountArb, // M: debit
          amountArb, // N: credit
          amountArb, // P: entityReclass
          amountArb, // R: endAje
          amountArb, // S: endRje
          (E, F, G, M, N, P, R, S) => {
            // Create a row with these input values
            const row: DetailRow = {
              ...createEmptyRow(),
              priorUnadjusted: E,
              priorAdjustment: F,
              priorReclass: G,
              debit: M,
              credit: N,
              entityReclass: P,
              endAje: R,
              endRje: S,
            }

            // Recalculate formula chain
            const result = recalcRowFormulas(row)

            // Assert formula chain
            const expectedH = calcPriorAudited(E, F, G)
            const expectedO = calcEndBalance(expectedH, N, M)
            const expectedQ = calcEndUnadjusted(expectedO, P)
            const expectedT = calcEndAudited(expectedQ, R, S)

            // H = E + F + G
            expect(result.priorAudited).toBeCloseTo(expectedH, 4)
            expect(result.priorAudited).toBeCloseTo(E + F + G, 4)

            // O = H + N - M (贷方科目)
            expect(result.endBalance).toBeCloseTo(expectedO, 4)
            expect(result.endBalance).toBeCloseTo(expectedH + N - M, 4)

            // Q = O + P
            expect(result.endUnadjusted).toBeCloseTo(expectedQ, 4)
            expect(result.endUnadjusted).toBeCloseTo(expectedO + P, 4)

            // T = Q + R + S
            expect(result.endAudited).toBeCloseTo(expectedT, 4)
            expect(result.endAudited).toBeCloseTo(expectedQ + R + S, 4)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d3-prepaid-accounts, Property 10: 动态行添加保持结构不变量**
   *
   * For any 当前行列表（长度N），执行addRow()后行列表长度应为N+1，
   * 且新行所有数值字段为0。
   *
   * **Validates: Requirements 4.6, 7.2, 9.3, 10.5, 11.4**
   */
  describe('Property 10: 动态行添加保持结构不变量', () => {
    it('addRow后length=N+1；新行数值全0', () => {
      fc.assert(
        fc.property(
          fc.array(detailRowArb, { minLength: 0, maxLength: 20 }),
          (existingRows) => {
            const N = existingRows.length

            // Simulate addRow: append createEmptyRow
            const newRow = createEmptyRow()
            const updatedRows = [...existingRows, newRow]

            // Length invariant
            expect(updatedRows.length).toBe(N + 1)

            // New row has all numeric fields = 0
            const added = updatedRows[updatedRows.length - 1]
            expect(added.priorUnadjusted).toBe(0)
            expect(added.priorAdjustment).toBe(0)
            expect(added.priorReclass).toBe(0)
            expect(added.priorAudited).toBe(0)
            expect(added.debit).toBe(0)
            expect(added.credit).toBe(0)
            expect(added.endBalance).toBe(0)
            expect(added.entityReclass).toBe(0)
            expect(added.endUnadjusted).toBe(0)
            expect(added.endAje).toBe(0)
            expect(added.endRje).toBe(0)
            expect(added.endAudited).toBe(0)
            expect(added.postPeriodSettlement).toBe(0)
            expect(added.agingPrior.within1).toBe(0)
            expect(added.agingPrior.y1to2).toBe(0)
            expect(added.agingPrior.y2to3).toBe(0)
            expect(added.agingPrior.over3).toBe(0)
            expect(added.agingAudited.within1).toBe(0)
            expect(added.agingAudited.y1to2).toBe(0)
            expect(added.agingAudited.y2to3).toBe(0)
            expect(added.agingAudited.over3).toBe(0)

            // New row has default non-numeric fields
            expect(added.customerName).toBe('')
            expect(added.nature).toBe('')
            expect(added.relationType).toBe('非关联方')
            expect(added.isConfirmed).toBe('')
            expect(added.remark).toBe('')

            // New row has a rowId
            expect(added.rowId).toBeTruthy()
            expect(typeof added.rowId).toBe('string')
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d3-prepaid-accounts, Property 11: 关联方自动匹配正确性**
   *
   * For any 客户名称字符串和关联方名单列表，若客户名称包含列表中某项
   * （或反向包含），则matchRelatedParty返回对应关联关系；否则返回'非关联方'。
   *
   * **Validates: Requirements 4.7, 10.5**
   */
  describe('Property 11: 关联方自动匹配正确性', () => {
    it('名称包含列表项→返回关联关系；否则→非关联方', () => {
      fc.assert(
        fc.property(
          fc.string({ minLength: 1, maxLength: 20 }),
          fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 0, maxLength: 10 }),
          (customerName, parties) => {
            const result = matchRelatedPartyPure(customerName, parties)

            const nameLower = customerName.toLowerCase()
            const hasMatch = parties.some(party => {
              if (!party) return false
              const partyLower = party.toLowerCase()
              return nameLower.includes(partyLower) || partyLower.includes(nameLower)
            })

            if (hasMatch) {
              // Should return a matched party name (not '非关联方')
              expect(result).not.toBe('非关联方')
              // The result should be one of the parties
              expect(parties).toContain(result)
            } else {
              // Should return '非关联方'
              expect(result).toBe('非关联方')
            }
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d3-prepaid-accounts, Property 12: 搜索过滤正确性**
   *
   * For any 搜索关键字q和明细行列表，filteredRows中每行的customerName应包含q
   * （大小写不敏感），且所有匹配行都应出现在结果中（无遗漏无多余）。
   *
   * **Validates: Requirements 4.11**
   */
  describe('Property 12: 搜索过滤正确性', () => {
    it('filteredRows每行customerName包含q(不敏感)；无遗漏无多余', () => {
      fc.assert(
        fc.property(
          fc.string({ minLength: 0, maxLength: 10 }),
          fc.array(detailRowArb, { minLength: 0, maxLength: 20 }),
          (query, rows) => {
            const result = filterRowsBySearch(rows, query)

            if (!query) {
              // Empty query returns all rows
              expect(result.length).toBe(rows.length)
              return
            }

            const q = query.toLowerCase()

            // Every result row's customerName contains query (case-insensitive)
            for (const row of result) {
              expect(row.customerName.toLowerCase()).toContain(q)
            }

            // No matching rows are missing (completeness)
            const expected = rows.filter(r => r.customerName.toLowerCase().includes(q))
            expect(result.length).toBe(expected.length)

            // Verify exact match of rowIds
            const resultIds = new Set(result.map(r => r.rowId))
            for (const exp of expected) {
              expect(resultIds.has(exp.rowId)).toBe(true)
            }
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d3-prepaid-accounts, Property 13: 函证完成事件标记正确性**
   *
   * For any confirmation:completed事件payload（含customerName），
   * 明细表中匹配该客户名称的行的"是否发函"列应被标记为"Y"，
   * 不匹配行保持不变。
   *
   * **Validates: Requirements 5.4, 18.4**
   */
  describe('Property 13: 函证完成事件标记正确性', () => {
    it('匹配行isConfirmed=Y；不匹配行不变', () => {
      fc.assert(
        fc.property(
          fc.string({ minLength: 1, maxLength: 20 }),
          fc.array(detailRowArb, { minLength: 0, maxLength: 20 }),
          (customerName, rows) => {
            // Record original isConfirmed values
            const originalConfirmed = rows.map(r => r.isConfirmed)

            const result = applyConfirmationCompleted(rows, customerName)

            // Same length
            expect(result.length).toBe(rows.length)

            const nameLower = customerName.toLowerCase()

            for (let i = 0; i < result.length; i++) {
              if (result[i].customerName.toLowerCase() === nameLower) {
                // Matching row should be marked 'Y'
                expect(result[i].isConfirmed).toBe('Y')
              } else {
                // Non-matching row should retain original value
                expect(result[i].isConfirmed).toBe(originalConfirmed[i])
              }
            }
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})
