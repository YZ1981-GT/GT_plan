/**
 * useA101GovernanceCommunication — A10-1 与治理层沟通函 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a10-1-governance-communication/
 * Task: 2.1
 *
 * 职责：
 * - reactive state: recipient, 16 chapters, 5 service fees, signing section
 * - computed totalFee (sum of non-null amounts)
 * - 2s debounce save (item_id: `a101-*`)
 * - flush pending saves
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface A101MetaInfo {
  client_name: string
  audit_period: string
  index_no: string
}

export interface A101ChapterData {
  number: number
  title: string
  content: string | null
  cross_ref: string | null
}

export interface A101ServiceFeeRow {
  name: string
  amount: number | null
}

export interface A101SigningSection {
  firm_name: string | null
  partner_name: string | null
  date: string | null
}

export interface A101CrossReferences {
  a9_2_wp_id: string | null
  a13_wp_id: string | null
}

export interface A101ProjectContext {
  client_name: string
  audit_period: string
  firm_name: string
}

export interface A101RenderData {
  meta_info?: Partial<A101MetaInfo>
  recipient?: string | null
  introduction_text?: string[]
  chapters?: A101ChapterData[]
  service_fees?: A101ServiceFeeRow[]
  signing_section?: Partial<A101SigningSection>
  guidance_notes?: string
  cross_references?: Partial<A101CrossReferences>
  project_context?: Partial<A101ProjectContext>
}

export interface UseA101Options {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData: Ref<A101RenderData | null>
}

export interface UseA101Return {
  metaInfo: Ref<A101MetaInfo>
  recipient: Ref<string>
  introductionText: Ref<string[]>
  chapters: Ref<A101ChapterData[]>
  serviceFees: Ref<A101ServiceFeeRow[]>
  signingSection: Ref<A101SigningSection>
  guidanceNotes: Ref<string>
  crossReferences: Ref<A101CrossReferences>
  projectContext: Ref<A101ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  totalFee: ComputedRef<number>
  // Actions
  updateRecipient: (value: string) => void
  updateChapter: (chapterNumber: number, content: string) => void
  updateFee: (index: number, amount: number | null) => void
  updateSigning: (field: string, value: string) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEFAULT_CHAPTERS: A101ChapterData[] = [
  { number: 1, title: '审计的范围和时间安排', content: null, cross_ref: null },
  { number: 2, title: '审计中发现的重大问题', content: null, cross_ref: null },
  { number: 3, title: '非审计服务费用', content: null, cross_ref: null },
  { number: 4, title: '独立性声明', content: null, cross_ref: null },
  { number: 5, title: '审计中发现的重大错报', content: null, cross_ref: null },
  { number: 6, title: '已更正的错报', content: null, cross_ref: null },
  { number: 7, title: '已向管理层通报的内部控制缺陷', content: null, cross_ref: null },
  { number: 8, title: '会计估计和相关披露', content: null, cross_ref: null },
  { number: 9, title: '其他需要通报的内部控制缺陷', content: null, cross_ref: 'A9-2' },
  { number: 10, title: '审计中遇到的重大困难', content: null, cross_ref: null },
  { number: 11, title: '与管理层讨论的重大问题', content: null, cross_ref: null },
  { number: 12, title: '修改后的计划审计范围和时间安排', content: null, cross_ref: null },
  { number: 13, title: '未更正错报', content: null, cross_ref: 'A13' },
  { number: 14, title: '其他需要注意的事项', content: null, cross_ref: null },
  { number: 15, title: '与审计相关的其他信息', content: null, cross_ref: null },
  { number: 16, title: '致同就被审计单位治理层的提醒', content: null, cross_ref: null },
]

const DEFAULT_SERVICE_FEES: A101ServiceFeeRow[] = [
  { name: '审计服务', amount: null },
  { name: '审阅服务', amount: null },
  { name: '其他鉴证服务', amount: null },
  { name: '税务服务', amount: null },
  { name: '其他服务', amount: null },
]

/** Build item_id for A10-1 fields */
export function buildA101ItemId(section: string, field: string): string {
  return `a101-${section}-${field}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA101GovernanceCommunication(opts: UseA101Options): UseA101Return {
  const { wpId, htmlData } = opts

  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')

  const metaInfo = ref<A101MetaInfo>({
    client_name: '',
    audit_period: '',
    index_no: 'A10-1',
  })

  const recipient = ref('')
  const introductionText = ref<string[]>([])
  const chapters = ref<A101ChapterData[]>(DEFAULT_CHAPTERS.map(ch => ({ ...ch })))
  const serviceFees = ref<A101ServiceFeeRow[]>(DEFAULT_SERVICE_FEES.map(f => ({ ...f })))
  const signingSection = ref<A101SigningSection>({
    firm_name: null,
    partner_name: null,
    date: null,
  })
  const guidanceNotes = ref('')

  const crossReferences = ref<A101CrossReferences>({
    a9_2_wp_id: null,
    a13_wp_id: null,
  })

  const projectContext = ref<A101ProjectContext>({
    client_name: '',
    audit_period: '',
    firm_name: '致同会计师事务所（特殊普通合伙）',
  })

  // ─── Computed: totalFee ───
  const totalFee = computed(() => {
    return serviceFees.value.reduce((sum, row) => {
      return sum + (row.amount ?? 0)
    }, 0)
  })

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Hydrate from render data ───
  function hydrateFromRenderData(data: A101RenderData | null) {
    if (!data) return
    if (data.meta_info) Object.assign(metaInfo.value, data.meta_info)
    if (data.recipient != null) recipient.value = data.recipient || ''
    if (data.introduction_text) introductionText.value = data.introduction_text
    if (data.chapters && Array.isArray(data.chapters) && data.chapters.length === 16) {
      chapters.value = data.chapters.map(ch => ({ ...ch }))
    }
    if (data.service_fees && Array.isArray(data.service_fees) && data.service_fees.length === 5) {
      serviceFees.value = data.service_fees.map(f => ({ ...f }))
    }
    if (data.signing_section) Object.assign(signingSection.value, data.signing_section)
    if (data.guidance_notes) guidanceNotes.value = data.guidance_notes
    if (data.cross_references) Object.assign(crossReferences.value, data.cross_references)
    if (data.project_context) Object.assign(projectContext.value, data.project_context)
  }

  watch(htmlData, (newData) => {
    hydrateFromRenderData(newData)
  }, { immediate: true })

  // ─── Update Recipient ───
  function updateRecipient(value: string) {
    recipient.value = value
    const itemId = 'a101-recipient'
    pendingItems.set(itemId, { item_id: itemId, conclusion: value || null, remark: null })
    scheduleSave()
  }

  // ─── Update Chapter ───
  function updateChapter(chapterNumber: number, content: string) {
    const idx = chapterNumber - 1
    if (idx < 0 || idx >= 16) return
    chapters.value[idx].content = content || null
    const itemId = `a101-ch${chapterNumber}-content`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: content || null })
    scheduleSave()
  }

  // ─── Update Fee ───
  function updateFee(index: number, amount: number | null) {
    if (index < 0 || index >= 5) return
    serviceFees.value[index].amount = amount
    // Save all fees as single JSON array
    const itemId = 'a101-fee'
    const feesJson = JSON.stringify(serviceFees.value.map(f => ({ name: f.name, amount: f.amount })))
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: feesJson })
    scheduleSave()
  }

  // ─── Update Signing ───
  function updateSigning(field: string, value: string) {
    if (field === 'firm_name' || field === 'partner_name' || field === 'date') {
      signingSection.value[field] = value || null
    }
    const itemId = `a101-sign-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: value || null, remark: null })
    scheduleSave()
  }

  // ─── Debounce Save ───
  function scheduleSave() {
    saveStatus.value = 'unsaved'
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveTimer = null; doSave() }, 2000)
  }

  async function doSave(retryCount = 0) {
    if (pendingItems.size === 0) return
    const items = [...pendingItems.values()]
    pendingItems.clear()
    saveStatus.value = 'saving'

    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, { items })
      saveStatus.value = 'saved'
    } catch {
      if (retryCount < 3) {
        for (const item of items) pendingItems.set(item.item_id, item)
        setTimeout(() => doSave(retryCount + 1), 1000 * (retryCount + 1))
        return
      }
      saveStatus.value = 'unsaved'
      ElMessage.warning('保存失败，请检查网络后重试')
    }
  }

  // ─── Flush ───
  async function flushPendingSaves(): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    await doSave()
  }

  return {
    metaInfo,
    recipient,
    introductionText,
    chapters,
    serviceFees,
    signingSection,
    guidanceNotes,
    crossReferences,
    projectContext,
    saveStatus,
    totalFee,
    updateRecipient,
    updateChapter,
    updateFee,
    updateSigning,
    flushPendingSaves,
  }
}
