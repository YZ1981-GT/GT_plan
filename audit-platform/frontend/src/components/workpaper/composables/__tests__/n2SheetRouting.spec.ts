/**
 * N2 sheet 分发守卫
 *
 * 锁死两个**实测过的**静默失真：
 *
 * P1 **国企判定必须认简体「国企」**。原实现写的是繁体 `國企`，而
 *    `workpaper_sheet_classification`（wp_code=N2）里的真实 tab 名是
 *    `附注披露信息（国企）` → 判定不命中 → 落到 OnlyOffice 兜底，
 *    **国企披露 Tab 从来没渲染过**。vitest 与 `get_diagnostics` 都查不出。
 * P2 **披露判定必须前置于 wp_code 正则**。平台实测（D2）披露 tab 名可能尾部带 wp_code
 *    （`附注披露信息（国企）D2-1`），先跑 `/N2-\d+/` 会把披露判成明细表。
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`
 */
import { describe, expect, it } from 'vitest'
import {
  N2_SHEET_DISCLOSURE_LISTED,
  N2_SHEET_DISCLOSURE_SOE,
  N2_SHEET_INDEX,
  isN2HtmlSheet,
  normalizeN2SheetName,
} from '../n2SheetRouting'

/** DB 实测的真实 tab 名 */
const REAL_LISTED = '附注披露信息（上市公司）'
const REAL_SOE = '附注披露信息（国企）'

describe('N2 sheet 分发', () => {
  it('P1 简体「国企」命中国企披露（原繁体 國企 实现下恒不命中）', () => {
    expect(normalizeN2SheetName(REAL_SOE)).toBe(N2_SHEET_DISCLOSURE_SOE)
  })

  it('P1 上市披露命中', () => {
    expect(normalizeN2SheetName(REAL_LISTED)).toBe(N2_SHEET_DISCLOSURE_LISTED)
  })

  it.each([
    '附注披露信息（国企）',
    '附注披露信息(国企)',
    '附注披露信息（国有企业）',
    '附注披露信息（國企）',
  ])('P1 国企多种写法都认：%s', (name) => {
    expect(normalizeN2SheetName(name)).toBe(N2_SHEET_DISCLOSURE_SOE)
  })

  it('P2 披露 tab 名尾部带 wp_code 时不被明细表正则抢占', () => {
    expect(normalizeN2SheetName('附注披露信息（国企）N2-2')).toBe(N2_SHEET_DISCLOSURE_SOE)
    expect(normalizeN2SheetName('附注披露信息（上市公司）N2-1')).toBe(N2_SHEET_DISCLOSURE_LISTED)
  })

  it.each([
    ['应交税费审定表N2-1', 'N2-1'],
    ['应交税费明细表N2-2', 'N2-2'],
    ['土地增值税测算表N2-10', 'N2-10'],
    ['应交税费审计程序表N2A', 'N2A'],
  ])('普通 sheet 仍按 wp_code 分发：%s', (name, expected) => {
    expect(normalizeN2SheetName(name)).toBe(expected)
  })

  it('底稿目录命中', () => {
    expect(normalizeN2SheetName('底稿目录')).toBe(N2_SHEET_INDEX)
  })

  it('sheetName 缺失时回退 wpCode', () => {
    expect(normalizeN2SheetName('', 'N2')).toBe('N2')
    expect(normalizeN2SheetName(null, 'N2-5')).toBe('N2-5')
  })

  it('未识别 sheet 原样返回（走 OnlyOffice 兜底）', () => {
    expect(normalizeN2SheetName('出口退税额复核示例')).toBe('出口退税额复核示例')
    expect(normalizeN2SheetName('GT_Custom')).toBe('GT_Custom')
  })
})

describe('N2 HTML sheet 判定', () => {
  it('两张披露表都走 HTML 组件', () => {
    expect(isN2HtmlSheet(N2_SHEET_DISCLOSURE_LISTED)).toBe(true)
    expect(isN2HtmlSheet(N2_SHEET_DISCLOSURE_SOE)).toBe(true)
  })

  it('N2-n / N2 / 底稿目录 走 HTML', () => {
    for (const s of ['N2-1', 'N2-11', 'N2', N2_SHEET_INDEX]) {
      expect(isN2HtmlSheet(s), s).toBe(true)
    }
  })

  it('N2A 与未识别 sheet 走 OnlyOffice', () => {
    expect(isN2HtmlSheet('N2A')).toBe(false)
    expect(isN2HtmlSheet('GT_Custom')).toBe(false)
  })
})

// ── 自检替身：证明断言真的能抓住原缺陷（防守卫本身失效）────────────────────

describe('反向自检（原缺陷实现必须被抓出）', () => {
  /** 原实现：wp_code 正则前置 + 繁体國企 */
  function buggyNormalize(name: string): string {
    const m = name.match(/(N2A|N2-\d+|N2)/)
    if (m) return m[1]
    if (name.includes('附注') && (name.includes('上市') || name.includes('國企'))) {
      return name.includes('上市') ? N2_SHEET_DISCLOSURE_LISTED : N2_SHEET_DISCLOSURE_SOE
    }
    if (name.includes('底稿目录')) return N2_SHEET_INDEX
    return name
  }

  it('原实现对简体国企 sheet 不命中（这就是线上缺陷）', () => {
    expect(buggyNormalize(REAL_SOE)).not.toBe(N2_SHEET_DISCLOSURE_SOE)
    expect(normalizeN2SheetName(REAL_SOE)).toBe(N2_SHEET_DISCLOSURE_SOE)
  })

  it('原实现会被 wp_code 后缀抢占', () => {
    expect(buggyNormalize('附注披露信息（上市公司）N2-1')).toBe('N2-1')
    expect(normalizeN2SheetName('附注披露信息（上市公司）N2-1')).toBe(N2_SHEET_DISCLOSURE_LISTED)
  })
})
