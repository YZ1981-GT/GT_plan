/**
 * customGridEditing.spec.ts — 自定义底稿可编辑网格守卫
 *
 * spec: custom-workpaper-dual-mode-formula-and-batch Wave 2 Task 8
 *
 * 覆盖 Property：
 *   - Property 4  单元格引用往返可逆（PBT）
 *   - Property 5  脏格补丁去重与超限
 *   - Property 14 公式格不可手工覆盖（数据驱动，非 CSS）
 *   - Property 23 前后端单元格解析一致（读后端源码交叉锁死）
 *   - 反向自检：`GtGridSheet.vue` 未被修改（防后续会话为省事去改共享只读件）
 *
 * 🔴 判据设计要点（memory 铁律）：
 *   - 标签/符号存在性断言带**边界**（`<Foo(?=[\s/>])`），否则被 `<FooREMOVED` 骗过
 *   - 读源码前先 `stripComments()`，并配「剥注释确实生效」自检
 *   - 断言「某校验存在」时判据是**条件表达式形态**而非其中出现的标识符
 *     （只断言标识符出现，把 `if (x)` 改成 `if (false)` 仍然通过 = 核心变异静默逃逸）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import fs from 'node:fs'
import path from 'node:path'

import {
  MAX_CELL_UPDATES,
  buildCellPatch,
  classifyEmptyGrid,
  colIndexToLetter,
  colLetterToIndex,
  gridHasContent,
  normalizeCellRef,
  parseCellRef,
} from '../customWpCellEdit'

// ─── 仓库根定位：双哨兵具体文件向上查找（禁写死回退级数） ──────────────────
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'app', 'services', 'custom_workpaper_projection.py')
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

/** 剥 JS/TS 注释（带字符串状态机，避免 URL 的 `//` 与 `accept="image/*"` 误判） */
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
    if (mode === 'line') { if (ch === '\n') { mode = 'code'; out += ch } ; i++; continue }
    if (mode === 'block') { if (ch === '*' && next === '/') { mode = 'code'; i += 2 } else i++; continue }
    // 字符串态：原样保留，处理转义
    out += ch
    if (ch === '\\') { out += next ?? ''; i += 2; continue }
    if ((mode === 'sq' && ch === "'") || (mode === 'dq' && ch === '"') || (mode === 'tpl' && ch === '`')) mode = 'code'
    i++
  }
  return out
}

/** 剥 Python 注释（`#` 到行尾，跳过字符串内） */
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

/**
 * 取某个函数的函数体（含花括号内文本）。找不到返回空串。
 *
 * 🔴 三条平台铁律都在这里落地（memory §踩坑铁律）：
 *   1. **禁固定字符窗口**（`slice(i, i+400)`）—— 块比窗口长时截出半截，断言假红/假绿
 *   2. **先按圆括号配对跳过参数列表** —— `function f(x: { a: 1 }) {` 的第一个 `{`
 *      在参数里，直接找 `{` 会截出参数的类型字面量
 *   3. **跳过内联返回类型注解** —— `function spanOf(...): { colspan: number } {`
 *      的第一个 `{` 是**返回类型**，截出来的"函数体"是那段类型 ⇒ 后续断言全在
 *      无关文本上求值。故逐个候选 `{` 配对，取第一个**含语句特征**的块。
 */
function fnBody(src: string, name: string): string {
  const decl = new RegExp(`function\\s+${name}\\s*\\(`)
  const m = src.match(decl)
  if (!m || m.index === undefined) return ''
  // ① 按圆括号配对跳过参数列表
  let i = src.indexOf('(', m.index)
  if (i < 0) return ''
  let depth = 0
  for (; i < src.length; i++) {
    if (src[i] === '(') depth++
    else if (src[i] === ')') {
      depth--
      if (depth === 0) { i++; break }
    }
  }
  // ② 逐个候选 `{` 做花括号配对，取第一个含语句特征的块（跳过返回类型字面量）
  const STATEMENT = /\b(return|const|let|if|for|while|await|throw|emit|expect)\b/
  while (i < src.length) {
    const open = src.indexOf('{', i)
    if (open < 0) return ''
    let d = 0
    let close = -1
    for (let j = open; j < src.length; j++) {
      if (src[j] === '{') d++
      else if (src[j] === '}') {
        d--
        if (d === 0) { close = j; break }
      }
    }
    if (close < 0) return ''
    const body = src.slice(open + 1, close)
    if (STATEMENT.test(body)) return body
    i = close + 1
  }
  return ''
}

/**
 * 截取 `const NAME = ...(() => { ... })` 形态的箭头函数/computed 体。
 *
 * 🔴 为什么不能用固定字符窗口（M3 变异实测抓出的守卫缺陷）：
 *   原判据写 `/formulaCellSet[\s\S]{0,200}?props\.formulaCells/`，而 200 字符窗口
 *   会**越过 `formulaCellSet` 的函数体尾部**，命中紧随其后的 `formulaExpr()` 里的
 *   `props.formulaCells` ⇒ 把 `formulaCellSet` 改成不读 prop 时守卫**仍然通过**。
 *   正解 = 花括号配对精确取该常量自己的函数体，只在体内断言。
 */
function arrowBody(src: string, name: string): string {
  const decl = new RegExp(`const\\s+${name}\\s*=`)
  const m = src.match(decl)
  if (!m || m.index === undefined) return ''
  // 从声明处起找第一个 `{`，做花括号配对（computed(() => { ... }) 的体）
  const open = src.indexOf('{', m.index)
  if (open < 0) return ''
  let d = 0
  for (let j = open; j < src.length; j++) {
    if (src[j] === '{') d++
    else if (src[j] === '}') {
      d--
      if (d === 0) return src.slice(open + 1, j)
    }
  }
  return ''
}

/** 取 `<script setup>` 区块（不含 template/style），用于「只在脚本里断言」的判据 */
function scriptBlock(sfc: string): string {
  const m = sfc.match(/<script[^>]*>([\s\S]*?)<\/script>/)
  return m ? m[1] : ''
}
/** 取 `<template>` 区块 */
function templateBlock(sfc: string): string {
  const m = sfc.match(/<template>([\s\S]*)<\/template>/)
  return m ? m[1] : ''
}

const GRID_SFC_REL = 'audit-platform/frontend/src/components/workpaper/custom/GtCustomGridSheet.vue'
const SHARED_GRID_REL = 'audit-platform/frontend/src/components/workpaper/GtGridSheet.vue'
const BACKEND_PROJ_REL = 'backend/app/services/custom_workpaper_projection.py'
const CELLS_ROUTER_REL = 'backend/app/routers/custom_workpaper_cells.py'

// ════════════════════════════════════════════════════════════════════════════
describe('守卫自检（判据本身必须有效）', () => {
  it('stripComments 确实剥掉注释且不误伤字符串', () => {
    const sample = `const a = 1 // 注释里写 forbiddenToken\n/* block forbiddenToken */\nconst u = 'http://x//y'\nconst t = \`a//b\``
    const cleaned = stripComments(sample)
    expect(cleaned).not.toContain('forbiddenToken')
    expect(cleaned).toContain('http://x//y')
    expect(cleaned).toContain('a//b')
  })

  it('stripPyComments 确实剥掉 # 注释与 docstring', () => {
    const sample = `def f():\n    """doc forbiddenPy"""\n    x = 1  # forbiddenPy\n    s = "keep#me"\n    return x`
    const cleaned = stripPyComments(sample)
    expect(cleaned).not.toContain('forbiddenPy')
    expect(cleaned).toContain('keep#me')
  })

  it('🔴 arrowBody 不越过函数体尾部（固定字符窗口会漏判 —— M3 变异实测）', () => {
    const sample = [
      'const target = computed(() => {',
      '  const a = 1',
      '  return a',
      '})',
      '',
      'function neighbor() {',
      '  return props.formulaCells',
      '}',
    ].join('\n')
    const body = arrowBody(sample, 'target')
    expect(body).toBeTruthy()
    expect(body).toContain('const a = 1')
    // 邻居函数里的内容绝不能被截进来（否则 M3 那类变异静默逃逸）
    expect(body).not.toContain('props.formulaCells')
    // 对照：固定窗口判据会被邻居骗过
    expect(/target[\s\S]{0,200}?props\.formulaCells/.test(sample)).toBe(true)
  })

  it('readFileAt 对不存在的路径抛错（判据失效必须打红而非静默通过）', () => {
    expect(() => readFileAt('backend/__no_such_file__.py')).toThrow(/判据文件缺失/)
  })

  it('🔴 fnBody 跳过参数列表与内联返回类型注解（平台铁律：禁固定字符窗口）', () => {
    // ① 参数里含类型字面量 `{ a: number }`：第一个 `{` 在参数内
    const withObjParam = `function f(o: { a: number }) {\n  return o.a + 1\n}`
    expect(fnBody(withObjParam, 'f')).toMatch(/return o\.a \+ 1/)
    // ② 内联返回类型注解：第一个配对块是**类型**而非函数体
    const withRetType = `function spanOf(r: number): { colspan: number; rowspan: number } {\n  const x = 1\n  return { colspan: x, rowspan: x }\n}`
    const body = fnBody(withRetType, 'spanOf')
    expect(body).toMatch(/const x = 1/)
    // 若误取到返回类型，body 会是 ` colspan: number; rowspan: number ` —— 这里必须不成立
    expect(body).not.toMatch(/^\s*colspan: number; rowspan: number\s*$/)
    // ③ 嵌套花括号不提前闭合
    const nested = `function g() {\n  if (a) { return 1 }\n  return 2\n}`
    expect(fnBody(nested, 'g')).toMatch(/return 2/)
    // ④ 找不到的函数返回空串（而非抛错/返回整份源码）
    expect(fnBody(nested, 'noSuchFn')).toBe('')
  })

  it('弱判据对照：只断言标识符出现无法抓住「条件改成 false」', () => {
    const good = 'if (dirty.size > maxCells) { overflow = true }'
    const mutated = 'if (false) { overflow = true } // maxCells 仍在文本里'
    // 弱判据（只看标识符）在变异后仍通过 —— 证明必须断言条件形态
    expect(good).toContain('maxCells')
    expect(mutated).toContain('maxCells')
    // 强判据（条件形态）能区分
    const cond = /if\s*\([^)]*>\s*maxCells\s*\)/
    expect(cond.test(good)).toBe(true)
    expect(cond.test(mutated)).toBe(false)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 4: 单元格引用往返可逆', () => {
  it('列字母 ↔ 列号往返（含多字母）', () => {
    expect(colLetterToIndex('A')).toBe(1)
    expect(colLetterToIndex('Z')).toBe(26)
    expect(colLetterToIndex('AA')).toBe(27)
    expect(colIndexToLetter(1)).toBe('A')
    expect(colIndexToLetter(26)).toBe('Z')
    expect(colIndexToLetter(27)).toBe('AA')
  })

  it('parseCellRef 与 openpyxl 口径一致（1-based 行列）', () => {
    expect(parseCellRef('B5')).toEqual({ row: 5, col: 2 })
    expect(parseCellRef('AA3')).toEqual({ row: 3, col: 27 })
    expect(parseCellRef('$B$5')).toEqual({ row: 5, col: 2 })
    expect(parseCellRef('b5')).toEqual({ row: 5, col: 2 })
  })

  it('🔴 非法引用返回 null 而不是 0（返 0 会让调用方 if 判空成功但语义是第 0 行）', () => {
    for (const bad of ['', 'B', '5', 'B5C', 'B0', '  ', '1A', 'B-5', '#REF!']) {
      expect(parseCellRef(bad), `parseCellRef(${JSON.stringify(bad)})`).toBeNull()
      expect(normalizeCellRef(bad), `normalizeCellRef(${JSON.stringify(bad)})`).toBeNull()
    }
  })

  it('normalizeCellRef ∘ parseCellRef 往返可逆（PBT）', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 200 }),
        fc.integer({ min: 1, max: 200 }),
        (row, col) => {
          const ref = `${colIndexToLetter(col)}${row}`
          expect(normalizeCellRef(ref)).toBe(ref)
          expect(parseCellRef(ref)).toEqual({ row, col })
          // 绝对引用与小写形态归一到同一个键
          expect(normalizeCellRef(`$${colIndexToLetter(col)}$${row}`)).toBe(ref)
          expect(normalizeCellRef(ref.toLowerCase())).toBe(ref)
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 5: 脏格补丁去重与超限', () => {
  it('同一格多次修改保留最后一次（键归一化后合并）', () => {
    const dirty = new Map<string, unknown>([
      ['b5', 1],
      ['$B$5', 2],
      ['B5', 3],
    ])
    const r = buildCellPatch(dirty)
    expect(Object.keys(r.updates)).toEqual(['B5'])
    expect(r.updates.B5).toBe(3)
  })

  it('非法键被丢弃并如实报告（不静默吞）', () => {
    const r = buildCellPatch({ B5: 1, ZZZ: 2, '': 3 })
    expect(r.updates).toEqual({ B5: 1 })
    expect(r.invalid.sort()).toEqual(['', 'ZZZ'].sort())
  })

  it('🔴 超限置 overflow 而非静默截断（截断会让用户以为都存上了）', () => {
    const dirty: Record<string, unknown> = {}
    for (let i = 1; i <= 5; i++) dirty[`A${i}`] = i
    const r = buildCellPatch(dirty, { maxCells: 3 })
    expect(r.overflow).toBe(true)
    // 未截断：全部键仍在（调用方据此提示分批，而不是丢数据）
    expect(Object.keys(r.updates)).toHaveLength(5)
  })

  it('未超限时 overflow 为 false', () => {
    const r = buildCellPatch({ A1: 1 }, { maxCells: 3 })
    expect(r.overflow).toBe(false)
  })

  it('归一化后无重复键（PBT）', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.tuple(fc.integer({ min: 1, max: 20 }), fc.integer({ min: 1, max: 20 })),
          { minLength: 1, maxLength: 30 },
        ),
        (pairs) => {
          const dirty = new Map<string, unknown>()
          pairs.forEach(([r, c], i) => {
            const ref = i % 2 === 0
              ? `${colIndexToLetter(c)}${r}`
              : `$${colIndexToLetter(c).toLowerCase()}$${r}`
            dirty.set(ref, i)
          })
          const out = buildCellPatch(dirty)
          const keys = Object.keys(out.updates)
          expect(new Set(keys).size).toBe(keys.length)
          for (const k of keys) expect(normalizeCellRef(k)).toBe(k)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('MAX_CELL_UPDATES 与后端常量交叉锁死', () => {
    const py = stripPyComments(readFileAt(BACKEND_PROJ_REL) + readFileAt(CELLS_ROUTER_REL))
    const m = py.match(/MAX_CELL_UPDATES\s*=\s*(\d+)/)
    expect(m, '后端未声明 MAX_CELL_UPDATES').not.toBeNull()
    expect(Number(m![1])).toBe(MAX_CELL_UPDATES)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('gridHasContent / classifyEmptyGrid 三侧口径一致', () => {
  it('与 GtGridSheet.hasData 同口径：cells 非空 且 max_row > 0', () => {
    expect(gridHasContent({ cells: { A1: { v: 1 } }, max_row: 1 })).toBe(true)
    expect(gridHasContent({ cells: {}, max_row: 5 })).toBe(false)
    expect(gridHasContent({ cells: { A1: { v: 1 } }, max_row: 0 })).toBe(false)
    expect(gridHasContent(null)).toBe(false)
    expect(gridHasContent(undefined)).toBe(false)
  })

  it('前端 hasData 表达式与共享只读件逐字同构（防口径漂移）', () => {
    const shared = stripComments(scriptBlock(readFileAt(SHARED_GRID_REL)))
    // 共享件：Object.keys(cells.value).length > 0 && maxRow.value > 0
    expect(shared).toMatch(/Object\.keys\(\s*cells\.value\s*\)\.length\s*>\s*0\s*&&\s*maxRow\.value\s*>\s*0/)
  })

  it('🔴 空网格三态可分：文件异常 ≠ 空底稿（两者都显示「暂无内容」会让文件损坏被当正常空表）', () => {
    expect(classifyEmptyGrid({ cells: { A1: { v: 1 } }, max_row: 1 })).toBe('has-content')
    expect(classifyEmptyGrid({ cells: {}, max_row: 0, source_unavailable: true })).toBe('source-unavailable')
    expect(classifyEmptyGrid({ cells: {}, max_row: 0 })).toBe('empty-workpaper')
  })

  it('后端 source_unavailable 标记确实存在（跨前后端锁死）', () => {
    const py = stripPyComments(readFileAt(BACKEND_PROJ_REL))
    expect(py).toContain('source_unavailable')
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 14: 公式格不可手工覆盖（数据驱动，非 CSS）', () => {
  const sfc = readFileAt(GRID_SFC_REL)
  const script = stripComments(scriptBlock(sfc))
  const tpl = templateBlock(sfc)

  it('组件声明了 formulaCells prop（判定由数据驱动）', () => {
    expect(script).toMatch(/formulaCells\??\s*:\s*(string\[\]|Record|Array)/)
  })

  it('🔴 isFormulaCell 的判定基于 formulaCells 集合而非 CSS class', () => {
    // 断言条件形态：必须查集合成员，不能只靠样式
    expect(script).toMatch(/formulaCellSet[\s\S]{0,200}?\.has\(/)
  })

  it('🔴 canEdit 同时受 readonly 与 isFormulaCell 门控（断言条件形态）', () => {
    const m = script.match(/function\s+canEdit\s*\([^)]*\)\s*:\s*boolean\s*\{([\s\S]*?)\n\}/)
    expect(m, 'canEdit 未找到').not.toBeNull()
    const body = m![1]
    // 只读态必须早退
    expect(body).toMatch(/if\s*\(\s*(props\.)?readonly\s*\)\s*return\s+false/)
    // 公式格必须早退
    expect(body).toMatch(/if\s*\(\s*isFormulaCell\([^)]*\)\s*\)\s*return\s+false/)
  })

  it('双击进入编辑 / Esc 取消 / Enter 提交 在模板中接线', () => {
    expect(tpl).toMatch(/@dblclick/)
    expect(tpl).toMatch(/@keyup\.esc/)
    expect(tpl).toMatch(/@keyup\.enter/)
  })

  it('🔴 编辑控件绑 @input（只绑 @change 会被 EP 在 nextTick 重置回 modelValue，抹掉键入）', () => {
    // 编辑输入必须是 el-input 且带 @input
    expect(tpl).toMatch(/<el-input(?=[\s/>])/)
    expect(tpl).toMatch(/@input\s*=/)
  })

  it('公式格有 tooltip 展示表达式（不是只有角标）', () => {
    // 🔴 判据要盯「真语义」而非某个标识符：模板上有 :title 绑定，
    // 且该绑定函数的实现里确实读了公式表达式（formulaExpr）。
    // 首版只在 <template> 段找 `formulaExpr` 是错的 —— 那个名字在 <script> 段，
    // 模板上是 `:title="cellTooltip(r, c)"`（又一次「守卫找错了层」）。
    const m = tpl.match(/:title="(\w+)\(/)
    expect(m, '模板上应有 :title="fn(...)" 绑定').toBeTruthy()
    const titleFn = m![1]
    // 该函数体里必须读到公式表达式，否则 tooltip 只是空壳
    const body = fnBody(script, titleFn)
    expect(body, `未找到 ${titleFn} 的实现`).toBeTruthy()
    expect(body).toMatch(/formulaExpr|expression/)
  })

  it('🔴 反向自检: 公式格判定由 formulaCells prop 驱动而非 CSS', () => {
    // 变异「把 isFormulaCell 改成恒 false」时下面两条会红
    expect(script).toMatch(/function\s+isFormulaCell\s*\(/)
    const body = fnBody(script, 'isFormulaCell')
    expect(body).toMatch(/formulaCellSet/)
    // 🔴 formulaCellSet 必须源自 props.formulaCells（不是硬编码集合）。
    // 判据必须精确截取该 computed 的**函数体**，禁用固定字符窗口 ——
    // `formulaCellSet[\s\S]{0,200}?props\.formulaCells` 会溢出到紧随其后的
    // `formulaExpr()`（它也读 props.formulaCells）⇒ 把 formulaCellSet 内部改成
    // 不读 prop 时守卫仍然通过（变异 M3 实测静默逃逸）。
    const setBody = arrowBody(script, 'formulaCellSet')
    expect(setBody, '未找到 formulaCellSet 的 computed 实现').toBeTruthy()
    expect(setBody).toMatch(/props\.formulaCells/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('保存失败可见性与金额格式单一真源', () => {
  const sfc = readFileAt(GRID_SFC_REL)
  const script = stripComments(scriptBlock(sfc))

  it('🔴 保存失败 ElMessage.error 且保留脏格（禁纯 catch {}）', () => {
    expect(script).toMatch(/ElMessage\.error/)
    // 不得出现空 catch
    expect(script).not.toMatch(/catch\s*(\([^)]*\))?\s*\{\s*\}/)
  })

  it('🔴 fmtAmount 走 store 成员且在 setup 顶层 inject（模块级命名导入会整页崩）', () => {
    expect(script).toMatch(/inject\(\s*DisplayPrefs_Key\s*,\s*null\s*\)\s*\?\?\s*useDisplayPrefsStore\(\)/)
    // 禁止把 fmtAmount 当模块命名导出引入
    expect(script).not.toMatch(/import\s*\{[^}]*\bfmtAmount\b[^}]*\}\s*from\s*['"]@\/stores\/displayPrefs['"]/)
  })

  it('DisplayPrefs_Key 的真源模块确实导出它（防 import 到不存在的符号）', () => {
    const keyMod = readFileAt(
      'audit-platform/frontend/src/components/workpaper/composables/displayPrefsKey.ts',
    )
    expect(keyMod).toMatch(/export\s+const\s+DisplayPrefs_Key/)
  })

  it('端点路径不硬编码在模板字符串里散落（集中一处常量）', () => {
    const hits = script.match(/custom-cells/g) ?? []
    expect(hits.length).toBeGreaterThan(0)
    // 只允许出现在一处常量/一处调用，避免多处漂移
    expect(hits.length).toBeLessThanOrEqual(2)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('反向自检: 共享只读件 GtGridSheet.vue 未被修改', () => {
  const shared = readFileAt(SHARED_GRID_REL)
  const sharedScript = stripComments(scriptBlock(shared))

  it('🔴 readonly 默认值仍为 true（40+ 只读消费方依赖）', () => {
    expect(sharedScript).toMatch(/withDefaults\([\s\S]*?\{\s*readonly:\s*true\s*\}\s*\)/)
  })

  it('🔴 仍为零 emit（一旦有 emit 说明有人把它改成可编辑了）', () => {
    expect((sharedScript.match(/\bemit\(/g) ?? []).length).toBe(0)
    expect((sharedScript.match(/defineEmits/g) ?? []).length).toBe(0)
  })

  it('可编辑网格是独立组件而非改共享件', () => {
    const own = readFileAt(GRID_SFC_REL)
    expect(own).toMatch(/defineEmits/)
    // 🔴 判据是「不依赖」而非「不提及」——组件注释里写明「复用 GtGridSheet 的视觉规则、
    // 有意不改它」是必要留证（memory 铁律：读源码型守卫必先 stripComments，否则说明性
    // 注释会被数成真实引用）。真正要禁的是 import/渲染共享件。
    const ownScript = stripComments(scriptBlock(own))
    const ownTemplate = stripComments(templateBlock(own))
    expect(ownScript).not.toMatch(/import\s+GtGridSheet\b/)
    expect(ownScript).not.toMatch(/from\s+['"][^'"]*GtGridSheet\.vue['"]/)
    expect(ownTemplate).not.toMatch(/<GtGridSheet(?=[\s/>])/)
  })

  it('🔴 反向自检: 剥注释确实生效（否则上一条断言是空转）', () => {
    const own = readFileAt(GRID_SFC_REL)
    // 原始源码里确实提到了共享件（留证注释），剥注释后才消失 ——
    // 若这条断言失败说明 stripComments 没起作用或注释被删，上一条即失去区分度。
    expect(own).toContain('GtGridSheet')
    const ownScript = stripComments(scriptBlock(own))
    expect(ownScript).not.toContain('GtGridSheet')
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 23: 前后端单元格解析一致（读后端源码交叉锁死）', () => {
  const py = readFileAt(BACKEND_PROJ_REL)
  const pyClean = stripPyComments(py)

  it('后端三个解析函数存在', () => {
    expect(pyClean).toMatch(/def\s+parse_cell_ref\s*\(/)
    expect(pyClean).toMatch(/def\s+normalize_cell_ref\s*\(/)
    expect(pyClean).toMatch(/def\s+col_letter_to_index\s*\(/)
  })

  it('🔴 合法样本两侧行列一致 / 非法样本两侧都判非法', () => {
    // 后端 parse_cell_ref 非法返 (0,0)、normalize_cell_ref 非法返 None；
    // 前端 parseCellRef/normalizeCellRef 非法均返 null。两侧「是否合法」结论必须一致。
    const legal = ['B5', '$B$5', 'b5', 'AA3', 'A1', 'ZZ100']
    const illegal = ['', 'B', '5', 'B5C', 'B0', '1A']

    // 前端结论
    for (const s of legal) expect(normalizeCellRef(s), `前端应判合法: ${s}`).not.toBeNull()
    for (const s of illegal) expect(normalizeCellRef(s), `前端应判非法: ${s}`).toBeNull()

    // 后端实现形态：必须显式处理 $ 与大小写，并对空字母/空数字返回非法
    expect(pyClean).toMatch(/replace\(\s*["']\$["']\s*,/)
    expect(pyClean).toMatch(/upper\(\)/)
    // 非法路径必须返回 0 / None（不得抛异常）
    expect(pyClean).toMatch(/return\s+0\s*,\s*0|return\s+\(?\s*0\s*,\s*0\s*\)?/)
    expect(pyClean).toMatch(/def\s+normalize_cell_ref[\s\S]*?return\s+None/)
  })

  it('🔴 后端解析对「字母在数字之后」判非法（与前端 B5C 口径一致）', () => {
    // 前端：digits 已出现后再遇字母即 null
    expect(parseCellRef('B5C')).toBeNull()
    // 后端：必须有等价守卫（正则锚定或显式状态判断）
    const hasAnchoredRe = /\^\s*\(\?P<col>\[A-Z\]\+\)\s*\(\?P<row>\\d\+\)\s*\$|\^\[A-Z\]\+\\d\+\$/.test(pyClean)
    const hasStateGuard = /if\s+digits[\s\S]{0,80}?return/.test(pyClean)
    expect(hasAnchoredRe || hasStateGuard, '后端缺少「字母在数字后即非法」的守卫').toBe(true)
  })

  it('后端 write_cells_to_xlsx 的参数名为 updates（与前端 body 键一致）', () => {
    expect(pyClean).toMatch(/def\s+write_cells_to_xlsx\([\s\S]*?updates\s*:/)
    const router = stripPyComments(readFileAt(CELLS_ROUTER_REL))
    expect(router).toMatch(/updates\s*:\s*dict/)
    // 不得残留 patches 作为 body 键
    expect(router).not.toMatch(/patches\s*:\s*dict/)
  })
})
