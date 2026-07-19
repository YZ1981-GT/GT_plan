/**
 * useG1CountReconciliation — G1-12 有价证券盘点倒轧表
 *
 * 对齐致同 Excel「有价证券盘点倒轧表G1-12」：
 *   盘点日实存 → 资产负债表日至盘点日增减 → 报表日推算实存 → 账面结存 → 差异
 *
 * 公式：
 *   报表日数量 = 盘点日数量 − 增加 + 减少
 *   报表日总计 = 报表日面值 × 报表日数量
 *   差异数量/金额 = 报表日 − 账面
 *
 * 与 G1-11 分工：监盘表提供盘点日实存；本表做时间轴倒轧与账面勾稽。
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcReconciliation,
  calcFaceTotal,
  calcSubtotal,
} from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export type G1SecurityCategory = 'debt' | 'equity' | 'derivative' | 'other' | ''

export const G1_SECURITY_CATEGORY_OPTIONS = [
  { value: 'debt', label: '债务工具投资' },
  { value: 'equity', label: '权益工具投资' },
  { value: 'derivative', label: '衍生金融资产' },
  { value: 'other', label: '其他' },
] as const

export interface G1ReconciliationRow {
  id: string
  seq: number
  category: G1SecurityCategory
  securityName: string
  /** 盘点日实存 */
  countQuantity: number
  countFaceValue: number
  countTotal: number
  countCouponRate: number
  countMaturityDate: string
  /** 资产负债表日→盘点日：增加 / 减少 */
  increaseQuantity: number
  increaseFaceTotal: number
  decreaseQuantity: number
  decreaseFaceTotal: number
  /** 资产负债表日实存（推算） */
  reportQuantity: number
  reportFaceValue: number
  reportTotal: number
  reportCouponRate: number
  reportMaturityDate: string
  /** 账面结存交易性金融资产 */
  bookQuantity: number
  bookFaceValue: number
  bookTotal: number
  /** 差异（公式） */
  diffQuantity: number
  diffAmount: number
  remark: string
  /** 来自 G1-11 的行 id */
  countRowId?: string
}

export type G1ReconSegment = 'countDate' | 'changes' | 'reportDate'

export interface G1ReconciliationColumn {
  prop: keyof G1ReconciliationRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date' | 'select'
}

export const G1_RECON_COUNTDAY_COLUMNS: G1ReconciliationColumn[] = [
  { prop: 'seq', label: '序号', width: 52, type: 'number' },
  { prop: 'category', label: '分类', width: 120, type: 'select' },
  { prop: 'securityName', label: '证券名称', width: 140, type: 'text' },
  { prop: 'countQuantity', label: '数量', width: 90, type: 'number' },
  { prop: 'countFaceValue', label: '面值', width: 100, type: 'number' },
  { prop: 'countTotal', label: '总计', width: 110, type: 'number', formula: true },
  { prop: 'countCouponRate', label: '票面利率(%)', width: 100, type: 'number' },
  { prop: 'countMaturityDate', label: '到期日', width: 120, type: 'date' },
]

export const G1_RECON_CHANGES_COLUMNS: G1ReconciliationColumn[] = [
  { prop: 'seq', label: '序号', width: 52, type: 'number' },
  { prop: 'securityName', label: '证券名称', width: 140, type: 'text' },
  { prop: 'increaseQuantity', label: '增加·数量', width: 100, type: 'number' },
  { prop: 'increaseFaceTotal', label: '增加·面值总额', width: 120, type: 'number' },
  { prop: 'decreaseQuantity', label: '减少·数量', width: 100, type: 'number' },
  { prop: 'decreaseFaceTotal', label: '减少·面值总额', width: 120, type: 'number' },
]

export const G1_RECON_CALC_COLUMNS: G1ReconciliationColumn[] = [
  { prop: 'seq', label: '序号', width: 52, type: 'number' },
  { prop: 'securityName', label: '证券名称', width: 130, type: 'text' },
  { prop: 'reportQuantity', label: '报表日·数量', width: 110, type: 'number', formula: true },
  { prop: 'reportFaceValue', label: '报表日·面值', width: 100, type: 'number' },
  { prop: 'reportTotal', label: '报表日·总计', width: 110, type: 'number', formula: true },
  { prop: 'reportCouponRate', label: '票面利率(%)', width: 100, type: 'number' },
  { prop: 'reportMaturityDate', label: '到期日', width: 120, type: 'date' },
  { prop: 'bookQuantity', label: '账面·数量', width: 100, type: 'number' },
  { prop: 'bookFaceValue', label: '账面·面值', width: 100, type: 'number' },
  { prop: 'bookTotal', label: '账面·总计', width: 110, type: 'number' },
  { prop: 'diffQuantity', label: '差异·数量', width: 100, type: 'number', formula: true },
  { prop: 'diffAmount', label: '差异·金额', width: 110, type: 'number', formula: true },
  { prop: 'remark', label: '备注', width: 140, type: 'text' },
]

/** @deprecated 兼容旧测试命名：监盘日区段 */
export const G1_RECON_COUNTDAY_COLUMNS_LEGACY = G1_RECON_COUNTDAY_COLUMNS

const DATA_KEY = 'G1-12-rows'
const CONCLUSION_KEY = 'G1-12-conclusion'
const COUNT_KEY = 'G1-11-rows'

export function emptyRow(id: string, seq: number): G1ReconciliationRow {
  return {
    id,
    seq,
    category: '',
    securityName: '',
    countQuantity: 0,
    countFaceValue: 0,
    countTotal: 0,
    countCouponRate: 0,
    countMaturityDate: '',
    increaseQuantity: 0,
    increaseFaceTotal: 0,
    decreaseQuantity: 0,
    decreaseFaceTotal: 0,
    reportQuantity: 0,
    reportFaceValue: 0,
    reportTotal: 0,
    reportCouponRate: 0,
    reportMaturityDate: '',
    bookQuantity: 0,
    bookFaceValue: 0,
    bookTotal: 0,
    diffQuantity: 0,
    diffAmount: 0,
    remark: '',
  }
}

export function enrich(r: G1ReconciliationRow): G1ReconciliationRow {
  const countTotal = calcFaceTotal(r.countFaceValue, r.countQuantity)
  const reportQuantity = calcReconciliation(
    parseNum(r.countQuantity),
    parseNum(r.increaseQuantity),
    parseNum(r.decreaseQuantity),
  )
  const reportFaceValue = parseNum(r.reportFaceValue) || parseNum(r.countFaceValue)
  const reportTotal = calcFaceTotal(reportFaceValue, reportQuantity)
  const bookFaceValue = parseNum(r.bookFaceValue)
  const bookQuantity = parseNum(r.bookQuantity)
  // 有面值时按 面值×数量；否则保留手工录入的账面总计
  const bookTotal =
    bookFaceValue > 0
      ? calcFaceTotal(bookFaceValue, bookQuantity)
      : parseNum(r.bookTotal)
  const diffQuantity = reportQuantity - bookQuantity
  const diffAmount = Math.round((reportTotal - bookTotal) * 100) / 100
  return {
    ...r,
    countTotal,
    reportQuantity,
    reportFaceValue,
    reportTotal,
    bookTotal,
    diffQuantity,
    diffAmount,
  }
}

/** 旧版数量/金额双计量 → 新面值矩阵 */
export function migrateLegacyRow(p: Record<string, any>, i: number): G1ReconciliationRow {
  const base = emptyRow(String(p.id ?? `row-${i + 1}`), Number(p.seq) || i + 1)
  base.category = (p.category as G1SecurityCategory) || ''
  base.securityName = String(p.securityName ?? '')
  base.countQuantity = parseNum(p.countQuantity ?? p.countDayQuantity)
  base.countFaceValue = parseNum(p.countFaceValue)
  base.countCouponRate = parseNum(p.countCouponRate)
  base.countMaturityDate = String(p.countMaturityDate ?? '')
  base.increaseQuantity = parseNum(p.increaseQuantity)
  base.increaseFaceTotal = parseNum(p.increaseFaceTotal ?? p.increaseAmount)
  base.decreaseQuantity = parseNum(p.decreaseQuantity)
  base.decreaseFaceTotal = parseNum(p.decreaseFaceTotal ?? p.decreaseAmount)
  base.reportFaceValue = parseNum(p.reportFaceValue ?? p.countFaceValue)
  base.reportCouponRate = parseNum(p.reportCouponRate ?? p.countCouponRate)
  base.reportMaturityDate = String(p.reportMaturityDate ?? p.countMaturityDate ?? '')
  base.bookQuantity = parseNum(p.bookQuantity)
  base.bookFaceValue = parseNum(p.bookFaceValue)
  base.bookTotal = parseNum(p.bookTotal ?? p.bookAmount)
  base.remark = String(p.remark ?? p.conclusion ?? '')
  base.countRowId = p.countRowId ? String(p.countRowId) : undefined

  // 旧「金额」无面值时：把监盘日金额当作总计，反推面值
  if (!base.countFaceValue && parseNum(p.countDayAmount) && base.countQuantity) {
    base.countFaceValue = Math.round((parseNum(p.countDayAmount) / base.countQuantity) * 10000) / 10000
  }
  if (!base.bookFaceValue && parseNum(p.bookAmount) && base.bookQuantity) {
    base.bookFaceValue = Math.round((parseNum(p.bookAmount) / base.bookQuantity) * 10000) / 10000
    base.bookTotal = parseNum(p.bookAmount)
  }
  if (!base.reportFaceValue) base.reportFaceValue = base.countFaceValue

  return enrich(base)
}

function loadRows(map: Map<string, ChecklistResponse>): G1ReconciliationRow[] {
  const raw = map.get(DATA_KEY)?.conclusion ?? map.get(DATA_KEY)?.remark
  if (!raw) return [enrich(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow('1', 1))]
    return parsed.map((p, i) => migrateLegacyRow(p, i))
  } catch {
    return [enrich(emptyRow('1', 1))]
  }
}

const SUM_FIELDS = [
  'countQuantity',
  'countTotal',
  'increaseQuantity',
  'increaseFaceTotal',
  'decreaseQuantity',
  'decreaseFaceTotal',
  'reportQuantity',
  'reportTotal',
  'bookQuantity',
  'bookTotal',
  'diffQuantity',
  'diffAmount',
] as const

export type G1ReconciliationTotals = Record<(typeof SUM_FIELDS)[number], number>

function sumRows(list: G1ReconciliationRow[]): G1ReconciliationTotals {
  const out = {} as G1ReconciliationTotals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f] as number)))
  }
  return out
}

function mapSecurityTypeToCategory(t: string): G1SecurityCategory {
  const s = t.trim().toLowerCase()
  if (!s) return ''
  if (/债|bond|debt|票据|理财/.test(s)) return 'debt'
  if (/股|权益|equity|stock|fund|基金/.test(s)) return 'equity'
  if (/衍生|derivative|期权|期货|互换|远期/.test(s)) return 'derivative'
  return 'other'
}

export function useG1CountReconciliation(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1ReconciliationRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion ?? opts.allResponses.value.get(DATA_KEY)?.remark,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  const grandTotal = computed(() => sumRows(rows.value))

  const diffCount = computed(
    () =>
      rows.value.filter(
        (r) => Math.abs(parseNum(r.diffQuantity)) > 0 || Math.abs(parseNum(r.diffAmount)) > 0.01,
      ).length,
  )

  const stats = computed(() => {
    const byCat = { debt: 0, equity: 0, derivative: 0, other: 0, unset: 0 }
    for (const r of rows.value) {
      if (r.category === 'debt') byCat.debt++
      else if (r.category === 'equity') byCat.equity++
      else if (r.category === 'derivative') byCat.derivative++
      else if (r.category === 'other') byCat.other++
      else byCat.unset++
    }
    return { ...byCat, total: rows.value.length, withDiff: diffCount.value }
  })

  function isDiffAbnormal(row: G1ReconciliationRow): boolean {
    return Math.abs(parseNum(row.diffQuantity)) > 0 || Math.abs(parseNum(row.diffAmount)) > 0.01
  }

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1ReconciliationRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      const next = { ...r, ...patch }
      // 改盘点面值/数量且报表日面值仍等于旧盘点面值时，跟随更新
      if (
        ('countFaceValue' in patch || 'countQuantity' in patch)
        && parseNum(r.reportFaceValue) === parseNum(r.countFaceValue)
      ) {
        next.reportFaceValue = parseNum(next.countFaceValue)
      }
      if ('countCouponRate' in patch && r.reportCouponRate === r.countCouponRate) {
        next.reportCouponRate = next.countCouponRate
      }
      if ('countMaturityDate' in patch && r.reportMaturityDate === r.countMaturityDate) {
        next.reportMaturityDate = next.countMaturityDate
      }
      if ('bookFaceValue' in patch || 'bookQuantity' in patch) {
        next.bookTotal = 0 // 让 enrich 按面值×数量重算
      }
      return enrich(next)
    })
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入证券名称', '新增倒轧行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '证券名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [
        ...rows.value,
        enrich({ ...emptyRow(`row-${Date.now()}`, seq), securityName: value }),
      ]
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  /** 从 G1-11 监盘带入盘点日实存与账面数量 */
  function syncFromSecuritiesCount(force = false): number {
    if (opts.isReadonly.value) return 0
    const raw = opts.allResponses.value.get(COUNT_KEY)?.conclusion
      ?? opts.allResponses.value.get(COUNT_KEY)?.remark
    if (!raw) {
      ElMessage.warning('G1-11 暂无监盘数据，请先完成有价证券监盘表')
      return 0
    }
    let parsed: Record<string, unknown>[]
    try {
      parsed = JSON.parse(raw)
    } catch {
      ElMessage.error('G1-11 数据解析失败')
      return 0
    }
    if (!Array.isArray(parsed) || parsed.length === 0) {
      ElMessage.warning('G1-11 无有效监盘行')
      return 0
    }

    const existingByCountId = new Map(
      rows.value.filter((r) => r.countRowId).map((r) => [r.countRowId!, r]),
    )
    const existingByName = new Map(
      rows.value
        .filter((r) => r.securityName.trim())
        .map((r) => [r.securityName.trim(), r]),
    )

    const next: G1ReconciliationRow[] = []
    let added = 0
    let updated = 0

    for (let i = 0; i < parsed.length; i++) {
      const p = parsed[i]
      const name = String(p.securityName ?? '').trim()
      if (!name) continue
      const countId = String(p.id ?? '')
      const matched =
        (countId && existingByCountId.get(countId))
        || existingByName.get(name)

      const face = parseNum(p.faceValue)
      const qty = parseNum(p.countedQuantity ?? p.quantity)
      const bookedQty = parseNum(p.bookedQuantity)
      const coupon = parseNum(p.couponRate)
      const maturity = String(p.maturityDate ?? '')
      const cat = mapSecurityTypeToCategory(String(p.securityType ?? ''))

      if (matched && !force) {
        const patch: Partial<G1ReconciliationRow> = {
          countQuantity: qty,
          countFaceValue: face || matched.countFaceValue,
          countCouponRate: coupon || matched.countCouponRate,
          countMaturityDate: maturity || matched.countMaturityDate,
          bookQuantity: bookedQty || matched.bookQuantity,
          countRowId: countId || matched.countRowId,
        }
        if (cat && !matched.category) patch.category = cat
        if (!matched.reportFaceValue) patch.reportFaceValue = face || matched.countFaceValue
        if (!matched.reportCouponRate) patch.reportCouponRate = coupon
        if (!matched.reportMaturityDate) patch.reportMaturityDate = maturity
        next.push(enrich({ ...matched, ...patch, securityName: name }))
        updated++
      } else if (matched && force) {
        next.push(
          enrich({
            ...matched,
            securityName: name,
            category: cat || matched.category,
            countQuantity: qty,
            countFaceValue: face,
            countCouponRate: coupon,
            countMaturityDate: maturity,
            reportFaceValue: face,
            reportCouponRate: coupon,
            reportMaturityDate: maturity,
            bookQuantity: bookedQty,
            countRowId: countId || matched.countRowId,
          }),
        )
        updated++
      } else {
        next.push(
          enrich({
            ...emptyRow(countId || `row-${Date.now()}-${i}`, next.length + 1),
            securityName: name,
            category: cat,
            countQuantity: qty,
            countFaceValue: face,
            countCouponRate: coupon,
            countMaturityDate: maturity,
            reportFaceValue: face,
            reportCouponRate: coupon,
            reportMaturityDate: maturity,
            bookQuantity: bookedQty,
            countRowId: countId || undefined,
          }),
        )
        added++
      }
    }

    if (next.length === 0) {
      ElMessage.warning('G1-11 无可同步的证券行')
      return 0
    }

    // 保留本表已有、但监盘未覆盖的行（如手工增减说明行）
    const syncedIds = new Set(next.map((r) => r.id))
    const syncedNames = new Set(next.map((r) => r.securityName.trim()))
    for (const r of rows.value) {
      if (syncedIds.has(r.id)) continue
      if (r.countRowId && next.some((n) => n.countRowId === r.countRowId)) continue
      if (syncedNames.has(r.securityName.trim())) continue
      if (r.securityName.trim() || r.countQuantity || r.bookQuantity) {
        next.push(r)
      }
    }

    rows.value = next.map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
    ElMessage.success(`已从 G1-11 同步：新增 ${added}、更新 ${updated}`)
    return added + updated
  }

  return {
    countDayColumns: G1_RECON_COUNTDAY_COLUMNS,
    changesColumns: G1_RECON_CHANGES_COLUMNS,
    calcColumns: G1_RECON_CALC_COLUMNS,
    rows,
    auditConclusion,
    grandTotal,
    diffCount,
    stats,
    isDiffAbnormal,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
    syncFromSecuritiesCount,
  }
}

export default useG1CountReconciliation
