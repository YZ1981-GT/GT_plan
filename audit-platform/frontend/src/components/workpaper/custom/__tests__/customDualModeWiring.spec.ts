/**
 * customDualModeWiring.spec.ts — 自定义底稿双模式接线守卫（Wave 3 Task 11）
 *
 * spec: custom-workpaper-dual-mode-formula-and-batch
 *
 * 覆盖 Property：
 *   - Property 6  双模式用参数化工厂 `createDualMode`（禁 `useD1DualMode`）
 *                 + `el-segmented` 用 `:model-value`（禁 `v-model`）
 *   - Property 7  切回 HTML 时调投影刷新端点
 *
 * 🔴 判据设计要点（memory 铁律）：
 *   - 标签存在性断言**必须带边界** `<Foo(?=[\s/>])`，
 *     否则被 `<FooREMOVED` 骗过（「删掉渲染块」这个最核心的变异会静默逃逸）
 *   - 读源码前先 `stripComments()`，否则本文件解释「为什么禁 useD1DualMode」的
 *     注释会被数成真实引用（守卫打自己）
 *   - 反向自检必须证明这条禁令**有实际差异**（两个 composable 取值域确实不同），
 *     否则禁令是空转
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// ─── 仓库根：双哨兵具体文件向上查找（禁写死回退级数） ──────────────────────
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

/** 剥 JS/TS 注释（带字符串状态机，避免 URL 的 `//` 误判） */
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

/** 剥 HTML 注释（模板段用） */
function stripHtmlComments(src: string): string {
  return src.replace(/<!--[\s\S]*?-->/g, '')
}

function scriptBlock(sfc: string): string {
  const m = sfc.match(/<script[^>]*>([\s\S]*?)<\/script>/)
  return m ? m[1] : ''
}
function templateBlock(sfc: string): string {
  const m = sfc.match(/<template>([\s\S]*)<\/template>/)
  return m ? m[1] : ''
}

/**
 * 取箭头函数/对象方法体：`name: (...) => {…}` 或 `name(...) {…}`。
 * 🔴 花括号配对而非固定字符窗口 —— 固定窗口会溢出到下一个函数
 *    （平台已实证：200 字符窗口把下一个函数的 `props.formulaCells` 一起吞进来，
 *     导致「删掉本函数的读取」这个变异静默逃逸）。
 */
function propBody(src: string, key: string): string {
  const re = new RegExp(`${key}\\s*:`)
  const m = src.match(re)
  if (!m || m.index === undefined) return ''
  let i = src.indexOf('{', m.index)
  if (i < 0) return ''
  let d = 0
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') d++
    else if (src[j] === '}') {
      d--
      if (d === 0) return src.slice(i + 1, j)
    }
  }
  return ''
}

/**
 * 取对象字面量里 `key:` 的**值表达式**（到同层 `,` 或 `}` 为止）。
 *
 * 🔴 为什么必需：配置项有两种合法形态 ——
 *   引用式 `onSwitchToHtml: refreshProjection,`（**无花括号**）
 *   内联式 `onSwitchToHtml: async () => { ... },`
 * 只按 `propBody` 找 `{` 会在引用式上一路命中**后面某个不相关函数**的花括号，
 * 于是断言落在无关文本上（本守卫首版即因此假红）。
 */
function propValue(src: string, key: string): string {
  const m = src.match(new RegExp(`${key}\\s*:`))
  if (!m || m.index === undefined) return ''
  let i = m.index + m[0].length
  let depth = 0
  let out = ''
  for (; i < src.length; i++) {
    const ch = src[i]
    if ('{(['.includes(ch)) depth++
    else if ('})]'.includes(ch)) {
      if (depth === 0) break // 到达外层对象的收尾 `}`
      depth--
    } else if (ch === ',' && depth === 0) break
    out += ch
  }
  return out.trim()
}

/** 取具名函数（`function f(){}` / `const f = () => {}`）的函数体，花括号配对 */
function namedFnBody(src: string, name: string): string {
  const patterns = [
    new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`),
    new RegExp(`const\\s+${name}\\s*=\\s*(?:async\\s*)?\\(`),
  ]
  for (const re of patterns) {
    const m = src.match(re)
    if (!m || m.index === undefined) continue
    // 先按圆括号配对跳过参数列表（参数里可能有类型字面量的 `{`）
    let i = src.indexOf('(', m.index)
    let d = 0
    for (; i < src.length; i++) {
      if (src[i] === '(') d++
      else if (src[i] === ')') {
        d--
        if (d === 0) { i++; break }
      }
    }
    // 逐个候选 `{` 配对，取第一个含语句特征的块（跳过返回类型注解）
    const STATEMENT = /\b(return|const|let|if|for|while|await|throw|try)\b/
    while (i < src.length) {
      const open = src.indexOf('{', i)
      if (open < 0) break
      let dd = 0
      let close = -1
      for (let j = open; j < src.length; j++) {
        if (src[j] === '{') dd++
        else if (src[j] === '}') {
          dd--
          if (dd === 0) { close = j; break }
        }
      }
      if (close < 0) break
      const body = src.slice(open + 1, close)
      if (STATEMENT.test(body)) return body
      i = close + 1
    }
  }
  return ''
}

/**
 * 端点引用形态：字面量 URL 或 apiPaths 访问器（两者都合法）。
 *
 * 🔴 判据必须同时认这两种 —— 平台要求端点登记进 `apiPaths` 而非组件内硬编码，
 * 只认字面量会在「按规范改用 apiPaths」之后把正确写法打红（本守卫首版即如此）。
 * 用 apiPaths 时另由下面的交叉锁死断言保证该访问器真的指向本端点。
 */
const REFRESH_ENDPOINT_RE =
  /custom-refresh-projection|apiPaths\.workpapers\.customRefreshProjection/

/** 判断某段函数体是否（直接或经一层具名函数委托）触达投影刷新端点 */
function resolveEndpointReach(script: string, body: string): boolean {
  if (REFRESH_ENDPOINT_RE.test(body)) return true
  // 一层委托：体内调用的具名函数里含端点
  for (const m of body.matchAll(/\b([A-Za-z_$][\w$]*)\s*\(/g)) {
    const inner = namedFnBody(script, m[1])
    if (inner && REFRESH_ENDPOINT_RE.test(inner)) return true
  }
  return false
}

/** 取标签的开标签文本（按 `<` … `>` 配对，禁固定窗口） */
function openTag(tpl: string, tag: string): string {
  const re = new RegExp(`<${tag}(?=[\\s/>])`)
  const m = tpl.match(re)
  if (!m || m.index === undefined) return ''
  const end = tpl.indexOf('>', m.index)
  if (end < 0) return ''
  return tpl.slice(m.index, end + 1)
}

const EDITOR_REL = 'audit-platform/frontend/src/components/workpaper/GtCustomWpEditor.vue'
const FACTORY_REL = 'audit-platform/frontend/src/components/workpaper/composables/factories/createDualMode.ts'
const D1_DUAL_REL = 'audit-platform/frontend/src/components/workpaper/composables/useD1DualMode.ts'
const OO_ROUTER_REL = 'backend/app/routers/wp_onlyoffice_router.py'

/** 从给定的开括号位置起做花括号配对，截出函数体（禁固定字符窗口）。 */
function braceBodyFrom(src: string, openIdx: number): string {
  let depth = 0
  for (let i = openIdx; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) return src.slice(openIdx, i + 1)
    }
  }
  throw new Error('braceBodyFrom: 花括号不配对')
}

// ════════════════════════════════════════════════════════════════════════════
describe('守卫自检（判据本身必须有效）', () => {
  it('stripComments 剥注释且不误伤字符串', () => {
    const s = `const a = 1 // useD1DualMode\n/* useD1DualMode */\nconst u = 'http://x//y'`
    const c = stripComments(s)
    expect(c).not.toContain('useD1DualMode')
    expect(c).toContain('http://x//y')
  })

  it('openTag 带边界：<Foo 不会被 <FooREMOVED 命中', () => {
    const tpl = `<GtOnlyOfficeSheetREMOVED :a="1" />`
    expect(openTag(tpl, 'GtOnlyOfficeSheet')).toBe('')
    const ok = `<GtOnlyOfficeSheet :a="1" />`
    expect(openTag(ok, 'GtOnlyOfficeSheet')).toContain(':a="1"')
  })

  it('propBody 花括号配对，不溢出到下一个函数', () => {
    const src = `onSwitchToHtml: async () => { await refreshProjection() },\nother: () => { LEAK }`
    const body = propBody(src, 'onSwitchToHtml')
    expect(body).toContain('refreshProjection')
    expect(body).not.toContain('LEAK')
  })

  it('🔴 propValue 对「引用式」不越界到后面的无关函数（本守卫首版缺陷）', () => {
    const src = [
      'const dualMode = createDualMode({',
      '  persistKey: `k`,',
      '  onSwitchToHtml: refreshProjection,',
      '})',
      '',
      'function unrelated() { LEAK_MARKER }',
    ].join('\n')
    expect(propValue(src, 'onSwitchToHtml')).toBe('refreshProjection')
    // 对照：propBody 在引用式上会溢出到 unrelated 的花括号
    expect(propBody(src, 'onSwitchToHtml')).toContain('LEAK_MARKER')
  })

  it('propValue 支持内联箭头函数且不吞掉同层后续项', () => {
    const src = 'createDualMode({ onSwitchToHtml: async () => { await go() }, other: 1 })'
    const v = propValue(src, 'onSwitchToHtml')
    expect(v).toContain('await go()')
    expect(v).not.toContain('other')
  })

  it('namedFnBody 跳过参数列表与返回类型注解', () => {
    const src = 'async function refreshProjection(o: { a: 1 }): Promise<void> {\n  await api.post("/x/custom-refresh-projection")\n}'
    expect(namedFnBody(src, 'refreshProjection')).toContain('custom-refresh-projection')
  })

  it('resolveEndpointReach 支持一层委托', () => {
    const script = 'function inner() {\n  return api.post("/a/custom-refresh-projection")\n}'
    expect(resolveEndpointReach(script, 'await inner()')).toBe(true)
    expect(resolveEndpointReach(script, 'await somethingElse()')).toBe(false)
  })

  it('readFileAt 对不存在路径抛错（判据失效必须打红）', () => {
    expect(() => readFileAt('backend/__no_such__.py')).toThrow(/判据文件缺失/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 6: 双模式用参数化工厂 createDualMode', () => {
  const sfc = readFileAt(EDITOR_REL)
  const script = stripComments(scriptBlock(sfc))
  const tpl = stripHtmlComments(templateBlock(sfc))

  it('引用 createDualMode 工厂', () => {
    expect(script).toMatch(/createDualMode/)
    expect(script).toMatch(/from\s+['"][^'"]*factories\/createDualMode['"]/)
  })

  it('🔴 不得引用 useD1DualMode（其取值是 html|oo，与平台 40+ 处不统一）', () => {
    expect(script).not.toMatch(/useD1DualMode/)
  })

  it('🔴 反向自检: 两个 composable 取值域确实不同（证明禁令非空转）', () => {
    const factory = readFileAt(FACTORY_REL)
    // 工厂取值域必须是 'html' | 'onlyoffice'
    expect(factory).toMatch(/'html'\s*\|\s*'onlyoffice'/)
    // useD1DualMode 若存在，其取值域应含 'oo'（差异真实存在）
    const d1Path = path.join(ROOT, D1_DUAL_REL)
    if (fs.existsSync(d1Path)) {
      const d1 = fs.readFileSync(d1Path, 'utf-8')
      expect(d1, 'useD1DualMode 取值域应含 oo，否则本禁令失去依据').toMatch(/'oo'/)
    }
  })

  it('persistKey 按 wpId 区分（避免多底稿互相覆盖偏好）', () => {
    expect(script).toMatch(/persistKey\s*:/)
    expect(script).toMatch(/custom-wp-mode-/)
  })

  it('🔴 el-segmented 用 :model-value + @change，禁 v-model', () => {
    const seg = openTag(tpl, 'el-segmented')
    expect(seg, '模板中应有 <el-segmented>').toBeTruthy()
    expect(seg).toMatch(/:model-value=/)
    expect(seg).toMatch(/@change=/)
    // v-model 会先改值使 switchMode 的 `target === currentMode` 守卫短路
    expect(seg).not.toMatch(/v-model/)
  })

  it('🔴 反向自检: switchMode 确有同值短路守卫（证明禁 v-model 有依据）', () => {
    const factory = stripComments(readFileAt(FACTORY_REL))
    expect(factory).toMatch(/if\s*\(\s*target\s*===\s*currentMode\.value\s*\)\s*return/)
  })

  it('OO 侧渲染 GtOnlyOfficeSheet 且带 @fallback 回落（标签断言带边界）', () => {
    const oo = openTag(tpl, 'GtOnlyOfficeSheet')
    expect(oo, '模板中应有 <GtOnlyOfficeSheet>').toBeTruthy()
    expect(oo).toMatch(/@fallback=/)
  })

  it('HTML 侧渲染 GtCustomGridSheet（可编辑网格，标签断言带边界）', () => {
    const grid = openTag(tpl, 'GtCustomGridSheet')
    expect(grid, '模板中应有 <GtCustomGridSheet>').toBeTruthy()
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('Property 7: 切回 HTML 时刷新投影', () => {
  const sfc = readFileAt(EDITOR_REL)
  const script = stripComments(scriptBlock(sfc))

  it('onSwitchToHtml 回调（引用式或内联式）都能追到投影刷新端点', () => {
    const val = propValue(script, 'onSwitchToHtml')
    expect(val, '未找到 onSwitchToHtml 配置项').toBeTruthy()

    // 形态 A：内联箭头函数 `onSwitchToHtml: () => { ... }` / `async () => { ... }`
    if (val.includes('{')) {
      const body = propBody(script, 'onSwitchToHtml')
      expect(body, '内联回调体应可截取').toBeTruthy()
      expect(resolveEndpointReach(script, body)).toBe(true)
      return
    }

    // 形态 B：函数引用 `onSwitchToHtml: refreshProjection`
    // 🔴 这里是本守卫首版的缺陷所在：`propBody` 对无花括号的引用式会一路找到
    //    **后面某个不相关函数**的 `{`，从而在无关文本上求值（既可能假红也可能假绿）。
    const fnName = val.trim().replace(/,$/, '')
    expect(fnName, 'onSwitchToHtml 应是标识符或内联函数').toMatch(/^[A-Za-z_$][\w$]*$/)
    const fnBody = namedFnBody(script, fnName)
    expect(fnBody, `未找到 ${fnName} 的实现`).toBeTruthy()
    expect(
      resolveEndpointReach(script, fnBody),
      `${fnName} 未追到 custom-refresh-projection 端点`
    ).toBe(true)
  })

  it('刷新端点用 POST（GET 语义不对：它会写 parsed_data）', () => {
    expect(script).toMatch(
      /api\.post\(\s*(?:apiPaths\.workpapers\.customRefreshProjection|[`'"][^`'"]*custom-refresh-projection)/
    )
  })

  it('🔴 交叉锁死: apiPaths 的访问器确实指向 custom-refresh-projection 端点', () => {
    // 组件改用 apiPaths 后，「端点对不对」的判据落在 apiPaths 定义上 ——
    // 不锁死它就可能出现「访问器名字对、URL 指到别处」的静默错误
    const ap = readFileAt(
      'audit-platform/frontend/src/services/apiPaths/workpaper.ts'
    )
    expect(ap).toMatch(
      /customRefreshProjection:\s*\([^)]*\)\s*=>\s*`\/api\/workpapers\/\$\{[^}]*\}\/custom-refresh-projection`/
    )
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('后端: OO 回调 custom 投影为加法式接线', () => {
  const src = readFileAt(OO_ROUTER_REL)

  it('存在 custom 门控（非 custom 路径整体跳过）', () => {
    // 🔴 判据是**条件形态**而非标识符出现 ——
    // 只断言 `resolve_is_custom` 出现，把 `if await resolve_is_custom(...)`
    // 改成 `if False:` 仍然通过 = 最核心的变异静默逃逸
    expect(src).toMatch(/if\s+await\s+resolve_is_custom\(/)
  })

  it('🔴 resolve_is_custom 传三个参数（少传会 TypeError 被 except 吞成死代码）', () => {
    const m = src.match(/resolve_is_custom\(([^)]*)\)/)
    expect(m, '未找到 resolve_is_custom 调用').toBeTruthy()
    const args = m![1].split(',').map((s) => s.trim()).filter(Boolean)
    expect(args, `实参应为 3 个 (db, wp, wp_code)，实为 ${args.length}: ${args.join('|')}`)
      .toHaveLength(3)
  })

  it('投影刷新失败 fail-open（WARNING 不抛）', () => {
    const idx = src.indexOf('custom 投影刷新失败')
    expect(idx, '应有 custom 投影刷新失败的 WARNING').toBeGreaterThan(0)
    // 该日志必须在 except 块里且不 raise
    const around = src.slice(Math.max(0, idx - 600), idx + 200)
    expect(around).toMatch(/except\s+Exception/)
    expect(around).not.toMatch(/raise\s+HTTPException/)
  })

  it('只对 xlsx 走投影（docx/word-template 路径不受影响）', () => {
    const idx = src.indexOf('custom: OO 侧编辑落盘后从 xlsx 重投影')
    expect(idx).toBeGreaterThan(0)
    const after = src.slice(idx, idx + 900)
    expect(after).toMatch(/\.suffix\.lower\(\)\s*==\s*['"]\.xlsx['"]/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
describe('R2/R3 用户可达性：custom 不得被只读 grid 兜底挤掉', () => {
  const RENDERER_REL = 'audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue'

  /**
   * 🔴 Task 26 浏览器实测抓到的真实缺口（四层验证全绿、只有浏览器能发现）：
   *
   * `GtWpRenderer.noRendererGridFallback` 的 `isGridOnly` 判据是
   * 「有 cells 且无 rows/programs/audit_rows」—— 而自定义底稿的 html_data
   * **正是**恒等坐标投影（cells/max_row/max_col/col_widths/merged_cells/header_rows），
   * 恰好命中 ⇒ `rendererEntry` 被强制 undefined ⇒ 专属编辑器 `GtCustomWpEditor`
   * （双模式 + 可编辑网格 + 自定义公式）**永不渲染**，用户只看到只读 GtGridSheet。
   *
   * 即「投影做对了反而把专属编辑器挤掉」。registry 映射、render-config、
   * componentType 三处全部正确，故 vitest/get_diagnostics/Vite 都查不出。
   *
   * 实测证据（修复前 → 后）：
   *   表格 class  gt-grid-sheet__table → gt-cgs__table
   *   el-segmented 数量        0 → 1（表格视图 / 在线编辑）
   */
  it('custom 在 grid 兜底判定里被显式豁免', () => {
    const src = stripComments(readFileAt(RENDERER_REL))
    const m = src.match(/const noRendererGridFallback\s*=\s*computed<boolean>\(\(\)\s*=>\s*\{/)
    expect(m).toBeTruthy()
    const body = braceBodyFrom(src, m!.index! + m![0].length - 1)
    // 条件形态断言（`if (false)` / 删整行都必须打红）
    expect(/if\s*\(\s*componentType\.value\s*===\s*'custom'\s*\)\s*return false/.test(body)).toBe(
      true,
    )
  })

  it('豁免必须早于 isGridOnly 判据（否则先被兜底短路）', () => {
    const src = stripComments(readFileAt(RENDERER_REL))
    const m = src.match(/const noRendererGridFallback\s*=\s*computed<boolean>\(\(\)\s*=>\s*\{/)
    const body = braceBodyFrom(src, m!.index! + m![0].length - 1)
    const iExempt = body.search(/componentType\.value\s*===\s*'custom'/)
    const iGridOnly = body.indexOf('isGridOnly')
    expect(iExempt).toBeGreaterThan(-1)
    expect(iGridOnly).toBeGreaterThan(-1)
    expect(iExempt).toBeLessThan(iGridOnly)
  })

  it('反向自检：isGridOnly 判据确实会命中 custom 的投影键集', () => {
    // custom 投影的实测键集（后端 project_custom_workpaper 产出）
    const hd: Record<string, unknown> = {
      cells: { A1: { v: 'x', r: 1, c: 1 } },
      max_row: 5,
      max_col: 7,
      col_widths: {},
      merged_cells: [],
      header_rows: 0,
    }
    // 复现生产判据：有 cells 且无 rows/programs/audit_rows
    const isGridOnly = !!(hd.cells && !hd.rows && !hd.programs && !hd.audit_rows)
    expect(isGridOnly).toBe(true) // ⇒ 没有豁免就会走只读兜底
  })

  it('confirmation-* 的同款豁免仍在（同族先例，删了说明有人在削弱该机制）', () => {
    const src = stripComments(readFileAt(RENDERER_REL))
    expect(/componentType\.value\.startsWith\('confirmation-'\)\s*\)\s*return false/.test(src)).toBe(
      true,
    )
  })
})
