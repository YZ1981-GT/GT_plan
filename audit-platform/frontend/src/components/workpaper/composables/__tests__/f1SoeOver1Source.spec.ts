/**
 * 国企披露②表「账龄超过1年的大额预付款项」数据源保真守卫。
 *
 * 源模板逐格实证（`附注披露信息(国企)` R18，见后端守卫
 * `backend/tests/test_f1_source_template_facts.py`）—— 本表四列全部指向 F1-5：
 *
 * | ②表列 | F1-5 列 |
 * |---|---|
 * | 债务单位 | A 债务人名称 |
 * | 期末余额 | **J 审定余额** = B 期末余额 − I 计提坏账准备 |
 * | 账龄 | C 账龄 |
 * | 未结算的原因 | E 未偿还或未结转的原因 |
 *
 * 「债权单位」= `RIGHT($A$3,…)` 即被审计单位名称。
 *
 * spec: .kiro/specs/f1-extraction-chain-and-disclosure-source-fidelity/ (Task 3.5)
 * Properties 1~4
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import fc from 'fast-check'
import {
  buildSoeOver1Rows,
  useF1DisclosureSoe,
  type F1CrossLongTermRow,
  type F1LongTermSourceRow,
  type F1SoeOver1Row,
} from '../useF1DisclosureSoe'
import { F1_SOE_SUBTABLE, buildF1SoeSubTableData } from '../f1DisclosureSyncPayload'
import type { ChecklistResponse } from '../useF1FormData'

const CLIENT = '重庆和平药房连锁有限责任公司'

const LT: F1LongTermSourceRow[] = [
  { customerName: '供应商甲', endBalance: 1000, badDebtProvision: 150, aging: '1至2年', reason: '货未到' },
  { customerName: '供应商乙', endBalance: 500, badDebtProvision: 0, aging: '3年以上', reason: '' },
]

const CS: F1CrossLongTermRow[] = [
  { customerName: '供应商丙', endAudited: 800, agingDescription: '1至2年、2至3年' },
]

function call(over: Partial<Parameters<typeof buildSoeOver1Rows>[0]> = {}) {
  return buildSoeOver1Rows({
    longTermSheetRows: [],
    crossSheetRows: [],
    dynamicRows: [],
    metaMap: {},
    defaultCreditorUnit: CLIENT,
    ...over,
  })
}

function manualRow(over: Partial<F1SoeOver1Row> = {}): F1SoeOver1Row {
  return {
    rowId: 'm1',
    creditorUnit: '',
    debtorUnit: '供应商丁',
    endBalance: 42,
    agingLabel: '1至2年',
    reason: '手工原因',
    fromCrossSheet: false,
    source: 'manual',
    ...over,
  }
}

describe('buildSoeOver1Rows — Property 1: F1-5 优先且回退零回归', () => {
  it('F1-5 有行时用 F1-5，来源标 f1-5', () => {
    const rows = call({ longTermSheetRows: LT, crossSheetRows: CS })
    expect(rows).toHaveLength(2)
    expect(rows.map((r) => r.debtorUnit)).toEqual(['供应商甲', '供应商乙'])
    expect(rows.every((r) => r.source === 'f1-5')).toBe(true)
  })

  it('F1-5 为空时回退 F1-2 派生行，来源标 f1-2 且 rowId 与改造前一致', () => {
    const rows = call({ longTermSheetRows: [], crossSheetRows: CS })
    expect(rows).toHaveLength(1)
    expect(rows[0].source).toBe('f1-2')
    expect(rows[0].rowId).toBe('cs-lt-供应商丙')
    expect(rows[0].endBalance).toBe(800)
    expect(rows[0].agingLabel).toBe('1至2年、2至3年')
  })

  it('F1-5 只有空名行时视为无效 → 仍回退 F1-2', () => {
    const rows = call({
      longTermSheetRows: [{ customerName: '  ', endBalance: 9, badDebtProvision: 0, aging: '', reason: '' }],
      crossSheetRows: CS,
    })
    expect(rows).toHaveLength(1)
    expect(rows[0].source).toBe('f1-2')
  })

  it('手工新增行始终附加在派生行之后', () => {
    const rows = call({ longTermSheetRows: LT, dynamicRows: [manualRow()] })
    expect(rows.map((r) => r.source)).toEqual(['f1-5', 'f1-5', 'manual'])
  })

  it('两个源都空时输出空数组（不造占位行）', () => {
    expect(call()).toEqual([])
  })
})

describe('buildSoeOver1Rows — Property 4: 期末余额取审定口径', () => {
  it('F1-5 行的期末余额 = 期末余额 − 计提坏账准备（源 J 列）', () => {
    const rows = call({ longTermSheetRows: LT })
    expect(rows[0].endBalance).toBe(850) // 1000 − 150
    expect(rows[1].endBalance).toBe(500) // 500 − 0
  })

  it('不信任持久化的 auditedBalance，按定义现算', () => {
    const rows = buildSoeOver1Rows({
      longTermSheetRows: [
        // 故意塞一个与 B−I 矛盾的 auditedBalance
        { customerName: 'X', endBalance: 100, badDebtProvision: 30, aging: '', reason: '',
          auditedBalance: 999 } as unknown as F1LongTermSourceRow,
      ],
      crossSheetRows: [],
      dynamicRows: [],
      metaMap: {},
      defaultCreditorUnit: CLIENT,
    })
    expect(rows[0].endBalance).toBe(70)
  })

  it('PBT：期末余额恒等于 B − I（金额域有界）', () => {
    const money = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
    fc.assert(
      fc.property(money, money, (endBalance, badDebtProvision) => {
        const rows = buildSoeOver1Rows({
          longTermSheetRows: [{ customerName: 'A', endBalance, badDebtProvision, aging: '', reason: '' }],
          crossSheetRows: [],
          dynamicRows: [],
          metaMap: {},
          defaultCreditorUnit: CLIENT,
        })
        expect(rows[0].endBalance).toBeCloseTo(endBalance - badDebtProvision, 6)
      }),
      { numRuns: 20 },
    )
  })
})

describe('buildSoeOver1Rows — Property 2: 手工覆盖单调优先', () => {
  it('meta 覆盖账龄与原因', () => {
    const rows = call({
      longTermSheetRows: LT,
      metaMap: { 供应商甲: { agingLabel: '2至3年', reason: '合同变更' } },
    })
    expect(rows[0].agingLabel).toBe('2至3年')
    expect(rows[0].reason).toBe('合同变更')
    // 未覆盖的行保持 F1-5 值
    expect(rows[1].agingLabel).toBe('3年以上')
  })

  it('F1-5 的 reason 直接作为②表原因（不再要求重复录入）', () => {
    const rows = call({ longTermSheetRows: LT })
    expect(rows[0].reason).toBe('货未到')
  })

  it('清空覆盖后回落到 F1-5 值', () => {
    const rows = call({
      longTermSheetRows: LT,
      metaMap: { 供应商甲: { agingLabel: '', reason: '   ' } },
    })
    expect(rows[0].agingLabel).toBe('1至2年')
    expect(rows[0].reason).toBe('货未到')
  })

  it('账龄三层缺省：meta > F1-5 > 「1年以上」', () => {
    const rows = call({
      longTermSheetRows: [{ customerName: 'A', endBalance: 1, badDebtProvision: 0, aging: '', reason: '' }],
    })
    expect(rows[0].agingLabel).toBe('1年以上')
  })

  it('PBT：非空 meta.reason 恒胜出', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 12 }).filter((s) => s.trim() !== ''),
        fc.string({ maxLength: 12 }),
        (metaReason, srcReason) => {
          const rows = buildSoeOver1Rows({
            longTermSheetRows: [
              { customerName: 'A', endBalance: 1, badDebtProvision: 0, aging: '', reason: srcReason },
            ],
            crossSheetRows: [],
            dynamicRows: [],
            metaMap: { A: { reason: metaReason } },
            defaultCreditorUnit: CLIENT,
          })
          expect(rows[0].reason).toBe(metaReason.trim())
        },
      ),
      { numRuns: 20 },
    )
  })
})

describe('buildSoeOver1Rows — Property 3: 债权单位永不为空', () => {
  it('缺省取被审计单位名称', () => {
    const rows = call({ longTermSheetRows: LT, dynamicRows: [manualRow()] })
    expect(rows.every((r) => r.creditorUnit === CLIENT)).toBe(true)
  })

  it('meta 覆盖优先；手工行自身值优先', () => {
    const rows = call({
      longTermSheetRows: LT,
      dynamicRows: [manualRow({ creditorUnit: '另一主体' })],
      metaMap: { 供应商甲: { creditorUnit: '子公司甲' } },
    })
    expect(rows[0].creditorUnit).toBe('子公司甲')
    expect(rows[1].creditorUnit).toBe(CLIENT)
    expect(rows[2].creditorUnit).toBe('另一主体')
  })

  it('缺省值为空时不臆造名称（由 F7-9 完整性校验提示）', () => {
    const rows = buildSoeOver1Rows({
      longTermSheetRows: LT,
      crossSheetRows: [],
      dynamicRows: [],
      metaMap: {},
      defaultCreditorUnit: '',
    })
    expect(rows.every((r) => r.creditorUnit === '')).toBe(true)
  })

  it('PBT：defaultCreditorUnit 非空 → 每行 creditorUnit 非空', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 20 }).filter((s) => s.trim() !== ''),
        fc.array(
          fc.record({
            customerName: fc.string({ minLength: 1, maxLength: 8 }).filter((s) => s.trim() !== ''),
            endBalance: fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
            badDebtProvision: fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
            aging: fc.constant(''),
            reason: fc.constant(''),
          }),
          { maxLength: 5 },
        ),
        (client, lt) => {
          const rows = buildSoeOver1Rows({
            longTermSheetRows: lt,
            crossSheetRows: [],
            dynamicRows: [],
            metaMap: {},
            defaultCreditorUnit: client,
          })
          expect(rows.every((r) => r.creditorUnit.trim() !== '')).toBe(true)
        },
      ),
      { numRuns: 20 },
    )
  })
})

describe('useF1DisclosureSoe — F1-5 接线与载荷', () => {
  beforeEach(() => {
    vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true)
    vi.spyOn(window, 'addEventListener').mockImplementation(() => undefined)
    vi.spyOn(window, 'removeEventListener').mockImplementation(() => undefined)
  })

  function makeCrossSheet(longTerm: any[] = []) {
    const aging = { within1: 2000, y1to2: 1000, prior_within1: 0, prior_y1to2: 0 }
    return {
      agingAggregation: computed(() => aging),
      agingSegments: computed(() => [
        { key: 'within1', label: '1年以内', dayFrom: 0, dayTo: 365 },
        { key: 'y1to2', label: '1-2年', dayFrom: 366, dayTo: 730 },
      ]),
      longTermRows: computed(() => longTerm),
      natureAggregation: computed(() => ({})),
      adjudicationForDisclosure: computed(() => ({
        natureAggregation: {}, agingAggregation: aging, longTermRows: longTerm,
      })),
    } as any
  }

  function build(ltRows: unknown[] | null, clientName = CLIENT) {
    const map = new Map<string, ChecklistResponse>()
    if (ltRows) {
      map.set('F1-lt-rows', {
        item_id: 'F1-lt-rows', conclusion: null, remark: JSON.stringify(ltRows),
      })
    }
    return useF1DisclosureSoe({
      allResponses: ref(map),
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet: makeCrossSheet([
        { customerName: '供应商丙', endAudited: 800, agingDescription: '1至2年', agingAudited: {} },
      ]),
      isReadonly: ref(false),
      applicableStandards: ref(['soe_standalone']),
      clientName: ref(clientName),
    })
  }

  it('读 F1-lt-rows 并驱动②表；over1FromLongTermSheet 为 true', () => {
    const api = build([
      { rowId: 'r1', customerName: '供应商甲', endBalance: 1000, badDebtProvision: 150,
        aging: '1至2年', reason: '货未到' },
    ])
    expect(api.over1FromLongTermSheet.value).toBe(true)
    expect(api.over1YearRows.value).toHaveLength(1)
    expect(api.over1YearRows.value[0]).toMatchObject({
      creditorUnit: CLIENT,
      debtorUnit: '供应商甲',
      endBalance: 850,
      agingLabel: '1至2年',
      reason: '货未到',
      source: 'f1-5',
    })
    expect(api.over1YearTotal.value.endBalance).toBe(850)
  })

  it('无 F1-lt-rows → 回退 F1-2，over1FromLongTermSheet 为 false', () => {
    const api = build(null)
    expect(api.over1FromLongTermSheet.value).toBe(false)
    expect(api.over1YearRows.value[0].source).toBe('f1-2')
    expect(api.over1YearRows.value[0].endBalance).toBe(800)
  })

  it('损坏的 F1-lt-rows JSON 不崩，回退 F1-2', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F1-lt-rows', { item_id: 'F1-lt-rows', conclusion: null, remark: '{not json' })
    const api = useF1DisclosureSoe({
      allResponses: ref(map),
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet: makeCrossSheet([
        { customerName: '供应商丙', endAudited: 800, agingDescription: '1至2年', agingAudited: {} },
      ]),
      isReadonly: ref(false),
      applicableStandards: ref(['soe_standalone']),
      clientName: ref(CLIENT),
    })
    expect(api.over1YearRows.value[0].source).toBe('f1-2')
  })

  it('载荷推最终值（含缺省债权单位），且不推 source 字段', () => {
    const api = build([
      { rowId: 'r1', customerName: '供应商甲', endBalance: 1000, badDebtProvision: 150,
        aging: '1至2年', reason: '货未到' },
    ])
    const sub = buildF1SoeSubTableData(api.getSyncSnapshot())
    const rows = sub[F1_SOE_SUBTABLE.OVER1] as any[]
    expect(rows[0]).toMatchObject({
      creditor_unit: CLIENT,
      debtor_unit: '供应商甲',
      end_balance: 850,
      aging: '1至2年',
      reason: '货未到',
    })
    expect(rows[0].source).toBeUndefined()
    // 合计行：账龄/原因列为源模板的「——」
    expect(rows[1]).toMatchObject({ end_balance: 850, aging: '——', reason: '——', is_total: true })
  })
})
