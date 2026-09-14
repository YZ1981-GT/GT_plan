/**
 * useI4Disclosure — I4 长期待摊费用附注披露 composable
 *
 * 对齐源表：单表账面余额滚动（期初+增加−摊销−其他减少=期末），无累计摊销备抵。
 * - 从 I4-2 按类别聚合自动取数
 * - 订阅 substantive:adjudicated 刷新
 * - sync-from-workpaper → 附注模块（上市五、29 / 国企八、30）
 * - EventBus disclosure:note-text-updated
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import {
  I4_DISC_KEYS,
  aggregateI4DetailForDisclosure,
  calcI4CurrentPortion,
  calcI4DisclosureEnd,
  defaultI4DisclosureRows,
  emptyI4DisclosureRow,
  mergeAutoFillPreserveManual,
  normalizeI4DisclosureRow,
  summarizeI4Disclosure,
  type I4DisclosureRow,
} from './i4DisclosureModel'
import {
  resolveI4NoteSectionTarget,
  type I4DisclosureVariant,
} from './i4NoteSectionMap'
import {
  buildI4ListedFootnote,
  buildI4ListedSyncPayloads,
  buildI4SoeSyncPayloads,
} from './i4DisclosureSyncPayload'

export type { I4DisclosureVariant, I4DisclosureRow }

function safeParseRows(jsonStr: string | null | undefined): any[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function useI4Disclosure(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, any>>,
  options: {
    variant: Ref<I4DisclosureVariant> | I4DisclosureVariant
    onSave?: (itemId: string, value: any) => void
    applicableStandards?: Ref<readonly string[] | null | undefined> | (() => readonly string[] | null | undefined)
  },
) {
  const variant = computed<I4DisclosureVariant>(() =>
    typeof options.variant === 'string' ? options.variant : options.variant.value,
  )
  const isListed = computed(() => variant.value === 'listed')
  const noteTarget = computed(() => resolveI4NoteSectionTarget(variant.value))
  const isSyncing = ref(false)
  const isAiGenerating = ref(false)

  const rows = ref<I4DisclosureRow[]>(defaultI4DisclosureRows())
  const currentPortion = ref(0)
  const otherNote = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  const totals = computed(() => summarizeI4Disclosure(rows.value))
  const footnote = computed(() =>
    isListed.value ? buildI4ListedFootnote(currentPortion.value) : '',
  )

  const reconcileDiff = computed(() => {
    const detail = _readDetailRows()
    if (!detail.length) return null
    const auto = aggregateI4DetailForDisclosure(detail)
    const autoTotal = summarizeI4Disclosure(auto).endBalance
    return Math.round((totals.value.endBalance - autoTotal) * 100) / 100
  })

  /** 附注期末 vs I4-1 审定合计 */
  const reconcileVsAdj = computed(() => {
    const adjItem = allResponses.value.get('I4-adj-rows') || allResponses.value.get('I4-1-rows')
    const adjRows = safeParseRows(adjItem?.remark)
    if (!adjRows.length) return null
    const adjTotal = adjRows.reduce((s: number, r: any) => s + Number(r.audited ?? r.审定 ?? 0), 0)
    if (!(Math.abs(adjTotal) > 0.005) && !(Math.abs(totals.value.endBalance) > 0.005)) return null
    return Math.round((totals.value.endBalance - adjTotal) * 100) / 100
  })

  function _standards(): readonly string[] | null | undefined {
    const s = options.applicableStandards
    if (!s) return undefined
    return typeof s === 'function' ? s() : s.value
  }

  function _keys() {
    return isListed.value
      ? {
          rows: I4_DISC_KEYS.listedRows,
          portion: I4_DISC_KEYS.listedCurrentPortion,
          note: I4_DISC_KEYS.listedNote,
          auditNote: I4_DISC_KEYS.listedAuditNote,
          auditConclusion: I4_DISC_KEYS.listedAuditConclusion,
        }
      : {
          rows: I4_DISC_KEYS.soeRows,
          portion: '',
          note: I4_DISC_KEYS.soeNote,
          auditNote: I4_DISC_KEYS.soeAuditNote,
          auditConclusion: I4_DISC_KEYS.soeAuditConclusion,
        }
  }

  function _readDetailRows(): any[] {
    const item = allResponses.value.get('I4-2-rows')
    return safeParseRows(item?.remark)
  }

  function _load(): void {
    const keys = _keys()
    const raw = allResponses.value.get(keys.rows)
    const parsed = safeParseRows(raw?.remark).map(normalizeI4DisclosureRow)
    rows.value = parsed.length ? parsed : defaultI4DisclosureRows()

    if (keys.portion) {
      const p = allResponses.value.get(keys.portion)
      currentPortion.value = Number(p?.remark) || 0
    }
    otherNote.value = String(allResponses.value.get(keys.note)?.remark ?? '')
    auditNote.value = String(allResponses.value.get(keys.auditNote)?.remark ?? '')
    auditConclusion.value = String(allResponses.value.get(keys.auditConclusion)?.remark ?? '')
  }

  function _persistRows(): void {
    const keys = _keys()
    options.onSave?.(keys.rows, JSON.stringify(rows.value))
  }

  function _persistField(key: string, val: string | number): void {
    if (!key) return
    options.onSave?.(key, String(val))
  }

  /** 从 I4-2 同步类别滚动数 */
  function syncFromDetail(force = false): void {
    const detail = _readDetailRows()
    if (!detail.length) {
      ElMessage.warning('I4-2 明细表暂无数据，请先编制明细')
      return
    }
    const autoRows = aggregateI4DetailForDisclosure(detail)
    rows.value = force
      ? autoRows
      : mergeAutoFillPreserveManual(rows.value, autoRows)
    currentPortion.value = calcI4CurrentPortion(detail)
    _persistRows()
    const keys = _keys()
    if (keys.portion) _persistField(keys.portion, currentPortion.value)
    ElMessage.success(`已从 I4-2 同步 ${rows.value.length} 个披露项目`)
  }

  function addRow(itemName?: string): void {
    rows.value.push(emptyI4DisclosureRow({ item: itemName || '' }))
    _persistRows()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    if (!rows.value.length) rows.value = defaultI4DisclosureRows()
    _persistRows()
  }

  function updateCell(rowId: string, field: keyof I4DisclosureRow, value: unknown): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    row.isAutoFilled = false
    if (['beginBalance', 'increase', 'amortization', 'otherDecrease'].includes(field)) {
      row.endBalance = calcI4DisclosureEnd(row)
    }
    _persistRows()
  }

  function saveOtherNote(val: string): void {
    otherNote.value = val
    _persistField(_keys().note, val)
  }

  function saveAuditNote(val: string): void {
    auditNote.value = val
    _persistField(_keys().auditNote, val)
  }

  function saveAuditConclusion(val: string): void {
    auditConclusion.value = val
    _persistField(_keys().auditConclusion, val)
  }

  function saveCurrentPortion(val: number): void {
    currentPortion.value = val
    const keys = _keys()
    if (keys.portion) _persistField(keys.portion, val)
  }

  /** 同步到附注模块 */
  async function syncToNotes(): Promise<void> {
    if (isSyncing.value || !projectId.value || !wpId.value) return
    const diff = reconcileDiff.value
    if (diff != null && Math.abs(diff) > 0.01) {
      try {
        await ElMessageBox.confirm(
          `披露期末合计与 I4-2 明细差额 ${diff.toLocaleString('zh-CN')}，是否仍同步到附注？`,
          '同步确认',
          { type: 'warning', confirmButtonText: '仍要同步', cancelButtonText: '取消' },
        )
      } catch {
        return
      }
    }

    const state = {
      rows: rows.value,
      currentPortion: currentPortion.value,
      otherNote: otherNote.value,
      footnote: footnote.value,
    }
    const payloads = isListed.value
      ? buildI4ListedSyncPayloads(wpId.value, _standards(), state)
      : buildI4SoeSyncPayloads(wpId.value, _standards(), state)

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
        wpCode: 'I4',
      })
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: {
          wpCode: 'I4',
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

  async function generateNoteText(): Promise<string | null> {
    if (!wpId.value) return null
    isAiGenerating.value = true
    try {
      const t = totals.value
      const res = await api.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section: `i4-disclosure-${variant.value}`,
        prompt: '请为长期待摊费用附注生成简要披露说明（含主要构成、摊销方法）',
        context: [
          `科目1801长期待摊费用`,
          `版本:${isListed.value ? '上市公司' : '国有企业'}`,
          `期初:${t.beginBalance}`,
          `增加:${t.increase}`,
          `摊销:${t.amortization}`,
          `其他减少:${t.otherDecrease}`,
          `期末:${t.endBalance}`,
          isListed.value ? `一年内到期信息性金额:${currentPortion.value}` : '',
          `项目:${rows.value.map((r) => r.item).filter(Boolean).join('、')}`,
        ].filter(Boolean).join('; '),
        existingContent: otherNote.value || '',
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

  function _onSubstantiveAdjudicated(event: Event): void {
    const detail = (event as CustomEvent).detail
    if (detail?.wpCode === 'I4' || detail?.accountCode === '1801') {
      const detailRows = _readDetailRows()
      if (!detailRows.length) return
      const autoRows = aggregateI4DetailForDisclosure(detailRows)
      rows.value = mergeAutoFillPreserveManual(rows.value, autoRows)
      currentPortion.value = calcI4CurrentPortion(detailRows)
      _persistRows()
      const keys = _keys()
      if (keys.portion) _persistField(keys.portion, currentPortion.value)
    }
  }

  watch(allResponses, () => _load(), { immediate: true })
  watch(variant, () => _load())

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
  })
  onUnmounted(() => {
    window.removeEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
  })

  return {
    variant,
    isListed,
    noteTarget,
    isSyncing,
    isAiGenerating,
    rows,
    totals,
    currentPortion,
    footnote,
    otherNote,
    auditNote,
    auditConclusion,
    reconcileDiff,
    reconcileVsAdj,
    syncFromDetail,
    addRow,
    removeRow,
    updateCell,
    saveOtherNote,
    saveAuditNote,
    saveAuditConclusion,
    saveCurrentPortion,
    syncToNotes,
    generateNoteText,
  }
}

export default useI4Disclosure
