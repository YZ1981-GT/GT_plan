/**
 * useA177IndependenceDeclaration — A17-7 独立性声明书 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a17-7-independence-declaration/
 * Task: 2.1
 *
 * 职责：
 * - loadData(wpId): 自加载 render-config?force_component_type=a17-7-independence-declaration
 * - variant-aware item_id prefix (a177- / a177a-)
 * - Team sign table CRUD (add/remove/update)
 * - Threat record CRUD (3 types: economic/loans/business)
 * - 2s debounce save, flush pending saves
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export type Variant = 'team' | 'committee'
export type ThreatType = 'economic_interest' | 'loan_guarantee' | 'business_relation'

export interface MetaInfo {
  client_name: string
  audit_year: string
  index_no: string
}

export interface PeriodData {
  business_start: string | null
  business_end: string | null
  report_start: string | null
  report_end: string | null
}

export interface SignRow {
  index: number
  name: string
  signed: boolean
  date: string | null
}

export interface PartnerSection {
  confirmed: boolean | null
  explanation: string | null
  partner_sign: { name: string | null; date: string | null }
  manager_sign: { name: string | null; date: string | null }
}

export interface EconomicThreatRow {
  member: string
  type: string
  amount: string
  measure: string
}

export interface LoanThreatRow {
  member: string
  type: string
  amount: string
  measure: string
}

export interface BusinessThreatRow {
  member: string
  description: string
  measure: string
}

export interface ThreatRecords {
  economic_interest: EconomicThreatRow[]
  loan_guarantee: LoanThreatRow[]
  business_relation: BusinessThreatRow[]
}

export interface ProjectContext {
  client_name: string
  audit_year: string
  team_members: { name: string }[]
}

export interface UseA177Return {
  loading: Ref<boolean>
  variant: Ref<Variant>
  metaInfo: Ref<MetaInfo>
  declarationText: Ref<string>
  periodData: Ref<PeriodData>
  teamSignTable: Ref<SignRow[]>
  partnerSection: Ref<PartnerSection>
  threatRecords: Ref<ThreatRecords>
  guidanceNotes: Ref<string[]>
  projectContext: Ref<ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  lastSavedAt: Ref<Date | null>
  // Team sign table CRUD
  addTeamMember: () => void
  removeTeamMember: (index: number) => void
  updateTeamMember: (index: number, field: keyof SignRow, value: any) => void
  // Threat record CRUD
  addThreatRow: (type: ThreatType) => void
  removeThreatRow: (type: ThreatType, index: number) => void
  updateThreatRow: (type: ThreatType, index: number, field: string, value: string) => void
  // General
  updatePeriod: (field: keyof PeriodData, value: string | null) => void
  updatePartner: (field: string, value: any) => void
  loadData: (id?: string) => Promise<void>
  flushPendingSaves: () => Promise<void>
}

// ─── Helper: get prefix from variant ─────────────────────────────────────────

export function getPrefix(variant: Variant): string {
  return variant === 'committee' ? 'a177a-' : 'a177-'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA177IndependenceDeclaration(wpId: Ref<string>): UseA177Return {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)

  const variant = ref<Variant>('team')
  const metaInfo = ref<MetaInfo>({ client_name: '', audit_year: '', index_no: 'A17-7' })
  const declarationText = ref('')
  const periodData = ref<PeriodData>({
    business_start: null,
    business_end: null,
    report_start: null,
    report_end: null,
  })
  const teamSignTable = ref<SignRow[]>([])
  const partnerSection = ref<PartnerSection>({
    confirmed: null,
    explanation: null,
    partner_sign: { name: null, date: null },
    manager_sign: { name: null, date: null },
  })
  const threatRecords = ref<ThreatRecords>({
    economic_interest: [],
    loan_guarantee: [],
    business_relation: [],
  })
  const guidanceNotes = ref<string[]>([])
  const projectContext = ref<ProjectContext>({
    client_name: '',
    audit_year: '',
    team_members: [],
  })

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load Data ───
  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=a17-7-independence-declaration`,
        { _silent: true } as any,
      )
      const htmlData = res?.sheets?.[0]?.html_data ?? res
      if (!htmlData) return

      if (htmlData.variant) variant.value = htmlData.variant
      if (htmlData.meta_info) Object.assign(metaInfo.value, htmlData.meta_info)
      if (htmlData.declaration_text) declarationText.value = htmlData.declaration_text
      if (htmlData.period_data) Object.assign(periodData.value, htmlData.period_data)
      if (htmlData.team_sign_table && Array.isArray(htmlData.team_sign_table)) {
        teamSignTable.value = htmlData.team_sign_table.map((r: any, i: number) => ({
          index: r.index ?? i + 1,
          name: r.name || '',
          signed: !!r.signed,
          date: r.date || null,
        }))
      }
      if (htmlData.partner_section) {
        partnerSection.value = {
          confirmed: htmlData.partner_section.confirmed ?? null,
          explanation: htmlData.partner_section.explanation ?? null,
          partner_sign: htmlData.partner_section.partner_sign || { name: null, date: null },
          manager_sign: htmlData.partner_section.manager_sign || { name: null, date: null },
        }
      }
      if (htmlData.threat_records) {
        threatRecords.value = {
          economic_interest: htmlData.threat_records.economic_interest || [],
          loan_guarantee: htmlData.threat_records.loan_guarantee || [],
          business_relation: htmlData.threat_records.business_relation || [],
        }
      }
      if (htmlData.guidance_notes) guidanceNotes.value = htmlData.guidance_notes
      if (htmlData.project_context) Object.assign(projectContext.value, htmlData.project_context)
    } catch {
      // Silent fail — static structure
    } finally {
      loading.value = false
    }
  }

  // ─── Team Sign Table CRUD ───
  function addTeamMember() {
    const nextIndex = teamSignTable.value.length > 0
      ? Math.max(...teamSignTable.value.map(r => r.index)) + 1
      : 1
    teamSignTable.value.push({ index: nextIndex, name: '', signed: false, date: null })
    _enqueueSignTableSave()
  }

  function removeTeamMember(index: number) {
    if (index >= 0 && index < teamSignTable.value.length) {
      teamSignTable.value.splice(index, 1)
      // Re-index
      teamSignTable.value.forEach((row, i) => { row.index = i + 1 })
      _enqueueSignTableSave()
    }
  }

  function updateTeamMember(index: number, field: keyof SignRow, value: any) {
    if (index >= 0 && index < teamSignTable.value.length) {
      ;(teamSignTable.value[index] as any)[field] = value
      _enqueueSignTableSave()
    }
  }

  function _enqueueSignTableSave() {
    const prefix = getPrefix(variant.value)
    // Save each row individually
    teamSignTable.value.forEach((row, i) => {
      const itemId = `${prefix}sign-${i + 1}`
      pendingItems.set(itemId, {
        item_id: itemId,
        conclusion: null,
        remark: JSON.stringify({ name: row.name, signed: row.signed, date: row.date }),
      })
    })
    scheduleSave()
  }

  // ─── Threat Record CRUD ───
  function addThreatRow(type: ThreatType) {
    if (type === 'economic_interest') {
      threatRecords.value.economic_interest.push({ member: '', type: '', amount: '', measure: '' })
    } else if (type === 'loan_guarantee') {
      threatRecords.value.loan_guarantee.push({ member: '', type: '', amount: '', measure: '' })
    } else if (type === 'business_relation') {
      threatRecords.value.business_relation.push({ member: '', description: '', measure: '' })
    }
    _enqueueThreatSave(type)
  }

  function removeThreatRow(type: ThreatType, index: number) {
    const arr = threatRecords.value[type]
    if (index >= 0 && index < arr.length) {
      arr.splice(index, 1)
      _enqueueThreatSave(type)
    }
  }

  function updateThreatRow(type: ThreatType, index: number, field: string, value: string) {
    const arr = threatRecords.value[type]
    if (index >= 0 && index < arr.length) {
      ;(arr[index] as any)[field] = value
      _enqueueThreatSave(type)
    }
  }

  function _enqueueThreatSave(type: ThreatType) {
    const prefix = getPrefix(variant.value)
    const typeKey = type === 'economic_interest' ? 'economic' : type === 'loan_guarantee' ? 'loan' : 'business'
    const arr = threatRecords.value[type]
    arr.forEach((row, i) => {
      const itemId = `${prefix}threat-${typeKey}-${i + 1}`
      pendingItems.set(itemId, {
        item_id: itemId,
        conclusion: null,
        remark: JSON.stringify(row),
      })
    })
    scheduleSave()
  }

  // ─── Update Period ───
  function updatePeriod(field: keyof PeriodData, value: string | null) {
    periodData.value[field] = value
    const prefix = getPrefix(variant.value)
    const fieldMap: Record<keyof PeriodData, string> = {
      business_start: 'period-business-start',
      business_end: 'period-business-end',
      report_start: 'period-report-start',
      report_end: 'period-report-end',
    }
    const itemId = `${prefix}${fieldMap[field]}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value || '' })
    scheduleSave()
  }

  // ─── Update Partner ───
  function updatePartner(field: string, value: any) {
    const prefix = getPrefix(variant.value)
    if (field === 'confirmed') {
      partnerSection.value.confirmed = value
      const itemId = `${prefix}partner-confirmed`
      pendingItems.set(itemId, { item_id: itemId, conclusion: value ? 'Y' : 'N', remark: null })
    } else if (field === 'explanation') {
      partnerSection.value.explanation = value
      const itemId = `${prefix}partner-explanation`
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value || '' })
    } else if (field === 'partner_sign') {
      partnerSection.value.partner_sign = value
      const itemId = `${prefix}partner-sign`
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(value) })
    } else if (field === 'manager_sign') {
      partnerSection.value.manager_sign = value
      const itemId = `${prefix}manager-sign`
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(value) })
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

  // ─── Flush ───
  async function flushPendingSaves(): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    await doSave()
  }

  return {
    loading,
    variant,
    metaInfo,
    declarationText,
    periodData,
    teamSignTable,
    partnerSection,
    threatRecords,
    guidanceNotes,
    projectContext,
    saveStatus,
    lastSavedAt,
    addTeamMember,
    removeTeamMember,
    updateTeamMember,
    addThreatRow,
    removeThreatRow,
    updateThreatRow,
    updatePeriod,
    updatePartner,
    loadData,
    flushPendingSaves,
  }
}
