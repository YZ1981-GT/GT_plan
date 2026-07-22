/**
 * G10-4 分类的适当性检查表
 * @see g10ClassificationModel.ts 数据模型
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ChecklistResponse } from './useF1FormData'
import { parseNum } from './useG10FormulaEngine'
import {
  type G10ClassificationRow,
  type G10Yn,
  G10_YN_OPTIONS,
  emptyClassificationRow,
  hasClassificationBasis,
  classifyBasisLabel,
} from './g10ClassificationModel'
import {
  collectClassificationIssues,
  getCategoryMismatchReason,
  mergeReclassificationDraftsIntoAdj,
  prefillBasisFromDetail,
  resolveReclassStatusForClassificationRow,
  reclassStatusLabel,
  type G10ReclassDraftStatus,
  G10_CLASSIFICATION_DRAFT_REVIEWED_EVENT,
} from './g10ClassificationCross'
import { commitG10AdjustmentWritebackFromRows } from './g10CrossHelpers'
import {
  buildG10ClassificationProcedureSummary,
  G10A_CLASSIFICATION_MARK_KEY,
  G10A_CLASSIFICATION_PROGRAM_NOS,
  markG10AProcedureSteps,
} from './g10FvCrossHelpers'

export type { G10ClassificationRow, G10Yn }
export { G10_YN_OPTIONS, emptyClassificationRow, hasClassificationBasis, classifyBasisLabel }

const DATA_KEY = 'G10-classification-rows'
const CONCLUSION_KEY = 'G10-classification-conclusion'
const DETAIL_KEY = 'G10-detail-rows'
const ADJ_ROWS_KEY = 'G10-aje-rows'

/** 旧版 28 行问卷行特征 */
function isLegacyQuestionnaireRow(p: Record<string, unknown>): boolean {
  return 'sectionNo' in p || 'checkItem' in p || 'compliance' in p || 'managementReply' in p
}

function normalizeRow(p: Partial<G10ClassificationRow> & Record<string, unknown>, i: number): G10ClassificationRow | null {
  if (isLegacyQuestionnaireRow(p)) return null
  const base = emptyClassificationRow(String(p.id ?? p.rowId ?? `row-${i + 1}`), Number(p.seq) || i + 1)
  return {
    ...base,
    id: String(p.id ?? p.rowId ?? base.id),
    seq: Number(p.seq) || i + 1,
    liabilityName: String(p.liabilityName ?? p.projectName ?? ''),
    closingBookValue: parseNum(p.closingBookValue),
    tradingNearTermSale: (p.tradingNearTermSale as G10Yn) || '',
    tradingPortfolioShortTerm: (p.tradingPortfolioShortTerm as G10Yn) || '',
    tradingDerivative: (p.tradingDerivative as G10Yn) || '',
    designatedMismatch: (p.designatedMismatch as G10Yn) || '',
    designatedFvManagement: (p.designatedFvManagement as G10Yn) || '',
    indexRef: String(p.indexRef ?? ''),
    liabilityCategory: p.liabilityCategory ? String(p.liabilityCategory) : undefined,
    detailRowId: p.detailRowId ? String(p.detailRowId) : undefined,
  }
}

function loadRows(map: Map<string, ChecklistResponse>): G10ClassificationRow[] {
  // 优先 remark（与其余 G10 sheet 一致）；兼容历史 conclusion 存行
  const item = map.get(DATA_KEY)
  const raw = item?.remark ?? item?.conclusion
  if (!raw) return [emptyClassificationRow('1', 1)]
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyClassificationRow('1', 1)]
    const normalized = parsed
      .map((p, i) => normalizeRow(p, i))
      .filter((r): r is G10ClassificationRow => r != null)
    return normalized.length ? normalized : [emptyClassificationRow('1', 1)]
  } catch {
    return [emptyClassificationRow('1', 1)]
  }
}

function parseDetailRows(map: Map<string, ChecklistResponse>): Array<{
  id: string
  liabilityName: string
  closingBookValue: number
  liabilityType: string
  liabilityCategory: string
  isDerivative: boolean
}> {
  const raw = map.get(DETAIL_KEY)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: Record<string, unknown>, i: number) => ({
      id: String(r.rowId ?? r.id ?? `d-${i}`),
      liabilityName: String(r.liabilityName ?? ''),
      closingBookValue: parseNum(r.closingAdjusted ?? r.closingBalance ?? 0),
      liabilityType: String(r.liabilityType ?? ''),
      liabilityCategory: String(r.liabilityCategory ?? ''),
      isDerivative: !!r.isDerivative,
    })).filter((r) => r.liabilityName.trim())
  } catch {
    return []
  }
}

function parseAdjRows(map: Map<string, ChecklistResponse>) {
  const raw = map.get(ADJ_ROWS_KEY)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function buildDetailMap(map: Map<string, ChecklistResponse>) {
  return new Map(
    parseDetailRows(map).map((d) => [d.id, { liabilityType: d.liabilityType, liabilityCategory: d.liabilityCategory }]),
  )
}

export function useG10ClassificationCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  wpId?: Ref<string>
  projectId?: Ref<string> | ComputedRef<string>
}) {
  const rows = ref<G10ClassificationRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')
  const aiLoading = ref(false)
  const procedureMarking = ref(false)

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.remark
      ?? opts.allResponses.value.get(DATA_KEY)?.conclusion,
    () => { rows.value = loadRows(opts.allResponses.value) },
  )
  watch(
    () => opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion,
    (v) => { if (v != null) auditConclusion.value = v },
  )

  const adjRevision = ref(0)
  watch(
    () => opts.allResponses.value.get(ADJ_ROWS_KEY)?.remark,
    () => { adjRevision.value += 1 },
  )

  const totalBookValue = computed(() =>
    rows.value.reduce((s, r) => s + (Number(r.closingBookValue) || 0), 0),
  )

  const stats = computed(() => {
    const detailMap = buildDetailMap(opts.allResponses.value)
    const withBasis = rows.value.filter(hasClassificationBasis).length
    const missingBasis = rows.value.filter(
      (r) => (r.closingBookValue || r.liabilityName) && !hasClassificationBasis(r),
    ).length
    const categoryMismatch = rows.value.filter((r) => {
      const cat = r.liabilityCategory || (r.detailRowId ? detailMap.get(r.detailRowId)?.liabilityCategory : '') || ''
      return !!getCategoryMismatchReason(r, cat)
    }).length
    const trading = rows.value.filter(
      (r) => r.tradingNearTermSale === 'yes' || r.tradingPortfolioShortTerm === 'yes' || r.tradingDerivative === 'yes',
    ).length
    const designated = rows.value.filter(
      (r) => r.designatedMismatch === 'yes' || r.designatedFvManagement === 'yes',
    ).length
    return { withBasis, missingBasis, categoryMismatch, trading, designated, total: rows.value.length }
  })

  const classificationIssues = computed(() =>
    collectClassificationIssues(rows.value, buildDetailMap(opts.allResponses.value)),
  )

  const adjRowsRef = computed(() => {
    void adjRevision.value
    return parseAdjRows(opts.allResponses.value)
  })

  const reclassStats = computed(() => {
    const adjRows = adjRowsRef.value
    let pending = 0
    let confirmed = 0
    for (const row of rows.value) {
      if (!row.liabilityName?.trim() && !row.closingBookValue) continue
      const status = resolveReclassStatusForClassificationRow(row, adjRows)
      if (status === 'pending') pending += 1
      if (status === 'confirmed') confirmed += 1
    }
    return { pending, confirmed }
  })

  function getReclassStatus(rowId: string): G10ReclassDraftStatus {
    const row = rows.value.find((r) => r.id === rowId)
    if (!row) return 'none'
    return resolveReclassStatusForClassificationRow(row, adjRowsRef.value)
  }

  function getReclassStatusLabel(rowId: string): string {
    return reclassStatusLabel(getReclassStatus(rowId))
  }

  const missingBasis = computed(() => stats.value.missingBasis)

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G10A_CLASSIFICATION_MARK_KEY)?.remark
    || opts.allResponses.value.get(G10A_CLASSIFICATION_MARK_KEY)?.conclusion === 'completed',
  )

  function persistAll() {
    if (opts.isReadonly.value) return
    // 行数据写入 remark（与 G10-1/2/3… 一致）；清空历史 conclusion 存行，避免双真源
    opts.debouncedSave(DATA_KEY, { remark: JSON.stringify(rows.value), conclusion: null })
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G10ClassificationRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      const next = { ...r, ...patch }
      if ('closingBookValue' in patch) next.closingBookValue = parseNum(patch.closingBookValue)
      return next
    })
    persistAll()
  }

  function addRow() {
    if (opts.isReadonly.value) return
    const seq = rows.value.length + 1
    rows.value = [...rows.value, emptyClassificationRow(`row-${Date.now()}`, seq)]
    persistAll()
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  /** 从 G10-2 明细同步项目名称与期末账面价值 */
  function syncFromDetail(force = false): number {
    if (opts.isReadonly.value) return 0
    const details = parseDetailRows(opts.allResponses.value)
    if (!details.length) {
      ElMessage.warning('G10-2 明细暂无数据，请先编制明细表')
      return 0
    }

    const byDetailId = new Map(rows.value.filter((r) => r.detailRowId).map((r) => [r.detailRowId!, r]))
    const byName = new Map(
      rows.value.filter((r) => r.liabilityName.trim()).map((r) => [r.liabilityName.trim(), r]),
    )

    const next: G10ClassificationRow[] = []
    let seq = 1
    for (const d of details) {
      const prev = byDetailId.get(d.id) ?? byName.get(d.liabilityName)
      if (prev && !force) {
        next.push({
          ...prev,
          seq: seq++,
          liabilityName: d.liabilityName,
          closingBookValue: d.closingBookValue,
          liabilityCategory: d.liabilityCategory,
          detailRowId: d.id,
        })
        continue
      }
      const row = emptyClassificationRow(prev?.id ?? `sync-${d.id}`, seq++)
      row.liabilityName = d.liabilityName
      row.closingBookValue = d.closingBookValue
      row.liabilityCategory = d.liabilityCategory
      row.detailRowId = d.id
      const prefilled = prefillBasisFromDetail(d.liabilityType, d.isDerivative, d.liabilityCategory)
      Object.assign(row, prefilled)
      if (prev) {
        row.tradingNearTermSale = prev.tradingNearTermSale || row.tradingNearTermSale
        row.tradingPortfolioShortTerm = prev.tradingPortfolioShortTerm || row.tradingPortfolioShortTerm
        row.tradingDerivative = prev.tradingDerivative || row.tradingDerivative
        row.designatedMismatch = prev.designatedMismatch || row.designatedMismatch
        row.designatedFvManagement = prev.designatedFvManagement || row.designatedFvManagement
        row.indexRef = prev.indexRef
      }
      next.push(row)
    }

    for (const r of rows.value) {
      if (r.detailRowId) continue
      if (details.some((d) => d.liabilityName === r.liabilityName.trim())) continue
      if (!r.liabilityName.trim() && !r.closingBookValue) continue
      next.push({ ...r, seq: seq++ })
    }

    rows.value = next.length ? next : [emptyClassificationRow('1', 1)]
    persistAll()
    ElMessage.success(`已从 G10-2 同步 ${details.length} 个负债项目`)
    return details.length
  }

  /** 将 G10-8 衍生工具核查结论写入索引，并对衍生负债预填依据 */
  function applyFromDerivativeCheck(): number {
    if (opts.isReadonly.value) return 0
    const conclusion = opts.allResponses.value.get('G10-derivative-conclusion')?.conclusion
    if (!conclusion?.trim()) {
      ElMessage.warning('请先完成 G10-8 衍生金融工具核查并填写结论')
      return 0
    }
    let n = 0
    rows.value = rows.value.map((r) => {
      if (!r.liabilityName.trim() && !r.closingBookValue) return r
      const details = parseDetailRows(opts.allResponses.value)
      const hit = details.find((d) => d.liabilityName === r.liabilityName.trim())
      const patch: Partial<G10ClassificationRow> = {
        indexRef: r.indexRef?.includes('G10-8') ? r.indexRef : [r.indexRef, 'G10-8'].filter(Boolean).join('+'),
      }
      if (hit?.isDerivative || hit?.liabilityType === '衍生金融负债') {
        patch.tradingDerivative = r.tradingDerivative || 'yes'
        n += 1
      }
      return { ...r, ...patch }
    })
    persistAll()
    if (n > 0) ElMessage.success(`已将 G10-8 结论关联至 ${n} 行衍生负债`)
    else ElMessage.info('无衍生负债行可写入，请先从 G10-2 取数')
    return n
  }

  /** 将缺依据/类别不一致项目生成 RJE 草稿写入 G10-3 */
  async function pushReclassificationDrafts(): Promise<number> {
    if (opts.isReadonly.value) return 0
    const issues = classificationIssues.value.filter((i) => Math.abs(i.closingBookValue) >= 0.005)
    if (!issues.length) {
      ElMessage.info('当前无需要重分类的缺依据项目（或账面价值为零）')
      return 0
    }
    try {
      await ElMessageBox.confirm(
        `将为 ${issues.length} 个项目各生成 1 组平衡 RJE 草稿（借 2101 / 贷 2501），写入 G10-3。请打开 G10-3 复核对方科目与金额。`,
        '生成重分类草稿',
        { type: 'warning', confirmButtonText: '生成', cancelButtonText: '取消' },
      )
    } catch {
      return 0
    }
    const { buildAllReclassificationDrafts } = await import('./g10ClassificationCross')
    const drafts = buildAllReclassificationDrafts(issues)
    const existing = opts.allResponses.value.get('G10-aje-rows')?.remark
    const { merged, added } = mergeReclassificationDraftsIntoAdj(existing, drafts)
    if (added <= 0) {
      ElMessage.info('G10-3 已存在相同摘要的重分类草稿，未重复追加')
      return 0
    }
    opts.debouncedSave('G10-aje-rows', { remark: merged })
    try {
      const parsed = JSON.parse(merged)
      if (Array.isArray(parsed) && parsed.length) {
        commitG10AdjustmentWritebackFromRows(
          opts.allResponses.value,
          opts.debouncedSave,
          parsed,
          { source: 'G10-4', offerDisclosurePull: added > 0 },
        )
      }
    } catch { /* ignore */ }
    try {
      sessionStorage.setItem('g10:review-classification-adj', String(issues.length))
    } catch { /* silent */ }
    try {
      window.dispatchEvent(new CustomEvent('g10:adjustment-updated', { detail: { added, projects: issues.length, source: 'G10-4' } }))
    } catch { /* silent */ }
    ElMessage.success(`已向 G10-3 追加 ${added} 行重分类草稿（${issues.length} 个项目）`)
    return added
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value || !opts.wpId?.value) return
    aiLoading.value = true
    try {
      const { api } = await import('@/services/apiProxy')
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g10/ai/classification-conclusion`,
        {
          existingContent: auditConclusion.value,
          rows: rows.value,
          relatedContext: {
            缺依据: stats.value.missingBasis,
            期末合计: totalBookValue.value,
          },
        },
        { _silent: true } as Record<string, unknown>,
      )
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) auditConclusion.value = text
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  function validateBeforeSave(): boolean {
    if (stats.value.missingBasis > 0) {
      ElMessage.warning(`有 ${stats.value.missingBasis} 项已列示账面价值但未勾选分类依据`)
      return false
    }
    return true
  }

  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G10A')
      return -1
    }
    const meaningful = rows.value.filter((r) => r.liabilityName.trim() || Math.abs(r.closingBookValue) > 0.005)
    if (!meaningful.length) {
      ElMessage.warning('请先编制 G10-4 分类检查（可从 G10-2 取数）')
      return -1
    }
    if (stats.value.missingBasis > 0) {
      try {
        await ElMessageBox.confirm(
          `仍有 ${stats.value.missingBasis} 项缺分类依据，是否仍标记 G10A 分类程序为已完成？`,
          '回填 G10A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    procedureMarking.value = true
    try {
      const summary = buildG10ClassificationProcedureSummary({
        rowCount: meaningful.length,
        withBasis: stats.value.withBasis,
        missingBasis: stats.value.missingBasis,
        categoryMismatch: stats.value.categoryMismatch,
        trading: stats.value.trading,
        designated: stats.value.designated,
        bookTotal: totalBookValue.value,
      })
      const n = await markG10AProcedureSteps({
        projectId: pid,
        programNos: [...G10A_CLASSIFICATION_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G10-4/G10-2',
        executionSummary: summary,
      })
      opts.debouncedSave(G10A_CLASSIFICATION_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary,
          programNos: [...G10A_CLASSIFICATION_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? `已回填 G10A 程序步骤 ${[...G10A_CLASSIFICATION_PROGRAM_NOS].join('/')}（分类适当性）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G10A 查看）',
      )
      return Math.max(n, 1)
    } finally {
      procedureMarking.value = false
    }
  }

  function bumpAdjRevision() {
    adjRevision.value += 1
  }

  onMounted(() => {
    window.addEventListener(G10_CLASSIFICATION_DRAFT_REVIEWED_EVENT, bumpAdjRevision)
    window.addEventListener('g10:adjustment-updated', bumpAdjRevision)
  })
  onBeforeUnmount(() => {
    window.removeEventListener(G10_CLASSIFICATION_DRAFT_REVIEWED_EVENT, bumpAdjRevision)
    window.removeEventListener('g10:adjustment-updated', bumpAdjRevision)
  })

  return {
    rows,
    sections: computed(() => []),
    overallConclusion: auditConclusion,
    auditConclusion,
    aiLoading,
    missingCompliance: missingBasis,
    missingBasis,
    classificationIssues,
    reclassStats,
    getReclassStatus,
    getReclassStatusLabel,
    stats,
    totalBookValue,
    procedureMarking,
    procedureMarked,
    ynOptions: G10_YN_OPTIONS,
    hasClassificationBasis,
    classifyBasisLabel,
    getCategoryMismatchReason,
    updateRow,
    addRow,
    removeRow,
    syncFromDetail,
    applyFromDerivativeCheck,
    pushReclassificationDrafts,
    generateAiConclusion,
    validateBeforeSave,
    markProcedureComplete,
    persist: persistAll,
    ITEM_ID: DATA_KEY,
  }
}

export default useG10ClassificationCheck
