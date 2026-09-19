/**
 * F1 预付款项披露子表名 ↔ 附注模板契约
 *
 * 防回归：`F1_LISTED_SUBTABLE` / `F1_SOE_SUBTABLE` 的每个值必须能在
 * `note_template_listed.json` §五、7 / `note_template_soe.json` §八、7
 * 的 `tables[].name` 中**逐字**找到，否则 sync-from-workpaper 会写出孤儿子表
 * （附注 TAB 永空，底稿数据丢失）——修订前国企第 3 张表与第 2 张同名，正踩此坑。
 *
 * spec: f1-prepayment-disclosure-template-alignment R1 / R4 / R6.2
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { F1_NOTE_SECTION } from '../f1NoteSectionMap'
import {
  F1_AGING_LABEL_COL,
  F1_LISTED_AGING_GROUPS,
  F1_LISTED_AMOUNT_LABEL,
  F1_LISTED_COLUMNS,
  F1_LISTED_OBSOLETE_TABLE_KEYS,
  F1_LISTED_PCT_LABEL,
  F1_LISTED_SUBTABLE,
  F1_SOE_AGING_GROUPS,
  F1_SOE_AMOUNT_LABEL,
  F1_SOE_COLUMNS,
  F1_SOE_PCT_LABEL,
  F1_SOE_SUBTABLE,
} from '../f1DisclosureSyncPayload'

interface NoteColumn { key?: string; label?: string; is_label?: boolean; group?: string }
interface NoteRow { label?: string; row_type?: string; is_total?: boolean }
interface NoteTable {
  name?: string
  headers?: string[]
  columns?: NoteColumn[]
  rows?: NoteRow[]
  guidance?: string
  _column_groups?: Array<{ group?: string; start?: number; span?: number }>
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

const listedSection = loadSection('note_template_listed.json', F1_NOTE_SECTION.listed)
const soeSection = loadSection('note_template_soe.json', F1_NOTE_SECTION.soe)

const listedNames = (listedSection.tables ?? []).map((t) => String(t.name))
const soeNames = (soeSection.tables ?? []).map((t) => String(t.name))

function table(section: NoteSection, name: string): NoteTable {
  const hit = (section.tables ?? []).find((t) => t.name === name)
  if (!hit) throw new Error(`缺表「${name}」`)
  return hit
}

describe('F1 子表名 ↔ note_template 契约', () => {
  it.each(Object.entries(F1_LISTED_SUBTABLE))(
    '上市 %s → 「%s」存在于 §五、7',
    (_key, name) => {
      expect(listedNames).toContain(name)
    },
  )

  it.each(Object.entries(F1_SOE_SUBTABLE))(
    '国企 %s → 「%s」存在于 §八、7',
    (_key, name) => {
      expect(soeNames).toContain(name)
    },
  )

  it('表名唯一（国企第 3 张表曾与第 2 张同名 → 孤儿子表）', () => {
    for (const names of [listedNames, soeNames]) {
      expect(new Set(names).size, `重名：${names.join(' / ')}`).toBe(names.length)
    }
  })

  it('旧表名「单位名称」已从附注模板消失（改名迁移完成）', () => {
    for (const k of F1_LISTED_OBSOLETE_TABLE_KEYS) {
      expect(listedNames).not.toContain(k)
    }
  })

  it('两版均为 3 张表', () => {
    expect(listedNames).toHaveLength(3)
    expect(soeNames).toHaveLength(3)
  })
})

describe('附注 §五、7 / §八、7 结构要求', () => {
  it('对齐脚本已打标 _aligned_by', () => {
    // 集合判定：历史批次写归档 spec 名，改标记后重跑脚本前不应打红
    const accepted = new Set([
      'f1-four-table-extraction-and-disclosure-alignment',
      'f1-prepayment-disclosure-template-alignment',
    ])
    for (const s of [listedSection, soeSection]) {
      expect(accepted.has(String(s._aligned_by)), String(s._aligned_by)).toBe(true)
    }
  })

  it('按账龄表为 5 列两级表头 + 7 行（各段 + 小计 + 减：减值准备 + 合计）', () => {
    // 🔴 列头字面**引用常量**（源 xlsx 逐格实证，含空格）：写死字面量必再分叉
    const cases = [
      [
        listedSection, F1_LISTED_SUBTABLE.AGING,
        F1_LISTED_AGING_GROUPS.end, F1_LISTED_AGING_GROUPS.prior,
        F1_LISTED_AMOUNT_LABEL, F1_LISTED_PCT_LABEL,
      ],
      [
        soeSection, F1_SOE_SUBTABLE.AGING,
        F1_SOE_AGING_GROUPS.end, F1_SOE_AGING_GROUPS.prior,
        F1_SOE_AMOUNT_LABEL, F1_SOE_PCT_LABEL,
      ],
    ] as const
    for (const [section, name, endGroup, priorGroup, amountLabel, pctLabel] of cases) {
      const t = table(section, name)
      expect(t.headers, name).toEqual([
        F1_AGING_LABEL_COL, amountLabel, pctLabel, amountLabel, pctLabel,
      ])
      expect(t._column_groups, name).toEqual([
        { group: endGroup, start: 1, span: 2 },
        { group: priorGroup, start: 3, span: 2 },
      ])
      expect((t.columns ?? []).map((c) => c.key), name).toEqual([
        'label', 'end_amount', 'end_pct', 'prior_amount', 'prior_pct',
      ])
      const labels = (t.rows ?? []).map((r) => r.label)
      expect(labels.slice(-3), name).toEqual(['小计', '减：减值准备', '合计'])
      expect(labels, name).toHaveLength(7)
    }
  })

  it('账龄骨架为源模版默认 3 年段四档（5年段/自定义由同步整表覆盖）', () => {
    expect((table(listedSection, F1_LISTED_SUBTABLE.AGING).rows ?? []).slice(0, 4).map((r) => r.label))
      .toEqual(['1年以内', '1至2年', '2至3年', '3年以上'])
    expect((table(soeSection, F1_SOE_SUBTABLE.AGING).rows ?? []).slice(0, 4).map((r) => r.label))
      .toEqual(['1年以内（含1年）', '1至2年', '2至3年', '3年以上'])
  })

  it('无残留 header_label 假数据行', () => {
    for (const section of [listedSection, soeSection]) {
      for (const t of section.tables ?? []) {
        for (const r of t.rows ?? []) {
          expect(r.row_type, `${t.name} 残留 header_label`).not.toBe('header_label')
        }
      }
    }
  })

  it('headers 无空串 + columns 数与 headers 数一致', () => {
    for (const section of [listedSection, soeSection]) {
      for (const t of section.tables ?? []) {
        for (const h of t.headers ?? []) {
          expect(String(h ?? '').trim(), `${t.name} headers 含空串`).not.toBe('')
        }
        expect((t.columns ?? []).length, `${t.name} columns/headers 列数不符`)
          .toBe((t.headers ?? []).length)
      }
    }
  })

  it('每张表都有 guidance（TAB 页签编制提示）', () => {
    for (const section of [listedSection, soeSection]) {
      const missing = (section.tables ?? [])
        .filter((t) => !String(t.guidance ?? '').trim())
        .map((t) => t.name)
      expect(missing, `缺 guidance: ${missing.join(' / ')}`).toHaveLength(0)
    }
  })

  it('同步 columns 的标签列头 = 附注 headers[0]（避免 TAB 首列名漂移）', () => {
    const mismatches: string[] = []
    for (const [section, columns] of [
      [listedSection, F1_LISTED_COLUMNS] as const,
      [soeSection, F1_SOE_COLUMNS] as const,
    ]) {
      for (const [name, cols] of Object.entries(columns)) {
        const expected = table(section, name).headers?.[0]
        const actual = cols.find((c) => c.is_label)?.label
        if (expected !== actual) mismatches.push(`${name}: 附注「${expected}」vs 同步「${actual}」`)
      }
    }
    expect(mismatches, mismatches.join(' / ')).toHaveLength(0)
  })

  it('同步 columns 的键序与附注 columns 键序逐一对应', () => {
    for (const [section, columns] of [
      [listedSection, F1_LISTED_COLUMNS] as const,
      [soeSection, F1_SOE_COLUMNS] as const,
    ]) {
      for (const [name, cols] of Object.entries(columns)) {
        expect((table(section, name).columns ?? []).map((c) => c.key), name)
          .toEqual(cols.map((c) => c.key))
      }
    }
  })

  it('上市超1年表无「账龄」「未结算的原因」列，前五名表无「减值准备」列（F7-9 / F7-13 listed）', () => {
    const over1 = table(listedSection, F1_LISTED_SUBTABLE.OVER1).headers ?? []
    expect(over1).toEqual(['债务人名称', '账面余额', '占预付款项合计的比例（%）', '减值准备'])
    const top5 = table(listedSection, F1_LISTED_SUBTABLE.TOP5).headers ?? []
    expect(top5.some((h) => h.includes('减值准备'))).toBe(false)
  })

  it('国企超1年表五列齐备；前五名表第 4 列为「减值准备」（F7-13 soe）', () => {
    expect(table(soeSection, F1_SOE_SUBTABLE.OVER1).headers)
      .toEqual(['债权单位', '债务单位', '期末余额', '账龄', '未结算的原因'])
    expect(table(soeSection, F1_SOE_SUBTABLE.TOP5).headers?.[3]).toBe('减值准备')
  })

  it('上市 text_sections 保留源模版两种披露格式说明', () => {
    const texts = (listedSection.text_sections ?? []).join('\n')
    expect(texts).toContain('汇总披露格式')
    expect(texts).toContain('分别披露格式')
    expect(texts).toContain('账龄超过1年的金额重要预付账款，应说明未及时结算的原因')
  })

  it('列头字面逐字对齐源 xlsx（含空格）—— 两版金额列空格数不同，不得被 trim', () => {
    // 上市 `B9=金  额`（双空格）/ 国企 `B10=金 额`（单空格）/ 两版 `A8=账  龄`（双空格）
    expect(F1_AGING_LABEL_COL).toBe('账  龄')
    expect(F1_LISTED_AMOUNT_LABEL).toBe('金  额')
    expect(F1_SOE_AMOUNT_LABEL).toBe('金 额')
    expect(F1_LISTED_AMOUNT_LABEL).not.toBe(F1_SOE_AMOUNT_LABEL)
    expect(F1_LISTED_AGING_GROUPS).toEqual({ end: '期末数', prior: '上年年末数' })
    expect(F1_SOE_AGING_GROUPS).toEqual({ end: '期末数', prior: '期初数' })
  })
})
