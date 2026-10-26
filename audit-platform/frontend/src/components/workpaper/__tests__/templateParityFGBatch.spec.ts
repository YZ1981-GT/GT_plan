/**
 * F / G 循环与审定表变动率按权威模板对齐（第二批，spec oo-writeback-template-parity-closure R2.2 / design §3.1）。
 *
 * 每条都同时断言「与模板同式」和「旧口径算出的值不同」：改回旧口径必须打红。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import type { ChecklistResponse } from '../composables/useF3FormData'
import { calcTemplateChangeRate } from '../composables/templateChangeRate'
import { calcChangeRate as d1ChangeRate } from '../composables/useD1FormulaEngine'
import { getChangeRate as d2ChangeRate } from '../composables/useD2FormulaEngine'
import { calcAdjudicationChangeRate as d3ChangeRate } from '../composables/useD3FormulaEngine'
import { calcF4ChangeRate } from '../composables/useF4Adjudication'
import { useF3Adjudication } from '../composables/useF3Adjudication'
import { buildF3DisclosureClassRows } from '../composables/useF3CrossSheet'
import { useG10Adjudication } from '../composables/useG10Adjudication'
import { G10_ADJUDICATION_ITEMS } from '../composables/g10Constants'

vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))

function responses(entries: Record<string, unknown>) {
  const map = new Map<string, ChecklistResponse>()
  for (const [key, value] of Object.entries(entries)) {
    map.set(key, { item_id: key, conclusion: null, remark: typeof value === 'string' ? value : JSON.stringify(value) })
  }
  return ref(map)
}

function withSetup<T>(fn: () => T): T {
  let result!: T
  mount(defineComponent({ setup() { result = fn(); return () => null } }))
  return result
}

describe('审定表变动率：期初为 0 时按模板 IF(AND(E=0,I=0),"",IF(AND(E=0,I>0),1,J/E))', () => {
  it.each([
    ['D1-1', d1ChangeRate],
    ['D2-1', d2ChangeRate],
    ['D3-1', d3ChangeRate],
    ['D5 / D6-1 / D7-1', (p: number, c: number) => calcTemplateChangeRate(p, c)],
  ] as const)('%s：不变 → 空、增加 → 100%、减少 → 无法计算（模板 #DIV/0!）', (_sheet, rate) => {
    expect(rate(0, 0)).toBe('')
    expect(rate(0, 500)).toBe(1)
    expect(rate(0, -500)).toBe('N/A')
    expect(rate(400, 500)).toBeCloseTo(0.25)
  })

  it('F1-1 / F4-1（模板 IF(AND(E=0,J=0),0,…)）：不变 → 0，减少 → 无法计算（F4 原先记 −100%）', () => {
    expect(calcTemplateChangeRate(0, 0, 0)).toBe(0)
    expect(calcTemplateChangeRate(0, 500, 0)).toBe(1)
    expect(calcF4ChangeRate(0, 0)).toBe(0)
    expect(calcF4ChangeRate(0, 500)).toBe(1)
    expect(calcF4ChangeRate(0, -500)).toBe('N/A')
    expect(calcF4ChangeRate(0, -500)).not.toBe(-1)
  })
})

// 期初未审 1000，期初调整 200 + 50（期初审定 1250），本期贷方 300、借方 100
const BASE = { openingUnadjusted: 1000, openingAje: 200, openingRje: 50, periodCredit: 300, periodDebit: 100 }

describe('F3-1 期末未审从期初未审起算（模板 F3-2 O = L + M − N，F3-1 F 取其分类合计）', () => {
  it('审定表行：期末未审 = 期初未审 + 贷方 − 借方，期初调整只进期初审定', () => {
    const adj = withSetup(() => useF3Adjudication({
      wpId: ref('wp-f3'),
      projectId: ref('proj-f3'),
      allResponses: responses({
        'F3-1-adj-rows': [{ rowKey: 'bank', label: '银行承兑汇票', isFixed: true, ...BASE, closingAje: 7, closingRje: 3, indexRef: '', isFromCrossSheet: false }],
      }),
    }))
    const bank = adj.dataRows.value.find((r) => r.rowKey === 'bank')!
    expect(bank.openingAdjusted).toBe(1250)
    expect(bank.closingUnadjusted).toBe(1000 + 300 - 100)
    expect(bank.closingUnadjusted).not.toBe(1250 + 300 - 100) // 旧口径
    expect(bank.closingAdjusted).toBe(1200 + 7 + 3)
  })

  it('附注分类行与审定表同式同取数：无明细时取审定表录入的本期发生（原先不计本期发生）', () => {
    const adj = JSON.stringify([{ rowKey: 'bank', ...BASE, closingAje: 7, closingRje: 3 }])
    const bank = buildF3DisclosureClassRows(adj, JSON.stringify([])).find((r) => r.rowKey === 'bank')!
    expect(bank.priorAmount).toBe(1250)
    expect(bank.endAmount).toBe(1000 + 300 - 100 + 7 + 3)
    expect(bank.endAmount).not.toBe(1250 + 7 + 3) // 旧口径：期初审定、无明细不计本期发生
  })

  it('有明细时本期发生取明细分类合计，起点仍是期初未审', () => {
    const adj = JSON.stringify([{ rowKey: 'bank', ...BASE, closingAje: 0, closingRje: 0 }])
    const detail = JSON.stringify([{ noteType: '银行承兑汇票', openingBalance: 1000, currentIssued: 80, currentAccepted: 30 }])
    const bank = buildF3DisclosureClassRows(adj, detail).find((r) => r.rowKey === 'bank')!
    expect(bank.endAmount).toBe(1000 + 80 - 30)
  })
})

describe('G10-1 期末未审缺失时倒推：期初未审 + 贷方 − 借方（与存储层 parseG10AdjStore 同口径）', () => {
  it('录入的期末未审为 0 而存量行带本期贷 / 借方时按期初未审起算', () => {
    const rowKey = G10_ADJUDICATION_ITEMS[0].rowKey
    const adj = withSetup(() => useG10Adjudication({
      wpId: ref('wp-g10'),
      projectId: ref('proj-g10'),
      allResponses: responses({
        'G10-adj-rows': { [rowKey]: { openingUnadjusted: 1000, openingAJE: 200, openingRJE: 50, closingUnadjusted: 0, periodCredit: 300, periodDebit: 100 } },
      }),
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    }))
    const row = adj.dataRows.value.find((r) => r.rowKey === rowKey)!
    expect(row.openingAdjusted).toBe(1250)
    expect(row.closingUnadjusted).toBe(1000 + 300 - 100)
    expect(row.closingUnadjusted).not.toBe(1250 + 300 - 100) // 旧口径
  })
})
