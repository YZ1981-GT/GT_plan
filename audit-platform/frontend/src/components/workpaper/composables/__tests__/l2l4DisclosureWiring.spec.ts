/**
 * L2 应付利息 / L4 应付债券 —— 披露接线与契约守卫（Wave 1「先打红」）
 *
 * spec: .kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/ Wave 1 Task 3
 *
 * ─── 判据分两类，失败消息必须写明类别 ────────────────────────────────────────
 *
 * 【类 A = 独立口径判据】现在应**全绿**。红了说明守卫自身有缺陷，不是被测实现有问题。
 *   来源：附注模板真实表名/章节号（openpyxl 直读派生的 note_template_*.json）、
 *   平台惯例、替身反向自检、扫描面非空自检、已经正确的接线（防回退）。
 *
 * 【类 B = 被测实现】现在应**全红**。每条消息带「这是预期的 Wave 1 打红结果」。
 *
 * ─── 实现约束（平台已踩过的坑，勿简化）────────────────────────────────────────
 * - REPO_ROOT 用双哨兵**具体文件**向上查找，禁写死回退级数（本目录实为 7 级）。
 * - 截函数体先用**圆括号配对**跳过参数列表再找 `{`（多行签名 + 内联返回类型注解
 *   会让「声明后第一个 `{`」命中类型字面量）。表达式体箭头函数无花括号，用圆括号
 *   配对取实参区。
 * - 「A 真的被 B 调用」的判据必须落在 **B 的函数体/实参区内**，整份源码
 *   `toContain` 会被 import 行的标识符冒充。
 * - 标签存在性断言带边界：`toContain('<Foo')` 会被 `<FooREMOVED` 骗过。
 * - 读源码前必 `stripComments()`，且配反向自检（否则计数恒 0 = 空转）。
 *   剥注释按区分区：`<style>` 整段丢 / 模板只剥 HTML 注释 / 只在 `<script>` 剥 JS
 *   注释（`accept="image/*"` 的 `/*` 会被当块注释起点）。
 * - 断言消息体只用 ASCII 符号 + 中文汉字（`=>` `包含于` `-`），禁 `⇒` `⊆` `−` emoji
 *   （GBK 不可编码会让整条消息转义成 \uXXXX）。
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'

// ═══════════════════════════════════════════════════════════════════════════
// 0. REPO_ROOT —— 双哨兵具体文件向上查找
// ═══════════════════════════════════════════════════════════════════════════

const SENTINELS = [
  'backend/data/note_template_listed.json',
  '.kiro/steering/memory.md',
] as const

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 32; i += 1) {
    if (SENTINELS.every((s) => existsSync(resolve(dir, s)))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(
    `仓库根定位失败（双哨兵 ${SENTINELS.join(' + ')} 未同时命中）。起点 ${__dirname}`,
  )
}

const REPO_ROOT = findRepoRoot()
const WP_DIR = resolve(
  REPO_ROOT,
  'audit-platform/frontend/src/components/workpaper',
)

function readRepo(rel: string): string {
  const p = resolve(REPO_ROOT, rel)
  if (!existsSync(p)) throw new Error(`文件不存在: ${rel}`)
  return readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

function readWp(rel: string): string {
  const p = resolve(WP_DIR, rel)
  if (!existsSync(p)) throw new Error(`workpaper 下文件不存在: ${rel}`)
  return readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. 剥注释 —— 带字符串状态 + 按区分区
// ═══════════════════════════════════════════════════════════════════════════

/** 剥 JS/TS 注释（带字符串与模板字符串状态，`/*` 在字符串内不算注释起点） */
function stripJsComments(src: string): string {
  let out = ''
  let i = 0
  const n = src.length
  while (i < n) {
    const c = src[i]
    // 字符串字面量：原样保留（内含 // 或 /* 不算注释）
    if (c === "'" || c === '"' || c === '`') {
      const quote = c
      out += c
      i += 1
      while (i < n) {
        if (src[i] === '\\') {
          out += src[i] + (src[i + 1] ?? '')
          i += 2
          continue
        }
        out += src[i]
        if (src[i] === quote) {
          i += 1
          break
        }
        i += 1
      }
      continue
    }
    if (c === '/' && src[i + 1] === '/') {
      while (i < n && src[i] !== '\n') i += 1
      continue
    }
    if (c === '/' && src[i + 1] === '*') {
      i += 2
      while (i < n && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    out += c
    i += 1
  }
  return out
}

/** 剥 HTML 注释 */
function stripHtmlComments(src: string): string {
  return src.replace(/<!--[\s\S]*?-->/g, '')
}

/**
 * SFC / TS 通用剥注释：
 * - `<style>` 整段丢弃（CSS 注释与选择器都不参与源码判据）
 * - `<template>` 只剥 HTML 注释（属性里的 `image/*` 不得被当块注释起点）
 * - `<script>` 剥 JS 注释
 * - 纯 `.ts` 走 JS 路径
 */
function stripComments(src: string): string {
  if (!/<template[\s>]/.test(src) && !/<script[\s>]/.test(src)) {
    return stripJsComments(src)
  }
  let out = src.replace(/<style[\s\S]*?<\/style>/g, '')
  out = out.replace(/<template([\s\S]*?)<\/template>/g, (_m, body: string) =>
    `<template${stripHtmlComments(body)}</template>`,
  )
  out = out.replace(/<script([^>]*)>([\s\S]*?)<\/script>/g, (_m, attrs: string, body: string) =>
    `<script${attrs}>${stripJsComments(body)}</script>`,
  )
  return out
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. 源码结构提取 —— 圆括号配对 / 花括号配对 / 标签属性区
// ═══════════════════════════════════════════════════════════════════════════

function esc(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** 从 `from` 处的开括号起做配对，返回闭括号下标（找不到返回 -1）。跳过字符串。 */
function matchPair(src: string, from: number, open: string, close: string): number {
  if (src[from] !== open) return -1
  let depth = 0
  let i = from
  while (i < src.length) {
    const c = src[i]
    if (c === "'" || c === '"' || c === '`') {
      const q = c
      i += 1
      while (i < src.length) {
        if (src[i] === '\\') {
          i += 2
          continue
        }
        if (src[i] === q) break
        i += 1
      }
      i += 1
      continue
    }
    if (c === open) depth += 1
    else if (c === close) {
      depth -= 1
      if (depth === 0) return i
    }
    i += 1
  }
  return -1
}

const STATEMENT_HINTS = /\b(return|const|let|var|await|if|for|while|throw|try)\b|[=;]/

/**
 * 截取具名函数的函数体（不含外层花括号）。支持三形态：
 *   `function f(...) {}` / `const f = (...) => {}` / `f(() => {})` 调用式回调（如 onMounted）
 * 先用圆括号配对跳过参数列表，再逐个候选 `{` 配对并要求块内含语句特征
 * （跳过内联返回类型注解 `): Promise<{ a: X }> {`）。
 * 找不到返回空串。
 */
function fnBody(rawSrc: string, name: string): string {
  const src = rawSrc
  const patterns = [
    new RegExp(`(?:async\\s+)?function\\s+${esc(name)}\\s*\\(`),
    new RegExp(`(?:const|let|var)\\s+${esc(name)}\\s*[:=][^=]*?(?:async\\s*)?\\(`),
    new RegExp(`\\b${esc(name)}\\s*\\(`),
  ]
  for (const re of patterns) {
    const m = re.exec(src)
    if (!m) continue
    // m[0] 以 `(` 结尾
    const openParen = m.index + m[0].length - 1
    const closeParen = matchPair(src, openParen, '(', ')')
    if (closeParen < 0) continue

    // 🔴 两个搜索窗口，顺序不可颠倒：
    //   ① 闭括号之后 —— 覆盖 `function f(...) {}` 与 `const f = (...) => {}`
    //      （须逐个候选 `{` 配对以跳过内联返回类型注解 `): Promise<{ ok: X }> {`）
    //   ② 圆括号之内 —— 覆盖**调用式回调** `onMounted(() => {...})`：
    //      这种形态的函数体在实参区里，只搜 ① 必然截不出（守卫自身缺陷，
    //      正是「三形态自检」那条用例抓出来的）。
    for (const [from, to] of [
      [closeParen + 1, src.length],
      [openParen + 1, closeParen],
    ] as const) {
      let cursor = from
      for (let guard = 0; guard < 12; guard += 1) {
        const braceIdx = src.indexOf('{', cursor)
        if (braceIdx < 0 || braceIdx >= to) break
        const end = matchPair(src, braceIdx, '{', '}')
        if (end < 0 || end > to) break
        const body = src.slice(braceIdx + 1, end)
        if (STATEMENT_HINTS.test(body)) return body
        cursor = end + 1
      }
    }
  }
  return ''
}

/**
 * 截取调用 `name(...)` 的实参区（表达式体箭头函数无花括号，只能靠圆括号配对）。
 * 找不到返回空串。
 */
function callArgs(rawSrc: string, name: string): string {
  const re = new RegExp(`\\b${esc(name)}\\s*\\(`)
  const m = re.exec(rawSrc)
  if (!m) return ''
  const openParen = m.index + m[0].length - 1
  const close = matchPair(rawSrc, openParen, '(', ')')
  if (close < 0) return ''
  return rawSrc.slice(openParen + 1, close)
}

/** 截取标签的属性区（`<Foo ... >` 之间），带标签名边界。找不到返回空串。 */
function tagAttrs(rawSrc: string, tag: string): string {
  const re = new RegExp(`<${esc(tag)}(?=[\\s/>])`)
  const m = re.exec(rawSrc)
  if (!m) return ''
  let i = m.index + m[0].length
  while (i < rawSrc.length) {
    const c = rawSrc[i]
    if (c === '"' || c === "'") {
      const q = c
      i += 1
      while (i < rawSrc.length && rawSrc[i] !== q) i += 1
      i += 1
      continue
    }
    if (c === '>') return rawSrc.slice(m.index + m[0].length, i)
    i += 1
  }
  return ''
}

/** 标签存在性（带名字边界，`<FooREMOVED` 不算命中） */
function hasTag(rawSrc: string, tag: string): boolean {
  return new RegExp(`<${esc(tag)}(?=[\\s/>])`).test(rawSrc)
}

/**
 * 抽 TS 对象字面量值：`export const NAME = { ... }`，按 **ASCII 花括号**配对
 * （源文字里的全角「（）」不参与配对）。对不存在的常量必须 throw。
 */
function tsObjectLiteral(rawSrc: string, name: string): string {
  const re = new RegExp(`\\b${esc(name)}\\s*(?::[^=]*)?=\\s*\\{`)
  const m = re.exec(rawSrc)
  if (!m) throw new Error(`常量 ${name} 未找到（守卫解析失效或已改名）`)
  const openIdx = m.index + m[0].length - 1
  const close = matchPair(rawSrc, openIdx, '{', '}')
  if (close < 0) throw new Error(`常量 ${name} 花括号未配对`)
  return rawSrc.slice(openIdx + 1, close)
}

/** 从对象字面量体里抽 `key: '值'` 对（值为单/双引号字符串） */
function literalEntries(body: string): Record<string, string> {
  const out: Record<string, string> = {}
  const re = /(\w+)\s*:\s*(['"])((?:\\.|(?!\2).)*)\2/g
  let m: RegExpExecArray | null
  while ((m = re.exec(body)) !== null) {
    out[m[1]] = m[3]
  }
  return out
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. 附注模板事实（判据真源，独立口径）
// ═══════════════════════════════════════════════════════════════════════════

interface TplColumn {
  key?: string
  label?: string
  is_label?: boolean
  group?: string
  flat?: boolean
}
interface TplTable {
  name?: string
  headers?: string[]
  columns?: TplColumn[]
  rows?: Array<{ label?: string; row_type?: string }>
}
interface TplSection {
  section_number?: string
  section_title?: string
  tables?: TplTable[]
}

const TEMPLATE_FILE = {
  listed: 'backend/data/note_template_listed.json',
  soe: 'backend/data/note_template_soe.json',
} as const

type Variant = keyof typeof TEMPLATE_FILE

const _tplCache = new Map<Variant, TplSection[]>()

function tplSections(variant: Variant): TplSection[] {
  const hit = _tplCache.get(variant)
  if (hit) return hit
  const doc = JSON.parse(readRepo(TEMPLATE_FILE[variant])) as { sections?: TplSection[] }
  const list = doc.sections ?? []
  _tplCache.set(variant, list)
  return list
}

/** 🔴 必须按 (章节号, 表名) 二元组索引：listed 有 63 个表名出现多次、soe 40 个， */
/**    按表名全局索引会命中会计政策章的空壳版本。 */
function tplSection(variant: Variant, sectionNumber: string): TplSection {
  const hits = tplSections(variant).filter(
    (s) => String(s.section_number ?? '').trim() === sectionNumber,
  )
  if (hits.length !== 1) {
    throw new Error(
      `模板 ${variant} 的章节 ${sectionNumber} 命中 ${hits.length} 个（期望恰好 1 个）`,
    )
  }
  return hits[0]
}

function tplTables(variant: Variant, sectionNumber: string): TplTable[] {
  return tplSection(variant, sectionNumber).tables ?? []
}

function tplTableNames(variant: Variant, sectionNumber: string): string[] {
  return tplTables(variant, sectionNumber).map((t) => String(t.name ?? ''))
}

function tplTable(variant: Variant, sectionNumber: string, tableName: string): TplTable {
  const hits = tplTables(variant, sectionNumber).filter((t) => t.name === tableName)
  if (hits.length !== 1) {
    throw new Error(
      `模板 ${variant} ${sectionNumber} 的表 "${tableName}" 命中 ${hits.length} 个（期望 1 个）`,
    )
  }
  return hits[0]
}

/** 表名在该模板全库出现多次的个数（用于证明「必须按二元组索引」这条前提成立） */
function duplicatedTableNameCount(variant: Variant): number {
  const counter = new Map<string, number>()
  for (const s of tplSections(variant)) {
    for (const t of s.tables ?? []) {
      const n = String(t.name ?? '')
      if (!n) continue
      counter.set(n, (counter.get(n) ?? 0) + 1)
    }
  }
  return [...counter.values()].filter((v) => v > 1).length
}

// ── 逐字锚点（实证冻结，改模板才允许改这里）───────────────────────────────

const L4_SECTION = { listed: '五、46', soe: '八、50' } as const
const L4_WITHIN1Y_SECTION = { listed: '五、43', soe: '八、46' } as const
const L2_SECTION = { listed: '五、42', soe: '八、42' } as const

const EXPECTED_TABLE_COUNT: ReadonlyArray<[Variant, string, number]> = [
  ['listed', '五、46', 5],
  ['listed', '五、43', 5],
  ['listed', '五、42', 7],
  ['soe', '八、50', 2],
  ['soe', '八、46', 2],
  ['soe', '八、42', 6],
  ['soe', '八、45', 1],
]

const L4_LISTED_MAIN_TABLES = [
  '应付债券',
  '应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）',
  '应付债券（续）',
  '（3）划分为金融负债的其他金融工具',
  '期末发行在外的优先股、永续债等其他金融工具变动情况',
] as const

const L4_SOE_MAIN_TABLES = [
  '应付债券',
  '应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）',
] as const

/** 五、43 里属于 L4 的两张表（另三张属 L3 / L5） */
const L4_LISTED_WITHIN1Y_TABLES = [
  '一年内到期的应付债券',
  '一年内到期的应付债券（续）',
] as const

const L4_SOE_WITHIN1Y_TABLES = [
  '（2）一年内到期的应付债券',
  '一年内到期的应付债券',
] as const

/** L2 落点：K3 章节内的两张表（第二张两版不同名，禁统一） */
const L2_TABLES = {
  listed: ['应付利息', '重要的逾期未付利息'],
  soe: ['应付利息', '重要的已逾期未支付的利息情况'],
} as const

const L2_INTEREST_ROWS = {
  listed: [
    '分期付息到期还本的长期借款利息',
    '企业债券利息',
    '短期借款应付利息',
    '划分为金融负债的优先股\\永续债利息',
    '其中：工具1',
    '工具2',
    '合计',
  ],
  soe: [
    '分期付息到期还本的长期借款利息',
    '企业债券利息',
    '短期借款应付利息',
    '划分为金融负债的优先股\\永续债利息',
    '其他利息',
    '合计',
  ],
} as const

// ═══════════════════════════════════════════════════════════════════════════
// 4. 被测文件
// ═══════════════════════════════════════════════════════════════════════════

const TAB_FILES = {
  L2Listed: 'l2/core/L2TabDisclosureListed.vue',
  L2Soe: 'l2/core/L2TabDisclosureSoe.vue',
  L4Listed: 'l4/core/L4TabDisclosureListed.vue',
  L4Soe: 'l4/core/L4TabDisclosureSoe.vue',
} as const

type TabKey = keyof typeof TAB_FILES

const HOST_FILES = {
  L2: 'GtL2InterestPayable.vue',
  L4: 'GtL4BondsPayable.vue',
} as const

const HOST_OF: Record<TabKey, keyof typeof HOST_FILES> = {
  L2Listed: 'L2',
  L2Soe: 'L2',
  L4Listed: 'L4',
  L4Soe: 'L4',
}

const TAB_TAG: Record<TabKey, string> = {
  L2Listed: 'L2TabDisclosureListed',
  L2Soe: 'L2TabDisclosureSoe',
  L4Listed: 'L4TabDisclosureListed',
  L4Soe: 'L4TabDisclosureSoe',
}

const L4_TABS: readonly TabKey[] = ['L4Listed', 'L4Soe']
const L2_TABS: readonly TabKey[] = ['L2Listed', 'L2Soe']
const ALL_TABS = Object.keys(TAB_FILES) as TabKey[]

const _srcCache = new Map<string, string>()
function tabSrc(key: TabKey): string {
  const hit = _srcCache.get(key)
  if (hit !== undefined) return hit
  const clean = stripComments(readWp(TAB_FILES[key]))
  _srcCache.set(key, clean)
  return clean
}

function hostSrc(key: keyof typeof HOST_FILES): string {
  const ck = `host:${key}`
  const hit = _srcCache.get(ck)
  if (hit !== undefined) return hit
  const clean = stripComments(readWp(HOST_FILES[key]))
  _srcCache.set(ck, clean)
  return clean
}

const L4_MAP_SRC = stripComments(readWp('composables/l4NoteSectionMap.ts'))
const L4_MAP_RAW = readWp('composables/l4NoteSectionMap.ts')
const K3_MAP_SRC = stripComments(readWp('composables/k3NoteSectionMap.ts'))
const COVERAGE_SPEC_PATH = '__tests__/disclosureAutoSyncCoverage.spec.ts'
const COVERAGE_RAW = readWp(COVERAGE_SPEC_PATH)

/**
 * 四个披露 Tab 的**纯文件名** —— 从 `TAB_FILES` 派生而非再抄一遍。
 *
 * 🔴 原先「已从 MISSING_SYNC_PATH 移出」等断言各自内联一份四条目字面量数组，
 *    组件改名时 `TAB_FILES` 会因 `readWp` 读不到文件而立刻打红，
 *    但那些内联副本只会**静默失效**（`includes` 恒 false ⇒ 判据变成恒真）。
 */
const L2L4_TAB_FILES: readonly string[] = Object.values(TAB_FILES).map(
  (p) => p.split('/').pop()!,
)

const RED = '这是预期的 Wave 1 打红结果（Wave 5~7 Task 14~22 修复）'

/**
 * 🔴 覆盖率守卫里**当前仍被登记为「无同步链路」**的 L2/L4 条目（从 `PERMANENT_EXEMPT` /
 *    `SYNC_PATH_GAP` 两个**活跃数组声明体**里取，`[类 A]` 与 `[类 B]` 共用同一语义量）。
 *
 * 🔴 为什么不用 `stripComments(COVERAGE_RAW)` 后全文件 `includes`（原写法）：
 *    disclosureAutoSyncCoverage 里有一个巨大的「墓碑注释块」——原 `MISSING_SYNC_PATH`
 *    的历史快照，含四条目的**带引号字面量**。实测 `stripComments` 对这种内嵌字符串
 *    与 `//` 注释的超大 `/* *​/` 块**并不可靠**（变异检验 M19：删空活跃登记后，全文件
 *    扫描仍命中墓碑快照 ⇒ `stillDeclared` 恒 = 4 ⇒ 判据**假绿**、`[类 B]` 还**永远无法转绿**）。
 *    按数组名 + 首个行首 `]` 只截**活跃声明体**，对墓碑与 stripComments 质量都免疫。
 */
function declaredNoSyncInCoverage(
  raw: string = COVERAGE_RAW,
  names: readonly string[] = L2L4_TAB_FILES,
): string[] {
  const pickBody = (name: string): string =>
    new RegExp(`const\\s+${name}\\b[\\s\\S]*?\\n\\]`).exec(raw)?.[0] ?? ''
  // 数组体内只有 `//` 行注释（无嵌套块注释），stripComments 在此可靠；
  // 且行注释里不含 `'XTabDisclosure*.vue'` 带引号形态，剥不剥都只命中真实条目。
  const body = stripComments(`${pickBody('PERMANENT_EXEMPT')}\n${pickBody('SYNC_PATH_GAP')}`)
  return names.filter((n) => body.includes(`'${n}'`))
}

// ═══════════════════════════════════════════════════════════════════════════
// 5. 纯判据函数（供真实源码与替身共用，替身反向自检靠它）
// ═══════════════════════════════════════════════════════════════════════════

const PAYLOAD_BUILDERS = ['buildL2SyncPayload', 'buildL4SyncPayload'] as const

/** 判据①：Tab 内必须有 useDisclosureAutoSync，且同步函数体内真的调了 payload 构造器 */
function checkAutoSyncWiring(src: string): { ok: boolean; detail: string } {
  const problems: string[] = []
  if (!/\buseDisclosureAutoSync\s*\(/.test(src)) {
    problems.push('未调用 useDisclosureAutoSync')
  }
  const syncFn = findSyncFnName(src)
  if (!syncFn) {
    problems.push('未找到同步函数（期望 syncToDisclosureNotes 或 syncToNotes）')
  } else {
    const body = fnBody(src, syncFn)
    if (!body) {
      problems.push(`同步函数 ${syncFn} 的函数体未截出（守卫解析失效或函数为空）`)
    } else {
      const called = PAYLOAD_BUILDERS.filter((b) => new RegExp(`\\b${b}\\s*\\(`).test(body))
      if (called.length === 0) {
        problems.push(
          `同步函数 ${syncFn} 体内未调用任何 payload 构造器（${PAYLOAD_BUILDERS.join(' / ')}）`,
        )
      }
    }
  }
  return { ok: problems.length === 0, detail: problems.join('；') }
}

const SYNC_FN_CANDIDATES = ['syncToDisclosureNotes', 'syncToNotes', 'syncToNote'] as const

function findSyncFnName(src: string): string | null {
  for (const n of SYNC_FN_CANDIDATES) {
    if (new RegExp(`(?:function\\s+${n}\\b|(?:const|let|var)\\s+${n}\\s*[:=])`).test(src)) return n
  }
  return null
}

/**
 * 判据②：禁自调度。判据落在**同步函数的函数体内** ——
 * `scheduleAutoSync(syncToDisclosureNotes)` 写在同步函数自己体内 = 800ms 周期重复 POST，
 * 且会骗过平台覆盖率守卫（它只看有没有该调用）。
 * 复合判据：同步函数必须存在（存在性这一半现在是红的），且其体内不得自调度。
 */
function checkNoSelfSchedule(src: string): { ok: boolean; detail: string } {
  const syncFn = findSyncFnName(src)
  if (!syncFn) {
    return {
      ok: false,
      detail: '同步函数不存在（无同步链路，禁自调度这条无处施加）',
    }
  }
  const body = fnBody(src, syncFn)
  if (!body) {
    return { ok: false, detail: `同步函数 ${syncFn} 的函数体未截出` }
  }
  const args = callArgs(body, 'scheduleAutoSync')
  if (args && new RegExp(`\\b${syncFn}\\b`).test(args)) {
    return {
      ok: false,
      detail: `同步函数 ${syncFn} 体内把自己传给了 scheduleAutoSync（自调度）`,
    }
  }
  return { ok: true, detail: '' }
}

/** 判据⑤：声明的子表名必须与模板逐字一致，且模板表必须被完整声明 */
function checkSubtableNames(
  declared: readonly string[],
  templateNames: readonly string[],
): { ok: boolean; orphans: string[]; missing: string[] } {
  const orphans = declared.filter((d) => !templateNames.includes(d))
  const missing = templateNames.filter((t) => !declared.includes(t))
  return { ok: orphans.length === 0 && missing.length === 0, orphans, missing }
}

/**
 * 判据⑦：同一张附注子表键只许有**指定的那一个**构造器产出。
 *
 * 🔴 不能只判 `owners.length === 1` —— 那会放行「唯一写者是 K3」这个**正是要消除的**
 * 现状（实测：K3 写 sub[T.interest]、L2 构造器不存在 ⇒ owners=['buildK3SyncPayload']
 * ⇒ 朴素判据 ok=true = 假绿）。收敛目标是「唯一写者 == buildL2SyncPayload」，
 * 故必须把期望写者作为入参一起判。
 */
function checkSingleWriter(
  writers: ReadonlyArray<{ builder: string; produces: readonly string[] }>,
  tableName: string,
  expectedOwner: string,
): { ok: boolean; owners: string[] } {
  const owners = writers.filter((w) => w.produces.includes(tableName)).map((w) => w.builder)
  return { ok: owners.length === 1 && owners[0] === expectedOwner, owners }
}

// ═══════════════════════════════════════════════════════════════════════════
// 类 A —— 独立口径判据：现在应全绿
// ═══════════════════════════════════════════════════════════════════════════

describe('[类 A] 扫描面非空自检（防守卫空转）', () => {
  it('REPO_ROOT 与被测文件全部可解析', () => {
    expect(existsSync(resolve(REPO_ROOT, SENTINELS[0]))).toBe(true)
    expect(existsSync(resolve(REPO_ROOT, SENTINELS[1]))).toBe(true)
    for (const [k, rel] of Object.entries(TAB_FILES)) {
      expect(existsSync(resolve(WP_DIR, rel)), `[类 A] 披露 Tab 缺失: ${k} -> ${rel}`).toBe(true)
    }
    for (const [k, rel] of Object.entries(HOST_FILES)) {
      expect(existsSync(resolve(WP_DIR, rel)), `[类 A] 宿主缺失: ${k} -> ${rel}`).toBe(true)
    }
    expect(existsSync(resolve(WP_DIR, COVERAGE_SPEC_PATH))).toBe(true)
  })

  /**
   * 🔴 这是**扫描面非空自检**，它要证明的命题只有一个：
   *    「表名会重复，所以索引必须用 (章节号, 表名) 二元组而不能只用表名」。
   *
   * 该命题只需要「重复数远大于 0」。原判据却写成
   * `expect(duplicatedTableNameCount('listed')).toBe(63)` —— 把附注模板的
   * **当前精确内容**焊进了一个只关心「非零」的自检里。
   *
   * 代价 2026-08-15 实测：并发会话往 `note_template_listed.json` 加了章节，
   * 重复数 63 → **64**，这条立刻打红。红的位置在「扫描面自检」，
   * 提示是「两份模板章节数与表名重复数非零」，而实际非零得很 ——
   * 排查者必须读到第 4 行才发现真正的失败原因是个无关的等值断言。
   * 附注模板是**多 spec 共享的高频改动文件**，把它的精确计数写进
   * 与之无关的自检里，等于给每个改模板的人埋一颗哑弹。
   *
   * 改为地板：数字只用来证明「远离 0」，模板增长不再打红。
   * 真要锁模板内容，该锁在附注模板自己的契约测试里（那里有 openpyxl 三向比对）。
   */
  it('模板扫描面下限：两份模板章节数与表名重复数非零', () => {
    expect(tplSections('listed').length).toBeGreaterThan(150)
    expect(tplSections('soe').length).toBeGreaterThan(150)
    // 「必须按 (章节号, 表名) 二元组索引」这条前提的量化证据 —— 地板而非等值
    expect(
      duplicatedTableNameCount('listed'),
      '[类 A] 上市模板的重复表名数掉到 20 以下 —— 要么模板被截断，要么 ' +
        'duplicatedTableNameCount 的解析路径漂了。此时「按二元组索引」的前提失去证据，' +
        '下游所有按 (章节号, 表名) 定位的判据都可能在空集上恒真。',
    ).toBeGreaterThan(20)
    expect(duplicatedTableNameCount('soe')).toBeGreaterThan(20)
  })

  it('被测源码非空且已剥注释（stripComments 反向自检）', () => {
    for (const k of ALL_TABS) {
      const raw = readWp(TAB_FILES[k])
      const clean = tabSrc(k)
      expect(raw.length, `[类 A] ${k} 原始源码为空`).toBeGreaterThan(1000)
      expect(clean.length, `[类 A] ${k} 剥注释后为空`).toBeGreaterThan(500)
      // 反向自检：原始源码确实含被剥字样，剥后不含
      expect(raw.includes('<style'), `[类 A] ${k} 原始源码应含 <style> 段`).toBe(true)
      expect(clean.includes('<style'), `[类 A] ${k} 剥注释后不应残留 <style> 段`).toBe(false)
    }
    // TS 侧：l4NoteSectionMap.ts 顶部有块注释
    expect(L4_MAP_RAW.includes('权威来源 note_template_variant_matrix.json')).toBe(true)
    expect(L4_MAP_SRC.includes('权威来源 note_template_variant_matrix.json')).toBe(false)
  })

  it('stripComments 不误伤字符串里的注释定界符（accept="image/*" 一类）', () => {
    const fake = [
      '<template>',
      '  <input accept="image/*" />',
      '  <!-- HTML_COMMENT_MARK -->',
      '  <span>KEEP_TEMPLATE</span>',
      '</template>',
      '<script setup lang="ts">',
      "const glob = '/* not a comment */'",
      '// JS_LINE_MARK',
      '/* JS_BLOCK_MARK */',
      'const keep = 1',
      '</script>',
      '<style scoped>',
      '.a { color: red } /* CSS_MARK */',
      '</style>',
    ].join('\n')
    const clean = stripComments(fake)
    expect(clean.includes('accept="image/*"')).toBe(true)
    expect(clean.includes('KEEP_TEMPLATE')).toBe(true)
    expect(clean.includes('const keep = 1')).toBe(true)
    expect(clean.includes("'/* not a comment */'")).toBe(true)
    expect(clean.includes('HTML_COMMENT_MARK')).toBe(false)
    expect(clean.includes('JS_LINE_MARK')).toBe(false)
    expect(clean.includes('JS_BLOCK_MARK')).toBe(false)
    expect(clean.includes('CSS_MARK')).toBe(false)
  })

  it('declaredNoSyncInCoverage 只认活跃数组、免疫墓碑注释快照（tombstone-immunity 替身自检）', () => {
    // 🔴 合成源：活跃 PERMANENT_EXEMPT **不含** L2，但墓碑块（/* *​/）里留着 L2 的历史快照。
    //    旧写法（全文件 stripComments + includes）实测对这种超大墓碑块不可靠
    //    （变异检验实测 raw=2 / stripped=2 ⇒ L2 仍被数进来 ⇒ 判据假绿、[类 B] 永不转绿）；
    //    declaredNoSyncInCoverage 只截活跃声明体，对墓碑与 stripComments 质量都免疫。
    const fixture = [
      'const PERMANENT_EXEMPT: readonly string[] = [',
      "  'H5TabDisclosureListed.vue',",
      ']',
      'const SYNC_PATH_GAP: readonly string[] = [',
      "  'L4TabDisclosureListed.vue',",
      ']',
      '/*',
      ' * 墓碑：原 MISSING_SYNC_PATH 历史快照（不参与断言）',
      "  'L2TabDisclosureListed.vue',",
      "  'L4TabDisclosureListed.vue',",
      ' */',
    ].join('\n')
    const names = ['L2TabDisclosureListed.vue', 'L4TabDisclosureListed.vue']
    // L2 只在墓碑里 → 必须被忽略；L4 在活跃 SYNC_PATH_GAP → 必须命中
    expect(declaredNoSyncInCoverage(fixture, names)).toEqual(['L4TabDisclosureListed.vue'])
    // 反向自检：合成源确实在墓碑里含 L2（否则本测试恒真、无区分力）
    expect(fixture.includes("'L2TabDisclosureListed.vue'")).toBe(true)
  })
})

describe('[类 A] 源码结构提取器自检（fnBody / callArgs / tagAttrs / tsObjectLiteral）', () => {
  it('fnBody 三形态都能截出，且跳过参数列表与内联返回类型注解', () => {
    const a = 'function alpha(payload: { rows: X[] }) { const v = 1; return v }'
    expect(fnBody(a, 'alpha')).toContain('const v = 1')
    expect(fnBody(a, 'alpha')).not.toContain('rows: X[]')

    const b = 'const beta = async (p: string): Promise<{ ok: boolean }> => { await go(); return { ok: true } }'
    const bBody = fnBody(b, 'beta')
    expect(bBody).toContain('await go()')
    expect(bBody).not.toContain('ok: boolean')

    // 形态三 = 调用式回调，函数体在**圆括号之内**（只搜闭括号之后必然截不出）
    const c = 'onMounted(() => { loadAll(); })'
    expect(fnBody(c, 'onMounted')).toContain('loadAll()')

    // 反向自检：两个搜索窗口的优先级不可颠倒 —— 具名函数必须优先取「闭括号之后」
    // 那个块。若先搜实参区，`function gamma(cb = () => { inArgs() }) { real() }`
    // 会截出 `inArgs()`（参数默认值里的箭头函数体）而不是真正的函数体。
    const d = 'function gamma(cb = () => { inArgs() }) { real(); return 1 }'
    const dBody = fnBody(d, 'gamma')
    expect(dBody).toContain('real()')
    expect(dBody).not.toContain('inArgs()')
  })

  it('fnBody 对不存在的函数返回空串（不抛、不误截邻居）', () => {
    const src = 'function one() { return 1 }\nfunction two() { return 2 }'
    expect(fnBody(src, 'nope')).toBe('')
    expect(fnBody(src, 'one')).toContain('return 1')
    expect(fnBody(src, 'one')).not.toContain('return 2')
  })

  it('callArgs 能取表达式体箭头函数的实参区（无花括号）', () => {
    expect(callArgs('const x = computed(() => calcTotal(rows))', 'computed')).toContain('calcTotal(rows)')
    expect(callArgs('scheduleAutoSync(syncToDisclosureNotes)', 'scheduleAutoSync')).toBe(
      'syncToDisclosureNotes',
    )
    expect(callArgs('nothing here', 'scheduleAutoSync')).toBe('')
  })

  it('hasTag / tagAttrs 带标签名边界（`<FooREMOVED` 不算命中）', () => {
    expect(hasTag('<Foo :a="1" />', 'Foo')).toBe(true)
    expect(hasTag('<FooREMOVED :a="1" />', 'Foo')).toBe(false)
    expect(tagAttrs('<Foo :a="1" :b="x > 2" />', 'Foo')).toContain(':b="x > 2"')
    expect(tagAttrs('<Bar />', 'Foo')).toBe('')
  })

  it('tsObjectLiteral 按 ASCII 花括号配对，全角括号不参与；对不存在常量必须 throw', () => {
    const src = "export const T = { a: '甲（含全角括号）', b: '乙' } as const"
    const body = tsObjectLiteral(src, 'T')
    expect(literalEntries(body)).toEqual({ a: '甲（含全角括号）', b: '乙' })
    expect(() => tsObjectLiteral(src, 'NOT_THERE')).toThrow(/未找到/)
  })
})

describe('[类 A] 附注模板锚点（判据真源，逐字实证冻结）', () => {
  it.each(EXPECTED_TABLE_COUNT)('%s %s 恰好 %i 张表', (variant, section, count) => {
    expect(
      tplTableNames(variant, section).length,
      `[类 A] 模板 ${variant} ${section} 表数与实证锚点不符（模板被改动？）`,
    ).toBe(count)
  })

  it('L4 上市 五、46 五张表名逐字一致', () => {
    expect(tplTableNames('listed', L4_SECTION.listed)).toEqual([...L4_LISTED_MAIN_TABLES])
  })

  it('L4 国企 八、50 两张表名逐字一致', () => {
    expect(tplTableNames('soe', L4_SECTION.soe)).toEqual([...L4_SOE_MAIN_TABLES])
  })

  it('L4 一年内到期两张表在 五、43 / 八、46（国企首表带序号前缀）', () => {
    const listed43 = tplTableNames('listed', L4_WITHIN1Y_SECTION.listed)
    for (const t of L4_LISTED_WITHIN1Y_TABLES) expect(listed43).toContain(t)
    expect(tplTableNames('soe', L4_WITHIN1Y_SECTION.soe)).toEqual([...L4_SOE_WITHIN1Y_TABLES])
    // 国企首表确实带 `（2）` 前缀（禁「顺手去掉」）
    expect(L4_SOE_WITHIN1Y_TABLES[0].startsWith('（2）')).toBe(true)
  })

  it('L2 落点两张表名逐字一致，且第二张两版不同名（禁统一）', () => {
    for (const v of ['listed', 'soe'] as const) {
      const names = tplTableNames(v, L2_SECTION[v])
      for (const t of L2_TABLES[v]) {
        expect(names, `[类 A] 模板 ${v} ${L2_SECTION[v]} 缺表 ${t}`).toContain(t)
      }
    }
    expect(L2_TABLES.listed[1]).not.toBe(L2_TABLES.soe[1])
  })

  it('L2「应付利息」行集逐字一致，且两版行标签序列不相等', () => {
    for (const v of ['listed', 'soe'] as const) {
      const rows = (tplTable(v, L2_SECTION[v], '应付利息').rows ?? []).map((r) =>
        String(r.label ?? ''),
      )
      expect(rows, `[类 A] ${v} 应付利息行集与实证锚点不符`).toEqual([...L2_INTEREST_ROWS[v]])
    }
    expect(L2_INTEREST_ROWS.listed.length).toBe(7)
    expect(L2_INTEREST_ROWS.soe.length).toBe(6)
    expect(L2_INTEREST_ROWS.listed).not.toEqual(L2_INTEREST_ROWS.soe)
    // 上市**没有**独立「其他」行；国企第 5 行是「其他利息」
    expect(L2_INTEREST_ROWS.listed).not.toContain('其他')
    expect(L2_INTEREST_ROWS.listed).not.toContain('其他利息')
    expect(L2_INTEREST_ROWS.soe[4]).toBe('其他利息')
    // 含一个真实反斜杠的行标签（TS 字面量需转义）
    expect(L2_INTEREST_ROWS.listed[3]).toContain('\\')
  })

  it('跨循环共享章节零交集：K3 表名与 L2 两张表名互不重叠', () => {
    for (const v of ['listed', 'soe'] as const) {
      const k3Body = tsObjectLiteral(
        K3_MAP_SRC,
        v === 'listed' ? 'K3_LISTED_SUBTABLE' : 'K3_SOE_SUBTABLE',
      )
      const k3Names = Object.values(literalEntries(k3Body))
      const l2Names = [...L2_TABLES[v]]
      // K3 自己也声明了「应付利息」两张表 = 写权冲突的量化证据（见判据⑦）
      const overlap = l2Names.filter((n) => k3Names.includes(n))
      expect(
        overlap.length,
        `[类 A] K3 与 L2 在 ${v} 侧共享表名 ${overlap.join(' / ')}（这是写权冲突的证据，非模板缺陷）`,
      ).toBe(2)
      // 除这两张外，K3 其余表名与 L2 零交集
      const others = k3Names.filter((n) => !l2Names.includes(n))
      expect(others.filter((n) => l2Names.includes(n))).toEqual([])
    }
  })

  it('五、43 五张表分属 L3 / L4 / L5，两两交集为空', () => {
    const names = tplTableNames('listed', '五、43')
    const l3 = names.filter((n) => n.includes('长期借款'))
    const l4 = names.filter((n) => n.includes('应付债券'))
    const l5 = names.filter((n) => n.includes('长期应付款'))
    expect(l3).toEqual(['一年内到期的长期借款'])
    expect(l4).toEqual([...L4_LISTED_WITHIN1Y_TABLES])
    expect(l5).toEqual(['一年内到期的长期应付款'])
    expect(l3.filter((n) => l4.includes(n))).toEqual([])
    expect(l4.filter((n) => l5.includes(n))).toEqual([])
    expect(l3.filter((n) => l5.includes(n))).toEqual([])
    expect(l3.length + l4.length + l5.length + 1).toBe(names.length) // +1 = 汇总表本身
  })

  it('L5 的一年内到期落点是 八、47（与 L4 的 八、46 不同章节，勿混）', () => {
    expect(tplTableNames('soe', '八、47')).toContain('（3）一年内到期的长期应付款')
    expect(tplTableNames('soe', '八、46')).not.toContain('（3）一年内到期的长期应付款')
  })
})

describe('[类 A] 已正确的接线（防回退）', () => {
  it.each(ALL_TABS)('%s: 宿主已传 :project-id（4/4 已传，防回退）', (key) => {
    const attrs = tagAttrs(hostSrc(HOST_OF[key]), TAB_TAG[key])
    expect(attrs, `[类 A] 宿主 ${HOST_FILES[HOST_OF[key]]} 未找到 <${TAB_TAG[key]}> 标签`).not.toBe('')
    expect(
      /:project-id\s*=/.test(attrs),
      `[类 A] 宿主漏传 :project-id 给 ${TAB_TAG[key]}。漏传即让披露同步永久静默失败（首行 if (!props.projectId) return），此前已 4/4 传齐，本条是防回退`,
    ).toBe(true)
  })

  it.each(ALL_TABS)('%s: 披露 Tab 已声明 projectId prop', (key) => {
    expect(/projectId\s*:\s*string/.test(tabSrc(key))).toBe(true)
  })

  it('L4 已有 buildL4SyncPayload（导出存在，Wave 5 只需接线不必新建）', () => {
    expect(/export\s+function\s+buildL4SyncPayload\s*\(/.test(L4_MAP_SRC)).toBe(true)
    expect(/export\s+function\s+buildL4ListedColumns\s*\(/.test(L4_MAP_SRC)).toBe(true)
    expect(/export\s+function\s+buildL4SoeColumns\s*\(/.test(L4_MAP_SRC)).toBe(true)
  })

  /**
   * 🔴 **跨文件锚定必须落在「行为事实」而不是「对方的写法」**
   *   （spec `guard-assertion-attribution-refactor` R5 / Property 12、13）
   *
   * 本条原先长这样：
   * ```ts
   * const m = /expect\(MISSING_SYNC_PATH\.length\)\.toBe\((\d+)\)/.exec(COVERAGE_RAW)
   * expect(m).not.toBeNull(); expect(Number(m![1])).toBe(6)
   * ...
   * expect(6 - 4).toBe(2)          // ← 「联动关系钉死」
   * ```
   * 四个缺陷，2026-08-15 实测逐条证实：
   *
   * ① **锚定对方的常量名 + 断言写法 + 具体数字**。覆盖率守卫按语义把
   *    `MISSING_SYNC_PATH` 拆成 `PERMANENT_EXEMPT`(4) + `SYNC_PATH_GAP`(2)
   *    —— 一次纯粹的改进 —— 本条就会打红。判据于是变成「禁止对方改进」。
   *
   * ② **对含注释原文做正则** ⇒ 反过来又**假绿**：拆表后覆盖率守卫的注释里
   *    留了一句「原判据是 `expect(MISSING_SYNC_PATH.length).toBe(6)`」解释为什么改，
   *    正则照样命中，本条继续报绿 —— 而它声称在守护的那个硬断言**已经不存在了**。
   *    同一条判据在「对方改好」时假红、在「对方删掉」时假绿，两个方向全错。
   *
   * ③ `COVERAGE_RAW.includes("'L2TabDisclosureListed.vue'")` 同样吃注释：
   *    拆表时保留的墓碑注释块含四条目的原始快照，即使真实登记全被删空也命中。
   *
   * ④ **`expect(6 - 4).toBe(2)` 是恒真的空操作** —— 两个字面量相减跟被测代码
   *    毫无关系，改动任何生产文件都不可能让它变红。它写着「联动关系钉死」，
   *    实际零校验，是本仓形态 E（判据只查字符串/只算常量）最干净的标本。
   *
   * 改造后：判据落在**「四条目仍被登记为无同步链路」这个事实**上，
   * 且只截**活跃数组声明体**再判（`declaredNoSyncInCoverage`）—— 对方叫什么常量名、
   * 用等值还是天花板、数字是几、墓碑注释里还留着什么历史快照，一概不管。
   */
  it('平台覆盖率守卫仍把 L2/L4 四条目登记为「无同步链路」（收敛时必须联动移出）', () => {
    // 🔴 只看**活跃数组声明体**（见 declaredNoSyncInCoverage 注释）：全文件 includes 会
    //    命中墓碑注释块里的历史快照 ⇒ 删空真实登记也照样绿（变异检验 M19 实测抓到）。
    const stillDeclared = declaredNoSyncInCoverage()
    expect(
      stillDeclared,
      `[类 A] 覆盖率守卫已不再把这些 Tab 登记为「无同步链路」：` +
        `${L2L4_TAB_FILES.filter((n) => !stillDeclared.includes(n)).join(' / ')}。\n` +
        `两种可能：① Wave 5~7 已接线并正确移出 → 本条与判据⑨应一并删除（本 spec 收口）；` +
        `② 有人误删了登记 → 覆盖率守卫会立刻在「每个无同步链路的披露 Tab 都必须已登记」` +
        `打红，去那边看。`,
    ).toEqual([...L2L4_TAB_FILES])

    // 覆盖率守卫必须仍持有**只许缩不许扩**的规模约束 —— 只认「有天花板」这个语义，
    // 不认常量名、不认数字：`toBeLessThanOrEqual(MAX_*)` 即合格。
    // 该断言是活跃代码（非注释），直接扫 COVERAGE_RAW 即可（墓碑块不含此形态）。
    expect(
      /toBeLessThanOrEqual\(\s*MAX_[A-Z_]+/.test(COVERAGE_RAW),
      `[类 A] 覆盖率守卫失去了「登记表只许缩不许扩」的规模约束。` +
        `没有这道天花板，新增披露 Tab 只要往登记表里加一条就能绕过同步链路检查。`,
    ).toBe(true)
  })

  it('L2 当前无金额录入控件（显式登记：判据⑧对 L2 暂不适用）', () => {
    for (const key of L2_TABS) {
      const src = tabSrc(key)
      const inputs = (src.match(/<el-input(?=[\s/>])/g) ?? []).length
      const numbers = (src.match(/<el-input-number(?=[\s/>])/g) ?? []).length
      const amounts = (src.match(/<WpAmountInput(?=[\s/>])/g) ?? []).length
      expect(
        inputs + numbers + amounts,
        `[类 A] ${key} 出现了金额/文本录入控件（当前实证为纯只读展示）。一旦 Wave 5 建了录入区块，判据⑧「金额列必须用 WpAmountInput」即对 L2 生效，须把 L2 纳入该判据的作用域`,
      ).toBe(0)
      // 只读展示口径：本地 fmtAmount 直接 toLocaleString（未收敛到 displayPrefs），
      // 属既有欠账，登记不在本 spec 范围内修。
      expect(src.includes('toLocaleString')).toBe(true)
    }
  })
})

describe('[类 A] 替身反向自检（判据本身有效性）', () => {
  const GOOD_TAB = [
    '<script setup lang="ts">',
    "import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'",
    "import { buildL4SyncPayload } from '../../composables/l4NoteSectionMap'",
    'const { scheduleAutoSync } = useDisclosureAutoSync({ wpId, projectId })',
    'async function syncToDisclosureNotes() {',
    '  const payload = buildL4SyncPayload({ variant: "listed", wpId, projectId })',
    '  await post(payload)',
    '}',
    'watch(rows, () => { scheduleAutoSync(syncToDisclosureNotes) })',
    '</script>',
  ].join('\n')

  it('替身：缺 useDisclosureAutoSync 必判红；正确形态放行', () => {
    const bad = GOOD_TAB.replace(/useDisclosureAutoSync/g, 'nothingHere')
    expect(checkAutoSyncWiring(bad).ok).toBe(false)
    expect(checkAutoSyncWiring(bad).detail).toContain('未调用 useDisclosureAutoSync')
    expect(checkAutoSyncWiring(GOOD_TAB).ok).toBe(true)
  })

  it('替身：同步函数体内未调 payload 构造器必判红（import 行不得冒充调用点）', () => {
    const bad = GOOD_TAB.replace(
      '  const payload = buildL4SyncPayload({ variant: "listed", wpId, projectId })',
      '  const payload = { note_section: "五、46" }',
    )
    // import 行仍含 buildL4SyncPayload —— 整份源码 toContain 会放行，落在函数体内才抓得住
    expect(bad.includes('buildL4SyncPayload')).toBe(true)
    expect(checkAutoSyncWiring(bad).ok).toBe(false)
    expect(checkAutoSyncWiring(bad).detail).toContain('体内未调用任何 payload 构造器')
  })

  it('替身：自调度形态必判红；watch 里调度放行', () => {
    const selfSchedule = GOOD_TAB.replace(
      '  await post(payload)',
      '  await post(payload)\n  scheduleAutoSync(syncToDisclosureNotes)',
    )
    expect(checkNoSelfSchedule(selfSchedule).ok).toBe(false)
    expect(checkNoSelfSchedule(selfSchedule).detail).toContain('自调度')
    expect(checkNoSelfSchedule(GOOD_TAB).ok).toBe(true)
  })

  it('替身：常量与模板不一致必判红（孤儿表 + 缺表两侧都抓）', () => {
    const tpl = [...L4_SOE_MAIN_TABLES]
    const bad = checkSubtableNames(['应付债券', '应付债券增减变动'], tpl)
    expect(bad.ok).toBe(false)
    expect(bad.orphans).toEqual(['应付债券增减变动'])
    expect(bad.missing).toEqual([L4_SOE_MAIN_TABLES[1]])
    const good = checkSubtableNames(tpl, tpl)
    expect(good.ok).toBe(true)
    expect(good.orphans).toEqual([])
    expect(good.missing).toEqual([])
  })

  it('替身：两个构造器都产出同一表键必判红；唯一写者且为期望者才放行', () => {
    const EXPECT = 'buildL2SyncPayload'
    const two = [
      { builder: 'buildK3SyncPayload', produces: ['应付利息', '应付股利'] },
      { builder: EXPECT, produces: ['应付利息'] },
    ]
    const r = checkSingleWriter(two, '应付利息', EXPECT)
    expect(r.ok).toBe(false)
    expect(r.owners.sort()).toEqual(['buildK3SyncPayload', EXPECT])

    const one = [
      { builder: 'buildK3SyncPayload', produces: ['应付股利'] },
      { builder: EXPECT, produces: ['应付利息'] },
    ]
    expect(checkSingleWriter(one, '应付利息', EXPECT).ok).toBe(true)
    expect(checkSingleWriter(one, '应付利息', EXPECT).owners).toEqual([EXPECT])

    // 🔴 关键对照：唯一写者但**是错的那一个**（当前现状）必须判红。
    //    朴素判据 owners.length === 1 会在这里假绿，这正是本判据升级的理由。
    const wrongSole = [{ builder: 'buildK3SyncPayload', produces: ['应付利息'] }]
    const w = checkSingleWriter(wrongSole, '应付利息', EXPECT)
    expect(w.owners).toEqual(['buildK3SyncPayload'])
    expect(w.ok, '唯一写者是 K3 时必须判红（收敛目标是唯一写者 == L2）').toBe(false)
    // 证明朴素判据确实会在此处放行（防下个会话把判据退回去）
    expect(wrongSole.filter((x) => x.produces.includes('应付利息')).length).toBe(1)

    // 零写者同样判红（避免「都不写」被当成通过）
    expect(checkSingleWriter(one, '不存在的表', EXPECT).ok).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 B —— 被测实现：现在应全红
// ═══════════════════════════════════════════════════════════════════════════

describe('[类 B] 判据① L2/L4 四个披露 Tab 必须有 useDisclosureAutoSync + payload 构造器调用', () => {
  it.each(ALL_TABS)('%s 已接自动同步且同步函数体内调 payload 构造器', (key) => {
    const r = checkAutoSyncWiring(tabSrc(key))
    expect(
      r.ok,
      `[类 B] ${TAB_FILES[key]} 未接同步链路：${r.detail || '(无细节)'}。` +
        `该 Tab 的披露数据只停在 checklist_responses，附注 ${
          key.startsWith('L4') ? '五、46 / 八、50' : '五、42 / 八、42'
        } 永远拿不到。${RED}`,
    ).toBe(true)
  })
})

describe('[类 B] 判据② 禁自调度（判据落在同步函数的函数体内）', () => {
  it.each(ALL_TABS)('%s 同步函数体内不得把自己传给 scheduleAutoSync', (key) => {
    const r = checkNoSelfSchedule(tabSrc(key))
    expect(
      r.ok,
      `[类 B] ${TAB_FILES[key]}: ${r.detail}。自调度会造成 800ms 周期重复 POST，` +
        `且能骗过平台覆盖率守卫（它只看有没有 scheduleAutoSync 调用）。${RED}`,
    ).toBe(true)
  })
})

describe('[类 B] 判据③ 宿主必须给 4 个披露 Tab 传 :html-data', () => {
  it.each(ALL_TABS)('%s 宿主已传 :html-data', (key) => {
    const attrs = tagAttrs(hostSrc(HOST_OF[key]), TAB_TAG[key])
    expect(attrs, `[类 A] 宿主未找到 <${TAB_TAG[key]}> 标签（守卫解析失效）`).not.toBe('')
    expect(
      /:html-data\s*=/.test(attrs),
      `[类 B] 宿主 ${HOST_FILES[HOST_OF[key]]} 漏传 :html-data 给 ${TAB_TAG[key]}。` +
        `Vue 对未声明/未传的 prop 静默失效（get_diagnostics 与 vitest 全绿），` +
        `Tab 内 props.htmlData 恒 undefined，四表取数与 tb_source_codes 全部读不到。${RED}`,
    ).toBe(true)
  })
})

describe('[类 B] 判据④ L4 录入必须落库（useChecklistPersistence 或 saveBatch）', () => {
  const L4_BOUND_FIELDS = [
    'row.noteContent',
    'row.isConsistent',
    'row.diffNote',
    'noteText',
    'conclusion',
  ] as const

  it.each(L4_TABS)('%s 出现 useChecklistPersistence 或 saveBatch', (key) => {
    const src = tabSrc(key)
    const hasPersistence = /\buseChecklistPersistence\s*\(/.test(src)
    const hasSaveBatch = /\bsaveBatch\s*\(/.test(src)
    expect(
      hasPersistence || hasSaveBatch,
      `[类 B] ${TAB_FILES[key]} 既无 useChecklistPersistence 也无 saveBatch。` +
        `实测 5 个 v-model 绑定字段全部只在内存，刷新即丢。${RED}`,
    ).toBe(true)
  })

  it.each(L4_TABS)('%s 5 个绑定字段都在持久化字段集内', (key) => {
    const src = tabSrc(key)
    // 反向自检：这 5 个字段确实被 v-model 绑定（扫描面非空）
    for (const f of L4_BOUND_FIELDS) {
      expect(
        src.includes(`v-model="${f}"`),
        `[类 A] ${key} 未找到 v-model="${f}"（守卫的字段清单已过期）`,
      ).toBe(true)
    }
    const persistBody =
      fnBody(src, 'persistAll') ||
      fnBody(src, 'saveAll') ||
      callArgs(src, 'useChecklistPersistence') ||
      ''
    const missing = L4_BOUND_FIELDS.filter((f) => {
      const leaf = f.replace(/^row\./, '')
      return !new RegExp(`\\b${esc(leaf)}\\b`).test(persistBody)
    })
    expect(
      missing,
      `[类 B] ${TAB_FILES[key]} 的持久化字段集缺少 ${missing.join(' / ')}。` +
        `未纳入持久化的绑定字段等于「界面有值、库里没有」。${RED}`,
    ).toEqual([])
  })
})

describe('[类 B] 判据⑤ L4 子表名常量必须与附注模板逐字一致（4 处偏差）', () => {
  it('L4_LISTED_SUBTABLE 与 五、46 五张表逐字一致（无孤儿、无缺表）', () => {
    const declared = Object.values(literalEntries(tsObjectLiteral(L4_MAP_SRC, 'L4_LISTED_SUBTABLE')))
    expect(declared.length, '[类 A] L4_LISTED_SUBTABLE 未解析出条目').toBeGreaterThan(0)
    const tpl = tplTableNames('listed', L4_SECTION.listed)
    const r = checkSubtableNames(declared, tpl)
    expect(
      r.ok,
      `[类 B] L4_LISTED_SUBTABLE 与模板 五、46 不一致。` +
        `孤儿表名（模板里不存在，推送即产生孤儿子表）: ${r.orphans.join(' / ') || '无'}；` +
        `未声明的模板表（附注永空）: ${r.missing.join(' / ') || '无'}。` +
        `已实证 4 处偏差：movement 少「的...（不包括...）」整段 / otherFinInstrument 缺「（3）」前缀 / ` +
        `overdue「已到期未偿付的应付债券」模板里压根不存在 / 缺「应付债券（续）」与` +
        `「期末发行在外的优先股、永续债等其他金融工具变动情况」两张。${RED}`,
    ).toBe(true)
  })

  it('L4_SOE_SUBTABLE 与 八、50 两张表逐字一致', () => {
    const declared = Object.values(literalEntries(tsObjectLiteral(L4_MAP_SRC, 'L4_SOE_SUBTABLE')))
    expect(declared.length, '[类 A] L4_SOE_SUBTABLE 未解析出条目').toBeGreaterThan(0)
    const r = checkSubtableNames(declared, tplTableNames('soe', L4_SECTION.soe))
    expect(
      r.ok,
      `[类 B] L4_SOE_SUBTABLE 与模板 八、50 不一致。孤儿: ${r.orphans.join(' / ') || '无'}；` +
        `缺表: ${r.missing.join(' / ') || '无'}。movement 与上市侧同错。${RED}`,
    ).toBe(true)
  })

  it('模板里不存在「已到期未偿付的应付债券」这张表（该常量必须删除或改名）', () => {
    const bad = '已到期未偿付的应付债券'
    for (const v of ['listed', 'soe'] as const) {
      const all = tplSections(v).flatMap((s) => (s.tables ?? []).map((t) => String(t.name ?? '')))
      expect(all.includes(bad), `[类 A] 模板 ${v} 竟然含 "${bad}"（实证前提已变）`).toBe(false)
    }
    expect(
      L4_MAP_SRC.includes(bad),
      `[类 B] l4NoteSectionMap.ts 仍声明 overdue: "${bad}"，而两份附注模板全库都没有这张表，` +
        `推送必产生孤儿子表。修正时须把旧表名登记进 _removed_table_keys 清理存量。${RED}`,
    ).toBe(false)
  })

  it('buildL4ListedColumns / buildL4SoeColumns 的键必须等于模板表名集合', () => {
    const listedKeys = Object.keys(literalEntries(tsObjectLiteral(L4_MAP_SRC, 'L4_LISTED_SUBTABLE')))
    expect(listedKeys.length, '[类 A] 解析失效').toBeGreaterThan(0)
    // 列构建器按语义键索引 subtable，故键集必须覆盖模板 5 张表
    const declared = Object.values(literalEntries(tsObjectLiteral(L4_MAP_SRC, 'L4_LISTED_SUBTABLE')))
    const tpl = tplTableNames('listed', L4_SECTION.listed)
    const covered = tpl.filter((t) => declared.includes(t))
    expect(
      covered.length,
      `[类 B] buildL4ListedColumns 只能覆盖模板 五、46 的 ${covered.length}/${tpl.length} 张表` +
        `（列定义按 L4_LISTED_SUBTABLE 的值索引）。未覆盖的表在附注侧无列元数据，` +
        `会被后端 _infer_groups_from_headers 凭空推断父表头。${RED}`,
    ).toBe(tpl.length)
  })
})

describe('[类 B] 判据⑥ L4_WITHIN1Y_NOTE_SECTION 缺 listed 键', () => {
  it('两版一年内到期落点都已声明（listed = 五、43 / soe = 八、46）', () => {
    const body = tsObjectLiteral(L4_MAP_SRC, 'L4_WITHIN1Y_NOTE_SECTION')
    const entries = literalEntries(body)
    expect(entries.soe, '[类 A] soe 键实证应为 八、46').toBe(L4_WITHIN1Y_SECTION.soe)
    expect(
      entries.listed,
      `[类 B] L4_WITHIN1Y_NOTE_SECTION 缺 listed 键（实测只有 soe 一个键）。` +
        `上市侧「一年内到期的应付债券」落点是 ${L4_WITHIN1Y_SECTION.listed}` +
        `（不是主章节 五、46），缺该键则上市第二个 payload 无处可发。${RED}`,
    ).toBe(L4_WITHIN1Y_SECTION.listed)
  })

  it('L4 一年内到期的两张表不在主章节，必须发第二个 payload', () => {
    const mainListed = tplTableNames('listed', L4_SECTION.listed)
    for (const t of L4_LISTED_WITHIN1Y_TABLES) {
      expect(mainListed, `[类 A] ${t} 竟在主章节 五、46 里（实证前提已变）`).not.toContain(t)
    }
    // buildL4SyncPayload 当前只发一个 note_section
    const body = fnBody(L4_MAP_SRC, 'buildL4SyncPayload')
    expect(body, '[类 A] buildL4SyncPayload 函数体未截出').not.toBe('')
    expect(
      /L4_WITHIN1Y_NOTE_SECTION/.test(body),
      `[类 B] buildL4SyncPayload 体内未引用 L4_WITHIN1Y_NOTE_SECTION，` +
        `即只发主章节一个 payload，一年内到期两张表（在 ${L4_WITHIN1Y_SECTION.listed} / ` +
        `${L4_WITHIN1Y_SECTION.soe}）永远推不出去。sync_from_workpaper 的定位键只含 ` +
        `(project_id, year, note_section)，一次只能写一节。${RED}`,
    ).toBe(true)
  })
})

describe('[类 B] 判据⑦ K3 写权冲突：「应付利息」子表键必须只有一个构造器产出', () => {
  it('buildK3SyncPayload 当前仍产出「应付利息」子表键（写权未撤）', () => {
    const body = fnBody(K3_MAP_SRC, 'buildK3SyncPayload')
    expect(body, '[类 A] buildK3SyncPayload 函数体未截出').not.toBe('')
    // 反向自检：该函数体确实在写 sub[T.interest]
    const writesInterest = /sub\[\s*T\.interest\s*\]\s*=/.test(body)
    expect(
      writesInterest,
      '[类 A] buildK3SyncPayload 体内未找到 sub[T.interest] 赋值（守卫判据已过期）',
    ).toBe(true)
    expect(
      writesInterest,
      `[类 B] buildK3SyncPayload 仍在产出「应付利息」子表（sub[T.interest]），` +
        `而源模板铁证该表由 L2-2 明细 SUMIF 驱动（附注披露（上市公司）信息!B8 = ` +
        `SUMIF('明细表L2-2'!A:A, ..., U:U)），K3 侧那份是手工重复录入。` +
        `裁决 = 收敛到 L2，K3 侧改只读 + 引导跳转。${RED}`,
    ).toBe(false)
  })

  it('buildK3SyncPayload 当前仍产出「逾期未付利息」子表键（写权未撤）', () => {
    const body = fnBody(K3_MAP_SRC, 'buildK3SyncPayload')
    const writesOverdue = /sub\[\s*T\.interestOverdue\s*\]\s*=/.test(body)
    expect(
      writesOverdue,
      '[类 A] buildK3SyncPayload 体内未找到 sub[T.interestOverdue] 赋值（判据过期）',
    ).toBe(true)
    expect(
      writesOverdue,
      `[类 B] buildK3SyncPayload 仍在产出「逾期未付利息」子表。该表两版不同名` +
        `（listed「重要的逾期未付利息」/ soe「重要的已逾期未支付的利息情况」），` +
        `收敛到 L2 后须同步撤 K3 写权。${RED}`,
    ).toBe(false)
  })

  it('buildL2SyncPayload 必须存在（L2 侧构造器尚未建立）', () => {
    const mapPath = resolve(WP_DIR, 'composables/l2NoteSectionMap.ts')
    expect(
      existsSync(mapPath),
      `[类 B] composables/l2NoteSectionMap.ts 不存在（l2AccountScope.ts 仅 1211 B，` +
        `无 payload 构造器）。收敛到 L2 需要 buildL2SyncPayload 产出「应付利息」+` +
        `「${L2_TABLES.listed[1]}」/「${L2_TABLES.soe[1]}」子表，并声明 _row_scope` +
        `（K3 章节是多 owner 共享表，不声明会整表覆盖 K3 其余 4~5 张表）。${RED}`,
    ).toBe(true)
  })

  it('「应付利息」子表键只有一个构造器产出', () => {
    const k3Body = fnBody(K3_MAP_SRC, 'buildK3SyncPayload')
    const writers: Array<{ builder: string; produces: string[] }> = []
    if (/sub\[\s*T\.interest\s*\]\s*=/.test(k3Body)) {
      writers.push({ builder: 'buildK3SyncPayload', produces: ['应付利息'] })
    }
    const l2Path = resolve(WP_DIR, 'composables/l2NoteSectionMap.ts')
    if (existsSync(l2Path)) {
      const l2Src = stripComments(readFileSync(l2Path, 'utf-8').replace(/\r\n/g, '\n'))
      const l2Body = fnBody(l2Src, 'buildL2SyncPayload')
      if (l2Body.includes('应付利息')) {
        writers.push({ builder: 'buildL2SyncPayload', produces: ['应付利息'] })
      }
    }
    const r = checkSingleWriter(writers, '应付利息', 'buildL2SyncPayload')
    expect(
      r.ok,
      `[类 B] 「应付利息」子表的产出者 = [${r.owners.join(', ') || '无'}]，` +
        `期望恰好 1 个且必须是 buildL2SyncPayload。` +
        `当前形态 = K3 仍持有写权 + L2 构造器不存在。` +
        `注意判据不能只写 owners.length === 1 —— 那样「唯一写者是 K3」会假绿，` +
        `而这正是收敛前的现状。${RED}`,
    ).toBe(true)
  })
})

// 判据⑧ 拆两半：
//   「不得用 el-input-number / :formatter」与「非金额列不得套 WpAmountInput」
//   实测当前**已经成立**（L4 两个 Tab 的 el-input-number 与 WpAmountInput 计数均为 0）
//   ⇒ 属类 A 防回退，放进类 B 会以「误绿」形态出现（看着像判据失效，实为分类错误）。
//   只有「金额列必须用 WpAmountInput」这条现在是真红（Wave 7 重建录入区块时补）。
describe('[类 A] 判据⑧-防回退 L4 不得使用 el-input-number / :formatter', () => {
  it.each(L4_TABS)('%s 不得使用 el-input-number 或 :formatter', (key) => {
    const src = tabSrc(key)
    const numbers = (src.match(/<el-input-number(?=[\s/>])/g) ?? []).length
    const formatters = (src.match(/:formatter\s*=/g) ?? []).length
    expect(
      numbers + formatters,
      `[类 B] ${TAB_FILES[key]} 出现 el-input-number x${numbers} / :formatter x${formatters}。` +
        `EP 2.13.6 的 el-input-number 无 formatter prop，千分符从未生效（平台已双证）。${RED}`,
    ).toBe(0)
  })

  it.each(L4_TABS)('%s 反向边界：非金额列不得套用 WpAmountInput', (key) => {
    const src = tabSrc(key)
    // 附注模板 五、46 / 八、50 里的非金额列（逐字取模板 label）
    const NON_AMOUNT_LABELS = [
      '票面利率',
      '债券期限',
      '是否违约',
      '发行日期',
      '票面利率（股息率）',
      '期限',
      '转股/赎回条件',
      '期初',
      '本期增加',
      '本期减少',
      '期末',
    ]
    // 反向自检：这些 label 确实是模板里的非金额列
    const listedCols = tplTables('listed', L4_SECTION.listed).flatMap((t) =>
      (t.columns ?? []).map((c) => String(c.label ?? '')),
    )
    const found = NON_AMOUNT_LABELS.filter((l) => listedCols.includes(l))
    expect(
      found.length,
      '[类 A] 非金额列 label 清单与模板不符（守卫清单已过期）',
    ).toBeGreaterThan(5)

    const offenders: string[] = []
    for (const label of NON_AMOUNT_LABELS) {
      // 在含该 label 的 el-table-column 块内查 WpAmountInput
      const re = new RegExp(`label="${esc(label)}"`, 'g')
      let m: RegExpExecArray | null
      while ((m = re.exec(src)) !== null) {
        const colStart = src.lastIndexOf('<el-table-column', m.index)
        if (colStart < 0) continue
        const colEnd = src.indexOf('</el-table-column>', m.index)
        const block = src.slice(colStart, colEnd < 0 ? src.length : colEnd)
        if (/<WpAmountInput(?=[\s/>])/.test(block)) offenders.push(label)
      }
    }
    expect(
      offenders,
      `[类 A] ${TAB_FILES[key]} 把非金额列 ${offenders.join(' / ')} 套上了 WpAmountInput。` +
        `票面利率 / 债券期限 / 是否违约 / 数量 一律禁用金额控件（平台铁律）。` +
        `本条当前恒真（该 Tab 尚无 WpAmountInput），Wave 7 建录入区块后才真正承重，属防回退。`,
    ).toEqual([])
  })
})

describe('[类 B] 判据⑧b L4 金额列必须用 WpAmountInput', () => {
  it.each(L4_TABS)('%s 金额录入列必须用 WpAmountInput', (key) => {
    const src = tabSrc(key)
    // 反向自检：确实存在录入控件（扫描面非空），否则本判据空转
    const inputCount = (src.match(/<el-input(?=[\s/>])/g) ?? []).length
    expect(
      inputCount,
      `[类 A] ${key} 未找到任何 <el-input>（实证应有 4 个，守卫扫描面已失效）`,
    ).toBeGreaterThan(0)
    expect(
      /<WpAmountInput(?=[\s/>])/.test(src),
      `[类 B] ${TAB_FILES[key]} 未使用 WpAmountInput。当前 ${inputCount} 个 el-input 中，` +
        `Wave 5 重建后属于金额列的（面值 / 发行金额 / 期初余额 / 本期发行 / 按面值计提利息 / ` +
        `溢折价摊销 / 本期偿还 / 期末余额）必须换成 WpAmountInput 才有千分符。${RED}`,
    ).toBe(true)
  })
})

/**
 * 🔴 判据⑨与上方类 A 那条是**同一事实的正反两面**：
 *    类 A =「现在必须还登记着」（防有人误删登记绕过检查）；
 *    类 B =「Wave 5~7 接线后必须已移出」（待办提醒，现在应当是红的）。
 *
 * 既然是同一事实，两条就必须判**同一个语义量** —— 都判「覆盖率守卫的登记表里
 * 还有没有这四个文件名」。原先不是这样：类 B 判的是**注释措辞**，
 * 而且两条都对含注释原文做 `includes`。三个后果 2026-08-15 全部实测到 ——
 *
 * ① 判据锚定长注释片段（如 `'🔴 L4 应付债券（2）**需结构对齐重建**（暂留缺口）'`），
 *    对方**改一个字**就静默失效：本次把 L4 的理由从「（暂留缺口）」改写为
 *    「：源模板 §五、46/§八、50 是…」，该 marker 立刻不命中 ⇒ 这条**假绿**了，
 *    而 L4 的缺口一条没少（`SYNC_PATH_GAP` 里仍是两条）。
 *
 * ② `COVERAGE_RAW.includes` 吃注释 ⇒「四条目已移出」这条**永远不可能转绿**：
 *    拆表时保留的墓碑注释块含四条目的原始快照，Wave 5~7 真接完线、真把条目
 *    从登记表删干净，`includes` 依旧命中注释里的快照。一条**结构上无法达成**的
 *    待办断言，比没有这条更糟 —— 它会让收口的人反复怀疑自己没改对。
 *
 * ③ 失败消息里写死「把 MISSING_SYNC_PATH.length 硬断言由 6 下调到 2」，
 *    该常量与该数字都已不存在，照着做只会更困惑。
 */
describe('[类 B] 判据⑨ 覆盖率守卫须不再把 L2/L4 登记为「无同步链路」', () => {
  /**
   * 🔴 与类 A 那条共用同一语义量：覆盖率守卫**活跃数组**里仍登记的 L2/L4 条目。
   *    走 `declaredNoSyncInCoverage`（只截活跃声明体）而非全文件扫描 —— 否则墓碑注释块
   *    的历史快照会让本判据**永远无法转绿**（Wave 5~7 真接完线也报红），见该函数注释。
   */
  const declaredInCoverage = (): string[] => declaredNoSyncInCoverage()

  it.each([...L2L4_TAB_FILES])('%s 已从覆盖率守卫的登记表移出', (name) => {
    expect(
      declaredInCoverage().includes(name),
      `[类 B] disclosureAutoSyncCoverage.spec.ts 仍把 ${name} 登记为「无同步链路」。` +
        `Wave 5~7 接线后必须从 PERMANENT_EXEMPT / SYNC_PATH_GAP 中移出，` +
        `并同步删掉对应的豁免/缺口理由注释与天花板余量。${RED}`,
    ).toBe(false)
  })

  it('四条目全部移出（收口判据：本 describe 与类 A 的防回退条应一并删除）', () => {
    const still = declaredInCoverage()
    expect(
      still,
      `[类 B] 覆盖率守卫仍登记 ${still.join(' / ')}。这四个 Tab 接线后必须移出。\n` +
        `🔴 全部移出时**类 A 的「仍把 L2/L4 四条目登记为无同步链路」会同时打红** —— ` +
        `那是正确的红：防回退锚点在事实变化后本就该退休。届时两处一并删除，` +
        `不要靠改数字或加豁免让它闭嘴。${RED}`,
    ).toEqual([])
  })
})
