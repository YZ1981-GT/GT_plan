/**
 * useI2PolicyCheck — I2-4 会计政策检查
 */
import { ref, computed, watch, type Ref } from 'vue'
import {
  type I2PolicyCasItem,
  type I2PolicyProcessItem,
  type I2PolicyInterview,
  type I2PolicyPeerRow,
  type I2PolicyReasonableness,
  emptyInterview,
  emptyProcessItems,
  emptyCasItems,
  emptyPeerRow,
  emptyReasonableness,
  normalizeInterview,
  normalizeProcessItems,
  normalizeCasItems,
  normalizePeerRows,
  normalizeReasonableness,
  evaluateI2PolicyCompleteness,
  buildReasonablenessNarrative,
  I2_POLICY_DEFAULT_CONCLUSION,
} from './i2PolicyCheckModel'
import {
  appendI23DraftAje,
  I2_INDUSTRY_PEER_TEMPLATES,
  listI27ProjectNames,
  writeSheetCompletionMarker,
} from './i2EnhancementHelpers'

export {
  type I2PolicyCasItem,
  type I2PolicyProcessItem,
  type I2PolicyInterview,
  type I2PolicyPeerRow,
  type I2PolicyReasonableness,
  I2_POLICY_DEFAULT_CONCLUSION,
  buildReasonablenessNarrative,
  evaluateI2PolicyCompleteness,
} from './i2PolicyCheckModel'

const KEY_ITEMS = 'I2-4-policy-items' // 兼容旧：CAS 段落
const KEY_INTERVIEW = 'I2-4-interview'
const KEY_PROCESS = 'I2-4-process-items'
const KEY_PEER = 'I2-4-peer-rows'
const KEY_REASON = 'I2-4-reasonableness'
const KEY_NOTE = 'I2-4-audit-note'
const KEY_CONCLUSION = 'I2-4-audit-conclusion'

function _readText(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  if (typeof raw === 'object') return String((raw as any).remark ?? (raw as any).conclusion ?? '')
  return ''
}

function _parseJson(raw: unknown): any {
  if (raw == null) return null
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    const remark = (raw as any).remark
    if (typeof remark === 'string' && remark) {
      try { return JSON.parse(remark) } catch { return raw }
    }
    return raw
  }
  if (typeof raw === 'string' && raw) {
    try { return JSON.parse(raw) } catch { return null }
  }
  return null
}

export function useI2PolicyCheck(
  allResponses: Ref<Map<string, any>> | (() => Map<string, any>),
  options?: {
    saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
  },
) {
  const getMap = typeof allResponses === 'function'
    ? allResponses
    : () => allResponses.value

  const interview = ref<I2PolicyInterview>(emptyInterview())
  const processItems = ref<I2PolicyProcessItem[]>(emptyProcessItems())
  const casItems = ref<I2PolicyCasItem[]>(emptyCasItems())
  const peerRows = ref<I2PolicyPeerRow[]>([emptyPeerRow(), emptyPeerRow()])
  const reasonableness = ref<I2PolicyReasonableness>(emptyReasonableness())
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load() {
    const map = getMap()
    interview.value = normalizeInterview(_parseJson(map.get(KEY_INTERVIEW)))
    processItems.value = normalizeProcessItems(_parseJson(map.get(KEY_PROCESS)))
    // CAS：优先新结构；兼容旧 I2-4-policy-items
    const casRaw = _parseJson(map.get(KEY_ITEMS))
    casItems.value = normalizeCasItems(casRaw)
    peerRows.value = normalizePeerRows(_parseJson(map.get(KEY_PEER)))
    reasonableness.value = normalizeReasonableness(_parseJson(map.get(KEY_REASON)))
    auditNote.value = _readText(map.get(KEY_NOTE))
    auditConclusion.value = _readText(map.get(KEY_CONCLUSION))
  }

  watch(() => {
    const m = getMap()
    return [
      m.get(KEY_ITEMS), m.get(KEY_INTERVIEW), m.get(KEY_PROCESS),
      m.get(KEY_PEER), m.get(KEY_REASON), m.get(KEY_NOTE), m.get(KEY_CONCLUSION),
    ]
  }, () => load(), { immediate: true, deep: false })

  const completeness = computed(() =>
    evaluateI2PolicyCompleteness({
      interview: interview.value,
      processItems: processItems.value,
      casItems: casItems.value,
      peerRows: peerRows.value,
      reasonableness: reasonableness.value,
      auditConclusion: auditConclusion.value,
    }),
  )

  const reasonNarrative = computed(() => buildReasonablenessNarrative(reasonableness.value))

  const casCompletedCount = computed(() => casItems.value.filter((i) => !!i.conclusion).length)

  function addPeerRow() {
    peerRows.value.push(emptyPeerRow())
  }

  function removePeerRow(rowId: string) {
    if (peerRows.value.length <= 1) return
    peerRows.value = peerRows.value.filter((r) => r.rowId !== rowId)
  }

  function applyDefaultConclusion() {
    auditConclusion.value = I2_POLICY_DEFAULT_CONCLUSION
  }

  function applyReasonNarrativeToNote() {
    const text = reasonNarrative.value
    if (!auditNote.value.trim()) {
      auditNote.value = text
    } else if (!auditNote.value.includes(text.slice(0, 20))) {
      auditNote.value = `${auditNote.value.trim()}\n\n${text}`
    }
  }

  function applyIndustryTemplate(id: string): { ok: boolean; message: string; count: number } {
    const tpl = I2_INDUSTRY_PEER_TEMPLATES.find((t) => t.id === id)
    if (!tpl) return { ok: false, message: '未找到行业模板', count: 0 }
    peerRows.value = tpl.peers.map((p) => emptyPeerRow({ ...p }))
    return { ok: true, message: `已填入「${tpl.label}」同业模板 ${tpl.peers.length} 家`, count: tpl.peers.length }
  }

  function syncProjectsFromI27(): { ok: boolean; message: string; count: number } {
    const names = listI27ProjectNames(getMap().get('I2-7-rows'))
    if (!names.length) return { ok: false, message: 'I2-7 无项目名称可带入', count: 0 }
    reasonableness.value.inspectedProjects = names.join('、')
    return { ok: true, message: `已带入 ${names.length} 个项目`, count: names.length }
  }

  async function draftAjeFromCasNo(item: I2PolicyCasItem): Promise<{ ok: boolean; message: string }> {
    if (item.conclusion !== '否') return { ok: false, message: '仅结论为「不符合」时可生成调整草稿' }
    await appendI23DraftAje({
      allResponses: getMap(),
      saveResponse: options?.saveResponse,
      draft: {
        description: `I2-4 会计政策不符合：${item.label}`,
        debitAmount: 0,
        indexRef: 'I2-4',
        remark: item.explanationIfNo || '来源:会计政策检查不符合一键生成',
      },
    })
    return { ok: true, message: '已向 I2-3 生成政策调整草稿' }
  }

  async function persistAll() {
    const save = options?.saveResponse
    if (!save) return
    const casPayload = casItems.value.map((i) => ({
      key: i.key,
      actualPolicy: i.actualPolicy,
      evaluation: i.evaluation,
      conclusion: i.conclusion,
      explanationIfNo: i.explanationIfNo,
    }))
    await save('I2-4', {
      [KEY_ITEMS]: JSON.stringify(casPayload),
      [KEY_INTERVIEW]: JSON.stringify(interview.value),
      [KEY_PROCESS]: JSON.stringify(processItems.value.map((i) => ({
        key: i.key, status: i.status, evidence: i.evidence, indexRef: i.indexRef,
      }))),
      [KEY_PEER]: JSON.stringify(peerRows.value),
      [KEY_REASON]: JSON.stringify(reasonableness.value),
      [KEY_NOTE]: auditNote.value,
      [KEY_CONCLUSION]: auditConclusion.value,
    })
    await writeSheetCompletionMarker({
      allResponses: getMap(),
      saveResponse: save,
      sheetCode: 'I2-4',
      progress: completeness.value.progress,
      ok: completeness.value.ok,
      detail: { casCompleted: casCompletedCount.value },
    })
  }

  async function saveAuditNote(val: string) {
    auditNote.value = val
    await options?.saveResponse?.('I2-4', { [KEY_NOTE]: val })
  }

  async function saveAuditConclusion(val: string) {
    auditConclusion.value = val
    await options?.saveResponse?.('I2-4', { [KEY_CONCLUSION]: val })
  }

  return {
    interview,
    processItems,
    casItems,
    peerRows,
    reasonableness,
    auditNote,
    auditConclusion,
    completeness,
    reasonNarrative,
    casCompletedCount,
    addPeerRow,
    removePeerRow,
    applyDefaultConclusion,
    applyReasonNarrativeToNote,
    applyIndustryTemplate,
    syncProjectsFromI27,
    draftAjeFromCasNo,
    persistAll,
    saveAuditNote,
    saveAuditConclusion,
    load,
  }
}
