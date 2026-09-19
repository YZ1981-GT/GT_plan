/**
 * `x3KeyProbe` —— 16 张 X-3 调整分录汇总表的**键提取判据 + 持久化机制探针**
 *
 * spec: `x3-adjustment-entry-import-export` / 任务 1.9（Wave 0，硬前置 → 任务 2.1 / 4.1）
 * 消费方: `components/workpaper/composables/__tests__/adjustmentIeContract.spec.ts`
 *          （helper 与消费方同任务交付；本文件若无消费方即 additive 死代码）
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 为什么要有本文件
 * ─────────────────────────────────────────────────────────────────────────────
 * 既有契约清单 `backend/data/adjustment_ie_contract.json` 里 16 张 X-3 有 11 条把
 * **复核键**（`openReviewDialog(sectionId)` 的第一参）当成了数据键。成因是原提取器
 * 只认两种形态（引号字面量 / `ITEM_PREFIX` 同文件拼接），而这 11 张的真数据键是
 * **模板字面量逐字段族**（形态 ③）；文件里唯一可见的 X-3 引号字面量恰好是复核键
 * ⇒ 被当成数据键收录（design 缺陷 B / §C6）。
 *
 * 四种形态（design §C6，R7.4）：
 *
 *   ① 引号字面量            `const ITEM_ID_ENTRIES = 'L2-L2-3-entries'`
 *   ② `ITEM_PREFIX` 同文件拼接  `` `${ITEM_PREFIX}-entries` ``
 *   ③ 模板字面量逐字段族      `` `M4-3-entry-${n}-desc` `` / 双前缀 `` `L6-L6-3-entry-${n}-type` ``
 *   ④ 跨文件运行期拼装        tab 只有 `formData.setField('3','entries', entries.value)`；
 *                            `ITEM_PREFIX='N5-'` 在**另一个文件** `useN5FormData.ts`，
 *                            键由 `ITEM_PREFIX + sheet + '-' + field` 在运行期三段拼出
 *
 * 形态 ④ 是**单文件纯文本 grep 永远抓不到**的那一类：`'N5-3-entries'` 字面量在 tab 里
 * 确实存在，但它属 `useAdjustmentCentralSync` 的**中央同步键**、与真数据键**同名纯属
 * 巧合**（design E12 → E17）。⇒ 形态 ④ 必须走三步链，且必须配反向自检（改 `ITEM_PREFIX`
 * 或改 `setField` 实参 ⇒ 该 sheet 判「键不可确证」），否则会因那个巧合同名字面量而蒙对。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 与后端守卫的分工（design §GS9 的完整判据 = 两侧之和）
 * ─────────────────────────────────────────────────────────────────────────────
 * `backend/tests/test_x3_key_ledger.py`（任务 1.1 已交付）的 GS9 后端侧判
 *   `storage_field == {formdata_setfield: 'conclusion', adjustment_savebatch: 'remark'}[mechanism]`，
 * 其 `mechanism` **取清单登记值** ⇒ 只能抓「清单内机制与列自相矛盾」这一类；
 * 「**机制本身是否与前端源码一致**」后端读不到 `.vue`，只能由本文件的前端探针承担。
 * 两侧合起来才是 design §GS9 的完整判据：
 *
 *   后端：清单.mechanism ──推导──> 应有列  ==  清单.storage_field   （清单内自洽）
 *   前端：前端源码 ──实测──> mechanism ──推导──> 应有列  ==  清单.storage_field
 *
 * 缺前端侧 ⇒ 一份「内部自洽但与前端不符」的清单可以让后端全绿（E14 那类「守卫把错值
 * 锁成基线」的形态）；缺后端侧 ⇒ 后端 `X3_SHEET_SPECS` 的装载值无人校验。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 判据形态：结构/行为，不是「源码含某字符串」
 * ─────────────────────────────────────────────────────────────────────────────
 * - 写入列**不写常量**：由「机制实现源码」实测得出 —— 机制 ① 读 `use{X}FormData.setField`
 *   函数体里 `saveField(itemId, { … })` 的对象字面量键；机制 ② 读写入调用点
 *   （`saveBatch` / `debouncedSave` / `saveField` / `emit('save', …)`）的载荷键。
 *   ⇒ E14 的修法是「机制推导」，不是把常量从 `'remark'` 换成 `'conclusion'`。
 * - 取函数体/调用实参一律**括号配对**，且**先跳参数列表**（返回类型注解里的 `{` 会骗到
 *   「第一个 `{`」）；不用固定字符窗口。
 * - 扫描前 `stripComments()`，且注释剥离本身有反向自检（消费方 spec 内）。
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// ═══════════════════════════════════════════════════════════════════════════
// 作业面与路径
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 本 spec 的 16 张 X-3 作业面（requirements.md §Introduction 的逐条列举）。
 *
 * 说明：清单侧的机器可读真源（`adjustment_ie_contract.json.sheets`）要到任务 2.1
 * 才落值，Wave 0 阶段前端探针只能自带作业面常量；消费方 spec 另有一条断言把它与
 * 清单/后端作业面交叉核对，防两处分叉。
 */
export const X3_TARGET_CYCLES = [
  'L2',
  'L6',
  'M1',
  'M2',
  'M3',
  'M4',
  'M5',
  'M6',
  'M7',
  'M8',
  'M9',
  'M10',
  'N1',
  'N2',
  'N3',
  'N5',
] as const

export type X3Cycle = (typeof X3_TARGET_CYCLES)[number]

/** X-3 的 sheet 序号（`{cycle}-3`）。不散落字面量，仅此一处定义。 */
export const X3_SHEET_NO = '3'

export const X3_TARGET_SHEETS: string[] = X3_TARGET_CYCLES.map((c) => `${c}-${X3_SHEET_NO}`)

const HERE = path.dirname(fileURLToPath(import.meta.url))

export function findRepoRoot(start: string = HERE): string {
  let dir = start
  for (let i = 0; i < 14; i++) {
    if (fs.existsSync(path.join(dir, 'backend', 'data', 'adjustment_ie_contract.json'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未找到仓库根（backend/data/adjustment_ie_contract.json）')
}

export const REPO_ROOT = findRepoRoot()

/** 前端 workpaper 根；本文件全部相对路径以它为基准。 */
export const WP_ROOT = path.join(
  REPO_ROOT,
  'audit-platform',
  'frontend',
  'src',
  'components',
  'workpaper',
)

export const CONTRACT_REL = 'backend/data/adjustment_ie_contract.json'

// ═══════════════════════════════════════════════════════════════════════════
// SourceBundle —— 可注入的源码读取面（反向自检靠它做「变体输入」）
// ═══════════════════════════════════════════════════════════════════════════

export interface SourceBundle {
  /** 读相对 `WP_ROOT` 的文件；不存在返回 null。 */
  read(rel: string): string | null
  exists(rel: string): boolean
  /** 本次探测实际读到的文件（供消费方做「扫描面非空」反空转断言）。 */
  touched(): string[]
}

/**
 * 建源码读取面。`overrides` 的键是相对 `WP_ROOT` 的路径：
 * - 值为字符串 ⇒ 用该内容替换磁盘内容（反向自检 (c)/(d) 的变体输入）
 * - 值为 `null` ⇒ 视为该文件不存在（反向自检：断链）
 */
export function createSourceBundle(
  overrides: Record<string, string | null> = {},
  root: string = WP_ROOT,
): SourceBundle {
  const seen = new Set<string>()
  const norm = (rel: string) => rel.replace(/\\/g, '/')
  return {
    read(rel: string) {
      const key = norm(rel)
      seen.add(key)
      if (key in overrides) return overrides[key]
      const abs = path.join(root, key)
      if (!fs.existsSync(abs)) return null
      return fs.readFileSync(abs, 'utf8')
    },
    exists(rel: string) {
      const key = norm(rel)
      if (key in overrides) return overrides[key] !== null
      return fs.existsSync(path.join(root, key))
    },
    touched() {
      return [...seen].sort()
    },
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 词法工具（注释剥离 / 括号配对 / 对象字面量拆解）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 剥注释：`//` 行注释、`/* *\/` 块注释、`.vue` 模板的 `<!-- -->`。
 *
 * 走字符状态机，字符串/模板字面量内的 `//` 与 `/*` 不剥；模板字面量里的 `${…}`
 * 递归回代码态（`` `${a /* c *\/ + b}` `` 这种也能剥对）。剥掉的字符用空格替换
 * 以**保持偏移量**（后续任何按位置回看的判据都不会串行）。
 */
export function stripComments(src: string): string {
  const out: string[] = []
  let i = 0
  const n = src.length
  // 状态栈：'code' | 'sq' | 'dq' | 'tpl'
  const stack: string[] = ['code']
  const top = () => stack[stack.length - 1]
  const keep = (ch: string) => out.push(ch)
  const blank = (ch: string) => out.push(ch === '\n' ? '\n' : ' ')

  while (i < n) {
    const ch = src[i]
    const st = top()
    if (st === 'code') {
      if (ch === '/' && src[i + 1] === '/') {
        while (i < n && src[i] !== '\n') blank(src[i++])
        continue
      }
      if (ch === '/' && src[i + 1] === '*') {
        blank(src[i++])
        blank(src[i++])
        while (i < n && !(src[i] === '*' && src[i + 1] === '/')) blank(src[i++])
        if (i < n) {
          blank(src[i++])
          blank(src[i++])
        }
        continue
      }
      if (src.startsWith('<!--', i)) {
        while (i < n && !src.startsWith('-->', i)) blank(src[i++])
        for (let k = 0; k < 3 && i < n; k++) blank(src[i++])
        continue
      }
      if (ch === "'") {
        stack.push('sq')
        keep(ch)
        i++
        continue
      }
      if (ch === '"') {
        stack.push('dq')
        keep(ch)
        i++
        continue
      }
      if (ch === '`') {
        stack.push('tpl')
        keep(ch)
        i++
        continue
      }
      if (ch === '}' && stack.length > 1) {
        // `${…}` 内的代码态由 'tpl' 压入的 'code' 承担，遇 '}' 弹回模板态
        stack.pop()
        keep(ch)
        i++
        continue
      }
      keep(ch)
      i++
      continue
    }
    if (st === 'sq' || st === 'dq') {
      if (ch === '\\') {
        keep(ch)
        i++
        if (i < n) {
          keep(src[i])
          i++
        }
        continue
      }
      if ((st === 'sq' && ch === "'") || (st === 'dq' && ch === '"')) {
        stack.pop()
        keep(ch)
        i++
        continue
      }
      keep(ch)
      i++
      continue
    }
    // tpl
    if (ch === '\\') {
      keep(ch)
      i++
      if (i < n) {
        keep(src[i])
        i++
      }
      continue
    }
    if (ch === '`') {
      stack.pop()
      keep(ch)
      i++
      continue
    }
    if (ch === '$' && src[i + 1] === '{') {
      keep(ch)
      i++
      keep(src[i])
      i++
      stack.push('code')
      continue
    }
    keep(ch)
    i++
  }
  return out.join('')
}

const OPEN: Record<string, string> = { '(': ')', '[': ']', '{': '}' }
const CLOSE = new Set([')', ']', '}'])

/**
 * 从 `src[from]`（必须是 `(` / `[` / `{`）开始做括号配对，返回闭合符的下标。
 * 字符串/模板字面量内的括号不计数。找不到返回 -1。
 */
export function matchBracket(src: string, from: number): number {
  const openCh = src[from]
  if (!OPEN[openCh]) return -1
  let depth = 0
  let i = from
  const n = src.length
  let quote: string | null = null
  const tplStack: number[] = []
  while (i < n) {
    const ch = src[i]
    if (quote) {
      if (ch === '\\') {
        i += 2
        continue
      }
      if (ch === quote) {
        if (quote === '`') tplStack.pop()
        quote = null
      }
      i++
      continue
    }
    if (ch === "'" || ch === '"') {
      quote = ch
      i++
      continue
    }
    if (ch === '`') {
      quote = '`'
      tplStack.push(depth)
      i++
      continue
    }
    if (OPEN[ch]) {
      depth++
      i++
      continue
    }
    if (CLOSE.has(ch)) {
      depth--
      if (depth === 0) return i
      i++
      continue
    }
    i++
  }
  return -1
}

/** 按顶层逗号切分（括号与引号内的逗号不算）。 */
export function splitTopLevel(inner: string): string[] {
  const parts: string[] = []
  let depth = 0
  let quote: string | null = null
  let buf = ''
  for (let i = 0; i < inner.length; i++) {
    const ch = inner[i]
    if (quote) {
      buf += ch
      if (ch === '\\') {
        if (i + 1 < inner.length) buf += inner[++i]
        continue
      }
      if (ch === quote) quote = null
      continue
    }
    if (ch === "'" || ch === '"' || ch === '`') {
      quote = ch
      buf += ch
      continue
    }
    if (OPEN[ch]) {
      depth++
      buf += ch
      continue
    }
    if (CLOSE.has(ch)) {
      depth--
      buf += ch
      continue
    }
    if (ch === ',' && depth === 0) {
      parts.push(buf.trim())
      buf = ''
      continue
    }
    buf += ch
  }
  if (buf.trim()) parts.push(buf.trim())
  return parts
}

export interface ObjectEntry {
  key: string
  /** 值表达式原文；shorthand（`{ remark }`）时等于键名 */
  value: string
  shorthand: boolean
}

/** 拆对象字面量顶层键值对；`raw` 须以 `{` 开头。 */
export function parseObjectLiteral(raw: string): ObjectEntry[] {
  const s = raw.trim()
  if (!s.startsWith('{')) return []
  const end = matchBracket(s, 0)
  if (end < 0) return []
  const out: ObjectEntry[] = []
  for (const part of splitTopLevel(s.slice(1, end))) {
    if (!part) continue
    if (part.startsWith('...')) continue
    const m = part.match(/^(?:\[([^\]]*)\]|(['"`])([^'"`]*)\2|([A-Za-z_$][\w$]*))\s*:\s*([\s\S]*)$/)
    if (m) {
      out.push({ key: m[3] ?? m[4] ?? m[1] ?? '', value: (m[5] ?? '').trim(), shorthand: false })
      continue
    }
    const sh = part.match(/^([A-Za-z_$][\w$]*)$/)
    if (sh) out.push({ key: sh[1], value: sh[1], shorthand: true })
  }
  return out
}

export interface CallSite {
  /** 被匹配到的调用文本（含被调用者名） */
  callee: string
  args: string[]
  /** 调用起点下标（供定位/去重） */
  index: number
}

/**
 * 找调用点并按顶层逗号拆实参。`calleeRe` 需含一个捕获组以命中被调用者名，
 * 且**必须**以 `\s*\(` 结尾之前的部分为准（本函数自己找 `(`）。
 *
 * **可选调用 `callee?.(…)` 必须一并识别**：M 族 11 张的复核入口实测写法是
 * `openReviewDialog?.('M1-3-adjustment', '调整分录')`（L2 是 `openReviewDialog(…)` 无 `?.`）。
 * 只认 `callee(` 会让 R2.4「排除复核键」对这 11 张**整条空转** —— 排除集恒空、
 * 判据看不出被排除了什么，而这 11 条恰是缺陷 B 的成因。
 */
export function findCalls(src: string, calleeRe: RegExp): CallSite[] {
  const re = new RegExp(calleeRe.source, calleeRe.flags.includes('g') ? calleeRe.flags : calleeRe.flags + 'g')
  const out: CallSite[] = []
  let m: RegExpExecArray | null
  while ((m = re.exec(src))) {
    let j = m.index + m[0].length
    while (j < src.length && /\s/.test(src[j])) j++
    if (src[j] === '?' && src[j + 1] === '.') {
      j += 2
      while (j < src.length && /\s/.test(src[j])) j++
    }
    if (src[j] !== '(') continue
    const end = matchBracket(src, j)
    if (end < 0) continue
    out.push({ callee: m[0], args: splitTopLevel(src.slice(j + 1, end)), index: m.index })
    re.lastIndex = end
  }
  return out
}

/**
 * 跳过一段尖括号泛型实参（`<…>`），返回闭合 `>` 之后的下标；配不上返回 -1。
 *
 * `matchBracket` 只认 `(`/`[`/`{` 三种括号，泛型必须单独处理。两处坑：
 *   · 泛型里可能嵌函数类型 `Promise<() => void>` ⇒ `=>` 的 `>` 不算闭合
 *   · 泛型里可能嵌对象类型 `Promise<{ ok: boolean }>` ⇒ 花括号整段跳过
 */
function skipAngles(src: string, from: number): number {
  let depth = 0
  let i = from
  while (i < src.length) {
    const ch = src[i]
    if (ch === '=' && src[i + 1] === '>') {
      i += 2
      continue
    }
    if (ch === '<') {
      depth++
      i++
      continue
    }
    if (ch === '>') {
      depth--
      i++
      if (depth === 0) return i
      continue
    }
    if (ch === '(' || ch === '[' || ch === '{') {
      const close = matchBracket(src, i)
      if (close < 0) return -1
      i = close + 1
      continue
    }
    if (ch === "'" || ch === '"' || ch === '`') {
      const q = ch
      i++
      while (i < src.length && src[i] !== q) i += src[i] === '\\' ? 2 : 1
      i++
      continue
    }
    i++
  }
  return -1
}

/**
 * 从参数列表闭合括号（`pEnd`）之后定位**函数体**的 `{`。找不到块体返回 -1。
 *
 * 只写 `indexOf('{', pEnd)` 会被 TS **返回类型注解**骗到 —— 注解里的 `{` 出现在 `)`
 * **之后**（`): Promise<{ ok: boolean }> {` / `): { ok: boolean } {`），于是把那段类型
 * 当成函数体。该形态平台**当前零实例**（105 个 `use*FormData.ts` 实测无一处命中），
 * 后果也是 fail-loud（形态④步③报「体内无键拼装模板」而非产出错键），但它会让判据对
 * 合法写法产生**假红** ⇒ 本轮（任务 3）修掉，P8-H 随之走「拼对」分支且仍绿。
 *
 * 判据：`)` 之后只可能是 `{`（函数体）/ `:`（返回类型注解）/ `=>`（箭头函数体）。
 * 注解区内用「此刻是否期待一个类型」区分 `{`：期待类型时的 `{` 是**对象类型**（整段跳过），
 * 读完一个完整类型之后的 `{` 才是函数体。
 */
function findFunctionBodyBrace(src: string, pEnd: number): number {
  let i = pEnd + 1
  let inAnnotation = false
  let expectType = false
  while (i < src.length) {
    const ch = src[i]
    if (/\s/.test(ch)) {
      i++
      continue
    }
    if (ch === '{') {
      if (!expectType) return i
      const close = matchBracket(src, i)
      if (close < 0) return -1
      i = close + 1
      expectType = false
      continue
    }
    if (ch === '=' && src[i + 1] === '>') {
      // 箭头函数的箭头（或注解里函数类型的箭头）：其后紧跟的 `{` 就是块体
      i += 2
      expectType = false
      continue
    }
    if (ch === ':' && !inAnnotation) {
      inAnnotation = true
      expectType = true
      i++
      continue
    }
    if (!inAnnotation) return -1 // `)` 后既非 `{` 也非 `:` / `=>` ⇒ 无块体（如箭头表达式体）
    if (ch === '<') {
      const after = skipAngles(src, i)
      if (after < 0) return -1
      i = after
      expectType = false
      continue
    }
    if (ch === '(' || ch === '[') {
      const close = matchBracket(src, i)
      if (close < 0) return -1
      i = close + 1
      expectType = false
      continue
    }
    if (ch === '|' || ch === '&' || ch === ',') {
      expectType = true
      i++
      continue
    }
    if (ch === "'" || ch === '"' || ch === '`') {
      const q = ch
      i++
      while (i < src.length && src[i] !== q) i += src[i] === '\\' ? 2 : 1
      i++
      expectType = false
      continue
    }
    if (/[A-Za-z0-9_$.]/.test(ch)) {
      while (i < src.length && /[A-Za-z0-9_$.]/.test(src[i])) i++
      expectType = false
      continue
    }
    i++ // `?` / `!` / 其它注解噪声：不改变「是否期待类型」
  }
  return -1
}

/**
 * 取具名函数体（`function name(...)` / `const name = (...) =>` / 方法 `name(...) {`）。
 *
 * 先按**圆括号配对**跳过参数列表（避免被参数里的内联类型字面量骗到），再用
 * `findFunctionBodyBrace` 跳过 TS **返回类型注解**定位真正的函数体 `{`。
 */
export function extractFunctionBody(src: string, name: string): string | null {
  const patterns = [
    new RegExp(`function\\s+${name}\\s*(?=\\()`),
    new RegExp(`(?:const|let|var)\\s+${name}\\s*=\\s*(?:async\\s*)?(?=\\()`),
    new RegExp(`(?:^|[\\n;{,])\\s*(?:async\\s+)?${name}\\s*(?=\\()`),
  ]
  for (const pat of patterns) {
    const m = src.match(pat)
    if (!m || m.index === undefined) continue
    let j = src.indexOf('(', m.index)
    if (j < 0) continue
    const pEnd = matchBracket(src, j)
    if (pEnd < 0) continue
    const bodyStart = findFunctionBodyBrace(src, pEnd)
    if (bodyStart < 0) continue
    const bodyEnd = matchBracket(src, bodyStart)
    if (bodyEnd < 0) continue
    return src.slice(bodyStart, bodyEnd + 1)
  }
  return null
}

/** 取模块级 `const NAME = '字面量'`（同时兼容 `export const`）。 */
export function resolveConstLiteral(src: string, name: string): string | null {
  const m = src.match(new RegExp(`(?:export\\s+)?(?:const|let|var)\\s+${name}\\s*=\\s*['"\`]([^'"\`]*)['"\`]`))
  return m ? m[1] : null
}

// ═══════════════════════════════════════════════════════════════════════════
// 四形态提取器
// ═══════════════════════════════════════════════════════════════════════════

/** `checklist_responses` 的两个存储列；写入列只可能是其中之一。 */
export const STORAGE_COLUMNS = ['remark', 'conclusion'] as const
export type StorageColumn = (typeof STORAGE_COLUMNS)[number]

export type ExtractionForm =
  | 'quoted_literal'
  | 'item_prefix_concat'
  | 'template_per_field'
  | 'cross_file_runtime'

/** 形态 ① 引号字面量：`'L2-L2-3-entries'` / `"M8-3-adjustmentNote"`。 */
const QUOTED_KEY_RE = /['"]((?:[A-Z]{1,2}\d{0,2}-)+[A-Za-z0-9\u4e00-\u9fa5_-]+)['"]/g

export function extractQuotedKeys(src: string): string[] {
  const out = new Set<string>()
  QUOTED_KEY_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = QUOTED_KEY_RE.exec(src))) out.add(m[1])
  return [...out]
}

/** 形态 ② `ITEM_PREFIX` 同文件拼接：`ITEM_PREFIX='K3-3-adj'` + `` `${ITEM_PREFIX}-entries` ``。 */
export function extractItemPrefixKeys(src: string): string[] {
  const prefix = resolveConstLiteral(src, 'ITEM_PREFIX')
  if (!prefix) return []
  const out = new Set<string>()
  for (const m of src.matchAll(/\$\{ITEM_PREFIX\}([A-Za-z0-9_-]+)/g)) out.add(`${prefix}${m[1]}`)
  return [...out]
}

/**
 * 形态 ③ 的**任务原文骨架**（tasks.md 任务 1.9 / design §C6）。
 *
 * 仅作留痕与实证对照：它的第一个字符类是 `\$`（要求键前缀本身来自插值，形如
 * `` `${M4}-3-entry-${n}-desc` ``），而 16 张 X-3 的真实写法里键前缀是**字面量**
 * （`` `M4-3-entry-${n}-desc` ``）⇒ 该骨架对全部前端源码**零命中**（消费方 spec 有
 * 一条断言实测这一点）。故实现用下面 `FORM3_RE`，形态语义不变。
 */
export const FORM3_SKELETON_FROM_TASK =
  /`\$\{?([A-Z]\d{0,2})\}?-(\d{1,2})-entry-\$\{[^}]+\}-(\$\{[^}]+\}|[a-z]+)`/g

/**
 * 形态 ③ 模板字面量逐字段（含双前缀变体）：
 *   `` `M4-3-entry-${n}-desc` ``      → prefix `M4-3`
 *   `` `L6-L6-3-entry-${n}-type` ``   → prefix `L6-L6-3`
 * 后缀允许 camelCase（实测 `M9-3` 多一个 `ociBlock`）。
 */
export const FORM3_RE =
  /`((?:[A-Z]{1,2}\d{0,2}-)+\d{1,2})-entry-\$\{[^}]+\}-(\$\{[^}]+\}|[A-Za-z][A-Za-z0-9]*)`/g

export interface TemplateFamilyHit {
  /** 键前缀原文，如 `M4-3` / `L6-L6-3` */
  keyPrefix: string
  /** 归约后的族键，如 `M4-3-entry-*` / `L6-L6-3-entry-*` */
  familyKey: string
  /** 后缀；`${…}` 形态（后缀本身是变量）记为 `*` */
  suffix: string
}

/** 形态 ③ 提取 + 族键归约。 */
export function extractTemplateFamilyKeys(src: string): TemplateFamilyHit[] {
  const out = new Map<string, TemplateFamilyHit>()
  FORM3_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = FORM3_RE.exec(src))) {
    const keyPrefix = m[1]
    const suffix = m[2].startsWith('${') ? '*' : m[2]
    out.set(`${keyPrefix}|${suffix}`, {
      keyPrefix,
      familyKey: `${keyPrefix}-entry-*`,
      suffix,
    })
  }
  return [...out.values()]
}

// ── 两类非数据键（R2.4 显式排除） ───────────────────────────────────────────

/**
 * 复核键：`openReviewDialog(sectionId)` 的第一参 + `<GtReviewTrigger section-id="…">`。
 * 实测两种形态：`{X}-3-adjustment` 与 `{X}-3-调整分录`。
 */
export function extractReviewKeys(src: string): string[] {
  const out = new Set<string>()
  for (const c of findCalls(src, /openReviewDialog/)) {
    const a = c.args[0]
    if (!a) continue
    const lit = a.match(/^['"`]([^'"`]+)['"`]$/)
    if (lit) out.add(lit[1])
  }
  for (const m of src.matchAll(/section-id\s*=\s*"([^"]+)"/g)) out.add(m[1])
  for (const m of src.matchAll(/section-id\s*=\s*'([^']+)'/g)) out.add(m[1])
  return [...out]
}

/** 中央同步键：`useAdjustmentCentralSync({ … itemId: '…' … })` 的 `itemId`。 */
export function extractCentralSyncKeys(src: string): string[] {
  const out = new Set<string>()
  for (const c of findCalls(src, /useAdjustmentCentralSync/)) {
    for (const arg of c.args) {
      for (const e of parseObjectLiteral(arg)) {
        if (e.key !== 'itemId') continue
        const lit = e.value.match(/^['"`]([^'"`]+)['"`]$/)
        if (lit) out.add(lit[1])
      }
    }
  }
  return [...out]
}

// ═══════════════════════════════════════════════════════════════════════════
// 写入点分析（键 → 载荷列）
// ═══════════════════════════════════════════════════════════════════════════

export interface WriteSite {
  /** 写入函数名 */
  via: string
  /** 键表达式原文 */
  keyExpr: string
  /** 顶层载荷键值对 */
  payload: ObjectEntry[]
  /** 载荷里非 `null` 的存储列（`{ conclusion: null }` 是显式清空，不算写入列） */
  columns: StorageColumn[]
  /** 载荷是否引用了 `entries`（判「这是 entries 的写入点」） */
  mentionsEntries: boolean
  /** 该写入点所在文件（相对 WP_ROOT） */
  file: string
}

function payloadColumns(payload: ObjectEntry[]): StorageColumn[] {
  const out: StorageColumn[] = []
  for (const e of payload) {
    if (!(STORAGE_COLUMNS as readonly string[]).includes(e.key)) continue
    if (/^null$/.test(e.value)) continue
    out.push(e.key as StorageColumn)
  }
  return [...new Set(out)]
}

function mentionsEntries(text: string): boolean {
  return /\bentries\b/.test(text) || /\bentry\b/.test(text)
}

/**
 * 收集一个文件里的 entries 写入点。覆盖平台实测存在的五种写入调用：
 *   `emit('save', k, obj)` · `debouncedSave(k, obj)` · `saveField(k, obj)`
 *   `saveBatch([{ itemId: k, data: obj }])` · `allResponses(.value)?.set(k, obj)`
 *
 * 最后一种是**乐观本地缓存镜像**（K1-4 / I5-3 / I6-3 走 `onSave(key, value)` 上抛，
 * 列不在调用点可见，唯一可见处就是这面缓存）。契约清单 `_verification` 记载的核实
 * 方法正是「`allResponses.get(key)?.remark` 实际读写列」⇒ 采信该处为列证据。
 */
export function collectWriteSites(src: string, file: string): WriteSite[] {
  const out: WriteSite[] = []
  const push = (via: string, keyExpr: string, payloadRaw: string, extraText = '') => {
    const payload = parseObjectLiteral(payloadRaw)
    out.push({
      via,
      keyExpr: keyExpr.trim(),
      payload,
      columns: payloadColumns(payload),
      mentionsEntries: mentionsEntries(payloadRaw) || mentionsEntries(extraText),
      file,
    })
  }

  for (const c of findCalls(src, /\bemit/)) {
    if (!/^['"`]save['"`]$/.test((c.args[0] ?? '').trim())) continue
    if (c.args.length < 3) continue
    push("emit('save')", c.args[1], c.args[2])
  }
  for (const name of ['debouncedSave', 'saveField']) {
    for (const c of findCalls(src, new RegExp(`\\b${name}`))) {
      if (c.args.length < 2) continue
      push(name, c.args[0], c.args[1])
    }
  }
  for (const c of findCalls(src, /\bsaveBatch/)) {
    const arr = (c.args[0] ?? '').trim()
    const inner = arr.startsWith('[') ? arr.slice(1, Math.max(1, matchBracket(arr, 0))) : arr
    for (const el of splitTopLevel(inner)) {
      const obj = parseObjectLiteral(el)
      const idEntry = obj.find((e) => e.key === 'itemId')
      if (!idEntry) continue
      const dataEntry = obj.find((e) => e.key === 'data')
      push('saveBatch', idEntry.value, dataEntry ? dataEntry.value : '{}', el)
    }
  }
  // `saveBatch(<变量>)` —— 载荷数组在调用点之外构造（L6-3 / M1-3 / M2-3 实测：
  // `const items = entries.value.map(...).flat()` 里才是 `{ itemId: …, data: { remark: … } }`）。
  // 只解析调用实参会让这三张**取不到写入列** ⇒ 机制判不出 ⇒ 被误标 pending_manual。
  // 故按**结构**扫 `{ itemId: …, data: … }` 元素字面量本身（两个键都在才算，避免把
  // `useAdjustmentCentralSync({ …, itemId })` 的选项对象当成写入载荷）。
  for (const m of src.matchAll(/\{\s*itemId\s*:/g)) {
    const start = m.index ?? -1
    if (start < 0) continue
    const end = matchBracket(src, start)
    if (end < 0) continue
    const obj = parseObjectLiteral(src.slice(start, end + 1))
    const idEntry = obj.find((e) => e.key === 'itemId')
    const dataEntry = obj.find((e) => e.key === 'data')
    if (!idEntry || !dataEntry) continue
    push('saveBatch item literal', idEntry.value, dataEntry.value, src.slice(start, end + 1))
  }
  for (const c of findCalls(src, /allResponses(?:\.value)?\.set/)) {
    if (c.args.length < 2) continue
    push('allResponses.set', c.args[0], c.args[1])
  }
  return out
}

// ═══════════════════════════════════════════════════════════════════════════
// 机制识别（E18：机制 ⇒ 列，列由机制实现源码实测）
// ═══════════════════════════════════════════════════════════════════════════

export type Mechanism = 'formdata_setfield' | 'adjustment_savebatch'
export type KeyFamily = 'single_json' | 'per_field' | 'per_field_plus_data'

export interface MechanismProbe {
  mechanism: Mechanism | null
  /** 由机制实现源码实测得出的写入列（**非常量**） */
  column: StorageColumn | null
  /** 取得依据链（file:符号 逐段留痕） */
  trail: string[]
  /** 判不出时的理由（fail-loud，不静默放过） */
  reasons: string[]
}

export interface SheetProbe extends MechanismProbe {
  sheet: string
  cycle: string
  /** 确证的 entries 数据键（族键已归约） */
  entryKeys: string[]
  keyFamily: KeyFamily | null
  /** 逐字段族的后缀集（不含 `data`；`M9-3` 实测多一个 `ociBlock`） */
  perFieldSuffixes: string[]
  /** 命中的提取形态 */
  forms: ExtractionForm[]
  /** 已排除的复核键 */
  reviewKeys: string[]
  /** 已排除的中央同步键 */
  centralSyncKeys: string[]
  /** 同 sheet 的其它数据键（审计说明/结论等，不是 entries 键，不参与 item_id 比对） */
  otherDataKeys: string[]
  /** 键可确证 = 有 entries 数据键 + 机制 + 列 三者齐全 */
  confirmed: boolean
  /** R2.6：键不可确证 ⇒ 待人工核 */
  pendingManual: boolean
  files: { tab: string | null; adjustment: string | null; formData: string | null }
}

export interface ProbeOptions {
  sources?: SourceBundle
  /**
   * 反向自检 (b)：强制机制探针对某 sheet 返回另一种机制（列随之由该机制的实现源码
   * 重新实测）。仅测试用。
   */
  mechanismOverride?: Record<string, Mechanism>
}

function relTab(cycle: string): string {
  return `${cycle.toLowerCase()}/core/${cycle}TabAdjustment.vue`
}
function relAdjustment(cycle: string): string {
  return `composables/use${cycle}Adjustment.ts`
}
function relFormData(cycle: string): string {
  return `composables/use${cycle}FormData.ts`
}

/**
 * 形态④步②③ 的产物 —— `use{X}FormData` 侧的**键拼装规则 + 写入列**。
 *
 * 抽成独立结构，是为了让「entries 键」（`probeFormDataSetField`）与「同 sheet 的表级
 * 独立键」（`collectSetFieldOtherKeys`）**共用同一套拼装规则**，不在探针里留第二份口径。
 */
interface SetFieldAssembler {
  /** `use{X}FormData.ts` 模块级 `ITEM_PREFIX` 字面量 */
  prefix: string
  /** `setField` 体内的键拼装模板原文（含 `${ITEM_PREFIX}` / `${sheet}` / `${field}` 插值） */
  tplRaw: string
  /** `setField` 体内 `saveField(itemId, { … })` 载荷实测出的写入列 */
  column: StorageColumn
  fdRel: string
  /** 依据链片段：`ITEM_PREFIX` 那一段（由调用方按既有顺序 push，保持 trail 顺序不变） */
  prefixTrail: string
  /** 依据链片段：写入列那一段 */
  columnTrail: string
}

/**
 * 形态④步②③：顺 tab 的 import 定位 `use{X}FormData.ts`，取模块级 `ITEM_PREFIX` +
 * `setField` 体内的键拼装模板与写入列。任一步取不到 ⇒ `asm = null` 且带可读理由。
 */
function resolveSetFieldAssembler(
  cycle: string,
  tab: string,
  tabRel: string,
  src: SourceBundle,
): { asm: SetFieldAssembler | null; reasons: string[] } {
  const reasons: string[] = []
  // 步② —— 顺 import 定位 use{X}FormData.ts，取模块级 ITEM_PREFIX
  const importRe = new RegExp(`import\\s*\\{[^}]*\\buse${cycle}FormData\\b[^}]*\\}\\s*from\\s*['"]([^'"]+)['"]`)
  const im = tab.match(importRe)
  if (!im) {
    reasons.push(`形态④步②：${tabRel} 未 import use${cycle}FormData ⇒ 链断`)
    return { asm: null, reasons }
  }
  const fdRel = relFormData(cycle)
  const fdRaw = src.read(fdRel)
  if (fdRaw === null) {
    reasons.push(`形态④步②：import 指向 ${im[1]}，但读不到 ${fdRel}`)
    return { asm: null, reasons }
  }
  const fd = stripComments(fdRaw)
  const prefix = resolveConstLiteral(fd, 'ITEM_PREFIX')
  if (prefix === null) {
    reasons.push(`形态④步②：${fdRel} 无模块级 ITEM_PREFIX 字面量 ⇒ 键前缀无出处`)
    return { asm: null, reasons }
  }

  // 步③ —— setField 函数体内的键拼装表达式与写入列
  const body = extractFunctionBody(fd, 'setField')
  if (!body) {
    reasons.push(`形态④步③：${fdRel} 取不到 setField 函数体`)
    return { asm: null, reasons }
  }
  const tpl = body.match(/`([^`]*\$\{ITEM_PREFIX\}[^`]*)`/)
  if (!tpl) {
    reasons.push(`形态④步③：${fdRel}.setField 体内无含 \${ITEM_PREFIX} 的键拼装模板`)
    return { asm: null, reasons }
  }
  const cols = new Set<StorageColumn>()
  for (const c of findCalls(body, /\bsaveField/)) {
    if (c.args.length < 2) continue
    for (const col of payloadColumns(parseObjectLiteral(c.args[1]))) cols.add(col)
  }
  if (cols.size !== 1) {
    reasons.push(
      `形态④步③：${fdRel}.setField 体内 saveField 载荷解析出 ${cols.size} 个存储列（${[...cols].join('/') || '无'}），无法唯一确定写入列`,
    )
    return { asm: null, reasons }
  }
  const column = [...cols][0]
  return {
    asm: {
      prefix,
      tplRaw: tpl[1],
      column,
      fdRel,
      prefixTrail: `${fdRel}: ITEM_PREFIX = '${prefix}'`,
      columnTrail: `${fdRel}.setField: saveField(itemId, { ${column} }) ⇒ 写入列 '${column}'`,
    },
    reasons,
  }
}

/** 用拼装规则把 `(sheet, field)` 一对实参拼成真键；插值解析不干净即 fail-loud。 */
function assembleSetFieldKey(
  asm: SetFieldAssembler,
  sheetArg: string,
  fieldArg: string,
): { key: string | null; reason: string | null; trail: string } {
  const assembled = asm.tplRaw
    .replace(/\$\{ITEM_PREFIX\}/g, asm.prefix)
    .replace(/\$\{sheet\}/g, sheetArg)
    .replace(/\$\{field\}/g, fieldArg)
  if (/\$\{/.test(assembled)) {
    return {
      key: null,
      reason: `形态④步③：键拼装表达式含无法解析的插值 ⇒ ${assembled}`,
      trail: '',
    }
  }
  return {
    key: assembled,
    reason: null,
    trail: `${asm.fdRel}.setField: itemId = \`${asm.tplRaw}\` ⇒ '${assembled}'`,
  }
}

/**
 * 机制 ① 的三步链（形态 ④）：缺任一步即判「键不可确证」，**不静默放过**。
 *
 *   ① tab 内取 `setField(<sheet 实参>, <field 实参>, <值>)`，其中 `<值>` 引用 entries；
 *      并顺带取 `getField(<同一对实参>)` 作读回证据（不作硬要求 —— N1/N2/N3 走
 *      `allResponses.get(字面量)` 读回，读回宿主判据属 GS10 / 任务 1.6）
 *   ② 顺 tab 的 import 定位 `use{X}FormData.ts`，取其模块级 `ITEM_PREFIX`
 *   ③ 取 `setField` 函数体内的键拼装表达式与写入列（`saveField(itemId, { … })`）
 */
function probeFormDataSetField(
  cycle: string,
  sheetNo: string,
  src: SourceBundle,
): { key: string | null; column: StorageColumn | null; trail: string[]; reasons: string[] } {
  const trail: string[] = []
  const reasons: string[] = []
  const tabRel = relTab(cycle)
  const tabRaw = src.read(tabRel)
  if (tabRaw === null) {
    reasons.push(`形态④步①：找不到 ${tabRel}`)
    return { key: null, column: null, trail, reasons }
  }
  const tab = stripComments(tabRaw)

  // 步① —— setField(<sheet>, <field>, <值引用 entries>)
  let sheetArg: string | null = null
  let fieldArg: string | null = null
  for (const c of findCalls(tab, /\bsetField/)) {
    if (c.args.length < 3) continue
    const s = c.args[0].match(/^['"`]([^'"`]+)['"`]$/)
    const f = c.args[1].match(/^['"`]([^'"`]+)['"`]$/)
    if (!s || !f) continue
    if (!/\bentries\b/.test(c.args[2])) continue
    sheetArg = s[1]
    fieldArg = f[1]
    trail.push(`${tabRel}: setField('${sheetArg}', '${fieldArg}', ${c.args[2].trim()})`)
    break
  }
  if (sheetArg === null || fieldArg === null) {
    reasons.push(
      `形态④步①：${tabRel} 内找不到「实参为字面量且第三参引用 entries」的 setField 调用`,
    )
    return { key: null, column: null, trail, reasons }
  }
  if (sheetArg !== sheetNo) {
    reasons.push(
      `形态④步①：setField 的 sheet 实参是 '${sheetArg}'，与本 sheet 序号 '${sheetNo}' 不符 ⇒ 该调用不属 ${cycle}-${sheetNo}`,
    )
    return { key: null, column: null, trail, reasons }
  }
  const getPair = findCalls(tab, /\bgetField/).some((c) => {
    const s = c.args[0]?.match(/^['"`]([^'"`]+)['"`]$/)
    const f = c.args[1]?.match(/^['"`]([^'"`]+)['"`]$/)
    return !!s && !!f && s[1] === sheetArg && f[1] === fieldArg
  })
  if (getPair) trail.push(`${tabRel}: getField('${sheetArg}', '${fieldArg}')（读回同一对实参）`)

  // 步②③ —— ITEM_PREFIX + 键拼装模板 + 写入列（与表级独立键共用同一套规则）
  const { asm, reasons: asmReasons } = resolveSetFieldAssembler(cycle, tab, tabRel, src)
  if (!asm) {
    reasons.push(...asmReasons)
    return { key: null, column: null, trail, reasons }
  }
  trail.push(asm.prefixTrail)
  const built = assembleSetFieldKey(asm, sheetArg, fieldArg)
  if (built.key === null) {
    reasons.push(built.reason as string)
    return { key: null, column: null, trail, reasons }
  }
  trail.push(built.trail)
  const column = asm.column
  trail.push(asm.columnTrail)

  // 键必须可归属到本 sheet（`{cycle}-{sheetNo}` 前缀）
  const expectPrefix = `${cycle}-${sheetNo}`
  if (!built.key.startsWith(expectPrefix)) {
    reasons.push(
      `形态④：拼出的键 '${built.key}' 不以 '${expectPrefix}' 开头 ⇒ 无法归属到 ${cycle}-${sheetNo}`,
    )
    return { key: null, column, trail, reasons }
  }
  return { key: built.key, column, trail, reasons }
}

/**
 * 写入点扫描的**第六种形态**：tab 内 `formData.setField(<sheet>, <field>, v)` 写的
 * **表级独立键**（不是 entries 键）。
 *
 * 为什么必须补这一形态（任务 3）：`collectWriteSites` 只认 `emit('save')` /
 * `debouncedSave` / `saveField` / `saveBatch` / `allResponses.set` 五种「键 + 载荷」
 * 形态，而 `setField(sheet, field, v)` 的键在**运行期三段拼出**、载荷列在 `use{X}FormData`
 * 体内 ⇒ 该形态写的键在重扫结果里整个缺席。`N5-3` 的 `N5-3-audit-notes` /
 * `N5-3-audit-conclusion` 正是这样两个真实数据落点（清单已登记）。
 * 只扩 `declaredKeys()`（读 `observed.entries_keys + other_data_keys`）而不扩本扫描，
 * `N5-3` 会以「登记 3 键 vs 重扫 1 键」**被动变红** ⇒ 两侧必须成对改。
 *
 * 排除面：①`sheet` 实参 ≠ 本 sheet 序号（`N1/N2/N3` 的 `setField('1','aje-net',…)` 属
 * X-1 审定表勾稽面，不是本表键）②第三参引用 `entries`（那次属 entries 键，由步①承担）。
 * **不按名字剔除**复核键/中央同步键 —— 这些键由三步链证过出处（G11 / E12 → E17 的教训）。
 */
function collectSetFieldOtherKeys(
  cycle: string,
  sheetNo: string,
  src: SourceBundle,
): { keys: string[]; trail: string[]; reasons: string[] } {
  const keys: string[] = []
  const trail: string[] = []
  const reasons: string[] = []
  const tabRel = relTab(cycle)
  const tabRaw = src.read(tabRel)
  if (tabRaw === null) return { keys, trail, reasons }
  const tab = stripComments(tabRaw)

  const fields: string[] = []
  for (const c of findCalls(tab, /\bsetField/)) {
    if (c.args.length < 3) continue
    const s = c.args[0].match(/^['"`]([^'"`]+)['"`]$/)
    const f = c.args[1].match(/^['"`]([^'"`]+)['"`]$/)
    if (!s || !f) continue
    if (s[1] !== sheetNo) continue
    if (mentionsEntries(c.args[2])) continue
    if (!fields.includes(f[1])) fields.push(f[1])
  }
  if (!fields.length) return { keys, trail, reasons }

  const { asm, reasons: asmReasons } = resolveSetFieldAssembler(cycle, tab, tabRel, src)
  if (!asm) {
    for (const r of asmReasons) reasons.push(`表级独立键（setField 形态）：${r}`)
    return { keys, trail, reasons }
  }
  const expectPrefix = `${cycle}-${sheetNo}`
  for (const field of fields) {
    const built = assembleSetFieldKey(asm, sheetNo, field)
    if (built.key === null) {
      reasons.push(`表级独立键（setField 形态）：${built.reason}`)
      continue
    }
    if (!built.key.startsWith(expectPrefix)) {
      reasons.push(
        `表级独立键（setField 形态）：拼出的键 '${built.key}' 不以 '${expectPrefix}' 开头 ⇒ 无法归属到 ${cycle}-${sheetNo}`,
      )
      continue
    }
    keys.push(built.key)
    trail.push(
      `${tabRel}: setField('${sheetNo}', '${field}', …) ⇒ 表级独立键 '${built.key}'（写入列 '${asm.column}'）`,
    )
  }
  return { keys: [...new Set(keys)].sort(), trail, reasons }
}

/** 机制 ②：`use{X}Adjustment.ts` 的 `saveBatch` / `debouncedSave` / `saveField` 写 entries。 */
function probeAdjustmentComposable(
  cycle: string,
  sheetNo: string,
  src: SourceBundle,
): {
  keys: string[]
  suffixes: string[]
  family: KeyFamily | null
  column: StorageColumn | null
  trail: string[]
  reasons: string[]
  otherKeys: string[]
} {
  const trail: string[] = []
  const reasons: string[] = []
  const empty = {
    keys: [] as string[],
    suffixes: [] as string[],
    family: null as KeyFamily | null,
    column: null as StorageColumn | null,
    trail,
    reasons,
    otherKeys: [] as string[],
  }
  const rels = [relAdjustment(cycle), relTab(cycle)].filter((r) => src.exists(r))
  if (!rels.length) {
    reasons.push(`机制②：既无 ${relAdjustment(cycle)} 也无 ${relTab(cycle)}`)
    return empty
  }

  const expect = `${cycle}-${sheetNo}`
  const entryKeys = new Set<string>()
  const suffixes = new Set<string>()
  const otherKeys = new Set<string>()
  const cols = new Set<StorageColumn>()
  let hasData = false
  let hasFamily = false

  for (const rel of rels) {
    const raw = src.read(rel)
    if (raw === null) continue
    const s = stripComments(raw)
    const sites = collectWriteSites(s, rel)
    const excluded = new Set([...extractReviewKeys(s), ...extractCentralSyncKeys(s)])
    for (const site of sites) {
      // 键表达式 → 具体键 / 族键
      const fam = extractTemplateFamilyKeys(site.keyExpr)
      if (fam.length) {
        for (const f of fam) {
          if (!belongsToSheet(f.keyPrefix, cycle, sheetNo)) continue
          hasFamily = true
          if (f.suffix === 'data') hasData = true
          else suffixes.add(f.suffix)
          entryKeys.add(f.familyKey)
          for (const c of site.columns) cols.add(c)
          trail.push(`${rel}: ${site.via}(\`${f.keyPrefix}-entry-\${n}-${f.suffix}\`, { ${site.columns.join('/') || '?'} })`)
        }
        continue
      }
      const key = resolveKeyExpr(site.keyExpr, s)
      if (!key) continue
      if (excluded.has(key)) continue
      if (!key.startsWith(expect) && !key.startsWith(`${cycle}-${expect}`)) continue
      if (site.mentionsEntries) {
        entryKeys.add(key)
        for (const c of site.columns) cols.add(c)
        trail.push(`${rel}: ${site.via}('${key}', { ${site.columns.join('/') || '?'} })`)
      } else {
        otherKeys.add(key)
      }
    }
    // 逐字段族在同一文件里也可能只出现在非写入语句（如 restore 侧）；补扫一遍族键
    for (const f of extractTemplateFamilyKeys(s)) {
      if (!belongsToSheet(f.keyPrefix, cycle, sheetNo)) continue
      hasFamily = true
      if (f.suffix === 'data') hasData = true
      else if (f.suffix !== '*') suffixes.add(f.suffix)
      entryKeys.add(f.familyKey)
    }
  }

  if (!entryKeys.size) {
    reasons.push(`机制②：${rels.join(' / ')} 内找不到可归属 ${expect} 的 entries 写入点`)
    return empty
  }
  if (cols.size !== 1) {
    reasons.push(
      `机制②：entries 写入点解析出 ${cols.size} 个存储列（${[...cols].join('/') || '无'}），无法唯一确定写入列`,
    )
    return { ...empty, keys: [...entryKeys].sort(), suffixes: [...suffixes].sort(), otherKeys: [...otherKeys].sort() }
  }
  const family: KeyFamily = hasFamily ? (hasData ? 'per_field_plus_data' : 'per_field') : 'single_json'
  return {
    keys: [...entryKeys].sort(),
    suffixes: [...suffixes].sort(),
    family,
    column: [...cols][0],
    trail,
    reasons,
    otherKeys: [...otherKeys].sort(),
  }
}

/** 键前缀（`M4-3` / `L6-L6-3`）是否归属 `{cycle}-{sheetNo}`。 */
function belongsToSheet(keyPrefix: string, cycle: string, sheetNo: string): boolean {
  return keyPrefix === `${cycle}-${sheetNo}` || keyPrefix === `${cycle}-${cycle}-${sheetNo}`
}

/** 键表达式 → 具体键：引号字面量 / 无插值模板 / 模块级常量标识符 / `${ITEM_PREFIX}-x`。 */
function resolveKeyExpr(expr: string, src: string): string | null {
  const e = expr.trim()
  const lit = e.match(/^['"`]([^'"`${]+)['"`]$/)
  if (lit) return lit[1]
  const ident = e.match(/^[A-Za-z_$][\w$]*$/)
  if (ident) return resolveConstLiteral(src, e)
  const tpl = e.match(/^`([^`]*)`$/)
  if (tpl) {
    const prefix = resolveConstLiteral(src, 'ITEM_PREFIX')
    if (prefix !== null) {
      const filled = tpl[1].replace(/\$\{ITEM_PREFIX\}/g, prefix)
      if (!/\$\{/.test(filled)) return filled
    }
  }
  return null
}

// ═══════════════════════════════════════════════════════════════════════════
// 逐 sheet 探测
// ═══════════════════════════════════════════════════════════════════════════

export function probeSheet(cycle: string, opts: ProbeOptions = {}): SheetProbe {
  const src = opts.sources ?? createSourceBundle()
  const sheetNo = X3_SHEET_NO
  const sheet = `${cycle}-${sheetNo}`
  const tabRel = relTab(cycle)
  const tabRaw = src.read(tabRel)
  const tab = tabRaw === null ? '' : stripComments(tabRaw)

  const reviewKeys = new Set(extractReviewKeys(tab))
  const centralSyncKeys = new Set(extractCentralSyncKeys(tab))
  const adjRel = relAdjustment(cycle)
  const adjRaw = src.read(adjRel)
  if (adjRaw !== null) {
    const adj = stripComments(adjRaw)
    for (const k of extractReviewKeys(adj)) reviewKeys.add(k)
    for (const k of extractCentralSyncKeys(adj)) centralSyncKeys.add(k)
  }

  const mech1 = probeFormDataSetField(cycle, sheetNo, src)
  const mech2 = probeAdjustmentComposable(cycle, sheetNo, src)
  // 写入点扫描的第六种形态（`setField` 写的表级独立键）—— 与 `declaredKeys()` 的口径成对
  const setFieldOther = collectSetFieldOtherKeys(cycle, sheetNo, src)

  const forms = new Set<ExtractionForm>()
  if (mech1.key) forms.add('cross_file_runtime')
  for (const k of mech2.keys) {
    if (k.endsWith('-entry-*')) forms.add('template_per_field')
    else forms.add('quoted_literal')
  }
  if (adjRaw !== null && extractItemPrefixKeys(stripComments(adjRaw)).length) {
    forms.add('item_prefix_concat')
  }

  const reasons: string[] = []
  let mechanism: Mechanism | null = null
  let column: StorageColumn | null = null
  let entryKeys: string[] = []
  let keyFamily: KeyFamily | null = null
  let perFieldSuffixes: string[] = []
  const trail: string[] = []

  const has1 = !!mech1.key && !!mech1.column
  const has2 = mech2.keys.length > 0 && !!mech2.column

  if (has1 && has2) {
    // 两条通路命中同一个存储目标 ≠ 机制歧义。
    // N1-3 实测：tab 内既 `formData.setField('3','entries', …)`（机制①三步链）
    // 又 `formData.debouncedSave('N1-3-entries', { conclusion: … })`（同一个 formData
    // 门面的直呼形态）—— 键与列**逐字相同** ⇒ 同一通路的两种调用写法。
    // 此时取机制①（design §storage_field 机制归类把 N1-3 记为 ①，且三步链是可解释、
    // 可守卫的那一条），两条依据链都留痕。**只有键或列真分叉才判歧义**，
    // 否则「机制歧义」会把 4 张机制① sheet 里唯一多写了一处直呼的那张误标 pending。
    const sameKey = mech2.keys.length === 1 && mech2.keys[0] === mech1.key
    const sameColumn = mech1.column === mech2.column
    if (sameKey && sameColumn) {
      mechanism = 'formdata_setfield'
      column = mech1.column
      entryKeys = [mech1.key as string]
      keyFamily = 'single_json'
      trail.push(...mech1.trail, ...mech2.trail)
    } else {
      reasons.push(
        `机制歧义：形态④（键 ${mech1.key} / 列 ${mech1.column}）与机制②（键 ${mech2.keys.join(', ')} / 列 ${mech2.column}）不一致 ⇒ 需人工核`,
      )
    }
  } else if (has1) {
    mechanism = 'formdata_setfield'
    column = mech1.column
    entryKeys = [mech1.key as string]
    keyFamily = 'single_json'
    trail.push(...mech1.trail)
  } else if (has2) {
    mechanism = 'adjustment_savebatch'
    column = mech2.column
    entryKeys = mech2.keys
    keyFamily = mech2.family
    perFieldSuffixes = mech2.suffixes
    trail.push(...mech2.trail)
  } else {
    reasons.push(...mech1.reasons, ...mech2.reasons)
  }

  // 第六种写入形态的留痕与 fail-loud（只在真有 `setField('{sheetNo}', <非 entries>)` 调用
  // 却拼不出键时才报理由 —— 没有这类调用不是缺陷，不制造噪声理由）
  trail.push(...setFieldOther.trail)
  reasons.push(...setFieldOther.reasons)

  // 反向自检 (b)：强制机制 ⇒ 列改由被强制机制的实现源码重新实测
  const forced = opts.mechanismOverride?.[sheet]
  if (forced && mechanism) {
    mechanism = forced
    column = forced === 'formdata_setfield' ? mech1.column : mech2.column
    if (column === null) {
      // 被强制的机制在该 sheet 上没有实现 ⇒ 用另一机制实测到的列做「错列」代入，
      // 使「机制 ⇒ 列」的分叉一定暴露（而不是退化成 null 静默跳过）
      column = forced === 'formdata_setfield' ? 'conclusion' : 'remark'
    }
    trail.push(`[override] 机制被强制为 ${forced} ⇒ 列 '${column}'`)
  }

  // 最终排除两类非数据键（R2.4）—— **只作用于字面量扫描来的键**（机制②）。
  //
  // 形态 ④ 的键由三步链在运行期拼出，来源已证（tab 的 setField 实参 + use{X}FormData
  // 的 ITEM_PREFIX + setField 体内拼装表达式）⇒ 不得因为「与某个非数据键同名」被剔除。
  // N5-3 正是这一例（design E12 → E17 / G11）：tab 内那个 `'N5-3-entries'` 字面量属
  // `useAdjustmentCentralSync` 的中央同步键，与真数据键**同名纯属巧合**。按名字剔除
  // 就会重犯 E12 那个「按字面量 grep 判 N5-3 键不可确证」的错。
  if (mechanism === 'adjustment_savebatch') {
    entryKeys = entryKeys.filter((k) => !reviewKeys.has(k) && !centralSyncKeys.has(k))
  }

  const confirmed = entryKeys.length > 0 && mechanism !== null && column !== null
  return {
    sheet,
    cycle,
    mechanism,
    column,
    trail,
    reasons,
    entryKeys,
    keyFamily: confirmed ? keyFamily : null,
    perFieldSuffixes,
    forms: [...forms],
    reviewKeys: [...reviewKeys].sort(),
    centralSyncKeys: [...centralSyncKeys].sort(),
    otherDataKeys: [...new Set([...mech2.otherKeys, ...setFieldOther.keys])].sort(),
    confirmed,
    pendingManual: !confirmed,
    files: {
      tab: tabRaw === null ? null : tabRel,
      adjustment: adjRaw === null ? null : adjRel,
      formData: src.exists(relFormData(cycle)) ? relFormData(cycle) : null,
    },
  }
}

export function probeAllX3(opts: ProbeOptions = {}): Record<string, SheetProbe> {
  const src = opts.sources ?? createSourceBundle()
  const out: Record<string, SheetProbe> = {}
  for (const cycle of X3_TARGET_CYCLES) {
    out[`${cycle}-${X3_SHEET_NO}`] = probeSheet(cycle, { ...opts, sources: src })
  }
  return out
}

// ═══════════════════════════════════════════════════════════════════════════
// 通用写入列实测（供既有 aligned sheet 的 E14 判据用）
// ═══════════════════════════════════════════════════════════════════════════

export interface ObservedColumnResult {
  /** 实测到的写入列集合（应恰为 1 个） */
  columns: StorageColumn[]
  /** 取得依据 */
  trail: string[]
}

/**
 * 给定一个**具体 item_id**，在全部调整分录源文件里实测其写入列。
 *
 * 用途：把既有 `Property 9 — storage_field 一致` 的硬断言 `=== 'remark'`（E14 的守卫
 * 缺陷）换成「由源码实测的写入列」比对。判据落在写入点结构上，不含任何列名常量。
 */
export function observeStorageColumn(itemId: string, files: Map<string, string>): ObservedColumnResult {
  const cols = new Set<StorageColumn>()
  const trail: string[] = []
  for (const [rel, raw] of files) {
    const s = stripComments(raw)
    for (const site of collectWriteSites(s, rel)) {
      const key = resolveKeyExpr(site.keyExpr, s)
      if (key !== itemId) continue
      if (!site.columns.length) continue
      for (const c of site.columns) cols.add(c)
      trail.push(`${rel}: ${site.via}('${itemId}', { ${site.columns.join('/')} })`)
    }
  }
  return { columns: [...cols], trail }
}

// ═══════════════════════════════════════════════════════════════════════════
// 契约清单读取（含替身注入）
// ═══════════════════════════════════════════════════════════════════════════

export interface ContractDoc {
  sheets: Record<string, any>
  exempt: Record<string, any>
  _iron_rules?: string[]
  _source?: string
  [k: string]: any
}

export function loadContract(): ContractDoc {
  return JSON.parse(fs.readFileSync(path.join(REPO_ROOT, CONTRACT_REL), 'utf8')) as ContractDoc
}

export interface DeclaredColumn {
  value: string | null
  /** 取自清单的哪个位置（供失败消息定位） */
  from: string
}

/**
 * 取清单登记的写入列。
 *
 * 迁入 `sheets` 后是 `sheets[X].storage_field`（任务 2.1 的目标态）；当前 16 张仍挂
 * `exempt`，其中 N1/N2/N3 用 `observed.frontend_field` 记了列、其余未记 ⇒ 本函数
 * 两处都找，找不到返回 `null`（消费方据此判「未登记」而**不是**跳过）。
 */
export function declaredStorageField(contract: ContractDoc, sheet: string): DeclaredColumn {
  const s = contract.sheets?.[sheet]
  if (s && typeof s.storage_field === 'string') {
    return { value: s.storage_field, from: `sheets.${sheet}.storage_field` }
  }
  const e = contract.exempt?.[sheet]
  if (e) {
    const obs = e.observed ?? {}
    if (typeof obs.frontend_field === 'string') {
      return { value: obs.frontend_field, from: `exempt.${sheet}.observed.frontend_field` }
    }
    if (typeof e.storage_field === 'string') {
      return { value: e.storage_field, from: `exempt.${sheet}.storage_field` }
    }
    return { value: null, from: `exempt.${sheet}（未登记写入列）` }
  }
  return { value: null, from: `${sheet} 在清单中完全无登记` }
}

/**
 * 取清单登记的**全部数据键**（`observed` 侧）。R7.5 的比对基准。
 *
 * 口径（任务 3 扩，与探针第六种写入形态成对）：已迁入 `sheets` 的条目读
 * `observed.entries_keys + observed.other_data_keys` —— 只读单个 `item_id` 时，
 * 「entries 族键 + 表级独立说明键」这类**一张表两个数据落点**的条目（实测 `M2-3` /
 * `M8-3` / `N5-3`）会以「登记 1 键 vs 重扫 2~3 键」被判不一致，而正解绝不是删掉
 * 说明键的登记（那会丢一个真实数据落点、导入往返丢数据）。
 *
 * `item_id` 仍是三重键之一（后端 `test_x3_key_ledger.py` 与 P8-G 各自钉住它），
 * 消费方应另行断言 `item_id ∈ 本函数返回的键集`，防「扩口径」变成绕过 `item_id` 的口子。
 * `observed` 缺失时退回 `item_id`（老条目形态）。
 */
export function declaredKeys(contract: ContractDoc, sheet: string): { keys: string[]; from: string } {
  const s = contract.sheets?.[sheet]
  if (s) {
    const obs = s.observed ?? {}
    const keys: string[] = []
    if (Array.isArray(obs.entries_keys)) keys.push(...obs.entries_keys)
    if (Array.isArray(obs.other_data_keys)) keys.push(...obs.other_data_keys)
    if (keys.length) {
      return {
        keys: [...new Set(keys)].sort(),
        from: `sheets.${sheet}.observed.entries_keys + other_data_keys`,
      }
    }
    if (typeof s.item_id === 'string') return { keys: [s.item_id], from: `sheets.${sheet}.item_id` }
  }
  const e = contract.exempt?.[sheet]
  if (e) {
    const obs = e.observed ?? {}
    const keys: string[] = []
    if (Array.isArray(obs.frontend_keys)) keys.push(...obs.frontend_keys)
    if (typeof obs.frontend_key === 'string') keys.push(obs.frontend_key)
    return { keys: [...new Set(keys)].sort(), from: `exempt.${sheet}.observed` }
  }
  return { keys: [], from: `${sheet} 在清单中完全无登记` }
}

// ═══════════════════════════════════════════════════════════════════════════
// AJE / RJE 枚举**大小写**：清单登记值 ↔ 前端源码实测值（任务 2.4）
//
// 🔴 为什么必须有这一路判据（补的是一个实测出来的 GREEN）：
// 后端 `test_x3_key_ledger.py` 只能把「实现落的值」与「清单登记的值」互相比对 ——
// 清单登记错了大小写（例：给大写形态的 `M4-3` 登记成 `'aje'`），实现照登记落值，
// 两侧逐字相等 ⇒ **全绿**，而用户导入的行会从界面按 AJE / RJE 分区的视图里消失
// （`filter` 全不命中 = 静默丢行）。这正是 memory 记的「守卫把错值当基线锁死」。
// 大小写的真源只有一处 —— 前端源码里「界面按什么值 filter」，而后端读不到 `.vue`，
// 故这一路只能落在前端探针侧（与 §GS9 机制探针同一分工）。
// ═══════════════════════════════════════════════════════════════════════════

/** AJE / RJE 两个规范值（大小写形态逐 sheet 实测，此处只作「哪一侧」的标签）。 */
export const ENTRY_TYPE_CANONICALS = ['AJE', 'RJE'] as const
export type EntryTypeCanonical = (typeof ENTRY_TYPE_CANONICALS)[number]

/** 联合类型声明：`'AJE' | 'RJE'` / `'aje' | 'rje'`（顺序不限，大小写即待测量的东西）。 */
const ENTRY_TYPE_UNION_RE = /['"]([A-Za-z]{3})['"]\s*\|\s*['"]([A-Za-z]{3})['"]/g

function canonicalOf(literal: string): EntryTypeCanonical | null {
  const up = literal.toUpperCase()
  return up === 'AJE' || up === 'RJE' ? (up as EntryTypeCanonical) : null
}

/** 与某字段作**等值比较**的字面量：`e.type === 'AJE'` / `raw.entryType !== 'RJE'`。 */
function fieldCompareRe(field: string): RegExp {
  return new RegExp(
    `(?:^|[^\\w$])(?:[\\w$]+\\.)*${field}\\s*[=!]==?\\s*['"]([A-Za-z]{3})['"]`,
    'g',
  )
}

export interface EntryTypeCasingProbe {
  sheet: string
  /** 规范值 → 本 sheet 实测字面量；判不出的方向该键缺失（不猜、不兜底） */
  values: Partial<Record<EntryTypeCanonical, string>>
  /** 依据链（`文件:行号  原文`，逐条可复算） */
  trail: string[]
  /** 判不出 / 自相矛盾的理由（fail-loud） */
  reasons: string[]
}

/**
 * 从前端源码实测某张 X-3 的 AJE / RJE 字面量。
 *
 * 判据 = 「**界面按什么值 filter**」，两类证据都取（同一方向出现两种拼写即判自相矛盾）：
 *   (A) 联合类型声明 —— `export type M4AdjustmentType = 'AJE' | 'RJE'`、
 *       `type AdjustmentType = 'AJE' | 'RJE'`、`ref<'AJE' | 'RJE'>(…)`、行模型内联字段；
 *   (B) 与该字段的等值比较 —— `entries.value.filter(e => e.type === 'AJE')`、
 *       `raw.entryType === 'RJE' ? … : …`。
 *
 * 刻意**不**采信两类噪声：
 *   * `adjustmentType: activeType.value === 'RJE' ? 'rje' : 'aje'` —— 这是跨底稿推送
 *     （A13 / B50）载荷里的 `adjustmentType`，与行模型的 `type` 是两个字段，实测 16 张
 *     全是小写；把它当证据会把 15 张大写 sheet 全判成自相矛盾；
 *   * `type: 'AJE'`（新增行默认值）与 `handleDeleteEntry(row, 'aje')`（实参）—— 不是
 *     「界面按什么值 filter」，不进证据面（但若与 filter 侧冲突，(A)(B) 已足以判红）。
 *
 * `field` 取自清单登记的 `unmapped_fields[].field`（实测 `L2-3` 是 `entryType`、其余
 * 15 张是 `type`）—— 顺带把字段名也钉住了：字段名登记错 ⇒ (B) 一条证据都取不到 ⇒
 * `reasons` 非空 ⇒ 消费方打红。
 */
export function probeEntryTypeCasing(
  cycle: string,
  field: string,
  opts: ProbeOptions = {},
): EntryTypeCasingProbe {
  const src = opts.sources ?? createSourceBundle()
  const sheet = `${cycle}-${X3_SHEET_NO}`
  const found = new Map<EntryTypeCanonical, Set<string>>()
  const trail: string[] = []
  const reasons: string[] = []

  const note = (rel: string, text: string, at: number, tag: string) => {
    const line = text.slice(0, at).split('\n').length
    const body = (text.split('\n')[line - 1] ?? '').trim()
    trail.push(`[${tag}] ${rel}:${line}  ${body}`)
  }
  const take = (lit: string, rel: string, text: string, at: number, tag: string) => {
    const canonical = canonicalOf(lit)
    if (!canonical) return
    if (!found.has(canonical)) found.set(canonical, new Set())
    found.get(canonical)!.add(lit)
    note(rel, text, at, tag)
  }

  for (const rel of [relTab(cycle), relAdjustment(cycle)]) {
    const raw = src.read(rel)
    if (raw === null) continue
    // `stripComments` 保持偏移量 ⇒ 上面按 offset 反算的行号与磁盘原文逐行对齐
    const text = stripComments(raw)

    ENTRY_TYPE_UNION_RE.lastIndex = 0
    for (let m = ENTRY_TYPE_UNION_RE.exec(text); m; m = ENTRY_TYPE_UNION_RE.exec(text)) {
      const pair = [m[1], m[2]]
      const canon = pair.map(canonicalOf)
      if (canon[0] === null || canon[1] === null || canon[0] === canon[1]) continue
      take(pair[0], rel, text, m.index, 'union')
      take(pair[1], rel, text, m.index, 'union')
    }

    const cmp = fieldCompareRe(field)
    for (let m = cmp.exec(text); m; m = cmp.exec(text)) {
      take(m[1], rel, text, m.index, 'filter')
    }
  }

  const values: Partial<Record<EntryTypeCanonical, string>> = {}
  for (const canonical of ENTRY_TYPE_CANONICALS) {
    const spellings = [...(found.get(canonical) ?? [])]
    if (spellings.length === 0) {
      reasons.push(
        `${sheet}: 源码里判不出 ${canonical} 方向的字面量（字段名 '${field}'；` +
          `联合类型声明与 ${field} 的等值比较两类证据都没命中）`,
      )
    } else if (spellings.length > 1) {
      reasons.push(
        `${sheet}: ${canonical} 方向实测出多种拼写 ${JSON.stringify(spellings)} ⇒ 源码自相矛盾，不猜`,
      )
    } else {
      values[canonical] = spellings[0]
    }
  }
  return { sheet, values, trail, reasons }
}

export interface DeclaredCasing {
  /** 清单登记的 `(AJE 侧, RJE 侧)` 字面量；未登记为 `null` */
  values: Record<EntryTypeCanonical, string> | null
  /** 该 sheet 的 entryType 字段名（`unmapped_fields[].field`）；取不到为 `null` */
  field: string | null
  from: string
}

/** 「AJE/RJE 标记」条目锚点（与后端实现的 `_ENTRY_TYPE_MARKER_RE` 同形）。 */
const CONTRACT_MARKER_RE = /AJE\s*\/\s*RJE\s*标记/
/** 「取值 'x' | 'y'」枚举对（与后端实现的 `_ENTRY_TYPE_ENUM_RE` 同形）。 */
const CONTRACT_ENUM_RE = /取值\s*['"]([A-Za-z]{2,8})['"]\s*\|\s*['"]([A-Za-z]{2,8})['"]/

/**
 * 取清单登记的 AJE / RJE 字面量与字段名。
 *
 * **独立解析**是要点：直接读后端 `spec.entry_type_values` 当期望值，判据会退化成
 * 「实现和自己比」；这里从清单原文的「取值 'x' | 'y'」句式重新解析一次，与前端源码实测
 * 值比对，才构成「清单 ↔ 真源」的那一路。
 */
export function declaredEntryTypeCasing(contract: ContractDoc, sheet: string): DeclaredCasing {
  const entry = contract.sheets?.[sheet] ?? contract.exempt?.[sheet]
  const where = contract.sheets?.[sheet] ? `sheets.${sheet}` : `exempt.${sheet}`
  const items: any[] = Array.isArray(entry?.unmapped_fields) ? entry.unmapped_fields : []
  const hits = items.filter(
    (it) => it && typeof it.handling === 'string' && CONTRACT_MARKER_RE.test(it.handling),
  )
  if (hits.length !== 1) {
    return {
      values: null,
      field: null,
      from: `${where}.unmapped_fields（「AJE/RJE 标记」条目实测 ${hits.length} 处，须 1）`,
    }
  }
  const item = hits[0]
  const field = typeof item.field === 'string' && item.field ? item.field : null
  const m = CONTRACT_ENUM_RE.exec(item.handling)
  if (!m) {
    return { values: null, field, from: `${where}.unmapped_fields[AJE/RJE].handling（未登记枚举形态）` }
  }
  const byCanonical: Partial<Record<EntryTypeCanonical, string>> = {}
  for (const lit of [m[1], m[2]]) {
    const canonical = canonicalOf(lit)
    if (canonical) byCanonical[canonical] = lit
  }
  if (!byCanonical.AJE || !byCanonical.RJE) {
    return {
      values: null,
      field,
      from: `${where}.unmapped_fields[AJE/RJE].handling（登记的枚举对 ${JSON.stringify([m[1], m[2]])} 不对应 AJE / RJE）`,
    }
  }
  return {
    values: { AJE: byCanonical.AJE, RJE: byCanonical.RJE },
    field,
    from: `${where}.unmapped_fields[AJE/RJE].handling`,
  }
}

/**
 * E14 回归锚点：**旧**判据（硬断言写入列 === 某个常量）。
 *
 * 仅供消费方证明「旧判据会把机制 ① 的 4 张判违规、新的机制推导判据不会」，
 * 不参与任何正向断言。常量取自旧代码原样（`'remark'`）。
 */
export const LEGACY_HARDCODED_STORAGE_FIELD = 'remark'

export function legacyConstantJudgement(declared: string | null): boolean {
  return declared === LEGACY_HARDCODED_STORAGE_FIELD
}
