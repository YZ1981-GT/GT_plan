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
import {
  parseNum,
  calcAuditedAmount,
  calcChangeRate,
  calcSubtotal,
  calcNetValue,
  isChangeRateExceeding,
} from './useD1FormulaEngine'

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

interface RowConfig {
  rowKey: string
  label: string
  isEditable: boolean
}

const GROSS_ROWS: RowConfig[] = [
  { rowKey: 'gross-bank', label: '银行承兑汇票', isEditable: true },
  { rowKey: 'gross-commercial', label: '商业承兑汇票', isEditable: true },
]

const BAD_DEBT_ROWS: RowConfig[] = [
  { rowKey: 'bd-bank', label: '银行承兑汇票', isEditable: true },
  { rowKey: 'bd-commercial', label: '商业承兑汇票', isEditable: true },
]

const NET_VALUE_ROWS: RowConfig[] = [
  { rowKey: 'net-bank', label: '银行承兑汇票', isEditable: false },
  { rowKey: 'net-commercial', label: '商业承兑汇票', isEditable: false },
]

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

  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')

  /**
   * 从 allResponses 中解析 D1-cat-rows remark JSON 获取按类别明细数据
   * item_id = "D1-cat-rows", remark = JSON array of CategoryRow
   */
  interface CategoryRowData {
    rowId: string
    category: string
    priorUnadjusted: number
    priorAje: number
    priorRje: number
    priorAudited: number
    currentUnadjusted: number
    currentAje: number
    currentRje: number
    currentAudited: number
  }

  const categoryRows = computed<CategoryRowData[]>(() => {
    const raw = getVal('D1-cat-rows').remark
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : []
    } catch { return [] }
  })

  /** 从 D1-bd-individual-rows / D1-bd-portfolio-rows 解析坏账数据 */
  interface BadDebtRowData {
    rowId: string
    priorAudited: number
    currentAudited: number
  }

  const badDebtRows = computed<BadDebtRowData[]>(() => {
    const rows: BadDebtRowData[] = []
    for (const key of ['D1-bd-individual-rows', 'D1-bd-portfolio-rows']) {
      const raw = getVal(key).remark
      if (!raw) continue
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) rows.push(...parsed)
      } catch { /* skip */ }
    }
    return rows
  })

  // ─── Row Builder ─────────────────────────────────────────────────────────

  function buildRow(rowKey: string, label: string, isEditable: boolean, isFromCrossSheet: boolean): AdjudicationDetailRow {
    const priorUnadjusted = parseNum(getVal(`D1-adj-${rowKey}-prior-unadj`).remark)
    const priorAje = parseNum(getVal(`D1-adj-${rowKey}-prior-aje`).remark)
    const priorRje = parseNum(getVal(`D1-adj-${rowKey}-prior-rje`).remark)
    const priorAudited = calcAuditedAmount(priorUnadjusted, priorAje, priorRje)

    const currentUnadjusted = parseNum(getVal(`D1-adj-${rowKey}-current-unadj`).remark)
    const currentAje = parseNum(getVal(`D1-adj-${rowKey}-current-aje`).remark)
    const currentRje = parseNum(getVal(`D1-adj-${rowKey}-current-rje`).remark)
    const currentAudited = calcAuditedAmount(currentUnadjusted, currentAje, currentRje)

    const change = currentAudited - priorAudited
    const changeRate = calcChangeRate(priorAudited, currentAudited)
    const reasonAnalysis = getVal(`D1-adj-${rowKey}-reason`).remark || ''

    return {
      rowKey, label, priorUnadjusted, priorAje, priorRje, priorAudited,
      currentUnadjusted, currentAje, currentRje, currentAudited,
      change, changeRate, reasonAnalysis, isFromCrossSheet, isEditable,
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
    // Section 1: 原值
    const grossDetailRows = GROSS_ROWS.map(cfg => {
      // Try cross-sheet first
      const catRow = categoryRows.value.find(r =>
        (cfg.rowKey === 'gross-bank' && r.category?.includes('银行')) ||
        (cfg.rowKey === 'gross-commercial' && r.category?.includes('商业'))
      )
      const row = buildRow(cfg.rowKey, cfg.label, cfg.isEditable, !!catRow)
      // Override with cross-sheet data if available
      if (catRow) {
        row.priorUnadjusted = parseNum(catRow.priorUnadjusted)
        row.priorAje = parseNum(catRow.priorAje)
        row.priorRje = parseNum(catRow.priorRje)
        row.priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
        row.currentUnadjusted = parseNum(catRow.currentUnadjusted)
        row.currentAje = parseNum(catRow.currentAje)
        row.currentRje = parseNum(catRow.currentRje)
        row.currentAudited = calcAuditedAmount(row.currentUnadjusted, row.currentAje, row.currentRje)
        row.change = row.currentAudited - row.priorAudited
        row.changeRate = calcChangeRate(row.priorAudited, row.currentAudited)
        row.isFromCrossSheet = true
      }
      return row
    })
    const grossSubtotal = buildSubtotalRow('gross', '小计', grossDetailRows)

    // Section 2: 坏账准备
    const bdDetailRows = BAD_DEBT_ROWS.map(cfg => {
      const row = buildRow(cfg.rowKey, cfg.label, cfg.isEditable, badDebtRows.value.length > 0)
      return row
    })
    const bdSubtotal = buildSubtotalRow('bad-debt', '小计', bdDetailRows)

    // Section 3: 净值 = 原值 - 坏账准备
    const netDetailRows = NET_VALUE_ROWS.map((cfg, idx) => {
      const grossRow = grossDetailRows[idx]
      const bdRow = bdDetailRows[idx]
      if (!grossRow || !bdRow) return buildRow(cfg.rowKey, cfg.label, false, false)

      const priorAudited = calcNetValue(grossRow.priorAudited, bdRow.priorAudited)
      const currentAudited = calcNetValue(grossRow.currentAudited, bdRow.currentAudited)
      const change = currentAudited - priorAudited
      const changeRate = calcChangeRate(priorAudited, currentAudited)

      return {
        rowKey: cfg.rowKey,
        label: cfg.label,
        priorUnadjusted: calcNetValue(grossRow.priorUnadjusted, bdRow.priorUnadjusted),
        priorAje: calcNetValue(grossRow.priorAje, bdRow.priorAje),
        priorRje: calcNetValue(grossRow.priorRje, bdRow.priorRje),
        priorAudited,
        currentUnadjusted: calcNetValue(grossRow.currentUnadjusted, bdRow.currentUnadjusted),
        currentAje: calcNetValue(grossRow.currentAje, bdRow.currentAje),
        currentRje: calcNetValue(grossRow.currentRje, bdRow.currentRje),
        currentAudited,
        change,
        changeRate,
        reasonAnalysis: '',
        isFromCrossSheet: true,
        isEditable: false,
      }
    })
    const netSubtotal = buildSubtotalRow('net-value', '小计', netDetailRows)

    return [
      { sectionKey: 'gross', sectionLabel: '一、应收票据原值', rows: grossDetailRows, subtotalRow: grossSubtotal },
      { sectionKey: 'bad-debt', sectionLabel: '二、坏账准备', rows: bdDetailRows, subtotalRow: bdSubtotal },
      { sectionKey: 'net-value', sectionLabel: '三、应收票据净值', rows: netDetailRows, subtotalRow: netSubtotal },
    ] as AdjudicationSection[]
  })

  // ─── Trial Balance Diff ──────────────────────────────────────────────────

  const trialBalanceDiff: ComputedRef<TrialBalanceDiffRow> = computed(() => {
    // 手工录入的 D1-adj-tb-amount 优先；未录入时回退 render 预填的 TB(1121) 数
    const manual = getVal('D1-adj-tb-amount').remark
    const tbAmount = (manual !== null && manual !== '')
      ? parseNum(manual)
      : (tbSeedAmount?.value ?? 0)
    const netSection = adjudicationSections.value.find(s => s.sectionKey === 'net-value')
    const auditedAmount = netSection?.subtotalRow.currentAudited ?? 0
    return { tbAmount, auditedAmount, diff: auditedAmount - tbAmount }
  })

  // ─── Audit Note & Conclusion ─────────────────────────────────────────────

  const auditNote = ref<string>(getVal('D1-adj-note').remark || '')
  const auditConclusion = ref<string>(getVal('D1-adj-conclusion').remark || '')

  // Sync from allResponses on load
  watch(() => getVal('D1-adj-note').remark, (v) => { if (v !== null) auditNote.value = v || '' }, { immediate: true })
  watch(() => getVal('D1-adj-conclusion').remark, (v) => { if (v !== null) auditConclusion.value = v || '' }, { immediate: true })

  function saveAuditNote(text: string): void {
    auditNote.value = text
    const item = setLocal('D1-adj-note', null, text)
    saveImmediate([item])
  }

  function saveAuditConclusion(text: string): void {
    auditConclusion.value = text
    const item = setLocal('D1-adj-conclusion', null, text)
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

  async function aiGenerateNote(): Promise<string> {
    const { api } = await import('@/services/apiProxy')
    const context = buildAiContext()
    const res = await api.post(`/api/workpapers/${wpId.value}/review-dialog/ai-generate`, {
      section: 'audit-note',
      context,
    })
    const text = (res as any)?.text || (res as any)?.data?.text || ''
    return text
  }

  async function aiGenerateConclusion(): Promise<string> {
    const { api } = await import('@/services/apiProxy')
    const context = buildAiContext()
    const res = await api.post(`/api/workpapers/${wpId.value}/review-dialog/ai-generate`, {
      section: 'audit-conclusion',
      context,
    })
    const text = (res as any)?.text || (res as any)?.data?.text || ''
    return text
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

  function updateCell(rowKey: string, field: string, value: number): void {
    if (isReadonly.value) return
    const itemId = `D1-adj-${rowKey}-${field}`
    setLocal(itemId, null, String(value))

    // Debounce 2s
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      const items: ChecklistItem[] = []
      for (const [, resp] of allResponses.value) {
        if (resp.item_id.startsWith('D1-adj-')) {
          items.push(resp)
        }
      }
      saveImmediate(items)
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
    const itemId = `D1-adj-${targetRowKey}-${fieldSuffix}`
    const existing = parseNum(getVal(itemId).remark)
    setLocal(itemId, null, String(existing + amount))

    // Debounce save
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      const items: ChecklistItem[] = []
      for (const [, resp] of allResponses.value) {
        if (resp.item_id.startsWith('D1-adj-')) items.push(resp)
      }
      saveImmediate(items)
    }, 2000)
  }

  function resolveRowKeyFromAccount(accountCode: string): string | null {
    // Map account codes to row keys
    if (accountCode.startsWith('1121') || accountCode.includes('银行承兑')) return 'gross-bank'
    if (accountCode.startsWith('1122') || accountCode.includes('商业承兑')) return 'gross-commercial'
    if (accountCode.startsWith('1231') || accountCode.includes('坏账')) return 'bd-bank'
    return 'gross-bank' // fallback to first row
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
