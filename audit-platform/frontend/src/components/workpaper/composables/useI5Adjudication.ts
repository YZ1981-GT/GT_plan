/**
 * useI5Adjudication — I5-1 其他非流动资产审定表
 *
 * 镜像 I4-1：未审滚动 → 账项调整 → 审定；行自 I5-2；AJE/RJE 自 I5-3；
 * 与 TB 1911 / I5-2 勾稽；上期审定比较。无摊销列。
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useI5CrossSheet } from './useI5CrossSheet'
import {
  type I5AdjudicationRowModel,
  type I5AdjudicationCrossCheck,
  emptyI5AdjudicationRow,
  normalizeI5AdjudicationRow,
  summarizeI5Adjudication,
  seedI5AdjudicationFromDetail,
  applyAjeFromI53,
  buildI5AdjudicationCrossCheck,
  buildI5ExcelLeadSummary,
  buildI5LeadMatrixRows,
  buildI5ThreeLayerLeadFromDetail,
  appendI5TbReconciliationToLead,
  buildI5VarianceNoteDraft,
  buildI5AdjudicationConclusionDraft,
  validateI5AdjudicationSave,
  recalcI5AdjudicationRow,
  formatI5VarianceRate,
  I5_ADJ_ROWS_KEY,
  I5_ADJ_NOTE_KEY,
  I5_ADJ_CONCLUSION_KEY,
  I5_ADJ_MATTERS_KEY,
  I5_ADJ_OWNERSHIP_KEY,
  I5_DEFAULT_CATEGORIES,
  I5_CONCLUSION_OPTIONS,
} from './i5AdjudicationModel'

export type I5AdjudicationRow = I5AdjudicationRowModel
export {
  formatI5VarianceRate,
  I5_CONCLUSION_OPTIONS,
  I5_DEFAULT_CATEGORIES,
  buildI5VarianceNoteDraft,
}

export interface I5DifferenceRow {
  label: string
  accountCode: string
  audited: number
  tbAmount: number
  difference: number
}

export interface I5ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

const ITEM_PREFIX = 'I5-adj'
const ACCOUNT_CODE_1911 = '1911'
const DEFAULT_CATEGORIES = [...I5_DEFAULT_CATEGORIES]

function safeParseRows(raw: unknown): any[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch {
      return []
    }
  }
  return []
}

export function useI5Adjudication(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, I5ChecklistItem>>,
  options?: {
    tbUnadjusted1911?: Ref<number>
    tbAudited1911?: Ref<number>
    tbPriorAudited1911?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<I5AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const significantMatters = ref('')
  const ownershipPledge = ref('')

  const {
    detailTotals,
    detailRowsRaw,
    adjustmentRowsRaw,
  } = useI5CrossSheet(allResponses as Ref<Map<string, any>>)

  function _loadRows(): void {
    const data = _getJson(I5_ADJ_ROWS_KEY) ?? _getJson(`${ITEM_PREFIX}-rows`)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(normalizeI5AdjudicationRow)
    } else {
      rows.value = DEFAULT_CATEGORIES.map((cat) => emptyI5AdjudicationRow({ projectName: cat }))
    }
    auditNote.value = _getString(I5_ADJ_NOTE_KEY) || _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(I5_ADJ_CONCLUSION_KEY) || _getString(`${ITEM_PREFIX}-audit-conclusion`)
    significantMatters.value = _getString(I5_ADJ_MATTERS_KEY) || _getString(`${ITEM_PREFIX}-significant-matters`)
    ownershipPledge.value = _getString(I5_ADJ_OWNERSHIP_KEY) || _getString(`${ITEM_PREFIX}-ownership-pledge`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    if (typeof raw !== 'string') return raw
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  const computedRows = computed(() => rows.value.map(recalcI5AdjudicationRow))
  const subtotals = computed(() => summarizeI5Adjudication(computedRows.value))
  const excelLead = computed(() => buildI5ExcelLeadSummary(computedRows.value))
  const leadMatrixRows = computed(() => buildI5LeadMatrixRows(computedRows.value))
  /** 有 I5-2 嵌套原值/减值时展示三层矩阵 + TB勾稽；否则回退净值矩阵 */
  const threeLayerLeadRows = computed(() => {
    const detail = detailRowsRaw.value
    const hasNested = detail.some((r: any) => r?.gross && typeof r.gross === 'object')
    if (hasNested) {
      const base = buildI5ThreeLayerLeadFromDetail(detail)
      return appendI5TbReconciliationToLead(base, tbUnadjusted.value)
    }
    return leadMatrixRows.value.map((r) => ({ ...r, layer: r.isTotal ? 'total' as const : 'net' as const }))
  })
  const hasThreeLayerDetail = computed(() =>
    detailRowsRaw.value.some((r: any) => r?.gross && typeof r.gross === 'object'),
  )
  const crossCheck = computed<I5AdjudicationCrossCheck>(() =>
    buildI5AdjudicationCrossCheck(computedRows.value, detailTotals.value as any),
  )
  const reconciliationStatus = computed<'balanced' | 'mismatch'>(() =>
    computedRows.value.some((r) => r.hasError) ? 'mismatch' : 'balanced',
  )
  const hasAjeApprox = computed(() => computedRows.value.some((r) => r.ajeApprox))
  const tbUnadjusted = computed(() => options?.tbUnadjusted1911?.value ?? 0)
  const tbDifference = computed(() => subtotals.value.audited - tbUnadjusted.value)
  const differenceRows = computed<I5DifferenceRow[]>(() => [{
    label: '其他非流动资产(1911)',
    accountCode: ACCOUNT_CODE_1911,
    audited: subtotals.value.audited,
    tbAmount: tbUnadjusted.value,
    difference: tbDifference.value,
  }])

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(I5_ADJ_ROWS_KEY, rows.value)
    save(`${ITEM_PREFIX}-rows`, rows.value)
  }

  async function addRow(): Promise<void> {
    try {
      const { value: projectName } = await ElMessageBox.prompt(
        '请输入其他非流动资产项目名称',
        '新增项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '项目名称不能为空',
        },
      )
      if (!projectName) return
      rows.value.push(emptyI5AdjudicationRow({ projectName: projectName.trim() }))
      _persist()
      ElMessage.success(`已添加：${projectName}`)
    } catch { /* cancel */ }
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    const removed = rows.value.splice(idx, 1)[0]
    _persist()
    ElMessage.info(`已删除：${removed.projectName}`)
  }

  function updateCell(rowId: string, field: keyof I5AdjudicationRowModel, value: number | string): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row || row.isEditable === false) return
    ;(row as any)[field] = value
    if (field === 'aje' || field === 'rje') row.ajeApprox = false
    Object.assign(row, recalcI5AdjudicationRow(row))
    _persist()
  }

  function seedFromI52(): void {
    const detail = detailRowsRaw.value.length
      ? detailRowsRaw.value
      : safeParseRows(_getJson('I5-2-rows'))
    if (!detail.length) {
      ElMessage.warning('I5-2 明细暂无数据，请先编制明细表')
      return
    }
    rows.value = seedI5AdjudicationFromDetail(detail, rows.value)
    _persist()
    ElMessage.success(`已从 I5-2 带入 ${rows.value.length} 行（保留已有 AJE/RJE）`)
  }

  function syncFromI53(): void {
    const adj = adjustmentRowsRaw.value.length
      ? adjustmentRowsRaw.value
      : safeParseRows(_getJson('I5-3-rows'))
    const result = applyAjeFromI53(rows.value, adj)
    rows.value = result.rows
    _persist()
    if (!result.applied && Math.abs(result.totalAje) < 0.005 && Math.abs(result.totalRje) < 0.005) {
      ElMessage.info('I5-3 无 1911 相关调整可同步')
      return
    }
    ElMessage.success(
      result.approx
        ? `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（含近似分摊，请复核）`
        : `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（精确匹配 ${result.matchedByName}）`,
    )
  }

  function applyTbData(tbUnadjustedTotal?: number): void {
    const total = tbUnadjustedTotal ?? tbUnadjusted.value
    if (!rows.value.length) return
    if (rows.value.length === 1) {
      rows.value[0] = recalcI5AdjudicationRow({ ...rows.value[0], unadjusted: total })
    } else {
      const base = rows.value.map((r) => Math.abs(r.beginBalance) || Math.abs(r.endBalance) || 0)
      const sum = base.reduce((a, b) => a + b, 0)
      if (sum > 0) {
        let left = total
        rows.value = rows.value.map((r, i) => {
          const isLast = i === rows.value.length - 1
          const amt = isLast ? Math.round(left * 100) / 100 : Math.round((total * base[i] / sum) * 100) / 100
          left = Math.round((left - amt) * 100) / 100
          return recalcI5AdjudicationRow({ ...r, unadjusted: amt })
        })
      } else {
        rows.value[0] = recalcI5AdjudicationRow({ ...rows.value[0], unadjusted: total })
      }
    }
    _persist()
    ElMessage.success('已写入 TB 未审数')
  }

  /** 从上期 TB / 比较期字段写入 priorAudited */
  function applyPriorFromTb(priorTotal?: number): void {
    const total = priorTotal ?? options?.tbPriorAudited1911?.value ?? 0
    if (!(Math.abs(total) > 0.005)) {
      ElMessage.warning('暂无上期审定/比较期数据（TB prior_* 字段）')
      return
    }
    if (rows.value.length === 1) {
      rows.value[0] = recalcI5AdjudicationRow({ ...rows.value[0], priorAudited: total })
    } else {
      const base = rows.value.map((r) => Math.abs(r.beginBalance) || Math.abs(r.unadjusted) || 0)
      const sum = base.reduce((a, b) => a + b, 0)
      if (sum > 0) {
        let left = total
        rows.value = rows.value.map((r, i) => {
          const isLast = i === rows.value.length - 1
          const amt = isLast ? Math.round(left * 100) / 100 : Math.round((total * base[i] / sum) * 100) / 100
          left = Math.round((left - amt) * 100) / 100
          return recalcI5AdjudicationRow({ ...r, priorAudited: amt })
        })
      } else {
        rows.value[0] = recalcI5AdjudicationRow({ ...rows.value[0], priorAudited: total })
      }
    }
    _persist()
    ElMessage.success('已写入上期审定')
  }

  function fillConclusionDraft(): void {
    auditConclusion.value = buildI5AdjudicationConclusionDraft({
      sampleCount: rows.value.length,
      auditedTotal: subtotals.value.audited,
      tbDiff: tbDifference.value,
      hasAje: rows.value.some((r) => Math.abs(r.aje) + Math.abs(r.rje) > 0.005),
      crossWarning: crossCheck.value.hasWarning,
    })
    saveConclusion(auditConclusion.value)
  }

  /** 生成 Excel 式变动说明草稿，写入审计说明（可再编辑） */
  function fillVarianceNoteDraft(append = true): void {
    const draft = buildI5VarianceNoteDraft(computedRows.value)
    auditNote.value = append && auditNote.value.trim()
      ? `${auditNote.value.trim()}\n\n${draft}`
      : draft
    saveNote(auditNote.value)
  }

  function applyConclusionTemplate(key: string): void {
    const t = I5_CONCLUSION_OPTIONS.find((x) => x.key === key)
    if (!t) return
    auditConclusion.value = t.text
    saveConclusion(t.text)
  }

  async function writeback(force = false): Promise<{ ok: boolean; message?: string }> {
    const gate = validateI5AdjudicationSave({
      rows: computedRows.value,
      tbDiff: tbDifference.value,
      force,
    })
    if (!gate.ok) {
      const msg = gate.blockers.join('；')
      ElMessage.error(msg)
      return { ok: false, message: msg }
    }
    if (gate.warnings.length) ElMessage.warning(gate.warnings[0])

    _persist()
    const auditedTotal = subtotals.value.audited
    options?.onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    if (projectId.value) {
      try {
        await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_1911,
          audited_amount: auditedTotal,
        })
        ElMessage.success('审定数已回写试算表(1911)')
      } catch {
        ElMessage.warning('审定数回写试算表失败，请手动确认')
      }
    }

    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { wpCode: 'I5', accountCodes: [ACCOUNT_CODE_1911], auditedTotal },
    }))
    return { ok: true }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(I5_ADJ_NOTE_KEY, note)
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(I5_ADJ_CONCLUSION_KEY, conclusion)
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  function saveSignificantMatters(text: string): void {
    significantMatters.value = text
    options?.onSave?.(I5_ADJ_MATTERS_KEY, text)
    options?.onSave?.(`${ITEM_PREFIX}-significant-matters`, text)
  }

  function saveOwnershipPledge(text: string): void {
    ownershipPledge.value = text
    options?.onSave?.(I5_ADJ_OWNERSHIP_KEY, text)
    options?.onSave?.(`${ITEM_PREFIX}-ownership-pledge`, text)
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  return {
    rows: computedRows,
    auditNote,
    auditConclusion,
    significantMatters,
    ownershipPledge,
    subtotals,
    excelLead,
    leadMatrixRows,
    threeLayerLeadRows,
    hasThreeLayerDetail,
    crossCheck,
    reconciliationStatus,
    hasAjeApprox,
    tbUnadjusted,
    tbDifference,
    differenceRows,
    addRow,
    removeRow,
    updateCell,
    seedFromI52,
    syncFromI53,
    applyTbData,
    applyPriorFromTb,
    applyAdjustments: (adjustments: { 项目: string; AJE: number; RJE: number }[]) => {
      for (const adj of adjustments) {
        const row = rows.value.find((r) => r.projectName === adj.项目)
        if (!row) continue
        row.aje = adj.AJE
        row.rje = adj.RJE
        row.ajeApprox = false
        Object.assign(row, recalcI5AdjudicationRow(row))
      }
      _persist()
    },
    fillConclusionDraft,
    fillVarianceNoteDraft,
    applyConclusionTemplate,
    writeback,
    saveNote,
    saveConclusion,
    saveSignificantMatters,
    saveOwnershipPledge,
  }
}

export default useI5Adjudication
