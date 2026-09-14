/**
 * 完整性敏感清单逐循环覆盖面板守卫。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 14 / Requirements 5.5, 5.6, 5.7
 *
 * ## 本文件首要防的缺陷（本轮实证，不是假想）
 *
 * 恢复中断的实现时发现：后端 service / router、`apiPaths`、`commonApi`、以及 `.vue` 脚本侧
 * 的 ref / computed / 处理函数**全部就绪**，唯独模板里**没有面板本体** ——
 * `completenessPanelVisible` / `completenessScopeRows` / `setCompletenessScope` /
 * `revertCompletenessScope` / `completenessSourceLabel` / `completenessSaving` 在模板中
 * **0 引用**。点「逐循环设置 →」只是把一个没人读的 ref 置真，功能完全不存在，而
 * Volar / vitest / `get_diagnostics` / HEAD-swap **四层全绿**（SFC 模板表达式不参与 TS
 * 类型检查；脚本里声明但不被消费的绑定也不是错误）。
 *
 * 故判据 A 落在「每个脚本侧声明都要有**模板消费方**」上 —— 这是平台已登记的
 * 「additive 注入即死代码」的对偶形态：那次是新写的取数没有消费方，这次是新写的
 * 交互没有渲染宿主。
 *
 * ## 判据必须剥注释
 *
 * 修复时**刻意**在模板注释里保留了这六个标识符（记录缺陷成因），故一切「名字是否出现」
 * 类判据必须先 `stripComments`，否则会被自己的说明文字骗成绿（平台已多次踩到）。
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
const BE = path.join(ROOT, 'backend', 'app')

const P_TRIM_VUE = path.join(FE, 'views', 'ProcedureTrimming.vue')
const P_EXEMPTION = path.join(FE, 'components', 'workpaper', 'composables', 'completenessExemption.ts')
const P_COMMON_API = path.join(FE, 'services', 'commonApi.ts')
const P_API_PATHS = path.join(FE, 'services', 'apiPaths', 'workpaper.ts')
const P_ROUTER_PY = path.join(BE, 'routers', 'procedure_trim.py')
const P_CTX_PY = path.join(BE, 'services', 'trim_decision_context.py')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/**
 * 带字符串状态的注释剥离（`accept="image/*"` 里的 `/*` 不能当块注释起点）。
 * 同时剥 SFC 模板里的 `<!-- -->`。字符串字面量原样保留。
 */
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

/**
 * 截取具名函数的**函数体**（花括号配对 + 语句特征筛选）。
 *
 * 🔴 不能用「声明后第一个 `{`」—— 那个 `{` 可能是内联返回类型注解
 * （`function f(): Promise<{ a: X }> {`），截出来的"函数体"是那段类型，断言全在
 * 无关文本上求值。
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
        if (depth === 0) { end = i; break }
      }
    }
    if (end < 0) return ''
    const block = src.slice(open, end + 1)
    if (/\b(return|const|let|await|if|for|throw)\b/.test(block)) return block
    from = end + 1
  }
  return ''
}

/**
 * 截取 `const {name} = computed(...)` 的**整个实参区**（圆括号配对）。
 *
 * 🔴 泛型标注**不能**用 `<[^>]*>` 匹配：`computed<Record<string, boolean> | null>(` 的
 * `[^>]*` 会在 `Record<string, boolean>` 的第一个 `>` 处停下，整条正则不匹配 ⇒ 返回空串 ⇒
 * 后续断言以 `expected '' to contain …` 的形态**假红**（本文件首轮即因此打红一条）。
 * 正解 = 只锚 `const NAME = computed`，再取其后**第一个** `(`（泛型里不会有圆括号）。
 */
function computedArg(src: string, name: string): string {
  const m = src.match(new RegExp(`const\\s+${name}\\s*=\\s*computed\\b`))
  if (!m || m.index === undefined) return ''
  const open = src.indexOf('(', m.index + m[0].length)
  if (open < 0) return ''
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

const RAW = read(P_TRIM_VUE)
const CLEAN = stripComments(RAW)

/**
 * SFC 三段切分。
 *
 * 🔴 `</template>` 取 `<script setup` 之前的**最后一个** —— 本 SFC 有 20+ 个嵌套
 * `<template #default>` 插槽，第一个闭合标签在 L175 左右，按它切只能拿到 ~4% 的模板，
 * 判据 A 会在绝大部分模板上空转恒绿。
 */
function sfcSegments(clean: string) {
  const tplStart = clean.indexOf('<template>')
  const scStart = clean.indexOf('<script setup')
  const scEnd = clean.indexOf('</script>', scStart)
  expect(tplStart, '未找到 <template>').toBeGreaterThanOrEqual(0)
  expect(scStart, '未找到 <script setup').toBeGreaterThan(tplStart)
  const tplEnd = clean.lastIndexOf('</template>', scStart)
  expect(tplEnd, '未找到 </template>').toBeGreaterThan(tplStart)
  return {
    template: clean.slice(tplStart, tplEnd),
    script: clean.slice(scStart, scEnd),
    naiveTemplate: clean.slice(tplStart, clean.indexOf('</template>', tplStart)),
  }
}

const SEG = sfcSegments(CLEAN)

/** 平台默认标注措辞 —— 前后两侧交叉锁死的那个字面量。 */
const NOTICE = '使用平台默认，未经本项目确认'

/** Task 14 在脚本侧声明、且**必须**有模板消费方的标识符。 */
const TASK14_BINDINGS = [
  'completenessPanelVisible',
  'completenessScopeRows',
  'setCompletenessScope',
  'revertCompletenessScope',
  'completenessSourceLabel',
  'completenessSaving',
  'completenessDefaultNotice',
  'completenessOverrides',
  'openCompletenessPanel',
  'loadCompletenessOverrides',
] as const

// ═══════════════════════════════════════════════════════════════════════════
// helper 自检（防判据空转 / 假红）
// ═══════════════════════════════════════════════════════════════════════════
describe('helper 自检', () => {
  it('stripComments 剥 HTML 注释与 JS 注释，保留字符串字面量', () => {
    const s = '<!-- setCompletenessScope 只在注释里 -->\n<a accept="image/*" />\n// x\nconst y = "/*keep*/"'
    const out = stripComments(s)
    expect(out).not.toContain('setCompletenessScope')
    expect(out).toContain('accept="image/*"')
    expect(out).toContain('/*keep*/')
    expect(out).not.toContain('// x')
  })

  it('模板切分取「script 前最后一个 </template>」而非第一个', () => {
    const nested = (SEG.template.match(/<template\s+#/g) ?? []).length
    expect(nested, '未见嵌套 template 插槽，切分自检失去意义').toBeGreaterThan(5)
    expect(
      SEG.template.length,
      '正确切法未显著长于朴素切法 —— 切分可能退化，判据 A 会大面积空转',
    ).toBeGreaterThan(SEG.naiveTemplate.length * 2)
  })

  it('fnBody 跳过内联返回类型注解', () => {
    const fx = [
      'async function f(): Promise<{',
      '  a: any[]',
      '}> {',
      '  const x = 1',
      '  return x',
      '}',
    ].join('\n')
    expect(fnBody(fx, /async\s+function\s+f\b/)).toContain('const x = 1')
  })

  it('computedArg 对带泛型标注的 computed 也能截到实参区', () => {
    const fx = 'const r = computed<Record<string, boolean> | null>(() => resolveIt({ a: 1 }))'
    expect(computedArg(fx, 'r')).toContain('resolveIt')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 A：面板有渲染宿主（脚本侧声明必须被模板消费）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 A: 逐循环覆盖面板有渲染宿主（R5.5）', () => {
  /** 某标识符在**剥注释后**的模板里是否被真实消费。 */
  function consumedInTemplate(name: string): boolean {
    return new RegExp(`(?<![A-Za-z0-9_$])${name}(?![A-Za-z0-9_$])`).test(SEG.template)
  }

  function declaredInScript(name: string): boolean {
    return new RegExp(`\\b(?:const|let|function|async function)\\s+${name}\\b`).test(SEG.script)
  }

  it('扫描面非空（模板与脚本两段都切到了实体内容）', () => {
    expect(SEG.template.length).toBeGreaterThan(20000)
    expect(SEG.script.length).toBeGreaterThan(20000)
  })

  it.each(TASK14_BINDINGS)('%s 在 script setup 有声明', (name) => {
    expect(declaredInScript(name), `${name} 无声明（模板消费它会 ReferenceError）`).toBe(true)
  })

  it.each(TASK14_BINDINGS)('%s 被模板真实消费（有渲染宿主，不是死代码）', (name) => {
    expect(
      consumedInTemplate(name),
      `${name} 在模板中 0 引用 —— 脚本侧就绪但功能不存在；`
      + '四层检查（Volar / vitest / get_diagnostics / HEAD-swap）对此全绿，只有本判据能抓',
    ).toBe(true)
  })

  it('面板是真正的 el-dialog 且 v-model 绑到 completenessPanelVisible', () => {
    const dialog = SEG.template.match(/<el-dialog[\s\S]{0,400}?completenessPanelVisible/)
    expect(dialog, '未找到以 completenessPanelVisible 为 v-model 的 el-dialog').not.toBeNull()
    expect(SEG.template).toMatch(/v-model="completenessPanelVisible"/)
  })

  it('面板渲染逐循环行（遍历 completenessScopeRows 的表格）', () => {
    expect(SEG.template).toMatch(/:data="completenessScopeRows"/)
  })

  it('两个写入动作在模板上都有触发点（设为敏感 / 设为不敏感 / 撤销）', () => {
    const trueCall = /setCompletenessScope\(\s*row\s*,\s*true\s*\)/.test(SEG.template)
    const falseCall = /setCompletenessScope\(\s*row\s*,\s*false\s*\)/.test(SEG.template)
    expect(trueCall && falseCall, 'Y/N 双向表态必须都能点到（只给一个方向等于半个功能）').toBe(true)
    expect(SEG.template).toMatch(/revertCompletenessScope\(\s*row\s*\)/)
  })

  it('留痕（谁改的 / 何时改的）在面板上可见', () => {
    for (const f of ['updatedByName', 'updatedAt']) {
      expect(SEG.template, `${f} 未渲染 —— 覆盖动作的留痕看不到，复核无从评价`).toContain(f)
    }
  })

  it('写入按钮受 canManage 门控（无权时禁用而不是静默 return）', () => {
    const cell = SEG.template.match(/setCompletenessScope[\s\S]{0,200}/)?.[0] ?? ''
    expect(cell).toContain('canManage')
    const revert = SEG.template.match(/:disabled="[^"]*"[\s\S]{0,120}revertCompletenessScope/)
    expect(revert, '撤销按钮未做门控').not.toBeNull()
  })

  it('反向自检：不存在的名字必须被判为「无宿主」', () => {
    expect(consumedInTemplate('completenessPanelVisibleXX')).toBe(false)
    expect(declaredInScript('completenessPanelVisibleXX')).toBe(false)
    // 前缀不得误命中：`completeness` 是上面所有名字的公共前缀，不能靠它蒙过判据
    expect(
      new RegExp('(?<![A-Za-z0-9_$])completenessPanelVisible(?![A-Za-z0-9_$])').test('xcompletenessPanelVisibleY'),
    ).toBe(false)
  })

  it('反向自检：注释里的标识符不算宿主（stripComments 必须生效）', () => {
    // 源码注释里刻意留了这些名字用于记录缺陷成因；raw 侧命中数必须多于 clean 侧
    const raw = sfcSegments(RAW.replace(/<!--[\s\S]*?-->/g, m => m)) // 不剥，仅切分
    const rawTpl = raw.template
    const cnt = (s: string, n: string) =>
      (s.match(new RegExp(`(?<![A-Za-z0-9_$])${n}(?![A-Za-z0-9_$])`, 'g')) ?? []).length
    const rawTotal = TASK14_BINDINGS.reduce((a, n) => a + cnt(rawTpl, n), 0)
    const cleanTotal = TASK14_BINDINGS.reduce((a, n) => a + cnt(SEG.template, n), 0)
    expect(
      rawTotal,
      '注释里已不再提这些标识符 —— 剥注释这层防护无对象可防，请确认判据 A 未退化成空转',
    ).toBeGreaterThan(cleanTotal)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 B：判据单一真源（R5.6 / Property 9）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 B: 平台默认标注只来自 resolveCompletenessExemption', () => {
  const ROWS_ARG = computedArg(SEG.script, 'completenessScopeRows')
  const NOTICE_ARG = computedArg(SEG.script, 'completenessDefaultNotice')

  it('扫描面非空（两个 computed 的实参区都截到了）', () => {
    expect(ROWS_ARG.length, 'completenessScopeRows 实参区未截到').toBeGreaterThan(200)
    expect(NOTICE_ARG.length, 'completenessDefaultNotice 实参区未截到').toBeGreaterThan(80)
  })

  it('行由 COMPLETENESS_CYCLE_RULES 派生（不自造循环清单）', () => {
    expect(ROWS_ARG).toContain('COMPLETENESS_CYCLE_RULES')
    expect(ROWS_ARG).toContain('resolveCompletenessExemption')
  })

  it('结论 / 来源 / 标注三项全取纯函数输出，不在视图里重算', () => {
    expect(ROWS_ARG).toMatch(/sensitive:\s*resolved\.exempt/)
    expect(ROWS_ARG).toMatch(/source:\s*resolved\.source/)
    expect(ROWS_ARG).toMatch(/usingPlatformDefault:\s*resolved\.usingPlatformDefault/)
  })

  it('标注触发条件只看 usingPlatformDefault（不看「覆盖表是否为空」这类第二判据）', () => {
    expect(NOTICE_ARG).toMatch(/usingPlatformDefault/)
    expect(
      /overrides\.value\s*[!=]==?\s*\[\]|\.length\s*===?\s*0\s*\)\s*return\s*\{/.test(NOTICE_ARG),
      '出现了「覆盖表为空即全部平台默认」这类等价判据 —— 与 Property 9 分叉时无从裁决',
    ).toBe(false)
  })

  it('循环级视图固定传「认定缺失」（认定级判据是逐科目的，不同层）', () => {
    expect(ROWS_ARG).toMatch(/completenessRmm:\s*null/)
    expect(ROWS_ARG).toMatch(/completenessSpecial:\s*false/)
  })

  it('标注措辞与 completenessExemption.ts 的 cycle_default 分支交叉锁死', () => {
    expect(SEG.script, '裁剪页未声明 PLATFORM_DEFAULT_NOTICE 常量').toContain('PLATFORM_DEFAULT_NOTICE')
    expect(SEG.script).toContain(NOTICE)
    const pure = stripComments(read(P_EXEMPTION))
    expect(
      pure.includes(NOTICE),
      `纯函数侧的 cycle_default rationale 不再以「${NOTICE}」开头 —— `
      + '两侧会用两套说法描述同一件事（复核视图与判据说明分叉）',
    ).toBe(true)
    // 该措辞只应出现在 cycle_default 分支（唯一置 usingPlatformDefault 为真的分支）
    const idx = pure.indexOf(NOTICE)
    expect(pure.slice(Math.max(0, idx - 400), idx)).toContain('cycle_default')
  })

  it('决策内核入参仍走后端下发的 completeness_override（面板不喂第二份覆盖表）', () => {
    const build = fnBody(SEG.script, /function\s+buildAndDecide\b/)
    expect(build.length, 'buildAndDecide 函数体未截到').toBeGreaterThan(200)
    expect(build).toContain('ctx.completeness_override')
    expect(
      build.includes('completenessOverrideMap'),
      '决策内核吃了面板自己的覆盖表 —— 与后端下发的那份构成双真源',
    ).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 C：未知态不退化为「全部平台默认」（R5.6 的如实标注）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 C: 读取失败保持未知，不谎报实质结论', () => {
  const LOAD = fnBody(SEG.script, /async\s+function\s+loadCompletenessOverrides\b/)

  it('扫描面非空', () => {
    expect(LOAD.length).toBeGreaterThan(120)
    expect(LOAD).toContain('fetchCompletenessScopeOverrides')
  })

  it('ref 初值为 null（不是 []）', () => {
    expect(SEG.script).toMatch(
      /const\s+completenessOverrides\s*=\s*ref<[^>]*>\(\s*null\s*\)/,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    )
  })

  it('catch 分支把值设回 null 且不写空数组', () => {
    const catchBlock = LOAD.match(/catch\s*\([\s\S]*?\}\s*$/)?.[0] ?? LOAD.slice(LOAD.indexOf('catch'))
    expect(catchBlock).toMatch(/completenessOverrides\.value\s*=\s*null/)
    expect(
      /completenessOverrides\.value\s*=\s*\[\s*\]/.test(catchBlock),
      '失败退化成空数组 —— 11 个循环会全被标注「未经本项目确认」，而真因是接口读不到',
    ).toBe(false)
    expect(catchBlock).toContain('completenessError')
  })

  it('标注 computed 在未知态早退返回 null', () => {
    const arg = computedArg(SEG.script, 'completenessDefaultNotice')
    expect(arg).toMatch(/completenessOverrides\.value\s*===\s*null\s*\)\s*return\s+null/)
  })

  it('状态条把未知态与「已逐循环确认」「使用平台默认」三态分开渲染', () => {
    expect(SEG.template).toMatch(/completenessOverrides\s*===\s*null/)
    expect(SEG.template).toContain('状态未知')
    expect(SEG.template).toContain(NOTICE.slice(0, 6))
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 D：理由必填（R5.5）与写入后双刷新
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 D: 理由必填 + 写入后刷新面板与判据上下文', () => {
  const SET = fnBody(SEG.script, /async\s+function\s+setCompletenessScope\b/)
  const REVERT = fnBody(SEG.script, /async\s+function\s+revertCompletenessScope\b/)

  it('扫描面非空', () => {
    expect(SET.length).toBeGreaterThan(300)
    expect(REVERT.length).toBeGreaterThan(200)
  })

  it('弹窗有 inputValidator（交互层第一道）', () => {
    expect(SET).toContain('inputValidator')
    expect(SET).toContain('ElMessageBox.prompt')
  })

  it('发请求前有独立的空理由早退（程序化调用也拦住）', () => {
    const idxCheck = SET.search(/if\s*\(\s*!reason\s*\)/)
    const idxSave = SET.indexOf('saveCompletenessScopeOverride')
    expect(idxCheck, '缺独立的空理由判断 —— 只靠弹窗校验会被别的调用方式绕过').toBeGreaterThan(-1)
    expect(idxSave).toBeGreaterThan(-1)
    expect(
      idxCheck < idxSave,
      '空理由判断在发请求之后 —— 无理由的覆盖会先落库再被提示',
    ).toBe(true)
  })

  it('写入与撤销都同时刷新面板列表与判据上下文', () => {
    for (const [name, body] of [['setCompletenessScope', SET], ['revertCompletenessScope', REVERT]] as const) {
      expect(body, `${name} 未刷新面板列表`).toContain('loadCompletenessOverrides()')
      expect(
        body.includes('loadTrimContext('),
        `${name} 未刷新判据上下文 —— 会出现「面板说已确认、裁剪判据仍按平台默认」`,
      ).toBe(true)
    }
  })

  it('两个写入动作都有 canManage 前置与 finally 收尾（避免行级 loading 卡死）', () => {
    for (const body of [SET, REVERT]) {
      expect(body).toMatch(/if\s*\(\s*!canManage\.value\s*\)\s*return/)
      expect(body).toContain('finally')
      expect(body).toMatch(/completenessSaving\.value\s*=\s*null/)
    }
  })

  it('撤销走 clear（DELETE 删行），不是写空值', () => {
    expect(REVERT).toContain('clearCompletenessScopeOverride')
    expect(
      REVERT.includes('saveCompletenessScopeOverride'),
      '撤销复用了写入接口 —— 会留一行既非表态也非缺失的脏记录',
    ).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 E：跨前后端交叉锁死（键空间 / 路径 / 方法 / 维度名）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 E: 跨前后端交叉锁死', () => {
  const API = stripComments(read(P_COMMON_API))
  const PATHS = stripComments(read(P_API_PATHS))
  const ROUTER = read(P_ROUTER_PY)
  const CTX = read(P_CTX_PY)

  it('三个取数函数都经 apiPaths 访问器，不裸拼 URL', () => {
    for (const fn of [
      'fetchCompletenessScopeOverrides',
      'saveCompletenessScopeOverride',
      'clearCompletenessScopeOverride',
    ]) {
      const body = fnBody(API, new RegExp(`export\\s+async\\s+function\\s+${fn}\\b`))
      expect(body.length, `${fn} 函数体未截到`).toBeGreaterThan(60)
      expect(body).toMatch(/P_prt\.trimCompletenessScope/)
      expect(
        /http\.\w+\(\s*[`'"]\/api\//.test(body),
        `${fn} 里出现裸 URL —— 后端改路径时前端不会被守卫抓到`,
      ).toBe(false)
    }
  })

  it('HTTP 方法与后端一致（GET 读 / PUT 写 / DELETE 撤销）', () => {
    const g = fnBody(API, /export\s+async\s+function\s+fetchCompletenessScopeOverrides\b/)
    const p = fnBody(API, /export\s+async\s+function\s+saveCompletenessScopeOverride\b/)
    const d = fnBody(API, /export\s+async\s+function\s+clearCompletenessScopeOverride\b/)
    expect(g).toContain('http.get')
    expect(p).toContain('http.put')
    expect(d).toContain('http.delete')
    expect(ROUTER).toContain('@router.get("/{pid}/procedure-trim/completeness-scope")')
    expect(ROUTER).toContain('@router.put("/{pid}/procedure-trim/completeness-scope")')
    expect(ROUTER).toContain('@router.delete("/{pid}/procedure-trim/completeness-scope/{cycle}")')
  })

  it('apiPaths 的路径字面量与后端 router path 逐字相等', () => {
    const base = PATHS.match(/trimCompletenessScope:\s*\(pid: string\)\s*=>\s*`([^`]+)`/)?.[1]
    const item = PATHS.match(/trimCompletenessScopeItem:[\s\S]{0,120}?`([^`]+)`/)?.[1]
    expect(base, '未找到 trimCompletenessScope 访问器').toBeTruthy()
    expect(item, '未找到 trimCompletenessScopeItem 访问器').toBeTruthy()
    // 前端模板串 → 后端路径形态（${pid} → {pid}，${encodeURIComponent(cycle)} → {cycle}）
    const norm = (s: string) => s
      .replace(/\$\{pid\}/g, '{pid}')
      .replace(/\$\{encodeURIComponent\(cycle\)\}/g, '{cycle}')
      .replace(/\$\{cycle\}/g, '{cycle}')
    expect(norm(base!)).toBe('/api/projects/{pid}/procedure-trim/completeness-scope')
    expect(norm(item!)).toBe('/api/projects/{pid}/procedure-trim/completeness-scope/{cycle}')
  })

  it('写入请求体三键与后端 pydantic 模型一致', () => {
    const body = fnBody(API, /export\s+async\s+function\s+saveCompletenessScopeOverride\b/)
    expect(body).toMatch(/\{\s*\n?\s*cycle,\s*sensitive,\s*reason,?\s*\n?\s*\}/)
    const model = ROUTER.slice(ROUTER.indexOf('class CompletenessScopeOverrideRequest'))
      .slice(0, 900)
    for (const f of ['cycle', 'sensitive', 'reason']) {
      expect(model, `后端模型缺字段 ${f}（pydantic 会静默忽略前端传的该键）`).toContain(f)
    }
    expect(model, '后端未把理由设为必填').toMatch(/reason:\s*str\s*=\s*Field\(min_length=1/)
  })

  it('前端不出现 B50-T3-cscope- 键字面量（键由后端按常量拼）', () => {
    for (const [name, src] of [['ProcedureTrimming.vue', CLEAN], ['commonApi.ts', API]] as const) {
      expect(
        src.includes('B50-T3-cscope-'),
        `${name} 代码里出现了 checklist 键字面量 —— 前端另造键会与后端常量漂移，`
        + '且两侧各自的测试都不会打红',
      ).toBe(false)
    }
    // 反向：后端确实以常量形式持有该键（证明上一条不是「这个键根本不存在」的空转）
    expect(CTX).toContain('COMPLETENESS_SCOPE_ITEM_PREFIX')
    expect(CTX).toContain('B50-T3-cscope-')
  })

  it('降级维度名与后端 DIM_COMPLETENESS_OVERRIDE 字面量一致', () => {
    const dim = CTX.match(/DIM_COMPLETENESS_OVERRIDE\s*=\s*"([^"]+)"/)?.[1]
    expect(dim, '后端未定义 DIM_COMPLETENESS_OVERRIDE').toBeTruthy()
    expect(dim).toBe('completeness_override')
    expect(
      new RegExp(`dim\\s*===\\s*'${dim}'`).test(SEG.script),
      `裁剪页的降级分支未按 '${dim}' 判断 —— 该分支永不命中，降级标注会落到兜底文案上`,
    ).toBe(true)
    expect(API, 'commonApi 的维度取值域未含该维度').toContain(`'${dim}'`)
  })
})
