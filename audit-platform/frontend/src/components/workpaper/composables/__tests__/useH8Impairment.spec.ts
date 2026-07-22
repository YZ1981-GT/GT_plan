/**
 * useH8Impairment 单元测试 — 公式闸门 / H8-2 带入 / 编制校验 / H8-11 回写
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  emptyH8ImpairmentRow,
  recomputeH8ImpairmentRow,
  validateH8ImpairmentPrep,
  seedRowsFromH82,
  mapAlreadyProvidedFromH88,
  upsertH810RowFromRecoverable,
  useH8Impairment,
  H810_ROWS_KEY,
} from '../useH8Impairment'

describe('recomputeH8ImpairmentRow', () => {
  it('无迹象时⑤⑥⑧为 0，多提进⑨', () => {
    const row = recomputeH8ImpairmentRow(emptyH8ImpairmentRow({
      hasIndication: 'N',
      bookValue: 1000,
      fairValueLessDisposal: 100,
      dcfValue: 200,
      alreadyProvided: 50,
    }))
    expect(row.recoverableAmount).toBe(0)
    expect(row.impairmentAmount).toBe(0)
    expect(row.supplement).toBe(0)
    expect(row.overProvision).toBe(50)
  })

  it('有迹象时⑥=MAX(②−⑤,0)，⑧不得为负', () => {
    const row = recomputeH8ImpairmentRow(emptyH8ImpairmentRow({
      hasIndication: 'Y',
      bookValue: 1000,
      fairValueLessDisposal: 400,
      dcfValue: 300,
      alreadyProvided: 100,
    }))
    expect(row.recoverableAmount).toBe(400)
    expect(row.impairmentAmount).toBe(600)
    expect(row.supplement).toBe(500)
    expect(row.overProvision).toBe(0)
  })
})

describe('validateH8ImpairmentPrep', () => {
  it('有迹象缺 H8-11 索引则失败', () => {
    const v = validateH8ImpairmentPrep([
      emptyH8ImpairmentRow({
        assetName: '办公室',
        hasIndication: 'Y',
        indicationDesc: '闲置',
        bookValue: 100,
        fairValueLessDisposal: 80,
        indexRef: '',
      }),
    ])
    expect(v.ok).toBe(false)
    expect(v.messages.some((m) => m.includes('H8-11'))).toBe(true)
  })

  it('有迹象且索引含 H8-11、已测可收回则通过', () => {
    const v = validateH8ImpairmentPrep([
      recomputeH8ImpairmentRow(emptyH8ImpairmentRow({
        assetName: '办公室',
        hasIndication: 'Y',
        indicationDesc: '闲置',
        bookValue: 100,
        fairValueLessDisposal: 80,
        indexRef: 'H8-11',
      })),
    ])
    expect(v.ok).toBe(true)
  })
})

describe('seedRowsFromH82 / mapAlreadyProvidedFromH88', () => {
  it('从 H8-2 计算②=入账值−累计折旧', () => {
    const rows = seedRowsFromH82([
      {
        rowId: 'd1',
        assetName: '车辆A',
        contractNo: 'L-01',
        initialAmount: 120000,
        accDepBegin: 20000,
        depCurrentPeriod: 10000,
        accDepEnd: 30000,
      },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].bookValue).toBe(90000)
    expect(rows[0].sourceDetailRowId).toBe('d1')
  })

  it('按名称匹配 H8-8 减值写入⑦', () => {
    const seeded = seedRowsFromH82([
      { rowId: 'd1', assetName: '车辆A', initialAmount: 100, accDepEnd: 0 },
    ])
    const mapped = mapAlreadyProvidedFromH88(seeded, [
      { assetName: '车辆A', impairmentAmount: 15 },
    ])
    expect(mapped[0].alreadyProvided).toBe(15)
  })

  it('按合同号优先匹配 H8-8 减值写入⑦', () => {
    const seeded = [
      emptyH8ImpairmentRow({ assetName: '车辆A', contractNo: 'L-01', bookValue: 100 }),
    ]
    const mapped = mapAlreadyProvidedFromH88(seeded, [
      { assetName: '其他名', contractNo: 'L-01', impairmentAmount: 25 },
      { assetName: '车辆A', contractNo: 'L-99', impairmentAmount: 99 },
    ])
    expect(mapped[0].alreadyProvided).toBe(25)
  })
})

describe('upsertH810RowFromRecoverable', () => {
  it('按名称更新或新增行并强制有迹象+H8-11', () => {
    const base = [emptyH8ImpairmentRow({ assetName: '仓库', bookValue: 50000 })]
    const next = upsertH810RowFromRecoverable(base, {
      assetName: '仓库',
      bookValue: 50000,
      fairValueNet: 10000,
      pvCashFlows: 20000,
    })
    expect(next).toHaveLength(1)
    expect(next[0].hasIndication).toBe('Y')
    expect(next[0].recoverableAmount).toBe(20000)
    expect(next[0].impairmentAmount).toBe(30000)
    expect(next[0].indexRef).toContain('H8-11')
  })
})

describe('useH8Impairment', () => {
  it('importFromH82 持久化行并推送摘要 params', () => {
    const saved: Record<string, any> = {}
    const map = ref(new Map<string, any>([
      ['H8-2-rows', {
        remark: JSON.stringify([
          { rowId: 'r1', assetName: '厂房', contractNo: 'C1', initialAmount: 200, accDepEnd: 50 },
        ]),
      }],
    ]))
    const api = useH8Impairment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map,
      isReadonly: ref(false),
      onSave: (id, v) => { saved[id] = v },
    })
    const r = api.importFromH82()
    expect(r.ok).toBe(true)
    expect(api.rows.value[0].bookValue).toBe(150)
    expect(saved[H810_ROWS_KEY]).toBeTruthy()
    expect(api.supplementTotal.value).toBe(0)
  })

  it('有⑧补提时可切换 H8-8 含减值分支', () => {
    const saved: Record<string, any> = {}
    const api = useH8Impairment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: ref(new Map()),
      isReadonly: ref(false),
      onSave: (id, v) => { saved[id] = v },
    })
    api.updateRow(api.rows.value[0].rowId, {
      assetName: '厂房',
      hasIndication: 'Y',
      indicationDesc: '闲置',
      bookValue: 1000,
      fairValueLessDisposal: 400,
      dcfValue: 300,
      alreadyProvided: 0,
      indexRef: 'H8-11',
    })
    expect(api.supplementTotal.value).toBe(600)
    const r = api.switchH88ToWithImpairment()
    expect(r.ok).toBe(true)
    expect(saved['H8-8-branch']).toBe('含减值')
  })
})
