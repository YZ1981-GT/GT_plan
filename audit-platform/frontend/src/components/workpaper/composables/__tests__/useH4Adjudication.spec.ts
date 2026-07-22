/**
 * useH4Adjudication — H4-1 审定表单测
 * 对齐 Excel：期初/期末×未审·账项调整·审定 + 变动额/率；三段净值
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  useH4Adjudication,
  calcH4ChangeRate,
  CHANGE_RATE_THRESHOLD,
  DEFAULT_H4_CATEGORIES,
} from '../useH4Adjudication'

function setup(map?: Map<string, any>) {
  const allResponses = ref(map ?? new Map())
  const saved: Record<string, any> = {}
  const api = useH4Adjudication({
    wpId: ref('wp1'),
    projectId: ref('p1'),
    allResponses,
    tbData: ref({ unadjusted1605: 10000, audited1605: 9800 }),
    onSave: (id, val) => {
      saved[id] = val
      allResponses.value.set(id, {
        remark: typeof val === 'string' ? val : JSON.stringify(val),
      })
    },
    onWritebackTB: vi.fn(),
  })
  return { api, allResponses, saved }
}

describe('calcH4ChangeRate', () => {
  it('对齐 Excel：期初0且变动0 → 0', () => {
    expect(calcH4ChangeRate(0, 0)).toBe(0)
  })
  it('对齐 Excel：期初0且变动>0 → 100%', () => {
    expect(calcH4ChangeRate(50, 0)).toBe(100)
  })
  it('对齐 Excel：正常变动率', () => {
    expect(calcH4ChangeRate(30, 100)).toBeCloseTo(30, 5)
  })
})

describe('useH4Adjudication', () => {
  it('空数据时种子默认四分类原值+减值', () => {
    const { api } = setup()
    expect(api.originalRows.value).toHaveLength(DEFAULT_H4_CATEGORIES.length)
    expect(api.impairmentRows.value).toHaveLength(DEFAULT_H4_CATEGORIES.length)
    expect(api.originalRows.value.map((r) => r.name)).toEqual([...DEFAULT_H4_CATEGORIES])
  })

  it('审定=未审+账项调整；变动额/率自动计算', () => {
    const { api } = setup()
    const row = api.originalRows.value[0]
    api.updateCell(row.rowId, 'beginUnadjusted', 1000)
    api.updateCell(row.rowId, 'beginAdjustment', 100)
    api.updateCell(row.rowId, 'endUnadjusted', 1500)
    api.updateCell(row.rowId, 'endAdjustment', -50)

    const updated = api.originalRows.value.find((r) => r.rowId === row.rowId)!
    expect(updated.beginAudited).toBe(1100)
    expect(updated.endAudited).toBe(1450)
    expect(updated.auditedChange).toBe(350)
    expect(updated.auditedChangeRate).toBeCloseTo((350 / 1100) * 100, 5)
  })

  it('净值=原值−减值，身份校验为0', () => {
    const map = new Map()
    map.set('H4-1-rows', {
      remark: JSON.stringify([
        {
          rowId: 'o1', name: '专用材料', section: 'original',
          beginUnadjusted: 1000, beginAdjustment: 0,
          endUnadjusted: 2000, endAdjustment: 0,
        },
        {
          rowId: 'i1', name: '专用材料', section: 'impairment',
          beginUnadjusted: 100, beginAdjustment: 0,
          endUnadjusted: 200, endAdjustment: 0,
        },
      ]),
    })
    const { api } = setup(map)
    expect(api.netTotalRow.value.endAudited).toBe(1800)
    expect(api.netTotalRow.value.beginAudited).toBe(900)
    expect(api.netIdentityDiff.value).toBe(0)
    expect(api.adjudicatedTotal.value).toBe(1800)
  })

  it('兼容旧存档字段 beginBalance/unadjusted/aje/rje', () => {
    const map = new Map()
    map.set('H4-1-rows', {
      remark: JSON.stringify([
        {
          rowId: 'legacy', name: '工器具', section: 'original',
          beginBalance: 500, debitAmount: 100, creditAmount: 50,
          endBalance: 550, unadjusted: 550, aje: 20, rje: 10,
        },
      ]),
    })
    const { api } = setup(map)
    const row = api.originalRows.value[0]
    expect(row.beginUnadjusted).toBe(500)
    expect(row.endUnadjusted).toBe(550)
    expect(row.endAdjustment).toBe(30)
    expect(row.endAudited).toBe(580)
  })

  it('从 H4-2 按分类回填原值/减值', () => {
    const map = new Map()
    map.set('H4-2-rows', {
      remark: JSON.stringify([
        {
          category: '专用材料', name: '水泥',
          beginAmount: 1000, purchaseAmount: 500, otherIncrease: 0,
          usageAmount: 200, returnAmount: 0, scrapAmount: 0, otherDecrease: 0,
          endAmount: 1300,
          ajeBegin: 10, ajeIncrease: 0, ajeDecrease: 0,
          impairBegin: 50, impairEnd: 80, ajeImpair: 5,
          auditedEnd: 1310,
        },
      ]),
    })
    const { api } = setup(map)
    const r = api.syncFromH42()
    expect(r.applied).toBe(true)
    const orig = api.originalRows.value.find((x) => x.name === '专用材料')!
    expect(orig.beginUnadjusted).toBe(1000)
    expect(orig.beginAdjustment).toBe(10)
    expect(orig.endUnadjusted).toBe(1300)
    expect(orig.endAdjustment).toBe(10) // auditedEnd - endAmount
    const imp = api.impairmentRows.value.find((x) => x.name === '专用材料')!
    expect(imp.endUnadjusted).toBe(80)
    expect(imp.endAdjustment).toBe(5)
  })

  it('从 H4-3 按权重回写期末账项调整', () => {
    const map = new Map()
    map.set('H4-1-rows', {
      remark: JSON.stringify([
        {
          rowId: 'o1', name: '专用材料', section: 'original',
          beginUnadjusted: 0, beginAdjustment: 0,
          endUnadjusted: 800, endAdjustment: 0,
        },
        {
          rowId: 'o2', name: '专用设备', section: 'original',
          beginUnadjusted: 0, beginAdjustment: 0,
          endUnadjusted: 200, endAdjustment: 0,
        },
        {
          rowId: 'i1', name: '专用材料', section: 'impairment',
          beginUnadjusted: 0, beginAdjustment: 0,
          endUnadjusted: 0, endAdjustment: 0,
        },
        {
          rowId: 'i2', name: '专用设备', section: 'impairment',
          beginUnadjusted: 0, beginAdjustment: 0,
          endUnadjusted: 0, endAdjustment: 0,
        },
      ]),
    })
    map.set('H4-3-rows', {
      remark: JSON.stringify([
        { category: '账项调整', accountCode: '1605', debitAmount: 100, creditAmount: 0 },
        { category: '账项调整', accountCode: '6602', debitAmount: 0, creditAmount: 100 },
      ]),
    })
    const { api } = setup(map)
    const r = api.syncEndAdjFromH43()
    expect(r.applied).toBe(true)
    const a = api.originalRows.value.find((x) => x.name === '专用材料')!
    const b = api.originalRows.value.find((x) => x.name === '专用设备')!
    expect(a.endAdjustment).toBe(80)
    expect(b.endAdjustment).toBe(20)
    expect(a.endAudited).toBe(880)
  })

  it('变动率≥阈值标记重大变动', () => {
    const map = new Map()
    map.set('H4-1-rows', {
      remark: JSON.stringify([
        {
          rowId: 'o1', name: '专用材料', section: 'original',
          beginUnadjusted: 100, beginAdjustment: 0,
          endUnadjusted: 200, endAdjustment: 0,
        },
        {
          rowId: 'i1', name: '专用材料', section: 'impairment',
          beginUnadjusted: 0, beginAdjustment: 0,
          endUnadjusted: 0, endAdjustment: 0,
        },
      ]),
    })
    const { api } = setup(map)
    expect(CHANGE_RATE_THRESHOLD).toBe(30)
    expect(api.netRows.value[0].auditedChangeRate).toBe(100)
    expect(api.significantNetChanges.value).toHaveLength(1)
  })

  it('报表核对行：工程物资自动带入，合计数/差异公式', () => {
    const map = new Map()
    map.set('H4-1-rows', {
      remark: JSON.stringify([
        {
          rowId: 'o1', name: '专用材料', section: 'original',
          beginUnadjusted: 500, beginAdjustment: 0,
          endUnadjusted: 1000, endAdjustment: 0,
        },
      ]),
    })
    const { api } = setup(map)
    api.updateFsField('cipEndAudited', 5000)
    api.updateFsField('cipBeginAudited', 4000)
    api.updateFsField('fsEndAmount', 6000)
    api.updateFsField('fsBeginAmount', 4500)
    const rows = api.fsCompareRows.value
    expect(rows[1].label).toBe('工程物资审定数')
    expect(rows[1].endAudited).toBe(1000)
    expect(rows[2].endAudited).toBe(6000) // 5000+1000
    expect(rows[4].endAudited).toBe(0) // 差异
    expect(rows[4].beginAudited).toBe(0) // 4000+500-4500
  })

  it('从 TB·1604 带入在建工程审定', () => {
    const allResponses = ref(new Map())
    const saved: Record<string, any> = {}
    const api = useH4Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      tbData: ref({
        unadjusted1605: 0,
        audited1605: 0,
        unadjusted1604: 9000,
        audited1604: 8800,
        opening1604: 7000,
      }),
      onSave: (id, val) => {
        saved[id] = val
        allResponses.value.set(id, {
          remark: typeof val === 'string' ? val : JSON.stringify(val),
        })
      },
    })
    const r = api.seedCipFromTb('overwrite')
    expect(r.applied).toBe(true)
    expect(api.fsReconcile.value.cipEndAudited).toBe(8800)
    expect(api.fsReconcile.value.cipBeginAudited).toBe(7000)
  })

  it('从 H2-1 原值行汇总带入在建工程', () => {
    const { api } = setup()
    const r = api.seedCipFromH21Rows([
      { name: '厂房', beginAudited: 1000, endAudited: 2000 },
      { name: '设备安装', beginAudited: 500, endAudited: 800 },
    ])
    expect(r.applied).toBe(true)
    expect(api.fsReconcile.value.cipEndAudited).toBe(2800)
    expect(api.fsReconcile.value.cipBeginAudited).toBe(1500)
  })

  it('持久化重大变动附注键，并可写入说明草稿', () => {
    const map = new Map()
    map.set('H4-1-rows', {
      remark: JSON.stringify([
        {
          rowId: 'o1', name: '专用材料', section: 'original',
          beginUnadjusted: 100, beginAdjustment: 0,
          endUnadjusted: 200, endAdjustment: 0,
        },
        {
          rowId: 'i1', name: '专用材料', section: 'impairment',
          beginUnadjusted: 0, beginAdjustment: 0,
          endUnadjusted: 0, endAdjustment: 0,
        },
      ]),
    })
    const { api, saved } = setup(map)
    api.save()
    expect(saved['H4-1-significant-change-count']).toBe(1)
    expect(saved['H4-1-significant-changes']).toHaveLength(1)
    expect(saved['H4-1-significant-changes'][0].name).toBe('专用材料')
    const note = api.applySignificantNoteDraft()
    expect(note.applied).toBe(true)
    expect(api.qualitativeNotes.value.fluctuation).toContain('专用材料')
  })

  it('结论模板 A/B/C', () => {
    const { api } = setup()
    api.applyConclusionTemplate('A')
    expect(api.auditConclusion.value).toContain('未见异常')
    api.applyConclusionTemplate('C')
    expect(api.auditConclusion.value).toContain('不可确认')
  })
})
