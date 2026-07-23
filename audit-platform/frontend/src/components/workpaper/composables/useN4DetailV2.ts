/**
 * useN4DetailV2 — N4-2 税金及附加明细表（对齐源模板双期增减四栏 + 应交税费核对）
 *
 * 源模板结构：
 *   A: 项目（税种名）
 *   B-E（本期）: 未审数 / 账项调整 / 重分类调整 / 审定数(=B+C+D)
 *   F-I（上期）: 未审数 / 账项调整 / 重分类调整 / 审定数(=F+G+H)
 *   J: 应交税费贷方金额
 *   K: 与应交税费贷方差异(=E-J)
 *   合计行 + 审计目标 + 审计过程/说明/结论
 *
 * Item IDs: "N4-2-rows-v2", "N4-2-subtotal", "N4-2-note", "N4-2-conclusion"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcYoyChange } from './useN4FormulaEngine'
import { N4_TAX_TYPES, n4NormalizeKey } from './n4TaxTypes'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表双期行 */
export interface N4DetailRowV2 {
  rowKey: string
  taxType: string
  /** 本期：未审数 */
  curUnadj: number
  /** 本期：账项调整 */
  curAje: number
  /** 本期：重分类调整 */
  curRje: number
  /** 本期：审定数（公式 = curUnadj + curAje + curRje） */
  curAudited: number
  /** 上期：未审数 */
  priorUnadj: number
  /** 上期：账项调整 */
  priorAje: number
  /** 上期：重分类调整 */
  priorRje: number
  /** 上期：审定数（公式 = priorUnadj + priorAje + priorRje） */
  priorAudited: number
  /** 应交税费贷方金额（来自 N2 或手工） */
  n2Credit: number
  /** 与应交税费贷方差异（公式 = curAudited - n2Credit） */
  diffN2: number
  /** 可编辑 */
  isEditable: boolean
}

export interface N4DetailSubtotalV2 {
  curUnadj: number
  curAje: number
  curRje: number
  curAudited: number
  priorUnadj: number
  priorAje: number
  priorRje: number
  priorAudited: number
  n2Credit: number
  diffN2: number
}

export interface UseN4DetailV2Params {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean | undefined>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'N4-2-rows-v2'
const SUBTOTAL_KEY = 'N4-2-subtotal'
const NOTE_KEY = 'N4-2-note'
const CONCLUSION_KEY = 'N4-2-conclusion'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN4DetailV2(params: UseN4DetailV2Params) {
  const { allResponses, wpId, isReadonly, onSave } = params

  const rows = ref<N4DetailRowV2[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    // 优先读 v2 格式
    const rawV2 = _getJson(ROWS_KEY)
    if (Array.isArray(rawV2) && rawV2.length > 0) {
      rows.value = rawV2.map(_normalizeRow)
    } else {
      // 回退：尝试读旧 v1 格式并迁移
      const rawV1 = _getJson('N4-2-detail-rows')
      if (Array.isArray(rawV1) && rawV1.length > 0) {
        rows.value = rawV1.map(_migrateV1Row)
      } else {
        rows.value = _buildDefaultRows()
      }
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): N4DetailRowV2 {
    const curUnadj = parseNum(raw.curUnadj)
    const curAje = parseNum(raw.curAje)
    const curRje = parseNum(raw.curRje)
    const curAudited = curUnadj + curAje + curRje
    const priorUnadj = parseNum(raw.priorUnadj)
    const priorAje = parseNum(raw.priorAje)
    const priorRje = parseNum(raw.priorRje)
    const priorAudited = priorUnadj + priorAje + priorRje
    const n2Credit = parseNum(raw.n2Credit)
    return {
      rowKey: n4NormalizeKey(raw.rowKey) || n4NormalizeKey(raw.taxType) || raw.rowKey || '',
      taxType: raw.taxType ?? '',
      curUnadj, curAje, curRje, curAudited,
      priorUnadj, priorAje, priorRje, priorAudited,
      n2Credit,
      diffN2: curAudited - n2Credit,
      isEditable: raw.isEditable ?? true,
    }
  }

  /** 从旧 v1 行迁移（计税依据×税率 → 本期未审数，其余归零） */
  function _migrateV1Row(raw: any): N4DetailRowV2 {
    const periodAmount = parseNum(raw.taxBasis) * parseNum(raw.taxRate)
    return _normalizeRow({
      rowKey: raw.rowKey,
      taxType: raw.taxType,
      curUnadj: periodAmount || parseNum(raw.periodAmount),
      curAje: 0,
      curRje: 0,
      priorUnadj: parseNum(raw.priorAmount),
      priorAje: 0,
      priorRje: 0,
      n2Credit: parseNum(raw.n2Accrual),
      isEditable: true,
    })
  }

  function _buildDefaultRows(): N4DetailRowV2[] {
    return N4_TAX_TYPES.map((t) => ({
      rowKey: t.key,
      taxType: t.label,
      curUnadj: 0, curAje: 0, curRje: 0, curAudited: 0,
      priorUnadj: 0, priorAje: 0, priorRje: 0, priorAudited: 0,
      n2Credit: 0, diffN2: 0,
      isEditable: true,
    }))
  }

  // ─── Computed rows（公式列自动重算） ───────────────────────────────────

  const computedRows: ComputedRef<N4DetailRowV2[]> = computed(() => {
    return rows.value.map((row) => {
      const curAudited = row.curUnadj + row.curAje + row.curRje
      const priorAudited = row.priorUnadj + row.priorAje + row.priorRje
      const diffN2 = curAudited - row.n2Credit
      return { ...row, curAudited, priorAudited, diffN2 }
    })
  })

  // ─── Subtotal ──────────────────────────────────────────────────────────

  const subtotal: ComputedRef<N4DetailSubtotalV2> = computed(() => {
    const r = computedRows.value
    const curUnadj = calcSubtotal(r.map(x => x.curUnadj))
    const curAje = calcSubtotal(r.map(x => x.curAje))
    const curRje = calcSubtotal(r.map(x => x.curRje))
    const curAudited = curUnadj + curAje + curRje
    const priorUnadj = calcSubtotal(r.map(x => x.priorUnadj))
    const priorAje = calcSubtotal(r.map(x => x.priorAje))
    const priorRje = calcSubtotal(r.map(x => x.priorRje))
    const priorAudited = priorUnadj + priorAje + priorRje
    const n2Credit = calcSubtotal(r.map(x => x.n2Credit))
    return { curUnadj, curAje, curRje, curAudited, priorUnadj, priorAje, priorRje, priorAudited, n2Credit, diffN2: curAudited - n2Credit }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────

  type EditableField = 'curUnadj' | 'curAje' | 'curRje' | 'priorUnadj' | 'priorAje' | 'priorRje' | 'n2Credit'

  function updateCell(rowKey: string, field: EditableField, value: number): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalc(row)
    isChanged.value = true
    _persist()
  }

  function _recalc(row: N4DetailRowV2): void {
    row.curAudited = row.curUnadj + row.curAje + row.curRje
    row.priorAudited = row.priorUnadj + row.priorAje + row.priorRje
    row.diffN2 = row.curAudited - row.n2Credit
  }

  // ─── Dynamic rows ─────────────────────────────────────────────────────

  function addRow(taxType: string): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `custom-${Date.now()}`,
      taxType,
      curUnadj: 0, curAje: 0, curRje: 0, curAudited: 0,
      priorUnadj: 0, priorAje: 0, priorRje: 0, priorAudited: 0,
      n2Credit: 0, diffN2: 0,
      isEditable: true,
    })
    isChanged.value = true
    _persist()
  }

  function removeRow(rowKey: string): void {
    if (isReadonly?.value) return
    const idx = rows.value.findIndex(r => r.rowKey === rowKey)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      isChanged.value = true
      _persist()
    }
  }

  // ─── Note / Conclusion ─────────────────────────────────────────────────

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    onSave?.(CONCLUSION_KEY, conclusion)
  }

  // ─── Persist ───────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    // 合计供 crossSheet 交叉验证
    onSave(SUBTOTAL_KEY, subtotal.value.curAudited)
  }

  // ─── Watch init ────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  return {
    rows: computedRows,
    subtotal,
    auditNote,
    auditConclusion,
    isChanged,
    updateCell,
    addRow,
    removeRow,
    saveNote,
    saveConclusion,
    initFromResponses,
  }
}

export default useN4DetailV2
