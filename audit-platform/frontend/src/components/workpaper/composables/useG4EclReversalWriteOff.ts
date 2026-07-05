/**
 * useG4EclReversalWriteOff — G4-12 减值准备转回核销检查表
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/
 * Task: 8.3
 *
 * 职责：
 * - 转回校验逻辑（调用 isReversalValid：转回金额 ≤ 累计计提）
 * - 核销数据管理 + 关联交易标记（isRelatedParty=true → 橙色高亮）
 * - 合计行计算（调用 calcSumColumn）
 * - Tab切换行同步（activeTab + activeRowIndex 共享）
 * - 行CRUD（addReversalRow / addWriteOffRow / removeRow）
 *
 * Requirements: 5.2, 5.6
 */
import { ref, computed } from 'vue'
import { isReversalValid, calcSumColumn } from '@/composables/useG4EclFormulaEngine'
import { ElMessageBox } from 'element-plus'
import type { ReversalRow, WriteOffRow } from './useG4EclFormData'

// ─── 合计行接口 ──────────────────────────────────────────────────────────────

export interface ReversalSummary {
  totalReversalAmount: number
  totalAccumulatedProvision: number
  invalidCount: number
}

export interface WriteOffSummary {
  totalWriteOffAmount: number
  relatedPartyCount: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG4EclReversalWriteOff() {
  const reversals = ref<ReversalRow[]>([])
  const writeOffs = ref<WriteOffRow[]>([])
  const activeTab = ref<'tab1' | 'tab2'>('tab1')
  const activeRowIndex = ref(0)

  // ─── 转回校验 ─────────────────────────────────────────────────────────────

  /**
   * 判断转回行是否有效（转回金额 ≤ 累计计提）
   * Requirements: 5.2
   */
  function isRowValid(row: ReversalRow): boolean {
    return isReversalValid(row.reversalAmount, row.accumulatedProvision)
  }

  /**
   * 获取转回行的校验错误信息
   * Requirements: 5.3
   */
  function getReversalError(row: ReversalRow): string | null {
    if (!isRowValid(row)) {
      return '转回金额超过累计计提'
    }
    return null
  }

  // ─── 合计行计算 ───────────────────────────────────────────────────────────

  /**
   * Tab1转回检查合计
   * Requirements: 5.6
   */
  const reversalSummary = computed<ReversalSummary>(() => ({
    totalReversalAmount: calcSumColumn(reversals.value.map(r => r.reversalAmount)),
    totalAccumulatedProvision: calcSumColumn(reversals.value.map(r => r.accumulatedProvision)),
    invalidCount: reversals.value.filter(r => !isRowValid(r)).length,
  }))

  /**
   * Tab2核销检查合计
   * Requirements: 5.6
   */
  const writeOffSummary = computed<WriteOffSummary>(() => ({
    totalWriteOffAmount: calcSumColumn(writeOffs.value.map(r => r.writeOffAmount)),
    relatedPartyCount: writeOffs.value.filter(r => r.isRelatedParty).length,
  }))

  // ─── 关联交易标记 ─────────────────────────────────────────────────────────

  /**
   * 判断核销行是否为关联交易（用于橙色高亮）
   * Requirements: 5.4
   */
  function isRelatedPartyRow(row: WriteOffRow): boolean {
    return row.isRelatedParty === true
  }

  // ─── 行 CRUD ──────────────────────────────────────────────────────────────

  /**
   * 新增转回行（ElMessageBox.prompt输入单位名称）
   * Requirements: 5.8, 11.5
   */
  async function addReversalRow(): Promise<void> {
    const { value } = await ElMessageBox.prompt('请输入单位名称', '新增转回行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValidator: (v) => (v?.trim() ? true : '单位名称不能为空'),
    })
    if (!value?.trim()) return

    const newRow: ReversalRow = {
      id: crypto.randomUUID(),
      seq: reversals.value.length + 1,
      unitName: value.trim(),
      reversalReason: '',
      recoveryMethod: '',
      originalBasis: '',
      reversalAmount: 0,
      accumulatedProvision: 0,
      reasonAnalysis: '',
      isReasonable: '合理',
      indexRef: '',
    }
    reversals.value.push(newRow)
  }

  /**
   * 新增核销行（ElMessageBox.prompt输入单位名称）
   * Requirements: 5.8, 11.5
   */
  async function addWriteOffRow(): Promise<void> {
    const { value } = await ElMessageBox.prompt('请输入单位名称', '新增核销行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValidator: (v) => (v?.trim() ? true : '单位名称不能为空'),
    })
    if (!value?.trim()) return

    const newRow: WriteOffRow = {
      id: crypto.randomUUID(),
      seq: writeOffs.value.length + 1,
      unitName: value.trim(),
      writeOffType: '到期',
      writeOffAmount: 0,
      writeOffReason: '',
      writeOffProcedure: '',
      isRelatedParty: false,
      reasonAnalysis: '',
      isReasonable: '合理',
      indexRef: '',
    }
    writeOffs.value.push(newRow)
  }

  /**
   * 删除转回行
   */
  function removeReversalRow(id: string): void {
    reversals.value = reversals.value.filter(r => r.id !== id)
    reversals.value.forEach((r, i) => { r.seq = i + 1 })
  }

  /**
   * 删除核销行
   */
  function removeWriteOffRow(id: string): void {
    writeOffs.value = writeOffs.value.filter(r => r.id !== id)
    writeOffs.value.forEach((r, i) => { r.seq = i + 1 })
  }

  // ─── 数据加载 ─────────────────────────────────────────────────────────────

  function loadData(data: { reversals?: ReversalRow[]; writeOffs?: WriteOffRow[] }): void {
    if (data.reversals) {
      reversals.value = data.reversals.map((r, i) => ({
        ...r,
        id: r.id || crypto.randomUUID(),
        seq: i + 1,
      }))
    }
    if (data.writeOffs) {
      writeOffs.value = data.writeOffs.map((r, i) => ({
        ...r,
        id: r.id || crypto.randomUUID(),
        seq: i + 1,
      }))
    }
  }

  // ─── 导出序列化 ──────────────────────────────────────────────────────────

  function toJSON(): { reversals: ReversalRow[]; writeOffs: WriteOffRow[] } {
    return {
      reversals: reversals.value.map(r => ({ ...r })),
      writeOffs: writeOffs.value.map(r => ({ ...r })),
    }
  }

  return {
    // State
    reversals,
    writeOffs,
    activeTab,
    activeRowIndex,
    // Computed
    reversalSummary,
    writeOffSummary,
    // Validation
    isRowValid,
    getReversalError,
    isRelatedPartyRow,
    // CRUD
    addReversalRow,
    addWriteOffRow,
    removeReversalRow,
    removeWriteOffRow,
    // Data
    loadData,
    toJSON,
  }
}

export default useG4EclReversalWriteOff
