/**
 * useI3CrossSheet — 跨表联动测试（合并确认减值 / 明细聚合）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useI3CrossSheet, resolveAdjustmentInvestee } from '../useI3CrossSheet'

function makeResponses(data: Record<string, any>) {
  const map = new Map<string, any>()
  for (const [k, v] of Object.entries(data)) {
    map.set(k, { item_id: k, conclusion: null, remark: JSON.stringify(v) })
  }
  return ref(map)
}

describe('useI3CrossSheet', () => {
  it('I3-6 优先使用 consolidatedGwImpairment 汇总至 I3-1', () => {
    const all = makeResponses({
      'I3-6-rows': [
        {
          cguName: 'CGU-A',
          impairmentAmount: 750000,
          goodwillImpairment: 750000,
          consolidatedGwImpairment: 600000,
          recoverableAmount: 100,
        },
      ],
    })
    const { impairmentResult, impairmentByCgu } = useI3CrossSheet(all)
    expect(impairmentResult.value.totalImpairment).toBe(600000)
    expect(impairmentByCgu.value['CGU-A']).toBe(600000)
  })

  it('无 consolidated 时回退 goodwillImpairment', () => {
    const all = makeResponses({
      'I3-6-rows': [{ cguName: 'CGU-B', goodwillImpairment: 100000 }],
    })
    const { impairmentResult } = useI3CrossSheet(all)
    expect(impairmentResult.value.totalImpairment).toBe(100000)
  })

  it('I3-2 优先 costAudited / impAudited', () => {
    const all = makeResponses({
      'I3-2-rows': [
        {
          investee: '甲',
          cguName: 'CGU-A',
          costAudited: 2000,
          goodwillOriginal: 999,
          impAudited: 300,
          accImpairmentEnd: 111,
          impIncrease: 50,
          goodwillNetValue: 1700,
        },
      ],
    })
    const { detailTotals } = useI3CrossSheet(all)
    expect(detailTotals.value.goodwillOriginalTotal).toBe(2000)
    expect(detailTotals.value.accImpairmentTotal).toBe(300)
    expect(detailTotals.value.currentImpairmentTotal).toBe(50)
    expect(detailTotals.value.netValueTotal).toBe(1700)
  })

  it('I3-7 recoverableDetailByCgu 拆分公允与使用价值', () => {
    const all = makeResponses({
      'I3-7-rows': [
        {
          cguName: 'CGU-A',
          fairValueLessCost: 800,
          valueInUse: 1200,
          recoverableAmount: 1200,
        },
      ],
    })
    const { recoverableByCgu, recoverableDetailByCgu } = useI3CrossSheet(all)
    expect(recoverableByCgu.value['CGU-A']).toBe(1200)
    expect(recoverableDetailByCgu.value['CGU-A'].valueInUse).toBe(1200)
    expect(recoverableDetailByCgu.value['CGU-A'].fairValueLessDisposal).toBe(800)
  })

  it('resolveAdjustmentInvestee 从说明匹配', () => {
    expect(resolveAdjustmentInvestee(
      { description: '计提商誉减值-子公司甲' },
      ['子公司甲', '子公司乙'],
    )).toBe('子公司甲')
  })

  it('resolveAdjustmentInvestee 按 CGU 唯一映射解析被投资单位', () => {
    expect(resolveAdjustmentInvestee(
      { description: '计提商誉减值-CGU甲' },
      ['子公司甲', '子公司乙'],
      { 'CGU甲': ['子公司甲'] },
    )).toBe('子公司甲')
  })

  it('ajeVariances 识别 I3-3 与 I3-2 账项差异', () => {
    const all = makeResponses({
      'I3-2-rows': [{ investee: '甲公司', costAje: 0, impAje: 0 }],
      'I3-3-rows': [
        {
          description: '计提减值',
          investee: '甲公司',
          accountCode: '1711',
          accountName: '商誉',
          entryType: 'AJE',
          debitAmount: 0,
          creditAmount: 100,
        },
      ],
    })
    const { ajeVariances } = useI3CrossSheet(all)
    expect(ajeVariances.value).toHaveLength(1)
    expect(ajeVariances.value[0].investee).toBe('甲公司')
    expect(ajeVariances.value[0].adjImpAje).toBe(100)
    expect(ajeVariances.value[0].impDiff).toBe(100)
  })
})
