/**
 * useJ2CrossSheet — J2 跨sheet联动 + B51精算假设联动
 *
 * 职责：
 * - 明细表 ↔ 审定表 数据一致性校验
 * - 精算假设变动 → EventBus publish actuarial:assumption-changed → B51
 * - 附注 ↔ 审定表 自动取数
 * - GtIndexChip 跨底稿跳转支持
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 * Requirements: 5.1-5.4, 6.2-6.4
 */
import { ref, type Ref } from 'vue'
import http from '@/utils/http'

export interface CrossSheetDiscrepancy {
  field: string
  sourceSheet: string
  targetSheet: string
  sourceValue: number
  targetValue: number
  diff: number
}

export interface ActuarialAssumptionChange {
  field: string               // 变动的假设字段名
  oldValue: number
  newValue: number
  impactDescription: string   // 影响描述
}

export interface J2CrossSheetOptions {
  wpId: string
  projectId: string
  year?: string | number
}

export function useJ2CrossSheet(options: J2CrossSheetOptions) {
  const discrepancies: Ref<CrossSheetDiscrepancy[]> = ref([])
  const isChecking = ref(false)

  // ── 明细vs审定 一致性校验 ─────────────────────────────────────────────────

  function checkConsistency(
    detailTotals: { beginBalance: number; endBalance: number; increase: number; decrease: number },
    adjudicationValues: { beginBalance: number; auditedEnd: number },
  ): CrossSheetDiscrepancy[] {
    const results: CrossSheetDiscrepancy[] = []

    if (Math.abs(detailTotals.beginBalance - adjudicationValues.beginBalance) > 0.01) {
      results.push({
        field: '期初余额',
        sourceSheet: 'J2-2明细表',
        targetSheet: 'J2-1审定表',
        sourceValue: detailTotals.beginBalance,
        targetValue: adjudicationValues.beginBalance,
        diff: detailTotals.beginBalance - adjudicationValues.beginBalance,
      })
    }

    const detailEnd = detailTotals.beginBalance + detailTotals.increase - detailTotals.decrease
    if (Math.abs(detailEnd - adjudicationValues.auditedEnd) > 0.01) {
      results.push({
        field: '期末余额',
        sourceSheet: 'J2-2明细表',
        targetSheet: 'J2-1审定表',
        sourceValue: detailEnd,
        targetValue: adjudicationValues.auditedEnd,
        diff: detailEnd - adjudicationValues.auditedEnd,
      })
    }

    discrepancies.value = results
    return results
  }

  // ── B51精算假设联动 EventBus ───────────────────────────────────────────────

  async function publishAssumptionChanged(changes: ActuarialAssumptionChange[]) {
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
      console.warn('[J2 CrossSheet] actuarial:assumption-changed publish failed:', e)
    }
  }

  // ── 附注自动取数（从审定表拉取） ──────────────────────────────────────────

  async function fetchAdjudicationData(): Promise<Record<string, unknown> | null> {
    try {
      const res = await http.get(`/api/workpapers/${options.wpId}/render-config`)
      const sheets = res.data?.data?.sheets || res.data?.sheets || []
      const adjSheet = sheets.find((s: { sheet_name?: string }) =>
        s.sheet_name?.includes('J2-1'),
      )
      return adjSheet?.html_data || null
    } catch (e) {
      console.warn('[J2 CrossSheet] fetchAdjudicationData failed:', e)
      return null
    }
  }

  // ── cross_wp_references 注册（J2→B51） ─────────────────────────────────────

  const crossReferences = [
    { source: 'J2-4', target: 'B51', reason: '精算假设→会计估计', direction: 'outbound' as const },
    { source: 'J2A', target: 'S12', reason: '精算师工作利用→ISA620', direction: 'outbound' as const },
  ]

  return {
    discrepancies,
    isChecking,
    checkConsistency,
    publishAssumptionChanged,
    fetchAdjudicationData,
    crossReferences,
  }
}
