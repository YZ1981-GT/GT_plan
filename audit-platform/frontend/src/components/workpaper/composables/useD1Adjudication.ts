/**
 * useD1Adjudication — D1-1 审定表核心逻辑 composable
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Task: 3.1
 *
 * 职责：
 * - 审定表三区块行数据（原值/坏账/净值）的 computed 计算
 * - 跨Sheet取数：从同一 allResponses Map 读取 D1-cat-rows / D1-bd-*-rows
 * - 试算平衡表差异行
 * - 审计说明/结论持久化 + AI生成
 * - EventBus publish/subscribe（substantive:adjudicated / adjustment:created）
 * - 单元格编辑 + debounce 保存
 *
 * Requirements: 1.1~1.8, 2.1~2.5, 3.1~3.4, 8.1, 8.5, 8.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import { parseNum, calcChangeRate, calcSubtotal } from './useD1FormulaEngine'
import {
  D1_ADJ_CONCLUSION_KEY,
  D1_ADJ_NOTE_KEY,
  D1_ADJ_TB_AMOUNT_KEY,
  d1AdjAnchorByRowKey,
  d1AdjRowKey,
  isD1AdjAnchor,
  readD1AdjudicationTotals,
  readD1AnchorReason,
  readD1BadDebtTotal,
  readD1CategoryTotal,
  type D1AdjSection,
  type D1PeriodAmounts,
} from './d1AdjudicationModel'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface AdjudicationDetailRow {
  rowKey: string
  label: string
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number
  change: number
  changeRate: number | ''
  reasonAnalysis: string
  isFromCrossSheet: boolean
  isEditable: boolean
}

export interface AdjudicationSection {
  sectionKey: 'gross' | 'bad-debt' | 'net-value'
  sectionLabel: string
  rows: AdjudicationDetailRow[]
  subtotalRow: AdjudicationDetailRow
}

export interface TrialBalanceDiffRow {
  tbAmount: number
  auditedAmount: number
  diff: number
  /**
   * 是否核对一致（按分容差判定）。
   *
   * 🔴 不能在模板里写 `diff === 0`：金额经多层浮点求和会带 1e-9 级噪声
   * （实测 净值 19,046,910.15 与 TB 数完全相等时 `diff` 仍为 -3.7e-9），
   * 界面显示 `0.00` 却打红「✗ 存在差异」。金额精度到分，故容差取 0.005。
   */
  matched: boolean
}

/** 金额核对容差（元）—— 金额精度到分，半分以内视为一致。 */
export const D1_ADJ_AMOUNT_TOLERANCE = 0.005

/** 审定表小计 ↔ 上游明细底稿合计的勾稽提示行（非阻断，仅展示差异）。 */
export interface CrossCheckRow {
  key: string
  label: string
  detailAmount: number
  adjudicatedAmount: number
  diff: number
}

export interface UseD1AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: SaveFn
  loadSubWorkpaperData: (subWpCode: string) => Promise<Record<string, string | number>>
  isReadonly: Ref<boolean>
  openReviewDialog?: (params: { sectionId: string; sectionLabel: string; relatedData?: Record<string, unknown> }) => void
  /** 试算平衡表应收票据(1121)数：由 render 提供，用于 TB 差异行预填（手工录入优先） */
  tbSeedAmount?: Ref<number>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/**
 * 三区块行集**不再是固定常量**：改由 `readD1Categories`（D1-2 实际票据种类）派生。
 *
 * 🔴 原因（实证）：源模板 D1-2 固定行就有三个（银行承兑汇票 / **财务公司承兑汇票** /
 * 商业承兑汇票），四表库 seed 还会按客户科目表产出「信用证」等动态行（项目 0ec33ac9
 * 的 1121.03 信用证 期初 55,021,577.23）。写死「银行/商业」两行会让这些金额在审定表
 * **无落点** → 原值小计 ≠ D1-2 合计 → 净值与试算平衡表出现假差异、附注主表跟着少数。
 */
const SECTION_META: Record<D1AdjSection, { label: string; editable: boolean }> = {
  gross: { label: '一、应收票据原值', editable: true },
  bd: { label: '二、坏账准备', editable: true },
  net: { label: '三、应收票据净值', editable: false },
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD1Adjudication(options: UseD1AdjudicationOptions) {
  const { allResponses, wpId, projectId, saveImmediate, isReadonly, openReviewDialog, tbSeedAmount } = options

  // ─── Helpers ─────────────────────────────────────────────────────────────

  function getVal(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  }

  function setLocal(itemId: string, conclusion: string | null, remark: string | null): ChecklistItem {
    const item: ChecklistItem = { item_id: itemId, conclusion, remark }
    allResponses.value.set(itemId, item)
    return item
  }

  // ─── Cross-Sheet Data (pure computed from allResponses) ──────────────────



  /**
   * 跨表取数**唯一入口** = `readD1AdjudicationTotals`（共享纯函数）。
   *
   * 🔴 改造前这里有两个致命缺陷：
   *  1. 原值行读 `catRow.currentUnadjusted`，而 `useD1DetailCategory.serializeRows()`
   *     **有意不持久化派生列** → 恒 `undefined` → 0，即「D1-2 填了数、审定表期末仍是 0」。
   *  2. 坏账区块只把 `isFromCrossSheet` 标记翻成 true、**从不写值** → 界面显示「已取数」
   *     但金额恒 0 → 净值 = 原值、附注主表坏账列全 0、F4-3a/F4-6 勾稽必不成立。
   *
   * 现在两侧都由共享模型按源模板口径现算（原值 ← D1-2；坏账 ← D1-4 按票据种类小计）。
   */
  const totals = computed(() => readD1AdjudicationTotals(allResponses.value))

  /**
   * 跨表取数状态：`loaded` = 至少一行由上游明细带入；否则 `loading`（需手工补录）。
   *
   * 改造前是恒 `'loaded'` 的 ref（无论有没有取到数），审计师无法据此判断是否需手工补录。
   * 🔴 必须声明在 `totals` **之后**（computed 若被 setup 期的 immediate watch 提前求值，
   * 引用尚未初始化的 const 会 TDZ ReferenceError —— 平台已有同类踩坑记录）。
   */
  const crossSheetStatus = computed<'loaded' | 'loading' | 'error'>(() =>
    Object.values(totals.value.grossFromCrossSheet).some(Boolean) ||
    Object.values(totals.value.provisionFromCrossSheet).some(Boolean)
      ? 'loaded'
      : 'loading',
  )

  // ─── Row Builder ─────────────────────────────────────────────────────────

  /** 由共享模型算出的金额组装成表格行（派生列现算，不落库）。 */
  function buildRow(
    section: D1AdjSection,
    slug: string,
    label: string,
    amounts: D1PeriodAmounts,
    isFromCrossSheet: boolean,
  ): AdjudicationDetailRow {
    const rowKey = d1AdjRowKey(section, slug)
    const change = amounts.currentAudited - amounts.priorAudited
    return {
      rowKey,
      label,
      priorUnadjusted: amounts.priorUnadjusted,
      priorAje: amounts.priorAje,
      priorRje: amounts.priorRje,
      priorAudited: amounts.priorAudited,
      currentUnadjusted: amounts.currentUnadjusted,
      currentAje: amounts.currentAje,
      currentRje: amounts.currentRje,
      currentAudited: amounts.currentAudited,
      change,
      changeRate: calcChangeRate(amounts.priorAudited, amounts.currentAudited),
      reasonAnalysis: readD1AnchorReason(allResponses.value, section, slug),
      isFromCrossSheet,
      // 跨表取数命中的行不可手工改（以上游明细为准）；净值区块恒只读
      isEditable: SECTION_META[section].editable && !isFromCrossSheet,
    }
  }

  function buildSubtotalRow(sectionKey: string, label: string, detailRows: AdjudicationDetailRow[]): AdjudicationDetailRow {
    const sum = (field: keyof AdjudicationDetailRow) =>
      calcSubtotal(detailRows.map(r => r[field] as number))

    const priorAudited = sum('priorAudited')
    const currentAudited = sum('currentAudited')
    const change = currentAudited - priorAudited
    const changeRate = calcChangeRate(priorAudited, currentAudited)

    return {
      rowKey: `${sectionKey}-subtotal`,
      label,
      priorUnadjusted: sum('priorUnadjusted'),
      priorAje: sum('priorAje'),
      priorRje: sum('priorRje'),
      priorAudited,
      currentUnadjusted: sum('currentUnadjusted'),
      currentAje: sum('currentAje'),
      currentRje: sum('currentRje'),
      currentAudited,
      change,
      changeRate,
      reasonAnalysis: '',
      isFromCrossSheet: false,
      isEditable: false,
    }
  }

  // ─── Adjudication Sections (computed) ────────────────────────────────────

  const adjudicationSections: ComputedRef<AdjudicationSection[]> = computed(() => {
    const t = totals.value

    const grossDetailRows = t.categories.map((c) =>
      buildRow('gross', c.slug, c.label, t.gross[c.slug], t.grossFromCrossSheet[c.slug]),
    )
    const bdDetailRows = t.categories.map((c) =>
      buildRow('bd', c.slug, c.label, t.provision[c.slug], t.provisionFromCrossSheet[c.slug]),
    )
    // 净值恒 = 原值 − 坏账（源模板 B16=B8-B12），不可手工
    const netDetailRows = t.categories.map((c) =>
      buildRow('net', c.slug, c.label, t.net[c.slug], true),
    )

    return [
      {
        sectionKey: 'gross',
        sectionLabel: SECTION_META.gross.label,
        rows: grossDetailRows,
        subtotalRow: buildSubtotalRow('gross', '小计', grossDetailRows),
      },
      {
        sectionKey: 'bad-debt',
        sectionLabel: SECTION_META.bd.label,
        rows: bdDetailRows,
        subtotalRow: buildSubtotalRow('bad-debt', '小计', bdDetailRows),
      },
      {
        sectionKey: 'net-value',
        sectionLabel: SECTION_META.net.label,
        rows: netDetailRows,
        subtotalRow: buildSubtotalRow('net-value', '小计', netDetailRows),
      },
    ] as AdjudicationSection[]
  })

  // ─── 与上游明细的勾稽提示行（非阻断）──────────────────────────────────────
  //
  // 源模板 D1-1 的原值/坏账小计本应逐分对上 D1-2 / D1-4 的合计；出现差异通常意味着
  // ① D1-2 有类别未在审定表建行（改造后已由动态行消除）② D1-4 按票据种类小计未填齐
  // （四表库 1231 只有总额、无票据种类拆分，故该块只能手工，宁缺勿造）。

  const crossCheckRows = computed<CrossCheckRow[]>(() => {
    const t = totals.value
    const cat = readD1CategoryTotal(allResponses.value)
    const bd = readD1BadDebtTotal(allResponses.value)
    return [
      {
        key: 'gross-vs-d1-2',
        label: '原值小计 ↔ D1-2 明细合计（期末未审）',
        detailAmount: cat.currentUnadjusted,
        adjudicatedAmount: t.grossTotal.currentUnadjusted,
        diff: t.grossTotal.currentUnadjusted - cat.currentUnadjusted,
      },
      {
        key: 'provision-vs-d1-4',
        label: '坏账小计 ↔ D1-4 明细合计（期末未审）',
        detailAmount: bd.currentUnadjusted,
        adjudicatedAmount: t.provisionTotal.currentUnadjusted,
        diff: t.provisionTotal.currentUnadjusted - bd.currentUnadjusted,
      },
    ]
  })

  // ─── Trial Balance Diff ──────────────────────────────────────────────────

  const trialBalanceDiff: ComputedRef<TrialBalanceDiffRow> = computed(() => {
    // 手工录入的 D1-adj-tb-amount 优先；未录入时回退 render 预填的 TB(1121) 数
    const manual = getVal(D1_ADJ_TB_AMOUNT_KEY).remark
    const tbAmount = (manual !== null && manual !== '')
      ? parseNum(manual)
      : (tbSeedAmount?.value ?? 0)
    const netSection = adjudicationSections.value.find(s => s.sectionKey === 'net-value')
    const auditedAmount = netSection?.subtotalRow.currentAudited ?? 0
    // 差异按分取整，消除浮点噪声（与显示口径一致；源模板 D1-1 E20=E18-E19）
    const rawDiff = auditedAmount - tbAmount
    const diff = Math.round(rawDiff * 100) / 100
    return {
      tbAmount,
      auditedAmount,
      diff,
      matched: Math.abs(rawDiff) <= D1_ADJ_AMOUNT_TOLERANCE,
    }
  })

  // ─── Audit Note & Conclusion ─────────────────────────────────────────────

  const auditNote = ref<string>(getVal(D1_ADJ_NOTE_KEY).remark || '')
  const auditConclusion = ref<string>(getVal(D1_ADJ_CONCLUSION_KEY).remark || '')

  // Sync from allResponses on load
  watch(() => getVal(D1_ADJ_NOTE_KEY).remark, (v) => { if (v !== null) auditNote.value = v || '' }, { immediate: true })
  watch(() => getVal(D1_ADJ_CONCLUSION_KEY).remark, (v) => { if (v !== null) auditConclusion.value = v || '' }, { immediate: true })

  function saveAuditNote(text: string): void {
    auditNote.value = text
    const item = setLocal(D1_ADJ_NOTE_KEY, null, text)
    saveImmediate([item])
  }

  function saveAuditConclusion(text: string): void {
    auditConclusion.value = text
    const item = setLocal(D1_ADJ_CONCLUSION_KEY, null, text)
    saveImmediate([item])
  }

  // ─── Auto Change Description ─────────────────────────────────────────────

  const autoChangeDescription: ComputedRef<string> = computed(() => {
    const netSection = adjudicationSections.value.find(s => s.sectionKey === 'net-value')
    if (!netSection) return ''
    const rate = netSection.subtotalRow.changeRate
    if (rate === '' || rate === 0) return '公司应收票据期末净值较期初净值无变动。'
    const direction = rate > 0 ? '增加' : '减少'
    const pct = (Math.abs(rate) * 100).toFixed(2)
    return `公司应收票据期末净值较期初净值${direction}：${pct}%`
  })

  // ─── AI Generate ─────────────────────────────────────────────────────────

  /**
   * 调用平台 AI 生成端点。
   *
   * 🔴 请求体必须是 `{section_id, related_data, existing_content}`（后端
   * `review_dialog.AiGenerateRequest`），响应字段是 `generated_text`。
   * 历史实现发的是 `{section, context}` 且读 `.text` → 必然 422 且取不到文本，
   * 审定表两个 AI 按钮长期空转。平台正解见 `useReviewDialog.ts`。
   * `section_id` 含 `note` 时后端产出「审计说明」，否则产出「审计结论」。
   */
  async function aiGenerate(sectionId: string): Promise<string> {
    const { api } = await import('@/services/apiProxy')
    const res = await api.post(`/api/workpapers/${wpId.value}/review-dialog/ai-generate`, {
      section_id: sectionId,
      related_data: { context: buildAiContext() },
      existing_content: '',
    })
    const payload = (res as any)?.data ?? res
    return payload?.generated_text || payload?.data?.generated_text || ''
  }

  async function aiGenerateNote(): Promise<string> {
    return aiGenerate('d1-adjudication-audit-note')
  }

  async function aiGenerateConclusion(): Promise<string> {
    return aiGenerate('d1-adjudication-audit-conclusion')
  }

  function buildAiContext(): string {
    const sections = adjudicationSections.value
    const lines: string[] = ['D1-1 审定表数据摘要：']
    for (const sec of sections) {
      lines.push(`${sec.sectionLabel}：`)
      lines.push(`  小计 期初审定=${sec.subtotalRow.priorAudited} 期末审定=${sec.subtotalRow.currentAudited} 变动=${sec.subtotalRow.change}`)
    }
    const diff = trialBalanceDiff.value
    lines.push(`试算平衡表差异：${diff.diff}`)
    return lines.join('\n')
  }

  // ─── Update Cell + Debounce Save ─────────────────────────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  /** 收集当前全部 `D1-adj-*` 响应并整批保存（按 item_id 去重，防同批重复被后端整批拒绝）。 */
  function flushAdjItems(): void {
    const byId = new Map<string, ChecklistItem>()
    for (const [, resp] of allResponses.value) {
      if (isD1AdjAnchor(resp.item_id)) byId.set(resp.item_id, resp)
    }
    saveImmediate([...byId.values()])
  }

  function updateCell(rowKey: string, field: string, value: number): void {
    if (isReadonly.value) return
    setLocal(d1AdjAnchorByRowKey(rowKey, field), null, String(value))

    // Debounce 2s
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      flushAdjItems()
    }, 2000)
  }

  // ─── Cross-Sheet Refresh (legacy compat, now no-op since data is computed) ─

  async function refreshCrossSheetData(): Promise<void> {
    // Cross-sheet data is now derived from allResponses computed chain.
    // This function remains for API compatibility but is a no-op.
    crossSheetStatus.value = 'loaded'
  }

  // ─── EventBus ────────────────────────────────────────────────────────────

  let previousNetAudited: number | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  /** 发布 substantive:adjudicated */
  function publishAdjudicated(): void {
    const netSection = adjudicationSections.value.find(s => s.sectionKey === 'net-value')
    if (!netSection) return
    const auditedAmount = netSection.subtotalRow.currentAudited
    const priorAmount = netSection.subtotalRow.priorAudited
    const rate = netSection.subtotalRow.changeRate

    const payload = {
      wpCode: 'D1',
      accountCode: '1121',
      auditedAmount,
      adjudicatedAmount: auditedAmount,
      priorAmount,
      changeRate: typeof rate === 'number' ? rate : null,
    }
    try {
      // 经 eventBus.emit 发布（crossWpEventBridge 双向转发到 window），
      // 使 eventBus.on 与 window.addEventListener 两侧消费者均可收到。
      eventBus.emit('substantive:adjudicated' as any, payload as any)
    } catch {
      console.warn('[D1Adjudication] EventBus publish substantive:adjudicated failed')
    }
  }

  // Watch net audited changes → auto publish
  watch(
    () => adjudicationSections.value.find(s => s.sectionKey === 'net-value')?.subtotalRow.currentAudited,
    (current) => {
      if (current === undefined) return
      if (previousNetAudited !== null && previousNetAudited !== current) {
        publishAdjudicated()
      }
      previousNetAudited = current
    }
  )

  /** 监听 adjustment:created → 累加 AJE/RJE */
  function onAdjustmentCreated(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || detail.wpCode !== 'D1') return

    const entryType: 'AJE' | 'RJE' = detail.entryType
    const amount = parseNum(detail.amount)
    if (amount === 0) return

    // Determine which row to update based on account code
    const targetRowKey = resolveRowKeyFromAccount(detail.debitAccount || detail.creditAccount || '')
    if (!targetRowKey) return

    const fieldSuffix = entryType === 'AJE' ? 'current-aje' : 'current-rje'
    const itemId = d1AdjAnchorByRowKey(targetRowKey, fieldSuffix)
    const existing = parseNum(getVal(itemId).remark)
    setLocal(itemId, null, String(existing + amount))

    // Debounce save
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      flushAdjItems()
    }, 2000)
  }

  function resolveRowKeyFromAccount(accountCode: string): string | null {
    // Map account codes to row keys
    if (accountCode.startsWith('1121') || accountCode.includes('银行承兑')) return d1AdjRowKey('gross', 'bank')
    if (accountCode.startsWith('1122') || accountCode.includes('商业承兑')) return d1AdjRowKey('gross', 'commercial')
    if (accountCode.startsWith('1231') || accountCode.includes('坏账')) return d1AdjRowKey('bd', 'bank')
    return d1AdjRowKey('gross', 'bank') // fallback to first row
  }

  // Register EventBus listeners
  function registerHandler(event: string, handler: (e: Event) => void): void {
    window.addEventListener(event, handler)
    eventListeners.push({ event, handler })
  }

  registerHandler('adjustment:created', onAdjustmentCreated)

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
    eventListeners.length = 0
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    adjudicationSections,
    crossSheetStatus,
    crossCheckRows,
    trialBalanceDiff,
    auditNote,
    auditConclusion,
    autoChangeDescription,
    refreshCrossSheetData,
    updateCell,
    saveAuditNote,
    saveAuditConclusion,
    aiGenerateNote,
    aiGenerateConclusion,
    publishAdjudicated,
  }
}
