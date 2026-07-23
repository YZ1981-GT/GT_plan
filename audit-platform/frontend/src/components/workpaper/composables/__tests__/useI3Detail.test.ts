/**
 * useI3Detail — 单元测试（原值/减值双表滚动）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useI3Detail,
  calcRollEnding,
  calcAudited,
  I3_DETAIL_SECTION_LABELS,
} from '../useI3Detail'
import type { ChecklistItem } from '../useI3FormData'

function createAllResponses(data?: Record<string, any>) {
  const map = new Map<string, ChecklistItem>()
  if (data) {
    for (const [key, value] of Object.entries(data)) {
      map.set(key, {
        item_id: key,
        conclusion: null,
        remark: typeof value === 'string' ? value : JSON.stringify(value),
      })
    }
  }
  return ref(map)
}

describe('calcRollEnding / calcAudited', () => {
  it('期末 = 期初 + 增加 - 减少', () => {
    expect(calcRollEnding(1000, 200, 50)).toBe(1150)
  })
  it('审定 = 未审 + 调整', () => {
    expect(calcAudited(1150, -50)).toBe(1100)
  })
})

describe('useI3Detail', () => {
  let wpId: ReturnType<typeof ref<string>>
  let allResponses: ReturnType<typeof createAllResponses>
  let onSave: ReturnType<typeof vi.fn>

  beforeEach(() => {
    wpId = ref('wp-i3-2')
    allResponses = createAllResponses()
    onSave = vi.fn()
  })

  it('区段为原值/减值/入账/基础四段', () => {
    expect(I3_DETAIL_SECTION_LABELS).toEqual(['原值滚动', '减值滚动', '入账测算', '基础信息'])
  })

  it('原值滚动公式正确并回写兼容字段', () => {
    const { importRows, rows } = useI3Detail(wpId, allResponses, { onSave })
    importRows([
      {
        investee: '甲公司',
        costOpening: 1000000,
        costIncrease: 200000,
        costDecrease: 50000,
        costUnadj: 1150000,
        costAje: 0,
        impOpening: 100000,
        impIncrease: 30000,
        impDecrease: 0,
        impUnadj: 130000,
        impAje: 0,
      },
    ])
    const row = rows.value[0]
    expect(row.costEnding).toBe(1150000)
    expect(row.costAudited).toBe(1150000)
    expect(row.impEnding).toBe(130000)
    expect(row.impAudited).toBe(130000)
    expect(row.goodwillOriginal).toBe(1150000)
    expect(row.currentImpairment).toBe(30000)
    expect(row.accImpairmentEnd).toBe(130000)
    expect(row.goodwillNetValue).toBe(1020000) // 1150000-130000
  })

  it('兼容旧字段加载', () => {
    allResponses = createAllResponses({
      'I3-2-rows': [
        {
          investee: '旧行',
          goodwillOriginal: 500000,
          accImpairmentBegin: 80000,
          currentImpairment: 20000,
        },
      ],
    })
    const { rows } = useI3Detail(wpId, allResponses, { onSave })
    expect(rows.value[0].costOpening).toBe(500000)
    expect(rows.value[0].impOpening).toBe(80000)
    expect(rows.value[0].impIncrease).toBe(20000)
    expect(rows.value[0].impEnding).toBe(100000)
    expect(rows.value[0].goodwillNetValue).toBe(rows.value[0].costAudited - rows.value[0].impAudited)
  })

  it('入账测算商誉 = 合并成本 - 公允份额', () => {
    const { importRows, rows } = useI3Detail(wpId, allResponses, { onSave })
    importRows([{ investee: '乙', mergerCost: 800000, netAssetFairValue: 500000 }])
    expect(rows.value[0].entryGoodwillCalc).toBe(300000)
  })

  it('本期减值不可为负（不可转回）', () => {
    const { importRows, updateCell, rows } = useI3Detail(wpId, allResponses, { onSave })
    importRows([{ investee: '丙', impOpening: 100, impIncrease: 50 }])
    updateCell(0, 'impIncrease', -20)
    expect(rows.value[0].impIncrease).toBe(0)
    expect(rows.value[0].currentImpairment).toBe(0)
  })

  it('合计行汇总正确', () => {
    const { importRows, summaryRow } = useI3Detail(wpId, allResponses, { onSave })
    importRows([
      { investee: 'A', costOpening: 100, costUnadj: 100, impOpening: 10, impUnadj: 10 },
      { investee: 'B', costOpening: 200, costUnadj: 200, impOpening: 20, impUnadj: 20 },
    ])
    expect(summaryRow.value.costAudited).toBe(300)
    expect(summaryRow.value.impAudited).toBe(30)
    expect(summaryRow.value.goodwillNetValue).toBe(270)
  })

  it('与 I3-1 交叉验证差异警示', () => {
    const adjOriginal = ref(1000)
    const adjImpairment = ref(100)
    const adjNet = ref(900)
    const { importRows, crossValidation } = useI3Detail(wpId, allResponses, {
      onSave,
      adjGoodwillOriginalSubtotal: adjOriginal,
      adjAccImpairmentSubtotal: adjImpairment,
      adjNetValueSubtotal: adjNet,
    })
    importRows([{ investee: 'A', costOpening: 1100, costUnadj: 1100, impOpening: 100, impUnadj: 100 }])
    expect(crossValidation.value.hasOriginalWarning).toBe(true)
    expect(crossValidation.value.goodwillOriginalDiff).toBe(100)
    expect(crossValidation.value.hasAnyWarning).toBe(true)
  })

  it('编辑增加后自动同步未审（当未审=期末）', () => {
    const { importRows, updateCell, rows } = useI3Detail(wpId, allResponses, { onSave })
    importRows([{ investee: 'D', costOpening: 1000, costIncrease: 0, costUnadj: 1000 }])
    updateCell(0, 'costIncrease', 200)
    expect(rows.value[0].costEnding).toBe(1200)
    expect(rows.value[0].costUnadj).toBe(1200)
    expect(rows.value[0].costAudited).toBe(1200)
  })

  it('syncImpIncreaseFromI3_6 按 CGU 回写本期计提', () => {
    const { importRows, syncImpIncreaseFromI3_6, rows } = useI3Detail(wpId, allResponses, { onSave })
    importRows([
      { investee: '甲', cguName: 'CGU-A', costAudited: 800, costUnadj: 800, impOpening: 0, impUnadj: 0 },
      { investee: '乙', cguName: 'CGU-A', costAudited: 200, costUnadj: 200, impOpening: 0, impUnadj: 0 },
    ])
    // costAudited is formula from unadj+aje - set via costUnadj
    rows.value[0].costUnadj = 800
    rows.value[1].costUnadj = 200
    const n = syncImpIncreaseFromI3_6({ 'CGU-A': 1000 })
    expect(n).toBe(2)
    expect(rows.value[0].impIncrease + rows.value[1].impIncrease).toBeCloseTo(1000, 1)
  })

  it('syncAjeFromI3_3 按被投资单位回写调整', () => {
    const { importRows, syncAjeFromI3_3, rows } = useI3Detail(wpId, allResponses, { onSave })
    importRows([{ investee: '甲公司', costUnadj: 100, impUnadj: 0 }])
    const result = syncAjeFromI3_3({ '甲公司': { costAje: 50, impAje: 20, net: 30 } })
    expect(result.updated).toBe(1)
    expect(result.applied).toEqual(['甲公司'])
    expect(rows.value[0].costAje).toBe(50)
    expect(rows.value[0].impAje).toBe(20)
    expect(rows.value[0].costAudited).toBe(150)
    expect(rows.value[0].impAudited).toBe(20)
  })

  it('syncAjeFromI3_3 报告未匹配被投资单位', () => {
    const { importRows, syncAjeFromI3_3 } = useI3Detail(wpId, allResponses, { onSave })
    importRows([{ investee: '甲公司', costUnadj: 100 }])
    const result = syncAjeFromI3_3({
      '甲公司': { costAje: 10, impAje: 0, net: 10 },
      '乙公司': { costAje: 5, impAje: 0, net: 5 },
      '未指定': { costAje: 0, impAje: 8, net: -8 },
    })
    expect(result.updated).toBe(1)
    expect(result.unmatched).toEqual(['乙公司'])
    expect(result.unspecified).toBe(true)
  })
})
