/**
 * E1 披露子表 ↔ note_template 契约（共享 helper P1~P6）
 *
 * 两版章节：上市 `五、1` / 国企 `八、1`，各 2 张表
 * （主表「货币资金」+②「受限制的货币资金明细」，②表上市侧按用户裁决补建）。
 *
 * 另加 E1 专属断言：
 * - 单级表头必须标 `flat`（源模板两版都是 3 列单级，不标会被
 *   `_infer_groups_from_headers` 凭空推出父表头）
 * - 载荷侧与 seed 侧列定义**同一真源**（`buildE1*Columns`），不得在 payload 里另写一份
 * - ②表**不推「受限原因」列**（源模板只有 3 列，事由走 `_note_texts`）
 * - 合计行字面按本章节实证取 `合计`（**不套**平台的 `合 计`）
 * - `sheet_name` 保持**半角括号**（源 xlsx tab 名实证）
 *
 * spec: e1-four-table-extraction-and-disclosure-alignment / Task 10
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  E1_DISCLOSURE_SHEET_NAME,
  E1_LISTED_SUBTABLE,
  E1_MAIN_TABLE,
  E1_NOTE_SECTION,
  E1_NOTE_TOTAL_LABEL,
  E1_RESTRICTED_TABLE,
  E1_SOE_SUBTABLE,
  buildE1ListedColumns,
  buildE1SoeColumns,
  buildE1SyncPayload,
  resolveE1CurrentStandard,
  type E1DisclosureSnapshot,
} from '../e1NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'E1',
  variants: [
    {
      variant: 'listed',
      section: E1_NOTE_SECTION.listed,
      subtables: E1_LISTED_SUBTABLE,
      columns: buildE1ListedColumns(),
    },
    {
      variant: 'soe',
      section: E1_NOTE_SECTION.soe,
      subtables: E1_SOE_SUBTABLE,
      columns: buildE1SoeColumns(),
    },
  ],
})

// ─── E1 专属断言 ───────────────────────────────────────────────────────────────

const MAP_SRC = readFileSync(resolve(__dirname, '../e1NoteSectionMap.ts'), 'utf-8')

function snapshot(): E1DisclosureSnapshot {
  return {
    mainRows: [
      { key: 'cash', label: '现金', endingAmount: 100, openingAmount: 80 },
      { key: 'total', label: '合计', endingAmount: 100, openingAmount: 80 },
    ],
    restrictedRows: [
      { item: '保证金存款', openingAmount: 30, endingAmount: 40, reason: '开具银行承兑汇票保证金' },
    ],
  } as E1DisclosureSnapshot
}

describe('E1 披露载荷专属契约', () => {
  it('单级表头两版都必须标 flat（seed 与推送同一真源）', () => {
    for (const cols of [buildE1ListedColumns(), buildE1SoeColumns()]) {
      for (const [name, defs] of Object.entries(cols)) {
        expect(defs.length, name).toBe(3)
        expect(defs.some((c) => c.flat), `${name} 未标 flat`).toBe(true)
        expect(defs.some((c) => c.group), `${name} 不应声明 group（源模板是单级表头）`).toBe(false)
      }
    }
  })

  it('两版列头 label 必须不同（上市「上年年末余额」/ 国企「期初余额」）', () => {
    const l = buildE1ListedColumns()[E1_MAIN_TABLE].map((c) => c.label)
    const s = buildE1SoeColumns()[E1_MAIN_TABLE].map((c) => c.label)
    expect(l).toEqual(['项目', '期末余额', '上年年末余额'])
    expect(s).toEqual(['项目', '期末余额', '期初余额'])
    expect(l).not.toEqual(s)
  })

  it('🔴 载荷 columns 委托零参 builder，不得在 payload 里另写一份列定义', () => {
    const payload = buildE1SyncPayload('soe', 'wp-1', ['soe_standalone'], snapshot())!
    const expected = buildE1SoeColumns()
    expect(payload.columns[E1_MAIN_TABLE]).toBe(expected[E1_MAIN_TABLE])
    expect(payload.columns[E1_RESTRICTED_TABLE]).toBe(expected[E1_RESTRICTED_TABLE])
    // 源码级：payload 里不得直接引用私有列常量（否则又成双真源）
    const bodyStart = MAP_SRC.indexOf('export function buildE1SyncPayload')
    const body = MAP_SRC.slice(bodyStart)
    expect(body).not.toMatch(/columns\[[^\]]+\]\s*=\s*\n?\s*variant === 'soe' \? RESTRICTED_COLUMNS_SOE/)
    expect(body).toContain('buildE1SoeColumns()')
  })

  it('🔴 ②表不推「受限原因」列（源模板只有 3 列，事由走 _note_texts）', () => {
    const payload = buildE1SyncPayload('listed', 'wp-1', ['listed_standalone'], snapshot())!
    const rows = payload.sub_table_data[E1_RESTRICTED_TABLE] as Array<Record<string, unknown>>
    expect(rows.length).toBe(2) // 1 明细 + 1 合计
    for (const r of rows) {
      expect(Object.keys(r).sort()).not.toContain('reason')
    }
    const colKeys = payload.columns[E1_RESTRICTED_TABLE].map((c) => c.key)
    expect(colKeys).toEqual(['label', 'end_amount', 'prior_amount'])
  })

  it('合计行字面按本章节实证取「合计」（不套平台的「合 计」）', () => {
    expect(E1_NOTE_TOTAL_LABEL).toBe('合计')
    expect(E1_NOTE_TOTAL_LABEL).not.toContain(' ')
    const payload = buildE1SyncPayload('soe', 'wp-1', ['soe_standalone'], snapshot())!
    const rows = payload.sub_table_data[E1_RESTRICTED_TABLE] as Array<Record<string, unknown>>
    const total = rows[rows.length - 1]
    expect(total.label).toBe('合计')
    expect(total.is_total).toBe(true)
    expect(total.end_amount).toBe(40)
    expect(total.prior_amount).toBe(30)
  })

  it('🔴 sheet_name 保持半角括号（源 xlsx tab 名实证）', () => {
    expect(E1_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息(上市公司)')
    expect(E1_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息(国企)')
    for (const v of ['listed', 'soe'] as const) {
      const name = E1_DISCLOSURE_SHEET_NAME[v]
      expect(name).not.toContain('（')
      expect(name).not.toContain('）')
      expect(buildE1SyncPayload(v, 'wp-1', [], snapshot())!.sheet_name).toBe(name)
    }
  })

  it('restrictedRows === undefined（不管这张表）→ 不推且不进 _removed_table_keys', () => {
    const snap = { ...snapshot(), restrictedRows: undefined } as E1DisclosureSnapshot
    const payload = buildE1SyncPayload('soe', 'wp-1', [], snap)!
    expect(payload.sub_table_data[E1_RESTRICTED_TABLE]).toBeUndefined()
    expect(payload.sub_table_data._removed_table_keys).toBeUndefined()
  })

  it('restrictedRows === [] （管但为空）→ 进 _removed_table_keys', () => {
    const snap = { ...snapshot(), restrictedRows: [] } as E1DisclosureSnapshot
    const payload = buildE1SyncPayload('soe', 'wp-1', [], snap)!
    expect(payload.sub_table_data[E1_RESTRICTED_TABLE]).toBeUndefined()
    expect(payload.sub_table_data._removed_table_keys).toEqual([E1_RESTRICTED_TABLE])
  })

  it('current_standard 随准则变（漏传 → 退化 *_standalone，这是修掉的旧缺陷）', () => {
    expect(resolveE1CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
    expect(resolveE1CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveE1CurrentStandard('soe', null)).toBe('soe_standalone')
    const p = buildE1SyncPayload('soe', 'wp-1', ['soe_consolidated'], snapshot())!
    expect(p.current_standard).toBe('soe_consolidated')
  })

  it('_note_texts 每条带中文 title 且无空文本', () => {
    const snap = snapshot()
    ;(snap as any).noteTexts = { 'listed-restricted': '本期存在保证金存款。' }
    const p = buildE1SyncPayload('listed', 'wp-1', [], snap)!
    const texts = p.sub_table_data._note_texts as Array<Record<string, string>> | undefined
    for (const t of texts ?? []) {
      expect(String(t.title || '').length, `缺中文 title：${JSON.stringify(t)}`).toBeGreaterThan(0)
      expect(/^[\x20-\x7E]+$/.test(String(t.title)), `title 不应是英文键：${t.title}`).toBe(false)
      expect(String(t.text || '').trim().length).toBeGreaterThan(0)
    }
  })
})
