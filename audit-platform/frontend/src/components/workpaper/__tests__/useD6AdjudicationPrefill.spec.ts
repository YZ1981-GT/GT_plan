/**
 * useD6Adjudication — Tier B 四表库审定表预填（adjudication_prefill）消费单测
 *
 * spec: .kiro/specs/d-cycle-four-table-extraction-formulas/  (Task 2.2)
 * Requirements: 2.1（无持久化时建行/填未审数 + 自动取数标注）、2.2/2.3（手工优先不覆盖）
 * Property 2（手工优先）、Property 9（无 prefill → 零回归）、Property 11（来源可溯）
 *
 * 覆盖：
 *  1. block1 空 + 有 prefill → 建行、期初/期末未审 = 期初/期末余额、标注 isFourTableSeed、
 *     rowKeys 经正常保存路径持久化。
 *  2. block1 已有持久化行（rowKeys / per-field）→ 不 seed、不覆盖（手工优先）。
 *  3. D6-2 明细已聚合出原值行 → 不 seed（既有明细导入优先，R2.3）。
 *  4. 无 prefill（灰度关/后端未下发）→ 无变化、零回归。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useD6Adjudication, type AdjudicationPrefillRow } from '../composables/useD6Adjudication'
import { useD6CrossSheet } from '../composables/useD6CrossSheet'
import type { ChecklistResponse } from '../composables/useD6FormData'

function makeResponses(entries: Array<[string, string]> = []): Map<string, ChecklistResponse> {
  const map = new Map<string, ChecklistResponse>()
  for (const [item_id, remark] of entries) {
    map.set(item_id, { item_id, conclusion: null, remark })
  }
  return map
}

function setup(opts: {
  responses?: Array<[string, string]>
  prefill?: AdjudicationPrefillRow[] | undefined
}) {
  const allResponses = ref(makeResponses(opts.responses ?? []))
  const crossSheet = useD6CrossSheet({ allResponses })
  const saveImmediate = vi.fn().mockResolvedValue(undefined)
  const debouncedSave = vi.fn()
  const adjudicationPrefill = ref<AdjudicationPrefillRow[] | undefined>(opts.prefill)

  const composable = useD6Adjudication({
    allResponses,
    crossSheet,
    saveImmediate,
    debouncedSave,
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    adjudicationPrefill,
  })
  return { allResponses, saveImmediate, debouncedSave, ...composable }
}

const PREFILL: AdjudicationPrefillRow[] = [
  { code: '1141.01', name: '合同资产-工程A', opening_balance: 800, closing_balance: 1000, block: 'block1', source: 'four-table' },
  { code: '1141.02', name: '合同资产-工程B', opening_balance: 300, closing_balance: 250, block: 'block1', source: 'four-table' },
]

describe('useD6Adjudication — 四表库预填 seed', () => {
  it('block1 空 + 有 prefill → 建行、seed 期初/期末未审、标注自动取数、持久化 rowKeys', () => {
    const { blocks, allResponses, saveImmediate } = setup({ prefill: PREFILL })

    const block1 = blocks.value[0]
    expect(block1.blockKey).toBe('block1')
    const dynamicRows = block1.rows
    expect(dynamicRows.map(r => r.label).sort()).toEqual(['合同资产-工程A', '合同资产-工程B'])

    const rowA = dynamicRows.find(r => r.label === '合同资产-工程A')!
    expect(rowA.priorUnadjusted).toBe(800)
    expect(rowA.currentUnadjusted).toBe(1000)
    expect(rowA.isFourTableSeed).toBe(true) // Property 11 来源可溯

    const rowB = dynamicRows.find(r => r.label === '合同资产-工程B')!
    expect(rowB.priorUnadjusted).toBe(300)
    expect(rowB.currentUnadjusted).toBe(250)

    // rowKeys 走正常保存路径持久化（saveImmediate，不新造键）
    expect(saveImmediate).toHaveBeenCalledWith(
      'D6-1-adj-block1-rowKeys',
      expect.objectContaining({ remark: expect.stringContaining('合同资产-工程A') }),
    )
    // 本地 allResponses 已写入 per-field 未审值
    expect(allResponses.value.get('D6-1-adj-block1-合同资产-工程A-priorUnadjusted')?.remark).toBe('800')
    expect(allResponses.value.get('D6-1-adj-block1-合同资产-工程A-currentUnadjusted')?.remark).toBe('1000')
  })

  it('block1 已有持久化 rowKeys → 不 seed、不覆盖（手工优先 Property 2）', () => {
    const { blocks, saveImmediate } = setup({
      responses: [
        ['D6-1-adj-block1-rowKeys', JSON.stringify(['手工行'])],
        ['D6-1-adj-block1-手工行-currentUnadjusted', '5555'],
      ],
      prefill: PREFILL,
    })

    const labels = blocks.value[0].rows.map(r => r.label)
    // 只应有手工行，不应出现 prefill 的叶子科目名
    expect(labels).toContain('手工行')
    expect(labels).not.toContain('合同资产-工程A')
    expect(labels).not.toContain('合同资产-工程B')
    // 未触发 rowKeys 覆盖保存
    expect(saveImmediate).not.toHaveBeenCalledWith(
      'D6-1-adj-block1-rowKeys',
      expect.objectContaining({ remark: expect.stringContaining('合同资产-工程A') }),
    )
  })

  it('D6-2 明细已聚合出原值行 → 不 seed（既有明细导入优先 R2.3）', () => {
    const detailRows = JSON.stringify([
      { contractType: '工程施工', priorAudited: 111, endAudited: 222 },
    ])
    const { blocks, saveImmediate } = setup({
      responses: [['D6-2-rows', detailRows]],
      prefill: PREFILL,
    })
    const labels = blocks.value[0].rows.map(r => r.label)
    expect(labels).toContain('工程施工')
    expect(labels).not.toContain('合同资产-工程A')
    expect(saveImmediate).not.toHaveBeenCalledWith(
      'D6-1-adj-block1-rowKeys',
      expect.anything(),
    )
  })

  it('无 prefill（灰度关/后端未下发）→ 无变化、零回归', () => {
    const { blocks, saveImmediate, debouncedSave } = setup({ prefill: undefined })
    expect(blocks.value[0].rows).toHaveLength(0)
    expect(saveImmediate).not.toHaveBeenCalled()
    expect(debouncedSave).not.toHaveBeenCalled()
  })
})
