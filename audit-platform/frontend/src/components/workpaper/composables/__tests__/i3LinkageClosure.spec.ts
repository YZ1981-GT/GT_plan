/**
 * I3 联动闭环：I3-7 → I3-6 可收回；I3-3 减值草稿贷方科目
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import { useI3CrossSheet } from '../useI3CrossSheet'
import { useI3Impairment } from '../useI3Impairment'
import {
  buildI3ImpairmentDraftLines,
  useI3Adjustment,
} from '../useI3Adjustment'

vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@/services/apiPaths/accounting', () => ({
  adjustments: {
    list: (pid: string) => `/api/projects/${pid}/adjustments`,
    create: (pid: string) => `/api/projects/${pid}/adjustments`,
  },
}))

function makeMap(extra?: Record<string, unknown>) {
  const m = new Map<string, { item_id: string; conclusion: null; remark: string | null }>()
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      m.set(k, {
        item_id: k,
        conclusion: null,
        remark: typeof v === 'string' ? v : JSON.stringify(v),
      })
    }
  }
  return ref(m)
}

describe('I3-7 → I3-6 recoverable sync', () => {
  beforeEach(() => vi.clearAllMocks())

  it('recoverableDetailByCgu maps FV and VIU from I3-7-rows', () => {
    const allResponses = makeMap({
      'I3-7-rows': [
        {
          cguName: 'CGU-A',
          fairValueLessDisposal: 800,
          valueInUse: 1200,
          recoverableAmount: 1200,
        },
      ],
    })
    const { recoverableDetailByCgu, recoverableByCgu } = useI3CrossSheet(allResponses as any)
    expect(recoverableDetailByCgu.value['CGU-A']).toEqual({
      fairValueLessDisposal: 800,
      valueInUse: 1200,
      recoverableAmount: 1200,
    })
    expect(recoverableByCgu.value['CGU-A']).toBe(1200)
  })

  it('syncRecoverableFromI3_7 writes fairValueLessCost + valueInUse and resolves MAX', async () => {
    const allResponses = makeMap({
      'I3-6-rows': [
        {
          rowId: 'c1',
          cguName: 'CGU-A',
          goodwillB1: 500,
          assetGroupCarrying: 2000,
          minorityB2: 0,
          otherAssets: [],
          recoverableAmount: 0,
        },
      ],
      'I3-7-rows': [
        {
          cguName: 'CGU-A',
          fairValueLessDisposal: 900,
          valueInUse: 1500,
          recoverableAmount: 1500,
        },
      ],
    })
    const { recoverableByCgu, recoverableDetailByCgu } = useI3CrossSheet(allResponses as any)
    const saves: Array<[string, any]> = []
    const state = useI3Impairment(ref('wp1'), allResponses as any, {
      onSave: (id, v) => saves.push([id, v]),
      recoverableByCgu,
      recoverableDetailByCgu,
    })
    await nextTick()
    const { changed } = state.syncRecoverableFromI3_7()
    expect(changed).toBe(1)
    expect(state.cguRows.value[0].fairValueLessCost).toBe(900)
    expect(state.cguRows.value[0].valueInUse).toBe(1500)
    expect(state.cguRows.value[0].recoverableAmount).toBe(1500)
  })
})

describe('I3-3 impairment draft credit account', () => {
  it('buildI3ImpairmentDraftLines respects creditAccountCode', () => {
    const lines = buildI3ImpairmentDraftLines({
      cguName: 'CGU-A',
      goodwillImpairment: 100,
      creditAccountCode: '1711.01',
    })
    expect(lines[1].accountCode).toBe('1711.01')
    expect(lines[1].accountName).toContain('减值')
  })

  it('seedFromI36 uses configured credit account', () => {
    const allResponses = makeMap({
      'I3-6-rows': [
        { cguName: 'CGU-A', consolidatedGwImpairment: 50000, goodwillImpairment: 50000 },
      ],
    })
    const state = useI3Adjustment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave: () => {},
    })
    const n = state.seedFromI36({ creditAccountCode: '1711.01' })
    expect(n).toBe(2)
    expect(state.rows.value[1].accountCode).toBe('1711.01')
  })
})
