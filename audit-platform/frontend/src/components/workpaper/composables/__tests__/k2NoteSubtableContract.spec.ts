/**
 * K2 披露子表 ↔ 附注模板契约 + 同步载荷断言
 *
 * P1~P5 由共享 helper 覆盖（子表名逐字一致 / 章节号存在 / flat·group 表态 /
 * 标签纯文本 / 标签列头对齐 headers[0]）。
 * 本文件另断言载荷侧的键集恒等、合计行、条件性表开关与 `_removed_table_keys`。
 *
 * spec: .kiro/specs/k2-other-current-assets-disclosure-alignment/ Task 5.1
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  K2_CARBON_ROWS,
  K2_CONTRACT_COST_ROWS,
  K2_DISCLOSURE_SHEET_NAME,
  K2_LEGACY_OBSOLETE_TABLES,
  K2_LISTED_MAIN_ROWS,
  K2_LISTED_SUBTABLE,
  K2_NOTE_SECTION,
  K2_SOE_MAIN_ROWS,
  K2_SOE_SUBTABLE,
  buildK2ListedColumns,
  buildK2SoeColumns,
  buildK2SyncPayload,
  type K2DisclosureSnapshot,
} from '../k2NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'K2',
  variants: [
    {
      variant: 'listed',
      section: K2_NOTE_SECTION.listed,
      subtables: K2_LISTED_SUBTABLE,
      columns: buildK2ListedColumns(),
    },
    {
      variant: 'soe',
      section: K2_NOTE_SECTION.soe,
      subtables: K2_SOE_SUBTABLE,
      columns: buildK2SoeColumns(),
    },
  ],
})

// ─── 模板侧结构（fix_note_k2_structure.py 的成果，防回退）────────────────────

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

interface NoteTable {
  name?: string
  headers?: string[]
  columns?: Array<Record<string, unknown>>
  guidance?: string
  rows?: Array<Record<string, unknown>>
  _column_groups?: unknown
}

function loadSection(file: string, sectionNumber: string): { tables?: NoteTable[] } {
  const raw = JSON.parse(
    readFileSync(resolve(REPO_ROOT, 'backend/data', file), 'utf-8'),
  ) as { sections: Array<{ section_number?: string; tables?: NoteTable[] }> }
  const hit = raw.sections.find(s => String(s.section_number ?? '').trim() === sectionNumber)
  if (!hit) throw new Error(`${file} 缺少章节 ${sectionNumber}`)
  return hit
}

const listedSection = loadSection('note_template_listed.json', K2_NOTE_SECTION.listed)
const soeSection = loadSection('note_template_soe.json', K2_NOTE_SECTION.soe)

describe('附注 §五、13 / §八、14 模板结构', () => {
  it('上市恰 3 张表、国企恰 1 张表', () => {
    expect((listedSection.tables ?? []).map(t => t.name)).toEqual([
      K2_LISTED_SUBTABLE.main,
      K2_LISTED_SUBTABLE.contractCost,
      K2_LISTED_SUBTABLE.carbon,
    ])
    expect((soeSection.tables ?? []).map(t => t.name)).toEqual([K2_SOE_SUBTABLE.main])
  })

  it('历史表名（段落文本 / 表头首格泄漏）已清除', () => {
    const names = new Set([
      ...(listedSection.tables ?? []).map(t => String(t.name)),
      ...(soeSection.tables ?? []).map(t => String(t.name)),
    ])
    for (const legacy of K2_LEGACY_OBSOLETE_TABLES) {
      expect(names.has(legacy), `模板仍残留历史表名：${legacy.slice(0, 30)}`).toBe(false)
    }
  })

  it('每张表都有 guidance 与 columns，且显式 flat、无 _column_groups', () => {
    for (const section of [listedSection, soeSection]) {
      for (const t of section.tables ?? []) {
        expect(String(t.guidance ?? '').trim(), `${t.name} 缺 guidance`).not.toBe('')
        expect((t.columns ?? []).length, `${t.name} 缺 columns`).toBeGreaterThan(0)
        expect(
          (t.columns ?? []).some(c => c.flat === true),
          `${t.name} 未显式 flat（源模板单行表头）`,
        ).toBe(true)
        expect((t.columns ?? []).some(c => c.group), `${t.name} 不应有 group`).toBe(false)
        expect(t._column_groups, `${t.name} 标了 flat 却留 _column_groups`).toBeUndefined()
      }
    }
  })

  it('无 header_label 假数据行', () => {
    for (const section of [listedSection, soeSection]) {
      for (const t of section.tables ?? []) {
        const bad = (t.rows ?? []).filter(r => String(r.row_type ?? '') === 'header_label')
        expect(bad, `${t.name} 残留 header_label 假数据行`).toEqual([])
      }
    }
  })

  it('固定行名常量与模板 rows 逐字一致', () => {
    const byName = new Map((listedSection.tables ?? []).map(t => [String(t.name), t]))
    const labelsOf = (t?: NoteTable) => (t?.rows ?? []).map(r => String(r.label ?? ''))

    expect(labelsOf(byName.get(K2_LISTED_SUBTABLE.main))).toEqual([
      ...K2_LISTED_MAIN_ROWS,
      '合计',
    ])
    expect(labelsOf(byName.get(K2_LISTED_SUBTABLE.contractCost))).toEqual([
      ...K2_CONTRACT_COST_ROWS,
    ])
    expect(labelsOf(byName.get(K2_LISTED_SUBTABLE.carbon))).toEqual([...K2_CARBON_ROWS])

    const soeMain = (soeSection.tables ?? []).find(t => t.name === K2_SOE_SUBTABLE.main)
    expect(labelsOf(soeMain)).toEqual([...K2_SOE_MAIN_ROWS, '合计'])
  })
})

// ─── sheet_name ──────────────────────────────────────────────────────────────

describe('K2 sheet_name = 源 xlsx 真实 tab 名（全角括号）', () => {
  it('两版均为全角括号', () => {
    expect(K2_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(K2_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })
})

// ─── 载荷 ────────────────────────────────────────────────────────────────────

function snapshot(overrides: Partial<K2DisclosureSnapshot> = {}): K2DisclosureSnapshot {
  return {
    mainRows: [
      { label: '进项税额', endAmount: 100, priorAmount: 60 },
      { label: '待抵扣进项税额', endAmount: 25, priorAmount: 15 },
    ],
    ...overrides,
  }
}

describe('buildK2SyncPayload', () => {
  it('国企只推主表，键集与 columns 一致', () => {
    const p = buildK2SyncPayload('soe', 'wp-1', snapshot())
    const dataKeys = Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))
    expect(dataKeys).toEqual([K2_SOE_SUBTABLE.main])
    expect(Object.keys(p.columns)).toEqual([K2_SOE_SUBTABLE.main])
    expect(p.section_id).toBe(K2_NOTE_SECTION.soe)
    expect(p.current_standard).toBe('soe_standalone')
    expect(p.sheet_name).toBe(K2_DISCLOSURE_SHEET_NAME.soe)
  })

  it('P1：每张表的行对象业务键 ⊆ columns 键', () => {
    for (const p of [
      buildK2SyncPayload('soe', 'wp-1', snapshot()),
      buildK2SyncPayload('listed', 'wp-1', snapshot({
        contractCost: { enabled: true, categories: ['佣金支出', '中介费'], cells: [] },
        carbon: { enabled: true, rows: [] },
      })),
    ]) {
      for (const [name, rows] of Object.entries(p.sub_table_data)) {
        if (name.startsWith('_')) continue
        const colKeys = new Set((p.columns[name] ?? []).map(c => c.key))
        for (const row of rows as Array<Record<string, unknown>>) {
          for (const key of Object.keys(row)) {
            if (key === 'is_total') continue
            expect(colKeys.has(key), `${name}.${key} 无 columns 落点`).toBe(true)
          }
        }
      }
    }
  })

  it('主表末行为合计行，逐列 = 各明细行之和', () => {
    const p = buildK2SyncPayload('listed', 'wp-1', snapshot())
    const rows = p.sub_table_data[K2_LISTED_SUBTABLE.main] as Array<Record<string, unknown>>
    const total = rows[rows.length - 1]
    expect(total.label).toBe('合计')
    expect(total.is_total).toBe(true)
    expect(total.end_amount).toBe(125)
    expect(total.prior_amount).toBe(60 + 15)
  })

  it('条件性表关闭 → 不推该表且表名进 _removed_table_keys', () => {
    const p = buildK2SyncPayload('listed', 'wp-1', snapshot())
    expect(p.sub_table_data[K2_LISTED_SUBTABLE.contractCost]).toBeUndefined()
    expect(p.sub_table_data[K2_LISTED_SUBTABLE.carbon]).toBeUndefined()
    const removed = p.sub_table_data._removed_table_keys as string[]
    expect(removed).toContain(K2_LISTED_SUBTABLE.contractCost)
    expect(removed).toContain(K2_LISTED_SUBTABLE.carbon)
    for (const legacy of K2_LEGACY_OBSOLETE_TABLES) expect(removed).toContain(legacy)
    // 关闭时 columns 也不带该表（columns 与 sub_table_data 成对进出）
    expect(Object.keys(p.columns)).toEqual([K2_LISTED_SUBTABLE.main])
  })

  it('条件性表开启 → 推送且不在 _removed_table_keys', () => {
    const p = buildK2SyncPayload('listed', 'wp-1', snapshot({
      contractCost: { enabled: true, categories: ['佣金支出'], cells: [] },
      carbon: { enabled: true, rows: [{ label: K2_CARBON_ROWS[0], currentAmount: 7, priorAmount: 3 }] },
    }))
    const removed = p.sub_table_data._removed_table_keys as string[]
    expect(removed).not.toContain(K2_LISTED_SUBTABLE.contractCost)
    expect(removed).not.toContain(K2_LISTED_SUBTABLE.carbon)

    const carbonRows = p.sub_table_data[K2_LISTED_SUBTABLE.carbon] as Array<Record<string, unknown>>
    expect(carbonRows).toHaveLength(K2_CARBON_ROWS.length)
    expect(carbonRows[0]).toMatchObject({ label: K2_CARBON_ROWS[0], current_amount: 7, prior_amount: 3 })
  })

  it('合同取得成本：合计列 = 各类别之和；类别列键随类别数扩展', () => {
    const cells = [
      [10, 20], // 期初余额
      [5, 1], // 本年增加
      [2, 0], // 本年摊销
      [1, 0], // 本年计提减值损失
      [12, 21], // 期末余额（组件侧公式派生）
    ]
    const p = buildK2SyncPayload('listed', 'wp-1', snapshot({
      contractCost: { enabled: true, categories: ['佣金支出', '中介费'], cells },
    }))
    const rows = p.sub_table_data[K2_LISTED_SUBTABLE.contractCost] as Array<Record<string, unknown>>
    expect(rows.map(r => r.label)).toEqual([...K2_CONTRACT_COST_ROWS])
    expect(rows[0]).toMatchObject({ cat_1: 10, cat_2: 20, total: 30 })
    expect(rows[4]).toMatchObject({ cat_1: 12, cat_2: 21, total: 33 })
    expect((p.columns[K2_LISTED_SUBTABLE.contractCost] ?? []).map(c => c.key)).toEqual([
      'label',
      'cat_1',
      'cat_2',
      'total',
    ])
    expect((p.columns[K2_LISTED_SUBTABLE.contractCost] ?? []).map(c => c.label)).toEqual([
      '项目',
      '佣金支出',
      '中介费',
      '合计',
    ])
  })

  it('_note_texts：空文本被剔除，非空按 section/title/text 推送', () => {
    const p = buildK2SyncPayload('listed', 'wp-1', snapshot({
      texts: [
        { section: 'k2-significant', title: '说明', text: '  正文  ' },
        { section: 'k2-carbon', title: '碳排放', text: '   ' },
      ],
    }))
    expect(p.sub_table_data._note_texts).toEqual([
      { section: 'k2-significant', title: '说明', text: '正文' },
    ])
  })

  it('零参 buildK2ListedColumns 返回 seed 形态（sweep 空入参可调）', () => {
    const cols = buildK2ListedColumns()
    expect(Object.keys(cols)).toEqual([
      K2_LISTED_SUBTABLE.main,
      K2_LISTED_SUBTABLE.contractCost,
      K2_LISTED_SUBTABLE.carbon,
    ])
    for (const defs of Object.values(cols)) {
      expect(defs.length).toBeGreaterThan(0)
      for (const d of defs) expect(String(d.label ?? '').trim()).not.toBe('')
    }
  })
})
