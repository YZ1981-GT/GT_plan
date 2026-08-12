/**
 * 裁剪页建议态接线守卫（源码级，零 mount）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 13
 * Requirements: 3.1 / 6.1~6.7 / 7.3 / 8.6 / 4.5
 *
 * ## 本文件防的是什么
 *
 * Task 13 落地时实测发现的**不是**「功能没做」，而是整条建议态链**从未跑通过**：
 *
 * | 缺陷 | 表现 | 四层检查（Volar / vitest / get_diagnostics / HEAD-swap） |
 * |---|---|---|
 * | `suggestions` / `suggestionOf` / `decisionContext` / `loadDecisionContext` / `TrimSuggestion` 五个标识符全文零声明 | 运行即 `ReferenceError` | 全绿 |
 * | `loadTrimContext` 零调用点（死代码）⇒ `trimContext` 恒 null ⇒ `degradationNotes` 恒空 | 降级标注（R4.4）从未渲染 | 全绿 |
 * | `_suggest` / `_suggestReasonCode` / `_suggestNarrative` / `_decisionAccountName` / `_decisionEvidence` 五个行字段零赋值点 | 建议条计数恒 0、汇总闸恒空 | 全绿 |
 *
 * 三类缺陷的共同点：**符号名都在源码里出现过**（在注释、在读取侧、在 import 行），
 * 所以任何「grep 到标识符即视为已接线」的判据都会静默通过。故本文件的每条判据都落到
 * **结构**（哪个函数体的哪个分支里有什么赋值）而非「字符是否存在」。
 *
 * ## 🔴 判据必须先 stripComments
 *
 * 修复时**刻意在注释里保留了** `decisionContext` / `TrimSuggestion` / `suggestions.value` /
 * `loadDecisionContext` 等字样，用来记录缺陷成因（防后续会话把修复回退）。任何断言
 * 「全文不含 X」的判据若不剥注释就会**误红** —— 那是守卫缺陷，不是代码缺陷。
 *
 * ## helper 来源
 *
 * `repoRoot` / `read` / `fnBody` / `computedArg` / `stripComments` 五件套与两组自检
 * 照抄 `b50BadgeSingleSource.spec.ts`（Task 4 已用变异检验验证过其承重性）。刻意不抽公共
 * 模块：守卫的 helper 一旦共享，改动它就会同时改变多个守卫的判据面，而那正是
 * 「守卫自身被改坏却无人发现」的入口。
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

const P_TRIM_VUE = path.join(FE, 'views', 'ProcedureTrimming.vue')
const P_DECISION = path.join(FE, 'components', 'workpaper', 'composables', 'procedureTrimDecision.ts')
const P_REASON = path.join(FE, 'components', 'workpaper', 'composables', 'trimReasonCodes.ts')
const P_GATE = path.join(FE, 'components', 'workpaper', 'composables', 'trimAggregateGate.ts')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/**
 * 截取具名函数的**函数体**（花括号配对）。
 *
 * 🔴 不能用「声明后第一个 `{`」定位 —— 平台已多次踩到：那个 `{` 可能是**内联返回
 * 类型注解**（`function f(): Promise<{ a: X }> {`）或参数的内联类型字面量
 * （`function f(p: { a: X })`），截出来的"函数体"其实是那段类型，后续断言全在无关
 * 文本上求值（会把正确实现打红）。
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
 */
function computedArg(src: string, name: string): string {
  // 🔴 只锚 `const NAME = computed`，再取其后第一个 `(`（泛型里不会有圆括号）。
  //    首版写成 `computed\s*\(` ⇒ 带类型参数的 `computed<number | null>(` 整条失配、
  //    返回空串，进而以「未找到该 computed」的形态**假红**（Task 20 实证）。
  //    也不能写 `computed\s*(?:<[^>]*>)?\s*\(`：`computed<Record<string, boolean> | null>(`
  //    里 `[^>]*` 会停在内层 `>` 上，同样失配（Task 14 实证）。
  const decl = new RegExp(`const\\s+${name}\\s*=\\s*computed`)
  const m = src.match(decl)
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

  it('computedArg 容忍类型参数（否则带泛型的 computed 会以「未找到」假红）', () => {
    const a = 'const x = computed(() => f(1))'
    const b = 'const y = computed<number | null>(() => g(2))'
    const c = 'const z = computed<Record<string, boolean> | null>(() => h(3))'
    expect(computedArg(a, 'x')).toContain('f(1)')
    expect(computedArg(b, 'y'), '简单泛型失配 = 判据假红').toContain('g(2)')
    expect(computedArg(c, 'z'), '嵌套泛型失配 = 判据假红').toContain('h(3)')
    expect(computedArg(a, 'nosuch'), '不存在的名字必须返回空串').toBe('')
  })

  it('剥掉 HTML 注释（SFC 模板里的说明文字）', () => {
    const s = stripComments(`<!-- 说明：不得自行聚合 -->\n<div>keep</div>`)
    expect(s).not.toContain('不得自行聚合')
    expect(s).toContain('<div>keep</div>')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 共享的源码切片（一次读盘，多处判据复用）
// ═══════════════════════════════════════════════════════════════════════════

const TRIM_SRC = stripComments(read(P_TRIM_VUE))

/**
 * SFC 三段切分。
 *
 * 🔴 `</template>` 不能取**第一个** —— 本文件有 20+ 个嵌套的 `<template #default>`
 * 插槽，第一个 `</template>` 在第 175 行左右就闭合了，按它切会只拿到 ~6% 的模板、
 * 让判据 D 在绝大部分模板上空转（本轮探测阶段实测踩到）。正解 = 取 `<script setup`
 * 之前的**最后一个** `</template>`。
 */
function sfcSegments(clean: string): { template: string; script: string; naiveTemplate: string } {
  const tplStart = clean.indexOf('<template>')
  const scStart = clean.indexOf('<script setup')
  const scEnd = clean.indexOf('</script>', scStart)
  expect(tplStart, '未找到 <template>').toBeGreaterThanOrEqual(0)
  expect(scStart, '未找到 <script setup').toBeGreaterThan(tplStart)
  const tplEnd = clean.lastIndexOf('</template>', scStart)
  expect(tplEnd, '未找到 </template>').toBeGreaterThan(tplStart)
  const naiveEnd = clean.indexOf('</template>', tplStart)
  return {
    template: clean.slice(tplStart, tplEnd),
    script: clean.slice(scStart, scEnd),
    naiveTemplate: clean.slice(tplStart, naiveEnd),
  }
}

const SEG = sfcSegments(TRIM_SRC)

// ═══════════════════════════════════════════════════════════════════════════
// 判据 A：建议态产生路径不含适用性写入（R6.2 / R6.7）
// ═══════════════════════════════════════════════════════════════════════════
//
// 防的真实缺陷：`suggest_trim` 分支若写了 `_applicable = false` / `status` /
// `skip_reason`，「建议」就直接落成了「已裁剪」—— 重要性类判据（金额低于实际执行
// 重要性）是职业判断，未经审计师确认即落地等于绕过 R6.2。这类改动在 UI 上几乎
// 看不出（表格里那行照样变成"裁剪"），只有对着分支源码才能发现。
describe('判据 A: suggest_trim 分支只挂建议态，不写适用性', () => {
  const body = fnBody(TRIM_SRC, /async\s+function\s+confirmSmartTrim\b/)

  /** 从 `} else if (d.verdict === 'X')` 起到下一个 `} else if` 的片段。 */
  function verdictBranch(src: string, verdict: string): string {
    const anchor = verdict === 'auto_trim'
      ? `if (d.verdict === '${verdict}')`
      : `else if (d.verdict === '${verdict}')`
    const at = src.indexOf(anchor)
    if (at < 0) return ''
    const rest = src.slice(at + anchor.length)
    const next = rest.indexOf('} else if')
    return next < 0 ? rest : rest.slice(0, next)
  }

  const suggestBranch = verdictBranch(body, 'suggest_trim')
  const autoBranch = verdictBranch(body, 'auto_trim')

  // 扫描面非空自检：函数体截取失败时下面所有「不含 X」断言都会空转成假绿
  it('扫描面非空（confirmSmartTrim 函数体与两个 verdict 分支都截到了）', () => {
    expect(body, '未截到 confirmSmartTrim 函数体').not.toBe('')
    expect(body.length, 'confirmSmartTrim 函数体过短，疑似截错').toBeGreaterThan(2000)
    expect(suggestBranch, '未截到 suggest_trim 分支').not.toBe('')
    expect(autoBranch, '未截到 auto_trim 分支').not.toBe('')
  })

  it('suggest_trim 分支写齐五个建议态字段（缺一个则建议条/汇总闸取不到判据数值）', () => {
    expect(/_suggest\s*=\s*true/.test(suggestBranch), '未写 _suggest = true').toBe(true)
    for (const field of [
      '_suggestReasonCode',
      '_suggestNarrative',
      '_decisionAccountName',
      '_decisionEvidence',
    ]) {
      expect(suggestBranch, `suggest_trim 分支未写 ${field}（该字段曾全文零赋值点）`).toContain(field)
    }
  })

  it('suggest_trim 分支不写 _applicable / status / skip_reason（R6.2 红线）', () => {
    // `=(?!=)` 排除 `===` / `==` 比较；分支里 `if (p._applicable) keepCount++` 是**读**，合法
    expect(/_applicable\s*=(?!=)/.test(suggestBranch), 'suggest_trim 分支写了 _applicable').toBe(false)
    expect(/\.status\s*=(?!=)/.test(suggestBranch), 'suggest_trim 分支写了 status').toBe(false)
    expect(/skip_reason\s*=(?!=)/.test(suggestBranch), 'suggest_trim 分支写了 skip_reason').toBe(false)
  })

  it('auto_trim 分支确实写 _applicable = false（证明判据能区分两分支，不是恒不命中）', () => {
    expect(/_applicable\s*=\s*false/.test(autoBranch), 'auto_trim 分支未写 _applicable = false').toBe(true)
    expect(/\.status\s*=(?!=)/.test(autoBranch), 'auto_trim 分支未写 status').toBe(true)
  })

  it('反向自检：替身分支写了 _applicable 时同一判据必须打红', () => {
    const fake = suggestBranch.replace(/p\._suggest\s*=\s*true/, 'p._applicable = false')
    expect(fake, '替身构造失败（未替换到 _suggest = true）').not.toBe(suggestBranch)
    // 同一条正则对替身必须命中 —— 否则说明上面那条「不含」断言恒真、无承重
    expect(/_applicable\s*=(?!=)/.test(fake), '判据对替身未命中，说明该判据无承重').toBe(true)
  })

  it('重跑前逐行清理建议态（否则上轮建议会残留、计数虚高）', () => {
    expect(body).toContain('clearRowSuggestion(')
    const clear = fnBody(TRIM_SRC, /function\s+clearRowSuggestion\b/)
    expect(clear, '未找到 clearRowSuggestion 函数体').not.toBe('')
    // 五个字段必须全清；漏一个就会出现「已改判保留但仍显示判据数值」
    for (const field of [
      '_suggest',
      '_suggestReasonCode',
      '_suggestNarrative',
      '_decisionAccountName',
      '_decisionEvidence',
    ]) {
      expect(clear, `clearRowSuggestion 未清理 ${field}`).toContain(field)
    }
  })

  it('判据上下文只经 loadTrimContext 取（不得内联第二份取数）', () => {
    // 改造前此处内联了第二份 fetchTrimDecisionContext + data-availability 取数，
    // 并用同名局部 const 遮蔽了模块级 subjectWithData/subjectNoData ⇒ 模块 ref 恒空。
    expect(body).toContain('loadTrimContext(')
    expect(
      /const\s+subjectWithData\s*=/.test(body),
      'confirmSmartTrim 内声明了同名局部 subjectWithData（会遮蔽模块级 ref）',
    ).toBe(false)
    expect(
      /const\s+subjectNoData\s*=/.test(body),
      'confirmSmartTrim 内声明了同名局部 subjectNoData（会遮蔽模块级 ref）',
    ).toBe(false)
    expect(
      /fetchTrimDecisionContext\s*\(/.test(body),
      'confirmSmartTrim 内联了第二份 fetchTrimDecisionContext 取数',
    ).toBe(false)
  })

  it('loadTrimContext 有真实调用点（它曾是零调用的死代码，致降级标注从未渲染）', () => {
    const calls = (SEG.script.match(/loadTrimContext\s*\(/g) ?? []).length
    const decl = (SEG.script.match(/async\s+function\s+loadTrimContext\s*\(/g) ?? []).length
    expect(decl, 'loadTrimContext 未声明').toBe(1)
    // 总出现次数减去声明处 = 调用点数；曾为 0（死代码）
    expect(calls - decl, 'loadTrimContext 无调用点（死代码 ⇒ trimContext 恒 null ⇒ 降级标注恒空）')
      .toBeGreaterThanOrEqual(1)
  })

  it('降级标注（R4.4）唯一来源是后端 degradations，前端不自行判断', () => {
    const arg = computedArg(TRIM_SRC, 'degradationNotes')
    expect(arg, '未找到 degradationNotes computed').not.toBe('')
    expect(arg, 'degradationNotes 未读 trimContext.degradations').toMatch(
      /trimContext\.value\?\.degradations/,
    )
    // 模板里真的渲染了（否则标注仍然"从未显示过"）
    expect(SEG.template).toContain('degradationNotes')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 B：重要性类 reason_code 不走自动裁路径（R6.7 / R3.7 / R3.8）
// ═══════════════════════════════════════════════════════════════════════════
//
// 这是本 spec 的核心红线，也是最容易被"优化"掉的一条：把 below_materiality 的
// verdict 从 suggest_trim 改成 auto_trim，功能表面上"更智能了"（不用人工点确认），
// 实际是让「金额小就不查」自动生效 —— 而准则明确要求汇总考虑错报，且完整性方向的
// 漏记与账面金额无关。双向锁死：auto_trim 恰 1 处且必为 no_data；两个重要性码必为
// suggest_trim。
describe('判据 B: 重要性类判据恒为建议、永不自动裁', () => {
  const src = stripComments(read(P_DECISION))

  /** 按 `return {` 切块（花括号配对），返回全部 return 对象字面量。 */
  function returnBlocks(text: string): string[] {
    const out: string[] = []
    const re = /return\s*\{/g
    let m: RegExpExecArray | null
    while ((m = re.exec(text)) !== null) {
      const open = m.index + m[0].length - 1
      let depth = 0
      for (let i = open; i < text.length; i += 1) {
        if (text[i] === '{') depth += 1
        else if (text[i] === '}') {
          depth -= 1
          if (depth === 0) {
            out.push(text.slice(open, i + 1))
            break
          }
        }
      }
    }
    return out
  }

  const blocks = returnBlocks(src)

  it('扫描面非空（决策内核的 return 块可切出且数量合理）', () => {
    expect(blocks.length, 'return 块切分失败').toBeGreaterThan(8)
    expect(
      blocks.some(b => b.includes("verdict: 'keep'")),
      '未切到任何 keep 块，疑似切分逻辑坏了',
    ).toBe(true)
  })

  it("auto_trim 恰出现 1 次，且其 reasonCode 为 no_data（事实判断才可自动裁）", () => {
    const autoBlocks = blocks.filter(b => /verdict:\s*'auto_trim'/.test(b))
    expect(autoBlocks.length, 'auto_trim 的 return 块数量不为 1').toBe(1)
    expect(autoBlocks[0], 'auto_trim 块的 reasonCode 不是 no_data').toMatch(
      /reasonCode:\s*'no_data'/,
    )
    // 全文层面也钉死次数（防在别处新增一个 auto_trim 出口）
    expect((src.match(/verdict:\s*'auto_trim'/g) ?? []).length).toBe(1)
  })

  for (const code of ['below_trivial', 'below_materiality']) {
    it(`${code} 所在 return 块的 verdict 必为 suggest_trim`, () => {
      const hit = blocks.filter(b => new RegExp(`reasonCode:\\s*'${code}'`).test(b))
      expect(hit.length, `未找到 ${code} 的 return 块`).toBe(1)
      expect(hit[0], `${code} 的 verdict 不是 suggest_trim`).toMatch(
        /verdict:\s*'suggest_trim'/,
      )
      expect(/verdict:\s*'auto_trim'/.test(hit[0]), `${code} 走了自动裁路径`).toBe(false)
    })
  }

  it('机器理由码集合 = no_data / below_trivial / below_materiality（与真源一致）', () => {
    const reasonSrc = stripComments(read(P_REASON))
    const m = reasonSrc.match(/MACHINE_REASON_CODES[^=]*=\s*new Set\(\[([^\]]*)\]/)
    expect(m, '未找到 MACHINE_REASON_CODES').not.toBeNull()
    const codes = [...m![1].matchAll(/'([^']+)'/g)].map(x => x[1]).sort()
    expect(codes).toEqual(['below_materiality', 'below_trivial', 'no_data'])
  })

  it('汇总闸只计重要性类两码（纳入 no_data 会让闸门恒亮进而被当误报关掉）', () => {
    const gateSrc = stripComments(read(P_GATE))
    const m = gateSrc.match(/MATERIALITY_REASON_CODES[^=]*=\s*new Set\(\[([^\]]*)\]/)
    expect(m, '未找到 MATERIALITY_REASON_CODES').not.toBeNull()
    const codes = [...m![1].matchAll(/'([^']+)'/g)].map(x => x[1]).sort()
    expect(codes).toEqual(['below_materiality', 'below_trivial'])
    expect(codes.includes('no_data'), '汇总闸纳入了 no_data').toBe(false)
  })

  it('裁剪页的汇总闸只喂当前建议态行（已确认行反复计入会让闸门单调收紧）', () => {
    const arg = computedArg(TRIM_SRC, 'aggregateGate')
    expect(arg, '未找到 aggregateGate computed').not.toBe('')
    expect(arg, 'aggregateGate 未调用 evaluateAggregateGate').toContain('evaluateAggregateGate')
    // 🔴 Task 20 起，建议项的构造与阈值读取各收敛成一个具名 computed（复核视图要与
    //    这道闸门用**同一批输入**才可能"逐项相等"）。故本条判据跟着指向那两个 computed，
    //    而「只喂建议态行」这个不变式在下一条上钉死 —— 不是放宽，是把它挪到了真源上。
    expect(arg, 'aggregateGate 未喂 suggestedGateItems').toContain('suggestedGateItems.value')
    expect(arg).toContain('performanceMateriality.value')
    expect(/overall_materiality/.test(arg), 'aggregateGate 用了 overall_materiality 作阈值').toBe(false)
  })

  it('汇总闸的建议项真源只取建议态行，阈值只取实际执行重要性', () => {
    const items = computedArg(TRIM_SRC, 'suggestedGateItems')
    expect(items, '未找到 suggestedGateItems computed').not.toBe('')
    expect(items, '建议项未取 suggestedRows（会把已确认行也算进闸门）')
      .toContain('suggestedRows.value')
    expect(/procedures\.value/.test(items), '建议项直接遍历全部程序 ⇒ 已确认行反复计入')
      .toBe(false)

    const pm = computedArg(TRIM_SRC, 'performanceMateriality')
    expect(pm, '未找到 performanceMateriality computed').not.toBe('')
    expect(pm).toMatch(/performance_materiality/)
    expect(/overall_materiality/.test(pm), '阈值读了财务报表整体重要性').toBe(false)
  })

  it('批量确认前过汇总闸，blocked 时只阻断批量、仍允许逐条', () => {
    const body = fnBody(TRIM_SRC, /async\s+function\s+confirmAllSuggestions\b/)
    expect(body, '未找到 confirmAllSuggestions 函数体').not.toBe('')
    expect(body, '批量确认未读汇总闸').toContain('aggregateGate.value')
    expect(/gate\.blocked/.test(body), '批量确认未判 blocked').toBe(true)
    // 逐条确认路径**不得**判 blocked（否则闸门会连逐条一起锁死）
    const one = fnBody(TRIM_SRC, /async\s+function\s+confirmSuggestion\b/)
    expect(one, '未找到 confirmSuggestion 函数体').not.toBe('')
    expect(/blocked/.test(one), '逐条确认也被汇总闸阻断（R7.3 要求只拦批量）').toBe(false)
  })

  it('确认走既有 canonical preview → apply，理由码随同一次请求提交（禁两次写入）', () => {
    const body = fnBody(TRIM_SRC, /async\s+function\s+applySuggestions\b/)
    expect(body, '未找到 applySuggestions 函数体').not.toBe('')
    expect(body).toContain('canonicalTrimPreview')
    expect(body).toContain('canonicalTrimApply')
    // reason_code 与 target_status 同在一个 entry 对象里
    expect(/target_status:/.test(body), 'entry 未带 target_status').toBe(true)
    expect(/reason_code:/.test(body), 'entry 未带 reason_code（理由码无处可落）').toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 C：导出理由码与理由文本双列（R8.6 / R8.8）
// ═══════════════════════════════════════════════════════════════════════════
//
// R8.8 明令不得把理由码编码进理由文本列 —— 合并成一列后复核方无法按码做全项目统计
// （「本项目有多少裁剪是因金额低于重要性」这类问题就答不了）。
describe('判据 C: 导出方案含理由码与理由文本两列', () => {
  const body = fnBody(TRIM_SRC, /async\s+function\s+exportScheme\b/)

  /** 取表头 aoa 首行的字面量列表。 */
  function headerCells(text: string): string[] {
    const m = text.match(/const\s+aoa[^=]*=\s*\[\[([^\]]*)\]\]/)
    if (!m) return []
    return [...m[1].matchAll(/'([^']*)'/g)].map(x => x[1])
  }

  const header = headerCells(body)

  it('扫描面非空（exportScheme 函数体与表头都截到了）', () => {
    expect(body, '未截到 exportScheme 函数体').not.toBe('')
    expect(header.length, '未解析出表头列').toBeGreaterThan(4)
  })

  it('表头同时含「裁剪理由」与「理由码」，且二者并列相邻', () => {
    expect(header, '表头缺「裁剪理由」列').toContain('裁剪理由')
    expect(header, '表头缺「理由码」列').toContain('理由码')
    const iText = header.indexOf('裁剪理由')
    const iCode = header.indexOf('理由码')
    expect(iCode, '「理由码」未紧随「裁剪理由」（R8.6 要求并列两列）').toBe(iText + 1)
  })

  it('行构造读 suggestion_state.reason_code（不是把码塞进文本列）', () => {
    expect(
      /suggestion_state\?\.reason_code/.test(body),
      '导出行未读 suggestion_state.reason_code',
    ).toBe(true)
    // 理由文本列仍读 skip_reason 原文（存量纯手工理由必须可读）
    expect(/skip_reason/.test(body), '导出行未读 skip_reason 原文').toBe(true)
  })

  it("列宽 ws['!cols'] 项数与表头列数相等（漏一项会让末列挤成默认宽）", () => {
    const m = body.match(/ws\['!cols'\]\s*=\s*\[([^\]]*)\]/)
    expect(m, "未找到 ws['!cols']").not.toBeNull()
    const widths = (m![1].match(/\{\s*wch:/g) ?? []).length
    expect(widths, `列宽项数 ${widths} 与表头列数 ${header.length} 不等`).toBe(header.length)
  })

  it('反向自检：删掉「理由码」的替身必须被同一判据打红', () => {
    const fake = body.replace("'理由码', ", '')
    expect(fake, '替身构造失败（未替换到 理由码）').not.toBe(body)
    const fakeHeader = headerCells(fake)
    expect(fakeHeader.includes('理由码'), '替身仍含理由码，构造无效').toBe(false)
    // 上面那条「表头含理由码」的判据对替身必须失败 ⇒ 判据有承重
    expect(fakeHeader.length, '替身表头列数未减少').toBe(header.length - 1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 D：模板消费的标识符必须有声明
// ═══════════════════════════════════════════════════════════════════════════
//
// 🔴 本轮最贵的一类缺陷：`suggestions` / `suggestionOf` / `decisionContext` /
// `loadDecisionContext` / `TrimSuggestion` 五个标识符**全文零声明**，运行即
// `ReferenceError`，而 Volar / vitest / get_diagnostics / HEAD-swap 四层全绿 ——
// 只有浏览器挂载才暴露。原因：SFC 模板表达式不参与 TS 类型检查，脚本里对 `any` 行
// 对象赋任意字段也不报错。
//
// 故此处做一层**结构性**判据：模板里出现的自由函数调用，必须在 `<script setup>` 里
// 找得到 `function X` / `const X =` / `import { X }` 之一。
describe('判据 D: 模板消费的标识符在 script setup 里有声明', () => {
  /** `<script setup>` 里 import 进来的绑定名（含具名与默认导入）。 */
  function importedBindings(script: string): Set<string> {
    const out = new Set<string>()
    for (const m of script.matchAll(/import\s+(?:type\s+)?\{([^}]*)\}\s*from/g)) {
      for (const raw of m[1].split(',')) {
        const name = raw.replace(/^\s*type\s+/, '').split(/\s+as\s+/).pop()?.trim()
        if (name) out.add(name)
      }
    }
    for (const m of script.matchAll(/import\s+([A-Za-z_$][\w$]*)\s*(?:,\s*\{[^}]*\}\s*)?from/g)) {
      out.add(m[1])
    }
    return out
  }

  const IMPORTED = importedBindings(SEG.script)

  function declKind(name: string): string {
    if (new RegExp(`\\b(?:async\\s+)?function\\s+${name}\\b`).test(SEG.script)) return 'function'
    if (new RegExp(`\\bconst\\s+${name}\\s*[=:]`).test(SEG.script)) return 'const'
    if (new RegExp(`\\blet\\s+${name}\\s*=`).test(SEG.script)) return 'let'
    if (IMPORTED.has(name)) return 'import'
    return 'MISSING'
  }

  /**
   * 模板里的**自由函数调用**（排除 `.foo(` 形态的方法调用与 JS 内建）。
   */
  const BUILTIN: ReadonlySet<string> = new Set([
    'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'console', 'encodeURIComponent',
    'filter', 'map', 'reduce', 'slice', 'join', 'includes', 'indexOf', 'find', 'some',
    'every', 'toFixed', 'trim', 'split', 'replace', 'push', 'startsWith', 'endsWith',
    'sort', 'toUpperCase', 'toLowerCase', 'concat', 'keys', 'values', 'entries', 'has',
    'get', 'set', 'length',
  ])

  /**
   * 允许在模板里"无声明"出现的名字 —— **CSS 函数**，不是 JS 标识符。
   *
   * 实测来源（不是猜的）：
   * - `calc` ← `max-height="calc(100vh - 340px)"`（Element Plus 的 CSS 长度 prop）
   * - `var`  ← `style="color: var(--gt-color-primary)"` 与 `:style="… 'color: var(…)' …"`
   *
   * 🔴 这个清单必须保持最小：它每多一个名字，就多一个真实标识符可以藏进来的缺口。
   * 故下面配了「清单里的名字不得同时是脚本声明」的自检，以及把未声明集合**冻结**
   * 为恰好这两个 —— 新增任何未声明标识符都会打红（那正是本判据的目的）。
   */
  const CSS_FUNCTIONS: ReadonlySet<string> = new Set(['calc', 'var'])

  /**
   * 标识符首字符类是 `[a-z_$]` 而**不是** `[a-z]`。
   *
   * 🔴 这处放宽是本守卫自身的反向自检逼出来的，不是顺手加的：首版写
   * `/\b([a-z][A-Za-z0-9_]*)\s*\(/`，而反向自检的哨兵名是 `__nonexistentHelper__`
   * （下划线起头）⇒ 哨兵**根本不可能被提取到**，那条自检于是在测「哨兵长什么样」
   * 而不是在测「判据是否承重」，并以 `expected ['calc','var'] to include …` 的形态
   * 假红。这正是平台记过的「守卫自身缺陷」典型：判据的扫描面与它声称覆盖的输入
   * 空间不一致时，红/绿两种结果都不可信。
   *
   * 放宽到 `[a-z_$]` 后，`_privateHelper()` / `$emit()` 这类真实写法也一并纳入
   * 扫描面 —— 它们同样是「模板消费、脚本必须有声明」的对象。
   */
  function freeCalls(template: string): string[] {
    // 左边界用负向后顾而**不是** `\b`：`\b` 在 `$emit(` 前不成立（`$` 非单词字符），
    // 会把 `$` 起头的标识符整类漏掉 —— 又一处「扫描面与声称覆盖面不一致」。
    // 后顾同时排掉 `.` ⇒ 方法调用天然不进集合。
    const ID = /(?<![A-Za-z0-9_$.])([a-z_$][A-Za-z0-9_$]*)\s*\(/g
    const all = new Set([...template.matchAll(ID)].map(m => m[1]))
    return [...all].filter(n => !BUILTIN.has(n)).sort()
  }

  const CALLS = freeCalls(SEG.template)

  it('模板切分自检：取「script 前最后一个 </template>」而非第一个', () => {
    // 本文件有 20+ 个嵌套 <template #default> 插槽，朴素切法会只拿到极小一段
    const nested = (SEG.template.match(/<template\s+#/g) ?? []).length
    expect(nested, '未见嵌套 template 插槽，切分自检失去意义').toBeGreaterThan(5)
    expect(
      SEG.template.length,
      '正确切法未比朴素切法拿到更多模板（切分逻辑坏了）',
    ).toBeGreaterThan(SEG.naiveTemplate.length * 2)
    expect(SEG.template.length, '模板段过短，疑似切错').toBeGreaterThan(20000)
    expect(CALLS.length, '模板自由调用提取为空，判据会空转').toBeGreaterThan(8)
  })

  it('白名单函数在 script setup 里都有声明', () => {
    const whitelist = [
      'suggestionOf', 'reasonCodeLabel', 'formatTrimReason', 'jumpToCycleFromOverview',
      'exportScheme', 'confirmAllSuggestions', 'confirmSuggestion', 'rejectSuggestion',
      'clearRowSuggestion', 'applySuggestions', 'loadTrimContext', 'saveTrim',
    ]
    const missing = whitelist.filter(n => declKind(n) === 'MISSING')
    expect(missing, `以下标识符在 script setup 里查不到声明: ${missing.join(', ')}`).toEqual([])
  })

  it('白名单 computed / ref 在 script setup 里都有声明', () => {
    const whitelist = [
      'suggestionStats', 'aggregateGate', 'degradationNotes', 'overviewRows',
      'overviewTotals', 'suggestedRows', 'trimContext', 'b50Completeness',
    ]
    const missing = whitelist.filter(n => !new RegExp(`\\bconst\\s+${n}\\s*=`).test(SEG.script))
    expect(missing, `以下响应式量缺 const 声明: ${missing.join(', ')}`).toEqual([])
  })

  it('建议态相关标识符真的被模板消费（有渲染宿主，不是死代码）', () => {
    for (const name of [
      'suggestionOf', 'suggestionStats', 'aggregateGate', 'degradationNotes',
      'confirmSuggestion', 'rejectSuggestion', 'confirmAllSuggestions',
    ]) {
      expect(SEG.template, `${name} 未被模板消费（无渲染宿主 = 死代码）`).toContain(name)
    }
  })

  it('模板里没有未声明的自由调用（CSS 函数除外，清单已冻结）', () => {
    const undeclared = CALLS.filter(n => declKind(n) === 'MISSING').sort()
    // 冻结基线：恰为两个 CSS 函数。新增任何未声明标识符（含把 suggestionOf 写成
    // suggestionOfX 这类改名）都会让本条打红 —— 这正是四层检查抓不到的那类缺陷。
    expect(undeclared, `模板存在未声明标识符: ${undeclared.join(', ')}`).toEqual(['calc', 'var'])
  })

  it('CSS 函数豁免清单保持最小（不得掩盖真实标识符）', () => {
    for (const name of CSS_FUNCTIONS) {
      expect(
        declKind(name),
        `${name} 同时是脚本声明，不该出现在 CSS 豁免清单里`,
      ).toBe('MISSING')
      expect(CALLS, `豁免清单里的 ${name} 在模板中并不出现，属冗余豁免`).toContain(name)
    }
  })

  it('反向自检：故意不存在的名字必须被判为未声明', () => {
    // 🔴 哨兵名必须落在 `freeCalls` 的提取域内，否则这条自检只是在测哨兵的形状、
    //    而不是在测判据的承重能力。首版哨兵写作 `__nonexistentHelper__`（双下划线
    //    起头）而提取正则要求首字符 `[a-z]` ⇒ 哨兵**永远进不了集合**，本条恒红且
    //    红的原因与被测判据无关。修法是两侧同时收口：提取域扩到 `[a-z_$]` 起头
    //    （顺带覆盖 `$emit` 这类真实存在的形态），哨兵改为小写起头。
    const SENTINEL = 'nonexistentHelperSentinel'
    expect(declKind(SENTINEL), '哨兵在生产代码里居然有声明，请换个名字').toBe('MISSING')
    const fakeTpl = `${SEG.template}\n<div>{{ ${SENTINEL}(row) }}</div>`
    // 先证明哨兵确实进得了提取域（否则下一条断言会以假红的形态掩盖判据缺陷）
    expect(freeCalls(fakeTpl), '哨兵未被提取域捕获，反向自检失去意义').toContain(SENTINEL)
    const fakeUndeclared = freeCalls(fakeTpl).filter(n => declKind(n) === 'MISSING')
    expect(
      fakeUndeclared,
      '注入未声明标识符后判据未命中，说明该判据无承重',
    ).toContain(SENTINEL)
  })

  it('提取域自检：`$` 与 `_` 起头的调用不被漏掉', () => {
    // 负向后顾（而非 `\b`）是必要的：`\b` 在 `$emit(` 前不成立，会整类漏掉。
    const fixture = '<div>{{ $emitLike(a) }} {{ _privateHelper(b) }} {{ obj.method(c) }}</div>'
    const got = freeCalls(fixture)
    expect(got).toContain('$emitLike')
    expect(got).toContain('_privateHelper')
    expect(got, '方法调用不应进入自由调用集合').not.toContain('method')
  })

  it('反向自检：改名后的模板调用会被判据抓到（对应变异 M5）', () => {
    const fakeTpl = SEG.template.replace(/suggestionOf\(row\)/g, 'suggestionOfX(row)')
    expect(fakeTpl, '替身构造失败（未替换到 suggestionOf(row)）').not.toBe(SEG.template)
    const fakeUndeclared = freeCalls(fakeTpl).filter(n => declKind(n) === 'MISSING')
    expect(fakeUndeclared, '改名后未被判为未声明').toContain('suggestionOfX')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 概览侧建议态统计（R6.6）
// ═══════════════════════════════════════════════════════════════════════════
describe('R6.6: 建议态统计在裁剪页与全项目概览均可见', () => {
  it('裁剪页统计三项齐备（建议 / 已确认 / 已驳回）', () => {
    const arg = computedArg(TRIM_SRC, 'suggestionStats')
    expect(arg, '未找到 suggestionStats computed').not.toBe('')
    for (const key of ['suggested', 'confirmed', 'rejected']) {
      expect(arg, `suggestionStats 缺 ${key}`).toContain(key)
    }
    // 已确认判据 = 已落不适用 且 带机器理由码（人工裁剪不算"建议已确认"）
    expect(arg, '已确认未用机器理由码判据').toContain('isMachineReasonCode')
  })

  it('概览侧统计已确认 / 已驳回，且不伪造「待确认」', () => {
    const arg = computedArg(TRIM_SRC, 'overviewRows')
    expect(arg, '未找到 overviewRows computed').not.toBe('')
    expect(arg, '概览缺 suggestConfirmed').toContain('suggestConfirmed')
    expect(arg, '概览缺 suggestRejected').toContain('suggestRejected')
    // 概览侧消费 getProcedures 原始行（无 _suggest 字段），「待确认」不可派生 ——
    // 若这里出现 _suggest 判据，就是在原始行上读一个永远不存在的字段并恒得 0。
    expect(/_suggest\b/.test(arg), '概览侧读了原始行上不存在的 _suggest 字段').toBe(false)
    // 合计项同步
    const totals = computedArg(TRIM_SRC, 'overviewTotals')
    expect(totals, '未找到 overviewTotals computed').not.toBe('')
    expect(totals).toContain('suggestConfirmed')
    expect(totals).toContain('suggestRejected')
  })

  it('概览未初始化循环的建议态计数为 0（不是 undefined，否则合计变 NaN）', () => {
    const arg = computedArg(TRIM_SRC, 'overviewRows')
    // 两处 return 都要带这两个键：!Array.isArray(list) 的早退分支 + 正常分支
    const returns = (arg.match(/suggestConfirmed/g) ?? []).length
    expect(returns, 'suggestConfirmed 未在两处 return 都出现（早退分支会得 undefined ⇒ 合计 NaN）')
      .toBeGreaterThanOrEqual(2)
  })

  it('概览表格与合计条真的渲染了两列（否则统计只存在于内存）', () => {
    expect(SEG.template).toContain('overviewTotals.suggestConfirmed')
    expect(SEG.template).toContain('overviewTotals.suggestRejected')
    expect(SEG.template).toContain('row.suggestConfirmed')
    expect(SEG.template).toContain('row.suggestRejected')
  })
})
