/**
 * useK6InitialRecognition — K6-4 初始确认（CAS42五条件清单）
 *
 * Spec: .kiro/specs/k6-held-for-sale/
 * Task: 3.4
 * Requirements: 4.1-4.5
 *
 * 职责：
 * - CAS42五条件核对清单（每条件：满足/不满足/不适用）
 * - 分类判断结果：全满足→'classified'；否则→'not_classified'
 * - AI辅助生成分类判断结论
 * - 五条件明细说明+证据
 *
 * CAS42 五条件：
 *   ① 可立即出售（在当前状况下仅根据惯例条款即可立即出售）
 *   ② 已就出售作出决议
 *   ③ 已与购买方签订不可撤销转让协议
 *   ④ 出售预计一年内完成
 *   ⑤ 售价合理，不太可能变更/撤销
 *
 * Prefix: "K6-4-"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { classifyHeldForSale, type ClassificationResult } from './useK6ClassificationEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 条件状态：'met'满足 / 'not_met'不满足 / 'na'不适用 / ''未评估 */
export type ConditionStatus = 'met' | 'not_met' | 'na' | ''

export interface K6Condition {
  index: number
  label: string
  description: string
  status: ConditionStatus
  evidence: string       // 审计证据/说明
}

export interface UseK6InitialRecognitionParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const CAS42_CONDITIONS: Array<{ label: string; description: string }> = [
  { label: '条件①：可立即出售', description: '在当前状况下仅根据出售此类资产或处置组的惯例条款即可立即出售' },
  { label: '条件②：已作出决议', description: '企业已就出售计划作出决议（如董事会决议）' },
  { label: '条件③：已签订不可撤销转让协议', description: '已与受让方签订了不可撤销的转让协议' },
  { label: '条件④：出售预计一年内完成', description: '该项转让将在一年内完成' },
  { label: '条件⑤：售价合理不太可能变更', description: '转让价格合理，且不太可能发生重大变化或被撤回' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getVal(map: Map<string, any>, itemId: string): string {
  const item = map.get(itemId)
  if (!item) return ''
  return item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK6InitialRecognition(params: UseK6InitialRecognitionParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const conditions = ref<K6Condition[]>(
    CAS42_CONDITIONS.map((c, i) => ({
      index: i,
      label: c.label,
      description: c.description,
      status: '' as ConditionStatus,
      evidence: '',
    }))
  )

  const classificationConclusion = ref('')

  // ─── 从 allResponses 加载条件状态 ─────────────────────────────────────────

  function _loadConditions(): void {
    for (let i = 0; i < 5; i++) {
      const status = getVal(allResponses.value, `K6-4-cond-${i}-status`) as ConditionStatus
      const evidence = getVal(allResponses.value, `K6-4-cond-${i}-evidence`)
      conditions.value[i].status = status || ''
      conditions.value[i].evidence = evidence
    }
    classificationConclusion.value = getVal(allResponses.value, 'K6-4-conclusion')
  }

  // ─── 分类判断结果（Req 4.2） ──────────────────────────────────────────────

  const classificationResult: ComputedRef<ClassificationResult> = computed(() => {
    // 将条件状态转为布尔数组：'met'视为true，'na'视为true（不适用=不影响判断），其他为false
    const booleans = conditions.value.map(c => {
      if (c.status === 'met') return true
      if (c.status === 'na') return true
      return false
    })
    return classifyHeldForSale(booleans)
  })

  /** 是否所有条件都已评估（非空） */
  const isFullyEvaluated: ComputedRef<boolean> = computed(() => {
    return conditions.value.every(c => c.status !== '')
  })

  /** 不满足的条件列表（用于红色提示） */
  const unmetConditions: ComputedRef<K6Condition[]> = computed(() => {
    return conditions.value.filter(c => c.status === 'not_met')
  })

  // ─── 更新条件状态 ─────────────────────────────────────────────────────────

  function updateConditionStatus(index: number, status: ConditionStatus): void {
    if (index < 0 || index >= 5) return
    conditions.value[index].status = status
    saveResponse(`K6-4-cond-${index}-status`, { remark: status })
  }

  function updateConditionEvidence(index: number, evidence: string): void {
    if (index < 0 || index >= 5) return
    conditions.value[index].evidence = evidence
    saveResponse(`K6-4-cond-${index}-evidence`, { remark: evidence })
  }

  // ─── 保存结论 ─────────────────────────────────────────────────────────────

  async function saveConclusion(): Promise<void> {
    await saveResponse('K6-4-conclusion', { remark: classificationConclusion.value })
    await saveResponse('K6-4-result', { remark: classificationResult.value })
  }

  // ─── AI 辅助绑定点（由组件调用AI端点后设值） ──────────────────────────────

  function setAiConclusion(text: string): void {
    classificationConclusion.value = text
    saveResponse('K6-4-conclusion', { remark: text })
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadConditions(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    conditions,
    classificationResult,
    classificationConclusion,
    isFullyEvaluated,
    unmetConditions,
    updateConditionStatus,
    updateConditionEvidence,
    saveConclusion,
    setAiConclusion,
  }
}
