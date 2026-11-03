/**
 * spec excel-style-table-editing design §4：显示格式与文本解析。
 */
import { describe, expect, it } from 'vitest'
import fc from 'fast-check'
import {
  buildClipboardPayload, formatDateDisplay, formatNumberDisplay, formatSelectDisplay, formatTextDisplay,
  parseClipboardMatrix, parseDateLoose, parseDateText, parseHtmlMatrix, parseLooseNumber, parseNumberText,
  parseSelectText, parseToggleText, parseTsv, stripDecorations,
} from '../cellValue'

describe('数字显示', () => {
  it('有 precision 按位数并加千分位', () => {
    expect(formatNumberDisplay(1234567.5, 2)).toBe('1,234,567.50')
    expect(formatNumberDisplay(0, 2)).toBe('0.00')
    expect(formatNumberDisplay(-1234.5, 2)).toBe('-1,234.50')
    expect(formatNumberDisplay(0.0525, 4)).toBe('0.0525')
  })
  it('无 precision：按值本身小数位；4 位整数（年度 / 笔数）不加千分位，≥1 万加', () => {
    expect(formatNumberDisplay(2025)).toBe('2025')
    expect(formatNumberDisplay(9999)).toBe('9999')
    expect(formatNumberDisplay(100000000)).toBe('100,000,000')
    expect(formatNumberDisplay(1234.56)).toBe('1,234.56')
    expect(formatNumberDisplay(12.5)).toBe('12.5')
    expect(formatNumberDisplay(0.1 + 0.2)).toBe('0.3')
  })
  it('空值显示空白，非数字原样', () => {
    expect(formatNumberDisplay(null)).toBe('')
    expect(formatNumberDisplay(undefined, 2)).toBe('')
    expect(formatNumberDisplay('')).toBe('')
    expect(formatNumberDisplay('abc')).toBe('abc')
  })
})

describe('数字解析', () => {
  it('千分位 / 括号负数 / 全角 / 货币符号 / 百分号（不换算）', () => {
    expect(parseNumberText('1,234.50')).toEqual({ ok: true, value: 1234.5 })
    expect(parseNumberText('(1,000)')).toEqual({ ok: true, value: -1000 })
    expect(parseNumberText('１２３')).toEqual({ ok: true, value: 123 })
    expect(parseNumberText('¥88')).toEqual({ ok: true, value: 88 })
    expect(parseNumberText('5.25%')).toEqual({ ok: true, value: 5.25 })
    expect(parseNumberText('−3')).toEqual({ ok: true, value: -3 })
  })
  it('空 / 横线视为 null，非数字失败', () => {
    expect(parseNumberText('')).toEqual({ ok: true, value: null })
    expect(parseNumberText('—')).toEqual({ ok: true, value: null })
    expect(parseNumberText('-')).toEqual({ ok: true, value: null })
    expect(parseNumberText('12a').ok).toBe(false)
  })
  it('precision 舍入、min / max 夹紧', () => {
    expect(parseNumberText('1.005', { precision: 2 })).toEqual({ ok: true, value: 1.01 })
    expect(parseNumberText('150', { max: 100 })).toEqual({ ok: true, value: 100 })
    expect(parseNumberText('-5', { min: 0 })).toEqual({ ok: true, value: 0 })
  })
  it('属性：两位小数金额 显示 → 解析 往返不变', () => {
    fc.assert(fc.property(fc.integer({ min: -1e12, max: 1e12 }), (cents) => {
      const v = cents / 100
      const r = parseNumberText(formatNumberDisplay(v, 2), { precision: 2 })
      return r.ok && r.value === v
    }), { numRuns: 30 })
  })
  it('从显示文本取数（选区统计）', () => {
    expect(parseLooseNumber('1,234.50📊')).toBe(1234.5)
    expect(parseLooseNumber('(200)')).toBe(-200)
    expect(parseLooseNumber('合计')).toBeNull()
  })
})

describe('文本 / 下拉 / 勾选', () => {
  it('密码显示圆点，空值空白', () => {
    expect(formatTextDisplay('abc', 'password')).toBe('•••')
    expect(formatTextDisplay(null)).toBe('')
  })
  const options = [{ label: '是', value: 1 }, { label: '否', value: 0 }, { label: '不适用', value: 'na' }]
  it('下拉显示名称；多选用顿号连接；找不到名称显示值', () => {
    expect(formatSelectDisplay(1, options)).toBe('是')
    expect(formatSelectDisplay([1, 'na'], options, true)).toBe('是、不适用')
    expect(formatSelectDisplay('自定义', options)).toBe('自定义')
  })
  it('下拉解析：先名称后值；allow-create 接受原文；多选拆分', () => {
    expect(parseSelectText('否', options)).toEqual({ ok: true, value: 0 })
    expect(parseSelectText('na', options)).toEqual({ ok: true, value: 'na' })
    expect(parseSelectText('其他', options).ok).toBe(false)
    expect(parseSelectText('其他', options, { allowCreate: true })).toEqual({ ok: true, value: '其他' })
    expect(parseSelectText('是、否', options, { multiple: true })).toEqual({ ok: true, value: [1, 0] })
  })
  it('勾选：是/否、√/×、true/false，开关按 active-value', () => {
    expect(parseToggleText('是')).toEqual({ ok: true, value: true })
    expect(parseToggleText('×')).toEqual({ ok: true, value: false })
    expect(parseToggleText('', {})).toEqual({ ok: true, value: false })
    expect(parseToggleText('1', { activeValue: 'Y', inactiveValue: 'N' })).toEqual({ ok: true, value: 'Y' })
    expect(parseToggleText('也许').ok).toBe(false)
  })
})

describe('日期', () => {
  it('多种写法与 Excel 序列号', () => {
    const fmt = (d: Date | null) => (d ? `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}` : null)
    expect(fmt(parseDateLoose('2025-12-31'))).toBe('2025-12-31')
    expect(fmt(parseDateLoose('2025/1/5'))).toBe('2025-1-5')
    expect(fmt(parseDateLoose('2025年3月8日'))).toBe('2025-3-8')
    expect(fmt(parseDateLoose('20250308'))).toBe('2025-3-8')
    expect(fmt(parseDateLoose('45658'))).toBe('2025-1-1')
    expect(parseDateLoose('2025-02-30')).toBeNull()
  })
  it('按 value-format 输出；区间', () => {
    expect(parseDateText('2025/1/5', { valueFormat: 'YYYY-MM-DD' })).toEqual({ ok: true, value: '2025-01-05' })
    expect(parseDateText('2025-01 ', { type: 'month', valueFormat: 'YYYY-MM' })).toEqual({ ok: true, value: '2025-01' })
    expect(parseDateText('2025-01-01 至 2025-12-31', { type: 'daterange', valueFormat: 'YYYY-MM-DD' }))
      .toEqual({ ok: true, value: ['2025-01-01', '2025-12-31'] })
    expect(parseDateText('明天', {}).ok).toBe(false)
  })
  it('显示：已按 value-format 存的字符串原样；区间「至」', () => {
    expect(formatDateDisplay('2025-12-31')).toBe('2025-12-31')
    expect(formatDateDisplay(['2025-01-01', '2025-12-31'], { type: 'daterange' })).toBe('2025-01-01 至 2025-12-31')
    expect(formatDateDisplay(new Date(2025, 0, 5), { type: 'month' })).toBe('2025-01')
  })
})

describe('剪贴板', () => {
  it('制表符文本：保留中间空行、引号格里的换行与 Tab', () => {
    expect(parseTsv('a\tb\r\n\t\r\nc\td\r\n')).toEqual([['a', 'b'], ['', ''], ['c', 'd']])
    expect(parseTsv('"多\n行"\t"含""引号"""\nx')).toEqual([['多\n行', '含"引号"'], ['x']])
    expect(parseTsv('单个值')).toEqual([['单个值']])
    expect(parseTsv('a\n\nb')).toEqual([['a'], [''], ['b']])
  })
  it('HTML 表格按 rowspan / colspan 展开', () => {
    const html = '<table><tr><td rowspan="2">A</td><td colspan="2">B</td></tr><tr><td>C</td><td>D</td></tr></table>'
    expect(parseHtmlMatrix(html)).toEqual([['A', 'B', ''], ['', 'C', 'D']])
  })
  it('优先文本；只有 HTML 表格时用 HTML', () => {
    expect(parseClipboardMatrix('1\t2', '<table><tr><td>x</td></tr></table>')).toEqual([['1', '2']])
    expect(parseClipboardMatrix('', '<table><tr><td>x</td><td>y</td></tr></table>')).toEqual([['x', 'y']])
  })
  it('属性：矩阵 → 文本 → 矩阵 往返不变', () => {
    const cell = fc.string({ maxLength: 6 }).map((s) => s.replace(/\r/g, ''))
    fc.assert(fc.property(fc.array(fc.array(cell, { minLength: 2, maxLength: 4 }), { minLength: 1, maxLength: 4 }), (rows) => {
      const width = rows[0].length
      const m = rows.map((r) => Array.from({ length: width }, (_, i) => r[i] ?? ''))
      return JSON.stringify(parseTsv(buildClipboardPayload(m).text)) === JSON.stringify(m)
    }), { numRuns: 30 })
  })
  it('只读格复制去掉图标字符', () => {
    expect(stripDecorations('1,234.00 📊')).toBe('1,234.00')
    expect(stripDecorations('✏️ 人工')).toBe('人工')
  })
})
