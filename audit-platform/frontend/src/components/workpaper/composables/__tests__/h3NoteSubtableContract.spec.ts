/**
 * H3 投资性房地产披露子表 ↔ note_template 契约（共享 helper P1~P6）+ H3 专属守卫。
 *
 * spec: h3-investment-property-disclosure-alignment (Task 7)
 */
import { describe, expect, it } from 'vitest'
import { columnDeclState, runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  H3_LEGACY_OBSOLETE_TABLES,
  H3_LISTED_SUBTABLE,
  H3_NOTE_SECTION,
  H3_SOE_SUBTABLE,
  buildH3ListedColumns,
  buildH3SoeColumns,
  buildH3SyncPayload,
} from '../h3NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'H3',
  variants: [
    {
      variant: 'listed',
      section: H3_NOTE_SECTION.listed,
      subtables: H3_LISTED_SUBTABLE,
      columns: buildH3ListedColumns(),
    },
    {
      variant: 'soe',
      section: H3_NOTE_SECTION.soe,
      subtables: H3_SOE_SUBTABLE,
      columns: buildH3SoeColumns(),
    },
  ],
})

const CTX = { projectId: 'p1', wpId: 'wp1' }

describe('H3 披露结构专属守卫', () => {
  it('章节号正确，且不得引用 八、22（固定资产章节）', () => {
    expect(H3_NOTE_SECTION.listed).toBe('五、21')
    expect(H3_NOTE_SECTION.soe).toBe('八、21')
    expect(Object.values(H3_NOTE_SECTION)).not.toContain('八、22')
  })

  it('国企两级表头带 group，rowspan=2 的期初/期末列不带 group', () => {
    const s = buildH3SoeColumns()
    expect(columnDeclState(s['以成本计量'])).toBe('group')
    expect(columnDeclState(s['以公允价值计量'])).toBe('group')
    const cost = s['以成本计量']
    expect(cost.find((c) => c.key === 'begin')?.group).toBeUndefined()
    expect(cost.find((c) => c.key === 'end')?.group).toBeUndefined()
    expect(cost.filter((c) => c.group === '本期增加')).toHaveLength(2)
    expect(cost.filter((c) => c.group === '本期减少')).toHaveLength(2)
    const fair = s['以公允价值计量']
    expect(fair.filter((c) => c.group === '本期增加')).toHaveLength(3)
    expect(fair.filter((c) => c.group === '本期减少')).toHaveLength(2)
  })

  it('上市三表为单级（flat）列转置', () => {
    const l = buildH3ListedColumns()
    for (const name of Object.values(H3_LISTED_SUBTABLE)) {
      expect(columnDeclState(l[name])).toBe('flat')
    }
    expect(l[H3_LISTED_SUBTABLE.cost].map((c) => c.key)).toEqual(
      ['label', '房屋、建筑物', '土地使用权', '在建工程', '合计'],
    )
  })

  it('载荷行是业务键 dict，不得是位置化 values 数组', () => {
    const rows = [{ category: '房屋、建筑物', beginBalance: 100, increase: 20, decrease: 5 }]
    for (const variant of ['listed', 'soe'] as const) {
      const p = buildH3SyncPayload({
        variant, measurementModel: 'cost', costOriginalRows: rows, ...CTX,
      })
      const names = variant === 'listed' ? H3_LISTED_SUBTABLE : H3_SOE_SUBTABLE
      const table = p.sub_table_data[names.cost] as Record<string, unknown>[]
      expect(Array.isArray(table)).toBe(true)
      for (const r of table) {
        expect(r).not.toHaveProperty('values')
        expect(typeof r.label).toBe('string')
      }
    }
  })

  it('计量模式互斥：只推选中模式的表，另一模式进 _removed_table_keys', () => {
    const cost = buildH3SyncPayload({ variant: 'soe', measurementModel: 'cost', ...CTX })
    expect(Object.keys(cost.sub_table_data)).toContain(H3_SOE_SUBTABLE.cost)
    expect(Object.keys(cost.sub_table_data)).not.toContain(H3_SOE_SUBTABLE.fair)
    expect(cost.sub_table_data._removed_table_keys).toContain(H3_SOE_SUBTABLE.fair)

    const fair = buildH3SyncPayload({ variant: 'soe', measurementModel: 'fair_value', ...CTX })
    expect(Object.keys(fair.sub_table_data)).toContain(H3_SOE_SUBTABLE.fair)
    expect(fair.sub_table_data._removed_table_keys).toContain(H3_SOE_SUBTABLE.cost)
  })

  it('历史孤儿表名全部进 _removed_table_keys', () => {
    const p = buildH3SyncPayload({ variant: 'listed', measurementModel: 'cost', ...CTX })
    const removed = p.sub_table_data._removed_table_keys as string[]
    for (const legacy of H3_LEGACY_OBSOLETE_TABLES) {
      expect(removed).toContain(legacy)
    }
  })

  it('国企成本表 15 行 5 层且账面价值层 = 原值 − 折旧 − 减值', () => {
    const p = buildH3SyncPayload({
      variant: 'soe',
      measurementModel: 'cost',
      costOriginalRows: [{ category: '房屋、建筑物', beginBalance: 1000, increase: 200, decrease: 50 }],
      costDepRows: [{ category: '房屋、建筑物', beginBalance: 300, increase: 60, decrease: 10 }],
      costImpairRows: [{ category: '房屋、建筑物', beginBalance: 100, increase: 20, decrease: 0 }],
      ...CTX,
    })
    const rows = p.sub_table_data[H3_SOE_SUBTABLE.cost] as Record<string, unknown>[]
    expect(rows).toHaveLength(15)
    const carrying = rows.find((r) => r.label === '五、投资性房地产账面价值合计')!
    // 期末：原值 1150 − 折旧 350 − 减值 120 = 680
    expect(carrying.end).toBe(1150 - 350 - 120)
    expect(carrying.begin).toBe(1000 - 300 - 100)
  })

  it('未办妥产权证书为条件表：无行时不推空表且进 removed', () => {
    const p = buildH3SyncPayload({ variant: 'soe', measurementModel: 'cost', ...CTX })
    expect(Object.keys(p.sub_table_data)).not.toContain(H3_SOE_SUBTABLE.title)
    expect(p.sub_table_data._removed_table_keys).toContain(H3_SOE_SUBTABLE.title)

    const withRows = buildH3SyncPayload({
      variant: 'soe',
      measurementModel: 'cost',
      titleRows: [{ category: '厂房A', bookValue: 500, reason: '正在办理' }],
      ...CTX,
    })
    const t = withRows.sub_table_data[H3_SOE_SUBTABLE.title] as Record<string, unknown>[]
    expect(t.at(-1)).toMatchObject({ label: '合计', book_value: 500, is_total: true })
  })

  it('提供两级子列时按细分值推送（不再走「聚合归主渠道」退化映射）', () => {
    const p = buildH3SyncPayload({
      variant: 'soe',
      measurementModel: 'cost',
      costOriginalRows: [{
        category: '房屋、建筑物',
        beginBalance: 1000,
        buyOrProvision: 120, transferIn: 80,
        disposal: 30, transferOut: 20,
        increase: 200, decrease: 50, // 底稿 onSubChange 回写的聚合值
      }],
      ...CTX,
    })
    const rows = p.sub_table_data[H3_SOE_SUBTABLE.cost] as Record<string, unknown>[]
    const layer = rows.find((r) => r.label === '一、账面原值合计')!
    expect(layer.buy_or_provision).toBe(120)
    expect(layer.transfer_in).toBe(80)
    expect(layer.disposal).toBe(30)
    expect(layer.transfer_out).toBe(20)
    // 期末 = 期初 + 聚合增加 − 聚合减少，且聚合与子列之和一致
    expect(layer.end).toBe(1000 + 200 - 50)
    expect((layer.buy_or_provision as number) + (layer.transfer_in as number)).toBe(200)
  })

  it('公允价值模式：期末 = 期初 + 增加 − 减少 + 公允价值变动损益（不双算）', () => {
    const p = buildH3SyncPayload({
      variant: 'soe',
      measurementModel: 'fair_value',
      fairChangeRows: [{
        category: '房屋、建筑物',
        beginBalance: 1000,
        buyOrProvision: 100, transferIn: 50, fairChange: 30,
        disposal: 20, transferOut: 10,
        increase: 150, decrease: 30,
      }],
      ...CTX,
    })
    const rows = p.sub_table_data[H3_SOE_SUBTABLE.fair] as Record<string, unknown>[]
    const carrying = rows.find((r) => r.label === '三、投资性房地产账面价值合计')!
    expect(carrying.fair_change_pl).toBe(30)
    expect(carrying.end_fair).toBe(1000 + 150 - 30 + 30)
  })

  it('未办妥产权证书原因兼容 usage / reason 两种字段（底稿区块用 usage）', () => {
    const p = buildH3SyncPayload({
      variant: 'listed',
      measurementModel: 'cost',
      titleRows: [{ category: '厂房B', beginBalance: 800, usage: '手续办理中' }],
      ...CTX,
    })
    const t = p.sub_table_data[H3_LISTED_SUBTABLE.title] as Record<string, unknown>[]
    expect(t[0]).toMatchObject({ label: '厂房B', book_value: 800, reason: '手续办理中' })
    // 上市源模板该表无合计行
    expect(t.some((r) => r.is_total)).toBe(false)
  })

  it('_note_texts 每条带中文 title 且过滤空文本', () => {
    const p = buildH3SyncPayload({
      variant: 'soe',
      measurementModel: 'cost',
      sectionTexts: { 'soe-cost': '成本说明', 'soe-impair': '   ' },
      ...CTX,
    })
    const texts = p.sub_table_data._note_texts as Array<{ section: string; title: string }>
    expect(texts).toHaveLength(1)
    expect(texts[0].title).toBe('以成本计量说明')
    expect(/^[a-z-]+$/.test(texts[0].title)).toBe(false)
  })
})
