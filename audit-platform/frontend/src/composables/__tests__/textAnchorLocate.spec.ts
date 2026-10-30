/**
 * textAnchorLocate — 目录登记的文字锚点（spec wp-deeplink-locate-coverage-closure 需求 2.1 / 2.3）。
 * 各组件结论区标题的几种写法（卡片标题 span、section-title、表单项标签、带「四、」与冒号）都能认出；
 * 表格列名、隐藏页签里的同名标题不算；不唯一 / 没有返回 null，不猜。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { findTextAnchorElement, locateTextAnchor, normalizeAnchorText } from '../textAnchorLocate'
import { GT_LOCATE_HIGHLIGHT_CLASS } from '../useCellLocate'
import { CATALOG_TEXT_ANCHORS, catalogTextAnchor } from '@/generated/catalogTextAnchors'
import { locateSheetCode } from '../useRendererCellLocate'

function root(html: string): HTMLElement {
  const el = document.createElement('div')
  el.innerHTML = html
  document.body.appendChild(el)
  return el
}

afterEach(() => { document.body.innerHTML = '' })

describe('normalizeAnchorText', () => {
  it('去空白、序号与尾部冒号', () => {
    expect(normalizeAnchorText(' 四、审计结论： ')).toBe('审计结论')
    expect(normalizeAnchorText('审计 结论')).toBe('审计结论')
    expect(normalizeAnchorText('审计结论:')).toBe('审计结论')
    expect(normalizeAnchorText('审计结论及说明')).toBe('审计结论及说明')
  })

  it('各组件的序号写法都去掉（2、/ 2. / （三）/ (3) / IV.），带别的字的标题不算', () => {
    for (const s of ['2、审计结论', '2. 审计结论', '4.审计结论', '（三）审计结论', '(3) 审计结论', 'IV. 审计结论', '六、审计结论'])
      expect(normalizeAnchorText(s), s).toBe('审计结论')
    for (const s of ['总体审计结论', '审计结论确认', '分析结论（四、审计结论）', '2024年审计结论', '🤖 AI 生成审计结论'])
      expect(normalizeAnchorText(s), s).not.toBe('审计结论')
  })
})

describe('findTextAnchorElement', () => {
  it('卡片标题 span → 返回所在 el-card', () => {
    const r = root('<div class="el-card"><div class="el-card__header"><span>审计结论</span><button>AI</button></div></div>')
    expect(findTextAnchorElement(r, '审计结论')).toBe(r.querySelector('.el-card'))
  })

  it('section-title（不在卡片里）→ 返回标题本身；带序号与冒号也认', () => {
    const r = root('<div class="section-title">四、审计结论：</div><div class="note-section"><textarea></textarea></div>')
    expect(findTextAnchorElement(r, '审计结论')).toBe(r.querySelector('.section-title'))
  })

  it('表单项标签 → 返回所在 el-form-item', () => {
    const r = root('<div class="el-form-item"><label class="el-form-item__label">审计结论</label><div>…</div></div>')
    expect(findTextAnchorElement(r, '审计结论')).toBe(r.querySelector('.el-form-item'))
  })

  it('表格列名不算结论区（只有列名 ⇒ null；另有标题 ⇒ 取标题）', () => {
    const onlyTh = root('<table><thead><tr><th>审计结论</th></tr></thead></table>')
    expect(findTextAnchorElement(onlyTh, '审计结论')).toBeNull()
    const both = root('<table><tr><th>审计结论</th></tr></table><div class="section-title">审计结论</div>')
    expect(findTextAnchorElement(both, '审计结论')).toBe(both.querySelector('.section-title'))
  })

  it('隐藏页签（display:none / hidden / aria-hidden）里的同名标题不算', () => {
    const r = root(`
      <div style="display: none"><div class="el-card"><span>审计结论</span></div></div>
      <div hidden><span>审计结论</span></div>
      <div aria-hidden="true"><span>审计结论</span></div>
      <div class="el-card" id="visible"><span>审计结论</span></div>`)
    expect(findTextAnchorElement(r, '审计结论')).toBe(r.querySelector('#visible'))
  })

  it('可见的不止一处 ⇒ null（不猜）；没有 ⇒ null', () => {
    const two = root('<div class="el-card"><span>审计结论</span></div><div class="el-card"><span>审计结论</span></div>')
    expect(findTextAnchorElement(two, '审计结论')).toBeNull()
    const none = root('<div class="el-card"><span>审计说明</span></div>')
    expect(findTextAnchorElement(none, '审计结论')).toBeNull()
  })

  it('根元素本身在卡片里：不越出根元素，返回标题本身', () => {
    const outer = root('<div class="el-card" id="outer"><div id="r"><span id="t">审计结论</span></div></div>')
    const r = outer.querySelector('#r') as HTMLElement
    expect(findTextAnchorElement(r, '审计结论')).toBe(outer.querySelector('#t'))
  })
})

describe('locateTextAnchor', () => {
  it('命中即加高亮类；找不到返回 false', () => {
    const r = root('<div class="el-card" id="c"><span>审计结论</span></div>')
    expect(locateTextAnchor(r, '审计结论', 'k1')).toBe(true)
    expect(r.querySelector('#c')!.classList.contains(GT_LOCATE_HIGHLIGHT_CLASS)).toBe(true)
    expect(locateTextAnchor(r, '审计说明', 'k2')).toBe(false)
  })
})

describe('目录文字锚点对照（generated/catalogTextAnchors.ts）与渲染器接线', () => {
  it('按 sheet 编码 + A1 查（都去空白、不分大小写）；只登记结论格', () => {
    expect(Object.keys(CATALOG_TEXT_ANCHORS).length).toBeGreaterThanOrEqual(60)
    expect(catalogTextAnchor('E1-14', ' a50 ')).toBe('审计结论')
    expect(catalogTextAnchor(' e1-9 ', 'A26')).toBe('审计结论')
    expect(catalogTextAnchor('E1-14', 'I18')).toBeNull()
    expect(catalogTextAnchor(null, 'A50')).toBeNull()
    expect(catalogTextAnchor('E1-14', null)).toBeNull()
  })

  it('每张登记表的模板页签名都能按末尾编码对回登记编码（渲染配置对模板页签不给 sheet_code）', () => {
    const catalog = JSON.parse(readFileSync(resolve(__dirname, '../../../../../backend/data/acnr/global_catalog.json'), 'utf-8'))
    const byCode = new Map<string, string[]>()
    for (const s of catalog.sheets as Array<{ sheet_code?: string; sheet_name?: string; deprecated?: boolean }>) {
      if (!s.deprecated && s.sheet_code) byCode.set(s.sheet_code, [...(byCode.get(s.sheet_code) ?? []), s.sheet_name ?? ''])
    }
    const bad: string[] = []
    for (const code of Object.keys(CATALOG_TEXT_ANCHORS)) {
      const names = byCode.get(code) ?? []
      if (!names.length) bad.push(`${code}: 目录里没有这张表`)
      for (const name of names) if (locateSheetCode({ sheet_name: name }) !== code) bad.push(`${code}: ${name} → ${locateSheetCode({ sheet_name: name })}`)
    }
    expect(bad).toEqual([])
  })

  it('GtWpRenderer 把对照交给 useRendererCellLocate（第三级定位）', () => {
    const src = readFileSync(resolve(__dirname, '../../components/workpaper/GtWpRenderer.vue'), 'utf-8')
    expect(src).toContain("import { catalogTextAnchor } from '@/generated/catalogTextAnchors'")
    const start = src.indexOf('useRendererCellLocate({')
    expect(start).toBeGreaterThan(0)
    expect(src.slice(start, src.indexOf('})', start))).toMatch(/\btextAnchor:\s*catalogTextAnchor\b/)
  })
})
