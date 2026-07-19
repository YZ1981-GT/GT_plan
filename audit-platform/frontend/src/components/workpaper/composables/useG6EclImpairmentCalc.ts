/**
 * useG6EclImpairmentCalc — G6-12 减值准备测算表
 *
 * 对齐 Excel：①账面余额 / ④⑨摊余成本；补 PV、信用组合；
 * Stage1/2 损失率法，Stage3 现值法（参考 G4-10）。
 */
import { ref, computed, watch } from 'vue'
import {
  calcImpairmentProvision,
  calcImpairmentFromPv,
  calcImpliedLossRate,
  calcImpairmentAdjustment,
  calcImpairmentAdjustmentIdentity,
  calcAdjustedBalance,
  calcAdjustedImpairment,
  calcAdjustedBookValue,
  parseNum,
} from '@/composables/useG6EclFormulaEngine'
import { ElMessageBox } from 'element-plus'
import type { ImpairmentCalcRow } from './useG6EclFormData'

export interface GroupSubtotal {
  amortizedCost: number         // Σ① 账面余额
  pvFutureCashFlow: number      // Σ 现值
  impairmentProvision: number   // Σ③
  bookValue: number             // Σ④ 摊余成本
  balanceAdjustment: number     // Σ⑤
  impairmentAdjustment: number  // Σ⑥
  adjBalance: number            // Σ⑦
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

function sumColumn(rows: ImpairmentCalcRow[], key: keyof ImpairmentCalcRow): number {
  const total = rows.reduce((s, r) => s + parseNum(r[key] as number), 0)
  return Math.round(total * 100) / 100
}

function calcSubtotal(rows: ImpairmentCalcRow[]): GroupSubtotal {
  return {
    amortizedCost: sumColumn(rows, 'amortizedCost'),
    pvFutureCashFlow: sumColumn(rows, 'pvFutureCashFlow'),
    impairmentProvision: sumColumn(rows, 'impairmentProvision'),
    bookValue: sumColumn(rows, 'bookValue'),
    balanceAdjustment: sumColumn(rows, 'balanceAdjustment'),
    impairmentAdjustment: sumColumn(rows, 'impairmentAdjustment'),
    adjBalance: sumColumn(rows, 'adjBalance'),
    adjImpairment: sumColumn(rows, 'adjImpairment'),
    adjBookValue: sumColumn(rows, 'adjBookValue'),
  }
}

export function createEmptyImpairmentRow(
  partial: Partial<ImpairmentCalcRow> & Pick<ImpairmentCalcRow, 'id' | 'seq' | 'investProject'>,
): ImpairmentCalcRow {
  const stage = (partial.stage || partial.stageGroup || 'Stage1') as ImpairmentCalcRow['stage']
  const { stage: _s, stageGroup: _sg, ...rest } = partial
  return {
    amortizedCost: 0,
    pvFutureCashFlow: 0,
    adjustedPvFutureCashFlow: 0,
    adjPvTouched: false,
    fairValue: 0,
    creditLossRate: 0,
    impairmentProvision: 0,
    bookValue: 0,
    balanceAdjustment: 0,
    adjustedCreditLossRate: 0,
    adjRateTouched: false,
    impairmentAdjustment: 0,
    creditGroupMethod: '',
    creditGroupName: '',
    ociImpact: 0,
    indexRef: '',
    adjBalance: 0,
    adjImpairment: 0,
    adjBookValue: 0,
    adjFairValue: 0,
    priorImpairment: 0,
    currentProvision: 0,
    currentReversal: 0,
    ociAdjustment: 0,
    differenceNote: '',
    ...rest,
    stageGroup: stage,
    stage,
  }
}

/** 旧数据迁移补全新字段 */
export function migrateImpairmentRow(raw: any, seq: number): ImpairmentCalcRow {
  const stage = (raw.stage || raw.stageGroup || 'Stage1') as ImpairmentCalcRow['stage']
  return createEmptyImpairmentRow({
    id: String(raw.id || `imp-${Date.now()}-${seq}`),
    seq,
    investProject: String(raw.investProject || ''),
    stageGroup: stage,
    stage,
    amortizedCost: parseNum(raw.amortizedCost ?? raw.bookBalance),
    pvFutureCashFlow: parseNum(raw.pvFutureCashFlow),
    adjustedPvFutureCashFlow: parseNum(
      raw.adjustedPvFutureCashFlow ?? raw.pvFutureCashFlow,
    ),
    adjPvTouched: Boolean(raw.adjPvTouched),
    fairValue: parseNum(raw.fairValue),
    creditLossRate: parseNum(raw.creditLossRate),
    balanceAdjustment: parseNum(raw.balanceAdjustment),
    adjustedCreditLossRate: parseNum(raw.adjustedCreditLossRate ?? raw.creditLossRate),
    adjRateTouched: Boolean(raw.adjRateTouched),
    creditGroupMethod: String(raw.creditGroupMethod || ''),
    creditGroupName: String(raw.creditGroupName || ''),
    ociImpact: parseNum(raw.ociImpact),
    indexRef: String(raw.indexRef || ''),
    adjFairValue: parseNum(raw.adjFairValue),
    priorImpairment: parseNum(raw.priorImpairment),
    ociAdjustment: parseNum(raw.ociAdjustment),
    differenceNote: String(raw.differenceNote || ''),
  })
}

function normalizeInvestName(name: string): string {
  return String(name || '').trim().replace(/\s+/g, '').toLowerCase()
}

export type EclRateUpdateInput = {
  projectName: string
  eclRate: number
  method: 'pdLgd' | 'lossRate'
  stage?: '' | 'Stage1' | 'Stage2' | 'Stage3'
}

export type EclRateSkipReason = 'not-found' | 'stage3' | 'invalid-rate'

export type EclRateApplyResult = {
  rows: ImpairmentCalcRow[]
  count: number
  matched: string[]
  unmatched: string[]
  skipped: Array<{ projectName: string; reason: EclRateSkipReason }>
}

/** 从 G6-13 两套测算行收集待回写损失率 */
export function collectEclRateUpdates(
  pdLgdRows: Array<{ projectName?: string; stage?: string; eclRate?: number }> | null | undefined,
  lossRateRows: Array<{ projectName?: string; stage?: string; eclRate?: number }> | null | undefined,
  prefer: 'pdLgd' | 'lossRate' = 'pdLgd',
): EclRateUpdateInput[] {
  const map = new Map<string, EclRateUpdateInput>()
  const ingest = (
    list: Array<{ projectName?: string; stage?: string; eclRate?: number }> | null | undefined,
    method: 'pdLgd' | 'lossRate',
  ) => {
    for (const r of list || []) {
      const name = String(r.projectName || '').trim()
      if (!name) continue
      const rate = Number(r.eclRate)
      if (!Number.isFinite(rate) || rate < 0) continue
      const key = normalizeInvestName(name)
      const next: EclRateUpdateInput = {
        projectName: name,
        eclRate: rate,
        method,
        stage: (r.stage as EclRateUpdateInput['stage']) || '',
      }
      if (!map.has(key) || prefer === method) map.set(key, next)
    }
  }
  if (prefer === 'pdLgd') {
    ingest(lossRateRows, 'lossRate')
    ingest(pdLgdRows, 'pdLgd')
  } else {
    ingest(pdLgdRows, 'pdLgd')
    ingest(lossRateRows, 'lossRate')
  }
  return [...map.values()]
}

export function applyEclRateUpdatesToRows(
  base: ImpairmentCalcRow[],
  updates: EclRateUpdateInput[],
  options?: { skipStage3?: boolean },
): EclRateApplyResult {
  const skipStage3 = options?.skipStage3 !== false
  const byName = new Map(base.map(r => [normalizeInvestName(r.investProject), r]))
  const matched: string[] = []
  const unmatched: string[] = []
  const skipped: Array<{ projectName: string; reason: EclRateSkipReason }> = []
  let count = 0
  const rows = base.map(r => ({ ...r }))

  for (const u of updates) {
    const key = normalizeInvestName(u.projectName)
    const idx = rows.findIndex(r => normalizeInvestName(r.investProject) === key)
    if (idx < 0) {
      unmatched.push(u.projectName)
      skipped.push({ projectName: u.projectName, reason: 'not-found' })
      continue
    }
    const row = rows[idx]
    if (skipStage3 && (row.stageGroup === 'Stage3' || row.stage === 'Stage3')) {
      skipped.push({ projectName: u.projectName, reason: 'stage3' })
      continue
    }
    if (!Number.isFinite(u.eclRate) || u.eclRate < 0 || u.eclRate > 1) {
      skipped.push({ projectName: u.projectName, reason: 'invalid-rate' })
      continue
    }
    row.creditLossRate = u.eclRate
    if (!row.adjRateTouched) row.adjustedCreditLossRate = u.eclRate
    matched.push(u.projectName)
    count += 1
    byName.set(key, row)
  }

  return { rows, count, matched, unmatched, skipped }
}

export function useG6EclImpairmentCalc() {
  const rows = ref<ImpairmentCalcRow[]>([])
  const activeTab = ref<'tab1' | 'tab2'>('tab1')
  const selectedRowIndex = ref(0)

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

  /**
   * 公式链：
   * Stage1/2：③=①×②；⑥=⑤×②A+①×(②A-②)
   * Stage3：③=max(0,①−PV)；⑥=目标⑧−③（目标⑧=max(0,⑦−审定PV)）
   * ⑦=①+⑤；⑧=③+⑥；⑨=⑦−⑧
   */
  function recalcRow(row: ImpairmentCalcRow): void {
    const isStage3 = (row.stageGroup || row.stage) === 'Stage3'
    const bal = parseNum(row.amortizedCost)

    if (isStage3 && (parseNum(row.pvFutureCashFlow) > 0 || row.adjPvTouched)) {
      row.impairmentProvision = calcImpairmentFromPv(bal, row.pvFutureCashFlow)
      row.creditLossRate = calcImpliedLossRate(bal, row.impairmentProvision)
    } else {
      row.impairmentProvision = calcImpairmentProvision(bal, row.creditLossRate)
    }

    row.bookValue = Math.round((bal - parseNum(row.impairmentProvision)) * 100) / 100

    if (!row.adjRateTouched) {
      row.adjustedCreditLossRate = parseNum(row.creditLossRate)
    }
    if (!row.adjPvTouched) {
      row.adjustedPvFutureCashFlow = parseNum(row.pvFutureCashFlow)
    }

    row.adjBalance = calcAdjustedBalance(bal, row.balanceAdjustment)

    if (isStage3 && (parseNum(row.pvFutureCashFlow) > 0 || row.adjPvTouched)) {
      const targetAudited = calcImpairmentFromPv(row.adjBalance, effectiveAdjPv(row))
      row.impairmentAdjustment = calcImpairmentAdjustmentIdentity(
        targetAudited,
        row.impairmentProvision,
      )
    } else {
      row.impairmentAdjustment = calcImpairmentAdjustment(
        row.balanceAdjustment,
        effectiveAdjRate(row),
        bal,
        row.creditLossRate,
      )
    }

    row.adjImpairment = calcAdjustedImpairment(row.impairmentProvision, row.impairmentAdjustment)
    row.adjBookValue = calcAdjustedBookValue(row.adjBalance, row.adjImpairment)

    const diff = parseNum(row.adjImpairment) - parseNum(row.priorImpairment)
    row.currentProvision = Math.round(Math.max(0, diff) * 100) / 100
    row.currentReversal = Math.round(Math.max(0, -diff) * 100) / 100

    // 同步 stage ↔ stageGroup
    if (row.stage && row.stage !== row.stageGroup) {
      row.stageGroup = row.stage
    } else if (row.stageGroup && row.stage !== row.stageGroup) {
      row.stage = row.stageGroup
    }
  }

  const groupedRows = computed<ImpairmentCalcGrouped>(() => {
    const s1Rows = rows.value.filter(r => (r.stageGroup || r.stage) === 'Stage1')
    const s2Rows = rows.value.filter(r => (r.stageGroup || r.stage) === 'Stage2')
    const s3Rows = rows.value.filter(r => (r.stageGroup || r.stage) === 'Stage3')
    return {
      stage1: { rows: s1Rows, subtotal: calcSubtotal(s1Rows) },
      stage2: { rows: s2Rows, subtotal: calcSubtotal(s2Rows) },
      stage3: { rows: s3Rows, subtotal: calcSubtotal(s3Rows) },
      grandTotal: calcSubtotal(rows.value),
    }
  })

  const grandTotal = computed(() => groupedRows.value.grandTotal)

  /** Excel 合计行 D：Σ现值 / Σ账面余额（回收率参考） */
  const totalRecoveryRate = computed(() => {
    const bal = grandTotal.value.amortizedCost
    if (bal === 0) return null
    return Math.round((grandTotal.value.pvFutureCashFlow / bal) * 1e6) / 1e6
  })

  watch(rows, (list) => {
    for (const row of list) recalcRow(row)
  }, { deep: true })

  const FORMULA_FIELDS = new Set([
    'impairmentProvision', 'bookValue', 'impairmentAdjustment',
    'adjBalance', 'adjImpairment', 'adjBookValue',
    'currentProvision', 'currentReversal',
  ])

  function updateRow(id: string, field: keyof ImpairmentCalcRow, value: any): void {
    if (FORMULA_FIELDS.has(field)) return
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    ;(row as any)[field] = value

    if (field === 'stage' || field === 'stageGroup') {
      row.stage = value as ImpairmentCalcRow['stage']
      row.stageGroup = value as ImpairmentCalcRow['stageGroup']
    }
    if (field === 'adjustedCreditLossRate') row.adjRateTouched = true
    if (field === 'adjustedPvFutureCashFlow') row.adjPvTouched = true
    if (field === 'creditLossRate' && !row.adjRateTouched) {
      row.adjustedCreditLossRate = parseNum(value)
    }
    if (field === 'pvFutureCashFlow' && !row.adjPvTouched) {
      row.adjustedPvFutureCashFlow = parseNum(value)
    }
    recalcRow(row)
  }

  async function addRow(defaultStage: 'Stage1' | 'Stage2' | 'Stage3' = 'Stage1'): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增减值测算行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValidator: (v) => (v?.trim() ? true : '投资项目名称不能为空'),
      })
      if (!value?.trim()) return
      const newRow = createEmptyImpairmentRow({
        id: crypto.randomUUID(),
        seq: rows.value.length + 1,
        investProject: value.trim(),
        stageGroup: defaultStage,
        stage: defaultStage,
      })
      recalcRow(newRow)
      rows.value.push(newRow)
      selectedRowIndex.value = rows.value.length - 1
    } catch {
      /* cancel */
    }
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    if (selectedRowIndex.value >= rows.value.length) {
      selectedRowIndex.value = Math.max(0, rows.value.length - 1)
    }
  }

  function loadRows(data: ImpairmentCalcRow[] | null | undefined): void {
    if (!data?.length) {
      rows.value = []
      return
    }
    rows.value = data.map((r, i) => {
      const row = migrateImpairmentRow(r, i + 1)
      recalcRow(row)
      return row
    })
  }

  function toJSON(): ImpairmentCalcRow[] {
    return rows.value.map(r => ({ ...r }))
  }

  /**
   * 应用 G6-13 测算损失率至本表（按投资项目名匹配；默认跳过 Stage3）
   */
  function applyEclRateUpdates(
    updates: EclRateUpdateInput[],
    options?: { skipStage3?: boolean },
  ): EclRateApplyResult {
    const result = applyEclRateUpdatesToRows(rows.value, updates, options)
    rows.value = result.rows
    return result
  }

  return {
    rows,
    activeTab,
    selectedRowIndex,
    groupedRows,
    grandTotal,
    totalRecoveryRate,
    recalcRow,
    updateRow,
    addRow,
    removeRow,
    loadRows,
    toJSON,
    applyEclRateUpdates,
    effectiveAdjRate,
    effectiveAdjPv,
  }
}

export default useG6EclImpairmentCalc
