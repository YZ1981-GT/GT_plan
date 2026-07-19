/**
 * useG5BadDebtDetail — G5-3 坏账准备明细表（对齐致同 Excel 滚动态）
 *
 * 结构：按单项评估计提（动态「其中」行）+ 信用风险组合计提（动态组合行）+ 合计
 * 公式：
 *   期初审定 = 期初未审 + 期初账项调整
 *   期末未审 = 期初审定 + 计提 + 其他增加 − 转回 − 转销 − 其他减少
 *   期末审定 = 期末未审 + 期末账项调整
 *
 * 兼容旧版 ECL 双 Tab（closingBalance / adjustedProvision…）自动迁移。
 * ECL 测算仍在 G5-9/G5-10；本表聚焦坏账准备滚动与 G5-1 勾稽。
 */
import { ref, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum } from '@/composables/useG5FormulaEngine'

export type G5BadDebtCategory = 'individual' | 'portfolio'
export type G5BadDebtRowKind = 'section_header' | 'leaf' | 'subtotal' | 'total'
export type G5PortfolioType = 'business' | 'customer' | ''

/** 持久化 leaf（可序列化） */
export interface G5BadDebtLeaf {
  id: string
  seq: number
  category: G5BadDebtCategory
  item: string
  /** 组合细分：业务类型 / 客户类型 */
  portfolioType: G5PortfolioType
  openingUnadjusted: number
  openingAdjustment: number
  provisionIncrease: number
  otherIncrease: number
  reversal: number
  writeOff: number
  otherDecrease: number
  closingAdjustment: number
  reason: string
  /** 跨期稳定键（上年结转优先匹配） */
  crossSheetReceivableId?: string
}

/** 展示行（含公式派生与分区头） */
export interface G5BadDebtDisplayRow extends G5BadDebtLeaf {
  kind: G5BadDebtRowKind
  editable: boolean
  openingAudited: number
  closingUnadjusted: number
  closingAudited: number
  /** 兼容旧字段名，供下游汇总 */
  debtorOrGroup: string
  provisionMethod: 'individual' | 'group'
  adjustedProvision: number
  unadjustedProvision: number
  priorYearProvision: number
  currentYearProvision: number
  currentYearReversal: number
}

export interface G5BadDebtTotals {
  openingUnadjusted: number
  openingAdjustment: number
  openingAudited: number
  provisionIncrease: number
  otherIncrease: number
  reversal: number
  writeOff: number
  otherDecrease: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAudited: number
}

const uid = (prefix: string) =>
  `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

function round2(n: number): number {
  return Math.round((Number(n) || 0) * 100) / 100
}

export function computeMovement(leaf: Pick<
  G5BadDebtLeaf,
  | 'openingUnadjusted'
  | 'openingAdjustment'
  | 'provisionIncrease'
  | 'otherIncrease'
  | 'reversal'
  | 'writeOff'
  | 'otherDecrease'
  | 'closingAdjustment'
>): { openingAudited: number; closingUnadjusted: number; closingAudited: number } {
  const openingAudited = round2(
    parseNum(leaf.openingUnadjusted) + parseNum(leaf.openingAdjustment),
  )
  const closingUnadjusted = round2(
    openingAudited
    + parseNum(leaf.provisionIncrease)
    + parseNum(leaf.otherIncrease)
    - parseNum(leaf.reversal)
    - parseNum(leaf.writeOff)
    - parseNum(leaf.otherDecrease),
  )
  const closingAudited = round2(closingUnadjusted + parseNum(leaf.closingAdjustment))
  return { openingAudited, closingUnadjusted, closingAudited }
}

function emptyLeaf(
  category: G5BadDebtCategory,
  item: string,
  seq: number,
  portfolioType: G5PortfolioType = '',
): G5BadDebtLeaf {
  return {
    id: uid(category === 'portfolio' ? 'port' : 'ind'),
    seq,
    category,
    item,
    portfolioType: category === 'portfolio' ? (portfolioType || 'business') : '',
    openingUnadjusted: 0,
    openingAdjustment: 0,
    provisionIncrease: 0,
    otherIncrease: 0,
    reversal: 0,
    writeOff: 0,
    otherDecrease: 0,
    closingAdjustment: 0,
    reason: '',
  }
}

function toDisplayLeaf(leaf: G5BadDebtLeaf): G5BadDebtDisplayRow {
  const d = computeMovement(leaf)
  return {
    ...leaf,
    kind: 'leaf',
    editable: true,
    ...d,
    debtorOrGroup: leaf.item,
    provisionMethod: leaf.category === 'individual' ? 'individual' : 'group',
    adjustedProvision: d.closingAudited,
    unadjustedProvision: d.closingUnadjusted,
    priorYearProvision: d.openingAudited,
    currentYearProvision: parseNum(leaf.provisionIncrease),
    currentYearReversal: parseNum(leaf.reversal),
  }
}

function sumLeaves(leaves: G5BadDebtLeaf[]): G5BadDebtTotals {
  const openingUnadjusted = round2(leaves.reduce((s, r) => s + parseNum(r.openingUnadjusted), 0))
  const openingAdjustment = round2(leaves.reduce((s, r) => s + parseNum(r.openingAdjustment), 0))
  const provisionIncrease = round2(leaves.reduce((s, r) => s + parseNum(r.provisionIncrease), 0))
  const otherIncrease = round2(leaves.reduce((s, r) => s + parseNum(r.otherIncrease), 0))
  const reversal = round2(leaves.reduce((s, r) => s + parseNum(r.reversal), 0))
  const writeOff = round2(leaves.reduce((s, r) => s + parseNum(r.writeOff), 0))
  const otherDecrease = round2(leaves.reduce((s, r) => s + parseNum(r.otherDecrease), 0))
  const closingAdjustment = round2(leaves.reduce((s, r) => s + parseNum(r.closingAdjustment), 0))
  const openingAudited = round2(openingUnadjusted + openingAdjustment)
  const closingUnadjusted = round2(
    openingAudited + provisionIncrease + otherIncrease - reversal - writeOff - otherDecrease,
  )
  const closingAudited = round2(closingUnadjusted + closingAdjustment)
  return {
    openingUnadjusted,
    openingAdjustment,
    openingAudited,
    provisionIncrease,
    otherIncrease,
    reversal,
    writeOff,
    otherDecrease,
    closingUnadjusted,
    closingAdjustment,
    closingAudited,
  }
}

function headerRow(
  id: string,
  item: string,
  category: G5BadDebtCategory,
): G5BadDebtDisplayRow {
  const z = emptyLeaf(category, item, 0)
  return {
    ...z,
    id,
    item,
    kind: 'section_header',
    editable: false,
    openingAudited: 0,
    closingUnadjusted: 0,
    closingAudited: 0,
    debtorOrGroup: item,
    provisionMethod: category === 'individual' ? 'individual' : 'group',
    adjustedProvision: 0,
    unadjustedProvision: 0,
    priorYearProvision: 0,
    currentYearProvision: 0,
    currentYearReversal: 0,
  }
}

function aggregateDisplayRow(
  id: string,
  item: string,
  kind: 'subtotal' | 'total',
  category: G5BadDebtCategory,
  totals: G5BadDebtTotals,
): G5BadDebtDisplayRow {
  return {
    ...emptyLeaf(category, item, 0),
    id,
    item,
    kind,
    editable: false,
    openingUnadjusted: totals.openingUnadjusted,
    openingAdjustment: totals.openingAdjustment,
    openingAudited: totals.openingAudited,
    provisionIncrease: totals.provisionIncrease,
    otherIncrease: totals.otherIncrease,
    reversal: totals.reversal,
    writeOff: totals.writeOff,
    otherDecrease: totals.otherDecrease,
    closingUnadjusted: totals.closingUnadjusted,
    closingAdjustment: totals.closingAdjustment,
    closingAudited: totals.closingAudited,
    debtorOrGroup: item,
    provisionMethod: category === 'individual' ? 'individual' : 'group',
    adjustedProvision: totals.closingAudited,
    unadjustedProvision: totals.closingUnadjusted,
    priorYearProvision: totals.openingAudited,
    currentYearProvision: totals.provisionIncrease,
    currentYearReversal: totals.reversal,
  }
}

export function buildDisplayRows(leaves: G5BadDebtLeaf[]): G5BadDebtDisplayRow[] {
  const ind = leaves.filter((r) => r.category === 'individual')
  const port = leaves.filter((r) => r.category === 'portfolio')
  const indT = sumLeaves(ind)
  const portT = sumLeaves(port)
  const allT = sumLeaves(leaves)

  return [
    headerRow('hdr-ind', '按单项评估计提坏账准备', 'individual'),
    ...ind.map(toDisplayLeaf),
    aggregateDisplayRow('sub-ind', '单项小计', 'subtotal', 'individual', indT),
    headerRow('hdr-port', '按信用风险特征组合计提坏账准备', 'portfolio'),
    ...port.map(toDisplayLeaf),
    aggregateDisplayRow('sub-port', '组合小计', 'subtotal', 'portfolio', portT),
    aggregateDisplayRow('total', '合计', 'total', 'portfolio', allT),
  ]
}

/** 旧 ECL 行 → 滚动态 leaf */
export function migrateLegacyEclRows(arr: any[]): G5BadDebtLeaf[] {
  return arr.map((r, i) => {
    const category: G5BadDebtCategory =
      r.provisionMethod === 'individual' || r.category === 'individual'
        ? 'individual'
        : 'portfolio'
    const closing = parseNum(r.adjustedProvision ?? r.unadjustedProvision ?? r.closingAudited)
    const opening = parseNum(r.priorYearProvision ?? r.openingAudited ?? r.openingUnadjusted)
    const reversal = parseNum(r.currentYearReversal ?? r.reversal)
    const writeOff = parseNum(r.writeOff)
    const provisionIncrease = parseNum(
      r.currentYearProvision
      ?? r.provisionIncrease
      ?? Math.max(0, closing - opening + reversal + writeOff),
    )
    const openingUnadjusted = opening
    const openingAdjustment = 0
    const openingAudited = openingUnadjusted + openingAdjustment
    const otherIncrease = parseNum(r.otherIncrease)
    const otherDecrease = parseNum(r.otherDecrease)
    const provisionalClosingUnaudited =
      openingAudited + provisionIncrease + otherIncrease - reversal - writeOff - otherDecrease
    const closingAdjustment = round2(closing - provisionalClosingUnaudited)

    return {
      id: String(r.id || uid(category === 'portfolio' ? 'port' : 'ind')),
      seq: Number(r.seq) || i + 1,
      category,
      item: String(r.debtorOrGroup || r.item || r.debtor || `明细${i + 1}`),
      portfolioType:
        category === 'portfolio'
          ? (r.portfolioType === 'customer' ? 'customer' : 'business')
          : '',
      openingUnadjusted,
      openingAdjustment,
      provisionIncrease,
      otherIncrease,
      reversal,
      writeOff,
      otherDecrease,
      closingAdjustment,
      reason: String(r.reason || r.adjustmentDesc || r.remark || ''),
    }
  })
}

function isLegacyEclRow(r: any): boolean {
  return (
    r
    && typeof r === 'object'
    && ('closingBalance' in r || 'creditLossRate' in r || 'adjustedProvision' in r)
    && !('provisionIncrease' in r && 'openingUnadjusted' in r)
  )
}

function isMovementLeaf(r: any): boolean {
  return (
    r
    && typeof r === 'object'
    && ('openingUnadjusted' in r || 'provisionIncrease' in r || r.category === 'individual' || r.category === 'portfolio')
    && (r.item != null || r.debtorOrGroup != null || r.category)
  )
}

export function normalizeStoredLeaves(raw: unknown): G5BadDebtLeaf[] {
  if (!raw) return []
  let arr: any[] = []
  if (Array.isArray(raw)) arr = raw
  else if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      arr = Array.isArray(parsed) ? parsed : (parsed?.rows ?? [])
    } catch {
      return []
    }
  } else if (typeof raw === 'object' && Array.isArray((raw as any).rows)) {
    arr = (raw as any).rows
  }
  if (!arr.length) return []

  if (arr.every(isLegacyEclRow) || (arr.some(isLegacyEclRow) && !arr.some(isMovementLeaf))) {
    return migrateLegacyEclRows(arr)
  }

  return arr
    .filter((r) => r && (r.kind == null || r.kind === 'leaf' || r.category))
    .filter((r) => r.kind !== 'section_header' && r.kind !== 'subtotal' && r.kind !== 'total')
    .map((r, i) => {
      if (isLegacyEclRow(r) && !('openingUnadjusted' in r)) {
        return migrateLegacyEclRows([r])[0]
      }
      const category: G5BadDebtCategory =
        r.category === 'individual' || r.provisionMethod === 'individual'
          ? 'individual'
          : 'portfolio'
      return {
        id: String(r.id || uid(category === 'portfolio' ? 'port' : 'ind')),
        seq: Number(r.seq) || i + 1,
        category,
        item: String(r.item || r.debtorOrGroup || ''),
        portfolioType:
          category === 'portfolio'
            ? (r.portfolioType === 'customer' ? 'customer' : 'business')
            : '',
        openingUnadjusted: parseNum(r.openingUnadjusted),
        openingAdjustment: parseNum(r.openingAdjustment),
        provisionIncrease: parseNum(r.provisionIncrease),
        otherIncrease: parseNum(r.otherIncrease),
        reversal: parseNum(r.reversal),
        writeOff: parseNum(r.writeOff),
        otherDecrease: parseNum(r.otherDecrease),
        closingAdjustment: parseNum(r.closingAdjustment),
        reason: String(r.reason || ''),
        crossSheetReceivableId: r.crossSheetReceivableId
          ? String(r.crossSheetReceivableId)
          : undefined,
      } as G5BadDebtLeaf
    })
}

const EDITABLE_FIELDS: Array<keyof G5BadDebtLeaf> = [
  'item',
  'portfolioType',
  'openingUnadjusted',
  'openingAdjustment',
  'provisionIncrease',
  'otherIncrease',
  'reversal',
  'writeOff',
  'otherDecrease',
  'closingAdjustment',
  'reason',
]

export function useG5BadDebtDetail() {
  const leaves = ref<G5BadDebtLeaf[]>([])
  const activeRowIndex = ref(0)

  const displayRows = computed(() => buildDisplayRows(leaves.value))
  const groupRows = computed(() => leaves.value.filter((r) => r.category === 'portfolio'))
  const individualRows = computed(() => leaves.value.filter((r) => r.category === 'individual'))

  const totals = computed(() => {
    const t = sumLeaves(leaves.value)
    return {
      ...t,
      // 兼容旧合计栏
      adjustedBalance: 0,
      adjustedProvision: t.closingAudited,
      adjustedNetValue: 0,
      currentYearProvision: t.provisionIncrease,
      closingBalance: t.closingAudited,
      unadjustedProvision: t.closingUnadjusted,
    }
  })

  /** 兼容旧 API：扁平 leaf 列表（带派生字段） */
  const rows = computed({
    get: () => leaves.value.map(toDisplayLeaf),
    set: (v: G5BadDebtDisplayRow[]) => {
      leaves.value = v
        .filter((r) => r.kind === 'leaf' || !('kind' in r))
        .map((r, i) => ({
          id: r.id,
          seq: i + 1,
          category: r.category,
          item: r.item || r.debtorOrGroup || '',
          portfolioType: r.portfolioType || (r.category === 'portfolio' ? 'business' : ''),
          openingUnadjusted: parseNum(r.openingUnadjusted),
          openingAdjustment: parseNum(r.openingAdjustment),
          provisionIncrease: parseNum(r.provisionIncrease),
          otherIncrease: parseNum(r.otherIncrease),
          reversal: parseNum(r.reversal),
          writeOff: parseNum(r.writeOff),
          otherDecrease: parseNum(r.otherDecrease),
      closingAdjustment: parseNum(r.closingAdjustment),
      reason: String(r.reason || ''),
      crossSheetReceivableId: r.crossSheetReceivableId
        ? String(r.crossSheetReceivableId)
        : undefined,
        }))
    },
  })

  async function addRow(category: G5BadDebtCategory = 'portfolio') {
    const label = category === 'individual' ? '债务人名称' : '组合名称'
    const { value } = await ElMessageBox.prompt(`请输入${label}`, '新增行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    const seq = leaves.value.filter((r) => r.category === category).length + 1
    leaves.value = [
      ...leaves.value,
      emptyLeaf(category, value.trim(), seq, category === 'portfolio' ? 'business' : ''),
    ]
    renumber()
  }

  function removeRow(id: string) {
    leaves.value = leaves.value.filter((r) => r.id !== id)
    renumber()
  }

  function renumber() {
    let i = 1
    let p = 1
    leaves.value = leaves.value.map((r) => {
      if (r.category === 'individual') return { ...r, seq: i++ }
      return { ...r, seq: p++ }
    })
  }

  function updateCell(id: string, field: keyof G5BadDebtLeaf, value: string | number) {
    leaves.value = leaves.value.map((r) => {
      if (r.id !== id) return r
      if (!EDITABLE_FIELDS.includes(field)) return r
      if (field === 'item' || field === 'reason') {
        return { ...r, [field]: String(value ?? '') }
      }
      if (field === 'portfolioType') {
        const v = value === 'customer' ? 'customer' : value === 'business' ? 'business' : ''
        return { ...r, portfolioType: r.category === 'portfolio' ? (v || 'business') : '' }
      }
      return { ...r, [field]: parseNum(value) }
    })
  }

  /** 旧 API 兼容：对 display leaf 重算（实际由 computed 派生，无副作用） */
  function recalcRow(_row: G5BadDebtDisplayRow) {
    /* no-op：公式在 display 层即时派生 */
  }

  function loadRows(data: any[]): void {
    leaves.value = normalizeStoredLeaves(data)
  }

  function serializeRows(): string {
    return JSON.stringify(leaves.value)
  }

  return {
    leaves,
    rows,
    displayRows,
    activeRowIndex,
    activeTab: ref<'movement'>('movement'),
    groupRows,
    individualRows,
    totals,
    addRow,
    removeRow,
    updateCell,
    recalcRow,
    loadRows,
    serializeRows,
    computeMovement,
  }
}
