/**
 * n2DisclosurePrefill.spec.ts — prefillFromAdjudication 纯函数守卫
 *
 * spec: .kiro/specs/n2-disclosure-and-extraction-alignment/ Task 4.3
 */
import { describe, it, expect } from 'vitest'
import { prefillFromAdjudication, N2_LISTED_TAX_ITEMS, N2_SOE_TAX_ITEMS } from '../useN2DisclosureTables'
import { computeN2SoeEnd, type N2DisclosureVariant } from '../n2NoteSectionMap'
import { N2_FIXED_TAX_LABELS } from '../n2TaxLabelMap'

// ─── 辅助：构造 13 种审定行 ──────────────────────────────────────────────────

const THIRTEEN_TAX_TYPES = [...N2_FIXED_TAX_LABELS]

function makeAdjRows(amount = 100) {
  return THIRTEEN_TAX_TYPES.map((taxType, i) => ({
    taxType,
    beginAudited: (i + 1) * amount,
    endAudited: (i + 2) * amount,
  }))
}

function makeDetailRows(amount = 100) {
  return THIRTEEN_TAX_TYPES.map((taxType, i) => ({
    taxType,
    audBegin: (i + 1) * amount,
    audPayable: (i + 3) * amount,
    audPaid: (i + 2) * amount,
  }))
}

// ─── 1. 喂 13 种审定行 → 13 固定行全有值 ─────────────────────────────────────

describe('喂 13 种审定行 → 13 固定行全有值', () => {
  it('上市版：每行 end/prior 都非 null', () => {
    const result = prefillFromAdjudication({
      variant: 'listed',
      adjRows: makeAdjRows(),
    })
    expect(result.listedRows).toBeDefined()
    expect(result.listedRows!.length).toBeGreaterThanOrEqual(13)
    for (const label of THIRTEEN_TAX_TYPES) {
      const row = result.listedRows!.find((r) => r.item === label)
      expect(row, `缺少行: ${label}`).toBeDefined()
      expect(row!.end).not.toBeNull()
      expect(row!.prior).not.toBeNull()
    }
  })

  it('国企版：每行 opening/payable/paid 都非 null', () => {
    const result = prefillFromAdjudication({
      variant: 'soe',
      adjRows: [],
      detailRows: makeDetailRows(),
    })
    expect(result.soeRows).toBeDefined()
    expect(result.soeRows!.length).toBeGreaterThanOrEqual(13)
    for (const label of THIRTEEN_TAX_TYPES) {
      const row = result.soeRows!.find((r) => r.item === label)
      expect(row, `缺少行: ${label}`).toBeDefined()
      expect(row!.opening).not.toBeNull()
      expect(row!.payable).not.toBeNull()
      expect(row!.paid).not.toBeNull()
    }
  })
})

// ─── 2. 喂空数组 → 13 行全 null ──────────────────────────────────────────────

describe('喂空数组 → 13 行全 null', () => {
  it('上市版：13 行骨架全 null', () => {
    const result = prefillFromAdjudication({
      variant: 'listed',
      adjRows: [],
    })
    expect(result.listedRows).toBeDefined()
    expect(result.listedRows!).toHaveLength(13)
    for (const row of result.listedRows!) {
      expect(row.end).toBeNull()
      expect(row.prior).toBeNull()
    }
  })

  it('国企版：13 行骨架全 null', () => {
    const result = prefillFromAdjudication({
      variant: 'soe',
      adjRows: [],
      detailRows: [],
    })
    expect(result.soeRows).toBeDefined()
    expect(result.soeRows!).toHaveLength(13)
    for (const row of result.soeRows!) {
      expect(row.opening).toBeNull()
      expect(row.payable).toBeNull()
      expect(row.paid).toBeNull()
    }
  })
})

// ─── 3. 手工优先：已有值的格子不被覆盖 ──────────────────────────────────────

describe('手工优先', () => {
  it('existingListedRows 某行 end=999，prefill 后该格子仍为 999', () => {
    const existing = N2_LISTED_TAX_ITEMS.map((item) => ({
      item,
      end: null as number | null,
      prior: null as number | null,
    }))
    // 手工设置第一行
    existing[0].end = 999

    const result = prefillFromAdjudication({
      variant: 'listed',
      adjRows: makeAdjRows(),
      existingListedRows: existing,
    })

    expect(result.listedRows![0].end).toBe(999) // 手工值不被覆盖
    expect(result.listedRows![0].prior).not.toBeNull() // null 格被填充
  })

  it('国企版：已有 opening 不被覆盖', () => {
    const existing = N2_SOE_TAX_ITEMS.map((item) => ({
      item,
      opening: null as number | null,
      payable: null as number | null,
      paid: null as number | null,
    }))
    existing[2].opening = 777

    const result = prefillFromAdjudication({
      variant: 'soe',
      adjRows: [],
      detailRows: makeDetailRows(),
      existingSoeRows: existing,
    })

    expect(result.soeRows![2].opening).toBe(777)
    expect(result.soeRows![2].payable).not.toBeNull()
  })
})

// ─── 4. 同名累加 ─────────────────────────────────────────────────────────────

describe('同名累加', () => {
  it('两行 taxType=增值税（endAudited=100,200）→ 增值税行 end=300', () => {
    const result = prefillFromAdjudication({
      variant: 'listed',
      adjRows: [
        { taxType: '增值税', beginAudited: 50, endAudited: 100 },
        { taxType: '增值税', beginAudited: 60, endAudited: 200 },
      ],
    })

    const vatRow = result.listedRows!.find((r) => r.item === '增值税')
    expect(vatRow).toBeDefined()
    expect(vatRow!.end).toBe(300)
    expect(vatRow!.prior).toBe(110)
  })
})

// ─── 5. 国企版 computeN2SoeEnd ───────────────────────────────────────────────

describe('国企版 computeN2SoeEnd', () => {
  it('end = opening + payable - paid', () => {
    const end = computeN2SoeEnd({ opening: 100, payable: 200, paid: 50 })
    expect(end).toBe(250)
  })

  it('全 null → null', () => {
    const end = computeN2SoeEnd({ opening: null, payable: null, paid: null })
    expect(end).toBeNull()
  })

  it('部分 null → 视缺失为 0 计算', () => {
    const end = computeN2SoeEnd({ opening: 100, payable: null, paid: null })
    expect(end).toBe(100)
  })

  it('detailRows 喂值后，用 computeN2SoeEnd 验证', () => {
    const result = prefillFromAdjudication({
      variant: 'soe',
      adjRows: [],
      detailRows: [
        { taxType: '企业所得税', audBegin: 1000, audPayable: 500, audPaid: 300 },
      ],
    })
    const row = result.soeRows!.find((r) => r.item === '企业所得税')!
    expect(row.opening).toBe(1000)
    expect(row.payable).toBe(500)
    expect(row.paid).toBe(300)
    // end = 1000 + 500 - 300 = 1200
    const end = computeN2SoeEnd(row)
    expect(end).toBe(1200)
  })
})

// ─── 6. 归一 ─────────────────────────────────────────────────────────────────

describe('归一', () => {
  it("taxType='未交增值税' → 落到「增值税」行", () => {
    const result = prefillFromAdjudication({
      variant: 'listed',
      adjRows: [{ taxType: '未交增值税', beginAudited: 10, endAudited: 20 }],
    })
    const vatRow = result.listedRows!.find((r) => r.item === '增值税')
    expect(vatRow!.end).toBe(20)
    // 「未交增值税」不应产生新行
    expect(result.listedRows!.find((r) => r.item === '未交增值税')).toBeUndefined()
  })

  it("taxType='城建税' → 落到「城市维护建设税」行", () => {
    const result = prefillFromAdjudication({
      variant: 'listed',
      adjRows: [{ taxType: '城建税', beginAudited: 10, endAudited: 30 }],
    })
    const row = result.listedRows!.find((r) => r.item === '城市维护建设税')
    expect(row!.end).toBe(30)
  })
})

// ─── 7. 动态增行 ─────────────────────────────────────────────────────────────

describe('动态增行', () => {
  it("taxType='印花税'（不在 13 固定行）→ 追加到末尾且 _editableLabel=true", () => {
    const result = prefillFromAdjudication({
      variant: 'listed',
      adjRows: [{ taxType: '印花税', beginAudited: 5, endAudited: 15 }],
    })
    const stampRow = result.listedRows!.find((r) => r.item === '印花税')
    expect(stampRow).toBeDefined()
    expect(stampRow!.end).toBe(15)
    expect(stampRow!.prior).toBe(5)
    expect(stampRow!._editableLabel).toBe(true)
    // 印花税应在固定 13 行之后
    const idx = result.listedRows!.indexOf(stampRow!)
    expect(idx).toBeGreaterThanOrEqual(13)
  })
})
