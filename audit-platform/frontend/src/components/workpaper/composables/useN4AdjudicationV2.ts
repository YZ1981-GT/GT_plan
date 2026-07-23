/**
 * useN4AdjudicationV2 — N4-1 税金及附加审定表（对齐源模板双期14列 + TB勾稽）
 *
 * 源模板结构 (14列)：
 *   A: 项目
 *   B-E（上年数）: 未审 / 账项调整 / 重分类 / 审定(=B+C+D)
 *   F-I（本期数）: 未审 / 账项调整 / 重分类 / 审定(=F+G+H)
 *   J-K（本期未审vs上期未审）: 变动额(=F-B) / 变动率
 *   L-M（本期审定vs上期审定）: 变动额(=I-E) / 变动率
 *   N: 原因分析
 *   合计行 + 试算平衡表数(TB) + 差异数(=审定合计-TB) + 审计说明 + 审计结论
 *
 * 数据来源: 主要从 N4-2 同步（或独立录入）。
 * Item IDs: "N4-1-rows-v2", "N4-1-audited-total", "N4-1-adjudicated-amount",
 *           "N4-1-audit-note", "N4-1-audit-conclusion"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcYoyChange } from './useN4FormulaEngine'
import { N4_TAX_TYPES, n4NormalizeKey } from './n4TaxTypes'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface N4AdjRowV2 {
  rowKey: string
  taxType: string
  /** 上年：未审 */
  priorUnadj: number
  /** 上年：账项调整 */
  priorAje: number
  /** 上年：重分类 */
  priorRje: number
  /** 上年：审定（公式） */
  priorAudited: number
  /** 本期：未审 */
  curUnadj: number
  /** 本期：账项调整 */
  curAje: number
  /** 本期：重分类 */
  curRje: number
  /** 本期：审定（公式） */
  curAudited: number
  /** 本期未审vs上期未审：变动额（公式=curUnadj-priorUnadj） */
  unadjDiff: number
  /** 本期未审vs上期未审：变动率 */
  unadjRate: number | null
  /** 本期审定vs上期审定：变动额（公式=curAudited-priorAudited） */
  auditedDiff: number
  /** 本期审定vs上期审定：变动率 */
  auditedRate: number | null
  /** 原因分析 */
  reason: string
  isEditable: boolean
}

export interface UseN4AdjudicationV2Params {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
  writebackTB?: (auditedAmount: number) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'N4-1-rows-v2'
const ROWS_KEY_LEGACY = 'N4-1-rows'
const TOTAL_KEY = 'N4-1-audited-total'
const ADJ_AMOUNT_KEY = 'N4-1-adjudicated-amount'
const NOTE_KEY = 'N4-1-audit-note'
const CONCLUSION_KEY = 'N4-1-audit-conclusion'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN4AdjudicationV2(params: UseN4AdjudicationV2Params) {
  const { allResponses, isReadonly, onSave, writebackTB } = params

  const rows = ref<N4AdjRowV2[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const rawV2 = _getJson(ROWS_KEY)
    if (Array.isArray(rawV2) && rawV2.length > 0) {
      rows.value = rawV2.map(_normalizeRow)
    } else {
      // 回退旧格式
      const rawV1 = _getJson(ROWS_KEY_LEGACY)
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
    const raw = item?.remark ?? item?.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): N4AdjRowV2 {
    const priorUnadj = parseNum(raw.priorUnadj)
    const priorAje = parseNum(raw.priorAje)
    const priorRje = parseNum(raw.priorRje)
    const priorAudited = priorUnadj + priorAje + priorRje
    const curUnadj = parseNum(raw.curUnadj)
    const curAje = parseNum(raw.curAje)
    const curRje = parseNum(raw.curRje)
    const curAudited = curUnadj + curAje + curRje
    return {
      rowKey: n4NormalizeKey(raw.rowKey) || n4NormalizeKey(raw.taxType) || raw.rowKey || '',
      taxType: raw.taxType ?? '',
      priorUnadj, priorAje, priorRje, priorAudited,
      curUnadj, curAje, curRje, curAudited,
      unadjDiff: curUnadj - priorUnadj,
      unadjRate: calcYoyChange(curUnadj, priorUnadj),
      auditedDiff: curAudited - priorAudited,
      auditedRate: calcYoyChange(curAudited, priorAudited),
      reason: raw.reason ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  function _migrateV1Row(raw: any): N4AdjRowV2 {
    return _normalizeRow({
      rowKey: raw.rowKey,
      taxType: raw.taxType,
      curUnadj: parseNum(raw.unadjusted),
      curAje: parseNum(raw.aje),
      curRje: parseNum(raw.rje),
      priorUnadj: parseNum(raw.prior),
      priorAje: 0,
      priorRje: 0,
      reason: raw.remark ?? '',
      isEditable: true,
    })
  }

  function _buildDefaultRows(): N4AdjRowV2[] {
    return N4_TAX_TYPES.map(t => ({
      rowKey: t.key, taxType: t.label,
      priorUnadj: 0, priorAje: 0, priorRje: 0, priorAudited: 0,
      curUnadj: 0, curAje: 0, curRje: 0, curAudited: 0,
      unadjDiff: 0, unadjRate: null, auditedDiff: 0, auditedRate: null,
      reason: '', isEditable: true,
    }))
  }

  // ─── Computed rows ─────────────────────────────────────────────────────

  const computedRows: ComputedRef<N4AdjRowV2[]> = computed(() => {
    return rows.value.map(row => {
      const priorAudited = row.priorUnadj + row.priorAje + row.priorRje
      const curAudited = row.curUnadj + row.curAje + row.curRje
      return {
        ...row,
        priorAudited, curAudited,
        unadjDiff: row.curUnadj - row.priorUnadj,
        unadjRate: calcYoyChange(row.curUnadj, row.priorUnadj),
        auditedDiff: curAudited - priorAudited,
        auditedRate: calcYoyChange(curAudited, priorAudited),
      }
    })
  })

  // ─── Total row ─────────────────────────────────────────────────────────

  const totalRow = computed(() => {
    const r = computedRows.value
    const priorUnadj = calcSubtotal(r.map(x => x.priorUnadj))
    const priorAje = calcSubtotal(r.map(x => x.priorAje))
    const priorRje = calcSubtotal(r.map(x => x.priorRje))
    const priorAudited = priorUnadj + priorAje + priorRje
    const curUnadj = calcSubtotal(r.map(x => x.curUnadj))
    const curAje = calcSubtotal(r.map(x => x.curAje))
    const curRje = calcSubtotal(r.map(x => x.curRje))
    const curAudited = curUnadj + curAje + curRje
    return {
      priorUnadj, priorAje, priorRje, priorAudited,
      curUnadj, curAje, curRje, curAudited,
      unadjDiff: curUnadj - priorUnadj,
      unadjRate: calcYoyChange(curUnadj, priorUnadj),
      auditedDiff: curAudited - priorAudited,
      auditedRate: calcYoyChange(curAudited, priorAudited),
    }
  })

  // ─── Cell update ───────────────────────────────────────────────────────

  type EditableField = 'curUnadj' | 'curAje' | 'curRje' | 'priorUnadj' | 'priorAje' | 'priorRje' | 'reason'

  function updateCell(rowKey: string, field: EditableField, value: number | string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalc(row)
    isChanged.value = true
    _persist()
  }

  function _recalc(row: N4AdjRowV2): void {
    row.priorAudited = row.priorUnadj + row.priorAje + row.priorRje
    row.curAudited = row.curUnadj + row.curAje + row.curRje
    row.unadjDiff = row.curUnadj - row.priorUnadj
    row.unadjRate = calcYoyChange(row.curUnadj, row.priorUnadj)
    row.auditedDiff = row.curAudited - row.priorAudited
    row.auditedRate = calcYoyChange(row.curAudited, row.priorAudited)
  }

  // ─── Dynamic rows ─────────────────────────────────────────────────────

  function addRow(taxType: string): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `custom-${Date.now()}`, taxType,
      priorUnadj: 0, priorAje: 0, priorRje: 0, priorAudited: 0,
      curUnadj: 0, curAje: 0, curRje: 0, curAudited: 0,
      unadjDiff: 0, unadjRate: null, auditedDiff: 0, auditedRate: null,
      reason: '', isEditable: true,
    })
    isChanged.value = true
    _persist()
  }

  function removeRow(rowKey: string): void {
    if (isReadonly?.value) return
    const idx = rows.value.findIndex(r => r.rowKey === rowKey)
    if (idx >= 0) { rows.value.splice(idx, 1); isChanged.value = true; _persist() }
  }

  // ─── Writeback TB ──────────────────────────────────────────────────────

  async function writeback(): Promise<void> {
    _persist()
    const auditedTotal = totalRow.value.curAudited
    onSave?.(TOTAL_KEY, auditedTotal)
    onSave?.(ADJ_AMOUNT_KEY, auditedTotal)
    if (writebackTB) await writebackTB(auditedTotal)
    isChanged.value = false
  }

  // ─── Persist ───────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    // 兼容旧 key（crossSheet / 附注 读 'N4-1-rows'）
    onSave(ROWS_KEY_LEGACY, rows.value)
  }

  function saveNote(note: string): void { auditNote.value = note; onSave?.(NOTE_KEY, note) }
  function saveConclusion(c: string): void { auditConclusion.value = c; onSave?.(CONCLUSION_KEY, c) }

  // ─── Watch ─────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  return {
    rows: computedRows,
    totalRow,
    auditNote,
    auditConclusion,
    isChanged,
    updateCell,
    addRow,
    removeRow,
    writeback,
    saveNote,
    saveConclusion,
    initFromResponses,
  }
}

export default useN4AdjudicationV2
