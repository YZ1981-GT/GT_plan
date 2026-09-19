/**
 * useG4EclImpairmentCalc — G4-10 减值准备测算表（ECL公式链 + Stage分组 + 2区段Tab）
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/
 * Task: 6.2
 *
 * 职责：
 * - 公式链自动计算（③④⑥⑦⑧⑨；Stage1/2 损失率法，Stage3 现值法）
 * - Stage分组逻辑 + GroupSubtotal 小计汇总
 * - 行CRUD（addRow/removeRow）+ ②A/审定现值默认回落
 * - Tab切换行同步（activeTab + activeRowIndex）
 *
 * Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9
 */
import { ref, computed, watch } from 'vue'
import {
  calcImpairmentProvision,
  calcImpairmentFromPv,
  calcBookValue,
  calcTargetAuditedImpairmentByRate,
  calcImpairmentAdjustmentIdentity,
  calcAdjustedBalance,
  calcAdjustedImpairment,
  calcAdjustedBookValue,
  calcSumColumn,
  parseNum,
  round2,
} from '@/composables/useG4EclFormulaEngine'
import { ElMessageBox } from 'element-plus'
import type { ImpairmentCalcRow } from './useG4EclFormData'
import { normalizeInvestName } from './g4CrossHelpers'

// ─── GroupSubtotal 小计接口 ──────────────────────────────────────────────────

export interface GroupSubtotal {
  bookBalance: number           // Σ①
  impairmentProvision: number   // Σ③
  bookValue: number             // Σ④
  balanceAdjustment: number     // Σ⑤
  impairmentAdjustment: number  // Σ⑥
  adjBookBalance: number        // Σ⑦
  adjImpairment: number         // Σ⑧
  adjBookValue: number          // Σ⑨
}

export interface StageGroup {
  rows: ImpairmentCalcRow[]
  subtotal: GroupSubtotal
}

export interface ImpairmentCalcGrouped {
  stage1: StageGroup
  stage2: StageGroup
  stage3: StageGroup
  grandTotal: GroupSubtotal
}

// ─── 小计计算辅助 ────────────────────────────────────────────────────────────

function calcSubtotal(rows: ImpairmentCalcRow[]): GroupSubtotal {
  return {
    bookBalance: calcSumColumn(rows.map(r => r.bookBalance)),
    impairmentProvision: calcSumColumn(rows.map(r => r.impairmentProvision)),
    bookValue: calcSumColumn(rows.map(r => r.bookValue)),
    balanceAdjustment: calcSumColumn(rows.map(r => r.balanceAdjustment)),
    impairmentAdjustment: calcSumColumn(rows.map(r => r.impairmentAdjustment)),
    adjBookBalance: calcSumColumn(rows.map(r => r.adjBookBalance)),
    adjImpairment: calcSumColumn(rows.map(r => r.adjImpairment)),
    adjBookValue: calcSumColumn(rows.map(r => r.adjBookValue)),
  }
}

function createBlankRow(
  partial: Partial<ImpairmentCalcRow> & Pick<ImpairmentCalcRow, 'id' | 'seq' | 'investProject' | 'stageGroup'>,
): ImpairmentCalcRow {
  return {
    bookBalance: 0,
    pvFutureCashFlow: 0,
    adjustedPvFutureCashFlow: 0,
    creditLossRate: 0,
    impairmentProvision: 0,
    bookValue: 0,
    balanceAdjustment: 0,
    adjustedCreditLossRate: 0,
    adjRateTouched: false,
    adjPvTouched: false,
    impairmentAdjustment: 0,
    adjBookBalance: 0,
    adjImpairment: 0,
    adjBookValue: 0,
    priorImpairment: 0,
    currentProvision: 0,
    currentReversal: 0,
    differenceNote: '',
    ...partial,
  }
}

export type StageUpdateInput = {
  investProject: string
  auditStage: 'Stage1' | 'Stage2' | 'Stage3'
  bookBalance?: number
}

export type EclRateUpdateInput = {
  projectName: string
  /** 稳定投资 ID（优先匹配） */
  crossSheetInvestmentId?: string
  stage?: '' | 'Stage1' | 'Stage2' | 'Stage3'
  eclRate: number
  method: 'pdLgd' | 'lossRate'
}

export type EclRateSkipReason = 'not-found' | 'stage3' | 'invalid-rate'

export type EclRateApplyResult = {
  rows: ImpairmentCalcRow[]
  count: number
  matched: string[]
  unmatched: string[]
  skipped: Array<{ projectName: string; reason: EclRateSkipReason }>
  /** 匹配报告：id / name / unmatched 明细 */
  matchReport: {
    byId: string[]
    byName: string[]
    unmatched: string[]
    skipped: Array<{ projectName: string; reason: EclRateSkipReason }>
  }
}

/**
 * 从 G4-11 两套测算行收集待回写损失率。
 * 同名项目两法并存时，按 prefer 覆盖（默认损失率法）。
 * 优先保留稳定 crossSheetInvestmentId / id。
 */
export function collectEclRateUpdates(
  pdLgdRows: Array<{
    id?: string
    projectName?: string
    crossSheetInvestmentId?: string
    stage?: string
    eclRate?: number
  }> | null | undefined,
  lossRateRows: Array<{
    id?: string
    projectName?: string
    crossSheetInvestmentId?: string
    stage?: string
    eclRate?: number
  }> | null | undefined,
  prefer: 'pdLgd' | 'lossRate' = 'lossRate',
): EclRateUpdateInput[] {
  const map = new Map<string, EclRateUpdateInput>()

  const ingest = (
    list: Array<{
      id?: string
      projectName?: string
      crossSheetInvestmentId?: string
      stage?: string
      eclRate?: number
    }> | null | undefined,
    method: 'pdLgd' | 'lossRate',
  ) => {
    if (!Array.isArray(list)) return
    for (const r of list) {
      const name = String(r?.projectName || '').trim()
      const stableId = String(r?.crossSheetInvestmentId || r?.id || '').trim()
      const nameKey = normalizeInvestName(name)
      if (!stableId && !nameKey) continue
      const rate = Number(r.eclRate)
      if (!Number.isFinite(rate)) continue
      const mapKey = stableId ? `id:${stableId}` : `name:${nameKey}`
      map.set(mapKey, {
        projectName: name || stableId,
        crossSheetInvestmentId: stableId || undefined,
        stage: (r.stage as EclRateUpdateInput['stage']) || '',
        eclRate: rate,
        method,
      })
    }
  }

  if (prefer === 'pdLgd') {
    ingest(lossRateRows, 'lossRate')
    ingest(pdLgdRows, 'pdLgd')
  } else {
    ingest(pdLgdRows, 'pdLgd')
    ingest(lossRateRows, 'lossRate')
  }

  return Array.from(map.values())
}

/**
 * G4-11 → G4-10：优先按稳定投资 ID，其次按投资项目名写入 ② creditLossRate；
 * ②A 仅在未触碰时同步；默认不新建行、跳过 Stage3（现值法）。
 */
export function applyEclRateUpdatesToRows(
  existing: ImpairmentCalcRow[] | unknown,
  updates: EclRateUpdateInput[],
  options?: {
    skipStage3?: boolean
    updateAdjustedRate?: 'ifUntouched' | 'always' | 'never'
    /** 强制覆盖人工调整后的 ②A；默认保留人工值。 */
    force?: boolean
  },
): EclRateApplyResult {
  const skipStage3 = options?.skipStage3 !== false
  const updateAdjusted = options?.force ? 'always' : (options?.updateAdjustedRate ?? 'ifUntouched')

  const rows: ImpairmentCalcRow[] = Array.isArray(existing)
    ? existing.map((r, i) => createBlankRow({
        ...r,
        id: r.id || crypto.randomUUID(),
        seq: r.seq || i + 1,
        investProject: r.investProject || `投资${i + 1}`,
        stageGroup: r.stageGroup || 'Stage1',
        crossSheetInvestmentId: r.crossSheetInvestmentId || r.id || '',
      }))
    : []

  const byId = new Map<string, ImpairmentCalcRow>()
  const byName = new Map(rows.map(r => [normalizeInvestName(r.investProject), r]))
  for (const row of rows) {
    for (const id of [row.crossSheetInvestmentId, row.id]) {
      const key = String(id || '').trim()
      if (key) byId.set(key, row)
    }
  }
  const skipped: EclRateApplyResult['skipped'] = []
  const matched: string[] = []
  const unmatched: string[] = []
  const matchedById: string[] = []
  const matchedByName: string[] = []
  let count = 0

  for (const u of updates) {
    const name = String(u.projectName || '').trim()
    const stableId = String(u.crossSheetInvestmentId || '').trim()
    const key = normalizeInvestName(name)
    const label = name || stableId || key
    if (!stableId && !key) continue
    const rate = Number(u.eclRate)
    if (!Number.isFinite(rate) || rate < 0) {
      skipped.push({ projectName: label, reason: 'invalid-rate' })
      continue
    }

    let matchVia: 'id' | 'name' | null = null
    let row = stableId ? byId.get(stableId) : undefined
    if (row) matchVia = 'id'
    if (!row && key) {
      row = byName.get(key)
      if (row) matchVia = 'name'
    }
    if (!row) {
      skipped.push({ projectName: label, reason: 'not-found' })
      unmatched.push(label)
      continue
    }
    if (skipStage3 && row.stageGroup === 'Stage3') {
      skipped.push({ projectName: row.investProject, reason: 'stage3' })
      continue
    }

    row.creditLossRate = rate
    if (stableId) row.crossSheetInvestmentId = row.crossSheetInvestmentId || stableId
    if (updateAdjusted === 'always' || (updateAdjusted === 'ifUntouched' && !row.adjRateTouched)) {
      row.adjustedCreditLossRate = rate
      if (updateAdjusted === 'always') row.adjRateTouched = true
    }
    count += 1
    matched.push(row.investProject)
    if (matchVia === 'id') matchedById.push(row.investProject)
    else matchedByName.push(row.investProject)
  }

  rows.forEach((r, i) => { r.seq = i + 1 })
  return {
    rows,
    count,
    matched,
    unmatched,
    skipped,
    matchReport: {
      byId: matchedById,
      byName: matchedByName,
      unmatched,
      skipped,
    },
  }
}

/**
 * G4-9 → G4-10：按投资项目名（归一化）匹配写入 stageGroup；缺失则新建空行。
 * 新行可带入账面余额；已有行仅在账面余额为空时回填。
 */
export function applyStageUpdatesToRows(
  existing: ImpairmentCalcRow[] | unknown,
  updates: StageUpdateInput[],
): { rows: ImpairmentCalcRow[]; count: number } {
  const rows: ImpairmentCalcRow[] = Array.isArray(existing)
    ? existing.map((r, i) => createBlankRow({
        ...r,
        id: r.id || crypto.randomUUID(),
        seq: r.seq || i + 1,
        investProject: r.investProject || `投资${i + 1}`,
        stageGroup: r.stageGroup || 'Stage1',
      }))
    : []

  const byName = new Map(rows.map(r => [normalizeInvestName(r.investProject), r]))
  let count = 0

  for (const u of updates) {
    const name = String(u.investProject || '').trim()
    const key = normalizeInvestName(name)
    if (!key) continue
    let row = byName.get(key)
    if (!row) {
      row = createBlankRow({
        id: crypto.randomUUID(),
        seq: rows.length + 1,
        investProject: name,
        stageGroup: u.auditStage,
        bookBalance: parseNum(u.bookBalance),
        differenceNote: '来自G4-9三阶段',
      })
      rows.push(row)
      byName.set(key, row)
    } else {
      row.stageGroup = u.auditStage
      const incoming = parseNum(u.bookBalance)
      if (incoming > 0 && !parseNum(row.bookBalance)) {
        row.bookBalance = incoming
      }
      if (!row.differenceNote?.includes('来自G4-9')) {
        row.differenceNote = [row.differenceNote, '来自G4-9三阶段'].filter(Boolean).join('|')
      }
    }
    count += 1
  }

  rows.forEach((r, i) => { r.seq = i + 1 })
  return { rows, count }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG4EclImpairmentCalc() {
  const rows = ref<ImpairmentCalcRow[]>([])
  const activeTab = ref<'tab1' | 'tab2'>('tab1')
  const activeRowIndex = ref(0)

  /**
   * recalcRow — 重算所有公式列 ③④⑥⑦⑧⑨ + currentProvision/currentReversal
   *
   * Stage1/2（损失率法）：
   *   ③ = ① × ②
   *   目标⑧' = (①+⑤)×②A（②A 未触碰则回落②）
   * Stage3（现值法）：
   *   ③ = max(0, ① − PV)
   *   目标⑧' = max(0, (①+⑤) − PV审定)（PV审定未触碰则回落未审PV）
   * 共通：
   *   ⑥ = ⑧' − ③
   *   ⑦ = ① + ⑤；⑧ = ③ + ⑥；⑨ = ⑦ − ⑧
   */
  function effectiveAdjRate(row: ImpairmentCalcRow): number {
    return row.adjRateTouched
      ? parseNum(row.adjustedCreditLossRate)
      : parseNum(row.creditLossRate)
  }

  function effectiveAdjPv(row: ImpairmentCalcRow): number {
    return row.adjPvTouched
      ? parseNum(row.adjustedPvFutureCashFlow)
      : parseNum(row.pvFutureCashFlow)
  }

  function recalcRow(row: ImpairmentCalcRow): void {
    const isStage3 = row.stageGroup === 'Stage3'

    if (isStage3) {
      row.impairmentProvision = calcImpairmentFromPv(row.bookBalance, row.pvFutureCashFlow)
    } else {
      row.impairmentProvision = calcImpairmentProvision(row.bookBalance, row.creditLossRate)
    }

    row.bookValue = calcBookValue(row.bookBalance, row.impairmentProvision)

    const adjBalance = calcAdjustedBalance(row.bookBalance, row.balanceAdjustment)
    row.adjBookBalance = adjBalance

    const targetAudited = isStage3
      ? calcImpairmentFromPv(adjBalance, effectiveAdjPv(row))
      : calcTargetAuditedImpairmentByRate(
        row.bookBalance,
        row.balanceAdjustment,
        effectiveAdjRate(row),
      )

    row.impairmentAdjustment = calcImpairmentAdjustmentIdentity(
      targetAudited,
      row.impairmentProvision,
    )

    row.adjImpairment = calcAdjustedImpairment(row.impairmentProvision, row.impairmentAdjustment)
    row.adjBookValue = calcAdjustedBookValue(row.adjBookBalance, row.adjImpairment)

    const diff = parseNum(row.adjImpairment) - parseNum(row.priorImpairment)
    row.currentProvision = round2(Math.max(0, diff))
    row.currentReversal = round2(Math.max(0, -diff))
  }

  // ─── Stage分组 + 小计汇总 ─────────────────────────────────────────────────

  const groupedRows = computed<ImpairmentCalcGrouped>(() => {
    const s1Rows = rows.value.filter(r => r.stageGroup === 'Stage1')
    const s2Rows = rows.value.filter(r => r.stageGroup === 'Stage2')
    const s3Rows = rows.value.filter(r => r.stageGroup === 'Stage3')

    return {
      stage1: { rows: s1Rows, subtotal: calcSubtotal(s1Rows) },
      stage2: { rows: s2Rows, subtotal: calcSubtotal(s2Rows) },
      stage3: { rows: s3Rows, subtotal: calcSubtotal(s3Rows) },
      grandTotal: calcSubtotal(rows.value),
    }
  })

  const grandTotal = computed<GroupSubtotal>(() => groupedRows.value.grandTotal)

  // ─── watch输入字段变化自动重算 ────────────────────────────────────────────

  watch(
    rows,
    (newRows) => {
      for (const row of newRows) {
        recalcRow(row)
      }
    },
    { deep: true },
  )

  // ─── 行CRUD ───────────────────────────────────────────────────────────────

  async function addRow(defaultStage: 'Stage1' | 'Stage2' | 'Stage3' = 'Stage1'): Promise<void> {
    const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValidator: (v) => (v?.trim() ? true : '投资项目名称不能为空'),
    })
    if (!value?.trim()) return

    const newRow = createBlankRow({
      id: crypto.randomUUID(),
      seq: rows.value.length + 1,
      investProject: value.trim(),
      stageGroup: defaultStage,
    })
    recalcRow(newRow)
    rows.value.push(newRow)
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  // ─── 数据加载 ─────────────────────────────────────────────────────────────

  function loadRows(data: ImpairmentCalcRow[]): void {
    rows.value = data.map((r, i) => {
      const row = createBlankRow({
        ...r,
        id: r.id || crypto.randomUUID(),
        seq: i + 1,
        adjustedPvFutureCashFlow: r.adjustedPvFutureCashFlow ?? r.pvFutureCashFlow ?? 0,
        adjRateTouched: r.adjRateTouched ?? false,
        adjPvTouched: r.adjPvTouched ?? false,
      })
      recalcRow(row)
      return row
    })
  }

  /** 从 checklist JSON 原始字符串加载 */
  function loadFromRaw(raw: string | null | undefined): void {
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      const list = Array.isArray(parsed) ? parsed : parsed?.rows
      if (Array.isArray(list)) loadRows(list)
    } catch { /* ignore */ }
  }

  /** 应用 G4-9 同步的阶段更新 */
  function applyStageUpdates(updates: StageUpdateInput[]): number {
    const applied = applyStageUpdatesToRows(rows.value, updates)
    loadRows(applied.rows)
    return applied.count
  }

  /** 应用 G4-11 同步的 ECL 损失率 */
  function applyEclRateUpdates(
    updates: EclRateUpdateInput[],
    options?: Parameters<typeof applyEclRateUpdatesToRows>[2],
  ): EclRateApplyResult {
    const applied = applyEclRateUpdatesToRows(rows.value, updates, options)
    loadRows(applied.rows)
    return applied
  }

  // ─── 导出序列化 ──────────────────────────────────────────────────────────

  function toJSON(): ImpairmentCalcRow[] {
    return rows.value.map(r => ({ ...r }))
  }

  return {
    rows,
    activeTab,
    activeRowIndex,
    groupedRows,
    grandTotal,
    recalcRow,
    effectiveAdjRate,
    effectiveAdjPv,
    addRow,
    removeRow,
    loadRows,
    loadFromRaw,
    applyStageUpdates,
    applyEclRateUpdates,
    toJSON,
    createBlankRow,
  }
}

export default useG4EclImpairmentCalc
