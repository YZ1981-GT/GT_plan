/**
 * F1 上市③前五名「汇总 / 分别」二选一（Property 7）
 *
 * 源模板 `附注披露信息(上市公司)`：
 *   `A23=（按预付对象集中度，汇总**或**分别披露…）` / `A24=汇总披露格式：` / `A26=分别披露格式：`
 * → 两者**互斥**，不能同时进附注（改造前汇总句与③表同时推送）。
 *
 * spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/ R7
 */
import { describe, expect, it } from 'vitest'
import {
  F1_LISTED_SUBTABLE,
  F1_TOP5_MODE_DEFAULT,
  F1_TOP5_MODE_OPTIONS,
  buildF1ListedSubTableData,
  buildF1SyncPayload,
  normalizeF1Top5Mode,
  type F1ListedSyncSnapshot,
  type F1Top5Mode,
} from '../f1DisclosureSyncPayload'

const SUMMARY_SECTION = 'listed-top5-summary'

function snap(top5Mode?: F1Top5Mode): F1ListedSyncSnapshot {
  return {
    agingRows: [
      { label: '1年以内', endAmount: 100, endPct: 100, priorAmount: 80, priorPct: 100 },
    ],
    agingTotal: { label: '小计', endAmount: 100, endPct: 100, priorAmount: 80, priorPct: 100 },
    impairmentProvision: 0,
    impairmentPrior: 0,
    agingNet: { label: '合计', endAmount: 100, priorAmount: 80 },
    over1YearRows: [],
    over1YearTotal: { endBalance: 0, proportionPct: 0, impairment: 0 },
    top5Rows: [{ entityName: '甲供应商', endBalance: 60, proportionPct: 60 }],
    top5Total: { endBalance: 60, proportionPct: 60 },
    top5SummaryText: '本期按预付对象归集的期末余额前五名预付款项汇总金额60.00元，占比60.00%。',
    top5Mode,
    noteAging: '',
    noteOver1Year: '',
    noteTop5: '',
  }
}

function noteSections(sub: Record<string, unknown>): string[] {
  const texts = (sub._note_texts ?? []) as Array<{ section?: string }>
  return texts.map((t) => String(t.section ?? ''))
}

describe('normalizeF1Top5Mode', () => {
  it('默认为「分别披露格式」（与改造前推③表行为一致 → 升级零回归）', () => {
    expect(F1_TOP5_MODE_DEFAULT).toBe('separate')
    expect(normalizeF1Top5Mode(undefined)).toBe('separate')
    expect(normalizeF1Top5Mode(null)).toBe('separate')
    expect(normalizeF1Top5Mode('')).toBe('separate')
    expect(normalizeF1Top5Mode('xxx')).toBe('separate')
  })

  it('只认 summary 一个非默认值', () => {
    expect(normalizeF1Top5Mode('summary')).toBe('summary')
    expect(normalizeF1Top5Mode(' summary ')).toBe('summary')
  })

  it('选项为中文且与源模板 A24 / A26 字面一致', () => {
    expect(F1_TOP5_MODE_OPTIONS.map((o) => o.label)).toEqual(['分别披露格式', '汇总披露格式'])
    expect(F1_TOP5_MODE_OPTIONS.map((o) => o.value)).toEqual(['separate', 'summary'])
  })
})

describe('Property 7：③表与汇总句恰有一者进附注', () => {
  it.each(['separate', 'summary', undefined] as const)('mode=%s 时互斥', (mode) => {
    const sub = buildF1ListedSubTableData(snap(mode as F1Top5Mode | undefined))
    const hasTable = F1_LISTED_SUBTABLE.TOP5 in sub
    const hasSummary = noteSections(sub).includes(SUMMARY_SECTION)
    expect(hasTable !== hasSummary, `mode=${mode} table=${hasTable} summary=${hasSummary}`).toBe(true)
  })

  it('separate：推③表，不推汇总句，③表不进 _removed_table_keys', () => {
    const sub = buildF1ListedSubTableData(snap('separate'))
    expect(sub[F1_LISTED_SUBTABLE.TOP5]).toBeDefined()
    expect(noteSections(sub)).not.toContain(SUMMARY_SECTION)
    const removed = (sub._removed_table_keys ?? []) as string[]
    expect(removed).not.toContain(F1_LISTED_SUBTABLE.TOP5)
  })

  it('summary：推汇总句，不推③表，③表进 _removed_table_keys（防附注残留过时明细）', () => {
    const sub = buildF1ListedSubTableData(snap('summary'))
    expect(sub[F1_LISTED_SUBTABLE.TOP5]).toBeUndefined()
    expect(noteSections(sub)).toContain(SUMMARY_SECTION)
    const removed = (sub._removed_table_keys ?? []) as string[]
    expect(removed).toContain(F1_LISTED_SUBTABLE.TOP5)
  })

  it('两次切换后载荷回到初始值（可逆，数据不丢）', () => {
    const a = JSON.stringify(buildF1ListedSubTableData(snap('separate')))
    buildF1ListedSubTableData(snap('summary'))
    const b = JSON.stringify(buildF1ListedSubTableData(snap('separate')))
    expect(b).toBe(a)
  })

  it('summary 模式下不再发③表的列元数据（避免附注留无数据的列元数据残片）', () => {
    const payload = buildF1SyncPayload(
      'listed', 'wp-f1', null, buildF1ListedSubTableData(snap('summary')),
    )
    expect(payload).not.toBeNull()
    expect(payload!.columns![F1_LISTED_SUBTABLE.TOP5]).toBeUndefined()
    expect(payload!.columns![F1_LISTED_SUBTABLE.AGING]).toBeDefined()
  })

  it('separate 模式列元数据齐备（三张表）', () => {
    const payload = buildF1SyncPayload(
      'listed', 'wp-f1', null, buildF1ListedSubTableData(snap('separate')),
    )
    expect(Object.keys(payload!.columns!).sort()).toEqual(
      [F1_LISTED_SUBTABLE.AGING, F1_LISTED_SUBTABLE.OVER1, F1_LISTED_SUBTABLE.TOP5].sort(),
    )
  })
})
