/**
 * useA81OtherInfoRepresentation — A8-1 管理层对其他信息的书面声明 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a8-1-other-info-representation/
 * Task: 2.1
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface A81Statements {
  1: { files: string[] }
  2: { date: string | null }
  3: { consistency: 'Y' | 'N' | null; explanation: string | null }
  4: { files: string[] }
  5: { files: string[] }
  6: { other: string | null }
}

export interface A81SignatureData {
  representative: string | null
  signatureDate: string | null
}

export interface A81ProjectContext {
  clientName: string
  auditReportDate: string | null
  cpaNames: string[]
}

export interface UseA81Return {
  loading: Ref<boolean>
  statements: Ref<A81Statements>
  signatureData: Ref<A81SignatureData>
  projectContext: Ref<A81ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  lastSavedAt: Ref<Date | null>
  loadData: (wpId: string) => Promise<void>
  addFile: (statementNum: 1 | 4 | 5, fileName: string) => void
  removeFile: (statementNum: 1 | 4 | 5, index: number) => void
  updateStatement: (statementNum: number, fieldId: string, value: any) => void
  updateSignature: (fieldId: string, value: string) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA81OtherInfoRepresentation(wpId: Ref<string>): UseA81Return {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)

  const statements = ref<A81Statements>({
    1: { files: [] },
    2: { date: null },
    3: { consistency: null, explanation: null },
    4: { files: [] },
    5: { files: [] },
    6: { other: null },
  })

  const signatureData = ref<A81SignatureData>({
    representative: null,
    signatureDate: null,
  })

  const projectContext = ref<A81ProjectContext>({
    clientName: '',
    auditReportDate: null,
    cpaNames: [],
  })

  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=a8-1-other-info-representation`,
        { _silent: true } as any,
      )
      const htmlData = res?.sheets?.[0]?.html_data ?? res
      if (htmlData?.statements) {
        const s = htmlData.statements
        if (s['1']) statements.value[1] = { files: s['1'].files || [] }
        if (s['2']) statements.value[2] = { date: s['2'].date || null }
        if (s['3']) statements.value[3] = {
          consistency: s['3'].consistency || null,
          explanation: s['3'].explanation || null,
        }
        if (s['4']) statements.value[4] = { files: s['4'].files || [] }
        if (s['5']) statements.value[5] = { files: s['5'].files || [] }
        if (s['6']) statements.value[6] = { other: s['6'].other || null }
      }
      if (htmlData?.signature_data) {
        const sig = htmlData.signature_data
        signatureData.value.representative = sig.representative || null
        signatureData.value.signatureDate = sig.signature_date || null
      }
      if (htmlData?.project_context) {
        const ctx = htmlData.project_context
        projectContext.value.clientName = ctx.client_name || ''
        projectContext.value.auditReportDate = ctx.audit_report_date || null
        projectContext.value.cpaNames = ctx.cpa_names || []
        // Default signature date to audit_report_date if not already set
        if (!signatureData.value.signatureDate && ctx.audit_report_date) {
          signatureData.value.signatureDate = ctx.audit_report_date
        }
      }
    } catch { /* 静态结构无需后端 */ }
    finally { loading.value = false }
  }

  function addFile(statementNum: 1 | 4 | 5, fileName: string) {
    if (!fileName.trim()) return
    const list = statements.value[statementNum].files
    list.push(fileName.trim())
    _enqueueFileListSave(statementNum)
  }

  function removeFile(statementNum: 1 | 4 | 5, index: number) {
    const list = statements.value[statementNum].files
    if (index >= 0 && index < list.length) {
      list.splice(index, 1)
      _enqueueFileListSave(statementNum)
    }
  }

  function _enqueueFileListSave(statementNum: 1 | 4 | 5) {
    const list = statements.value[statementNum].files
    const itemId = `a81-statement-${statementNum}-files`
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: String(list.length),
      remark: JSON.stringify(list),
    })
    scheduleSave()
  }

  function updateStatement(statementNum: number, fieldId: string, value: any) {
    const key = statementNum as keyof A81Statements
    if (statementNum === 2 && fieldId === 'date') {
      statements.value[2].date = value || null
      const itemId = `a81-statement-2-date`
      pendingItems.set(itemId, { item_id: itemId, conclusion: value || '', remark: null })
    } else if (statementNum === 3 && fieldId === 'consistency') {
      statements.value[3].consistency = value || null
      const itemId = `a81-statement-3-consistency`
      pendingItems.set(itemId, { item_id: itemId, conclusion: value || '', remark: null })
    } else if (statementNum === 3 && fieldId === 'explanation') {
      statements.value[3].explanation = value || null
      const itemId = `a81-statement-3-explanation`
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value || '' })
    } else if (statementNum === 6 && fieldId === 'other') {
      statements.value[6].other = value || null
      const itemId = `a81-statement-6-other`
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value || '' })
    }
    scheduleSave()
  }

  function updateSignature(fieldId: string, value: string) {
    if (fieldId === 'representative') {
      signatureData.value.representative = value || null
    } else if (fieldId === 'date') {
      signatureData.value.signatureDate = value || null
    }
    const itemId = `a81-signature-${fieldId}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value || '' })
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
    loading, statements, signatureData, projectContext,
    saveStatus, lastSavedAt,
    loadData, addFile, removeFile, updateStatement, updateSignature, flushPendingSaves,
  }
}
