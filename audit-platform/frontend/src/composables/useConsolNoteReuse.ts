/**
 * useConsolNoteReuse — 合并附注映射规则复用、值变化通知、确认、结构锁 composable
 *
 * spec: consol-note-mapping-reuse-and-reference-push
 *
 * 提供：
 * - stale 汇总查询 + SSE 事件驱动的 stale 状态
 * - 值确认 CRUD + 签发闸门
 * - 结构锁查询 + 锁定/解锁
 * - 科目参考查询
 */
import { ref, computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { consolNoteReuse as P } from '@/services/apiPaths'

// ═══════════════════════════════════════════════════════════════════════════════
// 类型
// ═══════════════════════════════════════════════════════════════════════════════

export interface StaleEntity {
  node_key: string | null
  is_stale: boolean
  updated_at: string | null
}

export interface StaleSummary {
  project_id: string
  sections: Record<string, StaleEntity[]>
  total_stale: number
}

export interface ConfirmationItem {
  id: string
  section_id: string
  entity_node_key: string
  confirmed_value_hash: string
  confirmed_by: string | null
  confirmed_at: string | null
  status: 'confirmed' | 'outdated'
}

export interface ReadinessResult {
  passed: boolean
  blocking_items: Array<{ section_id: string; entity_node_key: string; reason: string }>
  confirmed_count: number
  total_count: number
  message: string
}

export interface StructureLockInfo {
  locked: boolean
  lock_id: string
  consol_project_id: string
  section_id: string
  lock_scope: string
  locked_by: string | null
  locked_at: string | null
}

export interface AccountReferenceRow {
  target_row_id: string
  canonical_name: string
  recommended_account_codes: string[]
}

// ═══════════════════════════════════════════════════════════════════════════════
// Composable
// ═══════════════════════════════════════════════════════════════════════════════

export function useConsolNoteReuse(projectId: Ref<string>) {
  // ─── stale 状态 ──────────────────────────────────────────────────────────
  const staleSummary = ref<StaleSummary | null>(null)
  const staleLoading = ref(false)
  const hasStale = computed(() => (staleSummary.value?.total_stale ?? 0) > 0)
  const staleEntities = computed<string[]>(() => {
    if (!staleSummary.value) return []
    const names: string[] = []
    for (const entities of Object.values(staleSummary.value.sections)) {
      for (const e of entities) {
        if (e.node_key) names.push(e.node_key)
      }
    }
    return [...new Set(names)]
  })

  async function loadStaleSummary(sectionId?: string) {
    if (!projectId.value) return
    staleLoading.value = true
    try {
      const params = sectionId ? { section_id: sectionId } : {}
      staleSummary.value = await api.get(P.staleSummary(projectId.value), { params })
    } catch {
      staleSummary.value = null
    } finally {
      staleLoading.value = false
    }
  }

  /** SSE 事件回调：外部收到 CONSOL_NOTE_VALUE_CHANGED 时调用，刷新 stale 汇总。 */
  function onValueChanged() {
    loadStaleSummary()
  }

  /** 用户点击刷新后清除 stale（由调用方在 fill_by_formula 成功后调用）。 */
  function clearStale() {
    staleSummary.value = null
  }

  // ─── 映射变更通知（P2：集团确认映射 / 提升模板 → SSE → 横幅） ──────────
  const mappingChanged = ref(false)

  /** SSE 事件回调：consol.note_mapping_confirmed / template_promoted → 前端刷新提示 */
  function onMappingChanged() {
    mappingChanged.value = true
    // 同时刷新 stale 和结构锁（映射确认可能伴随锁定）
    loadStaleSummary()
    loadLocks()
  }

  function clearMappingChanged() {
    mappingChanged.value = false
  }

  // ─── 值确认 ──────────────────────────────────────────────────────────────
  const confirmations = ref<ConfirmationItem[]>([])
  const confirmLoading = ref(false)

  async function loadConfirmations(sectionId?: string) {
    if (!projectId.value) return
    confirmLoading.value = true
    try {
      const params = sectionId ? { section_id: sectionId } : {}
      confirmations.value = await api.get(P.confirmationStatus(projectId.value), { params })
    } catch {
      confirmations.value = []
    } finally {
      confirmLoading.value = false
    }
  }

  async function confirmValue(sectionId: string, entityNodeKey: string, valueHash: string) {
    if (!projectId.value) return
    await api.post(P.confirm(projectId.value), {
      section_id: sectionId,
      entity_node_key: entityNodeKey,
      value_hash: valueHash,
    })
    await loadConfirmations(sectionId)
  }

  async function checkReadiness(): Promise<ReadinessResult | null> {
    if (!projectId.value) return null
    try {
      return await api.get(P.readinessCheck(projectId.value))
    } catch {
      return null
    }
  }

  function confirmationStatus(sectionId: string, entityNodeKey: string): 'confirmed' | 'outdated' | 'unconfirmed' {
    const item = confirmations.value.find(
      c => c.section_id === sectionId && c.entity_node_key === entityNodeKey,
    )
    if (!item) return 'unconfirmed'
    return item.status
  }

  // ─── 结构锁 ──────────────────────────────────────────────────────────────
  const structureLocks = ref<Array<{ lock_id: string; section_id: string; lock_scope: string; entity_count: number }>>([])
  const lockLoading = ref(false)

  async function loadLocks() {
    if (!projectId.value) return
    lockLoading.value = true
    try {
      structureLocks.value = await api.get(P.structureLock(projectId.value))
    } catch {
      structureLocks.value = []
    } finally {
      lockLoading.value = false
    }
  }

  function isSectionLocked(sectionId: string): boolean {
    return structureLocks.value.some(l => l.section_id === sectionId)
  }

  async function activateLock(sectionId: string, lockedVersionId: string) {
    if (!projectId.value) return
    await api.post(P.structureLock(projectId.value), {
      section_id: sectionId,
      locked_version_id: lockedVersionId,
    })
    await loadLocks()
  }

  async function releaseLock(sectionId: string) {
    if (!projectId.value) return
    await api.delete(P.structureLockRelease(projectId.value, sectionId))
    await loadLocks()
  }

  // ─── 科目参考 ────────────────────────────────────────────────────────────
  const accountReference = ref<AccountReferenceRow[]>([])
  const accountRefLoading = ref(false)

  async function loadAccountReference(sectionId: string) {
    if (!projectId.value || !sectionId) {
      accountReference.value = []
      return
    }
    accountRefLoading.value = true
    try {
      const res: any = await api.get(P.accountReference(projectId.value, sectionId))
      accountReference.value = res?.rows ?? []
    } catch {
      accountReference.value = []
    } finally {
      accountRefLoading.value = false
    }
  }

  return {
    // stale
    staleSummary,
    staleLoading,
    hasStale,
    staleEntities,
    loadStaleSummary,
    onValueChanged,
    clearStale,
    // 映射变更
    mappingChanged,
    onMappingChanged,
    clearMappingChanged,
    // 确认
    confirmations,
    confirmLoading,
    loadConfirmations,
    confirmValue,
    checkReadiness,
    confirmationStatus,
    // 结构锁
    structureLocks,
    lockLoading,
    loadLocks,
    isSectionLocked,
    activateLock,
    releaseLock,
    // 科目参考
    accountReference,
    accountRefLoading,
    loadAccountReference,
  }
}
