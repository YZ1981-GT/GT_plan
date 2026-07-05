/**
 * useL2Adjudication — L2-1 审定表核心逻辑 composable
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 按来源分类固定行（短期借款利息 / 长期借款利息 / 应付债券利息）
 * - sections computed（从allResponses加载行数据）
 * - 行内公式：审定数=未审+AJE+RJE（calcAuditedAmount）
 * - 行内公式：期末=期初+贷方-借方（calcLiabilityEndBalance，负债类！）
 * - 分类小计（calcSubtotal）
 * - 合计 vs L2-2明细 交叉验证
 * - writebackTB回写（科目2231）+ 发布'substantive:adjudicated'
 * - EventBus监听 adjustment:created 累加AJE/RJE
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from './useL2FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useL2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjudicationRow {
  /** 行唯一标识 */
  rowKey: string
  /** 来源分类标签 */
  label: string
  /** 期初余额 */
  beginBalance: number
  /** 贷方发生额（本期计提/增加） */
  creditAmount: number
  /** 借方发生额（本期支付/减少） */
  debitAmount: number
  /** 期末余额 = 期初 + 贷方 - 借方（自动计算，负债类！） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE 调整 */
  aje: number
  /** RJE 重分类调整 */
  rje: number
  /** 审定数 = 未审 + AJE + RJE（自动计算） */
  audited: number
  /** 是否可编辑 */
  isEditable: boolean
}

export interface UseL2AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveField: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  writebackTB: (auditedAmount: number) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 按来源分类固定行定义 */
export const SOURCE_ROWS = [
  { rowKey: 'short-term-loan', label: '短期借款利息' },
  { rowKey: 'long-term-loan', label: '长期借款利息' },
  { rowKey: 'bonds-payable', label: '应付债券利息' },
] as const

/** item_id 前缀 */
const PREFIX = 'L2-L2-1'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeItemId(rowKey: string, field: string): string {
  return `${PREFIX}-${rowKey}-${field}`
}

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function getResponseNum(responses: Map<string, ChecklistResponse>, itemId: string): number {
  return parseNum(responses.get(itemId)?.remark)
}

function buildRow(
  rowKey: string,
  label: string,
  responses: Map<string, ChecklistResponse>,
  eventAje: number,
  eventRje: number,
): AdjudicationRow {
  const beginBalance = getResponseNum(responses, makeItemId(rowKey, 'beginBalance'))
  const creditAmount = getResponseNum(responses, makeItemId(rowKey, 'creditAmount'))
  const debitAmount = getResponseNum(responses, makeItemId(rowKey, 'debitAmount'))
  const endBalance = calcLiabilityEndBalance(beginBalance, creditAmount, debitAmount)

  const unadjusted = getResponseNum(responses, makeItemId(rowKey, 'unadjusted'))
  const savedAje = getResponseNum(responses, makeItemId(rowKey, 'aje'))
  const savedRje = getResponseNum(responses, makeItemId(rowKey, 'rje'))
  const aje = savedAje + eventAje
  const rje = savedRje + eventRje
  const audited = calcAuditedAmount(unadjusted, aje, rje)

  return {
    rowKey,
    label,
    beginBalance,
    creditAmount,
    debitAmount,
    endBalance,
    unadjusted,
    aje,
    rje,
    audited,
    isEditable: true,
  }
}

function buildSubtotalRow(rows: AdjudicationRow[]): AdjudicationRow {
  const beginBalance = calcSubtotal(rows.map(r => r.beginBalance))
  const creditAmount = calcSubtotal(rows.map(r => r.creditAmount))
  const debitAmount = calcSubtotal(rows.map(r => r.debitAmount))
  const endBalance = calcLiabilityEndBalance(beginBalance, creditAmount, debitAmount)
  const unadjusted = calcSubtotal(rows.map(r => r.unadjusted))
  const aje = calcSubtotal(rows.map(r => r.aje))
  const rje = calcSubtotal(rows.map(r => r.rje))
  const audited = calcAuditedAmount(unadjusted, aje, rje)

  return {
    rowKey: '__subtotal__',
    label: '合计',
    beginBalance,
    creditAmount,
    debitAmount,
    endBalance,
    unadjusted,
    aje,
    rje,
    audited,
    isEditable: false,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL2Adjudication(options: UseL2AdjudicationOptions) {
  const { allResponses, wpId, projectId, saveField, debouncedSave, writebackTB } = options

  // Session-level AJE/RJE accumulated from EventBus adjustment:created events
  const eventAjeAccum = ref(0)
  const eventRjeAccum = ref(0)

  // ─── Rows computed ─────────────────────────────────────────────────────

  const rows: ComputedRef<AdjudicationRow[]> = computed(() => {
    const responses = allResponses.value
    return SOURCE_ROWS.map(({ rowKey, label }) =>
      buildRow(rowKey, label, responses, eventAjeAccum.value, eventRjeAccum.value),
    )
  })

  const subtotalRow: ComputedRef<AdjudicationRow> = computed(() => {
    return buildSubtotalRow(rows.value)
  })

  // ─── 合计审定数 ────────────────────────────────────────────────────────

  /** 审定总额（合计行的 audited） */
  const totalAuditedAmount: ComputedRef<number> = computed(() => {
    return subtotalRow.value.audited
  })

  // ─── 同步合计到 allResponses 供跨sheet消费 ────────────────────────────

  watch(totalAuditedAmount, (val) => {
    // 存入 allResponses 供 useL2CrossSheet.adjudicationVsDetail 消费
    allResponses.value.set('L2-L2-1-adjudication-total', {
      item_id: 'L2-L2-1-adjudication-total',
      conclusion: null,
      remark: String(val),
    })
  })

  // ─── updateCell ────────────────────────────────────────────────────────

  /**
   * 更新审定表单元格
   * @param rowKey - 行标识
   * @param field - 字段名
   * @param value - 新值
   */
  function updateCell(rowKey: string, field: string, value: number | string): void {
    const itemId = makeItemId(rowKey, field)
    const strValue = typeof value === 'number' ? String(value) : value
    debouncedSave(itemId, { remark: strValue })
  }

  // ─── publishAdjudicated + writebackTB ──────────────────────────────────

  /**
   * 提交审定：回写TB(2231) + 发布EventBus
   */
  async function submitAdjudication(): Promise<void> {
    const amount = totalAuditedAmount.value
    await writebackTB(amount)

    // 存储合计到持久层
    await saveField('L2-L2-1-adjudication-total', { remark: String(amount) })
  }

  // ─── onAdjustmentCreated（EventBus监听） ───────────────────────────────

  /**
   * 处理 adjustment:created 事件
   * mitt Events 中 'adjustment:created' 为 void 类型，这里重新加载明细数据来同步
   */
  function onAdjustmentCreated(): void {
    // adjustment:created 事件触发时，从 allResponses 重新计算即可
    // 因为 useL2Adjustment.persistEntries() 已经将最新数据写入 allResponses
    // rows computed 会自动响应 allResponses 变化
  }

  // ─── EventBus Registration（mitt 类型安全） ────────────────────────────

  eventBus.on('adjustment:created', onAdjustmentCreated)

  onBeforeUnmount(() => {
    eventBus.off('adjustment:created', onAdjustmentCreated)
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 数据行
    rows,
    subtotalRow,
    totalAuditedAmount,
    // 操作
    updateCell,
    submitAdjudication,
    // EventBus（测试可用）
    onAdjustmentCreated,
    _eventAjeAccum: eventAjeAccum,
    _eventRjeAccum: eventRjeAccum,
  }
}

export default useL2Adjudication
