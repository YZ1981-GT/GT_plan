/**
 * F4 应付账款披露子表名 ↔ 附注模板契约 + 同步载荷结构
 *
 * 防回归：`F4_LISTED_SUBTABLE` / `F4_SOE_SUBTABLE` 的每个值必须能在
 * `note_template_listed.json` §五、37 / `note_template_soe.json` §八、37
 * 的 `tables[].name` 中找到，否则 sync-from-workpaper 会写出孤儿子表
 * （附注 TAB 永空 + 底稿数据丢失）。
 *
 * 结构修订脚本：`backend/scripts/fix/fix_note_accounts_payable_structure.py`
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  F4_DISCLOSURE_SHEET_NAME,
  F4_LISTED_NATURE_COLUMNS,
  F4_LISTED_OVER1Y_COLUMNS,
  F4_LISTED_REMOVED_TABLE_KEYS,
  F4_LISTED_SUBTABLE,
  F4_NOTE_SECTION,
  F4_SOE_AGING_COLUMNS,
  F4_SOE_OVER1Y_COLUMNS,
  F4_SOE_SUBTABLE,
  buildF4ListedSyncPayload,
  buildF4SoeSyncPayload,
  f4NoteAgingLabel,
  f4NoteAgingLabelByRowKey,
  resolveF4CurrentStandard,
} from '../f4NoteSectionMap'
import type { ColumnDef } from '../disclosureColumnDefs'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'

interface NoteTable {
  name?: string
  headers?: string[]
  guidance?: string
  columns?: ColumnDef[]
  rows?: Array<{ label?: string; row_type?: string; is_total?: boolean }>
}
interface NoteSection {
  section_number?: string
  tables?: NoteTable[]
  text_sections?: string[]
  _aligned_by?: string
}

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function loadSection(file: string, sectionNumber: string): NoteSection {
  const path = resolve(REPO_ROOT, 'backend/data', file)
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as { sections: NoteSection[] }
  const hit = raw.sections.find((s) => String(s.section_number ?? '').trim() === sectionNumber)
  if (!hit) throw new Error(`${file} 缺少章节 ${sectionNumber}`)
  return hit
}

const listedSection = loadSection('note_template_listed.json', F4_NOTE_SECTION.listed)
const soeSection = loadSection('note_template_soe.json', F4_NOTE_SECTION.soe)

function table(section: NoteSection, name: string): NoteTable {
  const hit = (section.tables ?? []).find((t) => t.name === name)
  if (!hit) throw new Error(`未找到子表「${name}」，现有：${(section.tables ?? []).map((t) => t.name).join(' / ')}`)
  return hit
}

describe('F4 子表名 ↔ note_template 契约', () => {
  it.each(Object.entries(F4_LISTED_SUBTABLE))(
    '上市 %s → 「%s」存在于 §五、37',
    (_key, name) => {
      expect((listedSection.tables ?? []).map((t) => t.name)).toContain(name)
    },
  )

  it.each(Object.entries(F4_SOE_SUBTABLE))(
    '国企 %s → 「%s」存在于 §八、37',
    (_key, name) => {
      expect((soeSection.tables ?? []).map((t) => t.name)).toContain(name)
    },
  )

  it('历史误名「项  目」已从上市模板移除（否则 TAB 页签显示表头文案）', () => {
    for (const removed of F4_LISTED_REMOVED_TABLE_KEYS) {
      expect((listedSection.tables ?? []).map((t) => t.name)).not.toContain(removed)
    }
  })

  it('两个 variant 已打对齐标记', () => {
    expect(listedSection._aligned_by).toBe('f4-accounts-payable-disclosure-template-alignment')
    expect(soeSection._aligned_by).toBe('f4-accounts-payable-disclosure-template-alignment')
  })
})

describe('附注 §五、37 / §八、37 结构要求', () => {
  const all = [
    ...(listedSection.tables ?? []),
    ...(soeSection.tables ?? []),
  ]

  it('headers 无空串', () => {
    for (const t of all) {
      for (const h of t.headers ?? []) {
        expect(String(h ?? '').trim(), `${t.name} headers 含空串`).not.toBe('')
      }
    }
  })

  it('每张表都有 guidance（TAB 页签编制提示）', () => {
    const missing = all.filter((t) => !String(t.guidance ?? '').trim()).map((t) => t.name)
    expect(missing, `缺 guidance: ${missing.join(' / ')}`).toHaveLength(0)
  })

  it('columns 数量与 headers 一致、恰有 1 个标签列且其 label = headers[0]', () => {
    for (const t of all) {
      const cols = t.columns ?? []
      expect(cols.length, `${t.name} columns 缺失或数量不符`).toBe((t.headers ?? []).length)
      const labelCols = cols.filter((c) => c.is_label)
      expect(labelCols, `${t.name} is_label 列数应为 1`).toHaveLength(1)
      expect(labelCols[0].label).toBe((t.headers ?? [])[0])
    }
  })

  it('3 列单级表头显式 flat（抑制后端前缀推断出凭空父表头）', () => {
    for (const t of all) {
      expect(t.columns?.some((c) => c.flat), `${t.name} 缺 flat 声明`).toBe(true)
    }
  })

  it('上市按性质行 = F4-1 审定表 5 类，占位行「可无限量添加行」已删', () => {
    const rows = table(listedSection, F4_LISTED_SUBTABLE.nature).rows ?? []
    expect(rows.map((r) => r.label)).toEqual(['货款', '工程款', '设备款', '服务费', '其他', '合计'])
  })

  it('国企按账龄行逐字对齐附注模版（不带「（含2年）」）', () => {
    const rows = table(soeSection, F4_SOE_SUBTABLE.aging).rows ?? []
    expect(rows.map((r) => r.label)).toEqual([
      '1年以内（含1年）', '1至2年', '2至3年', '3年以上', '合计',
    ])
  })

  it('columns 键与前端 ColumnDef 常量逐字一致', () => {
    expect(table(listedSection, F4_LISTED_SUBTABLE.nature).columns).toEqual(F4_LISTED_NATURE_COLUMNS)
    expect(table(listedSection, F4_LISTED_SUBTABLE.over1y).columns).toEqual(F4_LISTED_OVER1Y_COLUMNS)
    expect(table(soeSection, F4_SOE_SUBTABLE.aging).columns).toEqual(F4_SOE_AGING_COLUMNS)
    expect(table(soeSection, F4_SOE_SUBTABLE.over1y).columns).toEqual(F4_SOE_OVER1Y_COLUMNS)
  })

  it('text_sections 不含纯表标题行（应由 tables[].name 承载）', () => {
    for (const section of [listedSection, soeSection]) {
      const names = new Set((section.tables ?? []).map((t) => String(t.name ?? '').trim()))
      for (const text of section.text_sections ?? []) {
        const stripped = String(text).replace(/^#+\s*/, '').trim()
        expect(names.has(stripped), `text_sections 混入表标题：${text}`).toBe(false)
      }
    }
  })
})

describe('账龄文案：底稿用词 → 附注模版用词', () => {
  it('3 年段投影为附注模版 4 档', () => {
    expect(PRESET_SEGMENTS.THREE_YEAR.map(f4NoteAgingLabel)).toEqual([
      '1年以内（含1年）', '1至2年', '2至3年', '3年以上',
    ])
  })

  it('5 年段按同一「X至Y年」构词展开为 6 档', () => {
    expect(PRESET_SEGMENTS.FIVE_YEAR.map(f4NoteAgingLabel)).toEqual([
      '1年以内（含1年）', '1至2年', '2至3年', '3至4年', '4至5年', '5年以上',
    ])
  })

  it('自定义段无约定映射时回落配置 label', () => {
    expect(f4NoteAgingLabel({ key: 'y6to8', label: '6-8年', dayFrom: 2191, dayTo: 2920 }))
      .toBe('6-8年')
  })

  it('F4-1 既有 rowKey（3 年段存储键）也能投影', () => {
    expect(f4NoteAgingLabelByRowKey('within1year', 'x')).toBe('1年以内（含1年）')
    expect(f4NoteAgingLabelByRowKey('1to2year', 'x')).toBe('1至2年')
    expect(f4NoteAgingLabelByRowKey('2to3year', 'x')).toBe('2至3年')
    expect(f4NoteAgingLabelByRowKey('3yearplus', 'x')).toBe('3年以上')
    // 5 年段 rowKey 即段 key
    expect(f4NoteAgingLabelByRowKey('y4to5', 'x')).toBe('4至5年')
    // 残差行不在映射内 → 用底稿 label（且不会被推送）
    expect(f4NoteAgingLabelByRowKey('aging-other', '其他/未分类')).toBe('其他/未分类')
  })
})

describe('current_standard 解析', () => {
  it('按 variant + consolidated 关键字分流', () => {
    expect(resolveF4CurrentStandard('listed', [])).toBe('listed_standalone')
    expect(resolveF4CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveF4CurrentStandard('soe', undefined)).toBe('soe_standalone')
    expect(resolveF4CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })
})

describe('buildF4ListedSyncPayload', () => {
  const payload = buildF4ListedSyncPayload(
    'wp-1',
    ['listed_standalone'],
    [
      { label: '货款', endAmount: 1000, priorAmount: 800 },
      { label: '工程款', endAmount: 500, priorAmount: 400 },
      { label: '', endAmount: 0, priorAmount: 0 },
    ],
    [
      { creditor: 'A供应商', amount: 300, reason: '双方对账差异未结' },
      { creditor: '', amount: 0, reason: '' },
    ],
    '本期末应付账款较上年年末增加 XX 元。',
  )

  it('指向 五、37 且 sheet_name 为源 xlsx 中文 tab 名', () => {
    expect(payload.section_id).toBe('五、37')
    expect(payload.sheet_name).toBe('附注披露信息(上市公司)')
    expect(F4_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息(上市公司)')
    expect(payload.current_standard).toBe('listed_standalone')
  })

  it('按性质表：空白行不推送，末行为合计', () => {
    const rows = payload.sub_table_data[F4_LISTED_SUBTABLE.nature] as any[]
    expect(rows).toHaveLength(3)
    expect(rows[0]).toMatchObject({ label: '货款', end_amount: 1000, prior_amount: 800 })
    expect(rows[2]).toMatchObject({ label: '合计', end_amount: 1500, prior_amount: 1200, is_total: true })
  })

  it('账龄超 1 年表：空白骨架行不推送，原因列键为 unsettled_reason', () => {
    const rows = payload.sub_table_data[F4_LISTED_SUBTABLE.over1y] as any[]
    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({
      label: 'A供应商', end_amount: 300, unsettled_reason: '双方对账差异未结',
    })
    expect(rows[1]).toMatchObject({ label: '合计', end_amount: 300, is_total: true })
  })

  // R5（spec f-cycle-disclosure-parity）：原实现 `[{ text }]` 无 section 也无 title，
  // 附注侧无从判断正文来自哪个披露 Tab。现补齐变体 section + 中文 title。
  it('叙述正文带变体 section 与中文 title', () => {
    const texts = payload.sub_table_data._note_texts as any[]
    expect(texts).toHaveLength(1)
    expect(texts[0]).toMatchObject({
      section: 'listed-disclosure-note',
      title: '应付账款披露说明',
    })
    expect(texts[0].text).toContain('应付账款')
    // 禁止英文 section 键泄漏成标题
    expect(texts[0].title).not.toBe(texts[0].section)
    expect(/[a-z-]{6,}/.test(texts[0].title)).toBe(false)
  })

  it('R5 空正文被过滤（不用空段落覆盖附注既有正文）', () => {
    const empty = buildF4ListedSyncPayload('wp-x', ['listed_standalone'], [], [], '   ')
    expect(empty.sub_table_data._note_texts).toEqual([])
  })

  it('上报历史误名以删除附注侧残留空表', () => {
    expect(payload.sub_table_data._removed_table_keys).toEqual(['项  目'])
  })

  it('携带 columns，且标签列 label = 附注 headers[0]', () => {
    expect(payload.columns?.[F4_LISTED_SUBTABLE.nature]?.[0]).toMatchObject({
      key: 'label', label: '项目', is_label: true,
    })
    expect(payload.columns?.[F4_LISTED_SUBTABLE.over1y]?.[2].label).toBe('未偿还或未结转的原因')
  })
})

describe('buildF4SoeSyncPayload', () => {
  const agingRows = [
    { rowKey: 'within1year', label: '1年以内（含1年）', endAmount: 900, openingAmount: 700 },
    { rowKey: '1to2year', label: '1至2年（含2年）', endAmount: 300, openingAmount: 200 },
    { rowKey: '2to3year', label: '2至3年（含3年）', endAmount: 100, openingAmount: 80 },
    { rowKey: '3yearplus', label: '3年以上', endAmount: 50, openingAmount: 40 },
    { rowKey: 'aging-other', label: '其他/未分类', endAmount: 20, openingAmount: 10 },
  ]
  const payload = buildF4SoeSyncPayload(
    'wp-2',
    ['soe_standalone'],
    agingRows,
    [{ creditor: '甲公司', amount: 120, reason: '工程未结算' }],
    '按账龄列示的应付账款期末余额为 XX 元。',
  )

  it('指向 八、37 且 sheet_name 为源 xlsx 中文 tab 名', () => {
    expect(payload.section_id).toBe('八、37')
    expect(payload.sheet_name).toBe('附注披露信息(国企)')
    expect(payload.current_standard).toBe('soe_standalone')
  })

  it('账龄行名按附注模版投影，残差行不进附注', () => {
    const rows = payload.sub_table_data[F4_SOE_SUBTABLE.aging] as any[]
    expect(rows.map((r) => r.label)).toEqual([
      '1年以内（含1年）', '1至2年', '2至3年', '3年以上', '合计',
    ])
  })

  it('合计含残差行金额，与 F4-1 按性质合计保持勾稽', () => {
    const rows = payload.sub_table_data[F4_SOE_SUBTABLE.aging] as any[]
    const total = rows[rows.length - 1]
    expect(total).toMatchObject({ label: '合计', end_amount: 1370, opening_amount: 1030, is_total: true })
  })

  it('国企子表名保留附注模版原文空格「账龄超过1 年」', () => {
    expect(F4_SOE_SUBTABLE.over1y).toBe('账龄超过1 年的重要应付账款')
    expect(Object.keys(payload.sub_table_data)).toContain('账龄超过1 年的重要应付账款')
  })

  it('重要应付账款原因列键为 unsettled_reason，列头为「未偿还原因」', () => {
    const rows = payload.sub_table_data[F4_SOE_SUBTABLE.over1y] as any[]
    expect(rows[0]).toMatchObject({ label: '甲公司', end_amount: 120, unsettled_reason: '工程未结算' })
    expect(payload.columns?.[F4_SOE_SUBTABLE.over1y]?.[2].label).toBe('未偿还原因')
  })

  it('国企不上报 _removed_table_keys（表名未变更）', () => {
    expect(payload.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('5 年段账龄配置下推送 6 档行名', () => {
    const five = PRESET_SEGMENTS.FIVE_YEAR.map((seg) => ({
      rowKey: seg.key,
      label: seg.label,
      endAmount: 10,
      openingAmount: 5,
    }))
    const p = buildF4SoeSyncPayload('wp-3', ['soe_standalone'], five, [], '')
    const rows = p.sub_table_data[F4_SOE_SUBTABLE.aging] as any[]
    expect(rows.map((r) => r.label)).toEqual([
      '1年以内（含1年）', '1至2年', '2至3年', '3至4年', '4至5年', '5年以上', '合计',
    ])
    expect(rows[rows.length - 1].end_amount).toBe(60)
  })
})
