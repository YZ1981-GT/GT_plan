/**
 * B22A IT 子区行身份守卫（BC-53 同型改造）。
 *
 * spec: b-cycle-sync-foundation-and-first-canary
 *
 * IT 子区是与 COSO tab **并存的第二套行存储**（前缀 `B22A-it-summary` /
 * `-it-system` / `-it-sod`），原用 `{prefix}-{index}-{field}` 下标键 +
 * shift 搬迁删行。本文件钉死改造后的三条行为：
 *   ① legacy 下标数据自动迁移
 *   ② 删中间行剩余行内容不串台
 *   ③ 行数取自行数组长度（不再读 count 键）
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, effectScope } from 'vue'

function setup(seed: Record<string, any> = {}) {
  const allResponses = ref(new Map<string, any>(Object.entries(seed)))
  const saveFn = vi.fn().mockResolvedValue(undefined)
  return { allResponses, saveFn }
}

describe('IT 概要行（B22A-it-summary）', () => {
  it('legacy 下标数据自动迁移为行数组', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')
    const scope = effectScope()
    scope.run(() => {
      const { allResponses, saveFn } = setup({
        'B22A-it-summary-count': { item_id: 'B22A-it-summary-count', conclusion: null, remark: '2', wp_ref: null },
        'B22A-it-summary-1-kind': { item_id: 'B22A-it-summary-1-kind', conclusion: null, remark: 'ERP系统', wp_ref: null },
        'B22A-it-summary-2-kind': { item_id: 'B22A-it-summary-2-kind', conclusion: null, remark: 'OA系统', wp_ref: null },
      })
      const m = useB22AControlMatrix(allResponses, saveFn)

      const rows = m.getItSummaryRows()
      expect(rows).toHaveLength(2)
      expect(rows[0].kind).toBe('ERP系统')
      expect(rows[1].kind).toBe('OA系统')
      // 迁移后落库了行数组
      expect(allResponses.value.get('B22A-it-summary-rows')).toBeDefined()
    })
    scope.stop()
  })

  it('addItSummaryRow 追加一行，行数递增', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')
    const scope = effectScope()
    scope.run(() => {
      const { allResponses, saveFn } = setup()
      const m = useB22AControlMatrix(allResponses, saveFn)

      expect(m.getItSummaryRows()).toHaveLength(0)
      m.addItSummaryRow()
      expect(m.getItSummaryRows()).toHaveLength(1)
      m.addItSummaryRow()
      expect(m.getItSummaryRows()).toHaveLength(2)
    })
    scope.stop()
  })

  it('setItSummaryField 写字段后能读回', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')
    const scope = effectScope()
    scope.run(() => {
      const { allResponses, saveFn } = setup()
      const m = useB22AControlMatrix(allResponses, saveFn)

      m.addItSummaryRow()
      m.setItSummaryField(1, 'kind', '金蝶云')
      expect(m.getItSummaryRows()[0].kind).toBe('金蝶云')
    })
    scope.stop()
  })

  it('🔴 删中间行：剩余行内容不串台', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')
    const scope = effectScope()
    scope.run(() => {
      const { allResponses, saveFn } = setup({
        'B22A-it-summary-count': { item_id: 'B22A-it-summary-count', conclusion: null, remark: '3', wp_ref: null },
        'B22A-it-summary-1-kind': { item_id: 'B22A-it-summary-1-kind', conclusion: null, remark: '甲系统', wp_ref: null },
        'B22A-it-summary-2-kind': { item_id: 'B22A-it-summary-2-kind', conclusion: null, remark: '乙系统', wp_ref: null },
        'B22A-it-summary-3-kind': { item_id: 'B22A-it-summary-3-kind', conclusion: null, remark: '丙系统', wp_ref: null },
      })
      const m = useB22AControlMatrix(allResponses, saveFn)

      m.removeItSummaryRow(2)

      const rows = m.getItSummaryRows()
      expect(rows).toHaveLength(2)
      // 改造前 shift 搬迁会把「丙系统」搬到位置 2；改造后位置 2 就是丙系统
      // 且它是原第 3 行本体（身份未变），不是被顶替的第 2 行
      expect(rows.map((r) => r.kind)).toEqual(['甲系统', '丙系统'])
      expect(rows.map((r) => r.index)).toEqual([1, 2])
    })
    scope.stop()
  })

  it('删行后行数立即反映（不依赖 count 键）', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')
    const scope = effectScope()
    scope.run(() => {
      const { allResponses, saveFn } = setup()
      const m = useB22AControlMatrix(allResponses, saveFn)

      m.addItSummaryRow()
      m.addItSummaryRow()
      m.addItSummaryRow()
      expect(m.getItSummaryRows()).toHaveLength(3)
      m.removeItSummaryRow(1)
      expect(m.getItSummaryRows()).toHaveLength(2)
    })
    scope.stop()
  })

  it('越界删除不改数据', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')
    const scope = effectScope()
    scope.run(() => {
      const { allResponses, saveFn } = setup()
      const m = useB22AControlMatrix(allResponses, saveFn)

      m.addItSummaryRow()
      m.removeItSummaryRow(0)
      m.removeItSummaryRow(5)
      expect(m.getItSummaryRows()).toHaveLength(1)
    })
    scope.stop()
  })
})

describe('IT 系统清单行（B22A-it-system）与 SoD 行（B22A-it-sod）同口径', () => {
  it('三套前缀表各自独立（互不污染）', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')
    const scope = effectScope()
    scope.run(() => {
      const { allResponses, saveFn } = setup()
      const m = useB22AControlMatrix(allResponses, saveFn)

      m.addItSummaryRow()
      m.addItSystemRow()
      m.addItSystemRow()

      expect(m.getItSummaryRows()).toHaveLength(1)
      expect(m.getItSystemRows()).toHaveLength(2)
      // 各自独立的行数组 item
      expect(allResponses.value.get('B22A-it-summary-rows')).toBeDefined()
      expect(allResponses.value.get('B22A-it-system-rows')).toBeDefined()
    })
    scope.stop()
  })

  it('IT 系统清单删中间行不串台', async () => {
    const { useB22AControlMatrix } = await import('../composables/useB22AControlMatrix')
    const scope = effectScope()
    scope.run(() => {
      const { allResponses, saveFn } = setup()
      const m = useB22AControlMatrix(allResponses, saveFn)

      m.addItSystemRow()
      m.addItSystemRow()
      m.addItSystemRow()
      m.setItSystemField(1, 'process', 'A')
      m.setItSystemField(2, 'process', 'B')
      m.setItSystemField(3, 'process', 'C')

      m.removeItSystemRow(2)

      expect(m.getItSystemRows().map((r) => r.process)).toEqual(['A', 'C'])
    })
    scope.stop()
  })
})
