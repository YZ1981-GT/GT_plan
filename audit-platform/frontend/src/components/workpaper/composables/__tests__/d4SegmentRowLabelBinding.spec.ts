/**
 * D4（4）分解信息表：行标签模板绑定字段必须存在于真源类型
 *
 * spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion (Task 30)
 *
 * ## 缺陷形态（2026-08-07 浏览器实测抓出）
 *
 * 两个 D4 披露 Tab 的（4）表把行标签写成 `{{ row.item }}`，而
 * `D4_SEGMENT_ROWS` 的 `D4SegmentRowDef` 字段名是 **`label`**。
 *
 * Vue 对**不存在的属性**渲染空串且不报错 ⇒ 9 个行标签
 * （主营业务 / 其中：在某一时点确认 / 在某一时段确认 / 其他业务 / 租赁收入 / 合  计 …）
 * **全部消失**，表格只剩空可扩行的提示文字。
 *
 * 🔴 四层验证全绿：`get_diagnostics`(Volar) 对 `v-for` 解构出的 row 不做属性存在性检查、
 * vitest 未挂载该表、Vite transform 200 —— 只有浏览器能发现。
 * 与 memory 已登记的「Vue 传不存在的 prop 静默失效」同族。
 *
 * ## 判据
 *
 * 从 `d4RevenueSegmentColumns.ts` **动态抽**出 `D4SegmentRowDef` 的合法字段名，
 * 再扫两个 SFC 里 `v-for="row in section4RowDefs"` 块内所有 `row.xxx` 引用，
 * 差集非空即打红。**不写死字段清单** —— 否则真源加字段时守卫会误判。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

import {
  D4_SEGMENT_INPUT_ROW_KEYS,
  D4_SEGMENT_ROWS,
  isSegmentRowReadonly,
} from '../d4RevenueSegmentColumns'

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    try {
      statSync(join(dir, 'audit-platform', 'frontend', 'package.json'))
      statSync(join(dir, 'backend', 'requirements.txt'))
      return dir
    } catch {
      dir = join(dir, '..')
    }
  }
  throw new Error('repoRoot 未找到')
}

const ROOT = repoRoot()
const D4_DIR = join(ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper', 'd4', 'core')
const SOURCE_TS = join(
  ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
  'composables', 'd4RevenueSegmentColumns.ts',
)

const SFCS = ['D4TabDisclosureSoe.vue', 'D4TabDisclosureListed.vue'] as const

/** 剥 HTML 注释与 JS 注释（说明文字里写着反例 `row.item`）*/
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/**
 * `section4RowDefs` 在 `useD4Disclosure` 里额外派生下发的字段
 * （不在 `D4SegmentRowDef` 接口上，但模板可合法引用）。
 *
 * 🔴 每一项都必须能在 composable 源码里找到派生赋值，否则又是「字段不存在 → 静默 falsy」。
 */
const DERIVED_FIELDS = ['readonly'] as const

/** 从真源 .ts 抽 `D4SegmentRowDef` 接口的字段名（不写死清单）*/
function legalFieldsFromSource(): Set<string> {
  const src = readFileSync(SOURCE_TS, 'utf-8')
  const m = /interface\s+D4SegmentRowDef\s*\{([\s\S]*?)\n\}/.exec(src)
  if (!m) throw new Error('未找到 D4SegmentRowDef 接口声明 ⇒ 守卫会空转')
  const body = stripComments(m[1])
  const fields = new Set<string>()
  for (const line of body.split('\n')) {
    const f = /^\s*(?:readonly\s+)?([A-Za-z_$][\w$]*)\s*\??\s*:/.exec(line)
    if (f) fields.add(f[1])
  }
  for (const d of DERIVED_FIELDS) fields.add(d)
  return fields
}

/** 截出 `v-for="row in section4RowDefs"` 所在 `<tr>` 块（按标签配对，禁固定窗口）*/
function segmentRowBlock(sfc: string): string {
  const anchor = sfc.indexOf('v-for="row in section4RowDefs"')
  if (anchor < 0) throw new Error('未找到 section4RowDefs 的 v-for ⇒ 守卫会空转')
  const trStart = sfc.lastIndexOf('<tr', anchor)
  const trEnd = sfc.indexOf('</tr>', anchor)
  if (trStart < 0 || trEnd < 0) throw new Error('<tr> 标签未配对')
  return sfc.slice(trStart, trEnd + 5)
}

describe('D4（4）表行标签绑定字段', () => {
  const legal = legalFieldsFromSource()

  it('真源接口字段抽取非空且含 label（防守卫空转）', () => {
    expect(legal.size).toBeGreaterThan(2)
    expect(legal.has('label')).toBe(true)
    expect(legal.has('kind')).toBe(true)
    // `item` 不是合法字段 —— 这正是缺陷的成因
    expect(legal.has('item')).toBe(false)
  })

  for (const name of SFCS) {
    it(`${name} 的（4）表只引用真源存在的字段`, () => {
      const raw = readFileSync(join(D4_DIR, name), 'utf-8')
      const block = stripComments(segmentRowBlock(raw))
      const used = new Set(
        Array.from(block.matchAll(/\brow\.([A-Za-z_$][\w$]*)/g)).map((m) => m[1]),
      )
      expect(used.size, `${name} 未抽到任何 row.xxx 引用 ⇒ 判据失效`).toBeGreaterThan(0)
      const illegal = Array.from(used).filter((f) => !legal.has(f))
      expect(
        illegal,
        `${name}（4）表引用了 D4SegmentRowDef 不存在的字段 ${illegal.join('/')}。` +
          'Vue 会静默渲染空串（行标签全部消失）且四层验证全绿。合法字段：' +
          Array.from(legal).join('/'),
      ).toEqual([])
    })

    it(`${name} 明确使用 row.label 渲染行标签`, () => {
      const raw = readFileSync(join(D4_DIR, name), 'utf-8')
      const block = stripComments(segmentRowBlock(raw))
      expect(block).toMatch(/\{\{\s*row\.label\s*\}\}/)
    })
  }

  it('派生字段必须在 useD4Disclosure 里真被赋值（防豁免退化成空转）', () => {
    const composable = readFileSync(
      join(
        ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
        'composables', 'useD4Disclosure.ts',
      ),
      'utf-8',
    )
    const body = stripComments(composable)
    const m = /const\s+section4RowDefs\s*=\s*computed\(([\s\S]*?)\n\s*\)/.exec(body)
    expect(m, '未找到 section4RowDefs 的 computed 声明 ⇒ 判据失效').not.toBeNull()
    for (const f of DERIVED_FIELDS) {
      expect(
        new RegExp(`\\b${f}\\s*:`).test(m![1]),
        `豁免字段 ${f} 在 section4RowDefs 里没有派生赋值 ⇒ 模板引用它会恒为 undefined`,
      ).toBe(true)
    }
  })

  it('只读派生：小计与合计行只读，明细与可扩行可录入', () => {
    for (const r of D4_SEGMENT_ROWS) {
      const expected = r.kind === 'subtotal' || r.kind === 'total'
      expect(isSegmentRowReadonly(r), `行 ${r.key}(${r.kind}) 只读判定错`).toBe(expected)
    }
    // 可录入行键与只读判定互斥（同一真源两种表达必须一致）
    for (const key of D4_SEGMENT_INPUT_ROW_KEYS) {
      const def = D4_SEGMENT_ROWS.find((r) => r.key === key)!
      expect(isSegmentRowReadonly(def), `可录入行 ${key} 被判成只读`).toBe(false)
    }
  })

  it('反向自检：替身模板里的错误字段能被判据识别', () => {
    const fake = '<tr v-for="row in section4RowDefs"><td>{{ row.item }}</td></tr>'
    const used = Array.from(fake.matchAll(/\brow\.([A-Za-z_$][\w$]*)/g)).map((m) => m[1])
    expect(used).toContain('item')
    expect(used.filter((f) => !legal.has(f))).toEqual(['item'])
  })

  it('反向自检：stripComments 剥掉注释里的反例', () => {
    const withComment = '<!-- {{ row.item }} -->\n<td>{{ row.label }}</td>'
    const s = stripComments(withComment)
    expect(s).not.toContain('row.item')
    expect(s).toContain('row.label')
  })

  it('9 个行标签在真源里都非空（expandable 行除外）', () => {
    expect(D4_SEGMENT_ROWS.length).toBe(9)
    for (const r of D4_SEGMENT_ROWS) {
      if (r.kind === 'expandable') {
        expect(r.label).toBe('')
      } else {
        expect(r.label.trim().length, `行 ${r.key} 的 label 为空`).toBeGreaterThan(0)
      }
    }
  })
})
