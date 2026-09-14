/**
 * useI6Disclosure — I6 研发费用附注披露 composable
 *
 * - 从 I6-2 明细 / I6-1 审定按类别 SUMIF 自动取数
 * - 订阅 substantive:adjudicated 刷新
 * - sync-from-workpaper → 附注模块（上市五、66 / 国企八、67）
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import {
  I6_DISC_KEYS,
  aggregateI6AdjForDisclosure,
  aggregateI6DetailForDisclosure,
  buildI6DisclosureReconcileView,
  defaultI6DisclosureRows,
  mergeAutoFillPreserveManual,
  normalizeI6DisclosureRow,
  summarizeI6Disclosure,
  type I6DisclosureRow,
  type I6DisclosureReconcileView,
} from './i6DisclosureModel'
import {
  resolveI6NoteSectionTarget,
  type I6DisclosureVariant,
} from './i6NoteSectionMap'
import {
  buildI6ListedSyncPayloads,
  buildI6SoeSyncPayloads,
} from './i6DisclosureSyncPayload'

export type { I6DisclosureVariant, I6DisclosureRow, I6DisclosureReconcileView }

function safeParseRows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const remark = (raw as any).remark ?? (raw as any).conclusion
    if (remark != null) return safeParseRows(remark)
  }
  return []
}

export function useI6Disclosure(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, any>>,
  options: {
    variant: Ref<I6DisclosureVariant> | I6DisclosureVariant
    onSave?: (itemId: string, value: any) => void
    applicableStandards?: Ref<readonly string[] | null | undefined> | (() => readonly string[] | null | undefined)
  },
) {
  const variant = computed<I6DisclosureVariant>(() =>
    typeof options.variant === 'string' ? options.variant : options.variant.value,
  )
  const isListed = computed(() => variant.value === 'listed')
  const noteTarget = computed(() => resolveI6NoteSectionTarget(variant.value))
  const isSyncing = ref(false)
  const isAiGenerating = ref(false)

  const rows = ref<I6DisclosureRow[]>(defaultI6DisclosureRows())
  const capitalizationNote = ref('')
  const projectsNote = ref('')
  const supplementNote = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  const totals = computed(() => summarizeI6Disclosure(rows.value.filter((r) => r.item !== '合计')))

  const reconcileVsDetail = computed(() => {
    const detail = _readDetailRows()
    if (!detail.length) return null
    const auto = aggregateI6DetailForDisclosure(detail)
    const autoTotal = summarizeI6Disclosure(auto).currentAmount
    return Math.round((totals.value.currentAmount - autoTotal) * 100) / 100
  })

  const reconcileVsAdj = computed(() => {
    const summary = reconcileSummary.value
    if (!summary.vsAdj.hasBoth && Math.abs(summary.vsAdj.adjudicatedTotal) < 0.005) return null
    return summary.vsAdj.diff
  })

  const reconcileSummary = computed<I6DisclosureReconcileView>(() =>
    buildI6DisclosureReconcileView(rows.value, _readDetailRows(), _readAdjRows()),
  )

  function _standards(): readonly string[] | null | undefined {
    const s = options.applicableStandards
    if (!s) return undefined
    return typeof s === 'function' ? s() : s.value
  }

  function _keys() {
    return isListed.value
      ? {
          rows: I6_DISC_KEYS.listedRows,
          legacyRows: I6_DISC_KEYS.legacyListedRows,
          capitalization: I6_DISC_KEYS.listedCapitalization,
          projects: I6_DISC_KEYS.listedProjects,
          auditNote: I6_DISC_KEYS.listedAuditNote,
          auditConclusion: I6_DISC_KEYS.listedAuditConclusion,
        }
      : {
          rows: I6_DISC_KEYS.soeRows,
          legacyRows: I6_DISC_KEYS.legacySoeRows,
          supplement: I6_DISC_KEYS.soeSupplement,
          auditNote: I6_DISC_KEYS.soeAuditNote,
          auditConclusion: I6_DISC_KEYS.soeAuditConclusion,
        }
  }

  function _readDetailRows(): any[] {
    return safeParseRows(allResponses.value.get('I6-2-detail-rows')?.remark)
  }

  function _readAdjRows(): any[] {
    const from1 = safeParseRows(allResponses.value.get('I6-1-rows')?.remark)
    if (from1.length) return from1
    return safeParseRows(allResponses.value.get('I6-adj-rows')?.remark)
  }

  function _load(): void {
    const keys = _keys()
    const raw = allResponses.value.get(keys.rows) || allResponses.value.get(keys.legacyRows)
    const parsed = safeParseRows(raw?.remark).map(normalizeI6DisclosureRow)
    rows.value = parsed.length ? parsed : defaultI6DisclosureRows()

    if (isListed.value) {
      capitalizationNote.value = String(allResponses.value.get(keys.capitalization!)?.remark ?? '')
      projectsNote.value = String(allResponses.value.get(keys.projects!)?.remark ?? '')
    } else {
      supplementNote.value = String(allResponses.value.get(keys.supplement!)?.remark ?? '')
    }
    auditNote.value = String(allResponses.value.get(keys.auditNote)?.remark ?? '')
    auditConclusion.value = String(allResponses.value.get(keys.auditConclusion)?.remark ?? '')
  }

  function _persistRows(): void {
    options.onSave?.(_keys().rows, JSON.stringify(rows.value))
  }

  function _persistField(key: string, val: string | number): void {
    if (!key) return
    options.onSave?.(key, String(val))
  }

  /** 从 I6-2 明细 SUMIF 同步 */
  function syncFromDetail(force = false): void {
    const detail = _readDetailRows()
    if (!detail.length) {
      ElMessage.warning('I6-2 明细表暂无数据，请先编制明细')
      return
    }
    const autoRows = aggregateI6DetailForDisclosure(detail)
    rows.value = force ? autoRows : mergeAutoFillPreserveManual(rows.value, autoRows)
    _persistRows()
    ElMessage.success(`已从 I6-2 同步 ${rows.value.length} 个披露项目`)
  }

  /** 从 I6-1 审定表同步（本期/上期审定） */
  function syncFromAdjudication(force = false): void {
    const adjRows = _readAdjRows()
    if (!adjRows.length) {
      ElMessage.warning('I6-1 审定表暂无数据')
      return
    }
    const autoRows = aggregateI6AdjForDisclosure(adjRows)
    rows.value = force ? autoRows : mergeAutoFillPreserveManual(rows.value, autoRows)
    _persistRows()
    ElMessage.success(`已从 I6-1 同步 ${rows.value.length} 个披露项目`)
  }

  /** 优先 I6-2 SUMIF，无明细时回退 I6-1 */
  function syncAllFromWorkpaper(force = false): void {
    const detail = _readDetailRows()
    if (detail.length) {
      syncFromDetail(force)
      return
    }
    syncFromAdjudication(force)
  }

  /** 静默刷新：保留手工行，仅更新 isAutoFilled 项 */
  function _autoRefreshFromWorkpaper(): void {
    const detail = _readDetailRows()
    if (detail.length) {
      rows.value = mergeAutoFillPreserveManual(
        rows.value,
        aggregateI6DetailForDisclosure(detail),
      )
      _persistRows()
      return
    }
    const adjRows = _readAdjRows()
    if (!adjRows.length) return
    rows.value = mergeAutoFillPreserveManual(
      rows.value,
      aggregateI6AdjForDisclosure(adjRows),
    )
    _persistRows()
  }

  function addRow(itemName?: string): void {
    rows.value.push({
      rowId: `i6d-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      item: itemName || '',
      currentAmount: 0,
      priorAmount: 0,
      isAutoFilled: false,
      remark: '',
    })
    _persistRows()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    if (!rows.value.length) rows.value = defaultI6DisclosureRows()
    _persistRows()
  }

  function updateCell(rowId: string, field: keyof I6DisclosureRow, value: unknown): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    row.isAutoFilled = false
    _persistRows()
  }

  function saveCapitalizationNote(val: string): void {
    capitalizationNote.value = val
    _persistField(_keys().capitalization!, val)
    _publishNoteEvent('capitalization')
  }

  function saveProjectsNote(val: string): void {
    projectsNote.value = val
    _persistField(_keys().projects!, val)
    _publishNoteEvent('projects')
  }

  function saveSupplementNote(val: string): void {
    supplementNote.value = val
    _persistField(_keys().supplement!, val)
    _publishNoteEvent('supplement')
  }

  function saveAuditNote(val: string): void {
    auditNote.value = val
    _persistField(_keys().auditNote, val)
  }

  function saveAuditConclusion(val: string): void {
    auditConclusion.value = val
    _persistField(_keys().auditConclusion, val)
  }

  async function syncToNotes(): Promise<void> {
    if (isSyncing.value || !projectId.value || !wpId.value) return

    const summary = reconcileSummary.value
    if (!summary.vsAdj.matched && summary.vsAdj.hasBoth) {
      try {
        await ElMessageBox.confirm(
          `${summary.headline}。是否仍同步到附注？`,
          '勾稽差异确认',
          { type: 'warning', confirmButtonText: '仍要同步', cancelButtonText: '取消' },
        )
      } catch { return }
    } else if (summary.itemDiffs.length) {
      try {
        await ElMessageBox.confirm(
          `${summary.headline}。是否仍同步到附注？`,
          '分项差异确认',
          { type: 'info', confirmButtonText: '仍要同步', cancelButtonText: '取消' },
        )
      } catch { return }
    }

    const snap = {
      rows: rows.value,
      capitalizationNote: capitalizationNote.value,
      projectsNote: projectsNote.value,
      supplementNote: supplementNote.value,
    }
    const payloads = isListed.value
      ? buildI6ListedSyncPayloads(wpId.value, _standards(), snap)
      : buildI6SoeSyncPayloads(wpId.value, _standards(), snap)

    if (!payloads.length) {
      ElMessage.warning('当前报告准则不适用本披露版本同步')
      return
    }

    isSyncing.value = true
    try {
      let synced = 0
      for (const payload of payloads) {
        const result: any = await api.post(
          `/api/projects/${projectId.value}/disclosure-notes/sync-from-workpaper`,
          payload,
        )
        const data = result?.data ?? result
        synced += Number(data?.rows_synced ?? 0)
      }
      eventBus.emit('disclosure:note-text-updated' as any, {
        projectId: projectId.value,
        sectionIds: [noteTarget.value.sectionId],
        wpId: wpId.value,
        sheet: isListed.value ? '附注披露（上市公司）' : '附注披露（国有企业）',
        wpCode: 'I6',
      })
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: {
          wpCode: 'I6',
          variant: variant.value,
          sectionId: noteTarget.value.sectionId,
        },
      }))
      ElMessage.success(`已同步至附注 ${noteTarget.value.sectionId}（${synced} 行）`)
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.message || e?.message || '同步失败')
    } finally {
      isSyncing.value = false
    }
  }

  async function generateNoteText(section: 'capitalization' | 'projects' | 'supplement'): Promise<string | null> {
    if (!wpId.value) return null
    isAiGenerating.value = true
    try {
      const t = totals.value
      const res = await api.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section: `i6-disclosure-${variant.value}-${section}`,
        prompt: `请为研发费用附注「${section}」生成披露文字描述`,
        context: [
          '科目6602研发费用，损益类借方，取发生额非余额',
          `版本:${isListed.value ? '上市公司' : '国有企业'}`,
          `本期合计:${t.currentAmount}`,
          `上期合计:${t.priorAmount}`,
          `项目:${rows.value.map((r) => r.item).filter(Boolean).join('、')}`,
        ].join('; '),
        existingContent: section === 'capitalization' ? capitalizationNote.value
          : section === 'projects' ? projectsNote.value : supplementNote.value,
      })
      const data = res?.data ?? res
      return data?.content ?? data?.text ?? null
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.message || err?.message || 'AI生成失败')
      return null
    } finally {
      isAiGenerating.value = false
    }
  }

  let publishTimer: ReturnType<typeof setTimeout> | null = null
  function _publishNoteEvent(section: string): void {
    if (publishTimer) clearTimeout(publishTimer)
    publishTimer = setTimeout(() => {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { wpCode: 'I6', variant: variant.value, sections: [section] },
      }))
    }, 300)
  }

  function _onSubstantiveAdjudicated(event: Event): void {
    const detail = (event as CustomEvent).detail
    if (detail?.wpCode === 'I6' || detail?.accountCodes?.includes?.('6602') || detail?.accountCode === '6602') {
      _autoRefreshFromWorkpaper()
    }
  }

  function _onAdjustmentWriteback(): void {
    _autoRefreshFromWorkpaper()
  }

  let autoRefreshTimer: ReturnType<typeof setTimeout> | null = null

  watch(allResponses, () => _load(), { immediate: true })
  watch(variant, () => _load())
  watch(
    () => allResponses.value.get('I6-2-detail-rows')?.remark,
    () => {
      if (autoRefreshTimer) clearTimeout(autoRefreshTimer)
      autoRefreshTimer = setTimeout(() => _autoRefreshFromWorkpaper(), 300)
    },
  )

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
    window.addEventListener('i6:adjustment-writeback', _onAdjustmentWriteback)
  })
  onUnmounted(() => {
    window.removeEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
    window.removeEventListener('i6:adjustment-writeback', _onAdjustmentWriteback)
    if (publishTimer) clearTimeout(publishTimer)
    if (autoRefreshTimer) clearTimeout(autoRefreshTimer)
  })

  return {
    variant,
    isListed,
    noteTarget,
    isSyncing,
    isAiGenerating,
    rows,
    totals,
    capitalizationNote,
    projectsNote,
    supplementNote,
    auditNote,
    auditConclusion,
    reconcileVsDetail,
    reconcileVsAdj,
    reconcileSummary,
    syncFromDetail,
    syncFromAdjudication,
    syncAllFromWorkpaper,
    addRow,
    removeRow,
    updateCell,
    saveCapitalizationNote,
    saveProjectsNote,
    saveSupplementNote,
    saveAuditNote,
    saveAuditConclusion,
    syncToNotes,
    generateNoteText,
  }
}

export default useI6Disclosure
