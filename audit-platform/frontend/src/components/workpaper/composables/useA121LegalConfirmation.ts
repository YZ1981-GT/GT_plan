/**
 * useA121LegalConfirmation — A12-1 法律事务确认函 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a12-1-legal-confirmation/
 * Task: 2.1
 *
 * 职责：
 * - reactive sendSection + replySection
 * - litigation list CRUD (add/remove/update)
 * - 2s debounce save (item_id: `a121-{part}-{field}`)
 * - flush pending saves
 * - JSON serialization for litigation rows
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface LitigationRecord {
  description: string | null
  opinion: string | null
  estimated_loss: number | null
}

export interface SendRecipient {
  firm_name: string | null
  lawyer_name: string | null
}

export interface SendSignInfo {
  company_name: string | null
  date: string | null
}

export interface ReplyInfoTable {
  address: string | null
  phone: string | null
  contact: string | null
}

export interface SendSection {
  recipient: SendRecipient
  explanation_text: string
  inquiry_1: { litigation_list: LitigationRecord[] }
  inquiry_2: { content: string | null }
  inquiry_3: { content: string | null }
  simplified_note: string
  sign_info: SendSignInfo
  reply_info_table: ReplyInfoTable
}

export interface ReplySign {
  firm_name: string | null
  lawyer_name: string | null
  date: string | null
}

export interface ReplySection {
  litigation_status: 'no_litigation' | 'has_litigation' | null
  litigation_details: string | null
  fee_status: 'no_outstanding' | 'has_outstanding' | null
  outstanding_amount: number | null
  sign: ReplySign
}

export interface A121MetaInfo {
  client_name: string
  audit_period: string
  index_no: string
}

export interface A121CrossReferences {
  a5_3_wp_id: string | null
}

export interface A121ProjectContext {
  client_name: string
  audit_period: string
}

export interface A121RenderData {
  meta_info?: Partial<A121MetaInfo>
  send_section?: Partial<SendSection>
  reply_section?: Partial<ReplySection>
  cross_references?: Partial<A121CrossReferences>
  project_context?: Partial<A121ProjectContext>
}

export interface UseA121Options {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData: Ref<A121RenderData | null>
}

export interface UseA121Return {
  metaInfo: Ref<A121MetaInfo>
  sendSection: Ref<SendSection>
  replySection: Ref<ReplySection>
  crossReferences: Ref<A121CrossReferences>
  projectContext: Ref<A121ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  loading: Ref<boolean>
  // Computed conditionals
  showLitigationDetails: ComputedRef<boolean>
  showOutstandingAmount: ComputedRef<boolean>
  // Litigation CRUD
  addLitigation: () => void
  removeLitigation: (index: number) => void
  updateLitigation: (index: number, field: string, value: any) => void
  // Field updates
  updateField: (part: 'send' | 'reply', field: string, value: any) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Build item_id for A12-1 fields */
export function buildA121ItemId(part: 'send' | 'reply', field: string): string {
  return `a121-${part}-${field}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA121LegalConfirmation(opts: UseA121Options): UseA121Return {
  const { wpId, htmlData } = opts

  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')

  const metaInfo = ref<A121MetaInfo>({
    client_name: '',
    audit_period: '',
    index_no: 'A12-1',
  })

  const sendSection = ref<SendSection>({
    recipient: { firm_name: null, lawyer_name: null },
    explanation_text: '',
    inquiry_1: { litigation_list: [] },
    inquiry_2: { content: null },
    inquiry_3: { content: null },
    simplified_note: '',
    sign_info: { company_name: null, date: null },
    reply_info_table: { address: null, phone: null, contact: null },
  })

  const replySection = ref<ReplySection>({
    litigation_status: null,
    litigation_details: null,
    fee_status: null,
    outstanding_amount: null,
    sign: { firm_name: null, lawyer_name: null, date: null },
  })

  const crossReferences = ref<A121CrossReferences>({ a5_3_wp_id: null })

  const projectContext = ref<A121ProjectContext>({
    client_name: '',
    audit_period: '',
  })

  // ─── Computed: conditional logic ───
  const showLitigationDetails = computed(() => {
    return replySection.value.litigation_status === 'has_litigation'
  })

  const showOutstandingAmount = computed(() => {
    return replySection.value.fee_status === 'has_outstanding'
  })

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Hydrate from render data ───
  function hydrateFromRenderData(data: A121RenderData | null) {
    if (!data) return
    if (data.meta_info) {
      Object.assign(metaInfo.value, data.meta_info)
    }
    if (data.send_section) {
      const s = data.send_section
      if (s.recipient) Object.assign(sendSection.value.recipient, s.recipient)
      if (s.explanation_text) sendSection.value.explanation_text = s.explanation_text
      if (s.inquiry_1?.litigation_list) {
        sendSection.value.inquiry_1.litigation_list = s.inquiry_1.litigation_list.map(r => ({ ...r }))
      }
      if (s.inquiry_2) Object.assign(sendSection.value.inquiry_2, s.inquiry_2)
      if (s.inquiry_3) Object.assign(sendSection.value.inquiry_3, s.inquiry_3)
      if (s.simplified_note) sendSection.value.simplified_note = s.simplified_note
      if (s.sign_info) Object.assign(sendSection.value.sign_info, s.sign_info)
      if (s.reply_info_table) Object.assign(sendSection.value.reply_info_table, s.reply_info_table)
    }
    if (data.reply_section) {
      const r = data.reply_section
      if (r.litigation_status !== undefined) replySection.value.litigation_status = r.litigation_status ?? null
      if (r.litigation_details !== undefined) replySection.value.litigation_details = r.litigation_details ?? null
      if (r.fee_status !== undefined) replySection.value.fee_status = r.fee_status ?? null
      if (r.outstanding_amount !== undefined) replySection.value.outstanding_amount = r.outstanding_amount ?? null
      if (r.sign) Object.assign(replySection.value.sign, r.sign)
    }
    if (data.cross_references) {
      Object.assign(crossReferences.value, data.cross_references)
    }
    if (data.project_context) {
      Object.assign(projectContext.value, data.project_context)
    }
  }

  watch(htmlData, (newData) => {
    hydrateFromRenderData(newData)
  }, { immediate: true })

  // ─── Litigation CRUD ───
  function addLitigation() {
    sendSection.value.inquiry_1.litigation_list.push({
      description: null,
      opinion: null,
      estimated_loss: null,
    })
    _enqueueLitigationSave()
  }

  function removeLitigation(index: number) {
    const list = sendSection.value.inquiry_1.litigation_list
    if (index < 0 || index >= list.length) return
    list.splice(index, 1)
    _enqueueLitigationSave()
  }

  function updateLitigation(index: number, field: string, value: any) {
    const list = sendSection.value.inquiry_1.litigation_list
    if (index < 0 || index >= list.length) return
    const row = list[index]
    if (field === 'description' || field === 'opinion') {
      (row as any)[field] = value || null
    } else if (field === 'estimated_loss') {
      row.estimated_loss = value != null && value !== '' ? Number(value) : null
    }
    _enqueueLitigationSave()
  }

  function _enqueueLitigationSave() {
    const itemId = 'a121-send-litigation'
    const rows = sendSection.value.inquiry_1.litigation_list.map(r => ({
      description: r.description,
      opinion: r.opinion,
      estimated_loss: r.estimated_loss,
    }))
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: String(rows.length),
      remark: JSON.stringify(rows),
    })
    scheduleSave()
  }

  // ─── Update Field ───
  function updateField(part: 'send' | 'reply', field: string, value: any) {
    if (part === 'send') {
      _updateSendField(field, value)
    } else {
      _updateReplyField(field, value)
    }
  }

  function _updateSendField(field: string, value: any) {
    const v = value || null
    switch (field) {
      case 'recipient-firm':
        sendSection.value.recipient.firm_name = v
        break
      case 'recipient-lawyer':
        sendSection.value.recipient.lawyer_name = v
        break
      case 'inquiry2-content':
        sendSection.value.inquiry_2.content = v
        break
      case 'inquiry3-content':
        sendSection.value.inquiry_3.content = v
        break
      case 'sign-company':
        sendSection.value.sign_info.company_name = v
        break
      case 'sign-date':
        sendSection.value.sign_info.date = v
        break
      case 'reply-address':
        sendSection.value.reply_info_table.address = v
        break
      case 'reply-phone':
        sendSection.value.reply_info_table.phone = v
        break
      case 'reply-contact':
        sendSection.value.reply_info_table.contact = v
        break
    }
    const itemId = buildA121ItemId('send', field)
    // Long text → remark, short values → conclusion
    const isLongText = field === 'inquiry2-content' || field === 'inquiry3-content'
    if (isLongText) {
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: v })
    } else {
      pendingItems.set(itemId, { item_id: itemId, conclusion: v, remark: null })
    }
    scheduleSave()
  }

  function _updateReplyField(field: string, value: any) {
    const v = value || null
    switch (field) {
      case 'status':
        replySection.value.litigation_status = v
        break
      case 'details':
        replySection.value.litigation_details = v
        break
      case 'fee-status':
        replySection.value.fee_status = v
        break
      case 'fee-amount':
        replySection.value.outstanding_amount = v != null && v !== '' ? Number(v) : null
        break
      case 'sign-firm':
        replySection.value.sign.firm_name = v
        break
      case 'sign-lawyer':
        replySection.value.sign.lawyer_name = v
        break
      case 'sign-date':
        replySection.value.sign.date = v
        break
    }
    const itemId = buildA121ItemId('reply', field)
    const isLongText = field === 'details'
    if (isLongText) {
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: v })
    } else {
      const strValue = v != null ? String(v) : null
      pendingItems.set(itemId, { item_id: itemId, conclusion: strValue, remark: null })
    }
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
    sendSection,
    replySection,
    crossReferences,
    projectContext,
    saveStatus,
    loading,
    showLitigationDetails,
    showOutstandingAmount,
    addLitigation,
    removeLitigation,
    updateLitigation,
    updateField,
    flushPendingSaves,
  }
}
