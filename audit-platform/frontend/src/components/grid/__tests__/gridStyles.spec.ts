/**
 * spec excel-style-table-editing：gt-grid.css 的层叠关系（浏览器实测抓到：区域外沿的宽度规则优先级低于
 * `border: 0` 简写，选区边框从来没画出来）。jsdom 不算伪元素样式，这里按选择器优先级核对。
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const CSS = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../styles/gt-grid.css'), 'utf-8')

type Spec = [number, number, number]

/** 去掉成对括号包住的一段（:where(...) 优先级为 0）。 */
function stripWhere(sel: string): string {
  let out = sel
  for (;;) {
    const i = out.indexOf(':where(')
    if (i < 0) return out
    let depth = 0
    let j = i + ':where'.length
    for (; j < out.length; j++) {
      if (out[j] === '(') depth++
      else if (out[j] === ')' && --depth === 0) break
    }
    out = out.slice(0, i) + out.slice(j + 1)
  }
}

export function specificity(selector: string): Spec {
  let s = stripWhere(selector).replace(/:(not|is)\(([^()]*)\)/g, ' $2')
  s = s.replace(/\[[^\]]*\]/g, () => ' [a] ')
  const a = (s.match(/#[\w-]+/g) || []).length
  const pseudoEl = (s.match(/::[\w-]+/g) || []).length
  s = s.replace(/::[\w-]+/g, ' ')
  const b = (s.match(/\.[\w-]+|\[a\]|:[\w-]+/g) || []).length
  const types = s.split(/[\s>+~]+/).filter((part) => /^[a-zA-Z]/.test(part)).length
  return [a, b, types + pseudoEl]
}

const cmp = (x: Spec, y: Spec) => (x[0] - y[0]) || (x[1] - y[1]) || (x[2] - y[2])

/** 按顶层逗号拆选择器列表（:where(a, b) 里的逗号不拆）。 */
function splitSelectors(list: string): string[] {
  const out: string[] = []
  let depth = 0
  let cur = ''
  for (const ch of list) {
    if (ch === '(') depth++
    else if (ch === ')') depth--
    if (ch === ',' && depth === 0) { out.push(cur); cur = ''; continue }
    cur += ch
  }
  out.push(cur)
  return out.map((x) => x.trim()).filter(Boolean)
}

function rules(css: string): Array<{ selectors: string[]; body: string; index: number }> {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, '')
  const out: Array<{ selectors: string[]; body: string; index: number }> = []
  const re = /([^{}]+)\{([^{}]*)\}/g
  let m: RegExpExecArray | null
  while ((m = re.exec(clean))) {
    out.push({ selectors: splitSelectors(m[1]), body: m[2], index: m.index })
  }
  return out
}

describe('gt-grid.css 层叠', () => {
  it('优先级计算本身（:where 记 0、属性 / 伪类记 b、类型 / 伪元素记 c）', () => {
    expect(specificity("[data-gt-grid-root] td[data-gt-sel]::after")).toEqual([0, 2, 2])
    expect(specificity("[data-gt-grid-root] [data-gt-sel~='t']::after")).toEqual([0, 2, 1])
    expect(specificity(':where(table.gt-grid-raw) :where(td, th)')).toEqual([0, 0, 0])
    expect(specificity('[data-gt-grid-root]:not([data-gt-grid-focused]) td[data-gt-active]')).toEqual([0, 3, 1])
  })

  it('选区 / 复制框外沿的宽度规则不低于 `border: 0` 简写、且写在它后面（否则边框画不出来）', () => {
    const all = rules(CSS)
    const base = all.find((r) => /\bborder:\s*0\b/.test(r.body) && r.selectors.some((s) => s.includes('[data-gt-sel]')))
    expect(base, '找不到选区边框的 border 简写规则').toBeTruthy()
    const baseSpec = base!.selectors.map(specificity).sort(cmp).at(-1)!
    const edges = all.filter((r) => /border-(top|bottom|left|right)-width/.test(r.body)
      && r.selectors.some((s) => /data-gt-(sel|copy)~=/.test(s)))
    expect(edges.length).toBe(8)
    for (const r of edges) {
      expect(r.index, r.selectors.join(', ')).toBeGreaterThan(base!.index)
      for (const s of r.selectors) expect(cmp(specificity(s), baseSpec), s).toBeGreaterThanOrEqual(0)
    }
  })

  it('原生表格的定位规则零优先级（页面自己写的 position，如 sticky 首列，一律以页面为准）', () => {
    const pos = rules(CSS).filter((r) => /position:\s*relative/.test(r.body) && r.selectors.some((s) => s.includes('gt-grid-raw')))
    expect(pos.length).toBeGreaterThan(0)
    for (const r of pos) for (const s of r.selectors) expect(specificity(s), s).toEqual([0, 0, 0])
  })
})
