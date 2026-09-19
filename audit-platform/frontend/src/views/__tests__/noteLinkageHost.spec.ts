/**
 * 附注反向联动的**渲染宿主 + 单一真源**守卫。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 21 / Requirements 13.1~13.7
 *
 * ## 本文件首要防的两个缺陷
 *
 * **（1）脚本侧齐备而模板无宿主。** Task 14 已在同一个 `.vue` 上踩过一次：service /
 * router / `apiPaths` / `commonApi` / `ref` / `computed` / 处理函数全部就绪，唯独模板里
 * 没有面板本体 ⇒ 点按钮只把一个没人读的 ref 置真，功能完全不存在，而 Volar / vitest /
 * `get_diagnostics` / HEAD-swap **四层全绿**（SFC 模板表达式不参与 TS 类型检查；脚本里
 * 声明而不被消费的绑定也不是错误）。故判据 A 落在「每个脚本侧声明都要有**模板消费方**」。
 *
 * **（2）前端另建一份"不适用"判定。** 附注侧的不适用真源只有
 * `disclosure_notes.is_empty`，判定只有 `note_content_utils.note_has_data`。前端若自己
 * 判"这个章节该不该标"，就会与后端派生结果分叉 —— 而且**两边各自的测试都会全绿**，
 * 只有交付件（Word）与界面（附注树）对不上才暴露。故判据 B 断言前端只**展示**后端派生
 * 的桶，不自己算。
 *
 * ## 判据必须剥注释
 *
 * 实现时**刻意**在模板注释与 docstring 里保留了这些标识符（记录缺陷成因与设计理由），
 * 故一切「名字是否出现」类判据必须先 `stripComments`，并配反向自检断言 raw 命中 > clean。
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
const P_COMMON_API = path.join(FE, 'services', 'commonApi.ts')
const P_API_PATHS = path.join(FE, 'services', 'apiPaths', 'workpaper.ts')
const P_ROUTER_PY = path.join(BE, 'routers', 'procedure_trim.py')
const P_LINKAGE_PY = path.join(BE, 'services', 'procedure_trim_note_linkage.py')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/** 带字符串状态的注释剥离（`accept="image/*"` 里的 `/*` 不能当块注释起点）+ 剥 `<!-- -->`。 */
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

function matchBrace(src: string, open: number): number {
  let depth = 0
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}') {
      depth -= 1
      if (depth === 0) return i
    }
  }
  return -1
}

/**
 * 截取具名函数的**函数体**（花括号配对）。
 *
 * 🔴 不能用「声明后第一个 `{`」—— 那个 `{` 可能是内联返回类型注解
 * （`function f(): Promise<{ a: X }> {`），截出来的"函数体"是那段类型，断言会在无关
 * 文本上求值。
 *
 * 🔴 也**不能**只靠「块内含 return/const/await 等关键字」来筛：本轮实测
 * `openNoteLinkagePanel` 的函数体是
 * `{ noteLinkagePanelVisible.value = true; void loadNoteLinkage() }` —— 一个关键字都没有
 * ⇒ 关键字筛选把真函数体跳过、返回了后面某个无关块，断言以「入口未置开面板」的形态
 * **假红**。那是 helper 缺陷不是代码缺陷。
 *
 * 正解 = 主判据取「其后第一个**紧跟换行**的 `{`」（函数体开括号后必换行；返回类型注解的
 * `{` 同行还有 `ok: boolean }`），关键字筛选降为**兜底**（覆盖单行函数体写法）。
 */
function fnBody(src: string, decl: RegExp): string {
  const m = src.match(decl)
  if (!m || m.index === undefined) return ''
  const from = m.index + m[0].length
  // 主判据：第一个「后面只有空格就换行」的 `{`
  for (let i = from; i < src.length; i += 1) {
    if (src[i] !== '{') continue
    if (/^\{[ \t]*\r?\n/.test(src.slice(i, i + 4))) {
      const end = matchBrace(src, i)
      return end < 0 ? '' : src.slice(i, end + 1)
    }
    // 该 `{` 不是函数体开括号（多为内联类型注解）→ 整块跳过，避免误入其内部
    const end = matchBrace(src, i)
    if (end < 0) return ''
    i = end
  }
  // 兜底：单行函数体（`function f() { return 1 }`）
  let cursor = from
  for (let guard = 0; guard < 12; guard += 1) {
    const open = src.indexOf('{', cursor)
    if (open < 0) return ''
    const end = matchBrace(src, open)
    if (end < 0) return ''
    const block = src.slice(open, end + 1)
    if (/\b(return|const|let|await|if|for|throw|void)\b/.test(block)) return block
    cursor = end + 1
  }
  return ''
}

/** 截取 `fn(...)` 的实参区（**圆括号配对**）。 */
function callArgs(src: string, fnName: string): string {
  const idx = src.indexOf(`${fnName}(`)
  if (idx < 0) return ''
  const open = src.indexOf('(', idx)
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

/**
 * 截取 `const {name} = computed(...)` 的**整个实参区**（圆括号配对）。
 *
 * 🔴 泛型标注**不能**用 `<[^>]*>` 匹配：`computed<{ a: X }[]>(` 的 `[^>]*` 会在内层 `>`
 * 处停下 ⇒ 整条正则不匹配 ⇒ 返回空串 ⇒ 断言以 `expected '' to contain …` 假红。
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
 * `<template #default>` 插槽，按第一个闭合标签切只能拿到 ~4% 的模板，判据 A 会空转恒绿。
 */
function sfcSegments(clean: string) {
  const tplStart = clean.indexOf('<template>')
  const scStart = clean.indexOf('<script setup')
  const scEnd = clean.indexOf('</script>', scStart)
  expect(tplStart, '未找到 <template>').toBeGreaterThanOrEqual(0)
  expect(scStart, '未找到 <script setup').toBeGreaterThan(tplStart)
  const tplEnd = clean.lastIndexOf('</template>', scStart)
  expect(tplEnd, '未找到 </template>').toBeGreaterThan(tplStart)
  const styleStart = clean.indexOf('<style', scEnd)
  return {
    template: clean.slice(tplStart, tplEnd),
    script: clean.slice(scStart, scEnd),
    style: styleStart < 0 ? '' : clean.slice(styleStart),
    naiveTemplate: clean.slice(tplStart, clean.indexOf('</template>', tplStart)),
  }
}

const SEG = sfcSegments(CLEAN)

// 脚本侧声明 → 模板消费方（判据 A 的清单）
const BINDINGS = [
  'noteLinkagePanelVisible',
  'noteLinkage',
  'noteLinkageError',
  'noteLinkageLoading',
  'noteLinkageApplying',
  'noteLinkageActionable',
  'noteLinkageBuckets',
  'applyNoteLinkage',
  'loadNoteLinkage',
  'openNoteLinkagePanel',
] as const

// ═══════════════════════════════════════════════════════════════════════════
describe('helper 自检（判据的扫描面必须真的覆盖它声称的输入空间）', () => {
  it('stripComments 不被 accept="image/*" 骗成块注释', () => {
    const src = 'const a = "image/*"\n// gone\nconst b = 1\n/* block */\nconst c = 2\n'
    const out = stripComments(src)
    expect(out).toContain('"image/*"')
    expect(out).not.toContain('gone')
    expect(out).not.toContain('block')
    expect(out).toContain('const c = 2')
  })

  it('stripComments 剥掉 SFC 的 <!-- --> 注释', () => {
    expect(stripComments('<div />\n<!-- noteLinkagePanelVisible -->\n<b />'))
      .not.toContain('noteLinkagePanelVisible')
  })

  it('fnBody 跳过内联返回类型注解', () => {
    const src = 'async function f(): Promise<{ ok: boolean }> {\n  return { ok: true }\n}\n'
    const body = fnBody(src, /async function f\s*\(/)
    expect(body).toContain('return { ok: true }')
    expect(body).not.toContain('ok: boolean')
  })

  it('fnBody 截得**一个关键字都没有**的函数体（本轮实证的 helper 缺陷）', () => {
    const src = 'function g() {\n  flag.value = true\n  void load()\n}\n\nfunction h() {\n  return 9\n}\n'
    const body = fnBody(src, /function g\s*\(/)
    expect(body, '关键字筛选把无关键字的真函数体跳过了 —— 会以「入口未置开面板」形态假红')
      .toContain('flag.value = true')
    expect(body, '越界截到了下一个函数').not.toContain('return 9')
  })

  it('callArgs 按圆括号配对取实参（嵌套调用不得截断）', () => {
    const src = 'await http.post(P.apply(projectId), { year })\n'
    expect(callArgs(src, 'http.post')).toBe('(P.apply(projectId), { year })')
    expect(
      src.match(/http\.post\([^)]*\)/)![0],
      '朴素 [^)]* 写法应在嵌套调用处截断（这正是本轮 helper 缺陷的成因）',
    ).not.toContain('{ year }')
  })

  it('computedArg 在嵌套泛型上不失配', () => {
    const src = 'const x = computed<{ a: string }[]>(() => [{ a: "v" }])\n'
    expect(computedArg(src, 'x')).toContain('a: "v"')
    expect(computedArg(src, '__nope__')).toBe('')
  })

  it('SFC 切分取到的是完整模板（朴素切法只拿到一小段）', () => {
    expect(SEG.template.length).toBeGreaterThan(SEG.naiveTemplate.length * 2)
    expect(SEG.script.length).toBeGreaterThan(5000)
    expect(SEG.style.length).toBeGreaterThan(1000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('判据 A：渲染宿主存在（脚本侧声明 × 模板消费方）', () => {
  it.each(BINDINGS)('%s 在 script setup 有声明', (name) => {
    const declared = new RegExp(
      `(?:const|let|function|async\\s+function)\\s+${name}\\b`,
    ).test(SEG.script)
    expect(declared, `${name} 在 script setup 无声明 —— 模板引用它会 ReferenceError`).toBe(true)
  })

  it.each(BINDINGS.filter((b) => b !== 'loadNoteLinkage'))(
    '%s 被模板真正消费（不只是注释里出现）',
    (name) => {
      const hits = (SEG.template.match(new RegExp(`\\b${name}\\b`, 'g')) || []).length
      expect(
        hits,
        `${name} 在剥注释后的模板中 0 引用 —— 这是「脚本侧齐备而无渲染宿主」，`
        + '四层检查全绿但功能不存在（Task 14 已在本文件踩过一次）',
      ).toBeGreaterThan(0)
    },
  )

  it('loadNoteLinkage 既被模板重试按钮消费、也被裁剪保存路径调用', () => {
    expect(SEG.template).toContain('loadNoteLinkage()')
    const save = fnBody(SEG.script, /async function saveTrim\s*\(/)
    expect(save, 'saveTrim 函数体未截到（守卫解析失效）').not.toBe('')
    expect(
      save.includes('loadNoteLinkage()'),
      '裁剪保存成功后未触发附注联动 —— 联动服务成为死代码（本 spec 反复出现的失败形态）',
    ).toBe(true)
  })

  it('面板本体是 el-dialog 且绑在 noteLinkagePanelVisible 上', () => {
    const dialogs = SEG.template.match(/<el-dialog[\s\S]*?<\/el-dialog>/g) || []
    const host = dialogs.filter((d) => /v-model="noteLinkagePanelVisible"/.test(d))
    expect(host.length, '没有任何 el-dialog 绑定 noteLinkagePanelVisible').toBe(1)
    expect(host[0]).toContain('noteLinkageBuckets')
    expect(host[0]).toContain('applyNoteLinkage()')
  })

  it('有一个随时可开的入口（不只在保存那一刻弹一次）', () => {
    expect(
      SEG.template,
      '缺常驻入口 —— 审计师事后想复核「哪些附注章节被标了不适用」将无路可走',
    ).toContain('openNoteLinkagePanel')
  })

  it('反向自检：raw 里这些标识符命中数**多于** clean（剥注释确实在生效）', () => {
    for (const name of ['noteLinkagePanelVisible', 'noteLinkageBuckets', 'loadNoteLinkage']) {
      const rawHits = (RAW.match(new RegExp(`\\b${name}\\b`, 'g')) || []).length
      const cleanHits = (CLEAN.match(new RegExp(`\\b${name}\\b`, 'g')) || []).length
      expect(
        rawHits,
        `${name} 在 raw 与 clean 命中数相同（${rawHits}）—— 剥注释未生效或注释里已不再`
        + '记录设计理由，判据 A 的"剥注释"防护已无对象可防',
      ).toBeGreaterThan(cleanHits)
    }
  })

  it('反向自检：不存在的标识符不得被判为"已声明"', () => {
    expect(/(?:const|let|function)\s+noteLinkageNope\b/.test(SEG.script)).toBe(false)
  })

  /**
   * 🔴 判据必须带**右定界符**，不能用 `style.includes('.' + cls)`。
   *
   * 变异检验实测：把 `.gt-proc-nlink__hint` 改名成 `.gt-proc-nlink__hintX` 后，
   * `includes('.gt-proc-nlink__hint')` **仍然为真**（前者是后者的子串）⇒ 判据 GREEN，
   * 而界面上那一组已经没有样式了。同族于 Task 20 的
   * `toContain('<GtTrimAdequacyReview')` 被 `<GtTrimAdequacyReviewXX` 骗过。
   */
  const hasStyleRule = (style: string, cls: string): boolean =>
    new RegExp(`\\.${cls}(?![\\w-])`).test(style)

  it('模板用到的 scoped 类必须真有样式（缺类不报错、只表现为无视觉分层）', () => {
    const used = new Set(
      (SEG.template.match(/gt-proc-nlink__[a-z-]+/g) || []),
    )
    expect(used.size, '模板未用到任何 gt-proc-nlink 类 —— 面板可能压根不存在').toBeGreaterThan(2)
    for (const cls of used) {
      expect(
        hasStyleRule(SEG.style, cls),
        `模板用了 .${cls} 但 <style> 里没有（或只有以它为前缀的别的类名）—— scoped CSS `
        + '缺类不报错、渲染照旧，get_diagnostics 与 vitest 全查不出，'
        + '只表现为各分组视觉上完全一样',
      ).toBe(true)
    }
  })

  it('反向自检：改名后的同前缀类名不得被判为"有样式"', () => {
    expect(hasStyleRule('.foo__bar { color: red; }', 'foo__bar')).toBe(true)
    expect(hasStyleRule('.foo__bar,\n.baz { color: red; }', 'foo__bar')).toBe(true)
    expect(
      hasStyleRule('.foo__barX { color: red; }', 'foo__bar'),
      '子串匹配未被排除 —— 删/改一个类名的变异会恒绿（本轮变异 M20 的实证成因）',
    ).toBe(false)
    expect(hasStyleRule('.foo__bar-lite { color: red; }', 'foo__bar')).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('判据 B：前端只展示后端派生结果，不另建"不适用"判定', () => {
  it('前端不出现 is_empty 写入或空判定逻辑', () => {
    for (const token of ['is_empty', 'note_has_data', 'is_section_empty', 'is_empty_table']) {
      expect(
        SEG.script.includes(token),
        `脚本里出现 ${token} —— 不适用真源与判定都在后端（disclosure_notes.is_empty + `
        + 'note_content_utils.note_has_data），前端另算一份必然与后端分叉',
      ).toBe(false)
    }
  })

  const BUCKET_KEYS = ['to_mark', 'to_revoke', 'conflicts', 'unlocatable', 'skipped_foreign_mark']

  /**
   * 每个桶的 `items` 必须**恰好**是它自己那一个后端数组，1:1。
   *
   * 🔴 「每个桶键名都出现过」这种判据挡不住合并：变异检验实测把 `items: v.to_mark,`
   * 改成 `items: [...v.to_mark, ...v.conflicts, ...v.unlocatable],` 后，五个 `v.<key>`
   * 依然全在、`key:` 依然是 5 个 ⇒ 判据 GREEN，而界面上「有内容所以没标」和
   * 「附注侧没这一节」已经混进了「将标注」那张表（没标的看起来像已标）。
   */
  const bucketMappingIs1to1 = (arg: string): { ok: boolean; why: string } => {
    for (const key of BUCKET_KEYS) {
      if (!arg.includes(`items: v.${key},`)) {
        return { ok: false, why: `桶 ${key} 的 items 不是恰 \`v.${key}\`（可能被合并或改源）` }
      }
    }
    if (/items:\s*\[/.test(arg)) return { ok: false, why: 'items 是数组字面量 —— 多个桶被合并' }
    if (/items:[^,\n]*\.concat\(/.test(arg)) return { ok: false, why: 'items 用 concat 合并了多个桶' }
    const itemsCount = (arg.match(/items:/g) || []).length
    if (itemsCount !== BUCKET_KEYS.length) {
      return { ok: false, why: `items: 出现 ${itemsCount} 次，与桶数 ${BUCKET_KEYS.length} 不等` }
    }
    return { ok: true, why: '' }
  }

  it('noteLinkageBuckets 只做分组展示，不判定该不该标注', () => {
    const arg = computedArg(SEG.script, 'noteLinkageBuckets')
    expect(arg, 'noteLinkageBuckets 未截到（守卫解析失效）').not.toBe('')
    for (const key of BUCKET_KEYS) {
      expect(arg, `分组缺 ${key} 桶`).toContain(`v.${key}`)
    }
    const verdict = bucketMappingIs1to1(arg)
    expect(verdict.ok, `桶与后端数组不是 1:1：${verdict.why}`).toBe(true)
    // 不得出现自算判据（余额 / 阈值 / 循环是否整体裁剪等一律来自后端）
    for (const bad of ['trimmed', 'decideTrim', 'performance_materiality', 'filter(']) {
      expect(arg, `分组实参区出现自算判据 ${bad}`).not.toContain(bad)
    }
  })

  it('反向自检：合并了桶的实参区必须被判为不合格', () => {
    const merged = BUCKET_KEYS
      .map((k, i) => (i === 0
        ? `{ key: '${k}', items: [...v.${k}, ...v.conflicts], hint: 'x' },`
        : `{ key: '${k}', items: v.${k}, hint: 'x' },`))
      .join('\n')
    expect(
      bucketMappingIs1to1(merged).ok,
      '合并形态被判为合格 —— 判据退化成「键名是否出现」（本轮变异 M17 的实证成因）',
    ).toBe(false)
    const clean = BUCKET_KEYS.map((k) => `{ key: '${k}', items: v.${k}, hint: 'x' },`).join('\n')
    expect(bucketMappingIs1to1(clean).ok, '合格形态被误判为不合格（判据过严）').toBe(true)
  })

  it('五个桶必须分开渲染，不得合并成一张表', () => {
    const arg = computedArg(SEG.script, 'noteLinkageBuckets')
    const keys = (arg.match(/key:\s*'([a-z_]+)'/g) || []).length
    expect(
      keys,
      '桶数不足 5 —— 「有内容所以没标」「附注侧没这一节」「人工标注」三者与「将标注」'
      + '含义完全不同，合成一张表会让没标的看起来像已标',
    ).toBe(5)
  })

  it('应用按钮只在真有净变更时可点（避免"应用了但一节没动"）', () => {
    const dialog = (SEG.template.match(/<el-dialog[\s\S]*?<\/el-dialog>/g) || [])
      .find((d) => /v-model="noteLinkagePanelVisible"/.test(d)) || ''
    expect(dialog).toMatch(/summary\.to_mark\s*\+\s*noteLinkage\.summary\.to_revoke\)\s*===\s*0/)
    expect(dialog, '应用按钮未做权限门控').toContain('!canManage')
  })

  it('只经两个 commonApi 函数访问后端，不自己拼 http 调用', () => {
    const script = SEG.script
    expect(script).toContain('fetchTrimNoteLinkage')
    expect(script).toContain('applyTrimNoteLinkage')
    for (const fn of ['loadNoteLinkage', 'applyNoteLinkage', 'openNoteLinkagePanel']) {
      const body = fnBody(script, new RegExp(`(?:async\\s+)?function ${fn}\\s*\\(`))
      expect(body, `${fn} 函数体未截到`).not.toBe('')
      expect(body, `${fn} 里直接发了 http 请求（应经 commonApi）`).not.toMatch(/http\.(get|post|put|delete)/)
      expect(body, `${fn} 里出现 note-linkage 路径字面量（应经 apiPaths）`).not.toContain('note-linkage')
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('判据 C：未知态不退化为"没有需要标注的章节"', () => {
  it('noteLinkage 是三态 ref，加载失败置 null 并记 error', () => {
    expect(SEG.script).toMatch(/const noteLinkage\s*=\s*ref<NoteLinkageView \| null>\(null\)/)
    const body = fnBody(SEG.script, /async function loadNoteLinkage\s*\(/)
    expect(body, 'loadNoteLinkage 未截到').not.toBe('')
    const cat = body.slice(body.indexOf('catch'))
    expect(cat, '失败时未把状态置 null').toContain('noteLinkage.value = null')
    expect(cat, '失败时未记 error（会让"读不到"与"没有可标注章节"不可区分）')
      .toContain('noteLinkageError.value')
    expect(cat, '失败时退化成了空对象/空数组 —— 会把技术故障显示成实质结论')
      .not.toMatch(/noteLinkage\.value\s*=\s*(\[\]|\{)/)
  })

  it('模板对未知态有独立渲染，且明说它不等于"没有需要标注的章节"', () => {
    const dialog = (SEG.template.match(/<el-dialog[\s\S]*?<\/el-dialog>/g) || [])
      .find((d) => /v-model="noteLinkagePanelVisible"/.test(d)) || ''
    expect(dialog).toContain('v-if="noteLinkageError"')
    expect(dialog).toMatch(/type="error"/)
    expect(
      dialog,
      '未知态提示没写清后果 —— 只显示一句"失败"会让审计师当成"没有需要标注的章节"',
    ).toContain('不等于')
  })

  it('手动入口先开面板再加载（否则读取失败完全不可见）', () => {
    const body = fnBody(SEG.script, /function openNoteLinkagePanel\s*\(/)
    const openIdx = body.indexOf('noteLinkagePanelVisible.value = true')
    const loadIdx = body.indexOf('loadNoteLinkage()')
    expect(openIdx, '入口未置开面板').toBeGreaterThanOrEqual(0)
    expect(loadIdx, '入口未触发加载').toBeGreaterThan(openIdx)
  })

  it('降级标注有独立渲染（后端 degradations 是唯一来源）', () => {
    const dialog = (SEG.template.match(/<el-dialog[\s\S]*?<\/el-dialog>/g) || [])
      .find((d) => /v-model="noteLinkagePanelVisible"/.test(d)) || ''
    expect(dialog).toContain('noteLinkage.degradations')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
describe('判据 D：跨前后端交叉锁死', () => {
  const API_PATHS = stripComments(read(P_API_PATHS))
  const COMMON = stripComments(read(P_COMMON_API))
  const ROUTER_PY = read(P_ROUTER_PY)
  const LINKAGE_PY = read(P_LINKAGE_PY)

  it('端点路径与后端 router 装饰器逐字一致', () => {
    const suffixes = [
      '/procedure-trim/note-linkage',
      '/procedure-trim/note-linkage/apply',
    ]
    for (const s of suffixes) {
      expect(API_PATHS, `apiPaths 缺 ${s}`).toContain(s)
      expect(
        ROUTER_PY,
        `后端 router 没有 ${s} —— 前端会 404，而两侧各自的单测都不会红`,
      ).toContain(`"/{pid}${s}"`)
    }
  })

  it('apiPaths 访问器挂在已被 barrel re-export 的对象内', () => {
    const idx = API_PATHS.indexOf('trimNoteLinkage:')
    const objStart = API_PATHS.lastIndexOf('export const procedureRowTasks', 0 + idx)
    expect(objStart, 'trimNoteLinkage 不在 procedureRowTasks 对象内 —— barrel 不会导出它')
      .toBeGreaterThanOrEqual(0)
  })

  it('前端消费的桶键名与后端 _as_payload 逐键一致', () => {
    const m = LINKAGE_PY.match(/def _as_payload\(c: _Classification\) -> dict:[\s\S]*?\n\n/)
    expect(m, '未截到后端 _as_payload').not.toBeNull()
    const py = m![0]
    for (const key of [
      'to_mark', 'already_marked', 'conflicts', 'to_revoke',
      'unlocatable', 'skipped_foreign_mark', 'degradations', 'cycles_fully_trimmed',
    ]) {
      expect(py, `后端 payload 缺键 ${key}`).toContain(`"${key}":`)
      expect(COMMON, `前端 commonApi 未消费键 ${key}`).toContain(key)
    }
  })

  it('apply 请求体只传 year（不传章节清单）', () => {
    const body = fnBody(COMMON, /export async function applyTrimNoteLinkage\s*\(/)
    expect(body, 'applyTrimNoteLinkage 未截到').not.toBe('')
    const post = callArgs(body, 'http.post')
    expect(post, '未找到 post 调用（圆括号配对提取失效）').not.toBe('')
    expect(post).toContain('{ year }')
    expect(
      post,
      '前端传了章节清单 —— 那会与并发会话改过的裁剪状态脱节，把已恢复执行的循环标成不适用',
    ).not.toMatch(/sections|to_mark|note_section/)
  })

  it('preview 走 GET 并带 year 查询参数', () => {
    const body = fnBody(COMMON, /export async function fetchTrimNoteLinkage\s*\(/)
    expect(body).toMatch(/http\.get\(/)
    expect(body, '预览未带 year —— 后端定位不到附注章节行，整份联动静默返空')
      .toContain('params: { year }')
    expect(body, '预览端点被用于写入').not.toMatch(/http\.(post|put|delete)/)
  })
})
