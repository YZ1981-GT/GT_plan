/**
 * useH8LeaseTerm — H8-5 lease term unit tests
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  calcLeaseTermMonths,
  calcReassessmentConclusion,
  resolveEffectiveLeaseTermMonths,
  needsTermModification,
  isShortTermLeaseCandidate,
  useH8LeaseTerm,
  type H8LeaseTermRecord,
} from '../useH8LeaseTerm'

const Y = '\u662f'
const N = '\u5426'

function base(partial: Partial<H8LeaseTermRecord> = {}): H8LeaseTermRecord {
  return {
    recordId: 'r1',
    contractNo: 'ZL-001',
    signingToCommencementInfo: '',
    commencementInfo: '',
    commencementDate: '',
    nonCancellableInfo: '',
    nonCancellableMonths: 36,
    lessorOnlyTerminate: '',
    lesseeOnlyTerminate: '',
    lesseeReasonablyCertainNotTerminate: '',
    bothCanTerminateNoPenalty: '',
    terminationOptionMonths: 0,
    renewalInfo: '',
    renewalMonths: 0,
    renewalReasonablyCertain: '',
    purchaseOptionInfo: '',
    purchaseReasonablyCertain: '',
    determinedLeaseTermMonths: 0,
    termEndDate: '',
    indexRef: '',
    majorImprovement: '',
    majorCustomization: '',
    relatedBusinessDecision: '',
    exercisedOptionNotIncluded: '',
    didNotExerciseIncludedOption: '',
    eventForcesExercise: '',
    eventPreventsExercise: '',
    redeterminedInfo: '',
    redeterminedLeaseTermMonths: 0,
    explanation: '',
    conclusion: '',
    ...partial,
  }
}

describe('calcLeaseTermMonths', () => {
  it('non-cancellable only', () => {
    expect(calcLeaseTermMonths(base())).toBe(36)
  })

  it('adds renewal when reasonably certain', () => {
    expect(calcLeaseTermMonths(base({
      renewalMonths: 24,
      renewalReasonablyCertain: Y as any,
    }))).toBe(60)
  })

  it('skips renewal when not certain', () => {
    expect(calcLeaseTermMonths(base({
      renewalMonths: 24,
      renewalReasonablyCertain: N as any,
    }))).toBe(36)
  })

  it('adds termination option when reasonably certain NOT to terminate', () => {
    expect(calcLeaseTermMonths(base({
      lesseeReasonablyCertainNotTerminate: Y as any,
      terminationOptionMonths: 12,
    }))).toBe(48)
  })

  it('both can terminate: keep non-cancellable only', () => {
    expect(calcLeaseTermMonths(base({
      bothCanTerminateNoPenalty: Y as any,
      renewalMonths: 24,
      renewalReasonablyCertain: Y as any,
      terminationOptionMonths: 12,
      lesseeReasonablyCertainNotTerminate: Y as any,
    }))).toBe(36)
  })
})

describe('calcReassessmentConclusion', () => {
  it('any yes -> reassess', () => {
    expect(calcReassessmentConclusion(Y as any, N as any, N as any)).toContain('\u5e94\u5f53\u91cd\u65b0\u8bc4\u4f30')
    expect(calcReassessmentConclusion(N as any, Y as any, N as any)).toContain('\u5e94\u5f53\u91cd\u65b0\u8bc4\u4f30')
    expect(calcReassessmentConclusion(N as any, N as any, Y as any)).toContain('\u5e94\u5f53\u91cd\u65b0\u8bc4\u4f30')
  })

  it('all no -> no reassess', () => {
    expect(calcReassessmentConclusion(N as any, N as any, N as any)).toBe('\u65e0\u9700\u91cd\u65b0\u8bc4\u4f30')
  })

  it('incomplete -> pending', () => {
    expect(calcReassessmentConclusion('' as any, N as any, N as any)).toContain('\u5f85\u586b\u5199')
  })
})

describe('resolveEffectiveLeaseTermMonths / needsTermModification', () => {
  it('priority redetermined > determined > formula', () => {
    expect(resolveEffectiveLeaseTermMonths(base({
      nonCancellableMonths: 36,
      determinedLeaseTermMonths: 48,
      redeterminedLeaseTermMonths: 60,
    }))).toBe(60)
    expect(resolveEffectiveLeaseTermMonths(base({
      determinedLeaseTermMonths: 48,
      nonCancellableMonths: 36,
    }))).toBe(48)
    expect(resolveEffectiveLeaseTermMonths(base({ nonCancellableMonths: 36 }))).toBe(36)
  })

  it('any modify trigger', () => {
    expect(needsTermModification(base({ exercisedOptionNotIncluded: Y as any }))).toBe(true)
    expect(needsTermModification(base({ didNotExerciseIncludedOption: Y as any }))).toBe(true)
    expect(needsTermModification(base({ eventForcesExercise: Y as any }))).toBe(true)
    expect(needsTermModification(base({ eventPreventsExercise: Y as any }))).toBe(true)
    expect(needsTermModification(base())).toBe(false)
  })
})

describe('useH8LeaseTerm composable', () => {
  it('migrates legacy termination semantics', () => {
    const saved = [{
      recordId: 'legacy-1',
      contractNo: 'OLD-1',
      nonCancellableTerm: 24,
      renewalOptionTerm: 12,
      isRenewalReasonablyCertain: Y,
      terminationOptionTerm: 6,
      isTerminationReasonablyCertain: N,
      finalLeaseTerm: 36,
      explanation: 'legacy',
      conclusion: Y,
    }]
    const map = new Map([['H8-5-records', { remark: JSON.stringify(saved) }]])
    const { records } = useH8LeaseTerm({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(map),
    })
    expect(records.value[0].nonCancellableMonths).toBe(24)
    expect(records.value[0].renewalReasonablyCertain).toBe(Y)
    expect(records.value[0].lesseeReasonablyCertainNotTerminate).toBe(Y)
  })

  it('applySuggestedTerm persists', () => {
    const saved: any[] = []
    const api = useH8LeaseTerm({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(new Map()),
      onSave: (_id, value) => { saved.splice(0, saved.length, ...(value as any[])) },
    })
    api.addRecord('ZL-2024-001')
    const id = api.records.value[0].recordId
    api.updateField(id, 'nonCancellableMonths', 36)
    api.updateField(id, 'renewalMonths', 12)
    api.updateField(id, 'renewalReasonablyCertain', Y)
    api.applySuggestedTerm(id)
    expect(api.records.value[0].determinedLeaseTermMonths).toBe(48)
  })

  it('bothCanTerminate clears not-terminate flag', () => {
    const api = useH8LeaseTerm({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(new Map()),
      onSave: () => {},
    })
    api.addRecord('ZL-X')
    const id = api.records.value[0].recordId
    api.updateField(id, 'lesseeReasonablyCertainNotTerminate', Y)
    api.updateField(id, 'bothCanTerminateNoPenalty', Y)
    expect(api.records.value[0].lesseeReasonablyCertainNotTerminate).toBe('')
  })

  it('pushLeaseTermToH86 keeps other params', () => {
    const saved = new Map<string, any>()
    const map = ref(new Map<string, any>([
      ['H8-6-params', {
        remark: JSON.stringify({
          leaseLiabilityInitial: 100000,
          directCost: 500,
          incentive: 200,
          discountRate: 4.5,
          leaseTermMonths: 12,
          rentalPerPeriod: 1000,
          paymentTiming: '\u671f\u672b',
        }),
      }],
    ]))
    const api = useH8LeaseTerm({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: map,
      onSave: (itemId, value) => { saved.set(itemId, value) },
    })
    api.addRecord('ZL-PUSH')
    const id = api.records.value[0].recordId
    api.updateField(id, 'nonCancellableMonths', 36)
    api.updateField(id, 'renewalMonths', 12)
    api.updateField(id, 'renewalReasonablyCertain', Y)
    api.applySuggestedTerm(id)
    const r = api.pushLeaseTermToH86(id)
    expect(r.ok).toBe(true)
    expect(r.months).toBe(48)
    expect(saved.get('H8-6-params').leaseLiabilityInitial).toBe(100000)
  })

  it('pushLeaseTermToH86 fails when zero', () => {
    const api = useH8LeaseTerm({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(new Map()),
      onSave: () => {},
    })
    api.addRecord('ZL-0')
    expect(api.pushLeaseTermToH86(api.records.value[0].recordId).ok).toBe(false)
  })

  it('pushLeaseTermToH88 updates matching rows', () => {
    const saved = new Map<string, any>()
    const map = ref(new Map<string, any>([
      ['H8-8-dep-rows', {
        remark: JSON.stringify([
          { rowId: 'd1', contractNo: 'ZL-88', leaseTermMonths: 24, startDate: '', assetName: 'A' },
          { rowId: 'd2', contractNo: 'OTHER', leaseTermMonths: 12, assetName: 'B' },
        ]),
      }],
    ]))
    const api = useH8LeaseTerm({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: map,
      onSave: (id, v) => saved.set(id, v),
    })
    api.addRecord('ZL-88')
    const id = api.records.value[0].recordId
    api.updateField(id, 'determinedLeaseTermMonths', 60)
    api.updateField(id, 'commencementDate', '2024-01-01')
    const r = api.pushLeaseTermToH88(id)
    expect(r.updated).toBe(1)
    expect(saved.get('H8-8-dep-rows')[0].leaseTermMonths).toBe(60)
    expect(saved.get('H8-8-dep-rows')[0].startDate).toBe('2024-01-01')
  })
})

describe('H8-5 to H8-13 short-term', () => {
  it('excludes purchase option from short-term', () => {
    expect(isShortTermLeaseCandidate(base({
      determinedLeaseTermMonths: 10,
      purchaseReasonablyCertain: Y as any,
    }))).toBe(false)
    expect(isShortTermLeaseCandidate(base({
      determinedLeaseTermMonths: 10,
      purchaseReasonablyCertain: N as any,
    }))).toBe(true)
    expect(isShortTermLeaseCandidate(base({
      determinedLeaseTermMonths: 36,
    }))).toBe(false)
  })

  it('pushShortTermToH813 skips purchase option', () => {
    const saved = new Map<string, any>()
    const api = useH8LeaseTerm({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: ref(new Map()),
      onSave: (id, v) => saved.set(id, v),
    })
    api.addRecord('ST-1')
    api.updateField(api.records.value[0].recordId, 'determinedLeaseTermMonths', 6)
    api.addRecord('BUY-1')
    api.updateField(api.records.value[1].recordId, 'determinedLeaseTermMonths', 6)
    api.updateField(api.records.value[1].recordId, 'purchaseReasonablyCertain', Y)
    expect(api.shortTermCandidateCount.value).toBe(1)
    const r = api.pushShortTermToH813()
    expect(r.ok).toBe(true)
    expect(r.added).toBe(1)
    expect(r.skippedPurchaseOption).toBe(1)
    expect(saved.get('H8-13-rows')[0].contractNo).toBe('ST-1')
  })
})
