import { describe, it, expect } from 'vitest'
import {
  defaultClassificationRows,
  sumAmountLeaves,
  hierarchyTotal,
  calcL3Closing,
  defaultFvHierarchyRows,
  defaultL3RollRows,
  G1_INPUT_CANDIDATES,
} from '../g1DisclosureItems'
import { buildG1ListedSubTableData, buildG1SyncPayload } from '../g1DisclosureSyncPayload'
import { G1_DISCLOSURE_SHEET_NAME, G1_NOTE_SECTION } from '../g1NoteSectionMap'

describe('g1DisclosureItems', () => {
  it('分类行含划分为与指定小类及合计', () => {
    const rows = defaultClassificationRows()
    expect(rows.some((r) => r.rowKey.startsWith('classified-'))).toBe(true)
    expect(rows.some((r) => r.rowKey.startsWith('designated-'))).toBe(true)
    expect(rows.find((r) => r.kind === 'subtotal')?.label).toBe('合计')
  })

  it('sumAmountLeaves 仅汇总适用叶子', () => {
    const rows = defaultClassificationRows().map((r) =>
      r.rowKey === 'classified-debt'
        ? { ...r, endAmount: 100, priorAmount: 40 }
        : r.rowKey === 'classified-equity'
          ? { ...r, endAmount: 50, applicable: false }
          : r,
    )
    expect(sumAmountLeaves(rows).end).toBe(100)
    expect(sumAmountLeaves(rows).prior).toBe(40)
  })

  it('hierarchyTotal 与 L3 closing 公式', () => {
    const fv = defaultFvHierarchyRows().map((r) =>
      r.rowKey === 'fv-trading' ? { ...r, l1: 10, l2: 20, l3: 30 } : r,
    )
    expect(hierarchyTotal(fv).total).toBe(60)
    expect(calcL3Closing({
      rowKey: 'x', label: '', kind: 'leaf',
      opening: 100, transferIn: 10, transferOut: 5,
      gainPl: 3, gainOci: 0, purchase: 20, issue: 0, sale: 8, settlement: 0,
      closing: 0, unrealizedHeld: 0,
    })).toBe(120)
  })

  it('估值技术有候选指标', () => {
    expect(G1_INPUT_CANDIDATES.market.length).toBeGreaterThan(0)
    expect(G1_INPUT_CANDIDATES.income).toContain('折现率')
  })
})

describe('g1DisclosureSyncPayload', () => {
  it('构建五、2 sync payload', () => {
    const snap = {
      classificationRows: defaultClassificationRows(),
      designatedReason: '指定理由测试',
      derivativeRows: [],
      derivativeNote: '',
      fvRows: defaultFvHierarchyRows(),
      inputRows: [],
      l3Rows: defaultL3RollRows(),
      amortRows: [],
      generalNote: '说明',
    }
    const sub = buildG1ListedSubTableData(snap)
    expect(sub['交易性金融资产分类']).toBeTruthy()
    expect(sub['指定理由'][0].说明).toBe('指定理由测试')
    const payload = buildG1SyncPayload('listed', 'wp-1', ['listed_standalone'], sub)
    expect(payload?.section_id).toBe(G1_NOTE_SECTION.listed.trading)
    // sheet_name = 源 xlsx 真实 tab 名（非 `G1-note-listed` 合成标识）
    expect(payload?.sheet_name).toBe(G1_DISCLOSURE_SHEET_NAME.listed)
  })
})
