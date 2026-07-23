/**
 * useI3Adjudication — I3-1 商誉审定表
 *
 * 对齐 Excel：未审 → 账项调整 → 审定；行自 I3-2 带入；AJE/RJE 自 I3-3；
 * 本期减值可自 I3-6；与 TB 1711 / I3-2 勾稽。
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useI3CrossSheet } from './useI3CrossSheet'
import {
  type I3AdjudicationRowModel,
  type I3AdjudicationCrossCheck,
  emptyI3AdjudicationRow,
  normalizeI3AdjudicationRow,
  summarizeI3Adjudication,
  seedI3AdjudicationFromDetail,
  allocateI3Adjustments,
  applyAjeFromI33,
  applyI3ImpairmentFromTest,
  buildI3AdjudicationCrossCheck,
  buildI3AdjudicationConclusionDraft,
  buildI3LayerSummary,
  validateI3AdjudicationSave,
  recalcI3AdjudicationRow,
  I3_ADJ_ROWS_KEY,
  I3_ADJ_ROWS_CANDIDATES,
  I3_ADJ_NOTE_KEY,
  I3_ADJ_CONCLUSION_KEY,
} from './i3AdjudicationModel'

export type I3AdjudicationRow = I3AdjudicationRowModel

export interface I3Warning {
  rowId: string
  investee: string
  type: 'newAcquisition' | 'impairmentReversal' | 'endVsNet'
  message: string
}

export interface I3DifferenceRow {
  label: string
  accountCode: string
  audited: number
  tbAmount: number
  difference: number
}

export interface I3ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

const ITEM_PREFIX = 'I3-adj'
const ACCOUNT_CODE_1711 = '1711'

export function useI3Adjudication(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, I3ChecklistItem>>,
  options?: {
    tbUnadjusted1711?: Ref<number>
    tbAudited1711?: Ref<number>
    crossSheetImpairment?: Ref<number>
    asOfYear?: Ref<number> | (() => number)
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<I3AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  const {
    detailTotals,
    impairmentResult,
    adjustmentSync,
  } = useI3CrossSheet(allResponses as Ref<Map<string, any>>)

  function getYear(): number {
    if (!options?.asOfYear) return new Date().getFullYear()
    return typeof options.asOfYear === 'function'
      ? options.asOfYear()
      : options.asOfYear.value
  }

  function _loadRows(): void {
    let data: any = null
    for (const key of I3_ADJ_ROWS_CANDIDATES) {
      data = _getJson(key)
      if (Array.isArray(data) && data.length > 0) break
    }
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(normalizeI3AdjudicationRow)
    } else {
      rows.value = []
    }
    auditNote.value = _getString(I3_ADJ_NOTE_KEY) || _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(I3_ADJ_CONCLUSION_KEY) || _getString(`${ITEM_PREFIX}-audit-conclusion`)
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

  const subtotals = computed(() => summarizeI3Adjudication(rows.value))

  const crossCheck = computed<I3AdjudicationCrossCheck>(() =>
    buildI3AdjudicationCrossCheck(rows.value, detailTotals.value),
  )

  const warnings = computed<I3Warning[]>(() => {
    const result: I3Warning[] = []
    for (const row of rows.value) {
      if (row.newAcquisition !== 0) {
        result.push({
          rowId: row.rowId,
          investee: row.investee,
          type: 'newAcquisition',
          message: `${row.investee || '未命名'}：本期增加非零（${row.newAcquisition}），请确认是否有新并购交易`,
        })
      }
      if (row.impairment < 0) {
        result.push({
          rowId: row.rowId,
          investee: row.investee,
          type: 'impairmentReversal',
          message: `${row.investee || '未命名'}：商誉减值不可转回！本期减少不能为负数`,
        })
      }
      if (Math.abs(row.endBalance - row.netValue) > 0.01) {
        result.push({
          rowId: row.rowId,
          investee: row.investee,
          type: 'endVsNet',
          message: `${row.investee || '未命名'}：期末余额(${row.endBalance})与净额(${row.netValue})不一致，请核对期初/原值/累计减值`,
        })
      }
    }
    return result
  })

  function getWarnings(): I3Warning[] {
    return warnings.value
  }

  const tbRow = computed(() => ({
    unadjusted: options?.tbUnadjusted1711?.value ?? 0,
    audited: options?.tbAudited1711?.value ?? 0,
  }))

  const differenceRows = computed<I3DifferenceRow[]>(() => {
    const tbUnadj = options?.tbUnadjusted1711?.value ?? 0
    const auditedTotal = subtotals.value.audited
    return [
      {
        label: '商誉(1711)',
        accountCode: ACCOUNT_CODE_1711,
        audited: auditedTotal,
        tbAmount: tbUnadj,
        difference: Math.round((auditedTotal - tbUnadj) * 100) / 100,
      },
    ]
  })

  const tbDiff = computed(() => differenceRows.value[0]?.difference ?? 0)

  async function addRow(): Promise<void> {
    try {
      const { value: investeeName } = await ElMessageBox.prompt(
        '请输入被投资单位名称',
        '新增商誉项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '被投资单位名称不能为空',
        },
      )
      if (!investeeName) return
      rows.value.push(emptyI3AdjudicationRow({ investee: investeeName.trim() }))
      _persist()
      ElMessage.success(`已添加：${investeeName}`)
    } catch {
      /* cancel */
    }
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      const removed = rows.value.splice(idx, 1)[0]
      _persist()
      ElMessage.info(`已删除：${removed.investee}`)
    }
  }

  function updateCell(
    rowId: string,
    field: keyof I3AdjudicationRow,
    value: number | string,
  ): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row || row.isEditable === false) return

    if (field === 'impairment' && typeof value === 'number' && value < 0) {
      ElMessage.error('商誉减值不可转回！本期减少不能为负数')
      return
    }

    ;(row as any)[field] = value
    // 手工改调整后清除近似标记
    if (field === 'aje' || field === 'rje') {
      row.ajeApprox = false
    }
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) rows.value[idx] = recalcI3AdjudicationRow(row)
    _persist()
  }

  function applyTbData(tbUnadjustedTotal: number): void {
    if (rows.value.length === 1) {
      rows.value[0] = recalcI3AdjudicationRow({
        ...rows.value[0],
        unadjusted: tbUnadjustedTotal,
      })
    } else if (rows.value.length > 1) {
      const totalBegin = rows.value.reduce((s, r) => s + r.beginBalance, 0)
      if (totalBegin > 0) {
        rows.value = rows.value.map((row) => recalcI3AdjudicationRow({
          ...row,
          unadjusted: Math.round((row.beginBalance / totalBegin) * tbUnadjustedTotal * 100) / 100,
        }))
      }
    }
    _persist()
  }

  function applyAdjustments(adjustments: { investee: string; aje: number; rje: number }[]): void {
    for (const adj of adjustments) {
      const row = rows.value.find((r) => r.investee === adj.investee)
      if (row) {
        Object.assign(row, recalcI3AdjudicationRow({ ...row, aje: adj.aje, rje: adj.rje }))
      }
    }
    _persist()
  }

  /** 从 I3-2 带入/更新行（保留已有 AJE/RJE） */
  function seedFromI32(): { ok: boolean; message: string; count: number } {
    const raw = allResponses.value.get('I3-2-rows')
    const seeded = seedI3AdjudicationFromDetail(raw, getYear(), rows.value)
    if (!seeded.length) {
      return { ok: false, count: 0, message: 'I3-2 无明细可带入，请先完成明细表' }
    }
    rows.value = seeded
    _persist()
    return { ok: true, count: seeded.length, message: `已从 I3-2 带入/更新 ${seeded.length} 个被投资单位` }
  }

  /** 从 I3-3 同步 AJE/RJE：优先按被投资单位精确匹配，剩余比例分摊并标近似 */
  function syncFromI33(): { ok: boolean; message: string; approx?: boolean } {
    if (!rows.value.length) return { ok: false, message: '请先带入或新增审定行' }
    const adjRows = (() => {
      const raw = allResponses.value.get('I3-3-rows')
      if (!raw) return []
      const remark = (raw as any).remark ?? (raw as any).conclusion ?? raw
      if (Array.isArray(remark)) return remark
      if (typeof remark === 'string') {
        try {
          const p = JSON.parse(remark)
          return Array.isArray(p) ? p : []
        } catch { return [] }
      }
      return []
    })()
    const result = applyAjeFromI33(rows.value, adjRows)
    if (Math.abs(result.totalAje) < 0.005 && Math.abs(result.totalRje) < 0.005) {
      // 回退：无行级明细时用 crossSheet 合计分摊
      const { totalAje, totalRje } = adjustmentSync.value
      if (Math.abs(totalAje) < 0.005 && Math.abs(totalRje) < 0.005) {
        return { ok: false, message: 'I3-3 无 1711 相关 AJE/RJE 可同步' }
      }
      rows.value = allocateI3Adjustments(rows.value, totalAje, totalRje, true)
      _persist()
      return {
        ok: true,
        approx: rows.value.length > 1,
        message: `已按合计分摊 AJE ${totalAje.toFixed(2)} / RJE ${totalRje.toFixed(2)}${rows.value.length > 1 ? '（近似，请复核）' : ''}`,
      }
    }
    rows.value = result.rows
    _persist()
    const parts = [
      `AJE ${result.totalAje.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
      `RJE ${result.totalRje.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
      result.matchedByName ? `精确匹配 ${result.matchedByName}` : '',
      result.approx ? '含近似分摊须复核' : '',
    ].filter(Boolean)
    return { ok: true, approx: result.approx, message: `已同步 ${parts.join(' / ')}` }
  }

  /** 从 I3-6 同步本期商誉减值 */
  function syncImpairmentFromI36(): { ok: boolean; message: string } {
    if (!rows.value.length) return { ok: false, message: '请先带入或新增审定行' }
    const byName: Record<string, number> = {}
    for (const [cgu, v] of Object.entries(impairmentResult.value.byCgu)) {
      byName[cgu] = v.goodwillImpairment
    }
    const total = impairmentResult.value.totalImpairment
    if (!(total > 0) && !Object.keys(byName).length) {
      return { ok: false, message: 'I3-6 无商誉减值可同步' }
    }
    rows.value = applyI3ImpairmentFromTest(rows.value, byName, total)
    _persist()
    return {
      ok: true,
      message: `已同步本期商誉减值 ${total.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
    }
  }

  function fillConclusionDraft(): void {
    auditConclusion.value = buildI3AdjudicationConclusionDraft({
      rowCount: rows.value.length,
      auditedTotal: subtotals.value.audited,
      netTotal: subtotals.value.netValue,
      newAcquisitionTotal: subtotals.value.newAcquisition,
      impairmentTotal: subtotals.value.impairment,
      tbDiff: tbDiff.value,
      crossCheck: crossCheck.value,
    })
  }

  const layerSummary = computed(() => buildI3LayerSummary(rows.value))

  const hasAjeApprox = computed(() => rows.value.some((r) => r.ajeApprox))

  async function saveAdjudication(opts?: { force?: boolean }): Promise<{ ok: boolean; message: string }> {
    const gate = validateI3AdjudicationSave({
      rows: rows.value,
      tbDiff: tbDiff.value,
      force: opts?.force,
    })
    if (!gate.ok) {
      return { ok: false, message: gate.blockers.join('；') }
    }
    _persist()
    const auditedTotal = subtotals.value.audited
    options?.onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)
    options?.onSave?.(`${ITEM_PREFIX}-audited-net`, subtotals.value.netValue)

    if (projectId.value) {
      try {
        await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_1711,
          audited_amount: auditedTotal,
        })
      } catch {
        ElMessage.warning('审定数回写试算表失败，请手动确认')
      }
    }

    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: {
        wpCode: 'I3',
        accountCodes: [ACCOUNT_CODE_1711],
        auditedTotal,
        netValue: subtotals.value.netValue,
      },
    }))
    return {
      ok: true,
      message: gate.warnings.length
        ? `已保存（注意：${gate.warnings.slice(0, 2).join('；')}）`
        : '审定表已保存',
    }
  }

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(I3_ADJ_ROWS_KEY, rows.value)
    save(`${ITEM_PREFIX}-rows`, rows.value) // 兼容旧 key
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(I3_ADJ_NOTE_KEY, note)
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(I3_ADJ_CONCLUSION_KEY, conclusion)
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  return {
    rows,
    auditNote,
    auditConclusion,
    subtotals,
    warnings,
    crossCheck,
    detailTotals,
    adjustmentSync,
    impairmentResult,
    layerSummary,
    hasAjeApprox,
    tbRow,
    tbDiff,
    differenceRows,
    addRow,
    removeRow,
    updateCell,
    applyTbData,
    applyAdjustments,
    seedFromI32,
    syncFromI33,
    syncImpairmentFromI36,
    fillConclusionDraft,
    saveAdjudication,
    saveNote,
    saveConclusion,
    getWarnings,
  }
}

export default useI3Adjudication
