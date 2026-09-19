/**
 * D 循环披露组件金额控件收敛守卫 —— spec Task 25（Property 28 / 29）。
 *
 * 🔴 **为什么必须换掉 `el-input-number`**（平台双证，2026-07-29）
 *
 * EP **2.13.6** 的 `element-plus/es/components/input-number/**` 全文**没有**
 * `formatter` / `parser` prop —— 该 prop 不存在；浏览器实测输 `1234567.5` 显示
 * `1234567.50`（**无千分符**），换 `el-input` 后才显示 `1,234,567.50`。
 *
 * 故凡「可编辑金额」一律走 `components/workpaper/shared/WpAmountInput.vue`。
 * 平台上仍有 40+ 处 `el-input-number :formatter` 是**空操作**（另有 spec 收口），
 * 本守卫只钉死 D 循环这 4 个披露组件。
 *
 * 🔴 **反向边界（Property 29）**：比例 / 占比 / 率 / 账龄天数 / 年度 / 笔数 /
 * 数量**不得**套 `WpAmountInput`（千分符与 2 位小数对它们是错的）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// ── REPO_ROOT：双哨兵**具体文件**向上查找，禁写死回退级数 ────────────────────
function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    const up = path.dirname(dir)
    if (up === dir) break
    dir = up
  }
  throw new Error('REPO_ROOT not found (双哨兵均未命中)')
}

const WP_DIR = path.join(
  findRepoRoot(),
  'audit-platform',
  'frontend',
  'src',
  'components',
  'workpaper',
)

/** 本 spec 收口的 4 个披露组件（改造前 el-input-number 计数） */
const TARGETS: Readonly<Record<string, number>> = Object.freeze({
  'd2/D2DisclosureNoteBody.vue': 43,
  'd5/D5TabDisclosure.vue': 14,
  'd7/D7TabDisclosure.vue': 4,
  'd6/D6TabDisclosure.vue': 2,
})

/** 非金额语义（反向边界） */
const NON_AMOUNT_HINTS = [
  '比例', '占比', '率', '账龄', '天数', '年度', '年份', '笔数', '数量', '个数', '期数',
] as const

function read(rel: string): string {
  const p = path.join(WP_DIR, rel)
  if (!fs.existsSync(p)) throw new Error(`组件不存在：${rel}（路径表已过期？）`)
  return fs.readFileSync(p, 'utf-8')
}

/** 取 `<template>` 段并剥 HTML 注释（注释里会写被禁的反例） */
function templateOf(src: string): string {
  const m = src.match(/<template>([\s\S]*)<\/template>/)
  return (m ? m[1] : '').replace(/<!--[\s\S]*?-->/g, '')
}

const AMOUNT_TAG_RE = /<WpAmountInput\b[\s\S]*?(?:\/>|<\/WpAmountInput>)/g

/** 取某标签前最近的列头 label（判反向边界用） */
function nearLabel(src: string, pos: number): string {
  const pre = src.slice(Math.max(0, pos - 900), pos)
    const labels = [...pre.matchAll(/label="([^"]{1,32})"/g)].map((m) => m[1])
  return labels.length ? labels[labels.length - 1] : ''
}

const cycles = Object.keys(TARGETS)

// ══════════════════════════════════════════════════════════════════════════════
// Property 28: el-input-number 归零 + WpAmountInput 已接
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 28: D 循环披露组件金额控件已收敛', () => {
  it.each(cycles)('%s 的 el-input-number 计数为 0', (rel) => {
    const tpl = templateOf(read(rel))
    const hits = tpl.match(/<el-input-number\b/g) || []
    expect(
      hits.length,
      `${rel} 仍有 ${hits.length} 处 el-input-number —— 它的 :formatter 在 EP 2.13.6 是空操作，千分符不会生效`,
    ).toBe(0)
  })

  it.each(cycles)('%s 已 import 平台单一真源 WpAmountInput', (rel) => {
    const src = read(rel)
    // 只认 import 路径 —— 符号级匹配会被注释骗（平台已登记）
    expect(src).toMatch(/from\s+'[^']*shared\/WpAmountInput\.vue'/)
  })

  it.each(cycles)('%s 模板里真的渲染了 WpAmountInput（带标签名边界）', (rel) => {
    const tpl = templateOf(read(rel))
    // 🔴 `toContain('<WpAmountInput')` 会被 `<WpAmountInputREMOVED` 骗过
    expect(tpl).toMatch(/<WpAmountInput(?=[\s/>])/)
  })

  it.each(cycles)('%s 的 WpAmountInput 数量 ≥ 改造前 el-input-number 数量', (rel) => {
    const tpl = templateOf(read(rel))
    const got = (tpl.match(/<WpAmountInput(?=[\s/>])/g) || []).length
    expect(
      got,
      `${rel} 只有 ${got} 处 WpAmountInput，少于改造前 ${TARGETS[rel]} 处 el-input-number —— 有金额格丢了控件`,
    ).toBeGreaterThanOrEqual(TARGETS[rel])
  })

  it.each(cycles)('%s 不得残留 el-input-number 专属的 :controls 属性', (rel) => {
    const tpl = templateOf(read(rel))
    // WpAmountInput 基于 el-input，本就无 controls；留着会落成无意义的 HTML 属性
    const stray = [...tpl.matchAll(AMOUNT_TAG_RE)].filter((m) => m[0].includes(':controls'))
    expect(stray.map((m) => m[0].slice(0, 80))).toEqual([])
  })

  it.each(cycles)('%s 每个 WpAmountInput 都绑了值与回写', (rel) => {
    const tpl = templateOf(read(rel))
    const bad: string[] = []
    for (const m of tpl.matchAll(AMOUNT_TAG_RE)) {
      const tag = m[0]
      const hasValue = /:model-value=|v-model/.test(tag)
      const hasWrite = /@change=|@update:model-value=|v-model/.test(tag)
      if (!hasValue || !hasWrite) bad.push(tag.replace(/\s+/g, ' ').slice(0, 110))
    }
    expect(bad, `${rel} 有 WpAmountInput 缺值绑定或回写`).toEqual([])
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 29: 反向边界 —— 非金额数值列不得套 WpAmountInput
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 29: 非金额列反向边界', () => {
  it.each(cycles)('%s 的 WpAmountInput 邻近列头都不是非金额语义', (rel) => {
    const tpl = templateOf(read(rel))
    const bad: string[] = []
    for (const m of tpl.matchAll(AMOUNT_TAG_RE)) {
      const near = nearLabel(tpl, m.index ?? 0)
      const hit = NON_AMOUNT_HINTS.find((k) => near.includes(k))
      if (hit) bad.push(`near_label=${JSON.stringify(near)} 命中「${hit}」`)
    }
    expect(bad, `${rel} 把非金额列套成金额控件（千分符与 2 位小数对它们是错的）`).toEqual([])
  })

  it('反向自检：命中非金额语义的列头确实会被判红', () => {
    const near = '坏账准备计提比例'
    expect(NON_AMOUNT_HINTS.some((k) => near.includes(k))).toBe(true)
    // 而真实金额列头不应命中
    for (const ok of ['账面余额', '坏账准备', '本期计提', '核销金额', '期末已质押金额']) {
      expect(NON_AMOUNT_HINTS.some((k) => ok.includes(k)), `${ok} 被误判成非金额`).toBe(false)
    }
  })

  it('反向自检：改名后的标签不通过存在性断言', () => {
    const mutated = '<template><WpAmountInputREMOVED :model-value="x" @change="f" /></template>'
    expect(templateOf(mutated)).not.toMatch(/<WpAmountInput(?=[\s/>])/)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 36: 只读金额走 displayPrefs 单一真源（AC 9.4）
//
// 🔴 本组守卫补的是 spec 交付时的一处判据缺口 —— Property 28/29 只钉「可编辑
// 金额用 WpAmountInput」，而 AC 9.4 要求的「只读金额经 `displayPrefs.fmtAmount`
// 且以 setup 顶层 inject 取得该 store」当时**一条断言都没有**。
//
// 三条平台铁律在此汇合（都属「四层验证全绿、只有浏览器暴露」那一类）：
//
//  1. `fmtAmount` 是 **store 成员**，`stores/displayPrefs` **不导出**它 ——
//     写 `import { fmtAmount } from '@/stores/displayPrefs'` 会让整页崩成
//     「页面渲染出错：does not provide an export named 'fmtAmount'」，
//     而 `get_diagnostics` 与 vitest 全绿（命名导出缺失是 ESM 运行时错误）。
//  2. `useDisplayPrefsStore` 是 **setup 作用域 composable**，写进函数体会
//     静默失效（拿不到 effect scope）。
//  3. 组件内自造 `toLocaleString` 闭包 = 硬编码 2 位小数 / 不带单位 /
//     不消费用户偏好，切「万元」时本页不跟随。
// ══════════════════════════════════════════════════════════════════════════════

/** 取 `<script setup>` 段 */
function scriptOf(src: string): string {
  const m = src.match(/<script[^>]*setup[^>]*>([\s\S]*?)<\/script>/)
  return m ? m[1] : ''
}

/**
 * 剥 JS 注释（块注释 + 整行 `//` 注释）。
 * 🔴 只剥「行首空白后紧跟 //」的整行注释 —— 不动行尾 `//`，避免误伤 URL
 * 与正则字面量（平台已登记的坑）。
 */
function stripJsComments(s: string): string {
  return s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^[ \t]*\/\/.*$/gm, '')
}

describe('Property 36: 只读金额经 displayPrefs（AC 9.4）', () => {
  it.each(cycles)('%s 不得自造 toLocaleString 金额闭包（剥注释后判定）', (rel) => {
    const code = stripJsComments(scriptOf(read(rel)))
    expect(
      code.includes('toLocaleString'),
      `${rel} 在代码里自造了 toLocaleString —— 金额格式单一真源是 displayPrefs.fmtAmount`,
    ).toBe(false)
  })

  it.each(cycles)('%s 不得从 stores/displayPrefs 具名 import fmtAmount', (rel) => {
    const code = stripJsComments(scriptOf(read(rel)))
    for (const m of code.matchAll(/import\s*\{([^}]*)\}\s*from\s*'[^']*stores\/displayPrefs'/g)) {
      expect(
        /\bfmtAmount\b/.test(m[1]),
        `${rel} 写了 import { fmtAmount } from '@/stores/displayPrefs' —— 该模块不导出 fmtAmount，运行时整页崩`,
      ).toBe(false)
    }
  })

  it.each(cycles)('%s 若用 fmtAmount 则必须经 setup 顶层 inject 的 displayPrefs', (rel) => {
    const src = read(rel)
    const code = stripJsComments(scriptOf(src))
    if (!code.includes('fmtAmount')) return // 该组件无只读金额格，跳过

    expect(code, `${rel} 用了 fmtAmount 但未 import DisplayPrefs_Key`).toMatch(
      /import\s*\{[^}]*\bDisplayPrefs_Key\b[^}]*\}\s*from\s*'[^']*displayPrefsKey'/,
    )
    // setup 顶层 = 行首无缩进（写进函数体会静默失效）
    expect(code, `${rel} 的 displayPrefs 未在 setup 顶层 inject`).toMatch(
      /^const displayPrefs\s*=\s*inject\(\s*DisplayPrefs_Key\s*,\s*null\s*\)\s*\?\?\s*useDisplayPrefsStore\(\)/m,
    )
    // 每一处 fmtAmount 调用都必须挂在 displayPrefs 上（或是本文件的薄壳定义）
    const bad: string[] = []
    for (const m of code.matchAll(/(\w+(?:\.\w+)*)\.fmtAmount\s*\(/g)) {
      if (m[1] !== 'displayPrefs') bad.push(m[0])
    }
    expect(bad, `${rel} 有 fmtAmount 调用不是走 displayPrefs`).toEqual([])
  })

  it.each(cycles)('%s 的 useDisplayPrefsStore 不得写在函数体内', (rel) => {
    const code = stripJsComments(scriptOf(read(rel)))
    const bad = [...code.matchAll(/^[ \t]+.*\buseDisplayPrefsStore\s*\(/gm)].map((m) =>
      m[0].trim().slice(0, 100),
    )
    expect(
      bad,
      `${rel} 把 useDisplayPrefsStore 写进了缩进作用域 —— setup 作用域 composable 在函数体内静默失效`,
    ).toEqual([])
  })

  it('反向自检：stripJsComments 确实剥掉了注释里的 toLocaleString', () => {
    // 真实文件的注释里就写着这个反例（说明「改造前是自造闭包」）——
    // 不剥注释则本组断言必然假红
    const withComment = read('d5/D5TabDisclosure.vue')
    expect(withComment.includes('toLocaleString'), '扫描面非空自检失败').toBe(true)
    expect(stripJsComments(scriptOf(withComment)).includes('toLocaleString')).toBe(false)
  })

  it('反向自检：三种错误写法都会被判红', () => {
    const selfMade = `<script setup lang="ts">
const x = (v: number) => v.toLocaleString('zh-CN')
</script>`
    expect(stripJsComments(scriptOf(selfMade)).includes('toLocaleString')).toBe(true)

    const badImport = `<script setup lang="ts">
import { fmtAmount } from '@/stores/displayPrefs'
</script>`
    const m = [
      ...stripJsComments(scriptOf(badImport)).matchAll(
        /import\s*\{([^}]*)\}\s*from\s*'[^']*stores\/displayPrefs'/g,
      ),
    ]
    expect(m.length).toBe(1)
    expect(/\bfmtAmount\b/.test(m[0][1])).toBe(true)

    const injectInBody = `<script setup lang="ts">
function f() {
  const displayPrefs = useDisplayPrefsStore()
  return displayPrefs.fmtAmount(1)
}
</script>`
    const code = stripJsComments(scriptOf(injectInBody))
    expect([...code.matchAll(/^[ \t]+.*\buseDisplayPrefsStore\s*\(/gm)].length).toBe(1)
    expect(code).not.toMatch(
      /^const displayPrefs\s*=\s*inject\(\s*DisplayPrefs_Key\s*,\s*null\s*\)/m,
    )
  })
})
