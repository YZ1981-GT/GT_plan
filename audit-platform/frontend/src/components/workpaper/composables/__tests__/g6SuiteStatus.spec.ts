import { describe, expect, it } from 'vitest'
import { evaluateG6EclSuiteStatus, formatG6EclStatusRemark } from '../g6SuiteStatus'
import type { ChecklistResponse } from '../useF1FormData'
import { G6_ITEM_IDS } from '../g6StorageContract'

function responseMap(items: ChecklistResponse[]): Map<string, ChecklistResponse> {
  return new Map(items.map((item) => [item.item_id, item]))
}

function jsonItem(itemId: string, value: unknown): ChecklistResponse {
  const json = JSON.stringify(value)
  return { item_id: itemId, conclusion: json, remark: json }
}

describe('evaluateG6EclSuiteStatus', () => {
  it('识别 G6-11 有数据、G6-14 闸门失败', () => {
    const map = responseMap([
      jsonItem(G6_ITEM_IDS.G6_11_ROWS, [{
        investProject: '债A',
        auditStage: 'Stage1',
        companyStage: 'Stage1',
      }]),
      jsonItem(G6_ITEM_IDS.G6_14_DATA, {
        schemaVersion: 2,
        reversals: [{
          reversalAmount: 50,
          accumulatedProvision: 10,
          isReasonable: '合理',
        }],
        writeOffs: [],
        conclusion: '',
      }),
      {
        item_id: 'G6-11-audit-conclusion',
        conclusion: '阶段划分结论',
        remark: null,
      },
    ])
    const statuses = evaluateG6EclSuiteStatus(map)
    const g11 = statuses.find((s) => s.code === 'G6-11')!
    const g14 = statuses.find((s) => s.code === 'G6-14')!
    expect(g11.hasData).toBe(true)
    expect(g11.gate).toBe(true)
    expect(g11.conclusionComplete).toBe(true)
    expect(g11.tone).toBe('ok')
    expect(g14.hasData).toBe(true)
    expect(g14.gate).toBe(false)
    expect(g14.issues).toContain('质量闸门待处理')
  })

  it('G6-11 不一致缺差异说明时闸门失败', () => {
    const map = responseMap([
      jsonItem(G6_ITEM_IDS.G6_11_ROWS, [{
        investProject: '债A',
        companyStage: 'Stage1',
        auditStage: 'Stage2',
        discrepancyNote: '',
      }]),
    ])
    const g11 = evaluateG6EclSuiteStatus(map).find((s) => s.code === 'G6-11')!
    expect(g11.gate).toBe(false)
  })

  it('G6-12 缺阶段时闸门失败', () => {
    const map = responseMap([
      jsonItem(G6_ITEM_IDS.G6_12_DATA, {
        rows: [{ investProject: '债A', stage: '' }],
      }),
    ])
    const g12 = evaluateG6EclSuiteStatus(map).find((s) => s.code === 'G6-12')!
    expect(g12.hasData).toBe(true)
    expect(g12.gate).toBe(false)
  })

  it('识别 G6-15 异常缺说明', () => {
    const map = responseMap([
      jsonItem(G6_ITEM_IDS.G6_15_ROWS, [{
        voucherNo: 'PZ-1',
        isAbnormal: true,
        abnormalNote: '',
      }]),
    ])
    const g15 = evaluateG6EclSuiteStatus(map).find((s) => s.code === 'G6-15')!
    expect(g15.hasData).toBe(true)
    expect(g15.gate).toBe(false)
    expect(formatG6EclStatusRemark(g15)).toContain('闸门待办')
  })

  it('G6-14 合规数据闸门通过', () => {
    const map = responseMap([
      jsonItem(G6_ITEM_IDS.G6_14_DATA, {
        reversals: [{
          reversalAmount: 10,
          accumulatedProvision: 20,
          isReasonable: '合理',
        }],
        writeOffs: [{
          isRelatedParty: true,
          reasonAnalysis: '已专项复核',
          isReasonable: '合理',
        }],
      }),
      {
        item_id: 'G6-14-reversal-writeoff-conclusion',
        conclusion: '转回核销结论',
        remark: null,
      },
    ])
    const g14 = evaluateG6EclSuiteStatus(map).find((s) => s.code === 'G6-14')!
    expect(g14.gate).toBe(true)
    expect(g14.conclusionComplete).toBe(true)
    expect(g14.tone).toBe('ok')
  })
})
