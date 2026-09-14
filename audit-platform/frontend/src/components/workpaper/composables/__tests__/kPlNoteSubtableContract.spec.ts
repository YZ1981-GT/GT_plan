/**
 * K 系损益类（K8~K13）披露子表 ↔ 附注模板契约 + 载荷断言
 *
 * 六循环两版共 12 个章节。P1~P5 由共享 helper 覆盖；本文件另断言：
 * - 列与模板 `headers` **逐位同形**（K10 国企 4 列 / K12 K13 两版 4 列）
 * - 合计行派生（含第 4 列金额型求和、文本型置 null）
 * - 结构行「其中：政府补助」排在合计**之后**且不参与求和
 * - 上市侧章节号为模板实测截断值（`三、资产减值损失（损` 等）
 * - 历史孤儿表名进 `_removed_table_keys`
 *
 * spec: .kiro/specs/k-cycle-disclosure-alignment/ Task 4.1
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  K8_DISCLOSURE_SHEET_NAME,
  K8_LEGACY_OBSOLETE_TABLES,
  K8_LISTED_SUBTABLE,
  K8_NOTE_SECTION,
  K8_SOE_SUBTABLE,
  buildK8ListedColumns,
  buildK8SoeColumns,
  buildK8SyncPayload,
} from '../k8NoteSectionMap'
import {
  K9_LEGACY_OBSOLETE_TABLES,
  K9_LISTED_SUBTABLE,
  K9_NOTE_SECTION,
  K9_SOE_SUBTABLE,
  buildK9ListedColumns,
  buildK9SoeColumns,
  buildK9SyncPayload,
} from '../k9NoteSectionMap'
import {
  K10_LISTED_SUBTABLE,
  K10_NOTE_SECTION,
  K10_SOE_STRUCTURAL_ROW,
  K10_SOE_SUBTABLE,
  buildK10ListedColumns,
  buildK10SoeColumns,
  buildK10SyncPayload,
} from '../k10NoteSectionMap'
import {
  K11_LEGACY_OBSOLETE_TABLES,
  K11_LISTED_ROWS,
  K11_LISTED_SUBTABLE,
  K11_NOTE_SECTION,
  K11_SOE_ROWS,
  K11_SOE_SUBTABLE,
  buildK11ListedColumns,
  buildK11SoeColumns,
  buildK11SyncPayload,
} from '../k11NoteSectionMap'
import {
  K12_LEGACY_OBSOLETE_TABLES,
  K12_LISTED_SUBTABLE,
  K12_NOTE_SECTION,
  K12_SOE_SUBTABLE,
  buildK12ListedColumns,
  buildK12SoeColumns,
  buildK12SyncPayload,
} from '../k12NoteSectionMap'
import {
  K13_LEGACY_OBSOLETE_TABLES,
  K13_LISTED_SUBTABLE,
  K13_NOTE_SECTION,
  K13_SOE_SUBTABLE,
  buildK13ListedColumns,
  buildK13SoeColumns,
  buildK13SyncPayload,
} from '../k13NoteSectionMap'

// ─── 共享 helper：P1~P5 ──────────────────────────────────────────────────────

runDisclosureSubtableContract({
  cycle: 'K8',
  variants: [
    { variant: 'listed', section: K8_NOTE_SECTION.listed, subtables: K8_LISTED_SUBTABLE, columns: buildK8ListedColumns() },
    { variant: 'soe', section: K8_NOTE_SECTION.soe, subtables: K8_SOE_SUBTABLE, columns: buildK8SoeColumns() },
  ],
})
runDisclosureSubtableContract({
  cycle: 'K9',
  variants: [
    { variant: 'listed', section: K9_NOTE_SECTION.listed, subtables: K9_LISTED_SUBTABLE, columns: buildK9ListedColumns() },
    { variant: 'soe', section: K9_NOTE_SECTION.soe, subtables: K9_SOE_SUBTABLE, columns: buildK9SoeColumns() },
  ],
})
runDisclosureSubtableContract({
  cycle: 'K10',
  variants: [
    { variant: 'listed', section: K10_NOTE_SECTION.listed, subtables: K10_LISTED_SUBTABLE, columns: buildK10ListedColumns() },
    { variant: 'soe', section: K10_NOTE_SECTION.soe, subtables: K10_SOE_SUBTABLE, columns: buildK10SoeColumns() },
  ],
})
runDisclosureSubtableContract({
  cycle: 'K11',
  variants: [
    { variant: 'listed', section: K11_NOTE_SECTION.listed, subtables: K11_LISTED_SUBTABLE, columns: buildK11ListedColumns() },
    { variant: 'soe', section: K11_NOTE_SECTION.soe, subtables: K11_SOE_SUBTABLE, columns: buildK11SoeColumns() },
  ],
})
runDisclosureSubtableContract({
  cycle: 'K12',
  variants: [
    { variant: 'listed', section: K12_NOTE_SECTION.listed, subtables: K12_LISTED_SUBTABLE, columns: buildK12ListedColumns() },
    { variant: 'soe', section: K12_NOTE_SECTION.soe, subtables: K12_SOE_SUBTABLE, columns: buildK12SoeColumns() },
  ],
})
runDisclosureSubtableContract({
  cycle: 'K13',
  variants: [
    { variant: 'listed', section: K13_NOTE_SECTION.listed, subtables: K13_LISTED_SUBTABLE, columns: buildK13ListedColumns() },
    { variant: 'soe', section: K13_NOTE_SECTION.soe, subtables: K13_SOE_SUBTABLE, columns: buildK13SoeColumns() },
  ],
})

// ─── 模板侧：列逐位同形 + 无占位行 + guidance ─────────────────────────────────

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
  const raw = JSON.parse(readFileSync(resolve(REPO_ROOT, 'backend/data', file), 'utf-8')) as {
    sections: Array<{ section_number?: string; tables?: NoteTable[] }>
  }
  const hit = raw.sections.find(s => String(s.section_number ?? '').trim() === sectionNumber)
  if (!hit) throw new Error(`${file} 缺少章节 ${sectionNumber}`)
  return hit
}

const PLACEHOLDER_ROWS = ['可无限量添加行', '......', '……']

const CASES = [
  { cycle: 'K8', variant: 'listed' as const, section: K8_NOTE_SECTION.listed, table: K8_LISTED_SUBTABLE.main, cols: buildK8ListedColumns() },
  { cycle: 'K8', variant: 'soe' as const, section: K8_NOTE_SECTION.soe, table: K8_SOE_SUBTABLE.main, cols: buildK8SoeColumns() },
  { cycle: 'K9', variant: 'listed' as const, section: K9_NOTE_SECTION.listed, table: K9_LISTED_SUBTABLE.main, cols: buildK9ListedColumns() },
  { cycle: 'K9', variant: 'soe' as const, section: K9_NOTE_SECTION.soe, table: K9_SOE_SUBTABLE.main, cols: buildK9SoeColumns() },
  { cycle: 'K10', variant: 'listed' as const, section: K10_NOTE_SECTION.listed, table: K10_LISTED_SUBTABLE.main, cols: buildK10ListedColumns() },
  { cycle: 'K10', variant: 'soe' as const, section: K10_NOTE_SECTION.soe, table: K10_SOE_SUBTABLE.main, cols: buildK10SoeColumns() },
  { cycle: 'K11', variant: 'listed' as const, section: K11_NOTE_SECTION.listed, table: K11_LISTED_SUBTABLE.main, cols: buildK11ListedColumns() },
  { cycle: 'K11', variant: 'soe' as const, section: K11_NOTE_SECTION.soe, table: K11_SOE_SUBTABLE.main, cols: buildK11SoeColumns() },
  { cycle: 'K12', variant: 'listed' as const, section: K12_NOTE_SECTION.listed, table: K12_LISTED_SUBTABLE.main, cols: buildK12ListedColumns() },
  { cycle: 'K12', variant: 'soe' as const, section: K12_NOTE_SECTION.soe, table: K12_SOE_SUBTABLE.main, cols: buildK12SoeColumns() },
  { cycle: 'K13', variant: 'listed' as const, section: K13_NOTE_SECTION.listed, table: K13_LISTED_SUBTABLE.main, cols: buildK13ListedColumns() },
  { cycle: 'K13', variant: 'soe' as const, section: K13_NOTE_SECTION.soe, table: K13_SOE_SUBTABLE.main, cols: buildK13SoeColumns() },
]

const FILE_OF = { listed: 'note_template_listed.json', soe: 'note_template_soe.json' } as const

describe('K 系损益类模板结构（fix_note_k_pl_structure.py 成果防回退）', () => {
  it.each(CASES)('$cycle $variant 列与模板 headers 逐位同形', (c) => {
    const sec = loadSection(FILE_OF[c.variant], c.section)
    const tbl = (sec.tables ?? []).find(t => t.name === c.table)
    expect(tbl, `模板缺表「${c.table}」`).toBeDefined()
    const defs = c.cols[c.table] ?? []
    expect(defs.map(d => String(d.label))).toEqual(tbl!.headers)
  })

  it.each(CASES)('$cycle $variant 显式 flat 且无 _column_groups', (c) => {
    const sec = loadSection(FILE_OF[c.variant], c.section)
    const tbl = (sec.tables ?? []).find(t => t.name === c.table)!
    expect((tbl.columns ?? []).some(x => x.flat === true)).toBe(true)
    expect((tbl.columns ?? []).some(x => x.group)).toBe(false)
    expect(tbl._column_groups).toBeUndefined()
    expect((c.cols[c.table] ?? []).some(d => d.flat === true)).toBe(true)
  })

  it.each(CASES)('$cycle $variant 有 guidance 且无占位说明行 / 假表头行', (c) => {
    const sec = loadSection(FILE_OF[c.variant], c.section)
    const tbl = (sec.tables ?? []).find(t => t.name === c.table)!
    expect(String(tbl.guidance ?? '').trim()).not.toBe('')
    const labels = (tbl.rows ?? []).map(r => String(r.label ?? ''))
    for (const bad of PLACEHOLDER_ROWS) expect(labels).not.toContain(bad)
    expect((tbl.rows ?? []).some(r => String(r.row_type ?? '') === 'header_label')).toBe(false)
  })

  it('上市侧章节号是模板实测截断值（三、章 md 重建既有形态，不得"修正"）', () => {
    expect(K11_NOTE_SECTION.listed).toBe('三、资产减值损失（损')
    expect(K12_NOTE_SECTION.listed).toBe('三、营业外收入（注：')
    expect(K13_NOTE_SECTION.listed).toBe('三、营业外支出（注：')
  })

  it('K10 国企是 4 列（末列「是否为政府补助」），上市是 3 列', () => {
    expect(buildK10SoeColumns()[K10_SOE_SUBTABLE.main].map(c => c.label)).toEqual([
      '项目', '本期发生额', '上期发生额', '是否为政府补助',
    ])
    expect(buildK10ListedColumns()[K10_LISTED_SUBTABLE.main]).toHaveLength(3)
  })

  it('K12 / K13 两版都含第 4 列「计入当期非经常性损益的金额」', () => {
    for (const cols of [
      buildK12ListedColumns()[K12_LISTED_SUBTABLE.main],
      buildK12SoeColumns()[K12_SOE_SUBTABLE.main],
      buildK13ListedColumns()[K13_LISTED_SUBTABLE.main],
      buildK13SoeColumns()[K13_SOE_SUBTABLE.main],
    ]) {
      expect(cols.map(c => c.key)).toContain('non_recurring_amount')
      expect(cols).toHaveLength(4)
    }
  })

  it('K11 固定行常量与模板 rows 逐字一致（不含合计）', () => {
    for (const [variant, section, table, want] of [
      ['listed', K11_NOTE_SECTION.listed, K11_LISTED_SUBTABLE.main, K11_LISTED_ROWS],
      ['soe', K11_NOTE_SECTION.soe, K11_SOE_SUBTABLE.main, K11_SOE_ROWS],
    ] as const) {
      const sec = loadSection(FILE_OF[variant], section)
      const tbl = (sec.tables ?? []).find(t => t.name === table)!
      const labels = (tbl.rows ?? []).map(r => String(r.label ?? '')).filter(l => l !== '合计')
      expect(labels).toEqual([...want])
    }
  })
})

// ─── 载荷侧 ─────────────────────────────────────────────────────────────────

const ROWS3 = [
  { project: '甲项目', currentAmount: 100, priorAmount: 60 },
  { project: '乙项目', currentAmount: 25, priorAmount: 15 },
]

describe('K 系损益类载荷', () => {
  it('P1 双向：数据键 ≡ columns 键（除 is_total）', () => {
    const payloads = [
      buildK8SyncPayload('listed', 'wp-1', ROWS3, ''),
      buildK8SyncPayload('soe', 'wp-1', ROWS3, ''),
      buildK9SyncPayload('listed', 'wp-1', ROWS3, ''),
      buildK10SyncPayload('soe', 'wp-1', ROWS3.map(r => ({ ...r, isGovGrant: '是' })), ''),
      buildK11SyncPayload('listed', 'wp-1', ROWS3, ''),
      buildK12SyncPayload('soe', 'wp-1', ROWS3.map(r => ({ ...r, nonRecurringAmount: 3 })), ''),
      buildK13SyncPayload('listed', 'wp-1', ROWS3.map(r => ({ ...r, nonRecurringAmount: 3 })), ''),
    ]
    for (const p of payloads) {
      for (const [name, rows] of Object.entries(p.sub_table_data)) {
        if (name.startsWith('_')) continue
        const colKeys = new Set((p.columns[name] ?? []).map(c => c.key))
        for (const row of rows as Array<Record<string, unknown>>) {
          for (const k of Object.keys(row)) {
            if (k === 'is_total') continue
            expect(colKeys.has(k), `${name}.${k} 无 columns 落点`).toBe(true)
          }
        }
        expect(new Set(colKeys).size).toBe((p.columns[name] ?? []).length)
      }
    }
  })

  it('不把底稿审计分析列（变动额/变动率/占比/备注）推给附注', () => {
    const p = buildK10SyncPayload('listed', 'wp-1', ROWS3, '')
    const rows = p.sub_table_data[K10_LISTED_SUBTABLE.main] as Array<Record<string, unknown>>
    for (const row of rows) {
      for (const k of Object.keys(row)) {
        expect(['label', 'current_amount', 'prior_amount', 'is_total']).toContain(k)
      }
    }
  })

  it('合计行为末行派生值（金额列求和）', () => {
    const p = buildK9SyncPayload('soe', 'wp-1', ROWS3, '')
    const rows = p.sub_table_data[K9_SOE_SUBTABLE.main] as Array<Record<string, unknown>>
    const total = rows[rows.length - 1]
    expect(total).toMatchObject({ label: '合计', is_total: true, current_amount: 125, prior_amount: 75 })
  })

  it('第 4 列金额型参与合计求和', () => {
    const p = buildK12SyncPayload('listed', 'wp-1', [
      { project: '捐赠利得', currentAmount: 10, priorAmount: 5, nonRecurringAmount: 10 },
      { project: '政府补助', currentAmount: 20, priorAmount: 8, nonRecurringAmount: 4 },
    ], '')
    const rows = p.sub_table_data[K12_LISTED_SUBTABLE.main] as Array<Record<string, unknown>>
    expect(rows[rows.length - 1]).toMatchObject({ is_total: true, non_recurring_amount: 14 })
  })

  it('K10 国企：文本型第 4 列合计置 null；结构行排在合计之后且不参与求和', () => {
    const p = buildK10SyncPayload(
      'soe',
      'wp-1',
      [
        { project: '政府补助', currentAmount: 100, priorAmount: 50, isGovGrant: '是' },
        { project: '个税手续费返还', currentAmount: 20, priorAmount: 10, isGovGrant: '否' },
      ],
      '',
      { currentAmount: 100, priorAmount: 50 },
    )
    const rows = p.sub_table_data[K10_SOE_SUBTABLE.main] as Array<Record<string, unknown>>
    expect(rows.map(r => r.label)).toEqual(['政府补助', '个税手续费返还', '合计', K10_SOE_STRUCTURAL_ROW])
    const total = rows[2]
    expect(total).toMatchObject({ is_total: true, current_amount: 120, prior_amount: 60 })
    expect(total.is_gov_grant).toBeNull()
    expect(rows[3]).toMatchObject({ current_amount: 100, prior_amount: 50 })
  })

  it('入参里已带的合计行被剔除（防双合计）', () => {
    const p = buildK8SyncPayload('soe', 'wp-1', [...ROWS3, { project: '合  计', currentAmount: 125, priorAmount: 75 }], '')
    const rows = p.sub_table_data[K8_SOE_SUBTABLE.main] as Array<Record<string, unknown>>
    expect(rows.filter(r => r.is_total)).toHaveLength(1)
    expect(rows).toHaveLength(3)
  })

  it('历史孤儿表名进 _removed_table_keys（仅上市侧）', () => {
    const cases = [
      [buildK8SyncPayload('listed', 'wp-1', ROWS3, ''), K8_LEGACY_OBSOLETE_TABLES],
      [buildK9SyncPayload('listed', 'wp-1', ROWS3, ''), K9_LEGACY_OBSOLETE_TABLES],
      [buildK11SyncPayload('listed', 'wp-1', ROWS3, ''), K11_LEGACY_OBSOLETE_TABLES],
      [buildK12SyncPayload('listed', 'wp-1', ROWS3, ''), K12_LEGACY_OBSOLETE_TABLES],
      [buildK13SyncPayload('listed', 'wp-1', ROWS3, ''), K13_LEGACY_OBSOLETE_TABLES],
    ] as const
    for (const [p, legacy] of cases) {
      const removed = (p.sub_table_data._removed_table_keys ?? []) as string[]
      for (const name of legacy) expect(removed).toContain(name)
      // 本次推送的表名不得进 removed
      for (const pushed of Object.keys(p.sub_table_data).filter(k => !k.startsWith('_'))) {
        expect(removed).not.toContain(pushed)
      }
    }
    // 国企侧表名未变，不产生 removed
    expect(buildK8SyncPayload('soe', 'wp-1', ROWS3, '').sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('sheet_name 全部为全角括号（源 xlsx 实测）', () => {
    expect(K8_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(K8_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })

  it('narrativeText 为空时不推 _note_texts', () => {
    expect(buildK8SyncPayload('soe', 'wp-1', ROWS3, '   ').sub_table_data._note_texts).toBeUndefined()
    expect(
      buildK8SyncPayload('soe', 'wp-1', ROWS3, '本期销售费用主要为运输费').sub_table_data._note_texts,
    ).toEqual([{ section: 'k8-note', title: '销售费用说明', text: '本期销售费用主要为运输费' }])
  })
})
