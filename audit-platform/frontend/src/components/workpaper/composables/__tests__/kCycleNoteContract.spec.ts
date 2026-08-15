/**
 * K 循环附注载荷契约守卫（Property 36~38 / 42~45，Requirement 10.x / 12.x）。
 *
 * 与后端 `test_note_k_aging_and_payload_closure.py` 的分工：
 * - 后端那边判**模板 JSON**（seed 侧）：列 key 风格、账龄行列、子表名 ↔ 模板表名。
 * - 本文件判**前端源码**（推送侧）：账龄真源接线、无账龄循环零引用、子表名常量不含
 *   污染值、载荷元数据（`_removed_table_keys` / `_note_texts` / 标签列 key）。
 *
 * 🔴 两侧都要判，因为「seed 干净」不等于「推送干净」：模板列头对了，而载荷推来的
 * 键名不对，结果是**附注表里那几列永远空着**且不报错。
 *
 * spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
 *       Properties 36, 37, 38, 42, 43, 44, 45
 */
import { readFileSync, existsSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const COMPOSABLES = resolve(__dirname, '..')

const ALL_CYCLES = [
  'k1', 'k2', 'k3', 'k4', 'k5', 'k6', 'k7', 'k8', 'k9', 'k10', 'k11', 'k12', 'k13',
] as const

/** Requirement 10.6 / Property 38：无账龄维度的 11 个循环 */
const NO_AGING_CYCLES = [
  'k2', 'k4', 'k5', 'k6', 'k7', 'k8', 'k9', 'k10', 'k11', 'k12', 'k13',
] as const

/** 账龄相关模块名 —— 无账龄循环一处都不许引用 */
const AGING_MODULES = ['disclosureAgingLabels', 'useAgingConfig', 'AGING_BANDS', 'agingPresets']

function mapSrc(cycle: string): string {
  const path = resolve(COMPOSABLES, `${cycle}NoteSectionMap.ts`)
  expect(existsSync(path), `${cycle}NoteSectionMap.ts 不存在`).toBe(true)
  return readCached(path)
}

/** 取该循环全部 `*SUBTABLE*` 常量体（花括号配对，值可能是引用而非字面量） */
function subtableBodies(cycle: string): string[] {
  const src = mapSrc(cycle)
  const out: string[] = []
  const re = new RegExp(`export\\s+const\\s+${cycle.toUpperCase()}[A-Z0-9_]*SUBTABLE[A-Z0-9_]*\\s*(?::[^=]+)?=\\s*`, 'g')
  let m: RegExpExecArray | null
  while ((m = re.exec(src)) !== null) {
    let i = m.index + m[0].length
    let depth = 0
    for (; i < src.length; i++) {
      if (src[i] === '{' || src[i] === '[') depth++
      else if (src[i] === '}' || src[i] === ']') {
        depth--
        if (depth === 0) break
      }
    }
    out.push(src.slice(m.index + m[0].length, i + 1))
  }
  return out
}

function stringLiterals(body: string): string[] {
  return [...body.matchAll(/'([^']*)'|"([^"]*)"/g)].map((x) => x[1] ?? x[2]).filter(Boolean)
}

const CJK_RE = /[\u4e00-\u9fff]/

/** 递归收集 `components/workpaper` 下的 .vue / .ts（跳过测试目录） */
function walkWorkpaper(): string[] {
  const root = resolve(COMPOSABLES, '..')
  const out: string[] = []
  const stack = [root]
  while (stack.length) {
    const dir = stack.pop()!
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const full = resolve(dir, e.name)
      if (e.isDirectory()) {
        if (e.name !== '__tests__' && e.name !== 'node_modules') stack.push(full)
      } else if (e.name.endsWith('.vue') || e.name.endsWith('.ts')) {
        out.push(full)
      }
    }
  }
  return out
}

let _wpFiles: string[] | null = null
function workpaperFiles(): string[] {
  if (_wpFiles === null) _wpFiles = walkWorkpaper()
  return _wpFiles
}

/**
 * 剥注释（Requirement 13.8）。
 *
 * 🔴 不剥就有两个方向的假：
 * - 假绿：注释里写着 `title: '其他应付款说明'` 或一行被注掉的 `if (x.trim())`，
 *   会让「有中文 title」「有空文本闸门」两条判据凭注释通过。
 * - 假红：无账龄循环的注释里提到 `disclosureAgingLabels`（解释「为什么本循环不用
 *   账龄」正是最可能出现的地方），会把合规代码判成违规。
 *
 * 按字符扫描而不是正则：字符串/模板串里的 `//`（如 URL）不能被当注释切掉。
 */
export function stripComments(src: string): string {
  let out = ''
  let i = 0
  const n = src.length
  while (i < n) {
    const c = src[i]
    const d = src[i + 1]
    if (c === '/' && d === '/') {
      while (i < n && src[i] !== '\n') i++
      continue
    }
    if (c === '/' && d === '*') {
      i += 2
      while (i < n && !(src[i] === '*' && src[i + 1] === '/')) i++
      i += 2
      continue
    }
    if (c === "'" || c === '"' || c === '`') {
      const quote = c
      out += c
      i++
      while (i < n) {
        if (src[i] === '\\') {
          out += src[i] + (src[i + 1] ?? '')
          i += 2
          continue
        }
        out += src[i]
        if (src[i] === quote) {
          i++
          break
        }
        i++
      }
      continue
    }
    out += c
    i++
  }
  return out
}

const _srcCache = new Map<string, string>()
/** 一律返回**剥注释后**的源码（判据不许被注释满足，也不许被注释误伤） */
function readCached(path: string): string {
  let s = _srcCache.get(path)
  if (s === undefined) {
    s = stripComments(readFileSync(path, 'utf-8'))
    _srcCache.set(path, s)
  }
  return s
}

/**
 * 解析某循环 `_note_texts` 的**链路文件集**。
 *
 * 组成：map 文件 + 该循环的独立载荷/建模文件（k1）+ 它 import 的共享 kit
 * （k8~k13 的 `kPlDisclosureShared`）+ 调用 `build{C}SyncPayload` 的 `.vue`
 * （k2 的 title 由调用方穿透）。
 */
function chainFiles(cycle: string): string[] {
  const files: string[] = []
  const push = (p: string) => {
    if (existsSync(p) && !files.includes(p)) files.push(p)
  }
  push(resolve(COMPOSABLES, `${cycle}NoteSectionMap.ts`))
  if (cycle === 'k1') {
    push(resolve(COMPOSABLES, 'k1DisclosureSyncPayload.ts'))
    push(resolve(COMPOSABLES, 'k1DisclosureModel.ts'))
  }
  // 共享 kit（按 import 实际解析，不写死）
  for (const p of [...files]) {
    for (const m of readCached(p).matchAll(/from\s+'\.\/([A-Za-z0-9_]+)'/g)) {
      const dep = resolve(COMPOSABLES, `${m[1]}.ts`)
      if (existsSync(dep) && readCached(dep).includes('_note_texts')) push(dep)
    }
  }
  // 调用方（穿透型的 title 真源）
  const fn = `build${cycle.toUpperCase()}SyncPayload`
  for (const p of workpaperFiles()) {
    if (p.endsWith('.vue') && readCached(p).includes(fn)) push(p)
  }
  return files
}

/** 链路内全部中文 `title` 字面量（含 k1 的三元组第 2 位） */
function titlesInChain(cycle: string): { titles: string[]; files: string[] } {
  const files = chainFiles(cycle)
  const titles: string[] = []
  for (const p of files) {
    const src = readCached(p)
    for (const m of src.matchAll(/title\s*:\s*(?:'([^']*)'|"([^"]*)"|`([^`]*)`)/g)) {
      const v = m[1] ?? m[2] ?? m[3] ?? ''
      if (v && CJK_RE.test(v)) titles.push(v)
    }
    // k1 形态：`['listed-audit-note', '审计说明', auditNote]`
    for (const m of src.matchAll(/\[\s*'[a-z0-9-]+'\s*,\s*'([^']+)'\s*,/g)) {
      if (CJK_RE.test(m[1])) titles.push(m[1])
    }
  }
  return { titles, files: files.map((p) => p.split(/[\\/]/).pop()!) }
}

/** 取 `function fn(...)` 的函数体（花括号配对，禁固定字符窗口） */
function fnBody(src: string, fn: string): string | null {
  const m = new RegExp(`function\\s+${fn}\\s*\\(`).exec(src)
  if (!m) return null
  let i = m.index + m[0].length
  let depth = 1 // 已进入参数列表
  for (; i < src.length && depth > 0; i++) {
    if (src[i] === '(') depth++
    else if (src[i] === ')') depth--
  }
  const brace = src.indexOf('{', i)
  if (brace < 0) return null
  depth = 0
  let j = brace
  for (; j < src.length; j++) {
    if (src[j] === '{') depth++
    else if (src[j] === '}') {
      depth--
      if (depth === 0) break
    }
  }
  return src.slice(brace, j + 1)
}

/** 函数体内是否自带空文本闸门 */
function bodyFilters(body: string): boolean {
  return (
    /\.filter\([\s\S]{0,140}?trim\(\)/.test(body) ||
    /trim\(\)[\s\S]{0,80}?(?:if\s*\(\s*!\w+\s*\)|return\s+(?:undefined|\[\]))/.test(body) ||
    /if\s*\([^)]{0,60}trim\(\)\s*\)/.test(body)
  )
}

/**
 * 单处 `_note_texts` 赋值附近是否有闸门（窗口 + 一跳函数解析）。
 *
 * 🔴 `prev` = 上一处 `_note_texts` 的位置：窗口必须在它之后截断，否则**前一处赋值
 * 的闸门会被后一处借用** —— 两处相邻、只有一处有闸门时会假绿（自检已覆盖）。
 */
function gateNear(src: string, at: number, prev = -1): boolean {
  const win = src.slice(Math.max(0, at - 800, prev + 1), at + 280)

  // 形态⓪：右值直接是本文件辅助函数调用，函数体内过滤（k1 的 `noteTextRows([...])`）
  const rhs = /_note_texts\s*[:=]\s*(\w+)\s*\(/.exec(src.slice(at, at + 60))
  if (rhs) {
    const body = fnBody(src, rhs[1])
    if (body && bodyFilters(body)) return true
  }
  // 形态①：就地 `.filter(...text...trim())`（k2 / kPlDisclosureShared）
  if (/\.filter\([\s\S]{0,140}?\btext\b[\s\S]{0,80}?trim\(\)/.test(win)) return true
  // 形态②：`if (xxx.trim())` 直接守住赋值（k4 / k5 / k7）
  if (/if\s*\([^)]{0,80}\btrim\(\)\s*\)/.test(win)) return true
  // 形态③：`if (texts.length)` / `texts.length > 0` 守住赋值
  if (/if\s*\(\s*\w*[Tt]exts?\??\.length\b/.test(win)) return true
  if (/\w*[Tt]exts?\.length\s*>\s*0/.test(win)) return true
  // 形态④：闸门变量先被 trim（k3 的 `const narrative = ....trim(); if (narrative)`）
  for (const m of win.matchAll(/(?:const|let)\s+(\w+)\s*=\s*[^\n;]*\.trim\(\)/g)) {
    if (new RegExp(`if\\s*\\(\\s*!?${m[1]}\\b`).test(win)) return true
  }
  // 形态⑤：闸门变量来自本文件辅助函数，函数体内过滤（k6 的 `noteTexts()`）
  for (const m of win.matchAll(/(?:const|let)\s+(\w+)\s*=\s*(\w+)\s*\(/g)) {
    const [, v, fn] = m
    if (!new RegExp(`if\\s*\\(\\s*!?${v}\\b`).test(win)) continue
    const body = fnBody(src, fn)
    if (body && bodyFilters(body)) return true
  }
  return false
}

/**
 * 链路内**每一处** `_note_texts` 赋值都有空文本闸门。
 *
 * 🔴 用 `every` 而不是 `some`：只要有一处没闸门，用户没填的那段就会被推成空披露
 * 段落覆盖附注既有正文 —— 「别处有闸门」救不了这一处。反向自检见同名测试。
 */
function hasEmptyTextGate(src: string): boolean {
  const idxs = [...src.matchAll(/_note_texts\s*[:=]/g)].map((m) => m.index ?? 0)
  if (idxs.length === 0) return false
  return idxs.every((at, n) => gateNear(src, at, n === 0 ? -1 : idxs[n - 1]))
}

// ───────────────────────────────────────────────────────────────────────────
// Requirement 13.8：剥注释生效自检（放最前，后面所有判据都建立在它之上）
// ───────────────────────────────────────────────────────────────────────────

describe('Requirement 13.8 — 剥注释生效自检', () => {
  it('行注释 / 块注释都被剥掉', () => {
    expect(stripComments('const a = 1 // title: 说明\nconst b = 2')).not.toContain('title')
    expect(stripComments('/* title: 说明 */ const a = 1')).not.toContain('title')
    expect(stripComments('const a = 1 /* 多\n行 */ + 2')).toBe('const a = 1  + 2')
  })

  it('字符串里的 `//` 与 `/*` 不被误剥', () => {
    expect(stripComments("const u = 'https://x.cn/a'")).toBe("const u = 'https://x.cn/a'")
    expect(stripComments('const s = `a//b`')).toBe('const s = `a//b`')
    expect(stripComments('const s = "/* not a comment */"')).toBe('const s = "/* not a comment */"')
  })

  it('🔴 注释里的中文 title 不算数（否则注释即可假绿）', () => {
    const commented = "// const t = [{ title: '其他应付款说明' }]\nconst x = 1"
    const stripped = stripComments(commented)
    const titles = [...stripped.matchAll(/title\s*:\s*'([^']*)'/g)]
    expect(titles.length, '注释里的 title 被当成真 title ⇒ 判据可被注释满足').toBe(0)
  })

  it('🔴 注释里的空文本闸门不算数', () => {
    const src = stripComments(
      "// if (narrativeText.trim()) {\nsub._note_texts = [{ text: raw }]",
    )
    expect(hasEmptyTextGate(src), '注释里的闸门被当成真闸门').toBe(false)
  })

  it('🔴 注释里提到账龄模块不算违规（否则解释性注释被判成引用）', () => {
    const src = stripComments("// 本循环无账龄维度，故不引用 disclosureAgingLabels\nconst x = 1")
    expect(AGING_MODULES.some((m) => src.includes(m)), '注释被当成真引用 ⇒ 假红').toBe(false)
  })

  it('扫描面自检：真实文件剥注释后仍保留可判据的代码量', () => {
    // 防止 stripComments 写坏把整个文件吃空 ⇒ 所有判据一起变成空转
    for (const cycle of ALL_CYCLES) {
      const src = mapSrc(cycle)
      expect(src.length, `${cycle} 剥注释后源码过短 ⇒ 剥注释写坏了`).toBeGreaterThan(500)
      expect(src, `${cycle} 剥注释后 export 都没了`).toMatch(/export\s+(?:const|function|type|interface)/)
    }
  })
})

// ───────────────────────────────────────────────────────────────────────────
// Property 36：账龄单一真源且首档分变体
// ───────────────────────────────────────────────────────────────────────────

describe('Property 36 — 账龄单一真源', () => {
  it('真源模块导出 soe 首档常量，且两版首档字面不同', async () => {
    const mod = await import('../disclosureAgingLabels')
    expect(mod.DISCLOSURE_AGING_WITHIN1_SOE).toBe('1年以内（含1年）')
    // 反向自检：listed 首档不带「（含1年）」—— 两版确实不同，禁统一
    const listed = mod.toDisclosureAgingLabel?.('within1', 'listed')
    if (listed) expect(listed).not.toBe(mod.DISCLOSURE_AGING_WITHIN1_SOE)
  })

  it('K1 走共享真源而不是自写枚举', () => {
    const src = readCached(resolve(COMPOSABLES, 'k1DisclosureModel.ts'))
    expect(src).toContain("from './disclosureAgingLabels'")
    expect(src).toContain('buildDisclosureAgingLabelMap')
  })
})

// ───────────────────────────────────────────────────────────────────────────
// Property 38：无账龄循环反向锁死（源码零引用）
// ───────────────────────────────────────────────────────────────────────────

describe('Property 38 — 无账龄循环零引用', () => {
  it.each(NO_AGING_CYCLES)('%s 的 NoteSectionMap 不引用任何账龄模块', (cycle) => {
    const src = mapSrc(cycle)
    const hits = AGING_MODULES.filter((m) => src.includes(m))
    expect(hits, `${cycle} 引用了账龄模块 ${hits.join('/')} ⇒ 会引入账龄枚举`).toEqual([])
  })

  it('扫描面非空自检：K1 确实引用了账龄模块', () => {
    // 没有这条，上面 11 条的「零命中」可能只是因为文件读错/路径错
    const k1Model = readCached(resolve(COMPOSABLES, 'k1DisclosureModel.ts'))
    expect(AGING_MODULES.some((m) => k1Model.includes(m))).toBe(true)
  })
})

// ───────────────────────────────────────────────────────────────────────────
// Property 42：子表名无污染 + 反向自检
// ───────────────────────────────────────────────────────────────────────────

const HEADER_WORDS = ['项目', '本期发生额', '上期发生额', '期末余额', '期初余额']
const ENGLISH_KEY = /^[a-z][a-z0-9_]*$/

describe('Property 42 — 子表名无污染', () => {
  it.each(ALL_CYCLES)('%s 的子表名常量不含表头文字或英文列 key', (cycle) => {
    const bad: string[] = []
    for (const body of subtableBodies(cycle)) {
      for (const v of stringLiterals(body)) {
        if (HEADER_WORDS.includes(v) || ENGLISH_KEY.test(v)) bad.push(v)
      }
    }
    expect(bad, `${cycle} 子表名混入 ${bad.join('/')}`).toEqual([])
  })

  it('K7 两个变体常量都非空（值可以是引用，不能是空对象）', () => {
    const bodies = subtableBodies('k7')
    expect(bodies.length).toBeGreaterThanOrEqual(2)
    for (const body of bodies) {
      const hasEntry = /\w+\s*:/.test(body)
      expect(hasEntry, `K7 子表名常量为空：${body}`).toBe(true)
    }
  })

  it('🔴 反向自检：污染检测器对 K8~K13 的旧值必须命中', () => {
    // 旧值实测形态（Requirement 12.2）：`项目` / `本期发生额` / `non_recurring_amount`
    const legacy = ['项目', '本期发生额', '上期发生额', 'non_recurring_amount', 'amount']
    for (const v of legacy) {
      const caught = HEADER_WORDS.includes(v) || ENGLISH_KEY.test(v)
      expect(caught, `检测器漏了旧值 ${v}`).toBe(true)
    }
    // 真表名不得被误杀
    for (const v of ['销售费用（按费用性质列示）', '资产减值损失', '其他流动资产']) {
      expect(HEADER_WORDS.includes(v) || ENGLISH_KEY.test(v)).toBe(false)
    }
  })
})

// ───────────────────────────────────────────────────────────────────────────
// Property 43：K1 推送路径已明确
// ───────────────────────────────────────────────────────────────────────────

describe('Property 43 — K1 推送路径', () => {
  it('K1 的建模 + 载荷两个文件都在，且真导出载荷构造器', () => {
    for (const name of ['k1DisclosureModel.ts', 'k1DisclosureSyncPayload.ts']) {
      const path = resolve(COMPOSABLES, name)
      expect(existsSync(path), `${name} 缺失`).toBe(true)
    }
    const payload = readCached(resolve(COMPOSABLES, 'k1DisclosureSyncPayload.ts'))
    expect(payload).toMatch(/export\s+(?:function|const)\s+\w*[Pp]ayload/)
  })

  it('其余 12 个循环走统一范式（build*SyncPayload）', () => {
    const missing = ALL_CYCLES.filter(
      (c) => c !== 'k1' && !/export\s+function\s+build\w*SyncPayload/.test(mapSrc(c)),
    )
    expect(missing, `这些循环没有 build*SyncPayload：${missing.join('/')}`).toEqual([])
  })
})

// ───────────────────────────────────────────────────────────────────────────
// Property 45：载荷元数据齐备
// ───────────────────────────────────────────────────────────────────────────

describe('Property 45 — 载荷元数据', () => {
  /**
   * 必须有孤儿清理的循环 = **有条件表**（关掉后上次推送的表会残留）。
   *
   * 🔴 判据不是「多表」而是「有条件表」：K1 有 10 张表但**全是无条件推送**，
   * 没有孤儿可清；而且它的汇总表「其他应收款」与 G2/G3 共享，越权上报
   * `_removed_table_keys` 会打断对方的推送（见 `k1NoteSectionMap.ts` 的注释）。
   */
  const ORPHAN_CLEANUP_REQUIRED = [
    'k2', 'k3', 'k4', 'k6', 'k7', 'k8', 'k9', 'k11', 'k12', 'k13',
  ] as const

  /** 登记豁免（理由必须写明「为什么没有孤儿」，不是「暂未实现」） */
  const ORPHAN_CLEANUP_EXEMPT: Record<string, string> = {
    k1: 'K1 十张表全为无条件推送（无条件表 ⇒ 无孤儿）；且汇总表「其他应收款」与 G2/G3 共享，越权上报 _removed_table_keys 会打断对方推送',
    k5: '单表循环（仅「预计负债」一张），无条件表可关 ⇒ 无孤儿',
    k10: '单表循环（仅「其他收益」一张），无条件表可关 ⇒ 无孤儿',
  }

  it('孤儿清理登记完备（每个循环要么必须清、要么已登记豁免）', () => {
    const covered = new Set<string>([...ORPHAN_CLEANUP_REQUIRED, ...Object.keys(ORPHAN_CLEANUP_EXEMPT)])
    const missing = ALL_CYCLES.filter((c) => !covered.has(c))
    expect(missing, `这些循环既未要求清孤儿也未登记豁免：${missing.join('/')}`).toEqual([])
    for (const [c, why] of Object.entries(ORPHAN_CLEANUP_EXEMPT)) {
      expect(why.length, `${c} 的豁免理由过短`).toBeGreaterThan(20)
      expect(/无孤儿|共享|单表/.test(why), `${c} 的豁免理由没说清为什么没有孤儿`).toBe(true)
    }
  })

  it.each(ORPHAN_CLEANUP_REQUIRED)('%s 声明了 removedTableKeys（孤儿清理）', (cycle) => {
    const src = mapSrc(cycle)
    expect(
      src.includes('removedTableKeys') || src.includes('_removed_table_keys'),
      `${cycle} 缺孤儿清理声明 ⇒ 条件表关闭后附注里留空表`,
    ).toBe(true)
  })

  it('🔴 K1 豁免的前提成立：表全为无条件推送且确实不上报 removed', () => {
    // 豁免不许长期挂着 —— 哪天 K1 加了条件表，本条打红要求改登记
    const src = readCached(resolve(COMPOSABLES, 'k1DisclosureSyncPayload.ts'))
    const literalKeys = [...src.matchAll(/\[K1_(?:LISTED|SOE)_SUBTABLE\.\w+\]\s*:/g)].length
    expect(literalKeys, 'K1 的表不再是对象字面量无条件推送 ⇒ 豁免前提失效').toBeGreaterThanOrEqual(5)
    expect(
      src.includes('_removed_table_keys'),
      'K1 开始上报 _removed_table_keys ⇒ 请把它移出豁免登记（并确认没越权删 G2/G3 的共享表）',
    ).toBe(false)
  })

  it.each(ALL_CYCLES)('%s 的叙述段带中文 title', (cycle) => {
    // 🔴 必须按**链路**判而不是按单文件判：13 个循环的 title 有三种落法 ——
    //   · 字面量直写在 map 里（k3~k7）
    //   · 元组直写在独立载荷文件里（k1 的 `['listed-audit-note','审计说明',…]`）
    //   · 由调用方 `.vue` 穿透进来（k2 的 `title: t.title`）
    // 只读 map 文件会把后两种误判成「没有中文 title」。
    const { titles, files } = titlesInChain(cycle)
    expect(files.length, `${cycle} 链路解析为空 ⇒ 判据源可疑`).toBeGreaterThan(0)
    expect(
      titles.length,
      `${cycle} 链路（${files.join('/')}）里找不到中文 title 字面量 ⇒ ` +
        '后端 `_format_note_texts` 缺 title 时回退英文 section 键，' +
        '附注正文会渲染成 `【listed-audit-note】` 这类英文键',
    ).toBeGreaterThan(0)
    for (const t of titles) {
      expect(CJK_RE.test(t), `${cycle} 的 title 不是中文：${t}`).toBe(true)
    }
  })

  it.each(ALL_CYCLES)('%s 的 _note_texts 过滤空文本', (cycle) => {
    // 空文本不过滤 ⇒ 用户没填的叙述段被推成空披露段落，覆盖附注既有正文。
    const paths = chainFiles(cycle)
    expect(paths.length, `${cycle} 链路解析为空 ⇒ 判据源可疑`).toBeGreaterThan(0)
    const src = paths.map(readCached).join('\n')
    expect(
      hasEmptyTextGate(src),
      `${cycle} 链路里找不到空文本闸门（.filter(...text...trim()) 或 if (...trim()) 守卫）`,
    ).toBe(true)
  })

  it('🔴 反向自检：空文本闸门检测器对「无闸门直写」必须打红', () => {
    // 六种真实形态都要认（⓪~⑤，与 gateNear 一一对应）
    const ok = [
      // ⓪ 右值是本文件辅助函数，函数体内过滤（k1）
      "function noteTextRows(e) { return e.filter(x => x[2].trim()).map(x => x) }\n" +
        'const p = { _note_texts: noteTextRows([]) }',
      // ① 就地 filter（k2 / kPl kit）
      "const texts = (s.texts ?? []).filter(t => String(t?.text ?? '').trim())\n" +
        'if (texts.length) sub._note_texts = texts.map(t => t)',
      // ② if (xxx.trim()) 守住赋值（k4/k5/k7）
      "if (narrativeText.trim()) { sub._note_texts = [{ title: '说明' }] }",
      // ③ texts.length 守住赋值
      'if (texts.length) sub._note_texts = texts',
      // ④ 闸门变量先 trim（k3）
      "const narrative = String(s.n ?? '').trim()\nif (narrative) sub._note_texts = [{ text: narrative }]",
      // ⑤ 闸门变量来自辅助函数，函数体内过滤（k6）
      "function noteTexts(n) { const text = (n || '').trim(); if (!text) return undefined; return [{ text }] }\n" +
        'const texts = noteTexts(snap.narrativeText)\nif (texts) sub._note_texts = texts',
    ]
    ok.forEach((src, i) => {
      expect(hasEmptyTextGate(src), `形态${i} 应被认作有闸门`).toBe(true)
    })

    // 无闸门直写必须不认
    const bad = [
      "sub._note_texts = [{ section: 'x', title: '说明', text: raw }]",
      'sub._note_texts = snapshot.texts',
      // 有 filter 但过滤的不是文本（只去重表名），不算闸门
      'const names = list.filter(n => !pushed.has(n))\nsub._note_texts = snapshot.texts',
      // 辅助函数存在但体内不过滤
      'function build(n) { return [{ text: n }] }\nconst texts = build(x)\nif (texts) sub._note_texts = texts',
    ]
    bad.forEach((src, i) => {
      expect(hasEmptyTextGate(src), `无闸门形态${i} 不该被认作有闸门`).toBe(false)
    })

    // 多处赋值只要有一处无闸门，整体必须打红（every 语义）
    expect(
      hasEmptyTextGate(
        "if (a.trim()) sub._note_texts = [{ text: a }]\nsub2._note_texts = [{ text: raw }]",
      ),
      'every 语义失效：一处无闸门也放过了',
    ).toBe(false)
  })

  it('标签列 key 一律 `label`（推 columns 的循环）', () => {
    const bad: string[] = []
    for (const cycle of ALL_CYCLES) {
      const src = mapSrc(cycle)
      for (const m of src.matchAll(/isLabel\s*:\s*true/g)) {
        // 取该列定义所在的 `{...}` 片段，检查其 key
        const start = src.lastIndexOf('{', m.index ?? 0)
        const seg = src.slice(start, (m.index ?? 0) + 40)
        if (!/key\s*:\s*'label'/.test(seg)) bad.push(`${cycle}: ${seg.replace(/\s+/g, ' ').slice(0, 70)}`)
      }
    }
    expect(bad, `标签列 key 不是 label：${bad.join(' | ')}`).toEqual([])
  })
})
