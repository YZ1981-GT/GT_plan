/**
 * 完整性豁免判据守卫（Wave 2 打红）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 5
 * Property 6（认定级优先）/ 7（循环级仅在认定缺失时生效）/ 8（每条都有审计依据）/
 * 9（平台默认标注与覆盖状态一致）。
 *
 * ## 本文件只管完整性豁免
 *
 * 类 A 的共享判据（`materiality` 表列、`scope-accounts` 的 `amount`、现状裁剪丢弃
 * `amount`、`TrimReasonCode` 快照、pm/te/sat 扫描）**全部集中在
 * `procedureTrimDecision.spec.ts`**，本文件不重复 —— 同一不变式两处各写一份会让
 * 「改一处另一处不红」。
 *
 * ## 类 A / 类 B
 *
 * - 类 A（现在应全绿）：默认清单要覆盖的 11 个循环取值来自 `ProcedureTrimming.vue` 的
 *   `DATA_DRIVEN_CYCLES`（独立真源，本守卫自己读出来），且 A/B/C/S 确实不在其中。
 * - 类 B（现在应全红）：`completenessExemption.ts` 存在且导出约定接口与行为。
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 14; i += 1) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵）')
}

const ROOT = repoRoot()
const FE = path.join(ROOT, 'audit-platform', 'frontend', 'src')
const P_EXEMPTION = path.join(FE, 'components', 'workpaper', 'composables', 'completenessExemption.ts')
const P_TRIM_VUE = path.join(FE, 'views', 'ProcedureTrimming.vue')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
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
      if (c === '\\') {
        out += n ?? ''
        i += 2
        continue
      }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c
      out += c
      i += 1
      continue
    }
    if (c === '/' && n === '/') {
      while (i < src.length && src[i] !== '\n') i += 1
      continue
    }
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

function pendingFail(what: string, task: string): never {
  return expect.fail(
    `${what} 尚未实现（Wave 2 ${task}）。本条红是**预期**的 Wave 2 打红结果。`,
  )
}

async function loadPure(file: string, specifier: string, task: string): Promise<any> {
  if (!fs.existsSync(file)) pendingFail(`模块 ${path.basename(file)}`, task)
  try {
    return await import(/* @vite-ignore */ specifier)
  } catch (e) {
    pendingFail(`模块 ${path.basename(file)} 无法加载（${String(e)}）`, task)
  }
}

/** 默认**开**（完整性敏感）：负债费用类的完整性风险系统性高于资产类。 */
const EXPECT_SENSITIVE = ['L', 'J', 'N', 'K', 'D']
/** 默认**关**：主风险为存在与估值（高估方向），账面小则敞口本身小。 */
const EXPECT_NOT_SENSITIVE = ['E', 'F', 'G', 'H', 'I', 'M']
/** 非科目余额驱动，本判据不适用。 */
const EXPECT_ABSENT = ['A', 'B', 'C', 'S']

// ═══════════════════════════════════════════════════════════════════════════
// helper 自检
// ═══════════════════════════════════════════════════════════════════════════
describe('helper 自检', () => {
  it('stripComments 剥注释保字面量', () => {
    const s = stripComments(`const a = 'L' // 注释里写 'E'\n/* 块里写 'F' */`)
    expect(s).toContain("'L'")
    expect(s).not.toContain('注释里写')
  })

  it('loadPure 对不存在的模块产生「尚未实现」红而非 collection error', async () => {
    const bogus = path.join(path.dirname(P_EXEMPTION), '__nope_ce__.ts')
    await expect(loadPure(bogus, './__nope_ce__', 'Task 0')).rejects.toThrow(/尚未实现/)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 A：默认清单应覆盖的循环集合（独立真源 = DATA_DRIVEN_CYCLES）
// ═══════════════════════════════════════════════════════════════════════════
describe('[类 A] 默认清单的覆盖面来自独立真源', () => {
  const src = stripComments(read(P_TRIM_VUE))
  const m = src.match(/const\s+DATA_DRIVEN_CYCLES\s*=\s*new\s+Set\(\[([^\]]+)\]\)/)
  const codes = m ? Array.from(m[1].matchAll(/'([A-Z])'/g)).map((x) => x[1]) : []

  it('扫描面非空自检：抽出 11 个科目余额驱动循环', () => {
    expect(m, '未找到 DATA_DRIVEN_CYCLES（正则失效或常量已改名）').not.toBeNull()
    expect(codes.length, `抽出的循环数应为 11，实为 ${codes.length}`).toBe(11)
  })

  it('期望的开/关两组合起来恰好等于该集合（清单不多不少）', () => {
    expect([...EXPECT_SENSITIVE, ...EXPECT_NOT_SENSITIVE].slice().sort()).toEqual(
      codes.slice().sort(),
    )
  })

  it('A/B/C/S 确实不在其中（本判据不适用）', () => {
    for (const c of EXPECT_ABSENT) {
      expect(codes, `${c} 不应是科目余额驱动循环`).not.toContain(c)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 B：模块契约与四条 Property
// ═══════════════════════════════════════════════════════════════════════════
describe('[类 B] completenessExemption 模块契约', () => {
  it('模块存在且导出 COMPLETENESS_CYCLE_RULES + resolveCompletenessExemption', async () => {
    const mod = await loadPure(P_EXEMPTION, '../completenessExemption', 'Task 6')
    expect(Array.isArray(mod.COMPLETENESS_CYCLE_RULES), 'COMPLETENESS_CYCLE_RULES 应为数组').toBe(
      true,
    )
    expect(typeof mod.resolveCompletenessExemption, 'resolveCompletenessExemption 应为函数').toBe(
      'function',
    )
  })

  it('模块零 Vue 依赖、零 IO', () => {
    if (!fs.existsSync(P_EXEMPTION)) pendingFail('模块 completenessExemption.ts', 'Task 6')
    const src = stripComments(read(P_EXEMPTION))
    expect(/from\s+['"]vue['"]/.test(src), '不得依赖 vue').toBe(false)
    expect(/\bfetch\s*\(|axios|http\.get/.test(src), '不得含 IO').toBe(false)
  })
})

describe('[类 B] Property 8: 完整性清单每条都有审计依据', () => {
  it('覆盖 11 个循环、不含 A/B/C/S、每条 rationale 长度 ≥ 20 且非占位', async () => {
    const { COMPLETENESS_CYCLE_RULES } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    const rules: any[] = COMPLETENESS_CYCLE_RULES as any[]
    const byCycle = new Map(rules.map((r) => [r.cycle, r]))

    expect(rules.length, '清单条数应为 11').toBe(11)
    for (const c of [...EXPECT_SENSITIVE, ...EXPECT_NOT_SENSITIVE]) {
      expect(byCycle.has(c), `清单缺少循环 ${c}`).toBe(true)
    }
    for (const c of EXPECT_ABSENT) {
      expect(byCycle.has(c), `清单不得含 ${c}（非科目余额驱动）`).toBe(false)
    }

    const PLACEHOLDER = /^(?:TODO|待补充|待填|同上|-+|\s*)$/
    for (const r of rules) {
      expect(typeof r.rationale, `${r.cycle} 的 rationale 应为字符串`).toBe('string')
      expect(
        r.rationale.length,
        `${r.cycle} 的 rationale 长度 ${r.rationale.length} < 20（须写明审计依据）`,
      ).toBeGreaterThanOrEqual(20)
      expect(PLACEHOLDER.test(r.rationale.trim()), `${r.cycle} 的 rationale 是占位文本`).toBe(false)
      expect(typeof r.sensitiveByDefault, `${r.cycle} 的 sensitiveByDefault 应为布尔`).toBe(
        'boolean',
      )
    }
  })

  it('默认开/关取值与审计依据一致（负债费用类开、资产类关）', async () => {
    const { COMPLETENESS_CYCLE_RULES } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    const byCycle = new Map((COMPLETENESS_CYCLE_RULES as any[]).map((r) => [r.cycle, r]))
    for (const c of EXPECT_SENSITIVE) {
      expect(byCycle.get(c)?.sensitiveByDefault, `${c} 应默认开（完整性敏感）`).toBe(true)
    }
    for (const c of EXPECT_NOT_SENSITIVE) {
      expect(byCycle.get(c)?.sensitiveByDefault, `${c} 应默认关`).toBe(false)
    }
  })
})

describe('[类 B] Property 6: 完整性认定优先于循环级', () => {
  it('completenessRmm 非 null 时结果与 projectOverride / 循环级清单无关，且 source=assertion', async () => {
    const { resolveCompletenessExemption } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    // 取一个默认**关**的循环（E），并给一个把它强行打开的项目覆盖 ——
    // 认定级存在时这两者都不应影响结论。
    for (const rmm of ['H', 'M', 'L'] as const) {
      const variants = [
        { cycle: 'E', projectOverride: null },
        { cycle: 'E', projectOverride: { E: true } },
        { cycle: 'L', projectOverride: { L: false } },
      ]
      const results = variants.map((v) =>
        resolveCompletenessExemption({
          completenessRmm: rmm,
          completenessSpecial: false,
          ...v,
        }),
      )
      for (const r of results) {
        expect(r.source, `completenessRmm=${rmm} 时 source 应为 assertion`).toBe('assertion')
      }
      const exempts = new Set(results.map((r) => r.exempt))
      expect(
        exempts.size,
        `completenessRmm=${rmm} 时结论受循环级影响（认定级未优先），得到 ${JSON.stringify(results.map((r) => r.exempt))}`,
      ).toBe(1)
    }
  })

  it('completenessSpecial 为真时同样走认定级且豁免', async () => {
    const { resolveCompletenessExemption } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    const r = resolveCompletenessExemption({
      completenessRmm: null,
      completenessSpecial: true,
      cycle: 'E',
      projectOverride: { E: false },
    })
    expect(r.source).toBe('assertion')
    expect(r.exempt, '完整性认定为特别风险时必须豁免金额判据').toBe(true)
  })

  it('认定级为 H 时豁免（不受金额判据裁剪）', async () => {
    const { resolveCompletenessExemption } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    const r = resolveCompletenessExemption({
      completenessRmm: 'H',
      completenessSpecial: false,
      cycle: 'E',
      projectOverride: null,
    })
    expect(r.exempt).toBe(true)
    expect(r.source).toBe('assertion')
  })
})

describe('[类 B] Property 7: 循环级清单仅在认定缺失时生效', () => {
  it('completenessRmm=null 且 completenessSpecial=false ⟹ source ∈ {cycle_default, cycle_override, none}', async () => {
    const { resolveCompletenessExemption } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    const cases = [
      { cycle: 'L', projectOverride: null },
      { cycle: 'E', projectOverride: null },
      { cycle: 'L', projectOverride: { L: false } },
      { cycle: 'E', projectOverride: { E: true } },
      { cycle: 'B', projectOverride: null },
      { cycle: 'S', projectOverride: null },
    ]
    for (const c of cases) {
      const r = resolveCompletenessExemption({
        completenessRmm: null,
        completenessSpecial: false,
        ...c,
      })
      expect(
        ['cycle_default', 'cycle_override', 'none'],
        `cycle=${c.cycle} override=${JSON.stringify(c.projectOverride)} 得到 source=${r.source}`,
      ).toContain(r.source)
      expect(r.source, '认定缺失时不得声称走了认定级').not.toBe('assertion')
    }
  })

  it('清单外循环（A/B/C/S）走 none 且不豁免', async () => {
    const { resolveCompletenessExemption } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    for (const cycle of EXPECT_ABSENT) {
      const r = resolveCompletenessExemption({
        completenessRmm: null,
        completenessSpecial: false,
        cycle,
        projectOverride: null,
      })
      expect(r.source, `${cycle} 不在清单内应为 none`).toBe('none')
      expect(r.exempt, `${cycle} 不适用本判据，不应豁免`).toBe(false)
    }
  })

  it('项目覆盖生效时 source=cycle_override 且结论按覆盖值', async () => {
    const { resolveCompletenessExemption } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    const opened = resolveCompletenessExemption({
      completenessRmm: null,
      completenessSpecial: false,
      cycle: 'E',
      projectOverride: { E: true },
    })
    expect(opened.source).toBe('cycle_override')
    expect(opened.exempt, '项目把 E 设为完整性敏感 ⟹ 豁免金额判据').toBe(true)

    const closed = resolveCompletenessExemption({
      completenessRmm: null,
      completenessSpecial: false,
      cycle: 'D',
      projectOverride: { D: false },
    })
    expect(closed.source).toBe('cycle_override')
    expect(closed.exempt, '项目把 D 关掉 ⟹ 不豁免').toBe(false)
  })
})

describe('[类 B] Property 9: 平台默认标注与覆盖状态一致', () => {
  it('usingPlatformDefault === true 当且仅当 source === cycle_default', async () => {
    const { resolveCompletenessExemption } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    const cases = [
      { completenessRmm: 'H' as const, completenessSpecial: false, cycle: 'L', projectOverride: null },
      { completenessRmm: null, completenessSpecial: true, cycle: 'L', projectOverride: null },
      { completenessRmm: null, completenessSpecial: false, cycle: 'L', projectOverride: null },
      { completenessRmm: null, completenessSpecial: false, cycle: 'E', projectOverride: null },
      { completenessRmm: null, completenessSpecial: false, cycle: 'L', projectOverride: { L: false } },
      { completenessRmm: null, completenessSpecial: false, cycle: 'B', projectOverride: null },
    ]
    for (const c of cases) {
      const r = resolveCompletenessExemption(c as any)
      expect(
        r.usingPlatformDefault,
        `source=${r.source} 时 usingPlatformDefault 应为 ${r.source === 'cycle_default'}`,
      ).toBe(r.source === 'cycle_default')
    }
  })

  it('cycle_override 时该标志恒为 false（已经本项目确认过）', async () => {
    const { resolveCompletenessExemption } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    for (const [cycle, v] of [
      ['L', false],
      ['E', true],
      ['D', false],
    ] as const) {
      const r = resolveCompletenessExemption({
        completenessRmm: null,
        completenessSpecial: false,
        cycle,
        projectOverride: { [cycle]: v },
      })
      expect(r.source).toBe('cycle_override')
      expect(r.usingPlatformDefault, 'cycle_override 时不得标注「使用平台默认」').toBe(false)
    }
  })

  it('结果恒含四键且 rationale 非空（复核视图要展示判据来源）', async () => {
    const { resolveCompletenessExemption } = await loadPure(
      P_EXEMPTION,
      '../completenessExemption',
      'Task 6',
    )
    const r = resolveCompletenessExemption({
      completenessRmm: null,
      completenessSpecial: false,
      cycle: 'L',
      projectOverride: null,
    })
    for (const k of ['exempt', 'source', 'usingPlatformDefault', 'rationale']) {
      expect(Object.keys(r), `返回值缺少键 ${k}`).toContain(k)
    }
    expect(typeof r.rationale).toBe('string')
    expect(r.rationale.length, 'rationale 不得为空').toBeGreaterThan(0)
  })
})
