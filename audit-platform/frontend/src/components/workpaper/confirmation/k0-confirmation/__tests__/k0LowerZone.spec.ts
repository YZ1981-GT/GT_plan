/**
 * k0LowerZone.spec.ts — K0-1 下区组件的金额铁律守卫（Wave 4 / Task 15）
 *
 * spec: k0-confirmation-source-alignment
 *   Property 22（金额显示走平台单一真源）/ Property 23（可编辑金额控件选型正确）
 *   Requirement 3.1 / 3.5
 *
 * 为什么单开一个文件：`k0LowerZoneSpec.spec.ts` 守的是**声明真源**
 * （`k0LowerZoneSpec.ts` 的四块文字/键名/笔误映射），本文件守的是**组件实现形态**
 * （`K0SummaryLowerZone.vue` 里金额怎么读、怎么录）。两者判据域不同，混在一个文件里
 * 会让「改声明」与「改渲染」的红信号混淆。
 *
 * 🔴 三条平台铁律在本组件的落法（判据形态就是从这三条反推出来的）：
 *
 * 1. **`fmtAmount` 是 store 成员、不是模块级命名导出** —— 写
 *    `import { fmtAmount } from '@/stores/displayPrefs'` 会让整页崩成
 *    「does not provide an export named 'fmtAmount'」，而 `get_diagnostics`(Volar) /
 *    vitest / Vite transform 200 **四层全绿**（命名导出缺失是 ESM 运行时错误，
 *    Vite 只做单文件编译、不解析跨模块导出集合）。
 * 2. **`useDisplayPrefsStore()` 必须在 setup 顶层** —— 它是 setup 作用域 composable，
 *    写进函数体会静默失效（拿不到 effect scope）。判据 = 行首无缩进。
 * 3. **可编辑金额只能用 `WpAmountInput`** —— EP 2.13.6 的 `el-input-number` 源码里
 *    压根没有 `formatter` prop（`node_modules/element-plus/es/components/input-number/**`
 *    全文无该 prop），平台现存 40+ 处 `el-input-number :formatter` 全是空操作、
 *    千分符从未生效。
 *
 * 判据边界（有意不重复的部分）：
 * - `DisplayPrefs_Key` **引入来源**的不变式已有平台级守卫
 *   `components/workpaper/__tests__/displayPrefsKeyImportSource.spec.ts` 全量扫 `.vue`，
 *   本文件只做一条「该平台守卫仍在」的交叉锁死（防它被删掉后本处判据变成孤岛），
 *   不再抄一份扫描逻辑（同一不变式两份判据 = 改一处另一处不红）。
 * - 比例行是只读派生（`cellText` 输出百分比），不参与金额控件选型 —— 反向边界断言
 *   在 Property 23 里显式钉住，防「顺手把比例也套上 WpAmountInput」。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const SENTINEL = 'backend/wp_templates/K/K0 管理循环函证.xlsx'

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(resolve(dir, SENTINEL))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未找到仓库根（哨兵 ${SENTINEL} 不存在于 ${__dirname} 的任一祖先）`)
}

const REPO_ROOT = findRepoRoot()
const COMPONENT = resolve(__dirname, '../K0SummaryLowerZone.vue')
const PLATFORM_GUARD = resolve(
  REPO_ROOT,
  'audit-platform/frontend/src/components/workpaper/__tests__/displayPrefsKeyImportSource.spec.ts',
)

const rawSrc = readFileSync(COMPONENT, 'utf-8').replace(/\r\n/g, '\n')

/**
 * 带字符串状态的注释剥离器。
 *
 * 🔴 不能用裸正则 —— 模板里的 `accept="image/*"` 会被当块注释起点，一路吞掉几千字符
 * （平台已实测踩过：两个真实宿主因此静默逃出扫描面而守卫仍然是绿的）；
 * `https://` 的双斜杠同理会被当行注释。
 */
function stripComments(input: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < input.length) {
    const ch = input[i]
    const next = input[i + 1]
    if (quote) {
      out += ch
      if (ch === '\\') {
        out += next ?? ''
        i += 2
        continue
      }
      if (ch === quote) quote = null
      i += 1
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch
      out += ch
      i += 1
      continue
    }
    if (ch === '<' && input.startsWith('<!--', i)) {
      const end = input.indexOf('-->', i + 4)
      i = end === -1 ? input.length : end + 3
      continue
    }
    if (ch === '/' && next === '*') {
      const end = input.indexOf('*/', i + 2)
      i = end === -1 ? input.length : end + 2
      continue
    }
    if (ch === '/' && next === '/') {
      const end = input.indexOf('\n', i)
      i = end === -1 ? input.length : end
      continue
    }
    out += ch
    i += 1
  }
  return out
}

const cleanSrc = stripComments(rawSrc)

/** 取 `<script setup ...>` 到 `</script>` 之间的代码（已剥注释） */
function scriptOf(src: string): string {
  const m = /<script[^>]*>([\s\S]*?)<\/script>/.exec(src)
  expect(m, '未取到 <script> 区').not.toBeNull()
  return (m as RegExpExecArray)[1]
}

/** 取 `<template>` 到 `</template>` 之间的标记（已剥注释） */
function templateOf(src: string): string {
  const m = /<template>([\s\S]*)<\/template>/.exec(src)
  expect(m, '未取到 <template> 区').not.toBeNull()
  return (m as RegExpExecArray)[1]
}

const script = scriptOf(cleanSrc)
const template = templateOf(cleanSrc)

function countOf(src: string, pattern: RegExp): number {
  return [...src.matchAll(pattern)].length
}

// ─── helper 自检（防剥注释/取区失效导致后面断言全部空转） ──────────────────────

describe('k0LowerZone · helper 自检', () => {
  it('剥注释确实生效：原文里的反例字样在剥后消失', () => {
    // 组件文档注释里如实写了「不得用 el-input-number :formatter」，
    // 若剥注释失效，Property 23 会把这句说明数成真实控件。
    expect(countOf(rawSrc, /el-input-number/g)).toBeGreaterThan(0)
    expect(countOf(cleanSrc, /el-input-number/g)).toBe(0)
  })

  it('剥注释不误伤字符串字面量（MIME 通配 / 协议双斜杠不当注释）', () => {
    const fixture = `<template><input accept="image/*" /></template>
<script setup lang="ts">
// 行注释里的 el-input-number 应被剥掉
const url = 'https://example.com/a'
const keep = 'el-input' + '-number-in-string'
/* 块注释 */
</script>`
    const cleaned = stripComments(fixture)
    expect(cleaned).toContain('accept="image/*"')
    expect(cleaned).toContain("'https://example.com/a'")
    expect(cleaned).not.toContain('行注释里的')
    expect(cleaned).not.toContain('块注释')
  })

  it('script / template 两区都取到了非空内容', () => {
    expect(script.length).toBeGreaterThan(500)
    expect(template.length).toBeGreaterThan(500)
    expect(script).toContain('defineProps')
    expect(template).toContain('el-table')
  })
})

// ─── Property 22 · 金额显示走平台单一真源 ─────────────────────────────────────

describe('Property 22 · 金额显示走 displayPrefs.fmtAmount 单一真源', () => {
  it('setup 顶层 inject（行首无缩进；写进函数体会静默失效）', () => {
    expect(script).toMatch(
      /^const displayPrefs\s*=\s*inject\(\s*DisplayPrefs_Key\s*,\s*null\s*\)\s*\?\?\s*useDisplayPrefsStore\(\)/m,
    )
  })

  it('🔴 `useDisplayPrefsStore()` 只在那一处调用，且不在任何缩进行（函数体内）', () => {
    expect(countOf(script, /\buseDisplayPrefsStore\s*\(/g)).toBe(1)
    // 缩进行里出现调用 = 写进了函数体
    expect(countOf(script, /^[ \t]+.*\buseDisplayPrefsStore\s*\(/gm)).toBe(0)
  })

  it('🔴 禁把 fmtAmount 当模块级命名导出引入（那会让整页崩，四层验证全绿）', () => {
    expect(script).not.toMatch(
      /import\s*\{[^}]*\bfmtAmount\b[^}]*\}\s*from\s*['"]@\/stores\/displayPrefs['"]/,
    )
    // store 侧只许引入 useDisplayPrefsStore
    const storeImport = /import\s*\{([^}]*)\}\s*from\s*['"]@\/stores\/displayPrefs['"]/.exec(script)
    expect(storeImport, '未找到 store 的 import 语句').not.toBeNull()
    const named = (storeImport as RegExpExecArray)[1]
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    expect(named).toEqual(['useDisplayPrefsStore'])
  })

  it('`DisplayPrefs_Key` 取自真源模块 composables/displayPrefsKey（不是 store）', () => {
    expect(script).toMatch(
      /import\s*\{[^}]*\bDisplayPrefs_Key\b[^}]*\}\s*from\s*'[^']*composables\/displayPrefsKey'/,
    )
  })

  it('每一处 fmtAmount 调用都挂在 displayPrefs 上（无第二条格式化路径）', () => {
    const total = countOf(script, /\bfmtAmount\s*\(/g)
    const viaPrefs = countOf(script, /\bdisplayPrefs\.fmtAmount\s*\(/g)
    expect(total).toBeGreaterThan(0)
    expect(viaPrefs).toBe(total)
  })

  it('🔴 不得自造格式化（toLocaleString / Intl.NumberFormat / 手写千分符正则）', () => {
    expect(script).not.toMatch(/\btoLocaleString\s*\(/)
    expect(script).not.toMatch(/\bIntl\s*\.\s*NumberFormat\b/)
    // 手写千分符的典型形态
    expect(script).not.toMatch(/\\B\(\?=\(\\d\{3\}\)\+/)
  })

  it('模板不直接插值原始金额（一律经 cellText / bookDisplayOf 等格式化出口）', () => {
    // 允许的插值出口：这些函数体内已断言走 displayPrefs.fmtAmount
    expect(template).toMatch(/\{\{\s*cellText\(/)
    expect(template).toMatch(/\{\{\s*bookDisplayOf\(/)
    // 禁止把矩阵单元格的裸 value 直接插进模板
    expect(template).not.toMatch(/\{\{\s*[\w.]*cell\.value\s*\}\}/)
  })

  it('平台级 import 来源守卫仍在（本文件不重复其判据，但它不得被删）', () => {
    expect(existsSync(PLATFORM_GUARD), 'displayPrefsKeyImportSource.spec.ts 缺失').toBe(true)
    const guard = readFileSync(PLATFORM_GUARD, 'utf-8')
    expect(guard).toMatch(/DisplayPrefs_Key/)
    expect(guard).toMatch(/displayPrefsKey/)
  })

  it('反向自检：三种坏形态都能被上面的判据抓到', () => {
    const badIndentedInject = `
function useIt() {
  const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
  return displayPrefs
}`
    expect(badIndentedInject).not.toMatch(
      /^const displayPrefs\s*=\s*inject\(\s*DisplayPrefs_Key\s*,\s*null\s*\)/m,
    )
    expect(countOf(badIndentedInject, /^[ \t]+.*\buseDisplayPrefsStore\s*\(/gm)).toBe(1)

    const badNamedImport = "import { fmtAmount } from '@/stores/displayPrefs'"
    expect(badNamedImport).toMatch(
      /import\s*\{[^}]*\bfmtAmount\b[^}]*\}\s*from\s*['"]@\/stores\/displayPrefs['"]/,
    )

    const badLocale = 'return Number(v).toLocaleString("zh-CN")'
    expect(badLocale).toMatch(/\btoLocaleString\s*\(/)
  })
})

// ─── Property 23 · 可编辑金额控件选型正确 ─────────────────────────────────────

describe('Property 23 · 可编辑金额控件选型正确', () => {
  it('🔴 全文（剥注释后）`el-input-number` 计数为 0', () => {
    expect(countOf(cleanSrc, /el-input-number/g)).toBe(0)
    expect(countOf(cleanSrc, /ElInputNumber/g)).toBe(0)
  })

  it('🔴 不出现 `:formatter` / `:parser`（EP 2.13.6 的 input-number 无此 prop，是空操作）', () => {
    expect(countOf(cleanSrc, /:formatter\b/g)).toBe(0)
    expect(countOf(cleanSrc, /:parser\b/g)).toBe(0)
  })

  it('账面金额行的可编辑控件是 WpAmountInput，且已从共享目录引入', () => {
    expect(script).toMatch(
      /import\s+WpAmountInput\s+from\s+'[^']*shared\/WpAmountInput\.vue'/,
    )
    expect(countOf(template, /<WpAmountInput/g)).toBeGreaterThan(0)
  })

  it('WpAmountInput 走受控形态（`:model-value` + `@update:model-value`）', () => {
    const at = template.indexOf('<WpAmountInput')
    expect(at).toBeGreaterThan(-1)
    const close = template.indexOf('/>', at)
    expect(close).toBeGreaterThan(at)
    const tag = template.slice(at, close)
    expect(tag).toMatch(/:model-value=/)
    expect(tag).toMatch(/@update:model-value=/)
  })

  it('只有账面金额行可编辑（金额控件受 `metric === \'book_amount\'` 与 readonly 双门控）', () => {
    const at = template.indexOf('<WpAmountInput')
    const close = template.indexOf('/>', at)
    const tag = template.slice(at, close)
    expect(tag).toMatch(/v-if="[^"]*book_amount[^"]*"/)
    expect(tag).toMatch(/v-if="[^"]*!readonly[^"]*"/)
  })

  it('反向边界：比例行不得套金额控件（比例走 cellText 的百分比分支）', () => {
    // 组件里比例是只读派生：cellText 对 kind==='ratio' 输出百分比
    expect(script).toMatch(/kind\s*===\s*'ratio'/)
    expect(script).toMatch(/toFixed\(2\)\}%/)
    // WpAmountInput 只出现在 book_amount 分支里 ⇒ 模板中金额控件数量不超过 1 处声明
    expect(countOf(template, /<WpAmountInput/g)).toBe(1)
  })

  it('反向自检：把控件换成 el-input-number :formatter 的替身必须被抓到', () => {
    const bad = `<template>
  <el-input-number :model-value="v" :formatter="fmt" />
</template>`
    const cleaned = stripComments(bad)
    expect(countOf(cleaned, /el-input-number/g)).toBe(1)
    expect(countOf(cleaned, /:formatter\b/g)).toBe(1)
  })

  it('反向自检：非金额语义控件不得被本判据误伤（利率/笔数用 el-input-number 是合法的）', () => {
    // 该边界写成断言是为了防下个会话把「el-input-number 计数为 0」推广成平台级禁令。
    const legit = '<el-input-number :model-value="rate" :precision="4" />'
    expect(legit).toMatch(/el-input-number/)
    // 本判据的作用域只有 K0SummaryLowerZone.vue —— 它没有利率/笔数列
    expect(countOf(cleanSrc, /precision/g)).toBe(0)
  })
})
