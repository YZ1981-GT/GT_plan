/**
 * useD2BizModel — 业务模式D2-13核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 15.1
 *
 * 职责：
 * - BizModelJudgment 类型（4个Y/N问题）+ BizModelGroup 类型（5列）
 * - judgments reactive（4项）, groups reactive
 * - allAnswered computed, recommendedModel computed（决策逻辑）
 * - addGroup / removeGroup / updateJudgment / updateGroup
 *
 * 决策逻辑：
 * - 仅收取合同现金流量 → 摊余成本计量
 * - 仅出售金融资产 → 以公允价值计量且其变动计入当期损益(FVTPL)
 * - 兼有收取与出售 → 以公允价值计量且其变动计入其他综合收益(FVOCI)
 * - SPPI不满足 → FVTPL
 *
 * Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface BizModelJudgment {
  questionId: string
  question: string             // 判断问题
  answer: 'Y' | 'N' | ''      // Y/N/未回答
  explanation: string          // 说明
}

export interface BizModelGroup {
  rowId: string
  groupName: string            // 组合名称
  bizModel: string             // 业务模式分类
  sppiResult: string           // SPPI测试结果
  measurementBasis: string     // 计量基础
  remark: string               // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

const JUDGMENTS_KEY = 'D2-bizmodel-judgments'
const GROUPS_KEY = 'D2-bizmodel-groups'
const NOTE_KEY = 'D2-bizmodel-note'
const CONCLUSION_KEY = 'D2-bizmodel-conclusion'

/** 默认4个判断问题 */
const DEFAULT_JUDGMENTS: BizModelJudgment[] = [
  {
    questionId: 'q1',
    question: '管理金融资产的业务模式是否以收取合同现金流量为目标？',
    answer: '',
    explanation: '',
  },
  {
    questionId: 'q2',
    question: '管理金融资产的业务模式是否以出售金融资产为目标？',
    answer: '',
    explanation: '',
  },
  {
    questionId: 'q3',
    question: '管理金融资产的业务模式是否兼有收取合同现金流量和出售金融资产？',
    answer: '',
    explanation: '',
  },
  {
    questionId: 'q4',
    question: '合同现金流量特征是否仅为对本金和以未偿付本金为基础的利息的支付（SPPI测试）？',
    answer: '',
    explanation: '',
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `bm-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptyGroup(): BizModelGroup {
  return {
    rowId: generateRowId(),
    groupName: '',
    bizModel: '',
    sppiResult: '',
    measurementBasis: '',
    remark: '',
  }
}

function parseJudgments(jsonStr: string | null | undefined): BizModelJudgment[] {
  if (!jsonStr) return DEFAULT_JUDGMENTS.map(j => ({ ...j }))
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return DEFAULT_JUDGMENTS.map(j => ({ ...j }))
    }
    return parsed.map((raw: any) => ({
      questionId: raw.questionId || '',
      question: raw.question || '',
      answer: (['Y', 'N'].includes(raw.answer) ? raw.answer : '') as BizModelJudgment['answer'],
      explanation: raw.explanation || '',
    }))
  } catch {
    return DEFAULT_JUDGMENTS.map(j => ({ ...j }))
  }
}

function parseGroups(jsonStr: string | null | undefined): BizModelGroup[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      groupName: raw.groupName || '',
      bizModel: raw.bizModel || '',
      sppiResult: raw.sppiResult || '',
      measurementBasis: raw.measurementBasis || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2BizModel(options: UseD2BaseOptions) {
  const { allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const judgments = ref<BizModelJudgment[]>(DEFAULT_JUDGMENTS.map(j => ({ ...j })))
  const groups = ref<BizModelGroup[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadData(): void {
    const jResp = allResponses.value.get(JUDGMENTS_KEY)
    judgments.value = parseJudgments(jResp?.remark)

    const gResp = allResponses.value.get(GROUPS_KEY)
    groups.value = parseGroups(gResp?.remark)

    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark ?? ''
  }

  watch(
    () => [
      allResponses.value.get(JUDGMENTS_KEY)?.remark,
      allResponses.value.get(GROUPS_KEY)?.remark,
    ],
    () => {
      const isInitial = judgments.value.every(j => !j.answer && !j.explanation)
      if (isInitial) {
        loadData()
      }
    },
    { immediate: true }
  )

  // ─── Computed ──────────────────────────────────────────────────────────

  const allAnswered: ComputedRef<boolean> = computed(() => {
    return judgments.value.every(j => j.answer !== '')
  })

  /**
   * 推荐业务模式（基于4问判断的决策逻辑）
   *
   * 决策树：
   * 1. SPPI不满足(q4=N) → FVTPL
   * 2. 仅收取(q1=Y, q2=N, q3=N) → 摊余成本
   * 3. 仅出售(q1=N, q2=Y, q3=N) → FVTPL
   * 4. 兼有(q3=Y) → FVOCI
   * 5. 其他/未完成 → ''
   */
  const recommendedModel: ComputedRef<string> = computed(() => {
    if (!allAnswered.value) return ''

    const answers: Record<string, string> = {}
    for (const j of judgments.value) {
      answers[j.questionId] = j.answer
    }

    // SPPI不满足 → FVTPL
    if (answers['q4'] === 'N') {
      return '以公允价值计量且其变动计入当期损益(FVTPL)'
    }

    // 仅收取合同现金流量 → 摊余成本
    if (answers['q1'] === 'Y' && answers['q2'] === 'N' && answers['q3'] === 'N') {
      return '以摊余成本计量'
    }

    // 仅出售 → FVTPL
    if (answers['q1'] === 'N' && answers['q2'] === 'Y' && answers['q3'] === 'N') {
      return '以公允价值计量且其变动计入当期损益(FVTPL)'
    }

    // 兼有 → FVOCI
    if (answers['q3'] === 'Y') {
      return '以公允价值计量且其变动计入其他综合收益(FVOCI)'
    }

    return ''
  })

  // ─── Update Operations ─────────────────────────────────────────────────

  function updateJudgment(questionId: string, field: 'answer' | 'explanation', value: string): void {
    if (isReadonly.value) return
    const judgment = judgments.value.find(j => j.questionId === questionId)
    if (!judgment) return

    if (field === 'answer') {
      judgment.answer = (['Y', 'N'].includes(value) ? value : '') as BizModelJudgment['answer']
    } else {
      judgment.explanation = value
    }
    debounceSave()
  }

  function updateGroup(rowId: string, field: string, value: string): void {
    if (isReadonly.value) return
    const group = groups.value.find(g => g.rowId === rowId)
    if (!group) return

    const key = field as keyof BizModelGroup
    if (key === 'rowId') return
    ;(group as any)[key] = value
    debounceSave()
  }

  function addGroup(): void {
    if (isReadonly.value) return
    groups.value.push(createEmptyGroup())
    debounceSave()
  }

  function removeGroup(rowId: string): void {
    if (isReadonly.value) return
    const idx = groups.value.findIndex(g => g.rowId === rowId)
    if (idx === -1) return
    groups.value.splice(idx, 1)
    debounceSave()
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const items = [
      { item_id: JUDGMENTS_KEY, conclusion: null, remark: JSON.stringify(judgments.value) },
      { item_id: GROUPS_KEY, conclusion: null, remark: JSON.stringify(groups.value) },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    dispatchSaveEvent(items)
  }

  function dispatchSaveEvent(items: any[]): void {
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  function saveText(key: string, value: string): void {
    if (isReadonly.value) return
    const item = { item_id: key, conclusion: null, remark: value }
    allResponses.value.set(key, item)
    dispatchSaveEvent([item])
  }

  function saveAuditNote(value: string): void {
    auditNote.value = value
    saveText(NOTE_KEY, value)
  }

  function saveAuditConclusion(value: string): void {
    auditConclusion.value = value
    saveText(CONCLUSION_KEY, value)
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
    judgments,
    groups,
    allAnswered,
    recommendedModel,
    auditNote,
    auditConclusion,
    updateJudgment,
    updateGroup,
    addGroup,
    removeGroup,
    saveAuditNote,
    saveAuditConclusion,
  }
}

export default useD2BizModel
