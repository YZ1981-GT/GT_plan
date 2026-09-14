/**
 * useH8Detail — H8-2 明细表（对齐致同源模板 79×58 宽表）
 *
 * 源模板把「原值 | 累计折旧 | 减值准备+审定净值」横排三页（A–V / W–AM / AN–BF），
 * HTML 拆为 4 区段 Tab，行同步：
 *   ① 基础+初始计量（合同身份 + CAS21 入账值）
 *   ② 原值（未审 期初+租入/重估/其他增 − 转租融资/转让待售/其他减 = 期末
 *          → 期初调整/账项调整 → 审定自动）
 *   ③ 累计折旧（计提|其他增 / 转租融资|转让待售|其他减）
 *   ④ 减值+净值+变更（同折旧结构；净值=原值−折旧−减值；CAS8 减值不得转回）
 *
 * 后向兼容：initialAmount / accDepBegin / depCurrentPeriod / accDepEnd / netValue
 *   供 H8-4/5/7/8/10/12 等跨表带入继续使用。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcSubtotal,
} from './useH8FormulaEngine'
import { calcInitialMeasurement } from './useH8CAS21Engine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H8-2 明细行（源模板核心列 + CAS21 合同字段） */
export interface H8DetailRow {
  rowId: string

  // ═══ 区段1: 基础 + CAS21 初始计量 ═══
  /** 使用权资产类别（房屋及建筑物/机器设备…） */
  category: string
  contractNo: string
  assetName: string
  assetNo: string
  lessor: string
  /** @deprecated 兼容旧 leaseType，等同 category */
  leaseType: string
  startDate: string
  endDate: string
  leaseTermMonths: number
  h9InitialAmount: number
  directCost: number
  incentive: number
  /** CAS21 入账值 = H9 + 直接费用 − 激励（公式） */
  initialAmount: number

  // ═══ 区段2: 原值 — 未审 ═══
  costBeginUnadj: number
  /** 本期租入 */
  costIncLease: number
  /** 租赁负债重估调整 */
  costIncReval: number
  /** 其他增加 */
  costIncOther: number
  /** 转租转为融资租赁 */
  costDecSublease: number
  /** 转让或持有待售 */
  costDecDisposal: number
  /** 其他减少 */
  costDecOther: number
  costEndUnadj: number
  costOpenAdj: number
  costAjeIncLease: number
  costAjeIncReval: number
  costAjeIncOther: number
  costAjeDecSublease: number
  costAjeDecDisposal: number
  costAjeDecOther: number
  costBeginAud: number
  costIncAud: number
  costDecAud: number
  costEndAud: number

  // ═══ 区段3: 累计折旧 — 未审 ═══
  depBeginUnadj: number
  depProvUnadj: number
  depOtherIncUnadj: number
  depDecSublease: number
  depDecDisposal: number
  depOtherDecUnadj: number
  depEndUnadj: number
  depOpenAdj: number
  depAjeProv: number
  depAjeOtherInc: number
  depAjeDecSublease: number
  depAjeDecDisposal: number
  depAjeOtherDec: number
  depBeginAud: number
  depIncAud: number
  depDecAud: number
  depEndAud: number

  // ═══ 区段4: 减值 — 未审 ═══
  impairBeginUnadj: number
  impairProvUnadj: number
  impairOtherIncUnadj: number
  impairDecSublease: number
  impairDecDisposal: number
  impairOtherDecUnadj: number
  impairEndUnadj: number
  impairOpenAdj: number
  impairAjeProv: number
  impairAjeOtherInc: number
  impairAjeDecSublease: number
  impairAjeDecDisposal: number
  impairAjeOtherDec: number
  impairBeginAud: number
  impairIncAud: number
  impairDecAud: number
  impairEndAud: number

  // 净值（公式）
  netBeginUnadj: number
  netBeginAud: number
  netEndUnadj: number
  netEndAud: number

  // 变更
  modificationAmount: number
  terminationDate: string
  remark: string

  // ── 后向兼容别名（跨表仍读这些键）──
  accDepBegin: number
  depCurrentPeriod: number
  accDepEnd: number
  netValue: number
}

export type H8DetailTab = 'basic' | 'cost' | 'dep' | 'impair'

export const H8_2_CATEGORY_OPTIONS = [
  '房屋及建筑物',
  '机器设备',
  '运输设备',
  '办公设备',
  '其他设备',
] as const

export const H8_DETAIL_SEGMENTS: { label: string; value: H8DetailTab }[] = [
  { label: '基础+初始计量', value: 'basic' },
  { label: '原值变动', value: 'cost' },
  { label: '累计折旧', value: 'dep' },
  { label: '减值与净值', value: 'impair' },
]

const ROWS_KEY = 'H8-2-rows'
const DETAIL_TOTAL_KEY = 'H8-2-initial-total'

/** H8-1 审定合计键（优先） */
const H81_COST_TOTAL = 'H8-1-cost-audited-total'
const H81_DEP_TOTAL = 'H8-1-dep-audited-total'
const H81_IMPAIR_TOTAL = 'H8-1-impair-audited-total'
const H81_NET_TOTAL = 'H8-1-net-audited'
const H81_COST_ROWS = 'H8-1-cost-rows'
const H81_DEP_ROWS = 'H8-1-dep-rows'
const H81_IMPAIR_ROWS = 'H8-1-impair-rows'
const H88_DEP_ROWS = 'H8-8-dep-rows'

function _num(v: unknown, d = 0): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : d
}

function _str(v: unknown, d = ''): string {
  if (v == null) return d
  return String(v)
}

function _parseJsonRemark(item: any): any {
  if (!item) return null
  const raw = item.remark ?? item.conclusion
  if (raw == null) return null
  if (typeof raw !== 'string') return raw
  try { return JSON.parse(raw) } catch { return raw }
}

/** 读 H8-1 数值合计（remark 存数字串） */
function _readTotalRemark(map: Map<string, any>, key: string): number {
  const raw = map.get(key)?.remark
  if (raw == null || raw === '') return 0
  return _num(raw)
}

/** 从 H8-1 分块行汇总期末审定 = 未审 + 账项调整 */
function _sumH81BlockEndAudited(map: Map<string, any>, rowsKey: string): number {
  const data = _parseJsonRemark(map.get(rowsKey))
  if (!Array.isArray(data)) return 0
  return calcSubtotal(
    data
      .filter((r: any) => !r.isSubtotal)
      .map((r: any) => {
        if (r.endAudited != null) return _num(r.endAudited)
        if (r.audited != null) return _num(r.audited)
        return _num(r.endUnadjusted) + _num(r.endAdjustment ?? r.aje)
      }),
  )
}

export interface H82CrossValidation {
  costFromH81: number
  depFromH81: number
  impairFromH81: number
  netFromH81: number
  costTotal: number
  depTotal: number
  impairTotal: number
  netTotal: number
  costDiff: number
  depDiff: number
  impairDiff: number
  netDiff: number
  hasCostWarning: boolean
  hasDepWarning: boolean
  hasImpairWarning: boolean
  hasNetWarning: boolean
  /** H8-1 与 H8-2 均有数且全部勾稽 */
  isConsistent: boolean
  /** 任一侧尚无数据 */
  isEmpty: boolean
}

function _diffWarn(a: number, b: number): boolean {
  return Math.abs(a - b) > 0.01 && (a !== 0 || b !== 0)
}

function _id(): string {
  return `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

/** 空行 */
export function createEmptyH8DetailRow(partial?: Partial<H8DetailRow>): H8DetailRow {
  const row: H8DetailRow = {
    rowId: _id(),
    category: '',
    contractNo: '',
    assetName: '',
    assetNo: '',
    lessor: '',
    leaseType: '',
    startDate: '',
    endDate: '',
    leaseTermMonths: 0,
    h9InitialAmount: 0,
    directCost: 0,
    incentive: 0,
    initialAmount: 0,

    costBeginUnadj: 0,
    costIncLease: 0,
    costIncReval: 0,
    costIncOther: 0,
    costDecSublease: 0,
    costDecDisposal: 0,
    costDecOther: 0,
    costEndUnadj: 0,
    costOpenAdj: 0,
    costAjeIncLease: 0,
    costAjeIncReval: 0,
    costAjeIncOther: 0,
    costAjeDecSublease: 0,
    costAjeDecDisposal: 0,
    costAjeDecOther: 0,
    costBeginAud: 0,
    costIncAud: 0,
    costDecAud: 0,
    costEndAud: 0,

    depBeginUnadj: 0,
    depProvUnadj: 0,
    depOtherIncUnadj: 0,
    depDecSublease: 0,
    depDecDisposal: 0,
    depOtherDecUnadj: 0,
    depEndUnadj: 0,
    depOpenAdj: 0,
    depAjeProv: 0,
    depAjeOtherInc: 0,
    depAjeDecSublease: 0,
    depAjeDecDisposal: 0,
    depAjeOtherDec: 0,
    depBeginAud: 0,
    depIncAud: 0,
    depDecAud: 0,
    depEndAud: 0,

    impairBeginUnadj: 0,
    impairProvUnadj: 0,
    impairOtherIncUnadj: 0,
    impairDecSublease: 0,
    impairDecDisposal: 0,
    impairOtherDecUnadj: 0,
    impairEndUnadj: 0,
    impairOpenAdj: 0,
    impairAjeProv: 0,
    impairAjeOtherInc: 0,
    impairAjeDecSublease: 0,
    impairAjeDecDisposal: 0,
    impairAjeOtherDec: 0,
    impairBeginAud: 0,
    impairIncAud: 0,
    impairDecAud: 0,
    impairEndAud: 0,

    netBeginUnadj: 0,
    netBeginAud: 0,
    netEndUnadj: 0,
    netEndAud: 0,

    modificationAmount: 0,
    terminationDate: '',
    remark: '',

    accDepBegin: 0,
    depCurrentPeriod: 0,
    accDepEnd: 0,
    netValue: 0,
  }
  if (partial) Object.assign(row, partial)
  recalcH8DetailRow(row)
  return row
}

/**
 * 重算行内公式（对齐源 xlsx 第12行）：
 * 原值期末未审 = 期初+三项增−三项减
 * 审定期初 = 未审期初+期初调整；审定增/减 = 未审合计+账项调整合计
 * 折旧/减值同备抵结构；净值 = 原值 − 累计折旧 − 减值
 */
export function recalcH8DetailRow(row: H8DetailRow): void {
  const costIncUnadj = row.costIncLease + row.costIncReval + row.costIncOther
  const costDecUnadj = row.costDecSublease + row.costDecDisposal + row.costDecOther
  row.costEndUnadj = calcAssetEndBalance(row.costBeginUnadj, costIncUnadj, costDecUnadj)

  const costAjeInc = row.costAjeIncLease + row.costAjeIncReval + row.costAjeIncOther
  const costAjeDec = row.costAjeDecSublease + row.costAjeDecDisposal + row.costAjeDecOther
  row.costBeginAud = row.costBeginUnadj + row.costOpenAdj
  row.costIncAud = costIncUnadj + costAjeInc
  row.costDecAud = costDecUnadj + costAjeDec
  row.costEndAud = calcAssetEndBalance(row.costBeginAud, row.costIncAud, row.costDecAud)

  const depIncUnadj = row.depProvUnadj + row.depOtherIncUnadj
  const depDecUnadj = row.depDecSublease + row.depDecDisposal + row.depOtherDecUnadj
  row.depEndUnadj = calcContraEndBalance(row.depBeginUnadj, depDecUnadj, depIncUnadj)
  row.depBeginAud = row.depBeginUnadj + row.depOpenAdj
  row.depIncAud = depIncUnadj + row.depAjeProv + row.depAjeOtherInc
  row.depDecAud = depDecUnadj + row.depAjeDecSublease + row.depAjeDecDisposal + row.depAjeOtherDec
  row.depEndAud = calcContraEndBalance(row.depBeginAud, row.depDecAud, row.depIncAud)

  const impairIncUnadj = row.impairProvUnadj + row.impairOtherIncUnadj
  const impairDecUnadj = row.impairDecSublease + row.impairDecDisposal + row.impairOtherDecUnadj
  row.impairEndUnadj = calcContraEndBalance(row.impairBeginUnadj, impairDecUnadj, impairIncUnadj)
  row.impairBeginAud = row.impairBeginUnadj + row.impairOpenAdj
  row.impairIncAud = impairIncUnadj + row.impairAjeProv + row.impairAjeOtherInc
  row.impairDecAud =
    impairDecUnadj + row.impairAjeDecSublease + row.impairAjeDecDisposal + row.impairAjeOtherDec
  row.impairEndAud = calcContraEndBalance(row.impairBeginAud, row.impairDecAud, row.impairIncAud)

  row.netBeginUnadj = calcNetValue(row.costBeginUnadj, row.depBeginUnadj, row.impairBeginUnadj)
  row.netBeginAud = calcNetValue(row.costBeginAud, row.depBeginAud, row.impairBeginAud)
  row.netEndUnadj = calcNetValue(row.costEndUnadj, row.depEndUnadj, row.impairEndUnadj)
  row.netEndAud = calcNetValue(row.costEndAud, row.depEndAud, row.impairEndAud)

  // CAS21 入账值
  const cas21 = calcInitialMeasurement(row.h9InitialAmount, row.directCost, row.incentive)
  row.initialAmount = cas21 > 0 ? cas21 : row.costEndAud

  // 后向兼容
  if (!row.leaseType && row.category) row.leaseType = row.category
  if (!row.category && row.leaseType) row.category = row.leaseType
  row.accDepBegin = row.depBeginUnadj
  row.depCurrentPeriod = row.depProvUnadj
  row.accDepEnd = row.depEndAud
  row.netValue = row.netEndAud
}

/** 旧精简行 / 新宽表行 → 统一模型 */
export function normalizeH8DetailRow(raw: any): H8DetailRow {
  const row = createEmptyH8DetailRow()
  if (!raw || typeof raw !== 'object') return row

  row.rowId = _str(raw.rowId, row.rowId)
  row.category = _str(raw.category ?? raw.assetCategory ?? raw.leaseType)
  row.leaseType = _str(raw.leaseType ?? row.category)
  row.contractNo = _str(raw.contractNo)
  row.assetName = _str(raw.assetName ?? raw.name)
  row.assetNo = _str(raw.assetNo ?? raw.assetCode)
  row.lessor = _str(raw.lessor)
  row.startDate = _str(raw.startDate)
  row.endDate = _str(raw.endDate)
  row.leaseTermMonths = _num(raw.leaseTermMonths)
  row.h9InitialAmount = _num(raw.h9InitialAmount ?? raw.h9InitialMeasurement)
  row.directCost = _num(raw.directCost)
  row.incentive = _num(raw.incentive ?? raw.leaseIncentive)
  row.modificationAmount = _num(raw.modificationAmount ?? raw.modAdjustment)
  row.terminationDate = _str(raw.terminationDate)
  row.remark = _str(raw.remark)

  const hasNewCost =
    raw.costBeginUnadj != null
    || raw.costIncLease != null
    || raw.costIncReval != null
    || raw.costEndUnadj != null
    || raw.costEndAud != null

  if (hasNewCost) {
    row.costBeginUnadj = _num(raw.costBeginUnadj)
    row.costIncLease = _num(raw.costIncLease)
    row.costIncReval = _num(raw.costIncReval)
    row.costIncOther = _num(raw.costIncOther)
    row.costDecSublease = _num(raw.costDecSublease)
    row.costDecDisposal = _num(raw.costDecDisposal)
    row.costDecOther = _num(raw.costDecOther)
    row.costOpenAdj = _num(raw.costOpenAdj)
    row.costAjeIncLease = _num(raw.costAjeIncLease)
    row.costAjeIncReval = _num(raw.costAjeIncReval)
    row.costAjeIncOther = _num(raw.costAjeIncOther)
    row.costAjeDecSublease = _num(raw.costAjeDecSublease)
    row.costAjeDecDisposal = _num(raw.costAjeDecDisposal)
    row.costAjeDecOther = _num(raw.costAjeDecOther)
  } else {
    // 旧数据：入账值落入期初原值，便于继续编 rollforward
    const oldInitial =
      _num(raw.initialAmount)
      || calcInitialMeasurement(row.h9InitialAmount, row.directCost, row.incentive)
    row.costBeginUnadj = oldInitial
  }

  const hasNewDep =
    raw.depBeginUnadj != null
    || raw.depProvUnadj != null
    || raw.depEndUnadj != null
    || raw.depEndAud != null

  if (hasNewDep) {
    row.depBeginUnadj = _num(raw.depBeginUnadj)
    row.depProvUnadj = _num(raw.depProvUnadj)
    row.depOtherIncUnadj = _num(raw.depOtherIncUnadj)
    row.depDecSublease = _num(raw.depDecSublease)
    row.depDecDisposal = _num(raw.depDecDisposal ?? raw.depDispUnadj)
    row.depOtherDecUnadj = _num(raw.depOtherDecUnadj)
    row.depOpenAdj = _num(raw.depOpenAdj)
    row.depAjeProv = _num(raw.depAjeProv)
    row.depAjeOtherInc = _num(raw.depAjeOtherInc)
    row.depAjeDecSublease = _num(raw.depAjeDecSublease)
    row.depAjeDecDisposal = _num(raw.depAjeDecDisposal ?? raw.depAjeDisp)
    row.depAjeOtherDec = _num(raw.depAjeOtherDec)
  } else {
    row.depBeginUnadj = _num(raw.accDepBegin)
    row.depProvUnadj = _num(raw.depCurrentPeriod)
  }

  row.impairBeginUnadj = _num(raw.impairBeginUnadj ?? raw.impairmentBegin)
  row.impairProvUnadj = _num(raw.impairProvUnadj ?? raw.impairmentProvision ?? raw.currentImpairment)
  row.impairOtherIncUnadj = _num(raw.impairOtherIncUnadj)
  row.impairDecSublease = _num(raw.impairDecSublease)
  row.impairDecDisposal = _num(raw.impairDecDisposal ?? raw.impairDispUnadj)
  row.impairOtherDecUnadj = _num(raw.impairOtherDecUnadj)
  row.impairOpenAdj = _num(raw.impairOpenAdj)
  row.impairAjeProv = _num(raw.impairAjeProv)
  row.impairAjeOtherInc = _num(raw.impairAjeOtherInc)
  row.impairAjeDecSublease = _num(raw.impairAjeDecSublease)
  row.impairAjeDecDisposal = _num(raw.impairAjeDecDisposal ?? raw.impairAjeDisp)
  row.impairAjeOtherDec = _num(raw.impairAjeOtherDec)

  recalcH8DetailRow(row)
  return row
}

function _serializeRow(r: H8DetailRow): Record<string, unknown> {
  // 持久化全量 + 兼容别名，保证跨表带入不丢字段
  return { ...r }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Detail(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  const rows = ref<H8DetailRow[]>([])
  const activeTab = ref<H8DetailTab>('basic')

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(normalizeH8DetailRow)
    } else {
      rows.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  const subtotalRow = computed(() => ({
    initialAmount: calcSubtotal(rows.value.map(r => r.initialAmount)),
    costEndUnadj: calcSubtotal(rows.value.map(r => r.costEndUnadj)),
    costEndAud: calcSubtotal(rows.value.map(r => r.costEndAud)),
    depProvUnadj: calcSubtotal(rows.value.map(r => r.depProvUnadj)),
    depEndAud: calcSubtotal(rows.value.map(r => r.depEndAud)),
    impairEndAud: calcSubtotal(rows.value.map(r => r.impairEndAud)),
    netEndAud: calcSubtotal(rows.value.map(r => r.netEndAud)),
    // 兼容旧 UI
    accDepEnd: calcSubtotal(rows.value.map(r => r.accDepEnd)),
    netValue: calcSubtotal(rows.value.map(r => r.netValue)),
    depCurrentPeriod: calcSubtotal(rows.value.map(r => r.depCurrentPeriod)),
  }))

  const initialTotal: ComputedRef<number> = computed(() => subtotalRow.value.initialAmount)

  const categorySubtotals = computed(() => {
    const map = new Map<string, { category: string; costEndAud: number; depEndAud: number; netEndAud: number; count: number }>()
    for (const r of rows.value) {
      const cat = r.category || '未分类'
      const cur = map.get(cat) ?? { category: cat, costEndAud: 0, depEndAud: 0, netEndAud: 0, count: 0 }
      cur.costEndAud += r.costEndAud
      cur.depEndAud += r.depEndAud
      cur.netEndAud += r.netEndAud
      cur.count += 1
      map.set(cat, cur)
    }
    return [...map.values()]
  })

  /** 与 H8-1 审定表期末勾稽 */
  const crossValidation = computed<H82CrossValidation>(() => {
    const map = allResponses.value
    const costFromH81 =
      _readTotalRemark(map, H81_COST_TOTAL)
      || _readTotalRemark(map, 'H8-1-cost-audited')
      || _sumH81BlockEndAudited(map, H81_COST_ROWS)
    const depFromH81 =
      _readTotalRemark(map, H81_DEP_TOTAL)
      || _readTotalRemark(map, 'H8-1-accdep-audited')
      || _sumH81BlockEndAudited(map, H81_DEP_ROWS)
    const impairFromH81 =
      _readTotalRemark(map, H81_IMPAIR_TOTAL)
      || _sumH81BlockEndAudited(map, H81_IMPAIR_ROWS)
    const netFromH81 =
      _readTotalRemark(map, H81_NET_TOTAL)
      || (costFromH81 - depFromH81 - impairFromH81)

    const costTotal = subtotalRow.value.costEndAud
    const depTotal = subtotalRow.value.depEndAud
    const impairTotal = subtotalRow.value.impairEndAud
    const netTotal = subtotalRow.value.netEndAud

    const hasCostWarning = _diffWarn(costTotal, costFromH81)
    const hasDepWarning = _diffWarn(depTotal, depFromH81)
    const hasImpairWarning = _diffWarn(impairTotal, impairFromH81)
    const hasNetWarning = _diffWarn(netTotal, netFromH81)
    const isEmpty =
      rows.value.length === 0
      && costFromH81 === 0
      && depFromH81 === 0
      && impairFromH81 === 0

    return {
      costFromH81,
      depFromH81,
      impairFromH81,
      netFromH81,
      costTotal,
      depTotal,
      impairTotal,
      netTotal,
      costDiff: costTotal - costFromH81,
      depDiff: depTotal - depFromH81,
      impairDiff: impairTotal - impairFromH81,
      netDiff: netTotal - netFromH81,
      hasCostWarning,
      hasDepWarning,
      hasImpairWarning,
      hasNetWarning,
      isEmpty,
      isConsistent:
        !isEmpty
        && !hasCostWarning
        && !hasDepWarning
        && !hasImpairWarning
        && !hasNetWarning,
    }
  })

  /** 租赁期≤12 月的行（提示转 H8-13，不含购买权场景由 H8-5 精细判断） */
  const shortTermCandidates = computed(() =>
    rows.value.filter(r => r.leaseTermMonths > 0 && r.leaseTermMonths <= 12),
  )

  function addRow(contractNo: string): void {
    if (!contractNo?.trim()) return
    rows.value.push(createEmptyH8DetailRow({ contractNo: contractNo.trim() }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  const TEXT_FIELDS = new Set([
    'contractNo', 'assetName', 'assetNo', 'lessor', 'category', 'leaseType',
    'startDate', 'endDate', 'terminationDate', 'remark',
  ])

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    if (TEXT_FIELDS.has(field)) {
      ;(row as any)[field] = String(value ?? '')
      if (field === 'category') row.leaseType = row.category
      if (field === 'leaseType' && !row.category) row.category = row.leaseType
      // 起止日变化时粗算租赁月数（可手改）
      if ((field === 'startDate' || field === 'endDate') && row.startDate && row.endDate) {
        const s = new Date(row.startDate)
        const e = new Date(row.endDate)
        if (!Number.isNaN(s.getTime()) && !Number.isNaN(e.getTime())) {
          row.leaseTermMonths = Math.max(
            (e.getFullYear() - s.getFullYear()) * 12 + (e.getMonth() - s.getMonth()),
            0,
          )
        }
      }
      recalcH8DetailRow(row)
      _persist()
      return
    }

    ;(row as any)[field] = _num(value)
    recalcH8DetailRow(row)
    _persist()
  }

  function setActiveTab(tab: H8DetailTab): void {
    activeTab.value = tab
  }

  function save(): void { _persist() }

  /**
   * 从 H8-8 按合同号回填本期计提折旧（优先 periodDep / currentPeriodDep，其次 bookDepreciation）
   */
  function pullDepFromH88(): { updated: number; unmatched: string[]; message: string } {
    const data = _parseJsonRemark(allResponses.value.get(H88_DEP_ROWS))
    if (!Array.isArray(data) || !data.length) {
      return { updated: 0, unmatched: [], message: 'H8-8 尚无折旧测算行' }
    }
    const byCn = new Map<string, any>()
    for (const r of data) {
      const cn = String(r?.contractNo ?? '').trim()
      if (cn) byCn.set(cn, r)
    }
    let updated = 0
    const unmatched: string[] = []
    for (const row of rows.value) {
      const cn = row.contractNo.trim()
      if (!cn) continue
      const src = byCn.get(cn)
      if (!src) {
        unmatched.push(cn)
        continue
      }
      const amt =
        _num(src.periodDep)
        || _num(src.currentPeriodDep)
        || _num(src.bookDepreciation)
      if (amt <= 0) continue
      row.depProvUnadj = amt
      // 若原值期末为空且 H8-8 有原值，补期初/入账参考
      const cost = _num(src.originalCost ?? src.rouAmount)
      if (cost > 0 && row.costEndAud === 0 && row.costBeginUnadj === 0 && row.costIncLease === 0) {
        row.costBeginUnadj = cost
      }
      const bookAcc = _num(src.bookAccDepEnd ?? src.accumulatedDep)
      if (bookAcc > 0 && row.depBeginUnadj === 0) {
        // 期末账面累计 − 本期 ≈ 期初（近似）
        row.depBeginUnadj = Math.max(bookAcc - amt, 0)
      }
      recalcH8DetailRow(row)
      updated += 1
    }
    if (updated) _persist()
    return {
      updated,
      unmatched,
      message: updated
        ? `已从 H8-8 回填 ${updated} 笔本期计提`
        : '无匹配合同可回填',
    }
  }

  /**
   * 用 CAS21 入账值填「本期租入」（仅当原值各变动列均为 0）
   */
  function seedCostIncFromInitial(): { updated: number; message: string } {
    let updated = 0
    for (const row of rows.value) {
      const emptyCost =
        row.costBeginUnadj === 0
        && row.costIncLease === 0
        && row.costIncReval === 0
        && row.costIncOther === 0
        && row.costDecSublease === 0
        && row.costDecDisposal === 0
        && row.costDecOther === 0
      if (!emptyCost) continue
      const amt = calcInitialMeasurement(row.h9InitialAmount, row.directCost, row.incentive)
      if (amt <= 0) continue
      row.costIncLease = amt
      recalcH8DetailRow(row)
      updated += 1
    }
    if (updated) _persist()
    return {
      updated,
      message: updated
        ? `已用入账值填入「本期租入」${updated} 笔`
        : '无需填入（已有原值或未填 CAS21）',
    }
  }

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value.map(_serializeRow))
    onSave(DETAIL_TOTAL_KEY, initialTotal.value)
    // 跨表别名：供 H8↔H9 / CrossSheet 多键兜底
    const direct = calcSubtotal(rows.value.map(r => r.directCost))
    const incentive = calcSubtotal(rows.value.map(r => r.incentive))
    const h9Init = calcSubtotal(rows.value.map(r => r.h9InitialAmount))
    onSave('H8-initial-measurement', initialTotal.value)
    onSave('H8-direct-cost-total', direct)
    onSave('H8-incentive-total', incentive)
    // 镜像写入，兼容旧 GtH8 父栏读 H8-h9-initial-recognition
    if (h9Init !== 0) onSave('H8-h9-initial-recognition', h9Init)
    // 同会话内 H9 挂载时可落库 H9-h8-*（跨底稿勾稽）
    try {
      window.dispatchEvent(new CustomEvent('h8:asset-updated', {
        detail: {
          h8InitialMeasurement: initialTotal.value,
          h8DirectCost: direct,
          h8Incentive: incentive,
          h9InitialAmount: h9Init,
        },
      }))
    } catch { /* SSR / 非浏览器 */ }
  }

  return {
    rows,
    activeTab,
    subtotalRow,
    initialTotal,
    categorySubtotals,
    crossValidation,
    shortTermCandidates,
    addRow,
    deleteRow,
    updateCell,
    setActiveTab,
    save,
    load,
    pullDepFromH88,
    seedCostIncFromInitial,
  }
}

export default useH8Detail
