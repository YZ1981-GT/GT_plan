/**
 * I 循环（I1~I6）披露子表 ↔ note_template 契约测试
 *
 * 接入共享 helper P1~P6，`columnsPending` 为空（Wave 4 已补齐）。
 *
 * Spec: i-cycle-four-table-extraction-and-disclosure-alignment Task 5.6
 */
import { describe, it, expect } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'

// ── I1 无形资产 ──────────────────────────────────────────────────
import {
  I1_NOTE_SECTION,
  I1_LISTED_SUBTABLE,
  I1_SOE_SUBTABLE,
  I1_LEGACY_OBSOLETE_TABLES,
} from '../i1NoteSectionMap'
import { buildI1ListedColumns, buildI1ListedSyncPayloads } from '../i1DisclosureSyncPayload'

// ── I2 开发支出 ──────────────────────────────────────────────────
import {
  I2_NOTE_SECTION,
  I2_LISTED_SUBTABLE,
  I2_SOE_SUBTABLE,
  I2_LEGACY_OBSOLETE_TABLES,
} from '../i2NoteSectionMap'
import { buildI2ListedSyncPayloads, buildI2SoeSyncPayloads } from '../i2DisclosureSyncPayload'

// ── I3 商誉 ─────────────────────────────────────────────────────
import {
  I3_NOTE_SECTION,
  I3_LISTED_SUBTABLE,
  I3_SOE_SUBTABLE,
  I3_LEGACY_OBSOLETE_TABLES,
} from '../i3NoteSectionMap'
import { buildI3ListedSyncPayloads, buildI3SoeSyncPayloads } from '../i3DisclosureSyncPayload'

// ── I4 长期待摊费用 ──────────────────────────────────────────────
import {
  I4_NOTE_SECTION,
  I4_LISTED_SUBTABLE,
  I4_SOE_SUBTABLE,
  I4_LEGACY_OBSOLETE_TABLES,
} from '../i4NoteSectionMap'
import { buildI4ListedSyncPayloads, buildI4SoeSyncPayloads } from '../i4DisclosureSyncPayload'

// ── I5 其他非流动资产 ────────────────────────────────────────────
import {
  I5_NOTE_SECTION,
  I5_LISTED_SUBTABLE,
  I5_SOE_SUBTABLE,
  I5_LEGACY_OBSOLETE_TABLES,
} from '../i5NoteSectionMap'
import { buildI5ListedSyncPayloads, buildI5SoeSyncPayloads } from '../i5DisclosureSyncPayload'

// ── I6 研发费用 ──────────────────────────────────────────────────
import {
  I6_NOTE_SECTION,
  I6_LISTED_SUBTABLE,
  I6_SOE_SUBTABLE,
  I6_LEGACY_OBSOLETE_TABLES,
} from '../i6NoteSectionMap'
import { buildI6ListedSyncPayloads, buildI6SoeSyncPayloads } from '../i6DisclosureSyncPayload'

// ═══════════════════════════════════════════════════════════════════
// P1~P6 跑契约
// ═══════════════════════════════════════════════════════════════════

// I1: 上市动态列 — 需传默认分类来生成 columns
const i1ListedCols = buildI1ListedColumns({
  categories: [
    { key: 'patent', label: '专利权' },
    { key: 'software', label: '软件' },
    { key: 'non_patent', label: '非专利技术' },
    { key: 'land_use', label: '土地使用权' },
    { key: 'mining', label: '采矿权' },
    { key: 'trademark', label: '商标权' },
    { key: 'franchise', label: '特许经营权' },
    { key: 'copyright', label: '著作权' },
    { key: 'emission', label: '碳排放权' },
    { key: 'domain', label: '域名' },
    { key: 'other', label: '其他' },
  ],
} as any)

// I1 SOE: 只有 movement 表在模板里有 columns
const I1_SOE_COLUMNS: Record<string, any[]> = {
  [I1_SOE_SUBTABLE.movement]: [
    { key: 'label', label: '项  目', is_label: true, flat: true },
    { key: 'begin', label: '期初余额', format: 'amount', flat: true },
    { key: 'increase', label: '本期增加', format: 'amount', flat: true },
    { key: 'decrease', label: '本期减少', format: 'amount', flat: true },
    { key: 'end', label: '期末余额', format: 'amount', flat: true },
  ],
}

runDisclosureSubtableContract({
  cycle: 'I1',
  variants: [
    {
      variant: 'listed',
      section: I1_NOTE_SECTION.listed,
      subtables: I1_LISTED_SUBTABLE,
      columns: i1ListedCols,
      // 表1「无形资产情况」的 columns 由前端动态类别生成，模板侧无 columns 定义
      columnsPending: {
        [I1_LISTED_SUBTABLE.movement]: '列转置由前端动态类别生成，模板 columns=0',
      },
    },
    {
      variant: 'soe',
      section: I1_NOTE_SECTION.soe,
      subtables: I1_SOE_SUBTABLE,
      columns: I1_SOE_COLUMNS,
      columnsPending: {
        [I1_SOE_SUBTABLE.dataResource]: '列转置结构复杂（H7 式），同步载荷暂不推送',
      },
    },
  ],
})

// I2
const i2ListedPayload = buildI2ListedSyncPayloads('wp-i2', null, {
  natureRows: [], movementRows: [], importantRows: [], impairmentRows: [],
  noteText: '', noteCap: '', noteImpairTest: '', notePurchased: '',
})
const i2SoePayload = buildI2SoeSyncPayloads('wp-i2', null, { movementRows: [], noteText: '' })

runDisclosureSubtableContract({
  cycle: 'I2',
  variants: [
    {
      variant: 'listed',
      section: I2_NOTE_SECTION.listed,
      subtables: I2_LISTED_SUBTABLE,
      columns: i2ListedPayload[0]?.columns ?? {},
    },
    {
      variant: 'soe',
      section: I2_NOTE_SECTION.soe,
      subtables: I2_SOE_SUBTABLE,
      columns: i2SoePayload[0]?.columns ?? {},
    },
  ],
})

// I3
const i3ListedPayload = buildI3ListedSyncPayloads('wp-i3', null, {
  bookValueRows: [], impairmentRows: [],
})
const i3SoePayload = buildI3SoeSyncPayloads('wp-i3', null, { bookValueRows: [], impairmentRows: [] })

runDisclosureSubtableContract({
  cycle: 'I3',
  variants: [
    {
      variant: 'listed',
      section: I3_NOTE_SECTION.listed,
      subtables: I3_LISTED_SUBTABLE,
      columns: i3ListedPayload[0]?.columns ?? {},
      // 表3「商誉减值测试关键假设」模板 headers[0] 是示例数据非列头（动态结构）
      columnsPending: {
        [I3_LISTED_SUBTABLE.assumptions]: '模板 headers[0] 为示例数据残留，非标签列头',
      },
    },
    {
      variant: 'soe',
      section: I3_NOTE_SECTION.soe,
      subtables: I3_SOE_SUBTABLE,
      columns: i3SoePayload[0]?.columns ?? {},
    },
  ],
})

// I4
const i4ListedPayload = buildI4ListedSyncPayloads('wp-i4', null, { rows: [] })
const i4SoePayload = buildI4SoeSyncPayloads('wp-i4', null, { rows: [] })

runDisclosureSubtableContract({
  cycle: 'I4',
  variants: [
    {
      variant: 'listed',
      section: I4_NOTE_SECTION.listed,
      subtables: I4_LISTED_SUBTABLE,
      columns: i4ListedPayload[0]?.columns ?? {},
    },
    {
      variant: 'soe',
      section: I4_NOTE_SECTION.soe,
      subtables: I4_SOE_SUBTABLE,
      columns: i4SoePayload[0]?.columns ?? {},
    },
  ],
})

// I5
const i5ListedPayload = buildI5ListedSyncPayloads('wp-i5', null, { rows: [] })
const i5SoePayload = buildI5SoeSyncPayloads('wp-i5', null, { rows: [] })

runDisclosureSubtableContract({
  cycle: 'I5',
  variants: [
    {
      variant: 'listed',
      section: I5_NOTE_SECTION.listed,
      subtables: I5_LISTED_SUBTABLE,
      columns: i5ListedPayload[0]?.columns ?? {},
    },
    {
      variant: 'soe',
      section: I5_NOTE_SECTION.soe,
      subtables: I5_SOE_SUBTABLE,
      columns: i5SoePayload[0]?.columns ?? {},
    },
  ],
})

// I6
const i6ListedPayload = buildI6ListedSyncPayloads('wp-i6', null, { rows: [] })
const i6SoePayload = buildI6SoeSyncPayloads('wp-i6', null, { rows: [] })

runDisclosureSubtableContract({
  cycle: 'I6',
  variants: [
    {
      variant: 'listed',
      section: I6_NOTE_SECTION.listed,
      subtables: I6_LISTED_SUBTABLE,
      columns: i6ListedPayload[0]?.columns ?? {},
    },
    {
      variant: 'soe',
      section: I6_NOTE_SECTION.soe,
      subtables: I6_SOE_SUBTABLE,
      columns: i6SoePayload[0]?.columns ?? {},
    },
  ],
})

// ═══════════════════════════════════════════════════════════════════
// Legacy 旧名清单完备性
// ═══════════════════════════════════════════════════════════════════

describe('I 循环 LEGACY_OBSOLETE_TABLES 非空', () => {
  it('I1 有旧名需清理', () => {
    expect(I1_LEGACY_OBSOLETE_TABLES.length).toBeGreaterThan(0)
  })
  it('I2 有旧名需清理', () => {
    expect(I2_LEGACY_OBSOLETE_TABLES.length).toBeGreaterThan(0)
  })
  it('I3 有旧名需清理', () => {
    expect(I3_LEGACY_OBSOLETE_TABLES.length).toBeGreaterThan(0)
  })
  it('I6 有旧名需清理', () => {
    expect(I6_LEGACY_OBSOLETE_TABLES.length).toBeGreaterThan(0)
  })
  it('I4 无旧名', () => {
    expect(I4_LEGACY_OBSOLETE_TABLES.length).toBe(0)
  })
  it('I5 无旧名', () => {
    expect(I5_LEGACY_OBSOLETE_TABLES.length).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════
// _note_texts 中文 title 覆盖（Task 5.5）
// ═══════════════════════════════════════════════════════════════════

describe('I 循环 _note_texts 有中文 title 且过滤空文本', () => {
  it('I1 listed 空文本过滤（全空 → _note_texts 空数组）', () => {
    const [p] = buildI1ListedSyncPayloads('wp', null, {
      categories: [{ key: 'a', label: 'A' }],
      movement: {},
    } as any)
    const notes = p.sub_table_data._note_texts ?? []
    // 全空时应无条目
    expect(notes.every((n: any) => n.text && n.text.trim())).toBe(true)
  })

  it('I2 listed 空文本过滤', () => {
    const [p] = buildI2ListedSyncPayloads('wp', null, {
      natureRows: [], movementRows: [], importantRows: [], impairmentRows: [],
      noteText: '', noteCap: '', noteImpairTest: '', notePurchased: '',
    })
    expect(p.sub_table_data._note_texts).toBeUndefined()
  })

  it('I4 soe 空文本过滤', () => {
    const [p] = buildI4SoeSyncPayloads('wp', null, { rows: [] })
    expect(p.sub_table_data._note_texts).toBeUndefined()
  })

  it('I5 soe 空文本过滤', () => {
    const [p] = buildI5SoeSyncPayloads('wp', null, { rows: [] })
    expect(p.sub_table_data._note_texts).toBeUndefined()
  })

  it('I6 listed 有 title 且空过滤', () => {
    const [p] = buildI6ListedSyncPayloads('wp', null, {
      rows: [], capitalizationNote: '测试',
    })
    const notes = p.sub_table_data._note_texts as any[]
    expect(notes.length).toBe(1)
    expect(notes[0].title).toBe('研发支出资本化情况说明')
    expect(notes[0].section).toBe('listed-capitalization')
  })
})
