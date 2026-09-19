/**
 * useM6Detail — M6-2 明细表 composable（利润分配结转核心公式链！）
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 管理M6-2明细表数据（32×19，63 formula cells）
 * - 利润分配结转公式链：期末=期初+本年净利润-提取盈余公积-分配股利
 * - 列结构：项目 | 未审期初 | 调整期初 | 审定期初 | 本年净利润 | 可供分配利润
 *           | 提取法定盈余公积 | 提取任意盈余公积 | 应付普通股股利 | 应付优先股股利
 *           | 其他分配 | 期末未分配利润 | 前期差错更正 | 会计政策变更
 *           | AJE | RJE | 备注 | 索引号 | 来源
 * - 13公式前端实时计算并逐行勾稽
 * - 动态行新增（ElMessageBox.prompt 命名后创建）
 * - 与M6-1审定表合计交叉验证
 * - 使用 calcRetainedEnd / calcDistributable from useM6DistributionEngine
 *
 * 科目：4104 利润分配-未分配利润（**贷方/权益类！期末=期初+贷方-借方**）
 * 利润分配结转核心：期末=期初+本年净利润-提取盈余公积-分配股利
 *
 * 32×19结构，13公式（63 formula cells）
 */
import { computed, ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcSubtotal } from './useM6FormulaEngine'
import { calcRetainedEnd, calcDistributable, calcLinkageDiff } from './useM6DistributionEngine'
import type { useM6FormData } from './useM6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细行分类 */
export type M6DetailCategory =
  | 'retained-beginning'     // 期初未分配利润
  | 'net-profit'             // 本年净利润
  | 'distributable'          // 可供分配利润（公式行）
  | 'statutory-surplus'      // 提取法定盈余公积
  | 'discretionary-surplus'  // 提取任意盈余公积
  | 'ordinary-dividend'      // 应付普通股股利
  | 'preferred-dividend'     // 应付优先股股利
  | 'other-distribution'     // 其他分配
  | 'retained-end'           // 期末未分配利润（公式行）
  | 'prior-error'            // 前期差错更正（调整年初）
  | 'policy-change'          // 会计政策变更（调整年初）
  | 'adjustment'             // 调整行（动态）

/** M6-2 明细表行数据（19列结构） */
export interface M6DetailRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 行分类 */
  category: M6DetailCategory
  /** 是否公式行（不可编辑金额） */
  isFormula: boolean
  /** 未审金额 */
  unadjustedAmount: number
  /** AJE调整 */
  ajeAmount: number
  /** RJE调整 */
  rjeAmount: number
  /** 审定金额（公式=未审+AJE+RJE 或 公式行由结转计算） */
  auditedAmount: number
  /** 备注 */
  remark: string
  /** 索引号 */
  refIndex: string
  /** 来源（GtIndexChip跳转目标） */
  source: string
}

/** 利润分配结转汇总 */
export interface M6DistributionSummary {
  /** 期初未分配利润 */
  retainedBeginning: number
  /** 本年净利润 */
  netProfit: number
  /** 可供分配利润 = 期初 + 本年净利润 */
  distributable: number
  /** 提取法定盈余公积 */
  statutorySurplus: number
  /** 提取任意盈余公积 */
  discretionarySurplus: number
  /** 盈余公积合计 = 法定 + 任意 */
  totalSurplus: number
  /** 应付普通股股利 */
  ordinaryDividend: number
  /** 应付优先股股利 */
  preferredDividend: number
  /** 其他分配 */
  otherDistribution: number
  /** 股利合计 = 普通 + 优先 + 其他 */
  totalDividend: number
  /** 期末未分配利润 = 可供分配 - 盈余公积 - 股利 */
  retainedEnd: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M6-2 明细表业务逻辑（利润分配结转公式链！13公式+动态行）
 *
 * @param formData 由调用方传入的 useM6FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useM6Detail(
  formData: ReturnType<typeof useM6FormData>,
  detailRows: { value: M6DetailRow[] },
) {
  const { debouncedSave } = formData

  // ─── 1. 计算属性：13公式实时计算 ───────────────────────────────────────

  /** 各行审定金额计算（非公式行：审定=未审+AJE+RJE） */
  const computedRows: ComputedRef<M6DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      if (row.isFormula) {
        // 公式行金额由结转汇总计算赋值，此处仅透传
        return row
      }
      // 普通行：审定=未审+AJE+RJE
      const auditedAmount = row.unadjustedAmount + row.ajeAmount + row.rjeAmount
      return { ...row, auditedAmount }
    })
  })

  // ─── 2. 利润分配结转汇总（核心！13公式） ──────────────────────────────

  /** 利润分配结转汇总 */
  const distributionSummary: ComputedRef<M6DistributionSummary> = computed(() => {
    const r = computedRows.value

    // 按分类汇总审定金额
    const retainedBeginning = _sumByCategory(r, 'retained-beginning')
    const netProfit = _sumByCategory(r, 'net-profit')
    const priorError = _sumByCategory(r, 'prior-error')
    const policyChange = _sumByCategory(r, 'policy-change')

    // 调整后期初 = 期初 + 前期差错 + 会计政策变更
    const adjustedBeginning = retainedBeginning + priorError + policyChange

    // 可供分配利润 = 调整后期初 + 本年净利润（P4公式）
    const distributable = calcDistributable(adjustedBeginning, netProfit)

    // 盈余公积
    const statutorySurplus = _sumByCategory(r, 'statutory-surplus')
    const discretionarySurplus = _sumByCategory(r, 'discretionary-surplus')
    const totalSurplus = statutorySurplus + discretionarySurplus

    // 股利
    const ordinaryDividend = _sumByCategory(r, 'ordinary-dividend')
    const preferredDividend = _sumByCategory(r, 'preferred-dividend')
    const otherDistribution = _sumByCategory(r, 'other-distribution')
    const totalDividend = ordinaryDividend + preferredDividend + otherDistribution

    // 期末未分配利润 = 可供分配 - 盈余公积 - 股利（P3核心公式链！）
    const retainedEnd = calcRetainedEnd(adjustedBeginning, netProfit, totalSurplus, totalDividend)

    return {
      retainedBeginning: adjustedBeginning,
      netProfit,
      distributable,
      statutorySurplus,
      discretionarySurplus,
      totalSurplus,
      ordinaryDividend,
      preferredDividend,
      otherDistribution,
      totalDividend,
      retainedEnd,
    }
  })

  function _sumByCategory(rows: M6DetailRow[], category: M6DetailCategory): number {
    return calcSubtotal(
      rows.filter(r => r.category === category).map(r => r.auditedAmount),
    )
  }

  // ─── 3. 联动差异核对（M5/M1） ────────────────────────────────────────

  /** M6记录的盈余公积 vs M5实际计提 的差异 */
  const surplusLinkageRef = ref<number>(0) // M5实际计提额（由CrossSheet注入）

  /** M6记录的股利 vs M1实际宣告 的差异 */
  const dividendLinkageRef = ref<number>(0) // M1实际宣告额（由CrossSheet注入）

  /** 盈余公积联动差异 */
  const surplusLinkageDiff: ComputedRef<{ diff: number; isConsistent: boolean }> = computed(() => {
    const diff = calcLinkageDiff(distributionSummary.value.totalSurplus, surplusLinkageRef.value)
    return { diff, isConsistent: Math.abs(diff) < 0.01 }
  })

  /** 股利联动差异 */
  const dividendLinkageDiff: ComputedRef<{ diff: number; isConsistent: boolean }> = computed(() => {
    const diff = calcLinkageDiff(distributionSummary.value.totalDividend, dividendLinkageRef.value)
    return { diff, isConsistent: Math.abs(diff) < 0.01 }
  })

  /** 设置M5联动值（由CrossSheet调用） */
  function setSurplusLinkage(m5Accrual: number): void {
    surplusLinkageRef.value = m5Accrual
  }

  /** 设置M1联动值（由CrossSheet调用） */
  function setDividendLinkage(m1Declared: number): void {
    dividendLinkageRef.value = m1Declared
  }

  // ─── 4. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入名称）
   */
  async function addRow(category?: M6DetailCategory): Promise<void> {
    const targetCategory = category || 'adjustment'
    const categoryLabel = _getCategoryLabel(targetCategory)

    try {
      const { value: itemName } = await ElMessageBox.prompt(
        `请输入${categoryLabel}项目名称`,
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：补提法定盈余公积、特别股利等',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            return true
          },
        },
      )

      const key = `m6-det-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: M6DetailRow = {
        key,
        itemName: itemName?.trim() || '',
        category: targetCategory,
        isFormula: false,
        unadjustedAmount: 0,
        ajeAmount: 0,
        rjeAmount: 0,
        auditedAmount: 0,
        remark: '',
        refIndex: '',
        source: '',
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
    const row = detailRows.value[index]
    // 公式行不可删除
    if (row.isFormula) return
    detailRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  /** 更新某行某字段 */
  function updateRow(index: number, field: keyof M6DetailRow, value: string | number): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    // 公式行金额字段不可手动修改
    if (row.isFormula && ['unadjustedAmount', 'ajeAmount', 'rjeAmount', 'auditedAmount'].includes(field as string)) {
      return
    }
    row[field] = value

    // 金额字段变动→重算审定
    if (['unadjustedAmount', 'ajeAmount', 'rjeAmount'].includes(field as string)) {
      row.auditedAmount = row.unadjustedAmount + row.ajeAmount + row.rjeAmount
    }

    _triggerSave(index)
  }

  // ─── 5. 与M6-1审定表交叉验证 ─────────────────────────────────────────

  /**
   * 与M6-1审定表交叉验证
   * M6-2明细结转后的期末 === M6-1审定表期末余额
   */
  function crossValidateWithAdjudication(
    adjudicationEndBalance: number,
  ): { diff: number; isMatch: boolean } {
    const diff = distributionSummary.value.retainedEnd - adjudicationEndBalance
    const isMatch = Math.abs(diff) < 0.01
    return { diff, isMatch }
  }

  // ─── 6. 辅助方法 ─────────────────────────────────────────────────────

  function _getCategoryLabel(category: M6DetailCategory): string {
    const labels: Record<M6DetailCategory, string> = {
      'retained-beginning': '期初未分配利润',
      'net-profit': '本年净利润',
      'distributable': '可供分配利润',
      'statutory-surplus': '提取法定盈余公积',
      'discretionary-surplus': '提取任意盈余公积',
      'ordinary-dividend': '应付普通股股利',
      'preferred-dividend': '应付优先股股利',
      'other-distribution': '其他分配',
      'retained-end': '期末未分配利润',
      'prior-error': '前期差错更正',
      'policy-change': '会计政策变更',
      'adjustment': '调整项目',
    }
    return labels[category] || '其他'
  }

  // ─── 7. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M6-2-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        category: row.category,
        isFormula: row.isFormula,
        unadjustedAmount: row.unadjustedAmount,
        ajeAmount: row.ajeAmount,
        rjeAmount: row.rjeAmount,
        remark: row.remark,
        refIndex: row.refIndex,
        source: row.source,
      }),
    })
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < detailRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算属性
    computedRows,
    // 利润分配结转汇总（核心！）
    distributionSummary,
    // 联动差异
    surplusLinkageDiff,
    dividendLinkageDiff,
    setSurplusLinkage,
    setDividendLinkage,
    // 行操作
    addRow,
    removeRow,
    updateRow,
    // 交叉验证
    crossValidateWithAdjudication,
  }
}

export default useM6Detail
