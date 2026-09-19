/**
 * B50 完成度徽标「单一真源」守卫。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 4 / Requirements 2.5, 2.6, 2.7
 * Property 24（B50 完成度三态与前后端同口径）。
 *
 * ## 为什么要源码级断言
 *
 * 徽标出现在两处：B50 底稿页（`GtB50RiskAssessment.vue`）与裁剪页
 * （`ProcedureTrimming.vue`）。两处若各自实现一遍「怎么算已评估」，一定会漂移 ——
 * 而漂移的表现是「同一项目在两个页面显示不同完成度」，用户无从判断哪个对。
 *
 * 故本守卫断言：两处都从 `b50Completeness.ts` 导入同一组函数/常量，且**都不含**
 * 自行判定 RMM 是否填写的逻辑（不出现自造的 `'H'|'M'|'L'` 判定 + 计数循环）。
 *
 * ## 判据必须剥注释
 *
 * 本文件与被测两个 SFC 的注释里都会写「不得自行聚合」这类说明文字，裸子串匹配会把
 * 说明文字数成真实实现（平台已多次踩这个坑）。故一律先 stripComments 再判。
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

// ── 双哨兵向上找仓库根（单哨兵不稳，目录做哨兵会被历史空目录骗停）──
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵 audit-platform/frontend/package.json + backend/app/main.py）')
}

const ROOT = repoRoot()
const FE = path.join(ROOT, 'audit-platform', 'frontend', 'src')

const P_PURE = path.join(FE, 'components', 'workpaper', 'composables', 'b50Completeness.ts')
const P_B50_VUE = path.join(FE, 'components', 'workpaper', 'GtB50RiskAssessment.vue')
const P_TRIM_VUE = path.join(FE, 'views', 'ProcedureTrimming.vue')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/**
 * 带字符串状态的注释剥离（`accept="image/*"` 里的 `/*` 不能当块注释起点）。
 *
 * 返回剥掉 `//` 行注释与 `/* *​/` 块注释后的源码；字符串字面量原样保留
 * （字面量里可能是真实的判定值，不能剥）。
 */
/**
 * 截取具名函数的**函数体**（花括号配对）。
 *
 * 🔴 不能用「声明后第一个 `{`」定位 —— 平台已多次踩到：那个 `{` 可能是**内联返回
 * 类型注解**（`function f(): Promise<{ a: X }> {`）或参数的内联类型字面量
 * （`function f(p: { a: X })`），截出来的"函数体"其实是那段类型，后续断言全在无关
 * 文本上求值（本守卫首轮就因此把正确实现打红）。
 *
 * 做法：从声明处起逐个候选 `{` 做配对，取第一个**含语句特征**的块。
 */
function fnBody(src: string, decl: RegExp): string {
  const m = src.match(decl)
  if (!m || m.index === undefined) return ''
  let from = m.index + m[0].length
  for (let guard = 0; guard < 12; guard += 1) {
    const open = src.indexOf('{', from)
    if (open < 0) return ''
    let depth = 0
    let end = -1
    for (let i = open; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1
      else if (src[i] === '}') {
        depth -= 1
        if (depth === 0) {
          end = i
          break
        }
      }
    }
    if (end < 0) return ''
    const block = src.slice(open, end + 1)
    // 语句特征：类型字面量里不会出现这些
    if (/\b(return|const|let|await|if|for|throw)\b/.test(block)) return block
    from = end + 1
  }
  return ''
}

/**
 * 截取 `const {name} = computed(...)` 的**整个实参区**（圆括号配对）。
 *
 * 🔴 为什么不复用 `fnBody`：computed 有两种形态 —— 带花括号体
 * （`computed(() => { ... })`）与**表达式体**（`computed(() => f({ a: b }))`）。
 * 后者的第一个 `{` 是对象字面量而非函数体，`fnBody` 的「含语句特征」筛选会跳过它、
 * 一路找到别的函数体上去 ⇒ 断言落在无关文本上。圆括号配对对两种形态都成立。
 *
 * 这条 helper 的存在本身是为了抓住一类真实变异：把 computed 整体换成写死值时，
 * 纯函数标识符**仍留在 import 行里** ⇒ 只断言 `src.toContain('resolveB50Completeness')`
 * 会静默通过（本守卫首轮变异检验 M8/M9 即因此 GREEN）。
 */
function computedArg(src: string, name: string): string {
  const decl = new RegExp(`const\\s+${name}\\s*=\\s*computed\\s*\\(`)
  const m = src.match(decl)
  if (!m || m.index === undefined) return ''
  const open = m.index + m[0].length - 1
  let depth = 0
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === '(') depth += 1
    else if (src[i] === ')') {
      depth -= 1
      if (depth === 0) return src.slice(open, i + 1)
    }
  }
  return ''
}

function stripComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') { out += n ?? ''; i += 2; continue }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i += 1; continue }
    if (c === '/' && n === '/') { while (i < src.length && src[i] !== '\n') i += 1; continue }
    if (c === '/' && n === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    if (c === '<' && src.startsWith('<!--', i)) {
      const end = src.indexOf('-->', i)
      i = end < 0 ? src.length : end + 3
      continue
    }
    out += c
    i += 1
  }
  return out
}

describe('fnBody 自检（防「第一个 { 命中返回类型注解」）', () => {
  it('跳过内联返回类型注解，截到真正的函数体', () => {
    const fixture = [
      'export async function f(pid: string): Promise<{',
      '  a: any[]',
      '  b: any[]',
      '}> {',
      '  const x = call(pid)',
      '  return x',
      '}',
    ].join('\n')
    const body = fnBody(fixture, /export\s+async\s+function\s+f\b/)
    expect(body).toContain('const x = call(pid)')
    // 反向：朴素「第一个 {」会截到类型字面量（证明该 helper 有存在意义）
    const naive = fixture.slice(fixture.indexOf('{'), fixture.indexOf('}') + 1)
    expect(naive).toContain('a: any[]')
    expect(naive).not.toContain('const x')
  })

  it('跳过参数的内联类型字面量', () => {
    const fixture = [
      'function g(p: { k: string }) {',
      '  return p.k',
      '}',
    ].join('\n')
    expect(fnBody(fixture, /function\s+g\b/)).toContain('return p.k')
  })

  it('声明不存在时返回空串（不抛，也不静默匹配别的函数）', () => {
    expect(fnBody('const a = 1', /function\s+zzz\b/)).toBe('')
  })
})

describe('stripComments 自检（防判据空转）', () => {
  it('剥掉行注释与块注释，保留字符串字面量', () => {
    const s = stripComments(`const a = 'H' // 注释里写 'M'\n/* 块里写 'L' */\nconst b = "keep"`)
    expect(s).toContain("'H'")
    expect(s).toContain('"keep"')
    expect(s).not.toContain('注释里写')
    expect(s).not.toContain('块里写')
  })

  it('不把 accept="image/*" 当块注释起点', () => {
    const s = stripComments(`<input accept="image/*" />\nconst x = 1`)
    expect(s).toContain('const x = 1')
  })

  it('剥掉 HTML 注释（SFC 模板里的说明文字）', () => {
    const s = stripComments(`<!-- 说明：不得自行聚合 -->\n<div>keep</div>`)
    expect(s).not.toContain('不得自行聚合')
    expect(s).toContain('<div>keep</div>')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 24：两处徽标同源
// ═══════════════════════════════════════════════════════════════════════════
describe('Property 24: B50 完成度徽标两处同源', () => {
  it('纯函数模块导出完成度判定 + 三态标签', () => {
    const src = stripComments(read(P_PURE))
    for (const sym of [
      'resolveB50Completeness',
      'normalizeFromReader',
      'normalizeFromMatrixRows',
      'B50_COMPLETENESS_LABEL',
      'B50_COMPLETENESS_TAG_TYPE',
      'B50_COMPLETENESS_HINT',
    ]) {
      expect(new RegExp(`export\\s+(?:function|const)\\s+${sym}\\b`).test(src), `缺少导出 ${sym}`).toBe(true)
    }
  })

  it('纯函数模块零 Vue 依赖（可在任意上下文调用）', () => {
    const src = stripComments(read(P_PURE))
    expect(/from\s+['"]vue['"]/.test(src), 'b50Completeness.ts 不得依赖 vue').toBe(false)
  })

  it('B50 底稿页从纯函数模块 import（不自造判定）', () => {
    const src = stripComments(read(P_B50_VUE))
    expect(/from\s+['"]\.\/composables\/b50Completeness['"]/.test(src), 'B50 页未 import b50Completeness').toBe(true)
    expect(src).toContain('resolveB50Completeness')
    expect(src).toContain('normalizeFromMatrixRows')
    // 🔴 上面两条只证明"标识符出现过" —— 把 computed 整体换成写死值时标识符仍留在
    // import 行里，弱断言会静默通过（首轮变异检验 M9 即因此 GREEN）。故必须断言
    // computed 的**实参区内**真的调用了这两个函数。
    const arg = computedArg(src, 'b50Completeness')
    expect(arg, 'B50 页未见 b50Completeness computed').not.toBe('')
    expect(arg, 'B50 页的 computed 未调用 resolveB50Completeness').toContain(
      'resolveB50Completeness(',
    )
    expect(arg, 'B50 页的 computed 未经 normalizeFromMatrixRows 归一（手写内联映射即双真源）')
      .toContain('normalizeFromMatrixRows(')
  })

  it('裁剪页从纯函数模块 import（不自造判定）', () => {
    const src = stripComments(read(P_TRIM_VUE))
    expect(
      /from\s+['"]@\/components\/workpaper\/composables\/b50Completeness['"]/.test(src),
      '裁剪页未 import b50Completeness',
    ).toBe(true)
    expect(src).toContain('resolveB50Completeness')
    expect(src).toContain('normalizeFromReader')
    // 同上：断言 computed 实参区内真有调用（防「把 computed 换成写死 completed」逃逸，
    // 那会让裁剪页永远显示"已完成"、风险维度判据被静默旁路 —— 首轮变异 M8 即此形态）。
    const arg = computedArg(src, 'b50Completeness')
    expect(arg, '裁剪页未见 b50Completeness computed').not.toBe('')
    expect(arg, '裁剪页的 computed 未调用 resolveB50Completeness').toContain(
      'resolveB50Completeness(',
    )
    expect(arg, '裁剪页的 computed 未经 normalizeFromReader 归一').toContain(
      'normalizeFromReader(',
    )
    // 未知态必须由 computed 自己短路（null 直返），不能靠纯函数把 null 当空数组处理 ——
    // 后者会把「读不到 B50」显示成「未开始」（谎报，Requirement 2.6）。
    expect(arg, '裁剪页 computed 未对未知态短路').toMatch(/===\s*null\s*\)\s*return\s+null/)
  })

  it('两处都不自行实现「RMM 是否已填」的判定', () => {
    // 自造判定的特征 = 在 SFC 里直接对三个等级做集合/数组判定。
    // 合法用法（RISK_COLOR_MAP['H'] 之类按等级取色）不匹配该模式。
    const bad = /\[\s*['"]H['"]\s*,\s*['"]M['"]\s*,\s*['"]L['"]\s*\]\s*\.\s*(?:includes|indexOf)/
    for (const p of [P_B50_VUE, P_TRIM_VUE]) {
      const src = stripComments(read(p))
      expect(bad.test(src), `${path.basename(p)} 出现自造的 RMM 等级判定`).toBe(false)
    }
  })

  it('两处标签文字都读同一常量（不写死中文三态）', () => {
    for (const p of [P_B50_VUE, P_TRIM_VUE]) {
      const src = stripComments(read(p))
      expect(src).toContain('B50_COMPLETENESS_LABEL')
      // 写死三态中文即双真源
      for (const lit of ['未开始', '部分完成', '已完成']) {
        const inTemplateLiteral = new RegExp(`['"\`]${lit}['"\`]`).test(src)
        expect(inTemplateLiteral, `${path.basename(p)} 写死了三态中文「${lit}」`).toBe(false)
      }
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Requirements 2.5–2.7：裁剪页徽标的可达性与后果说明
// ═══════════════════════════════════════════════════════════════════════════
describe('Requirements 2.5-2.7: 裁剪页徽标与跳转', () => {
  const src = stripComments(read(P_TRIM_VUE))

  it('徽标条真实渲染在模板里', () => {
    expect(/class="gt-proc-b50-bar"/.test(src), '徽标条未渲染').toBe(true)
  })

  it('tooltip 说明风险联动依赖 B50（让审计师理解未填后果）', () => {
    // 必须出现"风险"与"B50"同时出现的提示文案（不只显示一个状态词）
    const hasTip = /el-tooltip[\s\S]{0,400}?风险[\s\S]{0,200}?B50|el-tooltip[\s\S]{0,400}?B50[\s\S]{0,200}?风险/.test(src)
    expect(hasTip, '徽标缺少「风险联动依赖 B50」的 tooltip 说明').toBe(true)
  })

  it('非 completed 时提供跳转 B50 的入口', () => {
    expect(src).toContain('goToB50')
    // 跳转按钮受状态门控（completed 时不显示）
    //
    // 🔴 `!?` 不可省：模板里写的是 `b50Completeness!.state`（TS 非空断言）。首版正则写
    //    `b50Completeness\.state`，门控**明明存在**却匹配不到 ⇒ 以「跳转入口未按状态门控」
    //    的形态**假红**（Task 14 恢复实现时定性）。这是平台记过的同一类守卫缺陷：判据的
    //    扫描面与它声称覆盖的写法不一致时，红/绿两种结果都不可信。
    const GATE = /b50Completeness!?\.state\s*!==\s*['"]completed['"]/
    expect(GATE.test(src), '跳转入口未按状态门控').toBe(true)
    // 反向自检：两种写法都要落进扫描面（防后续会话把 `!?` 删掉后本条重新假红）
    expect(GATE.test("b50Completeness.state !== 'completed'")).toBe(true)
    expect(GATE.test("b50Completeness!.state !== 'completed'")).toBe(true)
    // 反向自检：换成 `===` 或换个字段就不该命中（证明判据不是「含这几个字就算过」）
    expect(GATE.test("b50Completeness!.state === 'completed'")).toBe(false)
    expect(GATE.test("b50Completeness!.importedCount !== 'completed'")).toBe(false)
  })

  it('跳转走 router 且带 wp_code=B50（不硬编码底稿 UUID）', () => {
    const m = src.match(/function\s+goToB50\s*\([^)]*\)\s*\{/)
    expect(m, '未找到 goToB50 定义').not.toBeNull()
    const start = src.indexOf(m![0])
    // 花括号配对截函数体（禁固定字符窗口 —— 会越界到下一个函数）
    let depth = 0
    let i = start + m![0].length - 1
    let end = -1
    for (; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1
      else if (src[i] === '}') {
        depth -= 1
        if (depth === 0) { end = i; break }
      }
    }
    expect(end, 'goToB50 函数体未闭合').toBeGreaterThan(start)
    const body = src.slice(start, end)
    expect(body).toContain('router.push')
    expect(/wp_code:\s*['"]B50['"]/.test(body), '跳转未带 wp_code=B50').toBe(true)
  })

  it('加载失败保持「未知」而非退化成 not_started（否则会谎报"未开始"）', () => {
    // b50Accounts 三态：null = 未知
    expect(/b50Accounts\s*=\s*ref<[^>]*\|\s*null>\(null\)/.test(src), 'b50Accounts 未声明为三态 ref').toBe(true)

    // 🔴 只断言 ref 声明形态**抓不住** catch 分支里退化成 `[]`（变异检验 M7 实测 GREEN）。
    // 空数组会让 resolveB50Completeness 返回 not_started ⇒ 请求失败被谎报成「B50 未开始」，
    // 而审计师据此以为"去填 B50 就能用风险维度"，实际是接口坏了。故必须断言 catch 分支置 null。
    const load = fnBody(src, 'loadB50Status')
    expect(load, '未找到 loadB50Status 函数体').not.toBe('')
    const catchBlock = load.slice(load.indexOf('catch'))
    expect(catchBlock, 'loadB50Status 无 catch 分支').toContain('catch')
    expect(
      /b50Accounts\.value\s*=\s*null/.test(catchBlock),
      'loadB50Status 的 catch 分支未把 b50Accounts 置 null（退化成 [] 会谎报「未开始」）',
    ).toBe(true)
    expect(
      /b50Accounts\.value\s*=\s*\[\s*\]/.test(catchBlock),
      'loadB50Status 的 catch 分支把 b50Accounts 置成了空数组',
    ).toBe(false)
    expect(src).toContain('b50Loaded')
  })

  it('进入页面即加载（不依赖先打开其他抽屉）', () => {
    const idx = src.lastIndexOf('onMounted(')
    expect(idx).toBeGreaterThan(0)
    // 🔴 函数名以生产实现为准（`loadB50Status`）。首版守卫按 spec 措辞猜成
    // `loadB50Accounts()` → 断言恒红而实现完全正确，正是「基线/期望值必须由实测
    // 得出、禁按『应该叫什么』写」那条铁律的又一实例。
    expect(src.slice(idx)).toContain('loadB50Status()')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 取数路径：走 apiPaths + commonApi，不硬编码 URL
// ═══════════════════════════════════════════════════════════════════════════
describe('取数路径收敛', () => {
  it('裁剪页经 commonApi 取数，不在组件里拼 URL', () => {
    const src = stripComments(read(P_TRIM_VUE))
    expect(src).toContain('fetchB50RiskRows')
    expect(/['"]\/api\/b60\/b50-risk-rows['"]/.test(src), '裁剪页硬编码了 B50 端点 URL').toBe(false)
  })

  it('commonApi 的取数函数走 apiPaths 访问器', () => {
    const src = stripComments(read(path.join(FE, 'services', 'commonApi.ts')))
    const body = fnBody(src, 'fetchB50RiskRows')
    expect(body, '未找到 fetchB50RiskRows 的函数体').not.toBe('')
    expect(body).toContain('b50RiskRows')
    expect(/['"]\/api\/b60/.test(body), 'commonApi 里硬编码了 URL').toBe(false)
  })

  it('fnBody 自检：跳过内联返回类型注解，截到真正的函数体', () => {
    // 🔴 这条自检存在的理由：`fetchB50RiskRows` 的签名是
    //     export async function fetchB50RiskRows(pid: string): Promise<{ ... }> {
    // 「声明后第一个 `{`」命中的是 **返回类型字面量** `Promise<{...}>`，截出来的
    // "函数体"是那段类型 ⇒ 上一条断言会以「函数体里没有 b50RiskRows」的形态假红，
    // 而生产代码完全正确。故 fnBody 必须按「含语句特征的花括号块」定位。
    const fixture = [
      'export async function demoFn(pid: string): Promise<{',
      '  a: any[]',
      '  b: any[]',
      '}> {',
      '  const x = P_risk.marker()',
      '  return x',
      '}',
    ].join('\n')
    const body = fnBody(fixture, 'demoFn')
    expect(body).toContain('P_risk.marker()')
    // 反向：朴素实现（取第一个 `{`）会截到类型字面量，拿不到 marker
    const naiveStart = fixture.indexOf('{', fixture.indexOf('demoFn'))
    const naive = fixture.slice(naiveStart, fixture.indexOf('}', naiveStart) + 1)
    expect(naive).not.toContain('P_risk.marker()')
  })

  it('apiPaths 登记了 b50RiskRows 且指向 b60-data-pull 端点', () => {
    const src = stripComments(read(path.join(FE, 'services', 'apiPaths', 'system.ts')))
    const m = src.match(/b50RiskRows:\s*\([^)]*\)\s*=>\s*`([^`]+)`/)
    expect(m, 'apiPaths 未登记 b50RiskRows').not.toBeNull()
    expect(m![1]).toBe('/api/b60/b50-risk-rows')
  })
})
