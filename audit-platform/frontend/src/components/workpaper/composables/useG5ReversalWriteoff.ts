/**
 * useG5ReversalWriteoff — G5-11 减值准备转回（收回）、核销检查
 *
 * 对齐纸质底稿：
 *   （一）本期重要转回/收回检查  （二）本期重要核销检查
 * 校验：转回 ≤ 累计计提；核销须审批完整；关联方高亮
 */
import { ref, computed } from 'vue'
import { parseNum, isReversalValid } from '@/composables/useG5FormulaEngine'

export type YesNo = '是' | '否' | ''

/** 合理性分析检查项 */
export interface ReasonablenessItem {
  id: string
  label: string
  result: YesNo | '不适用'
  note: string
}

export interface ReversalRow {
  id: string
  seq: number
  /** 单位名称 */
  debtor: string
  /** 转回原因 */
  reason: string
  /** 收回方式 */
  recoveryMethod: string
  /** 原确定减值准备的依据 */
  originalBasis: string
  /** 收回或转回金额 */
  reversalAmount: number
  /** 转回前累计已计提减值准备 */
  accumulatedProvision: number
  /** 合理性分析（文字结论） */
  reasonableness: string
  /** 结构化检查项 */
  checks: ReasonablenessItem[]
  isRelatedParty: boolean
  isValid: boolean
  indexRef: string
}

export interface WriteoffRow {
  id: string
  seq: number
  debtor: string
  /** 长期应收款的性质 */
  nature: string
  writeoffAmount: number
  /** 核销原因 */
  reason: string
  /** 履行的核销程序 */
  procedures: string
  /** 审批状态（兼容旧字段） */
  approvalStatus: string
  /** 是否由关联交易产生 */
  isRelatedParty: boolean
  reasonableness: string
  checks: ReasonablenessItem[]
  /** 审批是否完整（由 checks / procedures 推导，可手改） */
  approvalComplete: boolean
  indexRef: string
}

export const REVERSAL_CHECK_DEFS: { id: string; label: string }[] = [
  { id: 'r1', label: '转回/收回金额不超过转回前累计已计提减值准备' },
  { id: 'r2', label: '转回原因充分（信用风险改善或款项实际收回等）' },
  { id: 'r3', label: '与原确定减值准备的依据逻辑一致，非任意转回' },
  { id: 'r4', label: '收回方式可验证（银行回单/抵债资产/债务重组等）' },
  { id: 'r5', label: '非通过关联交易不当调节利润' },
]

export const WRITEOFF_CHECK_DEFS: { id: string; label: string }[] = [
  { id: 'w1', label: '已履行内部核销审批程序并取得有效批准文件' },
  { id: 'w2', label: '核销原因充分（债务人破产/注销/无法收回等）' },
  { id: 'w3', label: '核销金额与账面减值/应收余额匹配' },
  { id: 'w4', label: '关联交易核销已单独识别并充分披露关注' },
  { id: 'w5', label: '已建立核销后备查/后续追偿安排（如适用）' },
]

function createChecks(defs: { id: string; label: string }[], saved?: ReasonablenessItem[]): ReasonablenessItem[] {
  const byId = new Map((saved || []).map(c => [c.id, c]))
  return defs.map(d => {
    const prev = byId.get(d.id)
    return {
      id: d.id,
      label: d.label,
      result: (prev?.result || '') as ReasonablenessItem['result'],
      note: prev?.note || '',
    }
  })
}

export function emptyReversalRow(partial?: Partial<ReversalRow>): ReversalRow {
  const { checks: savedChecks, ...rest } = partial || {}
  const row: ReversalRow = {
    id: crypto.randomUUID(),
    seq: 0,
    debtor: '',
    reason: '',
    recoveryMethod: '',
    originalBasis: '',
    reversalAmount: 0,
    accumulatedProvision: 0,
    reasonableness: '',
    checks: createChecks(REVERSAL_CHECK_DEFS, savedChecks),
    isRelatedParty: false,
    isValid: true,
    indexRef: '',
    ...rest,
  }
  // 防止 rest 里残留空 checks
  row.checks = createChecks(REVERSAL_CHECK_DEFS, savedChecks)
  row.isValid = isReversalValid(row.reversalAmount, row.accumulatedProvision)
  return row
}

export function emptyWriteoffRow(partial?: Partial<WriteoffRow>): WriteoffRow {
  const { checks: savedChecks, approvalComplete, ...rest } = partial || {}
  const row: WriteoffRow = {
    id: crypto.randomUUID(),
    seq: 0,
    debtor: '',
    nature: '',
    writeoffAmount: 0,
    reason: '',
    procedures: '',
    approvalStatus: '',
    isRelatedParty: false,
    reasonableness: '',
    checks: createChecks(WRITEOFF_CHECK_DEFS, savedChecks),
    approvalComplete: false,
    indexRef: '',
    ...rest,
  }
  row.checks = createChecks(WRITEOFF_CHECK_DEFS, savedChecks)
  row.approvalComplete = approvalComplete === undefined
    ? inferApprovalComplete(row)
    : !!approvalComplete
  return row
}

export function inferApprovalComplete(row: WriteoffRow): boolean {
  const w1 = row.checks?.find(c => c.id === 'w1')?.result
  if (w1 === '是') return true
  if (w1 === '否') return false
  const status = (row.approvalStatus || row.procedures || '').trim()
  if (!status) return false
  return /已审批|已批准|完整|通过|批准/.test(status)
}

export function summarizeChecks(checks: ReasonablenessItem[]): string {
  const answered = checks.filter(c => c.result)
  if (!answered.length) return ''
  return answered.map(c => `${c.label}：${c.result}${c.note ? `（${c.note}）` : ''}`).join('；')
}

function migrateReversal(raw: any, index: number): ReversalRow {
  return emptyReversalRow({
    id: raw?.id || crypto.randomUUID(),
    seq: index + 1,
    debtor: raw?.debtor || raw?.entityName || '',
    reason: raw?.reason || '',
    recoveryMethod: raw?.recoveryMethod || '',
    originalBasis: raw?.originalBasis || '',
    reversalAmount: parseNum(raw?.reversalAmount),
    accumulatedProvision: parseNum(raw?.accumulatedProvision),
    reasonableness: raw?.reasonableness || '',
    checks: raw?.checks,
    isRelatedParty: !!raw?.isRelatedParty,
    indexRef: raw?.indexRef || '',
  })
}

function migrateWriteoff(raw: any, index: number): WriteoffRow {
  return emptyWriteoffRow({
    id: raw?.id || crypto.randomUUID(),
    seq: index + 1,
    debtor: raw?.debtor || raw?.entityName || '',
    nature: raw?.nature || '',
    writeoffAmount: parseNum(raw?.writeoffAmount),
    reason: raw?.reason || '',
    procedures: raw?.procedures || raw?.approvalStatus || '',
    approvalStatus: raw?.approvalStatus || '',
    isRelatedParty: !!raw?.isRelatedParty,
    reasonableness: raw?.reasonableness || '',
    checks: raw?.checks,
    approvalComplete: raw?.approvalComplete,
    indexRef: raw?.indexRef || '',
  })
}

export function useG5ReversalWriteoff() {
  const reversalRows = ref<ReversalRow[]>([])
  const writeoffRows = ref<WriteoffRow[]>([])
  const activeTab = ref<'reversal' | 'writeoff'>('reversal')
  const activeRowIndex = ref(0)

  function recalcReversal(row: ReversalRow): void {
    row.isValid = isReversalValid(row.reversalAmount, row.accumulatedProvision)
    // 同步 r1 检查项
    const r1 = row.checks.find(c => c.id === 'r1')
    if (r1 && !r1.result) {
      r1.result = row.isValid ? '是' : '否'
    } else if (r1 && (r1.result === '是' || r1.result === '否')) {
      r1.result = row.isValid ? '是' : '否'
    }
  }

  function recalculateWriteoff(row: WriteoffRow): void {
    row.approvalComplete = inferApprovalComplete(row)
  }

  function renumber(): void {
    reversalRows.value.forEach((r, i) => { r.seq = i + 1 })
    writeoffRows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function addReversalRow(seed?: Partial<ReversalRow>): ReversalRow {
    const row = emptyReversalRow({ ...seed, seq: reversalRows.value.length + 1 })
    recalcReversal(row)
    reversalRows.value.push(row)
    renumber()
    return row
  }

  function addWriteoffRow(seed?: Partial<WriteoffRow>): WriteoffRow {
    const row = emptyWriteoffRow({ ...seed, seq: writeoffRows.value.length + 1 })
    writeoffRows.value.push(row)
    renumber()
    return row
  }

  function removeReversalRow(id: string): void {
    reversalRows.value = reversalRows.value.filter(r => r.id !== id)
    renumber()
  }

  function removeWriteoffRow(id: string): void {
    writeoffRows.value = writeoffRows.value.filter(r => r.id !== id)
    renumber()
  }

  function upsertReversal(next: ReversalRow): void {
    recalcReversal(next)
    if (!next.reasonableness) next.reasonableness = summarizeChecks(next.checks)
    const idx = reversalRows.value.findIndex(r => r.id === next.id)
    if (idx >= 0) reversalRows.value[idx] = next
    else reversalRows.value.push(next)
    renumber()
  }

  function upsertWriteoff(next: WriteoffRow): void {
    recalculateWriteoff(next)
    if (!next.reasonableness) next.reasonableness = summarizeChecks(next.checks)
    if (!next.procedures && next.approvalStatus) next.procedures = next.approvalStatus
    const idx = writeoffRows.value.findIndex(r => r.id === next.id)
    if (idx >= 0) writeoffRows.value[idx] = next
    else writeoffRows.value.push(next)
    renumber()
  }

  const invalidReversals = computed(() => reversalRows.value.filter(r => !r.isValid))
  const incompleteWriteoffs = computed(() =>
    writeoffRows.value.filter(r => parseNum(r.writeoffAmount) > 0 && !r.approvalComplete),
  )
  const relatedReversals = computed(() => reversalRows.value.filter(r => r.isRelatedParty))
  const relatedWriteoffs = computed(() => writeoffRows.value.filter(r => r.isRelatedParty))

  const totals = computed(() => ({
    reversalAmount: reversalRows.value.reduce((s, r) => s + parseNum(r.reversalAmount), 0),
    accumulatedProvision: reversalRows.value.reduce((s, r) => s + parseNum(r.accumulatedProvision), 0),
    writeoffAmount: writeoffRows.value.reduce((s, r) => s + parseNum(r.writeoffAmount), 0),
  }))

  function loadReversalRows(data: ReversalRow[] | any[]): void {
    reversalRows.value = (data || []).map((r, i) => migrateReversal(r, i))
  }

  function loadWriteoffRows(data: WriteoffRow[] | any[]): void {
    writeoffRows.value = (data || []).map((r, i) => migrateWriteoff(r, i))
  }

  return {
    reversalRows,
    writeoffRows,
    activeTab,
    activeRowIndex,
    recalcReversal,
    recalculateWriteoff,
    addReversalRow,
    addWriteoffRow,
    removeReversalRow,
    removeWriteoffRow,
    upsertReversal,
    upsertWriteoff,
    invalidReversals,
    incompleteWriteoffs,
    relatedReversals,
    relatedWriteoffs,
    totals,
    loadReversalRows,
    loadWriteoffRows,
  }
}
