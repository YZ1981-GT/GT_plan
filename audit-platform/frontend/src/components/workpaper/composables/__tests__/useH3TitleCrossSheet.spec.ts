import { describe, it, expect } from 'vitest'
import {
  calcAreaDiff,
  isAreaAnomaly,
  isAreaAcceptableDiff,
  suggestMatchConsistent,
  normalizeTitleRow,
  nameSimilarity,
  buildRestrictionDisclosureText,
} from '../h3TitleRowModel'
import {
  extractH32TitleSeeds,
  extractH39TitleSeeds,
  importTitleRowsFromH32,
  importTitleRowsFromH39,
  syncMortgageFromL1,
  parseL1PledgeRowsFromMap,
  buildCompletenessChecks,
  applySamplePlan,
  fillCertAreaFromBook,
  applyAuditeeDefaults,
  findBestTitleMatch,
  mapAssetTypeToCertName,
} from '../useH3TitleCrossSheet'

describe('h3TitleRowModel area tolerance', () => {
  it('calcAreaDiff', () => {
    expect(calcAreaDiff(120, 100)).toBe(20)
  })

  it('容差内不视为异常', () => {
    expect(isAreaAnomaly(100.5, 100)).toBe(false)
    expect(isAreaAcceptableDiff(100.5, 100)).toBe(true)
  })

  it('超出容差视为异常', () => {
    expect(isAreaAnomaly(120, 100)).toBe(true)
  })

  it('suggestMatchConsistent 使用容差', () => {
    expect(suggestMatchConsistent({
      isAuditEntity: '是',
      areaDiff: 0.5,
      certArea: 100.5,
      bookArea: 100,
      certPurpose: '商业',
      actualPurpose: '商业',
      inconsistentReason: '',
    })).toBe('是')
  })
})

describe('useH3TitleCrossSheet enhanced', () => {
  const getValue = (id: string) => {
    if (id === 'H3-2-cost-rows') {
      return [
        { rowId: 'dc-1', assetName: 'A大厦', assetType: '房屋', location: '上海市浦东', area: 1200, costEnd: 5000000 },
        { rowId: 'dc-2', assetName: 'B地块', assetType: '土地', location: '杭州市滨江', area: 3000, originalCost: 2000000 },
      ]
    }
    if (id === 'H3-9-stocktake-rows') {
      return [
        { rowId: 'st-1', assetName: 'A大厦1号楼', location: '上海市浦东新区', titleCertNo: '沪房地浦字001', area: 1200, bookValue: 4800000, purpose: '出租' },
      ]
    }
    return []
  }

  it('模糊匹配名称包含关系', () => {
    expect(nameSimilarity('A大厦', 'A大厦1号楼')).toBe(0.8)
    const rows = [normalizeTitleRow({ assetName: 'A大厦', location: '上海市浦东', bookArea: 1200 })]
    const hit = findBestTitleMatch(rows, { assetName: 'A大厦1号楼', location: '上海市浦东新区', bookArea: 1200 })
    expect(hit?.assetName).toBe('A大厦')
  })

  it('H3-2/H3-9 提取与导入', () => {
    const seeds = extractH32TitleSeeds(getValue, 'cost')
    expect(seeds).toHaveLength(2)
    expect(mapAssetTypeToCertName('土地')).toBe('土地使用权证')
    const rows = [normalizeTitleRow({ assetName: '已有', seq: 1 })]
    const r = importTitleRowsFromH32(rows, seeds, 'addNew')
    expect(r.added).toBe(2)
  })

  it('模糊匹配从 H3-9 补全', () => {
    const rows = [normalizeTitleRow({ assetName: 'A大厦', seq: 1 })]
    const seeds = extractH39TitleSeeds(getValue)
    const r = importTitleRowsFromH39(rows, seeds, 'fillEmpty')
    expect(r.updated).toBe(1)
    expect(rows[0].titleCertNo).toContain('沪房地')
  })

  it('parseL1PledgeRowsFromMap + syncMortgageFromL1', () => {
    const seeds = parseL1PledgeRowsFromMap([
      { item_id: 'L1-plg-1-assetName', remark: 'A大厦' },
      { item_id: 'L1-plg-1-bookValue', remark: '5000000' },
      { item_id: 'L1-plg-1-guaranteedLoan', remark: '3000000' },
      { item_id: 'L1-plg-1-ownershipVerified', remark: '已核验-权属清晰' },
    ])
    expect(seeds).toHaveLength(1)
    const rows = [normalizeTitleRow({ assetName: 'A大厦', seq: 1 })]
    const r = syncMortgageFromL1(rows, seeds)
    expect(r.updated).toBe(1)
    expect(rows[0].isRestricted).toBe('是')
    expect(rows[0].mortgageValue).toBe(3000000)
    expect(rows[0].refIndex).toBe('L1-8')
  })

  it('完整性勾稽', () => {
    const rows = extractH32TitleSeeds(getValue, 'cost').map((s, i) =>
      normalizeTitleRow({ ...s, seq: i + 1 }),
    )
    const checks = buildCompletenessChecks(rows, getValue, 'cost')
    expect(checks.find((c) => c.code === 'row-count')?.status).toBe('ok')
  })

  it('抽样覆盖', () => {
    const rows = [
      normalizeTitleRow({ assetName: 'A', bookValue: 800 }),
      normalizeTitleRow({ assetName: 'B', bookValue: 150 }),
      normalizeTitleRow({ assetName: 'C', bookValue: 50 }),
    ]
    const plan = applySamplePlan(rows, { targetCoverage: 0.8, minCount: 1 })
    expect(plan.sampledCount).toBeGreaterThanOrEqual(1)
    expect(rows.some((r) => r.sampled)).toBe(true)
  })

  it('预填证载面积 + 被审计单位默认', () => {
    const rows = [normalizeTitleRow({ assetName: 'A', bookArea: 100 })]
    expect(fillCertAreaFromBook(rows)).toBe(1)
    expect(rows[0].certArea).toBe(100)
    expect(rows[0].certAreaPending).toBe(true)
    expect(applyAuditeeDefaults(rows, '测试公司')).toBeGreaterThan(0)
    expect(rows[0].isAuditEntity).toBe('是')
  })

  it('附注受限文本', () => {
    const rows = [normalizeTitleRow({
      assetName: 'A大厦', isRestricted: '是', mortgageValue: 100, mortgageNature: '抵押',
    })]
    const text = buildRestrictionDisclosureText(rows)
    expect(text).toContain('来源:H3-12')
    expect(text).toContain('A大厦')
  })
})
