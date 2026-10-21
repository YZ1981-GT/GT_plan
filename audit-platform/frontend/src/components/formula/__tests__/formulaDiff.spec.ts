import { describe, it, expect } from 'vitest'
import { escHtml, lcs, diffOld, diffNew, diffInline } from '../formulaDiff'

describe('escHtml', () => {
  it('转义 HTML 特殊字符', () => {
    expect(escHtml('<script>&</script>')).toBe('&lt;script&gt;&amp;&lt;/script&gt;')
  })
  it('普通文本不变', () => {
    expect(escHtml("TB('1001','期末余额')")).toBe("TB('1001','期末余额')")
  })
})

describe('lcs', () => {
  it('完全相同', () => {
    expect(lcs('abc', 'abc')).toBe('abc')
  })
  it('完全不同', () => {
    expect(lcs('abc', 'xyz')).toBe('')
  })
  it('部分相同', () => {
    expect(lcs('ABCDE', 'ACE')).toBe('ACE')
  })
  it('一方为空', () => {
    expect(lcs('', 'abc')).toBe('')
    expect(lcs('abc', '')).toBe('')
  })
  it('典型公式变更', () => {
    const old = "TB('1001','期末余额')"
    const cur = "TB('1001','期初余额')"
    const common = lcs(old, cur)
    // 期末 → 期初：公共子序列应包含两侧的公共部分
    expect(common).toContain("TB('1001','期")
    expect(common).toContain("余额')")
  })
})

describe('diffOld', () => {
  it('null old 返回空', () => {
    expect(diffOld(null, 'any')).toBe('')
  })
  it('相同返回纯文本（无标记）', () => {
    expect(diffOld('abc', 'abc')).toBe('abc')
    expect(diffOld('abc', 'abc')).not.toContain('gt-fh-del')
  })
  it('null cur 返回纯文本（全部原样）', () => {
    expect(diffOld('abc', null)).toBe('abc')
  })
  it('变化字符带 gt-fh-del 标记', () => {
    const result = diffOld('abc', 'axc')
    expect(result).toContain('gt-fh-del')
    expect(result).toContain('b') // 被删的 b
    expect(result).toContain('a') // 不变的 a
  })
})

describe('diffNew', () => {
  it('null cur 返回空', () => {
    expect(diffNew('any', null)).toBe('')
  })
  it('相同返回纯文本', () => {
    expect(diffNew('abc', 'abc')).toBe('abc')
    expect(diffNew('abc', 'abc')).not.toContain('gt-fh-add')
  })
  it('变化字符带 gt-fh-add 标记', () => {
    const result = diffNew('abc', 'axc')
    expect(result).toContain('gt-fh-add')
    expect(result).toContain('x') // 新增的 x
  })
})

describe('diffInline', () => {
  it('两者都为 null 返回空', () => {
    expect(diffInline(null, null)).toBe('')
  })
  it('只有新 → 全部标绿', () => {
    const result = diffInline(null, 'new')
    expect(result).toContain('gt-fh-add')
    expect(result).toContain('new')
  })
  it('只有旧 → 全部标红', () => {
    const result = diffInline('old', null)
    expect(result).toContain('gt-fh-del')
    expect(result).toContain('old')
  })
  it('典型公式变更同时有删除和新增', () => {
    const result = diffInline("TB('1001','期末余额')", "TB('1001','期初余额')")
    expect(result).toContain('gt-fh-del') // 末 被删
    expect(result).toContain('gt-fh-add') // 初 被加
    // 公共部分不带标记
    expect(result).toContain('TB(')
  })
  it('XSS 转义：输入含 HTML 不会产出未转义标签', () => {
    const result = diffInline('<script>', '<div>')
    // 用户输入的 < > 必须被转义，不能出现未转义的 <script> 或 <div>
    expect(result).not.toContain('<script>')
    expect(result).not.toContain('<div>')
    expect(result).toContain('&lt;')
  })
})
