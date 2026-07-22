/**
 * useI2Capitalization — I2-6 研发项目资本化时点判断
 * 项目行表 + CAS6 五条件 + 闸门/勾稽/时点 + 联动 I2-2
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type I2CapitalizationProjectRow,
  type I2CapitalizationSummary,
  type CAS6Condition,
  type I26GateIssue,
  type I26AmountReconcile,
  emptyI2CapitalizationRow,
  normalizeI2CapitalizationRow,
  migrateLegacyCapitalizationMap,
  summarizeI2Capitalization,
  seedRowsFromI2Detail,
  getRowCapResult,
  buildI26ConclusionDraft,
  evaluateCapitalization,
  validateI26CapGate,
  validateI26CapTiming,
  reconcileI26Amounts,
  suggestCas6ConditionsFromText,
} from './i2CapitalizationModel'

export type {
  I2CapitalizationProjectRow,
  I2CapitalizationSummary,
  CAS6Condition,
  I26GateIssue,
  I26AmountReconcile,
} from './i2CapitalizationModel'

export {
  emptyI2CapitalizationRow,
  getRowCapResult,
  buildI26ConclusionDraft,
  evaluateCapitalization,
  validateI26CapGate,
  validateI26CapTiming,
  reconcileI26Amounts,
  suggestCas6ConditionsFromText,
  CAS6_CONDITION_NAMES,
  CAS6_CONDITION_ANALYSIS,
  CAS6_CONDITION_EXAMPLES,
  CAS6_OBJECTIVES,
  CAS6_PROCEDURE_HINTS,
  createEmptyCAS6Conditions,
} from './i2CapitalizationModel'

const STORAGE_ROWS = 'I2-6-rows'
const STORAGE_LEGACY = 'I2-6-capitalization'
const STORAGE_NOTE = 'I2-6-audit-note'
const STORAGE_CONCLUSION = 'I2-6-audit-conclusion'
const I22_ROWS = 'I2-2-rows'
const I27_ROWS = 'I2-7-rows'

function _safeParseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const remark = (raw as any).remark ?? (raw as any).conclusion
    if (remark != null) return _safeParseArray(remark)
  }
  return []
}

function _readText(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  if (typeof raw === 'object') return String((raw as any).remark ?? (raw as any).conclusion ?? '')
  return ''
}

function _parseObject(raw: unknown): any {
  if (!raw) return null
  if (typeof raw === 'string' && raw) {
    try { return JSON.parse(raw) } catch { return null }
  }
  if (typeof raw === 'object') {
    const remark = (raw as any).remark
    if (typeof remark === 'string' && remark) {
      try { return JSON.parse(remark) } catch { return raw }
    }
    return raw
  }
  return null
}

export function useI2Capitalization(
  allResponses: Ref<Map<string, any>> | (() => Map<string, any>),
  options?: {
    saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
  },
) {
  const getMap = typeof allResponses === 'function'
    ? allResponses
    : () => allResponses.value

  const rows = ref<I2CapitalizationProjectRow[]>([])
  const activeRowId = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load() {
    const map = getMap()
    const fromRows = _safeParseArray(map.get(STORAGE_ROWS)).map(normalizeI2CapitalizationRow)
    if (fromRows.length) {
      rows.value = fromRows
    } else {
      const legacy = migrateLegacyCapitalizationMap(_parseObject(map.get(STORAGE_LEGACY)))
      rows.value = legacy
    }
    auditNote.value = _readText(map.get(STORAGE_NOTE))
    auditConclusion.value = _readText(map.get(STORAGE_CONCLUSION))
  }

  watch(() => {
    const m = getMap()
    return [
      m.get(STORAGE_ROWS),
      m.get(STORAGE_LEGACY),
      m.get(STORAGE_NOTE),
      m.get(STORAGE_CONCLUSION),
      m.get(I22_ROWS),
      m.get(I27_ROWS),
    ]
  }, () => load(), { immediate: true, deep: false })

  const summary: ComputedRef<I2CapitalizationSummary> = computed(() =>
    summarizeI2Capitalization(rows.value),
  )

  const activeRow = computed(() =>
    rows.value.find((r) => r.rowId === activeRowId.value) || null,
  )

  const activeResult = computed(() =>
    activeRow.value ? getRowCapResult(activeRow.value) : null,
  )

  const gateIssues: ComputedRef<I26GateIssue[]> = computed(() =>
    validateI26CapGate(rows.value),
  )

  const gateBlocked = computed(() =>
    gateIssues.value.some((i) => i.level === 'error'),
  )

  const amountReconciles: ComputedRef<I26AmountReconcile[]> = computed(() =>
    reconcileI26Amounts(
      rows.value,
      _safeParseArray(getMap().get(I27_ROWS)),
      _safeParseArray(getMap().get(I22_ROWS)),
    ),
  )

  const activeTimingIssues = computed(() =>
    activeRow.value ? validateI26CapTiming(activeRow.value) : [],
  )

  function addRow(partial?: Partial<I2CapitalizationProjectRow>) {
    const row = emptyI2CapitalizationRow(partial)
    rows.value.push(row)
    activeRowId.value = row.rowId
    return row
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    if (activeRowId.value === rowId) activeRowId.value = rows.value[0]?.rowId || ''
  }

  function updateField(rowId: string, field: keyof I2CapitalizationProjectRow, value: any) {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
  }

  function updateCondition(
    rowId: string,
    condIdx: number,
    patch: Partial<Pick<CAS6Condition, 'result' | 'evidence' | 'attachments'>>,
  ) {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row || condIdx < 0 || condIdx > 4) return
    row.conditions[condIdx] = { ...row.conditions[condIdx], ...patch }
  }

  /** 据项目文本启发式建议五条件（仅填空项，不覆盖已有判断） */
  function applyAiSuggest(rowId: string): { ok: boolean; message: string; filled: number } {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return { ok: false, message: '未选中项目', filled: 0 }
    const suggested = suggestCas6ConditionsFromText({
      projectContent: row.projectContent,
      capBasis: row.capBasis,
      supportingEvidence: row.supportingEvidence,
      personnelComposition: row.personnelComposition,
    })
    let filled = 0
    for (let i = 0; i < 5; i++) {
      const cur = row.conditions[i]
      const sug = suggested[i]
      if (!sug?.result) continue
      if (cur.result) continue
      row.conditions[i] = {
        ...cur,
        result: sug.result,
        evidence: cur.evidence || sug.evidence,
      }
      filled++
    }
    return {
      ok: filled > 0,
      filled,
      message: filled > 0
        ? `已建议填入 ${filled} 项条件（请人工复核）`
        : '未匹配到关键词，或条件均已填写',
    }
  }

  function seedFromDetail(): { ok: boolean; message: string; count: number } {
    const seeded = seedRowsFromI2Detail(_safeParseArray(getMap().get(I22_ROWS)))
    if (!seeded.length) return { ok: false, count: 0, message: 'I2-2 无项目可带入' }

    const byName = new Map(rows.value.map((r) => [(r.projectName || '').trim(), r]))
    let count = 0
    for (const s of seeded) {
      const key = s.projectName.trim()
      const prev = byName.get(key)
      if (prev) {
        if (!prev.capStartDate && s.capStartDate) prev.capStartDate = s.capStartDate
        if (!prev.transferDate && s.transferDate) prev.transferDate = s.transferDate
        if (!prev.projectNo && s.projectNo) prev.projectNo = s.projectNo
        if (!prev.developmentAmount && s.developmentAmount) prev.developmentAmount = s.developmentAmount
        if (!prev.recognizedIaAmount && s.recognizedIaAmount) prev.recognizedIaAmount = s.recognizedIaAmount
        count++
      } else {
        rows.value.push(s)
        byName.set(key, s)
        count++
      }
    }
    return { ok: count > 0, count, message: `已从 I2-2 带入/更新 ${count} 项` }
  }

  /** 将满足五条件的资本化时点回写 I2-2 同名项目（闸门阻断时拒绝） */
  function linkCapDateToDetail(): { ok: boolean; message: string; count: number } {
    if (gateBlocked.value) {
      const n = gateIssues.value.filter((i) => i.level === 'error').length
      return { ok: false, count: 0, message: `资本化闸门未通过（${n} 项），禁止回写 I2-2` }
    }
    const detailRaw = _safeParseArray(getMap().get(I22_ROWS))
    if (!detailRaw.length || !options?.saveResponse) {
      return { ok: false, count: 0, message: '无 I2-2 明细或无法保存' }
    }
    let count = 0
    for (const row of rows.value) {
      const name = (row.projectName || '').trim()
      if (!name || !row.capStartDate) continue
      if (!getRowCapResult(row).isMet) continue
      for (const d of detailRaw) {
        if ((_str(d.projectName || d.name)).trim() === name) {
          if (d.capStartDate !== row.capStartDate) {
            d.capStartDate = row.capStartDate
            count++
          }
        }
      }
    }
    if (count > 0) {
      void options.saveResponse('I2-2', { [I22_ROWS]: JSON.stringify(detailRaw) })
    }
    return {
      ok: count > 0,
      count,
      message: count > 0 ? `已回写 I2-2 资本化起点 ${count} 处` : '无变更（须五条件满足且已填时点）',
    }
  }

  function _str(v: unknown): string {
    return v == null ? '' : String(v)
  }

  function fillConclusionDraft(): { ok: boolean; message: string } {
    if (gateBlocked.value) {
      return { ok: false, message: '存在资本化闸门错误，请先纠正后再生成结论' }
    }
    auditConclusion.value = buildI26ConclusionDraft(summary.value)
    return { ok: true, message: '已生成结论草稿' }
  }

  async function persistAll() {
    if (!options?.saveResponse) return
    await options.saveResponse('I2-6', {
      [STORAGE_ROWS]: JSON.stringify(rows.value),
      [STORAGE_NOTE]: auditNote.value,
      [STORAGE_CONCLUSION]: auditConclusion.value,
    })
  }

  async function saveNote(val: string) {
    auditNote.value = val
    if (options?.saveResponse) await options.saveResponse('I2-6', { [STORAGE_NOTE]: val })
  }

  async function saveConclusion(val: string) {
    auditConclusion.value = val
    if (options?.saveResponse) await options.saveResponse('I2-6', { [STORAGE_CONCLUSION]: val })
  }

  return {
    rows,
    activeRowId,
    activeRow,
    activeResult,
    summary,
    gateIssues,
    gateBlocked,
    amountReconciles,
    activeTimingIssues,
    auditNote,
    auditConclusion,
    addRow,
    removeRow,
    updateField,
    updateCondition,
    applyAiSuggest,
    seedFromDetail,
    linkCapDateToDetail,
    fillConclusionDraft,
    persistAll,
    saveNote,
    saveConclusion,
    load,
  }
}

export default useI2Capitalization
