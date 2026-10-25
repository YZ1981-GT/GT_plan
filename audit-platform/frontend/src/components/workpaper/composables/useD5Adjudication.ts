/**
 * useD5Adjudication — D5-1 审定表核心逻辑 composable
 *
 * Spec: .kiro/specs/d5-receivables-financing/
 * Task: 6.1
 *
 * 职责：
 * - 固定行结构（ADJUDICATION_ROWS: 应收票据/应收账款/小计/减:OCI变动/FV合计/TB数/差异）
 * - rows computed（从allResponses加载 + crossSheet聚合填入 + 公式计算）
 * - trialBalanceAmount（从TB auto_data取数科目1124）+ trialBalanceDiff computed
 * - auditNotes 双向绑定（explanation/conclusion）
 * - updateCell（编辑 → 公式重算 → debouncedSave）
 * - publishAdjudicated（EventBus: substantive:adjudicated，payload含1124/auditedAmount）
 * - onAdjustmentCreated监听（AJE/RJE累加）
 * - 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率
 *
 * Requirements: 2.1-2.8, 3.1-3.7, 11.1, 11.2
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  calcFvTotal,
} from './useD5FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import { resolveTbAmountWithSeed } from './dCycleTbSeed'
// 🔴 复用平台级共享四态状态机（spec d567-sync-coverage Task 20）——**绝不**在 D5 侧另写一套。
//    D5-1 是逐格固定行（per-cell），三个派生格（notes/acc 的 currentUnadjusted ← D5-2 聚合、
//    oci-change 的 currentUnadjusted ← D5-4 公允价值），判定链与 D3-1/D4-1 完全同源。
import {
  resolvePerCellDerivedState,
  type DerivedCellState,
} from './shared/dynamicAdjudicationRows'
import type { ChecklistResponse } from './useD5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjudicationRow {
  rowKey: string
  label: string
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number      // = 未审 + AJE + RJE
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number    // = 未审 + AJE + RJE
  changeAmount: number      // = 期末审定 - 期初审定
  changeRate: number | '' | 'N/A'
  isFromCrossSheet: boolean
  isEditable: boolean
  /**
   * 逐格覆盖态（spec d567-sync-coverage Task 20）：仅**派生格**
   * （`currentUnadjusted`，来源 cross_sheet）在 S2/S4 时有值。
   * S1/S3 不产生条目（纯派生跟随上游）。
   */
  cellOverrides?: Record<
    string,
    { state: DerivedCellState; stored: number; snap: number; derived: number }
  >
}

export interface AdjustmentPayload {
  wpCode: string
  entryType: 'AJE' | 'RJE'
  amount: number
  accountCode?: string
}

export interface UseD5AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: {
    categoryAggregation: ComputedRef<{
      notesReceivable: { prior: number; current: number }
      accountsReceivable: { prior: number; current: number }
    }>
    ociChange: ComputedRef<{ prior: number; current: number }>
    adjustmentTotals: ComputedRef<{ ajeTotal: number; rjeTotal: number }>
  }
  isReadonly: Ref<boolean>
  /**
   * 试算平衡表数种子（render `project_context.tb_amount`，BS-007 报表行解析后的
   * 叶子口径）。**只读回退** —— 手工录入优先，未录入时用它。
   *
   * 🔴 D5 的 `1124 应收款项融资` 在活体 `account_chart` 两个 source 零命中、
   * `account_mapping` 零反解、`tb_balance` 零数据行 —— 恒空是**业务事实**而非缺陷
   * （这批项目没有应收款项融资业务）。故 seed 通常为 0，此时与改造前行为一致。
   *
   * spec: d-cycle-four-table-extraction-and-disclosure-completion Task 16
   */
  tbSeedAmount?: Ref<number>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 固定行配置：审定表D5-1特殊OCI扣减结构 */
export const ADJUDICATION_ROWS = [
  { rowKey: 'notes-receivable', label: '应收票据', isComputed: false, isFromFV: false, isFromTB: false },
  { rowKey: 'accounts-receivable', label: '应收账款', isComputed: false, isFromFV: false, isFromTB: false },
  { rowKey: 'subtotal', label: '小计', isComputed: true, isFromFV: false, isFromTB: false },
  { rowKey: 'oci-change', label: '减：其他综合收益-公允价值变动', isComputed: false, isFromFV: true, isFromTB: false },
  { rowKey: 'fv-total', label: '应收款项融资公允价值合计', isComputed: true, isFromFV: false, isFromTB: false },
  { rowKey: 'trial-balance', label: '试算平衡表数', isComputed: false, isFromFV: false, isFromTB: true },
  { rowKey: 'difference', label: '差异数', isComputed: true, isFromFV: false, isFromTB: false },
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeItemId(rowKey: string, field: string): string {
  return `D5-1-adj-${rowKey}-${field}`
}

function getResponseNum(allResponses: Map<string, ChecklistResponse>, itemId: string): number {
  return parseNum(allResponses.get(itemId)?.remark)
}

/**
 * 派生快照 per-cell 键（四态状态机的第三个量 `snap`）。
 *
 * 🔴 照 D4/D3-1 同款存法（`{itemId}-snap`），不自创机制。
 */
function snapItemId(rowKey: string, field: string): string {
  return `${makeItemId(rowKey, field)}-snap`
}

/** 读某格 stored（落库主值）；空/非数 → null（与 snap 的 null 语义对称）。 */
function readStoredCell(
  allResponses: Map<string, ChecklistResponse>,
  rowKey: string,
  field: string,
): number | null {
  const raw = allResponses.get(makeItemId(rowKey, field))?.remark
  if (raw == null || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

/** 读某格 snap（派生快照 `{itemId}-snap`）；空/非数 → null。 */
function readSnapCell(
  allResponses: Map<string, ChecklistResponse>,
  rowKey: string,
  field: string,
): number | null {
  const raw = allResponses.get(snapItemId(rowKey, field))?.remark
  if (raw == null || raw === '') return null
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
}

/**
 * 派生格四态解析（**共享一份**：`resolvePerCellDerivedState` 含 `snap === null` 降级）。
 *
 * 三个量：`stored`（落库主值，可能被 OO 回写/手工改过）/ `snap`（上一次派生写入的值）/
 * `derived`（当前现算派生值）。S1/S3 显示派生值（跟随上游），S2/S4 显示 stored（人工覆盖值）。
 *
 * 🔴 **替代原 `cross !== 0 ? cross : manual` 二选一**：那套写法在上游一变时无法区分
 *    「人工覆盖」与「派生跟随」，且派生值恰为 0 时把手工值当派生用。
 */
function resolveDerivedCellState(
  allResponses: Map<string, ChecklistResponse>,
  rowKey: string,
  field: string,
  derivedValue: number,
) {
  return resolvePerCellDerivedState(
    readStoredCell(allResponses, rowKey, field),
    readSnapCell(allResponses, rowKey, field),
    derivedValue,
  )
}

/** 派生格逐格覆盖解析结果：display = 应显示值，override 仅 S2/S4 有值。 */
interface DerivedCellResult {
  display: number
  override?: { state: DerivedCellState; stored: number; snap: number; derived: number }
}

/** 供 rows computed 用的薄包装：S2/S4 时附带 override 三量。 */
function resolveDerivedCell(
  allResponses: Map<string, ChecklistResponse>,
  rowKey: string,
  field: string,
  derivedValue: number,
): DerivedCellResult {
  const r = resolveDerivedCellState(allResponses, rowKey, field, derivedValue)
  if (r.state === 'S2' || r.state === 'S4') {
    return {
      display: r.display,
      override: {
        state: r.state,
        stored: r.stored ?? 0,
        snap: r.snap ?? 0,
        derived: r.derived,
      },
    }
  }
  return { display: r.display }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD5Adjudication(options: UseD5AdjudicationOptions) {
  const { allResponses, saveImmediate, debouncedSave, crossSheet, isReadonly } = options

  // EventBus accumulated AJE/RJE (session-level, from adjustment:created events)
  const eventAjeAccum = ref(0)
  const eventRjeAccum = ref(0)

  // ─── Rows computed ───────────────────────────────────────────────────

  const rows: ComputedRef<AdjudicationRow[]> = computed(() => {
    const responses = allResponses.value
    const catAgg = crossSheet.categoryAggregation.value
    const ociData = crossSheet.ociChange.value
    const adjTotals = crossSheet.adjustmentTotals.value

    // D5-3 crossSheet AJE/RJE + session-level EventBus accumulated
    const totalAje = adjTotals.ajeTotal + eventAjeAccum.value
    const totalRje = adjTotals.rjeTotal + eventRjeAccum.value

    // ─── 应收票据行 ─────────────────────────────────────────────────
    const notesPriorUnadjusted = getResponseNum(responses, makeItemId('notes-receivable', 'priorUnadjusted'))
    const notesPriorAje = getResponseNum(responses, makeItemId('notes-receivable', 'priorAje'))
    const notesPriorRje = getResponseNum(responses, makeItemId('notes-receivable', 'priorRje'))
    // ─── currentUnadjusted：cross_sheet 派生格，走四态覆盖状态机（Task 20）──────────
    // 🔴 派生值 = D5-2 明细按类别聚合。原实现 `cross !== 0 ? cross : manual` 二选一已替换。
    const notesCrossCurrent = catAgg.notesReceivable.current
    const notesCell = resolveDerivedCell(responses, 'notes-receivable', 'currentUnadjusted', notesCrossCurrent)
    const notesCurrentUnadjusted = notesCell.display
    const notesCurrentAje = getResponseNum(responses, makeItemId('notes-receivable', 'currentAje')) + totalAje
    const notesCurrentRje = getResponseNum(responses, makeItemId('notes-receivable', 'currentRje')) + totalRje

    const notesPriorAudited = calcAuditedAmount(notesPriorUnadjusted, notesPriorAje, notesPriorRje)
    const notesCurrentAudited = calcAuditedAmount(notesCurrentUnadjusted, notesCurrentAje, notesCurrentRje)
    const notesChangeAmount = calcChangeAmount(notesPriorAudited, notesCurrentAudited)
    const notesChangeRate = calcChangeRate(notesPriorAudited, notesCurrentAudited)

    const notesRow: AdjudicationRow = {
      rowKey: 'notes-receivable',
      label: '应收票据',
      priorUnadjusted: notesPriorUnadjusted,
      priorAje: notesPriorAje,
      priorRje: notesPriorRje,
      priorAudited: notesPriorAudited,
      currentUnadjusted: notesCurrentUnadjusted,
      currentAje: notesCurrentAje,
      currentRje: notesCurrentRje,
      currentAudited: notesCurrentAudited,
      changeAmount: notesChangeAmount,
      changeRate: notesChangeRate,
      isFromCrossSheet: notesCrossCurrent !== 0,
      isEditable: true,
      ...(notesCell.override ? { cellOverrides: { currentUnadjusted: notesCell.override } } : {}),
    }

    // ─── 应收账款行 ─────────────────────────────────────────────────
    const accPriorUnadjusted = getResponseNum(responses, makeItemId('accounts-receivable', 'priorUnadjusted'))
    const accPriorAje = getResponseNum(responses, makeItemId('accounts-receivable', 'priorAje'))
    const accPriorRje = getResponseNum(responses, makeItemId('accounts-receivable', 'priorRje'))
    const accCrossCurrent = catAgg.accountsReceivable.current
    const accCell = resolveDerivedCell(responses, 'accounts-receivable', 'currentUnadjusted', accCrossCurrent)
    const accCurrentUnadjusted = accCell.display
    const accCurrentAje = getResponseNum(responses, makeItemId('accounts-receivable', 'currentAje')) + totalAje
    const accCurrentRje = getResponseNum(responses, makeItemId('accounts-receivable', 'currentRje')) + totalRje

    const accPriorAudited = calcAuditedAmount(accPriorUnadjusted, accPriorAje, accPriorRje)
    const accCurrentAudited = calcAuditedAmount(accCurrentUnadjusted, accCurrentAje, accCurrentRje)
    const accChangeAmount = calcChangeAmount(accPriorAudited, accCurrentAudited)
    const accChangeRate = calcChangeRate(accPriorAudited, accCurrentAudited)

    const accRow: AdjudicationRow = {
      rowKey: 'accounts-receivable',
      label: '应收账款',
      priorUnadjusted: accPriorUnadjusted,
      priorAje: accPriorAje,
      priorRje: accPriorRje,
      priorAudited: accPriorAudited,
      currentUnadjusted: accCurrentUnadjusted,
      currentAje: accCurrentAje,
      currentRje: accCurrentRje,
      currentAudited: accCurrentAudited,
      changeAmount: accChangeAmount,
      changeRate: accChangeRate,
      isFromCrossSheet: accCrossCurrent !== 0,
      isEditable: true,
      ...(accCell.override ? { cellOverrides: { currentUnadjusted: accCell.override } } : {}),
    }

    // ─── 小计行 (= 应收票据 + 应收账款) ─────────────────────────────
    const subtotalPriorUnadjusted = calcSubtotal([notesPriorUnadjusted, accPriorUnadjusted])
    const subtotalPriorAje = calcSubtotal([notesPriorAje, accPriorAje])
    const subtotalPriorRje = calcSubtotal([notesPriorRje, accPriorRje])
    const subtotalCurrentUnadjusted = calcSubtotal([notesCurrentUnadjusted, accCurrentUnadjusted])
    const subtotalCurrentAje = calcSubtotal([notesCurrentAje, accCurrentAje])
    const subtotalCurrentRje = calcSubtotal([notesCurrentRje, accCurrentRje])
    const subtotalPriorAudited = calcAuditedAmount(subtotalPriorUnadjusted, subtotalPriorAje, subtotalPriorRje)
    const subtotalCurrentAudited = calcAuditedAmount(subtotalCurrentUnadjusted, subtotalCurrentAje, subtotalCurrentRje)
    const subtotalChangeAmount = calcChangeAmount(subtotalPriorAudited, subtotalCurrentAudited)
    const subtotalChangeRate = calcChangeRate(subtotalPriorAudited, subtotalCurrentAudited)

    const subtotalRow: AdjudicationRow = {
      rowKey: 'subtotal',
      label: '小计',
      priorUnadjusted: subtotalPriorUnadjusted,
      priorAje: subtotalPriorAje,
      priorRje: subtotalPriorRje,
      priorAudited: subtotalPriorAudited,
      currentUnadjusted: subtotalCurrentUnadjusted,
      currentAje: subtotalCurrentAje,
      currentRje: subtotalCurrentRje,
      currentAudited: subtotalCurrentAudited,
      changeAmount: subtotalChangeAmount,
      changeRate: subtotalChangeRate,
      isFromCrossSheet: false,
      isEditable: false,
    }

    // ─── 减：OCI公允价值变动行 (取自D5-4) ────────────────────────────
    const ociPriorUnadjusted = getResponseNum(responses, makeItemId('oci-change', 'priorUnadjusted'))
    const ociPriorAje = getResponseNum(responses, makeItemId('oci-change', 'priorAje'))
    const ociPriorRje = getResponseNum(responses, makeItemId('oci-change', 'priorRje'))
    // 期末：cross_sheet 派生格（← D5-4 公允价值测算），走四态覆盖状态机
    const ociCrossCurrent = ociData.current
    const ociCell = resolveDerivedCell(responses, 'oci-change', 'currentUnadjusted', ociCrossCurrent)
    const ociCurrentUnadjusted = ociCell.display
    const ociCurrentAje = getResponseNum(responses, makeItemId('oci-change', 'currentAje'))
    const ociCurrentRje = getResponseNum(responses, makeItemId('oci-change', 'currentRje'))

    const ociPriorAudited = calcAuditedAmount(ociPriorUnadjusted, ociPriorAje, ociPriorRje)
    const ociCurrentAudited = calcAuditedAmount(ociCurrentUnadjusted, ociCurrentAje, ociCurrentRje)
    const ociChangeAmount = calcChangeAmount(ociPriorAudited, ociCurrentAudited)
    const ociChangeRate = calcChangeRate(ociPriorAudited, ociCurrentAudited)

    const ociRow: AdjudicationRow = {
      rowKey: 'oci-change',
      label: '减：其他综合收益-公允价值变动',
      priorUnadjusted: ociPriorUnadjusted,
      priorAje: ociPriorAje,
      priorRje: ociPriorRje,
      priorAudited: ociPriorAudited,
      currentUnadjusted: ociCurrentUnadjusted,
      currentAje: ociCurrentAje,
      currentRje: ociCurrentRje,
      currentAudited: ociCurrentAudited,
      changeAmount: ociChangeAmount,
      changeRate: ociChangeRate,
      isFromCrossSheet: ociCrossCurrent !== 0,
      isEditable: true,
      ...(ociCell.override ? { cellOverrides: { currentUnadjusted: ociCell.override } } : {}),
    }

    // ─── 公允价值合计行 (= 小计 - OCI变动) ──────────────────────────
    // 公式：公允价值合计 = 小计 - OCI变动（D5审定表特殊结构）
    const fvPriorAudited = calcFvTotal(subtotalPriorAudited, ociPriorAudited)
    const fvCurrentAudited = calcFvTotal(subtotalCurrentAudited, ociCurrentAudited)
    const fvPriorUnadjusted = calcFvTotal(subtotalPriorUnadjusted, ociPriorUnadjusted)
    const fvCurrentUnadjusted = calcFvTotal(subtotalCurrentUnadjusted, ociCurrentUnadjusted)
    const fvPriorAje = calcFvTotal(subtotalPriorAje, ociPriorAje)
    const fvCurrentAje = calcFvTotal(subtotalCurrentAje, ociCurrentAje)
    const fvPriorRje = calcFvTotal(subtotalPriorRje, ociPriorRje)
    const fvCurrentRje = calcFvTotal(subtotalCurrentRje, ociCurrentRje)
    const fvChangeAmount = calcChangeAmount(fvPriorAudited, fvCurrentAudited)
    const fvChangeRate = calcChangeRate(fvPriorAudited, fvCurrentAudited)

    const fvTotalRow: AdjudicationRow = {
      rowKey: 'fv-total',
      label: '应收款项融资公允价值合计',
      priorUnadjusted: fvPriorUnadjusted,
      priorAje: fvPriorAje,
      priorRje: fvPriorRje,
      priorAudited: fvPriorAudited,
      currentUnadjusted: fvCurrentUnadjusted,
      currentAje: fvCurrentAje,
      currentRje: fvCurrentRje,
      currentAudited: fvCurrentAudited,
      changeAmount: fvChangeAmount,
      changeRate: fvChangeRate,
      isFromCrossSheet: false,
      isEditable: false,
    }

    // ─── 试算平衡表数行 (从TB auto_data取数科目1124) ─────────────────
    const tbCurrentUnadjusted = trialBalanceAmount.value
    const tbPriorUnadjusted = getResponseNum(responses, makeItemId('trial-balance', 'priorUnadjusted'))

    const tbRow: AdjudicationRow = {
      rowKey: 'trial-balance',
      label: '试算平衡表数',
      priorUnadjusted: tbPriorUnadjusted,
      priorAje: 0,
      priorRje: 0,
      priorAudited: tbPriorUnadjusted,
      currentUnadjusted: tbCurrentUnadjusted,
      currentAje: 0,
      currentRje: 0,
      currentAudited: tbCurrentUnadjusted,
      changeAmount: calcChangeAmount(tbPriorUnadjusted, tbCurrentUnadjusted),
      changeRate: calcChangeRate(tbPriorUnadjusted, tbCurrentUnadjusted),
      isFromCrossSheet: false,
      isEditable: false,
    }

    // ─── 差异行 (= 公允价值合计 - 试算平衡表数) ─────────────────────
    const diffPriorAudited = fvPriorAudited - tbPriorUnadjusted
    const diffCurrentAudited = fvCurrentAudited - tbCurrentUnadjusted

    const differenceRow: AdjudicationRow = {
      rowKey: 'difference',
      label: '差异数',
      priorUnadjusted: 0,
      priorAje: 0,
      priorRje: 0,
      priorAudited: diffPriorAudited,
      currentUnadjusted: 0,
      currentAje: 0,
      currentRje: 0,
      currentAudited: diffCurrentAudited,
      changeAmount: calcChangeAmount(diffPriorAudited, diffCurrentAudited),
      changeRate: calcChangeRate(diffPriorAudited, diffCurrentAudited),
      isFromCrossSheet: false,
      isEditable: false,
    }

    return [notesRow, accRow, subtotalRow, ociRow, fvTotalRow, tbRow, differenceRow]
  })

  // ─── Trial Balance Amount ────────────────────────────────────────────

  /**
   * 试算平衡表数（手工优先，其次 render 下发的四表口径）。
   *
   * 🔴 改造前只读 `D5-1-tb-amount`，而 render 的 `project_context.tb_amount`
   * （`seed_tb_amount_scalars` 按 BS-007 解析后的叶子口径）**零消费方** = dead
   * output。现按平台既有范式（D1/D7 的 `tbSeedAmount`）加只读回退。
   *
   * spec: d-cycle-four-table-extraction-and-disclosure-completion Task 16
   */
  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    resolveTbAmountWithSeed(
      allResponses.value.get('D5-1-tb-amount')?.remark,
      options.tbSeedAmount?.value,
    ),
  )

  /** trialBalanceDiff = 公允价值合计审定数 - 试算平衡表数 */
  const trialBalanceDiff: ComputedRef<number> = computed(() => {
    const fvTotalRow = rows.value.find(r => r.rowKey === 'fv-total')
    if (!fvTotalRow) return 0
    return fvTotalRow.currentAudited - trialBalanceAmount.value
  })

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  // Load from allResponses
  watch(
    () => [
      allResponses.value.get('D5-1-note-explanation')?.remark,
      allResponses.value.get('D5-1-note-conclusion')?.remark,
    ],
    ([explanation, conclusion]) => {
      auditNotes.value = {
        explanation: explanation || '',
        conclusion: conclusion || '',
      }
    },
    { immediate: true },
  )

  // Watch for changes and debounce save
  watch(
    () => auditNotes.value.explanation,
    (val) => {
      debouncedSave('D5-1-note-explanation', { remark: val })
    },
  )

  watch(
    () => auditNotes.value.conclusion,
    (val) => {
      debouncedSave('D5-1-note-conclusion', { remark: val })
    },
  )

  // ─── 派生格逐格落库 + snap 维护（四态状态机，Task 20）───────────────────────
  //
  // 🔴 上游「13 条纯函数判据全绿但生产坏掉」的教训：S4 可达性完全取决于 snap 怎么维护。
  //    本段照 D3-1/D4 同款：watch 派生源变化 → 幂等把派生值写进 stored + snap
  //    （仅**未被人工覆盖**的格：`stored ≠ snap ⟺ S2/S4` 时不写，冻结 snap 在覆盖发生时的
  //    派生值，S4 才可达）。

  /** D5 的三个 cross_sheet 派生格（rowKey + 现算派生值取法）。 */
  function _derivedCells(): Array<{ rowKey: string; derived: number }> {
    const catAgg = crossSheet.categoryAggregation.value
    const ociData = crossSheet.ociChange.value
    return [
      { rowKey: 'notes-receivable', derived: catAgg.notesReceivable.current },
      { rowKey: 'accounts-receivable', derived: catAgg.accountsReceivable.current },
      { rowKey: 'oci-change', derived: ociData.current },
    ]
  }

  /** 幂等写一格（值未变则不写，避免无谓 save）。 */
  function _writeCellIfChanged(itemId: string, value: number): void {
    const cur = allResponses.value.get(itemId)?.remark
    const next = String(value)
    if (cur === next) return
    debouncedSave(itemId, { remark: next })
  }

  /**
   * 派生格同步进 store（幂等）：把派生值写进 stored + snap，**仅对未覆盖格**
   * （`stored == snap`，即 S1/S3）。覆盖格（S2/S4）**不写** —— 冻结 snap 在覆盖时的派生值，
   * 否则 snap 无条件追上 derived ⇒ S4 不可达。
   */
  function syncDerivedCellsIntoStore(): void {
    if (isReadonly.value) return
    const field = 'currentUnadjusted'
    for (const { rowKey, derived } of _derivedCells()) {
      // 🔴 覆盖判定**必须**走与读侧同一个 `resolveDerivedCellState`（含 snap===null 降级），
      //    不可手写第二份谓词：
      //    ① 状态机的 overridden 是 `!_eq(stored, snap)`，而 `_eq(5, null) === false`
      //       ⇒ 手写 `stored != null && snap != null && |Δ| > tol` 会把「有 stored 无 snap」
      //       判成未覆盖，用派生值盖掉用户数据；
      //    ② 而不带降级直接用 `resolveCellState` 又会把「stored=0 无 snap」判成 S4 ⇒ 永不写 snap
      //       ⇒ 该格永久显示 0（不可自愈）。两个方向都踩过，故读写必须同源。
      const { state } = resolveDerivedCellState(allResponses.value, rowKey, field, derived)
      if (state === 'S2' || state === 'S4') continue // 冻结 snap，不跟随上游
      _writeCellIfChanged(snapItemId(rowKey, field), derived)
      _writeCellIfChanged(makeItemId(rowKey, field), derived)
    }
  }

  watch(
    () => _derivedCells().map(c => c.derived).join('|'),
    () => { syncDerivedCellsIntoStore() },
    { immediate: true },
  )

  /**
   * 恢复取数：把某派生格从覆盖态（S2/S4）退回 S1（纯派生）。
   * 只影响被点那一格：stored ← derived、snap ← derived（用当前派生值）。**当场**写对。
   */
  function restoreDerivedValue(rowKey: string, field: string = 'currentUnadjusted'): void {
    if (isReadonly.value) return
    const cell = _derivedCells().find(c => c.rowKey === rowKey)
    if (!cell) return
    _writeCellIfChanged(makeItemId(rowKey, field), cell.derived)
    _writeCellIfChanged(snapItemId(rowKey, field), cell.derived)
  }

  // ─── updateCell ──────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: number | string): void {
    if (isReadonly.value) return

    const itemId = makeItemId(rowKey, field)
    const strValue = typeof value === 'number' ? String(value) : value

    // Update allResponses locally and trigger debounced save
    debouncedSave(itemId, { remark: strValue })
  }

  // ─── publishAdjudicated ──────────────────────────────────────────────

  function publishAdjudicated(): void {
    const fvTotalRow = rows.value.find(r => r.rowKey === 'fv-total')
    const auditedAmount = fvTotalRow?.currentAudited ?? 0

    const payload = {
      wpCode: 'D5',
      accountCode: '1124',
      auditedAmount,
      adjudicatedAmount: auditedAmount, // 别名兼容
      timestamp: Date.now(),
    }

    // Persist the adjudicated amount
    saveImmediate('D5-1-tb-amount', { remark: String(auditedAmount) })

    // 统一 eventBus (crossWpEventBridge 双向桥接 window)
    eventBus.emit('substantive:adjudicated', payload)
  }

  // ─── onAdjustmentCreated ─────────────────────────────────────────────

  function onAdjustmentCreated(payload: AdjustmentPayload): void {
    if (payload.wpCode !== 'D5') return
    if (payload.entryType === 'AJE') {
      eventAjeAccum.value += payload.amount
    } else if (payload.entryType === 'RJE') {
      eventRjeAccum.value += payload.amount
    }
  }

  // ─── EventBus Registration ───────────────────────────────────────────

  // 统一 eventBus
  eventBus.on('adjustment:created', (payload: any) => {
    if (payload) onAdjustmentCreated(payload)
  })

  onBeforeUnmount(() => {
    eventBus.off('adjustment:created')
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    trialBalanceAmount,
    trialBalanceDiff,
    auditNotes,
    updateCell,
    publishAdjudicated,
    onAdjustmentCreated,
    // 逐格覆盖：恢复取数（把派生格从 S2/S4 退回 S1）
    restoreDerivedValue,
    // Internal (for testing)
    _eventAjeAccum: eventAjeAccum,
    _eventRjeAccum: eventRjeAccum,
    _syncDerivedCellsIntoStore: syncDerivedCellsIntoStore,
  }
}

export default useD5Adjudication
