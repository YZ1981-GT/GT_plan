/**
 * j1NoteSectionMap 同步载荷守卫 —— 合计行必须推给附注
 *
 * 🔴 P0 回归（2026-07-30 复盘）：组件传给 `buildJ1SyncPayload` 的
 * `summaryData` / `shortTermData` / `postEmploymentData` **都不含合计行**
 * （合计在 `useJ1DisclosureSections` 里是 computed），历史实现直接
 * `mapDisclosureRows(snapshot.summary)` → 同步后附注五、40 / 八、40
 * 三张表**全缺合计行**。附注是交付物，缺合计行等于表没编完。
 *
 * 连带项：底稿 UI 的合计行字面是源模板的「合 计」/「合  计」（中间带空格），
 * 而附注模板是「合计」（无空格）→ 载荷必须用 `J1_NOTE_TOTAL_LABEL`，
 * 否则合计行字面与模板 `rows[].label` 漂移（与 D3 同款坑）。
 *
 * spec: .kiro/specs/j1-disclosure-template-alignment/（复盘 P0）
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  buildJ1SyncPayload,
  J1_NOTE_SECTION,
  J1_NOTE_TOTAL_LABEL,
  J1_SUB_TABLE_KEYS,
  type J1DisclosureVariant,
} from '../j1NoteSectionMap'
import type { J1DisclosureRow } from '@/composables/workpaper/j1/j1DisclosureRowModel'

interface SyncRow {
  label: string
  values: (number | null)[]
  is_total?: boolean
}

function row(
  label: string,
  begin: number,
  increase: number,
  decrease: number,
  indent = 0,
): J1DisclosureRow {
  return {
    id: `r-${label}`,
    label,
    category: 'x',
    ...(indent ? { indent } : {}),
    beginBalance: begin,
    increase,
    decrease,
    endBalance: begin + increase - decrease,
  }
}

/** 汇总表 2 行 + 明细两表（含「其中：」缩进子行，验合计不双算） */
function snapshot() {
  return {
    summary: [row('短期薪酬', 100, 20, 10), row('辞退福利', 50, 5, 1)],
    shortTerm: [
      row('社会保险费', 30, 3, 1),
      row('其中：1．医疗保险费', 10, 1, 0, 1),
      row('2．工伤保险费', 20, 2, 1, 1),
      row('住房公积金', 15, 1, 1),
    ],
    postEmployment: [
      row('离职后福利', 40, 4, 2),
      row('其中：基本养老保险费', 25, 2, 1, 1),
      row('其他长期职工福利（不适用的删除）', 8, 1, 0),
    ],
    notes: {},
  }
}

function payloadTables(variant: J1DisclosureVariant): Record<string, SyncRow[]> {
  const { body } = buildJ1SyncPayload({
    variant,
    wpId: 'wp-1',
    year: 2025,
    snapshot: snapshot(),
  })
  return (body.sub_table_data as Record<string, SyncRow[]>)
}

const VARIANTS: J1DisclosureVariant[] = ['listed', 'soe']

describe('J1 同步载荷：合计行', () => {
  it.each(VARIANTS)('%s 三张表每张都以合计行结尾', (variant) => {
    const tables = payloadTables(variant)
    for (const name of Object.values(J1_SUB_TABLE_KEYS[variant])) {
      const rows = tables[name]
      expect(rows, `${name} 未出现在载荷中`).toBeDefined()
      const last = rows[rows.length - 1]
      expect(last.is_total, `${name} 末行不是合计行 → 附注该表缺合计`).toBe(true)
    }
  })

  it.each(VARIANTS)('%s 合计行字面取附注模板口径「合计」（无空格）', (variant) => {
    const tables = payloadTables(variant)
    expect(J1_NOTE_TOTAL_LABEL).toBe('合计')
    for (const name of Object.values(J1_SUB_TABLE_KEYS[variant])) {
      const rows = tables[name]
      expect(rows[rows.length - 1].label).toBe(J1_NOTE_TOTAL_LABEL)
    }
  })

  it.each(VARIANTS)('%s 合计行字面与模板 rows 里的合计行一致（防字面漂移）', (variant) => {
    const file = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
    const path = resolve(__dirname, '../../../../../../..', 'backend/data', file)
    const doc = JSON.parse(readFileSync(path, 'utf-8')) as {
      sections: Array<{ section_number?: string; tables?: Array<{ name?: string; rows?: Array<Record<string, unknown>> }> }>
    }
    const section = doc.sections.find(
      (s) => String(s.section_number ?? '') === J1_NOTE_SECTION[variant],
    )
    expect(section, `模板缺章节 ${J1_NOTE_SECTION[variant]}`).toBeDefined()
    for (const tbl of section!.tables ?? []) {
      const total = (tbl.rows ?? []).find((r) => r.is_total === true)
      expect(total, `${tbl.name} 模板缺合计行`).toBeDefined()
      expect(String(total!.label)).toBe(J1_NOTE_TOTAL_LABEL)
    }
  })

  it.each(VARIANTS)('%s 汇总表合计 = 各类别行之和', (variant) => {
    const rows = payloadTables(variant)[J1_SUB_TABLE_KEYS[variant].summary]
    // 期初 100+50 / 增加 20+5 / 减少 10+1 / 期末 110+54
    expect(rows[rows.length - 1].values).toEqual([150, 25, 11, 164])
  })

  it.each(VARIANTS)('%s 明细表合计只累加非缩进行（源模板合计公式排除「其中：」）', (variant) => {
    const tables = payloadTables(variant)
    const shortTerm = tables[J1_SUB_TABLE_KEYS[variant].shortTerm]
    // 社会保险费 30/3/1 + 住房公积金 15/1/1（不含医疗 10 与工伤 20）
    expect(shortTerm[shortTerm.length - 1].values).toEqual([45, 4, 2, 47])

    const post = tables[J1_SUB_TABLE_KEYS[variant].postEmployment]
    // 离职后福利 40/4/2 + 其他长期职工福利 8/1/0（不含基本养老 25）
    expect(post[post.length - 1].values).toEqual([48, 5, 2, 51])
  })

  it.each(VARIANTS)('%s 数据行原样保留且不标 is_total', (variant) => {
    const rows = payloadTables(variant)[J1_SUB_TABLE_KEYS[variant].shortTerm]
    expect(rows).toHaveLength(5) // 4 数据行 + 1 合计行
    expect(rows.slice(0, 4).every((r) => r.is_total === undefined)).toBe(true)
    expect(rows[0]).toEqual({ label: '社会保险费', values: [30, 3, 1, 32], is_total: undefined })
  })

  it.each(VARIANTS)('%s 上游已带合计行时不产生双合计（幂等）', (variant) => {
    const snap = snapshot()
    snap.summary.push({ ...row('合 计', 150, 25, 11), isSubtotal: true })
    const { body } = buildJ1SyncPayload({ variant, wpId: 'wp-1', year: 2025, snapshot: snap })
    const rows = (body.sub_table_data as Record<string, SyncRow[]>)[
      J1_SUB_TABLE_KEYS[variant].summary
    ]
    expect(rows.filter((r) => r.is_total)).toHaveLength(1)
    expect(rows[rows.length - 1].label).toBe(J1_NOTE_TOTAL_LABEL)
    expect(rows[rows.length - 1].values).toEqual([150, 25, 11, 164])
  })

  it('空表也补一个全零合计行（附注表头列数不塌）', () => {
    const { body } = buildJ1SyncPayload({
      variant: 'listed',
      wpId: 'wp-1',
      year: 2025,
      snapshot: { summary: [], shortTerm: [], postEmployment: [], notes: {} },
    })
    const rows = (body.sub_table_data as Record<string, SyncRow[]>)[
      J1_SUB_TABLE_KEYS.listed.summary
    ]
    expect(rows).toEqual([{ label: '合计', values: [0, 0, 0, 0], is_total: true }])
  })
})
