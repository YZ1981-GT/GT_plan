/**
 * j1DisclosureDetailPull — 披露明细表「从 J1-2 明细带入」纯函数测试
 *
 * 行名映射的每条断言都对应源模板 Excel 公式（见被测模块头注释表格）：
 * - `A18='明细表J1-2 '!J13`（父行精确匹配，其下「其中：」子项不重复带入）
 * - `A21='明细表J1-2 '!J21+J22`（医疗保险费 ← 基本 + 补充医疗保险费）
 * - `A29='明细表J1-2 '!J26+J27`（工会经费和职工教育经费 ← 两行相加）
 * - 国企 `B28='明细表J1-2 '!J30+J31`（其他短期薪酬吸收非货币性福利）
 *
 * spec: .kiro/specs/j1-disclosure-template-alignment/（复盘 P1-a）
 */
import { describe, expect, it } from 'vitest'
import {
  applyDetailPullToDisclosureRows,
  auditedPullAmounts,
  J1_SOE_SHORT_TERM_ABSORB,
  MIN_CONTAIN_LEN,
  type J1DetailPullRow,
} from '../j1DisclosureDetailPull'
import type { J1DisclosureRow } from '../j1DisclosureRowModel'

// ─── 夹具 ────────────────────────────────────────────────────────────────

function row(label: string, indent = 0): J1DisclosureRow {
  return {
    id: `r-${label}-${indent}`,
    label,
    category: 'short_term',
    ...(indent ? { indent } : {}),
    beginBalance: 0,
    increase: 0,
    decrease: 0,
    endBalance: 0,
  }
}

function detail(
  label: string,
  begin: number,
  increase: number,
  decrease: number,
  isSubItem = false,
): J1DetailPullRow {
  return {
    label,
    isSubItem,
    indent: isSubItem ? 1 : 0,
    unadjBegin: begin,
    openingAdj: 0,
    unadjIncrease: increase,
    ajeIncrease: 0,
    unadjDecrease: decrease,
    ajeDecrease: 0,
  }
}

/** 披露表（上市）短期薪酬骨架，行序取自源模板 R18~R33 */
function listedShortTermRows(): J1DisclosureRow[] {
  return [
    row('工资、奖金、津贴和补贴'),
    row('职工福利费'),
    row('社会保险费'),
    row('其中：1．医疗保险费', 1),
    row('2．工伤保险费', 1),
    row('3．生育保险费', 1),
    row('住房公积金'),
    row('工会经费和职工教育经费'),
    row('短期带薪缺勤'),
    row('短期利润分享计划'),
    row('非货币性福利'),
    row('其他短期薪酬'),
  ]
}

/** J1-2 明细表短期薪酬分区（行名取自 `useJ1Detail.defaultRows`） */
function j12ShortTermDetail(): J1DetailPullRow[] {
  return [
    detail('工资、奖金、津贴和补贴', 100, 10, 4),
    detail('其中：1.工资', 60, 6, 2, true),
    detail('2.奖金', 40, 4, 2, true),
    detail('职工福利费', 20, 2, 1),
    detail('社会保险费', 30, 3, 1),
    detail('1.基本医疗保险费', 7, 1, 0, true),
    detail('2.补充医疗保险费', 3, 1, 0, true),
    detail('3.工伤保险费', 5, 0, 1, true),
    detail('4.生育保险费', 2, 1, 0, true),
    detail('住房公积金', 15, 1, 1),
    detail('工会经费', 4, 1, 0),
    detail('职工教育经费', 6, 2, 1),
    detail('短期带薪缺勤', 8, 1, 1),
    detail('短期利润分享计划', 9, 2, 0),
    detail('非货币性福利', 11, 3, 1),
    detail('其他短期薪酬', 12, 4, 2),
  ]
}

function byLabel(rows: J1DisclosureRow[], label: string): J1DisclosureRow {
  const hit = rows.find((r) => r.label === label)
  if (!hit) throw new Error(`未找到行：${label}`)
  return hit
}

// ─── 金额口径 ────────────────────────────────────────────────────────────

describe('auditedPullAmounts — 审定口径 = 未审 + 调整', () => {
  it('期初取 unadjBegin + openingAdj；增减各取未审 + AJE', () => {
    expect(
      auditedPullAmounts({
        unadjBegin: 100,
        openingAdj: 5,
        unadjIncrease: 20,
        ajeIncrease: 2,
        unadjDecrease: 8,
        ajeDecrease: 1,
      }),
    ).toEqual({ begin: 105, increase: 22, decrease: 9 })
  })

  it('缺字段 / 非数值一律按 0（不产生 NaN）', () => {
    expect(auditedPullAmounts({ unadjBegin: 'x', unadjIncrease: null })).toEqual({
      begin: 0,
      increase: 0,
      decrease: 0,
    })
  })
})

// ─── 精确匹配 ────────────────────────────────────────────────────────────

describe('精确匹配（源模板父行直引，如 A18=J1-2!J13）', () => {
  it('父行按归一名精确命中，期末自动派生', () => {
    const rows = listedShortTermRows()
    applyDetailPullToDisclosureRows(rows, j12ShortTermDetail())
    const wage = byLabel(rows, '工资、奖金、津贴和补贴')
    expect(wage.beginBalance).toBe(100)
    expect(wage.increase).toBe(10)
    expect(wage.decrease).toBe(4)
    expect(wage.endBalance).toBe(106) // 100 + 10 − 4
  })

  it('「其中：」序号前缀不影响匹配（工伤 / 生育保险费）', () => {
    const rows = listedShortTermRows()
    applyDetailPullToDisclosureRows(rows, j12ShortTermDetail())
    expect(byLabel(rows, '2．工伤保险费').beginBalance).toBe(5)
    expect(byLabel(rows, '3．生育保险费').beginBalance).toBe(2)
  })

  it('🔴 父行的「其中：」子项不重复带入到父行（否则父行双算）', () => {
    const rows = listedShortTermRows()
    applyDetailPullToDisclosureRows(rows, j12ShortTermDetail())
    // 工资 60 + 奖金 40 = 100 恰等于父行，若被叠加则会变成 200
    expect(byLabel(rows, '工资、奖金、津贴和补贴').beginBalance).toBe(100)
  })
})

// ─── 包含聚合 ────────────────────────────────────────────────────────────

describe('包含聚合（源模板 SUM 两个明细单元格）', () => {
  it('披露名 ⊂ 明细名：医疗保险费 ← 基本 + 补充医疗保险费（A21=J21+J22）', () => {
    const rows = listedShortTermRows()
    applyDetailPullToDisclosureRows(rows, j12ShortTermDetail())
    const medical = byLabel(rows, '其中：1．医疗保险费')
    expect(medical.beginBalance).toBe(10) // 7 + 3
    expect(medical.increase).toBe(2) // 1 + 1
  })

  it('明细名 ⊂ 披露名：工会经费和职工教育经费 ← 两行相加（A29=J26+J27）', () => {
    const rows = listedShortTermRows()
    applyDetailPullToDisclosureRows(rows, j12ShortTermDetail())
    const union = byLabel(rows, '工会经费和职工教育经费')
    expect(union.beginBalance).toBe(10) // 4 + 6
    expect(union.increase).toBe(3) // 1 + 2
    expect(union.decrease).toBe(1) // 0 + 1
  })

  it('社会保险费父行取明细父行值，与其中项之和自洽', () => {
    const rows = listedShortTermRows()
    applyDetailPullToDisclosureRows(rows, j12ShortTermDetail())
    const parent = byLabel(rows, '社会保险费')
    const children =
      byLabel(rows, '其中：1．医疗保险费').beginBalance +
      byLabel(rows, '2．工伤保险费').beginBalance +
      byLabel(rows, '3．生育保险费').beginBalance
    expect(parent.beginBalance).toBe(30)
    expect(children).toBe(17) // 10 + 5 + 2；差额为明细表其他险种，如实呈现不强配平
  })
})

// ─── 两字词与队列配对 ────────────────────────────────────────────────────

describe('「其他」只走精确匹配 + 队列配对', () => {
  const postRows = (): J1DisclosureRow[] => [
    { ...row('离职后福利'), category: 'post_employment' },
    { ...row('其中：基本养老保险费', 1), category: 'post_employment' },
    { ...row('失业保险费', 1), category: 'post_employment' },
    { ...row('企业年金缴费', 1), category: 'post_employment' },
    { ...row('其他', 1), category: 'post_employment' },
    { ...row('其他长期职工福利（不适用的删除）'), category: 'post_employment' },
    { ...row('其中：xxx', 1), category: 'post_employment' },
    { ...row('其他', 1), category: 'post_employment' },
  ]

  const postDetail = (): J1DetailPullRow[] => [
    detail('离职后福利', 50, 5, 2),
    detail('其中：1.基本养老保险', 30, 3, 1, true),
    detail('2.失业保险费', 10, 1, 0, true),
    detail('3.企业年金缴费', 8, 1, 1, true),
    detail('4.其他', 2, 0, 0, true),
    detail('其他长期职工福利', 40, 4, 1),
    detail('其中：1.xxx', 25, 2, 0, true),
    detail('2.其他', 15, 2, 1, true),
  ]

  it('两个「其他」按出现顺序配对，不互相串值', () => {
    const rows = postRows()
    applyDetailPullToDisclosureRows(rows, postDetail())
    const others = rows.filter((r) => r.label === '其他')
    expect(others).toHaveLength(2)
    expect(others[0].beginBalance).toBe(2) // 离职后福利下的 4.其他
    expect(others[1].beginBalance).toBe(15) // 其他长期职工福利下的 2.其他
  })

  it('「其他」不被「其他短期薪酬」「其他长期职工福利」包含匹配吸走', () => {
    expect('其他'.length).toBeLessThan(MIN_CONTAIN_LEN)
    const rows = postRows()
    applyDetailPullToDisclosureRows(rows, postDetail())
    expect(byLabel(rows, '其他长期职工福利（不适用的删除）').beginBalance).toBe(40)
  })

  it('基本养老保险费 ← 基本养老保险（包含匹配，明细名少一个「费」）', () => {
    const rows = postRows()
    applyDetailPullToDisclosureRows(rows, postDetail())
    expect(byLabel(rows, '其中：基本养老保险费').beginBalance).toBe(30)
  })

  it('「（不适用的删除）」尾注不影响匹配', () => {
    const rows = postRows()
    const res = applyDetailPullToDisclosureRows(rows, postDetail())
    expect(res.appended).toBe(0)
  })
})

// ─── 国企 absorb ─────────────────────────────────────────────────────────

describe('国企：其他短期薪酬吸收非货币性福利（B28=J30+J31）', () => {
  /** 国企骨架无独立「非货币性福利」行 */
  function soeShortTermRows(): J1DisclosureRow[] {
    return [
      row('工资、奖金、津贴和补贴'),
      row('职工福利费'),
      row('社会保险费'),
      row('其中：医疗保险费', 1),
      row('工伤保险费', 1),
      row('其他', 1),
      row('住房公积金'),
      row('工会经费和职工教育经费'),
      row('短期带薪缺勤'),
      row('短期利润分享计划'),
      row('其他短期薪酬'),
    ]
  }

  it('带 absorb 时合并为一行，不追加多余行', () => {
    const rows = soeShortTermRows()
    const res = applyDetailPullToDisclosureRows(rows, j12ShortTermDetail(), {
      absorb: J1_SOE_SHORT_TERM_ABSORB,
    })
    const other = byLabel(rows, '其他短期薪酬')
    expect(other.beginBalance).toBe(23) // 非货币 11 + 其他短期 12
    expect(other.increase).toBe(7) // 3 + 4
    expect(other.decrease).toBe(3) // 1 + 2
    expect(rows.some((r) => r.label === '非货币性福利')).toBe(false)
    expect(res.appended).toBe(0)
  })

  it('🔴 反向：不传 absorb 时非货币性福利会被追加成多余行（证明 absorb 必需）', () => {
    const rows = soeShortTermRows()
    const res = applyDetailPullToDisclosureRows(rows, j12ShortTermDetail())
    expect(byLabel(rows, '其他短期薪酬').beginBalance).toBe(12)
    expect(res.appended).toBe(1)
    expect(rows.some((r) => r.label === '非货币性福利')).toBe(true)
  })

  it('上市侧不得套用 absorb：非货币性福利是独立行（A32=J1-2!J30）', () => {
    const rows = listedShortTermRows()
    applyDetailPullToDisclosureRows(rows, j12ShortTermDetail())
    expect(byLabel(rows, '非货币性福利').beginBalance).toBe(11)
    expect(byLabel(rows, '其他短期薪酬').beginBalance).toBe(12)
  })
})

// ─── 未匹配处理 ──────────────────────────────────────────────────────────

describe('未匹配项：顶层追加 / 子项跳过', () => {
  it('未匹配的顶层非零明细行追加为新行（沿用 J1-7 范式）', () => {
    const rows = [row('工资、奖金、津贴和补贴')]
    const res = applyDetailPullToDisclosureRows(rows, [
      detail('工资、奖金、津贴和补贴', 100, 0, 0),
      detail('境外补贴', 33, 3, 1),
    ])
    expect(res.appended).toBe(1)
    const added = byLabel(rows, '境外补贴')
    expect(added.category).toBe('short_term')
    expect(added.endBalance).toBe(35) // 33 + 3 − 1
  })

  it('🔴 未匹配的「其中：」子项跳过而非追加（金额已含在父行，追加会双算）', () => {
    const rows = [row('其他短期薪酬')]
    const res = applyDetailPullToDisclosureRows(rows, [
      detail('其他短期薪酬', 12, 0, 0),
      detail('其中：以现金结算的股份支付', 5, 0, 0, true),
    ])
    expect(res.appended).toBe(0)
    expect(res.skippedSubItems).toEqual(['其中：以现金结算的股份支付'])
    expect(byLabel(rows, '其他短期薪酬').beginBalance).toBe(12)
    expect(rows).toHaveLength(1)
  })

  it('全零的未匹配行不追加（避免灌一堆空行）', () => {
    const rows = [row('职工福利费')]
    const res = applyDetailPullToDisclosureRows(rows, [detail('从未使用的项目', 0, 0, 0)])
    expect(res.appended).toBe(0)
    expect(rows).toHaveLength(1)
  })

  it('未匹配的披露行保持原值（不清零手工录入）', () => {
    const rows = listedShortTermRows()
    byLabel(rows, '短期带薪缺勤').beginBalance = 999
    applyDetailPullToDisclosureRows(rows, [detail('职工福利费', 20, 0, 0)])
    expect(byLabel(rows, '短期带薪缺勤').beginBalance).toBe(999)
  })

  it('明细为空时不改动任何行', () => {
    const rows = listedShortTermRows()
    const res = applyDetailPullToDisclosureRows(rows, [])
    expect(res).toEqual({ matched: 0, appended: 0, skippedSubItems: [] })
    expect(rows.every((r) => r.beginBalance === 0)).toBe(true)
  })
})

// ─── 两趟匹配（行序不影响结果） ──────────────────────────────────────────

describe('🔴 两趟匹配：精确优先，行序不影响结果', () => {
  it('包含聚合不会贪心吃掉后面行需要的精确匹配项', () => {
    // 「医疗保险费」若在第 1 趟就做包含聚合，可能吸走「基本医疗保险费」，
    // 但「基本医疗保险费」本身也是另一披露行的精确目标时必须留给它。
    const rows = [row('医疗保险费'), row('基本医疗保险费')]
    applyDetailPullToDisclosureRows(rows, [
      detail('基本医疗保险费', 7, 0, 0),
      detail('补充医疗保险费', 3, 0, 0),
    ])
    expect(byLabel(rows, '基本医疗保险费').beginBalance).toBe(7)
    expect(byLabel(rows, '医疗保险费').beginBalance).toBe(3) // 只剩补充
  })

  it('披露行倒序排列时结果一致（无行序依赖）', () => {
    const forward = listedShortTermRows()
    applyDetailPullToDisclosureRows(forward, j12ShortTermDetail())
    const reversed = listedShortTermRows().reverse()
    applyDetailPullToDisclosureRows(reversed, j12ShortTermDetail())
    for (const r of forward) {
      expect(byLabel(reversed, r.label).beginBalance).toBe(r.beginBalance)
    }
  })
})

// ─── 合计行 ──────────────────────────────────────────────────────────────

describe('合计行不参与带入', () => {
  it('isSubtotal 行被跳过，也不会被明细覆盖', () => {
    const rows: J1DisclosureRow[] = [
      row('职工福利费'),
      { ...row('合 计'), isSubtotal: true, beginBalance: 20 },
    ]
    applyDetailPullToDisclosureRows(rows, [detail('职工福利费', 20, 0, 0), detail('合 计', 99, 0, 0)])
    const total = rows.find((r) => r.isSubtotal)!
    expect(total.beginBalance).toBe(20)
  })
})
