/**
 * useA1721Kam — A17-2-1 关键审计事项(KAM) 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a17-2-1-kam/
 * Task: 2.1
 *
 * 职责：
 * - reactive state: candidates + kams(dynamic) + notes + applicability
 * - KAM add/remove, candidate add/remove
 * - 2s debounce save (item_id: `a1721-*`)
 * - flush pending saves
 * - EventBus KAM_UPDATED emit
 */
import { ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CandidateRow {
  description: string
  risk_level: string
  communicate: 'Y' | 'N'
  reason: string
}

export interface KamItem {
  index: number
  basic: string
  policy: string
  reason: string
  response: string
  result: string
  ref_index: string
}

export interface NoteItem {
  kam_index: number
  content: string
}

export interface A1721Applicability {
  noKam: boolean
  reason: string | null
}

export interface A1721RenderData {
  candidates?: CandidateRow[]
  kams?: KamItem[]
  notes?: NoteItem[]
  applicability?: { no_kam?: boolean; reason?: string | null }
  project_context?: { client_name?: string; period?: string }
}

export interface UseA1721Options {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData: Ref<A1721RenderData | null>
}

export interface UseA1721Return {
  candidates: Ref<CandidateRow[]>
  kams: Ref<KamItem[]>
  notes: Ref<NoteItem[]>
  applicability: Ref<A1721Applicability>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  addCandidate(): void
  removeCandidate(index: number): void
  addKam(): void
  removeKam(index: number): void
  updateKamField(kamIndex: number, fieldId: string, value: string): void
  updateCandidate(index: number, field: string, value: string): void
  updateNote(kamIndex: number, content: string): void
  toggleApplicability(noKam: boolean): void
  setApplicabilityReason(reason: string): void
  flushPendingSaves(): Promise<void>
}

// ─── item_id builders ────────────────────────────────────────────────────────

export function buildCandidatesItemId(): string {
  return 'a1721-candidates'
}

export function buildKamItemId(kamIndex: number): string {
  return `a1721-kam${kamIndex}`
}

export function buildNoteItemId(kamIndex: number): string {
  return `a1721-notes-${kamIndex}`
}

export function buildApplicabilityItemId(): string {
  return 'a1721-applicability'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA1721Kam(opts: UseA1721Options): UseA1721Return {
  const { wpId, htmlData } = opts

  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const candidates = ref<CandidateRow[]>([])
  const kams = ref<KamItem[]>([])
  const notes = ref<NoteItem[]>([])
  const applicability = ref<A1721Applicability>({ noKam: false, reason: null })

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Hydrate from render data ───
  function hydrateFromRenderData(data: A1721RenderData | null) {
    if (!data) return

    if (Array.isArray(data.candidates)) {
      candidates.value = data.candidates.map(c => ({
        description: c.description ?? '',
        risk_level: c.risk_level ?? '',
        communicate: c.communicate === 'Y' ? 'Y' : 'N',
        reason: c.reason ?? '',
      }))
    }

    if (Array.isArray(data.kams)) {
      kams.value = data.kams.map((k, i) => ({
        index: k.index ?? i,
        basic: k.basic ?? '',
        policy: k.policy ?? '',
        reason: k.reason ?? '',
        response: k.response ?? '',
        result: k.result ?? '',
        ref_index: k.ref_index ?? '',
      }))
    }

    if (Array.isArray(data.notes)) {
      notes.value = data.notes.map(n => ({
        kam_index: n.kam_index ?? 0,
        content: n.content ?? '',
      }))
    }

    if (data.applicability) {
      applicability.value = {
        noKam: !!data.applicability.no_kam,
        reason: data.applicability.reason ?? null,
      }
    }

    // Sync notes length with kams
    syncNotes()
  }

  watch(htmlData, (newData) => {
    hydrateFromRenderData(newData)
  }, { immediate: true })

  // ─── Notes sync ───
  function syncNotes() {
    while (notes.value.length < kams.value.length) {
      notes.value.push({ kam_index: notes.value.length, content: '' })
    }
    if (notes.value.length > kams.value.length) {
      notes.value.splice(kams.value.length)
    }
  }

  // ─── Candidate operations ───
  function addCandidate(): void {
    candidates.value.push({ description: '', risk_level: '', communicate: 'N', reason: '' })
    scheduleCandidatesSave()
  }

  function removeCandidate(index: number): void {
    if (index < 0 || index >= candidates.value.length) return
    candidates.value.splice(index, 1)
    scheduleCandidatesSave()
  }

  function updateCandidate(index: number, field: string, value: string): void {
    if (index < 0 || index >= candidates.value.length) return
    const row = candidates.value[index] as any
    if (field in row) {
      row[field] = value
    }
    scheduleCandidatesSave()
  }

  function scheduleCandidatesSave() {
    const itemId = buildCandidatesItemId()
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: String(candidates.value.length),
      remark: JSON.stringify(candidates.value),
    })
    scheduleSave()
  }

  // ─── KAM operations ───
  function addKam(): void {
    const newIndex = kams.value.length
    kams.value.push({
      index: newIndex,
      basic: '',
      policy: '',
      reason: '',
      response: '',
      result: '',
      ref_index: '',
    })
    syncNotes()
    scheduleKamSave(newIndex)
    emitKamUpdated()
  }

  function removeKam(index: number): void {
    if (index < 0 || index >= kams.value.length) return
    kams.value.splice(index, 1)
    // Re-index remaining KAMs
    kams.value.forEach((k, i) => { k.index = i })
    syncNotes()
    // Clear old item_ids and schedule all KAM saves
    scheduleAllKamsSave()
    emitKamUpdated()
  }

  function updateKamField(kamIndex: number, fieldId: string, value: string): void {
    if (kamIndex < 0 || kamIndex >= kams.value.length) return
    const kam = kams.value[kamIndex] as any
    if (fieldId in kam) {
      kam[fieldId] = value
    }
    scheduleKamSave(kamIndex)
  }

  function scheduleKamSave(kamIndex: number) {
    const kam = kams.value[kamIndex]
    if (!kam) return
    const itemId = buildKamItemId(kamIndex)
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: null,
      remark: JSON.stringify({
        basic: kam.basic,
        policy: kam.policy,
        reason: kam.reason,
        response: kam.response,
        result: kam.result,
        ref_index: kam.ref_index,
      }),
    })
    scheduleSave()
  }

  function scheduleAllKamsSave() {
    // Remove all old kam item_ids from pending
    for (const key of pendingItems.keys()) {
      if (key.startsWith('a1721-kam')) pendingItems.delete(key)
    }
    // Schedule save for each current KAM
    for (let i = 0; i < kams.value.length; i++) {
      scheduleKamSave(i)
    }
    // Also schedule notes
    for (let i = 0; i < notes.value.length; i++) {
      scheduleNoteSave(i)
    }
    scheduleSave()
  }

  // ─── Notes operations ───
  function updateNote(kamIndex: number, content: string): void {
    if (kamIndex < 0 || kamIndex >= notes.value.length) return
    notes.value[kamIndex].content = content
    scheduleNoteSave(kamIndex)
  }

  function scheduleNoteSave(kamIndex: number) {
    const note = notes.value[kamIndex]
    if (!note) return
    const itemId = buildNoteItemId(kamIndex)
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: null,
      remark: note.content,
    })
    scheduleSave()
  }

  // ─── Applicability operations ───
  function toggleApplicability(noKam: boolean): void {
    applicability.value.noKam = noKam
    if (!noKam) {
      applicability.value.reason = null
    }
    scheduleApplicabilitySave()
  }

  function setApplicabilityReason(reason: string): void {
    applicability.value.reason = reason
    scheduleApplicabilitySave()
  }

  function scheduleApplicabilitySave() {
    const itemId = buildApplicabilityItemId()
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: applicability.value.noKam ? 'Y' : 'N',
      remark: applicability.value.reason,
    })
    scheduleSave()
  }

  // ─── EventBus emit ───
  function emitKamUpdated() {
    eventBus.emit('kam:updated', {
      count: kams.value.length,
      summaries: kams.value.map(k => ({ index: k.index, basic: k.basic })),
    })
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
    candidates,
    kams,
    notes,
    applicability,
    saveStatus,
    addCandidate,
    removeCandidate,
    addKam,
    removeKam,
    updateKamField,
    updateCandidate,
    updateNote,
    toggleApplicability,
    setApplicabilityReason,
    flushPendingSaves,
  }
}
