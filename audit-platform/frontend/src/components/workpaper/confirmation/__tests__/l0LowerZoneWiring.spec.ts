/**
 * l0LowerZoneWiring — L0 下区接入宿主的接线守卫（Property 17）
 *
 * spec: l0-confirmation-source-alignment，Task 19
 *
 * 🔴 为什么必须有这条守卫（memory 已记的缺陷模式「链条上游合格、整条链仍是死的」）：
 *    `L0SummaryLowerZone.vue` 自身测试全绿、`l0SummaryMatrix` / `l0SummaryLowerZone`
 *    声明件守卫全绿，但只要宿主没挂它，整条链对用户就是不可达的（`CrossWorkpaperNav.vue`
 *    是平台第一例：修复正确但全仓零渲染宿主）。
 *
 * 🔴 标签存在性断言必须带**标签名边界** —— `toContain('<L0SummaryLowerZone')` 会被
 *    `<L0SummaryLowerZoneREMOVED` 骗过，而「把渲染块改名 = 组件根本没渲染」正是最
 *    核心的变异。故一律用 `new RegExp('<Foo(?=[\\s/>])')`。
 *
 * 🔴 读源码型断言先 `stripComments()`，并配反向自检（断言原始源码确实含被禁字样）——
 *    否则守卫说明注释里引用的反例会被数成真实代码，或者剥注释失效让断言恒真。
 */

import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import { L0_LOWER_KEY_PREFIX, L0_LOWER_ZONE_FIELDS } from '../l0-confirmation/l0SummaryLowerZone'
import { L0_MATRIX_KEY_PREFIX } from '../l0-confirmation/l0MatrixDataSources'

// ─── REPO_ROOT（双哨兵具体文件向上查找；目录做哨兵会被历史空目录骗停） ──────────

const SENTINELS = [
  'backend/tests/test_l0_source_template_facts.py',
  'backend/wp_templates/L/L0 债务循环函证.xlsx',
]

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    if (SENTINELS.every((s) => fs.existsSync(path.join(dir, s)))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`REPO_ROOT 定位失败：从 ${__dirname} 未找到 ${SENTINELS.join(' + ')}`)
}

const REPO_ROOT = findRepoRoot()
const CONFIRM_DIR = path.join(
  REPO_ROOT,
  'audit-platform/frontend/src/components/workpaper/confirmation',
)
const HOST = path.join(CONFIRM_DIR, 'GtConfirmationSummary.vue')
const SAMPLING = path.join(CONFIRM_DIR, 'ConfirmationSampling.vue')
const LOWER_SFC = path.join(CONFIRM_DIR, 'l0-confirmation/L0SummaryLowerZone.vue')

/** 剥 HTML 注释 + JS 行/块注释（模板里的 `accept="image/*"` 不会被误当块注释起点：只在 script 区剥 JS 注释） */
function stripComments(src: string): string {
  // 1) HTML 注释（模板区与 script 区都可能有）
  let out = src.replace(/<!--[\s\S]*?-->/g, '')
  // 2) 只在 <script> 区剥 JS 注释（避免 URL 的 // 与 MIME 通配 /* 被误剥）
  out = out.replace(/<script\b[^>]*>([\s\S]*?)<\/script>/g, (_m, body: string) => {
    const cleaned = body
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .split('\n')
      .map((line) => {
        // 保守：只剥「行首起的 //」与「空白后的 //」，不动 URL 中的 ://
        const i = line.search(/(^|\s)\/\//)
        return i >= 0 ? line.slice(0, i) : line
      })
      .join('\n')
    return `<script>${cleaned}</script>`
  })
  return out
}

/** 带标签名边界的存在性判据 */
function hasTag(src: string, tag: string): boolean {
  return new RegExp(`<${tag}(?=[\\s/>])`).test(src)
}

const HOST_RAW = fs.readFileSync(HOST, 'utf-8')
const HOST_SRC = stripComments(HOST_RAW)
const SAMPLING_RAW = fs.readFileSync(SAMPLING, 'utf-8')
const SAMPLING_SRC = stripComments(SAMPLING_RAW)

// ─────────────────────────────────────────────────────────────────────────────

describe('l0LowerZoneWiring 自检：源文件与剥注释器有效', () => {
  it('三个源文件都存在（否则以下断言全部空转）', () => {
    for (const p of [HOST, SAMPLING, LOWER_SFC]) {
      expect(fs.existsSync(p), `文件不存在：${p}`).toBe(true)
    }
    expect(HOST_RAW.length).toBeGreaterThan(10000)
  })

  it('stripComments 确实剥掉了注释（反向自检）', () => {
    // 宿主里有大量 `spec: l0-confirmation-source-alignment` 的说明注释
    expect(HOST_RAW).toContain('spec: l0-confirmation-source-alignment')
    expect(HOST_SRC).not.toContain('spec: l0-confirmation-source-alignment')
  })

  it('剥注释未破坏模板中的 MIME 通配与 URL（同族坑对照）', () => {
    const fixture = `<template><input accept="image/*" /><a href="https://x/y" /></template>
<script setup>// c
const a = 1 /* b */
</script>`
    const out = stripComments(fixture)
    expect(out).toContain('accept="image/*"')
    expect(out).toContain('https://x/y')
    expect(out).toContain('const a = 1')
    expect(out).not.toContain('/* b */')
  })

  it('hasTag 判据带边界：改名即判否（这是本文件最核心的判据）', () => {
    expect(hasTag('<L0SummaryLowerZone v-if="isL0"', 'L0SummaryLowerZone')).toBe(true)
    expect(hasTag('<L0SummaryLowerZone/>', 'L0SummaryLowerZone')).toBe(true)
    // 🔴 弱判据 toContain 会被下面这个骗过 —— 带边界的正则不会
    expect('<L0SummaryLowerZoneREMOVED'.includes('<L0SummaryLowerZone')).toBe(true)
    expect(hasTag('<L0SummaryLowerZoneREMOVED v-if="isL0"', 'L0SummaryLowerZone')).toBe(false)
  })
})

describe('Property 17: 下区组件已挂进宿主且受 isL0 门控', () => {
  it('宿主 import 了 L0SummaryLowerZone（路径指向 l0-confirmation/）', () => {
    const m = HOST_SRC.match(
      /import\s+L0SummaryLowerZone\s+from\s+['"]\.\/l0-confirmation\/L0SummaryLowerZone\.vue['"]/,
    )
    expect(m, 'GtConfirmationSummary.vue 未 import L0SummaryLowerZone').not.toBeNull()
  })

  it('宿主模板真的渲染了该标签（带标签名边界）', () => {
    expect(
      hasTag(HOST_SRC, 'L0SummaryLowerZone'),
      'L0SummaryLowerZone 未在宿主模板中渲染 → 整条链对用户不可达',
    ).toBe(true)
  })

  it('渲染块紧跟 v-if="isL0" 门控（其余六枢纽不渲染）', () => {
    const i = HOST_SRC.search(/<L0SummaryLowerZone(?=[\s/>])/)
    expect(i).toBeGreaterThan(0)
    // 🔴 禁用「固定字符窗口」截标签 —— 该标签块约 430 字符，写死 400 会让
    //    `indexOf('>')` 返 -1 → 截出空串 → 断言在空文本上求值（表现为莫名打红）。
    //    同族坑：固定字符窗口截函数体。改按**真实标签边界**定位。
    const end = HOST_SRC.indexOf('>', i)
    expect(end, '未找到 L0SummaryLowerZone 的标签结束符（守卫会空转）').toBeGreaterThan(i)
    const openTag = HOST_SRC.slice(i, end + 1)
    expect(openTag, `渲染块缺 v-if="isL0" 门控：${openTag}`).toMatch(/v-if="isL0"/)
    // 反向自检：截出的确实是开标签（含属性），不是空串或别的片段
    expect(openTag.startsWith('<L0SummaryLowerZone')).toBe(true)
    expect(openTag.length).toBeGreaterThan(50)
  })

  it('isL0 定义为 confirmCycle === L0（不是别的枢纽、不是恒真）', () => {
    const m = HOST_SRC.match(/const\s+isL0\s*=\s*computed\(\(\)\s*=>\s*([^)]*\))/)
    expect(m, '未找到 isL0 computed 定义').not.toBeNull()
    const body = m![1]
    expect(body).toContain("confirmCycle.value === 'L0'")
    // 反向：不得写成 true / 别的枢纽
    expect(body).not.toMatch(/=>\s*true/)
    for (const other of ['D0', 'E0', 'F0', 'G0', 'H0', 'K0']) {
      expect(body, `isL0 误绑 ${other}`).not.toContain(`=== '${other}'`)
    }
  })

  it('confirmCycle 由 wpCode 首字母派生且 L0 在有效枢纽集合内', () => {
    const m = HOST_SRC.match(/const\s+confirmCycle\s*=\s*computed[\s\S]{0,600}?\n\}\)/)
    expect(m, '未找到 confirmCycle computed').not.toBeNull()
    const body = m![0]
    expect(body).toMatch(/props\.wpCode/)
    expect(body).toContain("'L0'")
    // 缺省不得是 L0（否则未知 wpCode 会误渲染 L0 下区）
    expect(body).toMatch(/:\s*'D0'/)
  })

  it('六个非 L0 枢纽各自有独立门控常量，互不复用（门控不串枢纽）', () => {
    const defs = Array.from(
      HOST_SRC.matchAll(/const\s+(is[DEFGHKL]0)\s*=\s*computed\(\(\)\s*=>\s*confirmCycle\.value\s*===\s*'([DEFGHKL]0)'/g),
    ).map((x) => [x[1], x[2]] as const)
    // 每个门控常量名与其比较的枢纽值必须一致（isL0 不能比 'K0'）
    for (const [name, cycle] of defs) {
      expect(name, `${name} 与 ${cycle} 不一致`).toBe(`is${cycle}`)
    }
    expect(defs.map((d) => d[1])).toContain('L0')
  })
})

describe('Property 17: 样本选择单一录入口（避免双真源）', () => {
  it('共享 ConfirmationSampling 对 L0 不渲染（v-if="!isL0"）', () => {
    const i = SAMPLING_TAG_INDEX()
    expect(i, '宿主未渲染 ConfirmationSampling').toBeGreaterThan(0)
    // 向上找最近的 el-collapse-item 开标签，断言其带 !isL0 门控
    const before = HOST_SRC.slice(0, i)
    const openIdx = before.lastIndexOf('<el-collapse-item')
    expect(openIdx).toBeGreaterThan(0)
    const openTag = HOST_SRC.slice(openIdx, HOST_SRC.indexOf('>', openIdx) + 1)
    expect(openTag, `样本选择区缺 !isL0 门控：${openTag}`).toMatch(/v-if="!isL0"/)
    expect(openTag).toMatch(/name="sampling"/)
  })

  function SAMPLING_TAG_INDEX(): number {
    return HOST_SRC.search(/<ConfirmationSampling(?=[\s/>])/)
  }

  it('ConfirmationSampling 组件自身无 isL0 分支（L0 的 6 项在下区组件内）', () => {
    // 🔴 这是 Task 16 的实际裁决（推翻 design 原写法）：
    //    L0 的「二、样本选择」6 项属 L0-1 下区（落 checklist_responses 的
    //    `L0-1-lower-sample-*`），若共享组件也开 isL0 分支 → 同一语义两个录入口
    //    （一个落 SamplingConfig、一个落 checklist）= 双真源。
    expect(SAMPLING_SRC).not.toMatch(/\bisL0\b/)
  })

  it('ConfirmationSampling 的 isG0 分支保持不变（其余枢纽零回归）', () => {
    expect(SAMPLING_SRC).toMatch(/const\s+isG0\s*=\s*computed\(\(\)\s*=>\s*props\.cycle\s*===\s*'G0'\)/)
    expect(hasTag(SAMPLING_SRC, 'el-form')).toBe(true)
  })

  it('L0 的 6 项样本选择确实在下区声明件里（单一真源落点）', () => {
    const sampleFields = L0_LOWER_ZONE_FIELDS.filter((f) => f.includes('sample'))
    expect(sampleFields).toHaveLength(6)
    for (const f of sampleFields) {
      expect(f.startsWith(L0_LOWER_KEY_PREFIX)).toBe(true)
    }
  })
})

describe('Property 16 接缝: 下区键空间与上区/矩阵不冲突', () => {
  it('下区键前缀与矩阵键前缀不互为前缀', () => {
    expect(L0_LOWER_KEY_PREFIX.startsWith(L0_MATRIX_KEY_PREFIX)).toBe(false)
    expect(L0_MATRIX_KEY_PREFIX.startsWith(L0_LOWER_KEY_PREFIX)).toBe(false)
  })

  it('宿主的下区保存走 checklist-responses，不走 sheet 级 emit(save, 载荷)', () => {
    // 🔴 平台铁律：下区/itemId 维度录入若 emit sheet 级 save，宿主会把载荷整体写成
    //    该 sheet 的 html_data → 一次点击丢光上区函证行并让 sheet 退化成「旧格式只读」。
    const m = HOST_SRC.match(/function\s+handleL0LowerSave[\s\S]{0,1200}/)
    expect(m, '未找到 handleL0LowerSave').not.toBeNull()
    const body = m![0]
    expect(body).toMatch(/checklist-responses/)
  })

  it('下区组件自身只 emit save(itemId, value)，不构造 sheet 载荷', () => {
    const sfc = stripComments(fs.readFileSync(LOWER_SFC, 'utf-8'))
    expect(sfc).toMatch(/defineEmits/)
    // 不得出现把整个 sheet 写回的形态
    expect(sfc).not.toMatch(/_format\s*:/)
    expect(sfc).not.toMatch(/html_data\s*\[/)
  })
})
