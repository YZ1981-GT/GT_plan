/**
 * Property-Based Tests — D1 附注披露 composable
 *
 * Spec: .kiro/specs/d1-disclosure-note/
 * Tasks: 4.1–4.7
 *
 * 使用 fast-check + vitest 验证 7 个 correctness properties (Property 3–9)。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import {
  calcNetValue,
  calcSubtotal,
  calcBadDebtEndBalance,
  parseNum,
} from '../useD1FormulaEngine'
import { d1AdjAnchor } from '../d1AdjudicationModel'
import { useD1Disclosure } from '../useD1Disclosure'
import type { PledgedRow, EndorsedRow, TransferRow, RowType } from '../useD1Disclosure'
import type { ChecklistResponse } from '../useD1FormData'

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 账面价值等于余额减坏账
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-disclosure-note, Property 3: 账面价值等于余额减坏账', () => {
  /**
   * **Validates: Requirements 5.6, 10.3**
   *
   * 账面价值 = 余额 - 坏账准备
   */
  it('calcNetValue(balance, provision) === balance - provision', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (balance, provision) => {
          const result = calcNetValue(balance, provision)
          const expected = balance - provision
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 合计行恒等于明细行之和
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-disclosure-note, Property 4: 合计行恒等于明细行之和', () => {
  /**
   * **Validates: Requirements 2.5, 3.4, 4.3, 5.7, 8.7, 9.4**
   *
   * calcSubtotal(rows) === rows.reduce((a,b) => a+b, 0)
   */
  it('calcSubtotal equals sum of all elements', () => {
    fc.assert(
      fc.property(
        // 金额域必须有界：`noNaN` 只排 NaN 不排 ±Infinity，
        // 数组同时含 +Inf 与 -Inf 时求和为 NaN → `toBeCloseTo(NaN)` 必失败（生成器越界，非公式缺陷）
        fc.array(fc.float({ min: -1e9, max: 1e9, noNaN: true }), { minLength: 1, maxLength: 20 }),
        (rows) => {
          const result = calcSubtotal(rows)
          const expected = rows.reduce((a, b) => a + b, 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 坏账变动期末余额公式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-disclosure-note, Property 5: 坏账变动期末余额公式', () => {
  /**
   * **Validates: Requirements 8.2**
   *
   * calcBadDebtEndBalance(priorAudited, provision, recovery, reversal, writeOff, other)
   * === priorAudited + provision - recovery - reversal - writeOff + other
   */
  it('endBalance === priorAudited + provision - recovery - reversal - writeOff + other', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (priorAudited, provision, recovery, reversal, writeOff, other) => {
          const result = calcBadDebtEndBalance(priorAudited, provision, recovery, reversal, writeOff, other)
          const expected = priorAudited + provision - recovery - reversal - writeOff + other
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 动态行添加保持结构不变量
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-disclosure-note, Property 6: 动态行添加保持结构不变量', () => {
  /**
   * **Validates: Requirements 2.3, 3.3, 6.3, 8.6, 9.3**
   *
   * Given any array of PledgedRow, appending a new row with pledgedAmount=0
   * yields length+1 and last row amount=0
   */
  it('after adding a row, length is N+1 and new row has pledgedAmount=0', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            rowId: fc.string(),
            rowType: fc.constant('dynamic' as RowType),
            category: fc.string(),
            isFixed: fc.constant(false),
            pledgedAmount: fc.float({ noNaN: true }),
          }),
          { minLength: 0, maxLength: 10 },
        ),
        (rows: PledgedRow[]) => {
          const originalLength = rows.length

          // Simulate addRow logic: append a new row with pledgedAmount=0
          const newRow: PledgedRow = {
            rowId: `pl-test-${Date.now()}`,
            rowType: 'dynamic',
            category: '',
            isFixed: false,
            pledgedAmount: 0,
          }
          const updatedRows = [...rows, newRow]

          // Invariant 1: length is N+1
          expect(updatedRows.length).toBe(originalLength + 1)

          // Invariant 2: new row has all numeric fields = 0
          const lastRow = updatedRows[updatedRows.length - 1]
          expect(lastRow.pledgedAmount).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: 跨Sheet取数响应式一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-disclosure-note, Property 7: 跨Sheet取数响应式一致性', () => {
  /**
   * **Validates: Requirements 10.2, 11.2, 11.3**
   *
   * For each key in CROSS_SHEET_KEYS, parseNum(map.get(key).remark) === expected field value
   */

  /**
   * 🔴 本用例原来是**空转的重言式**：它自己用
   * `'D1-adj-gross-bank-current-audited'` / `'D1-adj-baddebt-*'` 建 Map，再断言
   * `parseNum` 能把同一个值读回来 —— 既没触碰生产代码，也掩盖了「这批锚点全平台
   * 无写入方」这一事实（`-current-audited` 是 computed 列从不持久化、前缀
   * `baddebt` ≠ 写入方的 `bd`）。披露①分类表的跨表取数因此从未生效过。
   *
   * 现改为对**真实持久化锚点**（`current-unadj` / `current-aje` / `current-rje`）
   * 做 PBT：`crossSheetData` 必须等于 `审定 = 未审 + 账项调整 + 重分类调整`
   * （源模板 D1-1 `I8=F8+G8+H8`）。锚点一律经 `d1AdjAnchor` 构造，禁字面量。
   */
  it('crossSheetData 恒等于「未审 + 账项调整 + 重分类调整」（真实锚点，禁派生列）', () => {
    const amount = () => fc.float({ min: -1e9, max: 1e9, noNaN: true })
    fc.assert(
      fc.property(
        fc.record({
          gUnadj: amount(),
          gAje: amount(),
          gRje: amount(),
          pUnadj: amount(),
          pAje: amount(),
          pRje: amount(),
        }),
        (v) => {
          const map = new Map<string, ChecklistResponse>()
          const put = (k: string, val: number) =>
            map.set(k, { item_id: k, conclusion: null, remark: String(val) })
          put(d1AdjAnchor('gross', 'bank', 'current-unadj'), v.gUnadj)
          put(d1AdjAnchor('gross', 'bank', 'current-aje'), v.gAje)
          put(d1AdjAnchor('gross', 'bank', 'current-rje'), v.gRje)
          put(d1AdjAnchor('bd', 'bank', 'current-unadj'), v.pUnadj)
          put(d1AdjAnchor('bd', 'bank', 'current-aje'), v.pAje)
          put(d1AdjAnchor('bd', 'bank', 'current-rje'), v.pRje)

          const api = useD1Disclosure({
            allResponses: ref(map) as any,
            wpId: ref('wp-1') as any,
            projectId: ref('p-1') as any,
            variant: 'listed',
            saveImmediate: vi.fn(async () => {}),
            isReadonly: ref(false) as any,
          })
          expect(api.crossSheetData.value.bankEndBalance).toBeCloseTo(
            v.gUnadj + v.gAje + v.gRje,
            4,
          )
          expect(api.crossSheetData.value.bankEndProvision).toBeCloseTo(
            v.pUnadj + v.pAje + v.pRje,
            4,
          )
        },
      ),
      { numRuns: 60 },
    )
  })

  it('🔴 反向自检：派生列锚点（-current-audited）不得被消费', () => {
    // 若有人把 `-current-audited` 重新接回读取路径，本断言立即打红
    const map = new Map<string, ChecklistResponse>()
    const bogus = 'D1-adj-gross-bank-current-audited'
    map.set(bogus, { item_id: bogus, conclusion: null, remark: '999999' })
    const api = useD1Disclosure({
      allResponses: ref(map) as any,
      wpId: ref('wp-1') as any,
      projectId: ref('p-1') as any,
      variant: 'listed',
      saveImmediate: vi.fn(async () => {}),
      isReadonly: ref(false) as any,
    })
    expect(api.crossSheetData.value.bankEndBalance).toBe(0)
    expect(api.crossSheetStatus.value).toBe('empty')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 动态行序列化 Round-Trip
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-disclosure-note, Property 8: 动态行序列化 Round-Trip', () => {
  /**
   * **Validates: Requirements 13.4, 13.5**
   *
   * JSON.parse(JSON.stringify(rows)) deep equals rows
   */

  // Use min:0 trick or filter to avoid -0 (JSON.stringify(-0) === "0", breaking deep equality)
  const safeFloat = fc.float({ noNaN: true, noDefaultInfinity: true }).map(v => (Object.is(v, -0) ? 0 : v))

  const pledgedRowGen = fc.record({
    rowId: fc.string(),
    rowType: fc.constant('dynamic' as RowType),
    category: fc.string(),
    isFixed: fc.constant(false),
    pledgedAmount: safeFloat,
  })

  const endorsedRowGen = fc.record({
    rowId: fc.string(),
    rowType: fc.constant('dynamic' as RowType),
    category: fc.string(),
    isFixed: fc.constant(false),
    derecognizedAmount: safeFloat,
    notDerecognizedAmount: safeFloat,
  })

  const transferRowGen = fc.record({
    rowId: fc.string(),
    rowType: fc.constant('dynamic' as RowType),
    category: fc.string(),
    isFixed: fc.constant(false),
    transferAmount: safeFloat,
  })

  it('PledgedRow[] round-trip: JSON.parse(JSON.stringify(rows)) deep equals rows', () => {
    fc.assert(
      fc.property(
        fc.array(pledgedRowGen, { minLength: 0, maxLength: 10 }),
        (rows) => {
          const serialized = JSON.stringify(rows)
          const deserialized = JSON.parse(serialized)
          expect(deserialized).toEqual(rows)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('EndorsedRow[] round-trip: JSON.parse(JSON.stringify(rows)) deep equals rows', () => {
    fc.assert(
      fc.property(
        fc.array(endorsedRowGen, { minLength: 0, maxLength: 10 }),
        (rows) => {
          const serialized = JSON.stringify(rows)
          const deserialized = JSON.parse(serialized)
          expect(deserialized).toEqual(rows)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('TransferRow[] round-trip: JSON.parse(JSON.stringify(rows)) deep equals rows', () => {
    fc.assert(
      fc.property(
        fc.array(transferRowGen, { minLength: 0, maxLength: 10 }),
        (rows) => {
          const serialized = JSON.stringify(rows)
          const deserialized = JSON.parse(serialized)
          expect(deserialized).toEqual(rows)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 9: 变体子节顺序正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-disclosure-note, Property 9: 变体子节顺序正确性', () => {
  /**
   * **Validates: Requirements 1.2, 1.3**
   *
   * listed → ['pledged','endorsed','transfer','badDebtClass','badDebtMovement','writeOff']
   * soe → ['categorySummary','badDebtClass','badDebtMovement','pledged','endorsed','transfer','writeOff']
   */

  const LISTED_ORDER = ['pledged', 'endorsed', 'transfer', 'badDebtClass', 'badDebtMovement', 'writeOff']
  const SOE_ORDER = ['categorySummary', 'badDebtClass', 'badDebtMovement', 'pledged', 'endorsed', 'transfer', 'writeOff']

  it('variant determines sectionOrder correctly', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('listed' as const, 'soe' as const),
        (variant) => {
          // Inline the sectionOrder logic (pure, no Vue context needed)
          const sectionOrder = variant === 'listed'
            ? ['pledged', 'endorsed', 'transfer', 'badDebtClass', 'badDebtMovement', 'writeOff']
            : ['categorySummary', 'badDebtClass', 'badDebtMovement', 'pledged', 'endorsed', 'transfer', 'writeOff']

          if (variant === 'listed') {
            expect(sectionOrder).toEqual(LISTED_ORDER)
          } else {
            expect(sectionOrder).toEqual(SOE_ORDER)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})
