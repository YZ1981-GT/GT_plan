/**
 * D 循环审定表「TB 核对数 seed 回退」与「四表溯源面板挂载」守卫。
 *
 * spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/ Task 16
 *       Requirements 4.1, 4.3, 4.4, 4.5, 4.6 / Property 13, 14
 *
 * 🔴 本守卫覆盖的三类「四层验证全绿但用户不可达」缺陷：
 *
 * 1. **dead output** —— render 下发 `project_context.tb_amount`（`seed_tb_amount_scalars`
 *    按报表行解析后的叶子口径）而前端零消费 ⇒ 未手工录入时 TB 核对行恒 0、
 *    差异行显示整额假差异。D2/D3/D5/D6 改造前全中招。
 * 2. **孤儿组件** —— `WpFourTableSourcePanel` 写好却无渲染宿主（改造前只有 D4 挂了）。
 * 3. **手工优先被破坏** —— seed 覆盖了审计师已录入的值。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  resolveTbAmountWithSeed,
  hasManualTbAmount,
  isTbSeedFallbackActive,
} from '../dCycleTbSeed'
import { pickDTbSourceCodes, normalizeDSlots } from '../dCycleAccountScope'
import { pickDTbSourceCodes, normalizeDSlots } from '../dCycleAccountScope'

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

const REPO_ROOT = findRepoRoot()
const WP_DIR = path.join(
  REPO_ROOT,
  'audit-platform',
  'frontend',
  'src',
  'components',
  'workpaper',
)

/** D1~D7 审定表组件相对 `workpaper/` 的路径（D4 在 core/ 子目录下） */
const ADJ_COMPONENTS: Readonly<Record<string, string>> = Object.freeze({
  D1: 'd1/D1TabAdjudication.vue',
  D2: 'd2/D2TabAdjudication.vue',
  D3: 'd3/D3TabAdjudication.vue',
  D4: 'd4/core/D4TabAdjudication.vue',
  D5: 'd5/D5TabAdjudication.vue',
  D6: 'd6/D6TabAdjudication.vue',
  D7: 'd7/D7TabAdjudication.vue',
})

/** 走 `dCycleTbSeed` 回退的循环（D1/D7 早有自己的 `tbSeedAmount`，D4 有独立 TB 行结构） */
const SEED_FALLBACK_CYCLES = Object.freeze(['D2', 'D3', 'D5', 'D6'] as const)

const COMPOSABLES = path.join(WP_DIR, 'composables')

function readComponent(cycle: string): string {
  const rel = ADJ_COMPONENTS[cycle]
  const p = path.join(WP_DIR, rel)
  if (!fs.existsSync(p)) throw new Error(`组件不存在：${rel}（路径表已过期？）`)
  return fs.readFileSync(p, 'utf-8')
}

function readComposable(cycle: string): string {
  const p = path.join(COMPOSABLES, `use${cycle}Adjudication.ts`)
  if (!fs.existsSync(p)) throw new Error(`composable 不存在：use${cycle}Adjudication.ts`)
  return fs.readFileSync(p, 'utf-8')
}

/** 剥注释（守卫说明里会如实写出被禁的反例，不剥会把说明文字数成真实代码） */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 取 `<template>` 段（模板里的 HTML 注释另行剥离） */
function templateOf(src: string): string {
  const m = src.match(/<template>([\s\S]*)<\/template>/)
  return (m ? m[1] : '').replace(/<!--[\s\S]*?-->/g, '')
}

// ══════════════════════════════════════════════════════════════════════════════
// Property 13: 三态纯函数语义（手工优先 / null≠0 / 未取数≠0）
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 13: resolveTbAmountWithSeed 三态语义', () => {
  it('手工值存在时一律优先，即使 seed 有值', () => {
    expect(resolveTbAmountWithSeed('1000', 999)).toBe(1000)
    expect(resolveTbAmountWithSeed(1000, 999)).toBe(1000)
  })

  it('手工值为 0 也算已录入（不得被 seed 顶掉）', () => {
    // 🔴 「审计师确认为 0」与「未录入」是两种状态 —— 前者不能被 seed 覆盖
    expect(resolveTbAmountWithSeed('0', 888)).toBe(0)
    expect(resolveTbAmountWithSeed(0, 888)).toBe(0)
  })

  it('无手工值时回退 seed', () => {
    expect(resolveTbAmountWithSeed(undefined, 777)).toBe(777)
    expect(resolveTbAmountWithSeed(null, 777)).toBe(777)
    expect(resolveTbAmountWithSeed('', 777)).toBe(777)
    expect(resolveTbAmountWithSeed('   ', 777)).toBe(777)
  })

  it('两侧都无值时返回 0（表格数值列不能是 null）', () => {
    expect(resolveTbAmountWithSeed(undefined, undefined)).toBe(0)
    expect(resolveTbAmountWithSeed(null, null)).toBe(0)
  })

  it('seed 为 null / 非有限数时不当 0 用，回退才是 0', () => {
    expect(resolveTbAmountWithSeed(undefined, null)).toBe(0)
    expect(resolveTbAmountWithSeed(undefined, Number.NaN)).toBe(0)
    expect(resolveTbAmountWithSeed(undefined, Number.POSITIVE_INFINITY)).toBe(0)
  })

  it('手工值非法（非数值文本）时视为未录入，回退 seed', () => {
    expect(resolveTbAmountWithSeed('abc', 555)).toBe(555)
    expect(resolveTbAmountWithSeed('--', 555)).toBe(555)
  })

  it('带千分符 / 括号负数的手工值可解析', () => {
    expect(resolveTbAmountWithSeed('1,234,567.50', 0)).toBeCloseTo(1234567.5, 2)
    expect(resolveTbAmountWithSeed('(1,000)', 0)).toBeCloseTo(-1000, 2)
  })

  it('hasManualTbAmount 与 isTbSeedFallbackActive 互补且不重叠', () => {
    // 已录入 → 非回退态
    expect(hasManualTbAmount('1')).toBe(true)
    expect(isTbSeedFallbackActive('1', 2)).toBe(false)
    // 未录入 + seed 有值 → 回退态（供 UI 出「取自四表库」提示）
    expect(hasManualTbAmount('')).toBe(false)
    expect(isTbSeedFallbackActive('', 2)).toBe(true)
    // 未录入 + seed 未下发 → 不是回退态（没什么可回退）
    expect(isTbSeedFallbackActive('', undefined)).toBe(false)
    expect(isTbSeedFallbackActive('', null)).toBe(false)
    // 🔴 未录入 + seed 为 **0** → 仍是回退态。
    // `0` 是「四表确实取到 0」这一实证值（平台铁律：金额为 0 也算有内容），
    // 与「未下发 / 本项目无此科目」（`null`）语义不同 —— 展示值来自 seed，
    // 故 UI 应照样标注「取自四表库」。若这里写成 false，审计师会以为这个 0
    // 是自己填的或系统没取到，而它其实是有效的取数结论。
    expect(isTbSeedFallbackActive('', 0)).toBe(true)
  })

  it('seed 为 null 时返回 0，而 0 与 null 在语义上不可互换', () => {
    // 「本项目无此科目」（seed=null）与「余额确实为 0」（seed=0）在 UI 上由溯源面板
    // 三态 tag 区分；此函数只保证数值列不出 NaN。
    expect(resolveTbAmountWithSeed('', null)).toBe(0)
    expect(resolveTbAmountWithSeed('', 0)).toBe(0)
    // 🔴 但 isTbSeedFallbackActive 必须能区分二者 —— 否则「无此科目」会被标成「已自动取数」
    expect(isTbSeedFallbackActive('', null)).toBe(false)
    expect(isTbSeedFallbackActive('', 0)).toBe(true)
  })

  it('反向自检：朴素实现（Number(remark) || seed）会把手工 0 判成未录入', () => {
    const naive = (remark: unknown, seed?: number | null) =>
      Number(remark) || Number(seed ?? 0)
    // 朴素实现把「审计师确认为 0」顶成 seed 值 = 正是本函数要防的缺陷
    expect(naive('0', 888)).toBe(888)
    expect(resolveTbAmountWithSeed('0', 888)).toBe(0)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 14: 四个 composable 真实消费 seed（消 dead output）
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 14: D2/D3/D5/D6 composable 已接 TB seed 回退', () => {
  it.each(SEED_FALLBACK_CYCLES)('%s 声明 tbSeedAmount 入参', (cycle) => {
    const src = stripComments(readComposable(cycle))
    expect(src).toMatch(/tbSeedAmount\?:\s*Ref</)
  })

  it.each(SEED_FALLBACK_CYCLES)('%s 从单一真源 import 回退纯函数', (cycle) => {
    const src = stripComments(readComposable(cycle))
    // 只认 import 路径 —— 符号级匹配会被注释/同名导出骗（平台已登记）
    expect(src).toMatch(/from\s+'\.\/dCycleTbSeed'/)
  })

  it.each(SEED_FALLBACK_CYCLES)('%s 的 TB 数走 resolveTbAmountWithSeed 且传了 seed', (cycle) => {
    const src = stripComments(readComposable(cycle))
    expect(src).toMatch(/resolveTbAmountWithSeed\s*\(/)
    // 🔴 必须真的把 seed 传进去 —— 只调函数不传 seed 等于没接
    expect(src).toMatch(/options\.tbSeedAmount\?\.value/)
  })

  it.each(SEED_FALLBACK_CYCLES)('%s 不得保留「只读 checklist」的旧写法', (cycle) => {
    const src = stripComments(readComposable(cycle))
    // 旧形态：ref(0) + watch 单向赋值。改造后应是 computed 派生
    expect(src).not.toMatch(
      /trialBalanceAmount(?:\s*:\s*Ref<number>)?\s*=\s*ref\s*(?:<number>)?\s*\(\s*0\s*\)/,
    )
  })

  it('反向自检：旧形态源码片段确实会被上一条断言打红', () => {
    const legacy = `
      const trialBalanceAmount: Ref<number> = ref(0)
      watch(() => allResponses.value.get('D3-adj-trial-balance-amount')?.remark,
        (val) => { trialBalanceAmount.value = parseNum(val) }, { immediate: true })
    `
    expect(stripComments(legacy)).toMatch(
      /trialBalanceAmount(?:\s*:\s*Ref<number>)?\s*=\s*ref\s*(?:<number>)?\s*\(\s*0\s*\)/,
    )
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 14（续）: 7 个审定表组件挂溯源面板（消孤儿组件）
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 14: 7 个 D 审定表已挂 WpFourTableSourcePanel', () => {
  const cycles = Object.keys(ADJ_COMPONENTS)

  it.each(cycles)('%s 组件 import 了面板组件', (cycle) => {
    const src = stripComments(readComponent(cycle))
    expect(src).toMatch(/from\s+'[^']*WpFourTableSourcePanel\.vue'/)
  })

  it.each(cycles)('%s 模板里真的渲染了面板标签', (cycle) => {
    const tpl = templateOf(readComponent(cycle))
    // 🔴 带标签名边界 —— `toContain('<WpFourTableSourcePanel')` 会被
    //    `<WpFourTableSourcePanelREMOVED` 骗过（平台已登记该守卫缺陷）
    expect(tpl).toMatch(/<WpFourTableSourcePanel(?=[\s/>])/)
  })

  it.each(cycles)('%s 给面板传了必填的 source-codes', (cycle) => {
    const tpl = templateOf(readComponent(cycle))
    const m = tpl.match(/<WpFourTableSourcePanel[\s\S]*?\/>/)
    expect(m, `${cycle} 未找到面板标签`).toBeTruthy()
    // 缺 :source-codes ⇒ 面板内部 visible 恒 false ⇒ 等于没挂
    expect(m![0]).toMatch(/:source-codes=/)
    expect(m![0]).toMatch(/gross-label=/)
  })

  it.each(cycles)('%s 给面板传的属性名都在其 defineProps 里', (cycle) => {
    const panelPath = path.join(WP_DIR, 'shared', 'WpFourTableSourcePanel.vue')
    const panelSrc = fs.readFileSync(panelPath, 'utf-8')
    // 从被调组件动态抽合法 prop 名（转 kebab-case）
    const propsBlock = panelSrc.match(/defineProps<\{([\s\S]*?)\}>\(/)
    expect(propsBlock, 'WpFourTableSourcePanel 的 defineProps 未解析到').toBeTruthy()
    const legal = new Set<string>()
    for (const line of propsBlock![1].split('\n')) {
      const pm = line.match(/^\s*([A-Za-z][A-Za-z0-9]*)\??\s*:/)
      if (pm) {
        legal.add(pm[1])
        legal.add(pm[1].replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`))
      }
    }
    expect(legal.size, '合法 prop 集合为空 = 解析失效').toBeGreaterThan(3)

    const tpl = templateOf(readComponent(cycle))
    const tag = tpl.match(/<WpFourTableSourcePanel[\s\S]*?\/>/)![0]
    const attrs = [...tag.matchAll(/(?:^|\s):?([a-z][a-z0-9-]*)\s*=/g)].map((x) => x[1])
    const IGNORED = new Set(['key', 'ref', 'class', 'style'])
    const unknown = attrs.filter((a) => !IGNORED.has(a) && !legal.has(a))
    expect(unknown, `${cycle} 传了面板不存在的属性（会静默失效）`).toEqual([])
  })

  it.each(cycles)('%s 经单一真源 pickDTbSourceCodes 取载荷（两层落点都读）', (cycle) => {
    const src = stripComments(readComponent(cycle))
    expect(src).toMatch(/pickDTbSourceCodes/)
    // 🔴 禁止组件内自己写 `htmlData?.project_context?.tb_source_codes` 单层读法：
    //    D1/D2/D3/D5/D6/D7 写 html_data 顶层、只有 D4 写 project_context，
    //    单读一层必让其中一侧恒 undefined。
    const inlineSingleLayer =
      /htmlData\?\.\s*project_context\?\.\s*tb_source_codes/.test(src) &&
      !/pickDTbSourceCodes/.test(src)
    expect(inlineSingleLayer).toBe(false)
  })

  it('反向自检：改名后的标签不应通过存在性断言', () => {
    const mutated = '<template><WpFourTableSourcePanelREMOVED :source-codes="x" /></template>'
    expect(templateOf(mutated)).not.toMatch(/<WpFourTableSourcePanel(?=[\s/>])/)
  })

  it('反向自检：缺 :source-codes 的标签应被打红', () => {
    const tag = '<WpFourTableSourcePanel gross-label="x" />'
    expect(tag).not.toMatch(/:source-codes=/)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 15: pickDTbSourceCodes 行为级 —— 两套落点都必须读到
// ══════════════════════════════════════════════════════════════════════════════
//
// 🔴 这一组是**行为级**断言，与上面的源码级断言互补。
//
// 源码级只能查「组件有没有调用 pickDTbSourceCodes」，查不出该函数**自己**是不是
// 只读了一层 —— 变异检验实测：把 `dCycleAccountScope.pickDTbSourceCodes` 里的
// `project_context` 分支挖掉后，全部源码级断言仍然通过（D4 会恒读不到载荷、
// 溯源面板永不渲染，而 get_diagnostics / Vite 200 / vitest 四层全绿）。
//
// 落点事实（2026-08-06 实测，design.md 写的与实际不符）：
//   html_data 顶层        → D1 / D2 / D3 / D5 / D6 / D7（6 个）
//   html_data.project_context → D4（唯一）

describe('Property 15: pickDTbSourceCodes 两层落点', () => {
  const payload = { row_code: 'BS-006', gross: ['1122'] }

  it('顶层落点可读（D1/D2/D3/D5/D6/D7 的形态）', () => {
    const got = pickDTbSourceCodes({ tb_source_codes: payload })
    expect(got, '顶层 tb_source_codes 未被读到').not.toBeNull()
    expect(got!.row_code).toBe('BS-006')
  })

  it('project_context 落点可读（D4 的形态）', () => {
    const got = pickDTbSourceCodes({ project_context: { tb_source_codes: payload } })
    expect(got, 'project_context.tb_source_codes 未被读到 —— D4 的溯源面板会永不渲染').not.toBeNull()
    expect(got!.row_code).toBe('BS-006')
  })

  it('两层同时存在时顶层优先（避免同一底稿出现两个口径）', () => {
    const got = pickDTbSourceCodes({
      tb_source_codes: { row_code: 'TOP' },
      project_context: { tb_source_codes: { row_code: 'PC' } },
    })
    expect(got!.row_code).toBe('TOP')
  })

  it('两层都没有时返 null（未取数 ≠ 空载荷）', () => {
    expect(pickDTbSourceCodes({})).toBeNull()
    expect(pickDTbSourceCodes(null)).toBeNull()
    expect(pickDTbSourceCodes('not-an-object')).toBeNull()
  })

  it('normalizeDSlots 把 query_codes 投影成 codes/standard_codes（否则共享工厂误判「无此科目」）', () => {
    const got = normalizeDSlots({
      slots: { gross: { found: true, query_codes: ['1122'], closing: 1 } as any },
    } as any)
    const slot = got!.slots!.gross as any
    expect(slot.codes).toEqual(['1122'])
    expect(slot.standard_codes).toEqual(['1122'])
  })

  it('反向自检：只读单层的朴素实现会漏掉 project_context（M5 变异要打红的正是这条）', () => {
    const naive = (hd: any) => hd?.tb_source_codes ?? null
    expect(naive({ project_context: { tb_source_codes: payload } })).toBeNull()
    expect(pickDTbSourceCodes({ project_context: { tb_source_codes: payload } })).not.toBeNull()
  })
})
