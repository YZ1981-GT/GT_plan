/**
 * useL8NonFinInterest — L8-4 非金融机构利息支出测算 composable
 *
 * Spec: .kiro/specs/l8-financial-expenses/
 * Task: 3.4
 * Requirements: 5.1-5.4
 *
 * 职责：
 * - 非金融机构借款利息支出测算
 * - 列结构：核算科目 | 贷款单位 | 借款日 | 还款日 | 年利率 | 本金
 *   | 计息天数 | 应计利息 | 合同索引 | 备注
 * - 计息天数公式: IF((还款日-借款日)=365, 还款日-借款日, 还款日-借款日+1)
 * - 应计利息: 年利率 × 本金 / 365 × 天数（actual/365制！）
 * - 可扣除利息: 本金 × 同期金融机构利率 × 天数 / 360
 * - 超标利息: 应计利息 - 可扣除利息（>0橙色提示税务调整）
 * - 差异 = 测算合计 - 账面合计
 *
 * 科目：6603 财务费用（借方/损益类！取发生额）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcDeductibleInterest,
  calcExcessInterest,
  hasExcessInterest,
} from './useL8InterestEngine'
import { calcSubtotal, parseNum } from './useL8FormulaEngine'
import type { useL8FormData } from './useL8FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L8-4 非金融机构利息测算行（对应xlsx 15列） */
export interface L8NonFinInterestRow {
  /** 行唯一标识 */
  key: string
  /** 核算科目 */
  accountSubject: string
  /** 贷款单位（非金融机构名称） */
  lender: string
  /** 借款日（YYYY-MM-DD） */
  startDate: string
  /** 还款日（YYYY-MM-DD） */
  endDate: string
  /** 约定年利率（如 0.08 表示8%） */
  annualRate: number
  /** 同期金融机构基准利率（如 0.0435 表示4.35%） */
  benchmarkRate: number
  /** 借款本金 */
  principal: number
  /** 计息天数（公式计算） */
  interestDays: number
  /** 应计利息（公式: 年利率×本金/365×天数） */
  accruedInterest: number
  /** 可扣除利息（公式: 本金×基准利率×天数/360） */
  deductibleInterest: number
  /** 超标利息（公式: 应计利息-可扣除利息） */
  excessInterest: number
  /** 是否超标（超标利息>0时橙色高亮） */
  isExcess: boolean
  /** 合同索引/参考号 */
  contractRef: string
  /** 备注 */
  remark: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 计算两个日期间天数（L8-4公式逻辑）
 *
 * IF((还款日-借款日)=365, 还款日-借款日, 还款日-借款日+1)
 * 即：整年(365天)不加1，非整年加1天（含头含尾）
 */
function calcInterestDays(startDate: string, endDate: string): number {
  if (!startDate || !endDate) return 0
  const start = new Date(startDate)
  const end = new Date(endDate)
  if (isNaN(start.getTime()) || isNaN(end.getTime())) return 0

  const diffMs = end.getTime() - start.getTime()
  const diffDays = Math.round(diffMs / 86_400_000)
  if (diffDays <= 0) return 0

  // 整年(365天)不加1，否则加1
  return diffDays === 365 ? 365 : diffDays + 1
}

/**
 * 计算应计利息（actual/365制！非360制）
 * 应计利息 = 年利率 × 本金 / 365 × 计息天数
 */
function calcAccruedInterest(annualRate: number, principal: number, days: number): number {
  return parseNum(annualRate) * parseNum(principal) / 365 * parseNum(days)
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L8-4 非金融机构利息支出测算逻辑
 *
 * @param formData 由调用方传入的 useL8FormData 实例
 * @param rows reactive ref of non-fin interest rows
 */
export function useL8NonFinInterest(
  formData: ReturnType<typeof useL8FormData>,
  rows: Ref<L8NonFinInterestRow[]>,
) {
  const { debouncedSave } = formData

  /** 账面利息合计（用户输入） */
  const bookedInterestTotal = ref(0)

  // ─── 1. 计算属性：公式列自动计算 ─────────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<L8NonFinInterestRow[]> = computed(() => {
    return rows.value.map(row => {
      // 计息天数
      const interestDays = calcInterestDays(row.startDate, row.endDate)
      // 应计利息（actual/365制！）
      const accruedInterest = calcAccruedInterest(row.annualRate, row.principal, interestDays)
      // 可扣除利息（本金×基准利率×天数/360，税务口径）
      const deductibleInterest = calcDeductibleInterest(row.principal, row.benchmarkRate, interestDays)
      // 超标利息
      const excessInterest = calcExcessInterest(accruedInterest, deductibleInterest)
      // 是否超标
      const isExcess = hasExcessInterest(excessInterest)

      return {
        ...row,
        interestDays,
        accruedInterest,
        deductibleInterest,
        excessInterest,
        isExcess,
      }
    })
  })

  // ─── 2. 合计行 ────────────────────────────────────────────────────────

  /** 应计利息合计（测算合计） */
  const totalAccruedInterest: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.accruedInterest))
  })

  /** 可扣除利息合计 */
  const totalDeductibleInterest: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.deductibleInterest))
  })

  /** 超标利息合计 */
  const totalExcessInterest: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.excessInterest))
  })

  /** 差异 = 测算合计 - 账面合计 */
  const diffVsBooked: ComputedRef<number> = computed(() => {
    return totalAccruedInterest.value - bookedInterestTotal.value
  })

  /** 是否存在超标行（整体税务提示） */
  const hasAnyExcess: ComputedRef<boolean> = computed(() => {
    return computedRows.value.some(r => r.isExcess)
  })

  // ─── 3. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增测算行（先弹 ElMessageBox.prompt 输入贷款单位名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: lender } = await ElMessageBox.prompt(
        '请输入贷款单位（非金融机构）名称',
        '新增利息测算行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：XX股东/XX关联方/XX自然人',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '贷款单位不能为空'
            return true
          },
        },
      )

      const key = `l8-nfi-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: L8NonFinInterestRow = {
        key,
        accountSubject: '6603 财务费用',
        lender: lender?.trim() || '',
        startDate: '',
        endDate: '',
        annualRate: 0,
        benchmarkRate: 0,
        principal: 0,
        interestDays: 0,
        accruedInterest: 0,
        deductibleInterest: 0,
        excessInterest: 0,
        isExcess: false,
        contractRef: '',
        remark: '',
      }
      rows.value.push(newRow)
      _triggerSaveAll()
    } catch {
      // 用户取消
    }
  }

  /** 删除指定行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    _triggerSaveAll()
  }

  /** 更新某行某字段 */
  function updateRow(index: number, field: keyof L8NonFinInterestRow, value: any): void {
    if (index < 0 || index >= rows.value.length) return
    const row = rows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  /** 更新账面利息合计 */
  function setBookedTotal(value: number): void {
    bookedInterestTotal.value = parseNum(value)
    debouncedSave('L8-4-bookedTotal', { remark: String(bookedInterestTotal.value) })
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = rows.value[rowIndex]
    if (!row) return
    debouncedSave(`L8-4-row-${rowIndex}-data`, {
      remark: JSON.stringify({
        key: row.key,
        accountSubject: row.accountSubject,
        lender: row.lender,
        startDate: row.startDate,
        endDate: row.endDate,
        annualRate: row.annualRate,
        benchmarkRate: row.benchmarkRate,
        principal: row.principal,
        contractRef: row.contractRef,
        remark: row.remark,
      }),
    })
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < rows.value.length; i++) {
      _triggerSave(i)
    }
    // 保存合计数据
    debouncedSave('L8-4-totalAccrued', { remark: String(totalAccruedInterest.value) })
    debouncedSave('L8-4-totalExcess', { remark: String(totalExcessInterest.value) })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算行
    computedRows,
    // 合计
    totalAccruedInterest,
    totalDeductibleInterest,
    totalExcessInterest,
    diffVsBooked,
    hasAnyExcess,
    bookedInterestTotal,
    // 行操作
    addRow,
    removeRow,
    updateRow,
    setBookedTotal,
  }
}

export default useL8NonFinInterest
