/**
 * useK1BadDebt — K1-3 坏账准备明细表
 *
 * 对齐致同源模板 K1-3：
 *   (一) 坏账准备明细表 — 单项/组合/合计，期初·本期增减·期末（账面/调整/审定）
 *   (二) 三阶段转入转出 — Stage1/2/3 + 合计 + 与TB核查
 *
 * 公式：
 *   期初审定 = 期初账面 + 期初调整
 *   期末账面 = 期初审定 + 计提 + 其他增加 − 转回 − 核销 − 其他减少
 *   期末审定 = 期末账面 + 期末调整
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { parseNum } from './useD2FormulaEngine'
import { calcAuditedAmount, calcSubtotal } from './useK1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type K1BadDebtCategory = 'individual' | 'portfolio' | 'total'

export interface K1BadDebtMainRow {
  id: string
  category: K1BadDebtCategory
  label: string
  isSubRow: boolean
  isFixed: boolean
  priorBook: number
  priorAdj: number
  priorAudited: number
  currentProvision: number
  currentOtherIncrease: number
  currentReversal: number
  currentWriteOff: number
  currentOtherDecrease: number
  currentBook: number
  currentAdj: number
  currentAudited: number
  reason: string
}

export type K1StageAmountKey = 'stage1' | 'stage2' | 'stage3'

export interface K1StageMovementRow {
  key: string
  label: string
  stage1: number
  stage2: number
  stage3: number
  editable: boolean
}

export interface K1BadDebtPayloadV2 {
  version: 2
  mainRows: K1BadDebtMainRow[]
  stageMovements: K1StageMovementRow[]
  auditNote: string
  conclusion: string
  conclusionOption: string
}

/** @deprecated V1 扁平行，供 K1-9 导入兼容 */
export interface K1BadDebtRow {
  id: string
  label: string
  beginBadDebt: number
  provision: number
  reversal: number
  writeoff: number
  endBadDebt: number
  provisionRate: number | null
  receivableEnd: number
  stage: 1 | 2 | 3
  remark: string
}

export interface K1BadDebtCrossValidation {
  calcProvision: number
  bookedProvision: number
  diff: number
  isMatch: boolean
}

export interface UseK1BadDebtOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}

const STORAGE_KEY = 'K1-3-baddebt-rows'

const NUMERIC_MAIN_FIELDS: (keyof K1BadDebtMainRow)[] = [
  'priorBook', 'priorAdj', 'priorAudited',
  'currentProvision', 'currentOtherIncrease',
  'currentReversal', 'currentWriteOff', 'currentOtherDecrease',
  'currentBook', 'currentAdj', 'currentAudited',
]

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function round2(n: number): number {
  return Math.round(parseNum(n) * 100) / 100
}

export function recalcK1BadDebtMainRow(row: K1BadDebtMainRow): K1BadDebtMainRow {
  row.priorAudited = round2(calcAuditedAmount(row.priorBook, row.priorAdj, 0))
  row.currentBook = round2(
    row.priorAudited
    + parseNum(row.currentProvision)
    + parseNum(row.currentOtherIncrease)
    - parseNum(row.currentReversal)
    - parseNum(row.currentWriteOff)
    - parseNum(row.currentOtherDecrease),
  )
  row.currentAudited = round2(calcAuditedAmount(row.currentBook, row.currentAdj, 0))
  return row
}

function createFixedMainRow(category: K1BadDebtCategory, label: string): K1BadDebtMainRow {
  return recalcK1BadDebtMainRow({
    id: `fixed-${category}`,
    category,
    label,
    isSubRow: false,
    isFixed: true,
    priorBook: 0,
    priorAdj: 0,
    priorAudited: 0,
    currentProvision: 0,
    currentOtherIncrease: 0,
    currentReversal: 0,
    currentWriteOff: 0,
    currentOtherDecrease: 0,
    currentBook: 0,
    currentAdj: 0,
    currentAudited: 0,
    reason: '',
  })
}

function createSubRow(label = ''): K1BadDebtMainRow {
  return recalcK1BadDebtMainRow({
    id: uid('sub'),
    category: 'individual',
    label,
    isSubRow: true,
    isFixed: false,
    priorBook: 0,
    priorAdj: 0,
    priorAudited: 0,
    currentProvision: 0,
    currentOtherIncrease: 0,
    currentReversal: 0,
    currentWriteOff: 0,
    currentOtherDecrease: 0,
    currentBook: 0,
    currentAdj: 0,
    currentAudited: 0,
    reason: '',
  })
}

export function defaultStageMovements(): K1StageMovementRow[] {
  return [
    { key: 'opening', label: '期初余额', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 's1-s2', label: '第一阶段→第二阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 's1-s3', label: '第一阶段→第三阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 's2-s1', label: '第二阶段→第一阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 's2-s3', label: '第二阶段→第三阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 's3-s1', label: '第三阶段→第一阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 's3-s2', label: '第三阶段→第二阶段', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'provision', label: '本年计提', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'reversal', label: '本年转回', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'writeoff', label: '本年核销', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'fx', label: '汇兑差异', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'other', label: '其他', stage1: 0, stage2: 0, stage3: 0, editable: true },
    { key: 'closing', label: '期末余额', stage1: 0, stage2: 0, stage3: 0, editable: false },
  ]
}

function emptyPayload(): K1BadDebtPayloadV2 {
  return {
    version: 2,
    mainRows: [
      createFixedMainRow('individual', '单项评估计提'),
      createFixedMainRow('portfolio', '按组合计提'),
      createFixedMainRow('total', '合计'),
    ],
    stageMovements: defaultStageMovements(),
    auditNote: '',
    conclusion: '',
    conclusionOption: '',
  }
}

function migrateV1Rows(rows: K1BadDebtRow[]): K1BadDebtPayloadV2 {
  const base = emptyPayload()
  if (!rows.length) return base

  const subRows = rows.map((r) =>
    recalcK1BadDebtMainRow({
      id: r.id || uid('sub'),
      category: 'individual',
      label: r.label,
      isSubRow: true,
      isFixed: false,
      priorBook: parseNum(r.beginBadDebt),
      priorAdj: 0,
      priorAudited: parseNum(r.beginBadDebt),
      currentProvision: parseNum(r.provision),
      currentOtherIncrease: 0,
      currentReversal: parseNum(r.reversal),
      currentWriteOff: parseNum(r.writeoff),
      currentOtherDecrease: 0,
      currentBook: 0,
      currentAdj: 0,
      currentAudited: parseNum(r.endBadDebt),
      reason: r.remark || '',
    }),
  )

  base.mainRows = [
    ...subRows.length ? [createFixedMainRow('individual', '单项评估计提'), ...subRows] : [createFixedMainRow('individual', '单项评估计提')],
    createFixedMainRow('portfolio', '按组合计提'),
    createFixedMainRow('total', '合计'),
  ]
  recomputeCategoryTotals(base.mainRows)
  return base
}

export function parseK13Payload(raw: unknown): K1BadDebtPayloadV2 {
  const base = emptyPayload()
  if (raw == null || raw === '') return base

  let parsed: any = raw
  if (typeof raw === 'string') {
    try {
      parsed = JSON.parse(raw)
    } catch {
      return base
    }
  }

  if (Array.isArray(parsed)) {
    return migrateV1Rows(parsed as K1BadDebtRow[])
  }

  if (parsed?.version === 2) {
    const p = parsed as Partial<K1BadDebtPayloadV2>
    const mainRows = Array.isArray(p.mainRows)
      ? p.mainRows.map((r) => recalcK1BadDebtMainRow({ ...createFixedMainRow('individual', ''), ...r }))
      : base.mainRows
    const stageMovements = Array.isArray(p.stageMovements) && p.stageMovements.length
      ? p.stageMovements.map((r) => ({ ...r, editable: r.key !== 'closing' }))
      : defaultStageMovements()
    return {
      version: 2,
      mainRows,
      stageMovements,
      auditNote: p.auditNote ?? '',
      conclusion: p.conclusion ?? '',
      conclusionOption: p.conclusionOption ?? '',
    }
  }

  return base
}

/** 扁平化供 K1-9 导入（单项子行 + 组合行） */
export function flattenK13ForImport(payload: K1BadDebtPayloadV2): Array<{
  id: string
  label: string
  beginBadDebt: number
  provision: number
  reversal: number
  writeoff: number
  endBadDebt: number
  remark: string
}> {
  const individualSubs = payload.mainRows.filter((r) => r.category === 'individual' && r.isSubRow)
  const portfolio = payload.mainRows.find((r) => r.category === 'portfolio' && r.isFixed)
  const mapRow = (r: K1BadDebtMainRow) => ({
    id: r.id,
    label: r.label,
    beginBadDebt: r.priorAudited,
    provision: r.currentProvision,
    reversal: r.currentReversal,
    writeoff: r.currentWriteOff,
    endBadDebt: r.currentAudited,
    remark: r.reason,
  })

  if (individualSubs.length) {
    const rows = individualSubs.map(mapRow)
    if (portfolio && (portfolio.currentProvision || portfolio.currentReversal || portfolio.currentWriteOff || portfolio.currentAudited)) {
      rows.push(mapRow(portfolio))
    }
    return rows
  }

  const individual = payload.mainRows.find((r) => r.category === 'individual' && r.isFixed)
  const result: ReturnType<typeof mapRow>[] = []
  if (individual) result.push(mapRow(individual))
  if (portfolio) result.push(mapRow(portfolio))
  return result
}

export function sumK13Column(payload: K1BadDebtPayloadV2, col: 'reversal' | 'writeoff' | 'provision'): number {
  const total = payload.mainRows.find((r) => r.category === 'total' && r.isFixed)
  if (total) {
    if (col === 'reversal') return total.currentReversal
    if (col === 'writeoff') return total.currentWriteOff
    return total.currentProvision
  }
  return calcSubtotal(
    payload.mainRows
      .filter((r) => r.category !== 'total')
      .map((r) => (col === 'reversal' ? r.currentReversal : col === 'writeoff' ? r.currentWriteOff : r.currentProvision)),
  )
}

function recomputeCategoryTotals(rows: K1BadDebtMainRow[]): void {
  const sumCategory = (cat: K1BadDebtCategory, excludeSubFromFixed = true) => {
    const targets = rows.filter((r) => {
      if (r.category !== cat || r.isFixed === false && cat === 'total') return false
      if (cat === 'individual' && r.isFixed && excludeSubFromFixed) {
        return !rows.some((x) => x.category === 'individual' && x.isSubRow)
      }
      if (cat === 'individual' && r.isSubRow) return true
      if (cat === 'portfolio' && r.isFixed) return !rows.some((x) => x.category === 'portfolio' && x.isSubRow)
      if (cat === 'portfolio' && r.isSubRow) return true
      return r.isFixed
    })

    return targets.reduce((acc, r) => {
      for (const f of NUMERIC_MAIN_FIELDS) {
        if (f === 'priorAudited' || f === 'currentBook' || f === 'currentAudited') continue
        acc[f] = round2(parseNum(acc[f]) + parseNum(r[f]))
      }
      return acc
    }, {
      priorBook: 0, priorAdj: 0,
      currentProvision: 0, currentOtherIncrease: 0,
      currentReversal: 0, currentWriteOff: 0, currentOtherDecrease: 0,
      currentAdj: 0,
    } as Record<string, number>)
  }

  const indFixed = rows.find((r) => r.category === 'individual' && r.isFixed)
  const portFixed = rows.find((r) => r.category === 'portfolio' && r.isFixed)
  const totalFixed = rows.find((r) => r.category === 'total' && r.isFixed)
  const hasIndSubs = rows.some((r) => r.category === 'individual' && r.isSubRow)

  if (hasIndSubs && indFixed) {
    const sums = sumCategory('individual', true)
    Object.assign(indFixed, sums)
    recalcK1BadDebtMainRow(indFixed)
  }

  if (portFixed) {
    const portSubs = rows.filter((r) => r.category === 'portfolio' && r.isSubRow)
    if (portSubs.length) {
      const sums = sumCategory('portfolio', true)
      Object.assign(portFixed, sums)
      recalcK1BadDebtMainRow(portFixed)
    }
  }

  if (totalFixed) {
    const parts = [indFixed, portFixed].filter(Boolean) as K1BadDebtMainRow[]
    for (const f of NUMERIC_MAIN_FIELDS) {
      if (['priorAudited', 'currentBook', 'currentAudited'].includes(f)) continue
      ;(totalFixed as any)[f] = round2(calcSubtotal(parts.map((p) => parseNum((p as any)[f]))))
    }
    recalcK1BadDebtMainRow(totalFixed)
  }
}

export function recalcStageClosing(movements: K1StageMovementRow[]): K1StageMovementRow[] {
  const editable = movements.filter((r) => r.key !== 'closing')
  const closing = movements.find((r) => r.key === 'closing') || {
    key: 'closing', label: '期末余额', stage1: 0, stage2: 0, stage3: 0, editable: false,
  }
  for (const stage of ['stage1', 'stage2', 'stage3'] as K1StageAmountKey[]) {
    closing[stage] = round2(editable.reduce((s, r) => s + parseNum(r[stage]), 0))
  }
  const others = movements.filter((r) => r.key !== 'closing')
  return [...others, closing]
}

export function stageMovementTotal(row: K1StageMovementRow): number {
  return round2(parseNum(row.stage1) + parseNum(row.stage2) + parseNum(row.stage3))
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1BadDebt(opts: UseK1BadDebtOpts) {
  const { allResponses } = opts
  const payload = ref<K1BadDebtPayloadV2>(emptyPayload())

  const mainRows = computed(() => payload.value.mainRows)
  const stageMovements = computed(() => recalcStageClosing(payload.value.stageMovements))
  const individualRows = computed(() =>
    payload.value.mainRows.filter((r) => r.category === 'individual'),
  )
  const portfolioRows = computed(() =>
    payload.value.mainRows.filter((r) => r.category === 'portfolio'),
  )
  const totalRow = computed(() =>
    payload.value.mainRows.find((r) => r.category === 'total' && r.isFixed)!,
  )

  const totalEndBadDebt = computed(() => totalRow.value?.currentAudited ?? 0)
  const totalProvision = computed(() => totalRow.value?.currentProvision ?? 0)
  const totalReversal = computed(() => totalRow.value?.currentReversal ?? 0)
  const totalWriteoff = computed(() => totalRow.value?.currentWriteOff ?? 0)

  const stageMatrix = computed(() => {
    const closing = stageMovements.value.find((r) => r.key === 'closing')
    return {
      1: { total: closing?.stage1 ?? 0 },
      2: { total: closing?.stage2 ?? 0 },
      3: { total: closing?.stage3 ?? 0 },
    } as Record<1 | 2 | 3, { total: number }>
  })

  const crossValidation = computed<K1BadDebtCrossValidation>(() => {
    const calcProvision =
      Number(allResponses.value.get('K1-8-calc-provision-total')?.remark)
      || Number(allResponses.value.get('K1-8-calc-total-provision')?.remark)
      || 0
    const bookedProvision = totalEndBadDebt.value
    const diff = calcProvision - bookedProvision
    return { calcProvision, bookedProvision, diff, isMatch: Math.abs(diff) < 0.01 }
  })

  function touch() {
    payload.value = { ...payload.value }
  }

  function loadRows(): void {
    const raw = allResponses.value.get(STORAGE_KEY)?.remark
    payload.value = parseK13Payload(raw)
    payload.value.stageMovements = recalcStageClosing(payload.value.stageMovements)
  }

  function isMainRowEditable(row: K1BadDebtMainRow): boolean {
    if (row.category === 'total') return false
    if (row.isSubRow) return true
    const hasSubs = payload.value.mainRows.some(
      (r) => r.category === row.category && r.isSubRow,
    )
    return !hasSubs
  }

  function addSubRow(label = ''): void {
    payload.value.mainRows.splice(
      payload.value.mainRows.findIndex((r) => r.category === 'portfolio'),
      0,
      createSubRow(label),
    )
    recomputeCategoryTotals(payload.value.mainRows)
    touch()
  }

  function removeSubRow(id: string): void {
    payload.value.mainRows = payload.value.mainRows.filter((r) => r.id !== id)
    recomputeCategoryTotals(payload.value.mainRows)
    touch()
  }

  function updateMainRow(id: string, field: keyof K1BadDebtMainRow, value: string | number): void {
    const row = payload.value.mainRows.find((r) => r.id === id)
    if (!row || !isMainRowEditable(row)) return
    ;(row as any)[field] = value
    recalcK1BadDebtMainRow(row)
    recomputeCategoryTotals(payload.value.mainRows)
    touch()
  }

  function updateStageMovement(key: string, stage: K1StageAmountKey, value: number): void {
    const row = payload.value.stageMovements.find((r) => r.key === key)
    if (!row || !row.editable) return
    row[stage] = value
    payload.value.stageMovements = recalcStageClosing(payload.value.stageMovements)
    touch()
  }

  /** 从 (一) 合计同步本年计提/转回/核销至 (二) 对应行（合计列，阶段分布仍须人工拆分） */
  function syncStageFromMain(): void {
    const total = totalRow.value
    if (!total) return
    const map: Record<string, keyof K1BadDebtMainRow> = {
      provision: 'currentProvision',
      reversal: 'currentReversal',
      writeoff: 'currentWriteOff',
    }
    for (const [key, field] of Object.entries(map)) {
      const row = payload.value.stageMovements.find((r) => r.key === key)
      if (!row) continue
      const amt = parseNum(total[field])
      row.stage1 = amt
      row.stage2 = 0
      row.stage3 = 0
    }
    payload.value.stageMovements = recalcStageClosing(payload.value.stageMovements)
    touch()
  }

  function setAuditText(note: string, conclusion: string, option: string) {
    payload.value.auditNote = note
    payload.value.conclusion = conclusion
    payload.value.conclusionOption = option
    touch()
  }

  function serializeRows(): string {
    return JSON.stringify(payload.value)
  }

  /** @deprecated 兼容旧引用 */
  const rows = computed(() =>
    flattenK13ForImport(payload.value).map((r) => ({
      id: r.id,
      label: r.label,
      beginBadDebt: r.beginBadDebt,
      provision: r.provision,
      reversal: r.reversal,
      writeoff: r.writeoff,
      endBadDebt: r.endBadDebt,
      provisionRate: null,
      receivableEnd: 0,
      stage: 1 as const,
      remark: r.remark,
    })),
  )

  return {
    payload,
    mainRows,
    individualRows,
    portfolioRows,
    totalRow,
    stageMovements,
    rows,
    totalEndBadDebt,
    totalProvision,
    totalReversal,
    totalWriteoff,
    stageMatrix,
    crossValidation,
    loadRows,
    addSubRow,
    removeSubRow,
    updateMainRow,
    updateStageMovement,
    syncStageFromMain,
    isMainRowEditable,
    setAuditText,
    serializeRows,
    STORAGE_KEY,
  }
}
