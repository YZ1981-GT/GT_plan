/**
 * useF2OverallAnalysis — F2-18 存货总体分析表
 *
 * 对齐 xlsx：
 * A 存货构成分析（三期金额/结构比/是否异常）
 * B 存货指标分析（三期对比）
 * C 存货指标分析（与同行业对比）
 * D 主要产品大类周转（三期）
 * 各段审计说明/异常原因 + 总体审计结论
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcTurnoverRate,
  calcChangeRate,
} from './useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from './useF2FormData'
import type { useF2CrossSheet } from './useF2CrossSheet'
import { F2_CATEGORIES } from './useF2Adjudication'

type CrossSheet = ReturnType<typeof useF2CrossSheet>
export type F2YesNo = '是' | '否' | ''

const STORAGE_KEY = 'F2-18-pack'
const LEGACY_CONCLUSION_KEY = 'F2-18-conclusion'
const LEGACY_TURNOVER_KEY = 'F2-18-turnover'
const LEGACY_NOTE_KEY = 'F2-overall-analysis-audit-note'
const LEGACY_AUDIT_CONCLUSION_KEY = 'F2-overall-analysis-audit-conclusion'

export interface F2AnomalyItem {
  id: string
  type: string
  message: string
  severity: 'warning' | 'danger'
}

export interface F2CompositionRow {
  key: string
  label: string
  /** 本年 / 上年 / 前年 金额 */
  amt0: number
  amt1: number
  amt2: number
  /** 是否手工覆盖（false 时本期/上年可从明细回写） */
  override: boolean
  abnormal: F2YesNo
}

export type F2StructureRow = F2CompositionRow & {
  share0: number
  share1: number
  share2: number
}

export interface F2IndicatorInputs {
  cogs0: number
  cogs1: number
  cogs2: number
  invAvg0: number
  invAvg1: number
  invAvg2: number
  invBal0: number
  invBal1: number
  invBal2: number
  impairment0: number
  impairment1: number
  impairment2: number
  caAvg0: number
  caAvg1: number
  caAvg2: number
  writeOff0: number
  writeOff1: number
  writeOff2: number
}

export interface F2IndicatorAbnormal {
  turnover: F2YesNo
  days: F2YesNo
  impairmentRatio: F2YesNo
  invToCa: F2YesNo
  scrap: F2YesNo
}

export interface F2IndustryPeer {
  name: string
  turnover: number
  days: number
  impairmentRatio: number
  invToCa: number
  scrap: number
}

export interface F2IndustryBlock {
  avg: F2IndustryPeer
  companyA: F2IndustryPeer
  companyB: F2IndustryPeer
  companyC: F2IndustryPeer
  abnormal: F2IndicatorAbnormal
}

export interface F2ProductTurnoverRow {
  rowId: string
  productName: string
  avgInv0: number
  cogs0: number
  avgInv1: number
  cogs1: number
  avgInv2: number
  cogs2: number
  abnormal: F2YesNo
}

export interface F2SectionNotes {
  note: string
  abnormalReason: string
}

export interface F2OverallPack {
  version: 2
  yearLabels: [string, string, string]
  composition: F2CompositionRow[]
  notesA: F2SectionNotes
  inputs: F2IndicatorInputs
  abnormalB: F2IndicatorAbnormal
  notesB: F2SectionNotes
  industry: F2IndustryBlock
  notesC: F2SectionNotes
  products: F2ProductTurnoverRow[]
  notesD: F2SectionNotes
  auditConclusion: string
}

export const F2_INDICATOR_DEFS = [
  { key: 'turnover' as const, label: '存货周转率（营业成本/平均存货余额）', unit: '次' },
  { key: 'days' as const, label: '存货平均天数（365/存货周转率）', unit: '天' },
  { key: 'impairmentRatio' as const, label: '存货跌价准备占存货余额比例', unit: '%' },
  { key: 'invToCa' as const, label: '存货占流动资产比例（平均存货/平均流动资产）', unit: '%' },
  { key: 'scrap' as const, label: '废品（核销）率（核销净额/平均存货净值）', unit: '%' },
]

function emptyNotes(): F2SectionNotes {
  return { note: '', abnormalReason: '' }
}

function emptyAbnormal(): F2IndicatorAbnormal {
  return { turnover: '', days: '', impairmentRatio: '', invToCa: '', scrap: '' }
}

function emptyPeer(name = ''): F2IndustryPeer {
  return { name, turnover: 0, days: 0, impairmentRatio: 0, invToCa: 0, scrap: 0 }
}

function emptyInputs(): F2IndicatorInputs {
  return {
    cogs0: 0, cogs1: 0, cogs2: 0,
    invAvg0: 0, invAvg1: 0, invAvg2: 0,
    invBal0: 0, invBal1: 0, invBal2: 0,
    impairment0: 0, impairment1: 0, impairment2: 0,
    caAvg0: 0, caAvg1: 0, caAvg2: 0,
    writeOff0: 0, writeOff1: 0, writeOff2: 0,
  }
}

function defaultComposition(): F2CompositionRow[] {
  return F2_CATEGORIES.map((c) => ({
    key: c.rowKey,
    label: c.label,
    amt0: 0,
    amt1: 0,
    amt2: 0,
    override: false,
    abnormal: '' as F2YesNo,
  }))
}

function emptyProduct(): F2ProductTurnoverRow {
  return {
    rowId: `f2oa-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    productName: '',
    avgInv0: 0, cogs0: 0,
    avgInv1: 0, cogs1: 0,
    avgInv2: 0, cogs2: 0,
    abnormal: '',
  }
}

function defaultPack(): F2OverallPack {
  return {
    version: 2,
    yearLabels: ['本期', '上期', '上上期'],
    composition: defaultComposition(),
    notesA: emptyNotes(),
    inputs: emptyInputs(),
    abnormalB: emptyAbnormal(),
    notesB: emptyNotes(),
    industry: {
      avg: emptyPeer('行业平均'),
      companyA: emptyPeer('公司A'),
      companyB: emptyPeer('公司B'),
      companyC: emptyPeer('公司C'),
      abnormal: emptyAbnormal(),
    },
    notesC: emptyNotes(),
    products: [emptyProduct()],
    notesD: emptyNotes(),
    auditConclusion: '',
  }
}

function normalizeYesNo(v: unknown): F2YesNo {
  if (v === '是' || v === '否') return v
  return ''
}

function rateToNumber(r: number | '' | 'N/A'): number | null {
  if (r === '' || r === 'N/A') return null
  return r
}

function calcIndicatorTriplet(
  inputs: F2IndicatorInputs,
  year: 0 | 1 | 2,
): Record<'turnover' | 'days' | 'impairmentRatio' | 'invToCa' | 'scrap', number> {
  const cogs = inputs[`cogs${year}` as keyof F2IndicatorInputs] as number
  const invAvg = inputs[`invAvg${year}` as keyof F2IndicatorInputs] as number
  const invBal = inputs[`invBal${year}` as keyof F2IndicatorInputs] as number
  const impairment = inputs[`impairment${year}` as keyof F2IndicatorInputs] as number
  const caAvg = inputs[`caAvg${year}` as keyof F2IndicatorInputs] as number
  const writeOff = inputs[`writeOff${year}` as keyof F2IndicatorInputs] as number
  const turnover = calcTurnoverRate(cogs, invAvg)
  const days = turnover ? 365 / turnover : 0
  const impairmentRatio = invBal ? (impairment / invBal) * 100 : 0
  const invToCa = caAvg ? (invAvg / caAvg) * 100 : 0
  const netAvg = Math.max(invAvg - impairment, 0)
  const scrap = netAvg ? (writeOff / netAvg) * 100 : 0
  return { turnover, days, impairmentRatio, invToCa, scrap }
}

function parsePack(jsonStr: string | null | undefined): F2OverallPack {
  if (!jsonStr) return defaultPack()
  try {
    const parsed = JSON.parse(jsonStr)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return defaultPack()
    const base = defaultPack()
    if (Array.isArray(parsed.yearLabels) && parsed.yearLabels.length >= 3) {
      base.yearLabels = [String(parsed.yearLabels[0]), String(parsed.yearLabels[1]), String(parsed.yearLabels[2])]
    }
    if (Array.isArray(parsed.composition)) {
      const map = new Map(parsed.composition.map((r: any) => [r.key, r]))
      base.composition = F2_CATEGORIES.map((c) => {
        const src = map.get(c.rowKey) || {}
        return {
          key: c.rowKey,
          label: c.label,
          amt0: parseNum(src.amt0),
          amt1: parseNum(src.amt1),
          amt2: parseNum(src.amt2),
          override: Boolean(src.override),
          abnormal: normalizeYesNo(src.abnormal),
        }
      })
    }
    for (const k of ['notesA', 'notesB', 'notesC', 'notesD'] as const) {
      const src = parsed[k] || {}
      base[k] = {
        note: src.note != null ? String(src.note) : '',
        abnormalReason: src.abnormalReason != null ? String(src.abnormalReason) : '',
      }
    }
    if (parsed.inputs && typeof parsed.inputs === 'object') {
      for (const key of Object.keys(base.inputs) as (keyof F2IndicatorInputs)[]) {
        if (parsed.inputs[key] != null) base.inputs[key] = parseNum(parsed.inputs[key])
      }
    }
    if (parsed.abnormalB) {
      for (const key of Object.keys(base.abnormalB) as (keyof F2IndicatorAbnormal)[]) {
        base.abnormalB[key] = normalizeYesNo(parsed.abnormalB[key])
      }
    }
    if (parsed.industry && typeof parsed.industry === 'object') {
      for (const peer of ['avg', 'companyA', 'companyB', 'companyC'] as const) {
        const src = parsed.industry[peer] || {}
        base.industry[peer] = {
          name: src.name != null ? String(src.name) : base.industry[peer].name,
          turnover: parseNum(src.turnover),
          days: parseNum(src.days),
          impairmentRatio: parseNum(src.impairmentRatio),
          invToCa: parseNum(src.invToCa),
          scrap: parseNum(src.scrap),
        }
      }
      if (parsed.industry.abnormal) {
        for (const key of Object.keys(base.industry.abnormal) as (keyof F2IndicatorAbnormal)[]) {
          base.industry.abnormal[key] = normalizeYesNo(parsed.industry.abnormal[key])
        }
      }
    }
    if (Array.isArray(parsed.products) && parsed.products.length) {
      base.products = parsed.products.map((r: any) => ({
        rowId: r.rowId || emptyProduct().rowId,
        productName: r.productName != null ? String(r.productName) : '',
        avgInv0: parseNum(r.avgInv0),
        cogs0: parseNum(r.cogs0),
        avgInv1: parseNum(r.avgInv1),
        cogs1: parseNum(r.cogs1),
        avgInv2: parseNum(r.avgInv2),
        cogs2: parseNum(r.cogs2),
        abnormal: normalizeYesNo(r.abnormal),
      }))
    }
    base.auditConclusion = parsed.auditConclusion != null ? String(parsed.auditConclusion) : ''
    return base
  } catch {
    return defaultPack()
  }
}

export function useF2OverallAnalysis(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  crossSheet: CrossSheet
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, crossSheet, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let hydrating = false

  const pack = ref<F2OverallPack>(defaultPack())

  function hydrate(): void {
    hydrating = true
    let stored = parsePack(allResponses.value.get(STORAGE_KEY)?.remark)

    // legacy conclusion / note
    if (!stored.auditConclusion) {
      stored.auditConclusion =
        allResponses.value.get(LEGACY_AUDIT_CONCLUSION_KEY)?.remark
        || allResponses.value.get(LEGACY_CONCLUSION_KEY)?.remark
        || ''
    }
    if (!stored.notesA.note) {
      const n = allResponses.value.get(LEGACY_NOTE_KEY)?.remark
      if (n) stored.notesA.note = n
    }
    // legacy turnover inputs
    const tur = allResponses.value.get(LEGACY_TURNOVER_KEY)?.remark
    if (tur) {
      try {
        const d = JSON.parse(tur)
        if (!stored.inputs.cogs0 && d.cogsAmount) stored.inputs.cogs0 = parseNum(d.cogsAmount)
      } catch { /* ignore */ }
    }

    pack.value = stored
    hydrating = false
    syncCompositionFromDetail()
  }

  /** Pull amt0/amt1 from F2-3~13 when not overridden */
  function syncCompositionFromDetail(): void {
    if (readonly.value) return
    const summaries = crossSheet.categorySummaries.value
    const byKey = new Map(summaries.map((s) => [s.rowKey, s]))
    let changed = false
    for (const row of pack.value.composition) {
      if (row.override) continue
      const s = byKey.get(row.key)
      if (!s) continue
      if (row.amt0 !== s.closingAmt || row.amt1 !== s.openingAmt) {
        row.amt0 = s.closingAmt
        row.amt1 = s.openingAmt
        changed = true
      }
    }
    // Auto-fill inv balances / avg from composition totals when zero
    const t0 = calcSubtotal(pack.value.composition.map((r) => r.amt0))
    const t1 = calcSubtotal(pack.value.composition.map((r) => r.amt1))
    const t2 = calcSubtotal(pack.value.composition.map((r) => r.amt2))
    if (!pack.value.inputs.invBal0 && t0) pack.value.inputs.invBal0 = t0
    if (!pack.value.inputs.invBal1 && t1) pack.value.inputs.invBal1 = t1
    if (!pack.value.inputs.invBal2 && t2) pack.value.inputs.invBal2 = t2
    if (!pack.value.inputs.invAvg0 && (t0 || t1)) {
      pack.value.inputs.invAvg0 = (t0 + t1) / 2
      changed = true
    }
    if (!pack.value.inputs.invAvg1 && (t1 || t2)) {
      pack.value.inputs.invAvg1 = (t1 + t2) / 2
      changed = true
    }
    if (changed) persist()
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => hydrate(),
    { immediate: true },
  )

  watch(
    () => crossSheet.categorySummaries.value,
    () => {
      if (!hydrating) syncCompositionFromDetail()
    },
    { deep: true },
  )

  // ─── Computed views ─────────────────────────────────────────────────────

  const yearLabels = computed(() => pack.value.yearLabels)

  const compositionRows = computed(() => {
    const rows = pack.value.composition
    const total0 = calcSubtotal(rows.map((r) => r.amt0))
    const total1 = calcSubtotal(rows.map((r) => r.amt1))
    const total2 = calcSubtotal(rows.map((r) => r.amt2))
    return rows.map((r) => ({
      ...r,
      share0: total0 ? (r.amt0 / total0) * 100 : 0,
      share1: total1 ? (r.amt1 / total1) * 100 : 0,
      share2: total2 ? (r.amt2 / total2) * 100 : 0,
    }))
  })

  const compositionTotals = computed(() => {
    const rows = pack.value.composition
    return {
      amt0: calcSubtotal(rows.map((r) => r.amt0)),
      amt1: calcSubtotal(rows.map((r) => r.amt1)),
      amt2: calcSubtotal(rows.map((r) => r.amt2)),
      share0: 100,
      share1: 100,
      share2: 100,
    }
  })

  const indicatorsByYear = computed(() => ({
    y0: calcIndicatorTriplet(pack.value.inputs, 0),
    y1: calcIndicatorTriplet(pack.value.inputs, 1),
    y2: calcIndicatorTriplet(pack.value.inputs, 2),
  }))

  const indicatorRows = computed(() => {
    const { y0, y1, y2 } = indicatorsByYear.value
    return F2_INDICATOR_DEFS.map((d) => {
      const v0 = y0[d.key]
      const v1 = y1[d.key]
      const v2 = y2[d.key]
      const ch01 = rateToNumber(calcChangeRate(v1, v0))
      const ch12 = rateToNumber(calcChangeRate(v2, v1))
      return {
        key: d.key,
        label: d.label,
        unit: d.unit,
        v0, v1, v2,
        change01: ch01 == null ? null : ch01 * 100,
        change12: ch12 == null ? null : ch12 * 100,
        abnormal: pack.value.abnormalB[d.key],
      }
    })
  })

  const industryRows = computed(() => {
    const client = indicatorsByYear.value.y0
    const avg = pack.value.industry.avg
    return F2_INDICATOR_DEFS.map((d) => {
      const cv = client[d.key]
      const iv = avg[d.key]
      const deviation = iv ? ((cv - iv) / iv) * 100 : null
      return {
        key: d.key,
        label: d.label,
        unit: d.unit,
        client: cv,
        deviation,
        industry: iv,
        companyA: pack.value.industry.companyA[d.key],
        companyB: pack.value.industry.companyB[d.key],
        companyC: pack.value.industry.companyC[d.key],
        abnormal: pack.value.industry.abnormal[d.key],
      }
    })
  })

  const productRows = computed(() =>
    pack.value.products.map((r) => {
      const t0 = calcTurnoverRate(r.cogs0, r.avgInv0)
      const t1 = calcTurnoverRate(r.cogs1, r.avgInv1)
      const t2 = calcTurnoverRate(r.cogs2, r.avgInv2)
      const ch01 = rateToNumber(calcChangeRate(t1, t0))
      return {
        ...r,
        turnover0: t0,
        turnover1: t1,
        turnover2: t2,
        change01: ch01 == null ? null : ch01 * 100,
      }
    }),
  )

  const abnormalCount = computed(() => {
    let n = 0
    for (const r of pack.value.composition) if (r.abnormal === '是') n++
    for (const k of Object.keys(pack.value.abnormalB) as (keyof F2IndicatorAbnormal)[]) {
      if (pack.value.abnormalB[k] === '是') n++
    }
    for (const k of Object.keys(pack.value.industry.abnormal) as (keyof F2IndicatorAbnormal)[]) {
      if (pack.value.industry.abnormal[k] === '是') n++
    }
    for (const r of pack.value.products) if (r.abnormal === '是') n++
    return n
  })

  /** Backward-compat aliases for old UI / AI */
  const analysisConclusion = computed({
    get: () => pack.value.auditConclusion,
    set: (v: string) => { if (!readonly.value) { pack.value.auditConclusion = v; persist() } },
  })
  const structureRows = compositionRows
  const anomalies = computed(() =>
    [
      ...pack.value.composition.filter((r) => r.abnormal === '是').map((r) => ({
        id: `comp-${r.key}`,
        type: '构成异常',
        message: `${r.label}构成标为异常`,
        severity: 'warning' as const,
      })),
      ...indicatorRows.value.filter((r) => r.abnormal === '是').map((r) => ({
        id: `ind-${r.key}`,
        type: '指标异常',
        message: `${r.label}标为异常`,
        severity: 'warning' as const,
      })),
    ],
  )
  const cogsAmount = computed({
    get: () => pack.value.inputs.cogs0,
    set: (v: number) => updateInput('cogs0', v),
  })
  const computedTurnoverRate = computed(() => indicatorsByYear.value.y0.turnover)
  const computedTurnoverDays = computed(() => indicatorsByYear.value.y0.days)

  // ─── Persist ────────────────────────────────────────────────────────────

  function flushSave(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function persist(): void {
    if (hydrating || readonly.value) return
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(pack.value),
    })
    // also mirror conclusion for older readers
    allResponses.value.set(LEGACY_CONCLUSION_KEY, {
      item_id: LEGACY_CONCLUSION_KEY,
      conclusion: null,
      remark: pack.value.auditConclusion,
    })
    debounceSave()
  }

  // ─── Mutations ──────────────────────────────────────────────────────────

  function updateYearLabel(idx: 0 | 1 | 2, label: string): void {
    if (readonly.value) return
    const next = [...pack.value.yearLabels] as [string, string, string]
    next[idx] = label
    pack.value.yearLabels = next
    persist()
  }

  function updateComposition(
    key: string,
    field: 'amt0' | 'amt1' | 'amt2' | 'abnormal' | 'override',
    value: string | number | boolean,
  ): void {
    if (readonly.value) return
    const idx = pack.value.composition.findIndex((r) => r.key === key)
    if (idx === -1) return
    const row = { ...pack.value.composition[idx] }
    if (field === 'abnormal') row.abnormal = normalizeYesNo(value)
    else if (field === 'override') row.override = Boolean(value)
    else {
      row[field] = parseNum(value as number)
      row.override = true
    }
    pack.value.composition.splice(idx, 1, row)
    persist()
  }

  function updateInput(field: keyof F2IndicatorInputs, value: number): void {
    if (readonly.value) return
    pack.value.inputs = { ...pack.value.inputs, [field]: parseNum(value) }
    persist()
  }

  function updateAbnormalB(key: keyof F2IndicatorAbnormal, value: string): void {
    if (readonly.value) return
    pack.value.abnormalB = { ...pack.value.abnormalB, [key]: normalizeYesNo(value) }
    persist()
  }

  function updateIndustryPeer(
    peer: 'avg' | 'companyA' | 'companyB' | 'companyC',
    field: keyof F2IndustryPeer,
    value: string | number,
  ): void {
    if (readonly.value) return
    const cur = { ...pack.value.industry[peer] }
    if (field === 'name') cur.name = String(value)
    else cur[field] = parseNum(value)
    pack.value.industry = { ...pack.value.industry, [peer]: cur }
    persist()
  }

  function updateIndustryAbnormal(key: keyof F2IndicatorAbnormal, value: string): void {
    if (readonly.value) return
    pack.value.industry = {
      ...pack.value.industry,
      abnormal: { ...pack.value.industry.abnormal, [key]: normalizeYesNo(value) },
    }
    persist()
  }

  function updateNotes(section: 'notesA' | 'notesB' | 'notesC' | 'notesD', field: keyof F2SectionNotes, value: string): void {
    if (readonly.value) return
    pack.value[section] = { ...pack.value[section], [field]: value }
    persist()
  }

  function addProductRow(): void {
    if (readonly.value) return
    pack.value.products.push(emptyProduct())
    persist()
  }

  function removeProductRow(rowId: string): void {
    if (readonly.value || pack.value.products.length <= 1) return
    pack.value.products = pack.value.products.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateProduct(
    rowId: string,
    field: keyof Omit<F2ProductTurnoverRow, 'rowId'>,
    value: string | number,
  ): void {
    if (readonly.value) return
    const idx = pack.value.products.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...pack.value.products[idx] }
    if (field === 'productName') row.productName = String(value)
    else if (field === 'abnormal') row.abnormal = normalizeYesNo(value)
    else (row as any)[field] = parseNum(value)
    pack.value.products.splice(idx, 1, row)
    persist()
  }

  function updateTurnoverInputs(patch: { cogsAmount?: number }): void {
    if (patch.cogsAmount !== undefined) updateInput('cogs0', patch.cogsAmount)
  }

  function aiContext(): Record<string, unknown> {
    return {
      yearLabels: pack.value.yearLabels,
      composition: compositionRows.value.map((r) => ({
        label: r.label, amt0: r.amt0, share0: r.share0, abnormal: r.abnormal,
      })),
      compositionTotals: compositionTotals.value,
      indicators: indicatorRows.value,
      industry: industryRows.value,
      products: productRows.value,
      abnormalCount: abnormalCount.value,
      notesA: pack.value.notesA,
      notesB: pack.value.notesB,
      notesC: pack.value.notesC,
      notesD: pack.value.notesD,
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  return {
    pack,
    yearLabels,
    compositionRows,
    compositionTotals,
    indicatorRows,
    industryRows,
    productRows,
    indicatorsByYear,
    abnormalCount,
    notesA: computed(() => pack.value.notesA),
    notesB: computed(() => pack.value.notesB),
    notesC: computed(() => pack.value.notesC),
    notesD: computed(() => pack.value.notesD),
    auditConclusion: analysisConclusion,
    analysisConclusion,
    structureRows,
    anomalies,
    cogsAmount,
    computedTurnoverRate,
    computedTurnoverDays,
    updateYearLabel,
    updateComposition,
    updateInput,
    updateAbnormalB,
    updateIndustryPeer,
    updateIndustryAbnormal,
    updateNotes,
    addProductRow,
    removeProductRow,
    updateProduct,
    updateTurnoverInputs,
    syncCompositionFromDetail,
    aiContext,
    flushSave,
    persist,
  }
}

export default useF2OverallAnalysis
