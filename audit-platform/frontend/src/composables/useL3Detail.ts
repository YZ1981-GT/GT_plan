/**
 * useL3Detail — L3-2 明细表 composable
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 32列宽表数据管理（借款银行|合同号|借款类型|起始日|到期日|年利率|期初|本期借入|本期归还|期末|一年内到期）
 * - 期末=期初+借入-归还（负债类）
 * - calcCurrentPortion判定一年内到期
 * - 区段Tab 4组切换（基础信息/金额变动/到期分类/担保信息，行同步）
 * - 动态行增删（ElMessageBox.prompt 命名）
 * - 排序/筛选
 */
import { computed, ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcLiabilityEndBalance, calcSubtotal } from '@/composables/useL3FormulaEngine'
import { calcCurrentPortion } from '@/composables/useL3ReclassEngine'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L3明细表行数据 */
export interface L3DetailRow {
  /** 借款银行 */
  bank: string
  /** 合同号 */
  contractNo: string
  /** 借款类型（信用/保证/抵押/质押） */
  loanType: string
  /** 起始日 */
  startDate: string
  /** 到期日 */
  dueDate: string
  /** 年利率 */
  annualRate: number
  /** 期初余额 */
  beginning: number
  /** 本期借入（贷方） */
  borrowed: number
  /** 本期归还（借方） */
  repaid: number
  /** 期末余额（公式列：期初+借入-归还） */
  endBalance: number
  /** 一年内到期金额（公式列） */
  currentPortion: number
  /** 担保方式 */
  guaranteeType: string
  /** 担保物 */
  pledgeAsset: string
  /** 担保价值 */
  pledgeValue: number
  /** 用途 */
  purpose: string
  /** 币种 */
  currency: string
  /** 备注 */
  remark: string
}

/** 区段Tab类型：4组 */
export type L3DetailSegment = 'basic' | 'movement' | 'maturity' | 'guarantee'

/** 排序配置 */
export interface L3DetailSortConfig {
  field: keyof L3DetailRow
  order: 'asc' | 'desc'
}

/** 筛选配置 */
export interface L3DetailFilterConfig {
  bank?: string
  loanType?: string
  overdueOnly?: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：32列拆4段 */
export const L3_DETAIL_SEGMENTS = [
  { key: 'basic' as const, label: '基础信息', fields: ['bank', 'contractNo', 'loanType', 'startDate', 'dueDate', 'annualRate', 'purpose', 'currency'] },
  { key: 'movement' as const, label: '金额变动', fields: ['beginning', 'borrowed', 'repaid', 'endBalance'] },
  { key: 'maturity' as const, label: '到期分类', fields: ['currentPortion', 'dueDate'] },
  { key: 'guarantee' as const, label: '担保信息', fields: ['guaranteeType', 'pledgeAsset', 'pledgeValue'] },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L3-2 明细表业务逻辑
 *
 * @param formData 由调用方传入的 useL3FormData 实例
 * @param detailRows reactive ref of detail rows
 * @param reportDate 报告期截止日 (YYYY-MM-DD)
 */
export function useL3Detail(
  formData: ReturnType<typeof useL3FormData>,
  detailRows: { value: L3DetailRow[] },
  reportDate: string,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<L3DetailSegment>('basic')

  function switchSegment(segment: L3DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 排序/筛选状态 ─────────────────────────────────────────────────

  const sortConfig = ref<L3DetailSortConfig | null>(null)
  const filterConfig = ref<L3DetailFilterConfig>({})

  /** 筛选+排序后的行 */
  const filteredRows: ComputedRef<L3DetailRow[]> = computed(() => {
    let rows = [...detailRows.value]

    const f = filterConfig.value
    if (f.bank) {
      rows = rows.filter(r => r.bank.includes(f.bank!))
    }
    if (f.loanType) {
      rows = rows.filter(r => r.loanType === f.loanType)
    }
    if (f.overdueOnly) {
      rows = rows.filter(r => r.currentPortion > 0)
    }

    if (sortConfig.value) {
      const { field, order } = sortConfig.value
      rows.sort((a, b) => {
        const va = a[field]
        const vb = b[field]
        if (typeof va === 'number' && typeof vb === 'number') {
          return order === 'asc' ? va - vb : vb - va
        }
        return order === 'asc'
          ? String(va).localeCompare(String(vb))
          : String(vb).localeCompare(String(va))
      })
    }

    return rows
  })

  function setSort(field: keyof L3DetailRow, order: 'asc' | 'desc'): void {
    sortConfig.value = { field, order }
  }

  function clearSort(): void {
    sortConfig.value = null
  }

  function setFilter(config: Partial<L3DetailFilterConfig>): void {
    filterConfig.value = { ...filterConfig.value, ...config }
  }

  function clearFilter(): void {
    filterConfig.value = {}
  }

  // ─── 3. 计算属性：每行 endBalance + currentPortion ─────────────────────

  /** 各行 endBalance + currentPortion 自动计算 */
  const computedRows: ComputedRef<L3DetailRow[]> = computed(() => {
    return detailRows.value.map(row => ({
      ...row,
      // 负债类：期末=期初+借入-归还
      endBalance: calcLiabilityEndBalance(row.beginning, row.borrowed, row.repaid),
      // 一年内到期判定
      currentPortion: calcCurrentPortion(
        row.dueDate,
        reportDate,
        calcLiabilityEndBalance(row.beginning, row.borrowed, row.repaid),
      ),
    }))
  })

  /** 合计 endBalance（供与审定表L3-1交叉验证） */
  const totalEndBalance: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.endBalance))
  })

  /** 一年内到期金额合计 */
  const totalCurrentPortion: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.currentPortion))
  })

  // ─── 4. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入借款银行名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: bankName } = await ElMessageBox.prompt(
        '请输入借款银行名称',
        '新增长期借款明细',
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

      const newRow: L3DetailRow = {
        bank: bankName?.trim() || '',
        contractNo: '',
        loanType: '',
        startDate: '',
        dueDate: '',
        annualRate: 0,
        beginning: 0,
        borrowed: 0,
        repaid: 0,
        endBalance: 0,
        currentPortion: 0,
        guaranteeType: '',
        pledgeAsset: '',
        pledgeValue: 0,
        purpose: '',
        currency: 'CNY',
        remark: '',
      }

      detailRows.value.push(newRow)
      _triggerSave(detailRows.value.length - 1)
    } catch {
      // 用户取消
    }
  }

  /** 删除指定行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= detailRows.value.length) return
    detailRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  /** 更新某行某字段 */
  function updateRow(index: number, field: keyof L3DetailRow, value: string | number): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value

    // 如果是金额字段，重算 endBalance + currentPortion
    if (field === 'beginning' || field === 'borrowed' || field === 'repaid') {
      row.endBalance = calcLiabilityEndBalance(row.beginning, row.borrowed, row.repaid)
      row.currentPortion = calcCurrentPortion(row.dueDate, reportDate, row.endBalance)
    }
    // 如果修改到期日，重算 currentPortion
    if (field === 'dueDate') {
      row.currentPortion = calcCurrentPortion(row.dueDate, reportDate, row.endBalance)
    }

    _triggerSave(index)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    const fields: (keyof L3DetailRow)[] = [
      'bank', 'contractNo', 'loanType', 'startDate', 'dueDate', 'annualRate',
      'beginning', 'borrowed', 'repaid', 'endBalance', 'currentPortion',
      'guaranteeType', 'pledgeAsset', 'pledgeValue', 'purpose', 'currency', 'remark',
    ]
    for (const field of fields) {
      const val = (row as any)[field]
      debouncedSave(`L3-det-${n}-${field}`, {
        remark: val != null && val !== '' && val !== 0 ? String(val) : null,
      })
    }
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
    totalCurrentPortion,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL3Detail
