/** useA177IndependenceDeclaration — A17-7 独立性声明书 多章节+双模式+AI+批量签署 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export type Variant = 'team' | 'committee'
export type ThreatType = 'economic_interest' | 'loan_guarantee' | 'business_relation'
export interface MetaInfo { client_name: string; audit_year: string; index_no: string }
export interface PeriodData { business_start: string | null; business_end: string | null; report_start: string | null; report_end: string | null }
export interface CommitmentItem { id: string; label: string; answer: 'Y' | 'N' | null; explanation: string | null }
export interface SignRow { index: number; name: string; signed: boolean; date: string | null }
export interface PartnerSection { confirmed: boolean | null; explanation: string | null; partner_sign: { name: string | null; date: string | null }; manager_sign: { name: string | null; date: string | null } }
export interface EconomicThreatRow { member: string; type: string; amount: string; measure: string }
export interface LoanThreatRow { member: string; type: string; amount: string; measure: string }
export interface BusinessThreatRow { member: string; description: string; measure: string }
export interface ThreatRecords { economic_interest: EconomicThreatRow[]; loan_guarantee: LoanThreatRow[]; business_relation: BusinessThreatRow[] }
export interface ProjectContext { client_name: string; audit_year: string; team_members: { name: string }[]; project_id: string }
export interface ChapterData { title: string; type: 'declaration' | 'commitment' | 'signing' | 'partner' | 'threat' }
export function getPrefix(variant: Variant): string { return variant === 'committee' ? 'a177a-' : 'a177-' }
export const DEFAULT_CHAPTERS: Record<string, ChapterData> = {
  '1': { title: '一、声明正文及业务期间', type: 'declaration' },
  '2': { title: '二、独立性承诺事项', type: 'commitment' },
  '3': { title: '三、项目组成员签字确认', type: 'signing' },
  '4': { title: '四、合伙人及负责经理审查确认', type: 'partner' },
  '5': { title: '五、独立性威胁记录（附件）', type: 'threat' },
}
export const CHAPTER_GUIDANCE: Record<number, string> = {
  1: '独立性声明书应在业务承接阶段签署，并在项目执行过程中如有变化及时更新。\n业务期间指自审计业务承接之日起至审计报告签发之日止的期间。\n财务报告期间指被审计单位财务报表所涵盖的期间。',
  2: '经济利益包括直接经济利益和重大间接经济利益，含股票、债券、基金等投资。\n贷款与担保包括项目组成员或其近亲属与客户之间的贷款或担保关系。\n如对上述任何事项回答"是"，请在说明栏简述具体情况并在附件中记录详细措施。',
  3: '项目组全体成员均须签字确认。签字即表明本人已阅读上述独立性承诺事项并确认遵守。\n可通过"发送确认"按钮将独立性声明弹窗推送给全体项目组成员进行电子签署确认。',
  4: '合伙人审查确认：项目合伙人应审查全体成员的签字及威胁披露情况。\n如确认不存在独立性问题选择"是"，如发现问题选择"否"并说明措施。',
  5: '如存在独立性威胁，应在此附件中如实披露：\n1.经济利益记录 2.贷款担保记录 3.商业关系记录\n无任何威胁时可不填写此附件。',
}
export const DEFAULT_COMMITMENT_ITEMS: CommitmentItem[] = [
  { id: 'economic', label: '本人及直系亲属不持有被审计单位及其关联方的直接或重大间接经济利益', answer: null, explanation: null },
  { id: 'loan', label: '本人及直系亲属与被审计单位及其关联方之间不存在贷款或担保关系', answer: null, explanation: null },
  { id: 'business', label: '本人及直系亲属与被审计单位之间不存在可能产生自身利益威胁的商业关系', answer: null, explanation: null },
  { id: 'family', label: '本人的近亲属未在被审计单位及其关联方担任董事、经理或特定会计岗位', answer: null, explanation: null },
  { id: 'employment', label: '本人未曾在被审计单位担任董事、经理或特定会计岗位（或已满足冷却期要求）', answer: null, explanation: null },
]
export const DECLARATION_TEMPLATES: Record<Variant, string> = {
  team: '本人确认，在本项目的业务期间及财务报告期间内，本人及直系亲属与被审计单位之间不存在可能影响独立性的利害关系。如存在上述情形，已在附件中如实披露并采取了适当防范措施。',
  committee: '本人作为专业技术委员会审核委员，确认在参与本项目的独立性判断过程中，本人与被审计单位之间不存在可能影响判断客观性的利害关系。',
}

export interface SigningProgress {
  total: number
  signed: number
  complete: boolean
}

export function useA177IndependenceDeclaration(
  wpId: Ref<string>,
  opts?: { projectId?: Ref<string> },
) {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)

  const variant = ref<Variant>('team')
  const metaInfo = ref<MetaInfo>({ client_name: '', audit_year: '', index_no: 'A17-7' })
  const declarationText = ref(DECLARATION_TEMPLATES.team)
  const periodData = ref<PeriodData>({
    business_start: null, business_end: null, report_start: null, report_end: null,
  })
  const commitmentItems = ref<CommitmentItem[]>(
    DEFAULT_COMMITMENT_ITEMS.map((i) => ({ ...i })),
  )
  const teamSignTable = ref<SignRow[]>([])
  const partnerSection = ref<PartnerSection>({
    confirmed: null,
    explanation: null,
    partner_sign: { name: null, date: null },
    manager_sign: { name: null, date: null },
  })
  const threatRecords = ref<ThreatRecords>({
    economic_interest: [], loan_guarantee: [], business_relation: [],
  })
  const projectContext = ref<ProjectContext>({
    client_name: '', audit_year: '', team_members: [], project_id: '',
  })
  const chapters = ref<Record<string, ChapterData>>({ ...DEFAULT_CHAPTERS })
  const signingProgress = ref<SigningProgress>({ total: 0, signed: 0, complete: false })

  // ─── Debounced persistence (checklist_responses, item_id prefix a177-/a177a-) ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    saveStatus.value = 'unsaved'
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveTimer = null; void doSave() }, 2000)
  }

  async function doSave(retryCount = 0): Promise<void> {
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

  // ─── Load (render-config?force_component_type=a17-7-independence-declaration) ───
  async function loadData(id?: string): Promise<void> {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=a17-7-independence-declaration`,
        { _silent: true } as any,
      )
      const data = res?.data ?? res
      const htmlData = data?.sheets?.[0]?.html_data ?? data
      if (!htmlData) return

      if (htmlData.variant) variant.value = htmlData.variant
      if (htmlData.meta_info) Object.assign(metaInfo.value, htmlData.meta_info)
      if (htmlData.declaration_text) declarationText.value = htmlData.declaration_text
      if (htmlData.period_data) Object.assign(periodData.value, htmlData.period_data)
      if (Array.isArray(htmlData.commitment_items) && htmlData.commitment_items.length) {
        commitmentItems.value = htmlData.commitment_items.map((i: any) => ({
          id: i.id, label: i.label, answer: i.answer ?? null, explanation: i.explanation ?? null,
        }))
      }
      if (Array.isArray(htmlData.team_sign_table)) {
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
      if (htmlData.project_context) Object.assign(projectContext.value, htmlData.project_context)
    } catch {
      // 静默降级：保留默认静态结构
    } finally {
      loading.value = false
    }
  }

  // ─── Team sign table CRUD ───
  function _enqueueSignTableSave(): void {
    const prefix = getPrefix(variant.value)
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

  function addTeamMember(): void {
    const nextIndex = teamSignTable.value.length > 0
      ? Math.max(...teamSignTable.value.map((r) => r.index)) + 1
      : 1
    teamSignTable.value.push({ index: nextIndex, name: '', signed: false, date: null })
    _enqueueSignTableSave()
  }

  function removeTeamMember(index: number): void {
    if (index >= 0 && index < teamSignTable.value.length) {
      teamSignTable.value.splice(index, 1)
      teamSignTable.value.forEach((row, i) => { row.index = i + 1 })
      _enqueueSignTableSave()
    }
  }

  function updateTeamMember(index: number, field: keyof SignRow, value: any): void {
    if (index >= 0 && index < teamSignTable.value.length) {
      ;(teamSignTable.value[index] as any)[field] = value
      _enqueueSignTableSave()
    }
  }

  // ─── Commitment items ───
  function updateCommitment(id: string, field: 'answer' | 'explanation', value: any): void {
    const item = commitmentItems.value.find((i) => i.id === id)
    if (!item) return
    ;(item as any)[field] = value
    const prefix = getPrefix(variant.value)
    const itemId = `${prefix}commit-${id}`
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: item.answer,
      remark: item.explanation || null,
    })
    scheduleSave()
  }

  // ─── Threat records CRUD ───
  function _enqueueThreatSave(type: ThreatType): void {
    const prefix = getPrefix(variant.value)
    const typeKey = type === 'economic_interest' ? 'economic' : type === 'loan_guarantee' ? 'loan' : 'business'
    threatRecords.value[type].forEach((row, i) => {
      const itemId = `${prefix}threat-${typeKey}-${i + 1}`
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(row) })
    })
    scheduleSave()
  }

  function addThreatRow(type: ThreatType): void {
    if (type === 'business_relation') {
      threatRecords.value.business_relation.push({ member: '', description: '', measure: '' })
    } else {
      threatRecords.value[type].push({ member: '', type: '', amount: '', measure: '' })
    }
    _enqueueThreatSave(type)
  }

  function removeThreatRow(type: ThreatType, index: number): void {
    const arr = threatRecords.value[type]
    if (index >= 0 && index < arr.length) {
      arr.splice(index, 1)
      _enqueueThreatSave(type)
    }
  }

  function updateThreatRow(type: ThreatType, index: number, field: string, value: string): void {
    const arr = threatRecords.value[type]
    if (index >= 0 && index < arr.length) {
      ;(arr[index] as any)[field] = value
      _enqueueThreatSave(type)
    }
  }

  // ─── Period / Partner ───
  function updatePeriod(field: keyof PeriodData, value: string | null): void {
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

  function updatePartner(field: string, value: any): void {
    const prefix = getPrefix(variant.value)
    if (field === 'confirmed') {
      partnerSection.value.confirmed = value
      pendingItems.set(`${prefix}partner-confirmed`, {
        item_id: `${prefix}partner-confirmed`, conclusion: value ? 'Y' : 'N', remark: null,
      })
    } else if (field === 'explanation') {
      partnerSection.value.explanation = value
      pendingItems.set(`${prefix}partner-explanation`, {
        item_id: `${prefix}partner-explanation`, conclusion: null, remark: value || '',
      })
    } else if (field === 'partner_sign' || field === 'manager_sign') {
      ;(partnerSection.value as any)[field] = value
      pendingItems.set(`${prefix}${field.replace('_', '-')}`, {
        item_id: `${prefix}${field.replace('_', '-')}`, conclusion: null, remark: JSON.stringify(value),
      })
    }
    scheduleSave()
  }

  // ─── Batch signing (independence_signing_service) ───
  function _signingYear(): string {
    return metaInfo.value.audit_year || projectContext.value.audit_year || String(new Date().getFullYear())
  }

  function _templateCode(): string {
    return variant.value === 'committee' ? 'A17-7A' : 'A17-7'
  }

  async function initiateSigningBatch(): Promise<void> {
    const pid = opts?.projectId?.value || projectContext.value.project_id
    if (!pid) { ElMessage.warning('缺少项目信息，无法发起签署'); return }
    try {
      await api.post(
        `/api/projects/${pid}/signing/${_signingYear()}/initiate?template_code=${_templateCode()}`,
      )
      ElMessage.success('已向项目组成员发送签署确认')
      await refreshSigningProgress()
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.detail || '发送签署确认失败')
    }
  }

  async function refreshSigningProgress(): Promise<void> {
    const pid = opts?.projectId?.value || projectContext.value.project_id
    if (!pid) return
    try {
      const res = await api.get<any>(
        `/api/projects/${pid}/signing/${_signingYear()}/progress?template_code=${_templateCode()}`,
        { _silent: true } as any,
      )
      const data = res?.data ?? res
      if (data && typeof data === 'object') {
        const total = Number(data.total ?? data.total_count ?? 0)
        const signed = Number(data.signed ?? data.signed_count ?? 0)
        signingProgress.value = {
          total,
          signed,
          complete: data.complete ?? (total > 0 && signed >= total),
        }
      }
    } catch {
      // 签署进度获取失败不阻塞页面
    }
  }

  // ─── AI 章节生成 ───
  async function aiGenerateChapter(chapterNum: number): Promise<string> {
    const chapter = chapters.value[String(chapterNum)]
    try {
      const res = await api.post<any>(`/api/workpapers/${wpId.value}/a177/ai-generate`, {
        chapter: chapterNum,
        chapter_title: chapter?.title || `章节${chapterNum}`,
        guidance: CHAPTER_GUIDANCE[chapterNum] || '',
        variant: variant.value,
        existing_content: chapterNum === 1 ? declarationText.value : '',
      })
      const data = res?.data ?? res
      return data?.content || ''
    } catch {
      ElMessage.error('AI 生成失败，请稍后重试')
      return ''
    }
  }

  return {
    loading,
    variant,
    metaInfo,
    declarationText,
    periodData,
    commitmentItems,
    teamSignTable,
    partnerSection,
    threatRecords,
    projectContext,
    saveStatus,
    lastSavedAt,
    chapters,
    signingProgress,
    addTeamMember,
    removeTeamMember,
    updateTeamMember,
    updateCommitment,
    addThreatRow,
    removeThreatRow,
    updateThreatRow,
    updatePeriod,
    updatePartner,
    loadData,
    flushPendingSaves,
    initiateSigningBatch,
    refreshSigningProgress,
    aiGenerateChapter,
  }
}
