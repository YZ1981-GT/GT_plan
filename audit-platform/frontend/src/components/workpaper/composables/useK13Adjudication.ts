/**
 * useK13Adjudication — K13-1 审定表逻辑（损益类69公式+发生额取数+按去向分行+TB回写）
 *
 * Spec: .kiro/specs/k13-non-operating-expense/
 * Task: 4.2
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理审定表行数据（按去向分行：非流动资产处置损失/债务重组损失/资产盘亏损失/捐赠支出/罚款滞纳金/其他）
 * - 每行: { name, unadjusted, aje, rje, audited(computed), priorUnadj, priorAje, priorRje, priorAudited(computed), yoyChange(computed), remark }
 * - 使用 calcAuditedAmount / calcYoYChange / calcSubtotal from useK13FormulaEngine
 * - 合计行计算 + 与K13-2明细合计交叉验证
 * - TB回写（6711发生额！）+ 发布 'substantive:adjudicated' EventBus事件
 *
 * 科目：6711营业外支出（**损益类/借方科目**）
 * ⚠️ 损益类！取发生额非余额！6711借方科目：借方=支出增加，贷方=支出冲回
 *
 * Item IDs: "K13-1-rows", "K13-1-audited-total", "K13-1-audit-note", "K13-1-audit-conclusion"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcYoYChange,
  calcSubtotal,
} from './useK13FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K13AdjRow {
  rowKey: string
  /** 项目名称（支出去向） */
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

export interface K13AdjSubtotalRow {
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

export interface UseK13AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
  /** writebackTB from parent (GtK13NonOperatingExpense) */
  writebackTB?: (auditedAmount: number) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'K13-1'
const ROWS_KEY = `${ITEM_PREFIX}-rows`

/** 默认审定表支出去向行（营业外支出6大类） */
const DEFAULT_EXPENSE_CATEGORIES: Array<{ name: string }> = [
  { name: '非流动资产处置损失' },
  { name: '债务重组损失' },
  { name: '资产盘亏损失' },
  { name: '捐赠支出' },
  { name: '罚款滞纳金' },
  { name: '其他' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK13Adjudication(params: UseK13AdjudicationParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave, writebackTB } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K13AdjRow[]>([])
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

  function _normalizeRow(raw: any): K13AdjRow {
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

  function _buildDefaultRows(): K13AdjRow[] {
    return DEFAULT_EXPENSE_CATEGORIES.map((item) => ({
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

  const computedRows: ComputedRef<K13AdjRow[]> = computed(() => {
    return rows.value.map((row) => {
      const audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
      const priorAudited = calcAuditedAmount(row.priorUnadj, row.priorAje, row.priorRje)
      const yoyChange = calcYoYChange(audited, priorAudited)
      return { ...row, audited, priorAudited, yoyChange }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow: ComputedRef<K13AdjSubtotalRow> = computed(() => {
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

  // ─── 与K13-2明细合计交叉验证 ────────────────────────────────────────────────

  const detailCrossValidation: ComputedRef<{ diff: number; isBalanced: boolean }> = computed(() => {
    const adjTotal = totalRow.value.audited
    const detailTotalRaw = allResponses.value.get('K13-2-subtotal')
    const detailTotal = parseNum(detailTotalRaw?.remark ?? detailTotalRaw?.conclusion ?? 0)
    const diff = adjTotal - detailTotal
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: keyof K13AdjRow, value: number | string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K13AdjRow): void {
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

  // ─── TB回写 + EventBus（损益类发生额！）────────────────────────────────────

  async function writeback(): Promise<void> {
    _persist()
    const auditedTotal = totalRow.value.audited

    // 持久化审定合计（独立item_id，供CrossSheet+render策略回读）
    onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    // 调用父级 writebackTB（发生额回写6711）
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
