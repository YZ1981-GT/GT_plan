/**
 * useM7Detail — M7-2 明细表 composable（27列区段Tab管理）
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 3.4
 * Requirements: 3.1-3.5
 *
 * 职责：
 * - 27列按区段Tab管理（计提/费用化使用/资本化使用，行同步）
 * - 行结构：安全生产费/维简费/其他 + 合计行
 * - 22公式实时计算：
 *   E = B + C - D（期末=期初+贷方计提-借方使用，权益类！）
 *   L = B + F + G（审定期初=期初+期初AJE+期初RJE）
 *   M = C + H + J（审定计提=账面计提+计提AJE+计提RJE）
 *   N = D + I + K（审定使用=账面使用+使用AJE+使用RJE）
 *   O = L + M - N（审定期末=审定期初+审定计提-审定使用，权益类！）
 * - 动态行新增（ElMessageBox.prompt输入名称）+合计行
 * - 导入导出数据准备
 * - 与M7-1审定表交叉验证
 *
 * 科目：4201 专项储备（**贷方/权益类！期末=期初+贷方-借方**）
 * 24×27结构，22公式
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from './useM7FormulaEngine'
import type { useM7FormData } from './useM7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** M7-2 明细表行数据（27列） */
export interface M7DetailRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 期初余额（B列，贷方余额） */
  beginning: number
  /** 本期计提（C列，贷方增加：安全生产费计提） */
  creditAccrual: number
  /** 本期使用-费用化（D1列，借方减少：直接冲减专项储备） */
  debitExpense: number
  /** 本期使用-资本化（D2列，借方减少：形成固定资产同时冲减） */
  debitCapital: number
  /** 本期使用合计（D列=D1+D2，公式列） */
  debitTotal: number
  /** 期末余额（E列，公式=B+C-D，权益类！） */
  endBalance: number
  // ─── AJE/RJE调整列（审定口径） ───
  /** 期初AJE（F列） */
  beginAje: number
  /** 期初RJE（G列） */
  beginRje: number
  /** 计提AJE（H列） */
  accrualAje: number
  /** 计提RJE（J列） */
  accrualRje: number
  /** 使用AJE（I列） */
  usageAje: number
  /** 使用RJE（K列） */
  usageRje: number
  // ─── 审定列（公式列） ───
  /** 审定期初（L列，公式=B+F+G） */
  auditedBegin: number
  /** 审定计提（M列，公式=C+H+J） */
  auditedAccrual: number
  /** 审定使用（N列，公式=D+I+K） */
  auditedUsage: number
  /** 审定期末（O列，公式=L+M-N，权益类！） */
  auditedEnd: number
  // ─── 上期对比 ───
  /** 上期期初（P列） */
  priorBeginning: number
  /** 上期计提（Q列） */
  priorAccrual: number
  /** 上期使用（R列） */
  priorUsage: number
  /** 上期期末（S列） */
  priorEnd: number
  // ─── 变动+备注 ───
  /** 变动额（T列=O-S） */
  changeAmount: number
  /** 变动率（U列） */
  changeRate: number
  /** 备注（V列） */
  remark: string
}

/** 区段Tab类型 */
export type M7DetailSegment = 'accrual' | 'expense' | 'capital'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：27列拆3段 */
export const M7_DETAIL_SEGMENTS = [
  {
    key: 'accrual' as const,
    label: '计提',
    description: '安全生产费计提明细（贷方增加）',
    fields: ['itemName', 'beginning', 'creditAccrual', 'endBalance', 'beginAje', 'beginRje', 'accrualAje', 'accrualRje', 'auditedBegin', 'auditedAccrual'],
  },
  {
    key: 'expense' as const,
    label: '费用化使用',
    description: '费用性支出（直接冲减专项储备）',
    fields: ['itemName', 'debitExpense', 'usageAje', 'usageRje', 'auditedUsage'],
  },
  {
    key: 'capital' as const,
    label: '资本化使用',
    description: '资本性支出（形成固定资产+全额折旧冲减）',
    fields: ['itemName', 'debitCapital', 'auditedEnd', 'priorBeginning', 'priorAccrual', 'priorUsage', 'priorEnd', 'changeAmount', 'changeRate', 'remark'],
  },
] as const

/** 默认明细行 */
export const M7_DETAIL_DEFAULT_ITEMS = [
  '安全生产费',
  '维简费',
  '安全费—安全设备购置',
  '安全费—安全设施维护',
  '安全费—安全培训',
  '其他专项储备',
]

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M7-2 明细表业务逻辑（27列区段Tab + 22公式）
 *
 * @param formData 由调用方传入的 useM7FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useM7Detail(
  formData: ReturnType<typeof useM7FormData>,
  detailRows: Ref<M7DetailRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<M7DetailSegment>('accrual')

  function switchSegment(segment: M7DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：22公式全部前端实时计算 ────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M7DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      // D=D1+D2 本期使用合计
      const debitTotal = row.debitExpense + row.debitCapital
      // E=B+C-D 期末余额（权益类！）
      const endBalance = calcEquityEndBalance(row.beginning, row.creditAccrual, debitTotal)
      // L=B+F+G 审定期初
      const auditedBegin = calcAuditedAmount(row.beginning, row.beginAje, row.beginRje)
      // M=C+H+J 审定计提
      const auditedAccrual = calcAuditedAmount(row.creditAccrual, row.accrualAje, row.accrualRje)
      // N=D+I+K 审定使用
      const auditedUsage = calcAuditedAmount(debitTotal, row.usageAje, row.usageRje)
      // O=L+M-N 审定期末（权益类！）
      const auditedEnd = calcEquityEndBalance(auditedBegin, auditedAccrual, auditedUsage)
      // T=O-S 变动额
      const changeAmount = auditedEnd - row.priorEnd
      // U 变动率
      const changeRate = row.priorEnd === 0
        ? (auditedEnd === 0 ? 0 : 1)
        : (auditedEnd - row.priorEnd) / row.priorEnd

      return {
        ...row,
        debitTotal,
        endBalance,
        auditedBegin,
        auditedAccrual,
        auditedUsage,
        auditedEnd,
        changeAmount,
        changeRate,
      }
    })
  })

  // ─── 3. 合计行 ────────────────────────────────────────────────────────

  /** 各列合计（供审定表交叉验证） */
  const totals = computed(() => {
    const r = computedRows.value
    const beginning = calcSubtotal(r.map(x => x.beginning))
    const creditAccrual = calcSubtotal(r.map(x => x.creditAccrual))
    const debitExpense = calcSubtotal(r.map(x => x.debitExpense))
    const debitCapital = calcSubtotal(r.map(x => x.debitCapital))
    const debitTotal = debitExpense + debitCapital
    const endBalance = calcEquityEndBalance(beginning, creditAccrual, debitTotal)
    const auditedBegin = calcSubtotal(r.map(x => x.auditedBegin))
    const auditedAccrual = calcSubtotal(r.map(x => x.auditedAccrual))
    const auditedUsage = calcSubtotal(r.map(x => x.auditedUsage))
    const auditedEnd = calcEquityEndBalance(auditedBegin, auditedAccrual, auditedUsage)
    return {
      beginning,
      creditAccrual,
      debitExpense,
      debitCapital,
      debitTotal,
      endBalance,
      auditedBegin,
      auditedAccrual,
      auditedUsage,
      auditedEnd,
    }
  })

  /** 计提合计（贷方，供M7-1交叉验证） */
  const totalCreditAccrual: ComputedRef<number> = computed(() => totals.value.creditAccrual)

  /** 使用合计（借方，供M7-1交叉验证） */
  const totalDebitUsage: ComputedRef<number> = computed(() => totals.value.debitTotal)

  /** 审定期末合计（供M7-1交叉验证） */
  const totalAuditedEnd: ComputedRef<number> = computed(() => totals.value.auditedEnd)

  // ─── 4. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入项目名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: itemName } = await ElMessageBox.prompt(
        '请输入专项储备明细项目名称',
        '新增明细项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：安全生产费—设备购置/维简费/安全培训费',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            return true
          },
        },
      )

      const key = `m7-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: M7DetailRow = {
        key,
        itemName: itemName?.trim() || '',
        beginning: 0,
        creditAccrual: 0,
        debitExpense: 0,
        debitCapital: 0,
        debitTotal: 0,
        endBalance: 0,
        beginAje: 0,
        beginRje: 0,
        accrualAje: 0,
        accrualRje: 0,
        usageAje: 0,
        usageRje: 0,
        auditedBegin: 0,
        auditedAccrual: 0,
        auditedUsage: 0,
        auditedEnd: 0,
        priorBeginning: 0,
        priorAccrual: 0,
        priorUsage: 0,
        priorEnd: 0,
        changeAmount: 0,
        changeRate: 0,
        remark: '',
      }
      detailRows.value.push(newRow)
      _triggerSaveAll()
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
  function updateRow(index: number, field: keyof M7DetailRow, value: any): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  // ─── 5. 导入导出数据准备 ──────────────────────────────────────────────

  /** 导出数据准备（所有计算行+合计行，27列完整数据） */
  function prepareExportData(): { rows: M7DetailRow[]; totals: typeof totals.value } {
    return {
      rows: computedRows.value,
      totals: totals.value,
    }
  }

  /** 导入数据（替换所有行） */
  function importData(imported: Array<Partial<M7DetailRow>>): void {
    detailRows.value = imported.map((item, i) => ({
      key: item.key || `m7-detail-import-${i}-${Date.now()}`,
      itemName: item.itemName || '',
      beginning: item.beginning || 0,
      creditAccrual: item.creditAccrual || 0,
      debitExpense: item.debitExpense || 0,
      debitCapital: item.debitCapital || 0,
      debitTotal: 0,
      endBalance: 0,
      beginAje: item.beginAje || 0,
      beginRje: item.beginRje || 0,
      accrualAje: item.accrualAje || 0,
      accrualRje: item.accrualRje || 0,
      usageAje: item.usageAje || 0,
      usageRje: item.usageRje || 0,
      auditedBegin: 0,
      auditedAccrual: 0,
      auditedUsage: 0,
      auditedEnd: 0,
      priorBeginning: item.priorBeginning || 0,
      priorAccrual: item.priorAccrual || 0,
      priorUsage: item.priorUsage || 0,
      priorEnd: item.priorEnd || 0,
      changeAmount: 0,
      changeRate: 0,
      remark: item.remark || '',
    }))
    _triggerSaveAll()
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const computed = computedRows.value[rowIndex]
    // 保存审定期末（供CrossSheet勾稽）
    if (computed) {
      debouncedSave(`M7-2-row-${rowIndex}-auditedEnd`, {
        remark: String(computed.auditedEnd),
      })
    }
    // 保存行完整数据
    debouncedSave(`M7-2-row-${rowIndex}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        beginning: row.beginning,
        creditAccrual: row.creditAccrual,
        debitExpense: row.debitExpense,
        debitCapital: row.debitCapital,
        beginAje: row.beginAje,
        beginRje: row.beginRje,
        accrualAje: row.accrualAje,
        accrualRje: row.accrualRje,
        usageAje: row.usageAje,
        usageRje: row.usageRje,
        priorBeginning: row.priorBeginning,
        priorAccrual: row.priorAccrual,
        priorUsage: row.priorUsage,
        priorEnd: row.priorEnd,
        remark: row.remark,
      }),
    })
    // 保存明细表审定期末合计（供M7-1交叉验证）
    debouncedSave('M7-2-auditedEndTotal', {
      remark: String(totalAuditedEnd.value),
    })
  }

  function _triggerSaveAll(): void {
    computedRows.value.forEach((_, i) => {
      _triggerSave(i)
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    totals,
    totalCreditAccrual,
    totalDebitUsage,
    totalAuditedEnd,

    // 行操作
    addRow,
    removeRow,
    updateRow,

    // 导入导出
    prepareExportData,
    importData,
  }
}

export default useM7Detail
