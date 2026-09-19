/**
 * H1 国企附注披露模型 / 同步载荷 单测
 */
import { describe, expect, it } from 'vitest'
import {
  H1_SOE_CATEGORIES,
  buildSummaryRows,
  flattenSoeMovement,
  hydrateIdleRows,
  mapToSoeCategoryKey,
  mapUncertifiedBuildingsToSoe,
  recomputeSoeLayers,
  seedMovementFromDetailRows,
  layerTotal,
  deriveSoeFullyDepreciated,
  fullyDepSubtotal,
  createH1SoeDisclosureState,
} from '../h1SoeDisclosureModel'
import { buildH1SoeSubTableData, buildH1SoeSyncPayload } from '../h1DisclosureSyncPayload'
import { H1_NOTE_SECTION, isH1FixedAssetNoteSection } from '../h1NoteSectionMap'
import { SOE_SECTIONS } from '../h1DisclosureSections'

describe('h1SoeDisclosureModel — 已提足折旧仍在使用', () => {
  it('deriveSoeFullyDepreciated maps to SOE category labels and aggregates cost', () => {
    const rows = [
      { category: '房屋及建筑物', originalCostEnd: 1_000_000, accDepEnd: 1_000_000, impairmentEnd: 0 },
      { category: '运输设备', originalCostEnd: 300_000, accDepEnd: 290_000, impairmentEnd: 0 }, // 净值3.3%
      { category: '机器设备', originalCostEnd: 500_000, accDepEnd: 100_000, impairmentEnd: 0 }, // 未提足
    ]
    const res = deriveSoeFullyDepreciated(rows)
    const byName = Object.fromEntries(res.map((r) => [r.name, r.cost]))
    expect(byName['房屋、建筑物']).toBeCloseTo(1_000_000)
    expect(byName['运输工具']).toBeCloseTo(300_000)
    expect(byName['机器设备']).toBeUndefined()
    expect(fullyDepSubtotal(res)).toBeCloseTo(1_300_000)
  })

  it('deriveSoeFullyDepreciated honors audited fields (costEndAud/depEndAud)', () => {
    const rows = [
      { category: '电子设备', costEndAud: 200_000, depEndAud: 200_000, impairEndAud: 0 },
    ]
    const res = deriveSoeFullyDepreciated(rows)
    expect(res).toHaveLength(1)
    expect(res[0].name).toBe('电子设备')
    expect(res[0].cost).toBeCloseTo(200_000)
  })
})

describe('flattenSoeMovement — 源模板整行「—」列示约定', () => {
  function landRow(layer: string, layers = recomputeSoeLayers(createEmptyLayersFixture())) {
    return flattenSoeMovement(layers).find((r) => r.rowKey === `${layer}-land`)!
  }

  function createEmptyLayersFixture() {
    return createH1SoeDisclosureState().layers
  }

  it('土地资产在累计折旧（R24）与减值准备（R42）层标记 allNa', () => {
    expect(landRow('dep').allNa).toBe(true)
    expect(landRow('impair').allNa).toBe(true)
    // 原值层土地是正常可填行
    expect(landRow('cost').allNa).toBe(false)
  })

  it('无金额时 hasAmount=false（UI 显示「—」）', () => {
    expect(landRow('dep').hasAmount).toBe(false)
    expect(landRow('impair').hasAmount).toBe(false)
  })

  it('带入金额后 hasAmount=true —— 照常显示以免静默丢数', () => {
    const st = createH1SoeDisclosureState()
    st.layers.find((l) => l.layer === 'dep')!.categories.find((c) => c.key === 'land')!.begin = 123
    recomputeSoeLayers(st.layers)
    const row = flattenSoeMovement(st.layers).find((r) => r.rowKey === 'dep-land')!
    expect(row.allNa).toBe(true)
    expect(row.hasAmount).toBe(true)
    expect(row.begin).toBe(123)
  })
})

describe('h1SoeDisclosureModel', () => {
  it('maps H1-2 categories onto SOE fixed taxonomy', () => {
    expect(mapToSoeCategoryKey('房屋及建筑物')).toBe('building')
    expect(mapToSoeCategoryKey('运输设备')).toBe('transport')
    expect(mapToSoeCategoryKey('土地资产')).toBe('land')
    expect(mapToSoeCategoryKey('酒店业家具')).toBe('hotel')
    expect(mapToSoeCategoryKey('其他设备')).toBe('other')
  })

  it('seeds movement from detail and derives net / carrying', () => {
    const layers = seedMovementFromDetailRows([
      {
        category: '房屋及建筑物',
        costBeginAud: 1000,
        costIncAud: 200,
        costDecAud: 50,
        depBeginAud: 100,
        depIncAud: 20,
        depDecAud: 0,
        impairBeginAud: 10,
        impairIncAud: 0,
        impairDecAud: 0,
      },
      {
        category: '机器设备',
        originalCostBegin: 500,
        originalCostIncrease: 0,
        originalCostDecrease: 0,
        accDepBegin: 50,
        accDepProvision: 10,
        accDepReversal: 0,
        impairmentBegin: 0,
        impairmentProvision: 0,
        impairmentReversal: 0,
      },
    ])
    const cost = layers.find((l) => l.layer === 'cost')!
    const building = cost.categories.find((c) => c.key === 'building')!
    expect(building.begin).toBe(1000)
    expect(building.increase).toBe(200)
    expect(building.decrease).toBe(50)
    expect(building.end).toBe(1150)

    const carrying = layers.find((l) => l.layer === 'carrying')!
    const bCarrying = carrying.categories.find((c) => c.key === 'building')!
    // end = 1150 - (100+20) - 10 = 1020
    expect(bCarrying.end).toBe(1020)

    const flat = flattenSoeMovement(layers)
    expect(flat.some((r) => r.label === '一、账面原值合计' && r.kind === 'total')).toBe(true)
    expect(flat.filter((r) => r.layer === 'net' && r.kind === 'detail').every((r) => r.movementNa)).toBe(true)
    expect(H1_SOE_CATEGORIES).toHaveLength(8)
  })

  it('summary FA row equals carrying layer total', () => {
    const layers = seedMovementFromDetailRows([
      {
        category: '办公设备',
        costBeginAud: 100,
        costIncAud: 0,
        costDecAud: 0,
        depBeginAud: 40,
        depIncAud: 0,
        depDecAud: 0,
        impairBeginAud: 0,
        impairIncAud: 0,
        impairDecAud: 0,
      },
    ])
    recomputeSoeLayers(layers)
    const rows = buildSummaryRows(layers, { clearingEnd: 5, clearingBegin: 3 })
    const fa = rows.find((r) => r.key === 'fa')!
    const tot = rows.find((r) => r.key === 'total')!
    const carryingEnd = layerTotal(layers.find((l) => l.layer === 'carrying')!).end
    expect(fa.endCarrying).toBe(carryingEnd)
    expect(fa.endCarrying).toBe(60)
    expect(tot.endCarrying).toBe(65)
  })

  it('hydrates legacy idle rows {amount,description}', () => {
    const rows = hydrateIdleRows([
      { rowId: '1', name: '旧行', amount: 88, description: '说明' },
    ])
    expect(rows[0].carrying).toBe(88)
    expect(rows[0].remark).toBe('说明')
  })

  it('maps uncertified buildings from H1-16', () => {
    const rows = mapUncertifiedBuildingsToSoe([
      { rowId: 'a', name: '厂房A', checkConclusion: '未取得权证', netValue: 12, cipNote: '正在办证' },
      { rowId: 'b', name: '厂房B', fromCip: 'Y', titleCertNo: '', bookValue: 100, accumDep: 20, impairment: 0 },
      { rowId: 'c', name: '已办证', titleCertNo: '京房权证1', checkConclusion: '相符', netValue: 9 },
    ])
    expect(rows).toHaveLength(2)
    expect(rows[0].reason).toContain('正在办证')
    expect(rows[1].carrying).toBe(80)
  })
})

describe('h1DisclosureSyncPayload / note map', () => {
  it('SOE sections match note template chapters', () => {
    expect(SOE_SECTIONS.map((s) => s.key)).toEqual(['summary', 'overview', 'idle', 'title', 'clearing'])
    expect(H1_NOTE_SECTION.soe).toBe('八、22')
    expect(isH1FixedAssetNoteSection('八、22')).toBe(true)
  })

  it('builds sync payload with note_template_soe sub-table names', () => {
    const layers = seedMovementFromDetailRows([
      {
        category: '电子设备',
        costBeginAud: 10,
        costIncAud: 0,
        costDecAud: 0,
        depBeginAud: 1,
        depIncAud: 0,
        depDecAud: 0,
        impairBeginAud: 0,
        impairIncAud: 0,
        impairDecAud: 0,
      },
    ])
    const state = {
      summary: { clearingEnd: 1, clearingBegin: 0 },
      layers,
      idleRows: [{ rowId: 'i1', name: '闲置机', originalCost: 10, accumDep: 2, impairment: 0, carrying: 8, remark: '' }],
      titleRows: [{ rowId: 't1', name: '未办证房', carrying: 5, reason: '手续中' }],
      clearingRows: [{ rowId: 'c1', name: '报废车', endCarrying: 1, beginCarrying: 0, reason: '报废' }],
      clearingNote: '超1年清理仍在拍卖中',
    }
    const sub = buildH1SoeSubTableData(state)
    expect(Object.keys(sub)).toEqual(expect.arrayContaining([
      '固定资产',
      '固定资产情况',
      '暂时闲置的固定资产情况',
      '未办妥产权证书的固定资产情况',
      '固定资产清理',
      '_note_texts',
    ]))
    expect(sub['固定资产'].some((r) => r.label === '合计' && r.is_total)).toBe(true)
    expect(sub['固定资产情况'].some((r) => String(r.label).includes('账面原值'))).toBe(true)

    const payload = buildH1SoeSyncPayload('wp-h1', ['soe_standalone'], state)
    expect(payload?.section_id).toBe('八、22')
    expect(payload?.sheet_name).toContain('国有企业')
  })

  it('rejects sync when standards are listed-only', () => {
    const state = {
      summary: { clearingEnd: 0, clearingBegin: 0 },
      layers: seedMovementFromDetailRows([]),
      idleRows: [],
      titleRows: [],
      clearingRows: [],
      clearingNote: '',
    }
    expect(buildH1SoeSyncPayload('wp', ['listed_standalone'], state)).toBeNull()
  })
})
