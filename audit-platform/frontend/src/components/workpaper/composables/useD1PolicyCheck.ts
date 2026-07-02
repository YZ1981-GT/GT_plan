/**
 * useD1PolicyCheck — D1-14 应收票据坏账准备会计政策检查 composable
 *
 * Spec: .kiro/specs/d1-ecl-provision/
 * Task: 3.1
 *
 * 段落式左右分栏布局的5个section逻辑：
 * - Section 2: 政策概述（左侧描述 + 右侧核查意见）
 * - Section 3: ECL模型描述（组合/单项/迁徙率 + 右侧核查意见）
 * - Section 4: 政策变更（是/否 + 条件展开）
 * - Section 5: 审计结论（合理性评价 + 结论文本）
 *
 * Requirements: 1.1-5.5, 10.3, 12.1, 12.3, 12.4, 14.3, 14.4
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type PolicyConclusion = '合理' | '基本合理但需关注' | '不合理' | ''
export type PolicyChangeFlag = '是' | '否' | ''

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface UseD1PolicyCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  debouncedSave: SaveFn
  isReadonly: Ref<boolean>
}

// ─── Item ID Constants ───────────────────────────────────────────────────────

const ITEM_IDS = {
  // Section 2: 政策概述
  overviewLeft: 'D1-policy-overview-left',
  overviewRight: 'D1-policy-overview-right',
  // Section 3: ECL模型
  eclPortfolio: 'D1-policy-ecl-portfolio',
  eclIndividual: 'D1-policy-ecl-individual',
  eclMigration: 'D1-policy-ecl-migration',
  eclRight: 'D1-policy-ecl-right',
  // Section 4: 政策变更
  changeFlag: 'D1-policy-change-flag',
  changeContent: 'D1-policy-change-content',
  changeReason: 'D1-policy-change-reason',
  // Section 5: 审计结论
  conclusion: 'D1-policy-conclusion',
} as const

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1PolicyCheck(options: UseD1PolicyCheckOptions) {
  const { allResponses, saveImmediate, debouncedSave, isReadonly } = options

  const isLoading = ref(false)

  // ─── Section 2: 政策概述 ─────────────────────────────────────────────────

  const policyOverviewLeft = ref('')
  const policyOverviewRight = ref('')

  function savePolicyOverview(): void {
    if (isReadonly.value) return
    debouncedSave([
      { item_id: ITEM_IDS.overviewLeft, remark: policyOverviewLeft.value, conclusion: null },
      { item_id: ITEM_IDS.overviewRight, remark: policyOverviewRight.value, conclusion: null },
    ])
  }

  // ─── Section 3: ECL模型描述 ──────────────────────────────────────────────

  const eclModelPortfolio = ref('')
  const eclModelIndividual = ref('')
  const eclModelMigration = ref('')
  const eclModelRight = ref('')

  function saveEclModel(): void {
    if (isReadonly.value) return
    debouncedSave([
      { item_id: ITEM_IDS.eclPortfolio, remark: eclModelPortfolio.value, conclusion: null },
      { item_id: ITEM_IDS.eclIndividual, remark: eclModelIndividual.value, conclusion: null },
      { item_id: ITEM_IDS.eclMigration, remark: eclModelMigration.value, conclusion: null },
      { item_id: ITEM_IDS.eclRight, remark: eclModelRight.value, conclusion: null },
    ])
  }

  // ─── Section 4: 政策变更 ─────────────────────────────────────────────────

  const policyChangeFlag = ref<PolicyChangeFlag>('')
  const policyChangeContent = ref('')
  const policyChangeReason = ref('')

  const showPolicyChangeDetails: ComputedRef<boolean> = computed(
    () => policyChangeFlag.value === '是'
  )

  function setPolicyChangeFlag(flag: PolicyChangeFlag): void {
    if (isReadonly.value) return
    policyChangeFlag.value = flag
    saveImmediate([
      { item_id: ITEM_IDS.changeFlag, conclusion: flag, remark: null },
    ])
  }

  function savePolicyChange(): void {
    if (isReadonly.value) return
    debouncedSave([
      { item_id: ITEM_IDS.changeContent, remark: policyChangeContent.value, conclusion: null },
      { item_id: ITEM_IDS.changeReason, remark: policyChangeReason.value, conclusion: null },
    ])
  }

  // ─── Section 5: 审计结论 ─────────────────────────────────────────────────

  const policyConclusion = ref<PolicyConclusion>('')
  const conclusionText = ref('')

  function setPolicyConclusion(c: PolicyConclusion): void {
    if (isReadonly.value) return
    policyConclusion.value = c
    // 跨Spec写出：conclusion字段=合理性评价
    saveImmediate([
      { item_id: ITEM_IDS.conclusion, conclusion: c, remark: conclusionText.value || null },
    ])
  }

  function saveConclusionText(): void {
    if (isReadonly.value) return
    debouncedSave([
      { item_id: ITEM_IDS.conclusion, conclusion: policyConclusion.value || null, remark: conclusionText.value },
    ])
  }

  // ─── Hydrate ─────────────────────────────────────────────────────────────

  function hydrate(): void {
    isLoading.value = true
    try {
      const get = (id: string) => allResponses.value.get(id)

      // Section 2
      policyOverviewLeft.value = get(ITEM_IDS.overviewLeft)?.remark ?? ''
      policyOverviewRight.value = get(ITEM_IDS.overviewRight)?.remark ?? ''

      // Section 3
      eclModelPortfolio.value = get(ITEM_IDS.eclPortfolio)?.remark ?? ''
      eclModelIndividual.value = get(ITEM_IDS.eclIndividual)?.remark ?? ''
      eclModelMigration.value = get(ITEM_IDS.eclMigration)?.remark ?? ''
      eclModelRight.value = get(ITEM_IDS.eclRight)?.remark ?? ''

      // Section 4
      const flagVal = get(ITEM_IDS.changeFlag)?.conclusion ?? ''
      policyChangeFlag.value = (flagVal === '是' || flagVal === '否') ? flagVal : ''
      policyChangeContent.value = get(ITEM_IDS.changeContent)?.remark ?? ''
      policyChangeReason.value = get(ITEM_IDS.changeReason)?.remark ?? ''

      // Section 5
      const concVal = get(ITEM_IDS.conclusion)?.conclusion ?? ''
      policyConclusion.value = (['合理', '基本合理但需关注', '不合理'].includes(concVal)
        ? concVal as PolicyConclusion
        : '')
      conclusionText.value = get(ITEM_IDS.conclusion)?.remark ?? ''
    } finally {
      isLoading.value = false
    }
  }

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    // Section 2: 政策概述
    policyOverviewLeft,
    policyOverviewRight,
    savePolicyOverview,

    // Section 3: ECL模型
    eclModelPortfolio,
    eclModelIndividual,
    eclModelMigration,
    eclModelRight,
    saveEclModel,

    // Section 4: 政策变更
    policyChangeFlag,
    policyChangeContent,
    policyChangeReason,
    showPolicyChangeDetails,
    setPolicyChangeFlag,
    savePolicyChange,

    // Section 5: 审计结论
    policyConclusion,
    conclusionText,
    setPolicyConclusion,
    saveConclusionText,

    // 加载状态
    isLoading,
    hydrate,
  }
}
