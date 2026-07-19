import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { buildCanonicalPayload, G4_ITEM_IDS, parseCanonicalArray, parseCanonicalJson } from '../g4StorageContract'
import type { ChecklistResponse } from '../useF1FormData'

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }))

vi.mock('@/services/apiProxy', () => ({
  api: { get: getMock },
}))

import { useG4PriorYearRollForward } from '../useG4PriorYearRollForward'

describe('useG4PriorYearRollForward', () => {
  beforeEach(() => {
    getMock.mockReset()
  })

  it('通过 prior wp_id 回退获取 checklist 并生成三类预览', async () => {
    getMock
      .mockResolvedValueOnce({ wp_id: 'prior-wp', wp_code: 'G4' })
      .mockResolvedValueOnce([
        buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, [{
          id: 'bond-1',
          investProject: '债券A',
          closingCost: 120,
          closingInterestAdj: -2,
          closingAccruedInterest: 3,
          closingImpairment: 5,
          amortizedCost: 116,
          oneYearSubtotal: 10,
          closingAdjustment: 0,
          closingAudited: 121,
        }]),
        buildCanonicalPayload(G4_ITEM_IDS.G4_10_ROWS, [{
          id: 'ecl-1',
          investProject: '债券A',
          adjImpairment: 5,
        }]),
        buildCanonicalPayload(G4_ITEM_IDS.G4_4_INTEREST, [{
          id: 'interest-1',
          projectName: '债券A',
          initial: { faceValueTotal: 100, couponRate: 0.03, effectiveRate: 0.04 },
          periods: [{ closingBalance: 999 }],
        }]),
      ])

    const allResponses = ref(new Map<string, ChecklistResponse>())
    const rollForward = useG4PriorYearRollForward({
      projectId: ref('project-1'),
      wpId: ref('current-wp'),
      allResponses,
      saveImmediate: vi.fn(),
      confirm: vi.fn().mockResolvedValue(undefined),
    })

    const plan = await rollForward.loadPreview()

    expect(getMock).toHaveBeenNthCalledWith(
      2,
      '/api/workpapers/prior-wp/checklist-responses',
    )
    expect(plan.changes.map((change) => change.itemId)).toEqual([
      G4_ITEM_IDS.G4_2_ROWS,
      G4_ITEM_IDS.G4_10_ROWS,
      G4_ITEM_IDS.G4_4_INTEREST,
    ])
    const detailRows = parseCanonicalArray(
      plan.changes.find((change) => change.itemId === G4_ITEM_IDS.G4_2_ROWS)?.payload,
    )
    expect(detailRows[0]).toMatchObject({ openingCost: 120, openingImpairment: 5 })
    const groups = parseCanonicalJson<any[]>(
      plan.changes.find((change) => change.itemId === G4_ITEM_IDS.G4_4_INTEREST)?.payload,
    )!
    expect(groups[0].initial.couponRate).toBe(0.03)
    expect(groups[0].periods).toEqual([])
  })

  it('默认保护已填期初，确认后以 canonical payload 持久化', async () => {
    getMock.mockResolvedValueOnce({
      wp_id: 'prior-wp',
      wp_code: 'G4',
      checklist_responses: [
        buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, [{
          id: 'prior-1',
          investProject: '债券A',
          closingCost: 120,
          closingImpairment: 5,
        }]),
      ],
    })
    const current = buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, [{
      id: 'current-1',
      investProject: '债券A',
      openingCost: 88,
      openingImpairment: 0,
    }])
    const allResponses = ref(new Map([[current.item_id, current]]))
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const confirm = vi.fn().mockResolvedValue(undefined)
    const rollForward = useG4PriorYearRollForward({
      projectId: ref('project-1'),
      wpId: ref('current-wp'),
      allResponses,
      saveImmediate,
      confirm,
    })

    const plan = await rollForward.loadPreview(false)
    const rows = parseCanonicalArray(plan.changes[0].payload)
    expect(rows[0].openingCost).toBe(88)
    expect(rows[0].openingImpairment).toBe(5)

    expect(await rollForward.applyPreview(plan)).toBe(true)
    expect(confirm).toHaveBeenCalledOnce()
    expect(saveImmediate).toHaveBeenCalledWith(
      G4_ITEM_IDS.G4_2_ROWS,
      expect.objectContaining({
        item_id: G4_ITEM_IDS.G4_2_ROWS,
        conclusion: expect.any(String),
        remark: expect.any(String),
      }),
    )
  })

  it('force=true 可覆盖已填期初', async () => {
    getMock.mockResolvedValueOnce({
      wp_id: 'prior-wp',
      checklist_responses: [
        buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, [{
          investProject: '债券A',
          closingCost: 120,
        }]),
      ],
    })
    const current = buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, [{
      investProject: '债券A',
      openingCost: 88,
    }])
    const rollForward = useG4PriorYearRollForward({
      projectId: ref('project-1'),
      wpId: ref('current-wp'),
      allResponses: ref(new Map([[current.item_id, current]])),
      saveImmediate: vi.fn(),
      confirm: vi.fn().mockResolvedValue(undefined),
    })

    const plan = await rollForward.loadPreview(true)
    expect(parseCanonicalArray(plan.changes[0].payload)[0].openingCost).toBe(120)
  })

  it('有 saveBatch 时一次写入全部结转项', async () => {
    getMock.mockResolvedValueOnce({
      wp_id: 'prior-wp',
      checklist_responses: [
        buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, [{
          investProject: '债券A',
          closingCost: 120,
          closingImpairment: 5,
        }]),
        buildCanonicalPayload(G4_ITEM_IDS.G4_10_ROWS, [{
          investProject: '债券A',
          adjImpairment: 5,
        }]),
      ],
    })
    const saveImmediate = vi.fn()
    const saveBatch = vi.fn().mockResolvedValue(undefined)
    const rollForward = useG4PriorYearRollForward({
      projectId: ref('project-1'),
      wpId: ref('current-wp'),
      allResponses: ref(new Map()),
      saveImmediate,
      saveBatch,
      confirm: vi.fn().mockResolvedValue(undefined),
    })

    const plan = await rollForward.loadPreview(false)
    expect(plan.changes.length).toBeGreaterThanOrEqual(2)
    expect(await rollForward.applyPreview(plan)).toBe(true)
    expect(saveBatch).toHaveBeenCalledOnce()
    expect(saveImmediate).not.toHaveBeenCalled()
    const batchArg = saveBatch.mock.calls[0][0] as ChecklistResponse[]
    expect(batchArg.map((item) => item.item_id)).toEqual(
      plan.changes.map((change) => change.itemId),
    )
  })

  it('优先按 crossSheetInvestmentId 匹配上年行', async () => {
    getMock.mockResolvedValueOnce({
      wp_id: 'prior-wp',
      checklist_responses: [
        buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, [{
          investProject: '旧名称',
          crossSheetInvestmentId: 'inv-stable-1',
          closingCost: 200,
          closingImpairment: 8,
        }]),
      ],
    })
    const current = buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, [{
      investProject: '新名称',
      crossSheetInvestmentId: 'inv-stable-1',
      openingCost: 0,
    }])
    const rollForward = useG4PriorYearRollForward({
      projectId: ref('project-1'),
      wpId: ref('current-wp'),
      allResponses: ref(new Map([[current.item_id, current]])),
      saveImmediate: vi.fn(),
      confirm: vi.fn().mockResolvedValue(undefined),
    })

    const plan = await rollForward.loadPreview(false)
    const rows = parseCanonicalArray(plan.changes[0].payload)
    expect(rows).toHaveLength(1)
    expect(rows[0].openingCost).toBe(200)
    expect(rows[0].openingImpairment).toBe(8)
    expect(rows[0].investProject).toBe('新名称')
  })
})
