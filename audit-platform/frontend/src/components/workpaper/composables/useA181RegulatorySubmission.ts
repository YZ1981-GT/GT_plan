/**
 * useA181RegulatorySubmission — A18-1 向监管部门报送审计小结 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a18-1-regulatory-submission/
 * Task: 2.1
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface A181Recipient { bureau: string }
export interface A181Body { contact_person: string; contact_phone: string }
export interface A181Issuance { partner: string; date: string }
export interface A181ProjectContext { client_name: string; audit_year: string; firm_name: string; partner_name: string }

export interface UseA181Return {
  loading: Ref<boolean>
  recipient: Ref<A181Recipient>
  body: Ref<A181Body>
  issuance: Ref<A181Issuance>
  projectContext: Ref<A181ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  lastSavedAt: Ref<Date | null>
  loadData: (wpId: string) => Promise<void>
  updateField: (section: string, field: string, value: string) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA181RegulatorySubmission(wpId: Ref<string>): UseA181Return {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)

  const recipient = ref<A181Recipient>({ bureau: '' })
  const body = ref<A181Body>({ contact_person: '', contact_phone: '' })
  const issuance = ref<A181Issuance>({ partner: '', date: '' })
  const projectContext = ref<A181ProjectContext>({
    client_name: '', audit_year: '', firm_name: '致同会计师事务所（特殊普通合伙）', partner_name: '',
  })

  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=a18-1-regulatory-submission`,
        { _silent: true } as any,
      )
      const htmlData = res?.sheets?.[0]?.html_data ?? res
      if (htmlData?.recipient) Object.assign(recipient.value, htmlData.recipient)
      if (htmlData?.body) Object.assign(body.value, htmlData.body)
      if (htmlData?.issuance) Object.assign(issuance.value, htmlData.issuance)
      if (htmlData?.project_context) Object.assign(projectContext.value, htmlData.project_context)
    } catch { /* 静态结构无需后端 */ }
    finally { loading.value = false }
  }

  function updateField(section: string, field: string, value: string) {
    // Update reactive state
    if (section === 'recipient' && field in recipient.value) {
      (recipient.value as any)[field] = value
    } else if (section === 'body' && field in body.value) {
      (body.value as any)[field] = value
    } else if (section === 'issuance' && field in issuance.value) {
      (issuance.value as any)[field] = value
    }
    const itemId = `a181-${section}-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

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
      lastSavedAt.value = new Date()
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

  async function flushPendingSaves(): Promise<void> {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
    await doSave()
  }

  return { loading, recipient, body, issuance, projectContext, saveStatus, lastSavedAt, loadData, updateField, flushPendingSaves }
}
