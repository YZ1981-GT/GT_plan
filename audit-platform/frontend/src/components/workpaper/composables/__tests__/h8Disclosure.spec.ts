/**
 * H8 披露模型 / sync payload / 附注跳转
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  H8_NOTE_SECTION,
  isH8RouNoteSection,
  isH8DisclosureApplicable,
} from '../h8NoteSectionMap'
import {
  H8_LISTED_DEFAULT_CATEGORIES,
  H8_LISTED_MOVEMENT_ROWS,
  h8ListedCellValue,
  h8ListedTotalCellValue,
  mapToListedCategoryKey,
  setCell,
} from '../h8ListedDisclosureModel'
import {
  createDefaultSoeLayers,
  layerTotal,
  mapToSoeCategoryKey,
  recomputeDerivedLayers,
} from '../h8SoeDisclosureModel'
import {
  buildH8ListedSyncPayloads,
  buildH8SoeSyncPayloads,
} from '../h8DisclosureSyncPayload'
import { useH8ListedDisclosure, aggregateH810ImpairmentByCategory } from '../useH8Disclosure'
import {
  isH8RouNoteSection as jumpIsH8,
  resolveNoteDisclosureJumpTarget,
} from '@/views/composables/noteDisclosureJump'

describe('h8NoteSectionMap', () => {
  it('上市/国企映射到五、25 / 八、26', () => {
    expect(H8_NOTE_SECTION.listed).toBe('五、25')
    expect(H8_NOTE_SECTION.soe).toBe('八、26')
    expect(isH8RouNoteSection('五、25')).toBe(true)
    expect(isH8RouNoteSection('使用权资产')).toBe(true)
    expect(isH8DisclosureApplicable('listed', ['listed_standalone'])).toBe(true)
    expect(isH8DisclosureApplicable('listed', ['soe_standalone'])).toBe(false)
  })
})

describe('h8ListedDisclosureModel', () => {
  it('期末/账面价值公式', () => {
    let map = {}
    map = setCell(map, 'cost_begin', 'buildings', 100)
    map = setCell(map, 'cost_inc_lease', 'buildings', 40)
    map = setCell(map, 'cost_dec_other', 'buildings', 10)
    map = setCell(map, 'dep_begin', 'buildings', 20)
    map = setCell(map, 'dep_inc_provision', 'buildings', 5)
    map = setCell(map, 'imp_begin', 'buildings', 0)

    const costEnd = H8_LISTED_MOVEMENT_ROWS.find((r) => r.key === 'cost_end')!
    const bookEnd = H8_LISTED_MOVEMENT_ROWS.find((r) => r.key === 'book_end')!
    expect(h8ListedCellValue(map, costEnd, 'buildings')).toBe(130)
    // 账面价值 = 130 - 25 - 0
    expect(h8ListedCellValue(map, bookEnd, 'buildings')).toBe(105)
    expect(h8ListedTotalCellValue(map, costEnd, [...H8_LISTED_DEFAULT_CATEGORIES])).toBe(130)
    expect(mapToListedCategoryKey('房屋租赁')).toBe('buildings')
  })
})

describe('h8SoeDisclosureModel', () => {
  it('净值/账面价值自动推导', () => {
    const layers = createDefaultSoeLayers()
    const cost = layers.find((l) => l.layer === 'cost')!
    const dep = layers.find((l) => l.layer === 'dep')!
    const building = cost.categories.find((c) => c.key === 'building')!
    building.begin = 200
    building.increase = 50
    building.decrease = 0
    const dBuilding = dep.categories.find((c) => c.key === 'building')!
    dBuilding.begin = 30
    dBuilding.increase = 10
    const next = recomputeDerivedLayers(layers)
    const net = next.find((l) => l.layer === 'net')!
    const carrying = next.find((l) => l.layer === 'carrying')!
    const n = net.categories.find((c) => c.key === 'building')!
    expect(n.begin).toBe(170)
    expect(n.end).toBe(210) // 250 - 40
    expect(layerTotal(carrying).end).toBe(n.end)
    expect(mapToSoeCategoryKey('土地使用权')).toBe('land')
  })
})

describe('h8DisclosureSyncPayload', () => {
  it('buildH8ListedSyncPayloads 目标五、25', () => {
    const payloads = buildH8ListedSyncPayloads('wp-h8', ['listed_standalone'], {
      categories: [...H8_LISTED_DEFAULT_CATEGORIES],
      movement: setCell({}, 'cost_begin', 'buildings', 1),
      noteShortLow: '短期费用说明',
      noteImpairment: '',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('五、25')
    expect(payloads[0].sub_table_data['使用权资产']?.length).toBeGreaterThan(10)
  })

  it('buildH8SoeSyncPayloads 目标八、26', () => {
    const payloads = buildH8SoeSyncPayloads('wp-h8', ['soe_standalone'], {
      layers: createDefaultSoeLayers(),
      noteImpairment: '',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('八、26')
    expect(payloads[0].sheet_name).toContain('国企')
  })
})

describe('useH8ListedDisclosure pull', () => {
  it('从 H8-2 按类别带入', () => {
    const allResponses = ref(new Map([
      ['H8-2-rows', {
        remark: JSON.stringify([
          { contractNo: 'A', leaseType: '房屋', initialAmount: 100, beginCost: 0, accDepBegin: 0, depCurrentPeriod: 10, accDepEnd: 10 },
          { contractNo: 'B', leaseType: '车辆', initialAmount: 50, beginCost: 0, accDepBegin: 0, depCurrentPeriod: 5, accDepEnd: 5 },
        ]),
      }],
    ]))
    const saved: any[] = []
    const api = useH8ListedDisclosure({
      allResponses,
      onSave: (id, v) => saved.push({ id, v }),
    })
    const res = api.pullFromSources()
    expect(res.message).toContain('带入')
    expect(api.movement.value.cost_inc_lease?.buildings).toBe(100)
    expect(api.movement.value.cost_inc_lease?.transport).toBe(50)
    expect(saved.length).toBeGreaterThan(0)
  })

  it('从 H8-10 减值明细填减值期初/本期计提 + 说明草稿', () => {
    const allResponses = ref(new Map([
      ['H8-10-rows', {
        remark: JSON.stringify([
          {
            assetName: '办公楼使用权',
            contractNo: 'ZL-1',
            hasIndication: 'Y',
            indicationDesc: '租金下行',
            alreadyProvided: 20,
            impairmentAmount: 50,
            supplement: 30,
          },
          {
            assetName: '货车租赁',
            contractNo: 'ZL-2',
            hasIndication: 'N',
            alreadyProvided: 0,
            impairmentAmount: 0,
            supplement: 0,
          },
        ]),
      }],
    ]))
    const api = useH8ListedDisclosure({
      allResponses,
      onSave: () => {},
    })
    const res = api.pullFromSources()
    expect(res.message).toContain('H8-10')
    expect(api.movement.value.imp_begin?.buildings).toBe(20)
    expect(api.movement.value.imp_inc_provision?.buildings).toBe(30)
    expect(api.noteImpairment.value).toContain('H8-10')
    expect(api.noteImpairment.value).toContain('租金下行')
  })
})

describe('aggregateH810ImpairmentByCategory', () => {
  it('⑧优先；无⑧时用⑥−⑦', () => {
    const { byCat, noteDraft } = aggregateH810ImpairmentByCategory(
      [
        { assetName: '机器A', alreadyProvided: 10, impairmentAmount: 25, supplement: 0, hasIndication: 'Y' },
      ],
      mapToListedCategoryKey,
    )
    expect(byCat.machinery.begin).toBe(10)
    expect(byCat.machinery.provision).toBe(15)
    expect(noteDraft).toContain('补提')
  })
})

describe('noteDisclosureJump H8', () => {
  it('五、25 / 八、26 跳转 H8 披露表', () => {
    expect(jumpIsH8('五、25')).toBe(true)
    const listed = resolveNoteDisclosureJumpTarget({ note_section: '五、25' })
    expect(listed?.wpCode).toBe('H8')
    expect(listed?.variant).toBe('listed')
    const soe = resolveNoteDisclosureJumpTarget({ note_section: '八、26' })
    expect(soe?.wpCode).toBe('H8')
    expect(soe?.variant).toBe('soe')
    expect(soe?.sheet).toContain('国企')
  })
})
