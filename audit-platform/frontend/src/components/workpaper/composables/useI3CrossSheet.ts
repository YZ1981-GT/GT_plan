/**
 * useI3CrossSheet — I3 商誉跨Sheet联动 computed 引擎
 *
 * 数据流：
 * - I3-2 明细 → I3-1 审定小计（原值/减值/净值；兼容 costAudited 滚动字段）
 * - I3-6 减值测试 → I3-1「本期减少(减值)」：使用 consolidatedGwImpairment（母公司份额）
 * - I3-7 DCF → I3-6 可收回金额
 * - I3-3 调整 → I3-1 AJE/RJE；按被投资单位拆分供 I3-2 回写
 * - I3-4 入账测算 → 供 I3-2 勾稽
 * - I3-6 按 CGU → 供 I3-2 本期计提回写
 */
import { computed, type ComputedRef, type Ref } from 'vue'

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I3-2 明细行（兼容旧字段 + 滚动字段） */
export interface I3DetailRowRaw {
  rowId?: string
  investee?: string
  acquisitionDate?: string
  consideration?: number
  mergerCost?: number
  netAssetFairValue?: number
  goodwillOriginal?: number
  costAudited?: number
  accImpairmentBegin?: number
  currentImpairment?: number
  accImpairmentEnd?: number
  impIncrease?: number
  impAudited?: number
  netValueEnd?: number
  goodwillNetValue?: number
  cguName?: string
  costAje?: number
  impAje?: number
  costIncrease?: number
  entryGoodwillCalc?: number
}

export interface I3AdjustmentRowRaw {
  rowId?: string
  description?: string
  category?: string
  entryType?: string
  reportItem?: string
  accountCode?: string
  accountName?: string
  noteItem?: string
  summary?: string
  debitAmount?: number
  creditAmount?: number
  debit?: number
  credit?: number
  indexRef?: string
  remark?: string
  /** 可选：匹配 I3-2 被投资单位 */
  investee?: string
}

export interface I3ImpairmentTestRowRaw {
  rowId?: string
  cguName?: string
  goodwillAmount?: number
  goodwillB1?: number
  minorityB2?: number
  cguBookValue?: number
  recoverableAmount?: number
  impairmentAmount?: number
  goodwillImpairment?: number
  /** 合并报表确认（母公司份额）— 优先用于 I3-1 / I3-2 */
  consolidatedGwImpairment?: number
  otherAssetImpairment?: number
  otherAllocations?: { name: string; amount: number }[]
}

export interface I3RecoverableResultRaw {
  rowId?: string
  cguName?: string
  name?: string
  fairValueLessDisposal?: number
  fairValueLessCost?: number
  valueInUse?: number
  recoverableAmount?: number
}

/** I3-7 → I3-6 可收回明细（公允净额 + 使用价值） */
export interface I3RecoverableDetail {
  fairValueLessDisposal?: number
  valueInUse?: number
  recoverableAmount: number
}

export interface I3InitialValueRowRaw {
  rowId?: string
  investee?: string
  projectName?: string
  mergerCost?: number
  netAssetFairValue?: number
  netAssetFV?: number
  equityRatio?: number
  goodwillAmount?: number
  bookedAmount?: number
  sameControl?: string
}

export interface I3DetailTotals {
  goodwillOriginalTotal: number
  accImpairmentTotal: number
  netValueTotal: number
  currentImpairmentTotal: number
  byCgu: Record<string, {
    goodwillOriginal: number
    accImpairment: number
    netValue: number
    currentImpairment: number
  }>
}

export interface I3ImpairmentResult {
  totalImpairment: number
  byCgu: Record<string, {
    impairmentAmount: number
    goodwillImpairment: number
    consolidatedGwImpairment: number
    otherImpairment: number
    recoverableAmount: number
  }>
}

export interface I3AdjustmentSync {
  totalAje: number
  totalRje: number
  /** 按被投资单位拆分的商誉科目 AJE 净额（借-贷），供 I3-2 costAje/impAje */
  byInvestee: Record<string, { costAje: number; impAje: number; net: number }>
}

export interface I3DisclosureData {
  [key: string]: number
}

export interface I3EntryVariance {
  investee: string
  entryCalc: number
  costIncrease: number
  costAudited: number
  diffVsIncrease: number
  diffVsAudited: number
}

/** I3-3 与 I3-2 账项调整列差异 */
export interface I3AjeVariance {
  investee: string
  detailCostAje: number
  detailImpAje: number
  adjCostAje: number
  adjImpAje: number
  costDiff: number
  impDiff: number
  /** I3-3 有金额但 I3-2 无该被投资单位行 */
  missingOnDetail: boolean
}

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _normName(s: string | undefined | null): string {
  return String(s || '').trim()
}

/**
 * 解析分录说明中的被投资单位：优先 investee 字段，否则从 description 匹配已知名称 / CGU
 */
export function resolveAdjustmentInvestee(
  row: I3AdjustmentRowRaw,
  knownInvestees: string[],
  cguToInvestees?: Record<string, string[]>,
): string {
  if (row.investee && _normName(row.investee)) return _normName(row.investee)
  const text = `${row.description || ''} ${row.summary || ''} ${row.remark || ''}`
  for (const name of knownInvestees) {
    if (name && text.includes(name)) return name
  }
  // 计提商誉减值-CGU名 → 若该 CGU 仅对应一家被投资单位则自动解析
  const m = text.match(/商誉减值[-—:：\s]*([^\s,，；;]+)/)
    || text.match(/商誉[-—:：\s]*([^\s,，；;]+)/)
  if (m) {
    const token = m[1].trim()
    if (cguToInvestees?.[token]?.length === 1) return cguToInvestees[token][0]
    if (knownInvestees.includes(token)) return token
    return token
  }
  return ''
}

/** 从 I3-3 分录汇总商誉科目 AJE（供回写 I3-2） */
export function aggregateGoodwillAjeByInvestee(
  rows: I3AdjustmentRowRaw[],
  knownInvestees: string[],
  cguToInvestees?: Record<string, string[]>,
): I3AdjustmentSync {
  let totalAje = 0
  let totalRje = 0
  const byInvestee: I3AdjustmentSync['byInvestee'] = {}

  for (const row of rows) {
    const debit = _getNum(row.debitAmount ?? row.debit)
    const credit = _getNum(row.creditAmount ?? row.credit)
    const netAmount = debit - credit
    const et = row.entryType || (row.category === '报表调整' ? 'RJE' : 'AJE')
    const code = String(row.accountCode || '')
    const name = String(row.accountName || '')
    const isGoodwill = code.startsWith('1711') || name.includes('商誉')
    if (!isGoodwill) continue

    if (et === 'AJE') totalAje += netAmount
    else if (et === 'RJE') totalRje += netAmount

    const inv = resolveAdjustmentInvestee(row, knownInvestees, cguToInvestees) || '未指定'
    if (!byInvestee[inv]) byInvestee[inv] = { costAje: 0, impAje: 0, net: 0 }
    byInvestee[inv].net += netAmount
    if (netAmount >= 0) {
      byInvestee[inv].costAje += netAmount
    } else {
      byInvestee[inv].impAje += Math.abs(netAmount)
    }
  }

  return { totalAje, totalRje, byInvestee }
}

export function useI3CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<I3DetailTotals>
  impairmentResult: ComputedRef<I3ImpairmentResult>
  adjustmentSync: ComputedRef<I3AdjustmentSync>
  disclosureAutoFill: ComputedRef<I3DisclosureData>
  recoverableByCgu: ComputedRef<Record<string, number>>
  recoverableDetailByCgu: ComputedRef<Record<string, I3RecoverableDetail>>
  initialValueRows: ComputedRef<I3InitialValueRowRaw[]>
  impairmentByCgu: ComputedRef<Record<string, number>>
  cguNameOptions: ComputedRef<string[]>
  entryVariances: ComputedRef<I3EntryVariance[]>
  ajeVariances: ComputedRef<I3AjeVariance[]>
  detailRows: ComputedRef<I3DetailRowRaw[]>
} {
  const detailRows = computed<I3DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('I3-2-rows')
    return safeParseRows<I3DetailRowRaw>(resp?.remark)
  })

  const adjustmentRows = computed<I3AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('I3-3-rows')
    return safeParseRows<I3AdjustmentRowRaw>(resp?.remark)
  })

  const impairmentTestRows = computed<I3ImpairmentTestRowRaw[]>(() => {
    const resp = allResponses.value.get('I3-6-rows')
    return safeParseRows<I3ImpairmentTestRowRaw>(resp?.remark)
  })

  const recoverableRows = computed<I3RecoverableResultRaw[]>(() => {
    const resp = allResponses.value.get('I3-7-rows')
    return safeParseRows<I3RecoverableResultRaw>(resp?.remark)
  })

  const initialValueRows = computed<I3InitialValueRowRaw[]>(() => {
    const resp = allResponses.value.get('I3-4-rows')
    return safeParseRows<I3InitialValueRowRaw>(resp?.remark)
  })

  const knownInvestees = computed(() =>
    detailRows.value.map(r => _normName(r.investee)).filter(Boolean),
  )

  const cguToInvestees = computed(() => {
    const map: Record<string, string[]> = {}
    for (const r of detailRows.value) {
      const cgu = _normName(r.cguName)
      const inv = _normName(r.investee)
      if (!cgu || !inv) continue
      if (!map[cgu]) map[cgu] = []
      if (!map[cgu].includes(inv)) map[cgu].push(inv)
    }
    return map
  })

  const detailTotals: ComputedRef<I3DetailTotals> = computed(() => {
    let goodwillOriginalTotal = 0
    let accImpairmentTotal = 0
    let netValueTotal = 0
    let currentImpairmentTotal = 0
    const byCgu: I3DetailTotals['byCgu'] = {}

    for (const row of detailRows.value) {
      const original = _getNum(row.costAudited ?? row.goodwillOriginal)
      const accImp = _getNum(row.impAudited ?? row.accImpairmentEnd ?? (row as any).accImpairment)
      const netRaw = row.goodwillNetValue ?? row.netValueEnd
      const netVal = netRaw != null && netRaw !== '' ? _getNum(netRaw) : (original - accImp)
      const curImp = _getNum(row.impIncrease ?? row.currentImpairment)

      goodwillOriginalTotal += original
      accImpairmentTotal += accImp
      netValueTotal += netVal
      currentImpairmentTotal += curImp

      const cgu = row.cguName || '未分配CGU'
      if (!byCgu[cgu]) {
        byCgu[cgu] = { goodwillOriginal: 0, accImpairment: 0, netValue: 0, currentImpairment: 0 }
      }
      byCgu[cgu].goodwillOriginal += original
      byCgu[cgu].accImpairment += accImp
      byCgu[cgu].netValue += netVal
      byCgu[cgu].currentImpairment += curImp
    }

    return { goodwillOriginalTotal, accImpairmentTotal, netValueTotal, currentImpairmentTotal, byCgu }
  })

  const impairmentResult: ComputedRef<I3ImpairmentResult> = computed(() => {
    let totalImpairment = 0
    const byCgu: I3ImpairmentResult['byCgu'] = {}

    for (const row of impairmentTestRows.value) {
      const cgu = row.cguName || '未命名CGU'
      const impairment = _getNum(row.impairmentAmount)
      const gwImpairment = _getNum(row.goodwillImpairment)
      // 优先合并确认；无 B2 时与全额商誉分摊相等
      const consol = row.consolidatedGwImpairment != null
        ? _getNum(row.consolidatedGwImpairment)
        : gwImpairment
      const otherFromAlloc = Array.isArray(row.otherAllocations)
        ? row.otherAllocations.reduce((s, a) => s + _getNum(a.amount), 0)
        : 0
      const otherImpairment = _getNum(row.otherAssetImpairment) || otherFromAlloc
      const recoverable = _getNum(row.recoverableAmount)

      totalImpairment += consol

      byCgu[cgu] = {
        impairmentAmount: impairment,
        goodwillImpairment: gwImpairment,
        consolidatedGwImpairment: consol,
        otherImpairment,
        recoverableAmount: recoverable,
      }
    }

    return { totalImpairment, byCgu }
  })

  /** I3-6 → I3-2：按 CGU 的合并确认商誉减值 */
  const impairmentByCgu: ComputedRef<Record<string, number>> = computed(() => {
    const map: Record<string, number> = {}
    for (const [cgu, v] of Object.entries(impairmentResult.value.byCgu)) {
      map[cgu] = v.consolidatedGwImpairment
    }
    return map
  })

  const recoverableDetailByCgu: ComputedRef<Record<string, I3RecoverableDetail>> = computed(() => {
    const result: Record<string, I3RecoverableDetail> = {}
    for (const row of recoverableRows.value) {
      const cgu = row.cguName || row.name || '未命名CGU'
      const fv = _getNum(row.fairValueLessDisposal ?? row.fairValueLessCost)
      const viu = _getNum(row.valueInUse)
      const rec = _getNum(row.recoverableAmount) || Math.max(fv, viu)
      result[cgu] = {
        fairValueLessDisposal: fv,
        valueInUse: viu,
        recoverableAmount: rec,
      }
    }
    return result
  })

  const recoverableByCgu: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}
    for (const [cgu, d] of Object.entries(recoverableDetailByCgu.value)) {
      result[cgu] = d.recoverableAmount
    }
    return result
  })

  const cguNameOptions: ComputedRef<string[]> = computed(() => {
    const set = new Set<string>()
    for (const r of detailRows.value) {
      if (_normName(r.cguName)) set.add(_normName(r.cguName))
    }
    for (const r of impairmentTestRows.value) {
      if (_normName(r.cguName)) set.add(_normName(r.cguName))
    }
    for (const r of recoverableRows.value) {
      const n = _normName(r.cguName || r.name)
      if (n) set.add(n)
    }
    return [...set].sort()
  })

  const adjustmentSync: ComputedRef<I3AdjustmentSync> = computed(() =>
    aggregateGoodwillAjeByInvestee(
      adjustmentRows.value,
      knownInvestees.value,
      cguToInvestees.value,
    ),
  )

  const entryVariances: ComputedRef<I3EntryVariance[]> = computed(() => {
    const list: I3EntryVariance[] = []
    const i4ByName = new Map<string, I3InitialValueRowRaw>()
    for (const r of initialValueRows.value) {
      const key = _normName(r.investee || r.projectName)
      if (key) i4ByName.set(key, r)
    }

    for (const row of detailRows.value) {
      const inv = _normName(row.investee)
      if (!inv) continue
      const i4 = i4ByName.get(inv)
      const entryCalc = i4
        ? _getNum(i4.goodwillAmount)
        : _getNum(row.entryGoodwillCalc)
      if (entryCalc === 0 && !i4) continue
      const costIncrease = _getNum(row.costIncrease)
      const costAudited = _getNum(row.costAudited ?? row.goodwillOriginal)
      list.push({
        investee: inv,
        entryCalc,
        costIncrease,
        costAudited,
        diffVsIncrease: entryCalc - costIncrease,
        diffVsAudited: entryCalc - costAudited,
      })
    }
    return list
  })

  /** I3-2 明细账项调整列 vs I3-3 商誉科目汇总 */
  const ajeVariances: ComputedRef<I3AjeVariance[]> = computed(() => {
    const list: I3AjeVariance[] = []
    const detailByInv = new Map<string, I3DetailRowRaw>()
    for (const row of detailRows.value) {
      const inv = _normName(row.investee)
      if (inv) detailByInv.set(inv, row)
    }
    for (const [inv, src] of Object.entries(adjustmentSync.value.byInvestee)) {
      if (inv === '未指定') {
        if (Math.abs(src.costAje) > 0.01 || Math.abs(src.impAje) > 0.01) {
          list.push({
            investee: '未指定',
            detailCostAje: 0,
            detailImpAje: 0,
            adjCostAje: src.costAje,
            adjImpAje: src.impAje,
            costDiff: src.costAje,
            impDiff: src.impAje,
            missingOnDetail: true,
          })
        }
        continue
      }
      const detail = detailByInv.get(inv)
      const dCost = detail ? _getNum(detail.costAje) : 0
      const dImp = detail ? _getNum(detail.impAje) : 0
      const costDiff = src.costAje - dCost
      const impDiff = src.impAje - dImp
      if (!detail || Math.abs(costDiff) > 0.01 || Math.abs(impDiff) > 0.01) {
        list.push({
          investee: inv,
          detailCostAje: dCost,
          detailImpAje: dImp,
          adjCostAje: src.costAje,
          adjImpAje: src.impAje,
          costDiff,
          impDiff,
          missingOnDetail: !detail,
        })
      }
    }
    return list
  })

  const disclosureAutoFill: ComputedRef<I3DisclosureData> = computed(() => {
    const result: I3DisclosureData = {}
    const totals = detailTotals.value
    result['disc_goodwill_original'] = totals.goodwillOriginalTotal
    result['disc_goodwill_impairment'] = totals.accImpairmentTotal
    result['disc_goodwill_net'] = totals.netValueTotal
    result['disc_goodwill_current_impairment'] = totals.currentImpairmentTotal

    const impResult = impairmentResult.value
    result['disc_cgu_count'] = Object.keys(impResult.byCgu).length
    result['disc_total_impairment'] = impResult.totalImpairment

    let totalRecoverable = 0
    let totalBookValue = 0
    for (const row of impairmentTestRows.value) {
      totalRecoverable += _getNum(row.recoverableAmount)
      totalBookValue += _getNum(row.cguBookValue)
    }
    result['disc_total_recoverable'] = totalRecoverable
    result['disc_total_book_value'] = totalBookValue

    const adjSync = adjustmentSync.value
    result['disc_aje_amount'] = adjSync.totalAje
    result['disc_rje_amount'] = adjSync.totalRje
    result['disc_investee_count'] = detailRows.value.length

    return result
  })

  return {
    detailTotals,
    impairmentResult,
    adjustmentSync,
    disclosureAutoFill,
    recoverableByCgu,
    recoverableDetailByCgu,
    initialValueRows,
    impairmentByCgu,
    cguNameOptions,
    entryVariances,
    ajeVariances,
    detailRows,
  }
}

export default useI3CrossSheet
