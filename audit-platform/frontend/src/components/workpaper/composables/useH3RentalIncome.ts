/**
 * useH3RentalIncome — H3-14 租金收入测算 composable
 *
 * 对齐致同 Excel《租金收入测算表 H3-14》核心逻辑：
 *   应计③ = 本期月数① × 月租金②；差异⑤ = 应计③ − 已计④；
 *   并保留数字底稿增强：月度12列、到期/空置管理、日后未折现租赁收款额。
 *
 * 持久化键：H3-14-contract-rows（兼容读取旧键 H3-14-rental-rows）
 */
import { ref, computed, watch, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal } from './useH3FormulaEngine'
import {
  type D43RentalAggregate,
  type H32AssetSeed,
  extractH32Assets,
  fetchD43RowsFromProject,
  matchD43ItemToContract,
} from './useH3RentalCrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export type RentalAssetCategory = 'building' | 'land'
export type RentalRowKind = 'data' | 'categorySubtotal' | 'grandTotal'

export interface RentalDisplayRow {
  rowKind: RentalRowKind
  rowId: string
  label: string
  category?: RentalAssetCategory
  /** contractRows 中的原始下标（仅 data 行） */
  dataIndex?: number
  contractAmount: number
  expectedRent: number
  bookedRent: number
  incomeDiff: number
  futureTotal: number
}

export interface RentalD43Reconcile {
  status: 'match' | 'mismatch' | 'unknown'
  d43Total: number | null
  h3BookedTotal: number
  diff: number
  itemCount: number
  note: string
}

export interface RentalPlReconcile {
  status: 'match' | 'mismatch' | 'unknown'
  tb6051Amount: number | null
  h3BookedTotal: number
  diff: number
  note: string
}

export interface RentalContractRow {
  rowId: string
  /** 资产类别：房屋建筑物 / 土地使用权（对齐 Excel 分组） */
  category: RentalAssetCategory
  assetName: string
  tenant: string
  leaseStart: string
  leaseEnd: string
  /** 租赁合同总金额 */
  contractAmount: number
  area: number
  /** ① 本期应计租赁月数 */
  monthsThisYear: number
  /** ② 月租金 */
  monthlyRent: number
  /** ③ = ①×② 本期应计租金收入（公式） */
  expectedRent: number
  /** ④ 账面已计租金收入 */
  bookedRent: number
  /** ⑤ = ③−④（正数=账面少计；对齐 Excel 公式 H−I，修正表头④−③笔误） */
  incomeDiff: number
  diffReason: string
  /** 租赁协议索引号 */
  contractIndex: string
  /** 资产负债表日后未折现租赁收款额 */
  futureY1: number
  futureY2: number
  futureY3: number
  futureY4: number
  futureY5: number
  futureAfter: number
  /** 日后收款合计（公式） */
  futureTotal: number
  /** 年租金 = 月租×12（附注联动） */
  annualRent: number
  vacancyRate: number
  /** 12个月实际入账（增强区） */
  monthlyActual: number[]
  renewalStatus: string
  vacancyForecast: string
  monthsToExpiry: number | null
}

export const RENTAL_CATEGORY_LABEL: Record<RentalAssetCategory, string> = {
  building: '房屋、建筑物',
  land: '土地使用权',
}

const ITEM_CONTRACT = 'H3-14-contract-rows'
const ITEM_CONTRACT_LEGACY = 'H3-14-rental-rows'
const ACCOUNT_6051 = '6051'

function _summarizeRows(rows: RentalContractRow[]) {
  return {
    contractAmount: calcSubtotal(rows.map((r) => r.contractAmount)),
    expectedRent: calcSubtotal(rows.map((r) => r.expectedRent)),
    bookedRent: calcSubtotal(rows.map((r) => r.bookedRent)),
    incomeDiff: calcSubtotal(rows.map((r) => r.incomeDiff)),
    futureTotal: calcSubtotal(rows.map((r) => r.futureTotal)),
  }
}

/** 构建带分类小计/合计的展示行（对齐 Excel H3-14 分组结构） */
export function buildRentalDisplayRows(rows: RentalContractRow[]): RentalDisplayRow[] {
  const result: RentalDisplayRow[] = []
  const categories: RentalAssetCategory[] = ['building', 'land']

  for (const cat of categories) {
    const catIndices: number[] = []
    rows.forEach((r, i) => { if (r.category === cat) catIndices.push(i) })
    if (!catIndices.length) continue

    for (const dataIndex of catIndices) {
      const r = rows[dataIndex]
      result.push({
        rowKind: 'data',
        rowId: r.rowId,
        label: '',
        category: cat,
        dataIndex,
        contractAmount: r.contractAmount,
        expectedRent: r.expectedRent,
        bookedRent: r.bookedRent,
        incomeDiff: r.incomeDiff,
        futureTotal: r.futureTotal,
      })
    }
    const sub = _summarizeRows(catIndices.map((i) => rows[i]))
    result.push({
      rowKind: 'categorySubtotal',
      rowId: `subtotal-${cat}`,
      label: `${RENTAL_CATEGORY_LABEL[cat]} 小计`,
      category: cat,
      ...sub,
    })
  }

  if (rows.length > 0) {
    result.push({
      rowKind: 'grandTotal',
      rowId: 'grand-total',
      label: '合计',
      ..._summarizeRows(rows),
    })
  }
  return result
}

/** 从 TB 行解析 6051 本期贷方净额（收入发生额） */
export function parseTb6051Amount(hit: any): number {
  if (!hit) return 0
  if (hit.audited_amount != null && hit.audited_amount !== '') return Number(hit.audited_amount) || 0
  const credit = Number(hit.credit_amount ?? hit.period_credit ?? 0)
  const debit = Number(hit.debit_amount ?? hit.period_debit ?? 0)
  return credit - debit
}

/** 会计年度内租期重叠月数（按日历月近似，0~12） */
export function calcMonthsInFiscalYear(start: string, end: string, year: number): number {
  if (!start || !end || !year) return 0
  const s = new Date(start)
  const e = new Date(end)
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime()) || e < s) return 0
  const yearStart = new Date(year, 0, 1)
  const yearEnd = new Date(year, 11, 31)
  const overlapStart = s > yearStart ? s : yearStart
  const overlapEnd = e < yearEnd ? e : yearEnd
  if (overlapEnd < overlapStart) return 0
  const months =
    (overlapEnd.getFullYear() - overlapStart.getFullYear()) * 12
    + (overlapEnd.getMonth() - overlapStart.getMonth())
    + 1
  return Math.min(12, Math.max(0, months))
}

/** 重算一行公式列（应计/差异/年租/日后合计/到期月数） */
export function recalcRentalRow(row: RentalContractRow, opts?: { fiscalYear?: number; fillMonthsIfEmpty?: boolean }): void {
  if (opts?.fillMonthsIfEmpty && !(row.monthsThisYear > 0) && row.leaseStart && row.leaseEnd) {
    const y = opts.fiscalYear ?? new Date().getFullYear()
    const m = calcMonthsInFiscalYear(row.leaseStart, row.leaseEnd, y)
    if (m > 0) row.monthsThisYear = m
  }

  // 月租金：合同总额÷租期月数（仅当月租金尚未录入时推算）
  const leaseTermMonths = (() => {
    if (!row.leaseStart || !row.leaseEnd) return 0
    const s = new Date(row.leaseStart)
    const e = new Date(row.leaseEnd)
    if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime()) || e < s) return 0
    return (e.getFullYear() - s.getFullYear()) * 12 + (e.getMonth() - s.getMonth()) + 1
  })()
  if (row.contractAmount > 0 && leaseTermMonths > 0 && !(row.monthlyRent > 0)) {
    row.monthlyRent = row.contractAmount / leaseTermMonths
  }

  row.expectedRent = (Number(row.monthsThisYear) || 0) * (Number(row.monthlyRent) || 0)
  row.incomeDiff = row.expectedRent - (Number(row.bookedRent) || 0)
  row.annualRent = (Number(row.monthlyRent) || 0) * 12
  row.futureTotal =
    (Number(row.futureY1) || 0)
    + (Number(row.futureY2) || 0)
    + (Number(row.futureY3) || 0)
    + (Number(row.futureY4) || 0)
    + (Number(row.futureY5) || 0)
    + (Number(row.futureAfter) || 0)
  row.monthsToExpiry = _monthsToExpiry(row.leaseEnd)
}

function _monthsToExpiry(leaseEnd: string): number | null {
  if (!leaseEnd) return null
  const t = new Date(leaseEnd).getTime()
  if (Number.isNaN(t)) return null
  return Math.max(0, Math.round((t - Date.now()) / (30 * 24 * 3600 * 1000)))
}

function _emptyMonthly(): number[] {
  return Array(12).fill(0)
}

export function createEmptyRentalRow(partial?: Partial<RentalContractRow>): RentalContractRow {
  const row: RentalContractRow = {
    rowId: partial?.rowId ?? `rc-${Date.now()}`,
    category: partial?.category ?? 'building',
    assetName: '',
    tenant: '',
    leaseStart: '',
    leaseEnd: '',
    contractAmount: 0,
    area: 0,
    monthsThisYear: 0,
    monthlyRent: 0,
    expectedRent: 0,
    bookedRent: 0,
    incomeDiff: 0,
    diffReason: '',
    contractIndex: '',
    futureY1: 0,
    futureY2: 0,
    futureY3: 0,
    futureY4: 0,
    futureY5: 0,
    futureAfter: 0,
    futureTotal: 0,
    annualRent: 0,
    vacancyRate: 0,
    monthlyActual: _emptyMonthly(),
    renewalStatus: '',
    vacancyForecast: '',
    monthsToExpiry: null,
    ...partial,
  }
  if (!Array.isArray(row.monthlyActual) || row.monthlyActual.length !== 12) {
    row.monthlyActual = _emptyMonthly()
  }
  recalcRentalRow(row)
  return row
}

/** 由月度实际合计回填已计租金（可选） */
export function sumMonthlyActual(row: RentalContractRow): number {
  return (row.monthlyActual || []).reduce((s, v) => s + (Number(v) || 0), 0)
}

export function useH3RentalIncome(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  measurementModel?: Ref<'cost' | 'fair_value'>
  htmlData?: Ref<any>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue, projectId, htmlData, measurementModel } = params

  const contractRows = ref<RentalContractRow[]>([])
  const tb6051Amount = ref<number | null>(null)
  const tb6051Loading = ref(false)
  const d43Aggregate = ref<D43RentalAggregate>({
    totalCurrent: 0,
    totalPrior: 0,
    items: [],
    loaded: false,
    message: '',
  })
  const d43Loading = ref(false)

  function loadData(): void {
    const raw = getValue(ITEM_CONTRACT) ?? getValue(ITEM_CONTRACT_LEGACY)
    contractRows.value = Array.isArray(raw) ? raw.map(_normContract) : []
  }

  function _normContract(raw: any): RentalContractRow {
    const monthlyActual: number[] = Array.isArray(raw?.monthlyActual)
      ? raw.monthlyActual.slice(0, 12).map((m: any) => Number(m) || 0)
      : _emptyMonthly()
    while (monthlyActual.length < 12) monthlyActual.push(0)

    const category: RentalAssetCategory =
      raw?.category === 'land' || raw?.category === '土地使用权' ? 'land' : 'building'

    const row = createEmptyRentalRow({
      rowId: raw?.rowId ?? `rc-${Math.random().toString(36).slice(2, 8)}`,
      category,
      assetName: raw?.assetName ?? '',
      tenant: raw?.tenant ?? raw?.lessee ?? '',
      leaseStart: raw?.leaseStart ?? '',
      leaseEnd: raw?.leaseEnd ?? '',
      contractAmount: Number(raw?.contractAmount) || 0,
      area: Number(raw?.area) || 0,
      monthsThisYear: Number(raw?.monthsThisYear ?? raw?.rentMonths) || 0,
      monthlyRent: Number(raw?.monthlyRent) || 0,
      bookedRent: Number(raw?.bookedRent ?? raw?.actualIncome) || 0,
      diffReason: raw?.diffReason ?? '',
      contractIndex: raw?.contractIndex ?? '',
      futureY1: Number(raw?.futureY1) || 0,
      futureY2: Number(raw?.futureY2) || 0,
      futureY3: Number(raw?.futureY3) || 0,
      futureY4: Number(raw?.futureY4) || 0,
      futureY5: Number(raw?.futureY5) || 0,
      futureAfter: Number(raw?.futureAfter) || 0,
      vacancyRate: Number(raw?.vacancyRate) || 0,
      monthlyActual,
      renewalStatus: raw?.renewalStatus ?? '',
      vacancyForecast: raw?.vacancyForecast ?? '',
    })
    recalcRentalRow(row, { fillMonthsIfEmpty: true })
    return row
  }

  const contractSummary = computed(() => {
    const expectedTotal = calcSubtotal(contractRows.value.map((r) => r.expectedRent))
    const bookedTotal = calcSubtotal(contractRows.value.map((r) => r.bookedRent))
    const diffTotal = expectedTotal - bookedTotal
    const futureTotal = calcSubtotal(contractRows.value.map((r) => r.futureTotal))
    const abnormalCount = contractRows.value.filter((r) => Math.abs(r.incomeDiff) > 0.01).length
    const byCategory = {
      building: _summarizeRows(contractRows.value.filter((r) => r.category === 'building')),
      land: _summarizeRows(contractRows.value.filter((r) => r.category === 'land')),
    }
    return {
      totalAnnualRent: calcSubtotal(contractRows.value.map((r) => r.annualRent)),
      expectedTotal,
      bookedTotal,
      diffTotal,
      futureTotal,
      abnormalCount,
      assetCount: contractRows.value.length,
      byCategory,
    }
  })

  const displayRows = computed(() => buildRentalDisplayRows(contractRows.value))

  const d43Reconcile = computed<RentalD43Reconcile>(() => {
    const h3BookedTotal = contractSummary.value.bookedTotal
    const agg = d43Aggregate.value
    if (!agg.loaded || !agg.items.length) {
      return {
        status: 'unknown',
        d43Total: null,
        h3BookedTotal,
        diff: 0,
        itemCount: 0,
        note: agg.message || '尚未加载 D4-3 租金分项，可点击「刷新D4-3」',
      }
    }
    const diff = h3BookedTotal - agg.totalCurrent
    const matched = Math.abs(diff) <= 0.01
    return {
      status: matched ? 'match' : 'mismatch',
      d43Total: agg.totalCurrent,
      h3BookedTotal,
      diff,
      itemCount: agg.items.length,
      note: matched
        ? `本表已计④与 D4-3 租金分项（${agg.items.length} 项）一致`
        : `本表已计④ ${h3BookedTotal.toFixed(2)} 与 D4-3 租金分项 ${agg.totalCurrent.toFixed(2)} 差异 ${diff.toFixed(2)}`,
    }
  })

  const plReconcile = computed<RentalPlReconcile>(() => {
    const h3BookedTotal = contractSummary.value.bookedTotal
    const tb = tb6051Amount.value
    if (tb == null) {
      return {
        status: 'unknown',
        tb6051Amount: null,
        h3BookedTotal,
        diff: 0,
        note: '尚未取到试算表 6051 其他业务收入发生额，可点击「刷新TB勾稽」',
      }
    }
    const diff = h3BookedTotal - tb
    const matched = Math.abs(diff) <= 0.01
    return {
      status: matched ? 'match' : 'mismatch',
      tb6051Amount: tb,
      h3BookedTotal,
      diff,
      note: matched
        ? '本表已计④合计与试算表 6051 本期发生额一致（若 6051 含非投资性房地产租金，仍应分项核对）'
        : `本表已计④合计 ${h3BookedTotal.toFixed(2)} 与 TB 6051 ${tb.toFixed(2)} 差异 ${diff.toFixed(2)}；${d43Reconcile.value.d43Total != null ? `D4-3租金分项 ${d43Reconcile.value.d43Total.toFixed(2)} 可供对照` : '请与 D4-3 等收入底稿分项勾稽'}`,
    }
  })

  const expiryAlerts = computed(() =>
    contractRows.value.filter((r) => r.monthsToExpiry != null && r.monthsToExpiry <= 3),
  )

  function addContractRow(assetName?: string, category: RentalAssetCategory = 'building'): void {
    contractRows.value.push(createEmptyRentalRow({
      assetName: assetName ?? '',
      category,
      rowId: `rc-${Date.now()}`,
    }))
    _persist()
  }

  function removeContractRow(index: number): void {
    contractRows.value.splice(index, 1)
    _persist()
  }

  function updateContractRow(index: number, _row?: any): void {
    const row = contractRows.value[index]
    if (!row) return
    row.monthlyRent = Number(row.monthlyRent) || 0
    row.area = Number(row.area) || 0
    row.monthsThisYear = Number(row.monthsThisYear) || 0
    row.bookedRent = Number(row.bookedRent) || 0
    row.contractAmount = Number(row.contractAmount) || 0
    ;(['futureY1', 'futureY2', 'futureY3', 'futureY4', 'futureY5', 'futureAfter'] as const).forEach((k) => {
      row[k] = Number(row[k]) || 0
    })
    recalcRentalRow(row)
    _persist()
  }

  function updateMonthlyData(index: number, _row?: any): void {
    const row = contractRows.value[index]
    if (!row) return
    row.monthlyActual = row.monthlyActual.map((m) => Number(m) || 0)
    // 月度累计回填已计（便于与 Excel「已计」口径一致）
    const monthlySum = sumMonthlyActual(row)
    if (monthlySum > 0) row.bookedRent = monthlySum
    recalcRentalRow(row)
    _persist()
  }

  /** 按合同起止日推算本期租赁月数 */
  function fillMonthsThisYear(fiscalYear?: number): number {
    const y = fiscalYear ?? new Date().getFullYear()
    let updated = 0
    for (const row of contractRows.value) {
      const m = calcMonthsInFiscalYear(row.leaseStart, row.leaseEnd, y)
      if (m > 0) {
        row.monthsThisYear = m
        recalcRentalRow(row)
        updated++
      }
    }
    if (updated) _persist()
    return updated
  }

  /** 从 H3-2 明细带入资产（名称/面积/类别） */
  function importFromH32(mode: 'addNew' | 'fillEmpty' = 'addNew') {
    const model = measurementModel?.value ?? 'cost'
    const seeds = extractH32Assets(getValue, model)
    if (!seeds.length) {
      return { added: 0, updated: 0, skipped: 0, message: 'H3-2 明细暂无资产，请先编制 H3-2' }
    }

    const norm = (s: string) => (s || '').trim().toLowerCase()
    const existingNames = new Set(contractRows.value.map((r) => norm(r.assetName)).filter(Boolean))
    let added = 0
    let updated = 0
    let skipped = 0

    if (mode === 'addNew') {
      for (const seed of seeds) {
        const key = norm(seed.assetName)
        if (!key || existingNames.has(key)) { skipped++; continue }
        contractRows.value.push(createEmptyRentalRow({
          assetName: seed.assetName,
          category: seed.category,
          area: seed.area,
          rowId: `rc-h32-${seed.rowId || Date.now()}`,
        }))
        existingNames.add(key)
        added++
      }
      if (added || updated) _persist()
      return {
        added,
        updated,
        skipped,
        message: added ? `已从 H3-2 新增 ${added} 份租赁合同行` : 'H3-2 资产均已存在于本表，未新增',
      }
    }

    for (const row of contractRows.value) {
      const seed = seeds.find((s) => norm(s.assetName) === norm(row.assetName))
      if (!seed) { skipped++; continue }
      let changed = false
      if (!row.assetName.trim() && seed.assetName) { row.assetName = seed.assetName; changed = true }
      if (!(row.area > 0) && seed.area > 0) { row.area = seed.area; changed = true }
      if (seed.category) { row.category = seed.category; changed = true }
      if (changed) { recalcRentalRow(row); updated++ } else skipped++
    }

    const unnamed = contractRows.value.filter((r) => !norm(r.assetName))
    const unusedSeeds = seeds.filter((s) => !existingNames.has(norm(s.assetName)))
    for (let i = 0; i < unnamed.length && i < unusedSeeds.length; i++) {
      const row = unnamed[i]
      const seed = unusedSeeds[i]
      row.assetName = seed.assetName
      row.category = seed.category
      row.area = seed.area
      recalcRentalRow(row)
      existingNames.add(norm(seed.assetName))
      updated++
    }

    if (added || updated) _persist()
    return {
      added: 0,
      updated,
      skipped,
      message: updated ? `已从 H3-2 补全 ${updated} 行资产信息` : '无需从 H3-2 补全（字段已填或无匹配资产）',
    }
  }

  /** 将 D4-3 租金分项同步至已计④ */
  function applyD43BookedRent(mode: 'fillEmpty' | 'overwrite' = 'fillEmpty') {
    const aggregate = d43Aggregate.value
    if (!aggregate.items.length) {
      return {
        updated: 0,
        unmatchedAmount: aggregate.totalCurrent,
        matchedAmount: 0,
        message: aggregate.message || 'D4-3 无租金分项',
      }
    }

    let updated = 0
    let matchedAmount = 0
    const matchedItemIds = new Set<string>()

    for (const row of contractRows.value) {
      const hit = matchD43ItemToContract(row.assetName, aggregate.items)
      if (!hit) continue
      matchedItemIds.add(hit.rowId)
      matchedAmount += hit.currentAudited
      if (mode === 'overwrite' || !(row.bookedRent > 0)) {
        row.bookedRent = hit.currentAudited
        recalcRentalRow(row)
        updated++
      }
    }

    if (contractRows.value.length === 1 && aggregate.items.length >= 1 && updated === 0) {
      const row = contractRows.value[0]
      if (mode === 'overwrite' || !(row.bookedRent > 0)) {
        row.bookedRent = aggregate.totalCurrent
        recalcRentalRow(row)
        updated++
        matchedAmount = aggregate.totalCurrent
        aggregate.items.forEach((it) => matchedItemIds.add(it.rowId))
      }
    }

    const unmatchedAmount = aggregate.items
      .filter((it) => !matchedItemIds.has(it.rowId))
      .reduce((s, it) => s + it.currentAudited, 0)

    if (updated) _persist()
    return {
      updated,
      unmatchedAmount,
      matchedAmount,
      message: updated
        ? `已从 D4-3 同步 ${updated} 行已计④（匹配 ${matchedAmount.toFixed(2)}）`
        : '未能按名称匹配 D4-3 项目，请手工核对或检查项目名称',
    }
  }

  /** 跨项目加载 D4-3 租金分项 */
  async function refreshD43Reconcile(): Promise<D43RentalAggregate> {
    d43Loading.value = true
    try {
      d43Aggregate.value = await fetchD43RowsFromProject(projectId.value)
      return d43Aggregate.value
    } finally {
      d43Loading.value = false
    }
  }

  /** 从 render-config 种子或 trial-balance API 取 6051 发生额 */
  async function refreshTbReconcile(): Promise<void> {
    tb6051Loading.value = true
    try {
      const seeded =
        htmlData?.value?.tb_values?.revenue_6051
        ?? htmlData?.value?.tb_values?.other_revenue_6051
        ?? htmlData?.value?.tb_values?.[`${ACCOUNT_6051}_period`]
      if (seeded != null && seeded !== '') {
        tb6051Amount.value = Number(seeded) || 0
        return
      }
      if (!projectId.value) {
        tb6051Amount.value = null
        return
      }
      const res = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { account_prefix: ACCOUNT_6051 },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data ?? res) ? (res?.data ?? res) : (res?.data?.items ?? [])
      const hit = list.find((r) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(ACCOUNT_6051),
      )
      tb6051Amount.value = hit ? parseTb6051Amount(hit) : null
    } catch {
      tb6051Amount.value = null
    } finally {
      tb6051Loading.value = false
    }
  }

  /** 生成审计说明草稿：应计/已计勾稽 + TB6051 + 差异事项 */
  function buildNoteDraft(): string {
    const s = contractSummary.value
    const pl = plReconcile.value
    const lines: string[] = [
      '1. 租赁收入与其他业务收入的勾稽情况',
      `   本期应计租金收入合计 ${s.expectedTotal.toFixed(2)}；账面已计合计 ${s.bookedTotal.toFixed(2)}；应计-已计差异 ${s.diffTotal.toFixed(2)}。`,
    ]
    if (pl.tb6051Amount != null) {
      lines.push(
        `   试算表 6051 其他业务收入本期发生额 ${pl.tb6051Amount.toFixed(2)}；与本表已计差异 ${pl.diff.toFixed(2)}。${pl.note}`,
      )
    } else {
      lines.push('   试算表 6051 发生额待取数，请与利润表/其他业务收入科目核对。')
    }
    const d43 = d43Reconcile.value
    if (d43.d43Total != null) {
      lines.push(
        `   D4-3 租金/租赁相关分项 ${d43.itemCount} 项，本期审定合计 ${d43.d43Total.toFixed(2)}；与本表已计差异 ${d43.diff.toFixed(2)}。`,
      )
      if (d43Aggregate.value.items.length) {
        d43Aggregate.value.items.forEach((it) => {
          lines.push(`     · ${it.item}：${it.currentAudited.toFixed(2)}`)
        })
      }
    }
    if (s.byCategory.building.bookedRent > 0 || s.byCategory.building.expectedRent > 0) {
      const b = s.byCategory.building
      lines.push(`   房屋、建筑物：应计 ${b.expectedRent.toFixed(2)}，已计 ${b.bookedRent.toFixed(2)}。`)
    }
    if (s.byCategory.land.bookedRent > 0 || s.byCategory.land.expectedRent > 0) {
      const l = s.byCategory.land
      lines.push(`   土地使用权：应计 ${l.expectedRent.toFixed(2)}，已计 ${l.bookedRent.toFixed(2)}。`)
    }
    const diffs = contractRows.value.filter((r) => Math.abs(r.incomeDiff) > 0.01)
    if (diffs.length) {
      lines.push('2. 差异事项')
      diffs.forEach((r, i) => {
        lines.push(
          `   ${i + 1}) ${r.assetName || '未命名'} / ${r.tenant || '-'}：应计 ${r.expectedRent.toFixed(2)}，已计 ${r.bookedRent.toFixed(2)}，差异 ${r.incomeDiff.toFixed(2)}。${r.diffReason ? `原因：${r.diffReason}` : '原因：待核实。'}`,
        )
      })
    } else {
      lines.push('2. 逐项测算应计与已计一致，未见重大差异。')
    }
    if (expiryAlerts.value.length) {
      lines.push(`3. 到期管理：${expiryAlerts.value.length} 份合同将于3个月内到期，需关注续租/空置对收入及估值的影响。`)
    }
    if (s.futureTotal > 0) {
      lines.push(`4. 资产负债表日后未折现租赁收款额合计 ${s.futureTotal.toFixed(2)}，可供附注租赁披露引用。`)
    }
    return lines.join('\n')
  }

  function _persist(): void {
    setValue(ITEM_CONTRACT, contractRows.value)
  }

  watch(allResponses, () => loadData(), { immediate: true })
  watch(projectId, () => {
    void refreshTbReconcile()
    void refreshD43Reconcile()
  }, { immediate: true })

  return {
    contractRows,
    displayRows,
    contractSummary,
    expiryAlerts,
    plReconcile,
    d43Reconcile,
    d43Aggregate,
    tb6051Loading,
    d43Loading,
    addContractRow,
    removeContractRow,
    updateContractRow,
    updateMonthlyData,
    fillMonthsThisYear,
    buildNoteDraft,
    refreshTbReconcile,
    refreshD43Reconcile,
    importFromH32,
    applyD43BookedRent,
    loadData,
  }
}

export default useH3RentalIncome
