/**
 * useG9Detail — G9-2 明细表单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  enrichG9DetailRow,
  scanG9DetailIntegrity,
  seedRowFromAux,
  useG9Detail,
} from '../useG9Detail'
import { pushG9DetailGroupTotalsToAdjudication } from '../g9CrossHelpers'
import { calcEndingBalance } from '../useG9FormulaEngine'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: {
    prompt: vi.fn(),
    confirm: vi.fn().mockResolvedValue(true),
  },
}))

describe('G9-2 公式', () => {
  it('期末含 OCI 变动', () => {
    expect(calcEndingBalance(1000, 100, 50, 20, 10, 5, 30)).toBe(1105)
  })

  it('enrich 计算期初审定与期末', () => {
    const row = enrichG9DetailRow({
      rowId: 'r1',
      assetName: '基金A',
      openingBalance: 1000,
      openingAdjustment: 50,
      increaseAmount: 100,
      decreaseAmount: 20,
      fvChangeAmount: 30,
      interestIncome: 5,
      impairmentLoss: 0,
      ociChange: 10,
      closingAdjustment: 0,
    }, 1)
    expect(row.openingAdjusted).toBe(1050)
    expect(row.closingBalance).toBe(1175)
    expect(row.closingAdjusted).toBe(1175)
  })
})

describe('scanG9DetailIntegrity', () => {
  it('Level3 缺估值方法', () => {
    const issues = scanG9DetailIntegrity([
      enrichG9DetailRow({
        rowId: 'r1',
        assetName: '私募',
        fairValueLevel: 'Level3',
        valuationMethod: '',
        closingAdjustment: 0,
        openingBalance: 100,
      }, 1),
    ])
    expect(issues.some((i) => i.field === 'valuationMethod')).toBe(true)
  })

  it('FVOCI FV 与 OCI 不一致告警', () => {
    const issues = scanG9DetailIntegrity([
      enrichG9DetailRow({
        rowId: 'r1',
        assetName: '债A',
        classification: 'FVOCI',
        fvChangeAmount: 100,
        ociChange: 50,
      }, 1),
    ])
    expect(issues.some((i) => i.field === 'ociChange')).toBe(true)
  })
})

describe('seedRowFromAux', () => {
  it('轧差入 FV 变动', () => {
    const row = seedRowFromAux({
      assetName: '理财X',
      openingBalance: 100,
      closingBalance: 130,
      auxType: '产品',
      auxCode: 'P1',
    }, 1)
    expect(row.openingBalance).toBe(100)
    expect(row.fvChangeAmount).toBe(30)
    expect(row.closingBalance).toBe(130)
  })
})

describe('pushG9DetailGroupTotalsToAdjudication', () => {
  it('按分类写入各组首行', () => {
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const map = new Map<string, ChecklistResponse>()
    const n = pushG9DetailGroupTotalsToAdjudication(
      map,
      (id, d) => {
        saves.push({ id, data: d })
        map.set(id, { item_id: id, conclusion: d.conclusion ?? null, remark: d.remark ?? null } as ChecklistResponse)
      },
      [
        { classification: 'FVTPL', openingAdjusted: 1000, closingBalance: 1200, closingAdjusted: 1200 },
        { classification: 'FVOCI', openingAdjusted: 500, closingBalance: 550, closingAdjusted: 550 },
        { classification: '摊余成本', openingAdjusted: 0, closingBalance: 0, closingAdjusted: 0 },
      ],
    )
    expect(n).toBe(2)
    const store = JSON.parse(String(saves.find((s) => s.id === 'G9-adj-rows')?.data.remark))
    expect(store.fvtpl_1.closingUnadjusted).toBe(1200)
    expect(store.fvoci_1.openingUnadjusted).toBe(500)
  })
})

describe('useG9Detail', () => {
  it('分类小计与完整性', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G9-detail-rows', {
        item_id: 'G9-detail-rows',
        conclusion: null,
        remark: JSON.stringify([
          { rowId: 'a', assetName: 'A', classification: 'FVTPL', openingBalance: 100, fairValueLevel: 'Level2' },
          { rowId: 'b', assetName: 'B', classification: 'FVOCI', openingBalance: 200, fvChangeAmount: 10, fairValueLevel: 'Level3' },
        ]),
      } as ChecklistResponse],
    ]))
    const d = useG9Detail({
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(d.rows.value).toHaveLength(2)
    expect(d.classificationSubtotals.value.FVTPL).toBe(100)
    expect(d.classificationSubtotals.value.FVOCI).toBe(210)
    expect(d.level3MissingMethodCount.value).toBe(1)
  })

  it('fillOciFromFvChange', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G9-detail-rows', {
        item_id: 'G9-detail-rows',
        conclusion: null,
        remark: JSON.stringify([
          { rowId: 'a', assetName: 'A', classification: 'FVOCI', fvChangeAmount: 80, ociChange: 0 },
          { rowId: 'b', assetName: 'B', classification: 'FVTPL', fvChangeAmount: 50, ociChange: 0 },
        ]),
      } as ChecklistResponse],
    ]))
    const d = useG9Detail({
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })
    expect(d.fillOciFromFvChange()).toBe(1)
    expect(d.rows.value.find((r) => r.rowId === 'a')?.ociChange).toBe(80)
  })
})
