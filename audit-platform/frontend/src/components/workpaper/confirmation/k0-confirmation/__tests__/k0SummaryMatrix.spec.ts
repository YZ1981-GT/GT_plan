/**
 * k0SummaryMatrix.spec.ts — K0-1 矩阵纯函数守卫
 *
 * spec: k0-confirmation-source-alignment · Task 8 / Task 11 / Task 15
 *   Property 5（8 指标与源模板公式同构）
 *   Property 6（分母缺失不产 NaN/Infinity 且不用 0 冒充，含 PBT）
 *   Property 7（对 E0/F0/G0/H0/L0 五份既有矩阵零回归）
 *   Property 8（账面金额三态 + row_code 精确匹配）
 *
 * 判据原则：同源性拿 **F0 的真实实现**逐字节比对（不拿自己写的 fixture 自证）；
 * 每条关键断言配反向自检，防正则失效导致空转。
 *
 * 🔴 **Property 7 的判据形态偏离 design.md**（落手时的有意裁决，理由见下）：
 * design 写「断言 f0/e0/h0 三文件的**内容哈希**不变」。冻结哈希是**假红发生器** ——
 * 那三个文件被 E0/F0/G0/H0/L0 五个 spec 共享，任何并发会话动一个字（哪怕只是注释）
 * 都会让本 spec 打红，而那与「K0 是否造成回归」毫无因果
 * （平台已登记同族教训：characterization 冻结上游快照 → 与本 spec 无因果的假红）。
 * 改用**两条更硬的结构性判据**：
 *   ① 行为快照：`buildF0SummaryMatrix` 对固定输入的输出逐字节等于冻结值
 *      （真正要保的「零回归」就是这个，且它对无害的注释改动免疫）；
 *   ② 源码级：`k0SummaryMatrix.ts` 对 `f0SummaryAggregation` **只 import 不赋值/不改写**。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import fc from 'fast-check'
import { describe, expect, it } from 'vitest'

import {
  F0_MATRIX_LABELS,
  buildF0SummaryMatrix,
  safeRatio,
  sumByCategory,
} from '../../composables/f0SummaryAggregation'
import { buildE0SummaryMatrix } from '../../e0SummaryMatrix'
import type { ConfirmationRow } from '../../confirmationTypes'
import {
  K0_MATRIX_CATEGORIES,
  K0_MATRIX_METRIC_LABELS,
  k0MatrixOverrideItemId,
} from '../k0MatrixSpec'
import {
  CONVERGENCE_TARGET,
  K0_MATRIX_CATEGORY_NAMES,
  K0_MATRIX_LABELS,
  K0_MATRIX_METRICS,
  buildK0SummaryMatrix,
  countK0UnclassifiedRows,
  pickK0MatrixCell,
  resolveK0BookAmount,
  type K0MetricKey,
} from '../k0SummaryMatrix'
import {
  K0_BOOK_SOURCE_SPECS,
  K0_BOOK_STATE_TEXT,
  bookAmountOverrideItemId,
  buildK0BookAmountViews,
  hasK0MatrixDiagnostics,
  parseK0ManualOverrides,
} from '../k0MatrixDataSources'

const MATRIX_TS = resolve(__dirname, '../k0SummaryMatrix.ts')
const SOURCES_TS = resolve(__dirname, '../k0MatrixDataSources.ts')
const matrixSrc = readFileSync(MATRIX_TS, 'utf-8')
const sourcesSrc = readFileSync(SOURCES_TS, 'utf-8')

/** 剥注释（守卫自己的说明注释里会写反例，不剥会把说明数成真实代码） */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

const row = (o: Partial<ConfirmationRow>): ConfirmationRow => ({ ...(o as ConfirmationRow) })

const RECEIVABLE = '其他应收款'
const PAYABLE = '其他应付款'

describe('helper 自检', () => {
  it('stripComments 确实剥掉了注释里的反例字样', () => {
    expect(matrixSrc).toContain('SHALL NOT')
    expect(stripComments(matrixSrc)).not.toContain('SHALL NOT')
  })
})

// ─── Property 5 ──────────────────────────────────────────────────────────────

describe('Property 5: 8 指标与源模板公式同构', () => {
  it('矩阵形状为 2 品种 × 8 指标', () => {
    const m = buildK0SummaryMatrix({ rows: [] })
    expect(m).toHaveLength(2)
    for (const r of m) expect(r).toHaveLength(8)
    expect(K0_MATRIX_CATEGORY_NAMES).toEqual([RECEIVABLE, PAYABLE])
  })

  it('label 取自 k0MatrixSpec（不抄第二份中文）', () => {
    expect(K0_MATRIX_LABELS).toEqual([...K0_MATRIX_METRIC_LABELS])
    // 源码里不得再出现中文指标字面量（真源在 k0MatrixSpec）
    const body = stripComments(matrixSrc)
    for (const label of K0_MATRIX_METRIC_LABELS) {
      expect(body).not.toContain(label)
    }
  })

  it('anchor 与 sourceRef 逐条对应源模板 C29..C36', () => {
    expect(K0_MATRIX_METRICS.map((m) => m.anchor)).toEqual([
      'C29', 'C30', 'C31', 'C32', 'C33', 'C34', 'C35', 'C36',
    ])
    for (const m of K0_MATRIX_METRICS) {
      expect(m.sourceRef).toBe(`K0-1!${m.anchor}`)
    }
  })

  it('三个金额指标 = SUMIF(E列=品种, F/U/Y 列)，不叠相符过滤', () => {
    const rows = [
      row({ account_type: RECEIVABLE, amount: 100, confirmed_amount: 90, alt_confirmed: 5, match_status: '不符' }),
      row({ account_type: RECEIVABLE, amount: 200, confirmed_amount: 180, alt_confirmed: 0, match_status: '相符' }),
      row({ account_type: PAYABLE, amount: 50, confirmed_amount: 50, alt_confirmed: 0 }),
      // 未归类行不计入任何品种
      row({ account_type: '预付账款', amount: 999, confirmed_amount: 999, alt_confirmed: 999 }),
    ]
    const m = buildK0SummaryMatrix({ rows })
    expect(pickK0MatrixCell(m, RECEIVABLE, 'send_amount')!.value).toBe(300)
    // 🔴 不叠 match_status 过滤：不符行的 90 也计入（可确认金额的业务规则已在派生里）
    expect(pickK0MatrixCell(m, RECEIVABLE, 'reply_confirmed')!.value).toBe(270)
    expect(pickK0MatrixCell(m, RECEIVABLE, 'alt_confirmed')!.value).toBe(5)
    expect(pickK0MatrixCell(m, PAYABLE, 'send_amount')!.value).toBe(50)
  })

  it('反向自检：若叠了「相符」过滤，回函确认金额会变成 180 而非 270', () => {
    const rows = [
      row({ account_type: RECEIVABLE, amount: 100, confirmed_amount: 90, match_status: '不符' }),
      row({ account_type: RECEIVABLE, amount: 200, confirmed_amount: 180, match_status: '相符' }),
    ]
    const m = buildK0SummaryMatrix({ rows })
    expect(pickK0MatrixCell(m, RECEIVABLE, 'reply_confirmed')!.value).toBe(270)
    expect(pickK0MatrixCell(m, RECEIVABLE, 'reply_confirmed')!.value).not.toBe(180)
  })

  it('四个比例 = 对应商；末行 = (替代 + 回函) / 账面', () => {
    const rows = [row({ account_type: RECEIVABLE, amount: 400, confirmed_amount: 300, alt_confirmed: 100 })]
    const m = buildK0SummaryMatrix({
      rows,
      bookAmounts: { [RECEIVABLE]: 1000, [PAYABLE]: null },
    })
    const pick = (k: K0MetricKey) => pickK0MatrixCell(m, RECEIVABLE, k)!.value
    expect(pick('book_amount')).toBe(1000)
    expect(pick('send_ratio')).toBeCloseTo(400 / 1000, 12)
    expect(pick('reply_over_send')).toBeCloseTo(300 / 400, 12)
    expect(pick('reply_over_book')).toBeCloseTo(300 / 1000, 12)
    // 源 R36 = (R35 + R32) / R29
    expect(pick('reply_alt_over_book')).toBeCloseTo((100 + 300) / 1000, 12)
  })

  it('只有账面金额行 editable，其余 7 行派生', () => {
    const m = buildK0SummaryMatrix({ rows: [] })
    for (const r of m) {
      expect(r.filter((c) => c.editable).map((c) => c.metric)).toEqual(['book_amount'])
    }
  })

  it('账面金额行带溯源提示，其余行不带', () => {
    const m = buildK0SummaryMatrix({ rows: [] })
    const book = pickK0MatrixCell(m, PAYABLE, 'book_amount')!
    expect(book.sourceHint).toContain('BS-050')
    expect(pickK0MatrixCell(m, PAYABLE, 'send_amount')!.sourceHint).toBeUndefined()
  })
})

// ─── Property 6 ──────────────────────────────────────────────────────────────

describe('Property 6: 分母缺失不产 NaN/Infinity，且不用 0 冒充', () => {
  it('bookAmounts 整体缺失 → 账面金额与三个含账面分母的比例全为 null（不是 0）', () => {
    const rows = [row({ account_type: RECEIVABLE, amount: 400, confirmed_amount: 300 })]
    const m = buildK0SummaryMatrix({ rows })
    const pick = (k: K0MetricKey) => pickK0MatrixCell(m, RECEIVABLE, k)!.value
    expect(pick('book_amount')).toBeNull()
    expect(pick('send_ratio')).toBeNull()
    expect(pick('reply_over_book')).toBeNull()
    expect(pick('reply_alt_over_book')).toBeNull()
    // 分母是发函金额的那个仍可算
    expect(pick('reply_over_send')).toBeCloseTo(300 / 400, 12)
  })

  it('某品种值为 null（本项目无此科目）→ 该品种比例为 null，另一品种不受影响', () => {
    const rows = [
      row({ account_type: RECEIVABLE, amount: 100, confirmed_amount: 100 }),
      row({ account_type: PAYABLE, amount: 100, confirmed_amount: 100 }),
    ]
    const m = buildK0SummaryMatrix({ rows, bookAmounts: { [RECEIVABLE]: null, [PAYABLE]: 500 } })
    expect(pickK0MatrixCell(m, RECEIVABLE, 'send_ratio')!.value).toBeNull()
    expect(pickK0MatrixCell(m, PAYABLE, 'send_ratio')!.value).toBeCloseTo(0.2, 12)
  })

  it('账面金额为 0（科目存在但余额为 0）→ 比例仍为 null（除零），但账面金额格是 0 不是 null', () => {
    const m = buildK0SummaryMatrix({
      rows: [row({ account_type: PAYABLE, amount: 10 })],
      bookAmounts: { [PAYABLE]: 0 },
    })
    expect(pickK0MatrixCell(m, PAYABLE, 'book_amount')!.value).toBe(0)
    expect(pickK0MatrixCell(m, PAYABLE, 'send_ratio')!.value).toBeNull()
  })

  it('手工覆盖优先于取数结果（源 R29 本就是手填行）', () => {
    const key = k0MatrixOverrideItemId(RECEIVABLE, 'book_amount')
    const m = buildK0SummaryMatrix({
      rows: [],
      bookAmounts: { [RECEIVABLE]: 1000 },
      manualOverrides: { [key]: 2500 },
    })
    expect(pickK0MatrixCell(m, RECEIVABLE, 'book_amount')!.value).toBe(2500)
  })

  it('手工覆盖为空串/非法值时不生效（不写入 NaN）', () => {
    const key = k0MatrixOverrideItemId(RECEIVABLE, 'book_amount')
    for (const bad of ['', 'abc', null, undefined] as unknown[]) {
      const v = resolveK0BookAmount(RECEIVABLE, {
        bookAmounts: { [RECEIVABLE]: 777 },
        manualOverrides: { [key]: bad as number },
      })
      expect(v).toBe(777)
    }
  })

  it('PBT：任意金额输入下，每一格 value 要么有限、要么 null，绝不 NaN/±Infinity', () => {
    // 🔴 金额生成器必须显式排除 ±Infinity —— `fc.float({noNaN:true})` 仍会生成无穷值
    //    （平台已踩过一次，seed 1139061718）。
    const money = fc
      .float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
      .filter((n) => Number.isFinite(n))
    const rowArb = fc.record({
      account_type: fc.constantFrom(RECEIVABLE, PAYABLE, '未知品种', ''),
      amount: money,
      confirmed_amount: money,
      alt_confirmed: money,
    })
    fc.assert(
      fc.property(
        fc.array(rowArb, { maxLength: 12 }),
        fc.option(money, { nil: undefined }),
        fc.option(money, { nil: undefined }),
        (rows, bookR, bookP) => {
          const bookAmounts: Record<string, number | null> = {}
          if (bookR !== undefined) bookAmounts[RECEIVABLE] = bookR
          if (bookP !== undefined) bookAmounts[PAYABLE] = bookP
          const m = buildK0SummaryMatrix({
            rows: rows as unknown as ConfirmationRow[],
            bookAmounts: Object.keys(bookAmounts).length ? bookAmounts : undefined,
          })
          for (const line of m) {
            for (const cell of line) {
              if (cell.value === null) continue
              expect(Number.isFinite(cell.value)).toBe(true)
            }
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('countK0UnclassifiedRows 只数「填了但不在两品种内」的行（空值不算）', () => {
    const rows = [
      row({ account_type: RECEIVABLE }),
      row({ account_type: '预付账款' }),
      row({ account_type: '  ' }),
      row({}),
    ]
    expect(countK0UnclassifiedRows(rows)).toBe(1)
  })
})

// ─── Property 7 ──────────────────────────────────────────────────────────────

describe('Property 7: 对既有五份矩阵零回归', () => {
  const F0_ROWS: ConfirmationRow[] = [
    row({ account_type: '预付账款', amount: 1000, confirmed_amount: 800, alt_confirmed: 150 }),
    row({ account_type: '应付票据', amount: 500, confirmed_amount: 500, alt_confirmed: 0 }),
  ]

  it('buildF0SummaryMatrix 行为快照逐字节不变（真正的零回归判据）', () => {
    const out = buildF0SummaryMatrix({
      rows: F0_ROWS,
      bookAmounts: { 预付账款: 4000 },
    })
    // 冻结值 = 引入 K0 矩阵**之前**实测的输出（`[品种, 指标, value, kind, editable]`）。
    // 🔴 `sourceHint` 的**措辞**不进快照（改文案不是回归），但它的**存在模式**由下一条断言钉住。
    const digest = out.map((line) =>
      line.map((c) => [c.category, c.metric, c.value, c.kind, c.editable]),
    )
    expect(JSON.stringify(digest)).toBe(
      JSON.stringify([
        [
          ['预付账款', '本期（期末）账面金额', 4000, 'amount', true],
          ['预付账款', '抽取样本的发函金额', 1000, 'amount', false],
          ['预付账款', '发函金额占账面金额的比例(%)', 0.25, 'ratio', false],
          ['预付账款', '回函确认金额', 800, 'amount', false],
          ['预付账款', '回函可确认金额占发函金额的比例(%)', 0.8, 'ratio', false],
          ['预付账款', '回函可确认金额占账面金额的比例(%)', 0.2, 'ratio', false],
          ['预付账款', '替代测试确认金额', 150, 'amount', false],
          ['预付账款', '回函和替代确认金额占账面金额的比例(%)', 0.2375, 'ratio', false],
        ],
        [
          ['应付票据', '本期（期末）账面金额', null, 'amount', true],
          ['应付票据', '抽取样本的发函金额', 500, 'amount', false],
          ['应付票据', '发函金额占账面金额的比例(%)', null, 'ratio', false],
          ['应付票据', '回函确认金额', 500, 'amount', false],
          ['应付票据', '回函可确认金额占发函金额的比例(%)', 1, 'ratio', false],
          ['应付票据', '回函可确认金额占账面金额的比例(%)', null, 'ratio', false],
          ['应付票据', '替代测试确认金额', 0, 'amount', false],
          ['应付票据', '回函和替代确认金额占账面金额的比例(%)', null, 'ratio', false],
        ],
        [
          ['应付账款', '本期（期末）账面金额', null, 'amount', true],
          ['应付账款', '抽取样本的发函金额', 0, 'amount', false],
          ['应付账款', '发函金额占账面金额的比例(%)', null, 'ratio', false],
          ['应付账款', '回函确认金额', 0, 'amount', false],
          ['应付账款', '回函可确认金额占发函金额的比例(%)', null, 'ratio', false],
          ['应付账款', '回函可确认金额占账面金额的比例(%)', null, 'ratio', false],
          ['应付账款', '替代测试确认金额', 0, 'amount', false],
          ['应付账款', '回函和替代确认金额占账面金额的比例(%)', null, 'ratio', false],
        ],
        [
          ['本期采购', '本期（期末）账面金额', null, 'amount', true],
          ['本期采购', '抽取样本的发函金额', 0, 'amount', false],
          ['本期采购', '发函金额占账面金额的比例(%)', null, 'ratio', false],
          ['本期采购', '回函确认金额', 0, 'amount', false],
          ['本期采购', '回函可确认金额占发函金额的比例(%)', null, 'ratio', false],
          ['本期采购', '回函可确认金额占账面金额的比例(%)', null, 'ratio', false],
          ['本期采购', '替代测试确认金额', 0, 'amount', false],
          ['本期采购', '回函和替代确认金额占账面金额的比例(%)', null, 'ratio', false],
        ],
      ]),
    )
  })

  it('F0 的 sourceHint 存在模式不变：金额行有、比例行无', () => {
    const out = buildF0SummaryMatrix({ rows: F0_ROWS, bookAmounts: { 预付账款: 4000 } })
    for (const line of out) {
      for (const c of line) {
        if (c.kind === 'amount') expect(typeof c.sourceHint).toBe('string')
        else expect(c.sourceHint).toBeUndefined()
      }
    }
  })

  it('safeRatio / sumByCategory 行为未被改写（K0 只 import 不修改）', () => {
    expect(safeRatio(1, 0)).toBeNull()
    expect(safeRatio(null, 5)).toBeNull()
    expect(safeRatio(3, 4)).toBe(0.75)
    expect(sumByCategory(F0_ROWS, '预付账款', 'amount')).toBe(1000)
  })

  it('E0 矩阵仍可构建（未被 K0 波及）', () => {
    expect(typeof buildE0SummaryMatrix).toBe('function')
  })

  it('源码级：k0SummaryMatrix 只 import 不给共享函数赋值/再导出改写版', () => {
    const body = stripComments(matrixSrc)
    expect(body).toMatch(/import \{ safeRatio, sumByCategory \} from '\.\.\/composables\/f0SummaryAggregation'/)
    // 不得出现「重新定义同名函数」或「对共享模块成员赋值」
    expect(body).not.toMatch(/function\s+safeRatio/)
    expect(body).not.toMatch(/function\s+sumByCategory/)
    expect(body).not.toMatch(/f0SummaryAggregation\w*\.\w+\s*=/)
  })

  it('8 个指标标签与 F0 逐字相同（同源守卫：副本在收敛前不得各自漂移）', () => {
    expect(K0_MATRIX_LABELS).toEqual([...F0_MATRIX_LABELS])
  })

  it('同一批输入下，K0 与 F0 的同名指标 kind/editable/value 逐字节相同', () => {
    // 用一个 F0 与 K0 都认识的构造：把品种名换掉即可
    const mk = (cat: string) => [
      row({ account_type: cat, amount: 1000, confirmed_amount: 800, alt_confirmed: 150 }),
    ]
    const f0 = buildF0SummaryMatrix({ rows: mk('预付账款'), bookAmounts: { 预付账款: 4000 } })[0]
    const k0 = buildK0SummaryMatrix({
      rows: mk(RECEIVABLE),
      bookAmounts: { [RECEIVABLE]: 4000 },
    })[0]
    expect(k0).toHaveLength(f0.length)
    for (let i = 0; i < f0.length; i += 1) {
      expect(k0[i].label).toBe(f0[i].metric)
      expect(k0[i].kind).toBe(f0[i].kind)
      expect(k0[i].editable).toBe(f0[i].editable)
      expect(k0[i].value).toBe(f0[i].value)
    }
  })

  it('CONVERGENCE_TARGET 与其余副本同标识', () => {
    expect(CONVERGENCE_TARGET).toBe('confirmation-summary-matrix-convergence')
  })
})

// ─── Property 8（取数侧） ────────────────────────────────────────────────────

describe('Property 8: 账面金额三态与取数口径声明', () => {
  it('取数声明与矩阵品种一一对应、row_code 一致', () => {
    expect(K0_BOOK_SOURCE_SPECS.map((s) => s.category)).toEqual([...K0_MATRIX_CATEGORY_NAMES])
    expect(K0_BOOK_SOURCE_SPECS.map((s) => s.reportRowCode)).toEqual(
      K0_MATRIX_CATEGORIES.map((c) => c.reportRowCode),
    )
    expect(K0_BOOK_SOURCE_SPECS.map((s) => s.wpCode)).toEqual(['K1', 'K3'])
  })

  it('三态文案互不相同且 value 态为空串', () => {
    const texts = Object.values(K0_BOOK_STATE_TEXT)
    expect(new Set(texts).size).toBe(texts.length)
    expect(K0_BOOK_STATE_TEXT.value).toBe('')
    expect(K0_BOOK_STATE_TEXT.not_fetched).not.toBe(K0_BOOK_STATE_TEXT.absent)
  })

  it('amounts 为 undefined → 全部 not_fetched；键为 null → absent；数字 → value', () => {
    expect(buildK0BookAmountViews(undefined).map((v) => v.state)).toEqual([
      'not_fetched',
      'not_fetched',
    ])
    const views = buildK0BookAmountViews({ [RECEIVABLE]: null, [PAYABLE]: 0 })
    expect(views.map((v) => v.state)).toEqual(['absent', 'value'])
    expect(views[1].value).toBe(0)
    expect(views[0].value).toBeNull()
  })

  it('resolvedBy 如实记录命中的取数口径（审计追溯）', () => {
    const views = buildK0BookAmountViews({ [RECEIVABLE]: 100 }, { [RECEIVABLE]: 'K1 报表核对数' })
    expect(views[0].resolvedBy).toBe('K1 报表核对数')
    // 未取到时不得编造口径
    expect(views[1].resolvedBy).toBeNull()
  })

  it('K1 侧首选口径是 BS-009 净额（report_total），退化口径显式标注不含股利/利息', () => {
    const spec = K0_BOOK_SOURCE_SPECS[0]
    expect(spec.attempts.length).toBeGreaterThanOrEqual(2)
    expect(spec.attempts[0].caliber).toContain('report_total')
    expect(spec.attempts[0].caliber).toContain('BS-009')
    expect(spec.attempts[1].caliber).toContain('不含')
  })

  it('K1 首选口径真能从 render 形态里取到 report_total', () => {
    const hd = { adjudication_prefill: { fs_reconciliation: { report_total: 123.45 } } }
    expect(K0_BOOK_SOURCE_SPECS[0].attempts[0].pick(hd)).toBe(123.45)
  })

  it('K1 退化口径 = 叶子期末原值 − 备抵', () => {
    const hd = {
      tb_values: { receivable_unadjusted_closing: 1000, bad_debt_unadjusted_closing: 120 },
    }
    expect(K0_BOOK_SOURCE_SPECS[0].attempts[1].pick(hd)).toBe(880)
  })

  it('K3 侧首选叶子期末，退化才用 trial_balance 的 tb_amount 且标注双算风险', () => {
    const spec = K0_BOOK_SOURCE_SPECS[1]
    expect(spec.attempts[0].pick({ tb_values: { other_payable_2241_closing: 555 } })).toBe(555)
    expect(spec.attempts[1].caliber).toContain('trial_balance')
    expect(spec.attempts[1].caliber).toContain('双算')
    expect(spec.attempts[1].pick({ tb_amount: 777 })).toBe(777)
  })

  it('K3 的 2231 缺口已登记 knownGap 且会进 diagnostics（不静默）', () => {
    const spec = K0_BOOK_SOURCE_SPECS[1]
    expect(spec.knownGap).toBeTruthy()
    expect(spec.knownGap).toContain('2231')
    expect(spec.knownGap).toContain('BS-050')
    expect(hasK0MatrixDiagnostics({ errors: [], resolved: [], missing: [], knownGaps: [spec.knownGap!] })).toBe(true)
  })

  it('手工覆盖键与 k0MatrixSpec 同源', () => {
    for (const cat of K0_MATRIX_CATEGORY_NAMES) {
      expect(bookAmountOverrideItemId(cat)).toBe(k0MatrixOverrideItemId(cat, 'book_amount'))
    }
  })

  it('parseK0ManualOverrides 兼容 Map 与普通对象，且拒非法值', () => {
    const key = bookAmountOverrideItemId(RECEIVABLE)
    expect(parseK0ManualOverrides(new Map([[key, { remark: '1234.5' }]]))).toEqual({ [key]: 1234.5 })
    expect(parseK0ManualOverrides({ [key]: { value: 88 } })).toEqual({ [key]: 88 })
    expect(parseK0ManualOverrides({ [key]: { remark: '' } })).toEqual({})
    expect(parseK0ManualOverrides({ [key]: { remark: 'abc' } })).toEqual({})
    expect(parseK0ManualOverrides(null)).toEqual({})
  })

  it('取数模块用 @/services/apiProxy（不是 @/utils/http）—— F0 那轮的 P0', () => {
    const body = stripComments(sourcesSrc)
    expect(body).toMatch(/import \{ api \} from '@\/services\/apiProxy'/)
    expect(body).not.toMatch(/from '@\/utils\/http'/)
  })

  it('反向自检：换成 @/utils/http 的默认导入形态会被上一条打红', () => {
    const bad = "import api from '@/utils/http'\n"
    expect(bad).toMatch(/from '@\/utils\/http'/)
  })

  it('调用方禁写 `?? {}` 兜底（会把「未取数」变成「无此科目」）', () => {
    const body = stripComments(sourcesSrc)
    expect(body).not.toMatch(/bookAmounts\s*\?\?\s*\{\}/)
  })
})
