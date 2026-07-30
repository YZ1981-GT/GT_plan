/**
 * D3 预收款项披露子表名 ↔ 附注模板契约 + 国企账龄口径映射
 *
 * 防回归两件事：
 * 1. `buildD3SyncPayload` 产出的每个数据子表名必须能在 `note_template_listed.json`
 *    §五、38 / `note_template_soe.json` §八、38 的 `tables[].name` 中逐字找到，
 *    否则 sync-from-workpaper 会写出孤儿子表（附注 TAB 永空 + 底稿数据丢失）。
 * 2. 国企按账龄主表的行名走 `disclosureAgingLabels`（方案 A：同步层映射）——
 *    底稿显示 `1年以内`，推给附注必须是模板字面 `1年以内（含1年）`。
 *
 * 🔴 合计行按 D3 模板逐字为 `合计`（**无空格**，与 D2 §五、5 / §八、5 的 `合 计` 不同），
 *    故 D3 不套 `DISCLOSURE_TOTAL_LABEL`。本测试正向锁死此差异。
 *
 * spec: .kiro/specs/disclosure-columns-coverage-rollout/ R6（Task 13.6）
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  buildD3SyncPayload,
  D3_DISCLOSURE_SHEET_NAME,
  D3_NOTE_SECTION,
  type D3DisclosureSnapshot,
} from '../d3NoteSectionMap'
import { DISCLOSURE_AGING_WITHIN1_SOE } from '../disclosureAgingLabels'

interface NoteTable {
  name?: string
  headers?: string[]
  rows?: Array<{ label?: string; row_type?: string; is_total?: boolean }>
}
interface NoteSection {
  section_number?: string
  tables?: NoteTable[]
}

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function loadSection(file: string, sectionNumber: string): NoteSection {
  const path = resolve(REPO_ROOT, 'backend/data', file)
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as { sections: NoteSection[] }
  const hit = raw.sections.find((s) => String(s.section_number ?? '').trim() === sectionNumber)
  if (!hit) throw new Error(`${file} 缺少章节 ${sectionNumber}`)
  return hit
}

const listedSection = loadSection('note_template_listed.json', D3_NOTE_SECTION.listed)
const soeSection = loadSection('note_template_soe.json', D3_NOTE_SECTION.soe)

/** 国企 section1 两桶行（rowKey 由 useD3DisclosureSoe 透出，供同步层映射） */
const SOE_SNAPSHOT: D3DisclosureSnapshot = {
  mainRows: [
    { rowKey: 'within1', label: '1年以内', endAmount: 800, priorAmount: 600 },
    { rowKey: 'over1', label: '1年以上', endAmount: 200, priorAmount: 150 },
  ],
  mainTotal: { label: '合计', endAmount: 1000, priorAmount: 750 },
  longTermRows: [{ label: '甲公司', endAmount: 200, priorAmount: 0, reason: '工程未完工' }],
  longTermTotal: { label: '合计', endAmount: 200, priorAmount: 0 },
  notes: {},
}

const LISTED_SNAPSHOT: D3DisclosureSnapshot = {
  mainRows: [{ label: '工程款', endAmount: 500, priorAmount: 400 }],
  mainTotal: { label: '合计', endAmount: 500, priorAmount: 400 },
  longTermRows: [{ label: '乙公司', endAmount: 120, priorAmount: 0, reason: '尚未结转' }],
  longTermTotal: { label: '合计', endAmount: 120, priorAmount: 0 },
  changeRows: [{ label: '预收工程款', endAmount: 500, priorAmount: 400, reason: '新签合同' }],
  notes: { nature: '主要为工程款预收。' },
}

function dataTableNames(payload: { sub_table_data: Record<string, unknown> }): string[] {
  return Object.keys(payload.sub_table_data).filter((k) => !k.startsWith('_'))
}

describe('D3 子表名 ↔ note_template 契约', () => {
  it('国企载荷子表名逐字存在于 §八、38', () => {
    const payload = buildD3SyncPayload('soe', 'wp-1', ['soe_standalone'], SOE_SNAPSHOT)
    const tplNames = (soeSection.tables ?? []).map((t) => t.name)
    expect(dataTableNames(payload)).toEqual(['预收款项', '账龄超过1年的重要预收款项'])
    for (const name of dataTableNames(payload)) {
      expect(tplNames, `孤儿子表「${name}」`).toContain(name)
    }
  })

  it('上市载荷子表名逐字存在于 §五、38', () => {
    const payload = buildD3SyncPayload('listed', 'wp-1', ['listed_standalone'], LISTED_SNAPSHOT)
    const tplNames = (listedSection.tables ?? []).map((t) => t.name)
    expect(dataTableNames(payload)).toEqual([
      '预收款项',
      '账龄超过1年的重要预收款项',
      '本期预收账款账面价值的重大变动',
    ])
    for (const name of dataTableNames(payload)) {
      expect(tplNames, `孤儿子表「${name}」`).toContain(name)
    }
  })

  it('sheet_name / section_id 为源 xlsx tab 名与模板章节号', () => {
    const soe = buildD3SyncPayload('soe', 'wp-1', ['soe_consolidated'], SOE_SNAPSHOT)
    expect(soe.sheet_name).toBe(D3_DISCLOSURE_SHEET_NAME.soe)
    expect(soe.section_id).toBe('八、38')
    expect(soe.current_standard).toBe('soe_consolidated')
  })
})

describe('D3 国企按账龄主表行名（方案 A：同步层映射）', () => {
  const payload = buildD3SyncPayload('soe', 'wp-1', ['soe_standalone'], SOE_SNAPSHOT)
  const rows = payload.sub_table_data['预收款项'] as Array<Record<string, unknown>>

  it('首档映射为模板字面「1年以内（含1年）」，底稿快照仍是「1年以内」', () => {
    expect(rows.map((r) => r.label)).toEqual([DISCLOSURE_AGING_WITHIN1_SOE, '1年以上', '合计'])
    // Property 8：不改入参（底稿显示口径不受影响）
    expect(SOE_SNAPSHOT.mainRows.map((r) => r.label)).toEqual(['1年以内', '1年以上'])
  })

  it('行名与模板 §八、38 主表数据行逐字一致', () => {
    const tplRows = (table(soeSection, '预收款项').rows ?? []).map((r) => r.label)
    expect(rows.map((r) => r.label)).toEqual(tplRows)
  })

  it('合计行字面为「合计」（无空格），不套 D2 的「合 计」', () => {
    expect(rows[rows.length - 1]).toMatchObject({ label: '合计', is_total: true })
    expect(rows.map((r) => r.label)).not.toContain('合 计')
  })

  it('金额原样透传，合计不重算', () => {
    expect(rows[0]).toMatchObject({ end_amount: 800, prior_amount: 600 })
    expect(rows[2]).toMatchObject({ end_amount: 1000, prior_amount: 750 })
  })
})

describe('D3 上市主表不做账龄映射（按性质分类）', () => {
  it('性质行名原样透传', () => {
    const payload = buildD3SyncPayload('listed', 'wp-1', ['listed_standalone'], LISTED_SNAPSHOT)
    const rows = payload.sub_table_data['预收款项'] as Array<Record<string, unknown>>
    expect(rows.map((r) => r.label)).toEqual(['工程款', '合计'])
  })

  it('重大变动表变动金额 = 期末 − 期初', () => {
    const payload = buildD3SyncPayload('listed', 'wp-1', ['listed_standalone'], LISTED_SNAPSHOT)
    const rows = payload.sub_table_data['本期预收账款账面价值的重大变动'] as Array<Record<string, unknown>>
    expect(rows[0]).toMatchObject({ label: '预收工程款', change_amount: 100 })
    expect(rows[1]).toMatchObject({ label: '合计', change_amount: 100, is_total: true })
  })

  it('文本框内容进 _note_texts', () => {
    const payload = buildD3SyncPayload('listed', 'wp-1', ['listed_standalone'], LISTED_SNAPSHOT)
    expect(payload.sub_table_data._note_texts).toEqual([
      { section: 'note-nature', title: '按性质分类说明', text: '主要为工程款预收。' },
    ])
  })
})

function table(section: NoteSection, name: string): NoteTable {
  const hit = (section.tables ?? []).find((t) => t.name === name)
  if (!hit) {
    throw new Error(
      `未找到子表「${name}」，现有：${(section.tables ?? []).map((t) => t.name).join(' / ')}`,
    )
  }
  return hit
}
