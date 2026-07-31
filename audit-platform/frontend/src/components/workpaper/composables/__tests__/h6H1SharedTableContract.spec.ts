/**
 * H1 ↔ H6 共享子表契约守卫。
 *
 * 背景：H6 固定资产清理**没有独立附注章节** —— `H6_NOTE_SECTION = H1_NOTE_SECTION`
 * （上市 §五、22 / 国企 §八、22 = 固定资产），H6 只推「固定资产清理」子表并浅合并刷新
 * 汇总表「固定资产」里的清理行（与 H4→H2 工程物资同款模式）。
 *
 * 两个循环写同一章节时，列定义与合计行字面必须与**附注模板**一致，否则
 * `_sub_table_columns` 会随最后一次同步跳变，而两侧单测各自都是绿的
 * （H4 曾实测踩中：自造列定义缺 format=amount + 合计行推「合  计」）。
 *
 * 本守卫锁定：
 * - H6 清理表列定义 ≡ 附注模板 §五、22 / §八、22 的「固定资产清理」columns
 * - 两变体列名不同（上市 期末余额/上年年末余额；国企 期末账面价值/期初账面价值）
 * - H6 只声明它实际推送的清理表，不越界重定义 H1 的汇总表列
 * - 合计行字面 = 模板字面「合计」
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  H6_CLEARING_SUBTABLE,
  H6_NOTE_SECTION,
  H6_SUMMARY_SUBTABLE,
} from '../h6NoteSectionMap'
import {
  buildH6ListedClearingSubTable,
  buildH6ListedSyncPayloads,
  buildH6SoeClearingSubTable,
  buildH6SoeSyncPayloads,
} from '../h6DisclosureSyncPayload'
import { H1_NOTE_SECTION } from '../h1NoteSectionMap'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function templateTable(variant: 'listed' | 'soe', section: string, name: string) {
  const file = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
  const raw = JSON.parse(
    readFileSync(resolve(REPO_ROOT, 'backend/data', file), 'utf-8'),
  ) as { sections?: Array<Record<string, any>> }
  const sec = (raw.sections ?? []).find((s) => String(s.section_number).trim() === section)
  return (sec?.tables ?? []).find((t: any) => t.name === name)
}

const STATE = {
  clearingRows: [
    { name: '报废设备A', endBalance: 1000, priorBalance: 800, reason: '技术淘汰' },
  ],
  clearingNote: '',
  faEnd: 0,
  faPrior: 0,
} as never

describe('H6 复用 H1 章节（无独立章节）', () => {
  it('H6 章节号 === H1 章节号（固定资产）', () => {
    expect(H6_NOTE_SECTION).toBe(H1_NOTE_SECTION)
    expect(H6_NOTE_SECTION.listed).toBe('五、22')
    expect(H6_NOTE_SECTION.soe).toBe('八、22')
  })

  it('清理表 / 汇总表名逐字命中附注模板', () => {
    expect(templateTable('listed', '五、22', H6_CLEARING_SUBTABLE)).toBeDefined()
    expect(templateTable('soe', '八、22', H6_CLEARING_SUBTABLE)).toBeDefined()
    expect(templateTable('listed', '五、22', H6_SUMMARY_SUBTABLE)).toBeDefined()
    expect(templateTable('soe', '八、22', H6_SUMMARY_SUBTABLE)).toBeDefined()
  })
})

describe('H6 清理表列定义 ≡ 附注模板 columns', () => {
  it.each([
    ['listed', '五、22'],
    ['soe', '八、22'],
  ] as const)('%s 变体列 key/label 与模板逐字一致', (variant, section) => {
    const payloads = variant === 'listed'
      ? buildH6ListedSyncPayloads('wp1', ['listed_standalone'], STATE)
      : buildH6SoeSyncPayloads('wp1', ['soe_standalone'], STATE)
    expect(payloads).toHaveLength(1)
    const cols = (payloads[0].columns || {})[H6_CLEARING_SUBTABLE]
    expect(cols, '载荷缺清理表列定义').toBeDefined()

    const tpl = templateTable(variant, section, H6_CLEARING_SUBTABLE)!
    expect(cols.map((c) => c.key)).toEqual((tpl.columns as any[]).map((c) => c.key))
    expect(cols.map((c) => c.label)).toEqual((tpl.columns as any[]).map((c) => c.label))
    // 标签列头必须等于模板 headers[0]
    expect(cols[0].label).toBe(tpl.headers[0])
  })

  it('两变体列名按源模板口径不同（上市余额 / 国企账面价值）', () => {
    const l = (buildH6ListedSyncPayloads('wp1', ['listed_standalone'], STATE)[0].columns || {})[H6_CLEARING_SUBTABLE]
    const s = (buildH6SoeSyncPayloads('wp1', ['soe_standalone'], STATE)[0].columns || {})[H6_CLEARING_SUBTABLE]
    expect(l.map((c) => c.label)).toEqual(['项目', '期末余额', '上年年末余额', '转入清理的原因'])
    expect(s.map((c) => c.label)).toEqual(['项目', '期末账面价值', '期初账面价值', '转入清理的原因'])
    expect(l.map((c) => c.label)).not.toEqual(s.map((c) => c.label))
  })

  it('只声明实际推送的清理表，不越界重定义 H1 汇总表列', () => {
    for (const p of [
      buildH6ListedSyncPayloads('wp1', ['listed_standalone'], STATE)[0],
      buildH6SoeSyncPayloads('wp1', ['soe_standalone'], STATE)[0],
    ]) {
      expect(Object.keys(p.columns || {})).toEqual([H6_CLEARING_SUBTABLE])
      // 汇总表只补行（浅合并），不得带列定义 → 避免与 H1 的列定义分叉
      expect(Object.keys(p.columns || {})).not.toContain(H6_SUMMARY_SUBTABLE)
    }
  })
})

describe('H6 合计行字面与模板一致', () => {
  it('两变体合计行推「合计」（模板字面，无空格）', () => {
    for (const rows of [
      buildH6ListedClearingSubTable(STATE.clearingRows as never),
      buildH6SoeClearingSubTable(STATE.clearingRows as never),
    ]) {
      const total = rows.find((r) => r.is_total)!
      expect(total.label).toBe('合计')
      expect(rows.map((r) => r.label)).not.toContain('合  计')
    }
  })

  it('上市/国企清理表行键与各自列 key 对应（不串味）', () => {
    const l = buildH6ListedClearingSubTable(STATE.clearingRows as never)[0]
    expect(l).toHaveProperty('end_balance')
    expect(l).not.toHaveProperty('end_carrying')
    const s = buildH6SoeClearingSubTable(STATE.clearingRows as never)[0]
    expect(s).toHaveProperty('end_carrying')
    expect(s).not.toHaveProperty('end_balance')
  })
})
