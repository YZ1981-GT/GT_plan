/**
 * useA182RegulatoryCommunication — A18-2 与监管层沟通函 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a18-2-regulatory-communication/
 * Task: 2.1
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface A182Recipient { authority: string; custom: string }
export interface A182Matter { id: number; title: string; applicability: 'Y' | 'N' | 'NA' | null; content: string }
export interface A182Issuance { cpa1: string; cpa2: string; date: string }
export interface A182ProjectContext { client_name: string; audit_year: string; firm_name: string }

export interface UseA182Return {
  loading: Ref<boolean>
  recipient: Ref<A182Recipient>
  matters: Ref<A182Matter[]>
  issuance: Ref<A182Issuance>
  projectContext: Ref<A182ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  lastSavedAt: Ref<Date | null>
  loadData: (wpId?: string) => Promise<void>
  updateRecipient: (field: string, value: string) => void
  updateMatter: (matterId: number, field: 'applicability' | 'content', value: string) => void
  updateIssuance: (field: string, value: string) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const MATTER_TITLES: string[] = [
  '舞弊',
  '重大违反法律法规行为',
  '年度报告中信息不一致或错报',
  '其他事项',
]

function createDefaultMatters(): A182Matter[] {
  return MATTER_TITLES.map((title, i) => ({
    id: i + 1,
    title,
    applicability: null,
    content: '',
  }))
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA182RegulatoryCommunication(wpId: Ref<string>): UseA182Return {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)

  const recipient = ref<A182Recipient>({ authority: '', custom: '' })
  const matters = ref<A182Matter[]>(createDefaultMatters())
  const issuance = ref<A182Issuance>({ cpa1: '', cpa2: '', date: '' })
  const projectContext = ref<A182ProjectContext>({
    client_name: '', audit_year: '', firm_name: '致同会计师事务所（特殊普通合伙）',
  })

  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=a18-2-regulatory-communication`,
        { _silent: true } as any,
      )
      const htmlData = res?.sheets?.[0]?.html_data ?? res
      if (htmlData?.recipient) Object.assign(recipient.value, htmlData.recipient)
      if (htmlData?.matters && Array.isArray(htmlData.matters)) {
        matters.value = htmlData.matters.map((m: any, i: number) => ({
          id: m.id ?? i + 1,
          title: m.title ?? MATTER_TITLES[i] ?? '',
          applicability: m.applicability ?? null,
          content: m.content ?? '',
        }))
      }
      if (htmlData?.issuance) Object.assign(issuance.value, htmlData.issuance)
      if (htmlData?.project_context) Object.assign(projectContext.value, htmlData.project_context)
    } catch { /* 静态结构无需后端 */ }
    finally { loading.value = false }
  }

  function updateRecipient(field: string, value: string) {
    if (field in recipient.value) {
      (recipient.value as any)[field] = value
    }
    const itemId = `a182-recipient-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

  function updateMatter(matterId: number, field: 'applicability' | 'content', value: string) {
    const matter = matters.value.find(m => m.id === matterId)
    if (matter) {
      if (field === 'applicability') {
        matter.applicability = value as 'Y' | 'N' | 'NA' | null
      } else {
        matter.content = value
      }
    }
    const itemId = `a182-matter${matterId}-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

  function updateIssuance(field: string, value: string) {
    if (field in issuance.value) {
      (issuance.value as any)[field] = value
    }
    const itemId = `a182-sign-${field}`
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

  return {
    loading, recipient, matters, issuance, projectContext,
    saveStatus, lastSavedAt, loadData, updateRecipient, updateMatter, updateIssuance, flushPendingSaves,
  }
}
