/**
 * useG10DerivativeCheck — G10-8 衍生金融工具核查（78行5section）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  G10A_DERIVATIVE_MARK_KEY,
  G10A_DERIVATIVE_PROGRAM_NOS,
  buildG10DerivativeProcedureSummary,
  markG10AProcedureSteps,
} from './g10FvCrossHelpers'
import {
  buildG10DerivativeContractNoteFromDetails,
  collectG10DerivativeNonCompliantIssues,
  filterG10DerivativeDetailRows,
  G10_DERIVATIVE_DETAIL_LINKS_KEY,
  parseG10DerivativeDetailLinks,
  pullG10DerivativeLinksFromDetail,
  pushG10DerivativeCheckToDetail,
  pushG10DerivativeIssuesToAdjustment,
  type G10DerivativeDetailLink,
} from './g10DerivativeCross'
import { G10_DETAIL_ROWS_KEY, parseG10DetailRows } from './g10CrossHelpers'
import { G10_DERIVATIVE_SEED } from './g10DerivativeSeed'
import {
  applyG10DerivativeWizardToRows,
  buildG10DerivativeWizardConclusion,
  defaultG10DerivativeWizardState,
  evaluateG10DerivativeWizard,
  parseG10DerivativeWizardState,
  type G10DerivativeWizardState,
  type G10YesNo,
} from './g10DerivativeDecision'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'

export interface G10DerivativeRow {
  rowId: string
  seq: number
  sectionNo: string
  sectionTitle: string
  checkArea: string
  checkItem: string
  auditRequirement: string
  checkResult: string
  compliance: '' | 'compliant' | 'non_compliant' | 'not_applicable'
  riskLevel: '' | 'high' | 'medium' | 'low'
  auditConclusion: string
  indexRef: string
  remark: string
}

const ITEM_ID = 'G10-derivative-rows'
const CONCLUSION_ID = 'G10-derivative-conclusion'
export const ITEM_ID_G10_DERIVATIVE_WIZARD = 'G10-derivative-wizard'
function genId() { return `g10dr-${Date.now().toString(36)}` }

function defaultRows(): G10DerivativeRow[] {
  return G10_DERIVATIVE_SEED.map((s, i) => ({
    rowId: genId() + i,
    seq: i + 1,
    sectionNo: s.sectionNo,
    sectionTitle: s.sectionTitle,
    checkArea: s.checkArea,
    checkItem: s.checkItem,
    auditRequirement: s.auditRequirement,
    checkResult: '',
    compliance: '' as const,
    riskLevel: '' as const,
    auditConclusion: '',
    indexRef: '',
    remark: '',
  }))
}

export function useG10DerivativeCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  wpId?: Ref<string>
  projectId?: Ref<string> | ComputedRef<string>
  year?: Ref<number | null> | ComputedRef<number | null>
}) {
  const rows = ref<G10DerivativeRow[]>(defaultRows())
  const wizard = ref<G10DerivativeWizardState>(defaultG10DerivativeWizardState())
  const wizardStep = ref(0)
  const overallConclusion = ref('')
  const aiLoading = ref(false)
  const procedureMarking = ref(false)
  const detailLinks = ref<G10DerivativeDetailLink[]>([])
  const useVirtualScroll = computed(() => rows.value.length > 50)

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    if (!j) { rows.value = defaultRows(); return }
    try {
      const parsed = JSON.parse(j)
      rows.value = Array.isArray(parsed) && parsed.length ? parsed : defaultRows()
    } catch { rows.value = defaultRows() }
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(CONCLUSION_ID)?.conclusion, (v) => {
    overallConclusion.value = v ?? ''
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(ITEM_ID_G10_DERIVATIVE_WIZARD)?.remark, (j) => {
    wizard.value = parseG10DerivativeWizardState(j)
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(G10_DERIVATIVE_DETAIL_LINKS_KEY)?.remark, (j) => {
    detailLinks.value = parseG10DerivativeDetailLinks(j)
  }, { immediate: true })

  const wizardEval = computed(() => evaluateG10DerivativeWizard(wizard.value))

  const linkedDetailCount = computed(() => detailLinks.value.length)

  const unmatchedDerivativeDetailCount = computed(() => {
    const derivatives = filterG10DerivativeDetailRows(
      parseG10DetailRows(opts.allResponses.value.get(G10_DETAIL_ROWS_KEY)?.remark),
    )
    if (!derivatives.length) return 0
    const linked = new Set(detailLinks.value.map((l) => l.detailRowId))
    return derivatives.filter((d) => !linked.has(d.rowId)).length
  })

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G10A_DERIVATIVE_MARK_KEY)?.remark
    || opts.allResponses.value.get(G10A_DERIVATIVE_MARK_KEY)?.conclusion === 'completed',
  )

  const sections = computed(() => {
    const map = new Map<string, G10DerivativeRow[]>()
    for (const r of rows.value) {
      const key = `${r.sectionNo} ${r.sectionTitle}`
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(r)
    }
    return [...map.entries()].map(([title, sectionRows]) => ({ title, rows: sectionRows }))
  })

  const missingCompliance = computed(() => rows.value.filter((r) => !r.compliance))

  const nonCompliantIssues = computed(() => collectG10DerivativeNonCompliantIssues(rows.value))

  const nonCompliantCount = computed(() => nonCompliantIssues.value.length)

  function persist() {
    opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(rows.value) })
  }

  function updateCell(rowId: string, field: keyof G10DerivativeRow, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = { ...next[idx], [field]: value }
    rows.value = next
    persist()
  }

  function persistWizard(): void {
    opts.debouncedSave(ITEM_ID_G10_DERIVATIVE_WIZARD, { remark: JSON.stringify(wizard.value) })
  }

  function updateWizard(patch: Partial<G10DerivativeWizardState>): void {
    if (opts.isReadonly.value) return
    wizard.value = { ...wizard.value, ...patch }
    persistWizard()
  }

  function updateWizardVariable(key: string, value: G10YesNo): void {
    if (opts.isReadonly.value) return
    wizard.value = {
      ...wizard.value,
      variableAnswers: { ...wizard.value.variableAnswers, [key]: value },
    }
    persistWizard()
  }

  function applyWizardToConclusion(): void {
    const text = buildG10DerivativeWizardConclusion(wizard.value)
    wizard.value = { ...wizard.value, wizardConclusion: text }
    persistWizard()
    updateOverallConclusion(text)
  }

  function applyWizardToQuestionnaire(overwrite = false): number {
    if (opts.isReadonly.value) return 0
    const { rows: next, filled } = applyG10DerivativeWizardToRows(rows.value, wizard.value, { overwrite })
    if (!filled) {
      ElMessage.info('向导未完成或无可自动勾选的问卷行（请先完成步骤 B～E）')
      return 0
    }
    rows.value = next
    persist()
    ElMessage.success(`已根据向导勾选 ${filled} 行问卷`)
    return filled
  }

  function applyWizardAll(): void {
    applyWizardToConclusion()
    applyWizardToQuestionnaire(false)
  }

  function setWizardStep(step: number): void {
    wizardStep.value = Math.max(0, Math.min(4, step))
  }

  function updateOverallConclusion(v: string) {
    if (opts.isReadonly.value) return
    overallConclusion.value = v
    opts.debouncedSave(CONCLUSION_ID, { conclusion: v })
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g10/ai/derivative-conclusion`,
        { existingContent: overallConclusion.value, rows: rows.value },
        { _silent: true } as any,
      )
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateOverallConclusion(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  function validateBeforeSave(): boolean {
    const missing = missingCompliance.value
    if (missing.length) {
      ElMessage.warning(`还有 ${missing.length} 行未选择「是否合规」`)
      return false
    }
    return true
  }

  function syncFromDetail(): number {
    if (opts.isReadonly.value) return 0
    const derivatives = filterG10DerivativeDetailRows(
      parseG10DetailRows(opts.allResponses.value.get(G10_DETAIL_ROWS_KEY)?.remark),
    )
    if (!derivatives.length) {
      ElMessage.warning('G10-2 无衍生负债行（请勾选「衍生」或类型为衍生金融负债）')
      return 0
    }
    const links = pullG10DerivativeLinksFromDetail(opts.allResponses.value)
    detailLinks.value = links
    opts.debouncedSave(G10_DERIVATIVE_DETAIL_LINKS_KEY, { remark: JSON.stringify(links) })
    const note = buildG10DerivativeContractNoteFromDetails(derivatives)
    if (note) {
      wizard.value = { ...wizard.value, contractReviewNote: note }
      persistWizard()
    }
    ElMessage.success(`已从 G10-2 带入 ${derivatives.length} 个衍生负债项目`)
    return derivatives.length
  }

  function pushToDetail(): number {
    if (opts.isReadonly.value) return 0
    const links = detailLinks.value.length
      ? detailLinks.value
      : pullG10DerivativeLinksFromDetail(opts.allResponses.value)
    if (!links.length) {
      ElMessage.warning('请先「从 G10-2 带入」衍生负债项目')
      return 0
    }
    const n = pushG10DerivativeCheckToDetail(
      opts.allResponses.value,
      opts.debouncedSave,
      {
        links,
        wizardConclusion: wizard.value.wizardConclusion || wizardEval.value.summary,
        overallConclusion: overallConclusion.value,
        indexRef: 'G10-8',
      },
    )
    if (!n) {
      ElMessage.warning('未匹配到 G10-2 衍生行，请核对项目名称')
      return 0
    }
    ElMessage.success(`已回写 G10-2 ${n} 行（嵌入衍生判断/索引）`)
    return n
  }

  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G10A')
      return -1
    }
    if (missingCompliance.value.length) {
      try {
        await ElMessageBox.confirm(
          `仍有 ${missingCompliance.value.length} 行未填合规，是否仍标记 G10A 衍生工具程序为已完成？`,
          '回填 G10A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }
    procedureMarking.value = true
    try {
      const summary = buildG10DerivativeProcedureSummary({
        questionnaireRows: rows.value.length,
        missingCompliance: missingCompliance.value.length,
        linkedDetailCount: linkedDetailCount.value,
        wizardSummary: wizardEval.value.summary,
      })
      const n = await markG10AProcedureSteps({
        projectId: pid,
        year: opts.year?.value ?? undefined,
        programNos: [...G10A_DERIVATIVE_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G10-8/G10-2',
        executionSummary: summary,
      })
      opts.debouncedSave(G10A_DERIVATIVE_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary,
          programNos: [...G10A_DERIVATIVE_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? `已回填 G10A 程序步骤 ${[...G10A_DERIVATIVE_PROGRAM_NOS].join('/')}（衍生工具核查）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G10A 查看）',
      )
      return Math.max(n, 1)
    } finally {
      procedureMarking.value = false
    }
  }

  async function pushIssuesToAdjustment(): Promise<number> {
    if (opts.isReadonly.value) return 0
    const issues = nonCompliantIssues.value
    if (!issues.length) {
      ElMessage.info('无「不合规」问卷项可推送')
      return 0
    }
    try {
      await ElMessageBox.confirm(
        `将为 ${issues.length} 项不合规检查各生成 1 组备忘 AJE（金额 0，待追查补录），写入 G10-3。`,
        '推送不合规→G10-3',
        { type: 'warning', confirmButtonText: '推送', cancelButtonText: '取消' },
      )
    } catch {
      return 0
    }
    const { pushed, skipped } = pushG10DerivativeIssuesToAdjustment(
      opts.allResponses.value,
      opts.debouncedSave,
      issues,
    )
    if (!pushed) {
      ElMessage.info(skipped ? 'G10-3 已存在相同摘要的衍生不合规草稿，未重复追加' : '无可推送项')
      return 0
    }
    const skipHint = skipped ? `（跳过 ${skipped} 项重复）` : ''
    ElMessage.success(`已向 G10-3 推送 ${pushed} 项衍生不合规备忘${skipHint}`)
    return pushed
  }

  return {
    rows,
    sections,
    wizard,
    wizardStep,
    wizardEval,
    overallConclusion,
    aiLoading,
    useVirtualScroll,
    missingCompliance,
    nonCompliantCount,
    linkedDetailCount,
    unmatchedDerivativeDetailCount,
    procedureMarking,
    procedureMarked,
    updateCell,
    updateWizard,
    updateWizardVariable,
    applyWizardToConclusion,
    applyWizardToQuestionnaire,
    applyWizardAll,
    setWizardStep,
    updateOverallConclusion,
    generateAiConclusion,
    validateBeforeSave,
    syncFromDetail,
    pushToDetail,
    pushIssuesToAdjustment,
    markProcedureComplete,
    persist,
    ITEM_ID,
  }
}
