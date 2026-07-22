/**
 * H2 在建工程披露：附注映射 + 公式 + sync payload
 */
import { describe, expect, it } from 'vitest'
import {
  H2_NOTE_SECTION,
  H2_LISTED_SUBTABLE,
  H2_SOE_SUBTABLE,
  isH2CipNoteSection,
  resolveH2NoteSectionTarget,
} from '../h2NoteSectionMap'
import {
  createDefaultListedSummary,
  listedDetailNet,
  listedImpairmentEnd,
  listedMaterialsNet,
  listedProjectEnd,
  listedProjectSubtotal,
  listedSummaryTotal,
  mapDetailToListedProjects,
  createDefaultListedMaterials,
} from '../h2ListedDisclosureModel'
import {
  createDefaultSoeSummary,
  soeCarrying,
  soeProjectEnd,
  soeSummaryTotal,
} from '../h2SoeDisclosureModel'
import {
  buildH2ListedSyncPayloads,
  buildH2SoeSyncPayloads,
} from '../h2DisclosureSyncPayload'

describe('h2NoteSectionMap', () => {
  it('上市/国企映射到五、23 / 八、23', () => {
    expect(H2_NOTE_SECTION.listed).toBe('五、23')
    expect(H2_NOTE_SECTION.soe).toBe('八、23')
    expect(resolveH2NoteSectionTarget('listed', [])?.chipValue).toBe('Note:五、23')
    expect(resolveH2NoteSectionTarget('soe', ['soe_standalone'])?.chipValue).toBe('Note:八、23')
    expect(isH2CipNoteSection('五、23')).toBe(true)
    expect(isH2CipNoteSection('八、23')).toBe(true)
  })

  it('适用准则过滤', () => {
    expect(resolveH2NoteSectionTarget('listed', ['soe_standalone'])).toBeNull()
    expect(resolveH2NoteSectionTarget('soe', ['listed_standalone'])).toBeNull()
  })
})

describe('h2ListedDisclosureModel formulas', () => {
  it('汇总合计 / 净值 / 项目期末 / 减值期末', () => {
    const summary = createDefaultListedSummary()
    summary[0].endBalance = 100
    summary[1].endBalance = 20
    expect(listedSummaryTotal(summary).endBalance).toBe(120)
    expect(listedDetailNet(100, 15)).toBe(85)
    expect(listedProjectEnd({ beginBalance: 50, increase: 30, transferToFA: 10, otherDecrease: 5 })).toBe(65)
    expect(listedImpairmentEnd({ rowId: 'x', name: 'a', beginBalance: 10, provision: 5, decrease: 2 })).toBe(13)
  })

  it('工程物资净值扣减值', () => {
    const mats = createDefaultListedMaterials()
    mats[0].endBalance = 100
    mats[1].endBalance = 50
    mats[3].endBalance = 20
    expect(listedMaterialsNet(mats).endBalance).toBe(130)
  })

  it('H2-2 明细映射重要项目并合计', () => {
    const projects = mapDetailToListedProjects([
      { name: 'A厂', cipBegin: 10, increaseTotal: 5, transferAmount: 2, decrease: 1, budget: 100, accumulatedInput: 40 },
      { name: '', cipBegin: 99 },
    ])
    expect(projects).toHaveLength(1)
    expect(listedProjectEnd(projects[0])).toBe(12)
    expect(listedProjectSubtotal(projects).budget).toBe(100)
  })
})

describe('h2SoeDisclosureModel formulas', () => {
  it('账面价值与宽表期末', () => {
    expect(soeCarrying(200, 30)).toBe(170)
    const summary = createDefaultSoeSummary()
    summary[0].endBook = 200
    summary[0].endImpairment = 30
    expect(soeSummaryTotal(summary).endCarrying).toBe(170)
    expect(soeProjectEnd({ beginBalance: 10, increase: 20, transferToFA: 5, otherDecrease: 0 })).toBe(25)
  })
})

describe('h2DisclosureSyncPayload', () => {
  it('上市 sync 子表名对齐 note_template_listed', () => {
    const payloads = buildH2ListedSyncPayloads('wp-h2', [], {
      summary: createDefaultListedSummary(),
      detail: [{ rowId: '1', name: '车间改建', endBook: 100, endImpairment: 0, priorBook: 80, priorImpairment: 0 }],
      projects: [{
        rowId: 'p1', name: '车间改建', beginBalance: 80, increase: 30, transferToFA: 10, otherDecrease: 0,
        interestCapAccum: 1, interestCapCurrent: 1, interestCapRate: 3.5,
        budget: 200, cumInputPct: 50, accumulatedInput: 100, progress: '50%', fundSource: '自筹',
      }],
      impairment: [],
      materials: createDefaultListedMaterials(),
      mortgage: [{ rowId: 'm1', name: '车间改建', amount: 100, description: '抵押', remark: '' }],
      noteImpairment: '已测试',
      noteFundSource: '',
      noteMortgage: '车间改建已抵押',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('五、23')
    const data = payloads[0].sub_table_data
    expect(data[H2_LISTED_SUBTABLE.summary]).toBeTruthy()
    expect(data[H2_LISTED_SUBTABLE.detail]?.some((r) => r.label === '车间改建')).toBe(true)
    expect(data[H2_LISTED_SUBTABLE.projectMovement]?.find((r) => r.is_total)?.end_balance).toBe(100)
    expect(data[H2_LISTED_SUBTABLE.projectCont]?.[0]?.fund_source).toBe('自筹')
    expect(data[H2_LISTED_SUBTABLE.restricted]?.some((r) => r.label === '车间改建')).toBe(true)
  })

  it('国企 sync 子表名对齐 note_template_soe', () => {
    const payloads = buildH2SoeSyncPayloads('wp-h2', [], {
      summary: createDefaultSoeSummary(),
      detail: [],
      projects: [{
        rowId: 'p1', name: '码头', beginBalance: 0, increase: 50, transferToFA: 0, otherDecrease: 0,
        interestCapAccum: 0, interestCapCurrent: 0, interestCapRate: 0,
        budget: 100, cumInputPct: 50, accumulatedInput: 50, progress: '在建', fundSource: '贷款',
      }],
      impairment: [{ rowId: 'i1', name: '码头', provisionAmount: 5, reason: '停工' }],
      noteImpairment: '',
    })
    expect(payloads[0].section_id).toBe('八、23')
    const data = payloads[0].sub_table_data
    expect(data[H2_SOE_SUBTABLE.projectMovement]?.[0]?.fund_source).toBe('贷款')
    expect(data[H2_SOE_SUBTABLE.impairment]?.find((r) => r.label === '码头')?.provision_amount).toBe(5)
  })
})
