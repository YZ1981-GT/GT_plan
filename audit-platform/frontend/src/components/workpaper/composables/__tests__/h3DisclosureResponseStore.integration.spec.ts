/** H3 披露 Tab 的宿主响应 Map、重挂载与无来源同步回归。 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { effectScope, ref, type EffectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('@/services/apiProxy', () => {
  const api = { get: h.get, put: h.put }
  return { api, apiProxy: api, default: api }
})

import { useH3Disclosure, type DisclosureVariant } from '../useH3Disclosure'
import { useH3FormData, type ChecklistItem } from '../useH3FormData'
import { buildH3SyncPayload, H3_LISTED_SUBTABLE, H3_SOE_SUBTABLE } from '../h3NoteSectionMap'

const stored = (item_id: string, value: unknown): ChecklistItem => ({
  item_id,
  conclusion: null,
  remark: typeof value === 'string' ? value : JSON.stringify(value),
})

function mountStore(
  variant: DisclosureVariant,
  initial: Record<string, unknown>,
  measurementModel: 'cost' | 'fair_value',
) {
  const responses = ref(new Map<string, ChecklistItem>(
    Object.entries(initial).map(([key, value]) => [key, stored(key, value)]),
  ))
  const scope: EffectScope = effectScope()
  let form!: ReturnType<typeof useH3FormData>
  let disclosure!: ReturnType<typeof useH3Disclosure>
  scope.run(() => {
    form = useH3FormData({
      wpId: ref('wp-h3'), projectId: ref('p1'), measurementModel: ref(measurementModel),
      allResponses: responses,
    })
    disclosure = useH3Disclosure({
      allResponses: responses, wpId: ref('wp-h3'), projectId: ref('p1'),
      getValue: form.getValue, setValue: form.setValue, saveImmediate: form.saveImmediate,
      measurementModel: ref(measurementModel), variant: ref(variant),
    })
  })
  return { responses, scope, form, disclosure }
}

describe('H3 披露共用宿主 allResponses', () => {
  beforeEach(() => {
    h.get.mockReset()
    h.put.mockReset().mockResolvedValue([])
  })

  const cases = [
    {
      name: '上市成本', variant: 'listed' as const, model: 'cost' as const,
      rowKey: 'cost-original', row: { rowId: 'lc', category: '写字楼', beginBalance: 120, increase: 30, decrease: 10 },
      text: '上市成本说明', hierarchy: 210,
    },
    {
      name: '上市公允价值', variant: 'listed' as const, model: 'fair_value' as const,
      rowKey: 'fair-change', row: { rowId: 'lf', category: '商铺', beginBalance: 320, increase: 40, decrease: 5, fairChange: 66 },
      text: '上市公允说明', hierarchy: 421,
    },
    {
      name: '国企成本', variant: 'soe' as const, model: 'cost' as const,
      rowKey: 'soe-cost', row: { rowId: 'sc', category: '厂房', beginBalance: 520, buyOrProvision: 50, transferIn: 20, disposal: 8, transferOut: 2 },
      text: '国企成本说明', hierarchy: 610,
    },
    {
      name: '国企公允价值', variant: 'soe' as const, model: 'fair_value' as const,
      rowKey: 'soe-fair-change', row: { rowId: 'sf', category: '土地', beginBalance: 720, buyOrProvision: 30, transferIn: 10, fairChange: 88, disposal: 5, transferOut: 1 },
      text: '国企公允说明', hierarchy: 842,
    },
  ]

  it.each(cases)('$name：非零行、说明与层次在卸载后从同一 Map 读回', ({ variant, model, rowKey, row, text, hierarchy }) => {
    const prefix = `H3-disc-${variant}`
    const initial = {
      [`${prefix}-rows-${rowKey}`]: [row],
      [`${prefix}-text-${rowKey}`]: text,
      [`${prefix}-fv-hierarchy`]: [{ rowId: 'fv1', category: '样本资产', level: '3', fairValue: hierarchy, valuationTechnique: '收益法', keyInputs: '折现率' }],
    }
    const first = mountStore(variant, initial, model)
    expect(first.form.allResponses).toBe(first.responses)
    expect(first.disclosure.getSectionRows(rowKey)[0]).toMatchObject(row)
    expect(first.disclosure.sectionTexts[rowKey]).toBe(text)
    expect(first.disclosure.fvHierarchyRows.value[0]).toMatchObject({ fairValue: hierarchy, valuationTechnique: '收益法' })
    first.scope.stop()

    const remounted = mountStore(variant, initial, model)
    expect(remounted.disclosure.getSectionRows(rowKey)[0]).toMatchObject(row)
    expect(remounted.disclosure.sectionTexts[rowKey]).toBe(text)
    expect(remounted.disclosure.fvHierarchyTotalsByLevel.value.total).toBe(hierarchy)
    remounted.scope.stop()
  })

  it('编辑行、文字与层次先更新宿主 Map，再经现有 checklist 批量保存', async () => {
    const mounted = mountStore('listed', {
      'H3-disc-listed-rows-cost-original': [{ rowId: 'r1', category: '写字楼', beginBalance: 100 }],
    }, 'cost')
    const row = mounted.disclosure.getSectionRows('cost-original')[0]
    row.increase = 55
    mounted.disclosure.updateRow('cost-original', row)
    mounted.disclosure.updateText('cost-original', '已编辑说明')
    mounted.disclosure.addFvHierarchyRow({ category: '写字楼', level: '2', fairValue: 155 })

    expect(JSON.parse(mounted.responses.value.get('H3-disc-listed-rows-cost-original')!.remark!)[0].increase).toBe(55)
    expect(mounted.responses.value.get('H3-disc-listed-text-cost-original')?.remark).toBe('已编辑说明')
    expect(JSON.parse(mounted.responses.value.get('H3-disc-listed-fv-hierarchy')!.remark!)[0].fairValue).toBe(155)

    await mounted.form.flushPendingSaves()
    expect(h.put).toHaveBeenCalledTimes(1)
    expect(h.put).toHaveBeenCalledWith('/api/workpapers/wp-h3/checklist-responses', {
      project_id: 'p1',
      items: expect.arrayContaining([
        expect.objectContaining({ item_id: 'H3-disc-listed-rows-cost-original' }),
        expect.objectContaining({ item_id: 'H3-disc-listed-text-cost-original', remark: '已编辑说明' }),
        expect.objectContaining({ item_id: 'H3-disc-listed-fv-hierarchy' }),
      ]),
    })
    mounted.scope.stop()
  })

  it('默认展示行没有来源时不推零表；首次编辑落入 Map 后才取得同步来源', () => {
    const mounted = mountStore('listed', {}, 'cost')
    expect(mounted.disclosure.getSectionRows('cost-original')).toHaveLength(2)
    expect(mounted.disclosure.getSectionRowsForSync('cost-original')).toBeUndefined()

    const empty = buildH3SyncPayload({
      variant: 'listed', measurementModel: 'cost',
      costOriginalRows: mounted.disclosure.getSectionRowsForSync('cost-original'),
      projectId: 'p1', wpId: 'wp-h3', sectionTexts: { conversion: '仅更新说明' },
    })
    expect(empty.sub_table_data).not.toHaveProperty(H3_LISTED_SUBTABLE.cost)
    expect(empty.sub_table_data._removed_table_keys).not.toContain(H3_LISTED_SUBTABLE.cost)
    expect(empty.sub_table_data._removed_table_keys).not.toContain(H3_LISTED_SUBTABLE.fair)

    const row = mounted.disclosure.getSectionRows('cost-original')[0]
    row.beginBalance = 99
    mounted.disclosure.updateRow('cost-original', row)
    const withSource = buildH3SyncPayload({
      variant: 'listed', measurementModel: 'cost',
      costOriginalRows: mounted.disclosure.getSectionRowsForSync('cost-original'),
      projectId: 'p1', wpId: 'wp-h3',
    })
    expect(withSource.sub_table_data).toHaveProperty(H3_LISTED_SUBTABLE.cost)
    mounted.scope.stop()
  })

  it('上市与国企 Tab 都把宿主 Map 显式传给 useH3FormData', () => {
    const root = resolve(__dirname, '../..')
    for (const file of ['h3/core/H3TabDisclosureListed.vue', 'h3/core/H3TabDisclosureSoe.vue']) {
      const source = readFileSync(resolve(root, file), 'utf-8')
      expect(source, file).toMatch(/useH3FormData\(\{[\s\S]*?allResponses:\s*toRef\(props,\s*['"]allResponses['"]\)/)
    }
  })

  it('国企无来源时同样不推零表', () => {
    const payload = buildH3SyncPayload({ variant: 'soe', measurementModel: 'fair_value', projectId: 'p1', wpId: 'wp-h3' })
    expect(payload.sub_table_data).not.toHaveProperty(H3_SOE_SUBTABLE.fair)
    expect(payload.sub_table_data._removed_table_keys).not.toContain(H3_SOE_SUBTABLE.cost)
    expect(payload.sub_table_data._removed_table_keys).not.toContain(H3_SOE_SUBTABLE.fair)
  })
})
