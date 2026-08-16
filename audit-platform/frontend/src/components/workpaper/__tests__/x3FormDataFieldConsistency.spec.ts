/**
 * GS11 —— X-3 Tab 读的 formData 字段必须被其 FormData composable 真实导出
 *
 * spec: x3-adjustment-entry-import-export / 任务 15.2 挖出的真实缺陷补的守卫
 *
 * ## 为什么需要（2026-08-16 由 Playwright 实测挖出）
 *
 * `L6TabAdjustment.vue` 的 onMounted / handleImported 调
 * `loadFromResponses(formData.allResponses.value)`，而 `useL6FormData` 导出的是
 * `responses` 不是 `allResponses` ⇒ `formData.allResponses` 为 undefined ⇒
 * 读 `.value` 抛 `Cannot read properties of undefined`，整个 L6-3 Tab 挂载即崩、
 * 刷新后看不到任何导入的行。
 *
 * memory 铁律：**Vue 访问不存在的字段 = 静默失效/崩溃**，Volar / vitest /
 * get_diagnostics / HEAD-swap 四层全绿，只有浏览器真挂载才暴露。本守卫把它拉回静态可检。
 *
 * ## 判据（非字符存在）
 *
 * 对每张 X-3 的 {X}TabAdjustment.vue，提取它读的 `formData.<name>`，<name> 必须出现在
 * 对应 use{X}FormData.ts 的最后一个 `return { ... }` 导出块里。缺失即红。
 *
 * 该文件从 `ieWiringIntegrity.spec.ts` 抽出（后者追加 GS11 后超 1500 行门禁上限；
 * 按「优先拆分而非加 whitelist 豁免」的规矩独立成文）。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'

import { describe, it, expect } from 'vitest'

// ═══════════════════════════════════════════════════════════════════════════
// 仓库根 —— 哨兵文件向上查找（禁写死回退级数）
// ═══════════════════════════════════════════════════════════════════════════

function findRepoRoot(): string {
  let dir = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))
  for (let i = 0; i < 12; i++) {
    if (existsSync(resolve(dir, 'audit-platform/frontend/src/components/workpaper'))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未找到仓库根')
}

const WP_ROOT = resolve(findRepoRoot(), 'audit-platform/frontend/src/components/workpaper')

/** 剥 JS 注释（`//` 与 `/* *​/`），字符串内的不剥。 */
function stripJsComments(src: string): string {
  const out: string[] = []
  let i = 0
  const n = src.length
  let quote: string | null = null
  while (i < n) {
    const ch = src[i]
    if (quote) {
      if (ch === '\\') {
        out.push(ch, src[i + 1] ?? '')
        i += 2
        continue
      }
      if (ch === quote) quote = null
      out.push(ch)
      i++
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch
      out.push(ch)
      i++
      continue
    }
    if (ch === '/' && src[i + 1] === '/') {
      while (i < n && src[i] !== '\n') i++
      continue
    }
    if (ch === '/' && src[i + 1] === '*') {
      i += 2
      while (i < n && !(src[i] === '*' && src[i + 1] === '/')) i++
      i += 2
      continue
    }
    out.push(ch)
    i++
  }
  return out.join('')
}

/** 花括号配对，返回从 from（必须是 `{`）到匹配 `}` 的整段文本。 */
function balancedBrace(src: string, from: number): { text: string } | null {
  let depth = 0
  for (let i = from; i < src.length; i++) {
    const ch = src[i]
    if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) return { text: src.slice(from, i + 1) }
    }
  }
  return null
}

/** 从 use{X}FormData.ts 的最后一个 `return { ... }` 提取导出标识符集合。 */
function exportedFields(fdSrc: string): Set<string> {
  const stripped = stripJsComments(fdSrc)
  const returns = [...stripped.matchAll(/return\s*\{/g)]
  if (returns.length === 0) return new Set()
  const last = returns[returns.length - 1]
  const open = last.index! + last[0].length - 1
  const block = balancedBrace(stripped, open)
  if (!block) return new Set()
  const names = new Set<string>()
  for (const raw of block.text.replace(/^\{|\}$/g, '').split(/[,\n]/)) {
    let tok = raw.trim()
    if (!tok) continue
    if (tok.includes(':')) tok = tok.split(':')[0].trim() // a: b → a
    const m = /^([A-Za-z_$][\w$]*)$/.exec(tok)
    if (m) names.add(m[1])
  }
  return names
}

const X3_CYCLES = [
  'L2', 'L6', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6',
  'M7', 'M8', 'M9', 'M10', 'N1', 'N2', 'N3', 'N5',
]

describe('GS11: X-3 Tab 的 formData 字段引用必须被 FormData composable 导出', () => {
  for (const cyc of X3_CYCLES) {
    it(`${cyc}-3: TabAdjustment 读的 formData.<字段> 必须被 use${cyc}FormData 导出`, () => {
      const tab = resolve(WP_ROOT, cyc.toLowerCase(), 'core', `${cyc}TabAdjustment.vue`)
      const fd = resolve(WP_ROOT, 'composables', `use${cyc}FormData.ts`)
      if (!existsSync(tab) || !existsSync(fd)) {
        // 不是所有 X-3 都用独立 use{X}FormData（有的走宿主注入）；缺文件跳过不误报
        return
      }
      const tabSrc = stripJsComments(readFileSync(tab, 'utf-8'))
      const exported = exportedFields(readFileSync(fd, 'utf-8'))
      const referenced = new Set(
        [...tabSrc.matchAll(/\bformData\.([A-Za-z_$][\w$]*)/g)].map((m) => m[1]),
      )
      const missing = [...referenced].filter((name) => !exported.has(name))
      expect(
        missing,
        `${cyc}TabAdjustment.vue 读的 formData.{${missing.join(', ')}} 未被 use${cyc}FormData 导出` +
          `（导出的是 {${[...exported].sort().join(', ')}}）\n` +
          '→ 运行时 formData.<该字段> 为 undefined，读 .value 会让整个 Tab 挂载崩溃；' +
          '四层守卫查不出，只有浏览器实测暴露（2026-08-16 L6 踩过）。',
      ).toEqual([])
    })
  }
})
