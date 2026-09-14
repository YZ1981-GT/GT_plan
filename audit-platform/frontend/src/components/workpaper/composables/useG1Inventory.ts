/**
 * useG1Inventory — G1-4 交易性金融资产期末结存表
 *
 * 对齐 Excel「结存表 G1-4」：①账面 vs ②库存 vs ③对账单 vs ④函证 → ⑤差异
 * 差异公式（默认）：⑤ = ① − ② − (③ 或 ④)，外部证据优先函证，否则对账单；
 * 亦可按行指定证据源（对账单/函证/仅监盘）。
 *
 * 联动：从 G1-2 带入账面；从 G1-11 回填监盘数量；差异行可推送 G1-3 调整草稿。
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { TradingDetailRow } from './useG1Detail'
import type { G1SecuritiesCountRow } from './useG1SecuritiesCount'
import { createEmptyG1AdjustmentRow, type G1AdjustmentRow } from './useG1Adjustment'

/** 外部证据源：对账单 / 函证 / 仅监盘（②） */
export type G1InventoryEvidenceSource = 'auto' | 'statement' | 'confirmation' | 'stocktake'

export interface G1InventoryRow {
  id: string
  seq: number
  securityName: string
  cashAccountNo: string
  accountName: string
  // ① 账面结存
  bookQuantity: number
  bookFaceValue: number
  couponRate: string
  maturityDate: string
  bookTotal: number
  // ② 报表日库存
  stockQuantity: number
  stockFaceValue: number
  stockTotal: number
  // ③ 对账单
  stmtQuantity: number
  stmtFaceValue: number
  stmtTotal: number
  // ④ 函证
  confQuantity: number
  confFaceValue: number
  confTotal: number
  /** 本行证据源；auto = 函证优先否则对账单，再与监盘合计 */
  evidenceSource: G1InventoryEvidenceSource
  // ⑤ 差异（公式）
  diffQuantity: number
  diffFaceValue: number
  diffTotal: number
  remark: string
}

const DATA_KEY = 'G1-4-rows'
const CONCLUSION_KEY = 'G1-4-conclusion'
const DETAIL_KEY = 'G1-2-rows'
const COUNT_KEY = 'G1-11-rows'
const ADJ_KEY = 'G1-3-rows'
const RECON_KEY = 'G1-12-rows'
const DIFF_TOLERANCE = 0.005

function generateId(): string {
  return `g14-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function createEmptyG1InventoryRow(seq = 1): G1InventoryRow {
  return {
    id: generateId(),
    seq,
    securityName: '',
    cashAccountNo: '',
    accountName: '',
    bookQuantity: 0,
    bookFaceValue: 0,
    couponRate: '',
    maturityDate: '',
    bookTotal: 0,
    stockQuantity: 0,
    stockFaceValue: 0,
    stockTotal: 0,
    stmtQuantity: 0,
    stmtFaceValue: 0,
    stmtTotal: 0,
    confQuantity: 0,
    confFaceValue: 0,
    confTotal: 0,
    evidenceSource: 'auto',
    diffQuantity: 0,
    diffFaceValue: 0,
    diffTotal: 0,
    remark: '',
  }
}

function calcLineTotal(qty: number, face: number, explicit?: number): number {
  if (explicit != null && Number.isFinite(explicit) && explicit !== 0) return explicit
  return parseNum(qty) * parseNum(face)
}

/** 选取外部证据（③或④）；auto：函证有数用函证，否则对账单 */
export function pickExternalEvidence(row: G1InventoryRow): {
  quantity: number
  faceValue: number
  total: number
  label: string
} {
  const src = row.evidenceSource || 'auto'
  if (src === 'stocktake') {
    return { quantity: 0, faceValue: 0, total: 0, label: '仅监盘' }
  }
  if (src === 'confirmation') {
    return {
      quantity: parseNum(row.confQuantity),
      faceValue: parseNum(row.confFaceValue),
      total: calcLineTotal(row.confQuantity, row.confFaceValue, row.confTotal),
      label: '函证',
    }
  }
  if (src === 'statement') {
    return {
      quantity: parseNum(row.stmtQuantity),
      faceValue: parseNum(row.stmtFaceValue),
      total: calcLineTotal(row.stmtQuantity, row.stmtFaceValue, row.stmtTotal),
      label: '对账单',
    }
  }
  // auto
  const confTotal = calcLineTotal(row.confQuantity, row.confFaceValue, row.confTotal)
  const confQty = parseNum(row.confQuantity)
  if (confQty !== 0 || confTotal !== 0) {
    return {
      quantity: confQty,
      faceValue: parseNum(row.confFaceValue),
      total: confTotal,
      label: '函证',
    }
  }
  return {
    quantity: parseNum(row.stmtQuantity),
    faceValue: parseNum(row.stmtFaceValue),
    total: calcLineTotal(row.stmtQuantity, row.stmtFaceValue, row.stmtTotal),
    label: '对账单',
  }
}

/**
 * ⑤ = ① − ② − (③或④)
 * stocktake 模式：⑤ = ① − ②
 */
export function calcInventoryDiff(row: G1InventoryRow): {
  diffQuantity: number
  diffFaceValue: number
  diffTotal: number
} {
  const bookQty = parseNum(row.bookQuantity)
  const bookTotal = calcLineTotal(row.bookQuantity, row.bookFaceValue, row.bookTotal)

  const stockQty = parseNum(row.stockQuantity)
  const stockTotal = calcLineTotal(row.stockQuantity, row.stockFaceValue, row.stockTotal)

  const ext = pickExternalEvidence(row)

  return {
    diffQuantity: bookQty - stockQty - ext.quantity,
    // 单价列不参与勾稽（面值/单价为说明性字段），差异以数量/总计为准
    diffFaceValue: 0,
    diffTotal: bookTotal - stockTotal - ext.total,
  }
}

export function enrichG1InventoryRow(row: G1InventoryRow): G1InventoryRow {
  const bookTotal = calcLineTotal(row.bookQuantity, row.bookFaceValue, undefined)
  const stockTotal = calcLineTotal(row.stockQuantity, row.stockFaceValue, undefined)
  const stmtTotal = calcLineTotal(row.stmtQuantity, row.stmtFaceValue, undefined)
  const confTotal = calcLineTotal(row.confQuantity, row.confFaceValue, undefined)
  const base = {
    ...row,
    bookTotal,
    stockTotal,
    stmtTotal,
    confTotal,
  }
  const diff = calcInventoryDiff(base)
  return { ...base, ...diff }
}

export function isDiffAbnormal(row: G1InventoryRow): boolean {
  return Math.abs(parseNum(row.diffTotal)) > DIFF_TOLERANCE
    || Math.abs(parseNum(row.diffQuantity)) > DIFF_TOLERANCE
}

/** 旧版滚动结存 → 新版账面列迁移 */
function migrateLegacyRow(raw: Record<string, unknown>, seq: number): G1InventoryRow {
  const base = createEmptyG1InventoryRow(seq)
  if (raw.bookQuantity != null || raw.stockQuantity != null || raw.stmtQuantity != null) {
    return enrichG1InventoryRow({
      ...base,
      id: String(raw.id || base.id),
      seq: Number(raw.seq) || seq,
      securityName: String(raw.securityName || ''),
      cashAccountNo: String(raw.cashAccountNo || ''),
      accountName: String(raw.accountName || ''),
      bookQuantity: parseNum(raw.bookQuantity),
      bookFaceValue: parseNum(raw.bookFaceValue),
      couponRate: String(raw.couponRate || ''),
      maturityDate: String(raw.maturityDate || ''),
      bookTotal: parseNum(raw.bookTotal),
      stockQuantity: parseNum(raw.stockQuantity),
      stockFaceValue: parseNum(raw.stockFaceValue),
      stockTotal: parseNum(raw.stockTotal),
      stmtQuantity: parseNum(raw.stmtQuantity),
      stmtFaceValue: parseNum(raw.stmtFaceValue),
      stmtTotal: parseNum(raw.stmtTotal),
      confQuantity: parseNum(raw.confQuantity),
      confFaceValue: parseNum(raw.confFaceValue),
      confTotal: parseNum(raw.confTotal),
      evidenceSource: (raw.evidenceSource as G1InventoryEvidenceSource) || 'auto',
      remark: String(raw.remark || ''),
    })
  }
  // legacy roll-forward
  const closingQty = parseNum(raw.closingQuantity)
  const closingCost = parseNum(raw.closingCost)
  const closingFv = parseNum(raw.closingFairValue)
  const total = closingFv || closingCost
  const face = closingQty > 0 ? total / closingQty : 0
  return enrichG1InventoryRow({
    ...base,
    id: String(raw.id || base.id),
    seq: Number(raw.seq) || seq,
    securityName: String(raw.securityName || ''),
    accountName: String(raw.securityType || raw.accountName || ''),
    bookQuantity: closingQty,
    bookFaceValue: face,
    bookTotal: total,
    remark: closingFv ? `自旧版结存迁移；未实现损益曾为 ${parseNum(raw.unrealizedGain)}` : '自旧版结存迁移',
  })
}

function loadRows(map: Map<string, ChecklistResponse>): G1InventoryRow[] {
  const item = map.get(DATA_KEY)
  const raw = item?.conclusion || item?.remark
  if (!raw) return [enrichG1InventoryRow(createEmptyG1InventoryRow(1))]
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>[]
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return [enrichG1InventoryRow(createEmptyG1InventoryRow(1))]
    }
    return parsed.map((p, i) => migrateLegacyRow(p, i + 1))
  } catch {
    return [enrichG1InventoryRow(createEmptyG1InventoryRow(1))]
  }
}

function loadDetailRows(map: Map<string, ChecklistResponse>): TradingDetailRow[] {
  const raw = map.get(DETAIL_KEY)?.conclusion
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function loadCountRows(map: Map<string, ChecklistResponse>): G1SecuritiesCountRow[] {
  const raw = map.get(COUNT_KEY)?.conclusion
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function loadReconRows(map: Map<string, ChecklistResponse>): Array<{
  securityName?: string
  bookQuantity?: number
  bookTotal?: number
  reportQuantity?: number
}> {
  const raw = map.get(RECON_KEY)?.conclusion || map.get(RECON_KEY)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function matchKey(name: string, code?: string): string {
  const c = String(code || '').trim()
  if (c) return `c:${c}`
  return `n:${String(name || '').trim()}`
}

/** G1-4 与 G1-12 交叉校验差异项 */
export interface G1InventoryReconMismatch {
  securityName: string
  /** G1-4 ①账面数量 */
  inventoryBookQty: number
  /** G1-12 账面数量 */
  reconBookQty: number
  /** G1-4 ①账面总计 */
  inventoryBookTotal: number
  /** G1-12 账面总计 */
  reconBookTotal: number
  /** G1-12 报表日倒轧数量（对照存在性） */
  reconReportQty: number
}

/**
 * 交叉核对 G1-4 账面结存 vs G1-12 账面/报表日倒轧（按证券名称）。
 * 用于提示两表「证据维 vs 时间维」是否一致。
 */
export function crossCheckInventoryVsReconciliation(
  inventoryRows: G1InventoryRow[],
  reconRows: Array<{
    securityName?: string
    bookQuantity?: number
    bookTotal?: number
    reportQuantity?: number
  }>,
  tolerance = DIFF_TOLERANCE,
): G1InventoryReconMismatch[] {
  const byName = new Map<string, {
    bookQuantity: number
    bookTotal: number
    reportQuantity: number
  }>()
  for (const r of reconRows || []) {
    const name = String(r.securityName || '').trim()
    if (!name) continue
    byName.set(name, {
      bookQuantity: parseNum(r.bookQuantity),
      bookTotal: parseNum(r.bookTotal),
      reportQuantity: parseNum(r.reportQuantity),
    })
  }
  const out: G1InventoryReconMismatch[] = []
  for (const inv of inventoryRows || []) {
    const name = String(inv.securityName || '').trim()
    if (!name) continue
    const hit = byName.get(name)
    if (!hit) continue
    const invQty = parseNum(inv.bookQuantity)
    const invTotal = parseNum(inv.bookTotal)
    const qtyDiff = Math.abs(invQty - hit.bookQuantity) > tolerance
    const totalDiff = Math.abs(invTotal - hit.bookTotal) > tolerance
    if (qtyDiff || totalDiff) {
      out.push({
        securityName: name,
        inventoryBookQty: invQty,
        reconBookQty: hit.bookQuantity,
        inventoryBookTotal: invTotal,
        reconBookTotal: hit.bookTotal,
        reconReportQty: hit.reportQuantity,
      })
    }
  }
  return out
}

/** 函证模块证券行（G0-3S / G0-1）→ G1-4 ④列输入 */
export interface G1ConfirmationSecuritiesInput {
  security_name?: string
  securityName?: string
  security_code?: string
  securityCode?: string
  entity_name?: string
  confirmed_qty?: number
  confirmedQty?: number
  confirmed_unit_fv?: number
  confirmedUnitFv?: number
  confirmed_market_value?: number
  confirmedMarketValue?: number
  amount?: number
}

/**
 * 将函证证券行回填到结存表④列。
 * 匹配顺序：证券代码精确 → 名称精确 → 名称模糊（包含/去空白后相等，阈值≥0.8）。
 */
export function normalizeConfirmName(s: string): string {
  return String(s || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[（）()【】\[\]]/g, '')
}

/** 0~1，名称相似度 */
export function fuzzyConfirmNameScore(a: string, b: string): number {
  const na = normalizeConfirmName(a)
  const nb = normalizeConfirmName(b)
  if (!na || !nb) return 0
  if (na === nb) return 1
  if (na.includes(nb) || nb.includes(na)) {
    const shorter = Math.min(na.length, nb.length)
    const longer = Math.max(na.length, nb.length)
    return 0.75 + 0.2 * (shorter / longer)
  }
  let common = 0
  const len = Math.min(na.length, nb.length)
  for (let i = 0; i < len; i++) {
    if (na[i] === nb[i]) common++
    else break
  }
  return common / Math.max(na.length, nb.length)
}

export interface G1ConfirmApplyResult {
  rows: G1InventoryRow[]
  matched: number
  fuzzyMatched: number
  unmatchedConfirm: Array<{ label: string; raw: G1ConfirmationSecuritiesInput }>
}

function confirmRowLabel(c: G1ConfirmationSecuritiesInput): string {
  const name = String(c.security_name || c.securityName || c.entity_name || '').trim()
  const code = String(c.security_code || c.securityCode || '').trim()
  if (name && code) return `${name}（${code}）`
  return name || code || '（无名证券）'
}

function patchInventoryFromConfirm(
  r: G1InventoryRow,
  hit: G1ConfirmationSecuritiesInput,
  viaFuzzy: boolean,
): G1InventoryRow {
  let qty = parseNum(hit.confirmed_qty ?? hit.confirmedQty)
  let unitFv = parseNum(hit.confirmed_unit_fv ?? hit.confirmedUnitFv)
  const market = parseNum(hit.confirmed_market_value ?? hit.confirmedMarketValue ?? hit.amount)

  if (qty === 0 && unitFv === 0 && market === 0) return r

  if (qty === 0 && market > 0) {
    const bookQty = parseNum(r.bookQuantity)
    qty = bookQty > 0 ? bookQty : 1
    unitFv = market / qty
  } else if (qty > 0 && unitFv === 0 && market > 0) {
    unitFv = market / qty
  }

  const face = unitFv || r.bookFaceValue || 0
  const remarkBase = viaFuzzy ? '自函证模块模糊匹配回填' : '自函证模块回填'
  return enrichG1InventoryRow({
    ...r,
    confQuantity: qty,
    confFaceValue: face,
    evidenceSource: r.evidenceSource === 'auto' || !r.evidenceSource
      ? 'confirmation'
      : r.evidenceSource,
    remark: r.remark || remarkBase,
  })
}

export function applyConfirmationSecuritiesRows(
  inventoryRows: G1InventoryRow[],
  confirmRows: G1ConfirmationSecuritiesInput[],
): G1ConfirmApplyResult {
  if (!confirmRows?.length) {
    return { rows: inventoryRows, matched: 0, fuzzyMatched: 0, unmatchedConfirm: [] }
  }

  const next = inventoryRows.map((r) => ({ ...r }))
  const usedInv = new Set<string>()
  let matched = 0
  let fuzzyMatched = 0
  const unmatchedConfirm: G1ConfirmApplyResult['unmatchedConfirm'] = []

  for (const c of confirmRows) {
    const cName = String(c.security_name || c.securityName || c.entity_name || '').trim()
    const cCode = String(c.security_code || c.securityCode || '').trim()
    const qty = parseNum(c.confirmed_qty ?? c.confirmedQty)
    const unitFv = parseNum(c.confirmed_unit_fv ?? c.confirmedUnitFv)
    const market = parseNum(c.confirmed_market_value ?? c.confirmedMarketValue ?? c.amount)
    if (!cName && !cCode && qty === 0 && unitFv === 0 && market === 0) continue

    let idx = -1
    let viaFuzzy = false

    if (cCode) {
      idx = next.findIndex(
        (r) => !usedInv.has(r.id) && matchKey('', r.cashAccountNo) === matchKey('', cCode),
      )
    }
    if (idx < 0 && cName) {
      idx = next.findIndex((r) => {
        if (usedInv.has(r.id)) return false
        return (
          matchKey(r.securityName) === matchKey(cName)
          || matchKey(r.accountName) === matchKey(cName)
        )
      })
    }
    if (idx < 0 && cName) {
      let best = -1
      let bestScore = 0
      for (let i = 0; i < next.length; i++) {
        if (usedInv.has(next[i].id)) continue
        const s1 = fuzzyConfirmNameScore(cName, next[i].securityName)
        const s2 = fuzzyConfirmNameScore(cName, next[i].accountName)
        const s = Math.max(s1, s2)
        if (s > bestScore) {
          bestScore = s
          best = i
        }
      }
      if (best >= 0 && bestScore >= 0.8) {
        idx = best
        viaFuzzy = true
      }
    }

    if (idx < 0) {
      unmatchedConfirm.push({ label: confirmRowLabel(c), raw: c })
      continue
    }

    const patched = patchInventoryFromConfirm(next[idx], c, viaFuzzy)
    if (patched === next[idx] && parseNum(patched.confQuantity) === parseNum(next[idx].confQuantity)) {
      // 无有效数量/金额可写
      unmatchedConfirm.push({ label: confirmRowLabel(c), raw: c })
      continue
    }
    next[idx] = patched
    usedInv.add(next[idx].id)
    matched += 1
    if (viaFuzzy) fuzzyMatched += 1
  }

  return { rows: next, matched, fuzzyMatched, unmatchedConfirm }
}

const SUM_FIELDS = [
  'bookQuantity',
  'bookTotal',
  'stockQuantity',
  'stockTotal',
  'stmtQuantity',
  'stmtTotal',
  'confQuantity',
  'confTotal',
  'diffQuantity',
  'diffTotal',
] as const

export type G1InventoryTotals = Record<(typeof SUM_FIELDS)[number], number>

function sumRows(list: G1InventoryRow[]): G1InventoryTotals {
  const out = {} as G1InventoryTotals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f])))
  }
  return out
}

export function useG1Inventory(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1InventoryRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion
      ?? opts.allResponses.value.get(DATA_KEY)?.remark,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  const grandTotal = computed(() => sumRows(rows.value))
  const diffCount = computed(() => rows.value.filter(isDiffAbnormal).length)
  const bookGrandTotal = computed(() => grandTotal.value.bookTotal)
  const diffGrandTotal = computed(() => grandTotal.value.diffTotal)

  /** 与 G1-12 账面交叉校验结果（同名证券数量/金额不一致） */
  const reconCrossMismatches = computed(() =>
    crossCheckInventoryVsReconciliation(rows.value, loadReconRows(opts.allResponses.value)),
  )

  /** 最近一次函证回填结果（含未匹配清单） */
  const lastConfirmSync = ref<G1ConfirmApplyResult | null>(null)

  function persistAll() {
    if (opts.isReadonly.value) return
    const json = JSON.stringify(rows.value)
    opts.debouncedSave(DATA_KEY, { conclusion: json, remark: json })
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1InventoryRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichG1InventoryRow({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入证券名称', '新增结存行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '证券名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [
        ...rows.value,
        enrichG1InventoryRow({
          ...createEmptyG1InventoryRow(seq),
          securityName: value,
        }),
      ]
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  /** 从 G1-2 明细带入①账面结存（按证券代码/名称合并） */
  function syncFromDetail(): number {
    if (opts.isReadonly.value) return 0
    const details = loadDetailRows(opts.allResponses.value)
    if (!details.length) return 0

    const byKey = new Map<string, G1InventoryRow>()
    for (const r of rows.value) {
      if (!r.securityName && !r.bookQuantity) continue
      byKey.set(matchKey(r.securityName, r.cashAccountNo), r)
    }

    let n = 0
    const next: G1InventoryRow[] = []
    for (const d of details) {
      if (!d.securityName && !d.securityCode) continue
      const key = matchKey(d.securityName, d.securityCode)
      const qty = parseNum(d.closingQuantity)
      const cost = parseNum(d.auditedClosingCost ?? d.closingCost)
      const fv = parseNum(d.auditedClosingFvTotal ?? d.closingFairValue)
      const total = fv || cost
      const face = qty > 0 ? total / qty : parseNum(d.unitFairValue)
      const existing = byKey.get(key)
      const row = enrichG1InventoryRow({
        ...(existing || createEmptyG1InventoryRow(next.length + 1)),
        securityName: d.securityName || existing?.securityName || '',
        cashAccountNo: d.securityCode || existing?.cashAccountNo || '',
        accountName: existing?.accountName || d.securityName || '',
        bookQuantity: qty,
        bookFaceValue: face,
        bookTotal: total,
        maturityDate: existing?.maturityDate || '',
        couponRate: existing?.couponRate || '',
      })
      next.push(row)
      byKey.delete(key)
      n += 1
    }
    // 保留未匹配的手工行
    for (const leftover of byKey.values()) next.push(leftover)
    rows.value = next.map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
    return n
  }

  /** 从 G1-11 监盘回填②库存数量 */
  function syncFromSecuritiesCount(): number {
    if (opts.isReadonly.value) return 0
    const counts = loadCountRows(opts.allResponses.value)
    if (!counts.length) return 0
    const map = new Map<string, G1SecuritiesCountRow>()
    for (const c of counts) {
      map.set(matchKey(c.securityName, c.securityCode), c)
    }
    let n = 0
    rows.value = rows.value.map((r) => {
      const hit = map.get(matchKey(r.securityName, r.cashAccountNo))
        || map.get(matchKey(r.securityName))
      if (!hit) return r
      n += 1
      return enrichG1InventoryRow({
        ...r,
        stockQuantity: parseNum(hit.countedQuantity),
        stockFaceValue: r.stockFaceValue || r.bookFaceValue,
      })
    })
    persistAll()
    return n
  }

  /** 用已解析的函证证券行回填④（纯数据，便于单测） */
  function syncFromConfirmationRows(confirmRows: G1ConfirmationSecuritiesInput[]): number {
    if (opts.isReadonly.value || !confirmRows?.length) return 0
    const result = applyConfirmationSecuritiesRows(rows.value, confirmRows)
    lastConfirmSync.value = result
    if (result.matched === 0) return 0
    rows.value = result.rows
    persistAll()
    return result.matched
  }

  /**
   * 从函证模块回填④：优先 G0-3S（diff-securities-v1），其次 G0-1（confirmation-v1 金额）。
   * 匹配键：证券代码 / 证券名称（与账面行 cashAccountNo、securityName 对齐）。
   */
  async function syncFromConfirmationModule(projectId: string): Promise<number> {
    if (opts.isReadonly.value || !projectId) return 0
    const { api } = await import('@/services/apiProxy')

    async function loadByWpCode(wpCode: string): Promise<any[]> {
      try {
        const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
          params: { project_id: projectId, wp_code: wpCode },
          _silent: true,
        } as any)
        const wpId = (idRes as any)?.wp_id
        if (!wpId) return []
        const cfg = await api.get<any>(`/api/workpapers/${wpId}/render-config`, { _silent: true } as any)
        const sheets = cfg?.sheets ?? []
        for (const sheet of sheets) {
          const hd = sheet?.html_data ?? sheet?.htmlData
          if (!hd || !Array.isArray(hd.rows)) continue
          if (hd._format === 'diff-securities-v1' || hd._format === 'confirmation-v1') {
            return hd.rows
          }
        }
        // 无 _format 时：若行含证券字段也接受
        for (const sheet of sheets) {
          const hd = sheet?.html_data ?? sheet?.htmlData
          if (Array.isArray(hd?.rows) && hd.rows.some((r: any) => r.security_name || r.confirmed_qty != null)) {
            return hd.rows
          }
        }
      } catch {
        /* silent */
      }
      return []
    }

    let confirmRows = await loadByWpCode('G0-3S')
    if (!confirmRows.length) confirmRows = await loadByWpCode('G0-1')
    if (!confirmRows.length) return 0
    return syncFromConfirmationRows(confirmRows)
  }

  /** 将差异行推送为 G1-3 调整草稿 */
  function pushDiffToAdjustment(rowIds?: string[]): number {
    if (opts.isReadonly.value) return 0
    const targets = rows.value.filter(
      (r) => isDiffAbnormal(r) && (!rowIds || rowIds.includes(r.id)),
    )
    if (!targets.length) return 0

    let existing: G1AdjustmentRow[] = []
    const raw = opts.allResponses.value.get(ADJ_KEY)?.remark
      || opts.allResponses.value.get(ADJ_KEY)?.conclusion
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) existing = parsed
      } catch {
        existing = []
      }
    }

    const added: G1AdjustmentRow[] = targets.map((r) => {
      const amt = Math.abs(parseNum(r.diffTotal))
      const isDebit = parseNum(r.diffTotal) > 0
      const row = createEmptyG1AdjustmentRow()
      return {
        ...row,
        description: `G1-4 结存差异：${r.securityName || '未命名证券'}`,
        category: '账项调整',
        reportItem: '交易性金融资产',
        accountName: r.accountName || '交易性金融资产',
        accountCode: '1501',
        debitAmount: isDebit ? amt : 0,
        creditAmount: isDebit ? 0 : amt,
        indexRef: 'G1-4',
        remark: r.remark || `数量差异 ${r.diffQuantity}`,
      }
    })

    const merged = [...existing, ...added]
    const json = JSON.stringify(merged)
    opts.debouncedSave(ADJ_KEY, { remark: json, conclusion: json })

    for (const row of added) {
      try {
        window.dispatchEvent(
          new CustomEvent('adjustment:created', {
            detail: {
              wpCode: 'G1',
              entryType: 'AJE',
              amount: Math.max(row.debitAmount, row.creditAmount),
              accountCode: '1501',
              accountName: row.accountName,
              description: row.description,
              debitAmount: row.debitAmount,
              creditAmount: row.creditAmount,
              source: 'G1-4',
              timestamp: Date.now(),
            },
          }),
        )
      } catch {
        /* silent */
      }
    }
    return added.length
  }

  return {
    rows,
    auditConclusion,
    grandTotal,
    diffCount,
    bookGrandTotal,
    diffGrandTotal,
    reconCrossMismatches,
    lastConfirmSync,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
    syncFromDetail,
    syncFromSecuritiesCount,
    syncFromConfirmationRows,
    syncFromConfirmationModule,
    pushDiffToAdjustment,
    isDiffAbnormal,
  }
}

export default useG1Inventory
