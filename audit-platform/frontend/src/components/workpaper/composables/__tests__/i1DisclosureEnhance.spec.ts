/**
 * I1 披露增强 + sync + 取数策略
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  preferAuditedAmount,
  buildI1ListedCrossCheck,
  validateI1ListedPrep,
  fillNoteIfEmpty,
  draftImpairmentNoteFromI112,
  draftSaleNoteFromI16,
  aggregateI19AmortAlloc,
  buildDataResourceSubTableRows,
  emptyDataResourceMove,
} from '../i1DisclosureEnhance'
import {
  I1_LISTED_DEFAULT_CATEGORIES,
  setCell,
} from '../i1ListedDisclosureModel'
import { buildI1ListedSyncPayloads } from '../i1DisclosureSyncPayload'
import { useI1ListedDisclosure } from '../useI1Disclosure'
import { I1_NOTE_SECTION } from '../i1NoteSectionMap'

describe('preferAuditedAmount', () => {
  it('审定为 0 时不回退未审', () => {
    expect(preferAuditedAmount({ auditedCostBegin: 0, costBegin: 100 }, 'auditedCostBegin', 'costBegin')).toBe(0)
    expect(preferAuditedAmount({ costBegin: 100 }, 'auditedCostBegin', 'costBegin')).toBe(100)
  })
})

describe('crossCheck / prep', () => {
  it('与审定差异告警', () => {
    let map = {}
    map = setCell(map, 'cost_begin', 'software', 1000)
    const cross = buildI1ListedCrossCheck(map, I1_LISTED_DEFAULT_CATEGORIES, {
      cost: 900,
      amort: 0,
      impair: 0,
    })
    expect(cross.hasCostWarning).toBe(true)
    expect(Math.abs(cross.costDiff - 100) < 0.01).toBe(true)
  })

  it('账面价值为负阻断', () => {
    let map = {}
    map = setCell(map, 'cost_begin', 'software', 100)
    map = setCell(map, 'amort_begin', 'software', 200)
    const v = validateI1ListedPrep({
      movement: map,
      categories: I1_LISTED_DEFAULT_CATEGORIES,
      titleCertRows: [{ name: '土地A', bookValue: 1, reason: '' }],
    })
    expect(v.ok).toBe(false)
    expect(v.blocking.some((m) => m.includes('负'))).toBe(true)
    expect(v.warnings.some((m) => m.includes('未填原因'))).toBe(true)
  })
})

describe('drafts', () => {
  it('fillNoteIfEmpty 保留已填', () => {
    expect(fillNoteIfEmpty('已有', '草稿')).toBe('已有')
    expect(fillNoteIfEmpty('', '草稿')).toBe('草稿')
  })

  it('I1-12 / I1-6 草稿', () => {
    const imp = draftImpairmentNoteFromI112([
      { name: '专利', needTest: 'Y', supplement: 10, alreadyProvided: 5, impairmentAmount: 15, hasIndication: 'Y' },
    ])
    expect(imp).toContain('I1-12')
    expect(imp).toContain('补提')
    const sale = draftSaleNoteFromI16([
      { name: '软件', disposalGainLoss: 200000, netBookValue: 100000, disposalIncome: 300000, salePriceFair: 'N' },
    ])
    expect(sale).toContain('I1-6')
  })

  it('I1-9 摊销归属合计', () => {
    const a = aggregateI19AmortAlloc([
      { productionCost: 10, manufacturingExpense: 5, sellingExpense: 3, managementExpense: 20, rdExpense: 7, otherExpense: 1 },
    ])
    expect(a.total).toBe(46)
  })
})

describe('data resource + sync', () => {
  it('数据资源子表进 payload', () => {
    const dr = { ...emptyDataResourceMove(), costBegin: 50, costIncRd: 20 }
    const payloads = buildI1ListedSyncPayloads('wp', ['listed_standalone'], {
      categories: [...I1_LISTED_DEFAULT_CATEGORIES],
      movement: {},
      noteRdRatio: '',
      noteIndefinite: '',
      noteMortgage: '',
      noteImpairment: '',
      noteSale: '',
      noteImportant: '',
      titleCertRows: [],
      importantRows: [],
      dataResource: dr,
      noteDataResource: '数据资源说明',
      amortAlloc: { productionCost: 1, manufacturing: 0, selling: 0, management: 2, rd: 0, other: 0, total: 3 },
    })
    expect(payloads[0].section_id).toBe(I1_NOTE_SECTION.listed)
    expect(payloads[0].sub_table_data['确认为无形资产的数据资源']?.length).toBeGreaterThan(5)
    expect(payloads[0].sub_table_data['本期摊销费用归属']?.[0].合计).toBe(3)
    expect(buildDataResourceSubTableRows(dr).some((r) => r.label === '4.期末余额')).toBe(true)
  })
})

describe('pull preserve notes', () => {
  it('二次取数保留已填减值说明', () => {
    const map = new Map<string, any>([
      ['I1-2-rows', {
        remark: JSON.stringify([
          {
            name: 'ERP',
            category: '软件',
            auditedCostBegin: 0,
            costBegin: 1000,
            costIncrease: 0,
            costDecrease: 0,
            accAmortBegin: 0,
            amortProvision: 0,
          },
        ]),
      }],
      ['I1-listed-note-impairment', { remark: '手工已填减值说明，勿覆盖' }],
    ])
    const allResponses = ref(map)
    const { pullFromSources, noteImpairment, movement } = useI1ListedDisclosure({
      allResponses,
      onSave: () => {},
    })
    // hydrate note from map via load - need to set after load
    noteImpairment.value = '手工已填减值说明，勿覆盖'
    pullFromSources({ overwriteNotes: false })
    expect(noteImpairment.value).toBe('手工已填减值说明，勿覆盖')
    // auditedCostBegin=0 应取 0 而非 1000
    expect(movement.value.cost_begin?.software).toBe(0)
  })
})
