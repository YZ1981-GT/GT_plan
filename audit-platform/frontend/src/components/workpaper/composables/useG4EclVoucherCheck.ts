/**
 * useG4EclVoucherCheck — G4-13 凭证检查表 composable
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/
 * Task: 9.2
 *
 * 职责：
 * - 借贷平衡实时校验（调用 isDebitCreditBalanced + calcDebitCreditDifference）
 * - 凭证异常判定（调用 isVoucherNormal）
 * - 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：一个对方科目一行
 *   （后端配对），按分录指纹去重，行元数据 `_gt` 随行 JSON 落库（spec voucher-identity-writeback-and-audit-phase 任务 11）
 * - 行CRUD（addRow / removeRow 含 ElMessageBox.prompt）
 * - 数据持久化（loadRows / toJSON）
 *
 * Requirements: 6.6, 6.7
 */
import { newUuid } from '@/utils/uuid'
import { ref, computed, type MaybeRefOrGetter } from 'vue'
import {
  isDebitCreditBalanced,
  calcDebitCreditDifference,
  isVoucherNormal,
  calcSumColumn,
} from '@/composables/useG4EclFormulaEngine'
import { ElMessageBox } from 'element-plus'
import type { VoucherCheckRow } from './useG4EclFormData'
import { sideTableOf, useVoucherCheckFill, withRowMeta, type PreparedItem } from './shared/voucherCheckFill'

/**
 * 共享回填函数的待写入项 → G4-13 凭证检查行：金额在样本自己的借贷栏，按分录自己的借贷栏分区（`sideTableOf`：
 * 借方红字仍在借方区，原规则「借方有正数才进借方区」把它分到贷方区、贷方区只显示贷方金额 0）；
 * 对方科目 = 编码、明细科目 = 名称（配不上写「多科目」时名称与编码相同，明细科目沿用原来的本科目名称兜底）。
 * 原实现把多科目凭证按分录展开、行金额取对方分录的金额（借方区的行写成贷方金额），已改为后端配对。
 */
export function mapPreparedToG4VoucherRow(item: PreparedItem): VoucherCheckRow {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null; accountName?: string | null }
  const code = item.counterpartAccount
  const name = item.counterpartAccountName
  const debit = Number(item.debitAmount ?? 0) || 0
  return {
    id: newUuid(),
    seq: 0,
    section: sideTableOf(item),
    date: s.voucherDate || '',
    voucherNo: s.voucherNo || '',
    businessContent: s.summary || '',
    counterAccount: code,
    detailAccount: name && name !== code ? name : (s.accountName || ''),
    debitAmount: debit,
    creditAmount: Number(item.creditAmount ?? 0) || 0,
    attachment: null,
    supportingDocDesc: '',
    checkOriginalComplete: false,
    checkAuthorized: false,
    checkAccountingCorrect: false,
    checkInitialCostCorrect: false,
    checkInterestCorrect: false,
    checkImpairmentCorrect: false,
    indexRef: '',
    isAbnormal: true, // 未核对前默认异常
    abnormalNote: '',
    remark: '',
  }
}

/** 行上已勾核对项或已填附件、支持性文件、索引、异常说明、备注（替换与撤销抽凭时据此先确认） */
export function hasG4VoucherContent(r: VoucherCheckRow): boolean {
  return [r.checkOriginalComplete, r.checkAuthorized, r.checkAccountingCorrect, r.checkInitialCostCorrect,
    r.checkInterestCorrect, r.checkImpairmentCorrect].some(Boolean)
    || [r.attachment, r.supportingDocDesc, r.indexRef, r.abnormalNote, r.remark].some(v => String(v ?? '').trim() !== '')
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG4EclVoucherCheck(opts: {
  /** 项目 id（抽凭回填按项目当前审计阶段标行阶段，年审阶段预审行只读） */
  projectId?: MaybeRefOrGetter<string | null | undefined>
  readonly?: MaybeRefOrGetter<boolean>
} = {}) {
  const rows = ref<VoucherCheckRow[]>([])
  const activeTab = ref<'tab1' | 'tab2' | 'tab3'>('tab1')
  const activeRowIndex = ref(0)

  // ─── 借方/贷方分区（computed） ────────────────────────────────────────────

  /** 借方区行 */
  const debitRows = computed(() => rows.value.filter(r => r.section === 'debit'))

  /** 贷方区行 */
  const creditRows = computed(() => rows.value.filter(r => r.section === 'credit'))

  // ─── 借贷平衡校验（Requirements: 6.6） ────────────────────────────────────

  /** 借方金额合计 */
  const debitTotal = computed(() =>
    calcSumColumn(debitRows.value.map(r => r.debitAmount))
  )

  /** 贷方金额合计 */
  const creditTotal = computed(() =>
    calcSumColumn(creditRows.value.map(r => r.creditAmount))
  )

  /** 借贷差额 */
  const difference = computed(() =>
    calcDebitCreditDifference(
      debitRows.value.map(r => r.debitAmount),
      creditRows.value.map(r => r.creditAmount)
    )
  )

  /** 是否平衡 */
  const isBalanced = computed(() =>
    isDebitCreditBalanced(
      debitRows.value.map(r => r.debitAmount),
      creditRows.value.map(r => r.creditAmount)
    )
  )

  // ─── 凭证异常判定（Requirements: 6.7） ────────────────────────────────────

  /**
   * 重新计算某行的异常状态：
   * 6项核对任一 false → isAbnormal = true
   */
  function recalcAbnormal(row: VoucherCheckRow): void {
    const checks = [
      row.checkOriginalComplete,
      row.checkAuthorized,
      row.checkAccountingCorrect,
      row.checkInitialCostCorrect,
      row.checkInterestCorrect,
      row.checkImpairmentCorrect,
    ]
    row.isAbnormal = !isVoucherNormal(checks)
  }

  /**
   * 判断某行是否全部核对通过
   */
  function isAllChecked(row: VoucherCheckRow): boolean {
    return isVoucherNormal([
      row.checkOriginalComplete,
      row.checkAuthorized,
      row.checkAccountingCorrect,
      row.checkInitialCostCorrect,
      row.checkInterestCorrect,
      row.checkImpairmentCorrect,
    ])
  }

  // ─── 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（Requirements: 6.3；共享回填函数） ─────

  const voucherFill = useVoucherCheckFill<VoucherCheckRow>({
    projectId: opts.projectId ?? null,
    tables: rows,
    mapSampleToRow: item => mapPreparedToG4VoucherRow(item),
    // 宿主深度监听 rows 落库（rowsToPersist 已按读入版本写回预审行），这里不另存
    persist: () => undefined,
    hasUserContent: hasG4VoucherContent,
    afterChange: () => _resequence(),
    readonly: opts.readonly,
  })

  /** 保存用的行：年审阶段预审行按读入版本写回（宿主落库与 toJSON 都用它） */
  function rowsToPersist(): VoucherCheckRow[] {
    return voucherFill.guardPersist(rows.value)
  }

  // ─── 行 CRUD（Requirements: 6.10） ────────────────────────────────────────

  /**
   * 新增行（ElMessageBox.prompt输入凭证编号）
   */
  async function addRow(section: 'debit' | 'credit', defaultVoucherNo?: string): Promise<void> {
    let voucherNo = defaultVoucherNo
    if (!voucherNo) {
      const { value } = await ElMessageBox.prompt('请输入凭证编号', '新增凭证行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValidator: (v) => (v?.trim() ? true : '凭证编号不能为空'),
      })
      if (!value?.trim()) return
      voucherNo = value.trim()
    }

    const sectionRows = rows.value.filter(r => r.section === section)
    const newRow: VoucherCheckRow = {
      id: newUuid(),
      seq: sectionRows.length + 1,
      section,
      date: '',
      voucherNo: voucherNo!,
      businessContent: '',
      counterAccount: '',
      detailAccount: '',
      debitAmount: 0,
      creditAmount: 0,
      attachment: null,
      supportingDocDesc: '',
      checkOriginalComplete: false,
      checkAuthorized: false,
      checkAccountingCorrect: false,
      checkInitialCostCorrect: false,
      checkInterestCorrect: false,
      checkImpairmentCorrect: false,
      indexRef: '',
      isAbnormal: true,
      abnormalNote: '',
      remark: '',
    }
    rows.value.push(newRow)
    _resequence()
  }

  /**
   * 删除行
   */
  function removeRow(id: string): void {
    if (rows.value.some(r => r.id === id && voucherFill.isRowLocked(r))) return
    rows.value = rows.value.filter(r => r.id !== id)
    _resequence()
  }

  /** 内部：按section重新编号 */
  function _resequence(): void {
    let debitSeq = 0
    let creditSeq = 0
    for (const row of rows.value) {
      if (row.section === 'debit') {
        row.seq = ++debitSeq
      } else {
        row.seq = ++creditSeq
      }
    }
  }

  // ─── 数据持久化 ───────────────────────────────────────────────────────────

  /**
   * 加载行数据
   */
  function loadRows(data: VoucherCheckRow[]): void {
    rows.value = (data || []).map(r => withRowMeta({
      ...r,
      id: r.id || newUuid(),
    }, r))
    _resequence()
    voucherFill.markLoaded()
  }

  /**
   * 导出为 JSON
   */
  function toJSON(): {
    rows: VoucherCheckRow[]
    debitTotal: number
    creditTotal: number
    difference: number
    isBalanced: boolean
  } {
    return {
      rows: rowsToPersist().map(r => ({ ...r })),
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      difference: difference.value,
      isBalanced: isBalanced.value,
    }
  }

  return {
    // State
    rows,
    activeTab,
    activeRowIndex,
    // Computed - 分区
    debitRows,
    creditRows,
    // Computed - 借贷平衡
    debitTotal,
    creditTotal,
    difference,
    isBalanced,
    // Validation
    recalcAbnormal,
    isAllChecked,
    // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled: voucherFill.onEngineFilled,
    onAttachImported: voucherFill.onAttachImported,
    onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
    rowsToPersist,
    // CRUD
    addRow,
    removeRow,
    // Data
    loadRows,
    toJSON,
  }
}

export default useG4EclVoucherCheck
