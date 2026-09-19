/**
 * useH1Detail — H1-2 明细表 composable
 *
 * 对齐致同源模板「明细表H1-2」54列核心逻辑（宽表拆4区段）：
 *   原值/累计折旧/减值准备各自：未审数(期初/增/减/期末) + 期初调整 + 账项调整(增/减) + 审定数(期初/增/减/期末)
 *   折旧/减值增减细分：本期计提|其他增加 / 处置|其他减少
 *   净值：期初/期末 × 未审|审定；核对标志：提足折旧/闲置/权属/抵押
 *
 * 后向兼容：保留 originalCost / accDep / impairment / netValue 字段，
 *   未审变动写入 legacy 增减压字段；期末与净值同步为审定数供 H1-1、H1-7 等跨表取用。
 *
 * Spec: .kiro/specs/h1-fixed-assets/  |  Requirements: 3.1-3.12
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import {
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcSubtotal,
} from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表行（源模板54列精简为可编辑字段 + 公式派生列） */
export interface DetailRow {
  rowId: string
  // ── 区段1: 基础信息 ──
  category: string
  name: string
  assetNo: string
  acquisitionDate: string
  usefulLife: number
  salvageRate: number
  depMethod: string
  location: string
  department: string
  quantity: number
  unit: string
  spec: string
  supplier: string
  /** 是否提足折旧：Y/N/空 */
  isFullyDepreciated: string
  /** 是否闲置：Y/N/空 */
  isIdle: string
  /** 是否有权属证明：Y/N/空 */
  hasTitleDoc: string
  /** 是否抵押受限：Y/N/空 */
  isMortgaged: string

  // ── 区段2: 原值 — 未审 ──
  costBeginUnadj: number
  costIncUnadj: number
  costIncMethod: string
  costDecUnadj: number
  costDecMethod: string
  costEndUnadj: number
  /** 期初调整 */
  costOpenAdj: number
  /** 账项调整增减 */
  costAjeInc: number
  costAjeDec: number
  /** 审定（公式） */
  costBeginAud: number
  costIncAud: number
  costDecAud: number
  costEndAud: number

  // ── 区段3: 累计折旧 — 未审 ──
  depBeginUnadj: number
  depProvUnadj: number
  depOtherIncUnadj: number
  depDispUnadj: number
  depOtherDecUnadj: number
  depEndUnadj: number
  depOpenAdj: number
  depAjeProv: number
  depAjeOtherInc: number
  depAjeDisp: number
  depAjeOtherDec: number
  depBeginAud: number
  depIncAud: number
  depDecAud: number
  depEndAud: number

  // ── 区段4: 减值 — 未审 ──
  impairBeginUnadj: number
  impairProvUnadj: number
  impairOtherIncUnadj: number
  impairDispUnadj: number
  impairOtherDecUnadj: number
  impairEndUnadj: number
  impairOpenAdj: number
  impairAjeProv: number
  impairAjeOtherInc: number
  impairAjeDisp: number
  impairAjeOtherDec: number
  impairBeginAud: number
  impairIncAud: number
  impairDecAud: number
  impairEndAud: number

  // ── 净值（公式）──
  netBeginUnadj: number
  netBeginAud: number
  netEndUnadj: number
  netEndAud: number

  // ── 折旧辅助（测算参考，可手改年折旧）──
  annualDep: number
  monthlyDep: number

  // ── 后向兼容别名（跨表 H1-1/H1-4/H1-7/H1-12 等仍读这些键）──
  originalCostBegin: number
  originalCostIncrease: number
  originalCostDecrease: number
  originalCostEnd: number
  increaseReason: string
  decreaseReason: string
  accDepBegin: number
  accDepProvision: number
  accDepReversal: number
  accDepEnd: number
  impairmentBegin: number
  impairmentProvision: number
  impairmentReversal: number
  impairmentEnd: number
  impairmentReason: string
  recoverableAmount: number
  netValue: number
  remark: string
}

export interface SegmentConfig {
  key: string
  label: string
  fields: (keyof DetailRow)[]
}

export const H1_2_CONCLUSION_TEMPLATES: Record<'A' | 'B' | 'C', string> = {
  A: '未见异常。',
  B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
  C: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
}

export const H1_2_CATEGORY_OPTIONS = [
  '房屋及建筑物',
  '机器设备',
  '运输设备',
  '办公设备',
  '其他设备',
] as const

const ITEM_PREFIX = 'H1-2'

export const SEGMENT_CONFIGS: SegmentConfig[] = [
  {
    key: 'basic',
    label: '基础信息',
    fields: [
      'category', 'name', 'assetNo', 'acquisitionDate', 'usefulLife', 'salvageRate', 'depMethod',
      'location', 'department', 'quantity', 'unit', 'spec', 'supplier',
      'isFullyDepreciated', 'isIdle', 'hasTitleDoc', 'isMortgaged',
    ],
  },
  {
    key: 'cost',
    label: '原值变动',
    fields: [
      'costBeginUnadj', 'costIncUnadj', 'costIncMethod', 'costDecUnadj', 'costDecMethod', 'costEndUnadj',
      'costOpenAdj', 'costAjeInc', 'costAjeDec',
      'costBeginAud', 'costIncAud', 'costDecAud', 'costEndAud',
    ],
  },
  {
    key: 'depreciation',
    label: '累计折旧',
    fields: [
      'depBeginUnadj', 'depProvUnadj', 'depOtherIncUnadj', 'depDispUnadj', 'depOtherDecUnadj', 'depEndUnadj',
      'depOpenAdj', 'depAjeProv', 'depAjeOtherInc', 'depAjeDisp', 'depAjeOtherDec',
      'depBeginAud', 'depIncAud', 'depDecAud', 'depEndAud',
      'annualDep', 'monthlyDep', 'netEndAud',
    ],
  },
  {
    key: 'impairment',
    label: '减值准备',
    fields: [
      'impairBeginUnadj', 'impairProvUnadj', 'impairOtherIncUnadj', 'impairDispUnadj', 'impairOtherDecUnadj', 'impairEndUnadj',
      'impairOpenAdj', 'impairAjeProv', 'impairAjeOtherInc', 'impairAjeDisp', 'impairAjeOtherDec',
      'impairBeginAud', 'impairIncAud', 'impairDecAud', 'impairEndAud',
      'netBeginUnadj', 'netBeginAud', 'netEndUnadj', 'netEndAud',
    ],
  },
]

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown, fallback = ''): string {
  return v == null ? fallback : String(v)
}

function _normalizeDepMethod(v: unknown): string {
  const s = _str(v, '直线法')
  const map: Record<string, string> = {
    straight: '直线法',
    double: '双倍余额递减',
    sum_of_years: '年数总和',
    units: '工作量法',
    直线法: '直线法',
    双倍余额: '双倍余额递减',
    双倍余额递减: '双倍余额递减',
    年数总和: '年数总和',
    年数总和法: '年数总和',
    工作量法: '工作量法',
  }
  return map[s] ?? s
}

/** 空行骨架 */
export function createEmptyDetailRow(name = '', category = ''): DetailRow {
  const row: DetailRow = {
    rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    category,
    name,
    assetNo: '',
    acquisitionDate: '',
    usefulLife: 0,
    salvageRate: 0,
    depMethod: '直线法',
    location: '',
    department: '',
    quantity: 1,
    unit: '台',
    spec: '',
    supplier: '',
    isFullyDepreciated: '',
    isIdle: '',
    hasTitleDoc: '',
    isMortgaged: '',
    costBeginUnadj: 0,
    costIncUnadj: 0,
    costIncMethod: '',
    costDecUnadj: 0,
    costDecMethod: '',
    costEndUnadj: 0,
    costOpenAdj: 0,
    costAjeInc: 0,
    costAjeDec: 0,
    costBeginAud: 0,
    costIncAud: 0,
    costDecAud: 0,
    costEndAud: 0,
    depBeginUnadj: 0,
    depProvUnadj: 0,
    depOtherIncUnadj: 0,
    depDispUnadj: 0,
    depOtherDecUnadj: 0,
    depEndUnadj: 0,
    depOpenAdj: 0,
    depAjeProv: 0,
    depAjeOtherInc: 0,
    depAjeDisp: 0,
    depAjeOtherDec: 0,
    depBeginAud: 0,
    depIncAud: 0,
    depDecAud: 0,
    depEndAud: 0,
    impairBeginUnadj: 0,
    impairProvUnadj: 0,
    impairOtherIncUnadj: 0,
    impairDispUnadj: 0,
    impairOtherDecUnadj: 0,
    impairEndUnadj: 0,
    impairOpenAdj: 0,
    impairAjeProv: 0,
    impairAjeOtherInc: 0,
    impairAjeDisp: 0,
    impairAjeOtherDec: 0,
    impairBeginAud: 0,
    impairIncAud: 0,
    impairDecAud: 0,
    impairEndAud: 0,
    netBeginUnadj: 0,
    netBeginAud: 0,
    netEndUnadj: 0,
    netEndAud: 0,
    annualDep: 0,
    monthlyDep: 0,
    originalCostBegin: 0,
    originalCostIncrease: 0,
    originalCostDecrease: 0,
    originalCostEnd: 0,
    increaseReason: '',
    decreaseReason: '',
    accDepBegin: 0,
    accDepProvision: 0,
    accDepReversal: 0,
    accDepEnd: 0,
    impairmentBegin: 0,
    impairmentProvision: 0,
    impairmentReversal: 0,
    impairmentEnd: 0,
    impairmentReason: '',
    recoverableAmount: 0,
    netValue: 0,
    remark: '',
  }
  recalcDetailRow(row)
  return row
}

/**
 * 重算行内公式（对齐源 xlsx row13）：
 * 原值：I=D+E−G；M=D+J；N=E+K；O=G+L；P=M+N−O
 * 折旧：V=Q+R+S−T−U；AB=Q+W；AC=R+X+S+Y；AD=T+Z+U+AA；AE=AB+AC−AD
 * 减值：同折旧结构
 * 净值：AU=D−Q−AF；AV=M−AB−AQ；AW=I−V−AK；AX=P−AE−AT
 */
export function recalcDetailRow(row: DetailRow): void {
  // 原值
  row.costEndUnadj = calcAssetEndBalance(row.costBeginUnadj, row.costIncUnadj, row.costDecUnadj)
  row.costBeginAud = row.costBeginUnadj + row.costOpenAdj
  row.costIncAud = row.costIncUnadj + row.costAjeInc
  row.costDecAud = row.costDecUnadj + row.costAjeDec
  row.costEndAud = calcAssetEndBalance(row.costBeginAud, row.costIncAud, row.costDecAud)

  // 累计折旧（备抵：期末=期初+计提类增加−处置类减少）
  const depIncUnadj = row.depProvUnadj + row.depOtherIncUnadj
  const depDecUnadj = row.depDispUnadj + row.depOtherDecUnadj
  row.depEndUnadj = calcContraEndBalance(row.depBeginUnadj, depDecUnadj, depIncUnadj)
  row.depBeginAud = row.depBeginUnadj + row.depOpenAdj
  row.depIncAud = row.depProvUnadj + row.depAjeProv + row.depOtherIncUnadj + row.depAjeOtherInc
  row.depDecAud = row.depDispUnadj + row.depAjeDisp + row.depOtherDecUnadj + row.depAjeOtherDec
  row.depEndAud = calcContraEndBalance(row.depBeginAud, row.depDecAud, row.depIncAud)

  // 减值（备抵，结构同折旧；CAS8 一经确认不得转回——UI 提示，不强制拦）
  const impairIncUnadj = row.impairProvUnadj + row.impairOtherIncUnadj
  const impairDecUnadj = row.impairDispUnadj + row.impairOtherDecUnadj
  row.impairEndUnadj = calcContraEndBalance(row.impairBeginUnadj, impairDecUnadj, impairIncUnadj)
  row.impairBeginAud = row.impairBeginUnadj + row.impairOpenAdj
  row.impairIncAud = row.impairProvUnadj + row.impairAjeProv + row.impairOtherIncUnadj + row.impairAjeOtherInc
  row.impairDecAud = row.impairDispUnadj + row.impairAjeDisp + row.impairOtherDecUnadj + row.impairAjeOtherDec
  row.impairEndAud = calcContraEndBalance(row.impairBeginAud, row.impairDecAud, row.impairIncAud)

  // 净值
  row.netBeginUnadj = calcNetValue(row.costBeginUnadj, row.depBeginUnadj, row.impairBeginUnadj)
  row.netBeginAud = calcNetValue(row.costBeginAud, row.depBeginAud, row.impairBeginAud)
  row.netEndUnadj = calcNetValue(row.costEndUnadj, row.depEndUnadj, row.impairEndUnadj)
  row.netEndAud = calcNetValue(row.costEndAud, row.depEndAud, row.impairEndAud)

  if (row.annualDep > 0) {
    row.monthlyDep = Math.round((row.annualDep / 12) * 100) / 100
  }

  // 后向兼容同步
  row.originalCostBegin = row.costBeginUnadj
  row.originalCostIncrease = row.costIncUnadj
  row.originalCostDecrease = row.costDecUnadj
  row.originalCostEnd = row.costEndAud
  row.increaseReason = row.costIncMethod
  row.decreaseReason = row.costDecMethod
  row.accDepBegin = row.depBeginUnadj
  row.accDepProvision = row.depProvUnadj
  row.accDepReversal = row.depDispUnadj + row.depOtherDecUnadj
  row.accDepEnd = row.depEndAud
  row.impairmentBegin = row.impairBeginUnadj
  row.impairmentProvision = row.impairProvUnadj
  row.impairmentReversal = row.impairDispUnadj + row.impairOtherDecUnadj
  row.impairmentEnd = row.impairEndAud
  row.netValue = row.netEndAud
}

/** 从旧版精简字段或新版字段归一化 */
export function normalizeDetailRow(raw: any): DetailRow {
  const row = createEmptyDetailRow()
  if (!raw || typeof raw !== 'object') return row

  row.rowId = _str(raw.rowId, row.rowId)
  row.category = _str(raw.category)
  row.name = _str(raw.name ?? raw.assetName)
  row.assetNo = _str(raw.assetNo ?? raw.assetCode)
  row.acquisitionDate = _str(raw.acquisitionDate)
  row.usefulLife = _num(raw.usefulLife)
  row.salvageRate = _num(raw.salvageRate)
  row.depMethod = _normalizeDepMethod(raw.depMethod)
  row.location = _str(raw.location)
  row.department = _str(raw.department)
  row.quantity = _num(raw.quantity) || 1
  row.unit = _str(raw.unit, '台')
  row.spec = _str(raw.spec)
  row.supplier = _str(raw.supplier)
  row.isFullyDepreciated = _str(raw.isFullyDepreciated)
  row.isIdle = _str(raw.isIdle)
  row.hasTitleDoc = _str(raw.hasTitleDoc)
  row.isMortgaged = _str(raw.isMortgaged)
  row.remark = _str(raw.remark)
  row.impairmentReason = _str(raw.impairmentReason)
  row.recoverableAmount = _num(raw.recoverableAmount)
  row.annualDep = _num(raw.annualDep)
  row.monthlyDep = _num(raw.monthlyDep)

  const hasNewCost = raw.costBeginUnadj != null || raw.costIncUnadj != null || raw.costEndAud != null
  if (hasNewCost) {
    row.costBeginUnadj = _num(raw.costBeginUnadj)
    row.costIncUnadj = _num(raw.costIncUnadj)
    row.costIncMethod = _str(raw.costIncMethod ?? raw.increaseReason)
    row.costDecUnadj = _num(raw.costDecUnadj)
    row.costDecMethod = _str(raw.costDecMethod ?? raw.decreaseReason)
    row.costOpenAdj = _num(raw.costOpenAdj)
    row.costAjeInc = _num(raw.costAjeInc)
    row.costAjeDec = _num(raw.costAjeDec)
  } else {
    // 旧数据：原 originalCost* 视为未审数
    row.costBeginUnadj = _num(raw.originalCostBegin ?? raw.costOpening)
    row.costIncUnadj = _num(raw.originalCostIncrease ?? raw.costIncrease)
    row.costIncMethod = _str(raw.increaseReason)
    row.costDecUnadj = _num(raw.originalCostDecrease ?? raw.costDecrease)
    row.costDecMethod = _str(raw.decreaseReason)
  }

  const hasNewDep = raw.depBeginUnadj != null || raw.depProvUnadj != null || raw.depEndAud != null
  if (hasNewDep) {
    row.depBeginUnadj = _num(raw.depBeginUnadj)
    row.depProvUnadj = _num(raw.depProvUnadj)
    row.depOtherIncUnadj = _num(raw.depOtherIncUnadj)
    row.depDispUnadj = _num(raw.depDispUnadj)
    row.depOtherDecUnadj = _num(raw.depOtherDecUnadj)
    row.depOpenAdj = _num(raw.depOpenAdj)
    row.depAjeProv = _num(raw.depAjeProv)
    row.depAjeOtherInc = _num(raw.depAjeOtherInc)
    row.depAjeDisp = _num(raw.depAjeDisp)
    row.depAjeOtherDec = _num(raw.depAjeOtherDec)
  } else {
    row.depBeginUnadj = _num(raw.accDepBegin ?? raw.depOpening)
    row.depProvUnadj = _num(raw.accDepProvision ?? raw.depProvision)
    row.depDispUnadj = _num(raw.accDepReversal ?? raw.depReversal)
  }

  const hasNewImpair = raw.impairBeginUnadj != null || raw.impairProvUnadj != null || raw.impairEndAud != null
  if (hasNewImpair) {
    row.impairBeginUnadj = _num(raw.impairBeginUnadj)
    row.impairProvUnadj = _num(raw.impairProvUnadj)
    row.impairOtherIncUnadj = _num(raw.impairOtherIncUnadj)
    row.impairDispUnadj = _num(raw.impairDispUnadj)
    row.impairOtherDecUnadj = _num(raw.impairOtherDecUnadj)
    row.impairOpenAdj = _num(raw.impairOpenAdj)
    row.impairAjeProv = _num(raw.impairAjeProv)
    row.impairAjeOtherInc = _num(raw.impairAjeOtherInc)
    row.impairAjeDisp = _num(raw.impairAjeDisp)
    row.impairAjeOtherDec = _num(raw.impairAjeOtherDec)
  } else {
    row.impairBeginUnadj = _num(raw.impairmentBegin ?? raw.impairOpening)
    row.impairProvUnadj = _num(raw.impairmentProvision ?? raw.impairProvision)
    row.impairDispUnadj = _num(raw.impairmentReversal ?? raw.impairReversal)
  }

  recalcDetailRow(row)
  return row
}

function _sumH1Audited(allResponses: Map<string, ChecklistItem>, itemId: string): number {
  const raw = allResponses.get(itemId)?.remark
  if (!raw) return 0
  try {
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) return 0
    return calcSubtotal(arr.filter((r: any) => !r.isSubtotal).map((r: any) => _num(r.audited)))
  } catch {
    return 0
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Detail(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    crossSheetCostAudited?: Ref<number>
    crossSheetDepAudited?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<DetailRow[]>([])
  const activeSegment = ref<string>('basic')
  const selectedRowId = ref<string | null>(null)
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _loadRows(): void {
    const item = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    const raw = item?.remark
    if (!raw) {
      rows.value = []
    } else {
      try {
        const parsed = JSON.parse(raw)
        rows.value = Array.isArray(parsed) ? parsed.map(normalizeDetailRow) : []
      } catch {
        rows.value = []
      }
    }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  const subtotalRow = computed<Partial<DetailRow>>(() => ({
    rowId: 'subtotal',
    category: '合计',
    name: '',
    costBeginUnadj: calcSubtotal(rows.value.map((r) => r.costBeginUnadj)),
    costIncUnadj: calcSubtotal(rows.value.map((r) => r.costIncUnadj)),
    costDecUnadj: calcSubtotal(rows.value.map((r) => r.costDecUnadj)),
    costEndUnadj: calcSubtotal(rows.value.map((r) => r.costEndUnadj)),
    costOpenAdj: calcSubtotal(rows.value.map((r) => r.costOpenAdj)),
    costAjeInc: calcSubtotal(rows.value.map((r) => r.costAjeInc)),
    costAjeDec: calcSubtotal(rows.value.map((r) => r.costAjeDec)),
    costBeginAud: calcSubtotal(rows.value.map((r) => r.costBeginAud)),
    costIncAud: calcSubtotal(rows.value.map((r) => r.costIncAud)),
    costDecAud: calcSubtotal(rows.value.map((r) => r.costDecAud)),
    costEndAud: calcSubtotal(rows.value.map((r) => r.costEndAud)),
    depBeginUnadj: calcSubtotal(rows.value.map((r) => r.depBeginUnadj)),
    depProvUnadj: calcSubtotal(rows.value.map((r) => r.depProvUnadj)),
    depOtherIncUnadj: calcSubtotal(rows.value.map((r) => r.depOtherIncUnadj)),
    depDispUnadj: calcSubtotal(rows.value.map((r) => r.depDispUnadj)),
    depOtherDecUnadj: calcSubtotal(rows.value.map((r) => r.depOtherDecUnadj)),
    depEndUnadj: calcSubtotal(rows.value.map((r) => r.depEndUnadj)),
    depBeginAud: calcSubtotal(rows.value.map((r) => r.depBeginAud)),
    depIncAud: calcSubtotal(rows.value.map((r) => r.depIncAud)),
    depDecAud: calcSubtotal(rows.value.map((r) => r.depDecAud)),
    depEndAud: calcSubtotal(rows.value.map((r) => r.depEndAud)),
    impairBeginUnadj: calcSubtotal(rows.value.map((r) => r.impairBeginUnadj)),
    impairProvUnadj: calcSubtotal(rows.value.map((r) => r.impairProvUnadj)),
    impairEndUnadj: calcSubtotal(rows.value.map((r) => r.impairEndUnadj)),
    impairBeginAud: calcSubtotal(rows.value.map((r) => r.impairBeginAud)),
    impairIncAud: calcSubtotal(rows.value.map((r) => r.impairIncAud)),
    impairDecAud: calcSubtotal(rows.value.map((r) => r.impairDecAud)),
    impairEndAud: calcSubtotal(rows.value.map((r) => r.impairEndAud)),
    netBeginUnadj: calcSubtotal(rows.value.map((r) => r.netBeginUnadj)),
    netBeginAud: calcSubtotal(rows.value.map((r) => r.netBeginAud)),
    netEndUnadj: calcSubtotal(rows.value.map((r) => r.netEndUnadj)),
    netEndAud: calcSubtotal(rows.value.map((r) => r.netEndAud)),
    // legacy
    originalCostBegin: calcSubtotal(rows.value.map((r) => r.originalCostBegin)),
    originalCostIncrease: calcSubtotal(rows.value.map((r) => r.originalCostIncrease)),
    originalCostDecrease: calcSubtotal(rows.value.map((r) => r.originalCostDecrease)),
    originalCostEnd: calcSubtotal(rows.value.map((r) => r.originalCostEnd)),
    accDepBegin: calcSubtotal(rows.value.map((r) => r.accDepBegin)),
    accDepProvision: calcSubtotal(rows.value.map((r) => r.accDepProvision)),
    accDepReversal: calcSubtotal(rows.value.map((r) => r.accDepReversal)),
    accDepEnd: calcSubtotal(rows.value.map((r) => r.accDepEnd)),
    impairmentBegin: calcSubtotal(rows.value.map((r) => r.impairmentBegin)),
    impairmentProvision: calcSubtotal(rows.value.map((r) => r.impairmentProvision)),
    impairmentReversal: calcSubtotal(rows.value.map((r) => r.impairmentReversal)),
    impairmentEnd: calcSubtotal(rows.value.map((r) => r.impairmentEnd)),
    netValue: calcSubtotal(rows.value.map((r) => r.netValue)),
  }))

  const crossValidation = computed(() => {
    const costFromH1 = options?.crossSheetCostAudited?.value
      ?? _sumH1Audited(allResponses.value, 'H1-1-cost-rows')
    const depFromH1 = options?.crossSheetDepAudited?.value
      ?? _sumH1Audited(allResponses.value, 'H1-1-dep-rows')
    const costTotal = subtotalRow.value.costEndAud ?? 0
    const depTotal = subtotalRow.value.depEndAud ?? 0
    const impairTotal = subtotalRow.value.impairEndAud ?? 0
    return {
      costFromH1,
      depFromH1,
      costTotal,
      depTotal,
      impairTotal,
      costDiff: costTotal - costFromH1,
      depDiff: depTotal - depFromH1,
      hasCostWarning: Math.abs(costTotal - costFromH1) > 0.01 && (costFromH1 !== 0 || costTotal !== 0),
      hasDepWarning: Math.abs(depTotal - depFromH1) > 0.01 && (depFromH1 !== 0 || depTotal !== 0),
    }
  })

  /** 按类别汇总（对齐源模板「其中：」分类行） */
  const categorySubtotals = computed(() => {
    const map = new Map<string, { category: string; costEndAud: number; depEndAud: number; impairEndAud: number; netEndAud: number; count: number }>()
    for (const r of rows.value) {
      const cat = r.category || '未分类'
      const cur = map.get(cat) ?? { category: cat, costEndAud: 0, depEndAud: 0, impairEndAud: 0, netEndAud: 0, count: 0 }
      cur.costEndAud += r.costEndAud
      cur.depEndAud += r.depEndAud
      cur.impairEndAud += r.impairEndAud
      cur.netEndAud += r.netEndAud
      cur.count += 1
      map.set(cat, cur)
    }
    return Array.from(map.values())
  })

  function addRow(name: string, category?: string): void {
    rows.value.push(createEmptyDetailRow(name, category ?? ''))
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      _persist()
    }
  }

  function updateCell(rowId: string, field: keyof DetailRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 编辑 legacy 字段时回写未审主字段
    if (field === 'originalCostBegin') row.costBeginUnadj = _num(value)
    if (field === 'originalCostIncrease') row.costIncUnadj = _num(value)
    if (field === 'originalCostDecrease') row.costDecUnadj = _num(value)
    if (field === 'increaseReason') row.costIncMethod = _str(value)
    if (field === 'decreaseReason') row.costDecMethod = _str(value)
    if (field === 'accDepBegin') row.depBeginUnadj = _num(value)
    if (field === 'accDepProvision') row.depProvUnadj = _num(value)
    if (field === 'accDepReversal') row.depDispUnadj = _num(value)
    if (field === 'impairmentBegin') row.impairBeginUnadj = _num(value)
    if (field === 'impairmentProvision') row.impairProvUnadj = _num(value)
    if (field === 'impairmentReversal') row.impairDispUnadj = _num(value)
    recalcDetailRow(row)
    _persist()
  }

  function _persist(): void {
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  function applyConclusionTemplate(key: 'A' | 'B' | 'C'): void {
    saveConclusion(H1_2_CONCLUSION_TEMPLATES[key])
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  return {
    rows,
    activeSegment,
    selectedRowId,
    auditNote,
    auditConclusion,
    subtotalRow,
    crossValidation,
    categorySubtotals,
    addRow,
    removeRow,
    updateCell,
    saveNote,
    saveConclusion,
    applyConclusionTemplate,
    SEGMENT_CONFIGS,
    H1_2_CONCLUSION_TEMPLATES,
    H1_2_CATEGORY_OPTIONS,
  }
}

export default useH1Detail
