/**
 * useK1WriteoffCheck — K1-9 坏账准备转回（收回）、核销检查表
 *
 * 职责：
 * - 双表动态行（转回 + 核销）CRUD 与合计
 * - 与 K1-3 坏账准备明细「本期转回/本期核销」列勾稽
 * - 行级预警：转回金额超原计提、必填缺失、关联方核销
 * - 审计程序 / 说明 / 结论持久化（K1-9-writeoff）
 * - 写出 K1-9-reversal-total / K1-9-writeoff-total 供其他底稿读取
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum } from './useD2FormulaEngine'
import {
  parseK13Payload,
  flattenK13ForImport,
  sumK13Column,
} from './useK1BadDebt'
import {
  isReversalExceedsProvision,
  getMissingReversalFields as getMissingD1ReversalFields,
  getMissingWriteoffFields as getMissingD1WriteoffFields,
  type ReversalRow as D1ReversalRow,
  type WriteoffRow as D1WriteoffRow,
} from './useD1WriteoffCheck'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K1ReversalRow {
  id: string
  unit: string
  reason: string
  method: string
  basis: string
  amount: number
  accumProvision: number
  isReasonable: string
  analysis: string
  indexNo: string
}

export interface K1WriteoffRow {
  id: string
  unit: string
  nature: string
  amount: number
  reason: string
  procedure: string
  relatedParty: string
  isReasonable: string
  analysis: string
  indexNo: string
}

export const K1_RECOVERY_METHODS = [
  '现金收回', '银行转账', '票据兑现', '以物抵债', '债务重组', '其他',
] as const

export const K1_REASONABLE_OPTIONS = ['合理', '不合理', '待核实'] as const

export const K1_DEFAULT_AUDIT_PROCEDURES = [
  '获取本期大额坏账准备转回、核销明细清单，并与 K1-3 坏账准备明细表勾稽核对。',
  '了解大额转回/收回的原因及收回方式，结合原计提依据判断转回/收回是否合理，关注是否存在跨期调节利润。',
  '对实际核销项目，检查核销依据是否符合企业会计政策及监管规定，核销程序是否履行，会计处理是否正确。',
  '对已确认并核销的坏账重新收回的，检查其会计处理是否正确（先转回再收款或按准则规定处理）。',
].join('\n')

const ITEM_ID = 'K1-9-writeoff'
const REVERSAL_TOTAL_KEY = 'K1-9-reversal-total'
const WRITEOFF_TOTAL_KEY = 'K1-9-writeoff-total'
const K1_3_ROWS_KEY = 'K1-3-baddebt-rows'
const K1_11_ITEM_ID = 'K1-11-related-party'

export interface K1BadDebtSourceRow {
  id: string
  label: string
  beginBadDebt: number
  provision: number
  reversal: number
  writeoff: number
  endBadDebt: number
  remark: string
}

export interface K1WriteoffImportResult {
  reversalAdded: number
  reversalUpdated: number
  writeoffAdded: number
  writeoffUpdated: number
  skipped: number
}

export function normalizeUnitName(name: string): string {
  return String(name || '').trim().replace(/\s+/g, '').toLowerCase()
}

export function parseK13BadDebtRows(json: string | undefined): K1BadDebtSourceRow[] {
  if (!json) return []
  try {
    const payload = parseK13Payload(json)
    return flattenK13ForImport(payload).map((r) => ({
      id: r.id,
      label: r.label,
      beginBadDebt: r.beginBadDebt,
      provision: r.provision,
      reversal: r.reversal,
      writeoff: r.writeoff,
      endBadDebt: r.endBadDebt,
      remark: r.remark,
    }))
  } catch {
    return []
  }
}

/** 从 K1-11 关联方检查表读取关联方名称集合 */
export function loadK11RelatedPartyNames(map: Map<string, any>): Set<string> {
  const names = new Set<string>()
  const raw = map.get(K1_11_ITEM_ID)?.remark
  if (!raw) return names
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw
    const rows = data?.tables?.rows
    if (!Array.isArray(rows)) return names
    for (const r of rows) {
      const n = normalizeUnitName(r.name ?? r.unit ?? r.counterparty ?? '')
      if (n) names.add(n)
    }
  } catch {
    // ignore
  }
  return names
}

function findReversalByUnit(rows: K1ReversalRow[], unit: string): K1ReversalRow | undefined {
  const key = normalizeUnitName(unit)
  return rows.find((r) => normalizeUnitName(r.unit) === key)
}

function findWriteoffByUnit(rows: K1WriteoffRow[], unit: string): K1WriteoffRow | undefined {
  const key = normalizeUnitName(unit)
  return rows.find((r) => normalizeUnitName(r.unit) === key)
}

/**
 * 从 K1-3 导入本期有转回/核销的明细行（同名合并，保留已填分析/索引号）
 */
export function importWriteoffFromK13(
  reversalRows: K1ReversalRow[],
  writeoffRows: K1WriteoffRow[],
  k13Rows: K1BadDebtSourceRow[],
  k11Names: Set<string>,
  minAmount = 0,
): K1WriteoffImportResult {
  const result: K1WriteoffImportResult = {
    reversalAdded: 0,
    reversalUpdated: 0,
    writeoffAdded: 0,
    writeoffUpdated: 0,
    skipped: 0,
  }

  for (const src of k13Rows) {
    const label = src.label.trim()
    if (!label) {
      result.skipped++
      continue
    }

    if (src.reversal > minAmount) {
      const accum = src.endBadDebt + src.reversal
      const existing = findReversalByUnit(reversalRows, label)
      if (existing) {
        existing.amount = src.reversal
        existing.accumProvision = existing.accumProvision || accum
        if (!existing.basis && src.remark) existing.basis = src.remark
        result.reversalUpdated++
      } else {
        reversalRows.push({
          ...emptyReversalRow(),
          unit: label,
          amount: src.reversal,
          accumProvision: accum,
          basis: src.remark,
        })
        result.reversalAdded++
      }
    }

    if (src.writeoff > minAmount) {
      const isRp = k11Names.has(normalizeUnitName(label)) ? '是' : ''
      const existing = findWriteoffByUnit(writeoffRows, label)
      if (existing) {
        existing.amount = src.writeoff
        if (!existing.relatedParty && isRp) existing.relatedParty = isRp
        if (!existing.nature && src.remark) existing.nature = src.remark
        result.writeoffUpdated++
      } else {
        writeoffRows.push({
          ...emptyWriteoffRow(),
          unit: label,
          amount: src.writeoff,
          nature: src.remark,
          relatedParty: isRp,
        })
        result.writeoffAdded++
      }
    }

    if (src.reversal <= minAmount && src.writeoff <= minAmount) {
      result.skipped++
    }
  }

  return result
}

/** 按 K1-11 关联方名录标记核销行的「是否关联方往来」（仅补「是」，不覆盖已填「否」） */
export function syncWriteoffRelatedPartyFromK11(
  writeoffRows: K1WriteoffRow[],
  k11Names: Set<string>,
): number {
  let updated = 0
  for (const row of writeoffRows) {
    if (!row.unit || row.amount <= 0) continue
    if (k11Names.has(normalizeUnitName(row.unit)) && row.relatedParty !== '是') {
      row.relatedParty = '是'
      updated++
    }
  }
  return updated
}

function newId(): string {
  return `k1wo-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function emptyReversalRow(): K1ReversalRow {
  return {
    id: newId(),
    unit: '',
    reason: '',
    method: '',
    basis: '',
    amount: 0,
    accumProvision: 0,
    isReasonable: '',
    analysis: '',
    indexNo: '',
  }
}

function emptyWriteoffRow(): K1WriteoffRow {
  return {
    id: newId(),
    unit: '',
    nature: '',
    amount: 0,
    reason: '',
    procedure: '',
    relatedParty: '',
    isReasonable: '',
    analysis: '',
    indexNo: '',
  }
}

function toD1Reversal(row: K1ReversalRow): D1ReversalRow {
  return {
    id: row.id,
    unitName: row.unit,
    reason: row.reason,
    recoveryMethod: row.method,
    originalBasis: row.basis,
    reversalAmount: row.amount,
    priorProvisionAmount: row.accumProvision,
    reasonabilityAnalysis: row.analysis,
    indexRef: row.indexNo,
  }
}

function toD1Writeoff(row: K1WriteoffRow): D1WriteoffRow {
  return {
    id: row.id,
    unitName: row.unit,
    noteNature: row.nature,
    writeoffAmount: row.amount,
    writeoffReason: row.reason,
    writeoffProcedure: row.procedure,
    isRelatedPartyGenerated: row.relatedParty,
    reasonabilityAnalysis: row.analysis,
    indexRef: row.indexNo,
  }
}

function deserializeReversal(raw: any): K1ReversalRow {
  const row = emptyReversalRow()
  if (!raw || typeof raw !== 'object') return row
  if (raw.id) row.id = String(raw.id)
  row.unit = raw.unit ?? raw.unitName ?? ''
  row.reason = raw.reason ?? ''
  row.method = raw.method ?? raw.recoveryMethod ?? ''
  row.basis = raw.basis ?? raw.originalBasis ?? ''
  row.amount = parseNum(raw.amount ?? raw.reversalAmount)
  row.accumProvision = parseNum(raw.accumProvision ?? raw.priorProvisionAmount)
  row.isReasonable = raw.isReasonable ?? ''
  row.analysis = raw.analysis ?? raw.reasonabilityAnalysis ?? ''
  row.indexNo = raw.indexNo ?? raw.indexRef ?? ''
  return row
}

function deserializeWriteoff(raw: any): K1WriteoffRow {
  const row = emptyWriteoffRow()
  if (!raw || typeof raw !== 'object') return row
  if (raw.id) row.id = String(raw.id)
  row.unit = raw.unit ?? raw.unitName ?? ''
  row.nature = raw.nature ?? raw.noteNature ?? ''
  row.amount = parseNum(raw.amount ?? raw.writeoffAmount)
  row.reason = raw.reason ?? raw.writeoffReason ?? ''
  row.procedure = raw.procedure ?? raw.writeoffProcedure ?? ''
  row.relatedParty = raw.relatedParty ?? raw.isRelatedPartyGenerated ?? ''
  row.isReasonable = raw.isReasonable ?? ''
  row.analysis = raw.analysis ?? raw.reasonabilityAnalysis ?? ''
  row.indexNo = raw.indexNo ?? raw.indexRef ?? ''
  return row
}

function sumK1BadDebtColumn(json: string | undefined, col: 'reversal' | 'writeoff'): number {
  if (!json) return 0
  try {
    return sumK13Column(parseK13Payload(json), col)
  } catch {
    return 0
  }
}

export function getMissingK1ReversalFields(row: K1ReversalRow): string[] {
  return getMissingD1ReversalFields(toD1Reversal(row))
}

export function getMissingK1WriteoffFields(row: K1WriteoffRow): string[] {
  return getMissingD1WriteoffFields(toD1Writeoff(row))
}

export interface UseK1WriteoffCheckOpts {
  allResponses: Ref<Map<string, any>>
}

export function useK1WriteoffCheck(opts: UseK1WriteoffCheckOpts) {
  const reversalRows = ref<K1ReversalRow[]>([])
  const writeoffRows = ref<K1WriteoffRow[]>([])
  const auditProcedures = ref(K1_DEFAULT_AUDIT_PROCEDURES)
  const auditNote = ref('')
  const conclusion = ref('')
  const conclusionOption = ref('')

  function load(): void {
    const stored = opts.allResponses.value.get(ITEM_ID)
    const raw = stored?.remark ?? stored?.value
    if (!raw) return
    try {
      const data = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(data.tables?.reversal)) {
        reversalRows.value = data.tables.reversal.map(deserializeReversal)
      }
      if (Array.isArray(data.tables?.writeoff)) {
        writeoffRows.value = data.tables.writeoff.map(deserializeWriteoff)
      }
      auditProcedures.value = data.auditProcedures || K1_DEFAULT_AUDIT_PROCEDURES
      auditNote.value = data.auditNote ?? ''
      conclusion.value = data.conclusion ?? ''
      conclusionOption.value = data.conclusionOption ?? ''
    } catch {
      // ignore corrupt payload
    }
  }

  const reversalTotal: ComputedRef<number> = computed(() =>
    reversalRows.value.reduce((s, r) => s + r.amount, 0),
  )

  const writeoffTotal: ComputedRef<number> = computed(() =>
    writeoffRows.value.reduce((s, r) => s + r.amount, 0),
  )

  const k13ReversalTotal: ComputedRef<number> = computed(() =>
    sumK1BadDebtColumn(opts.allResponses.value.get(K1_3_ROWS_KEY)?.remark, 'reversal'),
  )

  const k13WriteoffTotal: ComputedRef<number> = computed(() =>
    sumK1BadDebtColumn(opts.allResponses.value.get(K1_3_ROWS_KEY)?.remark, 'writeoff'),
  )

  const reversalDiff: ComputedRef<number | null> = computed(() => {
    if (k13ReversalTotal.value === 0 && reversalTotal.value === 0) return null
    return reversalTotal.value - k13ReversalTotal.value
  })

  const writeoffDiff: ComputedRef<number | null> = computed(() => {
    if (k13WriteoffTotal.value === 0 && writeoffTotal.value === 0) return null
    return writeoffTotal.value - k13WriteoffTotal.value
  })

  const reversalConsistencyWarning: ComputedRef<string | null> = computed(() => {
    const diff = reversalDiff.value
    if (diff == null || Math.abs(diff) < 0.01) return null
    return `本表转回合计 ${reversalTotal.value.toFixed(2)} 与 K1-3 本期转回合计 ${k13ReversalTotal.value.toFixed(2)} 差异 ${diff.toFixed(2)}，请查明原因。`
  })

  const writeoffConsistencyWarning: ComputedRef<string | null> = computed(() => {
    const diff = writeoffDiff.value
    if (diff == null || Math.abs(diff) < 0.01) return null
    return `本表核销合计 ${writeoffTotal.value.toFixed(2)} 与 K1-3 本期核销合计 ${k13WriteoffTotal.value.toFixed(2)} 差异 ${diff.toFixed(2)}，请查明原因。`
  })

  const relatedPartyWriteoffCount: ComputedRef<number> = computed(() =>
    writeoffRows.value.filter((r) => r.amount > 0 && r.relatedParty === '是').length,
  )

  function addRow(section: 'reversal' | 'writeoff'): void {
    if (section === 'reversal') reversalRows.value = [...reversalRows.value, emptyReversalRow()]
    else writeoffRows.value = [...writeoffRows.value, emptyWriteoffRow()]
  }

  function removeRow(section: 'reversal' | 'writeoff', id: string): void {
    if (section === 'reversal') reversalRows.value = reversalRows.value.filter((r) => r.id !== id)
    else writeoffRows.value = writeoffRows.value.filter((r) => r.id !== id)
  }

  function updateReversal(id: string, field: keyof K1ReversalRow, value: any): void {
    const row = reversalRows.value.find((r) => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
  }

  function updateWriteoff(id: string, field: keyof K1WriteoffRow, value: any): void {
    const row = writeoffRows.value.find((r) => r.id === id)
    if (!row) return
    ;(row as any)[field] = value
  }

  function serialize(): string {
    return JSON.stringify({
      tables: { reversal: reversalRows.value, writeoff: writeoffRows.value },
      auditProcedures: auditProcedures.value,
      auditNote: auditNote.value,
      conclusion: conclusion.value,
      conclusionOption: conclusionOption.value,
    })
  }

  function buildSavePayload(): { itemId: string; remark: string; totals: Array<{ item_id: string; remark: string }> } {
    const totals = [
      { item_id: REVERSAL_TOTAL_KEY, remark: String(reversalTotal.value) },
      { item_id: WRITEOFF_TOTAL_KEY, remark: String(writeoffTotal.value) },
    ]
    return { itemId: ITEM_ID, remark: serialize(), totals }
  }

  function importFromK13(minAmount = 0): K1WriteoffImportResult {
    const k13Rows = parseK13BadDebtRows(opts.allResponses.value.get(K1_3_ROWS_KEY)?.remark)
    const k11Names = loadK11RelatedPartyNames(opts.allResponses.value)
    const result = importWriteoffFromK13(
      reversalRows.value,
      writeoffRows.value,
      k13Rows,
      k11Names,
      minAmount,
    )
    reversalRows.value = [...reversalRows.value]
    writeoffRows.value = [...writeoffRows.value]
    return result
  }

  function syncRelatedPartyFromK11(): number {
    const k11Names = loadK11RelatedPartyNames(opts.allResponses.value)
    const n = syncWriteoffRelatedPartyFromK11(writeoffRows.value, k11Names)
    if (n > 0) writeoffRows.value = [...writeoffRows.value]
    return n
  }

  const k13ImportableCount: ComputedRef<number> = computed(() => {
    const rows = parseK13BadDebtRows(opts.allResponses.value.get(K1_3_ROWS_KEY)?.remark)
    return rows.filter((r) => r.reversal > 0 || r.writeoff > 0).length
  })

  watch(
    () => opts.allResponses.value.get(ITEM_ID)?.remark,
    () => {
      if (reversalRows.value.length === 0 && writeoffRows.value.length === 0) load()
    },
    { immediate: true },
  )

  return {
    reversalRows,
    writeoffRows,
    auditProcedures,
    auditNote,
    conclusion,
    conclusionOption,
    reversalTotal,
    writeoffTotal,
    k13ReversalTotal,
    k13WriteoffTotal,
    reversalDiff,
    writeoffDiff,
    reversalConsistencyWarning,
    writeoffConsistencyWarning,
    relatedPartyWriteoffCount,
    load,
    addRow,
    removeRow,
    updateReversal,
    updateWriteoff,
    serialize,
    buildSavePayload,
    importFromK13,
    syncRelatedPartyFromK11,
    k13ImportableCount,
    isReversalExceedsProvision,
  }
}
