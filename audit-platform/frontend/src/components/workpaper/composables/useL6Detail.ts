/**
 * useL6Detail — L6-2 明细表 composable（33列区段Tab管理）
 *
 * Spec: .kiro/specs/l6-special-payables/
 * Task: 3.4
 * Requirements: 3.1-3.5
 *
 * 职责：
 * - 33列按3区段Tab管理（项目信息/资金变动/用途核查，行同步）
 * - 动态行增删（先弹ElMessageBox.prompt输入专项项目名称）
 * - 期末余额计算：负债类 期末=期初+本期拨入-本期使用-本期结转
 * - 与L6-1审定表合计交叉验证
 * - 支持导入导出
 *
 * 明细表L6-2列结构（33列）：
 *   A(序号) | B(专项项目) | C(拨款来源) | D(批文号) | E(用途)
 *   F(期初余额) | G(本期拨入/贷方) | H(本期结转/借方) | I(本期返还/借方)
 *   J(期末余额=F+G-H-I)
 *   K~N(AJE: 期初AJE/拨入AJE/结转AJE/返还AJE)
 *   O~R(RJE: 期初RJE/拨入RJE/结转RJE/返还RJE)
 *   S(审定期初) | T(审定拨入) | U(审定结转) | V(审定返还) | W(审定期末)
 *   X(底稿索引) | Y(凭证索引) | Z(完成状态) | AA(备注)
 *
 * 科目：2601 专项应付款（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcDetailEndBalance, calcSubtotal } from './useL6FormulaEngine'
import type { useL6FormData } from './useL6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L6-2 明细表行数据（33列） */
export interface L6DetailRow {
  /** 行唯一标识（多区段共享） */
  key: string
  /** 序号 */
  seq: number
  /** 专项项目名称（B列） */
  project: string
  /** 拨款来源（C列） */
  fundSource: string
  /** 批文号（D列） */
  approvalNo: string
  /** 用途（E列） */
  purpose: string
  /** 期初余额（F列） */
  beginBalance: number
  /** 本期拨入/贷方（G列） */
  creditIn: number
  /** 本期结转/借方（H列） */
  carryForward: number
  /** 本期返还/借方（I列） */
  refund: number
  /** 期末余额（J列，公式=F+G-H-I） */
  endBalance: number
  /** 期初AJE（K列） */
  ajeBegin: number
  /** 拨入AJE（L列） */
  ajeCredit: number
  /** 结转AJE（M列） */
  ajeCarryFwd: number
  /** 返还AJE（N列） */
  ajeRefund: number
  /** 期初RJE（O列） */
  rjeBegin: number
  /** 拨入RJE（P列） */
  rjeCredit: number
  /** 结转RJE（Q列） */
  rjeCarryFwd: number
  /** 返还RJE（R列） */
  rjeRefund: number
  /** 审定期初（S列） */
  auditedBegin: number
  /** 审定拨入（T列） */
  auditedCredit: number
  /** 审定结转（U列） */
  auditedCarryFwd: number
  /** 审定返还（V列） */
  auditedRefund: number
  /** 审定期末（W列，公式=S+T-U-V） */
  auditedEnd: number
  /** 底稿索引（X列） */
  docRef: string
  /** 凭证索引（Y列） */
  indexRef: string
  /** 完成状态（Z列） */
  completionStatus: string
  /** 备注（AA列） */
  remark: string
}

/** 区段Tab类型：3区段 */
export type L6DetailSegment = 'project-info' | 'fund-movement' | 'usage-check'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：33列拆3段（项目信息/资金变动/用途核查） */
export const L6_DETAIL_SEGMENTS = [
  {
    key: 'project-info' as const,
    label: '项目信息',
    fields: [
      'seq', 'project', 'fundSource', 'approvalNo', 'purpose',
      'beginBalance', 'creditIn', 'carryForward', 'refund', 'endBalance',
    ],
  },
  {
    key: 'fund-movement' as const,
    label: '资金变动',
    fields: [
      'ajeBegin', 'ajeCredit', 'ajeCarryFwd', 'ajeRefund',
      'rjeBegin', 'rjeCredit', 'rjeCarryFwd', 'rjeRefund',
    ],
  },
  {
    key: 'usage-check' as const,
    label: '用途核查',
    fields: [
      'auditedBegin', 'auditedCredit', 'auditedCarryFwd', 'auditedRefund', 'auditedEnd',
      'docRef', 'indexRef', 'completionStatus', 'remark',
    ],
  },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L6-2 明细表业务逻辑（33列区段Tab）
 *
 * @param formData 由调用方传入的 useL6FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useL6Detail(
  formData: ReturnType<typeof useL6FormData>,
  detailRows: Ref<L6DetailRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<L6DetailSegment>('project-info')

  function switchSegment(segment: L6DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：负债类期末余额 ─────────────────────────────────────────

  /** 各行期末余额自动计算（负债类：期初+拨入-结转-返还） */
  const computedRows: ComputedRef<L6DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      // 未审期末 = 期初 + 拨入(贷方) - 结转(借方) - 返还(借方)
      const endBalance = calcDetailEndBalance(row.beginBalance, row.creditIn, row.carryForward, row.refund)
      // 审定期末 = 审定期初 + 审定拨入 - 审定结转 - 审定返还
      const auditedEnd = calcDetailEndBalance(row.auditedBegin, row.auditedCredit, row.auditedCarryFwd, row.auditedRefund)
      return {
        ...row,
        endBalance,
        auditedEnd,
      }
    })
  })

  /** 期末余额合计（供L6-1交叉验证） */
  const totalEndBalance: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.endBalance))
  })

  /** 审定期末合计 */
  const totalAuditedEnd: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.auditedEnd))
  })

  /** 期初余额合计 */
  const totalBeginBalance: ComputedRef<number> = computed(() => {
    return calcSubtotal(detailRows.value.map(r => r.beginBalance))
  })

  /** 本期拨入合计 */
  const totalCreditIn: ComputedRef<number> = computed(() => {
    return calcSubtotal(detailRows.value.map(r => r.creditIn))
  })

  /** 本期结转合计 */
  const totalCarryForward: ComputedRef<number> = computed(() => {
    return calcSubtotal(detailRows.value.map(r => r.carryForward))
  })

  /** 本期返还合计 */
  const totalRefund: ComputedRef<number> = computed(() => {
    return calcSubtotal(detailRows.value.map(r => r.refund))
  })

  // ─── 3. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入专项项目名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: project } = await ElMessageBox.prompt(
        '请输入专项项目名称',
        '新增专项应付款明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：XX科研经费/XX基建项目/XX扶贫资金',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '专项项目名称不能为空'
            return true
          },
        },
      )

      const key = `l6-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newSeq = detailRows.value.length + 1
      const newRow: L6DetailRow = {
        key,
        seq: newSeq,
        project: project?.trim() || '',
        fundSource: '',
        approvalNo: '',
        purpose: '',
        beginBalance: 0,
        creditIn: 0,
        carryForward: 0,
        refund: 0,
        endBalance: 0,
        ajeBegin: 0,
        ajeCredit: 0,
        ajeCarryFwd: 0,
        ajeRefund: 0,
        rjeBegin: 0,
        rjeCredit: 0,
        rjeCarryFwd: 0,
        rjeRefund: 0,
        auditedBegin: 0,
        auditedCredit: 0,
        auditedCarryFwd: 0,
        auditedRefund: 0,
        auditedEnd: 0,
        docRef: '',
        indexRef: '',
        completionStatus: '',
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
    // 重新编号
    detailRows.value.forEach((r, i) => { r.seq = i + 1 })
    _triggerSaveAll()
  }

  /** 更新某行某字段 */
  function updateRow(index: number, field: keyof L6DetailRow, value: string | number): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value

    // 如果是金额字段，重算期末余额
    if (['beginBalance', 'creditIn', 'carryForward', 'refund'].includes(field)) {
      row.endBalance = calcDetailEndBalance(row.beginBalance, row.creditIn, row.carryForward, row.refund)
    }
    if (['auditedBegin', 'auditedCredit', 'auditedCarryFwd', 'auditedRefund'].includes(field)) {
      row.auditedEnd = calcDetailEndBalance(row.auditedBegin, row.auditedCredit, row.auditedCarryFwd, row.auditedRefund)
    }

    _triggerSave(index)
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    // 保存行的期末余额（供CrossSheet勾稽读取）
    const computed = computedRows.value[rowIndex]
    if (computed) {
      debouncedSave(`L6-L6-2-row-${rowIndex + 1}-end_balance`, {
        remark: String(computed.endBalance),
      })
    }
    // 保存行完整数据
    debouncedSave('L6-L6-2-rows', {
      remark: JSON.stringify(detailRows.value.map((r, i) => ({
        key: r.key,
        project: r.project,
        endBalance: computedRows.value[i]?.endBalance ?? 0,
        auditedEnd: computedRows.value[i]?.auditedEnd ?? 0,
      }))),
    })
  }

  function _triggerSaveAll(): void {
    // 保存所有行的 end_balance（供CrossSheet读取）
    computedRows.value.forEach((row, i) => {
      debouncedSave(`L6-L6-2-row-${i + 1}-end_balance`, {
        remark: String(row.endBalance),
      })
    })
    debouncedSave('L6-L6-2-rows', {
      remark: JSON.stringify(detailRows.value.map((r, i) => ({
        key: r.key,
        project: r.project,
        endBalance: computedRows.value[i]?.endBalance ?? 0,
        auditedEnd: computedRows.value[i]?.auditedEnd ?? 0,
      }))),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    totalEndBalance,
    totalAuditedEnd,
    totalBeginBalance,
    totalCreditIn,
    totalCarryForward,
    totalRefund,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL6Detail
