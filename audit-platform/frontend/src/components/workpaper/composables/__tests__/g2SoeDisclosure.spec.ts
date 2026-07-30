/**
 * G2 国企附注披露 — 章节映射 / 行结构 / 同步 payload 契约测试
 */
import { describe, it, expect } from 'vitest'
import {
  G2_COMBINED_DISCLOSURE_INDEX,
  G2_DISCLOSURE_SHEET_NAME,
  G2_NOTE_SECTION,
  isG2DisclosureApplicable,
  resolveG2NoteSectionTarget,
} from '../g2NoteSectionMap'
import {
  buildDefaultClassRows,
  buildDefaultEclRows,
  classifyDetailAmounts,
  extractAdjAmounts,
  extractOverdueFromG26,
  recomputeClassDerived,
  recomputeEclClosing,
  eclRowTotal,
} from '../g2SoeDisclosureRows'
import { buildG2SoeSyncPayloads, buildG2SoeSubTableData, buildG2ListedSyncPayloads } from '../g2DisclosureSyncPayload'

describe('g2NoteSectionMap', () => {
  it('国企映射到八、9，合计数索引映射 K1-1', () => {
    expect(G2_NOTE_SECTION.soe).toBe('八、9')
    expect(G2_COMBINED_DISCLOSURE_INDEX.excelLegacy).toBe('M1-1')
    expect(G2_COMBINED_DISCLOSURE_INDEX.wpCode).toBe('K1-1')
    const t = resolveG2NoteSectionTarget('soe', ['soe_standalone'])
    expect(t?.sectionId).toBe('八、9')
    expect(t?.combinedWpChip).toBe('wp:K1-1')
    expect(t?.combinedNoteChip).toBe('Note:八、9')
  })

  it('上市映射到五、8，合计数索引同样映射 K1-1（Excel M1-1）', () => {
    expect(G2_NOTE_SECTION.listed).toBe('五、8')
    const t = resolveG2NoteSectionTarget('listed', ['listed_standalone'])
    expect(t?.sectionId).toBe('五、8')
    expect(t?.chipValue).toBe('Note:五、8')
    expect(t?.combinedWpChip).toBe('wp:K1-1')
    expect(t?.combinedNoteChip).toBe('Note:五、8')
    // sheetName = 源 xlsx 真实 tab 名（非 `G2-note-listed` 合成标识）
    expect(t?.sheetName).toBe(G2_DISCLOSURE_SHEET_NAME.listed)
  })

  it('上市准则下国企页不适用', () => {
    expect(isG2DisclosureApplicable('soe', ['listed_standalone'])).toBe(false)
    expect(resolveG2NoteSectionTarget('soe', ['listed_standalone'])).toBeNull()
  })

  it('国企准则下上市页不适用', () => {
    expect(isG2DisclosureApplicable('listed', ['soe_standalone'])).toBe(false)
    expect(resolveG2NoteSectionTarget('listed', ['soe_standalone'])).toBeNull()
  })
})

describe('g2SoeDisclosureRows', () => {
  it('分类小计与合计 = 小计 − 坏账', () => {
    let rows = buildDefaultClassRows()
    rows = rows.map((r) => {
      if (r.rowKey === 'fixed-deposit') return { ...r, endAmount: 100, priorAmount: 80 }
      if (r.rowKey === 'bond') return { ...r, endAmount: 50, priorAmount: 40 }
      if (r.rowKey === 'provision') return { ...r, endAmount: 10, priorAmount: 5 }
      return r
    })
    rows = recomputeClassDerived(rows)
    const sub = rows.find((r) => r.rowKey === 'subtotal')!
    const total = rows.find((r) => r.rowKey === 'total')!
    expect(sub.endAmount).toBe(150)
    expect(total.endAmount).toBe(140)
    expect(total.priorAmount).toBe(115)
  })

  it('ECL 期末 = 期初 + 计提 − 转回等', () => {
    let rows = buildDefaultEclRows()
    rows = rows.map((r) => {
      if (r.rowKey === 'opening') return { ...r, stage1: 100, stage2: 20, stage3: 0 }
      if (r.rowKey === 'provision') return { ...r, stage1: 10, stage2: 5, stage3: 0 }
      if (r.rowKey === 'reversal') return { ...r, stage1: 3, stage2: 0, stage3: 0 }
      return r
    })
    rows = recomputeEclClosing(rows)
    const closing = rows.find((r) => r.rowKey === 'closing')!
    expect(closing.stage1).toBe(107)
    expect(closing.stage2).toBe(25)
    expect(eclRowTotal(closing)).toBe(132)
  })

  it('从审定 store 提取坏账与原值', () => {
    const store = JSON.stringify({
      'gross-individual': { openingUnadjusted: 10, openingAdjustment: 0, closingUnadjusted: 20, closingAdjustment: 0 },
      'gross-collective': { openingUnadjusted: 30, openingAdjustment: 0, closingUnadjusted: 40, closingAdjustment: 0 },
      'provision-individual': { openingUnadjusted: 1, openingAdjustment: 0, closingUnadjusted: 2, closingAdjustment: 0 },
      'provision-collective': { openingUnadjusted: 3, openingAdjustment: 0, closingUnadjusted: 4, closingAdjustment: 0 },
    })
    const amt = extractAdjAmounts(store)
    expect(amt.grossEnd).toBe(60)
    expect(amt.provisionEnd).toBe(6)
    expect(amt.netEnd).toBe(54)
  })

  it('明细 investType 归集到分类', () => {
    const raw = JSON.stringify([
      { investType: '定期存款', closingAudited: 100, openingAudited: 80 },
      { investType: '债券投资A', bookValue: 50 },
      { investType: '其他杂项', netReceivable: 7 },
    ])
    const c = classifyDetailAmounts(raw)
    expect(c['fixed-deposit'].endAmount).toBe(100)
    expect(c['fixed-deposit'].priorAmount).toBe(80)
    expect(c.bond.endAmount).toBe(50)
    expect(c.other.endAmount).toBe(7)
  })
})

describe('G2-6 → 附注②逾期', () => {
  it('提取一年以上/无法收回行', () => {
    const raw = JSON.stringify([
      {
        id: '1',
        debtorName: '甲公司',
        aging: '1-2年',
        auditedBalance: 1000,
        unrecoveredReason: '资金紧张',
        isUncollectible: '否',
      },
      {
        id: '2',
        debtorName: '乙公司',
        aging: '1年以内',
        auditedBalance: 500,
        unrecoveredReason: '',
        isUncollectible: '',
      },
      {
        id: '3',
        debtorName: '丙公司',
        aging: '1年以内',
        auditedBalance: 200,
        unrecoveredReason: '',
        isUncollectible: '是',
      },
    ])
    const rows = extractOverdueFromG26(raw)
    expect(rows.map((r) => r.borrower).sort()).toEqual(['丙公司', '甲公司'])
    expect(rows.find((r) => r.borrower === '甲公司')!.endAmount).toBe(1000)
  })
})

describe('g2DisclosureSyncPayload', () => {
  it('构建八、9 三张子表', () => {
    const classRows = recomputeClassDerived(
      buildDefaultClassRows().map((r) =>
        r.rowKey === 'fixed-deposit' ? { ...r, endAmount: 100, priorAmount: 80 } : r,
      ),
    )
    const payloads = buildG2SoeSyncPayloads('wp-1', ['soe_standalone'], {
      classRows,
      overdueRows: [{ id: '1', borrower: '甲公司', endAmount: 10, overdueMonths: 6, overdueReason: '资金紧张', impairmentBasis: '未减值' }],
      eclRows: buildDefaultEclRows(),
      auditNote: '测试',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('八、9')
    const sub = buildG2SoeSubTableData({
      classRows,
      overdueRows: [],
      eclRows: buildDefaultEclRows(),
      auditNote: '',
    })
    expect(sub['应收利息分类']?.length).toBeGreaterThan(0)
    expect(sub['重要逾期利息']).toBeDefined()
    expect(sub['坏账准备计提情况']).toBeDefined()
  })

  it('构建五、8 上市同步 payload', () => {
    const payloads = buildG2ListedSyncPayloads('wp-listed', ['listed_standalone'], {
      classRows: buildDefaultClassRows(),
      overdueRows: [],
      eclRows: buildDefaultEclRows(),
      auditNote: '上市说明',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('五、8')
    expect(payloads[0].sheet_name).toBe(G2_DISCLOSURE_SHEET_NAME.listed)
    expect(payloads[0].current_standard).toBe('listed_standalone')
    expect(payloads[0].sub_table_data._note_texts?.[0]).toMatchObject({
      section: 'listed-audit-note',
      text: '上市说明',
    })
  })
})
