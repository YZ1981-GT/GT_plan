/**
 * useH9Adjudication — H9-1 审定表 composable（3段：原值+未确认融资费用+净值）
 *
 * 审定表结构（对齐 Excel 审定表H9-1）：
 * 区块1：租赁负债-原值（贷方/负债类，按合同类型+小计）
 * 区块2：未确认融资费用（借方/负债备抵类）
 * 净值合计 = 原值小计 - 未确认融资费用小计
 *
 * 列：项目 | 期初 | 贷方(增加) | 借方(减少) | 期末 | 未审 | AJE | RJE | 审定
 *     | 重分类(一年内到期) | 报表数 | 变动额 | 变动率
 *
 * ⚠️ CRITICAL: 负债类贷方科目 期末=期初+贷方-借方
 *              备抵类借方科目 期末=期初+借方-贷方
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 3.4
 * Requirements: 2.1-2.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcContraLiabilityEndBalance,
  calcNetLiability,
  calcFsAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
} from './useH9FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H9-1 从明细带入模式 */
export type H91FillMode = 'book' | 'full'

/** H9-1 审定表行 */
export interface H9AdjudicationRow {
  rowId: string
  /** 项目名称 */
  name: string
  /** 区块：liability=租赁负债原值(贷方) / unearned=未确认融资费用(借方备抵) */
  block: 'liability' | 'unearned'
  /** 期初余额 */
  beginBalance: number
  /** 贷方发生额(负债增加)/借方发生额(备抵增加) */
  creditAmount: number
  /** 借方发生额(负债减少)/贷方发生额(备抵减少=摊销确认) */
  debitAmount: number
  /** 期末余额（公式计算） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（=未审+AJE+RJE） */
  audited: number
  /** 重分类：减一年内到期（对齐 Excel E/J 列） */
  reclassification: number
  /** 报表数 = 审定 − 重分类（公式） */
  fsAmount: number
  /** 期初报表数（用于变动额/率，默认=期初余额） */
  beginFsAmount: number
  /** 变动额 = 报表数 − 期初报表数（公式） */
  changeAmount: number
  /** 变动率（小数，公式） */
  changeRate: number
  /** 是否小计行 */
  isSubtotal?: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H9-1-rows'
const NOTE_KEY = 'H9-1-audit-note'
const CONCLUSION_KEY = 'H9-1-audit-conclusion'
const LIABILITY_AUDITED_KEY = 'H9-1-liability-audited'
const UNEARNED_AUDITED_KEY = 'H9-1-unearned-audited'
const NET_AUDITED_KEY = 'H9-1-net-audited'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9Adjudication(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  onWritebackTB?: (auditedLiability: number, auditedUnearned: number) => Promise<void>
}) {
  const { allResponses, onSave, onWritebackTB } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H9AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

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

  function _applyDerived(row: H9AdjudicationRow): void {
    row.endBalance = row.block === 'liability'
      ? calcLiabilityEndBalance(row.beginBalance, row.creditAmount, row.debitAmount)
      : calcContraLiabilityEndBalance(row.beginBalance, row.debitAmount, row.creditAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    row.fsAmount = calcFsAmount(row.audited, row.reclassification)
    row.changeAmount = calcChangeAmount(row.fsAmount, row.beginFsAmount)
    row.changeRate = calcChangeRate(row.beginFsAmount, row.changeAmount)
  }

  function _normalizeRow(raw: any): H9AdjudicationRow {
    const begin = Number(raw.beginBalance) || 0
    const credit = Number(raw.creditAmount) || 0
    const debit = Number(raw.debitAmount) || 0
    const unadj = Number(raw.unadjusted) || 0
    const aje = Number(raw.aje) || 0
    const rje = Number(raw.rje) || 0
    const reclass = Number(raw.reclassification) || 0
    const block = raw.block === 'unearned' ? 'unearned' : 'liability'
    // 期初报表数：有持久化值用持久化；否则默认=期初余额（对齐 Excel 期初报表数列）
    const beginFs = raw.beginFsAmount != null && raw.beginFsAmount !== ''
      ? (Number(raw.beginFsAmount) || 0)
      : begin

    const row: H9AdjudicationRow = {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: raw.name ?? '',
      block,
      beginBalance: begin,
      creditAmount: credit,
      debitAmount: debit,
      endBalance: 0,
      unadjusted: unadj,
      aje,
      rje,
      audited: 0,
      reclassification: reclass,
      fsAmount: 0,
      beginFsAmount: beginFs,
      changeAmount: 0,
      changeRate: 0,
      isSubtotal: raw.isSubtotal ?? false,
    }
    _applyDerived(row)
    return row
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 分区块行 ────────────────────────────────────────────────────

  const liabilityRows = computed(() => rows.value.filter(r => r.block === 'liability' && !r.isSubtotal))
  const unearnedRows = computed(() => rows.value.filter(r => r.block === 'unearned' && !r.isSubtotal))

  // ─── Computed: 各区块小计 ──────────────────────────────────────────────────

  const liabilitySubtotal = computed(() => ({
    beginBalance: calcSubtotal(liabilityRows.value.map(r => r.beginBalance)),
    creditAmount: calcSubtotal(liabilityRows.value.map(r => r.creditAmount)),
    debitAmount: calcSubtotal(liabilityRows.value.map(r => r.debitAmount)),
    endBalance: calcSubtotal(liabilityRows.value.map(r => r.endBalance)),
    unadjusted: calcSubtotal(liabilityRows.value.map(r => r.unadjusted)),
    aje: calcSubtotal(liabilityRows.value.map(r => r.aje)),
    rje: calcSubtotal(liabilityRows.value.map(r => r.rje)),
    audited: calcSubtotal(liabilityRows.value.map(r => r.audited)),
    reclassification: calcSubtotal(liabilityRows.value.map(r => r.reclassification)),
    fsAmount: calcSubtotal(liabilityRows.value.map(r => r.fsAmount)),
    beginFsAmount: calcSubtotal(liabilityRows.value.map(r => r.beginFsAmount)),
    changeAmount: calcSubtotal(liabilityRows.value.map(r => r.changeAmount)),
  }))

  const unearnedSubtotal = computed(() => ({
    beginBalance: calcSubtotal(unearnedRows.value.map(r => r.beginBalance)),
    creditAmount: calcSubtotal(unearnedRows.value.map(r => r.creditAmount)),
    debitAmount: calcSubtotal(unearnedRows.value.map(r => r.debitAmount)),
    endBalance: calcSubtotal(unearnedRows.value.map(r => r.endBalance)),
    unadjusted: calcSubtotal(unearnedRows.value.map(r => r.unadjusted)),
    aje: calcSubtotal(unearnedRows.value.map(r => r.aje)),
    rje: calcSubtotal(unearnedRows.value.map(r => r.rje)),
    audited: calcSubtotal(unearnedRows.value.map(r => r.audited)),
    reclassification: calcSubtotal(unearnedRows.value.map(r => r.reclassification)),
    fsAmount: calcSubtotal(unearnedRows.value.map(r => r.fsAmount)),
    beginFsAmount: calcSubtotal(unearnedRows.value.map(r => r.beginFsAmount)),
    changeAmount: calcSubtotal(unearnedRows.value.map(r => r.changeAmount)),
  }))

  // ─── Computed: 净值 = 原值 - 未确认融资费用 ────────────────────────────────

  const netAudited: ComputedRef<number> = computed(() =>
    calcNetLiability(liabilitySubtotal.value.audited, unearnedSubtotal.value.audited),
  )

  const netFsAmount: ComputedRef<number> = computed(() =>
    calcNetLiability(liabilitySubtotal.value.fsAmount, unearnedSubtotal.value.fsAmount),
  )

  /** 净额变动率（Excel 30% 阈值提示） */
  const netChangeRate: ComputedRef<number> = computed(() => {
    const beginFs = calcNetLiability(
      liabilitySubtotal.value.beginFsAmount,
      unearnedSubtotal.value.beginFsAmount,
    )
    const change = calcChangeAmount(netFsAmount.value, beginFs)
    return calcChangeRate(beginFs, change)
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row || row.isSubtotal) return

    const numVal = Number(value) || 0
    switch (field) {
      case 'name': row.name = String(value ?? ''); break
      case 'beginBalance':
        row.beginBalance = numVal
        // 若期初报表数仍等于旧期初，同步跟随（首次编制体验）
        break
      case 'creditAmount': row.creditAmount = numVal; break
      case 'debitAmount': row.debitAmount = numVal; break
      case 'unadjusted': row.unadjusted = numVal; break
      case 'aje': row.aje = numVal; break
      case 'rje': row.rje = numVal; break
      case 'reclassification': row.reclassification = numVal; break
      case 'beginFsAmount': row.beginFsAmount = numVal; break
      default: return
    }
    _applyDerived(row)
    _persist()
  }

  function addRow(name: string, block: 'liability' | 'unearned' = 'liability'): void {
    if (!name?.trim()) return
    rows.value.push(_normalizeRow({ name: name.trim(), block }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1 || rows.value[idx].isSubtotal) return
    rows.value.splice(idx, 1)
    _persist()
  }

  /**
   * 从 H9-4 调整分录回写 H9-1 AJE/RJE（对齐 H8-3→H8-1）。
   * - 租赁负债(2205)：按贷−借（负债贷方科目）写入 liability 行
   * - 未确认融资费用(1802)：按借−贷（备抵借方科目）写入 unearned 行
   * - 若无科目命中，则将传入的 ajeNet/rjeNet 落到 liability（兼容旧调用）
   */
  function syncAjeRjeFromAdjustment(ajeNet = 0, rjeNet = 0): {
    applied: boolean
    message: string
  } {
    const adjRows = _getJson('H9-4-rows') ?? _getJson('H9-5-rows')
    let liabAje = 0
    let liabRje = 0
    let unearnedAje = 0
    let unearnedRje = 0
    let matched = false

    if (Array.isArray(adjRows) && adjRows.length > 0) {
      for (const r of adjRows) {
        const label = `${r.accountName ?? ''} ${r.reportItem ?? ''} ${r.noteItem ?? ''}`
        const debit = Number(r.debitAmount) || 0
        const credit = Number(r.creditAmount) || 0
        const isRje = String(r.category || '').toUpperCase() === 'RJE'
        if (/未确认融资|1802/.test(label)) {
          matched = true
          const net = debit - credit
          if (isRje) unearnedRje += net
          else unearnedAje += net
        } else if (/租赁负债|2205/.test(label)) {
          matched = true
          const net = credit - debit
          if (isRje) liabRje += net
          else liabAje += net
        }
      }
    }

    if (!matched) {
      liabAje = Number(ajeNet) || 0
      liabRje = Number(rjeNet) || 0
    }

    if (
      Math.abs(liabAje) < 0.005 && Math.abs(liabRje) < 0.005
      && Math.abs(unearnedAje) < 0.005 && Math.abs(unearnedRje) < 0.005
    ) {
      return { applied: false, message: 'H9-4 暂无租赁负债/未确认融资费用调整净额' }
    }

    if (Math.abs(liabAje) >= 0.005 || Math.abs(liabRje) >= 0.005) {
      let target = rows.value.find(r => r.block === 'liability' && !r.isSubtotal)
      if (!target) {
        target = _normalizeRow({ name: '租赁负债合计', block: 'liability' })
        rows.value.push(target)
      }
      target.aje = liabAje
      target.rje = liabRje
      _applyDerived(target)
    }

    if (Math.abs(unearnedAje) >= 0.005 || Math.abs(unearnedRje) >= 0.005) {
      let target = rows.value.find(r => r.block === 'unearned' && !r.isSubtotal)
      if (!target) {
        target = _normalizeRow({ name: '未确认融资费用合计', block: 'unearned' })
        rows.value.push(target)
      }
      target.aje = unearnedAje
      target.rje = unearnedRje
      _applyDerived(target)
    }

    _persist()
    return {
      applied: true,
      message: matched
        ? `已从 H9-4 回写 AJE/RJE：负债 ${liabAje.toFixed(2)}/${liabRje.toFixed(2)}，融资费用 ${unearnedAje.toFixed(2)}/${unearnedRje.toFixed(2)}`
        : `已回写 liability AJE/RJE：${liabAje.toFixed(2)} / ${liabRje.toFixed(2)}（无科目命中，使用事件净额）`,
    }
  }

  /**
   * 从 H9-2 / H9-3 明细汇总带入审定表（对齐 H8-1←H8-2 带入）。
   * mode=book：写入未审/发生额/重分类，保留已有 AJE/RJE。
   * mode=full：未审=明细审定/最终审定，并清零 AJE/RJE。
   */
  function fillFromDetail(mode: H91FillMode = 'book'): {
    liabilityFilled: boolean
    unearnedFilled: boolean
    message: string
  } {
    const detail = _getJson('H9-2-rows')
    const finance = _getJson('H9-3-rows')
    const hasDetail = Array.isArray(detail) && detail.length > 0
    const hasFinance = Array.isArray(finance) && finance.length > 0
    if (!hasDetail && !hasFinance) {
      return { liabilityFilled: false, unearnedFilled: false, message: 'H9-2/H9-3 暂无明细行可带入' }
    }

    let liabilityFilled = false
    let unearnedFilled = false

    if (hasDetail) {
      const begin = calcSubtotal(detail.map((r: any) => Number(r.beginBalance) || 0))
      const repay = calcSubtotal(detail.map((r: any) => Number(r.repayment) || 0))
      const interest = calcSubtotal(detail.map((r: any) => Number(r.interestAccrued) || 0))
      const reclass = calcSubtotal(detail.map((r: any) => Number(r.reclassification) || 0))
      const auditedEnd = calcSubtotal(detail.map((r: any) => {
        const b = Number(r.beginBalance) || 0
        const rp = Number(r.repayment) || 0
        const it = Number(r.interestAccrued) || 0
        const ba = Number(r.beginAje) || 0
        const ra = Number(r.repayAje) || 0
        const ia = Number(r.interestAje) || 0
        const ab = b + ba
        const ar = rp + ra
        const ai = it + ia
        return calcLiabilityEndBalance(ab, ai, ar)
      }))
      const endUnaud = calcSubtotal(detail.map((r: any) => {
        const b = Number(r.beginBalance) || 0
        const rp = Number(r.repayment) || 0
        const it = Number(r.interestAccrued) || 0
        return calcLiabilityEndBalance(b, it, rp)
      }))
      const unadj = mode === 'full' ? auditedEnd : endUnaud

      let target = rows.value.find(r => r.block === 'liability' && !r.isSubtotal)
      if (!target) {
        target = _normalizeRow({ name: '租赁负债合计', block: 'liability' })
        rows.value.push(target)
      }
      target.beginBalance = begin
      target.debitAmount = repay
      target.creditAmount = interest
      target.unadjusted = unadj
      target.reclassification = reclass
      target.beginFsAmount = begin
      if (mode === 'full') {
        target.aje = 0
        target.rje = 0
      }
      _applyDerived(target)
      liabilityFilled = true
    }

    if (hasFinance) {
      const begin = calcSubtotal(finance.map((r: any) => Number(r.beginBalance) || 0))
      const debitInc = calcSubtotal(finance.map((r: any) => Number(r.debitIncrease) || 0))
      const creditDec = calcSubtotal(finance.map((r: any) => Number(r.creditDecrease) || 0))
      const reclass = calcSubtotal(finance.map((r: any) => Number(r.reclassification) || 0))
      const endUnaud = calcSubtotal(finance.map((r: any) => {
        const b = Number(r.beginBalance) || 0
        const di = Number(r.debitIncrease) || 0
        const cd = Number(r.creditDecrease) || 0
        return calcContraLiabilityEndBalance(b, di, cd)
      }))
      const auditedEnd = calcSubtotal(finance.map((r: any) => {
        const b = Number(r.beginBalance) || 0
        const di = Number(r.debitIncrease) || 0
        const cd = Number(r.creditDecrease) || 0
        const ba = Number(r.beginAje) || 0
        const ia = Number(r.increaseAje) || 0
        const ca = Number(r.confirmAje) || 0
        const oa = Number(r.otherAje) || 0
        const ai = di + ba + ia
        const ad = cd + ca + oa
        return calcContraLiabilityEndBalance(b, ai, ad)
      }))
      const unadj = mode === 'full' ? auditedEnd : endUnaud

      let target = rows.value.find(r => r.block === 'unearned' && !r.isSubtotal)
      if (!target) {
        target = _normalizeRow({ name: '未确认融资费用合计', block: 'unearned' })
        rows.value.push(target)
      }
      target.beginBalance = begin
      target.debitAmount = debitInc
      target.creditAmount = creditDec
      target.unadjusted = unadj
      target.reclassification = reclass
      target.beginFsAmount = begin
      if (mode === 'full') {
        target.aje = 0
        target.rje = 0
      }
      _applyDerived(target)
      unearnedFilled = true
    }

    _persist()
    const parts: string[] = []
    if (liabilityFilled) parts.push('原值←H9-2')
    if (unearnedFilled) parts.push('融资费用←H9-3')
    return {
      liabilityFilled,
      unearnedFilled,
      message: `已带入：${parts.join('；')}（${mode === 'full' ? '审定覆盖并清零AJE/RJE' : '写入未审，保留AJE/RJE'}）`,
    }
  }

  async function publishAdjudicated(): Promise<void> {
    if (onWritebackTB) {
      await onWritebackTB(liabilitySubtotal.value.audited, unearnedSubtotal.value.audited)
    }
    // Dispatch EventBus 'substantive:adjudicated' to notify other workpapers (附注/H8/报表)
    // 🔴 2026-08-03 纠正：原写 `2205`（合同负债，D7 域）→ 租赁负债真值 `2601`。
    //    该载荷驱动 TB 回写与跨底稿联动，写错科目会**污染 D7 合同负债的审定口径**
    //    （Req 6.4）。兜底码与后端 `four_table/h9_account_scope.py` 一致。
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: {
        wpCode: 'H9',
        accountCode: '2601',
        auditedAmount: liabilitySubtotal.value.audited,
        auditedAmountFinanceCost: unearnedSubtotal.value.audited,
      },
    }))
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    onSave?.(CONCLUSION_KEY, conclusion)
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.filter(r => !r.isSubtotal).map(r => ({
      rowId: r.rowId, name: r.name, block: r.block,
      beginBalance: r.beginBalance, creditAmount: r.creditAmount, debitAmount: r.debitAmount,
      unadjusted: r.unadjusted, aje: r.aje, rje: r.rje,
      reclassification: r.reclassification, beginFsAmount: r.beginFsAmount,
    }))
    onSave(ROWS_KEY, toPersist)
    onSave(LIABILITY_AUDITED_KEY, liabilitySubtotal.value.audited)
    onSave(UNEARNED_AUDITED_KEY, unearnedSubtotal.value.audited)
    onSave(NET_AUDITED_KEY, netAudited.value)
    // 跨表别名（useH9CrossSheet 读 H9-1-liability-total-audited）
    onSave('H9-1-liability-total-audited', liabilitySubtotal.value.audited)
    onSave('H9-1-unearned-total-audited', unearnedSubtotal.value.audited)
    onSave('H9-1-fs-amount', liabilitySubtotal.value.fsAmount)
    onSave('H9-1-interest-expense-audited', liabilitySubtotal.value.creditAmount)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, auditNote, auditConclusion,
    liabilityRows, unearnedRows,
    liabilitySubtotal, unearnedSubtotal, netAudited, netFsAmount, netChangeRate,
    updateCell, addRow, deleteRow, save, load,
    fillFromDetail,
    syncAjeRjeFromAdjustment,
    publishAdjudicated, saveNote, saveConclusion,
  }
}

export default useH9Adjudication
