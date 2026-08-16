/**
 * l0SummaryMatrix.spec.ts — L0-1 矩阵守卫
 *
 * spec: l0-confirmation-source-alignment，Task 13
 *   Property 8（矩阵结构与源模板一致）
 *   Property 9（与 F0 同源，防收敛前漂移）
 *   Property 10（比例列按源模板 ISERROR 兜底）
 *   Property 12（三态可区分）
 *   Property 13（手工覆盖键用指标 key 构键）
 *
 * 🔴 `REPO_ROOT` 用**双哨兵具体文件**向上查找 —— 写死回退级数会在目录层级变化时
 * 静默解析到错误路径（表现为**文件级** ENOENT 失败而非断言失败，极易被当噪声跳过）。
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  CONVERGENCE_TARGET,
  L0_MATRIX_CATEGORIES,
  L0_MATRIX_CATEGORY_NAMES,
  L0_MATRIX_LABELS,
  L0_MATRIX_LABEL_HEADER,
  L0_MATRIX_METRICS,
  buildL0SummaryMatrix,
  pickL0MatrixCell,
  type L0MetricKey,
} from '../l0SummaryMatrix'
import {
  L0_BOOK_STATE_TEXT,
  L0_MATRIX_KEY_PREFIX,
  bookAmountOverrideItemId,
  buildL0BookAmountViews,
  buildL0MatrixDiagnostics,
  hasL0MatrixDiagnostics,
  matrixOverrideItemId,
  readL0BookAmounts,
} from '../l0MatrixDataSources'

// ─── REPO_ROOT：双哨兵具体文件向上查找 ─────────────────────────────────────

function findRepoRoot(): string {
  // 两个哨兵**具体文件**（不是目录 —— `audit-platform/backend/app/routers`
  // 是历史遗留空目录，会让向上查找提前停下）
  const sentinels = [
    path.join('backend', 'app', 'services', 'four_table', 'l_cycle_specs.py'),
    path.join('backend', 'wp_templates', 'L', 'L0 债务循环函证.xlsx'),
  ]
  let dir = process.cwd()
  for (let i = 0; i < 12; i += 1) {
    if (sentinels.every((s) => fs.existsSync(path.join(dir, s)))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未找到仓库根（双哨兵均存在的目录）；cwd=${process.cwd()}`)
}

const REPO_ROOT = findRepoRoot()

// ─── Property 8：矩阵结构与源模板一致 ──────────────────────────────────────

describe('Property 8: 矩阵结构与源模板一致', () => {
  it('恰 2 品种，顺序与源模板 E29/F29 一致', () => {
    expect(L0_MATRIX_CATEGORY_NAMES).toEqual(['长期应付款', '应付债券'])
    expect(L0_MATRIX_CATEGORIES).toHaveLength(2)
  })

  it('恰 8 指标，label 逐字取自源 C30:C37（去行尾冒号）', () => {
    expect(L0_MATRIX_LABELS).toEqual([
      '本期（期末）账面金额',
      '抽取样本的发函金额',
      '发函金额占账面金额的比例(%)',
      '回函确认金额',
      '回函可确认金额占发函金额的比例(%)',
      '回函可确认金额占账面金额的比例(%)',
      '替代测试确认金额',
      '回函和替代确认金额占账面金额的比例(%)',
    ])
  })

  it('kind 序列 = [amount, amount, ratio, amount, ratio, ratio, amount, ratio]', () => {
    expect(L0_MATRIX_METRICS.map((m) => m.kind)).toEqual([
      'amount', 'amount', 'ratio', 'amount', 'ratio', 'ratio', 'amount', 'ratio',
    ])
  })

  it('仅 book_amount 可手填（源模板该行无公式）', () => {
    const editable = L0_MATRIX_METRICS.filter((m) => m.editable).map((m) => m.key)
    expect(editable).toEqual(['book_amount'])
  })

  it('三个金额类指标的 sum 字段对应源模板 SUMIF 的 sum_range（F/U/Y 列）', () => {
    const byKey = new Map(L0_MATRIX_METRICS.map((m) => [m.key, m]))
    expect(byKey.get('send_amount')?.sum).toBe('amount')          // 源 F 列
    expect(byKey.get('reply_confirmed')?.sum).toBe('confirmed_amount')  // 源 U 列
    expect(byKey.get('alt_confirmed')?.sum).toBe('alt_confirmed')  // 源 Y 列
  })

  it('末行分子 = 替代 + 回函（源 R37 =(R36+R33)/R30）', () => {
    const last = L0_MATRIX_METRICS[L0_MATRIX_METRICS.length - 1]
    expect(last.key).toBe('reply_alt_over_book')
    expect(last.ratio).toEqual({ num: ['alt_confirmed', 'reply_confirmed'], den: 'book_amount' })
  })

  it('标签列头 = 源 C29「项目」', () => {
    expect(L0_MATRIX_LABEL_HEADER).toBe('项目')
  })

  it('每个指标与品种都带 source_ref 锚点', () => {
    for (const m of L0_MATRIX_METRICS) expect(m.source_ref).toMatch(/^L0-1!C3[0-7]$/)
    expect(L0_MATRIX_CATEGORIES.map((c) => c.source_ref)).toEqual(['L0-1!E29', 'L0-1!F29'])
  })

  it('品种报表行取自 report_config 实证（BS-064 / BS-062）', () => {
    expect(L0_MATRIX_CATEGORIES[0].book.rowCode).toBe('BS-064')
    expect(L0_MATRIX_CATEGORIES[1].book.rowCode).toBe('BS-062')
  })

  it('矩阵输出 2×8 且顺序与常量一致', () => {
    const m = buildL0SummaryMatrix({ rows: [] })
    expect(m).toHaveLength(2)
    for (const row of m) {
      expect(row).toHaveLength(8)
      expect(row.map((c) => c.metric)).toEqual(L0_MATRIX_METRICS.map((x) => x.key))
      expect(row.map((c) => c.label)).toEqual([...L0_MATRIX_LABELS])
    }
  })
})

// ─── 源模板事实交叉锁死（读后端守卫常量） ───────────────────────────────────

describe('跨前后端交叉锁死：与后端源模板守卫常量一致', () => {
  const backendGuard = path.join(REPO_ROOT, 'backend', 'tests', 'test_l0_source_template_facts.py')

  it('后端守卫文件存在（否则本组断言空转）', () => {
    expect(fs.existsSync(backendGuard)).toBe(true)
  })

  it('品种字面与后端 MATRIX_CATEGORIES 一致', () => {
    const src = fs.readFileSync(backendGuard, 'utf-8')
    const block = /MATRIX_CATEGORIES\s*=\s*\[([\s\S]*?)\]/.exec(src)
    expect(block).toBeTruthy()
    for (const name of L0_MATRIX_CATEGORY_NAMES) {
      expect(block![1]).toContain(name)
    }
  })

  it('指标 label 与后端 MATRIX_METRIC_CELLS 一致（后端含行尾冒号）', () => {
    const src = fs.readFileSync(backendGuard, 'utf-8')
    const block = /MATRIX_METRIC_CELLS\s*=\s*\[([\s\S]*?)\n\]/.exec(src)
    expect(block).toBeTruthy()
    for (const label of L0_MATRIX_LABELS) {
      expect(block![1]).toContain(`${label}：`)
    }
  })

  it('报表行与后端 l_cycle_specs 的 L5/L4 一致', () => {
    const specs = fs.readFileSync(
      path.join(REPO_ROOT, 'backend', 'app', 'services', 'four_table', 'l_cycle_specs.py'),
      'utf-8',
    )
    expect(/L5_SPEC\s*=\s*SemanticAccountSpec\(\s*\n\s*row_code="BS-064"/.test(specs)).toBe(true)
    expect(/L4_SPEC\s*=\s*SemanticAccountSpec\(\s*\n\s*row_code="BS-062"/.test(specs)).toBe(true)
  })
})

// ─── Property 9：与 F0 同源（防收敛前漂移） ────────────────────────────────

describe('Property 9: 与 F0 矩阵同源', () => {
  const f0Path = path.join(
    REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
    'confirmation', 'composables', 'f0SummaryAggregation.ts',
  )

  it('F0 模块存在（否则本组断言空转）', () => {
    expect(fs.existsSync(f0Path)).toBe(true)
  })

  it('8 个指标 label 与 F0 逐字相同', () => {
    const src = fs.readFileSync(f0Path, 'utf-8')
    for (const label of L0_MATRIX_LABELS) {
      expect(src, `F0 应含指标「${label}」`).toContain(label)
    }
  })

  it('F0 仍是 label-as-key 形态 —— 一旦改成 key+label 即提示收敛可推进', () => {
    const src = fs.readFileSync(f0Path, 'utf-8')
    // F0 的 cell 用 `metric` 直接存中文 label（无独立 label 字段）
    const hasSeparateLabelField = /interface\s+F0MatrixCell\s*\{[\s\S]*?\blabel\s*:/.test(src)
    expect(
      hasSeparateLabelField,
      'F0 已改为 key+label 两字段 → 收敛 spec 可推进，请更新本断言',
    ).toBe(false)
  })

  it('L0 是 key+label 两字段（收敛目标形态）', () => {
    const cell = buildL0SummaryMatrix({ rows: [] })[0][0]
    expect(cell.metric).toBe('book_amount')       // 稳定 key
    expect(cell.label).toBe('本期（期末）账面金额')  // 中文 label 独立
    expect(cell.metric).not.toBe(cell.label)
  })

  it('收敛锚点存在且值与其它副本一致', () => {
    expect(CONVERGENCE_TARGET).toBe('confirmation-summary-matrix-convergence')
    const g0 = fs.readFileSync(
      path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
        'g0-confirmation', 'g0SummaryMatrix.ts'),
      'utf-8',
    )
    expect(g0).toContain(`CONVERGENCE_TARGET = '${CONVERGENCE_TARGET}'`)
  })

  it('L0 不做动态品种可见性（源模板无 …… 可扩位，G0 那套是为 8 品种候选全集设计的）', () => {
    const src = fs.readFileSync(
      path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
        'confirmation', 'l0-confirmation', 'l0SummaryMatrix.ts'),
      'utf-8',
    )
    expect(src).not.toContain('showAllCategories')
    expect(src).not.toContain('visibleCategories')
  })
})

// ─── Property 10：比例列按源模板 ISERROR 兜底 ─────────────────────────────

describe('Property 10: 比例列兜底与聚合口径', () => {
  const row = (o: Record<string, unknown>) => o as never

  it('分母为 0 时比例返 0（源模板 IF(ISERROR(...),0,...)），不返 null 不抛异常', () => {
    const m = buildL0SummaryMatrix({
      rows: [row({ account_type: '长期应付款', amount: 100 })],
      bookAmounts: { 长期应付款: 0, 应付债券: 0 },
    })
    const ratio = pickL0MatrixCell(m, '长期应付款', 'send_ratio')
    expect(ratio?.value).toBe(0)
  })

  it('账面金额为 null（本项目无此科目）时比例仍返 0 不抛异常', () => {
    const m = buildL0SummaryMatrix({
      rows: [row({ account_type: '应付债券', amount: 50 })],
      bookAmounts: { 长期应付款: null, 应付债券: null },
    })
    for (const key of ['send_ratio', 'reply_over_book', 'reply_alt_over_book'] as L0MetricKey[]) {
      expect(pickL0MatrixCell(m, '应付债券', key)?.value).toBe(0)
    }
  })

  it('SUMIF 按 account_type 分品种聚合，不叠「相符」过滤', () => {
    const m = buildL0SummaryMatrix({
      rows: [
        row({ account_type: '长期应付款', amount: 100, confirmed_amount: 90, alt_confirmed: 5, match_status: '不符' }),
        row({ account_type: '长期应付款', amount: 200, confirmed_amount: 200, alt_confirmed: 0, match_status: '相符' }),
        row({ account_type: '应付债券', amount: 300, confirmed_amount: 250, alt_confirmed: 10 }),
      ],
      bookAmounts: { 长期应付款: 1000, 应付债券: 500 },
    })
    // 「不符」行的 90 也计入 —— 相符判断已在 computeConfirmedAmount 的派生里
    expect(pickL0MatrixCell(m, '长期应付款', 'send_amount')?.value).toBe(300)
    expect(pickL0MatrixCell(m, '长期应付款', 'reply_confirmed')?.value).toBe(290)
    expect(pickL0MatrixCell(m, '长期应付款', 'alt_confirmed')?.value).toBe(5)
    expect(pickL0MatrixCell(m, '应付债券', 'send_amount')?.value).toBe(300)
  })

  it('末行 = (替代 + 回函) / 账面', () => {
    const m = buildL0SummaryMatrix({
      rows: [row({ account_type: '长期应付款', amount: 100, confirmed_amount: 80, alt_confirmed: 20 })],
      bookAmounts: { 长期应付款: 200, 应付债券: 0 },
    })
    expect(pickL0MatrixCell(m, '长期应付款', 'reply_alt_over_book')?.value).toBeCloseTo(0.5, 10)
  })

  it('三个比例的分子分母对应源模板公式', () => {
    const m = buildL0SummaryMatrix({
      rows: [row({ account_type: '应付债券', amount: 400, confirmed_amount: 100 })],
      bookAmounts: { 长期应付款: 0, 应付债券: 800 },
    })
    expect(pickL0MatrixCell(m, '应付债券', 'send_ratio')?.value).toBeCloseTo(0.5, 10)      // 400/800
    expect(pickL0MatrixCell(m, '应付债券', 'reply_over_send')?.value).toBeCloseTo(0.25, 10) // 100/400
    expect(pickL0MatrixCell(m, '应付债券', 'reply_over_book')?.value).toBeCloseTo(0.125, 10) // 100/800
  })

  it('非有限值/空串输入不产生 NaN 或 Infinity（PBT 式穷举脏值）', () => {
    const dirty = [undefined, null, '', 'abc', NaN, Infinity, -Infinity, '1e400', {}, []]
    for (const v of dirty) {
      const m = buildL0SummaryMatrix({
        rows: [row({ account_type: '长期应付款', amount: v, confirmed_amount: v, alt_confirmed: v })],
        bookAmounts: { 长期应付款: 100, 应付债券: 100 },
      })
      for (const cell of m.flat()) {
        if (cell.value === null) continue
        expect(Number.isFinite(cell.value), `脏值 ${String(v)} 产生了 ${cell.value}`).toBe(true)
      }
    }
  })

  it('脏值账面金额（NaN/Infinity）被归一，不污染比例列', () => {
    for (const bad of [NaN, Infinity, -Infinity]) {
      const m = buildL0SummaryMatrix({
        rows: [row({ account_type: '长期应付款', amount: 10 })],
        bookAmounts: { 长期应付款: bad as number, 应付债券: 0 },
      })
      const ratio = pickL0MatrixCell(m, '长期应付款', 'send_ratio')
      expect(Number.isFinite(ratio?.value ?? 0)).toBe(true)
    }
  })
})

// ─── Property 13：手工覆盖键 ───────────────────────────────────────────────

describe('Property 13: 手工覆盖键用指标 key 构键', () => {
  it('键形 = X0-1-matrix-{中文品种}-{指标key}（与 G0/K0 同构）', () => {
    expect(matrixOverrideItemId('长期应付款', 'book_amount'))
      .toBe('L0-1-matrix-长期应付款-book_amount')
    expect(bookAmountOverrideItemId('应付债券')).toBe('L0-1-matrix-应付债券-book_amount')
    expect(L0_MATRIX_KEY_PREFIX).toBe('L0-1-matrix')
  })

  it('指标段是稳定 key，不含中文', () => {
    for (const cat of L0_MATRIX_CATEGORY_NAMES) {
      for (const m of L0_MATRIX_METRICS) {
        const id = matrixOverrideItemId(cat, m.key)
        const metricSeg = id.slice(`${L0_MATRIX_KEY_PREFIX}-${cat}-`.length)
        expect(metricSeg).toBe(m.key)
        expect(/[\u4e00-\u9fa5]/.test(metricSeg), `指标段不应含中文: ${metricSeg}`).toBe(false)
      }
    }
  })

  it('品种段是源模板中文字面（同时是 SUMIF criteria，非可改文案）', () => {
    const id = matrixOverrideItemId('长期应付款', 'book_amount')
    expect(id).toContain('长期应付款')
    expect(L0_MATRIX_CATEGORY_NAMES).toContain('长期应付款')
  })

  it('反向自检：用中文 label 作指标段的朴素实现会被上条断言打红', () => {
    const naive = (cat: string, label: string) => `${L0_MATRIX_KEY_PREFIX}-${cat}-${label}`
    const bad = naive('长期应付款', '本期（期末）账面金额')
    const metricSeg = bad.slice(`${L0_MATRIX_KEY_PREFIX}-长期应付款-`.length)
    expect(/[\u4e00-\u9fa5]/.test(metricSeg)).toBe(true)   // 复现缺陷
    expect(bad).not.toBe(matrixOverrideItemId('长期应付款', 'book_amount'))
  })

  it('手工覆盖优先于后端取数', () => {
    const m = buildL0SummaryMatrix({
      rows: [],
      bookAmounts: { 长期应付款: 111, 应付债券: 222 },
      manualOverrides: { 'L0-1-matrix-长期应付款-book_amount': 999 },
    })
    expect(pickL0MatrixCell(m, '长期应付款', 'book_amount')?.value).toBe(999)
    expect(pickL0MatrixCell(m, '应付债券', 'book_amount')?.value).toBe(222)
  })
})

// ─── Property 12：三态可区分 ──────────────────────────────────────────────

describe('Property 12: 账面金额三态可区分', () => {
  it('键不存在 → not_fetched；值为 null → absent；值为 0 → value', () => {
    expect(buildL0BookAmountViews({ project_context: {} }).map((v) => v.state))
      .toEqual(['not_fetched', 'not_fetched'])
    const views = buildL0BookAmountViews({
      project_context: { l0_book_amounts: { 长期应付款: null, 应付债券: 0 } },
    })
    expect(views.map((v) => v.state)).toEqual(['absent', 'value'])
    expect(views[1].value).toBe(0)
  })

  it('三态文案互不相同且为中文（UI 全中文化）', () => {
    expect(L0_BOOK_STATE_TEXT.not_fetched).not.toBe(L0_BOOK_STATE_TEXT.absent)
    expect(L0_BOOK_STATE_TEXT.not_fetched).toContain('未取数')
    expect(L0_BOOK_STATE_TEXT.absent).toContain('本项目无此科目')
    expect(/[A-Za-z]/.test(L0_BOOK_STATE_TEXT.absent)).toBe(false)
  })

  it('readL0BookAmounts 在键不存在时返 undefined 而非 {}', () => {
    expect(readL0BookAmounts({ project_context: {} }).amounts).toBeUndefined()
    expect(readL0BookAmounts(null).amounts).toBeUndefined()
    expect(readL0BookAmounts({ project_context: { l0_book_amounts: {} } }).amounts).toEqual({})
  })

  it('反向自检：`?? {}` 兜底会让 not_fetched 塌陷成 absent', () => {
    const raw = readL0BookAmounts({ project_context: {} }).amounts
    const naive = raw ?? {}                       // 复现被禁的写法
    expect(raw).toBeUndefined()
    expect(naive).toEqual({})
    // 朴素写法下「键不存在」与「值为 null」都会走同一分支
    expect('长期应付款' in naive).toBe(false)
  })

  it('源码级：模块不含 `?? {}` 兜底', () => {
    const src = fs.readFileSync(
      path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src', 'components', 'workpaper',
        'confirmation', 'l0-confirmation', 'l0MatrixDataSources.ts'),
      'utf-8',
    )
    const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
    expect(code).not.toMatch(/l0_book_amounts[^\n]*\?\?\s*\{\}/)
  })

  it('矩阵单元格保留 null（不塌陷成 0）', () => {
    const m = buildL0SummaryMatrix({
      rows: [],
      bookAmounts: { 长期应付款: null, 应付债券: 0 },
    })
    expect(pickL0MatrixCell(m, '长期应付款', 'book_amount')?.value).toBeNull()
    expect(pickL0MatrixCell(m, '应付债券', 'book_amount')?.value).toBe(0)
  })
})

// ─── 诊断必须有渲染出口 ────────────────────────────────────────────────────

describe('取数诊断（F0 教训：只收集不渲染会掩盖链路失效）', () => {
  it('未下发 l0_book_amounts 时产出 error（不是静默）', () => {
    const d = buildL0MatrixDiagnostics({ project_context: {} })
    expect(d.errors.length).toBeGreaterThan(0)
    expect(d.errors[0]).toContain('未取数')
    expect(hasL0MatrixDiagnostics(d)).toBe(true)
  })

  it('「本项目科目表无该科目」不算 error（是正确行为不是告警）', () => {
    const d = buildL0MatrixDiagnostics({
      project_context: {
        l0_book_amounts: { 长期应付款: null, 应付债券: 0 },
        l0_book_source_codes: {
          长期应付款: { found: false, absent_reason: '本项目科目表无该科目' },
          应付债券: { found: true, parent_check: { '2502': 0 } },
        },
      },
    })
    expect(d.errors).toEqual([])
    expect(hasL0MatrixDiagnostics(d)).toBe(false)
  })

  it('parent_check 超容差 → 产出勾稽问题（审计追溯，必须可见）', () => {
    const d = buildL0MatrixDiagnostics({
      project_context: {
        l0_book_amounts: { 长期应付款: 100, 应付债券: 0 },
        l0_book_source_codes: {
          长期应付款: { found: true, parent_check: { '2701': 12.34 } },
        },
      },
    })
    expect(d.parentCheckIssues).toHaveLength(1)
    expect(d.parentCheckIssues[0]).toContain('2701')
    expect(d.parentCheckIssues[0]).toContain('12.34')
  })

  it('容差内的 parent_check 不报（与后端 tolerance=0.005 同口径）', () => {
    const d = buildL0MatrixDiagnostics({
      project_context: {
        l0_book_amounts: { 长期应付款: 100, 应付债券: 0 },
        l0_book_source_codes: { 长期应付款: { found: true, parent_check: { '2701': 0.004 } } },
      },
    })
    expect(d.parentCheckIssues).toEqual([])
  })

  it('conflicts 与 chart_available=false 被透出', () => {
    const d = buildL0MatrixDiagnostics({
      project_context: {
        l0_book_amounts: { 长期应付款: 1 },
        l0_book_conflicts: ['报表公式给的码与科目表不一致'],
        l0_book_source_codes: { 长期应付款: { found: true, chart_available: false } },
      },
    })
    expect(d.conflicts).toHaveLength(1)
    expect(d.chartUnavailable).toBe(true)
  })

  it('chart_available 缺省（undefined）不判为不可用', () => {
    const d = buildL0MatrixDiagnostics({
      project_context: {
        l0_book_amounts: { 长期应付款: 1 },
        l0_book_source_codes: { 长期应付款: { found: true } },
      },
    })
    expect(d.chartUnavailable).toBe(false)
  })
})
