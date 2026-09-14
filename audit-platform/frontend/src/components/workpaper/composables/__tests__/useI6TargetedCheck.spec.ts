/**
 * useI6TargetedCheck — 持久化、I6-2 联动与旧数据迁移
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { useI6TargetedCheck } from '../useI6TargetedCheck'

function makeMap(extra?: Record<string, unknown>) {
  const m = new Map<string, { item_id: string; conclusion: null; remark: string | null }>()
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      m.set(k, {
        item_id: k,
        conclusion: null,
        remark: typeof v === 'string' ? v : JSON.stringify(v),
      })
    }
  }
  return ref(m)
}

describe('useI6TargetedCheck', () => {
  it('从 I6-2 明细自动带入本期发生额（非手工锁定）', async () => {
    const allResponses = makeMap({
      'I6-2-detail-rows': [
        { category: '平台研发', months: [100, 200], aje: 0, rje: 0 },
      ],
    })
    const { sampleMeta, linkedPeriod } = useI6TargetedCheck(allResponses)
    await nextTick()
    expect(linkedPeriod.value.debitTotal).toBe(300)
    expect(sampleMeta.value.populationAmount).toBe(300)
    expect(sampleMeta.value.populationManual).toBe(false)
  })

  it('populationManual=true 时不被 I6-2 覆盖', async () => {
    const allResponses = makeMap({
      'I6-2-detail-rows': [{ category: 'A', months: [1000], aje: 0, rje: 0 }],
      'I6-4-sample-meta': { populationAmount: 88, populationManual: true },
    })
    const { sampleMeta } = useI6TargetedCheck(allResponses)
    await nextTick()
    expect(sampleMeta.value.populationAmount).toBe(88)
    expect(sampleMeta.value.populationManual).toBe(true)
  })

  it('旧段落型 key 迁移到 risk-focus 与结论', async () => {
    const allResponses = makeMap({
      'I6-4-complete-project': '正常',
      'I6-4-complete-misclass': '异常',
      'I6-4-alloc-staff': '正常',
      'I6-4-i2-vr-balance': '异常',
      'I6-4-superDeduction-conclusion': '可加计范围无重大异常',
      'I6-4-super-deduction-rows': [{ category: '人工费', collectedAmount: 100 }],
      'I6-4-conclusion': '旧版总体结论',
      'I6-4-audit-note': '旧版说明',
    })
    const { riskFocus, auditConclusion, auditNote } = useI6TargetedCheck(allResponses)
    await nextTick()
    expect(riskFocus.value.completenessConclusion).toContain('未见异常')
    expect(riskFocus.value.allocationConclusion).toContain('未见异常')
    expect(riskFocus.value.i2ConsistencyConclusion).toContain('存在异常')
    expect(riskFocus.value.legacyDeductionNote).toContain('N5-6-1')
    expect(auditConclusion.value).toBe('旧版总体结论')
    expect(auditNote.value).toBe('旧版说明')
  })

  it('persistAll 写入新 storage key', async () => {
    const allResponses = makeMap()
    const onSave = vi.fn()
    const { rows, sampleMeta, addRow, persistAll } = useI6TargetedCheck(allResponses, { onSave })
    addRow({ debitAmount: 50, voucherNo: '记-1' })
    sampleMeta.value.testReasons = ['大额']
    await persistAll()
    expect(onSave).toHaveBeenCalledWith('I6-4-rows', expect.any(String))
    expect(onSave).toHaveBeenCalledWith('I6-4-sample-meta', expect.any(String))
    expect(onSave).toHaveBeenCalledWith('I6-4-risk-focus', expect.any(String))
    expect(onSave).toHaveBeenCalledWith('I6-4-audit-note', expect.any(String))
    expect(onSave).toHaveBeenCalledWith('I6-4-audit-conclusion', expect.any(String))
    const savedRows = JSON.parse(onSave.mock.calls.find((c) => c[0] === 'I6-4-rows')![1])
    expect(savedRows).toHaveLength(1)
    expect(savedRows[0].debitAmount).toBe(50)
  })

  it('syncPopulationFromI62 带入 I6-2 审定合计', async () => {
    const allResponses = makeMap({
      'I6-2-detail-rows': [{ category: 'B', months: [500], aje: 20, rje: 0 }],
    })
    const { syncPopulationFromI62, sampleMeta } = useI6TargetedCheck(allResponses)
    await nextTick()
    const r = syncPopulationFromI62()
    expect(r.ok).toBe(true)
    expect(sampleMeta.value.populationAmount).toBe(520)
    expect(sampleMeta.value.populationDesc).toContain('I6-2')
  })

  it('fillFromSampledVouchers 去重并挂接 I6-2 项目', async () => {
    const allResponses = makeMap({
      'I6-2-detail-rows': [{ category: '智能平台', months: [100], aje: 0, rje: 0 }],
    })
    const { fillFromSampledVouchers, rows } = useI6TargetedCheck(allResponses)
    await nextTick()
    const n1 = fillFromSampledVouchers([
      { voucherNo: '001', voucherDate: '2025-01-01', summary: '智能平台材料', debitAmount: 100 },
    ])
    const n2 = fillFromSampledVouchers([
      { voucherNo: '001', voucherDate: '2025-01-01', summary: '智能平台材料', debitAmount: 100 },
    ])
    expect(n1).toBe(1)
    expect(n2).toBe(0)
    expect(rows.value).toHaveLength(1)
    expect(rows.value[0].projectName).toBe('智能平台')
  })

  it('pushAdjDraftsToI63 写入 I6-3-rows 并去重', async () => {
    const allResponses = makeMap()
    const onSave = vi.fn()
    const { rows, addRow, updateRow, pushAdjDraftsToI63 } = useI6TargetedCheck(allResponses, { onSave })
    addRow({ projectName: 'P1', voucherNo: 'V1', debitAmount: 200 })
    const target = rows.value[0]
    updateRow(target.rowId, 'check1', '√')
    updateRow(target.rowId, 'check2', '√')
    updateRow(target.rowId, 'check3', '×')
    updateRow(target.rowId, 'check4', '√')
    updateRow(target.rowId, 'check5', '√')

    const r1 = await pushAdjDraftsToI63()
    expect(r1.ok).toBe(true)
    expect(r1.added).toBe(2)
    expect(onSave).toHaveBeenCalledWith('I6-3-rows', expect.any(String))

    const r2 = await pushAdjDraftsToI63()
    expect(r2.ok).toBe(false)
    expect(r2.message).toContain('未重复')
  })
})
