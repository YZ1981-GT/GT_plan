/**
 * customFormulaWiring.spec.ts — 自定义底稿公式可用性守卫（Wave 4 Task 15）
 *
 * spec: custom-workpaper-dual-mode-formula-and-batch
 *
 * 覆盖 Property：
 *   - Property 9  选址 label 带语义（非纯 cell 引用）；空投影给 el-empty
 *   - Property 15 清单面板读 `items` 键 / 类型标签复用单一真源 / 路径走 apiPaths
 *   - Property 8  公式求值双写 xlsx + 投影（后端源码级，含反向自检）
 *   - Property 21 删公式清格（custom 门控 + 非 custom 零改动）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import fs from 'node:fs'
import path from 'node:path'

import { buildFormulaCellOptions, normalizeCellRef } from '../customWpCellEdit'

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'app', 'routers', 'wp_formula.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵均需存在）')
}
const ROOT = repoRoot()

function readFileAt(rel: string): string {
  const p = path.join(ROOT, rel)
  if (!fs.existsSync(p)) throw new Error(`守卫判据文件缺失: ${rel}`)
  return fs.readFileSync(p, 'utf-8')
}

function stripComments(src: string): string {
  let out = ''
  let i = 0
  let mode: 'code' | 'line' | 'block' | 'sq' | 'dq' | 'tpl' = 'code'
  while (i < src.length) {
    const ch = src[i]
    const next = src[i + 1]
    if (mode === 'code') {
      if (ch === '/' && next === '/') { mode = 'line'; i += 2; continue }
      if (ch === '/' && next === '*') { mode = 'block'; i += 2; continue }
      if (ch === "'") { mode = 'sq'; out += ch; i++; continue }
      if (ch === '"') { mode = 'dq'; out += ch; i++; continue }
      if (ch === '`') { mode = 'tpl'; out += ch; i++; continue }
      out += ch; i++; continue
    }
    if (mode === 'line') { if (ch === '\n') { mode = 'code'; out += ch }; i++; continue }
    if (mode === 'block') { if (ch === '*' && next === '/') { mode = 'code'; i += 2 } else i++; continue }
    out += ch
    if (ch === '\\') { out += next ?? ''; i += 2; continue }
    if ((mode === 'sq' && ch === "'") || (mode === 'dq' && ch === '"') || (mode === 'tpl' && ch === '`')) mode = 'code'
    i++
  }
  return out
}

/** 剥 Python 注释（`#` 到行尾 + docstring），跳过字符串内 */
function stripPyComments(src: string): string {
  const lines = src.split(/\r?\n/)
  const out: string[] = []
  let inDoc = false
  let docQ = ''
  for (const line of lines) {
    let s = line
    if (inDoc) {
      const idx = s.indexOf(docQ)
      if (idx >= 0) { inDoc = false; s = s.slice(idx + 3) } else { out.push(''); continue }
    }
    for (const q of ['"""', "'''"]) {
      const start = s.indexOf(q)
      if (start >= 0) {
        const end = s.indexOf(q, start + 3)
        if (end < 0) { inDoc = true; docQ = q; s = s.slice(0, start); break }
        s = s.slice(0, start) + ' ' + s.slice(end + 3)
      }
    }
    let res = ''
    let q: string | null = null
    for (let i = 0; i < s.length; i++) {
      const c = s[i]
      if (q) { res += c; if (c === q && s[i - 1] !== '\\') q = null; continue }
      if (c === '"' || c === "'") { q = c; res += c; continue }
      if (c === '#') break
      res += c
    }
    out.push(res)
  }
  return out.join('\n')
}

function scriptBlock(sfc: string): string {
  const m = sfc.match(/<script[^>]*>([\s\S]*?)<\/script>/)
  return m ? m[1] : ''
}
function templateBlock(sfc: string): string {
  const m = sfc.match(/<template>([\s\S]*)<\/template>/)
  return m ? m[1] : ''
}

/** 取 python 函数体：`def name(` → 到下一个同级或更浅缩进的 `def`/`@router` 为止 */
function pyFnBody(src: string, name: string): string {
  const re = new RegExp(`^([ \\t]*)(?:async +)?def +${name}\\s*\\(`, 'm')
  const m = src.match(re)
  if (!m || m.index === undefined) return ''
  // 🔴 缩进用 `[ \t]*` 不能用 `\s*` —— re.M 下 `\s` 含换行，
  //    会从前面的空行开始匹配，indent 被算成一串换行的长度（平台既有铁律）
  const indent = m[1].length
  const lines = src.slice(m.index).split('\n')
  const body: string[] = [lines[0]]
  for (let i = 1; i < lines.length; i++) {
    const ln = lines[i]
    if (ln.trim() === '') { body.push(ln); continue }
    const ind = ln.length - ln.trimStart().length
    if (ind <= indent && /^\s*(@|(async +)?def |class )/.test(ln)) break
    body.push(ln)
  }
  return body.join('\n')
}

const EDITOR_REL = 'audit-platform/frontend/src/components/workpaper/GtCustomWpEditor.vue'
const WPF_REL = 'backend/app/routers/wp_formula.py'
const APIPATHS_REL = 'audit-platform/frontend/src/services/apiPaths/workpaper.ts'

// ════════════════════════════════════════════════════════════════════════════
describe('守卫自检', () => {
  it('pyFnBody 按缩进截取且不越界到下一个 def', () => {
    const src = [
      'async def save_formula(a):',
      '    x = 1',
      '    return x',
      '',
      'async def delete_formula(b):',
      '    LEAK_MARKER = 2',
    ].join('\n')
    const body = pyFnBody(src, 'save_formula')
    expect(body).toContain('x = 1')
    expect(body).not.toContain('LEAK_MARKER')
  })

  it('stripPyComments 剥掉 # 与 docstring 但保留字符串内 #', () => {
    const s = 'def f():\n    """doc FORBIDDEN"""\n    a = 1  # FORBIDDEN\n    s = "keep#me"'
    const c = stripPyComments(s)
    expect(c).not.toContain('FORBIDDEN')
    expect(c).toContain('keep#me')
  })

  it('readFileAt 缺文件抛错', () => {
    expect(() => readFileAt('backend/__nope__.py')).toThrow(/判据文件缺失/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 9: 选址 label 带语义', () => {
  it('同行首列文本作为语义标签（不是纯 A1/B2）', () => {
    const cells = {
      A5: { v: '货币资金', r: 5, c: 1 },
      B5: { v: 1234.5, r: 5, c: 2 },
      A6: { v: '应收账款', r: 6, c: 1 },
      B6: { v: 99, r: 6, c: 2 },
    }
    const opts = buildFormulaCellOptions(cells)
    const b5 = opts.find((o) => o.cell === 'B5')
    expect(b5).toBeTruthy()
    expect(b5!.label).toContain('货币资金')
    expect(b5!.label).toContain('B5')
    const b6 = opts.find((o) => o.cell === 'B6')
    expect(b6!.label).toContain('应收账款')
  })

  it('无行标签时回退同列首行（表头）', () => {
    const cells = {
      B1: { v: '期末余额', r: 1, c: 2 },
      B7: { v: 500, r: 7, c: 2 },
    }
    const opts = buildFormulaCellOptions(cells)
    const b7 = opts.find((o) => o.cell === 'B7')
    expect(b7!.label).toContain('期末余额')
  })

  it('🔴 纯数字文本不当语义标签（金额当标签更难定位）', () => {
    const cells = {
      A3: { v: '1,234.00', r: 3, c: 1 },
      B3: { v: 9, r: 3, c: 2 },
    }
    const opts = buildFormulaCellOptions(cells)
    const b3 = opts.find((o) => o.cell === 'B3')
    // 没有可用语义标签 → 退回纯引用，而不是拿金额当标签
    expect(b3!.label).toBe('B3')
  })

  it('本格自带 label/name 优先', () => {
    const cells = { C9: { label: '存货合计', v: 1, r: 9, c: 3 } }
    const opts = buildFormulaCellOptions(cells)
    expect(opts.find((o) => o.cell === 'C9')!.label).toBe('存货合计')
  })

  it('空/非法输入返回空数组（不抛错）', () => {
    expect(buildFormulaCellOptions(undefined)).toEqual([])
    expect(buildFormulaCellOptions(null)).toEqual([])
    expect(buildFormulaCellOptions({})).toEqual([])
  })

  it('PBT: 每个选项的 cell 都是归一化引用且 label 非空', () => {
    fc.assert(
      fc.property(
        fc.dictionary(
          fc.tuple(
            fc.integer({ min: 1, max: 20 }),
            fc.integer({ min: 1, max: 12 }),
          ).map(([r, c]) => `${String.fromCharCode(64 + c)}${r}`),
          fc.oneof(fc.string({ maxLength: 8 }), fc.integer()),
          { maxKeys: 12 },
        ),
        (cells) => {
          const opts = buildFormulaCellOptions(cells)
          for (const o of opts) {
            expect(normalizeCellRef(o.cell)).toBe(o.cell)
            expect(o.label.length).toBeGreaterThan(0)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('空投影时模板渲染 el-empty 且带可操作提示', () => {
    const tpl = templateBlock(readFileAt(EDITOR_REL))
    expect(tpl).toMatch(/<el-empty(?=[\s/>])/)
    expect(tpl).toMatch(/请先在网格中录入或切换在线编辑/)
    const script = stripComments(scriptBlock(readFileAt(EDITOR_REL)))
    expect(script).toMatch(/hasPickableCells/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 15: 公式清单面板', () => {
  const sfc = readFileAt(EDITOR_REL)
  const script = stripComments(scriptBlock(sfc))
  const tpl = templateBlock(sfc)

  it('🔴 读 items 键，不得把响应当 formulas 键读（后端返回的是 items）', () => {
    expect(script).toMatch(/\bitems\b/)
    // 🔴 判据必须只盯「响应体取键」，不能笼统禁 `.formulas` ——
    //    `apiPaths.workpapers.formulas(...)` 是**合法**的路径访问器，
    //    笼统禁会把正确写法打红（本守卫首版即如此）。
    expect(script).not.toMatch(/\bres\s*\??\.\s*formulas\b/)
    expect(script).not.toMatch(/\bdata\s*\??\.\s*formulas\b/)
    expect(script).not.toMatch(/formulaList\.value\s*=\s*[^\n]*\.formulas\b/)
  })

  it('🔴 类型标签 import 自 formulaEngineInventory（禁第二份标签表）', () => {
    expect(script).toMatch(/FORMULA_TYPE_LABEL/)
    expect(script).toMatch(/from\s+['"][^'"]*formulaEngineInventory['"]/)
    // 组件内不得自建标签映射（如 { auto_calc: '自动运算' }）
    expect(script).not.toMatch(/auto_calc\s*:\s*['"]/)
  })

  it('端点走 apiPaths，不在组件内硬编码模板字符串', () => {
    expect(script).toMatch(/apiPaths\.workpapers\.formulas\(/)
    expect(script).toMatch(/apiPaths\.workpapers\.formulaDetail\(/)
    // 组件内不得出现硬编码的 /api/workpapers/.../formulas 模板串
    expect(script).not.toMatch(/`\/api\/workpapers\/\$\{[^}]*\}\/formulas`/)
  })

  it('apiPaths 已登记四个自定义底稿端点', () => {
    const ap = readFileAt(APIPATHS_REL)
    for (const k of ['customCells', 'customRefreshProjection', 'formulas:', 'formulaDetail']) {
      expect(ap, `apiPaths 缺 ${k}`).toContain(k)
    }
  })

  it('清单为空显示 el-empty 而非空表格', () => {
    expect(tpl).toMatch(/formulaList\.length\s*===\s*0/)
    expect(tpl).toMatch(/<el-empty(?=[\s/>])/)
  })

  it('清单每条含目标格/表达式/类型/最后计算/删除', () => {
    expect(tpl).toMatch(/target_cell/)
    expect(tpl).toMatch(/expression/)
    expect(tpl).toMatch(/formulaTypeLabel\(/)
    expect(tpl).toMatch(/last_computed_at/)
    expect(tpl).toMatch(/removeFormula\(/)
  })

  it('点击定位到目标格（R6.3）且网格接收 highlight-cell', () => {
    expect(script).toMatch(/function\s+locateFormulaCell/)
    expect(script).toMatch(/highlightCell/)
    expect(tpl).toMatch(/:highlight-cell=/)
  })

  it('删除失败/清格失败如实提示（禁静默成功）', () => {
    expect(script).toMatch(/cell_clear_failed/)
    expect(script).toMatch(/ElMessage\.warning/)
    expect(script).toMatch(/handleApiError/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 8: 公式求值双写 xlsx + 投影', () => {
  const raw = readFileAt(WPF_REL)
  const src = stripPyComments(raw)
  const body = pyFnBody(src, 'save_formula')

  it('save_formula 里有 custom 门控（条件形态，非仅标识符出现）', () => {
    expect(body, '未截到 save_formula 函数体').toBeTruthy()
    // 🔴 断言条件形态：只查标识符会被 `if False:` 变异骗过
    expect(body).toMatch(/if\s+_is_custom_wp\s*:/)
  })

  it('🔴 custom 分支写 xlsx 且顺序在重投影之前（xlsx 是权威）', () => {
    // 🔴 必须比**调用点**位置，不能用裸 indexOf ——
    //    `from ... import (refresh_custom_projection, write_cells_to_xlsx,)`
    //    的 import 清单按字母序把 refresh 排在前面，裸 indexOf 会命中 import 行
    //    从而误判「顺序反了」（本守卫首版即如此假红）。
    const callPos = (name: string) => body.search(new RegExp(`${name}\\s*\\(`))
    const xi = callPos('write_cells_to_xlsx')
    const ri = callPos('refresh_custom_projection')
    expect(xi, 'save_formula 应调 write_cells_to_xlsx').toBeGreaterThan(0)
    expect(ri, 'save_formula 应调 refresh_custom_projection').toBeGreaterThan(0)
    expect(xi, 'xlsx 必须先于投影（顺序反了会让投影领先权威）').toBeLessThan(ri)
  })

  it('🔴 xlsx 写失败让整个保存失败（不留「只有投影有值」的分叉态）', () => {
    // write_cells_to_xlsx 的 except 分支里必须 raise
    const i = body.indexOf('write_cells_to_xlsx')
    const after = body.slice(i, i + 1200)
    expect(after).toMatch(/except\s+Exception/)
    expect(after).toMatch(/raise\s+HTTPException/)
    expect(after).toMatch(/status_code=500/)
  })

  it('🔴 反向自检: 非 custom 分支仍走 write_cell_to_parsed_data（零回归）', () => {
    expect(body).toMatch(/else\s*:/)
    expect(body).toMatch(/write_cell_to_parsed_data\(/)
  })

  it('🔴 反向自检: 「只写投影不写 xlsx」的替身实现必须被本判据打红', () => {
    const fake = [
      'async def save_formula(a):',
      '    if _is_custom_wp:',
      '        write_cell_to_parsed_data(wp, sheet_name=s, cell_ref=c, value=v)',
      '    return 1',
    ].join('\n')
    const fb = pyFnBody(fake, 'save_formula')
    // 替身里没有 write_cells_to_xlsx ⇒ 上面那条「写 xlsx」断言会失败
    expect(fb.indexOf('write_cells_to_xlsx')).toBe(-1)
  })

  it('resolve_is_custom 传三参（少传会 TypeError 被 except 吞成死代码）', () => {
    for (const m of src.matchAll(/resolve_is_custom\(([^)]*)\)/g)) {
      const args = m[1].split(',').map((s) => s.trim()).filter(Boolean)
      expect(args, `实参应 3 个，实为 ${args.length}`).toHaveLength(3)
    }
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 21: 删公式清格', () => {
  const raw = readFileAt(WPF_REL)
  const src = stripPyComments(raw)
  const body = pyFnBody(src, 'delete_formula')

  it('delete_formula 有 custom 门控（条件形态）', () => {
    expect(body, '未截到 delete_formula 函数体').toBeTruthy()
    expect(body).toMatch(/if\s+await\s+resolve_is_custom\(/)
  })

  it('🔴 清格用 None 写 xlsx 并刷投影（双方都清）', () => {
    expect(body).toMatch(/write_cells_to_xlsx\([^)]*\{[^}]*:\s*None\s*\}/s)
    expect(body).toMatch(/refresh_custom_projection\(/)
  })

  it('🔴 清格失败不让删除整体失败，且响应带 cell_clear_failed', () => {
    expect(body).toMatch(/cell_clear_failed/)
    const i = body.indexOf('cell_clear_failed')
    const around = body.slice(Math.max(0, i - 500), i + 200)
    expect(around).toMatch(/except\s+Exception/)
    // 清格失败路径不得 raise
    expect(around).not.toMatch(/raise\s+HTTPException/)
  })

  it('🔴 反向自检: 非 custom 底稿的 delete 路径无 xlsx 写入', () => {
    // xlsx 写入必须在 custom 门控之后
    const gi = body.search(/if\s+await\s+resolve_is_custom\(/)
    const xi = body.indexOf('write_cells_to_xlsx')
    expect(gi).toBeGreaterThan(0)
    expect(xi).toBeGreaterThan(gi)
  })

  it('删除前留存 target_cell（delete 后 ORM 字段不可靠）', () => {
    expect(body).toMatch(/_target_cell\s*=\s*existing\.target_cell/)
  })
})
