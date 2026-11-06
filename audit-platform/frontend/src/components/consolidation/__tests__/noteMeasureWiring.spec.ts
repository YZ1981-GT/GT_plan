import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ConsolNoteGridCell from '../ConsolNoteGridCell.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const HERE = dirname(fileURLToPath(import.meta.url))
const consolSource = readFileSync(resolve(HERE, '../ConsolNoteTab.vue'), 'utf-8')
const disclosureSource = readFileSync(resolve(HERE, '../../../views/DisclosureEditor.vue'), 'utf-8')

beforeEach(() => {
  setActivePinia(createPinia())
  const prefs = useDisplayPrefsStore()
  prefs.setUnit('wan')
  prefs.setShowZero(true)
})

describe('附注 measure kind 屏幕接线', () => {
  it('ConsolNoteGridCell 按 kind 显示：只有 amount 按万元缩放', () => {
    const amount = mount(ConsolNoteGridCell, { props: { value: 10000, label: '金额', editable: false, measureKind: 'amount' } })
    const count = mount(ConsolNoteGridCell, { props: { value: 10000, label: '数量', editable: false, measureKind: 'count' } })
    const ratio = mount(ConsolNoteGridCell, { props: { value: 20, label: '比例', editable: false, measureKind: 'ratio', ratioScale: 'percent_points' } })
    expect(amount.text()).toBe('1.00')
    expect(count.text()).toBe('10,000')
    expect(ratio.text()).toBe('20.00%')
  })

  it('合并附注普通 + 全屏的每个叶子格都传 kind/scale（分母非空）', () => {
    const tags = [...consolSource.matchAll(/<ConsolNoteGridCell\b[\s\S]*?\/>/g)].map((m) => m[0])
    expect(tags.length).toBeGreaterThanOrEqual(8)
    for (const tag of tags) {
      expect(tag).toContain(':measure-kind=')
      expect(tag).toContain(':ratio-scale=')
    }
    expect(consolSource).toContain('columnIds: Array.isArray(sec.column_ids)')
    expect(consolSource).toContain('measureStatus: sec.measure_status')
  })

  it('单体附注唯一数值格模板改用 GtMeasureCell，不再硬当 amount', () => {
    const tags = [...disclosureSource.matchAll(/<GtMeasureCell\b[\s\S]*?\/>/g)].map((m) => m[0])
    expect(tags).toHaveLength(2)
    for (const tag of tags) {
      expect(tag).toContain(':kind="disclosureMeasureKind(headerIdx)"')
      expect(tag).toContain(':ratio-scale="disclosureRatioScale(headerIdx)"')
    }
    expect(disclosureSource).not.toContain('<GtAmountCell')
    expect(disclosureSource).toContain(':column-key-for="disclosureColumnKey"')
    expect(disclosureSource).toContain(':fixed-for="disclosureFixedFor"')
  })
})
