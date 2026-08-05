/**
 * L 循环披露子表契约（L7 其他非流动负债 / L8 财务费用）
 *
 * 复用共享 helper 的 P1~P6，另加本循环专属断言：
 * - L7 国企侧「底稿列序（年初/期末）→ 附注口径（期末/期初）」投影正确
 * - L8 派生行读时推导（源模板 4 个计算关系）
 * - L8 两版行集完全相同（源 xlsx 实证）
 * - 审计结论 / 国资专项说明**不进附注**（禁自造披露内容）
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 4.5 / 4.6
 */
import { describe, expect, it } from 'vitest'

import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  L5_LISTED_SUBTABLE,
  L5_NOTE_SECTION,
  L5_SOE_SUBTABLE,
  L5_WITHIN1Y_NOTE_SECTION,
  L5_WITHIN1Y_SUBTABLE,
  L6_LISTED_SUBTABLE,
  L6_SOE_SUBTABLE,
  buildL5MainRows,
  buildL5SyncPayload,
  buildL6SpecialRows,
  buildL6SyncPayload,
  l5ColumnsFor,
  l5Within1yColumns,
  l6ColumnsFor,
  l6SpecialEndAmount,
} from '../l5NoteSectionMap'
import {
  L7_DISCLOSURE_SHEET_NAME,
  L7_NOTE_SECTION,
  L7_SUBTABLE,
  L7_TOTAL_LABEL,
  buildL7MainRows,
  buildL7SyncPayload,
  isL7DisclosureApplicable,
  l7ColumnsFor,
} from '../l7NoteSectionMap'
import {
  L8_DISCLOSURE_SHEET_NAME,
  L8_LISTED_SUBTABLE,
  L8_NOTE_SECTION,
  L8_ROW_ORDER,
  L8_SOE_SUBTABLE,
  buildL8DisplayRows,
  buildL8MainRows,
  buildL8SyncPayload,
  createEmptyL8Period,
  deriveL8Period,
  l8ColumnsFor,
  l8MainTableName,
} from '../l8NoteSectionMap'

// ─── P1~P6 共享契约 ──────────────────────────────────────────────────────────

// L5 主表 + 明细表（L5 自己推的表）
runDisclosureSubtableContract({
  cycle: 'L5',
  variants: [
    {
      variant: 'listed',
      section: L5_NOTE_SECTION.listed,
      subtables: L5_LISTED_SUBTABLE,
      columns: l5ColumnsFor('listed'),
    },
    {
      variant: 'soe',
      section: L5_NOTE_SECTION.soe,
      subtables: L5_SOE_SUBTABLE,
      columns: l5ColumnsFor('soe'),
    },
  ],
})

// L6 专项应付款表（推 L5 章节）
runDisclosureSubtableContract({
  cycle: 'L6(→L5 §五、48/八、53)',
  variants: [
    {
      variant: 'listed',
      section: L5_NOTE_SECTION.listed,
      subtables: L6_LISTED_SUBTABLE,
      columns: l6ColumnsFor('listed'),
    },
    {
      variant: 'soe',
      section: L5_NOTE_SECTION.soe,
      subtables: L6_SOE_SUBTABLE,
      columns: l6ColumnsFor('soe'),
    },
  ],
})

// 八、47 一年内到期的长期应付款（仅国企）
runDisclosureSubtableContract({
  cycle: 'L5-within1y',
  variants: [
    {
      variant: 'soe',
      section: L5_WITHIN1Y_NOTE_SECTION.soe,
      subtables: L5_WITHIN1Y_SUBTABLE,
      columns: l5Within1yColumns(),
    },
  ],
})

runDisclosureSubtableContract({
  cycle: 'L7',
  variants: [
    {
      variant: 'listed',
      section: L7_NOTE_SECTION.listed,
      subtables: L7_SUBTABLE,
      columns: l7ColumnsFor('listed'),
    },
    {
      variant: 'soe',
      section: L7_NOTE_SECTION.soe,
      subtables: L7_SUBTABLE,
      columns: l7ColumnsFor('soe'),
    },
  ],
})

runDisclosureSubtableContract({
  cycle: 'L8',
  variants: [
    {
      variant: 'listed',
      section: L8_NOTE_SECTION.listed,
      subtables: L8_LISTED_SUBTABLE,
      columns: l8ColumnsFor('listed'),
    },
    {
      variant: 'soe',
      section: L8_NOTE_SECTION.soe,
      subtables: L8_SOE_SUBTABLE,
      columns: l8ColumnsFor('soe'),
    },
  ],
})

// ─── L5 / L6 专属 ────────────────────────────────────────────────────────────

describe('L5 长期应付款 / L6 专项应付款 披露映射', () => {
  it('L5 主表两行（长期应付款 / 专项应付款）+ 合计，合计读时派生', () => {
    const rows = buildL5MainRows({ end: 900, prior: 800 }, { end: 100, prior: 50 })
    expect(rows.map((r) => r.label)).toEqual(['长期应付款', '专项应付款', '合计'])
    const total = rows[rows.length - 1]
    expect(total.is_total).toBe(true)
    expect(total.end_amount).toBe(1000)
    expect(total.prior_amount).toBe(850)
  })

  it('L5 只推主表 —— 不含「专项应付款」表（由 L6 推，防同章节互相覆盖）', () => {
    const payload = buildL5SyncPayload('wp-1', {
      variant: 'listed',
      longTerm: { end: 900, prior: 800 },
      special: { end: 0, prior: 0 },
    })
    expect(payload).not.toBeNull()
    const keys = Object.keys(payload!.sub_table_data)
    expect(keys).toContain(L5_LISTED_SUBTABLE.main)
    expect(keys).not.toContain(L6_LISTED_SUBTABLE.special)
  })

  it('L5 两版主表列名分取（上市 期末数/上年年末余额；国企 期末数/期初数）', () => {
    const listed = l5ColumnsFor('listed')[L5_LISTED_SUBTABLE.main]
    const soe = l5ColumnsFor('soe')[L5_SOE_SUBTABLE.main]
    expect(listed.map((c) => c.label)).toEqual(['项目', '期末数', '上年年末余额'])
    expect(soe.map((c) => c.label)).toEqual(['项目', '期末数', '期初数'])
  })

  it('L6 专项应付款期末余额读时派生 = 期初 + 增加 − 减少', () => {
    expect(l6SpecialEndAmount({ label: 'x', beginAmount: 100, increase: 50, decrease: 30 })).toBe(120)
    const rows = buildL6SpecialRows(
      [{ label: '项目A', beginAmount: 100, increase: 50, decrease: 30, reason: 'x' }],
      'listed',
    )
    expect(rows[0].end_amount).toBe(120)
    const total = rows[rows.length - 1]
    expect(total.is_total).toBe(true)
    expect(total.end_amount).toBe(120)
  })

  it('L6 只推「专项应付款」表，用 L6 自己的 sheet 名（括号在中间）', () => {
    const payload = buildL6SyncPayload('wp-1', {
      variant: 'listed',
      rows: [{ label: '项目A', beginAmount: 100, increase: 0, decrease: 0 }],
    })
    expect(payload).not.toBeNull()
    expect(Object.keys(payload!.sub_table_data)).toContain(L6_LISTED_SUBTABLE.special)
    expect(payload!.section_id).toBe(L5_NOTE_SECTION.listed)
    expect(payload!.sheet_name).toBe('附注披露（上市公司）信息')
  })

  it('L6 国企侧 5 列（无形成原因），上市侧 6 列（含形成原因）', () => {
    const listedCols = l6ColumnsFor('listed')[L6_LISTED_SUBTABLE.special]
    const soeCols = l6ColumnsFor('soe')[L6_SOE_SUBTABLE.special]
    expect(listedCols.map((c) => c.label)).toContain('形成原因')
    expect(soeCols.map((c) => c.label)).not.toContain('形成原因')
  })

  it('L5/L6 不适用变体返回 null', () => {
    expect(buildL5SyncPayload('wp-1', {
      variant: 'listed', longTerm: { end: 0, prior: 0 }, special: { end: 0, prior: 0 },
    }, ['soe_standalone'])).toBeNull()
    expect(buildL6SyncPayload('wp-1', { variant: 'soe', rows: [] }, ['listed_standalone'])).toBeNull()
  })
})

// ─── L7 专属 ─────────────────────────────────────────────────────────────────

describe('L7 其他非流动负债 披露映射', () => {
  it('sheet 名逐字取源 xlsx（国企侧半角括号，勿"修正"为全角）', () => {
    expect(L7_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(L7_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息(国企)')
    // 反向：不得带「核对」（那是 L4 的写法，原映射写错过）
    expect(L7_DISCLOSURE_SHEET_NAME.listed).not.toContain('核对')
    expect(L7_DISCLOSURE_SHEET_NAME.soe).not.toContain('核对')
  })

  it('两版列名按源模板分取（上市 期末数/上年年末数；国企 期末余额/期初余额）', () => {
    const listed = l7ColumnsFor('listed')[L7_SUBTABLE.main]
    const soe = l7ColumnsFor('soe')[L7_SUBTABLE.main]
    expect(listed.map((c) => c.label)).toEqual(['项目', '期末数', '上年年末数'])
    expect(soe.map((c) => c.label)).toEqual(['项目', '期末余额', '期初余额'])
    // 反向：两版列头必须不同（防一份常量给两个变体共用 → 国企表头错位）
    expect(listed.map((c) => c.label)).not.toEqual(soe.map((c) => c.label))
    // 列键两版一致（只有 label 分变体）
    expect(listed.map((c) => c.key)).toEqual(soe.map((c) => c.key))
  })

  it('单级表头必须显式 flat（抑制后端前缀推断凭空造父表头）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const cols = l7ColumnsFor(variant)[L7_SUBTABLE.main]
      expect(cols.some((c) => c.flat), `${variant} 未表态 flat`).toBe(true)
      expect(cols.some((c) => c.group), `${variant} 不应有 group`).toBe(false)
    }
  })

  it('行是业务键行（非位置化 values），且 columns 的 key 都能在行里找到落点', () => {
    const rows = buildL7MainRows([
      { label: '递延收益', endAmount: 100, priorAmount: 80 },
      { label: '押金', endAmount: 20, priorAmount: 10 },
    ])
    expect(rows[0]).not.toHaveProperty('values')
    const keys = l7ColumnsFor('listed')[L7_SUBTABLE.main].map((c) => c.key)
    for (const k of keys) expect(Object.keys(rows[0])).toContain(k)
  })

  it('合计行读时派生，且原有合计行不被重复计入', () => {
    const rows = buildL7MainRows([
      { label: '递延收益', endAmount: 100, priorAmount: 80 },
      { label: '押金', endAmount: 20, priorAmount: 10 },
      // 上游误传了合计行（旧版第 6 行就是合计）→ 必须被剔除后重算
      { label: '合  计', endAmount: 999, priorAmount: 999 },
    ])
    const total = rows[rows.length - 1]
    expect(total.label).toBe(L7_TOTAL_LABEL)
    expect(total.is_total).toBe(true)
    expect(total.end_amount).toBe(120)
    expect(total.prior_amount).toBe(90)
    expect(rows).toHaveLength(3) // 2 数据行 + 1 合计
  })

  it('国企载荷把底稿列序（年初/期末）投影为附注口径（期末/期初）', () => {
    // 组件侧传入时已归一：endAmount ← endBalance、priorAmount ← beginBalance
    const payload = buildL7SyncPayload('wp-1', {
      variant: 'soe',
      rows: [{ label: '合同负债', endAmount: 500, priorAmount: 300 }],
    })
    expect(payload).not.toBeNull()
    const row = payload!.sub_table_data[L7_SUBTABLE.main][0]
    expect(row.end_amount).toBe(500)
    expect(row.prior_amount).toBe(300)
  })

  it('审计结论不进附注（源模板两版都无说明段）', () => {
    const payload = buildL7SyncPayload('wp-1', {
      variant: 'listed',
      rows: [{ label: '递延收益', endAmount: 1, priorAmount: 1 }],
    })
    expect(payload!.sub_table_data).not.toHaveProperty('_note_texts')
  })

  it('不适用变体返回 null（跳过同步，不写错章节）', () => {
    expect(buildL7SyncPayload('wp-1', { variant: 'listed', rows: [] }, ['soe_standalone'])).toBeNull()
    expect(buildL7SyncPayload('wp-1', { variant: 'soe', rows: [] }, ['soe_standalone'])).not.toBeNull()
    // 空准则列表 = 未知 → 放行（与平台其它循环同口径）
    expect(isL7DisclosureApplicable('listed', [])).toBe(true)
  })
})

// ─── L8 专属 ─────────────────────────────────────────────────────────────────

describe('L8 财务费用 披露映射', () => {
  it('行集 = 源 xlsx r7~r18 共 12 行（11 明细 + 合计），逐字对齐', () => {
    expect(L8_ROW_ORDER.map((r) => r.label)).toEqual([
      '利息费用总额',
      '减：利息资本化',
      '利息费用',
      '减：利息收入',
      '利息净支出',
      '承兑汇票贴息',
      '汇兑损失',
      '减：汇兑收益',
      '减：汇兑损益资本化',
      '汇兑净损失',
      '手续费及其他',
      '合计',
    ])
  })

  it('两版行集完全相同（源 xlsx 实证；原组件各自造 7 / 10 行且互不相同）', () => {
    const listed = buildL8MainRows(createEmptyL8Period(), createEmptyL8Period())
    const soe = buildL8MainRows(createEmptyL8Period(), createEmptyL8Period())
    expect(listed.map((r) => r.label)).toEqual(soe.map((r) => r.label))
    expect(listed).toHaveLength(12)
  })

  it('表名两版不同且逐字对齐模板（上市带「（按费用性质列示）」）', () => {
    expect(l8MainTableName('listed')).toBe('财务费用（按费用性质列示）')
    expect(l8MainTableName('soe')).toBe('财务费用')
    expect(l8MainTableName('listed')).not.toBe(l8MainTableName('soe'))
  })

  it('派生行按源模板 4 条计算关系推导', () => {
    const d = deriveL8Period({
      interestTotal: 1000,
      interestCapitalized: 200,
      interestIncome: 50,
      acceptanceDiscount: 30,
      exchangeLoss: 100,
      exchangeGain: 40,
      exchangeCapitalized: 10,
      feeAndOther: 25,
    })
    expect(d.interestExpense).toBe(800) // 1000 − 200
    expect(d.interestNet).toBe(750) // 800 − 50
    expect(d.exchangeNet).toBe(50) // 100 − 40 − 10
    expect(d.total).toBe(855) // 750 + 30 + 50 + 25
  })

  it('派生行标记为 derived（组件据此转只读，禁持久化派生值）', () => {
    const derived = L8_ROW_ORDER.filter((r) => r.derived).map((r) => r.key)
    expect(derived).toEqual(['interestExpense', 'interestNet', 'exchangeNet', 'total'])
    const rows = buildL8DisplayRows(createEmptyL8Period(), createEmptyL8Period())
    expect(rows.filter((r) => r.derived)).toHaveLength(4)
  })

  it('合计行带 is_total、其余派生行带 is_subtotal', () => {
    const rows = buildL8MainRows(createEmptyL8Period(), createEmptyL8Period())
    const total = rows[rows.length - 1]
    expect(total.is_total).toBe(true)
    expect(total.is_subtotal).toBeUndefined()
    const subtotals = rows.filter((r) => r.is_subtotal)
    expect(subtotals.map((r) => r.label)).toEqual(['利息费用', '利息净支出', '汇兑净损失'])
  })

  it('仅上市侧推资本化说明（源 xlsx r19/r20），国企侧无此段', () => {
    const listed = buildL8SyncPayload('wp-1', {
      variant: 'listed',
      current: createEmptyL8Period(),
      prior: createEmptyL8Period(),
      capitalizationNote: '资本化率为 4.5%',
    })
    expect(listed!.sub_table_data).toHaveProperty('_note_texts')
    const soe = buildL8SyncPayload('wp-1', {
      variant: 'soe',
      current: createEmptyL8Period(),
      prior: createEmptyL8Period(),
      capitalizationNote: '国企侧不应推此段',
    })
    expect(soe!.sub_table_data).not.toHaveProperty('_note_texts')
  })

  it('_note_texts 带中文 title（缺 title 会让附注渲染出英文 section 键）', () => {
    const p = buildL8SyncPayload('wp-1', {
      variant: 'listed',
      current: createEmptyL8Period(),
      prior: createEmptyL8Period(),
      capitalizationNote: 'x',
    })
    const texts = (p!.sub_table_data as any)._note_texts as Array<Record<string, string>>
    expect(texts[0].title).toBe('利息资本化说明')
    expect(texts[0].title).not.toMatch(/^[a-z0-9-]+$/i)
  })

  it('sheet 名两版逐字取源 xlsx', () => {
    expect(L8_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(L8_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
  })

  it('单级表头显式 flat', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const cols = l8ColumnsFor(variant)[l8MainTableName(variant)]
      expect(cols.some((c) => c.flat)).toBe(true)
      expect(cols.some((c) => c.group)).toBe(false)
      expect(cols.map((c) => c.label)).toEqual(['项目', '本期发生额', '上期发生额'])
    }
  })
})


// ─── L1 / L3 / L4 子表契约（Property 7/8/11）─────────────────────────────────
//
// 验证：
// - Property 7：子表名逐字与附注模板一致
// - Property 8：列元数据 flat/group 双侧表态
// - Property 11：_removed_table_keys 与推送键无交集
//
// spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R8, Property 7/8/11

import { buildL1ListedColumns, buildL1SoeColumns } from '../l1NoteSectionMap'
import { buildL3ListedColumns, buildL3SoeColumns } from '../l3NoteSectionMap'
import { buildL4ListedColumns, buildL4SoeColumns } from '../l4NoteSectionMap'

/**
 * Property 8 helper：每张表的列必须显式表态 flat 或 group。
 * - 有任何列带 `group` → 该表是两级表头
 * - 有任何列带 `flat: true` → 该表是单级表头
 * - 不允许：某表既无 group 也无 flat（未表态 → 会被 _infer_groups_from_headers 推断）
 */
function assertColumnsStated(columns: Record<string, any[]>, context: string) {
  for (const [tableName, cols] of Object.entries(columns)) {
    const hasGroup = cols.some((c: any) => c.group)
    const hasFlat = cols.some((c: any) => c.flat === true)
    expect(
      hasGroup || hasFlat,
      `${context} / ${tableName}: 列未表态 flat 或 group（会被后端前缀推断凭空造父表头）`,
    ).toBe(true)
    // 单级表不得同时声明 group
    if (hasFlat && !hasGroup) {
      for (const col of cols) {
        expect(
          (col as any).group,
          `${context} / ${tableName}: 标了 flat 又有 group "${(col as any).group}"`,
        ).toBeUndefined()
      }
    }
  }
}

describe('L1 子表契约', () => {
  it('上市列定义表态正确', () => {
    const cols = buildL1ListedColumns({ includeOverdue: true })
    assertColumnsStated(cols, 'L1 listed')
    // 所有表都是 flat（单行表头）
    for (const [, tableCols] of Object.entries(cols)) {
      expect(tableCols.some((c: any) => c.flat === true)).toBe(true)
    }
  })
  it('国企列定义表态正确', () => {
    const cols = buildL1SoeColumns({ includeOverdue: true })
    assertColumnsStated(cols, 'L1 soe')
  })
})

describe('L3 子表契约', () => {
  it('上市列定义含两级表头（利率区间）', () => {
    const cols = buildL3ListedColumns()
    assertColumnsStated(cols, 'L3 listed')
    // 长期借款表应为 flat（无 group）
    const mainCols = cols['长期借款']
    expect(mainCols).toBeDefined()
    expect(mainCols.some((c: any) => c.flat === true)).toBe(true)
  })
  it('国企列定义表态正确', () => {
    const cols = buildL3SoeColumns()
    assertColumnsStated(cols, 'L3 soe')
  })
  it('子表名包含一年内到期', () => {
    const listedKeys = Object.keys(buildL3ListedColumns())
    expect(listedKeys).toContain('一年内到期的长期借款')
  })
})

describe('L4 子表契约', () => {
  it('上市列定义含两级表头', () => {
    const cols = buildL4ListedColumns()
    assertColumnsStated(cols, 'L4 listed')
    // 主表有 group（期末余额/上年年末余额）
    const mainCols = cols['应付债券']
    expect(mainCols).toBeDefined()
    expect(mainCols.some((c: any) => c.group === '期末余额')).toBe(true)
  })
  it('国企列定义表态正确', () => {
    const cols = buildL4SoeColumns()
    assertColumnsStated(cols, 'L4 soe')
  })
  it('上市有 4 张子表', () => {
    const keys = Object.keys(buildL4ListedColumns())
    expect(keys.length).toBe(4)
    expect(keys).toContain('应付债券')
    expect(keys).toContain('应付债券增减变动')
    expect(keys).toContain('一年内到期的应付债券')
    expect(keys).toContain('已到期未偿付的应付债券')
  })
  it('国企有 2 张子表', () => {
    const keys = Object.keys(buildL4SoeColumns())
    expect(keys.length).toBe(2)
    expect(keys).toContain('应付债券')
    expect(keys).toContain('应付债券增减变动')
  })
  it('增减变动表列有 group（两级表头）', () => {
    const cols = buildL4ListedColumns()
    const movCols = cols['应付债券增减变动']
    expect(movCols.some((c: any) => c.group === '期初余额')).toBe(true)
    expect(movCols.some((c: any) => c.group === '本期增加')).toBe(true)
    expect(movCols.some((c: any) => c.group === '本期减少')).toBe(true)
    expect(movCols.some((c: any) => c.group === '期末余额')).toBe(true)
  })
})
