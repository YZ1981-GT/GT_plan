/**
 * useI5Disclosure — I5 其他非流动资产附注披露 composable
 *
 * 对齐源表：上市账面价值对比表 / 国企期末·年初余额表
 * - 从 I5-2 按分类聚合自动取数
 * - 订阅 substantive:adjudicated 刷新
 * - sync-from-workpaper → 附注模块（上市五、31 / 国企八、32）
 * - EventBus disclosure:note-text-updated
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import {
  I5_DISC_KEYS,
  aggregateI5DetailForDisclosure,
  calcI5EndBookValue,
  calcI5PriorBookValue,
  defaultI5DisclosureRows,
  emptyI5DisclosureRow,
  mergeAutoFillPreserveManual,
  normalizeI5DisclosureRow,
  summarizeI5Disclosure,
  type I5DisclosureRow,
} from './i5DisclosureModel'
import {
  resolveI5NoteSectionTarget,
  type I5DisclosureVariant,
} from './i5NoteSectionMap'
import {
  buildI5ListedSyncPayloads,
  buildI5SoeSyncPayloads,
} from './i5DisclosureSyncPayload'

export type { I5DisclosureVariant, I5DisclosureRow }

/** @deprecated 兼容旧 UI 类型别名 */
export type I5DisclosureMatrixRow = I5DisclosureRow

function safeParseRows(jsonStr: string | null | undefined): any[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function useI5Disclosure(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, any>>,
  options: {
    variant: Ref<I5DisclosureVariant> | I5DisclosureVariant
    onSave?: (itemId: string, value: any) => void
    applicableStandards?: Ref<readonly string[] | null | undefined> | (() => readonly string[] | null | undefined)
  },
) {
  const variant = computed<I5DisclosureVariant>(() =>
    typeof options.variant === 'string' ? options.variant : options.variant.value,
  )
  const isListed = computed(() => variant.value === 'listed')
  const noteTarget = computed(() => resolveI5NoteSectionTarget(variant.value))
  const isSyncing = ref(false)
  const isAiGenerating = ref(false)

  const rows = ref<I5DisclosureRow[]>(defaultI5DisclosureRows())
  const otherNote = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  const totals = computed(() => summarizeI5Disclosure(rows.value))

  const reconcileDiff = computed(() => {
    const detail = _readDetailRows()
    if (!detail.length) return null
    const auto = aggregateI5DetailForDisclosure(detail)
    const autoTotal = summarizeI5Disclosure(auto).endBookValue
    return Math.round((totals.value.endBookValue - autoTotal) * 100) / 100
  })

  /** 附注期末账面价值 vs I5-1 审定合计 */
  const reconcileVsAdj = computed(() => {
    const adjItem = allResponses.value.get('I5-adj-rows') || allResponses.value.get('I5-1-rows')
    const adjRows = safeParseRows(adjItem?.remark)
    if (!adjRows.length) return null
    const adjTotal = adjRows.reduce((s: number, r: any) => s + Number(r.audited ?? r.审定 ?? 0), 0)
    if (!(Math.abs(adjTotal) > 0.005) && !(Math.abs(totals.value.endBookValue) > 0.005)) return null
    return Math.round((totals.value.endBookValue - adjTotal) * 100) / 100
  })

  function _standards(): readonly string[] | null | undefined {
    const s = options.applicableStandards
    if (!s) return undefined
    return typeof s === 'function' ? s() : s.value
  }

  function _keys() {
    return isListed.value
      ? {
          rows: I5_DISC_KEYS.listedRows,
          legacy: I5_DISC_KEYS.listedLegacyMatrix,
          note: I5_DISC_KEYS.listedNote,
          auditNote: I5_DISC_KEYS.listedAuditNote,
          auditConclusion: I5_DISC_KEYS.listedAuditConclusion,
        }
      : {
          rows: I5_DISC_KEYS.soeRows,
          legacy: I5_DISC_KEYS.soeLegacyMatrix,
          note: I5_DISC_KEYS.soeNote,
          auditNote: I5_DISC_KEYS.soeAuditNote,
          auditConclusion: I5_DISC_KEYS.soeAuditConclusion,
        }
  }

  function _readDetailRows(): any[] {
    const item = allResponses.value.get('I5-2-rows')
    return safeParseRows(item?.remark)
  }

  function _load(): void {
    const keys = _keys()
    let parsed = safeParseRows(allResponses.value.get(keys.rows)?.remark).map(normalizeI5DisclosureRow)
    if (!parsed.length) {
      parsed = safeParseRows(allResponses.value.get(keys.legacy)?.remark).map(normalizeI5DisclosureRow)
    }
    rows.value = parsed.length ? parsed : defaultI5DisclosureRows()
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

  /** 从 I5-2 同步分类余额 */
  function syncFromDetail(force = false): void {
    const detail = _readDetailRows()
    if (!detail.length) {
      ElMessage.warning('I5-2 明细表暂无数据，请先编制明细')
      return
    }
    const autoRows = aggregateI5DetailForDisclosure(detail)
    rows.value = force
      ? autoRows
      : mergeAutoFillPreserveManual(rows.value, autoRows)
    _persistRows()
    ElMessage.success(`已从 I5-2 同步 ${rows.value.length} 个披露项目`)
  }

  function addRow(itemName?: string): void {
    rows.value.push(emptyI5DisclosureRow({ item: itemName || '' }))
    _persistRows()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    if (!rows.value.length) rows.value = defaultI5DisclosureRows()
    _persistRows()
  }

  function updateCell(rowId: string, field: keyof I5DisclosureRow, value: unknown): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    row.isAutoFilled = false

    // 国企简化：直接改期末/年初账面价值时同步原值
    if (field === 'endBookValue') {
      row.endGross = _num(value)
      row.endImpairment = 0
    }
    if (field === 'priorBookValue') {
      row.priorGross = _num(value)
      row.priorImpairment = 0
    }
    if (['endGross', 'endImpairment', 'endBookValue'].includes(field)) {
      row.endBookValue = calcI5EndBookValue(row)
    }
    if (['priorGross', 'priorImpairment', 'priorBookValue'].includes(field)) {
      row.priorBookValue = calcI5PriorBookValue(row)
    }
    _persistRows()
  }

  function _num(v: unknown): number {
    const n = Number(v)
    return Number.isFinite(n) ? n : 0
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

  /** 同步到附注模块 */
  async function syncToNotes(): Promise<void> {
    if (isSyncing.value || !projectId.value || !wpId.value) return
    const diff = reconcileDiff.value
    if (diff != null && Math.abs(diff) > 0.01) {
      try {
        await ElMessageBox.confirm(
          `披露期末合计与 I5-2 明细差额 ${diff.toLocaleString('zh-CN')}，是否仍同步到附注？`,
          '同步确认',
          { type: 'warning', confirmButtonText: '仍要同步', cancelButtonText: '取消' },
        )
      } catch {
        return
      }
    }

    const state = { rows: rows.value, otherNote: otherNote.value }
    const payloads = isListed.value
      ? buildI5ListedSyncPayloads(wpId.value, _standards(), state)
      : buildI5SoeSyncPayloads(wpId.value, _standards(), state)

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
        wpCode: 'I5',
        accountCode: '1911',
      })
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: {
          wpCode: 'I5',
          variant: variant.value,
          sectionId: noteTarget.value.sectionId,
          accountCode: '1911',
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
        section: `i5-disclosure-${variant.value}`,
        prompt: '请为其他非流动资产附注生成简要披露说明（含主要构成、重大项目、受限情况）',
        context: [
          `科目1911其他非流动资产`,
          `版本:${isListed.value ? '上市公司' : '国有企业'}`,
          `期末账面价值:${t.endBookValue}`,
          `上年/年初账面价值:${t.priorBookValue}`,
          `期末减值:${t.endImpairment}`,
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
    if (detail?.wpCode === 'I5' || detail?.accountCode === '1911') {
      const detailRows = _readDetailRows()
      if (!detailRows.length) return
      const autoRows = aggregateI5DetailForDisclosure(detailRows)
      rows.value = mergeAutoFillPreserveManual(rows.value, autoRows)
      _persistRows()
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
    syncToNotes,
    generateNoteText,
  }
}

export default useI5Disclosure
