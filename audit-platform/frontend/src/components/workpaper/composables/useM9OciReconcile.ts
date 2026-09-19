/**
 * useM9OciReconcile — M9-4 OCI核对表 composable
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 3.4
 * Requirements: 4.1-4.8
 *
 * 职责：
 * - 多来源核对：G8其他权益工具投资公允变动 + J2设定受益计划重计量 + 外币折算 + 其他债权 + 套期
 * - 核对差异计算：差异 = 来源金额(税后) - 账面OCI增加（calcReconcileDiff）
 * - 13公式全部前端实时计算
 * - 阈值高亮：|差异|>阈值时红色高亮
 * - EventBus 订阅：
 *   - 'g8:fair-value-changed' 接收G8公允变动数据
 *   - 'j2:remeasured' 接收J2重计量数据
 * - 通过 cross_wp_references 关联G8、J2底稿
 *
 * 科目：4103 其他综合收益（**贷方/权益类！**）
 * OCI核对是M9底稿的核心功能，验证OCI完整性与准确性
 *
 * 42×9结构，13公式
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcReconcileDiff, calcAfterTaxNet, aggregateOci, type OciItem } from './useM9OciEngine'
import { calcSubtotal } from './useM9FormulaEngine'
import type { useM9FormData } from './useM9FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 核对来源类型 */
export type M9ReconcileSource =
  | 'G8'        // 其他权益工具投资公允价值变动（不可重分类）
  | 'J2'        // 设定受益计划重计量（不可重分类）
  | 'debt-fv'   // 其他债权投资公允变动（可重分类）
  | 'hedge'     // 现金流量套期损益（可重分类）
  | 'fx'        // 外币财务报表折算差额（可重分类）
  | 'other'     // 其他

/** OCI分类（核对维度） */
export type M9ReconcileCategory = 'nonReclass' | 'reclass'

/** 核对行数据 */
export interface M9ReconcileRow {
  /** 行唯一标识 */
  key: string
  /** 来源底稿名称/描述（A列） */
  sourceName: string
  /** 来源类型 */
  sourceType: M9ReconcileSource
  /** OCI分类 */
  category: M9ReconcileCategory
  /** 来源金额-税前（B列） */
  sourcePreTax: number
  /** 来源金额-所得税影响（C列） */
  sourceTaxEffect: number
  /** 来源金额-税后净额（D列，公式=B-C） */
  sourceAfterTax: number
  /** 账面OCI增加-贷方发生额（E列，从M9-2取） */
  bookedOciIncrease: number
  /** 核对差异（F列，公式=D-E） */
  reconcileDiff: number
  /** 差异说明（G列） */
  diffExplanation: string
  /** 来源底稿编码（H列，如G8/J2） */
  sourceWpCode: string
  /** 关联底稿ID（I列，cross_wp_references） */
  crossRefId: string
}

/** 核对汇总 */
export interface M9ReconcileSummary {
  /** 来源合计（税后） */
  totalSourceAfterTax: number
  /** 账面OCI增加合计 */
  totalBookedIncrease: number
  /** 差异合计 */
  totalDiff: number
  /** 是否全部核对一致 */
  isAllReconciled: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 核对差异阈值（超过此值红色高亮） */
const RECONCILE_THRESHOLD = 0.01

/** 默认核对来源 */
export const M9_RECONCILE_DEFAULT_SOURCES: Array<{
  name: string
  type: M9ReconcileSource
  category: M9ReconcileCategory
  wpCode: string
}> = [
  // 不可重分类
  { name: '其他权益工具投资公允价值变动', type: 'G8', category: 'nonReclass', wpCode: 'G8' },
  { name: '设定受益计划重计量', type: 'J2', category: 'nonReclass', wpCode: 'J2' },
  // 可重分类
  { name: '其他债权投资公允价值变动', type: 'debt-fv', category: 'reclass', wpCode: '' },
  { name: '现金流量套期损益', type: 'hedge', category: 'reclass', wpCode: '' },
  { name: '外币财务报表折算差额', type: 'fx', category: 'reclass', wpCode: '' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M9-4 OCI核对表业务逻辑（多来源核对 + 13公式 + 阈值高亮）
 *
 * @param formData 由调用方传入的 useM9FormData 实例
 * @param reconcileRows reactive ref of reconcile rows
 */
export function useM9OciReconcile(
  formData: ReturnType<typeof useM9FormData>,
  reconcileRows: Ref<M9ReconcileRow[]>,
) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. 计算属性：13公式全部前端实时计算 ────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M9ReconcileRow[]> = computed(() => {
    return reconcileRows.value.map(row => {
      // D=B-C 来源金额税后净额
      const sourceAfterTax = calcAfterTaxNet(row.sourcePreTax, row.sourceTaxEffect)
      // F=D-E 核对差异
      const reconcileDiff = calcReconcileDiff(sourceAfterTax, row.bookedOciIncrease)
      return { ...row, sourceAfterTax, reconcileDiff }
    })
  })

  // ─── 2. 分类过滤 ─────────────────────────────────────────────────────

  /** 不可重分类来源（G8+J2） */
  const nonReclassRows: ComputedRef<M9ReconcileRow[]> = computed(() => {
    return computedRows.value.filter(r => r.category === 'nonReclass')
  })

  /** 可重分类来源（其他债权+套期+外币折算） */
  const reclassRows: ComputedRef<M9ReconcileRow[]> = computed(() => {
    return computedRows.value.filter(r => r.category === 'reclass')
  })

  // ─── 3. 汇总 ─────────────────────────────────────────────────────────

  /** 不可重分类核对汇总 */
  const nonReclassSummary: ComputedRef<M9ReconcileSummary> = computed(() => {
    return _calcSummary(nonReclassRows.value)
  })

  /** 可重分类核对汇总 */
  const reclassSummary: ComputedRef<M9ReconcileSummary> = computed(() => {
    return _calcSummary(reclassRows.value)
  })

  /** 全部核对汇总 */
  const totalSummary: ComputedRef<M9ReconcileSummary> = computed(() => {
    return _calcSummary(computedRows.value)
  })

  /** OCI两大类汇总（aggregateOci格式，供CrossSheet） */
  const ociAggregate = computed(() => {
    const items: OciItem[] = computedRows.value.map(row => ({
      amount: row.sourceAfterTax,
      category: row.category,
    }))
    return aggregateOci(items)
  })

  function _calcSummary(rows: M9ReconcileRow[]): M9ReconcileSummary {
    const totalSourceAfterTax = calcSubtotal(rows.map(x => x.sourceAfterTax))
    const totalBookedIncrease = calcSubtotal(rows.map(x => x.bookedOciIncrease))
    const totalDiff = calcReconcileDiff(totalSourceAfterTax, totalBookedIncrease)
    const isAllReconciled = rows.every(r => Math.abs(r.reconcileDiff) <= RECONCILE_THRESHOLD)
    return { totalSourceAfterTax, totalBookedIncrease, totalDiff, isAllReconciled }
  }

  // ─── 4. 阈值高亮 ─────────────────────────────────────────────────────

  /** 差异超过阈值的行（需红色高亮） */
  const highlightedRows: ComputedRef<M9ReconcileRow[]> = computed(() => {
    return computedRows.value.filter(r => Math.abs(r.reconcileDiff) > RECONCILE_THRESHOLD)
  })

  /** 判断某行是否需要高亮 */
  function isHighlighted(row: M9ReconcileRow): boolean {
    return Math.abs(row.reconcileDiff) > RECONCILE_THRESHOLD
  }

  // ─── 5. 行操作 ────────────────────────────────────────────────────────

  /** 新增核对行 */
  function addRow(
    sourceName?: string,
    sourceType?: M9ReconcileSource,
    category?: M9ReconcileCategory,
  ): void {
    const key = `m9-reconcile-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: M9ReconcileRow = {
      key,
      sourceName: sourceName || '',
      sourceType: sourceType || 'other',
      category: category || 'nonReclass',
      sourcePreTax: 0,
      sourceTaxEffect: 0,
      sourceAfterTax: 0,
      bookedOciIncrease: 0,
      reconcileDiff: 0,
      diffExplanation: '',
      sourceWpCode: '',
      crossRefId: '',
    }
    reconcileRows.value.push(newRow)
    _triggerSaveAll()
  }

  /** 删除行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= reconcileRows.value.length) return
    reconcileRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  /** 更新行字段 */
  function updateRow(index: number, field: keyof M9ReconcileRow, value: any): void {
    if (index < 0 || index >= reconcileRows.value.length) return
    const row = reconcileRows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  // ─── 6. EventBus 订阅（接收G8/J2数据） ────────────────────────────────

  /**
   * 订阅 G8 公允价值变动事件
   * @param callback 接收G8数据的回调
   */
  function subscribeG8FairValue(
    callback: (payload: { amount: number; afterTax: number }) => void,
  ): () => void {
    const handler = (payload: any) => {
      callback({
        amount: payload?.amount || 0,
        afterTax: payload?.afterTax || payload?.amount || 0,
      })
    }
    eventBus.on('g8:fair-value-changed' as any, handler)
    return () => eventBus.off('g8:fair-value-changed' as any, handler)
  }

  /**
   * 订阅 J2 设定受益计划重计量事件
   * @param callback 接收J2数据的回调
   */
  function subscribeJ2Remeasured(
    callback: (payload: { amount: number; afterTax: number }) => void,
  ): () => void {
    const handler = (payload: any) => {
      callback({
        amount: payload?.amount || 0,
        afterTax: payload?.afterTax || payload?.amount || 0,
      })
    }
    eventBus.on('j2:remeasured' as any, handler)
    return () => eventBus.off('j2:remeasured' as any, handler)
  }

  /**
   * 从来源事件更新指定来源行的来源金额
   * @param sourceType 来源类型
   * @param preTax 税前金额
   * @param taxEffect 税额
   */
  function updateFromSource(sourceType: M9ReconcileSource, preTax: number, taxEffect: number): void {
    const rowIndex = reconcileRows.value.findIndex(r => r.sourceType === sourceType)
    if (rowIndex >= 0) {
      const row = reconcileRows.value[rowIndex]
      row.sourcePreTax = preTax
      row.sourceTaxEffect = taxEffect
      _triggerSave(rowIndex)
    }
  }

  // ─── 7. 保存 ─────────────────────────────────────────────────────────

  /** 保存核对表数据 */
  async function saveReconcileData(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `M9-4-row-${n}-source`, data: { remark: row.sourceName } },
        { itemId: `M9-4-row-${n}-type`, data: { remark: row.sourceType } },
        { itemId: `M9-4-row-${n}-category`, data: { remark: row.category } },
        { itemId: `M9-4-row-${n}-sourceAfterTax`, data: { remark: String(row.sourceAfterTax) } },
        { itemId: `M9-4-row-${n}-bookedIncrease`, data: { remark: String(row.bookedOciIncrease) } },
        { itemId: `M9-4-row-${n}-diff`, data: { remark: String(row.reconcileDiff) } },
      ]
    }).flat()

    // 汇总
    items.push(
      { itemId: 'M9-4-nonReclass-diff', data: { remark: String(nonReclassSummary.value.totalDiff) } },
      { itemId: 'M9-4-reclass-diff', data: { remark: String(reclassSummary.value.totalDiff) } },
      { itemId: 'M9-4-total-diff', data: { remark: String(totalSummary.value.totalDiff) } },
      { itemId: 'M9-4-is-reconciled', data: { remark: String(totalSummary.value.isAllReconciled) } },
    )

    await saveBatch(items)
  }

  // ─── 8. 内部保存触发 ──────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = reconcileRows.value[rowIndex]
    if (!row) return
    debouncedSave(`M9-4-row-${rowIndex}-data`, {
      remark: JSON.stringify({
        key: row.key,
        sourceName: row.sourceName,
        sourceType: row.sourceType,
        category: row.category,
        sourcePreTax: row.sourcePreTax,
        sourceTaxEffect: row.sourceTaxEffect,
        bookedOciIncrease: row.bookedOciIncrease,
        diffExplanation: row.diffExplanation,
        sourceWpCode: row.sourceWpCode,
        crossRefId: row.crossRefId,
      }),
    })
  }

  function _triggerSaveAll(): void {
    reconcileRows.value.forEach((_, i) => _triggerSave(i))
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算行
    computedRows,
    nonReclassRows,
    reclassRows,

    // 汇总
    nonReclassSummary,
    reclassSummary,
    totalSummary,
    ociAggregate,

    // 高亮
    highlightedRows,
    isHighlighted,

    // 行操作
    addRow,
    removeRow,
    updateRow,

    // 来源更新
    updateFromSource,

    // EventBus 订阅
    subscribeG8FairValue,
    subscribeJ2Remeasured,

    // 保存
    saveReconcileData,
  }
}

export default useM9OciReconcile
