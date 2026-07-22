/**
 * useH8Adjudication — H8-1 使用权资产、累计折旧及减值准备审定表
 *
 * 对齐致同 Excel「使用权资产、累计折旧及减值准备审定表 H8-1」：
 *   一、原值(1901) → 二、累计折旧(1902) → 三、减值准备(1903) → 四、净额
 *   列：期初{未审/账项调整/审定} | 期末{未审/账项调整/审定} | 变动额/变动率
 *
 * 数字化增强：
 * - 默认五类资产分类；审定=未审+账项调整；变动率≥30% 须说明
 * - 从 H8-3 回写期末账项调整（1901/1902 净额按未审权重分摊）
 * - H8-2 / H9 / TB 勾稽；TB 回写 1901+累计折旧
 * - 兼容旧存档：block cost|accDep + beginBalance/debit/credit/unadjusted/aje/rje
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcChangeRate,
  calcNetValue,
  calcSubtotal,
} from './useH8FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type H8AdjBlock = 'cost' | 'dep' | 'impair'

/** H8-1 审定表明细行（对齐 Excel 列 B–I） */
export interface H8AdjudicationRow {
  rowId: string
  /** 资产分类（房屋及建筑物等） */
  category: string
  /** @deprecated 旧字段 name，读档并入 category */
  name?: string
  block: H8AdjBlock
  beginUnadjusted: number
  beginAdjustment: number
  beginAudited: number
  endUnadjusted: number
  endAdjustment: number
  endAudited: number
  changeAmount: number
  changeRate: number | null
  isSignificant?: boolean
  isSubtotal?: boolean
  isEditable?: boolean
  /** 兼容旧过程结构字段 */
  beginBalance?: number
  debitAmount?: number
  creditAmount?: number
  endBalance?: number
  unadjusted?: number
  aje?: number
  rje?: number
  audited?: number
}

/** 四、净额派生行 */
export interface H8NetValueRow {
  rowId: string
  category: string
  beginNet: number
  endNet: number
  changeAmount: number
  changeRate: number | null
  isSignificant: boolean
  isSubtotal?: boolean
}

export interface H8QualitativeNotes {
  /** (1) 净值重大变动原因（变动率≥30%） */
  fluctuation: string
  /** (2) 简化处理（短期/低价值/可变付款额） */
  simplified: string
  /** (3) 转租收入 */
  sublease: string
}

export interface H8TbDiffRow {
  label: string
  scheduleAmount: number
  tbAmount: number
  difference: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 对齐 Excel 默认分类 */
export const H8_ROU_CATEGORIES = [
  '房屋及建筑物',
  '机器设备',
  '运输设备',
  '办公设备',
  '其他设备',
] as const

export const CHANGE_RATE_THRESHOLD = 30

const ROWS_KEY = 'H8-1-rows'
const COST_ROWS_KEY = 'H8-1-cost-rows'
const DEP_ROWS_KEY = 'H8-1-dep-rows'
const IMPAIR_ROWS_KEY = 'H8-1-impair-rows'
const NOTE_KEY = 'H8-1-audit-note'
const CONCLUSION_KEY = 'H8-1-audit-conclusion'
const QUAL_KEY = 'H8-1-qualitative-notes'

const COST_AUDITED_TOTAL_KEY = 'H8-1-cost-audited-total'
const DEP_AUDITED_TOTAL_KEY = 'H8-1-dep-audited-total'
const IMPAIR_AUDITED_TOTAL_KEY = 'H8-1-impair-audited-total'
const NET_AUDITED_KEY = 'H8-1-net-audited'
const COST_BEGIN_TOTAL_KEY = 'H8-1-cost-begin-total'
const DEP_BEGIN_TOTAL_KEY = 'H8-1-dep-begin-total'
const DEP_CURRENT_PROVISION_KEY = 'H8-1-dep-current-provision'

const CONCLUSION_TEMPLATES: Record<'A' | 'B' | 'C', string> = {
  A: '未见异常。经审定，使用权资产原值、累计折旧及减值准备在所有重大方面公允反映。',
  B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
  C: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
}

const EMPTY_NOTES: H8QualitativeNotes = {
  fluctuation: '',
  simplified: '',
  sublease: '',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

function _isSignificant(rate: number | null): boolean {
  return rate != null && Math.abs(rate) >= CHANGE_RATE_THRESHOLD
}

function _blankRow(category: string, block: H8AdjBlock): H8AdjudicationRow {
  return {
    rowId: `h81-${block}-${category}-${Math.random().toString(36).slice(2, 7)}`,
    category,
    block,
    beginUnadjusted: 0,
    beginAdjustment: 0,
    beginAudited: 0,
    endUnadjusted: 0,
    endAdjustment: 0,
    endAudited: 0,
    changeAmount: 0,
    changeRate: 0,
    isSignificant: false,
    isSubtotal: false,
    isEditable: true,
  }
}

function _applyFormulas(row: H8AdjudicationRow): void {
  row.beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAdjustment, 0)
  row.endAudited = calcAuditedAmount(row.endUnadjusted, row.endAdjustment, 0)
  row.changeAmount = row.endAudited - row.beginAudited
  row.changeRate = calcChangeRate(row.changeAmount, row.beginAudited)
  row.isSignificant = _isSignificant(row.changeRate)
  // 兼容旧字段 / CrossSheet / 披露
  row.beginBalance = row.beginAudited
  row.endBalance = row.endAudited
  row.unadjusted = row.endUnadjusted
  row.aje = row.endAdjustment
  row.rje = 0
  row.audited = row.endAudited
  row.name = row.category
}

function _sumBlock(detail: H8AdjudicationRow[], label: string, block: H8AdjBlock): H8AdjudicationRow {
  const rows = detail.filter((r) => !r.isSubtotal)
  const beginUnadjusted = calcSubtotal(rows.map((r) => r.beginUnadjusted))
  const beginAdjustment = calcSubtotal(rows.map((r) => r.beginAdjustment))
  const endUnadjusted = calcSubtotal(rows.map((r) => r.endUnadjusted))
  const endAdjustment = calcSubtotal(rows.map((r) => r.endAdjustment))
  const beginAudited = calcAuditedAmount(beginUnadjusted, beginAdjustment, 0)
  const endAudited = calcAuditedAmount(endUnadjusted, endAdjustment, 0)
  const changeAmount = endAudited - beginAudited
  const changeRate = calcChangeRate(changeAmount, beginAudited)
  return {
    rowId: `h81-${block}-subtotal`,
    category: label,
    block,
    beginUnadjusted,
    beginAdjustment,
    beginAudited,
    endUnadjusted,
    endAdjustment,
    endAudited,
    changeAmount,
    changeRate,
    isSignificant: _isSignificant(changeRate),
    isSubtotal: true,
    isEditable: false,
    beginBalance: beginAudited,
    endBalance: endAudited,
    unadjusted: endUnadjusted,
    aje: endAdjustment,
    rje: 0,
    audited: endAudited,
  }
}

function _normalizeCategory(raw: string): string {
  const s = String(raw || '').trim()
  if (!s) return '其他设备'
  if (s.includes('房屋') || s.includes('建筑')) return '房屋及建筑物'
  if (s.includes('机器') || s.includes('机械')) return '机器设备'
  if (s.includes('运输') || s.includes('车辆')) return '运输设备'
  if (s.includes('办公')) return '办公设备'
  if ((H8_ROU_CATEGORIES as readonly string[]).includes(s)) return s
  return s
}

/** H8-2 → H8-1 按类别汇总（book=未审数；full=审定数写入未审列） */
export interface H82CategoryAgg {
  category: string
  costBegin: number
  costEnd: number
  depBegin: number
  depEnd: number
  impairBegin: number
  impairEnd: number
  count: number
}

export type H81FillMode = 'book' | 'full'

export function aggregateH82ByCategory(
  detailRows: any[],
  mode: H81FillMode = 'book',
): { map: Record<string, H82CategoryAgg>; unmatchedCount: number; unmatchedCategories: string[] } {
  const map: Record<string, H82CategoryAgg> = {}
  for (const cat of H8_ROU_CATEGORIES) {
    map[cat] = {
      category: cat,
      costBegin: 0,
      costEnd: 0,
      depBegin: 0,
      depEnd: 0,
      impairBegin: 0,
      impairEnd: 0,
      count: 0,
    }
  }
  const unmatchedSet = new Set<string>()
  if (!Array.isArray(detailRows)) {
    return { map, unmatchedCount: 0, unmatchedCategories: [] }
  }

  for (const r of detailRows) {
    const rawLabel = String(r?.category ?? r?.assetCategory ?? r?.leaseType ?? '').trim()
    const cat = _normalizeCategory(rawLabel)
    if (!map[cat]) {
      map[cat] = {
        category: cat,
        costBegin: 0,
        costEnd: 0,
        depBegin: 0,
        depEnd: 0,
        impairBegin: 0,
        impairEnd: 0,
        count: 0,
      }
      if (!(H8_ROU_CATEGORIES as readonly string[]).includes(cat)) {
        unmatchedSet.add(rawLabel || cat)
      }
    }
    const a = map[cat]
    a.count += 1
    if (mode === 'full') {
      a.costBegin += Number(r.costBeginAud ?? r.costBeginUnadj) || 0
      a.costEnd += Number(r.costEndAud ?? r.costEndUnadj ?? r.initialAmount) || 0
      a.depBegin += Number(r.depBeginAud ?? r.depBeginUnadj ?? r.accDepBegin) || 0
      a.depEnd += Number(r.depEndAud ?? r.depEndUnadj ?? r.accDepEnd) || 0
      a.impairBegin += Number(r.impairBeginAud ?? r.impairBeginUnadj) || 0
      a.impairEnd += Number(r.impairEndAud ?? r.impairEndUnadj) || 0
    } else {
      a.costBegin += Number(r.costBeginUnadj) || 0
      a.costEnd +=
        Number(r.costEndUnadj)
        || Number(r.costEndAud)
        || Number(r.initialAmount)
        || 0
      a.depBegin += Number(r.depBeginUnadj ?? r.accDepBegin) || 0
      a.depEnd +=
        Number(r.depEndUnadj)
        || Number(r.depEndAud)
        || Number(r.accDepEnd)
        || ((Number(r.accDepBegin) || 0) + (Number(r.depCurrentPeriod) || Number(r.depProvUnadj) || 0))
      a.impairBegin += Number(r.impairBeginUnadj) || 0
      a.impairEnd += Number(r.impairEndUnadj ?? r.impairEndAud) || 0
    }
  }
  const unmatchedCategories = Array.from(unmatchedSet)
  return { map, unmatchedCount: unmatchedCategories.length, unmatchedCategories }
}

function _blockFromLegacy(raw: any): H8AdjBlock {
  if (raw.block === 'dep' || raw.block === 'accDep') return 'dep'
  if (raw.block === 'impair' || raw.block === 'impairment') return 'impair'
  return 'cost'
}

/** 兼容旧存档行 → 新列结构 */
export function normalizeH81Row(raw: any): H8AdjudicationRow | null {
  if (!raw || raw.isSubtotal || raw.isTotal) return null
  const block = _blockFromLegacy(raw)
  const category = _normalizeCategory(raw.category || raw.name || '')

  const hasNew = raw.beginUnadjusted != null || raw.endUnadjusted != null
  let beginUnadjusted = 0
  let beginAdjustment = 0
  let endUnadjusted = 0
  let endAdjustment = 0

  if (hasNew) {
    beginUnadjusted = Number(raw.beginUnadjusted) || 0
    beginAdjustment = Number(raw.beginAdjustment) || 0
    endUnadjusted = Number(raw.endUnadjusted) || 0
    endAdjustment = Number(raw.endAdjustment) || 0
  } else {
    // 旧：期初余额≈期初审定；未审≈期末未审；AJE+RJE→期末账项调整
    beginUnadjusted = Number(raw.beginBalance) || 0
    beginAdjustment = 0
    endUnadjusted = Number(raw.unadjusted ?? raw.endBalance) || 0
    endAdjustment = (Number(raw.aje) || 0) + (Number(raw.rje) || 0)
  }

  const row: H8AdjudicationRow = {
    rowId: raw.rowId ?? `h81-${block}-${Math.random().toString(36).slice(2, 8)}`,
    category,
    block,
    beginUnadjusted,
    beginAdjustment,
    beginAudited: 0,
    endUnadjusted,
    endAdjustment,
    endAudited: 0,
    changeAmount: 0,
    changeRate: 0,
    isSubtotal: false,
    isEditable: raw.isEditable ?? true,
    debitAmount: Number(raw.debitAmount ?? raw.debit) || 0,
    creditAmount: Number(raw.creditAmount ?? raw.credit) || 0,
  }
  _applyFormulas(row)
  return row
}

function _allocateEndAdj(details: H8AdjudicationRow[], net: number): void {
  if (!details.length || Math.abs(net) < 0.005) {
    for (const r of details) {
      r.endAdjustment = 0
      _applyFormulas(r)
    }
    return
  }
  const weights = details.map((r) => Math.abs(r.endUnadjusted) || 0)
  const weightSum = calcSubtotal(weights)
  if (weightSum < 0.005) {
    const each = _round2(net / details.length)
    let allocated = 0
    details.forEach((r, i) => {
      if (i === details.length - 1) r.endAdjustment = _round2(net - allocated)
      else {
        r.endAdjustment = each
        allocated = _round2(allocated + each)
      }
      _applyFormulas(r)
    })
    return
  }
  let allocated = 0
  details.forEach((r, i) => {
    if (i === details.length - 1) {
      r.endAdjustment = _round2(net - allocated)
    } else {
      const share = _round2((net * weights[i]) / weightSum)
      r.endAdjustment = share
      allocated = _round2(allocated + share)
    }
    _applyFormulas(r)
  })
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Adjudication(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly?: Ref<boolean>
  tbUnadjusted?: Ref<{ cost1901: number; dep1902: number; impair1903?: number }>
  onSave?: (itemId: string, value: any) => void
  onWritebackTB?: (audited1901: number, auditedAccDep: number, auditedImpair?: number) => Promise<void>
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const { allResponses, onSave, onWritebackTB, onPublishEvent } = params
  const isReadonly = params.isReadonly ?? ref(false)

  const costRows = ref<H8AdjudicationRow[]>([])
  const depRows = ref<H8AdjudicationRow[]>([])
  const impairRows = ref<H8AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const qualitativeNotes = ref<H8QualitativeNotes>({ ...EMPTY_NOTES })
  const tbScheduleUnaudited = ref({ cost: 0, dep: 0, impair: 0 })

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try {
      return typeof raw === 'string' ? JSON.parse(raw) : raw
    } catch {
      return null
    }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _defaultBlock(block: H8AdjBlock): H8AdjudicationRow[] {
    return H8_ROU_CATEGORIES.map((c) => {
      const row = _blankRow(c, block)
      _applyFormulas(row)
      return row
    })
  }

  function _loadBlock(key: string, block: H8AdjBlock): H8AdjudicationRow[] {
    const data = _getJson(key)
    if (Array.isArray(data) && data.length > 0) {
      return data
        .map(normalizeH81Row)
        .filter((r): r is H8AdjudicationRow => !!r && r.block === block)
    }
    return []
  }

  function load(): void {
    // 优先分块存档；否则兼容旧 H8-1-rows 合并数组
    let costs = _loadBlock(COST_ROWS_KEY, 'cost')
    let deps = _loadBlock(DEP_ROWS_KEY, 'dep')
    let impairs = _loadBlock(IMPAIR_ROWS_KEY, 'impair')

    if (!costs.length && !deps.length && !impairs.length) {
      const legacy = _getJson(ROWS_KEY)
      if (Array.isArray(legacy) && legacy.length > 0) {
        const all = legacy.map(normalizeH81Row).filter((r): r is H8AdjudicationRow => !!r)
        costs = all.filter((r) => r.block === 'cost')
        deps = all.filter((r) => r.block === 'dep')
        impairs = all.filter((r) => r.block === 'impair')
      }
    }

    costRows.value = costs.length ? costs : _defaultBlock('cost')
    depRows.value = deps.length ? deps : _defaultBlock('dep')
    impairRows.value = impairs.length ? impairs : _defaultBlock('impair')

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
    const notesRaw = _getJson(QUAL_KEY)
    qualitativeNotes.value = {
      fluctuation: String(notesRaw?.fluctuation ?? ''),
      simplified: String(notesRaw?.simplified ?? ''),
      sublease: String(notesRaw?.sublease ?? ''),
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Subtotals / display ───────────────────────────────────────────────────

  const costSubtotal = computed(() =>
    _sumBlock(costRows.value, '使用权资产原值合计', 'cost'),
  )
  const depSubtotal = computed(() => _sumBlock(depRows.value, '累计折旧合计', 'dep'))
  const impairSubtotal = computed(() =>
    _sumBlock(impairRows.value, '减值准备合计', 'impair'),
  )

  const costDisplayRows = computed(() => [
    ...costRows.value.filter((r) => !r.isSubtotal),
    costSubtotal.value,
  ])
  const depDisplayRows = computed(() => [
    ...depRows.value.filter((r) => !r.isSubtotal),
    depSubtotal.value,
  ])
  const impairDisplayRows = computed(() => [
    ...impairRows.value.filter((r) => !r.isSubtotal),
    impairSubtotal.value,
  ])

  const netAudited: ComputedRef<number> = computed(() =>
    calcNetValue(
      costSubtotal.value.endAudited,
      depSubtotal.value.endAudited,
      impairSubtotal.value.endAudited,
    ),
  )

  const netBeginAudited = computed(() =>
    calcNetValue(
      costSubtotal.value.beginAudited,
      depSubtotal.value.beginAudited,
      impairSubtotal.value.beginAudited,
    ),
  )

  const netRows = computed<H8NetValueRow[]>(() => {
    const byCat = (rows: H8AdjudicationRow[]) => {
      const m = new Map<string, H8AdjudicationRow>()
      for (const r of rows.filter((x) => !x.isSubtotal)) m.set(r.category, r)
      return m
    }
    const costs = byCat(costRows.value)
    const deps = byCat(depRows.value)
    const impairs = byCat(impairRows.value)
    const cats = [
      ...new Set([
        ...costs.keys(),
        ...deps.keys(),
        ...impairs.keys(),
        ...H8_ROU_CATEGORIES,
      ]),
    ]
    const detail: H8NetValueRow[] = cats.map((cat) => {
      const c = costs.get(cat)
      const d = deps.get(cat)
      const i = impairs.get(cat)
      const beginNet = calcNetValue(
        c?.beginAudited ?? 0,
        d?.beginAudited ?? 0,
        i?.beginAudited ?? 0,
      )
      const endNet = calcNetValue(
        c?.endAudited ?? 0,
        d?.endAudited ?? 0,
        i?.endAudited ?? 0,
      )
      const changeAmount = endNet - beginNet
      const changeRate = calcChangeRate(changeAmount, beginNet)
      return {
        rowId: `h81-net-${cat}`,
        category: cat,
        beginNet,
        endNet,
        changeAmount,
        changeRate,
        isSignificant: _isSignificant(changeRate),
        isSubtotal: false,
      }
    })
    const beginNet = calcSubtotal(detail.map((r) => r.beginNet))
    const endNet = calcSubtotal(detail.map((r) => r.endNet))
    const changeAmount = endNet - beginNet
    const changeRate = calcChangeRate(changeAmount, beginNet)
    detail.push({
      rowId: 'h81-net-subtotal',
      category: '净额合计',
      beginNet,
      endNet,
      changeAmount,
      changeRate,
      isSignificant: _isSignificant(changeRate),
      isSubtotal: true,
    })
    return detail
  })

  const significantNetChanges = computed(() =>
    netRows.value.filter((r) => !r.isSubtotal && r.isSignificant),
  )

  // ─── TB / Cross checks ─────────────────────────────────────────────────────

  const tbDiffRows = computed<H8TbDiffRow[]>(() => {
    const tb = params.tbUnadjusted?.value ?? {
      cost1901: 0,
      dep1902: 0,
      impair1903: 0,
    }
    const costTb = tb.cost1901 || tbScheduleUnaudited.value.cost
    const depTb = tb.dep1902 || tbScheduleUnaudited.value.dep
    const impairTb = (tb.impair1903 ?? 0) || tbScheduleUnaudited.value.impair
    return [
      {
        label: '使用权资产原值(1901)',
        scheduleAmount: costSubtotal.value.endUnadjusted,
        tbAmount: costTb,
        difference: costSubtotal.value.endUnadjusted - costTb,
      },
      {
        label: '累计折旧(1902)',
        scheduleAmount: depSubtotal.value.endUnadjusted,
        tbAmount: depTb,
        difference: depSubtotal.value.endUnadjusted - depTb,
      },
      {
        label: '减值准备(1903)',
        scheduleAmount: impairSubtotal.value.endUnadjusted,
        tbAmount: impairTb,
        difference: impairSubtotal.value.endUnadjusted - impairTb,
      },
      {
        label: '净额',
        scheduleAmount: calcNetValue(
          costSubtotal.value.endUnadjusted,
          depSubtotal.value.endUnadjusted,
          impairSubtotal.value.endUnadjusted,
        ),
        tbAmount: costTb - depTb - impairTb,
        difference:
          calcNetValue(
            costSubtotal.value.endUnadjusted,
            depSubtotal.value.endUnadjusted,
            impairSubtotal.value.endUnadjusted,
          ) -
          (costTb - depTb - impairTb),
      },
    ]
  })

  /** 兼容旧 UI：合并 rows */
  const rows = computed(() => [
    ...costRows.value,
    ...depRows.value,
    ...impairRows.value,
  ])
  const accDepRows = depRows
  const accDepSubtotal = depSubtotal

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistShape(list: H8AdjudicationRow[]) {
    return list
      .filter((r) => !r.isSubtotal)
      .map((r) => ({
        rowId: r.rowId,
        category: r.category,
        name: r.category,
        block: r.block,
        beginUnadjusted: r.beginUnadjusted,
        beginAdjustment: r.beginAdjustment,
        endUnadjusted: r.endUnadjusted,
        endAdjustment: r.endAdjustment,
        // 兼容旧消费者
        beginBalance: r.beginAudited,
        unadjusted: r.endUnadjusted,
        aje: r.endAdjustment,
        rje: 0,
        debitAmount: r.debitAmount ?? 0,
        creditAmount: r.creditAmount ?? 0,
      }))
  }

  function _writeTotals(): void {
    if (!onSave) return
    const pairs: Array<[string, number]> = [
      [COST_AUDITED_TOTAL_KEY, costSubtotal.value.endAudited],
      [DEP_AUDITED_TOTAL_KEY, depSubtotal.value.endAudited],
      [IMPAIR_AUDITED_TOTAL_KEY, impairSubtotal.value.endAudited],
      [NET_AUDITED_KEY, netAudited.value],
      [COST_BEGIN_TOTAL_KEY, costSubtotal.value.beginAudited],
      [DEP_BEGIN_TOTAL_KEY, depSubtotal.value.beginAudited],
      // 折旧本期计提近似：期末审定 − 期初审定（备抵增加）
      [DEP_CURRENT_PROVISION_KEY, depSubtotal.value.endAudited - depSubtotal.value.beginAudited],
      // 兼容旧 key
      ['H8-1-cost-audited', costSubtotal.value.endAudited],
      ['H8-1-accdep-audited', depSubtotal.value.endAudited],
    ]
    for (const [key, val] of pairs) {
      onSave(key, val)
      const existing = allResponses.value.get(key) || { item_id: key, conclusion: null, remark: null }
      allResponses.value.set(key, { ...existing, item_id: key, remark: String(val) })
    }
  }

  function _persist(): void {
    if (!onSave) return
    const costShaped = _persistShape(costRows.value)
    const depShaped = _persistShape(depRows.value)
    const impairShaped = _persistShape(impairRows.value)
    onSave(COST_ROWS_KEY, costShaped)
    onSave(DEP_ROWS_KEY, depShaped)
    onSave(IMPAIR_ROWS_KEY, impairShaped)
    // 兼容旧单一数组
    onSave(ROWS_KEY, [
      ...costShaped.map((r) => ({ ...r, block: 'cost' })),
      ...depShaped.map((r) => ({ ...r, block: 'accDep' })),
      ...impairShaped.map((r) => ({ ...r, block: 'impair' })),
    ])
    for (const [key, shaped] of [
      [COST_ROWS_KEY, costShaped],
      [DEP_ROWS_KEY, depShaped],
      [IMPAIR_ROWS_KEY, impairShaped],
    ] as const) {
      const existing = allResponses.value.get(key) || { item_id: key, conclusion: null, remark: null }
      allResponses.value.set(key, {
        ...existing,
        item_id: key,
        remark: JSON.stringify(shaped),
      })
    }
    _writeTotals()
  }

  // ─── Mutations ─────────────────────────────────────────────────────────────

  function _rowsOf(block: H8AdjBlock): Ref<H8AdjudicationRow[]> {
    if (block === 'cost') return costRows
    if (block === 'dep') return depRows
    return impairRows
  }

  function updateCell(
    block: H8AdjBlock,
    rowId: string,
    field: string,
    value: any,
  ): void {
    if (isReadonly.value) return
    const row = _rowsOf(block).value.find((r) => r.rowId === rowId)
    if (!row || row.isSubtotal) return

    if (field === 'category' || field === 'name') {
      row.category = _normalizeCategory(String(value ?? ''))
      row.name = row.category
    } else if (
      [
        'beginUnadjusted',
        'beginAdjustment',
        'endUnadjusted',
        'endAdjustment',
      ].includes(field)
    ) {
      ;(row as any)[field] = Number(value) || 0
    } else if (field === 'unadjusted') {
      row.endUnadjusted = Number(value) || 0
    } else if (field === 'aje') {
      row.endAdjustment = Number(value) || 0
    } else if (field === 'beginBalance') {
      row.beginUnadjusted = Number(value) || 0
    } else {
      return
    }
    _applyFormulas(row)
    _persist()
  }

  /** 兼容旧 UI：仅传 rowId 时在三块中查找 */
  function updateCellByRowId(rowId: string, field: string, value: any): void {
    const hit =
      costRows.value.find((r) => r.rowId === rowId) ||
      depRows.value.find((r) => r.rowId === rowId) ||
      impairRows.value.find((r) => r.rowId === rowId)
    if (!hit) return
    updateCell(hit.block, rowId, field, value)
  }

  function addRow(nameOrCategory: string, block: H8AdjBlock | 'accDep' = 'cost'): void {
    if (isReadonly.value || !nameOrCategory?.trim()) return
    const b: H8AdjBlock = block === 'accDep' ? 'dep' : (block as H8AdjBlock)
    const row = _blankRow(_normalizeCategory(nameOrCategory), b)
    _applyFormulas(row)
    _rowsOf(b).value.push(row)
    _persist()
  }

  function deleteRow(rowId: string): void {
    if (isReadonly.value) return
    for (const block of ['cost', 'dep', 'impair'] as H8AdjBlock[]) {
      const list = _rowsOf(block).value
      const idx = list.findIndex((r) => r.rowId === rowId)
      if (idx === -1) continue
      if (list[idx].isSubtotal) return
      list.splice(idx, 1)
      _persist()
      return
    }
  }

  /**
   * 从 H8-2 按类别汇总带入未审期初/期末。
   * mode=book：写入未审数，保留已有账项调整（留给 H8-3）。
   * mode=full：用审定数覆盖未审列，并清零账项调整。
   */
  function fillFromH82Detail(mode: H81FillMode = 'book'): {
    costFilled: number
    depFilled: number
    impairFilled: number
    unmatchedCount: number
    unmatchedCategories: string[]
    message: string
  } {
    const detail = _getJson('H8-2-rows')
    if (!Array.isArray(detail) || detail.length === 0) {
      return {
        costFilled: 0,
        depFilled: 0,
        impairFilled: 0,
        unmatchedCount: 0,
        unmatchedCategories: [],
        message: 'H8-2 暂无明细行可带入',
      }
    }
    const { map, unmatchedCount, unmatchedCategories } = aggregateH82ByCategory(detail, mode)

    // 确保五类骨架 + H8-2 出现的额外类别
    const ensureBlock = (list: Ref<H8AdjudicationRow[]>, block: H8AdjBlock) => {
      const existing = new Set(list.value.filter((r) => !r.isSubtotal).map((r) => r.category))
      for (const cat of Object.keys(map)) {
        if (!existing.has(cat) && map[cat].count > 0) {
          const row = _blankRow(cat, block)
          _applyFormulas(row)
          list.value.push(row)
        }
      }
      // 默认五类若被删光则补回
      if (!list.value.some((r) => !r.isSubtotal)) {
        list.value = _defaultBlock(block)
      }
    }
    ensureBlock(costRows, 'cost')
    ensureBlock(depRows, 'dep')
    ensureBlock(impairRows, 'impair')

    let costFilled = 0
    costRows.value = costRows.value.map((row) => {
      if (row.isSubtotal) return row
      const cat = _normalizeCategory(row.category)
      const a = map[cat]
      if (!a || a.count === 0) return row
      row.beginUnadjusted = a.costBegin
      row.endUnadjusted = a.costEnd
      if (mode === 'full') {
        row.beginAdjustment = 0
        row.endAdjustment = 0
      }
      _applyFormulas(row)
      costFilled += 1
      return row
    })

    let depFilled = 0
    depRows.value = depRows.value.map((row) => {
      if (row.isSubtotal) return row
      const cat = _normalizeCategory(row.category)
      const a = map[cat]
      if (!a || a.count === 0) return row
      row.beginUnadjusted = a.depBegin
      row.endUnadjusted = a.depEnd
      if (mode === 'full') {
        row.beginAdjustment = 0
        row.endAdjustment = 0
      }
      _applyFormulas(row)
      depFilled += 1
      return row
    })

    let impairFilled = 0
    impairRows.value = impairRows.value.map((row) => {
      if (row.isSubtotal) return row
      const cat = _normalizeCategory(row.category)
      const a = map[cat]
      if (!a || a.count === 0) return row
      row.beginUnadjusted = a.impairBegin
      row.endUnadjusted = a.impairEnd
      if (mode === 'full') {
        row.beginAdjustment = 0
        row.endAdjustment = 0
      }
      _applyFormulas(row)
      impairFilled += 1
      return row
    })

    _persist()
    const msg =
      `已从 H8-2 按类别带入：原值 ${costFilled} / 折旧 ${depFilled} / 减值 ${impairFilled}`
      + (unmatchedCount ? `（含 ${unmatchedCount} 笔非标准分类）` : '')
    return { costFilled, depFilled, impairFilled, unmatchedCount, unmatchedCategories, message: msg }
  }

  /** 从 H8-3 回写期末账项调整：1901→原值，1902→折旧（按未审权重分摊） */
  function syncEndAdjFromH83(
    costAjeNet?: number,
    costRjeNet?: number,
    depAjeNet?: number,
    depRjeNet?: number,
  ): { applied: boolean; message: string } {
    let cAje = Number(costAjeNet)
    let cRje = Number(costRjeNet)
    let dAje = Number(depAjeNet)
    let dRje = Number(depRjeNet)

    if (![cAje, cRje, dAje, dRje].every((n) => Number.isFinite(n))) {
      // 从 CrossSheet / 持久化 key 读取
      cAje = Number(allResponses.value.get('H8-3-aje-net')?.remark) || 0
      cRje = Number(allResponses.value.get('H8-3-rje-net')?.remark) || 0
      dAje = Number(allResponses.value.get('H8-3-dep-aje-net')?.remark) || 0
      dRje = Number(allResponses.value.get('H8-3-dep-rje-net')?.remark) || 0

      // 优先从行汇总
      const adjRows = _getJson('H8-3-rows')
      if (Array.isArray(adjRows) && adjRows.length > 0) {
        cAje = 0
        cRje = 0
        dAje = 0
        dRje = 0
        for (const r of adjRows) {
          const code = String(r.accountCode || '')
          const debit = Number(r.debitAmount ?? r.debit) || 0
          const credit = Number(r.creditAmount ?? r.credit) || 0
          const net = debit - credit
          const isRje =
            r.category === '报表调整' ||
            String(r.entryType || r.adjustType || '').toUpperCase() === 'RJE'
          if (code === '1901' || code.startsWith('1901')) {
            if (isRje) cRje += net
            else cAje += net
          }
          if (code === '1902' || code.startsWith('1902')) {
            if (isRje) dRje += net
            else dAje += net
          }
        }
      }
    }

    const costNet = cAje + cRje
    const depNet = dAje + dRje
    if (Math.abs(costNet) < 0.005 && Math.abs(depNet) < 0.005) {
      return { applied: false, message: 'H8-3 暂无 1901/1902 调整净额' }
    }

    if (Math.abs(costNet) >= 0.005) {
      _allocateEndAdj(
        costRows.value.filter((r) => !r.isSubtotal),
        costNet,
      )
    }
    if (Math.abs(depNet) >= 0.005) {
      _allocateEndAdj(
        depRows.value.filter((r) => !r.isSubtotal),
        depNet,
      )
    }
    _persist()
    return {
      applied: true,
      message: `已从 H8-3 回写期末账项调整：1901 ${costNet.toLocaleString('zh-CN')} / 1902 ${depNet.toLocaleString('zh-CN')}`,
    }
  }

  /** 兼容旧 API */
  function syncAjeRjeFromAdjustment(ajeNet: number, rjeNet: number): void {
    syncEndAdjFromH83(ajeNet, rjeNet, 0, 0)
  }

  async function publishAdjudicated(): Promise<void> {
    _persist()
    if (onWritebackTB) {
      await onWritebackTB(
        costSubtotal.value.endAudited,
        depSubtotal.value.endAudited,
        impairSubtotal.value.endAudited,
      )
    }
    try {
      onPublishEvent?.('substantive:adjudicated', {
        wpCode: 'H8',
        costAudited: costSubtotal.value.endAudited,
        depAudited: depSubtotal.value.endAudited,
        impairAudited: impairSubtotal.value.endAudited,
        netAudited: netAudited.value,
      })
      window.dispatchEvent(
        new CustomEvent('substantive:adjudicated', {
          detail: {
            wpCode: 'H8',
            costAudited: costSubtotal.value.endAudited,
            depAudited: depSubtotal.value.endAudited,
            netAudited: netAudited.value,
          },
        }),
      )
    } catch {
      /* silent */
    }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    onSave?.(CONCLUSION_KEY, conclusion)
  }

  function saveQualitativeNotes(): void {
    onSave?.(QUAL_KEY, { ...qualitativeNotes.value })
  }

  function applyConclusionTemplate(key: 'A' | 'B' | 'C'): void {
    auditConclusion.value = CONCLUSION_TEMPLATES[key]
    onSave?.(CONCLUSION_KEY, auditConclusion.value)
  }

  function applySignificantFluctuationDraft(): void {
    const items = significantNetChanges.value
    if (!items.length) return
    const lines = items.map((r) => {
      const rate =
        r.changeRate == null
          ? '—'
          : `${r.changeRate > 0 ? '+' : ''}${r.changeRate.toFixed(2)}%`
      return `${r.category}：变动额 ${r.changeAmount.toLocaleString('zh-CN')}（${rate}）`
    })
    const draft = `净值变动率≥${CHANGE_RATE_THRESHOLD}%：\n${lines.join('\n')}`
    qualitativeNotes.value = {
      ...qualitativeNotes.value,
      fluctuation: qualitativeNotes.value.fluctuation?.trim()
        ? `${qualitativeNotes.value.fluctuation.trim()}\n${draft}`
        : draft,
    }
    saveQualitativeNotes()
  }

  function setTbScheduleAmounts(cost: number, dep: number, impair = 0): void {
    tbScheduleUnaudited.value = { cost, dep, impair }
  }

  /** 与 H8-2 明细期末审定勾稽 */
  const detailCrossCheck = computed(() => {
    const raw = _getJson('H8-2-rows')
    const detailRows = Array.isArray(raw) ? raw : []
    let cost = 0
    let dep = 0
    let impair = 0
    let net = 0
    for (const r of detailRows) {
      cost += Number(r.costEndAud) || Number(r.initialAmount) || Number(r.rouAmount) || 0
      dep += Number(r.depEndAud) || Number(r.accDepEnd) || 0
      impair += Number(r.impairEndAud) || Number(r.impairmentEnd) || 0
      net += Number(r.netEndAud) || Number(r.netValue) || 0
    }
    if (net === 0 && (cost || dep || impair)) net = cost - dep - impair
    const costAdj = costSubtotal.value.endAudited
    const depAdj = depSubtotal.value.endAudited
    const impairAdj = impairSubtotal.value.endAudited
    const netAdj = netAudited.value
    const warn = (a: number, b: number) => Math.abs(a - b) > 0.01 && (a !== 0 || b !== 0)
    const empty = detailRows.length === 0 && costAdj === 0
    return {
      detailCost: cost,
      detailDep: dep,
      detailImpair: impair,
      detailNet: net,
      costDiff: costAdj - cost,
      depDiff: depAdj - dep,
      impairDiff: impairAdj - impair,
      netDiff: netAdj - net,
      hasCostWarning: warn(costAdj, cost),
      hasDepWarning: warn(depAdj, dep),
      hasImpairWarning: warn(impairAdj, impair),
      hasNetWarning: warn(netAdj, net),
      isEmpty: empty,
      isConsistent:
        !empty
        && !warn(costAdj, cost)
        && !warn(depAdj, dep)
        && !warn(impairAdj, impair)
        && !warn(netAdj, net),
      detailCount: detailRows.length,
    }
  })

  /** H8-2 非标准类别清单（带入后金额已归一，但需人工复核分类名） */
  const h82CategoryGap = computed(() => {
    const raw = _getJson('H8-2-rows')
    const detailRows = Array.isArray(raw) ? raw : []
    const { unmatchedCount, unmatchedCategories } = aggregateH82ByCategory(detailRows, 'book')
    return { unmatchedCount, unmatchedCategories }
  })

  function save(): void {
    _persist()
  }

  return {
    rows,
    costRows,
    depRows,
    impairRows,
    accDepRows,
    costDisplayRows,
    depDisplayRows,
    impairDisplayRows,
    costSubtotal,
    depSubtotal,
    impairSubtotal,
    accDepSubtotal,
    netRows,
    netAudited,
    netBeginAudited,
    significantNetChanges,
    tbDiffRows,
    detailCrossCheck,
    h82CategoryGap,
    auditNote,
    auditConclusion,
    qualitativeNotes,
    categoryOptions: H8_ROU_CATEGORIES,
    CHANGE_RATE_THRESHOLD,
    updateCell,
    updateCellByRowId,
    addRow,
    deleteRow,
    save,
    load,
    publishAdjudicated,
    saveNote,
    saveConclusion,
    saveQualitativeNotes,
    applyConclusionTemplate,
    applySignificantFluctuationDraft,
    syncEndAdjFromH83,
    syncAjeRjeFromAdjustment,
    setTbScheduleAmounts,
    fillFromH82Detail,
  }
}

export default useH8Adjudication
