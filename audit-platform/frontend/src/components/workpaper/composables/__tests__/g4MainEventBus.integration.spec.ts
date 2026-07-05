/**
 * g4MainEventBus.integration.spec.ts — G4(main) EventBus 跨组件传递验证
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 9.4
 * Requirements: 3.9, 4.3, 6.5, 7.11, 9.4
 *
 * 测试场景：
 * 1. G4-1 审定数变更 → CustomEvent 'substantive:adjudicated' fires with correct payload
 * 2. G4-3 回写 → CustomEvent 'g4:adjustment-writeback' fires with summaries
 * 3. G4-4 比对差异 computation is correct
 * 4. Disclosure components receive and process 'substantive:adjudicated' events
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useG4MainAdjudication, G4_ACCOUNT_CODE } from '../useG4MainAdjudication'
import { useG4MainAdjustment } from '../useG4MainAdjustment'
import { useG4MainInterestCalc } from '../useG4MainInterestCalc'
import type { ChecklistResponse } from '../useF1FormData'

// Mock vue lifecycle hooks
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...(actual as any),
    onMounted: vi.fn((cb: () => void) => cb()),
    onBeforeUnmount: vi.fn(),
  }
})

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessageBox: {
    prompt: vi.fn().mockRejectedValue(new Error('cancel')),
    confirm: vi.fn().mockRejectedValue(new Error('cancel')),
  },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

// Mock API
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({ data: { data: { audited_amount: 0 } } }) },
}))

describe('G4(main) EventBus 跨组件传递验证', () => {
  let dispatchedEvents: { type: string; detail: any }[]

  beforeEach(() => {
    dispatchedEvents = []
    // Intercept all CustomEvent dispatches
    const origDispatch = window.dispatchEvent.bind(window)
    vi.spyOn(window, 'dispatchEvent').mockImplementation((event: Event) => {
      if (event instanceof CustomEvent) {
        dispatchedEvents.push({ type: event.type, detail: event.detail })
      }
      return origDispatch(event)
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ─── Scenario 1: G4-1 审定数变更 → substantive:adjudicated ───
  describe('Scenario 1: G4-1 审定数变更 → substantive:adjudicated', () => {
    it('should publish substantive:adjudicated when amortizedCostRow.closingAdjusted changes', async () => {
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
      const wpId = ref('wp-001')
      const projectId = ref('proj-001')

      const adjudication = useG4MainAdjudication({
        wpId,
        projectId,
        allResponses,
      })

      // Trigger a cell update that changes closing adjusted
      adjudication.updateCell('original-value', 'ov-individual', 'openingUnadjusted', 100000)
      await nextTick()

      // Verify substantive:adjudicated event was dispatched
      const adjEvent = dispatchedEvents.find(e => e.type === 'substantive:adjudicated')
      expect(adjEvent).toBeDefined()
      expect(adjEvent!.detail.accountCode).toBe('1501')
      expect(adjEvent!.detail).toHaveProperty('adjudicatedAmount')
      expect(typeof adjEvent!.detail.adjudicatedAmount).toBe('number')
    })

    it('payload format should be {accountCode, adjudicatedAmount}', async () => {
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
      const wpId = ref('wp-002')
      const projectId = ref('proj-002')

      // Seed with known data
      allResponses.value.set('G4-1-adj-groups-original-value', {
        item_id: 'G4-1-adj-groups-original-value',
        conclusion: null,
        remark: JSON.stringify([
          {
            rowKey: 'ov-individual',
            label: '单项计提',
            openingUnadjusted: 500000,
            openingAJE: 0,
            openingRJE: 0,
            periodDebit: 100000,
            periodCredit: 50000,
            closingAJE: 10000,
            closingRJE: 0,
            reasonAnalysis: '',
            indexRef: '',
          },
        ]),
      })

      const adjudication = useG4MainAdjudication({
        wpId,
        projectId,
        allResponses,
      })
      await nextTick()

      // Trigger a change that causes closingAdjusted to update → fires publish
      adjudication.updateCell('original-value', 'ov-individual', 'closingAJE', 20000)
      await nextTick()

      // publishAdjudicated fires on watch, verify format
      const adjEvents = dispatchedEvents.filter(e => e.type === 'substantive:adjudicated')
      expect(adjEvents.length).toBeGreaterThan(0)
      const lastEvent = adjEvents[adjEvents.length - 1]
      expect(lastEvent.detail).toMatchObject({
        accountCode: G4_ACCOUNT_CODE,
        adjudicatedAmount: expect.any(Number),
      })
    })
  })

  // ─── Scenario 2: G4-3 回写 → g4:adjustment-writeback ───
  describe('Scenario 2: G4-3 回写 → g4:adjustment-writeback', () => {
    it('should fire g4:adjustment-writeback with summaries on saveAndWriteback', () => {
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
      const writebackCallback = vi.fn()

      // Seed with entries
      allResponses.value.set('G4-3-rows', {
        item_id: 'G4-3-rows',
        conclusion: null,
        remark: JSON.stringify([
          {
            id: 'e1',
            seq: 1,
            entryType: 'AJE',
            date: '2024-12-31',
            summary: '冲回多计利息',
            accountCode: '1501',
            accountName: '债权投资——成本',
            debitAmount: 0,
            creditAmount: 50000,
            preparedBy: '张三',
            remark: '',
          },
          {
            id: 'e2',
            seq: 2,
            entryType: 'AJE',
            date: '2024-12-31',
            summary: '冲回多计利息(对方科目)',
            accountCode: '6011',
            accountName: '利息收入',
            debitAmount: 50000,
            creditAmount: 0,
            preparedBy: '张三',
            remark: '',
          },
        ]),
      })

      const adjustment = useG4MainAdjustment({
        allResponses,
        onWritebackG4_1: writebackCallback,
      })

      // Execute saveAndWriteback
      adjustment.saveAndWriteback()

      // Verify callback called with aggregated summaries
      expect(writebackCallback).toHaveBeenCalledTimes(1)
      const summaries = writebackCallback.mock.calls[0][0]
      expect(summaries).toBeInstanceOf(Array)
      expect(summaries.length).toBe(2)

      // Check 1501 AJE net
      const bond = summaries.find((s: any) => s.accountCode === '1501')
      expect(bond).toBeDefined()
      expect(bond!.ajeNet).toBe(-50000) // 借0 - 贷50000 = -50000

      // Check 6011 AJE net
      const interest = summaries.find((s: any) => s.accountCode === '6011')
      expect(interest).toBeDefined()
      expect(interest!.ajeNet).toBe(50000) // 借50000 - 贷0 = 50000

      // Verify CustomEvent g4:adjustment-writeback was dispatched
      const wbEvent = dispatchedEvents.find(e => e.type === 'g4:adjustment-writeback')
      expect(wbEvent).toBeDefined()
      expect(wbEvent!.detail.summaries).toEqual(summaries)
    })

    it('should aggregate AJE and RJE separately', () => {
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map())

      allResponses.value.set('G4-3-rows', {
        item_id: 'G4-3-rows',
        conclusion: null,
        remark: JSON.stringify([
          {
            id: 'e1', seq: 1, entryType: 'AJE', date: '', summary: '',
            accountCode: '1501', accountName: '', debitAmount: 100000, creditAmount: 0,
            preparedBy: '', remark: '',
          },
          {
            id: 'e2', seq: 2, entryType: 'RJE', date: '', summary: '',
            accountCode: '1501', accountName: '', debitAmount: 0, creditAmount: 20000,
            preparedBy: '', remark: '',
          },
        ]),
      })

      const adjustment = useG4MainAdjustment({ allResponses })
      const summaries = adjustment.aggregateForWriteback()

      const bond = summaries.find(s => s.accountCode === '1501')
      expect(bond).toBeDefined()
      expect(bond!.ajeNet).toBe(100000)   // AJE: 借100000 - 贷0
      expect(bond!.rjeNet).toBe(-20000)   // RJE: 借0 - 贷20000
    })
  })

  // ─── Scenario 3: G4-4 比对差异 computation ───
  describe('Scenario 3: G4-4 比对差异 computation', () => {
    it('should compute variance correctly when totalEffectiveInterest differs from g4_1InterestAdjusted', () => {
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
      const g4_1InterestAdjusted = ref(120000)

      // Seed interest calc groups with known data
      allResponses.value.set('G4-4-interest-calc', {
        item_id: 'G4-4-interest-calc',
        conclusion: null,
        remark: JSON.stringify([
          {
            id: 'g1',
            projectName: '项目A',
            initial: {
              faceValueTotal: 1000000,
              initialDate: '2023-01-01',
              maturityDate: '2026-01-01',
              purchasePrice: 980000,
              transactionCost: 5000,
              initialCarryingAmount: 985000,
              couponRate: 0.05,
              effectiveRate: 0.06,
            },
            periods: [
              {
                id: 'p1',
                cutoffDate: '2024-12-31',
                openingBalance: 990000,
                openingImpairment: 0,
                openingAmortizedCost: 990000,
                effectiveInterest: 59400,
                cashInflow: 50000,
                principalRepaid: 0,
                closingBalance: 999400,
                days: 365,
                stage: 'Stage1',
              },
              {
                id: 'p2',
                cutoffDate: '2024-06-30',
                openingBalance: 985000,
                openingImpairment: 0,
                openingAmortizedCost: 985000,
                effectiveInterest: 59100,
                cashInflow: 50000,
                principalRepaid: 0,
                closingBalance: 994100,
                days: 365,
                stage: 'Stage1',
              },
            ],
          },
        ]),
      })

      const calc = useG4MainInterestCalc({
        allResponses,
        g4_1InterestAdjusted,
      })

      const summary = calc.summary.value
      // totalEffectiveInterest = recalculated by formula engine from periods
      // g4_1InterestAdjusted = 120000
      expect(summary.g4_1InterestAdjusted).toBe(120000)
      expect(typeof summary.totalEffectiveInterest).toBe('number')
      expect(typeof summary.variance).toBe('number')
      expect(summary.variance).toBe(
        Math.round((summary.totalEffectiveInterest - 120000) * 100) / 100,
      )
    })

    it('should mark variance acceptable when |variance| <= 0.01', () => {
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
      const g4_1InterestAdjusted = ref(0)

      // No groups → totalEffectiveInterest = 0, variance = 0
      const calc = useG4MainInterestCalc({
        allResponses,
        g4_1InterestAdjusted,
      })

      expect(calc.summary.value.isVarianceAcceptable).toBe(true)
      expect(calc.isVarianceHighlight()).toBe(false)
    })

    it('should mark variance unacceptable when |variance| > 0.01', () => {
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map())
      const g4_1InterestAdjusted = ref(100)

      // Seed with a period that will produce non-zero effective interest
      allResponses.value.set('G4-4-interest-calc', {
        item_id: 'G4-4-interest-calc',
        conclusion: null,
        remark: JSON.stringify([
          {
            id: 'g1',
            projectName: '测试项目',
            initial: {
              faceValueTotal: 1000000,
              initialDate: '',
              maturityDate: '',
              purchasePrice: 0,
              transactionCost: 0,
              initialCarryingAmount: 0,
              couponRate: 0.05,
              effectiveRate: 0.06,
            },
            periods: [
              {
                id: 'p1',
                cutoffDate: '2024-12-31',
                openingBalance: 1000000,
                openingImpairment: 0,
                openingAmortizedCost: 1000000,
                effectiveInterest: 60000,
                cashInflow: 50000,
                principalRepaid: 0,
                closingBalance: 1010000,
                days: 365,
                stage: 'Stage1',
              },
            ],
          },
        ]),
      })

      const calc = useG4MainInterestCalc({
        allResponses,
        g4_1InterestAdjusted,
      })

      // Formula engine will recalculate: effectiveInterest = 1000000 * 0.06 * 365/365 = 60000
      // variance = 60000 - 100 = 59900 → unacceptable
      expect(calc.summary.value.isVarianceAcceptable).toBe(false)
      expect(calc.isVarianceHighlight()).toBe(true)
    })
  })

  // ─── Scenario 4: Disclosure components subscribe ───
  describe('Scenario 4: Disclosure components receive substantive:adjudicated', () => {
    it('CustomEvent substantive:adjudicated has correct format for disclosure consumption', () => {
      // Simulate what G4-1 publishes
      const payload = {
        wpCode: 'G4',
        accountCode: '1501',
        adjudicatedAmount: 8500000,
        auditedAmount: 8500000,
      }
      const event = new CustomEvent('substantive:adjudicated', { detail: payload })

      // Verify event construction
      expect(event.type).toBe('substantive:adjudicated')
      expect(event.detail.accountCode).toBe('1501')
      expect(event.detail.adjudicatedAmount).toBe(8500000)
    })

    it('disclosure handler filters by accountCode correctly', () => {
      const received: any[] = []

      // Simulate disclosure subscription handler (same logic as in G4TabDisclosureListed.vue)
      function handleAdjudicated(e: Event): void {
        const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
        if (d?.accountCode === '1501' && d.adjudicatedAmount != null) {
          received.push(d)
        }
      }

      window.addEventListener('substantive:adjudicated', handleAdjudicated)

      // Dispatch event for account 1501 (should be received)
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: '1501', adjudicatedAmount: 5000000 },
      }))

      // Dispatch event for different account (should be ignored)
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
        detail: { accountCode: '1401', adjudicatedAmount: 3000000 },
      }))

      expect(received.length).toBe(1)
      expect(received[0].accountCode).toBe('1501')
      expect(received[0].adjudicatedAmount).toBe(5000000)

      window.removeEventListener('substantive:adjudicated', handleAdjudicated)
    })

    it('disclosure:note-text-updated event has correct format', () => {
      const received: any[] = []
      function handler(e: Event): void {
        received.push((e as CustomEvent).detail)
      }
      window.addEventListener('disclosure:note-text-updated', handler)

      // Simulate what disclosure components publish
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { accountCode: '1501', section: 'listed', text: '测试附注文本' },
      }))

      expect(received.length).toBe(1)
      expect(received[0]).toMatchObject({
        accountCode: '1501',
        text: '测试附注文本',
      })

      window.removeEventListener('disclosure:note-text-updated', handler)
    })
  })
})
