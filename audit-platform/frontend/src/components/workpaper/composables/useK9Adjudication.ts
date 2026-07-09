/**
 * useK9Adjudication — K9-1 审定表逻辑（44行×14列，73公式，损益类！取发生额）
 *
 * Spec: .kiro/specs/k9-admin-expenses/
 * Task: 3.4
 * Requirements: 2.1-2.7, 7.1-7.4, 9.1-9.2
 *
 * 职责：
 * - 管理审定表行数据（按费用明细项目分行，44行）
 * - 每行: { projectName, unadjustedDebit, unadjustedCredit, unadjusted, aje, rje, audited, priorAmount, yoyChange }
 * - 使用 calcAuditedAmount / calcIncomeStatementOccurrence / calcSubtotal
 * - 合计行计算 + 与K9-2明细交叉验证
 * - TB回写（6602发生额！）+ 发布 'substantive:adjudicated' EventBus事件
 *
 * 科目：6602管理费用（**损益类！取发生额**）
 * ⚠️ 损益类！从tb_ledger取借方发生额累计，非tb_balance期末余额
 *
 * Item IDs: "K9-1-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcSubtotal,
} from './useK9FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K9AdjRow {
  rowKey: string
  /** 费用项目名称 */
  projectName: string
  /** 本期借方发生（从tb_ledger取） */
  unadjustedDebit: number
  /** 本期贷方发生（红冲） */
  unadjustedCredit: number
  /** 本期未审数（净额：借方-贷方，公式列） */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（公式：未审+AJE+RJE） */
  audited: number
  /** 上期审定数 */
  priorAmount: number
  /** 同比变动额（公式：审定-上期审定） */
  yoyChange: number
  /** 同比变动率（公式：变动额/|上期|） */
  yoyChangeRate: number | null
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

export interface K9AdjSubtotalRow {
  label: string
  unadjustedDebit: number
  unadjustedCredit: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  priorAmount: number
  yoyChange: number
  yoyChangeRate: number | null
}

export interface UseK9AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'K9-1'
const ROWS_KEY = `${ITEM_PREFIX}-rows`
const ACCOUNT_CODE_6602 = '6602'

/** 默认费用明细项目（管理费用典型44行中的重要项目） */
const DEFAULT_PROJECTS = [
  '职工薪酬', '办公费', '折旧费', '无形资产摊销', '长期待摊费用摊销',
  '中介机构费', '研发费用', '税金', '差旅费', '业务招待费',
  '租赁费', '通讯费', '物业管理费', '修理费', '保险费',
  '水电费', '会议费', '培训费', '劳动保护费', '运输费',
  '低值易耗品', '绿化费', '聘请专家费', '诉讼费', '其他',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function calcChangeRate(current: number, prior: number): number | null {
  const pri = parseNum(prior)
  if (pri === 0) return null
  return (parseNum(current) - pri) / Math.abs(pri)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK9Adjudication(params: UseK9AdjudicationParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K9AdjRow[]>([])
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

  function _normalizeRow(raw: any): K9AdjRow {
    const unadjustedDebit = parseNum(raw.unadjustedDebit)
    const unadjustedCredit = parseNum(raw.unadjustedCredit)
    const unadjusted = calcIncomeStatementOccurrence(unadjustedDebit, unadjustedCredit)
    const aje = parseNum(raw.aje)
    const rje = parseNum(raw.rje)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const priorAmount = parseNum(raw.priorAmount)
    const yoyChange = audited - priorAmount
    const yoyChangeRate = calcChangeRate(audited, priorAmount)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      projectName: raw.projectName ?? '',
      unadjustedDebit, unadjustedCredit, unadjusted,
      aje, rje, audited, priorAmount, yoyChange, yoyChangeRate,
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  function _buildDefaultRows(): K9AdjRow[] {
    return DEFAULT_PROJECTS.map((name) => ({
      rowKey: `row-${name}`,
      projectName: name,
      unadjustedDebit: 0, unadjustedCredit: 0, unadjusted: 0,
      aje: 0, rje: 0, audited: 0,
      priorAmount: 0, yoyChange: 0, yoyChangeRate: null,
      remark: '', isEditable: true,
    }))
  }

  // ─── Computed: 带公式列完整行 ──────────────────────────────────────────────

  const computedRows: ComputedRef<K9AdjRow[]> = computed(() => {
    return rows.value.map((row) => {
      const unadjusted = calcIncomeStatementOccurrence(row.unadjustedDebit, row.unadjustedCredit)
      const audited = calcAuditedAmount(unadjusted, row.aje, row.rje)
      const yoyChange = audited - row.priorAmount
      const yoyChangeRate = calcChangeRate(audited, row.priorAmount)
      return { ...row, unadjusted, audited, yoyChange, yoyChangeRate }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow: ComputedRef<K9AdjSubtotalRow> = computed(() => {
    const detail = computedRows.value
    const unadjustedDebit = calcSubtotal(detail.map(r => r.unadjustedDebit))
    const unadjustedCredit = calcSubtotal(detail.map(r => r.unadjustedCredit))
    const unadjusted = calcIncomeStatementOccurrence(unadjustedDebit, unadjustedCredit)
    const aje = calcSubtotal(detail.map(r => r.aje))
    const rje = calcSubtotal(detail.map(r => r.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const priorAmount = calcSubtotal(detail.map(r => r.priorAmount))
    const yoyChange = audited - priorAmount
    const yoyChangeRate = calcChangeRate(audited, priorAmount)
    return { label: '合  计', unadjustedDebit, unadjustedCredit, unadjusted, aje, rje, audited, priorAmount, yoyChange, yoyChangeRate }
  })

  // ─── 与K9-2明细合计交叉验证 ────────────────────────────────────────────────

  const detailCrossValidation: ComputedRef<{ diff: number; isBalanced: boolean }> = computed(() => {
    const adjTotal = totalRow.value.audited
    const detailTotalRaw = allResponses.value.get('K9-2-detail-audited-total')
    const detailTotal = parseNum(detailTotalRaw?.remark ?? detailTotalRaw?.conclusion ?? 0)
    const diff = adjTotal - detailTotal
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: keyof K9AdjRow, value: number | string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K9AdjRow): void {
    row.unadjusted = calcIncomeStatementOccurrence(row.unadjustedDebit, row.unadjustedCredit)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    row.yoyChange = row.audited - row.priorAmount
    row.yoyChangeRate = calcChangeRate(row.audited, row.priorAmount)
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(projectName: string): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      projectName,
      unadjustedDebit: 0, unadjustedCredit: 0, unadjusted: 0,
      aje: 0, rje: 0, audited: 0,
      priorAmount: 0, yoyChange: 0, yoyChangeRate: null,
      remark: '', isEditable: true,
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

    // TB回写（科目6602，**发生额！**）
    if (projectId.value) {
      try {
        const { default: http } = await import('@/utils/http')
        await http.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_6602,
          audited_amount: auditedTotal,
          is_occurrence: true, // 损益类标记
        })
        ElMessage.success('审定发生额已回写试算表(6602)')
      } catch {
        ElMessage.warning('审定发生额回写失败，请手动确认')
      }
    }

    // 发布 'substantive:adjudicated' EventBus事件（mitt eventBus，附注组件 subscribe 刷新）
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'K9',
      accountCode: ACCOUNT_CODE_6602,
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

export default useK9Adjudication
