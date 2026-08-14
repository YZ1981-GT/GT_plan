/**
 * useH8Impairment — H8-10 使用权资产减值测算 composable
 *
 * 对齐增强后 Excel：
 *   B迹象 → ②账面(原值−累计折旧) → ③④(H8-11) → ⑤MAX → ⑥MAX(②−⑤,0)
 *   → ⑧MAX(⑥−⑦,0) / ⑨MAX(⑦−⑥,0) 不得转回
 *
 * 联动：从 H8-2 带入②；从 H8-8(含减值) 带入⑦；回写/推送⑧→K11；有迹象强制索引含 H8-11
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'

import { exportMultiSheetData, readSheetObjects } from '@/composables/useExcelIO'
import {
  calcImpairmentBookValue,
  calcImpairmentRecoverableAmount,
  calcRequiredImpairment,
  calcImpairmentSupplement,
  calcImpairmentOverProvision,
  calcSubtotal,
} from './useH8FormulaEngine'
import { safeParseRows } from './h8RecoverableModel'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H8ImpairmentCalcRow {
  rowId: string
  assetName: string
  contractNo: string
  hasIndication: 'Y' | 'N' | ''
  indicationDesc: string
  /** ② 原值−累计折旧（不含减值） */
  bookValue: number
  /** ③ */
  fairValueLessDisposal: number
  /** ④ */
  dcfValue: number
  /** ⑤ */
  recoverableAmount: number
  /** ⑥ */
  impairmentAmount: number
  /** ⑦ */
  alreadyProvided: number
  /** ⑧ */
  supplement: number
  /** ⑨ 多提待查 */
  overProvision: number
  indexRef: string
  remark: string
  sourceDetailRowId?: string
}

export interface H8ImpPrepValidation {
  ok: boolean
  messages: string[]
}

export interface H8K11ReconcileResult {
  h10Supplement: number
  k11Amount: number | null
  diff: number | null
  isMatch: boolean
  source: string
  message: string
}

// ─── Keys ────────────────────────────────────────────────────────────────────

export const H810_ROWS_KEY = 'H8-10-rows'
export const H810_PARAMS_KEY = 'H8-10-params'
export const H810_SUPPLEMENT_TOTAL_KEY = 'H8-10-supplement-total'
export const H810_AUDIT_NOTE_KEY = 'H8-impairment-audit-note'
export const H810_AUDIT_CONCLUSION_KEY = 'H8-impairment-audit-conclusion'

const H82_ROWS_KEY = 'H8-2-rows'
const H88_DEP_ROWS_KEY = 'H8-8-dep-rows'
const H88_BRANCH_KEY = 'H8-8-branch'
const H811_GROUPS_KEY = 'H8-11-groups'

const K11_H8_AMOUNT_CANDIDATES = [
  { id: 'K11-2-detail-rows', label: 'K11-2 明细(使用权资产行)' },
  { id: 'K11-source-H8-amount', label: 'K11-source-H8-amount' },
  { id: 'K11-2-rou-occurrence', label: 'K11-2-rou-occurrence' },
]

// ─── Pure helpers (exported for tests) ───────────────────────────────────────

export function emptyH8ImpairmentRow(partial?: Partial<H8ImpairmentCalcRow>): H8ImpairmentCalcRow {
  return recomputeH8ImpairmentRow({
    rowId: partial?.rowId ?? `h810-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    assetName: '',
    contractNo: '',
    hasIndication: '',
    indicationDesc: '',
    bookValue: 0,
    fairValueLessDisposal: 0,
    dcfValue: 0,
    recoverableAmount: 0,
    impairmentAmount: 0,
    alreadyProvided: 0,
    supplement: 0,
    overProvision: 0,
    indexRef: '',
    remark: '',
    ...partial,
  })
}

export function recomputeH8ImpairmentRow(row: H8ImpairmentCalcRow): H8ImpairmentCalcRow {
  const has = row.hasIndication === 'Y'
  const recoverableAmount = calcImpairmentRecoverableAmount(
    row.fairValueLessDisposal,
    row.dcfValue,
    has,
  )
  const impairmentAmount = calcRequiredImpairment(row.bookValue, recoverableAmount, has)
  return {
    ...row,
    bookValue: Number(row.bookValue) || 0,
    fairValueLessDisposal: Number(row.fairValueLessDisposal) || 0,
    dcfValue: Number(row.dcfValue) || 0,
    alreadyProvided: Number(row.alreadyProvided) || 0,
    recoverableAmount,
    impairmentAmount,
    supplement: calcImpairmentSupplement(impairmentAmount, row.alreadyProvided),
    overProvision: calcImpairmentOverProvision(impairmentAmount, row.alreadyProvided),
    indicationDesc: row.hasIndication === 'N' ? '' : (row.indicationDesc || ''),
  }
}

/** 有迹象行须索引含 H8-11 */
export function validateH8ImpairmentPrep(rows: H8ImpairmentCalcRow[]): H8ImpPrepValidation {
  const messages: string[] = []
  for (const r of rows) {
    if (!r.assetName && !r.bookValue && r.hasIndication !== 'Y') continue
    if (r.hasIndication === 'Y') {
      if (!r.indicationDesc.trim()) {
        messages.push(`「${r.assetName || r.contractNo || r.rowId}」有减值迹象但未填写描述`)
      }
      if (!/H8-11/i.test(r.indexRef || '')) {
        messages.push(`「${r.assetName || r.contractNo || r.rowId}」有减值迹象，索引号须含 H8-11`)
      }
      if (r.recoverableAmount <= 0 && r.bookValue > 0) {
        messages.push(`「${r.assetName || r.contractNo || r.rowId}」有迹象但可收回金额⑤尚未测算（请完成 H8-11 并回写）`)
      }
    }
    if (r.overProvision > 0.01) {
      messages.push(`「${r.assetName || r.contractNo || r.rowId}」多提待查⑨=${r.overProvision.toFixed(2)}，须查明原因且不得转回`)
    }
  }
  return { ok: messages.length === 0, messages }
}

/** 从 H8-2 明细推导减值测算行（②=入账值−累计折旧期末） */
export function seedRowsFromH82(h2Rows: any[]): H8ImpairmentCalcRow[] {
  const out: H8ImpairmentCalcRow[] = []
  for (const r of h2Rows ?? []) {
    const assetName = String(r?.assetName || '').trim()
    const contractNo = String(r?.contractNo || '').trim()
    if (!assetName && !contractNo) continue
    const cost = Number(r.initialAmount) || 0
    const accDep = Number(r.accDepEnd) || ((Number(r.accDepBegin) || 0) + (Number(r.depCurrentPeriod) || 0))
    const bookValue = calcImpairmentBookValue(cost, accDep)
    // 兼容：若无 initialAmount，回退 netValue（H8-2 当前净值未扣减值）
    const book = bookValue > 0 ? bookValue : (Number(r.netValue) || 0)
    out.push(emptyH8ImpairmentRow({
      assetName: assetName || contractNo,
      contractNo,
      bookValue: book,
      sourceDetailRowId: String(r.rowId ?? ''),
      indexRef: '',
      remark: contractNo ? `自H8-2带入（合同 ${contractNo}）` : '自H8-2带入',
    }))
  }
  return out
}

/** 按资产名/合同号匹配 H8-8 含减值行的 impairmentAmount → ⑦ */
export function mapAlreadyProvidedFromH88(
  rows: H8ImpairmentCalcRow[],
  depRows: any[],
): H8ImpairmentCalcRow[] {
  const byName = new Map<string, number>()
  const byContract = new Map<string, number>()
  for (const d of depRows ?? []) {
    const amt = Number(d.impairmentAmount ?? d.impairment) || 0
    if (!amt) continue
    const name = String(d?.assetName || '').trim()
    const contract = String(d?.contractNo || '').trim()
    if (name) byName.set(name, (byName.get(name) || 0) + amt)
    if (contract) byContract.set(contract, (byContract.get(contract) || 0) + amt)
  }
  return rows.map((r) => {
    const byContractHit = r.contractNo.trim()
      ? byContract.get(r.contractNo.trim())
      : undefined
    const byNameHit = r.assetName.trim()
      ? byName.get(r.assetName.trim())
      : undefined
    const matched = byContractHit ?? byNameHit
    if (matched == null) return r
    return recomputeH8ImpairmentRow({ ...r, alreadyProvided: matched })
  })
}

/** 从 H8-11 各组回填③④⑤（按名称或合同号匹配） */
export function applyH811GroupsToRows(
  rows: H8ImpairmentCalcRow[],
  groups: any[],
): H8ImpairmentCalcRow[] {
  const byName = new Map<string, any>()
  const byContract = new Map<string, any>()
  for (const g of groups ?? []) {
    const name = String(g?.name || g?.assumptions?.assetName || g?.fvDisposal?.assetName || '').trim()
    const contract = String(g?.contractNo || g?.assumptions?.contractNo || '').trim()
    if (name) byName.set(name, g)
    if (contract) byContract.set(contract, g)
  }
  return rows.map((r) => {
    const g = (r.contractNo.trim()
      ? byContract.get(r.contractNo.trim())
      : undefined)
      ?? byName.get(r.assetName.trim())
    if (!g) return r
    const fv = Number(g._fairValueNet)
      || Math.max(
        0,
        (Number(g.fvDisposal?.salesAgreementPrice)
          || Number(g.fvDisposal?.activeMarketPrice)
          || Number(g.fvDisposal?.estimatedPrice)
          || 0)
          - (
            (Number(g.fvDisposal?.legalFees) || 0)
            + (Number(g.fvDisposal?.relatedTaxes) || 0)
            + (Number(g.fvDisposal?.transportCosts) || 0)
            + (Number(g.fvDisposal?.directCosts) || 0)
            + (Number(g.fvDisposal?.otherCosts) || 0)
          ),
      )
    // DCF：若组上已有缓存字段则用；否则留给 sync 时由 recoverable 侧写入
    const dcf = Number(g._pvCashFlows) || Number(g.pvCashFlows) || 0
    const hasIndication = r.hasIndication === 'Y' ? 'Y' : (fv > 0 || dcf > 0 ? 'Y' : r.hasIndication)
    return recomputeH8ImpairmentRow({
      ...r,
      hasIndication,
      fairValueLessDisposal: fv || r.fairValueLessDisposal,
      dcfValue: dcf || r.dcfValue,
      indexRef: /H8-11/i.test(r.indexRef) ? r.indexRef : (r.indexRef ? `${r.indexRef};H8-11` : 'H8-11'),
    })
  })
}

/** 将单组可收回结果写入匹配行（H8-11 syncToH810 用） */
export function upsertH810RowFromRecoverable(
  rows: H8ImpairmentCalcRow[],
  payload: {
    assetName: string
    bookValue?: number
    fairValueNet: number
    pvCashFlows: number
    sourceRowId?: string
  },
): H8ImpairmentCalcRow[] {
  const name = String(payload.assetName || '').trim() || '使用权资产'
  const idx = rows.findIndex((r) =>
    r.assetName.trim() === name
    || (payload.sourceRowId && r.sourceDetailRowId === payload.sourceRowId),
  )
  const patch = {
    assetName: name,
    bookValue: payload.bookValue,
    fairValueLessDisposal: payload.fairValueNet,
    dcfValue: payload.pvCashFlows,
    hasIndication: 'Y' as const,
    indexRef: 'H8-11',
  }
  if (idx >= 0) {
    const next = [...rows]
    next[idx] = recomputeH8ImpairmentRow({
      ...next[idx],
      ...patch,
      bookValue: payload.bookValue && payload.bookValue > 0 ? payload.bookValue : next[idx].bookValue,
      indexRef: /H8-11/i.test(next[idx].indexRef) ? next[idx].indexRef : (next[idx].indexRef ? `${next[idx].indexRef};H8-11` : 'H8-11'),
      hasIndication: 'Y',
    })
    return next
  }
  return [
    ...rows.filter((r) => r.assetName || r.bookValue || r.hasIndication),
    emptyH8ImpairmentRow({
      ...patch,
      bookValue: payload.bookValue || 0,
      sourceDetailRowId: payload.sourceRowId,
      remark: '自H8-11回写',
    }),
  ]
}

export function extractK11RouAmount(list: any[]): { amount: number | null; source: string } {
  const byId = (id: string) => {
    const item = list.find((r) => r.item_id === id)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (raw == null || raw === '') return null
    if (typeof raw === 'string' && raw.trim().startsWith('[')) {
      try {
        const rows = JSON.parse(raw)
        if (!Array.isArray(rows)) return null
        const rou = rows.filter((r: any) => {
          const cat = String(r.assetCategory || r.impairmentItem || r.projectName || '')
          const wp = String(r.sourceWp || '')
          return wp === 'H8' || cat.includes('使用权资产')
        })
        if (!rou.length) return null
        return rou.reduce(
          (s: number, r: any) => s + (Number(r.currentOccurrence ?? r.currentProvision ?? r.sourceAmount) || 0),
          0,
        )
      } catch {
        return null
      }
    }
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  }
  for (const c of K11_H8_AMOUNT_CANDIDATES) {
    const v = byId(c.id)
    if (v != null) return { amount: v, source: c.label }
  }
  return { amount: null, source: '' }
}

function _parseStoredRows(raw: unknown): H8ImpairmentCalcRow[] {
  if (!raw) return []
  let data = raw
  if (typeof raw === 'string') {
    try { data = JSON.parse(raw) } catch { return [] }
  }
  if (!Array.isArray(data)) return []
  return data.map((r: any) => emptyH8ImpairmentRow(r))
}

function _legacyParamsToRows(params: any): H8ImpairmentCalcRow[] {
  if (!params || typeof params !== 'object') return []
  const book = Number(params.bookValue) || 0
  const rec = Number(params.recoverableAmount) || 0
  const fv = Number(params.fairValueNet) || rec
  const pv = Number(params.pvCashFlows) || 0
  if (!book && !rec && !params.assetName) return []
  const sign = params.impairmentSign && params.impairmentSign !== '无'
  return [emptyH8ImpairmentRow({
    assetName: String(params.assetName || params.name || '使用权资产'),
    hasIndication: sign ? 'Y' : 'N',
    indicationDesc: sign ? String(params.impairmentSign) : '',
    bookValue: book,
    fairValueLessDisposal: fv,
    dcfValue: pv,
    alreadyProvided: Number(params.alreadyProvided) || 0,
    indexRef: sign ? 'H8-11' : '',
    remark: '自旧版 H8-10-params 迁移',
  })]
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Impairment(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  const rows = ref<H8ImpairmentCalcRow[]>([emptyH8ImpairmentRow()])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const k11Reconcile = ref<H8K11ReconcileResult>({
    h10Supplement: 0,
    k11Amount: null,
    diff: null,
    isMatch: true,
    source: '',
    message: '尚未核对 K11',
  })

  function _getRaw(key: string): any {
    const item = options.allResponses.value.get(key)
    if (!item) return null
    return item.remark ?? item.conclusion ?? item
  }

  function hydrate(): void {
    const stored = _parseStoredRows(_getRaw(H810_ROWS_KEY))
    if (stored.length) {
      rows.value = stored
    } else {
      let legacy: any = _getRaw(H810_PARAMS_KEY)
      if (typeof legacy === 'string') {
        try { legacy = JSON.parse(legacy) } catch { legacy = null }
      }
      const migrated = _legacyParamsToRows(legacy)
      rows.value = migrated.length ? migrated : [emptyH8ImpairmentRow()]
    }
    const n = _getRaw(H810_AUDIT_NOTE_KEY)
    if (typeof n === 'string') auditNote.value = n
    const c = _getRaw(H810_AUDIT_CONCLUSION_KEY)
    if (typeof c === 'string') auditConclusion.value = c
  }

  hydrate()

  function persist(): void {
    if (options.isReadonly.value) return
    const supp = supplementTotal.value
    options.onSave?.(H810_ROWS_KEY, JSON.stringify(rows.value))
    options.onSave?.(H810_SUPPLEMENT_TOTAL_KEY, supp)
    // 兼容 H8-11 仍读 H8-10-params（汇总层）
    const first = rows.value.find((r) => r.hasIndication === 'Y') || rows.value[0]
    options.onSave?.(H810_PARAMS_KEY, JSON.stringify({
      assetName: rows.value.length > 1
        ? `多合同合计(${rows.value.filter((r) => r.assetName).length})`
        : (first?.assetName || ''),
      bookValue: bookValueTotal.value,
      recoverableAmount: recoverableTotal.value,
      fairValueNet: calcSubtotal(rows.value.map((r) => r.fairValueLessDisposal)),
      pvCashFlows: calcSubtotal(rows.value.map((r) => r.dcfValue)),
      alreadyProvided: alreadyProvidedTotal.value,
      impairmentSign: rows.value.some((r) => r.hasIndication === 'Y') ? '其他' : '无',
    }))
    _publishImpairmentToK11(supp)
  }

  function _publishImpairmentToK11(supplement: number): void {
    try {
      if (typeof window === 'undefined') return
      window.dispatchEvent(new CustomEvent('impairment:calculated', {
        detail: {
          wpCode: 'H8',
          wp_code: 'H8',
          sheetCode: 'H8-10',
          sheet: '减值测算表H8-10',
          totalRequiredProvision: supplement,
          amount: supplement,
          label: '本期补提⑧',
          impairmentAmount: requiredTotal.value,
        },
      }))
    } catch { /* silent */ }
  }

  const bookValueTotal = computed(() => calcSubtotal(rows.value.map((r) => r.bookValue)))
  const recoverableTotal = computed(() => calcSubtotal(rows.value.map((r) => r.recoverableAmount)))
  const requiredTotal = computed(() => calcSubtotal(rows.value.map((r) => r.impairmentAmount)))
  const alreadyProvidedTotal = computed(() => calcSubtotal(rows.value.map((r) => r.alreadyProvided)))
  const supplementTotal = computed(() => calcSubtotal(rows.value.map((r) => r.supplement)))
  const overProvisionTotal = computed(() => calcSubtotal(rows.value.map((r) => r.overProvision)))
  const prepValidation: ComputedRef<H8ImpPrepValidation> = computed(() =>
    validateH8ImpairmentPrep(rows.value),
  )

  function addRow(assetName?: string): void {
    if (options.isReadonly.value) return
    rows.value.push(emptyH8ImpairmentRow({ assetName: assetName || '' }))
    persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    if (!rows.value.length) rows.value.push(emptyH8ImpairmentRow())
    persist()
  }

  function updateRow(rowId: string, patch: Partial<H8ImpairmentCalcRow>): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value[idx] = recomputeH8ImpairmentRow({ ...rows.value[idx], ...patch })
    persist()
  }

  function importFromH82(): { ok: boolean; message: string; count: number } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式', count: 0 }
    const h2 = safeParseRows(_getRaw(H82_ROWS_KEY))
    const seeded = seedRowsFromH82(h2)
    if (!seeded.length) return { ok: false, message: 'H8-2 暂无明细行可带入', count: 0 }
    // 保留已填迹象/可收回/已计提（按 sourceDetailRowId 或名称合并）
    const prevBySrc = new Map(rows.value.filter((r) => r.sourceDetailRowId).map((r) => [r.sourceDetailRowId!, r]))
    const prevByName = new Map(rows.value.filter((r) => r.assetName).map((r) => [r.assetName.trim(), r]))
    rows.value = seeded.map((s) => {
      const prev = (s.sourceDetailRowId && prevBySrc.get(s.sourceDetailRowId))
        || prevByName.get(s.assetName.trim())
      if (!prev) return s
      return recomputeH8ImpairmentRow({
        ...s,
        hasIndication: prev.hasIndication || s.hasIndication,
        indicationDesc: prev.indicationDesc || s.indicationDesc,
        fairValueLessDisposal: prev.fairValueLessDisposal || s.fairValueLessDisposal,
        dcfValue: prev.dcfValue || s.dcfValue,
        alreadyProvided: prev.alreadyProvided || s.alreadyProvided,
        indexRef: prev.indexRef || s.indexRef,
        remark: prev.remark || s.remark,
      })
    })
    // 尝试带入⑦
    const branch = String(_getRaw(H88_BRANCH_KEY) || '')
    const depRows = safeParseRows(_getRaw(H88_DEP_ROWS_KEY))
    if (branch.includes('含减值') || depRows.some((d: any) => Number(d.impairmentAmount) > 0)) {
      rows.value = mapAlreadyProvidedFromH88(rows.value, depRows)
    }
    persist()
    return { ok: true, message: `已从 H8-2 带入 ${seeded.length} 行账面价值②`, count: seeded.length }
  }

  function pullAlreadyProvidedFromH88(): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式' }
    const depRows = safeParseRows(_getRaw(H88_DEP_ROWS_KEY))
    if (!depRows.length) return { ok: false, message: 'H8-8 暂无折旧行' }
    rows.value = mapAlreadyProvidedFromH88(rows.value, depRows)
    persist()
    return { ok: true, message: '已按合同号/资产名称匹配写入⑦已计提（来自 H8-8）' }
  }

  /**
   * 本期有补提时，将 H8-8 切换为「含减值」分支并提示重算折旧。
   * 不改动折旧行数值，仅写分支键。
   */
  function switchH88ToWithImpairment(): { ok: boolean; message: string } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式' }
    if (supplementTotal.value < 0.01) {
      return { ok: false, message: '本期⑧应补提为 0，无需切换含减值分支' }
    }
    options.onSave?.(H88_BRANCH_KEY, '含减值')
    return {
      ok: true,
      message: `已切换 H8-8 为「含减值」；请打开 H8-8 将⑦/补提 ${supplementTotal.value.toFixed(2)} 写入各行后重算折旧`,
    }
  }

  function pullRecoverableFromH811(): { ok: boolean; message: string; count: number } {
    if (options.isReadonly.value) return { ok: false, message: '只读模式', count: 0 }
    let groups: any = _getRaw(H811_GROUPS_KEY)
    if (typeof groups === 'string') {
      try { groups = JSON.parse(groups) } catch { groups = [] }
    }
    if (!Array.isArray(groups) || !groups.length) {
      return { ok: false, message: 'H8-11 暂无资产组可回填', count: 0 }
    }
    const before = JSON.stringify(rows.value)
    rows.value = applyH811GroupsToRows(rows.value, groups)
    persist()
    const changed = before !== JSON.stringify(rows.value)
    return {
      ok: changed,
      message: changed ? `已按名称匹配回填 H8-11 可收回相关字段` : '未匹配到同名资产组',
      count: changed ? rows.value.filter((r) => /H8-11/i.test(r.indexRef)).length : 0,
    }
  }

  function applyRecoverableWriteback(payload: {
    assetName: string
    bookValue?: number
    fairValueNet: number
    pvCashFlows: number
    sourceRowId?: string
  }): void {
    if (options.isReadonly.value) return
    rows.value = upsertH810RowFromRecoverable(rows.value, payload)
    persist()
  }

  function saveAuditNote(text: string): void {
    if (options.isReadonly.value) return
    auditNote.value = text
    options.onSave?.(H810_AUDIT_NOTE_KEY, text)
  }

  function saveAuditConclusion(text: string): void {
    if (options.isReadonly.value) return
    auditConclusion.value = text
    options.onSave?.(H810_AUDIT_CONCLUSION_KEY, text)
  }

  function buildConclusionDraft(): string {
    const v = prepValidation.value
    const signOk = rows.value.every((r) => r.hasIndication !== 'Y' || r.indicationDesc)
    return [
      `经审计：（1）减值迹象识别${signOk ? '□充分' : '□需补充'}；`,
      `（2）可收回金额测算${rows.value.some((r) => r.hasIndication === 'Y' && r.recoverableAmount <= 0) ? '□需调整' : '□合理'}；`,
      `（3）本期应补提合计（⑧）${supplementTotal.value.toFixed(2)}元，已建议调整□是 / □否 / □不适用；`,
      `（4）多提待查（⑨）${overProvisionTotal.value.toFixed(2)}元，原因及处理____________________；`,
      `（5）使用权资产减值准备在重大方面${supplementTotal.value < 0.01 && overProvisionTotal.value < 0.01 && v.ok ? '□公允反映' : '□存在错报风险'}。`,
    ].join('')
  }

  async function reconcileWithK11(projectId: string): Promise<H8K11ReconcileResult> {
    const h10Supplement = supplementTotal.value
    const empty: H8K11ReconcileResult = {
      h10Supplement,
      k11Amount: null,
      diff: null,
      isMatch: true,
      source: '',
      message: 'K11 未取到使用权资产减值金额',
    }
    if (!projectId) {
      k11Reconcile.value = { ...empty, message: '缺少 projectId，无法核对 K11' }
      return k11Reconcile.value
    }
    try {
      const { api } = await import('@/services/apiProxy')
      const { data: wpList } = await api.get('/api/workpapers', {
        params: { project_id: projectId, wp_code: 'K11' },
      })
      const k11 = Array.isArray(wpList) ? wpList.find((w: any) => w.wp_code === 'K11') : null
      if (!k11?.id) {
        k11Reconcile.value = { ...empty, message: '项目中未找到 K11 底稿' }
        return k11Reconcile.value
      }
      const { data: list } = await api.get(`/api/workpapers/${k11.id}/checklist-responses`)
      const { amount: k11Amount, source } = extractK11RouAmount(Array.isArray(list) ? list : [])
      if (k11Amount == null) {
        k11Reconcile.value = { ...empty, message: 'K11 未取到使用权资产减值金额', source }
        return k11Reconcile.value
      }
      const diff = Math.round((h10Supplement - k11Amount) * 100) / 100
      const isMatch = Math.abs(diff) < 0.01
      k11Reconcile.value = {
        h10Supplement,
        k11Amount,
        diff,
        isMatch,
        source,
        message: isMatch
          ? `K11 勾稽通过：⑧本期补提 ${h10Supplement.toFixed(2)} = K11 ${k11Amount.toFixed(2)}（${source}）`
          : `K11 勾稽差异：⑧ ${h10Supplement.toFixed(2)} − K11 ${k11Amount.toFixed(2)} = ${diff.toFixed(2)}（${source}）`,
      }
      return k11Reconcile.value
    } catch (e) {
      k11Reconcile.value = {
        ...empty,
        message: `拉取 K11 失败：${e instanceof Error ? e.message : String(e)}`,
      }
      return k11Reconcile.value
    }
  }

  /** 客户端 xlsx 导入导出（对齐 H8-8 模式，无需后端 cycle IE） */
  async function exportData(kind: 'template' | 'data'): Promise<void> {
    const headers = [
      '合同号', '资产名称', '有减值迹象', '迹象说明',
      '账面价值②', '公允减处置③', 'DCF现值④', '可收回金额⑤',
      '应计提⑥', '已计提⑦', '本期补提⑧', '多提待查⑨',
      '索引', '备注',
    ]
    const dataRows = kind === 'template'
      ? []
      : rows.value
        .filter((r) => r.assetName || r.contractNo || r.bookValue)
        .map((r) => ({
          '合同号': r.contractNo || '',
          '资产名称': r.assetName || '',
          '有减值迹象': r.hasIndication || '',
          '迹象说明': r.indicationDesc || '',
          '账面价值②': r.bookValue || 0,
          '公允减处置③': r.fairValueLessDisposal || 0,
          'DCF现值④': r.dcfValue || 0,
          '可收回金额⑤': r.recoverableAmount || 0,
          '应计提⑥': r.impairmentAmount || 0,
          '已计提⑦': r.alreadyProvided || 0,
          '本期补提⑧': r.supplement || 0,
          '多提待查⑨': r.overProvision || 0,
          '索引': r.indexRef || '',
          '备注': r.remark || '',
        }))
    // 走 useExcelIO 单一入口（B3 批）。模板态 = 只有表头行；数据态 = 表头 + 按 headers
    // 顺序取值 —— json_to_sheet 与 aoa_to_sheet 对缺失字段同样跳过该单元格，故逐格等价。
    await exportMultiSheetData({
      sheets: [
        {
          sheetName: 'H8-10减值测算',
          rows: kind === 'template'
            ? [headers]
            : [headers, ...dataRows.map((r) => headers.map((h) => (r as any)[h]))],
        },
      ],
      fileName: `H8-10_减值测算_${kind === 'template' ? '模板' : '数据'}.xlsx`,
      applyStyles: false,
      successMessage: false,
    })
  }

  async function importData(file: File, replace = true): Promise<{ imported: number }> {
    if (options.isReadonly.value) return { imported: 0 }
    // 走 useExcelIO 低层入口（B3 批）。原实现 = read(buffer,{type:'array',cellDates:false})
    // + sheet_to_json(sheet,{defval:''}) + 取第一个 sheet。
    // 🔴 cellDates 与 defval 必须显式透传：前者决定日期是 Date 还是序列号，
    // 后者决定空单元格填 '' 还是被跳过（下游用 ?? / || 取值时两者行为不同）。
    const { rows: rowsRaw } = await readSheetObjects<Record<string, any>>(file, {
      cellDates: false,
      defval: '',
    })
    const mapped = rowsRaw
      .filter((r) => String(r['资产名称'] || r['合同号'] || '').trim())
      .map((r) => {
        const indication = String(r['有减值迹象'] || '').trim().toUpperCase()
        return recomputeH8ImpairmentRow(emptyH8ImpairmentRow({
          contractNo: String(r['合同号'] || ''),
          assetName: String(r['资产名称'] || ''),
          hasIndication: indication === 'Y' || indication === '是' ? 'Y' : indication === 'N' || indication === '否' ? 'N' : '',
          indicationDesc: String(r['迹象说明'] || ''),
          bookValue: Number(r['账面价值②'] || r['账面价值'] || 0) || 0,
          fairValueLessDisposal: Number(r['公允减处置③'] || r['公允减处置'] || 0) || 0,
          dcfValue: Number(r['DCF现值④'] || r['DCF现值'] || 0) || 0,
          alreadyProvided: Number(r['已计提⑦'] || r['已计提'] || 0) || 0,
          indexRef: String(r['索引'] || ''),
          remark: String(r['备注'] || ''),
        }))
      })
    rows.value = replace ? (mapped.length ? mapped : [emptyH8ImpairmentRow()]) : [...rows.value, ...mapped]
    persist()
    return { imported: mapped.length }
  }

  return {
    rows,
    auditNote,
    auditConclusion,
    k11Reconcile,
    bookValueTotal,
    recoverableTotal,
    requiredTotal,
    alreadyProvidedTotal,
    supplementTotal,
    overProvisionTotal,
    prepValidation,
    hydrate,
    persist,
    addRow,
    removeRow,
    updateRow,
    importFromH82,
    pullAlreadyProvidedFromH88,
    pullRecoverableFromH811,
    switchH88ToWithImpairment,
    applyRecoverableWriteback,
    saveAuditNote,
    saveAuditConclusion,
    buildConclusionDraft,
    reconcileWithK11,
    exportData,
    importData,
  }
}

export default useH8Impairment
