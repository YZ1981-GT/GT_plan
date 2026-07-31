/**
 * useN4Adjudication — N4-1 审定表逻辑（损益类83公式+发生额取数+10税种行+TB回写）
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/
 * Task: 3.3
 * Requirements: 2~5 全部
 *
 * 职责：
 * - 管理审定表行数据（10个税种行：消费税/城建税/教育费附加/地方教育附加/房产税/土地使用税/车船税/印花税/资源税/其他）
 * - 每行: { taxType, unadjusted, aje, rje, audited(computed), prior, yoyChange(computed) }
 * - 使用 calcAuditedAmount / calcYoyChange / calcSubtotal from useN4FormulaEngine
 * - 合计行计算 + 与N4-2明细合计交叉验证
 * - TB回写（6403发生额！）+ 发布 'substantive:adjudicated' EventBus事件
 * - 审计结论/说明状态
 *
 * 科目：6403 税金及附加（**损益类/借方科目**）
 * ⚠️ 损益类！取发生额非余额！6403借方科目：借方=费用增加，贷方=费用冲回
 *
 * Item IDs: "N4-1-rows", "N4-1-audited-total", "N4-1-audit-note", "N4-1-audit-conclusion"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcYoyChange,
  calcSubtotal,
} from './useN4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface N4AdjRow {
  rowKey: string
  /** 税种名称 */
  taxType: string
  /** 本期未审数（发生额） */
  unadjusted: number
  /** 本期AJE调整 */
  aje: number
  /** 本期RJE重分类 */
  rje: number
  /** 本期审定数（公式：未审+AJE+RJE） */
  audited: number
  /** 上期审定数 */
  prior: number
  /** 同比变动率（公式：(本期审定-上期审定)/|上期审定|）*/
  yoyChange: number | null
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

export interface N4AdjSubtotalRow {
  label: string
  unadjusted: number
  aje: number
  rje: number
  audited: number
  prior: number
  yoyChange: number | null
}

export interface UseN4AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
  /** writebackTB from useN4FormData */
  writebackTB?: (auditedAmount: number) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'N4-1'
const ROWS_KEY = `${ITEM_PREFIX}-rows`

/** 默认审定表10税种行 */
// 默认审定表税种行。命名与顺序沿用 N4 模块全局约定（城镇土地使用税/车船税），
// 须与 useN4Detail / useN4CrossSheet(N2 勾稽按名匹配) / 附注三处保持一致，切勿单独改名或改序。
// 覆盖源模板 N4-1 全部税种（消费税/城市维护建设税/教育费附加/资源税/房产税/土地使用税/车船使用税/印花税）+ 地方教育附加。
const DEFAULT_TAX_TYPES: Array<{ taxType: string }> = [
  { taxType: '消费税' },
  { taxType: '城市维护建设税' },
  { taxType: '教育费附加' },
  { taxType: '地方教育附加' },
  { taxType: '房产税' },
  { taxType: '城镇土地使用税' },
  { taxType: '车船税' },
  { taxType: '印花税' },
  { taxType: '资源税' },
  { taxType: '其他' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN4Adjudication(params: UseN4AdjudicationParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave, writebackTB } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<N4AdjRow[]>([])
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

  function _normalizeRow(raw: any): N4AdjRow {
    const unadjusted = parseNum(raw.unadjusted)
    const aje = parseNum(raw.aje)
    const rje = parseNum(raw.rje)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const prior = parseNum(raw.prior)
    const yoyChange = calcYoyChange(audited, prior)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      taxType: raw.taxType ?? '',
      unadjusted,
      aje,
      rje,
      audited,
      prior,
      yoyChange,
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  function _buildDefaultRows(): N4AdjRow[] {
    return DEFAULT_TAX_TYPES.map((item) => ({
      rowKey: `row-${item.taxType}`,
      taxType: item.taxType,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      prior: 0,
      yoyChange: null,
      remark: '',
      isEditable: true,
    }))
  }

  // ─── 四表库带入未审数 ──────────────────────────────────────────────────────

  /**
   * 从四表库带入未审数（本期发生额）。
   *
   * 数据来源优先级：
   * 1. `adjudication_prefill`（后端按 6403 **叶子子科目名称**归入 10 个税种行）——
   *    活体实测编码语义在客户间冲突（`6403.01` 某客户是印花税），故按名称判据。
   * 2. 无子科目时用 `tb_values.audited_amount` 总额落「其他」行，并由界面提示需人工分配。
   *
   * 🔴 只填空不覆盖：目标行 `unadjusted` 已非 0 时一律保留（手工优先）。
   *
   * @returns `{ filled, total, byTaxType }` 供调用方提示
   */
  function pullFromTB(source: {
    prefill?: Record<string, number> | null
    totalAmount?: number
  }): { filled: number; total: number; byTaxType: boolean } {
    const prefill = source.prefill || {}
    const hasPrefill = Object.keys(prefill).length > 0
    let filled = 0
    let total = 0

    if (hasPrefill) {
      rows.value = rows.value.map((r) => {
        const amount = parseNum(prefill[r.taxType])
        if (!amount) return r
        total += amount
        if (parseNum(r.unadjusted) !== 0) return r // 手工优先
        filled += 1
        return { ...r, unadjusted: amount }
      })
    } else {
      const amount = parseNum(source.totalAmount)
      if (amount) {
        total = amount
        const idx = rows.value.findIndex((r) => r.taxType === '其他')
        if (idx >= 0 && parseNum(rows.value[idx].unadjusted) === 0) {
          const next = [...rows.value]
          next[idx] = { ...next[idx], unadjusted: amount }
          rows.value = next
          filled = 1
        }
      }
    }

    if (filled > 0) {
      for (const r of rows.value) _recalcRow(r)
      isChanged.value = true
      _persist()
    }
    return { filled, total: Math.round(total * 100) / 100, byTaxType: hasPrefill }
  }

  /** 审定表是否已有任何录入（供 seed 守卫；避免覆盖已编制内容） */
  function hasAnyInput(): boolean {
    return rows.value.some(
      (r) => parseNum(r.unadjusted) !== 0 || parseNum(r.aje) !== 0 || parseNum(r.rje) !== 0,
    )
  }

  // ─── Computed: 带公式列完整行 ──────────────────────────────────────────────

  const computedRows: ComputedRef<N4AdjRow[]> = computed(() => {
    return rows.value.map((row) => {
      const audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
      const yoyChange = calcYoyChange(audited, row.prior)
      return { ...row, audited, yoyChange }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow: ComputedRef<N4AdjSubtotalRow> = computed(() => {
    const detail = computedRows.value
    const unadjusted = calcSubtotal(detail.map(r => r.unadjusted))
    const aje = calcSubtotal(detail.map(r => r.aje))
    const rje = calcSubtotal(detail.map(r => r.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const prior = calcSubtotal(detail.map(r => r.prior))
    const yoyChange = calcYoyChange(audited, prior)
    return { label: '合  计', unadjusted, aje, rje, audited, prior, yoyChange }
  })

  // ─── 与N4-2明细合计交叉验证 ────────────────────────────────────────────────

  const detailCrossValidation: ComputedRef<{ diff: number; isBalanced: boolean }> = computed(() => {
    const adjTotal = totalRow.value.audited
    const detailTotalRaw = allResponses.value.get('N4-2-subtotal')
    const detailTotal = parseNum(detailTotalRaw?.remark ?? detailTotalRaw?.conclusion ?? 0)
    const diff = adjTotal - detailTotal
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: keyof N4AdjRow, value: number | string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: N4AdjRow): void {
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    row.yoyChange = calcYoyChange(row.audited, row.prior)
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(taxType: string): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      taxType,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      prior: 0,
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

  // ─── TB回写 + EventBus（损益类发生额！6403）────────────────────────────────

  async function writeback(): Promise<void> {
    _persist()
    const auditedTotal = totalRow.value.audited

    // 持久化审定合计（独立item_id，供CrossSheet+render策略回读）
    onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    // 调用 useN4FormData 的 writebackTB（发生额回写6403）
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
    pullFromTB,
    hasAnyInput,
    DEFAULT_TAX_TYPES,
  }
}

export { DEFAULT_TAX_TYPES as N4_DEFAULT_TAX_TYPES }

export default useN4Adjudication
