/**
 * useL1Detail — L1-2 明细表 composable
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 30列宽表数据管理
 * - 动态行增删（ElMessageBox.prompt 命名）
 * - 区段Tab切换（借款信息/期间变动/期末余额 3区段）
 * - 排序/筛选
 * - 负债类期末=期初+贷方-借方
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcLiabilityEndBalance, calcSubtotal } from '@/composables/useL1FormulaEngine'
import type { useL1FormData } from '@/composables/useL1FormData'
import type { DetailRow } from '@/composables/useL1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 区段Tab类型 */
export type DetailSegment = 'basic' | 'movement' | 'balance'

/** 排序配置 */
export interface DetailSortConfig {
  field: keyof DetailRow
  order: 'asc' | 'desc'
}

/** 筛选配置 */
export interface DetailFilterConfig {
  bank?: string
  loanType?: string
  currency?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：30列拆3段 */
export const DETAIL_SEGMENTS = [
  { key: 'basic' as const, label: '借款信息', fields: ['bank', 'contractNo', 'loanType', 'amount', 'rate', 'startDate', 'endDate', 'purpose', 'guarantee', 'currency'] },
  { key: 'movement' as const, label: '期间变动', fields: ['beginning', 'creditAmount', 'debitAmount'] },
  { key: 'balance' as const, label: '期末余额', fields: ['endBalance'] },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L1-2 明细表业务逻辑
 *
 * @param formData 由调用方传入的 useL1FormData 实例
 */
export function useL1Detail(formData: ReturnType<typeof useL1FormData>) {
  const { detailRows, debounceSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<DetailSegment>('basic')

  function switchSegment(segment: DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 排序/筛选状态 ─────────────────────────────────────────────────

  const sortConfig = ref<DetailSortConfig | null>(null)
  const filterConfig = ref<DetailFilterConfig>({})

  /** 筛选+排序后的行 */
  const filteredRows: ComputedRef<DetailRow[]> = computed(() => {
    let rows = [...detailRows.value]

    // 筛选
    const f = filterConfig.value
    if (f.bank) {
      rows = rows.filter(r => r.bank.includes(f.bank!))
    }
    if (f.loanType) {
      rows = rows.filter(r => r.loanType === f.loanType)
    }
    if (f.currency) {
      rows = rows.filter(r => r.currency === f.currency)
    }

    // 排序
    if (sortConfig.value) {
      const { field, order } = sortConfig.value
      rows.sort((a, b) => {
        const va = a[field]
        const vb = b[field]
        if (typeof va === 'number' && typeof vb === 'number') {
          return order === 'asc' ? va - vb : vb - va
        }
        const sa = String(va)
        const sb = String(vb)
        return order === 'asc' ? sa.localeCompare(sb) : sb.localeCompare(sa)
      })
    }

    return rows
  })

  function setSort(field: keyof DetailRow, order: 'asc' | 'desc'): void {
    sortConfig.value = { field, order }
  }

  function clearSort(): void {
    sortConfig.value = null
  }

  function setFilter(config: Partial<DetailFilterConfig>): void {
    filterConfig.value = { ...filterConfig.value, ...config }
  }

  function clearFilter(): void {
    filterConfig.value = {}
  }

  // ─── 3. 计算属性：每行 endBalance ──────────────────────────────────────

  /** 各行 endBalance 自动计算（负债类：期末=期初+贷方-借方） */
  const computedRows: ComputedRef<DetailRow[]> = computed(() => {
    return detailRows.value.map(row => ({
      ...row,
      endBalance: calcLiabilityEndBalance(row.beginning, row.creditAmount, row.debitAmount),
    }))
  })

  /** 合计 endBalance（供与审定表L1-1交叉验证） */
  const totalEndBalance: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.endBalance))
  })

  // ─── 4. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入借款银行名称）
   * 确认后插入空行，bank 字段预填
   */
  async function addRow(): Promise<void> {
    try {
      const { value: bankName } = await ElMessageBox.prompt(
        '请输入借款银行名称',
        '新增借款明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：中国银行',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '银行名称不能为空'
            return true
          },
        },
      )

      const newRow: DetailRow = {
        bank: bankName?.trim() || '',
        contractNo: '',
        loanType: '',
        amount: 0,
        rate: 0,
        startDate: '',
        endDate: '',
        purpose: '',
        guarantee: '',
        beginning: 0,
        creditAmount: 0,
        debitAmount: 0,
        endBalance: 0,
        currency: 'CNY',
      }

      detailRows.value.push(newRow)
      _triggerSave(detailRows.value.length - 1)
    } catch {
      // 用户取消
    }
  }

  /**
   * 删除指定行
   */
  function removeRow(index: number): void {
    if (index < 0 || index >= detailRows.value.length) return
    detailRows.value.splice(index, 1)
    // 全量保存（删除后重建 item_id 序列）
    _triggerSaveAll()
  }

  /**
   * 更新某行某字段
   */
  function updateRow(index: number, field: keyof DetailRow, value: string | number): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value

    // 如果是金额字段，重算 endBalance
    if (field === 'beginning' || field === 'creditAmount' || field === 'debitAmount') {
      row.endBalance = calcLiabilityEndBalance(row.beginning, row.creditAmount, row.debitAmount)
    }

    _triggerSave(index)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    const fields = ['bank', 'contractNo', 'loanType', 'amount', 'rate',
      'startDate', 'endDate', 'purpose', 'guarantee',
      'beginning', 'creditAmount', 'debitAmount', 'endBalance', 'currency']
    const items = fields.map(field => ({
      item_id: `L1-det-${n}-${field}`,
      conclusion: null,
      remark: (row as any)[field] != null && (row as any)[field] !== 0 ? String((row as any)[field]) : null,
    }))
    debounceSave(items)
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < detailRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 排序/筛选
    filteredRows,
    sortConfig,
    filterConfig,
    setSort,
    clearSort,
    setFilter,
    clearFilter,

    // 计算属性
    computedRows,
    totalEndBalance,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL1Detail
