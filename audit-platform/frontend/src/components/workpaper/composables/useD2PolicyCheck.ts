/**
 * useD2PolicyCheck — 政策检查D2-8核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 12.1
 *
 * 职责：
 * - PolicyParagraph 类型定义（6字段）
 * - paragraphs reactive（6个政策段落）
 * - completedCount / totalCount computed
 * - hasNonCompliant computed（是否存在不合规项）
 * - updateParagraph（conclusion→即时保存，文本→debounce）
 *
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PolicyParagraph {
  paragraphId: string
  title: string                // 政策段落标题
  policyDescription: string    // 政策条款描述（只读）
  actualSituation: string      // 被审计单位实际情况（可编辑）
  auditorEvaluation: string    // 审计师评价（可编辑）
  conclusion: 'Y' | 'N' | 'NA' | ''  // 结论
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D2-policy-paragraphs'

/** 默认6个政策检查段落 */
const DEFAULT_PARAGRAPHS: PolicyParagraph[] = [
  {
    paragraphId: 'p1',
    title: '应收账款确认条件',
    policyDescription: '企业应当在履行了合同中的履约义务，即在客户取得相关商品或服务控制权时确认收入及应收账款。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
  {
    paragraphId: 'p2',
    title: '坏账准备计提政策',
    policyDescription: '企业应当以预期信用损失为基础，对应收账款进行减值会计处理并确认损失准备。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
  {
    paragraphId: 'p3',
    title: '应收账款终止确认',
    policyDescription: '企业转移了应收账款所有权上几乎所有的风险和报酬的，应当终止确认该应收账款。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
  {
    paragraphId: 'p4',
    title: '应收账款列报与披露',
    policyDescription: '应收账款应当按照扣除坏账准备后的净额列示。按欠款方归集的期末余额前五名的应收账款情况应予披露。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
  {
    paragraphId: 'p5',
    title: '外币应收账款折算',
    policyDescription: '以外币计价的应收账款，在资产负债表日应当按照期末即期汇率折算，差额计入财务费用。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
  {
    paragraphId: 'p6',
    title: '关联方应收账款',
    policyDescription: '关联方之间的应收账款应单独披露，并说明交易的定价政策及其公允性。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseParagraphs(jsonStr: string | null | undefined): PolicyParagraph[] {
  if (!jsonStr) return DEFAULT_PARAGRAPHS.map(p => ({ ...p }))
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return DEFAULT_PARAGRAPHS.map(p => ({ ...p }))
    }
    return parsed.map((raw: any) => ({
      paragraphId: raw.paragraphId || '',
      title: raw.title || '',
      policyDescription: raw.policyDescription || '',
      actualSituation: raw.actualSituation || '',
      auditorEvaluation: raw.auditorEvaluation || '',
      conclusion: (['Y', 'N', 'NA'].includes(raw.conclusion) ? raw.conclusion : '') as PolicyParagraph['conclusion'],
    }))
  } catch {
    return DEFAULT_PARAGRAPHS.map(p => ({ ...p }))
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2PolicyCheck(options: UseD2BaseOptions) {
  const { allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const paragraphs = ref<PolicyParagraph[]>(DEFAULT_PARAGRAPHS.map(p => ({ ...p })))
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadData(): void {
    const resp = allResponses.value.get(STORAGE_KEY)
    paragraphs.value = parseParagraphs(resp?.remark)
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => {
      // Only reload on initial
      const isInitial = paragraphs.value.every(p => !p.actualSituation && !p.auditorEvaluation && !p.conclusion)
      if (isInitial) {
        loadData()
      }
    },
    { immediate: true }
  )

  // ─── Computed ──────────────────────────────────────────────────────────

  const totalCount: ComputedRef<number> = computed(() => {
    return paragraphs.value.length
  })

  const completedCount: ComputedRef<number> = computed(() => {
    return paragraphs.value.filter(p => p.conclusion !== '').length
  })

  /**
   * 是否存在不合规项（conclusion='N'）
   */
  const hasNonCompliant: ComputedRef<boolean> = computed(() => {
    return paragraphs.value.some(p => p.conclusion === 'N')
  })

  // ─── Update Paragraph ──────────────────────────────────────────────────

  /**
   * 更新段落字段
   * - conclusion → 即时保存（关键判断项）
   * - actualSituation / auditorEvaluation → debounce 2s 保存
   */
  function updateParagraph(id: string, field: string, value: string): void {
    if (isReadonly.value) return
    const paragraph = paragraphs.value.find(p => p.paragraphId === id)
    if (!paragraph) return

    if (field === 'conclusion') {
      paragraph.conclusion = (['Y', 'N', 'NA'].includes(value) ? value : '') as PolicyParagraph['conclusion']
      immediateSave()
    } else if (field === 'actualSituation') {
      paragraph.actualSituation = value
      debounceSave()
    } else if (field === 'auditorEvaluation') {
      paragraph.auditorEvaluation = value
      debounceSave()
    }
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function immediateSave(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    flushSave()
  }

  function flushSave(): void {
    const json = JSON.stringify(paragraphs.value)
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    dispatchSaveEvent(json)
  }

  function dispatchSaveEvent(json: string): void {
    try {
      const items = [{ item_id: STORAGE_KEY, conclusion: null, remark: json }]
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    paragraphs,
    completedCount,
    totalCount,
    hasNonCompliant,
    updateParagraph,
  }
}

export default useD2PolicyCheck
