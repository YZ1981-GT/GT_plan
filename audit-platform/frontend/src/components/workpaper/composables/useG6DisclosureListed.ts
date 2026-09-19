/**
 * useG6DisclosureListed — G6 其他债权投资 附注披露（上市公司）状态与勾稽
 *
 * 按**权威模板** `backend/wp_templates/G/G6 其他债权投资.xlsx` 的 14 张表重写
 * （旧组件是自造的 7 个虚构小节 + 137 行 `成本项目N`，详见
 * `g6ListedDisclosureRows.ts` 文件头）。
 *
 * 持久化：两个 item_id
 * - `G6-disclosure-listed-rows`   → 除三阶段块外的全部行与文本
 * - `G6-disclosure-listed-stages` → 三阶段块（复用 G4 的 `serializeStageBlocks`）
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.3
 */
import { computed, ref, watch, type Ref } from 'vue'
import {
  addStageDetail,
  patchStageDetail,
  removeStageDetail,
  type G4StageBlock,
  type G4StageDetailRow,
  type G4StageMethod,
} from './g4ListedStageDisclosure'
import {
  buildDefaultG6ListedState,
  emptyBalanceRow,
  emptyFairValueRow,
  emptyImportantRow,
  emptyProvisionRow,
  emptyWriteoffRow,
  endingStageImpairment,
  parseG6ListedState,
  recomputeBalanceRows,
  recomputeFairValueRows,
  recomputeImportantRows,
  recomputeProvisionRows,
  serializeG6ListedStages,
  serializeG6ListedState,
  stageTransferImbalances,
  writeoffDetailTotal,
  type G6BalanceRow,
  type G6FairValueRow,
  type G6ImportantRow,
  type G6ListedDisclosureState,
  type G6ProvisionMovementRow,
  type G6StageMoveRow,
  type G6WriteoffRow,
} from './g6ListedDisclosureRows'
import type { ChecklistResponse } from './useF1FormData'

export const G6_LISTED_ROWS_ITEM = 'G6-disclosure-listed-rows'
export const G6_LISTED_STAGES_ITEM = 'G6-disclosure-listed-stages'
/** 与 G6-1 勾稽用的审定数 item（其他债权投资，科目 1503） */
export const G6_ADJUDICATED_ITEM = 'G6-1-adjudicated-amount'

/** 勾稽容差（元） */
export const G6_TIE_TOLERANCE = 0.01

export interface G6ListedTieCheck {
  code: string
  label: string
  left: number
  right: number
  diff: number
  ok: boolean
  detail: string
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function useG6DisclosureListed(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const state = ref<G6ListedDisclosureState>(buildDefaultG6ListedState())

  function readRaw(itemId: string): string | null {
    const r = opts.allResponses.value.get(itemId)
    return r?.remark ?? r?.conclusion ?? null
  }

  function load(): void {
    state.value = parseG6ListedState(readRaw(G6_LISTED_ROWS_ITEM), readRaw(G6_LISTED_STAGES_ITEM))
  }

  watch(
    () => [readRaw(G6_LISTED_ROWS_ITEM), readRaw(G6_LISTED_STAGES_ITEM)],
    () => load(),
    { immediate: true },
  )

  function persist(): void {
    if (opts.isReadonly.value) return
    opts.debouncedSave(G6_LISTED_ROWS_ITEM, { remark: serializeG6ListedState(state.value) })
    opts.debouncedSave(G6_LISTED_STAGES_ITEM, { remark: serializeG6ListedStages(state.value) })
  }

  function mutate(fn: (s: G6ListedDisclosureState) => G6ListedDisclosureState): void {
    if (opts.isReadonly.value) return
    state.value = fn(state.value)
    persist()
  }

  // ─── 主表 ───────────────────────────────────────────────────
  function patchBalance(id: string, patch: Partial<G6BalanceRow>): void {
    mutate((s) => ({
      ...s,
      balanceRows: recomputeBalanceRows(
        s.balanceRows.map((r) =>
          r.id === id
            ? { ...r, ...patch, ...(r.fixed ? { label: r.label } : {}) }
            : r,
        ),
      ),
    }))
  }

  function addBalanceRow(): void {
    mutate((s) => {
      const firstFixed = s.balanceRows.findIndex((r) => r.fixed)
      const next = [...s.balanceRows]
      next.splice(firstFixed < 0 ? next.length : firstFixed, 0, emptyBalanceRow())
      return { ...s, balanceRows: recomputeBalanceRows(next) }
    })
  }

  function removeBalanceRow(id: string): void {
    mutate((s) => ({
      ...s,
      balanceRows: recomputeBalanceRows(s.balanceRows.filter((r) => r.id !== id || r.fixed)),
    }))
  }

  // ─── （1）其他债权投资情况 ──────────────────────────────────
  function patchFairValue(id: string, patch: Partial<G6FairValueRow>): void {
    mutate((s) => ({
      ...s,
      fairValueRows: recomputeFairValueRows(
        s.fairValueRows.map((r) =>
          r.id === id ? { ...r, ...patch, ...(r.fixed ? { label: r.label } : {}) } : r,
        ),
      ),
    }))
  }

  function addFairValueRow(): void {
    mutate((s) => {
      const at = s.fairValueRows.findIndex((r) => r.fixed)
      const next = [...s.fairValueRows]
      next.splice(at < 0 ? next.length : at, 0, emptyFairValueRow())
      return { ...s, fairValueRows: recomputeFairValueRows(next) }
    })
  }

  function removeFairValueRow(id: string): void {
    mutate((s) => ({
      ...s,
      fairValueRows: recomputeFairValueRows(s.fairValueRows.filter((r) => r.id !== id || r.fixed)),
    }))
  }

  // ─── （2）减值准备本期变动 ──────────────────────────────────
  function patchProvision(id: string, patch: Partial<G6ProvisionMovementRow>): void {
    mutate((s) => ({
      ...s,
      provisionRows: recomputeProvisionRows(
        s.provisionRows.map((r) =>
          r.id === id ? { ...r, ...patch, ...(r.fixed ? { label: r.label } : {}) } : r,
        ),
      ),
    }))
  }

  function addProvisionRow(): void {
    mutate((s) => {
      const at = s.provisionRows.findIndex((r) => r.fixed)
      const next = [...s.provisionRows]
      next.splice(at < 0 ? next.length : at, 0, emptyProvisionRow())
      return { ...s, provisionRows: recomputeProvisionRows(next) }
    })
  }

  function removeProvisionRow(id: string): void {
    mutate((s) => ({
      ...s,
      provisionRows: recomputeProvisionRows(s.provisionRows.filter((r) => r.id !== id || r.fixed)),
    }))
  }

  // ─── （3）期末重要 + 续表 ───────────────────────────────────
  type ImportantKey = 'importantEndRows' | 'importantPriorRows'

  function patchImportant(key: ImportantKey, id: string, patch: Partial<G6ImportantRow>): void {
    mutate((s) => ({
      ...s,
      [key]: recomputeImportantRows(
        s[key].map((r) =>
          r.id === id ? { ...r, ...patch, ...(r.fixed ? { label: r.label } : {}) } : r,
        ),
      ),
    }))
  }

  function addImportantRow(key: ImportantKey): void {
    mutate((s) => {
      const at = s[key].findIndex((r) => r.fixed)
      const next = [...s[key]]
      next.splice(at < 0 ? next.length : at, 0, emptyImportantRow())
      return { ...s, [key]: recomputeImportantRows(next) }
    })
  }

  function removeImportantRow(key: ImportantKey, id: string): void {
    mutate((s) => ({
      ...s,
      [key]: recomputeImportantRows(s[key].filter((r) => r.id !== id || r.fixed)),
    }))
  }

  // ─── （4）三阶段块 ──────────────────────────────────────────
  function patchStage(
    blockId: string,
    method: G4StageMethod,
    detailId: string,
    patch: Partial<Pick<G4StageDetailRow, 'name' | 'bookBalance' | 'impairment' | 'reason'>>,
  ): void {
    mutate((s) => ({
      ...s,
      stageBlocks: patchStageDetail(s.stageBlocks, blockId, method, detailId, patch),
    }))
  }

  function addStageRow(blockId: string, method: G4StageMethod): void {
    mutate((s) => ({ ...s, stageBlocks: addStageDetail(s.stageBlocks, blockId, method) }))
  }

  function removeStageRow(blockId: string, method: G4StageMethod, detailId: string): void {
    mutate((s) => ({
      ...s,
      stageBlocks: removeStageDetail(s.stageBlocks, blockId, method, detailId),
    }))
  }

  // ─── （5）阶段迁移 ──────────────────────────────────────────
  function patchStageMove(rowKey: string, patch: Partial<G6StageMoveRow>): void {
    mutate((s) => ({
      ...s,
      stageMoveRows: s.stageMoveRows.map((r) => (r.rowKey === rowKey ? { ...r, ...patch } : r)),
    }))
  }

  // ─── （6）核销 ──────────────────────────────────────────────
  function patchWriteoff(id: string, patch: Partial<G6WriteoffRow>): void {
    mutate((s) => ({
      ...s,
      writeoffRows: s.writeoffRows.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    }))
  }

  function addWriteoffRow(): void {
    mutate((s) => ({ ...s, writeoffRows: [...s.writeoffRows, emptyWriteoffRow()] }))
  }

  function removeWriteoffRow(id: string): void {
    mutate((s) => ({ ...s, writeoffRows: s.writeoffRows.filter((r) => r.id !== id) }))
  }

  function setWriteoffTotal(v: number): void {
    mutate((s) => ({ ...s, writeoffTotal: num(v) }))
  }

  // ─── 文本域 ────────────────────────────────────────────────
  function setNote(
    key: 'fvNote' | 'significantChangeNote' | 'judgementBasisNote',
    text: string,
  ): void {
    mutate((s) => ({ ...s, [key]: String(text ?? '') }))
  }

  // ─── 派生与勾稽 ────────────────────────────────────────────
  const adjudicatedAmount = computed<number | null>(() => {
    const raw = opts.allResponses.value.get(G6_ADJUDICATED_ITEM)?.conclusion
    if (raw == null || raw === '') return null
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  })

  const balanceTotalRow = computed(
    () => state.value.balanceRows.find((r) => r.kind === 'total') ?? null,
  )
  const balanceSubtotalRow = computed(
    () => state.value.balanceRows.find((r) => r.kind === 'subtotal') ?? null,
  )
  const fairValueTotalRow = computed(
    () => state.value.fairValueRows.find((r) => r.kind === 'total') ?? null,
  )
  const provisionTotalRow = computed(
    () => state.value.provisionRows.find((r) => r.kind === 'total') ?? null,
  )

  const transferImbalances = computed(() => stageTransferImbalances(state.value.stageMoveRows))

  /**
   * 披露内部勾稽（只取源模板可判定的项，容差 0.01 元）：
   * 1. 主表合计 = 小计 − 减：一年内到期（公式列，恒成立；用于暴露手工改动）
   * 2. 主表合计期末 = G6-1 审定数（1503）
   * 3. （1）表合计期末公允价值 = 主表小计期末余额
   * 4. （2）表合计期末 = （1）表合计「累计在其他综合收益中确认的减值准备」
   * 5. （2）表合计期末 = 期末三阶段减值准备合计
   * 6. （5）表期末余额合计 = 期末三阶段减值准备合计
   * 7. 核销总额 ≥ 重要核销明细合计
   */
  const tieChecks = computed<G6ListedTieCheck[]>(() => {
    const s = state.value
    const out: G6ListedTieCheck[] = []
    const push = (
      code: string,
      label: string,
      left: number,
      right: number,
      detail: string,
      cmp: 'eq' | 'gte' = 'eq',
    ) => {
      const diff = Number((left - right).toFixed(2))
      out.push({
        code,
        label,
        left,
        right,
        diff,
        ok: cmp === 'eq' ? Math.abs(diff) <= G6_TIE_TOLERANCE : diff >= -G6_TIE_TOLERANCE,
        detail,
      })
    }

    const sub = num(balanceSubtotalRow.value?.endBalance)
    const total = num(balanceTotalRow.value?.endBalance)
    const ded = num(s.balanceRows.find((r) => r.kind === 'deduction')?.endBalance)
    push('main-total', '主表合计 = 小计 − 一年内到期', total, sub - ded, '主表公式列')

    if (adjudicatedAmount.value != null) {
      push(
        'main-vs-adj',
        '主表合计期末 = G6-1 审定数（1503）',
        total,
        adjudicatedAmount.value,
        '扣减一年内到期后应与资产负债表「其他债权投资」及 G6-1 一致',
      )
    }

    push(
      'fv-vs-main',
      '（1）表合计期末公允价值 = 主表小计期末余额',
      num(fairValueTotalRow.value?.closingFv),
      sub,
      '主表按公允价值列示',
    )

    const provClosing =
      num(provisionTotalRow.value?.opening)
      + num(provisionTotalRow.value?.increase)
      - num(provisionTotalRow.value?.decrease)
    push(
      'prov-vs-oci',
      '（2）表合计期末 = （1）表累计在其他综合收益中确认的减值准备',
      provClosing,
      num(fairValueTotalRow.value?.ociImpairment),
      '损失准备在其他综合收益中确认，不冲减账面价值',
    )

    const stageEnd = endingStageImpairment(s.stageBlocks)
    push('prov-vs-stage', '（2）表合计期末 = 期末三阶段减值准备合计', provClosing, stageEnd, 'CAS 22 三阶段')

    const moveClosing = s.stageMoveRows.find((r) => r.rowKey === 'closing')
    push(
      'move-vs-stage',
      '（5）表期末余额合计 = 期末三阶段减值准备合计',
      moveClosing
        ? num(moveClosing.stage1) + num(moveClosing.stage2) + num(moveClosing.stage3)
        : 0,
      stageEnd,
      '并与坏账准备明细表 G6-3 期末审定数勾稽',
    )

    push(
      'writeoff-vs-detail',
      '核销总额 ≥ 重要核销明细合计',
      num(s.writeoffTotal) || writeoffDetailTotal(s.writeoffRows),
      writeoffDetailTotal(s.writeoffRows),
      '差额为不重要款项核销',
      'gte',
    )
    return out
  })

  const hasTieIssue = computed(() => tieChecks.value.some((c) => !c.ok))

  return {
    state,
    load,
    persist,
    adjudicatedAmount,
    balanceSubtotalRow,
    balanceTotalRow,
    fairValueTotalRow,
    provisionTotalRow,
    transferImbalances,
    tieChecks,
    hasTieIssue,
    patchBalance, addBalanceRow, removeBalanceRow,
    patchFairValue, addFairValueRow, removeFairValueRow,
    patchProvision, addProvisionRow, removeProvisionRow,
    patchImportant, addImportantRow, removeImportantRow,
    patchStage, addStageRow, removeStageRow,
    patchStageMove,
    patchWriteoff, addWriteoffRow, removeWriteoffRow, setWriteoffTotal,
    setNote,
  }
}

export type { G4StageBlock }
