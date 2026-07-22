/**
 * useH2Adjudication — H2-1 审定表单元测试
 * 覆盖：原值/减值/净值、变动率≥30%、H2-2同步、身份校验、结论模板
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useH2Adjudication, CHANGE_RATE_THRESHOLD } from '../useH2Adjudication'

function makeMap(entries: Record<string, any> = {}) {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, {
      item_id: k,
      conclusion: null,
      remark: typeof v === 'string' ? v : JSON.stringify(v),
    })
  }
  return m
}

describe('useH2Adjudication', () => {
  const wpId = ref('wp-1')
  const projectId = ref('proj-1')
  let saved: Record<string, any>
  let onSave: ReturnType<typeof vi.fn>

  beforeEach(() => {
    saved = {}
    onSave = vi.fn((id: string, val: any) => {
      saved[id] = val
    })
  })

  it('审定=未审+调整，净值=原值−减值', async () => {
    const allResponses = ref(makeMap())
    const api = useH2Adjudication({
      wpId,
      projectId,
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave,
    })
    await nextTick()

    api.addProjectRow('厂房扩建')
    const costId = api.costDetailRows.value[0].rowId
    api.updateCell('cost', costId, 'beginUnadjusted', 1000)
    api.updateCell('cost', costId, 'beginAdjustment', 50)
    api.updateCell('cost', costId, 'endUnadjusted', 1200)
    api.updateCell('cost', costId, 'endAdjustment', 80)

    const impairId = api.impairDetailRows.value[0].rowId
    api.updateCell('impair', impairId, 'beginUnadjusted', 100)
    api.updateCell('impair', impairId, 'endUnadjusted', 150)
    api.updateCell('impair', impairId, 'endAdjustment', 20)

    expect(api.costDetailRows.value[0].beginAudited).toBe(1050)
    expect(api.costDetailRows.value[0].endAudited).toBe(1280)
    expect(api.impairDetailRows.value[0].endAudited).toBe(170)

    const net = api.netRows.value.find((r) => r.name === '厂房扩建')
    expect(net?.beginAudited).toBe(950) // 1050-100
    expect(net?.endAudited).toBe(1110) // 1280-170
    expect(Math.abs(api.netIdentityDiff.value)).toBeLessThan(0.01)
  })

  it('净值变动率≥30% 标记 isSignificant', async () => {
    const allResponses = ref(makeMap())
    const api = useH2Adjudication({
      wpId,
      projectId,
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave,
    })
    await nextTick()

    api.addProjectRow('码头')
    const costId = api.costDetailRows.value[0].rowId
    api.updateCell('cost', costId, 'beginUnadjusted', 100)
    api.updateCell('cost', costId, 'endUnadjusted', 160)

    const net = api.netRows.value.find((r) => r.name === '码头')
    expect(net?.auditedChangeRate).toBeCloseTo(60, 5)
    expect(net?.isSignificant).toBe(true)
    expect(api.significantNetChanges.value.length).toBe(1)
    expect(CHANGE_RATE_THRESHOLD).toBe(30)
  })

  it('从 H2-2 同步工程原值与减值', async () => {
    const allResponses = ref(
      makeMap({
        'H2-2-rows': [
          {
            name: '专线',
            cipBegin: 500,
            beginAudited: 510,
            cipEnd: 800,
            endAudited: 820,
            impairmentBegin: 20,
            impairBeginAud: 20,
            impairmentEnd: 30,
            impairEndAud: 35,
            transferAmount: 100,
          },
        ],
      }),
    )
    const api = useH2Adjudication({
      wpId,
      projectId,
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave,
    })
    await nextTick()

    const res = api.syncFromH22('overwrite')
    expect(res.applied).toBe(true)
    expect(api.costDetailRows.value).toHaveLength(1)
    expect(api.costDetailRows.value[0].beginUnadjusted).toBe(500)
    expect(api.costDetailRows.value[0].beginAdjustment).toBe(10)
    expect(api.costDetailRows.value[0].endAudited).toBe(820)
    expect(api.impairDetailRows.value[0].endAudited).toBe(35)
    expect(api.qualitativeNotes.value.transferToFa).toContain('100')
  })

  it('结论模板 A/B/C 与定性说明持久化', async () => {
    const allResponses = ref(makeMap())
    const api = useH2Adjudication({
      wpId,
      projectId,
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave,
    })
    await nextTick()

    api.applyConclusionTemplate('A')
    expect(saved['H2-1-audit-conclusion']).toContain('未见异常')
    api.applyConclusionTemplate('C')
    expect(api.auditConclusion.value).toContain('不可确认')

    api.saveQualitativeNotes({ fluctuation: '产能扩建导致净值上升' })
    expect(saved['H2-1-qualitative-notes']).toMatchObject({
      fluctuation: '产能扩建导致净值上升',
    })
  })

  it('H2-3 账项净额回写期末调整（单行）', async () => {
    const allResponses = ref(makeMap())
    const api = useH2Adjudication({
      wpId,
      projectId,
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave,
    })
    await nextTick()
    api.addProjectRow('A')
    const res = api.syncEndAdjustmentFromH23(1234.56)
    expect(res.applied).toBe(true)
    expect(api.costDetailRows.value[0].endAdjustment).toBe(1234.56)
  })

  it('试算核对含在建工程与工程物资', async () => {
    const allResponses = ref(makeMap())
    const api = useH2Adjudication({
      wpId,
      projectId,
      allResponses: allResponses as any,
      isReadonly: ref(false),
      tbData: ref({ audited_amount: 1000, materials_audited: 200 }),
      onSave,
    })
    await nextTick()
    api.addProjectRow('A')
    api.updateCell('cost', api.costDetailRows.value[0].rowId, 'endUnadjusted', 1000)
    api.updateMaterials('audited', 200)
    api.updateMaterials('tbAmount', 200)

    const rows = api.tbCompareRows.value
    expect(rows).toHaveLength(2)
    expect(rows[0].difference).toBe(0)
    expect(rows[1].label).toContain('1605')
    expect(rows[1].difference).toBe(0)
  })

  it('未审合计 vs TB 差异 + 从 TB 带入工程物资', async () => {
    const tbData = ref({
      unadjusted_amount: 500,
      audited_amount: 500,
      materials_unadjusted: 80,
      materials_audited: 80,
    })
    const allResponses = ref(makeMap())
    const api = useH2Adjudication({
      wpId,
      projectId,
      allResponses: allResponses as any,
      isReadonly: ref(false),
      tbData: tbData as any,
      onSave,
    })
    await nextTick()

    // watch 自动带入物资
    expect(api.materialsAudited.value).toBe(80)

    api.addProjectRow('A')
    api.updateCell('cost', api.costDetailRows.value[0].rowId, 'endUnadjusted', 400)
    expect(api.unadjustedVsTbDiff.value).toBe(-100)

    api.updateMaterials('audited', 0)
    api.updateMaterials('tbAmount', 0)
    const res = api.seedMaterialsFromTb('overwrite')
    expect(res.applied).toBe(true)
    expect(api.materialsAudited.value).toBe(80)
  })

  it('确认审定触发 TB 回写与 EventBus', async () => {
    const writeback = vi.fn(async () => {})
    const publish = vi.fn()
    const allResponses = ref(makeMap())
    const api = useH2Adjudication({
      wpId,
      projectId,
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave,
      onWritebackTB: writeback,
      onPublishEvent: publish,
    })
    await nextTick()
    api.addProjectRow('A')
    api.updateCell('cost', api.costDetailRows.value[0].rowId, 'endUnadjusted', 999)
    await api.publishAdjudicated()
    expect(writeback).toHaveBeenCalledWith(999)
    expect(publish).toHaveBeenCalledWith(
      'substantive:adjudicated',
      expect.objectContaining({ account_codes: ['1604'], audited_amount: 999 }),
    )
  })
})
