/**
 * useJ2Integration — J2 集成联动统一入口
 *
 * 整合所有 EventBus + TB回写 + GtIndexChip + 附注联动 + 双模式
 *
 * 6大集成：
 * 1. TB回写: 2221期末余额
 * 2. EventBus: substantive:adjudicated (审定完成)
 * 3. EventBus: actuarial:assumption-changed → B51
 * 4. cross_wp_references: J2→B51, J2A→S12
 * 5. 附注EventBus: subscribe substantive:adjudicated 刷新 + publish disclosure:note-text-updated
 * 6. 双模式OO: HTML ↔ OnlyOffice
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 * Requirements: 6.1-6.5
 */
import { ref } from 'vue'
import http from '@/utils/http'
import type { ActuarialAssumptionChange } from './useJ2CrossSheet'

export interface J2IntegrationOptions {
  wpId: string
  projectId: string
  year?: string | number
}

export function useJ2Integration(options: J2IntegrationOptions) {
  const isWritingBack = ref(false)

  // ── 6.1 TB回写 2221期末余额 + substantive:adjudicated ─────────────────

  async function onAdjudicationComplete(auditedEndBalance: number) {
    isWritingBack.value = true
    try {
      // TB回写
      await http.post(`/api/projects/${options.projectId}/trial-balance/writeback`, {
        account_code: '2221',
        audited_amount: auditedEndBalance,
        year: options.year,
        source_wp_id: options.wpId,
      })

      // EventBus publish
      await http.post(`/api/projects/${options.projectId}/events/publish`, {
        event_type: 'substantive:adjudicated',
        payload: {
          accountCode: '2221',
          accountName: '长期应付职工薪酬',
          auditedAmount: auditedEndBalance,
          wpId: options.wpId,
          direction: 'credit',
        },
      })
    } catch (e) {
      console.warn('[J2 Integration] adjudication complete failed:', e)
    } finally {
      isWritingBack.value = false
    }
  }

  // ── 6.2 actuarial:assumption-changed → B51 ────────────────────────────

  async function onAssumptionChanged(changes: ActuarialAssumptionChange[]) {
    try {
      await http.post(`/api/projects/${options.projectId}/events/publish`, {
        event_type: 'actuarial:assumption-changed',
        payload: {
          wpId: options.wpId,
          changes,
          timestamp: new Date().toISOString(),
          source: 'J2-4计提检查',
        },
      })
    } catch (e) {
      console.warn('[J2 Integration] assumption-changed publish failed:', e)
    }
  }

  // ── 6.3 cross_wp_references 定义 ──────────────────────────────────────

  const crossReferences = [
    { source: 'J2-4', target: 'B51', reason: '精算假设→会计估计', type: 'outbound' },
    { source: 'J2A', target: 'S12', reason: '精算师工作利用→ISA620', type: 'outbound' },
    { source: 'J2A', target: 'S12A', reason: '精算师独立性评价', type: 'outbound' },
  ]

  // ── 6.4 GtIndexChip targets ────────────────────────────────────────────

  const indexChipTargets = [
    { label: 'B51会计估计', value: 'B51', description: '精算假设作为会计估计' },
    { label: 'S12精算师利用', value: 'S12', description: 'ISA620精算师工作利用评价' },
  ]

  // ── 6.5 附注EventBus ──────────────────────────────────────────────────

  async function publishDisclosureUpdated(noteContent: string) {
    try {
      await http.post(`/api/projects/${options.projectId}/events/publish`, {
        event_type: 'disclosure:note-text-updated',
        payload: {
          accountCode: '2221',
          accountName: '长期应付职工薪酬-设定受益计划',
          noteContent,
          wpId: options.wpId,
        },
      })
    } catch (e) {
      console.warn('[J2 Integration] disclosure update failed:', e)
    }
  }

  return {
    isWritingBack,
    onAdjudicationComplete,
    onAssumptionChanged,
    crossReferences,
    indexChipTargets,
    publishDisclosureUpdated,
  }
}
