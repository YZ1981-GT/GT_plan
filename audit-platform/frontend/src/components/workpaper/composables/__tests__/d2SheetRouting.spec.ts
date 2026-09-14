/**
 * D2 sheet 名 → 分发键契约（`normalizeD2SheetName`）
 *
 * 🔴 回归锁定（2026-07-30 Playwright 实测）：源模板披露 tab 名尾部带 wp_code
 * （`附注披露信息（国企）D2-1` / `附注披露信息(上市公司）D2-1`），旧实现先跑
 * `/D2(?:-\d+)?[A-Z]?$/` 正则 → 判成 `D2-1` → 渲染「应收账款审定表」，
 * 披露组件永远挂不上。`get_diagnostics` 与 vitest 都查不出，只有浏览器实测能发现。
 *
 * 平台级铁律：「国企」与「国有企业」两种源模板写法都必须认。
 */
import { describe, expect, it } from 'vitest'
import { normalizeD2SheetName } from '../d2Constants'

describe('normalizeD2SheetName — 披露 sheet 优先于 wp_code 后缀', () => {
  it.each([
    // 实测 workpaper_sheet_classification（wp_code=D2-1）中的 4 个披露 sheet 名
    ['附注披露信息（国企）D2-1', '附注国企'],
    ['附注披露信息(上市公司）D2-1', '附注上市'],
    ['附注披露信息(国企)', '附注国企'],
    ['附注披露信息(上市公司)', '附注上市'],
    // 平台级：「国有企业」写法（24 份源模板在用）
    ['附注披露信息（国有企业）', '附注国企'],
    ['附注披露信息（国有企业）D2-1', '附注国企'],
  ])('「%s」→ %s', (sheet, expected) => {
    expect(normalizeD2SheetName(sheet)).toBe(expected)
  })

  it('非披露 sheet 仍按 wp_code 后缀分发（不回归）', () => {
    expect(normalizeD2SheetName('审定表D2-1')).toBe('D2-1')
    expect(normalizeD2SheetName('明细表D2-2')).toBe('D2-2')
    expect(normalizeD2SheetName('坏账准备明细表D2-3')).toBe('D2-3')
    expect(normalizeD2SheetName('调整分录汇总表D2-4')).toBe('D2-4')
    expect(normalizeD2SheetName('应收账款实质性程序表D2A')).toBe('D2A')
    expect(normalizeD2SheetName('底稿目录')).toBe('目录')
    expect(normalizeD2SheetName('截止测试')).toBe('截止测试')
  })

  it('缺省与未知 sheet 的兜底不变', () => {
    expect(normalizeD2SheetName(undefined)).toBe('D2')
    expect(normalizeD2SheetName(null)).toBe('D2')
    expect(normalizeD2SheetName('')).toBe('D2')
    expect(normalizeD2SheetName('D2 应收账款')).toBe('D2')
    expect(normalizeD2SheetName('GT_Custom')).toBe('GT_Custom')
  })

  it('披露键落在 GtD2 已知 HTML sheet 集合内（否则会走 OnlyOffice fallback）', () => {
    // 与 GtD2AccountsReceivable.KNOWN_HTML_SHEETS 对齐的两个披露键
    expect(['附注上市', '附注国企']).toContain(normalizeD2SheetName('附注披露信息（国企）D2-1'))
    expect(['附注上市', '附注国企']).toContain(normalizeD2SheetName('附注披露信息(上市公司）D2-1'))
  })
})
