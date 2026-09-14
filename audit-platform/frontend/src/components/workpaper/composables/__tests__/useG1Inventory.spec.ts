import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useG1Inventory,
  createEmptyG1InventoryRow,
  enrichG1InventoryRow,
  calcInventoryDiff,
  pickExternalEvidence,
  isDiffAbnormal,
  applyConfirmationSecuritiesRows,
  crossCheckInventoryVsReconciliation,
} from '../useG1Inventory'
import type { ChecklistResponse } from '../useF1FormData'

function setup(seed?: Partial<ChecklistResponse>) {
  const allResponses = ref(new Map<string, ChecklistResponse>())
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      allResponses.value.set(k, v as ChecklistResponse)
    }
  }
  const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
  const debouncedSave = (itemId: string, data: Partial<ChecklistResponse>) => {
    saves.push({ id: itemId, data })
    allResponses.value.set(itemId, {
      item_id: itemId,
      conclusion: data.conclusion ?? null,
      remark: data.remark ?? null,
      ...data,
    } as ChecklistResponse)
  }
  const hook = useG1Inventory({
    allResponses,
    debouncedSave,
    isReadonly: ref(false),
  })
  return { ...hook, allResponses, saves }
}

describe('G1-4 差异公式', () => {
  it('⑤ = ① − ② − ④（auto 优先函证）', () => {
    const row = enrichG1InventoryRow({
      ...createEmptyG1InventoryRow(),
      bookQuantity: 100,
      bookFaceValue: 10,
      stockQuantity: 20,
      stockFaceValue: 10,
      stmtQuantity: 50,
      stmtFaceValue: 10,
      confQuantity: 70,
      confFaceValue: 10,
      evidenceSource: 'auto',
    })
    // 100*10 - 20*10 - 70*10 = 1000 - 200 - 700 = 100
    expect(row.bookTotal).toBe(1000)
    expect(pickExternalEvidence(row).label).toBe('函证')
    expect(row.diffQuantity).toBe(10) // 100 - 20 - 70
    expect(row.diffTotal).toBe(100)
  })

  it('无函证时 auto 使用对账单', () => {
    const row = enrichG1InventoryRow({
      ...createEmptyG1InventoryRow(),
      bookQuantity: 100,
      bookFaceValue: 1,
      stockQuantity: 0,
      stmtQuantity: 100,
      stmtFaceValue: 1,
      evidenceSource: 'auto',
    })
    expect(pickExternalEvidence(row).label).toBe('对账单')
    expect(row.diffQuantity).toBe(0)
    expect(isDiffAbnormal(row)).toBe(false)
  })

  it('仅监盘模式：⑤ = ① − ②', () => {
    const diff = calcInventoryDiff({
      ...createEmptyG1InventoryRow(),
      bookQuantity: 80,
      bookFaceValue: 5,
      stockQuantity: 80,
      stockFaceValue: 5,
      stmtQuantity: 999,
      stmtFaceValue: 5,
      evidenceSource: 'stocktake',
    })
    expect(diff.diffQuantity).toBe(0)
    expect(diff.diffTotal).toBe(0)
  })

  it('迁移旧版滚动结存字段', () => {
    const { rows } = setup({
      'G1-4-rows': {
        item_id: 'G1-4-rows',
        conclusion: JSON.stringify([
          {
            id: 'legacy-1',
            securityName: '国债01',
            securityType: '债券',
            closingQuantity: 10,
            closingCost: 1000,
            closingFairValue: 1100,
            unrealizedGain: 100,
          },
        ]),
        remark: null,
      } as ChecklistResponse,
    })
    expect(rows.value[0].securityName).toBe('国债01')
    expect(rows.value[0].bookQuantity).toBe(10)
    expect(rows.value[0].bookTotal).toBe(1100)
  })
})

describe('useG1Inventory 联动', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('从 G1-2 带入账面', () => {
    const { syncFromDetail, rows, allResponses } = setup({
      'G1-2-rows': {
        item_id: 'G1-2-rows',
        conclusion: JSON.stringify([
          {
            securityName: '股票A',
            securityCode: '600000',
            closingQuantity: 100,
            closingCost: 5000,
            auditedClosingCost: 5000,
            closingFairValue: 6000,
            auditedClosingFvTotal: 6000,
          },
        ]),
        remark: null,
      } as ChecklistResponse,
    })
    const n = syncFromDetail()
    expect(n).toBe(1)
    expect(rows.value[0].securityName).toBe('股票A')
    expect(rows.value[0].cashAccountNo).toBe('600000')
    expect(rows.value[0].bookQuantity).toBe(100)
    expect(rows.value[0].bookTotal).toBe(6000)
    expect(allResponses.value.get('G1-4-rows')?.conclusion).toContain('股票A')
  })

  it('从 G1-11 回填监盘数量', () => {
    const { syncFromSecuritiesCount, rows, updateRow } = setup()
    // ensure a named row
    updateRow(rows.value[0].id, {
      securityName: '股票A',
      cashAccountNo: '600000',
      bookQuantity: 100,
      bookFaceValue: 10,
    })
    const { syncFromSecuritiesCount: sync2, rows: rows2, allResponses } = setup({
      'G1-4-rows': {
        item_id: 'G1-4-rows',
        conclusion: JSON.stringify(rows.value),
        remark: null,
      } as ChecklistResponse,
      'G1-11-rows': {
        item_id: 'G1-11-rows',
        conclusion: JSON.stringify([
          {
            securityName: '股票A',
            securityCode: '600000',
            countedQuantity: 95,
          },
        ]),
        remark: null,
      } as ChecklistResponse,
    })
    const n = sync2()
    expect(n).toBe(1)
    expect(rows2.value[0].stockQuantity).toBe(95)
    expect(allResponses.value.get('G1-4-rows')).toBeTruthy()
  })

  it('从函证证券行回填④（按代码匹配）', () => {
    const { syncFromConfirmationRows, rows, updateRow } = setup()
    updateRow(rows.value[0].id, {
      securityName: '股票A',
      cashAccountNo: '600000',
      bookQuantity: 100,
      bookFaceValue: 10,
    })
    const n = syncFromConfirmationRows([
      {
        security_name: '股票A',
        security_code: '600000',
        confirmed_qty: 98,
        confirmed_unit_fv: 10.5,
        confirmed_market_value: 1029,
      },
    ])
    expect(n).toBe(1)
    expect(rows.value[0].confQuantity).toBe(98)
    expect(rows.value[0].confFaceValue).toBe(10.5)
    expect(rows.value[0].confTotal).toBeCloseTo(1029, 5)
    expect(rows.value[0].evidenceSource).toBe('confirmation')
  })

  it('函证仅有金额时按账面数量折算单价', () => {
    const { rows } = applyConfirmationSecuritiesRows(
      [
        enrichG1InventoryRow({
          ...createEmptyG1InventoryRow(1),
          securityName: '基金B',
          bookQuantity: 50,
          bookFaceValue: 2,
        }),
      ],
      [{ entity_name: '基金B', amount: 120 }],
    )
    expect(rows[0].confQuantity).toBe(50)
    expect(rows[0].confFaceValue).toBe(2.4)
    expect(rows[0].confTotal).toBeCloseTo(120, 5)
  })

  it('函证模糊匹配与未匹配清单', () => {
    const result = applyConfirmationSecuritiesRows(
      [
        enrichG1InventoryRow({
          ...createEmptyG1InventoryRow(1),
          securityName: '贵州茅台',
          cashAccountNo: '600519',
          bookQuantity: 10,
          bookFaceValue: 100,
        }),
      ],
      [
        { security_name: '贵州茅台股份', confirmed_qty: 10, confirmed_unit_fv: 100 },
        { security_name: '不存在的证券XYZ', confirmed_qty: 1, confirmed_unit_fv: 1 },
      ],
    )
    expect(result.matched).toBe(1)
    expect(result.fuzzyMatched).toBe(1)
    expect(result.rows[0].confQuantity).toBe(10)
    expect(result.unmatchedConfirm).toHaveLength(1)
    expect(result.unmatchedConfirm[0].label).toContain('不存在的证券XYZ')
  })

  it('与 G1-12 交叉校验检出账面数量差异', () => {
    const mismatches = crossCheckInventoryVsReconciliation(
      [
        enrichG1InventoryRow({
          ...createEmptyG1InventoryRow(1),
          securityName: '股票A',
          bookQuantity: 100,
          bookFaceValue: 10,
        }),
      ],
      [{ securityName: '股票A', bookQuantity: 95, bookTotal: 950, reportQuantity: 95 }],
    )
    expect(mismatches).toHaveLength(1)
    expect(mismatches[0].inventoryBookQty).toBe(100)
    expect(mismatches[0].reconBookQty).toBe(95)
  })

  it('差异推送写入 G1-3-rows', () => {
    const { rows, updateRow, pushDiffToAdjustment, saves } = setup()
    updateRow(rows.value[0].id, {
      securityName: '差异券',
      bookQuantity: 100,
      bookFaceValue: 10,
      stockQuantity: 0,
      stmtQuantity: 0,
      confQuantity: 0,
    })
    expect(isDiffAbnormal(rows.value[0])).toBe(true)
    const n = pushDiffToAdjustment()
    expect(n).toBe(1)
    expect(saves.some((s) => s.id === 'G1-3-rows')).toBe(true)
    const adj = JSON.parse(String(saves.find((s) => s.id === 'G1-3-rows')!.data.remark))
    expect(adj[0].description).toContain('G1-4')
    expect(adj[0].indexRef).toBe('G1-4')
  })
})
