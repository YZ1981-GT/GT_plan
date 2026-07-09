/**
 * useN5DeferredReconcile — N5-8 递延所得税费用核对表 composable
 *
 * Spec: .kiro/specs/n5-income-tax-expense/
 * Task: 3.4
 * Requirements: 8.1-8.5
 *
 * 职责：
 * - 管理N5-8数据（递延所得税核对项）
 * - Uses calcDeferredTaxExpense from useN5IncomeTaxEngine
 * - Uses calcSubtotal from useN5FormulaEngine
 * - 订阅N1 'deferred-tax:asset-updated' + N3 'deferred-tax:liability-updated' 接收本期变动
 * - 计算递延所得税费用 = 递延税负债本期增加 - 递延税资产本期增加
 * - 与N1/N3交叉验证
 * - 递延所得税费用回填N5-1审定表
 *
 * 科目：6801 所得税费用（损益类，递延部分）
 */
import { computed, ref, onMounted, onUnmounted, type ComputedRef, type Ref } from 'vue'
import { calcDeferredTaxExpense } from './useN5IncomeTaxEngine'
import { calcSubtotal, parseNum } from './useN5FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useN5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 递延核对明细行 */
export interface N5DeferredReconcileRow {
  /** 行序号 */
  index: number
  /** 项目名称（暂时性差异项目） */
  label: string
  /** 递延税资产-期初 */
  assetBeginning: number
  /** 递延税资产-期末 */
  assetEnding: number
  /** 递延税资产-本期变动（= 期末 - 期初） */
  assetChange: number
  /** 递延税负债-期初 */
  liabilityBeginning: number
  /** 递延税负债-期末 */
  liabilityEnding: number
  /** 递延税负债-本期变动（= 期末 - 期初） */
  liabilityChange: number
  /** 递延所得税费用（= 负债变动 - 资产变动） */
  deferredExpense: number
  /** 备注 */
  remark: string
}

/** 递延核对汇总 */
export interface N5DeferredReconcileSummary {
  /** 递延税资产本期变动合计 */
  totalAssetChange: number
  /** 递延税负债本期变动合计 */
  totalLiabilityChange: number
  /** 递延所得税费用 = 负债变动合计 - 资产变动合计 */
  deferredTaxExpense: number
  /** 与N1核对差异 */
  n1Diff: number
  /** 与N3核对差异 */
  n3Diff: number
  /** 是否通过核对 */
  isReconciled: boolean
}

/** N1/N3 EventBus传入的变动数据 */
export interface DeferredTaxChangePayload {
  /** 本期变动金额 */
  periodChange: number
  /** 期末余额 */
  endingBalance: number
  /** 期初余额 */
  beginningBalance: number
  /** 来源底稿编码 */
  wpCode: string
  /** 时间戳 */
  timestamp: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN5DeferredReconcileOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN5DeferredReconcile(options: UseN5DeferredReconcileOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. N1/N3 EventBus 订阅数据 ──────────────────────────────────────────

  /** N1递延税资产本期变动（来自EventBus或手填） */
  const n1AssetChange = ref<number>(0)
  /** N3递延税负债本期变动（来自EventBus或手填） */
  const n3LiabilityChange = ref<number>(0)

  // 订阅N1/N3事件
  function _onAssetUpdated(payload: any) {
    const data = payload as DeferredTaxChangePayload
    n1AssetChange.value = parseNum(data.periodChange)
    // 持久化到 checklist_responses
    saveField('8', 'n1-asset-change', data.periodChange)
  }

  function _onLiabilityUpdated(payload: any) {
    const data = payload as DeferredTaxChangePayload
    n3LiabilityChange.value = parseNum(data.periodChange)
    // 持久化到 checklist_responses
    saveField('8', 'n3-liability-change', data.periodChange)
  }

  // EventBus 订阅/取消订阅
  let _unsubAsset: (() => void) | null = null
  let _unsubLiability: (() => void) | null = null

  function _subscribe() {
    _unsubAsset = () => eventBus.off('deferred-tax:asset-updated', _onAssetUpdated)
    _unsubLiability = () => eventBus.off('deferred-tax:liability-updated', _onLiabilityUpdated)
    eventBus.on('deferred-tax:asset-updated', _onAssetUpdated)
    eventBus.on('deferred-tax:liability-updated', _onLiabilityUpdated)
  }

  function _unsubscribe() {
    _unsubAsset?.()
    _unsubLiability?.()
    _unsubAsset = null
    _unsubLiability = null
  }

  onMounted(() => {
    _subscribe()
    // 从持久化数据恢复
    const savedAsset = getField('8', 'n1-asset-change')
    const savedLiab = getField('8', 'n3-liability-change')
    if (savedAsset != null) n1AssetChange.value = parseNum(savedAsset)
    if (savedLiab != null) n3LiabilityChange.value = parseNum(savedLiab)
  })

  onUnmounted(() => {
    _unsubscribe()
  })

  // ─── 2. 核对项行数据 ─────────────────────────────────────────────────────

  const rows: ComputedRef<N5DeferredReconcileRow[]> = computed(() => {
    const itemId = 'N5-8-reconcile-rows'
    const resp = allResponses.value.get(itemId)
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }

    if (raw.length === 0) return _getDefaultRows()

    return raw.map((r: any, i: number) => {
      const assetBeginning = parseNum(r.assetBeginning)
      const assetEnding = parseNum(r.assetEnding)
      const assetChange = assetEnding - assetBeginning
      const liabilityBeginning = parseNum(r.liabilityBeginning)
      const liabilityEnding = parseNum(r.liabilityEnding)
      const liabilityChange = liabilityEnding - liabilityBeginning
      const deferredExpense = calcDeferredTaxExpense(liabilityChange, assetChange)

      return {
        index: i + 1,
        label: r.label || `项目${i + 1}`,
        assetBeginning,
        assetEnding,
        assetChange,
        liabilityBeginning,
        liabilityEnding,
        liabilityChange,
        deferredExpense,
        remark: r.remark || '',
      }
    })
  })

  // ─── 3. 汇总合计 ─────────────────────────────────────────────────────────

  const totalAssetChange: ComputedRef<number> = computed(() => {
    return calcSubtotal(rows.value.map(r => r.assetChange))
  })

  const totalLiabilityChange: ComputedRef<number> = computed(() => {
    return calcSubtotal(rows.value.map(r => r.liabilityChange))
  })

  /** 递延所得税费用 = 递延税负债本期增加 - 递延税资产本期增加 */
  const deferredTaxExpense: ComputedRef<number> = computed(() => {
    return calcDeferredTaxExpense(totalLiabilityChange.value, totalAssetChange.value)
  })

  // ─── 4. 与N1/N3交叉核对 ──────────────────────────────────────────────────

  /** N1差异 = 本表资产变动合计 - N1传入变动 */
  const n1Diff: ComputedRef<number> = computed(() => {
    return parseFloat((totalAssetChange.value - n1AssetChange.value).toFixed(2))
  })

  /** N3差异 = 本表负债变动合计 - N3传入变动 */
  const n3Diff: ComputedRef<number> = computed(() => {
    return parseFloat((totalLiabilityChange.value - n3LiabilityChange.value).toFixed(2))
  })

  /** 是否通过核对（差异容忍0.01精度） */
  const isReconciled: ComputedRef<boolean> = computed(() => {
    return Math.abs(n1Diff.value) <= 0.01 && Math.abs(n3Diff.value) <= 0.01
  })

  // ─── 5. 汇总对象 ─────────────────────────────────────────────────────────

  const summary: ComputedRef<N5DeferredReconcileSummary> = computed(() => ({
    totalAssetChange: totalAssetChange.value,
    totalLiabilityChange: totalLiabilityChange.value,
    deferredTaxExpense: deferredTaxExpense.value,
    n1Diff: n1Diff.value,
    n3Diff: n3Diff.value,
    isReconciled: isReconciled.value,
  }))

  // ─── 6. 行操作 ────────────────────────────────────────────────────────────

  /**
   * 更新指定行字段
   */
  async function updateRow(
    rowIndex: number,
    field: keyof Pick<N5DeferredReconcileRow, 'label' | 'assetBeginning' | 'assetEnding' | 'liabilityBeginning' | 'liabilityEnding' | 'remark'>,
    value: number | string,
  ): Promise<void> {
    const currentRows = rows.value.map(r => ({ ...r }))
    if (rowIndex >= 0 && rowIndex < currentRows.length) {
      ;(currentRows[rowIndex] as any)[field] = value
      await _saveRows(currentRows)
    }
  }

  /**
   * 新增核对行
   */
  async function addRow(label: string): Promise<void> {
    const currentRows = rows.value.map(r => ({ ...r }))
    currentRows.push({
      index: currentRows.length + 1,
      label,
      assetBeginning: 0,
      assetEnding: 0,
      assetChange: 0,
      liabilityBeginning: 0,
      liabilityEnding: 0,
      liabilityChange: 0,
      deferredExpense: 0,
      remark: '',
    })
    await _saveRows(currentRows)
  }

  /**
   * 删除指定行
   */
  async function removeRow(rowIndex: number): Promise<void> {
    const currentRows = rows.value.filter((_, i) => i !== rowIndex)
    await _saveRows(currentRows)
  }

  /**
   * 手动设置N1变动（当EventBus未触发时手动覆盖）
   */
  async function setN1AssetChange(value: number): Promise<void> {
    n1AssetChange.value = parseNum(value)
    await saveField('8', 'n1-asset-change', value)
  }

  /**
   * 手动设置N3变动（当EventBus未触发时手动覆盖）
   */
  async function setN3LiabilityChange(value: number): Promise<void> {
    n3LiabilityChange.value = parseNum(value)
    await saveField('8', 'n3-liability-change', value)
  }

  /**
   * 同步递延所得税费用到N5-1审定表
   */
  async function syncDeferredExpenseToAdjudication(): Promise<void> {
    await saveField('1', 'deferred-tax', deferredTaxExpense.value)
  }

  // ─── 7. 内部helper ────────────────────────────────────────────────────────

  async function _saveRows(data: N5DeferredReconcileRow[]): Promise<void> {
    const itemId = 'N5-8-reconcile-rows'
    const conclusion = JSON.stringify(data)
    allResponses.value.set(itemId, {
      item_id: itemId,
      conclusion,
      remark: null,
    })
    await saveField('8', 'reconcile-rows', data)
  }

  /**
   * 默认核对项（常见暂时性差异项目）
   */
  function _getDefaultRows(): N5DeferredReconcileRow[] {
    const defaults = [
      '坏账准备',
      '存货跌价准备',
      '固定资产折旧差异',
      '无形资产摊销差异',
      '公允价值变动',
      '未弥补亏损',
      '预计负债',
      '资产减值准备',
    ]
    return defaults.map((label, i) => ({
      index: i + 1,
      label,
      assetBeginning: 0,
      assetEnding: 0,
      assetChange: 0,
      liabilityBeginning: 0,
      liabilityEnding: 0,
      liabilityChange: 0,
      deferredExpense: 0,
      remark: '',
    }))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // Reactive state
    n1AssetChange,
    n3LiabilityChange,
    // Computed
    rows,
    totalAssetChange,
    totalLiabilityChange,
    deferredTaxExpense,
    n1Diff,
    n3Diff,
    isReconciled,
    summary,
    // Actions
    updateRow,
    addRow,
    removeRow,
    setN1AssetChange,
    setN3LiabilityChange,
    syncDeferredExpenseToAdjudication,
  }
}

export default useN5DeferredReconcile
