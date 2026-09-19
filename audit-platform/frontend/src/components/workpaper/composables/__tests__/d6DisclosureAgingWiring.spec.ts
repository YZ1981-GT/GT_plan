/**
 * D6 披露表组合明细账龄枚举贯通守卫（Requirement 6.3/6.4，Property 11）。
 *
 * 背景（2026-08-01 Wave 4.1 复核发现的真实缺口）：D6 附注模板国企侧「组合计提项目」
 * 分表（源模板「工程施工」「质量保证金」两张，headers=「账 龄」）的行维度本就是
 * 账龄段，但披露 Tab 的账龄列此前只是 `el-input` 自由文本，与 D1/D2/D7 已统一的
 * 项目账龄枚举（`useAgingConfig`）割裂 —— 审计师手打的账龄段名可能与项目配置
 * 不一致，导致跨底稿聚合失真。
 *
 * 修法：新增 `useD6Disclosure.fillGroupAgingBands(groupIndex, segmentLabels)`
 * （只补缺失段、不覆盖已有行金额）+ 账龄列改 `el-select`（`allow-create` 保留自定义，
 * 因组合分表行维度理论上可以是任意分类不限于账龄）+「按账龄段生成」按钮，
 * 与 D1 `fillPortfolioAgingBands` 同范式。
 *
 * spec: .kiro/specs/d-cycle-extraction-chain-completion/ Task 4.1
 */
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useD6Disclosure } from '../useD6Disclosure'
import type { ChecklistResponse } from '../useD6FormData'

function makeOptions() {
  const allResponses = ref(new Map<string, ChecklistResponse>())
  return {
    allResponses,
    crossSheet: {
      adjudicationForDisclosure: ref({}) as any,
      eclForDisclosure: ref({}) as any,
      impairmentChangesForDisclosure: ref({}) as any,
    },
    saveImmediate: async () => {},
    debouncedSave: () => {},
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
  }
}

describe('useD6Disclosure.fillGroupAgingBands', () => {
  it('对空组合按段全量生成行（其余数值字段清零，宁缺勿造）', () => {
    const d6 = useD6Disclosure(makeOptions())
    d6.addGroup()
    const added = d6.fillGroupAgingBands(0, ['1年以内', '1至2年', '2年以上'])
    expect(added).toBe(3)
    const rows = d6.groupedDetails.value[0].rows
    expect(rows.map(r => r.label)).toEqual(['1年以内', '1至2年', '2年以上'])
    for (const r of rows) {
      expect(r.balance).toBe(0)
      expect(r.provision).toBe(0)
    }
  })

  it('只补缺失段，不重复已存在的账龄段行', () => {
    const d6 = useD6Disclosure(makeOptions())
    d6.addGroup()
    d6.fillGroupAgingBands(0, ['1年以内', '1至2年'])
    const added2 = d6.fillGroupAgingBands(0, ['1年以内', '1至2年', '2年以上'])
    expect(added2).toBe(1)
    expect(d6.groupedDetails.value[0].rows).toHaveLength(3)
  })

  it('不覆盖已有行的手工录入金额（手工优先）', () => {
    const d6 = useD6Disclosure(makeOptions())
    d6.addGroup()
    d6.fillGroupAgingBands(0, ['1年以内'])
    const rowId = d6.groupedDetails.value[0].rows[0].rowId
    d6.updateGroupedCell(0, rowId, 'balance', 12345)
    d6.fillGroupAgingBands(0, ['1年以内', '1至2年'])
    const row = d6.groupedDetails.value[0].rows.find(r => r.rowId === rowId)
    expect(row?.balance).toBe(12345)
  })

  it('无缺失段时返回 0（幂等）', () => {
    const d6 = useD6Disclosure(makeOptions())
    d6.addGroup()
    d6.fillGroupAgingBands(0, ['1年以内'])
    const added = d6.fillGroupAgingBands(0, ['1年以内'])
    expect(added).toBe(0)
  })

  it('反向自检：越界 groupIndex 不抛错也不产生变更', () => {
    const d6 = useD6Disclosure(makeOptions())
    d6.addGroup()
    expect(() => d6.fillGroupAgingBands(99, ['1年以内'])).not.toThrow()
    expect(d6.groupedDetails.value[0].rows).toHaveLength(0)
  })
})
