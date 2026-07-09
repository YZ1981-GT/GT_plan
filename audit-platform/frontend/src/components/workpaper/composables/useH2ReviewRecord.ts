/**
 * useH2ReviewRecord — H2-6 在建工程审核记录 composable
 *
 * 签章式结构（基本信息+审核事项逐条+结论签名）
 * 工程项目筛选 + 从H2-2取数工程列表
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.8
 * Requirements: 7.1-7.5
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H2ReviewBasicInfo {
  projectName: string
  projectLocation: string
  constructionUnit: string
  supervisorUnit: string
  contractAmount: number
  reviewDate: string
  reviewer: string
}

export interface H2ReviewItem {
  rowId: string
  /** 审核事项 */
  subject: string
  /** 审核内容 */
  content: string
  /** 合同约定 */
  contractTerms: string
  /** 实际情况 */
  actualStatus: string
  /** 差异 */
  difference: string
  /** 审核意见 */
  opinion: string
  /** 是否异常 */
  isAbnormal: boolean
  /** 进一步程序 */
  furtherProcedure: string
  /** 证据索引 */
  evidenceIndex: string
  /** 审核人 */
  reviewedBy: string
  /** 日期 */
  date: string
  /** 备注 */
  remark: string
}

export interface H2ReviewSignature {
  preparedBy: string
  preparedDate: string
  reviewedBy: string
  reviewedDate: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const BASIC_KEY = 'H2-6-basic-info'
const ITEMS_KEY = 'H2-6-items'
const SIGNATURE_KEY = 'H2-6-signature'
const CONCLUSION_KEY = 'H2-6-conclusion'
const FILTER_KEY = 'H2-6-filter-project'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2ReviewRecord(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const basicInfo = ref<H2ReviewBasicInfo>({
    projectName: '',
    projectLocation: '',
    constructionUnit: '',
    supervisorUnit: '',
    contractAmount: 0,
    reviewDate: '',
    reviewer: '',
  })
  const reviewItems = ref<H2ReviewItem[]>([])
  const signature = ref<H2ReviewSignature>({
    preparedBy: '',
    preparedDate: '',
    reviewedBy: '',
    reviewedDate: '',
  })
  const conclusion = ref('')
  const filterProject = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const bi = _getJson(BASIC_KEY)
    if (bi && typeof bi === 'object') {
      basicInfo.value = {
        projectName: bi.projectName ?? '',
        projectLocation: bi.projectLocation ?? '',
        constructionUnit: bi.constructionUnit ?? '',
        supervisorUnit: bi.supervisorUnit ?? '',
        contractAmount: Number(bi.contractAmount) || 0,
        reviewDate: bi.reviewDate ?? '',
        reviewer: bi.reviewer ?? '',
      }
    }

    const items = _getJson(ITEMS_KEY)
    if (Array.isArray(items)) {
      reviewItems.value = items.map((r: any) => ({
        rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
        subject: r.subject ?? '',
        content: r.content ?? '',
        contractTerms: r.contractTerms ?? '',
        actualStatus: r.actualStatus ?? '',
        difference: r.difference ?? '',
        opinion: r.opinion ?? '',
        isAbnormal: !!r.isAbnormal,
        furtherProcedure: r.furtherProcedure ?? '',
        evidenceIndex: r.evidenceIndex ?? '',
        reviewedBy: r.reviewedBy ?? '',
        date: r.date ?? '',
        remark: r.remark ?? '',
      }))
    } else {
      reviewItems.value = []
    }

    const sig = _getJson(SIGNATURE_KEY)
    if (sig && typeof sig === 'object') {
      signature.value = {
        preparedBy: sig.preparedBy ?? '',
        preparedDate: sig.preparedDate ?? '',
        reviewedBy: sig.reviewedBy ?? '',
        reviewedDate: sig.reviewedDate ?? '',
      }
    }

    conclusion.value = _getString(CONCLUSION_KEY)
    filterProject.value = _getString(FILTER_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed: 从H2-2取数工程列表 ──────────────────────────────────────────

  const projectList: ComputedRef<string[]> = computed(() => {
    const resp = options.allResponses.value.get('H2-2-rows')
    const raw = resp?.remark ?? resp?.conclusion
    if (!raw) return []
    try {
      const rows = JSON.parse(raw)
      if (Array.isArray(rows)) {
        return rows.map((r: any) => r.name ?? '').filter((n: string) => n)
      }
    } catch { /* ignore */ }
    return []
  })

  /** 筛选后的审核事项（按工程名称过滤） */
  const filteredItems: ComputedRef<H2ReviewItem[]> = computed(() => {
    if (!filterProject.value) return reviewItems.value
    return reviewItems.value.filter(
      item => item.subject.includes(filterProject.value) ||
              item.content.includes(filterProject.value),
    )
  })

  /** 异常事项数量 */
  const abnormalCount: ComputedRef<number> = computed(() =>
    reviewItems.value.filter(r => r.isAbnormal).length,
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateBasicInfo(field: keyof H2ReviewBasicInfo, value: any): void {
    if (options.isReadonly.value) return
    ;(basicInfo.value as any)[field] = field === 'contractAmount' ? (Number(value) || 0) : String(value ?? '')
    options.onSave?.(BASIC_KEY, basicInfo.value)
  }

  function addReviewItem(): void {
    if (options.isReadonly.value) return
    reviewItems.value.push({
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      subject: '',
      content: '',
      contractTerms: '',
      actualStatus: '',
      difference: '',
      opinion: '',
      isAbnormal: false,
      furtherProcedure: '',
      evidenceIndex: '',
      reviewedBy: '',
      date: '',
      remark: '',
    })
    _persistItems()
  }

  function removeReviewItem(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = reviewItems.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      reviewItems.value.splice(idx, 1)
      _persistItems()
    }
  }

  function updateReviewItem(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const item = reviewItems.value.find(r => r.rowId === rowId)
    if (!item) return
    if (field === 'isAbnormal') {
      item.isAbnormal = !!value
    } else if (field in item) {
      ;(item as any)[field] = String(value ?? '')
    }
    _persistItems()
  }

  function saveConclusion(text: string): void {
    conclusion.value = text
    options.onSave?.(CONCLUSION_KEY, text)
  }

  function setFilterProject(name: string): void {
    filterProject.value = name
    options.onSave?.(FILTER_KEY, name)
  }

  function saveSignature(sig: Partial<H2ReviewSignature>): void {
    if (options.isReadonly.value) return
    Object.assign(signature.value, sig)
    options.onSave?.(SIGNATURE_KEY, signature.value)
  }

  function _persistItems(): void {
    if (!options.onSave) return
    options.onSave(ITEMS_KEY, reviewItems.value.map(r => ({
      rowId: r.rowId,
      subject: r.subject,
      content: r.content,
      contractTerms: r.contractTerms,
      actualStatus: r.actualStatus,
      difference: r.difference,
      opinion: r.opinion,
      isAbnormal: r.isAbnormal,
      furtherProcedure: r.furtherProcedure,
      evidenceIndex: r.evidenceIndex,
      reviewedBy: r.reviewedBy,
      date: r.date,
      remark: r.remark,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    basicInfo,
    reviewItems,
    signature,
    conclusion,
    filterProject,
    projectList,
    filteredItems,
    abnormalCount,
    updateBasicInfo,
    addReviewItem,
    removeReviewItem,
    updateReviewItem,
    saveConclusion,
    setFilterProject,
    saveSignature,
    initFromAllResponses,
  }
}

export default useH2ReviewRecord
