/**
 * 裁剪汇总闸守卫（Wave 2 打红）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 5
 * Property 10（只计重要性类且按科目去重）/ 11（阈值方向）。
 *
 * ## 汇总闸为什么必须有守卫
 *
 * 准则要求「汇总考虑错报」：若干各自低于实际执行重要性的科目，其汇总错报可能远超
 * 实际执行重要性。三条约束都极易被「优化」掉且优化后功能看起来仍然正常：
 *
 * 1. **只计重要性类** —— 把 `no_data` 也纳入会让闸门在正常项目上恒亮（`no_data` 是
 *    自动裁、金额恒 0 或极小，纳入只增噪声不增信号），随后闸门会被当噪声关掉。
 * 2. **按科目去重** —— 同一科目往往有多个程序被同时建议裁剪，不去重会让合计虚高
 *    数倍，同样导致闸门被当误报关掉。
 * 3. **`>=` 而非 `>`** —— 恰好等于阈值时准则上已属"可能超过"，放过它就是放过边界。
 *
 * 三条都配变异检验（Task 22）。
 *
 * ## 类 A / 类 B
 *
 * 本文件的共享类 A 判据（`materiality` 表列、`TrimReasonCode` 快照等）在
 * `procedureTrimDecision.spec.ts`，此处不重复。本文件的类 A 只有 helper 自检与
 * 「阈值口径必须是 performance_materiality」这条源码级约束。
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
const P_GATE = path.join(FE, 'components', 'workpaper', 'composables', 'trimAggregateGate.ts')

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

/**
 * 🔴 specifier 必须是**变量**且带 `@vite-ignore`。
 *
 * 写成字面量 `await import('../trimAggregateGate')` 时，Vite 仍会在 **transform 期**
 * 静态解析该路径 —— 模块不存在即 `Failed to resolve import` ⇒ **整个文件 collection
 * error、零断言执行**（本守卫首轮实测：`assertions=0` 且只有一条文件级 message）。
 * 那种"全红"既可能是功能没做也可能是守卫写坏，恰是硬性约束 4 要禁的形态。
 *
 * 变量 specifier 让 Vite 无法静态求值，于是推迟到运行时 → `catch` 能接住 → 走
 * `pendingFail` 逐条打红，类 A 断言照常执行。
 */
const GATE_SPECIFIER = '../trimAggregateGate'

async function loadGate(): Promise<any> {
  if (!fs.existsSync(P_GATE)) pendingFail('模块 trimAggregateGate.ts', 'Task 8')
  try {
    return await import(/* @vite-ignore */ GATE_SPECIFIER)
  } catch (e) {
    pendingFail(`模块 trimAggregateGate.ts 无法加载（${String(e)}）`, 'Task 8')
  }
}

type Item = { accountName: string; amount: number; reasonCode: string }

// ═══════════════════════════════════════════════════════════════════════════
// helper 自检
// ═══════════════════════════════════════════════════════════════════════════
describe('helper 自检', () => {
  it('stripComments 剥注释保字面量', () => {
    const s = stripComments(`const a = 'below_trivial' // 注释里写 'no_data'`)
    expect(s).toContain("'below_trivial'")
    expect(s).not.toContain('注释里写')
  })

  it('本文件不得用字面量 specifier 动态 import 生产模块（否则整文件零断言）', () => {
    // 🔴 这条钉死本守卫首轮踩到的自身缺陷：`await import('../trimAggregateGate')`
    // 会被 Vite 在 transform 期静态解析，模块不存在 ⇒ collection error ⇒ 18 条断言
    // 一条都不执行，而报告里只看到"这个文件失败了"。改用变量 specifier 后才逐条打红。
    const self = stripComments(read(__filename.replace(/\.js$/, '.ts')))
    expect(
      /await\s+import\s*\(\s*['"]\.\.\//.test(self),
      '出现字面量 specifier 的动态 import —— 会让本文件在生产模块缺失时零断言执行',
    ).toBe(false)
    // 反向自检：确认扫描面非空（读到的确实是本文件源码）
    expect(self).toContain('GATE_SPECIFIER')
  })

  it('loadGate 对不存在的模块产生「尚未实现」红而非 collection error', async () => {
    if (fs.existsSync(P_GATE)) {
      // 已实现时该自检改为断言 loadGate 真能加载（不空转）
      await expect(loadGate()).resolves.toBeTruthy()
      return
    }
    await expect(loadGate()).rejects.toThrow(/尚未实现/)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 B：模块契约
// ═══════════════════════════════════════════════════════════════════════════
describe('[类 B] trimAggregateGate 模块契约', () => {
  it('导出 evaluateAggregateGate', async () => {
    const mod = await loadGate()
    expect(typeof mod.evaluateAggregateGate, 'evaluateAggregateGate 应为函数').toBe('function')
  })

  it('模块零 Vue 依赖、零 IO', () => {
    if (!fs.existsSync(P_GATE)) pendingFail('模块 trimAggregateGate.ts', 'Task 8')
    const src = stripComments(read(P_GATE))
    expect(/from\s+['"]vue['"]/.test(src), '不得依赖 vue').toBe(false)
    expect(/\bfetch\s*\(|axios|http\.get/.test(src), '不得含 IO').toBe(false)
  })

  it('返回值恒含六键', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const r = evaluateAggregateGate({ items: [], performanceMateriality: 1000 })
    for (const k of [
      'applicable',
      'distinctAccountCount',
      'totalAmount',
      'threshold',
      'blocked',
      'narrative',
    ]) {
      expect(Object.keys(r), `返回值缺少键 ${k}`).toContain(k)
    }
  })

  it('阈值口径是 performance_materiality（禁 overall / trivial 作汇总闸阈值）', () => {
    if (!fs.existsSync(P_GATE)) pendingFail('模块 trimAggregateGate.ts', 'Task 8')
    const src = stripComments(read(P_GATE))
    expect(
      /performanceMateriality/.test(src),
      '汇总闸阈值必须取实际执行重要性 performanceMateriality',
    ).toBe(true)
    // overall_materiality 是财报整体评价基准，不作单科目/汇总裁剪门槛
    expect(
      /overallMateriality|overall_materiality/.test(src),
      '汇总闸不得引用整体重要性',
    ).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 B：Property 10 — 只计重要性类 + 按科目去重
// ═══════════════════════════════════════════════════════════════════════════
describe('[类 B] Property 10: 只计重要性类且按科目去重', () => {
  it('no_data / 其他理由码不计入 totalAmount 与 distinctAccountCount', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const items: Item[] = [
      { accountName: '应收账款', amount: 100, reasonCode: 'below_materiality' },
      { accountName: '预付款项', amount: 9_000_000, reasonCode: 'no_data' },
      { accountName: '其他应收款', amount: 8_000_000, reasonCode: 'no_related_business' },
      { accountName: '存货', amount: 7_000_000, reasonCode: 'low_risk_assessment' },
    ]
    const r = evaluateAggregateGate({ items, performanceMateriality: 1000 })
    expect(r.totalAmount, '仅应计入 below_materiality 的 100').toBe(100)
    expect(r.distinctAccountCount, '仅应计 1 个科目').toBe(1)
    expect(r.blocked, '100 < 1000 不应阻断').toBe(false)
  })

  it('below_trivial 与 below_materiality 两类都计入', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const r = evaluateAggregateGate({
      items: [
        { accountName: 'A科目', amount: 300, reasonCode: 'below_trivial' },
        { accountName: 'B科目', amount: 400, reasonCode: 'below_materiality' },
      ],
      performanceMateriality: 10_000,
    })
    expect(r.totalAmount).toBe(700)
    expect(r.distinctAccountCount).toBe(2)
  })

  it('同一科目多条只计一次（同金额）', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const one = evaluateAggregateGate({
      items: [{ accountName: '应收账款', amount: 500, reasonCode: 'below_materiality' }],
      performanceMateriality: 10_000,
    })
    const five = evaluateAggregateGate({
      items: Array.from({ length: 5 }, () => ({
        accountName: '应收账款',
        amount: 500,
        reasonCode: 'below_materiality' as const,
      })),
      performanceMateriality: 10_000,
    })
    expect(five.totalAmount, '同科目 5 条不应变成 5 倍').toBe(one.totalAmount)
    expect(five.distinctAccountCount, '去重后应为 1').toBe(1)
  })

  it('去重后金额稳定：同科目不同金额时不得累加成和', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const r = evaluateAggregateGate({
      items: [
        { accountName: '应收账款', amount: 500, reasonCode: 'below_materiality' },
        { accountName: '应收账款', amount: 700, reasonCode: 'below_materiality' },
      ],
      performanceMateriality: 10_000,
    })
    expect(r.distinctAccountCount).toBe(1)
    expect(
      r.totalAmount,
      `同一科目两条不同金额应取其一（500 或 700），不得累加成 1200，实得 ${r.totalAmount}`,
    ).toBeLessThan(1200)
  })

  it('负金额按绝对值计入（贷方性质科目余额为负）', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const r = evaluateAggregateGate({
      items: [
        { accountName: '应付账款', amount: -600, reasonCode: 'below_materiality' },
        { accountName: '预收账款', amount: -400, reasonCode: 'below_trivial' },
      ],
      performanceMateriality: 1000,
    })
    expect(r.totalAmount, '应取绝对值合计 1000').toBe(1000)
    expect(r.blocked, '1000 >= 1000 应阻断').toBe(true)
  })

  it('items 为空时 totalAmount=0 且不阻断', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const r = evaluateAggregateGate({ items: [], performanceMateriality: 1000 })
    expect(r.totalAmount).toBe(0)
    expect(r.distinctAccountCount).toBe(0)
    expect(r.blocked).toBe(false)
  })

  it('源码级：去重与理由码过滤都真实存在（防写成裸 reduce 求和）', () => {
    if (!fs.existsSync(P_GATE)) pendingFail('模块 trimAggregateGate.ts', 'Task 8')
    const src = stripComments(read(P_GATE))
    expect(
      /new\s+Map|new\s+Set/.test(src),
      '未见去重结构（Map/Set）—— 裸 reduce 求和会让同科目多程序虚增合计',
    ).toBe(true)
    expect(
      /below_trivial/.test(src) && /below_materiality/.test(src),
      '未见重要性类理由码过滤',
    ).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 B：Property 11 — 阈值方向与重要性缺失
// ═══════════════════════════════════════════════════════════════════════════
describe('[类 B] Property 11: 汇总闸阈值方向', () => {
  it('恰好等于阈值时阻断（>= 而非 >）', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const r = evaluateAggregateGate({
      items: [{ accountName: 'A科目', amount: 1000, reasonCode: 'below_materiality' }],
      performanceMateriality: 1000,
    })
    expect(r.totalAmount).toBe(1000)
    expect(r.blocked, '恰好等于实际执行重要性时应阻断（判据须为 >=）').toBe(true)
  })

  it('略低于阈值不阻断，略高于阈值阻断', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const below = evaluateAggregateGate({
      items: [{ accountName: 'A科目', amount: 999.99, reasonCode: 'below_materiality' }],
      performanceMateriality: 1000,
    })
    const above = evaluateAggregateGate({
      items: [{ accountName: 'A科目', amount: 1000.01, reasonCode: 'below_materiality' }],
      performanceMateriality: 1000,
    })
    expect(below.blocked).toBe(false)
    expect(above.blocked).toBe(true)
  })

  it('blocked === true 当且仅当 threshold !== null && totalAmount >= threshold', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const grid: { amount: number; pm: number | null }[] = [
      { amount: 0, pm: 1000 },
      { amount: 999, pm: 1000 },
      { amount: 1000, pm: 1000 },
      { amount: 1001, pm: 1000 },
      { amount: 5000, pm: null },
      { amount: 0, pm: null },
    ]
    for (const g of grid) {
      const r = evaluateAggregateGate({
        items: [{ accountName: 'A科目', amount: g.amount, reasonCode: 'below_materiality' }],
        performanceMateriality: g.pm,
      })
      const want = r.threshold !== null && r.totalAmount >= r.threshold
      expect(
        r.blocked,
        `amount=${g.amount} pm=${g.pm} threshold=${r.threshold} total=${r.totalAmount} 时 blocked 应为 ${want}`,
      ).toBe(want)
    }
  })

  it('performanceMateriality === null ⟹ applicable=false 且 blocked=false（无比较基准）', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const r = evaluateAggregateGate({
      items: [
        { accountName: 'A科目', amount: 9_999_999, reasonCode: 'below_materiality' },
        { accountName: 'B科目', amount: 8_888_888, reasonCode: 'below_trivial' },
      ],
      performanceMateriality: null,
    })
    expect(r.applicable, '重要性缺失时闸门不适用').toBe(false)
    expect(r.blocked, '无阈值时不得阻断（不能凭空造一个基准）').toBe(false)
    expect(r.threshold, '无阈值时 threshold 应为 null').toBeNull()
  })

  it('有重要性时 applicable=true 且 threshold 等于传入值', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const r = evaluateAggregateGate({ items: [], performanceMateriality: 12345 })
    expect(r.applicable).toBe(true)
    expect(r.threshold).toBe(12345)
  })

  it('narrative 含判据数值（审计师要能看到合计与阈值）', async () => {
    const { evaluateAggregateGate } = await loadGate()
    const r = evaluateAggregateGate({
      items: [{ accountName: 'A科目', amount: 1500, reasonCode: 'below_materiality' }],
      performanceMateriality: 1000,
    })
    expect(typeof r.narrative).toBe('string')
    expect(r.narrative.length, 'narrative 不得为空').toBeGreaterThan(0)
    expect(/\d/.test(r.narrative), 'narrative 应含判据数值').toBe(true)
  })

  it('源码级：判据是 >= 且不得只与 trivialThreshold 比', () => {
    if (!fs.existsSync(P_GATE)) pendingFail('模块 trimAggregateGate.ts', 'Task 8')
    const src = stripComments(read(P_GATE))
    // 形态断言而非「标识符存在」—— 后者挡不住把条件改成 if (false)
    expect(
      />=/.test(src),
      '未见 >= 比较（判据方向：恰好等于阈值也应阻断）',
    ).toBe(true)
  })
})
