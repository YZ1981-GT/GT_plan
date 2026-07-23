/**
 * useM3TreasuryCheck — M3-5 检查表 composable（回购/注销核对）
 *
 * Spec: .kiro/specs/m3-treasury-stock/
 * Task: 3.4
 * Requirements: 5.1-5.5
 *
 * 职责：
 * - 回购核对区：批次|决议|回购股数|回购单价|回购总额|核对结果
 *   使用 calcRepurchaseAmount(shares, price) 验证回购金额
 * - 注销核对区：注销股数|注销金额|冲减实收资本(M2)|冲减资本公积(M4)|差额
 *   使用 calcCancelDiff(cancelAmount, deductCapital, deductReserve) 验证
 * - 核对清单 + 审计结论区
 *
 * 科目联动：
 * - M2(实收资本)：注销冲减按面值（冲减实收资本）
 * - M4(资本公积)：注销差额冲减资本公积
 * - 当差额≠0：需进一步冲减盈余公积(M5)/未分配利润(M6)
 */
import { computed, ref, type ComputedRef } from 'vue'
import { calcRepurchaseAmount, calcCancelDiff } from './useM3TreasuryEngine'
import { calcSubtotal } from './useM3FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import type { useM3FormData } from './useM3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 回购核对行 */
export interface M3RepurchaseCheckRow {
  /** 回购批次名 */
  batchName: string
  /** 回购决议文号 */
  resolution: string
  /** 回购股数 */
  shares: number
  /** 回购单价 */
  price: number
  /** 回购总额（公式=shares×price） */
  totalAmount: number
  /** 核对结果（√=一致/×=有差异） */
  checkResult: '√' | '×' | ''
  /** 备注 */
  remark: string
}

/** 注销核对行 */
export interface M3CancelCheckRow {
  /** 回购批次名 */
  batchName: string
  /** 注销股数 */
  cancelShares: number
  /** 注销金额（库存股账面金额） */
  cancelAmount: number
  /** 冲减实收资本（按面值，联动M2） */
  deductCapital: number
  /** 冲减资本公积（差额，联动M4） */
  deductReserve: number
  /** 冲减差额（公式=注销金额-冲减实收资本-冲减资本公积） */
  diff: number
  /** 差额处理说明 */
  diffHandling: string
}

/** 核对清单项 */
export interface M3ChecklistItem {
  /** 序号 */
  index: number
  /** 检查项目 */
  item: string
  /** 是否通过 */
  passed: boolean | null
  /** 说明 */
  note: string
}

/** 建议AJE分录（注销冲减差额>0时自动生成） */
export interface M3SuggestedAjeEntry {
  /** 说明 */
  description: string
  /** 类别 */
  category: '账项调整'
  /** 科目名称 */
  accountName: string
  /** 科目编码 */
  accountCode: string
  /** 借方金额（>0=借记） */
  debit: number
  /** 贷方金额（>0=贷记） */
  credit: number
  /** 来源批次 */
  batchName: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M3-5 检查表业务逻辑（回购核对+注销核对+清单+结论）
 *
 * @param formData 由调用方传入的 useM3FormData 实例
 */
export function useM3TreasuryCheck(formData: ReturnType<typeof useM3FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const repurchaseRows = ref<M3RepurchaseCheckRow[]>([])
  const cancelRows = ref<M3CancelCheckRow[]>([])
  const checklist = ref<M3ChecklistItem[]>([])
  const conclusion = ref('')

  // ─── 2. 回购核对计算 ──────────────────────────────────────────────────

  /** 回购核对行（自动计算 totalAmount） */
  const computedRepurchaseRows: ComputedRef<M3RepurchaseCheckRow[]> = computed(() => {
    return repurchaseRows.value.map(row => ({
      ...row,
      totalAmount: calcRepurchaseAmount(row.shares, row.price),
    }))
  })

  /** 回购核对合计 */
  const repurchaseTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRepurchaseRows.value.map(r => r.totalAmount))
  })

  // ─── 3. 注销核对计算 ──────────────────────────────────────────────────

  /** 注销核对行（自动计算 diff） */
  const computedCancelRows: ComputedRef<M3CancelCheckRow[]> = computed(() => {
    return cancelRows.value.map(row => ({
      ...row,
      diff: calcCancelDiff(row.cancelAmount, row.deductCapital, row.deductReserve),
    }))
  })

  /** 注销核对：是否存在差额≠0的行（需进一步冲减M5/M6） */
  const hasUnresolvedDiff: ComputedRef<boolean> = computed(() => {
    return computedCancelRows.value.some(r => Math.abs(r.diff) > 0.01)
  })

  /** 注销金额合计 */
  const cancelTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedCancelRows.value.map(r => r.cancelAmount))
  })

  // ─── 4. 行操作：回购核对 ──────────────────────────────────────────────

  /** 新增回购核对行 */
  function addRepurchaseRow(batchName?: string): void {
    repurchaseRows.value.push({
      batchName: batchName || '',
      resolution: '',
      shares: 0,
      price: 0,
      totalAmount: 0,
      checkResult: '',
      remark: '',
    })
    _saveRepurchaseRows()
  }

  /** 删除回购核对行 */
  function removeRepurchaseRow(index: number): void {
    if (index < 0 || index >= repurchaseRows.value.length) return
    repurchaseRows.value.splice(index, 1)
    _saveRepurchaseRows()
  }

  /** 更新回购核对行 */
  function updateRepurchaseRow(index: number, field: keyof M3RepurchaseCheckRow, value: string | number): void {
    if (index < 0 || index >= repurchaseRows.value.length) return
    const row = repurchaseRows.value[index] as any
    row[field] = value
    // 重算 totalAmount
    row.totalAmount = calcRepurchaseAmount(row.shares, row.price)
    _saveRepurchaseRows()
  }

  // ─── 5. 行操作：注销核对 ──────────────────────────────────────────────

  /** 新增注销核对行 */
  function addCancelRow(batchName?: string): void {
    cancelRows.value.push({
      batchName: batchName || '',
      cancelShares: 0,
      cancelAmount: 0,
      deductCapital: 0,
      deductReserve: 0,
      diff: 0,
      diffHandling: '',
    })
    _saveCancelRows()
  }

  /** 删除注销核对行 */
  function removeCancelRow(index: number): void {
    if (index < 0 || index >= cancelRows.value.length) return
    cancelRows.value.splice(index, 1)
    _saveCancelRows()
  }

  /** 更新注销核对行 */
  function updateCancelRow(index: number, field: keyof M3CancelCheckRow, value: string | number): void {
    if (index < 0 || index >= cancelRows.value.length) return
    const row = cancelRows.value[index] as any
    row[field] = value
    // 重算 diff
    row.diff = calcCancelDiff(row.cancelAmount, row.deductCapital, row.deductReserve)
    _saveCancelRows()
  }

  // ─── 6. 核对清单操作 ──────────────────────────────────────────────────

  /** 更新清单项 */
  function updateChecklistItem(index: number, field: 'passed' | 'note', value: boolean | null | string): void {
    if (index < 0 || index >= checklist.value.length) return
    const item = checklist.value[index] as any
    item[field] = value
    _saveChecklist()
  }

  /** 设置审计结论 */
  function setConclusion(text: string): void {
    conclusion.value = text
    debouncedSave('M3-M3-5-conclusion', { remark: text })
  }

  // ─── 7. 注销冲减发布 EventBus（M2/M4联动） ────────────────────────────

  /** 上次发布的注销金额（变化检测，仅变化时发布） */
  let _lastPublishedCancelTotal: number | null = null

  /**
   * 发布 'm3:cancellation-deduction' 事件到 EventBus。
   * M2实收资本 / M4资本公积 订阅此事件核对注销冲减是否入账。
   * 仅在注销金额合计变化时发布（避免重复广播）。
   */
  function publishCancellationDeduction(): void {
    const currentTotal = cancelTotal.value
    if (_lastPublishedCancelTotal === currentTotal) return
    _lastPublishedCancelTotal = currentTotal
    // 无注销业务时不发布
    if (currentTotal === 0) return

    const rows = computedCancelRows.value
    eventBus.emit('m3:cancellation-deduction', {
      wpCode: 'M3',
      totalCancellationAmount: currentTotal,
      deductCapitalTotal: calcSubtotal(rows.map(r => r.deductCapital)),
      deductReserveTotal: calcSubtotal(rows.map(r => r.deductReserve)),
      remainingDiff: calcSubtotal(rows.map(r => r.diff)),
      byBatch: rows.map(r => ({
        batchName: r.batchName,
        cancelAmount: r.cancelAmount,
        deductCapital: r.deductCapital,
        deductReserve: r.deductReserve,
      })),
      timestamp: Date.now(),
    } as any)
  }

  // ─── 8. 保存逻辑 ──────────────────────────────────────────────────────

  function _saveRepurchaseRows(): void {
    repurchaseRows.value.forEach((row, i) => {
      const n = i + 1
      debouncedSave(`M3-M3-5-repurchase-${n}`, {
        remark: JSON.stringify({
          batchName: row.batchName,
          resolution: row.resolution,
          shares: row.shares,
          price: row.price,
          checkResult: row.checkResult,
          remark: row.remark,
        }),
      })
    })
  }

  function _saveCancelRows(): void {
    cancelRows.value.forEach((row, i) => {
      const n = i + 1
      debouncedSave(`M3-M3-5-cancel-${n}`, {
        remark: JSON.stringify({
          batchName: row.batchName,
          cancelShares: row.cancelShares,
          cancelAmount: row.cancelAmount,
          deductCapital: row.deductCapital,
          deductReserve: row.deductReserve,
          diffHandling: row.diffHandling,
        }),
      })
    })
    // 同时保存完整 cancel-rows JSON 供 useM3CrossSheet 消费
    debouncedSave('M3-M3-5-cancel-rows', {
      remark: JSON.stringify(cancelRows.value.map(row => ({
        batchName: row.batchName,
        cancelAmount: row.cancelAmount,
        deductCapital: row.deductCapital,
        deductReserve: row.deductReserve,
      }))),
    })
  }

  function _saveChecklist(): void {
    checklist.value.forEach((item, i) => {
      const n = i + 1
      debouncedSave(`M3-M3-5-checklist-${n}`, {
        remark: JSON.stringify({ passed: item.passed, note: item.note }),
      })
    })
  }

  // ─── 9. 注销冲减差额>0 → 建议AJE分录（自动生成，M5/M6冲减） ────────

  /**
   * 当注销冲减差额>0时自动建议AJE分录:
   * - 差额优先冲减盈余公积(M5/3101)
   * - 盈余公积不足部分冲减未分配利润(M6/3104)
   *
   * CAS准则：注销库存股冲减顺序=实收资本(面值)→资本公积→盈余公积→未分配利润
   * 此处差额=注销金额−冲减M2−冲减M4，即M2/M4已冲减完的剩余部分
   */
  const suggestedAjeEntries: ComputedRef<M3SuggestedAjeEntry[]> = computed(() => {
    const entries: M3SuggestedAjeEntry[] = []
    for (const row of computedCancelRows.value) {
      const diff = row.diff
      if (Math.abs(diff) <= 0.01) continue
      if (diff > 0) {
        // 差额>0：库存股成本高于冲减M2+M4，需继续冲减M5→M6
        // 建议分录：借:盈余公积/未分配利润  贷:库存股
        // 这里全额建议冲减盈余公积，审计师可手动调整分配到M6
        entries.push({
          description: `注销库存股"${row.batchName}"冲减差额${diff.toFixed(2)}元，建议冲减盈余公积`,
          category: '账项调整',
          accountName: '盈余公积',
          accountCode: '3101',
          debit: diff,
          credit: 0,
          batchName: row.batchName,
        })
        entries.push({
          description: `注销库存股"${row.batchName}"冲减差额对应贷记库存股`,
          category: '账项调整',
          accountName: '库存股',
          accountCode: '4002',
          debit: 0,
          credit: diff,
          batchName: row.batchName,
        })
      } else {
        // 差额<0：注销金额低于冲减M2+M4（极端罕见），增加资本公积
        const absDiff = Math.abs(diff)
        entries.push({
          description: `注销库存股"${row.batchName}"低于冲减合计${absDiff.toFixed(2)}元，建议增加资本公积`,
          category: '账项调整',
          accountName: '资本公积',
          accountCode: '3002',
          debit: 0,
          credit: absDiff,
          batchName: row.batchName,
        })
        entries.push({
          description: `注销库存股"${row.batchName}"差额对应借记库存股`,
          category: '账项调整',
          accountName: '库存股',
          accountCode: '4002',
          debit: absDiff,
          credit: 0,
          batchName: row.batchName,
        })
      }
    }
    return entries
  })

  /** 是否有建议AJE */
  const hasSuggestedAje: ComputedRef<boolean> = computed(() => suggestedAjeEntries.value.length > 0)

  /**
   * 推送建议AJE到调整分录模块（EventBus 'adjustment:created'）
   * 审计师确认后一键推送，M3-3调整分录订阅此事件自动新增
   */
  function pushSuggestedAje(): void {
    if (!hasSuggestedAje.value) return
    const entries = suggestedAjeEntries.value
    eventBus.emit('adjustment:created', {
      wpCode: 'M3',
      source: 'M3-5-cancel-diff',
      entries: entries.map(e => ({
        description: e.description,
        category: e.category,
        accountName: e.accountName,
        accountCode: e.accountCode,
        debit: e.debit,
        credit: e.credit,
      })),
      timestamp: Date.now(),
    } as any)
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    repurchaseRows,
    cancelRows,
    checklist,
    conclusion,

    // 计算
    computedRepurchaseRows,
    repurchaseTotal,
    computedCancelRows,
    hasUnresolvedDiff,
    cancelTotal,

    // 建议AJE（注销冲减差额>0）
    suggestedAjeEntries,
    hasSuggestedAje,
    pushSuggestedAje,

    // 回购核对操作
    addRepurchaseRow,
    removeRepurchaseRow,
    updateRepurchaseRow,

    // 注销核对操作
    addCancelRow,
    removeCancelRow,
    updateCancelRow,

    // 注销冲减发布（M2/M4联动）
    publishCancellationDeduction,

    // 清单+结论
    updateChecklistItem,
    setConclusion,
  }
}

export default useM3TreasuryCheck
