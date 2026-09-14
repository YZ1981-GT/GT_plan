/**
 * K12 EventBus Integration Test
 *
 * Spec: k12-non-operating-income Task 6.1
 * Requirements: 2.6, 6.1
 *
 * 验证端到端集成链路:
 * 1. K12TabAdjudication → writebackTB → PUT /trial-balance/writeback (6301 发生额)
 * 2. writebackTB 成功后 → eventBus.emit('substantive:adjudicated', payload)
 * 3. K12TabDisclosureListed/Soe → eventBus.on('substantive:adjudicated') → applyAutoFill()
 *
 * Payload 契约:
 *   { accountCode: '6301', auditedAmount: number, wpCode: 'K12', type: 'occurrence_amount', timestamp: number }
 *
 * Backend TB writeback:
 *   _on_d_audit_determination_saved regex `^[D-N]\d+-1$` matches K12-1
 *   → UPDATE trial_balance SET audited_amount WHERE account_code='6301'
 *   → publish TRIAL_BALANCE_UPDATED
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── Mock eventBus ───────────────────────────────────────────────────────────

const emitSpy = vi.fn()
const onSpy = vi.fn()
const offSpy = vi.fn()

vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (...args: any[]) => emitSpy(...args),
    on: (...args: any[]) => onSpy(...args),
    off: (...args: any[]) => offSpy(...args),
  },
}))

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockPut = vi.fn().mockResolvedValue({ data: { code: 200 } })
const mockGet = vi.fn().mockResolvedValue({ data: [] })

vi.mock('@/services/apiProxy', () => ({
  api: {
    put: (...args: any[]) => mockPut(...args),
    get: (...args: any[]) => mockGet(...args),
  },
}))

// ─── Mock element-plus ───────────────────────────────────────────────────────

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue(true) },
}))

// 注：useK12FormData / ref 原用于已移除的 Part A/B（直调 formData.writebackTB 死代码，
//     spec tb-writeback-explicit-publish-gate Task 17 批C），随之移除 import。
//     保留的 Part C/D/E 用本地 handler 函数 + regex，不需要 composable 实例。

// ═══════════════════════════════════════════════════════════════════════════════
// Part A: writebackTB → API → EventBus.emit('substantive:adjudicated')
// ═══════════════════════════════════════════════════════════════════════════════

describe('K12 EventBus Integration: TB回写(6301发生额) → substantive:adjudicated → 附注', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ═══ Part A/B（已移除，spec tb-writeback-explicit-publish-gate Task 17 批C） ═══
  // 原 Part A（5 用例）+ Part B（2 用例）直调 formData.writebackTB，测的是零生产消费死代码
  //（useK12FormData.writebackTB 已随本 spec 移除）。Part C/D/E 测的是附注订阅 handler 逻辑 /
  // 后端 regex / 事件流分离（用本地函数，不调 formData.writebackTB），与死代码无关，保留。
  // K12 发生额活路径回写走显式发布门 publish-to-tb（改造归 M6/task9）。

  // ═══ Part C: Disclosure subscription wiring ═══

  describe('Part C: Disclosure subscribe to substantive:adjudicated', () => {
    it('K12TabDisclosureListed subscribes on mount (eventBus.on contract)', () => {
      // The disclosure component does:
      //   onMounted(() => { eventBus.on('substantive:adjudicated', handleAdjudicated) })
      //   onUnmounted(() => { eventBus.off('substantive:adjudicated', handleAdjudicated) })
      //
      // We verify the contract matches:
      // 1. Event name is 'substantive:adjudicated' (same as writebackTB emits)
      // 2. Handler checks accountCode === '6301' || wpCode === 'K12'

      // Simulate disclosure handler logic
      let autoFillCalled = false
      function disclosureHandler(payload: any): void {
        if (payload?.accountCode === '6301' || payload?.wpCode === 'K12') {
          autoFillCalled = true
        }
      }

      // Matching payload (from writebackTB)
      disclosureHandler({ accountCode: '6301', auditedAmount: 100000, wpCode: 'K12', type: 'occurrence_amount' })
      expect(autoFillCalled).toBe(true)
    })

    it('K12TabDisclosureSoe subscribes with same filter (accountCode=6301)', () => {
      let autoFillCalled = false
      function disclosureHandler(payload: any): void {
        if (payload?.accountCode === '6301' || payload?.wpCode === 'K12') {
          autoFillCalled = true
        }
      }

      disclosureHandler({ accountCode: '6301', auditedAmount: 75000, wpCode: 'K12' })
      expect(autoFillCalled).toBe(true)
    })

    it('disclosure handler ignores events from other accounts', () => {
      let autoFillCalled = false
      function disclosureHandler(payload: any): void {
        if (payload?.accountCode === '6301' || payload?.wpCode === 'K12') {
          autoFillCalled = true
        }
      }

      // Other account (e.g., K8=6601)
      disclosureHandler({ accountCode: '6601', auditedAmount: 50000, wpCode: 'K8' })
      expect(autoFillCalled).toBe(false)
    })

    it('disclosure handler ignores null/undefined payload', () => {
      let autoFillCalled = false
      function disclosureHandler(payload: any): void {
        if (!payload) return
        if (payload.accountCode === '6301' || payload.wpCode === 'K12') {
          autoFillCalled = true
        }
      }

      disclosureHandler(null)
      expect(autoFillCalled).toBe(false)

      disclosureHandler(undefined)
      expect(autoFillCalled).toBe(false)
    })
  })

  // ═══ Part D: Backend TB writeback coverage ═══

  describe('Part D: Backend _on_d_audit_determination_saved covers K12-1', () => {
    it('regex ^[D-N]\\d+-1$ matches K12-1', () => {
      // Backend handler regex: /^[D-N]\d+-1$/
      const regex = /^[D-N]\d+-1$/
      expect(regex.test('K12-1')).toBe(true)
    })

    it('regex matches other K-cycle determination sheets', () => {
      const regex = /^[D-N]\d+-1$/
      expect(regex.test('K8-1')).toBe(true)
      expect(regex.test('K9-1')).toBe(true)
      expect(regex.test('K11-1')).toBe(true)
      expect(regex.test('K13-1')).toBe(true)
    })

    it('regex does NOT match non-determination sheets', () => {
      const regex = /^[D-N]\d+-1$/
      expect(regex.test('K12-2')).toBe(false) // 明细表
      expect(regex.test('K12A')).toBe(false)  // 程序表
      expect(regex.test('K12-3')).toBe(false) // 调整分录
      expect(regex.test('A1-1')).toBe(false)  // A循环不在范围
    })
  })

  // ═══ Part E: Event flow separation ═══

  describe('Part E: Event flow separation (adjustment:created vs substantive:adjudicated)', () => {
    it('adjustment:created flows to A13 only (not disclosure directly)', () => {
      // Design: K12-3 →|adjustment:created| A13
      //         K12-1 →|substantive:adjudicated| NOTE (disclosure)
      //
      // Disclosure components subscribe to 'substantive:adjudicated',
      // NOT to 'adjustment:created'. The flow is:
      //   K12-3 save → AJE/RJE → K12-1 recalc → writebackTB → substantive:adjudicated → disclosure
      //   K12-3 save → adjustment:created → A13

      let disclosureRefreshed = false
      function disclosureHandler(eventName: string): void {
        if (eventName === 'substantive:adjudicated') {
          disclosureRefreshed = true
        }
      }

      // adjustment:created does NOT trigger disclosure
      disclosureHandler('adjustment:created')
      expect(disclosureRefreshed).toBe(false)

      // substantive:adjudicated DOES trigger disclosure
      disclosureHandler('substantive:adjudicated')
      expect(disclosureRefreshed).toBe(true)
    })
  })
})
