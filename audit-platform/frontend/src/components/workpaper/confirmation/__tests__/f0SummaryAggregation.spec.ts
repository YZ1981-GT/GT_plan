/**
 * f0SummaryAggregation.spec.ts — F0-1 矩阵聚合纯函数守卫
 *
 * Property 1: 矩阵的「发函金额」= grid「金额」列按品种求和（源模板 SUMIF(E,品种,F)）
 * Property 2: 矩阵的「回函确认金额」= grid「可确认金额」列按品种求和（SUMIF(E,品种,U)）
 * Property 3: 零除 → null（渲染「-」）
 * Property 4: 手工覆盖不被自动值覆盖
 * Property 5: 反向自检（去掉品种过滤则和不等）
 * Property 6: safeRatio 不产出 NaN/Infinity
 * Property 8: 替代确认金额 = grid「替代后可确认金额」列（SUMIF(E,品种,Y)），
 *             并对 F0-5/F0-6 底稿合计做勾稽而非反推分摊（Task 28）
 */
import { describe, it, expect } from 'vitest'
import {
  buildF0SummaryMatrix,
  sumByCategory,
  safeRatio,
  checkAltConsistency,
  detectAltOverlapRows,
  F0_MATRIX_CATEGORIES,
  F0_MATRIX_LABELS,
  fetchTbAmountsForF0,
  F0_BOOK_AMOUNT_SOURCES,
  type F0MatrixInput,
} from '../composables/f0SummaryAggregation'
import type { ConfirmationRow } from '../confirmationTypes'

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeRow(overrides: Partial<ConfirmationRow>): ConfirmationRow {
  return { _row_id: Math.random().toString(36).slice(2), ...overrides }
}

/**
 * 列语义对齐源模板 F0-1 上区（R6 表头）：
 * `amount`=F 金额 · `confirmed_amount`=U 可确认金额 · `alt_confirmed`=Y 替代后可确认金额。
 *
 * `confirmed_amount` 取值遵循平台 `computeConfirmedAmount` 的派生结果
 * （相符→amount / 不符→reply_amount / 积极式未回函→alt_confirmed），
 * 故本 fixture 里未回函行的 U 与 Y 相等 —— 正是 `detectAltOverlapRows` 要提示的形态。
 */
const SAMPLE_ROWS: ConfirmationRow[] = [
  makeRow({ account_type: '预付账款', amount: 1000, reply_amount: 900, match_status: '相符', confirmed_amount: 1000 }),
  makeRow({ account_type: '预付账款', amount: 500, reply_amount: 500, match_status: '相符', confirmed_amount: 500 }),
  makeRow({ account_type: '预付账款', amount: 200, match_status: '未回函', alt_confirmed: 150, confirmed_amount: 150 }),
  makeRow({ account_type: '应付票据', amount: 3000, reply_amount: 2800, match_status: '相符', confirmed_amount: 3000 }),
  makeRow({ account_type: '应付票据', amount: 1000, reply_amount: 900, match_status: '不符', confirmed_amount: 900 }),
  makeRow({ account_type: '应付账款', amount: 5000, reply_amount: 5000, match_status: '相符', confirmed_amount: 5000 }),
  makeRow({ account_type: '本期采购', amount: 8000, reply_amount: 7500, match_status: '相符', confirmed_amount: 8000 }),
  makeRow({ account_type: '本期采购', amount: 2000, match_status: '未回函', alt_confirmed: 1800, confirmed_amount: 1800 }),
]

// ─── Property 1: 发函金额 = grid 按品种求和 ──────────────────────────────────

describe('Property 1: sumByCategory', () => {
  it('预付账款发函金额 = 1000 + 500 + 200 = 1700', () => {
    expect(sumByCategory(SAMPLE_ROWS, '预付账款', 'amount')).toBe(1700)
  })

  it('应付票据发函金额 = 3000 + 1000 = 4000', () => {
    expect(sumByCategory(SAMPLE_ROWS, '应付票据', 'amount')).toBe(4000)
  })

  it('应付账款发函金额 = 5000', () => {
    expect(sumByCategory(SAMPLE_ROWS, '应付账款', 'amount')).toBe(5000)
  })

  it('本期采购发函金额 = 8000 + 2000 = 10000', () => {
    expect(sumByCategory(SAMPLE_ROWS, '本期采购', 'amount')).toBe(10000)
  })

  it('空行返回 0', () => {
    expect(sumByCategory([], '预付账款', 'amount')).toBe(0)
  })

  it('不存在的品种返回 0', () => {
    expect(sumByCategory(SAMPLE_ROWS, '不存在品种', 'amount')).toBe(0)
  })
})

// ─── Property 2: 回函确认 = 相符行按品种求和 ─────────────────────────────────

describe('Property 2: 回函确认金额 = SUMIF(E,品种,U) 无相符过滤', () => {
  it('预付账款回函确认 = 1000 + 500 + 150 = 1650（含未回函行的可确认金额）', () => {
    expect(sumByCategory(SAMPLE_ROWS, '预付账款', 'confirmed_amount')).toBe(1650)
  })

  it('应付票据回函确认 = 3000 + 900 = 3900（不符行按可确认金额计入）', () => {
    expect(sumByCategory(SAMPLE_ROWS, '应付票据', 'confirmed_amount')).toBe(3900)
  })

  it('本期采购回函确认 = 8000 + 1800 = 9800', () => {
    expect(sumByCategory(SAMPLE_ROWS, '本期采购', 'confirmed_amount')).toBe(9800)
  })

  it('反向自检：旧口径（只取 match_status=相符 的 reply_amount）会得到不同结果', () => {
    // 旧实现 sumConfirmedByCategory('预付账款') = 900 + 500 = 1400
    const legacy = SAMPLE_ROWS
      .filter(r => r.account_type === '预付账款' && r.match_status === '相符')
      .reduce((s, r) => s + (r.reply_amount ?? 0), 0)
    expect(legacy).toBe(1400)
    expect(sumByCategory(SAMPLE_ROWS, '预付账款', 'confirmed_amount')).not.toBe(legacy)
  })
})

// ─── Property 3: 零除 → null ─────────────────────────────────────────────────

describe('Property 3: safeRatio', () => {
  it('正常除法', () => {
    expect(safeRatio(100, 200)).toBeCloseTo(0.5)
  })

  it('分母 0 → null', () => {
    expect(safeRatio(100, 0)).toBeNull()
  })

  it('分子 null → null', () => {
    expect(safeRatio(null, 100)).toBeNull()
  })

  it('分母 null → null', () => {
    expect(safeRatio(100, null)).toBeNull()
  })

  it('分母 undefined → null', () => {
    expect(safeRatio(100, undefined)).toBeNull()
  })

  it('0/非零 → 0（不是 null）', () => {
    expect(safeRatio(0, 100)).toBe(0)
  })
})

// ─── Property 4: 手工覆盖 ────────────────────────────────────────────────────

describe('Property 4: manualOverrides 优先', () => {
  it('有手工覆盖时用覆盖值而非自动聚合值', () => {
    const input: F0MatrixInput = {
      rows: SAMPLE_ROWS,
      manualOverrides: {
        '预付账款::抽取样本的发函金额': 9999,
      },
    }
    const matrix = buildF0SummaryMatrix(input)
    // 预付账款的发函金额行（index 1）
    const sendCell = matrix[0][1]
    expect(sendCell.value).toBe(9999)
  })

  it('无手工覆盖时用自动聚合值', () => {
    const input: F0MatrixInput = {
      rows: SAMPLE_ROWS,
    }
    const matrix = buildF0SummaryMatrix(input)
    const sendCell = matrix[0][1] // 预付账款发函金额
    expect(sendCell.value).toBe(1700) // 自动聚合
  })
})

// ─── Property 5: 反向自检 ────────────────────────────────────────────────────

describe('Property 5: 反向自检（去掉品种过滤则和不等）', () => {
  it('全品种求和 ≠ 单品种求和（证明品种过滤有效）', () => {
    const allSum = SAMPLE_ROWS.reduce((s, r) => s + (r.amount || 0), 0)
    const prepaySum = sumByCategory(SAMPLE_ROWS, '预付账款', 'amount')
    // 如果品种过滤无效（即对全部行求和），结果应为 allSum
    // 品种过滤有效则 prepaySum < allSum
    expect(prepaySum).toBeLessThan(allSum)
  })
})

// ─── Property 6: safeRatio 不产出 NaN/Infinity ───────────────────────────────

describe('Property 6: safeRatio 安全性', () => {
  const edgeCases: [number | null | undefined, number | null | undefined][] = [
    [Infinity, 1],
    [1, Infinity],
    [-Infinity, 1],
    [NaN, 1],
    [1, NaN],
    [0, 0],
    [Infinity, Infinity],
  ]

  it.each(edgeCases)('safeRatio(%s, %s) 不产出 NaN 或 ±Infinity', (a, b) => {
    const result = safeRatio(a as any, b as any)
    if (result !== null) {
      expect(Number.isFinite(result)).toBe(true)
    }
  })
})

// ─── 集成测试：完整矩阵构建 ──────────────────────────────────────────────────

describe('buildF0SummaryMatrix 集成', () => {
  it('返回 4 品种 × 8 指标', () => {
    const matrix = buildF0SummaryMatrix({ rows: SAMPLE_ROWS })
    expect(matrix.length).toBe(4) // 4 品种
    for (const cells of matrix) {
      expect(cells.length).toBe(8) // 8 指标
    }
  })

  it('品种列 category 正确', () => {
    const matrix = buildF0SummaryMatrix({ rows: SAMPLE_ROWS })
    for (let i = 0; i < 4; i++) {
      for (const cell of matrix[i]) {
        expect(cell.category).toBe(F0_MATRIX_CATEGORIES[i])
      }
    }
  })

  it('比例行无 bookAmounts 时全为 null', () => {
    const matrix = buildF0SummaryMatrix({ rows: SAMPLE_ROWS })
    // R32 发函占账面比例（index 2）
    for (const cells of matrix) {
      expect(cells[2].value).toBeNull() // book 缺 → null
    }
  })

  it('有 bookAmounts 时比例正确', () => {
    const matrix = buildF0SummaryMatrix({
      rows: SAMPLE_ROWS,
      bookAmounts: { '预付账款': 10000, '应付票据': 20000, '应付账款': 50000, '本期采购': 100000 },
    })
    // 预付账款发函占账面 = 1700/10000 = 0.17
    expect(matrix[0][2].value).toBeCloseTo(0.17)
    // 预付账款回函占发函 = 1650/1700 ≈ 0.9706
    expect(matrix[0][4].value).toBeCloseTo(1650 / 1700, 4)
    // R37 = (回函 1650 + 替代 150) / 账面 10000
    expect(matrix[0][7].value).toBeCloseTo(1800 / 10000, 6)
  })

  it('替代测试确认金额取上区 Y 列而非 F0-5/F0-6 反推', () => {
    const matrix = buildF0SummaryMatrix({ rows: SAMPLE_ROWS })
    expect(matrix[0][6].value).toBe(150)   // 预付账款：仅未回函行 alt_confirmed=150
    expect(matrix[1][6].value).toBe(0)     // 应付票据：无替代
    expect(matrix[2][6].value).toBe(0)     // 应付账款：无替代
    expect(matrix[3][6].value).toBe(1800)  // 本期采购：alt_confirmed=1800
  })

  it('矩阵入参不接受 altF05Totals/altF06Totals（防再次滑向编造分摊）', () => {
    // 传入也不应影响取值（类型上已移除，运行时忽略）
    const withAlt = buildF0SummaryMatrix({
      rows: SAMPLE_ROWS,
      // @ts-expect-error 已从 F0MatrixInput 移除
      altF05Totals: { total: 999999 },
      // @ts-expect-error 已从 F0MatrixInput 移除
      altF06Totals: { total: 888888 },
    })
    expect(withAlt[0][6].value).toBe(150)
    expect(withAlt[1][6].value).toBe(0)
  })

  it('仅 editable 行标记 editable=true', () => {
    const matrix = buildF0SummaryMatrix({ rows: SAMPLE_ROWS })
    for (const cells of matrix) {
      expect(cells[0].editable).toBe(true) // 账面金额可编辑
      for (let i = 1; i < 8; i++) {
        expect(cells[i].editable).toBe(false)
      }
    }
  })
})

// ─── Property 8: 替代确认勾稽（替代 distributeAltAmounts） ───────────────────

describe('Property 8: checkAltConsistency', () => {
  it('两侧相符 → ok（容差 0.01）', () => {
    // 上区 Y 列合计 = 150 + 1800 = 1950
    const r = checkAltConsistency({
      rows: SAMPLE_ROWS,
      altF05Totals: { total: 150 },
      altF06Totals: { total: 1800 },
    })
    expect(r.gridAltTotal).toBe(1950)
    expect(r.procedureTotal).toBe(1950)
    expect(r.level).toBe('ok')
    expect(r.diff).toBe(0)
  })

  it('两侧不符 → mismatch 且 diff 为有符号差异', () => {
    const r = checkAltConsistency({
      rows: SAMPLE_ROWS,
      altF05Totals: { total: 100 },
      altF06Totals: { total: 100 },
    })
    expect(r.level).toBe('mismatch')
    expect(r.diff).toBe(1750)
    expect(r.message).toContain('不符')
  })

  it('两侧都无数据 → no-data（不误报不符）', () => {
    const r = checkAltConsistency({ rows: [] })
    expect(r.level).toBe('no-data')
    expect(r.gridAltTotal).toBe(0)
    expect(r.procedureTotal).toBe(0)
  })

  it('只有上区有数据 → mismatch（提示替代程序底稿漏编）', () => {
    const r = checkAltConsistency({ rows: SAMPLE_ROWS })
    expect(r.level).toBe('mismatch')
    expect(r.gridAltTotal).toBe(1950)
    expect(r.procedureTotal).toBe(0)
  })

  it('0.01 以内视为相符', () => {
    const r = checkAltConsistency({
      rows: SAMPLE_ROWS,
      altF05Totals: { total: 150.005 },
      altF06Totals: { total: 1800 },
    })
    expect(r.level).toBe('ok')
  })

  it('浮点归一到两位小数不产出漂移', () => {
    const rows = [
      makeRow({ account_type: '预付账款', alt_confirmed: 0.1 }),
      makeRow({ account_type: '预付账款', alt_confirmed: 0.2 }),
    ]
    const r = checkAltConsistency({ rows, altF05Totals: { total: 0.3 } })
    expect(r.gridAltTotal).toBe(0.3)
    expect(r.level).toBe('ok')
  })
})

// ─── detectAltOverlapRows（R37 双算风险如实暴露，不改公式） ──────────────────

describe('detectAltOverlapRows', () => {
  it('U 与 Y 相等且非零的行被识别（积极式未回函派生）', () => {
    const overlap = detectAltOverlapRows(SAMPLE_ROWS)
    expect(overlap.length).toBe(2)
    expect(overlap.map(r => r.account_type).sort()).toEqual(['本期采购', '预付账款'])
  })

  it('U 与 Y 不等 → 不算重叠', () => {
    const rows = [makeRow({ account_type: '预付账款', confirmed_amount: 1000, alt_confirmed: 200 })]
    expect(detectAltOverlapRows(rows)).toHaveLength(0)
  })

  it('任一为 0 → 不算重叠（避免全表误报）', () => {
    const rows = [
      makeRow({ account_type: '预付账款', confirmed_amount: 0, alt_confirmed: 0 }),
      makeRow({ account_type: '预付账款', confirmed_amount: 500, alt_confirmed: 0 }),
    ]
    expect(detectAltOverlapRows(rows)).toHaveLength(0)
  })

  it('缺字段/非数值安全跳过', () => {
    const rows = [
      makeRow({ account_type: '预付账款' }),
      makeRow({ account_type: '预付账款', confirmed_amount: NaN, alt_confirmed: NaN }),
    ]
    expect(detectAltOverlapRows(rows)).toHaveLength(0)
  })
})

// ─── fetchTbAmountsForF0 ─────────────────────────────────────────────────────

describe('fetchTbAmountsForF0', () => {
  // 🔴 三个循环的键名各不相同（2026-08-03 后端源码实证 + 浏览器实测）：
  //    F1 = project_context.prepaid_tb_amount / F3 = tb_values['2201'] / F4 = project_context.tb_amount
  it('按各循环真实键名提取（不是统一的 tb_amount）', () => {
    const result = fetchTbAmountsForF0({
      'F1': { project_context: { prepaid_tb_amount: 100000 } },
      'F3': { tb_values: { '2201': 200000 } },
      'F4': { project_context: { tb_amount: 300000 } },
    })
    expect(result['预付账款']).toBe(100000)
    expect(result['应付票据']).toBe(200000)
    expect(result['应付账款']).toBe(300000)
    expect(result['本期采购']).toBeUndefined()
  })

  it('反向自检：旧口径（三者都读 project_context.tb_amount）只能取到 F4', () => {
    const legacyShape = {
      'F1': { project_context: { tb_amount: 100000 } },
      'F3': { project_context: { tb_amount: 200000 } },
      'F4': { project_context: { tb_amount: 300000 } },
    }
    const result = fetchTbAmountsForF0(legacyShape)
    expect(result['预付账款']).toBeUndefined() // F1 真实键是 prepaid_tb_amount
    expect(result['应付票据']).toBeUndefined() // F3 真实键是 tb_values['2201']
    expect(result['应付账款']).toBe(300000)    // 只有 F4 恰好对
  })

  it('F1 无 prepaid_tb_amount 时回退 prepaid_tb_leaf_amount（并列口径）', () => {
    const result = fetchTbAmountsForF0({ 'F1': { project_context: { prepaid_tb_leaf_amount: 55555 } } })
    expect(result['预付账款']).toBe(55555)
  })

  it('缺失返回 undefined 而非 0', () => {
    const result = fetchTbAmountsForF0({})
    expect(result['预付账款']).toBeUndefined()
    expect(result['应付票据']).toBeUndefined()
  })

  it('取到 0 要保留（余额为 0 ≠ 无此科目）', () => {
    const result = fetchTbAmountsForF0({ 'F3': { tb_values: { '2201': 0 } } })
    expect(result['应付票据']).toBe(0)
  })

  it('NaN/Infinity/非数值不进入结果', () => {
    const result = fetchTbAmountsForF0({
      'F1': { project_context: { prepaid_tb_amount: NaN } },
      'F3': { tb_values: { '2201': Infinity } },
      'F4': { project_context: { tb_amount: '不是数字' } },
    })
    expect(result['预付账款']).toBeUndefined()
    expect(result['应付票据']).toBeUndefined()
    expect(result['应付账款']).toBeUndefined()
  })
})

// ─── F0_BOOK_AMOUNT_SOURCES 常量完整性 ───────────────────────────────────────

describe('F0_BOOK_AMOUNT_SOURCES', () => {
  it('四品种全覆盖', () => {
    for (const cat of F0_MATRIX_CATEGORIES) {
      expect(cat in F0_BOOK_AMOUNT_SOURCES).toBe(true)
    }
  })

  it('本期采购无固定源（null）', () => {
    expect(F0_BOOK_AMOUNT_SOURCES['本期采购']).toBeNull()
  })

  it('其余三品种有 wpCode / hint / pick 三项', () => {
    for (const cat of ['预付账款', '应付票据', '应付账款'] as const) {
      const src = F0_BOOK_AMOUNT_SOURCES[cat]
      expect(src).not.toBeNull()
      expect(src!.wpCode).toBeTruthy()
      expect(src!.hint).toBeTruthy()
      expect(typeof src!.pick).toBe('function')
    }
  })

  it('wpCode 与报表行科目码对应（hint 必须含该科目码）', () => {
    expect(F0_BOOK_AMOUNT_SOURCES['预付账款']!.hint).toContain('1123')
    expect(F0_BOOK_AMOUNT_SOURCES['应付票据']!.hint).toContain('2201')
    expect(F0_BOOK_AMOUNT_SOURCES['应付账款']!.hint).toContain('2202')
  })

  it('三个 pick 互不相同（防又统一成 project_context.tb_amount）', () => {
    const probe = {
      project_context: { tb_amount: 1, prepaid_tb_amount: 2 },
      tb_values: { '2201': 3 },
    }
    expect(F0_BOOK_AMOUNT_SOURCES['预付账款']!.pick(probe)).toBe(2)
    expect(F0_BOOK_AMOUNT_SOURCES['应付票据']!.pick(probe)).toBe(3)
    expect(F0_BOOK_AMOUNT_SOURCES['应付账款']!.pick(probe)).toBe(1)
  })

  it('pick 对 undefined/空对象安全（不抛）', () => {
    for (const cat of ['预付账款', '应付票据', '应付账款'] as const) {
      expect(() => F0_BOOK_AMOUNT_SOURCES[cat]!.pick(undefined)).not.toThrow()
      expect(F0_BOOK_AMOUNT_SOURCES[cat]!.pick({})).toBeUndefined()
    }
  })
})
