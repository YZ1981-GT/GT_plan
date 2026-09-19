/**
 * 自定义底稿公式格只读态守卫（Task 26 浏览器实测抓出的 P0）。
 *
 * ## 被钉死的缺陷
 *
 * 2026-08-08 浏览器实测：给 D4 配了 `TB('1001','期末余额')` 后，该格
 * **没有 ƒ 标记、仍标 `--editable`、双击能进编辑态** ⇒ 审计师可直接改写公式格，
 * 改完被下一次求值静默覆盖（数据丢失）。
 *
 * 根因 = `GtCustomWpEditor.formulaCells` 从 `htmlData.cells[*].formula` 派生，
 * 而自定义底稿的公式**存在 `wp_formula` 表**、xlsx 里写的是**求值结果**
 * （`D4` 存的是数字 `0`，不是 `=TB(...)`）⇒ 该 computed 恒为空。
 *
 * ⇒ `formulaCells` 必须由 `wp_formula` 清单派生（挂载即拉 + 保存/删除后刷新），
 * xlsx 的 `formula` 键只作补充。
 *
 * ## 为什么四层验证抓不到
 *
 * - `get_diagnostics` / Vite transform：computed 恒空是运行时行为，不是类型错误
 * - 既有 `customFormulaWiring.spec.ts`：只验「保存端点/响应键/清单渲染」，
 *   不验「公式格在网格里是否只读」
 * - 只有浏览器里真配一条公式再看那一格才暴露
 *
 * spec: custom-workpaper-dual-mode-formula-and-batch Task 26
 */

import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

/** 双哨兵向上查找仓库根（单哨兵将来遇同名文件会误停）。 */
function repoRoot(): string {
  let dir = HERE
  for (let i = 0; i < 12; i++) {
    const a = resolve(dir, 'audit-platform/frontend/package.json')
    const b = resolve(dir, 'backend/app/main.py')
    if (existsSync(a) && existsSync(b)) return dir
    dir = resolve(dir, '..')
  }
  throw new Error('未找到仓库根（双哨兵 audit-platform/frontend/package.json + backend/app/main.py）')
}

const ROOT = repoRoot()
const EDITOR = resolve(ROOT, 'audit-platform/frontend/src/components/workpaper/GtCustomWpEditor.vue')
const GRID = resolve(
  ROOT,
  'audit-platform/frontend/src/components/workpaper/custom/GtCustomGridSheet.vue'
)

function src(p: string): string {
  expect(existsSync(p), `文件不存在: ${p}`).toBe(true)
  return readFileSync(p, 'utf-8')
}

/**
 * 剥注释（HTML 注释 + JS 行/块注释）。
 * 🔴 必须剥 —— 本守卫的修复说明注释里会原样写出被禁形态。
 * 🔴 块注释扫描要带字符串状态，否则 `accept="image/*"` 的 `/*` 会被当注释起点
 *    （memory 已记该坑）。
 */
function strip(s: string): string {
  let out = s.replace(/<!--[\s\S]*?-->/g, '')
  let res = ''
  let i = 0
  let inS: string | null = null
  while (i < out.length) {
    const ch = out[i]
    const nx = out[i + 1]
    if (inS) {
      res += ch
      if (ch === '\\') {
        res += nx ?? ''
        i += 2
        continue
      }
      if (ch === inS) inS = null
      i += 1
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      inS = ch
      res += ch
      i += 1
      continue
    }
    if (ch === '/' && nx === '/') {
      while (i < out.length && out[i] !== '\n') i += 1
      continue
    }
    if (ch === '/' && nx === '*') {
      i += 2
      while (i < out.length && !(out[i] === '*' && out[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    res += ch
    i += 1
  }
  return res
}

/** 按花括号配对截取函数体。支持三种形态：
 *  ① `const name = computed<...>(() => { ... })` / `const name = () => { ... }`
 *  ② `function name() { ... }` / `async function name() { ... }`
 *  ③ **调用式** `name(() => { ... })` —— 生命周期钩子（`onMounted`）属这类，
 *     它不是命名声明，只按 `const|function` 找会报「未找到声明」（本守卫首轮踩中）。
 *
 * 🔴 `async function` 必须排在 `function` 之前 —— 交替分支左优先，
 *    写成 `function|async function` 时 `async function foo` 里的 `function` 先命中，
 *    `\b${name}` 位置随之错位（本守卫首轮的第二个假红）。
 */
function arrowBody(s: string, name: string): string {
  const decl = new RegExp(`(?:const|let|var|async\\s+function|function)\\s+${name}\\b`).exec(s)
  // 调用式（onMounted / watch 等）：直接找 `name(`
  const call = decl ? null : new RegExp(`\\b${name}\\s*\\(`).exec(s)
  const m = decl ?? call
  expect(m, `未找到声明或调用: ${name}`).toBeTruthy()
  const from = m!.index
  // 🔴 `function` / `async function` 形态必须先用圆括号配对跳过参数列表 ——
  //    `async function f(payload: { a: string })` 的第一个 `{` 是**参数的内联类型
  //    字面量**，直接取它会把「类型声明」当函数体截出来，导致断言恒假红
  //    （memory 已记该坑：H 循环与 custom spec 各踩过一次）。
  //    `const` 箭头与调用式回调不能这么跳：它们的函数体本身就在括号内。
  let searchFrom = from
  if (/^(?:async\s+)?function\b/.test(s.slice(from, from + 20))) {
    const p = s.indexOf('(', from)
    if (p > -1) {
      let d = 0
      let j = p
      while (j < s.length) {
        if (s[j] === '(') d += 1
        else if (s[j] === ')') {
          d -= 1
          if (d === 0) break
        }
        j += 1
      }
      searchFrom = j
    }
  }
  const open = s.indexOf('{', searchFrom)
  expect(open, `未找到 ${name} 的函数体起点`).toBeGreaterThan(-1)
  let depth = 0
  let i = open
  while (i < s.length) {
    if (s[i] === '{') depth += 1
    else if (s[i] === '}') {
      depth -= 1
      if (depth === 0) break
    }
    i += 1
  }
  const body = s.slice(open, i + 1)
  expect(body.length, `${name} 函数体为空`).toBeGreaterThan(2)
  return body
}

describe('自定义底稿公式格只读态（Task 26 P0）', () => {
  it('formulaCells 必须由 wp_formula 清单派生，不能只读 cells[*].formula', () => {
    const code = strip(src(EDITOR))
    const body = arrowBody(code, 'formulaCells')
    expect(
      /formulaList/.test(body),
      'formulaCells 未消费 formulaList ⇒ 恒为空 ⇒ 公式格无 ƒ 标记且可被手工改写' +
        '（xlsx 里存的是求值结果不是表达式，靠 cells[*].formula 永远派生不出来）'
    ).toBe(true)
  })

  it('挂载即拉公式清单（否则刷新页面后公式格又变可编辑）', () => {
    const code = strip(src(EDITOR))
    expect(/onMounted\s*\(/.test(code), '缺少 onMounted ⇒ 首次进入页面时清单为空').toBe(true)
    const mounted = arrowBody(code, 'onMounted')
    expect(
      /fetchFormulaList\s*\(/.test(mounted),
      'onMounted 未拉公式清单 ⇒ 刷新后公式格恢复可编辑态'
    ).toBe(true)
  })

  it('公式保存后必须刷新清单（新加的公式格要立刻变只读）', () => {
    const code = strip(src(EDITOR))
    const body = arrowBody(code, 'onFormulaSave')
    expect(
      /fetchFormulaList\s*\(/.test(body),
      'onFormulaSave 未刷新公式清单 ⇒ 刚配好的公式格仍可双击改写'
    ).toBe(true)
  })

  it('拉取清单的静默版不得弹错误提示（挂载期弹窗会骚扰用户）', () => {
    const code = strip(src(EDITOR))
    const body = arrowBody(code, 'fetchFormulaList')
    expect(
      /items/.test(body),
      '响应键是 items 不是 formulas（后端 list_formulas 实证），读错键恒空'
    ).toBe(true)
  })

  it('网格侧：公式格判定驱动 ƒ 标记 / 只读 / tooltip 三处', () => {
    const code = strip(src(GRID))
    // canEdit 必须真的因公式格返回 false（不是只声明了 isFormulaCell）
    const canEdit = arrowBody(code, 'canEdit')
    expect(
      /if\s*\(\s*isFormulaCell\s*\(\s*r\s*,\s*c\s*\)\s*\)\s*return\s+false/.test(canEdit),
      'canEdit 未因公式格返回 false ⇒ 双击仍能编辑公式格'
    ).toBe(true)
    // ƒ 标记
    expect(/gt-cgs__fx/.test(code), '缺少 ƒ 标记元素 ⇒ 用户看不出哪些格是公式格').toBe(true)
    // tooltip 展示表达式（审计追溯）
    const tip = arrowBody(code, 'cellTooltip')
    expect(
      /formulaExpr\s*\(/.test(tip),
      'tooltip 未展示公式表达式 ⇒ 违反「审计 UI 必须有逻辑追溯能力」'
    ).toBe(true)
  })

  it('formulaCellSet 必须读 props.formulaCells（不能自己造来源）', () => {
    const code = strip(src(GRID))
    const body = arrowBody(code, 'formulaCellSet')
    expect(
      /props\s*\.\s*formulaCells/.test(body),
      'formulaCellSet 未读 props.formulaCells ⇒ 与宿主派生结果脱钩'
    ).toBe(true)
  })

  // ─── 反向自检 ────────────────────────────────────────────────────────────

  it('strip 真的剥掉注释（否则上面判据可被注释里的反例骗过）', () => {
    const sample = `
// 注释里写 formulaList 反例
/* 块注释里也写 fetchFormulaList( */
const x = 1
`
    const out = strip(sample)
    expect(out.includes('formulaList')).toBe(false)
    expect(out.includes('const x = 1')).toBe(true)
  })

  it('strip 不被 MIME 通配 /* 骗（accept="image/*" 之后的代码必须保留）', () => {
    const sample = `const a = 'image/*'\nconst marker_after = 2\n`
    const out = strip(sample)
    expect(
      out.includes('marker_after'),
      'MIME 通配的 /* 被当块注释起点，吞掉了后续真实代码（memory 已记该坑）'
    ).toBe(true)
  })

  it('arrowBody 跳过参数里的内联类型字面量（否则截出来是类型声明，断言恒假红）', () => {
    const sample = `
async function withInlineType(payload: { formula: string; target_cell?: string }) {
  const marker_real_body = 1
  return marker_real_body
}
`
    const body = arrowBody(sample, 'withInlineType')
    expect(body.includes('marker_real_body'), '未截到真实函数体').toBe(true)
    expect(
      body.includes('target_cell?: string'),
      '把参数的内联类型字面量当函数体截出来了 —— 这正是 onFormulaSave 首轮假红的成因'
    ).toBe(false)
  })

  it('arrowBody 支持三种形态：const 箭头 / async function / 调用式回调', () => {
    // 🔴 首版只认「命名声明」⇒ `onMounted(() => {...})` 找不到、`async function` 的
    //    正则分支顺序错 ⇒ 两条真判据以「未找到声明」的形式假红，而生产代码是对的。
    //    这条自检把三形态钉死，防解析缺陷再以假红/假绿形式复发。
    const sample = `
const aArrow = computed(() => { const inA = 1 })
async function bAsync(): Promise<void> { const inB = 2 }
onMounted(() => { const inC = 3 })
function dPlain() { const inD = 4 }
`
    expect(arrowBody(sample, 'aArrow')).toContain('inA')
    expect(arrowBody(sample, 'bAsync')).toContain('inB')
    expect(arrowBody(sample, 'onMounted')).toContain('inC')
    expect(arrowBody(sample, 'dPlain')).toContain('inD')
    // 互不串味
    expect(arrowBody(sample, 'bAsync')).not.toContain('inC')
    expect(arrowBody(sample, 'onMounted')).not.toContain('inD')
  })

  it('arrowBody 能精确截到本函数体（不越界到邻居函数）', () => {
    const sample = `
const first = computed(() => {
  return 'INSIDE_FIRST'
})
const second = computed(() => {
  return 'INSIDE_SECOND'
})
`
    const body = arrowBody(sample, 'first')
    expect(body.includes('INSIDE_FIRST')).toBe(true)
    expect(
      body.includes('INSIDE_SECOND'),
      '固定窗口/贪婪匹配越界到了下一个函数（memory 已记该坑）'
    ).toBe(false)
  })
})
