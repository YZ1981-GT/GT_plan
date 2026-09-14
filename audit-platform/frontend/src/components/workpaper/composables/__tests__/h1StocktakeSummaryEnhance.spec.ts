/**
 * H1-11 增强逻辑单测：闸门 / 起草 / 推送 / 覆盖率对照
 */
import { describe, expect, it } from 'vitest'
import { createEmptySummaryForm } from '../h1StocktakeSummaryModel'
import {
  applyAutoSyncPatch,
  buildDiffEvidence,
  calcSamplePlanGap,
  collectConcernsFromCheck,
  draftConclusionRule,
  evaluateCompleteness,
  fingerprintCheckRows,
  mergeBuildingFromOcr,
  mergeDiffIntoAbnormal,
  mergeIdleRowsFromConcerns,
} from '../h1StocktakeSummaryEnhance'

describe('h1StocktakeSummaryEnhance', () => {
  it('applyAutoSyncPatch respects overrides', () => {
    const f = createEmptySummaryForm()
    f.recountTotalUnits = 10
    f.manualOverrides = ['recountTotalUnits']
    applyAutoSyncPatch(f, { recountTotalUnits: 99, recountSampleUnits: 5 }, f.manualOverrides)
    expect(f.recountTotalUnits).toBe(10)
    expect(f.recountSampleUnits).toBe(5)
  })

  it('evaluateCompleteness flags incomplete precheck', () => {
    const f = createEmptySummaryForm()
    const items = evaluateCompleteness({
      form: f,
      matchRate: 100,
      deficitRows: [],
      checkTotal: 0,
    })
    expect(items.find((i) => i.id === 'precheck')?.ok).toBe(false)
    expect(items.find((i) => i.id === 'conclusion')?.ok).toBe(false)
  })

  it('calcSamplePlanGap detects shortfall', () => {
    const g = calcSamplePlanGap([{ sampleSize: 20 }], 12)
    expect(g.ok).toBe(false)
    expect(g.gap).toBe(8)
  })

  it('mergeDiffIntoAbnormal replaces synced block', () => {
    const diffs = buildDiffEvidence([
      {
        rowId: '1', name: '机床', assetNo: 'A1', result: '盘亏', diffAmount: 100,
        diffReason: '丢失', actualStatus: '在用', photoUrl: '', suggestion: '',
      },
    ])
    const once = mergeDiffIntoAbnormal('', diffs)
    const twice = mergeDiffIntoAbnormal(once + '\n人工补充', diffs)
    expect(twice.match(/【自 H1-10 同步的差异\/异常】/g)?.length).toBe(1)
    expect(twice).toContain('机床')
    expect(twice).toContain('人工补充')
  })

  it('collectConcerns + mergeIdleRowsFromConcerns', () => {
    const concerns = collectConcernsFromCheck([
      {
        rowId: 'r1', name: '旧车床', assetNo: 'C1', actualStatus: '闲置', result: '账实相符',
        bookNetValue: 1000, bookCost: 5000, diffReason: '', suggestion: '',
      },
    ])
    expect(concerns).toHaveLength(1)
    const { rows, added } = mergeIdleRowsFromConcerns([], concerns, [
      { rowId: 'r1', name: '旧车床', assetNo: 'C1', bookCost: 5000, bookNetValue: 1000 },
    ])
    expect(added).toBe(1)
    expect(rows[0].remark).toContain('H1-11')
  })

  it('mergeBuildingFromOcr adds then updates', () => {
    const a = mergeBuildingFromOcr([], { titleCertNo: '粤(2020)1号', address: '广州路1号', buildingArea: 120 })
    expect(a.mode).toBe('add')
    const b = mergeBuildingFromOcr(a.rows, { titleCertNo: '粤(2020)1号', owner: '甲公司' })
    expect(b.mode).toBe('update')
    expect(b.rows[0].owner).toBe('甲公司')
  })

  it('draftConclusionRule mentions match rate', () => {
    const text = draftConclusionRule({
      total: 10,
      matchCount: 9,
      matchRate: 90,
      surplusCount: 0,
      deficitCount: 1,
      surplusAmount: 0,
      deficitAmount: 50,
      form: createEmptySummaryForm(),
      sampleGap: calcSamplePlanGap([{ sampleSize: 10 }], 10),
    })
    expect(text).toContain('90')
    expect(text).toContain('盘亏')
  })

  it('fingerprint changes when result changes', () => {
    const a = fingerprintCheckRows([{ rowId: '1', result: '账实相符', diffAmount: 0, actualStatus: '在用', bookNetValue: 1 }])
    const b = fingerprintCheckRows([{ rowId: '1', result: '盘亏', diffAmount: 10, actualStatus: '在用', bookNetValue: 1 }])
    expect(a).not.toBe(b)
  })
})
