/**
 * g0SummaryMatrix.spec.ts — G0-1 品种矩阵守卫
 *
 * spec: g0-confirmation-source-alignment，Task 5/6
 * Property 4（SUMIF 口径，含 PBT）/ 5（分母 0 返 null）/ 5.1（可见性无死锁）/ 5.2（自定义品种）
 *        / 6（手工优先）/ 7（**与 F0 同源** + F0/E0 未被改动 + CONVERGENCE_TARGET）
 *        / 10（品种 rowCode 与后端 g_cycle_specs.py 交叉锁死）/ 11（科目码不进请求参数）
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import fc from 'fast-check'
import { describe, expect, it } from 'vitest'

import {
  CONVERGENCE_TARGET,
  G0_BOOK_AMOUNT_WP_CODES,
  G0_CATEGORY_NAMES,
  G0_CUSTOM_CATEGORY_HINT,
  G0_MATRIX_CATEGORIES,
  G0_MATRIX_LABELS,
  G0_MATRIX_METRICS,
  buildG0SummaryMatrix,
  extractG0BookAmount,
  fetchG0BookAmounts,
  getG0MatrixRow,
  hasG0CategoryContent,
  safeRatio,
  sumByCategory,
  visibleG0Categories,
} from '../g0SummaryMatrix'
import { g0MatrixOverrideItemId, parseG0ManualOverrides } from '../g0MatrixDataSources'
import {
  F0_MATRIX_LABELS,
  buildF0SummaryMatrix,
} from '../../confirmation/composables/f0SummaryAggregation'
import type { ConfirmationRow } from '../../confirmation/confirmationTypes'

// 🔴 本文件位于 src/components/workpaper/g0-confirmation/__tests__/ → 回退 6 级到仓库根
//    （src → components → workpaper → g0-confirmation → __tests__ 共 5 段 + frontend/audit-platform）
//    实测得出，不照抄其它目录下的守卫层数。
const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function row(account_type: string, amount?: number, confirmed_amount?: number, alt_confirmed?: number): ConfirmationRow {
  return { account_type, amount, confirmed_amount, alt_confirmed } as ConfirmationRow
}

// ─── Property 4: SUMIF 口径 ──────────────────────────────────────────────────

describe('Property 4: 金额指标 = 按品种 SUMIF（对齐源模板）', () => {
  it('三个金额指标分别聚合 amount / confirmed_amount / alt_confirmed', () => {
    const rows = [
      row('债权投资', 100, 90, 5),
      row('债权投资', 200, 150, 0),
      row('长期股权投资', 50, 50, 0),
    ]
    const m = buildG0SummaryMatrix({ rows, categories: ['债权投资'] })
    const byKey = new Map(m[0].map((c) => [c.metric, c.value]))
    expect(byKey.get('send_amount')).toBe(300)
    expect(byKey.get('reply_confirmed')).toBe(240)
    expect(byKey.get('alt_confirmed')).toBe(5)
  })

  it('其它品种的行不参与本品种聚合', () => {
    const rows = [row('长期股权投资', 999, 999, 999)]
    const m = buildG0SummaryMatrix({ rows, categories: ['债权投资'] })
    const byKey = new Map(m[0].map((c) => [c.metric, c.value]))
    expect(byKey.get('send_amount')).toBe(0)
  })

  it('PBT: 各品种发函金额之和 == 全部行金额之和（无遗漏无重复）', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            cat: fc.constantFrom(...G0_CATEGORY_NAMES),
            amt: fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
          }),
          { maxLength: 40 },
        ),
        (specs) => {
          const rows = specs.map((s) => row(s.cat, Math.round(s.amt * 100) / 100))
          const matrix = buildG0SummaryMatrix({ rows })
          const perCat = getG0MatrixRow(matrix, 'send_amount').reduce((a, c) => a + (c.value ?? 0), 0)
          const total = rows.reduce((a, r) => a + (r.amount ?? 0), 0)
          expect(Math.abs(perCat - total)).toBeLessThanOrEqual(0.05)
        },
      ),
      { numRuns: 60 },
    )
  })

  it('反向自检：去掉品种过滤则各品种值之和必不等于逐品种值', () => {
    const rows = [row('债权投资', 100), row('长期股权投资', 200)]
    const filtered = sumByCategory(rows, '债权投资', 'amount')
    const unfiltered = rows.reduce((a, r) => a + (r.amount ?? 0), 0)
    expect(filtered).not.toBe(unfiltered)
  })

  it('非数值 / 缺失金额不进求和（不产出 NaN）', () => {
    const rows = [row('债权投资'), { account_type: '债权投资', amount: 'x' } as unknown as ConfirmationRow]
    expect(sumByCategory(rows, '债权投资', 'amount')).toBe(0)
  })
})

// ─── Property 5: 分母缺失或为 0 → null ───────────────────────────────────────

describe('Property 5: 分母缺失或为 0 时返回 null，绝不 NaN/Infinity/0 冒充', () => {
  it('账面金额缺失 → 三个占账面比例为 null', () => {
    const m = buildG0SummaryMatrix({ rows: [row('债权投资', 100, 90, 5)], categories: ['债权投资'] })
    const byKey = new Map(m[0].map((c) => [c.metric, c.value]))
    expect(byKey.get('book_amount')).toBeNull()
    expect(byKey.get('send_ratio')).toBeNull()
    expect(byKey.get('reply_over_book')).toBeNull()
    expect(byKey.get('reply_alt_over_book')).toBeNull()
  })

  it('账面金额为 0 → 比例为 null（不是 0 也不是 Infinity）', () => {
    const m = buildG0SummaryMatrix({
      rows: [row('债权投资', 100, 90, 5)],
      bookAmounts: { 债权投资: 0 },
      categories: ['债权投资'],
    })
    const byKey = new Map(m[0].map((c) => [c.metric, c.value]))
    expect(byKey.get('send_ratio')).toBeNull()
  })

  it('发函金额为 0 → 回函占发函比例为 null', () => {
    const m = buildG0SummaryMatrix({ rows: [], bookAmounts: { 债权投资: 100 }, categories: ['债权投资'] })
    const byKey = new Map(m[0].map((c) => [c.metric, c.value]))
    expect(byKey.get('reply_over_send')).toBeNull()
  })

  it('全矩阵不含 NaN / Infinity', () => {
    const m = buildG0SummaryMatrix({
      rows: [row('债权投资', 0, 0, 0)],
      bookAmounts: { 债权投资: 0, 长期股权投资: undefined },
    })
    for (const cells of m) for (const c of cells) {
      if (c.value !== null) expect(Number.isFinite(c.value)).toBe(true)
    }
  })

  it('safeRatio 边界', () => {
    expect(safeRatio(1, 0)).toBeNull()
    expect(safeRatio(undefined, 1)).toBeNull()
    expect(safeRatio(1, undefined)).toBeNull()
    expect(safeRatio(1, 2)).toBe(0.5)
  })
})

// ─── Property 6: 手工优先 ────────────────────────────────────────────────────

describe('Property 6: 手工值优先于自动取数，且只对 editable 指标生效', () => {
  it('账面金额行手工值覆盖自动取数并标 isManual', () => {
    const m = buildG0SummaryMatrix({
      rows: [],
      bookAmounts: { 债权投资: 100 },
      manualOverrides: { '债权投资::book_amount': 555 },
      categories: ['债权投资'],
    })
    const cell = m[0].find((c) => c.metric === 'book_amount')!
    expect(cell.value).toBe(555)
    expect(cell.isManual).toBe(true)
    expect(cell.sourceHint).toContain('手工填写')
  })

  it('非 editable 指标的手工覆盖不生效', () => {
    const m = buildG0SummaryMatrix({
      rows: [row('债权投资', 100)],
      manualOverrides: { '债权投资::send_amount': 999 },
      categories: ['债权投资'],
    })
    const cell = m[0].find((c) => c.metric === 'send_amount')!
    expect(cell.value).toBe(100)
    expect(cell.isManual).toBe(false)
  })

  it('只有账面金额行 editable', () => {
    expect(G0_MATRIX_METRICS.filter((m) => m.editable).map((m) => m.key)).toEqual(['book_amount'])
  })
})

// ─── Property 5.1: 可见性「有就显示没有隐藏」且无死锁 ────────────────────────

describe('Property 5.1: 品种可见性（裁决门 A）', () => {
  it('grid 有该品种行 → 可见', () => {
    expect(hasG0CategoryContent('债权投资', { rows: [row('债权投资', 1)] })).toBe(true)
  })

  it('取到账面金额 → 可见（即使 grid 无行）', () => {
    expect(hasG0CategoryContent('债权投资', { rows: [], bookAmounts: { 债权投资: 100 } })).toBe(true)
  })

  it('账面金额为 0 也算「有内容」（0 是实证值，不是缺失）', () => {
    expect(hasG0CategoryContent('债权投资', { rows: [], bookAmounts: { 债权投资: 0 } })).toBe(true)
  })

  it('有手工值 → 可见', () => {
    expect(
      hasG0CategoryContent('债权投资', { rows: [], manualOverrides: { '债权投资::book_amount': 1 } }),
    ).toBe(true)
  })

  it('三者皆无 → 不可见', () => {
    expect(hasG0CategoryContent('债权投资', { rows: [row('长期股权投资', 1)] })).toBe(false)
  })

  it('部分品种有内容 → 只显示有内容的', () => {
    const visible = visibleG0Categories({
      rows: [row('债权投资', 1)],
      bookAmounts: { 长期股权投资: 50 },
    })
    expect(visible).toEqual(['长期股权投资', '债权投资'])
  })

  it('🔴 一个品种都没有内容 → 返回全部候选（防空白区 + 防录入死锁）', () => {
    const visible = visibleG0Categories({ rows: [] })
    expect(visible).toEqual([...G0_CATEGORY_NAMES])
    expect(visible.length).toBe(8)
  })

  it('showAll=true → 返回全部候选', () => {
    const visible = visibleG0Categories({ rows: [row('债权投资', 1)], showAll: true })
    expect(visible).toEqual([...G0_CATEGORY_NAMES])
  })

  it('反向自检：若无「全无内容→返全部」分支，空底稿必返空数组（死锁复现）', () => {
    const naive = [...G0_CATEGORY_NAMES].filter((c) => hasG0CategoryContent(c, { rows: [] }))
    expect(naive).toEqual([])
    // 实现必须不等于这个朴素版本
    expect(visibleG0Categories({ rows: [] })).not.toEqual(naive)
  })

  it('隐藏不丢已录入值 —— 被隐藏品种的手工值仍参与计算', () => {
    const input = { rows: [row('债权投资', 1)], manualOverrides: { '交易性金融负债::book_amount': 777 } }
    // 交易性金融负债 有手工值 → 其实可见
    expect(visibleG0Categories(input)).toContain('交易性金融负债')
    const m = buildG0SummaryMatrix({ ...input, categories: ['交易性金融负债'] })
    expect(m[0].find((c) => c.metric === 'book_amount')!.value).toBe(777)
  })
})

// ─── Property 5.2: 自定义品种可扩展 ──────────────────────────────────────────

describe('Property 5.2: 自定义品种（源 H20 的 `……` 可扩位）', () => {
  it('名称与 grid account_type 一致 → 参与聚合', () => {
    const m = buildG0SummaryMatrix({
      rows: [row('结构性存款', 300, 300, 0)],
      categories: ['结构性存款'],
    })
    expect(m[0].find((c) => c.metric === 'send_amount')!.value).toBe(300)
  })

  it('名称不一致 → 金额指标为 0（不报错）', () => {
    const m = buildG0SummaryMatrix({ rows: [row('结构性存款', 300)], categories: ['结构性存款 '] })
    expect(m[0].find((c) => c.metric === 'send_amount')!.value).toBe(0)
  })

  it('自定义品种无账面取数口径 → 提示手工填写', () => {
    const m = buildG0SummaryMatrix({ rows: [], categories: ['结构性存款'] })
    expect(m[0].find((c) => c.metric === 'book_amount')!.sourceHint).toContain('手工填写')
  })

  it('该前提有明示文案', () => {
    expect(G0_CUSTOM_CATEGORY_HINT).toContain('账户/交易')
    expect(G0_CUSTOM_CATEGORY_HINT.length).toBeGreaterThanOrEqual(20)
  })
})

// ─── Property 7: 与 F0 同源 + F0/E0 未被改动 + 收敛锚点 ──────────────────────

describe('Property 7: G0 矩阵与 F0 矩阵同源（D-2 的分叉对冲）', () => {
  it('8 个指标 label 与 F0 逐字相同', () => {
    expect([...G0_MATRIX_LABELS]).toEqual([...F0_MATRIX_LABELS])
  })

  /**
   * 🔴 已实证的**结构**差异（收敛 spec 的设计输入，非算法分叉）：
   * F0 的 `F0MatrixCell` 用 `metric` 字段直接存**label 文本**（`metric: F0Metric` 即中文标签），
   * 没有独立 `label` 字段；G0 的 `G0MatrixCell` 是 `metric`（稳定 key）+ `label`（文本）两字段。
   * G0 的形态更稳（改文案不会改 key），收敛时应以 G0 形态为目标。
   * 本守卫因此比对 `g0.label` ↔ `f0.metric`，并在下方显式断言该差异仍然存在 ——
   * 一旦 F0 也改成 key+label 形态，本断言会打红提醒收敛已可推进。
   */
  it('F0 仍是 label-as-key 形态（收敛目标：改成 G0 的 key+label）', () => {
    const f0 = buildF0SummaryMatrix({ rows: [], bookAmounts: {} })[0]
    expect(f0[0]).not.toHaveProperty('label')
    expect(F0_MATRIX_LABELS).toContain(f0[0].metric as unknown as string)
  })

  it('对同一输入，8 指标的 label/kind/editable/value 逐字节相同', () => {
    // F0 品种「应付账款」与 G0 品种「债权投资」各自作为品种名，行数据同构
    const g0Rows = [row('债权投资', 1000, 800, 150), row('债权投资', 500, 400, 50)]
    const f0Rows = [row('应付账款', 1000, 800, 150), row('应付账款', 500, 400, 50)]

    const g0 = buildG0SummaryMatrix({ rows: g0Rows, bookAmounts: { 债权投资: 2000 }, categories: ['债权投资'] })[0]
    const f0 = buildF0SummaryMatrix({ rows: f0Rows, bookAmounts: { 应付账款: 2000 } })
      .find((cells) => cells[0].category === '应付账款')!

    expect(g0).toHaveLength(8)
    expect(f0).toHaveLength(8)
    for (let i = 0; i < 8; i++) {
      expect(g0[i].label, `指标 ${i} label 漂移`).toBe(f0[i].metric as unknown as string)
      expect(g0[i].kind, `指标 ${i} kind 漂移`).toBe(f0[i].kind)
      expect(g0[i].editable, `指标 ${i} editable 漂移`).toBe(f0[i].editable)
      expect(g0[i].value, `指标 ${i} value 漂移（算法分叉）`).toBe(f0[i].value)
    }
  })

  it('分母 0 的行为也一致（两侧同返 null）', () => {
    const g0 = buildG0SummaryMatrix({ rows: [row('债权投资', 100, 90, 5)], bookAmounts: { 债权投资: 0 }, categories: ['债权投资'] })[0]
    const f0 = buildF0SummaryMatrix({ rows: [row('应付账款', 100, 90, 5)], bookAmounts: { 应付账款: 0 } })
      .find((cells) => cells[0].category === '应付账款')!
    for (let i = 0; i < 8; i++) expect(g0[i].value).toBe(f0[i].value)
  })

  it('反向自检：把某比例改成分母 0 返 0 则同源断言必红', () => {
    // 模拟分叉：分母 0 返 0（而非 null）
    const forked = (n: number | null, d: number | null) => (d === 0 ? 0 : safeRatio(n, d))
    expect(forked(1, 0)).toBe(0)
    expect(safeRatio(1, 0)).toBeNull()
    expect(forked(1, 0)).not.toBe(safeRatio(1, 0))
  })

  it('收敛锚点已声明（收敛 spec 靠 grep 定位副本）', () => {
    expect(CONVERGENCE_TARGET).toBe('confirmation-summary-matrix-convergence')
  })

  it('F0 / E0 / E0LowerZone 未被本 spec 改动（导出符号集合与基线一致）', () => {
    const baseline = JSON.parse(
      readFileSync(resolve(__dirname, '__snapshots__/g0Baseline.json'), 'utf-8'),
    )
    const f0Src = readFileSync(
      resolve(__dirname, '../../confirmation/composables/f0SummaryAggregation.ts'),
      'utf-8',
    )
    const e0Src = readFileSync(resolve(__dirname, '../../confirmation/e0SummaryMatrix.ts'), 'utf-8')
    // 只取运行时符号（const / function）—— interface / type 不影响行为
    const names = (src: string) =>
      [...src.matchAll(/^export (?:const|function)\s+(\w+)/gm)].map((m) => m[1]).sort()
    expect(names(f0Src)).toEqual(baseline.f0MatrixExports)
    expect(names(e0Src)).toEqual(baseline.e0MatrixExports)
    expect(baseline.convergenceTargets.matrix).toBe(CONVERGENCE_TARGET)
  })
})

// ─── Property 10: 品种 rowCode 与后端 g_cycle_specs.py 交叉锁死 ──────────────

describe('Property 10: 品种账面取数口径与后端声明双向锁死', () => {
  const specSrc = readFileSync(
    resolve(REPO_ROOT, 'backend/app/services/four_table/g_cycle_specs.py'),
    'utf-8',
  )

  it('REPO_ROOT 解析正确（防层数写错导致断言空转）', () => {
    expect(specSrc.length).toBeGreaterThan(500)
    // 该文件用 semantic_account_resolver 的 SemanticAccountSpec 声明各 G 循环规格
    expect(specSrc).toContain('SemanticAccountSpec')
    expect(specSrc).toContain('row_code')
  })

  it('每个品种的 rowCode 都在后端 g_cycle_specs.py 中出现', () => {
    for (const cat of G0_MATRIX_CATEGORIES) {
      expect(specSrc, `${cat.name} 的 ${cat.book.rowCode} 未在后端声明`).toContain(cat.book.rowCode)
    }
  })

  it('8 个品种 rowCode 互不重复（防两品种认领同一报表行 → 双算）', () => {
    const codes = G0_MATRIX_CATEGORIES.map((c) => c.book.rowCode)
    expect(new Set(codes).size).toBe(codes.length)
  })

  it('账面来源 wp_code 覆盖 8 个 G 循环', () => {
    expect([...G0_BOOK_AMOUNT_WP_CODES].sort()).toEqual(
      ['G1', 'G10', 'G4', 'G5', 'G6', 'G7', 'G8', 'G9'].sort(),
    )
  })

  it('候选品种恰 8 个且名称唯一', () => {
    expect(G0_MATRIX_CATEGORIES).toHaveLength(8)
    expect(new Set(G0_CATEGORY_NAMES).size).toBe(8)
  })

  it('前 3 个品种的 source_ref 指向源模板 G0-1，后 5 个指向 G0A', () => {
    const refs = G0_MATRIX_CATEGORIES.map((c) => c.source_ref)
    expect(refs.slice(0, 3)).toEqual(['G0-1!E20', 'G0-1!F20', 'G0-1!G20'])
    expect(refs.slice(3)).toEqual(Array(5).fill('G0A!B7'))
  })
})

// ─── Property 11: 科目码不参与运行态取数 ────────────────────────────────────

describe('Property 11: 科目码只作展示，不进请求参数/事件载荷', () => {
  const src = readFileSync(resolve(__dirname, '../g0SummaryMatrix.ts'), 'utf-8')

  /** 去注释（块注释 + 行注释），保留字符串 */
  function stripComments(s: string): string {
    return s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
  }

  it('stripComments 自检（对内联 fixture 有效）', () => {
    const fixture = "const a = 1 // 注释里的 1101\n/* 块注释 1502 */\nconst b = 'keep 1101'"
    const out = stripComments(fixture)
    expect(out).toContain("'keep 1101'")
    expect(out).not.toContain('块注释')
    expect(out).not.toContain('注释里的')
  })

  it('去注释后科目码只出现在 hint 字符串内', () => {
    const code = stripComments(src)
    // 逐个科目码：出现的每一行都必须是 hint 声明行
    for (const account of ['1101', '1511', '1504', '1531', '1506', '1507', '1519', '2101']) {
      const lines = code.split('\n').filter((l) => l.includes(account))
      for (const l of lines) {
        expect(l, `科目码 ${account} 出现在非 hint 行: ${l.trim()}`).toContain('hint:')
      }
    }
  })

  it('模块不含请求/事件相关调用（取数由调用方注入 render-config 结果）', () => {
    const code = stripComments(src)
    for (const banned of ['api.', 'fetch(', 'axios', 'eventBus', '$emit', 'account_code']) {
      expect(code, `不应出现 ${banned}`).not.toContain(banned)
    }
  })

  it('反向自检：原始源码确实含科目码（否则上条断言空转）', () => {
    expect(src).toContain('1101')
    expect(src).toContain('2101')
  })
})

// ─── 取数纯函数 ──────────────────────────────────────────────────────────────

describe('fetchG0BookAmounts', () => {
  it('从相邻循环 render-config 取 project_context.tb_amount', () => {
    const out = fetchG0BookAmounts({
      G1: { project_context: { tb_amount: 1234.56 } },
      G7: { project_context: { tb_amount: 0 } },
    })
    expect(out['交易性金融资产']).toBe(1234.56)
    expect(out['长期股权投资']).toBe(0)
  })

  it('缺失 / 非数值 → 不落键（undefined ≠ 0）', () => {
    const out = fetchG0BookAmounts({
      G4: undefined,
      G5: { project_context: {} },
      G6: { project_context: { tb_amount: 'x' } },
    })
    expect('债权投资' in out).toBe(false)
    expect('长期应收款' in out).toBe(false)
    expect('其他债权投资' in out).toBe(false)
  })
})

/**
 * Task 23 浏览器/真实库实测抓到的缺陷 —— 账面金额键名在 G1..G10 不统一。
 *
 * 下面 5 个 fixture 全部**逐字取自真实库**（项目 2aa00f57 / 2025，
 * `backend` 直读 render-config，见 tasks.md Task 23 实测表）。
 */
describe('extractG0BookAmount：G1..G10 键名不统一（真实库实测形态）', () => {
  /** G7 实测：只有 tb_values，且有真实金额 */
  const G7_LIVE = {
    tb_values: {
      opening: 40459060.6,
      closing: 40459060.6,
      impairment: 4790032.97,
      source_codes: { gross: ['1511.01'], impairment: ['1512'] },
    },
    project_context: {
      account_code: '1511',
      tb_source_codes: { resolved_from: 'account_chart_client', gross: ['1511.01'] },
    },
  }
  /** G1/G4/G8/G9/G10 实测：tb_amount 是**字面 0**，而 resolved_from='none' */
  const G1_LIVE = {
    tb_values: {},
    project_context: {
      tb_amount: 0,
      tb_source_codes: { resolved_from: 'none', gross: [], chart_available: true },
    },
  }
  /** G5/G6 实测：压根没有 tb_amount，tb_source_codes 在 html_data 顶层 */
  const G5_LIVE = {
    tb_values: {},
    tb_source_codes: { resolved_from: 'none', gross: [], chart_available: true },
    project_context: { account_code: '1531' },
  }

  it('G7 形态：取 tb_values.closing（此前只读 tb_amount → 真实金额被漏掉）', () => {
    expect(extractG0BookAmount(G7_LIVE)).toEqual({
      kind: 'value',
      amount: 40459060.6,
      source: 'tb_values.closing',
    })
  })

  it('G1 形态：resolved_from=none + gross 空 ⇒ absent，绝不采信字面 0', () => {
    expect(extractG0BookAmount(G1_LIVE)).toEqual({ kind: 'absent' })
  })

  it('G5/G6 形态：tb_source_codes 在 html_data 顶层也要认', () => {
    expect(extractG0BookAmount(G5_LIVE)).toEqual({ kind: 'absent' })
  })

  it('科目存在且余额为 0 ⇒ value 0（与 absent 必须可区分）', () => {
    const state = extractG0BookAmount({
      tb_values: { closing: 0 },
      project_context: { tb_source_codes: { resolved_from: 'account_chart_client', gross: ['1101'] } },
    })
    expect(state).toEqual({ kind: 'value', amount: 0, source: 'tb_values.closing' })
  })

  it('无 html_data / 空对象 ⇒ unknown（既非 absent 也非 0）', () => {
    expect(extractG0BookAmount(undefined)).toEqual({ kind: 'unknown' })
    expect(extractG0BookAmount({})).toEqual({ kind: 'unknown' })
    expect(extractG0BookAmount({ project_context: { tb_amount: '' } })).toEqual({ kind: 'unknown' })
  })

  it('兼容回退：只有 project_context.tb_amount 且科目已解析 ⇒ 用它', () => {
    expect(
      extractG0BookAmount({
        project_context: {
          tb_amount: 88,
          tb_source_codes: { resolved_from: 'report_config', gross: ['1101'] },
        },
      }),
    ).toEqual({ kind: 'value', amount: 88, source: 'project_context.tb_amount' })
  })

  it('反向自检：朴素实现（只读 tb_amount）会把 G7 漏掉、把 G1 的 0 当真值', () => {
    const naive = (hd: any) => {
      const raw = hd?.project_context?.tb_amount
      return raw != null && raw !== '' && Number.isFinite(Number(raw)) ? Number(raw) : undefined
    }
    expect(naive(G7_LIVE)).toBeUndefined() // 真实 4 千万被漏
    expect(naive(G1_LIVE)).toBe(0) // 无此科目被伪装成余额 0
  })

  it('fetchG0BookAmounts 用同一规则：G7 取到、G1 不落键', () => {
    const out = fetchG0BookAmounts({ G7: G7_LIVE, G1: G1_LIVE, G5: G5_LIVE })
    expect(out['长期股权投资']).toBe(40459060.6)
    expect('交易性金融资产' in out).toBe(false)
    expect('长期应收款' in out).toBe(false)
  })
})

// ─── Task 7: 取数编排 + 手工覆盖键（g0MatrixDataSources） ────────────────────

describe('Task 7: g0MatrixDataSources', () => {
  const dsSrc = readFileSync(resolve(__dirname, '../g0MatrixDataSources.ts'), 'utf-8')

  it('🔴 用 apiProxy 的 api，不用 utils/http（F0 那轮实测的 P0）', () => {
    expect(dsSrc).toContain("from '@/services/apiProxy'")
    expect(dsSrc).not.toMatch(/from\s+'@\/utils\/http'/)
  })

  it('八个品种的 wp_code 各不相同 → 并行请求不会被 http 去重 abort', () => {
    const wpCodes = G0_MATRIX_CATEGORIES.map((c) => c.book.wpCode)
    expect(new Set(wpCodes).size).toBe(wpCodes.length)
  })

  const matrixSrc = readFileSync(resolve(__dirname, '../g0SummaryMatrix.ts'), 'utf-8')
  /** 🔴 去注释后再断言 —— 本模块头的说明表里就写着 `project_context.tb_amount` */
  const stripped = (s: string) =>
    s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')

  it('取数走共享三态提取器，不在编排层自己读 tb_amount（防两处规则漂移）', () => {
    expect(dsSrc).toContain('extractG0BookAmount')
    // 编排层不得再出现「直接读 project_context.tb_amount」的旁路
    expect(stripped(dsSrc)).not.toMatch(/project_context\??\.\s*tb_amount/)
  })

  it('反向自检：去注释确实生效（原文注释里含该字样，去注释后消失）', () => {
    expect(dsSrc).toMatch(/project_context\.tb_amount/)
    expect(stripped(dsSrc)).not.toMatch(/project_context\.tb_amount/)
  })

  it('取值时先排除 null/空串（Number(null)===0 会造假 0）—— 规则在矩阵模块', () => {
    expect(matrixSrc).toContain("raw == null || raw === ''")
  })

  it('缺失品种进 bookMissing 而非落 0 键；absent 另有专列', () => {
    expect(dsSrc).toContain('bookMissing.push')
    expect(dsSrc).toContain('bookAbsent.push')
    expect(dsSrc).not.toMatch(/bookAmounts\[[^\]]+\]\s*=\s*0/)
  })

  it('逐 sheet 找最有信息量的状态，不取首个 sheet 就返回（G4/G6/G7 有无 html_data 的 sheet）', () => {
    expect(dsSrc).toMatch(/for \(const sheet of sheets\)/)
    expect(dsSrc).toContain("if (state.kind === 'value') return state")
  })

  it('取数错误如实进 diagnostics.errors（不静默吞）', () => {
    expect(dsSrc).toContain('diagnostics.errors.push')
  })

  it('手工覆盖 item_id 用指标 key 而非中文 label（改文案不丢数据）', () => {
    expect(g0MatrixOverrideItemId('债权投资', 'book_amount')).toBe('G0-1-matrix-债权投资-book_amount')
    expect(g0MatrixOverrideItemId('债权投资', 'book_amount')).not.toContain('账面金额')
  })

  it('parseG0ManualOverrides 支持 Map 与普通对象两种形态', () => {
    const id = g0MatrixOverrideItemId('债权投资', 'book_amount')
    const fromMap = parseG0ManualOverrides(new Map([[id, { value: '1234.5' }]]))
    const fromObj = parseG0ManualOverrides({ [id]: { remark: 1234.5 } })
    expect(fromMap['债权投资::book_amount']).toBe(1234.5)
    expect(fromObj['债权投资::book_amount']).toBe(1234.5)
  })

  it('parseG0ManualOverrides 忽略空值与非数值，且只解析可编辑指标', () => {
    const idEditable = g0MatrixOverrideItemId('债权投资', 'book_amount')
    const idDerived = g0MatrixOverrideItemId('债权投资', 'send_amount')
    const out = parseG0ManualOverrides({
      [idEditable]: { value: '' },
      [idDerived]: { value: '999' },
      [g0MatrixOverrideItemId('长期股权投资', 'book_amount')]: { value: 'abc' },
    })
    expect(out).toEqual({})
  })

  it('parseG0ManualOverrides 支持自定义品种', () => {
    const id = g0MatrixOverrideItemId('结构性存款', 'book_amount')
    const out = parseG0ManualOverrides({ [id]: { value: 88 } }, ['结构性存款'])
    expect(out['结构性存款::book_amount']).toBe(88)
  })

  it('解析出的键可直接喂给 buildG0SummaryMatrix', () => {
    const id = g0MatrixOverrideItemId('债权投资', 'book_amount')
    const overrides = parseG0ManualOverrides({ [id]: { value: 4242 } })
    const m = buildG0SummaryMatrix({ rows: [], manualOverrides: overrides, categories: ['债权投资'] })
    expect(m[0].find((c) => c.metric === 'book_amount')!.value).toBe(4242)
  })
})
