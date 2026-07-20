/**
 * G8 跨表联动辅助 — G8-2 / G8-3 / G8-4 / G8-5
 */
import { G8_ACCOUNT_CODE, G8_ADJ_WRITEBACK_ROW_KEY } from './g8Constants'
import { parseNum, calcAdjustedAmount } from './useG8FormulaEngine'
import { parseG8AdjStore, patchG8AdjRow } from './g8AdjStorage'
import { G8_SHEET_LABEL_MAP, resolveG8SheetLabel } from './g8SheetLabels'
import type { ChecklistResponse } from './useF1FormData'

/** 辅助核算取数行（生成 G8-2 明细） */
export interface G8AuxInvesteeSeed {
  investeeName: string
  openingBalance: number
  closingBalance: number
  auxType: string
  auxCode: string
}

/** G8-4 回写 G8-2 所需的最小字段 */
export interface G8FvPushDetailSource {
  investeeName: string
  fairValueLevel: string
  valuationMethod: string
  closingAuditedQty: number
  closingAuditedPrice: number
  closingAuditedFV: number
}

export const G8_DETAIL_KEY = 'G8-detail-rows'
export const G8_ADJ_KEY = 'G8-adjustment-rows'
export const G8_FV_KEY = 'G8-fv-test-rows'
export const G8_DESIGNATION_KEY = 'G8-designation-rows'
export const G8_ADJ_ROWS_KEY = 'G8-adj-rows'

export function matchG8InvesteeKey(name: string): string {
  let s = (name || '').trim().toLowerCase()
  // 去掉 OCI 分录后缀、空白、常见公司后缀与括号内容噪声
  s = s.replace(/（oci）|\(oci\)/gi, '')
  s = s.replace(/\s+/g, '')
  s = s.replace(/[（(][^）)]*[）)]/g, '')
  const suffixes = [
    '股份有限公司',
    '有限责任公司',
    '有限公司',
    '集团股份',
    '集团公司',
    '集团',
    '公司',
  ]
  for (const suf of suffixes) {
    if (s.endsWith(suf) && s.length > suf.length + 1) {
      s = s.slice(0, -suf.length)
      break
    }
  }
  return s
}

/** 两名称是否视为同一被投资单位（精确键相等，或规范化后互相包含） */
export function matchG8Investee(a: string, b: string): boolean {
  const ka = matchG8InvesteeKey(a)
  const kb = matchG8InvesteeKey(b)
  if (!ka || !kb) return false
  if (ka === kb) return true
  return ka.includes(kb) || kb.includes(ka)
}

/** 拉取科目 1503 辅助核算余额，按辅助名称汇总为被投资单位种子 */
export async function fetchG8AuxInvesteeSeeds(
  projectId: string,
  year?: number,
): Promise<{ seeds: G8AuxInvesteeSeed[]; dimType: string; error?: string }> {
  if (!projectId) return { seeds: [], dimType: '', error: '缺少项目 ID' }
  try {
    const http = (await import('@/utils/http')).default
    const { resolveAuditYearNumber } = await import('./workpaperAuditYear')
    const y = year
      ?? resolveAuditYearNumber(undefined, new Date().getFullYear() - 1)
      ?? (new Date().getFullYear() - 1)

    const { data } = await http.get(`/api/projects/${projectId}/ledger/aux-balance/${G8_ACCOUNT_CODE}`, {
      params: { year: y },
      _silent: true,
    } as any)

    const rows: any[] = Array.isArray(data)
      ? data
      : (data?.data ?? data?.items ?? data?.rows ?? [])

    if (!rows.length) {
      return { seeds: [], dimType: '', error: `科目 ${G8_ACCOUNT_CODE} 无辅助核算余额（年度 ${y}）` }
    }

    // 按维度类型分组，取行数最多的维度（通常为往来单位/客户/被投资单位）
    const byType = new Map<string, any[]>()
    for (const r of rows) {
      const t = String(r.aux_type ?? r.auxType ?? r.dim_type ?? '未分类').trim() || '未分类'
      if (!byType.has(t)) byType.set(t, [])
      byType.get(t)!.push(r)
    }
    let bestType = ''
    let bestRows: any[] = []
    for (const [t, list] of byType) {
      if (list.length > bestRows.length) {
        bestType = t
        bestRows = list
      }
    }

    const merged = new Map<string, G8AuxInvesteeSeed>()
    for (const r of bestRows) {
      const name = String(r.aux_name ?? r.auxName ?? r.name ?? '').trim()
      if (!name) continue
      const key = matchG8InvesteeKey(name)
      const opening = parseNum(r.opening_balance ?? r.openingBalance)
      const closing = parseNum(r.closing_balance ?? r.closingBalance ?? r.ending_balance)
      const prev = merged.get(key)
      if (prev) {
        prev.openingBalance = Math.round((prev.openingBalance + opening) * 100) / 100
        prev.closingBalance = Math.round((prev.closingBalance + closing) * 100) / 100
      } else {
        merged.set(key, {
          investeeName: name,
          openingBalance: opening,
          closingBalance: closing,
          auxType: bestType,
          auxCode: String(r.aux_code ?? r.auxCode ?? ''),
        })
      }
    }

    const seeds = [...merged.values()].filter(
      (s) => Math.abs(s.openingBalance) > 0.01 || Math.abs(s.closingBalance) > 0.01,
    )
    if (!seeds.length) {
      return { seeds: [], dimType: bestType, error: `维度「${bestType}」无有效余额行` }
    }
    return { seeds, dimType: bestType }
  } catch (e: any) {
    return { seeds: [], dimType: '', error: e?.message || '辅助核算取数失败' }
  }
}

/**
 * 将 G8-2 明细期初审定/期末未审合计回写 G8-1 首行（fv_1），
 * 保留已有账项调整；并发布审定数。
 */
export function pushG8DetailTotalsToAdjudication(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  totals: { openingAdjusted: number; closingBalance: number; closingAdjusted: number },
): boolean {
  const store = parseG8AdjStore(responses.get(G8_ADJ_ROWS_KEY)?.remark)
  const next = patchG8AdjRow(store, G8_ADJ_WRITEBACK_ROW_KEY, {
    openingUnadjusted: totals.openingAdjusted,
    closingUnadjusted: totals.closingBalance,
    indexRef: 'G8-2',
  })
  debouncedSave(G8_ADJ_ROWS_KEY, { remark: JSON.stringify(next) })

  const row = next[G8_ADJ_WRITEBACK_ROW_KEY] ?? {}
  const closingAdj = calcAdjustedAmount(
    parseNum(row.closingUnadjusted),
    parseNum(row.closingAdjustment),
  )
  debouncedSave('G8-1-adjudicated-amount', { conclusion: String(closingAdj) })
  try {
    window.dispatchEvent(
      new CustomEvent('g8:detail-to-adjudication', {
        detail: { closingAdjusted: closingAdj, timestamp: Date.now() },
      }),
    )
  } catch { /* silent */ }
  return true
}

export function dispatchG8FairValueUpdated(source = 'G8-4'): void {
  try {
    window.dispatchEvent(
      new CustomEvent('g8:fair-value-updated', {
        detail: { source, timestamp: Date.now() },
      }),
    )
  } catch { /* silent */ }
}

/** 将 G8-4 审定结果回写 G8-2：层次 / 数量 / 单价 / 公允价值合计 / 估值方法 */
export function pushG8FvToDetail(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  fvRows: G8FvPushDetailSource[],
): number {
  const raw = responses.get(G8_DETAIL_KEY)?.remark
  if (!raw) return 0
  let details: Record<string, unknown>[]
  try {
    details = JSON.parse(raw)
    if (!Array.isArray(details)) return 0
  } catch {
    return 0
  }

  const byKey = new Map(
    fvRows
      .filter((r) => r.investeeName?.trim())
      .map((r) => [matchG8InvesteeKey(r.investeeName), r]),
  )
  let n = 0
  const next = details.map((d) => {
    const hit = byKey.get(matchG8InvesteeKey(String(d.investeeName ?? '')))
    if (!hit) return d
    n += 1
    return {
      ...d,
      fairValueLevel: hit.fairValueLevel || d.fairValueLevel,
      valuationMethod: hit.valuationMethod || d.valuationMethod,
      shareCount: hit.closingAuditedQty,
      pricePerShare: hit.closingAuditedPrice,
      fairValueTotal: hit.closingAuditedFV,
    }
  })
  if (n) {
    debouncedSave(G8_DETAIL_KEY, { remark: JSON.stringify(next) })
    dispatchG8FairValueUpdated('G8-4→G8-2')
  }
  return n
}

/**
 * 将 G8-4 层次 / FV 可靠计量结论同步到已存在的 G8-5 指定适当性行
 *（不新建行；名称匹配不上则跳过）
 */
export function pushG8FvToDesignation(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  fvRows: Array<{ investeeName: string; fairValueLevel: string }>,
): number {
  const raw = responses.get(G8_DESIGNATION_KEY)?.remark
  if (!raw) return 0
  let rows: Record<string, unknown>[]
  try {
    rows = JSON.parse(raw)
    if (!Array.isArray(rows) || !rows.length) return 0
    // 旧版问卷格式不处理
    if (typeof rows[0]?.checkItem === 'string' && typeof rows[0]?.sectionNo === 'string') return 0
  } catch {
    return 0
  }

  const byKey = new Map(
    fvRows
      .filter((r) => r.investeeName?.trim())
      .map((r) => [matchG8InvesteeKey(r.investeeName), r]),
  )
  let n = 0
  const next = rows.map((d) => {
    const name = String(d.investeeName ?? '')
    const hit = byKey.get(matchG8InvesteeKey(name))
    if (!hit) return d
    n += 1
    const level = hit.fairValueLevel || String(d.fairValueLevel ?? '')
    const refs = new Set(
      String(d.indexRef || '')
        .split(/[,，;/|]/)
        .map((s) => s.trim())
        .filter(Boolean),
    )
    refs.add('G8-4')
    return {
      ...d,
      fairValueLevel: level,
      fvReliable: level ? 'yes' : d.fvReliable,
      indexRef: [...refs].join('/'),
      other: d.other || (level ? `G8-4层次：${level}` : d.other),
    }
  })
  if (n) {
    debouncedSave(G8_DESIGNATION_KEY, { remark: JSON.stringify(next) })
    dispatchG8FairValueUpdated('G8-4→G8-5')
  }
  return n
}

export interface G8PushAdjItem {
  summary: string
  amount: number
  indexRef?: string
  remark?: string
}

/** G8-4→G8-3 推送指纹，用于幂等去重/覆盖 */
export function buildG8FvAdjFingerprint(
  summary: string,
  amount: number,
  source = 'G8-4',
): string {
  const key = matchG8InvesteeKey(summary).replace(/（oci）$/i, '')
  return `fvfp:${source}:${key}:${Math.round(Math.abs(parseNum(amount)) * 100)}`
}

function rowHasFvFingerprint(row: Record<string, unknown>, fp: string): boolean {
  return String(row.remark || '').includes(fp)
}

/**
 * 将 G8-4 公允差异追加至 G8-3（正差借 1503，负差贷 1503），触发既有回写 G8-1。
 * 同一指纹（来源+摘要+金额）已存在时先移除旧分录组再写入，避免重复推送叠分录。
 */
export function pushG8FvDiffToAdjustment(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  items: G8PushAdjItem[],
  source = 'G8-4',
): number {
  if (!items.length) return 0

  let existing: Record<string, unknown>[] = []
  const raw = responses.get(G8_ADJ_KEY)?.remark
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) existing = parsed
    } catch { /* ignore */ }
  }

  const fingerprints = items
    .filter((it) => Math.abs(parseNum(it.amount)) >= 0.01)
    .map((it) => buildG8FvAdjFingerprint(it.summary, it.amount, source))

  if (fingerprints.length) {
    existing = existing.filter((r) => !fingerprints.some((fp) => rowHasFvFingerprint(r, fp)))
  }

  const added: Record<string, unknown>[] = []
  items.forEach((it, i) => {
    const amt = Math.abs(parseNum(it.amount))
    if (amt < 0.01) return
    const isIncrease = parseNum(it.amount) > 0
    const fp = buildG8FvAdjFingerprint(it.summary, it.amount, source)
    const base = {
      date: new Date().toISOString().slice(0, 10),
      entryType: 'AJE',
      preparedBy: '',
      remark: `${it.remark || `来源 ${source}`}|${fp}`,
    }
    // FVOCI：公允上升 Dr 1503 / Cr OCI；下降反向
    added.push({
      ...base,
      rowId: `g8fv-adj-${Date.now().toString(36)}-${i}a`,
      seq: existing.length + added.length + 1,
      summary: it.summary,
      accountCode: G8_ACCOUNT_CODE,
      accountName: '其他权益工具投资',
      debitAmount: isIncrease ? amt : 0,
      creditAmount: isIncrease ? 0 : amt,
    })
    added.push({
      ...base,
      rowId: `g8fv-adj-${Date.now().toString(36)}-${i}b`,
      seq: existing.length + added.length + 1,
      summary: `${it.summary}（OCI）`,
      accountCode: '4002',
      accountName: '其他综合收益',
      debitAmount: isIncrease ? 0 : amt,
      creditAmount: isIncrease ? amt : 0,
    })
  })

  if (!added.length) return 0

  const merged = [...existing, ...added].map((r, i) => ({ ...r, seq: i + 1 }))
  debouncedSave(G8_ADJ_KEY, { remark: JSON.stringify(merged) })

  // 仅 1503 净额回写 G8-1（与 G8-3 syncWriteback 一致）
  const net = merged.reduce((s, r) => {
    if (!String(r.accountCode ?? '').startsWith('1503')) return s
    return s + parseNum(r.debitAmount) - parseNum(r.creditAmount)
  }, 0)
  debouncedSave('G8-adj-overlay', {
    remark: JSON.stringify({ rowKey: 'fv_1', closingAdjustment: net }),
  })

  // 同步写入 G8-1 rowStore，避免审定表未挂载时丢失
  try {
    const adjRaw = responses.get('G8-adj-rows')?.remark
    let store: Record<string, Record<string, unknown>> = {}
    if (adjRaw) {
      try { store = JSON.parse(adjRaw) } catch { store = {} }
    }
    store = {
      ...store,
      fv_1: { ...(store.fv_1 ?? {}), closingAdjustment: net },
    }
    debouncedSave('G8-adj-rows', { remark: JSON.stringify(store) })
  } catch { /* ignore */ }

  try {
    window.dispatchEvent(
      new CustomEvent('g8:adjustment-writeback', {
        detail: { rowKey: 'fv_1', closingAdjustment: net },
      }),
    )
  } catch { /* silent */ }

  dispatchG8FairValueUpdated(source)
  return added.length / 2
}

export interface G8LevelMismatch {
  investeeName: string
  fvLevel: string
  designationLevel: string
  issue: string
}

/** 解析 G8-5 other / fairValueLevel 中的层次标注 */
export function extractDesignationLevel(row: {
  fairValueLevel?: string
  other?: string
}): string {
  const direct = String(row.fairValueLevel ?? '').trim()
  if (direct) return direct
  const other = String(row.other ?? '')
  const m = other.match(/G8-4层次[：:]\s*(Level[123]|L[123])/i)
  if (!m) return ''
  const raw = m[1]
  if (/^L[123]$/i.test(raw)) return `Level${raw.slice(1)}`
  return raw.replace(/^level/i, 'Level')
}

/**
 * G8-4 与 G8-5 层次一致性比对：
 * - 两边均有的被投资单位，层次不一致
 * - G8-4 Level3 但 G8-5 已勾「FV可靠」却未标注 Level3
 * - G8-4 有项目但 G8-5 未列示
 */
export function reconcileG8FvWithDesignation(
  fvRows: Array<{ investeeName: string; fairValueLevel: string }>,
  designationRows: Array<{
    investeeName: string
    fairValueLevel?: string
    other?: string
    fvReliable?: string
  }>,
): {
  mismatches: G8LevelMismatch[]
  missingInDesignation: string[]
  missingInFv: string[]
} {
  const fvMap = new Map<string, string>()
  for (const r of fvRows) {
    const name = r.investeeName?.trim()
    if (!name) continue
    fvMap.set(matchG8InvesteeKey(name), r.fairValueLevel || '')
  }

  const desigMap = new Map<string, { name: string; level: string; fvReliable: string }>()
  for (const r of designationRows) {
    const name = r.investeeName?.trim()
    if (!name) continue
    desigMap.set(matchG8InvesteeKey(name), {
      name,
      level: extractDesignationLevel(r),
      fvReliable: String(r.fvReliable ?? ''),
    })
  }

  const mismatches: G8LevelMismatch[] = []
  const missingInDesignation: string[] = []
  const missingInFv: string[] = []

  for (const [key, fvLevel] of fvMap) {
    const d = desigMap.get(key)
    if (!d) {
      missingInDesignation.push(
        [...fvRows].find((r) => matchG8InvesteeKey(r.investeeName) === key)?.investeeName || key,
      )
      continue
    }
    if (d.level && fvLevel && d.level !== fvLevel) {
      mismatches.push({
        investeeName: d.name,
        fvLevel,
        designationLevel: d.level,
        issue: `G8-4 为 ${fvLevel}，G8-5 标注 ${d.level}`,
      })
    } else if (
      fvLevel === 'Level3'
      && (d.fvReliable === 'yes' || d.fvReliable === '是')
      && d.level !== 'Level3'
    ) {
      mismatches.push({
        investeeName: d.name,
        fvLevel,
        designationLevel: d.level || '（未标注）',
        issue: 'G8-4 为 Level3 且 G8-5 已勾 FV 可靠，但未标注 Level3',
      })
    }
  }

  for (const [key, d] of desigMap) {
    if (!fvMap.has(key)) missingInFv.push(d.name)
  }

  return { mismatches, missingInDesignation, missingInFv }
}

/** 差异相对未审合计的预警等级；hardAbs 通常取 B15 实际执行重要性 */
export function calcG8FvDiffWarning(
  absDiff: number,
  unadjTotal: number,
  opts?: { softRatio?: number; hardRatio?: number; hardAbs?: number },
): 'none' | 'soft' | 'hard' {
  const softRatio = opts?.softRatio ?? 0.05
  const hardRatio = opts?.hardRatio ?? 0.2
  const hardAbs = opts?.hardAbs ?? 0
  if (Math.abs(absDiff) <= 0.01) return 'none'
  const base = Math.abs(unadjTotal)
  const ratio = base > 0.01 ? Math.abs(absDiff) / base : 1
  if (ratio >= hardRatio || (hardAbs > 0 && Math.abs(absDiff) >= hardAbs)) return 'hard'
  if (ratio >= softRatio) return 'soft'
  return 'none'
}

/** 拉取项目实际执行重要性（B15） */
export async function fetchG8PerformanceMateriality(projectId: string): Promise<number> {
  if (!projectId) return 0
  try {
    const { fetchPerformanceMateriality } = await import('./g6CrossHelpers')
    const pm = await fetchPerformanceMateriality(projectId)
    return pm && pm > 0 ? pm : 0
  } catch {
    return 0
  }
}

export interface G8FvDiffSelectInput {
  rows: Array<{ investeeName: string; fairValueDiff: number; closingAuditedFV: number; closingUnadjustedFV: number; diffReason?: string }>
  performanceMateriality: number
  /** 默认 true：仅 |diff| > B15（B15 未取到时退回 >0.01） */
  onlyMaterial?: boolean
}

/** 按 B15 筛选可推送的公允差异行 */
export function selectG8FvDiffTargets(input: G8FvDiffSelectInput): {
  targets: G8FvDiffSelectInput['rows']
  skipped: Array<{ investeeName: string; diff: number; reason: string }>
  threshold: number
} {
  const onlyMaterial = input.onlyMaterial !== false
  const pm = parseNum(input.performanceMateriality)
  const threshold = onlyMaterial ? (pm > 0 ? pm : 0.01) : 0.01
  const targets: G8FvDiffSelectInput['rows'] = []
  const skipped: Array<{ investeeName: string; diff: number; reason: string }> = []
  for (const r of input.rows) {
    const diff = parseNum(r.fairValueDiff)
    if (Math.abs(diff) <= 0.01) continue
    if (Math.abs(diff) > threshold) {
      targets.push(r)
    } else {
      skipped.push({
        investeeName: r.investeeName || '未命名',
        diff,
        reason: pm > 0 ? `|差异| ${Math.abs(diff).toFixed(2)} ≤ B15 ${pm.toFixed(2)}` : '低于阈值',
      })
    }
  }
  return { targets, skipped, threshold }
}

/** G8A 程序表 sheet 名（field-overrides scope） */
export const G8A_PROCEDURE_SHEET = '其他权益工具投资实质性程序表G8A'

/** 精简模板 seq3 + 完整模板 seq10 均为公允价值测试；指定适当性为 seq2 */
export const G8A_FV_PROGRAM_NOS = [3, 10] as const
export const G8A_DESIGNATION_PROGRAM_NOS = [2] as const
/** 完整模板：新增/处置(6/7) 与关联方(12) 索引 G8-6 */
export const G8A_VOUCHER_PROGRAM_NOS = [6, 7, 12] as const

export const G8A_FV_MARK_KEY = 'G8A-fv-complete'
export const G8A_DESIGNATION_MARK_KEY = 'G8A-designation-complete'
export const G8A_VOUCHER_MARK_KEY = 'G8A-voucher-complete'

/** 回填 G8A 程序步骤状态（FieldOverrideService，与 GtAProgramConsole 一致） */
export async function markG8AProcedureSteps(opts: {
  projectId: string
  year?: number
  programNos: number[]
  status?: string
  linkedWorkpapers?: string
  executionSummary?: string
  sheetName?: string
}): Promise<number> {
  if (!opts.projectId || !opts.programNos.length) return 0
  const { api } = await import('@/services/apiProxy')
  const year = opts.year || new Date().getFullYear()
  const scope = `procedure_table:${opts.sheetName || G8A_PROCEDURE_SHEET}`
  const status = opts.status || 'completed'
  let n = 0
  for (const programNo of opts.programNos) {
    const fields: Array<{ field: string; value: unknown }> = [
      { field: 'status', value: status },
    ]
    if (opts.linkedWorkpapers) {
      fields.push({ field: 'linked_workpapers', value: opts.linkedWorkpapers })
    }
    if (opts.executionSummary) {
      fields.push({ field: 'execution_summary', value: opts.executionSummary })
    }
    for (const f of fields) {
      try {
        await api.post('/api/workpapers/field-overrides', {
          project_id: opts.projectId,
          year,
          scope,
          item_key: String(programNo),
          field: f.field,
          value: f.value,
        }, { _silent: true } as any)
        if (f.field === 'status') n += 1
      } catch { /* silent per field */ }
    }
  }
  try {
    window.dispatchEvent(
      new CustomEvent('g8:procedure-marked', {
        detail: {
          programNos: opts.programNos,
          status,
          linkedWorkpapers: opts.linkedWorkpapers,
          timestamp: Date.now(),
        },
      }),
    )
  } catch { /* silent */ }
  return n
}

export function buildG8FvProcedureSummary(input: {
  rowCount: number
  diffCount: number
  level3Count: number
  auditedTotal: number
  validationErrors: number
}): string {
  const parts = [
    `G8-4 公允价值测试已编制：${input.rowCount} 项`,
    `审定合计 ${input.auditedTotal.toFixed(2)}`,
    `差异项 ${input.diffCount}`,
    `Level3 ${input.level3Count}`,
  ]
  if (input.validationErrors > 0) {
    parts.push(`校验未通过 ${input.validationErrors} 项（请补全后再确认完成）`)
  }
  return parts.join('；')
}

export function buildG8VoucherProcedureSummary(input: {
  rowCount: number
  untested: number
  abnormal: number
  quantitative: number
  completionPct: number
  samplingMethod?: string
}): string {
  const parts = [
    `G8-6 凭证检查已编制：${input.rowCount} 笔`,
    `完成度 ${input.completionPct}%`,
    `未测 ${input.untested}`,
    `异常 ${input.abnormal}（金额类 ${input.quantitative}）`,
  ]
  if (input.samplingMethod) parts.push(`方法 ${input.samplingMethod}`)
  return parts.join('；')
}

/** 解析 G8 sheet 显示名并跳转（依赖 inject jumpToSection） */
export function jumpToG8Sheet(
  code: string,
  jumpFn: ((sheetLabel: string) => void) | null | undefined,
  availableSheets?: Array<{ sheet_name?: string }>,
): boolean {
  if (!jumpFn) return false
  const label = resolveG8SheetLabel(code, availableSheets) || G8_SHEET_LABEL_MAP[code] || code
  jumpFn(label)
  return true
}

export const G8_NAV_HIGHLIGHT_ADJ_EVENT = 'g8:highlight-adjustment-from-fv'
export const PROCEDURE_FOCUS_PROGRAM_EVENT = 'procedure:focus-program'

/** 推送差异后：高亮 G8-3 来源行并可选跳转 */
export function dispatchG8AdjHighlight(payload: {
  investeeNames?: string[]
  source?: string
}): void {
  try {
    window.dispatchEvent(
      new CustomEvent(G8_NAV_HIGHLIGHT_ADJ_EVENT, {
        detail: {
          investeeNames: payload.investeeNames ?? [],
          source: payload.source || 'G8-4',
          timestamp: Date.now(),
        },
      }),
    )
  } catch { /* silent */ }
}

/** 回填程序后：请求程序控制台滚动并高亮指定序号 */
export function dispatchProcedureFocus(payload: {
  programNos: number[]
  sheetCode?: string
  sheetName?: string
}): void {
  try {
    window.dispatchEvent(
      new CustomEvent(PROCEDURE_FOCUS_PROGRAM_EVENT, {
        detail: {
          programNos: payload.programNos,
          sheetCode: payload.sheetCode || 'G8A',
          sheetName: payload.sheetName || G8A_PROCEDURE_SHEET,
          timestamp: Date.now(),
        },
      }),
    )
  } catch { /* silent */ }
}

/** 询问用户是否跳转目标 sheet；取消则 false */
export async function confirmNavigateToSheet(opts: {
  title: string
  message: string
  confirmText?: string
}): Promise<boolean> {
  try {
    const { ElMessageBox } = await import('element-plus')
    await ElMessageBox.confirm(opts.message, opts.title, {
      type: 'success',
      confirmButtonText: opts.confirmText || '前往查看',
      cancelButtonText: '留在本页',
    })
    return true
  } catch {
    return false
  }
}
