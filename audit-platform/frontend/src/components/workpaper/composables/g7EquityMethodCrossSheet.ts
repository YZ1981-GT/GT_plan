/**
 * G7 权益法组跨底稿读写辅助（G7-4 / G7-6 / G7-14）
 */
import {
  calcAdjustedNetProfit,
  calcEquityMethodBalance,
  calcEquityShare,
  calcIncomeDifference,
  calcLteiBookBalance,
  calcNetAssetShareVariance,
  calcUnexplainedVariance,
  calcOpeningReconVariance,
  calcClosingReconVariance,
  parseNum,
} from './useG7EquityMethodFormulaEngine'
import { normalizeG7DetailRows } from './g7DetailModel'

export const G7_4_ROWS_KEY = 'G7-4-rows'
export const G7_5_ROWS_KEY = 'G7-5-rows'
export const G7_6_ROWS_KEY = 'G7-6-rows'
export const G7_13_ROWS_KEY = 'G7-13-rows'
export const G7_14_SECTION_KEY = 'G7-14-equity-method-calc'
/** 与导入导出键对齐；页面保存时应与 SECTION 原子双写 */
export const G7_14_ROWS_KEY = 'G7-14-rows'
export const G7_15_SECTION_KEY = 'G7-15-internal-transaction'
export const G7_15_ROWS_KEY = 'G7-15-rows'
/** 页面 section 键（兼容旧数据）；导入导出/合并 linkage 认 ROWS_KEY */
export const G7_17_SECTION_KEY = 'G7-17-impairment-test'
export const G7_17_ROWS_KEY = 'G7-17-rows'
export const G7_16_ROWS_KEY = 'G7-16-rows'
export const G7_2_ROWS_KEY = 'G7-2-rows'

export function parseChecklistJson(value: unknown): any | null {
  if (value == null || value === '') return null
  if (typeof value === 'object') return value
  if (typeof value !== 'string') return null
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

function extractFlatRows(parsed: unknown): any[] {
  if (Array.isArray(parsed)) return parsed
  if (parsed && typeof parsed === 'object' && Array.isArray((parsed as any).rows)) {
    return (parsed as any).rows
  }
  return []
}

function groupsFromFlatRows(rows: any[]): { investeeName: string; rows: any[] }[] {
  const byName = new Map<string, any[]>()
  for (const r of rows) {
    const name = normalizeInvesteeKey(r?.investeeName ?? r?.investee_name) || '未命名'
    if (!byName.has(name)) byName.set(name, [])
    byName.get(name)!.push(r)
  }
  return [...byName.entries()].map(([investeeName, rs]) => ({ investeeName, rows: rs }))
}

/**
 * 从 checklist 读 G7-14 页面 payload：优先 SECTION（含 NA/GWF/结论/重要性）；
 * SECTION 空而 ROWS 有数据时，用 ROWS 组装最小 payload，避免 G7-6 等外推覆盖空壳。
 */
export function resolveG714PayloadFromChecklist(
  getConclusion: (itemId: string) => unknown,
): any | null {
  const section = parseChecklistJson(getConclusion(G7_14_SECTION_KEY))
  const sectionObj =
    section && typeof section === 'object' && !Array.isArray(section) ? section : null
  const sectionRows = extractFlatRows(sectionObj)
  const sectionGroups = Array.isArray(sectionObj?.groups) ? sectionObj!.groups : []
  const sectionHasBody =
    sectionRows.length > 0
    || sectionGroups.some((g: any) => Array.isArray(g?.rows) && g.rows.length > 0)
    || Boolean(sectionObj && (
      sectionObj.materialityLevel != null
      || sectionObj.conclusion
      || (Array.isArray(sectionObj.netAssetAdjustments) && sectionObj.netAssetAdjustments.length > 0)
      || (Array.isArray(sectionObj.goodwillFvDetails) && sectionObj.goodwillFvDetails.length > 0)
    ))

  if (sectionHasBody && sectionObj) return sectionObj

  const rows = extractFlatRows(parseChecklistJson(getConclusion(G7_14_ROWS_KEY)))
  if (!rows.length) return sectionObj

  const base = sectionObj
    ? { ...sectionObj }
    : {
        materialityLevel: 0,
        conclusion: '',
        netAssetAdjustments: [],
        goodwillFvDetails: [],
      }
  base.rows = rows
  if (!Array.isArray(base.groups) || base.groups.length === 0) {
    base.groups = groupsFromFlatRows(rows)
  }
  return base
}

type G714ResponseLike = { conclusion?: unknown } | null | undefined

/** Map + responses_snapshot 联合取值，供各表外推 G7-14 使用 */
export function makeG714ConclusionGetter(
  data?: Map<string, G714ResponseLike> | null,
  snapshot?: Record<string, G714ResponseLike> | null,
): (itemId: string) => unknown {
  return (itemId: string) =>
    data?.get(itemId)?.conclusion
    ?? snapshot?.[itemId]?.conclusion
}

export function flattenG714Rows(payload: Record<string, any> | null | undefined): any[] {
  if (!payload || typeof payload !== 'object') return []
  if (Array.isArray(payload.rows) && payload.rows.length > 0) return payload.rows
  if (Array.isArray(payload.groups)) {
    return payload.groups.flatMap((g: any) => (Array.isArray(g?.rows) ? g.rows : []))
  }
  return []
}

/**
 * G7-14 双写：SECTION=整页 JSON；ROWS=扁平 rows[]（IE/consol 认后者）。
 */
export function buildG714DualWriteItems(payload: Record<string, any>): Array<{
  itemId: string
  data: { conclusion: string; remark: string | null }
}> {
  const rows = flattenG714Rows(payload)
  payload.rows = rows
  if ((!Array.isArray(payload.groups) || payload.groups.length === 0) && rows.length > 0) {
    payload.groups = groupsFromFlatRows(rows)
  }
  const pageJson = JSON.stringify(payload)
  const rowsJson = JSON.stringify(rows)
  return [
    { itemId: G7_14_SECTION_KEY, data: { conclusion: pageJson, remark: null } },
    { itemId: G7_14_ROWS_KEY, data: { conclusion: rowsJson, remark: rowsJson } },
  ]
}

/** 与后端 g7_consol_linkage_service.G714_UNMAPPED_FIELDS 对齐，供 Tab4 明示 */
export const G714_CONSOL_UNMAPPED_FIELD_LABELS: Record<string, string> = {
  nonControllingInterest: '少数股东权益（展示项，不计入归母净资产）',
  fvDiffAtAcquisition: '取得投资时公允价值差额（合并净资产表无对应行）',
  otherProfitAdj: '其他需调整损益的项目（合并净资产表无对应行）',
  openingFvDiffCumulative: '期初累计公允价值调整（合并净资产表无对应行）',
  unrealizedInternalElim: '未实现内部交易损益（合并净资产表无对应行）',
}

/** 取第一个已定义的数值（0 有效；跳过 null/undefined/''） */
export function pickDefinedNum(...candidates: unknown[]): number {
  for (const c of candidates) {
    if (c === null || c === undefined || c === '') continue
    if (typeof c === 'string' && c.trim() === '') continue
    const n = typeof c === 'number' ? c : Number(typeof c === 'string' ? c.trim() : c)
    if (Number.isFinite(n)) return n
  }
  return 0
}

function hasDefinedField(obj: Record<string, unknown>, ...keys: string[]): boolean {
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(obj, key)) continue
    const v = obj[key]
    if (v === null || v === undefined || v === '') continue
    if (typeof v === 'string' && v.trim() === '') continue
    return true
  }
  return false
}

/** 从 G7-4 提取合营/联营（权益法）被投资单位 */
export interface G7EquityInvesteeOption {
  name: string
  /** G7-4 行 id，作为跨表 investeeId */
  investeeId: string
  /**
   * 持股比例（小数 0~1）。
   * 优先直接+间接持股合计；皆空则用表决权比例。
   */
  investmentRatio: number | null
}

/** G7-4 比例字段 → 小数；G7-4 默认存百分数，ratioScale=fraction 时已是小数 */
export function parseG74HoldingRatioFraction(r: Record<string, any>): number | null {
  const asFraction = r.ratioScale === 'fraction'
  const toFrac = (raw: number): number => (
    asFraction
      ? Math.round(raw * 1e6) / 1e6
      : Math.round((raw / 100) * 1e6) / 1e6
  )

  const direct = Number(r.directHoldingRatio ?? r.direct_holding_ratio)
  const indirect = Number(r.indirectHoldingRatio ?? r.indirect_holding_ratio)
  const hasDirect = Number.isFinite(direct)
  const hasIndirect = Number.isFinite(indirect)
  if (hasDirect || hasIndirect) {
    return toFrac((hasDirect ? direct : 0) + (hasIndirect ? indirect : 0))
  }

  const total = Number(r.holdingRatioTotal ?? r.holding_ratio_total)
  if (Number.isFinite(total)) return toFrac(total)

  const votingRaw = Number(r.votingRatio ?? r.voting_ratio)
  if (Number.isFinite(votingRaw)) return toFrac(votingRaw)

  return null
}

export function loadEquityInvestees(g74Conclusion: unknown): G7EquityInvesteeOption[] {
  const parsed = parseChecklistJson(g74Conclusion)
  const list = Array.isArray(parsed) ? parsed : parsed?.rows
  if (!Array.isArray(list)) return []
  const out: G7EquityInvesteeOption[] = []
  const seen = new Set<string>()
  for (const r of list) {
    if (!isG74EquityInvesteeRow(r)) continue
    const name = String(r.investeeName ?? r.investee_name ?? '').trim()
    const investeeId = String(r.id ?? r.investeeId ?? r.investee_id ?? '').trim()
    if (!name) continue
    const dedupeKey = investeeId ? `id:${investeeId}` : `name:${name}`
    if (seen.has(dedupeKey)) continue
    seen.add(dedupeKey)
    out.push({
      name,
      investeeId,
      investmentRatio: parseG74HoldingRatioFraction(r),
    })
  }
  return out
}

/** @deprecated 优先使用 loadEquityInvestees；保留名称列表兼容旧调用 */
export function loadEquityInvesteeNames(g74Conclusion: unknown): string[] {
  return loadEquityInvestees(g74Conclusion).map((x) => x.name)
}

/**
 * G7-4 → G7-14：按 ID/名称确保被投资单位行存在，回填 investeeId；
 * 持股比例仅在目标行为空(0)时写入，不覆盖已有测算比例。
 */
export function applyG74InvesteesToG714Payload(
  g714Payload: any | null,
  g74Payload: unknown,
): SyncPolicyAdjResult {
  const investees = loadEquityInvestees(g74Payload)
  if (!investees.length) {
    return { ok: false, message: 'G7-4 中暂无合营/联营企业' }
  }
  const payload = clonePayload(g714Payload)
  let created = 0
  let linked = 0
  let ratioFilled = 0
  for (const inv of investees) {
    const beforeCount = (payload.groups || []).length
    const rows = ensureG714InvesteeRows(payload, {
      investeeName: inv.name,
      investeeId: inv.investeeId || undefined,
    })
    const afterCount = (payload.groups || []).length
    if (afterCount > beforeCount) created += 1
    if (inv.investeeId && rows.some((r: any) => String(r.investeeId || '') === inv.investeeId)) {
      linked += 1
    }
    if (inv.investmentRatio != null && inv.investmentRatio > 0) {
      for (const row of rows) {
        if (!parseNum(row.investmentRatio)) {
          row.investmentRatio = inv.investmentRatio
          recalcEquityCalcRow(row)
          ratioFilled += 1
        }
      }
      const group = (payload.groups || []).find((g: any) => matchInvestee(g, {
        investeeName: inv.name,
        investeeId: inv.investeeId || undefined,
      }))
      if (group && !parseNum(group.ownershipRatio) && inv.investmentRatio) {
        // 兼容旧 group 上偶发的 ownershipRatio
        group.ownershipRatio = inv.investmentRatio
      }
    }
  }

  // NA：ownershipRatio 为空时从刚写入的行比例回填
  if (Array.isArray(payload.netAssetAdjustments)) {
    for (const adj of payload.netAssetAdjustments) {
      if (parseNum(adj.ownershipRatio)) continue
      const row = (payload.rows || []).find((r: any) => matchInvestee(r, {
        investeeName: adj.investeeName,
        investeeId: adj.investeeId,
      }))
      const fromRow = parseNum(row?.investmentRatio)
      if (fromRow > 0) adj.ownershipRatio = fromRow
    }
  }

  syncFlatRowsFromGroups(payload)
  return {
    ok: true,
    message: `已从 G7-4 同步 ${investees.length} 家合营/联营（新增 ${created}，关联ID ${linked}，补比例 ${ratioFilled}）`,
    payload,
  }
}

/** 是否 G7-4 子公司行（与 loadSubsidiaryInvestees 口径一致） */
export function isG74SubsidiaryRow(r: Record<string, unknown>): boolean {
  const groupType = String(r.groupType ?? r.group_type ?? r.controlType ?? '')
  const method = String(r.accountingMethod ?? r.accounting_method ?? '')
  return groupType === 'subsidiary'
    || groupType === '子公司'
    || method.includes('成本法')
}

/** 是否 G7-4 权益法合营/联营行（与 loadEquityInvestees 口径一致） */
export function isG74EquityInvesteeRow(r: Record<string, unknown>): boolean {
  const groupType = String(r.groupType ?? r.group_type ?? '')
  const method = String(r.accountingMethod ?? r.accounting_method ?? '')
  return groupType === 'joint_venture'
    || groupType === 'associate'
    || method.includes('权益法')
}
export interface G7SubsidiaryInvesteeOption {
  /** 与 G7-4 行 id 对齐，供跨表 investeeId 绑定 */
  id: string
  name: string
  /** 直接+间接持股，小数 0~1 */
  shareholdingRatio: number | null
  /** 投资成本/账面近似值（G7-4 investmentAmount） */
  carryingAmount: number | null
  votingRatio: number | null
}

/**
 * 从 G7-4 提取子公司清单，供 G7-7/10/11 下拉与预填。
 * G7-4 比例存百分数(0~100)；若 ratioScale=fraction 则已是小数。
 */
export function loadSubsidiaryInvestees(g74Conclusion: unknown): G7SubsidiaryInvesteeOption[] {
  const parsed = parseChecklistJson(g74Conclusion)
  const list = Array.isArray(parsed) ? parsed : parsed?.rows
  if (!Array.isArray(list)) return []

  const options: G7SubsidiaryInvesteeOption[] = []
  const seen = new Set<string>()

  for (const r of list) {
    if (!isG74SubsidiaryRow(r)) continue
    const name = String(r.investeeName ?? r.investee_name ?? '').trim()
    const id = String(r.id ?? r.investeeId ?? r.investee_id ?? '').trim()
    if (!name) continue
    const dedupeKey = id ? `id:${id}` : `name:${name}`
    if (seen.has(dedupeKey)) continue
    seen.add(dedupeKey)

    const asFraction = r.ratioScale === 'fraction'
    const direct = Number(r.directHoldingRatio ?? r.direct_holding_ratio)
    const indirect = Number(r.indirectHoldingRatio ?? r.indirect_holding_ratio)
    const hasDirect = Number.isFinite(direct)
    const hasIndirect = Number.isFinite(indirect)
    let shareholdingRatio: number | null = null
    if (hasDirect || hasIndirect) {
      const total = (hasDirect ? direct : 0) + (hasIndirect ? indirect : 0)
      shareholdingRatio = asFraction
        ? Math.round(total * 1e6) / 1e6
        : Math.round((total / 100) * 1e6) / 1e6
    }

    const votingRaw = Number(r.votingRatio ?? r.voting_ratio)
    let votingRatio: number | null = null
    if (Number.isFinite(votingRaw)) {
      votingRatio = asFraction
        ? Math.round(votingRaw * 1e6) / 1e6
        : Math.round((votingRaw / 100) * 1e6) / 1e6
    }

    const carrying = Number(r.investmentAmount ?? r.investment_amount)
    options.push({
      id: id || name,
      name,
      shareholdingRatio,
      carryingAmount: Number.isFinite(carrying) ? carrying : null,
      votingRatio,
    })
  }
  return options
}

function recalcEquityCalcRow(row: any): void {
  row.adjustedNetProfit = calcAdjustedNetProfit(
    row.reportedNetProfit,
    row.internalTransactionAdj,
    row.fvDepreciationAdj,
    row.accountingPolicyAdj,
    row.otherAdj,
  )
  row.equityShare = calcEquityShare(row.adjustedNetProfit, row.investmentRatio)
  row.ociShare = calcEquityShare(row.ociChange, row.investmentRatio)
  row.otherEquityShare = calcEquityShare(row.otherEquityChange, row.investmentRatio)
  row.incomeDifference = calcIncomeDifference(
    row.confirmedIncome,
    row.equityShare,
    row.dividendDistributed,
  )
  row.ociDifference = Math.round(
    (parseNum(row.confirmedOci) - parseNum(row.ociShare)) * 100,
  ) / 100
  row.otherEquityDifference = Math.round(
    (parseNum(row.confirmedOtherEquity) - parseNum(row.otherEquityShare)) * 100,
  ) / 100
  row.costClosing = Math.round((parseNum(row.costOpening) + parseNum(row.costChange)) * 100) / 100
  row.pnlAdjClosing = Math.round((parseNum(row.pnlAdjOpening) + parseNum(row.pnlAdjChange)) * 100) / 100
  row.ociBalChange = row.ociShare
  row.otherEqBalChange = row.otherEquityShare
  row.ociBalClosing = Math.round((parseNum(row.ociBalOpening) + parseNum(row.ociBalChange)) * 100) / 100
  row.otherEqBalClosing = Math.round((parseNum(row.otherEqBalOpening) + parseNum(row.otherEqBalChange)) * 100) / 100
  row.lteiBookBalance = calcLteiBookBalance(
    row.costClosing, row.pnlAdjClosing, row.ociBalClosing, row.otherEqBalClosing,
  )
  row.shareOfAuditedNetAssets = calcEquityShare(row.auditedNetAssets, row.investmentRatio)
  row.netAssetShareVariance = calcNetAssetShareVariance(
    row.lteiBookBalance, row.auditedNetAssets, row.investmentRatio,
  )
  row.unexplainedVariance = calcUnexplainedVariance(
    row.netAssetShareVariance, row.goodwill, row.cumulativeFvAdj, row.impairment,
  )
  row.openingReconVariance = calcOpeningReconVariance(
    row.costOpening, row.pnlAdjOpening, row.ociBalOpening, row.otherEqBalOpening, row.g72OpeningTotal,
  )
  row.closingReconVariance = calcClosingReconVariance(row.lteiBookBalance, row.g72ClosingTotal)
  row.closingBalance = calcEquityMethodBalance(
    row.openingBalance,
    row.equityShare,
    row.ociShare,
    row.otherEquityShare,
    row.dividendDistributed,
  )
}

export interface SyncPolicyAdjResult {
  ok: boolean
  message: string
  payload?: any
  /** 非阻断提示（如跳过未审数据） */
  warnings?: string[]
}

export interface ApplyFinancialInfoOptions {
  /** 为 true 时连同未审/待确认一并带入；默认仅已审（无状态字段的旧数据仍带入） */
  includeUnaudited?: boolean
}

/**
 * 将 G7-6 某被投资方的会计政策调整合计写入 G7-14 对应行的 accountingPolicyAdj，
 * 并重算相关公式列。若尚无该被投资方行，则新建一行。
 */
export function applyPolicyAdjToG714Payload(
  g714Payload: any | null,
  investeeName: string,
  adjustmentTotal: number,
  investeeId?: string,
): SyncPolicyAdjResult {
  const name = investeeName.trim()
  if (!name) {
    return { ok: false, message: '被投资单位名称为空，无法同步至 G7-14' }
  }

  const payload = g714Payload && typeof g714Payload === 'object'
    ? structuredClone(g714Payload)
    : { rows: [], groups: [], materialityLevel: 0, conclusion: '' }

  if (!Array.isArray(payload.rows)) payload.rows = []
  if (!Array.isArray(payload.groups)) payload.groups = []

  const adj = Math.round(parseNum(adjustmentTotal) * 100) / 100
  const ref: InvesteeRef = { investeeName: name, investeeId: investeeId || undefined }
  let updated = false

  const touchRow = (row: any) => {
    row.accountingPolicyAdj = adj
    if (ref.investeeId && !String(row.investeeId || '').trim()) row.investeeId = ref.investeeId
    recalcEquityCalcRow(row)
    updated = true
  }

  for (const g of payload.groups) {
    if (!matchInvestee(g, ref)) continue
    if (!Array.isArray(g.rows) || g.rows.length === 0) {
      const stub = createStubEquityRow(name, adj)
      if (ref.investeeId) stub.investeeId = ref.investeeId
      g.rows = [stub]
      if (ref.investeeId) g.investeeId = ref.investeeId
      updated = true
    } else {
      for (const row of g.rows) touchRow(row)
      if (ref.investeeId && !String(g.investeeId || '').trim()) g.investeeId = ref.investeeId
    }
  }

  const flatMatches = payload.rows.filter((r: any) => matchInvestee(r, ref))
  if (flatMatches.length > 0) {
    for (const row of flatMatches) touchRow(row)
  }

  if (!updated) {
    const stub = createStubEquityRow(name, adj)
    if (ref.investeeId) stub.investeeId = ref.investeeId
    payload.rows.push(stub)
    payload.groups.push({
      investeeName: name,
      investeeId: ref.investeeId,
      rows: [stub],
    })
    updated = true
  } else {
    // 保持 rows 与 groups 同步：用 groups 展平覆盖 rows
    if (payload.groups.length > 0) {
      payload.rows = payload.groups.flatMap((g: any) => g.rows ?? [])
    }
  }

  return {
    ok: true,
    message: `已将「${name}」会计政策调整 ${adj} 同步至 G7-14`,
    payload,
  }
}

/**
 * 从 G7-6 会计政策表（groups 或扁平 rows）汇总各被投资方「不一致」调整金额，写入 G7-14。
 * 仅累加 isConsistent==='不一致' 的金额；合计为 0 的被投资方跳过，避免冲掉 G7-14 手工 policy。
 */
export function applyG76PolicyToG714Payload(
  g714Payload: any | null,
  g76Raw: unknown,
): SyncPolicyAdjResult {
  const parsed = parseChecklistJson(g76Raw) ?? g76Raw
  if (parsed == null) {
    return { ok: false, message: '未找到 G7-6 会计政策数据' }
  }

  type Agg = { name: string; investeeId?: string; total: number }
  const byKey = new Map<string, Agg>()

  const addInconsistent = (nameRaw: unknown, amount: unknown, idRaw?: unknown, isConsistent?: unknown) => {
    const consistent = String(isConsistent ?? '').trim()
    // 扁平旧数据无一致性字段时：仅非零金额计入（兼容）；有字段则必须「不一致」
    if (consistent && consistent !== '不一致') return
    if (!consistent && parseNum(amount) === 0) return
    const name = String(nameRaw ?? '').trim()
    if (!name || name === '未分组') return
    const key = name
    const prev = byKey.get(key) || { name, investeeId: undefined, total: 0 }
    prev.total = Math.round((prev.total + parseNum(amount)) * 100) / 100
    const id = String(idRaw ?? '').trim()
    if (id && !prev.investeeId) prev.investeeId = id
    byKey.set(key, prev)
  }

  if (typeof parsed === 'object' && Array.isArray((parsed as any).groups)) {
    for (const g of (parsed as any).groups) {
      const rows = Array.isArray(g?.rows) ? g.rows : []
      for (const r of rows) {
        addInconsistent(
          g?.investeeName ?? g?.investee_name,
          r?.adjustmentAmount,
          g?.investeeId ?? g?.investee_id,
          r?.isConsistent ?? r?.is_consistent,
        )
      }
    }
  } else {
    const rows = Array.isArray(parsed)
      ? parsed
      : (Array.isArray((parsed as any)?.rows) ? (parsed as any).rows : [])
    for (const r of rows) {
      addInconsistent(
        r?.investeeName ?? r?.investee_name,
        r?.adjustmentAmount,
        r?.investeeId ?? r?.investee_id,
        r?.isConsistent ?? r?.is_consistent,
      )
    }
  }

  const actionable = [...byKey.values()].filter(agg => Math.abs(agg.total) > 0.005)
  if (actionable.length === 0) {
    return {
      ok: false,
      message: 'G7-6 无「不一致」调整金额可带入（全零已跳过，避免覆盖 G7-14 手工值）',
    }
  }

  let payload = g714Payload
  const names: string[] = []
  for (const agg of actionable) {
    const result = applyPolicyAdjToG714Payload(payload, agg.name, agg.total, agg.investeeId)
    if (!result.ok || !result.payload) {
      return { ok: false, message: result.message || `同步「${agg.name}」失败` }
    }
    payload = result.payload
    names.push(agg.name)
  }

  const skipped = byKey.size - actionable.length
  return {
    ok: true,
    message: skipped > 0
      ? `已从 G7-6 带入 ${names.length} 家会计政策调整（另跳过 ${skipped} 家零金额）`
      : `已从 G7-6 带入 ${names.length} 家会计政策调整`,
    payload,
  }
}

function createStubEquityRow(investeeName: string, accountingPolicyAdj: number): any {
  const row = {
    id: `emc-sync-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq: 1,
    investeeName,
    investeeId: '',
    reportedNetProfit: 0,
    internalTransactionAdj: 0,
    fvDepreciationAdj: 0,
    accountingPolicyAdj,
    otherAdj: 0,
    otherAdjFromG716: 0,
    adjustedNetProfit: 0,
    investmentRatio: 0,
    equityShare: 0,
    confirmedIncome: 0,
    confirmedOci: 0,
    ociDifference: 0,
    confirmedOtherEquity: 0,
    otherEquityDifference: 0,
    incomeDifference: 0,
    ociChange: 0,
    ociShare: 0,
    otherEquityChange: 0,
    otherEquityShare: 0,
    dividendDistributed: 0,
    openingBalance: 0,
    closingBalance: 0,
    costOpening: 0,
    costChange: 0,
    costClosing: 0,
    pnlAdjOpening: 0,
    pnlAdjChange: 0,
    pnlAdjClosing: 0,
    ociBalOpening: 0,
    ociBalChange: 0,
    ociBalClosing: 0,
    otherEqBalOpening: 0,
    otherEqBalChange: 0,
    otherEqBalClosing: 0,
    auditedNetAssets: 0,
    shareOfAuditedNetAssets: 0,
    lteiBookBalance: 0,
    netAssetShareVariance: 0,
    g72OpeningTotal: 0,
    g72ClosingTotal: 0,
    openingReconVariance: 0,
    closingReconVariance: 0,
    goodwill: 0,
    cumulativeFvAdj: 0,
    impairment: 0,
    unexplainedVariance: 0,
    unexplainedNature: 'pending',
    varianceExplanation: '',
    auditConclusion: '无差异',
  }
  recalcEquityCalcRow(row)
  return row
}

function clonePayload(g714Payload: any | null): any {
  return g714Payload && typeof g714Payload === 'object'
    ? structuredClone(g714Payload)
    : { rows: [], groups: [], materialityLevel: 0, conclusion: '', netAssetAdjustments: [], goodwillFvDetails: [] }
}

function syncFlatRowsFromGroups(payload: any): void {
  if (!Array.isArray(payload.groups)) payload.groups = []
  if (!Array.isArray(payload.rows)) payload.rows = []
  if (payload.groups.length > 0) {
    payload.rows = payload.groups.flatMap((g: any) => g.rows ?? [])
  }
}

export interface InvesteeRef {
  investeeName: string
  investeeId?: string | null
}

export function normalizeInvesteeKey(name: unknown): string {
  return String(name ?? '').trim()
}

export function investeeIdsEqual(a?: string | null, b?: string | null): boolean {
  const x = String(a ?? '').trim()
  const y = String(b ?? '').trim()
  return Boolean(x && y && x === y)
}

/** ID 优先；任一方缺 ID 时回退到 trim 后名称精确匹配 */
export function matchInvestee(
  target: { investeeName?: string; investeeId?: string | null },
  ref: InvesteeRef,
): boolean {
  if (investeeIdsEqual(target.investeeId, ref.investeeId)) return true
  const tid = String(target.investeeId ?? '').trim()
  const rid = String(ref.investeeId ?? '').trim()
  if (tid && rid) return false
  return normalizeInvesteeKey(target.investeeName) === normalizeInvesteeKey(ref.investeeName)
}

function toInvesteeRef(nameOrRef: string | InvesteeRef): InvesteeRef {
  if (typeof nameOrRef === 'string') {
    return { investeeName: nameOrRef }
  }
  return {
    investeeName: String(nameOrRef.investeeName ?? ''),
    investeeId: nameOrRef.investeeId,
  }
}

function backfillInvesteeId(targets: any[], investeeId?: string | null): void {
  const id = String(investeeId ?? '').trim()
  if (!id) return
  for (const t of targets) {
    if (!t) continue
    if (!String(t.investeeId ?? '').trim()) t.investeeId = id
  }
}

/**
 * 确保存在被投资单位行，返回该单位全部行（通常 1 行）。
 * 支持 string 名称或 { investeeName, investeeId }；双方有 ID 时按 ID 匹配。
 */
export function ensureG714InvesteeRows(
  payload: any,
  investeeNameOrRef: string | InvesteeRef,
): any[] {
  const ref = toInvesteeRef(investeeNameOrRef)
  const name = normalizeInvesteeKey(ref.investeeName)
  if (!Array.isArray(payload.groups)) payload.groups = []
  if (!Array.isArray(payload.rows)) payload.rows = []

  let group = payload.groups.find((g: any) => matchInvestee(g, ref))
  if (!group && name) {
    // 名称兜底时允许 group.investeeName 未 trim 的旧数据
    group = payload.groups.find(
      (g: any) => normalizeInvesteeKey(g.investeeName) === name,
    )
  }
  if (!group) {
    const stub = createStubEquityRow(name || '未命名', 0)
    if (ref.investeeId) stub.investeeId = String(ref.investeeId).trim()
    group = {
      investeeName: name || '未命名',
      investeeId: stub.investeeId,
      rows: [stub],
    }
    payload.groups.push(group)
    payload.rows.push(stub)
    return group.rows
  }

  if (name && !normalizeInvesteeKey(group.investeeName)) {
    group.investeeName = name
  } else if (name && !group.investeeName) {
    group.investeeName = name
  }
  backfillInvesteeId([group], ref.investeeId)

  if (!Array.isArray(group.rows) || group.rows.length === 0) {
    const stub = createStubEquityRow(String(group.investeeName || name || '未命名'), 0)
    if (group.investeeId) stub.investeeId = group.investeeId
    group.rows = [stub]
  }
  for (const row of group.rows) {
    if (name && !normalizeInvesteeKey(row.investeeName)) row.investeeName = name
    backfillInvesteeId([row], group.investeeId || ref.investeeId)
  }

  const flat = payload.rows.filter((r: any) => matchInvestee(r, {
    investeeName: String(group.investeeName || name),
    investeeId: group.investeeId || ref.investeeId,
  }))
  if (flat.length === 0) payload.rows.push(...group.rows)
  else backfillInvesteeId(flat, group.investeeId || ref.investeeId)

  return group.rows
}

function matchReportItem(item: string, keywords: string[]): boolean {
  const text = String(item || '')
  return keywords.some((k) => text.includes(k))
}

/**
 * G7-5 → G7-14：净利润→报告净利润；所有者权益/净资产→经审计净资产。
 * 默认仅采用 auditStatus=已审（或未填状态的旧数据）；未审/待确认计入 warnings。
 */
export function applyFinancialInfoToG714Payload(
  g714Payload: any | null,
  g75Payload: unknown,
  opts: ApplyFinancialInfoOptions = {},
): SyncPolicyAdjResult {
  const payload = clonePayload(g714Payload)
  const includeUnaudited = opts.includeUnaudited === true
  const parsed = parseChecklistJson(g75Payload) ?? g75Payload
  const groups = Array.isArray((parsed as any)?.groups)
    ? (parsed as any).groups
    : null
  const flatRows = Array.isArray((parsed as any)?.rows)
    ? (parsed as any).rows
    : Array.isArray(parsed) ? parsed : []

  const byKey = new Map<string, { name: string; id: string; rows: any[] }>()
  const put = (name: string, id: string, rows: any[]) => {
    const key = id ? `id:${id}` : `name:${name}`
    if (!byKey.has(key)) byKey.set(key, { name, id, rows: [] })
    const bucket = byKey.get(key)!
    if (name && !bucket.name) bucket.name = name
    if (id && !bucket.id) bucket.id = id
    bucket.rows.push(...rows)
  }
  if (groups) {
    for (const g of groups) {
      const name = normalizeInvesteeKey(g.investeeName ?? g.investee_name)
      const id = String(g.investeeId ?? g.investee_id ?? '').trim()
      if (!name && !id) continue
      put(name, id, Array.isArray(g.rows) ? g.rows : [])
    }
  } else {
    for (const r of flatRows) {
      const name = normalizeInvesteeKey(r.investeeName ?? r.investee_name)
      const id = String(r.investeeId ?? r.investee_id ?? '').trim()
      if (!name && !id) continue
      put(name, id, [r])
    }
  }

  if (byKey.size === 0) {
    return { ok: false, message: 'G7-5 无可用财务信息' }
  }

  let touched = 0
  let skippedUnauditedItems = 0
  const skippedNames = new Set<string>()

  for (const { name, id, rows: finRows } of byKey.values()) {
    let netProfit: number | null = null
    let netAssets: number | null = null
    for (const r of finRows) {
      const item = String(r.reportItem ?? r.report_item ?? '')
      const isProfit = matchReportItem(item, ['净利润'])
      const isEquity = matchReportItem(item, ['所有者权益', '净资产'])
      if (!isProfit && !isEquity) continue

      const status = String(r.auditStatus ?? r.audit_status ?? '').trim()
      const isAuditedOrLegacy = !status || status === '已审'
      if (!includeUnaudited && !isAuditedOrLegacy) {
        skippedUnauditedItems += 1
        skippedNames.add(name || id)
        continue
      }

      const amt = parseNum(r.currentAmount ?? r.current_amount)
      if (isProfit) netProfit = amt
      if (isEquity) netAssets = amt
    }
    if (netProfit == null && netAssets == null) continue
    const rows = ensureG714InvesteeRows(payload, { investeeName: name || id, investeeId: id || undefined })
    for (const row of rows) {
      if (netProfit != null) row.reportedNetProfit = netProfit
      if (netAssets != null) row.auditedNetAssets = netAssets
      recalcEquityCalcRow(row)
    }
    touched += 1
  }
  syncFlatRowsFromGroups(payload)

  const warnings: string[] = []
  if (skippedUnauditedItems > 0) {
    const names = [...skippedNames].slice(0, 5).join('、')
    const more = skippedNames.size > 5 ? `等${skippedNames.size}家` : ''
    warnings.push(
      `已跳过 ${skippedUnauditedItems} 项未审/待确认财务信息（${names}${more}）`,
    )
  }

  return {
    ok: touched > 0,
    message: touched > 0
      ? `已从 G7-5 同步 ${touched} 家被投资方净利润/净资产`
      : (skippedUnauditedItems > 0
        ? 'G7-5 仅有未审/待确认数据，未自动带入'
        : 'G7-5 未匹配到净利润或净资产项目'),
    payload,
    warnings: warnings.length ? warnings : undefined,
  }
}

/**
 * G7-17 → G7-14：按被投资单位写入减值准备列（impairment = impairmentAmount）
 */
export function applyG717ImpairmentToG714Payload(
  g714Payload: any | null,
  g717Payload: unknown,
): SyncPolicyAdjResult {
  const payload = clonePayload(g714Payload)
  const parsed = parseChecklistJson(g717Payload) ?? g717Payload
  const rows = Array.isArray((parsed as any)?.rows)
    ? (parsed as any).rows
    : Array.isArray(parsed) ? parsed : []
  if (!rows.length) return { ok: false, message: 'G7-17 无减值测试数据' }

  let touched = 0
  for (const r of rows) {
    const name = normalizeInvesteeKey(r.investeeName ?? r.investee_name)
    const id = String(r.investeeId ?? r.investee_id ?? '').trim()
    if (!name && !id) continue
    const amt = Math.round(parseNum(r.impairmentAmount ?? r.impairment_amount) * 100) / 100
    const targetRows = ensureG714InvesteeRows(payload, {
      investeeName: name || id,
      investeeId: id || undefined,
    })
    for (const row of targetRows) {
      row.impairment = amt
      const note = `【G7-17】减值测试金额 ${amt.toFixed(2)}`
      const prev = String(row.varianceExplanation || '')
      if (!prev.includes('【G7-17】减值测试')) {
        row.varianceExplanation = prev ? `${prev}\n${note}` : note
      }
      recalcEquityCalcRow(row)
    }
    touched += 1
  }
  if (touched === 0) return { ok: false, message: 'G7-17 无有效被投资单位' }
  syncFlatRowsFromGroups(payload)
  return {
    ok: true,
    message: `已从 G7-17 同步 ${touched} 家减值金额至 G7-14 减值准备列`,
    payload,
  }
}

/**
 * G7-16 → G7-14：未确认损失本期变动累加写入 otherAdj（保留其他来源分量）
 * （正数=新增未确认→调增调整后净利润以停止确认超额损失；负数=利润恢复反序确认）
 */
export function applyUnrecognizedLossToG714Payload(
  g714Payload: any | null,
  g716Payload: unknown,
): SyncPolicyAdjResult {
  const payload = clonePayload(g714Payload)
  const parsed = parseChecklistJson(g716Payload) ?? g716Payload
  const rows = Array.isArray((parsed as any)?.rows)
    ? (parsed as any).rows
    : Array.isArray(parsed) ? parsed : []
  if (!rows.length) return { ok: false, message: 'G7-16 无未确认损失数据' }

  let touched = 0
  for (const r of rows) {
    const name = normalizeInvesteeKey(r.investeeName ?? r.investee_name)
    const id = String(r.investeeId ?? r.investee_id ?? '').trim()
    if (!name && !id) continue
    const amt = hasDefinedField(r, 'currentChange', 'current_change')
      ? pickDefinedNum(r.currentChange, r.current_change)
      : pickDefinedNum(r.unrecognizedLoss, r.unrecognized_loss)
    const g716Amt = Math.round(parseNum(amt) * 100) / 100
    const targetRows = ensureG714InvesteeRows(payload, {
      investeeName: name || id,
      investeeId: id || undefined,
    })
    for (const row of targetRows) {
      const prevG716 = parseNum(row.otherAdjFromG716)
      const baseOther = Math.round((parseNum(row.otherAdj) - prevG716) * 100) / 100
      row.otherAdjFromG716 = g716Amt
      row.otherAdj = Math.round((baseOther + g716Amt) * 100) / 100
      recalcEquityCalcRow(row)
    }
    touched += 1
  }
  if (touched === 0) return { ok: false, message: 'G7-16 无有效被投资单位' }
  syncFlatRowsFromGroups(payload)
  return {
    ok: true,
    message: `已从 G7-16 累加同步 ${touched} 家未确认损失变动至 G7-14（otherAdj，保留其他来源）`,
    payload,
  }
}

/**
 * G7-15 → G7-14：按被投资单位汇总本年抵销变动 → internalTransactionAdj
 */
export function applyInternalElimToG714Payload(
  g714Payload: any | null,
  g715Payload: unknown,
): SyncPolicyAdjResult {
  const payload = clonePayload(g714Payload)
  const parsed = parseChecklistJson(g715Payload) ?? g715Payload
  const rows = Array.isArray((parsed as any)?.rows)
    ? (parsed as any).rows
    : Array.isArray(parsed) ? parsed : []
  if (!rows.length) return { ok: false, message: 'G7-15 无内部交易数据' }

  const sumByKey = new Map<string, { name: string; id: string; amt: number }>()
  for (const r of rows) {
    const name = normalizeInvesteeKey(r.investeeName ?? r.investee_name)
    const id = String(r.investeeId ?? r.investee_id ?? '').trim()
    if (!name && !id) continue
    // currentChange 已填写（含 0）时优先用本期变动；未填写才回退累计抵销额
    const amt = hasDefinedField(r, 'currentChange', 'current_change')
      ? pickDefinedNum(r.currentChange, r.current_change)
      : pickDefinedNum(r.eliminationAmount, r.elimination_amount)
    const key = id ? `id:${id}` : `name:${name}`
    const prev = sumByKey.get(key)
    if (!prev) sumByKey.set(key, { name, id, amt })
    else prev.amt = Math.round((prev.amt + amt) * 100) / 100
  }
  if (sumByKey.size === 0) return { ok: false, message: 'G7-15 无有效被投资单位' }

  let touched = 0
  for (const { name, id, amt } of sumByKey.values()) {
    const targetRows = ensureG714InvesteeRows(payload, {
      investeeName: name || id,
      investeeId: id || undefined,
    })
    for (const row of targetRows) {
      row.internalTransactionAdj = Math.round(amt * 100) / 100
      recalcEquityCalcRow(row)
    }
    touched += 1
  }
  syncFlatRowsFromGroups(payload)
  return {
    ok: true,
    message: `已从 G7-15 同步 ${touched} 家内部交易抵销至 G7-14`,
    payload,
  }
}

export interface GoodwillFvDetailLine {
  id: string
  investeeName: string
  /** 稳定被投资单位 ID（可选；优先于名称匹配） */
  investeeId?: string
  kind: 'goodwill' | 'fvAdj'
  description: string
  /** 商誉金额；或 FV 期末未摊销份额 */
  amount: number
  indexRef: string
  /** FV 滚存（可选）：期初未摊销 */
  openingUnamortized?: number
  /** FV 滚存（可选）：本期折旧摊销（份额）→ 回写 fvDepreciationAdj */
  currentDepreciationAdj?: number
  /** FV 滚存（可选）：其他变动 */
  otherChange?: number
}

export interface SyncPreviewLine {
  investeeName: string
  field: string
  fieldLabel: string
  before: number
  after: number
}

export interface LastCrossSheetSyncMeta {
  at: string
  sources: string[]
  changeCount: number
}

const G714_PREVIEW_FIELDS: { key: string; label: string }[] = [
  { key: 'reportedNetProfit', label: '报告净利润' },
  { key: 'auditedNetAssets', label: '经审计净资产' },
  { key: 'internalTransactionAdj', label: '内部交易抵销' },
  { key: 'otherAdj', label: '其他调整' },
  { key: 'otherAdjFromG716', label: '其中:G7-16未确认损失' },
  { key: 'openingBalance', label: '期初余额' },
  { key: 'investmentRatio', label: '持股比例' },
  { key: 'pnlAdjChange', label: '损益调整本期' },
  { key: 'confirmedIncome', label: '确认投资收益' },
  { key: 'confirmedOci', label: '账面确认OCI' },
  { key: 'confirmedOtherEquity', label: '账面确认其他权益' },
  { key: 'dividendDistributed', label: '股利' },
  { key: 'ociChange', label: 'OCI变动(被投资方)' },
  { key: 'otherEquityChange', label: '其他权益变动' },
  { key: 'costChange', label: '成本变动' },
  { key: 'g72OpeningTotal', label: 'G7-2期初总额' },
  { key: 'g72ClosingTotal', label: 'G7-2期末总额' },
  { key: 'goodwill', label: '商誉' },
  { key: 'cumulativeFvAdj', label: '累计FV' },
  { key: 'fvDepreciationAdj', label: 'FV折旧摊销' },
]

function ensureGoodwillFvDetails(payload: any): GoodwillFvDetailLine[] {
  if (!Array.isArray(payload.goodwillFvDetails)) payload.goodwillFvDetails = []
  return payload.goodwillFvDetails
}

/** FV 行：有滚存字段时重算 amount（期末）= 期初 + 其他 − 本期摊销 */
export function recalcGoodwillFvDetailAmount(line: GoodwillFvDetailLine): number {
  if (line.kind === 'fvAdj') {
    const hasRoll =
      line.openingUnamortized != null
      || line.currentDepreciationAdj != null
      || line.otherChange != null
    if (hasRoll) {
      line.amount = Math.round(
        (parseNum(line.openingUnamortized)
          + parseNum(line.otherChange)
          - parseNum(line.currentDepreciationAdj)) * 100,
      ) / 100
    }
  }
  return parseNum(line.amount)
}

function flatInvesteeRows(payload: any): Map<string, any> {
  const map = new Map<string, any>()
  const push = (row: any) => {
    const name = normalizeInvesteeKey(row?.investeeName)
    const id = String(row?.investeeId ?? '').trim()
    const key = id ? `id:${id}` : (name ? `name:${name}` : '')
    if (!key || map.has(key)) return
    map.set(key, row)
  }
  if (Array.isArray(payload?.groups)) {
    for (const g of payload.groups) {
      for (const r of g.rows ?? []) push(r)
    }
  }
  if (Array.isArray(payload?.rows)) {
    for (const r of payload.rows) push(r)
  }
  return map
}

/** 比较带入前后关键字段，生成预览行 */
export function buildG714SyncPreview(before: any, after: any): SyncPreviewLine[] {
  const beforeRows = [...flatInvesteeRows(before).values()]
  const afterRows = [...flatInvesteeRows(after).values()]
  const matchedBefore = new Set<any>()
  const lines: SyncPreviewLine[] = []

  const pushDiffs = (name: string, b: any | undefined, a: any | undefined) => {
    for (const { key, label } of G714_PREVIEW_FIELDS) {
      const bv = parseNum(b?.[key])
      const av = parseNum(a?.[key])
      if (Math.abs(bv - av) < 0.005) continue
      lines.push({
        investeeName: name,
        field: key,
        fieldLabel: label,
        before: bv,
        after: av,
      })
    }
  }

  for (const a of afterRows) {
    const ref = {
      investeeName: String(a.investeeName || ''),
      investeeId: a.investeeId,
    }
    const b = beforeRows.find((x) => matchInvestee(x, ref))
    if (b) matchedBefore.add(b)
    pushDiffs(normalizeInvesteeKey(a.investeeName) || String(a.investeeId || ''), b, a)
  }
  for (const b of beforeRows) {
    if (matchedBefore.has(b)) continue
    pushDiffs(normalizeInvesteeKey(b.investeeName) || String(b.investeeId || ''), b, undefined)
  }
  return lines
}

export function formatSyncPreviewMessage(lines: SyncPreviewLine[], max = 12): string {
  if (!lines.length) {
    return '未检测到主表字段变化（可能仅更新了明细附表结构）。是否仍写入？'
  }
  const shown = lines.slice(0, max).map(
    (l) => `• ${l.investeeName}｜${l.fieldLabel}：${l.before} → ${l.after}`,
  )
  const more = lines.length > max ? `<br/>…另有 ${lines.length - max} 项变化` : ''
  return `即将覆盖以下字段（共 ${lines.length} 项）：<br/>${shown.join('<br/>')}${more}`
}

export function stampLastCrossSheetSync(
  payload: any,
  sources: string[],
  changeCount: number,
): LastCrossSheetSyncMeta {
  const meta: LastCrossSheetSyncMeta = {
    at: new Date().toISOString(),
    sources: [...sources],
    changeCount,
  }
  payload.lastCrossSheetSync = meta
  return meta
}

/**
 * 明细合计回写行上 goodwill / cumulativeFvAdj / fvDepreciationAdj。
 * @param previousInvesteeNames 变更前曾由明细驱动的被投资单位（改名/删除时需清零旧汇总）
 */
export function applyGoodwillFvDetailsToRows(
  payload: any,
  previousInvesteeNames: string[] = [],
): void {
  const details = ensureGoodwillFvDetails(payload) as GoodwillFvDetailLine[]
  const byKey = new Map<string, {
    name: string
    id: string
    goodwill: number
    fv: number
    fvDep: number
  }>()
  for (const d of details) {
    const name = normalizeInvesteeKey(d.investeeName)
    const id = String(d.investeeId ?? '').trim()
    if (!name && !id) continue
    const key = id ? `id:${id}` : `name:${name}`
    if (!byKey.has(key)) byKey.set(key, { name, id, goodwill: 0, fv: 0, fvDep: 0 })
    const bucket = byKey.get(key)!
    const amt = recalcGoodwillFvDetailAmount(d)
    if (d.kind === 'goodwill') {
      bucket.goodwill += amt
    } else {
      bucket.fv += amt
      bucket.fvDep += parseNum(d.currentDepreciationAdj)
    }
  }

  const namesToWrite = new Set<string>([
    ...previousInvesteeNames.map((n) => normalizeInvesteeKey(n)).filter(Boolean),
    ...[...byKey.values()].map((b) => b.name).filter(Boolean),
  ])
  const idsToWrite = new Set<string>([
    ...[...byKey.values()].map((b) => b.id).filter(Boolean),
  ])

  const writeBucket = (
    ref: InvesteeRef,
    sums: { goodwill: number; fv: number; fvDep: number },
    createIfMissing: boolean,
  ) => {
    const existingRows = [
      ...(Array.isArray(payload.groups)
        ? payload.groups
          .filter((g: any) => matchInvestee(g, ref))
          .flatMap((g: any) => g.rows ?? [])
        : []),
      ...(Array.isArray(payload.rows)
        ? payload.rows.filter((r: any) => matchInvestee(r, ref))
        : []),
    ]
    const rows = createIfMissing
      ? (existingRows.length ? existingRows : ensureG714InvesteeRows(payload, ref))
      : existingRows
    const seen = new Set<any>()
    for (const row of rows) {
      if (seen.has(row)) continue
      seen.add(row)
      row.goodwill = Math.round(sums.goodwill * 100) / 100
      row.cumulativeFvAdj = Math.round(sums.fv * 100) / 100
      row.fvDepreciationAdj = Math.round(sums.fvDep * 100) / 100
      recalcEquityCalcRow(row)
    }
  }

  for (const bucket of byKey.values()) {
    writeBucket(
      { investeeName: bucket.name || bucket.id, investeeId: bucket.id || undefined },
      bucket,
      true,
    )
  }
  // 清零仅出现在 previousInvesteeNames、且当前明细已无对应的旧名称
  for (const name of namesToWrite) {
    const stillPresent = [...byKey.values()].some((b) => b.name === name)
    if (stillPresent) continue
    writeBucket({ investeeName: name }, { goodwill: 0, fv: 0, fvDep: 0 }, false)
  }
  void idsToWrite
  syncFlatRowsFromGroups(payload)
}

/**
 * G7-13 → G7-14：正差额写入商誉明细；调整后份额差写入累计FV明细，并回写主表列
 */
export function applyInvestmentCostToG714Payload(
  g714Payload: any | null,
  g713Payload: unknown,
): SyncPolicyAdjResult {
  const payload = clonePayload(g714Payload)
  const parsed = parseChecklistJson(g713Payload) ?? g713Payload
  const rows = Array.isArray((parsed as any)?.rows)
    ? (parsed as any).rows
    : Array.isArray(parsed) ? parsed : []
  if (!rows.length) return { ok: false, message: 'G7-13 无投资成本测试数据' }

  const details = ensureGoodwillFvDetails(payload) as GoodwillFvDetailLine[]
  // 清除同源 G7-13 自动明细，保留手工
  payload.goodwillFvDetails = details.filter(
    (d) => !String(d.indexRef || '').includes('G7-13') && !String(d.description || '').includes('【G7-13】'),
  )

  let touched = 0
  for (const r of rows) {
    const name = normalizeInvesteeKey(r.investeeName ?? r.investee_name)
    const investeeId = String(r.investeeId ?? r.investee_id ?? '').trim()
    if (!name && !investeeId) continue
    const displayName = name || investeeId
    const difference = parseNum(r.difference)
    const share = pickDefinedNum(r.shareOfNetAssets, r.share_of_net_assets)
    const nature = String(r.differenceNature ?? r.difference_nature ?? '')
    const indexRef = String(r.indexRef ?? r.index_ref ?? 'G7-13')

    if (difference > 0.005 || nature.includes('商誉')) {
      const amt = Math.max(difference, 0)
      if (amt > 0.005) {
        payload.goodwillFvDetails.push({
          id: `gwf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          investeeName: displayName,
          investeeId: investeeId || undefined,
          kind: 'goodwill',
          description: `【G7-13】初始投资成本大于享有份额（商誉）`,
          amount: amt,
          indexRef,
        })
      }
    } else if (difference < -0.005 || nature.includes('营业外')) {
      // 廉价购买：备查明细（amount=0 不计入商誉/FV 汇总），并写入行说明
      const bargain = Math.round(Math.abs(difference) * 100) / 100
      payload.goodwillFvDetails.push({
        id: `gwf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        investeeName: displayName,
        investeeId: investeeId || undefined,
        kind: 'fvAdj',
        description: `【G7-13】初始成本小于享有份额（营业外收入/廉价购买）${bargain}`,
        amount: 0,
        openingUnamortized: 0,
        currentDepreciationAdj: 0,
        otherChange: 0,
        indexRef,
      })
    }
    // 仅当「调整后享有份额」字段确有填写时才生成 FV 明细，避免默认 0 产生虚假差额
    if (hasDefinedField(r, 'adjustedShareOfNetAssets', 'adjusted_share_of_net_assets')) {
      const adjustedShare = pickDefinedNum(r.adjustedShareOfNetAssets, r.adjusted_share_of_net_assets)
      const fvShareDiff = Math.round((adjustedShare - share) * 100) / 100
      if (Math.abs(fvShareDiff) > 0.005) {
        payload.goodwillFvDetails.push({
          id: `gwf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          investeeName: displayName,
          investeeId: investeeId || undefined,
          kind: 'fvAdj',
          description: `【G7-13】调整后享有份额与可辨认份额差额（累计FV）`,
          amount: fvShareDiff,
          openingUnamortized: fvShareDiff,
          currentDepreciationAdj: 0,
          otherChange: 0,
          indexRef,
        })
      }
    }

    // 持股比例若 G7-14 为空则带入
    const ratioRaw = pickDefinedNum(r.investmentRatio, r.investment_ratio)
    const targetRows = ensureG714InvesteeRows(payload, {
      investeeName: displayName,
      investeeId: investeeId || undefined,
    })
    for (const row of targetRows) {
      if (!parseNum(row.investmentRatio) && ratioRaw) {
        // G7-13 通常已是小数；>1 则按百分数
        row.investmentRatio = Math.abs(ratioRaw) > 1.0001 ? ratioRaw / 100 : ratioRaw
      }
      if (difference < -0.005) {
        const note = `【G7-13】廉价购买利得 ${Math.abs(difference).toFixed(2)}`
        const prev = String(row.varianceExplanation || '')
        if (!prev.includes('【G7-13】廉价购买')) {
          row.varianceExplanation = prev ? `${prev}\n${note}` : note
        }
      }
    }
    touched += 1
  }

  applyGoodwillFvDetailsToRows(payload)
  return {
    ok: touched > 0,
    message: `已从 G7-13 同步 ${touched} 家商誉/FV/廉价购买备查至 G7-14`,
    payload,
  }
}

/**
 * G7-2 权益法明细 → G7-14：期初余额、比例、损益/OCI/其他权益/股利
 */
export function applyG72EquityToG714Payload(
  g714Payload: any | null,
  g72Payload: unknown,
): SyncPolicyAdjResult {
  const payload = clonePayload(g714Payload)
  const state = normalizeG7DetailRows(parseChecklistJson(g72Payload) ?? g72Payload)
  const equityRows = state.equityRows || []
  if (!equityRows.length) return { ok: false, message: 'G7-2 无权益法（合营/联营）明细' }

  let touched = 0
  for (const src of equityRows) {
    const name = normalizeInvesteeKey(src.investeeName)
    const investeeId = String((src as any).investeeId ?? '').trim()
    if (!name && !investeeId) continue
    const displayName = name || investeeId
    // 比例：审定/未审期末比例，或投资比例；>1 视为百分数（0 有效，不因 || 误跳过）
    const ratioRaw = pickDefinedNum(
      src.auditedClosingRatio,
      src.closingRatio,
      src.investmentRatio,
      src.openingRatio,
    )
    const ratio = Math.abs(ratioRaw) > 1.0001 ? ratioRaw / 100 : ratioRaw
    const rows = ensureG714InvesteeRows(payload, {
      investeeName: displayName,
      investeeId: investeeId || undefined,
    })
    for (const row of rows) {
      if (ratio) row.investmentRatio = Math.round(ratio * 1e8) / 1e8
      // normalize 后 audited* 由未审+AJE/RJE 重算；0 为合法审定数，不得用 || 回退
      row.openingBalance = pickDefinedNum(src.auditedOpeningAmount, src.openingAmount)
      row.g72OpeningTotal = pickDefinedNum(src.auditedOpeningAmount, src.openingAmount)
      row.g72ClosingTotal = pickDefinedNum(src.auditedClosingAmount, src.closingAmount)
      // 若成本期初为空，默认将 G7-2 期初总额落入成本期初（与源表批注：期初仅投资成本时一致）
      if (!parseNum(row.costOpening) && parseNum(row.g72OpeningTotal)) {
        row.costOpening = row.g72OpeningTotal
      }
      row.pnlAdjChange = pickDefinedNum(src.auditedProfitLoss, src.profitLossAdjustment)
      row.confirmedIncome = pickDefinedNum(src.auditedProfitLoss, src.profitLossAdjustment)
      row.dividendDistributed = pickDefinedNum(src.auditedDividend, src.dividendReceived)
      row.costChange = Math.round(
        (pickDefinedNum(src.auditedCostIncrease, src.costIncrease)
          - pickDefinedNum(src.auditedCostDecrease, src.costDecrease)) * 100,
      ) / 100
      const ociShare = pickDefinedNum(src.auditedOci, src.otherComprehensiveIncome)
      const otherShare = pickDefinedNum(src.auditedOtherEquity, src.otherEquityChange)
      const r = parseNum(row.investmentRatio)
      row.ociChange = r > 0 ? Math.round((ociShare / r) * 100) / 100 : 0
      row.otherEquityChange = r > 0 ? Math.round((otherShare / r) * 100) / 100 : 0
      recalcEquityCalcRow(row)
    }
    touched += 1
  }
  syncFlatRowsFromGroups(payload)
  return {
    ok: touched > 0,
    message: `已从 G7-2 同步 ${touched} 家权益法期初/本期变动至 G7-14`,
    payload,
  }
}

/** 手工追加商誉/FV 明细行 */
export function addGoodwillFvDetail(
  payload: any | null,
  line: Omit<GoodwillFvDetailLine, 'id'> & { id?: string },
): SyncPolicyAdjResult {
  const next = clonePayload(payload)
  const details = ensureGoodwillFvDetails(next)
  details.push({
    id: line.id || `gwf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    investeeName: line.investeeName,
    investeeId: line.investeeId,
    kind: line.kind,
    description: line.description,
    amount: parseNum(line.amount),
    indexRef: line.indexRef || '',
    openingUnamortized: line.openingUnamortized,
    currentDepreciationAdj: line.currentDepreciationAdj,
    otherChange: line.otherChange,
  })
  recalcGoodwillFvDetailAmount(details[details.length - 1])
  applyGoodwillFvDetailsToRows(next)
  return { ok: true, message: '已添加商誉/FV明细并回写', payload: next }
}

export function removeGoodwillFvDetail(payload: any | null, id: string): SyncPolicyAdjResult {
  const next = clonePayload(payload)
  const details = ensureGoodwillFvDetails(next) as GoodwillFvDetailLine[]
  const previousNames = details.map((d) => d.investeeName)
  next.goodwillFvDetails = details.filter((d) => d.id !== id)
  applyGoodwillFvDetailsToRows(next, previousNames)
  return { ok: true, message: '已删除明细并回写', payload: next }
}
