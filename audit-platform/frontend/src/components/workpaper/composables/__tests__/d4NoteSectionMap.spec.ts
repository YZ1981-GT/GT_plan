import { describe, it, expect } from 'vitest'
import {
  buildD4SyncPayload,
  buildD4NoteTexts,
  resolveD4CurrentStandard,
  D4_NOTE_SECTION,
  D4_DISCLOSURE_SHEET_NAME,
  D4_LEGACY_OBSOLETE_TABLES,
  type D4DisclosureSnapshot,
} from '../d4NoteSectionMap'
import { D4_DEFAULT_CATEGORIES } from '../d4DisclosureModel'

const snapshot = (): D4DisclosureSnapshot => ({
  revenueRows: [
    { label: '主营业务', currentRevenue: 1000, currentCost: 600, priorRevenue: 900, priorCost: 550 },
    { label: '其他业务', currentRevenue: 100, currentCost: 40, priorRevenue: 80, priorCost: 30 },
  ],
  revenueTotal: { label: '合计', currentRevenue: 1100, currentCost: 640, priorRevenue: 980, priorCost: 580 },
  industryRows: [{ label: '消费品', currentRevenue: 700, currentCost: 400, priorRevenue: 600, priorCost: 350 }],
  regionRows: [{ label: '华东', currentRevenue: 500, currentCost: 300, priorRevenue: 450, priorCost: 270 }],
  timingRows: [
    { label: '在某一时点确认', cat_1_revenue: 300, cat_1_cost: 180, total_revenue: 300, total_cost: 180 },
  ],
  timingCategories: [...D4_DEFAULT_CATEGORIES],
  section6Rows: [
    { label: 'A合同预计将确认的收入', year_2026: 500, year_2027: 300 },
  ],
  section8Rows: [
    { label: '固定资产试运行收入', endRevenue: 100, endCost: 50, priorRevenue: 80, priorCost: 40 },
    { label: '研发样品销售收入', endRevenue: 60, endCost: 20, priorRevenue: 50, priorCost: 15 },
  ],
  auditYear: 2025,
  notes: { 'note-1': '收入说明', 'note-2': '', 'note-8': '试运行说明' },
})

describe('d4NoteSectionMap', () => {
  it('章节号 + sheet 名（真实 tab 名，全角括号）', () => {
    expect(D4_NOTE_SECTION.listed).toBe('五、62')
    expect(D4_NOTE_SECTION.soe).toBe('八、64')
    // 🔴 D4 为全角括号（与 D7 半角不同）
    expect(D4_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(D4_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })

  it('resolveD4CurrentStandard maps variant + applicable standards', () => {
    expect(resolveD4CurrentStandard('listed', null)).toBe('listed_standalone')
    expect(resolveD4CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveD4CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })

  it('listed payload → 五、62 六表（含（6）（8）），子表键与模板 tables[].name 逐字一致', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    expect(p.section_id).toBe('五、62')
    expect(p.sheet_name).toBe('附注披露信息（上市公司）')
    expect(p.current_standard).toBe('listed_standalone')

    // 六张结构化子表 + _note_texts + _removed_table_keys
    const dataKeys = Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))
    expect(dataKeys).toEqual([
      '营业收入和营业成本',
      '营业收入、营业成本按行业（或产品类型）划分',
      '营业收入、营业成本按地区划分',
      '营业收入、营业成本按分解信息',        // Req 6.1: 对齐源模板
      '与剩余履约义务有关的信息',              // Req 6.4:（6）
      '试运行销售收入',                        // Req 6.4:（8）仅上市
    ])

    // 🔴 各子表键 ↔ columns 键必须相同（Property 11）
    for (const k of dataKeys) {
      expect(p.columns[k]).toBeDefined()
    }
  })

  it('listed 主表 5 列两级 group', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    const mainCols = p.columns['营业收入和营业成本']
    // 🔴 2026-09-06：标签列**不得**带 flat。`flat` 是表级语义（后端
    // `_extract_column_groups` 里 `any(d.get("flat")) → return []` 整表禁分组），
    // 本表是两级表头（本期/上期发生额），标签列标 flat 会让 4 个 group 全失效。
    expect(mainCols[0]).toMatchObject({ key: 'label', is_label: true })
    expect(mainCols[0].flat).toBeUndefined()
    expect(mainCols[1]).toMatchObject({ key: 'endRevenue', group: '本期发生额' })
    expect(mainCols[2]).toMatchObject({ key: 'endCost', group: '本期发生额' })
    expect(mainCols[3]).toMatchObject({ key: 'priorRevenue', group: '上期发生额' })
    expect(mainCols[4]).toMatchObject({ key: 'priorCost', group: '上期发生额' })
    // 行数据含合计
    const mainRows = p.sub_table_data['营业收入和营业成本'] as any[]
    expect(mainRows[0]).toMatchObject({ label: '主营业务', endRevenue: 1000, endCost: 600, priorRevenue: 900, priorCost: 550 })
    expect(mainRows[mainRows.length - 1]).toMatchObject({ label: '合计', endRevenue: 1100, is_total: true })
  })

  it('listed（2）（3）含上期两列（Req 6.2）+ 叶子列名按变体（Property 12）', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    // 行业表
    const indCols = p.columns['营业收入、营业成本按行业（或产品类型）划分']
    expect(indCols[0].label).toBe('主要产品类型（或行业）')
    expect(indCols[1]).toMatchObject({ group: '本期发生额', label: '收入' })
    expect(indCols[3]).toMatchObject({ group: '上期发生额', label: '收入' })
    const indRows = p.sub_table_data['营业收入、营业成本按行业（或产品类型）划分'] as any[]
    expect(indRows[0]).toMatchObject({ label: '消费品', endRevenue: 700, priorRevenue: 600 })
    // 合计行
    expect(indRows[indRows.length - 1]).toMatchObject({ label: '合计', is_total: true })

    // 🔴 上市（3）按地区叶子列名 = 主营业务收入/主营业务成本（源 R37），与国企不同
    const regCols = p.columns['营业收入、营业成本按地区划分']
    expect(regCols[1].label).toBe('主营业务收入')
    expect(regCols[2].label).toBe('主营业务成本')
  })

  it('listed（4）分解信息列转置 + 动态类别列 group（Req 6.3）', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    const timCols = p.columns['营业收入、营业成本按分解信息']
    // 同上：本表按类别分组（两级），标签列不得带 flat
    expect(timCols[0]).toMatchObject({ key: 'label' })
    expect(timCols[0].flat).toBeUndefined()
    // 类别列带 group
    expect(timCols[1]).toMatchObject({ key: 'cat_1_revenue', group: '消费品' })
    expect(timCols[2]).toMatchObject({ key: 'cat_1_cost', group: '消费品' })
    // 🔴 Task 31: **不得**有横向合计列 —— 源 xlsx 实证该表 9 列，
    //    合计是**行**（上市 R56 `=B52+B48`）。改造前这里断言 2 个 `total_*` 列，
    //    镜像的是自造出来的列，会让附注比源模板多两列。
    const totalCols = timCols.filter(c => c.key.startsWith('total_'))
    expect(totalCols).toHaveLength(0)
    // 反向自检：类别列确实推过来了（否则上面的断言在空列集上也会通过）
    expect(timCols.filter(c => /^cat_\d+_(revenue|cost)$/.test(c.key)).length).toBeGreaterThan(0)
  })

  it('listed（6）义务表 flat + 动态年度列（Req 6.4 / 6.7）', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    const oblCols = p.columns['与剩余履约义务有关的信息']
    // 所有列 flat（单级表头）
    for (const c of oblCols) {
      expect(c.flat).toBe(true)
    }
    expect(oblCols).toHaveLength(4) // label + 2 years + total
    expect(oblCols[1].label).toBe('2026年')
    expect(oblCols[2].label).toBe('2027年')
    expect(oblCols[3].label).toBe('合计')
    // 行数据含派生 total
    const oblRows = p.sub_table_data['与剩余履约义务有关的信息'] as any[]
    expect(oblRows[0]).toMatchObject({ label: 'A合同预计将确认的收入', year_2026: 500, year_2027: 300, total: 800 })
  })

  it('listed（8）试运行销售收入两级 group（Req 6.4）', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    const trCols = p.columns['试运行销售收入']
    expect(trCols[1]).toMatchObject({ group: '本期发生额' })
    expect(trCols[3]).toMatchObject({ group: '上期发生额' })
    const trRows = p.sub_table_data['试运行销售收入'] as any[]
    expect(trRows).toHaveLength(2)
    expect(trRows[0]).toMatchObject({ label: '固定资产试运行收入', endRevenue: 100, endCost: 50 })
  })

  it('soe payload → 八、64 五表（无试运行销售收入）+ 表名对齐源模板', () => {
    const p = buildD4SyncPayload('soe', 'wp-2', ['soe_standalone'], snapshot())
    expect(p.section_id).toBe('八、64')
    expect(p.sheet_name).toBe('附注披露信息（国企）')

    const dataKeys = Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))
    expect(dataKeys).toEqual([
      '营业收入、营业成本',
      '按行业（或产品类型）划分',
      '营业收入、营业成本按地区划分',
      '营业收入分解信息',                      // 国企版表名
      '与剩余履约义务有关的信息',
    ])
    // 无（8）试运行销售收入
    expect(dataKeys).not.toContain('试运行销售收入')

    // 国企（4）首列头 = 合同分类/报告分部
    expect(p.columns['营业收入分解信息'][0].label).toBe('合同分类/报告分部')

    // 🔴 国企（3）按地区叶子列名 = 收入/成本（Property 12）
    const regCols = p.columns['营业收入、营业成本按地区划分']
    expect(regCols[1].label).toBe('收入')
    expect(regCols[2].label).toBe('成本')
  })

  it('_removed_table_keys 与本次推送键无交集（Property 20）', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    const pushKeys = new Set(Object.keys(p.sub_table_data).filter(k => !k.startsWith('_')))
    const removed = (p.sub_table_data._removed_table_keys as string[]) ?? []
    // 旧表名 in removed
    expect(removed).toContain('营业收入、营业成本按商品转让时间划分')
    // 无交集
    for (const r of removed) {
      expect(pushKeys.has(r)).toBe(false)
    }
  })

  it('_note_texts 在 sub_table_data 内、带中文 title、过滤空文本（Req 6.6）', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    const texts = p.sub_table_data._note_texts as Array<{ section: string; title: string; text: string }>
    // 只含非空文本
    expect(texts).toHaveLength(2) // note-1 + note-8
    expect(texts[0]).toEqual({ section: 'listed-note-1', title: '营业收入和营业成本说明', text: '收入说明' })
    expect(texts[1]).toEqual({ section: 'listed-note-8', title: '试运行销售收入说明', text: '试运行说明' })
    // note-2 空被过滤
    expect(texts.find(t => t.section === 'listed-note-2')).toBeUndefined()
  })

  it('列头表态完备（Property 13）：两级表有 group，单级表有 flat', () => {
    const p = buildD4SyncPayload('listed', 'wp-1', null, snapshot())
    for (const [, cols] of Object.entries(p.columns)) {
      for (const col of cols) {
        if (col.is_label) continue // 标签列可 flat
        // 每个数据列声明 group 或 flat
        expect(col.group || col.flat).toBeTruthy()
      }
    }
  })

  it('sumNullable：四列表空行 → 合计 null（不塌 0）', () => {
    const snap: D4DisclosureSnapshot = {
      revenueRows: [],
      revenueTotal: { label: '合计', currentRevenue: 0, currentCost: 0, priorRevenue: 0, priorCost: 0 },
      industryRows: [],
      regionRows: [],
      timingRows: [],
      section6Rows: [],
      auditYear: 2025,
      notes: {},
    }
    const p = buildD4SyncPayload('listed', 'wp', null, snap)
    const ind = p.sub_table_data['营业收入、营业成本按行业（或产品类型）划分'] as any[]
    expect(ind).toHaveLength(1) // 仅合计行
    expect(ind[0]).toMatchObject({ label: '合计', endRevenue: null, endCost: null, priorRevenue: null, priorCost: null, is_total: true })
    expect(p.sub_table_data['_note_texts']).toEqual([])
  })

  it('buildD4NoteTexts: section 前缀带 variant，空文本跳过', () => {
    expect(buildD4NoteTexts('listed', { 'note-1': '收入说明', 'note-2': '' })).toEqual([
      { section: 'listed-note-1', title: '营业收入和营业成本说明', text: '收入说明' },
    ])
    // soe 无 note-8
    expect(buildD4NoteTexts('soe', { 'note-8': '试运行' })).toEqual([])
  })

  it('D4_LEGACY_OBSOLETE_TABLES 含旧表名', () => {
    expect(D4_LEGACY_OBSOLETE_TABLES).toContain('营业收入、营业成本按商品转让时间划分')
  })
})
