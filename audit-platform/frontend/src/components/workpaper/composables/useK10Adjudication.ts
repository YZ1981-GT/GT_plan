/**
 * useK10Adjudication — K10-1 审定表逻辑（损益类69公式+发生额取数+按来源分行+TB回写）
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 3.4
 * Requirements: 2~7 全部
 *
 * 职责：
 * - 管理审定表行数据（按收益来源分行：政府补助-即征即退/财政贴息/研发补助/稳岗补贴/其他）
 * - 每行: { name, unadjusted, aje, rje, audited(computed), priorUnadj, priorAje, priorRje, priorAudited(computed), yoyChange(computed), remark }
 * - 使用 calcAuditedAmount / calcYoYChange / calcSubtotal from useK10FormulaEngine
 * - 合计行计算 + 与K10-2明细合计交叉验证
 * - TB回写（6117发生额！）+ 发布 'substantive:adjudicated' EventBus事件
 *
 * 科目：6117其他收益（**损益类/贷方科目**）
 * ⚠️ 损益类！取发生额非余额！6117贷方科目：贷方=收益增加，借方=收益冲回
 *
 * Item IDs: "K10-1-rows", "K10-1-audited-total", "K10-1-audit-note", "K10-1-audit-conclusion"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcYoYChange,
  calcSubtotal,
} from './useK10FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K10AdjRow {
  rowKey: string
  /** 项目名称（收益来源） */
  name: string
  /** 本期未审数 */
  unadjusted: number
  /** 本期AJE调整 */
  aje: number
  /** 本期RJE重分类 */
  rje: number
  /** 本期审定数（公式：未审+AJE+RJE） */
  audited: number
  /** 上期未审数 */
  priorUnadj: number
  /** 上期AJE */
  priorAje: number
  /** 上期RJE */
  priorRje: number
  /** 上期审定数（公式：上期未审+上期AJE+上期RJE） */
  priorAudited: number
  /** 同比变动率（公式：(本期审定-上期审定)/|上期审定|）*/
  yoyChange: number | null
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

export interface K10AdjSubtotalRow {
  label: string
  unadjusted: number
  aje: number
  rje: number
  audited: number
  priorUnadj: number
  priorAje: number
  priorRje: number
  priorAudited: number
  yoyChange: number | null
}

export interface UseK10AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
  /** writebackTB from useK10FormData */
  writebackTB?: (auditedAmount: number) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'K10-1'
const ROWS_KEY = `${ITEM_PREFIX}-rows`

/** 默认审定表收益来源行（其他收益5大类：政府补助细分） */
const DEFAULT_INCOME_SOURCES: Array<{ name: string }> = [
  { name: '政府补助-即征即退' },
  { name: '政府补助-财政贴息' },
  { name: '政府补助-研发补助' },
  { name: '政府补助-稳岗补贴' },
  { name: '其他' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK10Adjudication(params: UseK10AdjudicationParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave, writebackTB } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K10AdjRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      rows.value = raw.map(_normalizeRow)
    } else {
      rows.value = _buildDefaultRows()
    }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
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

  function _normalizeRow(raw: any): K10AdjRow {
    const unadjusted = parseNum(raw.unadjusted)
    const aje = parseNum(raw.aje)
    const rje = parseNum(raw.rje)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const priorUnadj = parseNum(raw.priorUnadj)
    const priorAje = parseNum(raw.priorAje)
    const priorRje = parseNum(raw.priorRje)
    const priorAudited = calcAuditedAmount(priorUnadj, priorAje, priorRje)
    const yoyChange = calcYoYChange(audited, priorAudited)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      name: raw.name ?? '',
      unadjusted,
      aje,
      rje,
      audited,
      priorUnadj,
      priorAje,
      priorRje,
      priorAudited,
      yoyChange,
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  function _buildDefaultRows(): K10AdjRow[] {
    return DEFAULT_INCOME_SOURCES.map((item) => ({
      rowKey: `row-${item.name}`,
      name: item.name,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      priorUnadj: 0,
      priorAje: 0,
      priorRje: 0,
      priorAudited: 0,
      yoyChange: null,
      remark: '',
      isEditable: true,
    }))
  }

  // ─── Computed: 带公式列完整行 ──────────────────────────────────────────────

  const computedRows: ComputedRef<K10AdjRow[]> = computed(() => {
    return rows.value.map((row) => {
      const audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
      const priorAudited = calcAuditedAmount(row.priorUnadj, row.priorAje, row.priorRje)
      const yoyChange = calcYoYChange(audited, priorAudited)
      return { ...row, audited, priorAudited, yoyChange }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow: ComputedRef<K10AdjSubtotalRow> = computed(() => {
    const detail = computedRows.value
    const unadjusted = calcSubtotal(detail.map(r => r.unadjusted))
    const aje = calcSubtotal(detail.map(r => r.aje))
    const rje = calcSubtotal(detail.map(r => r.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const priorUnadj = calcSubtotal(detail.map(r => r.priorUnadj))
    const priorAje = calcSubtotal(detail.map(r => r.priorAje))
    const priorRje = calcSubtotal(detail.map(r => r.priorRje))
    const priorAudited = calcAuditedAmount(priorUnadj, priorAje, priorRje)
    const yoyChange = calcYoYChange(audited, priorAudited)
    return { label: '合  计', unadjusted, aje, rje, audited, priorUnadj, priorAje, priorRje, priorAudited, yoyChange }
  })

  // ─── 与K10-2明细合计交叉验证 ────────────────────────────────────────────────

  const detailCrossValidation: ComputedRef<{ diff: number; isBalanced: boolean }> = computed(() => {
    const adjTotal = totalRow.value.audited
    const detailTotalRaw = allResponses.value.get('K10-2-subtotal')
    const detailTotal = parseNum(detailTotalRaw?.remark ?? detailTotalRaw?.conclusion ?? 0)
    const diff = adjTotal - detailTotal
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: keyof K10AdjRow, value: number | string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K10AdjRow): void {
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    row.priorAudited = calcAuditedAmount(row.priorUnadj, row.priorAje, row.priorRje)
    row.yoyChange = calcYoYChange(row.audited, row.priorAudited)
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(name: string): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      priorUnadj: 0,
      priorAje: 0,
      priorRje: 0,
      priorAudited: 0,
      yoyChange: null,
      remark: '',
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

  // ─── TB回写 + EventBus（损益类发生额！6117）────────────────────────────────

  async function writeback(): Promise<void> {
    _persist()
    const auditedTotal = totalRow.value.audited

    // 持久化审定合计（独立item_id，供CrossSheet+render策略回读）
    onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    // 调用 useK10FormData 的 writebackTB（发生额回写6117）
    if (writebackTB) {
      await writebackTB(auditedTotal)
    }

    isChanged.value = false
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  function getAuditedTotal(): number {
    return totalRow.value.audited
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    totalRow,
    auditNote,
    auditConclusion,
    isChanged,
    detailCrossValidation,
    updateCell,
    addRow,
    removeRow,
    writeback,
    saveNote,
    saveConclusion,
    getAuditedTotal,
    initFromResponses,
  }
}

export default useK10Adjudication
