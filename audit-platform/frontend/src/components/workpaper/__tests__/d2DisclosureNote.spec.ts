import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useD2DisclosureNote } from '../composables/useD2DisclosureNote'
import { buildD2SyncPayload, D2_TABLE_NAMES } from '../composables/d2NoteSectionMap'
import type { ChecklistResponse } from '../composables/useD2FormData'

function resp(itemId: string, remark: string): [string, ChecklistResponse] {
  return [itemId, { item_id: itemId, conclusion: null, remark }]
}

/** D2-3 分类固定行（仅小计行参与自动取数） */
function badDebtFixed(values: Partial<Record<string, number>>): string {
  return JSON.stringify([
    {
      rowId: 'fixed-x', isFixed: true, isSubRow: false, label: '小计',
      priorAudited: 0, currentAudited: 0, currentProvision: 0, currentReversal: 0,
      currentWriteOff: 0, currentOtherIncrease: 0, currentOtherDecrease: 0,
      ...values,
    },
  ])
}

interface SetupOptions {
  variant?: 'listed' | 'soe'
  entries?: Array<[string, ChecklistResponse]>
}

function setup(opts: SetupOptions = {}) {
  const save = vi.fn()
  const allResponses = ref(new Map<string, ChecklistResponse>(opts.entries ?? []))
  const api = useD2DisclosureNote({
    allResponses,
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    variant: opts.variant ?? 'listed',
    save,
    isReadonly: ref(false),
  })
  return { api, save, allResponses }
}

const NESTED_DETAIL = JSON.stringify([
  {
    rowId: 'r1', customerName: 'A公司',
    agingAudited: { within1: 600, y1to2: 200 },
    agingPrior: { within1: 400, y1to2: 100 },
  },
  {
    rowId: 'r2', customerName: 'B公司',
    agingAudited: { within1: 400, y2to3: 100 },
    agingPrior: { within1: 300 },
  },
])

const LEGACY_DETAIL = JSON.stringify([
  { rowId: 'r1', auditedAging1Year: 500, auditedAging1to2: 250, priorAging1Year: 300 },
])

describe('useD2DisclosureNote — 账龄披露', () => {
  it('账龄行 = 动态账龄段 + 小计/减：坏账准备/合计 三结构行（1年以内未细分时无小计）', () => {
    const { api } = setup()
    const rows = api.agingRows.value
    const segs = api.agingSegments.value
    expect(segs.length).toBeGreaterThan(0)
    // 默认 5 年段：1年以内只有一段 → 「1年以内小计」恒等于该段，源模板国企版无此行
    expect(segs.filter((s) => s.dayFrom < 366)).toHaveLength(1)
    expect(rows).toHaveLength(segs.length + 3)
    expect(rows.some((r) => r.kind === 'within1Subtotal')).toBe(false)
    expect(rows.slice(-3).map((r) => r.label)).toEqual(['小计', '减：坏账准备', '合计'])
    expect(rows.slice(-3).map((r) => r.kind)).toEqual(['subtotal', 'badDebt', 'total'])
  })

  it('账龄金额自动取自 D2-2 明细 nested 账龄；小计/合计按公式派生', () => {
    const { api } = setup({
      entries: [
        resp('D2-detail-rows', NESTED_DETAIL),
        resp('D2-bd-individual-rows', badDebtFixed({ currentAudited: 130, priorAudited: 100 })),
      ],
    })
    const rows = api.agingRows.value
    const byLabel = (label: string) => rows.find((r) => r.label === label)!
    expect(byLabel('1年以内').endAmount).toBe(1000)
    expect(byLabel('1年以内').priorAmount).toBe(700)
    expect(byLabel('1-2年').endAmount).toBe(200)
    expect(byLabel('2-3年').endAmount).toBe(100)
    // 1年以内小计 = 1年以内段之和
    // 小计 = 各账龄段之和
    expect(byLabel('小计').endAmount).toBe(1300)
    // 坏账准备取自 D2-3
    expect(byLabel('减：坏账准备').endAmount).toBe(130)
    expect(byLabel('减：坏账准备').endAuto).toBe(true)
    // 合计 = 小计 − 坏账准备
    expect(byLabel('合计').endAmount).toBe(1170)
    // 期初：小计 800（within1 700 + y1to2 100）− 坏账 100
    expect(byLabel('小计').priorAmount).toBe(800)
    expect(byLabel('合计').priorAmount).toBe(700)
    expect(api.detailAgingHasData.value).toBe(true)
  })

  it('兼容 legacy 扁平账龄字段（迁移前 D2-detail-rows）', () => {
    const { api } = setup({ entries: [resp('D2-detail-rows', LEGACY_DETAIL)] })
    const rows = api.agingRows.value
    expect(rows.find((r) => r.label === '1年以内')!.endAmount).toBe(500)
    expect(rows.find((r) => r.label === '1-2年')!.endAmount).toBe(250)
    expect(rows.find((r) => r.label === '小计')!.endAmount).toBe(750)
  })

  it('手工覆盖优先于自动取数，恢复取数后回到自动值', () => {
    const { api, save } = setup({ entries: [resp('D2-detail-rows', NESTED_DETAIL)] })
    const within1 = () => api.agingRows.value.find((r) => r.label === '1年以内')!
    expect(within1().endAmount).toBe(1000)

    api.setOverride('aging:end:within1', 1234)
    expect(within1().endAmount).toBe(1234)
    expect(within1().endAuto).toBe(false)
    expect(api.agingRows.value.find((r) => r.label === '小计')!.endAmount).toBe(1234 + 200 + 100)
    expect(save).toHaveBeenCalled()

    api.resetOverride('aging:end:within1')
    expect(within1().endAmount).toBe(1000)
    expect(within1().endAuto).toBe(true)
  })
})

describe('useD2DisclosureNote — 分类披露与组合', () => {
  it('分类行自动取自 D2-1 审定表，合计 = 单项 + 组合', () => {
    const { api } = setup({
      entries: [
        resp('D2-adj-individual-current-unadjusted', '500'),
        resp('D2-adj-individual-prior-unadjusted', '400'),
        resp('D2-adj-aging-current-unadjusted', '600'),
        resp('D2-adj-customer-type-current-unadjusted', '200'),
      ],
    })
    const rows = api.classRows.value
    const individual = rows.find((r) => r.key === 'individual')!
    const portfolio = rows.find((r) => r.key === 'portfolio')!
    const total = rows.find((r) => r.kind === 'total')!
    expect(individual.endAmount).toBe(500)
    expect(individual.priorAmount).toBe(400)
    expect(portfolio.endAmount).toBe(800)
    expect(total.endAmount).toBe(1300)
    // 提示行「其中：」存在且不可编辑
    expect(rows.filter((r) => r.kind === 'hint')).toHaveLength(2)
    expect(rows.every((r) => (r.kind === 'hint' ? !r.editable : true))).toBe(true)
  })

  it('组合分表按账龄段生成行，分类表出现该组合明细行（金额=组合各段之和）', () => {
    const { api } = setup()
    api.addPortfolio('应收中央企业客户')
    const group = api.portfolios.value[0]
    expect(group.rows.map((r) => r.label)).toEqual(api.agingSegments.value.map((s) => s.label))

    api.updatePortfolioCell(group.groupId, 'within1', 'endAmount', 600)
    api.updatePortfolioCell(group.groupId, 'y1to2', 'endAmount', 200)
    const detail = api.classRows.value.find((r) => r.label === '应收中央企业客户')!
    expect(detail.kind).toBe('detail')
    expect(detail.endAmount).toBe(800)
  })

  it('单项计提明细行进入分类表「其中：」之后，并可从 D2-3 带入', () => {
    const { api } = setup({
      entries: [
        resp('D2-bd-individual-rows', JSON.stringify([
          { rowId: 'fixed-individual', isFixed: true, label: '按单项计提小计', currentAudited: 50 },
          { rowId: 's1', isSubRow: true, label: 'A公司', currentAudited: 30 },
          { rowId: 's2', isSubRow: true, label: 'B公司', currentAudited: 20 },
        ])),
      ],
    })
    const added = api.importIndividualFromBadDebt()
    expect(added).toBe(2)
    expect(api.individualRows.value.map((r) => r.name)).toEqual(['A公司', 'B公司'])
    expect(api.individualRows.value[0].provision).toBe(30)
    // 幂等：重复带入不产生重复行
    expect(api.importIndividualFromBadDebt()).toBe(0)
    expect(api.individualRows.value).toHaveLength(2)
    const labels = api.classRows.value.map((r) => r.label)
    expect(labels.indexOf('A公司')).toBeGreaterThan(labels.indexOf('其中：'))
  })
})

describe('useD2DisclosureNote — 坏账准备变动', () => {
  it('上市纵向 7 行自动取自 D2-3，期末 = 期初+计提−转回−核销−转销+其他', () => {
    const { api } = setup({
      entries: [
        resp('D2-bd-aging-rows', badDebtFixed({
          priorAudited: 100, currentProvision: 40, currentReversal: 5,
          currentWriteOff: 3, currentOtherIncrease: 4, currentOtherDecrease: 1,
        })),
      ],
    })
    const f = (key: string) => api.movementFields.value.find((x) => x.key === key)!
    expect(f('priorBalance').amount).toBe(100)
    expect(f('provision').amount).toBe(40)
    expect(f('reversal').amount).toBe(5)
    expect(f('writeOff').amount).toBe(3)
    expect(f('other').amount).toBe(3) // 4 − 1
    expect(f('transfer').amount).toBe(0)
    // 100 + 40 − 5 − 3 − 0 + 3
    expect(api.movementEndBalance.value).toBe(135)

    api.setOverride('movement:transfer', 5)
    expect(api.movementEndBalance.value).toBe(130)
  })

  it('国企按类别变动：期初/计提/收回或转回/转销或核销/期末 五列，合计为各类别之和', () => {
    const { api } = setup({
      variant: 'soe',
      entries: [
        resp('D2-bd-individual-rows', badDebtFixed({
          priorAudited: 60, currentAudited: 70,
          currentProvision: 14, currentReversal: 3, currentWriteOff: 1,
        })),
        resp('D2-bd-aging-rows', badDebtFixed({
          priorAudited: 40, currentAudited: 60,
          currentProvision: 26, currentReversal: 4, currentWriteOff: 2,
        })),
      ],
    })
    const rows = api.movementByCategory.value
    expect(rows).toHaveLength(4)
    expect(rows[0]).toMatchObject({
      priorAmount: 60, provisionAmount: 14, reversalAmount: 3, writeOffAmount: 1, endAmount: 70,
    })
    expect(rows[1]).toMatchObject({
      priorAmount: 40, provisionAmount: 26, reversalAmount: 4, writeOffAmount: 2, endAmount: 60,
    })
    const total = rows.find((r) => r.isTotal)!
    expect(total).toMatchObject({
      priorAmount: 100, provisionAmount: 40, reversalAmount: 7, writeOffAmount: 3, endAmount: 130,
    })
  })
})

describe('useD2DisclosureNote — 快照透出账龄段 key（R6 映射前置条件）', () => {
  it('buildSnapshot 的账龄行与组合分表行必须带 key，否则同步层无法映射披露口径', () => {
    const { api } = setup({ variant: 'soe' })
    api.addPortfolio('应收中央企业客户')
    const snap = api.buildSnapshot()

    // 账龄段行（kind=segment）必须有 key，且与 agingSegments 对齐
    const segKeys = api.agingSegments.value.map((s) => s.key)
    const snapSegKeys = snap.agingRows.map((r) => r.key).filter((k) => k && !k.startsWith('__'))
    expect(snapSegKeys).toEqual(segKeys)

    // 结构行也带 key（`__subtotal` / `__badDebt` / `__total`）
    expect(snap.agingRows.every((r) => !!r.key)).toBe(true)

    // 组合分表行按账龄段生成 → key 同样透出
    expect(snap.portfolios[0].rows.map((r) => r.key)).toEqual(segKeys)
  })
})

describe('useD2DisclosureNote — 核销 / 转回 / 前五名', () => {
  it('核销金额默认取自 D2-3 本期核销合计，可覆盖', () => {
    const { api } = setup({ entries: [resp('D2-bd-aging-rows', badDebtFixed({ currentWriteOff: 33 }))] })
    expect(api.writeOffAmountCell.value).toMatchObject({ amount: 33, auto: true })
    api.setWriteOffAmount(50)
    expect(api.writeOffAmountCell.value).toMatchObject({ amount: 50, auto: false })
  })

  it('从 D2-11 带入转回/核销明细（无数据源的列留空）', () => {
    const { api } = setup({
      entries: [
        resp('D2-writeoff-reversal-rows', JSON.stringify([{ debtorName: 'C公司', amount: 5, reason: '款项收回' }])),
        resp('D2-writeoff-writeoff-rows', JSON.stringify([{ debtorName: 'D公司', amount: 3, reason: '破产清算' }])),
      ],
    })
    expect(api.importReversalFromWriteoffCheck()).toBe(1)
    expect(api.reversalRows.value[0]).toMatchObject({
      companyName: 'C公司', amount: 5, reversalReason: '款项收回', recoveryMethod: '', originalBasis: '',
    })
    expect(api.importWriteOffFromWriteoffCheck()).toBe(1)
    expect(api.writeOffRows.value[0]).toMatchObject({
      companyName: 'D公司', amount: 3, reason: '破产清算', nature: '', procedure: '', relatedParty: '',
    })
  })

  it('前五名从 D2-5 前十名按期末余额降序取 5 名；占比 = 本行余额 ÷ D2-1 审定合计', () => {
    const top10 = Array.from({ length: 7 }, (_, i) => ({ customerName: `C${i}`, endBalance: (i + 1) * 100 }))
    const { api } = setup({
      entries: [
        resp('D2-analysis-top10', JSON.stringify(top10)),
        resp('D2-adj-individual-current-unadjusted', '1000'),
        resp('D2-adj-aging-current-unadjusted', '1000'),
      ],
    })
    expect(api.importTop5FromAnalysis()).toBe(5)
    expect(api.top5Rows.value.map((r) => r.companyName)).toEqual(['C6', 'C5', 'C4', 'C3', 'C2'])
    expect(api.top5Total.value).toBe(2000)
    const first = api.top5Rows.value[0]
    expect(first.arAmount).toBe(700)
    expect(api.top5Ratio(first)).toBeCloseTo(35, 6)
    api.updateTop5Row(first.rowId, 'contractAssetAmount', 100)
    expect(api.top5Ratio(api.top5Rows.value[0])).toBeCloseTo(40, 6)
  })

  it('占比分母为 0 时返回 0（不产生 NaN/Infinity）', () => {
    const { api } = setup()
    api.addTop5Row()
    api.updateTop5Row(api.top5Rows.value[0].rowId, 'arAmount', 100)
    expect(api.top5Total.value).toBe(0)
    expect(api.top5Ratio(api.top5Rows.value[0])).toBe(0)
  })
})

describe('useD2DisclosureNote — 勾稽告警与同步快照', () => {
  it('披露合计与 D2-1 审定表 / D2-3 坏账表不一致时产出告警', () => {
    const { api } = setup({
      entries: [
        resp('D2-detail-rows', NESTED_DETAIL), // 小计 1300
        resp('D2-adj-individual-current-unadjusted', '900'), // 审定合计 900 ≠ 1300
        resp('D2-bd-individual-rows', badDebtFixed({ currentAudited: 130 })),
      ],
    })
    const warns = api.inconsistencyWarnings.value
    expect(warns.some((w) => w.includes('按账龄披露小计'))).toBe(true)
    // 披露坏账 130 vs D2-3 坏账 130 一致 → 无坏账告警
    expect(warns.some((w) => w.includes('披露坏账准备'))).toBe(false)
    // 手工覆盖分类金额后，分类合计与审定合计不一致亦产出告警
    api.setOverride('class:end:individual', 1200)
    expect(api.inconsistencyWarnings.value.some((w) => w.includes('按计提方法分类合计'))).toBe(true)
  })

  it('账龄小计与审定合计一致时不产出账龄告警', () => {
    const { api } = setup({
      entries: [
        resp('D2-detail-rows', NESTED_DETAIL), // 1300
        resp('D2-adj-individual-current-unadjusted', '1300'),
      ],
    })
    expect(api.inconsistencyWarnings.value.some((w) => w.includes('按账龄披露小计'))).toBe(false)
  })

  it('buildSnapshot 可直接喂 buildD2SyncPayload 并产出全部附注子表', () => {
    const { api } = setup({
      variant: 'soe',
      entries: [
        resp('D2-detail-rows', NESTED_DETAIL),
        resp('D2-bd-individual-rows', badDebtFixed({ priorAudited: 100, currentAudited: 130, currentWriteOff: 3 })),
      ],
    })
    api.addPortfolio('应收中央企业客户')
    api.setNote('aging', '账龄说明')
    const payload = buildD2SyncPayload('soe', 'wp-1', null, api.buildSnapshot())
    expect(payload.section_id).toBe('八、5')
    for (const name of Object.values(D2_TABLE_NAMES.soe)) {
      expect(payload.sub_table_data[name], `${name} 未推送`).toBeDefined()
    }
    expect(payload.sub_table_data['组合计提项目：应收中央企业客户']).toBeDefined()
    const texts = payload.sub_table_data._note_texts as any[]
    expect(texts).toEqual([{ section: 'note-aging', title: '按账龄披露说明', text: '账龄说明' }])
    // 账龄表行含结构行（合计标记）
    const aging = payload.sub_table_data[D2_TABLE_NAMES.soe.aging] as any[]
    expect(aging.at(-1)).toMatchObject({ label: '合 计', is_total: true })
  })

  it('只读态禁止任何写入', () => {
    const save = vi.fn()
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const api = useD2DisclosureNote({
      allResponses,
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      variant: 'listed',
      save,
      isReadonly: ref(true),
    })
    api.addPortfolio('X')
    api.addIndividualRow()
    api.addTop5Row()
    api.setOverride('aging:end:within1', 10)
    api.setNote('aging', '文本')
    expect(save).not.toHaveBeenCalled()
    expect(api.portfolios.value).toHaveLength(0)
    expect(api.individualRows.value).toHaveLength(0)
    expect(api.top5Rows.value).toHaveLength(0)
    expect(api.agingRows.value.find((r) => r.label === '1年以内')!.endAmount).toBe(0)
  })
})

describe('useD2DisclosureNote — 旧版披露数据（D2-disclosure-*）兼容带入', () => {
  const LEGACY_LISTED = JSON.stringify({
    top5: [
      { rowId: 'l1', label: '甲公司', amount: 900, badDebt: 90 },
      { rowId: 'l2', label: '乙公司', amount: 500, badDebt: 50 },
      { rowId: 'l3', label: '', amount: 0, badDebt: 0 },
    ],
    'aging-detail': [
      { rowId: 'a1', label: '一年以内', amount: 1000, badDebt: 0 },
      { rowId: 'a2', label: '一到二年', amount: 300, badDebt: 0 },
    ],
    'by-category': [{ rowId: 'c1', label: '货款', amount: 1300, badDebt: 0 }],
  })

  it('检测旧数据并区分可带入区块与需人工核对区块', () => {
    const { api } = setup({ entries: [resp('D2-disclosure-listed-d2-1', LEGACY_LISTED)] })
    const info = api.legacyDisclosureInfo.value
    expect(info.top5).toBe(2) // 空行不计
    expect(info.aging).toBe(2)
    expect(info.unmapped).toContain('by-category')
  })

  it('一键带入：前五名按名称去重追加，账龄写入期末覆盖值（标签中文数字归一）', () => {
    const { api } = setup({ entries: [resp('D2-disclosure-listed-d2-1', LEGACY_LISTED)] })
    const result = api.importFromLegacyDisclosure()
    expect(result.top5).toBe(2)
    expect(api.top5Rows.value.map((r) => r.companyName)).toEqual(['甲公司', '乙公司'])
    expect(api.top5Rows.value[0].arAmount).toBe(900)
    expect(api.top5Rows.value[0].provision).toBe(90)
    // 「一年以内」→ within1、「一到二年」→ y1to2
    expect(result.aging).toBe(2)
    const rows = api.agingRows.value
    expect(rows.find((r) => r.key === 'within1')!.endAmount).toBe(1000)
    expect(rows.find((r) => r.key === 'y1to2')!.endAmount).toBe(300)
  })

  it('不覆盖已有手工数据：已存在的前五名名称与已覆盖的账龄段跳过', () => {
    const { api } = setup({ entries: [resp('D2-disclosure-listed-d2-1', LEGACY_LISTED)] })
    api.addTop5Row()
    api.updateTop5Row(api.top5Rows.value[0].rowId, 'companyName', '甲公司')
    api.setOverride('aging:end:within1', 777)
    const result = api.importFromLegacyDisclosure()
    expect(result.top5).toBe(1) // 甲公司已存在 → 只带入乙公司
    expect(result.aging).toBe(1) // within1 已手工覆盖 → 只带入 y1to2
    expect(api.agingRows.value.find((r) => r.key === 'within1')!.endAmount).toBe(777)
  })

  it('只读态不带入任何数据', () => {
    const save = vi.fn()
    const allResponses = ref(new Map<string, ChecklistResponse>([resp('D2-disclosure-listed-d2-1', LEGACY_LISTED)]))
    const api = useD2DisclosureNote({
      allResponses,
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      variant: 'listed',
      save,
      isReadonly: ref(true),
    })
    expect(api.importFromLegacyDisclosure()).toEqual({ top5: 0, aging: 0 })
    expect(api.top5Rows.value).toHaveLength(0)
  })

  it('无旧数据时不产生提示、带入为空操作', () => {
    const { api } = setup()
    expect(api.legacyDisclosureInfo.value).toEqual({ top5: 0, aging: 0, unmapped: [] })
    expect(api.importFromLegacyDisclosure()).toEqual({ top5: 0, aging: 0 })
  })
})

describe('buildD2SyncPayload — 同名组合分表不丢表', () => {
  function snapshotWithPortfolios(names: Array<{ name: string; groupId: string }>) {
    return {
      agingRows: [], classRows: [], individualRows: [],
      portfolios: names.map((n) => ({ name: n.name, groupId: n.groupId, rows: [{ label: '1年以内', endAmount: 1, priorAmount: 0 }] })),
      movement: { priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, transfer: 0, other: 0, endBalance: 0 },
      reversalRows: [], writeOffAmount: 0, writeOffRows: [], top5Rows: [], notes: {},
    }
  }

  it('同名组合以 groupId 后缀区分，两张分表都在（旧实现会静默丢弃后一个）', () => {
    const payload = buildD2SyncPayload('listed', 'wp-1', null, snapshotWithPortfolios([
      { name: '应收中央企业客户', groupId: 'pf-aaaaaa' },
      { name: '应收中央企业客户', groupId: 'pf-bbbbbb' },
    ]) as any)
    const keys = Object.keys(payload.sub_table_data).filter((k) => k.startsWith('组合计提项目：'))
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBe('组合计提项目：应收中央企业客户')
    expect(keys[1]).toContain('bbbbbb')
    expect(payload.columns[keys[1]]).toBeDefined()
  })

  it('无 groupId 时退化为序号后缀，仍不丢表', () => {
    const payload = buildD2SyncPayload('listed', 'wp-1', null, snapshotWithPortfolios([
      { name: '组合A', groupId: '' },
      { name: '组合A', groupId: '' },
    ]) as any)
    const keys = Object.keys(payload.sub_table_data).filter((k) => k.startsWith('组合计提项目：'))
    expect(keys).toEqual(['组合计提项目：组合A', '组合计提项目：组合A（2）'])
  })

  it('不同名组合各一张表（回归：表名不受去重逻辑影响）', () => {
    const payload = buildD2SyncPayload('soe', 'wp-1', null, snapshotWithPortfolios([
      { name: '应收中央企业客户', groupId: 'p1' },
      { name: '应收海外企业客户', groupId: 'p2' },
    ]) as any)
    expect(Object.keys(payload.sub_table_data)).toContain(D2_TABLE_NAMES.soe.aging)
    expect(payload.sub_table_data['组合计提项目：应收中央企业客户']).toBeDefined()
    expect(payload.sub_table_data['组合计提项目：应收海外企业客户']).toBeDefined()
  })
})

describe('useD2DisclosureNote — R7.5 基线播种 seedSyncedTablesFromNote', () => {
  const NOTE_TABLE_DATA = {
    sub_table_data: {
      [D2_TABLE_NAMES.soe.aging]: [],
      '组合计提项目：应收中央企业客户': [],
      // 别的底稿推的表（不在 D2 命名空间内）
      存货跌价准备: [],
      _note_texts: [],
    },
  }

  it('首次同步：播种命名空间内的附注现存表名并持久化', () => {
    const { api, save } = setup({ variant: 'soe' })
    expect(api.syncedTableNames.value).toEqual([])
    const seeded = api.seedSyncedTablesFromNote(NOTE_TABLE_DATA)
    expect(seeded).toEqual([D2_TABLE_NAMES.soe.aging, '组合计提项目：应收中央企业客户'])
    expect(api.syncedTableNames.value).toEqual(seeded)
    expect(save).toHaveBeenCalledWith([
      expect.objectContaining({
        item_id: 'D2-disc-soe-synced-tables',
        remark: JSON.stringify(seeded),
      }),
    ])
  })

  it('基线已建立 → 幂等，不覆盖、不再写库', () => {
    const { api, save } = setup({ variant: 'soe' })
    api.markSynced(['既有表A'])
    save.mockClear()
    const seeded = api.seedSyncedTablesFromNote(NOTE_TABLE_DATA)
    expect(seeded).toEqual(['既有表A'])
    expect(api.syncedTableNames.value).toEqual(['既有表A'])
    expect(save).not.toHaveBeenCalled()
  })

  it('播种结果参与差集：上线前残留的组合分表被清理，别的底稿的表不受影响', () => {
    const { api } = setup({ variant: 'soe' })
    api.seedSyncedTablesFromNote(NOTE_TABLE_DATA)
    const payload = buildD2SyncPayload('soe', 'wp-1', null, api.buildSnapshot())
    const removed = (payload.sub_table_data._removed_table_keys ?? []) as string[]
    expect(removed).toEqual(['组合计提项目：应收中央企业客户'])
    expect(removed).not.toContain('存货跌价准备')
    // 本轮推送的表绝不在待删除清单里
    for (const key of removed) expect(payload.sub_table_data[key]).toBeUndefined()
  })

  it('附注尚未生成 / 读取失败（空 table_data）→ 不播种、不写库', () => {
    const { api, save } = setup({ variant: 'soe' })
    save.mockClear()
    expect(api.seedSyncedTablesFromNote(null)).toEqual([])
    expect(api.seedSyncedTablesFromNote({ rows: [] })).toEqual([])
    expect(api.syncedTableNames.value).toEqual([])
    expect(save).not.toHaveBeenCalled()
  })
})
