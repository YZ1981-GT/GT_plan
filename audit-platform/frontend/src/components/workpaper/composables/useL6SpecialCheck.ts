/**
 * useL6SpecialCheck — L6-4 专款专用检查表 composable
 *
 * Spec: .kiro/specs/l6-special-payables/
 * Task: 3.4
 * Requirements: 4.1-4.4
 *
 * 职责：
 * - 管理专款专用核查行（每个专项项目的用途检查）
 * - 检查凭证、核对实际用途与批准用途
 * - 实际用途≠批准用途时标记 isAbnormal=true → 红色高亮
 * - 计算检查比例（已检查金额/本期发生额）
 * - 提供审计结论区数据
 *
 * xlsx L6-4 列结构：
 *   A(专项项目) | B(凭证日期) | C(凭证号) | D(经济内容)
 *   E(对方科目) | F(借方金额) | G(贷方金额) | H(支持文件)
 *   I~M(检查项1~5: 用途合规/金额准确/手续完备/进度匹配/结余处理)
 *   N(索引) | O(是否异常) | P(备注)
 *
 * 科目：2601 专项应付款（贷方/负债类）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { calcCheckRatio, calcSubtotal } from './useL6FormulaEngine'
import type { useL6FormData } from './useL6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 检查项状态 */
export type CheckStatus = '是' | '否' | '不适用' | ''

/** L6-4 专款专用检查表行数据 */
export interface L6SpecialCheckRow {
  /** 行唯一标识 */
  key: string
  /** 专项项目（A列） */
  project: string
  /** 凭证日期（B列） */
  voucherDate: string
  /** 凭证号（C列） */
  voucherNo: string
  /** 经济内容（D列） */
  content: string
  /** 对方科目（E列） */
  counterAccount: string
  /** 借方金额（F列） */
  debitAmt: number
  /** 贷方金额（G列） */
  creditAmt: number
  /** 支持文件（H列） */
  supportDoc: string
  /** 检查项1：用途合规（I列） */
  check1: CheckStatus
  /** 检查项2：金额准确（J列） */
  check2: CheckStatus
  /** 检查项3：手续完备（K列） */
  check3: CheckStatus
  /** 检查项4：进度匹配（L列） */
  check4: CheckStatus
  /** 检查项5：结余处理合规（M列） */
  check5: CheckStatus
  /** 索引（N列） */
  indexRef: string
  /** 是否异常（O列：实际用途≠批准用途） */
  isAbnormal: boolean
  /** 备注（P列） */
  remark: string
}

/** 审计结论区数据 */
export interface L6AuditConclusion {
  /** 检查总金额（借方合计） */
  totalChecked: number
  /** 检查比例 */
  checkRatio: number
  /** 异常项目数量 */
  abnormalCount: number
  /** 结论文本 */
  conclusionText: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 检查项标签 */
export const CHECK_LABELS = [
  '用途合规',
  '金额准确',
  '手续完备',
  '进度匹配',
  '结余处理合规',
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L6-4 专款专用检查表业务逻辑
 *
 * @param formData 由调用方传入的 useL6FormData 实例
 * @param checkRows reactive ref of check rows
 * @param totalPeriodAmount 本期发生额（拨入+结转+返还之和，用于计算检查比例）
 */
export function useL6SpecialCheck(
  formData: ReturnType<typeof useL6FormData>,
  checkRows: Ref<L6SpecialCheckRow[]>,
  totalPeriodAmount: Ref<number>,
) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. 审计结论文本 ──────────────────────────────────────────────────

  const conclusionText = ref('')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 已检查总金额（借方发生额合计） */
  const totalCheckedAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(checkRows.value.map(r => r.debitAmt))
  })

  /** 检查比例（已检查/本期发生额） */
  const checkRatio: ComputedRef<number> = computed(() => {
    return calcCheckRatio(totalCheckedAmount.value, totalPeriodAmount.value)
  })

  /** 异常项目数量（isAbnormal=true） */
  const abnormalCount: ComputedRef<number> = computed(() => {
    return checkRows.value.filter(r => r.isAbnormal).length
  })

  /** 异常项目列表（红色高亮行） */
  const abnormalRows: ComputedRef<L6SpecialCheckRow[]> = computed(() => {
    return checkRows.value.filter(r => r.isAbnormal)
  })

  /** 按专项项目分组的检查行 */
  const rowsByProject: ComputedRef<Record<string, L6SpecialCheckRow[]>> = computed(() => {
    const result: Record<string, L6SpecialCheckRow[]> = {}
    for (const row of checkRows.value) {
      const key = row.project || '未分类'
      if (!result[key]) result[key] = []
      result[key].push(row)
    }
    return result
  })

  /** 审计结论区汇总数据 */
  const auditConclusion: ComputedRef<L6AuditConclusion> = computed(() => {
    return {
      totalChecked: totalCheckedAmount.value,
      checkRatio: checkRatio.value,
      abnormalCount: abnormalCount.value,
      conclusionText: conclusionText.value,
    }
  })

  // ─── 3. 行操作 ────────────────────────────────────────────────────────

  /** 新增检查行 */
  function addRow(project?: string): void {
    const key = `l6-check-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: L6SpecialCheckRow = {
      key,
      project: project || '',
      voucherDate: '',
      voucherNo: '',
      content: '',
      counterAccount: '',
      debitAmt: 0,
      creditAmt: 0,
      supportDoc: '',
      check1: '',
      check2: '',
      check3: '',
      check4: '',
      check5: '',
      indexRef: '',
      isAbnormal: false,
      remark: '',
    }
    checkRows.value.push(newRow)
    _triggerSave(checkRows.value.length - 1)
  }

  /** 删除检查行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= checkRows.value.length) return
    checkRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  /** 更新检查行字段 */
  function updateRow(
    index: number,
    field: keyof L6SpecialCheckRow,
    value: string | number | boolean,
  ): void {
    if (index < 0 || index >= checkRows.value.length) return
    const row = checkRows.value[index] as any
    row[field] = value

    // 如果检查项1"用途合规"标记为"否"，自动标记 isAbnormal
    if (field === 'check1') {
      row.isAbnormal = value === '否'
    }

    _triggerSave(index)
  }

  /** 更新审计结论文本 */
  function updateConclusion(text: string): void {
    conclusionText.value = text
    debouncedSave('L6-L6-4-conclusion', { remark: text })
  }

  // ─── 4. 保存 ──────────────────────────────────────────────────────────

  /** 批量保存所有检查行+结论 */
  async function saveAll(): Promise<void> {
    const items = checkRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `L6-L6-4-row-${n}-project`, data: { remark: row.project } },
        { itemId: `L6-L6-4-row-${n}-voucher`, data: { remark: `${row.voucherDate}|${row.voucherNo}` } },
        { itemId: `L6-L6-4-row-${n}-content`, data: { remark: row.content || null } },
        { itemId: `L6-L6-4-row-${n}-counter`, data: { remark: row.counterAccount || null } },
        { itemId: `L6-L6-4-row-${n}-debit`, data: { remark: row.debitAmt ? String(row.debitAmt) : null } },
        { itemId: `L6-L6-4-row-${n}-credit`, data: { remark: row.creditAmt ? String(row.creditAmt) : null } },
        { itemId: `L6-L6-4-row-${n}-checks`, data: { remark: JSON.stringify([row.check1, row.check2, row.check3, row.check4, row.check5]) } },
        { itemId: `L6-L6-4-row-${n}-abnormal`, data: { remark: row.isAbnormal ? '1' : '0' } },
        { itemId: `L6-L6-4-row-${n}-ref`, data: { remark: row.indexRef || null } },
      ]
    }).flat()

    // 结论
    items.push({
      itemId: 'L6-L6-4-conclusion',
      data: { remark: conclusionText.value || null },
    })

    // 汇总数据（供跨sheet读取）
    items.push({
      itemId: 'L6-L6-4-summary',
      data: {
        remark: JSON.stringify({
          totalChecked: totalCheckedAmount.value,
          checkRatio: checkRatio.value,
          abnormalCount: abnormalCount.value,
        }),
      },
    })

    await saveBatch(items)
  }

  // ─── 5. 内部保存触发 ──────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = checkRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`L6-L6-4-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        project: row.project,
        voucherDate: row.voucherDate,
        voucherNo: row.voucherNo,
        debitAmt: row.debitAmt,
        creditAmt: row.creditAmt,
        isAbnormal: row.isAbnormal,
        check1: row.check1,
      }),
    })
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < checkRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    conclusionText,

    // 计算属性
    totalCheckedAmount,
    checkRatio,
    abnormalCount,
    abnormalRows,
    rowsByProject,
    auditConclusion,

    // 行操作
    addRow,
    removeRow,
    updateRow,
    updateConclusion,

    // 保存
    saveAll,
  }
}

export default useL6SpecialCheck
