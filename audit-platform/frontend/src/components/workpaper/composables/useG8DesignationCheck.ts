/**
 * useG8DesignationCheck — G8-5 指定适当性检查
 *
 * 对齐 Excel「指定的适当性检查表G8-5」：
 * 按被投资单位矩阵核查「非交易性」与「权益工具+FVOCI指定」条件；
 * 投资项目 / 期末账面价值默认从 G8-2 明细取数。
 */
import { ref, computed, watch, onMounted, onUnmounted, getCurrentInstance, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ChecklistResponse } from './useF1FormData'
import { parseNum } from './useG8FormulaEngine'
import { api } from '@/services/apiProxy'
import {
  G8_FV_KEY,
  G8A_DESIGNATION_MARK_KEY,
  G8A_DESIGNATION_PROGRAM_NOS,
  markG8AProcedureSteps,
  matchG8InvesteeKey,
  reconcileG8FvWithDesignation,
} from './g8CrossHelpers'

export type G8Yn = 'yes' | 'no' | 'na' | ''

export const G8_YN_OPTIONS = [
  { value: 'yes', label: '是 / √' },
  { value: 'no', label: '否' },
  { value: 'na', label: '不适用' },
] as const

export interface G8DesignationRow {
  rowId: string
  seq: number
  /** 被投资单位（勾稽 G8-2） */
  investeeName: string
  /** 期末账面价值 / 审定公允价值 */
  closingBookValue: number
  /** 「非交易性」— 勾「是」表示存在该交易性情形，不宜指定 FVOCI */
  tradingNearTermSale: G8Yn
  tradingPortfolioShortTerm: G8Yn
  tradingDerivative: G8Yn
  /** 「权益工具投资」— 勾「是」表示满足 */
  equityInstrument: G8Yn
  /** 初始确认时不可撤销指定 FVOCI */
  designatedFvtoci: G8Yn
  /** 公允价值能够可靠计量 */
  fvReliable: G8Yn
  /** 指定 OCI 原因（可自 G8-2 带入） */
  designationReason: string
  /** 自 G8-4 带入的公允价值层次（用于勾稽） */
  fairValueLevel: string
  other: string
  indexRef: string
  detailRowId?: string
}

const ITEM_ID_ROWS = 'G8-designation-rows'
const ITEM_ID_CONCLUSION = 'G8-designation-conclusion'
const DETAIL_KEY = 'G8-detail-rows'

function genId(): string {
  return `g8dc-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function emptyDesignationRow(rowId: string, seq: number): G8DesignationRow {
  return {
    rowId,
    seq,
    investeeName: '',
    closingBookValue: 0,
    tradingNearTermSale: '',
    tradingPortfolioShortTerm: '',
    tradingDerivative: '',
    equityInstrument: '',
    designatedFvtoci: '',
    fvReliable: '',
    designationReason: '',
    fairValueLevel: '',
    other: '',
    indexRef: '',
  }
}

/** 是否存在任一交易性特征（不宜指定 FVOCI） */
export function hasTradingCharacteristic(row: G8DesignationRow): boolean {
  return (
    row.tradingNearTermSale === 'yes'
    || row.tradingPortfolioShortTerm === 'yes'
    || row.tradingDerivative === 'yes'
  )
}

/** 权益工具 + FVOCI 指定核心条件是否齐备 */
export function hasFvtociBasis(row: G8DesignationRow): boolean {
  return (
    row.equityInstrument === 'yes'
    && row.designatedFvtoci === 'yes'
    && row.fvReliable === 'yes'
    && !hasTradingCharacteristic(row)
  )
}

/** 矩阵行是否已完成必要勾选 */
export function isDesignationRowComplete(row: G8DesignationRow): boolean {
  if (!row.investeeName.trim() && !row.closingBookValue) return true
  const fields: G8Yn[] = [
    row.tradingNearTermSale,
    row.tradingPortfolioShortTerm,
    row.tradingDerivative,
    row.equityInstrument,
    row.designatedFvtoci,
    row.fvReliable,
  ]
  return fields.every((f) => f !== '')
}

/** 自动归纳指定适当性文案 */
export function designationBasisLabel(row: G8DesignationRow): string {
  if (!row.investeeName.trim() && !row.closingBookValue) return '—'
  if (hasTradingCharacteristic(row)) {
    const t: string[] = []
    if (row.tradingNearTermSale === 'yes') t.push('近期出售/回购')
    if (row.tradingPortfolioShortTerm === 'yes') t.push('组合短期获利')
    if (row.tradingDerivative === 'yes') t.push('衍生/交易性')
    return `存在交易性情形（${t.join('、')}）→ 不宜指定 FVOCI`
  }
  if (hasFvtociBasis(row)) return '非交易性权益工具，指定 FVOCI 适当'
  const missing: string[] = []
  if (row.equityInstrument !== 'yes') missing.push('权益工具')
  if (row.designatedFvtoci !== 'yes') missing.push('不可撤销指定')
  if (row.fvReliable !== 'yes') missing.push('公允价值可靠计量')
  if (missing.length) return `待补全：${missing.join('、')}`
  return '待完成矩阵勾选'
}

/** 根据矩阵统计生成 A/B/C 口径结论草稿（本地，不依赖 AI） */
export function buildDesignationConclusionDraft(input: {
  listed: number
  appropriate: number
  tradingRisk: number
  incomplete: number
  tradingNames?: string[]
}): string {
  const { listed, appropriate, tradingRisk, incomplete, tradingNames = [] } = input
  if (!listed) {
    return 'C、本期未列示其他权益工具投资，或尚未从 G8-2 取数完成指定适当性检查，范围受限，不可确认。'
  }
  if (incomplete > 0) {
    return `C、已列示 ${listed} 项中尚有 ${incomplete} 项未完成矩阵勾选，指定适当性检查范围受限，不可确认。`
  }
  if (tradingRisk > 0) {
    const names = tradingNames.length
      ? `（${tradingNames.slice(0, 5).join('、')}${tradingNames.length > 5 ? '等' : ''}）`
      : ''
    return `B、除存在交易性特征的 ${tradingRisk} 项${names}须重分类/调整外，其余 ${Math.max(listed - tradingRisk, 0)} 项指定为 FVOCI 未见异常。`
  }
  if (appropriate === listed) {
    return `A、已核查 ${listed} 项其他权益工具投资，均满足非交易性权益工具指定 FVOCI 条件，指定适当，未见异常。`
  }
  return `B、已列示 ${listed} 项中 ${appropriate} 项指定适当；其余项目条件未完全满足，除拟调整事项外未见其他异常。`
}

function isLegacyQuestionnaireRow(r: Record<string, unknown>): boolean {
  return typeof r.checkItem === 'string' && typeof r.sectionNo === 'string'
}

function normalizeRow(raw: Partial<G8DesignationRow> & Record<string, unknown>, i: number): G8DesignationRow {
  const base = emptyDesignationRow(String(raw.rowId ?? genId()), Number(raw.seq) || i + 1)
  return {
    ...base,
    ...raw,
    rowId: String(raw.rowId ?? base.rowId),
    seq: Number(raw.seq) || i + 1,
    investeeName: String(raw.investeeName ?? ''),
    closingBookValue: parseNum(raw.closingBookValue),
    tradingNearTermSale: (raw.tradingNearTermSale as G8Yn) ?? '',
    tradingPortfolioShortTerm: (raw.tradingPortfolioShortTerm as G8Yn) ?? '',
    tradingDerivative: (raw.tradingDerivative as G8Yn) ?? '',
    equityInstrument: (raw.equityInstrument as G8Yn) ?? '',
    designatedFvtoci: (raw.designatedFvtoci as G8Yn) ?? '',
    fvReliable: (raw.fvReliable as G8Yn) ?? '',
    designationReason: String(raw.designationReason ?? ''),
    fairValueLevel: String(raw.fairValueLevel ?? ''),
    other: String(raw.other ?? ''),
    indexRef: String(raw.indexRef ?? ''),
    detailRowId: raw.detailRowId ? String(raw.detailRowId) : undefined,
  }
}

function loadRows(map: Map<string, ChecklistResponse>): G8DesignationRow[] {
  const raw = map.get(ITEM_ID_ROWS)?.remark
  if (!raw) return [emptyDesignationRow(genId(), 1)]
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyDesignationRow(genId(), 1)]
    if (isLegacyQuestionnaireRow(parsed[0] as Record<string, unknown>)) {
      return [emptyDesignationRow(genId(), 1)]
    }
    return parsed.map((r, i) => normalizeRow(r, i))
  } catch {
    return [emptyDesignationRow(genId(), 1)]
  }
}

function parseDetailRows(map: Map<string, ChecklistResponse>): Array<{
  rowId: string
  investeeName: string
  closingBookValue: number
  designationReason: string
  fairValueLevel: string
}> {
  const raw = map.get(DETAIL_KEY)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .map((r: Record<string, unknown>, i: number) => ({
        rowId: String(r.rowId ?? r.id ?? `d-${i}`),
        investeeName: String(r.investeeName ?? ''),
        closingBookValue: parseNum(r.closingAdjusted ?? r.closingBalance ?? r.fairValueTotal ?? 0),
        designationReason: String(r.designationReason ?? ''),
        fairValueLevel: String(r.fairValueLevel ?? ''),
      }))
      .filter((r) => r.investeeName.trim())
  } catch {
    return []
  }
}

/** 从 G8-4 解析公允价值可靠计量结论（key 为规范化被投资单位名） */
function parseFvReliability(map: Map<string, ChecklistResponse>): Map<string, {
  fvReliable: G8Yn
  fairValueLevel: string
  indexHint: string
}> {
  const out = new Map<string, { fvReliable: G8Yn; fairValueLevel: string; indexHint: string }>()
  const raw = map.get(G8_FV_KEY)?.remark
  if (!raw) return out
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return out
    for (const r of parsed as Record<string, unknown>[]) {
      const name = String(r.investeeName ?? '').trim()
      if (!name) continue
      const level = String(r.fairValueLevel ?? '')
      const auditedFv = parseNum(r.closingAuditedFV)
      const technique = String(r.valuationTechnique ?? '').trim()
      const unobs = String(r.unobservableInputDesc ?? '').trim()
      let fvReliable: G8Yn = ''
      if (level === 'Level3') {
        fvReliable = technique && unobs ? 'yes' : auditedFv > 0 ? '' : 'no'
      } else if (level === 'Level1' || level === 'Level2') {
        fvReliable = auditedFv > 0 || !!level ? 'yes' : ''
      } else if (auditedFv > 0) {
        fvReliable = 'yes'
      }
      out.set(matchG8InvesteeKey(name), {
        fvReliable,
        fairValueLevel: level,
        indexHint: String(r.valuationDocIndex ?? '').trim() || 'G8-4',
      })
    }
  } catch { /* ignore */ }
  return out
}

export function useG8DesignationCheck(opts: {
  wpId: Ref<string>
  projectId?: Ref<string> | ComputedRef<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G8DesignationRow[]>(loadRows(opts.allResponses.value))
  const overallConclusion = ref(opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion ?? '')
  const validating = ref(false)
  const fvStale = ref(false)
  const procedureMarking = ref(false)

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G8A_DESIGNATION_MARK_KEY)?.remark
    || opts.allResponses.value.get(G8A_DESIGNATION_MARK_KEY)?.conclusion === 'completed',
  )

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    () => {
      rows.value = loadRows(opts.allResponses.value)
    },
  )

  watch(
    () => opts.allResponses.value.get(ITEM_ID_CONCLUSION)?.conclusion,
    (v) => {
      overallConclusion.value = v ?? ''
    },
  )

  const totalBookValue = computed(() =>
    rows.value.reduce((s, r) => s + (Number(r.closingBookValue) || 0), 0),
  )

  const stats = computed(() => {
    const listed = rows.value.filter((r) => r.investeeName.trim() || r.closingBookValue)
    const appropriate = listed.filter(hasFvtociBasis).length
    const tradingRisk = listed.filter(hasTradingCharacteristic).length
    const incomplete = listed.filter((r) => !isDesignationRowComplete(r)).length
    const missingBasis = listed.filter((r) => isDesignationRowComplete(r) && !hasFvtociBasis(r) && !hasTradingCharacteristic(r)).length
    return {
      total: rows.value.length,
      listed: listed.length,
      appropriate,
      tradingRisk,
      incomplete,
      missingBasis,
    }
  })

  const incompleteRows = computed(() => rows.value.filter((r) => !isDesignationRowComplete(r) && (r.investeeName.trim() || r.closingBookValue)))

  /** 与 G8-2 明细勾稽：名称缺失 / 账面合计差异 */
  const detailReconcile = computed(() => {
    const details = parseDetailRows(opts.allResponses.value)
    if (!details.length) {
      return { hasDetail: false, missingInDesignation: [] as string[], missingInDetail: [] as string[], bookDiff: 0, detailTotal: 0 }
    }
    const detailNames = new Set(details.map((d) => d.investeeName.trim()))
    const desigNames = new Set(
      rows.value.filter((r) => r.investeeName.trim()).map((r) => r.investeeName.trim()),
    )
    const missingInDesignation = [...detailNames].filter((n) => !desigNames.has(n))
    const missingInDetail = [...desigNames].filter((n) => !detailNames.has(n))
    const detailTotal = details.reduce((s, d) => s + d.closingBookValue, 0)
    const bookDiff = Math.round((totalBookValue.value - detailTotal) * 100) / 100
    return { hasDetail: true, missingInDesignation, missingInDetail, bookDiff, detailTotal }
  })

  /** 与 G8-4 公允价值层次一致性 */
  const levelReconcile = computed(() => {
    const raw = opts.allResponses.value.get(G8_FV_KEY)?.remark
    let fvRows: Array<{ investeeName: string; fairValueLevel: string }> = []
    if (raw) {
      try {
        const arr = JSON.parse(raw)
        if (Array.isArray(arr)) {
          fvRows = arr.map((r: Record<string, unknown>) => ({
            investeeName: String(r.investeeName ?? ''),
            fairValueLevel: String(r.fairValueLevel ?? ''),
          }))
        }
      } catch { /* ignore */ }
    }
    return reconcileG8FvWithDesignation(fvRows, rows.value)
  })

  const hasLevelMismatch = computed(() => {
    const r = levelReconcile.value
    return r.mismatches.length > 0 || r.missingInDesignation.length > 0 || r.missingInFv.length > 0
  })

  function persist(): void {
    if (opts.isReadonly.value) return
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function updateRow(rowId: string, patch: Partial<G8DesignationRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, ...patch }
      if ('closingBookValue' in patch) next.closingBookValue = parseNum(patch.closingBookValue)
      return next
    })
    persist()
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    const seq = rows.value.length + 1
    rows.value = [...rows.value, emptyDesignationRow(genId(), seq)]
    persist()
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  /** 从 G8-2 明细同步被投资单位、期末账面价值及指定原因 */
  function syncFromDetail(force = false): number {
    if (opts.isReadonly.value) return 0
    const details = parseDetailRows(opts.allResponses.value)
    if (!details.length) {
      ElMessage.warning('G8-2 明细暂无数据，请先编制明细表')
      return 0
    }

    const byDetailId = new Map(rows.value.filter((r) => r.detailRowId).map((r) => [r.detailRowId!, r]))
    const byName = new Map(rows.value.filter((r) => r.investeeName.trim()).map((r) => [r.investeeName.trim(), r]))

    const next: G8DesignationRow[] = []
    let seq = 1
    for (const d of details) {
      const prev = byDetailId.get(d.rowId) ?? byName.get(d.investeeName)
      if (prev && !force) {
        next.push({
          ...prev,
          seq: seq++,
          investeeName: d.investeeName,
          closingBookValue: d.closingBookValue,
          designationReason: d.designationReason || prev.designationReason,
          fairValueLevel: prev.fairValueLevel || d.fairValueLevel || '',
          detailRowId: d.rowId,
        })
        continue
      }
      const row = emptyDesignationRow(prev?.rowId ?? `sync-${d.rowId}`, seq++)
      row.investeeName = d.investeeName
      row.closingBookValue = d.closingBookValue
      row.designationReason = d.designationReason
      row.detailRowId = d.rowId
      row.fairValueLevel = prev?.fairValueLevel || d.fairValueLevel || ''
      row.equityInstrument = prev?.equityInstrument || 'yes'
      row.designatedFvtoci = prev?.designatedFvtoci || 'yes'
      row.fvReliable = prev?.fvReliable || (d.fairValueLevel ? 'yes' : '')
      row.tradingNearTermSale = prev?.tradingNearTermSale || 'no'
      row.tradingPortfolioShortTerm = prev?.tradingPortfolioShortTerm || 'no'
      row.tradingDerivative = prev?.tradingDerivative || 'no'
      row.other = prev?.other ?? ''
      row.indexRef = prev?.indexRef ?? 'G8-2'
      next.push(row)
    }

    for (const r of rows.value) {
      if (r.detailRowId) continue
      if (details.some((d) => d.investeeName === r.investeeName.trim())) continue
      if (!r.investeeName.trim() && !r.closingBookValue) continue
      next.push({ ...r, seq: seq++ })
    }

    rows.value = next.length ? next : [emptyDesignationRow(genId(), 1)]
    persist()
    ElMessage.success(`已从 G8-2 同步 ${details.length} 个被投资单位`)
    return details.length
  }

  /** 从 G8-4 公允价值测试带入「FV 可靠计量」勾选与层次 */
  function applyFromFairValue(): number {
    if (opts.isReadonly.value) return 0
    const fvMap = parseFvReliability(opts.allResponses.value)
    if (!fvMap.size) {
      ElMessage.warning('G8-4 公允价值测试暂无数据，请先编制 G8-4')
      return 0
    }
    let n = 0
    rows.value = rows.value.map((r) => {
      const name = r.investeeName.trim()
      if (!name) return r
      const hit = fvMap.get(matchG8InvesteeKey(name))
      if (!hit || !hit.fvReliable) return r
      n++
      const refs = new Set(
        String(r.indexRef || '')
          .split(/[,，;/|]/)
          .map((s) => s.trim())
          .filter(Boolean),
      )
      refs.add(hit.indexHint.startsWith('G8') ? hit.indexHint : 'G8-4')
      return {
        ...r,
        fvReliable: hit.fvReliable,
        fairValueLevel: hit.fairValueLevel || r.fairValueLevel,
        indexRef: [...refs].join('/'),
        other: r.other || (hit.fairValueLevel ? `G8-4层次：${hit.fairValueLevel}` : r.other),
      }
    })
    if (!n) {
      ElMessage.warning('G8-5 与 G8-4 被投资单位名称未匹配，请先从 G8-2 取数或核对名称')
      return 0
    }
    persist()
    ElMessage.success(`已从 G8-4 带入 ${n} 项公允价值可靠计量结论`)
    fvStale.value = false
    return n
  }

  /**
   * 联动刷新：G8-2 取数（保留已填勾选）→ 从 G8-4 带入 FV/层次
   */
  function refreshLinkage(): { detail: number; fv: number } {
    if (opts.isReadonly.value) return { detail: 0, fv: 0 }
    const detail = syncFromDetail(false)
    const fv = applyFromFairValue()
    fvStale.value = false
    return { detail, fv }
  }

  function onFairValueUpdated(ev: Event): void {
    if (opts.isReadonly.value) return
    const src = (ev as CustomEvent<{ source?: string }>)?.detail?.source || ''
    if (src.includes('G8-5')) return // 自身回写不提示
    if (!rows.value.some((r) => r.investeeName.trim() || r.closingBookValue)) return
    fvStale.value = true
  }

  if (getCurrentInstance()) {
    onMounted(() => {
      window.addEventListener('g8:fair-value-updated', onFairValueUpdated as EventListener)
    })
    onUnmounted(() => {
      window.removeEventListener('g8:fair-value-updated', onFairValueUpdated as EventListener)
    })
  }

  /**
   * 一键默认勾选（仅填空白）：
   * 非交易性三列 → 否；权益工具 / 不可撤销指定 → 是；不覆盖已有勾选。
   */
  function fillDefaultChecks(): number {
    if (opts.isReadonly.value) return 0
    let n = 0
    rows.value = rows.value.map((r) => {
      if (!r.investeeName.trim() && !r.closingBookValue) return r
      const patch: Partial<G8DesignationRow> = {}
      if (!r.tradingNearTermSale) patch.tradingNearTermSale = 'no'
      if (!r.tradingPortfolioShortTerm) patch.tradingPortfolioShortTerm = 'no'
      if (!r.tradingDerivative) patch.tradingDerivative = 'no'
      if (!r.equityInstrument) patch.equityInstrument = 'yes'
      if (!r.designatedFvtoci) patch.designatedFvtoci = 'yes'
      if (!Object.keys(patch).length) return r
      n++
      return { ...r, ...patch }
    })
    if (!n) {
      ElMessage.info('无需填充：已列示行均已有勾选')
      return 0
    }
    persist()
    ElMessage.success(`已为 ${n} 行填充默认勾选（非交易性=否，权益/指定=是；FV 列请用「从 G8-4 带入」）`)
    return n
  }

  function updateOverallConclusion(v: string): void {
    if (opts.isReadonly.value) return
    overallConclusion.value = v
    opts.debouncedSave(ITEM_ID_CONCLUSION, { conclusion: v })
  }

  /** 本地生成结论草稿并写入（不覆盖已有非空结论，除非 force） */
  function applyConclusionDraft(force = false): string {
    if (opts.isReadonly.value) return ''
    if (overallConclusion.value.trim() && !force) {
      ElMessage.info('已有综合结论，如需覆盖请先清空或使用强制生成')
      return ''
    }
    const tradingNames = rows.value
      .filter((r) => hasTradingCharacteristic(r) && r.investeeName.trim())
      .map((r) => r.investeeName.trim())
    const draft = buildDesignationConclusionDraft({
      listed: stats.value.listed,
      appropriate: stats.value.appropriate,
      tradingRisk: stats.value.tradingRisk,
      incomplete: stats.value.incomplete,
      tradingNames,
    })
    updateOverallConclusion(draft)
    ElMessage.success('已生成综合结论草稿（A/B/C 口径）')
    return draft
  }

  async function validateDesignationRemote(): Promise<{ ok: boolean; errors: { field: string; message: string; rowKey?: string }[] }> {
    if (!opts.wpId.value) {
      ElMessage.warning('底稿未就绪')
      return { ok: false, errors: [{ field: 'wpId', message: '底稿未就绪' }] }
    }
    validating.value = true
    try {
      const details = parseDetailRows(opts.allResponses.value)
      const fvRaw = opts.allResponses.value.get(G8_FV_KEY)?.remark
      let fairValueRows: Record<string, unknown>[] = []
      if (fvRaw) {
        try {
          const arr = JSON.parse(fvRaw)
          if (Array.isArray(arr)) fairValueRows = arr
        } catch { /* ignore */ }
      }
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g8/validate-formulas`,
        {
          designation_rows: rows.value.map((r) => ({
            rowId: r.rowId,
            investeeName: r.investeeName,
            closingBookValue: r.closingBookValue,
            tradingNearTermSale: r.tradingNearTermSale,
            tradingPortfolioShortTerm: r.tradingPortfolioShortTerm,
            tradingDerivative: r.tradingDerivative,
            equityInstrument: r.equityInstrument,
            designatedFvtoci: r.designatedFvtoci,
            fvReliable: r.fvReliable,
            fairValueLevel: r.fairValueLevel,
            other: r.other,
          })),
          detail_rows: details.map((d) => ({
            investeeName: d.investeeName,
            closingAdjusted: d.closingBookValue,
            closingBookValue: d.closingBookValue,
          })),
          fair_value_rows: fairValueRows.map((r) => ({
            investeeName: r.investeeName,
            fairValueLevel: r.fairValueLevel,
          })),
        },
        { _silent: true } as any,
      )
      const data = res?.data ?? res
      const errors = (data.errors ?? []) as { field: string; message: string; rowKey?: string }[]
      const ok = !!data.ok
      if (ok) ElMessage.success('G8-5 指定适当性校验通过')
      else ElMessage.warning(`校验发现 ${errors.length} 项问题`)
      return { ok, errors }
    } catch {
      ElMessage.warning('远程校验暂不可用，请先依据本地勾稽提示排查')
      return { ok: false, errors: [{ field: 'network', message: '远程校验不可用' }] }
    } finally {
      validating.value = false
    }
  }

  function validateBeforeSave(): boolean {
    const incomplete = incompleteRows.value
    if (incomplete.length) {
      ElMessage.warning(`还有 ${incomplete.length} 行未完成矩阵勾选`)
      return false
    }
    if (stats.value.tradingRisk > 0) {
      ElMessage.warning(`有 ${stats.value.tradingRisk} 项存在交易性特征，请在审计说明/结论中说明应对措施`)
    }
    return true
  }

  /** 回填 G8A seq2（指定适当性）为已完成 */
  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G8A')
      return -1
    }
    if (stats.value.listed === 0) {
      ElMessage.warning('请先从 G8-2 取数后再回填程序表')
      return -1
    }
    if (stats.value.incomplete > 0) {
      try {
        await ElMessageBox.confirm(
          `仍有 ${stats.value.incomplete} 项未完成矩阵勾选，是否仍标记 G8A 指定适当性程序为已完成？`,
          '回填 G8A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    procedureMarking.value = true
    try {
      const summary = [
        `G8-5 指定适当性已编制：列示 ${stats.value.listed} 项`,
        `适当 ${stats.value.appropriate}`,
        `交易性风险 ${stats.value.tradingRisk}`,
        `待完成勾选 ${stats.value.incomplete}`,
      ].join('；')
      const n = await markG8AProcedureSteps({
        projectId: pid,
        programNos: [...G8A_DESIGNATION_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G8-5',
        executionSummary: summary,
      })
      opts.debouncedSave(G8A_DESIGNATION_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary,
          programNos: [...G8A_DESIGNATION_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? '已回填 G8A 程序步骤 2（指定适当性）为已完成'
          : '已记录完成标记（程序表字段写入可能需刷新 G8A 查看）',
      )
      return Math.max(n, 1)
    } finally {
      procedureMarking.value = false
    }
  }

  return {
    rows,
    overallConclusion,
    validating,
    procedureMarking,
    procedureMarked,
    fvStale,
    totalBookValue,
    stats,
    incompleteRows,
    detailReconcile,
    levelReconcile,
    hasLevelMismatch,
    ynOptions: G8_YN_OPTIONS,
    hasTradingCharacteristic,
    hasFvtociBasis,
    isDesignationRowComplete,
    designationBasisLabel,
    updateRow,
    addRow,
    removeRow,
    syncFromDetail,
    applyFromFairValue,
    refreshLinkage,
    fillDefaultChecks,
    applyConclusionDraft,
    validateDesignationRemote,
    markProcedureComplete,
    updateOverallConclusion,
    validateBeforeSave,
    persist,
  }
}
