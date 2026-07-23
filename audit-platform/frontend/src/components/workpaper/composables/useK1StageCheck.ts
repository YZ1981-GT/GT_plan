/**
 * useK1StageCheck — K1-7 三阶段划分检查
 *
 * 对齐致同源模板「三阶段划分检查表 K1-7」：
 *   一、审计目标
 *   二、审计程序 — (一) SICR 13项 / (二) 较低信用风险 3项 / (三) 已减值 6项
 *   三、审计说明 / 四、审计结论
 *
 * 行式实现：每户往来对象一行，展开填写三区块检查矩阵（组合1~N → 逐户）。
 * 阶段判定含较低信用风险豁免；联动 K1-2 明细阶段列。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { determineStage, determineStageWithExemption } from './useK1ECLEngine'
import { calcAssetEndBalance } from './useK1FormulaEngine'
import { stageLabelToNumber } from './k1CrossHelpers'
import {
  suggestEclStageFromAging,
  estimateOverdueDaysFromAging,
} from './useG2OverdueCheck'

// ─── 三区块检查项（对齐 Excel K1-7）────────────────────────────────────────────

export const K1_STAGE_SECTION_ONE_LABELS = [
  '信用风险变化导致的内部价格指标显著变化（如信用利差）',
  '金融工具利率或其他条款将发生显著变化',
  '类似金融工具信用风险的外部市场指标显著变化',
  '外部/内部信用评级实际或预期下调',
  '借款人业务、财务或外部经济状况不利变化',
  '借款人经营成果实际或预期显著不利变化',
  '借款人所处监管、经济或技术环境显著不利变化',
  '同一借款人其他金融工具信用风险不利变化',
  '担保或信用增级质量显著变化',
  '借款人还款经济动机显著变化',
  '借款合同的预期变更',
  '借款人预期表现和还款行为显著变化',
  '逾期信息：逾期超过（含）30日通常推定信用风险显著增加',
] as const

export const K1_STAGE_SECTION_TWO_LABELS = [
  '金融工具的违约风险较低',
  '借款人在短期内履行支付合同现金流量义务的能力很强',
  '即使长期经济形势不利变化，也不一定降低借款人履约能力',
] as const

export const K1_STAGE_SECTION_THREE_LABELS = [
  '发行方或债务人发生重大财务困难',
  '债务人违反合同（偿付利息或本金违约、逾期）',
  '债权人因债务人财务困难给予让步',
  '债务人很可能破产或进行其他财务重组',
  '财务困难导致该金融资产的活跃市场消失',
  '以大幅折扣购买或源生一项金融资产（反映信用损失事实）',
] as const

export type K1SectionOneValue = '是' | '否' | '不适用'
export type K1SectionBoolValue = '是' | '否'

export interface K1SectionOneCheck { label: string; value: K1SectionOneValue }
export interface K1SectionTwoCheck { label: string; value: K1SectionBoolValue }
export interface K1SectionThreeCheck { label: string; value: K1SectionBoolValue }

export interface K1StageRow {
  id: string
  counterparty: string
  endBalance: number
  /** 综合判定（由检查矩阵推导，兼容旧版布尔字段） */
  isSignificantIncrease: boolean
  isImpaired: boolean
  hasLowCreditRisk: boolean
  sectionOneChecks: K1SectionOneCheck[]
  sectionTwoChecks: K1SectionTwoCheck[]
  sectionThreeChecks: K1SectionThreeCheck[]
  /** 企业划分阶段 */
  companyStage: 1 | 2 | 3
  /** 公式建议阶段 */
  suggestedStage: 1 | 2 | 3
  /** 审计最终阶段（默认同建议，可覆写） */
  stage: 1 | 2 | 3
  auditStageOverridden: boolean
  priorStage: 1 | 2 | 3
  changeNote: string
  judgmentBasis: string
  indexRef: string
}

export interface K1StageSummary {
  stage1Count: number
  stage2Count: number
  stage3Count: number
  stage1Total: number
  stage2Total: number
  stage3Total: number
  inconsistentCount: number
}

export interface UseK1StageCheckOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}

function buildDefaultSectionOne(): K1SectionOneCheck[] {
  return K1_STAGE_SECTION_ONE_LABELS.map(label => ({ label, value: '否' as K1SectionOneValue }))
}

function buildDefaultSectionTwo(): K1SectionTwoCheck[] {
  return K1_STAGE_SECTION_TWO_LABELS.map(label => ({ label, value: '否' as K1SectionBoolValue }))
}

function buildDefaultSectionThree(): K1SectionThreeCheck[] {
  return K1_STAGE_SECTION_THREE_LABELS.map(label => ({ label, value: '否' as K1SectionBoolValue }))
}

export function calcK1HasSignificantIncrease(checks: K1SectionOneCheck[]): boolean {
  return checks.some(c => c.value === '是')
}

export function calcK1HasLowCreditRisk(checks: K1SectionTwoCheck[]): boolean {
  return checks.length === 3 && checks.every(c => c.value === '是')
}

export function calcK1HasCreditImpairment(checks: K1SectionThreeCheck[]): boolean {
  return checks.some(c => c.value === '是')
}

export function getK1StageTriggerLabels(row: K1StageRow): string[] {
  const hits: string[] = []
  if (row.isImpaired) {
    for (const c of row.sectionThreeChecks) {
      if (c.value === '是') hits.push(`[已减值] ${c.label}`)
    }
  }
  if (row.isSignificantIncrease) {
    for (const c of row.sectionOneChecks) {
      if (c.value === '是') hits.push(`[SICR] ${c.label}`)
    }
  }
  if (row.hasLowCreditRisk) hits.push('[低风险豁免] 三项较低信用风险条件均满足')
  return hits
}

function recalcRow(row: K1StageRow): K1StageRow {
  row.isSignificantIncrease = calcK1HasSignificantIncrease(row.sectionOneChecks)
  row.isImpaired = calcK1HasCreditImpairment(row.sectionThreeChecks)
  row.hasLowCreditRisk = calcK1HasLowCreditRisk(row.sectionTwoChecks)
  row.suggestedStage = determineStageWithExemption(row.isImpaired, row.isSignificantIncrease, row.hasLowCreditRisk)
  if (!row.auditStageOverridden) {
    row.stage = row.suggestedStage
  }
  return row
}

function normalizeRow(raw: any): K1StageRow {
  const base: K1StageRow = {
    id: raw?.id ?? `K1-7-r-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    counterparty: raw?.counterparty ?? '',
    endBalance: Number(raw?.endBalance ?? 0),
    isSignificantIncrease: false,
    isImpaired: false,
    hasLowCreditRisk: false,
    sectionOneChecks: buildDefaultSectionOne(),
    sectionTwoChecks: buildDefaultSectionTwo(),
    sectionThreeChecks: buildDefaultSectionThree(),
    companyStage: (raw?.companyStage ?? raw?.stage ?? 1) as 1 | 2 | 3,
    suggestedStage: 1,
    stage: (raw?.stage ?? 1) as 1 | 2 | 3,
    auditStageOverridden: !!raw?.auditStageOverridden,
    priorStage: (raw?.priorStage ?? 1) as 1 | 2 | 3,
    changeNote: raw?.changeNote ?? '',
    judgmentBasis: raw?.judgmentBasis ?? '',
    indexRef: raw?.indexRef ?? '',
  }

  if (Array.isArray(raw?.sectionOneChecks) && raw.sectionOneChecks.length >= 13) {
    base.sectionOneChecks = raw.sectionOneChecks.slice(0, 13).map((c: any, i: number) => ({
      label: c?.label ?? K1_STAGE_SECTION_ONE_LABELS[i],
      value: (c?.value === '是' || c?.value === '不适用' ? c.value : '否') as K1SectionOneValue,
    }))
  } else if (raw?.isSignificantIncrease) {
    base.sectionOneChecks[12].value = '是'
  }

  if (Array.isArray(raw?.sectionTwoChecks) && raw.sectionTwoChecks.length >= 3) {
    base.sectionTwoChecks = raw.sectionTwoChecks.slice(0, 3).map((c: any, i: number) => ({
      label: c?.label ?? K1_STAGE_SECTION_TWO_LABELS[i],
      value: c?.value === '是' ? '是' : '否',
    }))
  }

  if (Array.isArray(raw?.sectionThreeChecks) && raw.sectionThreeChecks.length >= 6) {
    base.sectionThreeChecks = raw.sectionThreeChecks.slice(0, 6).map((c: any, i: number) => ({
      label: c?.label ?? K1_STAGE_SECTION_THREE_LABELS[i],
      value: c?.value === '是' ? '是' : '否',
    }))
  } else if (raw?.isImpaired) {
    base.sectionThreeChecks[1].value = '是'
  }

  return recalcRow(base)
}

export const K1_STAGE_ROWS_KEY = 'K1-7-stage-rows'

export function parseK1StageRowsFromMap(map: Map<string, any>): K1StageRow[] {
  const raw = map.get(K1_STAGE_ROWS_KEY)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

export interface OverdueStageHint {
  debtorName: string
  endBalance: number
  suggestedStage: 1 | 2 | 3
  sourceNote?: string
  overdueDays?: number
  aging?: string
  isUncollectible?: string
  litigation?: string
}

/** K1-7 → K1-4 推送标记，用于去重 */
export const K1_STAGE_PUSH_MARK = '【K1-7推送】'
export const K1_4_ENTRIES_KEY = 'K1-4-adj-entries'
export const K110_STORAGE_KEY = 'K1-10-overdue'

/** (一) 第13项：逾期≥30日 */
const K1_OVERDUE_SECTION_ONE_IDX = 12
/** (三) 第2项：违约/逾期 */
const K1_OVERDUE_SECTION_THREE_BREACH_IDX = 1
/** (三) 第1项：重大财务困难 */
const K1_OVERDUE_SECTION_THREE_DISTRESS_IDX = 0

export interface K110HintSource {
  debtorName: string
  closingBalance: number
  aging: string
  overdueDays?: number
  isUncollectible?: string
  litigation?: string
}

export interface K1StageInconsistencyDraft {
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}

function resolveK110OverdueStage(
  source: K110HintSource,
  stageLabel: ReturnType<typeof suggestEclStageFromAging>,
): 1 | 2 | 3 | null {
  let stage = stageLabelToNumber(stageLabel)
  if (source.isUncollectible === '是') stage = 3
  else if (source.isUncollectible === '部分' && (!stage || stage < 2)) stage = 2
  if (source.litigation === '是' && (!stage || stage < 2)) stage = 2
  return stage
}

/** 由 K1-10 行数据构建阶段提示（供 K1-7 勾选逾期项与阶段升级） */
export function buildK110StageHintsFromSources(sources: K110HintSource[]): OverdueStageHint[] {
  const hints: OverdueStageHint[] = []
  for (const source of sources) {
    const name = source.debtorName.trim()
    if (!name) continue
    const overdueDays = source.overdueDays ?? estimateOverdueDaysFromAging(source.aging)
    const label = suggestEclStageFromAging(source.aging, overdueDays)
    const stage = resolveK110OverdueStage(source, label)
    if (!stage) continue
    hints.push({
      debtorName: name,
      endBalance: source.closingBalance,
      suggestedStage: stage,
      overdueDays,
      aging: source.aging,
      isUncollectible: source.isUncollectible,
      litigation: source.litigation,
      sourceNote: `账龄${source.aging || '-'}；${
        source.isUncollectible === '是' ? '无法收回'
          : source.litigation === '是' ? '涉诉' : '长期挂账'
      }`,
    })
  }
  return hints
}

function parseK110BundleRows(raw: string | null | undefined): K110HintSource[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    const rawRows = Array.isArray(parsed) ? parsed : (parsed.rows ?? parsed.tables?.rows)
    if (!Array.isArray(rawRows)) return []
    return rawRows.map((r: any) => {
      const opening = Number(r?.openingBalance ?? 0)
      const debit = Number(r?.periodDebit ?? 0)
      const credit = Number(r?.periodCredit ?? 0)
      const aging = String(r?.aging ?? '')
      return {
        debtorName: String(r?.debtorName ?? ''),
        closingBalance: calcAssetEndBalance(opening, debit, credit),
        aging,
        overdueDays: estimateOverdueDaysFromAging(aging),
        isUncollectible: String(r?.isUncollectible ?? ''),
        litigation: String(r?.litigation ?? ''),
      }
    })
  } catch {
    return []
  }
}

/** 从 K1-10 存储读取长期未收回提示 */
export function pullK110OverdueHints(map: Map<string, any>): OverdueStageHint[] {
  const raw = map.get(K110_STORAGE_KEY)?.remark
  return buildK110StageHintsFromSources(parseK110BundleRows(raw))
}

/** K1-10 → K1-7：按逾期信号自动勾选检查矩阵项 */
export function applyOverdueCheckFlagsToRow(row: K1StageRow, hint: OverdueStageHint): void {
  const days = hint.overdueDays ?? 0
  if (hint.suggestedStage >= 2 || days >= 30) {
    row.sectionOneChecks[K1_OVERDUE_SECTION_ONE_IDX].value = '是'
  }
  if (hint.suggestedStage >= 3 || days >= 90 || hint.isUncollectible === '是') {
    row.sectionThreeChecks[K1_OVERDUE_SECTION_THREE_BREACH_IDX].value = '是'
  }
  if (hint.isUncollectible === '是' || hint.litigation === '是') {
    row.sectionThreeChecks[K1_OVERDUE_SECTION_THREE_DISTRESS_IDX].value = '是'
  }
}

function upgradeStageFromHint(row: K1StageRow, hint: OverdueStageHint): boolean {
  const stageFloor = Math.max(hint.suggestedStage, row.suggestedStage)
  if (stageFloor <= row.stage) return false
  if (row.priorStage === row.stage) row.priorStage = row.stage
  row.stage = stageFloor as 1 | 2 | 3
  row.auditStageOverridden = row.stage !== row.suggestedStage
  const note = hint.sourceNote || `K1-10 建议升级至 Stage ${hint.suggestedStage}`
  row.changeNote = row.changeNote?.trim() ? `${row.changeNote}；${note}` : note
  if (!row.indexRef) row.indexRef = 'K1-10'
  return true
}

/**
 * K1-10 → K1-7：自动勾选逾期检查项 + 阶段升级信号（只升不降）
 */
export function mergeOverdueStageHintsToK7(
  rows: K1StageRow[],
  hints: OverdueStageHint[],
): { rows: K1StageRow[]; added: number; upgraded: number; checked: number } {
  const next: K1StageRow[] = rows.map((r) => normalizeRow({ ...r }))
  const byName = new Map(next.map((r) => [r.counterparty.trim(), r]))
  let added = 0
  let upgraded = 0
  let checked = 0

  for (const h of hints) {
    const name = h.debtorName.trim()
    if (!name) continue
    checked += 1
    const existing = byName.get(name)
    if (existing) {
      if (Math.abs(h.endBalance) >= 0.005) existing.endBalance = h.endBalance
      applyOverdueCheckFlagsToRow(existing, h)
      recalcRow(existing)
      if (upgradeStageFromHint(existing, h)) upgraded += 1
    } else {
      const row = normalizeRow({
        counterparty: name,
        endBalance: h.endBalance,
        judgmentBasis: h.sourceNote || 'K1-10 长期未收回检查',
        indexRef: 'K1-10',
        changeNote: `自 K1-10 新增，建议 Stage ${h.suggestedStage}`,
      })
      applyOverdueCheckFlagsToRow(row, h)
      recalcRow(row)
      if (h.suggestedStage > row.stage) upgradeStageFromHint(row, h)
      next.push(row)
      byName.set(name, row)
      added += 1
    }
  }

  return { rows: next, added, upgraded, checked }
}

/** 企业阶段 ≠ 审计阶段 → K1-4 调整备忘草稿 */
export function buildK1StageInconsistencyAdjDrafts(rows: K1StageRow[]): K1StageInconsistencyDraft[] {
  return rows
    .filter((r) => r.companyStage !== r.stage && r.counterparty.trim())
    .map((r) => ({
      summary: `${K1_STAGE_PUSH_MARK}阶段不一致：${r.counterparty} 企业Stage${r.companyStage} vs 审计Stage${r.stage}`,
      accountCode: '1231',
      accountName: '坏账准备',
      debitAmount: 0,
      creditAmount: 0,
      indexRef: r.indexRef || 'K1-7',
      remark: `K1-7三阶段划分不一致；期末余额${r.endBalance}；金额待按K1-8测算补录`,
    }))
}

export function useK1StageCheck(opts: UseK1StageCheckOpts) {
  const { allResponses } = opts

  const rows = ref<K1StageRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const expandedRowIds = ref<Set<string>>(new Set())

  const ITEM_NOTE = 'K1-7-audit-note'
  const ITEM_CONCLUSION = 'K1-7-audit-conclusion'

  function loadRows(): void {
    const raw = allResponses.value.get('K1-7-stage-rows')?.remark
    auditNote.value = allResponses.value.get(ITEM_NOTE)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(ITEM_CONCLUSION)?.remark ?? ''
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) ? parsed.map(normalizeRow) : []
    } catch { rows.value = [] }
  }

  function updateRow(id: string, field: keyof K1StageRow, value: any): void {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'stage') {
      row.auditStageOverridden = row.stage !== row.suggestedStage
    }
    recalcRow(row)
  }

  function updateCheckValue(
    id: string,
    section: 'significantIncrease' | 'lowCreditRisk' | 'creditImpairment',
    index: number,
    value: K1SectionOneValue | K1SectionBoolValue,
  ): void {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    if (section === 'significantIncrease' && row.sectionOneChecks[index]) {
      row.sectionOneChecks[index].value = value as K1SectionOneValue
    } else if (section === 'lowCreditRisk' && row.sectionTwoChecks[index]) {
      row.sectionTwoChecks[index].value = value as K1SectionBoolValue
    } else if (section === 'creditImpairment' && row.sectionThreeChecks[index]) {
      row.sectionThreeChecks[index].value = value as K1SectionBoolValue
    }
    recalcRow(row)
  }

  function resetAuditStageToSuggested(id: string): void {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    row.auditStageOverridden = false
    row.stage = row.suggestedStage
  }

  function addRow(counterparty: string, endBalance: number, priorStage: 1 | 2 | 3 = 1): K1StageRow {
    const newRow = normalizeRow({
      id: `K1-7-r-${Date.now()}`,
      counterparty,
      endBalance,
      priorStage,
      companyStage: 1,
      stage: 1,
    })
    rows.value.push(newRow)
    return newRow
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    expandedRowIds.value.delete(id)
  }

  function getRowStyle(row: K1StageRow): string {
    if (row.stage === 3) return 'background-color: #fde2e2'
    if (row.stage === 2) return 'background-color: #fdf0e2'
    return ''
  }

  const summary: ComputedRef<K1StageSummary> = computed(() => {
    const s: K1StageSummary = {
      stage1Count: 0, stage2Count: 0, stage3Count: 0,
      stage1Total: 0, stage2Total: 0, stage3Total: 0,
      inconsistentCount: 0,
    }
    for (const row of rows.value) {
      if (row.stage === 1) { s.stage1Count++; s.stage1Total += row.endBalance }
      else if (row.stage === 2) { s.stage2Count++; s.stage2Total += row.endBalance }
      else { s.stage3Count++; s.stage3Total += row.endBalance }
      if (row.companyStage !== row.stage) s.inconsistentCount++
    }
    return s
  })

  /** 阶段迁移但未填变动说明 */
  const stageMigrationWarnings = computed(() =>
    rows.value.filter(r => r.priorStage !== r.stage && !r.changeNote?.trim()),
  )

  const inconsistentRows = computed(() =>
    rows.value.filter(r => r.companyStage !== r.stage),
  )

  /** 从 K1-10 长期未收回自动勾选逾期项并升级阶段 */
  function applyFromK110(): { added: number; upgraded: number; checked: number } {
    const hints = pullK110OverdueHints(allResponses.value)
    if (!hints.length) return { added: 0, upgraded: 0, checked: 0 }
    const merged = mergeOverdueStageHintsToK7(rows.value, hints)
    rows.value = merged.rows
    return { added: merged.added, upgraded: merged.upgraded, checked: merged.checked }
  }

  function buildInconsistencyAdjDrafts(): K1StageInconsistencyDraft[] {
    return buildK1StageInconsistencyAdjDrafts(rows.value)
  }

  /** 从 K1-2 明细带入往来对象与期末余额 */
  function applyFromK12Detail(): { added: number; updated: number } {
    let added = 0
    let updated = 0
    try {
      const raw = allResponses.value.get('K1-2-detail-rows')?.remark
      if (!raw) return { added, updated }
      const detailRows = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (!Array.isArray(detailRows)) return { added, updated }

      const byName = new Map(rows.value.map(r => [r.counterparty, r]))
      for (const d of detailRows) {
        const name = String(d?.counterparty ?? '').trim()
        if (!name) continue
        const bal = Number(d?.endBalance ?? 0)
        const prior = (Number(d?.stage) || 1) as 1 | 2 | 3
        const existing = byName.get(name)
        if (existing) {
          existing.endBalance = bal
          if (!existing.priorStage || existing.priorStage === 1) existing.priorStage = prior
          recalcRow(existing)
          updated++
        } else {
          const row = addRow(name, bal, prior)
          row.companyStage = prior
          added++
        }
      }
    } catch { /* ignore */ }
    return { added, updated }
  }

  function syncStagesToDetail(): Map<string, 1 | 2 | 3> {
    const map = new Map<string, 1 | 2 | 3>()
    for (const row of rows.value) map.set(row.counterparty, row.stage)
    return map
  }

  function expandAll(): void {
    expandedRowIds.value = new Set(rows.value.map(r => r.id))
  }

  function collapseAll(): void {
    expandedRowIds.value = new Set()
  }

  function toggleExpand(id: string, expanded: boolean): void {
    const next = new Set(expandedRowIds.value)
    if (expanded) next.add(id)
    else next.delete(id)
    expandedRowIds.value = next
  }

  function serializeRows(): string {
    return JSON.stringify(rows.value)
  }

  function serializeMeta(): { auditNote: string; auditConclusion: string } {
    return { auditNote: auditNote.value, auditConclusion: auditConclusion.value }
  }

  return {
    rows,
    auditNote,
    auditConclusion,
    expandedRowIds,
    summary,
    stageMigrationWarnings,
    inconsistentRows,
    loadRows,
    addRow,
    removeRow,
    updateRow,
    updateCheckValue,
    resetAuditStageToSuggested,
    getRowStyle,
    applyFromK12Detail,
    applyFromK110,
    buildInconsistencyAdjDrafts,
    syncStagesToDetail,
    expandAll,
    collapseAll,
    toggleExpand,
    serializeRows,
    serializeMeta,
    ITEM_NOTE,
    ITEM_CONCLUSION,
  }
}
