/**
 * I1 披露模型 / sync payload / 附注跳转
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  I1_NOTE_SECTION,
  isI1IntangibleNoteSection,
  isI1DisclosureApplicable,
} from '../i1NoteSectionMap'
import {
  I1_LISTED_DEFAULT_CATEGORIES,
  I1_LISTED_MOVEMENT_ROWS,
  i1ListedCellValue,
  i1ListedTotalCellValue,
  mapToI1ListedCategoryKey,
  setCell,
} from '../i1ListedDisclosureModel'
import {
  createDefaultI1SoeLayers,
  layerTotal,
  mapToI1SoeCategoryKey,
  recomputeI1SoeDerivedLayers,
} from '../i1SoeDisclosureModel'
import {
  buildI1ListedSyncPayloads,
  buildI1SoeSyncPayloads,
} from '../i1DisclosureSyncPayload'
import { useI1ListedDisclosure } from '../useI1Disclosure'
import {
  isI1IntangibleNoteSection as jumpIsI1,
  resolveNoteDisclosureJumpTarget,
} from '@/views/composables/noteDisclosureJump'

describe('i1NoteSectionMap', () => {
  it('上市/国企映射到五、26 / 八、27', () => {
    expect(I1_NOTE_SECTION.listed).toBe('五、26')
    expect(I1_NOTE_SECTION.soe).toBe('八、27')
    expect(isI1IntangibleNoteSection('五、26')).toBe(true)
    expect(isI1IntangibleNoteSection('无形资产')).toBe(true)
    expect(isI1DisclosureApplicable('listed', ['listed_standalone'])).toBe(true)
    expect(isI1DisclosureApplicable('listed', ['soe_standalone'])).toBe(false)
  })
})

describe('i1ListedDisclosureModel', () => {
  it('期末/账面价值公式 + 分类映射', () => {
    expect(mapToI1ListedCategoryKey('软件许可')).toBe('software')
    expect(mapToI1ListedCategoryKey('土地使用权')).toBe('land')
    let map = {}
    map = setCell(map, 'cost_begin', 'software', 1000)
    map = setCell(map, 'cost_inc_purchase', 'software', 200)
    map = setCell(map, 'cost_dec_dispose', 'software', 50)
    map = setCell(map, 'amort_begin', 'software', 100)
    map = setCell(map, 'amort_inc_provision', 'software', 40)
    map = setCell(map, 'imp_begin', 'software', 10)
    const costEnd = I1_LISTED_MOVEMENT_ROWS.find((r) => r.key === 'cost_end')!
    const bookEnd = I1_LISTED_MOVEMENT_ROWS.find((r) => r.key === 'book_end')!
    expect(i1ListedCellValue(map, costEnd, 'software')).toBe(1150)
    // 账面 = 1150 - 140 - 10 = 1000
    expect(i1ListedCellValue(map, bookEnd, 'software')).toBe(1000)
    expect(i1ListedTotalCellValue(map, costEnd, I1_LISTED_DEFAULT_CATEGORIES)).toBe(1150)
  })
})

describe('i1SoeDisclosureModel', () => {
  it('账面价值 = 原价 − 摊销 − 减值', () => {
    expect(mapToI1SoeCategoryKey('软件')).toBe('software')
    const layers = createDefaultI1SoeLayers()
    const cost = layers.find((l) => l.layer === 'cost')!
    const amort = layers.find((l) => l.layer === 'amort')!
    const impair = layers.find((l) => l.layer === 'impair')!
    const soft = (arr: typeof cost.categories) => arr.find((c) => c.key === 'software')!
    soft(cost.categories).begin = 1000
    soft(cost.categories).increase = 100
    soft(amort.categories).begin = 200
    soft(amort.categories).increase = 50
    soft(impair.categories).begin = 30
    const next = recomputeI1SoeDerivedLayers(layers)
    const carrying = next.find((l) => l.layer === 'carrying')!
    const c = soft(carrying.categories)
    // begin 1000-200-30=770; end (1100)-(250)-(30)=820
    expect(c.begin).toBe(770)
    expect(c.end).toBe(820)
    expect(layerTotal(cost).end).toBe(1100)
  })
})

describe('i1DisclosureSyncPayload', () => {
  it('上市 payload 含无形资产情况 + 五、26', () => {
    let map = {}
    map = setCell(map, 'cost_begin', 'software', 100)
    const payloads = buildI1ListedSyncPayloads('wp-i1', ['listed_standalone'], {
      categories: [...I1_LISTED_DEFAULT_CATEGORIES],
      movement: map,
      noteRdRatio: '研发占比10%',
      noteIndefinite: '',
      noteMortgage: '',
      noteImpairment: '',
      noteSale: '',
      noteImportant: '',
      titleCertRows: [],
      importantRows: [],
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('五、26')
    expect(payloads[0].sub_table_data['无形资产情况']?.length).toBeGreaterThan(10)
    const texts = payloads[0].sub_table_data._note_texts as any[]
    expect(texts.some((t) => t.section === 'listed-rd-ratio' && t.text.includes('10%'))).toBe(true)
  })

  it('国企 payload 含八、27', () => {
    const layers = recomputeI1SoeDerivedLayers(createDefaultI1SoeLayers())
    const payloads = buildI1SoeSyncPayloads('wp-i1', ['soe_standalone'], {
      layers,
      noteIndefinite: '寿命不确定依据',
      noteMortgage: '',
      noteValuation: '',
      noteImpairment: '',
      noteNotReady: '',
      noteSale: '',
      noteTitle: '',
    })
    expect(payloads[0].section_id).toBe('八、27')
    expect(payloads[0].sub_table_data['无形资产情况']?.some((r) => r.is_total)).toBe(true)
  })
})

describe('useI1ListedDisclosure pullFromSources', () => {
  it('从 I1-2-rows 按分类汇总', () => {
    const map = new Map<string, any>([
      ['I1-2-rows', {
        remark: JSON.stringify([
          {
            name: 'ERP软件',
            category: '软件',
            costBegin: 1000,
            costIncrease: 200,
            costIncreaseMethod: '购置',
            costDecrease: 0,
            accAmortBegin: 100,
            amortProvision: 50,
            impairmentBegin: 0,
            impairmentProvision: 0,
          },
        ]),
      }],
    ])
    const allResponses = ref(map)
    const saved: Record<string, any> = {}
    const { pullFromSources, movement } = useI1ListedDisclosure({
      allResponses,
      onSave: (id, v) => { saved[id] = v },
    })
    const res = pullFromSources()
    expect(res.count).toBe(1)
    expect(movement.value.cost_begin?.software).toBe(1000)
    expect(movement.value.cost_inc_purchase?.software).toBe(200)
    expect(movement.value.amort_inc_provision?.software).toBe(50)
  })
})

describe('noteDisclosureJump I1', () => {
  it('五、26 / 八、27 跳转到 I1 披露表', () => {
    expect(jumpIsI1('五、26')).toBe(true)
    const listed = resolveNoteDisclosureJumpTarget({
      note_section: '五、26',
      table_data: { _current_standard: 'listed_standalone' },
    })
    expect(listed?.wpCode).toBe('I1')
    expect(listed?.variant).toBe('listed')
    const soe = resolveNoteDisclosureJumpTarget({
      note_section: '八、27',
      table_data: { _current_standard: 'soe_standalone' },
    })
    expect(soe?.wpCode).toBe('I1')
    expect(soe?.variant).toBe('soe')
  })
})
