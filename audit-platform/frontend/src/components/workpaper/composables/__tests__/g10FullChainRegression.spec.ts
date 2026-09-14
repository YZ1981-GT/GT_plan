/**
 * G10 全链路回归：推荐工作流 push + G10A mark 齐套 + 底稿目录勾稽
 *
 * 覆盖路径：
 * 辅助核算 → G10-2 → G10-1 → 附注
 * G10-5 公允差异 → G10-3 → G10-1 账项调整
 * G10-5 ↔ G10-2 · G10-8 → G10-2/G10-3
 * 八项 G10A mark → collectG10AProcedureMarks
 */
import { describe, expect, it } from 'vitest'
import {
  applyG10AdjustmentWritebacks,
  g10RowClosingAdjusted,
  parseG10AdjStore,
} from '../g10AdjStorage'
import { isFromG105 } from '../g10AdjSource'
import { summarizeG10CrossChecks } from '../g10CrossChecks'
import {
  G10_ADJ_ROWS_KEY,
  G10_ADJUDICATED_KEY,
  G10_DETAIL_ROWS_KEY,
  pushG10DetailToAdjudication,
  pushG10FvToDetail,
  seedG10DetailRowFromAux,
} from '../g10CrossHelpers'
import {
  summarizeG10DisclosureDirectoryStatus,
  syncG10DisclosureFromAdjudication,
} from '../g10DisclosureFromAdj'
import {
  pushG10DerivativeCheckToDetail,
  pushG10DerivativeIssuesToAdjustment,
} from '../g10DerivativeCross'
import {
  buildG10AdjustmentProcedureSummary,
  collectG10AProcedureMarks,
  G10A_ADJUDICATION_MARK_KEY,
  G10A_ADJUSTMENT_MARK_KEY,
  G10A_CLASSIFICATION_MARK_KEY,
  G10A_DETAIL_MARK_KEY,
  G10A_DISCLOSURE_MARK_KEY,
  G10A_DERIVATIVE_MARK_KEY,
  G10A_FV_MARK_KEY,
  G10A_VOUCHER_MARK_KEY,
  pushG10FvDiffToAdjustment,
} from '../g10FvCrossHelpers'
import { enrichG10VoucherRow } from '../useG10VoucherCheck'
import { pushG10VoucherAbnormalToAdjustment } from '../g10VoucherCross'
import { enrichG10DetailRow } from '../useG10Detail'
import type { ChecklistResponse } from '../useF1FormData'

function createResponseHarness() {
  const responses = new Map<string, ChecklistResponse>()
  const save = (id: string, data: Partial<ChecklistResponse>) => {
    const prev = responses.get(id) ?? {}
    responses.set(id, { ...prev, ...data })
  }
  return { responses, save }
}

function buildDerivativeDetailRow() {
  const seeded = seedG10DetailRowFromAux({
    liabilityName: '利率互换',
    openingBalance: 100,
    closingBalance: 180,
    auxType: '项目',
    auxCode: 'SWAP-001',
  }, 1)
  return enrichG10DetailRow({
    ...seeded,
    liabilityType: '衍生金融负债',
    isDerivative: true,
    hostContractDesc: '流动资金贷款',
  }, 1)
}

describe('G10 full-chain regression', () => {
  it('推荐工作流：辅助核算 → G10-2 → G10-1 → 附注分项', () => {
    const { responses, save } = createResponseHarness()
    const detailRow = buildDerivativeDetailRow()

    expect(detailRow.closingAdjusted).toBe(180)

    const n = pushG10DetailToAdjudication(responses, save, [detailRow])
    expect(n).toBe(1)

    const store = parseG10AdjStore(responses.get(G10_ADJ_ROWS_KEY)?.remark)
    expect(store.book_derivative_liability?.closingUnadjusted).toBe(180)
    expect(Number(responses.get(G10_ADJUDICATED_KEY)?.conclusion)).toBe(180)

    const disclosure = syncG10DisclosureFromAdjudication(
      [{ rowKey: 'book_derivative_liability', currentAmount: 0, priorAmount: 0 }],
      responses.get(G10_ADJ_ROWS_KEY)?.remark,
      { bookSectionOnly: true },
    )
    expect(disclosure[0].currentAmount).toBe(180)
    expect(disclosure[0].priorAmount).toBe(100)
  })

  it('G10-5 公允差异 → G10-3 → G10-1 账项调整（含 G10-5 来源识别）', () => {
    const { responses, save } = createResponseHarness()
    const detailRow = buildDerivativeDetailRow()
    pushG10DetailToAdjudication(responses, save, [detailRow])

    const pushed = pushG10FvDiffToAdjustment(
      responses,
      save,
      [{
        summary: 'G10-5 公允测试差异：利率互换',
        amount: 80,
        liabilityName: '利率互换',
        liabilityType: '衍生金融负债',
        indexRef: 'G10-5',
      }],
    )
    expect(pushed).toBe(1)

    const adjRows = JSON.parse(String(responses.get('G10-aje-rows')?.remark))
    expect(adjRows).toHaveLength(2)
    expect(adjRows.filter(isFromG105)).toHaveLength(2)

    const s = buildG10AdjustmentProcedureSummary({
      rowCount: adjRows.length,
      ajeCount: 2,
      rjeCount: 0,
      balanced: true,
      net2101: 80,
      fvPlNet: 80,
      writebackRows: 1,
      fromG105: 2,
      fromG104: 0,
      pendingG104: 0,
    })
    expect(s).toContain('G10-5 来源 2')

    const store = parseG10AdjStore(responses.get(G10_ADJ_ROWS_KEY)?.remark)
    expect(g10RowClosingAdjusted(store.book_derivative_liability ?? {})).toBe(260)
  })

  it('G10-5 ↔ G10-2 层次同步 + G10-8 → G10-2/G10-3', () => {
    const { responses, save } = createResponseHarness()
    const detailRow = buildDerivativeDetailRow()
    save(G10_DETAIL_ROWS_KEY, { remark: JSON.stringify([detailRow]) })

    const fvSynced = pushG10FvToDetail(
      responses,
      save,
      [{ liabilityName: '利率互换', fairValueLevel: 'Level3', valuationMethod: '现金流折现' }],
    )
    expect(fvSynced).toBe(1)
    const afterFv = JSON.parse(String(responses.get(G10_DETAIL_ROWS_KEY)?.remark))
    expect(afterFv[0].fairValueLevel).toBe('Level3')

    const derivSynced = pushG10DerivativeCheckToDetail(
      responses,
      save,
      {
        links: [{ detailRowId: detailRow.rowId, liabilityName: '利率互换' }],
        wizardConclusion: '应整体 FVTPL',
        overallConclusion: '未见异常',
      },
    )
    expect(derivSynced).toBe(1)
    const afterDeriv = JSON.parse(String(responses.get(G10_DETAIL_ROWS_KEY)?.remark))
    expect(afterDeriv[0].embeddedDerivativeJudgment).toContain('G10-8')

    pushG10DerivativeIssuesToAdjustment(
      responses,
      save,
      [{
        rowId: 'q1',
        sectionNo: '2',
        sectionTitle: '嵌入衍生',
        checkItem: '拆分',
        riskLevel: 'high',
        auditConclusion: '应拆分',
      }],
    )
    const adjRows = JSON.parse(String(responses.get('G10-aje-rows')?.remark))
    expect(adjRows.length).toBeGreaterThan(0)
    expect(String(adjRows[0].summary)).toContain('G10-8')
  })

  it('G10-7 + G10-8 推送后 CHK-10 识别来源与备忘', () => {
    const { responses, save } = createResponseHarness()
    pushG10VoucherAbnormalToAdjustment(
      responses,
      save,
      [enrichG10VoucherRow({
        id: 'v1',
        isAbnormal: true,
        check6FairValueCorrect: false,
        creditAmount: 200,
        voucherNo: '记-01',
        businessContent: '卖空',
      }, 1)],
    )
    pushG10DerivativeIssuesToAdjustment(
      responses,
      save,
      [{
        rowId: 'q1',
        sectionNo: '2',
        sectionTitle: '嵌入衍生',
        checkItem: '拆分',
        riskLevel: 'high',
        auditConclusion: '应拆分',
      }],
    )
    const chk10 = summarizeG10CrossChecks(responses).find((i) => i.code === 'G10-CHK-10')
    expect(chk10?.status).toBe('warn')
    expect(chk10?.detail).toContain('G10-7')
    expect(chk10?.detail).toContain('G10-8')
  })

  it('勾稽看板 CHK-01/03 在明细回写后一致', () => {
    const { responses, save } = createResponseHarness()
    const detailRow = buildDerivativeDetailRow()
    pushG10DetailToAdjudication(responses, save, [detailRow])

    save('G10-adj-tb', { remark: '180' })
    save('G10-detail-rows', { remark: JSON.stringify([detailRow]) })

    const checks = summarizeG10CrossChecks(responses)
    expect(checks.find((c) => c.code === 'G10-CHK-01')?.status).toBe('ok')
    expect(checks.find((c) => c.code === 'G10-CHK-03')?.status).toBe('ok')
  })

  it('G10A 八项 mark 齐套后目录汇总顺序固定', () => {
    const m = new Map<string, { conclusion?: string; remark?: string }>()
    const keys = [
      G10A_DETAIL_MARK_KEY,
      G10A_ADJUDICATION_MARK_KEY,
      G10A_ADJUSTMENT_MARK_KEY,
      G10A_DISCLOSURE_MARK_KEY,
      G10A_FV_MARK_KEY,
      G10A_CLASSIFICATION_MARK_KEY,
      G10A_DERIVATIVE_MARK_KEY,
      G10A_VOUCHER_MARK_KEY,
    ]
    for (const key of keys) {
      m.set(key, { conclusion: 'completed', remark: JSON.stringify({ at: '2026-01-01' }) })
    }

    const marks = collectG10AProcedureMarks(m)
    expect(marks).toHaveLength(8)
    expect(marks.map((x) => x.key)).toEqual([
      'detail',
      'adjudication',
      'adjustment',
      'disclosure',
      'fv',
      'classification',
      'derivative',
      'voucher',
    ])

    const programUnion = new Set(marks.flatMap((x) => [...x.programNos]))
    expect(programUnion.has(1)).toBe(true)
    expect(programUnion.has(3)).toBe(true)
    expect(programUnion.has(4)).toBe(true)
    expect(programUnion.has(14)).toBe(true)
  })

  it('附注目录状态与 G10-1 审定勾稽', () => {
    const { responses, save } = createResponseHarness()
    const detailRow = buildDerivativeDetailRow()
    pushG10DetailToAdjudication(responses, save, [detailRow])

    let store = parseG10AdjStore(responses.get(G10_ADJ_ROWS_KEY)?.remark)
    store = applyG10AdjustmentWritebacks(store, {
      byRow: { book_derivative_liability: { closingAje: 0, closingRje: 0 } },
    })
    save(G10_ADJ_ROWS_KEY, { remark: JSON.stringify(store) })

    const disc = summarizeG10DisclosureDirectoryStatus(responses)
    expect(disc.adjudicated).toBe(180)
    expect(disc.variants).toHaveLength(2)
    expect(disc.variants.map((v) => v.code)).toEqual(['附注上市', '附注国企'])
  })
})
