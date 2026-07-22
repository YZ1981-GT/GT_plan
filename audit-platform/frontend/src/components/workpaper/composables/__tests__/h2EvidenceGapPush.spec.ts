/**
 * H2 证据缺口 → H2-3 推送
 */
import { describe, expect, it } from 'vitest'
import {
  H28_EVIDENCE_GAP_MARKER,
  H29_EVIDENCE_GAP_MARKER,
  buildEvidenceGapH23Row,
  collectDecreaseEvidenceGaps,
  evaluateAdditionEvidenceGaps,
  mergeEvidenceGapRowsToH23,
  type H2AdditionEvidenceGapRow,
} from '../h2EvidenceGapPush'

function baseAdditionRow(overrides: Partial<H2AdditionEvidenceGapRow> = {}): H2AdditionEvidenceGapRow {
  return {
    seq: 1,
    name: '车间改建',
    summary: '',
    amount: 100000,
    additionMethod: '出包',
    contractNo: '',
    progressDoc: '',
    materialDoc: '',
    invoiceNo: '',
    acceptanceDoc: '',
    paymentRef: '',
    approvalDoc: '',
    capitalizable: '',
    measurementConfirmed: '',
    progressConfirmed: '',
    ...overrides,
  }
}

describe('h2EvidenceGapPush', () => {
  it('H2-8 按增加方式识别适用证据缺口', () => {
    const gaps = evaluateAdditionEvidenceGaps(baseAdditionRow())
    expect(gaps).toContain('缺少合同/协议/订单')
    expect(gaps).toContain('缺少监理/进度(出包)')
    expect(gaps).toContain('审批文件未确认')
    expect(gaps).not.toContain('缺少领料单(自营)')

    const ok = evaluateAdditionEvidenceGaps(baseAdditionRow({
      contractNo: 'HT-001',
      progressDoc: '监理月报',
      invoiceNo: 'FP-001',
      paymentRef: 'FK-001',
      approvalDoc: 'Y',
      capitalizable: 'Y',
      measurementConfirmed: 'Y',
      progressConfirmed: 'Y',
    }))
    expect(ok).toHaveLength(0)
  })

  it('H2-9 转固样本审批/盖章缺口', () => {
    expect(collectDecreaseEvidenceGaps({
      missingApproval: true,
      missingStamps: true,
    })).toEqual(['审批未确认恰当', '验收盖章不全'])
  })

  it('构建 H2-3 说明行并替换同 marker 旧草稿', () => {
    const row = buildEvidenceGapH23Row({
      sourceSheet: 'H2-9',
      projectName: '码头',
      sampleLabel: '样本#2',
      gaps: ['审批未确认恰当'],
      seq: 3,
      marker: H29_EVIDENCE_GAP_MARKER,
    })
    expect(row.category).toBe('其他')
    expect(row.debitAmount).toBe(0)
    expect(row.indexRef).toBe('H2-9')
    expect(row.remark).toBe(H29_EVIDENCE_GAP_MARKER)
    expect(row.description).toContain('码头')

    const merged = mergeEvidenceGapRowsToH23(
      [
        { rowId: 'old', remark: H29_EVIDENCE_GAP_MARKER, seq: 1 },
        { rowId: 'keep', remark: 'manual', seq: 2 },
      ],
      [row],
      H29_EVIDENCE_GAP_MARKER,
    )
    expect(merged).toHaveLength(2)
    expect(merged.some((r) => r.rowId === 'old')).toBe(false)
    expect(merged.some((r) => r.rowId === 'keep')).toBe(true)
    expect(merged.some((r) => r.remark === H28_EVIDENCE_GAP_MARKER)).toBe(false)
  })
})
