/**
 * crossWorkpaperNav.spec.ts — 跨表导航按循环解析 + 七枢纽零回归守卫
 *
 * spec: g0-confirmation-source-alignment，Task 11
 * Property 12（跨表导航项按循环解析且无失效入口）
 * Property 13（`buildCrossWorkpaperNavDefs` 有真实非测试消费方，防再退化为零消费方）
 * R11.1（`CrossWorkpaperNav.vue` 是七枢纽共享件 → D0/E0/F0/H0/K0/L0 导航项逐字不变）
 *
 * 🔴 本文件的 SIX_HUB_BASELINE 是**改造前**真实跑 `buildCrossWorkpaperNavDefs()`
 *    采集的（2026-08-04），不是照着代码抄的期望值 —— 它是零回归的唯一锚点，
 *    只有在用户明确裁决改变某枢纽行为时才允许改动。
 */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  buildCrossWorkpaperNavDefs,
  getCycleConfirmationMeta,
  isSameWorkbookNavTarget,
  type ConfirmationCycle,
  type ConfirmationSheetRef,
  type ConfirmationSheetSlot,
  type CrossWorkpaperNavDef,
} from '../cycleConfirmationMeta'
import { G0_SHEET_NAMES } from '../../../g0-confirmation/g0SheetRegistry'
import { L0_SHEET_NAMES } from '../../l0-confirmation/l0SheetRegistry'
import { K0_SHEET_NAMES } from '../../k0-confirmation/k0SheetRegistry'

// ─── REPO_ROOT：哨兵**文件**向上查找（禁写死回退级数） ───────────────────────
const SENTINELS = [
  join('backend', 'app', 'data', 'wp_code_overrides.json'),
  join('audit-platform', 'frontend', 'package.json'),
] as const

function findRepoRoot(start: string): string {
  let dir = resolve(start)
  for (let i = 0; i < 20; i += 1) {
    if (SENTINELS.every((s) => existsSync(join(dir, s)))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能从 ${start} 向上找到同时含哨兵文件的仓库根：${SENTINELS.join(' + ')}`)
}

const REPO_ROOT = findRepoRoot(__dirname)
const FRONTEND_SRC = join(REPO_ROOT, 'audit-platform', 'frontend', 'src')
const NAV_VUE = join(
  FRONTEND_SRC,
  'components/workpaper/confirmation/coordination/CrossWorkpaperNav.vue',
)

/** 去注释（块 + 行 + HTML）—— 组件注释里写着「改造前写死了 D0-*」这类反例 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    const st = statSync(full)
    if (st.isDirectory()) {
      if (name === 'node_modules' || name === 'dist') continue
      walk(full, out)
    } else if (/\.(ts|vue|js)$/.test(name)) {
      out.push(full)
    }
  }
  return out
}

const ALL_SOURCE_FILES = walk(FRONTEND_SRC)

// ─── 改造前基线（真实采集，2026-08-04） ──────────────────────────────────────

type NavShape = { wpCode: string; label: string; tooltip: string }

const SIX_HUB_BASELINE: Readonly<Record<Exclude<ConfirmationCycle, 'G0'>, NavShape[]>> = {
  D0: [
    { wpCode: 'D0-2', label: 'D0-2', tooltip: '核实被函证单位' },
    { wpCode: 'D0-1', label: 'D0-1', tooltip: '函证汇总表' },
    { wpCode: 'D0-3', label: 'D0-3', tooltip: '跟函过程控制' },
    { wpCode: 'D0-7', label: 'D0-7', tooltip: '回函可靠性验证' },
    { wpCode: 'D0-4', label: 'D0-4', tooltip: '差异调节表' },
    { wpCode: 'D0-4b', label: 'D0-4b', tooltip: '差异检查表' },
    { wpCode: 'D0-5/D0-6', label: 'D0-5/D0-6', tooltip: '替代程序' },
    { wpCode: 'D0-8', label: 'D0-8', tooltip: '舞弊风险评价' },
  ],
  E0: [
    { wpCode: 'E0-2', label: 'E0-2', tooltip: '核实被函证单位' },
    { wpCode: 'E0-1', label: 'E0-1', tooltip: '函证汇总表' },
    { wpCode: 'E0-7', label: 'E0-7', tooltip: '跟函过程控制' },
    { wpCode: 'E0-8', label: 'E0-8', tooltip: '舞弊风险评价' },
  ],
  F0: [
    { wpCode: 'F0-2', label: 'F0-2', tooltip: '核实被函证单位' },
    { wpCode: 'F0-1', label: 'F0-1', tooltip: '函证汇总表' },
    { wpCode: 'F0-3', label: 'F0-3', tooltip: '跟函过程控制' },
    { wpCode: 'F0-7', label: 'F0-7', tooltip: '回函可靠性验证' },
    { wpCode: 'F0-4', label: 'F0-4', tooltip: '差异调节表' },
    { wpCode: 'F0-4b', label: 'F0-4b', tooltip: '差异检查表' },
    { wpCode: 'F0-5/F0-6', label: 'F0-5/F0-6', tooltip: '替代程序' },
    { wpCode: 'F0-8', label: 'F0-8', tooltip: '舞弊风险评价' },
  ],
  H0: [
    { wpCode: 'H0-2', label: 'H0-2', tooltip: '核实被函证单位' },
    { wpCode: 'H0-1', label: 'H0-1', tooltip: '函证汇总表' },
    { wpCode: 'H0-3', label: 'H0-3', tooltip: '跟函过程控制' },
    { wpCode: 'H0-6', label: 'H0-6', tooltip: '回函可靠性验证' },
    { wpCode: 'H0-4', label: 'H0-4', tooltip: '差异调节表' },
    { wpCode: 'H0-5', label: 'H0-5', tooltip: '替代程序' },
    { wpCode: 'H0-7', label: 'H0-7', tooltip: '舞弊风险评价' },
  ],
  K0: [
    { wpCode: 'K0-2', label: 'K0-2', tooltip: '核实被函证单位' },
    { wpCode: 'K0-1', label: 'K0-1', tooltip: '函证汇总表' },
    { wpCode: 'K0-3', label: 'K0-3', tooltip: '跟函过程控制' },
    { wpCode: 'K0-7', label: 'K0-7', tooltip: '回函可靠性验证' },
    { wpCode: 'K0-4', label: 'K0-4', tooltip: '差异调节表' },
    { wpCode: 'K0-5/K0-6', label: 'K0-5/K0-6', tooltip: '替代程序' },
    { wpCode: 'K0-8', label: 'K0-8', tooltip: '舞弊风险评价' },
  ],
  L0: [
    { wpCode: 'L0-2', label: 'L0-2', tooltip: '核实被函证单位' },
    { wpCode: 'L0-1', label: 'L0-1', tooltip: '函证汇总表' },
    { wpCode: 'L0-3', label: 'L0-3', tooltip: '跟函过程控制' },
    { wpCode: 'L0-6', label: 'L0-6', tooltip: '回函可靠性验证' },
    { wpCode: 'L0-4', label: 'L0-4', tooltip: '差异调节表' },
    { wpCode: 'L0-5', label: 'L0-5', tooltip: '替代程序' },
    { wpCode: 'L0-7', label: 'L0-7', tooltip: '舞弊风险评价' },
  ],
}

const shape = (defs: CrossWorkpaperNavDef[]): NavShape[] =>
  defs.map(({ wpCode, label, tooltip }) => ({ wpCode, label, tooltip }))

/**
 * 走 `deriveSheetsFromCodes`（无 tab 名真源）的循环。
 *
 * 🔴 L0 已于 spec `l0-confirmation-source-alignment` Task 18 接 `l0SheetRegistry`
 *    → 它的 `sheetName` 变成真实中文 tab 名、`isSameWorkbookNavTarget` 转 true。
 *    **`SIX_HUB_BASELINE.L0` 的 wpCode/label/tooltip 三元组仍逐字不变**（零回归锚点没动），
 *    变的只是同工作簿定位能力。库侧实证：`wp_index` 里 L0 只有整册 `L0` 与遗留单 sheet
 *    `L0-1`~`L0-5`，**没有 L0-6/L0-7** ⇒ 改造前按 wp_code 跳这两张表本来就落空。
 *
 * 🔴 K0 已于 spec `k0-confirmation-source-alignment` Task 12 接 `k0SheetRegistry`
 *    → 同 L0（wpCode/label 零回归锚点未动），另有一处**有意的行为变更**：
 *    K0 的三条「跨表引用索引号笔误」按 R6.2 必须在 tooltip 里标注 ⇒ `K0-3`/`K0-4`/`K0-7`
 *    三项的 tooltip 在基础文案后**追加**了说明。故 K0 的 tooltip 判据由「逐字全等」
 *    放宽为「以基线文案开头」（只许追加、不许改写），并由
 *    `k0-confirmation/__tests__/k0SheetRegistry.spec.ts` 逐条锁死追加内容由真源派生。
 *    库侧实证：`wp_index` 里 K0 只有整册 `K0` 与遗留 `K0-1`~`K0-5`，**没有 K0-6/K0-7/K0-8**。
 */
const DERIVED_CYCLES = ['D0', 'E0', 'F0', 'H0'] as const
/** 有源模板 tab 名真源（走注册表）的循环 */
const REGISTRY_CYCLES = ['G0', 'K0', 'L0'] as const
/** tooltip 允许在基线文案后追加笔误说明的循环（其余必须逐字全等） */
const TOOLTIP_SUFFIX_ALLOWED = new Set<string>(['K0'])

// ─── Property 12: 按循环解析且无失效入口 ─────────────────────────────────────

describe('Property 12: 跨表导航项按循环解析且无失效入口', () => {
  it('组件源码不再含写死的 D0-* 导航定义', () => {
    const src = stripComments(readFileSync(NAV_VUE, 'utf-8'))
    expect(src).not.toContain('NAV_DEFINITIONS')
    expect(src).not.toMatch(/wpCode:\s*'D0-/)
    expect(src).not.toMatch(/'D0-5\/6'/)
    // 而且确实改用了按循环解析的单一真源
    expect(src).toContain('buildCrossWorkpaperNavDefs(')
  })

  it('G0 不再产生指向不存在底稿 G0-3S 的入口', () => {
    const defs = buildCrossWorkpaperNavDefs('G0-1')
    expect(defs.map((d) => d.wpCode)).not.toContain('G0-3S')
    expect(defs.some((d) => JSON.stringify(d).includes('G0-3S'))).toBe(false)
    // 两张差异表按底稿目录裁决展示为 G0-4（证券）/ G0-5（非证券）
    const byTooltip = new Map(defs.map((d) => [d.tooltip.split('（')[0], d]))
    expect(byTooltip.get('证券差异专表')!.label).toBe('G0-4')
    expect(byTooltip.get('差异调节表')!.label).toBe('G0-5')
  })

  it('G0 每个导航项都有非 null 且在源模板 10 张 sheet 里的 sheetName', () => {
    const defs = buildCrossWorkpaperNavDefs('G0-1')
    expect(defs.length).toBeGreaterThan(0)
    for (const d of defs) {
      expect(d.sheetName, d.label).toBeTruthy()
      expect(G0_SHEET_NAMES, d.label).toContain(d.sheetName!)
      expect(isSameWorkbookNavTarget(d), d.label).toBe(true)
    }
  })

  it('G0 差异表的 tooltip 标注了源模板索引号笔误（不静默改写）', () => {
    const defs = buildCrossWorkpaperNavDefs('G0-1')
    const sec = defs.find((d) => d.label === 'G0-4')!
    expect(sec.tooltip).toContain('G0-3')
    expect(sec.tooltip).toContain('G0-4')
    const fraud = defs.find((d) => d.label === 'G0-8')!
    expect(fraud.tooltip).toContain('F0-8')
  })
})

// ─── R11.1: 六枢纽零回归 ─────────────────────────────────────────────────────

describe('R11.1: 六枢纽导航项与改造前逐字一致（共享组件零回归）', () => {
  for (const cycle of Object.keys(SIX_HUB_BASELINE) as Array<keyof typeof SIX_HUB_BASELINE>) {
    it(`${cycle} 导航项集合不变`, () => {
      const actual = shape(buildCrossWorkpaperNavDefs(`${cycle}-1`))
      const base = SIX_HUB_BASELINE[cycle]
      if (!TOOLTIP_SUFFIX_ALLOWED.has(cycle)) {
        expect(actual).toEqual(base)
        return
      }
      // 🔴 K0：wpCode/label 逐字冻结（零回归锚点），tooltip 只许在基线文案后追加笔误说明。
      expect(actual.map(({ wpCode, label }) => ({ wpCode, label }))).toEqual(
        base.map(({ wpCode, label }) => ({ wpCode, label })),
      )
      actual.forEach((d, i) => {
        expect(d.tooltip, `${cycle}/${d.label} tooltip 被改写而非追加`).toContain(base[i].tooltip)
        expect(d.tooltip.startsWith(base[i].tooltip), `${cycle}/${d.label} 基线文案必须在最前`).toBe(true)
      })
    })
  }

  it('K0 恰有三项 tooltip 追加了笔误说明（其余项逐字不变）', () => {
    const actual = shape(buildCrossWorkpaperNavDefs('K0-1'))
    const base = SIX_HUB_BASELINE.K0
    const appended = actual
      .map((d, i) => ({ label: d.label, extra: d.tooltip.slice(base[i].tooltip.length) }))
      .filter((x) => x.extra.length > 0)
    expect(appended.map((x) => x.label).sort()).toEqual(['K0-3', 'K0-4', 'K0-7'])
    for (const x of appended) {
      expect(x.extra, `${x.label} 的追加说明未标注源模板出处`).toContain('源模板')
    }
  })

  it('四个派生枢纽的 sheetName 必须由既有 code 派生（非 null 且 === wpCode），不得整体为 null', () => {
    // 🔴 这条是 Task 11「最容易做错的一处」的正面锁：若派生环节退化成 `sheetName: null`，
    //    组件那条「null 就不生成入口」的规则会把这些枢纽的入口全部干掉。
    //    断言不得写成 `if (d.sheetName !== null) …` —— 那样 null 会静默通过（首版守卫即如此，
    //    被变异测试 M7 抓出）。
    for (const cycle of DERIVED_CYCLES) {
      const defs = buildCrossWorkpaperNavDefs(`${cycle}-1`)
      for (const d of defs) {
        if (d.wpCode.includes('/')) {
          // 组合替代程序（X0-5/X0-6）没有单一 sheet → 显式 null，回退按 wpCode 跳
          expect(d.sheetName, `${cycle}/${d.label}`).toBeNull()
        } else {
          expect(d.sheetName, `${cycle}/${d.label}`).toBe(d.wpCode)
        }
        expect(isSameWorkbookNavTarget(d), `${cycle}/${d.label}`).toBe(false)
      }
      // 「若组件按 sheetName 过滤」时保留下来的入口数 = 除组合替代程序外的全部
      const combined = defs.filter((d) => d.wpCode.includes('/')).length
      expect(defs.filter((d) => d.sheetName !== null).length, cycle).toBe(defs.length - combined)
    }
  })

  it('L0 已接注册表：wpCode/label/tooltip 三元组不变，但 sheetName 变成真实 tab 名', () => {
    // 零回归锚点未动（上面的「L0 导航项集合不变」用的还是同一份 SIX_HUB_BASELINE.L0）
    const defs = buildCrossWorkpaperNavDefs('L0-1')
    expect(shape(defs)).toEqual(SIX_HUB_BASELINE.L0)
    // 变化点：每一项都拿到源模板 tab 名 → 同工作簿 `?sheet=` 深链可达
    for (const d of defs) {
      expect(d.sheetName, d.label).toBeTruthy()
      expect(L0_SHEET_NAMES, d.label).toContain(d.sheetName!)
      expect(d.sheetName, d.label).not.toBe(d.wpCode)
      expect(isSameWorkbookNavTarget(d), d.label).toBe(true)
    }
    // 反向锁：若哪天 L0 退回派生（sheetName === wpCode），本条必红
    expect(defs.find((d) => d.label === 'L0-1')!.sheetName).toBe('函证结果汇总表L0-1')
    expect(defs.find((d) => d.label === 'L0-7')!.sheetName).toBe('函证程序舞弊风险评价表L0-7')
  })

  it('K0 已接注册表：wpCode/label 不变、sheetName 变真实 tab 名、三项 tooltip 追加笔误说明', () => {
    const defs = buildCrossWorkpaperNavDefs('K0-1')
    // wpCode/label 零回归锚点未动
    expect(defs.map((d) => d.wpCode)).toEqual(SIX_HUB_BASELINE.K0.map((b) => b.wpCode))
    for (const d of defs) {
      if (d.wpCode.includes('/')) {
        // 组合替代程序（K0-5/K0-6）没有单一 sheet → 仍显式 null，回退按 wpCode 跳
        expect(d.sheetName, d.label).toBeNull()
        expect(isSameWorkbookNavTarget(d), d.label).toBe(false)
        continue
      }
      expect(d.sheetName, d.label).toBeTruthy()
      expect(K0_SHEET_NAMES, d.label).toContain(d.sheetName!)
      expect(d.sheetName, d.label).not.toBe(d.wpCode)
      expect(isSameWorkbookNavTarget(d), d.label).toBe(true)
    }
    // 反向锁：若哪天 K0 退回派生（sheetName === wpCode），本条必红
    expect(defs.find((d) => d.label === 'K0-1')!.sheetName).toBe('函证结果汇总表K0-1')
    expect(defs.find((d) => d.label === 'K0-8')!.sheetName).toBe('函证程序舞弊风险评价表K0-8')
  })

  it('注册表枢纽与派生枢纽两组互斥且合起来正好是七枢纽（防新增循环漏归组）', () => {
    const all = [...DERIVED_CYCLES, ...REGISTRY_CYCLES].sort()
    expect(new Set(all).size).toBe(all.length)
    expect(all).toEqual(['D0', 'E0', 'F0', 'G0', 'H0', 'K0', 'L0'])
  })

  it('既有 *Code 字段一个都没删，且六枢纽取值不变（加法式扩展支点）', () => {
    const CODE_FIELDS = [
      'summaryCode',
      'diffCode',
      'diffChecklistCode',
      'diffSecuritiesCode',
      'altPrimaryCode',
      'altSecondaryCode',
      'reliabilityCode',
      'fraudCode',
      'entityVerifyCode',
      'followupCode',
    ] as const
    const m = getCycleConfirmationMeta('D0-1')
    for (const f of CODE_FIELDS) expect(Object.prototype.hasOwnProperty.call(m, f), f).toBe(true)
    expect(m.diffChecklistCode).toBe('D0-4b')
    expect(getCycleConfirmationMeta('E0-1').reliabilityCode).toBeNull()
    expect(getCycleConfirmationMeta('K0-1').altSecondaryCode).toBe('K0-6')
  })

  it('反向自检：若六枢纽不派生 sheetName（全 null）且按「null 就不生成入口」处理，入口会被全部干掉', () => {
    // 复现「最容易做错的一处」：这正是 Task 11 第 3 条不能写成「null 即跳过」的原因
    const naiveFilter = (defs: CrossWorkpaperNavDef[], sheets: Record<string, unknown>) =>
      defs.filter((d) => sheets[d.label] !== null)
    for (const cycle of Object.keys(SIX_HUB_BASELINE) as Array<keyof typeof SIX_HUB_BASELINE>) {
      const defs = buildCrossWorkpaperNavDefs(`${cycle}-1`)
      const allNullSheets = Object.fromEntries(defs.map((d) => [d.label, null]))
      expect(naiveFilter(defs, allNullSheets).length, cycle).toBe(0)
      // 现行实现下它们全部保留
      expect(defs.length, cycle).toBeGreaterThan(0)
    }
  })

  it('反向自检：stripComments 剥掉注释里的 D0-* 反例（否则上面的源码断言是假红/空转）', () => {
    const fixture = `
      // const NAV_DEFINITIONS = [{ wpCode: 'D0-2' }]
      /* 'D0-5/6' */
      <!-- wpCode: 'D0-8' -->
      const real = buildCrossWorkpaperNavDefs(props.wpCode)
    `
    const out = stripComments(fixture)
    expect(out).not.toContain('NAV_DEFINITIONS')
    expect(out).not.toContain("'D0-5/6'")
    expect(out).not.toContain("wpCode: 'D0-8'")
    expect(out).toContain('buildCrossWorkpaperNavDefs(props.wpCode)')
  })
})

// ─── Property 13: 真实非测试消费方 ───────────────────────────────────────────

describe('Property 13: buildCrossWorkpaperNavDefs 有真实非测试消费方', () => {
  const isExcluded = (p: string) =>
    p.replace(/\\/g, '/').includes('/__tests__/') || p.endsWith('components.d.ts')

  it('扫全仓（排除 __tests__ 与 components.d.ts）至少 1 个消费方', () => {
    expect(ALL_SOURCE_FILES.length).toBeGreaterThan(500) // 防 walk 失效导致空转
    const consumers = ALL_SOURCE_FILES.filter((p) => {
      if (isExcluded(p)) return false
      const src = stripComments(readFileSync(p, 'utf-8'))
      if (p.endsWith('cycleConfirmationMeta.ts')) return false // 声明处不算消费方
      return /buildCrossWorkpaperNavDefs\s*\(/.test(src)
    }).map((p) => p.replace(/\\/g, '/').split('/src/')[1])
    expect(consumers.length, `消费方清单：${JSON.stringify(consumers)}`).toBeGreaterThan(0)
    expect(consumers).toContain(
      'components/workpaper/confirmation/coordination/CrossWorkpaperNav.vue',
    )
  })

  it('isSameWorkbookNavTarget 也有真实消费方（不是只给守卫用的死函数）', () => {
    const consumers = ALL_SOURCE_FILES.filter((p) => {
      if (isExcluded(p) || p.endsWith('cycleConfirmationMeta.ts')) return false
      return /isSameWorkbookNavTarget\s*\(/.test(stripComments(readFileSync(p, 'utf-8')))
    })
    expect(consumers.length).toBeGreaterThan(0)
  })

  it('g0SheetRegistry 有真实消费方（meta 引用）', () => {
    const consumers = ALL_SOURCE_FILES.filter((p) => {
      if (isExcluded(p) || p.endsWith('g0SheetRegistry.ts')) return false
      return /g0SheetRegistry/.test(stripComments(readFileSync(p, 'utf-8')))
    }).map((p) => p.replace(/\\/g, '/').split('/src/')[1])
    expect(consumers, JSON.stringify(consumers)).toContain(
      'components/workpaper/confirmation/coordination/cycleConfirmationMeta.ts',
    )
  })

  it('反向自检：扫一个必然不存在的符号必须返回 0（证明扫描不是恒真）', () => {
    const bogus = ALL_SOURCE_FILES.filter((p) =>
      /buildCrossWorkpaperNavDefsThatDoesNotExist\s*\(/.test(readFileSync(p, 'utf-8')),
    )
    expect(bogus.length).toBe(0)
  })
})

// ─── 类型面：sheets 字段完整覆盖 11 槽位 ─────────────────────────────────────

describe('sheets 字段覆盖 11 槽位且 G0 引用注册表', () => {
  const SLOTS: ConfirmationSheetSlot[] = [
    'program',
    'summary',
    'entityVerify',
    'followup',
    'diff',
    'diffSecurities',
    'diffChecklist',
    'altPrimary',
    'altSecondary',
    'reliability',
    'fraud',
  ]

  it('七枢纽的 sheets 都有全部 11 个键', () => {
    for (const cycle of ['D0', 'E0', 'F0', 'G0', 'H0', 'K0', 'L0'] as ConfirmationCycle[]) {
      const m = getCycleConfirmationMeta(`${cycle}-1`)
      expect(Object.keys(m.sheets).sort(), cycle).toEqual([...SLOTS].sort())
    }
  })

  it('G0 的 sheets 取自注册表（真实 tab 名），不是派生 code', () => {
    const m = getCycleConfirmationMeta('G0-1')
    const refs = SLOTS.map((s) => m.sheets[s]).filter((r): r is ConfirmationSheetRef => !!r)
    expect(refs.length).toBe(9) // 11 槽 − diffChecklist − altSecondary
    expect(m.sheets.fraud!.sheetName).toBe('函证程序舞弊风险评价表F0-8')
    expect(m.sheets.fraud!.indexLabel).toBe('G0-8')
    expect(m.sheets.program!.sheetName).toBe('函证程序表G0A')
  })

  it('六枢纽 program 槽按前缀派生 {cycle}A', () => {
    expect(getCycleConfirmationMeta('D0-1').sheets.program!.indexLabel).toBe('D0A')
    expect(getCycleConfirmationMeta('L0-1').sheets.program!.indexLabel).toBe('L0A')
  })
})
