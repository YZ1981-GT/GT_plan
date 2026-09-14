/**
 * N4 / N5 sheet 分发守卫（共享工厂 `shared/cycleSheetRouting.ts`）
 *
 * 锁死两类**实测过的**静默失真（vitest 与 `get_diagnostics` 都查不出，只有浏览器能发现）：
 *
 * P1 **披露判定必须前置于 wp_code 正则**。平台实测（D2）披露 tab 名可能尾部带 wp_code
 *    （`附注披露信息（国企）D2-1`），先跑 `/N5-[1-8]/` 会把披露判成明细表 →
 *    **披露组件永远挂不上**。
 * P2 **国企写法不唯一**：`国企` / `国有企业` / 繁体 `國企` 都要认；
 *    🔴 N5 国企 tab 名还**缺右括号**（`附注披露信息（国企`），源模板如此。
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`
 */
import { describe, expect, it } from 'vitest'
import {
  N4_SHEET_DISCLOSURE_LISTED,
  N4_SHEET_DISCLOSURE_SOE,
  N4_SHEET_INDEX,
  isN4HtmlSheet,
  normalizeN4SheetName,
} from '../n4SheetRouting'
import {
  N5_SHEET_DISCLOSURE_LISTED,
  N5_SHEET_DISCLOSURE_SOE,
  isN5HtmlSheet,
  normalizeN5SheetName,
} from '../n5SheetRouting'
import { N5_DISCLOSURE_SHEET_NAME } from '../n5NoteSectionMap'
import { N4_DISCLOSURE_SHEET_NAME } from '../n4NoteSectionMap'

describe('N4 sheet 分发', () => {
  it('P1 真实披露 tab 名命中（DB 实测值）', () => {
    expect(normalizeN4SheetName(N4_DISCLOSURE_SHEET_NAME.listed)).toBe(N4_SHEET_DISCLOSURE_LISTED)
    expect(normalizeN4SheetName(N4_DISCLOSURE_SHEET_NAME.soe)).toBe(N4_SHEET_DISCLOSURE_SOE)
  })

  it('P1 披露 tab 名尾部带 wp_code 时不被明细表正则抢占', () => {
    expect(normalizeN4SheetName('附注披露信息（国企）N4-2')).toBe(N4_SHEET_DISCLOSURE_SOE)
    expect(normalizeN4SheetName('附注披露信息（上市公司）N4-1')).toBe(N4_SHEET_DISCLOSURE_LISTED)
  })

  it.each([
    '附注披露信息（国企）',
    '附注披露信息(国企)',
    '附注披露信息（国有企业）',
    '附注披露信息（國企）',
  ])('P2 国企多种写法都认：%s', (name) => {
    expect(normalizeN4SheetName(name)).toBe(N4_SHEET_DISCLOSURE_SOE)
  })

  it.each([
    ['税金及附加审定表N4-1', 'N4-1'],
    ['税金及附加明细表N4-2', 'N4-2'],
    ['调整分录N4-3', 'N4-3'],
    ['税金及附加审计程序表N4A', 'N4A'],
  ])('普通 sheet 仍按 wp_code 分发：%s', (name, expected) => {
    expect(normalizeN4SheetName(name)).toBe(expected)
  })

  it('底稿目录 / 回退 wpCode / 未识别原样返回', () => {
    expect(normalizeN4SheetName('底稿目录')).toBe(N4_SHEET_INDEX)
    expect(normalizeN4SheetName('', 'N4')).toBe('N4')
    expect(normalizeN4SheetName('GT_Custom')).toBe('GT_Custom')
  })

  it('HTML sheet 判定：披露 / N4-n / 目录 走 HTML；N4A / O2A 走 OO', () => {
    for (const s of [N4_SHEET_DISCLOSURE_LISTED, N4_SHEET_DISCLOSURE_SOE, 'N4-1', 'N4', N4_SHEET_INDEX]) {
      expect(isN4HtmlSheet(s), s).toBe(true)
    }
    expect(isN4HtmlSheet('N4A')).toBe(false)
    expect(isN4HtmlSheet('O2A')).toBe(false)
    expect(isN4HtmlSheet('GT_Custom')).toBe(false)
  })
})

describe('N5 sheet 分发', () => {
  it('🔴 P2 国企 tab 名缺右括号仍命中（源模板如此）', () => {
    expect(N5_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企')
    expect(normalizeN5SheetName(N5_DISCLOSURE_SHEET_NAME.soe)).toBe(N5_SHEET_DISCLOSURE_SOE)
  })

  it('P1 上市披露命中', () => {
    expect(normalizeN5SheetName(N5_DISCLOSURE_SHEET_NAME.listed)).toBe(N5_SHEET_DISCLOSURE_LISTED)
  })

  it('P1 披露 tab 名尾部带 wp_code 时不被明细表正则抢占', () => {
    expect(normalizeN5SheetName('附注披露信息（国企 N5-2')).toBe(N5_SHEET_DISCLOSURE_SOE)
    expect(normalizeN5SheetName('附注披露信息（上市公司）N5-6-1')).toBe(N5_SHEET_DISCLOSURE_LISTED)
  })

  it.each([
    ['所得税费用审定表N5-1', 'N5-1'],
    ['纳税调整明细表N5-5', 'N5-5'],
    ['加计扣除研发费用N5-6-1', 'N5-6-1'],
    ['高新技术企业认定N5-6-2', 'N5-6-2'],
    ['所得税费用审计程序表N5A', 'N5A'],
    ['递延所得税程序表N3A', 'N3A'],
  ])('普通 sheet 仍按 wp_code 分发：%s', (name, expected) => {
    expect(normalizeN5SheetName(name)).toBe(expected)
  })

  it('HTML sheet 判定：披露 / N5-n(-n) / 目录 走 HTML；N5A / N3A 走 OO', () => {
    for (const s of [N5_SHEET_DISCLOSURE_LISTED, N5_SHEET_DISCLOSURE_SOE, 'N5-6-1', 'N5-8', 'N5']) {
      expect(isN5HtmlSheet(s), s).toBe(true)
    }
    expect(isN5HtmlSheet('N5A')).toBe(false)
    expect(isN5HtmlSheet('N3A')).toBe(false)
  })
})

// ── 自检替身：证明断言真的能抓住原缺陷（防守卫本身失效）────────────────────

describe('反向自检（宿主原实现必须被抓出）', () => {
  /** N5 宿主原实现：wp_code 正则前置 */
  function buggyN5(name: string): string {
    const m = name.match(/(N5A|N3A|N5-6-[12]|N5-[1-8]|N5)/)
    if (m) return m[1]
    if (name.includes('附注') && (name.includes('上市') || name.includes('国企'))) {
      return name.includes('上市') ? N5_SHEET_DISCLOSURE_LISTED : N5_SHEET_DISCLOSURE_SOE
    }
    return name
  }

  it('原实现会被 wp_code 后缀抢占', () => {
    expect(buggyN5('附注披露信息（上市公司）N5-1')).toBe('N5-1')
    expect(normalizeN5SheetName('附注披露信息（上市公司）N5-1')).toBe(N5_SHEET_DISCLOSURE_LISTED)
  })

  /** 假想的"只认全称国有企业"实现 —— 对真实 tab 名不命中 */
  function buggySoeToken(name: string): string {
    if (name.includes('附注') && name.includes('国有企业')) return N5_SHEET_DISCLOSURE_SOE
    return name
  }

  it('只认「国有企业」的实现对真实国企 tab 名不命中', () => {
    expect(buggySoeToken(N5_DISCLOSURE_SHEET_NAME.soe)).not.toBe(N5_SHEET_DISCLOSURE_SOE)
    expect(normalizeN5SheetName(N5_DISCLOSURE_SHEET_NAME.soe)).toBe(N5_SHEET_DISCLOSURE_SOE)
  })
})
