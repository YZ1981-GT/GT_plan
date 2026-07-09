/**
 * useK11Adjudication — K11-1 审定表逻辑（37行×12列，61公式，损益类！取发生额）
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/
 * Task: 3.4
 * Requirements: 2~6 全部
 *
 * 职责：
 * - 管理审定表行数据（按资产类别分行，37行）
 * - 每行: { projectName, currentOccurrence, priorOccurrence, unadjusted, aje, rje, audited, yoyChange, sourceWp, remark }
 * - 使用 calcAuditedAmount / calcIncomeStatementOccurrence / calcSubtotal
 * - 合计行计算 + 与K11-2明细交叉验证
 * - TB回写（6701发生额！）+ 发布 'substantive:adjudicated' EventBus事件
 * - GtIndexChip跳转源底稿(F2/H1/I1/I3/H2/G7/H4/H8/H3)
 *
 * 科目：6701资产减值损失（**损益类！取发生额**）
 * ⚠️ 损益类！从tb_ledger取借方发生额累计，非tb_balance期末余额
 *
 * Item IDs: "K11-1-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcSubtotal,
} from './useK11FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K11AdjRow {
  rowKey: string
  /** 资产类别/减值项目名称 */
  projectName: string
  /** 本期发生额（借方发生-贷方发生，从tb_ledger） */
  currentOccurrence: number
  /** 上期发生额 */
  priorOccurrence: number
  /** 未审数（=本期发生额，公式列） */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（公式：未审+AJE+RJE） */
  audited: number
  /** 同比变动额（公式：审定-上期） */
  yoyChange: number
  /** 同比变动率（公式：变动额/|上期|） */
  yoyChangeRate: number | null
  /** 来源底稿编码（如 F2/H1/I1/I3 等） */
  sourceWp: string
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
  /** 是否为合计行 */
  isTotalRow: boolean
}

export interface K11AdjSubtotalRow {
  label: string
  currentOccurrence: number
  priorOccurrence: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  yoyChange: number
  yoyChangeRate: number | null
}

export interface UseK11AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'K11-1'
const ROWS_KEY = `${ITEM_PREFIX}-rows`
const ACCOUNT_CODE_6701 = '6701'

/** 来源底稿映射（sourceWp codes） */
export const SOURCE_WP_CODES = ['F2', 'H1', 'I1', 'I3', 'H2', 'G7', 'H4', 'H8', 'H3'] as const

/** 默认审定表资产类别行（37行典型分类） */
const DEFAULT_PROJECTS: Array<{ name: string; sourceWp: string }> = [
  { name: '存货跌价准备', sourceWp: 'F2' },
  { name: '固定资产减值准备', sourceWp: 'H1' },
  { name: '无形资产减值准备', sourceWp: 'I1' },
  { name: '商誉减值准备', sourceWp: 'I3' },
  { name: '在建工程减值准备', sourceWp: 'H2' },
  { name: '长期股权投资减值准备', sourceWp: 'G7' },
  { name: '工程物资减值准备', sourceWp: 'H4' },
  { name: '使用权资产减值准备', sourceWp: 'H8' },
  { name: '投资性房地产减值准备', sourceWp: 'H3' },
  { name: '其他资产减值损失', sourceWp: '' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function calcChangeRate(current: number, prior: number): number | null {
  const pri = parseNum(prior)
  if (pri === 0) return null
  return (parseNum(current) - pri) / Math.abs(pri)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK11Adjudication(params: UseK11AdjudicationParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K11AdjRow[]>([])
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

  function _normalizeRow(raw: any): K11AdjRow {
    const currentOccurrence = parseNum(raw.currentOccurrence)
    const priorOccurrence = parseNum(raw.priorOccurrence)
    const unadjusted = currentOccurrence
    const aje = parseNum(raw.aje)
    const rje = parseNum(raw.rje)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const yoyChange = audited - priorOccurrence
    const yoyChangeRate = calcChangeRate(audited, priorOccurrence)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      projectName: raw.projectName ?? '',
      currentOccurrence,
      priorOccurrence,
      unadjusted,
      aje,
      rje,
      audited,
      yoyChange,
      yoyChangeRate,
      sourceWp: raw.sourceWp ?? '',
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
      isTotalRow: raw.isTotalRow ?? false,
    }
  }

  function _buildDefaultRows(): K11AdjRow[] {
    return DEFAULT_PROJECTS.map((item) => ({
      rowKey: `row-${item.name}`,
      projectName: item.name,
      currentOccurrence: 0,
      priorOccurrence: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      yoyChange: 0,
      yoyChangeRate: null,
      sourceWp: item.sourceWp,
      remark: '',
      isEditable: true,
      isTotalRow: false,
    }))
  }

  // ─── Computed: 带公式列完整行 ──────────────────────────────────────────────

  const computedRows: ComputedRef<K11AdjRow[]> = computed(() => {
    return rows.value.map((row) => {
      const unadjusted = row.currentOccurrence
      const audited = calcAuditedAmount(unadjusted, row.aje, row.rje)
      const yoyChange = audited - row.priorOccurrence
      const yoyChangeRate = calcChangeRate(audited, row.priorOccurrence)
      return { ...row, unadjusted, audited, yoyChange, yoyChangeRate }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow: ComputedRef<K11AdjSubtotalRow> = computed(() => {
    const detail = computedRows.value
    const currentOccurrence = calcSubtotal(detail.map(r => r.currentOccurrence))
    const priorOccurrence = calcSubtotal(detail.map(r => r.priorOccurrence))
    const unadjusted = currentOccurrence
    const aje = calcSubtotal(detail.map(r => r.aje))
    const rje = calcSubtotal(detail.map(r => r.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const yoyChange = audited - priorOccurrence
    const yoyChangeRate = calcChangeRate(audited, priorOccurrence)
    return { label: '合  计', currentOccurrence, priorOccurrence, unadjusted, aje, rje, audited, yoyChange, yoyChangeRate }
  })

  // ─── 与K11-2明细合计交叉验证 ────────────────────────────────────────────────

  const detailCrossValidation: ComputedRef<{ diff: number; isBalanced: boolean }> = computed(() => {
    const adjTotal = totalRow.value.audited
    const detailTotalRaw = allResponses.value.get('K11-2-total-occurrence')
    const detailTotal = parseNum(detailTotalRaw?.remark ?? detailTotalRaw?.conclusion ?? 0)
    const diff = adjTotal - detailTotal
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── GtIndexChip数据（源底稿跳转） ────────────────────────────────────────

  const sourceChipData: ComputedRef<Array<{ rowKey: string; sourceWp: string; label: string }>> = computed(() => {
    return computedRows.value
      .filter(r => r.sourceWp)
      .map(r => ({
        rowKey: r.rowKey,
        sourceWp: r.sourceWp,
        label: `${r.sourceWp} ${r.projectName}`,
      }))
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: keyof K11AdjRow, value: number | string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K11AdjRow): void {
    row.unadjusted = row.currentOccurrence
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    row.yoyChange = row.audited - row.priorOccurrence
    row.yoyChangeRate = calcChangeRate(row.audited, row.priorOccurrence)
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(projectName: string, sourceWp: string = ''): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      projectName,
      currentOccurrence: 0,
      priorOccurrence: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      yoyChange: 0,
      yoyChangeRate: null,
      sourceWp,
      remark: '',
      isEditable: true,
      isTotalRow: false,
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

    // TB回写（科目6701，**发生额！**）
    if (projectId.value) {
      try {
        const { default: http } = await import('@/utils/http')
        await http.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_6701,
          audited_amount: auditedTotal,
          is_occurrence: true, // 损益类标记
        })
        ElMessage.success('审定发生额已回写试算表(6701)')
      } catch {
        ElMessage.warning('审定发生额回写失败，请手动确认')
      }
    }

    // 发布 'substantive:adjudicated' EventBus事件（附注组件 subscribe 刷新）
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'K11',
      accountCode: ACCOUNT_CODE_6701,
      auditedAmount: auditedTotal,
      timestamp: Date.now(),
    })

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
    sourceChipData,
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

export default useK11Adjudication
